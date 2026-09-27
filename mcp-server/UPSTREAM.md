# Upstream

- Repository: https://github.com/velodb/velodb-mcp-server
- Commit: `f235832da69f30194574defa370fa793aa14a340` (tag `velodb-mcp-server-0.3.0`, 2026-08-31; its pyproject still says 0.2.6)
- Vendored with `git archive f235832 src test LICENSE.txt NOTICE mcp-server.toml requirements.txt`,
  committed unmodified first. Each patch below is a separate commit on top.
- License: Apache License 2.0 (`LICENSE.txt`, `NOTICE`).

## AgentCore patches (specs/doris-mcp-quick/design.md §5.2)

| # | Files | Change |
|---|---|---|
| P-01 | `mcp_server.py`, `src/agentcore_ext/` (new) | AgentCore entrypoint: settings from env / Secrets Manager, `build_server`, `GET /ping`, stderr logging, `main` |
| P-02 | `src/config/loader.py` | `ClusterConfig.fe_http_port` |
| P-03 | `src/store/store.py`, `src/store/bootstrap.py` | process-wide service credentials as a fallback for the store layer |
| P-04 | `src/server.py` | `create_server(service_credentials=, workspace_dir=)`: no MCP auth, one service-account pool |
| P-05 | `src/tools/profile.py` (new) | `list_recent_queries`, `get_query_profile` |
| P-06 | `config/mcp-server.toml` (new) | runtime limits (50 s SQL timeout, pool 5, 2000 rows) |
| P-07 | `pyproject.toml` (new) | dependencies pinned to upstream `uv.lock` + boto3, for AgentCore CodeZip |
| P-08 | `test/test_agentcore_*.py` (new) | tests for P-01..P-06 |
| P-09 | `src/config/loader.py`, `src/core/connection.py`, `config/mcp-server.toml`, `test/test_agentcore_session_timeout.py` (new) | `SET wait_timeout` on every pool connection (`session_wait_timeout_seconds = 600`), so Doris reaps what a torn-down Runtime microVM left open |

Only P-02, P-03, P-04 and P-09 touch upstream files; without service credentials and without
`session_wait_timeout_seconds` they behave exactly like upstream.

## Upgrading upstream

1. `git archive <new-commit> src test LICENSE.txt NOTICE mcp-server.toml requirements.txt` into a scratch dir and diff it against the vendored commit.
2. Replace the vendored files, then re-apply P-02/P-03/P-04/P-09 (`git log --oneline -- mcp-server/src` lists their commits).
3. Update the pins in `pyproject.toml` from the new `uv.lock`, then run the upstream offline suite and `test_agentcore_*.py`.
