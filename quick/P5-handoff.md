# P5 交接：导入 skills + 两轮完整彩排（T5.3 + T5.4）

> 本文件不含任何 URL、secret 或 token。详细步骤见 `quick/P5-guide.md`，本文件只是摘要和清单。

## 当前状态

- **已完成（AI 侧）**：
  - `quick/skills/` 里有 5 个 skill：自写的 `doris-mcp-adapter`，以及从 apache/doris-skills 锁定 commit 生成的 4 个副本（`UPSTREAM.md` 记录了来源和改动）。
  - `quick/agent-instructions.md` 更新了：诊断类问题先加载 adapter；时间粒度；「同期同天数」怎么比；不要用 OR 连接几个时间范围；时间只按 `metric_time` 过滤（不用 `order_date`）；回答跟随提问的语言（中文问中文答，英文问英文答）；类目维度名；活动日期查 `dim_promotion`；差评原因用倒排索引检索。
  - Runtime 已重新部署：审计日志会记下失败的原因和 `query_metric` 的过滤条件；`metric_time` 的过滤条件修好了（按天的范围、`>` / `<`、多个条件取交集；用 OR 连接会报错并提示改法）。
  - 整体评审（opus）的结果和处理见 `specs/doris-mcp-quick/progress.md` 的最新一条日志。
- **每一轮开始前**：你说「开始第 N 轮」，AI 跑 `demo-check pre`（约 1.5 分钟），把结果和开始时间（UTC）告诉你，再回复「可以开始」。

## 要做的事

打开 `quick/P5-guide.md`（可以在你自己的终端里 `less quick/P5-guide.md` 查看），按顺序做：

- [ ] **准备**：在你自己的终端里用 `scp` 把 `quick/skills` 拷到这台电脑（命令见指南「准备」）。
- [ ] **Part A**：导入 skills（T5.3）
  - [ ] A1：按顺序导入 5 个文件夹：`doris-mcp-adapter`、`doris-debug`（整个文件夹一次导入）、`doris-profile-reader`、`doris-best-practices`、`doris-architecture-advisor`。`LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md` 不导入。
  - [ ] A2：「Doris 专家」换上 `quick/agent-instructions.md` 的新全文，挂上 5 个 skill，连接器只有 `Doris-Desktop-MCP`；备份「Doris 专家（svc）」同样更新。
  - [ ] A3：12 个 `doris___` 工具按指南的表设置权限（D7：`doris___execute_query` 改为 Always Allow，`doris___reload_semantic_layer` 仍是 Ask Each Time）。
  - [ ] A4：只有弹出登录页时才做：先不要登录，从地址栏读 `scope=`、有没有 `resource=`、`code_challenge_method=`。
  - [ ] A5：新对话问 `现在集群上有没有正在运行的慢查询？`，看 adapter 有没有被选中。
  - [ ] 用模板 1 回复我，等 AI 核对。
- [ ] **Part B**：完整彩排 × 2（T5.4），每一轮：
  - [ ] 说「开始第 N 轮」，等 AI 回复「可以开始」。
  - [ ] 新对话，按顺序问 7 个问题（指南 Part B），每个问题记六项（发送时间、总耗时、skills 和工具、弹窗、424 / 报错、是否符合期望）。
  - [ ] 用模板 2 回复我，等 AI 跑完 `demo-check post` 并核对答案。

预计 Part A 30–40 分钟，每一轮 30–45 分钟。中途有问题可以随时问我。

## 注意

- 不要把 URL、secret、token 或登录页的地址粘贴到对话里。
- Quick 要求重新填 client secret 或 `demo` 密码时，按 `quick/T0.7-guide.md` 的「Step 2：取 secret」在**你自己的终端**里获取，不要用 Claude Code 的 `!` 前缀。
- agent 建议的 DDL、`ALTER`、`KILL` 等写操作一律不要执行，照抄进模板 2。不要删库重建，也不要做第 1 幕和第 7 幕的写入。
- `doris___reload_semantic_layer` 的弹窗一律拒绝。
- 遇到 424、报错或意料之外的弹窗：记下时间、工具名和错误信息原文（先把其中的地址去掉），然后继续。同一个问题最多重发一次。
- 两轮之间 AI 只修挡路的问题；其他问题记下来，T5.5 统一处理。

## 做完后

Part A 做完发模板 1，每一轮做完发一次模板 2（下面是 `quick/P5-guide.md`「回复模板」的副本）：

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

收到模板 1 后，AI 核对导入结果和 A5 的回答，必要时改 adapter 或指令，再告诉你能不能开始 Part B。收到模板 2 后，AI 记下结束时间，跑 `demo-check post`（审计日志、每分钟的 Gateway 耗时、连接数），对照指南里的参照值核对答案，把每一步的耗时记进 progress。两轮都做完后，AI 按结果做 T5.5（修问题、写 `quick/runbook.md` 的耗时表、四项决策），再提交。
