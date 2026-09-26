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
| [ ] | T0.2 | [AI+GATE] | `infra/10-network.sh`：2 个 SG + Doris SG 引用规则 + S3/logs/secretsmanager endpoints | R-40, R-44 | P0 §T0.2 |
| [ ] | T0.3 | [AI] | spike MCP `spike/p0-mcp/`（`net_check` 工具）+ `scripts/mcp_smoke.py`，本地测试（代码已起草）| R-30 | P0 §T0.3 |
| [ ] | T0.4 | [AI+GATE] | `agentcore create` 生成 `dorismcp/`，部署 spike runtime（VPC 模式），`infra/25-runtime-state.sh` 记录 Runtime ARN/URL，SigV4 冒烟，测冷启动 | R-30, R-11 | P0 §T0.4 |
| [ ] | T0.5 | [AI+GATE] | `infra/20-cognito.sh`：user pool + 域名 + resource server + client A/B + 演示用户 | R-10, R-13 | P0 §T0.5 |
| [ ] | T0.6 | [AI+GATE] | `infra/30-gateway.sh`：Gateway 服务角色 + Gateway（CUSTOM_JWT）+ target `doris`（IAM 出站），token 冒烟 | R-10, R-41 | P0 §T0.6 |
| [ ] | T0.7 | [USER] | Quick 桌面版：Cloud Connector（User auth，再试 Service auth）+ Local stdio 连接器，各调用一次 `net_check` | R-10, R-11, R-13 | P0 §T0.7 |
| [ ] | T0.8 | [AI] | 记录 P0 结论（回调 URL、scope 行为、冷启动耗时、CLI 差异），更新 design.md，编写 P1 前复核 | R-60 | P0 §T0.8 |

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

## P2 Doris 与语义层（计划：`plans/P2-doris.md`，P1 完成后编写）

| ✓ | ID | 标签 | 任务 | 需求 |
|---|---|---|---|---|
| [ ] | T2.1 | [AI+GATE] | `infra/40-doris-secret.sh`：Secrets Manager `doris-mcp/mcp_svc`（随机密码）| R-31, R-43 |
| [ ] | T2.2 | [AI+GATE] | `doris/01_mcp_user.sql`：root 建 `mcp_svc` 并授权（密码从 secret 读取后经 stdin 传入）| R-35, R-42 |
| [ ] | T2.3 | [AI] | 权限矩阵测试：ecom 可读、system_mcp 可 CREATE IF NOT EXISTS、写操作被拒 | R-21, R-42 |
| [ ] | T2.4 | [AI] | 编写 `doris/semantic/ecom/*.yaml`（orders / order_items / refunds / reviews）| R-26 |
| [ ] | T2.5 | [AI+GATE] | 本地起 upstream 原版 server（admin，Web UI）发布 ecom 模型到 `system_mcp`，发布后关闭 | R-26 |
| [ ] | T2.6 | [AI] | 用 `mcp_svc` 在本地跑 `list_metrics` / `query_metric`，与故事线 SQL 对账 | R-26 |

## P3 AgentCore 部署（计划：`plans/P3-deploy.md`）

| ✓ | ID | 标签 | 任务 | 需求 |
|---|---|---|---|---|
| [ ] | T3.1 | [AI+GATE] | Runtime 执行角色追加 `secretsmanager:GetSecretValue`（只限 `doris-mcp/mcp_svc`）| R-31, R-41 |
| [ ] | T3.2 | [AI+GATE] | `agentcore.json`：codeLocation 改为 `../mcp-server/`，envVars 加 `DORIS_SECRET_ID`、`PROFILE_SCOPE`，重新部署 | R-30 |
| [ ] | T3.3 | [AI] | SigV4 直连冒烟（12 个工具 + flow）；CloudWatch 能看到审计日志；冷启动 + 典型查询 < 60 s | R-12, R-32 |
| [ ] | T3.4 | [AI+GATE] | `synchronize-gateway-targets`；Gateway token 冒烟（`doris___*` 共 12 个）| R-10 |
| [ ] | T3.5 | [AI+GATE] | `mcp_svc` host 收紧为 `'172.31.%'`（D6），复测 | R-42 |

## P4 Quick 桌面版（计划：`plans/P4-quick.md`）

| ✓ | ID | 标签 | 任务 | 需求 |
|---|---|---|---|---|
| [ ] | T4.1 | [USER] | Cloud Connector Sync → 逐个启用 12 个工具，按 D7 设置权限 | R-10 |
| [ ] | T4.2 | [USER] | Local stdio 连接器切换到最终 Runtime（`quick/local-connector.json`）| R-11 |
| [ ] | T4.3 | [AI] | 编写「Doris 专家」agent 指令 `quick/agent-instructions.md`（≤ 5 万字符）| R-51 |
| [ ] | T4.4 | [USER] | 桌面版创建 Agent，跑「开场 + 第 2 幕」（两条路径各一次）| R-10, R-11 |

## P5 Skills 与彩排（计划：`plans/P5-skills.md`）

| ✓ | ID | 标签 | 任务 | 需求 |
|---|---|---|---|---|
| [ ] | T5.1 | [AI] | 锁定 apache/doris-skills commit；生成导入副本（加 adapter 提示行）到 `quick/skills/` | R-50 |
| [ ] | T5.2 | [AI] | 编写 `quick/skills/doris-mcp-adapter/SKILL.md`（翻译表、工具名前缀、profile 约定、60 s 限制）| R-50 |
| [ ] | T5.3 | [USER] | 桌面版导入 skills，验证 adapter 能被自动选中 | R-50 |
| [ ] | T5.4 | [USER] | 完整彩排 × 2（design §10），记录每步耗时和问题 | R-51 |
| [ ] | T5.5 | [AI] | 根据彩排结果修正（skill / 指令 / 超时），准备预热脚本和演示手册 `quick/runbook.md` | R-51 |
| [ ] | T5.6 | [AI+GATE] | （演示结束后）`infra/99-cleanup.sh` | — |
