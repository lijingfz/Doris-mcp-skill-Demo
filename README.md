# Doris MCP on AgentCore × Amazon Quick 桌面版

把 upstream 的 Doris MCP server（`velodb-mcp-server`）打上补丁，部署到 **Amazon Bedrock AgentCore Runtime**，经 **AgentCore Gateway** 暴露给 **Amazon Quick 桌面版**（Enterprise），在一套真实的 Doris 电商演示库上演示：语义层问答、业务排查、Query Profile 诊断和建表评审。

> 本文件不含 URL、IP、ARN、账号 ID、资源 ID 或 secret。资源 ID 一律「见 `infra/state.env`」；Quick 连接参数见 `quick/T0.7-guide.md`（里面有 URL，不要贴到对话或文档里）。
> 本文是总入口，讲清楚整个系统；细节在各个专门的文件里，见[文档索引](#12-文档索引)。

## 目录

1. [项目简介](#1-项目简介)
2. [架构](#2-架构)
3. [目录结构](#3-目录结构)
4. [工作原理](#4-工作原理)
5. [使用方法](#5-使用方法)
6. [测试原理](#6-测试原理)
7. [安全设计](#7-安全设计)
8. [资源保留期间的注意事项与成本](#8-资源保留期间的注意事项与成本)
9. [清理（以后由用户执行）](#9-清理以后由用户执行)
10. [已知限制与注意事项](#10-已知限制与注意事项)
11. [开发方式与断点恢复](#11-开发方式与断点恢复)
12. [文档索引](#12-文档索引)

---

## 1. 项目简介

### 1.1 演示的是什么

| 层 | 本项目用的东西 |
|---|---|
| MCP server | upstream `velodb/velodb-mcp-server` @ `f235832`（Apache License 2.0），vendored 到 `mcp-server/`，加 11 个补丁（P-01…P-11）和一个 query_id 修正 |
| 托管 | AgentCore Runtime `dorismcp_dorismcp`：CodeZip、Python 3.12、MCP 协议、VPC 模式 |
| 暴露 | AgentCore Gateway `doris-mcp-gw`：入站 Cognito JWT，出站 IAM SigV4 |
| 客户端 | Amazon Quick 桌面版（Enterprise）：Cloud Connector + agent「Doris 专家」+ 5 个 skill |
| 数据 | Doris 4.1.4 单节点（EC2），电商演示库 `ecom`，语义层 workspace `ecom` |

范围之外（design §1）：MCP 写路径（DDL / DML 由人执行）、多用户 Doris 身份透传、生产级高可用。

### 1.2 演示故事

故事线是「中秋节的一天」：设定今天是 2026-09-25 12:00。流程和参照值在 `quick/runbook.md`（英文 `quick/runbook.en.md`）和 `quick/P5-guide.md` Part B。原则是「写 = 人工，读 = MCP」：第 1 幕的 Stream Load 实时写入和第 7 幕建 MV 由演示者在 Quick 之外执行。

| 步骤 | 段落 | 问题（原样复制） | 看点 |
|---|---|---|---|
| — | 第 1 幕 | （人工 Stream Load，不经过 MCP） | 写 = 人工 |
| 1 | 开场 | `检查一下 Doris 连接状态` | 连接正常；回答里没有主机地址和账号 |
| 2 | 第 2 幕 经营大盘 | `今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比` | 语义层；9 月只到 25 日，按同天数比 +21.87%；小程序占比 32.30% |
| 3 | 第 3 幕 大促复盘 | `618 和双 11 哪个类目贡献最大？` | 618 家用电器第一（30.52%），双 11 手机数码第一（26.04%）；活动期来自 `dim_promotion` |
| 4 | 第 5 幕 问题排查 | `最近哪家店的退款率异常？原因是什么？物流有没有问题？` | 深圳极速数码配件专营店；差评「发烫」「充不进电」（倒排索引）；极兔发西北的干线慢 |
| 5 | 第 7 幕 + Track A | `按天统计埋点 UV 这个查询为什么要这么久？给出 profile 证据` | 带 profile 执行 → 按 trace 找 query_id → 读 profile；Doris 里只要几十毫秒 |
| — | 第 7 幕 | （人工建 MV，不经过 MCP） | 写 = 人工 |
| 6 | Track B 设计评审 | `评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL` | 135 个按天分区 × 2 个桶 = 270 个小 tablet；DDL 只给出，不执行 |
| 7 | 收尾 | `为 agg_daily_traffic 这类场景推荐数据模型` | 聚合模型 + BITMAP_UNION / HLL_UNION；DDL 由人工执行 |

### 1.3 当前状态（2026-09-30）

| 项 | 状态 |
|---|---|
| 阶段 | P0–P5 的开发和演示准备都已完成；只剩 T5.6（`plans/P5-skills.md` Task 9，清理）没做 |
| Runtime | `dorismcp_dorismcp` version 4（带 query_id 修正，`demo-check pre` 10/10） |
| 彩排 | 第 1 轮已完成（英文提问，每步耗时见 `quick/runbook.md`「每步耗时」）；第 2 轮按用户决定跳过 |
| AWS 资源 | **保留**：用户 2026-09-30 决定以后还要用，不再做测试和演示检查 |
| 清理 | Task 9 推迟，以后由用户自己执行（见[第 9 节](#9-清理以后由用户执行)） |
| git | `p5-skills` 已在本地快进合并到 `main`，没有推送（D8：推送由用户决定） |

---

## 2. 架构

### 2.1 总览

```
 +----------------------------------+   (1) sign in, get token     +-----------------------------+
 | Amazon Quick desktop (Enterprise)| ---------------------------> | Cognito user pool           |
 |   agent + 5 skills               |   client A: code + PKCE      |   doris-mcp-quick           |
 |   Cloud Connector                | <--------------------------- |   scope doris-mcp/invoke    |
 |     Doris-Desktop-MCP (User auth)|   access token (JWT)         +-----------------------------+
 +----------------+-----------------+
                  | (2) HTTPS, MCP streamable HTTP, Bearer JWT
                  v
 +----------------------------------+
 | AgentCore Gateway doris-mcp-gw   |   inbound  CUSTOM_JWT (clients A + B, allowedScopes)
 |   target doris -> doris___*      |   outbound GATEWAY_IAM_ROLE = doris-mcp-gateway-role
 +----------------+-----------------+
                  | (3) InvokeAgentRuntime, SigV4
 =================|=============== VPC (the one Doris runs in) =================================
                  v
 +----------------------------------+  (5) 443   +------------------------------------+
 | AgentCore Runtime                | ---------> | VPC endpoints (SG doris-mcp-vpce)  |
 |   dorismcp_dorismcp, version 4   |            |   secretsmanager  Interface        | --> Secrets Manager
 |   CodeZip, Python 3.12, MCP      |            |   logs            Interface        |       doris-mcp/mcp_svc
 |   inbound AWS_IAM, 3 subnets     |            |   S3              Gateway (free)   | --> CloudWatch Logs
 |   SG doris-mcp-rt (no ingress)   |            +------------------------------------+       audit + app logs
 +----------------+-----------------+
                  | (4) MySQL 9030 + FE HTTP 8030 (SG reference only)
                  v
 +----------------------------------+
 | Doris 4.1.4, single node (EC2)   |
 |   SG doris-demo-sg               |
 |   db ecom (data)                 |
 |   db system_mcp (semantic store) |
 +----------------------------------+
 ==============================================================================================
```

备份路径：连接器 `doris-mcp-svc`（Service auth，client B，client_credentials）接同一个 Gateway，配给备份 agent「Doris 专家（svc）」，在网页版使用（D9）。

### 2.2 组件

| 组件（仓库里的名字） | 作用 | 谁创建 |
|---|---|---|
| agent「Doris 专家」 | 演示入口；指令 = `quick/agent-instructions.md` 全文；只关联 `Doris-Desktop-MCP` | 人工，`quick/P4-guide.md` Part B、`quick/P5-guide.md` A2 |
| 连接器 `Doris-Desktop-MCP` / `doris-mcp-svc` | Quick 的 Cloud Connector（MCP + OAuth），User auth / Service auth | 人工，`quick/T0.7-guide.md`、`quick/P4-guide.md` |
| 5 个 skill | `quick/skills/` 下的 5 个文件夹 | 人工导入，`quick/P5-guide.md` A1 |
| Cognito user pool `doris-mcp-quick` | hosted UI 域名、resource server `doris-mcp`（scope `invoke`）、client A `quick-user`、client B `quick-service`、用户 `demo` | `infra/20-cognito.sh` |
| secret `doris-mcp/cognito-demo-user` | `demo` 用户的密码 | `infra/20-cognito.sh` |
| Gateway `doris-mcp-gw` + target `doris` | 校验 JWT，按 `<target>___<tool>` 命名工具，SigV4 调用 Runtime | `infra/30-gateway.sh` |
| IAM 角色 `doris-mcp-gateway-role` | 只能对这一个 Runtime 调用 `InvokeAgentRuntime` | `infra/30-gateway.sh` |
| Runtime `dorismcp_dorismcp`（栈 `AgentCore-dorismcp-default`） | 跑 `mcp-server/`，12 个工具 | `agentcore deploy`（在 `dorismcp/` 里），配置由 `scripts/render-agentcore.py` 生成；`infra/25-runtime-state.sh` 把 ID 记进 `state.env` |
| IAM 角色 `doris-mcp-runtime-role` | Runtime 的执行角色：只能写自己的日志组、只能读一个 secret | `infra/35-runtime-role.sh` |
| SG `doris-mcp-rt`、`doris-mcp-vpce`；`doris-demo-sg` 上 2 条规则 | 网络边界（见 2.4） | `infra/10-network.sh` |
| VPC endpoints：S3（Gateway 型）、logs、secretsmanager（Interface 型） | Runtime 的 ENI 只有私网地址，靠它们访问 AWS 服务 | `infra/10-network.sh` |
| secret `doris-mcp/mcp_svc` | Doris 服务账号的用户名和密码 | `infra/40-doris-secret.sh` |
| Doris 账号 `mcp_svc` | MCP 在 Doris 里的唯一身份（D1） | `doris/apply-admin-sql.sh` + `doris/01_mcp_user.sql` / `02_mcp_user_vpc.sql`（人工 GATE） |
| 库 `system_mcp` | 语义层存储（3 张表） | `doris/publish-semantic.sh`（人工 GATE） |
| Doris EC2、`doris-demo-sg`、VPC、库 `ecom`、账号 `demo_ro` | 项目之前就有 | — |
| 日志组 `/aws/bedrock-agentcore/runtimes/<RUNTIME_ID>-DEFAULT` | Runtime 的 stdout / stderr，含审计记录 | 平台自动创建 |

### 2.3 一次工具调用的全过程

以第 2 幕里的一次 `doris___query_metric` 为例：

1. **取 token。** 连接器用 User auth 时，Quick 走 Cognito hosted UI，用户以 `demo` 登录（client A，授权码 + PKCE），拿到带 `doris-mcp/invoke` scope 的 access token，由 Quick 自动续期。Service auth 用 client B 的 client_credentials。开发机上手工检查用 `scripts/get-gw-token.sh`（client B，见 5.4）。
2. **Gateway 校验 JWT。** 请求带 `Authorization: Bearer <JWT>` 发到 Gateway 的 MCP 地址。Gateway 的入站授权是 CUSTOM_JWT：Cognito 的 discovery URL、允许的 client（A 和 B）、`allowedScopes`（`doris-mcp/invoke`，它也会写进 Gateway 的 PRM）。`tools/list` 直接由 Gateway 从同步过的工具目录回答（约 1.6 s），不调用 Runtime。
3. **Gateway 调 Runtime。** target `doris` 的出站凭证是 `GATEWAY_IAM_ROLE`：Gateway 扮演 `doris-mcp-gateway-role`，用 SigV4 对 Runtime 调用 `InvokeAgentRuntime`。Runtime 的入站授权是 AWS_IAM。Runtime 收到的是不带 `doris___` 前缀的工具名（审计记录里的工具名也不带）。Gateway 不向客户端返回 `Mcp-Session-Id`，每个 `tools/call` 都落在一个新的 microVM 上，都是一次冷启动（完整的 server 约 5–10 s）。
4. **启动 server、取凭证。** 入口 `mcp-server/mcp_server.py` → `agentcore_ext.app.main`。`load_settings` 读环境变量（`DORIS_HOST`、`DORIS_PORT` 9030、`DORIS_HTTP_PORT` 8030、`DORIS_SECRET_ID` = `doris-mcp/mcp_svc`、`PROFILE_SCOPE` = `all`），经 secretsmanager endpoint 读 secret；执行角色只允许读这一个 secret。密码只在进程内存里。
5. **连 Doris。** FastMCP 在 8000 端口的 `/mcp` 提供 streamable HTTP（`stateless_http=True`），另有 `GET /ping` 给平台做健康检查。SQL 类工具用 `mcp_svc` 的连接池走 MySQL 协议 9030（池最多 5 个连接，每个连接 `SET wait_timeout = 600`，SQL 超时 50 s，最多返回 2000 行）；profile 工具走 FE HTTP 8030（超时 15 s）；语义层工具从 `system_mcp` 读模型，经 MetricFlow 编译成 SQL 再执行。
6. **写审计。** 每次工具调用在 logger `doris_new_mcp.audit` 下写一条 JSON（工具名、client_id、经 `mask_sensitive` 的参数、成败、耗时、`query_path`，失败时还有 `error`），和应用日志一起写 stderr，经 logs endpoint 进 CloudWatch Logs。没有挂 upstream 的 `RequestLoggerMiddleware`（它会记录请求体）。
7. **返回。** 结果原路返回 Runtime → Gateway → Quick。Quick 对每次 MCP 操作最多等 60 s，超过就报 HTTP 424。

### 2.4 网络与安全组

**为什么 Runtime 放在 VPC 里：** Doris 和 Runtime 在同一个 VPC，Runtime 走私网直连 Doris，`doris-demo-sg` 只需要放行「来源 = `doris-mcp-rt`」这一个 SG 引用，Doris 不用对外开放任何端口。

| SG | 入站 | 出站 |
|---|---|---|
| `doris-mcp-rt`（Runtime 的 ENI） | 无 | 只有 4 条：9030 / 8030 → `doris-demo-sg`；443 → `doris-mcp-vpce`；443 → S3 prefix list |
| `doris-mcp-vpce`（Interface endpoints） | 443，来源只有 `doris-mcp-rt` | 无 |
| `doris-demo-sg`（Doris，已有） | 本项目新增 2 条：9030、8030，来源 = `doris-mcp-rt`（SG 引用，不写 CIDR）。另有一条已有的 `/32` 规则（开发机，端口 22 / 8030 / 9030），不动 | 不改 |

- 规则只用 SG 引用或 `/32`，任何 SG 都不允许出现对任意来源开放的入站规则；`infra/10-network.sh` 执行后会自检。
- DNS 不需要出站规则。
- Runtime 的 ENI 只有私网地址，VPC 里也没有 NAT：没有 endpoints 时冷启动会在约 30 s 后超时，而且没有任何日志。所以 S3（拉 CodeZip）、logs、secretsmanager 三个 endpoint 都是必需的。
- Interface endpoint 开了私有 DNS，会影响整个 VPC 的解析；VPC 里唯一的 EC2 是 Doris，它没有 instance profile。
- 同一 VPC 里有 4 个 `launch-wizard-*` SG，带对任意来源开放的入站规则，但没挂在任何 ENI 上，也不属于本系统；是否清理由用户决定。

### 2.5 身份与账号

| 身份 | 用在哪 | 权限 / 说明 |
|---|---|---|
| Cognito client A `quick-user` | 连接器 `Doris-Desktop-MCP`（User auth） | 授权码 + PKCE，带 client secret，scope `openid doris-mcp/invoke`；用户 `demo`（只能由管理员建用户） |
| Cognito client B `quick-service` | 连接器 `doris-mcp-svc`（Service auth）、开发机冒烟 | client_credentials，scope `doris-mcp/invoke` |
| `doris-mcp-gateway-role` | Gateway → Runtime | 只能 `InvokeAgentRuntime` 这一个 Runtime；trust 限定本账号 |
| `doris-mcp-runtime-role` | Runtime 执行角色 | 只能写 `runtimes/dorismcp_dorismcp-*` 日志组（外加 DescribeLogGroups），只能 `GetSecretValue` 这一个 secret（AWS 托管密钥，不需要 kms）；替换了 CDK 默认生成的、带 Bedrock / X-Ray 通配权限的角色 |
| Doris `mcp_svc` | 所有 MCP 调用（D1） | `ecom` 上 SELECT_PRIV；`system_mcp` 上 SELECT_PRIV 和 CREATE_PRIV（只为 upstream 的 `CREATE … IF NOT EXISTS`）；外加 Doris 默认项。没有 ADMIN、LOAD、ALTER、DROP。host 只允许 VPC 私网网段（P3 收紧，见 5.10） |
| Doris `demo_ro` | 开发机只读：本地起 server、对账的参照 SQL | SELECT on `ecom`、`information_schema`、`mysql` |
| Doris root | 只由人工 GATE 脚本使用：建账号、发布语义层 | 凭证只在项目外的 `credentials.env` |

**只读是设计出来的，不是约定：**

- MCP 的 SQL 校验器在发往 Doris 之前拒绝 DDL / DML 和 `SET`（`flow` 里 `DELETE … WHERE 1 = 0` 被拒就是这个检查）；
- 即使漏过，`mcp_svc` 在 Doris 里也没有写权限（P2 权限矩阵：9 个写探针全部被拒）；
- agent 指令第 2 条要求只读，要建表、改表时只给出 DDL；
- 写操作（Stream Load、建 MV、执行推荐的 DDL）一律由人工在 Quick 之外执行。

### 2.6 可观测性

| 看什么 | 在哪 | 用什么看 |
|---|---|---|
| 每次工具调用（成败、耗时、失败原因） | 日志组 `/aws/bedrock-agentcore/runtimes/<RUNTIME_ID>-DEFAULT`，过滤 `"doris_new_mcp.audit"` | `scripts/audit_check.py`（`demo-check.sh post` 会调用） |
| Quick 实际等了多久 | CloudWatch 上 Gateway 的 InvokeGateway Latency（按分钟、按工具） | `scripts/gw_latency.py`（`demo-check.sh post` 会调用） |
| Runtime 状态 / 版本 | AgentCore 控制面 | `bash infra/25-runtime-state.sh 2>&1 \| grep -E 'runtime dorismcp\|WARN\|FATAL'`（其余行含 ARN / URL，见 5.6） |
| Doris 连接数、空闲时长 | `SHOW PROCESSLIST`（`mcp_svc` 只看得到自己的会话） | `mcp_smoke.py conns` |

审计记录保留 SQL，但经过 upstream 的 `sensitive_mask`（遮密码和 token）。部署前在 `~/.agentcore/config.json` 设了 `"disableTransactionSearch": true`；账号的 X-Ray 索引规则 `Default` 是 100%，按用户决定保持不变。

### 2.7 为什么这样设计

| 选择 | 原因（design §0 / §2 / §3，requirements 的 D1–D9） |
|---|---|
| vendoring upstream + 小补丁，按补丁分 commit | 升级时可以重放补丁；没设服务凭证时 P-02 / P-03 / P-04 / P-09 的行为和 upstream 完全一样 |
| CodeZip，不用 Dockerfile | 不需要 ECR，也就少 2 个 VPC endpoint |
| 单个 Cognito 池（只在 Quick → Gateway 这一段），Gateway → Runtime 用 IAM SigV4 | Gateway 的 MCP target 支持 IAM 出站；两条入口（Gateway 服务角色、开发机冒烟）都能 SigV4，所以 Runtime 用 AWS_IAM |
| Runtime ARN 不变 | P0 先把最小 spike 部署为 `dorismcp`，P3 只换 `codeLocation`；P0 建好的 Gateway target 和 IAM 策略直接沿用 |
| D1 单服务账号 `mcp_svc` | 鉴权已在 AgentCore 前面做过，请求里没有 Doris 用户名密码；所有 MCP 调用在 Doris 里都显示为 `mcp_svc` |
| D2 Quick Enterprise | Cloud MCP 连接器的前提 |
| D3 User auth 为主，Service auth 为备 | 主路径是用户登录；两种都在 P0 跑通 |
| D4 profile 可见范围 `all` | 演示时要看到别的会话的 profile；`PROFILE_SCOPE=self` 可以关掉跨用户回退 |
| D5 只用 `SET_VAR` hint 采 profile | 不改 Doris 全局配置 |
| D6 `mcp_svc` 的 host 先 `'%'`，P3 后收紧为 VPC 私网网段 | P2 要从开发机（经 Doris 公网地址）以 `mcp_svc` 联调，开发机不在 VPC 网段里；网络边界先由 SG 控制，P3 Runtime 接上后再收紧 |
| D7 `execute_query` 权限 | 彩排和演示时 Always Allow（省掉每次确认），平时 Ask Each Time |
| D8 git | 本地仓库；远程是私有仓库，每次推送都要用户确认 |
| D9 不做 Local stdio | User auth、Service auth 都已跑通，备份改为 Cloud Connector + Service auth |
| skills 原生导入 + 自写 adapter | 桌面版的 skill 就是「文件夹 + `SKILL.md`」；upstream skills 是按 `doriscli` 写的，需要一层翻译 |

---

## 3. 目录结构

```
.
├── README.md                 本文
├── CLAUDE.md                 给 Claude 的恢复协议和硬性规则
├── RESUME.md                 给人看的「下次如何继续」
├── .env.example              环境变量名（没有值）
├── specs/doris-mcp-quick/    spec：requirements / design / tasks / progress / plans/P0–P5
├── mcp-server/               vendored upstream + 补丁 = Runtime 的 codeLocation
│   ├── mcp_server.py         AgentCore 入口（P-01）
│   ├── src/agentcore_ext/    settings.py、app.py（P-01）
│   ├── src/tools/profile.py  两个 profile 工具（P-05）
│   ├── config/mcp-server.toml  运行参数（P-06、P-09）
│   ├── pyproject.toml        锁定的依赖（P-07）
│   ├── UPSTREAM.md           upstream 来源、补丁表、升级步骤
│   └── test/                 upstream 测试 + test_agentcore_*.py（P-08）
├── dorismcp/                 agentcore CLI 项目（agentcore/agentcore.json 由脚本生成，含私网地址）
├── infra/                    幂等 AWS CLI 脚本（默认 dry-run）、lib.sh、policies/、state.env、test/
├── doris/                    Doris 账号 SQL、语义层模型和发布、对账、权限矩阵、test/
│   └── semantic/ecom/        语义层 YAML（10 个文件）
├── quick/                    Quick 侧：指南、手册、agent 指令、skills、test/
│   └── skills/               自写 doris-mcp-adapter + 4 个 upstream 副本（共 120 个文件）
├── scripts/                  开发机工具：冒烟、耗时、审计、token、预检、生成、secret 检查、test/
├── spike/p0-mcp/             P0 的最小 MCP server（net_check），P0 时的 codeLocation
├── prepare/                  原始材料：不要修改
└── .venv/                    本地开发 venv（不提交）
```

- `prepare/` 是项目开始时的原始材料（方案报告、旧代码等），只读，不要修改。
- `.venv/` 放在仓库根目录，在 codeLocation（`mcp-server/`）之外，所以不会被打进 CodeZip。CodeZip 由 agentcore CLI 在 `dorismcp/agentcore/.cache/<runtime>/staging` 里单独构建。
- `quick/local-connector.json`、`scripts/render-local-connector.py`、`infra/policies/local-proxy.json` 是已取消的 Local stdio 路径（D9）留下的文件。

---

## 4. 工作原理

### 4.1 MCP server 与补丁

upstream `velodb-mcp-server` @ `f235832`（tag `velodb-mcp-server-0.3.0`）先原样提交，之后按补丁分 commit（个别补丁合在同一个 commit 里，见 `git log --oneline -- mcp-server`）。FastMCP 3.4.4；只挂 CharsetMiddleware。补丁表的英文原版在 `mcp-server/UPSTREAM.md`，设计在 design §5.2。

| 补丁 | 文件 | 改了什么 |
|---|---|---|
| P-01 | `mcp_server.py`、`src/agentcore_ext/`（新） | AgentCore 入口：`load_settings`（`DORIS_SECRET_ID` 优先于 `DORIS_PASSWORD`）、`build_server`（`create_server` → 注册 profile 工具 → `/ping`）、root 和审计 logger 写 stderr |
| P-02 | `src/config/loader.py` | `ClusterConfig.fe_http_port`（8030） |
| P-03 | `src/store/store.py`、`src/store/bootstrap.py` | 进程级服务凭证，作为语义层存储的后备（`get_effective_credentials`） |
| P-04 | `src/server.py` | `create_server(service_credentials=, workspace_dir=)`：不做 MCP 鉴权（`auth=None`），只用一个服务账号连接池 |
| P-05 | `src/tools/profile.py`（新） | `list_recent_queries`、`get_query_profile`（见 4.3） |
| P-06 | `config/mcp-server.toml`（新） | SQL 超时 50 s、连接池 5、最多 2000 行、FE HTTP 8030 |
| P-07 | `pyproject.toml`（新） | 依赖锁到 upstream 的 `uv.lock`，加 boto3 和 5 个传递依赖（botocore、caio、platformdirs、rich-rst、sse-starlette），让 CodeZip 和测试过的 `.venv` 一致 |
| P-08 | `test/test_agentcore_*.py`（新） | 补丁的测试 |
| P-09 | `loader.py`、`src/core/connection.py`、toml | 每个池连接执行 `SET wait_timeout`（`session_wait_timeout_seconds = 600`，必须大于 `pool_idle_timeout` 300）。microVM 回收后留下的连接由 Doris 清掉；否则它们会空闲 8 小时，耗尽 `mcp_svc` 的 `max_user_connections`（100） |
| P-10 | `src/server.py` | 失败的 `execute_query` / `query_metric` 的审计记录带 `error`（`CODE: message`，300 字符，经 mask）；`query_metric` 的审计记下解析后的 where、having、order_by、limit |
| P-11 | `src/store/compiler.py` | `_extract_time_constraints` 修正 metric_time 过滤（见 4.5） |
| query_id 修正 | `src/tools/profile.py`（`78d653f`） | query_id 每段接受 1–16 位十六进制（`^[0-9a-f]{1,16}-[0-9a-f]{1,16}$`）。Doris 用 `Long.toHexString` 打印，前导 0 会省略；原来要求正好 16-16，约八分之一的真实 id 被拒（在 `demo-check pre` 里发现）。随 Runtime version 4 上线 |

只有 P-02、P-03、P-04、P-09、P-10、P-11 改 upstream 文件。P-10、P-11 有意改变 upstream 行为（审计内容、metric_time 过滤）。升级 upstream 的步骤见 `mcp-server/UPSTREAM.md`「Upgrading upstream」。

Runtime 的版本：version 1 是 P0 的 spike，2 是 P3 换成 `mcp-server/`，3 是 P5 上线 P-10 / P-11，4 是 query_id 修正。

### 4.2 12 个工具

经 Gateway 后，工具名是 `<target>___<tool>`，target 叫 `doris`，所以 Quick 看到的是 `doris___` 前缀（三个下划线）。Runtime 和审计记录里是不带前缀的名字。`quick/test/test_p5_docs.py` 的 `GATEWAY_PREFIX` / `_gateway_tools()` 用这 12 个名字检查文档。

| 工具（Quick 里的名字） | 作用 | 演示时的权限（D7） |
|---|---|---|
| `doris___get_query_guide` | 查询工作流指南（健康检查、用语义层还是直接 SQL 等），对话里第一次查数前调用一次 | Always Allow |
| `doris___check_service_health` | Doris 连接和服务状态 | Always Allow |
| `doris___list_databases` | 列库 | Always Allow |
| `doris___list_tables` | 列表 | Always Allow |
| `doris___describe_table` | 表结构 | Always Allow |
| `doris___execute_query` | 只读 SQL（SELECT / SHOW / DESCRIBE / EXPLAIN） | 演示时 Always Allow，平时 Ask Each Time |
| `doris___list_metrics` | 语义层指标 | Always Allow |
| `doris___list_dimensions_for_metric` | 某个指标可用的维度 | Always Allow |
| `doris___query_metric` | 按指标 + 维度 + 过滤查询（MetricFlow 编译） | Always Allow |
| `doris___reload_semantic_layer` | 重新加载语义层 | Ask Each Time，弹窗一律拒绝 |
| `doris___list_recent_queries` | 最近的查询（找 query_id） | Always Allow |
| `doris___get_query_profile` | 读一条查询的 profile | Always Allow |

`reload_semantic_layer` 不需要：语义层版本变化时，server 在查询前会自动重新加载（`ensure_fresh`）。

### 4.3 profile 工具（design §5.3）

按 Doris 4.1.4 的实测重写（原来的 `prepare/profile.py` 有 6 处和真实 API 不符）。FE 访问封装在 `FeHttpTarget`（超时 15 s）。

| 工具 | 做法 |
|---|---|
| `list_recent_queries` | GET `/rest/v1/query_profile`（v2 的 query_info 对非 admin 返回空行）；`limit` 1–100；`user` 精确匹配；`sql_contains` 不区分大小写；`scope=self` 时强制只看自己 |
| `get_query_profile` | 先试 v2 `/rest/v2/manager/query/profile/text/{qid}` 的 `data.profile`，`scope=all` 时再试 `/api/profile/text`；都没有就返回 `profile_found=false`。`mode` = `summary` / `full`；`max_chars` 1000–200000，默认 20000 |

- `summary` 去掉 DetailProfile 段、N/A 和全 0 的计数器，折叠列统计：一份真实 profile 从 103,487 字符降到 9,109 字符。
- 错误码：401 / 403（或 body 里 code 401）→ `UNAUTHENTICATED`；超时 → `QUERY_TIMEOUT`；其他 → `CONNECTION_ERROR`；参数不合法 → `INVALID_PARAMS`。
- **怎么拿到一条查询的 profile：** `execute_query` 执行 `SELECT /*+SET_VAR(enable_profile=true)*/ … /* trace:X */` → `list_recent_queries(sql_contains=X)` 找到 query_id → `get_query_profile`。用 trace 注释而不用 `LAST_QUERY_ID()`，是因为连接池里下一次调用不一定是同一个连接；用 hint 而不用 `SET`，是因为 D5 不改全局配置，而且 SQL 校验器会拒绝 `SET`。

### 4.4 语义层

| 项 | 内容 |
|---|---|
| 引擎 | upstream 自带的 MetricFlow（`src/metricflow`）：指标 + 维度 + 过滤 → SQL |
| 存储 | 库 `system_mcp` 的 3 张表：`workspace_metadata`、`active_store_ecom`、`staging_store_ecom` |
| workspace | `ecom`，`semantic_version` = 3 |
| 模型 | `doris/semantic/ecom/` 的 10 个 YAML：`project`、`orders`、`order_items`、`refunds`、`reviews`、`regions`、`shops`、`categories`、`brands`、`metrics` |
| 规模 | 9 张物理表上共 22 个指标，其中 13 个显式写在 `metrics.yaml`（`aov`、`gmv_mini_program`、`mini_program_share`、`gmv_last_year`、`gmv_yoy`、`line_gmv`、`qty`、`gross_profit`、`gross_margin`、`item_count`、`refunded_item_count`、`refund_rate`、`bad_review_rate`）；时间轴是 `dim_date`（2025-01-01 至 2026-12-31） |

**发布（`doris/publish-semantic.sh`）：** 以 root 在进程内用 upstream 的 `DorisStore` 发布，不经过 Web UI（要 admin 角色），也不用 `commit_staging`（它会对 `'%'` 执行 GRANT）；不执行任何 GRANT。步骤：

1. 离线：bootstrap、MetricFlow 引擎初始化、重复检查；
2. `pre_validate_physical`（对每张物理表 DESCRIBE）；
3. 清空 staging → upsert / delete → 逐字节比较 → `staging_commit`（版本 + 1）→ 再逐字节比较 active。

**模型里容易踩的坑（写进了 agent 指令）：**

- 订单实体叫 `order_entity`，小程序渠道是 `order_entity__channel = 'MINI_PROGRAM'`；
- `gmv` 含运费，按类目、品牌、店铺看要用 `line_gmv`；订单级指标不能按类目 / 品牌拆；
- 类目维度是 `category__cat1_name`（下钻 `cat2` / `cat3`）；
- 去年同期类指标要按 metric_time 分组，并写结束日期；
- NULL 返回 0：`gmv_last_year` / `gmv_yoy` 是 0 表示「没有数据」；
- 模型里字面的 `$` 要写成 `$$`；
- 时间过滤写在 `order_date` 上会让去年同期指标变成 0；
- 时间过滤会对齐到分组粒度：要比较同天数，按天分组。

### 4.5 metric_time 过滤（P-11）

`query_metric` 的 where 里，只有 `TimeDimension('metric_time')` 的条件会被提取成时间范围交给 MetricFlow，其余条件原样编译。P-11 之后的行为：

| 写法 | 结果 |
|---|---|
| `metric_time BETWEEN 'a' AND 'b'`、`>=`、`<=` | 提取成时间范围 |
| 几个 metric_time 条件用 AND 连接 | 取交集；不会留下空的 `( AND )` |
| 严格的 `>` / `<` | 边界移 1 天（带时间部分时移 1 秒） |
| metric_time 条件外面有 OR | `ValueError`，作为编译错误返回，并提示「每个时间范围调用一次，或用去年同期指标」。upstream 会编成非法的 `WHERE () OR ()` |
| metric_time 条件或它所在的括号组前面有 NOT | `ValueError`：时间范围不能取反。upstream 会提取条件，把 `NOT` 留在原处或挂到下一个过滤上 |

agent 指令的对应要求：一次调用只写一个时间范围，不用 OR；时间只按 metric_time 过滤。

### 4.6 Quick 侧

- **连接器：** `Doris-Desktop-MCP`（User auth，`demo` 用户）是主路径，P4 在网页版新建；桌面版不能刷新已有连接器的工具列表，所以工具变了要在网页版新建连接器。备份是 `doris-mcp-svc`（Service auth，网页版使用）。连接参数在 `quick/T0.7-guide.md`。
- **agent「Doris 专家」：** 指令是 `quick/agent-instructions.md` 全文（约 3,500 字符，Quick 上限 50,000），分 3 段：

  | 段 | 内容 | 为什么 |
  |---|---|---|
  | 角色 | 真实 Doris 集群上的 Doris 专家；用提问的语言回答；库里的文本值都是中文，查询条件照原文用中文 | 双语演示时数字和查询条件都不走样 |
  | 硬约束 1 证据优先 | 数字都来自本次工具调用；先 `check_service_health`；指标先 `list_metrics` 再 `query_metric`，多个指标放一次调用；不调用 reload | 每次调用都是冷启动（5–10 s），调用越少越快 |
  | 硬约束 2 只读 | 只用 SELECT / SHOW / DESCRIBE / EXPLAIN；DDL 只给出 | 写 = 人工 |
  | 硬约束 3 60 s | 大查询先 EXPLAIN、加 LIMIT；424 时缩小重试一次 | Quick 的 60 s 上限 |
  | 硬约束 4 不复述连接信息 | 不出现主机、IP、端口、账号、URL | 演示录屏 |
  | 硬约束 5 skills | 诊断类问题按 skills 做，先加载 `doris-mcp-adapter` | skills 是按 doriscli 写的 |
  | 演示口径 | 「今天」是 2026-09-25 12:00；同比、比率、渠道、类目维度的写法；618（2026-05-26 至 06-18）和双 11（2025-10-20 至 11-11）的活动期；同期同天数；可用的时间粒度；不用 OR；只按 metric_time；评价用 `TOKENIZE` / `MATCH_PHRASE` | 让答案和参照值一致 |

  `quick/test/test_agent_instructions.py` 检查：长度上限、3 段结构、工具名都在 Gateway 后面存在、指令里写到的指标名都已发布、维度名都能在语义层编译、活动期和指南第 3 步一致、没有 URL / IP / ARN / 账号 ID。
- **skills（`quick/skills/`）：**

  | 文件夹 | 来源 | 作用 |
  |---|---|---|
  | `doris-mcp-adapter` | 本项目自写 | 环境说明（没有 doriscli、mysql、curl、shell）；工具表；doriscli 命令 → `doris___*` 工具的对照；profile 流程；哪些 SQL 能用、哪些被拒（`SHOW TABLETS`、`SHOW PROC` 被拒；`SHOW PROCESSLIST` 只看得到服务账号自己的会话）；写和管理操作的边界；60 s；证据优先 |
  | `doris-debug`（34 个文件） | apache/doris-skills @ `0476f3b` | 故障诊断；整个文件夹一次导入 |
  | `doris-profile-reader`（12） | 同上 | 解读 Query Profile |
  | `doris-best-practices`（51） | 同上 | 建表、分区分桶、DDL 评审 |
  | `doris-architecture-advisor`（19） | 同上 | 按场景推荐架构和数据模型 |

  4 个副本由 `scripts/build_skills.py` 从锁定的 commit 生成，对 upstream 只做了 3 类改动：14 个 `SKILL.md` 第一行加一行指向 adapter 的提示；2 个超过 1024 字符的 description 缩短（1328 → 975、1307 → 978）；修 1 个链接（3 处）。`doris-repo-review`、README、`verify/` 等不导入。另外 3 个文件（`LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md`）不导入 Quick。导入顺序：adapter → doris-debug → profile-reader → best-practices → architecture-advisor。
- **双语：** agent 用提问的语言回答（中文问中文、英文问英文），数据值保持中文。第 1 轮彩排用英文提问；指南和手册都有中英两版（`*.en.md`），由 `test_p5_docs.py` 保持一致。

---

## 5. 使用方法

### 5.1 前提

| 需要 | 说明 |
|---|---|
| 开发机 | 本仓库所在的机器。它不在 Doris 的 VPC 里，经 Doris 的公网地址连接；`doris-demo-sg` 上那条已有的 `/32` 规则放行的就是它 |
| AWS CLI | 凭证指向项目账号，区域 us-east-1（脚本默认） |
| `.venv` | 仓库根目录的 Python venv；所有 Python 工具用 `.venv/bin/python` |
| agentcore CLI | `@aws/agentcore`（v0.30），只在重新部署时需要 |
| tmux | `tmux new -A -s doris`，SSH 断线不丢会话 |
| Doris 凭证 | 项目外的 `/home/ubuntu/AI-code/Doris-test/credentials.env`；只用 `set -a; source …; set +a` 加载，永远不要 echo 或 cat |
| Quick 桌面版 | 已登录 Enterprise 账号 |

### 5.2 在 Quick 里使用（`quick/P5-guide.md` 摘要）

1. 把 `quick/skills` 拷到 Quick 所在的电脑（在你自己的终端里 `scp -r`，命令见指南「准备」）。
2. **Customize → Skills → From folder**，按顺序导入 5 个文件夹；3 个文件不导入。
3. 编辑「Doris 专家」：指令换成 `quick/agent-instructions.md` 全文，挂上 5 个 skill，只关联 `Doris-Desktop-MCP`；备份「Doris 专家（svc）」同样处理。
4. 按 A3 的表设置 12 个工具的权限。
5. 新建对话，按 Part B 的 7 个问题提问；参照值在指南里。

### 5.3 跑一次演示（`quick/runbook.md` / `quick/runbook.en.md`）

```bash
bash scripts/demo-check.sh pre       # 演示前 30 分钟以内，只读，约 1.5 分钟
date +%s%3N                          # 记下预检结束的毫秒数
# ……演示……
bash scripts/demo-check.sh post --since <预检结束的毫秒数> --until <演示结束的毫秒数>
```

- `pre` 做 10 项检查，`post` 做 5 项（见 6.5）。每项一行 `[PASS]` / `[FAIL]`，子进程的输出经过 mask（IPv4 → `<ip>`，URL → `<url>`），最后一行 `demo-check MODE: N/M passed`。退出码：0 全部通过，1 有失败，2 参数错误或 `state.env` 不完整。
- 只有一项 `[FAIL]` 时先重跑一次（Runtime 偶发 502 或冷启动慢）；同一项连续两次失败，先看手册「出问题时」，不要开始演示。
- 可调的环境变量：`STATE_FILE`、`PYTHON`、`MAX_CONNS`（默认 80）、`CREDENTIALS_FILE`、`TOKEN_CMD`。
- 演示后按手册「演示后」第 2 步，在 Quick 里把 `doris___execute_query` 改回 Ask Each Time（D7）。

### 5.4 手工检查时取 Gateway token

```bash
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"   # 只捕获，不要 echo
bash scripts/get-gw-token.sh --claims                # 只打印解码后的 claims（含 client ID 和 issuer URL，不要贴进对话或文档），不打印 token
source infra/state.env                               # 只 source，不要 cat
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN list --expect 12
unset GW_TOKEN
```

`get-gw-token.sh` 用 AWS CLI 把 client B 的 secret 读进 shell 变量，通过进程替换生成的 header 文件交给 curl：secret 不出现在命令行参数里，也不打印；用完即 unset。token 有效期 60 分钟。`demo-check.sh` 里的 token 也不导出、不打印，只通过环境变量交给 `mcp_smoke.py`。

### 5.5 开发机工具

所有工具的输出都经过 mask（`scripts/redact.py`），不打印 URL、主机名、token。

| 工具 | 用途 | 典型用法 |
|---|---|---|
| `scripts/mcp_smoke.py` | MCP 冒烟客户端：列工具、调工具、profile 流程、逐次测耗时、数连接 | `--url "$GW_URL" --bearer-env GW_TOKEN flow --prefix doris___`；`--url "$RUNTIME_URL" --sigv4 list --expect 12`；`… time --prefix doris___ --parallel 20 --repeat 2`；`… conns --prefix doris___ --max-idle 610` |
| `doris/reconcile.py` | 对账：语义层的数和手写参照 SQL 一致（12 个 case；金额差 ≤ 0.005，比率差 ≤ 1e-6） | `direct [--models DIR] [--case NAME …]`（本地编译 YAML）；`mcp [--workspace ecom]`（进程内 server）；`mcp --url "$RUNTIME_URL"`（经 Runtime） |
| `doris/permission_matrix.py` | `mcp_svc` 的权限：只读检查 + 写探针 | `[--workspace ecom]`（只读检查）；`APPLY=1 …`（GATE，加跑 store_init 和 9 个写探针，只能直连）；`--url "$RUNTIME_URL" --expect-host '<host>'`（经 Runtime） |
| `scripts/audit_check.py` | 统计 `filter-log-events` 输出里的审计记录；`--failures` 逐条列出失败调用 | `aws logs filter-log-events … --filter-pattern '"doris_new_mcp.audit"' --output json \| .venv/bin/python scripts/audit_check.py --failures`（`demo-check.sh post` 里有完整写法） |
| `scripts/gw_latency.py` | Gateway 每分钟、每个工具的调用数和耗时 | `queries --gateway-arn …` 生成查询，`get-metric-data` 的输出管道给 `report [--warn-ms 45000] [--limit-ms 60000]`（完整写法见 `demo-check.sh` 的 `latency()`） |

- `mcp_smoke.py` 的目标二选一：`--url`（可加 `--bearer-env` 或 `--sigv4 [--region]`）或 `--stdio`；`--timeout` 默认 90 s。子命令：`list [--expect N]`、`call TOOL [JSON]`、`flow [--prefix] [--table ecom.fact_order] [--wait 45]`、`time [--calls] [--prefix] [--parallel] [--repeat] [--fresh] [--budget-ms 60000]`、`conns [--prefix] [--expect-host-prefix] [--max-idle]`。
- `reconcile.py` 和 `permission_matrix.py` 直连 Doris 时读 `DORIS_HOST`、`DORIS_PORT` 和 `DORIS_SECRET_ID`（或 `DORIS_USER` / `DORIS_PASSWORD`）。用 `demo_ro` 时，在子 shell 里 source 凭证文件再映射变量，写法照 `scripts/demo-check.sh` 的 `reconcile()`，不要把密码写在命令行上。
- 本地起 server（用 `demo_ro`，端口 8000）的完整写法在 `plans/P1-mcp-server.md` T1.8 Step 2；之后对本机 8000 端口的 `/mcp` 跑 `mcp_smoke.py`。

### 5.6 infra 脚本

所有 `infra/*.sh` 默认 **dry-run**：只打印将要执行的变更命令（`DRY-RUN:`）。**用户确认后**才用 `APPLY=1` 执行（GATE，一次确认只对应一次操作）。脚本可以重复执行，已存在的资源会跳过或重新对齐。

| 编号 | 脚本 | 阶段 | 做什么 |
|---|---|---|---|
| 10 | `infra/10-network.sh` | P0 | 两个 SG、`doris-demo-sg` 上的 2 条 SG 引用规则、3 个 VPC endpoint；自检没有对任意来源开放的入站 |
| 20 | `infra/20-cognito.sh` | P0 | user pool、域名、resource server、client A / B、用户 `demo` 和它的 secret；`QUICK_CALLBACK` 覆盖回调地址 |
| — | `agentcore deploy` | P0 / P3 / P5 | 部署 Runtime（见 5.7） |
| 25 | `infra/25-runtime-state.sh` | 每次部署后 | 只读；状态行是 `runtime dorismcp_dorismcp: status=… version=…`，但 dry-run 也会打印 `DRY-RUN: state_set RUNTIME_ARN=…` 等 4 行（含 ARN、账号 ID、URL），所以只用 grep 过滤后的输出；`APPLY=1` 把 `RUNTIME_ARN`、`RUNTIME_ID`、`RUNTIME_ROLE_ARN`、`RUNTIME_URL` 写进 `state.env` |
| 30 | `infra/30-gateway.sh` | P0 | `doris-mcp-gateway-role`、Gateway、target。变量：`GW_ALLOWED_SCOPES`（默认 `doris-mcp/invoke`，设为空去掉 scope 检查）；`GW_EXCEPTION_LEVEL`（默认 `DEBUG`，设为空字符串返回通用错误，其他值拒绝）；`SYNC=1` 同步 target 的工具 |
| 35 | `infra/35-runtime-role.sh` | P3 | `doris-mcp-runtime-role` 和 inline 策略 `doris-mcp-runtime` |
| 40 | `infra/40-doris-secret.sh` | P2 | secret `doris-mcp/mcp_svc`（Secrets Manager 生成 32 位字母数字密码）；已存在就不动 |
| 99 | `infra/99-cleanup.sh` | T5.6 | 见第 9 节 |

编号是依赖顺序；历史上 40 在 P2、35 在 P3 才执行。

**`infra/state.env`：** 记录已创建资源的 ID（例如 `ACCOUNT_ID`、`GW_ID`、`GW_URL`、`GW_TARGET_ID`、`RUNTIME_ID`、`RUNTIME_URL`、`RT_SG`、`VPCE_SG`、`COGNITO_POOL_ID`、`CLIENT_A_ID`、`CLIENT_B_ID`、`DORIS_SECRET_ARN`、`RT_ROLE_ARN`）。只有非敏感 ID，但脚本和文档都按变量名引用，值不要贴到对话或文档里。

**`infra/lib.sh` 的安全措施：**

- 读操作（describe / list / get）直接执行；变更操作都经过 `run`，没有 `APPLY=1` 时只打印；
- `state_set` 只在 `APPLY=1` 时写 `state.env`；dry-run 时新资源的 ID 用占位符 `<new:NAME>`；
- 已记录的状态优先于环境变量，只有脚本在 `STATE_CALLER_WINS` 里列出的变量（例如 `QUICK_CALLBACK`）由调用方决定；
- 含 secret 的 CLI 输入写进 `private_tmp` 生成的 0600 临时文件（AWS CLI 的 `file://` 读不了 `/dev/fd`），用完删除；
- 每个资源带标签 `Name` 和 `Project=doris-mcp-demo`；区域默认 us-east-1；`AWS_PAGER=""`。

### 5.7 修改 server 并重新部署

```bash
# 1. 改代码、跑离线测试（6.8）
# 2. 生成 agentcore.json（codeLocation ../mcp-server/，环境变量和 executionRoleArn 来自 state.env）
.venv/bin/python scripts/render-agentcore.py --phase server
# 3. 看差异：应该只有 Runtime 一个资源变化，而且只变了 CodeZip 的 S3 路径
(cd dorismcp && agentcore validate && agentcore deploy --diff -v) > /tmp/deploy-diff.log 2>&1; echo "exit=$?"
# 4. GATE：用户确认后部署（原地更新栈 AgentCore-dorismcp-default）
(cd dorismcp && agentcore deploy -y -v) > /tmp/deploy.log 2>&1; echo "exit=$?"
# 5. 看状态：status=READY，version 加 1
bash infra/25-runtime-state.sh 2>&1 | grep -E 'runtime dorismcp|WARN|FATAL'   # 只看状态行；其余行含 ARN / URL
# 6. 工具定义变了才需要：同步 target（GATE），再在 Quick 里 Sync、启用新工具
SYNC=1 APPLY=1 bash infra/30-gateway.sh
# 7. 验证
bash scripts/demo-check.sh pre
```

- `render-agentcore.py` 只写非 secret 的值，拒绝看起来像 secret 的环境变量名；`--phase server` 要求 `state.env` 里有 `RT_ROLE_ARN`；`--check` 只打印条目、不写文件。
- **不要打印** `dorismcp/agentcore/agentcore.json`（含私网地址）、`--check` 的输出、`agentcore status` 的原始 JSON 和部署日志原文；`25-runtime-state.sh` 要经 `grep -E 'runtime dorismcp|WARN|FATAL'` 过滤，只看状态行。
- 部署是原地更新：ARN 和 URL 不变，version 加 1，约 1 分钟，9 个步骤 SUCCESS。
- **CodeZip 的平台：** CLI 用 uv `--only-binary` 按 aarch64 manylinux2014 选 wheel，没有时回退到 `manylinux_2_28`、`_2_34`（`rapidfuzz` 会触发 `_2_28`）；包约 107 MB（上限 250 MB）；staging 目录在 `dorismcp/agentcore/.cache/<runtime>/staging`。P5 部署前后都核对过 staging 的 88 个 dist 和 `.venv` 一致（核对脚本在仓库外，嵌在 `plans/P5-skills.md` 里）。
- 部署前确认 `~/.agentcore/config.json` 里有 `"disableTransactionSearch": true`。CDK 引导栈 `CDKToolkit` 早已存在，不需要重新 bootstrap。
- 工具变化后的完整链路：deploy → `SYNC=1 APPLY=1 bash infra/30-gateway.sh` → Quick 里 Sync（新工具默认不启用，要手动启用）。桌面版刷新不了已有连接器时，在网页版新建连接器。

### 5.8 更新语义层

```bash
.venv/bin/python -m unittest discover -s doris/test         # 模型的离线测试
bash doris/publish-semantic.sh [--models DIR] [--workspace ecom]          # dry-run：离线检查 + 发布计划
APPLY=1 bash doris/publish-semantic.sh [--models DIR] [--workspace ecom]  # GATE：以 root 发布，版本 + 1
```

发布后用 `reconcile.py`（`direct` 或 `mcp --url "$RUNTIME_URL"`）对账，或直接跑 `demo-check.sh pre`（其中的 reconcile 项）。Runtime 会在下一次查询时发现版本变化并重新加载，不需要重新部署，也不需要调用 `reload_semantic_layer`。凭证文件只在子 shell 里加载，root 密码只在 `APPLY=1` 时交给 Python 进程。

### 5.9 重新生成 skills

```bash
git clone <apache/doris-skills 的地址> /tmp/doris-skills
git -C /tmp/doris-skills checkout <LOCKED_COMMIT>            # 0476f3b…，全称见 quick/skills/UPSTREAM.md
.venv/bin/python scripts/build_skills.py --source /tmp/doris-skills --check   # 只比较
.venv/bin/python scripts/build_skills.py --source /tmp/doris-skills           # 写 quick/skills/
```

退出码：0 已写入或完全一致；1 `--check` 发现差异；2 源目录不在锁定的 commit。脚本从 git 对象读文件，不看工作区。`doris-mcp-adapter` 是手写的，不由脚本生成。改了 skill 要在 Quick 里重新导入。

### 5.10 Doris 账号 SQL（GATE，人工执行）

```bash
bash doris/apply-admin-sql.sh doris/01_mcp_user.sql            # dry-run：打印遮蔽后的语句，不连 Doris
APPLY=1 bash doris/apply-admin-sql.sh doris/01_mcp_user.sql    # GATE
```

| 文件 | 做什么 |
|---|---|
| `doris/01_mcp_user.sql` | 建 `'mcp_svc'@'%'` 并授权（D6，P2） |
| `doris/02_mcp_user_vpc.sql` | 把 host 收紧到 VPC 私网网段（P3）：先建新身份，再删 `'%'`。之后开发机直连 `mcp_svc` 会得到 1045；回滚是重跑 `01` |

- 以 root 执行；`doris/admin_sql.py` 只接受白名单里的语句。
- `mcp_svc` 的密码走 Secrets Manager → 管道 → `admin_sql.py`，只在内存里，不进命令行、磁盘或输出。
- Doris FE 的 `fe.audit.log` 可能记下建用户 / 改密码语句里的明文密码；P3 时用户在 Doris 主机上只按计数检查过。

### 5.11 必须遵守的规则

- **GATE：** 任何创建或修改 AWS 资源、Doris 账号 / 权限、安全组的操作，先展示 dry-run，用户确认后才 `APPLY=1`；一次确认只对应一次操作。
- **secret：** 密码只在 Secrets Manager 和项目外的 `credentials.env`；不出现在仓库、命令行参数、日志或对话里；不 echo、不 cat 凭证文件；不要用 Claude Code 的 `!` 前缀取 secret。
- **提交前：** 运行 `bash scripts/check-secrets.sh`，有命中就不能提交（它要读 Secrets Manager，需要有效的 AWS 凭证）。
- **推送：** 由用户决定（D8），不强推。
- **不改 `prepare/`**；MCP 不执行 DDL / DML。

---

## 6. 测试原理

目标：不碰 AWS、不连 Doris 也能证明大部分逻辑正确；必须在线才能证明的部分，用只读的在线检查和一次端到端彩排来证明。

### 6.1 分层

| 层 | 证明什么 | 位置 | 怎么跑 | 数量（2026-09-30 实测） |
|---|---|---|---|---|
| server 补丁单测 | P-01…P-11、qid 修正的行为 | `mcp-server/test/test_agentcore_*.py` | unittest | 154 |
| upstream 离线套件 | 补丁没有破坏 upstream | `mcp-server/test/` | `run_all_tests.sh --offline` | 19 组全部通过 |
| scripts 单测 | 冒烟、审计、耗时、mask、生成脚本、skills 构建 | `scripts/test/test_*.py` | unittest | 138 |
| doris 单测 | 账号 SQL、权限矩阵、对账、发布、语义模型、metric_time | `doris/test/test_*.py` | unittest | 168 |
| 文档即测试 | 指南 / 手册 / 指令 / skills 与代码和语义层一致 | `quick/test/` | unittest | 89 |
| shell 测试 | infra / 预检 / 清理 / secret 检查脚本的调用顺序和安全性 | `scripts/test/test-*.sh`、`infra/test/test-*.sh`、`doris/test/test-*.sh` | bash，假 `aws` / `python` | 9 个文件，353 个 ok |

shell 测试的 ok 数：`test-check-secrets` 36、`test-demo-check` 100、`test-30-gateway` 30、`test-35-runtime-role` 46、`test-40-doris-secret` 23、`test-99-cleanup` 81、`test-lib` 5、`test-apply-admin-sql` 18、`test-publish-semantic` 14。

### 6.2 shell 测试怎么做到不碰 AWS

每个测试建一个临时目录，把假的 `aws`（有的还有假的 `python`、`sleep` 或 `TOKEN_CMD`）放在 PATH 最前面，然后运行被测脚本：

- 假命令把每次调用的参数追加到 `FAKE_LOG`，按预设返回结果，或者按环境变量（例如 `FAKE_AWS_FAIL="service operation"`）模拟某个调用失败；
- 断言看的是调用记录：调用了什么、顺序、变更调用有几次、dry-run 时有没有变更调用、退出码，以及输出和参数里有没有出现 secret。

几个例子：

- `test-99-cleanup.sh`：假 `aws` 是一个 Python 程序，维护一份 JSON「世界」（本项目的资源），每次写操作都改这份世界，`--query` 用 jmespath 求值，和真 CLI 一样。测试证明：全部检查都在第一次删除之前；任何不符都 FATAL 且一个都不删；只撤销引用 `doris-mcp-rt` 的规则；已经不存在的资源跳过。
- `test-demo-check.sh`：假 `aws` / `python` 记下每个子进程拿到了哪些 `DORIS_*` / `GW_TOKEN` 变量名，证明 token 不进 argv、不导出、不打印，只有 reconcile 拿到只读账号；fixture 里故意放了测试网段的 IP，证明输出经过 mask。
- `test-check-secrets.sh`：在一次性的 git 仓库里跑，用 `FAKE_SM` 模拟 Secrets Manager 的各种回答（正常、排期删除、不存在、没有权限等），证明只有「排期删除」或「在本项目账号里确实不存在」才跳过，其他读不到的情况都算失败。

### 6.3 文档即测试

文档里的问题、参照值、命令和工具名都是演示时要照抄的，所以用测试锁住：

- `test_p5_docs.py`：中英文指南、手册的代码块、标题和参照值一致；每个出现的工具名都在 Gateway 后面存在（`GATEWAY_PREFIX` + 12 个名字）；手册运行的每个脚本都存在；卫生检查：没有 URL、IPv4、ARN、12 位账号 ID。
- `test_agent_instructions.py`：长度 ≤ 50,000；3 段结构；工具名带 `doris___`；指令里的指标名必须是已发布的指标，维度名用 `reconcile.py` 的 DirectBackend 对语义层编译一遍；活动期和指南第 3 步一致；「同期同天数」是一个对账 case；没有 URL / IP / ARN / 账号 ID。
- `test_skills.py`：文件夹集合；frontmatter 限制（name ≤ 64、description ≤ 1024、每个文件夹 ≤ 6 MB）；提示行；许可证和来源；触发词；链接。
- `test_adapter_skill.py`：`CLI-CONTRACT.md` 和副本里的每个 doriscli 用法都有对照；工具名；profile 流程的参数（`max_chars` 取自 server 的参数定义）；只读边界和 60 s。

### 6.4 计划里嵌入代码、突变测试

- **计划嵌入代码：** 每个阶段的代码和测试先在 spec 阶段按 TDD 在临时目录写好，完整嵌进 `plans/*.md`。每个文件前有一行 `<!-- file: NAME sha256=HEX -->`，紧跟的代码块就是文件内容（P5 计划嵌了 33 个文件）。执行时用一个小工具按 sha256 校验后取出文件，而不是手抄。这个工具本身也嵌在计划里，运行时写到 `/tmp`，不在仓库里。
- **突变测试：** 证明测试真的能抓到回归。每个突变把某个文件里的一段字符串（必须恰好出现 1 次）替换一次，跑它指定的测试，期望测试失败，然后逐字节恢复文件。子进程带 `PYTHONDONTWRITEBYTECODE=1`，避免跑到上一个突变体的缓存字节码。输出每个突变 `caught by …` 或 `NOT CAUGHT`，最后确认工作树恢复原样。P5 计划里的突变清单有 14 组、220 个突变，全部被抓到（`sk` 34、`st` 11、`ad` 14、`ai` 7、`p10` 21、`p11` 20、`af` 13、`m8` 6、`m9` 16、`gw` 11、`cl` 22、`dc` 21、`cs` 9、`docs` 15）；执行中又加了几组：双语改动 `bil` 44、`adx` 14，彩排后 T5.5 的修改 `t8` 52、`t8b` 6（见 `progress.md`），也全部被抓到。突变工具和 P5 的突变清单同样只嵌在计划里，不在仓库里；spec 阶段整份计划在一个干净的 worktree 上回放过。

### 6.5 在线检查（真实凭证，由人或 Claude 在 GATE 规则下执行）

| 检查 | 证明什么 | 阈值和原因 |
|---|---|---|
| `demo-check.sh pre`（10 项） | 账号是 `ACCOUNT_ID`；Gateway、target 是 READY；能取到 token；经 Gateway 列出 12 个工具；`flow`；`reconcile`；权限矩阵；连接的 host 前缀和空闲时长；连接数 | 连接空闲 ≤ 610 s（`wait_timeout` 600 加余量）；连接数 ≤ `MAX_CONNS` 80（`max_user_connections` 是 100） |
| `demo-check.sh post --since MS --until MS`（5 项） | 这段时间的审计记录（`audit_check --failures`）；Gateway 延迟（窗口扩到整分钟）；token；连接；连接数 | `--since` / `--until` 是 13 位毫秒时间戳 |
| `mcp_smoke.py flow`（6 步） | 带 profile 执行 → 按 trace 找到 query_id → summary < 20000 字符；非法 query_id → `INVALID_PARAMS`；不存在的 id → `profile_found=false`；`DELETE` 被拒 | `--wait` 默认 45 s：profile 是异步收集的，平台抖动时有一次 `list_recent_queries` 调用用了约 30 s，用完了原来 15 s 的等待，导致一次 `demo-check pre` 失败 |
| `reconcile.py mcp --url`（12 个 case） | 经 Runtime 的语义层答案和手写 SQL 一致 | 金额 0.005，比率 1e-6 |
| `permission_matrix.py --url … --expect-host …`（4 项只读检查 + 身份，共 5 项） | `SHOW GRANTS` 恰好是期望集合；`SHOW DATABASES`；模型的表都能读；workspace 有元数据行和 active 文件；连接身份的 host 正确 | 写探针只能在直连时用 `APPLY=1` 跑 |
| `audit_check.py --failures` | 每个预期的调用都有审计记录；失败的调用列出工具和错误原因 | 默认只打印按工具、结果的计数；`--failures` 再列出失败调用的错误（截到 200 字符，IPv4 已 mask）和 `query_metric` 的 group_by / where / having；不打印 SQL |
| `gw_latency.py report` | Quick 每次工具调用实际等了多久 | ≥ 45 s 标 WARN、≥ 60 s FAIL：Quick 的上限是 60 s；SQL 超时是 50 s，但每次调用另有约 5–10 s 的平台开销，跑满 50 s 的查询端到端约 56–61 s，可能超过 60 s。45 s 的 WARN 用来提示是否把 `query_timeout` 调到 40–45 s（T5.5 决定保持 50 s，因为没有出现 WARN） |

实测的耗时：P3 经 Gateway p50 约 6.2 s，最慢的是语义层调用（9.5–10.1 s），20 并发时最大约 10.1 s；P4 单次最长约 9.9 s，没有 ≥ 45 s 的调用；第 1 轮彩排整段窗口单次最长约 9.7 s（7 个步骤内最长 9.3 s，见手册「每步耗时」）。

### 6.6 安全测试

- `scripts/check-secrets.sh` 扫描 git 会提交的所有文件（已跟踪 + 未跟踪且未忽略），只打印变量名和文件名：
  1. 凭证文件里所有名字含 PASSWORD / SECRET 的变量的**确切值**，经管道（`grep -f -`）交给 grep，不进命令行；
  2. Secrets Manager 里的两个密码（`doris-mcp/mcp_svc`、`doris-mcp/cognito-demo-user`），经进程替换交给 grep；排期删除或已删除的 secret 跳过，读不到则失败；
  3. 通用模式：AWS access key、私钥头、`aws_secret_access_key` 赋值、带字面密码的建用户语句。占位符（`<password>`、`${VAR}`）不算。
- 离线测试 `scripts/test/test-check-secrets.sh`（36 个）覆盖以上每一类命中、占位符不误报、各种跳过和失败条件。
- 另外，`test_p5_docs.py` 的卫生检查、`test-demo-check.sh` 的 token / mask 检查、`test_mcp_smoke.py` 的 `hidden_values` 测试也都是安全测试。

### 6.7 彩排：端到端验收

在线检查证明了每一段；彩排证明整条链路在 Quick 里真的能讲完。第 1 轮（英文提问）已完成：用户确认 Part B 没有问题；`demo-check post` 5/5；审计 100 条里 4 条失败（SQL 错误或参数校验），都由 agent 自己改正；Gateway 延迟没有 ≥ 45 s 的调用。每步工具调用占用的时间（秒）是 6 / 37 / 76 / 115 / 30 / 67 / 32（按审计推算，见手册「每步耗时」）。第 2 轮按用户决定跳过。彩排发现的问题在 T5.5 修掉：第 3 幕猜错了类目维度名、活动期用了自己估的日期（于是把类目维度名和 618 / 双 11 的活动期写进指令）；英文第 5 幕没有用倒排索引检索差评词；`flow` 的 `--wait` 从 15 s 改为 45 s。

### 6.8 离线跑全部测试

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s quick/test                                 # 89
.venv/bin/python -m unittest discover -s scripts/test                               # 138
.venv/bin/python -m unittest discover -s doris/test                                 # 168
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py'   # 154
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline    # All tests passed
for t in scripts/test/test-*.sh infra/test/test-*.sh doris/test/test-*.sh; do bash "$t"; done   # 每个都 all passed
```

不要给 unittest 加 `-t .`。以上都不访问 AWS 和 Doris。

---

## 7. 安全设计

design §14 的安全清单和 `CLAUDE.md` 的硬性规则：

| 方面 | 做法 |
|---|---|
| 网络 | 只加 SG 引用规则；任何 SG 都没有对任意来源开放的入站；已有的 `/32` 规则不动；`doris-mcp-rt` 只有 4 条出站；Doris 不对外开放新端口 |
| 密码 | 只在 Secrets Manager 和项目外的 `credentials.env`；`agentcore.json`、脚本、文档、git 历史里都没有明文；提交前跑 `check-secrets.sh` |
| 密码怎么流动 | Secrets Manager → 进程内存；需要交给命令时走管道、进程替换或 0600 临时文件，不进命令行参数，不打印 |
| Doris 最小权限 | `mcp_svc` 的 `SHOW GRANTS` 恰好是期望集合 + Doris 默认项，没有 ADMIN；9 个写探针全部被拒；发布语义层不执行 GRANT；host 收紧到 VPC 私网网段 |
| IAM 最小权限 | Runtime 执行角色只能写自己的日志组、只能读一个 secret；Gateway 角色只能调用一个 Runtime；CDK 生成的通配权限角色已删除 |
| 只读 | SQL 校验器 + Doris 权限 + agent 指令 + Quick 工具权限，四层 |
| 输出 | 工具输出、脚本输出都 mask IPv4 / URL / token；agent 不复述连接信息 |
| Cognito | client secret 只填在 Quick 连接器里；不用长期静态 token；只允许管理员建用户 |
| 审计 | CloudWatch 审计日志保留 SQL，upstream 的 `sensitive_mask` 保持开启 |

**还开着的项：**

- Gateway 的 exception level 仍是 `DEBUG`（T5.5 决定保留，排错要用），错误详情会返回给客户端；改回见 8.2。
- Doris 连不上时，pymysql 的 2003 错误消息里带 Doris 地址，会经 Gateway 原样返回。T5.5 决定不打补丁（第 1 轮彩排没出现）；手册要求出现时不要念出来。
- Doris FE 的 `fe.audit.log` 可能记下建用户 / 改密码语句的明文密码（见 5.10）。
- 与本项目无关、但还没关闭：旧的公开仓库 `doris-mcp-agentcore` 的 `deploy.conf` 里有明文 root 密码。如果这个密码仍在使用，请轮换，并清理那个仓库的 git 历史。

---

## 8. 资源保留期间的注意事项与成本

### 8.1 成本（design §15，us-east-1 粗估）

| 项 | 费用 |
|---|---|
| Interface endpoints：logs + secretsmanager，各 2 个 AZ | 4 × $0.01/h ≈ **$29/月**，另加 $0.01/GB。这是保留期间的主要固定费用 |
| S3 Gateway endpoint | 免费 |
| AgentCore Runtime / Gateway | 按用量计费，不用就几乎没有 |
| Secrets Manager | 每个 secret $0.40/月，本项目 2 个 |
| Cognito | 很小 |
| Doris EC2 m6i.2xlarge（项目之前就有） | 约 $0.384/h，不用时可以停机（按 Doris 的运维手册操作，不在本仓库里） |

### 8.2 保留期间要记得的事

- **Gateway exception level 仍是 DEBUG。** 要改成通用错误：`GW_EXCEPTION_LEVEL="" bash infra/30-gateway.sh` 先 dry-run，确认后 `GW_EXCEPTION_LEVEL="" APPLY=1 bash infra/30-gateway.sh`（GATE）。`update-gateway` 会整体替换配置，所以不带这个变量重跑脚本会回到 DEBUG。
- **`doris___execute_query` 改回 Ask Each Time。** 在 Quick 里改（D7，手册「演示后」第 2 步）。下次演示前再按 `quick/P5-guide.md` A3 改回 Always Allow。
- **下次使用前先预检：** `bash scripts/demo-check.sh pre`。要 10/10 才开始；只有一项失败时重跑一次。
- **token 和登录：** Gateway token 60 分钟过期，重新取即可；Quick 要求重新登录或重新填 client secret / `demo` 密码时，按 `quick/T0.7-guide.md` 在你自己的终端里获取。
- **Doris 连接：** `mcp_svc` 的 host 只允许 VPC 私网网段，开发机不能用它直连（1045 是正常的）。
- **Doris EC2 停机后再启动：** 之后先跑 `demo-check.sh pre`，确认 Runtime 能连上。

---

## 9. 清理（以后由用户执行）

清理是 T5.6（`plans/P5-skills.md` Task 9）。用户已决定暂时保留资源，以后由用户自己执行；Claude 之后只做只读核对和记录。

### 9.1 AWS 侧：`infra/99-cleanup.sh`

```bash
bash infra/99-cleanup.sh              # 先 dry-run，看清要删的资源
APPLY=1 bash infra/99-cleanup.sh      # 确认后才执行（GATE）
```

只删除 `state.env` 里记录的资源，按依赖顺序（每一步删掉的是挡住下一步的东西）：

1. Gateway target，然后 Gateway `doris-mcp-gw`；
2. CloudFormation 栈 `AgentCore-dorismcp-default`（Runtime），等到 stack-delete-complete；
3. VPC endpoints S3 / logs / secretsmanager，等到它们消失；
4. Cognito hosted UI 域名，然后 user pool；
5. secret `doris-mcp/cognito-demo-user` 和 `doris-mcp/mcp_svc`：默认 7 天恢复期（`SECRET_RECOVERY_DAYS`，7–30），`FORCE_DELETE_SECRETS=1` 则不留恢复期；
6. `doris-demo-sg` 上引用 `doris-mcp-rt` 的入站规则（它的其他规则不动）；
7. 等 `doris-mcp-rt` / `doris-mcp-vpce` 不再被任何网卡使用（Runtime 的 ENI 在栈删除几分钟后才释放），撤销两者之间的互相引用，删除这两个 SG；
8. IAM 角色 `doris-mcp-gateway-role` 和 `doris-mcp-runtime-role`（先删 inline 策略）。

**安全措施：** 第一次删除之前先做全部检查：调用方账号必须是 `ACCOUNT_ID`；每个资源都要带 `Project=doris-mcp-demo` 标签（栈看 `agentcore:project-name=dorismcp`）；Gateway 的名字必须是 `doris-mcp-gw`。任何不符或意外错误都 FATAL，一个都不删。已经不存在的资源记一行后跳过，所以中途失败可以直接重跑。

**不删除：**

- `infra/state.env`（保留，作为删了什么的记录）；
- 日志组；X-Ray / transaction search 的设置；其他项目的资源（例如同账号里另一个项目的 Gateway `pragent-github-gw`）；
- CDK 引导栈 `CDKToolkit` 和它的 S3 桶：本项目之前就有，同账号同区域的其他 CDK 项目也可能在用（agentcore 部署只往桶里上传了资产）；
- AgentCore 自动创建的 workload identity（名字以 `dorismcp_dorismcp-`、`doris-mcp-gw-` 开头）：它们不在 `state.env` 里，脚本不处理；删除 Runtime / Gateway 时它们会不会一起删掉，没有验证过。

### 9.2 Doris 侧和 Quick 侧

按 `quick/runbook.md`「演示后」第 3 步：

- Doris 侧（可选，单独确认）：`99-cleanup.sh` 不删 `mcp_svc` 和 `system_mcp`。不再演示时，由你用 root 在自己的 mysql 客户端里执行手册里的两句（删除 `mcp_svc` 在 VPC 网段上的身份、删除库 `system_mcp`），AI 不执行。`ecom` 的数据和 `demo_ro` 不受影响。以后再演示要重做 P2（发布语义层）和 P3（建账号）。
- Quick 侧（可选）：连接器、agent 和 skills 由你在 Quick 里删除。

---

## 10. 已知限制与注意事项

| 限制 | 影响 | 应对 |
|---|---|---|
| Quick 每次 MCP 操作最多 60 s | 超过报 HTTP 424 | SQL 超时 50 s；大查询先 EXPLAIN、加 LIMIT；424 时缩小范围重试一次 |
| 每次 `tools/call` 都是新 microVM | 每次调用 5–10 s；预热没有用；新 microVM 第一次用语义层要重新加载 | 多个指标放一次调用；按每步几次调用估时间 |
| Runtime 偶发 502 / 冷启动慢 | spec 阶段 3 次预检里有 2 次各有 1 项失败 | 平台侧问题；只有一项失败时重跑一次 |
| `SHOW PROCESSLIST` 只看得到 `mcp_svc` 自己的会话 | 看不到其他用户正在跑的慢查询 | adapter 让 agent 说明这一点，并请用户提供 SQL 或 query_id |
| `SHOW TABLETS`、`SHOW PROC` 被拒 | skills 里基于它们的诊断做不了 | adapter 的「SQL that works and SQL that does not」给出替代 |
| metric_time 不能用 OR / NOT | 返回编译错误 | 每个时间范围调用一次，或用去年同期指标（4.5） |
| 时间过滤对齐到分组粒度 | 按月分组时 9 月 1–25 日会变成 9 月整月 | 比较同天数时按天分组 |
| 桌面版不能刷新已有连接器的工具列表 | 工具变了之后桌面版看不到 | 在网页版新建连接器，agent 改为关联新连接器 |
| Quick 每个连接器最多 100 个工具；input schema 要符合 JSON Schema Draft 7+ | 当前 12 个工具，符合 | 加工具时注意 |
| Quick 指令 ≤ 50,000 字符；每个 skill ≤ 6 MB，description ≤ 1024 字符 | 由 `quick/test` 检查 | — |
| 桌面版最多 20 个并行工具调用 | 已按 20 并发测过 | — |
| Quick 是否按 PRM 请求 scope 未证实（P0 评审 M-1） | 功能上不影响：User auth、Service auth 在 scope 限制下都成功 | 只作记录 |
| 2003 错误消息带 Doris 地址 | 可能出现在回答里 | 不念出来；录屏剪掉（7 节） |
| 没有 Local stdio 路径（D9） | 备份只有 Service auth 连接器 | 备份 agent 在网页版使用 |
| 单节点 Doris、单服务账号 | 不是生产架构，Doris 里看不到最终用户 | 演示范围内接受（design §1） |

---

## 11. 开发方式与断点恢复

### 11.1 spec 驱动

```
requirements.md  →  design.md  →  tasks.md  →  plans/P?-*.md  →  progress.md
（R-xx、D1–D9）     （设计和已核实事实） （总清单、执行方、GATE） （逐步计划 + 嵌入代码） （当前状态 + 追加式日志）
```

- 每完成一个任务：勾选 `tasks.md` → 更新 `progress.md`（「当前状态」+ 日志）→ 一次 commit（改动和进度一起提交，commit 前跑 `check-secrets.sh`）。
- 两种执行方式（`RESUME.md`）：subagent-driven（每个任务一个实现子代理 + 一个审查子代理，最后整体审查）和 native（在当前会话里逐个执行，适合 GATE 多的阶段）。
- 会话中断后，新会话按 `CLAUDE.md` 的「恢复协议」执行：读 `progress.md` 的当前状态 → 找 `tasks.md` 第一个未勾选的任务 → `git status` / `git log` → `source infra/state.env` → 继续。用户侧只需要说「继续」，详见 `RESUME.md`。

### 11.2 各阶段结果（design §11，`tasks.md`）

| 阶段 | 做了什么 | 结果 |
|---|---|---|
| P0 spike | VPC endpoints、SG、spike server（`net_check`）、Cognito、Gateway、Quick 两种鉴权 | Runtime 在 VPC 里连通 Doris；User auth、Service auth 都跑通 |
| P1 server | 本地补丁 P-01…P-08、12 个工具；本机用 `demo_ro` 联调 | 12 个工具都能调；Draft 7 校验通过；upstream 离线测试全部通过；profile 流程和错误情况（非法 qid、找不到、密码错误）都返回结构化结果 |
| P2 Doris | secret、`mcp_svc`、权限矩阵、语义层发布、对账 | 权限矩阵全部通过；语义层 `semantic_version` 3；对账全部一致 |
| P3 部署 | Runtime 换成 `mcp-server/`、secret、专用执行角色、target 同步、host 收紧、P-09 | 经 Gateway `flow` 6/6；耗时都在 60 s 以内；P-09 验证 |
| P4 Quick | User auth + Service auth 连接器、agent、输出 mask、Gateway 耗时探针 | 两条路径都能完成「开场 + 第 2 幕」 |
| P5 skills | skills 和 adapter；P-10 / P-11（version 3）；query_id 修正（version 4）；`demo-check.sh`、`99-cleanup.sh`；第 1 轮彩排；T5.5 决定 | 演示准备完成；本地合并到 `main`，未推送；T5.6 清理推迟 |

---

## 12. 文档索引

| 文件 | 是什么 | 什么时候读 |
|---|---|---|
| `README.md` | 本文：整体说明 | 第一次看这个仓库，或隔一段时间回来 |
| `RESUME.md` | 人怎么让 Claude 继续：启动方式、第一句话怎么说、GATE / secret 注意事项 | 开新会话之前 |
| `CLAUDE.md` | Claude 的恢复协议和硬性规则 | 改规则时；Claude 每次会话自动读 |
| `specs/doris-mcp-quick/README.md` | spec 目录里每个文件的说明 | 要改 spec 时 |
| `specs/doris-mcp-quick/requirements.md` | 需求 R-xx 和决策 D1–D9 | 想知道「为什么要这样」 |
| `specs/doris-mcp-quick/design.md` | 设计：架构、已核实事实、补丁、基础设施、风险、安全、成本 | 要改设计或排查问题（含私网地址，引用时注意） |
| `specs/doris-mcp-quick/tasks.md` | 总任务清单 P0–P5 | 看还剩什么 |
| `specs/doris-mcp-quick/plans/` | 各阶段的详细计划和嵌入代码 | 执行或重放某个任务 |
| `specs/doris-mcp-quick/progress.md` | 当前状态和日志 | 了解进度和历史决定 |
| `quick/runbook.md` / `runbook.en.md` | 演示手册：演示前、设置、流程、出问题时、演示后、每步耗时 | 演示当天 |
| `quick/P5-guide.md` / `P5-guide.en.md` | 导入 skills、更新 agent、工具权限、彩排步骤和参照值 | 重新设置 Quick 或彩排 |
| `quick/P4-guide.md` | 连接器、agent 的创建和 Service auth 备份 | 重建连接器或 agent |
| `quick/P4-handoff.md` / `P5-handoff.md` | 阶段交接摘要 | 回顾当时的状态 |
| `quick/T0.7-guide.md` | Quick 连接参数和取 secret 的方法（含 URL） | 新建连接器、重新登录时（不要贴到对话里） |
| `quick/agent-instructions.md` | agent「Doris 专家」的指令全文 | 更新 agent |
| `quick/skills/UPSTREAM.md` | skills 副本的来源 commit 和改动 | 升级 skills |
| `quick/skills/doris-mcp-adapter/SKILL.md` | 自写的 adapter skill | 了解 agent 在 Quick 里能做什么、不能做什么 |
| `mcp-server/UPSTREAM.md` | upstream 来源、补丁表、升级步骤 | 升级 upstream 或改补丁 |
| `mcp-server/test/README.md` | upstream 测试的说明 | 跑或改 upstream 测试 |
| `infra/*.sh` 文件头 | 每个脚本创建什么、有哪些变量 | 执行之前 |
| `dorismcp/README.md`、`dorismcp/AGENTS.md` | agentcore CLI 生成的项目说明 | 用 agentcore CLI 时 |
