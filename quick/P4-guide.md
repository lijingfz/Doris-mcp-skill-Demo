# P4：Quick 桌面版接入 12 个工具 + 「Doris 专家」agent（T4.1 + T4.4）

> 本文件不包含任何 URL、secret 或 token。连接参数（MCP URL、Token URL、Authorize URL、client ID）见 `quick/T0.7-guide.md` 的「连接参数」。如果 Quick 要求重新填 client secret 或 demo 用户的密码，按 T0.7 的「Step 2：取 secret」在**你自己的终端**里获取，不要用 Claude Code 的 `!` 前缀。

## 注意

- 不要把 URL、secret、token 或登录页的地址粘贴到对话里。登录页地址里有 `state`、`code_challenge` 这类一次性参数，A2 只从中读三项。
- 遇到 424、报错或意料之外的权限弹窗：记下时间、工具名和错误信息原文（先把其中的地址去掉），然后继续往下做。同一个问题最多重试一次。
- 两个连接器、两个 agent 全部做完再回复我，预计 40–60 分钟。

## 准备

- 秒表（手机即可）和记事本。
- 记下这台电脑的时区（回复模板第一行），我按 UTC 对日志。
- Quick 桌面版已登录。

## Part A：同步 `doris-mcp`（User auth），设置工具权限

1. **Customize → Connectors**，打开 `doris-mcp` 的详情页。先看连接设置里有没有 scope 一栏：有就记下填的值，没有这一栏或者是空的就记「无」（A2 的 scope 是不是来自这里，要靠这一项区分）。然后点 **Sync**。
2. 如果弹出登录页，**先不要登录**。看浏览器地址栏，只记三项：
   - `scope=` 的值。`%20` 是空格，`%2F` 是 `/`，例如 `openid%20doris-mcp%2Finvoke` 就是 `openid doris-mcp/invoke`。地址里没有 `scope=` 就记「无」。
   - 有没有 `resource=`：只记「有」或「无」，不抄它的值。
   - `code_challenge_method=` 的值，例如 `S256`。

   记完再用 `demo` 用户登录。如果看不到地址栏（比如是应用内窗口），记「看不到地址」。
   Sync 没有弹出登录页（上次登录的 token 还有效时会这样）：看详情页有没有 Reconnect、Sign in again 这类重新授权的按钮，有就点一次，按上面的方法记三项；没有这类按钮，记「Sync 没有要求登录」，继续往下做。
3. 同步完成后，工具列表应该是 12 个，名字都以 `doris___` 开头，**没有** `doris___net_check`（P3 已经把 P0 的 spike 换成了完整的 server）。记下实际数量。数量不是 12，或者 Sync 失败：停下，把错误信息告诉我。
4. 逐个启用这 12 个工具（新同步的工具默认禁用），权限按下表设置（D7：P4 不是彩排，`execute_query` 用 Ask Each Time；`reload_semantic_layer` 始终 Ask Each Time）：

| 工具 | 权限 |
|---|---|
| `doris___get_query_guide` | Always Allow |
| `doris___check_service_health` | Always Allow |
| `doris___list_databases` | Always Allow |
| `doris___list_tables` | Always Allow |
| `doris___describe_table` | Always Allow |
| `doris___execute_query` | Ask Each Time |
| `doris___list_metrics` | Always Allow |
| `doris___list_dimensions_for_metric` | Always Allow |
| `doris___query_metric` | Always Allow |
| `doris___reload_semantic_layer` | Ask Each Time |
| `doris___list_recent_queries` | Always Allow |
| `doris___get_query_profile` | Always Allow |

## Part B：创建 agent「Doris 专家」

1. 新建一个自定义 agent，名称 `Doris 专家`。
2. 指令：把仓库里 `quick/agent-instructions.md` 的**全文**复制粘贴（约 1900 字符；可以在你自己的终端里 `cat quick/agent-instructions.md` 后复制，这个文件里没有 secret）。
3. 连接器只关联 `doris-mcp`，不挂 skills（skills 在 P5 加）。

## Part C：用「Doris 专家」跑「开场 + 第 2 幕」

新建一个对话，选 agent「Doris 专家」，依次问下面两个问题。每个问题记五项：

- 发送时间（本地时间 hh:mm）；
- 总耗时：按下发送时开始秒表，答案完整显示后停，记秒数；
- Quick 显示的工具调用顺序，例如 `list_metrics → query_metric → query_metric`；
- 权限弹窗：`doris___execute_query` 只在 SQL 是 SELECT、SHOW、DESCRIBE 或 EXPLAIN 时点允许，其他一律拒绝；`doris___reload_semantic_layer` 一律拒绝。记下弹了几次、你怎么选的；
- 424 或其他报错：记原文（去掉其中的地址）。

**问题 1（开场）**：`检查一下 Doris 连接状态`

- 期望：调用 `doris___check_service_health`，回答说明连接正常；不出现主机地址、IP、端口、账号。

**问题 2（第 2 幕）**：`今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比`

- 期望：先 `doris___list_metrics`，再 `doris___query_metric`（按月一次、按渠道一次，也可能合并或多一次）。每次工具调用约 10 s。
- 数字应该和下面的参照值一致（截至 2026-09-25，即演示设定的「今天」；回答里的小数位数可以不同，按它显示的位数对照即可）：

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

- 2026 年 9 月只到 25 日，而去年同期是 2025 年 9 月整月，所以 9 月同比偏低（-0.44%）。回答里应该指出这一点；没指出不算失败，记下即可。
- 合计行的同比和客单价如果回答里没有，不算失败。

## Part D：`doris-mcp-svc`（Service auth）+「Doris 专家（svc）」

1. 打开 `doris-mcp-svc` 的详情页，点 **Sync**（Service auth 不需要登录）。和 A3、A4 一样：确认 12 个 `doris___` 工具，全部启用，权限按同一张表设置。
2. 新建 agent `Doris 专家（svc）`：同样的指令全文；连接器只关联 `doris-mcp-svc`，不挂 skills。每个 agent 只关联一个连接器：两个连接器的工具同名，同时关联会出现重名工具。
3. 新建一个对话，选「Doris 专家（svc）」，按 Part C 把两个问题再问一遍，同样记五项。

## 回复模板

全部做完后，复制下面的模板，填好发给我。不要包含任何 URL、secret 或 token。

```
时区：
A1 连接器设置里的 scope：____（没有或为空记「无」）
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
