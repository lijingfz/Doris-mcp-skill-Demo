# P5: Import the skills + two full rehearsals (T5.3 + T5.4)

> This file contains no URL, secret or token. The connection parameters (MCP URL, Token URL, Authorize URL, client ID) are in 「连接参数」 (Connection parameters) of `quick/T0.7-guide.md`. If Quick asks you to sign in again, or to enter the client secret / the password of the `demo` user again, get them in **your own terminal** as described in 「Step 2：取 secret」 (Step 2: get the secret) of T0.7; do not use Claude Code's `!` prefix.
> Chinese version: `quick/P5-guide.md`

## Important

- Do not paste any URL, secret, token or sign-in page address into the conversation.
- Permissions follow D7: during the rehearsals `doris___execute_query` is Always Allow (no pop-up) and `doris___reload_semantic_layer` is Ask Each Time; always deny its pop-up. After the rehearsals, switch back as described in "After the demo" of `quick/runbook.en.md`.
- Write operations the agent proposes (DDL, `ALTER`, `INSERT`, `KILL`, configuration changes): **never run them**; copy them into the reply template. The rehearsals skip act 1 (Stream Load) and creating the MV in act 7: the orders of the morning of 09-25 are already in the database, so leave the cluster as it is and **do not drop and rebuild the database**.
- On a 424, an error or an unexpected pop-up: note the time, the tool name and the error message verbatim (remove any address from it first), then carry on. Resend the same question at most once.
- Before each round, say 「开始第 N 轮」 (or "start round N") in the conversation and wait for the AI to reply 「可以开始」 (ready to start): the AI first runs `demo-check pre` (about 1.5 minutes) and notes the start time. From then until you send back your reply for the round, the AI makes no calls to the Gateway or the Runtime, so the audit log and the timings contain only your calls.
- Between the two rounds, only problems that block get fixed (no answer, a tool error, an answer that does not match the reference values); note wording and formatting problems for T5.5 to handle together.
- Expected time: Part A 30–40 minutes; each round 30–45 minutes (7 questions; each tool call takes 5–10 s, act 5 and Track A need 5–12 calls each).

## Preparation

- A stopwatch (a phone will do) and a notepad; note the time zone of this computer (the first line of the reply template); the AI matches the logs in UTC.
- Quick desktop is signed in. The agent 「Doris 专家」 (Doris expert) is linked only to `Doris-Desktop-MCP` (the connector P4 created in the web version; in the desktop version the old `doris-mcp` cannot refresh its tool list).
- Copy the skills to this computer. Run this in **your own terminal** (replace `<dev box>` with the host name or alias you normally use to SSH into the dev box):

```
scp -r <dev box>:/home/ubuntu/AI-code/Doris-mcp-skill-Demo/quick/skills ./doris-skills
```

- After the copy, `doris-skills` holds 5 folders and 3 files (`LICENSE.txt`, `CLI-CONTRACT.md`, `UPSTREAM.md`). Import only the 5 folders, not the 3 files: `UPSTREAM.md` records which commit of apache/doris-skills these copies come from and what was changed, and `LICENSE.txt` is its license.

## Part A: Import the skills (T5.3)

### A1 Import the 5 skills

**Customize → Skills → From folder**: import them one by one in the order of the table, one folder each time (each is under 1 MB; Quick's limit is 6 MB):

| Order | Folder | Purpose |
|---|---|---|
| 1 | `doris-mcp-adapter` | Written for this project: maps the doriscli commands in the doris-* skills to the `doris___*` tools; the read-only boundary; the 60 s limit per call |
| 2 | `doris-debug` | Troubleshooting (slow queries, loading, Compaction, cluster problems, etc.). **Import the whole folder at once**: its subfolders (`query`, `import`, `data-lake`, etc.) come along with it as reference files; do not import them separately |
| 3 | `doris-profile-reader` | Reading a Query Profile |
| 4 | `doris-best-practices` | Best practices for table design, partitioning and bucketing, and data models; DDL review |
| 5 | `doris-architecture-advisor` | Recommends an architecture and data model for a business scenario |

- For each import, note success or failure; on failure, note the error message verbatim. The skill names Quick shows should match the folder names.
- If Quick also shows the subfolders of `doris-debug` as separate skills (with names like `doris-debug-query`), note it; nothing to fix.

### A2 Update the agent

1. Open the edit page of the agent 「Doris 专家」.
2. Instructions: delete the old text and paste the new full text of `quick/agent-instructions.md` from the repository (about 2900 characters; you can `cat quick/agent-instructions.md` in your own terminal and copy it; the file holds no secret). Compared with P4, the new version adds: diagnosis questions load doris-mcp-adapter first; the time grains available; how to compare 「同期同天数」 (the same days of the same period); do not join several time ranges with OR; filter time only on metric_time (not on order_date); answer in the language of the question (a Chinese question gets a Chinese answer, an English question an English one). If Quick says the instructions are too long, note its message verbatim.
3. Skills: attach the 5 skills of A1. If the agent's edit page has no place to pick skills (skills apply to every agent), note "skills are global".
4. Connector: linked only to `Doris-Desktop-MCP`, unchanged.
5. The backup agent 「Doris 专家（svc）」 (linked to `doris-mcp-svc`): replace its instructions the same way and attach the skills. Also check how many `doris___` tools `doris-mcp-svc` shows in the desktop version and note the number; no need to fix it if it is not 12 (in P4 the old connector could not refresh in the desktop version, so the backup runs in the web version).

### A3 Tool permissions (D7: the settings for the rehearsals and the demo)

Open `Doris-Desktop-MCP`, check that all 12 `doris___` tools are enabled, and set the permissions as in the table (compared with P4, `doris___execute_query` is now Always Allow):

| Tool | Permission |
|---|---|
| `doris___get_query_guide` | Always Allow |
| `doris___check_service_health` | Always Allow |
| `doris___list_databases` | Always Allow |
| `doris___list_tables` | Always Allow |
| `doris___describe_table` | Always Allow |
| `doris___execute_query` | Always Allow |
| `doris___list_metrics` | Always Allow |
| `doris___list_dimensions_for_metric` | Always Allow |
| `doris___query_metric` | Always Allow |
| `doris___reload_semantic_layer` | Ask Each Time |
| `doris___list_recent_queries` | Always Allow |
| `doris___get_query_profile` | Always Allow |

If `doris-mcp-svc` also has 12 tools in the desktop version, set them from the same table.

### A4 scope (P0 review M-1, case c)

Only when Quick asks you to sign in (a sign-in page pops up when you import the skills, edit the agent or ask the first question): **do not sign in yet**; as in A2 of `quick/P4-guide.md`, read only three things from the address bar: the value of `scope=` (`%20` and `+` are both spaces, `%2F` is `/`), whether there is a `resource=` (note only yes or no), and the value of `code_challenge_method=`. Once they are noted, sign in as the `demo` user. If you were not asked to sign in, note "not asked to sign in".

### A5 Is the adapter picked automatically?

Start a new conversation, pick 「Doris 专家」 and ask: `Are there any slow queries running on the cluster right now?`

Chinese original: `现在集群上有没有正在运行的慢查询？`

- Expected: Quick picks `doris-debug` (or `doris-profile-reader`) and `doris-mcp-adapter`; it calls `doris___execute_query` to run `SHOW PROCESSLIST` (the adapter's translation of `doriscli profile list --active`), and may also call `doris___list_recent_queries`; the answer explains that the service account sees only its own sessions, not the queries other users are running, and asks you for the SQL or query_id of the slow query to analyze it further.
- Should not happen: it asks you to run `doriscli`, a mysql client or curl; it runs `KILL`.
- Note: the send time (hh:mm:ss), the total time, the skills and the order of the tool calls Quick shows, and whether it asked you to run a command.

When Part A is done, first reply to me with template 1 of "Reply templates". Once the AI has checked it, start Part B.

## Part B: Full rehearsals × 2

Three notes first:

- The questions can be asked in English or in Chinese. The agent answers in the language of the question.
- The data is Chinese: every text value (shop, category, brand, region, carrier and promotion names, review words) stays Chinese in the answers, possibly with an English gloss. The reference tables below show them the same way.
- For English listeners: 618 is the mid-year shopping festival around June 18; Double 11 (双 11, Singles' Day) is the one around November 11.

Each round goes like this:

1. Say 「开始第 N 轮」 (or "start round N") in the conversation and wait for the AI to reply 「可以开始」 (ready to start).
2. Start a new conversation, pick 「Doris 专家」 and ask the 7 questions below in order; ask the next one only when the previous answer is fully shown. Copy the questions exactly.
3. For each question, note six things:
   - the send time (local time, hh:mm:ss);
   - the total time: start the stopwatch when you press send, stop it when the answer is fully shown, note the seconds;
   - the skills and the order of the tool calls Quick shows, e.g. `doris-mcp-adapter → execute_query → list_recent_queries → get_query_profile`;
   - permission pop-ups: only `doris___reload_semantic_layer` should pop up; always deny it; note how many times it popped up;
   - a 424 or another error: note the message verbatim (without any address in it);
   - whether it matches the expectations below: yes / no (if no, one sentence why).
4. When all 7 questions are done, reply to me with template 2. The AI notes the end time, runs `demo-check post` (audit log, Gateway timings per minute, connection count), checks the answers against the reference values and then tells you whether the next round can start.

Round 2 asks the same 7 questions as round 1, in a new conversation.

### Step 1 (opening): `Check the Doris connection status`

Chinese original: `检查一下 Doris 连接状态`

- Expected: it calls `doris___check_service_health` (maybe also `doris___list_databases`), and may call `doris___execute_query` to run `SHOW VARIABLES LIKE 'version_comment'` for the version; the answer says the connection is fine and the version is 4.1 (not mentioning the version is not a failure); no host address, IP, port or account appears.

### Step 2 (act 2, business overview): `This year's monthly GMV, order count and average order value: how do they compare with the same period last year? And by channel, what is the mini program's share?`

Chinese original: `今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比`

- Expected: first `doris___list_metrics`, then `doris___query_metric` (once by month and once by channel; they may also be merged, or there may be one more call). Calling `doris___list_dimensions_for_metric` or `doris___get_query_guide` first to look up the dimensions is also normal.
- The numbers should match the reference values below (the same as in P4, as of 2026-09-25; the number of decimals may differ, compare at the precision the answer shows):

| Month | GMV | Orders | Average order value | GMV same period last year | YoY | Mini program share |
|---|---|---|---|---|---|---|
| 2026-01 | 7,986,117.85 | 5,753 | 1,388.17 | 5,211,027.86 | +53.25% | 30.82% |
| 2026-02 | 4,599,422.58 | 2,849 | 1,614.40 | 3,986,552.32 | +15.37% | 33.31% |
| 2026-03 | 6,391,853.90 | 4,526 | 1,412.25 | 5,397,104.03 | +18.43% | 32.26% |
| 2026-04 | 5,793,467.18 | 3,840 | 1,508.72 | 4,876,168.12 | +18.81% | 34.98% |
| 2026-05 | 8,039,374.11 | 5,029 | 1,598.60 | 6,164,787.89 | +30.41% | 31.58% |
| 2026-06 | 13,657,823.71 | 7,821 | 1,746.30 | 10,188,029.34 | +34.06% | 31.74% |
| 2026-07 | 6,630,639.04 | 4,305 | 1,540.22 | 5,718,799.51 | +15.94% | 32.81% |
| 2026-08 | 6,808,922.61 | 4,239 | 1,606.26 | 5,742,538.20 | +18.57% | 32.76% |
| 2026-09 | 5,754,567.17 | 4,633 | 1,242.08 | 5,780,111.92 | -0.44% | 32.10% |
| Total | 65,662,188.15 | 42,995 | 1,527.21 | 53,065,119.19 | +23.74% | 32.30% |

| Channel | GMV | Orders | GMV share |
|---|---|---|---|
| APP | 28,956,861.86 | 19,045 | 44.10% |
| MINI_PROGRAM (mini program) | 21,209,275.57 | 13,831 | 32.30% |
| PC | 9,413,720.01 | 6,160 | 14.34% |
| H5 | 6,082,330.71 | 3,959 | 9.26% |

- September 2026 only runs to September 25, while the same period last year is the whole of September 2025, so September's YoY is low (-0.44%). The answer should point this out. Compared on the same days (September 1–25 against September 1–25, 2025), the reference values are 5,754,567.17 against 4,721,825.63, YoY +21.87%.
- Giving only the mini program without listing the other channels is not a failure; nor is a total row without YoY and average order value.

### Step 3 (act 3, promotion review): `Which category contributed the most during the 618 and Double 11 promotions?`

Chinese original: `618 和双 11 哪个类目贡献最大？`

- Expected: first query `ecom.dim_promotion` for the start and end dates of the two promotions (618 of 2026: 05-26 to 06-18; Double 11 of 2025: 2025-10-20 to 11-11), then sum the paid amount of the order lines by first-level category with `doris___query_metric` (`line_gmv` by `category__cat1_name`) or `doris___execute_query`.
- Conclusion: at 618, **家用电器 (Home appliances)** contributed the most (30.52%); at Double 11, **手机数码 (Phones & digital)** was the largest (26.04%).
- Reference values (the paid amount of the order lines within the promotion; the top 5 categories of each promotion):

| Category | 618 (2026) | Share |
|---|---|---|
| 家用电器 (Home appliances) | 4,246,225.85 | 30.52% |
| 手机数码 (Phones & digital) | 3,792,443.46 | 27.26% |
| 电脑办公 (Computers & office) | 2,200,281.81 | 15.82% |
| 美妆个护 (Beauty & personal care) | 950,662.85 | 6.83% |
| 食品生鲜 (Food & fresh) | 863,086.11 | 6.20% |
| Total (12 categories) | 13,910,841.80 | 100% |

| Category | Double 11 (2025) | Share |
|---|---|---|
| 手机数码 (Phones & digital) | 2,819,401.92 | 26.04% |
| 家用电器 (Home appliances) | 1,924,179.64 | 17.77% |
| 美妆个护 (Beauty & personal care) | 1,347,724.62 | 12.45% |
| 电脑办公 (Computers & office) | 1,203,259.02 | 11.11% |
| 食品生鲜 (Food & fresh) | 852,991.33 | 7.88% |
| Total (12 categories) | 10,827,037.71 | 100% |

- If the agent uses a different time range (e.g. only June 18 itself, or the 618 of 2025), the numbers differ: note the range it used; not a failure.

### Step 4 (act 5, troubleshooting): `Which shop has had an abnormal refund rate recently? What is the cause? Is there a logistics problem?`

Chinese original: `最近哪家店的退款率异常？原因是什么？物流有没有问题？`

- Expected: several `doris___execute_query` calls: each shop's monthly refund rate against its own baseline of the past 6 months (window functions), word segmentation of the bad reviews (TOKENIZE) and full-text search (MATCH_PHRASE), delivery times (PERCENTILE). About 5–12 calls, 1–3 minutes in total.
- Reference:
  - Shop: **深圳极速数码配件专营店** (Shenzhen Jisu Digital Accessories Store). 2026-07 refund rate 17.4% (32 of 184 items refunded, 29 of them for quality problems; its own baseline 0.8%), 2026-08 22.1% (51 of 231 items refunded, 49 for quality problems; baseline 3.7%).
  - Cause: 「发烫」 (overheating; 0 → 52 times) and 「充不进电」 (won't charge; 0 → 39 times) newly appear in the bad reviews; all 65 reviews containing 「发烫」 come from this shop (average rating 1.89). The reviews containing 「坏了」 (broken) come from the store 食品生鲜馆 (Fresh Food Hall); that is a different problem, do not attribute it to this shop.
  - Logistics: 极兔速递 (J&T Express) is clearly slow on shipments to the northwest: 425 orders, 140.6 hours on average, P90 205.6 hours, 80.7% over 4 days (韵达 (Yunda) P90 122.1 hours / 47.8%). Broken down by the shipment tracking records, J&T's trunk leg takes 118.1 hours (顺丰 (SF Express) 42.1, 京东 (JD Logistics) 25.4): the problem is the trunk leg.
- The agent may answer only the refund rate and the cause and give the logistics only roughly (e.g. only the average time): note what it gave; not a failure.

### Step 5 (act 7 + Track A): `Why does the query that counts daily UV of the tracking events take so long? Give the profile evidence`

Chinese original: `按天统计埋点 UV 这个查询为什么要这么久？给出 profile 证据`

- Expected: Quick picks `doris-mcp-adapter` and `doris-profile-reader` (or `doris-debug`). It runs the query with profile as the adapter says: `doris___execute_query` (the SQL has `SET_VAR(enable_profile=true)` and `/* trace:… */`) → `doris___list_recent_queries` (finds the query_id by the trace) → `doris___get_query_profile` (if the result is truncated, it calls again with `max_chars=60000`). In round 2 the agent may also skip running with profile and use `doris___list_recent_queries` to find the profile of round 1 and read it (the adapter prefers an existing profile); that also matches the expectations.
- Reference: `ecom.fact_user_event` has 1.02 million rows over 135 days; the day with the most UV is 2026-06-18 (3,873). Measured in the spec phase, the profile `Total` of this query in Doris is 46 ms (Plan 3 ms, Schedule 9 ms, Fetch Result 32 ms).
- A good answer: quotes numbers from the profile such as `Total`, explains that the query itself takes only tens of milliseconds in Doris and the wait is mostly spent on the tool calls (5–10 s each); it may suggest pre-aggregation (the `uv_bitmap` of `agg_daily_traffic`) or a materialized view. It should not invent a bottleneck that is not in the profile.
- Should not happen: it asks you to run `doriscli profile`; it runs a `SET` statement.
- If the agent first asks you for the SQL or query_id of the query (that is what the adapter does for someone else's slow query), reply: `Write your own query that counts daily UV on ecom.fact_user_event and run it with profile` (in Chinese: `你自己写一条按天统计 ecom.fact_user_event UV 的查询，带 profile 执行`); note that it asked; not a failure. Keep the stopwatch running until the final answer is fully shown; this follow-up reply does not count as a resend; note it under "Other observations". If it looks up the query_id by the trace twice without finding it and says the profile could not be collected (what the adapter does), that is not invention, but Track A was not demonstrated: fill in "matches expectations" with "no (profile not collected)" and note it; Task 8 decides what to do about it.

### Step 6 (Track B, design review): `Review the table design of fact_user_event: are the VARIANT column, partitioning and bucketing reasonable? Give improved DDL`

Chinese original: `评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL`

- Expected: Quick picks `doris-best-practices` (and `doris-mcp-adapter`); it calls `doris___execute_query` to run `SHOW CREATE TABLE` and `SHOW PARTITIONS`, maybe also `SHOW DATA SKEW` and `SHOW TABLE STATS`.
- Reference (the actual table design): DUPLICATE KEY(event_date, event_time, user_id); automatic daily partitions (AUTO PARTITION BY RANGE(date_trunc(event_date, 'day'))), now 135 partitions (2026-05-14 to 2026-09-25); DISTRIBUTED BY HASH(user_id) BUCKETS 2, 270 tablets in total, for only about 1.02 million rows; `props` is VARIANT; `search_keyword` has an inverted index; a single replica.
- A good answer: points out that there are too many partitions and tablets and that each tablet is too small (e.g. suggests monthly partitions, or fewer buckets); gives a view on VARIANT; gives improved DDL (a new table + migration with `INSERT INTO … SELECT`) and says that a person runs it.
- **Do not run** the DDL the agent gives; copy it into template 2 (if it is long, copy only the `CREATE TABLE` line and the partition and bucket clauses).

### Step 7 (closing): `Recommend a data model for scenarios like agg_daily_traffic`

Chinese original: `为 agg_daily_traffic 这类场景推荐数据模型`

- Expected: Quick picks `doris-architecture-advisor` (maybe also `doris-best-practices`); it may first run `SHOW CREATE TABLE ecom.agg_daily_traffic` to see the current design.
- Reference: `agg_daily_traffic` already exists, with AGGREGATE KEY(event_date, channel, event_type): `pv` SUM, `uv_bitmap` BITMAP_UNION, `uv_hll` HLL_UNION, `last_event` MAX; 4,927 rows.
- A good answer: recommends (or confirms) the aggregate model + BITMAP_UNION / HLL_UNION for UV and explains the trade-offs; it may mention a materialized view as an alternative; it gives DDL and says that a person runs it.
- **Do not run** the DDL the agent gives.

## Reply templates

Copy a template below, fill it in and send it to me: template 1 when Part A is done, template 2 once after each round. Include no URL, secret or token. You may reply with this English template or with the Chinese one in `quick/P5-guide.md`.

Template 1 (Part A):

```
Time zone:
A1 import: doris-mcp-adapter __; doris-debug __; doris-profile-reader __; doris-best-practices __; doris-architecture-advisor __ (success / failure + error message verbatim)
A1 subfolders shown as separate skills: yes / no (names: )
A2 「Doris 专家」: instructions replaced (yes / no, message: ); skills: 5 attached / skills are global / other: ____; connector only Doris-Desktop-MCP (yes / no)
A2 「Doris 专家（svc）」: updated (yes / no); doris-mcp-svc tool count in the desktop version: __
A3 Doris-Desktop-MCP tool count: __; permissions set as in the table (yes / no, differences: )
A4 sign-in: not asked to sign in / scope=____; resource: yes / no; code_challenge_method=____ (or: address not visible)
A5: sent hh:mm:ss, __ s; skills: ____; tools: ____; asked me to run a command: yes / no
Other observations:

A5 full answer (replace any connection details in it, such as host addresses, IPs, ports or accounts, with <redacted>):
```

Template 2 (each round):

```
Round __
Step 1 opening: sent hh:mm:ss, __ s; skills: ____; tools: ____; pop-ups: __; 424 / errors: ; matches expectations:
Step 2 act 2: sent hh:mm:ss, __ s; skills: ____; tools: ____; pop-ups: __; 424 / errors: ; matches expectations:
Step 3 act 3: sent hh:mm:ss, __ s; skills: ____; tools: ____; pop-ups: __; 424 / errors: ; matches expectations:
Step 4 act 5: sent hh:mm:ss, __ s; skills: ____; tools: ____; pop-ups: __; 424 / errors: ; matches expectations:
Step 5 Track A: sent hh:mm:ss, __ s; skills: ____; tools: ____; pop-ups: __; 424 / errors: ; matches expectations:
Step 6 Track B: sent hh:mm:ss, __ s; skills: ____; tools: ____; pop-ups: __; 424 / errors: ; matches expectations:
Step 7 closing: sent hh:mm:ss, __ s; skills: ____; tools: ____; pop-ups: __; 424 / errors: ; matches expectations:
Statements the agent proposed for a person to run (verbatim, one per line; "none" if there are none):
Resent questions (step number and reason; "none" if there are none):
Other observations:

Full answers (7 parts; replace any connection details in them, such as host addresses, IPs, ports or accounts, with <redacted>):
```
