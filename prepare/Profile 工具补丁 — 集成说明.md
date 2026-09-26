# Profile 工具补丁 — 集成说明

给 `velodb-mcp-server` 增加两个只读工具，补齐 Track A（诊断）的 profile 抓取 gap：
- `get_query_profile(query_id)` —— 抓单条查询运行时 profile 文本
- `list_recent_queries(limit)` —— 列出近期/活跃查询及其 query_id

> 依据：§4.6 核实结果 —— Doris 的查询 profile 走 FE HTTP 管理 API（`/rest/v2/manager/query/...`），velodb MCP 的 `execute_query` 只做 SQL、不代理该 HTTP 端点。本补丁按"方式②"补上这条路径。

---

## 补丁包含 3 处改动

### 1. 新增文件 `src/tools/profile.py`
见同目录 `profile.py`。仿照 `src/tools/query.py`、`discovery.py` 的约定：
- async 函数，返回 `core.response` 的 JSON 信封（`success_response`/`error_response`/`ErrorCode`）
- 通过 FE HTTP 管理 API（默认端口 8030）用 HTTP Basic（调用方自己的 Doris user:password）读取 profile
- 失败（404/401/超时）作为**结构化证据**返回，而不是抛错 —— 契合 doris-skills 的"证据优先/连接优先"规则

依赖：`aiohttp`（若仓库未含，加入 `requirements.txt`；aiomysql 已在用，异步 HTTP 用 aiohttp 最自然）。

### 2. `src/core/connection.py` 附近的 `ClusterConfig` 增加 `fe_http_port`
`profile.py` 读取 `cluster.fe_http_port`（默认 8030）。在 `config/loader.py` 的 `ClusterConfig` 里加一个字段（与现有 `fe_host`/`fe_mysql_port` 并列）：

```diff
 @dataclass
 class ClusterConfig:
     fe_host: str = "127.0.0.1"
     fe_mysql_port: int = 9030
+    fe_http_port: int = 8030          # Doris FE HTTP 管理 API 端口（profile 抓取用）
     pool_min_size: int = ...
```

对应 `mcp-server.toml`：

```diff
 [server]
 mcp_name = "velodb-mcp-server"
 mcp_host = "0.0.0.0"
 mcp_port = 3000            # AgentCore 部署时改 8000（见主报告 §2.1）
 fe_port = 9030             # FE MySQL 协议端口
+fe_http_port = 8030        # FE HTTP 管理 API 端口（get_query_profile 用）
```

> 若 Doris FE 的 HTTP 端口非默认（如自定义 `http_port`），改这里即可。VeloDB Cloud 的 HTTP 端点地址以其控制台为准。

### 3. `src/server.py` 注册 2 个新工具
在注册现有 10 个工具（`get_query_guide`、`execute_query` 等）的地方，按同样的模式加两个。velodb 的工具是"从 Bearer 解析出 user/password → 拿到该用户的 cluster/pool → 调 tool 函数"。profile 工具不需要 pool（走 HTTP），只需要 `cluster + user + password`：

```python
# src/server.py —— 在 register 现有工具的附近

from tools.profile import get_query_profile, list_recent_queries

@mcp.tool()
async def list_recent_queries_tool(limit: int = 20) -> str:
    """List recent or currently-running Doris queries and their query_ids.

    Use this to find a query_id when the user describes a slow-query symptom
    but does not provide an id. Read-only (FE manager HTTP API).
    """
    cluster, user, password = _resolve_caller()   # 复用现有 Bearer→凭证解析
    return await list_recent_queries(cluster, user, password, limit=limit)

@mcp.tool()
async def get_query_profile_tool(query_id: str) -> str:
    """Fetch the full runtime profile text for a Doris query_id.

    Returns operator timers, counters, RuntimeFilterInfo, and scanned tables —
    the evidence the doris-profile-reader / doris-debug skills consume.
    Read-only (FE manager HTTP API).
    """
    cluster, user, password = _resolve_caller()
    return await get_query_profile(cluster, user, password, query_id)
```

> `_resolve_caller()` 是占位：用仓库里已有的"从请求 Bearer 取 user/password + 选中 cluster"的现成逻辑（`CredentialVerifier` / pool factory 附近）。关键点是 profile 工具复用**同一套凭证与身份**，不引入新的 admin 凭证。

---

## 与 skills 的对应关系（doriscli → 新 MCP 工具）

| skill 期望（CLI-CONTRACT.md）| 原 doriscli | 本补丁提供的 MCP 工具 |
|------------------------------|-------------|----------------------|
| `profile get <qid>` | `doriscli profile get` | `get_query_profile(query_id)` |
| `profile list [--active]` | `doriscli profile list` | `list_recent_queries(limit)` |
| `profile diff <slow> <fast>` | `doriscli profile diff` | 调 `get_query_profile` 两次，由 agent/skill 对比（或后续再加 `diff` 工具）|
| `profile history "<pat>"` | `doriscli profile history` | 走 `execute_query` 查 `audit_log`（若可查）|

`SHOW CREATE TABLE`、`EXPLAIN`、`SHOW DATA SKEW`、`SHOW COLUMN STATS` 等仍由现有 `execute_query` 覆盖（Track B 全量、Track A 计划级），无需改动。

---

## 部署与验证

1. 把 `profile.py` 放到 `src/tools/`，应用上面 3 处 diff，`aiohttp` 加进 `requirements.txt`。
2. 本地起服务后，用 MCP Inspector 应能看到 **12 个工具**（原 10 + 2 新增）。
3. 冒烟测试：
   - `list_recent_queries(limit=5)` → 返回近期查询与 query_id
   - 取一个 query_id → `get_query_profile(query_id)` → 返回 profile 文本
4. 打包进 AgentCore 镜像（见主报告 §2.1/§2.2），FE HTTP 端口需从 AgentCore Runtime 可达（与 9030 一并放通）。

## 安全与边界
- 全部只读（仅 HTTP GET manager 端点），符合 velodb "只读" 定位与 skills 的安全策略。
- 沿用调用方 Doris 身份（HTTP Basic），不新增共享凭证。
- 网络：Runtime 需能同时到达 Doris FE 的 9030（SQL）与 8030（profile HTTP）。若 Doris 在 VPC 内，两个端口都要在 Runtime 的 VPC 出站/安全组里放通。
- 未改动任何写路径；建表类（Track B）产出的 DDL 仍由人工执行。
