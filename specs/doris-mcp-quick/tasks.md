# 任务清单

> 勾选规则：任务的验收全部通过、改动已提交后才勾选 `[x]`。进行中的任务在 progress.md「当前状态」里写明。
> 标签：`[AI]` Claude 直接做 · `[AI+GATE]` 先 dry-run，用户确认后再执行 · `[USER]` 只能由用户操作。详见 `README.md`。
> 每个任务的具体步骤在「计划」列指向的 `plans/*.md` 章节。
> 「代码已起草」：代码在 spec 阶段已写好并验证过，完整内容嵌在计划里，执行时照计划落盘、跑测试、提交即可（仍需勾选验收）。

## P0 技术验证（计划：`plans/P0-spike.md`）

目标：在写业务代码之前，先把「网络 → Runtime → Gateway → Quick 桌面版」这条链路用最小 MCP 跑通。

| ✓ | ID | 标签 | 任务 | 需求 | 计划 |
|---|---|---|---|---|---|
| [x] | T0.1 | [AI] | 工具准备（agentcore CLI、uv、aws CLI 版本检查）+ `infra/lib.sh`（代码已起草）| R-61 | P0 §T0.1 |
| [x] | T0.2 | [AI+GATE] | `infra/10-network.sh`：2 个 SG + Doris SG 引用规则 + S3/logs/secretsmanager endpoints | R-40, R-44 | P0 §T0.2 |
| [x] | T0.3 | [AI] | spike MCP `spike/p0-mcp/`（`net_check` 工具）+ `scripts/mcp_smoke.py`，本地测试（代码已起草）| R-30 | P0 §T0.3 |
| [x] | T0.4 | [AI+GATE] | `agentcore create` 生成 `dorismcp/`，部署 spike runtime（VPC 模式），`infra/25-runtime-state.sh` 记录 Runtime ARN/URL，SigV4 冒烟，测冷启动 | R-30, R-11 | P0 §T0.4 |
| [x] | T0.5 | [AI+GATE] | `infra/20-cognito.sh`：user pool + 域名 + resource server + client A/B + 演示用户 | R-10, R-13 | P0 §T0.5 |
| [x] | T0.6 | [AI+GATE] | `infra/30-gateway.sh`：Gateway 服务角色 + Gateway（CUSTOM_JWT）+ target `doris`（IAM 出站），token 冒烟 | R-10, R-41 | P0 §T0.6 |
| [x] | T0.7 | [USER] | Quick 桌面版：Cloud Connector（User auth，再试 Service auth）+ Local stdio 连接器，各调用一次 `net_check`（Local stdio 未尝试；之后用户决定整个项目不做，见 D9）| R-10, R-11, R-13 | P0 §T0.7 |
| [x] | T0.8 | [AI] | 记录 P0 结论（回调 URL、scope 行为、冷启动耗时、CLI 差异），更新 design.md，编写 P1 前复核 | R-60 | P0 §T0.8 |

## P1 本地改造（计划：`plans/P1-mcp-server.md`）

目标：upstream + 8 处补丁，在本机用 `demo_ro` 连 Doris 公网 IP 跑通 12 个工具。P1 不依赖 P0 的结论，可与 P0 并行，也可以先做。
全部代码已在 spec 阶段起草并验证（77 个新测试 + upstream 离线测试通过；真实 Doris 上 flow 6/6），完整代码嵌在 `plans/P1-mcp-server.md`。

| ✓ | ID | 标签 | 任务 | 需求 | 计划 |
|---|---|---|---|---|---|
| [x] | T1.1 | [AI] | vendoring upstream @f235832 → `mcp-server/`，`pyproject.toml`（P-07），`.venv`，基线离线测试全部通过 | R-20 | P1 §T1.1 |
| [x] | T1.2 | [AI] | P-02：`ClusterConfig.fe_http_port` | R-23 | P1 §T1.2 |
| [x] | T1.3 | [AI] | P-03：store / bootstrap 服务账号兜底 | R-35 | P1 §T1.3 |
| [x] | T1.4 | [AI] | P-04：`create_server(service_credentials=, workspace_dir=)` | R-33, R-35 | P1 §T1.4 |
| [x] | T1.5 | [AI] | P-05：`src/tools/profile.py` + 单测（MockTransport）| R-22, R-23, R-24 | P1 §T1.5 |
| [x] | T1.6 | [AI] | P-06 `config/mcp-server.toml` + `agentcore_ext/settings.py` + `build_server`：注册 profile 工具，12 个工具 + Draft 7 校验测试 | R-12, R-20, R-31, R-33 | P1 §T1.6 |
| [x] | T1.7 | [AI] | P-01：`GET /ping`、stderr 日志、`main()`（配置错误 exit 2）、`mcp_server.py` + HTTP 测试 + 本地启动冒烟 | R-30, R-32, R-34 | P1 §T1.7 |
| [x] | T1.8 | [AI] | 本地 E2E：12 个工具、profile flow、3 种错误情况（`scripts/mcp_smoke.py flow`）| R-22–R-25 | P1 §T1.8 |

## P2 Doris 与语义层（计划：`plans/P2-doris.md`）

目标：备好 Runtime 需要的 Doris 侧前提 —— secret `doris-mcp/mcp_svc`、最小权限账号 `mcp_svc`、已发布到 `system_mcp` 的 `ecom` 语义层（10 个 YAML、22 个指标），并证明 `mcp_svc` 权限恰好是 R-42、`query_metric` 与故事线 SQL 到分一致。
全部代码已在 spec 阶段起草并验证（117 个 Python 测试 + 4 组 shell 测试通过；`demo_ro` 对真实 Doris 只读跑 `reconcile.py direct` 11/11），完整代码嵌在 `plans/P2-doris.md`。4 个 GATE 写操作在 spec 阶段都没有执行。
执行顺序 T2.1 → T2.4 → T2.5 → T2.2 → T2.3 → T2.6 → T2.7：root 发布（T2.5）会创建 `system_mcp` 库、3 张表和 `ecom` 的元数据行，所以 `mcp_svc` 不需要 LOAD_PRIV；T2.3 要检查已发布的 `ecom`。T2.7 是 P1 / P0 整体评审留下的小修，用户 2026-09-26 决定并入本阶段，放在最后（纯离线）。

| ✓ | ID | 标签 | 任务 | 需求 | 计划 |
|---|---|---|---|---|---|
| [x] | T2.1 | [AI+GATE] | `infra/40-doris-secret.sh`：Secrets Manager `doris-mcp/mcp_svc`（Secrets Manager 生成 32 位字母数字密码，不显示），ARN 写入 `state.env`；`scripts/check-secrets.sh` 增加块 1b：对 Secrets Manager 里的密码做精确值扫描 | R-31, R-43 | P2 §T2.1 |
| [x] | T2.2 | [AI+GATE] | `doris/01_mcp_user.sql` + `doris/admin_sql.py` + `doris/apply-admin-sql.sh`：root 建 `mcp_svc` 并授权（secret 经管道进入 python，只在内存里填进 SQL；语句白名单；输出 mask）| R-35, R-42 | P2 §T2.2 |
| [x] | T2.3 | [AI+GATE] | `doris/permission_matrix.py`：以 `mcp_svc` 检查 `SHOW GRANTS` 恰好是 R-42（+ Doris 默认项）、库列表、9 张表可读、`ecom` 已发布；GATE 后跑 upstream store 初始化（须成功）+ 9 个写探针（须全部被拒，每个即使被允许也不改变数据），14/14 | R-21, R-42 | P2 §T2.3 |
| [x] | T2.4 | [AI] | `doris/semantic/ecom/*.yaml`（10 个文件、22 个指标、time spine `dim_date`）+ `doris/reconcile.py`（11 个故事线对账用例）；`demo_ro` 只读跑 `direct` 模式 11/11 | R-26 | P2 §T2.4 |
| [x] | T2.5 | [AI+GATE] | `doris/publish_semantic.py` + `doris/publish-semantic.sh`（方案 C）：root 在本机进程内调用 upstream `DorisStore` 发布（离线校验 bootstrap + MetricFlow 引擎 + 重名，物理表校验，staging → commit → 回读比对）；不起 Web UI，不执行 upstream `commit_staging` 的 `GRANT … TO '%'` | R-26 | P2 §T2.5 |
| [x] | T2.6 | [AI] | `reconcile.py mcp`：以 `mcp_svc` 在进程内起 MCP server，`list_metrics`（22 个与本地一致）+ `query_metric` 与故事线 SQL 11/11 到分一致；全部离线测试 | R-26 | P2 §T2.6 |
| [x] | T2.7 | [AI] | P1 整体评审 ①–④：`get_query_profile` 的 profile 文本经 `mask_sensitive`；读 secret 失败时不链接原异常（`from None`）；`main()` 捕获 `build_server` 的异常（exit 2 + 一行 mask 后的日志）；非默认端口传到 `cfg.cluster` 和 FE URL 的测试。P0 整体评审 M-2（`quick/T0.7-guide.md` 取 secret 的命令改成单行）、M-8（根 `.gitignore` 的 staging 注释）| R-30, R-31, R-32（评审项）| P2 §T2.7 |

## P3 AgentCore 部署（计划：`plans/P3-deploy.md`）

目标：把 Runtime `dorismcp` 从 P0 的 spike 换成完整的 `mcp-server/`（12 个工具，以 `mcp_svc` 经 Secrets Manager 连 Doris 私网地址），执行角色换成只能写自己的日志、只能读 `doris-mcp/mcp_svc` 的专用角色；经 SigV4 直连和 Gateway 分别冒烟、测耗时和并发、核对审计日志；最后把 `mcp_svc` 的 host 收紧为 `'172.31.%'`。
全部代码已在 spec 阶段起草并验证（最终 `doris/test` 151 个、`scripts/test` 53 个、`test_agentcore_*.py` 89 个 + 6 组 shell 测试通过），并在 `178be68` 的干净 worktree 上按计划顺序回放过，完整代码嵌在 `plans/P3-deploy.md`。4 个 GATE（建 IAM 角色、deploy、同步 Gateway target、迁移 `mcp_svc` 的 host）在 spec 阶段都没有执行；只读预验证见计划的 Architecture。
执行顺序 T3.0 → T3.1 → T3.2 → T3.3 → T3.4 → T3.5：T3.0 是 P2 整体评审的遗留小修和补丁 P-09，必须在第一次 deploy 之前完成。T3.5 之后开发机不能再以 `mcp_svc` 登录（1045，预期行为）。T3.6 是 P3 整体评审之后补充的任务，在分支 `p3-minors` 上执行。

| ✓ | ID | 标签 | 任务 | 需求 | 计划 |
|---|---|---|---|---|---|
| [x] | T3.0 | [AI] | P2 整体评审遗留 M1–M4：两个 wrapper 先 `unset` 调用方 export 的 root / ro 变量；`permission_matrix.py` 只读检查失败时跳过探针、1105 要含 access / command denied、先 mask 再截断、重复对象合并、兜底 `except`；Secrets Manager client 构造失败也是 `SettingsError`；`check-secrets.sh` 读不到 secret 时失败。补丁 P-09：池连接 `SET wait_timeout = 600`（design §5.2、§13）| R-30, R-31, R-42, R-43 | P3 §T3.0 |
| [x] | T3.1 | [AI+GATE] | `infra/35-runtime-role.sh` 建专用执行角色 `doris-mcp-runtime-role`：只能写 `runtimes/dorismcp_dorismcp-*` 日志组，只能 `GetSecretValue` `DORIS_SECRET_ARN` 这一个 secret；`scripts/render-agentcore.py --phase server` 把它写进 `agentcore.json` 的 `executionRoleArn`（CDK 导入它，不再生成角色、不附加策略；不在 CDK 之外改角色）（design §7、§14）| R-31, R-41 | P3 §T3.1 |
| [x] | T3.2 | [AI+GATE] | `agentcore.json`：codeLocation 改为 `../mcp-server/`，envVars 加 `DORIS_SECRET_ID`、`PROFILE_SCOPE`，执行角色换成 T3.1 的角色，重新部署（删除 CDK 角色，Runtime 原地更新，`RUNTIME_ARN` 不变）；锁定 `caio`、`platformdirs`，CodeZip 与 `.venv` 的 88 个 dist 一致；deploy 前确认 `~/.agentcore/config.json` 有 `"disableTransactionSearch": true`，否则 deploy 会改账号级 X-Ray 设置（design §13）| R-30 | P3 §T3.2 |
| [x] | T3.3 | [AI] | SigV4 直连冒烟（12 个工具 + flow）；CloudWatch 能看到审计日志；冷启动 + 典型查询 < 60 s（共享 session 和每次新 session 逐次测）；`reconcile.py mcp --url` 11/11；Doris 连接来源都在 `172.31.` | R-12, R-32 | P3 §T3.3 |
| [x] | T3.4 | [AI+GATE] | `synchronize-gateway-targets`；Gateway token 冒烟（`doris___*` 共 12 个）；经 Gateway 每次调用都是冷启动，逐次记录耗时（12 个工具，含 `check_service_health` 和语义工具）并跑 20 个并发（design §13）；测耗时的探针脚本收进仓库，可重复运行（P0 评审 M-4：`mcp_smoke.py time` + `scripts/smoke_calls.json`）；残留连接 600 s 后被回收（P-09）；Gateway DEBUG 泄漏检查（design §14）| R-10, R-12 | P3 §T3.4 |
| [x] | T3.5 | [AI+GATE] | `mcp_svc` host 收紧为 `'172.31.%'`（D6）：`doris/02_mcp_user_vpc.sql` 先建新身份并授权，最后 `DROP USER IF EXISTS 'mcp_svc'@'%'`；经 Runtime 复核权限 5/5、对账 11/11，开发机登录得到 1045；R-40 只读复核；用户侧检查 FE 审计日志里有没有明文密码（只输出计数）| R-42, R-40 | P3 §T3.5 |
| [x] | T3.6 | [AI] | P3 整体评审之后补充：关闭 T3.5 遗留的 7 个 minor。`admin_sql` 的 DROP 必须放在最后，`render()` 也检查 DROP 规则；`permission_matrix --url` mask Runtime URL；`conn.close()` 失败时只输出一行 mask 过的 WARN，结果不变；测试 fixture 换成 TEST-NET 地址；测试清理 `sys.path`；`RuntimeCursor` 遇到不是 dict 的 `data` 也按 `no rows` 处理；更正 T3.5 日志的只读调用清单；用户侧补充 FE 审计日志 `IDENTIFIED BY` 的条数（只输出计数）| R-42（评审项）| P3 §T3.6 |

## P4 Quick 桌面版（计划：`plans/P4-quick.md`）

目标：把 12 个工具接进 Quick 桌面版。两个 Cloud Connector 同步后按 D7 设置权限；两个「Doris 专家」agent 用同一份指令，各跑一次「开场 + 第 2 幕」。同时核实 scope 行为（P0 评审 M-1），记录 Quick 侧耗时（M-3）。
代码（T4.5 的 mask 收口、T4.3 的指令和检查、T4.6 的 Gateway 耗时探针）已在 spec 阶段起草，并在 `96d18ce` 的干净 worktree 上按计划顺序回放过：最终 `doris/test` 161 个、`scripts/test` 75 个、`quick/test` 16 个、`test_agentcore_*.py` 89 个，6 组 shell 测试通过。完整代码嵌在 `plans/P4-quick.md`。P4 没有 GATE：Quick 里的操作由用户执行，AI 侧只做只读核对。
执行顺序 T4.5 → T4.3 → T4.6 → T4.1 + T4.4（用户一次做完），在分支 `p4-quick` 上执行。

| ✓ | ID | 标签 | 任务 | 需求 | 计划 |
|---|---|---|---|---|---|
| [ ] | T4.1 | [USER] | Cloud Connector Sync → 逐个启用 12 个工具，按 D7 设置权限；核实 Quick 是否按 PRM 请求 scope，并据此修正 design 里的 scope 结论（P0 评审 M-1：请求不带 scope 时 Cognito 会授予 client 的全部 scope，P0 登录成功不能证明 Quick 请求了 scope）。AI 侧先做只读预检（Gateway / target READY，经 Gateway 列出 12 个工具并跑参照查询，对账 11/11），事后核对审计日志、连接数和 CloudTrail | R-10 | P4 §T4.1 + T4.4 |
| [ ] | T4.3 | [AI] | 编写「Doris 专家」agent 指令 `quick/agent-instructions.md`：≤ 5 万字符，分角色、硬约束、演示口径三段（design §8.3），由 `quick/test/test_agent_instructions.py` 的 16 个检查锁住（含指标名、维度名与语义层一致） | R-51 | P4 §T4.3 |
| [ ] | T4.4 | [USER] | 桌面版创建 Agent，跑「开场 + 第 2 幕」（User auth、Service auth 两个连接器各一次；Local stdio 按 D9 取消，原 T4.2 已删除）；两个连接器各建一个 agent；记录 Quick 侧每个问题的总耗时（秒表）和每次工具调用的耗时（`gw_latency.py`）（P0 评审 M-3：P0 只测了 Gateway 侧）；答案与参照值对照 | R-10, R-13 | P4 §T4.1 + T4.4 |
| [ ] | T4.5 | [AI] | P3 整体评审和 T3.6 的遗留：<br>`scripts/redact.py` 统一 mask：字面 secret 换成 `***`（长的先换），再把 IPv4 换成 `<ip>`，并接管 MCP SDK 自己的日志行；<br>`mcp_smoke`、`reconcile mcp --url`、`permission_matrix --url` 的错误输出 mask URL 和 token；<br>`agentcore_client` 的 ValueError 不回显 URL，docstring 更正；<br>两处 lazy `sys.path` 改成模块顶部一次；<br>`permission_matrix` 直连模式 mask 拒绝消息里的客户端地址（T3.0 minor）；<br>补 T3.6 M2 的 2 个测试。<br>spec 小修（design §7 / §13、RESUME、tasks 的 T5.5 行）随计划在 Step 1 提交 | R-43（评审项）| P4 §T4.5 |
| [ ] | T4.6 | [AI] | `scripts/gw_latency.py`：从 CloudWatch 取 Gateway `tools/call` 每分钟、每个工具的调用数、平均耗时和最大耗时。≥ 45 s 标 WARN（留给 T5.5），≥ 60 s 失败；只输出工具名、时间和毫秒数（P0 评审 M-3）| R-12 | P4 §T4.6 |

## P5 Skills 与彩排（计划：`plans/P5-skills.md`）

| ✓ | ID | 标签 | 任务 | 需求 |
|---|---|---|---|---|
| [ ] | T5.1 | [AI] | 锁定 apache/doris-skills commit；生成导入副本（加 adapter 提示行）到 `quick/skills/` | R-50 |
| [ ] | T5.2 | [AI] | 编写 `quick/skills/doris-mcp-adapter/SKILL.md`（翻译表、工具名前缀、profile 约定、60 s 限制）| R-50 |
| [ ] | T5.3 | [USER] | 桌面版导入 skills，验证 adapter 能被自动选中 | R-50 |
| [ ] | T5.4 | [USER] | 完整彩排 × 2（design §10）。彩排前按 D7 把 `execute_query` 改成 Always Allow；记录每步耗时和问题（每次工具调用的耗时用 `gw_latency.py` 取）；每轮之后 AI 跑一次 `mcp_smoke conns`（连接预算）| R-51 |
| [ ] | T5.5 | [AI] | 根据彩排结果修正（skill / 指令 / 超时），准备演示前冒烟脚本和演示手册 `quick/runbook.md`（经 Gateway 预热无效，见 design §13）。同时决定：<br>Gateway `exceptionLevel` 是否关掉 DEBUG；<br>是否遮 2003 错误里的 Doris 主机地址（design §14）；<br>T4.4 / T5.4 出现单次工具调用 ≥ 45 s 时，把 `query_timeout` 调到 40–45 s；<br>重跑 `30-gateway.sh` 时补上 Gateway description（update 路径不传，现在是 `None`）。<br>演示前冒烟复用 `mcp_smoke`、`reconcile mcp --url`、`gw_latency.py` | R-51 |
| [ ] | T5.6 | [AI+GATE] | （演示结束后）`infra/99-cleanup.sh` | — |
