# P3 AgentCore 部署 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务执行本计划。步骤用复选框（`- [ ]`）跟踪。
> **断线恢复：** 先按仓库根目录 `CLAUDE.md` 的恢复协议执行，再从 `progress.md`「当前状态」里写的任务/步骤继续。本计划里所有命令都在仓库根目录 `/home/ubuntu/AI-code/Doris-mcp-skill-Demo` 下运行，除非步骤里明确写了 `cd`。执行顺序就是编号顺序：**T3.0 → T3.1 → T3.2 → T3.3 → T3.4 → T3.5**（T3.0 是 P2 整体评审的遗留小修和补丁 P-09，必须在第一次 deploy 之前完成）。
> **代码来源：** 本计划中的全部代码和测试已在 spec 阶段于临时目录完成 TDD，并在 `178be68` 的干净 worktree 上按本文的顺序回放过：每个「确认失败」「确认通过」步骤的输出都是回放时实测的。spec 阶段还做了几项**只读**预验证（见 Architecture 最后一条）。4 个 GATE（建 IAM 角色、deploy、同步 Gateway target、迁移 `mcp_svc` 的 host）在 spec 阶段**都没有执行**，它们的「期望」是按代码、dry-run 和 CDK diff 推导的。执行时照抄即可；如果某一步的实际输出与「期望」不一致，先停下来查原因，不要改测试去迁就实现。

**Goal:** 把 AgentCore Runtime `dorismcp` 从 P0 的 spike 换成完整的 `mcp-server/`（12 个工具，以 `mcp_svc` 经 Secrets Manager 连 Doris 私网地址），执行角色换成只能写自己的日志、只能读 `doris-mcp/mcp_svc` 的专用角色；经 SigV4 直连和 Gateway 分别冒烟、测耗时和并发、核对审计日志；最后把 `mcp_svc` 的 host 收紧为 `'172.31.%'`。

**Architecture:**
- **执行角色（T3.1）**：agentcore CLI 默认用 CDK 生成执行角色，权限远超需要（任意 Bedrock 模型、X-Ray、7 个 configuration-bundle 操作、`runtimes/*` 日志组的读写，design §7）。`infra/35-runtime-role.sh` 建专用角色 `doris-mcp-runtime-role`：信任 `bedrock-agentcore.amazonaws.com`，限本账号、本区域；内联策略 `doris-mcp-runtime` 只允许写 `runtimes/dorismcp_dorismcp-*` 日志组、`logs:DescribeLogGroups`，以及对 `DORIS_SECRET_ARN` 这**一个** secret 的 `GetSecretValue`（secret 用 AWS 托管密钥，不需要 `kms:Decrypt`）。`scripts/render-agentcore.py --phase server` 把它写进 `agentcore.json` 的 `executionRoleArn`，CDK 导入这个角色后不再生成角色、也不附加任何策略。spec 阶段已经跑过 `agentcore deploy --diff`：删除 CDK 角色和它的 DefaultPolicy，Runtime **原地更新**（`RUNTIME_ARN` 不变，Gateway target 不用改）。X-Ray 写权限随之去掉，这是预期的（`disableTransactionSearch`，不用 X-Ray）。
- **代码（T3.0、T3.2）**：`codeLocation` 从 `../spike/p0-mcp/` 换成 `../mcp-server/`（P1 的 vendored upstream + 补丁）。T3.0 先修 P2 整体评审留下的 M1–M4，再加补丁 **P-09**：Gateway 的每次工具调用都是一个新的 Runtime session（新 microVM），microVM 销毁时连接池里的连接不会被客户端关闭，而 Doris 默认 `wait_timeout` 是 28800 s，`mcp_svc` 的 `max_user_connections` 是 100（P2 T2.3）。P-09 让每个池连接执行 `SET wait_timeout = 600`（`session_wait_timeout_seconds`，必须大于 `pool_idle_timeout_seconds = 300`，也就是 aiomysql 的 `pool_recycle`），这样残留连接最多存活 10 分钟。
- **依赖（T3.2）**：CodeZip 由 agentcore CLI 用 uv 按 `mcp-server/pyproject.toml` 为 aarch64 解析。CLI 先试 manylinux2014，`rapidfuzz` 没有这个平台的 wheel，所以最后落在 manylinux_2_28。`pyproject.toml` 只锁了直接依赖。spec 阶段实测，两个传递依赖解析到的版本比 `.venv` 里的新：`caio` 0.12.9（`.venv` 是 0.12.5）、`platformdirs` 4.12.0（`.venv` 是 4.11.15）。T3.2 锁定这两个依赖，并用一个检查脚本对比 CodeZip 和 `.venv` 的 88 个 dist：锁定前 2 个不同，锁定后 0 个。
- **验证分三层**：
  - T3.3 SigV4 直连 Runtime：12 个工具、flow、逐次耗时（共享 session 和每次新 session）、CloudWatch 审计日志、`reconcile.py mcp --url` 11/11、Doris 连接来源；
  - T3.4 经 Gateway：`doris___*` 12 个、逐次耗时、20 个并发、连接数和空闲时长、Gateway DEBUG 错误信息的泄漏检查；
  - T3.5 收紧 host：`doris/02_mcp_user_vpc.sql` 先建 `'mcp_svc'@'172.31.%'` 并授权，最后才 `DROP USER IF EXISTS 'mcp_svc'@'%'`；然后用 `permission_matrix.py --url` 经 Runtime 复核权限。同一任务还做 R-40 的只读复核（本系统的 3 个 SG、Runtime ENI、Doris 实例），并请用户在 Doris 主机上检查 FE 审计日志里有没有 `mcp_svc` 的明文密码（只输出计数）。
- **T3.5 之后开发机不能再以 `mcp_svc` 登录**（1045，这是预期的；P2 整体评审遗留事项里写的「完成后确认开发机仍能以 `mcp_svc` 登录」是错的，已在 progress.md 更正）。所以：
  - `reconcile.py mcp --url` 的参照 SQL 用 `demo_ro` 在本机执行，指标经 Runtime 以 `mcp_svc` 查询；
  - `permission_matrix.py --url` 的只读检查走 Runtime 的 `execute_query`；
  - 写探针只能直连，P2 T2.3 已经跑过，本阶段不再跑。
- **spec 阶段的只读预验证**：
  - SigV4 客户端直连现在的 spike Runtime：`list` 成功，`connected+initialized in 5516 ms`；关闭时 Runtime 返回 404，这是预期的；
  - 草稿 server 在本机以 `mcp_svc` 运行：`SELECT @@wait_timeout` = 600；`time` 12 个调用全部 ok（第一次 `list_metrics` 11.5 s、`reload_semantic_layer` 7.7 s，都是加载语义层）；`conns` 能按账号计数；
  - `agentcore validate` + `deploy --diff`（结果见上）；
  - `infra/10-network.sh` 的自检：3 个 SG 都是 `no open inbound rule`。

**Tech Stack:** Python 3.12（仓库 `.venv`）· fastmcp Client + httpx · botocore SigV4 · agentcore CLI 0.30.0（CDK）· AWS CLI v2（IAM、bedrock-agentcore-control、logs）· uv · pymysql · bash · unittest

**Spec:** `specs/doris-mcp-quick/requirements.md`（R-10、R-12、R-30、R-31、R-32、R-40、R-41、R-42；D6、D8）、`specs/doris-mcp-quick/design.md`（§4.5、§5.2、§6.1、§7、§11 P3 行、§13、§14）

## Global Constraints

- 只用 us-east-1、账号 `890717383483`（环境变量里的凭证）；不要用 AWS profile `lijingfz`。本机环境的 `AWS_DEFAULT_REGION` 是 us-west-2，所以每条 AWS 命令都要显式指定 `--region us-east-1` 或 `AWS_REGION=us-east-1`（`infra/*.sh` 通过 `lib.sh` 已经这样做了）。
- **GATE**（CLAUDE.md）：本计划有 4 个 GATE，每个都先展示 dry-run / diff 输出，用户明确确认后才执行；一次确认只对应那一次操作：
  1. T3.1：建 IAM 角色 `doris-mcp-runtime-role` 和它的内联策略；
  2. T3.2：`agentcore deploy`，换代码和执行角色，同时删除 CDK 角色；
  3. T3.4：`SYNC=1 APPLY=1 bash infra/30-gateway.sh`，同步 target 的工具列表；它还会重新应用 Gateway 的内联策略和 `update-gateway`，内容都不变；
  4. T3.5：以 root 把 `mcp_svc` 迁到 `'172.31.%'`。

  T3.5 另有一项**用户侧**操作：在 Doris 主机上检查 FE 审计日志。如果发现明文密码，轮换密码需要另外的 GATE，本计划不执行，先停下来和用户商量。每个 GATE 的回滚也需要 GATE。
- 密码、secret、Cognito ClientSecret、`GW_TOKEN` 不出现在仓库、命令行参数、日志、输出和对话里，**grep 的参数也不行**：要按值查找，只能用 `grep -cF -f <(printf '%s\n' "$PW")`，而且只输出计数。
- **以下内容不出现在输出里**：Doris 主机地址、Doris 私网 IP、开发机 IP，以及 `RUNTIME_URL` / `GW_URL`。所有可能含这些内容的输出都经过 `sed -E 's/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'`（Doris 主机地址是 IPv4 字面量，这条 sed 能覆盖）。spec 阶段确认过，这些 IP 会出现在：Runtime 的 CloudWatch 日志和本机 server 的日志（启动行、连接池、访问 FE HTTP 的 URL）、`get_query_profile` 返回的 profile（BE 节点 IP）、Doris 连不上时的 2003 错误消息（upstream 的 `sensitive_mask` 不遮 host）。所以这些内容只计数，或者经过这条 sed 再看。
- **不要打印**：`dorismcp/agentcore/agentcore.json`（含私网 IP）、`render-agentcore.py --check` 的输出、`agentcore status` 的原始 JSON。
- Doris 凭证只从 `/home/ubuntu/AI-code/Doris-test/credentials.env` 在**子 shell** 里 `source`（该文件没有 `export` 行），只 export 需要的变量；**永远不要 echo 或 cat 这个文件**。`DORIS_ROOT_*` 从不以原名传给任何进程。
- `demo_ro` 只做 SELECT / SHOW / DESCRIBE；**不要用 `demo_ro` 试探写操作**。root 只在 T3.5 的 GATE 里执行 `doris/02_mcp_user_vpc.sql` 的 5 条语句。MCP 不执行任何 DDL/DML。
- 安全组不改（R-40）：Runtime 已经在 `doris-mcp-rt` 里，Doris 侧 9030/8030 只对 `RT_SG` 开放；`doris-demo-sg` 现有的 `13.125.9.110/32` 规则不动。T3.5 做 R-40 复核。
- Gateway `pragent-github-gw` 和其他项目的日志组、角色都不碰。Gateway 的 `exceptionLevel=DEBUG` 保留到 T5.5（T3.4 做泄漏检查）。
- 本机起的 server 用端口停止（`ss -ltnp` 找 pid 再 `kill`），**不要用 `pkill -f`**（会杀掉自己的 shell）。
- 不修改 `prepare/`；`mcp-server/` 只改 T3.0（M3、P-09）和 T3.2（依赖锁定）写明的地方，改动记进 `mcp-server/UPSTREAM.md`。
- 测试用 unittest：`.venv/bin/python -m unittest discover -s doris/test`、`-s scripts/test`、`-s mcp-server/test -p 'test_agentcore_*.py'`（**不要**加 `-t .`）。shell 测试用假的 `aws` / `python`，不访问 AWS 或 Doris。upstream 离线测试要带 `PYTHON_BIN=$PWD/.venv/bin/python`。
- 代码、注释、脚本输出用英文；计划和 progress 用中文。
- 每个任务结束：勾选 `tasks.md` → 更新 `progress.md`（「当前状态」+ 追加日志）→ `bash scripts/check-secrets.sh` → commit（message 结尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`）。全部在分支 `p3-deploy` 上，不 push（D8：P3 完成后是否推送由用户决定）。

## Review Focus

1. **密码、Doris 地址和私网 IP 泄漏**：可能经由这些渠道出去 —— Runtime 返回的错误（Gateway 的 DEBUG 会把它带给客户端）、CloudWatch 日志、`agentcore status` / deploy 日志（env 里有私网 IP）、smoke / 审计 / 权限矩阵脚本的输出、调用方已经 export 的 root 变量。相关的测试和检查：
   - T3.0：wrapper 测试 `caller-exported DORIS_ROOT_* / DORIS_RO_* / DORIS_ADMIN_PASSWORD do not reach python`；`test_long_messages_are_masked_before_they_are_cut`、`test_long_errors_are_masked_before_they_are_cut`、`test_an_unexpected_error_is_one_masked_line_and_exit_2`、`test_secrets_client_setup_failure_is_a_settings_error`；check-secrets 的 `unreadable secrets fail the check`；
   - T3.3：`test_never_prints_params_errors_or_client_ids`、`test_counts_only_never_hosts_or_statements`、`test_remote_setup_error_is_one_masked_line`；
   - T3.5：`test_doris_errors_keep_their_errno_and_ips_are_masked`；
   - T3.4 的 DEBUG 泄漏计数；各 GATE 步骤的 sed 过滤。
2. **执行角色错了或权限过宽**：用了 CDK 角色、别的账号的角色、通配 secret ARN，或者 get-role 失败时误建角色。相关的测试和检查：
   - T3.1：`test_requires_the_project_role`、`test_refuses_the_cdk_role`、`test_refuses_a_role_of_another_account`、`test_spike_keeps_the_cli_role`；
   - T3.1 test-35：`apply/wildcard secret ARN: no IAM write`、`apply/other-account secret ARN: fails`、`apply/get-role denied: fails instead of creating`、`apply/missing: permission policy (logs of dorismcp_dorismcp + one secret)`；
   - T3.2 deploy 后确认栈里没有 `AWS::IAM::Role`，Runtime 的 `roleArn` 就是这个角色。
3. **CodeZip 里的依赖与测试过的 `.venv` 不一致**：pyproject 只锁直接依赖，传递依赖会漂移。检查：T3.2 的 codezip 检查，锁定前 RED（2 个不同）、锁定后 GREEN（0 个），deploy 后再对 staging 目录跑一次。
4. **连接泄漏和并发**：每次 Gateway 调用都是新 microVM，残留连接可能耗尽 `max_user_connections=100`；20 个并发工具调用对 `pool_max_size=5` 和 Quick 60 s 上限的影响。相关的测试和检查：
   - T3.0：`test_pool_sets_the_session_wait_timeout`、`test_shipped_config_outlives_the_pool_recycle`、`test_no_init_command_without_the_setting`；
   - T3.3：`test_parallel_is_capped`、`test_fresh_opens_one_session_per_call`、`test_over_budget_fails`、`test_max_idle`；
   - T3.4：20 个并发，`conns --max-idle 610` 当时测一次，11 分钟后再测一次。
5. **迁移 host 时把账号锁死**：先 DROP 后 CREATE、DROP 了别的身份或别的用户、新身份的权限和原来的不一致、迁移前开的 Runtime session 还在用旧身份。相关的测试和检查：
   - T3.5：`test_drop_before_any_other_identity_is_created_is_refused`、`test_dropping_an_identity_the_script_also_sets_up_is_refused`、`test_dropping_another_user_is_refused`、`test_same_grants_as_01_on_the_new_host`、`test_the_old_identity_fails_the_host_check`；
   - T3.5 shell：`e2e 02 dry-run: new identity first, '%' dropped last`；
   - T3.5 的 GATE 之后全部用新 session 复测，回滚是重跑 `01_mcp_user.sql`。

---

## 文件地图

| 文件 | 状态 | 任务 | 作用 |
|---|---|---|---|
| `doris/publish-semantic.sh`、`doris/apply-admin-sql.sh` 及其 shell 测试 | 修改 | T3.0 | M1：先 `unset` 调用方已经 export 的 `DORIS_ROOT_*`、`DORIS_RO_*`、`DORIS_ADMIN_PASSWORD`（`source` 会保留它们的 export 属性）|
| `doris/permission_matrix.py`、`doris/reconcile.py` 及其测试 | 修改 | T3.0 | M2：只读检查失败时跳过探针；1105 必须含 access / command denied；先 mask 再截断；重复对象合并；兜底 `except` 输出一行并 exit 2 |
| `mcp-server/src/agentcore_ext/settings.py`、`test_agentcore_settings.py` | 修改 | T3.0 | M3：构造 Secrets Manager client 失败也是 `SettingsError`（只报类型名）|
| `scripts/check-secrets.sh`、`scripts/test/test-check-secrets.sh` | 修改 | T3.0 | M4：读不到 secret 时检查失败，不再是 WARN + OK |
| `mcp-server/config/mcp-server.toml`、`src/config/loader.py`、`src/core/connection.py`、`test/test_agentcore_session_timeout.py`、`UPSTREAM.md` | 修改 / 新建 | T3.0 | 补丁 P-09：每个池连接执行 `SET wait_timeout = 600`；6 个测试 |
| `infra/35-runtime-role.sh`、`infra/policies/runtime-{trust,exec}.json`、`infra/test/test-35-runtime-role.sh` | 新建 | T3.1 | Runtime 专用执行角色；30 项离线检查 |
| `scripts/render-agentcore.py`、`scripts/test/test_render_agentcore.py` | 修改 / 新建 | T3.1 | `--phase server` 写 `executionRoleArn`，只接受本项目的角色；9 个测试 |
| `mcp-server/pyproject.toml`、`mcp-server/UPSTREAM.md` | 修改 | T3.2 | 锁定 `caio==0.12.5`、`platformdirs==4.11.15` |
| `dorismcp/agentcore/agentcore.json`、`dorismcp/agentcore/.cli/deployed-state.json`、`infra/state.env` | 修改 | T3.1、T3.2 | render / deploy / `25-runtime-state.sh` 写入（`RT_ROLE_ARN`、新的 `RUNTIME_ROLE_ARN`）|
| `scripts/agentcore_client.py`、`scripts/test/test_agentcore_client.py` | 新建 | T3.3 | SigV4 签名的 fastmcp 客户端（直连 Runtime，AWS_IAM 入站认证）|
| `scripts/mcp_smoke.py`、`scripts/smoke_calls.json`、`scripts/test/test_mcp_smoke.py` | 修改 / 新建 | T3.3 | `--sigv4`、`time`（逐次耗时、并发、每次新 session、60 s 预算）、`conns`（连接数、来源前缀、空闲时长）|
| `scripts/audit_check.py`、`scripts/test/test_audit_check.py` | 新建 | T3.3 | 统计 CloudWatch 里的 `doris_new_mcp.audit` 记录（R-32），只输出计数 |
| `doris/reconcile.py`、`doris/test/test_reconcile.py` | 修改 | T3.3 | `mcp --url`：指标经部署的 Runtime 查询 |
| `doris/02_mcp_user_vpc.sql`、`doris/admin_sql.py`、`doris/test/test_admin_sql.py`、`test_mcp_user_sql.py`、`test-apply-admin-sql.sh` | 新建 / 修改 | T3.5 | host 迁移：白名单加 `DROP USER IF EXISTS`（只允许同一用户的另一个身份，且必须先建新身份）|
| `doris/permission_matrix.py`、`doris/test/test_permission_matrix.py` | 修改 | T3.5 | `--url`（只读检查经 Runtime）、`--expect-host` |

常用测试命令：

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 最终 151 个
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 最终 53 个（T3.1 起才有）
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 最终 89 个
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3     # 🎉 All tests passed!
for t in doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh infra/test/test-35-runtime-role.sh \
         infra/test/test-40-doris-secret.sh infra/test/test-lib.sh scripts/test/test-check-secrets.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 每行 all passed
```

---

### Task T3.0：P2 整体评审遗留 M1–M4 + 补丁 P-09（纯离线）

来源：`progress.md`「2026-09-27 P2 整体评审（opus）」的遗留事项 M1–M4，以及本计划新增的补丁 P-09（Architecture 第 2 条）。M1、M2 必须在 T3.5 复用 `apply-admin-sql.sh` 和 `permission_matrix.py` 之前完成，M4 必须在 T3.2 第一次 deploy `DORIS_SECRET_ID` 之前完成，所以都放在最前面。本任务不连 Doris，也不碰 AWS，没有 GATE。

**Files:**
- Modify：`doris/apply-admin-sql.sh`、`doris/publish-semantic.sh`（M1）；`doris/permission_matrix.py`、`doris/reconcile.py`（M2）；`mcp-server/src/agentcore_ext/settings.py`（M3）；`scripts/check-secrets.sh`（M4）
- Test：`doris/test/test-apply-admin-sql.sh`、`doris/test/test-publish-semantic.sh`、`doris/test/test_permission_matrix.py`、`doris/test/test_reconcile.py`、`mcp-server/test/test_agentcore_settings.py`、`scripts/test/test-check-secrets.sh`（`doris/test` 119 → 125，`test_agentcore_*.py` 82 → 83）
- Create：`mcp-server/test/test_agentcore_session_timeout.py`（P-09，6 个测试，83 → 89）
- Modify：`mcp-server/config/mcp-server.toml`、`mcp-server/src/config/loader.py`、`mcp-server/src/core/connection.py`、`mcp-server/UPSTREAM.md`（P-09）、`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：P2 的 `doris/permission_matrix.py`（`classify_error(error) -> "denied" | "error"`、`parse_grants(row) -> dict[str, dict[str, set[str]]]`、`main(argv, env, …) -> int`）、`doris/reconcile.py`（`McpBackend(client, workspace)`、`_mask(text, secrets)`）、`agentcore_ext.settings.load_settings(env=None, secrets_client=None) -> Settings`（失败抛 `SettingsError`）、`scripts/check-secrets.sh` 块 1b；upstream 的 `config.loader.ClusterConfig`、`core.connection.ConnectionPool`（`aiomysql.create_pool(…, pool_recycle=pool_idle_timeout)`）
- Produces：
  - M1：两个 wrapper 开头 `unset "${!DORIS_ROOT_@}" "${!DORIS_RO_@}" DORIS_ADMIN_PASSWORD`，调用方已经 export 的这些变量不会传给 python。
  - M2：`permission_matrix.py` 只有全部只读检查都 ok 才跑 `store_init` 和写探针，否则输出 `SKIPPED probes: N read-only check(s) failed; …`；1105 只有消息里含 `access denied` / `command denied` 才算 denied（`DENIED_1105`）；`_brief(error, secrets)` 先 mask 再截断；`parse_grants` 遇到重复对象合并权限；`main()` 的兜底 `except Exception` 输出一行 mask 过的 `FAILED: <类型>: <消息>`，exit 2。`reconcile.py` 的 `McpBackend(client, workspace, secrets=())` 同样先 mask 再截断。T3.3、T3.5 在此基础上扩展这两个文件。
  - M3：构造 Secrets Manager client 失败（例如 `NoRegionError`）也抛 `SettingsError("cannot read secret <id>: <类型名>")`，不链接原异常。
  - M4：`check-secrets.sh` 读不到某个 secret 时输出 `FAIL: cannot read secret <id> — its exact-value check did not run`，最后一行 `check-secrets: FAILED — do not commit`，exit 1。此后每个收尾步骤的 check-secrets 都要求 AWS 凭证有效。
  - P-09：`[query] session_wait_timeout_seconds`（`ClusterConfig.session_wait_timeout: int | None`，默认 `None`）；不为 `None` 时 `ConnectionPool` 给 `aiomysql.create_pool` 传 `init_command="SET wait_timeout = N"`。仓库的 `mcp-server/config/mcp-server.toml` 设为 `600`（> `pool_idle_timeout_seconds = 300`）。T3.2 在本机验证 `SELECT @@wait_timeout` = 600，T3.4 验证残留连接的空闲时长不超过 600 s。

- [ ] **Step 1：确认前置条件，建分支，提交计划**

```bash
git branch --show-current     # 期望：main
git status --short
```
期望：恰好 5 行 —— `?? specs/doris-mcp-quick/plans/P3-deploy.md`，以及 `specs/doris-mcp-quick/` 下 ` M` 的 `design.md`、`progress.md`、`requirements.md`、`tasks.md`（这是用户 review 过的计划和 spec 修订）。如果还有其他改动，先停下来问用户。

```bash
aws sts get-caller-identity --query Account --output text              # 期望：890717383483
.venv/bin/python --version                                             # 期望：Python 3.12.x
test -r /home/ubuntu/AI-code/Doris-test/credentials.env && echo "credentials.env readable"
bash scripts/check-secrets.sh | tail -1                                # 期望：check-secrets: OK (… files scanned)
git switch -c p3-deploy
git add specs/doris-mcp-quick/plans/P3-deploy.md specs/doris-mcp-quick/{design,progress,requirements,tasks}.md
git commit -m "docs(p3): P3 plan (AgentCore deploy); design v0.5, requirements v1.4

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2：写 M1–M4 的失败测试**

6 个测试文件的改动：
- 两个 wrapper 测试在调用方 export `DORIS_ROOT_USER`、`DORIS_RO_PASSWORD`、`DORIS_ADMIN_PASSWORD`，断言它们不会传到 stub python（M1）；
- `test_permission_matrix.py` 新增 5 个测试（M2 a、b、c、d、e），并把 Apply 测试的 denied fixture 改成真实 Doris 返回的 1105；
- `test_reconcile.py` 新增 1 个测试（M2 c，两个 subTest：non-JSON 和工具错误）；
- `test_agentcore_settings.py` 新增 1 个测试（M3）；
- `test-check-secrets.sh` 把「读不到 secret」的用例从 WARN + OK 改成失败（M4）。

```bash
git apply <<'PATCH'
diff --git a/doris/test/test-apply-admin-sql.sh b/doris/test/test-apply-admin-sql.sh
index 0a8007b..c1dded0 100644
--- a/doris/test/test-apply-admin-sql.sh
+++ b/doris/test/test-apply-admin-sql.sh
@@ -28,12 +28,13 @@ printf '%s\n' 'DORIS_HOST=198.51.100.7' 'DORIS_MYSQL_PORT=9030' 'DORIS_HTTP_PORT
   'DORIS_RO_USER=demo_ro' 'DORIS_RO_PASSWORD=RoPw0123456789' > "$TMP/cred.env"
 
 FAILS=0
+CALLER_ENV=()  # extra VAR=value pairs the caller has already exported
 check() { # NAME EXPECTED ACTUAL
   if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
 }
 run_wrapper() { # APPLY → sets RC, REC (what the stub saw), LOG (aws calls)
   : > "$TMP/aws.log"; : > "$TMP/stub.out"
-  env -u DORIS_HOST -u DORIS_ROOT_PASSWORD -u DORIS_RO_PASSWORD PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" \
+  env -u DORIS_HOST -u DORIS_ROOT_PASSWORD -u DORIS_RO_PASSWORD "${CALLER_ENV[@]}" PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" \
     STUB_OUT="$TMP/stub.out" PYTHON_BIN="$TMP/bin/stub-python" DORIS_CRED_FILE="$TMP/cred.env" APPLY="$1" \
     bash "$SCRIPT" doris/01_mcp_user.sql > "$TMP/out.txt" 2>&1
   RC=$?; REC="$(cat "$TMP/stub.out")"; LOG="$(cat "$TMP/aws.log")"
@@ -52,6 +53,16 @@ check "dry-run: APPLY=0 reaches python" yes "$(has "$REC" "env: APPLY=0")"
 check "never exports root/ro variables by their original names" "no|no" \
   "$(has "$REC" "DORIS_ROOT_")|$(has "$REC" "DORIS_RO_")"
 
+# M1: `source` keeps the export attribute of a variable the caller already exported, so without the
+# wrapper's unset the file's root/ro values (and the caller's admin password) would reach python.
+CALLER_ENV=(DORIS_ROOT_USER=caller DORIS_ROOT_PASSWORD=CallerRootPw DORIS_RO_USER=caller
+            DORIS_RO_PASSWORD=CallerRoPw DORIS_ADMIN_PASSWORD=CallerAdminPw)
+run_wrapper 0
+CALLER_ENV=()
+check "caller-exported: dry-run exit 0, admin user from the file" "0|yes" "$RC|$(has "$REC" "env: DORIS_ADMIN_USER=root")"
+check "caller-exported DORIS_ROOT_* / DORIS_RO_* / DORIS_ADMIN_PASSWORD do not reach python" "no|no|no" \
+  "$(has "$REC" "DORIS_ROOT_")|$(has "$REC" "DORIS_RO_")|$(has "$REC" "DORIS_ADMIN_PASSWORD")"
+
 run_wrapper 1
 check "apply: admin user and password exported" "yes|yes" \
   "$(has "$REC" "env: DORIS_ADMIN_USER=root")|$(has "$REC" "env: DORIS_ADMIN_PASSWORD=<set>")"
diff --git a/doris/test/test-publish-semantic.sh b/doris/test/test-publish-semantic.sh
index 63b6b4d..0426273 100644
--- a/doris/test/test-publish-semantic.sh
+++ b/doris/test/test-publish-semantic.sh
@@ -21,13 +21,14 @@ printf '%s\n' 'DORIS_HOST=198.51.100.7' 'DORIS_MYSQL_PORT=9030' 'DORIS_HTTP_PORT
   'DORIS_RO_USER=demo_ro' 'DORIS_RO_PASSWORD=RoPw0123456789' > "$TMP/cred.env"
 
 FAILS=0
+CALLER_ENV=()  # extra VAR=value pairs the caller has already exported
 check() { # NAME EXPECTED ACTUAL
   if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
 }
 run_wrapper() { # APPLY [ARGS...] → sets RC, REC (what the stub saw)
   local apply="$1"; shift
   : > "$TMP/stub.out"
-  env -u DORIS_HOST -u DORIS_ROOT_PASSWORD -u DORIS_RO_PASSWORD STUB_OUT="$TMP/stub.out" \
+  env -u DORIS_HOST -u DORIS_ROOT_PASSWORD -u DORIS_RO_PASSWORD "${CALLER_ENV[@]}" STUB_OUT="$TMP/stub.out" \
     PYTHON_BIN="$TMP/bin/stub-python" DORIS_CRED_FILE="$TMP/cred.env" APPLY="$apply" \
     bash "$SCRIPT" "$@" > "$TMP/out.txt" 2>&1
   RC=$?; REC="$(cat "$TMP/stub.out")"
@@ -45,6 +46,16 @@ check "dry-run: APPLY=0 reaches python" yes "$(has "$REC" "env: APPLY=0")"
 check "never exports root/ro variables by their original names" "no|no" \
   "$(has "$REC" "DORIS_ROOT_")|$(has "$REC" "DORIS_RO_")"
 
+# M1: `source` keeps the export attribute of a variable the caller already exported, so without the
+# wrapper's unset the file's root/ro values (and the caller's admin password) would reach python.
+CALLER_ENV=(DORIS_ROOT_USER=caller DORIS_ROOT_PASSWORD=CallerRootPw DORIS_RO_USER=caller
+            DORIS_RO_PASSWORD=CallerRoPw DORIS_ADMIN_PASSWORD=CallerAdminPw)
+run_wrapper 0
+CALLER_ENV=()
+check "caller-exported: dry-run exit 0, admin user from the file" "0|yes" "$RC|$(has "$REC" "env: DORIS_ADMIN_USER=root")"
+check "caller-exported DORIS_ROOT_* / DORIS_RO_* / DORIS_ADMIN_PASSWORD do not reach python" "no|no|no" \
+  "$(has "$REC" "DORIS_ROOT_")|$(has "$REC" "DORIS_RO_")|$(has "$REC" "DORIS_ADMIN_PASSWORD")"
+
 run_wrapper 1
 check "apply: admin password exported" yes "$(has "$REC" "env: DORIS_ADMIN_PASSWORD=<set>")"
 check "apply: APPLY=1 reaches python" yes "$(has "$REC" "env: APPLY=1")"
diff --git a/doris/test/test_permission_matrix.py b/doris/test/test_permission_matrix.py
index 317d0ca..e4b5ca4 100644
--- a/doris/test/test_permission_matrix.py
+++ b/doris/test/test_permission_matrix.py
@@ -49,8 +49,9 @@ DEMO_RO_GRANTS = grants_row(f"internal.ecom: Select_priv; {DEFAULT_DBS}", UserId
 
 
 def denied(action="LOAD"):
+    # Doris 4.1 refuses with errno 1105, not MySQL's 1142 (seen for every T2.3 probe).
     return pymysql.err.OperationalError(
-        1142, f"errCode = 2, detailMessage = {action} command denied to user 'mcp_svc'@'10.0.0.9' for table x")
+        1105, f"errCode = 2, detailMessage = {action} command denied to user 'mcp_svc'@'10.0.0.9' for table 'x'")
 
 
 class FakeCursor:
@@ -139,6 +140,11 @@ class ParseGrants(unittest.TestCase):
         parsed = parse_grants({"GlobalPrivs": "Node_priv,Admin_priv", "Roles": "operator", "TablePrivs": ""})
         self.assertEqual(parsed, {"GlobalPrivs": {"*": {"Node_priv", "Admin_priv"}}, "Roles": {"*": {"operator"}}})
 
+    def test_a_repeated_object_merges_instead_of_hiding_the_first_entry(self):
+        # Overwriting would drop Load_priv here and let grant_problems pass an over-privileged account.
+        parsed = parse_grants({"DatabasePrivs": "internal.ecom: Load_priv; internal.ecom: Select_priv"})
+        self.assertEqual(parsed, {"DatabasePrivs": {"internal.ecom": {"Load_priv", "Select_priv"}}})
+
     def test_non_privilege_columns_are_ignored(self):
         parsed = parse_grants({"UserIdentity": IDENTITY, "Password": "Yes", "Comment": "x", "RequireSan": None})
         self.assertEqual(parsed, {})
@@ -185,6 +191,13 @@ class ClassifyError(unittest.TestCase):
             with self.subTest(message=message):
                 self.assertEqual(classify_error(pymysql.err.OperationalError(1105, message)), "denied")
 
+    def test_a_1105_needs_access_denied_or_command_denied(self):
+        # errno 1105 is Doris's generic error: "denied" elsewhere in the text is not a privilege refusal.
+        for message in ("errCode = 2, detailMessage = Unknown column 'denied_at' in 'ecom.fact_order'",
+                        "errCode = 2, detailMessage = Permission denied: /opt/doris/fe/doris-meta"):
+            with self.subTest(message=message):
+                self.assertEqual(classify_error(pymysql.err.OperationalError(1105, message)), "error")
+
     def test_other_errors_are_not_denials(self):
         for errno, message in ((1105, "errCode = 2, detailMessage = Unknown table 'mcp_perm_probe'"),
                                (1064, "errCode = 2, detailMessage = Syntax error"),
@@ -271,7 +284,7 @@ class DryRun(unittest.TestCase):
         conn = FakeDoris({"SELECT 1 FROM internal.ecom.dim_brand": denied("SELECT")})
         rc, out, _, _, _ = run_main(conn=conn)
         self.assertEqual(rc, 1)
-        self.assertIn("FAIL  select: internal.ecom.dim_brand: 1142", out)
+        self.assertIn("FAIL  select: internal.ecom.dim_brand: 1105 SELECT command denied", out)
 
     def test_missing_metadata_row_fails_with_a_hint(self):
         # Upstream would INSERT the row on first use, which needs LOAD_PRIV: T2.5 must publish first.
@@ -289,14 +302,22 @@ class DryRun(unittest.TestCase):
     def test_a_check_that_errors_is_reported_by_name_and_the_rest_still_run(self):
         rc, out, _, _, _ = run_main(conn=FakeDoris({"SHOW GRANTS": denied("SHOW")}))
         self.assertEqual(rc, 1)
-        self.assertIn("FAIL  grants: 1142", out)
+        self.assertIn("FAIL  grants: 1105 SHOW command denied", out)
         self.assertIn("ok    databases", out)
         self.assertIn("3/4 checks pass", out)
 
+    def test_long_messages_are_masked_before_they_are_cut(self):
+        # Cutting first would keep a prefix of the password that the mask no longer recognises.
+        leak = pymysql.err.OperationalError(1105, "SELECT command denied " + "x" * 130 + PASSWORD)
+        rc, out, err, _, _ = run_main(conn=FakeDoris({"SELECT 1 FROM internal.ecom.dim_brand": leak}))
+        self.assertEqual(rc, 1)
+        self.assertNotIn(PASSWORD[:8], out + err)
+        self.assertIn("x***", out)
+
     def test_show_property_failure_is_only_informational(self):
         rc, out, err, _, _ = run_main(conn=FakeDoris({"SHOW PROPERTY": denied("SHOW")}))
         self.assertEqual(rc, 0, err)
-        self.assertIn("info  max_user_connections=unavailable (1142", out)
+        self.assertIn("info  max_user_connections=unavailable (1105", out)
 
     def test_another_account_is_a_usage_error(self):
         conn = FakeDoris({"SELECT CURRENT_USER()": [{"identity": "'demo_ro'@'%'"}]})
@@ -322,6 +343,14 @@ class DryRun(unittest.TestCase):
         self.assertIs(kwargs["cursorclass"], pymysql.cursors.DictCursor)
         self.assertTrue(kwargs["autocommit"])
 
+    def test_an_unexpected_error_is_one_masked_line_and_exit_2(self):
+        conn = FakeDoris({"SELECT CURRENT_USER()": RuntimeError(f"cursor broke on 10.0.0.1 ({PASSWORD})")})
+        rc, out, err, conn, _ = run_main(conn=conn)
+        self.assertEqual(rc, 2)
+        self.assertEqual(err.strip(), "FAILED: RuntimeError: cursor broke on *** (***)")
+        self.assertNotIn(PASSWORD, out + err)
+        self.assertTrue(conn.closed)
+
     def test_connect_errors_are_masked(self):
         def refuse(**kwargs):
             raise pymysql.err.OperationalError(1045, f"Access denied for 'mcp_svc' on 10.0.0.1 using {PASSWORD}")
@@ -341,12 +370,24 @@ class Apply(unittest.TestCase):
         probes = write_probes(IDENTITY)
         for probe in probes:
             self.assertEqual(conn.executed.count(probe.sql), 1, probe.sql)
-            self.assertIn(f"ok    probe {probe.name}: denied (1142", out)
+            self.assertIn(f"ok    probe {probe.name}: denied (1105 LOAD command denied", out)
         self.assertIn("ok    probe store_init: discover_workspaces -> ecom", out)
         total = 4 + 1 + len(probes)
         self.assertIn(f"{total}/{total} checks pass", out)
         self.assertNotIn("DRY-RUN", out)
 
+    def test_a_failed_read_only_check_skips_store_init_and_the_probes(self):
+        # A wrong account (e.g. with LOAD_PRIV) must not get its writes tried: the probes are no-ops only
+        # when the read-only checks hold.
+        row = grants_row(f"internal.ecom: Select_priv,Load_priv; {DEFAULT_DBS}; "
+                         "internal.system_mcp: Select_priv,Create_priv")
+        rc, out, _, conn, seen = run_main(conn=FakeDoris({"SHOW GRANTS": [row]}), apply=True)
+        self.assertEqual(rc, 1)
+        self.assertEqual(seen["store_init"], [])
+        self.assertEqual({s.split()[0] for s in conn.executed}, {"SELECT", "SHOW"})
+        self.assertIn("SKIPPED probes: 1 read-only check(s) failed; store_init and the write probes did not run", out)
+        self.assertIn("3/4 checks pass", out)
+
     def test_an_allowed_write_fails(self):
         conn = FakeDoris({"INSERT INTO ecom.dim_brand": []})
         rc, out, _, _, _ = run_main(conn=conn, apply=True)
diff --git a/doris/test/test_reconcile.py b/doris/test/test_reconcile.py
index c9dc520..ae5563f 100644
--- a/doris/test/test_reconcile.py
+++ b/doris/test/test_reconcile.py
@@ -269,6 +269,19 @@ class Mcp(unittest.TestCase):
         with self.assertRaisesRegex(ReconcileError, "non-JSON"):
             asyncio.run(McpBackend(client, "ecom").query(MONEY))
 
+    def test_long_errors_are_masked_before_they_are_cut(self):
+        # Cutting first would keep a prefix of the password that the mask no longer recognises.
+        # The password starts 10 characters before the cut (300 / 500 characters).
+        cases = {"non-JSON": "Error calling tool: " + "x" * 270 + PASSWORD,
+                 "tool error": {"success": False, "error": {"code": "QUERY_ERROR", "message": "x" * 454 + PASSWORD}}}
+        for name, body in cases.items():
+            with self.subTest(name):
+                backend = McpBackend(FakeClient({"query_metric": body}), "ecom", secrets=[PASSWORD])
+                with self.assertRaises(ReconcileError) as caught:
+                    asyncio.run(backend.query(MONEY))
+                self.assertNotIn(PASSWORD[:8], str(caught.exception))
+                self.assertIn("x***", str(caught.exception))
+
     def test_metric_names_reads_one_full_page(self):
         client = FakeClient({"list_metrics": ok([{"name": "gmv", "description": "d"}], {"total_count": 1})})
         self.assertEqual(asyncio.run(McpBackend(client, "ecom").metric_names()), {"gmv"})
diff --git a/mcp-server/test/test_agentcore_settings.py b/mcp-server/test/test_agentcore_settings.py
index b1416a6..d9b7a9e 100644
--- a/mcp-server/test/test_agentcore_settings.py
+++ b/mcp-server/test/test_agentcore_settings.py
@@ -5,11 +5,13 @@ import sys
 import tempfile
 import unittest
 from pathlib import Path
+from unittest import mock
 
 _SRC = Path(__file__).resolve().parent.parent / "src"
 if str(_SRC) not in sys.path:
     sys.path.insert(0, str(_SRC))
 
+from agentcore_ext import settings as settings_module  # noqa: E402
 from agentcore_ext.settings import SettingsError, load_settings  # noqa: E402
 
 PW = "env-s3cret"
@@ -117,6 +119,18 @@ class TestSettingsErrors(unittest.TestCase):
         self.assertIsNone(ctx.exception.__cause__)
         self.assertTrue(ctx.exception.__suppress_context__)
 
+    def test_secrets_client_setup_failure_is_a_settings_error(self):
+        # boto3 client construction (e.g. botocore.exceptions.NoRegionError) must reach main()'s
+        # `except SettingsError` (exit 2), not escape as a traceback.
+        env = {**BASE, "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}
+        boom = RuntimeError(f"cannot build client, password={SECRET_PW}")
+        with mock.patch.object(settings_module, "_secrets_client", side_effect=boom):
+            with self.assertRaises(SettingsError) as ctx:
+                load_settings(env)
+        self.assertEqual(str(ctx.exception), "cannot read secret doris-mcp/mcp_svc: RuntimeError")
+        self.assertIsNone(ctx.exception.__cause__)
+        self.assertTrue(ctx.exception.__suppress_context__)
+
 
 if __name__ == "__main__":
     unittest.main(verbosity=2)
diff --git a/scripts/test/test-check-secrets.sh b/scripts/test/test-check-secrets.sh
index 2f3f36f..a3860be 100644
--- a/scripts/test/test-check-secrets.sh
+++ b/scripts/test/test-check-secrets.sh
@@ -7,12 +7,16 @@ set -uo pipefail
 SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/check-secrets.sh"
 TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
 FAKE_PW="SmPw0123456789abcdefXYZ"
+FAKE_PW2="CgPw0123456789abcdefXYZ"
 mkdir -p "$TMP/bin" "$TMP/repo/scripts"
 cat > "$TMP/bin/aws" <<'FAKE'
 #!/usr/bin/env bash
 printf '%s\n' "$*" >> "$FAKE_LOG"
-if [[ "$1 $2" == "secretsmanager get-secret-value" && "$FAKE_SM" == "readable" && "$*" == *doris-mcp/mcp_svc* ]]; then
-  printf '{"username":"mcp_svc","password":"%s"}\n' "$FAKE_PW"; exit 0
+if [[ "$1 $2" == "secretsmanager get-secret-value" && "$FAKE_SM" == "readable" ]]; then
+  case "$*" in
+    *doris-mcp/mcp_svc*) printf '{"username":"mcp_svc","password":"%s"}\n' "$FAKE_PW"; exit 0 ;;
+    *doris-mcp/cognito-demo-user*) printf '{"username":"demo","password":"%s"}\n' "$FAKE_PW2"; exit 0 ;;
+  esac
 fi
 echo "An error occurred (ResourceNotFoundException) when calling the GetSecretValue operation" >&2; exit 254
 FAKE
@@ -28,7 +32,7 @@ check() { # NAME EXPECTED ACTUAL
 run_check() { # FAKE_SM → sets RC, OUT
   : > "$TMP/aws.log"
   # AWS_REGION points elsewhere, like a shell whose default profile is in another region.
-  OUT="$(cd "$TMP/repo" && PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" FAKE_PW="$FAKE_PW" FAKE_SM="$1" \
+  OUT="$(cd "$TMP/repo" && PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" FAKE_PW="$FAKE_PW" FAKE_PW2="$FAKE_PW2" FAKE_SM="$1" \
     AWS_REGION=eu-west-1 AWS_DEFAULT_REGION=eu-west-1 CRED_FILE="$TMP/no-such-file" bash scripts/check-secrets.sh 2>&1)"
   RC=$?
 }
@@ -47,9 +51,17 @@ check "names the secret and the file" yes "$(has "$OUT" "LEAK: password of secre
 check "never prints the password" no "$(has "$OUT" "$FAKE_PW")"
 check "password never in any aws argv" no "$(has "$(cat "$TMP/aws.log")" "$FAKE_PW")"
 
+printf 'demo login: %s\n' "$FAKE_PW2" > "$TMP/repo/leaky.log.txt"
+run_check readable
+check "leaked password of the second secret fails the check" "1|yes" \
+  "$RC|$(has "$OUT" "LEAK: password of secret doris-mcp/cognito-demo-user found in leaky.log.txt")"
+rm "$TMP/repo/leaky.log.txt"
+
+# An exact-value check that could not run is not a pass (P2 whole review M4).
 run_check unreadable
-check "unreadable secrets are skipped with a warning, not a failure" 0 "$RC"
-check "warning names the secret" yes "$(has "$OUT" "WARN: cannot read secret doris-mcp/mcp_svc")"
+check "unreadable secrets fail the check" 1 "$RC"
+check "the failure names the secret" yes "$(has "$OUT" "FAIL: cannot read secret doris-mcp/mcp_svc")"
+check "the last line says FAILED" "check-secrets: FAILED — do not commit" "$(tail -n 1 <<<"$OUT")"
 
 if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
 echo "all passed"
PATCH
```

- [ ] **Step 3：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s doris/test > /tmp/t30-red.log 2>&1
grep -E '^(FAIL|ERROR):' /tmp/t30-red.log | sed -E 's/ \(.*//' | sort -u
grep -E '^Ran|^FAILED|^OK' /tmp/t30-red.log
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | grep -E '^(FAIL|ERROR):|^Ran|^FAILED|^OK' | sed -E '/^(FAIL|ERROR):/s/ \(.*//'
for t in doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh scripts/test/test-check-secrets.sh; do
  echo "## $t"; bash "$t" 2>&1 | grep -E '^FAIL|failed$|all passed'
done
```
期望：
```
ERROR: test_an_unexpected_error_is_one_masked_line_and_exit_2
ERROR: test_long_errors_are_masked_before_they_are_cut
FAIL: test_a_1105_needs_access_denied_or_command_denied
FAIL: test_a_failed_read_only_check_skips_store_init_and_the_probes
FAIL: test_a_repeated_object_merges_instead_of_hiding_the_first_entry
FAIL: test_long_messages_are_masked_before_they_are_cut
Ran 125 tests in …s
FAILED (failures=5, errors=3)
ERROR: test_secrets_client_setup_failure_is_a_settings_error
Ran 83 tests in …s
FAILED (errors=1)
## doris/test/test-apply-admin-sql.sh
FAIL caller-exported DORIS_ROOT_* / DORIS_RO_* / DORIS_ADMIN_PASSWORD do not reach python: expected 'no|no|no', got 'yes|yes|yes'
1 failed
## doris/test/test-publish-semantic.sh
FAIL caller-exported DORIS_ROOT_* / DORIS_RO_* / DORIS_ADMIN_PASSWORD do not reach python: expected 'no|no|no', got 'yes|yes|yes'
1 failed
## scripts/test/test-check-secrets.sh
FAIL unreadable secrets fail the check: expected '1', got '0'
FAIL the failure names the secret: expected 'yes', got 'no'
FAIL the last line says FAILED: expected 'check-secrets: FAILED — do not commit', got 'check-secrets: OK (1 files scanned)'
3 failed
```
- `doris/test` 的 8 个失败里：`test_long_errors_are_masked_before_they_are_cut`（reconcile）是两个 subTest 的 ERROR，`test_a_1105_needs_access_denied_or_command_denied` 是两个 subTest 的 FAIL，`sort -u` 把它们各合并成一行。
- `test_an_unexpected_error_is_one_masked_line_and_exit_2` 是 ERROR，因为 `main()` 还没有兜底 `except`，异常直接抛到测试里。

- [ ] **Step 4：实现 M1–M4**

两个 wrapper 开头加 `unset`；`permission_matrix.py` 加 `DENIED_1105`、`_brief(error, secrets)`、合并重复对象、只读检查失败时跳过探针、兜底 `except`；`reconcile.py` 的 `McpBackend` 接收 `secrets` 并先 mask 再截断；`settings.py` 在 `try` 里构造 client；`check-secrets.sh` 把 WARN 改成 FAIL：

```bash
git apply <<'PATCH'
diff --git a/doris/apply-admin-sql.sh b/doris/apply-admin-sql.sh
index dee825c..610c155 100644
--- a/doris/apply-admin-sql.sh
+++ b/doris/apply-admin-sql.sh
@@ -6,6 +6,8 @@
 # credentials.env is sourced in a subshell; only host/port, the admin user and (APPLY=1 only) the admin
 # password are exported, under new names, to the python process.
 set -euo pipefail
+# `source` keeps the export attribute of variables the caller already exported: drop them first.
+unset "${!DORIS_ROOT_@}" "${!DORIS_RO_@}" DORIS_ADMIN_PASSWORD
 ROOT="$(cd "$(dirname "$0")/.." && pwd)"
 SQL="${1:?usage: [APPLY=1] bash doris/apply-admin-sql.sh doris/01_mcp_user.sql}"
 CRED="${DORIS_CRED_FILE:-/home/ubuntu/AI-code/Doris-test/credentials.env}"
diff --git a/doris/permission_matrix.py b/doris/permission_matrix.py
index 1c5b3b5..11f9cee 100644
--- a/doris/permission_matrix.py
+++ b/doris/permission_matrix.py
@@ -51,6 +51,7 @@ EXPECTED_GRANTS: dict[str, dict[str, set[str]]] = {
 }
 EXPECTED_DATABASES = frozenset({"ecom", "system_mcp", "information_schema", "mysql"})
 DENIED_ERRNOS = frozenset({1044, 1142, 1143, 1227})
+DENIED_1105 = ("access denied", "command denied")  # Doris 4.1 refuses privileges with errno 1105 (T2.3)
 _WORKSPACE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")  # upstream workspace/create rule
 _STORE_LOGGER = "doris_new_mcp.store"
 
@@ -98,7 +99,7 @@ def parse_grants(row: Mapping[str, Any]) -> dict[str, dict[str, set[str]]]:
         scopes: dict[str, set[str]] = {}
         for entry in str(value).split(";"):
             obj, sep, privs = entry.strip().rpartition(": ")
-            scopes[obj if sep else "*"] = {p.strip() for p in privs.split(",") if p.strip()}
+            scopes.setdefault(obj if sep else "*", set()).update(p.strip() for p in privs.split(",") if p.strip())
         parsed[column] = scopes
     return parsed
 
@@ -121,15 +122,16 @@ def classify_error(error: pymysql.MySQLError) -> str:
     """'denied' for a privilege error, 'error' for anything else."""
     errno = error.args[0] if error.args else None
     message = str(error.args[1]) if len(error.args) > 1 else ""
-    if errno in DENIED_ERRNOS or (errno == 1105 and "denied" in message.lower()):
+    if errno in DENIED_ERRNOS or (errno == 1105 and any(d in message.lower() for d in DENIED_1105)):
         return "denied"
     return "error"
 
 
-def _brief(error: pymysql.MySQLError) -> str:
+def _brief(error: pymysql.MySQLError, secrets: Iterable[str]) -> str:
+    """errno + message, masked before it is cut (a cut secret no longer matches the mask)."""
     errno = error.args[0] if error.args else "?"
     message = str(error.args[1]) if len(error.args) > 1 else str(error)
-    return f"{errno} {message.replace('errCode = 2, detailMessage = ', '')[:160]}"
+    return f"{errno} {_mask(message.replace('errCode = 2, detailMessage = ', ''), secrets)[:160]}"
 
 
 def _rows(cur: Any, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
@@ -154,13 +156,13 @@ def check_databases(cur: Any) -> Result:
     return Result(not problems, "databases", "; ".join(problems) or ", ".join(sorted(seen)))
 
 
-def check_select(cur: Any, tables: Sequence[str]) -> Result:
+def check_select(cur: Any, tables: Sequence[str], secrets: Iterable[str]) -> Result:
     failed = []
     for table in tables:
         try:
             _rows(cur, f"SELECT 1 FROM {table} LIMIT 1")
         except pymysql.MySQLError as e:
-            failed.append(f"{table}: {_brief(e)}")
+            failed.append(f"{table}: {_brief(e, secrets)}")
     return Result(not failed, "select", "; ".join(failed) or f"{len(tables)} physical tables of the models")
 
 
@@ -177,22 +179,22 @@ def check_semantic_store(cur: Any, workspace: str) -> Result:
                   f"workspace {workspace} semantic_version={rows[0]['semantic_version']}, {files} active files")
 
 
-def max_user_connections(cur: Any) -> str:
+def max_user_connections(cur: Any, secrets: Iterable[str]) -> str:
     try:
         props = {r["Key"]: r["Value"] for r in _rows(cur, "SHOW PROPERTY")}
     except pymysql.MySQLError as e:
-        return f"unavailable ({_brief(e)})"
+        return f"unavailable ({_brief(e, secrets)})"
     return props.get("max_user_connections", "?")
 
 
-def run_probe(cur: Any, probe: Probe) -> Result:
+def run_probe(cur: Any, probe: Probe, secrets: Iterable[str]) -> Result:
     name = f"probe {probe.name}"
     try:
         _rows(cur, probe.sql)
     except pymysql.MySQLError as e:
         if classify_error(e) == "denied":
-            return Result(True, name, f"denied ({_brief(e)})")
-        return Result(False, name, f"inconclusive, expected denied: {_brief(e)}")
+            return Result(True, name, f"denied ({_brief(e, secrets)})")
+        return Result(False, name, f"inconclusive, expected denied: {_brief(e, secrets)}")
     return Result(False, name, "ALLOWED, expected denied")
 
 
@@ -274,15 +276,16 @@ def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
             emit(f"connected as {identity}")
             checks: list[tuple[str, Callable[[Any], Result]]] = [
                 ("grants", check_grants), ("databases", check_databases),
-                ("select", lambda c: check_select(c, tables)),
+                ("select", lambda c: check_select(c, tables, secrets)),
                 ("semantic store", lambda c: check_semantic_store(c, args.workspace))]
             for name, check in checks:
                 try:
                     results.append(check(cur))
                 except pymysql.MySQLError as e:
-                    results.append(Result(False, name, _brief(e)))
+                    results.append(Result(False, name, _brief(e, secrets)))
                 emit(_line(results[-1]))
-            emit(f"info  max_user_connections={max_user_connections(cur)}")
+            emit(f"info  max_user_connections={max_user_connections(cur, secrets)}")
+            failed = sum(not r.ok for r in results)
 
             probes = write_probes(identity)
             if env.get("APPLY") != "1":
@@ -291,19 +294,26 @@ def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
                      "CREATE DATABASE/TABLE IF NOT EXISTS + metadata SELECT")
                 for probe in probes:
                     emit(f"  {probe.name:<18} expect denied  {probe.sql}   -- {probe.why}")
+            elif failed:
+                # The probes are no-ops only for the account the read-only checks describe.
+                emit(f"SKIPPED probes: {failed} read-only check(s) failed; "
+                     "store_init and the write probes did not run")
             else:
                 try:
                     ok, detail = store_init(settings, args.workspace)
                 except pymysql.MySQLError as e:
-                    ok, detail = False, _brief(e)
+                    ok, detail = False, _brief(e, secrets)
                 results.append(Result(ok, "probe store_init", detail))
                 emit(_line(results[-1]))
                 for probe in probes:
-                    results.append(run_probe(cur, probe))
+                    results.append(run_probe(cur, probe, secrets))
                     emit(_line(results[-1]))
     except pymysql.MySQLError as e:
-        emit(f"FAILED: {_brief(e)}", err)
+        emit(f"FAILED: {_brief(e, secrets)}", err)
         return 1
+    except Exception as e:  # noqa: BLE001 - one masked line instead of a traceback that may name the host
+        emit(f"FAILED: {type(e).__name__}: {e}", err)
+        return 2
     finally:
         conn.close()
     passed = sum(r.ok for r in results)
diff --git a/doris/publish-semantic.sh b/doris/publish-semantic.sh
index e14680f..fe7c9c1 100644
--- a/doris/publish-semantic.sh
+++ b/doris/publish-semantic.sh
@@ -5,6 +5,8 @@
 # credentials.env is sourced in a subshell; only host/port, the admin user and (APPLY=1 only) the admin
 # password are exported, under new names, to the python process.
 set -euo pipefail
+# `source` keeps the export attribute of variables the caller already exported: drop them first.
+unset "${!DORIS_ROOT_@}" "${!DORIS_RO_@}" DORIS_ADMIN_PASSWORD
 ROOT="$(cd "$(dirname "$0")/.." && pwd)"
 CRED="${DORIS_CRED_FILE:-/home/ubuntu/AI-code/Doris-test/credentials.env}"
 PY="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
diff --git a/doris/reconcile.py b/doris/reconcile.py
index efb4c58..199b09d 100644
--- a/doris/reconcile.py
+++ b/doris/reconcile.py
@@ -264,19 +264,20 @@ def local_metric_names(models_dir: Path | str) -> set[str]:
 class McpBackend:
     """Call the semantic tools the way an agent does, through a fastmcp Client."""
 
-    def __init__(self, client: Any, workspace: str):
-        self.client, self.workspace = client, workspace
+    def __init__(self, client: Any, workspace: str, secrets: Iterable[str] = ()):
+        self.client, self.workspace, self.secrets = client, workspace, list(secrets)
 
     async def _call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
         result = await self.client.call_tool(tool, args, raise_on_error=False)
         text = "".join(getattr(c, "text", "") for c in result.content)
+        # Mask before cutting: a cut secret no longer matches the mask applied when it is printed.
         try:
             body = json.loads(text)
         except ValueError:
-            raise ReconcileError(f"{tool}: non-JSON result: {text[:300]}") from None
+            raise ReconcileError(f"{tool}: non-JSON result: {_mask(text, self.secrets)[:300]}") from None
         if not isinstance(body, dict) or body.get("success") is not True:
             error = body.get("error", body) if isinstance(body, dict) else body
-            raise ReconcileError(f"{tool}: {json.dumps(error, ensure_ascii=False)[:500]}")
+            raise ReconcileError(f"{tool}: {_mask(json.dumps(error, ensure_ascii=False), self.secrets)[:500]}")
         return body
 
     async def metric_names(self) -> set[str]:
@@ -333,7 +334,7 @@ async def _run_mcp(client: Any, models_dir: Path, workspace: str, cases: Sequenc
     expected = local_metric_names(models_dir)
     failed = 0
     async with client:
-        backend = McpBackend(client, workspace)
+        backend = McpBackend(client, workspace, secrets)
         published = await backend.metric_names()
         if published == expected:
             print(f"published metrics: {len(published)} match {models_dir}", file=out)
diff --git a/mcp-server/src/agentcore_ext/settings.py b/mcp-server/src/agentcore_ext/settings.py
index 81e40b5..73afb15 100644
--- a/mcp-server/src/agentcore_ext/settings.py
+++ b/mcp-server/src/agentcore_ext/settings.py
@@ -82,7 +82,12 @@ def load_settings(env: Mapping[str, str] | None = None, secrets_client: Any = No
 
     secret_id = (env.get("DORIS_SECRET_ID") or "").strip()
     if secret_id:
-        user, password = _credentials_from_secret(secret_id, secrets_client or _secrets_client(env))
+        if secrets_client is None:
+            try:
+                secrets_client = _secrets_client(env)
+            except Exception as e:  # noqa: BLE001 - e.g. NoRegionError; only the type, like a read failure
+                raise SettingsError(f"cannot read secret {secret_id}: {type(e).__name__}") from None
+        user, password = _credentials_from_secret(secret_id, secrets_client)
     else:
         user, password = env.get("DORIS_USER") or "", env.get("DORIS_PASSWORD")
         if not user or password is None:
diff --git a/scripts/check-secrets.sh b/scripts/check-secrets.sh
index b815baa..40ed0c2 100644
--- a/scripts/check-secrets.sh
+++ b/scripts/check-secrets.sh
@@ -40,7 +40,9 @@ for sid in ${SM_SECRETS:-doris-mcp/mcp_svc doris-mcp/cognito-demo-user}; do
   if ! pw="$(aws secretsmanager get-secret-value --region "${SM_REGION:-us-east-1}" --secret-id "$sid" \
                --query SecretString --output text 2>/dev/null |
              python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])' 2>/dev/null)" || [[ ${#pw} -lt 4 ]]; then
-    echo "WARN: cannot read secret $sid — skipped its exact-value check"
+    # A check that could not run is not a pass: fix the AWS credentials, then re-run.
+    echo "FAIL: cannot read secret $sid — its exact-value check did not run"
+    fail=1
     continue
   fi
   while IFS= read -r f; do
PATCH
```

- [ ] **Step 5：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 125 tests / OK
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 期望：Ran 83 tests / OK
for t in doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh scripts/test/test-check-secrets.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 期望：每行 all passed
bash scripts/check-secrets.sh | tail -1                                                              # 期望：check-secrets: OK (… files scanned)
git status --short
```
期望：`git status` 恰好列出上面 12 个 ` M` 文件（6 个测试 + 6 个实现）。check-secrets 是 OK，说明本机能读到两个 secret；如果这里是 `FAIL: cannot read secret …`，先修 AWS 凭证，不要跳过。

```bash
bash scripts/check-secrets.sh
git add doris/apply-admin-sql.sh doris/publish-semantic.sh doris/permission_matrix.py doris/reconcile.py \
        mcp-server/src/agentcore_ext/settings.py scripts/check-secrets.sh \
        doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh doris/test/test_permission_matrix.py \
        doris/test/test_reconcile.py mcp-server/test/test_agentcore_settings.py scripts/test/test-check-secrets.sh
git commit -m "fix(p3): T3.0 P2 review M1-M4

M1 wrappers unset caller-exported root / demo_ro variables; M2 permission matrix skips the probes
after a failed read-only check, 1105 needs access/command denied, mask before cut, merged grants,
masked catch-all; M3 secrets client setup errors are SettingsError; M4 an unreadable secret fails
check-secrets.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6：写 P-09 的失败测试**

新建 `mcp-server/test/test_agentcore_session_timeout.py`：

```python
"""P-09: [query] session_wait_timeout_seconds -> SET wait_timeout on every pool connection.

Each Gateway call runs in a fresh Runtime microVM; pool connections left open when a microVM is torn
down stay on Doris until its wait_timeout (default 28800 s) unless the session sets a shorter one.
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config.loader import AppConfig  # noqa: E402
from core.connection import ConnectionPool  # noqa: E402

_SHIPPED_CONFIG = Path(__file__).resolve().parent.parent / "config"


def _config(toml: str) -> AppConfig:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "mcp-server.toml").write_text(toml, encoding="utf-8")
        return AppConfig(tmp)


class TestSessionWaitTimeoutConfig(unittest.TestCase):
    def test_default_is_none(self):
        self.assertIsNone(_config("[query]\n").cluster.session_wait_timeout)

    def test_explicit_value(self):
        cfg = _config("[query]\nsession_wait_timeout_seconds = 600\n")
        self.assertEqual(cfg.cluster.session_wait_timeout, 600)

    def test_string_value_is_coerced_to_int(self):
        cfg = _config('[query]\nsession_wait_timeout_seconds = "900"\n')
        self.assertEqual(cfg.cluster.session_wait_timeout, 900)

    def test_shipped_config_outlives_the_pool_recycle(self):
        # A pooled connection idle for pool_idle_timeout_seconds is recycled by aiomysql; Doris must not
        # drop it first, or the next query on it fails.
        cluster = AppConfig(_SHIPPED_CONFIG).cluster
        self.assertEqual(cluster.session_wait_timeout, 600)
        self.assertGreater(cluster.session_wait_timeout, cluster.pool_idle_timeout)


class TestPoolInitCommand(unittest.TestCase):
    def _create_pool_kwargs(self, toml: str) -> dict:
        pool = ConnectionPool(_config(toml).cluster, "mcp_svc", "pw", host="10.0.0.5")
        create = mock.AsyncMock(return_value=SimpleNamespace(closed=False))
        with mock.patch("core.connection.aiomysql.create_pool", create):
            asyncio.run(pool._ensure_pool())
        create.assert_awaited_once()
        return create.await_args.kwargs

    def test_pool_sets_the_session_wait_timeout(self):
        kwargs = self._create_pool_kwargs("[query]\nsession_wait_timeout_seconds = 600\n")
        self.assertEqual(kwargs["init_command"], "SET wait_timeout = 600")
        self.assertTrue(kwargs["autocommit"])

    def test_no_init_command_without_the_setting(self):
        kwargs = self._create_pool_kwargs("[query]\n")
        self.assertNotIn("init_command", kwargs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 7：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | grep -E '^(FAIL|ERROR):|^Ran|^FAILED|^OK' | sed -E '/^(FAIL|ERROR):/s/ \(.*//'
```
期望：
```
ERROR: test_pool_sets_the_session_wait_timeout
ERROR: test_default_is_none
ERROR: test_explicit_value
ERROR: test_shipped_config_outlives_the_pool_recycle
ERROR: test_string_value_is_coerced_to_int
Ran 89 tests in …s
FAILED (errors=5)
```
4 个配置测试是 `AttributeError: 'ClusterConfig' object has no attribute 'session_wait_timeout'`，`test_pool_sets_the_session_wait_timeout` 是 `KeyError: 'init_command'`。第 6 个测试 `test_no_init_command_without_the_setting` 现在就能通过（upstream 本来就不传 `init_command`），它守的是「不设置时行为和 upstream 一样」。

- [ ] **Step 8：实现 P-09**

`ClusterConfig` 读 `session_wait_timeout_seconds`；`ConnectionPool` 在设置了它时传 `init_command`；仓库配置设为 600；`UPSTREAM.md` 加 P-09 一行，并把它列进「会改 upstream 文件的补丁」和升级步骤：

```bash
git apply <<'PATCH'
diff --git a/mcp-server/UPSTREAM.md b/mcp-server/UPSTREAM.md
index daaeff2..7e79d25 100644
--- a/mcp-server/UPSTREAM.md
+++ b/mcp-server/UPSTREAM.md
@@ -18,11 +18,13 @@
 | P-06 | `config/mcp-server.toml` (new) | runtime limits (50 s SQL timeout, pool 5, 2000 rows) |
 | P-07 | `pyproject.toml` (new) | dependencies pinned to upstream `uv.lock` + boto3, for AgentCore CodeZip |
 | P-08 | `test/test_agentcore_*.py` (new) | tests for P-01..P-06 |
+| P-09 | `src/config/loader.py`, `src/core/connection.py`, `config/mcp-server.toml`, `test/test_agentcore_session_timeout.py` (new) | `SET wait_timeout` on every pool connection (`session_wait_timeout_seconds = 600`), so Doris reaps what a torn-down Runtime microVM left open |
 
-Only P-02, P-03 and P-04 touch upstream files; without service credentials they behave exactly like upstream.
+Only P-02, P-03, P-04 and P-09 touch upstream files; without service credentials and without
+`session_wait_timeout_seconds` they behave exactly like upstream.
 
 ## Upgrading upstream
 
 1. `git archive <new-commit> src test LICENSE.txt NOTICE mcp-server.toml requirements.txt` into a scratch dir and diff it against the vendored commit.
-2. Replace the vendored files, then re-apply P-02/P-03/P-04 (`git log --oneline -- mcp-server/src` lists their commits).
+2. Replace the vendored files, then re-apply P-02/P-03/P-04/P-09 (`git log --oneline -- mcp-server/src` lists their commits).
 3. Update the pins in `pyproject.toml` from the new `uv.lock`, then run the upstream offline suite and `test_agentcore_*.py`.
diff --git a/mcp-server/config/mcp-server.toml b/mcp-server/config/mcp-server.toml
index 16f25c7..f219d1c 100644
--- a/mcp-server/config/mcp-server.toml
+++ b/mcp-server/config/mcp-server.toml
@@ -16,6 +16,9 @@ rotation_backup_count = 3
 pool_min_size = 0
 pool_max_size = 5                 # one service account; Quick desktop runs <= 20 tools in parallel
 pool_idle_timeout_seconds = 300
+# SET wait_timeout on every pool connection: Doris reaps the connections a torn-down Runtime
+# microVM left open after 10 min. Must exceed pool_idle_timeout_seconds.
+session_wait_timeout_seconds = 600
 query_timeout_seconds = 50        # Quick fails any MCP call after 60 s (HTTP 424)
 query_max_rows = 2000             # keep results small enough for the agent's context
 db_whitelist = []
diff --git a/mcp-server/src/config/loader.py b/mcp-server/src/config/loader.py
index b25ea7e..540cdbe 100644
--- a/mcp-server/src/config/loader.py
+++ b/mcp-server/src/config/loader.py
@@ -65,6 +65,9 @@ class ClusterConfig:
         self.query_timeout: int = query.get("query_timeout_seconds", 600)
         self.max_rows: int = query.get("query_max_rows", 10000)
         self.db_whitelist: list[str] = query.get("db_whitelist", []) or []
+        # Session wait_timeout set on every pool connection (None: keep the Doris default).
+        raw = query.get("session_wait_timeout_seconds")
+        self.session_wait_timeout: int | None = int(raw) if raw is not None else None
 
 
 class AppConfig:
diff --git a/mcp-server/src/core/connection.py b/mcp-server/src/core/connection.py
index a4e4a7b..4ed06df 100644
--- a/mcp-server/src/core/connection.py
+++ b/mcp-server/src/core/connection.py
@@ -40,6 +40,11 @@ class ConnectionPool:
         async with self._lock:
             if self._pool is not None and not self._pool.closed:
                 return self._pool
+            extra: dict[str, Any] = {}
+            if self._cluster.session_wait_timeout is not None:
+                # A pool left open by a torn-down Runtime microVM is never closed
+                # by the client; Doris reaps its connections after this timeout.
+                extra["init_command"] = f"SET wait_timeout = {int(self._cluster.session_wait_timeout)}"
             self._pool = await aiomysql.create_pool(
                 host=self._host,
                 port=self._cluster.fe_mysql_port,
@@ -52,6 +57,7 @@ class ConnectionPool:
                 # Recycle connections idle longer than this so a connection
                 # silently dropped by Doris wait_timeout is never reused.
                 pool_recycle=self._cluster.pool_idle_timeout,
+                **extra,
             )
             return self._pool
 
PATCH
```

- [ ] **Step 9：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 期望：Ran 89 tests / OK
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3     # 期望：🎉 All tests passed!
```
期望：两条都通过。upstream 离线测试覆盖 `ConnectionPool` 的其他用法，确认 P-09 没有改变不设置时的行为。

- [ ] **Step 10：收尾**

勾选 T3.0；progress「当前状态」写 T3.0 完成、下一步 T3.1；日志记录 Step 3、Step 7 的失败数和 Step 5、Step 9 的测试数。

```bash
bash scripts/check-secrets.sh
git add mcp-server/config/mcp-server.toml mcp-server/src/config/loader.py mcp-server/src/core/connection.py \
        mcp-server/UPSTREAM.md mcp-server/test/test_agentcore_session_timeout.py \
        specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "feat(mcp): T3.0 P-09 SET wait_timeout = 600 on every pool connection

Each Gateway call runs in a fresh Runtime microVM; Doris now reaps the connections a torn-down
microVM left open after 10 min instead of 8 h (mcp_svc max_user_connections = 100).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T3.1：Runtime 专用执行角色 `doris-mcp-runtime-role`

来源：tasks.md T3.1、design §7（CDK 默认角色的权限）、P2 整体评审遗留「Runtime 角色的 `secretsmanager:GetSecretValue` 限定到 `DORIS_SECRET_ARN`」。agentcore CLI 0.30.0 的 CDK 构造在 `agentcore.json` 有 `executionRoleArn` 时导入这个角色（`Role.fromRoleArn(…, { mutable: false })`），不再生成角色，也不附加任何策略；所以角色的内联策略就是 Runtime 能做的全部事情。不用 `additionalPolicies`：它只能在 CDK 角色上**追加**权限，去不掉任意 Bedrock 模型和 X-Ray。

**Files:**
- Create：`infra/35-runtime-role.sh`、`infra/policies/runtime-trust.json`、`infra/policies/runtime-exec.json`、`infra/test/test-35-runtime-role.sh`（30 项检查）、`scripts/test/test_render_agentcore.py`（9 个测试，`scripts/test` 从这里开始有 unittest）
- Modify：`scripts/render-agentcore.py`（`--phase server` 写 `executionRoleArn`）、`infra/state.env`（APPLY=1 时由脚本写入 `RT_ROLE_ARN`）、`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：P0 的 `infra/lib.sh`：`log`、`run`（dry-run 时只打印，返回空）、`render FILE`（用 `os.path.expandvars` 替换 export 过的变量）、`placeholder NAME` / `is_placeholder V`、`none_to_empty`、`state_set KEY VALUE`（只在 APPLY=1 时写）、`_PRIVATE_TMPS`（EXIT 时删除）、`$APPLY`、`$PROJECT_TAG`、`$ACCOUNT_ID`、`AWS_REGION`；T2.1 的 `DORIS_SECRET_ARN`（`state.env`）
- Produces：
  - IAM 角色 `doris-mcp-runtime-role`（tag `Project=doris-mcp-demo`）：
    - 信任策略只允许 `bedrock-agentcore.amazonaws.com`，条件 `aws:SourceAccount` = 本账号、`aws:SourceArn` 匹配 `arn:aws:bedrock-agentcore:us-east-1:<账号>:*`；
    - 内联策略 `doris-mcp-runtime` 有 4 条 Sid：`RuntimeLogGroup`、`RuntimeLogStreams`（只限 `runtimes/dorismcp_dorismcp-*`）、`DescribeLogGroups`、`ReadDorisServiceSecret`（`secretsmanager:GetSecretValue`，Resource 就是 `DORIS_SECRET_ARN` 这一个 ARN）。
  - `infra/state.env` 的 `RT_ROLE_ARN=arn:aws:iam::890717383483:role/doris-mcp-runtime-role`（名字不用 `RUNTIME_ROLE_ARN`：那个键由 `infra/25-runtime-state.sh` 从 Runtime 读回，T3.2 deploy 后两者相等）。
  - `scripts/render-agentcore.py`：`main(argv=None)`；`--phase server` 要求 `RT_ROLE_ARN` 恰好等于 `arn:aws:iam::{ACCOUNT_ID}:role/doris-mcp-runtime-role`，否则 `sys.exit` 并说明要先跑 `infra/35-runtime-role.sh`；写入 `executionRoleArn`。`--phase spike` 不变（仍用 CLI 角色）。T3.2 用它生成 `agentcore.json`。
  - APPLY=1 时脚本拒绝不是本账号、本区域 `doris-mcp/mcp_svc-*` 的 `DORIS_SECRET_ARN`（包括通配符）；`get-role` 除 `NoSuchEntity` 以外的失败（权限不足、会话过期）直接退出，不会误建角色。

- [ ] **Step 1：确认分支和工作区**

```bash
git branch --show-current && git status --short
```
期望：只输出 `p3-deploy`（T3.0 已提交，工作区干净）。

- [ ] **Step 2：写失败测试**

`infra/test/test-35-runtime-role.sh` 用假的 `aws` 和 `sleep` 记录每次调用，覆盖 dry-run、APPLY=1 时角色不存在 / 已存在 / `get-role` 被拒绝，以及 secret ARN 缺失、带通配符、属于别的账号：

新建 `infra/test/test-35-runtime-role.sh`：

```bash
#!/usr/bin/env bash
# Offline tests for infra/35-runtime-role.sh. Fake `aws` and `sleep` on PATH record every call; no AWS access.
#   bash infra/test/test-35-runtime-role.sh
set -uo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
SECRET_ARN="arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-AbCdEf"
ROLE_ARN="arn:aws:iam::111122223333:role/doris-mcp-runtime-role"
mkdir -p "$TMP/bin"
# Fake AWS CLI. FAKE_ROLE = missing | exists | denied. file:// documents are copied to $FAKE_DIR.
cat > "$TMP/bin/aws" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
doc() { for a in "$@"; do [[ "$a" == file://* ]] && cat "${a#file://}"; done; }
case "$1 $2" in
  "iam get-role")
    case "$FAKE_ROLE" in
      exists) echo "arn:aws:iam::111122223333:role/doris-mcp-runtime-role" ;;
      denied) echo "An error occurred (AccessDenied) when calling the GetRole operation" >&2; exit 254 ;;
      *)      echo "An error occurred (NoSuchEntity) when calling the GetRole operation: The role with name doris-mcp-runtime-role cannot be found." >&2; exit 254 ;;
    esac ;;
  "iam create-role") doc "$@" > "$FAKE_DIR/trust.json"; echo "arn:aws:iam::111122223333:role/doris-mcp-runtime-role" ;;
  "iam put-role-policy") doc "$@" > "$FAKE_DIR/policy.json" ;;
  *) echo "fake aws: unexpected call: $*" >&2; exit 99 ;;
esac
FAKE
printf '#!/usr/bin/env bash\nprintf "sleep %%s\\n" "$*" >> "$FAKE_LOG"\n' > "$TMP/bin/sleep"
chmod +x "$TMP/bin/aws" "$TMP/bin/sleep"

FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
# run_script FAKE_ROLE APPLY [SECRET_ARN] — runs the script against a fresh state.env; sets RC, OUT, LOG.
run_script() {
  : > "$TMP/aws.log"; rm -f "$TMP/trust.json" "$TMP/policy.json"
  printf '%s\n' '# test state' 'AWS_REGION=us-east-1' 'ACCOUNT_ID=111122223333' > "$TMP/state.env"
  [[ -n "${3-}" ]] && printf 'DORIS_SECRET_ARN=%s\n' "$3" >> "$TMP/state.env"
  OUT="$(PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" FAKE_DIR="$TMP" FAKE_ROLE="$1" \
    APPLY="$2" STATE_FILE="$TMP/state.env" bash "$INFRA_DIR/35-runtime-role.sh" 2>&1)"
  RC=$?
  LOG="$(cat "$TMP/aws.log")"
}
has() { [[ "$1" == *"$2"* ]] && echo yes || echo no; }
# trust_problems FILE / policy_problems FILE — "none" or the list of problems with the document.
trust_problems() {
  python3 - "$1" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
problems = []
if "${" in json.dumps(doc):
    problems.append("unrendered ${...}")
[st] = doc["Statement"]
if st.get("Principal") != {"Service": "bedrock-agentcore.amazonaws.com"}:
    problems.append(f"principal {st.get('Principal')}")
if st.get("Action") != "sts:AssumeRole":
    problems.append(f"action {st.get('Action')}")
cond = st.get("Condition", {})
if cond.get("StringEquals") != {"aws:SourceAccount": "111122223333"}:
    problems.append(f"SourceAccount {cond.get('StringEquals')}")
if cond.get("ArnLike") != {"aws:SourceArn": "arn:aws:bedrock-agentcore:us-east-1:111122223333:*"}:
    problems.append(f"SourceArn {cond.get('ArnLike')}")
print("; ".join(problems) or "none")
PY
}
policy_problems() {
  python3 - "$1" "$SECRET_ARN" <<'PY'
import json, sys
doc, secret = json.load(open(sys.argv[1])), sys.argv[2]
allowed = {"logs:CreateLogGroup", "logs:DescribeLogStreams", "logs:PutResourcePolicy", "logs:CreateLogStream",
           "logs:PutLogEvents", "logs:DescribeLogGroups", "secretsmanager:GetSecretValue"}
problems = []
if "${" in json.dumps(doc):
    problems.append("unrendered ${...}")
for st in doc["Statement"]:
    actions = [st["Action"]] if isinstance(st["Action"], str) else st["Action"]
    resources = [st["Resource"]] if isinstance(st["Resource"], str) else st["Resource"]
    if st.get("Effect") != "Allow" or "NotAction" in st or "NotResource" in st:
        problems.append(f"{st.get('Sid')}: not a plain Allow")
    if set(actions) - allowed:
        problems.append(f"{st.get('Sid')}: unexpected actions {sorted(set(actions) - allowed)}")
    if "*" in resources:
        problems.append(f"{st.get('Sid')}: Resource *")
    if "secretsmanager:GetSecretValue" in actions and resources != [secret]:
        problems.append(f"GetSecretValue on {resources}")
    for r in resources:
        if r.startswith("arn:aws:logs:") and not r.startswith("arn:aws:logs:us-east-1:111122223333:log-group:"):
            problems.append(f"log resource outside this account/region: {r}")
        if r.startswith("arn:aws:logs:") and set(actions) != {"logs:DescribeLogGroups"} \
                and "/aws/bedrock-agentcore/runtimes/dorismcp_dorismcp-" not in r:
            problems.append(f"log write outside runtime dorismcp_dorismcp: {r}")
print("; ".join(problems) or "none")
PY
}

run_script missing 0 "$SECRET_ARN"
check "dry-run: exit 0" 0 "$RC"
check "dry-run: shows create-role" yes "$(has "$OUT" "DRY-RUN: aws iam create-role --role-name doris-mcp-runtime-role")"
check "dry-run: shows put-role-policy" yes "$(has "$OUT" "DRY-RUN: aws iam put-role-policy --role-name doris-mcp-runtime-role --policy-name doris-mcp-runtime")"
check "dry-run: prints the rendered policy with the secret ARN" yes "$(has "$OUT" "\"Resource\": \"$SECRET_ARN\"")"
check "dry-run: never creates the role" no "$(has "$LOG" "create-role")"
check "dry-run: never puts the policy" no "$(has "$LOG" "put-role-policy")"
check "dry-run: state.env unchanged" no "$(has "$(cat "$TMP/state.env")" "RT_ROLE_ARN")"

run_script missing 0
check "dry-run/no secret: exit 0 with a placeholder" yes "$([[ "$RC" == 0 ]] && has "$OUT" "<new:doris-secret-arn>")"

run_script missing 1
check "apply/no secret ARN: fails" 1 "$RC"
check "apply/no secret ARN: says to finish T2.1" yes "$(has "$OUT" "DORIS_SECRET_ARN")"
check "apply/no secret ARN: no create-role" no "$(has "$LOG" "create-role")"

run_script missing 1 "*"
check "apply/wildcard secret ARN: fails" 1 "$RC"
check "apply/wildcard secret ARN: no IAM write" 0 "$(grep -cE 'create-role|put-role-policy' <<<"$LOG")"
run_script missing 1 "arn:aws:secretsmanager:us-east-1:999999999999:secret:doris-mcp/mcp_svc-AbCdEf"
check "apply/other-account secret ARN: fails" 1 "$RC"

run_script missing 1 "$SECRET_ARN"
check "apply/missing: exit 0" 0 "$RC"
check "apply/missing: create-role called once" 1 "$(grep -c 'iam create-role' <<<"$LOG")"
check "apply/missing: tagged with Project" yes "$(has "$LOG" "Key=Project,Value=doris-mcp-demo")"
check "apply/missing: put-role-policy doris-mcp-runtime once" 1 "$(grep -c 'put-role-policy --role-name doris-mcp-runtime-role --policy-name doris-mcp-runtime ' <<<"$LOG")"
check "apply/missing: trust policy (bedrock-agentcore, this account, this region)" none "$(trust_problems "$TMP/trust.json")"
check "apply/missing: permission policy (logs of dorismcp_dorismcp + one secret)" none "$(policy_problems "$TMP/policy.json")"
check "apply/missing: waits 15s for IAM propagation" yes "$(has "$LOG" "sleep 15")"
check "apply/missing: RT_ROLE_ARN recorded" "RT_ROLE_ARN=$ROLE_ARN" "$(grep '^RT_ROLE_ARN=' "$TMP/state.env")"

run_script exists 1 "$SECRET_ARN"
check "apply/exists: exit 0" 0 "$RC"
check "apply/exists: no create-role" no "$(has "$LOG" "create-role")"
check "apply/exists: policy re-applied" 1 "$(grep -c 'put-role-policy' <<<"$LOG")"
check "apply/exists: permission policy" none "$(policy_problems "$TMP/policy.json")"
check "apply/exists: no propagation wait" no "$(has "$LOG" "sleep")"
check "apply/exists: RT_ROLE_ARN recorded" "RT_ROLE_ARN=$ROLE_ARN" "$(grep '^RT_ROLE_ARN=' "$TMP/state.env")"

run_script denied 1 "$SECRET_ARN"
check "apply/get-role denied: fails instead of creating" 1 "$RC"
check "apply/get-role denied: no IAM write" 0 "$(grep -cE 'create-role|put-role-policy' <<<"$LOG")"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
```

`scripts/test/test_render_agentcore.py` 在临时目录里放一份 `state.env` 和 `agentcore.json`，不碰仓库里的文件：

新建 `scripts/test/test_render_agentcore.py`：

```python
"""scripts/render-agentcore.py: the runtime entry written to dorismcp/agentcore/agentcore.json (P3 / T3.1).

    .venv/bin/python -m unittest discover -s scripts/test -p 'test_*.py' -v
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SCRIPT = Path(__file__).resolve().parents[1] / "render-agentcore.py"
_spec = importlib.util.spec_from_file_location("render_agentcore", _SCRIPT)
render = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render)

ROLE = "arn:aws:iam::111122223333:role/doris-mcp-runtime-role"
CDK_ROLE = "arn:aws:iam::111122223333:role/AgentCore-dorismcp-defaul-ApplicationAgentDorismcpR-30Mcwi4tCmaV"
STATE = {
    "ACCOUNT_ID": "111122223333", "AWS_REGION": "us-east-1", "DORIS_PRIVATE_IP": "10.9.8.7",
    "SUBNET_AZ4": "subnet-a", "SUBNET_AZ1": "subnet-b", "SUBNET_AZ2": "subnet-c", "RT_SG": "sg-rt",
    "RT_ROLE_ARN": ROLE,
}


def _env(entry: dict) -> dict:
    return {e["name"]: e["value"] for e in entry["envVars"]}


class TestServerEntry(unittest.TestCase):
    def test_uses_the_project_execution_role(self):
        self.assertEqual(render.runtime_entry("server", STATE)["executionRoleArn"], ROLE)

    def test_requires_the_project_role(self):
        state = {k: v for k, v in STATE.items() if k != "RT_ROLE_ARN"}
        with self.assertRaises(SystemExit) as cm:
            render.runtime_entry("server", state)
        self.assertIn("RT_ROLE_ARN", str(cm.exception))
        self.assertIn("infra/35-runtime-role.sh", str(cm.exception))

    def test_refuses_the_cdk_role(self):
        # The CLI's own role may invoke any Bedrock model (design §7); P3 replaces it.
        with self.assertRaises(SystemExit):
            render.runtime_entry("server", {**STATE, "RT_ROLE_ARN": CDK_ROLE})

    def test_refuses_a_role_of_another_account(self):
        with self.assertRaises(SystemExit):
            render.runtime_entry("server", {**STATE, "RT_ROLE_ARN": ROLE.replace("111122223333", "999999999999")})

    def test_reads_the_service_account_from_secrets_manager(self):
        entry = render.runtime_entry("server", STATE)
        self.assertEqual(_env(entry), {"DORIS_HOST": "10.9.8.7", "DORIS_PORT": "9030", "DORIS_HTTP_PORT": "8030",
                                       "DORIS_SECRET_ID": "doris-mcp/mcp_svc", "PROFILE_SCOPE": "all"})
        self.assertEqual(entry["codeLocation"], "../mcp-server/")

    def test_keeps_the_vpc_and_iam_inbound_auth(self):
        entry = render.runtime_entry("server", STATE)
        self.assertEqual(entry["networkConfig"], {"subnets": ["subnet-a", "subnet-b", "subnet-c"],
                                                  "securityGroups": ["sg-rt"]})
        self.assertEqual((entry["networkMode"], entry["authorizerType"], entry["protocol"]),
                         ("VPC", "AWS_IAM", "MCP"))


class TestSpikeEntry(unittest.TestCase):
    def test_spike_keeps_the_cli_role(self):
        # P0 history: the spike phase never set a role; RT_ROLE_ARN is not needed to re-render it.
        state = {k: v for k, v in STATE.items() if k != "RT_ROLE_ARN"}
        self.assertNotIn("executionRoleArn", render.runtime_entry("spike", state))


class TestMain(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.project = self.root / "dorismcp" / "agentcore"
        self.project.mkdir(parents=True)
        (self.root / "infra").mkdir()
        (self.root / "infra" / "state.env").write_text("# state\n" + "".join(f"{k}={v}\n" for k, v in STATE.items()))
        self.config = self.project / "agentcore.json"
        self.config.write_text(json.dumps({"name": "dorismcp", "runtimes": [
            {"name": "other", "build": "CodeZip"}, {"name": "dorismcp", "codeLocation": "../spike/p0-mcp/"}]}))
        for name, value in (("ROOT", self.root), ("PROJECT_DIR", self.project)):
            patcher = mock.patch.object(render, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _main(self, *argv: str) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            render.main(list(argv))
        return out.getvalue()

    def test_check_prints_without_writing(self):
        before = self.config.read_text()
        printed = json.loads(self._main("--phase", "server", "--check"))
        self.assertEqual(printed["executionRoleArn"], ROLE)
        self.assertEqual(self.config.read_text(), before)
        self.assertFalse((self.project / "aws-targets.json").exists())

    def test_write_replaces_only_the_dorismcp_runtime(self):
        self._main("--phase", "server")
        runtimes = json.loads(self.config.read_text())["runtimes"]
        self.assertEqual([r["name"] for r in runtimes], ["other", "dorismcp"])
        self.assertEqual(runtimes[1]["executionRoleArn"], ROLE)
        self.assertEqual(json.loads((self.project / "aws-targets.json").read_text()),
                         [{"name": "default", "account": "111122223333", "region": "us-east-1"}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 3：运行测试，确认失败**

```bash
bash infra/test/test-35-runtime-role.sh 2>&1 | grep -E '^FAIL|failed$' | tail -4
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | grep -E '^(FAIL|ERROR):|^Ran|^FAILED|^OK' | sed -E '/^(FAIL|ERROR):/s/ \(.*//'
```
期望：
```
FAIL apply/exists: permission policy: expected 'none', got ''
FAIL apply/exists: RT_ROLE_ARN recorded: expected 'RT_ROLE_ARN=arn:aws:iam::111122223333:role/doris-mcp-runtime-role', got ''
FAIL apply/get-role denied: fails instead of creating: expected '1', got '127'
22 failed
ERROR: test_check_prints_without_writing
ERROR: test_write_replaces_only_the_dorismcp_runtime
ERROR: test_uses_the_project_execution_role
FAIL: test_refuses_a_role_of_another_account
FAIL: test_refuses_the_cdk_role
FAIL: test_requires_the_project_role
Ran 9 tests in …s
FAILED (failures=3, errors=3)
```
- shell 测试的 22 个 FAIL 里，退出码都是 `got '127'`（脚本还不存在）。
- render 测试的 3 个 ERROR 是 `main()` 还不接受 `argv`（`TypeError`）或者还没有 `executionRoleArn`（`KeyError`）；3 个 FAIL 是现在的 `--phase server` 不检查角色，没有 `SystemExit`。其余 3 个测试（`test_reads_the_service_account_from_secrets_manager`、`test_keeps_the_vpc_and_iam_inbound_auth`、`test_spike_keeps_the_cli_role`）守的是现有行为，现在就能通过。

- [ ] **Step 4：写 `infra/35-runtime-role.sh` 和两个策略模板**

新建 `infra/35-runtime-role.sh`：

```bash
#!/usr/bin/env bash
# P3 / T3.1 — IAM execution role for AgentCore Runtime dorismcp, replacing the agentcore CLI's CDK role
# (which may invoke any Bedrock model and write X-Ray; design §7).
#   * trust: bedrock-agentcore, this account's resources in this region only
#   * inline policy doris-mcp-runtime: the runtime's own log groups + GetSecretValue on DORIS_SECRET_ARN
#     (the secret uses the AWS managed key, so no kms:Decrypt)
# agentcore.json references the role via executionRoleArn (scripts/render-agentcore.py --phase server);
# the CDK then imports it and adds no policies, so this policy is all the runtime can do.
# Dry-run by default. APPLY=1 to execute. Safe to re-run (re-applies the inline policy).
source "$(dirname "$0")/lib.sh"

ROLE_NAME=doris-mcp-runtime-role
POLICY_NAME=doris-mcp-runtime
RUNTIME_NAME=dorismcp_dorismcp # <agentcore project>_<runtime>; log groups are runtimes/<runtime-id>-<endpoint>

if [[ "$APPLY" == "1" ]]; then
  : "${DORIS_SECRET_ARN:?DORIS_SECRET_ARN missing in state.env - finish T2.1 first}"
  if [[ "$DORIS_SECRET_ARN" != "arn:aws:secretsmanager:$AWS_REGION:$ACCOUNT_ID:secret:doris-mcp/mcp_svc-"* ]]; then
    log "FATAL: DORIS_SECRET_ARN is not the doris-mcp/mcp_svc secret of this account/region"; exit 1
  fi
fi
DORIS_SECRET_ARN="${DORIS_SECRET_ARN:-$(placeholder doris-secret-arn)}"
export ACCOUNT_ID AWS_REGION RUNTIME_NAME DORIS_SECRET_ARN

render_tmp() { # FILE → path of a rendered copy in $RENDERED
  RENDERED="$(mktemp)"; _PRIVATE_TMPS+=("$RENDERED"); render "$1" > "$RENDERED"
  [[ "$APPLY" == "1" ]] || { log "rendered $(basename "$1"):"; cat "$RENDERED" >&2; }
}

# get-role: distinguish "not found" from every other failure, so a missing permission or an
# expired session never falls through to create-role.
RT_ROLE_ARN=""
if out="$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text 2>&1)"; then
  RT_ROLE_ARN="$(none_to_empty "$out")"
elif [[ "$out" != *NoSuchEntity* ]]; then
  log "FATAL: get-role $ROLE_NAME failed: $out"; exit 1
fi

role_is_new=0
if [[ -z "$RT_ROLE_ARN" ]]; then
  render_tmp "$INFRA_DIR/policies/runtime-trust.json"
  RT_ROLE_ARN="$(run aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document "file://$RENDERED" --tags "Key=Project,Value=$PROJECT_TAG" \
    --description "AgentCore Runtime dorismcp: own logs + the doris-mcp/mcp_svc secret" \
    --query Role.Arn --output text)"
  RT_ROLE_ARN="${RT_ROLE_ARN:-$(placeholder runtime-role-arn)}"
  role_is_new=1
else
  log "role exists: $RT_ROLE_ARN"
fi
render_tmp "$INFRA_DIR/policies/runtime-exec.json"
run aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" \
  --policy-document "file://$RENDERED"
[[ "$APPLY" == "1" && "$role_is_new" == "1" ]] && { log "waiting 15s for IAM propagation"; sleep 15; }
is_placeholder "$RT_ROLE_ARN" || state_set RT_ROLE_ARN "$RT_ROLE_ARN"
log "done (APPLY=$APPLY)"
```

新建 `infra/policies/runtime-trust.json`：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AgentCoreRuntimeAssume",
      "Effect": "Allow",
      "Principal": { "Service": "bedrock-agentcore.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "aws:SourceAccount": "${ACCOUNT_ID}" },
        "ArnLike": { "aws:SourceArn": "arn:aws:bedrock-agentcore:${AWS_REGION}:${ACCOUNT_ID}:*" }
      }
    }
  ]
}
```

新建 `infra/policies/runtime-exec.json`：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RuntimeLogGroup",
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:DescribeLogStreams", "logs:PutResourcePolicy"],
      "Resource": "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:/aws/bedrock-agentcore/runtimes/${RUNTIME_NAME}-*"
    },
    {
      "Sid": "RuntimeLogStreams",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:/aws/bedrock-agentcore/runtimes/${RUNTIME_NAME}-*:log-stream:*"
    },
    {
      "Sid": "DescribeLogGroups",
      "Effect": "Allow",
      "Action": "logs:DescribeLogGroups",
      "Resource": "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:*"
    },
    {
      "Sid": "ReadDorisServiceSecret",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "${DORIS_SECRET_ARN}"
    }
  ]
}
```

- [ ] **Step 5：`scripts/render-agentcore.py` 写 `executionRoleArn`**

```bash
git apply <<'PATCH'
diff --git a/scripts/render-agentcore.py b/scripts/render-agentcore.py
index 75b4d62..f17e6ca 100644
--- a/scripts/render-agentcore.py
+++ b/scripts/render-agentcore.py
@@ -2,7 +2,8 @@
 """Upsert runtime `dorismcp` in dorismcp/agentcore/agentcore.json and fill aws-targets.json.
 
   --phase spike   codeLocation ../spike/p0-mcp/  (P0 / T0.4)
-  --phase server  codeLocation ../mcp-server/    (P3 / T3.2: adds DORIS_SECRET_ID, PROFILE_SCOPE)
+  --phase server  codeLocation ../mcp-server/    (P3 / T3.2: adds DORIS_SECRET_ID, PROFILE_SCOPE and
+                  executionRoleArn = RT_ROLE_ARN, the role of infra/35-runtime-role.sh)
 
 Values come from infra/state.env. Only non-secret values are written; env var names that
 look like secrets are refused. codeLocation is relative to the project dir (dorismcp/).
@@ -19,6 +20,7 @@ PROJECT_DIR = ROOT / "dorismcp" / "agentcore"
 RUNTIME_NAME = "dorismcp"
 CODE_LOCATIONS = {"spike": "../spike/p0-mcp/", "server": "../mcp-server/"}
 SECRET_LIKE = re.compile(r"PASSWORD|TOKEN|SECRET_VALUE|ACCESS_KEY")
+EXECUTION_ROLE_NAME = "doris-mcp-runtime-role"
 
 
 def load_state(path: pathlib.Path) -> dict[str, str]:
@@ -37,6 +39,14 @@ def runtime_entry(phase: str, state: dict[str, str]) -> dict:
     bad = [k for k in env if SECRET_LIKE.search(k)]
     if bad:
         sys.exit(f"refusing secret-looking env vars: {bad}")
+    role = {}
+    if phase == "server":
+        # Without it the CLI's CDK creates a role that may invoke any Bedrock model (design §7).
+        want = f"arn:aws:iam::{state.get('ACCOUNT_ID', '')}:role/{EXECUTION_ROLE_NAME}"
+        if state.get("RT_ROLE_ARN") != want:
+            sys.exit(f"RT_ROLE_ARN in infra/state.env must be {want} (run infra/35-runtime-role.sh), "
+                     f"got {state.get('RT_ROLE_ARN') or 'nothing'}")
+        role = {"executionRoleArn": want}
     return {
         "name": RUNTIME_NAME,
         "build": "CodeZip",
@@ -52,14 +62,15 @@ def runtime_entry(phase: str, state: dict[str, str]) -> dict:
         "instrumentation": {"enableOtel": False},
         "protocol": "MCP",
         "authorizerType": "AWS_IAM",
+        **role,
     }
 
 
-def main() -> None:
+def main(argv: list[str] | None = None) -> None:
     parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
     parser.add_argument("--phase", choices=sorted(CODE_LOCATIONS), required=True)
     parser.add_argument("--check", action="store_true", help="print the entry, do not write")
-    args = parser.parse_args()
+    args = parser.parse_args(argv)
 
     state = load_state(ROOT / "infra" / "state.env")
     missing = [k for k in ("DORIS_PRIVATE_IP", "SUBNET_AZ4", "SUBNET_AZ1", "SUBNET_AZ2", "RT_SG") if not state.get(k)]
PATCH
```

- [ ] **Step 6：运行测试，确认通过**

```bash
bash infra/test/test-35-runtime-role.sh 2>&1 | grep -c '^ok'                             # 期望：30
bash infra/test/test-35-runtime-role.sh 2>&1 | tail -1                                   # 期望：all passed
bash infra/test/test-lib.sh 2>&1 | tail -1                                               # 期望：all passed
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                    # 期望：Ran 9 tests / OK
```

- [ ] **Step 7：dry-run**

只调用一次只读的 `aws iam get-role`（角色不存在，返回 `NoSuchEntity`）：

```bash
bash infra/35-runtime-role.sh
git diff --stat infra/state.env   # 期望：无输出
```
期望（时间戳和临时文件名不同）：
```
[..] APPLY=0 region=us-east-1 state=/home/ubuntu/AI-code/Doris-mcp-skill-Demo/infra/state.env
[..] rendered runtime-trust.json:
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AgentCoreRuntimeAssume",
      "Effect": "Allow",
      "Principal": { "Service": "bedrock-agentcore.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "aws:SourceAccount": "890717383483" },
        "ArnLike": { "aws:SourceArn": "arn:aws:bedrock-agentcore:us-east-1:890717383483:*" }
      }
    }
  ]
}
DRY-RUN: aws iam create-role --role-name doris-mcp-runtime-role --assume-role-policy-document file:///tmp/tmp.XXXXXXXXXX --tags Key=Project\,Value=doris-mcp-demo --description AgentCore\ Runtime\ dorismcp:\ own\ logs\ +\ the\ doris-mcp/mcp_svc\ secret --query Role.Arn --output text
[..] rendered runtime-exec.json:
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RuntimeLogGroup",
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:DescribeLogStreams", "logs:PutResourcePolicy"],
      "Resource": "arn:aws:logs:us-east-1:890717383483:log-group:/aws/bedrock-agentcore/runtimes/dorismcp_dorismcp-*"
    },
    {
      "Sid": "RuntimeLogStreams",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:us-east-1:890717383483:log-group:/aws/bedrock-agentcore/runtimes/dorismcp_dorismcp-*:log-stream:*"
    },
    {
      "Sid": "DescribeLogGroups",
      "Effect": "Allow",
      "Action": "logs:DescribeLogGroups",
      "Resource": "arn:aws:logs:us-east-1:890717383483:log-group:*"
    },
    {
      "Sid": "ReadDorisServiceSecret",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:us-east-1:890717383483:secret:doris-mcp/mcp_svc-RIUdT2"
    }
  ]
}
DRY-RUN: aws iam put-role-policy --role-name doris-mcp-runtime-role --policy-name doris-mcp-runtime --policy-document file:///tmp/tmp.XXXXXXXXXX
[..] done (APPLY=0)
```
dry-run 不写 `state.env`（角色 ARN 在 dry-run 里只是占位符）。如果输出里是 `role exists: …`，说明角色已经存在（例如上次执行到一半），先停下来查。

- [ ] **Step 8：GATE —— 展示并等待确认**

向用户展示 Step 7 的输出，并说明：
- 将创建 1 个 IAM 角色 `doris-mcp-runtime-role`（tag `Project=doris-mcp-demo`）和它的内联策略 `doris-mcp-runtime`，不附加任何托管策略；IAM 不收费；
- 角色只允许 AgentCore 在本账号、us-east-1 代入，权限只有：写 `dorismcp_dorismcp-*` 自己的日志组、`logs:DescribeLogGroups`、读 `doris-mcp/mcp_svc` 这一个 secret；没有 Bedrock 模型、X-Ray、configuration-bundle 权限；
- 本步骤不改 Runtime：Runtime 在 T3.2 的 deploy（另一个 GATE）之后才用这个角色；
- 回滚（也需要 GATE；只在 T3.2 deploy 之前可以直接删，之后要先 deploy 回 CDK 角色）：`aws iam delete-role-policy --role-name doris-mcp-runtime-role --policy-name doris-mcp-runtime`，再 `aws iam delete-role --role-name doris-mcp-runtime-role`，并删掉 `state.env` 的 `RT_ROLE_ARN` 行。

用户明确确认后执行：
```bash
APPLY=1 bash infra/35-runtime-role.sh
```
期望：没有 `rendered …` 和 `DRY-RUN:` 行；`waiting 15s for IAM propagation`、`state: RT_ROLE_ARN=arn:aws:iam::890717383483:role/doris-mcp-runtime-role`、`done (APPLY=1)`。如果 harness 拦住了这条命令，请用户在提示符里输入 `! APPLY=1 bash infra/35-runtime-role.sh` 自己执行。

- [ ] **Step 9：验证（只读）**

```bash
aws iam get-role --region us-east-1 --role-name doris-mcp-runtime-role \
  --query '{arn: Role.Arn, tags: Role.Tags, principal: Role.AssumeRolePolicyDocument.Statement[0].Principal.Service}' --output json
aws iam list-role-policies --region us-east-1 --role-name doris-mcp-runtime-role --query PolicyNames --output text
aws iam list-attached-role-policies --region us-east-1 --role-name doris-mcp-runtime-role --query 'length(AttachedPolicies)'
aws iam get-role-policy --region us-east-1 --role-name doris-mcp-runtime-role --policy-name doris-mcp-runtime \
  --query 'PolicyDocument.Statement[].[Sid, Resource]' --output text
grep '^RT_ROLE_ARN=' infra/state.env
bash infra/35-runtime-role.sh 2>&1 | grep -E 'role exists|DRY-RUN|done'
```
期望：
- `arn` 是 `arn:aws:iam::890717383483:role/doris-mcp-runtime-role`，`tags` 是 `Project=doris-mcp-demo`，`principal` 是 `bedrock-agentcore.amazonaws.com`；
- 内联策略只有 `doris-mcp-runtime`，托管策略 `0` 个；
- 4 行 Sid：`RuntimeLogGroup`、`RuntimeLogStreams`、`DescribeLogGroups`、`ReadDorisServiceSecret`，最后一行的 Resource 是 `arn:aws:secretsmanager:us-east-1:890717383483:secret:doris-mcp/mcp_svc-RIUdT2`（没有 `*`）；
- `state.env` 有 `RT_ROLE_ARN=arn:aws:iam::890717383483:role/doris-mcp-runtime-role`；
- 重跑 dry-run 输出 `role exists: arn:aws:iam::890717383483:role/doris-mcp-runtime-role`、一行 `DRY-RUN: aws iam put-role-policy …`、`done (APPLY=0)`，不再有 `create-role`。

- [ ] **Step 10：收尾**

勾选 T3.1；progress「当前状态」写 T3.1 完成、下一步 T3.2，「已创建的 AWS 资源」加上 IAM 角色 `doris-mcp-runtime-role`（内联策略 `doris-mcp-runtime`）；日志记录 Step 3 的失败数、Step 9 的结果和用户确认 GATE 的原话。

```bash
bash scripts/check-secrets.sh
git add infra/35-runtime-role.sh infra/policies/runtime-trust.json infra/policies/runtime-exec.json \
        infra/test/test-35-runtime-role.sh scripts/render-agentcore.py scripts/test/test_render_agentcore.py \
        infra/state.env specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "feat(p3): T3.1 Runtime execution role doris-mcp-runtime-role

Own log groups + GetSecretValue on the doris-mcp/mcp_svc secret only; render-agentcore.py --phase
server sets executionRoleArn so the CDK imports it instead of creating its Bedrock/X-Ray role.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T3.2：锁定 CodeZip 依赖，deploy 完整 server（换执行角色）

来源：tasks.md T3.2、design §7（deploy 行）、P1「P3 时核对」的 CodeZip 与 `.venv` 一致性。deploy 之前先在本机以 `mcp_svc`（凭证来自 Secrets Manager，和 Runtime 一样）跑一遍**将要打包的代码**，确认 P-09 生效、12 个工具和 flow 都正常；然后锁定两个传递依赖，让 CodeZip 与测试过的 `.venv` 一致；最后 render `--phase server`，看过 CDK diff 再 deploy。

**Files:**
- Modify：`mcp-server/pyproject.toml`（锁定 `caio==0.12.5`、`platformdirs==4.11.15`）、`mcp-server/UPSTREAM.md`（P-07 行）、`dorismcp/agentcore/agentcore.json`（render 写入）、`dorismcp/agentcore/.cli/deployed-state.json`（deploy 写入）、`infra/state.env`（`25-runtime-state.sh` 写入新的 `RUNTIME_ROLE_ARN`）、`tasks.md`、`progress.md`
- Test：`/tmp/p3-codezip-check.sh`（临时脚本，不进仓库）

**Interfaces:**
- Consumes：
  - T3.0：P-09、M3；
  - T3.1：`RT_ROLE_ARN`、`render-agentcore.py --phase server`；
  - P0：`infra/25-runtime-state.sh`（AWS 只读，APPLY=1 只写 `state.env`，不是 GATE）、`~/.agentcore/config.json` 的 `disableTransactionSearch`；
  - P2：Secrets Manager `doris-mcp/mcp_svc`、`mcp_svc` 目前的 host `'%'`（开发机可以登录，T3.5 之后就不行了）。
- Produces：
  - Runtime `dorismcp_dorismcp`：
    - 原地更新到 `agentRuntimeVersion` 2，`RUNTIME_ARN`、`RUNTIME_ID`、`RUNTIME_URL` 都不变；
    - `roleArn` 是 `doris-mcp-runtime-role`；
    - env 为 `DORIS_HOST`、`DORIS_HTTP_PORT`、`DORIS_PORT`、`DORIS_SECRET_ID`、`PROFILE_SCOPE`。
  - `state.env` 里 `RUNTIME_ROLE_ARN` = `RT_ROLE_ARN`。
  - CDK 生成的执行角色和它的 DefaultPolicy 被删除。
  - **Gateway target 此时还缓存着 spike 的工具列表**：T3.4 同步之前，经 Gateway 看到的仍是旧工具。Quick 在 P4 才接入，所以没有影响。

- [ ] **Step 1：确认分支和工作区**

```bash
git branch --show-current && git status --short && grep '^RT_ROLE_ARN=' infra/state.env
```
期望：`p3-deploy`，工作区干净，`RT_ROLE_ARN=arn:aws:iam::890717383483:role/doris-mcp-runtime-role`。

- [ ] **Step 2：本机以 `mcp_svc` 跑将要部署的代码**（只读；凭证经 Secrets Manager，与 Runtime 相同；server 日志里有 Doris 地址，只经 sed 查看）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
rm -rf /tmp/p3-local-ws
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  unset DORIS_ROOT_USER DORIS_ROOT_PASSWORD DORIS_RO_USER DORIS_RO_PASSWORD DORIS_ADMIN_PASSWORD DORIS_USER DORIS_PASSWORD
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_HTTP_PORT="${DORIS_HTTP_PORT:-8030}" \
         DORIS_SECRET_ID=doris-mcp/mcp_svc AWS_REGION=us-east-1 MCP_PORT=8000 DORIS_MCP_WORKSPACE_DIR=/tmp/p3-local-ws
  exec timeout 900 .venv/bin/python mcp-server/mcp_server.py ) > /tmp/p3-local.log 2>&1 &
for i in $(seq 40); do curl -sf http://127.0.0.1:8000/ping >/dev/null && break; sleep 1; done
U=http://127.0.0.1:8000/mcp
.venv/bin/python scripts/mcp_smoke.py --url $U call execute_query '{"sql": "SELECT @@wait_timeout AS wait_timeout"}' \
  | grep -oE '"wait_timeout": [0-9]+'
.venv/bin/python scripts/mcp_smoke.py --url $U list --expect 12 | grep -E '^tools:|FAIL'
.venv/bin/python scripts/mcp_smoke.py --url $U flow | grep -E '^flow:|FAIL'
p=8000; pid=$(ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | cut -d= -f2); [ -n "$pid" ] && kill "$pid"
grep -E 'Doris MCP for AgentCore|service mode' /tmp/p3-local.log | sed -E "$MASK" | cut -d' ' -f3-
grep -cE 'Traceback| ERROR | CRITICAL ' /tmp/p3-local.log
pw="$(aws secretsmanager get-secret-value --region us-east-1 --secret-id doris-mcp/mcp_svc --query SecretString --output text |
      python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')"
grep -cF -f <(printf '%s\n' "$pw") /tmp/p3-local.log; unset pw
```
期望：
```
"wait_timeout": 600
tools: 12
flow: 6/6 passed
INFO doris_new_mcp: Auth: service mode, MCP auth delegated to the edge; Doris user mcp_svc
INFO doris_new_mcp.agentcore: Doris MCP for AgentCore: Doris <ip>:9030 (http 8030) as mcp_svc, profile scope all, workspace /tmp/p3-local-ws
0
0
```
- `wait_timeout` 是 600，而不是 Doris 默认的 28800，说明 P-09 在真实 Doris 上生效；
- 最后两个 `0` 分别是：日志里没有 Traceback / ERROR，日志里没有 `mcp_svc` 的密码；
- spec 阶段实测的两个首调耗时：`list_metrics` 首次调用约 11.5 s，因为要加载语义层（T3.3 会在 Runtime 上再测）。

如果第一个 `grep` 没有输出，先按 mask 查看 `/tmp/p3-local.log` 的末尾（`tail -20 /tmp/p3-local.log | sed -E "$MASK"`），不要直接打印这个日志。

- [ ] **Step 3：写 CodeZip 依赖检查脚本，确认锁定前不一致**

agentcore CLI 用 uv 按 `mcp-server/pyproject.toml` 为 aarch64 解析依赖，再装进 staging 目录打包。这个脚本用同样的方式解析，然后把每个 dist 的版本和 `.venv` 比较；也可以直接检查已有的 staging 目录。脚本放在 `/tmp`，不进仓库。

```bash
cat > /tmp/p3-codezip-check.sh <<'SH'
# Compare the dists of an AgentCore CodeZip with the tested .venv (P3 / T3.2). Run from the repo root.
#   bash /tmp/p3-codezip-check.sh               # resolve mcp-server/pyproject.toml the way the agentcore CLI does
#   bash /tmp/p3-codezip-check.sh STAGING_DIR   # the dists of an existing CodeZip staging dir
set -euo pipefail
DIR="${1:-}"
if [[ -z "$DIR" ]]; then
  DIR=/tmp/p3-zipcheck
  rm -rf "$DIR"
  # The CLI tries manylinux2014 first; rapidfuzz has no such wheel, so it ends up on 2_28.
  uv pip install -q -r mcp-server/pyproject.toml --target "$DIR" --python-version 3.12 \
    --python-platform aarch64-manylinux_2_28 --only-binary :all:
fi
uv pip freeze --python .venv/bin/python > /tmp/p3-venv-freeze.txt
.venv/bin/python - "$DIR" <<'PY'
import pathlib, re, sys

def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()

zipped = {}
for d in pathlib.Path(sys.argv[1]).glob("*.dist-info"):
    name, version = d.name[: -len(".dist-info")].rsplit("-", 1)
    zipped[norm(name)] = version
if not zipped:
    sys.exit(f"FAIL: no *.dist-info in {sys.argv[1]}")
venv = {}
for line in open("/tmp/p3-venv-freeze.txt"):
    if "==" in line:
        name, version = line.strip().split("==", 1)
        venv[norm(name)] = version
differ = sorted(n for n in zipped if venv.get(n) != zipped[n])
for n in differ:
    print(f"  {n}: CodeZip {zipped[n]}, .venv {venv.get(n, '-')}")
print(f"CodeZip: {len(zipped)} dists, {len(differ)} differ from .venv")
sys.exit(1 if differ else 0)
PY
SH
bash /tmp/p3-codezip-check.sh; echo "exit=$?"
```
期望（约 30 s）：
```
  caio: CodeZip 0.12.9, .venv 0.12.5
  platformdirs: CodeZip 4.12.0, .venv 4.11.15
CodeZip: 88 dists, 2 differ from .venv
exit=1
```
`pyproject.toml` 只锁了直接依赖，这两个传递依赖（`aiofile` → `caio`，`fastmcp-slim` → `platformdirs`）解析到了比 `.venv` 更新的版本，而所有测试都是在 `.venv` 上跑的。如果这里列出的包或版本不同（PyPI 又有新版本），按实际输出锁定，并在 progress 里记录。

- [ ] **Step 4：锁定两个传递依赖**

```bash
git apply <<'PATCH'
diff --git a/mcp-server/UPSTREAM.md b/mcp-server/UPSTREAM.md
index 7e79d25..022f6a7 100644
--- a/mcp-server/UPSTREAM.md
+++ b/mcp-server/UPSTREAM.md
@@ -16,7 +16,7 @@
 | P-04 | `src/server.py` | `create_server(service_credentials=, workspace_dir=)`: no MCP auth, one service-account pool |
 | P-05 | `src/tools/profile.py` (new) | `list_recent_queries`, `get_query_profile` |
 | P-06 | `config/mcp-server.toml` (new) | runtime limits (50 s SQL timeout, pool 5, 2000 rows) |
-| P-07 | `pyproject.toml` (new) | dependencies pinned to upstream `uv.lock` + boto3, for AgentCore CodeZip |
+| P-07 | `pyproject.toml` (new) | dependencies pinned to upstream `uv.lock` + boto3 (+ 2 transitive pins that keep the CodeZip equal to the tested `.venv`), for AgentCore CodeZip |
 | P-08 | `test/test_agentcore_*.py` (new) | tests for P-01..P-06 |
 | P-09 | `src/config/loader.py`, `src/core/connection.py`, `config/mcp-server.toml`, `test/test_agentcore_session_timeout.py` (new) | `SET wait_timeout` on every pool connection (`session_wait_timeout_seconds = 600`), so Doris reaps what a torn-down Runtime microVM left open |
 
diff --git a/mcp-server/pyproject.toml b/mcp-server/pyproject.toml
index 4de5976..bb13ee7 100644
--- a/mcp-server/pyproject.toml
+++ b/mcp-server/pyproject.toml
@@ -33,4 +33,8 @@ dependencies = [
     "typer==0.27.0",
     "typing_extensions==4.16.0",
     "uvicorn==0.51.0",
+    # Transitive (aiofile -> caio, fastmcp-slim -> platformdirs), pinned to the tested .venv: unpinned,
+    # the CodeZip resolved newer releases than the ones the tests ran with (P3 T3.2).
+    "caio==0.12.5",
+    "platformdirs==4.11.15",
 ]
PATCH
```

- [ ] **Step 5：确认一致**

```bash
bash /tmp/p3-codezip-check.sh; echo "exit=$?"
bash /tmp/p3-codezip-check.sh /tmp/nonexistent-dir; echo "exit=$?"
```
期望：`CodeZip: 88 dists, 0 differ from .venv`、`exit=0`；第二条是检查脚本自己的自检：`FAIL: no *.dist-info in /tmp/nonexistent-dir`、`exit=1`（空目录不能算通过）。锁定的版本和 `.venv` 相同，所以 `.venv` 不用重装，测试不用重跑。

- [ ] **Step 6：确认 Transaction Search 保持关闭**（只读）

```bash
python3 -c "import json; print(json.load(open('/home/ubuntu/.agentcore/config.json')).get('disableTransactionSearch'))"
```
期望：`True`。P0 就关闭了它：打开时 CLI 在 deploy 过程中会去开启账号级的 CloudWatch Transaction Search。新的执行角色也没有 X-Ray 权限。如果输出不是 `True`，先停下来问用户。

- [ ] **Step 7：render `--phase server`**

```bash
.venv/bin/python scripts/render-agentcore.py --phase server
python3 - <<'PY'
import json
runtimes = json.load(open("dorismcp/agentcore/agentcore.json"))["runtimes"]
r = runtimes[0]
print(len(runtimes), r["name"], r["codeLocation"], r["entrypoint"], r["networkMode"], r["protocol"], r["authorizerType"])
print(r["executionRoleArn"])
print(sorted(e["name"] for e in r["envVars"]))
print({e["name"]: e["value"] for e in r["envVars"] if e["name"] != "DORIS_HOST"})
PY
git diff --stat dorismcp/
```
期望：
```
wrote dorismcp/agentcore/agentcore.json (runtime dorismcp, phase server) and aws-targets.json
1 dorismcp ../mcp-server/ mcp_server.py VPC MCP AWS_IAM
arn:aws:iam::890717383483:role/doris-mcp-runtime-role
['DORIS_HOST', 'DORIS_HTTP_PORT', 'DORIS_PORT', 'DORIS_SECRET_ID', 'PROFILE_SCOPE']
{'DORIS_PORT': '9030', 'DORIS_HTTP_PORT': '8030', 'DORIS_SECRET_ID': 'doris-mcp/mcp_svc', 'PROFILE_SCOPE': 'all'}
 dorismcp/agentcore/agentcore.json | 13 +++++++++++--
 1 file changed, 11 insertions(+), 2 deletions(-)
```
`aws-targets.json` 的内容不变。第 4 行故意不打印 `DORIS_HOST`（私网 IP）；**不要** `cat` 或 `git diff` `agentcore.json`。

- [ ] **Step 8：validate + CDK diff**（只读；会在 `dorismcp/agentcore/.cache/` 里生成 staging，已被 gitignore）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
(cd dorismcp && agentcore validate && agentcore deploy --diff -v) > /tmp/t32-diff.log 2>&1; echo "exit=$?"
sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g; s/^.*(Stack AgentCore)/\1/' /tmp/t32-diff.log | sed -E "$MASK" |
  grep -E '^Valid|^Stack |^│ - |^\[[-+~]\]|Added:|\[\+\] "arn|Number of stacks|Diff complete' | cut -c1-200 | sed -E 's/ +$//'
bash /tmp/p3-codezip-check.sh dorismcp/agentcore/.cache/dorismcp/staging; echo "exit=$?"
```
期望（spec 阶段在一个代码相同的 worktree 上实测，当时角色还没有建；CDK diff 不检查角色是否存在。S3 zip 的哈希每次不同，不在过滤结果里）：
```
exit=0
Valid
Stack AgentCore-dorismcp-default
│ - │ ${Application/AgentDorismcp/Runtime/ExecutionRole.Arn}                          │ Allow  │ sts:AssumeRole                                    │ Service:bedrock-agentcore.amazonaws.com
│ - │ *                                                                               │ Allow  │ logs:DescribeLogGroups                            │ AWS:${Application/AgentDorismcp/Runtime/E
│ - │ arn:aws:bedrock-agentcore:*:*:configuration-bundle/*                            │ Allow  │ bedrock-agentcore:CreateConfigurationBundle       │ AWS:${Application/AgentDorismcp/Runtime/E
│ - │ arn:aws:bedrock:*:890717383483:inference-profile/*                              │ Allow  │ bedrock:CountTokens                               │ AWS:${Application/AgentDorismcp/Runtime/E
│ - │ arn:aws:logs:us-east-1:890717383483:log-group:/aws/bedrock-agentcore/runtimes/* │ Allow  │ logs:CreateLogGroup                               │ AWS:${Application/AgentDorismcp/Runtime/E
[-] AWS::IAM::Role Application/AgentDorismcp/Runtime/ExecutionRole ApplicationAgentDorismcpRuntimeExecutionRole613A6EB1 destroy
[-] AWS::IAM::Policy Application/AgentDorismcp/Runtime/ExecutionRole/DefaultPolicy ApplicationAgentDorismcpRuntimeExecutionRoleDefaultPolicy3F6D2A41 destroy
[~] AWS::BedrockAgentCore::Runtime Application/AgentDorismcp/Runtime ApplicationAgentDorismcpRuntime21B2F7F2
 │   ├─ [+] Added: .DORIS_SECRET_ID
 │   └─ [+] Added: .PROFILE_SCOPE
 │      [+] "arn:aws:iam::890717383483:role/doris-mcp-runtime-role"
[~] Output Application/AgentDorismcp/RoleArnOutput ApplicationAgentDorismcpRoleArnOutput31D78029: {"Description":"Execution Role ARN for agent: dorismcp","Value":{"Fn::GetAtt":["ApplicationAgentDorism
✨ Number of stacks with differences: 1
✓ Diff complete for 'default' (stack: AgentCore-dorismcp-default)
CodeZip: 88 dists, 0 differ from .venv
exit=0
```
diff 的含义：
- 5 组 `│ - │` 是 CDK 角色的全部权限，随角色一起删除：
  - 代入信任；
  - `*` 上的 `logs:DescribeLogGroups` 和 X-Ray；
  - 7 个 configuration-bundle 操作；
  - 任意 Bedrock 模型和 inference profile；
  - `runtimes/*` 日志组的读写和 `PutResourcePolicy`。
- Runtime 是 `[~]`（原地更新）：
  - 代码 zip 换了；
  - 新增 env `DORIS_SECRET_ID`、`PROFILE_SCOPE`；
  - `RoleArn` 换成 `doris-mcp-runtime-role`；
  - 去掉了对 CDK 角色的 `DependsOn`。
- 没有 `[+]` 资源，也没有 Runtime 的 `[-]`，所以 `RUNTIME_ARN` 不变，Gateway target 不用改。

如果出现 Runtime 的 `destroy` / `replace`，或者有新增的 IAM 资源，停下来，不要 deploy。

- [ ] **Step 9：GATE —— 展示并等待确认**

向用户展示 Step 7、Step 8 的输出，并说明：
- `agentcore deploy` 更新 CloudFormation 栈 `AgentCore-dorismcp-default`：
  - Runtime `dorismcp_dorismcp` 原地更新为完整的 `mcp-server/`（12 个工具，以 `mcp_svc` 经 Secrets Manager 连 Doris 私网地址）；
  - 执行角色换成 `doris-mcp-runtime-role`；
  - 删除 CDK 生成的执行角色和它的策略。
- P0 的部署耗时是 5 分 41 秒。
- 费用：Runtime 按会话计费，没有新增的常驻资源；CodeZip（约 110 MB）上传到已有的 CDK bootstrap bucket。
- 影响：
  - Gateway target 仍然指向同一个 Runtime ARN，但缓存的还是 spike 的工具列表，T3.4 同步；
  - 在 T3.3 冒烟之前，没有东西会调用这个 Runtime。
- 回滚（也需要 GATE）：`.venv/bin/python scripts/render-agentcore.py --phase spike`，然后再 deploy 一次。这样代码回到 spike，CDK 会重新生成执行角色，`doris-mcp-runtime-role` 保留不动。

用户明确确认后执行（约 6 分钟；用 Bash 的 `run_in_background`，或者把 timeout 设为 600000）：
```bash
(cd dorismcp && agentcore deploy -y -v) > /tmp/t32-deploy.log 2>&1; echo "exit=$?"
```
期望：`exit=0`。如果 harness 拦住了这条命令，请用户在提示符里输入 `! (cd dorismcp && agentcore deploy -y -v) > /tmp/t32-deploy.log 2>&1; echo "exit=$?"` 自己执行。

- [ ] **Step 10：确认部署结果**（只读）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
log=$(ls -t dorismcp/agentcore/.cli/logs/deploy/deploy-*.log | head -1)
grep -c 'Status: SUCCESS' "$log"; grep -E '^(COMPLETED|FAILED)|^Total Duration|Status: (FAILED|ERROR)' "$log" | sed -E "$MASK"
(cd dorismcp && agentcore status --json) | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["resources"][0]
t=d["deployedState"]["targets"]["default"]["resources"]; print(r["deploymentState"], r["detail"], t["runtimes"]["dorismcp"]["roleArn"])'
bash infra/25-runtime-state.sh 2>&1 | sed -E "$MASK" | grep -E 'runtime dorismcp|WARN|FATAL'
```
期望：
- `9`（CLI 的 9 个步骤都是 `Status: SUCCESS`：Load deployment target、Validate project、Sync CDK dependencies、Build CDK project、Synthesize CloudFormation、Check bootstrap status、Check stack status、Deploy to AWS、Persist deployment state），然后是 `COMPLETED SUCCESSFULLY` 和 `Total Duration: …`（P0 是 `5m 41s`）；
- `deployed READY arn:aws:iam::890717383483:role/doris-mcp-runtime-role`；
- `runtime dorismcp_dorismcp: status=READY version=2`，没有 WARN。

如果 status 不是 READY，等 1 分钟重跑最后一条；仍然不是就停下来，把 `tail -40 /tmp/t32-deploy.log | sed -E "$MASK"` 给用户看。

- [ ] **Step 11：记录 Runtime，并核对角色和 env**（AWS 只读；`APPLY=1` 只写 `state.env`，不是 GATE）

```bash
APPLY=1 bash infra/25-runtime-state.sh 2>&1 | grep -cE 'state: RUNTIME_(ARN|ID|ROLE_ARN|URL)='
git diff -U0 infra/state.env | grep -E '^[-+][A-Z]'
source infra/state.env
aws bedrock-agentcore-control get-agent-runtime --region us-east-1 --agent-runtime-id "$RUNTIME_ID" \
  --query '{status: status, version: agentRuntimeVersion, role: roleArn, env: sort(keys(environmentVariables)), network: networkConfiguration.networkMode}' --output json
aws cloudformation list-stack-resources --region us-east-1 --stack-name AgentCore-dorismcp-default \
  --query "StackResourceSummaries[?starts_with(ResourceType, 'AWS::IAM::')] | length(@)"
OLD_ROLE=$(git show HEAD:infra/state.env | grep '^RUNTIME_ROLE_ARN=' | cut -d= -f2); echo "${OLD_ROLE##*/}"
aws iam get-role --region us-east-1 --role-name "${OLD_ROLE##*/}" 2>&1 | grep -c NoSuchEntity
```
期望：
- `4`；
- state.env 只有一行变化：`-RUNTIME_ROLE_ARN=arn:aws:iam::890717383483:role/AgentCore-dorismcp-defaul-ApplicationAgentDorismcpR-30Mcwi4tCmaV`、`+RUNTIME_ROLE_ARN=arn:aws:iam::890717383483:role/doris-mcp-runtime-role`（`RUNTIME_ARN`、`RUNTIME_ID`、`RUNTIME_URL` 都没变）；
- get-agent-runtime：`status` READY、`version` `"2"`、`role` 是 `doris-mcp-runtime-role`、`env` 是那 5 个名字、`network` VPC；
- 栈里 IAM 资源 `0` 个；
- 旧角色名 `AgentCore-dorismcp-defaul-ApplicationAgentDorismcpR-30Mcwi4tCmaV`，`get-role` 返回 NoSuchEntity（计数 `1`）。

- [ ] **Step 12：deploy 实际打包的依赖**

```bash
bash /tmp/p3-codezip-check.sh dorismcp/agentcore/.cache/dorismcp/staging; echo "exit=$?"
ls dorismcp/agentcore/.cache/dorismcp/staging | grep -E '^(mcp_server.py|src|config)$'
```
期望：`CodeZip: 88 dists, 0 differ from .venv`、`exit=0`；`config`、`mcp_server.py`、`src` 三行。

- [ ] **Step 13：收尾**

- 勾选 T3.2。
- progress「当前状态」：T3.2 完成、下一步 T3.3；「已创建的 AWS 资源」里 Runtime 一行改为 version 2 / `doris-mcp-runtime-role`，删掉 CDK 角色。
- 日志记录：Step 2 的结果、Step 3 的两个漂移和锁定、Step 8 的 diff 摘要、deploy 耗时（`Total Duration`）、Step 11 的结果、用户确认 GATE 的原话。

```bash
bash scripts/check-secrets.sh
git add mcp-server/pyproject.toml mcp-server/UPSTREAM.md dorismcp/agentcore/agentcore.json dorismcp/agentcore/aws-targets.json \
        dorismcp/agentcore/.cli/deployed-state.json infra/state.env specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "feat(p3): T3.2 deploy the full mcp-server to Runtime dorismcp with doris-mcp-runtime-role

Pin the transitive caio / platformdirs so the CodeZip equals the tested .venv (88 dists); the CDK
execution role is gone, the Runtime is updated in place (version 2, same ARN).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T3.3：SigV4 直连 Runtime 冒烟、耗时、审计日志和对账

来源：
- tasks.md T3.3、design §11 P3 行（冒烟 + 耗时）、R-32（审计）；
- P1「P3 时核对」的 20 个并发对 `pool_max_size=5` 和 60 s 上限的影响：本任务给 `time` 加上 `--parallel`，并发本身在 T3.4 经 Gateway 测；
- P2 整体评审遗留「`reconcile.py mcp` 对部署的 Runtime 再跑一次」。

Runtime 的入站认证是 AWS_IAM，所以本机要用 SigV4 签名的客户端直连。先离线 TDD：
- `scripts/agentcore_client.py`；
- `mcp_smoke.py` 的 `--sigv4`、`time`、`conns`；
- `scripts/audit_check.py`；
- `reconcile.py mcp --url`。

然后对 T3.2 部署的 Runtime 跑 7 项检查：
- 工具列表；
- flow；
- 共享 session 和每次新 session 的逐次耗时；
- CloudWatch 审计记录；
- CloudWatch 日志泄漏计数；
- 对账 11/11；
- Doris 连接的来源和空闲时长。

本任务不改任何 AWS 资源或 Doris 权限，没有 GATE。

**Files:**
- Create：
  - `scripts/agentcore_client.py`
  - `scripts/audit_check.py`
  - `scripts/smoke_calls.json`（12 个只读调用，每个 server 工具一个）
  - `scripts/test/test_agentcore_client.py`
  - `scripts/test/test_audit_check.py`
  - `scripts/test/test_mcp_smoke.py`
- Modify：`scripts/mcp_smoke.py`、`doris/reconcile.py`、`doris/test/test_reconcile.py`、`tasks.md`、`progress.md`
- 测试数：`scripts/test` 从 9 个增加到 53 个，`doris/test` 从 125 个增加到 130 个。

**Interfaces:**
- Consumes：
  - T3.2：Runtime `dorismcp_dorismcp`（`state.env` 的 `RUNTIME_URL`、`RUNTIME_ID`）；
  - P2 的 `scripts/mcp_smoke.py`：`build_client(args)`、`call_json`、`error_code`、`result_payload`，以及 `list` / `call` / `flow` 子命令；
  - P2 的 `doris/reconcile.py`：`main(argv, env, connect, out, err, client_factory)`、`_run_mcp`；
  - P1 的 `agentcore_ext.app`：root logger 和 `doris_new_mcp.audit` logger 都写 stderr，AgentCore 把 stderr 送到 CloudWatch 日志组 `/aws/bedrock-agentcore/runtimes/<RUNTIME_ID>-DEFAULT`。
- Produces：
  - `scripts/agentcore_client.py`：
    - `sigv4_client(url, region=None, timeout=90.0) -> fastmcp.Client`，region 默认从 URL 取；本机的 `AWS_DEFAULT_REGION` 是 us-west-2，不能用它；
    - `region_from_url(url) -> str | None`；
    - `SigV4Auth(region, credentials=None)`，httpx.Auth，每个请求连同 body 一起签名；没有凭证时抛 `RuntimeError`。
  - `scripts/mcp_smoke.py`：
    - 全局选项 `--sigv4 [--region R]`，只能配 `--url`，不能和 `--bearer-env` 同时用；
    - `time [--calls FILE] [--prefix P] [--parallel N] [--repeat N] [--fresh] [--budget-ms 60000]`：
      - 逐行输出 `  {ok|ERR|SLOW} {ms} ms  {tool}`；
      - 最后一行 `time: N calls (…), E errors, S over B ms; p50 … p95 … max …; wall …`；
    - `conns [--prefix P] [--expect-host-prefix X] [--max-idle S]`：只输出计数；
    - `load_calls(path)`；
    - `main(argv=None, client_factory=build_client)`；
    - exit 0 = 通过，1 = 失败，2 = calls 文件无效。
    - T3.4 经 Gateway 用 `--prefix doris___`，T3.5 用 `conns`。
  - `scripts/audit_check.py`：
    - 读 `aws logs filter-log-events --output json`，统计每个工具的 ok / failed 审计记录数，不输出参数、SQL、错误文本或 client id；
    - `--calls FILE --repeat N` 要求每个工具至少有 N 条记录；
    - exit 0 = 通过，1 = 缺记录或有读不出的记录，2 = 输入不是 filter-log-events 的 JSON。
  - `doris/reconcile.py`：
    - `mcp --url URL [--region R]`：指标经 Runtime 查询，参照 SQL 仍用 `load_settings` 的账号走 pymysql；
    - `main(…, remote_client_factory=None)`；
    - T3.5 之后用 `demo_ro` 作参照账号重跑。

- [ ] **Step 1：确认分支、工作区和 Runtime**

```bash
git branch --show-current && git status --short
source infra/state.env
aws bedrock-agentcore-control get-agent-runtime --region us-east-1 --agent-runtime-id "$RUNTIME_ID" \
  --query '[status, agentRuntimeVersion]' --output text
```
期望：
- 分支是 `p3-deploy`，工作区干净；
- `READY	2`。

- [ ] **Step 2：写失败测试**

`scripts/test/test_agentcore_client.py`：
- 用假凭证验证 SigV4 签名；
- 请求经 `httpx.MockTransport`，不访问 AWS；
- 验证 region 从 URL 取（覆盖 `AWS_DEFAULT_REGION`）。

新建 `scripts/test/test_agentcore_client.py`：

```python
"""scripts/agentcore_client.py: SigV4 (bedrock-agentcore) auth for a Runtime's MCP invoke URL (P3 / T3.3).

The signature is checked the way the service checks it: recomputed from the request as it arrives,
over the headers the request says it signed.
"""

import datetime as dt
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import httpx
from botocore.auth import SigV4Auth as BotoSigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agentcore_client  # noqa: E402
from agentcore_client import SigV4Auth, region_from_url  # noqa: E402

URL = ("https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/"
       "arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A111122223333%3Aruntime%2Fdorismcp_dorismcp-AbCdEf1234"
       "/invocations?qualifier=DEFAULT")
CREDS = Credentials("AKIDEXAMPLE", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "session-token-example")
NOW = dt.datetime(2026, 9, 27, 8, 0, 0)
BODY = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'


def _parts(request: httpx.Request) -> tuple[list[str], str]:
    auth = request.headers["authorization"]
    return (re.search(r"SignedHeaders=([^,]+)", auth).group(1).split(";"),
            re.search(r"Signature=([0-9a-f]{64})$", auth).group(1))


def _service_signature(request: httpx.Request, body: bytes | None = None) -> str:
    """What the service computes from the received method, URL, signed headers and body."""
    signed, _ = _parts(request)
    aws = AWSRequest(method=request.method, url=str(request.url),
                     data=request.content if body is None else body,
                     headers={h: request.headers[h] for h in signed})
    aws.context["timestamp"] = request.headers["x-amz-date"]
    signer = BotoSigV4Auth(CREDS.get_frozen_credentials(), "bedrock-agentcore", "us-east-1")
    return signer.signature(signer.string_to_sign(aws, signer.canonical_request(aws)), aws)


class TestSigV4Auth(unittest.IsolatedAsyncioTestCase):
    async def _send(self, headers: dict | None = None, credentials=CREDS) -> httpx.Request:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={})

        auth = SigV4Auth("us-east-1", credentials=credentials)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), auth=auth) as client:
            with mock.patch("botocore.auth.get_current_datetime", return_value=NOW):
                await client.post(URL, content=BODY, headers={"content-type": "application/json",
                                                               "accept": "application/json, text/event-stream",
                                                               **(headers or {})})
        return seen[0]

    async def test_credential_scope_is_bedrock_agentcore_in_the_region(self):
        request = await self._send()
        self.assertTrue(request.headers["authorization"].startswith(
            "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20260927/us-east-1/bedrock-agentcore/aws4_request, "))
        self.assertEqual(request.headers["x-amz-date"], "20260927T080000Z")

    async def test_signature_verifies_on_the_received_request(self):
        request = await self._send()
        self.assertEqual(_parts(request)[1], _service_signature(request))

    async def test_body_is_signed(self):
        request = await self._send()
        self.assertNotEqual(_parts(request)[1], _service_signature(request, body=BODY.replace(b"list", b"call")))

    async def test_session_token_is_sent_and_signed(self):
        request = await self._send()
        self.assertEqual(request.headers["x-amz-security-token"], "session-token-example")
        self.assertIn("x-amz-security-token", _parts(request)[0])

    async def test_mcp_session_id_is_signed(self):
        # The Runtime routes a session to its microVM by this header; an unsigned one could be swapped.
        request = await self._send({"mcp-session-id": "0f3c"})
        self.assertIn("mcp-session-id", _parts(request)[0])
        self.assertEqual(_parts(request)[1], _service_signature(request))

    async def test_headers_a_proxy_may_rewrite_are_not_signed(self):
        signed, _ = _parts(await self._send())
        self.assertIn("host", signed)
        self.assertIn("content-type", signed)
        for header in ("accept-encoding", "connection", "user-agent"):
            self.assertNotIn(header, signed)

    def test_missing_credentials_fail_at_construction(self):
        session = mock.Mock()
        session.get_credentials.return_value = None
        with mock.patch.object(agentcore_client.botocore.session, "get_session", return_value=session):
            with self.assertRaisesRegex(RuntimeError, "no AWS credentials"):
                SigV4Auth("us-east-1")


class TestRegionFromUrl(unittest.TestCase):
    def test_runtime_invoke_url(self):
        self.assertEqual(region_from_url(URL), "us-east-1")

    def test_other_region(self):
        self.assertEqual(region_from_url(URL.replace("us-east-1.amazonaws", "eu-west-1.amazonaws")), "eu-west-1")

    def test_not_an_agentcore_url(self):
        self.assertIsNone(region_from_url("http://127.0.0.1:8000/mcp"))


class TestSigV4Client(unittest.TestCase):
    def test_region_defaults_to_the_url_not_aws_default_region(self):
        # This dev box sets AWS_DEFAULT_REGION=us-west-2; the Runtime is in us-east-1.
        with mock.patch.dict("os.environ", {"AWS_DEFAULT_REGION": "us-west-2"}), \
                mock.patch.object(agentcore_client, "SigV4Auth") as auth:
            agentcore_client.sigv4_client(URL)
        auth.assert_called_once_with("us-east-1")

    def test_explicit_region_wins(self):
        with mock.patch.object(agentcore_client, "SigV4Auth") as auth:
            agentcore_client.sigv4_client(URL, region="eu-west-1")
        auth.assert_called_once_with("eu-west-1")

    def test_region_is_required_for_a_non_agentcore_url(self):
        with self.assertRaisesRegex(ValueError, "--region"):
            agentcore_client.sigv4_client("http://127.0.0.1:8000/mcp")


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

`scripts/test/test_audit_check.py`：
- 用 filter-log-events 格式的假输入；
- 包含一行和 Runtime stderr 格式完全相同的审计记录。

新建 `scripts/test/test_audit_check.py`：

```python
"""scripts/audit_check.py: count doris_new_mcp.audit records in filter-log-events output (P3 / T3.3, R-32)."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_check  # noqa: E402

SECRET_SQL = "SELECT phone FROM ecom.dim_user WHERE user_id = 42"


def audit_line(tool: str, success: bool = True, **extra) -> str:
    record = {"timestamp": "2026-09-27T08:00:00+0000", "tool": tool, "client_id": "client-abc",
              "params": {"sql": SECRET_SQL}, "success": success, "duration_ms": 12.5, "query_path": "direct", **extra}
    return f"[2026-09-27 08:00:00,123] INFO doris_new_mcp.audit: {json.dumps(record)}\n"


def events(*messages: str) -> str:
    return json.dumps({"events": [{"logStreamName": "2026/09/27/[runtime-logs]s1", "timestamp": 1, "message": m}
                                  for m in messages], "searchedLogStreams": []})


class _Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.calls = Path(tmp.name) / "calls.json"
        self.calls.write_text(json.dumps([{"tool": "execute_query", "params": {"sql": "SELECT 1"}},
                                          {"tool": "list_metrics", "params": {"workspace": "ecom"}}]))

    def run_check(self, stdin: str, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        rc = audit_check.main(list(argv), stdin=io.StringIO(stdin), out=out)
        return rc, out.getvalue()


class TestAuditCheck(_Case):
    def test_every_expected_call_audited(self):
        rc, out = self.run_check(events(audit_line("execute_query"), audit_line("list_metrics"),
                                        audit_line("execute_query"), audit_line("list_metrics")),
                                 "--calls", str(self.calls), "--repeat", "2")
        self.assertEqual(rc, 0, out)
        self.assertIn("audit: 4 records (4 ok, 0 failed), 0 unreadable", out)
        self.assertRegex(out, r"(?m)^  execute_query +2 ok +0 failed  \(expected >= 2\)$")
        self.assertIn("[PASS] every expected call audited: 2/2 tools", out)

    def test_a_missing_call_fails(self):
        rc, out = self.run_check(events(audit_line("execute_query"), audit_line("list_metrics"),
                                        audit_line("list_metrics")),
                                 "--calls", str(self.calls), "--repeat", "2")
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] every expected call audited: 1/2 tools (short: execute_query 1/2)", out)

    def test_failed_calls_count_as_audited(self):
        # R-32 is about the record existing; the smoke run itself checks success.
        rc, out = self.run_check(events(audit_line("execute_query", False, error="(1105, 'host 10.1.2.3')"),
                                        audit_line("list_metrics")),
                                 "--calls", str(self.calls))
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"(?m)^  execute_query +0 ok +1 failed")

    def test_never_prints_params_errors_or_client_ids(self):
        _, out = self.run_check(events(audit_line("execute_query", False, error="(1105, 'host 10.1.2.3')")))
        for leaked in (SECRET_SQL, "phone", "10.1.2.3", "client-abc", "1105"):
            self.assertNotIn(leaked, out)

    def test_other_log_lines_are_ignored(self):
        rc, out = self.run_check(events("[2026-09-27 08:00:00,1] INFO uvicorn.access: 169.254.0.1 GET /ping 200\n",
                                        audit_line("list_metrics")))
        self.assertEqual(rc, 0, out)
        self.assertIn("audit: 1 records", out)
        self.assertNotIn("169.254.0.1", out)

    def test_an_unreadable_record_fails(self):
        rc, out = self.run_check(events("[x] INFO doris_new_mcp.audit: {\"tool\": \"execute_q", audit_line("list_metrics")))
        self.assertEqual(rc, 1)
        self.assertIn("1 unreadable", out)
        self.assertIn("[FAIL] unreadable audit records: 1", out)

    def test_no_expectation_just_counts(self):
        rc, out = self.run_check(events(audit_line("get_query_guide")))
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"(?m)^  get_query_guide +1 ok +0 failed$")

    def test_no_records_with_an_expectation_fails(self):
        rc, out = self.run_check(events(), "--calls", str(self.calls))
        self.assertEqual(rc, 1)
        self.assertIn("audit: 0 records", out)

    def test_input_that_is_not_filter_log_events_json(self):
        for stdin in ("", "not json", "[]"):
            with self.subTest(stdin=stdin):
                rc, out = self.run_check(stdin)
                self.assertEqual(rc, 2)
                self.assertIn("FAIL: input is not", out)


class TestRealAuditLine(_Case):
    def test_reads_what_the_runtime_writes_to_stderr(self):
        # The server's own logging setup (agentcore_ext.app.configure_logging) and audit writer, in a
        # child process so this process's loggers stay untouched.
        code = """if True:
            import sys, tempfile
            from core.audit import init_audit_log, log_tool_call
            from agentcore_ext.app import configure_logging
            init_audit_log(tempfile.mkdtemp() + "/audit.log")
            configure_logging()
            log_tool_call("execute_query", params={"sql": "SELECT 1"}, success=True, duration_ms=3)
            log_tool_call("list_metrics", params={"workspace": "ecom"}, success=False, error="boom")
        """
        src = Path(__file__).resolve().parents[2] / "mcp-server" / "src"
        proc = subprocess.run([sys.executable, "-c", code], cwd=src, env={**os.environ, "PYTHONPATH": str(src)},
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        rc, out = self.run_check(events(*proc.stderr.splitlines(keepends=True)), "--calls", str(self.calls))
        self.assertEqual(rc, 0, out)
        self.assertIn("audit: 2 records (1 ok, 1 failed), 0 unreadable", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

`scripts/test/test_mcp_smoke.py`：
- `time`、`conns` 用一个假的 fastmcp Client；
- `test_one_read_only_call_per_server_tool` 核对 `smoke_calls.json` 恰好覆盖 server 的 12 个工具；它在进程内起 server，不连 Doris。

新建 `scripts/test/test_mcp_smoke.py`：

```python
"""scripts/mcp_smoke.py: --sigv4, `time` and `conns` (P3 / T3.3, T3.4) against an in-process fake server."""

import asyncio
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastmcp import Client, FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcp_smoke  # noqa: E402

SHIPPED_CALLS = Path(__file__).resolve().parents[1] / "smoke_calls.json"
OK = json.dumps({"success": True, "data": {}})
PROCESSLIST = [
    {"Id": 11, "User": "mcp_svc", "Host": "172.31.5.6:40001", "Command": "Query", "Time": "0",
     "Info": "SHOW PROCESSLIST"},
    {"Id": 12, "User": "mcp_svc", "Host": "172.31.7.8:40002", "Command": "Sleep", "Time": "42", "Info": ""},
    {"Id": 13, "User": "mcp_svc", "Host": "172.31.7.8:40003", "Command": "Sleep", "Time": 7, "Info": None},
]


def fake_server(state: SimpleNamespace) -> FastMCP:
    mcp = FastMCP("fake")

    @mcp.tool
    async def ok_tool() -> str:
        return OK

    @mcp.tool(name="doris___ok_tool")
    async def prefixed_ok_tool() -> str:
        return OK

    @mcp.tool
    async def slow(ms: int = 0) -> str:
        state.active += 1
        state.peak = max(state.peak, state.active)
        await asyncio.sleep(ms / 1000)
        state.active -= 1
        return OK

    @mcp.tool
    async def fails() -> str:
        return json.dumps({"success": False, "error": {"code": "QUERY_TIMEOUT", "message": "host 10.1.2.3"}})

    @mcp.tool
    async def boom() -> str:
        raise RuntimeError("detail naming 10.1.2.3")

    @mcp.tool
    async def execute_query(sql: str) -> str:
        state.sql.append(sql)
        if state.processlist is None:
            return json.dumps({"success": False, "error": {"code": "CONNECTION_ERROR", "message": "10.1.2.3"}})
        return json.dumps({"success": True, "data": {"columns": list(PROCESSLIST[0]), "rows": state.processlist}})

    return mcp


class _SmokeCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = SimpleNamespace(active=0, peak=0, sql=[], processlist=list(PROCESSLIST), clients=0)
        self.server = fake_server(self.state)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def factory(self, _args) -> Client:
        self.state.clients += 1
        return Client(self.server)

    def calls_file(self, calls) -> str:
        path = self.tmp / "calls.json"
        path.write_text(json.dumps(calls))
        return str(path)

    async def run_main(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = await mcp_smoke.main(["--url", "http://fake/mcp", *argv], client_factory=self.factory)
        return rc, out.getvalue()


class TestTime(_SmokeCase):
    async def test_all_ok_within_budget(self):
        rc, out = await self.run_main("time", "--calls", self.calls_file(
            [{"tool": "ok_tool", "params": {}}, {"tool": "slow", "params": {"ms": 5}}]))
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"(?m)^  ok +\d+ ms  ok_tool$")
        self.assertRegex(out, r"(?m)^  ok +\d+ ms  slow$")
        self.assertRegex(out, r"time: 2 calls \(1 parallel\), 0 errors, 0 over 60000 ms; "
                              r"p50 \d+ ms, p95 \d+ ms, max \d+ ms")

    async def test_a_tool_error_fails_the_run_with_its_code_only(self):
        rc, out = await self.run_main("time", "--calls", self.calls_file(
            [{"tool": "ok_tool", "params": {}}, {"tool": "fails", "params": {}}]))
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"(?m)^  ERR +\d+ ms  fails  \(QUERY_TIMEOUT\)$")
        self.assertIn("1 errors", out)
        self.assertNotIn("10.1.2.3", out)

    async def test_a_raised_tool_error_is_counted_without_its_message(self):
        with self.assertLogs("fastmcp", "ERROR"):  # the fake server logs the traceback; keep it off the console
            rc, out = await self.run_main("time", "--calls", self.calls_file([{"tool": "boom", "params": {}}]))
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"(?m)^  ERR +\d+ ms  boom  \(tool error\)$")
        self.assertNotIn("10.1.2.3", out)

    async def test_a_transport_failure_is_counted_and_the_run_continues(self):
        calls = self.calls_file([{"tool": "ok_tool", "params": {}}, {"tool": "ok_tool", "params": {}}])
        real = self.factory
        seen = []

        def flaky(args):
            seen.append(1)
            if len(seen) == 1:
                raise ConnectionError("connect to 10.1.2.3 refused")
            return real(args)

        self.factory = flaky
        rc, out = await self.run_main("time", "--calls", calls, "--fresh")
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"(?m)^  ERR +\d+ ms  ok_tool  \(ConnectionError\)$")
        self.assertRegex(out, r"(?m)^  ok +\d+ ms  ok_tool$")
        self.assertNotIn("10.1.2.3", out)

    async def test_over_budget_fails(self):
        rc, out = await self.run_main("time", "--budget-ms", "1", "--calls", self.calls_file(
            [{"tool": "slow", "params": {"ms": 30}}]))
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"(?m)^  SLOW +\d+ ms  slow$")
        self.assertIn("1 over 1 ms", out)

    async def test_parallel_runs_calls_concurrently(self):
        rc, out = await self.run_main("time", "--parallel", "5", "--calls", self.calls_file(
            [{"tool": "slow", "params": {"ms": 100}}] * 5))
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.state.peak, 5)
        self.assertIn("5 calls (5 parallel)", out)

    async def test_parallel_is_capped(self):
        await self.run_main("time", "--parallel", "2", "--calls", self.calls_file(
            [{"tool": "slow", "params": {"ms": 50}}] * 6))
        self.assertEqual(self.state.peak, 2)

    async def test_shared_session_by_default(self):
        await self.run_main("time", "--repeat", "3", "--calls", self.calls_file([{"tool": "ok_tool", "params": {}}]))
        self.assertEqual(self.state.clients, 1)

    async def test_fresh_opens_one_session_per_call(self):
        # Through the Gateway every tool call is a new Runtime session; --fresh times that path directly.
        rc, out = await self.run_main("time", "--fresh", "--repeat", "3", "--calls",
                                      self.calls_file([{"tool": "ok_tool", "params": {}}]))
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.state.clients, 3)
        self.assertIn("3 calls (1 parallel, fresh session each)", out)

    async def test_prefix_is_prepended(self):
        rc, out = await self.run_main("time", "--prefix", "doris___", "--calls",
                                      self.calls_file([{"tool": "ok_tool", "params": {}}]))
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"(?m)^  ok +\d+ ms  doris___ok_tool$")

    async def test_bad_calls_file_is_a_usage_error(self):
        for calls in ({"tool": "ok_tool"}, [{"params": {}}], [{"tool": "ok_tool", "params": []}]):
            with self.subTest(calls=calls):
                rc, out = await self.run_main("time", "--calls", self.calls_file(calls))
                self.assertEqual(rc, 2)
                self.assertEqual(self.state.clients, 0)

    async def test_bad_parallel_or_repeat_is_a_usage_error(self):
        for option in ("--parallel", "--repeat"):
            with self.subTest(option=option), self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    await self.run_main("time", option, "0")


class TestShippedCalls(unittest.TestCase):
    def test_one_read_only_call_per_server_tool(self):
        calls = mcp_smoke.load_calls(SHIPPED_CALLS)
        self.assertEqual({c["tool"] for c in calls}, {
            "get_query_guide", "list_databases", "list_tables", "describe_table", "execute_query",
            "check_service_health", "list_metrics", "list_dimensions_for_metric", "query_metric",
            "reload_semantic_layer", "list_recent_queries", "get_query_profile"})
        self.assertEqual(len(calls), 12)
        sql = [c["params"]["sql"] for c in calls if c["tool"] == "execute_query"]
        self.assertEqual(len(sql), 1)
        self.assertRegex(sql[0], r"^SELECT ")


class TestConns(_SmokeCase):
    async def test_counts_only_never_hosts_or_statements(self):
        rc, out = await self.run_main("conns")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.state.sql, ["SHOW PROCESSLIST"])
        self.assertIn("connections: 3 (Query 1, Sleep 2) from 2 distinct hosts; users mcp_svc; max idle 42 s", out)
        self.assertIsNone(re.search(r"\d+\.\d+\.\d+\.\d+", out), out)
        self.assertNotIn("SHOW PROCESSLIST", out)

    async def test_expected_host_prefix(self):
        rc, out = await self.run_main("conns", "--expect-host-prefix", "172.31.")
        self.assertEqual(rc, 0, out)
        self.assertIn("[PASS] host prefix 172.31.: 3/3 connections", out)

    async def test_a_connection_from_elsewhere_fails_the_prefix_check(self):
        self.state.processlist.append({"Id": 14, "User": "mcp_svc", "Host": "203.0.113.9:5000",
                                       "Command": "Sleep", "Time": "3", "Info": ""})
        rc, out = await self.run_main("conns", "--expect-host-prefix", "172.31.")
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] host prefix 172.31.: 3/4 connections", out)
        self.assertNotIn("203.0.113.9", out)

    async def test_max_idle(self):
        rc, out = await self.run_main("conns", "--max-idle", "40")
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] idle connections <= 40 s: 1 over", out)
        rc, out = await self.run_main("conns", "--max-idle", "600")
        self.assertEqual(rc, 0, out)
        self.assertIn("[PASS] idle connections <= 600 s: 0 over", out)

    async def test_query_error_fails_with_its_code_only(self):
        self.state.processlist = None
        rc, out = await self.run_main("conns", "--prefix", "")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: SHOW PROCESSLIST: CONNECTION_ERROR", out)
        self.assertNotIn("10.1.2.3", out)


class TestSigV4Option(unittest.TestCase):
    def _parse_error(self, *argv: str) -> None:
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            mcp_smoke.parse_args(list(argv))
        self.assertEqual(cm.exception.code, 2)

    def test_sigv4_needs_url(self):
        self._parse_error("--stdio", "server", "--sigv4", "list")

    def test_sigv4_excludes_a_bearer_token(self):
        self._parse_error("--url", "https://x/mcp", "--sigv4", "--bearer-env", "GW_TOKEN", "list")

    def test_sigv4_client_gets_url_region_and_timeout(self):
        args = mcp_smoke.parse_args(["--url", "https://x/mcp", "--sigv4", "--region", "us-east-1",
                                     "--timeout", "30", "list"])
        import agentcore_client
        with mock.patch.object(agentcore_client, "sigv4_client", return_value="client") as factory:
            self.assertEqual(mcp_smoke.build_client(args), "client")
        factory.assert_called_once_with("https://x/mcp", "us-east-1", timeout=30.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

`doris/test/test_reconcile.py`：
- 新增 `Remote` 测试类；
- `run_main` 多传一个 `remote_client_factory`，现有测试全部经过它。

```bash
git apply <<'PATCH'
diff --git a/doris/test/test_reconcile.py b/doris/test/test_reconcile.py
index ae5563f..54da637 100644
--- a/doris/test/test_reconcile.py
+++ b/doris/test/test_reconcile.py
@@ -116,7 +116,7 @@ def ok(data, meta=None):
     return {"success": True, "data": data, **({"meta": meta} if meta else {})}
 
 
-def run_main(argv, env=ENV, conn=None, connect=None, client=None, factory=None):
+def run_main(argv, env=ENV, conn=None, connect=None, client=None, factory=None, remote=None):
     out, err, seen = io.StringIO(), io.StringIO(), {}
 
     def fake_connect(**kwargs):
@@ -124,10 +124,15 @@ def run_main(argv, env=ENV, conn=None, connect=None, client=None, factory=None):
         return conn
 
     rc = reconcile.main(argv, env=env, connect=connect or fake_connect, out=out, err=err,
-                        client_factory=factory or ((lambda settings: client) if client else None))
+                        client_factory=factory or ((lambda settings: client) if client else None),
+                        remote_client_factory=remote)
     return rc, out.getvalue(), err.getvalue(), seen
 
 
+RUNTIME_URL = ("https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1"
+               "%3A111122223333%3Aruntime%2Fdorismcp_dorismcp-AbCdEf1234/invocations?qualifier=DEFAULT")
+
+
 class Normalize(unittest.TestCase):
     def test_values_are_encoded_like_the_mcp_response(self):
         # Mirrors core.response._Encoder, so direct rows and MCP rows compare alike.
@@ -412,5 +417,71 @@ class Main(unittest.TestCase):
                 self.assertNotIn("10.0.0.1", out + err)
 
 
+class Remote(unittest.TestCase):
+    """mcp --url: the deployed Runtime over SigV4 (P3 / T3.3); the reference SQL still runs on pymysql."""
+
+    def _client(self):
+        names = sorted(local_metric_names(MODELS))
+        return FakeClient({"list_metrics": ok([{"name": n, "description": "d"} for n in names],
+                                              {"total_count": len(names)}),
+                           "query_metric": ok({"columns": list(YTD_ROW), "rows": [json.loads(
+                               json.dumps(YTD_ROW, default=float))]})})
+
+    def test_url_reconciles_against_the_deployed_runtime(self):
+        client, seen = self._client(), []
+
+        def remote(url, region):
+            seen.append((url, region))
+            return client
+
+        def in_process(_settings):
+            raise AssertionError("--url must not start an in-process server")
+
+        conn = FakeConn([YTD_ROW])
+        rc, out, err, kwargs = run_main(["mcp", "--url", RUNTIME_URL, "--case", "ytd_totals"], conn=conn,
+                                        factory=in_process, remote=remote)
+        self.assertEqual(rc, 0, out + err)
+        self.assertEqual(seen, [(RUNTIME_URL, None)])
+        self.assertEqual([c[0] for c in client.calls], ["list_metrics", "query_metric"])
+        self.assertEqual(len(conn.executed), 1)  # the reference SQL, as the load_settings account
+        self.assertEqual(kwargs["user"], "demo_ro")
+        self.assertIn("1/1 cases match", out)
+
+    def test_region_is_passed_through(self):
+        seen = []
+        client = self._client()
+        run_main(["mcp", "--url", RUNTIME_URL, "--region", "us-east-1", "--case", "ytd_totals"],
+                 conn=FakeConn([YTD_ROW]), remote=lambda url, region: seen.append(region) or client)
+        self.assertEqual(seen, ["us-east-1"])
+
+    def test_url_and_region_are_mcp_mode_options(self):
+        for argv in (["direct", "--url", RUNTIME_URL], ["mcp", "--region", "us-east-1"]):
+            with self.subTest(argv=argv):
+                rc, _, err, kwargs = run_main(argv, conn=FakeConn([]))
+                self.assertEqual(rc, 2)
+                self.assertIn("ERROR:", err)
+                self.assertEqual(kwargs, {})  # rejected before connecting to Doris
+
+    def test_remote_setup_error_is_one_masked_line(self):
+        def remote(_url, _region):
+            raise RuntimeError("no AWS credentials found (set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)")
+
+        conn = FakeConn([YTD_ROW])
+        rc, out, err, _ = run_main(["mcp", "--url", RUNTIME_URL], conn=conn, remote=remote)
+        self.assertEqual(rc, 1)
+        self.assertEqual([line for line in err.splitlines() if line.startswith("FAILED:")],
+                         ["FAILED: RuntimeError: no AWS credentials found (set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)"])
+        self.assertNotIn("Traceback", out + err)
+        self.assertTrue(conn.closed)
+
+    def test_default_remote_client_is_the_sigv4_client(self):
+        sys.path.insert(0, str(ROOT / "scripts"))
+        import agentcore_client
+
+        with mock.patch.object(agentcore_client, "sigv4_client", return_value="client") as sigv4:
+            self.assertEqual(reconcile._remote_client(RUNTIME_URL, "us-east-1"), "client")
+        sigv4.assert_called_once_with(RUNTIME_URL, "us-east-1")
+
+
 if __name__ == "__main__":
     unittest.main()
PATCH
```

- [ ] **Step 3：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s scripts/test > /tmp/t33-red-scripts.log 2>&1
grep -E '^(FAIL|ERROR):' /tmp/t33-red-scripts.log | sed -E 's/ \(.*//' | sort -u
grep -E '^Ran|^FAILED|^OK' /tmp/t33-red-scripts.log
.venv/bin/python -m unittest discover -s doris/test > /tmp/t33-red-doris.log 2>&1
grep -E '^(FAIL|ERROR):' /tmp/t33-red-doris.log | sed -E 's/ \(.*//' | sort -u
grep -E '^Ran|^FAILED|^OK' /tmp/t33-red-doris.log
```
期望：
```
ERROR: test_a_connection_from_elsewhere_fails_the_prefix_check
ERROR: test_a_raised_tool_error_is_counted_without_its_message
ERROR: test_a_tool_error_fails_the_run_with_its_code_only
ERROR: test_a_transport_failure_is_counted_and_the_run_continues
ERROR: test_agentcore_client
ERROR: test_all_ok_within_budget
ERROR: test_audit_check
ERROR: test_bad_calls_file_is_a_usage_error
ERROR: test_bad_parallel_or_repeat_is_a_usage_error
ERROR: test_counts_only_never_hosts_or_statements
ERROR: test_expected_host_prefix
ERROR: test_fresh_opens_one_session_per_call
ERROR: test_max_idle
ERROR: test_one_read_only_call_per_server_tool
ERROR: test_over_budget_fails
ERROR: test_parallel_is_capped
ERROR: test_parallel_runs_calls_concurrently
ERROR: test_prefix_is_prepended
ERROR: test_query_error_fails_with_its_code_only
ERROR: test_shared_session_by_default
ERROR: test_sigv4_client_gets_url_region_and_timeout
ERROR: test_sigv4_excludes_a_bearer_token
ERROR: test_sigv4_needs_url
Ran 32 tests in …s
FAILED (errors=26)
ERROR: test_connect_error_is_masked
ERROR: test_default_remote_client_is_the_sigv4_client
ERROR: test_direct_runs_compiled_and_reference_sql_on_one_connection
ERROR: test_mcp_checks_published_metrics_then_reconciles
ERROR: test_mcp_fails_when_published_metrics_differ
ERROR: test_missing_host_is_a_usage_error
ERROR: test_region_is_passed_through
ERROR: test_remote_setup_error_is_one_masked_line
ERROR: test_setup_errors_are_one_masked_line_without_traceback
ERROR: test_unexpected_case_error_fails_only_that_case_and_is_masked
ERROR: test_unknown_case_is_a_usage_error
ERROR: test_url_and_region_are_mcp_mode_options
ERROR: test_url_reconciles_against_the_deployed_runtime
Ran 130 tests in …s
FAILED (errors=14)
```
`scripts/test` 的失败原因：
- `test_agentcore_client`、`test_audit_check` 两行是模块导入失败（`ModuleNotFoundError`）；
- 其余 21 个名字是 `mcp_smoke.py` 还没有 `--sigv4`、`time`、`conns`、`load_calls`，`main()` 也不接受 `client_factory`；
- `test_bad_calls_file_is_a_usage_error`（3 个 subTest）和 `test_bad_parallel_or_repeat_is_a_usage_error`（2 个 subTest）经 `sort -u` 各合并成一行，所以总数是 26；
- 没有失败的 9 个是 T3.1 的 render 测试。

`doris/test` 的 14 个 ERROR 都是 `TypeError`：`main()` 还不接受 `remote_client_factory`，现有的 8 个 `main` 测试也经过 `run_main`，所以一起报错。`test_url_and_region_are_mcp_mode_options` 有 2 个 subTest。

- [ ] **Step 4：实现**

新建 `scripts/agentcore_client.py`：

新建 `scripts/agentcore_client.py`：

```python
"""SigV4-signed MCP client for an AgentCore Runtime invoke URL (inbound auth AWS_IAM).

    from agentcore_client import sigv4_client
    async with sigv4_client(runtime_url) as client:
        await client.list_tools()

Credentials come from the default botocore chain (here: the AWS_* environment variables) and are
re-read before each request, so refreshed session credentials are picked up. The region comes from
the URL unless given: this dev box sets AWS_DEFAULT_REGION=us-west-2, the Runtime is in us-east-1.
One Client is one MCP session (Mcp-Session-Id), i.e. one Runtime microVM; the Gateway opens a new
session for every tool call.
"""

from __future__ import annotations

import re
from typing import Generator

import botocore.session
import httpx
from botocore.auth import SigV4Auth as _BotoSigV4Auth
from botocore.awsrequest import AWSRequest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

SERVICE = "bedrock-agentcore"
# botocore already skips hop-by-hop headers and user-agent; accept-encoding is set by httpx and
# may be rewritten on the way, so it is not signed either.
_UNSIGNED = frozenset({"accept-encoding"})
_REGION_RE = re.compile(r"^https://bedrock-agentcore\.([a-z0-9-]+)\.amazonaws\.com/")


def region_from_url(url: str) -> str | None:
    m = _REGION_RE.match(url)
    return m.group(1) if m else None


class SigV4Auth(httpx.Auth):
    """httpx auth that signs every request (body included) for bedrock-agentcore."""

    requires_request_body = True

    def __init__(self, region: str, credentials=None, service: str = SERVICE):
        self._region, self._service = region, service
        self._credentials = credentials or botocore.session.get_session().get_credentials()
        if self._credentials is None:
            raise RuntimeError("no AWS credentials found (set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)")

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _UNSIGNED}
        aws = AWSRequest(method=request.method, url=str(request.url), data=request.content, headers=headers)
        _BotoSigV4Auth(self._credentials.get_frozen_credentials(), self._service, self._region).add_auth(aws)
        for name in ("Authorization", "X-Amz-Date", "X-Amz-Security-Token"):
            if name in aws.headers:
                request.headers[name] = aws.headers[name]
        yield request


def sigv4_client(url: str, region: str | None = None, timeout: float = 90.0) -> Client:
    region = region or region_from_url(url)
    if not region:
        raise ValueError(f"cannot tell the region from {url!r}; pass --region")
    return Client(StreamableHttpTransport(url, auth=SigV4Auth(region)), timeout=timeout)
```

`scripts/audit_check.py`：

新建 `scripts/audit_check.py`：

```python
#!/usr/bin/env python3
"""Count the doris_new_mcp.audit records in `aws logs filter-log-events` output (P3 / T3.3, R-32).

  aws logs filter-log-events --region us-east-1 --log-group-name "$LOG_GROUP" --start-time "$SINCE_MS" \\
      --filter-pattern '"doris_new_mcp.audit"' --output json \\
    | .venv/bin/python scripts/audit_check.py --calls scripts/smoke_calls.json --repeat 2

Prints counts per tool and outcome only: never params, SQL, error text or client ids.
Exit code: 0 when every expected call is audited, 1 when some are missing or a record is unreadable,
2 when the input is not filter-log-events JSON.
"""

import argparse
import json
import sys
from collections import Counter

from mcp_smoke import load_calls

MARKER = "doris_new_mcp.audit: "


def parse_records(doc: dict) -> tuple[list[dict], int]:
    """The audit records of the log events, and how many audit lines could not be read."""
    records, unreadable = [], 0
    for event in doc.get("events") or []:
        message = str(event.get("message", ""))
        at = message.find(MARKER)
        if at < 0:
            continue
        try:
            record = json.loads(message[at + len(MARKER):])
        except ValueError:
            record = None
        if isinstance(record, dict) and isinstance(record.get("tool"), str):
            records.append(record)
        else:
            unreadable += 1
    return records, unreadable


def main(argv: list[str] | None = None, stdin=sys.stdin, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--calls", help="calls file of the smoke run (scripts/smoke_calls.json format)")
    parser.add_argument("--repeat", type=int, default=1, help="how many times the smoke run made each call")
    args = parser.parse_args(argv)

    def say(line: str) -> None:
        print(line, file=out)

    try:
        doc = json.load(stdin)
        if not isinstance(doc, dict):
            raise ValueError
    except ValueError:
        say("FAIL: input is not filter-log-events JSON (aws logs filter-log-events --output json)")
        return 2
    expected: Counter = Counter()
    if args.calls:
        for call in load_calls(args.calls):
            expected[call["tool"]] += args.repeat

    records, unreadable = parse_records(doc)
    ok = Counter(r["tool"] for r in records if r.get("success") is True)
    failed = Counter(r["tool"] for r in records if r.get("success") is not True)
    say(f"audit: {len(records)} records ({ok.total()} ok, {failed.total()} failed), {unreadable} unreadable")
    for tool in sorted(set(ok) | set(failed) | set(expected)):
        say(f"  {tool:<28} {ok[tool]:>3} ok {failed[tool]:>3} failed"
            + (f"  (expected >= {expected[tool]})" if tool in expected else ""))

    passed = True
    if expected:
        short = {t: n for t, n in sorted(expected.items()) if ok[t] + failed[t] < n}
        passed = not short
        detail = ", ".join(f"{t} {ok[t] + failed[t]}/{n}" for t, n in short.items())
        say(f"  [{'PASS' if passed else 'FAIL'}] every expected call audited: {len(expected) - len(short)}/"
            f"{len(expected)} tools" + (f" (short: {detail})" if short else ""))
    if unreadable:
        passed = False
        say(f"  [FAIL] unreadable audit records: {unreadable}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/smoke_calls.json`：
- 12 个只读调用；
- `get_query_profile` 用一个格式合法但不存在的 query_id（`profile_found=false`，不是错误）；
- `reload_semantic_layer` 只从 Doris 重新读取已发布的语义层，不写任何东西。

新建 `scripts/smoke_calls.json`：

```json
[
  {"tool": "get_query_guide", "params": {}},
  {"tool": "check_service_health", "params": {}},
  {"tool": "list_databases", "params": {}},
  {"tool": "list_tables", "params": {"database": "ecom"}},
  {"tool": "describe_table", "params": {"database": "ecom", "table": "fact_order"}},
  {"tool": "execute_query", "params": {"sql": "SELECT COUNT(*) AS n FROM ecom.fact_order"}},
  {"tool": "list_metrics", "params": {"workspace": "ecom"}},
  {"tool": "list_dimensions_for_metric", "params": {"workspace": "ecom", "metric_name": "gmv"}},
  {"tool": "query_metric", "params": {"workspace": "ecom", "metrics": ["gmv"], "group_by": ["metric_time__month"],
                                      "where": "metric_time >= '2026-01-01'"}},
  {"tool": "reload_semantic_layer", "params": {"workspace": "ecom"}},
  {"tool": "list_recent_queries", "params": {"limit": 5}},
  {"tool": "get_query_profile", "params": {"query_id": "ffffffffffffffff-ffffffffffffffff"}}
]
```

`scripts/mcp_smoke.py` 加 `--sigv4`、`time`、`conns`；`doris/reconcile.py` 加 `--url` / `--region`：

```bash
git apply <<'PATCH'
diff --git a/doris/reconcile.py b/doris/reconcile.py
index 199b09d..fc1b6d1 100644
--- a/doris/reconcile.py
+++ b/doris/reconcile.py
@@ -2,11 +2,14 @@
 
     python doris/reconcile.py direct [--models DIR] [--case NAME ...]   # compile the local YAML, run via pymysql
     python doris/reconcile.py mcp [--workspace ecom] [--case NAME ...]  # in-process MCP server: list_metrics + query_metric
+    python doris/reconcile.py mcp --url "$RUNTIME_URL" [--region R]    # the deployed Runtime over SigV4 (P3)
 
 Connection: agentcore_ext.settings.load_settings(os.environ) -- DORIS_HOST, DORIS_PORT and either
 DORIS_SECRET_ID or DORIS_USER/DORIS_PASSWORD. Every statement is a SELECT; the MCP server may run its
 CREATE ... IF NOT EXISTS on system_mcp. Each case runs the metric query and a hand-written reference
 SQL (column aliases = the semantic output columns) and compares the rows by the group-by key.
+With --url the metric queries go to the deployed Runtime (AWS_* credentials); the reference SQL still
+runs over pymysql as the load_settings account.
 Exit 0 when every case matches, 1 on a mismatch or runtime error, 2 on usage/configuration errors.
 """
 
@@ -329,6 +332,16 @@ def _in_process_client(settings: Settings) -> Any:
     return Client(build_server(settings))
 
 
+def _remote_client(url: str, region: str | None) -> Any:
+    """fastmcp Client for a Runtime invoke URL (inbound auth AWS_IAM), see scripts/agentcore_client.py."""
+    scripts = str(ROOT / "scripts")
+    if scripts not in sys.path:
+        sys.path.insert(0, scripts)
+    import agentcore_client
+
+    return agentcore_client.sigv4_client(url, region)
+
+
 async def _run_mcp(client: Any, models_dir: Path, workspace: str, cases: Sequence[Case],
                    reference: Callable[[Case], list[dict[str, Any]]], out: TextIO, secrets: Sequence[str]) -> int:
     expected = local_metric_names(models_dir)
@@ -348,13 +361,22 @@ async def _run_mcp(client: Any, models_dir: Path, workspace: str, cases: Sequenc
 
 def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None,
          connect: Callable[..., Any] = pymysql.connect, out: TextIO = sys.stdout, err: TextIO = sys.stderr,
-         client_factory: Callable[[Settings], Any] | None = None) -> int:
+         client_factory: Callable[[Settings], Any] | None = None,
+         remote_client_factory: Callable[[str, str | None], Any] | None = None) -> int:
     parser = argparse.ArgumentParser(description="Reconcile ecom semantic metrics with the storyline SQL.")
     parser.add_argument("mode", choices=("direct", "mcp"))
     parser.add_argument("--models", type=Path, default=MODELS_DIR, help="local semantic YAML directory")
     parser.add_argument("--workspace", default="ecom", help="MCP workspace (mcp mode)")
     parser.add_argument("--case", action="append", default=[], help="run only this case (repeatable)")
+    parser.add_argument("--url", help="mcp mode: the deployed Runtime's invoke URL (SigV4) instead of in-process")
+    parser.add_argument("--region", help="mcp --url: SigV4 region (default: taken from the URL)")
     args = parser.parse_args(argv)
+    if args.url and args.mode != "mcp":
+        print("ERROR: --url only applies to mcp mode", file=err)
+        return 2
+    if args.region and not args.url:
+        print("ERROR: --region only applies with --url", file=err)
+        return 2
 
     cases = list(CASES)
     if args.case:
@@ -389,6 +411,9 @@ def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
             if args.mode == "direct":
                 backend = DirectBackend(args.models, tmp, fetch=lambda sql: fetch(conn, sql))
                 failed = asyncio.run(reconcile(cases, backend.query, reference, out, secrets))
+            elif args.url:
+                client = (remote_client_factory or _remote_client)(args.url, args.region)
+                failed = asyncio.run(_run_mcp(client, args.models, args.workspace, cases, reference, out, secrets))
             else:
                 # A fresh workspace dir, so the server reads the published models from Doris, not a cache.
                 client = (client_factory or _in_process_client)(dataclasses.replace(settings, workspace_dir=tmp))
diff --git a/scripts/mcp_smoke.py b/scripts/mcp_smoke.py
index 442cf03..194b659 100644
--- a/scripts/mcp_smoke.py
+++ b/scripts/mcp_smoke.py
@@ -7,9 +7,13 @@ Examples:
   mcp_smoke.py --stdio "uvx mcp-proxy-for-aws@latest $RUNTIME_URL --service bedrock-agentcore --region us-east-1" list
   mcp_smoke.py --url http://127.0.0.1:8000/mcp flow                       # profile flow + error cases
   mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN flow --prefix doris___
+  mcp_smoke.py --url "$RUNTIME_URL" --sigv4 list --expect 12          # Runtime directly, AWS_IAM inbound auth
+  mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN time --prefix doris___ --parallel 20 --repeat 2
+  mcp_smoke.py --url "$RUNTIME_URL" --sigv4 conns --expect-host-prefix 172.31.
 
-The bearer token is read from the named environment variable and never printed.
-Exit code: 0 on success, 1 when a tool call returns an error or a check fails.
+The bearer token is read from the named environment variable and never printed. `time` and `conns`
+print status, timings, error codes and counts only: never tool output, SQL results, hosts or statements.
+Exit code: 0 on success, 1 when a tool call returns an error or a check fails, 2 on a bad calls file.
 """
 
 import argparse
@@ -20,12 +24,20 @@ import secrets
 import shlex
 import sys
 import time
+from collections import Counter
+from pathlib import Path
 
 from fastmcp import Client
 from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
 
+DEFAULT_CALLS = Path(__file__).resolve().parent / "smoke_calls.json"
+
 
 def build_client(args: argparse.Namespace) -> Client:
+    if args.sigv4:
+        import agentcore_client  # scripts/ is on sys.path when this file is run as a script
+
+        return agentcore_client.sigv4_client(args.url, args.region, timeout=args.timeout)
     if args.url:
         headers = {}
         if args.bearer_env:
@@ -119,15 +131,141 @@ async def cmd_flow(client: Client, args: argparse.Namespace) -> int:
     return 0 if all(results) else 1
 
 
-COMMANDS = {"list": cmd_list, "call": cmd_call, "flow": cmd_flow}
+def load_calls(path: str | Path) -> list[dict]:
+    """[{"tool": NAME, "params": {...}}, ...]; ValueError on any other shape."""
+    calls = json.loads(Path(path).read_text())
+    if not isinstance(calls, list) or not calls:
+        raise ValueError("calls file must be a non-empty JSON list")
+    for i, call in enumerate(calls, 1):
+        if not (isinstance(call, dict) and isinstance(call.get("tool"), str) and call["tool"]
+                and isinstance(call.get("params"), dict)):
+            raise ValueError(f"calls file entry {i} needs a tool name and a params object")
+    return calls
+
+
+def _percentile(sorted_ms: list[int], pct: int) -> int:
+    return sorted_ms[max(0, -(-len(sorted_ms) * pct // 100) - 1)]  # nearest rank
+
+
+async def _timed_call(client: Client, tool: str, params: dict) -> str | None:
+    """None when the call succeeded, else a short reason (error code or exception type, never a message)."""
+    result = await client.call_tool(tool, params, raise_on_error=False)
+    payload = result_payload(result)
+    body = payload if isinstance(payload, dict) else {}
+    if result.is_error:
+        return error_code(body) or "tool error"
+    if body.get("success") is False:
+        return error_code(body) or "success=false"
+    return None
+
+
+async def cmd_time(args: argparse.Namespace, client_factory) -> int:
+    """Time every call of the calls file; fail on an error or a call over --budget-ms."""
+    try:
+        calls = load_calls(args.calls)
+    except (OSError, ValueError) as e:
+        print(f"FAIL: {type(e).__name__}: {e}")
+        return 2
+    work = [(f"{args.prefix}{c['tool']}", c["params"]) for _ in range(args.repeat) for c in calls]
+    gate = asyncio.Semaphore(args.parallel)
+    timings: list[int] = []
+    errors = slow = 0
+
+    async def one(shared: Client | None, tool: str, params: dict) -> None:
+        nonlocal errors, slow
+        async with gate:
+            start = time.monotonic()
+            try:
+                if shared is not None:
+                    reason = await _timed_call(shared, tool, params)
+                else:  # a new MCP session per call, as the Gateway does; connect + initialize are timed too
+                    async with client_factory(args) as client:
+                        reason = await _timed_call(client, tool, params)
+            except Exception as e:  # noqa: BLE001 - counted and reported by type only
+                reason = type(e).__name__
+            ms = round((time.monotonic() - start) * 1000)
+        timings.append(ms)
+        if reason is not None:
+            errors += 1
+            status = "ERR"
+        elif ms > args.budget_ms:
+            slow += 1
+            status = "SLOW"
+        else:
+            status = "ok"
+        print(f"  {status:<4} {ms:>6} ms  {tool}" + (f"  ({reason})" if reason else ""), flush=True)
+
+    start = time.monotonic()
+    if args.fresh:
+        await asyncio.gather(*(one(None, tool, params) for tool, params in work))
+    else:
+        try:
+            async with client_factory(args) as client:
+                print(f"connected+initialized in {round((time.monotonic() - start) * 1000)} ms")
+                await asyncio.gather(*(one(client, tool, params) for tool, params in work))
+        except Exception as e:  # noqa: BLE001 - never print the message: it may carry a host
+            print(f"FAIL: session: {type(e).__name__}")
+            return 1
+    ordered = sorted(timings)
+    mode = f"{args.parallel} parallel" + (", fresh session each" if args.fresh else "")
+    print(f"time: {len(work)} calls ({mode}), {errors} errors, {slow} over {args.budget_ms} ms; "
+          f"p50 {_percentile(ordered, 50)} ms, p95 {_percentile(ordered, 95)} ms, max {ordered[-1]} ms; "
+          f"wall {round((time.monotonic() - start) * 1000)} ms")
+    return 1 if errors or slow else 0
+
+
+async def cmd_conns(client: Client, args: argparse.Namespace) -> int:
+    """The service account's Doris connections, as counts (a non-admin sees only its own)."""
+    body = await call_json(client, f"{args.prefix}execute_query", {"sql": "SHOW PROCESSLIST"})
+    if body.get("success") is not True:
+        print(f"FAIL: SHOW PROCESSLIST: {error_code(body) or 'no result'}")
+        return 1
+    rows = (body.get("data") or {}).get("rows") or []
+
+    def seconds(row: dict) -> int:
+        try:
+            return int(float(row.get("Time") or 0))
+        except (TypeError, ValueError):
+            return 0
+
+    commands = Counter(str(r.get("Command")) for r in rows)
+    hosts = {str(r.get("Host", "")).rsplit(":", 1)[0] for r in rows}
+    users = sorted({str(r.get("User")) for r in rows})
+    idle = [seconds(r) for r in rows if r.get("Command") == "Sleep"]
+    print(f"connections: {len(rows)} (" + ", ".join(f"{k} {v}" for k, v in sorted(commands.items()))
+          + f") from {len(hosts)} distinct hosts; users {', '.join(users) or '-'}; max idle {max(idle, default=0)} s")
+    ok = True
+    if args.expect_host_prefix is not None:
+        matched = sum(str(r.get("Host", "")).startswith(args.expect_host_prefix) for r in rows)
+        passed = bool(rows) and matched == len(rows)
+        ok &= passed
+        print(f"  [{'PASS' if passed else 'FAIL'}] host prefix {args.expect_host_prefix}: {matched}/{len(rows)} connections")
+    if args.max_idle is not None:
+        over = sum(s > args.max_idle for s in idle)
+        ok &= over == 0
+        print(f"  [{'PASS' if over == 0 else 'FAIL'}] idle connections <= {args.max_idle} s: {over} over")
+    return 0 if ok else 1
 
 
-async def main(argv: list[str] | None = None) -> int:
+COMMANDS = {"list": cmd_list, "call": cmd_call, "flow": cmd_flow, "conns": cmd_conns}
+
+
+def _positive_int(value: str) -> int:
+    n = int(value)
+    if n < 1:
+        raise argparse.ArgumentTypeError(f"must be >= 1, got {n}")
+    return n
+
+
+def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
     parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
     target = parser.add_mutually_exclusive_group(required=True)
     target.add_argument("--url", help="streamable HTTP MCP endpoint")
     target.add_argument("--stdio", help="command line of a stdio MCP server / proxy")
     parser.add_argument("--bearer-env", help="env var holding a bearer token (HTTP only)")
+    parser.add_argument("--sigv4", action="store_true",
+                        help="sign requests with SigV4 for bedrock-agentcore (a Runtime invoke URL, AWS_* credentials)")
+    parser.add_argument("--region", help="SigV4 region (default: taken from the --url host)")
     parser.add_argument("--timeout", type=float, default=90.0, help="per-request timeout seconds")
     sub = parser.add_subparsers(dest="command", required=True)
     p_list = sub.add_parser("list", help="list tools")
@@ -139,12 +277,36 @@ async def main(argv: list[str] | None = None) -> int:
     p_flow.add_argument("--prefix", default="", help="tool name prefix, e.g. doris___ through the Gateway")
     p_flow.add_argument("--table", default="ecom.fact_order", help="table the profiled COUNT(*) reads")
     p_flow.add_argument("--wait", type=float, default=15.0, help="seconds to wait for the profile to appear")
+    p_time = sub.add_parser("time", help="time each call of a calls file (P3 latency / concurrency checks)")
+    p_time.add_argument("--calls", default=str(DEFAULT_CALLS), help="JSON list of {tool, params} (default: %(default)s)")
+    p_time.add_argument("--prefix", default="", help="tool name prefix, e.g. doris___ through the Gateway")
+    p_time.add_argument("--parallel", type=_positive_int, default=1, help="calls in flight at once")
+    p_time.add_argument("--repeat", type=_positive_int, default=1, help="run the calls file N times")
+    p_time.add_argument("--fresh", action="store_true", help="new MCP session per call (timed with connect)")
+    p_time.add_argument("--budget-ms", type=int, default=60000, help="fail any call slower than this")
+    p_conns = sub.add_parser("conns", help="count the service account's Doris connections (SHOW PROCESSLIST)")
+    p_conns.add_argument("--prefix", default="", help="tool name prefix, e.g. doris___ through the Gateway")
+    p_conns.add_argument("--expect-host-prefix", help="fail unless every connection comes from hosts with this prefix")
+    p_conns.add_argument("--max-idle", type=int, help="fail if any idle (Sleep) connection is older than N seconds")
     args = parser.parse_args(argv)
+    if args.sigv4 and not args.url:
+        parser.error("--sigv4 needs --url")
+    if args.sigv4 and args.bearer_env:
+        parser.error("--sigv4 and --bearer-env are mutually exclusive")
+    if args.region and not args.sigv4:
+        parser.error("--region only applies to --sigv4")
+    return args
+
 
+async def main(argv: list[str] | None = None, client_factory=build_client) -> int:
+    args = parse_args(argv)
     start = time.monotonic()
-    async with build_client(args) as client:
-        print(f"connected+initialized in {round((time.monotonic() - start) * 1000)} ms")
-        rc = await COMMANDS[args.command](client, args)
+    if args.command == "time":
+        rc = await cmd_time(args, client_factory)
+    else:
+        async with client_factory(args) as client:
+            print(f"connected+initialized in {round((time.monotonic() - start) * 1000)} ms")
+            rc = await COMMANDS[args.command](client, args)
     print(f"total {round((time.monotonic() - start) * 1000)} ms")
     return rc
 
PATCH
```

- [ ] **Step 5：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 期望：Ran 53 tests / OK
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 130 tests / OK
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 期望：Ran 89 tests / OK
bash scripts/check-secrets.sh | tail -1                                                              # 期望：check-secrets: OK (… files scanned)
git status --short
```
期望：`git status` 恰好列出 9 个文件：
- 6 个 `??`：`scripts/agentcore_client.py`、`scripts/audit_check.py`、`scripts/smoke_calls.json`，以及 `scripts/test/` 下的 3 个测试；
- 3 个 ` M`：`scripts/mcp_smoke.py`、`doris/reconcile.py`、`doris/test/test_reconcile.py`。

先提交离线部分。后面的在线检查只读，不改代码：

```bash
bash scripts/check-secrets.sh
git add scripts/agentcore_client.py scripts/audit_check.py scripts/smoke_calls.json scripts/mcp_smoke.py doris/reconcile.py \
        scripts/test/test_agentcore_client.py scripts/test/test_audit_check.py scripts/test/test_mcp_smoke.py doris/test/test_reconcile.py
git commit -m "feat(p3): T3.3 SigV4 client, mcp_smoke time / conns, audit_check, reconcile mcp --url

agentcore_client signs every request for bedrock-agentcore (region from the invoke URL, not
AWS_DEFAULT_REGION); time measures each call against Quick's 60 s budget, shared or fresh session,
N in flight; conns and audit_check print counts only.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6：SigV4 直连：工具列表和 flow**（只读）

从这一步开始记录起始时间，Step 9 按它读 CloudWatch 日志。第一次连接会启动一个新的 microVM（冷启动）。

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
date +%s000 > /tmp/t33-since0
.venv/bin/python scripts/mcp_smoke.py --url "$RUNTIME_URL" --sigv4 list --expect 12 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
.venv/bin/python scripts/mcp_smoke.py --url "$RUNTIME_URL" --sigv4 flow 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
```
期望（按本机实测推导，耗时以实际为准）：

`list` 的输出和本机一样：
```
connected+initialized in … ms
  check_service_health  [readOnly]
  describe_table  [readOnly]
  execute_query  [readOnly]
  get_query_guide  [readOnly]
  get_query_profile  [readOnly]
  list_databases  [readOnly]
  list_dimensions_for_metric  [readOnly]
  list_metrics  [readOnly]
  list_recent_queries  [readOnly]
  list_tables  [readOnly]
  query_metric  [readOnly]
  reload_semantic_layer
tools: 12
total … ms
exit=0
```

`flow` 的输出：6 行 `[PASS]`，然后 `flow: 6/6 passed`、`exit=0`。

说明：
- `connected+initialized` 是冷启动耗时。P0 的 spike 是 5516 ms；完整 server 要多加载依赖，所以会更长，记进 progress。
- 如果 `list` 报 `FAIL: session: …` 或 HTTP 403 / 424：
  1. 先确认 AWS 凭证属于账号 `890717383483`；
  2. 再按 mask 查看 Runtime 日志的末尾：`aws logs tail "/aws/bedrock-agentcore/runtimes/${RUNTIME_ID}-DEFAULT" --region us-east-1 --since 10m | tail -30 | sed -E "$MASK"`；
  3. 不要直接打印这个日志：里面有 Doris 私网 IP，见 Global Constraints。
- 关闭 session 时 Runtime 对 DELETE 返回 404，这是预期的（P0 已记录），不影响 exit。

- [ ] **Step 7：逐次耗时：共享 session 和每次新 session**（只读）

两次 `time` 各跑 `smoke_calls.json` 的 12 个调用：
- 第一次共享一个 session（同一个 microVM）；
- 第二次 `--fresh`，每次调用都新开 session，也就是一个新的 microVM。Gateway 对每次工具调用都是这样做的，所以第二次代表 Quick 的最坏情况，耗时里包含了连接和初始化。

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
sleep 5; date +%s000 > /tmp/t33-since1; sleep 2
.venv/bin/python scripts/mcp_smoke.py --url "$RUNTIME_URL" --sigv4 time 2>&1 | sed -E "$MASK" | tee /tmp/t33-time-shared.txt; echo "exit=${PIPESTATUS[0]}"
.venv/bin/python scripts/mcp_smoke.py --url "$RUNTIME_URL" --sigv4 time --fresh 2>&1 | sed -E "$MASK" | tee /tmp/t33-time-fresh.txt; echo "exit=${PIPESTATUS[0]}"
```
期望：
- 每次都是 12 行 `ok`，然后 `time: 12 calls (1 parallel), 0 errors, 0 over 60000 ms; …` 和 `time: 12 calls (1 parallel, fresh session each), 0 errors, 0 over 60000 ms; …`，两个 `exit=0`；
- 本机 server 上的共享 session 实测结果如下（Runtime 上会更慢）：

```
connected+initialized in 36 ms
  ok       13 ms  get_query_guide
  ok     1406 ms  check_service_health
  ok      181 ms  list_databases
  ok      355 ms  list_tables
  ok      356 ms  describe_table
  ok      198 ms  execute_query
  ok    11396 ms  list_metrics
  ok     1217 ms  list_dimensions_for_metric
  ok     1450 ms  query_metric
  ok     7794 ms  reload_semantic_layer
  ok      375 ms  list_recent_queries
  ok      763 ms  get_query_profile
time: 12 calls (1 parallel), 0 errors, 0 over 60000 ms; p50 375 ms, p95 11396 ms, max 11396 ms; wall 25540 ms
```

说明：
- 共享 session 里，`list_metrics` 第一次调用要加载语义层（本机 11.4 s）。`reload_semantic_layer` 会重新加载语义层（本机 7.8 s）。
- `--fresh` 时，每个用到语义层的调用（`list_metrics`、`list_dimensions_for_metric`、`query_metric`、`reload_semantic_layer`）都在新 microVM 里从头加载，是最慢的一组。
- 把两份结果的 `time:` 行记进 progress，以及 `--fresh` 下最慢的 3 个调用。
- 如果有 `SLOW` 或 `ERR`，**先停下来**，把两份输出给用户看。超过 60 s 就是 Quick 会失败的调用；这属于 design §13 的风险，要和用户商量对策（例如调大 Runtime 规格、预热，或者调整语义层的加载方式），本计划不自行处理。

- [ ] **Step 8：等待日志送达**

```bash
sleep 60
```
CloudWatch 通常在几秒内收到 stderr，这里多等一会儿，避免 Step 9 少计。

- [ ] **Step 9：CloudWatch：审计记录和泄漏计数**（只读）

```bash
source infra/state.env
LG="/aws/bedrock-agentcore/runtimes/${RUNTIME_ID}-DEFAULT"
aws logs filter-log-events --region us-east-1 --log-group-name "$LG" --start-time "$(cat /tmp/t33-since1)" \
    --filter-pattern '"doris_new_mcp.audit"' --output json \
  | .venv/bin/python scripts/audit_check.py --calls scripts/smoke_calls.json --repeat 2; echo "exit=${PIPESTATUS[1]}"
tmp=$(mktemp)
aws logs filter-log-events --region us-east-1 --log-group-name "$LG" --start-time "$(cat /tmp/t33-since0)" --output json \
  | python3 -c 'import json,sys; [print(e["message"]) for e in json.load(sys.stdin)["events"]]' > "$tmp"
grep -c 'doris_new_mcp.audit' "$tmp"
grep -cE 'Traceback| ERROR | CRITICAL ' "$tmp"
pw="$(aws secretsmanager get-secret-value --region us-east-1 --secret-id doris-mcp/mcp_svc --query SecretString --output text |
      python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')"
grep -cF -f <(printf '%s\n' "$pw") "$tmp"; unset pw
grep -cE '\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b' "$tmp"
rm -f "$tmp"
```
期望：

第一段（Step 7 两次 `time` 的 24 个调用）：
```
audit: 24 records (24 ok, 0 failed), 0 unreadable
  check_service_health           2 ok   0 failed  (expected >= 2)
  describe_table                 2 ok   0 failed  (expected >= 2)
  execute_query                  2 ok   0 failed  (expected >= 2)
  get_query_guide                2 ok   0 failed  (expected >= 2)
  get_query_profile              2 ok   0 failed  (expected >= 2)
  list_databases                 2 ok   0 failed  (expected >= 2)
  list_dimensions_for_metric     2 ok   0 failed  (expected >= 2)
  list_metrics                   2 ok   0 failed  (expected >= 2)
  list_recent_queries            2 ok   0 failed  (expected >= 2)
  list_tables                    2 ok   0 failed  (expected >= 2)
  query_metric                   2 ok   0 failed  (expected >= 2)
  reload_semantic_layer          2 ok   0 failed  (expected >= 2)
  [PASS] every expected call audited: 12/12 tools
exit=0
```

第二段的 4 个计数：
- 审计记录数：大于 24，Step 6 的 `flow` 也有审计记录；
- `0`：没有 Traceback / ERROR / CRITICAL；
- `0`：日志里没有 `mcp_svc` 的密码；
- 一个大于 0 的数：含 IPv4 字面量的日志行数。这些行包括：
  - server 的启动行 `Doris MCP for AgentCore: Doris <ip>:9030 …`；
  - `Configured private IPv4`；
  - 连接池日志；
  - httpx 访问 FE HTTP 的 URL；
  - 平台的 `/ping` 访问日志。

  Doris 私网 IP 因此会出现在 CloudWatch 里。日志组只在本账号内可见，这是已知的，已记入 design §13。这里只计数，不打印。

说明：
- 审计记录的 `success` 看的是工具的执行结果。同一个进程里两个 `reload_semantic_layer` 重叠时，后一个返回 `already_running`：客户端收到 success，审计记为 `success=false`。这是 upstream 的现有行为，spec 阶段在本机 20 个并发时见到过 1 次。Step 7 是串行的，所以期望 `0 failed`；如果出现 `reload_semantic_layer … 1 failed`，就是这个原因，不算失败。
- R-32 的一个缺口：只有工具函数执行到 `log_tool_call` 才会留下审计记录。连接池拿不到连接、请求在工具函数之前就失败时，没有审计记录。requirements v1.4 在 R-32 下加了说明，由用户决定是否在 P5 补上。
- 如果 `exit=1`（有工具少于 2 条），先等 1 分钟重跑第一段；仍然缺，就停下来查。

- [ ] **Step 10：对账：指标经 Runtime，参照 SQL 用 `demo_ro`**（只读）

参照 SQL 在本机用 `demo_ro` 执行：T3.5 之后开发机不能再以 `mcp_svc` 登录，这里先用同样的方式跑，T3.5 之后照抄重跑。

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_USER="$DORIS_RO_USER" DORIS_PASSWORD="$DORIS_RO_PASSWORD" AWS_REGION=us-east-1
  unset DORIS_ROOT_USER DORIS_ROOT_PASSWORD DORIS_RO_USER DORIS_RO_PASSWORD DORIS_ADMIN_PASSWORD
  exec .venv/bin/python doris/reconcile.py mcp --url "$RUNTIME_URL" ) 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
```
期望（与 P2 T2.6 相同）：
```
published metrics: 22 match /home/ubuntu/AI-code/Doris-mcp-skill-Demo/doris/semantic/ecom
ok    ytd_totals (1 rows)
ok    monthly_2026 (9 rows)
ok    yoy_2026 (9 rows)
ok    channel_ytd (4 rows)
ok    area_ytd (7 rows)
ok    mini_program_quarterly (7 rows)
ok    cat1_items_ytd (12 rows)
ok    brand_tier_ytd (3 rows)
ok    refund_rate_5_1 (2 rows)
ok    reviews_by_shop_type_ytd (4 rows)
ok    refunds_by_reason_ytd (10 rows)
11/11 cases match
exit=0
```

- [ ] **Step 11：Doris 连接的来源和空闲时长**（只读）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
.venv/bin/python scripts/mcp_smoke.py --url "$RUNTIME_URL" --sigv4 conns --expect-host-prefix 172.31. --max-idle 610 2>&1 \
  | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
```
期望：
```
connected+initialized in … ms
connections: N (Query 1, Sleep N-1) from M distinct hosts; users mcp_svc; max idle S s
  [PASS] host prefix 172.31.: N/N connections
  [PASS] idle connections <= 610 s: 0 over
total … ms
exit=0
```

`N`、`M`、`S` 都以实际为准：
- `N`：Step 6–10 各个 microVM 留下的连接，每个 microVM 最多 5 个（`pool_max_size`）。microVM 被销毁时不会关闭连接，由 P-09 的 `wait_timeout = 600` 让 Doris 回收；
- `M`：Runtime ENI 的地址数。

这是 `mcp_svc` 第一次从 Runtime 登录 Doris：来源全部在 `172.31.` 下，这就是 T3.5 要收紧的 host。`610` 比 `wait_timeout` 多 10 s，是给 Doris FE 周期性回收留的余量。

把 `N`、`M`、`S` 记进 progress。如果 `N` 超过 50（`max_user_connections` 的一半），先停下来：连接回收没有按预期工作。

- [ ] **Step 12：收尾**

- 勾选 T3.3。
- progress「当前状态」：T3.3 完成，下一步 T3.4。
- 日志记录：
  - Step 3 的失败数；
  - Step 5 的测试数；
  - Step 6 的冷启动耗时；
  - Step 7 的两行 `time:`，以及 `--fresh` 下最慢的 3 个调用；
  - Step 9 的审计计数和 4 个日志计数；
  - Step 10 的对账结果；
  - Step 11 的 `N`、`M`、`S`。

```bash
bash scripts/check-secrets.sh
git add specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "docs(p3): T3.3 Runtime dorismcp over SigV4: 12 tools, flow, timings, audit, reconcile 11/11

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T3.4：同步 Gateway target；经 Gateway 冒烟、耗时、并发、连接回收和 DEBUG 泄漏检查

来源：
- tasks.md T3.4、design §11 P3 行（经 Gateway 冒烟）；
- design §14：Gateway 的 `exceptionLevel=DEBUG` 在 P3 复核，结论是保留到 T5.5，本任务做泄漏检查；
- P0 M-4：耗时探针要在仓库里、可以重跑。T3.3 的 `mcp_smoke.py time` + `scripts/smoke_calls.json` 就是这个探针，本任务经 Gateway 重跑；
- P1「P3 时核对」：20 个并发对 `pool_max_size=5` 和 60 s 上限的影响。T3.3 给 `time` 加了 `--parallel`，这里经 Quick 实际走的路径来测；
- 补丁 P-09 的在线验证：残留连接在 10 分钟内被 Doris 回收。

T3.2 换了 Runtime 的代码，但 Gateway target 缓存的仍是 spike 的工具列表（`doris___net_check`）。`synchronize-gateway-targets` 让 Gateway 重新向 Runtime 要工具列表。

经 Gateway 时的行为（P0 已确认）：
- `tools/list` 由 Gateway 自己的目录回答，不访问 Runtime；
- **每次 `tools/call` 都新开一个 Runtime session**，也就是一个新的 microVM；
- 所以 Quick 的每次工具调用都要经历冷启动；用到语义层的调用还要在新 microVM 里重新加载语义层。

本任务唯一的 GATE 是 Step 3 的同步，其余步骤都是只读的。

**Files:**
- Modify：`tasks.md`、`progress.md`（本任务不改代码；`infra/state.env` 会被脚本重写，但值不变）

**Interfaces:**
- Consumes：
  - T3.2：Runtime `dorismcp_dorismcp`，`RUNTIME_ARN` 不变，所以 target 的配置不用改；
  - T3.3：
    - `scripts/mcp_smoke.py` 的 `--bearer-env`、`list --expect`、`call`、`flow --prefix --wait`、`time --prefix --parallel --repeat`、`conns --prefix --expect-host-prefix --max-idle`；
    - `scripts/smoke_calls.json`；
    - `scripts/audit_check.py --calls --repeat`；
  - P0：
    - `infra/30-gateway.sh`（`SYNC=1` 时对已有 target 调 `synchronize-gateway-targets`）；
    - `scripts/get-gw-token.sh`（Cognito client B 的 access token，只能捕获进变量，不能打印）；
    - `state.env` 的 `GW_ID=doris-mcp-gw-ryxzl0vgyv`、`GW_TARGET_ID=ENINDEEGGB`、`GW_URL`。
- Produces：
  - Gateway target `ENINDEEGGB` 的工具目录是完整 server 的 12 个工具，带前缀 `doris___`，`lastSynchronizedAt` 更新；
  - `state.env` 不变；
  - P4 让 Quick 接入这个 Gateway；T3.5 仍然 SigV4 直连 Runtime，不经过 Gateway。

- [ ] **Step 1：确认分支、工作区，记录 Gateway 和 target 的当前状态**（只读）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
git branch --show-current && git status --short
source infra/state.env
aws bedrock-agentcore-control get-gateway --region us-east-1 --gateway-identifier "$GW_ID" \
  --query '[status, exceptionLevel, description]' --output text
aws bedrock-agentcore-control get-gateway-target --region us-east-1 --gateway-identifier "$GW_ID" --target-id "$GW_TARGET_ID" \
  --query '[status, lastSynchronizedAt]' --output text | tee /tmp/t34-target-before.txt
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN list 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
unset GW_TOKEN
```
期望：
- 分支是 `p3-deploy`，工作区干净；
- `READY	DEBUG	Quick desktop -> Doris MCP (Runtime dorismcp)`；
- `READY	2026-09-26T10:34:02.796135+00:00`：spec 阶段读到的值，是 P0 建 target 的时间；
- `list` 仍是 spike 的工具：`connected+initialized in … ms`、`  doris___net_check  [readOnly]`、`tools: 1`、`total … ms`、`exit=0`。

- [ ] **Step 2：dry-run**

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
SYNC=1 bash infra/30-gateway.sh 2>&1 | sed -E "$MASK"
git diff --stat infra/state.env   # 期望：无输出
```
期望（spec 阶段实测；时间戳和临时文件名不同）：
```
[..] APPLY=0 region=us-east-1 state=/home/ubuntu/AI-code/Doris-mcp-skill-Demo/infra/state.env
[..] role exists: arn:aws:iam::890717383483:role/doris-mcp-gateway-role
[..] rendered gateway-invoke-runtime.json:
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeDorisMcpRuntimeOnly",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:InvokeAgentRuntime",
      "Resource": ["arn:aws:bedrock-agentcore:us-east-1:890717383483:runtime/dorismcp_dorismcp-ILgkSAFotU", "arn:aws:bedrock-agentcore:us-east-1:890717383483:runtime/dorismcp_dorismcp-ILgkSAFotU/runtime-endpoint/*"]
    }
  ]
}
DRY-RUN: aws iam put-role-policy --role-name doris-mcp-gateway-role --policy-name invoke-dorismcp-runtime --policy-document file:///tmp/tmp.XXXXXXXXXX
[..] DRY-RUN: state_set GW_ROLE_ARN=arn:aws:iam::890717383483:role/doris-mcp-gateway-role
[..] gateway exists: doris-mcp-gw-ryxzl0vgyv (re-applying authorizer, scopes='doris-mcp/invoke')
DRY-RUN: aws bedrock-agentcore-control update-gateway --gateway-identifier doris-mcp-gw-ryxzl0vgyv --name doris-mcp-gw --role-arn arn:aws:iam::890717383483:role/doris-mcp-gateway-role --protocol-type MCP --authorizer-type CUSTOM_JWT --authorizer-configuration \{\"customJWTAuthorizer\":\ \{\"discoveryUrl\":\ \"<url>"\,\ \"allowedClients\":\ \[\"2q9be1ub7s5nh8ph4sl87uemr2\"\,\ \"4bf7hnvsugn9trphjtmsfldb4s\"\]\,\ \"allowedScopes\":\ \[\"doris-mcp/invoke\"\]\}\} --exception-level DEBUG --query status --output text
[..] DRY-RUN: state_set GW_ID=doris-mcp-gw-ryxzl0vgyv
[..] DRY-RUN: state_set GW_URL=<url>
DRY-RUN: aws bedrock-agentcore-control synchronize-gateway-targets --gateway-identifier doris-mcp-gw-ryxzl0vgyv --target-id-list ENINDEEGGB
[..] DRY-RUN: state_set GW_TARGET_ID=ENINDEEGGB
[..] done (APPLY=0)
```
脚本对已有资源的处理：
- `put-role-policy`：Gateway 角色的内联策略，内容和现在相同，只允许 invoke 这个 Runtime。T3.2 没有换 Runtime ARN，所以不用改。
- `update-gateway`：
  - 名字、角色、协议、Cognito authorizer（两个 client、scope `doris-mcp/invoke`）和 `--exception-level DEBUG` 都和现在相同；
  - 脚本不传 `--description`，所以 update 之后 description 可能被清空。这只影响控制台里的显示，Step 4 记录结果，本计划不修。
- `synchronize-gateway-targets`：让 Gateway 重新向 Runtime 要工具列表，这是本任务要做的事。
- 3 个 `state_set` 的值都和现在的 `state.env` 相同。

- [ ] **Step 3：GATE —— 展示并等待确认**

向用户展示 Step 2 的输出，并说明：
- 效果：
  - Gateway target 的工具目录从 spike 的 `net_check` 换成完整 server 的 12 个工具（`doris___` 前缀）；
  - Gateway 的角色策略和 authorizer 重新应用一遍，内容不变；
  - `exceptionLevel` 仍是 DEBUG（design §14：保留到 T5.5，本任务 Step 5 做泄漏检查）；
  - description 可能被清空。
- 费用：同步本身不产生资源。本任务后面的检查大约有 70 次工具调用，每次一个 Runtime session，按使用时长计费，金额可以忽略。
- 影响：Quick 在 P4 才接入，现在没有别的客户端使用这个 Gateway。
- 回滚（也需要 GATE）：这一步只改变 target 的工具目录。要回到 spike 的目录，先按 T3.2 的回滚把 Runtime deploy 回 spike，再执行一次 `SYNC=1 APPLY=1 bash infra/30-gateway.sh`。

用户明确确认后执行（约 1 分钟）：
```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
SYNC=1 APPLY=1 bash infra/30-gateway.sh 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
git diff --stat infra/state.env
```
期望：
```
[..] APPLY=1 region=us-east-1 state=/home/ubuntu/AI-code/Doris-mcp-skill-Demo/infra/state.env
[..] role exists: arn:aws:iam::890717383483:role/doris-mcp-gateway-role
[..] state: GW_ROLE_ARN=arn:aws:iam::890717383483:role/doris-mcp-gateway-role
[..] gateway exists: doris-mcp-gw-ryxzl0vgyv (re-applying authorizer, scopes='doris-mcp/invoke')
[..] get-gateway → READY
[..] state: GW_ID=doris-mcp-gw-ryxzl0vgyv
[..] state: GW_URL=<url>
[..] get-gateway-target → READY
[..] state: GW_TARGET_ID=ENINDEEGGB
[..] done (APPLY=1)
exit=0
```
`git diff` 没有输出：`state.env` 的值都没变。

说明：
- `get-gateway-target → READY` 可能出现得很快：`synchronize-gateway-targets` 刚返回时，状态有可能还没变成同步中。所以 Step 4 用 `lastSynchronizedAt` 确认同步真的完成了。
- 脚本的 `wait_status` 只把 `FAILED` / `UPDATE_UNSUCCESSFUL` 当作失败。如果同步失败（`SYNCHRONIZE_UNSUCCESSFUL`），它会等满 5 分钟，然后输出 `FATAL: timeout waiting for READY (last status: SYNCHRONIZE_UNSUCCESSFUL)`。这时查看原因，然后停下来，把结果给用户看：
  ```bash
  source infra/state.env
  aws bedrock-agentcore-control get-gateway-target --region us-east-1 --gateway-identifier "$GW_ID" --target-id "$GW_TARGET_ID" \
    --query statusReasons --output json | sed -E 's/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
  ```

如果 harness 拦住了这条命令，请用户在提示符里输入 `! SYNC=1 APPLY=1 bash infra/30-gateway.sh 2>&1 | sed -E 's/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'` 自己执行。

- [ ] **Step 4：确认同步完成；经 Gateway 列工具、跑 flow**（只读）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
for i in $(seq 36); do
  cur=$(aws bedrock-agentcore-control get-gateway-target --region us-east-1 --gateway-identifier "$GW_ID" --target-id "$GW_TARGET_ID" \
        --query '[status, lastSynchronizedAt]' --output text)
  [ "${cur%%$'\t'*}" = READY ] && [ "$cur" != "$(cat /tmp/t34-target-before.txt)" ] && break
  sleep 5
done; echo "$cur"
aws bedrock-agentcore-control get-gateway --region us-east-1 --gateway-identifier "$GW_ID" \
  --query '[status, exceptionLevel, description]' --output text
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN list --expect 12 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN flow --prefix doris___ --wait 60 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
unset GW_TOKEN
```
期望：

target 和 Gateway：
- `READY	2026-09-27T…`：`lastSynchronizedAt` 晚于 Step 1 记录的值。如果 3 分钟后仍是旧值，按 Step 3 的说明查看 `statusReasons`，然后停下来；
- `READY	DEBUG	…`：description 可能是原值，也可能是 `None`（被 update 清空了），把结果记进 progress。

`list` 的输出。工具名带 `doris___` 前缀；`readOnly` 标注经 Gateway 保留（P0 的 `net_check` 就是这样）：
```
connected+initialized in … ms
  doris___check_service_health  [readOnly]
  doris___describe_table  [readOnly]
  doris___execute_query  [readOnly]
  doris___get_query_guide  [readOnly]
  doris___get_query_profile  [readOnly]
  doris___list_databases  [readOnly]
  doris___list_dimensions_for_metric  [readOnly]
  doris___list_metrics  [readOnly]
  doris___list_recent_queries  [readOnly]
  doris___list_tables  [readOnly]
  doris___query_metric  [readOnly]
  doris___reload_semantic_layer
tools: 12
total … ms
exit=0
```
如果仍然只有 `doris___net_check`，说明同步没有生效，停下来查。

`flow` 的输出：6 行 `[PASS]`，然后 `flow: 6/6 passed`、`exit=0`。

说明：
- 经 Gateway 的每次调用都是冷启动，所以 flow 比 T3.3 慢得多，可能要一两分钟。
- `--wait 60`：`list_recent_queries` 的每次轮询本身也是一个新的 microVM，要几秒钟。默认的 15 s 只够轮询一两次，找不到 trace token 就会误报 FAIL。

- [ ] **Step 5：Gateway DEBUG 错误信息的泄漏检查**（只读）

对 6 类出错调用，分别比较 Gateway 返回的内容和本机 server 直接返回的内容。只输出计数和错误码，不输出错误消息：
- Runtime 返回的工具错误，Gateway 原样转发；
- Gateway 自己产生的错误（参数不合 schema、工具不存在），DEBUG 级别会带上更多细节。

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
out=$(mktemp); err=$(mktemp)
while IFS=$'\t' read -r tool params; do
  echo "## $tool"
  .venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN call "$tool" "$params" </dev/null 2>"$err"
  echo "exit=$?"
  tail -1 "$err"
done > "$out" <<'EOF'
doris___execute_query	{"sql": "SELECT * FROM ecom.no_such_table"}
doris___describe_table	{"database": "ecom", "table": "no_such_table"}
doris___query_metric	{"workspace": "ecom", "metrics": ["no_such_metric"]}
doris___get_query_profile	{"query_id": "../../api/x"}
doris___list_tables	{"database": 123}
doris___no_such_tool	{}
EOF
unset GW_TOKEN
echo "ipv4: $(grep -cE '\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b' "$out")"
pw="$(aws secretsmanager get-secret-value --region us-east-1 --secret-id doris-mcp/mcp_svc --query SecretString --output text |
      python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')"
n=$(grep -cF -f <(printf '%s\n' "$pw") "$out"); unset pw; echo "password: $n"
echo "traceback: $(grep -cE 'Traceback|File "/' "$out")"
echo "arn: $(grep -c 'arn:aws:' "$out")"
[ "$n" = 0 ] && grep -E '^## |^exit=|"code"|^"|Error: ' "$out" | sed -E "$MASK" | cut -c1-160
rm -f "$out" "$err"
```
期望：前 4 个计数都是 `0`，也就是返回里没有 IPv4 字面量、没有 `mcp_svc` 的密码、没有 Python 栈、没有 ARN。然后是每个调用的摘要：
```
## doris___execute_query
    "code": "CONNECTION_ERROR",
exit=0
## doris___describe_table
    "code": "CONNECTION_ERROR",
exit=0
## doris___query_metric
    "code": "INTERNAL_ERROR",
exit=0
## doris___get_query_profile
    "code": "INVALID_PARAMS",
exit=0
## doris___list_tables
…
exit=1
## doris___no_such_tool
exit=1
mcp.shared.exceptions.McpError: Unknown tool: doris___no_such_tool
```
- 前 4 个是 Runtime 返回的 `success: false`，错误码和本机相同：
  - 表不存在是 Doris 的 1105，upstream 把它归为 `CONNECTION_ERROR`，这个名字不准确，但行为是现有的；
  - 客户端看到的不是 MCP 错误，所以 `exit=0`。
- `doris___list_tables` 传了整数：可能由 Gateway 按 schema 拒绝，也可能转发给 server，由 pydantic 报校验错误。两种情况下 `exit=1` 后面的那一行不同，以实际为准，记进 progress。
- 未知工具由 Gateway 直接返回 JSON-RPC 错误，fastmcp 客户端把它抛成 `McpError`（spec 阶段对当前 Gateway 实测过）。
- 每个调用只保留 stderr 的最后一行：`McpError` 时我们自己的客户端会打印 30 多行栈，那不是 Gateway 返回的内容，不计入 `traceback`。

本机 server 直接返回的对照（spec 阶段实测，4 个计数也都是 `0`）：
```
## execute_query
    "code": "CONNECTION_ERROR",
exit=0
## describe_table
    "code": "CONNECTION_ERROR",
exit=0
## query_metric
    "code": "INTERNAL_ERROR",
exit=0
## get_query_profile
    "code": "INVALID_PARAMS",
exit=0
## list_tables
"1 validation error for call[list_tables]\ndatabase\n  Input should be a valid string [type=string_type, input_value=123, input_type=int]\n    For further infor
exit=1
## no_such_tool
"Unknown tool: 'no_such_tool'"
exit=1
```

判断：
- `ipv4`、`password`、`traceback` 任何一个不是 `0`：**停下来**，不打印内容，把计数给用户看。这说明 DEBUG 会把内部信息带给 Quick 用户，要和用户商量是否提前把 `exceptionLevel` 调低（design §14，也是一个 GATE）。
- `arn` 不是 `0`：ARN 不是 secret，记进 progress，留到 T5.5 一起决定。
- 覆盖不到的一类错误：Doris 连不上时（2003），pymysql 的消息里带 Doris 地址。upstream 的 `sensitive_mask` 只遮密码和 token，不遮 host，这条消息会原样返回给客户端。本任务不为了测它而断开网络，这是已知风险，已记入 design §13。

- [ ] **Step 6：经 Gateway 的逐次耗时和 20 个并发**（只读）

这就是 P0 M-4 要求的可重跑探针：探针代码是 `mcp_smoke.py time` 和 `smoke_calls.json`，下面的命令就是重跑方式。

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
sleep 5; date +%s000 > /tmp/t34-since; sleep 2
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN time --prefix doris___ 2>&1 \
  | sed -E "$MASK" | tee /tmp/t34-time-serial.txt; echo "exit=${PIPESTATUS[0]}"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN time --prefix doris___ --parallel 20 --repeat 2 2>&1 \
  | sed -E "$MASK" | tee /tmp/t34-time-parallel.txt; echo "exit=${PIPESTATUS[0]}"
unset GW_TOKEN
```
期望：
- 串行：12 行 `ok`，然后 `time: 12 calls (1 parallel), 0 errors, 0 over 60000 ms; …`、`exit=0`；
- 并发：24 行 `ok`，然后 `time: 24 calls (20 parallel), 0 errors, 0 over 60000 ms; …`、`exit=0`。

说明：
- 两次都在一个 Gateway session 里，这和 Quick 的用法相同。但 Gateway 对每次调用都新开 Runtime session，所以每一行的耗时都应该接近 T3.3 `--fresh` 的对应行，再加上 Gateway 的开销。
- 20 个并发就是 20 个 microVM，各有各的连接池，所以 `pool_max_size=5` 不是瓶颈。真正共享的上限是 Doris 对 `mcp_svc` 的 `max_user_connections=100`，由 Step 7 检查。
- spec 阶段在本机 server 的**一个共享 session** 里跑同样的并发：`time: 24 calls (20 parallel), 6 errors, 0 over 60000 ms; p50 4475 ms, p95 13824 ms, max 18928 ms`。6 个错误都是 `SERVICE_NOT_READY`：语义层重新加载期间，同一进程里的语义层工具都返回这个错误，而且这些调用没有审计记录（R-32 缺口，见 requirements v1.4）。经 Gateway 时每次调用在自己的 microVM 里，这种重叠不会出现。
- 如果出现 `SERVICE_NOT_READY`：说明 Gateway 在复用 Runtime session，停下来，把两份输出给用户看。
- 如果出现其他 `ERR` 或 `SLOW`：同样**先停下来**，这属于 design §13 的 60 s 风险，处理方式和 T3.3 Step 7 相同。
- 把两行 `time:` 和最慢的 3 个调用记进 progress。

- [ ] **Step 7：并发之后的 Doris 连接**（只读）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN conns --prefix doris___ \
  --expect-host-prefix 172.31. --max-idle 610 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
unset GW_TOKEN
date +%s > /tmp/t34-t0
```
期望：
```
connected+initialized in … ms
connections: N (Query 1, Sleep N-1) from M distinct hosts; users mcp_svc; max idle S s
  [PASS] host prefix 172.31.: N/N connections
  [PASS] idle connections <= 610 s: 0 over
total … ms
exit=0
```
`N`、`M`、`S` 以实际为准，都记进 progress：
- `N` 大约等于 Step 4–6 里用到连接池的 microVM 数，一般每个 microVM 1 个连接。spec 阶段估计 30–50。
- 这些 microVM 在空闲超时之前一直活着，连接留在 Sleep 状态。microVM 自己不会关闭这些连接，要等 P-09 的 `wait_timeout = 600` 让 Doris 回收。
- 如果 `N` 超过 80，**先停下来**：已经接近 `max_user_connections = 100`，Quick 并发使用时可能出现 `Too many connections`。这属于 design §13 的风险，要和用户商量对策，例如调高上限、缩短 `session_wait_timeout_seconds`，或者缩短 Runtime 的空闲超时。

- [ ] **Step 8：等 11 分钟，核对审计记录，确认残留连接已被回收**（只读）

等到 Step 7 之后满 660 s：P-09 的 600 s，再加 60 s 余量，给 Doris FE 周期性回收连接。Bash 工具单次最多 10 分钟，所以下面这条要重复执行，直到输出 `left` 小于等于 0，一般执行两次。每次都把 timeout 设为 600000。

```bash
left=$(( $(cat /tmp/t34-t0) + 660 - $(date +%s) )); [ "$left" -gt 0 ] && sleep "$(( left < 540 ? left : 540 ))"
echo "left $(( $(cat /tmp/t34-t0) + 660 - $(date +%s) )) s"
```

然后：
```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
aws logs filter-log-events --region us-east-1 --log-group-name "/aws/bedrock-agentcore/runtimes/${RUNTIME_ID}-DEFAULT" \
    --start-time "$(cat /tmp/t34-since)" --filter-pattern '"doris_new_mcp.audit"' --output json \
  | .venv/bin/python scripts/audit_check.py --calls scripts/smoke_calls.json --repeat 3; echo "exit=${PIPESTATUS[1]}"
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN conns --prefix doris___ \
  --expect-host-prefix 172.31. --max-idle 610 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
unset GW_TOKEN
```
期望：

审计记录：Step 6 的 36 个调用，加上 Step 7 `conns` 的 1 个 `execute_query`。每个 microVM 都把审计记录写进同一个日志组。
```
audit: 37 records (37 ok, 0 failed), 0 unreadable
  check_service_health           3 ok   0 failed  (expected >= 3)
  describe_table                 3 ok   0 failed  (expected >= 3)
  execute_query                  4 ok   0 failed  (expected >= 3)
  get_query_guide                3 ok   0 failed  (expected >= 3)
  get_query_profile              3 ok   0 failed  (expected >= 3)
  list_databases                 3 ok   0 failed  (expected >= 3)
  list_dimensions_for_metric     3 ok   0 failed  (expected >= 3)
  list_metrics                   3 ok   0 failed  (expected >= 3)
  list_recent_queries            3 ok   0 failed  (expected >= 3)
  list_tables                    3 ok   0 failed  (expected >= 3)
  query_metric                   3 ok   0 failed  (expected >= 3)
  reload_semantic_layer          3 ok   0 failed  (expected >= 3)
  [PASS] every expected call audited: 12/12 tools
exit=0
```

连接：
```
connected+initialized in … ms
connections: 1 (Query 1) from 1 distinct hosts; users mcp_svc; max idle 0 s
  [PASS] host prefix 172.31.: 1/1 connections
  [PASS] idle connections <= 610 s: 0 over
total … ms
exit=0
```
剩下的只有这次 `SHOW PROCESSLIST` 自己的连接。Step 7 看到的 `N` 个连接都已被 Doris 在空闲 600 s 后关闭，这就在线验证了 P-09；没有 P-09 时，它们会留 8 小时（Doris 默认的 `wait_timeout` 是 28800）。

判断：
- 有 Sleep 连接超过 610 s（`[FAIL] idle connections`）：P-09 没有生效，**停下来**，这时的连接会一直累积到 `max_user_connections`。
- 还有别的 Sleep 连接，但都没超过 610 s：说明这段时间里有别的东西在用 `mcp_svc`。P4 之前不应该有别的客户端，先查清楚。
- 审计 `exit=1`：先等 1 分钟重跑审计那一段；仍然缺记录就停下来查。

- [ ] **Step 9：收尾**

- 勾选 T3.4。
- progress「当前状态」：T3.4 完成，下一步 T3.5。
- 日志记录：
  - Step 4 的 `lastSynchronizedAt`、description 的结果、`tools: 12`、flow 结果；
  - Step 5 的 4 个计数，以及 `list_tables` 那一行的实际内容；
  - Step 6 的两行 `time:` 和最慢的 3 个调用；
  - Step 7 的 `N`、`M`、`S`；
  - Step 8 的审计计数和回收结果；
  - 用户确认 GATE 的原话。

```bash
bash scripts/check-secrets.sh
git add specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "docs(p3): T3.4 Gateway synced: doris___ 12 tools, flow, timings, 20 parallel, connections reaped, DEBUG leak check

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T3.5：把 `mcp_svc` 的 host 收紧为 `'172.31.%'`；R-40 复核；FE 审计日志

来源：
- tasks.md T3.5、D6、R-42、design §11 P3 行（`mcp_svc` host 收紧）；
- R-40 的「P3 审查」；
- P2 整体评审的两项遗留：
  - T3.5：Doris 不能修改用户的 host，所以要 CREATE 新身份、授权，再 `DROP USER IF EXISTS 'mcp_svc'@'%'`。`admin_sql` 的白名单目前没有 DROP；
  - FE audit log：`CREATE USER` / `ALTER USER … IDENTIFIED BY` 可能把密码明文写进 Doris FE 的审计日志。

**更正**：P2 遗留事项里写的「完成后确认开发机仍能以 `mcp_svc` 登录」是错的。

开发机（13.125.9.110，ap-northeast-2，另一个 VPC）经 Doris 的公网地址连接，来源不在 `172.31.%` 里。所以迁移之后，开发机以 `mcp_svc` 登录会得到 1045，这正是收紧 host 的目的。本任务 Step 10 确认这一点。

迁移之后本机的做法：
- 要以 `mcp_svc` 检查，只能经 Runtime（`permission_matrix.py --url`、`reconcile.py mcp --url`、`mcp_smoke.py --sigv4`）；
- 本机的参照 SQL 用 `demo_ro`。

迁移的顺序保证账号任何时候都有一个能用的身份：
1. 先建 `'mcp_svc'@'172.31.%'`，密码相同（来自 Secrets Manager），授权与 `01_mcp_user.sql` 相同；
2. 最后才删 `'%'`。

两个身份同时存在的时候，Doris 对来自 `172.31.x` 的连接选更具体的 `'172.31.%'`。

已经在运行的 microVM 的连接池里还是旧身份的连接。GATE 之后的所有复测都用新的 MCP session，也就是新的 microVM：`permission_matrix.py --url` 每次运行都新开一个 session。

本任务唯一的 GATE 是 Step 8。另有一项用户侧操作（Step 14），其余步骤都是只读的。

**Files:**
- Create：`doris/02_mcp_user_vpc.sql`
- Modify：
  - `doris/admin_sql.py`：白名单加 `DROP USER IF EXISTS`，并检查 DROP 的位置和对象；
  - `doris/permission_matrix.py`：`--url`、`--region`、`--expect-host`；
  - `tasks.md`、`progress.md`。
- Test：
  - `doris/test/test_admin_sql.py`：`DropUser` 类，5 个测试；
  - `doris/test/test_mcp_user_sql.py`：`McpUserVpcSql` 类，2 个测试；
  - `doris/test/test_permission_matrix.py`：`RemoteRuntime` 9 个测试、`RuntimeCursor` 4 个、`ExpectHostDirect` 1 个；
  - `doris/test/test-apply-admin-sql.sh`：2 项检查；
  - `doris/test` 的测试数从 130 个增加到 151 个。

**Interfaces:**
- Consumes：
  - T3.0：
    - M1：`apply-admin-sql.sh` 先 `unset` 调用方 export 的 root 变量；
    - M2：`permission_matrix.py` 的 `_brief` 先 mask 再截断、兜底 `except`、只读检查失败时跳过探针；
  - T3.3：
    - `scripts/agentcore_client.sigv4_client(url, region=None, timeout=90.0)`；
    - `mcp_smoke.py --sigv4 conns --expect-host-prefix --max-idle`；
    - `reconcile.py mcp --url`；
  - P2：
    - `doris/apply-admin-sql.sh FILE.sql`：dry-run 为默认，`APPLY=1` 以 root 执行，`mcp_svc` 的密码经管道从 Secrets Manager 进入 python；
    - `admin_sql.main(argv, stdin, env, connect, out, err)`，白名单 `_ALLOWED`；
    - `permission_matrix.main(argv, env, connect, out, err)`、`EXPECTED_USER = "mcp_svc"`、`check_grants` / `check_databases` / `check_select` / `check_semantic_store`；
    - `doris/01_mcp_user.sql`：回滚时重建 `'%'`。
- Produces：
  - Doris 用户 `'mcp_svc'@'172.31.%'`：密码 = Secrets Manager `doris-mcp/mcp_svc`，权限按 R-42，与原来的 `'%'` 相同；`'mcp_svc'@'%'` 被删除。
  - 此后开发机不能以 `mcp_svc` 登录（1045）。
  - `admin_sql.py`：
    - `DROP USER IF EXISTS '<user>'@'<host>'` 只在两个条件下放行：前面已经 CREATE 了同一用户的另一个身份，并且本脚本没有建立或授权这个被删的身份；
    - apply 之后只对没被删的身份 `SHOW GRANTS`。
  - `permission_matrix.py`：
    - `--url URL [--region R]`：只读检查经 Runtime 的 `execute_query`，在一个 MCP session 里完成；输出里的 IPv4 被 mask 成 `<ip>`；`APPLY=1` 配 `--url` 是用法错误（exit 2）；
    - `--expect-host H`：多一项检查，要求当前身份正好是 `'mcp_svc'@'H'`。
  - P4、P5 不再直连 `mcp_svc`；T5.x 的复核照抄本任务 Step 9。

- [ ] **Step 1：确认分支、工作区和 Runtime**

```bash
git branch --show-current && git status --short
source infra/state.env
aws bedrock-agentcore-control get-agent-runtime --region us-east-1 --agent-runtime-id "$RUNTIME_ID" \
  --query '[status, agentRuntimeVersion]' --output text
```
期望：
- 分支是 `p3-deploy`，工作区干净；
- `READY	2`。

- [ ] **Step 2：写失败测试**

改动的内容：
- `test_admin_sql.py`：
  - 新增 `MIGRATE_SQL`（3 条语句：CREATE 新身份、授权、DROP `'%'`）和 `DropUser` 类，5 个测试；
  - 白名单测试多一个被拒的用例：一次 DROP 多个身份。
- `test_mcp_user_sql.py`：
  - `EXPECTED_VPC` 钉住 `02_mcp_user_vpc.sql` 的 5 条语句；
  - `test_same_grants_as_01_on_the_new_host` 要求去掉 DROP 之后，把 host 换回 `'%'` 就与 01 完全相同，因为 01 是回滚脚本。
- `test_permission_matrix.py`：
  - `runtime_server(FakeDoris)` 在进程内起一个只有 `execute_query` 的 fastmcp server。它的返回格式与 upstream 相同：成功时是 `{"success": true, "data": [...]}`，Doris 错误时是 `success: false` 加上 pymysql 异常的 repr；
  - `RemoteRuntime` 经真实的 fastmcp Client 调用这个 server，不访问 AWS。
- `test-apply-admin-sql.sh`：
  - 对真实的 `doris/02_mcp_user_vpc.sql` 做 dry-run；
  - 断言新身份在前、DROP `'%'` 在最后；
  - 断言输出里没有密码和主机地址。

```bash
git apply <<'PATCH'
diff --git a/doris/test/test-apply-admin-sql.sh b/doris/test/test-apply-admin-sql.sh
index c1dded0..bb3b4ba 100644
--- a/doris/test/test-apply-admin-sql.sh
+++ b/doris/test/test-apply-admin-sql.sh
@@ -79,5 +79,15 @@ check "e2e dry-run: 4 statements as root" yes "$(has "$E2E" "DRY-RUN: 4 statemen
 check "e2e dry-run: no secret or host in output" "no|no|no" \
   "$(has "$E2E" "SvcPw0123")|$(has "$E2E" "RootPw0123")|$(has "$E2E" "198.51.100.7")"
 
+# P3 / T3.5 host migration script through the same path.
+E2E="$(cd "$(dirname "$SCRIPT")/.." && env -u DORIS_ROOT_PASSWORD PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" \
+  PYTHON_BIN="$REAL_PY" DORIS_CRED_FILE="$TMP/cred.env" APPLY=0 bash "$SCRIPT" doris/02_mcp_user_vpc.sql 2>&1)"
+check "e2e 02 dry-run: new identity first, '%' dropped last" "yes|yes" \
+  "$(has "$E2E" "DRY-RUN SQL: CREATE USER IF NOT EXISTS 'mcp_svc'@'172.31.%' IDENTIFIED BY '***'")|$(has "$E2E" \
+  "DRY-RUN SQL: DROP USER IF EXISTS 'mcp_svc'@'%'
+DRY-RUN: 5 statements as root;")"
+check "e2e 02 dry-run: no secret or host in output" "no|no|no" \
+  "$(has "$E2E" "SvcPw0123")|$(has "$E2E" "RootPw0123")|$(has "$E2E" "198.51.100.7")"
+
 if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
 echo "all passed"
diff --git a/doris/test/test_admin_sql.py b/doris/test/test_admin_sql.py
index 1f7dbb2..8321c8b 100644
--- a/doris/test/test_admin_sql.py
+++ b/doris/test/test_admin_sql.py
@@ -24,6 +24,11 @@ CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
 ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
 GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%';
 """
+# P3 / T3.5 host migration: the new identity first, then drop the old one.
+MIGRATE_SQL = """CREATE USER IF NOT EXISTS 'mcp_svc'@'172.31.%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
+GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'172.31.%';
+DROP USER IF EXISTS 'mcp_svc'@'%';
+"""
 
 
 class FakeCursor:
@@ -92,7 +97,7 @@ class Render(unittest.TestCase):
             admin_sql.render(["ALTER USER 'x'@'%' IDENTIFIED BY '${OTHER}'"], {"MCP_SVC_PASSWORD": PW})
 
     def test_statement_outside_the_allowlist_is_rejected(self):
-        for stmt in ("DROP USER 'mcp_svc'@'%'", "SET GLOBAL enable_profile = true", "SELECT 1",
+        for stmt in ("DROP USER 'mcp_svc'@'%'", "DROP USER IF EXISTS 'mcp_svc'@'%', 'x'@'%'", "SET GLOBAL enable_profile = true", "SELECT 1",
                      "GRANT ADMIN_PRIV ON *.*.* TO 'mcp_svc'@'%'", "GRANT SELECT_PRIV ON *.*.* TO 'mcp_svc'@'%'"):
             with self.subTest(stmt=stmt), self.assertRaises(admin_sql.AdminSqlError):
                 admin_sql.render([stmt], {})
@@ -161,5 +166,45 @@ class Main(unittest.TestCase):
         self.assertEqual(conn.executed, [])
 
 
+class DropUser(unittest.TestCase):
+    """DROP USER IF EXISTS retires an old identity of the secret's user (P3 / T3.5), nothing else."""
+
+    def test_dry_run_shows_the_drop(self):
+        rc, output, conn = run(sql=MIGRATE_SQL)
+        self.assertEqual(rc, 0, output)
+        self.assertIn("DRY-RUN SQL: DROP USER IF EXISTS 'mcp_svc'@'%'", output)
+        self.assertIn("DRY-RUN: 3 statements", output)
+        self.assertEqual(conn.executed, [])
+
+    def test_apply_drops_after_the_new_identity_and_shows_only_its_grants(self):
+        rc, output, conn = run(sql=MIGRATE_SQL, apply=True)
+        self.assertEqual(rc, 0, output)
+        self.assertEqual(conn.executed[2:], ["DROP USER IF EXISTS 'mcp_svc'@'%'", "SHOW GRANTS FOR 'mcp_svc'@'172.31.%'"])
+        self.assertIn("ok: DROP USER IF EXISTS 'mcp_svc'@'%'", output)
+
+    def test_drop_before_any_other_identity_is_created_is_refused(self):
+        sql = "DROP USER IF EXISTS 'mcp_svc'@'%';\n" + MIGRATE_SQL.replace("DROP USER IF EXISTS 'mcp_svc'@'%';\n", "")
+        rc, output, conn = run(sql=sql, apply=True)
+        self.assertEqual(rc, 2)
+        self.assertIn("must follow a CREATE USER of another mcp_svc identity", output)
+        self.assertEqual(conn.executed, [])
+
+    def test_dropping_an_identity_the_script_also_sets_up_is_refused(self):
+        for extra in ("GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%';",
+                      "ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';",
+                      "DROP USER IF EXISTS 'mcp_svc'@'172.31.%';"):
+            with self.subTest(extra=extra):
+                rc, output, conn = run(sql=MIGRATE_SQL + extra + "\n", apply=True)
+                self.assertEqual(rc, 2)
+                self.assertIn("also creates or grants", output)
+                self.assertEqual(conn.executed, [])
+
+    def test_dropping_another_user_is_refused(self):
+        rc, output, conn = run(sql=MIGRATE_SQL + "DROP USER IF EXISTS 'demo_ro'@'%';\n", apply=True)
+        self.assertEqual(rc, 2)
+        self.assertIn("'demo_ro'", output)
+        self.assertEqual(conn.executed, [])
+
+
 if __name__ == "__main__":
     unittest.main()
diff --git a/doris/test/test_mcp_user_sql.py b/doris/test/test_mcp_user_sql.py
index a0a27cb..3e38d49 100644
--- a/doris/test/test_mcp_user_sql.py
+++ b/doris/test/test_mcp_user_sql.py
@@ -1,4 +1,4 @@
-"""Contract test: doris/01_mcp_user.sql grants exactly what R-42 allows (offline).
+"""Contract tests: doris/01_mcp_user.sql and 02_mcp_user_vpc.sql grant exactly what R-42 allows (offline).
 
     .venv/bin/python -m unittest discover -s doris/test -v
 """
@@ -34,5 +34,27 @@ class McpUserSql(unittest.TestCase):
                          [s.replace("${MCP_SVC_PASSWORD}", PW) for s in EXPECTED])
 
 
+# P3 / T3.5: the same account from the VPC only (design §6.1); the '%' identity goes last.
+EXPECTED_VPC = [
+    "CREATE USER IF NOT EXISTS 'mcp_svc'@'172.31.%' IDENTIFIED BY '${MCP_SVC_PASSWORD}'",
+    "ALTER USER 'mcp_svc'@'172.31.%' IDENTIFIED BY '${MCP_SVC_PASSWORD}'",
+    "GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'172.31.%'",
+    "GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'172.31.%'",
+    "DROP USER IF EXISTS 'mcp_svc'@'%'",
+]
+
+
+class McpUserVpcSql(unittest.TestCase):
+    def test_statements_move_the_account_to_the_vpc_range(self):
+        stmts = admin_sql.load_statements((DORIS_DIR / "02_mcp_user_vpc.sql").read_text(encoding="utf-8"))
+        self.assertEqual(stmts, EXPECTED_VPC)
+        self.assertEqual(admin_sql.render(stmts, {"MCP_SVC_PASSWORD": PW}),
+                         [s.replace("${MCP_SVC_PASSWORD}", PW) for s in EXPECTED_VPC])
+
+    def test_same_grants_as_01_on_the_new_host(self):
+        # 01 is the rollback (it re-creates the '%' identity), so the two must stay in step.
+        self.assertEqual([s.replace("'172.31.%'", "'%'") for s in EXPECTED_VPC[:-1]], EXPECTED)
+
+
 if __name__ == "__main__":
     unittest.main()
diff --git a/doris/test/test_permission_matrix.py b/doris/test/test_permission_matrix.py
index e4b5ca4..3cab081 100644
--- a/doris/test/test_permission_matrix.py
+++ b/doris/test/test_permission_matrix.py
@@ -10,6 +10,7 @@ probes only after the GATE.
 from __future__ import annotations
 
 import io
+import json
 import logging
 import re
 import sys
@@ -28,6 +29,8 @@ from agentcore_ext.settings import load_settings  # noqa: E402
 from permission_matrix import classify_error, grant_problems, parse_grants, write_probes  # noqa: E402
 from store.bootstrap import collect_physical_tables  # noqa: E402
 
+from fastmcp import Client, FastMCP  # noqa: E402
+
 MODELS = ROOT / "doris" / "semantic" / "ecom"
 PASSWORD = "SvcPw0123456789abcXYZ"
 ENV = {"DORIS_HOST": "10.0.0.1", "DORIS_PORT": "9030", "DORIS_USER": "mcp_svc", "DORIS_PASSWORD": PASSWORD}
@@ -487,5 +490,155 @@ class UpstreamStoreInit(unittest.TestCase):
         self.mocks["clear_service_credentials"].assert_called_once_with()
 
 
+RUNTIME_URL = "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn/invocations?qualifier=DEFAULT"
+VPC_IDENTITY = "'mcp_svc'@'172.31.%'"
+
+
+def runtime_server(doris: FakeDoris) -> FastMCP:
+    """The deployed server's execute_query, answering from a FakeDoris the way upstream tools/query.py does."""
+    mcp = FastMCP("fake-runtime")
+
+    @mcp.tool
+    async def execute_query(sql: str, database: str = "", max_rows: int = 0) -> str:
+        cur = doris.cursor()
+        try:
+            cur.execute(sql)
+        except pymysql.MySQLError as e:  # upstream: error_response(CONNECTION_ERROR, str(e))
+            return json.dumps({"success": False, "error": {"code": "CONNECTION_ERROR", "message": str(e)}})
+        return json.dumps({"success": True, "data": {"columns": [], "rows": cur.fetchall()}}, default=str)
+
+    return mcp
+
+
+class RemoteRuntime(unittest.TestCase):
+    """--url: the read-only checks through the deployed Runtime, as mcp_svc from the VPC (P3 / T3.5)."""
+
+    def run_remote(self, argv=(), doris=None, apply=False, remote_error=None):
+        doris = doris or FakeDoris({"SELECT CURRENT_USER()": [{"identity": VPC_IDENTITY}]})
+        remote_calls = []
+
+        def remote_connect(url, region):
+            remote_calls.append((url, region))
+            if remote_error:
+                raise remote_error
+            return permission_matrix.RuntimeConnection(Client(runtime_server(doris)))
+
+        def no_direct_connect(**kwargs):
+            raise AssertionError("--url must not connect to Doris directly")
+
+        out, err = io.StringIO(), io.StringIO()
+        env = {"APPLY": "1"} if apply else {}  # no DORIS_* at all: the Runtime has its own settings
+        rc = permission_matrix.main(["--url", RUNTIME_URL, *argv], env=env, connect=no_direct_connect, out=out,
+                                    err=err, remote_connect=remote_connect)
+        return rc, out.getvalue(), err.getvalue(), doris, remote_calls
+
+    def test_read_only_checks_run_through_the_runtime(self):
+        rc, out, err, doris, remote_calls = self.run_remote(["--expect-host", "172.31.%"])
+        self.assertEqual(rc, 0, out + err)
+        self.assertEqual(remote_calls, [(RUNTIME_URL, None)])
+        self.assertEqual({s.split()[0] for s in doris.executed}, {"SELECT", "SHOW"})
+        for line in (f"connected as {VPC_IDENTITY} (through the Runtime)", f"ok    identity: {VPC_IDENTITY}",
+                     "ok    grants", "ok    databases", "ok    select: 9 physical tables", "ok    semantic store",
+                     "info  max_user_connections=100", "5/5 checks pass"):
+            self.assertIn(line, out)
+
+    def test_params_are_inlined_as_literals(self):
+        _, _, _, doris, _ = self.run_remote()
+        self.assertIn("SELECT semantic_version FROM system_mcp.workspace_metadata WHERE workspace = 'ecom'",
+                      doris.executed)
+
+    def test_the_old_identity_fails_the_host_check(self):
+        doris = FakeDoris()  # still 'mcp_svc'@'%'
+        rc, out, _, _, _ = self.run_remote(["--expect-host", "172.31.%"], doris=doris)
+        self.assertEqual(rc, 1)
+        self.assertIn(f"FAIL  identity: connected as {IDENTITY}, expected {VPC_IDENTITY}", out)
+
+    def test_doris_errors_keep_their_errno_and_ips_are_masked(self):
+        doris = FakeDoris({"SELECT CURRENT_USER()": [{"identity": VPC_IDENTITY}],
+                           "SELECT 1 FROM internal.ecom.fact_refund": denied("SELECT")})
+        rc, out, err, _, _ = self.run_remote(doris=doris)
+        self.assertEqual(rc, 1)
+        self.assertRegex(out, r"FAIL  select: internal\.ecom\.fact_refund: 1105 SELECT command denied to user 'mcp_svc'@'<ip>'")
+        self.assertNotIn("10.0.0.9", out + err)
+
+    def test_dry_run_lists_no_probes(self):
+        rc, out, _, _, _ = self.run_remote()
+        self.assertEqual(rc, 0, out)
+        self.assertIn("probes: not run with --url", out)
+        self.assertNotIn("DRY-RUN probes", out)
+
+    def test_apply_with_url_is_a_usage_error(self):
+        rc, _, err, doris, remote_calls = self.run_remote(apply=True)
+        self.assertEqual(rc, 2)
+        self.assertIn("APPLY=1", err)
+        self.assertEqual((doris.executed, remote_calls), ([], []))
+
+    def test_region_is_passed_and_needs_url(self):
+        _, _, _, _, remote_calls = self.run_remote(["--region", "us-east-1"])
+        self.assertEqual(remote_calls, [(RUNTIME_URL, "us-east-1")])
+        rc, _, err, _, _ = run_main(["--region", "us-east-1"])
+        self.assertEqual(rc, 2)
+        self.assertIn("--region only applies with --url", err)
+
+    def test_a_session_failure_is_one_masked_line(self):
+        rc, out, err, _, _ = self.run_remote(remote_error=ConnectionError("connect to 172.31.25.143:443 failed"))
+        self.assertEqual(rc, 1)
+        self.assertEqual(err.strip(), "FAILED: connect: ConnectionError: connect to <ip>:443 failed")
+        self.assertEqual(out, "")
+
+    def test_default_remote_connect_uses_the_sigv4_client(self):
+        sys.path.insert(0, str(ROOT / "scripts"))
+        import agentcore_client
+        server = runtime_server(FakeDoris())
+        with mock.patch.object(agentcore_client, "sigv4_client", return_value=Client(server)) as factory:
+            conn = permission_matrix._runtime_connection(RUNTIME_URL, "us-east-1")
+            try:
+                with conn.cursor() as cur:
+                    cur.execute("SELECT CURRENT_USER() AS identity")
+                    self.assertEqual(cur.fetchall(), [{"identity": IDENTITY}])
+            finally:
+                conn.close()
+        factory.assert_called_once_with(RUNTIME_URL, "us-east-1")
+
+
+class RuntimeCursor(unittest.TestCase):
+    def cursor(self, body):
+        return permission_matrix.RuntimeCursor(lambda sql: body)
+
+    def test_a_non_mysql_tool_error_keeps_its_code(self):
+        cur = self.cursor({"success": False, "error": {"code": "INVALID_SQL", "message": "Only read-only SQL"}})
+        with self.assertRaises(pymysql.MySQLError) as cm:
+            cur.execute("SELECT 1")
+        self.assertEqual(cm.exception.args, (0, "INVALID_SQL: Only read-only SQL"))
+
+    def test_a_mysql_error_message_becomes_errno_and_text(self):
+        cur = self.cursor({"success": False, "error": {"code": "CONNECTION_ERROR",
+                                                        "message": str(denied())}})
+        with self.assertRaises(pymysql.MySQLError) as cm:
+            cur.execute("SELECT 1")
+        self.assertEqual(cm.exception.args[0], 1105)
+        self.assertTrue(cm.exception.args[1].startswith("errCode = 2, detailMessage = LOAD command denied"))
+        self.assertEqual(classify_error(cm.exception), "denied")
+
+    def test_params_that_need_quoting_are_refused(self):
+        cur = self.cursor({"success": True, "data": {"rows": []}})
+        for bad in ("a'b", "x y", "", 3):
+            with self.subTest(bad=bad), self.assertRaises(ValueError):
+                cur.execute("SELECT 1 WHERE w = %s", (bad,))
+
+    def test_a_reply_that_is_not_a_result_is_an_error(self):
+        with self.assertRaises(pymysql.MySQLError) as cm:
+            self.cursor({"success": True}).execute("SELECT 1")
+        self.assertIn("no rows", cm.exception.args[1])
+
+
+class ExpectHostDirect(unittest.TestCase):
+    def test_expect_host_also_checks_a_direct_connection(self):
+        rc, out, err, _, _ = run_main(["--expect-host", "%"])
+        self.assertEqual(rc, 0, err)
+        self.assertIn(f"ok    identity: {IDENTITY}", out)
+        self.assertIn("5/5 checks pass", out)
+
+
 if __name__ == "__main__":
     unittest.main()
PATCH
```

- [ ] **Step 3：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s doris/test > /tmp/t35-red.log 2>&1
grep -E '^(FAIL|ERROR):' /tmp/t35-red.log | sed -E 's/ \(.*//' | sort -u
grep -E '^Ran|^FAILED|^OK' /tmp/t35-red.log
bash doris/test/test-apply-admin-sql.sh 2>&1 | grep -E '^FAIL|failed$|all passed'
```
期望：
```
ERROR: test_a_mysql_error_message_becomes_errno_and_text
ERROR: test_a_non_mysql_tool_error_keeps_its_code
ERROR: test_a_reply_that_is_not_a_result_is_an_error
ERROR: test_a_session_failure_is_one_masked_line
ERROR: test_apply_with_url_is_a_usage_error
ERROR: test_default_remote_connect_uses_the_sigv4_client
ERROR: test_doris_errors_keep_their_errno_and_ips_are_masked
ERROR: test_dry_run_lists_no_probes
ERROR: test_expect_host_also_checks_a_direct_connection
ERROR: test_params_are_inlined_as_literals
ERROR: test_params_that_need_quoting_are_refused
ERROR: test_read_only_checks_run_through_the_runtime
ERROR: test_region_is_passed_and_needs_url
ERROR: test_statements_move_the_account_to_the_vpc_range
ERROR: test_the_old_identity_fails_the_host_check
FAIL: test_apply_drops_after_the_new_identity_and_shows_only_its_grants
FAIL: test_drop_before_any_other_identity_is_created_is_refused
FAIL: test_dropping_an_identity_the_script_also_sets_up_is_refused
FAIL: test_dropping_another_user_is_refused
FAIL: test_dry_run_shows_the_drop
Ran 151 tests in …s
FAILED (failures=7, errors=15)
FAIL e2e 02 dry-run: new identity first, '%' dropped last: expected 'yes|yes', got 'no|no'
1 failed
```

失败的原因：
- 15 个 ERROR：
  - `test_statements_move_the_account_to_the_vpc_range`：`02_mcp_user_vpc.sql` 还不存在（`FileNotFoundError`）；
  - 其余 14 个：`permission_matrix.py` 还没有 `--url` / `--expect-host`、`RuntimeCursor`、`_runtime_connection`，`main()` 也不接受 `remote_connect`。
- 7 个 failures：
  - `DropUser` 的 5 个测试，其中 `test_dropping_an_identity_the_script_also_sets_up_is_refused` 有 3 个 subTest，经 `sort -u` 合并成一行；
  - 白名单还没有 DROP，所以 DROP 语句被当作不允许的语句拒绝，但错误消息和测试期望的不同。
- `test_same_grants_as_01_on_the_new_host` 此时已经通过：它比较的是两个期望常量。和 `test_statements_move…` 一起，才约束 SQL 文件本身。
- shell 测试：`02_mcp_user_vpc.sql` 不存在，dry-run 失败。

- [ ] **Step 4：实现**

新建 `doris/02_mcp_user_vpc.sql`：

```sql
-- P3 / T3.5 — move the doris-mcp service account to the VPC range (design §6.1, R-42, P2 review carry-forward).
-- Run as root through doris/apply-admin-sql.sh (dry-run by default; APPLY=1 only after the GATE).
-- ${MCP_SVC_PASSWORD} is filled in memory from Secrets Manager doris-mcp/mcp_svc; never write it here.
-- The Runtime ENIs are in 172.31.0.0/16. The new identity gets the same password and grants as 01 first;
-- only then is 'mcp_svc'@'%' dropped, so the account is never without a working identity.
-- Afterwards mcp_svc cannot log in from outside 172.31.%: that includes the dev box (expected, 1045).
-- Re-run safe (IF NOT EXISTS / IF EXISTS). Rollback: re-run doris/01_mcp_user.sql (re-creates '%').
CREATE USER IF NOT EXISTS 'mcp_svc'@'172.31.%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
ALTER USER 'mcp_svc'@'172.31.%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'172.31.%';
GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'172.31.%';
DROP USER IF EXISTS 'mcp_svc'@'%';
```

`doris/admin_sql.py`：
- 白名单加 `_DROP`；
- `_check_drops` 在读 secret 之前检查，被拒绝时不连接 Doris。

`doris/permission_matrix.py`：
- `RuntimeConnection` / `RuntimeCursor` 模拟 pymysql 的 cursor，只实现本脚本用到的 `execute` / `fetchall`；
- 参数只接受 `[A-Za-z0-9_]`（workspace 名），直接内联成字面量；
- 工具返回的 `success: false`：错误消息是 pymysql 异常的 repr（例如 `(1105, 'errCode = 2, …')`），用 `ast.literal_eval` 还原成 `pymysql.err.OperationalError(errno, msg)`，这样 `_brief` 和 `classify_error` 不用改；还原不了的，errno 记为 0。

```bash
git apply <<'PATCH'
diff --git a/doris/admin_sql.py b/doris/admin_sql.py
index 88e9f47..b0e659a 100644
--- a/doris/admin_sql.py
+++ b/doris/admin_sql.py
@@ -8,7 +8,9 @@ env    DORIS_HOST, DORIS_PORT (9030), DORIS_ADMIN_USER, DORIS_ADMIN_PASSWORD; AP
 The SQL may reference ${MCP_SVC_PASSWORD}; it is filled in memory only. Dry-run (default) prints the
 statements with the password masked and never connects. Only account statements for the secret's
 user are accepted: CREATE USER IF NOT EXISTS / ALTER USER ... IDENTIFIED BY / GRANT of SELECT_PRIV
-and CREATE_PRIV on a single internal database.
+and CREATE_PRIV on a single internal database / DROP USER IF EXISTS of an old identity (host
+migration, P3 / T3.5), only after a CREATE USER of another identity of that user and never of an
+identity the same script sets up.
 """
 
 from __future__ import annotations
@@ -27,10 +29,13 @@ _PASSWORD_RE = re.compile(r"^[A-Za-z0-9]{16,128}$")
 _PLACEHOLDER_RE = re.compile(r"\$\{([A-Z_]+)\}")
 _IDENT = r"(?P<ident>'(?P<user>[a-z_][a-z0-9_]*)'@'[0-9.%]+')"
 _PRIV = r"(?:SELECT_PRIV|CREATE_PRIV)"
+_CREATE = re.compile(rf"^CREATE USER IF NOT EXISTS {_IDENT} IDENTIFIED BY '[^']*'$")
+_DROP = re.compile(rf"^DROP USER IF EXISTS {_IDENT}$")
 _ALLOWED = (
-    re.compile(rf"^CREATE USER IF NOT EXISTS {_IDENT} IDENTIFIED BY '[^']*'$"),
+    _CREATE,
     re.compile(rf"^ALTER USER {_IDENT} IDENTIFIED BY '[^']*'$"),
     re.compile(rf"^GRANT {_PRIV}(?:, {_PRIV})* ON internal\.[a-z_][a-z0-9_]*\.\* TO {_IDENT}$"),
+    _DROP,
 )
 
 
@@ -63,6 +68,19 @@ def render(statements: Sequence[str], values: Mapping[str, str]) -> list[str]:
     return [_PLACEHOLDER_RE.sub(fill, stmt) for stmt in statements if _match(stmt)]
 
 
+def _check_drops(matches: Sequence[re.Match[str]]) -> None:
+    """A DROP retires an old identity: another identity of the user exists first, and nothing re-creates it."""
+    kept = {m.group("ident") for m in matches if m.re is not _DROP}
+    for i, m in enumerate(matches):
+        if m.re is not _DROP:
+            continue
+        ident, user = m.group("ident"), m.group("user")
+        if ident in kept:
+            raise AdminSqlError(f"DROP USER {ident}: the script also creates or grants {ident}")
+        if not any(c.re is _CREATE and c.group("user") == user for c in matches[:i]):
+            raise AdminSqlError(f"DROP USER {ident} must follow a CREATE USER of another {user} identity")
+
+
 def _read_secret(raw: str) -> tuple[str, str]:
     try:
         doc = json.loads(raw)
@@ -94,6 +112,7 @@ def main(
     try:
         statements = load_statements(Path(argv[0]).read_text(encoding="utf-8"))
         matches = [_match(s) for s in statements]
+        _check_drops(matches)
         user, password = _read_secret(stdin.read())
         targets = {m.group("user") for m in matches}
         if targets != {user}:
@@ -102,7 +121,7 @@ def main(
     except (OSError, AdminSqlError) as e:
         print(f"ERROR: {e}", file=err)
         return 2
-    identities = sorted({m.group("ident") for m in matches})
+    identities = sorted({m.group("ident") for m in matches if m.re is not _DROP})
     shown = [_mask(s, [password]) for s in rendered]
 
     if env.get("APPLY") != "1":
diff --git a/doris/permission_matrix.py b/doris/permission_matrix.py
index 11f9cee..5186f41 100644
--- a/doris/permission_matrix.py
+++ b/doris/permission_matrix.py
@@ -2,9 +2,15 @@
 
     python doris/permission_matrix.py [--workspace ecom]           # read-only checks + the probe list
     APPLY=1 python doris/permission_matrix.py [--workspace ecom]   # GATE: also run the probes
+    python doris/permission_matrix.py --url "$RUNTIME_URL" --expect-host '172.31.%'   # P3: through the Runtime
 
 Connection: agentcore_ext.settings.load_settings(os.environ) -- DORIS_HOST, DORIS_PORT and
 DORIS_SECRET_ID=doris-mcp/mcp_svc (or DORIS_USER/DORIS_PASSWORD).
+With --url the read-only checks go through the deployed Runtime's execute_query tool over SigV4
+(AWS_* credentials; scripts/agentcore_client.py), i.e. as mcp_svc from the VPC: after P3 / T3.5 that
+is the only place the account can log in from. The probes need a direct connection (APPLY=1 refuses
+--url); IPv4 addresses in the output are masked as <ip>. --expect-host H adds a check that the
+connected identity is exactly 'mcp_svc'@'H'.
 Read-only checks: SHOW GRANTS equals EXPECTED_GRANTS exactly (R-42), SHOW DATABASES equals
 EXPECTED_DATABASES, every physical table of the models is readable, the workspace has a metadata
 row (else upstream would INSERT it, which needs LOAD_PRIV) and active files.
@@ -18,7 +24,10 @@ Exit 0 when every check passes, 1 when one fails, 2 on usage/configuration error
 from __future__ import annotations
 
 import argparse
+import ast
+import asyncio
 import dataclasses
+import json
 import logging
 import os
 import re
@@ -53,6 +62,8 @@ EXPECTED_DATABASES = frozenset({"ecom", "system_mcp", "information_schema", "mys
 DENIED_ERRNOS = frozenset({1044, 1142, 1143, 1227})
 DENIED_1105 = ("access denied", "command denied")  # Doris 4.1 refuses privileges with errno 1105 (T2.3)
 _WORKSPACE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")  # upstream workspace/create rule
+_LITERAL_RE = re.compile(r"^[A-Za-z0-9_]+$")  # what RuntimeCursor inlines without quoting rules
+_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
 _STORE_LOGGER = "doris_new_mcp.store"
 
 
@@ -127,7 +138,10 @@ def classify_error(error: pymysql.MySQLError) -> str:
     return "error"
 
 
-def _brief(error: pymysql.MySQLError, secrets: Iterable[str]) -> str:
+Secrets = Iterable["str | re.Pattern[str]"]  # literal values -> ***, patterns (IPv4) -> <ip>
+
+
+def _brief(error: pymysql.MySQLError, secrets: Secrets) -> str:
     """errno + message, masked before it is cut (a cut secret no longer matches the mask)."""
     errno = error.args[0] if error.args else "?"
     message = str(error.args[1]) if len(error.args) > 1 else str(error)
@@ -156,7 +170,7 @@ def check_databases(cur: Any) -> Result:
     return Result(not problems, "databases", "; ".join(problems) or ", ".join(sorted(seen)))
 
 
-def check_select(cur: Any, tables: Sequence[str], secrets: Iterable[str]) -> Result:
+def check_select(cur: Any, tables: Sequence[str], secrets: Secrets) -> Result:
     failed = []
     for table in tables:
         try:
@@ -179,7 +193,7 @@ def check_semantic_store(cur: Any, workspace: str) -> Result:
                   f"workspace {workspace} semantic_version={rows[0]['semantic_version']}, {files} active files")
 
 
-def max_user_connections(cur: Any, secrets: Iterable[str]) -> str:
+def max_user_connections(cur: Any, secrets: Secrets) -> str:
     try:
         props = {r["Key"]: r["Value"] for r in _rows(cur, "SHOW PROPERTY")}
     except pymysql.MySQLError as e:
@@ -187,7 +201,7 @@ def max_user_connections(cur: Any, secrets: Iterable[str]) -> str:
     return props.get("max_user_connections", "?")
 
 
-def run_probe(cur: Any, probe: Probe, secrets: Iterable[str]) -> Result:
+def run_probe(cur: Any, probe: Probe, secrets: Secrets) -> Result:
     name = f"probe {probe.name}"
     try:
         _rows(cur, probe.sql)
@@ -229,43 +243,161 @@ def upstream_store_init(settings: Settings, workspace: str) -> tuple[bool, str]:
         clear_service_credentials()
 
 
-def _mask(text: str, secrets: Iterable[str]) -> str:
+def _mask(text: str, secrets: Secrets) -> str:
     for s in secrets:
-        if s:
+        if isinstance(s, re.Pattern):
+            text = s.sub("<ip>", text)
+        elif s:
             text = text.replace(s, MASK)
     return text
 
 
+def _inline(sql: str, params: Sequence[Any] | None) -> str:
+    """Fill %s with quoted literals; only plain identifiers (the workspace name) are accepted."""
+    if not params:
+        return sql
+    parts = sql.split("%s")
+    if len(parts) != len(params) + 1:
+        raise ValueError(f"{len(parts) - 1} placeholders for {len(params)} parameters")
+    for value in params:
+        if not (isinstance(value, str) and _LITERAL_RE.match(value)):
+            raise ValueError("RuntimeCursor only inlines letters, digits and '_'")
+    return parts[0] + "".join(f"'{value}'{rest}" for value, rest in zip(params, parts[1:]))
+
+
+def _tool_error(body: Mapping[str, Any]) -> pymysql.MySQLError:
+    """execute_query's error reply as a pymysql error; upstream puts str(pymysql error) in the message."""
+    error = body.get("error") if isinstance(body.get("error"), dict) else {}
+    code, message = str(error.get("code") or "ERROR"), str(error.get("message") or "")
+    try:
+        parsed = ast.literal_eval(message)  # "(1105, 'errCode = 2, ...')"
+    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
+        parsed = None
+    if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[0], int):
+        return pymysql.err.OperationalError(parsed[0], str(parsed[1]))
+    return pymysql.err.OperationalError(0, f"{code}: {message}" if message else code)
+
+
+class RuntimeCursor:
+    """The cursor subset the read-only checks use, over the Runtime's execute_query tool."""
+
+    def __init__(self, run_sql: Callable[[str], Mapping[str, Any]]) -> None:
+        self._run_sql, self._rows = run_sql, []
+
+    def __enter__(self) -> RuntimeCursor:
+        return self
+
+    def __exit__(self, *exc: object) -> bool:
+        return False
+
+    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
+        body = self._run_sql(_inline(sql, params))
+        if body.get("success") is not True:
+            raise _tool_error(body)
+        rows = (body.get("data") or {}).get("rows")
+        if not isinstance(rows, list):
+            raise pymysql.err.OperationalError(0, "no rows in the execute_query reply")
+        self._rows = rows
+
+    def fetchall(self) -> list[dict[str, Any]]:
+        return self._rows
+
+
+class RuntimeConnection:
+    """pymysql-like connection for --url: one MCP session (one Runtime microVM) for the whole run.
+
+    fastmcp keeps the session in its own task, so it stays open between the synchronous calls.
+    """
+
+    def __init__(self, client: Any, tool: str = "execute_query") -> None:
+        self._client, self._tool = client, tool
+        self._runner = asyncio.Runner()
+        try:
+            self._runner.run(client.__aenter__())
+        except BaseException:
+            self._runner.close()
+            raise
+
+    def run_sql(self, sql: str) -> dict[str, Any]:
+        result = self._runner.run(self._client.call_tool(self._tool, {"sql": sql}, raise_on_error=False))
+        try:
+            body = json.loads("".join(getattr(c, "text", "") for c in result.content))
+        except ValueError:
+            body = None
+        return body if isinstance(body, dict) else {"success": False, "error": {"code": "NOT_JSON"}}
+
+    def cursor(self) -> RuntimeCursor:
+        return RuntimeCursor(self.run_sql)
+
+    def close(self) -> None:
+        try:
+            self._runner.run(self._client.__aexit__(None, None, None))
+        finally:
+            self._runner.close()
+
+
+def _runtime_connection(url: str, region: str | None) -> RuntimeConnection:
+    """SigV4 MCP session to a Runtime invoke URL (inbound auth AWS_IAM), see scripts/agentcore_client.py."""
+    scripts = str(ROOT / "scripts")
+    if scripts not in sys.path:
+        sys.path.insert(0, scripts)
+    import agentcore_client
+    return RuntimeConnection(agentcore_client.sigv4_client(url, region))
+
+
 def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None,
          connect: Callable[..., Any] = pymysql.connect, out: TextIO = sys.stdout, err: TextIO = sys.stderr,
-         store_init: Callable[[Settings, str], tuple[bool, str]] = upstream_store_init) -> int:
+         store_init: Callable[[Settings, str], tuple[bool, str]] = upstream_store_init,
+         remote_connect: Callable[[str, str | None], Any] | None = None) -> int:
     parser = argparse.ArgumentParser(description="Check the Doris privileges of mcp_svc.")
     parser.add_argument("--models", type=Path, default=MODELS_DIR, help="semantic YAML directory (tables)")
     parser.add_argument("--workspace", default="ecom", help="semantic workspace")
+    parser.add_argument("--url", help="deployed Runtime invoke URL: read-only checks through its execute_query")
+    parser.add_argument("--region", help="region of --url (default: from the URL)")
+    parser.add_argument("--expect-host", help="the identity must be 'mcp_svc'@'HOST' (P3 / T3.5: 172.31.%%)")
     args = parser.parse_args(argv)
     env = os.environ if env is None else env
 
     if not _WORKSPACE_RE.match(args.workspace):
         print(f"ERROR: workspace must match {_WORKSPACE_RE.pattern}", file=err)
         return 2
-    try:
-        settings = load_settings(env)
-    except SettingsError as e:
-        print(f"ERROR: {e}", file=err)
+    if args.region and not args.url:
+        print("ERROR: --region only applies with --url", file=err)
         return 2
+    if args.url and env.get("APPLY") == "1":
+        print("ERROR: APPLY=1 needs a direct connection: the probes cannot go through the Runtime's "
+              "read-only execute_query (drop --url)", file=err)
+        return 2
+    settings: Settings | None = None
+    if args.url:
+        secrets: list[str | re.Pattern[str]] = [env.get("DORIS_HOST", ""), _IPV4_RE]
+    else:
+        try:
+            settings = load_settings(env)
+        except SettingsError as e:
+            print(f"ERROR: {e}", file=err)
+            return 2
+        secrets = [settings.doris_password, settings.doris_host]
     tables = sorted(collect_physical_tables(args.models))
-    secrets = [settings.doris_password, settings.doris_host]
 
     def emit(text: str, stream: TextIO = out) -> None:
         print(_mask(text, secrets), file=stream)
 
     try:
-        conn = connect(host=settings.doris_host, port=settings.doris_port, user=settings.doris_user,
-                       password=settings.doris_password, connect_timeout=10, read_timeout=60,
-                       autocommit=True, cursorclass=pymysql.cursors.DictCursor)
+        if args.url:
+            conn = (remote_connect or _runtime_connection)(args.url, args.region)
+        else:
+            conn = connect(host=settings.doris_host, port=settings.doris_port, user=settings.doris_user,
+                           password=settings.doris_password, connect_timeout=10, read_timeout=60,
+                           autocommit=True, cursorclass=pymysql.cursors.DictCursor)
     except pymysql.MySQLError as e:
         emit(f"FAILED: connect: {e}", err)
         return 1
+    except Exception as e:  # noqa: BLE001 - --url: HTTP, SigV4 or MCP initialize failed
+        if not args.url:
+            raise
+        emit(f"FAILED: connect: {type(e).__name__}: {e}", err)
+        return 1
     results: list[Result] = []
     try:
         with conn.cursor() as cur:
@@ -273,7 +405,12 @@ def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
             if not identity.startswith(f"'{EXPECTED_USER}'@"):
                 emit(f"ERROR: this checks {EXPECTED_USER}; connected as {identity}", err)
                 return 2
-            emit(f"connected as {identity}")
+            emit(f"connected as {identity}" + (" (through the Runtime)" if args.url else ""))
+            if args.expect_host is not None:
+                want = f"'{EXPECTED_USER}'@'{args.expect_host}'"
+                results.append(Result(identity == want, "identity",
+                                      identity if identity == want else f"connected as {identity}, expected {want}"))
+                emit(_line(results[-1]))
             checks: list[tuple[str, Callable[[Any], Result]]] = [
                 ("grants", check_grants), ("databases", check_databases),
                 ("select", lambda c: check_select(c, tables, secrets)),
@@ -288,7 +425,10 @@ def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
             failed = sum(not r.ok for r in results)
 
             probes = write_probes(identity)
-            if env.get("APPLY") != "1":
+            if args.url:
+                emit("probes: not run with --url (execute_query takes read-only SQL only; they need a "
+                     "direct connection)")
+            elif env.get("APPLY") != "1":
                 emit("DRY-RUN probes (APPLY=1 to run; each write is a no-op if it were allowed):")
                 emit(f"  store_init         expect ok      upstream DorisStore('{args.workspace}') as {EXPECTED_USER}: "
                      "CREATE DATABASE/TABLE IF NOT EXISTS + metadata SELECT")
PATCH
```

- [ ] **Step 5：运行测试，确认通过；提交离线部分**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 151 tests / OK
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 期望：Ran 53 tests / OK
for t in doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 期望：两行 all passed
bash scripts/check-secrets.sh | tail -1                                                              # 期望：check-secrets: OK (… files scanned)
git status --short
```
期望：`git status` 恰好列出 7 个文件：
- 1 个 `??`：`doris/02_mcp_user_vpc.sql`；
- 6 个 ` M`：`doris/admin_sql.py`、`doris/permission_matrix.py`，以及 `doris/test/` 下的 4 个测试。

```bash
bash scripts/check-secrets.sh
git add doris/02_mcp_user_vpc.sql doris/admin_sql.py doris/permission_matrix.py \
        doris/test/test_admin_sql.py doris/test/test_mcp_user_sql.py doris/test/test_permission_matrix.py doris/test/test-apply-admin-sql.sh
git commit -m "feat(p3): T3.5 02_mcp_user_vpc.sql; admin_sql DROP USER IF EXISTS for a host migration; permission_matrix --url / --expect-host

The DROP is allowed only after a CREATE USER of another identity of the same user and never for an
identity the script sets up, so the account always has a working identity. permission_matrix --url
runs the read-only checks through the Runtime's execute_query: after the move that is the only place
mcp_svc can log in from.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6：dry-run 迁移脚本**（不连 Doris）

```bash
bash doris/apply-admin-sql.sh doris/02_mcp_user_vpc.sql; echo "exit=$?"
```
期望（spec 阶段实测）：
```
DRY-RUN SQL: CREATE USER IF NOT EXISTS 'mcp_svc'@'172.31.%' IDENTIFIED BY '***'
DRY-RUN SQL: ALTER USER 'mcp_svc'@'172.31.%' IDENTIFIED BY '***'
DRY-RUN SQL: GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'172.31.%'
DRY-RUN SQL: GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'172.31.%'
DRY-RUN SQL: DROP USER IF EXISTS 'mcp_svc'@'%'
DRY-RUN: 5 statements as root; APPLY=1 to execute
exit=0
```

- [ ] **Step 7：迁移前经 Runtime 复核**（只读；新的 MCP session）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
.venv/bin/python doris/permission_matrix.py --url "$RUNTIME_URL" --expect-host '172.31.%' 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
```
期望。spec 阶段在本机 server 上用同样的代码实测，只有 identity 一行来自推导：
```
connected as 'mcp_svc'@'%' (through the Runtime)
FAIL  identity: connected as 'mcp_svc'@'%', expected 'mcp_svc'@'172.31.%'
ok    grants: exactly internal.ecom SELECT, internal.system_mcp SELECT+CREATE (+ Doris defaults)
ok    databases: ecom, information_schema, mysql, system_mcp
ok    select: 9 physical tables of the models
ok    semantic store: workspace ecom semantic_version=3, 10 active files
info  max_user_connections=100
probes: not run with --url (execute_query takes read-only SQL only; they need a direct connection)
4/5 checks pass
exit=1
```
这一步证明两件事：
- 经 Runtime 的只读检查能跑通；
- 迁移前 `--expect-host` 确实会失败（Review Focus 5）。

如果除了 identity 还有别的 `FAIL`，**先停下来**：迁移之后要用同样的检查确认新身份，现在就得全部通过。

- [ ] **Step 8：GATE —— 展示并等待确认**

向用户展示 Step 6、Step 7 的输出，并说明：
- 效果：以 root 执行 5 条语句。
  - 新建 `'mcp_svc'@'172.31.%'`：密码不变，来自 Secrets Manager `doris-mcp/mcp_svc`，只在内存里填进 SQL；
  - 授权与 `'%'` 相同；
  - 最后删除 `'mcp_svc'@'%'`。
- 费用：无。
- 影响：
  - Runtime 的新 session 以新身份登录，Doris 看到的来源地址都在 `172.31.`（T3.3、T3.4 的 `conns` 已经确认）；
  - 已经在运行的 microVM 的池连接是以旧身份登录的。没有客户端会再用这些 session：Gateway 对每次调用都新开 session，Quick 在 P4 才接入。这些连接最迟 600 s 后被 Doris 回收（P-09）；
  - **开发机从此不能以 `mcp_svc` 登录**（1045）；
  - `demo_ro` 和 root 不受影响。
- 如果中途 `FAILED`：
  - `admin_sql` 在第一条失败的语句处停下，后面的语句（包括 DROP）都不执行；
  - 但如果 CREATE 已经成功，新身份会优先匹配 Runtime 的新连接，而它的授权可能还不完整。所以先停下来，把输出给用户看。修好原因后重跑 02 是最直接的恢复方式，它是幂等的，同样需要 GATE。
- 回滚（也需要 GATE）：`APPLY=1 bash doris/apply-admin-sql.sh doris/01_mcp_user.sql`，重建 `'mcp_svc'@'%'`，密码和授权不变。
  - `'172.31.%'` 会保留：它比 `'%'` 更具体，权限相同，没有坏处。
  - 如果也要删掉它，写一个与 02 对称的脚本：先 CREATE `'%'`，再 DROP `'172.31.%'`。白名单允许这样做，同样需要 GATE。

用户明确确认后执行：
```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
APPLY=1 bash doris/apply-admin-sql.sh doris/02_mcp_user_vpc.sql 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
```
期望：
- 5 行 `ok: …`，内容与 dry-run 相同，密码为 `***`；
- 然后一行 `grants: 'mcp_svc'@'172.31.%' | …`，只有这一个身份；
- DatabasePrivs 与 P2 T2.2 的 `'%'` 相同：`internal.ecom: Select_priv`、`internal.system_mcp: Select_priv,Create_priv`，加上 Doris 默认的 `internal.information_schema: Select_priv`、`internal.mysql: Select_priv`，顺序可能不同；
- workload group `normal: Usage_priv`；
- `exit=0`。

如果 harness 拦住了这条命令，请用户在提示符里输入 `! APPLY=1 bash doris/apply-admin-sql.sh doris/02_mcp_user_vpc.sql` 自己执行。这个脚本本身把密码和 Doris 地址都 mask 成 `***`。

- [ ] **Step 9：迁移后经 Runtime 复核**（只读；新的 MCP session）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
.venv/bin/python doris/permission_matrix.py --url "$RUNTIME_URL" --expect-host '172.31.%' 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
```
期望：
```
connected as 'mcp_svc'@'172.31.%' (through the Runtime)
ok    identity: 'mcp_svc'@'172.31.%'
ok    grants: exactly internal.ecom SELECT, internal.system_mcp SELECT+CREATE (+ Doris defaults)
ok    databases: ecom, information_schema, mysql, system_mcp
ok    select: 9 physical tables of the models
ok    semantic store: workspace ecom semantic_version=3, 10 active files
info  max_user_connections=100
probes: not run with --url (execute_query takes read-only SQL only; they need a direct connection)
5/5 checks pass
exit=0
```
- `max_user_connections` 是 Doris 按用户名保存的属性，删除一个身份不影响它，所以仍然是 100。
- 写探针不重跑：它们只能直连，而开发机已经不能以 `mcp_svc` 登录。P2 T2.3 已经确认 9 个写操作全部被拒；新身份的授权与旧身份逐项相同，这由 Step 8 的 `grants:` 行和这里的 `ok grants` 保证。

如果仍然 `connected as 'mcp_svc'@'%'`：说明 DROP 没有生效，或者这个 session 复用了旧的 microVM。先停下来，把 Step 8 的输出给用户看。

- [ ] **Step 10：确认开发机不能再以 `mcp_svc` 登录**（只读；凭证经 Secrets Manager）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  unset DORIS_ROOT_USER DORIS_ROOT_PASSWORD DORIS_RO_USER DORIS_RO_PASSWORD DORIS_ADMIN_PASSWORD DORIS_USER DORIS_PASSWORD
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_SECRET_ID=doris-mcp/mcp_svc AWS_REGION=us-east-1
  exec .venv/bin/python doris/permission_matrix.py ) 2>&1 | sed -E "$MASK" | cut -c1-160; echo "exit=${PIPESTATUS[0]}"
```
期望：
- 一行 `FAILED: connect: (1045, "Access denied for user …`；
- `exit=1`。

说明：
- 消息里的 Doris 地址由脚本 mask 成 `***`，开发机的 IP 由 sed mask 成 `<ip>`。
- 如果 errno 不是 1045，但仍然是拒绝登录（例如 1130），也算符合预期，记进 progress。
- 如果连接成功了（`connected as …`）：说明来源地址匹配到了 `'172.31.%'`，或者 `'%'` 还在。**先停下来**，把输出给用户看。

- [ ] **Step 11：Doris 连接的来源和空闲时长**（只读）

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
.venv/bin/python scripts/mcp_smoke.py --url "$RUNTIME_URL" --sigv4 conns --expect-host-prefix 172.31. --max-idle 610 2>&1 \
  | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
```
期望：
- `connections: N (Query 1, Sleep N-1) from M distinct hosts; users mcp_svc; max idle S s`；
- `[PASS] host prefix 172.31.: N/N connections`；
- `[PASS] idle connections <= 610 s: 0 over`；
- `exit=0`。

`N` 包括 Step 7 的旧 session 留下的旧身份连接，它们在 600 s 内会被回收。`SHOW PROCESSLIST` 只显示用户名，不区分身份。把 `N`、`M`、`S` 记进 progress。

- [ ] **Step 12：对账：指标经 Runtime（新身份），参照 SQL 用 `demo_ro`**（只读）

命令与 T3.3 Step 10 相同：

```bash
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ "]+#<url>#g'
source infra/state.env
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_USER="$DORIS_RO_USER" DORIS_PASSWORD="$DORIS_RO_PASSWORD" AWS_REGION=us-east-1
  unset DORIS_ROOT_USER DORIS_ROOT_PASSWORD DORIS_RO_USER DORIS_RO_PASSWORD DORIS_ADMIN_PASSWORD
  exec .venv/bin/python doris/reconcile.py mcp --url "$RUNTIME_URL" ) 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
```
期望：
```
published metrics: 22 match /home/ubuntu/AI-code/Doris-mcp-skill-Demo/doris/semantic/ecom
ok    ytd_totals (1 rows)
ok    monthly_2026 (9 rows)
ok    yoy_2026 (9 rows)
ok    channel_ytd (4 rows)
ok    area_ytd (7 rows)
ok    mini_program_quarterly (7 rows)
ok    cat1_items_ytd (12 rows)
ok    brand_tier_ytd (3 rows)
ok    refund_rate_5_1 (2 rows)
ok    reviews_by_shop_type_ytd (4 rows)
ok    refunds_by_reason_ytd (10 rows)
11/11 cases match
exit=0
```
这是新身份下语义层的读取和 `query_metric` 的端到端检查：`system_mcp` 的 SELECT 和 `ecom` 的 SELECT 都用到了。

- [ ] **Step 13：R-40 复核：安全组和 Runtime ENI**（AWS 只读）

```bash
source infra/state.env
for sg in "$DORIS_SG" "$RT_SG" "$VPCE_SG"; do
  printf '%s %s: ' "$sg" "$(aws ec2 describe-security-groups --region us-east-1 --group-ids "$sg" --query 'SecurityGroups[0].GroupName' --output text)"
  aws ec2 describe-security-group-rules --region us-east-1 --filters Name=group-id,Values="$sg" \
    --query "length(SecurityGroupRules[?!IsEgress && (CidrIpv4=='0.0.0.0/0' || CidrIpv6=='::/0')])" --output text
done
aws ec2 describe-security-group-rules --region us-east-1 --filters Name=group-id,Values="$DORIS_SG" \
  --query "SecurityGroupRules[?!IsEgress].[IpProtocol, FromPort, ToPort, CidrIpv4 || ReferencedGroupInfo.GroupId]" --output text | sort
aws ec2 describe-network-interfaces --region us-east-1 --filters Name=group-id,Values="$RT_SG" \
  --query 'NetworkInterfaces[].[InterfaceType, join(`,`, Groups[].GroupId), Status]' --output text | sort | uniq -c
aws ec2 describe-instances --region us-east-1 --instance-ids "$DORIS_INSTANCE" \
  --query 'Reservations[0].Instances[0].[State.Name, join(`,`, SecurityGroups[].GroupName)]' --output text
```
期望（spec 阶段实测；ENI 的个数以实际为准）：
```
sg-0a02e336df4299888 doris-demo-sg: 0
sg-02e54e3ee60161793 doris-mcp-rt: 0
sg-0c405296a225090b5 doris-mcp-vpce: 0
tcp	22	22	13.125.9.110/32
tcp	8030	8030	13.125.9.110/32
tcp	8030	8030	sg-02e54e3ee60161793
tcp	9030	9030	13.125.9.110/32
tcp	9030	9030	sg-02e54e3ee60161793
      3 agentic_ai	sg-02e54e3ee60161793	in-use
running	doris-demo-sg
```
含义：
- 本系统的 3 个 SG 都没有 `0.0.0.0/0` 或 `::/0` 入站规则；
- Doris 的 9030/8030 只对开发机的 `/32` 和 Runtime 的 SG 开放，22 只对开发机开放。这些都是 P0 之前就有的规则，或者 P0 按 R-40 加的 SG 引用；
- Runtime 的 ENI 只挂 `doris-mcp-rt`；
- Doris 实例只挂 `doris-demo-sg`。

**VPC 范围的附带发现**（只读，不处理）：同一个 VPC 里有 4 个 `launch-wizard-*` SG 带 `0.0.0.0/0` 入站规则。它们不挂在任何 ENI 上，也不属于本系统：
- `sg-00236b997e0a1bbed`（launch-wizard-5）
- `sg-0ff551a6f5d256c19`（launch-wizard-1）
- `sg-0b8531c65bda78b8f`（launch-wizard-3）
- `sg-08a5ffe87e99db90f`（launch-wizard-4）

R-40 约束的是本系统的 SG，所以它们不影响 R-40。记进 progress，由用户决定是否清理。清理是修改安全组的操作，需要 GATE，不在本计划范围内。

如果前 3 行有不是 `0` 的，或者 Doris 的入站规则多了别的来源：**停下来**，不自行修改。

- [ ] **Step 14：FE 审计日志里有没有 `mcp_svc` 的明文密码**（用户侧，只输出计数）

P2 T2.2 和本任务 Step 8 都执行了 `CREATE USER` / `ALTER USER … IDENTIFIED BY`。Doris FE 会把执行过的语句写进 `fe.audit.log`，这台 Doris 上是 `/data/doris/fe/log/`，docker 挂载。较新的 Doris 版本会遮盖这类语句里的密码，但本项目没有核实过这个版本的行为。

这一步要登录 Doris 主机，所以由用户执行。请用户在提示符里输入下面这条命令（`!` 开头，`<ssh 目标>` 换成自己登录 Doris 主机的方式）：
- 密码经管道传给远端 `grep` 的 stdin，不进命令行参数，也不落盘；
- 命令只输出每个文件的命中数。

```bash
! aws secretsmanager get-secret-value --region us-east-1 --secret-id doris-mcp/mcp_svc --query SecretString --output text | python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])' | ssh <ssh 目标> 'sudo grep -cF -f - /data/doris/fe/log/fe.audit.log*'
```
期望：每个文件都是 `…:0`。

另外可以请用户看一下这类语句的条数，确认审计日志确实记录了它们。这条命令同样只输出计数：
```bash
! ssh <ssh 目标> 'sudo grep -c "IDENTIFIED BY" /data/doris/fe/log/fe.audit.log*'
```

判断：
- 全是 `0`，而且 `IDENTIFIED BY` 的条数大于 0：说明 Doris 遮盖了密码。记进 progress，这一项关闭。
- 全是 `0`，`IDENTIFIED BY` 的条数也是 0：说明审计日志没有记录这类语句，或者已经滚动掉了。同样记进 progress，这一项关闭。
- 有不是 `0` 的：**停下来**，不要打印这些行，把计数给用户看。
  - 轮换密码是另外的 GATE：
    1. 在 Secrets Manager 写入新值；
    2. 重跑 02，由其中的 `ALTER USER` 改密码；
    3. Runtime 的新 microVM 启动时读取新值。
  - 但 `ALTER USER` 同样会被审计。如果 Doris 不遮盖，轮换之后新密码也会出现在日志里。所以要和用户一起决定怎么处理，例如在 Doris 主机上清理这些行，或者调整 FE 的审计配置。本计划不执行。

- [ ] **Step 15：收尾**

- 勾选 T3.5。
- progress「当前状态」：
  - T3.5 完成；P3 的全部任务完成，下一步是 P3 整体评审，然后由用户决定合并和推送（D8）；
  - 「Doris 变更」加上：`'mcp_svc'@'172.31.%'` 替换了 `'%'`；回滚是重跑 `01_mcp_user.sql`（GATE）。
- 日志记录：
  - Step 3 的失败数、Step 5 的测试数；
  - Step 7 和 Step 9 的结果；
  - Step 8 的 `grants:` 行，以及用户确认 GATE 的原话；
  - Step 10 的 errno；
  - Step 11 的 `N`、`M`、`S`；
  - Step 12 的对账结果；
  - Step 13 的 SG 计数和 launch-wizard 的附带发现；
  - Step 14 用户给出的计数。

```bash
bash scripts/check-secrets.sh
git add specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "docs(p3): T3.5 mcp_svc moved to '172.31.%': 5/5 through the Runtime, dev box 1045, reconcile 11/11, R-40 review

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T3.6：关闭 T3.5 遗留的 7 个 minor（P3 整体评审之后补充）

P3 整体评审之后，用户要求「关闭 T3.5 留下的minor」。这 7 条来自 progress「P3 整体评审（opus）」→「各任务评审遗留的 minor」里以 T3.5 开头的 7 行。其他任务遗留的 minor 和整体评审的 6 个 Minor 不在本任务范围内。
- 在分支 `p3-minors`（从 `main` 切出）上执行。
- 没有 GATE。除 Step 7（用户侧，只读，只输出计数）以外，不访问 AWS、Doris、Runtime。
- 执行方式：native（控制方自己按 TDD 执行），完成后由一个 opus reviewer 评审。

| # | minor | 改动 | 测试 |
|---|---|---|---|
| 1 | `admin_sql` 不要求 DROP 放在最后：`CREATE X; DROP '%'; GRANT … TO X` 会被接受；单独调用 `render()` 时，孤立的 DROP 也会被接受 | `_check_drops` 规定 DROP 之后不能再有 CREATE / ALTER / GRANT；`render()` 也调用 `_check_drops` | `test_a_statement_after_a_drop_is_refused`、`test_render_applies_the_drop_rules` |
| 2 | `permission_matrix --url` 的错误输出不 mask Runtime URL | `--url` 模式的 `secrets` 加上 `args.url`（替换成 `***`） | `test_the_runtime_url_is_masked` |
| 3 | `finally` 里的 `conn.close()` 没有保护：`__aexit__` 的传输错误会打印原始 traceback（可能含 URL），并覆盖结果 | 捕获 `Exception`，输出一行 mask 过的 `WARN: close: …` 到 stderr，exit code 保持原来的结果 | `test_a_failed_close_is_one_masked_warning_and_keeps_the_result`（结果 0 和 1 各一个 subTest） |
| 4 | `test_a_session_failure_is_one_masked_line` 的 fixture 用了真实的 Doris 私网 IP | 换成 TEST-NET 的 `198.51.100.7`，断言不变（`--url` 模式把 IPv4 mask 成 `<ip>`）。改前改后都通过，所以没有红灯 | 该测试本身；验证方法：测试文件里命中私网 IP 的行数从 1 变成 0 |
| 5 | FE 审计日志一项在没有 `IDENTIFIED BY` 条数的情况下就关闭了 | 用户侧补充计数（Step 7） | — |
| 6 | T3.5 日志的只读调用清单漏了 Step 7 / 9 / 11 / 12 的 SigV4 `InvokeAgentRuntime` | 日志只追加不修改，所以在本任务的日志里写一条更正 | — |
| 7 | (a) `test_default_remote_connect_uses_the_sigv4_client` 把 `scripts/` 留在了 `sys.path` 上；(b) `RuntimeCursor.execute` 遇到不是 dict 的 `data` 会 AttributeError | (a) `addCleanup(sys.path.remove, …)`；(b) 只有 `data` 是 dict 时才取 `rows`，否则是 `no rows` 的 `OperationalError` | (a) 只改测试本身，没有红灯；验证方法：单独运行该测试前后比较 `sys.path`。(b) `test_a_reply_that_is_not_a_result_is_an_error` 扩成 4 个 subTest |

**Files:**
- Modify: `doris/admin_sql.py`（docstring、`render`、`_check_drops`、`main` 的注释）
- Modify: `doris/permission_matrix.py`（docstring、`RuntimeCursor.execute`、`main` 的 `secrets` 和 `finally`）
- Test: `doris/test/test_admin_sql.py`（`DropUser` 加 2 个）、`doris/test/test_permission_matrix.py`（`RemoteRuntime` 加 2 个并改 1 个 fixture 和 1 处清理，`RuntimeCursor` 改 1 个）
- Modify: `specs/doris-mcp-quick/tasks.md`、`specs/doris-mcp-quick/progress.md`

- [ ] **Step 1：分支**

```bash
git switch -c p3-minors   # 从 main（f88a773）
```

- [ ] **Step 2：写失败测试**

`doris/test/test_admin_sql.py`，加在 `DropUser.test_dropping_another_user_is_refused` 之后：
```python
    def test_a_statement_after_a_drop_is_refused(self):
        # The old identity must not disappear while the new one is still being set up.
        sql = MIGRATE_SQL.replace("GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'172.31.%';\n", "") + \
            "GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'172.31.%';\n"
        rc, output, conn = run(sql=sql, apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("DROP USER 'mcp_svc'@'%' must come after every CREATE / ALTER / GRANT", output)
        self.assertEqual(conn.executed, [])

    def test_render_applies_the_drop_rules(self):
        stmts = admin_sql.load_statements(MIGRATE_SQL)
        for bad, why in ((stmts[-1:], "must follow a CREATE USER"),
                         ([stmts[0], stmts[2], stmts[1]], "must come after every CREATE / ALTER / GRANT")):
            with self.subTest(bad=bad), self.assertRaisesRegex(admin_sql.AdminSqlError, why):
                admin_sql.render(bad, {"MCP_SVC_PASSWORD": PW})
```

`doris/test/test_permission_matrix.py`：
- `RemoteRuntime.run_remote` 加参数 `close_error=None`，并用一个关闭时出错的 Client：
```python
    def run_remote(self, argv=(), doris=None, apply=False, remote_error=None, close_error=None):
        doris = doris or FakeDoris({"SELECT CURRENT_USER()": [{"identity": VPC_IDENTITY}]})
        remote_calls = []

        class CloseFails(Client):  # e.g. the session DELETE hits a transport error after the checks
            async def __aexit__(self, *exc_info):
                await super().__aexit__(*exc_info)
                raise close_error

        def remote_connect(url, region):
            remote_calls.append((url, region))
            if remote_error:
                raise remote_error
            return permission_matrix.RuntimeConnection((CloseFails if close_error else Client)(runtime_server(doris)))
```
- `test_a_session_failure_is_one_masked_line`：把 `ConnectionError("connect to …:443 failed")` 里的 IPv4 换成 `198.51.100.7`，断言不变。改的时候不要打印原来那一行，可以用：
```bash
.venv/bin/python - <<'EOF'
import re, pathlib
p = pathlib.Path("doris/test/test_permission_matrix.py")
lines = p.read_text(encoding="utf-8").split("\n")
n = 0
for i, line in enumerate(lines):
    if "ConnectionError(\"connect to " in line and ":443 failed" in line:
        new = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "198.51.100.7", line)
        n += new != line
        lines[i] = new
p.write_text("\n".join(lines), encoding="utf-8")
print("lines changed:", n)
EOF
```
- 在它后面加 2 个测试，并给 `test_default_remote_connect_uses_the_sigv4_client` 加上清理：
```python
    def test_the_runtime_url_is_masked(self):
        rc, out, err, _, _ = self.run_remote(remote_error=ConnectionError(f"POST {RUNTIME_URL} failed"))
        self.assertEqual(rc, 1)
        self.assertEqual(err.strip(), "FAILED: connect: ConnectionError: POST *** failed")

    def test_a_failed_close_is_one_masked_warning_and_keeps_the_result(self):
        # A passing run stays 0; the old identity with --expect-host stays 1.
        for doris, argv, rc_want, summary in ((None, [], 0, "4/4 checks pass"),
                                              (FakeDoris(), ["--expect-host", "172.31.%"], 1, "4/5 checks pass")):
            with self.subTest(rc_want=rc_want):
                rc, out, err, _, _ = self.run_remote(argv, doris=doris,
                                                     close_error=ConnectionError(f"DELETE {RUNTIME_URL} failed"))
                self.assertEqual(rc, rc_want, out + err)
                self.assertIn(summary, out)
                self.assertEqual(err.strip(), "WARN: close: ConnectionError: DELETE *** failed")

    def test_default_remote_connect_uses_the_sigv4_client(self):
        scripts = str(ROOT / "scripts")
        sys.path.insert(0, scripts)
        self.addCleanup(sys.path.remove, scripts)
        import agentcore_client
        # … the rest unchanged
```
- `RuntimeCursor.test_a_reply_that_is_not_a_result_is_an_error`：
```python
    def test_a_reply_that_is_not_a_result_is_an_error(self):
        for data in (None, "text", [{"identity": IDENTITY}], {"rows": "text"}):
            with self.subTest(data=data):
                with self.assertRaises(pymysql.MySQLError) as cm:
                    self.cursor({"success": True, "data": data}).execute("SELECT 1")
                self.assertIn("no rows", cm.exception.args[1])
```

- [ ] **Step 3：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s doris/test > /tmp/t36-red.log 2>&1
grep -E '^(FAIL|ERROR):' /tmp/t36-red.log | sed -E 's/ \(.*//' | sort -u
grep -E '^Ran|^FAILED|^OK' /tmp/t36-red.log
```
期望（实测）：
```
ERROR: test_a_failed_close_is_one_masked_warning_and_keeps_the_result
ERROR: test_a_reply_that_is_not_a_result_is_an_error
FAIL: test_a_statement_after_a_drop_is_refused
FAIL: test_render_applies_the_drop_rules
FAIL: test_the_runtime_url_is_masked
Ran 155 tests in …
FAILED (failures=4, errors=4)
```
失败原因：
- 放错位置的 DROP 被接受（`0 != 2`）；
- `render()` 的两个 subTest 都是 `AdminSqlError not raised`；
- URL 没有被 mask；
- `close()` 的 `ConnectionError` 直接抛出（2 个 subTest）；
- 不是 dict 的 `data` 导致 `AttributeError: 'str' / 'list' object has no attribute 'get'`（2 个 subTest）。

- [ ] **Step 4：实现**

`doris/admin_sql.py`：
```python
def render(statements: Sequence[str], values: Mapping[str, str]) -> list[str]:
    """Check every statement against the allowlist and the DROP rules, then fill ${NAME} placeholders."""

    def fill(m: re.Match[str]) -> str:
        if m.group(1) not in values:
            raise AdminSqlError(f"unknown placeholder ${{{m.group(1)}}}")
        return values[m.group(1)]

    _check_drops([_match(stmt) for stmt in statements])
    return [_PLACEHOLDER_RE.sub(fill, stmt) for stmt in statements]


def _check_drops(matches: Sequence[re.Match[str]]) -> None:
    """A DROP retires an old identity: another identity of the user is set up first, and nothing re-creates it."""
    kept = {m.group("ident") for m in matches if m.re is not _DROP}
    for i, m in enumerate(matches):
        if m.re is not _DROP:
            continue
        ident, user = m.group("ident"), m.group("user")
        if ident in kept:
            raise AdminSqlError(f"DROP USER {ident}: the script also creates or grants {ident}")
        if not any(c.re is _CREATE and c.group("user") == user for c in matches[:i]):
            raise AdminSqlError(f"DROP USER {ident} must follow a CREATE USER of another {user} identity")
        if any(c.re is not _DROP for c in matches[i:]):
            raise AdminSqlError(f"DROP USER {ident} must come after every CREATE / ALTER / GRANT")
```
- `main()` 里原来的 `_check_drops(matches)` 保留，加注释 `# before the secret is read; render() checks again`。
- 模块 docstring 的 DROP 一句改成：`…, only after a CREATE USER of another identity of that user, never of an identity the same script sets up, and only at the end of the script.`

`doris/permission_matrix.py`：
```python
        data = body.get("data")
        rows = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(rows, list):
```
```python
        secrets: list[str | re.Pattern[str]] = [args.url, env.get("DORIS_HOST", ""), _IPV4_RE]
```
```python
    finally:
        try:
            conn.close()
        except Exception as e:  # noqa: BLE001 - e.g. --url: the session DELETE failed; the result stands
            emit(f"WARN: close: {type(e).__name__}: {e}", err)
```
- 模块 docstring：`IPv4 addresses in the output are masked as <ip>` 改成 `the URL is masked as *** and IPv4 addresses as <ip>`。

- [ ] **Step 5：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 155 tests / OK
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 期望：Ran 53 tests / OK
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 期望：Ran 89 tests / OK
for t in doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh infra/test/test-35-runtime-role.sh \
         infra/test/test-40-doris-secret.sh infra/test/test-lib.sh scripts/test/test-check-secrets.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 期望：6 行 all passed
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3     # 期望：🎉 All tests passed!
```
7(a) 的验证（期望：`ok: True sys.path unchanged: True`）：
```bash
(cd doris/test && ../../.venv/bin/python - <<'EOF'
import sys, unittest
import test_permission_matrix as t
before = list(sys.path)
r = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromName(
    "RemoteRuntime.test_default_remote_connect_uses_the_sigv4_client", t))
print("ok:", r.wasSuccessful(), "sys.path unchanged:", sys.path == before)
EOF
)
```
4 的验证（只输出计数；私网 IP 取自 `agentcore.json`，不打印。期望：`0`，改动前是 `1`）：
```bash
v="$(.venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))')"
grep -cF -f <(printf '%s\n' "$v") doris/test/test_permission_matrix.py; unset v
```

- [ ] **Step 6：提交离线部分**

```bash
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add doris/admin_sql.py doris/permission_matrix.py doris/test/test_admin_sql.py doris/test/test_permission_matrix.py \
        specs/doris-mcp-quick/plans/P3-deploy.md specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "fix(p3): T3.6 T3.5 minors: DROPs last and checked in render(); --url masks the URL; guarded close(); TEST-NET fixture

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
然后派一个 opus reviewer 评审这个提交（评审包里的 IP / URL 都要 mask）。

- [ ] **Step 7：`IDENTIFIED BY` 的条数**（用户侧，只输出计数）

请用户执行 T3.5 Step 14 的第二条命令，只回复每个文件的计数：
```bash
! ssh <ssh 目标> 'sudo grep -c "IDENTIFIED BY" /data/doris/fe/log/fe.audit.log*'
```
判断（T3.5 Step 14 已确认每个文件的密码命中都是 0）：
- 条数大于 0：说明审计日志记录了这类语句，并且遮盖了密码。minor 5 关闭。
- 条数都是 0：说明审计日志没有记录这类语句。T3.5 Step 8 是 2026-09-27 执行的，不太可能已经滚动掉。这种情况下密码不会经审计日志泄漏，minor 5 同样关闭，但要在日志里写明「没有证明 Doris 会遮盖密码」。

- [ ] **Step 8：收尾**

- 勾选 T3.6。
- progress：更新「当前状态」，并追加日志，记录这些内容：
  - Step 3 的失败数、Step 5 的测试数、4 和 7(a) 的验证结果；
  - minor 6 的更正；
  - Step 7 用户给出的计数；
  - 评审结论；
  - 在「P3 整体评审（opus）」对应的 7 行后面注明已由 T3.6 关闭。日志不改原文，只在新日志里写。
```bash
bash scripts/check-secrets.sh | tail -1
git add specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "docs(p3): T3.6 closed: FE audit IDENTIFIED BY count, review

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
合并方式和是否推送由用户决定（D8）。

---

## P3 完成标准（对照 design §11 P3 行）

- [ ] Runtime `dorismcp_dorismcp` 运行完整的 `mcp-server/`，`RUNTIME_ARN` 不变。执行角色是 `doris-mcp-runtime-role`：
  - 只能写 `runtimes/dorismcp_dorismcp-*` 日志组；
  - 只能 `GetSecretValue` `DORIS_SECRET_ARN` 这一个 secret；
  - CDK 角色和它的 DefaultPolicy 已删除，栈里没有 `AWS::IAM::Role`（T3.1、T3.2；R-31、R-41）。
- [ ] CodeZip 与 `.venv` 的 88 个 dist 版本一致，deploy 后对 staging 目录复核为 0 个不同（T3.2）。
- [ ] SigV4 直连冒烟通过：12 个工具、flow 6/6（T3.3）。
- [ ] Gateway token 冒烟通过：`doris___*` 12 个、flow 6/6（T3.4）。
- [ ] CloudWatch 能看到审计日志：
  - T3.3 的 24 个、T3.4 的 37 个调用逐工具都有记录；
  - 日志里没有 `mcp_svc` 的密码，没有 Traceback / ERROR（T3.3、T3.4；R-32）；
  - R-32 的缺口（请求没有执行到 `log_tool_call` 时没有审计记录）已写进 requirements v1.4，由用户决定是否在 P5 补上。
- [ ] 冷启动 + 典型查询 < 60 s：
  - T3.3 共享 session 和每次新 session 的逐次耗时都是 `0 over 60000 ms`；
  - T3.4 经 Gateway 串行 12 个、20 个并发 24 个都是 `0 errors, 0 over 60000 ms`；
  - P0 M-4 关闭：`mcp_smoke.py time` + `smoke_calls.json` 就是可重跑的探针（T3.3、T3.4；R-12）。
- [ ] 连接回收：
  - Doris 看到的来源都在 `172.31.`；
  - 并发之后的残留连接在空闲 600 s 后被 Doris 回收，在线验证了补丁 P-09（T3.4）。
- [ ] Gateway DEBUG 泄漏检查：6 类错误调用的返回里 IPv4、密码、Traceback 都是 0。`exceptionLevel=DEBUG` 保留到 T5.5，已更新 design §14（T3.4）。
- [ ] `mcp_svc` host 收紧为 `'172.31.%'`（T3.5；D6、R-42）：
  - 经 Runtime 的权限复核 5/5；
  - 开发机以 `mcp_svc` 登录被拒；
  - 对账 11/11。
- [ ] R-40 复核：本系统的 3 个 SG 没有 `0.0.0.0/0` / `::/0` 入站规则，Doris 的入站规则与 P0 相同。VPC 里 4 个未挂载的 `launch-wizard-*` SG 已记进 progress，由用户决定（T3.5）。
- [ ] FE 审计日志里 `mcp_svc` 密码的命中数为 0。如果不是 0，已停下来和用户商量处理方式（T3.5 Step 14，用户侧）。
- [ ] P2 整体评审的遗留事项全部关闭：
  - M1–M4：T3.0；
  - Runtime 角色的 GetSecretValue 只限 `DORIS_SECRET_ARN`：T3.1；
  - T3.5 的 host 迁移，以及 1045 的更正：T3.5；
  - FE audit log：T3.5 Step 14。
- [ ] P1 的「P3 时核对」全部有结论：
  - CodeZip 与 `.venv` 的依赖：T3.2；
  - 20 个并发对 `pool_max_size=5` 和 60 s 的影响：T3.4 Step 6（经 Gateway；spec 阶段本机共享 session 的对照结果也写在那里）；
  - R-32 的审计缺口：requirements v1.4。
- [ ] 测试全部通过：
  - `doris/test` 151 个；
  - `scripts/test` 53 个；
  - `mcp-server/test` 的 `test_agentcore_*.py` 89 个；
  - upstream 离线测试；
  - 6 组 shell 测试（`test-apply-admin-sql.sh`、`test-publish-semantic.sh`、`test-35-runtime-role.sh`、`test-40-doris-secret.sh`、`test-lib.sh`、`test-check-secrets.sh`）。
- [ ] P3 的提交里没有密码、Doris 主机地址和私网 IP：每个任务提交前 `check-secrets` 都是 OK，各任务的实测输出都经过 mask。
- [ ] P3 整体评审之后，由用户决定：合并方式，以及 P2 之后的提交和 P3 一起推送到私有仓库 `lijingfz/Doris-mcp-skill-Demo`（D8；用户已说「请等 P3 一起push」，推送前仍要再确认一次）。
