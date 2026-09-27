# 进度

## 当前状态

<!-- 每个任务结束时覆盖这一块；下面的日志只追加不修改 -->

- **阶段**：P2 执行中（Subagent-driven，implementer / reviewer 全部用 Opus 5.5；计划 `plans/P2-doris.md` 已通过用户 review）。P0、P1 已完成并本地合并到 `main`
- **进行中**：无（分支 `p2-doris`；T2.1、T2.4、T2.5 已完成，T2.2 尚未开始）
- **下一步**：T2.2 **[GATE]**（`doris/01_mcp_user.sql` + `doris/admin_sql.py` + `doris/apply-admin-sql.sh`：root 建 `mcp_svc` 并授权，secret 经管道进入 python，只在内存里填进 SQL；语句白名单；输出 mask；先给用户看 dry-run，确认后才 `APPLY=1`）。执行顺序 T2.1 ✅ → T2.4 ✅ → T2.5 ✅ → T2.2 → T2.3 → T2.6 → T2.7；4 个 GATE（T2.1 建 secret —— 已完成、T2.5 root 发布 —— 已完成、T2.2 root 建 `mcp_svc` 并授权、T2.3 以 `mcp_svc` 写探针）每次都先给用户看 dry-run，确认后才 `APPLY=1`。T2.7 = P1 整体评审 ①–④ + P0 评审 M-2、M-8（纯离线）；P0 评审 M-1 / M-3 / M-4 已写进 T4.1 / T4.4 / T3.4，M-5、M-6、M-7、M-9 不做
- **P3 / P4 路径决策**：P4 主路径 = Cloud Connector + **User auth**（client A），备份 = Cloud Connector + **Service auth**（client B），两条在 T0.7 都已跑通。**Local stdio 整个项目不做**（D9，用户 2026-09-26 决定；R-11 取消，原 T4.2 删除，T4.4 改为两个连接器各跑一次）。T3.1 加收紧 CDK 默认角色通配权限、T3.2 加 deploy 前确认 `disableTransactionSearch`、T3.4 加经 Gateway 逐次测耗时；T5.5 的「预热脚本」改为「演示前冒烟脚本」
- **阻塞**：无
- **已创建的 AWS 资源**：SG `doris-mcp-rt`、`doris-mcp-vpce`；`doris-demo-sg` 新增 9030/8030 ← `RT_SG`；VPC endpoints S3 / logs / secretsmanager；CloudFormation 栈 `AgentCore-dorismcp-default`（Runtime `dorismcp_dorismcp` + CDK 生成的执行角色）；Cognito user pool `doris-mcp-quick`（域名、resource server `doris-mcp`、client A `quick-user` / B `quick-service`、用户 `demo`）；Secrets Manager `doris-mcp/cognito-demo-user`、`doris-mcp/mcp_svc`（T2.1）；IAM 角色 `doris-mcp-gateway-role`（内联策略 `invoke-dorismcp-runtime`）；Gateway `doris-mcp-gw`（target `doris`）；账号级 X-Ray indexing rule `Default` = 100%（T0.4 时 CLI 自动修改，用户决定保持现状）—— ID 见 `infra/state.env`
- **Doris 变更**：T2.5 以 root 新建库 `system_mcp` 和 3 张表 `workspace_metadata`、`active_store_ecom`、`staging_store_ecom`；workspace `ecom` 的 `semantic_version=2`，active 10 个文件，staging 为空；没有执行任何 GRANT，`ecom` 库未改动。回滚（需 GATE）：root 执行 `DROP DATABASE system_mcp`。此前 spec 阶段只用 `demo_ro` 做过只读查询

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

### 2026-09-26 T1.8 本地 E2E（demo_ro → Doris 公网 IP，P1 收尾）
- `scripts/mcp_smoke.py` 新增 `flow` 子命令（`--prefix --table --wait`）+ docstring 示例，`flow --help` 确认三个参数都在。
- 端口 8000（`demo_ro`）：`list --expect 12` → `tools: 12`（12 个工具名与 R-20 一致，除 `reload_semantic_layer` 外全部 `[readOnly]`）；`check_service_health` → `"success": true` / `"doris": "connected"`（无 `doris_error`）；`list_databases` 含 `"ecom"` 计数 1。
- `flow` 结果 **6/6 passed**，`exit=0`：`query_id=75d16842cba948b0-bf99811a6c1004e1`，`trace_comment_kept=True`；`get_query_profile` → `source=v2 total_chars=103476 returned_chars=9129`（<20000）；非法 id → `INVALID_PARAMS`；未知 id → `profile_found=false`；`DELETE …` → 被 MCP SQL 校验器拒绝，`code=INVALID_SQL`。
- 端口 8001（`DORIS_PASSWORD=wrong-on-purpose`，每个工具只调用一次）：`list_recent_queries` → `success=false, code=UNAUTHENTICATED`（FE HTTP body `code:401`）；`check_service_health` → `success=true, doris="unavailable", doris_error="credentials rejected by Doris"`；`list_databases` → `success=false, code=CONNECTION_ERROR`，消息含 MySQL `1045 Access denied for user 'demo_ro@...'`（只有用户名，无密码）；两个进程调用期间均未退出、`/ping` 一直健康。
- 日志密码检查：`/tmp/p1-e2e.log`、`/tmp/p1-e2e-bad.log`、两个 workspace 的 `audit.log`/`server.log` 共 6 个文件，真实密码命中数全部为 `0`。审计日志：`wc -l /tmp/p1-e2e-ws/logs/audit.log` = 24 行、`grep -c doris_new_mcp.audit /tmp/p1-e2e.log` = 8 行；核对时间戳发现 24 行里有 16 行是同一 workspace 路径下更早（spec 阶段实测，见上面「P1 代码起草 + 实测」日志）留下未清理的历史记录，本次会话自己产生的 8 行与 stderr 里的 8 行 `doris_new_mcp.audit` 完全一一对应（同一 pid、同一时间窗），审计双写机制验证通过。
- 按端口停止两个实例（8000/8001），确认 `stopped`；清理 `/tmp/p1-e2e-ws`、`/tmp/p1-e2e-ws-bad`、`/tmp/p1-boot-ws`；日志文件保留在 `/tmp` 供查阅（不进仓库）。
- P1 至此全部完成（T1.1–T1.8）。

### 2026-09-26 P1 整体评审
- opus 整体评审 `aaebf3a..65e55f9`：Ready to merge = Yes；0 Critical / 0 Important / 9 Minor；77 个离线测试复跑通过；plan 中所有整文件代码块与提交逐字节一致；`git log -- mcp-server` 共 7 个 commit。
- 建议 P3 之前补一个小的后续提交（代码不在已 review 的计划里，需用户确认）：① `get_query_profile` 返回的 profile 文本里 `Sql Statement:` 行没有经过 `mask_sensitive`（`list_recent_queries` 有）；② `settings.py` 读 secret 失败时 `from e` 改为 `from None`；③ `main()` 没有捕获 `build_server` 的异常（现在是退出码 1 + traceback，而不是退出码 2）；④ 缺少非默认 `DORIS_PORT`/`DORIS_HTTP_PORT` 传到 `cfg.cluster` 和 FE URL 的测试。
- P3 时核对：CodeZip staging 的依赖 freeze 与 `.venv` 一致（`pyproject.toml` 只锁直接依赖）；20 个并发工具调用对 `pool_max_size=5` 和 Quick 60 s 上限的影响（FE HTTP 15 s 是分阶段超时，v2 + api_text 串行最坏 30 s 以上）；upstream 工具在连接池失败时不写审计（例如密码错误时的 `list_databases`），R-32 是否可以接受。
- 更正 T1.5 日志：`test_agentcore_profile.py` 350 行、`profile.py` 377 行（git 计数）；T1.5 的红灯证据（`ModuleNotFoundError: No module named 'tools.profile'`）是在 review 修复轮里对 `be0ece6` 导出补做的。
- 过程记录：T1.2、T1.5 的 commit 在推送前 amend 过（修正 Co-Authored-By trailer、补文件末尾换行），最终 SHA 以 `git log` 为准。

### 2026-09-26 P1 合并
- 用户选择「本地合并到 main」：`git merge --ff-only p1-mcp-server`（`aaebf3a..7a4b5a3`），合并后复跑 77 个 agentcore 测试 + upstream 离线测试均通过，删除分支 `p1-mcp-server`。未 push（没有配置远端）。

### 2026-09-26 T0.1 工具准备
- P0 按用户指示 native 执行（superpowers:executing-plans），在分支 `p0-spike` 上进行。
- `npm i -g @aws/agentcore@0.30.0` → `agentcore --version` = `0.30.0`；Node `v22.23.2`、uv `0.11.24`、aws-cli `2.36.36`；调用者 `arn:aws:iam::890717383483:user/jingamz`。
- `.venv` 已由 P1 T1.1 建好，**没有重建**（`uv venv .venv` 会覆盖 P1 的依赖），只执行 `uv pip install -r spike/p0-mcp/pyproject.toml`：68 个包均已满足，`fastmcp` = `3.4.4`。
- lib.sh 自检（临时 state 文件）：`DRY-RUN: echo would-mutate`、`DRY-RUN: state_set SELFTEST=dry`、upsert 后 `grep -c` = 1、`runtime_url` 输出与计划一致；`infra/*.sh`、`scripts/*.sh` 语法检查无 `SYNTAX:` 行。

### 2026-09-26 T0.3 spike MCP 本地测试
- T0.2 的 dry-run 已跑（`grep -c '^DRY-RUN: aws'` = 14，与计划一致），等待用户确认期间先做不依赖 AWS 的 T0.3。
- 单测：`(cd spike/p0-mcp && ../../.venv/bin/python -m unittest -v)` → `Ran 8 tests` / `OK`。
- 本机对 Doris 公网 IP 实测（`MCP_PORT=8765`，进程环境里只有 `DORIS_HOST`）：`/ping` → `{"status":"Healthy"}`；`list --expect 1` → `net_check  [readOnly]`、`tools: 1`（connected+initialized 35 ms）；`call net_check` → `mysql.ok=true`、`banner="5.7.99"`（350 ms）、`http.ok=true`、`status=200`（385 ms），total 432 ms。停止后确认 8765 端口已释放。
- 计划修正：计划里写的字段名 `server_version` 与 spike 代码、单测（`banner`，值就是 server version）不一致，以代码为准，把 `plans/P0-spike.md` 的 3 处改成 `banner`；spike 代码没有改动。

### 2026-09-26 T0.2 网络（SG + VPC endpoints）[GATE]
- 09:52 UTC dry-run：`grep -c '^DRY-RUN: aws'` = 14，与计划一致；以表格形式展示给用户。另外做了只读核实：目标 VPC 内只有 Doris EC2（`172.31.25.143`），没有已有 endpoint；本机在 ap-northeast-2 的另一个 VPC，不受 private DNS 影响。
- **用户确认 → 09:56 UTC `APPLY=1 bash infra/10-network.sh`**（用户同时要求：全程使用 Opus 5.5，所有 subagent 都显式指定 opus）。
- 新建：`RT_SG=sg-02e54e3ee60161793`（`doris-mcp-rt`）、`VPCE_SG=sg-0c405296a225090b5`（`doris-mcp-vpce`）、`VPCE_S3=vpce-000848162a3d0a1ab`、`VPCE_LOGS=vpce-0469d4fa5a0fb88ad`、`VPCE_SECRETSMANAGER=vpce-099dda5979ed39b9e`；3 个 endpoint 在 1 分钟内变为 `available`。
- 自检：3 个 SG 都是 `no open inbound rule`；`doris-mcp-rt` 出站正好 4 条（9030/8030 → `sg-0a02e336df4299888`，443 → `pl-63a5400a`，443 → `VPCE_SG`）。
- 验证：state.env 新增 5 行；重跑 dry-run 的 `DRY-RUN: aws` 行数 = 0（R-61）；`doris-demo-sg` 入站 = 原有 `13.125.9.110/32` 的 22/8030/9030 + 新增 `8030/9030 ← RT_SG`，没有其他规则；endpoints：S3 `available`/`False`（Gateway 类型没有 private DNS），logs、secretsmanager `available`/`True`。

### 2026-09-26 T0.4 部署 spike Runtime（VPC 模式）[GATE]
- Step 1：`agentcore create --project-name dorismcp --no-agent --skip-git --output-dir .` 一次成功（没有交互提问）。与计划相比多生成了 `dorismcp/AGENTS.md`、`dorismcp/README.md`、`agentcore/.llm-context/`、`agentcore/.env.local`（空文件，已被忽略）；`.gitignore` 与预期一致。`cdk/node_modules` 在 create 时就装好了（约 307 MB，已被忽略）。
- Step 2：`render-agentcore.py --phase spike` 写入的 runtime 条目与计划一致（CodeZip / PYTHON_3_12 / MCP / AWS_IAM / VPC、3 个子网 + `RT_SG`、只有 3 个 envVars）。
- Step 3：在 `dorismcp/` 目录下执行即可（不需要进 `dorismcp/agentcore`）：`agentcore validate` → `Valid`；`deploy --dry-run -v` → 栈 `AgentCore-dorismcp-default`，CodeZip 资产 17 MB（3 599 个文件）。合成模板里共 4 个资源：执行角色、默认策略、`AWS::BedrockAgentCore::Runtime`、CDKMetadata。
- GATE 时向用户说明：CDK 默认执行角色带有通配权限（`bedrock:InvokeModel`/`CountTokens` → 全部 foundation model 和本账号的 inference profile；`logs:DescribeLogGroups`、`xray:Put*` → `*`；configuration-bundle 读写），与 R-41「按具体 ARN 授权」不符。P0 先接受，**P3 检查项**：收紧执行角色（去掉 InvokeModel），与 T3.1 一起处理。
- **用户确认 → 10:07 UTC `agentcore deploy -y -v`**，10:13 完成（5 分 41 秒，exit 0）。`status --json` → `deployed` / `READY`。`25-runtime-state.sh`：`status=READY version=1`，写入 `RUNTIME_ARN/ID/ROLE_ARN/URL` 共 4 行（`RUNTIME_ID=dorismcp_dorismcp-ILgkSAFotU`）。
- **计划外的账号级改动（事后发现，已报告用户）**：部署结束时 CLI 输出 `Transaction search enabled`。读 CLI 0.30.0 源码（`setupTransactionSearch`）确认：只要项目里有 Python runtime，每次 deploy 后 CLI 都会 ① 如果 X-Ray trace 目的地不是 CloudWatchLogs 就改过去（本账号已经是 `CloudWatchLogs`/`ACTIVE`，logs 资源策略 `TransactionSearchXRayAccess` 是 2026-04 建的，说明之前就开启了）；② 把 X-Ray indexing rule `Default` 设为 `transactionSearchIndexPercentage`（默认 100）。CloudTrail：`2026-09-26T10:13:24Z UpdateIndexingRule Default → desiredSamplingPercentage 100.0`，调用者 `jingamz`；90 天内没有更早的 UpdateIndexingRule 事件，原值无法从 CloudTrail 得知。可以用 `~/.agentcore/config.json` 的 `{"disableTransactionSearch": true}` 关掉这一步。spike 的 `enableOtel=false`，本身不产生 span；100% 影响的是账号里其他产生 span 的工作负载的索引费用。
- Step 7 SigV4 冒烟（`mcp-proxy-for-aws` v1.7.0，uvx 缓存已预热）：`target=172.31.25.143`，`mysql.ok=true`（`banner=5.7.99`，60 ms），`http.ok=true`（`status=200`，66 ms）；`list --expect 1` → `net_check  [readOnly]`、`tools: 1`。耗时：第 1 次 connected+initialized 5434 ms / total 8146 ms；第 2 次 5694 / 8414 ms；list 6366 / 7681 ms。
- **冷 / 热的实测拆分**（T0.8 要用）：CloudWatch 显示每个 `mcp_smoke.py` 进程都对应一个新的 log stream（新 microVM 会话），因为 proxy 每个进程都开一个新会话，所以计划里「第 2 次 = 热」不成立。加 `--header X-Amzn-Bedrock-AgentCore-Runtime-Session-Id=…` 也没有复用会话。用 `/tmp` 下的临时 botocore SigV4 探针直接发请求：新会话 `initialize` 4378 ms（冷启动，从 ap-northeast-2 的本机发起）；Runtime 会返回 `Mcp-Session-Id`（server 本身是 stateless）；带回同一个 `Mcp-Session-Id` 后 `tools/call` × 3 = 371 / 315 / 294 ms（热）。proxy 自身开销（对本地 spike，`--skip-auth`）约 0.9 s；经 proxy 的一次调用约 6 个 `POST /mcp`，每个约 0.65 s（跨区域 RTT + 签名）。结论：热不热取决于客户端是否复用 `Mcp-Session-Id`；Gateway 是否复用要在 T0.6 观察。
- Step 8：日志组 `/aws/bedrock-agentcore/runtimes/dorismcp_dorismcp-ILgkSAFotU-DEFAULT`（与计划一致），能看到 `Uvicorn running on http://0.0.0.0:8000`、`POST /mcp` 200/202，以及平台每 2 s 一次的 `GET /ping`。账号里还有其他项目的日志组（`doris-mcp-server`、`doris_mcp_server-7w0KpkGDhR-DEFAULT`、`harness_pragent_*`），均未触碰。
- CodeZip staging 实际在 `dorismcp/agentcore/.cache/dorismcp/staging`（63 MB，被生成的 `.cache/*` 忽略），不在 codeLocation 下；根 `.gitignore` 里的 `spike/p0-mcp/agentcore/` 一行目前用不到，保留无害。
- Step 9：提交 `dorismcp/` 下 21 个文件（约 308 KB；`node_modules`、`cdk.out`、`.cache`、`.cli/logs`、`.env.local` 都被忽略，`.cli/deployed-state.json` 保留）。

### 2026-09-26 T0.5 Cognito [GATE]
- 10:20 UTC dry-run：6 条 `DRY-RUN: aws`（create-user-pool、create-user-pool-domain、create-resource-server、create-user-pool-client `quick-user` / `quick-service`、admin-create-user `demo`）+ 2 行日志（创建 demo 用户密码 secret、设置永久密码）。GATE 前核实脚本的 secret 处理：密码由 `get-random-password` 生成，经 0600 临时文件以 `file://` 传给 AWS CLI，不进 argv、不进输出。
- **X-Ray 决定（用户，10:22 UTC）**：indexing rule `Default` 保持 100%（原值未知，不再改账号设置）；在本机 `~/.agentcore/config.json` 加 `"disableTransactionSearch": true`，以后（P3 重新部署）`agentcore deploy` 不再执行 transaction search 步骤。该文件是本机全局配置，不在仓库里。
- **用户确认 → 10:23 UTC `APPLY=1 bash infra/20-cognito.sh`**，exit 0，约 20 s。state.env 新增 6 行：`COGNITO_POOL_ID=us-east-1_btuTL63V3`、`COGNITO_DOMAIN=doris-mcp-890717383483.auth.us-east-1.amazoncognito.com`、`DISCOVERY_URL`、`QUICK_CALLBACK`（默认值，T0.7 以 Quick UI 为准）、`CLIENT_A_ID=2q9be1ub7s5nh8ph4sl87uemr2`、`CLIENT_B_ID=4bf7hnvsugn9trphjtmsfldb4s`。
- 验证：discovery `issuer` = `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_btuTL63V3`，token / authorize endpoint 在 `https://$COGNITO_DOMAIN/oauth2/…` 下，域名立即生效（没有等待）；`get-gw-token.sh --claims` → `client_id=$CLIENT_B_ID`、`scope=doris-mcp/invoke`、`token_use=access`，`iss` 与 issuer 一致。
- 只读核对（不输出 ClientSecret）：pool `AllowAdminCreateUserOnly=true`、密码最少 16 位；client A = `code` 流程、scopes `openid doris-mcp/invoke`、回调为默认 URL、token revocation 开启；client B = `client_credentials`、scope `doris-mcp/invoke`；用户 `demo` = `CONFIRMED`/enabled；secret `doris-mcp/cognito-demo-user` 创建于 10:23:17。
- 幂等：重跑 dry-run 只有 1 行 `update-user-pool-client … --client-name quick-user …`，没有 `create-*`。

### 2026-09-26 T0.6 Gateway [GATE]
- 10:25 UTC dry-run：4 条 `DRY-RUN: aws`（create-role、put-role-policy、create-gateway、create-gateway-target），与计划一致。信任策略限定 `aws:SourceAccount=890717383483` + `aws:SourceArn gateway/*`；权限策略只有 `InvokeAgentRuntime` → `dorismcp_dorismcp-ILgkSAFotU`（及其 `runtime-endpoint/*`）；authorizer `allowedClients=[A,B]`、`allowedScopes=["doris-mcp/invoke"]`；target 出站 `GATEWAY_IAM_ROLE`（service `bedrock-agentcore`）。只读核实：账号里原有的 Gateway 只有 `pragent-github-gw`（未触碰），`doris-mcp-gateway-role` 之前不存在。
- **用户确认 → 10:33 UTC `APPLY=1 bash infra/30-gateway.sh`**，exit 0，38 s（含 15 s IAM 传播等待）；`get-gateway → READY`、`get-gateway-target → READY`。state.env 新增 4 行：`GW_ROLE_ARN`、`GW_ID=doris-mcp-gw-ryxzl0vgyv`、`GW_URL=https://doris-mcp-gw-ryxzl0vgyv.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp`、`GW_TARGET_ID=ENINDEEGGB`。创建 target 时 Gateway 调了 Runtime 两次（10:33:56、10:34:01 各一个新 log stream，用于同步工具目录）。
- 不带 token（T0.7 排障用）：`HTTP/2 401`，`www-authenticate: Bearer error="invalid_token", scope="doris-mcp/invoke", resource_metadata="https://doris-mcp-gw-ryxzl0vgyv.gateway.bedrock-agentcore.us-east-1.amazonaws.com/.well-known/oauth-protected-resource"`。PRM 在**根路径** `/.well-known/oauth-protected-resource`（不是 `…/oauth-protected-resource/mcp`），原文：`{"authorization_servers": ["https://cognito-idp.us-east-1.amazonaws.com/us-east-1_btuTL63V3"], "resource": "https://doris-mcp-gw-ryxzl0vgyv.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp", "scopes_supported": ["doris-mcp/invoke"]}`。
- 带 client B token（只放在环境变量里，未打印）：`list --expect 1` → `doris___net_check  [readOnly]`、`tools: 1`（没有 Gateway 内置工具，T3.4 / T4.1 的期望数量不用调整），connected+initialized 697 ms / total 1619 ms，Runtime 没有新 log stream（`tools/list` 由 Gateway 用已同步的目录回答）。`call doris___net_check` × 2：结果与 T0.4 相同（`mysql.ok=true banner=5.7.99`、`http.ok=true status=200`），connected+initialized 614 / 642 ms，total 7028 / 7022 ms。无效 token → `401 Unauthorized`，exit 1。
- **会话复用（T0.8 要用）**：Gateway 对客户端**不返回** `Mcp-Session-Id`（Gateway 侧是 stateless）。用 `/tmp` 下的临时 bearer 探针在同一个客户端会话里连续发 3 次 `tools/call`：5522 / 4506 / 4549 ms，Runtime 出现 3 个新 log stream；`mcp_smoke.py` 的 2 次 call 也各对应 1 个新 stream。结论：**Gateway 每次 `tools/call` 都会新开一个 Runtime 会话（新 microVM，冷启动）**，即使在同一个客户端会话里也一样；所以经过 Gateway 时，每次工具调用约 4.5–5.5 s（spike，Gateway 与 Runtime 同在 us-east-1），在 Runtime 前做预热没有效果。P3 要用完整的 P1 server（依赖更多、import 更重）重新测冷启动，并与 Quick 60 s 上限一起评估。
- 幂等：重跑 dry-run 只有 `put-role-policy` 和 `update-gateway`，没有 `create-*`。

### 2026-09-26 T0.7 Quick 桌面版接入 [USER]
- Claude 准备材料：`python3 scripts/render-local-connector.py` → `quick/local-connector.json`（profile `doris-demo`）；非敏感参数和操作步骤写入 `quick/T0.7-guide.md`（用户所在窗口无法复制，按用户要求生成），`check-secrets` OK。
- 用户取 secret 时遇到「没有输出」：Claude 核对了本机凭证来源——Claude Code 用的是环境变量凭证（`890717383483` / `jingamz`）；本机 `default` profile 是同一个账号（默认 region us-west-2，命令里都带了 `--region us-east-1`），`lijingfz` 是另一个账号 `057548996873`。给了用户带 `--output text --no-cli-pager` 的单行命令，之后用户顺利完成。
- **用户回报**：Callback URL 一栏未填；**Part A User auth 成功**（用户报「登录后首次调用耗时约 66 ms」，这个数字与 net_check 返回的 `mysql.ms` / `http.ms` 同一量级，应是工具结果里的内部耗时，不是端到端耗时）；**Part B Service auth 成功**；**Part C Local stdio 没有尝试**；其他观察：无。
- 回调 URL 的推断：client A 只注册了一个回调 `https://us-east-1.quicksight.aws.amazon.com/sn/oauthcallback`，Cognito 对不在 CallbackURLs 里的 `redirect_uri` 会直接报 `redirect_mismatch`，Part A 登录授权成功说明 Quick 用的就是这个默认值，`QUICK_CALLBACK` 不需要修改。
- Runtime 日志核对（只读）：Quick 的两次调用对应 15:18:18、15:24:15 两个新 log stream。每个 stream 都是新 microVM 冷启动（`Starting MCP server` → uvicorn 启动 → `POST /mcp` 200 initialize、202 initialized、200 tools/call）。server 从进程启动到 tools/call 返回不到 1 s，冷启动的大部分时间花在 microVM 分配上（在 server 日志之前）。与 T0.6 结论一致：经过 Gateway 时每次 `tools/call` 都是一次新会话。
- Part C 顺延：R-11 的验收在 P4（T4.2 切换 Local stdio 连接器、T4.4 两条路径各跑一次）。`mcp-proxy-for-aws` → Runtime 的 SigV4 链路已在 T0.4 从开发机验证；没验证的只是 Quick 桌面版这一侧（Local 连接器导入、Quick 所在电脑上的 `uv` 和 AWS profile）。P0 退出标准第 3 条中 Cloud Connector 部分已满足，Local stdio 部分记为未验证。

### 2026-09-26 T0.8 P0 结论
- design.md 升到 v0.3（变更记录一行，列 5 点）：§4.4 回调 URL ❓→✅（默认值）、User auth / Service auth 已跑通、Local stdio 顺延 T4.2；§4.5 写入 401 头、PRM（根路径）原文、Quick 按 PRM 请求到 scope、工具列表只有 target 工具、`tools/list` 由 Gateway 目录回答、Gateway 不返回 `Mcp-Session-Id` 且每次 `tools/call` 新开 Runtime 会话；§7 新增「agentcore CLI 0.30.0 实测」块（命令、生成文件、执行目录、栈名 / runtime 名、staging 路径、日志组、CDK 角色通配、transaction search 及关闭方式）；§11 P5 标准去掉「预热方案生效」；§13 用实测数字重写 60 s 一行，关闭 scope 一行，新增「deploy 修改 X-Ray」一行；§14 标注 Runtime 执行角色和 `--exception-level DEBUG` 待 P3 复查；取 secret 的命令改成单行并带 `--region` / `--output text` / `--no-cli-pager`（T0.7 经验）。
- **冷启动结论**：冷启动 + 首次调用约 4.5–5.5 s（经 Gateway）≪ 40 s，不需要预热方案；经 Gateway 每次调用都是新会话，预热本来也无效，原计划里的「演示前预热 `check_service_health`」「调大 idle timeout」取消。P3 T3.3 用完整 server 重测。
- **与 v0.19 的差异**：旧仓库不在本机，无法逐项对比；design §7 只记录 0.30.0 的实测事实，并注明 starter toolkit 的 `configure` / `launch` 已由 `agentcore create` / `deploy` 取代。
- tasks.md：T0.8 勾选；T4.2、T5.5 措辞按上面的路径决策调整；T3.x 不变。
- P0 退出标准：① Runtime → Doris 9030/8030 ✅（T0.4）；② 经 Gateway 列出并调用 `doris___net_check` ✅（T0.6）；③ Cloud Connector 两条路径 ✅，Local stdio 在 Quick 里未验证（顺延 T4.2）；④ 冷启动 / 热调用耗时、回调 URL、scope 行为都已记录 ✅（本条）。

### 2026-09-26 P0 整体评审（opus）
- 范围 `7a4b5a3..00315a9`（8 个提交）。结论：With fixes，0 Critical / 3 Important / 9 Minor。评审者用只读 describe 核对了现网：`doris-mcp-rt` 正好 4 条出站、没有入站，`doris-mcp-vpce` 只有 443 ← RT_SG，没有任何 `0.0.0.0/0` / `::/0` 入站；Gateway authorizer、Runtime 网络配置与 design 一致；`check-secrets` 与额外的 token 扫描都没有命中。
- **I-2 已修**：P0 的三条发现原先只写在 design 里，现在写进 tasks.md：T3.1 收紧 CDK 默认角色的通配权限（经 `agentcore.json`，不在 CDK 之外改）、T3.2 deploy 前确认 `disableTransactionSearch`、T3.4 经 Gateway 逐次记录耗时（含 `query_metric`）；「当前状态」里「T3.x 不用改」一并更正。
- **I-3 已修**：`infra/lib.sh` 读取 state.env 时会覆盖调用方的环境变量，T0.5 之后 state.env 里有了 `QUICK_CALLBACK`，所以文档里的 `QUICK_CALLBACK=… bash infra/20-cognito.sh` 会被静默忽略（main 上已有的问题，P0 没触发）。改为：脚本在 source 之前用 `STATE_CALLER_WINS` 列出允许调用方覆盖的变量，只有这些变量以调用方为准，其余仍以 state.env 为准（例如调用方的 `AWS_REGION` 不会生效）。新增离线测试 `infra/test/test-lib.sh`（5 项，修复前 2 项失败，修复后全部通过）；dry-run 验证：带 `QUICK_CALLBACK='https://example.invalid/cb'` 时 `update-user-pool-client --callback-urls` 显示覆盖值，不带时是默认值。
- **I-1 待用户决定**：P0 退出标准第 3 条的 Local stdio 部分没有在 Quick 里验证，顺延到 T4.2 是 Claude 自己的判断，需要用户确认，或者在合并前补做 Part C。
- Minor（记录，暂不修）：M-1 scope 结论表述过强（Cognito 在请求不带 scope 时会授予 client 的全部 scope，登录成功不能证明 Quick 按 PRM 请求了 scope）；M-2 `quick/T0.7-guide.md` 里取 secret 的命令还是旧的多行写法；M-3 Quick 侧端到端耗时没有测过；M-4 会话 / 冷启动探针只在 `/tmp`，P3 无法复现；M-5 `mcp-proxy-for-aws@latest` 未固定版本（只验证过 1.7.0）；M-6 「预热无效」只对 Gateway 路径成立，Local stdio 路径会复用会话，预热和 idle timeout 可能有用；M-7 `render-local-connector.py` 里把 `RUNTIME_URL` 的来源写成了 `30-gateway.sh`（应为 `25-runtime-state.sh`）；M-8 根 `.gitignore` 注释里的 staging 路径不对；M-9 `6a7bca0` 的提交标题写了 local stdio。评审建议 P3 考虑调低 `idleRuntimeSessionTimeout`（经 Gateway 每次调用都会留下一个最长 15 min 的 microVM 及其连接池），并核对 `mcp_svc` 的连接数上限。

### 2026-09-26 D9：不做 Local stdio（用户决定）
- 评审 I-1 指出：P0 退出标准第 3 条的 Local stdio 部分没有验证，顺延是 Claude 自己的判断。询问用户后，用户回复「既然 A 和 B 已经跑通，其实 C 就不用做了」，并确认范围是**整个项目都不做**。
- 同步修改：requirements v1.2（R-11 取消、R-13 成为备份路径并加 P4 验收、新增 D9）；design v0.3.1（§1、§2、§3 图、§4.4、§8.2 标为已取消但保留作参考、§8.3、§11 P0 / P4、§13 `mcp-proxy-for-aws` 一行关闭）；tasks（T0.7 备注、删除 T4.2、T4.4 改为 User auth / Service auth 各一次，需求列 R-11 → R-13）。
- P0 退出标准第 3 条按 D9 视为满足（User auth、Service auth 两条路径都已调用成功）。评审 M-6（Local stdio 路径的预热）随之不再适用。`quick/local-connector.json`、`scripts/render-local-connector.py` 保留作参考。
- 用户选择：分支 `p0-spike` 本地合并到 `main`，不 push。

### 2026-09-26 P2 计划编写
- `plans/P2-doris.md` 写好：任务按执行顺序排列 T2.1 → T2.4 → T2.5 → T2.2 → T2.3 → T2.6（root 发布时会创建 `system_mcp` 和 `ecom` 元数据行，所以 `mcp_svc` 不需要 LOAD_PRIV；T2.3 要检查已发布的 `ecom`）。全部代码按 TDD 在 `.superpowers/sdd/P2-doris/draft/`（git 忽略）起草，**权威版本是计划里嵌入的代码**：117 个 Python 测试 + 4 组 shell 测试（23 / 10 / 12 / 14 项）。
- 调研结论（写进 design v0.4 §4.2、§6.1、§6.3）：upstream Web UI 写接口要求 Doris 角色 `admin`，`commit_staging` 会 `GRANT … TO '%'`，`validate` 不初始化 MetricFlow 引擎 → 发布改为**方案 C**（root 在进程内调用 `DorisStore`，离线校验含引擎初始化 + 重名检查，发布前 DESCRIBE 物理表，回读逐字节比对，不执行 GRANT）；`ensure_fresh` 按 semantic_version 自动重载，不需要 `reload_semantic_layer`。
- 模型：10 个 YAML、22 个指标、9 张物理表，time spine `dim_date`。`demo_ro` 对真实 Doris **只读**跑 `reconcile.py direct`：11/11 个故事线用例到分一致（YTD GMV 65,442,236.24 / 订单 42,770 / 买家 20,187 / AOV 1530.10；故事 5.1 退款率 07 月 17.39%、08 月 22.08%）。
- 安全：`scripts/check-secrets.sh` 新增块 1b，对 Secrets Manager 里的密码做精确值扫描（固定读 us-east-1，因为本机 `AWS_DEFAULT_REGION` 是 us-west-2）；所有脚本的输出、异常信息都把 Doris 主机和密码 mask 成 `***`；root 密码只在 `APPLY=1` 时以新变量名传给 python；`mcp_svc` 密码经管道进入 python。
- spec 阶段**没有执行**任何 GATE 写操作（secret、发布、建账号、写探针）；`demo_ro` 只做了 SELECT / SHOW / DESCRIBE。自动模式拒绝过一次用 `demo_ro` 试探写操作的命令，计划里写明不要重试。
- 计划自查：从 HEAD 的干净副本（`/tmp/p2sim`）按计划顺序从计划文件里提取代码并逐步回放，每一步的红 / 绿输出、测试数、dry-run 输出都与「期望」一致，回放出来的文件树与草稿逐字节相同；修正了 4 处「期望」（两处 shell 红阶段改用 grep 显示 FAIL 行、T2.4 红阶段是 `failures=12` 而不是 errors，文件地图中 2 处测试数）。计划文件经 check-secrets 扫描通过，Doris 主机地址和密码命中 0 次。
- spec 修订（未提交，随计划一起给用户 review）：tasks.md P2 段（目标、执行顺序、计划列，T2.3 标签改为 [AI+GATE]，T2.5 改为方案 C）；design v0.4（§4.2、§5.1、§6.1、§6.3、§11 P2 行、§14）；requirements v1.3（R-26、R-42 验收）。

### 2026-09-26 P2 计划通过 review，执行方式与评审小修（用户决定）
- 用户回复「P1 可以合并，P0 按照你的意见进行修改。P2 采用你推荐的 subagent-driven 的方式推进」。理解为：P1 整体评审的 4 项小修①–④并入 P2 分支，作为最后一个任务 T2.7，P0 评审的 M-2（`quick/T0.7-guide.md` 取 secret 改成单行命令）、M-8（`.gitignore` staging 注释）一并放进 T2.7；M-1、M-3、M-4 按建议写进 T4.1、T4.4、T3.4；M-5、M-6（已随 D9 不适用）、M-7、M-9 不做。
- 计划新增 T2.7（9 步，纯离线）：`get_query_profile` 输出的 profile 文本按 SQL 预览同样 mask；`build_server` 失败时只写一行 mask 过的日志并 `exit 2`；读 secret 失败不再链出原始异常；新增非默认端口一路传到集群配置和 FE URL 的测试。新增 5 个测试，agentcore 测试共 82 个。所有代码块在临时副本里走完 RED → GREEN 和变异检查，与计划逐块一致。
- tasks.md：新增 T2.7 行；T3.4、T4.1、T4.4 分别补上 M-4、M-1、M-3。
- 执行方式：Subagent-driven（superpowers:subagent-driven-development），每个任务一个 implementer + 一个 task reviewer，最后做整体评审，全部指定 Opus 5.5。GATE 步骤由 implementer 停下来报告 dry-run，经用户逐次确认后才 `APPLY=1`。

### 2026-09-27 T2.1 Secrets Manager `doris-mcp/mcp_svc` + check-secrets 块 1b [GATE]
- Step 1：前置条件与计划一致（`main` 上恰好 5 行改动；账号 `890717383483`；Python 3.12.3；credentials.env 可读；check-secrets OK 665 个文件）。新建分支 `p2-doris`，提交计划和 spec 修订（`f2d6a60`）。
- TDD：`infra/test/test-40-doris-secret.sh` 先红（脚本不存在，exit 127，`13 failed`），写 `infra/40-doris-secret.sh` 后 23/23 通过；`infra/test/test-lib.sh` 仍全部通过。`scripts/test/test-check-secrets.sh` 先红（与计划列出的 6 项 FAIL 一致，`6 failed`），在 `scripts/check-secrets.sh` 插入块 1b（+16 行）后 10/10 通过。4 个文件与计划逐字一致。
- 块 1b 首次扫描真实仓库：只有 `WARN: cannot read secret doris-mcp/mcp_svc`（当时还没建；`doris-mcp/cognito-demo-user` 能读到），`check-secrets: OK (668 files scanned)`。
- dry-run：`describe-secret` 返回 ResourceNotFound，输出与计划一致（`get-random-password` 与 `create-secret --secret-string file://<0600 temp file…>` 两条 DRY-RUN），`state.env` 无变化。
- **用户确认 → 00:45 UTC `APPLY=1 bash infra/40-doris-secret.sh`**（由主会话执行）：`secret doris-mcp/mcp_svc created`，state.env 新增 `DORIS_SECRET_ARN`（后缀 `RIUdT2`），`done (APPLY=1)`。
- Step 12 只读验证：secret 内容只打印了用户名 / 长度 / 是否全是字母数字 → `mcp_svc 32 True`；state.env 有 `DORIS_SECRET_ARN=arn:aws:secretsmanager:us-east-1:890717383483:secret:doris-mcp/mcp_svc-RIUdT2`；重跑 dry-run → `secret exists: doris-mcp/mcp_svc (left unchanged)`、`done (APPLY=0)`（不会再生成密码）；check-secrets 不再有 WARN，两个 Secrets Manager 密码都参与精确值扫描，`check-secrets: OK (668 files scanned)`。
- 密码没有出现在命令行参数、日志或对话输出里（只经过一个 0600 临时文件，用完即删）。回滚（需 GATE）：`aws secretsmanager delete-secret --region us-east-1 --secret-id doris-mcp/mcp_svc --recovery-window-in-days 7`。

### 2026-09-27 T2.4 `ecom` 语义模型 + 对账脚本（`demo_ro` 只读）
- TDD：新建 `doris/test/test_semantic_models.py`，先红（`Ran 12 tests`、`FAILED (failures=12)`，`bootstrap_from_yaml failed: models/ directory not found`），写 `doris/semantic/ecom/` 的 10 个 YAML 后 12/12 通过。新建 `doris/test/test_reconcile.py`，先红（`Ran 13 tests`、`FAILED (errors=1)`，`No module named 'reconcile'`），写 `doris/reconcile.py` 后 `doris/test` 共 41 个测试全部通过，输出无警告。所有文件与计划逐字一致。
- 模型：workspace `ecom` 10 个文件、22 个指标、9 张物理表（不含 `dim_user` / `dim_user_address`），time spine `dim_date`；MetricFlow 引擎模式初始化成功，无重名、无阻塞问题。
- Step 9：`demo_ro` 对真实 Doris 只读跑 `reconcile.py direct`（本机编译 YAML，只执行 SELECT，不访问 `system_mcp`）：11 个用例全部 `ok`（ytd_totals 1 行、monthly_2026 9、yoy_2026 9、channel_ytd 4、area_ytd 7、mini_program_quarterly 7、cat1_items_ytd 12、brand_tier_ytd 3、refund_rate_5_1 2、reviews_by_shop_type_ytd 4、refunds_by_reason_ytd 10），`11/11 cases match`，`exit=0`，与计划期望一致；输出里没有 Doris 主机地址和密码。
- Doris 无变更（只读）；没有创建或修改 AWS 资源。

### 2026-09-27 T2.4 评审修复
- 评审（Important）：`mcp` 模式下的意外异常（传输错误、响应缺 `data.rows` 的 KeyError、`client_factory` / `build_server` / `load_settings` 抛出的非 `SettingsError`）会以未 mask 的 traceback 输出。修复：`reconcile()` 把任意 `Exception` 记为该用例的 FAIL（mask 后输出，继续跑后面的用例，照常打印汇总行）；`main()` 对这类异常只输出一行 mask 过的 `FAILED: <类型>: <信息>` 并返回 1（用法 / 配置错误仍返回 2，`KeyboardInterrupt` 照常抛出）。先加 2 个测试（红：2 个 RuntimeError 带着假主机和假密码直接抛出），修复后 `doris/test` 共 43 个测试全部通过。

### 2026-09-27 T2.5 以 root 发布 `ecom` 语义层（方案 C，无 GRANT）[GATE]
- TDD：新建 `doris/test/test_publish_semantic.py`，先红（`Ran 44 tests`、`FAILED (errors=1)`，`No module named 'publish_semantic'`），写 `doris/publish_semantic.py` 后 `doris/test` 共 68 个测试全部通过（新增 25 个）。计划写的是 42 / 66，差的 2 个是 T2.4 评审修复新增的测试（43 + 1、43 + 25）。新建 `doris/test/test-publish-semantic.sh`，先红（wrapper 不存在，exit 127，`9 failed`），写 `doris/publish-semantic.sh` 后 12/12 通过。4 个文件与计划逐字节一致。
- Step 9 dry-run（不连 Doris）与计划期望逐行一致：`offline checks ok: 10 files, 22 metrics, 9 physical tables (bootstrap, MetricFlow engine, duplicate names)`、`DRY-RUN: would publish workspace=ecom as root:`、按文件名排序的 10 行 `file:`（字节数 453 / 705 / 4297 / 1512 / 2308 / 324 / 1528 / 782 / 1151 / 629）、5 步计划、`DRY-RUN: no GRANT is executed; APPLY=1 to publish`。
- **用户确认（「可以执行」）→ `APPLY=1 bash doris/publish-semantic.sh`**（由主会话执行一次），exit 0，输出与计划期望完全一致（经过滤器屏蔽主机和密码，实际没有命中）：`offline checks ok: 10 files, 22 metrics, 9 physical tables (bootstrap, MetricFlow engine, duplicate names)`；`physical check ok: 9 tables and their column exprs exist`；`remote: semantic_version=1, 0 files; staging: 0 rows`；`plan: add ['brands.yaml', 'categories.yaml', 'metrics.yaml', 'order_items.yaml', 'orders.yaml', 'project.yaml', 'refunds.yaml', 'regions.yaml', 'reviews.yaml', 'shops.yaml'], change [], remove []`；`published workspace=ecom semantic_version=2 (10 files: +10 ~0 -0)`。
- Doris 变更：root 新建库 `system_mcp` 和 3 张表 `workspace_metadata`、`active_store_ecom`、`staging_store_ecom`；upstream 初始化时插入 `ecom` 的元数据行（`semantic_version=1`），commit 后为 2，active 10 个文件，staging 清空。没有执行任何 GRANT（不调用 upstream `commit_staging`），`ecom` 库未改动。发布结果在 T2.3、T2.6 里以 `mcp_svc` 身份复核。
- 回滚（需 GATE）：root 执行 `DROP DATABASE system_mcp`（本阶段之前它不存在）。
- implementer 自查备注（未改代码）：`test_unparseable_models_are_rejected` 会输出一行 upstream `bootstrap.py:277` 的 ERROR 日志（`logging.disable(logging.WARNING)` 不屏蔽 ERROR），测试照常通过；upstream `_ensure_tables` 把建表失败只记在 WARNING 级别，被脚本屏蔽，出错时只能看到后续 mask 过的错误。
