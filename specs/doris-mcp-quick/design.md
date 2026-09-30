# Doris MCP on AgentCore × Amazon Quick 桌面版 —— 设计

> 版本：**v0.9** · 2026-09-30 · 状态：P5 演示准备完成（`plans/P5-skills.md` Task 1–8，分支 `p5-skills`；Task 9 在演示结束后清理）；P4 已按 `plans/P4-quick.md` 实施完成（T4.1、T4.3–T4.6，分支 `p4-quick`），整体评审（opus）已完成；P3 已按 `plans/P3-deploy.md` 实施完成（T3.0–T3.5），整体评审（opus）已完成（0 Critical / 0 Important），已本地合并到 `main`；P2 已按 `plans/P2-doris.md` 实施完成（T2.1–T2.7），整体评审（opus）已完成、I1 已修复并重新发布，已本地合并到 `main`；P1 已完成并合并到 `main`；P0 技术验证已完成（结论见 v0.3 变更记录与 §4.4、§4.5、§13）；备份路径按 D9 改为 Service auth
> 输入材料：`prepare/` 下 4 份文件 + upstream `velodb-mcp-server`（锁定 commit `f235832`）+ 旧仓库 `velodb-mcp-agentcore`（复用流程与脚本）
> 标注约定：✅ 已实测（本次对真实 Doris / AWS 账号只读验证）· 📄 官方文档确认 · ❓ 待 P0 验证

### 变更记录

| 版本 | 变更 |
|---|---|
| v0.1 | 初版（`docs/改造方案.md`），用户 review |
| v0.9 | P5 实施（Task 1–8，2026-09-30）：① skills 导入 Quick 桌面版（T5.3）：A5 用 `execute_query` 执行 `SHOW FULL PROCESSLIST`，再查 `information_schema.active_queries` 和 `check_service_health`，没有让用户运行命令，也没有 `KILL`；A4（M-1）T5.3 导入时用户没有报告要求登录，仍**未证实**（§13）。② 彩排（T5.4）：第 1 轮（英文，用户自行完成）7 步没有挡路的问题，第 2 轮按用户决定跳过；彩排发现的 3 处偏差（类目维度名、活动期、差评检索）写进指令后重问：第 4 步按新规则回答；第 3 步用对了类目维度，双 11 用了 `dim_promotion` 的活动期，618 仍按 6 月 1–18 日算（结论方向不变，手册「出问题时」写明了追问的话）；单次工具调用最长 9655 ms，≥ 45 s 的 0 次，没有 424（§13）。③ T5.5 的四项决策：Gateway 保留 DEBUG 到演示结束，description 已补上（GATE；之后重跑 `infra/30-gateway.sh` 要显式带 `GW_EXCEPTION_LEVEL`，默认值是 DEBUG）；2003 错误里的主机地址：不补丁，第 1 轮彩排没有出现 2003（4 个失败都是 SQL 错误或参数校验）；手册「出问题时」已写明；`query_timeout` 保持 50 s（§13、§14）。④ Runtime version 4（P-10、P-11、3 个传递依赖锁定、query_id 每段 1–16 位的校验修复，§5.2）|
| v0.8 | P5 计划（`plans/P5-skills.md`）：代码在 spec 阶段完成 TDD，并在 `bcda0f3` 的干净 worktree 上回放；只读核实了 Gateway、Runtime、CDK diff 和 Doris（`demo_ro`）。① skills：锁定 apache/doris-skills `0476f3b`，`scripts/build_skills.py` 从 git 对象生成 4 个副本（每个 SKILL.md 正文第一行是 adapter 提示；2 个超过 1024 字符的 description 换成缩写版；修 1 处断链），`doris-debug` 整个文件夹一次导入，adapter 先导入；adapter 的翻译表覆盖 doriscli 命令、会话变量、SQL 和 FE / BE HTTP 调用（§8.3、§9）。② P4 遗留：P-10 审计记下失败原因和 `query_metric` 的过滤条件；P-11 修 metric_time 过滤（OR、严格比较、交集、括号），旧 server 经 Gateway、新 server 在本机编译后以 `demo_ro` 执行，结果对比写进计划 Task 6（§5.2）；按分组粒度对齐时间范围确认是 MetricFlow 的设计，指令改为「同期同天数」按天分组；脚本 M-7–M-10。③ CodeZip 漂移：`botocore` 1.43.104、`rich-rst` 2.2.0、`sse-starlette` 3.5.0，锁到 `.venv` 的 1.43.103、2.1.0、3.4.11（§5.2 P-07、§13）。④ `scripts/demo-check.sh`（演示前后的只读检查）、`infra/99-cleanup.sh`（按依赖顺序删除，删除前先做全部检查，§7）、`infra/30-gateway.sh` 的 `GW_EXCEPTION_LEVEL` 和 description（§7、§14）。⑤ Runtime 偶发 502 / 冷启动慢：预检只有一项失败时重跑一次（§13）|
| v0.7 | P4 实测（2026-09-28）：① scope（P0 评审 M-1）：仍**未证实**（`doris-mcp` 的 Sync 没有要求登录；新建 `Doris-Desktop-MCP` 时出现了登录页，但没有读地址）（§4.5、§13）。② Quick 侧耗时（P0 评审 M-3）：每个问题的总耗时 「Doris 专家」网页版约 5 s / 15 s（用户记录）；桌面版（`Doris-Desktop-MCP`）问题 1 的工具调用约 12 s、问题 2 约 2–3 分钟（按工具调用时间估算，未计时）；单次工具调用最长 9863 ms，≥ 45 s 的 0 次；T5.5 不必为此调整 `query_timeout`（§4.4、§13）。③ `doris-mcp`、`doris-mcp-svc`（网页版 Sync）和 `Doris-Desktop-MCP`（在网页版新建、桌面版使用，User auth）各 12 个工具，权限按 D7（`doris-mcp`、`doris-mcp-svc` 的 `execute_query` 用平时的 Ask Each Time；`Doris-Desktop-MCP` 的 `execute_query` 原为 Always Allow（D7 的彩排 / 演示设置，所以第 2 幕的 SQL 没有弹窗），改为 Ask Each Time 后桌面版会弹出允许 / 拒绝）；「Doris 专家」（User auth，桌面版，`Doris-Desktop-MCP`）的「开场 + 第 2 幕」数字与参照值一致（第 2 幕主动把 9 月按相同天数比较）；「Doris 专家（svc）」只在网页版验证了工具调用（client B），答案没有对账。④ 桌面版上 T0.7 建的 `doris-mcp` 刷新不了工具列表（仍是 `doris___net_check`；调用时 Quick 自己返回 HTTP 400，请求没有到 Gateway），所以桌面版改用新建的连接器 |
| v0.6 | P4 计划（`plans/P4-quick.md`）：代码在 spec 阶段完成 TDD 草稿，并在 `96d18ce` 的干净 worktree 上回放；另外只读核实了 CloudTrail 和 Gateway 指标。① **更正 scope 结论（P0 评审 M-1）**：P0 写的「Quick 按 PRM 请求到了 `doris-mcp/invoke`」证据不足，改为**未证实**，T4.1 用浏览器 authorize URL 确认（§4.5、§13）。CloudTrail `Token_POST` 显示：Service auth 的 token 请求带 `scope=doris-mcp/invoke`，可能来自界面里填的 scope；User auth 的 token 请求不带 scope、带 `resource`；authorize 请求不进 CloudTrail；请求不带 scope 时 Cognito 授予 client 的全部 scope。② **Quick 侧耗时（P0 评审 M-3）**：Quick 从自己的后端调用 Cloud Connector，所以 Gateway 的 InvokeGateway Latency 就是 Quick 每次工具调用等待的时间。新增 `scripts/gw_latency.py`（T4.6）；T4.4 用秒表记总耗时，用它记每次工具调用（§4.4、§13）。③ **URL / IPv4 mask 收口（T4.5）**：`scripts/redact.py` 统一处理，并接管 MCP SDK 自己的日志行（T3.0、T3.3 与 T3.6 M1 / M2 的遗留）。④ §13 写入 T3.3 / T3.4 实测值；§7 的清理一行补上两个 IAM 角色；§8.1 写明 P4 的工具权限；§8.3 两个 agent 各只关联自己的连接器，P4 不挂 skills |
| v0.5 | P3 计划（`plans/P3-deploy.md`）在 spec 阶段完成 TDD 草稿和只读预验证：① 补丁 **P-09**：Gateway 的每次调用都是新 microVM，销毁时池连接不会被关闭，Doris 默认 `wait_timeout` 28800 s，而 `mcp_svc` 的 `max_user_connections` 是 100；每个池连接执行 `SET wait_timeout = 600`（§5.2、§13）。② Runtime 执行角色改为自建的 `doris-mcp-runtime-role`（`infra/35-runtime-role.sh`，经 `agentcore.json` 的 `executionRoleArn` 导入），只能写自己的日志组、只能读 `doris-mcp/mcp_svc`；`deploy --diff` 确认删除 CDK 角色和 DefaultPolicy、Runtime 原地更新（§7、§14）。③ CodeZip 的传递依赖漂移（`caio`、`platformdirs`），T3.2 锁定并对比 88 个 dist（§5.2、§13）。④ `mcp_svc` 迁到 `'172.31.%'`：先 CREATE 新身份并授权，最后 `DROP USER IF EXISTS 'mcp_svc'@'%'`；之后开发机以 `mcp_svc` 登录会得到 1045（§6.1）。⑤ §13 增加连接泄漏、共享 session 下的并发、语义层加载耗时、日志和返回里的 IP、2003 错误带 host 等风险；§14 Gateway DEBUG 的结论为保留到 T5.5，T3.4 做泄漏检查，另加 FE 审计日志一项 |
| v0.4.1 | P2 整体评审（opus）I1：upstream query_metric 把指标列的 NULL 改写成 0，2025 年期间的同比会被报成 0；gmv_last_year / gmv_yoy 的 description 加上「无数据而不是持平」的说明，并记进 §6.3 的坑；需要重新发布 ecom（GATE）|
| v0.4 | P2 代码在 spec 阶段完成 TDD 草稿（117 个 Python 测试 + 4 组 shell 测试），并用 `demo_ro` 对真实 Doris 只读跑通 11 个故事线对账用例（到分一致）：① 语义层发布改为**方案 C**：root 在本机进程内调用 upstream `DorisStore`，不起 Web UI（upstream 写接口要求 Doris 角色 `admin`），不调用 upstream `commit_staging`（它会 `GRANT … TO '%'`）（§4.2、§6.3）。② 首次发布由 root 创建 `system_mcp` 库、3 张表和 `ecom` 元数据行，`mcp_svc` 因此不需要 LOAD_PRIV；执行顺序改为 T2.1 → T2.4 → T2.5 → T2.2 → T2.3 → T2.6。③ `01_mcp_user.sql` 改为 `CREATE USER IF NOT EXISTS` + `ALTER USER`，密码占位符在内存里填入（§6.1）。④ §6.3 模型表按实际的 10 个文件、22 个指标重写，并记录编译器的坑。⑤ `reload_semantic_layer` 不需要调用：`ensure_fresh` 在 semantic_version 变化时自动重载。⑥ R-42 验收接受 Doris 给每个用户默认列出的 `information_schema` / `mysql` SELECT 和 workload group `normal` 的 USAGE（requirements v1.3）|
| v0.3.1 | 用户决定 D9：User auth、Service auth 在 P0 都已跑通，**不做 Local stdio**（R-11 取消），备份路径改为 Cloud Connector + Service auth。§1、§2、§3、§4.4、§8.2、§8.3、§11、§13 同步；v0.3 行里「Local stdio 顺延到 T4.2」作废 |
| v0.3 | P0 实测结论（`progress.md` T0.2–T0.7 日志）：① OAuth 回调 URL 就是默认值 `https://us-east-1.quicksight.aws.amazon.com/sn/oauthcallback` ✅；Quick 桌面版 User auth、Service auth 都已跑通，Local stdio 顺延到 T4.2（§4.4）。② Gateway 的 401 / PRM 实际内容；Quick 按 PRM 请求到了 `doris-mcp/invoke`（v0.6 更正：证据不足，改为未证实，T4.1 确认）；工具列表只有 target 工具（§4.5）。③ **经 Gateway 时每次 `tools/call` 都新开一个 Runtime 会话（冷启动约 4.5–5.5 s），预热无效**；直连时复用 `Mcp-Session-Id` 的热调用约 0.3 s（§4.5、§13）。④ agentcore CLI 0.30.0 的实际行为，包括 deploy 会顺带修改账号级 X-Ray Transaction Search 设置（§7、§13）。⑤ 待 P3 复查：CDK 默认执行角色带通配权限、Gateway `--exception-level DEBUG`（§14）|
| v0.2.2 | P1 代码在 spec 阶段完成 TDD 草稿，并用 `demo_ro` 连真实 Doris 跑通 E2E（结论写进 `plans/P1-mcp-server.md`）：① `/api/profile/text` 找不到 id 时返回**纯文本** `query id <id> not found`，因此「非 JSON 就是命中」的判断改为「第一行必须是段落标题」（§4.1、§5.3）。② summary 额外删除全 0 计数器，并折叠 PhysicalPlan 的逐列统计：真实 profile 103 487 → **9 109** 字符（旧规则 20 487）（§4.1、§5.3、R-23）。③ Doris 会保留 `/* trace:… */` 注释，§5.3 的 ❓ 关闭。④ 入口**不挂** `RequestLoggerMiddleware`（它会把请求 header 和 body 里的 SQL 写进 CloudWatch）（§4.6、§5.2、§13）。⑤ P-07：vendoring 时要带上 upstream 根目录的 `requirements.txt`（upstream `test_deps.py` 需要它）；AgentCore CLI 0.30 先试 `aarch64-manylinux2014`，`rapidfuzz` 没有该平台 wheel，CLI 会自动回退到 `manylinux_2_28`，安装后约 107 MB |
| v0.2.1 | spec 阶段追加核实：Gateway 从一开始就设 `allowedScopes=[doris-mcp/invoke]`（会写进 PRM 和 WWW-Authenticate，解决 Quick scope 风险）；`supportedVersions` 用默认值；`Mcp-Session-Id` 放行改为 P0 之后的可选实验；CDK 已在 us-east-1 bootstrap；VPC 内只有 Doris 一台 EC2；AWS CLI `file://` 不能读 `/dev/fd`、stdin，secret 输入改用 0600 临时文件；Quick 用的 client secret 由用户在**自己的终端**获取（不用 `!` 前缀，否则会进入对话记录）|
| v0.2 | ① 决策 D1–D8 已定，D2 = Enterprise。② 读完 upstream 源码后精简补丁：删除原 P-07（关闭 Web UI）和 P-08（SEED_EXAMPLE），因为 Runtime 只转发 `/mcp`，示例数据只能从 Web UI 路由触发；原 P-06 改为「store 服务账号兜底 + `create_server(service_credentials=…)`」；profile 工具改从入口注册，不改动 upstream 的 `server.py` 工具区。③ upstream 锁定 commit `f235832`（tag `velodb-mcp-server-0.3.0`，pyproject 版本号仍是 0.2.6）。④ Gateway 用 AWS CLI 创建（已确认 CLI 支持 IAM 出站 + metadata 头），不依赖 agentcore CLI。⑤ Gateway 暴露的工具名带 target 前缀 `doris___`。⑥ 基础设施脚本重新编号，默认 dry-run。⑦ 移到 `specs/doris-mcp-quick/design.md` |

---

## 0. 一页结论

1. **代码基线**：upstream `velodb-mcp-server` @ `f235832` 原样 vendoring 到 `mcp-server/`，叠加 **8 处补丁**（§5.2），其中 4 处是新文件。旧 `doris-mcp-agentcore` 的代码不再沿用，只复用它的**部署流程、agentcore.json 结构、VPC endpoint 排障经验和脚本**。
2. **托管**：`@aws/agentcore` CLI v0.30，**CodeZip + Python 3.12 + VPC 模式**，Runtime 鉴权 **AWS_IAM**，Doris 走私网 `172.31.25.143:9030/8030`。
3. **鉴权**：**单 Cognito 池（Quick → Gateway）+ Gateway → Runtime 用 IAM SigV4**。
4. **Quick 桌面版集成**：
   - **主路径**：Cloud Connector（MCP + OAuth User auth）→ AgentCore Gateway。Enterprise 订阅满足前提（D2）。
   - **备份路径**：Cloud Connector + **Service auth**（client credentials，client B）→ 同一个 Gateway（D9）。原计划的 Local stdio 连接器 → `mcp-proxy-for-aws` → 直连 Runtime 已取消。
5. **Skills**：桌面版原生支持 `SKILL.md`。apache/doris-skills 用「From folder」导入，另加自写的 **`doris-mcp-adapter`** skill，把 skill 里的 `doriscli` 调用翻译成 MCP 工具调用。
6. **Profile 工具重写**：对 Doris 4.1.4 实测，`prepare/profile.py` 有 6 处与真实 API 行为不符（§4.1），按 §5.3 重写。
7. **推进方式**：spec 驱动，状态全部在仓库里（`CLAUDE.md` 中有恢复协议）；所有 AWS / Doris / SG 变更都要经过 GATE 确认。

---

## 1. 目标与范围

**目标**：在 Amazon Quick **桌面版**里，用一个「Doris 专家」对话入口，基于**真实 Doris 集群（电商演示库 `ecom`）**完成：
- 语义层问答（GMV、订单数、客单价……按渠道/月份/区域）；
- 业务排查（第 5 幕：退款率异常 → 差评分词 → 物流瓶颈）；
- **Track A 诊断**：慢查询 → 自动抓 profile → `doris-profile-reader` / `doris-debug` 解读（依赖 profile 工具）；
- **Track B 设计评审**：读真实 DDL、分区、倾斜 → `doris-best-practices` / `doris-architecture-advisor` 给出推荐 DDL → **人工执行**。

**不在范围**：MCP 写路径（DDL/DML 仍由人执行）、多用户 Doris 身份透传、生产级高可用、VeloDB Cloud。

---

## 2. 相对 `prepare/Doris MCP on AgentCore 方案报告.md` 的变更

| 原方案 | 本方案 | 原因 |
|---|---|---|
| Quick **Web** Connectors | **Quick 桌面版**：Cloud Connector 主路径（User auth）+ Service auth 备份（Local stdio 已按 D9 取消）| 新的硬性要求；桌面版已于 2026-09-09 GA（us-east-1 可用）📄 |
| 双 Cognito 池（Inbound #1 / Outbound #2） | **单池 + Gateway → Runtime IAM SigV4** | 📄 Gateway MCP target 文档写明 IAM 出站支持 AgentCore Runtime |
| legacy `agentcore configure / launch` | 新 `@aws/agentcore` CLI（`agentcore.json`，由 CDK 托管） | starter toolkit 已弃用；旧仓库已用新 CLI 跑通 |
| 自定义 Dockerfile | **CodeZip**（托管 Python 3.12） | 不需要 ECR，省 2 个 VPC endpoint；旧仓库验证过 |
| 路线 1：把 skill 逻辑注入 agent 指令 | **桌面版原生导入 SKILL.md** + 自写 adapter skill | 桌面版的 Skill 就是「文件夹 + `SKILL.md`」📄 |
| `profile.py` 原样合入 | 按实测**重写 6 处** | §4.1 |
| profile 工具「沿用调用方 Doris 身份」 | **Doris 服务账号 `mcp_svc`**（D1） | AgentCore 已在前面做了鉴权，请求里不再带 Doris user:password |
| 演示用 upstream 自带的 `dw.*` 示例 | **`ecom` workspace 语义模型** | 对齐「中秋节的一天」故事线；示例数据只能从 Web UI 触发，Runtime 上不会被创建（§4.6）|
| 网络 / Region 待定 | us-east-1 default VPC 私网直连，SG 引用放通 | ✅ Doris 与 Runtime 在同一个 VPC |

---

## 3. 目标架构

```
┌──────────────────────── Amazon Quick 桌面版 (macOS / Windows) ────────────────────────┐
│  自定义 Agent「Doris 专家」 / Chat                                                      │
│  Skills : doris-mcp-adapter(自写) + doris-debug / doris-profile-reader /               │
│           doris-best-practices / doris-architecture-advisor   (SKILL.md 原生导入)       │
│  Connectors : ① Cloud Connector (MCP, OAuth)        ② Local stdio (已取消, D9)          │
└───────────────┬──────────────────────────────────────────────┬─────────────────────────┘
                │ ① HTTPS + Cognito JWT (Quick 自动续期)        │ ② stdio → mcp-proxy-for-aws
                ▼   工具名：doris___<tool>                      │    (本机 AWS 凭证 SigV4) 工具名：<tool>
   ┌──────────────────────────────────┐                        │
   │ AgentCore Gateway  doris-mcp-gw   │                        │
   │  inbound : CUSTOM_JWT (Cognito)   │                        │
   │  outbound: IAM SigV4 (服务角色)    │                        │
   │  target  : doris (MCP server)     │                        │
   └────────────────┬─────────────────┘                        │
                    ▼  InvokeAgentRuntime (SigV4)                ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ AgentCore Runtime  dorismcp   authorizer=AWS_IAM  protocol=MCP            │
   │  velodb-mcp-server @f235832 + AgentCore 补丁 + profile 工具  (12 tools)    │
   │  0.0.0.0:8000/mcp  stateless  · CodeZip / Python 3.12                     │
   │  VPC 模式: vpc-0b806cad7faf55718, 子网 use1-az4 / az1 / az2, SG doris-mcp-rt│
   └──────────┬─────────────────────────────────┬─────────────────────────────┘
              │ MySQL 9030 (SQL)                 │ HTTP 8030 (FE profile API)
              ▼                                  ▼
   ┌───────────────────────────────────────────────────────────┐
   │ Doris 4.1.4  i-0d5ea8c0157912a05  172.31.25.143 (use1-az4)  │
   │ SG doris-demo-sg: 新增「来源 = doris-mcp-rt SG」→ 9030/8030 │
   └───────────────────────────────────────────────────────────┘
   VPC Endpoints: S3 (Gateway, 免费) · logs (Interface) · secretsmanager (Interface)
   Secrets Manager: doris-mcp/mcp_svc   ·   CloudWatch Logs: Runtime stdout/stderr + 审计
```

**为什么 Runtime 用 AWS_IAM 而不是 JWT**：两条入口都能用 SigV4 到达 Runtime（Gateway 用服务角色，开发机冒烟用本机凭证），所以 Cognito 只需要出现在「Quick → Gateway」这一段。

**Runtime ARN 保持不变**：P0 把最小 spike 部署为 runtime `dorismcp`，P3 只把 `codeLocation` 换成 `../mcp-server/` 后重新部署。这样 P0 建好的 Gateway target 和 IAM 策略可以直接沿用。

---

## 4. 已核实事实

### 4.1 Doris 4.1.4 profile API 实测（只读账号 `demo_ro` 和 root）✅

| 验证项 | 实测结果 | 对 `profile.py` 的影响 |
|---|---|---|
| 错误状态码 | 密码错误返回 **HTTP 200**，body `{"msg":"Unauthorized","code":401,"data":"Access denied …"}`；找不到 profile 返回 **HTTP 200** + `{"code":0,"data":{}}` | 按 HTTP status 判断 401/404 的分支**永远不会触发**，必须判断 body 的 `code` / `data` |
| `/rest/v2/manager/query/query_info` | **非 admin 永远返回空 rows**（连自己的查询也看不到）；root 能看到全部 | `list_recent_queries` 用服务账号时**必然为空** → 改用 `/rest/v1/query_profile` |
| `/rest/v1/query_profile` | 非 admin 能列出**所有用户**已采集的 profile（含 SQL 文本）。结构：`{"msg","code":0,"data":{"href_column","column_names":[10 列],"rows":[{"Profile ID","Task Type","Start Time","End Time","Total","Task State","User","Default Catalog","Default Db","Sql Statement","__hrefPaths"}]},"count"}` | 可用；需要可见范围控制（D4）|
| `/rest/v2/manager/query/profile/text/<qid>` | 只能取**自己的** profile，别人的返回 `data:{}`；文本在 `data.profile` | 字段是 `data.profile`，不是 `data` |
| `/api/profile/text?query_id=<qid>` | 成功时返回**纯文本**，**不区分用户**；格式非法的 id 返回 JSON `code:500 "Invalid profile id"`；格式合法但不存在的 id 返回 HTTP 200 **纯文本** `query id <qid> not found` | 作为跨用户回退；只有第一行是段落标题（如 `Summary:`）的纯文本才算命中 |
| 列名字段 | v2 返回 `columnNames`（驼峰） | `profile.py` 读的是 `column_names`，会拿到 None |
| profile 体积 | 简单查询 **114 KB**，按天 COUNT(DISTINCT) **190 KB** | 直接返回会撑爆上下文 → 需要 summary 模式 + 截断 |
| profile 结构 | 顶层段落都在第 0 列：`Summary:`、`Execution Summary:`、`ChangedSessionVariables:`、`MergedProfile:`、`DetailProfile(<qid>):`（约 94 KB，按 instance 展开）、`Appendix:`（含 `PhysicalPlan:`）；子段落有缩进；`PhysicalPlan:` 下每个扫描表的每一列都有一行统计 `<col>#<id> -> ndv=…` | summary = 去掉 DetailProfile 段 + 去掉 `N/A` 和全 0 的计数器 + 折叠逐列统计，`COUNT(*) ecom.fact_order` 实测 103 487 → **9 109** 字符（只去 DetailProfile 和 N/A 时是 20 487）|
| profile 开关 | 全局 `enable_profile=false`，`auto_profile_threshold_ms=-1` | 默认情况下，MCP 发起的查询**没有 profile** |
| 通过 MCP 开 profile | MCP 的 SQL 校验器**拒绝 `SET`**，但**放行** `SELECT /*+SET_VAR(enable_profile=true)*/ ...`；实测该 hint 能生成 profile，且 SQL 原文（含 hint）会出现在 `Sql Statement` 中 | **不改 Doris 全局配置**也能「带 profile 执行」|
| 错误码 | upstream `ErrorCode` 里**没有** `AUTH_FAILED` / `INVALID_ARGUMENT` | 改为 `UNAUTHENTICATED` / `INVALID_PARAMS`，否则 import 时就会 AttributeError |
| 依赖 | upstream 已依赖 `httpx`，没有 `aiohttp` | 改用 httpx，不新增依赖 |

### 4.2 Doris 权限与语义层 ✅
- `demo_ro` 只有 `SELECT` on `ecom` / `information_schema` / `mysql`。
- upstream 把语义模型存在 Doris 的 `system_mcp` 库里。`DorisStore.discover_workspaces()` 和 `_ensure_tables()` 会执行 `CREATE DATABASE IF NOT EXISTS system_mcp`、`CREATE TABLE IF NOT EXISTS workspace_metadata …`。**实测：即使库已存在，Doris 也会先检查 CREATE 权限**（`demo_ro` 执行 `CREATE DATABASE IF NOT EXISTS ecom` 报 Access denied）→ `mcp_svc` 需要 `CREATE_PRIV ON internal.system_mcp.*`（§6.1）。
- upstream 的发布路径（Web UI / `commit_staging`）会执行 `GRANT SELECT_PRIV ... TO '%'`，写接口还要求 Doris 角色 `admin` → **模型发布走方案 C**：root 在本机进程内调用 `DorisStore` 的 staging / commit，不执行任何 GRANT，不在 Runtime 上做（§6.3）。

### 4.3 AWS 网络 ✅ / 📄
- 账号 `890717383483`，default VPC `vpc-0b806cad7faf55718`（172.31.0.0/16，DNS support/hostnames 均已开启）：**没有 NAT，也没有任何 VPC endpoint**。
- 只有一张主路由表 `rtb-0372c2401cd48e394`，没有显式关联的子网 → 所有子网都用它；S3 Gateway endpoint 挂在这张表上。S3 prefix list：`pl-63a5400a`。
- 📄 AgentCore VPC 模式在 us-east-1 支持的 AZ：**use1-az1 / use1-az2 / use1-az4**。

  | 子网 | AZ | AZ ID | 用途 |
  |---|---|---|---|
  | `subnet-0a06e314475c5d116` | us-east-1a | use1-az4 | Doris 所在；Runtime ENI + Interface endpoint |
  | `subnet-065f33a1a5f2ac3ff` | us-east-1c | use1-az1 | Runtime ENI + Interface endpoint |
  | `subnet-01c473181df2246e4` | us-east-1d | use1-az2 | Runtime ENI |

- 📄 ENI 只有私网 IP，放在「公有子网」里也**不能**访问公网 → 必须建 VPC endpoint：S3 Gateway（CodeZip 拉包）+ `logs`，另外还需要 `secretsmanager`。旧仓库的教训：缺少 endpoint 时，冷启动约 30 s 后超时，而且 CloudWatch 里一条日志也没有。
- Interface endpoint 开启 private DNS 后，会影响整个 VPC 对这两个服务的解析。✅ VPC 内只有 Doris 这一台 EC2（没有其他实例或 VPC Lambda），且它**没有 instance profile**，不调用 AWS API，因此不受影响。
- ✅ CDK 已在 us-east-1 bootstrap（`CDKToolkit` UPDATE_COMPLETE，version 30），`agentcore deploy` 不需要额外的 bootstrap 步骤。
- Doris 的私网 IP 在 EC2 stop/start 后不变（公网 IP 会变，本地联调前需要从 `credentials.env` 或控制台重新获取）。

### 4.4 Quick 桌面版 📄
- 2026-04-28 预览，**2026-09-09 GA**（macOS 12+ Apple Silicon / Windows 10 x64，含 us-east-1）。
- 连接器有两类：
  - **Cloud Connector**：与 Web 版 Connectors → MCP 是同一个对象，桌面、Web、移动端通用。只支持远程 MCP，优先 streamable HTTP。鉴权三选一：User auth（OAuth 授权码 + PKCE S256 + RFC 8707）、Service auth（client credentials）、无鉴权。按 RFC 9728 做发现；Cognito 不支持 DCR，需要手填 Client ID/Secret。前提是 **Enterprise 订阅** —— **D2 已确认满足** ✅。
  - **Local connector**（仅桌面版，配置在 `~/.quickwork/`）：Local = stdio 命令；Remote = URL + 静态 Header；Import = 从 Kiro / Claude Code 等的配置文件导入。未见 OAuth 支持。
- 限制：MCP 单次操作**固定 60 s 超时**（超时报 HTTP 424）；单个连接最多 100 个工具；工具 inputSchema 需要符合 JSON Schema Draft 7+；自定义连接器改了工具后要手动 **Sync**（会触发重新授权），**新同步的工具默认禁用**；桌面版单次最多 20 个工具并发；agent 指令最长 5 万字符。
- **Skills（桌面版）**：文件夹 + `SKILL.md`（可附参考文件和脚本），支持从文件夹、`.md`、`.zip` 导入，单个 ≤ 6 MB；按 description 发现，激活时才读全文，工具从已连接的 connector 中解析。
- ✅ OAuth 回调 URL：`https://us-east-1.quicksight.aws.amazon.com/sn/oauthcallback`（与博客一致）。T0.7 时 client A 只注册了这一个回调，而 Cognito 会拒绝不匹配的 `redirect_uri`（`redirect_mismatch`）；User auth 登录授权成功，说明 Quick 用的就是这个值。
- ✅ P0 实测（T0.7，2026-09-26，Quick 桌面版 + spike 工具 `net_check`）：
  - **Cloud Connector + User auth**：成功（client A，`demo` 用户登录）。
  - **Cloud Connector + Service auth**：成功（client B）。
  - **Local stdio**：P0 未在 Quick 中尝试；之后用户决定整个项目不做（D9），备份路径改为 Service auth。`mcp-proxy-for-aws` → Runtime 的 SigV4 链路已在 T0.4 从开发机验证通过，仅用于开发机冒烟。
  - Quick 发起的每次调用在 Runtime 日志里都是一个新会话（新 microVM）：`initialize` 200 → `notifications/initialized` 202 → `tools/call` 200。✅ Quick 侧耗时（T4.4 / T4.6 实测，2026-09-28，P0 评审 M-3 关闭）：每个问题的总耗时 「Doris 专家」网页版约 5 s / 15 s（用户记录）；桌面版（`Doris-Desktop-MCP`）问题 1 的工具调用约 12 s、问题 2 约 2–3 分钟（按工具调用时间估算，未计时）；单次工具调用最长 9863 ms，≥ 45 s 的 0 次（用户记录 / 按工具调用时间估算 + `scripts/gw_latency.py`）。Quick 从自己的后端调用 Cloud Connector（CloudTrail 里的 UA 是 `Google-HTTP-Java-Client`），所以 Gateway 的 InvokeGateway Latency 就是 Quick 每次工具调用等待的时间。

### 4.5 AgentCore Gateway 📄 / ✅
- MCP server target 的出站鉴权支持：无 / OAuth（2LO、3LO、token exchange）/ **IAM SigV4**（`GATEWAY_IAM_ROLE` + `iamCredentialProvider{service: bedrock-agentcore, region}`）/ API key。
- 支持的 MCP 协议版本：2026-07-28、2025-11-25、2025-06-18、2025-03-26。
- ✅ AWS CLI 2.36.36 的 `bedrock-agentcore-control` 支持 `create-gateway`（`--protocol-configuration mcp{supportedVersions,searchType,sessionConfiguration}`、`customJWTAuthorizer{discoveryUrl,allowedClients,allowedScopes}`）、`create-gateway-target`（`mcpServer.endpoint`、`--credential-provider-configurations`、`--metadata-configuration allowedRequestHeaders/…`）、`synchronize-gateway-targets`。**因此 Gateway 用 AWS CLI 脚本创建**（`infra/30-gateway.sh`）。
- ✅ `customJWTAuthorizer.allowedScopes` 会出现在 Gateway 的 OAuth Protected Resource Metadata（RFC 9728）和 401 的 `WWW-Authenticate` 头里 → 客户端按 PRM 发现时可以据此请求 scope（Quick 有没有这样做仍**未证实**：`doris-mcp` 的 Sync 没有要求登录；新建 `Doris-Desktop-MCP` 时出现了登录页，但没有读地址，T5.3 再看；见下面 P0 实测的 scope 一条）。脚本默认设 `allowedScopes=[doris-mcp/invoke]`；需要回退时用 `GW_ALLOWED_SCOPES= APPLY=1 bash infra/30-gateway.sh` 去掉。
- `supportedVersions` 不设（用服务默认值，与账号里已有的 `pragent-github-gw` 一致）；不用 `searchType=SEMANTIC`（会多出一个搜索工具）。P0 用 `--exception-level DEBUG` 便于排错，**待 P3 复查**是否去掉（§14）。
- ✅ P0 实测（T0.6 / T0.7，Gateway `doris-mcp-gw`）：
  - 不带 token：`HTTP/2 401`，`www-authenticate: Bearer error="invalid_token", scope="doris-mcp/invoke", resource_metadata="https://<gw>.gateway.bedrock-agentcore.us-east-1.amazonaws.com/.well-known/oauth-protected-resource"`。PRM 在 Gateway 的**根路径**，不是 `…/oauth-protected-resource/mcp`。
  - PRM：`{"authorization_servers": ["https://cognito-idp.us-east-1.amazonaws.com/<pool-id>"], "resource": "https://<gw>…/mcp", "scopes_supported": ["doris-mcp/invoke"]}`。
  - scope：Gateway 设了 `allowedScopes`，Quick 的 User auth、Service auth 仍然都成功，不需要用 `GW_ALLOWED_SCOPES=` 回退。无效 token → 401。
    - **这不能证明 Quick 按 PRM 请求了 scope**（P0 评审 M-1，v0.6 更正）：请求不带 scope 时，Cognito 授予 client 允许的全部 scope（A 是 `openid doris-mcp/invoke`，B 是 `doris-mcp/invoke`），token 里照样有 `doris-mcp/invoke`。
    - CloudTrail `Token_POST`（2026-09-26，只看 client A / B、UA 为 `Google-HTTP-Java-Client` 的事件）：
      - Service auth：token 请求带 `scope=doris-mcp/invoke`。T0.7 指南让用户在界面里填了这个 scope，所以它不一定来自 PRM。
      - User auth：token 请求（authorization_code）不带 scope，这是正常的，scope 在 authorize 请求里；它带 `resource`（RFC 8707）。
      - authorize 请求不进 CloudTrail。
    - 结论（T4.1 实测，2026-09-28）：仍**未证实**（`doris-mcp` 的 Sync 没有要求登录；新建 `Doris-Desktop-MCP` 时出现了登录页，但没有读地址）。T5.3 导入 skills 时如果再次要求登录，按 `quick/P4-guide.md` A2 的方法再看一次。结果是什么都不影响功能。
  - 工具列表**只有 target 工具**（`doris___net_check`），没有 Gateway 内置工具，T3.4 / T4.1 的 12 个工具的期望不变。
  - `tools/list` 由 Gateway 用已同步的目录回答，不调用 Runtime（约 1.6 s，含 initialize）。`create-gateway-target` 时 Gateway 会调用 Runtime 同步工具（P0 观察到 2 个会话）。
  - **会话**：Gateway 不向客户端返回 `Mcp-Session-Id`；**每次 `tools/call` 都会新开一个 Runtime 会话**（新 microVM，冷启动），同一个客户端会话里连续 3 次调用也是 3 个新会话，每次约 4.5–5.5 s（spike，开发机在 ap-northeast-2）。
- ⚠ 账号里已有的 Gateway `pragent-github-gw` 属于其他项目，**不要修改或删除**。
- 经 Gateway 暴露的工具名是 `<target>___<tool>`。target 名定为 `doris`，所以桌面版里看到的是 `doris___execute_query` 等（adapter skill 要能兼容两种写法）。
- DEFAULT listing 模式下，工具变更后要调用 `synchronize-gateway-targets`。
- 可选（P0 之后再试）：target 的 `metadataConfiguration` 放行 `Mcp-Session-Id`。Runtime 是 stateless HTTP，不放行也能工作，P0 不设。P0 已确认 Gateway 不向客户端返回 `Mcp-Session-Id`，所以只放行请求头不够，至少还要放行响应头，客户端才拿得到可复用的会话 ID。是否值得做，要等 P3 用完整 server 测出冷启动开销后再决定（§13），做的话需要走 GATE。

### 4.6 upstream 源码要点（@f235832）✅
- 语义 workspace 是**懒加载**的：只有调用语义工具（`ensure_fresh`）时才会查 `system_mcp`；`check_service_health` 不会触发加载。
- 示例数据（`seed_all`，会创建 `dw.*`）**只能**由 Web UI 路由 `/mcp/web/example/deployment` 触发。Runtime 只转发 `/mcp`，这些路由不可达 → **不需要**「关闭 Web UI」或 `SEED_EXAMPLE` 补丁。
- `check_tool_access()` 总是放行；用户隔离完全靠 `_get_per_user_pool()`（从 Bearer `user:password` 取 Doris 凭证）。
- store 层（`pymysql`，同步）通过 contextvar `_request_creds` 取凭证，这个值只由 `CredentialVerifier` / Web 登录设置；`bootstrap.pre_validate_physical` 也读它。没有凭证时直接抛 RuntimeError（upstream 单测 `test_credential_pass.py` 锁定了这一行为）。
- 审计 logger `doris_new_mcp.audit` 只写文件（`propagate=False`）；服务日志写到 `<workspace>/logs/server.log`。`RequestLoggerMiddleware` 自带 stderr handler，header 已脱敏，但会记录请求 body（SQL）→ 入口**不挂**它；工具调用已经写进审计日志，入口再把审计 logger 接到 stderr（CloudWatch）。
- `workspace_dir = dirname(config_dir)/workspace`，在 `/var/task` 下只读。
- `main.py` 挂了 `SessionAffinityProxyMiddleware`（按机器 IP 在多个节点间转发 Web 会话），在 Runtime microVM 上没有意义 → 入口不挂它。
- FastMCP 3.4.4 已验证：`mcp.custom_route`、`mcp.tool(fn, name=, description=, annotations=)`、`Literal` 参数生成 enum schema、内存 `Client(mcp)`、`http_app(path="/mcp", stateless_http=True)` 能配合 Starlette TestClient 使用；`http_host_origin_protection` 默认关闭（不会拦截 AgentCore 的 Host 头）。
- 基线：用 uv.lock 锁定的版本安装后，`test/run_all_tests.sh --offline` **全部通过** ✅。

---

## 5. 代码改造

### 5.1 仓库布局

```
Doris-mcp-skill-Demo/
├── CLAUDE.md                        # 恢复协议 + 硬性规则（每次会话自动加载）
├── prepare/                         # 原始材料（只读，不改）
├── specs/doris-mcp-quick/           # requirements / design / tasks / progress / plans
├── mcp-server/                      # = AgentCore codeLocation（P3 起）
│   ├── UPSTREAM.md                  # upstream 地址 + 锁定 commit + 补丁清单
│   ├── mcp_server.py                # AgentCore 入口（P-01）
│   ├── pyproject.toml               # CodeZip 必需；锁定版本 + boto3（P-07）
│   ├── config/mcp-server.toml       # AgentCore 版配置（P-06）
│   ├── src/                         # vendored upstream src/ + 补丁
│   │   ├── agentcore_ext/           # 新增：settings.py（env/secret）、app.py（组装 server）
│   │   └── tools/profile.py         # 新增：profile 工具（P-05）
│   └── test/                        # upstream 测试 + test_agentcore_*.py（P-08）
├── spike/p0-mcp/                    # P0 最小 MCP（net_check），P0 结束后保留作排障工具
├── dorismcp/                        # agentcore CLI 项目（agentcore/agentcore.json, aws-targets.json, cdk/）
├── infra/                           # lib.sh + 幂等脚本（默认 dry-run）+ state.env + policies/
├── doris/                           # P2：01_mcp_user.sql（只有占位符）、semantic/ecom/*.yaml、publish/admin wrapper、reconcile.py、permission_matrix.py、test/
├── quick/                           # 桌面版：agent 指令、local-connector.json、skills/doris-mcp-adapter/（P4/P5）
├── scripts/                         # mcp_smoke.py、get-gw-token.sh、render-agentcore.py、check-secrets.sh
├── .venv/                           # 本地 venv（放在 codeLocation 之外，避免被打进 CodeZip / 符号链接 ELOOP）
├── .env.example                     # 只有变量名，没有值
└── .gitignore
```
> 凭证只放在 `/home/ubuntu/AI-code/Doris-test/credentials.env`（项目外，chmod 600）。该文件提供 `DORIS_HOST`（公网 IP）、`DORIS_MYSQL_PORT`、`DORIS_HTTP_PORT`、`DORIS_ROOT_USER/PASSWORD`、`DORIS_RO_USER/PASSWORD`。脚本运行时 `source`，不写进本仓库。

### 5.2 补丁清单（相对 upstream @f235832）

| # | 文件 | 改动 | 说明 |
|---|---|---|---|
| P-01 | `mcp_server.py`（新）+ `src/agentcore_ext/{settings,app}.py`（新） | `load_settings()`：从 env 读取配置，`DORIS_SECRET_ID` 优先（boto3 取 secret），否则读 `DORIS_PASSWORD`。`build_server()`：用 env 覆盖 `AppConfig.cluster` 的 host/端口 → `create_server(service_credentials=…, workspace_dir=…)` → `register_profile_tools()` → `GET /ping`。`configure_logging()`：root 和审计 logger 都写 stderr。`run()`：`streamable-http`，`0.0.0.0:8000/mcp`，`stateless_http=True`，中间件只挂 `[CharsetMiddleware]`（SSE 响应补 `charset=utf-8`；**不挂** RequestLogger 和 SessionAffinityProxy，见 §4.6）。配置错误时 `exit 2`，日志只写原因，不含 secret | 类型转换（int 端口）在 settings 里完成，不需要改 upstream 的 TOML 插值 |
| P-02 | `src/config/loader.py` | `ClusterConfig.fe_http_port = int(server.get("fe_http_port", 8030))` | profile 工具要用 |
| P-03 | `src/store/store.py` + `src/store/bootstrap.py` | 新增进程级 `_service_creds`、`set_service_credentials()` / `clear_service_credentials()` / `get_effective_credentials()`（请求凭证优先，其次服务凭证）；`_get_conn()` 和 `pre_validate_physical()` 改为调用 `get_effective_credentials()` | 没设服务凭证时行为与 upstream 完全一致（upstream 单测不变）|
| P-04 | `src/server.py` | `create_server(..., service_credentials=None, workspace_dir=None)`：设置了服务凭证时，`auth=None`，`_get_per_user_pool()` 返回服务账号连接池，并调用 `set_service_credentials`；workspace 目录优先用参数，其次 `DORIS_MCP_WORKSPACE_DIR`，最后才是原默认值 | 入站鉴权交给 Runtime IAM / Gateway JWT（D1）|
| P-05 | `src/tools/profile.py`（新） | 2 个 profile 工具 + `summarize_profile` + `register_profile_tools(mcp, target, scope)`（§5.3） | 替换 `prepare/profile.py` |
| P-06 | `config/mcp-server.toml`（新） | `query_timeout_seconds = 50`、`pool_max_size = 5`、`query_max_rows = 2000`、`fe_http_port = 8030` | Quick 固定 60 s 超时；限制行数，避免撑爆上下文 |
| P-07 | `pyproject.toml`（新） | 按 upstream `uv.lock` 锁定的直接依赖 + `mcp==1.28.1`、`starlette==1.3.1`、`boto3==1.43.103` | CodeZip 必须有 pyproject。CLI 用 `uv pip install --target … --python-platform aarch64-manylinux2014 --only-binary :all:` 安装，失败时依次回退 `_2_28`、`_2_34`；`rapidfuzz==3.14.5` 会触发回退到 `_2_28`（正常），安装后约 107 MB（上限 250 MB）。upstream 根目录的 `requirements.txt` 也要一起 vendoring（`test_deps.py` 读它）。P3 T3.2：pyproject 只锁直接依赖，CodeZip 解析到的 `caio` 0.12.9、`platformdirs` 4.12.0 比 `.venv` 新，所以再锁 `caio==0.12.5`、`platformdirs==4.11.15`，并用检查脚本对比 CodeZip 与 `.venv` 的 88 个 dist。P5：`botocore` 1.43.104（`boto3` 的依赖）、`rich-rst` 2.2.0（`cyclopts` 的）、`sse-starlette` 3.5.0（`mcp` 的）发布后，CodeZip 解析到新版（`.venv` 是 1.43.103、2.1.0、3.4.11），再锁这 3 个（共 5 个传递依赖），部署前后都用检查脚本确认 0 个不同 |
| P-08 | `test/test_agentcore_*.py`（新） | settings、store 兜底、service 模式、profile（`httpx.MockTransport`）、12 个工具 + Draft 7、HTTP app `/ping` + initialize | upstream 的离线测试保持全部通过 |
| P-09 | `src/config/loader.py` + `src/core/connection.py` + `config/mcp-server.toml`（P3 T3.0） | `[query] session_wait_timeout_seconds`（`ClusterConfig.session_wait_timeout`，默认 `None`）；不为 `None` 时 `ConnectionPool` 给 `aiomysql.create_pool` 传 `init_command="SET wait_timeout = N"`；仓库配置设为 `600` | Gateway 的每次调用都是新 microVM，microVM 销毁时池连接不会被关闭。没有 P-09 时它们在 Doris 上留 8 小时（默认 `wait_timeout` 28800），会耗尽 `max_user_connections = 100`。600 必须大于 `pool_idle_timeout_seconds = 300`（aiomysql 的 `pool_recycle`），否则池里的空闲连接会先被 Doris 关掉。没设这一项时行为与 upstream 相同 |
| P-10 | `src/server.py`（P5 T5.7a）| 失败的 `execute_query` / `query_metric` 的审计记录带 `error`（`CODE: message`，300 字符，经 mask）；`query_metric` 的成败取自解析后的结果，审计记下解析后的 `where` 以及 `having`、`order_by`、`limit`，`mf_command` 补上 `--where` / `--order-by` / `--limit` / `--having` | P4 发现：失败调用的审计记录 `error` 是 None，`query_metric` 的审计没有过滤条件，事后分不清失败的原因；`scripts/demo-check.sh post` 按它列出失败的调用 |
| P-11 | `src/store/compiler.py`（P5 T5.7a）| `_extract_time_constraints`：OR 包住 metric_time 条件时抛 `ValueError`（作为编译错误返回，提示每个范围调用一次）；NOT 紧挨 metric_time 条件或包住它所在的括号时同样抛 `ValueError`（`_METRIC_TIME_NOT_ERROR`）；严格的 `>` / `<` 把边界移 1 天（带时间部分时 1 s）；只提取 `TimeDimension('metric_time', …)`；多个条件取交集；带括号的范围不留下 `( AND )` | spec 阶段经 Gateway 实测旧 server：OR 连接两个范围、括号包住的范围都报 Doris 语法错误，`>` / `<` 按闭区间处理，多个条件只取最后一个。按分组粒度对齐时间范围是 MetricFlow 的设计（`reconcile` 的 `yoy_2026` 依赖它），不改；`NOT` 不能由时间约束表达，不报错的话清理之后 NOT 会落到下一个过滤条件上，变成结果错误的合法 SQL，所以直接报错 |

> v0.1 中的 P-07（ENABLE_WEBUI）和 P-08（SEED_EXAMPLE）已删除，原因见 §4.6。
> 工具数：upstream 10 个 + `list_recent_queries` + `get_query_profile` = **12**。工具名不带 `_tool` 后缀。

### 5.3 Profile 工具设计（`src/tools/profile.py`）

```text
FeHttpTarget(base_url, user, password, timeout=15.0)       # frozen dataclass；password 不出现在 repr 中

list_recent_queries(target, limit=20, user="", sql_contains="", *, scope="all", transport=None) -> str
  校验 1 ≤ limit ≤ 100，否则返回 INVALID_PARAMS
  scope="self" → 强制 user = target.user
  GET /rest/v1/query_profile → body.code==0 → data.rows
  过滤：user 精确匹配；sql_contains 在完整 SQL 中匹配（不区分大小写）
  按 "Start Time" 倒序，取前 limit 条
  返回 success({queries:[{query_id,user,default_db,task_type,state,start_time,end_time,total,sql(≤200 字)}], scope},
               {returned, matched, source})

get_query_profile(target, query_id, mode="summary", max_chars=20000, *, scope="all", transport=None) -> str
  qid = query_id.strip().lower()；必须匹配 ^[0-9a-f]{1,16}-[0-9a-f]{1,16}$（Doris 输出 query_id 时每段不补零；只允许 [0-9a-f-]，防止路径注入；P5 Runtime version 4 修正）
  mode ∈ {summary, full}；1000 ≤ max_chars ≤ 200000
  ① GET /rest/v2/manager/query/profile/text/{qid} → body.code==0 且 data.profile 非空 → 命中，source="v2"
  ② 仅 scope="all"：GET /api/profile/text?query_id=qid → 纯文本且第一行是段落标题 → 命中，source="api_text"
     （"query id <qid> not found" 这类纯文本、JSON code≠0 都算未命中，原文进 evidence）
  ③ 都没有 → success({query_id, profile_found:false}, {hint, evidence:{v2:{code,msg}, api_text:{code,msg}}})
  命中后 → summary 模式先裁剪 → 超过 max_chars 就截断并追加标记
  返回 success({query_id, profile_found:true, mode, source, total_chars, returned_chars, truncated, profile_text})

summarize_profile(text) -> str
  顶层段落 = 第 0 列匹配 ^([A-Za-z][A-Za-z ]*)(\([^)]*\))?:\s*$
  跳过 DetailProfile(...) 段落内容（保留标题 + 一行 "[N lines omitted …]"）
  删除值为 N/A 或所有聚合都为 0 的计数器行（如 "- MemoryUsage: sum 0.00 , avg 0.00 , max 0.00 , min 0.00"；
    "- InputRows: sum 0, avg 0, max 7, min 0" 保留）
  连续的逐列统计行（"<col>#<id> -> …"）折叠为一行 "[N column-statistics lines omitted …]"

错误映射（所有请求）：
  HTTP 401/403 或 body.code==401 → UNAUTHENTICATED
  httpx.TimeoutException → QUERY_TIMEOUT；其它 httpx.HTTPError、非 200、其它非 0 的 code → CONNECTION_ERROR

register_profile_tools(mcp, target, scope="all", transport=None)
  注册 list_recent_queries / get_query_profile（readOnlyHint=True），每次调用都写审计日志 log_tool_call
```

**「带 profile 执行 SQL」**：不新增工具，由 adapter skill 约定写法：
`execute_query("SELECT /*+SET_VAR(enable_profile=true)*/ ... /* trace:<随机串> */")` → `list_recent_queries(sql_contains="<随机串>")` 拿到 query_id → `get_query_profile(query_id)`。用 trace 注释定位 query_id，可以避开「连接池里 `LAST_QUERY_ID()` 不在同一条连接上」的问题。✅ 实测 Doris 4.1.4 会在 `Sql Statement` 里保留 `/* trace:… */` 注释（`mcp_smoke.py flow` 每次都会打印 `trace_comment_kept`）；如果将来 Doris 升级后剥掉了注释，就改用 `SELECT '<随机串>' AS _trace, ...`。

### 5.4 入口与运行参数

| env | Runtime 取值 | 本地（P1）取值 |
|---|---|---|
| `DORIS_HOST` | `172.31.25.143` | credentials.env 中的公网 IP |
| `DORIS_PORT` / `DORIS_HTTP_PORT` | 9030 / 8030 | 同左 |
| `DORIS_SECRET_ID` | `doris-mcp/mcp_svc` | 不设置 |
| `DORIS_USER` / `DORIS_PASSWORD` | 不设置（由 secret 提供） | `demo_ro`（P1）/ `mcp_svc`（P2 起）|
| `PROFILE_SCOPE` | `all`（D4） | `all` |
| `DORIS_MCP_WORKSPACE_DIR` | 不设置 → `$TMPDIR/doris-mcp-workspace` | 同左 |
| `MCP_PORT` | 8000 | 8000 |

---

## 6. Doris 侧准备（P2）

### 6.1 服务账号 `mcp_svc`
```sql
-- doris/01_mcp_user.sql（由 root 经 doris/apply-admin-sql.sh 执行；密码由 infra/40-doris-secret.sh 生成并存入
-- Secrets Manager，执行时经管道进入 doris/admin_sql.py，只在内存里替换占位符，不进 argv、文件和输出）
CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';   -- 重跑时收敛到 secret 里的密码
GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%';
GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'%';  -- CREATE 只为让 CREATE ... IF NOT EXISTS 通过
```
- 不授予 ADMIN / LOAD / ALTER / DROP。能访问哪些数据由 Doris 权限决定，MCP 的 SQL 校验器是第二道防线。`admin_sql.py` 只接受白名单内的语句（CREATE USER IF NOT EXISTS / ALTER USER … IDENTIFIED BY / 单库 GRANT SELECT_PRIV、CREATE_PRIV），执行后打印 `SHOW GRANTS`。
- `doris/permission_matrix.py`（T2.3）验证：`SHOW GRANTS` 恰好是上面两条 + Doris 默认项（`internal.information_schema`、`internal.mysql` 的 Select_priv，workload group `normal` 的 Usage_priv）；upstream store 初始化以 `mcp_svc` 成功；9 个写探针（LOAD ×4、CREATE、DROP ×2、GRANT、ADMIN）全部被拒，每个探针即使被允许也不改变任何数据。
- 先用 `'%'`（D6），因为 P2 需要从本机（13.125.9.110）联调，网络边界由 SG 控制（只有 /32 和 Runtime SG 两个来源）。P3 之后收紧为 `'172.31.%'`。
- **P3 T3.5 的迁移**（`doris/02_mcp_user_vpc.sql`，同样经 `apply-admin-sql.sh` 由 root 执行）：Doris 不能修改用户的 host，所以先 `CREATE USER IF NOT EXISTS 'mcp_svc'@'172.31.%'`（密码同一个 secret）+ `ALTER USER` + 两条与 01 相同的 GRANT，最后才 `DROP USER IF EXISTS 'mcp_svc'@'%'`。两个身份同时存在时，来自 `172.31.x` 的连接匹配更具体的 `'172.31.%'`，所以账号任何时候都有一个能用的身份。`admin_sql.py` 的白名单为此加上 `DROP USER IF EXISTS`，但只在前面已经 CREATE 了同一用户的另一个身份、并且本脚本没有建立或授权这个被删的身份时才放行。回滚（GATE）：重跑 `01_mcp_user.sql`。
- 迁移之后，开发机（另一个 VPC，经 Doris 公网地址连接）以 `mcp_svc` 登录会得到 **1045**，这正是收紧的目的。此后以 `mcp_svc` 做检查只能经 Runtime：`permission_matrix.py --url`（只读检查走 `execute_query`）、`reconcile.py mcp --url`（参照 SQL 用 `demo_ro`）。写探针只能直连，P2 T2.3 已经跑过，新身份的授权与旧身份逐项相同。

### 6.2 Profile 策略
- **不改全局配置**（D5），只用 `SET_VAR` hint 按需采集（§5.3）。

### 6.3 语义层：`ecom` workspace
- **发布走方案 C**（T2.5，`doris/publish-semantic.sh` → `doris/publish_semantic.py`）：root 在本机进程内调用 upstream `DorisStore('ecom')`，连 Doris 公网 IP（SG 已放行 /32）。
  1. 离线校验：`bootstrap_from_yaml` + **MetricFlow 引擎初始化** + measure / 模型重名检查。upstream 的 `validate` 不初始化引擎：缺 `agg_time_dimension`、measure 重名都能 commit 上去，之后该 workspace 的每次 `query_metric` 都会失败。
  2. `pre_validate_physical`：DESCRIBE 9 张物理表并检查列表达式。放在打开 store 之前，因为 `DorisStore(...)` 初始化本身就会写（CREATE IF NOT EXISTS + 元数据行）。
  3. staging：discard → upsert 全部本地文件 → delete 远端多余文件 → merged staging 与本地逐字节比对 → `staging_commit`（semantic_version + 1）→ active 与本地逐字节比对；semantic_version 必须前进。active 与本地一致且 staging 为空时不做任何写入。
  - 不用 Web UI：upstream 写接口要求 Doris 角色 `admin`，root 很可能只有 `operator`，会 403。不调用 upstream `commit_staging` / `grant_select_on_physical_tables` / `grant_workspace_access`：它们会执行 `GRANT SELECT_PRIV … TO '%'`。
  - 首次发布时 `DorisStore` 创建 `system_mcp` 库和 `workspace_metadata`、`active_store_ecom`、`staging_store_ecom` 三张表，插入 `semantic_version=1` 的元数据行，commit 后为 2。所以 root 发布在建 `mcp_svc` 之前，`mcp_svc` 只需要 SELECT + CREATE（CREATE 只用于 IF NOT EXISTS），不需要 LOAD。
- Runtime 用服务账号读取模型；`ensure_fresh` 在 semantic_version 变化时自动重载，**不需要**调用 `reload_semantic_layer`。
- 模型（`doris/semantic/ecom/`，10 个文件、22 个指标、9 张物理表）：

| 文件 | 来源表 | measure（同名指标）| 维度 / entity | 对应剧情 |
|---|---|---|---|---|
| `project.yaml` | `dim_date` | time spine（按天，2025-01-01 ~ 2026-12-31）| — | 同比 |
| `orders.yaml` | `v_paid_order` | gmv=sum(pay_amount，含运费)、order_count、buyer_count、discount_amount=discount_amount+coupon_amount | order_date、channel、device_os、is_first_order、order_status、promo_id；entity `order_entity`、shop、region | 第 2、3 幕 |
| `order_items.yaml` | `fact_order_item` | item_pay_amount、item_quantity、item_profit、item_rows（`create_metric: false`，由 metrics.yaml 定义指标）| order_date；entity order_item、`order_entity`、shop、category、brand | 第 3 幕 |
| `refunds.yaml` | `fact_refund` | refund_count、refund_amount | apply_date、refund_reason、refund_type、refund_status；entity refund、order_item、shop | 第 5.1 幕 |
| `reviews.yaml` | `fact_review` | review_count、avg_rating、bad_review_count(rating≤2) | review_date、has_image；entity review、shop | 第 5.4 幕 |
| `regions.yaml` / `shops.yaml` / `categories.yaml` / `brands.yaml` | `dim_region` / `dim_shop` / `v_category` / `dim_brand` | — | area、province、city、city_tier / shop_name、shop_type、shop_level（entity region）/ cat1–cat3_name / brand_name、brand_tier | — |
| `metrics.yaml` | — | 13 个显式指标：aov、gmv_mini_program、mini_program_share、gmv_last_year、gmv_yoy、line_gmv、qty、gross_profit、gross_margin、item_count、refunded_item_count、refund_rate、bad_review_rate | — | — |

- 口径与编译器的坑（spec 阶段实测，写在 YAML 注释和 `doris/test/test_semantic_models.py` 里）：
  - entity 叫 `order_entity`（`order` 是 SQL 保留字）；`shop_id` 是 entity，按店铺过滤写 `shop__shop_name`。
  - 订单级 GMV（`gmv`，含运费）与明细级 GMV（`line_gmv`，不含运费）是两个口径；订单级指标不能按 `cat1` / 品牌切（fan-out），按类目、品牌看用 `line_gmv` / `qty` / `gross_margin`。
  - 明细指标 `line_gmv` / `qty` / `gross_profit` 加已支付过滤 `order_entity__order_status IS NOT NULL`（能关联到 `v_paid_order`）；`refund_rate` = `refunded_item_count` / `item_count`，按故事 5.1 **不**过滤支付状态。
  - offset 指标（`gmv_last_year` / `gmv_yoy`）必须按 `metric_time` 分组并给出结束日期（time spine `dim_date` 到 2026-12-31）。
  - upstream 的 query_metric 会把指标列的 NULL 改写成 0（tools/semantic.py）：2025 年及更早期间没有去年同期数据，gmv_last_year / gmv_yoy 返回 0 表示「无数据」而不是「持平」。两个指标的 description 都写明了这一点（P2 整体评审 I1）。
  - `<` / `>` 会被编译成闭区间，时间范围用 `BETWEEN`；`metric_time` 放在 `OR` 里会生成错误的 SQL；join 来的维度写全路径（裸名按第一条路径解析）。
  - YAML 里字面量 `$` 写成 `$$`；必须恰好有一个 project 文档。
- 对账（`doris/reconcile.py`）：11 个故事线用例（YTD 汇总、2026 月度、同比、渠道、大区、小程序季度占比、一级类目、品牌层级、故事 5.1 退款率、店铺类型评价、退款原因），金额到分（误差 ≤ 0.005）、比率误差 ≤ 1e-6，与对照 SQL 一致。`direct` 模式在本机编译 YAML（T2.4，`demo_ro`），`mcp` 模式经进程内 MCP server 调用 `list_metrics` / `query_metric`（T2.6，`mcp_svc`）。

### 6.4 安全组（P0 的 `infra/10-network.sh` 创建）
- `doris-mcp-rt`（挂到 Runtime ENI）：**无入站**。删除默认的全放行出站，只放行：TCP 9030/8030 → `doris-demo-sg`；TCP 443 → `doris-mcp-vpce`；TCP 443 → S3 prefix list `pl-63a5400a`（共 4 条）。
- `doris-mcp-vpce`（挂到 Interface endpoint）：入站只允许来自 `doris-mcp-rt` 的 TCP 443；删除默认出站。
- `doris-demo-sg`（`sg-0a02e336df4299888`）：新增**来源为 SG 引用** `doris-mcp-rt` 的 TCP 9030、8030。**不加任何 CIDR 规则**。现有的 `13.125.9.110/32`（22/8030/9030）保持不变。
- AmazonProvidedDNS 的流量不受安全组过滤，出站不需要为 DNS 开规则。

---

## 7. AWS 基础设施（us-east-1）

所有脚本都 `source infra/lib.sh`：默认 dry-run（只打印将要执行的变更命令，只读查询照常执行）；`APPLY=1` 才真正执行；先查询再创建（幂等）；新资源的 ID 写入 `infra/state.env`；所有资源都打 `Project=doris-mcp-demo` 标签。需要把 secret 作为 AWS CLI 输入时，写到 `private_tmp` 生成的 0600 临时文件里，用完立即删除（AWS CLI v2 的 `file://` 读不了 `/dev/fd/N` 和 stdin）。

| 脚本 | 阶段 | 资源 |
|---|---|---|
| `infra/10-network.sh` | P0 | SG `doris-mcp-rt`、`doris-mcp-vpce`（§6.4）；`doris-demo-sg` 增加 2 条 SG 引用规则；S3 Gateway endpoint（主路由表）；Interface endpoint `logs`、`secretsmanager`（az4 + az1，private DNS）|
| `agentcore deploy`（`dorismcp/`）| P0 / P3 | Runtime `dorismcp`：CodeZip、PYTHON_3_12、protocol MCP、**AWS_IAM**、VPC（3 个子网 + `doris-mcp-rt`）；P0 的 envVars：`DORIS_HOST/PORT/HTTP_PORT`；P3 增加 `DORIS_SECRET_ID=doris-mcp/mcp_svc`、`PROFILE_SCOPE=all`，codeLocation 换成 `../mcp-server/`，执行角色换成 `doris-mcp-runtime-role`（`executionRoleArn`；CDK 不再生成角色）|
| `infra/35-runtime-role.sh` | P3 | IAM 角色 `doris-mcp-runtime-role`：信任 `bedrock-agentcore.amazonaws.com`（限本账号、本区域）；内联策略 `doris-mcp-runtime` 只允许写 `/aws/bedrock-agentcore/runtimes/dorismcp_dorismcp-*` 日志组、`logs:DescribeLogGroups`，以及对 `DORIS_SECRET_ARN` 这一个 secret 的 `secretsmanager:GetSecretValue`（secret 用 AWS 托管密钥，不需要 `kms:Decrypt`）；ARN 写入 `state.env` 的 `RT_ROLE_ARN`，`scripts/render-agentcore.py --phase server` 把它写进 `agentcore.json` |
| `infra/20-cognito.sh` | P0 | user pool `doris-mcp-quick`（只允许管理员建用户）、域名前缀 `doris-mcp-890717383483`、resource server `doris-mcp`（scope `invoke`）；client A `quick-user`（授权码 + PKCE，带 secret，callback 见 §4.4，scope `openid doris-mcp/invoke`）；client B `quick-service`（client_credentials，scope `doris-mcp/invoke`）；演示用户 `demo`（密码存入 Secrets Manager `doris-mcp/cognito-demo-user`）|
| `infra/30-gateway.sh` | P0 | IAM 角色 `doris-mcp-gateway-role`（信任 `bedrock-agentcore.amazonaws.com`，限定 SourceAccount；只允许对该 runtime 调用 `InvokeAgentRuntime`）；Gateway `doris-mcp-gw`（MCP，CUSTOM_JWT，allowedClients = A、B，allowedScopes = `doris-mcp/invoke`）；target `doris`（mcpServer endpoint = Runtime invoke URL，GATEWAY_IAM_ROLE）。P5：`GW_EXCEPTION_LEVEL`（默认 `DEBUG`；空串时不传 `--exception-level`；其他值拒绝）；description 放进 create 和 update 共用的参数（`update-gateway` 会替换整个配置，P3 同步时 description 被清空）|
| `infra/40-doris-secret.sh` | P2 | Secret `doris-mcp/mcp_svc`（`{"username":"mcp_svc","password":<get-random-password>}`）|
| `infra/99-cleanup.sh` | P5（T5.6）| 只删 `state.env` 记录的资源，按依赖顺序：① Gateway target，再删 Gateway；② 栈 `AgentCore-dorismcp-default`（Runtime），等到 DELETE_COMPLETE；③ VPC endpoints S3 / logs / secretsmanager，等它们消失；④ Cognito 域名（有域名的 user pool 删不掉），再删 user pool；⑤ 2 个 secret（默认 7 天恢复期，`FORCE_DELETE_SECRETS=1` 立即删除）；⑥ `doris-demo-sg` 上只删引用 `doris-mcp-rt` 的入站规则，其他规则不碰；⑦ 等 Runtime 的 ENI 释放（删栈之后还要几分钟），撤销两个 SG 之间的引用，删除 `doris-mcp-rt`、`doris-mcp-vpce`；⑧ IAM 角色 `doris-mcp-gateway-role`、`doris-mcp-runtime-role`（先删内联策略）。第一次删除之前先做全部检查：调用者账号 = `ACCOUNT_ID`，每个资源都带 `Project=doris-mcp-demo`（栈是 `agentcore:project-name=dorismcp`），Gateway 名为 `doris-mcp-gw`；任何不符或意外错误都 FATAL，一个都不删。已经不存在的资源跳过，中断后可以重跑。不碰 `state.env`（作为记录保留）、日志组、X-Ray 设置和其他项目；Doris 侧（`DROP USER mcp_svc`、`DROP DATABASE system_mcp`）由用户人工执行 |

**Runtime invoke URL**：`https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<URL 编码后的 Runtime ARN>/invocations?qualifier=DEFAULT`

**agentcore CLI 0.30.0 实测（T0.4）✅**
- `agentcore create --project-name dorismcp --no-agent --skip-git --output-dir .` 不需要交互。生成的文件有：
  - `dorismcp/AGENTS.md`、`dorismcp/README.md`；
  - `dorismcp/agentcore/` 下的 `agentcore.json`、`aws-targets.json`、`.gitignore`、`.llm-context/`、`.env.local`（空文件，已忽略）、`cdk/`。
  - `cdk/node_modules` 在 create 时就装好了（约 307 MB，已忽略）。
- 所有命令都在**项目根目录 `dorismcp/`** 下执行，不需要进 `dorismcp/agentcore/`：`agentcore validate`、`deploy --dry-run -v`、`deploy -y -v`、`status --json`。
- 生成的资源与路径：
  - CloudFormation 栈 `AgentCore-dorismcp-default`。Runtime 实际名称是 `<project>_<runtime>` = `dorismcp_dorismcp`。首次部署耗时 5 分 41 秒。
  - CodeZip staging 目录是 `dorismcp/agentcore/.cache/<runtime>/staging`（spike 版 63 MB，已忽略）。
  - 日志组 `/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT`。平台每 2 s 调用一次 `GET /ping`。
- 执行角色由 CDK 默认生成，带通配权限（`bedrock:InvokeModel` 对全部 foundation model、`logs:DescribeLogGroups` / `xray:Put*` 对 `*`、configuration-bundle），与 R-41 不符 → P3（T3.1）收紧（§14）。
  - P3 的做法：不在 CDK 之外改这个角色，而是自建 `doris-mcp-runtime-role`，经 `agentcore.json` 的 `executionRoleArn` 交给 CDK 导入；导入的角色 CDK 不附加任何策略。spec 阶段 `agentcore deploy --diff` ✅：删除 CDK 角色和它的 DefaultPolicy，Runtime **原地更新**（`RUNTIME_ARN` 不变，Gateway target 不用改）。X-Ray 写权限随之去掉，这是预期的（`disableTransactionSearch`，不用 X-Ray）。
- ⚠ **账号级副作用**：只要项目里有 Python runtime，每次 `deploy` 结束时 CLI 都会执行 `setupTransactionSearch`：
  - 如果 X-Ray trace 目的地不是 CloudWatchLogs，就改过去；
  - 把 X-Ray indexing rule `Default` 设为 `transactionSearchIndexPercentage`（默认 100%）。
  - P0 部署时 rule 被设为 100%，用户决定保持现状。开发机上已设置 `~/.agentcore/config.json` 的 `"disableTransactionSearch": true`，之后的 deploy 会跳过这一步；**在其他机器上部署前也要先这样设置**。
- 与旧仓库验证过的 v0.19 的逐项差异：旧仓库不在开发机上，**无法逐项核实**。能确认的只有一点：`prepare/` 方案报告里用的 starter toolkit `agentcore configure / launch` 在 0.30 中已不再使用，改为上面的 `create` / `deploy`。

**降级方案**：如果 Gateway 的 IAM 出站在 P0 调不通，回退到官方博客的 2LO 方案：Runtime 改为 CUSTOM_JWT，Gateway 出站走 AgentCore Identity OAuth（client_credentials，复用同一个池的 client B），不需要第二个池。

---

## 8. Quick 桌面版集成

### 8.1 主路径 ①：Cloud Connector → Gateway
1. 桌面版 **Customize → Connectors → Create → Cloud Connector → MCP**（在 Web 端 Connectors → MCP 创建效果相同，创建后三端都能用）。
2. URL：`https://<gateway-id>.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp`
3. 鉴权（D3）：
   - **User authentication（主）**：Client ID/Secret 填 client A；Token URL 为 `https://doris-mcp-890717383483.auth.us-east-1.amazoncognito.com/oauth2/token`，Authorize URL 把末尾换成 `/oauth2/authorize`。演示者用 Cognito 用户 `demo` 登录一次即可。
   - **Service authentication（备）**：填 client B，不需要用户登录。
   - client secret 由用户**在自己的终端里**获取（不要用 Claude Code 的 `!` 前缀，否则 secret 会进入对话记录）：`aws cognito-idp describe-user-pool-client --region us-east-1 --user-pool-id <COGNITO_POOL_ID> --client-id <CLIENT_A_ID> --query UserPoolClient.ClientSecret --output text --no-cli-pager`。演示用户密码同理：`aws secretsmanager get-secret-value --region us-east-1 --secret-id doris-mcp/cognito-demo-user --query SecretString --output text --no-cli-pager`。（T0.7 经验：命令要写成单行，并显式带上 `--region`、`--output text`、`--no-cli-pager`，否则用户的 CLI 配置可能导致没有任何输出；凭证必须属于账号 `890717383483`。）
4. 创建后**逐个启用工具**（新工具默认禁用）；只读工具设为 Always Allow，`execute_query` 在演示时也设为 Always Allow（D7）。P4 不是彩排，所以 `execute_query` 用 Ask Each Time（D7 的「平时」）；`reload_semantic_layer` 没有 readOnly 注解，始终用 Ask Each Time。
5. 工具有变更时：`aws bedrock-agentcore-control synchronize-gateway-targets` → 在 Quick 连接器详情页点 **Sync**（会重新授权）→ 启用新工具。

### 8.2 备份路径 ②：桌面版 Local stdio → Runtime（SigV4）—— 已取消（D9）
> v0.3.1：按 D9 不做这条路径，备份改为 Cloud Connector + Service auth（§4.4、§8.1）。下面的内容保留作参考（开发机上用 `mcp-proxy-for-aws` 冒烟仍然适用）。
```json
{
  "mcpServers": {
    "doris-agentcore": {
      "command": "uvx",
      "args": ["mcp-proxy-for-aws@latest",
               "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<URL编码的RuntimeARN>/invocations?qualifier=DEFAULT",
               "--service", "bedrock-agentcore", "--region", "us-east-1", "--timeout", "55"],
      "env": { "AWS_PROFILE": "doris-demo" }
    }
  }
}
```
- `mcp-proxy-for-aws` v1.7.0 的参数（✅ 已查看 `--help`）：`[--service] [--profile] [--region] [--metadata] [--header K=V] [--read-only] [--log-level] [--retries] [--timeout] [--connect-timeout] [--read-timeout] [--write-timeout] [--tool-timeout] [--skip-auth] endpoint`。
- 优点：不经过 Cognito / Gateway；同一份 JSON 可以导入 Claude Code，用来对照演示 skill 的原生用法。
- 缺点：本机要有 AWS 凭证（最小 IAM：只对该 ARN 允许 `bedrock-agentcore:InvokeAgentRuntime`，见 `infra/policies/local-proxy.json`）。
- **不推荐**：Remote + 静态 Bearer（Cognito access token 最长 1 天就会过期）。

### 8.3 「Doris 专家」Agent
- 在桌面版创建两个自定义 Agent，指令相同（`quick/agent-instructions.md`），各自只关联一个连接器：
  - 「Doris 专家」关联 `doris-mcp`（User auth，主路径）；
  - 「Doris 专家（svc）」关联 `doris-mcp-svc`（Service auth，备份路径）。
  - 两个连接器暴露的工具名都是 `doris___*`，一个 agent 同时关联两个连接器会出现重名工具。
  - P5（T5.3）：「Doris 专家」（桌面版关联 `Doris-Desktop-MCP`）挂上 §9 的 5 个 skill；指令第 5 条要求诊断类问题先加载 `doris-mcp-adapter`（Quick 不一定会自动选中它，T5.3 A5 实测）。
- 指令只写三件事：
  - 角色：基于真实 ecom 集群的 Doris 专家；
  - 硬约束：证据优先、只读、DDL 只给出不执行；外加 60 s 超时和不复述连接信息；
  - 演示口径：中秋节 2026-09-25 12:00 的业务设定，以及同比、占比指标的用法。
- 指令文件由 `quick/test/test_agent_instructions.py` 检查：长度、三段结构、关键规则；工具名都带 `doris___` 前缀并且真实存在；指令里的指标名是语义层发布的指标，维度名能在 `query_metric` 里编译，指标个数与语义层一致；没有 URL、IP、ARN、账号。
- skill 选择交给 Quick 按 description 自动匹配。

---

## 9. Skills 集成（P5）

| 步骤 | 做法 |
|---|---|
| 1. 获取 | `git clone apache/doris-skills`，锁定 commit `0476f3b`（`scripts/build_skills.py` 的 `LOCKED_COMMIT`；文件从 git 对象读取，不读 clone 的工作区）|
| 2. 导入 | 桌面版 **Customize → Skills → From folder**，按顺序导入 `quick/skills/` 的 5 个文件夹：`doris-mcp-adapter`（先导入）、`doris-debug`（**整个文件夹一次导入**，子文件夹作为参考文件随它导入）、`doris-profile-reader`、`doris-best-practices`、`doris-architecture-advisor`；每个 < 1 MB（上限 6 MB）。upstream 的 `doris-repo-review`（审 Doris 源码的 PR，不连集群）不导入；`LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md` 随副本保存，不导入 |
| 3. adapter skill | 自写 `quick/skills/doris-mcp-adapter/SKILL.md`，description 写「在本环境执行任何 doris-* skill 前必读」。正文：① 本环境**没有 doriscli**；② 下方翻译表；③ 工具名可能带 `doris___` 前缀（经 Gateway），也可能不带（Local 直连）；④ 带 profile 执行的约定写法；⑤ 只读边界和 60 s 超时（大查询先 EXPLAIN、加 LIMIT）；⑥ 证据优先 |
| 4. 副本内提示 | `scripts/build_skills.py` 生成副本：每个 `SKILL.md`（含 `doris-debug` 的子 skill）正文第一行是提示「Environment: Amazon Quick with the Doris MCP tools (`doris___*`), not `doriscli`. Load the `doris-mcp-adapter` skill …」；`doris-architecture-advisor`、`doris-best-practices` 的 description 超过 Quick 的 1024 字符，换成保留全部触发词的缩写版；修 1 处断链（`03-case-index.md` → `03-cir-case-index.md`）；`UPSTREAM.md` 由同一组常量生成。不改 upstream；`--check` 确认副本等于锁定 commit 加这些改动 |

**doriscli → MCP 翻译表**（写入 adapter skill）

| skill 期望 | MCP 调用 |
|---|---|
| `doriscli sql "<SELECT/SHOW/DESC/EXPLAIN>"` | `execute_query(sql, database)` |
| `doriscli sql ... --profile` | `execute_query("SELECT /*+SET_VAR(enable_profile=true)*/ ... /* trace:X */")` → `list_recent_queries(sql_contains="X")` → `get_query_profile(qid)` |
| `doriscli profile get <qid>` | `get_query_profile(qid, mode="summary")`，需要时用 `mode="full"` |
| `doriscli profile list` | `list_recent_queries(limit, user)` |
| `doriscli profile list --active` | `execute_query("SHOW PROCESSLIST")`（正在运行的查询；`list_recent_queries` 只列已结束的）|
| `doriscli profile diff a b` | 调用两次 `get_query_profile`，由 agent 对比 |
| `doriscli profile history "<pat>"` | `list_recent_queries(sql_contains=pat)`（只覆盖已采集 profile 的查询；audit_log 当前未启用）|
| `doriscli tablet db.t` | `execute_query("SHOW DATA SKEW FROM db.t")` + `SHOW TABLETS FROM db.t` + `SHOW COLUMN STATS db.t` |
| `doriscli auth status` | `check_service_health()` |
| 写操作（CREATE / ALTER / INSERT） | **不执行**，输出 DDL 由人工执行（Track B 的 HITL）|

---

## 10. 演示脚本（对齐「中秋节的一天」）

| 段落 | 用户在 Quick 桌面版里问 | 用到的工具 / skill | 前置条件 |
|---|---|---|---|
| 开场 | 「检查一下 Doris 连接状态」 | `check_service_health` | — |
| 第 2 幕 经营大盘 | 「今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比」 | `list_metrics` → `query_metric` | ecom 语义模型 |
| 第 3 幕 大促复盘 | 「618 和双 11 哪个类目贡献最大？」 | `query_metric` / `execute_query` | — |
| 第 5 幕 问题排查 | 「最近哪家店的退款率异常？原因是什么？物流有没有问题？」 | `execute_query`（窗口函数、TOKENIZE、MATCH_PHRASE、PERCENTILE）| — |
| 第 7 幕 + Track A | 「按天统计埋点 UV 这个查询为什么要这么久？给出 profile 证据」 | adapter → 带 hint 执行 → `list_recent_queries` → `get_query_profile` → `doris-profile-reader` 解读 | profile 工具 |
| Track B 设计评审 | 「评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL」 | `doris-best-practices`：`SHOW CREATE TABLE` / `SHOW PARTITIONS` / `SHOW DATA SKEW` → 推荐 DDL | 由人工执行 |
| 收尾 | 「为 agg_daily_traffic 这类场景推荐数据模型」 | `doris-architecture-advisor` | — |

> 第 1 幕（Stream Load 实时写入）和第 7 幕建 MV 都是写操作，仍由演示者在 mysql 客户端或脚本里执行，Quick 只负责读结果。这正好体现「读 = MCP，写 = 人工」的边界。

---

## 11. 分阶段实施与验收

具体任务见 `tasks.md`；每个阶段的执行计划在 `plans/` 下。

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **P0 技术验证** | VPC endpoints + SG；最小 MCP（`net_check`）部署到 Runtime VPC 模式；Cognito；Gateway（IAM 出站）；Quick 桌面版 ① 和 ② 各连一次（② 按 D9 取消，改为 Service auth 连一次 ✅）| ① Runtime 内能 TCP 连通 172.31.25.143:9030/8030；② 经 Gateway 能列出并调用 `doris___net_check`；③ 桌面版两条路径都能调用该工具（按 D9 为 User auth 与 Service auth，均 ✅）；④ 记录冷启动耗时、OAuth 回调 URL 和 scope 行为 |
| **P1 本地改造** | §5 全部补丁；本机用 `demo_ro` 连 Doris 公网 IP 联调 | 12 个工具都能调；Draft 7 校验通过；upstream 离线测试全部通过；profile：用 hint 执行 → 能列出 → 能取到 summary（< 20k 字符）；非法 qid、找不到、密码错误三种情况都返回结构化结果 |
| **P2 Doris 与语义层** | §6：secret、账号、授权、ecom 语义模型发布（方案 C）| `mcp_svc` 权限矩阵 14/14（`SHOW GRANTS` 恰好是 R-42 + Doris 默认项、store 初始化成功、9 个写探针全部被拒）；经 MCP server 的 `query_metric` 与故事线 SQL 11/11 到分一致，已发布的 22 个指标与本地模型一致 |
| **P3 AgentCore 部署** | P2 评审遗留 M1–M4 + 补丁 P-09；Runtime 切换为 `mcp-server/`，接入 secret，执行角色换成专用角色；同步 Gateway target；`mcp_svc` host 收紧（`plans/P3-deploy.md`）| SigV4 直连冒烟通过（12 个工具、flow 6/6）；Gateway token 冒烟通过（`doris___*` 12 个、flow 6/6）；CloudWatch 能看到每次调用的审计日志；冷启动 + 典型查询 < 60 s（串行和 20 个并发，探针可重跑）；残留连接空闲 600 s 后被 Doris 回收；Gateway DEBUG 返回里没有 IP / 密码 / 栈；`mcp_svc` host 收紧为 `'172.31.%'`，经 Runtime 复核 5/5、对账 11/11；R-40 复核 |
| **P4 Quick 桌面版** | §8：① 主路径（User auth）+ 备份路径（Service auth，D9）+ Agent；T4.5 URL / IPv4 mask 收口；T4.6 Gateway 侧耗时探针（`plans/P4-quick.md`）| 两条路径都能完成 §10 的「开场 + 第 2 幕」，数字与参照值一致；工具权限按 D7 设置；每个问题的总耗时和每次工具调用的耗时都有记录（M-3），没有 424；scope 行为有结论（M-1）|
| **P5 Skills 与彩排** | §9 导入与 adapter；§10 完整彩排 2 次；P4 遗留（审计 P-10、metric_time 过滤 P-11、脚本 M-7–M-10）；演示前后检查 `scripts/demo-check.sh`；清理 `infra/99-cleanup.sh`（`plans/P5-skills.md`）| Track A、Track B 端到端无人工干预（执行 DDL 除外）；记录每步耗时（经 Gateway 时每次工具调用都含冷启动，预热无效，见 §13）|

---

## 12. 决策

D1–D8 已于 2026-09-26 确定，完整结论见 `requirements.md` 文末。后续如有新的决策，也追加在那里，并在本文变更记录中注明。

---

## 13. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| Quick 60 s 硬超时 | VPC 冷启动 + 重查询会报 424 | query_timeout 设为 50 s，profile HTTP 超时 15 s；大查询先 EXPLAIN 并加 LIMIT。**P0 实测（spike `net_check`，开发机在 ap-northeast-2）✅**：<br>• 直连（SigV4）：新会话 `initialize` 约 4.4 s（冷），复用 `Mcp-Session-Id` 后 `tools/call` 约 0.3 s（热）；经 `mcp-proxy-for-aws` 时每个进程都开新会话，一次调用约 8 s。<br>• 经 Gateway：**每次** `tools/call` 约 4.5–5.5 s（每次都是新 Runtime 会话）。<br>• Runtime 日志显示，server 从进程启动到返回 tools/call 不到 1 s，冷启动的时间主要花在 microVM 分配上。<br>冷启动 + 首次调用远小于 40 s，**不需要预热方案**。而且经 Gateway 时每次调用都是新会话，预热本来也没有效果（取消原来的「演示前预热」和「调大 idle timeout」）。完整 server 实测（P3）✅：<br>• T3.3 直连：共享 session p50 670 ms、p95 2277 ms；每次新 session p50 9111 ms、max 12057 ms。<br>• T3.4 经 Gateway：串行 p50 6158 ms、p95 9516 ms；20 个并发 p50 7159 ms、max 10122 ms。<br>每次调用约 5–10 s 的冷启动开销要从 60 s 预算里扣掉：`query_timeout` 50 s 的查询跑满时，端到端约 56–61 s，可能超过 60 s。T4.4 / T4.6 实测（2026-09-28）：每个问题的总耗时 「Doris 专家」网页版约 5 s / 15 s（用户记录）；桌面版（`Doris-Desktop-MCP`）问题 1 的工具调用约 12 s、问题 2 约 2–3 分钟（按工具调用时间估算，未计时）；单次工具调用最长 9863 ms，≥ 45 s 的 0 次；T5.5 不必为此调整 `query_timeout`。P5 彩排（T5.4）实测：单次工具调用最长 9655 ms，≥ 45 s 的 0 次，没有 424；T5.5 决定：`query_timeout` 保持 50 s |
| profile 体积 100–200 KB | 上下文溢出 / 响应过慢 | 默认 summary（实测约 9 KB）+ max_chars；需要时再取 full |
| Quick 的 scope 行为 | PRM 没声明 scope 时，Quick 会用默认 scope，可能导致鉴权失败 | Gateway 设 `allowedScopes=[doris-mcp/invoke]`，它会写进 PRM，P0 实测 User auth、Service auth 都在 scope 限制下成功（§4.5），**功能上已关闭**。scope 从哪里来：T5.3 导入时用户没有报告要求登录，仍**未证实**（T5.3 A4；P4 时 `doris-mcp` 的 Sync 没有要求登录，新建 `Doris-Desktop-MCP` 时出现了登录页，但没有读地址）。回退手段保留：先用 `GW_ALLOWED_SCOPES=` 去掉 scope 限制，再不行改用 Service auth |
| Gateway 与 Quick 两层工具缓存 | 改了工具但 Quick 看不到 | 固定流程：deploy → synchronize-gateway-targets → Quick Sync → 启用新工具 |
| 工具名前缀 `doris___` | skill 里写的工具名对不上 | adapter skill 明确说明两种写法 |
| `mcp-proxy-for-aws` 与 Runtime URL 不兼容 | ~~备份路径不可用~~ 只影响开发机冒烟（D9 后不再是演示路径）| ✅ T0.4 已验证兼容；已关闭 |
| agentcore CLI v0.30 与旧仓库验证的 v0.19 有差异 | 部署命令或 schema 不同 | T0.4 先 `agentcore validate`；以 CLI 实际生成的文件为准。✅ P0 已用 0.30.0 跑通 create / validate / deploy / status，实际行为见 §7 |
| `agentcore deploy` 修改账号级 X-Ray 设置 | Transaction Search indexing rule 被设为 100%，影响账号里其他产生 span 的工作负载的索引费用 | 用户决定 rule 保持 100%；部署机上设置 `~/.agentcore/config.json` `"disableTransactionSearch": true`（开发机已设）；deploy 类 GATE 要说明这一点（§7）|
| v1 profile API 跨用户可见 | 能看到其他用户的 SQL 文本 | D4 开关（self 模式同时关闭跨用户回退）；这是 Doris 自身的行为，写进风险说明 |
| stateless MCP 每次请求都重新 initialize | 延迟增加 | ✅ T0.6 已测：经 Gateway 时每次 `tools/call` 都是新 Runtime 会话，约 4.5–5.5 s（spike）。完整 server 实测 ✅：T3.3 共享 session p50 670 ms，每次新 session p50 9111 ms；T3.4 经 Gateway p50 6158 ms（每次都是新 microVM）。T4.4 实测（2026-09-28）：每个问题的总耗时 「Doris 专家」网页版约 5 s / 15 s（用户记录）；桌面版（`Doris-Desktop-MCP`）问题 1 的工具调用约 12 s、问题 2 约 2–3 分钟（按工具调用时间估算，未计时）；单次工具调用最长 9863 ms，≥ 45 s 的 0 次；体验：网页版和桌面版都能完成开场和第 2 幕；桌面版上 T0.7 建的连接器刷新不了工具列表，要用在网页版新建的连接器。明显影响体验时，再试给 target 同时放行 `Mcp-Session-Id` 请求头和响应头（§4.5，走 GATE）|
| 请求日志泄漏 SQL / 凭证 | upstream `RequestLoggerMiddleware` 会把 header 和 body 写进 CloudWatch | 入口不挂它（P-01）；只有审计日志进 stderr；T1.8 对所有日志 grep 真实密码，命中数必须为 0 |
| 主路由表挂 S3 Gateway endpoint、Interface endpoint 开 private DNS | 影响整个 default VPC | 对 S3 无副作用；Doris EC2 没有 instance profile，不调用 logs/secretsmanager |
| Gateway 每次调用都是新 microVM，池连接不被关闭（P3 发现）| 残留连接按 Doris 默认 `wait_timeout` 留 8 小时，累积到 `mcp_svc` 的 `max_user_connections = 100` 后出现 `Too many connections` | 补丁 P-09：池连接 `SET wait_timeout = 600`，残留连接最多 10 分钟（§5.2）。T3.4 实测 ✅：20 个并发后有 24 个连接（Sleep 23），11 分钟后只剩 1 个（Query），P-09 在线验证通过。之后每次在 Quick 里跑完一轮（T4.4、T5.4）都看一次连接数；超过 80 就停下来，和用户商量调高上限、缩短 `session_wait_timeout_seconds` 或 Runtime 的空闲超时 |
| 同一个 MCP session 里的并发调用（P3 发现）| spec 阶段在本机一个共享 session 里跑 20 个并发：24 个调用 6 个 `SERVICE_NOT_READY`（语义层重新加载期间，同一进程里的语义层工具都返回这个错误），p95 13.8 s | 经 Gateway 时每次调用在自己的 microVM 里，不会重叠，`pool_max_size = 5` 也不是瓶颈（各有各的池）；T3.4 经 Gateway 实测 20 个并发。只有复用 Runtime session 的客户端会遇到，出现时说明 Gateway 在复用 session |
| 新 microVM 首次用语义层要重新加载（P3 发现）| 本机实测第一次 `list_metrics` 11.5 s、`reload_semantic_layer` 7.7 s；经 Gateway 时每次语义层调用都在新 microVM 里，都要付这笔开销 | 计入 60 s 预算；T3.3（共享 session 和 `--fresh`）、T3.4（经 Gateway）用 `mcp_smoke.py time` 逐次测，超过 60 s 的调用停下来和用户商量（P0 M-4：探针在仓库里，可重跑）。实测 ✅：经 Gateway 最慢的是语义层调用，约 9.5–10.1 s（串行时 `list_dimensions_for_metric` 9516 ms、`reload_semantic_layer` 9507 ms，20 个并发时 `list_metrics` 10122 ms）|
| 私网 IP 出现在日志和返回里（P3 发现）| Runtime 的 CloudWatch 日志（启动行、连接池、FE HTTP URL）有 Doris 私网 IP；`get_query_profile` 返回的 profile 里有 BE 节点 IP | 日志组只在本账号内可见；profile 是演示要看的内容，不改。计划里所有输出都经 IP / URL 的 sed，日志只计数；P5 录屏时注意 |
| Doris 连不上时的错误消息带 host（P3 发现）| pymysql 的 2003 消息含 Doris 地址；upstream `sensitive_mask` 只遮密码和 token，这条消息会经 Gateway 原样返回给 Quick | 已知风险，T3.4 不为了测它而断网；T5.5 决定：不补丁，第 1 轮彩排没有出现 2003（4 个失败都是 SQL 错误或参数校验）（§14）。演示手册「出问题时」：回答里出现地址不要念出来，录屏剪掉 |
| CodeZip 的传递依赖漂移（P3 发现）| pyproject 只锁直接依赖，CodeZip 按 aarch64 解析到的传递依赖可能与测试过的 `.venv` 不同 | T3.2 锁定 `caio`、`platformdirs`，并用检查脚本对比 88 个 dist；P5 spec 阶段又发现 `botocore`、`rich-rst`、`sse-starlette` 3 个有新版，Task 6 锁到 `.venv` 的版本；执行时检查脚本列出更多的包，同样锁定。每次 deploy 前后都对 staging 目录跑检查脚本 |
| Runtime 偶发 502 / 冷启动慢（P5 发现）| spec 阶段连续 3 次 `demo-check pre`，有 2 次各有 1 项失败（Runtime 返回 502，或冷启动慢到 Gateway 报错），重跑就通过 | 平台侧的偶发问题，不改代码。演示前预检只有一项失败时重跑一次，同一项连续两次失败才排查（`quick/runbook.md`）；彩排中出现时记下时间，T5.5 对照审计日志。T5.4 实测：P5 的 6 次 `demo-check pre` 和彩排第 1 轮里 502 出现 0 次；有 1 次预检遇到平台抖动（一次 `list_recent_queries` 用了 30842 ms），`mcp_smoke flow` 的轮询预算因此从 15 s 改为 45 s |
| 用 OR 连接几个 metric_time 范围（P5 发现）| 旧 server 把条件删成 `() OR ()`，Doris 报语法错误，agent 会换写法反复重试 | P-11 改成明确的编译错误，并提示改法（每个范围调用一次，或用去年同期指标）；指令写明一次调用只写一个时间范围 |
| adapter skill 没被自动选中 | agent 照 doriscli 的写法让用户去运行命令 | 指令第 5 条要求诊断类问题先加载 `doris-mcp-adapter`；每个副本的 SKILL.md 第一行也指向它；T5.3 A5 实测：用 `execute_query` 执行 `SHOW FULL PROCESSLIST`，再查 `information_schema.active_queries` 和 `check_service_health`，没有让用户运行命令，也没有 `KILL` |
| upstream 版本漂移 | 补丁冲突 | vendoring 并锁定 commit；每处补丁单独提交，升级时 rebase |
| Doris 单节点 | 演示过程中 FE/BE 挂掉 | 演示前跑 `scripts/demo-check.sh pre`；Doris 运维手册 §8 已有处理步骤 |
| 会话中断 | 进度丢失 | spec + progress + state.env + 每个任务一个 commit（R-60）；在 tmux 中运行 |

---

## 14. 安全清单

- [ ] SG 只增加 **SG 引用**规则；任何 SG 都不出现 `0.0.0.0/0` 入站；`13.125.9.110/32` 保持现状；`doris-mcp-rt` 的出站只有 4 条（§6.4）。P3 T3.5 做 R-40 只读复核（本系统的 3 个 SG、Runtime ENI、Doris 实例）。spec 阶段附带发现：同一 VPC 里有 4 个 `launch-wizard-*` SG 带 `0.0.0.0/0` 入站，没挂在任何 ENI 上，不属于本系统，由用户决定是否清理
- [ ] 密码只存在于 Secrets Manager 和项目外的 `credentials.env`；`agentcore.json`、脚本、文档、git 历史里都没有明文；每次提交前运行 `scripts/check-secrets.sh`
- [ ] `mcp_svc` 最小权限：`SHOW GRANTS` 恰好是 R-42 + Doris 默认项，没有 ADMIN，9 个写探针全部被 Doris 拒绝（P2 T2.3 权限矩阵）；语义层发布不执行任何 GRANT（§6.3）；P3 后 host 收紧为 `'172.31.%'`（T3.5，§6.1）
- [ ] Runtime 执行角色、Gateway 服务角色、本机 proxy 用户都按具体 ARN 授权。P0：Gateway 服务角色已满足 ✅；**Runtime 执行角色**是 CDK 默认生成的，带通配权限（§7），**P3 T3.1 / T3.2 换成 `doris-mcp-runtime-role`**：只能写 `runtimes/dorismcp_dorismcp-*` 日志组，只能 `GetSecretValue` `DORIS_SECRET_ARN` 这一个 secret；CDK 角色删除
- [ ] Gateway `--exception-level DEBUG` 会把错误详情返回给客户端（§4.5）。**P3 复查结论：保留到 T5.5**（P4 接入 Quick 和 P5 彩排时排错要用），T3.4 对 6 类错误调用做泄漏检查：IPv4、密码、栈的计数都必须是 0，不是 0 时停下来，和用户商量是否提前调低（GATE）；T5.5 决定是否关闭，同时决定是否遮 2003 消息里的 host（§13）。P5：`infra/30-gateway.sh` 加 `GW_EXCEPTION_LEVEL` 开关（默认 DEBUG），T5.5（Task 8）决定：保留 DEBUG 到演示结束，description 已补上（GATE；之后重跑 `infra/30-gateway.sh` 要显式带 `GW_EXCEPTION_LEVEL`，默认值是 DEBUG）
- [ ] Doris FE 审计日志（`fe.audit.log`）可能记下 `CREATE USER` / `ALTER USER … IDENTIFIED BY` 的明文密码：P3 T3.5 请用户在 Doris 主机上只输出计数检查；不是 0 时停下来商量（轮换密码也会被审计）
- [ ] Cognito client secret 只填在 Quick 连接器里；不使用长期静态 token；Cognito 只允许管理员建用户
- [ ] CloudWatch 审计日志保留 SQL（upstream 的 `sensitive_mask` 保持开启）
- [ ] **旧公开仓库 `doris-mcp-agentcore` 的 `deploy.conf` 里有明文 root 密码**：如果这个密码在任何环境中仍在使用，请轮换，并清理该仓库的 git 历史（与本项目无关，但这个安全项还没有关闭）
- [ ] 演示结束后执行 `infra/99-cleanup.sh`（T5.6，`plans/P5-skills.md` Task 9）：先 dry-run，GATE 确认后 `APPLY=1`；删除 Interface endpoints（持续计费）和本项目的全部 AWS 资源（§7）；Doris 侧的 `mcp_svc`、`system_mcp` 由用户人工删除

## 15. 成本（us-east-1，粗估）

| 项 | 估算 |
|---|---|
| Interface endpoints：logs + secretsmanager × 2 AZ | ≈ 4 × $0.01/h ≈ **$29/月**（另加 $0.01/GB），演示后删除 |
| S3 Gateway endpoint | 免费 |
| AgentCore Runtime / Gateway | 按用量计费，演示量级很小 |
| Cognito、Secrets Manager | 很小（每个 secret $0.40/月）|
| Doris EC2 m6i.2xlarge（已有） | 约 $0.384/h，不用时按运维手册 §8.3 停机 |
