"""Doris query-profile tools: list_recent_queries, get_query_profile.

Doris serves query profiles over the FE HTTP API, not over SQL. Behavior of
Doris 4.1.4 that this module relies on (measured, specs/doris-mcp-quick/design.md §4.1):

  * errors come back as HTTP 200 with a JSON body {"code": <non-zero>, "msg": ...};
  * GET /rest/v1/query_profile lists the collected profiles of all users, also
    for non-admin accounts;
  * GET /rest/v2/manager/query/profile/text/<query_id> serves only the caller's
    own profiles (anything else -> {"code": 0, "data": {}}), text in data.profile;
  * GET /api/profile/text?query_id=<query_id> returns any user's profile as plain
    text, and plain text "query id <query_id> not found" for unknown ids.

Every request is a read-only GET authenticated with HTTP Basic as the Doris
account the server runs as. Profiles are only collected for queries run with
profiling on, e.g. SELECT /*+SET_VAR(enable_profile=true)*/ ...
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from mcp.types import ToolAnnotations

from core.audit import log_tool_call
from core.response import ErrorCode, error_response, success_response
from core.sensitive_mask import mask_sensitive

_LIST_PATH = "/rest/v1/query_profile"
_V2_TEXT_PATH = "/rest/v2/manager/query/profile/text/{query_id}"
_API_TEXT_PATH = "/api/profile/text"

# Doris prints each half of a query id unpadded (Long.toHexString), so 1-16 hex digits.
_QUERY_ID_RE = re.compile(r"^[0-9a-f]{1,16}-[0-9a-f]{1,16}$")
_SECTION_RE = re.compile(r"^([A-Za-z][A-Za-z ]*)(\([^)]*\))?:\s*$")
_COUNTER_RE = re.compile(r"^\s*- [^:]+: (.*)$")
_ZERO_VALUE_RE = re.compile(
    r"(?:(?:sum|avg|max|min)\s+)?0(?:\.0+)?\s*[A-Za-z]*\s*"
    r"(?:,\s*(?:sum|avg|max|min)\s+0(?:\.0+)?\s*[A-Za-z]*\s*)*"
)
_COLUMN_STATS_RE = re.compile(r"^(\s+)\S+#\d+ -> ")
_SQL_PREVIEW_CHARS = 200
_NOT_FOUND_HINT = (
    "No profile for this query_id. Profiles exist only for queries run with "
    "SELECT /*+SET_VAR(enable_profile=true)*/ ...; they can also be evicted. "
    "Use list_recent_queries to find valid query_ids."
)

Scope = Literal["all", "self"]


@dataclass(frozen=True)
class FeHttpTarget:
    """Doris FE HTTP endpoint plus the account used for Basic auth."""

    base_url: str
    user: str
    password: str = field(repr=False)
    timeout: float = 15.0


class _FeError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code


async def _fe_get(
    target: FeHttpTarget,
    path: str,
    params: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.Response:
    """GET path on the FE; transport/HTTP-level failures raise _FeError."""
    try:
        async with httpx.AsyncClient(
            base_url=target.base_url,
            auth=(target.user, target.password),
            timeout=target.timeout,
            transport=transport,
        ) as client:
            resp = await client.get(path, params=params)
    except httpx.TimeoutException as e:
        raise _FeError(ErrorCode.QUERY_TIMEOUT, f"Doris FE HTTP {path} timed out after {target.timeout:g}s") from e
    except httpx.HTTPError as e:
        raise _FeError(ErrorCode.CONNECTION_ERROR, f"Doris FE HTTP {path} unreachable: {type(e).__name__}") from e
    if resp.status_code in (401, 403):
        raise _FeError(ErrorCode.UNAUTHENTICATED, f"Doris FE HTTP rejected the credentials (HTTP {resp.status_code})")
    if resp.status_code != 200:
        raise _FeError(ErrorCode.CONNECTION_ERROR, f"Doris FE HTTP {path} returned HTTP {resp.status_code}")
    return resp


def _json_body(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        body = resp.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _raise_for_auth(body: dict[str, Any]) -> None:
    if body.get("code") == 401 or str(body.get("msg", "")).lower() == "unauthorized":
        raise _FeError(ErrorCode.UNAUTHENTICATED, "Doris FE HTTP rejected the credentials (code 401)")


def _checked_json(resp: httpx.Response, path: str) -> dict[str, Any]:
    """JSON body with code == 0, else _FeError."""
    body = _json_body(resp)
    if body is None:
        raise _FeError(ErrorCode.CONNECTION_ERROR, f"Doris FE HTTP {path} returned a non-JSON body")
    _raise_for_auth(body)
    if body.get("code") != 0:
        raise _FeError(ErrorCode.CONNECTION_ERROR, f"Doris FE HTTP {path} returned code={body.get('code')}: {body.get('msg')}")
    return body


def _query_row(row: dict[str, Any]) -> dict[str, Any]:
    sql = mask_sensitive(str(row.get("Sql Statement") or ""))
    if len(sql) > _SQL_PREVIEW_CHARS:
        sql = sql[: _SQL_PREVIEW_CHARS - 3] + "..."
    return {
        "query_id": row.get("Profile ID"),
        "user": row.get("User"),
        "default_db": row.get("Default Db"),
        "task_type": row.get("Task Type"),
        "state": row.get("Task State"),
        "start_time": row.get("Start Time"),
        "end_time": row.get("End Time"),
        "total": row.get("Total"),
        "sql": sql,
    }


async def list_recent_queries(
    target: FeHttpTarget,
    limit: int = 20,
    user: str = "",
    sql_contains: str = "",
    *,
    scope: Scope = "all",
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Newest-first list of queries that have a collected profile."""
    if not 1 <= limit <= 100:
        return error_response(ErrorCode.INVALID_PARAMS, "limit must be between 1 and 100")
    if scope == "self":
        user = target.user
    try:
        body = _checked_json(await _fe_get(target, _LIST_PATH, transport=transport), _LIST_PATH)
    except _FeError as e:
        return error_response(e.code, str(e))

    data = body.get("data")
    rows = data.get("rows") if isinstance(data, dict) else None
    needle = sql_contains.lower()
    matched = [
        r for r in rows or []
        if isinstance(r, dict)
        and (not user or r.get("User") == user)
        and (not needle or needle in str(r.get("Sql Statement") or "").lower())
    ]
    matched.sort(key=lambda r: str(r.get("Start Time") or ""), reverse=True)
    queries = [_query_row(r) for r in matched[:limit]]
    return success_response(
        {"queries": queries, "scope": scope},
        {"returned": len(queries), "matched": len(matched), "source": _LIST_PATH},
    )


async def _profile_via_v2(
    target: FeHttpTarget, qid: str, transport: httpx.AsyncBaseTransport | None
) -> tuple[str | None, dict[str, Any]]:
    path = _V2_TEXT_PATH.format(query_id=qid)
    body = _json_body(await _fe_get(target, path, transport=transport))
    if body is None:
        raise _FeError(ErrorCode.CONNECTION_ERROR, f"Doris FE HTTP {path} returned a non-JSON body")
    _raise_for_auth(body)
    evidence = {"code": body.get("code"), "msg": body.get("msg")}
    data = body.get("data")
    profile = data.get("profile") if isinstance(data, dict) else None
    if body.get("code") == 0 and isinstance(profile, str) and profile.strip():
        return profile, evidence
    return None, evidence


async def _profile_via_api_text(
    target: FeHttpTarget, qid: str, transport: httpx.AsyncBaseTransport | None
) -> tuple[str | None, dict[str, Any]]:
    resp = await _fe_get(target, _API_TEXT_PATH, params={"query_id": qid}, transport=transport)
    body = _json_body(resp)
    if body is None:
        text = resp.text
        if _SECTION_RE.match(text.lstrip().split("\n", 1)[0]):
            return text, {"code": 0, "msg": "text"}
        # e.g. "query id <id> not found" for unknown or evicted ids
        return None, {"code": None, "msg": text.strip()[:200] or "empty body"}
    _raise_for_auth(body)
    data = body.get("data")
    if body.get("code") == 0 and isinstance(data, str) and data.strip():
        return data, {"code": 0, "msg": body.get("msg")}
    # e.g. {"code": 500, "msg": "Invalid profile id"} for malformed ids
    return None, {"code": body.get("code"), "msg": body.get("msg")}


def _is_empty_counter(line: str) -> bool:
    """A counter line whose value is N/A or zero in every aggregate."""
    if line.rstrip().endswith(": N/A"):
        return True
    counter = _COUNTER_RE.match(line)
    value = counter.group(1).strip() if counter else ""
    return bool(value) and _ZERO_VALUE_RE.fullmatch(value) is not None


def summarize_profile(text: str) -> str:
    """Shrink a profile to what is needed to find the slow operator.

    Top-level sections start in column 0 (Summary:, Execution Summary:,
    ChangedSessionVariables:, MergedProfile:, DetailProfile(<id>):, Appendix:,
    PhysicalPlan:); their contents are indented. Omitted:
      * the per-instance DetailProfile section (header kept, one marker line);
      * counters that are N/A or zero in every aggregate;
      * the plan's per-column statistics ("<column>#<id> -> ndv=..."), one marker per run.
    """
    out: list[str] = []
    in_detail = False
    pending: list[Any] = []  # [indent, count, what, purpose] of the lines being omitted

    def flush() -> None:
        if pending:
            indent, count, what, purpose = pending
            out.append(f"{indent}[{count} {what} omitted; use mode='full' for {purpose}]")
            pending.clear()

    def omit(indent: str, what: str, purpose: str) -> None:
        if pending and pending[2] == what:
            pending[1] += 1
        else:
            flush()
            pending[:] = [indent, 1, what, purpose]

    for line in text.splitlines():
        section = _SECTION_RE.match(line)
        column_stats = _COLUMN_STATS_RE.match(line)
        if section:
            flush()
            in_detail = section.group(1) == "DetailProfile"
            out.append(line)
        elif in_detail:
            omit("  ", "lines", "per-instance detail")
        elif column_stats:
            omit(column_stats.group(1), "column-statistics lines", "column statistics")
        elif not _is_empty_counter(line):
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


async def get_query_profile(
    target: FeHttpTarget,
    query_id: str,
    mode: str = "summary",
    max_chars: int = 20000,
    *,
    scope: Scope = "all",
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Profile text of one query; a missing profile is evidence, not an error."""
    qid = (query_id or "").strip().lower()
    if not _QUERY_ID_RE.match(qid):
        return error_response(
            ErrorCode.INVALID_PARAMS,
            "query_id must be two hex parts joined by '-', as list_recent_queries returns it "
            "(e.g. 4f3c29918764dfc-b03a971ce0467326)",
        )
    if mode not in ("summary", "full"):
        return error_response(ErrorCode.INVALID_PARAMS, "mode must be 'summary' or 'full'")
    if not 1000 <= max_chars <= 200000:
        return error_response(ErrorCode.INVALID_PARAMS, "max_chars must be between 1000 and 200000")

    evidence: dict[str, Any] = {}
    try:
        text, evidence["v2"] = await _profile_via_v2(target, qid, transport)
        source = "v2"
        if text is None and scope == "all":
            text, evidence["api_text"] = await _profile_via_api_text(target, qid, transport)
            source = "api_text"
    except _FeError as e:
        return error_response(e.code, str(e))

    if text is None:
        return success_response(
            {"query_id": qid, "profile_found": False},
            {"hint": _NOT_FOUND_HINT, "evidence": evidence},
        )

    # The profile repeats the whole SQL (possibly over several lines); mask it like the list preview.
    text = mask_sensitive(text)
    shown = summarize_profile(text) if mode == "summary" else text
    truncated = len(shown) > max_chars
    if truncated:
        omitted = len(shown) - max_chars
        shown = shown[:max_chars]
    returned_chars = len(shown)
    if truncated:
        shown += f"\n[... truncated: {omitted} more chars; raise max_chars or narrow the question ...]"
    return success_response({
        "query_id": qid,
        "profile_found": True,
        "mode": mode,
        "source": source,
        "total_chars": len(text),
        "returned_chars": returned_chars,
        "truncated": truncated,
        "profile_text": shown,
    })


_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

_LIST_DESCRIPTION = (
    "List recently profiled Doris queries, newest first, with their query_id. Only queries "
    "run with profiling on appear: run the SQL through execute_query as "
    "`SELECT /*+SET_VAR(enable_profile=true)*/ ... /* trace:<random token> */`, then call "
    "this tool with sql_contains='<random token>' to get its query_id. Filters: user (exact "
    "Doris user name), sql_contains (case-insensitive substring of the SQL). limit: 1-100."
)
_GET_DESCRIPTION = (
    "Fetch the runtime profile of one Doris query by query_id (from list_recent_queries). "
    "mode='summary' (default) drops the per-instance DetailProfile section, N/A and all-zero "
    "counters and per-column plan statistics, which is usually enough to find the slow "
    "operator; mode='full' returns everything. "
    "Output is capped at max_chars (1000-200000, default 20000) and marked when truncated. "
    "profile_found=false means no profile exists for that id (not run with enable_profile, or evicted)."
)


def register_profile_tools(
    mcp: Any,
    target: FeHttpTarget,
    scope: Scope = "all",
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Register list_recent_queries and get_query_profile on a FastMCP server."""

    def audit(tool: str, params: dict[str, Any], result: str, start: float) -> None:
        err = json.loads(result).get("error") or {}
        log_tool_call(
            tool,
            params=params,
            success=not err,
            duration_ms=(time.monotonic() - start) * 1000,
            error=err.get("message"),
        )

    async def list_recent_queries_tool(limit: int = 20, user: str = "", sql_contains: str = "") -> str:
        start = time.monotonic()
        result = await list_recent_queries(
            target, limit, user, sql_contains, scope=scope, transport=transport
        )
        audit("list_recent_queries", {"limit": limit, "user": user, "sql_contains": sql_contains[:100]}, result, start)
        return result

    async def get_query_profile_tool(
        query_id: str, mode: Literal["summary", "full"] = "summary", max_chars: int = 20000
    ) -> str:
        start = time.monotonic()
        result = await get_query_profile(
            target, query_id, mode, max_chars, scope=scope, transport=transport
        )
        audit("get_query_profile", {"query_id": query_id[:64], "mode": mode, "max_chars": max_chars}, result, start)
        return result

    mcp.tool(list_recent_queries_tool, name="list_recent_queries", description=_LIST_DESCRIPTION, annotations=_READ_ONLY)
    mcp.tool(get_query_profile_tool, name="get_query_profile", description=_GET_DESCRIPTION, annotations=_READ_ONLY)
