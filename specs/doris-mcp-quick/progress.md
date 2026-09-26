# 进度

## 当前状态

<!-- 每个任务结束时覆盖这一块；下面的日志只追加不修改 -->

- **阶段**：P0 进行中（native / executing-plans，分支 `p0-spike`）；P1 已 ff-merge 到 `main`（`7a4b5a3`），分支 `p1-mcp-server` 已删除
- **进行中**：T0.6 Gateway [GATE]：dry-run → 等待用户确认
- **下一步**：T0.6 → T0.7 [USER] → T0.8。P2 需要先编写 `plans/P2-doris.md`；P3 之前建议先做 P1 整体评审的 4 项小修（见日志「P1 整体评审」，需用户确认）
- **阻塞**：无
- **已创建的 AWS 资源**：SG `doris-mcp-rt`、`doris-mcp-vpce`；`doris-demo-sg` 新增 9030/8030 ← `RT_SG`；VPC endpoints S3 / logs / secretsmanager；CloudFormation 栈 `AgentCore-dorismcp-default`（Runtime `dorismcp_dorismcp` + CDK 生成的执行角色）；Cognito user pool `doris-mcp-quick`（域名、resource server `doris-mcp`、client A `quick-user` / B `quick-service`、用户 `demo`）；Secrets Manager `doris-mcp/cognito-demo-user`；账号级 X-Ray indexing rule `Default` = 100%（T0.4 时 CLI 自动修改，用户决定保持现状）—— ID 见 `infra/state.env`
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
