# Doris MCP Server 部署到 AWS AgentCore + Amazon Quick 连接演示方案

> 研究与方案报告 · 2026-09-26
> 目标：把 VeloDB/Doris MCP Server 改造并托管到 Amazon Bedrock AgentCore，用 Amazon Quick 作为 MCP 客户端连接，并挂载 apache/doris-skills 做演示。

---

## 0. 一图看懂整体链路

```
┌─────────────┐   Inbound Auth (JWT/OAuth)   ┌──────────────────┐  Outbound Auth (OAuth2)  ┌────────────────────┐   MySQL 9030   ┌──────────┐
│ Amazon Quick│ ───────────────────────────► │ AgentCore Gateway│ ───────────────────────► │ AgentCore Runtime  │ ─────────────► │  Doris   │
│ (MCP Client)│      Cognito 用户池 #1        │  (MCP target)    │   Cognito 用户池 #2       │  容器化 MCP Server  │   (你的测试库)  │  FE:9030 │
│ + Skills    │ ◄─────────────────────────── │                  │ ◄─────────────────────── │  0.0.0.0:8000/mcp  │ ◄───────────── │          │
└─────────────┘         tools / results       └──────────────────┘                          └────────────────────┘                └──────────┘
```

- **Amazon Quick** 内置 MCP 客户端，作为整个演示的对话入口，并承载 skills。
- **AgentCore Gateway** 负责鉴权桥接（Inbound = Quick→Gateway，Outbound = Gateway→Runtime）。
- **AgentCore Runtime** 以容器形式托管改造后的 MCP Server，暴露 `0.0.0.0:8000/mcp`（streamable-HTTP）。
- **Doris** 是你手上的测试库，MCP Server 通过 MySQL 协议（默认 FE 端口 9030）连接。

---

## 1. 客户提供的 4 个链接：研究整理

### 1.1 VeloDB MCP 官方文档（使用 SOP）
**客户原文链接**：https://docs.velodb.io/cloud/ai-devex/mcp-server/introduction （SelectDB 国内站文档内容一致）

来源：VeloDB Docs — MCP Service Overview [@627ec8cf5328]

- **定位**：把 AI agent 通过 MCP 连接到 VeloDB/Doris，支持三类能力：元数据发现、只读 SQL、以及（可选）语义指标查询。
- **两条查询路径**：
  1. **元数据发现 + 只读 SQL**：无需语义模型即可用。Agent 先发现库/表/列，再生成只读 SQL。
  2. **语义查询**：当管理员发布了语义模型（基于 MetricFlow）后可用，Agent 走 `list_metrics → list_dimensions_for_metric → query_metric`。
- **Agent 标准工作流（SOP）**：
  1. `get_query_guide` 载入工作流指引（永远第一步）
  2. `check_service_health` 校验连接 + 各 workspace 状态
  3. 元数据类问题 → 元数据工具
  4. 有匹配指标 → 语义查询工具链
  5. 无语义模型/无匹配指标 → `list_databases → list_tables → describe_table → execute_query`
- **安全**：每次请求用调用方自己的 VeloDB SQL 用户凭证（Bearer `user:password`）；`execute_query` 只允许 `SELECT / SHOW / DESCRIBE / EXPLAIN`，DML/DDL/多语句/导出全部拦截。
- 没有语义模型也能连接和用（会报 `no_models`，仍能跑元数据 + 只读 SQL）。

> 说明：官方页面有版权限制，以上为要点转述，不是逐字拷贝。SelectDB 国内站文档内容一致，可作中文对照。

### 1.2 velodb-mcp-server 开源仓库（README + AGENTS.md）
**客户原文链接**：https://github.com/velodb/velodb-mcp-server （含使用/安装/在 agent 中配置的 guide）

来源：github.com/velodb/velodb-mcp-server [@497370ef] [@2a75f82d]

**这是关键 —— 它是一个「自带 Python 3.10 运行时、自包含」的 HTTP MCP 服务，正好适合容器化到 AgentCore。**

- **技术栈**：FastMCP 3.x，transport = `streamable-http`，`stateless_http=True`，默认监听 **3000** 端口，路径 `/mcp`。
- **数据库要求**：任何 MySQL 协议兼容的 Doris 家族集群（VeloDB Cloud / VeloDB Enterprise / Apache Doris），默认 FE `127.0.0.1:9030`。
- **配置文件** `mcp-server.toml` 关键项：
  | Key | 默认 | 说明 |
  |-----|------|------|
  | `server.mcp_host` / `mcp_port` | `0.0.0.0` / `3000` | HTTP 监听地址 |
  | `server.fe_host` / `fe_port` | `127.0.0.1` / `9030` | Doris FE 端点（远程部署时改成私网 IP/主机名）|
  | `query.db_whitelist` | `[]` | 可选库白名单 |
  | `query.query_timeout_seconds` | `600` | SQL 超时 |
  | `query.query_max_rows` | `10000` | 单次最大行数 |

  所有值支持 `${ENV_VAR}` 环境变量插值 —— **这点对 AgentCore 容器化非常有用**（凭证/地址走环境变量注入）。
- **鉴权模型**：`Authorization: Bearer <velodb-user>:<password>`，每个用户独立连接池，无共享 admin 池。
- **安装方式**：
  - 面向 AI agent 的自动安装 playbook 在 `AGENTS.md`：只问用户 2 个问题（连接信息、安装位置），自动下载 release、改 `toml`、后台启动、健康检查、注册到客户端。
  - 手动 Quick Start：下 release tarball → 改 `mcp-server.toml` → `./start-mcp-server.sh` → 客户端注册。
- **构建**：`./build.sh linux-x64 | linux-arm64 | macos-arm64`，产出自包含 tarball（含 Python 3.10 + 全部依赖，目标机无需 pip/系统 Python）。
- **多节点**：应用层做 session affinity，nginx 只做无脑反代。
- 仓库还带 **CLI 客户端**（`mcp-client`）、**Web UI**（`/mcp/web`，管理语义模型）、以及示例 workspace（`dw.orders/users/products/dim_date` + 5 个示例指标）。

### 1.3 DESIGN.md（架构 + tools 清单）
**客户原文链接**：https://github.com/velodb/velodb-mcp-server/blob/main/DESIGN.md （tools 清单与 MCP 架构设计）

来源：velodb-mcp-server/DESIGN.md [@4ea1eb31]

**10 个 MCP Tools（全部只读）**：

| # | Tool | 作用 |
|---|------|------|
| 1 | `get_query_guide` | **强制第一步**，返回工作流指引 |
| 2 | `check_service_health` | **强制第二步**，VeloDB 连通性 + workspace 状态 + 指标数 |
| 3 | `list_metrics` | 列出 workspace 内所有指标 |
| 4 | `list_dimensions_for_metric` | 某指标可用的 group_by 维度 |
| 5 | `query_metric` | **核心语义查询**，MetricFlow 编译→执行 SQL |
| 6 | `list_databases` | 列库（分页）|
| 7 | `list_tables` | 列表（支持 like 模糊、分页）|
| 8 | `describe_table` | 表结构（names/summary/full 三档）|
| 9 | `execute_query` | 只读 SQL 兜底路径 |
| 10 | `reload_semantic_layer` | 手动触发 workspace 重载 |

**架构要点**：
- MCP 协议层（streamable-http, stateless）→ 鉴权层（Bearer→CredentialVerifier→VeloDB，10 分钟凭证缓存，5 次失败锁定 5 分钟）→ 多 workspace 管理器（Store→Manifest→MetricFlow Compiler，60s 轮询变更）→ 连接层（pymysql/aiomysql，每用户独立池）→ VeloDB FE。
- 语义模型 YAML 存在 VeloDB 表里（`active` + `staging` 两级），走 *staging→validate→commit* 工作流，坏模型永不影响线上查询。
- 关键设计决策：`stateless_http=True`（兼容不保持 session 的客户端，如 VeloDB proxy、Claude Desktop）；YAML 存库实现多节点共享状态；编译-only 的 SQL stub；每用户连接池保留 VeloDB 原生用户级授权。

> **对本方案的意义**：`stateless_http=True` + streamable-http + FastMCP 这三点，正好是 AgentCore Runtime 托管 MCP 的官方要求，改造工作量小。

### 1.4 apache/doris-skills（演示用的 skills）
**客户原文链接**：https://github.com/apache/doris-skills （用法见 repo README；应用场景见各 skill 的 SKILL.md description）

来源：github.com/apache/doris-skills [@094da27f]

开放 Agent Skills（`SKILL.md` 格式，Claude Code / Cursor / Codex / Cline 等通用）。**Agent 靠 `description` 自动选择 skill** —— 描述问题，对应 skill 自动加载。分两类：

**A. 面向集群（演示主力）**

| Skill | 作用 | 何时用 |
|-------|------|--------|
| `doris-best-practices` | 建表设计、容量规划、运行时查询排查（37 条规则、7 个用例模板、4 个 sizing 指南）| 写/评审 `CREATE TABLE`、选数据模型、分区分桶策略 |
| `doris-architecture-advisor` | 面向工作负载的架构设计（8 条决策规则、10 个行业实例）| 把业务负载翻译成 Doris 设计（模型选型、导入策略、sizing-first）|
| `doris-debug` | 生产诊断套件：症状路由 + 10 个域技能（query/import/compaction/node/MV/tablet/deployment/data-lake/resource-isolation/cloud）、16 个 case、45 种模式 | 出问题时：慢查询、导入失败、`-235` compaction 错误、OOM/节点崩、MV 不改写、tablet 降级 |
| `doris-profile-reader` | 查询 profile 解读与瓶颈定位（counter 语义、join-order/runtime-filter 诊断、9 个参考指南）| 有 profile/query id/profile URL，想知道到底什么让查询变慢 |

**B. 面向 Doris 源码（贡献者，非演示重点）**

| Skill | 作用 |
|-------|------|
| `doris-repo-review` | 对本地 `apache/doris` clone 做 PR review（跑与 CI Code Review Runner 相同流程）|

- **安装**：`npx skills add apache/doris-skills`，或手动 `cp -r skills/* ~/.claude/skills/`。
- **可选搭档 `doriscli`**：`npm install -g @apache-doris/doriscli`，是 skills 的"手"（跑 SQL、抓 profile、分析 tablet 分布，输出结构化 JSON）；skills 是"脑"。没有 doriscli 时自动回退到纯 MySQL 协议 SQL + FE HTTP API。
- **重要边界**：这些 skills 是 `SKILL.md`/Claude-Code 生态格式，**不是 Amazon Quick 原生 skill 格式**。见第 4 节的落地策略。

---

## 2. 把 Doris MCP Server 改造并部署到 AgentCore Runtime

AgentCore Runtime 对 MCP 容器的**硬性要求**（官方）[@c289f2] [@a34f34]：
- 容器暴露 **`0.0.0.0:8000/mcp`**（streamable-HTTP，官方 SDK 默认路径）
- 推荐 `stateless_http=True`（平台自动补 `Mcp-Session-Id` 头维持会话连续性）
- 鉴权用 OAuth bearer token（Cognito）或 IAM SigV4

### 2.1 需要做的改造（相对开源仓库）

velodb-mcp-server 已经是 FastMCP + streamable-http + `stateless_http=True`，改造点集中在**端口**和**凭证/连接注入**：

1. **端口对齐**：把 `mcp-server.toml` 的 `server.mcp_port` 从 `3000` 改成 **`8000`**（AgentCore 期望），或在容器 `CMD` 里覆盖。路径 `/mcp` 已一致。
2. **Doris 连接走环境变量**：利用 `${ENV_VAR}` 插值，把 `fe_host/fe_port` 指向你的测试 Doris。若 Doris 在 VPC 内，AgentCore Runtime 需要能路由到它（见 2.4 网络）。
3. **凭证策略（关键决策点）**：开源版是"调用方 Bearer = VeloDB user:password"透传。但 **AgentCore 的 Inbound/Outbound Auth 用的是 OAuth JWT**，不是 Doris 的 user:password。两种做法：
   - **(推荐-演示)** MCP Server 内部用一组固定的 Doris 服务账号（从环境变量/Secrets Manager 注入），OAuth 只用于 Quick↔Gateway↔Runtime 的机器鉴权。改造：在 credential 层用注入的服务账号替代"从 Bearer 解析"。演示最省事。
   - **(进阶)** 保留每用户身份透传，把 Quick 用户身份映射到 Doris 用户 —— 复杂，演示阶段不建议。
4. **容器化**：写 `Dockerfile`（AgentCore CLI 的 `configure/launch` 会自动生成一个，但因为这是自包含 tarball 而非标准 pip 包，建议自定义 Dockerfile：把 tarball 解包进镜像、`CMD ["./start-mcp-server.sh"]`、`EXPOSE 8000`）。

> 参考：有社区文章记录过把 stdio-only 的 MCP server 改造成 streamable-http 容器再上 AgentCore 的"踩坑"，velodb 因为本来就是 streamable-http，省掉了最大的一块改造 [@3c57e1]。

### 2.2 两种部署方式

**方式 A — 用改造后的 velodb-mcp-server（贴近客户真实产品）**
```
1. build.sh linux-x64 产出自包含 tarball
2. 自定义 Dockerfile：解包 tarball、暴露 8000、CMD 启动脚本
3. mcp-server.toml：mcp_port=8000，fe_host=${DORIS_FE_HOST} 等
4. agentcore configure（用自定义 Dockerfile）→ agentcore launch
```

**方式 B — 官方最小示例先跑通链路（建议先做，降风险）**
先用 AWS 官方 5 行示例把「Runtime→Gateway→Quick」整条链路跑通，再把 MCP 逻辑替换成 velodb：
```python
# my_mcp_server.py（官方样例）
from mcp.server.fastmcp import FastMCP
mcp = FastMCP(host="0.0.0.0", stateless_http=True)

@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together"""
    return a + b

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```
```bash
pip install mcp bedrock-agentcore bedrock-agentcore-starter-toolkit
npm install -g @aws/agentcore          # AgentCore CLI
agentcore configure --entrypoint my_mcp_server.py --name simple_mcp_server
agentcore launch                        # 打包→上传S3→建Runtime，返回 runtime ARN
```
部署后得到 runtime ARN，形如 `arn:aws:bedrock-agentcore:us-west-2:<acct>:runtime/xxx`。[@e1fa1c] [@c289f2]

### 2.3 本地/远程验证
- 本地：`python my_mcp_server.py` 起在 `localhost:8000`，用 MCP Inspector（`npx @modelcontextprotocol/inspector`）连 `http://localhost:8000/mcp` 看工具列表。
- 远程：用 URL-encode 后的 ARN 拼 `https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<encoded-arn>/invocations?qualifier=DEFAULT`，带 Bearer token，用 MCP Inspector 选 "Streamable HTTP" 测试。[@c289f2]

### 2.4 网络（Doris 可达性）
- AgentCore Runtime 需要能连到你的测试 Doris FE:9030。若 Doris 在公网/可路由 → 直接配 `fe_host`。若在 VPC 内 → 需要给 Runtime 配 VPC 连接，或在注册到 Quick 时用私有 VPC connectivity（见 3）。演示时最简单是用一个公网可达（安全组限制来源）的测试 Doris。

---

## 3. 用 Amazon Quick 连接这个 MCP（含鉴权）

AWS 官方博客《Connect an AgentCore Runtime hosted MCP server to Amazon Quick》给了逐步流程 [@c73886]。核心：**Quick 端用 Connector（MCP 类型），AgentCore 端用 Gateway 桥接**；鉴权分 Inbound（Quick→Gateway，Cognito 用户池 #1）和 Outbound（Gateway→Runtime，Cognito 用户池 #2 + AgentCore Identity OAuth）。

### 3.1 前置条件
- AWS 账号；**Amazon Quick 需 Author 或更高订阅**。
- 有权限创建 IAM、AgentCore、Cognito、CloudWatch 资源。
- 已完成第 2 节的 Runtime 部署（有 runtime ARN）。

### 3.2 步骤（对应官方 Step 2–4）

**Step 2 — 建 AgentCore Gateway（鉴权桥）**
1. **IAM 角色**：use case 选 "Amazon Bedrock AgentCore"，内联策略允许 `bedrock-agentcore:InvokeAgentRuntime`、`InvokeRegistryMcp`、`secretsmanager:GetSecretValue`，Resource 填 Runtime ARN。
2. **Cognito 用户池 #1（Inbound）**：建资源服务器，定义自定义 scope `invoke`。记录 Client ID / Secret / Discovery URL。
3. **Cognito 用户池 #2（Outbound）**：同样建资源服务器 + scope。然后在 **AgentCore Identity → Add Outbound Auth → Create OAuth Client**，填 #2 的 Discovery URL/Client ID/Secret。
4. **建 Gateway**：Inbound Auth 选 JWT + 用已有 IdP（填 #1 的 Discovery URL + Client ID）；Permissions 用上面的 IAM 角色；**Target 注册 MCP Server**，授权类型选 **OAuth Client**（MCP 协议目前只支持 OAuth），MCP 端点用：
   ```
   https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{URL编码的Runtime_ARN}/invocations?qualifier=DEFAULT
   ```
   Outbound 用刚建的 OAuth client。等 Gateway 和 Target 都变 **Ready**。

**Step 3 — 在 Amazon Quick 注册 MCP 集成**
1. Amazon Quick → **Connectors → Create for your team → 选 Model Context Protocol (MCP)**。
2. 填名称、描述、**MCP Server Endpoint = Gateway 的 Resource URL**。连接类型可选 **private VPC connectivity**（限制网络可见性，更安全）。
3. **Authenticate 页**：填 Gateway 上配置的 Inbound Auth 信息。个人用户场景选 **User authentication**，系统集成场景选 **Service authentication**（官方样例用 User + Cognito）。填 Client ID / Secret / Token URL / Authorization URL：
   - Token URL：`https://{去掉下划线的user_pool_id}.auth.{REGION}.amazoncognito.com/oauth2/token`（注意：`us-west-2_qNBcTlLbR` → `us-west-2qNBcTlLbR`）
   - Authorize URL：同上把 `token` 换成 `authorize`
4. **Create and Continue** → 系统 sync 工具，Action 变 **Available/Ready** 后能看到从 MCP 同步来的工具（`list_databases`、`execute_query`、`query_metric` 等 10 个）。

**Step 4 — 测试**
- 用 **Test Action APIs** 验证工具可达。
- 在 chat agent 里 **Link Actions** 选刚建的集成，然后自然语言测试（如"列出我集群里的所有表"）。

> 补充：Quick 现在也支持从组织的 **AWS Agent Registry** 直接搜索/一键接入已注册的 MCP server，连接信息自动带入，省去手填 URL [@b65eb5]。若你的账号已用 Agent Registry，可以走这条更简的路。授权深化（把 SSO 身份变成可执行的权限规则）见官方 defense-in-depth 文章 [@e5eb25]。

---

## 4. 挂载客户提供的 skills 做演示

**关键认知**：`apache/doris-skills` 是 **Claude-Code 生态的 `SKILL.md` 格式**（靠 `description` 自动路由，配 `doriscli`），**不是 Amazon Quick 的原生 skill**。所以"搭上 skill 演示"有两条路线：

### 路线 1 —（推荐，最贴合 Quick 演示）把 skill 的决策逻辑注入 Quick chat agent 指令
- 在 Quick 里创建一个 **chat agent**，Link 上面第 3 节的 MCP Action。
- 把 doris-skills 中演示相关 skill（如 `doris-best-practices`、`doris-debug`、`doris-profile-reader`）的 `SKILL.md` 决策逻辑，**提炼进 agent 的 instructions / 关联到 Space 作为参考文件**。
- 效果：用户问"帮我评审这段建表 DDL"或"这个查询为什么慢，这是 profile"，agent 依据 skill 逻辑 + 通过 MCP 工具实时查 Doris，给出结论。
- 这条路线 100% 在 Quick 内闭环，最适合给客户演示 Quick 的价值。

### 路线 2 —（贴合客户原始用法）在 Claude Code 等 agent 里用 skill + 连 MCP
- 如果演示目的是展示"客户维护的 skill 原样可用"，则在 Claude Code/Cursor 里 `npx skills add apache/doris-skills`，同时把 MCP server 注册进去（本地直连 velodb-mcp-server，或连 AgentCore 端点）。
- 这条路线不经过 Quick，是 skill 的"原生"用法，可作为对照演示。

### 演示脚本建议（用仓库自带示例数据）
velodb-mcp-server 自带示例 workspace（`dw.orders/users/products` + 指标 `total_amount`/`order_count` 等）。演示话术：
1. "check the service health" → 验证连通（预期 `"velodb":"connected"`）
2. "show me the tables in my cluster" → 元数据发现
3. "What is the total order amount by channel?" → 语义查询（`query_metric`）
4. 结合 skill："评审这张表的分区分桶设计" / "这个查询慢在哪（贴 profile）"

### 4.5 演示叙事：MCP 与 skill 如何协同（重要）

一个常见误解是"MCP 是只读读数据、skill 是建表/debug 最佳实践，方向完全不同"。实际上两者不是两个方向，而是**同一个栈的两层**，合起来才构成完整能力：

| 层 | 是什么 | 角色 |
|----|--------|------|
| **Skill**（doris-skills）| 决策逻辑 / 专家判断（建表规则、debug playbook、profile 解读）| **"大脑"** —— 知道该看什么证据、怎么解读、给什么结论 |
| **MCP**（velodb-mcp-server 的 10 个只读工具）| 对真实 Doris 的只读访问（`execute_query` 跑 SELECT/SHOW/DESCRIBE/EXPLAIN、`describe_table`、元数据、profile）| **"手和眼"** —— 去真实集群把证据抓回来 |

**为什么 skill 不接库也能"生成最佳实践"，但接了库才有价值**：doris-skills README 明确说明 skill 本身靠 **`doriscli`** 当"手"（跑 SQL、抓 profile、分析 tablet 分布，输出结构化 JSON），没有 doriscli 时自动回退到纯 MySQL 协议 SQL + FE HTTP API；skill 自己只是"读这些 JSON 做判断的脑子"。不接库时，skill 只能给**通用、悬空**的建议；一旦通过 MCP 连上真实 Doris，skill 就能**基于真实 schema / 数据分布 / profile** 给出具体、有依据的结论。

**本方案的关键替换**：在 AgentCore + Quick 架构里，让 **MCP 的只读工具充当 skill 原本由 doriscli 扮演的那只"手"**。Quick 里的 chat agent = skill 决策逻辑（写进 agent 指令）+ MCP 只读工具（Link 的 Actions）。agent 用 skill 的脑子决定"要看哪张表的 schema / 读哪个 query 的 profile"，再调 MCP 工具去真实 Doris 抓回来。

#### 读 vs 写：必须诚实区分的边界
velodb-mcp-server 是**故意只读**的（DML/DDL/多语句/导出全部拦截），因此两类 skill 的"执行闭环"不同：

- **诊断/优化类（`doris-debug`、`doris-profile-reader`）**：诊断本身天然只读（读 profile、SHOW 状态、tablet 分布），MCP 只读工具**完美契合，可完整闭环** —— 发现慢查询 → MCP 抓 profile/SHOW → skill 解读 → 给出结论。✅ 最强演示场景。
- **建表/设计类（`doris-best-practices`、`doris-architecture-advisor`）**：skill 需要**读**现状（现有表结构、数据量）给有依据的建议，这部分 MCP 只读能做；但最终产出的 `CREATE TABLE`/`ALTER` 是**写操作**，只读 MCP 不执行。闭环为 **MCP 读现状 → skill 生成推荐 DDL → 人工执行（human-in-the-loop）**。演示价值在于"给出了基于真实集群的精准建议"，而非自动改库。

> 若要让建表也自动执行，需另开一条可写路径（不是这个只读 MCP），演示阶段不建议，也有风险。

#### 故事线：两条 track，同一个栈串起来
统一叙事（一句话）：

> **MCP 让 agent「看得见你的真实集群」，skill 让 agent「有 Doris 专家的判断力」—— 合起来 = 一个对着你真实集群做推理的 Doris 专家，而不是背通用文档的聊天机器人。**

| Track | skill | 演示闭环 | 执行边界 |
|-------|-------|----------|----------|
| **A. 诊断 / 优化** | `doris-debug` + `doris-profile-reader` | 只读 MCP **完整闭环**：抓 profile/SHOW → 解读 → 结论 | 全程只读，无需人工干预 ✅ |
| **B. 设计 / 评审** | `doris-best-practices` + `doris-architecture-advisor` | MCP 读现状 → skill 推荐 DDL → 人工执行 | 读=MCP，写=人工（HITL）|

两条 track 用**同一个 Quick chat agent**（同一套 MCP Actions + 注入的 skill 逻辑），只是触发的用户问题不同，从而在一次演示里展现"诊断"和"设计"两个维度。

> ⚠️ **修正（见 §4.6 核实结果）**：上表 Track A 标注的"只读 MCP 完整闭环"需要一个前提 —— skill 的 profile 分析依赖 FE HTTP 管理 API 抓 profile，而 velodb MCP 只做 SQL、不暴露该 HTTP 端点。因此 Track A 用**原生 MCP 无法自动抓 profile**，需按 §4.6 的方式补齐（用户粘贴 profile / 给 MCP 加 profile 抓取工具）。Track B 则确认可用原生 MCP 闭环。

### 4.6 skill ↔ MCP 能力映射（核实结果）

对 4 个演示相关 skill 的 `SKILL.md` + `CLI-CONTRACT.md` + `cli-investigation.md` 做了逐条核实。结论：**skill 不接 doriscli 时会回退到"纯 MySQL 协议 SQL + FE HTTP API"，这条回退路径就是 MCP 顶替 doriscli 的锚点。** 但覆盖并不均匀。

**核实结论一句话**：**Track B（设计/评审）几乎 100% 被 velodb MCP 的只读 SQL 工具覆盖，可原生闭环；Track A（诊断）的 profile 分析有一个真实 gap —— profile 靠 FE HTTP API 抓取，MCP 只做 SQL，抓不到。**

#### 映射表：skill 期望的证据 → velodb MCP 工具

| skill 需要的证据 | doriscli 命令 | 无 doriscli 的原生回退 | velodb MCP 覆盖 | Track |
|------------------|--------------|------------------------|-----------------|-------|
| 表结构 DDL | `doriscli sql "SHOW CREATE TABLE"` | `SHOW CREATE TABLE db.t` | ✅ `execute_query`(SHOW) | B |
| 查询计划 | `doriscli sql "EXPLAIN ..."` | `EXPLAIN <query>` | ✅ `execute_query`(EXPLAIN) | A/B |
| 数据倾斜 | `doriscli tablet db.t` | `SHOW DATA SKEW FROM db.t` | ✅ `execute_query`(SHOW) | A/B |
| 列基数统计 | (tablet 内联 ndv) | `SHOW COLUMN STATS db.t` | ✅ `execute_query`(SHOW) | A/B |
| 分区列表 | — | `SHOW PARTITIONS FROM db.t` | ✅ `execute_query`(SHOW) | A/B |
| 库/表/列发现 | — | `SHOW DATABASES/TABLES`, `DESCRIBE` | ✅ `list_databases`/`list_tables`/`describe_table` | A/B |
| 连通性检查 | `doriscli auth status` | MySQL/HTTP 探活 | ⚠️ 部分：`check_service_health` 覆盖 VeloDB 连通，但不含 BE 存活明细 | A |
| 慢查询趋势 | `doriscli profile history` | `SELECT ... FROM audit_log`（若可查） | ⚠️ 部分：若 `audit_log` 是可查表，`execute_query` 的 SELECT 可覆盖 | A |
| **单条 profile** | `doriscli profile get <qid>` | **FE HTTP** `GET /rest/v2/manager/query/profile/text/<qid>` | ❌ **gap**：MCP 只做 SQL，不暴露 FE HTTP 管理 API | A |
| **活跃/近期查询列表** | `doriscli profile list [--active]` | **FE HTTP** `GET /rest/v2/manager/query/query_info` | ❌ **gap**：同上，HTTP-only | A |
| **profile 对比** | `doriscli profile diff <slow> <fast>` | 由两份 HTTP profile 派生 | ❌ **gap** | A |
| **带 profile 执行 SQL** | `doriscli sql ... --profile` | 跑 SQL 再 HTTP 抓 profile | ❌ **gap**：`execute_query` 不返回 profile | A |

#### 关键 gap 与补齐方式

**Gap 本质**：Doris 的查询运行时 profile（doris-profile-reader 和 doris-debug 的 `query` 域最核心的证据）走 **FE HTTP 管理 API**（`/rest/v2/manager/query/...`），而 velodb MCP 的 `execute_query` 只接受 `SELECT/SHOW/DESCRIBE/EXPLAIN` 这类 SQL，**不代理 FE 的 HTTP 端点**。所以原生 MCP 抓不到 profile。

**三种补齐方式（推荐第 2 种）**：

| 方式 | 做法 | 演示可用性 | 改造量 |
|------|------|-----------|--------|
| ① 用户粘贴 profile | doris-profile-reader 明确接受 "profile URL/text"，用户把 profile 文本贴进 Quick，skill 直接解读 | 今天即可演示，零改造 | 无 |
| ② **给 MCP 加 profile 工具**（推荐）| 在 velodb-mcp-server 加一个只读工具 `get_query_profile(query_id)` / `list_recent_queries()`，内部调 FE HTTP `/rest/v2/manager/query/...`（MCP 本来就有 FE 连接）| 完整自动闭环 | 小：加 1–2 个 FastMCP tool |
| ③ EXPLAIN + audit_log | 只用 `EXPLAIN`（执行前计划）+ 查 `audit_log`（历史趋势），不抓运行时 profile | 证据不完整，只能做"计划级"诊断 | 无 |

**对演示故事线的修正**：
- **Track B**：原生 velodb MCP 即可完整闭环（读 DDL/SHOW → skill 评审 → 人工执行 DDL），**无需改造**。
- **Track A**：若要"发现慢查询 → 自动抓 profile → 解读"的完整闭环，需按方式 ②给 MCP 加 profile 抓取工具；否则用方式 ① （用户粘贴 profile）也能演示 skill 的解读能力，只是少了"自动去集群抓"这一环。

#### Quick agent 里的"能力映射"落地
把 skill 逻辑注入 Quick chat agent 指令时，需要加一层翻译规则，把 skill 期望的 doriscli 调用改写成 MCP 工具调用，例如：
- "跑 `SHOW CREATE TABLE`" → 调 `execute_query("SHOW CREATE TABLE db.t")`
- "查 `doriscli tablet`" → 调 `execute_query("SHOW DATA SKEW FROM db.t")` + `execute_query("SHOW COLUMN STATS db.t")`
- "抓 `profile get <qid>`" → 调新增的 `get_query_profile(qid)`（方式②），或提示用户粘贴 profile（方式①）
并保留 skill 的"证据优先"硬门槛：没有证据前只输出调查计划和要跑的命令，不下结论。

---

## 5. 落地路线图（建议顺序）

| 阶段 | 动作 | 产出/验收 |
|------|------|-----------|
| P0 | 用官方最小示例跑通 Runtime→Gateway→Quick 整条链路 | Quick 里能看到 add_numbers 工具并调用成功 |
| P1 | 改造 velodb-mcp-server：端口 8000、Doris 连接走 env、服务账号凭证、自定义 Dockerfile | 本地 MCP Inspector 能列出 10 个工具、`check_service_health` 连通你的 Doris |
| P2 | `agentcore launch` 部署改造版；配 Gateway（Inbound/Outbound Cognito）；VPC 网络打通到 Doris | 远程 Inspector 用 Bearer token 能调 `list_tables` 拿到真实表 |
| P3 | Quick Connector 注册 + chat agent Link Actions | Quick 对话里能自然语言查 Doris |
| P4 | 注入/关联 doris-skills 决策逻辑，打磨演示脚本 | 端到端演示（建表评审 / 慢查询诊断 / 语义查询）|

---

## 6. 待确认 / 风险点

1. **凭证映射**：AgentCore 用 OAuth JWT，Doris MCP 原生用 `user:password` Bearer。演示建议用固定 Doris 服务账号 + Secrets Manager 注入（第 2.1-3）。是否接受？
2. **网络**：你的测试 Doris 是公网可达还是 VPC 内？决定 Runtime 是否需要 VPC 配置 / Quick 是否用 private VPC connectivity。
3. **Region**：AgentCore + Quick 需在同一支持的 Region。你计划用哪个 Region？
4. **Quick 订阅**：确认你的 Quick 账号是 Author 或以上。
5. **skill 呈现方式**：路线 1（注入 Quick agent 指令）还是路线 2（Claude Code 原生 skill）作为主演示？或两者都要（Quick 演示 + 对照）。
6. **Gateway 目前的成熟度**：有第三方记录 Gateway 前置到 Quick 的 `tools/list` 传播在某些情况下不稳定（实验性）[@84d1a4]；官方博客路径是可用的，建议按官方 Cognito 流程走。

---

### 附：核心来源
- VeloDB MCP 官方文档（Overview / SOP）[@627ec8cf5328]
- velodb-mcp-server README [@497370ef] / AGENTS.md 安装 playbook [@2a75f82d] / DESIGN.md 架构与 10 tools [@4ea1eb31]
- apache/doris-skills README（skill 清单与用法）[@094da27f]
- AWS 官方博客：把 AgentCore Runtime 托管 MCP 接入 Amazon Quick（含逐步鉴权）[@c73886]
- AWS 文档：AgentCore Runtime 部署 MCP server [@c289f2] / Prescriptive Guidance 部署模式 [@a34f34]
- Amazon Quick MCP client 连接说明 [@30b7f4]、Agent Registry 一键接入 [@b65eb5]、授权最佳实践 [@e5eb25]
