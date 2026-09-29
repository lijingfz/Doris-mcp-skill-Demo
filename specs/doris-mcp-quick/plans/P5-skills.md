# P5 Skills 与彩排 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务执行本计划。步骤用复选框（`- [ ]`）跟踪。
> **断线恢复：** 先按仓库根目录 `CLAUDE.md` 的恢复协议执行，再从 `progress.md`「当前状态」里写的任务/步骤继续。本计划里所有命令都在仓库根目录 `/home/ubuntu/AI-code/Doris-mcp-skill-Demo` 下运行（每个 bash 块第一行都是 `cd` 到这里）。执行顺序就是编号顺序：**Task 1（T5.1）→ Task 2（T5.2）→ Task 3（T5.7a 代码）→ Task 4（T5.7b）→ Task 5（T5.5 / T5.6 的离线脚本）→ Task 6（T5.7a 部署，GATE）→ Task 7（T5.3 + T5.4，用户）→ Task 8（T5.5）→ Task 9（T5.6，演示结束后，GATE）**。Task 1–5 是离线的 TDD，只有 Task 2 Step 5 和 Task 5 Step 5 做只读的在线核对；Task 6 重新部署 Runtime；Task 7 要等用户在 Quick 桌面版里导入 skill（30–40 分钟）并彩排两轮（每轮 30–45 分钟）；Task 9 等真正的演示结束后才做。每个 bash 块都自带 `MASK`、`source infra/state.env` 和需要的 token，可以单独重跑。`/tmp` 丢失（重启）后，先重跑下面的「从计划取文件」；Task 1 之后的步骤要用 `build_skills.py --check` 时，还要按 Task 1 Step 4 重新 clone upstream 到 `/tmp/doris-skills`；Task 7 的时间标记丢了，按 Task 7 Step 4 末尾的方法重建。
> **代码来源：** 本计划中的全部代码和测试已在 spec 阶段于临时目录完成 TDD，并在 `bcda0f3` 的干净 worktree 上按本文的顺序回放过：每个「确认失败」「确认通过」步骤的输出都是回放时实测的。嵌入的文件用 `/tmp/p5-extract.py` 按 sha256 校验后写出，**不要手抄**。`quick/skills/` 下 upstream 的 4 个副本（连同 `LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md` 共 119 个文件）不嵌入，由 `scripts/build_skills.py` 从锁定的 commit 生成，再用整棵树的 sha256 核对。GATE 有 3 个：Task 6 重新部署 Runtime、Task 8 重跑 `infra/30-gateway.sh`（只在决定改 Gateway 时；决策要改 server 时还有一次部署）、Task 9 `APPLY=1 infra/99-cleanup.sh`，每个都要用户单独确认。实测输出和本文不一致时，停下来查原因，不要为了对上输出去改测试。

**Goal:** 把 apache/doris-skills 的 4 个 skill（锁定 commit `0476f3b`，副本由脚本生成）和自写的 `doris-mcp-adapter` 接进「Doris 专家」，按 design §10 完整彩排 2 次，写好演示手册 `quick/runbook.md`；同时收口 P4 的遗留（审计 P-10、metric_time 过滤 P-11、CodeZip 漂移、脚本 M-7–M-10），写好演示前后的检查 `scripts/demo-check.sh` 和演示结束后的清理 `infra/99-cleanup.sh`。

**Architecture:**
- **T5.1 skills 副本（Task 1）**：`scripts/build_skills.py --source /tmp/doris-skills [--check]`。
  - clone 的 HEAD 必须是 `LOCKED_COMMIT`（`0476f3b84ade…`），否则报出两个 sha 和修正命令，exit 2。文件从 git 对象读取（`ls-tree -r -z` + 一次 `cat-file --batch`），不读 clone 的工作区。
  - upstream 顶层的每一项、`skills/` 下的每个文件夹都必须列在「导入」或 `EXCLUDED`（附理由）里：upstream 新增一个 skill 或 NOTICE，构建就会停下来。导入 `doris-architecture-advisor`、`doris-best-practices`、`doris-debug`、`doris-profile-reader` 和 `LICENSE.txt`、`CLI-CONTRACT.md`；不导入 `doris-repo-review`（审 Doris 源码的 PR，不连集群）。
  - 每个 `SKILL.md`（含 `doris-debug` 的 10 个子 skill，共 14 个）正文第一行是提示「Environment: Amazon Quick with the Doris MCP tools (`doris___*`), not `doriscli`. Load the `doris-mcp-adapter` skill …」，其余字节与 upstream 相同。
  - Quick 要求 description ≤ 1024 字符：`doris-architecture-advisor`（1328）和 `doris-best-practices`（1307）换成保留全部触发词的缩写版（975、978），缩写版必须能被 YAML 读回；覆盖一个本来就不超长的 description 算过期，构建失败。
  - 断链：`LINK_FIXES` 修 1 处（`doris-debug/SKILL.md` 里 3 次 `03-case-index.md` → `03-cir-case-index.md`）；`BROKEN_LINKS_ALLOWED` 列 4 个示例路径；其他断链让构建失败，允许的链接能解析了也失败。
  - 先渲染，全部通过才写盘（失败的构建不改任何文件）；只在 4 个副本文件夹里删除多余的文件。`UPSTREAM.md` 由同一组常量生成。`--check` 只比较，不写盘。
  - `check-secrets.sh` 的 secret-key 规则不再把 Doris 文档 S3 示例里的占位符（`<…>`、`${…}`、`...`、空值）当成泄漏，真实形状的值仍然命中：副本里有一处这样的示例，旧规则会让提交失败。
- **T5.2 adapter（Task 2）**：`quick/skills/doris-mcp-adapter/SKILL.md` 是 upstream skill 和 MCP 工具之间的翻译表：
  - `CLI-CONTRACT.md` 的每个命令和 flag、副本里用到的每个 `doriscli` 命令都有对应（`doriscli tablet` → 表的 `SHOW` 语句；`set` 是会话变量提示，不是语句；FE / BE HTTP 路径说明怎么用 SQL 代替）；
  - 带 profile 执行的约定（`SELECT /*+SET_VAR(enable_profile=true)*/ … /* trace:<随机串> */` → `list_recent_queries(sql_contains=…)` → `get_query_profile`；截断、full 模式、profile 不存在时怎么办；`max_chars` 用 server 接受的值）；
  - 只读边界（能做的、会被拒绝的；写操作和管理操作交给人）、60 s 限制、先给证据、不暴露连接信息。19 个检查。
  - agent 指令加第 5 条（诊断类问题先加载 adapter），写明可用的时间粒度、「同期同天数」要按天分组、一次调用只写一个时间范围；对账加 `yoy_same_days_2026_09`（按天分组的同期对比，12 个）。
- **T5.7a server 补丁（Task 3 写代码，Task 6 部署）**：
  - P-10（`src/server.py`）：失败的 `execute_query` / `query_metric` 的审计记录带 `error`（`CODE: message`，300 字符）；`query_metric` 的成败取自解析后的结果，审计记下解析后的 `where` 以及 `having`、`order_by`、`limit`，`mf_command` 补上对应的选项。
  - P-11（`src/store/compiler.py` 的 `_extract_time_constraints`）：OR 包住 metric_time 条件时报明确的编译错误（提示每个范围调用一次，或用 `*_last_year` 指标）；严格的 `>` / `<` 把边界移 1 天（带时间部分时 1 s）；只认 `TimeDimension('metric_time', …)`；多个条件取交集；带括号的范围不再留下 `( AND )`。
  - 锁 3 个传递依赖（`botocore==1.43.103`、`rich-rst==2.1.0`、`sse-starlette==3.4.11`）：它们在 P3 之后发了新版，CodeZip 按 `pyproject.toml` 解析到了新版，和测试用的 `.venv` 不一致。
- **T5.7b 脚本 minor（Task 4）**：`audit_check.py --failures` 按时间列出失败的调用（工具、错误、`query_metric` 的 `group_by` / `where` / `having`，IPv4 mask）；M-8 `mcp_smoke.py` 的 `--stdio` 也 mask（命令里的 URL、主机名）；M-9 `gw_latency.py` 接受数字时间戳，同一分钟同一工具的多个序列合并；M-7（审计里的工具名不带前缀）写进手册；M-10（`$v` 为空时 IP 计数输出 FAIL）从 Task 1 起用在每次提交前。
- **演示前后的检查和清理（Task 5）**：
  - `scripts/demo-check.sh pre`：10 项（账号、Gateway / target READY、token、12 个工具、`doris___` 流程、对账、权限矩阵、连接、连接数 ≤ 80）；`post --since MS --until MS`：5 项（窗口内的审计 + `--failures`、按整分钟放宽的 Gateway 耗时、token、连接）。子进程的输出都经过 MASK；token 不进 argv；调用方的 `DORIS_*`、`GW_TOKEN` 先 unset。
  - `infra/99-cleanup.sh`（T5.6）：按依赖顺序删除 `state.env` 记录的资源（design §7 的 8 步），第一次删除之前先做全部检查（账号、`Project` 标签、Gateway 名、栈的 `agentcore:project-name` 标签、Cognito 域名属于哪个 pool），默认 dry-run。
  - `infra/30-gateway.sh`：`GW_EXCEPTION_LEVEL`（默认 `DEBUG`，空串不传，其他值 FATAL），description 放进 create / update 共用的参数（`update-gateway` 会替换整个配置）。
  - `scripts/check-secrets.sh`：`99-cleanup.sh` 删掉的 secret 记一行 `SKIP`（Secrets Manager 说它已排期删除；或者它不存在，而调用方正是 `state.env` 的 `ACCOUNT_ID`），其他错误仍然失败。不改的话，Task 9 之后每次提交都过不了检查；只看「不存在」又会放过别的账号的凭证。
- **部署（Task 6，GATE）**：`agentcore deploy` 前后各跑一次 CodeZip 检查（0 个不同）和 7 个 `query_metric` 探针（旧 server 的结果已在 spec 阶段实测，新 server 的期望来自本机编译）；部署后 Runtime `version=3`，对账 12/12，权限矩阵 5/5。
- **Quick 侧（Task 7，用户）**：用户按 `quick/P5-guide.md` 导入 5 个 skill、更新两个 agent、按 D7 设置权限，检查 adapter 能不能被自动选中（A5）和登录页的 scope（M-1 情况 c）；然后彩排两轮，每轮前 AI 跑 `demo-check pre` 并记下开始时间，每轮后跑 `demo-check post` 并核对答案。整体评审放在 Task 7 Step 2，也就是代码、部署和指南都完成之后、交给用户之前。
- **修正和决策（Task 8）、清理（Task 9）**：按彩排结果修正，填演示手册的耗时表，定下 4 项决策（Gateway `exceptionLevel`、2003 错误里的主机地址、`query_timeout`、Gateway description）；演示结束后先 dry-run，GATE 后 `APPLY=1`，Doris 侧由用户人工执行。
- **spec 阶段的只读预验证**：
  - upstream `0476f3b`：177 个文件，没有 NOTICE；2 个 description 超长；`doris-debug/SKILL.md` 的 `03-case-index.md` 不存在（同一个 upstream commit 加的是 `03-cir-case-index.md`）；生成的 119 个文件共 566278 字节，每个文件夹 < 1 MB（Quick 的上限是 6 MB）。
  - 经 Gateway 对旧 server 跑了 7 个 `query_metric` 探针：OR 连接两个范围、括号包住的范围都报 Doris 语法错误，`>` / `<` 按闭区间处理，多个条件只取最后一个（Task 6 Step 2 的表）。新 server 的结果用 `reconcile.DirectBackend` 在本机编译、以 `demo_ro` 执行得到。
  - 按分组粒度对齐时间范围（按月分组时，9 月 1–25 日的过滤取 9 月整月）是 MetricFlow 的设计，`reconcile` 的 `yoy_2026` 依赖它，不改；指令改为「同期同天数」按天分组。
  - CodeZip：按 agentcore CLI 的方式解析 `mcp-server/pyproject.toml`，88 个 dist 里有 3 个比 `.venv` 新：`botocore` 1.43.104（`.venv` 1.43.103）、`rich-rst` 2.2.0（2.1.0）、`sse-starlette` 3.5.0（3.4.11）。
  - 带新代码的 `agentcore deploy --diff`：只有 Runtime 一个资源变化。
  - 对真实账号跑 `demo-check pre` 3 次：2 次各有 1 项失败（Runtime 返回 502，或冷启动慢到 Gateway 报错），重跑就通过；平台侧的偶发问题，手册里写明预检只有一项失败时重跑一次。
  - `99-cleanup.sh` 对真实账号 dry-run：全部检查通过，列出 18 个删除操作，没有删除任何东西。
  - 读一个不存在的 secret：CLI 输出 `aws: [ERROR]: An error occurred (ResourceNotFoundException) when calling the GetSecretValue operation: …`，`check-secrets.sh` 按括号里的错误代码判断，不依赖前缀。

**Tech Stack:** Python 3.12（仓库 `.venv`）· PyYAML · git（读 upstream 的对象）· MCP SDK（fastmcp Client）· MetricFlow（经 `doris/reconcile.py`）· AWS CLI v2（bedrock-agentcore-control、cloudformation、ec2、cognito-idp、secretsmanager、iam、logs、cloudwatch）· agentcore CLI / CDK · uv · bash · unittest · Amazon Quick 桌面版（用户侧）

**Spec:** `specs/doris-mcp-quick/requirements.md`（R-32、R-43、R-44、R-50、R-51、R-60、R-61；D7、D8）、`specs/doris-mcp-quick/design.md` v0.8（§5.2、§7、§8.3、§9、§10、§11 P5 行、§13、§14）

## Global Constraints

- 只用 us-east-1、账号 `890717383483`（环境变量里的凭证）；不要用 AWS profile `lijingfz`。本机环境的 `AWS_DEFAULT_REGION` 是 us-west-2，所以每条 AWS 命令都要显式指定 `--region us-east-1` 或 `AWS_REGION=us-east-1`（`infra/*.sh` 经 `lib.sh` 自带）。
- **GATE 只有 3 个**，每个都先展示命令和 dry-run / diff，用户确认后才执行，一次确认只对应那一次操作：
  1. Task 6：`agentcore deploy -y`（Runtime 升到新版本）；
  2. Task 8：`APPLY=1 bash infra/30-gateway.sh`（只在决定改 Gateway 的 `exceptionLevel` 或 description 时）；Task 8 的决策要改 server 时（2003 的主机地址、`query_timeout`），再部署一次，和 Task 6 一样单独确认；
  3. Task 9：`APPLY=1 bash infra/99-cleanup.sh`（演示结束后）。

  其余步骤 AI 侧只调用这些只读接口：`sts get-caller-identity`；`bedrock-agentcore-control` 的 get / list；`scripts/get-gw-token.sh`（读 client B 的 secret，不输出，再向 Cognito 取 token）；经 Gateway 的 MCP 调用（`list`、固定的只读流程、`query_metric` 探针、`conns`）；SigV4 `InvokeAgentRuntime`（`reconcile.py mcp --url`、`permission_matrix.py --url`）；`logs filter-log-events`、`cloudwatch get-metric-data`；`ec2 describe-security-group-rules`（Task 9，只输出计数）；`99-cleanup.sh` / `30-gateway.sh` / `25-runtime-state.sh` 的 dry-run（只有 describe / get / list）；`agentcore validate`、`agentcore deploy --diff`；`check-secrets.sh` 的 `secretsmanager get-secret-value`（只比较，不输出）。另外访问 GitHub（clone upstream）和 PyPI（`uv` 解析依赖）。Quick 里的操作、D7 权限的恢复和 Doris 侧的清理由用户执行。
- 密码、secret、Cognito ClientSecret、`GW_TOKEN` 不出现在仓库、命令行参数、日志、输出和对话里，**grep 的参数也不行**：要按值查找，只能用 `grep -cF -f <(printf '%s\n' "$PW")`，而且只输出计数。`GW_TOKEN` 只经环境变量交给 `--bearer-env GW_TOKEN`，块末尾 `unset`；每个块自己取一次（token 约 1 小时过期）。本计划的文字里不写 secret-key 规则能命中的字面量（键名后面紧跟 `=` 的写法），否则 `check-secrets.sh` 会把计划本身当成泄漏。
- **以下内容不出现在输出里**：Doris 主机地址、Doris 私网 IP、开发机 IP，以及 `RUNTIME_URL` / `GW_URL`。所有可能含这些内容的输出都经过 `MASK`，每个 bash 块开头都定义它：
  ``MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'``
  （Doris 主机地址是 IPv4 字面量，这条 sed 能覆盖）。
- **不要打印**：`dorismcp/agentcore/agentcore.json`（含私网 IP）、`render-agentcore.py --check` 的输出、`agentcore status` 的原始 JSON、部署日志的原文（只看 Task 6 里过滤后的行），以及 `infra/state.env` 的内容（只按变量名使用）。`99-cleanup.sh` 的输出里有 `state.env` 的资源 ID，只经 `/tmp/p5-idmask.py` 查看。`progress.md`、`design.md`、`quick/T0.7-guide.md`、`prepare/` 里有私网 IP 或 URL，只经 `MASK` 查看。
- 修改规格文件的方式：`progress.md` 只用 `/tmp/p5-progress.py` 修改；`design.md`、`tasks.md` 只用计数检查过的 python 修改（每个锚点必须恰好出现 1 次）。
- Doris 凭证只从 `/home/ubuntu/AI-code/Doris-test/credentials.env` 在**子 shell** 里 `source`（该文件没有 `export` 行），只 export 需要的变量；**永远不要 echo 或 cat 这个文件**。`DORIS_ROOT_*` 从不以原名传给任何进程；P5 不用 root。
- `demo_ro` 只做 SELECT / SHOW / DESCRIBE（对账的参照 SQL）；**不要用 `demo_ro` 试探写操作**。`mcp_svc` 只经 Runtime 使用，不要用它试探特权或诊断类语句（adapter 里「会被拒绝」的那些由 T5.3 A5 和彩排在 Quick 里观察）。MCP 不执行任何 DDL/DML；Doris 侧的清理（Task 9）由用户人工执行。
- 安全组在 Task 9 之前不改（R-40）；`99-cleanup.sh` 只删除本项目的两个 SG 和 `doris-demo-sg` 上引用 `doris-mcp-rt` 的入站规则，`doris-demo-sg` 本身和开发机的 `/32` 规则不动。VPC 里 4 个未挂载的 `launch-wizard-*` SG 由用户决定，本计划不碰。
- Gateway `pragent-github-gw` 和其他项目的资源、日志组、角色都不碰。
- 给用户看的内容（`quick/P5-guide.md`、`quick/P5-handoff.md`、`quick/runbook.md`、对话）不含 URL、secret、token、IP、ARN 和账号。Quick 要求重新填 client secret 或 `demo` 密码时，用户按 T0.7 在**自己的终端**里获取，不用 Claude Code 的 `!` 前缀（`!` 的输出会进对话）。
- 不修改 `prepare/` 和 `/tmp/doris-skills`（upstream 的 clone）。`quick/skills/` 下 upstream 的副本只由 `scripts/build_skills.py` 生成，不手改（`doris-mcp-adapter` 是自写的，例外）。测试 fixture 只用 TEST-NET 地址（`192.0.2.x`、`198.51.100.x`、`203.0.113.x`）和账号 `000000000000` / `111122223333`。
- 测试用 unittest：`.venv/bin/python -m unittest discover -s doris/test`、`-s scripts/test`、`-s quick/test`、`-s mcp-server/test -p 'test_agentcore_*.py'`（**不要**加 `-t .`）。shell 测试用假的 `aws` / `python`，不访问 AWS 或 Doris。upstream 离线测试要带 `PYTHON_BIN=$PWD/.venv/bin/python`。
- 选了 Subagent-driven 时，implementer / reviewer 全部用 Opus 5.5；subagent 不执行 `APPLY=1` 或部署，不访问 AWS、Doris 或凭证文件（`check-secrets.sh` 也会读 Secrets Manager 和凭证文件，同样不跑），不建分支、不提交；在线核对、GATE 和提交都由控制方执行。
- 代码、注释、脚本输出用英文；计划、progress、给用户的指南用中文。
- 每个任务结束：勾选 `tasks.md` → `/tmp/p5-progress.py` 更新「当前状态」并追加日志 → `bash scripts/check-secrets.sh`（需要有效的 AWS 凭证）→ 暂存区新增行的 IP 计数为 0（`$v` 为空时输出 FAIL，M-10）→ commit（message 结尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`）。全部在分支 `p5-skills` 上，不 push（D8）。

## Review Focus

1. **地址、URL、token 经新的输出泄漏**：`audit_check.py --failures` 列出的错误原因（`CONNECTION_ERROR` 的消息里有 Doris 主机地址）、`demo-check.sh` 各子进程的输出、`mcp_smoke.py --stdio` 命令里的 URL 和主机名、`99-cleanup.sh` 输出的资源 ID。相关的测试和检查：
   - Task 4：`test_audit_check` 的 `--failures` 测试（IPv4 mask、不输出 SQL 和其他参数）、`test_mcp_smoke` 的 `hidden_values` 测试；突变 af、m8；
   - Task 5：`test-demo-check.sh` 的 mask 和 token 检查（token 不进 argv、不导出、不打印）；突变 dc；在线核对的输出经 MASK，cleanup 的输出经 `p5-idmask.py`；
   - 每次提交前新增行的 IP 计数（M-10：`$v` 为空时是 FAIL，不再静默通过）。
2. **skill 副本和 upstream 对不上，或超出 Quick 的限制**：description 超过 1024 或丢了触发词、某个子 skill 的 `SKILL.md` 没有提示、断链、文件取自 clone 的工作区而不是锁定的 commit、upstream 新增的内容被静默漏掉。相关的测试和检查：
   - Task 1：`test_build_skills.py` 的 `TestHint`、`TestDescriptions`、`TestSelection`、`TestLinks`（38 个）；`quick/test/test_skills.py`（9 个，只看已提交的副本）；突变 sk、st；
   - `--check` 和整棵树的 sha256（`db3ca57c…`）；Task 2 Step 3 再跑一次 `--check`；
   - Task 7 Step 3 用户导入后的 A1 表（每个文件夹的名字和描述）。
3. **adapter 翻译错了**：agent 让用户去运行 `doriscli`、调用不存在的工具、`max_chars` 用了 server 不接受的值、带 profile 执行后找不到 profile。相关的测试和检查：
   - Task 2：`test_adapter_skill.py` 的 `CommandMap`（覆盖 `CLI-CONTRACT.md` 和副本里的每个 `doriscli` 用法）、`ProfileRecipe`（`max_chars` 取自 server 的参数定义）；突变 ad；
   - Task 7：A5（adapter 会不会被自动选中）、彩排步骤 5（Track A 的 profile 证据）。
4. **改了演示依赖的时间过滤**：P-11 之后，对账和演示问题的结果变了；OR 报错后 agent 反复重试。相关的测试和检查：
   - Task 3：`test_agentcore_time_constraints.py`（35 个，含 `TestDocumentedBehaviour` 11 个锁定已有行为）、`test_semantic_time.py`（7 个，本机编译，按月粒度对齐不变）；突变 p11；
   - Task 6：部署前后各跑 7 个探针，只有 strict、intersect、mixed、or 4 个变化，其余 3 个不变；部署后对账 12/12；
   - Task 7：两轮彩排的答案对照参照值，`demo-check post` 列出失败的调用。
5. **清理删错或删不干净**：删到其他项目的资源、删掉 `doris-demo-sg` 的其他规则、标签不符还继续删、ENI 还没释放就删 SG、中断后不能重跑。相关的测试和检查：
   - Task 5：`test-99-cleanup.sh`（81 个：全部检查在第一次删除之前、任何不符都 FATAL 且一个都不删、只撤销引用 `doris-mcp-rt` 的规则、已不存在的资源跳过、等待超时 FATAL）；突变 cl；对真实账号 dry-run；
   - Task 5：`test-check-secrets.sh` 的跳过检查（只有排期删除、或在 `state.env` 的账号里不存在才跳过；过期、没有权限、别的账号、没有 `state.env` 都失败）；突变 cs；
   - Task 9：执行前再 dry-run 一次，用户确认后 `APPLY=1`，之后再 dry-run 确认全部是「already gone」，`check-secrets.sh` 跳过 2 个 secret 后仍是 OK。

---

## 文件地图

| 文件 | 状态 | 任务 | 作用 |
|---|---|---|---|
| `scripts/build_skills.py`、`scripts/test/test_build_skills.py` | 新建 | Task 1 | 从锁定的 commit 生成 4 个副本和 `UPSTREAM.md`，`--check` 只比较；38 个测试（fixture 是临时 git 仓库）|
| `quick/skills/`（4 个副本、`LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md`，119 个文件）| 生成 | Task 1 | Quick 导入的 skill 文件夹；不嵌入本计划，sha256 核对 |
| `quick/test/test_skills.py` | 新建 | Task 1（Task 2 去掉 2 个 skip）| 已提交副本的布局、Quick 的限制、提示、description、链接；9 个 |
| `scripts/check-secrets.sh`、`scripts/test/test-check-secrets.sh` | 修改 | Task 1 | secret-key 规则不再把占位符当成泄漏；12 → 20 个检查 |
| `quick/skills/doris-mcp-adapter/SKILL.md`、`quick/test/test_adapter_skill.py` | 新建 | Task 2 | adapter skill；19 个检查 |
| `quick/agent-instructions.md`、`quick/test/test_agent_instructions.py` | 修改 | Task 2 | 第 5 条（诊断类问题先加载 adapter）、时间粒度、同期同天数、不用 OR；+6 个检查 |
| `doris/reconcile.py` | 修改 | Task 2 | 对账加 `yoy_same_days_2026_09`（12 个）|
| `mcp-server/src/server.py`、`mcp-server/src/store/compiler.py`、`mcp-server/UPSTREAM.md` | 修改 | Task 3 | P-10（审计的失败原因和过滤条件）、P-11（metric_time 过滤）|
| `mcp-server/test/test_agentcore_audit_errors.py`、`mcp-server/test/test_agentcore_time_constraints.py`、`doris/test/test_semantic_time.py` | 新建 | Task 3 | 17 + 35 + 7 个测试 |
| `scripts/audit_check.py`、`scripts/gw_latency.py`、`scripts/mcp_smoke.py` 和它们的测试 | 修改 | Task 4 | `--failures`；M-9；M-8；+24 个测试 |
| `infra/30-gateway.sh`、`infra/test/test-30-gateway.sh` | 修改 / 新建 | Task 5 | `GW_EXCEPTION_LEVEL`，description 进共用参数；30 个检查 |
| `infra/99-cleanup.sh`、`infra/test/test-99-cleanup.sh` | 新建 | Task 5 | T5.6 清理；81 个检查 |
| `scripts/demo-check.sh`、`scripts/test/test-demo-check.sh` | 新建 | Task 5 | 演示前后的只读检查；96 个检查 |
| `scripts/check-secrets.sh`、`scripts/test/test-check-secrets.sh` | 修改 | Task 5 | 清理删掉的 secret 跳过，其他错误仍然失败；20 → 36 个检查 |
| `mcp-server/pyproject.toml`、`mcp-server/UPSTREAM.md` | 修改 | Task 6 | 锁 `botocore`、`rich-rst`、`sse-starlette`（P-07）|
| `dorismcp/agentcore/.cli/deployed-state.json` | 部署生成 | Task 6 | 新的 `deployHash` |
| `quick/P5-guide.md`、`quick/P5-handoff.md`、`quick/runbook.md`、`quick/test/test_p5_docs.py` | 新建 | Task 7（Task 8 填耗时表）| 用户指南、交接清单、演示手册；10 个检查 |
| `specs/doris-mcp-quick/design.md`、`tasks.md`、`progress.md`、`RESUME.md`、本计划 | 修改 / 新建 | Task 1 Step 1、各任务收尾、Task 8、Task 9 | design v0.8 随计划提交；Task 8 写下 4 项决策（v0.9）；Task 9 清理之后 v1.0，`RESUME.md` 的「演示当天」一行换成「想再演示一次」|

常用测试命令：

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 最终 168 个
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 最终 137 个
.venv/bin/python -m unittest discover -s quick/test 2>&1 | tail -3                                  # 最终 60 个
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 最终 141 个
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3     # 🎉 All tests passed!
for t in doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh infra/test/test-35-runtime-role.sh \
         infra/test/test-40-doris-secret.sh infra/test/test-lib.sh scripts/test/test-check-secrets.sh \
         infra/test/test-30-gateway.sh infra/test/test-99-cleanup.sh scripts/test/test-demo-check.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 每行 all passed（后 3 个 Task 5 起才有）
```

## 从计划取文件

本计划嵌入了 33 个文件：每个 `<!-- file: NAME sha256=HEX -->` 下面紧跟的代码块就是一个文件，文件内容是块内文本加末尾换行。下面两个小工具先写到 `/tmp`：`p5-extract.py` 按 sha256 校验后写出文件，`p5-progress.py` 修改 `progress.md` 而不打印它（旧日志里有私网 IP）。然后把 6 个辅助工具取到 `/tmp`：突变工具 `p5-mut.py` 和它的突变表 `p5-mutations.json`（本节末尾）、`p5-rows.py`（Task 6 Step 2）、`p5-idmask.py`（Task 5 Step 5）、`p5-codezip-check.sh`（Task 6 Step 1）、`p5-steps.py`（Task 7 Step 4）。Task 1 Step 1 执行本节；`/tmp` 丢失后，从任何任务继续之前都先重跑本节。

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
cat > /tmp/p5-extract.py <<'EOF'
"""Write one embedded file of specs/doris-mcp-quick/plans/P5-skills.md to disk, after checking its sha256.

  .venv/bin/python /tmp/p5-extract.py --check          # checks every block's sha256; prints names and line counts
  .venv/bin/python /tmp/p5-extract.py NAME [DEST]      # DEST defaults to NAME (a repo path)
A block is the fenced code block right after a line `<!-- file: NAME sha256=HEX -->`; its text plus a final
newline is the file. Run from the repository root.
"""
import hashlib
import pathlib
import re
import sys

PLAN = pathlib.Path("specs/doris-mcp-quick/plans/P5-skills.md")
BLOCK = re.compile(r"^<!-- file: (\S+) sha256=([0-9a-f]{64}) -->\n(`{3,})[^\n]*\n(.*?)\n\3$", re.M | re.S)


def main(argv: list[str]) -> int:
    found = {m.group(1): (m.group(2), m.group(4) + "\n") for m in BLOCK.finditer(PLAN.read_text(encoding="utf-8"))}
    bad = {name for name, (sha, body) in found.items() if hashlib.sha256(body.encode("utf-8")).hexdigest() != sha}
    if argv == ["--check"]:
        for name, (_, body) in found.items():
            print(f"{'BAD' if name in bad else 'ok '}  {name} ({len(body.splitlines())} lines)")
        print(f"{len(found)} blocks, {len(bad)} bad")
        return 1 if bad or not found else 0
    name, dest = argv[0], pathlib.Path(argv[1] if len(argv) > 1 else argv[0])
    if name not in found or name in bad:
        print(f"FAIL: {name}: {'no such block' if name not in found else 'sha256 mismatch'}")
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(found[name][1], encoding="utf-8")
    print(f"{name} -> {dest} ({len(found[name][1].splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
EOF
cat > /tmp/p5-progress.py <<'EOF'
"""Edit specs/doris-mcp-quick/progress.md without printing it: older log entries hold private IPs.

  .venv/bin/python /tmp/p5-progress.py state KEY < TEXT   # the line "- **KEY**：…" of 当前状态 becomes "- **KEY**：TEXT"
  .venv/bin/python /tmp/p5-progress.py sub KEY OLD NEW    # in that line, OLD (exactly once) becomes NEW
  .venv/bin/python /tmp/p5-progress.py log < TEXT         # appends TEXT, a "### …" entry, at the end of 日志
Prints what changed (the key, or the entry's heading) and the new line count; nothing of the old text.
Run from the repository root.
"""
import pathlib
import sys

PROGRESS = pathlib.Path("specs/doris-mcp-quick/progress.md")


def state_line(text: str, key: str):
    """(lines of 当前状态, index of the KEY line, rest of the file), or None unless exactly one line matches."""
    state, sep, log = text.partition("\n## 日志\n")
    lines = state.split("\n")
    hits = [i for i, line in enumerate(lines) if line.startswith(f"- **{key}**：")]
    return (lines, hits[0], sep + log) if sep and len(hits) == 1 else None


def main(argv: list[str]) -> int:
    text = PROGRESS.read_text(encoding="utf-8")
    if len(argv) == 2 and argv[0] == "state":
        new, found = sys.stdin.read().strip("\n"), state_line(text, argv[1])
        if not found or not new or "\n" in new:
            print(f"FAIL: want exactly 1 line of 当前状态 starting with - **{argv[1]}**：, and TEXT one line")
            return 1
        lines, i, rest = found
        lines[i] = f"- **{argv[1]}**：{new}"
        text, what = "\n".join(lines) + rest, argv[1]
    elif len(argv) == 4 and argv[0] == "sub":
        found = state_line(text, argv[1])
        if not found or found[0][found[1]].count(argv[2]) != 1:
            print(f"FAIL: want exactly 1 line of 当前状态 starting with - **{argv[1]}**：, holding OLD exactly once")
            return 1
        lines, i, rest = found
        lines[i] = lines[i].replace(argv[2], argv[3])
        text, what = "\n".join(lines) + rest, f"{argv[1]} ({argv[2]} -> {argv[3]})"
    elif argv == ["log"]:
        new = sys.stdin.read().strip("\n")
        if not new.startswith("### "):
            print("FAIL: a log entry starts with '### '")
            return 1
        text, what = text.rstrip("\n") + "\n\n" + new + "\n", new.split("\n", 1)[0]
    else:
        print(__doc__)
        return 2
    PROGRESS.write_text(text, encoding="utf-8")
    print(f"{what}: written ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
EOF
.venv/bin/python /tmp/p5-extract.py --check; echo "exit=$?"
for f in p5-mut.py p5-mutations.json p5-rows.py p5-idmask.py p5-codezip-check.sh p5-steps.py; do .venv/bin/python /tmp/p5-extract.py "$f" "/tmp/$f"; done
```
期望（实测）：
```
ok   p5-mut.py (75 lines)
ok   p5-mutations.json (2818 lines)
ok   scripts/test/test_build_skills.py (390 lines)
ok   quick/test/test_skills.py (145 lines)
ok   t51-tests.diff (29 lines)
ok   t51-impl.diff (16 lines)
ok   scripts/build_skills.py (375 lines)
ok   quick/test/test_adapter_skill.py (220 lines)
ok   t52-tests.diff (107 lines)
ok   quick/skills/doris-mcp-adapter/SKILL.md (124 lines)
ok   t52-impl.diff (47 lines)
ok   mcp-server/test/test_agentcore_audit_errors.py (219 lines)
ok   mcp-server/test/test_agentcore_time_constraints.py (239 lines)
ok   doris/test/test_semantic_time.py (82 lines)
ok   t57a-impl.diff (247 lines)
ok   t57b-tests.diff (327 lines)
ok   t57b-impl.diff (193 lines)
ok   infra/test/test-30-gateway.sh (144 lines)
ok   infra/test/test-99-cleanup.sh (444 lines)
ok   scripts/test/test-demo-check.sh (265 lines)
ok   t55-tests.diff (109 lines)
ok   t5x-impl.diff (107 lines)
ok   infra/99-cleanup.sh (229 lines)
ok   scripts/demo-check.sh (169 lines)
ok   p5-idmask.py (28 lines)
ok   p5-codezip-check.sh (36 lines)
ok   t56-impl.diff (32 lines)
ok   p5-rows.py (25 lines)
ok   quick/test/test_p5_docs.py (144 lines)
ok   quick/P5-guide.md (228 lines)
ok   quick/P5-handoff.md (76 lines)
ok   quick/runbook.md (97 lines)
ok   p5-steps.py (58 lines)
33 blocks, 0 bad
exit=0
p5-mut.py -> /tmp/p5-mut.py (75 lines)
p5-mutations.json -> /tmp/p5-mutations.json (2818 lines)
p5-rows.py -> /tmp/p5-rows.py (25 lines)
p5-idmask.py -> /tmp/p5-idmask.py (28 lines)
p5-codezip-check.sh -> /tmp/p5-codezip-check.sh (36 lines)
p5-steps.py -> /tmp/p5-steps.py (58 lines)
```

突变工具：`.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json GROUP` 对组里的每个突变改一次文件、跑它的测试、再恢复文件。组名和测试：

| 组 | 个数 | 改的文件 | 测试 | 任务 |
|---|---|---|---|---|
| `sk` | 34 | `scripts/build_skills.py` 29、`scripts/check-secrets.sh` 5 | `test_build_skills.py`、`test-check-secrets.sh` | Task 1 |
| `st` | 11 | 生成的副本和 `UPSTREAM.md` | `quick/test/test_skills.py` | Task 1 |
| `ad` | 14 | adapter `SKILL.md` | `quick/test/test_adapter_skill.py` | Task 2 |
| `ai` | 7 | `quick/agent-instructions.md` 5、`doris/reconcile.py` 2 | `quick/test/test_agent_instructions.py` | Task 2 |
| `p10` | 21 | `mcp-server/src/server.py` 19、`mcp-server/src/core/audit.py` 2 | `test_agentcore_*.py` | Task 3 |
| `p11` | 20 | `mcp-server/src/store/compiler.py` | `test_agentcore_time_constraints.py`、`test_semantic_time.py` | Task 3 |
| `af` | 13 | `scripts/audit_check.py` | `test_audit_check.py` | Task 4 |
| `m8` | 6 | `scripts/mcp_smoke.py` | `test_mcp_smoke.py` | Task 4 |
| `m9` | 16 | `scripts/gw_latency.py` | `test_gw_latency.py` | Task 4 |
| `gw` | 11 | `infra/30-gateway.sh` | `test-30-gateway.sh` | Task 5 |
| `cl` | 22 | `infra/99-cleanup.sh` | `test-99-cleanup.sh` | Task 5 |
| `dc` | 21 | `scripts/demo-check.sh` | `test-demo-check.sh` | Task 5 |
| `cs` | 9 | `scripts/check-secrets.sh` | `test-check-secrets.sh` | Task 5 |
| `docs` | 15 | `quick/P5-guide.md` 10、`quick/runbook.md` 4、`quick/P5-handoff.md` 1 | `quick/test/test_p5_docs.py` | Task 7 |

每个突变的 `old` 在文件里必须恰好出现 1 次；突变以子进程运行，带 `PYTHONDONTWRITEBYTECODE=1`（同一秒内写出、大小相同的突变体，否则可能跑到上一个突变体的缓存字节码）。shell 测试按 `FAIL NAME:` 行找出被抓到的检查。

<!-- file: p5-mut.py sha256=9806894ad1617c477c2ef59c39c829083941fbb06e617f308a12fbf03ab819a1 -->
```python
"""Mutation checks for plans/P5-skills.md: each mutation changes one file once, runs its tests, restores the file.

  .venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json GROUP
`tests` is either unittest arguments (run as `python -m unittest ...`) or a command starting with `bash`
(the offline shell tests, which print `FAIL NAME: ...` lines and end with `all passed` or `N failed`).
One line per mutation: `NAME: caught by TEST[, TEST] (SUMMARY)`, `NAME: NOT CAUGHT (SUMMARY)` or
`NAME: pattern not found once`; then `C/N mutations caught` and whether the tree is back byte for byte.
Exit code 0 only when every mutation of the group was caught and the tree is unchanged. Run from the repo root.
Children run with PYTHONDONTWRITEBYTECODE=1: a mutant written in the same second with the same size as the
previous one would otherwise be run from the previous mutant's cached bytecode.
"""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys


CHILD_ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def tree_state(files: set[str]) -> str:
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout
    diff = subprocess.run(["git", "diff"], capture_output=True, check=True).stdout
    return status + hashlib.sha256(diff).hexdigest() + "".join(
        hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() for f in sorted(files))


def run_tests(tests: list[str]) -> tuple[int, str, list[str]]:
    """Return (exit code, summary, names of the failed tests)."""
    if tests[0] == "bash":
        run = subprocess.run(tests, capture_output=True, text=True, env=CHILD_ENV)
        out = (run.stdout + run.stderr).strip().splitlines()
        failed = sorted(set(re.findall(r"^FAIL (.+?):", "\n".join(out), re.M)))
        return run.returncode, out[-1] if out else "?", failed
    run = subprocess.run([sys.executable, "-m", "unittest", *tests], capture_output=True, text=True, env=CHILD_ENV)
    ran = re.search(r"^Ran (\d+) tests?", run.stderr, re.M)
    result = re.search(r"^(FAILED \(.*\)|OK)", run.stderr, re.M)
    summary = f"Ran {ran.group(1) if ran else '?'}, {result.group(1) if result else '?'}"
    return run.returncode, summary, sorted(set(re.findall(r"^(?:FAIL|ERROR): (\w+)", run.stderr, re.M)))


def main(spec: str, group: str) -> int:
    mutations = [m for m in json.loads(pathlib.Path(spec).read_text(encoding="utf-8")) if m["group"] == group]
    if not mutations:
        sys.exit(f"no mutations in group {group}")
    files = {m["file"] for m in mutations}
    before = tree_state(files)
    caught = 0
    for m in mutations:
        path = pathlib.Path(m["file"])
        original = path.read_bytes()
        text = original.decode("utf-8")
        if text.count(m["old"]) != 1:
            print(f"{m['name']}: pattern not found once")
            continue
        try:
            path.write_text(text.replace(m["old"], m["new"]), encoding="utf-8")
            rc, summary, failed = run_tests(m["tests"])
        finally:
            path.write_bytes(original)
        if rc != 0:
            caught += 1
            print(f"{m['name']}: caught by {', '.join(failed) or '?'} ({summary})")
        else:
            print(f"{m['name']}: NOT CAUGHT ({summary})")
    unchanged = tree_state(files) == before
    print(f"{caught}/{len(mutations)} mutations caught; tree unchanged: {unchanged}")
    return 0 if caught == len(mutations) and unchanged else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
```

<!-- file: p5-mutations.json sha256=3c8f0208c3bf3a487c76f03c953dfb1d1bbc506b2b91ece134fb17603bdf7b73 -->
````json
[
 {
  "group": "sk",
  "name": "sk1 hint only in the top-level SKILL.md, nested ones copied unchanged",
  "file": "scripts/build_skills.py",
  "old": "    body = body.lstrip(\"\\n\")\n",
  "new": "    if rel != f\"{skill}/SKILL.md\":\n        return text, lengths\n    body = body.lstrip(\"\\n\")\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk2 hint appended at the end of the file",
  "file": "scripts/build_skills.py",
  "old": "    return f\"---\\n{frontmatter}---\\n{HINT}\\n\\n{body}\", lengths\n",
  "new": "    return f\"---\\n{frontmatter}---\\n{body}\\n{HINT}\\n\", lengths\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk3 hint before the frontmatter",
  "file": "scripts/build_skills.py",
  "old": "    return f\"---\\n{frontmatter}---\\n{HINT}\\n\\n{body}\", lengths\n",
  "new": "    return f\"{HINT}\\n\\n---\\n{frontmatter}---\\n{body}\", lengths\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk4 no blank line after the hint",
  "file": "scripts/build_skills.py",
  "old": "    return f\"---\\n{frontmatter}---\\n{HINT}\\n\\n{body}\", lengths\n",
  "new": "    return f\"---\\n{frontmatter}---\\n{HINT}\\n{body}\", lengths\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk5 the body's leading blank lines kept",
  "file": "scripts/build_skills.py",
  "old": "    body = body.lstrip(\"\\n\")\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk6 override not applied (upstream description kept)",
  "file": "scripts/build_skills.py",
  "old": "    if rel == f\"{skill}/SKILL.md\" and skill in DESCRIPTION_OVERRIDES:",
  "new": "    if False and rel == f\"{skill}/SKILL.md\" and skill in DESCRIPTION_OVERRIDES:",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk7 override rewrite computed but discarded",
  "file": "scripts/build_skills.py",
  "old": "        frontmatter = _override_description(frontmatter, override, rel)\n",
  "new": "        _override_description(frontmatter, override, rel)\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk8 description length check removed",
  "file": "scripts/build_skills.py",
  "old": "    if length > DESCRIPTION_LIMIT:",
  "new": "    if False and length > DESCRIPTION_LIMIT:",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk9 stale-override check removed (override kept after upstream shortened)",
  "file": "scripts/build_skills.py",
  "old": "        if before <= DESCRIPTION_LIMIT:",
  "new": "        if False:",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk10 read-back check of the override removed",
  "file": "scripts/build_skills.py",
  "old": "if _meta(frontmatter, rel)[\"description\"].split() != override.split():",
  "new": "if False:",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk11 commit check skipped",
  "file": "scripts/build_skills.py",
  "old": "    _check_commit(source, commit)\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk12 excluded skill copied",
  "file": "scripts/build_skills.py",
  "old": "(p.startswith(\"skills/\") and p.split(\"/\")[1] in SKILLS)",
  "new": "p.startswith(\"skills/\")",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk13 upstream entries not accounted for (new NOTICE / skill ignored)",
  "file": "scripts/build_skills.py",
  "old": "    if problems:\n        raise BuildError(\"; \".join(problems))\n    return {p:",
  "new": "    return {p:",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk14 root SKILL.md check removed",
  "file": "scripts/build_skills.py",
  "old": "        if f\"{skill}/SKILL.md\" not in files:\n",
  "new": "        if False:\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk15 link fix only checks the text is present, not the count",
  "file": "scripts/build_skills.py",
  "old": "        if found != count:",
  "new": "        if found == 0:",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk16 unlisted broken link ignored",
  "file": "scripts/build_skills.py",
  "old": "for rel, target in sorted(broken - allowed)]",
  "new": "for rel, target in sorted(broken - allowed) if False]",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk17 stale allow-list entry not detected",
  "file": "scripts/build_skills.py",
  "old": "for rel, target in sorted(allowed - broken)]",
  "new": "for rel, target in sorted(allowed - broken) if False]",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk18 links checked in SKILL.md files only",
  "file": "scripts/build_skills.py",
  "old": "if not (rel.endswith(\".md\") and is_copy(rel)):",
  "new": "if not (rel.endswith(\"SKILL.md\") and is_copy(rel)):",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk19 #anchor not stripped from the target",
  "file": "scripts/build_skills.py",
  "old": "target.split(\"#\", 1)[0]",
  "new": "target",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk20 a link to a folder counts as broken",
  "file": "scripts/build_skills.py",
  "old": "if path not in files and path not in folders:",
  "new": "if path not in files:",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk21 build wipes the output folder (the adapter goes too)",
  "file": "scripts/build_skills.py",
  "old": "    files = render(source, commit)\n    for skill in SKILLS:\n",
  "new": "    files = render(source, commit)\n    __import__(\"shutil\").rmtree(out, ignore_errors=True)\n    for skill in SKILLS:\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk22 build prunes stale files in the whole output folder",
  "file": "scripts/build_skills.py",
  "old": "sorted((out / skill).rglob(\"*\"), reverse=True)",
  "new": "sorted(out.rglob(\"*\"), reverse=True)",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk23 build leaves stale files",
  "file": "scripts/build_skills.py",
  "old": "            elif path.relative_to(out).as_posix() not in files:",
  "new": "            elif False:",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk24 --check ignores differs",
  "file": "scripts/build_skills.py",
  "old": "    found += [(p, \"differs\") for p in present & set(files) if (out / p).read_bytes() != files[p]]\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk25 --check reports the adapter and other files as extra",
  "file": "scripts/build_skills.py",
  "old": "    present = {p for p in present if is_copy(p) or p == UPSTREAM_MD}\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk26 the override wrapped at hyphens",
  "file": "scripts/build_skills.py",
  "old": "break_on_hyphens=False",
  "new": "break_on_hyphens=True",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk27 files read from the clone's working tree",
  "file": "scripts/build_skills.py",
  "old": "    content = _read(source, commit, sorted(selected))\n",
  "new": "    content = {p: (source / p).read_bytes() for p in selected}\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk28 UPSTREAM.md NOTICE sentence inverted",
  "file": "scripts/build_skills.py",
  "old": "(\"\" if notice else \" Upstream has no NOTICE file at this commit.\")",
  "new": "(\" Upstream has no NOTICE file at this commit.\" if notice else \"\")",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk29 a build error exits 1 like a --check difference",
  "file": "scripts/build_skills.py",
  "old": "        return 2\n",
  "new": "        return 1\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_build_skills.py"
  ]
 },
 {
  "group": "sk",
  "name": "sk30 check-secrets: aws_secret_access_key no longer checked (a real value passes)",
  "file": "scripts/check-secrets.sh",
  "old": "aws_secret_access_key[[:space:]]*=[[:space:]]*[\"'\"'\"']?[^[:space:]<$.\"'\"'\"']|",
  "new": "",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "sk",
  "name": "sk31 check-secrets: only a quoted aws_secret_access_key value is checked",
  "file": "scripts/check-secrets.sh",
  "old": "aws_secret_access_key[[:space:]]*=[[:space:]]*[\"'\"'\"']?[^[:space:]<$.\"'\"'\"']|",
  "new": "aws_secret_access_key[[:space:]]*=[[:space:]]*[\"'\"'\"'][^[:space:]<$.\"'\"'\"']|",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "sk",
  "name": "sk32 check-secrets: spaces after = exempt the value",
  "file": "scripts/check-secrets.sh",
  "old": "aws_secret_access_key[[:space:]]*=[[:space:]]*[\"'\"'\"']?[^[:space:]<$.\"'\"'\"']|",
  "new": "aws_secret_access_key[[:space:]]*=[\"'\"'\"']?[^[:space:]<$.\"'\"'\"']|",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "sk",
  "name": "sk33 check-secrets: back to the old pattern (placeholders flagged)",
  "file": "scripts/check-secrets.sh",
  "old": "aws_secret_access_key[[:space:]]*=[[:space:]]*[\"'\"'\"']?[^[:space:]<$.\"'\"'\"']|",
  "new": "aws_secret_access_key[[:space:]]*=|",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "sk",
  "name": "sk34 check-secrets: the LEAK line prints the matching line",
  "file": "scripts/check-secrets.sh",
  "old": "    echo \"LEAK: secret-like pattern in $f\"\n",
  "new": "    echo \"LEAK: secret-like pattern in $f: $(grep -IE -- \"$patterns\" \"$f\")\"\n",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "st",
  "name": "st1 a nested SKILL.md without the hint",
  "file": "quick/skills/doris-debug/query/SKILL.md",
  "old": "> **Environment:** Amazon Quick with the Doris MCP tools (`doris___*`), not `doriscli`. Load the `doris-mcp-adapter` skill and map every command below through it.\n\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "st",
  "name": "st2 no blank line after the hint",
  "file": "quick/skills/doris-profile-reader/SKILL.md",
  "old": "> **Environment:** Amazon Quick with the Doris MCP tools (`doris___*`), not `doriscli`. Load the `doris-mcp-adapter` skill and map every command below through it.\n\n",
  "new": "> **Environment:** Amazon Quick with the Doris MCP tools (`doris___*`), not `doriscli`. Load the `doris-mcp-adapter` skill and map every command below through it.\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "st",
  "name": "st3 the hint twice",
  "file": "quick/skills/doris-best-practices/SKILL.md",
  "old": "> **Environment:** Amazon Quick with the Doris MCP tools (`doris___*`), not `doriscli`. Load the `doris-mcp-adapter` skill and map every command below through it.\n\n",
  "new": "> **Environment:** Amazon Quick with the Doris MCP tools (`doris___*`), not `doriscli`. Load the `doris-mcp-adapter` skill and map every command below through it.\n\n> **Environment:** Amazon Quick with the Doris MCP tools (`doris___*`), not `doriscli`. Load the `doris-mcp-adapter` skill and map every command below through it.\n\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "st",
  "name": "st4 top-level name differs from the folder",
  "file": "quick/skills/doris-debug/SKILL.md",
  "old": "name: doris-debug\n",
  "new": "name: doris-debugger\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "st",
  "name": "st5 description over 1024 characters",
  "file": "quick/skills/doris-architecture-advisor/SKILL.md",
  "old": "  multi-engine platforms, even when Doris is not named.\n---\n",
  "new": "  multi-engine platforms, even when Doris is not named. More text. More text. More text. More text. More text. More text. \n---\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "st",
  "name": "st6 UPSTREAM.md built from another commit",
  "file": "quick/skills/UPSTREAM.md",
  "old": "- Commit: `0476f3b84adeee4df75bc7ed694980306f8c6ab8` (committed 2026-09-14)\n\n## Rebuild and check\n\n    git clone https://github.com/apache/doris-skills /tmp/doris-skills && git -C /tmp/doris-skills checkout 0476f3b84adeee4df75bc7ed694980306f8c6ab8",
  "new": "- Commit: `1111111111111111111111111111111111111111` (committed 2026-09-14)\n\n## Rebuild and check\n\n    git clone https://github.com/apache/doris-skills /tmp/doris-skills && git -C /tmp/doris-skills checkout 1111111111111111111111111111111111111111",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "st",
  "name": "st7 an override trigger dropped (Pre-Flight Checklist)",
  "file": "quick/skills/doris-best-practices/SKILL.md",
  "old": "doris-architecture-advisor skill produces DDL — apply the Pre-Flight Checklist to\n",
  "new": "doris-architecture-advisor skill produces DDL — apply the checklist to\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "st",
  "name": "st8 the committed override drifted from the builder's",
  "file": "quick/skills/doris-architecture-advisor/SKILL.md",
  "old": "Workload-aware architecture design for Apache Doris. MUST USE when designing data",
  "new": "Workload-aware architecture design for Apache Doris. MUST USE when designing a data",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "st",
  "name": "st9 a new broken link",
  "file": "quick/skills/doris-debug/SKILL.md",
  "old": "# Doris Debug Router\n",
  "new": "# Doris Debug Router\n\nSee [the case index](shared/references/03-case-index.md).\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "st",
  "name": "st10 an allowed broken link that resolves now (allow-list stale)",
  "file": "quick/skills/doris-architecture-advisor/SKILL.md",
  "old": "(doris-best-practices/references/schema-props-compression.md)",
  "new": "(../doris-best-practices/references/schema-props-compression.md)",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "st",
  "name": "st11 frontmatter that is not valid YAML",
  "file": "quick/skills/doris-profile-reader/SKILL.md",
  "old": "name: doris-profile-reader\n",
  "new": "name: [doris-profile-reader\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_skills.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad1 no row for profile list --active",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "| `doriscli profile list --active` | `doris___execute_query(sql=\"SHOW PROCESSLIST\")` |\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad2 no row for --no-cache",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "| `doriscli sql ... --no-cache` | add the hint `/*+SET_VAR(enable_sql_cache=false)*/` |\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad3 max_chars outside the server's range",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "`max_chars=60000`",
  "new": "`max_chars=300000`",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad4 a tool name that is not behind the Gateway",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "| FE HTTP `/rest/v2/manager/query/query_info` | `doris___list_recent_queries` |",
  "new": "| FE HTTP `/rest/v2/manager/query/query_info` | `doris___list_queries` |",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad5 SET statements not said to be rejected",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": " (`SET` statements are rejected)",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad6 description without read-only",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "and states the\n  read-only boundary,",
  "new": "and states the\n  boundary,",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad7 KILL not in the writes list",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "`TRUNCATE`, `KILL`, `ADMIN",
  "new": "`TRUNCATE`, `ADMIN",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad8 no retry-once rule at 424",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "narrow it and retry once;",
  "new": "narrow it;",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad9 a bare tool name without the prefix",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "- A \"fallback\", \"mysql client\" or \"native SQL\" path in a skill means `doris___execute_query` here.",
  "new": "- A \"fallback\", \"mysql client\" or \"native SQL\" path in a skill means `execute_query` here.",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad10 no word on a missing profile",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "`profile_found: false` means",
  "new": "An empty result means",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad11 name differs from the folder",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "name: doris-mcp-adapter\n",
  "new": "name: doris-adapter\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad12 doriscli tablet maps to SHOW CREATE TABLE only",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": " + `SHOW PARTITIONS FROM db.t` + `SHOW DATA SKEW FROM db.t` + `SHOW TABLE STATS db.t` / `SHOW COLUMN STATS db.t` |",
  "new": " |",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad13 the evidence section drops the connection-details rule",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "Do not repeat host names, IP addresses, ports,\naccounts or URLs that appear in tool results.",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ad",
  "name": "ad14 no tablet row, only the --detail row",
  "file": "quick/skills/doris-mcp-adapter/SKILL.md",
  "old": "| `doriscli tablet <db.t>` | `SHOW CREATE TABLE db.t`",
  "new": "| `tablets of <db.t>` | `SHOW CREATE TABLE db.t`",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_adapter_skill.py"
  ]
 },
 {
  "group": "ai",
  "name": "ai1 quarter grain not named",
  "file": "quick/agent-instructions.md",
  "old": "`metric_time__quarter`、",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_agent_instructions.py"
  ]
 },
 {
  "group": "ai",
  "name": "ai2 the skills are used without the adapter",
  "file": "quick/agent-instructions.md",
  "old": "用之前先加载 doris-mcp-adapter，按它把命令换成 `doris___*` 工具；",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_agent_instructions.py"
  ]
 },
 {
  "group": "ai",
  "name": "ai3 same-days comparison grouped by month",
  "file": "quick/agent-instructions.md",
  "old": "按天分组（group_by `metric_time__day`）",
  "new": "按月分组（group_by `metric_time__month`）",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_agent_instructions.py"
  ]
 },
 {
  "group": "ai",
  "name": "ai4 no one-range-per-call rule",
  "file": "quick/agent-instructions.md",
  "old": "一次调用只写一个时间范围，",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_agent_instructions.py"
  ]
 },
 {
  "group": "ai",
  "name": "ai5 reconcile case grouped by month",
  "file": "doris/reconcile.py",
  "old": "Case(\"yoy_same_days_2026_09\", (\"gmv\", \"gmv_last_year\"), (\"metric_time__day\",),",
  "new": "Case(\"yoy_same_days_2026_09\", (\"gmv\", \"gmv_last_year\"), (\"metric_time__month\",),",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_agent_instructions.py"
  ]
 },
 {
  "group": "ai",
  "name": "ai6 a skill name that is not in quick/skills",
  "file": "quick/agent-instructions.md",
  "old": "按 doris-debug、doris-profile-reader",
  "new": "按 doris-diagnose、doris-profile-reader",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_agent_instructions.py"
  ]
 },
 {
  "group": "ai",
  "name": "ai7 no reconcile case for the same days",
  "file": "doris/reconcile.py",
  "old": "Case(\"yoy_same_days_2026_09\",",
  "new": "Case(\"yoy_days_2026_09\",",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_agent_instructions.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs1 guide question 3 reworded",
  "file": "quick/P5-guide.md",
  "old": "### 步骤 3（第 3 幕 大促复盘）：`618 和双 11 哪个类目贡献最大？`",
  "new": "### 步骤 3（第 3 幕 大促复盘）：`618 和双 11 哪个类目贡献最大`",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs2 runbook question 6 reworded",
  "file": "quick/runbook.md",
  "old": "`评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL`",
  "new": "`评审 fact_user_event 的建表`",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs3 guide monthly reference differs from P4",
  "file": "quick/P5-guide.md",
  "old": "| 2026-09 | 5,754,567.17 |",
  "new": "| 2026-09 | 5,754,567.18 |",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs4 guide channel reference differs from P4",
  "file": "quick/P5-guide.md",
  "old": "| APP | 28,956,861.86 |",
  "new": "| APP | 28,956,861.68 |",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs5 adapter not imported first",
  "file": "quick/P5-guide.md",
  "old": "| 1 | `doris-mcp-adapter` |",
  "new": "| 1 | `doris-mcp-adapter-x` |",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs6 a skill folder missing from the import table",
  "file": "quick/P5-guide.md",
  "old": "| 3 | `doris-profile-reader` | 解读 Query Profile |\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs7 reload_semantic_layer Always Allow",
  "file": "quick/P5-guide.md",
  "old": "| `doris___reload_semantic_layer` | Ask Each Time |",
  "new": "| `doris___reload_semantic_layer` | Always Allow |",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs8 execute_query back to Ask Each Time",
  "file": "quick/P5-guide.md",
  "old": "| `doris___execute_query` | Always Allow |",
  "new": "| `doris___execute_query` | Ask Each Time |",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs9 a tool missing from the permission table",
  "file": "quick/P5-guide.md",
  "old": "| `doris___get_query_profile` | Always Allow |\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs10 handoff template diverges",
  "file": "quick/P5-handoff.md",
  "old": "```\n第 __ 轮\n",
  "new": "```\n第 __ 次\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs11 runbook part renamed",
  "file": "quick/runbook.md",
  "old": "## 每步耗时\n",
  "new": "## 耗时\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs12 runbook runs a script that does not exist",
  "file": "quick/runbook.md",
  "old": "bash scripts/demo-check.sh post",
  "new": "bash scripts/demo_check.sh post",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs13 a tool that is not behind the Gateway",
  "file": "quick/P5-guide.md",
  "old": "调用 `doris___check_service_health`（可能再调用 `doris___list_databases`）",
  "new": "调用 `doris___check_service_health`（可能再调用 `doris___net_check`）",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs14 an address in the runbook",
  "file": "quick/runbook.md",
  "old": "（例如 2003 连接错误的原文）",
  "new": "（例如 2003 连接错误里的 192.0.2.10）",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "docs",
  "name": "docs15 a third reply template",
  "file": "quick/P5-guide.md",
  "old": "模板 2（每一轮）：\n",
  "new": "模板 3：\n\n```\nx\n```\n\n模板 2（每一轮）：\n",
  "tests": [
   "discover",
   "-s",
   "quick/test",
   "-p",
   "test_p5_docs.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-1",
  "file": "mcp-server/src/server.py",
  "old": "    Cut to 300 characters; log_tool_call masks it like the params.\n    \"\"\"\n",
  "new": "    Cut to 300 characters; log_tool_call masks it like the params.\n    \"\"\"\n    return None\n",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-2",
  "file": "mcp-server/src/server.py",
  "old": "success=actual_success, error=_audit_error(result), duration_ms=duration",
  "new": "success=actual_success, duration_ms=duration",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-3",
  "file": "mcp-server/src/server.py",
  "old": "success=error is None, error=error,",
  "new": "success='\"success\": true' in result, error=error,",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-4",
  "file": "mcp-server/src/server.py",
  "old": "\"group_by\": group_by, \"where\": where, \"having\": having,",
  "new": "\"group_by\": group_by, \"having\": having,",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-5",
  "file": "mcp-server/src/server.py",
  "old": "return (text or \"unknown error\")[:300]",
  "new": "return text or \"unknown error\"",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-6",
  "file": "mcp-server/src/server.py",
  "old": "success=error is None, error=error, duration_ms=duration",
  "new": "success=error is None, duration_ms=duration",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-7",
  "file": "mcp-server/src/server.py",
  "old": "\"where\": where, \"having\": having,",
  "new": "\"where\": where,",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-8",
  "file": "mcp-server/src/server.py",
  "old": "\"order_by\": order_by, \"limit\": limit},",
  "new": "},",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-9",
  "file": "mcp-server/src/server.py",
  "old": "mf_cmd += f\" --where {_mf_quote(where)}\"",
  "new": "mf_cmd += \"\"",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-10",
  "file": "mcp-server/src/server.py",
  "old": "mf_cmd += f\" --having {_mf_quote(having)}\"",
  "new": "mf_cmd += \"\"",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-11",
  "file": "mcp-server/src/server.py",
  "old": "mf_cmd += f\" --order-by {','.join(order_by)}\"",
  "new": "mf_cmd += \"\"",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-12",
  "file": "mcp-server/src/server.py",
  "old": "        if limit:\n            mf_cmd += f\" --limit {limit}\"",
  "new": "        if True:\n            mf_cmd += f\" --limit {limit}\"",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-13",
  "file": "mcp-server/src/server.py",
  "old": "return '\"' + value.replace('\"', '\\\\\"') + '\"'",
  "new": "return '\"' + value + '\"'",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-14",
  "file": "mcp-server/src/server.py",
  "old": "body.get(\"success\") is not False:",
  "new": "body.get(\"success\") is True:",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-15",
  "file": "mcp-server/src/server.py",
  "old": "if not isinstance(body, dict) or body.get(\"success\")",
  "new": "if body.get(\"success\")",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-16",
  "file": "mcp-server/src/server.py",
  "old": "for part in (error.get(\"code\"), error.get(\"message\")) if part)",
  "new": "for part in (error.get(\"code\"), error.get(\"message\")))",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-17",
  "file": "mcp-server/src/server.py",
  "old": "        error = {\"message\": error}\n",
  "new": "        error = {}\n",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-18",
  "file": "mcp-server/src/server.py",
  "old": "(text or \"unknown error\")",
  "new": "(text)",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-19",
  "file": "mcp-server/src/server.py",
  "old": "mask_sensitive(sql[:200])",
  "new": "mask_sensitive(sql)",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-20",
  "file": "mcp-server/src/core/audit.py",
  "old": "entry[\"error\"] = mask_sensitive(error)",
  "new": "entry[\"error\"] = error",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p10",
  "name": "p10-21",
  "file": "mcp-server/src/core/audit.py",
  "old": "{k: mask_sensitive(str(v)) for k, v in params.items()}",
  "new": "{k: str(v) for k, v in params.items()}",
  "tests": [
   "discover",
   "-s",
   "mcp-server/test",
   "-p",
   "test_agentcore_*.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-1",
  "file": "mcp-server/src/store/compiler.py",
  "old": "            raise ValueError(_METRIC_TIME_OR_ERROR)",
  "new": "            pass",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-2",
  "file": "mcp-server/src/store/compiler.py",
  "old": "or_groups.intersection(_scan(masked[:match.start()])[0])",
  "new": "or_groups.intersection(_scan(masked[:match.start()])[0][-1:])",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-3",
  "file": "mcp-server/src/store/compiler.py",
  "old": "masked = _STRING_LITERAL_RE.sub(lambda m: \" \" * len(m.group(0)), where)",
  "new": "masked = where",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-4",
  "file": "mcp-server/src/store/compiler.py",
  "old": "starts.append(_parse_dt(date1) + step)",
  "new": "starts.append(_parse_dt(date1))",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-5",
  "file": "mcp-server/src/store/compiler.py",
  "old": "ends.append(_parse_dt(date1) - step)",
  "new": "ends.append(_parse_dt(date1))",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-6",
  "file": "mcp-server/src/store/compiler.py",
  "old": "TimeDimension\\(\\s*['\"]metric_time['\"][^)]*\\)",
  "new": "TimeDimension\\([^)]*\\)",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-7",
  "file": "mcp-server/src/store/compiler.py",
  "old": "time_start = max(starts, default=None)\n        time_end = min(ends, default=None)",
  "new": "time_start = starts[-1] if starts else None\n        time_end = ends[-1] if ends else None",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-8",
  "file": "mcp-server/src/store/compiler.py",
  "old": "remaining = re.sub(r\"\\(\\s*\\x01\\s*\\)\", \"\\x01\", remaining)",
  "new": "remaining = remaining",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-9",
  "file": "mcp-server/src/store/compiler.py",
  "old": "while remaining != previous:",
  "new": "for _ in range(1):",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-10",
  "file": "mcp-server/src/store/compiler.py",
  "old": "remaining = re.sub(r\"\\x01\\s*\\bAND\\b\\s*\", \"\", remaining, flags=re.IGNORECASE)",
  "new": "remaining = remaining",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-11",
  "file": "mcp-server/src/store/compiler.py",
  "old": "remaining = re.sub(r\"\\s*\\bAND\\b\\s*\\x01\", \"\", remaining, flags=re.IGNORECASE)",
  "new": "remaining = remaining",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-12",
  "file": "mcp-server/src/store/compiler.py",
  "old": "remaining = remaining.replace(\"\\x01\", \"\")",
  "new": "remaining = remaining",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-13",
  "file": "mcp-server/src/store/compiler.py",
  "old": "step = timedelta(days=1) if len(date1) == 10 else timedelta(seconds=1)",
  "new": "step = timedelta(days=1)",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-14",
  "file": "mcp-server/src/store/compiler.py",
  "old": "if any(or_groups.intersection(_scan(masked[:match.start()])[0]) for match in matches):",
  "new": "if or_groups:",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-15",
  "file": "mcp-server/src/store/compiler.py",
  "old": "                ends.append(_parse_dt(date2))\n",
  "new": "                pass\n",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-16",
  "file": "mcp-server/src/store/compiler.py",
  "old": "TimeDimension\\(\\s*['\"]metric_time",
  "new": "TimeDimension\\(['\"]metric_time",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-17",
  "file": "mcp-server/src/store/compiler.py",
  "old": "['\"]metric_time['\"][^)]*",
  "new": "'metric_time'[^)]*",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-18",
  "file": "mcp-server/src/store/compiler.py",
  "old": "\"the offset metrics (e.g. *_last_year) grouped by metric_time instead.\"",
  "new": "\"separate calls instead.\"",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-19",
  "file": "mcp-server/src/store/compiler.py",
  "old": "            return None, mf_command, str(e)",
  "new": "            raise",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "p11",
  "name": "p11-20",
  "file": "mcp-server/src/store/compiler.py",
  "old": "                kwargs[\"time_constraint_end\"] = time_end",
  "new": "                pass",
  "tests": [
   "mcp-server/test/test_agentcore_time_constraints.py",
   "doris/test/test_semantic_time.py"
  ]
 },
 {
  "group": "af",
  "name": "af1-error-not-masked",
  "file": "scripts/audit_check.py",
  "old": "    return redact.redact(\" \".join(str(value).split()), [])",
  "new": "    return \" \".join(str(value).split())",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af2-error-not-cut",
  "file": "scripts/audit_check.py",
  "old": "_one_line(record[\"error\"])[:ERROR_CHARS]",
  "new": "_one_line(record[\"error\"])",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af3-cut-before-masking",
  "file": "scripts/audit_check.py",
  "old": "_one_line(record[\"error\"])[:ERROR_CHARS]",
  "new": "_one_line(str(record[\"error\"])[:ERROR_CHARS])",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af4-no-not-recorded",
  "file": "scripts/audit_check.py",
  "old": "if record.get(\"error\") else \"(not recorded)\"",
  "new": "if record.get(\"error\") else \"\"",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af5-all-params-printed-sql-leaks",
  "file": "scripts/audit_check.py",
  "old": "for name in FAILURE_PARAMS.get(record[\"tool\"], ())",
  "new": "for name in params",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af6-unsorted",
  "file": "scripts/audit_check.py",
  "old": "failed = sorted((r for r in records if r.get(\"success\") is not True), key=lambda r: str(r.get(\"timestamp\", \"\")))",
  "new": "failed = [r for r in records if r.get(\"success\") is not True]",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af7-client-id-printed",
  "file": "scripts/audit_check.py",
  "old": "lines.append(f\"  {record.get('timestamp')}  {record['tool']}  {error}\")",
  "new": "lines.append(f\"  {record.get('timestamp')}  {record['tool']}  {error}  ({record.get('client_id')})\")",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af8-section-without-the-flag",
  "file": "scripts/audit_check.py",
  "old": "    if args.failures:\n",
  "new": "    if True:\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af9-failures-fail-the-check",
  "file": "scripts/audit_check.py",
  "old": "    return 0 if passed else 1",
  "new": "    return 0 if passed and not (args.failures and failed) else 1",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af10-multi-line-error-kept",
  "file": "scripts/audit_check.py",
  "old": "    return redact.redact(\" \".join(str(value).split()), [])",
  "new": "    return redact.redact(str(value), [])",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af11-filters-not-masked",
  "file": "scripts/audit_check.py",
  "old": "f\"      {name}: {_one_line(params[name])}\"",
  "new": "f\"      {name}: {params[name]}\"",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af12-mf-command-printed",
  "file": "scripts/audit_check.py",
  "old": "lines.append(f\"  {record.get('timestamp')}  {record['tool']}  {error}\")",
  "new": "lines.append(f\"  {record.get('timestamp')}  {record['tool']}  {error}  {record.get('mf_command') or ''}\".rstrip())",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "af",
  "name": "af13-only-success-false-is-a-failure",
  "file": "scripts/audit_check.py",
  "old": "failed = sorted((r for r in records if r.get(\"success\") is not True)",
  "new": "failed = sorted((r for r in records if r.get(\"success\") is False)",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_audit_check.py"
  ]
 },
 {
  "group": "m8",
  "name": "m8-1-host-not-added",
  "file": "scripts/mcp_smoke.py",
  "old": "    return [v for v in (*urls, *hosts, token) if v]",
  "new": "    return [v for v in (*urls, token) if v]",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_mcp_smoke.py"
  ]
 },
 {
  "group": "m8",
  "name": "m8-2-stdio-url-not-extracted",
  "file": "scripts/mcp_smoke.py",
  "old": "    urls = [args.url] if args.url else [w for w in shlex.split(args.stdio or \"\") if \"://\" in w]",
  "new": "    urls = [args.url] if args.url else []",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_mcp_smoke.py"
  ]
 },
 {
  "group": "m8",
  "name": "m8-3-sdk-logs-masked-only-for-url",
  "file": "scripts/mcp_smoke.py",
  "old": "    hidden = hidden_values(args)\n    redact.redact_sdk_logs(hidden)\n",
  "new": "    hidden = hidden_values(args)\n    if args.url:\n        redact.redact_sdk_logs(hidden)\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_mcp_smoke.py"
  ]
 },
 {
  "group": "m8",
  "name": "m8-4-main-keeps-the-old-hidden-list",
  "file": "scripts/mcp_smoke.py",
  "old": "    hidden = hidden_values(args)\n",
  "new": "    hidden = [args.url, os.environ.get(args.bearer_env, \"\") if args.bearer_env else \"\"]\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_mcp_smoke.py"
  ]
 },
 {
  "group": "m8",
  "name": "m8-5-token-not-hidden",
  "file": "scripts/mcp_smoke.py",
  "old": "    token = os.environ.get(args.bearer_env, \"\") if args.bearer_env else \"\"\n",
  "new": "    token = \"\"\n",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_mcp_smoke.py"
  ]
 },
 {
  "group": "m8",
  "name": "m8-6-netloc-instead-of-hostname",
  "file": "scripts/mcp_smoke.py",
  "old": "    hosts = [urlsplit(u).hostname for u in urls]",
  "new": "    hosts = [urlsplit(u).netloc for u in urls]",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_mcp_smoke.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-1-offset-replaced-not-converted",
  "file": "scripts/gw_latency.py",
  "old": "    return moment.astimezone(timezone.utc).strftime(\"%Y-%m-%dT%H:%M\")",
  "new": "    return moment.replace(tzinfo=timezone.utc).strftime(\"%Y-%m-%dT%H:%M\")",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-2-minute-by-slicing-the-string",
  "file": "scripts/gw_latency.py",
  "old": "            stats = rows.setdefault((_minute(at), str(result.get(\"Label\"))), {})",
  "new": "            stats = rows.setdefault((str(at)[:16], str(result.get(\"Label\"))), {})",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-3-overwrite-instead-of-merge",
  "file": "scripts/gw_latency.py",
  "old": "            stats[id_] = MERGE[id_](stats[id_], float(value)) if id_ in stats else float(value)",
  "new": "            stats[id_] = float(value)",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-4-series-averaged-instead-of-added",
  "file": "scripts/gw_latency.py",
  "old": "MERGE = {\"calls\": operator.add, \"sum\": operator.add, \"max\": max}",
  "new": "MERGE = {\"calls\": operator.add, \"sum\": lambda a, b: (a + b) / 2, \"max\": max}",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-4b-avg-is-the-mean-of-series-averages",
  "file": "scripts/gw_latency.py",
  "old": "STATS = ((\"calls\", \"SampleCount\"), (\"sum\", \"Sum\"), (\"max\", \"Maximum\"))\nMERGE = {\"calls\": operator.add, \"sum\": operator.add, \"max\": max}",
  "new": "STATS = ((\"calls\", \"SampleCount\"), (\"sum\", \"Average\"), (\"max\", \"Maximum\"))\nMERGE = {\"calls\": operator.add, \"sum\": lambda a, b: (a + b) / 2, \"max\": max}",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-5-max-as-sum",
  "file": "scripts/gw_latency.py",
  "old": "\"max\": max}",
  "new": "\"max\": operator.add}",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-6-naive-time-taken-as-local",
  "file": "scripts/gw_latency.py",
  "old": "        if moment.tzinfo is None:\n            moment = moment.replace(tzinfo=timezone.utc)\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-7-epoch-read-as-naive-utc",
  "file": "scripts/gw_latency.py",
  "old": "        moment = datetime.fromtimestamp(at, timezone.utc)",
  "new": "        moment = datetime.utcfromtimestamp(at)",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-8-queries-still-ask-for-average",
  "file": "scripts/gw_latency.py",
  "old": "(\"sum\", \"Sum\")",
  "new": "(\"sum\", \"Average\")",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-9-avg-not-divided-by-calls",
  "file": "scripts/gw_latency.py",
  "old": "        stats[\"avg\"] = stats.get(\"sum\", 0) / stats[\"calls\"] if stats.get(\"calls\") else 0",
  "new": "        stats[\"avg\"] = stats.get(\"sum\", 0)",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-10-calls-take-the-max",
  "file": "scripts/gw_latency.py",
  "old": "MERGE = {\"calls\": operator.add,",
  "new": "MERGE = {\"calls\": max,",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-p4-m1-threshold-strict",
  "file": "scripts/gw_latency.py",
  "old": "if stats.get(\"max\", 0) >= threshold]",
  "new": "if stats.get(\"max\", 0) > threshold]",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-p4-m2-other-ids-not-skipped",
  "file": "scripts/gw_latency.py",
  "old": "        if result.get(\"Id\") not in ids:\n            continue\n",
  "new": "",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-p4-m3-arn-match-not-fullmatch",
  "file": "scripts/gw_latency.py",
  "old": "GATEWAY_ARN_RE.fullmatch(",
  "new": "GATEWAY_ARN_RE.match(",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-p4-m4-rows-unsorted",
  "file": "scripts/gw_latency.py",
  "old": "    rows = sorted(parse_rows(doc).items())",
  "new": "    rows = list(parse_rows(doc).items())",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "m9",
  "name": "m9-p4-m5-slow-exits-0",
  "file": "scripts/gw_latency.py",
  "old": "    return 1 if slow else 0",
  "new": "    return 0",
  "tests": [
   "discover",
   "-s",
   "scripts/test",
   "-p",
   "test_gw_latency.py"
  ]
 },
 {
  "group": "gw",
  "name": "gw1 description back to create-only",
  "file": "infra/30-gateway.sh",
  "old": "\"${GW_EXCEPTION_ARGS[@]}\"\n  --description \"Quick desktop -> Doris MCP (Runtime dorismcp)\")\n\nGW_ID=\"$(none_to_empty \"$(aws bedrock-agentcore-control list-gateways \\\n  --query \"items[?name=='$GW_NAME'].gatewayId | [0]\" --output text)\")\"\nif [[ -z \"$GW_ID\" ]]; then\n  GW_ID=\"$(run aws bedrock-agentcore-control create-gateway \"${GW_COMMON[@]}\" --tags \"Project=$PROJECT_TAG\"",
  "new": "\"${GW_EXCEPTION_ARGS[@]}\")\n\nGW_ID=\"$(none_to_empty \"$(aws bedrock-agentcore-control list-gateways \\\n  --query \"items[?name=='$GW_NAME'].gatewayId | [0]\" --output text)\")\"\nif [[ -z \"$GW_ID\" ]]; then\n  GW_ID=\"$(run aws bedrock-agentcore-control create-gateway \"${GW_COMMON[@]}\" --description \"Quick desktop -> Doris MCP (Runtime dorismcp)\" --tags \"Project=$PROJECT_TAG\"",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "gw",
  "name": "gw2 flag always passed (empty knob ignored)",
  "file": "infra/30-gateway.sh",
  "old": "\"\")    GW_EXCEPTION_ARGS=() ;;",
  "new": "\"\")    GW_EXCEPTION_ARGS=(--exception-level DEBUG) ;;",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "gw",
  "name": "gw3 bad value accepted",
  "file": "infra/30-gateway.sh",
  "old": "*)     log \"FATAL: GW_EXCEPTION_LEVEL must be DEBUG or empty, not '$GW_EXCEPTION_LEVEL'\"; exit 1 ;;",
  "new": "*)     GW_EXCEPTION_ARGS=(--exception-level \"$GW_EXCEPTION_LEVEL\") ;;",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "gw",
  "name": "gw4 description twice on create",
  "file": "infra/30-gateway.sh",
  "old": "--tags \"Project=$PROJECT_TAG\"",
  "new": "--description \"Quick desktop -> Doris MCP (Runtime dorismcp)\" --tags \"Project=$PROJECT_TAG\"",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "gw",
  "name": "gw5 DEBUG dropped by default",
  "file": "infra/30-gateway.sh",
  "old": "DEBUG) GW_EXCEPTION_ARGS=(--exception-level DEBUG) ;;",
  "new": "DEBUG) GW_EXCEPTION_ARGS=() ;;",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "gw",
  "name": "gw6 empty knob cannot turn DEBUG off (:- instead of -)",
  "file": "infra/30-gateway.sh",
  "old": "\"${GW_EXCEPTION_LEVEL-DEBUG}\"",
  "new": "\"${GW_EXCEPTION_LEVEL:-DEBUG}\"",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "gw",
  "name": "gw7 empty knob refused",
  "file": "infra/30-gateway.sh",
  "old": "  \"\")    GW_EXCEPTION_ARGS=() ;;\n",
  "new": "",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "gw",
  "name": "gw8 update-gateway outside run (writes in dry-run)",
  "file": "infra/30-gateway.sh",
  "old": "  run aws bedrock-agentcore-control update-gateway",
  "new": "  aws bedrock-agentcore-control update-gateway",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "gw",
  "name": "gw9 case-folded knob (the default DEBUG refused)",
  "file": "infra/30-gateway.sh",
  "old": "case \"$GW_EXCEPTION_LEVEL\" in",
  "new": "case \"${GW_EXCEPTION_LEVEL,,}\" in",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "gw",
  "name": "gw10 state written in dry-run",
  "file": "infra/30-gateway.sh",
  "old": "  state_set GW_ID \"$GW_ID\"",
  "new": "  APPLY=1 state_set GW_ID \"$GW_ID\"",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "gw",
  "name": "gw11 always create-gateway",
  "file": "infra/30-gateway.sh",
  "old": "if [[ -z \"$GW_ID\" ]]; then",
  "new": "if true; then",
  "tests": [
   "bash",
   "infra/test/test-30-gateway.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl1 tag check skipped",
  "file": "infra/99-cleanup.sh",
  "old": "  [[ \"$2\" == \"$PROJECT_TAG\" ]] || fatal \"$1 is not tagged",
  "new": "  true || fatal \"$1 is not tagged",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl2 account check skipped",
  "file": "infra/99-cleanup.sh",
  "old": "--query Account --output text)\" == \"$ACCOUNT_ID\" ]] \\",
  "new": "--query Account --output text)\" ]] \\",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl3 doris-demo-sg rules selected by tag",
  "file": "infra/99-cleanup.sh",
  "old": "SecurityGroupRules[?!IsEgress && ReferencedGroupInfo.GroupId=='$RT_SG'].[SecurityGroupRuleId",
  "new": "SecurityGroupRules[?!IsEgress && Tags[?Key=='Project']].[SecurityGroupRuleId",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl4 all doris-demo-sg ingress rules",
  "file": "infra/99-cleanup.sh",
  "old": "SecurityGroupRules[?!IsEgress && ReferencedGroupInfo.GroupId=='$RT_SG'].[",
  "new": "SecurityGroupRules[?!IsEgress].[",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl5 no ENI wait",
  "file": "infra/99-cleanup.sh",
  "old": "  wait_gone 30 20 \"network",
  "new": "  true 30 20 \"network",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl6 roles before the stack",
  "file": "infra/99-cleanup.sh",
  "old": "if (( DEL_STACK )); then\n  run aws cloudformation delete-stack --stack-name \"$STACK_NAME\"\n  run aws cloudformation wait stack-delete-complete --stack-name \"$STACK_NAME\" \\\n    || fatal \"stack $STACK_NAME did not reach DELETE_COMPLETE (see its events in the CloudFormation console)\"\n  DONE+=(\"stack $STACK_NAME\")\nfi\nif (( ${#VPCES[@]} )); then\n  run aws ec2 delete-vpc-endpoints --vpc-endpoint-ids \"${VPCES[@]}\" >/dev/null\n  wait_gone 30 10 \"VPC endpoints ${VPCES[*]} still exist after 300 s\" vpces_gone\n  DONE+=(\"${#VPCES[@]} VPC endpoints\")\nfi\nif (( DEL_DOMAIN )); then\n  run aws cognito-idp delete-user-pool-domain --domain \"$DOMAIN_PREFIX\" --user-pool-id \"$COGNITO_POOL_ID\"\n  DONE+=(\"Cognito domain\")\nfi\nif (( DEL_POOL )); then\n  run aws cognito-idp delete-user-pool --user-pool-id \"$COGNITO_POOL_ID\"; DONE+=(\"user pool\")\nfi\nfor s in \"${DEL_SECRETS[@]}\"; do\n  run aws secretsmanager delete-secret --secret-id \"$s\" \"${SECRET_ARGS[@]}\" >/dev/null; DONE+=(\"secret $s\")\ndone\nif (( ${#DORIS_RULES[@]} )); then\n  run aws ec2 revoke-security-group-ingress --group-id \"$DORIS_SG\" --security-group-rule-ids \"${DORIS_RULES[@]}\" >/dev/null\n  DONE+=(\"${#DORIS_RULES[@]} $DORIS_SG rules\")\nfi\nif (( ${#SGS[@]} )); then\n  wait_gone 30 20 \"network interfaces still use $RT_SG / $VPCE_SG after about 10 minutes. Runtime ENIs are released asynchronously; re-run later\" enis_gone\n  revoke_refs egress \"$RT_SG\" \"$VPCE_SG\"\n  revoke_refs ingress \"$VPCE_SG\" \"$RT_SG\"\n  for sg in \"${SGS[@]}\"; do run aws ec2 delete-security-group --group-id \"$sg\"; DONE+=(\"SG $sg\"); done\nfi\nfor role in \"${DEL_ROLES[@]}\"; do\n  fetch aws iam list-role-policies --role-name \"$role\" --query PolicyNames --output text\n  read -ra policies <<<\"$OUT\"\n  for p in \"${policies[@]}\"; do run aws iam delete-role-policy --role-name \"$role\" --policy-name \"$p\"; done\n  run aws iam delete-role --role-name \"$role\"; DONE+=(\"role $role\")\ndone\n",
  "new": "for role in \"${DEL_ROLES[@]}\"; do\n  fetch aws iam list-role-policies --role-name \"$role\" --query PolicyNames --output text\n  read -ra policies <<<\"$OUT\"\n  for p in \"${policies[@]}\"; do run aws iam delete-role-policy --role-name \"$role\" --policy-name \"$p\"; done\n  run aws iam delete-role --role-name \"$role\"; DONE+=(\"role $role\")\ndone\nif (( DEL_STACK )); then\n  run aws cloudformation delete-stack --stack-name \"$STACK_NAME\"\n  run aws cloudformation wait stack-delete-complete --stack-name \"$STACK_NAME\" \\\n    || fatal \"stack $STACK_NAME did not reach DELETE_COMPLETE (see its events in the CloudFormation console)\"\n  DONE+=(\"stack $STACK_NAME\")\nfi\nif (( ${#VPCES[@]} )); then\n  run aws ec2 delete-vpc-endpoints --vpc-endpoint-ids \"${VPCES[@]}\" >/dev/null\n  wait_gone 30 10 \"VPC endpoints ${VPCES[*]} still exist after 300 s\" vpces_gone\n  DONE+=(\"${#VPCES[@]} VPC endpoints\")\nfi\nif (( DEL_DOMAIN )); then\n  run aws cognito-idp delete-user-pool-domain --domain \"$DOMAIN_PREFIX\" --user-pool-id \"$COGNITO_POOL_ID\"\n  DONE+=(\"Cognito domain\")\nfi\nif (( DEL_POOL )); then\n  run aws cognito-idp delete-user-pool --user-pool-id \"$COGNITO_POOL_ID\"; DONE+=(\"user pool\")\nfi\nfor s in \"${DEL_SECRETS[@]}\"; do\n  run aws secretsmanager delete-secret --secret-id \"$s\" \"${SECRET_ARGS[@]}\" >/dev/null; DONE+=(\"secret $s\")\ndone\nif (( ${#DORIS_RULES[@]} )); then\n  run aws ec2 revoke-security-group-ingress --group-id \"$DORIS_SG\" --security-group-rule-ids \"${DORIS_RULES[@]}\" >/dev/null\n  DONE+=(\"${#DORIS_RULES[@]} $DORIS_SG rules\")\nfi\nif (( ${#SGS[@]} )); then\n  wait_gone 30 20 \"network interfaces still use $RT_SG / $VPCE_SG after about 10 minutes. Runtime ENIs are released asynchronously; re-run later\" enis_gone\n  revoke_refs egress \"$RT_SG\" \"$VPCE_SG\"\n  revoke_refs ingress \"$VPCE_SG\" \"$RT_SG\"\n  for sg in \"${SGS[@]}\"; do run aws ec2 delete-security-group --group-id \"$sg\"; DONE+=(\"SG $sg\"); done\nfi\n",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl7 SG step before the endpoints",
  "file": "infra/99-cleanup.sh",
  "old": "if (( ${#VPCES[@]} )); then\n  run aws ec2 delete-vpc-endpoints --vpc-endpoint-ids \"${VPCES[@]}\" >/dev/null\n  wait_gone 30 10 \"VPC endpoints ${VPCES[*]} still exist after 300 s\" vpces_gone\n  DONE+=(\"${#VPCES[@]} VPC endpoints\")\nfi\nif (( DEL_DOMAIN )); then\n  run aws cognito-idp delete-user-pool-domain --domain \"$DOMAIN_PREFIX\" --user-pool-id \"$COGNITO_POOL_ID\"\n  DONE+=(\"Cognito domain\")\nfi\nif (( DEL_POOL )); then\n  run aws cognito-idp delete-user-pool --user-pool-id \"$COGNITO_POOL_ID\"; DONE+=(\"user pool\")\nfi\nfor s in \"${DEL_SECRETS[@]}\"; do\n  run aws secretsmanager delete-secret --secret-id \"$s\" \"${SECRET_ARGS[@]}\" >/dev/null; DONE+=(\"secret $s\")\ndone\nif (( ${#DORIS_RULES[@]} )); then\n  run aws ec2 revoke-security-group-ingress --group-id \"$DORIS_SG\" --security-group-rule-ids \"${DORIS_RULES[@]}\" >/dev/null\n  DONE+=(\"${#DORIS_RULES[@]} $DORIS_SG rules\")\nfi\nif (( ${#SGS[@]} )); then\n  wait_gone 30 20 \"network interfaces still use $RT_SG / $VPCE_SG after about 10 minutes. Runtime ENIs are released asynchronously; re-run later\" enis_gone\n  revoke_refs egress \"$RT_SG\" \"$VPCE_SG\"\n  revoke_refs ingress \"$VPCE_SG\" \"$RT_SG\"\n  for sg in \"${SGS[@]}\"; do run aws ec2 delete-security-group --group-id \"$sg\"; DONE+=(\"SG $sg\"); done\nfi\n",
  "new": "if (( ${#SGS[@]} )); then\n  wait_gone 30 20 \"network interfaces still use $RT_SG / $VPCE_SG after about 10 minutes. Runtime ENIs are released asynchronously; re-run later\" enis_gone\n  revoke_refs egress \"$RT_SG\" \"$VPCE_SG\"\n  revoke_refs ingress \"$VPCE_SG\" \"$RT_SG\"\n  for sg in \"${SGS[@]}\"; do run aws ec2 delete-security-group --group-id \"$sg\"; DONE+=(\"SG $sg\"); done\nfi\nif (( ${#VPCES[@]} )); then\n  run aws ec2 delete-vpc-endpoints --vpc-endpoint-ids \"${VPCES[@]}\" >/dev/null\n  wait_gone 30 10 \"VPC endpoints ${VPCES[*]} still exist after 300 s\" vpces_gone\n  DONE+=(\"${#VPCES[@]} VPC endpoints\")\nfi\nif (( DEL_DOMAIN )); then\n  run aws cognito-idp delete-user-pool-domain --domain \"$DOMAIN_PREFIX\" --user-pool-id \"$COGNITO_POOL_ID\"\n  DONE+=(\"Cognito domain\")\nfi\nif (( DEL_POOL )); then\n  run aws cognito-idp delete-user-pool --user-pool-id \"$COGNITO_POOL_ID\"; DONE+=(\"user pool\")\nfi\nfor s in \"${DEL_SECRETS[@]}\"; do\n  run aws secretsmanager delete-secret --secret-id \"$s\" \"${SECRET_ARGS[@]}\" >/dev/null; DONE+=(\"secret $s\")\ndone\nif (( ${#DORIS_RULES[@]} )); then\n  run aws ec2 revoke-security-group-ingress --group-id \"$DORIS_SG\" --security-group-rule-ids \"${DORIS_RULES[@]}\" >/dev/null\n  DONE+=(\"${#DORIS_RULES[@]} $DORIS_SG rules\")\nfi\n",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl8 force-delete by default",
  "file": "infra/99-cleanup.sh",
  "old": "FORCE_DELETE_SECRETS=\"${FORCE_DELETE_SECRETS:-0}\"",
  "new": "FORCE_DELETE_SECRETS=\"${FORCE_DELETE_SECRETS:-1}\"",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl9 full domain instead of the prefix",
  "file": "infra/99-cleanup.sh",
  "old": "DOMAIN_PREFIX=\"${COGNITO_DOMAIN%%.*}\"",
  "new": "DOMAIN_PREFIX=\"$COGNITO_DOMAIN\"",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl10 any probe error taken for already deleted",
  "file": "infra/99-cleanup.sh",
  "old": "  if [[ -n \"$not_found\" ]] && grep -q -- \"$not_found\" \"$ERR_FILE\"; then",
  "new": "  if [[ -n \"$not_found\" ]]; then",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl11 Gateway name check skipped",
  "file": "infra/99-cleanup.sh",
  "old": "  [[ \"$name\" == \"$GW_NAME\" ]] || fatal",
  "new": "  true || fatal",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl12 no wait for the target",
  "file": "infra/99-cleanup.sh",
  "old": "  wait_gone 30 5 \"Gateway target",
  "new": "  true 30 5 \"Gateway target",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl13 domain of another pool deleted",
  "file": "infra/99-cleanup.sh",
  "old": "  *) fatal \"Cognito domain $DOMAIN_PREFIX belongs to another user pool\" ;;",
  "new": "  *) DEL_DOMAIN=1 ;;",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl14 stack tag check skipped",
  "file": "infra/99-cleanup.sh",
  "old": "  [[ \"$OUT\" == dorismcp ]] || fatal",
  "new": "  [[ \"$OUT\" ]] || fatal",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl15 already-scheduled secret deleted again",
  "file": "infra/99-cleanup.sh",
  "old": "  if [[ \"$deleted\" != None ]]; then log",
  "new": "  if false; then log",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl16 SECRET_RECOVERY_DAYS not range-checked",
  "file": "infra/99-cleanup.sh",
  "old": "=~ ^([7-9]|[12][0-9]|30)$ ]]",
  "new": "=~ ^[0-9]+$ ]]",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl17 delete-gateway outside run (writes in dry-run)",
  "file": "infra/99-cleanup.sh",
  "old": "  run aws bedrock-agentcore-control delete-gateway --gateway-identifier \"$GW_ID\"",
  "new": "  aws bedrock-agentcore-control delete-gateway --gateway-identifier \"$GW_ID\"",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl18 waits (and sleeps) in dry-run",
  "file": "infra/99-cleanup.sh",
  "old": "  [[ \"$APPLY\" == \"1\" ]] || return 0\n  for ((i = 1",
  "new": "  for ((i = 1",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl19 state.env edited (GW_ lines dropped)",
  "file": "infra/99-cleanup.sh",
  "old": ">/dev/null; DONE+=(\"Gateway\")",
  "new": ">/dev/null; sed -i '/^GW_/d' \"$STATE_FILE\"; DONE+=(\"Gateway\")",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl20 another Gateway deleted",
  "file": "infra/99-cleanup.sh",
  "old": "delete-gateway --gateway-identifier \"$GW_ID\" >/dev/null",
  "new": "delete-gateway --gateway-identifier gw-other0002 >/dev/null",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl21 SG cross-references not revoked",
  "file": "infra/99-cleanup.sh",
  "old": "  revoke_refs egress \"$RT_SG\" \"$VPCE_SG\"\n  revoke_refs ingress \"$VPCE_SG\" \"$RT_SG\"\n",
  "new": "",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "cl",
  "name": "cl22 inline policies not deleted before the role",
  "file": "infra/99-cleanup.sh",
  "old": "  for p in \"${policies[@]}\"; do run",
  "new": "  for p in; do run",
  "tests": [
   "bash",
   "infra/test/test-99-cleanup.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc1 token in argv",
  "file": "scripts/demo-check.sh",
  "old": "--bearer-env GW_TOKEN --timeout 60 \"$@\"",
  "new": "--bearer-env \"$GW_TOKEN\" --timeout 60 \"$@\"",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc2 GW_TOKEN leaks into reconcile",
  "file": "scripts/demo-check.sh",
  "old": "    unset GW_TOKEN \"${!DORIS_@}\" # whether or not",
  "new": "    unset \"${!DORIS_@}\"; export GW_TOKEN # whether or not",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc3 GW_TOKEN exported from the start",
  "file": "scripts/demo-check.sh",
  "old": "GW_TOKEN=\"\" TMPFILES=()",
  "new": "export GW_TOKEN=\"\"; TMPFILES=()",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc4 DORIS_ROOT_PASSWORD passed to reconcile",
  "file": "scripts/demo-check.sh",
  "old": "password=\"${DORIS_RO_PASSWORD-}\"",
  "new": "password=\"${DORIS_ROOT_PASSWORD-}\"",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc5 subshell unset list forgets DORIS_ROOT_*",
  "file": "scripts/demo-check.sh",
  "old": "    unset GW_TOKEN \"${!DORIS_@}\" # whether or not",
  "new": "    unset GW_TOKEN DORIS_RO_USER DORIS_RO_PASSWORD DORIS_MYSQL_PORT DORIS_HTTP_PORT DORIS_ADMIN_PASSWORD # whether or not",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc6 caller's DORIS_* not dropped",
  "file": "scripts/demo-check.sh",
  "old": "unset GW_TOKEN \"${!DORIS_@}\" # the caller",
  "new": "unset GW_TOKEN # the caller",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc7 no mask",
  "file": "scripts/demo-check.sh",
  "old": "OUT=\"$(\"$@\" 2>&1 | sed -E \"$MASK\"; exit",
  "new": "OUT=\"$(\"$@\" 2>&1 | cat; exit",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc8 exit 0 despite a FAIL",
  "file": "scripts/demo-check.sh",
  "old": "(( PASSED == TOTAL ))",
  "new": "true",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc9 MAX_CONNS off by one (<)",
  "file": "scripts/demo-check.sh",
  "old": "(( n <= MAX_CONNS ))",
  "new": "(( n < MAX_CONNS ))",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc10 window not rounded",
  "file": "scripts/demo-check.sh",
  "old": "(( ($1 / 1000 + 59) / 60 * 60 ))",
  "new": "(( $1 / 1000 / 60 * 60 ))",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc10b since rounded up (the first minute's calls dropped)",
  "file": "scripts/demo-check.sh",
  "old": "from=\"$(minute_floor \"$SINCE\")\"",
  "new": "from=\"$(minute_ceil \"$SINCE\")\"",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc11 token command's stderr not masked",
  "file": "scripts/demo-check.sh",
  "old": "report token \"$rc\" \"$(sed -E \"$MASK\" \"$err\")\"",
  "new": "report token \"$rc\" \"$(cat \"$err\")\"",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc12 credentials loaded globally (set -a)",
  "file": "scripts/demo-check.sh",
  "old": "export AWS_REGION=\"${AWS_REGION:-us-east-1}\" AWS_PAGER=\"\"",
  "new": "set -a; source \"$CREDENTIALS_FILE\"; set +a\nexport AWS_REGION=\"${AWS_REGION:-us-east-1}\" AWS_PAGER=\"\"",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc13 post runs the pre checks",
  "file": "scripts/demo-check.sh",
  "old": "if [[ \"$MODE\" == pre ]]; then",
  "new": "if true; then",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc14 audit_check without --failures",
  "file": "scripts/demo-check.sh",
  "old": "scripts/audit_check.py --failures",
  "new": "scripts/audit_check.py",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc15 seconds accepted for --since/--until",
  "file": "scripts/demo-check.sh",
  "old": "[[ \"$SINCE\" =~ ^[1-9][0-9]{12}$ && \"$UNTIL\" =~ ^[1-9][0-9]{12}$ ]]",
  "new": "[[ \"$SINCE\" =~ ^[0-9]+$ && \"$UNTIL\" =~ ^[0-9]+$ ]]",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc16 since == until accepted",
  "file": "scripts/demo-check.sh",
  "old": "(( SINCE < UNTIL )) || usage",
  "new": "(( SINCE <= UNTIL )) || usage",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc17 mcp_smoke called without a token",
  "file": "scripts/demo-check.sh",
  "old": "[[ -n \"$GW_TOKEN\" ]] || { echo \"skipped",
  "new": "true || { echo \"skipped",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc18 any status taken for READY",
  "file": "scripts/demo-check.sh",
  "old": "[[ \"$status\" == READY ]]",
  "new": "[[ -n \"$status\" ]]",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc19 account not compared",
  "file": "scripts/demo-check.sh",
  "old": "if [[ \"$account\" == \"$ACCOUNT_ID\" ]]; then",
  "new": "if [[ -n \"$account\" ]]; then",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "dc",
  "name": "dc20 filter-log-events window in seconds",
  "file": "scripts/demo-check.sh",
  "old": "--start-time \"$SINCE\" --end-time \"$UNTIL\"",
  "new": "--start-time \"$((SINCE / 1000))\" --end-time \"$((UNTIL / 1000))\"",
  "tests": [
   "bash",
   "scripts/test/test-demo-check.sh"
  ]
 },
 {
  "group": "cs",
  "name": "cs1 any Secrets Manager error counts as scheduled for deletion",
  "file": "scripts/check-secrets.sh",
  "old": "  elif grep -q 'marked for deletion' \"$sm_err\"; then\n",
  "new": "  elif grep -q 'Exception' \"$sm_err\"; then\n",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "cs",
  "name": "cs2 not found is skipped without asking sts for the caller's account",
  "file": "scripts/check-secrets.sh",
  "old": "       [[ \"$(aws sts get-caller-identity --region \"$SM_REGION\" --query Account --output text 2>/dev/null)\" == \"$project_account\" ]]; then\n",
  "new": "       true; then\n",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "cs",
  "name": "cs3 no account in infra/state.env still allows the skip (empty equals empty)",
  "file": "scripts/check-secrets.sh",
  "old": "grep -q '(ResourceNotFoundException)' \"$sm_err\" && [[ -n \"$project_account\" ]] &&\n",
  "new": "grep -q '(ResourceNotFoundException)' \"$sm_err\" &&\n",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "cs",
  "name": "cs4 any error in the project's account is skipped",
  "file": "scripts/check-secrets.sh",
  "old": "grep -q '(ResourceNotFoundException)' \"$sm_err\" && [[ -n \"$project_account\" ]] &&\n",
  "new": "grep -q 'Exception' \"$sm_err\" && [[ -n \"$project_account\" ]] &&\n",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "cs",
  "name": "cs5 sts asked in the caller's default region",
  "file": "scripts/check-secrets.sh",
  "old": "aws sts get-caller-identity --region \"$SM_REGION\" --query Account",
  "new": "aws sts get-caller-identity --query Account",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "cs",
  "name": "cs6 the first skip ends the loop (the other secret is not compared)",
  "file": "scripts/check-secrets.sh",
  "old": "    echo \"SKIP: secret $sid is scheduled for deletion (infra/99-cleanup.sh) — nothing left to compare\"\n    skipped=$((skipped + 1))\n",
  "new": "    echo \"SKIP: secret $sid is scheduled for deletion (infra/99-cleanup.sh) — nothing left to compare\"\n    skipped=$((skipped + 1)); break\n",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "cs",
  "name": "cs7 the OK line does not count the skipped secrets",
  "file": "scripts/check-secrets.sh",
  "old": "  echo \"check-secrets: OK (${#files[@]} files scanned, $skipped deleted secrets skipped)\"\n",
  "new": "  echo \"check-secrets: OK (${#files[@]} files scanned)\"\n",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "cs",
  "name": "cs8 the error file is appended to (an earlier secret's error decides the next one)",
  "file": "scripts/check-secrets.sh",
  "old": "--query SecretString --output text 2>\"$sm_err\" |",
  "new": "--query SecretString --output text 2>>\"$sm_err\" |",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 },
 {
  "group": "cs",
  "name": "cs9 an unreadable secret no longer fails the check",
  "file": "scripts/check-secrets.sh",
  "old": "    echo \"FAIL: cannot read secret $sid — its exact-value check did not run\"\n    fail=1\n",
  "new": "    echo \"FAIL: cannot read secret $sid — its exact-value check did not run\"\n",
  "tests": [
   "bash",
   "scripts/test/test-check-secrets.sh"
  ]
 }
]
````

---

### Task 1：T5.1 skills 副本（`scripts/build_skills.py`）和 `check-secrets.sh` 的占位符

来源：design §9 的步骤 1（锁定 commit）、2（导入哪些文件夹）、4（副本内提示），tasks.md T5.1。spec 阶段读了 upstream `0476f3b` 的全部 177 个文件，发现下表的 5 个问题；构建脚本把每一处处理都写成常量，`UPSTREAM.md` 从同一组常量生成，upstream 以后变了，构建会停下来并说明要改哪个常量。

| # | spec 阶段的发现 | 处理 | 测试 |
|---|---|---|---|
| 1 | `doris-architecture-advisor`（1328 字符）和 `doris-best-practices`（1307）的 description 超过 Quick 的 1024 | `DESCRIPTION_OVERRIDES`：保留全部触发词的缩写版（975、978），按 upstream 的缩进折行，必须能被 YAML 读回；upstream 缩短到 1024 以内后，覆盖算过期 | `TestDescriptions` 7 个；`test_skills` 的 `Descriptions` 2 个（触发词逐个检查）|
| 2 | `doris-debug/SKILL.md` 3 次链接 `shared/references/03-case-index.md`，文件不存在（同一个 upstream commit 加的是 `03-cir-case-index.md`，`shared/references/` 里唯一的 03-* 文件）| `LINK_FIXES`：精确替换，次数不符就失败 | `TestLinks` 的 3 个 |
| 3 | `doris-architecture-advisor/SKILL.md` 另有 4 个解析不到的相对链接：回答模板里的占位路径 `rule-name.md`，以及代码块里示例回答的 3 个路径（相对 skills 根目录写的，文件存在）| `BROKEN_LINKS_ALLOWED`，附理由；其他断链让构建失败，允许的链接能解析了也失败 | `TestLinks` 的 3 个；`test_skills` 的 `Links` |
| 4 | `doris-debug/data-lake/SKILL.md` 的 S3 示例里，secret-key 键名后面是占位符；`check-secrets.sh` 的旧规则只要看到「键名 + `=`」就算泄漏，提交会失败 | 规则改成：`=` 后面（可以有空格、引号）是 `<`、`$`、`.`、空白或引号时不算；真实形状的值仍然命中 | `test-check-secrets.sh` +8（5 种占位符、真实形状、不打印值、不带空格的引号写法）|
| 5 | `doris-profile-reader/scripts/extract_source_profile_inventory.py` 是 100755 | 只复制文件内容，不保留可执行位（Quick 不执行 skill 里的脚本），`UPSTREAM.md` 写明 | `TestHint` 的 `other_files_are_byte_identical` |

**Files:**
- Create: `scripts/build_skills.py`、`scripts/test/test_build_skills.py`（38 个，fixture 是临时目录里的 git 仓库，不联网）、`quick/test/test_skills.py`（9 个，只读已提交的副本；其中 2 个在 adapter 写好之前 skip，Task 2 去掉）
- Generate: `quick/skills/doris-architecture-advisor/`、`doris-best-practices/`、`doris-debug/`、`doris-profile-reader/`、`LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md`（共 119 个文件，566278 字节）
- Modify: `scripts/check-secrets.sh`、`scripts/test/test-check-secrets.sh`（12 → 20 个检查）
- Test: `scripts/test` 75 → 113，`quick/test` 16 → 25（2 个 skip）
- Modify: `specs/doris-mcp-quick/design.md`、`tasks.md`、`progress.md`、`RESUME.md`、本计划（Step 1 提交）

**Interfaces:**
- Consumes：apache/doris-skills 在 `0476f3b84adeee4df75bc7ed694980306f8c6ab8` 的 git 对象（`ls-tree -r -z`、`cat-file --batch`、`log -1 --format=%cs`）；`bcda0f3` 的 `check-secrets.sh` 规则 2（一个 `grep -qIE` 的 ERE）。
- Produces（Task 2、Task 7 和 `quick/test` 使用）：
  - 常量 `build_skills.LOCKED_COMMIT`、`SKILLS`（4 个文件夹名）、`TOP_LEVEL_FILES = ("LICENSE.txt", "CLI-CONTRACT.md")`、`EXCLUDED`、`HINT`、`DESCRIPTION_OVERRIDES`、`LINK_FIXES`、`BROKEN_LINKS_ALLOWED`、`DESCRIPTION_LIMIT = 1024`；
  - `split_frontmatter(text, where) -> (frontmatter, body)`、`broken_links(files: dict[str, bytes]) -> set[(file, target)]`、`is_copy(rel) -> bool`；
  - `render(source, commit=LOCKED_COMMIT) -> dict[str, bytes]`（不写盘）、`build(source, out, commit) -> list[str]`、`compare(files, out) -> list[str]`（`missing` / `extra` / `differs` 行，只看生成的路径，adapter 不算）、`main(argv, out) -> int`（0 / 1 / 2）；
  - `quick/skills/CLI-CONTRACT.md`：Task 2 的 adapter 测试逐条对照它的命令和 flag；
  - `quick/test/test_skills.py` 的 `_skip_until_the_adapter_lands`：Task 2 连同 2 处调用一起删除。

- [ ] **Step 1：前置检查，建分支，取文件，提交计划和 spec 修改**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
git branch --show-current                                   # 期望：main
git status --short                                          # 期望：下面 5 行
AWS_PAGER= aws sts get-caller-identity --region us-east-1 --query Account --output text   # 期望：890717383483
.venv/bin/python --version                                  # 期望：Python 3.12.3
uv --version                                                # 期望：uv 0.x（Task 6 用）
test -r /home/ubuntu/AI-code/Doris-test/credentials.env && echo "credentials: readable"
git log --oneline -1; git rev-parse --short origin/main    # 期望：bcda0f3 …；0b41b98
```
`git status --short` 期望：
```
 M RESUME.md
 M specs/doris-mcp-quick/design.md
 M specs/doris-mcp-quick/progress.md
 M specs/doris-mcp-quick/tasks.md
?? specs/doris-mcp-quick/plans/P5-skills.md
```
有其他改动就停下来，对照 progress 判断属于哪个任务（不要 reset / checkout）。

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
git switch -c p5-skills
```
然后执行上面的「从计划取文件」，期望输出与那里一致（33 个 `ok`、`33 blocks, 0 bad`，6 个辅助工具写到 `/tmp`）。

spec 阶段的临时目录已经不需要了（代码以本计划嵌入的为准）。先看一眼再删：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
git worktree list                     # 期望：主目录 [p5-skills]，以及 /tmp/p5-stage-{infra,quick,scripts,server,skills}（detached，bcda0f3）
for w in /tmp/p5-stage-infra /tmp/p5-stage-quick /tmp/p5-stage-scripts /tmp/p5-stage-server /tmp/p5-stage-skills /tmp/p5-replay; do
  git worktree list | grep -q "^$w " && git worktree remove --force "$w"
done
git worktree prune; git worktree list   # 期望：只剩主目录
ls -d /tmp/p5-work /tmp/p5-research /tmp/p5-plan /tmp/p5-zipcheck /tmp/p5-*probe*.py 2>/dev/null   # spec 阶段的草稿和探针
rm -rf /tmp/p5-work /tmp/p5-research /tmp/p5-plan /tmp/p5-zipcheck /tmp/p5-*probe*.py
```

design 的状态行改成「进行中」，progress 更新「当前状态」。`MODE` 按用户选的执行方式二选一：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - <<'EOF'
import pathlib
p = pathlib.Path("specs/doris-mcp-quick/design.md")
s = p.read_text(encoding="utf-8")
old = "状态：P5 计划已编写（`plans/P5-skills.md`，待用户 review）；"
assert s.count(old) == 1, old
p.write_text(s.replace(old, "状态：P5 进行中（`plans/P5-skills.md`，分支 `p5-skills`）；"), encoding="utf-8")
print("design.md: status line")
EOF
MODE='Native（控制方按 TDD 执行，Task 7 Step 2 由一个 Opus 5.5 reviewer 评审整个分支）'
# MODE='Subagent-driven（每个任务一个 Opus 5.5 implementer + 一个 Opus 5.5 reviewer，Task 7 Step 2 再整体评审）'
O=$(git rev-parse --short origin/main)
printf '**P5 进行中**（`plans/P5-skills.md`，分支 `p5-skills`，执行方式：%s）。P4 已完成（T4.1、T4.3–T4.6），已合并到 `main` 并推送到私有仓库（`origin/main` = `%s`）；P0–P4 的过程见日志' "$MODE" "$O" \
  | .venv/bin/python /tmp/p5-progress.py state 阶段
echo 'Task 1（T5.1）：Step 1 已提交计划和 spec 修改（design v0.8、tasks、RESUME）；从 Step 2 继续' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo 'Task 1 Step 2–6（写失败测试 → 生成副本 → 验证 → 提交），然后 Task 2（T5.2 adapter）、Task 3（T5.7a 代码）、Task 4（T5.7b）、Task 5（demo-check / cleanup 脚本）、Task 6（部署，GATE）、Task 7（整体评审，再交给用户导入 skill 和彩排 2 轮）、Task 8（T5.5）、Task 9（演示结束后清理，GATE）' | .venv/bin/python /tmp/p5-progress.py state 下一步
echo 'P5 的 GATE 有 3 个（Task 6 部署 Runtime；Task 8 改 Gateway，只在决定改时；Task 9 清理），每个单独确认。`mcp_svc` 只经 Runtime 使用，不试探特权或诊断类语句。Runtime 偶发 502 / 冷启动慢：`demo-check pre` 只有一项失败时重跑一次。VPC 里 4 个未挂载的 `launch-wizard-*` SG 由用户决定，P5 不碰。`check-secrets.sh` 要读 Secrets Manager，需要有效的 AWS 凭证' | .venv/bin/python /tmp/p5-progress.py state 注意
echo 'spec 阶段的 `/tmp/p5-stage-*`（worktree）、`/tmp/p5-work`、`/tmp/p5-research`、`/tmp/p5-plan`、探针脚本已在 Task 1 Step 1 删除。**权威版本是 `plans/P5-skills.md` 里嵌入的代码**，用 `/tmp/p5-extract.py` 按 sha256 取出（计划「从计划取文件」）；`/tmp` 丢失后先重跑那一节，要用 `build_skills.py` 时再按 Task 1 Step 4 clone upstream' | .venv/bin/python /tmp/p5-progress.py state 'spec 阶段的临时产物'
```
期望（实测）：
```
design.md: status line
阶段: written (735 lines)
进行中: written (735 lines)
下一步: written (735 lines)
注意: written (735 lines)
spec 阶段的临时产物: written (735 lines)
```

提交（新增行的 IP 计数只输出数字；私网 IP 取自 `agentcore.json` 和 `state.env`，不打印；`$v` 为空时输出 FAIL 而不是静默通过，M-10）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add RESUME.md specs/doris-mcp-quick/design.md specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md \
        specs/doris-mcp-quick/plans/P5-skills.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
docs(p5): P5 plan, design v0.8 (P-10, P-11, cleanup order, skills import), tasks T5.1-T5.7b

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git log --oneline -1 | cut -c9-
```
期望（实测）：
```
check-secrets: OK (717 files scanned)
0
docs(p5): P5 plan, design v0.8 (P-10, P-11, cleanup order, skills import), tasks T5.1-T5.7b
```

- [ ] **Step 2：写失败测试**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py scripts/test/test_build_skills.py
.venv/bin/python /tmp/p5-extract.py quick/test/test_skills.py
.venv/bin/python /tmp/p5-extract.py t51-tests.diff /tmp/t51-tests.diff
git apply /tmp/t51-tests.diff && git status --short && git diff --shortstat
```
期望（实测）：
```
scripts/test/test_build_skills.py -> scripts/test/test_build_skills.py (390 lines)
quick/test/test_skills.py -> quick/test/test_skills.py (145 lines)
t51-tests.diff -> /tmp/t51-tests.diff (29 lines)
 M scripts/test/test-check-secrets.sh
?? quick/test/test_skills.py
?? scripts/test/test_build_skills.py
 1 file changed, 18 insertions(+)
```

`test_build_skills.py` 在临时目录里建一个小的 fixture upstream（git 仓库，2 个 skill、1 个排除项、1 个 `LICENSE.txt`），把构建脚本的常量换成 fixture 的，覆盖：
- `TestHint`（6）：每个 `SKILL.md`（含嵌套的）正文第一行是提示，其余字节不变；正文前的空行合并成提示后的 1 个空行；覆盖了 description 的 `SKILL.md` 也有提示；其他文件逐字节相同；没有 frontmatter 的 `SKILL.md` 失败。
- `TestDescriptions`（7）：只替换 description，折行保持 upstream 的缩进；超长且没有覆盖、覆盖本身超长、嵌套 skill 超长、YAML 读不回、覆盖了本来不超长的 description，都失败。
- `TestSelection`（7）：只复制列出的 skill 和顶层文件；upstream 新增的项、`EXCLUDED` 里已经不存在的项、根目录没有 `SKILL.md` 的 skill 都失败；文件取自 commit 而不是工作区；clone 不在锁定的 commit、不是 git 仓库都失败。
- `TestLinks`（6）：修链接；次数不符、要替换的文本不在了、没列出的断链、已经不断的允许项都失败；哪些链接算断链（http、mailto、`#anchor`、文件夹、兄弟 skill）。
- `TestUpstreamMd`（3）：记下来源、commit、每处改动；每个导入的 skill 的文件数、字节数、版本；渲染两次字节相同。
- `TestBuild`（4）：写出渲染的树并返回路径；只在副本文件夹里删除多余文件，adapter 和其他文件不动；构建两次字节相同；失败的构建不改任何文件。
- `TestMain`（5）：构建只输出一行摘要；`--check` 对新构建通过且忽略 adapter；列出每处不同；输出目录不存在时列出每个文件；commit 不对时 exit 2 并给出修正命令。

`quick/test/test_skills.py` 只读已提交的 `quick/skills/`（不跑构建、不需要 clone），检查 Quick 导入和 agent 依赖的东西：5 个文件夹、每个文件夹根目录有 frontmatter 合法的 `SKILL.md`（name ≤ 64、description ≤ 1024、文件夹 ≤ 6 MB）、每个复制的 `SKILL.md` 第一行是提示、`LICENSE.txt` / `CLI-CONTRACT.md` / `UPSTREAM.md`、缩写的 description 保留的触发词、相对链接能解析（或在允许列表里）。adapter 的两个检查在 Task 2 之前 skip。

新文件 `scripts/test/test_build_skills.py`：

<!-- file: scripts/test/test_build_skills.py sha256=ce1541cda1d88ee57fbcedb310aeaf813297b5a6879cbf55d552db7afc601b81 -->
```python
"""scripts/build_skills.py: quick/skills/ copies of apache/doris-skills with the adapter hint (P5 / T5.1).

Runs against a small fixture upstream built in a temp git repo (no clone, no network); the builder's constants are
patched to the fixture's.

    .venv/bin/python -m unittest discover -s scripts/test -p 'test_build_skills.py' -v
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_skills  # noqa: E402

HINT = build_skills.HINT


def _folded(text: str) -> str:
    return "".join(f"  {line}\n" for line in textwrap.wrap(text, 80, break_on_hyphens=False))


LONG_DESCRIPTION = " ".join(f"Alpha trigger {i}: time-series, ETL/ELT and Lambda-style platforms." for i in range(20))
# Wrapped at 88 columns with breaks at hyphens it would split "point-query", which YAML reads back as "point- query".
OVERRIDE = " ".join(["Alpha, shorter: multi-engine, Lambda-style, time-series, ad-hoc and point-query workloads."] * 4)
ALPHA_FRONTMATTER = ("name: alpha\ndescription: >\n" + _folded(LONG_DESCRIPTION)
                     + 'license: Apache-2.0\nmetadata:\n  author: t\n  version: "1.0.0"\n')
ALPHA_BODY = ("\n# Alpha\n\n"
              "Read [the guide](references/guide.md#usage), [beta](../beta/SKILL.md) and [its scripts](../beta/scripts/).\n"
              "Cases: [index](references/old-index.md).\n"
              "Format: `Per [rule-name](references/rule-name.md)`.\n"
              "See [docs](https://docs.example.test/x), [mail](mailto:t@example.test) and [top](#alpha).\n")
FILES = {
    "LICENSE.txt": "Fixture licence text.\n",
    "CLI-CONTRACT.md": "# fixture contract\n\n`fixcli sql` runs SQL.\n",
    "README.md": "# fixture upstream\n",
    "verify/run.sh": "#!/bin/sh\necho verify\n",
    "skills/alpha/SKILL.md": f"---\n{ALPHA_FRONTMATTER}---\n{ALPHA_BODY}",
    "skills/alpha/references/guide.md": "# Guide\n\n## Usage\n",
    "skills/alpha/references/case-index.md": "# Cases\n",
    "skills/beta/SKILL.md": ("---\nname: beta\ndescription: Beta skill for short checks.\nversion: 0.2.0\n---\n"
                             "# Beta\n\nBody starts right after the frontmatter.\n"),
    "skills/beta/sub/SKILL.md": "---\nname: beta-sub\ndescription: >\n  Nested beta skill.\n---\n\n\n## Sub\n\nNested body.\n",
    "skills/beta/scripts/tool.py": "print('tool')\n",
    "skills/gamma/SKILL.md": "---\nname: gamma\ndescription: Excluded skill.\n---\n\n# Gamma\n",
}
CONFIG = {
    "SKILLS": ("alpha", "beta"),
    "TOP_LEVEL_FILES": ("LICENSE.txt", "CLI-CONTRACT.md"),
    "EXCLUDED": {"skills/gamma/": "reviews something else", "README.md": "upstream overview",
                 "verify/": "upstream tests"},
    "DESCRIPTION_OVERRIDES": {"alpha": OVERRIDE},
    "LINK_FIXES": {("alpha/SKILL.md", "old-index.md"): ("case-index.md", 1)},
    "BROKEN_LINKS_ALLOWED": {("alpha/SKILL.md", "references/rule-name.md"): "placeholder in the format template"},
}
COPIED = ["CLI-CONTRACT.md", "LICENSE.txt", "UPSTREAM.md", "alpha/SKILL.md", "alpha/references/case-index.md",
          "alpha/references/guide.md", "beta/SKILL.md", "beta/scripts/tool.py", "beta/sub/SKILL.md"]
GIT_ENV = {**os.environ, "GIT_AUTHOR_DATE": "2026-09-14T12:00:00+00:00",
           "GIT_COMMITTER_DATE": "2026-09-14T12:00:00+00:00"}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.test",
                           "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, check=True, env=GIT_ENV).stdout.strip()


def commit(repo: Path, changes: dict) -> str:
    """Write `changes` (path -> text, None deletes) into `repo` (created on first use), commit, return the sha."""
    if not repo.exists():
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
    for path, text in changes.items():
        target = repo / path
        if text is None:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")
    return _git(repo, "rev-parse", "HEAD")


def skill_md_with_hint(upstream: str) -> str:
    """What the builder must make of an upstream SKILL.md whose frontmatter it does not change."""
    end = upstream.index("\n---\n", 3) + 5
    return upstream[:end] + HINT + "\n\n" + upstream[end:].lstrip("\n")


def frontmatter_without_description(text: str) -> str:
    frontmatter = text[4:text.index("\n---\n", 3) + 1]
    return re.sub(r"^description: >\n(?: +\S.*\n)+", "", frontmatter, flags=re.M)


class _Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.src = self.tmp / "upstream"
        self.sha = commit(self.src, FILES)
        self.out = self.tmp / "skills"
        self.patch(**CONFIG, LOCKED_COMMIT=self.sha)

    def patch(self, **values):
        for name, value in values.items():
            patcher = mock.patch.object(build_skills, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def render(self) -> dict[str, str]:
        return {p: b.decode("utf-8") for p, b in build_skills.render(self.src, self.sha).items()}

    def assert_build_error(self, *parts: str) -> str:
        with self.assertRaises(build_skills.BuildError) as cm:
            build_skills.render(self.src, self.sha)
        for part in parts:
            self.assertIn(part, str(cm.exception))
        return str(cm.exception)

    def main(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        rc = build_skills.main(["--source", str(self.src), "--out", str(self.out), *argv], out=out)
        return rc, out.getvalue()


class TestHint(_Case):
    def test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream(self):
        files = self.render()
        for rel in ("beta/SKILL.md", "beta/sub/SKILL.md"):
            with self.subTest(rel):
                self.assertEqual(files[rel], skill_md_with_hint(FILES[f"skills/{rel}"]))
                self.assertEqual(files[rel].count(HINT), 1)

    def test_a_body_right_after_the_frontmatter_gets_the_same_blank_line(self):
        self.assertIn(f"---\n{HINT}\n\n# Beta\n\nBody starts", self.render()["beta/SKILL.md"])

    def test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint(self):
        self.assertIn(f"---\n{HINT}\n\n## Sub\n", self.render()["beta/sub/SKILL.md"])

    def test_the_overridden_skill_md_gets_the_hint_too(self):
        alpha = self.render()["alpha/SKILL.md"]
        body = alpha[alpha.index("\n---\n", 3) + 5:]
        self.assertEqual(body, HINT + "\n\n" + ALPHA_BODY.lstrip("\n").replace("old-index.md", "case-index.md"))
        self.assertEqual(alpha.count(HINT), 1)

    def test_other_files_are_byte_identical(self):
        files = self.render()
        for rel in ("LICENSE.txt", "CLI-CONTRACT.md", "alpha/references/guide.md", "beta/scripts/tool.py"):
            with self.subTest(rel):
                self.assertEqual(files[rel], FILES[rel if "/" not in rel else f"skills/{rel}"])

    def test_a_skill_md_without_frontmatter_fails(self):
        self.sha = commit(self.src, {"skills/beta/sub/SKILL.md": "# Sub\n\nNo frontmatter.\n"})
        self.patch(LOCKED_COMMIT=self.sha)
        self.assert_build_error("beta/sub/SKILL.md", "frontmatter")


class TestDescriptions(_Case):
    def test_the_override_replaces_only_the_description(self):
        alpha = self.render()["alpha/SKILL.md"]
        self.assertEqual(frontmatter_without_description(alpha), frontmatter_without_description(FILES["skills/alpha/SKILL.md"]))
        meta = yaml.safe_load(alpha[4:alpha.index("\n---\n", 3) + 1])
        self.assertEqual(" ".join(meta["description"].split()), OVERRIDE)
        self.assertEqual((meta["name"], meta["license"], meta["metadata"]),
                         ("alpha", "Apache-2.0", {"author": "t", "version": "1.0.0"}))

    def test_the_override_is_a_folded_block_at_upstreams_indentation(self):
        alpha = self.render()["alpha/SKILL.md"]
        block = re.search(r"^description: >\n((?:.*\n)*?)license:", alpha, re.M).group(1).splitlines()
        self.assertGreater(len(block), 1)
        for line in block:
            self.assertRegex(line, r"^  \S")
            self.assertLessEqual(len(line), 88)

    def test_an_overlong_description_without_override_fails(self):
        self.patch(DESCRIPTION_OVERRIDES={})
        self.assert_build_error("alpha/SKILL.md", "1024")

    def test_an_overlong_override_fails(self):
        self.patch(DESCRIPTION_OVERRIDES={"alpha": "Alpha " * 200})
        self.assert_build_error("alpha/SKILL.md", "1024")

    def test_an_overlong_nested_description_fails(self):
        self.sha = commit(self.src, {"skills/beta/sub/SKILL.md": "---\nname: beta-sub\ndescription: >\n"
                                     + _folded(LONG_DESCRIPTION) + "---\n\n## Sub\n"})
        self.patch(LOCKED_COMMIT=self.sha)
        self.assert_build_error("beta/sub/SKILL.md", "1024")

    def test_an_override_that_yaml_does_not_read_back_fails(self):
        # YAML keeps the last of two `description` keys while the builder rewrites the first one.
        second = "description: >\n" + _folded(LONG_DESCRIPTION)
        alpha = FILES["skills/alpha/SKILL.md"].replace("license: Apache-2.0\n", second + "license: Apache-2.0\n")
        self.sha = commit(self.src, {"skills/alpha/SKILL.md": alpha})
        self.patch(LOCKED_COMMIT=self.sha)
        self.assert_build_error("alpha/SKILL.md", "read back")

    def test_an_override_of_a_description_within_the_limit_fails(self):
        # Upstream shortened it: drop the override instead of hiding upstream's new text.
        self.patch(DESCRIPTION_OVERRIDES={"alpha": OVERRIDE, "beta": "Beta, shorter."})
        self.assert_build_error("beta/SKILL.md", "DESCRIPTION_OVERRIDES")


class TestSelection(_Case):
    def test_exactly_the_listed_skills_and_top_level_files_are_copied(self):
        self.assertEqual(sorted(self.render()), COPIED)

    def test_an_upstream_entry_neither_imported_nor_excluded_fails(self):
        self.sha = commit(self.src, {"NOTICE": "Fixture notice.\n", "skills/delta/SKILL.md": FILES["skills/gamma/SKILL.md"]})
        self.patch(LOCKED_COMMIT=self.sha)
        self.assert_build_error("NOTICE", "skills/delta")

    def test_an_excluded_entry_upstream_no_longer_has_fails(self):
        self.patch(EXCLUDED={**CONFIG["EXCLUDED"], "skills/omega/": "gone"})
        self.assert_build_error("skills/omega")

    def test_the_files_come_from_the_commit_not_the_working_tree(self):
        (self.src / "LICENSE.txt").write_text("edited, not committed\n")
        (self.src / "skills" / "beta" / "untracked.md").write_text("untracked\n")
        files = self.render()
        self.assertEqual(files["LICENSE.txt"], FILES["LICENSE.txt"])
        self.assertNotIn("beta/untracked.md", files)

    def test_a_skill_without_skill_md_at_its_root_fails(self):
        self.sha = commit(self.src, {"skills/beta/SKILL.md": None})
        self.patch(LOCKED_COMMIT=self.sha)
        self.assert_build_error("beta/SKILL.md", "root")

    def test_the_source_must_be_at_the_locked_commit(self):
        head = commit(self.src, {"README.md": "# fixture upstream, newer\n"})
        message = self.assert_build_error(head, self.sha, f"git -C {self.src} fetch",
                                          f"git -C {self.src} checkout {self.sha}")
        self.assertNotIn("Traceback", message)

    def test_a_source_that_is_not_a_git_clone_fails(self):
        self.src = self.tmp / "empty"
        self.src.mkdir()
        self.assert_build_error(str(self.src))


class TestLinks(_Case):
    def test_the_link_fix_is_applied(self):
        alpha = self.render()["alpha/SKILL.md"]
        self.assertIn("[index](references/case-index.md)", alpha)
        self.assertNotIn("old-index.md", alpha)

    def test_a_link_fix_that_matches_a_different_number_of_times_fails(self):
        self.patch(LINK_FIXES={("alpha/SKILL.md", "old-index.md"): ("case-index.md", 2)})
        self.assert_build_error("LINK_FIXES", "alpha/SKILL.md")

    def test_a_link_fix_whose_text_is_gone_fails(self):
        self.patch(LINK_FIXES={**CONFIG["LINK_FIXES"], ("beta/SKILL.md", "no-such-text"): ("x", 1)})
        self.assert_build_error("LINK_FIXES", "beta/SKILL.md")

    def test_an_unlisted_broken_link_fails(self):
        self.patch(BROKEN_LINKS_ALLOWED={})
        self.assert_build_error("alpha/SKILL.md", "references/rule-name.md")

    def test_a_stale_allowed_link_fails(self):
        self.patch(BROKEN_LINKS_ALLOWED={**CONFIG["BROKEN_LINKS_ALLOWED"],
                                         ("alpha/SKILL.md", "references/guide.md#usage"): "was broken"})
        self.assert_build_error("BROKEN_LINKS_ALLOWED", "references/guide.md#usage")

    def test_which_links_count_as_broken(self):
        files = {"alpha/a.md": (b"[s](../beta/b.md#top) [d](../beta/) [u](https://example.test/x) [h](http://x) "
                                b"[m](mailto:t@example.test) [#](#here) [n](missing.md) [o](../../outside.md) "
                                b"![i](img/pic.png) [self](./a.md)"),
                 "alpha/img/pic.png": b"", "alpha/note.txt": b"[n](missing.md)", "beta/b.md": b"",
                 "other/c.md": b"[n](missing.md)"}
        self.assertEqual(build_skills.broken_links(files),
                         {("alpha/a.md", "missing.md"), ("alpha/a.md", "../../outside.md")})


class TestUpstreamMd(_Case):
    def test_records_the_source_and_every_change(self):
        text = self.render()["UPSTREAM.md"]
        for part in (build_skills.SOURCE_URL, self.sha, "2026-09-14", HINT, "`alpha/SKILL.md`",
                     f"{len(LONG_DESCRIPTION) + 1} -> {len(OVERRIDE) + 1}", "`old-index.md` -> `case-index.md`",
                     "`references/rule-name.md`", "placeholder in the format template",
                     "`skills/gamma/`: reviews something else", "`README.md`: upstream overview",
                     "`verify/`: upstream tests", "LICENSE.txt", "no NOTICE file",
                     f"build_skills.py --source", "--check"):
            self.assertIn(part, text)

    def test_lists_every_imported_skill_with_its_files_bytes_and_version(self):
        files = build_skills.render(self.src, self.sha)
        text = files["UPSTREAM.md"].decode()
        for skill, version in (("alpha", "1.0.0"), ("beta", "0.2.0")):
            inside = [p for p in files if p.startswith(skill + "/")]
            self.assertIn(f"| `{skill}/` | {len(inside)} | {sum(len(files[p]) for p in inside)} | {version} |", text)
        self.assertNotIn("gamma/` |", text)

    def test_rendering_twice_gives_identical_bytes(self):
        self.assertEqual(build_skills.render(self.src, self.sha), build_skills.render(self.src, self.sha))


class TestBuild(_Case):
    def _tree(self) -> dict[str, bytes]:
        return {p.relative_to(self.out).as_posix(): p.read_bytes() for p in self.out.rglob("*") if p.is_file()}

    def test_writes_the_rendered_tree_and_returns_its_paths(self):
        written = build_skills.build(self.src, self.out, self.sha)
        self.assertEqual(written, COPIED)
        self.assertEqual(self._tree(), build_skills.render(self.src, self.sha))

    def test_keeps_other_entries_and_removes_stale_files_inside_the_copies(self):
        for rel, text in (("doris-mcp-adapter/SKILL.md", "hand-written\n"), ("notes.txt", "mine\n"),
                          ("alpha/stale.md", "old\n"), ("beta/old/deep/x.md", "old\n")):
            (self.out / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.out / rel).write_text(text)
        build_skills.build(self.src, self.out, self.sha)
        self.assertEqual((self.out / "doris-mcp-adapter" / "SKILL.md").read_text(), "hand-written\n")
        self.assertEqual((self.out / "notes.txt").read_text(), "mine\n")
        self.assertFalse((self.out / "alpha" / "stale.md").exists())
        self.assertFalse((self.out / "beta" / "old").exists())

    def test_building_twice_gives_identical_bytes(self):
        build_skills.build(self.src, self.out, self.sha)
        first = self._tree()
        build_skills.build(self.src, self.out, self.sha)
        self.assertEqual(self._tree(), first)

    def test_a_failing_build_changes_nothing(self):
        (self.out / "alpha").mkdir(parents=True)
        (self.out / "alpha" / "stale.md").write_text("old\n")
        self.patch(DESCRIPTION_OVERRIDES={})
        with self.assertRaises(build_skills.BuildError):
            build_skills.build(self.src, self.out, self.sha)
        self.assertEqual(self._tree(), {"alpha/stale.md": b"old\n"})


class TestMain(_Case):
    def test_build_prints_a_short_summary(self):
        rc, out = self.main()
        self.assertEqual(rc, 0, out)
        self.assertEqual(out, f"wrote {len(COPIED)} files to {self.out} ({self.sha[:12]})\n")

    def test_check_passes_on_a_fresh_build_and_ignores_the_adapter(self):
        build_skills.build(self.src, self.out, self.sha)
        (self.out / "doris-mcp-adapter").mkdir()
        (self.out / "doris-mcp-adapter" / "SKILL.md").write_text("hand-written\n")
        (self.out / "notes.txt").write_text("mine\n")
        rc, out = self.main("--check")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out, f"{self.out} matches {self.sha[:12]} ({len(COPIED)} files)\n")

    def test_check_lists_every_difference(self):
        build_skills.build(self.src, self.out, self.sha)
        (self.out / "beta" / "SKILL.md").write_text("tampered\n")
        (self.out / "alpha" / "references" / "guide.md").unlink()
        (self.out / "LICENSE.txt").unlink()
        (self.out / "alpha" / "extra.md").write_text("extra\n")
        (self.out / "doris-mcp-adapter").mkdir()
        (self.out / "doris-mcp-adapter" / "SKILL.md").write_text("hand-written\n")
        before = {p: p.read_bytes() for p in self.out.rglob("*") if p.is_file()}
        rc, out = self.main("--check")
        self.assertEqual(rc, 1, out)
        self.assertEqual(out.splitlines(), ["missing LICENSE.txt", "extra alpha/extra.md",
                                            "missing alpha/references/guide.md", "differs beta/SKILL.md",
                                            f"{self.out} does not match {self.sha[:12]}: 4 differences"])
        self.assertEqual({p: p.read_bytes() for p in self.out.rglob("*") if p.is_file()}, before)

    def test_check_of_a_missing_output_lists_every_file(self):
        rc, out = self.main("--check")
        self.assertEqual(rc, 1)
        self.assertEqual(out.splitlines()[:-1], [f"missing {p}" for p in COPIED])

    def test_a_wrong_commit_exits_2_with_the_fix(self):
        self.patch(LOCKED_COMMIT="0" * 40)
        for argv in ((), ("--check",)):
            with self.subTest(argv=argv):
                rc, out = self.main(*argv)
                self.assertEqual(rc, 2)
                self.assertTrue(out.startswith("FAIL: "), out)
                self.assertIn(f"git -C {self.src} checkout {'0' * 40}", out)
                self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

新文件 `quick/test/test_skills.py`：

<!-- file: quick/test/test_skills.py sha256=61cbec91f8b40678898a286aa33e8ac9caf7f1172360bfb25de42fec5b90d1e2 -->
```python
"""quick/skills/: the Agent Skills imported into Quick next to the "Doris 专家" agent (P5 / T5.1).

The four upstream copies are generated from apache/doris-skills by scripts/build_skills.py and committed; these
checks read the committed tree only (no builder run, no upstream clone). They protect what Quick's skill import
and the agent depend on: the folder set, a SKILL.md with valid frontmatter within Quick's limits in every folder,
the adapter hint at the top of every copied SKILL.md, the licence and provenance files, the triggers kept by the
shortened descriptions, and relative links that resolve.
"""

import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_skills  # noqa: E402

SKILLS_DIR = ROOT / "quick" / "skills"
ADAPTER = "doris-mcp-adapter"
FOLDERS = {"doris-architecture-advisor", "doris-best-practices", "doris-debug", ADAPTER, "doris-profile-reader"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME_LIMIT, DESCRIPTION_LIMIT, FOLDER_LIMIT = 64, 1024, 6 * 1024 * 1024  # Quick's skill import limits

# Triggers the shortened descriptions keep on purpose (upstream's when-to-use lists, condensed).
TRIGGERS = {
    "doris-architecture-advisor": (
        "MUST USE", "data architectures", "data models", "ingestion", "sizing clusters", "business requirements",
        "IoT", "sensor", "telemetry", "real-time analytics", "dashboards", "log analysis", "log search", "CDC sync",
        "time-series", "device monitoring", "point query", "ad-hoc analytics", "lakehouse federation", "ETL/ELT",
        "report", "clickstream", "user behavior", "observability", "metrics", "fleet tracking", "OLAP",
        "table design from scratch", "design a table for", "how should I store", "build an architecture for",
        "devices sending data every", "cluster size", "what data model should I use", "ingest X GB/day",
        "MySQL/PostgreSQL", "Impala", "Kudu", "Elasticsearch/ES", "Greenplum", "Presto", "HBase", "Hive",
        "Hadoop", "Redis", "Lambda-style", "even when Doris is not named"),
    "doris-best-practices": (
        "ALSO MUST USE whenever the doris-architecture-advisor skill produces DDL — apply the Pre-Flight "
        "Checklist to every CREATE TABLE before output.",
        "MUST USE when writing, reviewing, or optimizing Doris CREATE TABLE", "partition/bucket", "data models",
        "cluster configurations", "cluster sizing", "IoT", "analytics", "dashboard", "CDC", "time-series",
        "log analysis", "real-time warehouse", "point query", "data platform", "table design", "Impala", "Kudu",
        "Elasticsearch/ES", "Greenplum", "Presto", "HBase", "Hive", "Hadoop", "Redis", "Lambda-style",
        "even when Doris is not named", "connection string", "get started", "slow query", "query profiling",
        "runtime performance diagnosis", "tablet skew", "table health", "out of scope"),
}


def _skip_until_the_adapter_lands(test: unittest.TestCase) -> None:
    """TEMPORARY: quick/skills/doris-mcp-adapter/ is written by another P5 task. Delete this helper and its calls
    once that folder is committed."""
    if not (SKILLS_DIR / ADAPTER / "SKILL.md").is_file():
        test.skipTest(f"quick/skills/{ADAPTER}/SKILL.md is not written yet")


def _split(path: Path) -> tuple[dict, str]:
    """(frontmatter as parsed YAML, body) of a SKILL.md: the YAML between the first line `---` and the next."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?\n)?---\n", text, re.S)
    if match is None:
        raise AssertionError(f"{path.relative_to(ROOT)}: no frontmatter")
    meta = yaml.safe_load(match.group(1) or "")
    if not isinstance(meta, dict):
        raise AssertionError(f"{path.relative_to(ROOT)}: frontmatter is not a mapping")
    return meta, text[match.end():]


def _folders() -> set[str]:
    return {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}


class Layout(unittest.TestCase):
    def test_the_four_upstream_copies_are_there(self):
        self.assertEqual(_folders() - {ADAPTER}, set(build_skills.SKILLS))

    def test_exactly_the_five_skill_folders(self):
        _skip_until_the_adapter_lands(self)
        self.assertEqual(_folders(), FOLDERS)

    def test_licence_contract_and_provenance(self):
        for name in ("LICENSE.txt", "CLI-CONTRACT.md"):
            self.assertTrue((SKILLS_DIR / name).is_file(), name)
        self.assertIn(build_skills.LOCKED_COMMIT, (SKILLS_DIR / "UPSTREAM.md").read_text(encoding="utf-8"))


class SkillFolders(unittest.TestCase):
    def _check(self, folder: str):
        meta, _ = _split(SKILLS_DIR / folder / "SKILL.md")
        self.assertEqual(meta.get("name"), folder)
        self.assertRegex(folder, NAME_RE)
        self.assertLessEqual(len(folder), NAME_LIMIT)
        description = meta.get("description")
        self.assertIsInstance(description, str)
        self.assertTrue(description.strip())
        self.assertLessEqual(len(description), DESCRIPTION_LIMIT)
        size = sum(p.stat().st_size for p in (SKILLS_DIR / folder).rglob("*") if p.is_file())
        self.assertLessEqual(size, FOLDER_LIMIT)

    def test_every_copy_has_a_skill_md_within_quicks_limits(self):
        for folder in build_skills.SKILLS:
            with self.subTest(folder):
                self._check(folder)

    def test_the_adapter_has_a_skill_md_within_quicks_limits(self):
        _skip_until_the_adapter_lands(self)
        self._check(ADAPTER)


class Hint(unittest.TestCase):
    def test_every_copied_skill_md_starts_with_the_adapter_hint(self):
        paths = sorted(p for skill in build_skills.SKILLS for p in (SKILLS_DIR / skill).rglob("SKILL.md"))
        self.assertGreater(len(paths), len(build_skills.SKILLS))  # the nested doris-debug domain skills too
        for path in paths:
            with self.subTest(str(path.relative_to(SKILLS_DIR))):
                _, body = _split(path)
                self.assertTrue(body.startswith(build_skills.HINT + "\n\n"), body[:80])
                self.assertEqual(path.read_text(encoding="utf-8").count(build_skills.HINT), 1)


class Descriptions(unittest.TestCase):
    def test_the_overrides_are_the_builders(self):
        self.assertEqual(set(build_skills.DESCRIPTION_OVERRIDES), set(TRIGGERS))
        for skill, text in build_skills.DESCRIPTION_OVERRIDES.items():
            with self.subTest(skill):
                meta, _ = _split(SKILLS_DIR / skill / "SKILL.md")
                self.assertEqual(" ".join(meta["description"].split()), " ".join(text.split()))

    def test_the_shortened_descriptions_keep_their_triggers(self):
        for skill, phrases in TRIGGERS.items():
            meta, _ = _split(SKILLS_DIR / skill / "SKILL.md")
            description = " ".join(meta["description"].split())
            for phrase in phrases:
                with self.subTest(skill=skill, phrase=phrase):
                    self.assertIn(phrase, description)


class Links(unittest.TestCase):
    def test_every_relative_link_in_the_copies_resolves_or_is_allowed(self):
        files = {p.relative_to(SKILLS_DIR).as_posix(): p.read_bytes() for p in SKILLS_DIR.rglob("*") if p.is_file()}
        self.assertEqual(build_skills.broken_links(files), set(build_skills.BROKEN_LINKS_ALLOWED))


if __name__ == "__main__":
    unittest.main()
```

`test-check-secrets.sh` 的补丁（fixture 的行用 `printf` 拼出来，测试文件本身不会命中规则）：

<!-- file: t51-tests.diff sha256=5d7ceded8ab700f68eb792a47b0b68dab74d79678db86d5e04775ec675055335 -->
```diff
diff --git a/scripts/test/test-check-secrets.sh b/scripts/test/test-check-secrets.sh
index a3860be..98cd9c3 100644
--- a/scripts/test/test-check-secrets.sh
+++ b/scripts/test/test-check-secrets.sh
@@ -57,6 +57,24 @@ check "leaked password of the second secret fails the check" "1|yes" \
   "$RC|$(has "$OUT" "LEAK: password of secret doris-mcp/cognito-demo-user found in leaky.log.txt")"
 rm "$TMP/repo/leaky.log.txt"
 
+# Generic patterns: a placeholder after aws_secret_access_key is not a secret, a real-looking value is.
+# The lines are assembled with printf so that this file itself never matches the pattern.
+KEY=aws_secret_access_key
+FAKE_AWS_SECRET="wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY01"  # the shape of AWS's documented example key
+for value in "..." "<secret>" '${AWS_SECRET_ACCESS_KEY}' "" '"<secret>"'; do
+  printf '# be.conf\n%s = %s\n' "$KEY" "$value" > "$TMP/repo/be.conf.md"
+  run_check readable
+  check "placeholder '$value' after $KEY is not a hit" 0 "$RC"
+done
+printf '# be.conf\n%s = %s\n' "$KEY" "$FAKE_AWS_SECRET" > "$TMP/repo/be.conf.md"
+run_check readable
+check "a real-looking $KEY fails the check" "1|yes" "$RC|$(has "$OUT" "LEAK: secret-like pattern in be.conf.md")"
+check "never prints the $KEY value" no "$(has "$OUT" "$FAKE_AWS_SECRET")"
+printf '%s="%s"\n' "$KEY" "$FAKE_AWS_SECRET" > "$TMP/repo/be.conf.md"
+run_check readable
+check "a quoted $KEY without spaces fails the check" 1 "$RC"
+rm "$TMP/repo/be.conf.md"
+
 # An exact-value check that could not run is not a pass (P2 whole review M4).
 run_check unreadable
 check "unreadable secrets fail the check" 1 "$RC"
```

- [ ] **Step 3：确认失败**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
for s in scripts quick; do
  .venv/bin/python -m unittest discover -s $s/test > /tmp/t51-red-$s.log 2>&1; echo "$s rc=$?"
  grep -E '^(FAIL|ERROR):' /tmp/t51-red-$s.log | sed -E 's/ \(.*//' | sort -u; grep -E '^Ran |^OK|^FAILED' /tmp/t51-red-$s.log
done
grep -hE "^(ModuleNotFoundError|ImportError)" /tmp/t51-red-scripts.log /tmp/t51-red-quick.log | sort | uniq -c
bash scripts/test/test-check-secrets.sh > /tmp/t51-red-cs.log 2>&1; echo "check-secrets rc=$?"
grep -E '^FAIL' /tmp/t51-red-cs.log; tail -1 /tmp/t51-red-cs.log
```
期望（实测，秒数每次不同）：
```
scripts rc=1
ERROR: test_build_skills
Ran 76 tests in 1.381s
FAILED (errors=1)
quick rc=1
ERROR: test_skills
Ran 17 tests in 0.126s
FAILED (errors=1)
      1 ImportError: Failed to import test module: test_build_skills
      1 ImportError: Failed to import test module: test_skills
      2 ModuleNotFoundError: No module named 'build_skills'
check-secrets rc=1
FAIL placeholder '...' after aws_secret_access_key is not a hit: expected '0', got '1'
FAIL placeholder '<secret>' after aws_secret_access_key is not a hit: expected '0', got '1'
FAIL placeholder '${AWS_SECRET_ACCESS_KEY}' after aws_secret_access_key is not a hit: expected '0', got '1'
FAIL placeholder '' after aws_secret_access_key is not a hit: expected '0', got '1'
FAIL placeholder '"<secret>"' after aws_secret_access_key is not a hit: expected '0', got '1'
5 failed
```
失败的正是 Step 4 要做的：
- `scripts/test`、`quick/test` 各 1 个 `ERROR`：两个新测试模块都导入 `build_skills`，它还不存在（`ModuleNotFoundError`）。其余已有的测试（`scripts/test` 75 个、`quick/test` 16 个）都通过。
- `test-check-secrets.sh` 的 5 个 `FAIL`：都是占位符（`...`、`<secret>`、`${AWS_SECRET_ACCESS_KEY}`、空值、带引号的 `"<secret>"`），旧规则把它们当成了泄漏。新加的另外 3 项（真实形状的值仍然命中、带引号不带空格的值也命中、`LEAK` 行不打印值）在旧规则下已经通过：它们防止 Step 4 把规则改得太宽，突变 sk30–sk34 证明它们有效。

失败的项目或个数不同时（例如出现别的 `ERROR`，或者 check-secrets 的真实值用例也失败），先查明原因，不要进入 Step 4。

- [ ] **Step 4：实现：`check-secrets.sh` 的规则、`build_skills.py`，生成副本**

先改 `check-secrets.sh`：副本里有上面说的 S3 示例，旧规则会让 Step 6 的提交失败。

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py t51-impl.diff /tmp/t51-impl.diff
git apply /tmp/t51-impl.diff && git diff --shortstat scripts/check-secrets.sh
.venv/bin/python /tmp/p5-extract.py scripts/build_skills.py
```
期望（实测）：
```
t51-impl.diff -> /tmp/t51-impl.diff (16 lines)
 1 file changed, 3 insertions(+), 2 deletions(-)
scripts/build_skills.py -> scripts/build_skills.py (375 lines)
```

<!-- file: t51-impl.diff sha256=7e6af932cae6be55d8c4aab7eb67d932da6e460f773313592b8b01897e80e4d1 -->
```diff
diff --git a/scripts/check-secrets.sh b/scripts/check-secrets.sh
index 40ed0c2..6565541 100644
--- a/scripts/check-secrets.sh
+++ b/scripts/check-secrets.sh
@@ -53,8 +53,9 @@ done
 unset pw
 
 # 2) Generic patterns: AWS access keys, private keys, inline passwords.
-#    Placeholders such as IDENTIFIED BY '<password>' or '${DORIS_RO_PASSWORD}' are not secrets.
-patterns='AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|aws_secret_access_key[[:space:]]*=|IDENTIFIED BY '"'"'[^<$'"'"'][^<'"'"']{3,}'"'"
+#    Placeholders such as IDENTIFIED BY '<password>' or '${DORIS_RO_PASSWORD}' are not secrets, nor is an
+#    aws_secret_access_key whose value is ..., <secret>, ${VAR} or empty (the Doris docs' S3 examples).
+patterns='AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|aws_secret_access_key[[:space:]]*=[[:space:]]*["'"'"']?[^[:space:]<$."'"'"']|IDENTIFIED BY '"'"'[^<$'"'"'][^<'"'"']{3,}'"'"
 for f in "${files[@]}"; do
   if grep -qIE -- "$patterns" "$f"; then
     echo "LEAK: secret-like pattern in $f"
```

新文件 `scripts/build_skills.py`：

<!-- file: scripts/build_skills.py sha256=3df65b41a5c383196ea014b34620df1deccdcef5c24f5362243dd197e5a4a3fc -->
```python
#!/usr/bin/env python3
"""Write quick/skills/: copies of apache/doris-skills for Quick, next to the hand-written doris-mcp-adapter (P5 / T5.1).

  git clone https://github.com/apache/doris-skills /tmp/doris-skills
  git -C /tmp/doris-skills checkout 0476f3b84adeee4df75bc7ed694980306f8c6ab8
  .venv/bin/python scripts/build_skills.py --source /tmp/doris-skills           # (re)write quick/skills/
  .venv/bin/python scripts/build_skills.py --source /tmp/doris-skills --check   # compare only, write nothing

The copies are upstream's files at LOCKED_COMMIT (read from git objects, not from the clone's working tree) with the
edits recorded in the constants below: the adapter hint in every SKILL.md, the description overrides and the link
fixes. UPSTREAM.md is generated from the same constants. Only the SKILLS folders and the generated top-level files
are written; quick/skills/doris-mcp-adapter/ and anything else there is never touched. Prints paths and counts,
never file contents.
Exit code: 0 when written / (--check) identical, 1 when --check finds a difference, 2 when the clone is not at
LOCKED_COMMIT, upstream no longer matches the constants, or the arguments are wrong.
"""

import argparse
import posixpath
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE_URL = "https://github.com/apache/doris-skills"
LOCKED_COMMIT = "0476f3b84adeee4df75bc7ed694980306f8c6ab8"
UPSTREAM_MD = "UPSTREAM.md"
DESCRIPTION_LIMIT = 1024  # characters of the parsed `description`: Quick's skill import limit
WRAP = 88  # line width of a folded description override (upstream's lines are about as long)

SKILLS = ("doris-architecture-advisor", "doris-best-practices", "doris-debug", "doris-profile-reader")
# Also copied: Apache-2.0 wants the licence with the copies, and the contract lists the doriscli commands and JSON
# fields the skills use, which is what doris-mcp-adapter maps to the MCP tools.
TOP_LEVEL_FILES = ("LICENSE.txt", "CLI-CONTRACT.md")
# Every other upstream top-level entry and skill, with the reason it is left out. An upstream entry that is neither
# imported nor listed here (a new skill, a NOTICE file) stops the build.
EXCLUDED = {
    "skills/doris-repo-review/": "reviews Apache Doris source-code pull requests in a local clone (git, gh); "
                                 "it never talks to a cluster",
    "README.md": "upstream's overview and install guide (npx skills, doriscli); UPSTREAM.md takes its place",
    "verify/": "upstream's regression tests against a live cluster through doriscli, not skill content",
    ".asf.yaml": "Apache infrastructure settings of the upstream repository",
    ".gitignore": "upstream's git settings",
}

# The first body line of every copied SKILL.md (top-level and nested), followed by one blank line.
HINT = ("> **Environment:** Amazon Quick with the Doris MCP tools (`doris___*`), not `doriscli`. "
        "Load the `doris-mcp-adapter` skill and map every command below through it.")

# Upstream descriptions over DESCRIPTION_LIMIT, condensed in upstream's words with every trigger kept.
DESCRIPTION_OVERRIDES = {
    "doris-architecture-advisor": (
        "Workload-aware architecture design for Apache Doris. MUST USE when designing data architectures, "
        "choosing data models, planning ingestion, sizing clusters, or turning business requirements into "
        "Apache Doris designs. Use for IoT/sensor/telemetry, real-time analytics, dashboards, log analysis, "
        "log search, CDC sync, time-series, device monitoring, point query, ad-hoc analytics, lakehouse "
        "federation, ETL/ELT, report analytics, clickstream, user behavior, observability, metrics, fleet "
        "tracking, or any OLAP table design from scratch. Also triggers on \"design a table for...\", "
        "\"how should I store...\", \"build an architecture for...\", \"we have X devices sending data every Y "
        "seconds\", \"recommend a cluster size\", \"what data model should I use\", \"we need to ingest X "
        "GB/day\", and on migrating from or replacing MySQL/PostgreSQL, Impala, Kudu, Elasticsearch/ES, "
        "Greenplum, Presto, HBase, Hive, Hadoop, Redis, or Lambda-style multi-engine platforms, even when Doris "
        "is not named."),
    "doris-best-practices": (
        "Apache Doris table design and cluster sizing best practices. MUST USE when writing, reviewing, or "
        "optimizing Doris CREATE TABLE statements, partition/bucket strategies, data models, or cluster "
        "configurations. ALSO MUST USE whenever the doris-architecture-advisor skill produces DDL — apply the "
        "Pre-Flight Checklist to every CREATE TABLE before output. Also triggers on any table design decision, "
        "e.g. for IoT, analytics, dashboard, CDC, time-series, log analysis, real-time warehouse, point query, "
        "or data platform workloads, and on replacing or migrating from Impala, Kudu, Elasticsearch/ES, "
        "Greenplum, Presto, HBase, Hive, Hadoop, Redis, or Lambda-style multi-engine platforms, even when Doris "
        "is not named. Also use when user provides a Doris connection string or asks to get started, and for "
        "slow query investigation, query profiling, runtime performance diagnosis, tablet skew analysis, and "
        "table health checks. Cluster lifecycle, billing, and networking are out of scope."),
}

# (file, old text): (new text, occurrences in upstream's file). Exact-text edits where the intended target is obvious.
LINK_FIXES = {
    # The router's name for shared/references/03-cir-case-index.md, the only 03-* file there ("45 cases").
    ("doris-debug/SKILL.md", "03-case-index.md"): ("03-cir-case-index.md", 3),
}
# (file, link target): reason. Relative links that resolve to nothing, kept as upstream wrote them.
_EXAMPLE_ANSWER = ("example answer inside a code block; the path is relative to the skills folder, where the "
                   "file exists")
BROKEN_LINKS_ALLOWED = {
    ("doris-architecture-advisor/SKILL.md", "doris-best-practices/references/rule-name.md"):
        "placeholder in the answer-format template",
    ("doris-architecture-advisor/SKILL.md", "doris-best-practices/references/schema-bucket-target-size.md"):
        _EXAMPLE_ANSWER,
    ("doris-architecture-advisor/SKILL.md", "doris-best-practices/references/schema-model-choose-for-workload.md"):
        _EXAMPLE_ANSWER,
    ("doris-architecture-advisor/SKILL.md", "doris-best-practices/references/schema-props-compression.md"):
        _EXAMPLE_ANSWER,
}

_FOLDED_DESCRIPTION = re.compile(r"^description: >\n((?: +\S.*\n)+)", re.M)
_LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)")


class BuildError(Exception):
    """The clone or upstream does not match the constants; the message says what to change."""


def _git(source: Path, *args: str, stdin: bytes | None = None) -> bytes:
    run = subprocess.run(["git", "-C", str(source), *args], input=stdin, capture_output=True)
    if run.returncode:
        raise BuildError(f"git {args[0]} failed in {source}: {run.stderr.decode(errors='replace').strip()}")
    return run.stdout


def _check_commit(source: Path, commit: str) -> None:
    head = _git(source, "rev-parse", "HEAD").decode().strip()
    if head != commit:
        raise BuildError(f"{source} is at {head}, the builder is locked to {commit}; run\n"
                         f"  git -C {source} fetch\n  git -C {source} checkout {commit}")


def is_copy(rel: str) -> bool:
    """Whether an output path is an upstream copy: inside a SKILLS folder, or one of TOP_LEVEL_FILES."""
    return rel.split("/", 1)[0] in SKILLS or rel in TOP_LEVEL_FILES


def _select(paths: list[str]) -> dict[str, str]:
    """{upstream path: output path} of the imported files; every upstream entry must be imported or EXCLUDED."""
    entries = {"/".join(p.split("/")[:2]) if p.startswith("skills/") else p.split("/")[0] for p in paths}
    known = {f"skills/{s}" for s in SKILLS} | set(TOP_LEVEL_FILES) | {e.rstrip("/") for e in EXCLUDED}
    problems = [f"upstream has {e}: import it (SKILLS, TOP_LEVEL_FILES) or list it in EXCLUDED"
                for e in sorted(entries - known)]
    problems += [f"upstream no longer has {e}: update SKILLS, TOP_LEVEL_FILES or EXCLUDED"
                 for e in sorted(known - entries)]
    if problems:
        raise BuildError("; ".join(problems))
    return {p: p.removeprefix("skills/") for p in paths
            if p in TOP_LEVEL_FILES or (p.startswith("skills/") and p.split("/")[1] in SKILLS)}


def _read(source: Path, commit: str, paths: list[str]) -> dict[str, bytes]:
    """The content of `paths` at `commit`, from one `git cat-file --batch`."""
    data = _git(source, "cat-file", "--batch", stdin="".join(f"{commit}:{p}\n" for p in paths).encode())
    files, at = {}, 0
    for path in paths:
        eol = data.index(b"\n", at)
        size = int(data[at:eol].split()[2])
        files[path] = data[eol + 1:eol + 1 + size]
        at = eol + 2 + size  # the content is followed by a newline
    return files


def split_frontmatter(text: str, where: str) -> tuple[str, str]:
    """(frontmatter, body) of a SKILL.md: the file starts with a line `---`, the frontmatter ends at the next one."""
    end = text.find("\n---\n", 3)
    if not text.startswith("---\n") or end < 0:
        raise BuildError(f"{where}: no YAML frontmatter (a '---' line, the YAML, a '---' line)")
    return text[4:end + 1], text[end + 5:]


def _meta(frontmatter: str, where: str) -> dict:
    try:
        meta = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        raise BuildError(f"{where}: the frontmatter is not valid YAML") from None
    if not isinstance(meta, dict) or not isinstance(meta.get("description"), str) or not meta["description"].strip():
        raise BuildError(f"{where}: the frontmatter has no description")
    return meta


def _override_description(frontmatter: str, text: str, where: str) -> str:
    """Replace the value of a folded `description: >` block, keeping its indentation and every other byte."""
    block = _FOLDED_DESCRIPTION.search(frontmatter)
    if block is None:
        raise BuildError(f"{where}: the description is not a folded block ('description: >'); update the builder")
    indent = block.group(1)[:len(block.group(1)) - len(block.group(1).lstrip(" "))]
    lines = textwrap.wrap(text, WRAP, initial_indent=indent, subsequent_indent=indent,
                          break_long_words=False, break_on_hyphens=False)
    return frontmatter[:block.start(1)] + "".join(f"{line}\n" for line in lines) + frontmatter[block.end(1):]


def _edit_skill_md(rel: str, text: str) -> tuple[str, tuple[int, int] | None]:
    """The copied SKILL.md and, if its description was overridden, (upstream length, new length).

    Result: `---` line, frontmatter (description overridden if listed), `---` line, HINT, one blank line, the body
    without its leading blank lines."""
    frontmatter, body = split_frontmatter(text, rel)
    skill = rel.split("/", 1)[0]
    lengths = None
    if rel == f"{skill}/SKILL.md" and skill in DESCRIPTION_OVERRIDES:
        before = len(_meta(frontmatter, rel)["description"])
        if before <= DESCRIPTION_LIMIT:
            raise BuildError(f"{rel}: upstream's description is {before} characters now, within the limit; "
                             "drop its DESCRIPTION_OVERRIDES entry")
        override = DESCRIPTION_OVERRIDES[skill]
        frontmatter = _override_description(frontmatter, override, rel)
        if _meta(frontmatter, rel)["description"].split() != override.split():
            raise BuildError(f"{rel}: the description override does not read back as written")
        lengths = (before, len(_meta(frontmatter, rel)["description"]))
    length = len(_meta(frontmatter, rel)["description"])
    if length > DESCRIPTION_LIMIT:
        raise BuildError(f"{rel}: the description is {length} characters, Quick allows {DESCRIPTION_LIMIT}; "
                         "add or shorten its DESCRIPTION_OVERRIDES entry")
    body = body.lstrip("\n")
    return f"---\n{frontmatter}---\n{HINT}\n\n{body}", lengths


def _apply_link_fixes(files: dict[str, bytes]) -> None:
    for (rel, old), (new, count) in sorted(LINK_FIXES.items()):
        text = files[rel].decode("utf-8") if rel in files else ""
        found = text.count(old)
        if found != count:
            raise BuildError(f"LINK_FIXES: {old!r} occurs {found} times in {rel}, expected {count}; upstream changed")
        files[rel] = text.replace(old, new).encode("utf-8")


def broken_links(files: dict[str, bytes]) -> set[tuple[str, str]]:
    """(file, target) of every relative Markdown link in the copied .md files that points at nothing in `files`.

    http(s)://, mailto: and #anchor links are skipped and a target's #anchor is dropped; the target is resolved
    against the linking file's folder and may be a file or a folder (a sibling copied skill counts)."""
    folders = {"/".join(p.split("/")[:i]) for p in files for i in range(1, p.count("/") + 1)}
    broken = set()
    for rel, data in files.items():
        if not (rel.endswith(".md") and is_copy(rel)):
            continue
        for target in _LINK.findall(data.decode("utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target.split("#", 1)[0]))
            if path not in files and path not in folders:
                broken.add((rel, target))
    return broken


def _check_links(files: dict[str, bytes]) -> None:
    broken, allowed = broken_links(files), set(BROKEN_LINKS_ALLOWED)
    problems = [f"broken link {target} in {rel}: fix it (LINK_FIXES) or list it in BROKEN_LINKS_ALLOWED"
                for rel, target in sorted(broken - allowed)]
    problems += [f"BROKEN_LINKS_ALLOWED: {target} in {rel} is not broken any more; drop the entry"
                 for rel, target in sorted(allowed - broken)]
    if problems:
        raise BuildError("; ".join(problems))


def _version(meta: dict) -> str:
    metadata = meta["metadata"] if isinstance(meta.get("metadata"), dict) else {}
    return str(meta.get("version") or metadata.get("version") or "-")


def _upstream_md(commit: str, date: str, files: dict[str, bytes], overridden: dict[str, tuple[int, int]],
                 notice: bool) -> str:
    rows = []
    for skill in SKILLS:
        inside = [p for p in files if p.startswith(f"{skill}/")]
        meta = _meta(split_frontmatter(files[f"{skill}/SKILL.md"].decode("utf-8"), skill)[0], skill)
        rows.append(f"| `{skill}/` | {len(inside)} | {sum(len(files[p]) for p in inside)} | {_version(meta)} |")
    skill_mds = sum(1 for p in files if posixpath.basename(p) == "SKILL.md")
    lines = [
        "# quick/skills: copies of apache/doris-skills", "",
        "Generated by `scripts/build_skills.py`: change its constants and rebuild, do not edit the copies by hand. "
        "`doris-mcp-adapter/` is hand-written and not generated.", "",
        f"- Source: {SOURCE_URL}", f"- Commit: `{commit}` (committed {date})", "",
        "## Rebuild and check", "",
        f"    git clone {SOURCE_URL} /tmp/doris-skills && git -C /tmp/doris-skills checkout {commit}",
        "    .venv/bin/python scripts/build_skills.py --source /tmp/doris-skills           # rewrite the copies",
        "    .venv/bin/python scripts/build_skills.py --source /tmp/doris-skills --check   # compare only", "",
        "## Imported", "",
        "| Folder | Files | Bytes | Upstream version |", "|---|---:|---:|---|", *rows, "",
        "Also copied: " + ", ".join(f"`{name}`" for name in TOP_LEVEL_FILES) + ".", "",
        "## Changes to upstream", "",
        f"- Every `SKILL.md` ({skill_mds}, top-level and nested) starts its body with this line and one blank line "
        "(the body's own leading blank lines are dropped):", "", f"  {HINT}", "",
        f"- Descriptions over Quick's {DESCRIPTION_LIMIT}-character limit, rewritten shorter with the same triggers "
        "(the other frontmatter lines are upstream's):",
        *(f"  - `{rel}`: {old} -> {new} characters" for rel, (old, new) in sorted(overridden.items())),
        "- Link fixes:",
        *(f"  - `{rel}`: `{old}` -> `{new}` ({count}x)" for (rel, old), (new, count) in sorted(LINK_FIXES.items())),
        "- Broken links kept as upstream wrote them:",
        *(f"  - `{rel}`: `{target}`: {why}" for (rel, target), why in sorted(BROKEN_LINKS_ALLOWED.items())),
        "- Only file contents are copied: executable bits are not kept.", "",
        "## Not imported", "",
        *(f"- `{entry}`: {why}" for entry, why in EXCLUDED.items()), "",
        "## Licence", "",
        "Apache License 2.0: `LICENSE.txt` is upstream's. The copies are upstream's files, unmodified except for the "
        "changes listed above." + ("" if notice else " Upstream has no NOTICE file at this commit."),
    ]
    return "\n".join(lines) + "\n"


def render(source: Path, commit: str = LOCKED_COMMIT) -> dict[str, bytes]:
    """{output path: content} of the generated tree (the copies and UPSTREAM.md); writes nothing."""
    _check_commit(source, commit)
    upstream = [p for p in _git(source, "ls-tree", "-r", "-z", "--name-only", commit).decode().split("\0") if p]
    selected = _select(upstream)
    content = _read(source, commit, sorted(selected))
    files = {rel: content[path] for path, rel in selected.items()}
    for skill in SKILLS:
        if f"{skill}/SKILL.md" not in files:
            raise BuildError(f"{skill}/SKILL.md is missing upstream: Quick needs a SKILL.md at the skill's root")
    _apply_link_fixes(files)
    overridden = {}
    for rel in sorted(files):
        if posixpath.basename(rel) == "SKILL.md":
            text, lengths = _edit_skill_md(rel, files[rel].decode("utf-8"))
            files[rel] = text.encode("utf-8")
            if lengths:
                overridden[rel] = lengths
    _check_links(files)
    date = _git(source, "log", "-1", "--format=%cs", commit).decode().strip()
    notice = any(p.upper().startswith("NOTICE") for p in upstream if "/" not in p)
    files[UPSTREAM_MD] = _upstream_md(commit, date, files, overridden, notice).encode("utf-8")
    return dict(sorted(files.items()))


def build(source: Path, out: Path, commit: str = LOCKED_COMMIT) -> list[str]:
    """Render, then write the tree into `out`: stale files inside the SKILLS folders go, nothing else is touched."""
    files = render(source, commit)
    for skill in SKILLS:
        for path in sorted((out / skill).rglob("*"), reverse=True):  # a folder's entries before the folder
            if path.is_dir():
                if not any(path.iterdir()):
                    path.rmdir()
            elif path.relative_to(out).as_posix() not in files:
                path.unlink()
    for rel, data in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
    return sorted(files)


def compare(files: dict[str, bytes], out: Path) -> list[str]:
    """`missing PATH` / `extra PATH` / `differs PATH` lines between a render and `out`, generated paths only."""
    present = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    present = {p for p in present if is_copy(p) or p == UPSTREAM_MD}
    found = [(p, "missing") for p in files if p not in present] + [(p, "extra") for p in present if p not in files]
    found += [(p, "differs") for p in present & set(files) if (out / p).read_bytes() != files[p]]
    return [f"{kind} {path}" for path, kind in sorted(found)]


def _shown(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help=f"a clone of {SOURCE_URL} at LOCKED_COMMIT")
    parser.add_argument("--out", type=Path, default=ROOT / "quick" / "skills", help="default: quick/skills")
    parser.add_argument("--check", action="store_true", help="compare --out with a fresh render, write nothing")
    args = parser.parse_args(argv)
    name, commit = _shown(args.out), LOCKED_COMMIT
    try:
        if not args.check:
            written = build(args.source, args.out, commit)
            print(f"wrote {len(written)} files to {name} ({commit[:12]})", file=out)
            return 0
        files = render(args.source, commit)
    except BuildError as e:
        print(f"FAIL: {e}", file=out)
        return 2
    differences = compare(files, args.out)
    for line in differences:
        print(line, file=out)
    if differences:
        print(f"{name} does not match {commit[:12]}: {len(differences)} differences", file=out)
        return 1
    print(f"{name} matches {commit[:12]} ({len(files)} files)", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

clone upstream 并生成副本（`/tmp/doris-skills` 只读，不在里面改任何东西；已经 clone 过就直接 checkout）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
test -d /tmp/doris-skills/.git || git clone -q https://github.com/apache/doris-skills /tmp/doris-skills
git -C /tmp/doris-skills checkout -q 0476f3b84adeee4df75bc7ed694980306f8c6ab8
git -C /tmp/doris-skills log -1 --format='%H %cs'
git -C /tmp/doris-skills ls-tree -r --name-only HEAD | wc -l
.venv/bin/python scripts/build_skills.py --source /tmp/doris-skills; echo "exit=$?"
.venv/bin/python scripts/build_skills.py --source /tmp/doris-skills --check; echo "exit=$?"
find quick/skills -type f ! -path '*/doris-mcp-adapter/*' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum
for e in quick/skills/*; do printf '%s: %s files, %s bytes\n' "${e#quick/skills/}" "$(find "$e" -type f | wc -l)" "$(find "$e" -type f -print0 | xargs -0 cat | wc -c)"; done
grep -c '^> \*\*Environment:\*\*' $(find quick/skills -name SKILL.md | LC_ALL=C sort) | grep -vc ':1$'
```
期望（实测）：
```
0476f3b84adeee4df75bc7ed694980306f8c6ab8 2026-09-14
177
wrote 119 files to quick/skills (0476f3b84ade)
exit=0
quick/skills matches 0476f3b84ade (119 files)
exit=0
db3ca57ce3caf9ca72b4ee548b48ac4f0d37c00712df646855e9177c91cb91eb  -
CLI-CONTRACT.md: 1 files, 3026 bytes
LICENSE.txt: 1 files, 11358 bytes
UPSTREAM.md: 1 files, 3243 bytes
doris-architecture-advisor: 19 files, 104212 bytes
doris-best-practices: 51 files, 98592 bytes
doris-debug: 34 files, 126021 bytes
doris-profile-reader: 12 files, 219826 bytes
0
```
整棵树的 sha256 必须是上面这个值（`db3ca57c…`）：它只取决于锁定的 commit 和构建脚本的常量。最后一行 `0` 表示 14 个 `SKILL.md` 每个都恰好有 1 行提示。

`--check` 的 3 种输出：一致时 `quick/skills matches 0476f3b84ade (N files)`、exit 0；有不同时逐行列出 `missing` / `extra` / `differs PATH`，再一行 `… N differences`、exit 1；clone 不在锁定的 commit 或 upstream 和常量对不上时一行 `FAIL: …`（说明要改哪个常量或执行哪条 git 命令）、exit 2。

- [ ] **Step 5：确认通过；突变**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 期望：Ran 113 tests … OK
.venv/bin/python -m unittest discover -s quick/test 2>&1 | tail -3                                  # 期望：Ran 25 tests … OK (skipped=2)
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 161 tests … OK
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 期望：Ran 89 tests … OK
for t in doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh infra/test/test-35-runtime-role.sh \
         infra/test/test-40-doris-secret.sh infra/test/test-lib.sh scripts/test/test-check-secrets.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 期望：每行 all passed
grep -c '^ok' <(bash scripts/test/test-check-secrets.sh 2>&1)                                       # 期望：20
```
期望（实测，秒数每次不同）：
```
Ran 113 tests in 1.991s

OK
Ran 25 tests in 0.140s

OK (skipped=2)
Ran 161 tests in 6.419s

OK
Ran 89 tests in 0.448s

OK
doris/test/test-apply-admin-sql.sh: all passed
doris/test/test-publish-semantic.sh: all passed
infra/test/test-35-runtime-role.sh: all passed
infra/test/test-40-doris-secret.sh: all passed
infra/test/test-lib.sh: all passed
scripts/test/test-check-secrets.sh: all passed
20
```

突变：`sk` 改构建脚本和 `check-secrets.sh`，`st` 改生成的副本（每个突变体都是「有人手改了副本」或「构建脚本出了错」的样子）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json sk; echo "rc=$?"
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json st; echo "rc=$?"
.venv/bin/python scripts/build_skills.py --source /tmp/doris-skills --check; echo "exit=$?"
```
突变期望（实测）：
```
sk1 hint only in the top-level SKILL.md, nested ones copied unchanged: caught by test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream, test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint (Ran 38, FAILED (failures=2))
sk2 hint appended at the end of the file: caught by test_a_body_right_after_the_frontmatter_gets_the_same_blank_line, test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream, test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint, test_the_overridden_skill_md_gets_the_hint_too (Ran 38, FAILED (failures=5))
sk3 hint before the frontmatter: caught by test_a_body_right_after_the_frontmatter_gets_the_same_blank_line, test_build_prints_a_short_summary, test_building_twice_gives_identical_bytes, test_check_lists_every_difference, test_check_of_a_missing_output_lists_every_file, test_check_passes_on_a_fresh_build_and_ignores_the_adapter, test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream, test_exactly_the_listed_skills_and_top_level_files_are_copied, test_keeps_other_entries_and_removes_stale_files_inside_the_copies, test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint, test_lists_every_imported_skill_with_its_files_bytes_and_version, test_other_files_are_byte_identical, test_records_the_source_and_every_change, test_rendering_twice_gives_identical_bytes, test_the_files_come_from_the_commit_not_the_working_tree, test_the_link_fix_is_applied, test_the_overridden_skill_md_gets_the_hint_too, test_the_override_is_a_folded_block_at_upstreams_indentation, test_the_override_replaces_only_the_description, test_writes_the_rendered_tree_and_returns_its_paths (Ran 38, FAILED (failures=2, errors=18))
sk4 no blank line after the hint: caught by test_a_body_right_after_the_frontmatter_gets_the_same_blank_line, test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream, test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint, test_the_overridden_skill_md_gets_the_hint_too (Ran 38, FAILED (failures=5))
sk5 the body's leading blank lines kept: caught by test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream, test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint, test_the_overridden_skill_md_gets_the_hint_too (Ran 38, FAILED (failures=3))
sk6 override not applied (upstream description kept): caught by test_a_body_right_after_the_frontmatter_gets_the_same_blank_line, test_a_skill_md_without_frontmatter_fails, test_a_stale_allowed_link_fails, test_an_overlong_nested_description_fails, test_an_override_of_a_description_within_the_limit_fails, test_an_override_that_yaml_does_not_read_back_fails, test_an_unlisted_broken_link_fails, test_build_prints_a_short_summary, test_building_twice_gives_identical_bytes, test_check_lists_every_difference, test_check_of_a_missing_output_lists_every_file, test_check_passes_on_a_fresh_build_and_ignores_the_adapter, test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream, test_exactly_the_listed_skills_and_top_level_files_are_copied, test_keeps_other_entries_and_removes_stale_files_inside_the_copies, test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint, test_lists_every_imported_skill_with_its_files_bytes_and_version, test_other_files_are_byte_identical, test_records_the_source_and_every_change, test_rendering_twice_gives_identical_bytes, test_the_files_come_from_the_commit_not_the_working_tree, test_the_link_fix_is_applied, test_the_overridden_skill_md_gets_the_hint_too, test_the_override_is_a_folded_block_at_upstreams_indentation, test_the_override_replaces_only_the_description, test_writes_the_rendered_tree_and_returns_its_paths (Ran 38, FAILED (failures=8, errors=18))
sk7 override rewrite computed but discarded: caught by test_a_body_right_after_the_frontmatter_gets_the_same_blank_line, test_a_skill_md_without_frontmatter_fails, test_a_stale_allowed_link_fails, test_an_overlong_nested_description_fails, test_an_overlong_override_fails, test_an_override_of_a_description_within_the_limit_fails, test_an_unlisted_broken_link_fails, test_build_prints_a_short_summary, test_building_twice_gives_identical_bytes, test_check_lists_every_difference, test_check_of_a_missing_output_lists_every_file, test_check_passes_on_a_fresh_build_and_ignores_the_adapter, test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream, test_exactly_the_listed_skills_and_top_level_files_are_copied, test_keeps_other_entries_and_removes_stale_files_inside_the_copies, test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint, test_lists_every_imported_skill_with_its_files_bytes_and_version, test_other_files_are_byte_identical, test_records_the_source_and_every_change, test_rendering_twice_gives_identical_bytes, test_the_files_come_from_the_commit_not_the_working_tree, test_the_link_fix_is_applied, test_the_overridden_skill_md_gets_the_hint_too, test_the_override_is_a_folded_block_at_upstreams_indentation, test_the_override_replaces_only_the_description, test_writes_the_rendered_tree_and_returns_its_paths (Ran 38, FAILED (failures=8, errors=18))
sk8 description length check removed: caught by test_a_failing_build_changes_nothing, test_an_overlong_description_without_override_fails, test_an_overlong_nested_description_fails, test_an_overlong_override_fails (Ran 38, FAILED (failures=4))
sk9 stale-override check removed (override kept after upstream shortened): caught by test_an_override_of_a_description_within_the_limit_fails (Ran 38, FAILED (failures=1))
sk10 read-back check of the override removed: caught by test_an_override_that_yaml_does_not_read_back_fails (Ran 38, FAILED (failures=1))
sk11 commit check skipped: caught by test_a_wrong_commit_exits_2_with_the_fix, test_the_source_must_be_at_the_locked_commit (Ran 38, FAILED (failures=3))
sk12 excluded skill copied: caught by test_build_prints_a_short_summary, test_check_lists_every_difference, test_check_of_a_missing_output_lists_every_file, test_check_passes_on_a_fresh_build_and_ignores_the_adapter, test_exactly_the_listed_skills_and_top_level_files_are_copied, test_writes_the_rendered_tree_and_returns_its_paths (Ran 38, FAILED (failures=6))
sk13 upstream entries not accounted for (new NOTICE / skill ignored): caught by test_an_excluded_entry_upstream_no_longer_has_fails, test_an_upstream_entry_neither_imported_nor_excluded_fails (Ran 38, FAILED (failures=2))
sk14 root SKILL.md check removed: caught by test_a_skill_without_skill_md_at_its_root_fails (Ran 38, FAILED (failures=1))
sk15 link fix only checks the text is present, not the count: caught by test_a_link_fix_that_matches_a_different_number_of_times_fails (Ran 38, FAILED (failures=1))
sk16 unlisted broken link ignored: caught by test_an_unlisted_broken_link_fails (Ran 38, FAILED (failures=1))
sk17 stale allow-list entry not detected: caught by test_a_stale_allowed_link_fails (Ran 38, FAILED (failures=1))
sk18 links checked in SKILL.md files only: caught by test_which_links_count_as_broken (Ran 38, FAILED (failures=1))
sk19 #anchor not stripped from the target: caught by test_a_body_right_after_the_frontmatter_gets_the_same_blank_line, test_a_stale_allowed_link_fails, test_build_prints_a_short_summary, test_building_twice_gives_identical_bytes, test_check_lists_every_difference, test_check_of_a_missing_output_lists_every_file, test_check_passes_on_a_fresh_build_and_ignores_the_adapter, test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream, test_exactly_the_listed_skills_and_top_level_files_are_copied, test_keeps_other_entries_and_removes_stale_files_inside_the_copies, test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint, test_lists_every_imported_skill_with_its_files_bytes_and_version, test_other_files_are_byte_identical, test_records_the_source_and_every_change, test_rendering_twice_gives_identical_bytes, test_the_files_come_from_the_commit_not_the_working_tree, test_the_link_fix_is_applied, test_the_overridden_skill_md_gets_the_hint_too, test_the_override_is_a_folded_block_at_upstreams_indentation, test_the_override_replaces_only_the_description, test_which_links_count_as_broken, test_writes_the_rendered_tree_and_returns_its_paths (Ran 38, FAILED (failures=4, errors=18))
sk20 a link to a folder counts as broken: caught by test_a_body_right_after_the_frontmatter_gets_the_same_blank_line, test_build_prints_a_short_summary, test_building_twice_gives_identical_bytes, test_check_lists_every_difference, test_check_of_a_missing_output_lists_every_file, test_check_passes_on_a_fresh_build_and_ignores_the_adapter, test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream, test_exactly_the_listed_skills_and_top_level_files_are_copied, test_keeps_other_entries_and_removes_stale_files_inside_the_copies, test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint, test_lists_every_imported_skill_with_its_files_bytes_and_version, test_other_files_are_byte_identical, test_records_the_source_and_every_change, test_rendering_twice_gives_identical_bytes, test_the_files_come_from_the_commit_not_the_working_tree, test_the_link_fix_is_applied, test_the_overridden_skill_md_gets_the_hint_too, test_the_override_is_a_folded_block_at_upstreams_indentation, test_the_override_replaces_only_the_description, test_which_links_count_as_broken, test_writes_the_rendered_tree_and_returns_its_paths (Ran 38, FAILED (failures=3, errors=18))
sk21 build wipes the output folder (the adapter goes too): caught by test_keeps_other_entries_and_removes_stale_files_inside_the_copies (Ran 38, FAILED (errors=1))
sk22 build prunes stale files in the whole output folder: caught by test_keeps_other_entries_and_removes_stale_files_inside_the_copies (Ran 38, FAILED (errors=1))
sk23 build leaves stale files: caught by test_keeps_other_entries_and_removes_stale_files_inside_the_copies (Ran 38, FAILED (failures=1))
sk24 --check ignores differs: caught by test_check_lists_every_difference (Ran 38, FAILED (failures=1))
sk25 --check reports the adapter and other files as extra: caught by test_check_lists_every_difference, test_check_passes_on_a_fresh_build_and_ignores_the_adapter (Ran 38, FAILED (failures=2))
sk26 the override wrapped at hyphens: caught by test_a_body_right_after_the_frontmatter_gets_the_same_blank_line, test_a_skill_md_without_frontmatter_fails, test_a_stale_allowed_link_fails, test_an_overlong_nested_description_fails, test_an_override_of_a_description_within_the_limit_fails, test_an_unlisted_broken_link_fails, test_build_prints_a_short_summary, test_building_twice_gives_identical_bytes, test_check_lists_every_difference, test_check_of_a_missing_output_lists_every_file, test_check_passes_on_a_fresh_build_and_ignores_the_adapter, test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream, test_exactly_the_listed_skills_and_top_level_files_are_copied, test_keeps_other_entries_and_removes_stale_files_inside_the_copies, test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint, test_lists_every_imported_skill_with_its_files_bytes_and_version, test_other_files_are_byte_identical, test_records_the_source_and_every_change, test_rendering_twice_gives_identical_bytes, test_the_files_come_from_the_commit_not_the_working_tree, test_the_link_fix_is_applied, test_the_overridden_skill_md_gets_the_hint_too, test_the_override_is_a_folded_block_at_upstreams_indentation, test_the_override_replaces_only_the_description, test_writes_the_rendered_tree_and_returns_its_paths (Ran 38, FAILED (failures=7, errors=18))
sk27 files read from the clone's working tree: caught by test_the_files_come_from_the_commit_not_the_working_tree (Ran 38, FAILED (failures=1))
sk28 UPSTREAM.md NOTICE sentence inverted: caught by test_records_the_source_and_every_change (Ran 38, FAILED (failures=1))
sk29 a build error exits 1 like a --check difference: caught by test_a_wrong_commit_exits_2_with_the_fix (Ran 38, FAILED (failures=2))
sk30 check-secrets: aws_secret_access_key no longer checked (a real value passes): caught by a quoted aws_secret_access_key without spaces fails the check, a real-looking aws_secret_access_key fails the check (2 failed)
sk31 check-secrets: only a quoted aws_secret_access_key value is checked: caught by a real-looking aws_secret_access_key fails the check (1 failed)
sk32 check-secrets: spaces after = exempt the value: caught by a real-looking aws_secret_access_key fails the check (1 failed)
sk33 check-secrets: back to the old pattern (placeholders flagged): caught by placeholder '"<secret>"' after aws_secret_access_key is not a hit, placeholder '${AWS_SECRET_ACCESS_KEY}' after aws_secret_access_key is not a hit, placeholder '' after aws_secret_access_key is not a hit, placeholder '...' after aws_secret_access_key is not a hit, placeholder '<secret>' after aws_secret_access_key is not a hit (5 failed)
sk34 check-secrets: the LEAK line prints the matching line: caught by never prints the aws_secret_access_key value (1 failed)
34/34 mutations caught; tree unchanged: True
rc=0
st1 a nested SKILL.md without the hint: caught by test_every_copied_skill_md_starts_with_the_adapter_hint (Ran 9, FAILED (failures=1, skipped=2))
st2 no blank line after the hint: caught by test_every_copied_skill_md_starts_with_the_adapter_hint (Ran 9, FAILED (failures=1, skipped=2))
st3 the hint twice: caught by test_every_copied_skill_md_starts_with_the_adapter_hint (Ran 9, FAILED (failures=1, skipped=2))
st4 top-level name differs from the folder: caught by test_every_copy_has_a_skill_md_within_quicks_limits (Ran 9, FAILED (failures=1, skipped=2))
st5 description over 1024 characters: caught by test_every_copy_has_a_skill_md_within_quicks_limits, test_the_overrides_are_the_builders (Ran 9, FAILED (failures=2, skipped=2))
st6 UPSTREAM.md built from another commit: caught by test_licence_contract_and_provenance (Ran 9, FAILED (failures=1, skipped=2))
st7 an override trigger dropped (Pre-Flight Checklist): caught by test_the_overrides_are_the_builders, test_the_shortened_descriptions_keep_their_triggers (Ran 9, FAILED (failures=2, skipped=2))
st8 the committed override drifted from the builder's: caught by test_the_overrides_are_the_builders (Ran 9, FAILED (failures=1, skipped=2))
st9 a new broken link: caught by test_every_relative_link_in_the_copies_resolves_or_is_allowed (Ran 9, FAILED (failures=1, skipped=2))
st10 an allowed broken link that resolves now (allow-list stale): caught by test_every_relative_link_in_the_copies_resolves_or_is_allowed (Ran 9, FAILED (failures=1, skipped=2))
st11 frontmatter that is not valid YAML: caught by test_every_copied_skill_md_starts_with_the_adapter_hint, test_every_copy_has_a_skill_md_within_quicks_limits (Ran 9, FAILED (errors=2, skipped=2))
11/11 mutations caught; tree unchanged: True
rc=0
quick/skills matches 0476f3b84ade (119 files)
exit=0
```

- [ ] **Step 6：收尾，提交**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - T5.1 <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
echo 'Task 1（T5.1）已完成；Task 2（T5.2）从 Step 1 开始' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo 'Task 2（T5.2 adapter + 指令），然后 Task 3（T5.7a 代码）、Task 4（T5.7b）、Task 5（demo-check / cleanup 脚本）、Task 6（部署，GATE）、Task 7（整体评审，再交给用户导入 skill 和彩排 2 轮）、Task 8（T5.5）、Task 9（演示结束后清理，GATE）' | .venv/bin/python /tmp/p5-progress.py state 下一步
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 1（T5.1）：skills 副本和 `check-secrets.sh` 的占位符

- `scripts/build_skills.py`：从 apache/doris-skills `0476f3b`（2026-09-23）的 git 对象生成 `quick/skills/` 的 4 个副本和 `LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md`，共 119 个文件、566278 字节，整棵树 sha256 `db3ca57c…`。`doris-repo-review` 不导入。
- 改动全部是常量：14 个 `SKILL.md` 的提示行；2 个 description 缩写（1328 → 975、1307 → 978，触发词全部保留）；1 处链接修正（`03-case-index.md` → `03-cir-case-index.md`，3 次）；4 个允许的断链（示例路径）；可执行位不保留。upstream 新增或删除内容、常量过期，构建都会停下来。
- `check-secrets.sh` 的 secret-key 规则不再把占位符（`<…>`、`${…}`、`...`、空值）当成泄漏，真实形状的值仍然命中；`doris-debug/data-lake/SKILL.md` 的 S3 示例因此不会让提交失败。
- RED：`scripts/test`、`quick/test` 各 1 个 `ERROR`（`build_skills` 还不存在）；`test-check-secrets.sh` 5 个 `FAIL`（占位符被当成泄漏），真实值的 3 项已经通过。
- GREEN：`scripts/test` 113、`quick/test` 25（2 个 adapter 检查 skip，Task 2 去掉）、`doris/test` 161、`test_agentcore_*.py` 89、6 组 shell 全部通过（check-secrets 20 个）；突变 sk 34/34、st 11/11 被抓到，工作区恢复原样，`--check` 仍然一致。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add scripts/build_skills.py scripts/test/test_build_skills.py quick/skills quick/test/test_skills.py \
        scripts/check-secrets.sh scripts/test/test-check-secrets.sh specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
feat(p5): T5.1 quick/skills copies of apache/doris-skills 0476f3b from scripts/build_skills.py; check-secrets placeholders

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望（实测）：
```
ticked: T5.1
进行中: written (735 lines)
下一步: written (735 lines)
### 2026-09-28 P5 Task 1（T5.1）：skills 副本和 `check-secrets.sh` 的占位符: written (743 lines)
check-secrets: OK (839 files scanned)
0
feat(p5): T5.1 quick/skills copies of apache/doris-skills 0476f3b from scripts/build_skills.py; check-secrets placeholders
```
日志里的数字如果和实测不同，写实测值。

---

### Task 2：T5.2 adapter skill、指令第 5 条和时间口径、对账 case

来源：design §8.3（翻译表）、§9 的步骤 3（adapter）和 §8.2（指令），tasks.md T5.2；P4 遗留的「日期过滤假设」和「指令里的时间粒度」。spec 阶段的发现：

| # | spec 阶段的发现 | 处理 | 测试 |
|---|---|---|---|
| 1 | 副本用到的 doriscli 命令和 flag（`CLI-CONTRACT.md` 列的，加上 SKILL.md 正文里出现的 `profile diff` / `profile history` / `tablet --detail` 等）在 Quick 里都没有 | adapter 的「doriscli command map」逐条翻译成 `doris___*` 工具或 SQL；没有对应的（FE / BE HTTP、日志）写明「交给人」| `CommandMap` 5 个（逐条对照 `CLI-CONTRACT.md` 和副本正文）|
| 2 | `SET k = v` 被 server 拒绝（只读校验）| 翻译成 `/*+SET_VAR(k=v)*/` 提示 | `test_set_is_a_hint_not_a_statement` |
| 3 | 带 profile 执行：server 没有 `--profile` 参数 | 4 步：`SET_VAR(enable_profile=true)` + 随机 trace 注释 → `list_recent_queries(sql_contains=…)` → `get_query_profile`；`max_chars` 取 server 接受的范围（1000–200000）| `ProfileRecipe` 4 个 |
| 4 | 经 MCP 实测：`SHOW TABLETS`、`SHOW PROC` 被 Doris 拒绝，`SHOW DATA SKEW`、`SHOW TABLE STATS` 等可用 | adapter 写明哪些能用、哪些被拒绝；被拒绝的不换写法重试，说明缺了哪项证据 | `Boundaries` 4 个 |
| 5 | P4 的「9 月 1–25 日同比」取到的是整月：经 `demo_ro` 实测，MetricFlow 把时间过滤对齐到分组粒度（按月分组时 `BETWEEN '2026-09-01' AND '2026-09-25'` 取整月；`reconcile` 的 `yoy_2026` 依赖这一点）| 不改 server；指令写明「对齐到分组粒度」，「同期同天数」按天分组、逐日相加后再算同比；对账加 `yoy_same_days_2026_09`（9 月 1–24 日，避开 25 日的实时订单）| `test_filters_follow_the_grain_and_the_same_days_are_compared_by_day`、`test_the_same_days_comparison_is_a_reconcile_case`；Step 5 在线对账 12/12 |
| 6 | 用 OR 连接几个时间范围：旧 server 报 Doris 语法错误，agent 会换写法反复重试 | 指令写明一次调用只写一个时间范围（server 侧在 Task 3 改成明确的编译错误）| `test_one_time_range_per_call_and_no_or` |
| 7 | Quick 不一定会自动选中 adapter | 指令加第 5 条：诊断类问题先加载 `doris-mcp-adapter`；每个副本 SKILL.md 的第一行也指向它（Task 1）；Task 7 的 A5 实测 | `test_diagnosis_uses_the_skills_through_the_adapter`、`test_the_hint_in_every_copy_names_this_skill` |

**Files:**
- Create: `quick/skills/doris-mcp-adapter/SKILL.md`（124 行）、`quick/test/test_adapter_skill.py`（19 个）
- Modify: `quick/agent-instructions.md`（第 5 条；演示口径改 1 行、加 3 行）、`doris/reconcile.py`（+1 个 case，共 12 个）
- Test: `quick/test/test_skills.py`（去掉 Task 1 的 skip）、`quick/test/test_agent_instructions.py`（+6）。`quick/test` 25 → 50（0 skip），`doris/test` 161 不变

**Interfaces:**
- Consumes（Task 1）：`quick/skills/CLI-CONTRACT.md`、4 个副本的 SKILL.md、`build_skills.HINT`；`bcda0f3` 的 `mcp-server/src/tools/*.py`（工具名和参数、`get_query_profile` 的 `max_chars` 范围）、`reconcile.CASES` / `Case(name, metrics, group_by, where, sql)` / `DirectBackend`。
- Produces：
  - `quick/skills/doris-mcp-adapter/`：Task 7 由用户第一个导入；
  - `quick/agent-instructions.md` 第 5 条和新的演示口径：Task 7 由用户粘贴到两个 agent；Task 7 的 `test_p5_docs.py` 检查用户指南引用的是这一版；
  - `reconcile.CASES` 12 个：Task 5 的 `demo-check.sh pre` 期望 `12/12 cases match`。

- [ ] **Step 1：写失败测试**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py quick/test/test_adapter_skill.py
.venv/bin/python /tmp/p5-extract.py t52-tests.diff /tmp/t52-tests.diff
git apply /tmp/t52-tests.diff && git status --short && git diff --shortstat
```
期望（实测）：
```
quick/test/test_adapter_skill.py -> quick/test/test_adapter_skill.py (220 lines)
t52-tests.diff -> /tmp/t52-tests.diff (107 lines)
 M quick/test/test_agent_instructions.py
 M quick/test/test_skills.py
?? quick/test/test_adapter_skill.py
 2 files changed, 36 insertions(+), 10 deletions(-)
```

`test_adapter_skill.py` 从真实文件取对照：命令和 flag 取自 `CLI-CONTRACT.md` 和副本正文，工具名取自 `mcp-server/src/tools/` 注册的工具（经 Gateway 的名字是 `doris___<tool>`），`max_chars` 的范围取自 `profile.py`。它覆盖：
- `Frontmatter`（3）：name 等于文件夹名；description ≤ 1024 并说明用途；每个副本的提示行指向这个 skill。
- `CommandMap`（5）：`CLI-CONTRACT.md` 的每个命令和 flag、副本正文用到的每个 doriscli 命令都有一行翻译；`doriscli tablet` 换成 4 条表级语句；`SET` 是提示不是语句；副本用到的 FE HTTP 路径都有翻译。
- `ProfileRecipe`（4）：带 profile 执行再找回来；截断、`mode="full"`、找不到 profile；`max_chars` 的值 server 都接受；profile 文本的各节代替 doriscli 的 JSON 字段。
- `Boundaries`（4）：能用和被拒绝的语句；写操作和管理操作交给人；60 s 限制和怎么避开；先有证据、不复述连接信息。
- `Hygiene`（3）：提到的每个工具都存在且全部列出；工具名都带 `doris___` 前缀；没有 URL、IP、ARN、账号 ID。

新文件 `quick/test/test_adapter_skill.py`：

<!-- file: quick/test/test_adapter_skill.py sha256=3f3225cfe714b35f025b38ca4241850611844b40766fa3b8acb6969188f6785e -->
```python
"""quick/skills/doris-mcp-adapter/SKILL.md: how the doris-* skills reach Doris in Quick (P5 / T5.2).

The imported doris-* skills are written for doriscli; every one of their SKILL.md files starts with a hint that
points here. These checks keep the adapter complete and honest: every command and flag of upstream's doriscli
contract and every doriscli command the copies use is mapped, the tool names are the ones behind the Gateway,
the profile recipe uses parameters the server accepts, the read-only boundary and the 60-second limit are
stated, and nothing that must not leave the repo is in it.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "quick" / "skills"
ADAPTER = SKILLS / "doris-mcp-adapter" / "SKILL.md"
CONTRACT = SKILLS / "CLI-CONTRACT.md"  # copied unmodified from apache/doris-skills (T5.1)
UPSTREAM_SKILLS = ("doris-architecture-advisor", "doris-best-practices", "doris-debug", "doris-profile-reader")
GATEWAY_PREFIX = "doris___"  # <target>___<tool>, design §4.5
DESCRIPTION_LIMIT = 1024  # characters; Quick skills
MAX_CHARS_RANGE = (1000, 200000)  # get_query_profile, mcp-server/src/tools/profile.py


def _text() -> str:
    return ADAPTER.read_text(encoding="utf-8")


def _frontmatter() -> dict:
    match = re.match(r"---\n(.*?)\n---\n", _text(), re.S)
    if match is None:
        raise AssertionError("no YAML frontmatter")
    return yaml.safe_load(match.group(1))


def _section(title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", _text(), re.M | re.S)
    if match is None:
        raise AssertionError(f"no section '## {title}'")
    return match.group(1)


def _words(title: str) -> str:
    """A section with its line breaks and indentation folded to single spaces."""
    return " ".join(_section(title).split())


def _map_rows() -> list[str]:
    """The rows of the command map table, header and rule excluded."""
    return [line for line in _section("doriscli command map").splitlines()
            if line.startswith("| ") and not line.startswith("| The skill says")]


def _has_flag(flag: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text) is not None


def _contract_commands() -> list[tuple[str | None, list[str]]]:
    """(command, flags) per row of the contract's Commands table; command None for the global flags row."""
    section = re.search(r"^## Commands\n(.*?)(?=^## )", CONTRACT.read_text(encoding="utf-8"), re.M | re.S)
    rows = []
    for line in section.group(1).splitlines():
        if not line.startswith("| ") or line.startswith("| Command"):
            continue
        cell = line.split("|")[1]
        codes = re.findall(r"`([^`]+)`", cell)
        if cell.strip().startswith("global"):
            rows.append((None, [c.split()[0] for c in codes]))
        else:
            rows.append((re.match(r"doriscli(?: [a-z]+)*", codes[0]).group(0), [c.split()[0] for c in codes[1:]]))
    return rows


def _gateway_tools() -> set[str]:
    calls = json.loads((ROOT / "scripts" / "smoke_calls.json").read_text(encoding="utf-8"))
    return {GATEWAY_PREFIX + c["tool"] for c in calls}


class Frontmatter(unittest.TestCase):
    def test_name_is_the_folder_name(self):
        self.assertEqual(_frontmatter()["name"], ADAPTER.parent.name)

    def test_description_fits_and_names_what_it_is_for(self):
        description = _frontmatter()["description"]
        self.assertLessEqual(len(description), DESCRIPTION_LIMIT)
        for term in (*UPSTREAM_SKILLS, "doriscli", f"{GATEWAY_PREFIX}*", "read-only", "60-second"):
            self.assertIn(term, description)

    def test_the_hint_in_every_copy_names_this_skill(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_skills import HINT  # noqa: E402  (the line T5.1 puts into every copied SKILL.md)
        self.assertIn(f"`{_frontmatter()['name']}`", HINT)


class CommandMap(unittest.TestCase):
    def test_every_contract_command_and_flag_is_mapped(self):
        rows = _map_rows()
        contract = _contract_commands()
        self.assertGreaterEqual(len(contract), 8)
        for command, flags in contract:
            mine = rows if command is None else [r for r in rows if command in r]
            with self.subTest(command=command):
                self.assertTrue(mine, f"{command} is not mapped")
                for flag in flags:
                    self.assertTrue(any(_has_flag(flag, r) for r in mine), f"{command} {flag} is not mapped")

    def test_every_doriscli_command_the_copies_use_is_mapped(self):
        verbs = {"sql", "profile", "tablet", "auth", "use"}
        used = set()
        for skill in UPSTREAM_SKILLS:
            for path in (SKILLS / skill).rglob("*.md"):
                for words in re.findall(r"doriscli ((?:[a-z]+ ?){1,2})", path.read_text(encoding="utf-8")):
                    words = words.split()
                    if words[0] in verbs:
                        used.add(" ".join(words[:2] if words[0] in {"profile", "auth"} else words[:1]))
        self.assertGreaterEqual(used, {"sql", "profile get", "profile list", "profile diff", "profile history",
                                       "tablet", "auth status"})
        rows = "\n".join(_map_rows())
        for command in sorted(used):
            with self.subTest(command=command):
                self.assertIn(command if command.startswith("auth add") else f"doriscli {command}", rows)

    def test_doriscli_tablet_becomes_the_table_statements(self):
        # Track B (doris-best-practices) collects its table evidence with doriscli tablet.
        row = next((r for r in _map_rows() if r.startswith("| `doriscli tablet <db.t>` |")), "")
        for statement in ("SHOW CREATE TABLE", "SHOW PARTITIONS", "SHOW DATA SKEW", "SHOW TABLE STATS"):
            self.assertIn(statement, row)

    def test_set_is_a_hint_not_a_statement(self):
        rows = "\n".join(_map_rows())
        self.assertIn("/*+SET_VAR(k=v)*/", rows)
        self.assertIn("`SET` statements are rejected", rows)

    def test_the_fe_http_paths_the_skills_use_are_mapped(self):
        rows = "\n".join(_map_rows())
        for path, tool in (("/rest/v2/manager/query/query_info", "list_recent_queries"),
                           ("/rest/v2/manager/query/profile/text/", "get_query_profile")):
            row = next((r for r in _map_rows() if path in r), "")
            self.assertIn(GATEWAY_PREFIX + tool, row, path)
        self.assertIn("any other FE / BE HTTP call", rows)


class ProfileRecipe(unittest.TestCase):
    def test_run_with_a_profile_and_find_it_again(self):
        recipe = _words("Run a query with a profile")
        for term in ("/*+SET_VAR(enable_profile=true)*/", "/* trace:", f"{GATEWAY_PREFIX}list_recent_queries",
                     "sql_contains=", f"{GATEWAY_PREFIX}get_query_profile", "query_id"):
            self.assertIn(term, recipe)

    def test_truncation_full_mode_and_a_missing_profile(self):
        recipe = _words("Run a query with a profile")
        for term in ("truncated: true", "max_chars=60000", 'mode="full"', "profile_found: false"):
            self.assertIn(term, recipe)

    def test_max_chars_values_are_accepted_by_the_server(self):
        values = [int(v) for v in re.findall(r"max_chars=(\d+)", _text())]
        self.assertTrue(values)
        for value in values:
            self.assertTrue(MAX_CHARS_RANGE[0] <= value <= MAX_CHARS_RANGE[1], value)

    def test_the_profile_text_sections_replace_the_json_fields(self):
        text = _section("doriscli command map")
        for term in ("`Summary:`", "`Execution Summary:`", "`MergedProfile:`", "`PhysicalPlan:`", "profile_text"):
            self.assertIn(term, text)


class Boundaries(unittest.TestCase):
    def test_what_works_and_what_is_denied(self):
        sql = _words("SQL that works and SQL that does not")
        for term in ("SHOW CREATE TABLE", "SHOW DATA SKEW", "SHOW PROCESSLIST", "EXPLAIN",
                     "SHOW TABLETS", "SHOW PROC", "1105", "CONNECTION_ERROR", "try it once", "do not retry"):
            self.assertIn(term, sql)

    def test_writes_and_admin_actions_are_handed_to_a_person(self):
        writes = _words("Writes and admin actions")
        never, found, _ = writes.partition("Never run ")[2].partition(". When")  # the list, up to the next sentence
        self.assertTrue(found)
        for term in ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE", "KILL", "ADMIN",
                     "SET GLOBAL"):
            self.assertIn(f"`{term}", never)
        self.assertIn("a person runs it", writes)

    def test_the_60_second_limit_and_how_to_stay_under_it(self):
        limit = _words("The 60-second limit")
        for term in ("EXPLAIN", "LIMIT", "424", "retry once"):
            self.assertIn(term, limit)
        self.assertIn("60 s", _words("The environment"))

    def test_evidence_first_and_no_connection_details(self):
        evidence = _words("Evidence first")
        for term in ("tool result", "evidence gates", "host names", "IP addresses", "URLs"):
            self.assertIn(term, evidence)


class Hygiene(unittest.TestCase):
    def test_every_tool_named_exists_behind_the_gateway_and_all_are_listed(self):
        tools = _gateway_tools()
        self.assertEqual(len(tools), 12)
        named = set(re.findall(rf"\b{GATEWAY_PREFIX}\w+", _text()))
        self.assertEqual(named, tools)

    def test_every_tool_name_has_the_gateway_prefix(self):
        bare = {t[len(GATEWAY_PREFIX):] for t in _gateway_tools()}
        text = re.sub(rf"\b{GATEWAY_PREFIX}\w+", "", _text())
        self.assertEqual({t for t in bare if re.search(rf"\b{t}\b", text)}, set())

    def test_no_urls_addresses_arns_or_account_ids(self):
        text = _text()
        for pattern in (r"https?://", r"\b\d{1,3}(?:\.\d{1,3}){3}\b", r"\barn:aws", r"\b\d{12}\b",
                        r"amazonaws\.com"):
            self.assertIsNone(re.search(pattern, text), pattern)


if __name__ == "__main__":
    unittest.main()
```

`test_skills.py` 去掉 skip，`test_agent_instructions.py` 加 6 个（第 5 条、5 个时间粒度、对齐到分组粒度和同期同天数、不用 OR、对账 case 存在且和指令一致、提到的每个 skill 都在 `quick/skills/`）：

<!-- file: t52-tests.diff sha256=dc83cf36fe66be57c2767e6cf03650a0e9632075723872eaa8ad2c1a78796e59 -->
```diff
diff --git a/quick/test/test_skills.py b/quick/test/test_skills.py
index 4141134..907614c 100644
--- a/quick/test/test_skills.py
+++ b/quick/test/test_skills.py
@@ -47,13 +47,6 @@ TRIGGERS = {
 }
 
 
-def _skip_until_the_adapter_lands(test: unittest.TestCase) -> None:
-    """TEMPORARY: quick/skills/doris-mcp-adapter/ is written by another P5 task. Delete this helper and its calls
-    once that folder is committed."""
-    if not (SKILLS_DIR / ADAPTER / "SKILL.md").is_file():
-        test.skipTest(f"quick/skills/{ADAPTER}/SKILL.md is not written yet")
-
-
 def _split(path: Path) -> tuple[dict, str]:
     """(frontmatter as parsed YAML, body) of a SKILL.md: the YAML between the first line `---` and the next."""
     text = path.read_text(encoding="utf-8")
@@ -75,7 +68,6 @@ class Layout(unittest.TestCase):
         self.assertEqual(_folders() - {ADAPTER}, set(build_skills.SKILLS))
 
     def test_exactly_the_five_skill_folders(self):
-        _skip_until_the_adapter_lands(self)
         self.assertEqual(_folders(), FOLDERS)
 
     def test_licence_contract_and_provenance(self):
@@ -103,7 +95,6 @@ class SkillFolders(unittest.TestCase):
                 self._check(folder)
 
     def test_the_adapter_has_a_skill_md_within_quicks_limits(self):
-        _skip_until_the_adapter_lands(self)
         self._check(ADAPTER)
 
 
diff --git a/quick/test/test_agent_instructions.py b/quick/test/test_agent_instructions.py
index de43a62..3702df4 100644
--- a/quick/test/test_agent_instructions.py
+++ b/quick/test/test_agent_instructions.py
@@ -18,11 +18,12 @@ from pathlib import Path
 
 ROOT = Path(__file__).resolve().parents[2]
 sys.path.insert(0, str(ROOT / "doris"))
-from reconcile import MODELS_DIR, Case, DirectBackend, ReconcileError  # noqa: E402  (compiles like the server's query_metric)
+from reconcile import CASES, MODELS_DIR, Case, DirectBackend, ReconcileError  # noqa: E402  (compiles like the server's query_metric)
 
 INSTRUCTIONS = ROOT / "quick" / "agent-instructions.md"
 QUICK_LIMIT = 50_000  # characters; design §4.4
 GATEWAY_PREFIX = "doris___"  # <target>___<tool>, design §4.5
+GRAINS = ("day", "week", "month", "quarter", "year")  # metric_time__<grain>; every one compiles (SemanticLayer)
 
 
 def _text() -> str:
@@ -93,6 +94,27 @@ class Rules(unittest.TestCase):
                      "metric_time BETWEEN '2026-01-01' AND '2026-09-25'"):
             self.assertIn(term, framing)
 
+    def test_every_time_grain_of_metric_time_is_named(self):
+        framing = _section("演示口径")
+        for grain in GRAINS:
+            self.assertIn(f"`metric_time__{grain}`", framing)
+
+    def test_filters_follow_the_grain_and_the_same_days_are_compared_by_day(self):
+        framing = _section("演示口径")
+        for term in ("对齐到分组粒度", "整月", "同期同天数", "group_by `metric_time__day`", "相加"):
+            self.assertIn(term, framing)
+
+    def test_one_time_range_per_call_and_no_or(self):
+        framing = _section("演示口径")
+        for term in ("一次调用只写一个时间范围", "OR"):
+            self.assertIn(term, framing)
+
+    def test_diagnosis_uses_the_skills_through_the_adapter(self):
+        rules = _section("硬约束")
+        for term in ("doris-mcp-adapter", "doris-debug", "doris-profile-reader", "doris-best-practices",
+                     "doris-architecture-advisor", "doriscli"):
+            self.assertIn(term, rules)
+
     def test_ratios_are_fractions_and_a_zero_yoy_means_no_data(self):
         framing = _section("演示口径")
         for term in ("mini_program_share", "0~1", "无数据"):
@@ -126,6 +148,12 @@ class SemanticLayer(unittest.TestCase):
                 except ReconcileError as e:
                     self.fail(f"group_by {dimension}: {e}")
 
+    def test_the_same_days_comparison_is_a_reconcile_case(self):
+        # The same-days recipe in 演示口径 is checked against hand-written SQL on the cluster by reconcile.py.
+        case = next((c for c in CASES if c.name == "yoy_same_days_2026_09"), None)
+        self.assertIsNotNone(case)
+        self.assertEqual((case.metrics, case.group_by), (("gmv", "gmv_last_year"), ("metric_time__day",)))
+
 
 class Hygiene(unittest.TestCase):
     def test_every_tool_named_exists_behind_the_gateway(self):
@@ -141,6 +169,13 @@ class Hygiene(unittest.TestCase):
         text = re.sub(rf"\b{GATEWAY_PREFIX}\w+", "", _text())
         self.assertEqual({t for t in bare if re.search(rf"\b{t}\b", text)}, set())
 
+    def test_every_skill_named_is_in_quick_skills(self):
+        named = set(re.findall(r"\bdoris-[a-z]+(?:-[a-z]+)*", _text()))
+        self.assertTrue(named)
+        for name in sorted(named):
+            with self.subTest(skill=name):
+                self.assertTrue((ROOT / "quick" / "skills" / name / "SKILL.md").is_file())
+
     def test_no_urls_addresses_arns_or_account_ids(self):
         text = _text()
         for pattern in (r"https?://", r"\b\d{1,3}(?:\.\d{1,3}){3}\b", r"\barn:aws", r"\b\d{12}\b",
```

- [ ] **Step 2：确认失败**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s quick/test > /tmp/t52-red.log 2>&1; echo "rc=$?"
grep -E '^(FAIL|ERROR):' /tmp/t52-red.log | sed -E 's/^(FAIL|ERROR): (test_[a-z0-9_]+) \(([a-z_]+)\.([A-Za-z]+).*/\1 \3.\4.\2/' | sort
grep -E '^Ran |^OK|^FAILED' /tmp/t52-red.log
```
期望（实测）：
```
rc=1
ERROR test_adapter_skill.Boundaries.test_evidence_first_and_no_connection_details
ERROR test_adapter_skill.Boundaries.test_the_60_second_limit_and_how_to_stay_under_it
ERROR test_adapter_skill.Boundaries.test_what_works_and_what_is_denied
ERROR test_adapter_skill.Boundaries.test_writes_and_admin_actions_are_handed_to_a_person
ERROR test_adapter_skill.CommandMap.test_doriscli_tablet_becomes_the_table_statements
ERROR test_adapter_skill.CommandMap.test_every_contract_command_and_flag_is_mapped
ERROR test_adapter_skill.CommandMap.test_every_doriscli_command_the_copies_use_is_mapped
ERROR test_adapter_skill.CommandMap.test_set_is_a_hint_not_a_statement
ERROR test_adapter_skill.CommandMap.test_the_fe_http_paths_the_skills_use_are_mapped
ERROR test_adapter_skill.Frontmatter.test_description_fits_and_names_what_it_is_for
ERROR test_adapter_skill.Frontmatter.test_name_is_the_folder_name
ERROR test_adapter_skill.Frontmatter.test_the_hint_in_every_copy_names_this_skill
ERROR test_adapter_skill.Hygiene.test_every_tool_name_has_the_gateway_prefix
ERROR test_adapter_skill.Hygiene.test_every_tool_named_exists_behind_the_gateway_and_all_are_listed
ERROR test_adapter_skill.Hygiene.test_no_urls_addresses_arns_or_account_ids
ERROR test_adapter_skill.ProfileRecipe.test_max_chars_values_are_accepted_by_the_server
ERROR test_adapter_skill.ProfileRecipe.test_run_with_a_profile_and_find_it_again
ERROR test_adapter_skill.ProfileRecipe.test_the_profile_text_sections_replace_the_json_fields
ERROR test_adapter_skill.ProfileRecipe.test_truncation_full_mode_and_a_missing_profile
ERROR test_skills.SkillFolders.test_the_adapter_has_a_skill_md_within_quicks_limits
FAIL test_agent_instructions.Hygiene.test_every_skill_named_is_in_quick_skills
FAIL test_agent_instructions.Rules.test_diagnosis_uses_the_skills_through_the_adapter
FAIL test_agent_instructions.Rules.test_every_time_grain_of_metric_time_is_named
FAIL test_agent_instructions.Rules.test_filters_follow_the_grain_and_the_same_days_are_compared_by_day
FAIL test_agent_instructions.Rules.test_one_time_range_per_call_and_no_or
FAIL test_agent_instructions.SemanticLayer.test_the_same_days_comparison_is_a_reconcile_case
FAIL test_skills.Layout.test_exactly_the_five_skill_folders
Ran 50 tests in 0.149s
FAILED (failures=7, errors=20)
```
失败的正是 Step 3 要做的（Step 1 去掉了 `test_skills.py` 里临时的 `_skip_until_the_adapter_lands`，原来 skip 的 2 个检查现在直接失败）：
- 20 个 `ERROR`：`test_adapter_skill` 的 19 个检查和 `test_skills.SkillFolders` 的 adapter 检查都读 `quick/skills/doris-mcp-adapter/SKILL.md`，它还不存在。
- 7 个 `FAIL`：`test_skills.Layout` 要 5 个 skill 目录，现在只有 4 个；`test_agent_instructions` 的 6 个：指令里还没有第 5 条（没有点名任何 `doris-*` skill，也没有先加载 adapter 的要求），演示口径还没有 5 个时间粒度、「时间过滤对齐到分组粒度」「同期同天数按天分组」「一次调用一个时间范围，不用 OR」，`reconcile.py` 还没有 `yoy_same_days_2026_09`。

失败的项目或个数不同时，先查明原因，不要进入 Step 3。

- [ ] **Step 3：实现 adapter、指令和对账 case**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py quick/skills/doris-mcp-adapter/SKILL.md
.venv/bin/python /tmp/p5-extract.py t52-impl.diff /tmp/t52-impl.diff
git apply /tmp/t52-impl.diff && git status --short && git diff --shortstat
.venv/bin/python scripts/build_skills.py --source /tmp/doris-skills --check; echo "exit=$?"
```
期望（实测）：
```
quick/skills/doris-mcp-adapter/SKILL.md -> quick/skills/doris-mcp-adapter/SKILL.md (124 lines)
t52-impl.diff -> /tmp/t52-impl.diff (47 lines)
 M doris/reconcile.py
 M quick/agent-instructions.md
 M quick/test/test_agent_instructions.py
 M quick/test/test_skills.py
?? quick/skills/doris-mcp-adapter/
?? quick/test/test_adapter_skill.py
 4 files changed, 52 insertions(+), 12 deletions(-)
quick/skills matches 0476f3b84ade (119 files)
exit=0
```
`--check` 仍然一致：它只比较生成的路径，adapter 不算。

新文件 `quick/skills/doris-mcp-adapter/SKILL.md`：

<!-- file: quick/skills/doris-mcp-adapter/SKILL.md sha256=50fcc357e657a5b882188d6b4402d9581a1c2adfa6283512ed6080e9776abd3f -->
```markdown
---
name: doris-mcp-adapter
description: >
  Read this before following any doris-* skill (doris-debug, doris-profile-reader, doris-best-practices,
  doris-architecture-advisor) in this environment. There is no doriscli, no mysql client, no shell and no FE/BE
  HTTP access here: the only way to reach Doris is the Doris MCP tools (doris___*). This skill maps every doriscli
  command, session setting, SQL statement and HTTP call those skills mention to the MCP tools, and states the
  read-only boundary, the 60-second limit per call and how to run a query with a profile.
---

# Doris MCP adapter

The doris-* skills were written for `doriscli`, a Doris command-line client that is not available here. Here the
agent talks to one Apache Doris 4.1 cluster through MCP tools only. Follow the diagnostic reasoning of the doris-* skills
as written; translate every command they tell you to run with the tables below.

## The environment

- Tools are named `doris___<tool>` (the `doris___` prefix comes from the gateway). There is nothing else: no
  `doriscli`, no `mysql`, no `curl`, no shell, no FE/BE web UI, no log files, no BE HTTP (`/api/compaction/...`,
  `/metrics`, `be.conf`).
- Every tool call takes 5-10 s (each call starts a fresh server) and is cut off at 60 s. Plan the evidence you
  need, avoid calls you do not need, and put several metrics into one `doris___query_metric` call.
- The service account is read-only: SELECT, SHOW, DESCRIBE and EXPLAIN only. Writes are never executed (see
  "Writes and admin actions").
- A "fallback", "mysql client" or "native SQL" path in a skill means `doris___execute_query` here.

## Tools

| Tool | Use |
|---|---|
| `doris___check_service_health()` | connectivity and version (`doriscli auth status`) |
| `doris___list_databases()` / `doris___list_tables(database)` / `doris___describe_table(table, database)` | catalogue |
| `doris___execute_query(sql, database="", max_rows=0)` | any read-only statement (SELECT, SHOW, DESCRIBE, EXPLAIN) |
| `doris___list_recent_queries(limit=20, user="", sql_contains="")` | profiled queries, newest first, with `query_id` |
| `doris___get_query_profile(query_id, mode="summary", max_chars=20000)` | profile text of one query |
| `doris___get_query_guide()` | the server's own SQL guide |
| `doris___list_metrics` / `doris___list_dimensions_for_metric` / `doris___query_metric` | the `ecom` semantic layer (business metrics, not diagnostics) |
| `doris___reload_semantic_layer` | do not call unless the user asks |

## doriscli command map

| The skill says | Do this |
|---|---|
| `doriscli sql "<SELECT / SHOW / DESC / EXPLAIN>"` | `doris___execute_query(sql=...)`; use `max_rows` or `LIMIT` for big results |
| `doriscli sql ... --profile` | run with a profile (next section) |
| `doriscli sql ... --set k=v`, or a `SET k = v;` line before the query | put the variable into the query as a hint: `SELECT /*+SET_VAR(k=v)*/ ...` (`SET` statements are rejected) |
| `doriscli sql ... --no-cache` | add the hint `/*+SET_VAR(enable_sql_cache=false)*/` |
| `doriscli sql -f file.sql` | run the statements one by one with `doris___execute_query` |
| `doriscli profile get <qid>` | `doris___get_query_profile(query_id=qid)`; the text is in `profile_text` |
| `doriscli profile get <qid> --full` / `--raw` | `doris___get_query_profile(query_id=qid, mode="full", max_chars=100000)` |
| `doriscli profile get -f file` | the user gave the profile: read the text they pasted; no tool call |
| `doriscli profile list` (`--limit N`) | `doris___list_recent_queries(limit=N)` (default 20; only queries that were run with a profile) |
| `doriscli profile list --active` | `doris___execute_query(sql="SHOW PROCESSLIST")` |
| `doriscli profile diff <slow> <fast>` | call `doris___get_query_profile` for each id and compare the two texts yourself |
| `doriscli profile history "<pattern>"` (`--days N`, `--limit N`) | `doris___list_recent_queries(sql_contains="<pattern>", limit=100)`; there is no date filter, only profiled queries are listed and the audit log is not available, so there is no p50/p99 trend: say so |
| `doriscli tablet <db.t>` | `SHOW CREATE TABLE db.t` (model, keys, buckets, properties) + `SHOW PARTITIONS FROM db.t` + `SHOW DATA SKEW FROM db.t` + `SHOW TABLE STATS db.t` / `SHOW COLUMN STATS db.t` |
| `doriscli tablet <db.t> --detail` / `--partition p` | the same statements; for one partition `SHOW DATA SKEW FROM db.t PARTITION (p)` |
| `doriscli auth status` | `doris___check_service_health()` |
| `doriscli use <env>`, `auth add`, `--env`, `--socks5`, `--init-sql` | not needed: there is exactly one cluster |
| `--format json` | not needed: every tool returns JSON |
| FE HTTP `/rest/v2/manager/query/query_info` | `doris___list_recent_queries` |
| FE HTTP `/rest/v2/manager/query/profile/text/<qid>` | `doris___get_query_profile(query_id=qid)` |
| any other FE / BE HTTP call | not available: ask the human (see "Writes and admin actions") |

`doriscli profile get` returns parsed JSON fields (`summary.total_time_ms`, `operators[]`, `scanned_tables`, ...).
Here you get the profile text instead. Read the same facts from it: `Summary:` (`Total`, `Task State`),
`Execution Summary:` (plan and schedule times), `ChangedSessionVariables:`, `MergedProfile:` (per-operator
counters: rows, time, memory, spill, runtime filters), `Appendix:` → `PhysicalPlan:`. For the table-side fields
(`ddl`, `tablet_skew`, `total_rows`) use the SQL of the `doriscli tablet` row above.

## Run a query with a profile

Profiles are off by default. To profile one query:

1. Make a random token, e.g. `t7q2x9`.
2. `doris___execute_query(sql="SELECT /*+SET_VAR(enable_profile=true)*/ ... /* trace:t7q2x9 */")` - the hint goes
   right after `SELECT`, the comment at the end. If the query may be slow or return many rows, run `EXPLAIN` first
   and add `LIMIT` or aggregate (see "The 60-second limit").
3. `doris___list_recent_queries(sql_contains="t7q2x9", limit=5)` → take `query_id` of the newest row.
4. `doris___get_query_profile(query_id=...)`. If the result says `truncated: true`, call it again with
   `max_chars=60000`; use `mode="full"` only when the skill needs per-instance detail (e.g. skew between
   instances), because the full text is much longer.

`profile_found: false` means the query ran without a profile or the profile was evicted: re-run step 2. When the
user gives a query_id, skip steps 1-3. Prefer an existing profile over re-running an expensive query.

## SQL that works and SQL that does not

Checked on this cluster through the MCP tools:

- Works: `SHOW CREATE TABLE`, `SHOW PARTITIONS`, `SHOW DATA SKEW`, `SHOW TABLE STATS`, `SHOW COLUMN STATS`,
  `SHOW INDEX`, `SHOW PROCESSLIST`, `SHOW VARIABLES`, `SHOW ALTER TABLE MATERIALIZED VIEW`, `EXPLAIN`,
  `DESCRIBE`, and `SELECT` on the databases the account can read.
- Rejected by the tool: `SET ...` (use the `SET_VAR` hint) and every write or DDL statement.
- Denied by Doris (they come back as an error, often reported as `CONNECTION_ERROR` with Doris error 1105):
  `SHOW TABLETS`, `SHOW PROC ...`.
- Anything else a skill asks for (other `SHOW` / `ADMIN SHOW` statements, `information_schema` tables): try it
  once. If it is denied, do not retry variants; say which evidence could not be collected, and continue with what
  you have or give the statement to the human (next section).

## Writes and admin actions

Never run `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `KILL`, `ADMIN SET/REPAIR ...`,
`SET GLOBAL`, `REFRESH MATERIALIZED VIEW`, config changes, restarts or BE/FE HTTP actions. When a skill's fix needs
one, write the exact statement (DDL, `ALTER`, `KILL`, config line) with the reason and the expected effect, and
say that a person runs it. Evidence a person must collect outside this environment (BE logs, `be.conf`, BE HTTP
pages, `SHOW PROC` output) is a request to the human, not something to guess.

## The 60-second limit

- For detail or large-table queries run `EXPLAIN` first; then add a `LIMIT`, a partition / time filter or an
  aggregate.
- A tool error or a Quick timeout (424) after about 60 s means the query was too big: narrow it and retry once;
  if it fails again, tell the user.
- Timing talking point: Doris itself usually answers in milliseconds (the profile's `Total`); most of the 5-10 s
  per call is starting the server. Quote the profile time, not the wall-clock time, as the query cost.

## Evidence first

Every root cause, number or recommendation must come from a tool result of this conversation (or from data the
user gave). Follow the evidence gates of the doris-* skills: collect first, then state hypotheses with the evidence
and confidence. At the end, list the tools and statements you used. Do not repeat host names, IP addresses, ports,
accounts or URLs that appear in tool results.
```

`quick/agent-instructions.md` 和 `doris/reconcile.py` 的补丁：

<!-- file: t52-impl.diff sha256=ba7461e89eae37160cf4529a122d15f10436355308dc2bdf393a5ca28e995826 -->
```diff
diff --git a/doris/reconcile.py b/doris/reconcile.py
index 51e44b4..a8e9174 100644
--- a/doris/reconcile.py
+++ b/doris/reconcile.py
@@ -93,6 +93,17 @@ CASES: tuple[Case, ...] = (
         LEFT JOIN (SELECT MONTHS_ADD(DATE_TRUNC('month', order_date), 12) AS m, SUM(pay_amount) AS gmv
                    FROM ecom.v_paid_order WHERE order_date < '2026-01-01'
                    GROUP BY MONTHS_ADD(DATE_TRUNC('month', order_date), 12)) l ON l.m = t.m"""),
+    # The same days of last year: grouped by day the filter stays 09-01..09-24 (grouped by month it widens to the
+    # whole month, as in yoy_2026). Ends at 09-24 so the live orders of 09-25 cannot make the two sides differ.
+    Case("yoy_same_days_2026_09", ("gmv", "gmv_last_year"), ("metric_time__day",),
+         "metric_time BETWEEN '2026-09-01' AND '2026-09-24'", """
+        SELECT t.d AS metric_time__day, t.gmv AS gmv, l.gmv AS gmv_last_year
+        FROM (SELECT DATE_TRUNC('day', order_date) AS d, SUM(pay_amount) AS gmv
+              FROM ecom.v_paid_order WHERE order_date BETWEEN '2026-09-01' AND '2026-09-24'
+              GROUP BY DATE_TRUNC('day', order_date)) t
+        LEFT JOIN (SELECT DATE_ADD(DATE_TRUNC('day', order_date), INTERVAL 1 YEAR) AS d, SUM(pay_amount) AS gmv
+                   FROM ecom.v_paid_order WHERE order_date BETWEEN '2025-09-01' AND '2025-09-24'
+                   GROUP BY DATE_ADD(DATE_TRUNC('day', order_date), INTERVAL 1 YEAR)) l ON l.d = t.d"""),
     Case("channel_ytd", ("gmv", "order_count"), ("order_entity__channel",), YTD, f"""
         SELECT channel AS order_entity__channel, SUM(pay_amount) AS gmv, COUNT(DISTINCT order_id) AS order_count
         FROM ecom.v_paid_order WHERE order_date {YTD_SQL} GROUP BY channel"""),
diff --git a/quick/agent-instructions.md b/quick/agent-instructions.md
index db1ec6d..e63cefc 100644
--- a/quick/agent-instructions.md
+++ b/quick/agent-instructions.md
@@ -14,15 +14,18 @@
 2. **只读。** `doris___execute_query` 只用于 SELECT、SHOW、DESCRIBE、EXPLAIN。不执行任何写操作（INSERT、UPDATE、DELETE、CREATE、ALTER、DROP、TRUNCATE），也不要为了「试一下」去执行。需要建表、改表、建物化视图时，只给出 DDL 和理由，由人工执行。
 3. **60 s 超时。** 每次工具调用最多 60 s，超时 Quick 会报 424。明细查询和大表查询先用 EXPLAIN 看计划，再加 LIMIT 或先聚合，不要一次取回成千上万行。遇到 424，把查询缩小后重试一次；仍然失败就告诉用户。
 4. **不复述连接信息。** 回答里不出现主机地址、IP、端口、账号、URL。工具结果里有这些时，概括成「Doris FE 连接正常」这样的描述。
+5. **诊断类问题用 skills。** 慢查询、Profile、表设计与建表评审、导入、Compaction、集群故障这类问题，按 doris-debug、doris-profile-reader、doris-best-practices、doris-architecture-advisor 这几个 skill 的方法做。这些 skill 是按 doriscli 写的：用之前先加载 doris-mcp-adapter，按它把命令换成 `doris___*` 工具；它们要求的写操作、KILL、改配置，照第 2 条只给出语句和理由。
 
 ## 演示口径
 
 - 演示设定：今天是 2026-09-25（中秋节），现在是 12:00。「今天」「本月」「今年」都按这个时间算，不按系统时钟。
 - 今年 = 2026，去年同期 = 2025。订单数据从 2025-01-01 开始，历史订单到 2026-09-24；2026-09-25 上午的订单由演示者现场实时写入，写入之前今天是 0 单，这是正常的。
 - 2026 年 9 月只到 25 日。拿它和 2025 年 9 月整月比较时，要说明这一点。
-- 同比用 `gmv_last_year`（去年同期 GMV）和 `gmv_yoy`（GMV 同比增长率）。这两个指标必须按月分组（group_by `metric_time__month`），where 必须写结束日期，例如 `metric_time BETWEEN '2026-01-01' AND '2026-09-25'`；不写结束日期，结果会多出 2026-10 到 2026-12 这几行，它们只有去年的值。
+- 同比用 `gmv_last_year`（去年同期 GMV）和 `gmv_yoy`（GMV 同比增长率）。这两个指标要按时间分组，默认按月（group_by `metric_time__month`），where 必须写结束日期，例如 `metric_time BETWEEN '2026-01-01' AND '2026-09-25'`；不写结束日期，结果会多出 2026-10 到 2026-12 这几行，它们只有去年的值。
 - 2025 年及更早的期间没有去年同期数据，`gmv_last_year`、`gmv_yoy` 返回 0 表示「无数据」，不是「持平」。
 - 比率类指标返回小数：`mini_program_share`（小程序 GMV 占比）、`gross_margin`、`refund_rate`、`bad_review_rate` 在 0~1 之间，`gmv_yoy` 可能为负，也可能大于 1。展示时换算成百分比。
 - 小程序渠道是 `order_entity__channel = 'MINI_PROGRAM'`；分渠道看时 group_by `order_entity__channel`。
 - 按类目、品牌、店铺看 GMV 用 `line_gmv`（商品行实付，不含运费）；不要把订单级指标 `gmv`、`order_count`、`aov` 按类目拆分。
-- 时间范围写成 `metric_time BETWEEN '…' AND '…'`。
+- 时间过滤会对齐到分组粒度：按月分组时，`metric_time BETWEEN '2026-09-01' AND '2026-09-25'` 取的是 9 月整月，去年同期也是 2025 年 9 月整月。要比较「同期同天数」（例如 9 月 1–25 日对比去年 9 月 1–25 日），按天分组（group_by `metric_time__day`），在同一次调用里取 `gmv` 和 `gmv_last_year`，把各天分别相加后再算同比；不要把逐日的 `gmv_yoy` 取平均。
+- 可用的时间粒度：`metric_time__day`、`metric_time__week`、`metric_time__month`、`metric_time__quarter`、`metric_time__year`。
+- 时间范围写成 `metric_time BETWEEN '…' AND '…'`。一次调用只写一个时间范围，不要用 OR 连接几个时间范围（会报错）；要看几个时间段，就分几次调用，或者用上面的去年同期指标。
```

- [ ] **Step 4：确认通过；突变**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s quick/test 2>&1 | tail -3                                  # 期望：Ran 50 tests … OK
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 161 tests … OK
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 期望：Ran 113 tests … OK
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json ad; echo "rc=$?"
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json ai; echo "rc=$?"
```
期望（实测，秒数每次不同）：
```
Ran 50 tests in 0.169s

OK
Ran 161 tests in 6.442s

OK
Ran 113 tests in 1.989s

OK
ad1 no row for profile list --active: caught by test_every_contract_command_and_flag_is_mapped (Ran 19, FAILED (failures=1))
ad2 no row for --no-cache: caught by test_every_contract_command_and_flag_is_mapped (Ran 19, FAILED (failures=1))
ad3 max_chars outside the server's range: caught by test_max_chars_values_are_accepted_by_the_server, test_truncation_full_mode_and_a_missing_profile (Ran 19, FAILED (failures=2))
ad4 a tool name that is not behind the Gateway: caught by test_every_tool_named_exists_behind_the_gateway_and_all_are_listed, test_the_fe_http_paths_the_skills_use_are_mapped (Ran 19, FAILED (failures=2))
ad5 SET statements not said to be rejected: caught by test_set_is_a_hint_not_a_statement (Ran 19, FAILED (failures=1))
ad6 description without read-only: caught by test_description_fits_and_names_what_it_is_for (Ran 19, FAILED (failures=1))
ad7 KILL not in the writes list: caught by test_writes_and_admin_actions_are_handed_to_a_person (Ran 19, FAILED (failures=1))
ad8 no retry-once rule at 424: caught by test_the_60_second_limit_and_how_to_stay_under_it (Ran 19, FAILED (failures=1))
ad9 a bare tool name without the prefix: caught by test_every_tool_name_has_the_gateway_prefix (Ran 19, FAILED (failures=1))
ad10 no word on a missing profile: caught by test_truncation_full_mode_and_a_missing_profile (Ran 19, FAILED (failures=1))
ad11 name differs from the folder: caught by test_name_is_the_folder_name, test_the_hint_in_every_copy_names_this_skill (Ran 19, FAILED (failures=2))
ad12 doriscli tablet maps to SHOW CREATE TABLE only: caught by test_doriscli_tablet_becomes_the_table_statements (Ran 19, FAILED (failures=1))
ad13 the evidence section drops the connection-details rule: caught by test_evidence_first_and_no_connection_details (Ran 19, FAILED (failures=1))
ad14 no tablet row, only the --detail row: caught by test_doriscli_tablet_becomes_the_table_statements (Ran 19, FAILED (failures=1))
14/14 mutations caught; tree unchanged: True
rc=0
ai1 quarter grain not named: caught by test_every_time_grain_of_metric_time_is_named (Ran 22, FAILED (failures=1))
ai2 the skills are used without the adapter: caught by test_diagnosis_uses_the_skills_through_the_adapter (Ran 22, FAILED (failures=1))
ai3 same-days comparison grouped by month: caught by test_filters_follow_the_grain_and_the_same_days_are_compared_by_day (Ran 22, FAILED (failures=1))
ai4 no one-range-per-call rule: caught by test_one_time_range_per_call_and_no_or (Ran 22, FAILED (failures=1))
ai5 reconcile case grouped by month: caught by test_the_same_days_comparison_is_a_reconcile_case (Ran 22, FAILED (failures=1))
ai6 a skill name that is not in quick/skills: caught by test_diagnosis_uses_the_skills_through_the_adapter, test_every_skill_named_is_in_quick_skills (Ran 22, FAILED (failures=2))
ai7 no reconcile case for the same days: caught by test_the_same_days_comparison_is_a_reconcile_case (Ran 22, FAILED (failures=1))
7/7 mutations caught; tree unchanged: True
rc=0
```

- [ ] **Step 5：在线对账（只读）**

新 case 经已部署的 Runtime（旧 server；按天分组、`BETWEEN` 在旧 server 上就是对的）编译执行，手写 SQL 以 `demo_ro` 直连执行，两边逐行比较。凭证只在子 shell 里，只导出 `demo_ro` 的 4 个变量，root 账号的变量不传下去（与 P4 相同）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
source infra/state.env
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_USER="$DORIS_RO_USER" DORIS_PASSWORD="$DORIS_RO_PASSWORD" AWS_REGION=us-east-1
  unset DORIS_ROOT_USER DORIS_ROOT_PASSWORD DORIS_RO_USER DORIS_RO_PASSWORD DORIS_ADMIN_PASSWORD
  exec .venv/bin/python doris/reconcile.py mcp --url "$RUNTIME_URL" ) 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
```
期望（实测）：
```
published metrics: 22 match /home/ubuntu/AI-code/Doris-mcp-skill-Demo/doris/semantic/ecom
ok    ytd_totals (1 rows)
ok    monthly_2026 (9 rows)
ok    yoy_2026 (9 rows)
ok    yoy_same_days_2026_09 (24 rows)
ok    channel_ytd (4 rows)
ok    area_ytd (7 rows)
ok    mini_program_quarterly (7 rows)
ok    cat1_items_ytd (12 rows)
ok    brand_tier_ytd (3 rows)
ok    refund_rate_5_1 (2 rows)
ok    reviews_by_shop_type_ytd (4 rows)
ok    refunds_by_reason_ytd (10 rows)
12/12 cases match
exit=0
```
Runtime 偶发 502 或冷启动超时（design §13）时整条重跑一次；同一个 case 连续两次不一致才排查。

- [ ] **Step 6：收尾，提交**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - T5.2 <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
echo 'Task 2（T5.2）已完成；Task 3（T5.7a 代码：P-10、P-11）从 Step 1 开始' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo 'Task 3（T5.7a 代码），然后 Task 4（T5.7b）、Task 5（demo-check / cleanup 脚本）、Task 6（部署，GATE）、Task 7（整体评审，再交给用户导入 skill 和彩排 2 轮）、Task 8（T5.5）、Task 9（演示结束后清理，GATE）' | .venv/bin/python /tmp/p5-progress.py state 下一步
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 2（T5.2）：adapter skill、指令第 5 条和时间口径

- `quick/skills/doris-mcp-adapter/SKILL.md`（124 行）：工具表、doriscli 命令翻译表（`CLI-CONTRACT.md` 的全部命令和 flag，加上副本正文用到的命令；`SET` → `SET_VAR` 提示；`tablet` → 4 条表级语句；FE HTTP 路径）、带 profile 执行的 4 步、能用和被拒绝的 SQL、写操作交给人、60 s 限制、先有证据。19 个检查从 `CLI-CONTRACT.md`、副本正文和 server 的工具注册取对照。
- `quick/agent-instructions.md`：第 5 条（诊断类问题按 4 个 doris-* skill 的方法做，先加载 adapter）；演示口径加「时间过滤对齐到分组粒度」「同期同天数按天分组再相加」「5 个时间粒度」「一次调用一个时间范围，不用 OR」。P4 的「日期过滤假设」由此收口：按月分组取整月是 MetricFlow 的设计，不改 server。
- `doris/reconcile.py` 加 `yoy_same_days_2026_09`（按天分组的 `gmv` + `gmv_last_year`，9 月 1–24 日），经已部署的 Runtime 在线对账 12/12。
- RED：20 个 `ERROR`（adapter 的 `SKILL.md` 还不存在）、7 个 `FAIL`（4 个 skill 目录，指令没有第 5 条和时间粒度口径，对账没有 `yoy_same_days_2026_09`）。
- GREEN：`quick/test` 50、`doris/test` 161、`scripts/test` 113；突变 ad 14/14、ai 7/7 被抓到。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add quick/skills/doris-mcp-adapter quick/test/test_adapter_skill.py quick/test/test_skills.py quick/test/test_agent_instructions.py \
        quick/agent-instructions.md doris/reconcile.py specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
feat(p5): T5.2 doris-mcp-adapter skill, instruction 5 and time-grain framing, reconcile yoy_same_days_2026_09

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望（实测）：
```
ticked: T5.2
进行中: written (743 lines)
下一步: written (743 lines)
### 2026-09-28 P5 Task 2（T5.2）：adapter skill、指令第 5 条和时间口径: written (751 lines)
check-secrets: OK (841 files scanned)
0
feat(p5): T5.2 doris-mcp-adapter skill, instruction 5 and time-grain framing, reconcile yoy_same_days_2026_09
```
日志里的数字如果和实测不同，写实测值。

---

### Task 3：T5.7a 代码：P-10 审计的失败原因和过滤条件、P-11 metric_time 过滤

来源：design §5.2 的 P-10、P-11，tasks.md T5.7a；P4 遗留的「审计 `where` / `having`」「失败调用的 `error` 是 None」。部署在 Task 6。spec 阶段的发现：

| # | spec 阶段的发现（`bcda0f3` 的 server）| 处理 | 测试 |
|---|---|---|---|
| 1 | 失败的 `execute_query` / `query_metric` 的审计记录 `error` 是 None；`query_metric` 用子串 `'"success": true' in result` 判断成败 | P-10：`_audit_error(result)` 从解析后的结果取 `CODE: message`（300 字符，`log_tool_call` 照常 mask）；成败取自解析结果 | `TestAuditError` 5 个；`TestExecuteQueryAudit` 5 个；`test_success_is_parsed_not_substring_matched` |
| 2 | `query_metric` 的审计只有 `metrics`、`group_by`，分不清失败的调用写了什么过滤条件 | P-10：审计记下解析后的 `where`、`having`、`order_by`、`limit`（没设的记空值），`mf_command` 补上对应的选项（`where` / `having` 里的双引号转义）| `TestQueryMetricAudit` 7 个（含 where 里的密码字面量被 mask）|
| 3 | 经 Gateway 实测：OR 连接两个 metric_time 范围编译成 `WHERE () OR ()`，Doris 报 `no viable alternative` / `mismatched input 'OR'` | P-11：metric_time 条件所在的组（它自己的括号层或外层）有顶层 OR 时抛 `ValueError`，作为编译错误返回（`INTERNAL_ERROR`，消息提示每个范围调用一次或用 `*_last_year`）；引号里的 OR、括号不算；兄弟组里的 OR 不受影响 | `TestOr` 7 个、`TestOrSurfacesAsCompileError` 2 个；`test_semantic_time` 的 2 个 |
| 4 | `>` / `<` 按闭区间处理（`> '2026-09-20' AND < '2026-09-24'` 取到 20–24 日 5 天）| P-11：严格比较把日期边界移 1 天，带时间部分的移 1 s | `TestStrictOperators` 4 个；`test_semantic_time` 的 3 个（8 月 31 天）|
| 5 | 多个 metric_time 条件只取最后一个；`TimeDimension('order_entity__order_date', …)` 也被当成 metric_time | P-11：取交集（最晚的开始、最早的结束）；只提取 `TimeDimension('metric_time', …)`，其他时间维度留在 where | `TestIntersection` 2 个、`TestTimeDimensionTemplate` 3 个；`test_other_time_dimension_stays_a_where_filter` |
| 6 | 括号包住的范围留下 `( AND )`，Doris 报语法错误 | P-11：匹配到的条件先换成标记，再连同它的 AND 和空括号一起去掉 | `TestParenthesizedRange` 5 个 |
| 7 | 按分组粒度对齐时间范围是 MetricFlow 的设计（Task 2 第 5 条）；`NOT` 包住 metric_time 上游就没有处理 | 都不改：`test_day_filters_are_aligned_to_the_month_grain` 和 `TestNotIsOutOfScope` 锁定现状，`UPSTREAM.md` 写明 NOT 不在 P-11 范围内 | 这 2 个在 RED 时就通过 |

`TestDocumentedBehaviour`（11 个）锁定 `_extract_time_constraints` docstring 里已有的行为（只有开始、开始和结束、其他过滤条件保留、BETWEEN 闭区间、带粒度后缀、双引号、时间部分……），它们在 RED 时就通过，确保 P-11 没有改掉已有的行为。

**Files:**
- Modify: `mcp-server/src/server.py`（`_audit_error`、`_mf_quote`；`execute_query` 和 `query_metric` 的 `log_tool_call`）、`mcp-server/src/store/compiler.py`（`_extract_time_constraints`、`_METRIC_TIME_OR_ERROR`）、`mcp-server/UPSTREAM.md`（P-08 更新，加 P-10、P-11）
- Create: `mcp-server/test/test_agentcore_audit_errors.py`（17 个，Doris 连接池和语义层是假的）、`mcp-server/test/test_agentcore_time_constraints.py`（35 个）、`doris/test/test_semantic_time.py`（7 个，经 `reconcile.DirectBackend` 在本机编译 ecom 的模型，不连 Doris）
- Test: `test_agentcore_*.py` 89 → 141，`doris/test` 161 → 168；upstream 离线测试照常通过

**Interfaces:**
- Consumes：`bcda0f3` 的 `core.audit.log_tool_call(tool, client_id, params, success, error=None, duration_ms, metricflow, mf_command=None)`（对 params、mf_command、error 做 `mask_sensitive`）、`core.response.error_response` / `success_response`、`tools.semantic.query_metric(compiler, pool, metrics, group_by, where, order_by, limit, database, max_rows, having)`、`MetricFlowCompiler._extract_time_constraints(where) -> (remaining, start, end)`；Task 2 的 `reconcile.DirectBackend`、`Case`。
- Produces：
  - `server._audit_error(result: str) -> str | None`：失败时 `"CODE: message"`（≤ 300 字符），成功或不是 JSON 对象时 None；
  - 审计记录（CloudWatch 里 `doris_new_mcp.audit` 的 JSON 行）：`query_metric` 的 `params` 有 `metrics`、`group_by`、`where`、`having`、`order_by`、`limit`，失败的记录有 `error`。Task 4 的 `audit_check.py --failures` 和 Task 5 的 `demo-check.sh post` 按这个格式读；
  - OR 的编译错误消息 `_METRIC_TIME_OR_ERROR`（以 `metric_time filters must be a single range joined with AND` 开头）：Task 6 Step 2 的探针表期望它（部署后在 Step 6 重跑同样的探针，`demo-check post` 的失败列表里也应当有它）。

- [ ] **Step 1：写失败测试**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py mcp-server/test/test_agentcore_audit_errors.py
.venv/bin/python /tmp/p5-extract.py mcp-server/test/test_agentcore_time_constraints.py
.venv/bin/python /tmp/p5-extract.py doris/test/test_semantic_time.py
git status --short
```
期望（实测）：
```
mcp-server/test/test_agentcore_audit_errors.py -> mcp-server/test/test_agentcore_audit_errors.py (219 lines)
mcp-server/test/test_agentcore_time_constraints.py -> mcp-server/test/test_agentcore_time_constraints.py (239 lines)
doris/test/test_semantic_time.py -> doris/test/test_semantic_time.py (82 lines)
?? doris/test/test_semantic_time.py
?? mcp-server/test/test_agentcore_audit_errors.py
?? mcp-server/test/test_agentcore_time_constraints.py
```

新文件 `mcp-server/test/test_agentcore_audit_errors.py`（审计记录从 `doris_new_mcp.audit` logger 读回，所以 params、`mf_command`、`error` 和 AgentCore 上一样经过 `mask_sensitive`）：

<!-- file: mcp-server/test/test_agentcore_audit_errors.py sha256=c9128d0991076c4163bd207c7411e2284bbd63694c198ccbb063e7092a669b36 -->
```python
"""P-10: a failed tool call carries its error text in the audit log; query_metric logs its filters.

The audit record is read back from the `doris_new_mcp.audit` logger, so params, mf_command and
error go through log_tool_call's mask_sensitive exactly as they do on AgentCore (CloudWatch).
The Doris pool and the semantic workspace are fakes: no connection is opened.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastmcp import Client  # noqa: E402

import store.store as st  # noqa: E402
from config.loader import AppConfig  # noqa: E402
from core.response import ErrorCode, error_response, success_response  # noqa: E402
from server import _audit_error, create_server  # noqa: E402
from store.watcher import MultiWorkspaceWatcher  # noqa: E402

SVC = ("mcp_svc", "svc-pw")
DORIS_ERROR = "(1105, \"errCode = 2, detailMessage = Unknown column 'nope' in 'v_paid_order'\")"
CHANNEL = "{{ Dimension('order_entity__channel') }}"


class TestAuditError(unittest.TestCase):
    def test_success_is_none(self):
        self.assertIsNone(_audit_error(success_response({"rows": []})))

    def test_failure_is_code_and_message(self):
        result = error_response(ErrorCode.INVALID_SQL, "Only read-only queries are allowed", {"sql": "DELETE"})
        self.assertEqual(_audit_error(result), "INVALID_SQL: Only read-only queries are allowed")

    def test_not_json_or_not_an_object_is_none(self):
        for result in ("", "not json", "[1, 2]", '"text"', "null", '{"data": 1}'):
            with self.subTest(result=result):
                self.assertIsNone(_audit_error(result))

    def test_missing_code_or_message(self):
        cases = {
            '{"success": false, "error": {"message": "boom"}}': "boom",
            '{"success": false, "error": {"code": "QUERY_TIMEOUT"}}': "QUERY_TIMEOUT",
            '{"success": false, "error": "boom"}': "boom",
            '{"success": false}': "unknown error",
        }
        for result, expected in cases.items():
            with self.subTest(result=result):
                self.assertEqual(_audit_error(result), expected)

    def test_truncated_to_300_chars(self):
        error = _audit_error(error_response(ErrorCode.CONNECTION_ERROR, "x" * 400))
        self.assertEqual(len(error), 300)
        self.assertEqual(error, ("CONNECTION_ERROR: " + "x" * 400)[:300])


class FakePool:
    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.sql = rows or [], error, []

    async def execute(self, sql, database=None, max_rows=None):
        self.sql.append(sql)
        if self.error:
            raise self.error
        return self.rows, list(self.rows[0]) if self.rows else []


class FakeCompiler:
    """resolve_* like the real compiler for `month`/`channel`; compile returns a fixed (sql, command, error)."""

    def __init__(self, sql="SELECT 1 AS gmv", error=""):
        self.sql, self.error, self.compiled = sql, error, []

    def resolve_group_by(self, metrics, names):
        return ["metric_time__month" if n == "month" else n for n in names]

    def resolve_where(self, metrics, where):
        return where.replace("channel", CHANNEL)

    def compile(self, metrics, group_by, where, order_by, limit, having):
        self.compiled.append(where)
        return (None if self.error else self.sql), "mf query", self.error


class _AuditCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(st.clear_service_credentials)
        root = Path(tmp.name)
        (root / "config").mkdir()
        self.server = create_server(config_dir=str(root / "config"), config=AppConfig(root / "config"),
                                    machine_ip="198.51.100.7", service_credentials=SVC,
                                    workspace_dir=str(root / "ws"))

    async def call(self, tool, args, pool, compiler=None):
        """Call a tool; return (result body, audit record, raw audit line)."""
        workspace = SimpleNamespace(enabled=True, is_ready=lambda: True, last_reload_error="", compiler=compiler)
        with patch("core.pool_manager.PoolManager.get_or_create_local_pool", AsyncMock(return_value=pool)), \
                patch.object(MultiWorkspaceWatcher, "ensure_fresh", return_value=workspace), \
                self.assertLogs("doris_new_mcp.audit", "INFO") as logs:
            async with Client(self.server) as client:
                result = await client.call_tool(tool, args, raise_on_error=False)
        (line,) = [r.getMessage() for r in logs.records]
        record = json.loads(line)
        self.assertEqual(record["tool"], tool)
        return json.loads(result.content[0].text), record, line


class TestExecuteQueryAudit(_AuditCase):
    async def test_failure_records_the_error_text(self):
        body, record, _ = await self.call("execute_query", {"sql": "SELECT nope FROM v_paid_order", "database": "ecom"},
                                          FakePool(error=RuntimeError(DORIS_ERROR)))
        self.assertEqual(body["error"]["code"], "CONNECTION_ERROR")
        self.assertFalse(record["success"])
        self.assertEqual(record["error"], f"CONNECTION_ERROR: {DORIS_ERROR}")
        self.assertEqual(record["params"], {"sql": "SELECT nope FROM v_paid_order", "database": "ecom"})

    async def test_rejected_sql_records_the_reason(self):
        pool = FakePool()
        body, record, _ = await self.call("execute_query", {"sql": "DELETE FROM v_paid_order"}, pool)
        self.assertEqual(body["error"]["code"], "INVALID_SQL")
        self.assertEqual(record["error"], f"INVALID_SQL: {body['error']['message']}")
        self.assertEqual(pool.sql, [])

    async def test_success_records_no_error(self):
        body, record, _ = await self.call("execute_query", {"sql": "SELECT 1 AS n"}, FakePool(rows=[{"n": 1}]))
        self.assertTrue(body["success"])
        self.assertTrue(record["success"])
        self.assertNotIn("error", record)

    async def test_sql_is_masked_and_cut_to_200_chars(self):
        sql = "SELECT * FROM t WHERE password = 'hunter2-pw' AND x IN (" + "1, " * 100 + "1)"
        _, record, line = await self.call("execute_query", {"sql": sql}, FakePool(rows=[{"n": 1}]))
        self.assertEqual(record["params"]["sql"], sql[:200].replace("hunter2-pw", "****"))
        self.assertNotIn("hunter2-pw", line)

    async def test_error_echoing_a_password_is_masked(self):
        # Doris echoes the offending SQL in its error; the audit error goes through mask_sensitive.
        error = RuntimeError("(1105, \"errCode = 2, detailMessage = Syntax error near password = 'hunter2-pw'\")")
        _, record, line = await self.call("execute_query", {"sql": "SELECT 1"}, FakePool(error=error))
        self.assertIn("near password = '****'", record["error"])
        self.assertNotIn("hunter2-pw", line)


class TestQueryMetricAudit(_AuditCase):
    FILTERED = {"workspace": "ecom", "metrics": ["gmv"], "group_by": ["month"], "where": "channel = 'APP'",
                "having": "gmv > 100", "order_by": ["-gmv"], "limit": 5}

    async def test_records_resolved_filters(self):
        compiler = FakeCompiler()
        body, record, _ = await self.call("query_metric", self.FILTERED, FakePool(rows=[{"gmv": 1}]), compiler)
        self.assertTrue(body["success"])
        self.assertEqual(compiler.compiled, [f"{CHANNEL} = 'APP'"])
        self.assertEqual(record["params"], {
            "metrics": "['gmv']", "group_by": "['metric_time__month']", "where": f"{CHANNEL} = 'APP'",
            "having": "gmv > 100", "order_by": "['-gmv']", "limit": "5",
        })
        self.assertEqual(record["mf_command"],
                         f"mf query --metrics gmv --group-by metric_time__month --where \"{CHANNEL} = 'APP'\" "
                         "--order-by -gmv --limit 5 --having \"gmv > 100\"")
        self.assertTrue(record["success"])
        self.assertNotIn("error", record)

    async def test_unset_filters_are_logged_empty_and_left_out_of_mf_command(self):
        # One rule: every filter key is always in params (a stable schema for Logs Insights);
        # mf_command only carries the options that were set.
        _, record, _ = await self.call("query_metric", {"workspace": "ecom", "metrics": ["gmv", "aov"]},
                                       FakePool(rows=[{"gmv": 1}]), FakeCompiler())
        self.assertEqual(record["params"], {"metrics": "['gmv', 'aov']", "group_by": "[]", "where": "",
                                            "having": "", "order_by": "[]", "limit": "0"})
        self.assertEqual(record["mf_command"], "mf query --metrics gmv,aov")

    async def test_double_quotes_in_where_are_escaped_in_mf_command(self):
        args = {"workspace": "ecom", "metrics": ["gmv"], "where": 'region = "east"'}
        _, record, _ = await self.call("query_metric", args, FakePool(rows=[{"gmv": 1}]), FakeCompiler())
        self.assertEqual(record["mf_command"], 'mf query --metrics gmv --where "region = \\"east\\""')

    async def test_compile_failure_records_the_error_text(self):
        compiler = FakeCompiler(error="Unknown dimension 'nope'")
        pool = FakePool()
        body, record, _ = await self.call("query_metric", self.FILTERED, pool, compiler)
        self.assertEqual(body["error"]["code"], "INTERNAL_ERROR")
        self.assertFalse(record["success"])
        self.assertEqual(record["error"], "INTERNAL_ERROR: MetricFlow compile error: Unknown dimension 'nope'")
        self.assertEqual(record["params"]["where"], f"{CHANNEL} = 'APP'")
        self.assertEqual(pool.sql, [])

    async def test_doris_failure_records_the_error_text(self):
        _, record, _ = await self.call("query_metric", self.FILTERED, FakePool(error=RuntimeError(DORIS_ERROR)),
                                       FakeCompiler())
        self.assertFalse(record["success"])
        self.assertEqual(record["error"], f"CONNECTION_ERROR: {DORIS_ERROR}")

    async def test_success_is_parsed_not_substring_matched(self):
        # A compact JSON body has no '"success": true' substring; success comes from the parsed result.
        compact = json.dumps({"success": True, "data": {"columns": ["gmv"], "rows": [{"gmv": 1}]}},
                             separators=(",", ":"))
        with patch("tools.semantic.query_metric", AsyncMock(return_value=compact)):
            _, record, _ = await self.call("query_metric", self.FILTERED, FakePool(), FakeCompiler())
        self.assertTrue(record["success"])
        self.assertNotIn("error", record)

    async def test_password_literal_in_where_is_masked(self):
        args = {"workspace": "ecom", "metrics": ["gmv"], "where": "user__password = 'hunter2-pw'"}
        _, record, line = await self.call("query_metric", args, FakePool(rows=[{"gmv": 1}]), FakeCompiler())
        self.assertEqual(record["params"]["where"], "user__password = '****'")
        self.assertIn("--where \"user__password = '****'\"", record["mf_command"])
        self.assertNotIn("hunter2-pw", line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

新文件 `mcp-server/test/test_agentcore_time_constraints.py`：

<!-- file: mcp-server/test/test_agentcore_time_constraints.py sha256=1554f30e4aaca9a94ad60a9b54027a062a9beddce4f1f1705e5b9f5870213785 -->
```python
"""P-11: MetricFlowCompiler._extract_time_constraints turns metric_time filters into one time range.

metric_time comparisons become MetricFlow time_constraint_start/end (inclusive, day grain for
date-only literals); everything else stays in the where. OR around a metric_time condition is
rejected with a message for the calling agent, instead of compiling to `WHERE () OR ()`.
"""

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from store.compiler import MetricFlowCompiler  # noqa: E402
from tools.semantic import query_metric  # noqa: E402

extract = MetricFlowCompiler._extract_time_constraints
TD = "{{ TimeDimension('metric_time', 'day') }}"
ORDER_DATE = "{{ TimeDimension('order_entity__order_date', 'day') }}"
CHANNEL = "{{ Dimension('order_entity__channel') }}"
OR_RANGES = ("(metric_time BETWEEN '2025-09-01' AND '2025-09-25') OR "
             "(metric_time BETWEEN '2026-09-01' AND '2026-09-25')")
OR_MESSAGE = "metric_time filters must be a single range joined with AND"


def d(*args):
    return datetime(*args)


class TestDocumentedBehaviour(unittest.TestCase):
    """The docstring examples and the forms the server already relied on before P-11."""

    def test_start_only(self):
        self.assertEqual(extract("metric_time >= '2026-02-01'"), (None, d(2026, 2, 1), None))

    def test_start_and_end(self):
        self.assertEqual(extract("metric_time >= '2026-02-01' AND metric_time <= '2026-02-28'"),
                         (None, d(2026, 2, 1), d(2026, 2, 28)))

    def test_other_filters_remain(self):
        self.assertEqual(extract("metric_time >= '2026-02-01' AND channel = 'APP'"),
                         ("channel = 'APP'", d(2026, 2, 1), None))
        self.assertEqual(extract("channel = 'X' AND metric_time >= '2026-01-01' AND region = 'y'"),
                         ("channel = 'X' AND region = 'y'", d(2026, 1, 1), None))

    def test_time_dimension_template(self):
        self.assertEqual(extract(f"{TD} >= '2026-02-01'"), (None, d(2026, 2, 1), None))
        self.assertEqual(extract(f"{TD} >= '2026-02-01' AND {CHANNEL} = 'APP'"),
                         (f"{CHANNEL} = 'APP'", d(2026, 2, 1), None))

    def test_between_is_inclusive(self):
        self.assertEqual(extract("metric_time BETWEEN '2026-01-01' AND '2026-09-24'"),
                         (None, d(2026, 1, 1), d(2026, 9, 24)))
        self.assertEqual(extract("metric_time between '2026-01-01' and '2026-09-24'"),
                         (None, d(2026, 1, 1), d(2026, 9, 24)))

    def test_between_with_other_filter(self):
        # reconcile.py shop case
        self.assertEqual(extract("metric_time BETWEEN '2026-07-01' AND '2026-08-31' AND shop__shop_name = 'x'"),
                         ("shop__shop_name = 'x'", d(2026, 7, 1), d(2026, 8, 31)))

    def test_grain_suffix_names(self):
        self.assertEqual(extract("metric_time__month >= '2026-01-01'"), (None, d(2026, 1, 1), None))
        self.assertEqual(extract("metric_time__day <= '2026-01-31'"), (None, None, d(2026, 1, 31)))

    def test_double_quoted_literals(self):
        self.assertEqual(extract('metric_time >= "2026-02-01" AND metric_time <= "2026-02-28"'),
                         (None, d(2026, 2, 1), d(2026, 2, 28)))

    def test_time_part(self):
        self.assertEqual(extract("metric_time >= '2026-08-01 10:00:00'"), (None, d(2026, 8, 1, 10), None))
        self.assertEqual(extract("metric_time <= '2026-08-01T10:30:00'"), (None, None, d(2026, 8, 1, 10, 30)))

    def test_nothing_to_extract(self):
        for where in (None, "", "   "):
            self.assertEqual(extract(where), (None, None, None))
        self.assertEqual(extract("channel = 'APP'"), ("channel = 'APP'", None, None))

    def test_outer_quotes_only_leftover_is_none(self):
        self.assertEqual(extract("\"metric_time >= '2026-02-01'\""), (None, d(2026, 2, 1), None))


class TestOr(unittest.TestCase):
    def assert_rejected(self, where):
        with self.assertRaises(ValueError) as caught:
            extract(where)
        message = str(caught.exception)
        self.assertTrue(message.startswith(OR_MESSAGE), message)
        for hint in ("no OR", "one query_metric call per range", "_last_year", "grouped by metric_time"):
            self.assertIn(hint, message)

    def test_or_between_ranges(self):
        self.assert_rejected(OR_RANGES)
        self.assert_rejected(OR_RANGES.replace("(", "").replace(")", ""))
        self.assert_rejected(f"({TD} BETWEEN '2025-09-01' AND '2025-09-25') OR ({TD} BETWEEN '2026-09-01' AND '2026-09-25')")

    def test_or_at_the_match_level(self):
        self.assert_rejected("metric_time >= '2026-01-01' AND (channel = 'APP' OR metric_time < '2026-02-01')")
        self.assert_rejected("metric_time >= '2026-01-01' or channel = 'APP'")

    def test_or_at_an_enclosing_level(self):
        self.assert_rejected("channel = 'A' OR (metric_time >= '2026-01-01' AND channel = 'B')")
        self.assert_rejected("(channel = 'A' OR (region = 'x' AND (metric_time >= '2026-01-01'))) AND qty > 1")

    def test_or_in_a_sibling_group_is_kept(self):
        self.assertEqual(extract("metric_time >= '2026-01-01' AND (channel = 'A' OR channel = 'B')"),
                         ("(channel = 'A' OR channel = 'B')", d(2026, 1, 1), None))
        self.assertEqual(extract(f"{TD} >= '2026-01-01' AND ({CHANNEL} = 'A' OR {CHANNEL} = 'B')"),
                         (f"({CHANNEL} = 'A' OR {CHANNEL} = 'B')", d(2026, 1, 1), None))

    def test_or_inside_a_literal_is_not_an_or(self):
        self.assertEqual(extract("metric_time >= '2026-01-01' AND note = 'x OR y'"),
                         ("note = 'x OR y'", d(2026, 1, 1), None))
        self.assertEqual(extract('metric_time >= \'2026-01-01\' AND note = "a or b"'),
                         ('note = "a or b"', d(2026, 1, 1), None))

    def test_parentheses_inside_a_literal_are_ignored(self):
        where = "(channel = 'A' OR note = 'x (') AND metric_time >= '2026-01-01'"
        self.assertEqual(extract(where), ("(channel = 'A' OR note = 'x (')", d(2026, 1, 1), None))

    def test_or_without_metric_time_is_untouched(self):
        self.assertEqual(extract("channel = 'A' OR channel = 'B'"), ("channel = 'A' OR channel = 'B'", None, None))


class TestStrictOperators(unittest.TestCase):
    def test_greater_than_a_date_starts_the_next_day(self):
        self.assertEqual(extract("metric_time > '2026-08-31'"), (None, d(2026, 9, 1), None))
        self.assertEqual(extract("metric_time > '2025-12-31'"), (None, d(2026, 1, 1), None))

    def test_less_than_a_date_ends_the_day_before(self):
        self.assertEqual(extract("metric_time < '2026-09-01'"), (None, None, d(2026, 8, 31)))
        self.assertEqual(extract("metric_time < '2026-03-01'"), (None, None, d(2026, 2, 28)))

    def test_august_with_a_strict_end(self):
        self.assertEqual(extract("metric_time >= '2026-08-01' AND metric_time < '2026-09-01'"),
                         (None, d(2026, 8, 1), d(2026, 8, 31)))

    def test_time_part_shifts_by_one_second(self):
        self.assertEqual(extract("metric_time > '2026-08-01 10:00:00'"), (None, d(2026, 8, 1, 10, 0, 1), None))
        self.assertEqual(extract("metric_time < '2026-08-01T10:00:00'"), (None, None, d(2026, 8, 1, 9, 59, 59)))


class TestTimeDimensionTemplate(unittest.TestCase):
    def test_other_time_dimension_stays_in_where(self):
        where = f"{ORDER_DATE} >= '2026-01-01'"
        self.assertEqual(extract(where), (where, None, None))

    def test_mixed_with_metric_time(self):
        self.assertEqual(extract(f"{TD} >= '2026-01-01' AND {ORDER_DATE} <= '2026-03-31'"),
                         (f"{ORDER_DATE} <= '2026-03-31'", d(2026, 1, 1), None))

    def test_spaces_double_quotes_and_grain(self):
        self.assertEqual(extract("{{ TimeDimension( \"metric_time\" , 'month') }} >= '2026-01-01'"),
                         (None, d(2026, 1, 1), None))
        self.assertEqual(extract("{{TimeDimension('metric_time')}} <= '2026-01-31'"), (None, None, d(2026, 1, 31)))


class TestIntersection(unittest.TestCase):
    def test_latest_start_wins(self):
        self.assertEqual(extract("metric_time >= '2026-03-01' AND metric_time >= '2026-01-01'"),
                         (None, d(2026, 3, 1), None))

    def test_earliest_end_wins(self):
        self.assertEqual(extract("metric_time <= '2026-03-31' AND metric_time BETWEEN '2026-01-01' AND '2026-06-30'"),
                         (None, d(2026, 1, 1), d(2026, 3, 31)))
        self.assertEqual(extract("metric_time BETWEEN '2026-02-01' AND '2026-06-30' AND metric_time > '2026-01-15'"),
                         (None, d(2026, 2, 1), d(2026, 6, 30)))


class TestParenthesizedRange(unittest.TestCase):
    def test_range_group_leaves_exactly_the_other_filter(self):
        self.assertEqual(
            extract("(metric_time >= '2026-01-01' AND metric_time < '2026-02-01') AND channel = 'X'"),
            ("channel = 'X'", d(2026, 1, 1), d(2026, 1, 31)))
        self.assertEqual(
            extract(f"({TD} >= '2026-01-01' AND {TD} < '2026-02-01') AND {CHANNEL} = 'X'"),
            (f"{CHANNEL} = 'X'", d(2026, 1, 1), d(2026, 1, 31)))

    def test_range_group_after_the_other_filter(self):
        self.assertEqual(extract("channel = 'X' AND (metric_time BETWEEN '2026-01-01' AND '2026-01-31')"),
                         ("channel = 'X'", d(2026, 1, 1), d(2026, 1, 31)))

    def test_range_group_after_an_or_group(self):
        self.assertEqual(extract("(channel = 'A' OR channel = 'B') AND (metric_time <= '2026-01-31')"),
                         ("(channel = 'A' OR channel = 'B')", None, d(2026, 1, 31)))

    def test_range_group_alone(self):
        self.assertEqual(extract("((metric_time >= '2026-01-01') AND (metric_time <= '2026-01-31'))"),
                         (None, d(2026, 1, 1), d(2026, 1, 31)))

    def test_group_mixing_time_and_other_filters(self):
        self.assertEqual(extract("(channel = 'X' AND metric_time >= '2026-01-01') AND region = 'y'"),
                         ("(channel = 'X') AND region = 'y'", d(2026, 1, 1), None))


class TestNotIsOutOfScope(unittest.TestCase):
    def test_not_is_left_as_before(self):
        # NOT around metric_time is not handled (UPSTREAM.md P-11): the condition is still extracted
        # and a bare NOT remains, which MetricFlow renders as broken SQL exactly as before P-11.
        self.assertEqual(extract("NOT metric_time <= '2026-01-01'"), ("NOT", None, d(2026, 1, 1)))


class _FakeEngineCompiler(MetricFlowCompiler):
    """Engine mode without a manifest: compile() gets as far as _extract_time_constraints."""

    def __init__(self):  # noqa: D107 - no dbt project
        self._engine, self._engine_mode, self._init_error = object(), True, ""


class _NoPool:
    async def execute(self, *args, **kwargs):
        raise AssertionError("the pool must not be used when compile fails")


class TestOrSurfacesAsCompileError(unittest.IsolatedAsyncioTestCase):
    def test_compile_returns_the_message(self):
        for having in (None, "gmv > 0"):
            with self.subTest(having=having):
                sql, command, error = _FakeEngineCompiler().compile(["gmv"], ["metric_time__year"], OR_RANGES,
                                                                    having=having)
                self.assertIsNone(sql)
                self.assertTrue(command.startswith("mf query --metrics gmv"), command)
                self.assertTrue(error.startswith(OR_MESSAGE), error)

    async def test_query_metric_returns_internal_error(self):
        body = json.loads(await query_metric(_FakeEngineCompiler(), _NoPool(), ["gmv"], ["metric_time__year"],
                                             OR_RANGES))
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "INTERNAL_ERROR")
        self.assertTrue(body["error"]["message"].startswith(f"MetricFlow compile error: {OR_MESSAGE}"),
                        body["error"]["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

新文件 `doris/test/test_semantic_time.py`（编译出的 SQL 里查 `DATE_TRUNC('day', order_date) BETWEEN …`，确认 ecom 的模型上边界和粒度对齐都是预期的）：

<!-- file: doris/test/test_semantic_time.py sha256=23d6f573609ee885fe918d44ed2dd49450120788314dfcd3436d2e59cf1ea28c -->
```python
"""Offline: metric_time filters on the ecom models compile to the intended time range (P-11, no Doris).

    .venv/bin/python -m unittest discover -s doris/test -v

Compiled through doris/reconcile.py DirectBackend, i.e. bare names resolved and the SQL checked
read-only exactly like the MCP server's query_metric. MetricFlow renders the time constraint as an
inclusive `BETWEEN` aligned to the query grain.
"""

from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
sys.path.insert(0, str(ROOT / "doris"))

from reconcile import MODELS_DIR, Case, DirectBackend, ReconcileError  # noqa: E402

DAY_RANGE = "WHERE DATE_TRUNC('day', order_date) BETWEEN '{}' AND '{}'"


class SemanticTimeRange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.disable(logging.WARNING)  # MetricFlow is chatty at INFO/WARNING
        cls.tmp = tempfile.TemporaryDirectory(prefix="ecom_time_")
        cls.backend = DirectBackend(MODELS_DIR, cls.tmp.name, fetch=None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        logging.disable(logging.NOTSET)

    def sql(self, where: str, group_by: str = "metric_time__day", metrics: tuple[str, ...] = ("gmv",)) -> str:
        return self.backend.sql(Case("t", metrics, (group_by,), where, "SELECT 1"))

    def test_august_with_a_strict_end_is_31_days(self):
        sql = self.sql("metric_time >= '2026-08-01' AND metric_time < '2026-09-01'")
        self.assertIn(DAY_RANGE.format("2026-08-01", "2026-08-31"), sql)
        self.assertNotIn("2026-09-01", sql)

    def test_august_with_a_strict_start_is_31_days(self):
        sql = self.sql("metric_time > '2026-07-31' AND metric_time <= '2026-08-31'")
        self.assertIn(DAY_RANGE.format("2026-08-01", "2026-08-31"), sql)

    def test_strict_end_by_month_stops_before_the_next_month(self):
        # Without the shift the end 2026-10-01 is aligned to 2026-10-31 and October is added.
        sql = self.sql("metric_time >= '2026-09-01' AND metric_time < '2026-10-01'", "metric_time__month")
        self.assertIn(DAY_RANGE.format("2026-09-01", "2026-09-30"), sql)

    def test_day_filters_are_aligned_to_the_month_grain(self):
        # By design (reconcile yoy_2026 depends on it): an inclusive day end covers its whole month.
        sql = self.sql("metric_time >= '2026-09-01' AND metric_time <= '2026-09-25'", "metric_time__month")
        self.assertIn(DAY_RANGE.format("2026-09-01", "2026-09-30"), sql)

    def test_or_between_ranges_is_a_compile_error(self):
        where = ("(metric_time BETWEEN '2025-09-01' AND '2025-09-25') OR "
                 "(metric_time BETWEEN '2026-09-01' AND '2026-09-25')")
        with self.assertRaises(ReconcileError) as caught:
            self.sql(where, "metric_time__year")
        self.assertTrue(str(caught.exception).startswith(
            "compile failed: metric_time filters must be a single range joined with AND"), caught.exception)

    def test_or_in_a_sibling_group_stays_a_where_filter(self):
        sql = self.sql("metric_time >= '2026-08-01' AND (channel = 'APP' OR channel = 'WEB')")
        self.assertIn("Constrain Time Range to [2026-08-01T00:00:00,", sql)
        self.assertIn("WHERE (order_entity__channel = 'APP' OR order_entity__channel = 'WEB')", sql)

    def test_other_time_dimension_stays_a_where_filter(self):
        # order_date resolves to TimeDimension('order_entity__order_date', 'day'), not metric_time.
        sql = self.sql("order_date >= '2026-01-01'")
        self.assertNotIn("Constrain Time Range", sql)
        self.assertIn("WHERE order_entity__order_date__day >= '2026-01-01'", sql)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：确认失败**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' > /tmp/t53-red-server.log 2>&1; echo "server rc=$?"
.venv/bin/python -m unittest discover -s doris/test > /tmp/t53-red-doris.log 2>&1; echo "doris rc=$?"
for f in /tmp/t53-red-server.log /tmp/t53-red-doris.log; do
  grep -E '^(FAIL|ERROR):' "$f" | sed -E 's/^(FAIL|ERROR): [A-Za-z0-9_]+ \(([A-Za-z0-9_.]+)\).*/\1 \2/' | sort | uniq -c
  grep -E '^Ran |^OK|^FAILED' "$f"
done
grep -hE '^ImportError' /tmp/t53-red-server.log | sort | uniq -c
```
期望（实测）：
```
server rc=1
doris rc=1
      1 ERROR unittest.loader._FailedTest.test_agentcore_audit_errors
      1 FAIL test_agentcore_time_constraints.TestIntersection.test_earliest_end_wins
      1 FAIL test_agentcore_time_constraints.TestIntersection.test_latest_start_wins
      1 FAIL test_agentcore_time_constraints.TestOr.test_or_at_an_enclosing_level
      1 FAIL test_agentcore_time_constraints.TestOr.test_or_at_the_match_level
      1 FAIL test_agentcore_time_constraints.TestOr.test_or_between_ranges
      2 FAIL test_agentcore_time_constraints.TestOrSurfacesAsCompileError.test_compile_returns_the_message
      1 FAIL test_agentcore_time_constraints.TestOrSurfacesAsCompileError.test_query_metric_returns_internal_error
      1 FAIL test_agentcore_time_constraints.TestParenthesizedRange.test_group_mixing_time_and_other_filters
      1 FAIL test_agentcore_time_constraints.TestParenthesizedRange.test_range_group_after_an_or_group
      1 FAIL test_agentcore_time_constraints.TestParenthesizedRange.test_range_group_after_the_other_filter
      1 FAIL test_agentcore_time_constraints.TestParenthesizedRange.test_range_group_alone
      1 FAIL test_agentcore_time_constraints.TestParenthesizedRange.test_range_group_leaves_exactly_the_other_filter
      1 FAIL test_agentcore_time_constraints.TestStrictOperators.test_august_with_a_strict_end
      1 FAIL test_agentcore_time_constraints.TestStrictOperators.test_greater_than_a_date_starts_the_next_day
      1 FAIL test_agentcore_time_constraints.TestStrictOperators.test_less_than_a_date_ends_the_day_before
      1 FAIL test_agentcore_time_constraints.TestStrictOperators.test_time_part_shifts_by_one_second
      1 FAIL test_agentcore_time_constraints.TestTimeDimensionTemplate.test_mixed_with_metric_time
      1 FAIL test_agentcore_time_constraints.TestTimeDimensionTemplate.test_other_time_dimension_stays_in_where
Ran 125 tests in 0.459s
FAILED (failures=19, errors=1)
      1 FAIL test_semantic_time.SemanticTimeRange.test_august_with_a_strict_end_is_31_days
      1 FAIL test_semantic_time.SemanticTimeRange.test_august_with_a_strict_start_is_31_days
      1 FAIL test_semantic_time.SemanticTimeRange.test_or_between_ranges_is_a_compile_error
      1 FAIL test_semantic_time.SemanticTimeRange.test_other_time_dimension_stays_a_where_filter
      1 FAIL test_semantic_time.SemanticTimeRange.test_strict_end_by_month_stops_before_the_next_month
Ran 168 tests in 6.591s
FAILED (failures=5)
      1 ImportError: Failed to import test module: test_agentcore_audit_errors
      1 ImportError: cannot import name '_audit_error' from 'server' (/home/ubuntu/AI-code/Doris-mcp-skill-Demo/mcp-server/src/server.py)
```
失败的正是 Step 3 要做的：
- `test_agentcore_audit_errors` 整个模块 `ERROR`：它导入 `server._audit_error`（P-10），还不存在；模块里的 17 个检查都没有运行。
- `test_agentcore_time_constraints` 的 35 个检查里 19 个 `FAIL`（`test_compile_returns_the_message` 有 2 个 subTest，所以计数是 2）：严格比较、多个条件取交集、OR 返回编译错误、括号包住的范围、`TimeDimension('metric_time', …)` 模板，都是 P-11 要改的。其余 16 个（`BETWEEN` 包含两端、NOT 不改、字面量里的 `OR` 和括号、粒度后缀等）在旧代码上已经通过，锁定不该变的行为。
- `doris/test` 的 `test_semantic_time` 7 个里 5 个 `FAIL`（经真实的 MetricFlow 编译）；「日过滤按月粒度对齐」「兄弟分组里的 OR 仍是 where 过滤」2 个已经通过，锁定现状（MetricFlow 的设计，不改）。
- 其余已有的测试（`test_agentcore_*.py` 89 个、`doris/test` 161 个）都通过。

失败的项目或个数不同时，先查明原因，不要进入 Step 3。

- [ ] **Step 3：实现 P-10、P-11**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py t57a-impl.diff /tmp/t57a-impl.diff
git apply /tmp/t57a-impl.diff && git status --short && git diff --shortstat
```
期望（实测）：
```
t57a-impl.diff -> /tmp/t57a-impl.diff (247 lines)
 M mcp-server/UPSTREAM.md
 M mcp-server/src/server.py
 M mcp-server/src/store/compiler.py
?? doris/test/test_semantic_time.py
?? mcp-server/test/test_agentcore_audit_errors.py
?? mcp-server/test/test_agentcore_time_constraints.py
 3 files changed, 117 insertions(+), 30 deletions(-)
```

<!-- file: t57a-impl.diff sha256=e46f4ad44025a0a50262b633e18ad33f271fb2c80e66ce9bcdfa7de9f84e8917 -->
```diff
diff --git a/mcp-server/UPSTREAM.md b/mcp-server/UPSTREAM.md
index 022f6a7..38dc052 100644
--- a/mcp-server/UPSTREAM.md
+++ b/mcp-server/UPSTREAM.md
@@ -17,14 +17,20 @@
 | P-05 | `src/tools/profile.py` (new) | `list_recent_queries`, `get_query_profile` |
 | P-06 | `config/mcp-server.toml` (new) | runtime limits (50 s SQL timeout, pool 5, 2000 rows) |
 | P-07 | `pyproject.toml` (new) | dependencies pinned to upstream `uv.lock` + boto3 (+ 2 transitive pins that keep the CodeZip equal to the tested `.venv`), for AgentCore CodeZip |
-| P-08 | `test/test_agentcore_*.py` (new) | tests for P-01..P-06 |
+| P-08 | `test/test_agentcore_*.py` (new) | tests for P-01..P-06, P-10 (`test_agentcore_audit_errors.py`) and P-11 (`test_agentcore_time_constraints.py`) |
 | P-09 | `src/config/loader.py`, `src/core/connection.py`, `config/mcp-server.toml`, `test/test_agentcore_session_timeout.py` (new) | `SET wait_timeout` on every pool connection (`session_wait_timeout_seconds = 600`), so Doris reaps what a torn-down Runtime microVM left open |
+| P-10 | `src/server.py` | the audit record of a failed `execute_query` / `query_metric` carries `error` (`CODE: message`, 300 chars, masked); `query_metric` takes success from the parsed result, logs the resolved `where` plus `having`, `order_by`, `limit`, and its `mf_command` gains `--where`/`--order-by`/`--limit`/`--having` |
+| P-11 | `src/store/compiler.py`, `../doris/test/test_semantic_time.py` (new) | `_extract_time_constraints`: an OR around a metric_time condition raises `ValueError` (returned as the compile error) instead of compiling to `WHERE () OR ()`; strict `>` / `<` shift the bound by 1 day (1 s with a time part); only `TimeDimension('metric_time', ...)` is extracted; several conditions intersect; a parenthesized range leaves no `( AND )` behind |
 
-Only P-02, P-03, P-04 and P-09 touch upstream files; without service credentials and without
-`session_wait_timeout_seconds` they behave exactly like upstream.
+Only P-02, P-03, P-04, P-09, P-10 and P-11 touch upstream files; without service credentials and without
+`session_wait_timeout_seconds`, P-02/P-03/P-04/P-09 behave exactly like upstream. P-10 and P-11 change upstream
+behaviour on purpose (audit content, metric_time filters).
+
+NOT around a metric_time condition (`NOT metric_time < 'x'`) is not handled by P-11: the condition is still
+extracted and a bare `NOT` is left in the where, as upstream does.
 
 ## Upgrading upstream
 
 1. `git archive <new-commit> src test LICENSE.txt NOTICE mcp-server.toml requirements.txt` into a scratch dir and diff it against the vendored commit.
-2. Replace the vendored files, then re-apply P-02/P-03/P-04/P-09 (`git log --oneline -- mcp-server/src` lists their commits).
+2. Replace the vendored files, then re-apply P-02/P-03/P-04/P-09/P-10/P-11 (`git log --oneline -- mcp-server/src` lists their commits).
 3. Update the pins in `pyproject.toml` from the new `uv.lock`, then run the upstream offline suite and `test_agentcore_*.py`.
diff --git a/mcp-server/src/server.py b/mcp-server/src/server.py
index eb2e677..7ccc37d 100644
--- a/mcp-server/src/server.py
+++ b/mcp-server/src/server.py
@@ -4,6 +4,7 @@ from __future__ import annotations
 
 import asyncio
 import ipaddress
+import json
 import logging
 import os
 import re
@@ -129,6 +130,29 @@ def _reload_error_code(msg: str) -> ErrorCode:
     return ErrorCode.INTERNAL_ERROR
 
 
+def _audit_error(result: str) -> str | None:
+    """Return "CODE: message" of a failed tool result for the audit log, else None.
+
+    Cut to 300 characters; log_tool_call masks it like the params.
+    """
+    try:
+        body = json.loads(result)
+    except (TypeError, ValueError):
+        return None
+    if not isinstance(body, dict) or body.get("success") is not False:
+        return None
+    error = body.get("error")
+    if not isinstance(error, dict):
+        error = {"message": error}
+    text = ": ".join(str(part) for part in (error.get("code"), error.get("message")) if part)
+    return (text or "unknown error")[:300]
+
+
+def _mf_quote(value: str) -> str:
+    """Double-quote a value for the informational mf CLI command in the audit log."""
+    return '"' + value.replace('"', '\\"') + '"'
+
+
 def _encode_webui_session_cookie(session_id: str, server_ip: str) -> str:
     """Encode a Web UI session ID with the issuing server's IPv4 address."""
     if not session_id or "." in session_id:
@@ -961,7 +985,7 @@ def create_server(
         actual_success = parsed.get("success", False)
 
         log_tool_call("execute_query", client_id=auth.client_id, params={"sql": mask_sensitive(sql[:200]), "database": database},
-                      success=actual_success, duration_ms=duration, metricflow=False)
+                      success=actual_success, error=_audit_error(result), duration_ms=duration, metricflow=False)
         return result
 
     @mcp.tool(
@@ -1165,12 +1189,23 @@ def create_server(
         from tools.semantic import query_metric as _query_metric
         result = await _query_metric(ws.compiler, pool, metrics, group_by or None, where or None, order_by or None, limit or None, database or None, max_rows or None, having or None)
         duration = (time.monotonic() - start) * 1000
-        success = '"success": true' in result
+        error = _audit_error(result)
         mf_cmd = f"mf query --metrics {','.join(metrics)}"
         if group_by:
             mf_cmd += f" --group-by {','.join(group_by)}"
-        log_tool_call("query_metric", client_id=auth.client_id, params={"metrics": metrics, "group_by": group_by},
-                      success=success, duration_ms=duration, metricflow=True, mf_command=mf_cmd)
+        if where:
+            mf_cmd += f" --where {_mf_quote(where)}"
+        if order_by:
+            mf_cmd += f" --order-by {','.join(order_by)}"
+        if limit:
+            mf_cmd += f" --limit {limit}"
+        if having:
+            mf_cmd += f" --having {_mf_quote(having)}"
+        # where is the resolved filter that was compiled; unset filters are logged empty.
+        log_tool_call("query_metric", client_id=auth.client_id,
+                      params={"metrics": metrics, "group_by": group_by, "where": where, "having": having,
+                              "order_by": order_by, "limit": limit},
+                      success=error is None, error=error, duration_ms=duration, metricflow=True, mf_command=mf_cmd)
         return result
 
     # ========== Manual reload Tool ==========
diff --git a/mcp-server/src/store/compiler.py b/mcp-server/src/store/compiler.py
index f3dc11f..6ba0584 100644
--- a/mcp-server/src/store/compiler.py
+++ b/mcp-server/src/store/compiler.py
@@ -17,6 +17,13 @@ _SENTINEL_NO_JSON = object()
 _STRING_LITERAL_RE = re.compile(r"'(?:[^'\\]|\\.|'')*'|\"(?:[^\"\\]|\\.|\"\")*\"")
 _MASKED_LITERAL_RE = re.compile("\x00(\\d+)\x00")
 
+# Returned to the calling agent (via query_metric's compile error) for an OR around metric_time.
+_METRIC_TIME_OR_ERROR = (
+    "metric_time filters must be a single range joined with AND (no OR around a metric_time "
+    "condition). Make one query_metric call per range; for period-over-period comparisons use "
+    "the offset metrics (e.g. *_last_year) grouped by metric_time instead."
+)
+
 # Try to import MetricFlow engine
 _ENGINE_AVAILABLE = False
 try:
@@ -525,22 +532,29 @@ class MetricFlowCompiler:
           "metric_time >= '2026-02-01' AND metric_time <= '2026-02-28'"  → start, end, remaining=None
           "metric_time >= '2026-02-01' AND channel = 'APP'"  → start, remaining="channel = 'APP'"
           "{{ TimeDimension('metric_time', 'day') }} >= '2026-02-01'"  → same
+          "metric_time BETWEEN '2026-02-01' AND '2026-02-28'"  → start, end
+          "metric_time >= '2026-08-01' AND metric_time < '2026-09-01'"  → start, end=datetime(2026,8,31)
+          "(metric_time >= '2026-01-01' AND metric_time < '2026-02-01') AND channel = 'X'"  → remaining="channel = 'X'"
+
+        The range is inclusive: `>` / `<` move a date-only bound by one day, a bound with a time
+        part by one second. Several conditions intersect (latest start, earliest end). Only
+        metric_time is extracted (bare, metric_time__<grain> or TimeDimension('metric_time', ...));
+        other time dimensions stay in the where. A metric_time condition inside a group that has
+        a top-level OR (its own parenthesis level or an enclosing one; quoted literals ignored)
+        raises ValueError. NOT around metric_time is not handled.
 
         Returns (remaining_where, time_start, time_end).
         """
         if not where or not where.strip():
             return None, None, None
 
-        from datetime import datetime
+        from datetime import datetime, timedelta
         import re
 
-        time_start = None
-        time_end = None
-
-        # Match patterns: metric_time >= 'date' or "date", {{ TimeDimension(...) }} >= 'date'
+        # Match patterns: metric_time >= 'date' or "date", {{ TimeDimension('metric_time', ...) }} >= 'date'
         # Supports both single and double quotes around dates
         _TIME_PATTERN = re.compile(
-            r"""(?:{{[^}]*TimeDimension\([^)]*\)[^}]*}}|metric_time(?:__\w+)?)\s*"""
+            r"""(?:{{[^}]*TimeDimension\(\s*['"]metric_time['"][^)]*\)[^}]*}}|metric_time(?:__\w+)?)\s*"""
             r"""(>=?|<=?|BETWEEN)\s*['"](\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2})?)['"]"""
             r"""(?:\s+AND\s+['"](\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2})?)['"])?""",
             re.IGNORECASE
@@ -554,37 +568,69 @@ class MetricFlowCompiler:
                     continue
             return datetime.strptime(s[:10], "%Y-%m-%d")
 
+        def _scan(text: str) -> tuple[list[int], set[int]]:
+            """Parentheses still open at the end of text (-1 = top level) and the groups with an OR."""
+            stack, with_or = [-1], set()
+            for token in re.finditer(r"[()]|\bOR\b", text, re.IGNORECASE):
+                if token.group() == "(":
+                    stack.append(token.start())
+                elif token.group() == ")":
+                    if len(stack) > 1:
+                        stack.pop()
+                else:
+                    with_or.add(stack[-1])
+            return stack, with_or
+
         # Collect all matches first, then remove them from the string
         matches = list(_TIME_PATTERN.finditer(where))
         if not matches:
             return where, None, None
 
+        # A time constraint applies to the whole query, so it cannot stand for one branch of an OR.
+        # Literals are blanked (same length) so a quoted OR or parenthesis does not count.
+        masked = _STRING_LITERAL_RE.sub(lambda m: " " * len(m.group(0)), where)
+        or_groups = _scan(masked)[1]
+        if any(or_groups.intersection(_scan(masked[:match.start()])[0]) for match in matches):
+            raise ValueError(_METRIC_TIME_OR_ERROR)
+
+        starts: list[datetime] = []
+        ends: list[datetime] = []
         for match in matches:
             op = match.group(1).upper()
             date1 = match.group(2)
             date2 = match.group(3)
+            step = timedelta(days=1) if len(date1) == 10 else timedelta(seconds=1)
 
             if op == "BETWEEN" and date2:
-                time_start = _parse_dt(date1)
-                time_end = _parse_dt(date2)
-            elif op in (">=", ">"):
-                time_start = _parse_dt(date1)
-            elif op in ("<=", "<"):
-                time_end = _parse_dt(date1)
-
-        if time_start is None and time_end is None:
+                starts.append(_parse_dt(date1))
+                ends.append(_parse_dt(date2))
+            elif op == ">=":
+                starts.append(_parse_dt(date1))
+            elif op == ">":
+                starts.append(_parse_dt(date1) + step)
+            elif op == "<=":
+                ends.append(_parse_dt(date1))
+            elif op == "<":
+                ends.append(_parse_dt(date1) - step)
+
+        if not starts and not ends:
             return where, None, None
+        # AND-ed conditions intersect
+        time_start = max(starts, default=None)
+        time_end = min(ends, default=None)
 
-        # Remove matched spans from string (reverse order to preserve positions)
+        # Replace each matched span with a TRUE marker, then drop the markers together with their
+        # AND and the parentheses left around them: "(a AND b) AND c" -> "c".
         remaining = where
         for match in reversed(matches):
-            remaining = remaining[:match.start()] + remaining[match.end():]
-
-        # Robust cleanup of remaining string
-        for _ in range(3):
-            remaining = re.sub(r'^\s*AND\s+', '', remaining, flags=re.IGNORECASE)
-            remaining = re.sub(r'\s+AND\s*$', '', remaining, flags=re.IGNORECASE)
-            remaining = re.sub(r'\s+AND\s+AND\s+', ' AND ', remaining, flags=re.IGNORECASE)
+            remaining = remaining[:match.start()] + "\x01" + remaining[match.end():]
+        previous = None
+        while remaining != previous:
+            previous = remaining
+            remaining = re.sub(r"\(\s*\x01\s*\)", "\x01", remaining)
+            remaining = re.sub(r"\x01\s*\bAND\b\s*", "", remaining, flags=re.IGNORECASE)
+            remaining = re.sub(r"\s*\bAND\b\s*\x01", "", remaining, flags=re.IGNORECASE)
+        remaining = remaining.replace("\x01", "")
         # Strip whitespace, quotes, parentheses that are now empty wrappers
         remaining = remaining.strip()
         remaining = re.sub(r'^["\'\s()]+$', '', remaining)  # Only quotes/parens/spaces → empty
```

- [ ] **Step 4：确认通过；突变**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 期望：Ran 141 tests … OK
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 168 tests … OK
.venv/bin/python -m unittest discover -s quick/test 2>&1 | tail -3                                  # 期望：Ran 50 tests … OK
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 期望：Ran 113 tests … OK
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3     # 期望：🎉 All tests passed!
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json p10; echo "rc=$?"
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json p11; echo "rc=$?"
```
期望（实测，秒数每次不同）：
```
Ran 141 tests in 0.747s

OK
Ran 168 tests in 6.633s

OK
Ran 50 tests in 0.170s

OK
Ran 113 tests in 1.993s

OK
═══════════════════════════════════
  🎉 All tests passed!
═══════════════════════════════════
p10-1: caught by test_compile_failure_records_the_error_text, test_doris_failure_records_the_error_text, test_error_echoing_a_password_is_masked, test_failure_is_code_and_message, test_failure_records_the_error_text, test_missing_code_or_message, test_rejected_sql_records_the_reason, test_truncated_to_300_chars (Ran 141, FAILED (failures=7, errors=4))
p10-2: caught by test_error_echoing_a_password_is_masked, test_failure_records_the_error_text, test_rejected_sql_records_the_reason (Ran 141, FAILED (errors=3))
p10-3: caught by test_success_is_parsed_not_substring_matched (Ran 141, FAILED (failures=1))
p10-4: caught by test_compile_failure_records_the_error_text, test_password_literal_in_where_is_masked, test_records_resolved_filters, test_unset_filters_are_logged_empty_and_left_out_of_mf_command (Ran 141, FAILED (failures=2, errors=2))
p10-5: caught by test_truncated_to_300_chars (Ran 141, FAILED (failures=1))
p10-6: caught by test_compile_failure_records_the_error_text, test_doris_failure_records_the_error_text (Ran 141, FAILED (errors=2))
p10-7: caught by test_records_resolved_filters, test_unset_filters_are_logged_empty_and_left_out_of_mf_command (Ran 141, FAILED (failures=2))
p10-8: caught by test_records_resolved_filters, test_unset_filters_are_logged_empty_and_left_out_of_mf_command (Ran 141, FAILED (failures=2))
p10-9: caught by test_double_quotes_in_where_are_escaped_in_mf_command, test_password_literal_in_where_is_masked, test_records_resolved_filters (Ran 141, FAILED (failures=3))
p10-10: caught by test_records_resolved_filters (Ran 141, FAILED (failures=1))
p10-11: caught by test_records_resolved_filters (Ran 141, FAILED (failures=1))
p10-12: caught by test_double_quotes_in_where_are_escaped_in_mf_command, test_unset_filters_are_logged_empty_and_left_out_of_mf_command (Ran 141, FAILED (failures=2))
p10-13: caught by test_double_quotes_in_where_are_escaped_in_mf_command (Ran 141, FAILED (failures=1))
p10-14: caught by test_not_json_or_not_an_object_is_none (Ran 141, FAILED (failures=1))
p10-15: caught by test_not_json_or_not_an_object_is_none (Ran 141, FAILED (errors=3))
p10-16: caught by test_missing_code_or_message (Ran 141, FAILED (failures=4))
p10-17: caught by test_missing_code_or_message (Ran 141, FAILED (failures=1))
p10-18: caught by test_missing_code_or_message (Ran 141, FAILED (failures=1))
p10-19: caught by test_sql_is_masked_and_cut_to_200_chars (Ran 141, FAILED (failures=1))
p10-20: caught by test_error_echoing_a_password_is_masked (Ran 141, FAILED (failures=1))
p10-21: caught by test_password_literal_in_where_is_masked (Ran 141, FAILED (failures=1))
21/21 mutations caught; tree unchanged: True
rc=0
p11-1: caught by test_compile_returns_the_message, test_or_at_an_enclosing_level, test_or_at_the_match_level, test_or_between_ranges, test_or_between_ranges_is_a_compile_error, test_query_metric_returns_internal_error (Ran 42, FAILED (failures=7))
p11-2: caught by test_compile_returns_the_message, test_or_at_an_enclosing_level, test_or_between_ranges, test_or_between_ranges_is_a_compile_error, test_query_metric_returns_internal_error (Ran 42, FAILED (failures=6))
p11-3: caught by test_or_inside_a_literal_is_not_an_or, test_parentheses_inside_a_literal_are_ignored (Ran 42, FAILED (errors=2))
p11-4: caught by test_august_with_a_strict_start_is_31_days, test_greater_than_a_date_starts_the_next_day, test_time_part_shifts_by_one_second (Ran 42, FAILED (failures=3))
p11-5: caught by test_august_with_a_strict_end, test_august_with_a_strict_end_is_31_days, test_less_than_a_date_ends_the_day_before, test_range_group_leaves_exactly_the_other_filter, test_strict_end_by_month_stops_before_the_next_month, test_time_part_shifts_by_one_second (Ran 42, FAILED (failures=6))
p11-6: caught by test_mixed_with_metric_time, test_other_time_dimension_stays_a_where_filter, test_other_time_dimension_stays_in_where (Ran 42, FAILED (failures=3))
p11-7: caught by test_earliest_end_wins, test_latest_start_wins (Ran 42, FAILED (failures=2))
p11-8: caught by test_range_group_after_an_or_group, test_range_group_after_the_other_filter, test_range_group_alone, test_range_group_leaves_exactly_the_other_filter (Ran 42, FAILED (failures=4))
p11-9: caught by test_range_group_leaves_exactly_the_other_filter (Ran 42, FAILED (failures=1))
p11-10: caught by test_between_with_other_filter, test_mixed_with_metric_time, test_or_in_a_sibling_group_is_kept, test_or_in_a_sibling_group_stays_a_where_filter, test_or_inside_a_literal_is_not_an_or, test_other_filters_remain, test_range_group_leaves_exactly_the_other_filter, test_time_dimension_template (Ran 42, FAILED (failures=8))
p11-11: caught by test_group_mixing_time_and_other_filters, test_parentheses_inside_a_literal_are_ignored, test_range_group_after_an_or_group, test_range_group_after_the_other_filter (Ran 42, FAILED (failures=4))
p11-12: caught by test_august_with_a_strict_end, test_between_is_inclusive, test_double_quoted_literals, test_earliest_end_wins, test_grain_suffix_names, test_greater_than_a_date_starts_the_next_day, test_latest_start_wins, test_less_than_a_date_ends_the_day_before, test_not_is_left_as_before, test_outer_quotes_only_leftover_is_none, test_range_group_alone, test_spaces_double_quotes_and_grain, test_start_and_end, test_start_only, test_time_dimension_template, test_time_part, test_time_part_shifts_by_one_second (Ran 42, FAILED (failures=17))
p11-13: caught by test_time_part_shifts_by_one_second (Ran 42, FAILED (failures=1))
p11-14: caught by test_or_in_a_sibling_group_is_kept, test_or_in_a_sibling_group_stays_a_where_filter, test_parentheses_inside_a_literal_are_ignored, test_range_group_after_an_or_group (Ran 42, FAILED (errors=4))
p11-15: caught by test_between_is_inclusive, test_between_with_other_filter, test_earliest_end_wins, test_range_group_after_the_other_filter (Ran 42, FAILED (failures=4))
p11-16: caught by test_spaces_double_quotes_and_grain (Ran 42, FAILED (failures=1))
p11-17: caught by test_spaces_double_quotes_and_grain (Ran 42, FAILED (failures=1))
p11-18: caught by test_or_at_an_enclosing_level, test_or_at_the_match_level, test_or_between_ranges (Ran 42, FAILED (failures=3))
p11-19: caught by test_compile_returns_the_message, test_or_between_ranges_is_a_compile_error, test_query_metric_returns_internal_error (Ran 42, FAILED (failures=1, errors=3))
p11-20: caught by test_august_with_a_strict_end_is_31_days, test_august_with_a_strict_start_is_31_days, test_day_filters_are_aligned_to_the_month_grain, test_strict_end_by_month_stops_before_the_next_month (Ran 42, FAILED (failures=4))
20/20 mutations caught; tree unchanged: True
rc=0
```

- [ ] **Step 5：收尾，提交**

T5.7a 要到 Task 6 部署之后才勾选；这里只更新状态和日志。
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
echo 'Task 3（T5.7a 代码）已完成（P-10、P-11 未部署，Task 6 部署）；Task 4（T5.7b）从 Step 1 开始' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo 'Task 4（T5.7b），然后 Task 5（demo-check / cleanup 脚本）、Task 6（部署，GATE）、Task 7（整体评审，再交给用户导入 skill 和彩排 2 轮）、Task 8（T5.5）、Task 9（演示结束后清理，GATE）' | .venv/bin/python /tmp/p5-progress.py state 下一步
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 3（T5.7a 代码）：P-10 审计、P-11 metric_time 过滤

- P-10（`src/server.py`）：失败的 `execute_query` / `query_metric` 的审计记录带 `error`（`CODE: message`，300 字符，经 mask）；`query_metric` 的成败取自解析后的结果，审计记下 `where`、`having`、`order_by`、`limit`，`mf_command` 补上对应的选项。
- P-11（`src/store/compiler.py`）：OR 包住 metric_time 条件时返回编译错误（`INTERNAL_ERROR`，提示每个范围调用一次或用 `*_last_year`）；`>` / `<` 严格比较；多个条件取交集；只认 `TimeDimension('metric_time', …)`；括号包住的范围不再留下 `( AND )`。按分组粒度对齐（MetricFlow 的设计）和 NOT 不改，测试锁定现状。
- RED：`test_agentcore_audit_errors` 整个模块 `ERROR`（没有 `_audit_error`）；`test_agentcore_time_constraints` 35 个里 19 个 `FAIL`，`test_semantic_time` 7 个里 5 个 `FAIL`；其余已有的测试通过。
- GREEN：`test_agentcore_*.py` 141、`doris/test` 168、`quick/test` 50、`scripts/test` 113、upstream 离线测试通过；突变 p10 21/21、p11 20/20 被抓到。还没有部署（Task 6）。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add mcp-server/src/server.py mcp-server/src/store/compiler.py mcp-server/UPSTREAM.md \
        mcp-server/test/test_agentcore_audit_errors.py mcp-server/test/test_agentcore_time_constraints.py doris/test/test_semantic_time.py \
        specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
feat(p5): T5.7a P-10 audit error and query_metric filters, P-11 metric_time filters (OR, strict bounds, intersection, groups)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望（实测）：
```
进行中: written (751 lines)
下一步: written (751 lines)
### 2026-09-28 P5 Task 3（T5.7a 代码）：P-10 审计、P-11 metric_time 过滤: written (758 lines)
check-secrets: OK (844 files scanned)
0
feat(p5): T5.7a P-10 audit error and query_metric filters, P-11 metric_time filters (OR, strict bounds, intersection, groups)
```
日志里的数字如果和实测不同，写实测值。

---

### Task 4：T5.7b P4 评审 Minor：`audit_check --failures`、`gw_latency` 的时间戳和序列合并、`mcp_smoke` 的 mask

来源：tasks.md T5.7b，P4 整体评审的 M-7 / M-8 / M-9 / M-10（progress.md 的 P4 日志）。M-7 是文档（审计里的工具名不带 `doris___` 前缀），写进 Task 7 的 `quick/runbook.md`；M-10 已经体现在本计划每个提交块的 IP 计数里（`$v` 为空时输出 FAIL）。这里只改 3 个脚本。spec 阶段的发现：

| # | spec 阶段的发现（`bcda0f3` 的脚本）| 处理 | 测试 |
|---|---|---|---|
| 1 | `audit_check.py` 只输出计数：彩排后要知道哪次调用失败、为什么失败，只能去 CloudWatch 翻原始记录（里面有 SQL 和连接信息）| `--failures`：摘要之后按时间列出每个失败的调用：时间、工具、`error`（压成一行，IPv4 换成 `<ip>`，截到 200 字符，先 mask 再截断，地址不会被截成半个）；`query_metric` 另列 `group_by` / `where` / `having`。不输出 SQL、其他参数、MetricFlow 命令、client id。Task 3 之前写的记录没有 `error`，显示 `(not recorded)`。exit code 不变 | `TestFailures` 12 个 |
| 2 | M-9：`gw_latency.py` 用 `str(at)[:16]` 取分钟：数字时间戳（epoch 秒）变成乱码，带时区偏移的时间取的是当地分钟 | `_minute(at)`：epoch 秒、`Z`、`±HH:MM`、不带时区（按 UTC）都换成 UTC 分钟 | `Minute` 2 个（本机时区设成 `IST-5:30`，确认不受本机时区影响）|
| 3 | M-9：CloudWatch `SEARCH` 对同一个工具可能返回几条序列（其他维度的每个值一条），同一分钟后一条覆盖前一条；平均值没法合并 | 统计量从 `Average` 改成 `Sum`：同一工具同一分钟的序列合并，调用数和总耗时相加，最大值取最大，平均 = 总耗时 / 调用数 | `test_series_of_one_tool_and_minute_merge`、`test_the_same_minute_in_any_timestamp_form_merges`；`Queries` 和 `Report` 的 fixture 改成 `sum` |
| 4 | M-8：`mcp_smoke.py --stdio`（经 `mcp-proxy-for-aws` 访问 Runtime）时，命令里的 URL 不在 mask 列表里，MCP SDK 的日志行也只在 `--url` 时 mask | `hidden_values(args)`：`--url` 的 URL，或 `--stdio` 命令里每个带 `://` 的词，加上它们的主机名和 bearer token；SDK 日志行对所有 transport 都 mask | `TestHiddenValues` 5 个；`TestErrorsAreMasked` 的 2 个 stdio 用例 |
| 5 | M-8：DNS 错误只写主机名（`Failed to resolve '<host>'`），URL 整体 mask 抓不到 | 主机名单独进 mask 列表（去掉端口和 user）| `test_a_dns_error_naming_only_the_host_is_masked`、`test_the_host_name_without_port_or_user` |
| 6 | `--stdio` 子进程（`mcp-proxy-for-aws`）自己的 stderr 直接到终端，这个脚本管不到 | 不改：docstring 写明；P5 的演示检查只用 `--url`（经 Gateway），Runtime 走 `reconcile` / `permission_matrix` | 无（记为未解决的 Minor）|

**Files:**
- Modify: `scripts/audit_check.py`（`--failures`、`failure_lines`、`ERROR_CHARS`、`FAILURE_PARAMS`）、`scripts/gw_latency.py`（`STATS`、`MERGE`、`_minute`、`parse_rows`）、`scripts/mcp_smoke.py`（`hidden_values`，`main` 里对所有 transport 调 `redact_sdk_logs`）
- Test: `scripts/test/test_audit_check.py`（+12）、`scripts/test/test_gw_latency.py`（+4，改 2 处 fixture）、`scripts/test/test_mcp_smoke.py`（+8）。`scripts/test` 113 → 137

**Interfaces:**
- Consumes：Task 3 的审计记录格式（`tool`、`success`、`timestamp`、`params.group_by` / `where` / `having`、失败时的 `error`）；`bcda0f3` 的 `redact.redact(text, hidden)`（先换字面值，再换 IPv4）、`redact.redact_sdk_logs(hidden)`、`mcp_smoke.parse_args`、`mcp_smoke.load_calls`、`gw_latency.queries(arn)` / `report`。
- Produces（Task 5 的 `demo-check.sh post` 和 Task 7 的 runbook 使用）：
  - `audit_check.py --failures`：摘要之后一行 `failures: N`，每个失败一行 `  <timestamp>  <tool>  <error>`，`query_metric` 再跟 `      where: …` 等；`audit_check.failure_lines(records) -> list[str]`；
  - `gw_latency.py queries` 的 3 个查询 Id 是 `calls` / `sum` / `max`；`report` 的输出格式不变（每行 `  <UTC 分钟>  <tool>  N calls  avg … ms  max … ms`）；`gw_latency._minute(at: float | str) -> str`；
  - `mcp_smoke.hidden_values(args) -> list[str]`。

- [ ] **Step 1：写失败测试**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py t57b-tests.diff /tmp/t57b-tests.diff
git apply /tmp/t57b-tests.diff && git status --short && git diff --shortstat
```
期望（实测）：
```
t57b-tests.diff -> /tmp/t57b-tests.diff (327 lines)
 M scripts/test/test_audit_check.py
 M scripts/test/test_gw_latency.py
 M scripts/test/test_mcp_smoke.py
 3 files changed, 236 insertions(+), 7 deletions(-)
```

fixture 的 IP 用 TEST-NET（`198.51.100.7`、`203.0.113.45`），主机名用 `*.example.test`：

<!-- file: t57b-tests.diff sha256=197dafe3e079371ff392cace16acbf83ec941b14ccfb85c9db6506dad601a0e9 -->
```diff
diff --git a/scripts/test/test_audit_check.py b/scripts/test/test_audit_check.py
index 77912b7..2b1c8bd 100644
--- a/scripts/test/test_audit_check.py
+++ b/scripts/test/test_audit_check.py
@@ -101,6 +101,125 @@ class TestAuditCheck(_Case):
                 self.assertIn("FAIL: input is not", out)
 
 
+class TestFailures(_Case):
+    """--failures: each failed call's time, tool and error (IPv4-masked, cut), plus query_metric's filters."""
+
+    SUMMARY = ("audit: 2 records (1 ok, 1 failed), 0 unreadable\n"
+               "  execute_query                  0 ok   1 failed  (expected >= 1)\n"
+               "  list_metrics                   1 ok   0 failed  (expected >= 1)\n"
+               "  [PASS] every expected call audited: 2/2 tools\n")
+
+    def two_calls(self) -> str:
+        return events(audit_line("execute_query", False, error="CONNECTION_ERROR: 198.51.100.7"),
+                      audit_line("list_metrics"))
+
+    def test_without_the_flag_the_output_is_unchanged(self):
+        self.assertEqual(self.run_check(self.two_calls(), "--calls", str(self.calls)), (0, self.SUMMARY))
+
+    def test_the_section_follows_the_unchanged_summary(self):
+        rc, out = self.run_check(self.two_calls(), "--calls", str(self.calls), "--failures")
+        self.assertEqual(rc, 0, out)
+        self.assertEqual(out, self.SUMMARY + "failures: 1\n"
+                              "  2026-09-27T08:00:00+0000  execute_query  CONNECTION_ERROR: <ip>\n")
+
+    def test_the_error_text_is_shown_ip_masked(self):
+        _, out = self.run_check(events(audit_line(
+            "execute_query", False, error="CONNECTION_ERROR: (2003, \"Can't connect to MySQL server on "
+                                          "'198.51.100.7' ([Errno 111] Connection refused)\")")), "--failures")
+        self.assertEqual(out.splitlines()[-2:], [
+            "failures: 1",
+            "  2026-09-27T08:00:00+0000  execute_query  CONNECTION_ERROR: (2003, \"Can't connect to MySQL server "
+            "on '<ip>' ([Errno 111] Connection refused)\")"])
+        self.assertNotIn("198.51.100.7", out)
+
+    def test_a_failure_without_an_error_says_not_recorded(self):
+        # Records written before the server recorded the error text have no "error" key.
+        _, out = self.run_check(events(audit_line("describe_table", False)), "--failures")
+        self.assertEqual(out.splitlines()[-1], "  2026-09-27T08:00:00+0000  describe_table  (not recorded)")
+
+    def test_the_error_is_cut_at_200_chars(self):
+        error = "QUERY_ERROR: " + "x" * 287  # 300 chars, the server's cap
+        _, out = self.run_check(events(audit_line("execute_query", False, error=error)), "--failures")
+        self.assertEqual(out.splitlines()[-1], "  2026-09-27T08:00:00+0000  execute_query  " + error[:200])
+
+    def test_an_address_across_the_cut_is_masked_not_split(self):
+        head = "CONNECTION_ERROR: " + "y" * 172 + " at "  # the address starts at char 194
+        _, out = self.run_check(events(audit_line("execute_query", False, error=head + "203.0.113.45:9030 refused")),
+                                "--failures")
+        self.assertEqual(out.splitlines()[-1],
+                         "  2026-09-27T08:00:00+0000  execute_query  " + (head + "<ip>:9030 refused")[:200])
+        self.assertNotIn("203.0", out)
+
+    def test_a_multi_line_error_stays_on_one_line(self):
+        _, out = self.run_check(events(audit_line("query_metric", False, params={"where": "a = 1\n  AND b = 2"},
+                                                  error="QUERY_ERROR: first line\n  second line")), "--failures")
+        self.assertEqual(out.splitlines()[-2:], ["  2026-09-27T08:00:00+0000  query_metric  QUERY_ERROR: first line "
+                                                 "second line",
+                                                 "      where: a = 1 AND b = 2"])
+
+    def test_query_metric_failures_show_group_by_where_and_having_ip_masked(self):
+        full = {"metrics": "['secret_metric_x']", "group_by": "['metric_time__month', 'user__city']",
+                "where": "{{ Dimension('order__client_ip') }} = '203.0.113.9'", "having": "gmv > 100",
+                "order_by": "['-secret_order_y']", "limit": "10"}
+        _, out = self.run_check(events(
+            audit_line("query_metric", False, params=full, query_path="metricflow",
+                       mf_command="mf query --metrics secret_mf_z", error="INVALID_PARAMS: unknown user__city"),
+            audit_line("query_metric", False, timestamp="2026-09-27T08:01:00+0000",
+                       params={"metrics": "['gmv']", "group_by": "['metric_time__day']"}, error="QUERY_TIMEOUT")),
+            "--failures")
+        self.assertEqual(out.splitlines()[-7:], [
+            "failures: 2",
+            "  2026-09-27T08:00:00+0000  query_metric  INVALID_PARAMS: unknown user__city",
+            "      group_by: ['metric_time__month', 'user__city']",
+            "      where: {{ Dimension('order__client_ip') }} = '<ip>'",
+            "      having: gmv > 100",
+            "  2026-09-27T08:01:00+0000  query_metric  QUERY_TIMEOUT",
+            "      group_by: ['metric_time__day']"])
+        for leaked in ("secret_metric_x", "secret_order_y", "secret_mf_z", "203.0.113.9", "client-abc"):
+            self.assertNotIn(leaked, out)
+
+    def test_never_prints_sql_other_params_or_client_ids(self):
+        _, out = self.run_check(events(
+            audit_line("execute_query", False, error="QUERY_ERROR: Unknown column 'x'"),  # params.sql = SECRET_SQL
+            audit_line("describe_table", False, params={"table": "secret_table_w"}, error="TABLE_NOT_FOUND")),
+            "--failures")
+        self.assertIn("  2026-09-27T08:00:00+0000  describe_table  TABLE_NOT_FOUND", out)
+        for leaked in (SECRET_SQL, "phone", "dim_user", "secret_table_w", "client-abc"):
+            self.assertNotIn(leaked, out)
+
+    def test_failures_are_listed_in_timestamp_order(self):
+        # filter-log-events interleaves the log streams of several runtime sessions.
+        _, out = self.run_check(events(
+            audit_line("list_tables", False, timestamp="2026-09-27T08:02:00+0000", error="E3"),
+            audit_line("describe_table", False, timestamp="2026-09-27T08:00:00+0000", error="E1"),
+            audit_line("list_metrics", timestamp="2026-09-27T07:59:00+0000"),
+            audit_line("execute_query", False, timestamp="2026-09-27T08:01:00+0000", error="E2"),
+            audit_line("get_query_profile", None, timestamp="2026-09-27T07:58:00+0000", error="E0")),  # not True
+            "--failures")
+        self.assertIn("audit: 5 records (1 ok, 4 failed)", out)
+        self.assertEqual(out.splitlines()[-5:], ["failures: 4",
+                                                 "  2026-09-27T07:58:00+0000  get_query_profile  E0",
+                                                 "  2026-09-27T08:00:00+0000  describe_table  E1",
+                                                 "  2026-09-27T08:01:00+0000  execute_query  E2",
+                                                 "  2026-09-27T08:02:00+0000  list_tables  E3"])
+
+    def test_no_failures(self):
+        rc, out = self.run_check(events(audit_line("list_metrics")), "--failures")
+        self.assertEqual(rc, 0, out)
+        self.assertEqual(out.splitlines()[-1], "failures: 0")
+
+    def test_the_exit_code_is_unchanged(self):
+        # Failed tool calls are still audited calls: they alone never fail the check.
+        both_failed = events(*(audit_line(t, False, error="QUERY_TIMEOUT") for t in ("execute_query", "list_metrics")))
+        self.assertEqual(self.run_check(both_failed, "--calls", str(self.calls), "--failures")[0], 0)
+        rc, out = self.run_check(events(audit_line("execute_query", False, error="QUERY_TIMEOUT")),
+                                 "--calls", str(self.calls), "--failures")
+        self.assertEqual(rc, 1)
+        self.assertEqual(out.splitlines()[-2:], ["failures: 1",
+                                                 "  2026-09-27T08:00:00+0000  execute_query  QUERY_TIMEOUT"])
+        self.assertEqual(self.run_check("not json", "--failures")[0], 2)
+
+
 class TestRealAuditLine(_Case):
     def test_reads_what_the_runtime_writes_to_stderr(self):
         # The server's own logging setup (agentcore_ext.app.configure_logging) and audit writer, in a
diff --git a/scripts/test/test_gw_latency.py b/scripts/test/test_gw_latency.py
index 0c7d28d..ec00e58 100644
--- a/scripts/test/test_gw_latency.py
+++ b/scripts/test/test_gw_latency.py
@@ -2,9 +2,12 @@
 
 import io
 import json
+import os
 import sys
+import time
 import unittest
 from pathlib import Path
+from unittest import mock
 
 sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
 import gw_latency  # noqa: E402
@@ -18,8 +21,8 @@ def result(id_: str, tool: str, points: dict[str, float]) -> dict:
             "StatusCode": "Complete"}
 
 
-def minute(tool: str, at: str, calls: int, avg: float, peak: float) -> list[dict]:
-    return [result("calls", tool, {at: calls}), result("avg", tool, {at: avg}), result("max", tool, {at: peak})]
+def minute(tool: str, at: str | float, calls: int, total: float, peak: float) -> list[dict]:
+    return [result("calls", tool, {at: calls}), result("sum", tool, {at: total}), result("max", tool, {at: peak})]
 
 
 def doc(*results: dict) -> str:
@@ -35,8 +38,8 @@ def run(stdin: str, *argv: str) -> tuple[int, str]:
 class Queries(unittest.TestCase):
     def test_one_search_per_statistic_labelled_with_the_tool_name(self):
         queries = gw_latency.queries(ARN)
-        self.assertEqual([q["Id"] for q in queries], ["calls", "avg", "max"])
-        for query, stat in zip(queries, ("SampleCount", "Average", "Maximum")):
+        self.assertEqual([q["Id"] for q in queries], ["calls", "sum", "max"])
+        for query, stat in zip(queries, ("SampleCount", "Sum", "Maximum")):
             self.assertEqual(query["Label"], "${PROP('Dim.Name')}")
             expression = query["Expression"]
             self.assertTrue(expression.startswith(
@@ -59,11 +62,28 @@ class Queries(unittest.TestCase):
                 self.assertEqual(out.getvalue(), "FAIL: --gateway-arn is not a Gateway ARN\n")
 
 
+class Minute(unittest.TestCase):
+    def setUp(self):
+        self.addCleanup(time.tzset)  # runs after TZ is restored
+        self.enterContext(mock.patch.dict(os.environ, {"TZ": "IST-5:30"}))  # a local zone that is not UTC
+        time.tzset()
+
+    def test_every_form_becomes_the_utc_minute(self):
+        for at in (1790557500, 1790557559.9, "2026-09-28T01:05:00Z", "2026-09-28T01:05:00+00:00",
+                   "2026-09-28T01:05:59.999Z", "2026-09-28T09:05:00+08:00", "2026-09-27T20:35:00-04:30",
+                   "2026-09-28T01:05:00"):
+            with self.subTest(at=at):
+                self.assertEqual(gw_latency._minute(at), "2026-09-28T01:05")
+
+    def test_an_offset_can_change_the_day(self):
+        self.assertEqual(gw_latency._minute("2026-09-28T05:05:00+08:00"), "2026-09-27T21:05")
+
+
 class Report(unittest.TestCase):
     def test_one_line_per_minute_and_tool_in_time_order(self):
         rc, out = run(doc(*minute("doris___query_metric", T3, 1, 9269, 9269),
                           *minute("doris___check_service_health", T1, 1, 5432, 5432),
-                          *minute("doris___list_metrics", T3, 2, 6100.4, 6752)))
+                          *minute("doris___list_metrics", T3, 2, 12200.8, 6752)))
         self.assertEqual(rc, 0, out)
         self.assertEqual(out.splitlines(), [
             "tools/call: 4 calls in 3 rows (tool x minute), max 9269 ms (doris___query_metric at 2026-09-27T13:51)",
@@ -73,6 +93,29 @@ class Report(unittest.TestCase):
             "  [PASS] every minute under 60000 ms",
         ])
 
+    def test_series_of_one_tool_and_minute_merge(self):
+        # SEARCH returns one series per value of any other dimension: calls and sums add up, max is the largest.
+        rc, out = run(doc(*minute("doris___query_metric", T1, 2, 10000, 7000),
+                          *minute("doris___query_metric", T1, 3, 5000, 2500)))
+        self.assertEqual(rc, 0, out)
+        self.assertEqual(out.splitlines(), [  # avg = 15000 / 5; the mean of the series' averages would be 3333
+            "tools/call: 5 calls in 1 rows (tool x minute), max 7000 ms (doris___query_metric at 2026-09-27T13:49)",
+            "  2026-09-27T13:49  doris___query_metric                   5 calls  avg    3000 ms  max    7000 ms",
+            "  [PASS] every minute under 60000 ms",
+        ])
+
+    def test_the_same_minute_in_any_timestamp_form_merges(self):
+        rc, out = run(doc(*minute("doris___list_tables", "2026-09-27T13:49:00Z", 1, 4000, 4000),
+                          *minute("doris___list_tables", T1, 1, 6000, 6000),
+                          *minute("doris___list_tables", "2026-09-27T21:49:30+08:00", 2, 5000, 3000),
+                          *minute("doris___list_tables", 1790516940, 1, 1000, 1000)))
+        self.assertEqual(rc, 0, out)
+        self.assertEqual(out.splitlines(), [
+            "tools/call: 5 calls in 1 rows (tool x minute), max 6000 ms (doris___list_tables at 2026-09-27T13:49)",
+            "  2026-09-27T13:49  doris___list_tables                    5 calls  avg    3200 ms  max    6000 ms",
+            "  [PASS] every minute under 60000 ms",
+        ])
+
     def test_over_the_warning_threshold_is_flagged_but_passes(self):
         rc, out = run(doc(*minute("doris___execute_query", T2, 1, 47000, 47000),
                           *minute("doris___list_tables", T3, 1, 5600, 5600)))
diff --git a/scripts/test/test_mcp_smoke.py b/scripts/test/test_mcp_smoke.py
index ad44e12..4fdca38 100644
--- a/scripts/test/test_mcp_smoke.py
+++ b/scripts/test/test_mcp_smoke.py
@@ -20,6 +20,11 @@ sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
 import mcp_smoke  # noqa: E402
 
 SHIPPED_CALLS = Path(__file__).resolve().parents[1] / "smoke_calls.json"
+GW_HOST = "gw-0123.gateway.example.test"
+GW_URL = f"https://{GW_HOST}/mcp"
+RUNTIME_HOST = "runtime-0123.example.test"
+RUNTIME_URL = f"https://{RUNTIME_HOST}/runtimes/rt-0123/invocations?qualifier=DEFAULT"
+PROXY = f"uvx mcp-proxy-for-aws@latest {RUNTIME_URL} --service bedrock-agentcore --region us-east-1"
 OK = json.dumps({"success": True, "data": {}})
 PROCESSLIST = [
     {"Id": 11, "User": "mcp_svc", "Host": "172.31.5.6:40001", "Command": "Query", "Time": "0",
@@ -86,10 +91,10 @@ class _SmokeCase(unittest.IsolatedAsyncioTestCase):
         path.write_text(json.dumps(calls))
         return str(path)
 
-    async def run_main(self, *argv: str) -> tuple[int, str]:
+    async def run_main(self, *argv: str, target: tuple[str, str] = ("--url", "http://fake/mcp")) -> tuple[int, str]:
         out = io.StringIO()
         with contextlib.redirect_stdout(out):
-            rc = await mcp_smoke.main(["--url", "http://fake/mcp", *argv], client_factory=self.factory)
+            rc = await mcp_smoke.main([*target, *argv], client_factory=self.factory)
         return rc, out.getvalue()
 
 
@@ -277,6 +282,68 @@ class TestErrorsAreMasked(_SmokeCase):
         self.assertIn("Session termination failed: POST ***", err.getvalue())
         self.assertNotIn("fake/mcp", err.getvalue())
 
+    async def test_a_dns_error_naming_only_the_host_is_masked(self):
+        def unresolved(_args):
+            raise ConnectionError(f"Failed to resolve '{GW_HOST}' ([Errno -2] Name or service not known)")
+
+        self.factory = unresolved
+        rc, out = await self.run_main("list", target=("--url", GW_URL))
+        self.assertEqual(rc, 1)
+        self.assertIn("FAIL: ConnectionError: Failed to resolve '***' ([Errno -2] Name or service not known)\n", out)
+        self.assertNotIn("gw-0123", out)
+
+    async def test_the_url_in_a_stdio_command_is_masked(self):
+        def refused(_args):
+            raise RuntimeError(f"POST {RUNTIME_URL} failed; cannot resolve {RUNTIME_HOST}")
+
+        self.factory = refused
+        rc, out = await self.run_main("list", target=("--stdio", PROXY))
+        self.assertEqual(rc, 1)
+        self.assertIn("FAIL: RuntimeError: POST *** failed; cannot resolve ***\n", out)
+        self.assertNotIn("runtime-0123", out)
+
+    async def test_sdk_log_lines_are_masked_in_stdio_mode(self):
+        real = self.factory
+
+        def logs_the_url(args):
+            logging.getLogger("mcp.client.stdio").warning("Session termination failed: POST %s (%s)",
+                                                          RUNTIME_URL, RUNTIME_HOST)
+            return real(args)
+
+        self.factory = logs_the_url
+        err = io.StringIO()
+        with contextlib.redirect_stderr(err):
+            rc, _ = await self.run_main("list", target=("--stdio", PROXY))
+        self.assertEqual(rc, 0)
+        self.assertIn("WARNING mcp.client.stdio: Session termination failed: POST *** (***)\n", err.getvalue())
+        self.assertNotIn("runtime-0123", err.getvalue())
+
+
+class TestHiddenValues(unittest.TestCase):
+    def hidden(self, *argv: str) -> list[str]:
+        return mcp_smoke.hidden_values(mcp_smoke.parse_args([*argv, "list"]))
+
+    def test_the_url_and_its_host(self):
+        self.assertEqual(self.hidden("--url", GW_URL), [GW_URL, GW_HOST])
+
+    def test_the_host_name_without_port_or_user(self):
+        # A DNS error names the bare host: "Failed to resolve 'gw-0123...' ([Errno -2] ...)".
+        url = f"https://svc@{GW_HOST}:8443/mcp"
+        self.assertEqual(self.hidden("--url", url), [url, GW_HOST])
+
+    def test_the_url_in_a_stdio_command_and_its_host(self):
+        self.assertEqual(self.hidden("--stdio", PROXY), [RUNTIME_URL, RUNTIME_HOST])
+
+    def test_a_stdio_command_without_a_url_hides_nothing(self):
+        self.assertEqual(self.hidden("--stdio", "python -m doris_mcp_server --transport stdio"), [])
+
+    def test_the_bearer_token(self):
+        with mock.patch.dict(os.environ, {"GW_TOKEN": "tok-0123456789abcdef"}):
+            self.assertEqual(self.hidden("--url", GW_URL, "--bearer-env", "GW_TOKEN"),
+                             [GW_URL, GW_HOST, "tok-0123456789abcdef"])
+        with mock.patch.dict(os.environ, {"GW_TOKEN": ""}):
+            self.assertEqual(self.hidden("--url", GW_URL, "--bearer-env", "GW_TOKEN"), [GW_URL, GW_HOST])
+
 
 class TestSigV4Option(unittest.TestCase):
     def _parse_error(self, *argv: str) -> None:
```

- [ ] **Step 2：确认失败**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s scripts/test > /tmp/t54-red.log 2>&1; echo "rc=$?"
grep -E '^(FAIL|ERROR):' /tmp/t54-red.log | sed -E 's/^(FAIL|ERROR): [A-Za-z0-9_]+ \(([A-Za-z0-9_.]+)\).*/\1 \2/' | sort | uniq -c
grep -E '^Ran |^OK|^FAILED' /tmp/t54-red.log
```
期望（实测）：
```
rc=1
      1 ERROR test_audit_check.TestFailures.test_a_failure_without_an_error_says_not_recorded
      1 ERROR test_audit_check.TestFailures.test_a_multi_line_error_stays_on_one_line
      1 ERROR test_audit_check.TestFailures.test_an_address_across_the_cut_is_masked_not_split
      1 ERROR test_audit_check.TestFailures.test_failures_are_listed_in_timestamp_order
      1 ERROR test_audit_check.TestFailures.test_never_prints_sql_other_params_or_client_ids
      1 ERROR test_audit_check.TestFailures.test_no_failures
      1 ERROR test_audit_check.TestFailures.test_query_metric_failures_show_group_by_where_and_having_ip_masked
      1 ERROR test_audit_check.TestFailures.test_the_error_is_cut_at_200_chars
      1 ERROR test_audit_check.TestFailures.test_the_error_text_is_shown_ip_masked
      1 ERROR test_audit_check.TestFailures.test_the_exit_code_is_unchanged
      1 ERROR test_audit_check.TestFailures.test_the_section_follows_the_unchanged_summary
      1 ERROR test_gw_latency.Minute.test_an_offset_can_change_the_day
      8 ERROR test_gw_latency.Minute.test_every_form_becomes_the_utc_minute
      1 ERROR test_mcp_smoke.TestHiddenValues.test_a_stdio_command_without_a_url_hides_nothing
      1 ERROR test_mcp_smoke.TestHiddenValues.test_the_bearer_token
      1 ERROR test_mcp_smoke.TestHiddenValues.test_the_host_name_without_port_or_user
      1 ERROR test_mcp_smoke.TestHiddenValues.test_the_url_and_its_host
      1 ERROR test_mcp_smoke.TestHiddenValues.test_the_url_in_a_stdio_command_and_its_host
      1 FAIL test_gw_latency.Queries.test_one_search_per_statistic_labelled_with_the_tool_name
      1 FAIL test_gw_latency.Report.test_one_line_per_minute_and_tool_in_time_order
      1 FAIL test_gw_latency.Report.test_series_of_one_tool_and_minute_merge
      1 FAIL test_gw_latency.Report.test_the_same_minute_in_any_timestamp_form_merges
      1 FAIL test_mcp_smoke.TestErrorsAreMasked.test_a_dns_error_naming_only_the_host_is_masked
      1 FAIL test_mcp_smoke.TestErrorsAreMasked.test_sdk_log_lines_are_masked_in_stdio_mode
      1 FAIL test_mcp_smoke.TestErrorsAreMasked.test_the_url_in_a_stdio_command_is_masked
Ran 137 tests in 2.016s
FAILED (failures=7, errors=25)
```
失败的正是 Step 3 要做的（32 个失败的记录对应 25 个检查，`test_every_form_becomes_the_utc_minute` 有 8 个 subTest）：
- 25 个 `ERROR`：`audit_check.py` 还没有 `--failures` 选项（`TestFailures` 的 11 个）；`gw_latency._minute` 还不存在（`Minute` 的 2 个检查、9 个记录）；`mcp_smoke.hidden_values` 还不存在（`TestHiddenValues` 的 5 个）。
- 7 个 `FAIL`：`gw_latency` 还在要 `Average`、同一工具同一分钟的序列没有合并（`Queries`、`Report` 的 4 个）；`mcp_smoke` 还没有 mask `--stdio` 命令里的 URL、只有主机名的 DNS 错误、stdio 模式下的 SDK 日志行（`TestErrorsAreMasked` 的 3 个）。
- 其余 112 个（包括 `TestFailures` 里「不带 `--failures` 时输出不变」）都通过。

失败的项目或个数不同时，先查明原因，不要进入 Step 3。

- [ ] **Step 3：实现**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py t57b-impl.diff /tmp/t57b-impl.diff
git apply /tmp/t57b-impl.diff && git status --short && git diff --shortstat
```
期望（实测）：
```
t57b-impl.diff -> /tmp/t57b-impl.diff (193 lines)
 M scripts/audit_check.py
 M scripts/gw_latency.py
 M scripts/mcp_smoke.py
 M scripts/test/test_audit_check.py
 M scripts/test/test_gw_latency.py
 M scripts/test/test_mcp_smoke.py
 6 files changed, 308 insertions(+), 21 deletions(-)
```

<!-- file: t57b-impl.diff sha256=2bab012cce521e98b9c2f546c8e93c91ae78d5bd23d6ded106f50584003aa64b -->
```diff
diff --git a/scripts/audit_check.py b/scripts/audit_check.py
index 353063e..5415650 100644
--- a/scripts/audit_check.py
+++ b/scripts/audit_check.py
@@ -3,11 +3,13 @@
 
   aws logs filter-log-events --region us-east-1 --log-group-name "$LOG_GROUP" --start-time "$SINCE_MS" \\
       --filter-pattern '"doris_new_mcp.audit"' --output json \\
-    | .venv/bin/python scripts/audit_check.py --calls scripts/smoke_calls.json --repeat 2
+    | .venv/bin/python scripts/audit_check.py --calls scripts/smoke_calls.json --repeat 2 [--failures]
 
-Prints counts per tool and outcome only: never params, SQL, error text or client ids.
-Exit code: 0 when every expected call is audited, 1 when some are missing or a record is unreadable,
-2 when the input is not filter-log-events JSON.
+By default prints counts per tool and outcome only. With --failures it then lists every failed call in time
+order: its tool, its error text (cut to 200 chars) and, for query_metric, its group_by / where / having, all
+with IPv4 addresses masked as <ip>. Never SQL, other params, MetricFlow commands or client ids.
+Exit code (the same with --failures: a failed call is still an audited one): 0 when every expected call is
+audited, 1 when some are missing or a record is unreadable, 2 when the input is not filter-log-events JSON.
 """
 
 import argparse
@@ -15,9 +17,12 @@ import json
 import sys
 from collections import Counter
 
+import redact  # scripts/ is on sys.path when this file is run as a script
 from mcp_smoke import load_calls
 
 MARKER = "doris_new_mcp.audit: "
+ERROR_CHARS = 200
+FAILURE_PARAMS = {"query_metric": ("group_by", "where", "having")}  # the only params --failures shows
 
 
 def parse_records(doc: dict) -> tuple[list[dict], int]:
@@ -39,10 +44,30 @@ def parse_records(doc: dict) -> tuple[list[dict], int]:
     return records, unreadable
 
 
+def _one_line(value: object) -> str:
+    """value on one line, IPv4 addresses masked (a CONNECTION_ERROR names the Doris host)."""
+    return redact.redact(" ".join(str(value).split()), [])
+
+
+def failure_lines(records: list[dict]) -> list[str]:
+    """The --failures section: every failed call in time order, with its error and query_metric's filters."""
+    failed = sorted((r for r in records if r.get("success") is not True), key=lambda r: str(r.get("timestamp", "")))
+    lines = [f"failures: {len(failed)}"]
+    for record in failed:
+        error = _one_line(record["error"])[:ERROR_CHARS] if record.get("error") else "(not recorded)"
+        lines.append(f"  {record.get('timestamp')}  {record['tool']}  {error}")
+        params = record.get("params") if isinstance(record.get("params"), dict) else {}
+        lines += [f"      {name}: {_one_line(params[name])}" for name in FAILURE_PARAMS.get(record["tool"], ())
+                  if name in params]
+    return lines
+
+
 def main(argv: list[str] | None = None, stdin=sys.stdin, out=sys.stdout) -> int:
     parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
     parser.add_argument("--calls", help="calls file of the smoke run (scripts/smoke_calls.json format)")
     parser.add_argument("--repeat", type=int, default=1, help="how many times the smoke run made each call")
+    parser.add_argument("--failures", action="store_true",
+                        help="also list each failed call: time, tool, error (IPv4-masked), query_metric filters")
     args = parser.parse_args(argv)
 
     def say(line: str) -> None:
@@ -78,6 +103,9 @@ def main(argv: list[str] | None = None, stdin=sys.stdin, out=sys.stdout) -> int:
     if unreadable:
         passed = False
         say(f"  [FAIL] unreadable audit records: {unreadable}")
+    if args.failures:
+        for line in failure_lines(records):
+            say(line)
     return 0 if passed else 1
 
 
diff --git a/scripts/gw_latency.py b/scripts/gw_latency.py
index 0702583..3412e5b 100644
--- a/scripts/gw_latency.py
+++ b/scripts/gw_latency.py
@@ -9,18 +9,23 @@ waits for on each tool call: the number Quick's 60 s limit applies to.
       --metric-data-queries "$q" --output json \\
     | .venv/bin/python scripts/gw_latency.py report
 
-Prints tool names, minutes, call counts and milliseconds only: never the ARN.
+Prints tool names, UTC minutes, call counts and milliseconds only: never the ARN. Series of one tool in one
+minute (SEARCH returns one per value of any other dimension) are merged: calls and sums add up, avg is
+sum / calls, max is the largest.
 Exit code: 0 when every minute stays under --limit-ms (--warn-ms only flags), 1 when one does not or there
 are no datapoints, 2 when the input is not get-metric-data JSON or --gateway-arn is not a Gateway ARN.
 """
 
 import argparse
 import json
+import operator
 import re
 import sys
+from datetime import datetime, timezone
 
 GATEWAY_ARN_RE = re.compile(r"arn:aws:bedrock-agentcore:[a-z0-9-]+:\d{12}:gateway/[A-Za-z0-9-]+")
-STATS = (("calls", "SampleCount"), ("avg", "Average"), ("max", "Maximum"))
+STATS = (("calls", "SampleCount"), ("sum", "Sum"), ("max", "Maximum"))
+MERGE = {"calls": operator.add, "sum": operator.add, "max": max}  # series of one tool in one minute
 
 
 def queries(gateway_arn: str) -> list[dict]:
@@ -31,15 +36,31 @@ def queries(gateway_arn: str) -> list[dict]:
             for id_, stat in STATS]
 
 
+def _minute(at: float | str) -> str:
+    """The UTC minute (YYYY-MM-DDTHH:MM) of epoch seconds or an ISO 8601 time (Z, +HH:MM, or naive = UTC)."""
+    if isinstance(at, (int, float)):
+        moment = datetime.fromtimestamp(at, timezone.utc)
+    else:
+        moment = datetime.fromisoformat(at)
+        if moment.tzinfo is None:
+            moment = moment.replace(tzinfo=timezone.utc)
+    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
+
+
 def parse_rows(doc: dict) -> dict[tuple[str, str], dict[str, float]]:
-    """{(minute, tool): {"calls": n, "avg": ms, "max": ms}} from the results of queries(); others are skipped."""
+    """{(minute, tool): {"calls": n, "sum": ms, "max": ms, "avg": ms}} from the results of queries(); others are
+    skipped. SEARCH can return several series for one tool (other dimensions): they merge, avg = sum / calls."""
     rows: dict[tuple[str, str], dict[str, float]] = {}
     ids = {id_ for id_, _ in STATS}
     for result in doc["MetricDataResults"]:
         if result.get("Id") not in ids:
             continue
+        id_ = result["Id"]
         for at, value in zip(result.get("Timestamps") or [], result.get("Values") or []):
-            rows.setdefault((str(at)[:16], str(result.get("Label"))), {})[result["Id"]] = float(value)
+            stats = rows.setdefault((_minute(at), str(result.get("Label"))), {})
+            stats[id_] = MERGE[id_](stats[id_], float(value)) if id_ in stats else float(value)
+    for stats in rows.values():
+        stats["avg"] = stats.get("sum", 0) / stats["calls"] if stats.get("calls") else 0
     return rows
 
 
diff --git a/scripts/mcp_smoke.py b/scripts/mcp_smoke.py
index 042e04e..b20e8bb 100644
--- a/scripts/mcp_smoke.py
+++ b/scripts/mcp_smoke.py
@@ -13,9 +13,10 @@ Examples:
 
 The bearer token is read from the named environment variable and never printed. `time` and `conns`
 print status, timings, error codes and counts only: never tool output, SQL results, hosts or statements.
-A session or call that raises is one FAIL line with the URL and the token masked as *** and IPv4
-addresses as <ip>; with --url the MCP SDK's own log lines go to stderr masked the same way
-(scripts/redact.py).
+A session or call that raises is one FAIL line with the endpoint URL (--url, or each URL in the --stdio
+command), its host name and the token masked as *** and IPv4 addresses as <ip>; the MCP SDK's own log lines
+go to stderr masked the same way, for every transport (scripts/redact.py). With --stdio the child's own
+stderr (e.g. mcp-proxy-for-aws's log) goes straight to the terminal and is NOT masked by this script.
 Exit code: 0 on success, 1 when a tool call returns an error or a check fails, 2 on a bad calls file.
 """
 
@@ -29,6 +30,7 @@ import sys
 import time
 from collections import Counter
 from pathlib import Path
+from urllib.parse import urlsplit
 
 from fastmcp import Client
 from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
@@ -55,6 +57,14 @@ def build_client(args: argparse.Namespace) -> Client:
     return Client(StdioTransport(command=cmd[0], args=cmd[1:], env=dict(os.environ)), timeout=args.timeout)
 
 
+def hidden_values(args: argparse.Namespace) -> list[str]:
+    """What error lines and SDK log lines must not show: each endpoint URL, its host name, and the bearer token."""
+    urls = [args.url] if args.url else [w for w in shlex.split(args.stdio or "") if "://" in w]
+    hosts = [urlsplit(u).hostname for u in urls]
+    token = os.environ.get(args.bearer_env, "") if args.bearer_env else ""
+    return [v for v in (*urls, *hosts, token) if v]
+
+
 def result_payload(result) -> object:
     """Return the tool result as JSON when possible, else the raw text."""
     text = "".join(getattr(c, "text", "") for c in result.content)
@@ -305,9 +315,8 @@ def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
 
 async def main(argv: list[str] | None = None, client_factory=build_client) -> int:
     args = parse_args(argv)
-    hidden = [args.url, os.environ.get(args.bearer_env, "") if args.bearer_env else ""]
-    if args.url:
-        redact.redact_sdk_logs(hidden)
+    hidden = hidden_values(args)
+    redact.redact_sdk_logs(hidden)
     start = time.monotonic()
     try:
         if args.command == "time":
```

- [ ] **Step 4：确认通过；突变**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 期望：Ran 137 tests … OK
.venv/bin/python -m unittest discover -s quick/test 2>&1 | tail -3                                  # 期望：Ran 50 tests … OK
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 168 tests … OK
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json af; echo "rc=$?"
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json m8; echo "rc=$?"
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json m9; echo "rc=$?"
```
期望（实测，秒数每次不同）：
```
Ran 137 tests in 2.021s

OK
Ran 50 tests in 0.170s

OK
Ran 168 tests in 6.649s

OK
af1-error-not-masked: caught by test_an_address_across_the_cut_is_masked_not_split, test_query_metric_failures_show_group_by_where_and_having_ip_masked, test_the_error_text_is_shown_ip_masked, test_the_section_follows_the_unchanged_summary (Ran 22, FAILED (failures=4))
af2-error-not-cut: caught by test_an_address_across_the_cut_is_masked_not_split, test_the_error_is_cut_at_200_chars (Ran 22, FAILED (failures=2))
af3-cut-before-masking: caught by test_an_address_across_the_cut_is_masked_not_split (Ran 22, FAILED (failures=1))
af4-no-not-recorded: caught by test_a_failure_without_an_error_says_not_recorded (Ran 22, FAILED (failures=1))
af5-all-params-printed-sql-leaks: caught by test_a_failure_without_an_error_says_not_recorded, test_an_address_across_the_cut_is_masked_not_split, test_failures_are_listed_in_timestamp_order, test_never_prints_sql_other_params_or_client_ids, test_query_metric_failures_show_group_by_where_and_having_ip_masked, test_the_error_is_cut_at_200_chars, test_the_error_text_is_shown_ip_masked, test_the_exit_code_is_unchanged, test_the_section_follows_the_unchanged_summary (Ran 22, FAILED (failures=9))
af6-unsorted: caught by test_failures_are_listed_in_timestamp_order (Ran 22, FAILED (failures=1))
af7-client-id-printed: caught by test_a_failure_without_an_error_says_not_recorded, test_a_multi_line_error_stays_on_one_line, test_an_address_across_the_cut_is_masked_not_split, test_failures_are_listed_in_timestamp_order, test_never_prints_sql_other_params_or_client_ids, test_query_metric_failures_show_group_by_where_and_having_ip_masked, test_the_error_is_cut_at_200_chars, test_the_error_text_is_shown_ip_masked, test_the_exit_code_is_unchanged, test_the_section_follows_the_unchanged_summary (Ran 22, FAILED (failures=10))
af8-section-without-the-flag: caught by test_never_prints_params_errors_or_client_ids, test_without_the_flag_the_output_is_unchanged (Ran 22, FAILED (failures=2))
af9-failures-fail-the-check: caught by test_the_exit_code_is_unchanged, test_the_section_follows_the_unchanged_summary (Ran 22, FAILED (failures=2))
af10-multi-line-error-kept: caught by test_a_multi_line_error_stays_on_one_line (Ran 22, FAILED (failures=1))
af11-filters-not-masked: caught by test_a_multi_line_error_stays_on_one_line, test_query_metric_failures_show_group_by_where_and_having_ip_masked (Ran 22, FAILED (failures=2))
af12-mf-command-printed: caught by test_query_metric_failures_show_group_by_where_and_having_ip_masked (Ran 22, FAILED (failures=1))
af13-only-success-false-is-a-failure: caught by test_failures_are_listed_in_timestamp_order (Ran 22, FAILED (failures=1))
13/13 mutations caught; tree unchanged: True
rc=0
m8-1-host-not-added: caught by test_a_dns_error_naming_only_the_host_is_masked, test_sdk_log_lines_are_masked_in_stdio_mode, test_the_bearer_token, test_the_host_name_without_port_or_user, test_the_url_and_its_host, test_the_url_in_a_stdio_command_and_its_host, test_the_url_in_a_stdio_command_is_masked (Ran 32, FAILED (failures=7))
m8-2-stdio-url-not-extracted: caught by test_sdk_log_lines_are_masked_in_stdio_mode, test_the_url_in_a_stdio_command_and_its_host, test_the_url_in_a_stdio_command_is_masked (Ran 32, FAILED (failures=3))
m8-3-sdk-logs-masked-only-for-url: caught by test_sdk_log_lines_are_masked_in_stdio_mode (Ran 32, FAILED (failures=1))
m8-4-main-keeps-the-old-hidden-list: caught by test_a_dns_error_naming_only_the_host_is_masked, test_sdk_log_lines_are_masked_in_stdio_mode, test_the_url_in_a_stdio_command_is_masked (Ran 32, FAILED (failures=3))
m8-5-token-not-hidden: caught by test_the_bearer_token, test_the_bearer_token_is_masked (Ran 32, FAILED (failures=2))
m8-6-netloc-instead-of-hostname: caught by test_the_host_name_without_port_or_user (Ran 32, FAILED (failures=1))
6/6 mutations caught; tree unchanged: True
rc=0
m9-1-offset-replaced-not-converted: caught by test_an_offset_can_change_the_day, test_every_form_becomes_the_utc_minute, test_the_same_minute_in_any_timestamp_form_merges (Ran 14, FAILED (failures=4))
m9-2-minute-by-slicing-the-string: caught by test_the_same_minute_in_any_timestamp_form_merges (Ran 14, FAILED (failures=1))
m9-3-overwrite-instead-of-merge: caught by test_series_of_one_tool_and_minute_merge, test_the_same_minute_in_any_timestamp_form_merges (Ran 14, FAILED (failures=2))
m9-4-series-averaged-instead-of-added: caught by test_series_of_one_tool_and_minute_merge, test_the_same_minute_in_any_timestamp_form_merges (Ran 14, FAILED (failures=2))
m9-4b-avg-is-the-mean-of-series-averages: caught by test_one_search_per_statistic_labelled_with_the_tool_name, test_series_of_one_tool_and_minute_merge, test_the_same_minute_in_any_timestamp_form_merges (Ran 14, FAILED (failures=3))
m9-5-max-as-sum: caught by test_series_of_one_tool_and_minute_merge, test_the_same_minute_in_any_timestamp_form_merges (Ran 14, FAILED (failures=2))
m9-6-naive-time-taken-as-local: caught by test_every_form_becomes_the_utc_minute (Ran 14, FAILED (failures=1))
m9-7-epoch-read-as-naive-utc: caught by test_every_form_becomes_the_utc_minute (Ran 14, FAILED (failures=2))
m9-8-queries-still-ask-for-average: caught by test_one_search_per_statistic_labelled_with_the_tool_name (Ran 14, FAILED (failures=1))
m9-9-avg-not-divided-by-calls: caught by test_one_line_per_minute_and_tool_in_time_order, test_series_of_one_tool_and_minute_merge, test_the_same_minute_in_any_timestamp_form_merges (Ran 14, FAILED (failures=3))
m9-10-calls-take-the-max: caught by test_series_of_one_tool_and_minute_merge, test_the_same_minute_in_any_timestamp_form_merges (Ran 14, FAILED (failures=2))
m9-p4-m1-threshold-strict: caught by test_reaching_quick_s_limit_fails (Ran 14, FAILED (failures=1))
m9-p4-m2-other-ids-not-skipped: caught by test_results_of_other_queries_are_ignored (Ran 14, FAILED (failures=1))
m9-p4-m3-arn-match-not-fullmatch: caught by test_refuses_a_value_that_is_not_a_gateway_arn (Ran 14, FAILED (failures=1))
m9-p4-m4-rows-unsorted: caught by test_one_line_per_minute_and_tool_in_time_order (Ran 14, FAILED (failures=1))
m9-p4-m5-slow-exits-0: caught by test_reaching_quick_s_limit_fails, test_the_thresholds_are_options (Ran 14, FAILED (failures=2))
16/16 mutations caught; tree unchanged: True
rc=0
```

- [ ] **Step 5：收尾，提交**

T5.7b 的 M-7 在 Task 7 写进 runbook，T5.7b 在那里勾选；这里只更新状态和日志。
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
echo 'Task 4（T5.7b 的 3 个脚本）已完成（M-7 在 Task 7 写进 runbook 后勾选 T5.7b）；Task 5（demo-check / cleanup / 30-gateway）从 Step 1 开始' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo 'Task 5（demo-check / cleanup 脚本），然后 Task 6（部署，GATE）、Task 7（整体评审，再交给用户导入 skill 和彩排 2 轮）、Task 8（T5.5）、Task 9（演示结束后清理，GATE）' | .venv/bin/python /tmp/p5-progress.py state 下一步
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 4（T5.7b 脚本）：`audit_check --failures`、`gw_latency`、`mcp_smoke`

- `audit_check.py --failures`：摘要之后按时间列出失败的调用（时间、工具、`error` 压成一行并 mask IPv4、截到 200 字符；`query_metric` 另列 `group_by` / `where` / `having`），不输出 SQL、其他参数、MetricFlow 命令、client id；没有 `error` 的旧记录显示 `(not recorded)`；exit code 不变。
- M-9（`gw_latency.py`）：时间戳（epoch 秒、`Z`、`±HH:MM`、不带时区）统一换成 UTC 分钟；统计量 `Average` 改成 `Sum`，同一工具同一分钟的序列合并（调用数、总耗时相加，平均 = 总耗时 / 调用数）。
- M-8（`mcp_smoke.py`）：`--stdio` 命令里的 URL、URL 的主机名（DNS 错误只写主机名）进 mask 列表；SDK 日志行对所有 transport 都 mask。`--stdio` 子进程自己的 stderr 不归这个脚本管，docstring 写明（未解决的 Minor）。
- M-7 留给 Task 7 的 runbook；M-10 已体现在本计划每个提交块的 IP 计数里。
- RED：25 个 `ERROR`（没有 `--failures`、`_minute`、`hidden_values`）、7 个 `FAIL`（`Average`、序列没合并、stdio 没 mask），其余 112 个通过。
- GREEN：`scripts/test` 137、`quick/test` 50、`doris/test` 168；突变 af 13/13、m8 6/6、m9 16/16 被抓到。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add scripts/audit_check.py scripts/gw_latency.py scripts/mcp_smoke.py \
        scripts/test/test_audit_check.py scripts/test/test_gw_latency.py scripts/test/test_mcp_smoke.py \
        specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
feat(p5): T5.7b audit_check --failures, gw_latency UTC minutes and merged series (M-9), mcp_smoke masks stdio URLs and hosts (M-8)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望（实测）：
```
进行中: written (758 lines)
下一步: written (758 lines)
### 2026-09-28 P5 Task 4（T5.7b 脚本）：`audit_check --failures`、`gw_latency`、`mcp_smoke`: written (767 lines)
check-secrets: OK (844 files scanned)
0
feat(p5): T5.7b audit_check --failures, gw_latency UTC minutes and merged series (M-9), mcp_smoke masks stdio URLs and hosts (M-8)
```
日志里的数字如果和实测不同，写实测值。

---

### Task 5：演示检查和清理脚本：`infra/30-gateway.sh` 的开关、`infra/99-cleanup.sh`、`scripts/demo-check.sh`、清理之后的 `check-secrets.sh`

来源：tasks.md T5.5（演示前后的检查脚本；Gateway `exceptionLevel DEBUG` 的决策要有开关）、T5.6（`99-cleanup.sh`：脚本在这里写好并对真实账号 dry-run，执行在 Task 9），design §7 的 `30-gateway.sh`、`99-cleanup.sh` 两行，§13（Runtime 偶发 502），§14（演示结束后清理）。这个任务只写脚本和离线测试，Step 5 对真实账号只做读操作（清理的 dry-run、`demo-check pre` / `post`）；不改任何 AWS 资源，不重跑 `30-gateway.sh`（要不要改 Gateway 在 Task 8 决定，走 GATE）。spec 阶段的发现：

| # | spec 阶段的发现 | 处理 | 测试 |
|---|---|---|---|
| 1 | `update-gateway` 替换整个配置（没传的选项被清空）；`30-gateway.sh` 只在 create 时传 description，P3 同步 target 时重跑之后 Gateway 的 description 变成了 `None`；`exceptionLevel DEBUG` 写死 | create 和 update 共用一组参数，description 放进去；`GW_EXCEPTION_LEVEL`：默认 `DEBUG`（和现在一样），`""` 表示不传（客户端只看到笼统的错误），其他值拒绝。改完不执行，Task 8 决定 | `test-30-gateway.sh` 30 个检查（create 和 update 的完整参数列表和调用顺序；默认、`""`、`DEBUG` 3 种取值；`INFO`、`debug`、`' DEBUG'` 在任何 AWS 调用之前失败；dry-run 不写）|
| 2 | 删除有依赖顺序：有 target 的 Gateway 删不掉；Cognito 有 domain 的 pool 删不掉；VPC endpoint 的 ENI 用 `doris-mcp-vpce`；Runtime 的 ENI 在 stack 删除后几分钟才异步释放，释放前 SG 删不掉；`doris-mcp-rt` 和 `doris-mcp-vpce` 互相引用 | `99-cleanup.sh` 按 8 步的顺序删：target（等它消失）→ Gateway → stack（等 `stack-delete-complete`）→ 3 个 endpoint（等消失）→ domain → pool → 2 个 secret → `doris-demo-sg` 里引用 `doris-mcp-rt` 的入站规则 → 等 ENI 释放（约 10 分钟上限）→ 撤销两个 SG 的互相引用 → 删 2 个 SG → 2 个 IAM 角色（先删 inline policy）| `apply, everything present`、`ENIs still in use` 两组 |
| 3 | 清理删的是别的项目也可能在用的账号：`doris-demo-sg` 不是本项目建的（开发机的 /32 规则也在里面）；过期的会话、没有权限返回的错误不能当成「已经删掉」| 第一次删除之前做完全部检查：账号等于 `ACCOUNT_ID`，每个资源带 `Project=doris-mcp-demo`（stack 带 `agentcore:project-name=dorismcp`），Gateway 名字是 `doris-mcp-gw`；只认各服务的 NOT_FOUND 错误为「已删除」，其他错误都 FATAL、什么都不删；`doris-demo-sg` 只撤销引用 `doris-mcp-rt` 且带标签的规则 | `refusals: nothing is deleted` 一组 |
| 4 | 删到一半失败要能接着删；secret 删除默认有恢复期 | 已经不在的资源记一行跳过，重跑即可；secret 默认 7 天恢复期（`SECRET_RECOVERY_DAYS` 7–30，`FORCE_DELETE_SECRETS=1` 立即删除）；`state.env`、日志组、X-Ray 设置不动；Doris 侧（`DROP USER mcp_svc`、`DROP DATABASE system_mcp`）由用户人工执行（Task 9）| `secrets knobs`、`STACK_NAME knob` 两组；`test-99-cleanup.sh` 共 81 个检查 |
| 5 | 每轮彩排前后要跑的检查散在 P3 / P4 的 5 个脚本里，手工拼命令容易漏掉 mask 或把 token 放上命令行 | `demo-check.sh pre`（10 项）：账号、Gateway / target READY、token、tools/list = 12、`doris___` 固定流程、对账、权限矩阵、连接（来源 172.31.、空闲 ≤ 610 s）、连接数 ≤ `MAX_CONNS`（80，`mcp_svc` 的上限是 100）；`post --since MS --until MS`（5 项）：审计（`audit_check --failures`）、每分钟的 Gateway 耗时、token、连接两项 | `test-demo-check.sh` 96 个检查 |
| 6 | token 和 Doris 凭证的边界：P4 手工执行时 token 经过 `export` | token 不 export、不上命令行、不打印，只经环境变量给 `mcp_smoke.py`；调用方和 `state.env`（`DORIS_SG` 等）的 `DORIS_*` 全部 unset；只有对账的子 shell 拿到只读账号的 4 个变量；每个子进程的输出都过 MASK | 「凭证文件带 `export` 行、调用方 export 了 token 和 `DORIS_*`」一组；每组都查 argv、输出里没有 token 和凭证值 |
| 7 | CloudWatch 的每分钟指标按整分钟对齐：窗口的开始如果向上取整，第一分钟里的调用就漏掉了 | `post` 的耗时窗口 `--since` 向下取整、`--until` 向上取整 | `post` 一组的窗口检查（10:00:30.5 → 10:00，10:29:01 → 10:30）|
| 8 | Task 9 删掉 2 个 secret 之后，`check-secrets.sh` 读不到它们；按 P2 定下的规则（检查没跑成就不算通过）它会一直失败，Task 9 和之后的提交都过不了。但「不存在」本身不能当成「已删除」：换成别的账号的凭证，每个 secret 都不存在 | 1b 步：Secrets Manager 说已排期删除（`marked for deletion`，7 天恢复期内），或者 `(ResourceNotFoundException)` 且 `sts get-caller-identity` 的账号等于 `infra/state.env` 的 `ACCOUNT_ID` 时，记一行 `SKIP` 跳过，OK 行写明跳过了几个；其他情况（过期、没有权限、别的账号、没有 `state.env`、sts 失败）仍然 FAIL。不输出账号 | `test-check-secrets.sh` 20 → 36 个检查（假的 `aws` 加上 `sts` 和 4 种错误；跳过一个 secret 不影响另一个的泄漏检查）；突变 cs |

未解决的 Minor（记入 Task 8 的决策表）：`TOKEN_CMD` 的默认值读仓库的 `infra/state.env`，不看 `STATE_FILE`（header 写明）；`99-cleanup.sh` 里少数「已经不存在」的分支（例如 endpoint 已删但 SG 还在）只在离线测试里走过。

**Files:**
- Modify: `infra/30-gateway.sh`（`GW_EXCEPTION_LEVEL`，description 进 `GW_COMMON`）、`scripts/check-secrets.sh`（1b 步：删掉的 secret 跳过）、`scripts/test/test-check-secrets.sh`
- Create: `infra/99-cleanup.sh`（229 行）、`scripts/demo-check.sh`（169 行）、`infra/test/test-30-gateway.sh`、`infra/test/test-99-cleanup.sh`、`scripts/test/test-demo-check.sh`（都是离线测试：假的 `aws`、`sleep` 放在 PATH 上，`PYTHON`、`TOKEN_CMD` 换成记录调用的假脚本，不访问 AWS 和 Doris）
- Test: 新的 3 组 shell 测试（30 + 81 + 96 个检查），`test-check-secrets.sh` 20 → 36，原有的另外 5 组照常通过

**Interfaces:**
- Consumes：`bcda0f3` 的 `infra/lib.sh`（`run`、`log`、`none_to_empty`、`is_placeholder`、`placeholder`、`private_tmp`、`PROJECT_TAG`、`STATE_FILE`、`APPLY`）、`infra/state.env` 的键（`ACCOUNT_ID`、`GW_ID`、`GW_TARGET_ID`、`GW_URL`、`RUNTIME_ID`、`RUNTIME_URL`、`VPCE_*`、`COGNITO_*`、`DORIS_SG`、`RT_SG`、`VPCE_SG`）、`scripts/get-gw-token.sh`；Task 2 的 `reconcile.py mcp`（12 个 case）；Task 4 的 `audit_check.py --failures`、`gw_latency.py queries` / `report`；`bcda0f3` 的 `mcp_smoke.py list` / `flow` / `conns`、`permission_matrix.py --url`。
- Produces：
  - `bash scripts/demo-check.sh pre` / `post --since MS --until MS`：最后一行 `demo-check MODE: N/M passed`，exit 0 / 1 / 2。Task 6 部署后、Task 7 每轮彩排前后、演示当天使用；
  - `bash infra/99-cleanup.sh`（dry-run）/ `APPLY=1 …`：Task 9 执行（GATE）；
  - `GW_EXCEPTION_LEVEL=DEBUG|""`：Task 8 的决策项；
  - `check-secrets.sh` 在 Task 9 删除 secret 之后：每个 secret 一行 `SKIP: secret … is scheduled for deletion …`（恢复期过后是 `… no longer exists in the project's account …`），最后一行 `check-secrets: OK (N files scanned, 2 deleted secrets skipped)`。

- [ ] **Step 1：写失败测试**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py infra/test/test-30-gateway.sh
.venv/bin/python /tmp/p5-extract.py infra/test/test-99-cleanup.sh
.venv/bin/python /tmp/p5-extract.py scripts/test/test-demo-check.sh
.venv/bin/python /tmp/p5-extract.py t55-tests.diff /tmp/t55-tests.diff
git apply /tmp/t55-tests.diff && git status --short
```
期望（实测）：
```
infra/test/test-30-gateway.sh -> infra/test/test-30-gateway.sh (144 lines)
infra/test/test-99-cleanup.sh -> infra/test/test-99-cleanup.sh (444 lines)
scripts/test/test-demo-check.sh -> scripts/test/test-demo-check.sh (265 lines)
t55-tests.diff -> /tmp/t55-tests.diff (109 lines)
 M scripts/test/test-check-secrets.sh
?? infra/test/test-30-gateway.sh
?? infra/test/test-99-cleanup.sh
?? scripts/test/test-demo-check.sh
```

新文件 `infra/test/test-30-gateway.sh`（假的 `aws` 把 create-/update-gateway 的参数逐行写到文件，两边逐项比较）：

<!-- file: infra/test/test-30-gateway.sh sha256=887e74414ba773e4e0f8a3e67f1bb9f71c9693779d8cca71632eba6abe6c3cd3 -->
```bash
#!/usr/bin/env bash
# Offline tests for infra/30-gateway.sh. Fake `aws` and `sleep` on PATH record every call; no AWS access.
#   bash infra/test/test-30-gateway.sh
set -uo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
# Fake AWS CLI. FAKE_GW = exists | missing (the Gateway and its target). The arguments of
# create-/update-gateway are also written one per line to $FAKE_DIR/<operation>.args.
cat > "$TMP/bin/aws" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
case "$1 $2" in
  "iam get-role") echo "arn:aws:iam::111122223333:role/doris-mcp-gateway-role" ;;
  "iam put-role-policy") ;;
  "bedrock-agentcore-control list-gateways")
    if [[ "$FAKE_GW" == exists ]]; then echo "gw-fixture0001"; else echo "None"; fi ;;
  "bedrock-agentcore-control create-gateway")
    printf '%s\n' "${@:3}" > "$FAKE_DIR/create-gateway.args"; echo "gw-fixture0001" ;;
  "bedrock-agentcore-control update-gateway")
    printf '%s\n' "${@:3}" > "$FAKE_DIR/update-gateway.args"; echo "UPDATING" ;;
  "bedrock-agentcore-control get-gateway")
    case "$*" in *"--query gatewayUrl"*) echo "https://gw.example.test/mcp" ;; *) echo "READY" ;; esac ;;
  "bedrock-agentcore-control list-gateway-targets")
    if [[ "$FAKE_GW" == exists ]]; then echo "TGTFIXTURE1"; else echo "None"; fi ;;
  "bedrock-agentcore-control create-gateway-target") echo "TGTFIXTURE1" ;;
  "bedrock-agentcore-control get-gateway-target") echo "READY" ;;
  *) echo "fake aws: unexpected call: $*" >&2; exit 99 ;;
esac
FAKE
printf '#!/usr/bin/env bash\nprintf "sleep %%s\\n" "$*" >> "$FAKE_LOG"\n' > "$TMP/bin/sleep"
chmod +x "$TMP/bin/aws" "$TMP/bin/sleep"

FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
# run_script FAKE_GW APPLY [VAR=value...] — runs the script against a fresh state.env; sets RC, OUT, LOG
# (the call log with the rendered policy's temp path normalised to file://<rendered>).
run_script() {
  local gw="$1" apply="$2"; shift 2
  : > "$TMP/aws.log"; rm -f "$TMP"/*.args
  printf '%s\n' '# test state' 'AWS_REGION=us-east-1' 'ACCOUNT_ID=111122223333' \
    'RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:111122223333:runtime/dorismcp_dorismcp-AbCdEf1234' \
    'DISCOVERY_URL=https://idp.example.test/us-east-1_EXAMPLE/.well-known/openid-configuration' \
    'CLIENT_A_ID=clientafixture' 'CLIENT_B_ID=clientbfixture' > "$TMP/state.env"
  OUT="$(env -u GW_EXCEPTION_LEVEL -u GW_ALLOWED_SCOPES -u SYNC "$@" PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" \
    FAKE_DIR="$TMP" FAKE_GW="$gw" APPLY="$apply" STATE_FILE="$TMP/state.env" bash "$INFRA_DIR/30-gateway.sh" 2>&1)"
  RC=$?
  LOG="$(sed -E 's#file://[^ ]+#file://<rendered>#' "$TMP/aws.log")"
}
has() { [[ "$1" == *"$2"* ]] && echo yes || echo no; }
writes() { grep -cE ' (create|update|put|synchronize|delete)-' <<<"$LOG"; }
DESC="Quick desktop -> Doris MCP (Runtime dorismcp)"
AUTHZ='{"customJWTAuthorizer": {"discoveryUrl": "https://idp.example.test/us-east-1_EXAMPLE/.well-known/openid-configuration", "allowedClients": ["clientafixture", "clientbfixture"], "allowedScopes": ["doris-mcp/invoke"]}}'
ROLE_ARN="arn:aws:iam::111122223333:role/doris-mcp-gateway-role"
RUNTIME_URL="https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A111122223333%3Aruntime%2Fdorismcp_dorismcp-AbCdEf1234/invocations?qualifier=DEFAULT"
CREDS='[{"credentialProviderType":"GATEWAY_IAM_ROLE","credentialProvider":{"iamCredentialProvider":{"service":"bedrock-agentcore","region":"us-east-1"}}}]'
# The Gateway arguments update-gateway / create-gateway must send (update-gateway replaces the whole config).
gw_args() { # [--exception-level-value]
  printf '%s\n' --name doris-mcp-gw --role-arn "$ROLE_ARN" --protocol-type MCP --authorizer-type CUSTOM_JWT \
    --authorizer-configuration "$AUTHZ"
  [[ -z "${1-}" ]] || printf '%s\n' --exception-level "$1"
  printf '%s\n' --description "$DESC"
}
READS_HEAD="iam get-role --role-name doris-mcp-gateway-role --query Role.Arn --output text
iam put-role-policy --role-name doris-mcp-gateway-role --policy-name invoke-dorismcp-runtime --policy-document file://<rendered>
bedrock-agentcore-control list-gateways --query items[?name=='doris-mcp-gw'].gatewayId | [0] --output text"
READS_TAIL="bedrock-agentcore-control get-gateway --gateway-identifier gw-fixture0001 --query status --output text
bedrock-agentcore-control get-gateway --gateway-identifier gw-fixture0001 --query gatewayUrl --output text
bedrock-agentcore-control list-gateway-targets --gateway-identifier gw-fixture0001 --query items[?name=='doris'].targetId | [0] --output text"

run_script exists 0
check "dry-run: exit 0" 0 "$RC"
check "dry-run: no AWS write" 0 "$(writes)"
DRY_UPDATE="$(grep '^DRY-RUN: aws bedrock-agentcore-control update-gateway' <<<"$OUT")"
check "dry-run: shows update-gateway with --exception-level DEBUG" yes "$(has "$DRY_UPDATE" " --exception-level DEBUG ")"
check "dry-run: shows update-gateway with the description" yes \
  "$(has "$DRY_UPDATE" ' --description Quick\ desktop\ -\>\ Doris\ MCP\ \(Runtime\ dorismcp\) ')"
check "dry-run: state.env unchanged" no "$(has "$(cat "$TMP/state.env")" "GW_ID=")"

run_script exists 1
check "apply/exists: exit 0" 0 "$RC"
check "apply/exists: update-gateway keeps the description and DEBUG (full argument list)" \
  "$(printf '%s\n' --gateway-identifier gw-fixture0001; gw_args DEBUG; printf '%s\n' --query status --output text)" \
  "$(cat "$TMP/update-gateway.args" 2>/dev/null)"
check "apply/exists: every call, in order, and nothing else" \
  "$READS_HEAD
bedrock-agentcore-control update-gateway --gateway-identifier gw-fixture0001 $(gw_args DEBUG | paste -sd ' ') --query status --output text
$READS_TAIL
bedrock-agentcore-control get-gateway-target --gateway-identifier gw-fixture0001 --target-id TGTFIXTURE1 --query status --output text" \
  "$LOG"
check "apply/exists: no create-gateway" no "$(has "$LOG" "create-gateway ")"
check "apply/exists: GW_ID / GW_URL / GW_TARGET_ID recorded" "GW_ID=gw-fixture0001|GW_URL=https://gw.example.test/mcp|GW_TARGET_ID=TGTFIXTURE1" \
  "$(grep -E '^GW_(ID|URL|TARGET_ID)=' "$TMP/state.env" | paste -sd '|')"

run_script exists 1 GW_EXCEPTION_LEVEL=
check "apply/GW_EXCEPTION_LEVEL empty: exit 0" 0 "$RC"
check "apply/GW_EXCEPTION_LEVEL empty: update-gateway omits the flag, keeps the description" \
  "$(printf '%s\n' --gateway-identifier gw-fixture0001; gw_args; printf '%s\n' --query status --output text)" \
  "$(cat "$TMP/update-gateway.args" 2>/dev/null)"
check "apply/GW_EXCEPTION_LEVEL empty: no --exception-level anywhere" no "$(has "$LOG" "--exception-level")"
run_script exists 0 GW_EXCEPTION_LEVEL=
check "dry-run/GW_EXCEPTION_LEVEL empty: the DRY-RUN line omits the flag" no \
  "$(has "$(grep 'update-gateway' <<<"$OUT")" "--exception-level")"

run_script exists 1 GW_EXCEPTION_LEVEL=DEBUG
check "apply/GW_EXCEPTION_LEVEL=DEBUG: same as the default" \
  "$(printf '%s\n' --gateway-identifier gw-fixture0001; gw_args DEBUG; printf '%s\n' --query status --output text)" \
  "$(cat "$TMP/update-gateway.args" 2>/dev/null)"

for bad in INFO debug " DEBUG"; do
  run_script exists 1 "GW_EXCEPTION_LEVEL=$bad"
  check "apply/GW_EXCEPTION_LEVEL='$bad': fails" 1 "$RC"
  check "apply/GW_EXCEPTION_LEVEL='$bad': FATAL names the knob" yes "$(has "$OUT" "FATAL: GW_EXCEPTION_LEVEL")"
  check "apply/GW_EXCEPTION_LEVEL='$bad': no AWS call at all" "" "$LOG"
done
run_script missing 0 GW_EXCEPTION_LEVEL=ERROR
check "dry-run/GW_EXCEPTION_LEVEL=ERROR: fails too, before any AWS call" "1|" "$RC|$LOG"

run_script missing 1
check "apply/missing: exit 0" 0 "$RC"
check "apply/missing: create-gateway gets the description once, and DEBUG (full argument list)" \
  "$(gw_args DEBUG; printf '%s\n' --tags Project=doris-mcp-demo --query gatewayId --output text)" \
  "$(cat "$TMP/create-gateway.args" 2>/dev/null)"
check "apply/missing: every call, in order, and nothing else" \
  "$READS_HEAD
bedrock-agentcore-control create-gateway $(gw_args DEBUG | paste -sd ' ') --tags Project=doris-mcp-demo --query gatewayId --output text
$READS_TAIL
bedrock-agentcore-control create-gateway-target --gateway-identifier gw-fixture0001 --name doris --description AgentCore Runtime dorismcp (SigV4) --target-configuration {\"mcp\": {\"mcpServer\": {\"endpoint\": \"$RUNTIME_URL\"}}} --credential-provider-configurations $CREDS --query targetId --output text
bedrock-agentcore-control get-gateway-target --gateway-identifier gw-fixture0001 --target-id TGTFIXTURE1 --query status --output text" \
  "$LOG"
run_script missing 1 GW_EXCEPTION_LEVEL=
check "apply/missing/GW_EXCEPTION_LEVEL empty: create-gateway without the flag, with the description" \
  "$(gw_args; printf '%s\n' --tags Project=doris-mcp-demo --query gatewayId --output text)" \
  "$(cat "$TMP/create-gateway.args" 2>/dev/null)"

run_script exists 1 SYNC=1
check "apply/SYNC=1: synchronize-gateway-targets once, update-gateway unchanged" "1|$(printf '%s\n' --gateway-identifier gw-fixture0001; gw_args DEBUG; printf '%s\n' --query status --output text)" \
  "$(grep -c 'synchronize-gateway-targets --gateway-identifier gw-fixture0001 --target-id-list TGTFIXTURE1' <<<"$LOG")|$(cat "$TMP/update-gateway.args" 2>/dev/null)"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
```

新文件 `infra/test/test-99-cleanup.sh`（假的 `aws` 是一段 python，维护一个 JSON 的「账号」，每次写操作都改它；检查调用顺序、删完之后账号里还剩什么、每种拒绝都不删任何东西）：

<!-- file: infra/test/test-99-cleanup.sh sha256=199d04d3b16659eb463dbcdc10d4c051873760f47328deca63e90cccf69cb5ea -->
```bash
#!/usr/bin/env bash
# Offline tests for infra/99-cleanup.sh. A fake `aws` (python: a JSON "world" of the project's resources,
# --query evaluated with jmespath like the real CLI) and a fake `sleep` on PATH record every call; no AWS access.
#   bash infra/test/test-99-cleanup.sh
set -uo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
FAKE_PY=""
for py in python3 "$INFRA_DIR/../.venv/bin/python"; do
  if "$py" -c 'import jmespath' 2>/dev/null; then FAKE_PY="$(command -v "$py")"; break; fi
done
[[ -n "$FAKE_PY" ]] || { echo "FAIL setup: no python with jmespath for the fake aws"; echo "1 failed"; exit 1; }

# Fake AWS CLI over $FAKE_WORLD (JSON, rewritten by every write). Logs "$*" to $FAKE_LOG and the region the
# call would use to $FAKE_LOG.region. Errors look like the real CLI's (stderr "An error occurred (Code)", exit 254).
{ echo "#!$FAKE_PY"; cat <<'FAKE'
import json, os, sys
import jmespath

argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(" ".join(argv) + "\n")
with open(os.environ["FAKE_LOG"] + ".region", "a") as f:
    f.write(os.environ.get("AWS_REGION", "-") + "\n")
service, op, rest = argv[0], argv[1], argv[2:]
opts, key = {}, None
for a in rest:
    if a.startswith("--"):
        key = a[2:]; opts[key] = []
    elif key is not None:
        opts[key].append(a)
one = lambda k: opts[k][0]
world_path = os.environ["FAKE_WORLD"]
w = json.load(open(world_path))


def fail(code, op_name, msg="fake error"):
    sys.stderr.write(f"\nAn error occurred ({code}) when calling the {op_name} operation: {msg}\n")
    sys.exit(254)


def filters():
    out = {}
    for f in opts.get("filters", []):
        name, values = f.split(",Values=", 1)
        out[name.removeprefix("Name=")] = values.split(",")
    return out


def text(v):
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, list):
        if all(not isinstance(x, (list, dict)) for x in v):
            return "\t".join(text(x) for x in v)
        return "\n".join(text(x) for x in v)
    if isinstance(v, dict):
        return "\t".join(text(v[k]) for k in sorted(v))
    return str(v)


def enis_in_use():
    """The Runtime's ENIs go some polls after its stack, the endpoints' with the endpoints."""
    if w["stacks"] or any(e["State"] != "deleted" for e in w["vpc_endpoints"]):
        return True
    if w["eni_polls"] > 0:
        w["eni_polls"] -= 1
        return True
    return False


def gateway(gid, op_name):
    if gid not in w["gateways"]:
        fail("ResourceNotFoundException", op_name, f"Gateway {gid} not found")
    return w["gateways"][gid]


def role(name, op_name):
    if name not in w["roles"]:
        fail("NoSuchEntity", op_name, f"The role with name {name} cannot be found.")
    return w["roles"][name]


resp = {}
call = f"{service} {op}"
if w.get("deny") == call:
    fail("AccessDeniedException", op, "not authorized")
if call == "sts get-caller-identity":
    resp = {"Account": w["account"], "UserId": "AIDAFIXTURE", "Arn": f"arn:aws:iam::{w['account']}:user/fixture"}
elif call == "bedrock-agentcore-control get-gateway":
    g = gateway(one("gateway-identifier"), "GetGateway")
    resp = {k: g[k] for k in ("gatewayId", "name", "gatewayArn", "status")}
elif call == "bedrock-agentcore-control list-tags-for-resource":
    g = [g for g in w["gateways"].values() if g["gatewayArn"] == one("resource-arn")]
    if not g:
        fail("ResourceNotFoundException", "ListTagsForResource")
    resp = {"tags": g[0]["tags"]}
elif call == "bedrock-agentcore-control get-gateway-target":
    t = gateway(one("gateway-identifier"), "GetGatewayTarget")["targets"].get(one("target-id"))
    if t is None:
        fail("ResourceNotFoundException", "GetGatewayTarget", "Target not found")
    if t["status"] == "DELETING":
        t["polls"] -= 1
        if t["polls"] < 0:
            del gateway(one("gateway-identifier"), "GetGatewayTarget")["targets"][one("target-id")]
            json.dump(w, open(world_path, "w"))
            fail("ResourceNotFoundException", "GetGatewayTarget", "Target not found")
    resp = {"targetId": one("target-id"), "name": t["name"], "status": t["status"]}
elif call == "bedrock-agentcore-control delete-gateway-target":
    t = gateway(one("gateway-identifier"), "DeleteGatewayTarget")["targets"][one("target-id")]
    t["status"] = "DELETING"
    resp = {"targetId": one("target-id"), "status": "DELETING"}
elif call == "bedrock-agentcore-control delete-gateway":
    g = gateway(one("gateway-identifier"), "DeleteGateway")
    if g["targets"]:
        fail("ValidationException", "DeleteGateway", "Gateway has targets")
    del w["gateways"][one("gateway-identifier")]
    resp = {"gatewayId": one("gateway-identifier"), "status": "DELETING"}
elif call == "cloudformation describe-stacks":
    s = w["stacks"].get(one("stack-name"))
    if s is None:
        fail("ValidationError", "DescribeStacks", f"Stack with id {one('stack-name')} does not exist")
    resp = {"Stacks": [s]}
elif call == "cloudformation delete-stack":
    w["stacks"].pop(one("stack-name"), None)
elif call == "cloudformation wait":
    assert opts == {"stack-name": [w["stack_name"]]} and rest[0] == "stack-delete-complete", rest
elif call == "ec2 describe-vpc-endpoints":
    ids = filters()["vpc-endpoint-id"]
    for e in w["vpc_endpoints"]:  # deleting -> deleted after one more poll; deleted ones linger
        if e["VpcEndpointId"] in ids and e["State"] == "deleting":
            e["polls"] -= 1
            if e["polls"] < 0:
                e["State"] = "deleted"
    resp = {"VpcEndpoints": [{k: v for k, v in e.items() if k != "polls"} for e in w["vpc_endpoints"]
                             if e["VpcEndpointId"] in ids]}
elif call == "ec2 delete-vpc-endpoints":
    bad = []
    for i in opts["vpc-endpoint-ids"]:
        e = [e for e in w["vpc_endpoints"] if e["VpcEndpointId"] == i]
        if e:
            e[0].update(State="deleting", polls=1)
        else:
            bad.append({"ResourceId": i, "Error": {"Code": "InvalidVpcEndpoint.NotFound"}})
    resp = {"Unsuccessful": bad}
elif call == "cognito-idp describe-user-pool":
    p = w["user_pools"].get(one("user-pool-id"))
    if p is None:
        fail("ResourceNotFoundException", "DescribeUserPool", "User pool does not exist.")
    resp = {"UserPool": {"Id": one("user-pool-id"), "Name": "doris-mcp-quick", "UserPoolTags": p["UserPoolTags"],
                         "DeletionProtection": "INACTIVE"}}
elif call == "cognito-idp describe-user-pool-domain":
    owner = w["domains"].get(one("domain"))
    resp = {"DomainDescription": {"UserPoolId": owner, "Domain": one("domain")} if owner else {}}
elif call == "cognito-idp delete-user-pool-domain":
    if w["domains"].get(one("domain")) != one("user-pool-id"):
        fail("InvalidParameterException", "DeleteUserPoolDomain", "No such domain for this pool")
    del w["domains"][one("domain")]
elif call == "cognito-idp delete-user-pool":
    if one("user-pool-id") in w["domains"].values():
        fail("InvalidParameterException", "DeleteUserPool", "User pool has a domain configured")
    del w["user_pools"][one("user-pool-id")]
elif call == "secretsmanager describe-secret":
    s = w["secrets"].get(one("secret-id"))
    if s is None:
        fail("ResourceNotFoundException", "DescribeSecret", "Secrets Manager can't find the specified secret.")
    resp = {"Name": one("secret-id"), **s}
elif call == "secretsmanager delete-secret":
    s = w["secrets"].get(one("secret-id"))
    if s is None or s.get("DeletedDate"):
        fail("InvalidRequestException", "DeleteSecret", "already scheduled for deletion or missing")
    if "force-delete-without-recovery" in opts:
        del w["secrets"][one("secret-id")]
    else:
        days = int(one("recovery-window-in-days"))
        if not 7 <= days <= 30:
            fail("InvalidParameterException", "DeleteSecret", "recovery window out of range")
        s["DeletedDate"] = "2026-10-05T00:00:00+00:00"
elif call == "ec2 describe-security-group-rules":
    gid = filters()["group-id"]
    resp = {"SecurityGroupRules": [r for r in w["sg_rules"] if r["GroupId"] in gid]}
elif op in ("revoke-security-group-ingress", "revoke-security-group-egress"):
    egress = op.endswith("egress")
    for rid in opts["security-group-rule-ids"]:
        r = [r for r in w["sg_rules"] if r["SecurityGroupRuleId"] == rid and r["GroupId"] == one("group-id")
             and r["IsEgress"] == egress]
        if not r:
            fail("InvalidSecurityGroupRuleId.NotFound", op, rid)
        w["sg_rules"].remove(r[0])
    resp = {"Return": True}
elif call == "ec2 describe-security-groups":
    gid = filters()["group-id"]
    resp = {"SecurityGroups": [g for g in w["security_groups"] if g["GroupId"] in gid]}
elif call == "ec2 describe-network-interfaces":
    gid = filters()["group-id"]
    resp = {"NetworkInterfaces": [{"NetworkInterfaceId": "eni-fixture", "Groups": [{"GroupId": g} for g in gid]}]
            if enis_in_use() else []}
elif call == "ec2 delete-security-group":
    gid = one("group-id")
    if any(r.get("ReferencedGroupInfo", {}).get("GroupId") == gid and r["GroupId"] != gid for r in w["sg_rules"]):
        fail("DependencyViolation", "DeleteSecurityGroup", "resource has a dependent object")
    if w["stacks"] or any(e["State"] != "deleted" for e in w["vpc_endpoints"]) or w["eni_polls"] > 0:
        fail("DependencyViolation", "DeleteSecurityGroup", "in use by a network interface")
    w["security_groups"] = [g for g in w["security_groups"] if g["GroupId"] != gid]
    w["sg_rules"] = [r for r in w["sg_rules"] if r["GroupId"] != gid]
elif call == "iam list-role-tags":
    resp = {"Tags": role(one("role-name"), "ListRoleTags")["Tags"], "IsTruncated": False}
elif call == "iam list-role-policies":
    resp = {"PolicyNames": role(one("role-name"), "ListRolePolicies")["policies"], "IsTruncated": False}
elif call == "iam delete-role-policy":
    role(one("role-name"), "DeleteRolePolicy")["policies"].remove(one("policy-name"))
elif call == "iam delete-role":
    if role(one("role-name"), "DeleteRole")["policies"]:
        fail("DeleteConflict", "DeleteRole", "Cannot delete entity, must delete policies first.")
    del w["roles"][one("role-name")]
else:
    sys.stderr.write(f"fake aws: unexpected call: {' '.join(argv)}\n")
    sys.exit(99)
json.dump(w, open(world_path, "w"))
if "query" in opts:
    resp = jmespath.search(one("query"), resp)
if opts.get("output") == ["text"]:
    print(text(resp))
elif resp:
    print(json.dumps(resp, indent=4))
FAKE
} > "$TMP/bin/aws"
printf '#!/usr/bin/env bash\nprintf "sleep %%s\\n" "$*" >> "$FAKE_LOG"\n' > "$TMP/bin/sleep"
chmod +x "$TMP/bin/aws" "$TMP/bin/sleep"

# new_world [PYTHON-STATEMENTS] — the demo's resources, all present and tagged; the statements edit `w`.
new_world() {
  python3 - "$TMP/world.json" "${1-}" <<'PY'
import json, sys
tag = lambda v="doris-mcp-demo", k="Project": [{"Key": "Name", "Value": "fixture"}, {"Key": k, "Value": v}]
rule = lambda rid, gid, egress, port, **peer: {"SecurityGroupRuleId": rid, "GroupId": gid, "IsEgress": egress,
    "IpProtocol": "tcp", "FromPort": port, "ToPort": port, **peer}
ref = lambda g: {"ReferencedGroupInfo": {"GroupId": g, "UserId": "111122223333"}}
w = {
    "account": "111122223333", "stack_name": "AgentCore-dorismcp-default", "eni_polls": 2,
    "gateways": {
        "gw-fixture0001": {"gatewayId": "gw-fixture0001", "name": "doris-mcp-gw", "status": "READY",
                           "gatewayArn": "arn:aws:bedrock-agentcore:us-east-1:111122223333:gateway/gw-fixture0001",
                           "tags": {"Project": "doris-mcp-demo"},
                           "targets": {"TGTFIXTURE1": {"name": "doris", "status": "READY", "polls": 1}}},
        "gw-other0002": {"gatewayId": "gw-other0002", "name": "pragent-github-gw", "status": "READY",
                         "gatewayArn": "arn:aws:bedrock-agentcore:us-east-1:111122223333:gateway/gw-other0002",
                         "tags": {}, "targets": {}}},
    "stacks": {"AgentCore-dorismcp-default": {
        "StackName": "AgentCore-dorismcp-default", "StackStatus": "UPDATE_COMPLETE",
        "Tags": [{"Key": "agentcore:project-name", "Value": "dorismcp"},
                 {"Key": "agentcore:target-name", "Value": "default"}]}},
    "vpc_endpoints": [{"VpcEndpointId": i, "State": "available", "Tags": tag()}
                      for i in ("vpce-s3fixture", "vpce-logsfixture", "vpce-smfixture")],
    "user_pools": {"us-east-1_EXAMPLE": {"UserPoolTags": {"Project": "doris-mcp-demo"}}},
    "domains": {"doris-mcp-111122223333": "us-east-1_EXAMPLE"},
    "secrets": {n: {"ARN": f"arn:aws:secretsmanager:us-east-1:111122223333:secret:{n}-AbCdEf", "Tags": tag()[1:]}
                for n in ("doris-mcp/cognito-demo-user", "doris-mcp/mcp_svc")},
    # doris-demo-sg: the two rules 10-network.sh added, then rules that are not ours (the dev box's /32 carries
    # the project tag on purpose: the selector is the reference to doris-mcp-rt, the tag only a second check).
    "sg_rules": [
        rule("sgr-doris9030", "sg-doris", False, 9030, **ref("sg-rt"), Tags=tag()),
        rule("sgr-doris8030", "sg-doris", False, 8030, **ref("sg-rt"), Tags=tag()),
        rule("sgr-dorisdev", "sg-doris", False, 9030, CidrIpv4="203.0.113.10/32", Tags=tag()),
        rule("sgr-dorisother", "sg-doris", False, 9030, **ref("sg-other"), Tags=[]),
        rule("sgr-dorisegress", "sg-doris", True, 443, **ref("sg-other"), Tags=[]),
        rule("sgr-rt9030", "sg-rt", True, 9030, **ref("sg-doris"), Tags=tag()),
        rule("sgr-rt8030", "sg-rt", True, 8030, **ref("sg-doris"), Tags=tag()),
        rule("sgr-rtvpce", "sg-rt", True, 443, **ref("sg-vpce"), Tags=tag()),
        rule("sgr-rts3", "sg-rt", True, 443, PrefixListId="pl-fixture", Tags=tag()),
        rule("sgr-vpcert", "sg-vpce", False, 443, **ref("sg-rt"), Tags=tag())],
    "security_groups": [{"GroupId": g, "GroupName": n, "Tags": tag()}
                        for g, n in (("sg-rt", "doris-mcp-rt"), ("sg-vpce", "doris-mcp-vpce"))]
                       + [{"GroupId": "sg-doris", "GroupName": "doris-demo-sg", "Tags": []}],
    "roles": {"doris-mcp-gateway-role": {"Tags": tag()[1:], "policies": ["invoke-dorismcp-runtime"]},
              "doris-mcp-runtime-role": {"Tags": tag()[1:], "policies": ["doris-mcp-runtime"]}},
}
exec(sys.argv[2])
json.dump(w, open(sys.argv[1], "w"))
PY
}
FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
# run_script APPLY [VAR=value...] — runs the script against the current world and a fresh state.env;
# sets RC, OUT, LOG, WRITES (the mutating calls, in order) and DRY (the DRY-RUN lines, in order).
run_script() {
  local apply="$1"; shift
  : > "$TMP/aws.log"; : > "$TMP/aws.log.region"
  printf '%s\n' '# test state' 'AWS_REGION=us-east-1' 'ACCOUNT_ID=111122223333' 'GW_ID=gw-fixture0001' \
    'GW_TARGET_ID=TGTFIXTURE1' 'VPCE_S3=vpce-s3fixture' 'VPCE_LOGS=vpce-logsfixture' 'VPCE_SECRETSMANAGER=vpce-smfixture' \
    'COGNITO_POOL_ID=us-east-1_EXAMPLE' 'COGNITO_DOMAIN=doris-mcp-111122223333.auth.us-east-1.amazoncognito.com' \
    'DORIS_SG=sg-doris' 'RT_SG=sg-rt' 'VPCE_SG=sg-vpce' > "$TMP/state.env"
  cp "$TMP/state.env" "$TMP/state.env.orig"
  OUT="$(env -u STACK_NAME -u SECRET_RECOVERY_DAYS -u FORCE_DELETE_SECRETS "$@" PATH="$TMP/bin:$PATH" \
    FAKE_LOG="$TMP/aws.log" FAKE_WORLD="$TMP/world.json" APPLY="$apply" STATE_FILE="$TMP/state.env" \
    bash "$INFRA_DIR/99-cleanup.sh" 2>&1)"
  RC=$?
  LOG="$(cat "$TMP/aws.log")"
  WRITES="$(grep -E '^[a-z0-9-]+ (delete-|revoke-|wait )' <<<"$LOG" | grep -v '^sleep')"
  DRY="$(sed -n 's/^DRY-RUN: aws //p' <<<"$OUT")"
}
has() { [[ "$1" == *"$2"* ]] && echo yes || echo no; }
count() { grep -c -- "$2" <<<"$1"; }
# The full teardown, in order: target (then its wait), Gateway, stack, endpoints, Cognito, secrets,
# doris-demo-sg's two rules, the SG cross-references, both SGs, the roles' inline policies and the roles.
ALL_WRITES="bedrock-agentcore-control delete-gateway-target --gateway-identifier gw-fixture0001 --target-id TGTFIXTURE1
bedrock-agentcore-control delete-gateway --gateway-identifier gw-fixture0001
cloudformation delete-stack --stack-name AgentCore-dorismcp-default
cloudformation wait stack-delete-complete --stack-name AgentCore-dorismcp-default
ec2 delete-vpc-endpoints --vpc-endpoint-ids vpce-s3fixture vpce-logsfixture vpce-smfixture
cognito-idp delete-user-pool-domain --domain doris-mcp-111122223333 --user-pool-id us-east-1_EXAMPLE
cognito-idp delete-user-pool --user-pool-id us-east-1_EXAMPLE
secretsmanager delete-secret --secret-id doris-mcp/cognito-demo-user --recovery-window-in-days 7
secretsmanager delete-secret --secret-id doris-mcp/mcp_svc --recovery-window-in-days 7
ec2 revoke-security-group-ingress --group-id sg-doris --security-group-rule-ids sgr-doris9030 sgr-doris8030
ec2 revoke-security-group-egress --group-id sg-rt --security-group-rule-ids sgr-rtvpce
ec2 revoke-security-group-ingress --group-id sg-vpce --security-group-rule-ids sgr-vpcert
ec2 delete-security-group --group-id sg-rt
ec2 delete-security-group --group-id sg-vpce
iam delete-role-policy --role-name doris-mcp-gateway-role --policy-name invoke-dorismcp-runtime
iam delete-role --role-name doris-mcp-gateway-role
iam delete-role-policy --role-name doris-mcp-runtime-role --policy-name doris-mcp-runtime
iam delete-role --role-name doris-mcp-runtime-role"
SG_AND_IAM_WRITES="$(sed -n '/revoke-security-group-egress/,$p' <<<"$ALL_WRITES")"

# --- dry-run -----------------------------------------------------------------
new_world; run_script 0
check "dry-run: exit 0" 0 "$RC"
check "dry-run: no delete / revoke / wait call" "" "$WRITES"
check "dry-run: every DRY-RUN line, in order" "$ALL_WRITES" "$DRY"
check "dry-run: checks the account first" "sts get-caller-identity --query Account --output text" "$(head -1 <<<"$LOG")"
check "dry-run: no sleep" 0 "$(count "$LOG" '^sleep')"
check "dry-run: state.env unchanged" "" "$(diff "$TMP/state.env.orig" "$TMP/state.env")"

# --- apply, everything present -------------------------------------------------
new_world; run_script 1
check "apply: exit 0" 0 "$RC"
check "apply: deletes in dependency order" "$ALL_WRITES" "$WRITES"
check "apply: target gone before delete-gateway (polled get-gateway-target)" yes \
  "$(sed -n '/delete-gateway-target/,/delete-gateway --/p' <<<"$LOG" | grep -q 'get-gateway-target' && echo yes || echo no)"
check "apply: waits for the endpoints before Cognito" yes \
  "$(sed -n '/delete-vpc-endpoints/,/delete-user-pool-domain/p' <<<"$LOG" | grep -q 'describe-vpc-endpoints' && echo yes || echo no)"
check "apply: polls the ENIs (20 s apart) until free, before the SG revokes" "yes|2" \
  "$(sed -n '/revoke-security-group-ingress --group-id sg-doris/,/revoke-security-group-egress/p' <<<"$LOG" | grep -q 'describe-network-interfaces --filters Name=group-id,Values=sg-rt,sg-vpce' && echo yes || echo no)|$(count "$LOG" '^sleep 20$')"
check "apply: the other project's Gateway untouched" yes \
  "$(python3 -c 'import json,sys; print("yes" if "gw-other0002" in json.load(open(sys.argv[1]))["gateways"] else "no")' "$TMP/world.json")"
check "apply: doris-demo-sg keeps its other rules (dev /32, other SG, egress)" "sgr-dorisdev sgr-dorisother sgr-dorisegress" \
  "$(python3 -c 'import json,sys; print(" ".join(r["SecurityGroupRuleId"] for r in json.load(open(sys.argv[1]))["sg_rules"] if r["GroupId"] == "sg-doris"))' "$TMP/world.json")"
check "apply: state.env unchanged (kept as the record)" "" "$(diff "$TMP/state.env.orig" "$TMP/state.env")"
check "apply: says state.env is kept and the Doris side is separate" "yes|yes" \
  "$(has "$OUT" "state.env")|$(has "$OUT" "DROP USER mcp_svc")"
check "apply: every call in the state's region" "us-east-1" "$(sort -u "$TMP/aws.log.region")"

# re-run after a full teardown: nothing left, nothing to do
run_script 1
check "re-run after a full teardown: exit 0, no write" "0|" "$RC|$WRITES"
check "re-run after a full teardown: says already deleted" yes "$(has "$OUT" "already deleted")"

# caller's AWS_REGION does not win over state.env
new_world; run_script 0 AWS_REGION=eu-west-1 AWS_DEFAULT_REGION=eu-west-1
check "caller AWS_REGION=eu-west-1: calls still in us-east-1" "us-east-1" "$(sort -u "$TMP/aws.log.region")"

# --- refusals: nothing is deleted ----------------------------------------------
new_world 'w["account"] = "000000000000"'; run_script 1
check "wrong account: fails" 1 "$RC"
check "wrong account: no write" "" "$WRITES"
check "wrong account: FATAL" yes "$(has "$OUT" "FATAL")"
check "wrong account: no call after sts" "sts get-caller-identity --query Account --output text" "$LOG"

# refuse PYTHON-EDIT NAME — a world edit that must stop the run with FATAL before any write
refuse() {
  new_world "$1"; run_script 1
  check "$2: fails" 1 "$RC"
  check "$2: FATAL" yes "$(has "$OUT" "FATAL")"
  check "$2: no write at all" "" "$WRITES"
}
refuse 'w["gateways"]["gw-fixture0001"]["name"] = "pragent-github-gw"' "Gateway named otherwise"
refuse 'w["gateways"]["gw-fixture0001"]["tags"] = {"Project": "other"}' "Gateway tagged for another project"
refuse 'w["gateways"]["gw-fixture0001"]["tags"] = {}' "Gateway without tags"
refuse 'w["stacks"]["AgentCore-dorismcp-default"]["Tags"][0]["Value"] = "otherproject"' "stack of another agentcore project"
refuse 'w["vpc_endpoints"][2]["Tags"] = []' "VPC endpoint without the tag"
refuse 'w["user_pools"]["us-east-1_EXAMPLE"]["UserPoolTags"] = {"Project": "other"}' "user pool tagged otherwise"
refuse 'w["domains"]["doris-mcp-111122223333"] = "us-east-1_OTHER"' "Cognito domain of another pool"
refuse 'w["secrets"]["doris-mcp/mcp_svc"]["Tags"] = []' "secret without the tag"
refuse 'w["sg_rules"][1]["Tags"] = []' "doris-demo-sg rule referencing RT_SG without the tag"
refuse 'w["security_groups"][1]["Tags"] = [{"Key": "Project", "Value": "other"}]' "SG tagged otherwise"
refuse 'w["roles"]["doris-mcp-runtime-role"]["Tags"] = []' "IAM role without the tag"
refuse 'w["deny"] = "bedrock-agentcore-control get-gateway"' "get-gateway denied (not the same as deleted)"
refuse 'w["deny"] = "iam list-role-tags"' "list-role-tags denied (not the same as deleted)"
refuse 'w["deny"] = "secretsmanager describe-secret"' "describe-secret denied (not the same as deleted)"

new_world; run_script 1 SECRET_RECOVERY_DAYS=3
check "SECRET_RECOVERY_DAYS=3: fails before any AWS call" "1|" "$RC|$LOG"
new_world; run_script 1 SECRET_RECOVERY_DAYS=08
check "SECRET_RECOVERY_DAYS=08: fails before any AWS call" "1|" "$RC|$LOG"

# --- ENIs still in use ----------------------------------------------------------
new_world 'w["eni_polls"] = 10**6'; run_script 1
check "ENIs stay: fails" 1 "$RC"
check "ENIs stay: says to re-run later" yes "$(has "$OUT" "re-run later")"
check "ENIs stay: bounded wait (30 polls, 29 x 20 s)" "30|29" \
  "$(count "$LOG" 'describe-network-interfaces')|$(count "$LOG" '^sleep 20$')"
check "ENIs stay: no SG deleted, no cross-reference revoked, no role touched" 0 \
  "$(grep -cE 'delete-security-group|revoke-security-group-egress|group-id sg-vpce|iam delete' <<<"$WRITES")"
check "ENIs stay: everything before the SG step done" \
  "$(sed -n '1,/revoke-security-group-ingress --group-id sg-doris/p' <<<"$ALL_WRITES")" "$WRITES"
# ... then the ENIs go away: the re-run skips what is gone and finishes
python3 -c 'import json,sys; w=json.load(open(sys.argv[1])); w["eni_polls"]=0; json.dump(w, open(sys.argv[1], "w"))' "$TMP/world.json"
run_script 1
check "re-run after the ENI timeout: exit 0" 0 "$RC"
check "re-run after the ENI timeout: only the SG and IAM steps" "$SG_AND_IAM_WRITES" "$WRITES"
check "re-run after the ENI timeout: gone resources logged as already deleted" "yes|yes|yes|yes" \
  "$(has "$OUT" "Gateway gw-fixture0001 already deleted")|$(has "$OUT" "AgentCore-dorismcp-default already deleted")|$(has "$OUT" "vpce-smfixture already deleted")|$(has "$OUT" "us-east-1_EXAMPLE already deleted")"
check "re-run after the ENI timeout: secrets already scheduled are left alone" "0|yes" \
  "$(count "$LOG" 'delete-secret')|$(has "$OUT" "doris-mcp/mcp_svc already scheduled for deletion")"

# partial state: the target alone is gone; the stack is already being deleted
new_world 'w["gateways"]["gw-fixture0001"]["targets"] = {}'; run_script 1
check "target already gone: exit 0, delete-gateway without delete-gateway-target" "0|0|1" \
  "$RC|$(count "$WRITES" 'delete-gateway-target')|$(count "$WRITES" 'delete-gateway --gateway-identifier gw-fixture0001')"

# --- secrets knobs --------------------------------------------------------------
new_world; run_script 1 FORCE_DELETE_SECRETS=1
check "FORCE_DELETE_SECRETS=1: both secrets deleted without recovery" "2|0" \
  "$(count "$WRITES" 'delete-secret --secret-id doris-mcp/[a-z_-]* --force-delete-without-recovery$')|$(count "$WRITES" 'recovery-window')"
new_world; run_script 0 SECRET_RECOVERY_DAYS=30
check "SECRET_RECOVERY_DAYS=30: 30-day recovery window" 2 "$(count "$DRY" 'delete-secret --secret-id doris-mcp/[a-z_-]* --recovery-window-in-days 30$')"
new_world; run_script 0 FORCE_DELETE_SECRETS=0
check "FORCE_DELETE_SECRETS=0: the 7-day default" 2 "$(count "$DRY" 'delete-secret --secret-id doris-mcp/[a-z_-]* --recovery-window-in-days 7$')"

# --- STACK_NAME knob ------------------------------------------------------------
new_world 'w["stacks"] = {"AgentCore-dorismcp-other": dict(w["stacks"]["AgentCore-dorismcp-default"], StackName="AgentCore-dorismcp-other")}; w["stack_name"] = "AgentCore-dorismcp-other"'
run_script 1 STACK_NAME=AgentCore-dorismcp-other
check "STACK_NAME override: that stack is deleted and waited for" "0|1|1" \
  "$RC|$(count "$WRITES" '^cloudformation delete-stack --stack-name AgentCore-dorismcp-other$')|$(count "$WRITES" '^cloudformation wait stack-delete-complete --stack-name AgentCore-dorismcp-other$')"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
```

新文件 `scripts/test/test-demo-check.sh`（假的 `PYTHON` 按脚本名和子命令记录调用，以及每个子进程看到的 `DORIS_*` 变量名和 token 是否存在）：

<!-- file: scripts/test/test-demo-check.sh sha256=8f8334a13a3ceed780394c88ea53a470e702b5b1d85ee486fd4668fa49c75a3d -->
```bash
#!/usr/bin/env bash
# Offline tests for scripts/demo-check.sh: fake `aws` on PATH, a fake PYTHON and a fake TOKEN_CMD that record
# argv and which DORIS_* / GW_TOKEN variables reach them (names; values only as match/other), and print canned
# output with a TEST-NET address and an https URL for the mask. No AWS, no Doris, no Gateway.
#   bash scripts/test/test-demo-check.sh
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/demo-check.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
TOKEN="tok-fixture-9f8e7d6c5b4a"

# names VAR... helper for the fakes: the DORIS_* and GW_TOKEN variables in the environment, sorted.
cat > "$TMP/names.sh" <<'NAMES'
names() { compgen -e | grep -E '^(DORIS_|GW_TOKEN$)' | sort | paste -sd ' '; }
token_state() { if [[ -z "${GW_TOKEN+x}" ]]; then echo none; elif [[ "$GW_TOKEN" == tok-fixture-9f8e7d6c5b4a ]]; then echo match; else echo other; fi; }
NAMES
# Fake AWS CLI. FAKE_ACCOUNT, FAKE_GW_STATUS, FAKE_TARGET_STATUS; FAKE_AWS_FAIL="service operation" fails that call.
cat > "$TMP/bin/aws" <<'FAKE'
#!/usr/bin/env bash
source "$FAKE_DIR/names.sh"
{ echo "aws: $*"; echo "aws-env $1.$2: $(names)"; } >> "$FAKE_LOG"
if [[ "$1 $2" == "${FAKE_AWS_FAIL:-}" ]]; then
  echo "An error occurred (ExpiredToken) calling https://api.example.test/x from 198.51.100.23" >&2; exit 254
fi
case "$1 $2" in
  "sts get-caller-identity") echo "${FAKE_ACCOUNT:-111122223333}" ;;
  "bedrock-agentcore-control get-gateway") echo "${FAKE_GW_STATUS:-READY}" ;;
  "bedrock-agentcore-control get-gateway-target") echo "${FAKE_TARGET_STATUS:-READY}" ;;
  "logs filter-log-events") echo '{"events": [{"message": "doris_new_mcp.audit: {}"}]}' ;;
  "cloudwatch get-metric-data") echo '{"MetricDataResults": []}' ;;
  *) echo "fake aws: unexpected call: $*" >&2; exit 99 ;;
esac
FAKE
# Fake PYTHON: "$PYTHON" SCRIPT ARGS... ; the tag is the script's name plus its subcommand, if any.
# FAKE_FAIL=TAG makes that one exit 1; FAKE_TOOLS (12) and FAKE_CONNS (12) shape mcp_smoke's output.
cat > "$TMP/bin/fake-python" <<'FAKE'
#!/usr/bin/env bash
source "$FAKE_DIR/names.sh"
script="$(basename "$1" .py)"; tag="$script"
for a in "${@:2}"; do case "$a" in list|flow|conns|queries|report) tag="$script.$a"; break ;; esac; done
{ echo "py: $*"; echo "py-env $tag: $(names)"; echo "py-token $tag: $(token_state)"
  echo "py-region $tag: ${AWS_REGION:-none}"
  if [[ "$tag" == reconcile ]]; then
    case "${DORIS_PASSWORD-}" in ro-pass-fixture) pw=ro ;; root-pass-fixture) pw=root ;; "") pw=none ;; *) pw=other ;; esac
    echo "py-doris: ${DORIS_HOST-none}|${DORIS_PORT-none}|${DORIS_USER-none}|$pw"
  fi
  case "$tag" in audit_check|gw_latency.report) echo "py-stdin $tag: $(head -c 20)" ;; esac; } >> "$FAKE_LOG"
if [[ "$tag" == "${FAKE_FAIL:-}" ]]; then echo "FAIL: fixture failure talking to 198.51.100.23"; exit 1; fi
case "$tag" in
  mcp_smoke.list)
    for ((i = 1; i <= ${FAKE_TOOLS:-12}; i++)); do echo "  doris___tool$i"; done; echo "tools: ${FAKE_TOOLS:-12}"
    [[ "${FAKE_TOOLS:-12}" == 12 ]] || { echo "FAIL: expected 12 tools"; exit 1; } ;;
  mcp_smoke.flow) echo "connected+initialized in 640 ms (https://gw.example.test/mcp)"; echo "  [PASS] profile"
    echo "flow: 6/6 passed" ;;
  mcp_smoke.conns) echo "connections: ${FAKE_CONNS:-12} (Sleep ${FAKE_CONNS:-12}) from 2 distinct hosts; users mcp_svc; max idle 30 s"
    echo "  [PASS] host prefix 172.31.: ${FAKE_CONNS:-12}/${FAKE_CONNS:-12} connections"
    echo "  [PASS] idle connections <= 610 s: 0 over" ;;
  reconcile) echo "reference SQL on 198.51.100.7:9030"; echo "11/11 cases match" ;;
  permission_matrix) echo "identity mcp_svc@172.31.%"; echo "5/5 checks pass" ;;
  audit_check) echo "audit: 40 records, 0 failures" ;;
  gw_latency.queries) echo '[{"Id": "q1"}]' ;;
  gw_latency.report) echo "doris___execute_query 10:05 3 calls max 820 ms" ;;
  *) echo "fake python: unexpected: $*" >&2; exit 99 ;;
esac
FAKE
# Fake TOKEN_CMD: prints the fixture token; FAKE_TOKEN_FAIL=1 fails with an error naming a URL and an address.
cat > "$TMP/token.sh" <<'FAKE'
source "$FAKE_DIR/names.sh"
echo "token-env: $(names)" >> "$FAKE_LOG"
if [[ "${FAKE_TOKEN_FAIL:-}" == 1 ]]; then echo "token request failed: https://auth.example.test/oauth2/token 198.51.100.24" >&2; exit 1; fi
echo "tok-fixture-9f8e7d6c5b4a"
FAKE
chmod +x "$TMP/bin/aws" "$TMP/bin/fake-python"
CRED_LINES=('DORIS_HOST=198.51.100.7' 'DORIS_MYSQL_PORT=9030' 'DORIS_HTTP_PORT=8030' 'DORIS_ROOT_USER=root'
  'DORIS_ROOT_PASSWORD=root-pass-fixture' 'DORIS_RO_USER=demo_ro' 'DORIS_RO_PASSWORD=ro-pass-fixture')
printf '%s\n' "${CRED_LINES[@]}" > "$TMP/cred.env"
printf 'export %s\n' "${CRED_LINES[@]}" > "$TMP/cred-export.env"
printf '%s\n' '# test state' 'AWS_REGION=us-east-1' 'ACCOUNT_ID=111122223333' 'GW_ID=gw-fixture0001' \
  'GW_TARGET_ID=TGTFIXTURE1' 'GW_URL=https://gw.example.test/mcp' 'RUNTIME_ID=dorismcp_dorismcp-AbCdEf1234' \
  'RUNTIME_URL=https://runtime.example.test/invocations?qualifier=DEFAULT' 'DORIS_SG=sg-doris' \
  'DORIS_SECRET_ARN=arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-AbCdEf' > "$TMP/state.env"

FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
EXTRA=()  # VAR=value pairs for the next run (the caller's environment, fake knobs)
CRED="$TMP/cred.env"
# run_check ARGS... — sets RC, OUT (stdout), ERR (stderr), LOG (what the fakes saw)
run_check() {
  : > "$TMP/fake.log"
  OUT="$(env -u GW_TOKEN -u MAX_CONNS -u TOKEN_CMD -u PYTHON -u CREDENTIALS_FILE -u AWS_REGION "${EXTRA[@]}" \
    PATH="$TMP/bin:$PATH" FAKE_DIR="$TMP" FAKE_LOG="$TMP/fake.log" STATE_FILE="$TMP/state.env" \
    PYTHON="$TMP/bin/fake-python" CREDENTIALS_FILE="$CRED" TOKEN_CMD="bash $TMP/token.sh" \
    bash "$SCRIPT" "$@" 2>"$TMP/err")"
  RC=$?; ERR="$(cat "$TMP/err")"; LOG="$(cat "$TMP/fake.log")"
}
has() { [[ "$1" == *"$2"* ]] && echo yes || echo no; }
count() { grep -c -- "$2" <<<"$1"; }
field() { sed -n "s/^$2: //p" <<<"$1"; } # LOG PREFIX → the recorded values, one per line
verdicts() { grep -E '^\[(PASS|FAIL)\] ' <<<"$OUT"; }
# The DORIS_* names that reached a child other than reconcile, as "child: NAME" lines.
doris_elsewhere() {
  grep -E '^(aws-env|token-env|py-env)' <<<"$LOG" | grep -v '^py-env reconcile:' | grep -E 'DORIS_' \
    | sed -E 's/^([^:]*):.*/\1/' | paste -sd ' '
}
# The token and the credential values must never show up in an argv, in the output or in the log.
leaks() { grep -cE -- "$TOKEN|root-pass-fixture|ro-pass-fixture|caller-(token|root|ro|admin)" <<<"$OUT
$ERR
$LOG"; }
SMOKE="scripts/mcp_smoke.py --url https://gw.example.test/mcp --bearer-env GW_TOKEN --timeout 60"
RT_URL="https://runtime.example.test/invocations?qualifier=DEFAULT"
PRE_PASS="[PASS] account
[PASS] gateway READY
[PASS] target READY
[PASS] token
[PASS] list 12 tools
[PASS] flow
[PASS] reconcile
[PASS] permission matrix
[PASS] conns
[PASS] conns <= MAX_CONNS"

# --- pre, everything fine --------------------------------------------------------------
run_check pre
check "pre: exit 0" 0 "$RC"
check "pre: every check passes, in order" "$PRE_PASS" "$(verdicts)"
check "pre: summary line" "demo-check pre: 10/10 passed" "$(tail -1 <<<"$OUT")"
check "pre: AWS reads (account, Gateway, target), with the region" \
  "sts get-caller-identity --region us-east-1 --query Account --output text
bedrock-agentcore-control get-gateway --gateway-identifier gw-fixture0001 --region us-east-1 --query status --output text
bedrock-agentcore-control get-gateway-target --gateway-identifier gw-fixture0001 --target-id TGTFIXTURE1 --region us-east-1 --query status --output text" \
  "$(field "$LOG" aws)"
check "pre: python children and their arguments, in order" \
  "$SMOKE list --expect 12
$SMOKE flow --prefix doris___
doris/reconcile.py mcp --url $RT_URL
doris/permission_matrix.py --url $RT_URL --expect-host 172.31.%
$SMOKE conns --prefix doris___ --expect-host-prefix 172.31. --max-idle 610" "$(field "$LOG" py)"
check "pre: the token is in mcp_smoke's environment, and only there" \
  "py-token mcp_smoke.list: match|py-token mcp_smoke.flow: match|py-token reconcile: none|py-token permission_matrix: none|py-token mcp_smoke.conns: match" \
  "$(grep '^py-token' <<<"$LOG" | paste -sd '|')"
check "pre: no GW_TOKEN in the environment of aws or the token command" 0 "$(grep -E '^(aws-env|token-env)' <<<"$LOG" | grep -c GW_TOKEN)"
check "pre: the token and the credential values never in argv, output or log" 0 "$(leaks)"
check "pre: reconcile gets exactly DORIS_HOST/PORT/USER/PASSWORD" "DORIS_HOST DORIS_PASSWORD DORIS_PORT DORIS_USER" \
  "$(field "$LOG" "py-env reconcile")"
check "pre: reconcile's Doris settings are the read-only account's" "198.51.100.7|9030|demo_ro|ro" "$(field "$LOG" py-doris)"
check "pre: reconcile runs in us-east-1" us-east-1 "$(field "$LOG" "py-region reconcile")"
check "pre: no DORIS_* variable reaches any other child (state.env's DORIS_SG included)" "" "$(doris_elsewhere)"
check "pre: output masked (no IPv4, no https URL; <ip> and <url> shown)" "0|0|yes|yes" \
  "$(count "$OUT" '198\.51\.100\.')|$(count "$OUT" 'https://')|$(has "$OUT" '<ip>')|$(has "$OUT" '<url>')"
check "pre: nothing on stderr" "" "$ERR"

# --- the credentials file with export lines, and a caller who exported a token and Doris variables ---------
CRED="$TMP/cred-export.env"
EXTRA=(GW_TOKEN=caller-token-fixture DORIS_ROOT_USER=caller-root DORIS_ROOT_PASSWORD=caller-root-pw
       DORIS_RO_USER=caller-ro DORIS_RO_PASSWORD=caller-ro-pw DORIS_ADMIN_PASSWORD=caller-admin-pw DORIS_HOST=203.0.113.99)
run_check pre
check "caller-exported + export lines: exit 0, all checks pass" "0|$PRE_PASS" "$RC|$(verdicts)"
check "caller-exported + export lines: reconcile still gets exactly the four, from the file" \
  "DORIS_HOST DORIS_PASSWORD DORIS_PORT DORIS_USER|198.51.100.7|9030|demo_ro|ro" \
  "$(field "$LOG" "py-env reconcile")|$(field "$LOG" py-doris)"
check "caller-exported + export lines: no DORIS_* anywhere else" "" "$(doris_elsewhere)"
check "caller-exported + export lines: mcp_smoke gets the fresh token, nobody else any" \
  "match match match|0" \
  "$(grep '^py-token mcp_smoke' <<<"$LOG" | sed 's/.*: //' | paste -sd ' ')|$(grep -E '^(aws-env|token-env)|^py-env (reconcile|permission_matrix)' <<<"$LOG" | grep -c GW_TOKEN)"
check "caller-exported + export lines: no leak" 0 "$(leaks)"
CRED="$TMP/cred.env"; EXTRA=()

# --- one check fails: [FAIL], the count, exit 1 ----------------------------------------------------------
fails_one() { # NAME EXPECTED-FAIL-LINE SUMMARY ARGS... (with EXTRA set by the caller)
  local name="$1" line="$2" summary="$3"; shift 3
  run_check "$@"
  check "$name: exit 1" 1 "$RC"
  check "$name: $line" yes "$(has "$(verdicts)" "$line")"
  check "$name: summary" "$summary" "$(tail -1 <<<"$OUT")"
  check "$name: masked, no leak" "0|0|0" "$(count "$OUT" '198\.51\.100\.')|$(count "$OUT" 'https://')|$(leaks)"
}
EXTRA=(FAKE_ACCOUNT=000000000000); fails_one "wrong account" "[FAIL] account" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_GW_STATUS=UPDATING); fails_one "Gateway UPDATING" "[FAIL] gateway READY" "demo-check pre: 9/10 passed" pre
check "Gateway UPDATING: the status is shown" yes "$(has "$OUT" "UPDATING")"
EXTRA=(FAKE_TARGET_STATUS=FAILED); fails_one "target FAILED" "[FAIL] target READY" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_AWS_FAIL="bedrock-agentcore-control get-gateway"); fails_one "get-gateway error" "[FAIL] gateway READY" \
  "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_TOOLS=11); fails_one "11 tools" "[FAIL] list 12 tools" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_FAIL=reconcile); fails_one "reconcile fails" "[FAIL] reconcile" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_FAIL=permission_matrix); fails_one "permission matrix fails" "[FAIL] permission matrix" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_CONNS=81); fails_one "81 connections" "[FAIL] conns <= MAX_CONNS" "demo-check pre: 9/10 passed" pre
check "81 connections: conns itself passes, the count is shown" "yes|yes" "$(has "$OUT" "[PASS] conns")|$(has "$OUT" "81")"
EXTRA=(FAKE_CONNS=80); run_check pre
check "80 connections (= MAX_CONNS): passes" "0|demo-check pre: 10/10 passed" "$RC|$(tail -1 <<<"$OUT")"
EXTRA=(FAKE_CONNS=6 MAX_CONNS=5); fails_one "MAX_CONNS=5, 6 connections" "[FAIL] conns <= MAX_CONNS" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_CONNS=5 MAX_CONNS=5); run_check pre
check "MAX_CONNS=5, 5 connections: passes" 0 "$RC"

EXTRA=(FAKE_TOKEN_FAIL=1); run_check pre
check "no token: exit 1" 1 "$RC"
check "no token: the Gateway checks fail without calling mcp_smoke; the Runtime checks still run" \
  "[PASS] account
[PASS] gateway READY
[PASS] target READY
[FAIL] token
[FAIL] list 12 tools
[FAIL] flow
[PASS] reconcile
[PASS] permission matrix
[FAIL] conns
[FAIL] conns <= MAX_CONNS|demo-check pre: 5/10 passed|0" "$(verdicts)|$(tail -1 <<<"$OUT")|$(count "$LOG" '^py: scripts/mcp_smoke')"
check "no token: says why, token error masked" "yes|0|0" \
  "$(has "$OUT" "skipped: no Gateway token")|$(count "$OUT$ERR" '198\.51\.100\.')|$(count "$OUT$ERR" 'https://')"
EXTRA=()

# --- post -------------------------------------------------------------------------------------------
ms() { echo $(( $(date -u -d "$1" +%s) * 1000 + $2 )); } # ISO-8601 MILLIS → epoch ms
SINCE="$(ms 2026-09-28T10:00:30Z 500)" UNTIL="$(ms 2026-09-28T10:30:00Z 0)"
run_check post --since "$SINCE" --until "$UNTIL"
check "post: exit 0" 0 "$RC"
check "post: checks in order" "[PASS] audit
[PASS] latency
[PASS] token
[PASS] conns
[PASS] conns <= MAX_CONNS|demo-check post: 5/5 passed" "$(verdicts)|$(tail -1 <<<"$OUT")"
check "post: filter-log-events on the Runtime's log group, the exact window in ms, audit records only" \
  "logs filter-log-events --region us-east-1 --log-group-name /aws/bedrock-agentcore/runtimes/dorismcp_dorismcp-AbCdEf1234-DEFAULT --start-time $SINCE --end-time $UNTIL --filter-pattern \"doris_new_mcp.audit\" --output json" \
  "$(grep '^aws: logs' <<<"$LOG" | sed 's/^aws: //')"
check "post: audit_check --failures reads filter-log-events' output" "scripts/audit_check.py --failures|{\"events\": [{\"messag" \
  "$(field "$LOG" py | grep audit_check)|$(field "$LOG" "py-stdin audit_check")"
check "post: latency window widened to whole minutes (since 10:00:30.5 -> 10:00, until 10:30 stays)" \
  "cloudwatch get-metric-data --region us-east-1 --start-time 2026-09-28T10:00:00Z --end-time 2026-09-28T10:30:00Z --metric-data-queries [{\"Id\": \"q1\"}] --output json" \
  "$(grep '^aws: cloudwatch' <<<"$LOG" | sed 's/^aws: //')"
check "post: gw_latency queries for this Gateway's ARN, report reads get-metric-data's output" \
  "scripts/gw_latency.py queries --gateway-arn arn:aws:bedrock-agentcore:us-east-1:111122223333:gateway/gw-fixture0001|scripts/gw_latency.py report|{\"MetricDataResults\"" \
  "$(field "$LOG" py | grep gw_latency | paste -sd '|')|$(field "$LOG" "py-stdin gw_latency.report")"
check "post: no pre-only check (sts, Gateway status, reconcile, permission matrix, list, flow)" 0 \
  "$(grep -cE 'sts |get-gateway|reconcile|permission_matrix| list | flow ' <<<"$(field "$LOG" aws; field "$LOG" py)")"
check "post: token only in mcp_smoke conns; no leak" "py-token mcp_smoke.conns: match|0" \
  "$(grep '^py-token' <<<"$LOG" | grep -v ': none$' | paste -sd '|')|$(leaks)"
SINCE="$(ms 2026-09-28T10:00:59Z 999)" UNTIL="$(ms 2026-09-28T10:29:01Z 0)"
run_check post --since "$SINCE" --until "$UNTIL"
check "post: since 10:00:59.999 -> 10:00, until 10:29:01 -> 10:30" "--start-time 2026-09-28T10:00:00Z --end-time 2026-09-28T10:30:00Z" \
  "$(grep '^aws: cloudwatch' <<<"$LOG" | grep -oE -- '--start-time [^ ]+ --end-time [^ ]+')"
EXTRA=(FAKE_FAIL=audit_check); fails_one "audit failures" "[FAIL] audit" "demo-check post: 4/5 passed" post --since "$SINCE" --until "$UNTIL"
EXTRA=(FAKE_FAIL=gw_latency.report); fails_one "slow minute" "[FAIL] latency" "demo-check post: 4/5 passed" post --since "$SINCE" --until "$UNTIL"
EXTRA=(FAKE_AWS_FAIL="logs filter-log-events"); fails_one "filter-log-events error" "[FAIL] audit" "demo-check post: 4/5 passed" \
  post --since "$SINCE" --until "$UNTIL"
EXTRA=()

# --- bad arguments: usage on stderr, exit 2, nothing runs ---------------------------------------------
bad() { # NAME ARGS...
  local name="$1"; shift
  run_check "$@"
  check "bad arguments ($name): exit 2, usage on stderr, no call" "2|yes||" "$RC|$(has "$ERR" "usage:")|$LOG|$OUT"
}
S=1790000000000
bad "none"; bad "unknown mode" bogus; bad "pre with an argument" pre --since "$S"
bad "post without a window" post; bad "post without --until" post --since "$S"
bad "post without --since" post --until "$S"; bad "--until without a value" post --since "$S" --until
bad "non-numeric --since" post --since abc --until "$S"; bad "seconds, not ms" post --since 1790000000 --until 1790000060
bad "since = until" post --since "$S" --until "$S"; bad "since > until" post --since $((S + 60000)) --until "$S"
bad "unknown option" post --since "$S" --until $((S + 60000)) --verbose
EXTRA=(MAX_CONNS=eighty); bad "MAX_CONNS not a number" pre; EXTRA=()

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
```

`test-check-secrets.sh` 的补丁（假的 `aws` 按 secret 分别给出结果：可读、排期删除、不存在、没有权限、token 过期；`sts` 返回 `FAKE_STS` 的账号，空串表示过期。原来「读不到」那一组改用过期的 token：「不存在」在 `state.env` 的账号里现在是跳过）：

<!-- file: t55-tests.diff sha256=b492dff2add047df7268f311817ff4071ce0021960ae6bc62657d4b36b821b98 -->
```diff
diff --git a/scripts/test/test-check-secrets.sh b/scripts/test/test-check-secrets.sh
index 98cd9c3..5b3c930 100644
--- a/scripts/test/test-check-secrets.sh
+++ b/scripts/test/test-check-secrets.sh
@@ -9,16 +9,31 @@ TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
 FAKE_PW="SmPw0123456789abcdefXYZ"
 FAKE_PW2="CgPw0123456789abcdefXYZ"
 mkdir -p "$TMP/bin" "$TMP/repo/scripts"
+# FAKE_SM / FAKE_SM2: what get-secret-value does for doris-mcp/mcp_svc / doris-mcp/cognito-demo-user
+# (readable, scheduled = marked for deletion, gone = not found, denied, anything else = expired token);
+# FAKE_STS: the account sts get-caller-identity returns (empty: the token is expired).
 cat > "$TMP/bin/aws" <<'FAKE'
 #!/usr/bin/env bash
 printf '%s\n' "$*" >> "$FAKE_LOG"
-if [[ "$1 $2" == "secretsmanager get-secret-value" && "$FAKE_SM" == "readable" ]]; then
-  case "$*" in
-    *doris-mcp/mcp_svc*) printf '{"username":"mcp_svc","password":"%s"}\n' "$FAKE_PW"; exit 0 ;;
-    *doris-mcp/cognito-demo-user*) printf '{"username":"demo","password":"%s"}\n' "$FAKE_PW2"; exit 0 ;;
-  esac
+err() { echo "An error occurred ($1) when calling the $2 operation: $3" >&2; exit 254; }
+if [[ "$1 $2" == "sts get-caller-identity" ]]; then
+  [[ -n "$FAKE_STS" ]] && { echo "$FAKE_STS"; exit 0; }
+  err ExpiredToken GetCallerIdentity "The security token included in the request is expired"
 fi
-echo "An error occurred (ResourceNotFoundException) when calling the GetSecretValue operation" >&2; exit 254
+[[ "$1 $2" == "secretsmanager get-secret-value" ]] || err InvalidAction "$1 $2" "not faked"
+case "$*" in
+  *doris-mcp/mcp_svc*) mode="$FAKE_SM" user=mcp_svc pw="$FAKE_PW" ;;
+  *doris-mcp/cognito-demo-user*) mode="$FAKE_SM2" user=demo pw="$FAKE_PW2" ;;
+  *) mode=gone ;;
+esac
+case "$mode" in
+  readable) printf '{"username":"%s","password":"%s"}\n' "$user" "$pw"; exit 0 ;;
+  scheduled) err InvalidRequestException GetSecretValue \
+               "You can't perform this operation on the secret because it was marked for deletion." ;;
+  gone) err ResourceNotFoundException GetSecretValue "Secrets Manager can't find the specified secret." ;;
+  denied) err AccessDeniedException GetSecretValue "User is not authorized to perform: secretsmanager:GetSecretValue" ;;
+  *) err ExpiredTokenException GetSecretValue "The security token included in the request is expired" ;;
+esac
 FAKE
 chmod +x "$TMP/bin/aws"
 cp "$SRC" "$TMP/repo/scripts/check-secrets.sh"
@@ -29,10 +44,11 @@ FAILS=0
 check() { # NAME EXPECTED ACTUAL
   if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
 }
-run_check() { # FAKE_SM → sets RC, OUT
+run_check() { # FAKE_SM [FAKE_SM2 (default: FAKE_SM)] [FAKE_STS] → sets RC, OUT
   : > "$TMP/aws.log"
   # AWS_REGION points elsewhere, like a shell whose default profile is in another region.
-  OUT="$(cd "$TMP/repo" && PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" FAKE_PW="$FAKE_PW" FAKE_PW2="$FAKE_PW2" FAKE_SM="$1" \
+  OUT="$(cd "$TMP/repo" && PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" FAKE_PW="$FAKE_PW" FAKE_PW2="$FAKE_PW2" \
+    FAKE_SM="$1" FAKE_SM2="${2:-$1}" FAKE_STS="${3:-}" \
     AWS_REGION=eu-west-1 AWS_DEFAULT_REGION=eu-west-1 CRED_FILE="$TMP/no-such-file" bash scripts/check-secrets.sh 2>&1)"
   RC=$?
 }
@@ -76,10 +92,51 @@ check "a quoted $KEY without spaces fails the check" 1 "$RC"
 rm "$TMP/repo/be.conf.md"
 
 # An exact-value check that could not run is not a pass (P2 whole review M4).
-run_check unreadable
+run_check expired
 check "unreadable secrets fail the check" 1 "$RC"
 check "the failure names the secret" yes "$(has "$OUT" "FAIL: cannot read secret doris-mcp/mcp_svc")"
 check "the last line says FAILED" "check-secrets: FAILED — do not commit" "$(tail -n 1 <<<"$OUT")"
 
+# A secret that infra/99-cleanup.sh deleted has nothing left to compare: skipped, not failed (P5 Task 9).
+# "Not found" alone proves nothing (another account's credentials get it for every secret), so it counts
+# only when the caller is the account in infra/state.env.
+PROJECT_ACCOUNT=111122223333
+mkdir -p "$TMP/repo/infra"; printf 'AWS_REGION=us-east-1\nACCOUNT_ID=%s\n' "$PROJECT_ACCOUNT" > "$TMP/repo/infra/state.env"
+run_check scheduled
+check "secrets marked for deletion are skipped" 0 "$RC"
+check "the skip names the secret" yes "$(has "$OUT" "SKIP: secret doris-mcp/mcp_svc is scheduled for deletion")"
+check "the OK line counts the skipped secrets" yes "$(has "$(tail -n 1 <<<"$OUT")" "2 deleted secrets skipped")"
+run_check gone gone "$PROJECT_ACCOUNT"
+check "secrets not found in the project's account are skipped" "0|yes" \
+  "$RC|$(has "$OUT" "SKIP: secret doris-mcp/cognito-demo-user no longer exists in the project's account")"
+check "asks sts in us-east-1" yes "$(has "$(grep '^sts ' "$TMP/aws.log")" "--region us-east-1")"
+run_check gone gone 444455556666
+check "not found in another account fails the check" "1|yes" "$RC|$(has "$OUT" "FAIL: cannot read secret doris-mcp/mcp_svc")"
+check "never prints the caller's account" no "$(has "$OUT" 444455556666)"
+run_check gone gone ""
+check "not found with an expired sts token fails the check" 1 "$RC"
+run_check denied denied "$PROJECT_ACCOUNT"
+check "access denied in the project's account fails the check" 1 "$RC"
+run_check expired expired "$PROJECT_ACCOUNT"
+check "an expired token fails the check even when sts answers" 1 "$RC"
+rm "$TMP/repo/infra/state.env"
+run_check gone gone ""
+check "not found without infra/state.env fails the check (no account to compare)" 1 "$RC"
+run_check gone gone "$PROJECT_ACCOUNT"
+check "not found without infra/state.env fails even when sts answers" 1 "$RC"
+printf 'AWS_REGION=us-east-1\nACCOUNT_ID=%s\n' "$PROJECT_ACCOUNT" > "$TMP/repo/infra/state.env"
+
+printf 'demo login: %s\n' "$FAKE_PW2" > "$TMP/repo/leaky.log.txt"
+run_check scheduled readable
+check "a skipped secret does not hide a leak of the other one" "1|yes|yes" \
+  "$RC|$(has "$OUT" "SKIP: secret doris-mcp/mcp_svc")|$(has "$OUT" "LEAK: password of secret doris-mcp/cognito-demo-user found in leaky.log.txt")"
+rm "$TMP/repo/leaky.log.txt"
+run_check scheduled expired
+check "an error after a skipped secret still fails the check" "1|yes" "$RC|$(has "$OUT" "FAIL: cannot read secret doris-mcp/cognito-demo-user")"
+run_check readable scheduled
+check "one readable and one skipped secret pass" "0|yes" "$RC|$(has "$(tail -n 1 <<<"$OUT")" "1 deleted secrets skipped")"
+run_check readable
+check "the OK line mentions no skips when every secret was read" no "$(has "$(tail -n 1 <<<"$OUT")" "skipped")"
+
 if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
 echo "all passed"
```

- [ ] **Step 2：确认失败**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
for t in infra/test/test-30-gateway.sh infra/test/test-99-cleanup.sh scripts/test/test-demo-check.sh scripts/test/test-check-secrets.sh; do
  log=/tmp/t55-red-$(basename "$t" .sh).log
  bash "$t" > "$log" 2>&1; echo "$t: rc=$? ok=$(grep -c '^ok' "$log") FAIL=$(grep -c '^FAIL' "$log")"
  tail -1 "$log"
done
```
期望（实测）：
```
infra/test/test-30-gateway.sh: rc=1 ok=11 FAIL=19
19 failed
infra/test/test-99-cleanup.sh: rc=1 ok=21 FAIL=60
60 failed
scripts/test/test-demo-check.sh: rc=1 ok=18 FAIL=78
78 failed
scripts/test/test-check-secrets.sh: rc=1 ok=29 FAIL=7
7 failed
```
失败的正是 Step 3 要做的：
- `test-30-gateway.sh` 19 个 `FAIL`：`update-gateway` 没有带 description；还没有 `GW_EXCEPTION_LEVEL` 开关（`""` 仍然传 `--exception-level`，`INFO`、`debug`、` DEBUG` 这些值没有被拒绝）。通过的 11 个是 create 路径和 dry-run 里原来就对的部分。
- `test-99-cleanup.sh` 60 个、`test-demo-check.sh` 78 个 `FAIL`：两个脚本还不存在（exit 127，`No such file or directory`）。通过的 21 个、18 个是「不调用」「不写」「不打印」这类检查，脚本不存在时自然成立，Step 3 之后才有意义（突变 cl、dc 证明它们有效）。
- `test-check-secrets.sh` 7 个 `FAIL`：还不会跳过 Task 9 删掉的 secret。新加的 16 个里另外 9 个（过期、没有权限、别的账号、没有 `state.env` 仍然失败等）和原来的 20 个在旧脚本上已经通过。

失败的个数不同时，先查明原因，不要进入 Step 3。

- [ ] **Step 3：实现**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py t5x-impl.diff /tmp/t5x-impl.diff
git apply /tmp/t5x-impl.diff && git diff --shortstat
.venv/bin/python /tmp/p5-extract.py infra/99-cleanup.sh
.venv/bin/python /tmp/p5-extract.py scripts/demo-check.sh
git status --short
```
期望（实测）：
```
t5x-impl.diff -> /tmp/t5x-impl.diff (107 lines)
 3 files changed, 107 insertions(+), 22 deletions(-)
infra/99-cleanup.sh -> infra/99-cleanup.sh (229 lines)
scripts/demo-check.sh -> scripts/demo-check.sh (169 lines)
 M infra/30-gateway.sh
 M scripts/check-secrets.sh
 M scripts/test/test-check-secrets.sh
?? infra/99-cleanup.sh
?? infra/test/test-30-gateway.sh
?? infra/test/test-99-cleanup.sh
?? scripts/demo-check.sh
?? scripts/test/test-demo-check.sh
```

`infra/30-gateway.sh` 和 `scripts/check-secrets.sh` 的补丁：

<!-- file: t5x-impl.diff sha256=cd60488cd8765783cce7161984ee282ea37c2202c21e07e766d9dd911c2cd279 -->
```diff
diff --git a/infra/30-gateway.sh b/infra/30-gateway.sh
index d866ff9..9f9b984 100644
--- a/infra/30-gateway.sh
+++ b/infra/30-gateway.sh
@@ -5,7 +5,11 @@
 #   * Gateway doris-mcp-gw: MCP, CUSTOM_JWT (Cognito discovery URL, clients A+B, scope doris-mcp/invoke)
 #   * Target doris: mcpServer endpoint = Runtime invoke URL, outbound GATEWAY_IAM_ROLE SigV4
 # Env knobs:  GW_ALLOWED_SCOPES="doris-mcp/invoke" (set to "" to drop the scope check)
+#             GW_EXCEPTION_LEVEL=DEBUG (default: the MCP client sees the detailed error messages;
+#               set to "" for generic ones; any other value is refused)
 #             SYNC=1  → synchronize-gateway-targets (after the Runtime's tools changed)
+# update-gateway replaces the whole Gateway config (omitted options are cleared), so create and update
+# share one argument list, description included: re-running with the default keeps DEBUG.
 # Dry-run by default. APPLY=1 to execute. Safe to re-run (re-applies role policy + authorizer).
 source "$(dirname "$0")/lib.sh"
 
@@ -13,6 +17,12 @@ ROLE_NAME=doris-mcp-gateway-role
 GW_NAME=doris-mcp-gw
 TARGET_NAME=doris
 GW_ALLOWED_SCOPES="${GW_ALLOWED_SCOPES-doris-mcp/invoke}"
+GW_EXCEPTION_LEVEL="${GW_EXCEPTION_LEVEL-DEBUG}"
+case "$GW_EXCEPTION_LEVEL" in
+  DEBUG) GW_EXCEPTION_ARGS=(--exception-level DEBUG) ;;
+  "")    GW_EXCEPTION_ARGS=() ;;
+  *)     log "FATAL: GW_EXCEPTION_LEVEL must be DEBUG or empty, not '$GW_EXCEPTION_LEVEL'"; exit 1 ;;
+esac
 
 if [[ "$APPLY" == "1" ]]; then
   : "${RUNTIME_ARN:?RUNTIME_ARN missing in state.env - finish T0.4 first}"
@@ -61,17 +71,17 @@ print(json.dumps({"customJWTAuthorizer": cfg}))
 PY
 )"
 GW_COMMON=(--name "$GW_NAME" --role-arn "$GW_ROLE_ARN" --protocol-type MCP
-  --authorizer-type CUSTOM_JWT --authorizer-configuration "$AUTHZ" --exception-level DEBUG)
+  --authorizer-type CUSTOM_JWT --authorizer-configuration "$AUTHZ" "${GW_EXCEPTION_ARGS[@]}"
+  --description "Quick desktop -> Doris MCP (Runtime dorismcp)")
 
 GW_ID="$(none_to_empty "$(aws bedrock-agentcore-control list-gateways \
   --query "items[?name=='$GW_NAME'].gatewayId | [0]" --output text)")"
 if [[ -z "$GW_ID" ]]; then
-  GW_ID="$(run aws bedrock-agentcore-control create-gateway "${GW_COMMON[@]}" \
-    --description "Quick desktop -> Doris MCP (Runtime dorismcp)" --tags "Project=$PROJECT_TAG" \
+  GW_ID="$(run aws bedrock-agentcore-control create-gateway "${GW_COMMON[@]}" --tags "Project=$PROJECT_TAG" \
     --query gatewayId --output text)"
   GW_ID="${GW_ID:-$(placeholder gateway-id)}"
 else
-  log "gateway exists: $GW_ID (re-applying authorizer, scopes='$GW_ALLOWED_SCOPES')"
+  log "gateway exists: $GW_ID (re-applying authorizer, scopes='$GW_ALLOWED_SCOPES', exception level='$GW_EXCEPTION_LEVEL')"
   run aws bedrock-agentcore-control update-gateway --gateway-identifier "$GW_ID" "${GW_COMMON[@]}" \
     --query status --output text >/dev/null
 fi
diff --git a/scripts/check-secrets.sh b/scripts/check-secrets.sh
index 750c94e..d0efcbe 100644
--- a/scripts/check-secrets.sh
+++ b/scripts/check-secrets.sh
@@ -36,19 +36,33 @@ fi
 
 # 1b) Passwords held only in Secrets Manager (created by infra/*.sh, always in us-east-1). The value
 #     stays in a shell variable and reaches grep through a process substitution — never argv, never printed.
+#     A secret that infra/99-cleanup.sh deleted has nothing left to compare and is skipped: Secrets Manager
+#     says it is marked for deletion (the recovery window), or not found while the caller is the account in
+#     infra/state.env (with another account's credentials every secret is "not found"). Any other error fails.
+SM_REGION="${SM_REGION:-us-east-1}"
+project_account="$(sed -n 's/^ACCOUNT_ID=\([0-9]\{12\}\)$/\1/p' infra/state.env 2>/dev/null || true)"
+sm_err="$(mktemp)"; trap 'rm -f "$sm_err"' EXIT
+skipped=0
 for sid in ${SM_SECRETS:-doris-mcp/mcp_svc doris-mcp/cognito-demo-user}; do
-  if ! pw="$(aws secretsmanager get-secret-value --region "${SM_REGION:-us-east-1}" --secret-id "$sid" \
-               --query SecretString --output text 2>/dev/null |
-             python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])' 2>/dev/null)" || [[ ${#pw} -lt 4 ]]; then
+  if pw="$(aws secretsmanager get-secret-value --region "$SM_REGION" --secret-id "$sid" \
+             --query SecretString --output text 2>"$sm_err" |
+           python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])' 2>/dev/null)" && [[ ${#pw} -ge 4 ]]; then
+    while IFS= read -r f; do
+      echo "LEAK: password of secret $sid found in $f"
+      fail=1
+    done < <(grep -lIF -f <(printf '%s\n' "$pw") -- "${files[@]}" 2>/dev/null)
+  elif grep -q 'marked for deletion' "$sm_err"; then
+    echo "SKIP: secret $sid is scheduled for deletion (infra/99-cleanup.sh) — nothing left to compare"
+    skipped=$((skipped + 1))
+  elif grep -q '(ResourceNotFoundException)' "$sm_err" && [[ -n "$project_account" ]] &&
+       [[ "$(aws sts get-caller-identity --region "$SM_REGION" --query Account --output text 2>/dev/null)" == "$project_account" ]]; then
+    echo "SKIP: secret $sid no longer exists in the project's account (deleted) — nothing left to compare"
+    skipped=$((skipped + 1))
+  else
     # A check that could not run is not a pass: fix the AWS credentials, then re-run.
     echo "FAIL: cannot read secret $sid — its exact-value check did not run"
     fail=1
-    continue
   fi
-  while IFS= read -r f; do
-    echo "LEAK: password of secret $sid found in $f"
-    fail=1
-  done < <(grep -lIF -f <(printf '%s\n' "$pw") -- "${files[@]}" 2>/dev/null)
 done
 unset pw
 
@@ -67,4 +81,8 @@ if [[ $fail -ne 0 ]]; then
   echo "check-secrets: FAILED — do not commit"
   exit 1
 fi
-echo "check-secrets: OK (${#files[@]} files scanned)"
+if [[ $skipped -gt 0 ]]; then
+  echo "check-secrets: OK (${#files[@]} files scanned, $skipped deleted secrets skipped)"
+else
+  echo "check-secrets: OK (${#files[@]} files scanned)"
+fi
```

新文件 `infra/99-cleanup.sh`：

<!-- file: infra/99-cleanup.sh sha256=a54d6533fae30581d29bda26514f64399732d9065dfde2db60d782a5de24d225 -->
```bash
#!/usr/bin/env bash
# P5 / T5.6 — Tear down the demo's AWS resources after the demo. Deletes only what state.env records, in
# dependency order (each step removes what blocks the next one):
#   1. Gateway target, then (once the target is gone) the Gateway doris-mcp-gw
#   2. CloudFormation stack AgentCore-dorismcp-default (the Runtime), waiting for stack-delete-complete
#   3. VPC endpoints S3 / logs / secretsmanager, waiting until they are gone (their ENIs use doris-mcp-vpce)
#   4. Cognito hosted UI domain (a pool with a domain cannot be deleted), then the user pool
#   5. secrets doris-mcp/cognito-demo-user and doris-mcp/mcp_svc (recovery window, see the knobs)
#   6. doris-demo-sg: only its ingress rules that reference doris-mcp-rt; its other rules are never touched
#   7. waits until no network interface uses doris-mcp-rt / doris-mcp-vpce (the Runtime's ENIs are released
#      asynchronously, minutes after the stack), revokes their cross-references, deletes both SGs
#   8. IAM roles doris-mcp-gateway-role and doris-mcp-runtime-role (inline policies first)
# Every check runs before the first delete: the caller's account must be ACCOUNT_ID, every resource must carry
# Project=doris-mcp-demo (the stack: agentcore:project-name=dorismcp), the Gateway must be named doris-mcp-gw;
# any mismatch or unexpected error -> FATAL, nothing deleted. A resource already gone is logged and skipped,
# so a partial run can simply be re-run.
# Not touched: state.env (kept as the record), log groups, the X-Ray/transaction search setting, other projects.
# Doris side (DROP USER mcp_svc, DROP DATABASE system_mcp) is a separate step.
# Env knobs:  STACK_NAME=AgentCore-dorismcp-default
#             SECRET_RECOVERY_DAYS=7 (7-30)   FORCE_DELETE_SECRETS=1 → delete the secrets without recovery
# Dry-run by default. APPLY=1 to execute.
source "$(dirname "$0")/lib.sh"

STACK_NAME="${STACK_NAME:-AgentCore-dorismcp-default}"
SECRET_RECOVERY_DAYS="${SECRET_RECOVERY_DAYS:-7}"
FORCE_DELETE_SECRETS="${FORCE_DELETE_SECRETS:-0}"
GW_NAME=doris-mcp-gw
SECRETS=(doris-mcp/cognito-demo-user doris-mcp/mcp_svc)
ROLES=(doris-mcp-gateway-role doris-mcp-runtime-role)

DONE=() # what step 2 deleted (or would delete), for the summary
fatal() { log "FATAL: $* (${#DONE[@]} deleted so far)"; exit 1; }

[[ "$SECRET_RECOVERY_DAYS" =~ ^([7-9]|[12][0-9]|30)$ ]] || fatal "SECRET_RECOVERY_DAYS must be 7-30"
case "$FORCE_DELETE_SECRETS" in
  1) SECRET_ARGS=(--force-delete-without-recovery) ;;
  0) SECRET_ARGS=(--recovery-window-in-days "$SECRET_RECOVERY_DAYS") ;;
  *) fatal "FORCE_DELETE_SECRETS must be 0 or 1" ;;
esac
for key in ACCOUNT_ID GW_ID GW_TARGET_ID VPCE_S3 VPCE_LOGS VPCE_SECRETSMANAGER COGNITO_POOL_ID COGNITO_DOMAIN \
           DORIS_SG RT_SG VPCE_SG; do
  [[ -n "${!key:-}" ]] && ! is_placeholder "${!key}" || fatal "$key missing in $STATE_FILE"
done
DOMAIN_PREFIX="${COGNITO_DOMAIN%%.*}" # state has the full host <prefix>.auth.<region>.amazoncognito.com

# probe NOT_FOUND CMD... — a read; sets OUT ("None" -> ""). Returns 1 when the error output contains
# NOT_FOUND (the resource is gone); any other failure (access denied, expired session, ...) is FATAL, so it
# can never pass for "already deleted". fetch CMD... — a read that must succeed.
private_tmp; ERR_FILE="$PRIVATE_TMP"
probe() {
  local not_found="$1"; shift
  if OUT="$("$@" 2>"$ERR_FILE")"; then OUT="$(none_to_empty "$OUT")"; return 0; fi
  if [[ -n "$not_found" ]] && grep -q -- "$not_found" "$ERR_FILE"; then OUT=""; return 1; fi
  fatal "$1 $2 $3 failed: $(cat "$ERR_FILE")"
}
fetch() { probe "" "$@"; }
gone() { log "$1 already deleted"; }
require_tag() { # WHAT VALUE — VALUE is the resource's Project tag
  [[ "$2" == "$PROJECT_TAG" ]] || fatal "$1 is not tagged Project=$PROJECT_TAG (found '$(none_to_empty "$2")')"
}
# wait_gone TRIES SECONDS MESSAGE CHECK... — APPLY=1 only: polls CHECK until it succeeds, TRIES times at most,
# SECONDS apart; FATAL with MESSAGE when it never does.
wait_gone() {
  local tries="$1" secs="$2" message="$3" i; shift 3
  [[ "$APPLY" == "1" ]] || return 0
  for ((i = 1; i <= tries; i++)); do
    "$@" && return 0
    (( i == tries )) || sleep "$secs"
  done
  fatal "$message"
}

# --- 1. checks (read-only) --------------------------------------------------
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$ACCOUNT_ID" ]] \
  || fatal "the caller's account is not ACCOUNT_ID of $STATE_FILE"

DEL_GW=0 DEL_TARGET=0
if probe ResourceNotFoundException aws bedrock-agentcore-control get-gateway --gateway-identifier "$GW_ID" \
     --query '[name, gatewayArn]' --output text; then
  read -r name arn <<<"$OUT"
  [[ "$name" == "$GW_NAME" ]] || fatal "Gateway $GW_ID is named '$name', not $GW_NAME"
  fetch aws bedrock-agentcore-control list-tags-for-resource --resource-arn "$arn" --query tags.Project --output text
  require_tag "Gateway $GW_ID" "$OUT"; DEL_GW=1
  if probe ResourceNotFoundException aws bedrock-agentcore-control get-gateway-target --gateway-identifier "$GW_ID" \
       --target-id "$GW_TARGET_ID" --query status --output text; then DEL_TARGET=1; else gone "Gateway target $GW_TARGET_ID"; fi
else
  gone "Gateway $GW_ID"
fi

DEL_STACK=0
if probe 'does not exist' aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
     --query "Stacks[0].Tags[?Key=='agentcore:project-name'].Value | [0]" --output text; then
  [[ "$OUT" == dorismcp ]] || fatal "stack $STACK_NAME is not tagged agentcore:project-name=dorismcp"
  DEL_STACK=1
else
  gone "stack $STACK_NAME"
fi

VPCES=()
for id in "$VPCE_S3" "$VPCE_LOGS" "$VPCE_SECRETSMANAGER"; do
  fetch aws ec2 describe-vpc-endpoints --filters "Name=vpc-endpoint-id,Values=$id" \
    --query "VpcEndpoints[?State!='deleted'] | [0].[VpcEndpointId, Tags[?Key=='Project'].Value | [0]]" --output text
  if [[ -z "$OUT" ]]; then gone "VPC endpoint $id"; continue; fi
  read -r _ tag <<<"$OUT"; require_tag "VPC endpoint $id" "$tag"; VPCES+=("$id")
done

DEL_POOL=0 DEL_DOMAIN=0
if probe ResourceNotFoundException aws cognito-idp describe-user-pool --user-pool-id "$COGNITO_POOL_ID" \
     --query UserPool.UserPoolTags.Project --output text; then
  require_tag "user pool $COGNITO_POOL_ID" "$OUT"; DEL_POOL=1
else
  gone "user pool $COGNITO_POOL_ID"
fi
fetch aws cognito-idp describe-user-pool-domain --domain "$DOMAIN_PREFIX" --query DomainDescription.UserPoolId --output text
case "$OUT" in
  "") gone "Cognito domain $DOMAIN_PREFIX" ;;
  "$COGNITO_POOL_ID") DEL_DOMAIN=1 ;;
  *) fatal "Cognito domain $DOMAIN_PREFIX belongs to another user pool" ;;
esac

DEL_SECRETS=()
for s in "${SECRETS[@]}"; do
  if ! probe ResourceNotFoundException aws secretsmanager describe-secret --secret-id "$s" \
       --query "[DeletedDate, Tags[?Key=='Project'].Value | [0]]" --output text; then gone "secret $s"; continue; fi
  read -r deleted tag <<<"$OUT"
  if [[ "$deleted" != None ]]; then log "secret $s already scheduled for deletion"; continue; fi
  require_tag "secret $s" "$tag"; DEL_SECRETS+=("$s")
done

# doris-demo-sg is not ours: only the ingress rules 10-network.sh added (referencing doris-mcp-rt, tagged).
fetch aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$DORIS_SG" \
  --query "SecurityGroupRules[?!IsEgress && ReferencedGroupInfo.GroupId=='$RT_SG'].[SecurityGroupRuleId, Tags[?Key=='Project'].Value | [0]]" \
  --output text
DORIS_RULES=()
while read -r rule tag; do
  [[ -n "$rule" ]] || continue
  require_tag "$DORIS_SG rule $rule" "$tag"; DORIS_RULES+=("$rule")
done <<<"$OUT"
(( ${#DORIS_RULES[@]} )) || gone "$DORIS_SG ingress from $RT_SG"

SGS=()
for sg in "$RT_SG" "$VPCE_SG"; do
  fetch aws ec2 describe-security-groups --filters "Name=group-id,Values=$sg" \
    --query "SecurityGroups[0].[GroupId, Tags[?Key=='Project'].Value | [0]]" --output text
  if [[ -z "$OUT" ]]; then gone "security group $sg"; continue; fi
  read -r _ tag <<<"$OUT"; require_tag "security group $sg" "$tag"; SGS+=("$sg")
done

DEL_ROLES=()
for role in "${ROLES[@]}"; do
  if ! probe NoSuchEntity aws iam list-role-tags --role-name "$role" --query "Tags[?Key=='Project'].Value | [0]" \
       --output text; then gone "IAM role $role"; continue; fi
  require_tag "IAM role $role" "$OUT"; DEL_ROLES+=("$role")
done
log "checks passed"

# --- 2. deletes, in dependency order ----------------------------------------
target_gone() {
  ! probe ResourceNotFoundException aws bedrock-agentcore-control get-gateway-target --gateway-identifier "$GW_ID" \
    --target-id "$GW_TARGET_ID" --query status --output text
}
vpces_gone() {
  fetch aws ec2 describe-vpc-endpoints --filters "Name=vpc-endpoint-id,Values=$(IFS=,; echo "${VPCES[*]}")" \
    --query "VpcEndpoints[?State!='deleted'].VpcEndpointId" --output text
  [[ -z "$OUT" ]]
}
enis_gone() {
  fetch aws ec2 describe-network-interfaces --filters "Name=group-id,Values=$RT_SG,$VPCE_SG" \
    --query 'length(NetworkInterfaces)' --output text
  [[ "$OUT" == 0 ]]
}
revoke_refs() { # ingress|egress GROUP PEER — revoke GROUP's rules in that direction that reference PEER
  local egress=false ids; [[ "$1" == egress ]] && egress=true
  fetch aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$2" \
    --query "SecurityGroupRules[?IsEgress==\`$egress\` && ReferencedGroupInfo.GroupId=='$3'].SecurityGroupRuleId" --output text
  read -ra ids <<<"$OUT"
  (( ${#ids[@]} )) || return 0
  run aws ec2 "revoke-security-group-$1" --group-id "$2" --security-group-rule-ids "${ids[@]}" >/dev/null
}

if (( DEL_TARGET )); then
  run aws bedrock-agentcore-control delete-gateway-target --gateway-identifier "$GW_ID" --target-id "$GW_TARGET_ID" >/dev/null
  wait_gone 30 5 "Gateway target $GW_TARGET_ID still exists after 150 s" target_gone
  DONE+=("Gateway target")
fi
if (( DEL_GW )); then
  run aws bedrock-agentcore-control delete-gateway --gateway-identifier "$GW_ID" >/dev/null; DONE+=("Gateway")
fi
if (( DEL_STACK )); then
  run aws cloudformation delete-stack --stack-name "$STACK_NAME"
  run aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" \
    || fatal "stack $STACK_NAME did not reach DELETE_COMPLETE (see its events in the CloudFormation console)"
  DONE+=("stack $STACK_NAME")
fi
if (( ${#VPCES[@]} )); then
  run aws ec2 delete-vpc-endpoints --vpc-endpoint-ids "${VPCES[@]}" >/dev/null
  wait_gone 30 10 "VPC endpoints ${VPCES[*]} still exist after 300 s" vpces_gone
  DONE+=("${#VPCES[@]} VPC endpoints")
fi
if (( DEL_DOMAIN )); then
  run aws cognito-idp delete-user-pool-domain --domain "$DOMAIN_PREFIX" --user-pool-id "$COGNITO_POOL_ID"
  DONE+=("Cognito domain")
fi
if (( DEL_POOL )); then
  run aws cognito-idp delete-user-pool --user-pool-id "$COGNITO_POOL_ID"; DONE+=("user pool")
fi
for s in "${DEL_SECRETS[@]}"; do
  run aws secretsmanager delete-secret --secret-id "$s" "${SECRET_ARGS[@]}" >/dev/null; DONE+=("secret $s")
done
if (( ${#DORIS_RULES[@]} )); then
  run aws ec2 revoke-security-group-ingress --group-id "$DORIS_SG" --security-group-rule-ids "${DORIS_RULES[@]}" >/dev/null
  DONE+=("${#DORIS_RULES[@]} $DORIS_SG rules")
fi
if (( ${#SGS[@]} )); then
  wait_gone 30 20 "network interfaces still use $RT_SG / $VPCE_SG after about 10 minutes. Runtime ENIs are released asynchronously; re-run later" enis_gone
  revoke_refs egress "$RT_SG" "$VPCE_SG"
  revoke_refs ingress "$VPCE_SG" "$RT_SG"
  for sg in "${SGS[@]}"; do run aws ec2 delete-security-group --group-id "$sg"; DONE+=("SG $sg"); done
fi
for role in "${DEL_ROLES[@]}"; do
  fetch aws iam list-role-policies --role-name "$role" --query PolicyNames --output text
  read -ra policies <<<"$OUT"
  for p in "${policies[@]}"; do run aws iam delete-role-policy --role-name "$role" --policy-name "$p"; done
  run aws iam delete-role --role-name "$role"; DONE+=("role $role")
done

[[ "$APPLY" == "1" ]] && verb=deleted || verb="dry-run, APPLY=1 would delete"
printf -v list '%s, ' "${DONE[@]}"; list="${list%, }"
log "done ($verb: ${list:-nothing}). Kept: $STATE_FILE (the record), log groups, X-Ray settings. Doris side (DROP USER mcp_svc, DROP DATABASE system_mcp) is a separate step."
```

新文件 `scripts/demo-check.sh`：

<!-- file: scripts/demo-check.sh sha256=af8a54af1e4d15a5a71b435086e636c0cca1266fedc3d71670b18305bf107962 -->
```bash
#!/usr/bin/env bash
# P5 — Checks before and after each rehearsal / the demo. Read-only: AWS reads, MCP calls through the Gateway
# (tools/list, a fixed read-only flow, the connection count) and the Runtime (reconcile, permission matrix).
#   bash scripts/demo-check.sh pre                          # before: is everything up and consistent?
#   bash scripts/demo-check.sh post --since MS --until MS   # after: audit records and latency of that window
# MS = epoch milliseconds (e.g. `date +%s%3N` when the rehearsal starts and ends).
# pre:  account (== ACCOUNT_ID), Gateway READY, target READY, token, tools/list = 12 tools, the doris___ flow,
#       reconcile (read-only Doris account, over the Runtime), permission matrix, connections (host prefix
#       172.31., idle <= 610 s) and their count <= MAX_CONNS (mcp_svc has max_user_connections=100).
# post: audit (every doris_new_mcp.audit record of the window, audit_check --failures), latency (the window
#       widened to whole minutes: --since down, --until up; gw_latency report), token, connections as in pre.
# Each check prints [PASS] / [FAIL] NAME and its output indented; every child's stdout+stderr goes through MASK
# (IPv4 addresses -> <ip>, https URLs -> <url>). Last line: `demo-check MODE: N/M passed`.
# The Gateway token is never exported, never on a command line, never printed: it reaches mcp_smoke.py only,
# through its environment (--bearer-env GW_TOKEN). DORIS_* and GW_TOKEN from the caller are dropped. Only
# reconcile sees Doris credentials: DORIS_HOST / DORIS_PORT / DORIS_USER / DORIS_PASSWORD, set from the read-only
# account of CREDENTIALS_FILE in a subshell (DORIS_ROOT_* never reach any child).
# Env knobs: STATE_FILE=infra/state.env   PYTHON=.venv/bin/python (of the repo)   MAX_CONNS=80
#            CREDENTIALS_FILE=/home/ubuntu/AI-code/Doris-test/credentials.env
#            TOKEN_CMD="bash scripts/get-gw-token.sh" (split on whitespace, no quoting; the default reads the
#            repo's infra/state.env, whatever STATE_FILE says)
# Exit code: 0 when every check passes, 1 when one fails, 2 on bad arguments or an incomplete state file.
set -uo pipefail

MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() { # [REASON]
  [[ -z "${1-}" ]] || echo "demo-check: $1" >&2
  echo "usage: $0 pre | post --since MS --until MS   (MS: epoch milliseconds)" >&2
  exit 2
}

MODE="${1-}"; (( $# )) && shift
case "$MODE" in
  pre) (( $# == 0 )) || usage "pre takes no arguments" ;;
  post)
    SINCE="" UNTIL=""
    while (( $# )); do
      case "$1" in
        --since) (( $# >= 2 )) || usage "--since needs a value"; SINCE="$2"; shift 2 ;;
        --until) (( $# >= 2 )) || usage "--until needs a value"; UNTIL="$2"; shift 2 ;;
        *) usage "unknown argument '$1'" ;;
      esac
    done
    [[ "$SINCE" =~ ^[1-9][0-9]{12}$ && "$UNTIL" =~ ^[1-9][0-9]{12}$ ]] \
      || usage "--since and --until are required, in epoch milliseconds (13 digits)"
    (( SINCE < UNTIL )) || usage "--since must be before --until" ;;
  *) usage ;;
esac

STATE_FILE="${STATE_FILE:-$ROOT/infra/state.env}"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-/home/ubuntu/AI-code/Doris-test/credentials.env}"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
TOKEN_CMD="${TOKEN_CMD:-bash scripts/get-gw-token.sh}"
MAX_CONNS="${MAX_CONNS:-80}"
[[ "$MAX_CONNS" =~ ^(0|[1-9][0-9]*)$ ]] || usage "MAX_CONNS must be a number"
for v in STATE_FILE CREDENTIALS_FILE; do [[ "${!v}" == /* ]] || printf -v "$v" '%s/%s' "$PWD" "${!v}"; done

# shellcheck source=/dev/null
source "$STATE_FILE" || { echo "demo-check: cannot read $STATE_FILE" >&2; exit 2; }
unset GW_TOKEN "${!DORIS_@}" # the caller's and the state file's (DORIS_SG, ...): no child may inherit them
export AWS_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER=""
NEEDED=(ACCOUNT_ID GW_ID GW_URL)
[[ "$MODE" == pre ]] && NEEDED+=(GW_TARGET_ID RUNTIME_URL) || NEEDED+=(RUNTIME_ID)
for key in "${NEEDED[@]}"; do
  [[ -n "${!key:-}" ]] || { echo "demo-check: $key missing in $STATE_FILE" >&2; exit 2; }
done
cd "$ROOT" || exit 2

GW_TOKEN="" TMPFILES=()
trap 'unset GW_TOKEN; rm -f "${TMPFILES[@]}"' EXIT

PASSED=0 TOTAL=0
report() { # NAME RC OUTPUT — the verdict line, then the (already masked) output indented
  TOTAL=$((TOTAL + 1))
  if [[ "$2" == 0 ]]; then PASSED=$((PASSED + 1)); echo "[PASS] $1"; else echo "[FAIL] $1"; fi
  [[ -z "$3" ]] || sed 's/^/    /' <<<"$3"
}
check() { # NAME CMD... — passes when CMD exits 0; sets OUT to its masked stdout+stderr
  local name="$1" rc; shift
  OUT="$("$@" 2>&1 | sed -E "$MASK"; exit "${PIPESTATUS[0]}")"; rc=$?
  report "$name" "$rc" "$OUT"
}

account_ok() {
  local account
  account="$(aws sts get-caller-identity --region "$AWS_REGION" --query Account --output text)" || return 1
  if [[ "$account" == "$ACCOUNT_ID" ]]; then echo "the caller's account is ACCOUNT_ID"; return 0; fi
  echo "the caller's account is not ACCOUNT_ID of $STATE_FILE"; return 1
}
ready() { # CMD... — prints the status it returns; passes on READY
  local status
  status="$("$@")" || return 1
  echo "status: $status"
  [[ "$status" == READY ]]
}
get_token() { # sets GW_TOKEN (not exported); its stderr is masked, its stdout never printed
  local err rc argv
  err="$(mktemp)"; TMPFILES+=("$err")
  read -ra argv <<<"$TOKEN_CMD"
  GW_TOKEN="$("${argv[@]}" 2>"$err")"; rc=$?
  if (( rc == 0 )) && [[ -z "$GW_TOKEN" ]]; then echo "the token command printed nothing" >>"$err"; rc=1; fi
  (( rc == 0 )) || GW_TOKEN=""
  report token "$rc" "$(sed -E "$MASK" "$err")"
}
smoke() { # SUBCOMMAND ARGS... — mcp_smoke.py through the Gateway; the token only in its environment
  [[ -n "$GW_TOKEN" ]] || { echo "skipped: no Gateway token"; return 1; }
  GW_TOKEN="$GW_TOKEN" "$PYTHON" scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN --timeout 60 "$@"
}
reconcile() { # the read-only Doris account only; no GW_TOKEN, no other DORIS_* variable
  ( source "$CREDENTIALS_FILE" || exit 1
    host="${DORIS_HOST-}" port="${DORIS_MYSQL_PORT:-9030}" user="${DORIS_RO_USER-}" password="${DORIS_RO_PASSWORD-}"
    unset GW_TOKEN "${!DORIS_@}" # whether or not the file exports them
    [[ -n "$user" && -n "$password" ]] || { echo "DORIS_RO_USER / DORIS_RO_PASSWORD missing in $CREDENTIALS_FILE"; exit 1; }
    export DORIS_HOST="$host" DORIS_PORT="$port" DORIS_USER="$user" DORIS_PASSWORD="$password" AWS_REGION
    exec "$PYTHON" doris/reconcile.py mcp --url "$RUNTIME_URL" )
}
conns_max() { # the `connections: N` count of the last conns check <= MAX_CONNS
  local n
  n="$(sed -nE 's/^connections: ([0-9]+).*/\1/p' <<<"$CONNS_OUT" | head -1)"
  [[ -n "$n" ]] || { echo "no 'connections: N' line in the conns output"; return 1; }
  echo "connections: $n, MAX_CONNS: $MAX_CONNS"
  (( n <= MAX_CONNS ))
}
conns() {
  check conns smoke conns --prefix doris___ --expect-host-prefix 172.31. --max-idle 610
  CONNS_OUT="$OUT"
  check "conns <= MAX_CONNS" conns_max
}
audit() {
  aws logs filter-log-events --region "$AWS_REGION" --log-group-name "/aws/bedrock-agentcore/runtimes/${RUNTIME_ID}-DEFAULT" \
      --start-time "$SINCE" --end-time "$UNTIL" --filter-pattern '"doris_new_mcp.audit"' --output json \
    | "$PYTHON" scripts/audit_check.py --failures
}
minute_floor() { date -u -d "@$(( $1 / 1000 / 60 * 60 ))" +%Y-%m-%dT%H:%M:%SZ; } # MS -> ISO-8601, its whole minute
minute_ceil() { date -u -d "@$(( ($1 / 1000 + 59) / 60 * 60 ))" +%Y-%m-%dT%H:%M:%SZ; } # MS -> ISO-8601, next whole minute
latency() {
  local from to q
  from="$(minute_floor "$SINCE")" && to="$(minute_ceil "$UNTIL")" || return 1 # a call in the first minute counts
  echo "window $from .. $to"
  q="$("$PYTHON" scripts/gw_latency.py queries --gateway-arn "arn:aws:bedrock-agentcore:${AWS_REGION}:${ACCOUNT_ID}:gateway/${GW_ID}")" \
    || return 1
  aws cloudwatch get-metric-data --region "$AWS_REGION" --start-time "$from" --end-time "$to" --metric-data-queries "$q" \
      --output json \
    | "$PYTHON" scripts/gw_latency.py report
}

if [[ "$MODE" == pre ]]; then
  check account account_ok
  check "gateway READY" ready aws bedrock-agentcore-control get-gateway --gateway-identifier "$GW_ID" \
    --region "$AWS_REGION" --query status --output text
  check "target READY" ready aws bedrock-agentcore-control get-gateway-target --gateway-identifier "$GW_ID" \
    --target-id "$GW_TARGET_ID" --region "$AWS_REGION" --query status --output text
  get_token
  check "list 12 tools" smoke list --expect 12
  check flow smoke flow --prefix doris___
  check reconcile reconcile
  check "permission matrix" "$PYTHON" doris/permission_matrix.py --url "$RUNTIME_URL" --expect-host '172.31.%'
  conns
else
  check audit audit
  check latency latency
  get_token
  conns
fi

echo "demo-check $MODE: $PASSED/$TOTAL passed"
(( PASSED == TOTAL ))
```

- [ ] **Step 4：确认通过；突变**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
for t in infra/test/test-30-gateway.sh infra/test/test-99-cleanup.sh scripts/test/test-demo-check.sh scripts/test/test-check-secrets.sh; do
  printf '%s: ' "$t"; out="$(bash "$t" 2>&1)"; printf '%s ok, %s\n' "$(grep -c '^ok' <<<"$out")" "$(tail -1 <<<"$out")"
done                                                                                                 # 期望：30、81、96、36 ok，all passed
for t in doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh infra/test/test-35-runtime-role.sh \
         infra/test/test-40-doris-secret.sh infra/test/test-lib.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 期望：每行 all passed
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 期望：Ran 137 tests … OK
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json gw; echo "rc=$?"
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json cl; echo "rc=$?"
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json dc; echo "rc=$?"
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json cs; echo "rc=$?"
```
期望（实测，秒数每次不同）：
```
infra/test/test-30-gateway.sh: 30 ok, all passed
infra/test/test-99-cleanup.sh: 81 ok, all passed
scripts/test/test-demo-check.sh: 96 ok, all passed
scripts/test/test-check-secrets.sh: 36 ok, all passed
doris/test/test-apply-admin-sql.sh: all passed
doris/test/test-publish-semantic.sh: all passed
infra/test/test-35-runtime-role.sh: all passed
infra/test/test-40-doris-secret.sh: all passed
infra/test/test-lib.sh: all passed
Ran 137 tests in 2.025s

OK
gw1 description back to create-only: caught by apply/GW_EXCEPTION_LEVEL empty, apply/GW_EXCEPTION_LEVEL=DEBUG, apply/SYNC=1, apply/exists, dry-run (6 failed)
gw2 flag always passed (empty knob ignored): caught by apply/GW_EXCEPTION_LEVEL empty, apply/missing/GW_EXCEPTION_LEVEL empty, dry-run/GW_EXCEPTION_LEVEL empty (4 failed)
gw3 bad value accepted: caught by apply/GW_EXCEPTION_LEVEL=' DEBUG', apply/GW_EXCEPTION_LEVEL='INFO', apply/GW_EXCEPTION_LEVEL='debug', dry-run/GW_EXCEPTION_LEVEL=ERROR (10 failed)
gw4 description twice on create: caught by apply/missing, apply/missing/GW_EXCEPTION_LEVEL empty (3 failed)
gw5 DEBUG dropped by default: caught by apply/GW_EXCEPTION_LEVEL=DEBUG, apply/SYNC=1, apply/exists, apply/missing, dry-run (7 failed)
gw6 empty knob cannot turn DEBUG off (:- instead of -): caught by apply/GW_EXCEPTION_LEVEL empty, apply/missing/GW_EXCEPTION_LEVEL empty, dry-run/GW_EXCEPTION_LEVEL empty (4 failed)
gw7 empty knob refused: caught by apply/GW_EXCEPTION_LEVEL empty, apply/missing/GW_EXCEPTION_LEVEL empty (3 failed)
gw8 update-gateway outside run (writes in dry-run): caught by dry-run (3 failed)
gw9 case-folded knob (the default DEBUG refused): caught by apply/GW_EXCEPTION_LEVEL=DEBUG, apply/SYNC=1, apply/exists, apply/missing, dry-run (12 failed)
gw10 state written in dry-run: caught by dry-run (1 failed)
gw11 always create-gateway: caught by apply/GW_EXCEPTION_LEVEL empty, apply/GW_EXCEPTION_LEVEL=DEBUG, apply/SYNC=1, apply/exists, dry-run (8 failed)
11/11 mutations caught; tree unchanged: True
rc=0
cl1 tag check skipped: caught by Gateway tagged for another project, Gateway without tags, IAM role without the tag, SG tagged otherwise, VPC endpoint without the tag, doris-demo-sg rule referencing RT_SG without the tag, secret without the tag, user pool tagged otherwise (24 failed)
cl2 account check skipped: caught by wrong account (4 failed)
cl3 doris-demo-sg rules selected by tag: caught by ENIs stay, apply, doris-demo-sg rule referencing RT_SG without the tag, dry-run (7 failed)
cl4 all doris-demo-sg ingress rules: caught by ENIs stay, FORCE_DELETE_SECRETS=0, FORCE_DELETE_SECRETS=1, SECRET_RECOVERY_DAYS=30, STACK_NAME override, apply, dry-run, re-run after a full teardown, re-run after the ENI timeout, target already gone (23 failed)
cl5 no ENI wait: caught by ENIs stay, STACK_NAME override, apply, re-run after a full teardown, re-run after the ENI timeout, target already gone (13 failed)
cl6 roles before the stack: caught by ENIs stay, apply, dry-run, re-run after the ENI timeout (5 failed)
cl7 SG step before the endpoints: caught by ENIs stay, FORCE_DELETE_SECRETS=1, STACK_NAME override, apply, dry-run, re-run after a full teardown, re-run after the ENI timeout, target already gone (16 failed)
cl8 force-delete by default: caught by ENIs stay, SECRET_RECOVERY_DAYS=30, apply, dry-run, re-run after the ENI timeout (5 failed)
cl9 full domain instead of the prefix: caught by Cognito domain of another pool, ENIs stay, FORCE_DELETE_SECRETS=1, STACK_NAME override, apply, dry-run, re-run after a full teardown, re-run after the ENI timeout, target already gone (21 failed)
cl10 any probe error taken for already deleted: caught by describe-secret denied (not the same as deleted), get-gateway denied (not the same as deleted), list-role-tags denied (not the same as deleted) (9 failed)
cl11 Gateway name check skipped: caught by Gateway named otherwise (3 failed)
cl12 no wait for the target: caught by ENIs stay, FORCE_DELETE_SECRETS=1, STACK_NAME override, apply, re-run after a full teardown, re-run after the ENI timeout (19 failed)
cl13 domain of another pool deleted: caught by Cognito domain of another pool (3 failed)
cl14 stack tag check skipped: caught by stack of another agentcore project (3 failed)
cl15 already-scheduled secret deleted again: caught by re-run after a full teardown, re-run after the ENI timeout (4 failed)
cl16 SECRET_RECOVERY_DAYS not range-checked: caught by SECRET_RECOVERY_DAYS=08, SECRET_RECOVERY_DAYS=3 (2 failed)
cl17 delete-gateway outside run (writes in dry-run): caught by FORCE_DELETE_SECRETS=0, SECRET_RECOVERY_DAYS=30, dry-run (5 failed)
cl18 waits (and sleeps) in dry-run: caught by FORCE_DELETE_SECRETS=0, SECRET_RECOVERY_DAYS=30, dry-run (5 failed)
cl19 state.env edited (GW_ lines dropped): caught by apply, dry-run (2 failed)
cl20 another Gateway deleted: caught by ENIs stay, apply, dry-run, re-run after a full teardown, re-run after the ENI timeout, target already gone (9 failed)
cl21 SG cross-references not revoked: caught by STACK_NAME override, apply, dry-run, re-run after a full teardown, re-run after the ENI timeout, target already gone (9 failed)
cl22 inline policies not deleted before the role: caught by STACK_NAME override, apply, dry-run, re-run after a full teardown, re-run after the ENI timeout, target already gone (9 failed)
22/22 mutations caught; tree unchanged: True
rc=0
dc1 token in argv: caught by 11 tools, 81 connections, Gateway UPDATING, MAX_CONNS=5, 6 connections, audit failures, caller-exported + export lines, filter-log-events error, get-gateway error, permission matrix fails, post, pre, reconcile fails, slow minute, target FAILED, wrong account (16 failed)
dc2 GW_TOKEN leaks into reconcile: caught by caller-exported + export lines, pre (4 failed)
dc3 GW_TOKEN exported from the start: caught by caller-exported + export lines, post, pre (4 failed)
dc4 DORIS_ROOT_PASSWORD passed to reconcile: caught by caller-exported + export lines, pre (2 failed)
dc5 subshell unset list forgets DORIS_ROOT_*: caught by caller-exported + export lines (1 failed)
dc6 caller's DORIS_* not dropped: caught by caller-exported + export lines (1 failed)
dc7 no mask: caught by 11 tools, 81 connections, Gateway UPDATING, MAX_CONNS=5, 6 connections, audit failures, filter-log-events error, get-gateway error, no token, permission matrix fails, pre, reconcile fails, slow minute, target FAILED, wrong account (14 failed)
dc8 exit 0 despite a FAIL: caught by 11 tools, 81 connections, Gateway UPDATING, MAX_CONNS=5, 6 connections, audit failures, filter-log-events error, get-gateway error, no token, permission matrix fails, reconcile fails, slow minute, target FAILED, wrong account (13 failed)
dc9 MAX_CONNS off by one (<): caught by 80 connections (= MAX_CONNS), MAX_CONNS=5, 5 connections (2 failed)
dc10 window not rounded: caught by post (1 failed)
dc10b since rounded up (the first minute's calls dropped): caught by post (2 failed)
dc11 token command's stderr not masked: caught by no token (1 failed)
dc12 credentials loaded globally (set -a): caught by caller-exported + export lines, pre (2 failed)
dc13 post runs the pre checks: caught by audit failures, filter-log-events error, post, slow minute (17 failed)
dc14 audit_check without --failures: caught by post (1 failed)
dc15 seconds accepted for --since/--until: caught by bad arguments (seconds, not ms) (1 failed)
dc16 since == until accepted: caught by bad arguments (since = until) (1 failed)
dc17 mcp_smoke called without a token: caught by no token (2 failed)
dc18 any status taken for READY: caught by Gateway UPDATING, target FAILED (6 failed)
dc19 account not compared: caught by wrong account (3 failed)
dc20 filter-log-events window in seconds: caught by post (1 failed)
21/21 mutations caught; tree unchanged: True
rc=0
cs1 any Secrets Manager error counts as scheduled for deletion: caught by access denied in the project's account fails the check, an error after a skipped secret still fails the check, an expired token fails the check even when sts answers, asks sts in us-east-1, not found in another account fails the check, not found with an expired sts token fails the check, not found without infra/state.env fails even when sts answers, not found without infra/state.env fails the check (no account to compare), secrets not found in the project's account are skipped, the failure names the secret, the last line says FAILED, unreadable secrets fail the check (12 failed)
cs2 not found is skipped without asking sts for the caller's account: caught by asks sts in us-east-1, not found in another account fails the check, not found with an expired sts token fails the check (3 failed)
cs3 no account in infra/state.env still allows the skip (empty equals empty): caught by not found without infra/state.env fails the check (no account to compare) (1 failed)
cs4 any error in the project's account is skipped: caught by access denied in the project's account fails the check, an expired token fails the check even when sts answers (2 failed)
cs5 sts asked in the caller's default region: caught by asks sts in us-east-1 (1 failed)
cs6 the first skip ends the loop (the other secret is not compared): caught by a skipped secret does not hide a leak of the other one, an error after a skipped secret still fails the check, the OK line counts the skipped secrets (3 failed)
cs7 the OK line does not count the skipped secrets: caught by one readable and one skipped secret pass, the OK line counts the skipped secrets (2 failed)
cs8 the error file is appended to (an earlier secret's error decides the next one): caught by an error after a skipped secret still fails the check (1 failed)
cs9 an unreadable secret no longer fails the check: caught by access denied in the project's account fails the check, an error after a skipped secret still fails the check, an expired token fails the check even when sts answers, not found in another account fails the check, not found with an expired sts token fails the check, not found without infra/state.env fails even when sts answers, not found without infra/state.env fails the check (no account to compare), the last line says FAILED, unreadable secrets fail the check (9 failed)
9/9 mutations caught; tree unchanged: True
rc=0
```

- [ ] **Step 5：对真实账号只读运行**

先看清理脚本对真实账号会删什么（dry-run：只有读操作，删除命令只打印）。输出经 `/tmp/p5-idmask.py`：`state.env` 里的每个值换成 `<键名>`，IPv4 换成 `<ip>`，SG 规则 ID 换成 `<sgr>`；**不要看未经 mask 的输出**（里面有资源 ID）。header 的「从计划取文件」已经取出了它：

<!-- file: p5-idmask.py sha256=33ba7eb8618daf136860aa183e65e36c6731fe7ed2ddab7320f86904f2d4a793 -->
```python
"""Mask stdin for the conversation: every value of infra/state.env becomes <KEY>, then IPv4 -> <ip>,
security group rule IDs -> <sgr>, https URL -> <url>.

  some-command 2>&1 | .venv/bin/python /tmp/p5-idmask.py
AWS_REGION and ACCOUNT_ID stay readable (they are in the plan already). Longer values are replaced first, so an ARN
that contains an ID becomes <KEY> of the ARN. Run from the repository root.
"""
import pathlib
import re
import sys

KEEP = {"AWS_REGION", "ACCOUNT_ID"}
state = {}
for line in pathlib.Path("infra/state.env").read_text(encoding="utf-8").splitlines():
    key, sep, value = line.partition("=")
    if sep and re.fullmatch(r"[A-Z0-9_]+", key) and key not in KEEP and len(value.strip()) >= 4:
        state[key] = value.strip()
text = sys.stdin.read()
for key, value in sorted(state.items(), key=lambda kv: len(kv[1]), reverse=True):
    text = text.replace(value, f"<{key}>")
    if "." in value and not value.startswith(("http", "arn:")):  # a host: its first label too (a domain prefix)
        label = value.split(".", 1)[0]
        if len(label) >= 6:
            text = re.sub(rf"\b{re.escape(label)}\b", f"<{key}:prefix>", text)
text = re.sub(r"\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b", "<ip>", text)
text = re.sub(r"\bsgr-[0-9a-f]+\b", "<sgr>", text)
text = re.sub(r"https://[^ )\"`]+", "<url>", text)
sys.stdout.write(text)
```

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
bash infra/99-cleanup.sh 2>&1 | .venv/bin/python /tmp/p5-idmask.py | sed -E 's/^\[[0-9:]{8}\] /[hh:mm:ss] /'; echo "exit=${PIPESTATUS[0]}"
```
期望（实测）：
```
[hh:mm:ss] APPLY=0 region=us-east-1 state=/home/ubuntu/AI-code/Doris-mcp-skill-Demo/infra/state.env
[hh:mm:ss] checks passed
DRY-RUN: aws bedrock-agentcore-control delete-gateway-target --gateway-identifier <GW_ID> --target-id <GW_TARGET_ID>
DRY-RUN: aws bedrock-agentcore-control delete-gateway --gateway-identifier <GW_ID>
DRY-RUN: aws cloudformation delete-stack --stack-name AgentCore-dorismcp-default
DRY-RUN: aws cloudformation wait stack-delete-complete --stack-name AgentCore-dorismcp-default
DRY-RUN: aws ec2 delete-vpc-endpoints --vpc-endpoint-ids <VPCE_S3> <VPCE_LOGS> <VPCE_SECRETSMANAGER>
DRY-RUN: aws cognito-idp delete-user-pool-domain --domain <COGNITO_DOMAIN:prefix> --user-pool-id <COGNITO_POOL_ID>
DRY-RUN: aws cognito-idp delete-user-pool --user-pool-id <COGNITO_POOL_ID>
DRY-RUN: aws secretsmanager delete-secret --secret-id doris-mcp/cognito-demo-user --recovery-window-in-days 7
DRY-RUN: aws secretsmanager delete-secret --secret-id doris-mcp/mcp_svc --recovery-window-in-days 7
DRY-RUN: aws ec2 revoke-security-group-ingress --group-id <DORIS_SG> --security-group-rule-ids <sgr> <sgr>
DRY-RUN: aws ec2 revoke-security-group-egress --group-id <RT_SG> --security-group-rule-ids <sgr>
DRY-RUN: aws ec2 revoke-security-group-ingress --group-id <VPCE_SG> --security-group-rule-ids <sgr>
DRY-RUN: aws ec2 delete-security-group --group-id <RT_SG>
DRY-RUN: aws ec2 delete-security-group --group-id <VPCE_SG>
DRY-RUN: aws iam delete-role-policy --role-name doris-mcp-gateway-role --policy-name invoke-dorismcp-runtime
DRY-RUN: aws iam delete-role --role-name doris-mcp-gateway-role
DRY-RUN: aws iam delete-role-policy --role-name doris-mcp-runtime-role --policy-name doris-mcp-runtime
DRY-RUN: aws iam delete-role --role-name doris-mcp-runtime-role
[hh:mm:ss] done (dry-run, APPLY=1 would delete: Gateway target, Gateway, stack AgentCore-dorismcp-default, 3 VPC endpoints, Cognito domain, user pool, secret doris-mcp/cognito-demo-user, secret doris-mcp/mcp_svc, 2 <DORIS_SG> rules, SG <RT_SG>, SG <VPCE_SG>, role doris-mcp-gateway-role, role doris-mcp-runtime-role). Kept: /home/ubuntu/AI-code/Doris-mcp-skill-Demo/infra/state.env (the record), log groups, X-Ray settings. Doris side (DROP USER mcp_svc, DROP DATABASE system_mcp) is a separate step.
exit=0
```
18 条 `DRY-RUN`，顺序就是 Task 9 执行时的顺序。`doris-demo-sg` 只撤销 2 条引用 `doris-mcp-rt` 的入站规则，它的其他规则不在列表里。

再跑一轮演示检查：`pre` 之后等 3 分钟（CloudWatch 的每分钟指标有 1–3 分钟延迟），再用 `pre` 的时间窗口跑 `post`。输出已经过脚本自己的 MASK：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
S=$(date +%s%3N); bash scripts/demo-check.sh pre; echo "exit=$?"; U=$(date +%s%3N)
sleep 180
bash scripts/demo-check.sh post --since "$S" --until "$U"; echo "exit=$?"
```
期望（实测；毫秒数、`query_id`、连接数每次不同）：
```
[PASS] account
    the caller's account is ACCOUNT_ID
[PASS] gateway READY
    status: READY
[PASS] target READY
    status: READY
[PASS] token
[PASS] list 12 tools
    connected+initialized in 633 ms
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
    total 1579 ms
[PASS] flow
    connected+initialized in 625 ms
      [PASS] execute_query with the profile hint
      [PASS] list_recent_queries finds the trace token
          query_id=e650a325a2c24eb6-8cdf93a2c9db7755 trace_comment_kept=True
      [PASS] get_query_profile summary < 20000 chars  (source=v2 total_chars=103563 returned_chars=9187)
      [PASS] invalid query_id -> INVALID_PARAMS
      [PASS] unknown query_id -> profile_found=false
      [PASS] DML is rejected  (INVALID_SQL)
    flow: 6/6 passed
    total 38587 ms
[PASS] reconcile
    published metrics: 22 match /home/ubuntu/AI-code/Doris-mcp-skill-Demo/doris/semantic/ecom
    ok    ytd_totals (1 rows)
    ok    monthly_2026 (9 rows)
    ok    yoy_2026 (9 rows)
    ok    yoy_same_days_2026_09 (24 rows)
    ok    channel_ytd (4 rows)
    ok    area_ytd (7 rows)
    ok    mini_program_quarterly (7 rows)
    ok    cat1_items_ytd (12 rows)
    ok    brand_tier_ytd (3 rows)
    ok    refund_rate_5_1 (2 rows)
    ok    reviews_by_shop_type_ytd (4 rows)
    ok    refunds_by_reason_ytd (10 rows)
    12/12 cases match
[PASS] permission matrix
    WARNING mcp.client.streamable_http: Session termination failed: 404
    connected as 'mcp_svc'@'172.31.%' (through the Runtime)
    ok    identity: 'mcp_svc'@'172.31.%'
    ok    grants: exactly internal.ecom SELECT, internal.system_mcp SELECT+CREATE (+ Doris defaults)
    ok    databases: ecom, information_schema, mysql, system_mcp
    ok    select: 9 physical tables of the models
    ok    semantic store: workspace ecom semantic_version=3, 10 active files
    info  max_user_connections=100
    probes: not run with --url (execute_query takes read-only SQL only; they need a direct connection)
    5/5 checks pass
[PASS] conns
    connected+initialized in 602 ms
    connections: 5 (Query 1, Sleep 4) from 2 distinct hosts; users mcp_svc; max idle 83 s
      [PASS] host prefix 172.31.: 5/5 connections
      [PASS] idle connections <= 610 s: 0 over
    total 9052 ms
[PASS] conns <= MAX_CONNS
    connections: 5, MAX_CONNS: 80
demo-check pre: 10/10 passed
exit=0
[PASS] audit
    audit: 35 records (33 ok, 2 failed), 0 unreadable
      execute_query                 17 ok   1 failed
      get_query_profile              2 ok   1 failed
      list_metrics                   1 ok   0 failed
      list_recent_queries            1 ok   0 failed
      query_metric                  12 ok   0 failed
    failures: 2
      2026-09-28T22:19:30+0000  get_query_profile  query_id must look like 0123456789abcdef-0123456789abcdef (take it from list_recent_queries)
      2026-09-28T22:19:43+0000  execute_query  (not recorded)
[PASS] latency
    window 2026-09-28T22:18:00Z .. 2026-09-28T22:21:00Z
    tools/call: 7 calls in 4 rows (tool x minute), max 7309 ms (doris___execute_query at 2026-09-28T22:20)
      2026-09-28T22:19  doris___execute_query                  2 calls  avg    5502 ms  max    5760 ms
      2026-09-28T22:19  doris___get_query_profile              3 calls  avg    6304 ms  max    6847 ms
      2026-09-28T22:19  doris___list_recent_queries            1 calls  avg    5737 ms  max    5737 ms
      2026-09-28T22:20  doris___execute_query                  1 calls  avg    7309 ms  max    7309 ms
      [PASS] every minute under 60000 ms
[PASS] token
[PASS] conns
    connected+initialized in 688 ms
    connections: 6 (Query 1, Sleep 5) from 3 distinct hosts; users mcp_svc; max idle 276 s
      [PASS] host prefix 172.31.: 6/6 connections
      [PASS] idle connections <= 610 s: 0 over
    total 7106 ms
[PASS] conns <= MAX_CONNS
    connections: 6, MAX_CONNS: 80
demo-check post: 5/5 passed
exit=0
```
- `post` 的 `failures` 一节是 `flow` 故意触发的 2 个失败：无效的 `query_id`（`get_query_profile`，`INVALID_PARAMS`）和 DML（`execute_query`，`INVALID_SQL`）。已部署的还是旧 server（P-10 在 Task 6 部署），`execute_query` 的失败没有 `error`，显示 `(not recorded)`；`get_query_profile` 的错误文字旧 server 已经记录。
- `audit` 的记录数（这里 35）比 `latency` 的调用数（这里 7）多：`reconcile`（`list_metrics` 1 次、`query_metric` 12 次）和 `permission matrix`（`execute_query`）直接连 Runtime，不经 Gateway；经 Gateway 的只有 `flow` 的 6 次和 `conns` 的 1 次。两边的计数随窗口里的调用变化，按这个关系对得上就行。
- `permission matrix` 里的 `WARNING mcp.client.streamable_http: Session termination failed: 404` 是 mcp SDK 关闭 session 时发 DELETE、收到 404 后打印的告警（P3 已记录，预期的），不影响结果。

`pre` 只有一项失败（多半是 Runtime 偶发的 502 或冷启动超时，design §13）时整条重跑一次；同一项连续两次失败才排查。

- [ ] **Step 6：收尾，提交**

T5.5 在 Task 8、T5.6 在 Task 9 勾选；这里只更新状态和日志。
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
echo 'Task 5（demo-check / cleanup / 30-gateway 脚本）已完成；Task 6（部署 P-10、P-11，GATE）从 Step 1 开始' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo 'Task 6（锁 3 个传递依赖，部署，GATE），然后 Task 7（整体评审，再交给用户导入 skill 和彩排 2 轮）、Task 8（T5.5）、Task 9（演示结束后清理，GATE）' | .venv/bin/python /tmp/p5-progress.py state 下一步
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 5：`demo-check.sh`、`99-cleanup.sh`、`30-gateway.sh` 的开关、`check-secrets.sh` 跳过已删除的 secret

- `infra/30-gateway.sh`：create 和 update 共用一组参数（`update-gateway` 会清空没传的选项，P3 同步 target 时重跑之后 description 变成了 `None`），description 放进去；`GW_EXCEPTION_LEVEL` 开关（默认 `DEBUG`，`""` 不传，其他值拒绝）。没有执行，Task 8 决定。
- `infra/99-cleanup.sh`：按依赖顺序删除本项目的 AWS 资源（target → Gateway → stack → endpoint → Cognito domain → pool → secret → `doris-demo-sg` 里引用 `doris-mcp-rt` 的规则 → 等 ENI 释放 → 两个 SG → IAM 角色）；第一次删除前检查账号、标签、Gateway 名字，只认 NOT_FOUND 为「已删除」，其他错误 FATAL、什么都不删；可重跑。对真实账号 dry-run：检查全部通过，18 条删除命令。
- `scripts/demo-check.sh`：`pre` 10 项、`post` 5 项；token 不 export、不上命令行、不打印；只有对账拿到只读账号的变量；耗时窗口 `--since` 向下取整、`--until` 向上取整。对真实账号：pre 10/10、post 5/5（旧 server：失败的调用显示 `(not recorded)`）。
- `scripts/check-secrets.sh`：Task 9 删掉的 secret 跳过（排期删除，或者在 `state.env` 的账号里已不存在），OK 行写明跳过了几个；过期、没有权限、别的账号、没有 `state.env` 仍然失败。否则清理之后每次提交都过不了检查。
- 未解决的 Minor：`TOKEN_CMD` 的默认值不看 `STATE_FILE`；`99-cleanup.sh` 的少数「已经不存在」分支只在离线测试里走过。
- RED：`test-30-gateway.sh` 19 个、`test-99-cleanup.sh` 60 个、`test-demo-check.sh` 78 个、`test-check-secrets.sh` 7 个 `FAIL`（update 没带 description、没有 `GW_EXCEPTION_LEVEL`，两个脚本不存在，删掉的 secret 不跳过）。
- GREEN：`test-30-gateway.sh` 30、`test-99-cleanup.sh` 81、`test-demo-check.sh` 96、`test-check-secrets.sh` 36 个检查，原有另外 5 组 shell 测试和 `scripts/test` 137 通过；突变 gw 11/11、cl 22/22、dc 21/21、cs 9/9 被抓到。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add infra/30-gateway.sh infra/99-cleanup.sh scripts/demo-check.sh scripts/check-secrets.sh \
        infra/test/test-30-gateway.sh infra/test/test-99-cleanup.sh scripts/test/test-demo-check.sh scripts/test/test-check-secrets.sh \
        specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
feat(p5): demo-check.sh pre/post, 99-cleanup.sh (dependency order, checks before the first delete), 30-gateway.sh GW_EXCEPTION_LEVEL and shared create/update args, check-secrets.sh skips deleted secrets

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望（实测）：
```
进行中: written (767 lines)
下一步: written (767 lines)
### 2026-09-28 P5 Task 5：`demo-check.sh`、`99-cleanup.sh`、`30-gateway.sh` 的开关、`check-secrets.sh` 跳过已删除的 secret: written (777 lines)
check-secrets: OK (849 files scanned)
0
feat(p5): demo-check.sh pre/post, 99-cleanup.sh (dependency order, checks before the first delete), 30-gateway.sh GW_EXCEPTION_LEVEL and shared create/update args, check-secrets.sh skips deleted secrets
```
日志里的数字如果和实测不同，写实测值。

---

### Task 6：T5.7a 部署：锁 3 个传递依赖，部署前后的探针（GATE）

来源：tasks.md T5.7a（部署 P-10、P-11），design §5.2 的 P-07、P-10、P-11，P3 T3.2（CodeZip 必须和测试用的 `.venv` 一致）。本任务唯一的 GATE 是 Step 4 的 `agentcore deploy -y`，其余步骤对 AWS 都是只读的。spec 阶段的发现：

| # | spec 阶段的发现 | 处理 | 测试 |
|---|---|---|---|
| 1 | 3 个传递依赖在 P3 之后发了新版：`boto3` → `botocore`（1.43.104，`.venv` 是 1.43.103）、`cyclopts` → `rich-rst`（2.2.0，`.venv` 是 2.1.0）、`mcp` → `sse-starlette`（3.5.0，`.venv` 是 3.4.11）。CodeZip 按 `pyproject.toml` 解析到新版，和测试用的 `.venv` 不一致。PyPI 一直在发新版（`botocore` 几乎每个工作日一版），执行时可能还会多 | `pyproject.toml` 把这 3 个锁到 `.venv` 的版本，和 P3 锁 `caio`、`platformdirs` 的做法相同；`UPSTREAM.md` 的 P-07 改成「5 个传递依赖」。执行时 RED 列出的包多于这 3 个，按 Step 1 的说明补上 | Step 1：`p5-codezip-check.sh` 锁之前 3 个不同（RED），锁之后 0 个（GREEN）；Step 3 对 deploy 的 staging 再查一次 |
| 2 | 旧 server 上 7 个 `query_metric` 探针的结果（经 Gateway 实测）：`>` / `<` 按闭区间处理，3 个条件只取最后一个，括号包住的范围和 OR 都报 Doris 语法错误 | 部署前（Step 2）和部署后（Step 6）各跑一次同样的 7 个探针：只有 strict、intersect、mixed、or 4 个变化，between、yoy_days、yoy_year 不变 | Step 2 的对照表；新 server 的期望由本机编译、`demo_ro` 执行得到 |
| 3 | 带新代码的 `agentcore deploy --diff`：只有 Runtime 一个资源变化，而且只变了 CodeZip 的 S3 路径 | 出现 Runtime 的 destroy / replace、新增资源或 IAM 变化就停下来，不部署 | Step 3 的 diff 过滤结果（12 行）|
| 4 | Runtime 原地更新：ARN、URL、角色、env、网络都不变，`state.env` 不用改；12 个工具的名字、参数和描述都没改，Gateway target 不用同步 | 部署后 `25-runtime-state.sh` 应显示 `version=3`；`demo-check pre` 的 `list 12 tools` 确认工具目录不变 | Step 3 的工具定义计数（0）；Step 5、Step 6 |

**Files:**
- Modify: `mcp-server/pyproject.toml`（`botocore==1.43.103`、`rich-rst==2.1.0`、`sse-starlette==3.4.11`，注释）、`mcp-server/UPSTREAM.md`（P-07 一行）
- 部署生成：`dorismcp/agentcore/.cli/deployed-state.json`（新的 `deployHash`）
- Test: `/tmp/p5-codezip-check.sh`（按 agentcore CLI 的方式解析依赖，和 `.venv` 逐个比较版本）；在线：7 个探针、`demo-check pre` / `post`

**Interfaces:**
- Consumes：Task 3 的 P-10、P-11 和 `_METRIC_TIME_OR_ERROR`（`MetricFlow compile error: metric_time filters must be a single range joined with AND …`）；Task 4 的 `audit_check.py --failures`；Task 5 的 `demo-check.sh pre` / `post --since MS --until MS`；Task 2 的 `reconcile.CASES`（12 个）；`bcda0f3` 的 `infra/25-runtime-state.sh`（dry-run 输出 `runtime dorismcp_dorismcp: status=… version=…`）、`scripts/mcp_smoke.py call`；agentcore CLI 的 `validate`、`deploy --diff`、`deploy -y`。
- Produces：
  - Runtime `dorismcp_dorismcp` version 3（P-10、P-11）：Task 7 的彩排和每次 `demo-check post` 的失败列表都依赖它（失败的调用有 `error`，`query_metric` 有 `where` / `having`）；
  - `dorismcp/agentcore/.cli/deployed-state.json`（和部署一起提交）。

- [ ] **Step 1：锁 3 个传递依赖（RED → GREEN）**

先确认 CodeZip 和 `.venv` 不一致。`p5-codezip-check.sh` 不带参数时，按 agentcore CLI 的方式（`uv`，aarch64 的 manylinux_2_28 wheel）把 `mcp-server/pyproject.toml` 解析到 `/tmp/p5-zipcheck`，再和 `.venv` 逐个比较版本（要访问 PyPI）。header 的「从计划取文件」已经取出了它：

<!-- file: p5-codezip-check.sh sha256=1089532a48f96d781d0b555fc79cb3f33953236e497e105c4ee6dcf631959572 -->
```bash
# Compare the dists of an AgentCore CodeZip with the tested .venv (P3 / T3.2). Run from the repo root.
#   bash /tmp/p5-codezip-check.sh               # resolve mcp-server/pyproject.toml the way the agentcore CLI does
#   bash /tmp/p5-codezip-check.sh STAGING_DIR   # the dists of an existing CodeZip staging dir
set -euo pipefail
DIR="${1:-}"
if [[ -z "$DIR" ]]; then
  DIR=/tmp/p5-zipcheck
  rm -rf "$DIR"
  # The CLI tries manylinux2014 first; rapidfuzz has no such wheel, so it ends up on 2_28.
  uv pip install -q -r mcp-server/pyproject.toml --target "$DIR" --python-version 3.12 \
    --python-platform aarch64-manylinux_2_28 --only-binary :all:
fi
uv pip freeze --python .venv/bin/python > /tmp/p5-venv-freeze.txt
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
for line in open("/tmp/p5-venv-freeze.txt"):
    if "==" in line:
        name, version = line.strip().split("==", 1)
        venv[norm(name)] = version
differ = sorted(n for n in zipped if venv.get(n) != zipped[n])
for n in differ:
    print(f"  {n}: CodeZip {zipped[n]}, .venv {venv.get(n, '-')}")
print(f"CodeZip: {len(zipped)} dists, {len(differ)} differ from .venv")
sys.exit(1 if differ else 0)
PY
```

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
bash /tmp/p5-codezip-check.sh; echo "exit=$?"
```
期望（实测）：
```
  botocore: CodeZip 1.43.104, .venv 1.43.103
  rich-rst: CodeZip 2.2.0, .venv 2.1.0
  sse-starlette: CodeZip 3.5.0, .venv 3.4.11
CodeZip: 88 dists, 3 differ from .venv
exit=1
```

RED 列出的包和上面不同时：
- 多出来的包（PyPI 又发了新版）：`git apply` 之后，在 `pyproject.toml` 的锁定列表里按字母序加 `"包名==<.venv 的版本>"`，注释里补上它是谁的传递依赖（`uv pip show --python .venv/bin/python 包名` 的 `Required-by`）和 CodeZip 解析到的版本；`UPSTREAM.md` P-07 的计数、commit message 和 progress 日志都按实际的包写。
- 这 3 个里有的没有出现：锁定照样加（锁的就是 `.venv` 的版本）。
- GREEN 必须是 `0 differ` 和 `exit=0`，否则不进入 Step 2。uv 报版本冲突时停下来问用户。

锁定：

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py t56-impl.diff /tmp/t56-impl.diff
git apply /tmp/t56-impl.diff && git status --short && git diff --shortstat
```
期望（实测）：
```
t56-impl.diff -> /tmp/t56-impl.diff (32 lines)
 M mcp-server/UPSTREAM.md
 M mcp-server/pyproject.toml
 2 files changed, 7 insertions(+), 3 deletions(-)
```

<!-- file: t56-impl.diff sha256=0da28ca3f922ca5aa3941f8adbe3f1770ddd670fe0af6088b2688500b5d61316 -->
```diff
diff --git a/mcp-server/UPSTREAM.md b/mcp-server/UPSTREAM.md
index 38dc052..d13bd35 100644
--- a/mcp-server/UPSTREAM.md
+++ b/mcp-server/UPSTREAM.md
@@ -16,7 +16,7 @@
 | P-04 | `src/server.py` | `create_server(service_credentials=, workspace_dir=)`: no MCP auth, one service-account pool |
 | P-05 | `src/tools/profile.py` (new) | `list_recent_queries`, `get_query_profile` |
 | P-06 | `config/mcp-server.toml` (new) | runtime limits (50 s SQL timeout, pool 5, 2000 rows) |
-| P-07 | `pyproject.toml` (new) | dependencies pinned to upstream `uv.lock` + boto3 (+ 2 transitive pins that keep the CodeZip equal to the tested `.venv`), for AgentCore CodeZip |
+| P-07 | `pyproject.toml` (new) | dependencies pinned to upstream `uv.lock` + boto3 (+ 5 transitive pins that keep the CodeZip equal to the tested `.venv`), for AgentCore CodeZip |
 | P-08 | `test/test_agentcore_*.py` (new) | tests for P-01..P-06, P-10 (`test_agentcore_audit_errors.py`) and P-11 (`test_agentcore_time_constraints.py`) |
 | P-09 | `src/config/loader.py`, `src/core/connection.py`, `config/mcp-server.toml`, `test/test_agentcore_session_timeout.py` (new) | `SET wait_timeout` on every pool connection (`session_wait_timeout_seconds = 600`), so Doris reaps what a torn-down Runtime microVM left open |
 | P-10 | `src/server.py` | the audit record of a failed `execute_query` / `query_metric` carries `error` (`CODE: message`, 300 chars, masked); `query_metric` takes success from the parsed result, logs the resolved `where` plus `having`, `order_by`, `limit`, and its `mf_command` gains `--where`/`--order-by`/`--limit`/`--having` |
diff --git a/mcp-server/pyproject.toml b/mcp-server/pyproject.toml
index bb13ee7..6cdfde6 100644
--- a/mcp-server/pyproject.toml
+++ b/mcp-server/pyproject.toml
@@ -33,8 +33,12 @@ dependencies = [
     "typer==0.27.0",
     "typing_extensions==4.16.0",
     "uvicorn==0.51.0",
-    # Transitive (aiofile -> caio, fastmcp-slim -> platformdirs), pinned to the tested .venv: unpinned,
-    # the CodeZip resolved newer releases than the ones the tests ran with (P3 T3.2).
+    # Transitive (aiofile -> caio, fastmcp-slim -> platformdirs, boto3 -> botocore, cyclopts -> rich-rst,
+    # mcp -> sse-starlette), pinned to the tested .venv: unpinned, the CodeZip resolved newer releases than
+    # the ones the tests ran with (P3 T3.2; botocore 1.43.104, rich-rst 2.2.0 and sse-starlette 3.5.0 in P5).
+    "botocore==1.43.103",
     "caio==0.12.5",
     "platformdirs==4.11.15",
+    "rich-rst==2.1.0",
+    "sse-starlette==3.4.11",
 ]
```

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
bash /tmp/p5-codezip-check.sh; echo "exit=$?"
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 期望：Ran 141 tests … OK
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3     # 期望：🎉 All tests passed!
```
期望（实测）：
```
CodeZip: 88 dists, 0 differ from .venv
exit=0
Ran 141 tests in 0.775s

OK
═══════════════════════════════════
  🎉 All tests passed!
═══════════════════════════════════
```

先提交锁定（部署之前；GATE 之后如果要回滚，只回滚 Task 3 的代码，锁定保留）：

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
echo 'Task 6 Step 1（锁 3 个传递依赖）已提交；Step 2（部署前的探针）继续，Step 4 是 GATE（agentcore deploy -y）' | .venv/bin/python /tmp/p5-progress.py state 进行中
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add mcp-server/pyproject.toml mcp-server/UPSTREAM.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
fix(p5): pin botocore, rich-rst and sse-starlette to the tested .venv so the CodeZip matches it (P-07)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望（实测）：
```
进行中: written (777 lines)
check-secrets: OK (849 files scanned)
0
fix(p5): pin botocore, rich-rst and sse-starlette to the tested .venv so the CodeZip matches it (P-07)
```

- [ ] **Step 2：部署前的探针（只读，旧 server）**

经 Gateway 对已部署的 Runtime（旧 server）调 7 次 `query_metric`，每次只输出一行摘要：行数、`metric_time` 列的第一个和最后一个值、每个指标的合计；失败时输出错误码和消息的前 160 个字符。摘要由 `/tmp/p5-rows.py` 生成（header 的「从计划取文件」已经取出）：

<!-- file: p5-rows.py sha256=ff641acb8fe7037e45bbdf0d18ef5090ab88698204518e1f04afa4e548c931ad -->
```python
"""stdin: `mcp_smoke.py call doris___query_metric` output. Prints one line for LABEL (argv[1]):
  LABEL: N rows FIRST..LAST; COL=SUM ...      (the metric_time column's first and last value, each metric's sum)
  LABEL: CODE: MESSAGE                         (a failed call; the message cut to 160 characters)
Exit code 1 when stdin holds no JSON body. Mask the output (MASK) like everything else."""
import json
import sys

label = sys.argv[1]
text = sys.stdin.read()
try:
    body = json.loads(text[text.index("{"):text.rindex("}") + 1])
except ValueError:
    sys.exit(f"{label}: FAIL: no JSON body")
if body.get("success") is not True:
    error = body.get("error") or {}
    print(f"{label}: {error.get('code')}: {str(error.get('message'))[:160]}")
    sys.exit(0)
cols, rows = body["data"]["columns"], body["data"]["rows"]
time_cols = [c for c in cols if c.startswith("metric_time")]
span = ""
if time_cols and rows:
    days = sorted(str(r[time_cols[0]])[:10] for r in rows)
    span = f" {days[0]}..{days[-1]}"
sums = " ".join(f"{c}={sum(r[c] or 0 for r in rows):,.2f}" for c in cols if c not in time_cols)
print(f"{label}: {len(rows)} rows{span}; {sums}")
```

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
source infra/state.env
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
q() { printf '{"workspace":"ecom","metrics":%s,"group_by":["%s"],"where":"%s"}' "$1" "$2" "$3"; }
while IFS='|' read -r label metrics gb where; do
  .venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN --timeout 60 call doris___query_metric "$(q "$metrics" "$gb" "$where")" 2>/tmp/p5-qm.err \
    | .venv/bin/python /tmp/p5-rows.py "$label" | sed -E "$MASK"; sed -E "$MASK" /tmp/p5-qm.err | grep -v '^$' | head -3
done <<'CALLS'
strict|["gmv"]|metric_time__day|metric_time > '2026-09-20' AND metric_time < '2026-09-24'
between|["gmv"]|metric_time__day|metric_time BETWEEN '2026-09-21' AND '2026-09-23'
intersect|["gmv"]|metric_time__day|metric_time >= '2026-09-20' AND metric_time <= '2026-09-24' AND metric_time >= '2026-09-01'
yoy_days|["gmv","gmv_last_year"]|metric_time__day|metric_time BETWEEN '2026-09-01' AND '2026-09-25'
yoy_year|["gmv","gmv_last_year"]|metric_time__year|metric_time BETWEEN '2026-09-01' AND '2026-09-25'
mixed|["gmv"]|metric_time__month|(metric_time BETWEEN '2026-09-01' AND '2026-09-25') AND channel = 'MINI_PROGRAM'
or|["gmv"]|metric_time__day|metric_time BETWEEN '2026-09-01' AND '2026-09-03' OR metric_time BETWEEN '2025-09-01' AND '2025-09-03'
CALLS
unset GW_TOKEN; rm -f /tmp/p5-qm.err
```
期望（实测）：
```
strict: 5 rows 2026-09-20..2026-09-24; gmv=1,039,580.54
between: 3 rows 2026-09-21..2026-09-23; gmv=542,815.93
intersect: 24 rows 2026-09-01..2026-09-24; gmv=5,534,615.26
yoy_days: 25 rows 2026-09-01..2026-09-25; gmv=5,754,567.17 gmv_last_year=4,721,825.63
yoy_year: 1 rows 2026-01-01..2026-01-01; gmv=65,662,188.15 gmv_last_year=77,892,353.86
mixed: CONNECTION_ERROR: (1105, "errCode = 2, detailMessage = \nno viable alternative at input '()'(line 21, pos 7)\n")
or: CONNECTION_ERROR: (1105, "errCode = 2, detailMessage = \nmismatched input 'OR' expecting {'(', '[', '{', '}', 'ACTIONS', 'ADD', 'AFTER', 'AGG_STATE', 'AGGREGATE', 'ALIAS', 'ANALY
```
对照表：「旧 server」是上面经 Gateway 的实测；「新 server」是 spec 阶段用 Task 3 的代码在本机编译（`reconcile.DirectBackend`）、以 `demo_ro` 在同一份数据上执行的结果，Step 6 部署之后经 Gateway 应当得到同样的值。

| 探针 | 条件 | 旧 server | 新 server | 变化 |
|---|---|---|---|---|
| strict | `>` 20 日 `AND` `<` 24 日，按天 | 5 天（20–24 日，按闭区间），gmv 1,039,580.54 | 3 天（21–23 日），gmv 542,815.93 | 严格比较（P-11）|
| between | `BETWEEN` 21 日 `AND` 23 日，按天 | 3 天，gmv 542,815.93 | 相同 | 不变 |
| intersect | `>=` 20 日 `AND` `<=` 24 日 `AND` `>=` 1 日，按天 | 24 天（1–24 日，只取了最后一个条件），gmv 5,534,615.26 | 5 天（20–24 日），gmv 1,039,580.54 | 取交集（P-11）|
| yoy_days | 9 月 1–25 日，`gmv` + `gmv_last_year`，按天 | 25 天，5,754,567.17 / 4,721,825.63 | 相同 | 不变 |
| yoy_year | 9 月 1–25 日，`gmv` + `gmv_last_year`，按年 | 1 行（2026 整年），65,662,188.15 / 77,892,353.86 | 相同 | 不变：按分组粒度对齐，MetricFlow 的设计 |
| mixed | 括号包住的范围 `AND channel = 'MINI_PROGRAM'`，按月 | `CONNECTION_ERROR`：Doris 语法错误（去掉时间条件后留下空括号）| 1 行（9 月），gmv 1,847,038.07 | 括号（P-11）|
| or | 两个 `BETWEEN` 用 `OR` 连接，按天 | `CONNECTION_ERROR`：Doris 语法错误 | `INTERNAL_ERROR`：明确的编译错误，提示每个范围调用一次或用 `*_last_year` | 明确的错误（P-11）|

Step 6 的 7 行期望（`p5-rows.py` 的格式）：
```
strict: 3 rows 2026-09-21..2026-09-23; gmv=542,815.93
between: 3 rows 2026-09-21..2026-09-23; gmv=542,815.93
intersect: 5 rows 2026-09-20..2026-09-24; gmv=1,039,580.54
yoy_days: 25 rows 2026-09-01..2026-09-25; gmv=5,754,567.17 gmv_last_year=4,721,825.63
yoy_year: 1 rows 2026-01-01..2026-01-01; gmv=65,662,188.15 gmv_last_year=77,892,353.86
mixed: 1 rows 2026-09-01..2026-09-01; gmv=1,847,038.07
or: INTERNAL_ERROR: MetricFlow compile error: metric_time filters must be a single range joined with AND (no OR around a metric_time condition). Make one query_metric call per rang
```

某一个探针报 502 或超时（design §13）时整条重跑一次。

- [ ] **Step 3：validate + CDK diff（只读）**

先确认 Gateway target 不用同步：Task 3 没有改任何工具的注册、描述或参数（`@mcp.tool`、`description=`、工具函数的签名）：

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
git diff bcda0f3 -- mcp-server/src/server.py mcp-server/src/tools | grep -E '^[-+]' | grep -cE '@mcp\.tool|description=|async def [a-z_]+\('
```
期望（实测）：
```
0
```

然后跑 CDK diff。它会在 `dorismcp/agentcore/.cache/` 里生成 staging（已被 gitignore），用 `dorismcp/agentcore/cdk/node_modules`（P0 装好的）；日志原文里有账号和 ARN，只看过滤后的行：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
(cd dorismcp && agentcore validate && agentcore deploy --diff -v) > /tmp/t56-diff.log 2>&1; echo "exit=$?"
sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g; s/^.*(Stack AgentCore)/\1/' /tmp/t56-diff.log | sed -E "$MASK" |
  grep -E '^Valid|^Stack |\[[-+~]\] |Number of stacks|^✓ Diff complete' | sed -E 's/[0-9a-f]{64}/<sha>/g; s/ +$//' | cut -c1-200
bash /tmp/p5-codezip-check.sh dorismcp/agentcore/.cache/dorismcp/staging; echo "exit=$?"
```
期望（diff 的行是 spec 阶段在一个代码相同的 worktree 上实测的；那次只锁了 `rich-rst`，锁定只影响 zip 的内容，不影响 diff 的行。两个 zip 的 sha256 每次不同，换成了 `<sha>`。CodeZip 一行是 3 个锁定之后的期望，和 Step 1 GREEN 的解析相同）：
```
exit=0
Valid
Stack AgentCore-dorismcp-default
[~] AWS::BedrockAgentCore::Runtime Application/AgentDorismcp/Runtime ApplicationAgentDorismcpRuntime21B2F7F2
 └─ [~] AgentRuntimeArtifact
     └─ [~] .CodeConfiguration:
         └─ [~] .Code:
             └─ [~] .S3:
                 └─ [~] .Prefix:
                     ├─ [-] <sha>.zip
                     └─ [+] <sha>.zip
✨ Number of stacks with differences: 1
✓ Diff complete for 'default' (stack: AgentCore-dorismcp-default)
CodeZip: 88 dists, 0 differ from .venv
exit=0
```
diff 的含义：只有 Runtime 是 `[~]`（原地更新），变的只是 CodeZip 在 S3 上的路径（新代码的 zip）；env、角色、网络、Gateway 都没有出现，所以 `RUNTIME_ARN` / `RUNTIME_URL` 不变，`state.env` 不用改。staging 里 88 个 dist 和 `.venv` 一致（`botocore`、`rich-rst`、`sse-starlette` 都是 `.venv` 的版本）。

如果出现 Runtime 的 `destroy` / `replace`、任何 `[+]` 资源、IAM 的变化，或者 CodeZip 检查有不同，停下来，不要部署。`exit=1` 并且日志里有 `tsc: not found` 时，是 `cdk/node_modules` 不在了：`(cd dorismcp/agentcore/cdk && npm ci)` 之后重跑本步。

- [ ] **Step 4：GATE —— 展示并等待确认**

向用户展示 Step 1 的锁定、Step 2 的探针结果和 Step 3 的 diff，并说明：
- `agentcore deploy -y` 更新 CloudFormation 栈 `AgentCore-dorismcp-default`：Runtime `dorismcp_dorismcp` 原地更新为带 P-10、P-11 和 3 个传递依赖锁定的代码，version 2 → 3；ARN、URL、执行角色、env、网络都不变。
- Gateway target 不变：12 个工具的名字、参数和描述都没改（Step 3 的计数是 0），不用同步；`state.env` 不变。
- 耗时：P3 T3.2 的部署是 `1m 17s`（P0 是 `5m 41s`）。
- 费用：Runtime 按会话计费，没有新增的常驻资源；CodeZip（约 107 MB）上传到已有的 CDK bootstrap bucket。
- 影响：部署期间（约 2 分钟）不要在 Quick 里测试；已经打开的会话可能报一次错，新会话就正常了。
- 部署后可以看到的变化：Step 2 的 4 个探针结果变成新的值；失败的调用在审计里有原因（`demo-check post` 列出来）。
- 回滚（也需要 GATE）：`git revert` Task 3 的提交（server 代码回到 `bcda0f3`，Step 1 的锁定保留），然后再 deploy 一次（version 4）。

用户明确确认后执行（用 Bash 的 `run_in_background`，或者把 timeout 设为 600000）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
(cd dorismcp && agentcore deploy -y -v) > /tmp/t56-deploy.log 2>&1; echo "exit=$?"
```
期望：`exit=0`。如果 harness 拦住了这条命令，请用户在提示符里输入 `! cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo && (cd dorismcp && agentcore deploy -y -v) > /tmp/t56-deploy.log 2>&1; echo "exit=$?"` 自己执行（输出只有 `exit=…` 一行）。

- [ ] **Step 5：确认部署结果（只读）**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
log=$(ls -t dorismcp/agentcore/.cli/logs/deploy/deploy-*.log | head -1)
grep -c 'Status: SUCCESS' "$log"; grep -E '^(COMPLETED|FAILED)|^Total Duration|Status: (FAILED|ERROR)' "$log" | sed -E "$MASK"
bash infra/25-runtime-state.sh 2>&1 | sed -E "$MASK" | grep -E 'runtime dorismcp|WARN|FATAL' | sed -E 's/^\[[0-9:]{8}\] /[hh:mm:ss] /'
bash /tmp/p5-codezip-check.sh dorismcp/agentcore/.cache/dorismcp/staging; echo "exit=$?"
git status --short
```
期望（按 P3 T3.2 的实测格式）：
- `9`：CLI 的 9 个步骤都是 `Status: SUCCESS`（Load deployment target、Validate project、Sync CDK dependencies、Build CDK project、Synthesize CloudFormation、Check bootstrap status、Check stack status、Deploy to AWS、Persist deployment state）；然后是 `COMPLETED SUCCESSFULLY` 和 `Total Duration: …`（P3 是 `1m 17s`），没有 `FAILED` / `ERROR`；
- `[hh:mm:ss] runtime dorismcp_dorismcp: status=READY version=3`，没有 WARN；
- `CodeZip: 88 dists, 0 differ from .venv`、`exit=0`；
- `git status`：只有 ` M dorismcp/agentcore/.cli/deployed-state.json`。

如果 status 不是 READY，等 1 分钟重跑 `25-runtime-state.sh` 那一行；仍然不是、或者 version 还是 2，停下来，把 `grep -E 'Status: (FAILED|ERROR)|Error' /tmp/t56-deploy.log | tail -20 | sed -E "$MASK"` 给用户看。

- [ ] **Step 6：新 server 的在线核对（只读）**

先跑 `pre`（10 项，含对账 12/12 和权限矩阵 5/5），再跑一次 Step 2 的 7 个探针，等 3 分钟（CloudWatch 的每分钟指标有 1–3 分钟延迟），用这段时间窗口跑 `post`。窗口里有 3 个故意失败的调用：`pre` 的 `flow` 触发的 2 个（和 Task 5 Step 5 相同）和 or 探针。`post` 的审计应当列出它们的 `error`，or 探针还带过滤条件，这就是 P-10 在 AgentCore 上的实测：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
source infra/state.env
S=$(date +%s%3N); bash scripts/demo-check.sh pre; echo "exit=$?"
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
q() { printf '{"workspace":"ecom","metrics":%s,"group_by":["%s"],"where":"%s"}' "$1" "$2" "$3"; }
while IFS='|' read -r label metrics gb where; do
  .venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN --timeout 60 call doris___query_metric "$(q "$metrics" "$gb" "$where")" 2>/tmp/p5-qm.err \
    | .venv/bin/python /tmp/p5-rows.py "$label" | sed -E "$MASK"; sed -E "$MASK" /tmp/p5-qm.err | grep -v '^$' | head -3
done <<'CALLS'
strict|["gmv"]|metric_time__day|metric_time > '2026-09-20' AND metric_time < '2026-09-24'
between|["gmv"]|metric_time__day|metric_time BETWEEN '2026-09-21' AND '2026-09-23'
intersect|["gmv"]|metric_time__day|metric_time >= '2026-09-20' AND metric_time <= '2026-09-24' AND metric_time >= '2026-09-01'
yoy_days|["gmv","gmv_last_year"]|metric_time__day|metric_time BETWEEN '2026-09-01' AND '2026-09-25'
yoy_year|["gmv","gmv_last_year"]|metric_time__year|metric_time BETWEEN '2026-09-01' AND '2026-09-25'
mixed|["gmv"]|metric_time__month|(metric_time BETWEEN '2026-09-01' AND '2026-09-25') AND channel = 'MINI_PROGRAM'
or|["gmv"]|metric_time__day|metric_time BETWEEN '2026-09-01' AND '2026-09-03' OR metric_time BETWEEN '2025-09-01' AND '2025-09-03'
CALLS
unset GW_TOKEN; rm -f /tmp/p5-qm.err
U=$(date +%s%3N)
sleep 180
bash scripts/demo-check.sh post --since "$S" --until "$U"; echo "exit=$?"
```
期望：
- `pre`：和 Task 5 Step 5 的格式相同，10 项 `[PASS]`，`reconcile` 是 `12/12 cases match`，`permission matrix` 是 `5/5 checks pass`，最后 `demo-check pre: 10/10 passed`、`exit=0`；
- 7 个探针：Step 2 表里「新 server」那一列的值；
- `post`：5 项 `[PASS]`，`demo-check post: 5/5 passed`、`exit=0`。`audit` 一项的计数随调用数变化，`failures` 一节是这 3 个（时间戳每次不同；`pre` 重跑过时，`flow` 的 2 个出现两遍）。和 Task 5 Step 5 比，`execute_query` 不再是 `(not recorded)`：
```
    failures: 3
      2026-09-DDThh:mm:ss+0000  get_query_profile  query_id must look like 0123456789abcdef-0123456789abcdef (take it from list_recent_queries)
      2026-09-DDThh:mm:ss+0000  execute_query  INVALID_SQL: Statement prefix 'DELETE' not allowed in read-only mode
      2026-09-DDThh:mm:ss+0000  query_metric  INTERNAL_ERROR: MetricFlow compile error: metric_time filters must be a single range joined with AND (no OR around a metric_time condition). Make one query_metric call per range; for period-over-perio
          group_by: ['metric_time__day']
          where: {{ TimeDimension('metric_time', 'day') }} BETWEEN '2026-09-01' AND '2026-09-03' OR {{ TimeDimension('metric_time', 'day') }} BETWEEN '2025-09-01' AND '2025-09-03'
          having:
```
- `latency` 一项：窗口里每分钟一行，`query_metric` 的行里包含这 7 次调用。

`pre` 只有一项失败（多半是 Runtime 偶发的 502 或冷启动超时，design §13）时整条重跑一次；同一项连续两次失败，或者探针的结果和「新 server」那一列不同（9 月 25 日的实时订单只会让 yoy_days、yoy_year、mixed 的数字变大），停下来查原因。`failures` 里出现这 3 个之外的调用时，看它的 `error`，不要重试到通过为止。

- [ ] **Step 7：收尾，提交**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - T5.7a <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
.venv/bin/python /tmp/p5-progress.py sub '已创建的 AWS 资源' 'version 2' 'version 3'
echo 'Task 6（T5.7a 部署）已完成：Runtime version 3；Task 7 从 Step 1（用户指南、演示手册）开始' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo 'Task 7（写指南和手册 → 整体评审 → 用户导入 skill → 彩排 2 轮），然后 Task 8（T5.5）、Task 9（演示结束后清理，GATE）' | .venv/bin/python /tmp/p5-progress.py state 下一步
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 6（T5.7a 部署）：锁 3 个传递依赖，Runtime version 3

- 传递依赖漂移：CodeZip 按 `pyproject.toml` 解析到 `botocore` 1.43.104、`rich-rst` 2.2.0、`sse-starlette` 3.5.0，`.venv` 是 1.43.103、2.1.0、3.4.11；锁到 `.venv` 的版本（P-07 改成 5 个传递依赖），CodeZip 检查 3 个不同 → 0 个。
- 部署前经 Gateway 跑 7 个 `query_metric` 探针（旧 server）：strict 按闭区间取到 5 天，intersect 只取最后一个条件（24 天），mixed（括号包住的范围）和 or 报 Doris 语法错误（`CONNECTION_ERROR`）。
- `agentcore deploy --diff`：只有 Runtime 的 CodeZip 路径变化；staging 88 个 dist 和 `.venv` 一致；工具定义没有变化，target 不同步。
- GATE：用户确认「（用户的原话）」后 `agentcore deploy -y`：9 个步骤 SUCCESS，`Total Duration: （实测）`；Runtime `status=READY version=3`，ARN / URL 不变，`state.env` 不变。
- 部署后：`demo-check pre` 10/10（对账 12/12、权限矩阵 5/5）；7 个探针中 strict（3 天）、intersect（交集 5 天）、mixed（1 行）、or（`INTERNAL_ERROR: MetricFlow compile error: metric_time filters must be a single range joined with AND …`）按预期变化，其余 3 个不变；`demo-check post` 5/5，失败列表是 `flow` 故意触发的 2 个和 or 探针，都带 `error`（`execute_query` 不再是 `(not recorded)`），or 探针还带 `group_by`、`where`、`having`（P-10 实测）。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add dorismcp/agentcore/.cli/deployed-state.json specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
deploy(p5): T5.7a Runtime dorismcp version 3 with P-10, P-11 and the transitive pins

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望：`ticked: T5.7a`；`已创建的 AWS 资源 (version 2 -> version 3): written (… lines)`；`进行中`、`下一步` 各一行 `written`；日志一行 `### … P5 Task 6（T5.7a 部署）…: written`；`check-secrets: OK`；`0`；工作区干净，最后一行是这个提交的标题。日志里「（用户的原话）」「（实测）」两处换成实际的内容再执行。

---

### Task 7：T5.3 + T5.4：用户指南和演示手册（M-7），整体评审，导入 skills，彩排 2 轮

来源：design §9 的步骤 5（导入）、§10（演示脚本）、§11 P5 行，tasks.md T5.3、T5.4、T5.7b 的 M-7；P4 的做法（`quick/P4-guide.md` + `P4-handoff.md`，每个窗口前后 AI 做只读核对）。Step 1–2 由 AI 完成；Step 3–4 要等用户在 Quick 桌面版里操作，AI 只跑只读的 `demo-check pre` / `post`、核对答案、修挡路的问题。spec 阶段的发现：

| # | spec 阶段的发现 | 处理 | 测试 |
|---|---|---|---|
| 1 | 用户的桌面电脑不是开发机：skills 文件夹要先拷过去，指南里不能写主机名或 IP | 指南「准备」用 `scp -r <开发机>:…/quick/skills ./doris-skills`，`<开发机>` 由用户换成自己 SSH 用的名字 | `Hygiene` 2 个（没有 URL、IP、ARN、账号；每个 `doris___` 工具都在 Gateway 后面）|
| 2 | 指南、交接清单、手册各有一份问题、参照值或模板，改了一处容易漏掉另一处 | 问题和 design §10 逐字一致、顺序一致（指南和手册）；第 2 幕的两张参照表和 P4 指南相同；交接清单的两个模板是指南的副本 | `Questions` 3 个；`Setup` 的模板检查 |
| 3 | D7：彩排和演示时 `execute_query` 是 Always Allow，只有 `reload_semantic_layer` 弹窗；导入表要和 `quick/skills/` 的文件夹一致、adapter 先导入 | 指南 A3 的 12 行权限表、A1 的导入表 | `Setup` 的导入表、权限表（对照 `scripts/smoke_calls.json` 的 12 个工具）|
| 4 | M-7（P4 评审）：审计日志里的工具名不带 `doris___` 前缀，P4 读审计时被当成了问题 | 手册「演示后」写明这是正常的 | 手册的 6 个部分、每个要运行的脚本都存在（`Runbook` 2 个）|
| 5 | 模板 2 按桌面电脑的本地时间填，审计和 Gateway 耗时是 UTC；Gateway 每分钟一行，分不出哪次调用属于哪一步 | 模板 1 第一行记时区；每轮前 AI 记下开始时间（毫秒，写进 progress）；`/tmp/p5-steps.py` 把每分钟的行按 7 个发送时间分到步骤上（一分钟算给它之前最后发出的那一步）| Step 4 的示例（假的 `post` 输出）|
| 6 | 9 月只到 25 日，和去年 9 月整月比同比是 -0.44% | 指南给出同期同天数的参照值（+21.87%），回答指出这一点算好的回答；只给出小程序、合计行没有同比都不算失败 | 答案核对（Step 4）|
| 7 | 耗时表只能在两轮彩排之后填 | 手册「每步耗时」先放 7 行 `—`，Task 8 填写 | Task 8 Step 2 |

**Files:**
- Create: `quick/P5-guide.md`（用户指南：准备、Part A 导入 A1–A5、Part B 彩排 7 步和参照值、2 个回复模板）、`quick/P5-handoff.md`（交接清单）、`quick/runbook.md`（演示手册：演示前、设置、演示流程、出问题时、演示后、每步耗时）、`quick/test/test_p5_docs.py`（10 个）
- 辅助：`/tmp/p5-steps.py`（header 的「从计划取文件」已经取出，不进仓库）
- Test: `quick/test` 50 → 60；突变 docs 15 个

**Interfaces:**
- Consumes：design §10 的 7 个问题；`quick/P4-guide.md` 第 2 幕的两张表；`quick/skills/`（Task 1、2）；`scripts/smoke_calls.json`（12 个工具）；Task 5 的 `demo-check.sh pre` / `post --since MS --until MS` 和 `99-cleanup.sh`；Task 6 部署的 Runtime version 3。
- Produces：
  - 用户的回复（模板 1、每轮一份模板 2），AI 核对后写进 progress 日志；
  - `/tmp/p5-a-post.txt`、`/tmp/p5-r1-post.txt`、`/tmp/p5-r2-post.txt`（`demo-check post` 的输出，已经过脚本自己的 MASK）和 `p5-steps.py` 的每步汇总：Task 8 填耗时表、做决策时使用；
  - Task 8 要处理的事项清单（不挡路的问题、A4 的 scope、A5 的结果、2003 地址有没有出现）。

- [ ] **Step 1：指南、交接清单、手册（TDD）**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-extract.py quick/test/test_p5_docs.py
git status --short
```
期望（实测）：
```
quick/test/test_p5_docs.py -> quick/test/test_p5_docs.py (144 lines)
?? quick/test/test_p5_docs.py
```

新文件 `quick/test/test_p5_docs.py`：

<!-- file: quick/test/test_p5_docs.py sha256=e57f9831ff96c54534a74813cc2324cc90dea2ca0988207fdd61827eed053eba -->
````python
"""quick/P5-guide.md, quick/P5-handoff.md and quick/runbook.md: what the person at the desktop follows (P5).

The rehearsals (T5.4) and the demo are run by hand from these files, so these checks keep them consistent with
the rest of the repo: the questions are the ones of design §10, in order, in both the guide and the runbook; the
act 2 reference tables are the ones the P4 guide checked; every tool named exists behind the Gateway and the
permission table follows D7; the skills to import are exactly the folders under quick/skills/; the reply
templates in the handoff are copies of the guide's; every script the runbook runs exists; and nothing that must
not leave the repo is in them.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUICK = ROOT / "quick"
GUIDE = QUICK / "P5-guide.md"
HANDOFF = QUICK / "P5-handoff.md"
RUNBOOK = QUICK / "runbook.md"
P4_GUIDE = QUICK / "P4-guide.md"
SKILLS = QUICK / "skills"
GATEWAY_PREFIX = "doris___"  # <target>___<tool>, design §4.5
QUESTIONS = (  # design §10, verbatim and in order
    "检查一下 Doris 连接状态",
    "今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比",
    "618 和双 11 哪个类目贡献最大？",
    "最近哪家店的退款率异常？原因是什么？物流有没有问题？",
    "按天统计埋点 UV 这个查询为什么要这么久？给出 profile 证据",
    "评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL",
    "为 agg_daily_traffic 这类场景推荐数据模型",
)
ASK_EACH_TIME = {"reload_semantic_layer"}  # D7: execute_query is Always Allow for rehearsals and the demo
RUNBOOK_PARTS = ["演示前", "设置", "演示流程", "出问题时", "演示后", "每步耗时"]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(path: Path, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", _text(path), re.M | re.S)
    if match is None:
        raise AssertionError(f"{path.name}: no section '## {title}'")
    return match.group(1)


def _fenced(text: str) -> list[str]:
    return re.findall(r"^```\n(.*?)^```$", text, re.M | re.S)


def _table(text: str, header: str) -> list[str]:
    """The lines of the Markdown table whose header line starts with `header`."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    table = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        table.append(line)
    return table


def _gateway_tools() -> set[str]:
    calls = json.loads((ROOT / "scripts" / "smoke_calls.json").read_text(encoding="utf-8"))
    return {c["tool"] for c in calls}


def _in_order(text: str, items: tuple[str, ...]) -> bool:
    positions = [text.find(f"`{item}`") for item in items]
    return -1 not in positions and positions == sorted(positions)


class Questions(unittest.TestCase):
    def test_the_guide_asks_the_design_questions_in_order(self):
        self.assertTrue(_in_order(_section(GUIDE, "Part B：完整彩排 × 2"), QUESTIONS))

    def test_the_runbook_asks_the_same_questions_in_order(self):
        self.assertTrue(_in_order(_section(RUNBOOK, "演示流程"), QUESTIONS))

    def test_the_act_2_reference_tables_are_the_p4_ones(self):
        for header in ("| 月份 | GMV |", "| 渠道 | GMV |"):
            with self.subTest(header=header):
                self.assertEqual(_table(_text(GUIDE), header), _table(_text(P4_GUIDE), header))


class Setup(unittest.TestCase):
    def test_the_skills_to_import_are_the_folders_under_quick_skills(self):
        rows = re.findall(r"^\| (\d) \| `([a-z0-9-]+)` \|", _section(GUIDE, "Part A：导入 skills（T5.3）"), re.M)
        self.assertEqual([int(n) for n, _ in rows], list(range(1, len(rows) + 1)))
        self.assertEqual(rows[0][1], "doris-mcp-adapter")
        folders = {p.name for p in SKILLS.iterdir() if p.is_dir()}
        self.assertEqual({name for _, name in rows}, folders)
        for name in folders:
            self.assertTrue((SKILLS / name / "SKILL.md").is_file(), name)

    def test_the_permission_table_lists_every_tool_as_d7_says(self):
        rows = dict(re.findall(rf"^\| `{GATEWAY_PREFIX}(\w+)` \| ([A-Za-z ]+?) \|", _text(GUIDE), re.M))
        self.assertEqual(set(rows), _gateway_tools())
        for tool, permission in rows.items():
            with self.subTest(tool=tool):
                self.assertEqual(permission, "Ask Each Time" if tool in ASK_EACH_TIME else "Always Allow")

    def test_the_handoff_templates_are_copies_of_the_guides(self):
        guide = _fenced(_section(GUIDE, "回复模板"))
        self.assertEqual(len(guide), 2)
        self.assertEqual(_fenced(_section(HANDOFF, "做完后")), guide)


class Runbook(unittest.TestCase):
    def test_has_exactly_its_parts(self):
        self.assertEqual(re.findall(r"^## (.+)$", _text(RUNBOOK), re.M), RUNBOOK_PARTS)

    def test_every_script_it_runs_exists(self):
        paths = re.findall(r"(?:bash|python) ((?:scripts|infra|doris)/[\w./-]+)", _text(RUNBOOK))
        self.assertIn("scripts/demo-check.sh", paths)
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())


class Hygiene(unittest.TestCase):
    DOCS = (GUIDE, HANDOFF, RUNBOOK)

    def test_every_tool_named_exists_behind_the_gateway(self):
        tools = _gateway_tools()
        for path in self.DOCS:
            with self.subTest(doc=path.name):
                named = set(re.findall(rf"\b{GATEWAY_PREFIX}(\w+)", _text(path)))
                self.assertEqual(named - tools, set())

    def test_no_urls_addresses_arns_or_account_ids(self):
        for path in self.DOCS:
            text = _text(path)
            for pattern in (r"https?://", r"\b\d{1,3}(?:\.\d{1,3}){3}\b", r"\barn:aws", r"\b\d{12}\b",
                            r"amazonaws\.com"):
                with self.subTest(doc=path.name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, text))


if __name__ == "__main__":
    unittest.main()
````

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s quick/test > /tmp/t57-red.log 2>&1; echo "quick rc=$?"
grep -E '^(FAIL|ERROR):' /tmp/t57-red.log | sed -E 's/^(FAIL|ERROR): [A-Za-z0-9_]+ \(([A-Za-z0-9_.]+)\).*/\1 \2/' | sort
grep -hE '^(FileNotFoundError|AssertionError)' /tmp/t57-red.log | sed -E 's#/[^ ]*/quick/#quick/#' | sort | uniq -c
grep -E '^Ran |^OK|^FAILED' /tmp/t57-red.log
```
期望（实测，秒数每次不同）：
```
quick rc=1
ERROR test_p5_docs.Hygiene.test_every_tool_named_exists_behind_the_gateway
ERROR test_p5_docs.Hygiene.test_every_tool_named_exists_behind_the_gateway
ERROR test_p5_docs.Hygiene.test_every_tool_named_exists_behind_the_gateway
ERROR test_p5_docs.Hygiene.test_no_urls_addresses_arns_or_account_ids
ERROR test_p5_docs.Questions.test_the_act_2_reference_tables_are_the_p4_ones
ERROR test_p5_docs.Questions.test_the_act_2_reference_tables_are_the_p4_ones
ERROR test_p5_docs.Questions.test_the_guide_asks_the_design_questions_in_order
ERROR test_p5_docs.Questions.test_the_runbook_asks_the_same_questions_in_order
ERROR test_p5_docs.Runbook.test_every_script_it_runs_exists
ERROR test_p5_docs.Runbook.test_has_exactly_its_parts
ERROR test_p5_docs.Setup.test_the_handoff_templates_are_copies_of_the_guides
ERROR test_p5_docs.Setup.test_the_permission_table_lists_every_tool_as_d7_says
ERROR test_p5_docs.Setup.test_the_skills_to_import_are_the_folders_under_quick_skills
      8 FileNotFoundError: [Errno 2] No such file or directory: 'quick/P5-guide.md'
      1 FileNotFoundError: [Errno 2] No such file or directory: 'quick/P5-handoff.md'
      4 FileNotFoundError: [Errno 2] No such file or directory: 'quick/runbook.md'
Ran 60 tests in 0.171s
FAILED (errors=13)
```
失败的正是下面三个文档要满足的：13 个 `ERROR` 都是 `FileNotFoundError`，三个文档还不存在（`P5-guide.md` 8 次、`runbook.md` 4 次、`P5-handoff.md` 1 次）。失败的是 10 个检查，其中「每个工具名都在 Gateway 后面」有 3 个 subTest，「第二幕的对照表是 P4 的」有 2 个 subTest，所以记录是 13 个。`quick/test` 其余 50 个检查（`test_skills`、`test_adapter_skill`、`test_agent_instructions` 等）都通过。

失败的项目或个数不同时，先查明原因，再取出文档。

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
for f in quick/P5-guide.md quick/P5-handoff.md quick/runbook.md; do .venv/bin/python /tmp/p5-extract.py "$f"; done
for f in quick/P5-guide.md quick/P5-handoff.md quick/runbook.md; do printf '%s: ' "$f"; grep -cE 'https?://|\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b' "$f"; done
git status --short
```
期望（实测）：
```
quick/P5-guide.md -> quick/P5-guide.md (228 lines)
quick/P5-handoff.md -> quick/P5-handoff.md (76 lines)
quick/runbook.md -> quick/runbook.md (97 lines)
quick/P5-guide.md: 0
quick/P5-handoff.md: 0
quick/runbook.md: 0
?? quick/P5-guide.md
?? quick/P5-handoff.md
?? quick/runbook.md
?? quick/test/test_p5_docs.py
```

新文件 `quick/P5-guide.md`（第 2 幕的两张表和 P4 指南相同；第 3–7 步的参照值是 spec 阶段以 `demo_ro` 实测的）：

<!-- file: quick/P5-guide.md sha256=b11304399fd687db1f7eef43593dc44afcf9856904da69f899bd1b0983b9d26f -->
````markdown
# P5：导入 skills + 两轮完整彩排（T5.3 + T5.4）

> 本文件不包含任何 URL、secret 或 token。连接参数（MCP URL、Token URL、Authorize URL、client ID）见 `quick/T0.7-guide.md` 的「连接参数」。如果 Quick 要求重新登录，或者要求重新填 client secret / `demo` 用户的密码，按 T0.7 的「Step 2：取 secret」在**你自己的终端**里获取，不要用 Claude Code 的 `!` 前缀。

## 注意

- 不要把 URL、secret、token 或登录页的地址粘贴到对话里。
- 权限按 D7：彩排期间 `doris___execute_query` 是 Always Allow（不会弹窗），`doris___reload_semantic_layer` 是 Ask Each Time，弹窗一律拒绝。彩排结束后按 `quick/runbook.md` 的「演示后」改回。
- agent 建议的写操作（DDL、`ALTER`、`INSERT`、`KILL`、改配置）**一律不要执行**，照抄进回复模板。彩排不做第 1 幕（Stream Load）和第 7 幕建 MV：09-25 上午的订单已经在库里，集群保持现状，**不要删库重建**。
- 遇到 424、报错或意料之外的弹窗：记下时间、工具名和错误信息原文（先把其中的地址去掉），然后继续。同一个问题最多重发一次。
- 每一轮开始前，在对话里说「开始第 N 轮」，等 AI 回复「可以开始」：AI 先跑 `demo-check pre`（约 1.5 分钟）并记下开始时间。从这时起到你发回这一轮的回复之前，AI 不调用 Gateway 或 Runtime，审计日志和耗时里只有你的调用。
- 两轮之间只修挡路的问题（答不出、工具报错、答案和参照值对不上）；措辞和格式上的问题记下来，T5.5 统一处理。
- 预计：Part A 30–40 分钟；每一轮 30–45 分钟（7 个问题；每次工具调用 5–10 s，第 5 幕和 Track A 各要 5–12 次调用）。

## 准备

- 秒表（手机即可）和记事本；记下这台电脑的时区（回复模板第一行），AI 按 UTC 对日志。
- Quick 桌面版已登录。「Doris 专家」只关联 `Doris-Desktop-MCP`（P4 在网页版新建的连接器；桌面版里旧的 `doris-mcp` 刷新不了工具列表）。
- 把 skills 拷到这台电脑。在**你自己的终端**里执行（`<开发机>` 换成你平时 SSH 登录开发机用的主机名或别名）：

```
scp -r <开发机>:/home/ubuntu/AI-code/Doris-mcp-skill-Demo/quick/skills ./doris-skills
```

- 拷完后 `doris-skills` 下有 5 个文件夹和 3 个文件（`LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md`）。只导入 5 个文件夹，3 个文件不导入：`UPSTREAM.md` 记录了这些副本来自 apache/doris-skills 的哪个 commit、改了哪些地方，`LICENSE.txt` 是它的许可证。

## Part A：导入 skills（T5.3）

### A1 导入 5 个 skill

**Customize → Skills → From folder**，按下表的顺序逐个导入，每次选一个文件夹（每个都不到 1 MB，Quick 的上限是 6 MB）：

| 顺序 | 文件夹 | 作用 |
|---|---|---|
| 1 | `doris-mcp-adapter` | 本项目自写：把 doris-* skills 里的 doriscli 命令换成 `doris___*` 工具；只读边界；每次调用 60 s 的上限 |
| 2 | `doris-debug` | 故障诊断（慢查询、导入、Compaction、集群问题等）。**整个文件夹一次导入**，里面的子文件夹（`query`、`import`、`data-lake` 等）作为参考文件随它一起导入，不要单独导入 |
| 3 | `doris-profile-reader` | 解读 Query Profile |
| 4 | `doris-best-practices` | 建表、分区分桶、数据模型的最佳实践和 DDL 评审 |
| 5 | `doris-architecture-advisor` | 按业务场景推荐架构和数据模型 |

- 每导入一个，记下成功还是失败；失败时记下报错原文。Quick 里显示的 skill 名称应该和文件夹名一致。
- 如果 Quick 把 `doris-debug` 里的子文件夹也显示成单独的 skill（名字类似 `doris-debug-query`），记下来，不用处理。

### A2 更新 agent

1. 打开 agent「Doris 专家」的编辑页。
2. 指令：删掉原来的全文，粘贴仓库里 `quick/agent-instructions.md` 的新全文（约 2600 字符；可以在你自己的终端里 `cat quick/agent-instructions.md` 后复制，这个文件里没有 secret）。新版比 P4 多了几条：诊断类问题先加载 doris-mcp-adapter；可用的时间粒度；「同期同天数」怎么比；不要用 OR 连接几个时间范围。如果 Quick 提示指令太长，记下提示原文。
3. skills：挂上 A1 的 5 个 skill。如果 agent 的编辑页里没有选择 skill 的地方（skills 对所有 agent 生效），记「skills 是全局的」。
4. 连接器：只关联 `Doris-Desktop-MCP`，不变。
5. 备份 agent「Doris 专家（svc）」（关联 `doris-mcp-svc`）：同样替换指令、挂上 skills。再看一眼 `doris-mcp-svc` 在桌面版里显示几个 `doris___` 工具，记下数量；不是 12 个也不用修（P4 里桌面版的旧连接器刷新不了，备份走网页版）。

### A3 工具权限（D7：彩排和演示用的设置）

打开 `Doris-Desktop-MCP`，确认 12 个 `doris___` 工具都已启用，权限按下表（和 P4 相比，`doris___execute_query` 改为 Always Allow）：

| 工具 | 权限 |
|---|---|
| `doris___get_query_guide` | Always Allow |
| `doris___check_service_health` | Always Allow |
| `doris___list_databases` | Always Allow |
| `doris___list_tables` | Always Allow |
| `doris___describe_table` | Always Allow |
| `doris___execute_query` | Always Allow |
| `doris___list_metrics` | Always Allow |
| `doris___list_dimensions_for_metric` | Always Allow |
| `doris___query_metric` | Always Allow |
| `doris___reload_semantic_layer` | Ask Each Time |
| `doris___list_recent_queries` | Always Allow |
| `doris___get_query_profile` | Always Allow |

`doris-mcp-svc` 在桌面版如果也是 12 个工具，按同一张表设置。

### A4 scope（P0 评审 M-1，情况 c）

只在 Quick 要求登录时做（导入 skills、改 agent 或第一次提问时弹出登录页）：**先不要登录**，按 `quick/P4-guide.md` A2 的方法只从地址栏读三项：`scope=` 的值（`%20` 和 `+` 都是空格，`%2F` 是 `/`）、有没有 `resource=`（只记有或无）、`code_challenge_method=` 的值。记完再用 `demo` 用户登录。没有要求登录，就记「没有要求登录」。

### A5 adapter 会不会被自动选中

新建一个对话，选「Doris 专家」，问：`现在集群上有没有正在运行的慢查询？`

- 期望：Quick 选中 `doris-debug`（或 `doris-profile-reader`）和 `doris-mcp-adapter`；调用 `doris___execute_query` 执行 `SHOW PROCESSLIST`（adapter 里 `doriscli profile list --active` 的翻译），也可能再调用 `doris___list_recent_queries`；回答说明现在有没有长时间运行的查询。
- 不应该出现：让你去运行 `doriscli`、mysql 客户端或 curl；执行 `KILL`。
- 记：发送时间（hh:mm:ss）、总耗时、Quick 显示的 skills 和工具调用顺序、有没有让你去运行命令。

Part A 做完后，先用「回复模板」里的模板 1 回复我。AI 核对之后，再开始 Part B。

## Part B：完整彩排 × 2

每一轮这样做：

1. 在对话里说「开始第 N 轮」，等 AI 回复「可以开始」。
2. 新建一个对话，选「Doris 专家」，按顺序问下面 7 个问题；上一个回答完整显示后再问下一个。问题原样复制。
3. 每个问题记六项：
   - 发送时间（本地时间 hh:mm:ss）；
   - 总耗时：按下发送时开始秒表，答案完整显示后停，记秒数；
   - Quick 显示的 skills 和工具调用顺序，例如 `doris-mcp-adapter → execute_query → list_recent_queries → get_query_profile`；
   - 权限弹窗：应该只有 `doris___reload_semantic_layer` 会弹，一律拒绝；记下弹了几次；
   - 424 或其他报错：记原文（去掉其中的地址）；
   - 是否符合下面的期望：是 / 否（否的话一句话说明）。
4. 7 个问题都问完，用模板 2 回复我。AI 记下结束时间，跑 `demo-check post`（审计日志、Gateway 每分钟的耗时、连接数），对照参照值核对答案，然后告诉你能不能开始下一轮。

第 2 轮和第 1 轮问同样的 7 个问题，新建对话。

### 步骤 1（开场）：`检查一下 Doris 连接状态`

- 期望：调用 `doris___check_service_health`（可能再调用 `doris___list_databases`）；回答说明连接正常、版本 4.1；不出现主机地址、IP、端口、账号。

### 步骤 2（第 2 幕 经营大盘）：`今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比`

- 期望：先 `doris___list_metrics`，再 `doris___query_metric`（按月一次、按渠道一次，也可能合并或多一次）。先调用 `doris___list_dimensions_for_metric` 或 `doris___get_query_guide` 查维度也正常。
- 数字应该和下面的参照值一致（与 P4 相同，截至 2026-09-25；小数位数可以不同，按回答显示的位数对照）：

| 月份 | GMV | 订单数 | 客单价 | 去年同期 GMV | 同比 | 小程序占比 |
|---|---|---|---|---|---|---|
| 2026-01 | 7,986,117.85 | 5,753 | 1,388.17 | 5,211,027.86 | +53.25% | 30.82% |
| 2026-02 | 4,599,422.58 | 2,849 | 1,614.40 | 3,986,552.32 | +15.37% | 33.31% |
| 2026-03 | 6,391,853.90 | 4,526 | 1,412.25 | 5,397,104.03 | +18.43% | 32.26% |
| 2026-04 | 5,793,467.18 | 3,840 | 1,508.72 | 4,876,168.12 | +18.81% | 34.98% |
| 2026-05 | 8,039,374.11 | 5,029 | 1,598.60 | 6,164,787.89 | +30.41% | 31.58% |
| 2026-06 | 13,657,823.71 | 7,821 | 1,746.30 | 10,188,029.34 | +34.06% | 31.74% |
| 2026-07 | 6,630,639.04 | 4,305 | 1,540.22 | 5,718,799.51 | +15.94% | 32.81% |
| 2026-08 | 6,808,922.61 | 4,239 | 1,606.26 | 5,742,538.20 | +18.57% | 32.76% |
| 2026-09 | 5,754,567.17 | 4,633 | 1,242.08 | 5,780,111.92 | -0.44% | 32.10% |
| 合计 | 65,662,188.15 | 42,995 | 1,527.21 | 53,065,119.19 | +23.74% | 32.30% |

| 渠道 | GMV | 订单数 | GMV 占比 |
|---|---|---|---|
| APP | 28,956,861.86 | 19,045 | 44.10% |
| MINI_PROGRAM（小程序）| 21,209,275.57 | 13,831 | 32.30% |
| PC | 9,413,720.01 | 6,160 | 14.34% |
| H5 | 6,082,330.71 | 3,959 | 9.26% |

- 2026 年 9 月只到 25 日，而去年同期是 2025 年 9 月整月，所以 9 月同比偏低（-0.44%）。回答应该指出这一点。如果按同期同天数比（9 月 1–25 日对 2025 年 9 月 1–25 日），参照值是 5,754,567.17 对 4,721,825.63，同比 +21.87%。
- 渠道只给出小程序、没有列出其他渠道，不算失败；合计行没有同比和客单价，也不算失败。

### 步骤 3（第 3 幕 大促复盘）：`618 和双 11 哪个类目贡献最大？`

- 期望：先查 `ecom.dim_promotion` 拿到两个活动的起止日期（2026年618：05-26 至 06-18；2025年双11：2025-10-20 至 11-11），再用 `doris___query_metric`（`line_gmv` 按 `category__cat1_name`）或 `doris___execute_query` 按一级类目汇总商品行实付。
- 结论：618 是**家用电器**贡献最大（30.52%），双 11 是**手机数码**最大（26.04%）。
- 参照值（活动期内的商品行实付；每个活动取前 5 个类目）：

| 类目 | 2026年618 | 占比 |
|---|---|---|
| 家用电器 | 4,246,225.85 | 30.52% |
| 手机数码 | 3,792,443.46 | 27.26% |
| 电脑办公 | 2,200,281.81 | 15.82% |
| 美妆个护 | 950,662.85 | 6.83% |
| 食品生鲜 | 863,086.11 | 6.20% |
| 合计（12 个类目） | 13,910,841.80 | 100% |

| 类目 | 2025年双11 | 占比 |
|---|---|---|
| 手机数码 | 2,819,401.92 | 26.04% |
| 家用电器 | 1,924,179.64 | 17.77% |
| 美妆个护 | 1,347,724.62 | 12.45% |
| 电脑办公 | 1,203,259.02 | 11.11% |
| 食品生鲜 | 852,991.33 | 7.88% |
| 合计（12 个类目） | 10,827,037.71 | 100% |

- 如果 agent 取的时间范围不同（例如只看 6 月 18 日当天，或者用了 2025 年的 618），数字会不同：记下它用的范围，不算失败。

### 步骤 4（第 5 幕 问题排查）：`最近哪家店的退款率异常？原因是什么？物流有没有问题？`

- 期望：多次调用 `doris___execute_query`：店铺月度退款率对比自身过去 6 个月的基线（窗口函数），差评分词（TOKENIZE）和全文检索（MATCH_PHRASE），物流时效（PERCENTILE）。大约 5–12 次调用，总耗时 1–3 分钟。
- 参照：
  - 店铺：**深圳极速数码配件专营店**。2026-07 退款率 17.4%（184 件退 32 件，其中质量问题 29 件；自身基线 0.8%），2026-08 22.1%（231 件退 51 件，质量问题 49 件；基线 3.7%）。
  - 原因：差评里新出现「发烫」（0 → 52 次）和「充不进电」（0 → 39 次）；含「发烫」的 65 条评价全部来自这家店（平均评分 1.89）。含「坏了」的评价来自食品生鲜馆，是另一类问题，不要算到这家店头上。
  - 物流：极兔速递发往西北明显偏慢：425 单，平均 140.6 小时，P90 205.6 小时，80.7% 超过 4 天（韵达 P90 122.1 小时 / 47.8%）。按轨迹拆开，极兔的干线段 118.1 小时（顺丰 42.1、京东 25.4），问题在干线。
- agent 可能只答到退款率和原因，物流给得比较粗（例如只给平均时长）：记下它给了什么，不算失败。

### 步骤 5（第 7 幕 + Track A）：`按天统计埋点 UV 这个查询为什么要这么久？给出 profile 证据`

- 期望：Quick 选中 `doris-mcp-adapter` 和 `doris-profile-reader`（或 `doris-debug`）。按 adapter 的做法带 profile 执行：`doris___execute_query`（SQL 里有 `SET_VAR(enable_profile=true)` 和 `/* trace:… */`）→ `doris___list_recent_queries`（按 trace 找 query_id）→ `doris___get_query_profile`（结果被截断时，会带 `max_chars=60000` 再调用一次）。
- 参照：`ecom.fact_user_event` 有 102 万行、135 天；UV 最高的一天是 2026-06-18（3,873）。spec 阶段实测，这条查询在 Doris 里的 profile `Total` 是 46 ms（Plan 3 ms、Schedule 9 ms、Fetch Result 32 ms）。
- 好的回答：引用 profile 里的 `Total` 等数字，说明查询本身在 Doris 里只要几十毫秒，等待主要花在工具调用上（每次 5–10 s）；可以建议用预聚合（`agg_daily_traffic` 的 `uv_bitmap`）或物化视图。不应该编造 profile 里没有的瓶颈。
- 不应该出现：让你去运行 `doriscli profile`；执行 `SET` 语句。

### 步骤 6（Track B 设计评审）：`评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL`

- 期望：Quick 选中 `doris-best-practices`（和 `doris-mcp-adapter`）；调用 `doris___execute_query` 执行 `SHOW CREATE TABLE`、`SHOW PARTITIONS`，可能还有 `SHOW DATA SKEW`、`SHOW TABLE STATS`。
- 参照（实际的建表）：DUPLICATE KEY(event_date, event_time, user_id)；按天自动分区（AUTO PARTITION BY RANGE(date_trunc(event_date, 'day'))），现在 135 个分区（2026-05-14 至 2026-09-25）；DISTRIBUTED BY HASH(user_id) BUCKETS 2，共 270 个 tablet，只有约 102 万行；`props` 是 VARIANT；`search_keyword` 上有倒排索引；单副本。
- 好的回答：指出分区和 tablet 太多、每个 tablet 太小（例如建议按月分区，或减少分桶）；对 VARIANT 给出看法；给出改进的 DDL（新建表 + `INSERT INTO … SELECT` 迁移）并说明由人工执行。
- **不要执行** agent 给出的 DDL；照抄进模板 2（如果很长，只抄 `CREATE TABLE` 那一行和分区、分桶的子句）。

### 步骤 7（收尾）：`为 agg_daily_traffic 这类场景推荐数据模型`

- 期望：Quick 选中 `doris-architecture-advisor`（可能还有 `doris-best-practices`）；可能先 `SHOW CREATE TABLE ecom.agg_daily_traffic` 看现状。
- 参照：`agg_daily_traffic` 已经存在，是 AGGREGATE KEY(event_date, channel, event_type)：`pv` SUM、`uv_bitmap` BITMAP_UNION、`uv_hll` HLL_UNION、`last_event` MAX；4,927 行。
- 好的回答：推荐（或确认）聚合模型 + BITMAP_UNION / HLL_UNION 算 UV，说明取舍；可能提到物化视图作为替代；给出 DDL 并说明由人工执行。
- **不要执行** agent 给出的 DDL。

## 回复模板

复制下面的模板，填好发给我：Part A 做完发模板 1，每一轮做完发一次模板 2。不要包含任何 URL、secret 或 token。

模板 1（Part A）：

```
时区：
A1 导入：doris-mcp-adapter __；doris-debug __；doris-profile-reader __；doris-best-practices __；doris-architecture-advisor __（成功 / 失败 + 报错原文）
A1 子文件夹显示成单独的 skill：是 / 否（名字：）
A2「Doris 专家」：指令已替换（是 / 否，提示：）；skills：挂上 5 个 / skills 是全局的 / 其他：____；连接器只有 Doris-Desktop-MCP（是 / 否）
A2「Doris 专家（svc）」：已更新（是 / 否）；doris-mcp-svc 在桌面版的工具数：__
A3 Doris-Desktop-MCP 工具数：__；权限已按表设置（是 / 否，差异：）
A4 登录：没有要求登录 / scope=____；resource：有 / 无；code_challenge_method=____（或：看不到地址）
A5：发送 hh:mm:ss，__ s；skills：____；工具：____；让我去运行命令：是 / 否
其他观察：

A5 答案全文（其中如有主机地址、IP、端口、账号等连接信息，换成 <已遮盖>）：
```

模板 2（每一轮）：

```
第 __ 轮
步骤 1 开场：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 2 第 2 幕：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 3 第 3 幕：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 4 第 5 幕：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 5 Track A：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 6 Track B：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 7 收尾：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
agent 建议人工执行的语句（照抄，一条一行；没有就写「无」）：
重发过的问题（步骤号和原因；没有就写「无」）：
其他观察：

答案全文（7 段；其中如有主机地址、IP、端口、账号等连接信息，换成 <已遮盖>）：
```
````

新文件 `quick/P5-handoff.md`（「做完后」的两个模板是指南「回复模板」的副本，测试逐字比较）：

<!-- file: quick/P5-handoff.md sha256=c434b2ddcd6ea132f79cfb414a139544387df3268f605698a12551bdf1d560c9 -->
````markdown
# P5 交接：导入 skills + 两轮完整彩排（T5.3 + T5.4）

> 本文件不含任何 URL、secret 或 token。详细步骤见 `quick/P5-guide.md`，本文件只是摘要和清单。

## 当前状态

- **已完成（AI 侧）**：
  - `quick/skills/` 里有 5 个 skill：自写的 `doris-mcp-adapter`，以及从 apache/doris-skills 锁定 commit 生成的 4 个副本（`UPSTREAM.md` 记录了来源和改动）。
  - `quick/agent-instructions.md` 更新了：诊断类问题先加载 adapter；时间粒度；「同期同天数」怎么比；不要用 OR 连接几个时间范围。
  - Runtime 已重新部署：审计日志会记下失败的原因和 `query_metric` 的过滤条件；`metric_time` 的过滤条件修好了（按天的范围、`>` / `<`、多个条件取交集；用 OR 连接会报错并提示改法）。
  - 整体评审（opus）的结果和处理见 `specs/doris-mcp-quick/progress.md` 的最新一条日志。
- **每一轮开始前**：你说「开始第 N 轮」，AI 跑 `demo-check pre`（约 1.5 分钟），把结果和开始时间（UTC）告诉你，再回复「可以开始」。

## 要做的事

打开 `quick/P5-guide.md`（可以在你自己的终端里 `less quick/P5-guide.md` 查看），按顺序做：

- [ ] **准备**：在你自己的终端里用 `scp` 把 `quick/skills` 拷到这台电脑（命令见指南「准备」）。
- [ ] **Part A**：导入 skills（T5.3）
  - [ ] A1：按顺序导入 5 个文件夹：`doris-mcp-adapter`、`doris-debug`（整个文件夹一次导入）、`doris-profile-reader`、`doris-best-practices`、`doris-architecture-advisor`。`LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md` 不导入。
  - [ ] A2：「Doris 专家」换上 `quick/agent-instructions.md` 的新全文，挂上 5 个 skill，连接器只有 `Doris-Desktop-MCP`；备份「Doris 专家（svc）」同样更新。
  - [ ] A3：12 个 `doris___` 工具按指南的表设置权限（D7：`doris___execute_query` 改为 Always Allow，`doris___reload_semantic_layer` 仍是 Ask Each Time）。
  - [ ] A4：只有弹出登录页时才做：先不要登录，从地址栏读 `scope=`、有没有 `resource=`、`code_challenge_method=`。
  - [ ] A5：新对话问 `现在集群上有没有正在运行的慢查询？`，看 adapter 有没有被选中。
  - [ ] 用模板 1 回复我，等 AI 核对。
- [ ] **Part B**：完整彩排 × 2（T5.4），每一轮：
  - [ ] 说「开始第 N 轮」，等 AI 回复「可以开始」。
  - [ ] 新对话，按顺序问 7 个问题（指南 Part B），每个问题记六项（发送时间、总耗时、skills 和工具、弹窗、424 / 报错、是否符合期望）。
  - [ ] 用模板 2 回复我，等 AI 跑完 `demo-check post` 并核对答案。

预计 Part A 30–40 分钟，每一轮 30–45 分钟。中途有问题可以随时问我。

## 注意

- 不要把 URL、secret、token 或登录页的地址粘贴到对话里。
- Quick 要求重新填 client secret 或 `demo` 密码时，按 `quick/T0.7-guide.md` 的「Step 2：取 secret」在**你自己的终端**里获取，不要用 Claude Code 的 `!` 前缀。
- agent 建议的 DDL、`ALTER`、`KILL` 等写操作一律不要执行，照抄进模板 2。不要删库重建，也不要做第 1 幕和第 7 幕的写入。
- `doris___reload_semantic_layer` 的弹窗一律拒绝。
- 遇到 424、报错或意料之外的弹窗：记下时间、工具名和错误信息原文（先把其中的地址去掉），然后继续。同一个问题最多重发一次。
- 两轮之间 AI 只修挡路的问题；其他问题记下来，T5.5 统一处理。

## 做完后

Part A 做完发模板 1，每一轮做完发一次模板 2（下面是 `quick/P5-guide.md`「回复模板」的副本）：

```
时区：
A1 导入：doris-mcp-adapter __；doris-debug __；doris-profile-reader __；doris-best-practices __；doris-architecture-advisor __（成功 / 失败 + 报错原文）
A1 子文件夹显示成单独的 skill：是 / 否（名字：）
A2「Doris 专家」：指令已替换（是 / 否，提示：）；skills：挂上 5 个 / skills 是全局的 / 其他：____；连接器只有 Doris-Desktop-MCP（是 / 否）
A2「Doris 专家（svc）」：已更新（是 / 否）；doris-mcp-svc 在桌面版的工具数：__
A3 Doris-Desktop-MCP 工具数：__；权限已按表设置（是 / 否，差异：）
A4 登录：没有要求登录 / scope=____；resource：有 / 无；code_challenge_method=____（或：看不到地址）
A5：发送 hh:mm:ss，__ s；skills：____；工具：____；让我去运行命令：是 / 否
其他观察：

A5 答案全文（其中如有主机地址、IP、端口、账号等连接信息，换成 <已遮盖>）：
```

```
第 __ 轮
步骤 1 开场：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 2 第 2 幕：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 3 第 3 幕：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 4 第 5 幕：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 5 Track A：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 6 Track B：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
步骤 7 收尾：发送 hh:mm:ss，__ s；skills：____；工具：____；弹窗：__；424 / 报错：；符合期望：
agent 建议人工执行的语句（照抄，一条一行；没有就写「无」）：
重发过的问题（步骤号和原因；没有就写「无」）：
其他观察：

答案全文（7 段；其中如有主机地址、IP、端口、账号等连接信息，换成 <已遮盖>）：
```

收到模板 1 后，AI 核对导入结果和 A5 的回答，必要时改 adapter 或指令，再告诉你能不能开始 Part B。收到模板 2 后，AI 记下结束时间，跑 `demo-check post`（审计日志、每分钟的 Gateway 耗时、连接数），对照指南里的参照值核对答案，把每一步的耗时记进 progress。两轮都做完后，AI 按结果做 T5.5（修问题、写 `quick/runbook.md` 的耗时表、四项决策），再提交。
````

新文件 `quick/runbook.md`（「每步耗时」由 Task 8 填写）：

<!-- file: quick/runbook.md sha256=904276a45d4bdc8196a4ac68491cc80241c7dc04b24f3160f5f9aa1b728af8ed -->
````markdown
# 演示手册：Doris MCP × Amazon Quick 桌面版

> 本文件不含任何 URL、secret 或 token。连接参数见 `quick/T0.7-guide.md`；secret 只在你自己的终端里获取，不要用 Claude Code 的 `!` 前缀。
> 问题和参照值来自 design §10 和 `quick/P5-guide.md` Part B；「每步耗时」来自两轮彩排（T5.4）。

## 演示前

1. 演示前 30 分钟以内，在开发机的仓库根目录运行预检（只读，约 1.5 分钟）：

   ```
   bash scripts/demo-check.sh pre
   ```

   每项一行 `[PASS]` / `[FAIL]`，最后一行是 `demo-check pre: N/M passed`；有 `[FAIL]` 时退出码是 1。检查的内容：AWS 账号；Gateway 和 target 是 READY；能取到 Gateway token；经 Gateway 列出 12 个工具；经 Gateway 跑一遍 profile 流程（带 profile 执行一条查询 → 按 trace 找到 query_id → 读 profile）和 3 个错误用例（非法的 query_id、不存在的 query_id、`DELETE` 被拒绝）；对账（语义层的数和手写 SQL 一致）；`mcp_svc` 的权限；`mcp_svc` 的连接数（不超过 80）。
   只有一项 `[FAIL]` 时先重跑一次：spec 阶段连续 3 次预检里有 2 次各有 1 项偶发失败（Runtime 返回 502，或冷启动慢到 Gateway 报错），重跑就通过了。同一项连续两次 `[FAIL]`，先看「出问题时」，不要开始演示。
2. 记下预检结束的时间（`date +%s%3N`，毫秒），演示后要用。预检和演示之间不要再跑别的脚本，这样审计日志里只有演示的调用。
3. Quick 桌面版：
   - 已登录；「Doris 专家」的指令是 `quick/agent-instructions.md` 的全文，挂着 5 个 skill（`doris-mcp-adapter`、`doris-debug`、`doris-profile-reader`、`doris-best-practices`、`doris-architecture-advisor`），只关联 `Doris-Desktop-MCP`。
   - `Doris-Desktop-MCP` 有 12 个 `doris___` 工具，权限按「设置」。
   - 新建一个对话，先不提问。
4. 数据：第 1 幕（Stream Load 实时写入）和第 7 幕建 MV 是写操作，由演示者在 Quick 之外人工执行，Quick 只读结果。`quick/P5-guide.md` 的参照值是 09-25 上午的订单已经导入之后的数；如果删库重建，9 月（第 2 幕）会少掉当天的订单，参照值要重新算。

## 设置

- 工具权限（D7）：彩排和演示时 `doris___execute_query` 是 Always Allow（不弹窗，省下每次的确认时间），`doris___reload_semantic_layer` 是 Ask Each Time（弹窗一律拒绝），其余 10 个工具是 Always Allow。完整的表见 `quick/P5-guide.md` A3。其他时间把 `doris___execute_query` 改回 Ask Each Time（见「演示后」）。
- 连接器：`Doris-Desktop-MCP`（User auth，`demo` 用户）。桌面版不能刷新已有连接器的工具列表：如果工具数不是 12，或者工具调用返回 HTTP 400「参数无效」，在**网页版**新建一个连接器（参数见 `quick/T0.7-guide.md`），再在桌面版把 agent 改为关联新连接器。
- skills：从仓库的 `quick/skills/` 按文件夹导入（`doris-debug` 整个文件夹一次导入）；`LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md` 不导入。改了 skill 要重新导入。
- 指令：`quick/agent-instructions.md` 全文。
- 备份：「Doris 专家（svc）」关联 `doris-mcp-svc`（Service auth，不需要登录）。桌面版的旧连接器刷新不了工具列表，备份在**网页版**使用。

## 演示流程

每个问题等上一个回答完整显示后再问；问题原样复制。「预计」按每次工具调用 5–10 s 估算，彩排实测见「每步耗时」。

| 步骤 | 段落 | 问题 | 看点 / 要讲的 | 预计 |
|---|---|---|---|---|
| — | 第 1 幕 | （演示者在 Quick 之外做 Stream Load 实时写入，不经过 MCP） | 写 = 人工，读 = MCP | — |
| 1 | 开场 | `检查一下 Doris 连接状态` | 连接正常、版本 4.1；回答里没有主机地址、账号 | 10–20 s |
| 2 | 第 2 幕 经营大盘 | `今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比` | 语义层（`list_metrics` → `query_metric`）；先调用 `get_query_guide` / `list_dimensions_for_metric` 是正常的（P4 评审 M-3）；9 月只到 25 日，同比要按同天数看（+21.87%）；小程序占比 32.30% | 40–90 s |
| 3 | 第 3 幕 大促复盘 | `618 和双 11 哪个类目贡献最大？` | 618 家用电器第一（30.52%），双 11 手机数码第一（26.04%）；活动日期来自 `dim_promotion` | 40–90 s |
| 4 | 第 5 幕 问题排查 | `最近哪家店的退款率异常？原因是什么？物流有没有问题？` | 深圳极速数码配件专营店；差评「发烫」「充不进电」（倒排索引、TOKENIZE、MATCH_PHRASE）；极兔发西北的干线慢（PERCENTILE） | 1–3 min |
| 5 | 第 7 幕 + Track A | `按天统计埋点 UV 这个查询为什么要这么久？给出 profile 证据` | adapter + profile-reader；带 profile 执行 → 按 trace 找 query_id → 读 profile；Doris 里只要几十毫秒，时间花在工具调用上 | 1–2 min |
| — | 第 7 幕 | （演示者在 Quick 之外建 MV，不经过 MCP） | 写 = 人工 | — |
| 6 | Track B 设计评审 | `评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL` | best-practices；按天分区 135 个、BUCKETS 2 共 270 个小 tablet；DDL 只给出，不执行 | 1–2 min |
| 7 | 收尾 | `为 agg_daily_traffic 这类场景推荐数据模型` | architecture-advisor；聚合模型 + BITMAP_UNION / HLL_UNION；DDL 由人工执行 | 40–90 s |

## 出问题时

- **424 或工具报错**：Quick 等单次工具调用有上限（约 60 s）。让 agent 缩小范围（加时间范围、`LIMIT`、先 `EXPLAIN`），重发一次；还不行就跳过这一步，讲 `quick/P5-guide.md` 里的参照值。
- **回答里出现 Doris 主机地址或 IP**（例如 2003 连接错误的原文）：不要念出来；录屏的话剪掉这一段。演示后告诉 AI，按 design §14 处理。
- **弹出 `doris___reload_semantic_layer` 的权限窗口**：拒绝，让 agent 不重载继续回答。
- **agent 让你去运行 `doriscli`、mysql 客户端或 curl**：回复「这里没有命令行，只能用 Doris MCP 工具，按 doris-mcp-adapter 的对照表来」。
- **agent 要执行写操作（DDL、`KILL`、`SET`）**：工具会拒绝；让它把语句写出来，说明由人工执行。
- **连接器失效、要求重新登录或工具数不对**：先切到备份「Doris 专家（svc）」（网页版）；演示后按「设置」新建连接器。
- **怀疑后端有问题**：在开发机上重跑 `bash scripts/demo-check.sh pre`，看哪一项 `[FAIL]`。

## 演示后

1. 记下演示结束的时间（`date +%s%3N`），在开发机上运行（只读）：

   ```
   bash scripts/demo-check.sh post --since <预检结束的毫秒数> --until <演示结束的毫秒数>
   ```

   输出：审计日志里这段时间每个工具的调用次数和成败，再逐条列出失败的调用（时间、工具、错误原因；`query_metric` 还有它的 `group_by` / `where` / `having`）。审计日志里的工具名不带 `doris___` 前缀，这是正常的（P4 评审 M-7）。然后是 Gateway 每分钟、每个工具的调用数和耗时（≥ 45 s 标 WARN，≥ 60 s 算失败），以及 `mcp_svc` 当前的连接数。
2. 在 Quick 里把 `doris___execute_query` 改回 Ask Each Time（D7）。
3. 演示全部结束、不再需要这套环境时（T5.6）：
   - AWS 侧：先 dry-run，看清要删的资源：

     ```
     bash infra/99-cleanup.sh
     ```

     确认之后（GATE，一次确认只对应这一次）才执行 `APPLY=1 bash infra/99-cleanup.sh`。它按顺序删除 Gateway target、Gateway、Runtime 的栈、Interface endpoints（持续计费）、Cognito、secret、Doris SG 上引用 Runtime SG 的规则、本项目的 SG 和两个 IAM 角色；`infra/state.env` 保留，作为删了什么的记录。
   - Doris 侧（可选，单独确认）：`mcp_svc` 账号和语义层的库 `system_mcp` 不会被 `99-cleanup.sh` 删除。如果以后不再演示，由你用 root 在自己的 mysql 客户端里执行下面两句（AI 不执行）：

     ```
     DROP USER IF EXISTS 'mcp_svc'@'172.31.%';
     DROP DATABASE IF EXISTS system_mcp;
     ```

     `ecom` 的数据和 `demo_ro` 账号不受影响。以后要再演示，需要重新走 P2（发布语义层）和 P3（建账号）。
   - Quick 侧：连接器、agent 和 skills 由你在 Quick 里删除（可选）。

## 每步耗时

两轮彩排（T5.4）实测，单位秒；由 T5.5 根据彩排回复填写。「工具调用」是 Gateway 记录的这一步的调用次数。

| 步骤 | 段落 | 第 1 轮 | 第 2 轮 | 工具调用 | 单次最长 |
|---|---|---|---|---|---|
| 1 | 开场 | — | — | — | — |
| 2 | 第 2 幕 | — | — | — | — |
| 3 | 第 3 幕 | — | — | — | — |
| 4 | 第 5 幕 | — | — | — | — |
| 5 | 第 7 幕 + Track A | — | — | — | — |
| 6 | Track B | — | — | — | — |
| 7 | 收尾 | — | — | — | — |
````

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s quick/test 2>&1 | tail -3                                  # 期望：Ran 60 tests … OK
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json docs; echo "rc=$?"
git status --short
```
期望（实测，秒数每次不同）：
```
Ran 60 tests in 0.172s

OK
docs1 guide question 3 reworded: caught by test_the_guide_asks_the_design_questions_in_order (Ran 10, FAILED (failures=1))
docs2 runbook question 6 reworded: caught by test_the_runbook_asks_the_same_questions_in_order (Ran 10, FAILED (failures=1))
docs3 guide monthly reference differs from P4: caught by test_the_act_2_reference_tables_are_the_p4_ones (Ran 10, FAILED (failures=1))
docs4 guide channel reference differs from P4: caught by test_the_act_2_reference_tables_are_the_p4_ones (Ran 10, FAILED (failures=1))
docs5 adapter not imported first: caught by test_the_skills_to_import_are_the_folders_under_quick_skills (Ran 10, FAILED (failures=1))
docs6 a skill folder missing from the import table: caught by test_the_skills_to_import_are_the_folders_under_quick_skills (Ran 10, FAILED (failures=1))
docs7 reload_semantic_layer Always Allow: caught by test_the_permission_table_lists_every_tool_as_d7_says (Ran 10, FAILED (failures=1))
docs8 execute_query back to Ask Each Time: caught by test_the_permission_table_lists_every_tool_as_d7_says (Ran 10, FAILED (failures=1))
docs9 a tool missing from the permission table: caught by test_the_permission_table_lists_every_tool_as_d7_says (Ran 10, FAILED (failures=1))
docs10 handoff template diverges: caught by test_the_handoff_templates_are_copies_of_the_guides (Ran 10, FAILED (failures=1))
docs11 runbook part renamed: caught by test_has_exactly_its_parts (Ran 10, FAILED (failures=1))
docs12 runbook runs a script that does not exist: caught by test_every_script_it_runs_exists (Ran 10, FAILED (failures=1))
docs13 a tool that is not behind the Gateway: caught by test_every_tool_named_exists_behind_the_gateway (Ran 10, FAILED (failures=1))
docs14 an address in the runbook: caught by test_no_urls_addresses_arns_or_account_ids (Ran 10, FAILED (failures=1))
docs15 a third reply template: caught by test_the_handoff_templates_are_copies_of_the_guides (Ran 10, FAILED (failures=1))
15/15 mutations caught; tree unchanged: True
rc=0
?? quick/P5-guide.md
?? quick/P5-handoff.md
?? quick/runbook.md
?? quick/test/test_p5_docs.py
```

T5.7b 到这里全部完成（M-7 写进了手册「演示后」），勾选：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - T5.7b <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
echo 'Task 7 Step 1（指南、交接清单、手册）已提交；Step 2（整体评审）从头开始' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo 'Task 7 Step 2（整体评审，opus），然后 Step 3（用户导入 skills，模板 1）、Step 4（彩排 2 轮，模板 2）；Task 8（T5.5）、Task 9（演示结束后清理，GATE）' | .venv/bin/python /tmp/p5-progress.py state 下一步
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 7 Step 1：用户指南、交接清单、演示手册（M-7）

- `quick/P5-guide.md`：准备（`scp` 拷 `quick/skills`）；Part A 导入 5 个 skill（adapter 先导入，`doris-debug` 整个文件夹一次导入）、更新两个 agent、D7 权限表、A4 scope（只在要求登录时读地址栏）、A5 adapter 会不会被自动选中；Part B 彩排 7 步，每步的期望、参照值（第 2 幕和 P4 相同；9 月同期同天数 +21.87%）和不算失败的情况；2 个回复模板（模板 1 记时区）。
- `quick/P5-handoff.md`：摘要和清单，模板是指南的副本。
- `quick/runbook.md`：演示前（`demo-check pre`，只有一项失败时重跑一次）、设置、演示流程、出问题时、演示后（`demo-check post`；M-7：审计里的工具名不带 `doris___` 前缀是正常的；D7 权限改回；T5.6 清理和 Doris 侧的两句 DROP 由用户执行）、每步耗时（Task 8 填写）。
- RED：13 个 `ERROR`（10 个检查，有的带 subTest），都是 `FileNotFoundError`（3 个文档还不存在），`quick/test` 其余 50 个通过。
- GREEN：`quick/test` 60；突变 docs 15/15 被抓到。T5.7b 勾选（M-7–M-10 全部完成）。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add quick/P5-guide.md quick/P5-handoff.md quick/runbook.md quick/test/test_p5_docs.py \
        specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
docs(p5): P5 guide, handoff and runbook (M-7), with consistency checks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望（实测）：
```
ticked: T5.7b
进行中: written (785 lines)
下一步: written (785 lines)
### 2026-09-28 P5 Task 7 Step 1：用户指南、交接清单、演示手册（M-7）: written (793 lines)
check-secrets: OK (853 files scanned)
0
docs(p5): P5 guide, handoff and runbook (M-7), with consistency checks
```

- [ ] **Step 2：整体评审（opus）**

代码、部署和指南都完成了，交给用户之前评审整个分支。先生成评审材料：分支上的全部提交，除去 upstream 的 4 个副本（由 `build_skills.py --check` 和整棵树的 sha256 核对，Task 1）和本计划本身；经 MASK，新增行的 IP 计数必须是 0：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
source infra/state.env
X=(':!quick/skills/doris-debug' ':!quick/skills/doris-profile-reader' ':!quick/skills/doris-best-practices' ':!quick/skills/doris-architecture-advisor' ':!quick/skills/LICENSE.txt' ':!specs/doris-mcp-quick/plans/P5-skills.md')
{ git log --oneline main..HEAD | cut -c9-; echo; git diff --stat=160 main..HEAD | tail -1; echo; git diff -U10 main..HEAD -- . "${X[@]}"; } > /tmp/p5-review.txt
sed -E -i "$MASK" /tmp/p5-review.txt
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then grep -cF -f <(printf '%s\n' "$v") /tmp/p5-review.txt; else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
wc -l < /tmp/p5-review.txt; grep -c '^diff --git' /tmp/p5-review.txt
sed -n '1,/^$/p' /tmp/p5-review.txt
```
期望（回放时实测，Task 6 的提交在回放中没有部署；执行时提交标题相同，行数会因 `deployed-state.json` 多几行）：
```
0
5777
39
docs(p5): P5 guide, handoff and runbook (M-7), with consistency checks
deploy(p5): T5.7a Runtime dorismcp version 3 with P-10, P-11 and the transitive pins
fix(p5): pin botocore, rich-rst and sse-starlette to the tested .venv so the CodeZip matches it (P-07)
feat(p5): demo-check.sh pre/post, 99-cleanup.sh (dependency order, checks before the first delete), 30-gateway.sh GW_EXCEPTION_LEVEL and shared create/update args, check-secrets.sh skips deleted secrets
feat(p5): T5.7b audit_check --failures, gw_latency UTC minutes and merged series (M-9), mcp_smoke masks stdio URLs and hosts (M-8)
feat(p5): T5.7a P-10 audit error and query_metric filters, P-11 metric_time filters (OR, strict bounds, intersection, groups)
feat(p5): T5.2 doris-mcp-adapter skill, instruction 5 and time-grain framing, reconcile yoy_same_days_2026_09
feat(p5): T5.1 quick/skills copies of apache/doris-skills 0476f3b from scripts/build_skills.py; check-secrets placeholders
docs(p5): P5 plan, design v0.8 (P-10, P-11, cleanup order, skills import), tasks T5.1-T5.7b
```

派一个 **Opus 5.5** 的 subagent（`superpowers:requesting-code-review` 的 code-reviewer 模板），给它：`/tmp/p5-review.txt`、本计划（只读，路径 `specs/doris-mcp-quick/plans/P5-skills.md`）、`specs/doris-mcp-quick/design.md` v0.8、本计划的 Review Focus 5 条，以及前面任务记下的未解决 Minor（Task 5：`TOKEN_CMD` 的默认值不看 `STATE_FILE`，`99-cleanup.sh` 少数「已经不存在」的分支只在离线测试里走过；Task 4 的日志里如果还有，一并给）。要求：
- 每个问题标 Critical / Important / Minor，给出文件和行、会怎样出错、建议的改法；最后一行 `Ruling: ready` 或 `Ruling: not ready`；
- 可以在仓库里读文件、跑离线测试（上面「常用测试命令」），**不访问 AWS、Doris、凭证文件**（`check-secrets.sh` 也不跑），不执行 `APPLY=1` 或部署，不改文件、不提交；
- 特别看：新的输出会不会泄漏地址、URL 或 token（Review Focus 1）；`99-cleanup.sh` 的检查是否都在第一次删除之前（Review Focus 5）；adapter 的翻译有没有让 agent 去运行命令（Review Focus 3）；P-11 有没有改掉对账和演示依赖的行为（Review Focus 4）。

处理：
- Critical / Important：逐个先写一个失败的测试（RED）→ 修 → 全部测试（「常用测试命令」）和相关的突变组通过 → 提交 `fix(p5): …`（每个提交前照常跑 `check-secrets.sh` 和 IP 计数）。改了 `mcp-server/src/` 的，要按 Task 6 Step 3–6 再部署一次（GATE，version 4）；改了 skills 或指南的，还没有交给用户，不用重新导入；改了 `build_skills.py` 的常量，重新生成并在日志里写下新的整棵树 sha256。
- Minor：不改，记进下面的日志，Task 8 统一决定。
- 评审给出 `Ruling: not ready` 而修完之后，把修过的部分再给同一个 reviewer 看一次（SendMessage），直到 `ready`。

记录评审结果并提交（「（…）」换成实际的内容；没有 Critical / Important 就写「无」）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
echo 'Task 7 Step 2（整体评审）已完成；Step 3（用户导入 skills）从头开始' | .venv/bin/python /tmp/p5-progress.py state 进行中
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 整体评审（opus）

- 范围：`main..p5-skills` 的全部提交（除去 upstream 的 4 个副本和计划本身），经 MASK，IP 计数 0。
- 结论：（Ruling）。Critical / Important：（每条一行：问题 → 处理和提交；没有就写「无」）。
- Minor（Task 8 决定）：（每条一行）。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
docs(p5): overall review (opus) results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
rm -f /tmp/p5-review.txt
```
期望：`进行中`、日志各一行 `written`；`check-secrets: OK`；`0`；工作区干净。

- [ ] **Step 3：Part A：用户导入 skills（T5.3）**

先确认后端正常（只读，约 1.5 分钟；和 Task 6 Step 6 的 `pre` 相同，10 项 `[PASS]`）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
bash scripts/demo-check.sh pre; echo "exit=$?"
```
只有一项 `[FAIL]` 时重跑一次；同一项连续两次失败，先查原因，不交给用户。

记下 Part A 的开始时间（毫秒；`sleep 5` 让 `pre` 最后一次调用的那一分钟尽量不算进来），写进 progress，这样会话断了也能接着核对：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
sleep 5; S=$(date +%s%3N); echo "$S" > /tmp/p5-a-since; T=$(date -u -d "@$((S/1000))" +%FT%TZ); echo "since=$S ($T)"
echo "Task 7 Step 3（T5.3）：已交给用户，Part A 开始于 $T（毫秒 $S，/tmp/p5-a-since）；收到模板 1 后按 Step 3 核对" | .venv/bin/python /tmp/p5-progress.py state 进行中
echo '等待用户：Part A（导入 skills，模板 1）' | .venv/bin/python /tmp/p5-progress.py state 阻塞
```
期望：`since=… (…Z)`；`进行中`、`阻塞` 各一行 `written`。

然后用中文告诉用户（不含 URL、secret、IP、ARN、账号）：
- 打开 `quick/P5-handoff.md`（清单）和 `quick/P5-guide.md`（详细步骤），先做「准备」（在自己的终端里 `scp` 拷 `quick/skills`），再做 Part A 的 A1–A5；
- 预检结果（`demo-check pre: 10/10 passed`）和 Part A 的开始时间（UTC）；
- 从现在到收到模板 1 之前，AI 不调用 Gateway 或 Runtime（审计里只有用户的调用）；
- 做完用模板 1 回复；Quick 要求重新填 secret 时，在自己的终端里按 T0.7 获取，不用 `!` 前缀。

收到模板 1 后，记下结束时间，等 3 分钟（CloudWatch 每分钟的指标有 1–3 分钟延迟），跑 `post`：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
date +%s%3N > /tmp/p5-a-until; sleep 180
bash scripts/demo-check.sh post --since "$(cat /tmp/p5-a-since)" --until "$(cat /tmp/p5-a-until)" | tee /tmp/p5-a-post.txt; echo "exit=${PIPESTATUS[0]}"
```
期望：`demo-check post: 5/5 passed`、`exit=0`；`audit` 一项里是 A5 的调用（多半是 `execute_query` 执行 `SHOW PROCESSLIST`，可能还有 `list_recent_queries`）和导入时 Quick 自己的调用（`tools/list` 不进审计）；`failures` 没有，或者只有 agent 自己改正了的调用。

核对模板 1：

| 项 | 通过 | 不通过时 |
|---|---|---|
| 时区 | 填了（例如 Asia/Shanghai、UTC+8）| 问用户；Step 4 的 `p5-steps.py` 需要 IANA 时区名 |
| A1 | 5 个都成功，Quick 里的名字和文件夹名一致 | 报错原文：大小（每个 < 1 MB，上限 6 MB）、description（`quick/test/test_skills.py` 已查 ≤ 1024）、frontmatter；修副本只能改 `build_skills.py` 的常量再生成（Task 1），adapter 直接改 + 测试 |
| A1 子文件夹 | 「否」；「是」只记录 | — |
| A2 | 指令已替换，skills 挂上 5 个或「全局」，只有 `Doris-Desktop-MCP`；svc 已更新 | 指令太长：记下提示原文，缩短 `quick/agent-instructions.md`（`test_agent_instructions.py` 先 RED）|
| A3 | 12 个工具，权限按表 | 不是 12：按手册「设置」在网页版新建连接器（P4 的做法），用户操作 |
| A4 | 任何结果都只记录 | Task 8 写进 design §13（M-1）|
| A5 | 选中了 adapter（和 `doris-debug` 或 `doris-profile-reader`），工具是 `execute_query`（`SHOW PROCESSLIST`）/ `list_recent_queries`，没有让用户运行命令，答案里没有连接信息 | 见下 |

A5 不通过时：
- 没有选中 adapter，但答案用的是 MCP 工具、没有让用户运行命令：不挡路，记为 Minor，Task 8 决定要不要改 adapter 的 description；
- 让用户去运行 `doriscli` / mysql 客户端 / curl，或者执行了 `KILL`：挡路。按 TDD 修 adapter（`quick/test/test_adapter_skill.py`，突变组 ad）或指令（`test_agent_instructions.py`，突变组 ai）：先写失败的测试 → 改 → `quick/test` 全部通过、突变组全部被抓到 → 提交 `fix(p5): …`；请用户重新导入改过的 skill（或重新粘贴指令），在新对话里再做一次 A5，回复 A5 那一行。最多两轮；还不行，停下来和用户商量；
- 答案里出现主机地址或 IP：记下来，Task 8 的第 2 项决策（2003 错误里的地址）。

全部通过后提交（「（…）」换成实际的内容）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - T5.3 <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
echo 'Task 7 Step 3（T5.3）已完成；Step 4（彩排第 1 轮）等用户说「开始第 1 轮」' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo '无' | .venv/bin/python /tmp/p5-progress.py state 阻塞
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 7 Step 3（T5.3）：skills 导入 Quick 桌面版

- 时区：（）。窗口：（since UTC）–（until UTC）。
- A1：（5 个的结果；子文件夹是否单独显示）。A2：（指令、skills 挂法、连接器；svc 和 `doris-mcp-svc` 的工具数）。A3：（工具数、权限）。
- A4（M-1 情况 c）：（没有要求登录 / scope、resource、code_challenge_method 的值）。
- A5：（发送时间、耗时、skills、工具、有没有让用户运行命令；答案摘要）。
- `demo-check post`：（N/5；audit 的调用数和失败；latency 最长的一次）。
- 修改：（没有就写「无」；有就写提交和重新导入的结果）。Task 8 要决定的：（Minor）。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
docs(p5): T5.3 skills imported into Quick desktop, A1-A5 results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望：`ticked: T5.3`；`进行中`、`阻塞`、日志各一行 `written`；`check-secrets: OK`；`0`；工作区干净。然后告诉用户 Part A 的核对结果，可以开始 Part B（说「开始第 1 轮」）。

- [ ] **Step 4：Part B：彩排 2 轮（T5.4）**

每一轮都按下面做，`N` 是轮次。用户说「开始第 N 轮」后：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
bash scripts/demo-check.sh pre; echo "exit=$?"
```
期望：`demo-check pre: 10/10 passed`、`exit=0`。只有一项 `[FAIL]` 时重跑一次；同一项连续两次失败，告诉用户先不要开始，查原因。

通过后记下开始时间：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
N=1   # 第几轮
sleep 5; S=$(date +%s%3N); echo "$S" > /tmp/p5-r$N-since; T=$(date -u -d "@$((S/1000))" +%FT%TZ); echo "round $N since=$S ($T)"
echo "Task 7 Step 4（T5.4）：第 $N 轮开始于 $T（毫秒 $S，/tmp/p5-r$N-since）；收到模板 2 后按 Step 4 核对" | .venv/bin/python /tmp/p5-progress.py state 进行中
echo "等待用户：彩排第 $N 轮（模板 2）" | .venv/bin/python /tmp/p5-progress.py state 阻塞
```
期望：`round N since=… (…Z)`；`进行中`、`阻塞` 各一行 `written`。然后回复用户：预检结果、这一轮的开始时间（UTC）、「可以开始」。从这时起到收到模板 2 之前，不调用 Gateway 或 Runtime。

收到模板 2 后（`N`、时区、日期和 7 个发送时间取自模板 1 和模板 2；发送时间过了午夜的，写成 `YYYY-MM-DDThh:mm:ss`）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
N=1
date +%s%3N > /tmp/p5-r$N-until; sleep 180
bash scripts/demo-check.sh post --since "$(cat /tmp/p5-r$N-since)" --until "$(cat /tmp/p5-r$N-until)" | tee /tmp/p5-r$N-post.txt; echo "exit=${PIPESTATUS[0]}"
.venv/bin/python /tmp/p5-steps.py /tmp/p5-r$N-post.txt Asia/Shanghai 2026-09-29 14:02:10 14:03:40 14:08:00 14:12:30 14:21:05 14:22:30 14:30:00
```
（最后一行的时区、日期、时间是示例，换成模板里的值。）

`p5-steps.py` 读 `post` 的 `latency` 一节（每分钟、每个工具一行），把每一行算给它之前最后发出的那一步（同一分钟里下一步已经发出时，这一分钟算给下一步），输出每步的调用数、单次最长和各工具的次数；第一步之前的行（`pre` 的最后几次调用可能落在第一分钟里）单独计数。header 的「从计划取文件」已经取出了它：

<!-- file: p5-steps.py sha256=bd88c0409e5460d7b45ac3957c43ca9b652a9c3067242aa9fbe95f8eb0bad4aa -->
```python
"""Gateway calls per rehearsal step (P5 Task 7 Step 4), from the saved output of `demo-check.sh post`.

  .venv/bin/python /tmp/p5-steps.py POST_OUTPUT ZONE DAY T1 T2 ... T7
ZONE is the IANA zone of the desktop's clock (template 2 is filled in local time; e.g. Asia/Shanghai), DAY the
local date (YYYY-MM-DD), T1 ... T7 the local send times of the steps (hh:mm:ss, or YYYY-MM-DDThh:mm:ss for a step
sent after midnight). The latency rows are per UTC minute, so a minute belongs to the last step sent in or before
it: calls a step makes in the minute the next step is sent count toward the next step. Rows before step 1 are
left out (the tail of `pre` can land there: the window's start is floored to the minute) and counted on the last
line. Prints, per step, the calls, the longest single call and the calls per tool; exit 1 if the send times are
not in order.
"""
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROW = re.compile(r"^\s+(\d{4}-\d\d-\d\dT\d\d:\d\d)\s+(\w+)\s+(\d+) calls\s+avg\s+\d+ ms\s+max\s+(\d+) ms$")


def utc_minute(zone: str, day: str, sent: str) -> str:
    local = datetime.fromisoformat(sent if "T" in sent else f"{day}T{sent}").replace(tzinfo=ZoneInfo(zone))
    return local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M")


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    path, zone, day, *sent = argv
    starts = [utc_minute(zone, day, t) for t in sent]
    if starts != sorted(starts):
        print(f"FAIL: send times out of order (UTC minutes: {', '.join(starts)})")
        return 1
    steps = [{"calls": 0, "max": 0, "tools": {}} for _ in starts]
    before = 0
    with open(path, encoding="utf-8") as lines:
        for line in lines:
            m = ROW.match(line.rstrip("\n"))
            if not m:
                continue
            minute, tool, calls, longest = m[1], m[2], int(m[3]), int(m[4])
            k = max((i for i, start in enumerate(starts) if start <= minute), default=None)
            if k is None:
                before += calls
                continue
            step = steps[k]
            step["calls"] += calls
            step["max"] = max(step["max"], longest)
            step["tools"][tool] = step["tools"].get(tool, 0) + calls
    for i, step in enumerate(steps):
        tools = ", ".join(f"{t} x{n}" for t, n in step["tools"].items()) or "-"
        print(f"step {i + 1} (from {starts[i][11:]} UTC): {step['calls']} calls, longest {step['max']} ms; {tools}")
    print(f"total: {sum(s['calls'] for s in steps)} calls in the steps, {before} before step 1")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

用一个假的 `post` 输出看它的格式（第 1 步 14:02:10 发出，06:01 那一行在它之前）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
cat > /tmp/p5-steps-demo.txt <<'EOF'
[PASS] latency
    window 2026-09-29T06:01:00Z .. 2026-09-29T06:40:00Z
    tools/call: 10 calls in 7 rows (tool x minute), max 2150 ms (execute_query at 2026-09-29T06:21)
      2026-09-29T06:01  list_tables                            1 calls  avg      50 ms  max      50 ms
      2026-09-29T06:02  check_service_health                   1 calls  avg     812 ms  max     812 ms
      2026-09-29T06:03  list_metrics                           1 calls  avg     401 ms  max     401 ms
      2026-09-29T06:04  query_metric                           2 calls  avg     900 ms  max    1200 ms
      2026-09-29T06:05  query_metric                           1 calls  avg     700 ms  max     700 ms
      2026-09-29T06:21  execute_query                          3 calls  avg    1500 ms  max    2150 ms
      2026-09-29T06:22  execute_query                          1 calls  avg     900 ms  max     900 ms
      [PASS] every minute under 60000 ms
EOF
.venv/bin/python /tmp/p5-steps.py /tmp/p5-steps-demo.txt Asia/Shanghai 2026-09-29 14:02:10 14:03:40 14:08:00 14:12:30 14:21:05 14:22:30 14:30:00; echo "exit=$?"
.venv/bin/python /tmp/p5-steps.py /tmp/p5-steps-demo.txt Asia/Shanghai 2026-09-29 14:02:10 14:03:40 14:08:00 14:12:30 14:21:05 14:30:00 14:22:30; echo "exit=$?"
rm -f /tmp/p5-steps-demo.txt
```
期望（实测）：
```
step 1 (from 06:02 UTC): 1 calls, longest 812 ms; check_service_health x1
step 2 (from 06:03 UTC): 4 calls, longest 1200 ms; list_metrics x1, query_metric x3
step 3 (from 06:08 UTC): 0 calls, longest 0 ms; -
step 4 (from 06:12 UTC): 0 calls, longest 0 ms; -
step 5 (from 06:21 UTC): 3 calls, longest 2150 ms; execute_query x3
step 6 (from 06:22 UTC): 1 calls, longest 900 ms; execute_query x1
step 7 (from 06:30 UTC): 0 calls, longest 0 ms; -
total: 9 calls in the steps, 1 before step 1
exit=0
FAIL: send times out of order (UTC minutes: 2026-09-29T06:02, 2026-09-29T06:03, 2026-09-29T06:08, 2026-09-29T06:12, 2026-09-29T06:21, 2026-09-29T06:30, 2026-09-29T06:22)
exit=1
```
示例里第 3、4、7 步是 0 次调用：每分钟的行只能按分钟分，一步的调用如果和下一步落在同一分钟，就算给了下一步。所以耗时表的「工具调用」写两轮的次数（`8 / 9` 这样），核对时和模板 2 里 Quick 显示的工具调用顺序对照，差得多的写进日志。

核对（每一步都看模板 2 那一行和答案全文）：
- **挡路**（这一轮之后、下一轮之前要修）：答不出；工具报错且 agent 没有自己改正；步骤 2 的 GMV / 订单数、步骤 3 的两个第一名、步骤 4 的店铺、步骤 5 没有 profile 证据（没有调用 `get_query_profile`）；让用户去运行命令；执行了写操作；答案里有主机地址或 IP。
- **只记录**（Task 8 统一处理）：参照值之外的细节（小数位、渠道只给小程序、物流给得粗、时间范围取法不同）；多调用或少调用了一两次；措辞和格式。
- `post` 的 `failures`：每条看 `error`。OR 连接两个时间范围的编译错误（`metric_time filters must be a single range joined with AND`）之后 agent 自己分两次调用，是 P-11 预期的行为，只记录；其他错误按挡路处理。
- `latency`：有 WARN（≥ 45 s）的，记下工具和分钟，Task 8 的第 3 项决策（`query_timeout`）要用；有 `[FAIL]`（≥ 60 s）的，对照模板 2 里的 424。
- `conns`：连接数 ≤ 80（`MAX_CONNS`）；超过的话记下，Task 8 决定。
- 步骤 1 的调用数可能多 1–2 次：`pre` 最后几次调用落在第一分钟（`p5-steps.py` 的最后一行 `before step 1` 就是它们）。
- 答案里用户换成了 `<已遮盖>` 的地方：记下是哪一步、哪类信息（2003 错误里的地址 → Task 8 的第 2 项决策）。

挡路的问题：
- 改 server（`mcp-server/src/`）：TDD → 按 Task 6 Step 3–6 再部署（GATE）→ 再开始下一轮；
- 改 adapter、其他 skill 的常量或指令：TDD → 提交 → 请用户重新导入（或重新粘贴指令）→ 下一轮新建对话；
- 第 2 轮仍有挡路的问题：修好后加一轮（第 3 轮），同样记录；两轮都没有挡路的问题，T5.4 才算完成。

每一轮核对完，记录并提交（「（…）」换成实际的内容；最后一轮的提交同时勾选 T5.4：把 `TICK=` 改成 `TICK=T5.4`）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
N=1; TICK=
if test -n "$TICK"; then .venv/bin/python - "$TICK" <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
fi
echo "Task 7 Step 4（T5.4）：第 $N 轮已核对（/tmp/p5-r$N-post.txt）；（下一轮等用户说「开始第 $((N+1)) 轮」/ 两轮都没有挡路的问题，Task 8 从 Step 1 开始）" | .venv/bin/python /tmp/p5-progress.py state 进行中
echo '无' | .venv/bin/python /tmp/p5-progress.py state 阻塞
sed "s/@DATE@/$(date -u +%F)/;s/@N@/$N/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 7 Step 4（T5.4）：彩排第 @N@ 轮

- 窗口：（since UTC）–（until UTC）；时区（）。
- 每步（发送时间、总耗时 s、Gateway 调用数 / 单次最长 ms、skills、是否符合期望）：
  1. 开场：（）
  2. 第 2 幕：（）
  3. 第 3 幕：（）
  4. 第 5 幕：（）
  5. 第 7 幕 + Track A：（）
  6. Track B：（）
  7. 收尾：（）
- `demo-check post`：（N/5；audit 的调用数、失败的调用和 error；latency 最长的一次、WARN；conns）。
- 弹窗：（）。424 / 报错：（）。重发：（）。agent 建议人工执行的语句：（条数和摘要）。
- 挡路的问题和处理：（没有就写「无」）。Task 8 要处理的：（）。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<EOF
docs(p5): T5.4 rehearsal round $N

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望：（最后一轮）`ticked: T5.4`；`进行中`、`阻塞`、日志各一行 `written`；`check-secrets: OK`；`0`；工作区干净。日志里不写答案全文（可能有用户没遮盖干净的连接信息），只写摘要；答案原文不进仓库。

**时间标记丢了**（`/tmp` 被清空、会话中断）时重建：
- `since`：progress「进行中」里写着开始时间（UTC）和毫秒数，直接用；只有 UTC 时间时换算成毫秒；
- `until`：第 7 步的发送时间 + 它的总耗时 + 300 s（留出余量；多出的时间里没有别的调用）。

换算（`date` 的相对时间要写成不带符号的「N seconds」或「N seconds ago」：`+395 seconds`、`-5 minutes` 会被当成时区偏移，算错）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
date -u -d '2026-09-29T06:01:55Z' +%s%3N                                   # since：progress 里的 UTC 时间
date -u -d 'TZ="Asia/Shanghai" 2026-09-29 14:30:00 395 seconds' +%s%3N    # until：第 7 步 14:30:00 发出，耗时 95 s，再加 300 s
```
期望（实测）：
```
1790661715000
1790663795000
```

---

### Task 8：T5.5：按彩排结果修正，填耗时表，四项决策

来源：tasks.md T5.5，design §13（60 s、2003、502、scope、adapter 几行）、§14（Gateway DEBUG），Task 7 记下的 Minor 和「Task 8 要处理的」事项。Step 1–3 和 Step 5 对 AWS 只读；Step 4 是本计划的第 2 个 GATE，只在决定改 Gateway 时执行。spec 阶段的发现：

| # | spec 阶段的发现 | 处理 | 测试 / 依据 |
|---|---|---|---|
| 1 | Gateway 的 description 是 None：P3 T3.4 的 `update-gateway` 没有传 `--description`，把它清空了（`update-gateway` 替换整个配置）| Task 5 已经把 description 放进 create / update 共用的参数；决策 4：要补就和决策 1 在同一次 `update-gateway` 里补 | Step 3 的只读核对（`description: None`）和 dry-run（update 里有 `--description`）；`test-30-gateway.sh`（突变 gw）|
| 2 | `exceptionLevel` 仍是 DEBUG。T3.4 对 6 类错误调用做了泄漏检查，IP、密码、栈的计数都是 0；DEBUG 下 Gateway 自己按 schema 拒绝的调用带字段级的原因（`Field '/database' has invalid type…`，T3.4 实测），关掉后是什么消息没有实测 | 决策 1（见 Step 3 的推荐）。`30-gateway.sh` 的默认值仍是 DEBUG：关掉之后，任何一次重跑都要带 `GW_EXCEPTION_LEVEL=`，否则会重新打开；这一点写进 progress「注意」和 design §14 | Step 3 两种取值的 dry-run；GATE 之后再做一次只读核对和 `demo-check pre` |
| 3 | 2003 错误的消息带 Doris 地址（P3 发现）。它是 server 返回的工具结果（`CONNECTION_ERROR` 的 JSON），所以按理和 `exceptionLevel` 无关，关掉 DEBUG 也遮不住；只在 Doris 连不上时出现，spec 阶段没有为了测它断网 | 决策 2（见 Step 3）。要补丁就是 P-12：server 返回的错误消息把 IPv4 换成 `<ip>`，TDD，然后按 Task 6 Step 3–6 再部署（GATE，version 4）| 两轮彩排的模板 2 和 `post` 的 `failures` |
| 4 | `query_timeout` 是 50 s（P-06）：P4 实测单次工具调用最长 9863 ms，≥ 45 s 的 0 次 | 决策 3：两轮彩排里出现 WARN（≥ 45 s）或 424 才调到 40–45 s（`mcp-server/config/mcp-server.toml` 的 `query_timeout_seconds`，`test_agentcore_tools.py` 断言了 50，先 RED），再部署（GATE）；否则不改 | `post` 的 `latency`、`p5-steps.py` 的单次最长 |
| 5 | 未解决的 Minor：Task 5 的 `TOKEN_CMD` 默认值读仓库的 `infra/state.env`，不看 `STATE_FILE`；`99-cleanup.sh` 少数「已经不存在」的分支只在离线测试里走过。另有 Task 7 的整体评审和彩排记下的 | Step 1 逐条决定：修（TDD）或写明不修的理由 | — |

**Files:**
- Modify: `quick/runbook.md`（「每步耗时」）、`specs/doris-mcp-quick/design.md`（v0.9：四项决策、A4 / A5、彩排结果）、`tasks.md`、`progress.md`
- 按 Step 1 / Step 3 的决定可能修改：`quick/skills/doris-mcp-adapter/SKILL.md`、`quick/agent-instructions.md`（和它们的测试）、`mcp-server/config/mcp-server.toml`、`mcp-server/src/`（P-12）
- AWS（GATE，只在决定改时）：Gateway `doris-mcp-gw` 的 description、`exceptionLevel`

**Interfaces:**
- Consumes：Task 7 的 progress 日志（整体评审的 Minor、每轮的「Task 8 要处理的」）、两轮的模板 2、`/tmp/p5-r1-post.txt`、`/tmp/p5-r2-post.txt` 和 `p5-steps.py` 的每步汇总；Task 5 的 `infra/30-gateway.sh`（`GW_EXCEPTION_LEVEL`）；`/tmp/p5-idmask.py`；`bcda0f3` 的 `infra/policies/gateway-invoke-runtime.json`。
- Produces：填好的耗时表（演示时对照）；design v0.9；Gateway 的最终配置（演示用它，Task 9 删除）。

- [ ] **Step 1：不挡路的问题**

列出 Task 7 记下的事项（progress 里有私网 IP，只经 MASK 看）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
grep -nE 'Task 8 要|Minor（Task 8' specs/doris-mcp-quick/progress.md | sed -E "$MASK"
```
每一条定下「修」或「不修（理由）」，写进 Step 5 的日志：
- 修 skills 或指令：先写失败的测试（`quick/test/test_adapter_skill.py` / `test_agent_instructions.py`）→ 改 → `quick/test` 全部通过、突变组（ad / ai）全部被抓到 → 提交 `fix(p5): …`（提交前照常跑 `check-secrets.sh` 和 IP 计数）；请用户重新导入改过的 skill（或重新粘贴指令），在新对话里重问受影响的那一步，AI 前后各记一次时间，按 Task 7 Step 4 跑 `post` 并核对。突变的 `old` 被改掉了的，在 `/tmp/p5-mutations.json` 里换成新的文字再跑，日志里写明。
- 修 server（`mcp-server/src/`）：同样 TDD，按 Task 6 Step 3–6 再部署（GATE），`demo-check pre` 10/10 后重问受影响的那一步。
- Task 5 的两个 Minor 推荐都不修：`TOKEN_CMD` 只有离线测试会换 `STATE_FILE`，而测试本来就换掉了 `TOKEN_CMD`（`demo-check.sh` 的 header 写明了）；「已经不存在」的分支在 Task 9 Step 3 的第二次 dry-run 里会对真实账号走一遍。
- 没有要修的就记「无」。

- [ ] **Step 2：填耗时表**

「第 1 轮」「第 2 轮」取自两轮模板 2 的「总耗时」；「工具调用」写两轮 `p5-steps.py` 的调用数（`第 1 轮 / 第 2 轮`）；「单次最长」是两轮里这一步 `longest` 的较大值，换成秒（1 位小数）。把 `None` 换成 `(第 1 轮 s, 第 2 轮 s, "调用数 / 调用数", 单次最长 s)`：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - <<'EOF'
import pathlib
ROWS = {
    1: None,  # 填写：开场
    2: None,  # 填写：第 2 幕
    3: None,  # 填写：第 3 幕
    4: None,  # 填写：第 5 幕
    5: None,  # 填写：第 7 幕 + Track A
    6: None,  # 填写：Track B
    7: None,  # 填写：收尾
}
NAMES = {1: "开场", 2: "第 2 幕", 3: "第 3 幕", 4: "第 5 幕", 5: "第 7 幕 + Track A", 6: "Track B", 7: "收尾"}
assert all(ROWS.values()), "fill in every row"
p = pathlib.Path("quick/runbook.md"); s = p.read_text(encoding="utf-8")
old = "由 T5.5 根据彩排回复填写。"
assert s.count(old) == 1, old
s = s.replace(old, "「第 1 轮」「第 2 轮」是 Quick 里从发出问题到回答完整显示的时间，「单次最长」是两轮里这一步最长的一次工具调用。")
for k, name in NAMES.items():
    old = f"| {k} | {name} | — | — | — | — |"
    assert s.count(old) == 1, old
    r1, r2, calls, longest = ROWS[k]
    s = s.replace(old, f"| {k} | {name} | {r1} | {r2} | {calls} | {longest} |")
table = s.split("\n## 每步耗时\n", 1)[1]
assert "—" not in table, "a row is still empty"
p.write_text(s, encoding="utf-8")
print(table.strip())
EOF
.venv/bin/python -m unittest discover -s quick/test 2>&1 | tail -3                                  # 期望：Ran 60 tests … OK
.venv/bin/python /tmp/p5-mut.py /tmp/p5-mutations.json docs; echo "rc=$?"
git status --short
```
期望：打印「每步耗时」一节（说明一行，表头和 7 行都填了数）；`Ran 60 tests` `OK`；`docs: 15/15 mutations caught`、`rc=0`；`git status` 只有 ` M quick/runbook.md`。

提交：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
echo 'Task 8 Step 2（耗时表）已提交；Step 3（四项决策）等用户选择' | .venv/bin/python /tmp/p5-progress.py state 进行中
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add quick/runbook.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
docs(p5): T5.5 runbook timing table from the two rehearsals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望：`进行中` 一行 `written`；`check-secrets: OK`；`0`；工作区干净，最后一行是这个提交的标题。

- [ ] **Step 3：四项决策（用户选）**

先看 Gateway 现在的配置。只输出状态、枚举值和布尔值（`authorizerConfiguration` 里有 discovery URL，不打印，只和 `30-gateway.sh` 生成的比较）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
set -a; source infra/state.env; set +a
t=$(mktemp -d)
aws bedrock-agentcore-control get-gateway --gateway-identifier "$GW_ID" --region us-east-1 --output json > "$t/gw.json"; echo "get-gateway exit=$?"
aws iam get-role-policy --role-name doris-mcp-gateway-role --policy-name invoke-dorismcp-runtime --region us-east-1 --output json > "$t/policy.json"; echo "get-role-policy exit=$?"
.venv/bin/python - "$t" <<'EOF'
import json, os, sys, urllib.parse
d = sys.argv[1]
gw = json.load(open(f"{d}/gw.json"))
pol = json.load(open(f"{d}/policy.json"))["PolicyDocument"]
if isinstance(pol, str):
    pol = json.loads(urllib.parse.unquote(pol))
authz = {"customJWTAuthorizer": {"discoveryUrl": os.environ["DISCOVERY_URL"],
                                 "allowedClients": [os.environ["CLIENT_A_ID"], os.environ["CLIENT_B_ID"]],
                                 "allowedScopes": ["doris-mcp/invoke"]}}
want = json.loads(os.path.expandvars(open("infra/policies/gateway-invoke-runtime.json").read()))
print("status:", gw.get("status"))
print("exceptionLevel:", gw.get("exceptionLevel"))
print("description:", gw.get("description"))
print("name, protocol, authorizer type:", gw.get("name"), gw.get("protocolType"), gw.get("authorizerType"))
print("authorizer == 30-gateway.sh's (clients A, B; scope doris-mcp/invoke):", gw.get("authorizerConfiguration") == authz)
print("roleArn == GW_ROLE_ARN:", gw.get("roleArn") == os.environ["GW_ROLE_ARN"])
print("role policy == gateway-invoke-runtime.json:", pol == want)
EOF
rm -rf "$t"
```
期望（实测）：
```
get-gateway exit=0
get-role-policy exit=0
status: READY
exceptionLevel: DEBUG
description: None
name, protocol, authorizer type: doris-mcp-gw MCP CUSTOM_JWT
authorizer == 30-gateway.sh's (clients A, B; scope doris-mcp/invoke): True
roleArn == GW_ROLE_ARN: True
role policy == gateway-invoke-runtime.json: True
```
authorizer、角色、策略都和脚本一致，所以重跑 `30-gateway.sh` 实际改变的只有 description 和（选了关闭时的）`exceptionLevel`。

两种取值的 dry-run（只有 get / list；输出经 `p5-idmask.py`，authorizer 的 JSON 缩成 `<AUTHZ>`）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
for lvl in DEBUG ''; do
  echo "--- GW_EXCEPTION_LEVEL='$lvl'"
  GW_EXCEPTION_LEVEL="$lvl" bash infra/30-gateway.sh 2>&1 | .venv/bin/python /tmp/p5-idmask.py | grep -E 'DRY-RUN: aws|FATAL|gateway exists' \
    | sed -E 's#file:///tmp/tmp\.[A-Za-z0-9]+#file:///tmp/tmp.<x>#; s/^\[[0-9:]{8}\] /[hh:mm:ss] /; s/\\\{\\"customJWTAuthorizer.*\\\}\\\} /<AUTHZ> /'
  echo "exit=${PIPESTATUS[0]}"
done
```
期望（实测）：
```
--- GW_EXCEPTION_LEVEL='DEBUG'
DRY-RUN: aws iam put-role-policy --role-name doris-mcp-gateway-role --policy-name invoke-dorismcp-runtime --policy-document file:///tmp/tmp.<x>
[hh:mm:ss] gateway exists: <GW_ID> (re-applying authorizer, scopes='doris-mcp/invoke', exception level='DEBUG')
DRY-RUN: aws bedrock-agentcore-control update-gateway --gateway-identifier <GW_ID> --name doris-mcp-gw --role-arn <GW_ROLE_ARN> --protocol-type MCP --authorizer-type CUSTOM_JWT --authorizer-configuration <AUTHZ> --exception-level DEBUG --description Quick\ desktop\ -\>\ Doris\ MCP\ \(Runtime\ dorismcp\) --query status --output text
exit=0
--- GW_EXCEPTION_LEVEL=''
DRY-RUN: aws iam put-role-policy --role-name doris-mcp-gateway-role --policy-name invoke-dorismcp-runtime --policy-document file:///tmp/tmp.<x>
[hh:mm:ss] gateway exists: <GW_ID> (re-applying authorizer, scopes='doris-mcp/invoke', exception level='')
DRY-RUN: aws bedrock-agentcore-control update-gateway --gateway-identifier <GW_ID> --name doris-mcp-gw --role-arn <GW_ROLE_ARN> --protocol-type MCP --authorizer-type CUSTOM_JWT --authorizer-configuration <AUTHZ> --description Quick\ desktop\ -\>\ Doris\ MCP\ \(Runtime\ dorismcp\) --query status --output text
exit=0
```
两种取值都只有 `put-role-policy`（策略和现在的相同）和 `update-gateway`；差别只在 `--exception-level DEBUG` 有没有，两者都带 `--description`。target 不动（没有 `SYNC=1`）。

把两轮彩排的数据和下面的推荐一起告诉用户（中文，不含 URL、IP、ARN、账号），请用户逐项选择：

| # | 决策 | 选项 | 推荐 | 依据 |
|---|---|---|---|---|
| 1 | Gateway `exceptionLevel` | A 关闭（`GW_EXCEPTION_LEVEL=`）；B 保留 DEBUG 到演示结束 | **B**：两轮彩排用的就是 DEBUG，演示前改配置等于换成没彩排过的设置；T3.4 的泄漏检查是 0；Task 9 删除 Gateway 时它就没了。用户更看重「少给客户端信息」时选 A，GATE 之后 `demo-check pre` 的 3 个错误用例会确认 server 的错误码仍然能到 Quick | T3.4；两轮的 `post`；模板 2 里有没有 Quick 显示报错、但审计里没有对应记录的调用（那是 Gateway 自己拒绝的）|
| 2 | 2003 错误里的 Doris 地址 | A 不补丁；B P-12（server 的错误消息 mask IPv4，再部署）| **A**：只在 Doris 连不上时出现，那时演示本来就要停下来；手册「出问题时」已写明不念、剪掉。要公开发布录屏、希望从根上避免时选 B | 两轮的 `failures` 和模板 2（彩排里出现过就写明次数）|
| 3 | `query_timeout` | A 保持 50 s；B 调到 40–45 s（再部署）| 两轮都没有 WARN（≥ 45 s）和 424 时 **A**；有的话 **B** | 两轮 `latency` 的 WARN、`p5-steps.py` 的单次最长、模板 2 的 424 |
| 4 | Gateway description | A 补上（和决策 1 同一次 `update-gateway`）；B 不补（只影响控制台显示）| **A**：dry-run 显示除了 description 之外参数都没变；做完马上 `demo-check pre` | Step 3 的只读核对和 dry-run |

决策 1、4 选了「保留 DEBUG + 不补 description」时，跳过 Step 4。决策 2 选 B、决策 3 选 B 时，先按 TDD 改好并提交，再按 Task 6 Step 3–6 部署（和 Task 6 同一类 GATE，单独确认），部署后 `demo-check pre` 10/10。

- [ ] **Step 4：GATE：更新 Gateway（只在决策 1 或 4 要改时）**

向用户展示 Step 3 的只读核对、对应取值的 dry-run，并说明：
- `update-gateway` 替换 Gateway `doris-mcp-gw` 的整个配置：名字、角色、authorizer（2 个 client、scope `doris-mcp/invoke`）不变，description 补上，`exceptionLevel` 按决策 1；`put-role-policy` 重写同样的策略；target 和工具目录不动，`state.env` 不变。
- Gateway 会短暂变成 UPDATING（脚本等到 READY，通常 1 分钟以内），这段时间不要在 Quick 里测试；已经打开的 Quick 对话不用重建。
- 费用不变。回滚也是 GATE：`APPLY=1 bash infra/30-gateway.sh`（回到 DEBUG）或带 `GW_EXCEPTION_LEVEL=`。

用户明确确认后执行（`LVL` 按决策 1：`DEBUG` 或空串）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
LVL=DEBUG
APPLY=1 GW_EXCEPTION_LEVEL="$LVL" bash infra/30-gateway.sh 2>&1 | .venv/bin/python /tmp/p5-idmask.py | sed -E 's/^\[[0-9:]{8}\] /[hh:mm:ss] /'; echo "exit=${PIPESTATUS[0]}"
git status --short infra/state.env
```
期望：`APPLY=1 region=us-east-1 …`、`role exists: <GW_ROLE_ARN>`、`gateway exists: <GW_ID> (re-applying authorizer, scopes='doris-mcp/invoke', exception level='…')`、`get-gateway → READY`、`target exists: <GW_TARGET_ID> (SYNC=1 to re-list tools)`、`get-gateway-target → READY`、`done (APPLY=1)`，`exit=0`；`git status` 没有输出（`state.env` 的值不变）。

然后重跑 Step 3 的只读核对（t58-gw-now 那个块）和预检：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
bash scripts/demo-check.sh pre; echo "exit=$?"
```
期望：只读核对里 `description: Quick desktop -> Doris MCP (Runtime dorismcp)`，`exceptionLevel` 是 `DEBUG`（决策 1 选 B）或 `None`（选 A），其余 4 行不变、3 个 `True`；`demo-check pre: 10/10 passed`、`exit=0`。只有一项失败时重跑一次；选了 A 而 3 个错误用例那一项连续失败，说明关掉 DEBUG 影响了 server 错误码的传递，告诉用户，建议回滚（GATE）。

决策 1 选了 A（关闭）时，把重跑的注意事项写进 progress「注意」：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-progress.py sub 注意 '需要有效的 AWS 凭证' '需要有效的 AWS 凭证。Gateway 的 DEBUG 已在 T5.5 关闭：重跑 `infra/30-gateway.sh` 都要带 `GW_EXCEPTION_LEVEL=`，否则会重新打开'
```
期望：`注意 (需要有效的 AWS 凭证 -> …): written (… lines)`。

- [ ] **Step 5：design v0.9，收尾，提交**

把决策和 T5.3 / T5.4 的结果写进 design（把 `None` 换成一句中文；每个锚点必须恰好出现 1 次）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - <<'EOF'
import pathlib, time
DAY = time.strftime("%Y-%m-%d", time.gmtime())
EXC = None        # 填写：决策 1 + 4，例如「保留 DEBUG 到演示结束，description 已补上（GATE）」
HOST = None       # 填写：决策 2，例如「不补丁，两轮彩排都没有出现 2003；手册「出问题时」已写明」
QT = None         # 填写：决策 3，例如「`query_timeout` 保持 50 s」
A5 = None         # 填写：例如「选中了 adapter 和 doris-debug，用 `execute_query` 执行 `SHOW PROCESSLIST`，没有让用户运行命令」
SCOPE = None      # 填写：A4，例如「导入时没有要求登录，仍未证实」
REHEARSAL = None  # 填写：例如「两轮 7 步都没有挡路的问题（第 1 轮约 … min，第 2 轮约 … min）」
LAT = None        # 填写：例如「单次工具调用最长 … ms，≥ 45 s 的 0 次，没有 424」
R502 = None       # 填写：例如「两轮彩排和 … 次预检里 502 出现 … 次，重跑都通过」
assert all((EXC, HOST, QT, A5, SCOPE, REHEARSAL, LAT, R502)), "fill in every value"
p = pathlib.Path("specs/doris-mcp-quick/design.md"); s = p.read_text(encoding="utf-8")
edits = [
    ("> 版本：**v0.8** · 2026-09-28 · 状态：P5 进行中（`plans/P5-skills.md`，分支 `p5-skills`）；",
     f"> 版本：**v0.9** · {DAY} · 状态：P5 演示准备完成（`plans/P5-skills.md` Task 1–8，分支 `p5-skills`；Task 9 在演示结束后清理）；"),
    ("| v0.8 | ",
     f"| v0.9 | P5 实施（Task 1–8，{DAY}）：① skills 导入 Quick 桌面版（T5.3）：A5 {A5}；A4（M-1）{SCOPE}（§13）。② 彩排（T5.4）：{REHEARSAL}；{LAT}（§13）。③ T5.5 的四项决策：Gateway {EXC}；2003 错误里的主机地址：{HOST}；{QT}（§13、§14）。④ Runtime version 3（P-10、P-11、3 个传递依赖锁定，§5.2）|\n| v0.8 | "),
    ("≥ 45 s 的 0 次；T5.5 不必为此调整 `query_timeout` |",
     f"≥ 45 s 的 0 次；T5.5 不必为此调整 `query_timeout`。P5 彩排（T5.4）实测：{LAT}；T5.5 决定：{QT} |"),
    ("scope 从哪里来：仍**未证实**（`doris-mcp` 的 Sync 没有要求登录；新建 `Doris-Desktop-MCP` 时出现了登录页，但没有读地址），T5.3 再看。",
     f"scope 从哪里来：{SCOPE}（T5.3 A4；P4 时 `doris-mcp` 的 Sync 没有要求登录，新建 `Doris-Desktop-MCP` 时出现了登录页，但没有读地址）。"),
    ("是否补丁在 T5.5 与 Gateway DEBUG 一起决定（§14，`plans/P5-skills.md` Task 8）",
     f"T5.5 决定：{HOST}（§14）"),
    ("彩排中出现时记下时间，T5.5 对照审计日志",
     f"彩排中出现时记下时间，T5.5 对照审计日志。T5.4 实测：{R502}"),
    ("T5.3 A5 实测，没选中就改 description 或指令 |",
     f"T5.3 A5 实测：{A5} |"),
    ("T5.5（Task 8）按彩排结果决定，改 Gateway 走 GATE",
     f"T5.5（Task 8）决定：{EXC}"),
]
for old, new in edits:
    assert s.count(old) == 1, old
    s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
print(f"design.md: v0.9, {len(edits)} edits")
EOF
git diff --stat
```
期望：`design.md: v0.9, 8 edits`；`git diff --stat` 只有 `specs/doris-mcp-quick/design.md`。决策 1 选了 A 时，`EXC` 里写明「之后重跑 `infra/30-gateway.sh` 要带 `GW_EXCEPTION_LEVEL=`」。

勾选 T5.5，更新状态，提交（「（…）」换成实际的内容）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - T5.5 <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
echo 'Task 8（T5.5）已完成：P5 演示准备完成（Task 1–8）；Task 9（T5.6 清理）等真正的演示结束' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo '真正的演示（用户按 `quick/runbook.md`；演示前 30 分钟内跑 `demo-check pre`，结束后跑 `post`）；演示结束、用户说「演示结束了」之后做 Task 9（T5.6 清理，GATE）' | .venv/bin/python /tmp/p5-progress.py state 下一步
echo '等待用户：真正的演示；`p5-skills` 是否合并到 `main`、是否推送（D8）' | .venv/bin/python /tmp/p5-progress.py state 阻塞
.venv/bin/python /tmp/p5-progress.py sub '已创建的 AWS 资源' '`exceptionLevel` 仍是 DEBUG，保留到 T5.5；description 在 T3.4 被清空' '（T5.5 的决定，例如：`exceptionLevel` DEBUG 保留到演示结束，description 已在 T5.5 补上）'
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 8（T5.5）：修正、耗时表、四项决策

- Step 1（不挡路的问题）：（每条一行：问题 → 修（提交）/ 不修（理由）；没有就写「无」）。
- Step 2：`quick/runbook.md`「每步耗时」按两轮彩排填写（每步两轮的秒数、调用数、单次最长）。
- 决策（用户选择）：① `exceptionLevel`：（）；② 2003 主机地址：（）；③ `query_timeout`：（）；④ description：（）。
- Gateway（GATE，没有改就写「未执行」）：用户确认「（用户的原话）」后 `APPLY=1 GW_EXCEPTION_LEVEL=（） bash infra/30-gateway.sh`；只读核对 `description`、`exceptionLevel` 为新值，authorizer / 角色 / 策略不变；`state.env` 不变；`demo-check pre` 10/10。
- design v0.9：四项决策、A4 / A5、彩排结果、60 s 和 502 的实测写进 §13、§14。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add specs/doris-mcp-quick/design.md specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
docs(p5): T5.5 decisions (Gateway exception level and description, 2003 host, query_timeout), design v0.9

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望：`ticked: T5.5`；`进行中`、`下一步`、`阻塞`、`已创建的 AWS 资源 (… -> …)`、日志各一行 `written`；`check-secrets: OK`；`0`；工作区干净。

然后用中文告诉用户：P5 的演示准备已经完成（Task 1–8 的结果、四项决策、耗时表在手册里）；演示当天按 `quick/runbook.md`；演示结束后说「演示结束了」开始 Task 9。并问用户：`p5-skills` 现在是否合并到 `main`（fast-forward），是否推送到私有仓库（D8，由用户决定；合并和推送都不在用户同意之前做）。

---

### Task 9：T5.6 演示结束后清理（GATE）

来源：tasks.md T5.6，design §7 的 `99-cleanup.sh` 一行、§14 的最后一项，`quick/runbook.md`「演示后」第 3 条。用户说「演示结束了」（或者明确说不再需要这套环境）之后才开始；在那之前，即使 Task 8 已经完成，也不要执行本任务的 Step 2。本任务唯一的 GATE 是 Step 2 的 `APPLY=1 bash infra/99-cleanup.sh`，其余步骤对 AWS 只读；Doris 侧和 Quick 侧由用户执行（Step 4）。spec 阶段的发现：

| # | spec 阶段的发现 | 处理 |
|---|---|---|
| 1 | 清理要 15–25 分钟：栈删除 5–10 分钟，endpoint 最多等 5 分钟，Runtime 的 ENI 在栈删除后几分钟才释放（最多等约 10 分钟）；超过一次 Bash 调用 10 分钟的上限 | 用 Bash 的 `run_in_background`，输出全部写进 `/tmp/p5-cleanup.log`，结束时只看 `exit=…`；日志里有资源 ID，只经 `/tmp/p5-idmask.py` 查看 |
| 2 | `APPLY=1` 时 `run` 直接执行、不打印命令（只有 dry-run 打印 `DRY-RUN:`）；`delete-security-group` 会往 stdout 写 JSON（`"Return": true`、`"GroupId": …`）| 日志里没有逐条的命令，删了什么以最后一行 `done (deleted: …)` 为准；JSON 里的 SG ID 由 idmask 换成 `<RT_SG>` / `<VPCE_SG>` |
| 3 | `delete-gateway` 之后脚本不等 Gateway 消失：它会有一小段时间是 DELETING，这时候的 dry-run 仍会把它列为要删除 | 第二次 dry-run 列出 `Gateway` 时，等一分钟再 dry-run，**不要再 `APPLY=1`** |
| 4 | Task 5 之前，`check-secrets.sh` 在 secret 删除后会一直 FAIL | Task 5 已改：排期删除（7 天恢复期内）或在 `state.env` 的账号里已不存在时记一行 `SKIP`；Step 3 看完整输出，Step 5 的提交照常检查 |
| 5 | AgentCore 为 Runtime 和 Gateway 各自动建了一个 workload identity（名字是 `dorismcp_dorismcp-…`、`doris-mcp-gw-…`），不在 `state.env` 里，`99-cleanup.sh` 不处理；删 Runtime / Gateway 时它们会不会一起删掉，spec 阶段没有实测（没有删除过）| Step 1、Step 3 只输出这两个名字前缀的个数。删除后还在的话，告诉用户：它们不计费，只是名字；要删是一次单独的 GATE（`aws bedrock-agentcore-control delete-workload-identity --region us-east-1 --name …`，名字不打印，由命令从列表里取）|
| 6 | 账号里还有别的项目的资源：Gateway `pragent-github-gw`，Runtime `doris_mcp_server`、`harness_pragent_issue_autofix`（及它们的 workload identity、日志组），1 个 API key credential provider，CDK bootstrap 的 `CDKToolkit` 栈 | `99-cleanup.sh` 只按 `state.env` 的 ID 删除，并先核对标签和名字；Step 3 核对它们都还在 |

**Files:**
- Modify: `specs/doris-mcp-quick/design.md`（v1.0：§14 最后一项打勾）、`RESUME.md`（「演示当天」一行）、`tasks.md`、`progress.md`
- AWS（GATE）：删除 `state.env` 记录的本项目资源（Task 5 Step 5 dry-run 列出的 18 个操作）
- 不改：`infra/state.env`（作为删除前的记录保留）、代码和测试

**Interfaces:**
- Consumes：Task 5 的 `infra/99-cleanup.sh`、`/tmp/p5-idmask.py`、`scripts/check-secrets.sh`（1b 步的 `SKIP`）；Task 8 的 design v0.9 状态行。
- Produces：AWS 侧不再有本项目的资源（接口 endpoint 停止计费）；design v1.0；P5 完成。

- [ ] **Step 1：执行前再 dry-run 一次（只读）**

输出经 `/tmp/p5-idmask.py`（`state.env` 的值换成 `<键名>`，IPv4 换成 `<ip>`，SG 规则 ID 换成 `<sgr>`）。另外只输出计数和名字：`doris-demo-sg` 的入站规则数、Gateway 和 Runtime 的名字、本项目的 workload identity 个数：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
bash infra/99-cleanup.sh 2>&1 | .venv/bin/python /tmp/p5-idmask.py | sed -E 's/^\[[0-9:]{8}\] /[hh:mm:ss] /'; echo "exit=${PIPESTATUS[0]}"
set -a; source infra/state.env; set +a
sg_rules() {
  aws ec2 describe-security-group-rules --region us-east-1 --filters "Name=group-id,Values=$DORIS_SG" \
    --query "length(SecurityGroupRules[?!IsEgress$1])" --output text
}
echo "doris-demo-sg ingress: $(sg_rules '') in all, $(sg_rules " && ReferencedGroupInfo.GroupId=='$RT_SG'") from doris-mcp-rt," \
     "$(sg_rules " && CidrIpv4=='$DEV_BOX_IP/32'") from the dev box /32, $(sg_rules " && CidrIpv4=='0.0.0.0/0'") from 0.0.0.0/0"
names() { tr '\t' '\n' | sort | paste -sd' '; }
echo "gateways: $(aws bedrock-agentcore-control list-gateways --region us-east-1 --query 'items[].name' --output text | names)"
echo "runtimes: $(aws bedrock-agentcore-control list-agent-runtimes --region us-east-1 --query 'agentRuntimes[].agentRuntimeName' --output text | names)"
echo "workload identities of this project: $(aws bedrock-agentcore-control list-workload-identities --region us-east-1 \
  --query 'workloadIdentities[].name' --output text | tr '\t' '\n' | grep -cE '^(dorismcp_dorismcp|doris-mcp-gw)-')"
echo "CDKToolkit: $(aws cloudformation describe-stacks --region us-east-1 --stack-name CDKToolkit --query 'Stacks[0].StackStatus' --output text)"
```
期望（实测）：
```
[hh:mm:ss] APPLY=0 region=us-east-1 state=/home/ubuntu/AI-code/Doris-mcp-skill-Demo/infra/state.env
[hh:mm:ss] checks passed
DRY-RUN: aws bedrock-agentcore-control delete-gateway-target --gateway-identifier <GW_ID> --target-id <GW_TARGET_ID>
DRY-RUN: aws bedrock-agentcore-control delete-gateway --gateway-identifier <GW_ID>
DRY-RUN: aws cloudformation delete-stack --stack-name AgentCore-dorismcp-default
DRY-RUN: aws cloudformation wait stack-delete-complete --stack-name AgentCore-dorismcp-default
DRY-RUN: aws ec2 delete-vpc-endpoints --vpc-endpoint-ids <VPCE_S3> <VPCE_LOGS> <VPCE_SECRETSMANAGER>
DRY-RUN: aws cognito-idp delete-user-pool-domain --domain <COGNITO_DOMAIN:prefix> --user-pool-id <COGNITO_POOL_ID>
DRY-RUN: aws cognito-idp delete-user-pool --user-pool-id <COGNITO_POOL_ID>
DRY-RUN: aws secretsmanager delete-secret --secret-id doris-mcp/cognito-demo-user --recovery-window-in-days 7
DRY-RUN: aws secretsmanager delete-secret --secret-id doris-mcp/mcp_svc --recovery-window-in-days 7
DRY-RUN: aws ec2 revoke-security-group-ingress --group-id <DORIS_SG> --security-group-rule-ids <sgr> <sgr>
DRY-RUN: aws ec2 revoke-security-group-egress --group-id <RT_SG> --security-group-rule-ids <sgr>
DRY-RUN: aws ec2 revoke-security-group-ingress --group-id <VPCE_SG> --security-group-rule-ids <sgr>
DRY-RUN: aws ec2 delete-security-group --group-id <RT_SG>
DRY-RUN: aws ec2 delete-security-group --group-id <VPCE_SG>
DRY-RUN: aws iam delete-role-policy --role-name doris-mcp-gateway-role --policy-name invoke-dorismcp-runtime
DRY-RUN: aws iam delete-role --role-name doris-mcp-gateway-role
DRY-RUN: aws iam delete-role-policy --role-name doris-mcp-runtime-role --policy-name doris-mcp-runtime
DRY-RUN: aws iam delete-role --role-name doris-mcp-runtime-role
[hh:mm:ss] done (dry-run, APPLY=1 would delete: Gateway target, Gateway, stack AgentCore-dorismcp-default, 3 VPC endpoints, Cognito domain, user pool, secret doris-mcp/cognito-demo-user, secret doris-mcp/mcp_svc, 2 <DORIS_SG> rules, SG <RT_SG>, SG <VPCE_SG>, role doris-mcp-gateway-role, role doris-mcp-runtime-role). Kept: /home/ubuntu/AI-code/Doris-mcp-skill-Demo/infra/state.env (the record), log groups, X-Ray settings. Doris side (DROP USER mcp_svc, DROP DATABASE system_mcp) is a separate step.
exit=0
doris-demo-sg ingress: 5 in all, 2 from doris-mcp-rt, 3 from the dev box /32, 0 from 0.0.0.0/0
gateways: doris-mcp-gw pragent-github-gw
runtimes: doris_mcp_server dorismcp_dorismcp harness_pragent_issue_autofix
workload identities of this project: 2
CDKToolkit: UPDATE_COMPLETE
```
和 Task 5 Step 5 一样：全部检查通过，18 条 `DRY-RUN`，`exit=0`。`doris-demo-sg` 的入站规则里只有 2 条引用 `doris-mcp-rt`，会被撤销；开发机的 3 条 `/32` 规则不动，`0.0.0.0/0` 是 0。Task 8 改过 Gateway 也不影响这里（ID 不变）。

列出的操作和上面不同（多了、少了，或者有 `FATAL`）时停下来，查明原因再继续；不要进入 Step 2。

- [ ] **Step 2：GATE：执行清理**

向用户展示 Step 1 的 dry-run（mask 后的），并说明：
- 要删除的（按这个顺序）：Gateway target 和 Gateway `doris-mcp-gw`；CloudFormation 栈 `AgentCore-dorismcp-default`（Runtime `dorismcp_dorismcp`）；3 个 VPC endpoint（S3 gateway endpoint，以及 logs、secretsmanager 两个 interface endpoint，后两个按小时计费）；Cognito 域名和 user pool（2 个 app client、用户 `demo` 随 pool 一起删除）；2 个 secret（`doris-mcp/cognito-demo-user`、`doris-mcp/mcp_svc`）；`doris-demo-sg` 上引用 `doris-mcp-rt` 的 2 条入站规则；SG `doris-mcp-rt`、`doris-mcp-vpce`；IAM 角色 `doris-mcp-gateway-role`、`doris-mcp-runtime-role`。
- 不可恢复：secret 有 7 天恢复期（`aws secretsmanager restore-secret`），其余删掉就没有了。以后要再演示，要从 P1 起重建（`infra/*.sh`、`agentcore deploy`）；Runtime / Gateway 的地址、Cognito 的 client 和 secret 都会变，Quick 的连接器要重新配置。
- 不删：`infra/state.env`（保留作删除前的记录）、日志组（审计记录；有少量存储费用，以后由用户决定）、X-Ray 设置、`CDKToolkit` 栈和它的 bucket（CDK bootstrap）、账号里别的项目的资源（`pragent-github-gw` 等）；Doris 侧的 `mcp_svc` 和 `system_mcp`（Step 4，由用户决定）；Quick 里的连接器、agent、skill（清理之后连接器不能再用）。
- 执行前的检查：调用者账号、每个资源的 `Project` 标签、Gateway 的名字、栈的标签、Cognito 域名属于哪个 pool。任何一项不符都 FATAL，一个都不删。
- 耗时 15–25 分钟，在后台运行，期间不要在 Quick 里测试。中途失败了可以重跑（已删除的会跳过），但重跑前要再 dry-run、再确认一次。
- 费用：两个 interface endpoint 停止计费，Runtime、Gateway、Cognito 不再有调用。

用户明确确认后执行，用 Bash 的 `run_in_background`（不要把输出直接显示出来，里面有资源 ID）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
APPLY=1 bash infra/99-cleanup.sh > /tmp/p5-cleanup.log 2>&1; echo "exit=$?"
```
结束的通知里只有 `exit=…` 一行。然后经 idmask 查看日志：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p5-idmask.py < /tmp/p5-cleanup.log | sed -E 's/^\[[0-9:]{8}\] /[hh:mm:ss] /'
```
期望：`exit=0`；第一行 `APPLY=1 region=us-east-1 …`，然后 `checks passed`，中间可能有几行 JSON（`delete-security-group` 的 `"Return": true` 和 `"GroupId": "<RT_SG>"` / `"<VPCE_SG>"`），最后一行：
```
[hh:mm:ss] done (deleted: Gateway target, Gateway, stack AgentCore-dorismcp-default, 3 VPC endpoints, Cognito domain, user pool, secret doris-mcp/cognito-demo-user, secret doris-mcp/mcp_svc, 2 <DORIS_SG> rules, SG <RT_SG>, SG <VPCE_SG>, role doris-mcp-gateway-role, role doris-mcp-runtime-role). Kept: … (the record), log groups, X-Ray settings. Doris side (DROP USER mcp_svc, DROP DATABASE system_mcp) is a separate step.
```
（`Kept:` 后面是 `state.env` 的路径。）

不是这样时：
- `FATAL: … (0 deleted so far)`：检查没有通过，什么都没删。把 mask 后的那一行告诉用户，查明原因（例如凭证过期）后回到 Step 1，重新确认。
- `FATAL: … (N deleted so far)`，N > 0：已经删了 N 个，最常见的是等待超时（`network interfaces still use …`：Runtime 的 ENI 在约 10 分钟内没有释放）。等几分钟，回到 Step 1 再 dry-run（已删除的显示 `already deleted`），把剩下的操作给用户看，**重新确认**后再 `APPLY=1`。
- `stack AgentCore-dorismcp-default did not reach DELETE_COMPLETE`：不要重试。只读地看失败的原因（经 idmask），告诉用户，按原因决定下一步：
  ```bash
  cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
  aws cloudformation describe-stack-events --region us-east-1 --stack-name AgentCore-dorismcp-default \
    --query "StackEvents[?ResourceStatus=='DELETE_FAILED'].[LogicalResourceId, ResourceStatusReason]" --output text \
    | .venv/bin/python /tmp/p5-idmask.py | head -20
  ```

- [ ] **Step 3：确认删干净了（只读）**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
bash infra/99-cleanup.sh 2>&1 | .venv/bin/python /tmp/p5-idmask.py | sed -E 's/^\[[0-9:]{8}\] /[hh:mm:ss] /'; echo "exit=${PIPESTATUS[0]}"
set -a; source infra/state.env; set +a
sg_rules() {
  aws ec2 describe-security-group-rules --region us-east-1 --filters "Name=group-id,Values=$DORIS_SG" \
    --query "length(SecurityGroupRules[?!IsEgress$1])" --output text
}
echo "doris-demo-sg ingress: $(sg_rules '') in all, $(sg_rules " && ReferencedGroupInfo.GroupId=='$RT_SG'") from doris-mcp-rt," \
     "$(sg_rules " && CidrIpv4=='$DEV_BOX_IP/32'") from the dev box /32, $(sg_rules " && CidrIpv4=='0.0.0.0/0'") from 0.0.0.0/0"
names() { tr '\t' '\n' | sort | paste -sd' '; }
echo "gateways: $(aws bedrock-agentcore-control list-gateways --region us-east-1 --query 'items[].name' --output text | names)"
echo "runtimes: $(aws bedrock-agentcore-control list-agent-runtimes --region us-east-1 --query 'agentRuntimes[].agentRuntimeName' --output text | names)"
echo "workload identities of this project: $(aws bedrock-agentcore-control list-workload-identities --region us-east-1 \
  --query 'workloadIdentities[].name' --output text | tr '\t' '\n' | grep -cE '^(dorismcp_dorismcp|doris-mcp-gw)-')"
echo "CDKToolkit: $(aws cloudformation describe-stacks --region us-east-1 --stack-name CDKToolkit --query 'Stacks[0].StackStatus' --output text)"
git status --short infra/state.env
bash scripts/check-secrets.sh
```
期望：
- dry-run：`checks passed` 之前只有「已经不在」的行：`Gateway <GW_ID> already deleted`、`stack AgentCore-dorismcp-default already deleted`、3 行 `VPC endpoint <VPCE_…> already deleted`、`user pool <COGNITO_POOL_ID> already deleted`、`Cognito domain <COGNITO_DOMAIN:prefix> already deleted`、2 行 `secret … already scheduled for deletion`、`<DORIS_SG> ingress from <RT_SG> already deleted`、2 行 `security group … already deleted`、2 行 `IAM role … already deleted`；最后一行 `done (dry-run, APPLY=1 would delete: nothing). …`，`exit=0`。没有 `DRY-RUN` 行。
- 还列出 `Gateway`（`DRY-RUN: aws bedrock-agentcore-control delete-gateway …`）时，是它还在 DELETING：等一分钟重跑本块，不要 `APPLY=1`。其他资源还在时，把 mask 后的输出告诉用户，回到 Step 2 的「不是这样时」。
- `doris-demo-sg ingress: 3 in all, 0 from doris-mcp-rt, 3 from the dev box /32, 0 from 0.0.0.0/0`；`gateways: pragent-github-gw`；`runtimes: doris_mcp_server harness_pragent_issue_autofix`；`CDKToolkit` 的状态和 Step 1 相同；`git status` 没有输出。
- `workload identities of this project: 0`。不是 0 时按上面发现 5 告诉用户，由用户决定（要删就是一次单独的 GATE）。
- `check-secrets.sh`：
  ```
  SKIP: secret doris-mcp/mcp_svc is scheduled for deletion (infra/99-cleanup.sh) — nothing left to compare
  SKIP: secret doris-mcp/cognito-demo-user is scheduled for deletion (infra/99-cleanup.sh) — nothing left to compare
  check-secrets: OK (… files scanned, 2 deleted secrets skipped)
  ```
  出现的是 `FAIL: cannot read secret …`，说明 Secrets Manager 对排期删除的 secret 的真实报错和 Task 5 测的不同（spec 阶段没有真的删除过）：用 `aws secretsmanager get-secret-value --region us-east-1 --secret-id doris-mcp/mcp_svc --query Name --output text 2>&1 >/dev/null | sed -E 's/arn:[^ ]+/<arn>/g'` 看报错（secret 已排期删除，读不到值）；按 TDD 修：先在 `scripts/test/test-check-secrets.sh` 的假 `aws` 里用真实的报错（RED），再改 `check-secrets.sh`（GREEN，`test-check-secrets.sh` 全部通过，`p5-mut.py … cs` 9/9），单独提交 `fix(p5): …` 之后再做 Step 5。

- [ ] **Step 4：Doris 侧和 Quick 侧（用户，可选）**

`99-cleanup.sh` 不碰 Doris 和 Quick。把下面的内容告诉用户（中文，不含地址），由用户决定做不做；AI 不执行这些语句，也不用 root：
- Doris（按 `quick/runbook.md`「演示后」第 3 条）：以后不再演示时，用户用 root 在**自己的** mysql 客户端里执行（不用 Claude Code 的 `!`）：
  ```sql
  SHOW GRANTS FOR 'mcp_svc'@'172.31.%';
  DROP USER IF EXISTS 'mcp_svc'@'172.31.%';
  DROP DATABASE IF EXISTS system_mcp;
  ```
  第一句先确认要删的正是这个账号（权限是 R-42 的两项）。`DROP DATABASE` 不带 `FORCE` 时库进回收站，`catalog_trash_expire_second`（默认 1 天）内可以 `RECOVER DATABASE system_mcp`。`ecom` 的数据和 `demo_ro` 不受影响；以后再演示要重走 P2（发布语义层）和 P3 T3.5（建账号）。
- Quick：连接器 `Doris-Desktop-MCP`、`doris-mcp`、`doris-mcp-svc`，agent「Doris 专家」「Doris 专家（svc）」和 5 个 skill 都已不能使用（Gateway 和 Cognito 已删除），删不删由用户在 Quick 里决定。

记下用户的决定（做了、没做、以后做），写进 Step 5 的日志。用户做了 Doris 侧的删除时，Step 5 同时更新 progress 的「Doris 变更」。

- [ ] **Step 5：design v1.0，收尾，提交**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
git branch --show-current; git status --short
```
期望：`p5-skills`，工作区干净。当前分支是 `main`（Task 8 之后用户已经把 `p5-skills` 合并了）时，先 `git switch -c p5-cleanup`，下面的提交落在它上面，是否合并由用户决定。

design 升到 v1.0，RESUME 的「演示当天」一行换成清理之后的说明（把 `None` 换成一句中文；每个锚点必须恰好出现 1 次）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - <<'EOF'
import pathlib, re, time
DAY = time.strftime("%Y-%m-%d", time.gmtime())
CLEAN = None  # 填写：例如「`APPLY=1 infra/99-cleanup.sh` 删除了 18 个操作列出的全部资源（约 … 分钟），第二次 dry-run 全部 already deleted，workload identity 0 个」
DORIS = None  # 填写：例如「用户已删除 `'mcp_svc'@'172.31.%'` 和 `system_mcp`」或「`mcp_svc`、`system_mcp` 保留，由用户以后决定」
assert all((CLEAN, DORIS)), "fill in every value"
p = pathlib.Path("specs/doris-mcp-quick/design.md"); s = p.read_text(encoding="utf-8")
status = re.compile(r"> 版本：\*\*v0\.9\*\* · \d{4}-\d{2}-\d{2} · 状态：P5 演示准备完成（`plans/P5-skills\.md` Task 1–8，分支 `p5-skills`；Task 9 在演示结束后清理）；")
assert len(status.findall(s)) == 1, status.pattern
s = status.sub(lambda m: f"> 版本：**v1.0** · {DAY} · 状态：P5 已完成（`plans/P5-skills.md` Task 1–9，分支 `p5-skills`；演示后已按 T5.6 清理 AWS 资源，{DORIS}）；", s)
edits = [
    ("| v0.9 | ", f"| v1.0 | T5.6 清理（Task 9，{DAY}）：{CLEAN}；Doris 侧：{DORIS}（§14）|\n| v0.9 | "),
    ("- [ ] 演示结束后执行 `infra/99-cleanup.sh`（T5.6", "- [x] 演示结束后执行 `infra/99-cleanup.sh`（T5.6"),
    ("Doris 侧的 `mcp_svc`、`system_mcp` 由用户人工删除",
     f"Doris 侧的 `mcp_svc`、`system_mcp` 由用户人工删除。{DAY} 已执行：{CLEAN}；Doris 侧：{DORIS}"),
]
for old, new in edits:
    assert s.count(old) == 1, old
    s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
r = pathlib.Path("RESUME.md"); t = r.read_text(encoding="utf-8")
old = "| 演示当天 | 按 `quick/runbook.md` 执行：演示前 30 分钟内让 Claude 跑 `scripts/demo-check.sh pre`（约 1.5 分钟），结束后跑 `post`；清理 AWS 资源要在演示结束后单独确认（GATE）|"
assert t.count(old) == 1, old
r.write_text(t.replace(old, f"| 想再演示一次 | P5 的演示已经结束，AWS 资源已在 {DAY} 按 T5.6 清理（`infra/99-cleanup.sh`；`infra/state.env` 保留的是删除前的 ID）。要再演示，得从 P1 起重建（`infra/*.sh`、`agentcore deploy`），Runtime / Gateway 的地址和 Cognito 的 client 都会变，Quick 的连接器要重新配置：先告诉 Claude，它会先写计划 |"), encoding="utf-8")
print(f"design.md: v1.0, {len(edits) + 1} edits; RESUME.md: 1 row")
EOF
git diff --stat
```
期望：`design.md: v1.0, 4 edits; RESUME.md: 1 row`；`git diff --stat` 只有 `RESUME.md` 和 `specs/doris-mcp-quick/design.md`。

勾选 T5.6，更新状态，提交（「（…）」换成实际的内容；用户没有做 Doris 侧的删除时，删掉 `Doris 变更` 那一行命令）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - T5.6 <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
echo '**P5 已完成**（`plans/P5-skills.md` Task 1–9，分支 `p5-skills`）：skills 导入、彩排 2 轮、演示，演示后按 T5.6 清理了 AWS 资源（secret 7 天内可恢复）。P0–P5 的过程见日志；要再演示，从 P1 的 `infra/*.sh` 重建' | .venv/bin/python /tmp/p5-progress.py state 阶段
echo '无（P5 已完成）' | .venv/bin/python /tmp/p5-progress.py state 进行中
echo '由用户决定：`p5-skills` 是否合并到 `main`、是否推送（D8）；Quick 里的连接器、agent、skill 是否删除（已不能使用）' | .venv/bin/python /tmp/p5-progress.py state 下一步
echo '等待用户：`p5-skills` 是否合并到 `main`、是否推送（D8）' | .venv/bin/python /tmp/p5-progress.py state 阻塞
.venv/bin/python /tmp/p5-progress.py sub '已创建的 AWS 资源' 'SG `doris-mcp-rt`、`doris-mcp-vpce`；' "**T5.6（$(date -u +%F)）已删除下列资源**（\`infra/99-cleanup.sh\`，GATE；secret 7 天内可恢复；保留：\`state.env\` 的记录、日志组、X-Ray 设置、CDKToolkit）：SG \`doris-mcp-rt\`、\`doris-mcp-vpce\`；"
.venv/bin/python /tmp/p5-progress.py sub 'Doris 变更' 'T2.5 以 root 新建库 `system_mcp`' "**T5.6（$(date -u +%F)）用户以 root 删除了 \`'mcp_svc'@'172.31.%'\` 和库 \`system_mcp\`**（回收站保留 1 天）。以下是删除前的记录：T2.5 以 root 新建库 \`system_mcp\`"
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p5-progress.py log
### @DATE@ P5 Task 9（T5.6）：演示结束后清理

- 执行前 dry-run：全部检查通过，18 个操作（和 Task 5 Step 5 相同）；`doris-demo-sg` 入站 5 条（引用 `doris-mcp-rt` 2 条、开发机 `/32` 3 条、`0.0.0.0/0` 0 条）。
- GATE：用户确认「（用户的原话）」后 `APPLY=1 bash infra/99-cleanup.sh`（后台，约（实测）分钟）：`done (deleted: Gateway target, Gateway, stack AgentCore-dorismcp-default, 3 VPC endpoints, Cognito domain, user pool, 2 secrets, 2 doris-demo-sg rules, 2 SGs, 2 roles)`（有 FATAL 和重跑时逐次写明，每次重跑的确认也写上）。
- 删除后：第二次 dry-run 全部 `already deleted` / `already scheduled for deletion`，`would delete: nothing`；`doris-demo-sg` 入站剩开发机的 3 条 `/32`；Gateway 只剩 `pragent-github-gw`，Runtime 只剩别的项目的 2 个；本项目的 workload identity（）个；`state.env` 未改；`check-secrets.sh` 跳过 2 个排期删除的 secret，OK。
- Doris 侧：（用户的决定：已删除 `'mcp_svc'@'172.31.%'` 和 `system_mcp` / 保留）；Quick 侧：（用户的决定）。
- design v1.0（§14 清理一项打勾），RESUME 的「演示当天」一行换成「想再演示一次」。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned, 2 deleted secrets skipped)
git add RESUME.md specs/doris-mcp-quick/design.md specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
if test -n "$v"; then git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); else echo "FAIL: no private IPs to check against"; fi; unset v   # 期望：0
git commit -q -F - <<'EOF'
chore(p5): T5.6 cleanup after the demo (infra/99-cleanup.sh), design v1.0

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1 | cut -c9-   # 期望：工作区干净
```
期望：`ticked: T5.6`；`阶段`、`进行中`、`下一步`、`阻塞` 各一行 `written`；`已创建的 AWS 资源 (… -> …)`、（做了 Doris 侧删除时）`Doris 变更 (… -> …)`、日志各一行 `written`；`check-secrets: OK (… files scanned, 2 deleted secrets skipped)`；`0`；工作区干净，最后一行是这个提交的标题。

然后按下面的「P5 完成标准」逐项核对，用中文告诉用户：P5 已完成（每项的结果）、清理的结果（删了什么、保留了什么、secret 的恢复期到哪天）、用户在 Doris 和 Quick 侧还可以做什么；并问用户：`p5-skills`（或 `p5-cleanup`）是否合并到 `main`（fast-forward），是否推送到私有仓库（D8，由用户决定；合并和推送都不在用户同意之前做）。

---

## P5 完成标准（对照 design §11 P5 行）

- [ ] T5.1：`quick/skills/` 下的 4 个副本和 `LICENSE.txt`、`CLI-CONTRACT.md`、`UPSTREAM.md`（共 119 个文件）由 `scripts/build_skills.py` 从锁定的 `0476f3b` 生成，`--check` 没有不同，整棵树的 sha256 与本计划一致；14 个 `SKILL.md` 都带 adapter 提示，description 都 ≤ 1024 字符，没有未列明的断链（R-50）。
- [ ] T5.2：`doris-mcp-adapter` 覆盖 `CLI-CONTRACT.md` 和副本里的每个 `doriscli` 用法，带 profile 执行的约定用 server 接受的 `max_chars`；指令加了第 5 条和时间过滤的写法；对账 12/12（R-50）。
- [ ] T5.3：用户在桌面版导入了 5 个 skill（A1 表的名字和描述与仓库一致），两个 agent 已更新，权限按 D7；A5（adapter 能不能被自动选中）和 A4（登录页的 scope，P0 评审 M-1）的结论写进了 design v0.9（R-50、D7）。
- [ ] T5.4：完整彩排 2 轮。Track A（慢查询 → profile → 解读）、Track B（DDL 评审 → 推荐 DDL，由人工执行）端到端完成，除执行 DDL 外没有人工干预；每轮前 `demo-check pre` 10/10、每轮后 `post` 5/5，答案对照了 `quick/P5-guide.md` 的参照值；每步耗时已填进 `quick/runbook.md`（R-51，design §11 P5 行）。
- [ ] 每轮彩排的审计记录数和 Gateway 的调用数已对照；失败的调用都有原因（P-10：`error`，`query_metric` 的 `where` / `having`），由 `demo-check post` 列出（R-32）。
- [ ] T5.5：彩排发现的问题逐条修了（先红后绿）或写明了不修的理由；4 项决策（Gateway `exceptionLevel`、2003 错误里的主机地址、`query_timeout`、Gateway description）由用户选定，写进 design v0.9 的 §13、§14。
- [ ] T5.7a：Runtime version 3（P-10、P-11、3 个传递依赖锁定），CodeZip 检查 0 个不同，部署前后的 7 个探针按预期（strict、intersect、mixed、or 变化，其余 3 个不变），部署后对账 12/12、权限矩阵 5/5。T5.7b：M-7–M-10 已关闭。
- [ ] T5.6：演示结束后 `infra/99-cleanup.sh` 删除了本项目的全部 AWS 资源，第二次 dry-run 全部是 already deleted；`doris-demo-sg` 只剩开发机的 `/32` 规则，没有 `0.0.0.0/0`（R-40）；别的项目的资源都还在；`state.env` 保留；Doris 侧和 Quick 侧的决定已记录。
- [ ] 每个 GATE（Task 6 部署、Task 8 改 Gateway 或再部署（如果做了）、Task 9 清理）都先展示了命令和 dry-run / diff，progress 日志里有用户确认的原话（R-44）。
- [ ] 测试全部通过：`doris/test` 168 个、`scripts/test` 137 个、`quick/test` 60 个、`test_agentcore_*.py` 141 个、upstream 离线测试、9 组 shell 测试；14 组突变（共 220 个）全部被抓到。
- [ ] P5 的提交里没有密码、secret、token、Doris 主机地址、私网 IP 和开发机 IP：每次提交前 `check-secrets.sh` 都是 OK（清理之后跳过 2 个排期删除的 secret），暂存区新增行的 IP 计数都是 0，`$v` 为空时输出 FAIL（R-43、M-10）。
- [ ] 每个任务都有对应的提交和 progress 日志条目，新会话按 `CLAUDE.md` 能接着做（R-60）；新的 `infra/99-cleanup.sh` 默认 dry-run，可以重跑（R-61）。
- [ ] 整体评审（opus，Task 7 Step 2）已完成：Critical / Important 都已修复，每个修复都有先红后绿的测试；Minor 在 Task 8 Step 1 逐条处理。
- [ ] 合并方式和是否推送到私有仓库 `lijingfz/Doris-mcp-skill-Demo` 由用户决定（D8），推送前再确认一次。
