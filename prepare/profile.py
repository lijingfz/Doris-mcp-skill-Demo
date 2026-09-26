"""Profile tools: get_query_profile, list_recent_queries.

Adds Doris query-runtime-profile access to velodb-mcp-server so that the
apache/doris-skills profile/debug skills (doris-profile-reader,
doris-debug/query) can run their evidence-first workflow end-to-end through
MCP instead of requiring the local `doriscli`.

Doris exposes query profiles over the FE HTTP *manager* API, NOT over SQL:
  - GET /rest/v2/manager/query/query_info                    -> recent queries
  - GET /rest/v2/manager/query/profile/text/<query_id>       -> full profile text

These endpoints are read-only. They authenticate with the same VeloDB/Doris
user:password the MCP already receives as a Bearer credential (HTTP Basic).

This module mirrors the conventions of src/tools/query.py and
src/tools/discovery.py:
  - async functions returning the JSON envelope from core.response
  - errors surfaced via error_response(ErrorCode.*, msg)

Design notes
------------
* Read-only: only issues HTTP GETs against the manager query endpoints.
* Credential pass-through: reuses the caller's identity (same model as the
  per-user aiomysql pools) — no shared admin credential.
* FE HTTP port is configurable (see the mcp-server.toml / ClusterConfig
  patch); Doris default is 8030.
* Fetch failures are returned as structured evidence (the skills treat a
  failed profile fetch as a signal — eviction, wrong port, connectivity —
  not a dead end), matching cli-investigation.md's "Connection-First Rule".
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from config.loader import ClusterConfig
from core.response import ErrorCode, error_response, success_response

# Doris FE manager query REST API paths.
_QUERY_INFO_PATH = "/rest/v2/manager/query/query_info"
_PROFILE_TEXT_PATH = "/rest/v2/manager/query/profile/text/{query_id}"

_HTTP_TIMEOUT_SECONDS = 30


def _fe_http_base(cluster: ClusterConfig, host: str | None = None) -> str:
    """Build the FE HTTP base URL, e.g. http://10.0.0.5:8030 .

    ClusterConfig.fe_http_port is added by the accompanying config patch and
    defaults to 8030 (the Doris FE HTTP port). host overrides cluster.fe_host
    for multi-FE deployments (parallels ConnectionPool's host override).
    """
    fe_host = host or cluster.fe_host
    fe_http_port = getattr(cluster, "fe_http_port", 8030)
    return f"http://{fe_host}:{fe_http_port}"


async def _fe_get(
    cluster: ClusterConfig,
    user: str,
    password: str,
    path: str,
    params: dict[str, Any] | None = None,
    host: str | None = None,
) -> tuple[int, Any]:
    """Perform a read-only GET against the FE HTTP manager API.

    Returns (http_status, parsed_json_or_text). Uses HTTP Basic with the
    caller's own Doris credentials — same identity as their SQL queries.
    """
    url = _fe_http_base(cluster, host) + path
    auth = aiohttp.BasicAuth(user, password)
    timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params, auth=auth) as resp:
            status = resp.status
            # Doris manager endpoints return JSON; fall back to text on error pages.
            try:
                body = await resp.json(content_type=None)
            except Exception:
                body = await resp.text()
            return status, body


async def list_recent_queries(
    cluster: ClusterConfig,
    user: str,
    password: str,
    limit: int = 20,
    host: str | None = None,
) -> str:
    """List recent / currently-running queries and their query_ids.

    Backs the skills' `doriscli profile list [--active]` step: the agent uses
    this to find a query_id when the user only describes a symptom or pastes
    SQL text without an id.
    """
    try:
        status, body = await _fe_get(
            cluster, user, password, _QUERY_INFO_PATH, host=host
        )
        if status == 401:
            return error_response(
                ErrorCode.AUTH_FAILED,
                "FE manager API rejected credentials (401). Verify the "
                "VeloDB/Doris user has access to the query manager API.",
            )
        if status != 200:
            return error_response(
                ErrorCode.CONNECTION_ERROR,
                f"FE manager query_info returned HTTP {status}. "
                f"Check fe_http_port (default 8030) reachability.",
            )

        # Doris wraps payloads as {"msg":"success","code":0,"data":{...},"count":N}.
        data = body.get("data", body) if isinstance(body, dict) else body
        rows = data.get("rows") if isinstance(data, dict) else data
        column_names = data.get("column_names") if isinstance(data, dict) else None

        # Trim to the requested number of most-recent rows when the FE returns a list.
        if isinstance(rows, list) and limit:
            rows = rows[:limit]

        return success_response(
            {"column_names": column_names, "rows": rows},
            {"row_count": len(rows) if isinstance(rows, list) else None},
        )
    except (asyncio.TimeoutError, TimeoutError):
        return error_response(
            ErrorCode.QUERY_TIMEOUT,
            "Timed out contacting FE manager API (query_info).",
        )
    except Exception as e:  # noqa: BLE001 — surface as structured evidence
        return error_response(ErrorCode.CONNECTION_ERROR, str(e))


async def get_query_profile(
    cluster: ClusterConfig,
    user: str,
    password: str,
    query_id: str,
    host: str | None = None,
) -> str:
    """Fetch the full runtime profile *text* for a given query_id.

    Backs the skills' `doriscli profile get <query_id>` step. The raw profile
    text is exactly what doris-profile-reader / doris-debug consume (operator
    timers, counters, RuntimeFilterInfo, WaitFor* counters, scanned tables).

    A failed fetch is returned as structured evidence (status + hint) rather
    than a hard error, because the skills treat fetch failure (eviction, wrong
    HTTP port, connectivity) as a diagnostic signal in itself.
    """
    if not query_id or not query_id.strip():
        return error_response(ErrorCode.INVALID_ARGUMENT, "query_id is required")

    path = _PROFILE_TEXT_PATH.format(query_id=query_id.strip())
    try:
        status, body = await _fe_get(cluster, user, password, path, host=host)
        if status == 401:
            return error_response(
                ErrorCode.AUTH_FAILED,
                "FE manager API rejected credentials (401).",
            )
        if status == 404:
            # Profile not found — likely evicted or wrong id. Evidence, not crash.
            return success_response(
                {
                    "query_id": query_id,
                    "profile_found": False,
                    "fetch_status": 404,
                },
                {
                    "hint": "Profile not found. It may have been evicted "
                    "(enable_profile / max retained profiles), the query_id "
                    "may be wrong, or profiling was off for this query.",
                },
            )
        if status != 200:
            return error_response(
                ErrorCode.CONNECTION_ERROR,
                f"FE manager profile/text returned HTTP {status}. "
                f"Check fe_http_port (default 8030) reachability.",
            )

        # Success: data holds the profile text (JSON-wrapped) or raw text.
        if isinstance(body, dict):
            profile_text = body.get("data", body)
        else:
            profile_text = body

        return success_response(
            {
                "query_id": query_id,
                "profile_found": True,
                "profile_text": profile_text,
            },
            {"source": "fe_manager_http", "path": path},
        )
    except (asyncio.TimeoutError, TimeoutError):
        return error_response(
            ErrorCode.QUERY_TIMEOUT,
            "Timed out contacting FE manager API (profile/text).",
        )
    except Exception as e:  # noqa: BLE001 — surface as structured evidence
        return error_response(ErrorCode.CONNECTION_ERROR, str(e))
