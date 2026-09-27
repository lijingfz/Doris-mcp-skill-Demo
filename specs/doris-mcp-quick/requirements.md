# 需求：Doris MCP on AgentCore × Amazon Quick 桌面版

> 版本 v1.4 · 2026-09-27 · 来源：`prepare/` 下 4 份材料 + 用户确认的决策（见文末）
> v1.4：R-32 补充说明审计记录的范围：只有执行到工具函数（`log_tool_call`）的调用才有审计记录，在此之前就失败的请求没有记录（见 design v0.5 §13、`plans/P3-deploy.md` T3.3）
> v1.3：R-26 验收细化为 11 个故事线对账用例、到分一致；R-42 验收接受 Doris 给每个用户默认列出的权限项，并写明写探针（见 design v0.4 §6.1、§6.3）
> v1.2：R-11（Local stdio 备份路径）按 D9 取消，备份路径改为 Service auth（R-13），R-13 的验收同步加严
> v1.1：R-23 的 summary 裁剪规则按真实 profile 实测加严（另外删除全 0 计数器、折叠逐列统计；见 design v0.2.2），并补充 api_text 的命中条件
> 句式采用 EARS：WHEN〈触发〉THE SYSTEM SHALL〈行为〉；「验收」一栏写可检验的标准。

## 1. 接入（Quick 桌面版）

| ID | 需求 | 验收 |
|---|---|---|
| R-10 | WHEN 用户在 Quick 桌面版里通过 **Cloud Connector（MCP，User auth：OAuth 授权码 + PKCE）** 提问，THE SYSTEM SHALL 经 AgentCore Gateway → Runtime 调用 Doris MCP 工具并返回结果。 | 桌面版能列出工具（名称形如 `doris___<tool>`），能调通 `check_service_health`，能完成 design §10 中「开场 + 第 2 幕」 |
| R-11 | ~~THE SYSTEM SHALL 提供不依赖 Cognito/Gateway 的备份路径：桌面版 **Local stdio** 连接器 → `mcp-proxy-for-aws`（SigV4）→ Runtime。~~ **已取消（D9）**：User auth、Service auth 在 P0 都已跑通，备份路径改为 Service auth（R-13）。 | —（`quick/local-connector.json` 保留作参考，不验收）|
| R-12 | THE SYSTEM SHALL 让工具定义满足 Quick 的限制：inputSchema 符合 JSON Schema Draft 7；每个连接器 ≤ 100 个工具；典型操作在 60 s 内完成。 | 离线测试用 Draft7Validator 检查 12 个工具；P3 实测冷启动 + 典型查询 < 60 s |
| R-13 | WHERE 需要机器身份（不需要用户登录）时，THE SYSTEM SHALL 支持 Cloud Connector 的 **Service auth**（client credentials）；它也是 User auth 的备份路径（D9）。 | P0 中 Service auth 至少连通一次（✅ T0.7）；P4 用 Service auth 连接器跑通 design §10 的「开场 + 第 2 幕」 |

## 2. 工具

| ID | 需求 | 验收 |
|---|---|---|
| R-20 | THE SYSTEM SHALL 暴露 12 个工具：upstream 的 10 个（`get_query_guide` `list_databases` `list_tables` `describe_table` `execute_query` `check_service_health` `list_metrics` `list_dimensions_for_metric` `query_metric` `reload_semantic_layer`）+ `list_recent_queries` + `get_query_profile`。 | `tools/list` 的工具名集合与此完全一致 |
| R-21 | THE SYSTEM SHALL 只读：SQL 校验器拒绝 DML/DDL/多语句/OUTFILE；Doris 账号本身没有写权限。 | upstream 校验器单测通过；P2 权限矩阵（写操作被 Doris 拒绝）|
| R-22 | WHEN 调用 `list_recent_queries(limit, user, sql_contains)`，THE SYSTEM SHALL 从 FE `/rest/v1/query_profile` 返回已采集 profile 的查询，按开始时间倒序，每条包含 query_id、user、default_db、start/end、total、state、SQL 前 200 字；支持按 user / sql_contains（在完整 SQL 中匹配，不区分大小写）过滤；`limit` 范围 1–100。WHERE `PROFILE_SCOPE=self`，只返回服务账号自己的查询。 | 单测（MockTransport）覆盖排序、过滤、scope、越界 limit |
| R-23 | WHEN 调用 `get_query_profile(query_id, mode, max_chars)`，THE SYSTEM SHALL：校验 query_id 格式（`^[0-9a-f]{16}-[0-9a-f]{16}$`）；先查 v2 `data.profile`，WHERE scope=all 时回退到 `/api/profile/text`（只有第一行是段落标题的纯文本才算命中，`query id <id> not found` 算未命中）；`summary` 模式去掉 DetailProfile 段、值为 N/A 或全 0 的计数器，并把 PhysicalPlan 的逐列统计折叠为一行标记；输出截断到 `max_chars`（1 000–200 000，默认 20 000）并标记 `truncated`。 | 单测覆盖两条获取路径、not-found 纯文本、summary 各条裁剪规则、截断；P1 实测真实 profile 的 summary < 20 000 字符（spec 阶段实测 9 109）|
| R-24 | IF profile 获取失败，THE SYSTEM SHALL 返回结构化结果，不抛异常：找不到 → `success` + `profile_found=false` + 证据；凭证错误（HTTP 200 + body `code:401`，或 HTTP 401/403）→ `UNAUTHENTICATED`；超时 → `QUERY_TIMEOUT`；网络或 FE 错误 → `CONNECTION_ERROR`；参数不合法 → `INVALID_PARAMS`。 | 每种情况都有单测；P1 实测非法 id、不存在的 id、错误密码三种 |
| R-25 | THE SYSTEM SHALL 支持「带 profile 执行」，且不修改 Doris 全局配置：`execute_query("SELECT /*+SET_VAR(enable_profile=true)*/ ... /* trace:<id> */")` → `list_recent_queries(sql_contains=<id>)` → `get_query_profile`。 | P1 E2E 脚本 `scripts/mcp_smoke.py flow` 跑通 |
| R-26 | THE SYSTEM SHALL 在 `ecom` workspace 提供语义指标（GMV、订单数、客单价、退款率等），且结果与故事线中的 SQL 一致。 | P2：经 MCP server（`mcp_svc`）调用 `query_metric`，11 个故事线对账用例（`doris/reconcile.py`）与对照 SQL 逐行一致：金额到分，比率误差 ≤ 1e-6；已发布的 22 个指标与本地模型一致 |

## 3. 运行时（AgentCore）

| ID | 需求 | 验收 |
|---|---|---|
| R-30 | THE SYSTEM SHALL 以 CodeZip / PYTHON_3_12 / protocol MCP / authorizer AWS_IAM / VPC 模式运行，监听 `0.0.0.0:8000/mcp`（stateless streamable HTTP），并提供 `GET /ping`。 | `agentcore status` 显示 READY；SigV4 冒烟通过 |
| R-31 | THE SYSTEM SHALL 在启动时从 Secrets Manager（`DORIS_SECRET_ID`）读取 Doris 服务账号；只有未设置 `DORIS_SECRET_ID` 时才读 `DORIS_PASSWORD`（仅本地开发用）。 | `agentcore.json` 和 git 历史里没有明文密码；单测覆盖两种来源 |
| R-32 | THE SYSTEM SHALL 把服务日志和审计日志（`doris_new_mcp.audit`）写到 stderr，从而进入 CloudWatch Logs。 | P3：CloudWatch 能看到每次工具调用的审计记录。v1.4 说明：审计记录由工具函数里的 `log_tool_call` 写出，所以请求在工具函数之前就失败时（例如 MCP 协议错误、参数校验失败、连接池拿不到连接、语义层重新加载期间返回的 `SERVICE_NOT_READY`）没有审计记录；P3 只验收执行到工具函数的调用。是否在 P5 补上这类记录由用户决定 |
| R-33 | THE SYSTEM SHALL 把 workspace 目录放在可写路径（默认 `$TMPDIR/doris-mcp-workspace`，可用 `DORIS_MCP_WORKSPACE_DIR` 覆盖），因为 `/var/task` 只读。 | 单测：自定义目录下会创建 `workspaces/` 和 `logs/` |
| R-34 | THE SYSTEM SHALL 把 SQL 超时设为 50 s、FE HTTP 超时设为 15 s，保证不超过 Quick 的 60 s 上限。 | 配置文件 + 单测 |
| R-35 | THE SYSTEM SHALL 使用单一 Doris 服务账号 `mcp_svc` 访问 Doris（SQL 与 FE HTTP 都用它），入站鉴权交给 Runtime IAM / Gateway JWT。 | 单测：service 模式下所有连接池都用服务账号 |

## 4. 安全

| ID | 需求 | 验收 |
|---|---|---|
| R-40 | THE SYSTEM SHALL NOT 在任何安全组中出现 `0.0.0.0/0` 入站规则；新增规则只用 SG 引用（或 `/32`）。`doris-demo-sg` 现有规则保持不变。 | `infra/10-network.sh` 结束时自检；P3 审查 |
| R-41 | THE SYSTEM SHALL 按具体资源 ARN 授予 IAM 权限（Runtime 执行角色、Gateway 服务角色、本机 proxy 用户）。 | 策略 JSON 审查 |
| R-42 | `mcp_svc` SHALL 只有 `SELECT_PRIV ON internal.ecom.*` 和 `SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.*`，没有 ADMIN/LOAD/ALTER/DROP。 | P2 权限矩阵（`doris/permission_matrix.py`）：`SHOW GRANTS` 恰好是这两项，外加 Doris 给每个用户默认列出的 `internal.information_schema`、`internal.mysql` 的 Select_priv 和 workload group `normal` 的 Usage_priv（v1.3 接受，不算多出的权限）；upstream store 初始化成功；LOAD / CREATE / DROP / GRANT / ADMIN 写探针全部被拒 |
| R-43 | 仓库 SHALL NOT 包含任何明文凭证。 | 每次提交前 `scripts/check-secrets.sh` 返回 OK |
| R-44 | WHEN 某个操作会创建或修改 AWS 资源、Doris 账号或安全组，THE SYSTEM（Claude）SHALL 先展示命令并等待用户确认。 | tasks.md 中所有 `[AI+GATE]` 任务的日志里都有「用户确认」记录 |

## 5. Skills 与演示

| ID | 需求 | 验收 |
|---|---|---|
| R-50 | THE SYSTEM SHALL 在桌面版导入 apache/doris-skills（`doris-debug`、`doris-profile-reader`、`doris-best-practices`、`doris-architecture-advisor`）以及自写的 `doris-mcp-adapter`（把 doriscli 调用翻译成 MCP 工具）。 | 桌面版 Skills 列表里能看到；adapter 被自动选中 |
| R-51 | THE SYSTEM SHALL 支撑 design §10 的完整演示：Track A（慢查询 → profile → 解读）和 Track B（DDL 评审 → 推荐 DDL，由人工执行）端到端完成，除执行 DDL 外无需人工干预。 | 完整彩排 2 次，记录每一步耗时 |

## 6. 可恢复性（过程需求）

| ID | 需求 | 验收 |
|---|---|---|
| R-60 | 所有进度状态 SHALL 保存在仓库里（spec + progress.md + `infra/state.env` + git 提交），新会话读完 `CLAUDE.md` 就能继续。 | 每个完成的任务都有对应的 commit 和日志条目 |
| R-61 | `infra/*.sh` SHALL 可以重复执行（已存在就跳过），并且默认只 dry-run。 | 对已创建的资源重复执行，不会创建出第二份 |

---

## 已定决策（2026-09-26 用户确认）

| # | 决策 | 结论 |
|---|---|---|
| D1 | Doris 身份模型 | **单服务账号 `mcp_svc`**。所有 MCP 调用在 Doris 里都显示为 `mcp_svc`（集成说明中「沿用调用方身份」不再适用）|
| D2 | Quick 订阅层级 | **Enterprise**，满足 Cloud MCP 连接器的前提，主路径 ① 可以走 |
| D3 | Quick 鉴权方式 | **User auth**（OAuth 授权码 + PKCE，client A）；Service auth（client B）作为备选并在 P0 验证 |
| D4 | profile 可见范围 | 演示用 **all**，通过 `PROFILE_SCOPE` 切换；设为 `self` 时关闭跨用户回退 |
| D5 | profile 采集方式 | **只用 `SET_VAR` hint**，不修改 Doris 全局配置 |
| D6 | `mcp_svc` 的 host | 先用 `'%'`（由 SG 控制网络边界），P3 之后收紧为 `'172.31.%'` |
| D7 | `execute_query` 权限 | 彩排和演示时设为 **Always Allow**，平时用 Ask Each Time |
| D8 | 代码仓 | 本地 `git init`，是否推送由用户决定（2026-09-27 用户决定推送到**私有**仓库 `lijingfz/Doris-mcp-skill-Demo`，remote `origin`；以后每次 push 仍需用户确认）|
| D9 | 备份路径（P0 之后，2026-09-26）| User auth、Service auth 在 P0 都已跑通，**不做 Local stdio**（取消 R-11），备份路径改为 Cloud Connector + **Service auth**（client B）|
