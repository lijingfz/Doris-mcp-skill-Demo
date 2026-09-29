---
name: doris-mcp-adapter
description: >
  Read this before following any doris-* skill (doris-debug, doris-profile-reader, doris-best-practices,
  doris-architecture-advisor) in this environment. There is no doriscli, no mysql client, no shell and no FE/BE
  HTTP access here: the only way to reach Doris is the Doris MCP tools (doris___*). This skill maps every doriscli
  command, session setting, SQL statement and HTTP call those skills mention to the MCP tools, and states the
  read-only boundary, the 60-second limit per call and how to run a query with a profile.
---

# Doris MCP adapter

The doris-* skills were written for `doriscli`, a Doris command-line client that is not available here. Here the
agent talks to one Apache Doris 4.1 cluster through MCP tools only. Follow the diagnostic reasoning of the doris-* skills
as written; translate every command they tell you to run with the tables below.

## The environment

- Tools are named `doris___<tool>` (the `doris___` prefix comes from the gateway). There is nothing else: no
  `doriscli`, no `mysql`, no `curl`, no shell, no FE/BE web UI, no log files, no BE HTTP (`/api/compaction/...`,
  `/metrics`, `be.conf`).
- Every tool call takes 5-10 s (each call starts a fresh server) and is cut off at 60 s. Plan the evidence you
  need, avoid calls you do not need, and put several metrics into one `doris___query_metric` call.
- The service account is read-only: SELECT, SHOW, DESCRIBE and EXPLAIN only. Writes are never executed (see
  "Writes and admin actions").
- A "fallback", "mysql client" or "native SQL" path in a skill means `doris___execute_query` here.

## Tools

| Tool | Use |
|---|---|
| `doris___check_service_health()` | connectivity (`SELECT 1`) and semantic-layer status, not the Doris version (`doriscli auth status`) |
| `doris___list_databases()` / `doris___list_tables(database)` / `doris___describe_table(database, table)` | catalogue |
| `doris___execute_query(sql, database="", max_rows=0)` | any read-only statement (SELECT, SHOW, DESCRIBE, EXPLAIN) |
| `doris___list_recent_queries(limit=20, user="", sql_contains="")` | profiled queries, newest first, with `query_id` |
| `doris___get_query_profile(query_id, mode="summary", max_chars=20000)` | profile text of one query |
| `doris___get_query_guide()` | the server's own SQL guide |
| `doris___list_metrics` / `doris___list_dimensions_for_metric` / `doris___query_metric` | the `ecom` semantic layer (business metrics, not diagnostics) |
| `doris___reload_semantic_layer` | do not call unless the user asks |

## doriscli command map

| The skill says | Do this |
|---|---|
| `doriscli sql "<SELECT / SHOW / DESC / EXPLAIN>"` | `doris___execute_query(sql=...)`; for big results use `LIMIT` or an aggregate (`max_rows` only trims the rows returned; Doris still runs the whole query) |
| `doriscli sql ... --profile` | run with a profile (next section) |
| `doriscli sql ... --set k=v`, or a `SET k = v;` line before the query | put the variable into the query as a hint: `SELECT /*+SET_VAR(k=v)*/ ...` (`SET` statements are rejected) |
| `doriscli sql ... --no-cache` | add the hint `/*+SET_VAR(enable_sql_cache=false)*/` |
| `doriscli sql -f file.sql` | run the statements one by one with `doris___execute_query` |
| `doriscli profile get <qid>` | `doris___get_query_profile(query_id=qid)`; the text is in `profile_text` |
| `doriscli profile get <qid> --full` / `--raw` | `doris___get_query_profile(query_id=qid, mode="full", max_chars=100000)` |
| `doriscli profile get -f file` | the user gave the profile: read the text they pasted; no tool call |
| `doriscli profile list` (`--limit N`) | `doris___list_recent_queries(limit=N)` (default 20; only queries that were run with a profile) |
| `doriscli profile list --active` | `doris___execute_query(sql="SHOW PROCESSLIST")` |
| `doriscli profile diff <slow> <fast>` | call `doris___get_query_profile` for each id and compare the two texts yourself |
| `doriscli profile history "<pattern>"` (`--days N`, `--limit N`) | `doris___list_recent_queries(sql_contains="<pattern>", limit=100)`; there is no date filter, only profiled queries are listed and the audit log is not available, so there is no p50/p99 trend: say so |
| `doriscli tablet <db.t>` | `SHOW CREATE TABLE db.t` (model, keys, buckets, properties) + `SHOW PARTITIONS FROM db.t` + `SHOW DATA SKEW FROM db.t` + `SHOW TABLE STATS db.t` / `SHOW COLUMN STATS db.t` |
| `doriscli tablet <db.t> --detail` / `--partition p` | the same statements; for one partition `SHOW DATA SKEW FROM db.t PARTITION (p)` |
| `doriscli auth status` | `doris___check_service_health()` (connectivity only); for the version `doris___execute_query(sql="SHOW VARIABLES LIKE 'version_comment'")`; backend state is not shown |
| `doriscli use <env>`, `auth add`, `--env`, `--socks5`, `--init-sql` | not needed: there is exactly one cluster |
| `--format json` | not needed: every tool returns JSON |
| FE HTTP `/rest/v2/manager/query/query_info` | `doris___list_recent_queries` |
| FE HTTP `/rest/v2/manager/query/profile/text/<qid>` | `doris___get_query_profile(query_id=qid)` |
| FE HTTP `/api/query_profile?query_id=<qid>` | `doris___get_query_profile(query_id=qid)` |
| FE HTTP `/api/health`, `/api/bootstrap` | `doris___check_service_health()`: it only shows that the FE answers SQL; there are no backend counts and no bootstrap (FE ready) state. If the skill needs those, ask the human |
| FE HTTP `/api/tablets_distribution?db=...&table=...` | `SHOW DATA SKEW FROM db.t` (rows and data size per partition and bucket); the distribution per backend is not available |
| any other FE / BE HTTP call | not available: ask the human (see "Writes and admin actions") |

`doriscli profile get` returns parsed JSON fields (`summary.total_time_ms`, `operators[]`, `scanned_tables`, ...).
Here you get the profile text instead. Read the same facts from it: `Summary:` (`Total`, `Task State`),
`Execution Summary:` (plan and schedule times), `ChangedSessionVariables:`, `MergedProfile:` (per-operator
counters: rows, time, memory, spill, runtime filters), `Appendix:` → `PhysicalPlan:`. For the table-side fields
(`ddl`, `tablet_skew`, `total_rows`) use the SQL of the `doriscli tablet` row above.

## Run a query with a profile

Profiles are off by default. To profile one query:

1. Make a random token, e.g. `t7q2x9`.
2. `doris___execute_query(sql="SELECT /*+SET_VAR(enable_profile=true)*/ ... /* trace:t7q2x9 */")` - the hint goes
   right after `SELECT`, the comment at the end. If the query may be slow or return many rows, run `EXPLAIN` first
   and add `LIMIT` or aggregate (see "The 60-second limit").
3. `doris___list_recent_queries(sql_contains="t7q2x9", limit=5)` → take `query_id` of the newest row. If no row
   matches (the profile is not collected yet, or the hint was not honoured), call it once more; if there is still
   no row, say that the profile could not be collected and go on without it (do not loop).
4. `doris___get_query_profile(query_id=...)`. If the result says `truncated: true`, call it again with
   `max_chars=60000`; use `mode="full"` only when the skill needs per-instance detail (e.g. skew between
   instances), because the full text is much longer.

`profile_found: false` means the query ran without a profile or the profile was evicted: re-run step 2. When the
user gives a query_id, skip steps 1-3. Prefer an existing profile over re-running an expensive query.

## SQL that works and SQL that does not

Checked on this cluster through the MCP tools:

- Works: `SHOW CREATE TABLE`, `SHOW PARTITIONS`, `SHOW DATA SKEW`, `SHOW TABLE STATS`, `SHOW COLUMN STATS`,
  `SHOW INDEX`, `SHOW PROCESSLIST`, `SHOW VARIABLES`, `SHOW ALTER TABLE MATERIALIZED VIEW`, `EXPLAIN`,
  `DESCRIBE`, and `SELECT` on the databases the account can read.
- `SHOW PROCESSLIST` (what `doriscli profile list --active` becomes) lists only the service account's own sessions:
  queries that other users run do not appear, so an empty or short list is not evidence that nothing is running.
  To look at someone else's running or slow query, ask the user for its SQL or its query_id.
- Rejected by the tool: `SET ...` (use the `SET_VAR` hint) and every write or DDL statement.
- Denied by Doris (they come back as an error, often reported as `CONNECTION_ERROR` with Doris error 1105):
  `SHOW TABLETS`, `SHOW PROC ...`. The replica state and version counts of single tablets, and the `SHOW PROC`
  views (tablet health, tasks, disk usage), therefore cannot be collected here: say so, do not infer them.
- Anything else a skill asks for (other `SHOW` / `ADMIN SHOW` statements, `information_schema` tables): try it
  once. If it is denied, do not retry variants; say which evidence could not be collected, and continue with what
  you have or give the statement to the human (next section).

## Writes and admin actions

Never run `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `KILL`, `ADMIN SET/REPAIR ...`,
`SET GLOBAL`, `REFRESH MATERIALIZED VIEW`, config changes, restarts or BE/FE HTTP actions. When a skill's fix needs
one, write the exact statement (DDL, `ALTER`, `KILL`, config line) with the reason and the expected effect, and
say that a person runs it. Evidence a person must collect outside this environment (BE logs, `be.conf`, BE HTTP
pages, `SHOW PROC` output) is a request to the human, not something to guess.

## The 60-second limit

- For detail or large-table queries run `EXPLAIN` first; then add a `LIMIT`, a partition / time filter or an
  aggregate.
- A tool error or a Quick timeout (424) after about 60 s means the query was too big: narrow it and retry once;
  if it fails again, tell the user.
- Timing talking point: Doris itself usually answers in milliseconds (the profile's `Total`); most of the 5-10 s
  per call is starting the server. Quote the profile time, not the wall-clock time, as the query cost.

## Evidence first

Every root cause, number or recommendation must come from a tool result of this conversation (or from data the
user gave). Follow the evidence gates of the doris-* skills: collect first, then state hypotheses with the evidence
and confidence. At the end, list the tools and statements you used. Do not repeat host names, IP addresses, ports,
accounts or URLs that appear in tool results.
