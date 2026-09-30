# 演示手册：Doris MCP × Amazon Quick 桌面版

> 本文件不含任何 URL、secret 或 token。连接参数见 `quick/T0.7-guide.md`；secret 只在你自己的终端里获取，不要用 Claude Code 的 `!` 前缀。
> 问题和参照值来自 design §10 和 `quick/P5-guide.md` Part B；「每步耗时」来自两轮彩排（T5.4）。
> English version: `quick/runbook.en.md`

## 演示前

1. 演示前 30 分钟以内，在开发机的仓库根目录运行预检（只读，约 1.5 分钟）：

   ```
   bash scripts/demo-check.sh pre
   ```

   每项一行 `[PASS]` / `[FAIL]`，最后一行是 `demo-check pre: N/M passed`；有 `[FAIL]` 时退出码是 1。检查的内容：AWS 账号；Gateway 和 target 是 READY；能取到 Gateway token；经 Gateway 列出 12 个工具；经 Gateway 跑一遍 profile 流程（带 profile 执行一条查询 → 按 trace 找到 query_id → 读 profile）和 3 个错误用例（非法的 query_id、不存在的 query_id、`DELETE` 被拒绝）；对账（语义层的数和手写 SQL 一致）；`mcp_svc` 的权限；`mcp_svc` 的连接数（不超过 80）。
   只有一项 `[FAIL]` 时先重跑一次：spec 阶段连续 3 次预检里有 2 次各有 1 项偶发失败（Runtime 返回 502，或冷启动慢到 Gateway 报错），重跑就通过了。同一项连续两次 `[FAIL]`，先看「出问题时」，不要开始演示。
2. 记下预检结束的时间（`date +%s%3N`，毫秒），演示后要用。预检和演示之间不要再跑别的脚本，这样审计日志里只有演示的调用。
3. Quick 桌面版：
   - 已登录；「Doris 专家」的指令是 `quick/agent-instructions.md` 的全文，挂着 5 个 skill（`doris-mcp-adapter`、`doris-debug`、`doris-profile-reader`、`doris-best-practices`、`doris-architecture-advisor`），只关联 `Doris-Desktop-MCP`。
   - `Doris-Desktop-MCP` 有 12 个 `doris___` 工具，权限按「设置」。
   - 新建一个对话，先不提问。
4. 数据：第 1 幕（Stream Load 实时写入）和第 7 幕建 MV 是写操作，由演示者在 Quick 之外人工执行，Quick 只读结果。`quick/P5-guide.md` 的参照值是 09-25 上午的订单已经导入之后的数；如果删库重建，9 月（第 2 幕）会少掉当天的订单，参照值要重新算。

## 设置

- 工具权限（D7）：彩排和演示时 `doris___execute_query` 是 Always Allow（不弹窗，省下每次的确认时间），`doris___reload_semantic_layer` 是 Ask Each Time（弹窗一律拒绝），其余 10 个工具是 Always Allow。完整的表见 `quick/P5-guide.md` A3。其他时间把 `doris___execute_query` 改回 Ask Each Time（见「演示后」）。
- 连接器：`Doris-Desktop-MCP`（User auth，`demo` 用户）。桌面版不能刷新已有连接器的工具列表：如果工具数不是 12，或者工具调用返回 HTTP 400「参数无效」，在**网页版**新建一个连接器（参数见 `quick/T0.7-guide.md`），再在桌面版把 agent 改为关联新连接器。
- skills：从仓库的 `quick/skills/` 按文件夹导入（`doris-debug` 整个文件夹一次导入）；`LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md` 不导入。改了 skill 要重新导入。
- 指令：`quick/agent-instructions.md` 全文。
- 备份：「Doris 专家（svc）」关联 `doris-mcp-svc`（Service auth，不需要登录）。桌面版的旧连接器刷新不了工具列表，备份在**网页版**使用。

## 演示流程

每个问题等上一个回答完整显示后再问；问题原样复制。「预计」按每次工具调用 5–10 s 估算，彩排实测见「每步耗时」。

| 步骤 | 段落 | 问题 | 看点 / 要讲的 | 预计 |
|---|---|---|---|---|
| — | 第 1 幕 | （演示者在 Quick 之外做 Stream Load 实时写入，不经过 MCP） | 写 = 人工，读 = MCP | — |
| 1 | 开场 | `检查一下 Doris 连接状态` | 连接正常、版本 4.1；回答里没有主机地址、账号 | 10–20 s |
| 2 | 第 2 幕 经营大盘 | `今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比` | 语义层（`list_metrics` → `query_metric`）；先调用 `get_query_guide` / `list_dimensions_for_metric` 是正常的（P4 评审 M-3）；9 月只到 25 日，同比要按同天数看（+21.87%）；小程序占比 32.30% | 40–90 s |
| 3 | 第 3 幕 大促复盘 | `618 和双 11 哪个类目贡献最大？` | 618 家用电器第一（30.52%），双 11 手机数码第一（26.04%）；活动日期来自 `dim_promotion` | 40–90 s |
| 4 | 第 5 幕 问题排查 | `最近哪家店的退款率异常？原因是什么？物流有没有问题？` | 深圳极速数码配件专营店；差评「发烫」「充不进电」（倒排索引、TOKENIZE、MATCH_PHRASE）；极兔发西北的干线慢（PERCENTILE） | 1–3 min |
| 5 | 第 7 幕 + Track A | `按天统计埋点 UV 这个查询为什么要这么久？给出 profile 证据` | adapter + profile-reader；带 profile 执行 → 按 trace 找 query_id → 读 profile；Doris 里只要几十毫秒，时间花在工具调用上 | 1–2 min |
| — | 第 7 幕 | （演示者在 Quick 之外建 MV，不经过 MCP） | 写 = 人工 | — |
| 6 | Track B 设计评审 | `评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL` | best-practices；按天分区 135 个、BUCKETS 2 共 270 个小 tablet；DDL 只给出，不执行 | 1–2 min |
| 7 | 收尾 | `为 agg_daily_traffic 这类场景推荐数据模型` | architecture-advisor；聚合模型 + BITMAP_UNION / HLL_UNION；DDL 由人工执行 | 40–90 s |

## 出问题时

- **424 或工具报错**：Quick 等单次工具调用有上限（约 60 s）。让 agent 缩小范围（加时间范围、`LIMIT`、先 `EXPLAIN`），重发一次；还不行就跳过这一步，讲 `quick/P5-guide.md` 里的参照值。
- **回答里出现 Doris 主机地址或 IP**（例如 2003 连接错误的原文）：不要念出来；录屏的话剪掉这一段。演示后告诉 AI，按 design §14 处理。
- **弹出 `doris___reload_semantic_layer` 的权限窗口**：拒绝，让 agent 不重载继续回答。
- **agent 让你去运行 `doriscli`、mysql 客户端或 curl**：回复「这里没有命令行，只能用 Doris MCP 工具，按 doris-mcp-adapter 的对照表来」。
- **第 5 步 agent 问你要慢查询的 SQL 或 query_id**：回复「你自己写一条按天统计 ecom.fact_user_event UV 的查询，带 profile 执行」。
- **agent 要执行写操作（DDL、`KILL`、`SET`）**：工具会拒绝；让它把语句写出来，说明由人工执行。
- **连接器失效、要求重新登录或工具数不对**：先切到备份「Doris 专家（svc）」（网页版）；演示后按「设置」新建连接器。
- **怀疑后端有问题**：在开发机上重跑 `bash scripts/demo-check.sh pre`，看哪一项 `[FAIL]`。

## 演示后

1. 记下演示结束的时间（`date +%s%3N`），在开发机上运行（只读）：

   ```
   bash scripts/demo-check.sh post --since <预检结束的毫秒数> --until <演示结束的毫秒数>
   ```

   输出：审计日志里这段时间每个工具的调用次数和成败，再逐条列出失败的调用（时间、工具、错误原因；`query_metric` 还有它的 `group_by` / `where` / `having`）。审计日志里的工具名不带 `doris___` 前缀，这是正常的（P4 评审 M-7）。然后是 Gateway 每分钟、每个工具的调用数和耗时（≥ 45 s 标 WARN，≥ 60 s 算失败），以及 `mcp_svc` 当前的连接数。
2. 在 Quick 里把 `doris___execute_query` 改回 Ask Each Time（D7）。
3. 演示全部结束、不再需要这套环境时（T5.6）：
   - AWS 侧：先 dry-run，看清要删的资源：

     ```
     bash infra/99-cleanup.sh
     ```

     确认之后（GATE，一次确认只对应这一次）才执行 `APPLY=1 bash infra/99-cleanup.sh`。它按顺序删除 Gateway target、Gateway、Runtime 的栈、Interface endpoints（持续计费）、Cognito、secret、Doris SG 上引用 Runtime SG 的规则、本项目的 SG 和两个 IAM 角色；`infra/state.env` 保留，作为删了什么的记录。它不删除 CDK 的引导栈 `CDKToolkit` 和它的 S3 桶：它们在本项目之前就已存在（agentcore 部署只往桶里上传了资产），同一账号、同一区域的其他 CDK 项目也可能在用，所以保留。部署上传的 CodeZip 等资产也留在这个桶里。
   - Doris 侧（可选，单独确认）：`mcp_svc` 账号和语义层的库 `system_mcp` 不会被 `99-cleanup.sh` 删除。如果以后不再演示，由你用 root 在自己的 mysql 客户端里执行下面两句（AI 不执行）：

     ```
     DROP USER IF EXISTS 'mcp_svc'@'172.31.%';
     DROP DATABASE IF EXISTS system_mcp;
     ```

     `ecom` 的数据和 `demo_ro` 账号不受影响。以后要再演示，需要重新走 P2（发布语义层）和 P3（建账号）。
   - Quick 侧：连接器、agent 和 skills 由你在 Quick 里删除（可选）。

## 每步耗时

两轮彩排（T5.4）实测，单位秒；由 T5.5 根据彩排回复填写。「工具调用」是 Gateway 记录的这一步的调用次数。

| 步骤 | 段落 | 第 1 轮 | 第 2 轮 | 工具调用 | 单次最长 |
|---|---|---|---|---|---|
| 1 | 开场 | — | — | — | — |
| 2 | 第 2 幕 | — | — | — | — |
| 3 | 第 3 幕 | — | — | — | — |
| 4 | 第 5 幕 | — | — | — | — |
| 5 | 第 7 幕 + Track A | — | — | — | — |
| 6 | Track B | — | — | — | — |
| 7 | 收尾 | — | — | — | — |
