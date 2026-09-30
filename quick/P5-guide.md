# P5：导入 skills + 两轮完整彩排（T5.3 + T5.4）

> 本文件不包含任何 URL、secret 或 token。连接参数（MCP URL、Token URL、Authorize URL、client ID）见 `quick/T0.7-guide.md` 的「连接参数」。如果 Quick 要求重新登录，或者要求重新填 client secret / `demo` 用户的密码，按 T0.7 的「Step 2：取 secret」在**你自己的终端**里获取，不要用 Claude Code 的 `!` 前缀。
> English version: `quick/P5-guide.en.md`

## 注意

- 不要把 URL、secret、token 或登录页的地址粘贴到对话里。
- 权限按 D7：彩排期间 `doris___execute_query` 是 Always Allow（不会弹窗），`doris___reload_semantic_layer` 是 Ask Each Time，弹窗一律拒绝。彩排结束后按 `quick/runbook.md` 的「演示后」改回。
- agent 建议的写操作（DDL、`ALTER`、`INSERT`、`KILL`、改配置）**一律不要执行**，照抄进回复模板。彩排不做第 1 幕（Stream Load）和第 7 幕建 MV：09-25 上午的订单已经在库里，集群保持现状，**不要删库重建**。
- 遇到 424、报错或意料之外的弹窗：记下时间、工具名和错误信息原文（先把其中的地址去掉），然后继续。同一个问题最多重发一次。
- 每一轮开始前，在对话里说「开始第 N 轮」，等 AI 回复「可以开始」：AI 先跑 `demo-check pre`（约 1.5 分钟）并记下开始时间。从这时起到你发回这一轮的回复之前，AI 不调用 Gateway 或 Runtime，审计日志和耗时里只有你的调用。
- 两轮之间只修挡路的问题（答不出、工具报错、答案和参照值对不上）；措辞和格式上的问题记下来，T5.5 统一处理。
- 预计：Part A 30–40 分钟；每一轮 30–45 分钟（7 个问题；每次工具调用 5–10 s，第 5 幕和 Track A 各要 5–12 次调用）。

## 准备

- 秒表（手机即可）和记事本；记下这台电脑的时区（回复模板第一行），AI 按 UTC 对日志。
- Quick 桌面版已登录。「Doris 专家」只关联 `Doris-Desktop-MCP`（P4 在网页版新建的连接器；桌面版里旧的 `doris-mcp` 刷新不了工具列表）。
- 把 skills 拷到这台电脑。在**你自己的终端**里执行（`<开发机>` 换成你平时 SSH 登录开发机用的主机名或别名）：

```
scp -r <开发机>:/home/ubuntu/AI-code/Doris-mcp-skill-Demo/quick/skills ./doris-skills
```

- 拷完后 `doris-skills` 下有 5 个文件夹和 3 个文件（`LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md`）。只导入 5 个文件夹，3 个文件不导入：`UPSTREAM.md` 记录了这些副本来自 apache/doris-skills 的哪个 commit、改了哪些地方，`LICENSE.txt` 是它的许可证。

## Part A：导入 skills（T5.3）

### A1 导入 5 个 skill

**Customize → Skills → From folder**，按下表的顺序逐个导入，每次选一个文件夹（每个都不到 1 MB，Quick 的上限是 6 MB）：

| 顺序 | 文件夹 | 作用 |
|---|---|---|
| 1 | `doris-mcp-adapter` | 本项目自写：把 doris-* skills 里的 doriscli 命令换成 `doris___*` 工具；只读边界；每次调用 60 s 的上限 |
| 2 | `doris-debug` | 故障诊断（慢查询、导入、Compaction、集群问题等）。**整个文件夹一次导入**，里面的子文件夹（`query`、`import`、`data-lake` 等）作为参考文件随它一起导入，不要单独导入 |
| 3 | `doris-profile-reader` | 解读 Query Profile |
| 4 | `doris-best-practices` | 建表、分区分桶、数据模型的最佳实践和 DDL 评审 |
| 5 | `doris-architecture-advisor` | 按业务场景推荐架构和数据模型 |

- 每导入一个，记下成功还是失败；失败时记下报错原文。Quick 里显示的 skill 名称应该和文件夹名一致。
- 如果 Quick 把 `doris-debug` 里的子文件夹也显示成单独的 skill（名字类似 `doris-debug-query`），记下来，不用处理。

### A2 更新 agent

1. 打开 agent「Doris 专家」的编辑页。
2. 指令：删掉原来的全文，粘贴仓库里 `quick/agent-instructions.md` 的新全文（约 3300 字符；可以在你自己的终端里 `cat quick/agent-instructions.md` 后复制，这个文件里没有 secret）。新版比 P4 多了几条：诊断类问题先加载 doris-mcp-adapter；可用的时间粒度；「同期同天数」怎么比；不要用 OR 连接几个时间范围；时间只按 metric_time 过滤（不用 order_date）；回答跟随提问的语言（中文问中文答，英文问英文答）；类目维度名；活动日期查 dim_promotion；差评原因用倒排索引检索。全文粘到指令框；「描述」栏只能写一行纯文本，里面有换行时保存会报 `\P{C}*` 的校验错误。如果 Quick 提示指令太长，记下提示原文。
3. skills：挂上 A1 的 5 个 skill。如果 agent 的编辑页里没有选择 skill 的地方（skills 对所有 agent 生效），记「skills 是全局的」。
4. 连接器：只关联 `Doris-Desktop-MCP`，不变。
5. 备份 agent「Doris 专家（svc）」（关联 `doris-mcp-svc`）：同样替换指令、挂上 skills。再看一眼 `doris-mcp-svc` 在桌面版里显示几个 `doris___` 工具，记下数量；不是 12 个也不用修（P4 里桌面版的旧连接器刷新不了，备份走网页版）。

### A3 工具权限（D7：彩排和演示用的设置）

打开 `Doris-Desktop-MCP`，确认 12 个 `doris___` 工具都已启用，权限按下表（和 P4 相比，`doris___execute_query` 改为 Always Allow）：

| 工具 | 权限 |
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

`doris-mcp-svc` 在桌面版如果也是 12 个工具，按同一张表设置。

### A4 scope（P0 评审 M-1，情况 c）

只在 Quick 要求登录时做（导入 skills、改 agent 或第一次提问时弹出登录页）：**先不要登录**，按 `quick/P4-guide.md` A2 的方法只从地址栏读三项：`scope=` 的值（`%20` 和 `+` 都是空格，`%2F` 是 `/`）、有没有 `resource=`（只记有或无）、`code_challenge_method=` 的值。记完再用 `demo` 用户登录。没有要求登录，就记「没有要求登录」。

### A5 adapter 会不会被自动选中

新建一个对话，选「Doris 专家」，问：`现在集群上有没有正在运行的慢查询？`

- 期望：Quick 选中 `doris-debug`（或 `doris-profile-reader`）和 `doris-mcp-adapter`；调用 `doris___execute_query` 执行 `SHOW PROCESSLIST`（adapter 里 `doriscli profile list --active` 的翻译），也可能再调用 `doris___list_recent_queries`；回答说明服务账号只能看到自己的会话，看不到其他用户正在运行的查询，并请你提供慢查询的 SQL 或 query_id，以便进一步分析。
- 不应该出现：让你去运行 `doriscli`、mysql 客户端或 curl；执行 `KILL`。
- 记：发送时间（hh:mm:ss）、总耗时、Quick 显示的 skills 和工具调用顺序、有没有让你去运行命令。

Part A 做完后，先用「回复模板」里的模板 1 回复我。AI 核对之后，再开始 Part B。

## Part B：完整彩排 × 2

每一轮这样做：

1. 在对话里说「开始第 N 轮」，等 AI 回复「可以开始」。
2. 新建一个对话，选「Doris 专家」，按顺序问下面 7 个问题；上一个回答完整显示后再问下一个。问题原样复制。
3. 每个问题记六项：
   - 发送时间（本地时间 hh:mm:ss）；
   - 总耗时：按下发送时开始秒表，答案完整显示后停，记秒数；
   - Quick 显示的 skills 和工具调用顺序，例如 `doris-mcp-adapter → execute_query → list_recent_queries → get_query_profile`；
   - 权限弹窗：应该只有 `doris___reload_semantic_layer` 会弹，一律拒绝；记下弹了几次；
   - 424 或其他报错：记原文（去掉其中的地址）；
   - 是否符合下面的期望：是 / 否（否的话一句话说明）。
4. 7 个问题都问完，用模板 2 回复我。AI 记下结束时间，跑 `demo-check post`（审计日志、Gateway 每分钟的耗时、连接数），对照参照值核对答案，然后告诉你能不能开始下一轮。

第 2 轮和第 1 轮问同样的 7 个问题，新建对话。

### 步骤 1（开场）：`检查一下 Doris 连接状态`

- 期望：调用 `doris___check_service_health`（可能再调用 `doris___list_databases`），也可能调用 `doris___execute_query` 执行 `SHOW VARIABLES LIKE 'version_comment'` 查版本；回答说明连接正常、版本 4.1（没有提版本不算失败）；不出现主机地址、IP、端口、账号。

### 步骤 2（第 2 幕 经营大盘）：`今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比`

- 期望：先 `doris___list_metrics`，再 `doris___query_metric`（按月一次、按渠道一次，也可能合并或多一次）。先调用 `doris___list_dimensions_for_metric` 或 `doris___get_query_guide` 查维度也正常。
- 数字应该和下面的参照值一致（与 P4 相同，截至 2026-09-25；小数位数可以不同，按回答显示的位数对照）：

| 月份 | GMV | 订单数 | 客单价 | 去年同期 GMV | 同比 | 小程序占比 |
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
| 合计 | 65,662,188.15 | 42,995 | 1,527.21 | 53,065,119.19 | +23.74% | 32.30% |

| 渠道 | GMV | 订单数 | GMV 占比 |
|---|---|---|---|
| APP | 28,956,861.86 | 19,045 | 44.10% |
| MINI_PROGRAM（小程序）| 21,209,275.57 | 13,831 | 32.30% |
| PC | 9,413,720.01 | 6,160 | 14.34% |
| H5 | 6,082,330.71 | 3,959 | 9.26% |

- 2026 年 9 月只到 25 日，而去年同期是 2025 年 9 月整月，所以 9 月同比偏低（-0.44%）。回答应该指出这一点。如果按同期同天数比（9 月 1–25 日对 2025 年 9 月 1–25 日），参照值是 5,754,567.17 对 4,721,825.63，同比 +21.87%。
- 渠道只给出小程序、没有列出其他渠道，不算失败；合计行没有同比和客单价，也不算失败。

### 步骤 3（第 3 幕 大促复盘）：`618 和双 11 哪个类目贡献最大？`

- 期望：先查 `ecom.dim_promotion` 拿到两个活动的起止日期（2026年618：05-26 至 06-18；2025年双11：2025-10-20 至 11-11），再用 `doris___query_metric`（`line_gmv` 按 `category__cat1_name`）或 `doris___execute_query` 按一级类目汇总商品行实付。
- 结论：618 是**家用电器**贡献最大（30.52%），双 11 是**手机数码**最大（26.04%）。
- 参照值（活动期内的商品行实付；每个活动取前 5 个类目）：

| 类目 | 2026年618 | 占比 |
|---|---|---|
| 家用电器 | 4,246,225.85 | 30.52% |
| 手机数码 | 3,792,443.46 | 27.26% |
| 电脑办公 | 2,200,281.81 | 15.82% |
| 美妆个护 | 950,662.85 | 6.83% |
| 食品生鲜 | 863,086.11 | 6.20% |
| 合计（12 个类目） | 13,910,841.80 | 100% |

| 类目 | 2025年双11 | 占比 |
|---|---|---|
| 手机数码 | 2,819,401.92 | 26.04% |
| 家用电器 | 1,924,179.64 | 17.77% |
| 美妆个护 | 1,347,724.62 | 12.45% |
| 电脑办公 | 1,203,259.02 | 11.11% |
| 食品生鲜 | 852,991.33 | 7.88% |
| 合计（12 个类目） | 10,827,037.71 | 100% |

- 如果 agent 取的时间范围不同（例如只看 6 月 18 日当天，或者用了 2025 年的 618），数字会不同：记下它用的范围，不算失败。

### 步骤 4（第 5 幕 问题排查）：`最近哪家店的退款率异常？原因是什么？物流有没有问题？`

- 期望：多次调用 `doris___execute_query`：店铺月度退款率对比自身过去 6 个月的基线（窗口函数），差评分词（TOKENIZE）和全文检索（MATCH_PHRASE），物流时效（PERCENTILE）。大约 5–12 次调用，总耗时 1–3 分钟。
- 参照：
  - 店铺：**深圳极速数码配件专营店**。2026-07 退款率 17.4%（184 件退 32 件，其中质量问题 29 件；自身基线 0.8%），2026-08 22.1%（231 件退 51 件，质量问题 49 件；基线 3.7%）。
  - 原因：差评里新出现「发烫」（0 → 52 次）和「充不进电」（0 → 39 次）；含「发烫」的 65 条评价全部来自这家店（平均评分 1.89）。含「坏了」的评价来自食品生鲜馆，是另一类问题，不要算到这家店头上。
  - 物流：极兔速递发往西北明显偏慢：425 单，平均 140.6 小时，P90 205.6 小时，80.7% 超过 4 天（韵达 P90 122.1 小时 / 47.8%）。按轨迹拆开，极兔的干线段 118.1 小时（顺丰 42.1、京东 25.4），问题在干线。
- agent 可能只答到退款率和原因，物流给得比较粗（例如只给平均时长）：记下它给了什么，不算失败。

### 步骤 5（第 7 幕 + Track A）：`按天统计埋点 UV 这个查询为什么要这么久？给出 profile 证据`

- 期望：Quick 选中 `doris-mcp-adapter` 和 `doris-profile-reader`（或 `doris-debug`）。按 adapter 的做法带 profile 执行：`doris___execute_query`（SQL 里有 `SET_VAR(enable_profile=true)` 和 `/* trace:… */`）→ `doris___list_recent_queries`（按 trace 找 query_id）→ `doris___get_query_profile`（结果被截断时，会带 `max_chars=60000` 再调用一次）。第 2 轮 agent 也可能不再带 profile 执行，直接用 `doris___list_recent_queries` 找到第 1 轮的 profile 再读（adapter 优先用已有的 profile），同样符合期望。
- 参照：`ecom.fact_user_event` 有 102 万行、135 天；UV 最高的一天是 2026-06-18（3,873）。spec 阶段实测，这条查询在 Doris 里的 profile `Total` 是 46 ms（Plan 3 ms、Schedule 9 ms、Fetch Result 32 ms）。
- 好的回答：引用 profile 里的 `Total` 等数字，说明查询本身在 Doris 里只要几十毫秒，等待主要花在工具调用上（每次 5–10 s）；可以建议用预聚合（`agg_daily_traffic` 的 `uv_bitmap`）或物化视图。不应该编造 profile 里没有的瓶颈。
- 不应该出现：让你去运行 `doriscli profile`；执行 `SET` 语句。
- 如果 agent 先问你要这条查询的 SQL 或 query_id（adapter 对别人的慢查询就是这样做的），回复：`你自己写一条按天统计 ecom.fact_user_event UV 的查询，带 profile 执行`；记下它问了，不算失败。秒表一直计到最终答案显示完；这句追加的回复不算重发，记在「其他观察」里。如果它按 trace 找了两次都没找到 query_id，并说明 profile 没能收集到（adapter 的做法），这不是编造，但 Track A 没有演示成功：「符合期望」填「否（profile 没收集到）」，记下来，Task 8 决定怎么处理。

### 步骤 6（Track B 设计评审）：`评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL`

- 期望：Quick 选中 `doris-best-practices`（和 `doris-mcp-adapter`）；调用 `doris___execute_query` 执行 `SHOW CREATE TABLE`、`SHOW PARTITIONS`，可能还有 `SHOW DATA SKEW`、`SHOW TABLE STATS`。
- 参照（实际的建表）：DUPLICATE KEY(event_date, event_time, user_id)；按天自动分区（AUTO PARTITION BY RANGE(date_trunc(event_date, 'day'))），现在 135 个分区（2026-05-14 至 2026-09-25）；DISTRIBUTED BY HASH(user_id) BUCKETS 2，共 270 个 tablet，只有约 102 万行；`props` 是 VARIANT；`search_keyword` 上有倒排索引；单副本。
- 好的回答：指出分区和 tablet 太多、每个 tablet 太小（例如建议按月分区，或减少分桶）；对 VARIANT 给出看法；给出改进的 DDL（新建表 + `INSERT INTO … SELECT` 迁移）并说明由人工执行。
- **不要执行** agent 给出的 DDL；照抄进模板 2（如果很长，只抄 `CREATE TABLE` 那一行和分区、分桶的子句）。

### 步骤 7（收尾）：`为 agg_daily_traffic 这类场景推荐数据模型`

- 期望：Quick 选中 `doris-architecture-advisor`（可能还有 `doris-best-practices`）；可能先 `SHOW CREATE TABLE ecom.agg_daily_traffic` 看现状。
- 参照：`agg_daily_traffic` 已经存在，是 AGGREGATE KEY(event_date, channel, event_type)：`pv` SUM、`uv_bitmap` BITMAP_UNION、`uv_hll` HLL_UNION、`last_event` MAX；4,927 行。
- 好的回答：推荐（或确认）聚合模型 + BITMAP_UNION / HLL_UNION 算 UV，说明取舍；可能提到物化视图作为替代；给出 DDL 并说明由人工执行。
- **不要执行** agent 给出的 DDL。

## 回复模板

复制下面的模板，填好发给我：Part A 做完发模板 1，每一轮做完发一次模板 2。不要包含任何 URL、secret 或 token。

模板 1（Part A）：

```
时区：
A1 导入：doris-mcp-adapter __；doris-debug __；doris-profile-reader __；doris-best-practices __；doris-architecture-advisor __（成功 / 失败 + 报错原文）
A1 子文件夹显示成单独的 skill：是 / 否（名字：）
A2「Doris 专家」：指令已替换（是 / 否，提示：）；skills：挂上 5 个 / skills 是全局的 / 其他：____；连接器只有 Doris-Desktop-MCP（是 / 否）
A2「Doris 专家（svc）」：已更新（是 / 否）；doris-mcp-svc 在桌面版的工具数：__
A3 Doris-Desktop-MCP 工具数：__；权限已按表设置（是 / 否，差异：）
A4 登录：没有要求登录 / scope=____；resource：有 / 无；code_challenge_method=____（或：看不到地址）
A5：发送 hh:mm:ss，__ s；skills：____；工具：____；让我去运行命令：是 / 否
其他观察：

A5 答案全文（其中如有主机地址、IP、端口、账号等连接信息，换成 <已遮盖>）：
```

模板 2（每一轮）：

```
第 __ 轮
步骤 1 开场：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 2 第 2 幕：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 3 第 3 幕：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 4 第 5 幕：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 5 Track A：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 6 Track B：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 7 收尾：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
agent 建议人工执行的语句（照抄，一条一行；没有就写「无」）：
重发过的问题（步骤号和原因；没有就写「无」）：
其他观察：

答案全文（7 段；其中如有主机地址、IP、端口、账号等连接信息，换成 <已遮盖>）：
```
