# Demo runbook: Doris MCP × Amazon Quick desktop

> This file contains no URL, secret or token. The connection parameters are in `quick/T0.7-guide.md`; get secrets only in your own terminal, not with Claude Code's `!` prefix.
> The questions and reference values come from design §10 and Part B of `quick/P5-guide.en.md`; "Time per step" comes from the two rehearsals (T5.4).
> Chinese version: `quick/runbook.md`

## Before the demo

1. Within the 30 minutes before the demo, run the pre-check from the repository root on the dev box (read-only, about 1.5 minutes):

   ```
   bash scripts/demo-check.sh pre
   ```

   One `[PASS]` / `[FAIL]` line per check; the last line is `demo-check pre: N/M passed`; with any `[FAIL]` the exit code is 1. What it checks: the AWS account; the Gateway and the target are READY; a Gateway token can be obtained; 12 tools are listed through the Gateway; one run of the profile flow through the Gateway (run a query with profile → find the query_id by the trace → read the profile) and 3 error cases (an invalid query_id, a query_id that does not exist, a `DELETE` that is rejected); reconciliation (the numbers of the semantic layer match hand-written SQL); the permissions of `mcp_svc`; the connection count of `mcp_svc` (at most 80).
   If only one check is `[FAIL]`, re-run once first: in the spec phase, 2 of 3 consecutive pre-checks each had 1 intermittent failure (the Runtime returned 502, or a cold start was so slow that the Gateway reported an error), and a re-run passed. If the same check is `[FAIL]` twice in a row, see "If something goes wrong" first and do not start the demo.
2. Note the time the pre-check ended (`date +%s%3N`, in milliseconds); you need it after the demo. Do not run any other script between the pre-check and the demo, so that the audit log holds only the demo's calls.
3. Quick desktop:
   - Signed in; the instructions of 「Doris 专家」 (Doris expert) are the full text of `quick/agent-instructions.md`, it has the 5 skills attached (`doris-mcp-adapter`, `doris-debug`, `doris-profile-reader`, `doris-best-practices`, `doris-architecture-advisor`) and it is linked only to `Doris-Desktop-MCP`.
   - `Doris-Desktop-MCP` has 12 `doris___` tools, with the permissions of "Setup".
   - Start a new conversation; do not ask anything yet.
4. Data: act 1 (Stream Load real-time writes) and creating the MV in act 7 are write operations; the presenter runs them by hand outside Quick, and Quick only reads the results. The reference values in `quick/P5-guide.en.md` are the numbers after the orders of the morning of 09-25 were loaded; if the database is dropped and rebuilt, September (act 2) loses that day's orders and the reference values have to be computed again.

## Setup

- Tool permissions (D7): for the rehearsals and the demo, `doris___execute_query` is Always Allow (no pop-up, which saves a confirmation each time), `doris___reload_semantic_layer` is Ask Each Time (always deny its pop-up), and the other 10 tools are Always Allow. The full table is in A3 of `quick/P5-guide.en.md`. At other times, set `doris___execute_query` back to Ask Each Time (see "After the demo").
- Connector: `Doris-Desktop-MCP` (User auth, the `demo` user). The desktop version cannot refresh the tool list of an existing connector: if the tool count is not 12, or tool calls return HTTP 400 「参数无效」 (invalid parameters), create a new connector in the **web version** (parameters in `quick/T0.7-guide.md`), then in the desktop version link the agent to the new connector.
- Skills: import them folder by folder from `quick/skills/` in the repository (`doris-debug` as a whole folder at once); do not import `LICENSE.txt`, `CLI-CONTRACT.md` and `UPSTREAM.md`. A changed skill has to be imported again.
- Instructions: the full text of `quick/agent-instructions.md`.
- Backup: 「Doris 专家（svc）」 linked to `doris-mcp-svc` (Service auth, no sign-in needed). The old connector in the desktop version cannot refresh its tool list, so the backup is used in the **web version**.

## Demo flow

Ask each question only when the previous answer is fully shown; copy the questions exactly. "Expected" assumes 5–10 s per tool call; the rehearsal measurements are in "Time per step".

- The questions can be asked in English or in Chinese; the agent answers in the language of the question.
- The data values stay Chinese in the answers, usually with an English gloss, e.g. 家用电器 (Home appliances). 618 is the mid-year shopping festival around June 18; Double 11 (双 11, Singles' Day) is around November 11.

| Step | Part | Question | Chinese original | What to show / say | Expected |
|---|---|---|---|---|---|
| — | Act 1 | (the presenter does the Stream Load real-time writes outside Quick, not through MCP) | — | writes = by hand, reads = MCP | — |
| 1 | Opening | `Check the Doris connection status` | `检查一下 Doris 连接状态` | connection fine, version 4.1; no host address or account in the answer | 10–20 s |
| 2 | Act 2 business overview | `This year's monthly GMV, order count and average order value: how do they compare with the same period last year? And by channel, what is the mini program's share?` | `今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比` | semantic layer (`list_metrics` → `query_metric`); calling `get_query_guide` / `list_dimensions_for_metric` first is normal (P4 review M-3); September only runs to September 25, so compare the YoY on the same days (+21.87%); mini program share 32.30% | 40–90 s |
| 3 | Act 3 promotion review | `Which category contributed the most during the 618 and Double 11 promotions?` | `618 和双 11 哪个类目贡献最大？` | 618: 家用电器 (Home appliances) first (30.52%); Double 11: 手机数码 (Phones & digital) first (26.04%); the promotion dates come from `dim_promotion` | 40–90 s |
| 4 | Act 5 troubleshooting | `Which shop has had an abnormal refund rate recently? What is the cause? Is there a logistics problem?` | `最近哪家店的退款率异常？原因是什么？物流有没有问题？` | 深圳极速数码配件专营店 (Shenzhen Jisu Digital Accessories Store); bad reviews 「发烫」 (overheating) and 「充不进电」 (won't charge) (inverted index, TOKENIZE, MATCH_PHRASE); 极兔 (J&T Express) is slow on the trunk leg of shipments to the northwest (PERCENTILE) | 1–3 min |
| 5 | Act 7 + Track A | `Why does the query that counts daily UV of the tracking events take so long? Give the profile evidence` | `按天统计埋点 UV 这个查询为什么要这么久？给出 profile 证据` | adapter + profile-reader; run with profile → find the query_id by the trace → read the profile; only tens of milliseconds in Doris, the time goes into the tool calls | 1–2 min |
| — | Act 7 | (the presenter creates the MV outside Quick, not through MCP) | — | writes = by hand | — |
| 6 | Track B design review | `Review the table design of fact_user_event: are the VARIANT column, partitioning and bucketing reasonable? Give improved DDL` | `评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL` | best-practices; 135 daily partitions and BUCKETS 2, 270 small tablets in total; the DDL is only proposed, not run | 1–2 min |
| 7 | Closing | `Recommend a data model for scenarios like agg_daily_traffic` | `为 agg_daily_traffic 这类场景推荐数据模型` | architecture-advisor; aggregate model + BITMAP_UNION / HLL_UNION; the DDL is run by a person | 40–90 s |

## If something goes wrong

- **A 424 or a tool error**: Quick limits how long it waits for a single tool call (about 60 s). Ask the agent to narrow the scope (add a time range, `LIMIT`, `EXPLAIN` first) and resend once; if that still fails, skip the step and present the reference values in Part B of `quick/P5-guide.en.md`.
- **A Doris host address or IP in an answer** (e.g. the verbatim text of a 2003 connection error): do not read it out; if you are recording, cut that part. Tell the AI after the demo; it is handled as in design §14.
- **A permission pop-up for `doris___reload_semantic_layer`**: deny it and let the agent go on answering without reloading.
- **The agent asks you to run `doriscli`, a mysql client or curl**: reply `There is no command line here. Use only the Doris MCP tools, following the doris-mcp-adapter mapping table` (in Chinese: 「这里没有命令行，只能用 Doris MCP 工具，按 doris-mcp-adapter 的对照表来」).
- **The shares of step 3 do not match the reference values** (e.g. 618: 家用电器 (Home appliances) 31.45%; Double 11: 手机数码 (Phones & digital) 27.94%): the agent used dates it estimated itself (June 1–18, November 1–11), not the promotion periods in `dim_promotion`. If 家用电器 is first at 618 and 手机数码 at Double 11, present as usual. To match the reference values, or if it computed the 618 of 2025 (手机数码 first), reply `Recompute with the start and end dates of 2026年618 and 2025年双11 in ecom.dim_promotion` (in Chinese: 「按 ecom.dim_promotion 里 2026年618 和 2025年双11 的起止日期重算」).
- **In step 5 the agent asks you for the SQL or the query_id of the slow query**: reply `Write your own query that counts daily UV on ecom.fact_user_event and run it with profile` (in Chinese: 「你自己写一条按天统计 ecom.fact_user_event UV 的查询，带 profile 执行」).
- **The agent wants to run a write operation (DDL, `KILL`, `SET`)**: the tool rejects it; have it write out the statement and say that a person runs it.
- **The connector fails, asks you to sign in again, or the tool count is wrong**: first switch to the backup 「Doris 专家（svc）」 (web version); after the demo, create a new connector as in "Setup".
- **You suspect a backend problem**: re-run `bash scripts/demo-check.sh pre` on the dev box and see which check is `[FAIL]`.

## After the demo

1. Note the time the demo ended (`date +%s%3N`) and run this on the dev box (read-only):

   ```
   bash scripts/demo-check.sh post --since <pre-check end in ms> --until <demo end in ms>
   ```

   Output: for this period, the number of calls of each tool in the audit log and how many succeeded or failed, then each failed call (time, tool, cause of the error; for `query_metric` also its `group_by` / `where` / `having`). The tool names in the audit log have no `doris___` prefix; that is normal (P4 review M-7). Then the Gateway's calls and latency per minute and per tool (≥ 45 s is marked WARN, ≥ 60 s counts as a failure), and the current connection count of `mcp_svc`.
2. In Quick, set `doris___execute_query` back to Ask Each Time (D7).
3. When all the demos are over and the environment is no longer needed (T5.6):
   - AWS side: dry-run first and look closely at the resources it would delete:

     ```
     bash infra/99-cleanup.sh
     ```

     Only after confirmation (GATE; one confirmation covers only this one run) run `APPLY=1 bash infra/99-cleanup.sh`. In order, it deletes the Gateway target, the Gateway, the Runtime's stack, the Interface endpoints (billed continuously), Cognito, the secret, the rules on the Doris SG that reference the Runtime SG, this project's SGs and the two IAM roles; `infra/state.env` is kept as the record of what was deleted. It does not delete the CDK bootstrap stack `CDKToolkit` or its S3 bucket: they existed before this project (the agentcore deploy only uploaded its assets to the bucket) and other CDK projects in the same account and region may use them, so they are kept. The CodeZip and the other assets the deploy uploaded also stay in that bucket.
   - Doris side (optional, confirmed separately): the `mcp_svc` account and the semantic layer's database `system_mcp` are not deleted by `99-cleanup.sh`. If there will be no more demos, you run the two statements below as root in your own mysql client (the AI does not run them):

     ```
     DROP USER IF EXISTS 'mcp_svc'@'172.31.%';
     DROP DATABASE IF EXISTS system_mcp;
     ```

     The data of `ecom` and the `demo_ro` account are not affected. To demo again later, P2 (publish the semantic layer) and P3 (create the account) have to be done again.
   - Quick side: you delete the connector, the agents and the skills in Quick (optional).

## Time per step

Measured in rehearsal (T5.4), in seconds. Round 1 (in English) did not note when each question was sent and answered, so "Round 1" is the time the step's tool calls took, worked out from the audit (from the first call sent to the last call returned); the thinking before the first call and writing the answer after the last one are not in it, so allow extra time for them at the demo. Round 2 was skipped, as the user decided. "Tool calls" is the number of calls the Gateway recorded for the step, and "Longest call" the slowest of them; step 7 had 1 more call 2 minutes later (probably a follow-up question), which is not counted.

| Step | Part | Round 1 | Round 2 | Tool calls | Longest call |
|---|---|---|---|---|---|
| 1 | Opening | 6 | skipped | 1 | 5.7 |
| 2 | Act 2 | 37 | skipped | 6 | 7.5 |
| 3 | Act 3 | 76 | skipped | 8 | 9.3 |
| 4 | Act 5 | 115 | skipped | 16 | 8.9 |
| 5 | Act 7 + Track A | 30 | skipped | 7 | 7.3 |
| 6 | Track B | 67 | skipped | 11 | 7.3 |
| 7 | Closing | 32 | skipped | 7 | 6.7 |
