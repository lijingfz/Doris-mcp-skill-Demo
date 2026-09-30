# Upstream

- Repository: https://github.com/velodb/velodb-mcp-server
- Commit: `f235832da69f30194574defa370fa793aa14a340` (tag `velodb-mcp-server-0.3.0`, 2026-08-31; its pyproject still says 0.2.6)
- Vendored with `git archive f235832 src test LICENSE.txt NOTICE mcp-server.toml requirements.txt`,
  committed unmodified first. The patches below are committed on top, mostly one commit per patch (a few share a
  commit; `git log --oneline -- mcp-server` lists them).
- License: Apache License 2.0 (`LICENSE.txt`, `NOTICE`).

## AgentCore patches (specs/doris-mcp-quick/design.md §5.2)

| # | Files | Change |
|---|---|---|
| P-01 | `mcp_server.py`, `src/agentcore_ext/` (new) | AgentCore entrypoint: settings from env / Secrets Manager, `build_server`, `GET /ping`, stderr logging, `main` |
| P-02 | `src/config/loader.py` | `ClusterConfig.fe_http_port` |
| P-03 | `src/store/store.py`, `src/store/bootstrap.py` | process-wide service credentials as a fallback for the store layer |
| P-04 | `src/server.py` | `create_server(service_credentials=, workspace_dir=)`: no MCP auth, one service-account pool |
| P-05 | `src/tools/profile.py` (new) | `list_recent_queries`, `get_query_profile`; P5 fix `78d653f` (Runtime version 4): `get_query_profile` accepts query_id halves of 1-16 hex digits (`_QUERY_ID_RE`), as Doris prints them unpadded |
| P-06 | `config/mcp-server.toml` (new) | runtime limits (50 s SQL timeout, pool 5, 2000 rows) |
| P-07 | `pyproject.toml` (new) | dependencies pinned to upstream `uv.lock` + boto3 (+ 5 transitive pins that keep the CodeZip equal to the tested `.venv`), for AgentCore CodeZip |
| P-08 | `test/test_agentcore_*.py` (new) | tests for P-01..P-06, P-10 (`test_agentcore_audit_errors.py`) and P-11 (`test_agentcore_time_constraints.py`) |
| P-09 | `src/config/loader.py`, `src/core/connection.py`, `config/mcp-server.toml`, `test/test_agentcore_session_timeout.py` (new) | `SET wait_timeout` on every pool connection (`session_wait_timeout_seconds = 600`), so Doris reaps what a torn-down Runtime microVM left open |
| P-10 | `src/server.py` | the audit record of a failed `execute_query` / `query_metric` carries `error` (`CODE: message`, 300 chars, masked); `query_metric` takes success from the parsed result, logs the resolved `where` plus `having`, `order_by`, `limit`, and its `mf_command` gains `--where`/`--order-by`/`--limit`/`--having` (values masked before quoting) |
| P-11 | `src/store/compiler.py`, `../doris/test/test_semantic_time.py` (new) | `_extract_time_constraints`: an OR around a metric_time condition raises `ValueError` (returned as the compile error) instead of compiling to `WHERE () OR ()`, and so does a NOT before a metric_time condition or its enclosing group; a bare `metric_time` must be a whole word; strict `>` / `<` shift the bound by 1 day (1 s with a time part); only `TimeDimension('metric_time', ...)` is extracted; several conditions intersect; a parenthesized range leaves no `( AND )` behind |

Only P-02, P-03, P-04, P-09, P-10 and P-11 touch upstream files; without service credentials and without
`session_wait_timeout_seconds`, P-02/P-03/P-04/P-09 behave exactly like upstream. P-10 and P-11 change upstream
behaviour on purpose (audit content, metric_time filters).

NOT around a metric_time condition (`NOT metric_time < 'x'`, `NOT (metric_time BETWEEN … ) AND …`, or a NOT
before any parenthesized group that contains one) is rejected by P-11 with a `ValueError`, returned as the compile
error like the OR case: the time range cannot be negated. Upstream extracted the condition anyway and left the
`NOT` bare or on the next filter.

## Upgrading upstream

1. `git archive <new-commit> src test LICENSE.txt NOTICE mcp-server.toml requirements.txt` into a scratch dir and diff it against the vendored commit.
2. Replace the vendored files, then re-apply P-02/P-03/P-04/P-09/P-10/P-11 (`git log --oneline -- mcp-server/src` lists their commits).
3. Update the pins in `pyproject.toml` from the new `uv.lock`, then run the upstream offline suite and `test_agentcore_*.py`.
