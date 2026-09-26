# 进度

## 当前状态

<!-- 每个任务结束时覆盖这一块；下面的日志只追加不修改 -->

- **阶段**：P1 执行中（subagent-driven，分支 `p1-mcp-server`）；已完成 T1.1–T1.7
- **进行中**：无（T1.7 已提交，等待任务 review）
- **下一步**：T1.8 本地 E2E：12 个工具、profile flow、3 种错误情况（`scripts/mcp_smoke.py flow`）
- **阻塞**：无
- **已创建的 AWS 资源**：无（`infra/state.env` 中只有部署前查到的已有资源 ID）
- **Doris 变更**：无（spec 阶段只用 `demo_ro` 做过只读查询）

## 日志

### 2026-09-26 spec 骨架
- 用户确认决策：D2 = Enterprise，其余采用推荐方案（见 requirements.md 文末）。
- 用户要求按 spec 推进，保证断线后可以继续 → 新建 `CLAUDE.md`（恢复协议）、`specs/doris-mcp-quick/`（README / requirements / design / tasks / progress / plans）、`infra/`（lib.sh、10/20/25/30 脚本、policies、state.env）、`scripts/`（check-secrets、mcp_smoke、get-gw-token、render-*）、`spike/p0-mcp/`、`.gitignore`、`.env.example`。
- 只读核实（无变更）：VPC 路由表、子网 AZ ID、Doris EC2 没有 instance profile、doris-demo-sg 规则、agentcore CLI 0.30.0 可用、AWS CLI 支持 Gateway IAM 出站。
- upstream @f235832 按锁定依赖安装后，离线测试全部通过（临时 venv `/tmp/upenv`，P1 会在仓库 `.venv` 中重建）。

### 2026-09-26 P1 代码起草 + 实测
- P1 全部代码按 TDD 在 `/tmp/p1-draft` 起草（临时目录，重启会丢；**权威版本是 `plans/P1-mcp-server.md` 里嵌入的代码**）：77 个新测试 + upstream 离线测试通过。
- 用 `demo_ro` 连 Doris 公网 IP 实测：12 个工具可调用；`mcp_smoke.py flow` 6/6；错误密码 → FE `UNAUTHENTICATED`、health `doris: unavailable`、list_databases `CONNECTION_ERROR (1045)`；日志里真实密码命中 0 次。
- 实测发现并已写入 spec（design v0.2.2 / requirements v1.1）：`/api/profile/text` 找不到 id 时返回纯文本 `query id … not found`；summary 加严后真实 profile 103 487 → 9 109 字符；Doris 保留 trace 注释；不挂 `RequestLoggerMiddleware`；`rapidfuzz` 没有 manylinux2014 wheel，CLI 自动回退到 `manylinux_2_28`（约 107 MB）。
- P1 计划按「从零照计划执行」完整模拟了一遍（每步红/绿预期、测试数、启动冒烟），修正了 T1.3/T1.4 的红阶段预期、T1.7 的启动命令（`env -i` 不能直接 `exec` shell 内建命令）和 T1.8 的 grep 过滤。
- `docs/改造方案.md`（v0.1，用户 review 过的原稿）先单独提交保留在 git 历史里，然后删除；后续以 `design.md` 为准。
- 本地 `git init`，提交 spec。

### 2026-09-26 继续指南
- 应用户要求新增根目录 `RESUME.md`：下次如何继续（启动方式、第一句话示例、GATE / secret 注意事项、查看进度的命令、常见情况）；在 `CLAUDE.md` 的关键路径表中加入链接。

### 2026-09-26 T1.1 vendoring upstream + pyproject（P-07）
- `git archive f235832`（tag `velodb-mcp-server-0.3.0`）vendored 594 个文件到 `mcp-server/`；新增 `UPSTREAM.md` 和 `pyproject.toml`（P-07），共 596 个新文件，无 upstream 文件被改动。
- 新建仓库 `.venv`（Python 3.12.3），按 `pyproject.toml` 锁定版本安装：`fastmcp==3.4.4`、`starlette==1.3.1`、`httpx==0.28.1`（均与期望一致）。
- upstream 离线测试全部通过：`bash mcp-server/test/run_all_tests.sh --offline` 收尾 `🎉 All tests passed!`。
- aarch64（`manylinux_2_28`）模拟打包体积 106 MB（期望「约 107 MB」），符合 AgentCore CodeZip 250 MB 上限。
- 本任务 commit 即 upstream 原始版本（`git log --oneline -- mcp-server | tail -1`）。

### 2026-09-26 T1.2 P-02：`ClusterConfig.fe_http_port`
- TDD：新建 `test_agentcore_config.py`，4 个测试初始红（`AttributeError`），实现后全绿。
- 修改 `mcp-server/src/config/loader.py:61`，添加 `self.fe_http_port: int = int(server.get("fe_http_port", 8030))`。
- upstream 离线测试仍全部通过：`🎉 All tests passed!`
- T1.1 的 upstream 原始版本 commit 是 `e859681`（`git diff e859681 -- mcp-server/src` = 全部补丁）。
- 提交：1 个 commit，仅修改 loader.py 1 行 + 新增测试文件。

### 2026-09-26 T1.3 P-03：store/bootstrap 服务账号兜底
- TDD：新建 `test_agentcore_store_creds.py`，9 个测试初始红（`AttributeError: module 'store.store' has no attribute 'clear_service_credentials'` 等），共 16 个错误（测试 + tearDown）。
- 实现：在 `store.py` 中 `set_request_credentials()` 后插入全局变量 `_service_creds` + 三个函数 `set_service_credentials() / clear_service_credentials() / get_effective_credentials()`；修改 `_get_conn()` 从 `_request_creds.get()` 改为 `get_effective_credentials()`。
- bootstrap.py：修改 `pre_validate_physical()` 内的 import 从 `_request_creds` 改为 `get_effective_credentials`，读取凭证处也改用后者。
- 验证：9 个新测试全绿；与 T1.2 的 4 个测试共 13 个全绿；upstream 离线测试 `🎉 All tests passed!`；`grep -n "_request_creds" mcp-server/src/store/bootstrap.py` 无输出（bootstrap 不再直接读 _request_creds）。
- 提交：1 个 commit，修改 store.py + bootstrap.py，新增测试文件 + 更新任务清单与进度日志。

### 2026-09-26 T1.4 P-04：`create_server(service_credentials=, workspace_dir=)`
- TDD：新建 `test_agentcore_service_mode.py`，10 个测试初始红（8 个 TypeError: unexpected keyword argument，1 个 FAIL）。
- 实现：6 处修改 server.py（签名、docstring、workspace 参数、凭证设置、pool 逻辑、MCP auth 禁用），共 +26/-4 行。
- 验证：10 个新测试全绿；与 T1.2/T1.3 的 13 个测试共 23 个全绿；upstream 离线测试 `🎉 All tests passed!`；secrets check OK。
- 提交：1 个 commit，修改 server.py，新增测试文件 + 更新任务清单与进度日志。

### 2026-09-26 T1.5 P-05：profile 工具 (`src/tools/profile.py`)
- TDD：从 brief 提取 2 个 Python 代码块（test 349 行 + module 376 行），使用 Python 脚本原样抽取并写入文件。
- 实现：`FeHttpTarget`（frozen dataclass）、`list_recent_queries()`、`get_query_profile()`、`summarize_profile()`、`register_profile_tools()`。
- 验证：29 个新测试全绿（`test_agentcore_profile.py`）；与前 23 个共 52 个全绿；upstream 离线测试 `🎉 All tests passed!`；secrets check OK。
- git diff：`mcp-server/src/tools/profile.py` (+376) + `mcp-server/test/test_agentcore_profile.py` (+349)。
- 提交：1 个 commit，新增两个文件 + 更新任务清单与进度日志。

### 2026-09-26 T1.6 P-06：runtime settings + config + `build_server`（12 个工具 / Draft 7）
- TDD：从 brief 用 Python 脚本按 fenced block 顺序抽取并原样写入 `test_agentcore_settings.py`（19 项测试之一部分）+ `test_agentcore_tools.py`；先运行确认两个模块均报 `ModuleNotFoundError: No module named 'agentcore_ext'`，再写实现。
- 新增：`mcp-server/config/mcp-server.toml`（P-06 运行配置：`query_timeout_seconds=50`、`query_max_rows=2000`、`pool_max_size=5`）、`mcp-server/src/agentcore_ext/__init__.py`、`settings.py`（`SettingsError`、`Settings` frozen dataclass、`load_settings()`：env / Secrets Manager 凭证，端口与 scope 校验，密码永不出现在异常消息里）、`app.py`（本任务仅 `build_server()`，串联 `create_server` 服务模式 + `register_profile_tools`）。
- 验证：19 个新测试全绿；与 T1.1–T1.5 共 71 个 agentcore 测试全绿；upstream 离线测试 `🎉 All tests passed!`；`bash scripts/check-secrets.sh` → `check-secrets: OK (638 files scanned)`；6 个 whole-file 代码块与 brief 逐字节相等（Python 脚本比对确认）。
- 提交：1 个 commit，新增 `config/`、`src/agentcore_ext/` 三个文件、两个测试文件 + 更新任务清单与进度日志。

### 2026-09-26 T1.7 P-01：`/ping`、stderr 日志、`main()`、`mcp_server.py` + HTTP 测试 + 启动冒烟
- TDD 顺序纠正：因误操作曾一次性写入全部 3 个文件（含完整版 `app.py`），发现后用只读的 `git show HEAD:...` 还原出 T1.6 提交的过渡版 `app.py`（未用 `git checkout --`/`reset`），补跑一次真正的红：`Ran 6 tests` / `FAILED (errors=6)`，全部 `AttributeError`（`MCP_PATH`、`configure_logging`），随后再覆盖为完整版。
- 新增/覆盖：`test_agentcore_app.py`（新，6 个测试）、`app.py`（整体替换：`MCP_PATH`、`HTTP_MIDDLEWARE`（仅挂 `CharsetMiddleware`）、`build_server` 新增 `GET /ping`、`configure_logging()`、`main()`）、`mcp_server.py`（AgentCore Runtime entrypoint）；三个整文件块与 brief 逐字节相等（Python 脚本比对，`equal=True`）。
- 验证：新测试 6 个全绿；累计 `discover -p 'test_agentcore_*.py'` 共 `Ran 77 tests` / `OK`；upstream 离线测试 `🎉 All tests passed!`；`bash scripts/check-secrets.sh` → `check-secrets: OK (640 files scanned)`。
- 启动冒烟（不连 Doris）：(1) `DORIS_PORT=abc` → stderr 打印 `Invalid configuration: DORIS_PORT must be an integer, got 'abc'`，`exit=2`；(2) `MCP_PORT=18765` 正常启动，`/ping` 返回 `{"status":"Healthy","time_of_last_update":...}`，`mcp_smoke.py list --expect 12` → `tools: 12`，日志含 `Auth: service mode, MCP auth delegated to the edge; Doris user nobody` 与 `Doris MCP for AgentCore: Doris 127.0.0.1:1 (http 1) as nobody, profile scope all, workspace /tmp/p1-boot-ws`；日志中未出现密码；按端口 `ss -ltnp | grep ':18765 '` 找到 pid 后 `kill`，停止后端口确认已释放；`/tmp/p1-boot-ws`、`/tmp/p1-boot.log` 事后清理。
- 提交：1 个 commit，新增 `mcp_server.py`、`test_agentcore_app.py`，整体替换 `app.py` + 更新任务清单与进度日志。
