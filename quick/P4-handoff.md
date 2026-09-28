# P4 交接：在 Quick 桌面版里测试（T4.1 + T4.4）

> 本文件不含任何 URL、secret 或 token。详细步骤见 `quick/P4-guide.md`（评审修改后的版本，提交 026a2fe），本文件只是摘要和清单。

## 当前状态（2026-09-28）

- **整体评审（opus）**：0 Critical / 1 Important / 10 Minor；全部测试通过。
  - 已修复（026a2fe）：指南 A1 原来把「看不到 scope 栏」和「scope 栏是空的」都记「无」，可能导致没有依据就写「已证实」。现在改为进连接器的编辑页，只看不保存，从四种回答里选一种原样照抄。
  - 顺带修复：地址里的 `+` 也是空格；写进 design 的结论改为以「登录页地址」为依据；权限按你的回复如实填写。
  - 其余 Minor 已记进 progress，留给 P5 / T5.5，不影响这次测试。
- **AI 侧预检**：全部通过。
  - Gateway 和 target 都是 READY；经 Gateway 能列出 12 个工具。
  - 两条参照查询和指南里的表一致；对账 11/11；权限复核 5/5。
- **开始时间**：2026-09-28T00:57:09Z（UTC）。从这时起到你回复之前，AI 不再调用 Gateway 或 Runtime。

## 要做的事

打开 `quick/P4-guide.md`（可以在你自己的终端里 `less quick/P4-guide.md` 查看），按顺序做：

- [ ] **Part A**：同步 `doris-mcp`（User auth）
  - [ ] A1：打开连接器的编辑页看 scope 一栏，**只看不保存**，从四种回答里选一种原样照抄：
    - 有 scope 栏，值是 X
    - 有 scope 栏，空
    - 编辑页里没有 scope 栏
    - 看不到鉴权设置
  - [ ] A2：点 Sync；弹出登录页时**先不要登录**，只从地址栏读三项：`scope=` 的值（`%20` 和 `+` 都是空格，`%2F` 是 `/`）、有没有 `resource=`、`code_challenge_method=` 的值。
  - [ ] A3：确认有 12 个 `doris___` 工具，全部启用，按指南的表设置权限。
- [ ] **Part B**：建 agent「Doris 专家」，指令粘贴 `quick/agent-instructions.md` 的全文；连接器只关联 `doris-mcp`，不挂 skills。
- [ ] **Part C**：问两个问题，每个问题记五项（发送时间、总耗时、工具调用顺序、权限弹窗、424 / 报错）：
  - [ ] 问题 1（开场）：`检查一下 Doris 连接状态`
  - [ ] 问题 2（第 2 幕）：`今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比`
- [ ] **Part D**：对 `doris-mcp-svc`（Service auth）和「Doris 专家（svc）」再做一遍（Sync、12 个工具和权限、两个问题）。

预计 40–60 分钟。中途有问题可以随时问我。

## 注意

- 不要把 URL、secret、token 或登录页的地址粘贴到对话里。
- Quick 要求重新填 client secret 或 `demo` 密码时，按 `quick/T0.7-guide.md` 的「Step 2：取 secret」在**你自己的终端**里获取，不要用 Claude Code 的 `!` 前缀。
- 权限弹窗：`doris___execute_query` 只在 SQL 是 SELECT、SHOW、DESCRIBE 或 EXPLAIN 时点允许，其他一律拒绝；`doris___reload_semantic_layer` 一律拒绝。
- 遇到 424、报错或意料之外的权限弹窗：记下时间、工具名和错误信息原文（先把其中的地址去掉），然后继续。同一个问题最多重试一次。

## 做完后

复制 `quick/P4-guide.md` 最后的「回复模板」，填好发给我（下面是同一份模板的副本）：

```
时区：
A1 编辑页里的 scope：____（四选一，原样照抄：有 scope 栏，值是 __ / 有 scope 栏，空 / 编辑页里没有 scope 栏 / 看不到鉴权设置）
A2 登录页：scope=____；resource：有 / 无；code_challenge_method=____（或：Sync 没有要求登录 / 看不到地址）
A3 doris-mcp 工具数：__；D1 doris-mcp-svc 工具数：__
权限：已按表设置（是 / 否，差异：）

「Doris 专家」问题 1：发送 hh:mm，__ s；工具：____；弹窗：__；424 / 报错：
「Doris 专家」问题 2：发送 hh:mm，__ s；工具：____；弹窗：__；424 / 报错：
「Doris 专家（svc）」问题 1：发送 hh:mm，__ s；工具：____；弹窗：__；424 / 报错：
「Doris 专家（svc）」问题 2：发送 hh:mm，__ s；工具：____；弹窗：__；424 / 报错：
其他观察：

答案全文（4 段；其中如有主机地址、IP、端口、账号等连接信息，换成 <已遮盖>）：
```

收到回复后，AI 会记下结束时间，再查审计日志、Gateway 耗时、连接回收和 CloudTrail，然后按 scope 的情况写结论（design v0.7）并提交。
