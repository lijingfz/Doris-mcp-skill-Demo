# P0 技术验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans（推荐，P0 有多个交互式 GATE）或 superpowers:subagent-driven-development 按任务执行本计划。步骤用复选框（`- [ ]`）跟踪。
> **断线恢复：** 先按仓库根目录 `CLAUDE.md` 的恢复协议执行，再从 `progress.md`「当前状态」里写的任务/步骤继续。本计划里所有命令都在仓库根目录 `/home/ubuntu/AI-code/Doris-mcp-skill-Demo` 下运行，除非步骤里明确写了 `cd`。

**Goal:** 写业务代码之前，用最小 MCP（只有一个 `net_check` 工具）跑通「VPC 网络 → AgentCore Runtime → AgentCore Gateway → Quick 桌面版」整条链路，并量出冷启动耗时、确认 OAuth 回调 URL 和 scope 行为。

**Architecture:** 幂等 AWS CLI 脚本（`infra/*.sh`，默认 dry-run）建 SG、VPC endpoints、Cognito、Gateway；agentcore CLI（`dorismcp/` 项目）把 `spike/p0-mcp/` 以 CodeZip 部署为 VPC 模式的 Runtime `dorismcp`；Gateway 用 CUSTOM_JWT 入站、IAM SigV4 出站调用 Runtime。P3 只把 codeLocation 换成 `../mcp-server/`，Runtime ARN 不变，Gateway target 继续有效。

**Tech Stack:** AWS CLI 2.36.36 · agentcore CLI 0.30.0（CDK，账号已 bootstrap）· Python 3.12 + FastMCP 3.4.4 · uv/uvx · `mcp-proxy-for-aws` · Cognito · Amazon Quick 桌面版（Enterprise）

**Spec:** `specs/doris-mcp-quick/requirements.md`（R-10/11/13/30/40/41/44/60/61）、`specs/doris-mcp-quick/design.md`（§3、§4.3–§4.5、§6.4、§7、§8、§11 P0 行）

## Global Constraints

- 区域 `us-east-1`，账号 `890717383483`，VPC `vpc-0b806cad7faf55718`；所有 ID 从 `infra/state.env` 读取，不在命令里手写。
- **GATE**：创建或修改 AWS 资源、安全组、Doris 账号之前，先展示 dry-run 输出，**用户明确确认后**才执行 `APPLY=1 …`；一次确认只对应一次执行。确认记录写进 progress.md 日志。
- 安全组不出现 `0.0.0.0/0` / `::/0` 入站；新增规则只用 SG 引用；`doris-demo-sg` 现有 `13.125.9.110/32` 规则不动。
- secret（Cognito client secret、演示用户密码、Doris 密码）不出现在命令行参数、日志、对话输出、仓库里。**不要打印 `GW_TOKEN`**。
- 用户获取 secret 时，在**自己的终端**里执行命令，不用 Claude Code 的 `!` 前缀（否则会进入对话记录）。
- 不修改、不删除账号里已有的 Gateway `pragent-github-gw`（属于其他项目）。
- Runtime 名 `dorismcp`（部署后 AWS 侧名称为 `dorismcp_dorismcp`），Gateway `doris-mcp-gw`，target `doris`，工具在 Gateway 上显示为 `doris___net_check`。
- 每个任务结束：勾选 `tasks.md` → 更新 `progress.md`（「当前状态」+ 追加日志）→ `bash scripts/check-secrets.sh` → commit（message 结尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`）。不 push。

## Review Focus

1. **Runtime ENI 出不了网**（缺 endpoint 或 SG 少一条出站）：旧仓库的表现是冷启动约 30 s 后超时、CloudWatch 没有任何日志。T0.4 冒烟失败时先按排障表检查 endpoint 状态和 `doris-mcp-rt` 的 4 条出站，而不是改代码。
2. **脚本重跑不能产生第二份资源**（R-61）：T0.2 / T0.5 / T0.6 执行完之后各再跑一次 dry-run，确认没有 `create-*` 行。
3. **Quick 实际使用的回调 URL 与默认值不同**：T0.7 以 UI 显示的值为准，不一致时用 `QUICK_CALLBACK=… bash infra/20-cognito.sh` 更新 client A（走 GATE）。
4. **scope 被 Quick 忽略或替换**：Gateway 会在 PRM 里声明 `doris-mcp/invoke`；T0.6 先确认 PRM 内容，T0.7 若鉴权失败，按 §T0.7 的回退顺序处理。
5. **冷启动 + 首次调用超过 Quick 的 60 s**：T0.4 / T0.6 / T0.7 都要记录冷启动和热调用耗时；超过 40 s 就在 T0.8 里提出预热 / idle timeout 方案。

---

## 文件地图

| 文件 | 状态 | 作用 |
|---|---|---|
| `infra/lib.sh` | 已有（spec 阶段写好并验证）| `run`（dry-run / APPLY）、`state_set`、`render`、`private_tmp`、`runtime_url`、`tags` |
| `infra/10-network.sh` | 已有 | SG `doris-mcp-rt` / `doris-mcp-vpce`、Doris SG 引用规则、S3 / logs / secretsmanager endpoints、自检 |
| `infra/25-runtime-state.sh` | 已有 | 只读：查出已部署的 `dorismcp_dorismcp`，记录 `RUNTIME_ARN/ID/ROLE_ARN/URL` |
| `infra/20-cognito.sh` | 已有 | user pool、域名、resource server、client A（`quick-user`）/ B（`quick-service`）、演示用户 `demo` |
| `infra/30-gateway.sh` | 已有 | Gateway 服务角色、Gateway `doris-mcp-gw`、target `doris` |
| `infra/policies/*.json` | 已有 | Gateway 信任 / 调用策略、本机 proxy 最小策略 |
| `spike/p0-mcp/` | 已有 | 最小 MCP：`net_check`（MySQL 握手 + FE HTTP）、`/ping`；8 个单测 |
| `scripts/mcp_smoke.py` | 已有 | `list [--expect N]` / `call TOOL [json]`，HTTP 或 stdio |
| `scripts/get-gw-token.sh` | 已有 | client B 取 token（stdout）或 `--claims` |
| `scripts/render-agentcore.py` | 已有 | 按 state.env 写 `agentcore.json` 的 runtime 条目 + `aws-targets.json` |
| `scripts/render-local-connector.py` | 已有 | 写 `quick/local-connector.json` |
| `dorismcp/` | **T0.4 创建** | `agentcore create` 生成的项目 |
| `quick/local-connector.json` | **T0.7 创建** | 桌面版 Local stdio 连接器配置 |

---

### Task T0.1：工具准备

**Files:** 无代码改动（只安装工具、跑自检）；更新 `tasks.md`、`progress.md`

**Interfaces:**
- Produces：全局命令 `agentcore`（0.30.0）；仓库 `.venv/`（Python 3.12，装有 spike 依赖，供 `scripts/mcp_smoke.py` 使用）

- [ ] **Step 1：安装 agentcore CLI 并检查版本**

```bash
npm i -g @aws/agentcore@0.30.0     # nvm 的全局目录属于 ubuntu 用户，不需要 sudo
agentcore --version                # 期望：0.30.0
node --version; uv --version; aws --version
aws sts get-caller-identity --query Arn --output text
```
期望：Node v22.x、uv 0.11.x、aws-cli/2.36.x；调用者 `arn:aws:iam::890717383483:user/jingamz`。

- [ ] **Step 2：建本地 venv**

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r spike/p0-mcp/pyproject.toml
.venv/bin/python -c "import fastmcp; print(fastmcp.__version__)"
```
期望：`3.4.4`。

- [ ] **Step 3：lib.sh 自检（不碰 AWS 资源，用临时 state 文件）**

```bash
cp infra/state.env /tmp/state.selftest
STATE_FILE=/tmp/state.selftest bash -c '
  source infra/lib.sh
  run echo would-mutate                 # 期望：DRY-RUN: echo would-mutate
  state_set SELFTEST dry                # 期望：DRY-RUN: state_set SELFTEST=dry（不写文件）
  APPLY=1; state_set SELFTEST one; state_set SELFTEST two
  grep -c "^SELFTEST=two$" "$STATE_FILE"  # 期望：1（upsert，不会重复）
  runtime_url arn:aws:bedrock-agentcore:us-east-1:890717383483:runtime/dorismcp_dorismcp-abc1234567; echo'
rm -f /tmp/state.selftest
for f in infra/*.sh scripts/*.sh; do bash -n "$f" || echo "SYNTAX: $f"; done
```
期望：`runtime_url` 输出 `https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A890717383483%3Aruntime%2Fdorismcp_dorismcp-abc1234567/invocations?qualifier=DEFAULT`；没有 `SYNTAX:` 行。

- [ ] **Step 4：收尾**

勾选 T0.1，progress 记录工具版本。
```bash
bash scripts/check-secrets.sh
git add specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "chore(p0): T0.1 toolchain ready (agentcore 0.30.0, .venv)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T0.2：网络（SG + VPC endpoints）[GATE]

**Files:** `infra/state.env`（脚本写入）；`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：state.env 里的 `VPC_ID MAIN_RTB S3_PREFIX_LIST DORIS_SG SUBNET_AZ4 SUBNET_AZ1`
- Produces：state.env 新增 `RT_SG VPCE_SG VPCE_S3 VPCE_LOGS VPCE_SECRETSMANAGER`（T0.4 的 `render-agentcore.py` 要用 `RT_SG`）

- [ ] **Step 1：dry-run**

```bash
bash infra/10-network.sh 2>&1 | tee /tmp/t02-dryrun.log | grep -c '^DRY-RUN: aws'
```
期望：`14`（2 × create-security-group、2 × revoke 默认出站、`doris-mcp-rt` 4 条出站、`doris-mcp-vpce` 1 条入站、`doris-demo-sg` 2 条入站、1 个 S3 Gateway endpoint、2 个 Interface endpoint）。

- [ ] **Step 2：GATE —— 把 `/tmp/t02-dryrun.log` 中的 `DRY-RUN:` 行整理成表格给用户看，等待确认**

需要特别说明：`doris-demo-sg` 只新增两条**来源为 SG 引用**的规则（9030、8030）；S3 Gateway endpoint 挂在主路由表上；Interface endpoint 开 private DNS（VPC 内只有 Doris 一台 EC2，它不调用 AWS API）；Interface endpoint 按小时计费（2 个 × 2 AZ）。

- [ ] **Step 3：执行**（仅在用户确认后）

```bash
APPLY=1 bash infra/10-network.sh 2>&1 | tee /tmp/t02-apply.log | tail -15
```
期望：结尾有 3 行 `self-check sg-…: no open inbound rule`，然后列出 `doris-mcp-rt` 的 4 条出站规则（9030/8030 → `sg-0a02e336df4299888`，443 → `VPCE_SG`，443 → `pl-63a5400a`），最后 `done (APPLY=1)`。

- [ ] **Step 4：验证 state 与幂等**

```bash
grep -E '^(RT_SG|VPCE_SG|VPCE_S3|VPCE_LOGS|VPCE_SECRETSMANAGER)=' infra/state.env   # 期望：5 行
bash infra/10-network.sh 2>&1 | grep -c '^DRY-RUN: aws'                             # 期望：0（R-61）
source infra/state.env
aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$DORIS_SG" \
  --query 'SecurityGroupRules[?!IsEgress].[FromPort,CidrIpv4||ReferencedGroupInfo.GroupId]' --output text | sort
```
期望：最后一条命令的输出是原有 `13.125.9.110/32` 的 22/8030/9030 三条 + 新增 `8030 $RT_SG`、`9030 $RT_SG` 两条，没有别的。
```bash
aws ec2 describe-vpc-endpoints --vpc-endpoint-ids "$VPCE_S3" "$VPCE_LOGS" "$VPCE_SECRETSMANAGER" \
  --query 'VpcEndpoints[].[ServiceName,State,PrivateDnsEnabled]' --output text
```
期望：3 行都是 `available`；两个 Interface endpoint 的 PrivateDnsEnabled 为 `True`。

- [ ] **Step 5：收尾**

progress 日志写明「用户确认 → APPLY」的时间和新建资源 ID。
```bash
bash scripts/check-secrets.sh
git add infra/state.env specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "infra(p0): T0.2 runtime/vpce SGs, Doris SG refs, S3/logs/secretsmanager endpoints

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T0.3：spike MCP 本地测试

**Files:** `spike/p0-mcp/{mcp_server.py,test_spike.py,pyproject.toml}`、`scripts/mcp_smoke.py`（均已在 spec 阶段写好，本任务只做验证；如果有失败，修复后再提交）

**Interfaces:**
- Produces：工具 `net_check() -> {"target": str, "mysql": {"port", "ok", "ms", "server_version"|"error"}, "http": {"port", "ok", "ms", "status"|"error"}}`；`GET /ping -> {"status": "Healthy"}`；监听 `0.0.0.0:$MCP_PORT/mcp`（默认 8000，stateless streamable HTTP）

- [ ] **Step 1：单测**

```bash
(cd spike/p0-mcp && ../../.venv/bin/python -m unittest -v)
```
期望：`Ran 8 tests … OK`。

- [ ] **Step 2：本机对 Doris 公网 IP 实测**（只取 `DORIS_HOST`，不把密码带进进程环境）

```bash
DORIS_PUBLIC_IP="$(source /home/ubuntu/AI-code/Doris-test/credentials.env; printf %s "$DORIS_HOST")"
DORIS_HOST="$DORIS_PUBLIC_IP" MCP_PORT=8765 .venv/bin/python spike/p0-mcp/mcp_server.py > /tmp/spike.log 2>&1 &
sleep 3
curl -s http://127.0.0.1:8765/ping                                               # {"status":"Healthy"}
.venv/bin/python scripts/mcp_smoke.py --url http://127.0.0.1:8765/mcp list --expect 1
.venv/bin/python scripts/mcp_smoke.py --url http://127.0.0.1:8765/mcp call net_check
kill %1
```
期望：`net_check  [readOnly]`、`tools: 1`；`mysql.ok=true`、`server_version="5.7.99"`；`http.ok=true`、`status=200`。

- [ ] **Step 3：收尾**

```bash
find spike scripts -name __pycache__ -prune -exec rm -rf {} +
bash scripts/check-secrets.sh
git add -A spike scripts specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "test(p0): T0.3 spike net_check verified locally against Doris

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T0.4：部署 spike Runtime（VPC 模式）[GATE]

**Files:**
- Create：`dorismcp/`（由 `agentcore create` 生成）
- Modify：`dorismcp/agentcore/agentcore.json`、`dorismcp/agentcore/aws-targets.json`（由 `scripts/render-agentcore.py` 写入）
- Modify：`infra/state.env`（`infra/25-runtime-state.sh` 写入）

**Interfaces:**
- Consumes：state.env 的 `DORIS_PRIVATE_IP SUBNET_AZ4 SUBNET_AZ1 SUBNET_AZ2 RT_SG`
- Produces：state.env 的 `RUNTIME_ARN RUNTIME_ID RUNTIME_ROLE_ARN RUNTIME_URL`（T0.6 的 Gateway target 和 T0.7 的 Local 连接器都要用）

- [ ] **Step 1：生成 agentcore 项目**

```bash
agentcore create --project-name dorismcp --no-agent --skip-git --output-dir .
ls -a dorismcp/agentcore     # 期望：agentcore.json  aws-targets.json  cdk/  .gitignore（可能还有 .llm-context/）
cat dorismcp/agentcore/.gitignore
```
期望 `.gitignore` 里忽略 `cdk/cdk.out/`、`cdk/node_modules/`、`.cli/*`（保留 `.cli/deployed-state.json`）、`.cache/*`。如果 CLI 进入交互提问或参数报错：运行 `agentcore create --help`，按实际参数调整，并把差异写进 progress。

- [ ] **Step 2：写入 runtime 条目**

```bash
python3 scripts/render-agentcore.py --phase spike --check    # 先看将要写入的内容
python3 scripts/render-agentcore.py --phase spike
python3 -m json.tool dorismcp/agentcore/agentcore.json | sed -n '/"runtimes"/,/^  ]/p'
```
期望：`codeLocation: "../spike/p0-mcp/"`、`build: CodeZip`、`runtimeVersion: PYTHON_3_12`、`protocol: MCP`、`authorizerType: AWS_IAM`、`networkMode: VPC`、3 个子网 + `RT_SG`；envVars 只有 `DORIS_HOST=172.31.25.143`、`DORIS_PORT=9030`、`DORIS_HTTP_PORT=8030`。

- [ ] **Step 3：校验与部署预览**

```bash
cd dorismcp && agentcore validate && agentcore deploy --dry-run -v 2>&1 | tee /tmp/t04-dryrun.log | tail -40; cd ..
```
如果提示找不到项目，改在 `dorismcp/agentcore` 目录下执行（旧仓库就是在这个目录执行的），并记录下来。

- [ ] **Step 4：GATE —— 向用户说明将要创建的资源，等待确认**

CloudFormation 栈 `AgentCore-dorismcp-default`（CDK 资产上传到已有的 bootstrap bucket）、Runtime `dorismcp_dorismcp` 及其执行角色（CDK 生成）、Runtime 在 3 个子网里的 ENI（挂 `doris-mcp-rt`）。附上 `/tmp/t04-dryrun.log` 的关键部分。

- [ ] **Step 5：部署**（仅在用户确认后；通常需要 3–10 分钟，放后台跑并写日志）

```bash
(cd dorismcp && agentcore deploy -y -v) > /tmp/t04-deploy.log 2>&1; echo "exit=$?"
tail -30 /tmp/t04-deploy.log
(cd dorismcp && agentcore status --json)
```
期望：`exit=0`；status 显示 runtime READY。

- [ ] **Step 6：记录 Runtime 到 state.env**（AWS 侧只读；`APPLY=1` 只是允许写 state.env，不属于 GATE 操作）

```bash
bash infra/25-runtime-state.sh            # 先看一眼：status=READY
APPLY=1 bash infra/25-runtime-state.sh
grep -E '^RUNTIME_(ARN|ID|ROLE_ARN|URL)=' infra/state.env    # 期望：4 行
```

- [ ] **Step 7：SigV4 冒烟 + 冷启动计时**

```bash
source infra/state.env
PROXY="uvx mcp-proxy-for-aws@latest $RUNTIME_URL --service bedrock-agentcore --region $AWS_REGION --timeout 55"
.venv/bin/python scripts/mcp_smoke.py --stdio "$PROXY" call net_check     # 第 1 次 = 冷启动
.venv/bin/python scripts/mcp_smoke.py --stdio "$PROXY" call net_check     # 第 2 次 = 热
.venv/bin/python scripts/mcp_smoke.py --stdio "$PROXY" list --expect 1
```
期望：`target` 为 `172.31.25.143`，`mysql.ok=true`（`server_version=5.7.99`），`http.ok=true`（`status=200`）。把两次的 `connected+initialized` / `total` 毫秒数记入 progress。

- [ ] **Step 8：看 CloudWatch 日志**

```bash
aws logs describe-log-groups --log-group-name-prefix /aws/bedrock-agentcore/runtimes/ \
  --query 'logGroups[].logGroupName' --output text
aws logs tail "/aws/bedrock-agentcore/runtimes/${RUNTIME_ID}-DEFAULT" --since 30m | tail -30
```
期望：能看到 uvicorn 启动日志和 `POST /mcp` 请求。日志组名和上面不一致时，以第一条命令查到的为准，并记录下来。

**排障表（Step 7 失败时）：**

| 现象 | 最可能的原因 | 检查 |
|---|---|---|
| 约 30 s 超时，CloudWatch 没有任何日志 | ENI 拉不到代码包或写不了日志 | `describe-vpc-endpoints` 状态；`doris-mcp-rt` 是否有 443 → `pl-63a5400a` 和 443 → `VPCE_SG`；`doris-mcp-vpce` 入站是否允许 `RT_SG` |
| 日志里有启动记录，`mysql.ok=false` | Doris SG 没放行 | `doris-demo-sg` 是否有 9030 ← `RT_SG`；Doris 进程是否在跑 |
| `mysql.ok=true`，`http.ok=false` | 8030 规则缺失 | 同上，检查 8030 |
| 403 / AccessDenied | 本机凭证没有 InvokeAgentRuntime 权限 | `aws sts get-caller-identity`；确认 ARN 与 qualifier |
| proxy 报协议 / URL 错误 | `mcp-proxy-for-aws` 与 Runtime URL 不兼容 | 先加 `--log-level DEBUG` 看请求；仍不行就给 `mcp_smoke.py` 加 SigV4 `httpx.Auth`（botocore `SigV4Auth`，service `bedrock-agentcore`），直接走 `--url`，并在 progress 记录，T0.7 的 Local 路径改用旧仓库的 token proxy 方案 |
| deploy 报缺 `pyproject.toml` 或 ELOOP | codeLocation 路径不对或有循环 symlink | codeLocation 相对 `dorismcp/`；`find spike/p0-mcp -type l` |

- [ ] **Step 9：收尾**

```bash
git status --short dorismcp | head -30      # 不应出现 node_modules、cdk.out、.cache
git status --short spike | head            # 不应出现 spike/p0-mcp/agentcore/（CodeZip 打包目录，已在 .gitignore）
bash scripts/check-secrets.sh
git add dorismcp infra/state.env specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "deploy(p0): T0.4 spike runtime dorismcp in VPC mode, SigV4 smoke ok

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T0.5：Cognito [GATE]

**Files:** `infra/state.env`（脚本写入）；`tasks.md`、`progress.md`

**Interfaces:**
- Produces：state.env 的 `COGNITO_POOL_ID COGNITO_DOMAIN DISCOVERY_URL QUICK_CALLBACK CLIENT_A_ID CLIENT_B_ID`；Secrets Manager `doris-mcp/cognito-demo-user`（`{"username","password"}`）

- [ ] **Step 1：dry-run**

```bash
bash infra/20-cognito.sh 2>&1 | tee /tmp/t05-dryrun.log | grep 'DRY-RUN'
```
期望：6 条命令（create-user-pool、create-user-pool-domain、create-resource-server、create-user-pool-client × 2 即 `quick-user` / `quick-service`、admin-create-user），以及两行日志说明（创建 demo 用户密码 secret、设置永久密码）。

- [ ] **Step 2：GATE —— 展示并等待确认**

需要说明：user pool 只允许管理员建用户；client A 的回调 URL 先用默认值 `https://us-east-1.quicksight.aws.amazon.com/sn/oauthcallback`，T0.7 以 Quick UI 显示的为准；演示用户密码随机生成，只存在 Secrets Manager 里。

- [ ] **Step 3：执行**（仅在用户确认后）

```bash
APPLY=1 bash infra/20-cognito.sh 2>&1 | tee /tmp/t05-apply.log | tail -12
grep -E '^(COGNITO_POOL_ID|COGNITO_DOMAIN|DISCOVERY_URL|QUICK_CALLBACK|CLIENT_A_ID|CLIENT_B_ID)=' infra/state.env   # 6 行
```

- [ ] **Step 4：验证 discovery 与 token**（Cognito 域名生效可能要 1 分钟左右）

```bash
source infra/state.env
curl -s "$DISCOVERY_URL" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["issuer"]); print(d["token_endpoint"]); print(d["authorization_endpoint"])'
bash scripts/get-gw-token.sh --claims
```
期望：issuer = `https://cognito-idp.us-east-1.amazonaws.com/$COGNITO_POOL_ID`；token / authorize endpoint 在 `https://$COGNITO_DOMAIN/oauth2/…` 下；claims 中 `client_id=$CLIENT_B_ID`、`scope=doris-mcp/invoke`、`token_use=access`。

- [ ] **Step 5：幂等检查**

```bash
bash infra/20-cognito.sh 2>&1 | grep '^DRY-RUN'
```
期望：只有一行 `update-user-pool-client … quick-user …`（脚本每次都会重新同步 client A 的回调 URL），没有 `create-*`。

- [ ] **Step 6：收尾**

```bash
bash scripts/check-secrets.sh
git add infra/state.env specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "infra(p0): T0.5 Cognito pool, domain, clients A/B, demo user

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T0.6：Gateway [GATE]

**Files:** `infra/state.env`（脚本写入）；`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：`RUNTIME_ARN`（T0.4）、`DISCOVERY_URL CLIENT_A_ID CLIENT_B_ID`（T0.5）
- Produces：state.env 的 `GW_ROLE_ARN GW_ID GW_URL GW_TARGET_ID`

- [ ] **Step 1：dry-run**

```bash
bash infra/30-gateway.sh 2>&1 | tee /tmp/t06-dryrun.log | grep -E 'DRY-RUN|"Resource"|aws:Source'
```
期望：create-role、put-role-policy、create-gateway（`--authorizer-configuration` 里有 `allowedClients`=[A,B] 和 `allowedScopes`=["doris-mcp/invoke"]）、create-gateway-target（endpoint = `RUNTIME_URL`，`GATEWAY_IAM_ROLE`）；渲染出的两份策略里资源是真实的 Runtime ARN。

- [ ] **Step 2：GATE —— 展示并等待确认**

需要说明：IAM 角色只能被本账号的 AgentCore Gateway assume，只允许对 `dorismcp_dorismcp` 调用 `InvokeAgentRuntime`；P0 使用 `--exception-level DEBUG`（错误详情会返回给客户端，P3 再评估是否关闭）。

- [ ] **Step 3：执行**（仅在用户确认后）

```bash
APPLY=1 bash infra/30-gateway.sh 2>&1 | tee /tmp/t06-apply.log | tail -10
grep -E '^(GW_ROLE_ARN|GW_ID|GW_URL|GW_TARGET_ID)=' infra/state.env    # 4 行
```
期望：`get-gateway → READY`、`get-gateway-target → READY`。target 状态为 FAILED 时，脚本会打印 statusReasons —— 通常是 Gateway 调 Runtime 被拒（检查角色策略）或 Runtime 的 `tools/list` 失败（先回到 T0.4 Step 7）。

- [ ] **Step 4：不带 token 的请求 → 401 + PRM**

```bash
source infra/state.env
curl -s -D - -o /dev/null -X POST "$GW_URL" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | grep -iE '^HTTP|^www-authenticate'
```
期望：`HTTP/… 401` 和 `WWW-Authenticate: Bearer … resource_metadata="https://…"`（可能还带 `scope=`）。再取 PRM：
```bash
PRM_URL="$(curl -s -D - -o /dev/null -X POST "$GW_URL" -H 'Content-Type: application/json' -d '{}' \
  | sed -n 's/.*resource_metadata="\([^"]*\)".*/\1/Ip' | tr -d '\r')"
curl -s "$PRM_URL" | python3 -m json.tool
```
期望：`authorization_servers` 指向 Cognito issuer，`scopes_supported` 包含 `doris-mcp/invoke`。把 401 头和 PRM 原文记入 progress（T0.7 排障要用）。

- [ ] **Step 5：带 token 冒烟 + 计时**

```bash
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"      # 只放进环境变量，不要 echo
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN list --expect 1
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN call doris___net_check
GW_TOKEN=invalid .venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN list; echo "exit=$?"
unset GW_TOKEN
```
期望：`doris___net_check  [readOnly]`、`tools: 1`；调用结果与 T0.4 相同；无效 token 那次以 401 失败退出（exit 非 0）。如果列出的工具多于 1 个（例如 Gateway 内置工具），记录工具名，并把 T3.4 / T4.1 的期望数量相应调整。记录耗时。

- [ ] **Step 6：幂等检查 + 收尾**

```bash
bash infra/30-gateway.sh 2>&1 | grep '^DRY-RUN'
```
期望：只有 put-role-policy 和 update-gateway（脚本每次重新下发策略和鉴权配置），没有 `create-*`。
```bash
bash scripts/check-secrets.sh
git add infra/state.env specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "infra(p0): T0.6 gateway doris-mcp-gw (CUSTOM_JWT in, IAM SigV4 out), token smoke ok

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T0.7：Quick 桌面版接入 [USER]

**Files:** Create `quick/local-connector.json`（Claude 生成）；`progress.md`（记录用户反馈）

- [ ] **Step 1（Claude）：准备材料**

```bash
python3 scripts/render-local-connector.py            # 写 quick/local-connector.json
source infra/state.env
printf 'MCP URL:        %s\nToken URL:      https://%s/oauth2/token\nAuthorize URL:  https://%s/oauth2/authorize\nClient A ID:    %s\nClient B ID:    %s\nPool ID:        %s\nCallback (now): %s\n' \
  "$GW_URL" "$COGNITO_DOMAIN" "$COGNITO_DOMAIN" "$CLIENT_A_ID" "$CLIENT_B_ID" "$COGNITO_POOL_ID" "$QUICK_CALLBACK"
```
把以上**非敏感**信息和下面的操作步骤一起发给用户。

- [ ] **Step 2（用户）：在自己的终端里取 secret**（不要用 Claude Code 的 `!` 前缀）

```bash
aws cognito-idp describe-user-pool-client --user-pool-id <Pool ID> --client-id <Client A ID> \
  --query UserPoolClient.ClientSecret --output text                      # client A secret
aws cognito-idp describe-user-pool-client --user-pool-id <Pool ID> --client-id <Client B ID> \
  --query UserPoolClient.ClientSecret --output text                      # client B secret（Part B 用）
aws secretsmanager get-secret-value --secret-id doris-mcp/cognito-demo-user \
  --query SecretString --output text                                     # demo 用户名和密码
```

- [ ] **Step 3（用户）：Part A —— Cloud Connector，User auth（主路径）**

1. 桌面版 **Customize → Connectors → Create → Cloud Connector → MCP**，名称 `doris-mcp`，URL 填 `MCP URL`。
2. 鉴权选 **User authentication**：Client ID / Secret 填 client A；Token URL、Authorization URL 按 Step 1。
3. **记下 UI 上显示的 Redirect / Callback URL**。如果它和 `Callback (now)` 不同，先告诉 Claude：Claude 运行 `QUICK_CALLBACK='<UI 上的 URL>' bash infra/20-cognito.sh` 展示 dry-run（只有一行 update-user-pool-client），用户确认后 `APPLY=1` 执行，再继续。
4. 用 `demo` 用户登录授权。
5. 在连接器详情里启用 `doris___net_check`（新工具默认禁用）。
6. 新建对话：「调用 doris___net_check 检查 Doris 连通性，原样给出结果」。期望返回 `mysql.ok=true`、`http.ok=true`。

鉴权失败时的回退顺序（每一步都告诉 Claude 现象，由 Claude 执行并走 GATE）：
① 看 Quick 的错误信息是否提到 scope → Claude 对照 T0.6 Step 4 记录的 PRM 检查；
② `GW_ALLOWED_SCOPES= bash infra/30-gateway.sh`（去掉 scope 限制）→ GATE → `APPLY=1`，重试；
③ 仍失败 → 用 Part B 的 Service auth 作为主路径，并在 T0.8 记录。

- [ ] **Step 4（用户）：Part B —— Cloud Connector，Service auth（R-13）**

再建一个连接器 `doris-mcp-svc`：同一个 URL，鉴权选 **Service authentication**，填 client B 的 ID / Secret 和 Token URL，scope（如果 UI 要求填写）为 `doris-mcp/invoke`。启用工具并调用一次。验证完可以先禁用，保留配置。

- [ ] **Step 5（用户）：Part C —— Local stdio（备份路径，R-11）**

前提：Quick 桌面版所在的电脑上装了 `uv`（`uvx`），并有一个 AWS profile `doris-demo`，其凭证有权对该 Runtime 调用 `bedrock-agentcore:InvokeAgentRuntime`（最小策略见 `infra/policies/local-proxy.json`，把 `${RUNTIME_ARN}` 换成 state.env 里的值）。推荐用 IAM Identity Center（SSO）profile；如果需要专用 IAM 用户，告诉 Claude，Claude 会准备命令并走 GATE。
1. 先在本机终端验证：`AWS_PROFILE=doris-demo uvx mcp-proxy-for-aws@latest '<RUNTIME_URL>' --service bedrock-agentcore --region us-east-1 --timeout 55`，能启动、不报错即可（Ctrl-C 退出）。
2. 桌面版 **Customize → Connectors → Local → Import**，导入 `quick/local-connector.json`（或选 Local stdio，按文件里的 command / args / env 手工填写）。profile 名不同的话，让 Claude 用 `python3 scripts/render-local-connector.py --aws-profile <名称>` 重新生成。
3. 启用工具（这条路径的工具名没有 `doris___` 前缀，是 `net_check`），调用一次。

- [ ] **Step 6（用户 → Claude）：回报结果**

请按下面的格式回复（不要包含任何 secret）：
```
Callback URL（UI 显示）：
Part A User auth：成功/失败（错误信息）；登录后首次调用耗时约 __ s
Part B Service auth：成功/失败（错误信息）
Part C Local stdio：成功/失败（错误信息）；工具名：
其他观察：
```
Claude 把回报内容写进 progress 日志，勾选 T0.7 并提交：
```bash
bash scripts/check-secrets.sh
git add quick/local-connector.json infra/state.env specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "test(p0): T0.7 Quick desktop connectors (user auth / service auth / local stdio)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T0.8：P0 结论

**Files:** Modify `specs/doris-mcp-quick/design.md`（§4.4、§4.5、§13、变更记录）、`tasks.md`、`progress.md`

- [ ] **Step 1：更新 design.md**

- §4.4：回调 URL 从 ❓ 改为 ✅（写实际值）；User / Service / Local 三条路径的实测结果。
- §4.5：401 头、PRM 内容、scope 的实际行为；Gateway 工具列表是否只有 target 工具。
- §13：用实测数字替换「Quick 60 s 硬超时」一行里的估计；如果冷启动 + 首次调用 > 40 s，写出预热方案（演示前 5 分钟调用一次 `check_service_health`；评估 Runtime idle timeout 配置）。
- 记录 agentcore CLI 0.30.0 与旧仓库 v0.19 的差异（命令、生成的文件、执行目录）。
- 标注待 P3 复查：`--exception-level DEBUG`。
- 变更记录加一行 v0.3。

- [ ] **Step 2：P3 路径决策**

根据 T0.7 的结果，在 progress「当前状态」写明：P4 的主路径（User auth 或 Service auth）、备份路径是否可用、是否需要改动 T3.x / T4.x。需要改动时同步修改 `tasks.md`。

- [ ] **Step 3：收尾**

```bash
bash scripts/check-secrets.sh
git add specs/doris-mcp-quick
git commit -m "docs(p0): T0.8 record P0 findings (callback, scope, cold start, CLI diffs)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## P0 退出标准（design §11）

- [ ] Runtime 内 TCP 能连通 `172.31.25.143:9030/8030`（T0.4 Step 7）
- [ ] 经 Gateway 能列出并调用 `doris___net_check`（T0.6 Step 5）
- [ ] 桌面版至少一条 Cloud Connector 路径 + Local stdio 路径都能调用（T0.7）
- [ ] 冷启动 / 热调用耗时、OAuth 回调 URL、scope 行为都已记录（T0.8）
