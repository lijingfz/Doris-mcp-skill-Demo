# P4 Quick 桌面版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务执行本计划。步骤用复选框（`- [ ]`）跟踪。
> **断线恢复：** 先按仓库根目录 `CLAUDE.md` 的恢复协议执行，再从 `progress.md`「当前状态」里写的任务/步骤继续。本计划里所有命令都在仓库根目录 `/home/ubuntu/AI-code/Doris-mcp-skill-Demo` 下运行（每个 bash 块第一行都是 `cd` 到这里）。执行顺序就是编号顺序：**Task 1（T4.5）→ Task 2（T4.3）→ Task 3（T4.6）→ Task 4（T4.1 + T4.4）**。Task 1–3 是离线的 TDD，只有 Task 1 Step 5 和 Task 3 Step 5 做只读的在线核对；Task 4 要等用户在 Quick 桌面版里操作 40–60 分钟。每个 bash 块都自带 `MASK`、`source infra/state.env` 和需要的 token，可以单独重跑。`/tmp` 丢失（重启）后，先重跑下面的「从计划取文件」；Task 4 的时间标记丢了，按 Step 4 末尾的方法重建。
> **代码来源：** 本计划中的全部代码和测试已在 spec 阶段于临时目录完成 TDD，并在 `96d18ce` 的干净 worktree 上按本文的顺序回放过：每个「确认失败」「确认通过」步骤的输出都是回放时实测的。嵌入的文件用 `/tmp/p4-extract.py` 按 sha256 校验后写出，**不要手抄**。P4 没有 GATE（见 Global Constraints）。实测输出和本文不一致时，停下来查原因，不要为了对上输出去改测试。

**Goal:** 把 P3 部署好的 12 个工具接进 Quick 桌面版：两个 Cloud Connector（`doris-mcp` User auth、`doris-mcp-svc` Service auth）同步后按 D7 设置权限；两个「Doris 专家」agent 用同一份指令 `quick/agent-instructions.md`，各跑一次「开场 + 第 2 幕」，答案与参照值一致；同时给 P0 评审的 M-1（scope）和 M-3（Quick 侧耗时）下结论，并在这之前收口 P3 评审遗留的 URL / IPv4 mask（T4.5）。

**Architecture:**
- **T4.5 mask 收口（Task 1）**：新模块 `scripts/redact.py`。
  - `redact(text, secrets)` 先把字面 secret（URL、token、`DORIS_HOST`）按长度从长到短换成 `***`，再把所有 IPv4 换成 `<ip>`。顺序不能反：先换 IPv4 的话，URL 里的 IP 变成 `<ip>` 之后，URL 就和 secret 字面不相等了，URL 的其余部分会原样留下（`test_a_url_with_an_ipv4_host_is_masked_whole`，突变 a2 / a2d）。
  - `redact_sdk_logs(secrets, stream)` 给 `mcp` logger 装唯一一个做 mask 的 handler，并关掉 propagate。MCP SDK 自己会记传输错误（例如 `Session termination failed: …`，或者消息里带完整 URL 的 httpx 错误）；`mcp` logger 没有自己的 handler 时，这些记录经 `logging.lastResort` 原样写到 stderr（T3.6 M1）。
  - `mcp_smoke.py`、`reconcile.py mcp --url`、`permission_matrix.py` 的错误输出都改用它。`mcp_smoke.py` 的异常变成一行 mask 过的 `FAIL:`，不再是带 URL 的 traceback（T3.3）。`permission_matrix.py` 直连模式下，Doris 拒绝消息里的客户端地址也会被 mask（T3.0 minor）。两处 lazy `sys.path` 改成模块顶部一次（P3 整体评审 Minor #4）。
- **T4.3 agent 指令（Task 2）**：`quick/agent-instructions.md` 按 design §8.3 分「角色」「硬约束」「演示口径」三段，1924 个字符（Quick 上限 5 万）。16 个检查：
  - Shape 2 个：长度、三段标题；
  - Rules 9 个：演示依赖的规则逐条锁住；
  - SemanticLayer 2 个：用 `reconcile.DirectBackend` 在本机编译，不连 Doris。指令里出现的指标名必须是语义层发布的（数量也要一致），维度名必须能作为 `group_by` 编译；
  - Hygiene 3 个：工具名都在 Gateway 的 12 个里、都带 `doris___` 前缀；没有 URL、IP、ARN、账号。
- **T4.6 Gateway 侧耗时（Task 3）**：Quick 从自己的后端调用 Cloud Connector，所以 Gateway 的 `InvokeGateway` Latency 就是 Quick 每次工具调用等待的时间（取 `Method=tools/call`，按工具名 `Name` 分开）。
  - `gw_latency.py queries` 生成 3 个 SEARCH（SampleCount / Average / Maximum，60 s 粒度）；
  - `report` 按「分钟 × 工具」输出调用数、平均和最大毫秒数：≥ 45000 ms 标 WARN（留给 T5.5 决定是否调低 `query_timeout`），≥ 60000 ms 失败（Quick 的硬上限）；
  - 2 小时的窗口最多 2 × 60 × 12 × 3 = 4320 个数据点，远低于单次请求的上限，不需要分页。
- **T4.1 + T4.4（Task 4）**：Quick 里的操作由用户按 `quick/P4-guide.md` 一次做完，AI 只做只读核对。
  - 事前：Gateway / target 状态；经 Gateway 列出 12 个工具；跑两条参照查询；对账 11/11；权限矩阵 5/5；连接数。
  - 事后：按时间窗口核对审计日志和 `gw_latency.py`；连接回收（660 s 后只剩自己的 1 个）；CloudTrail 的 `Token_POST`。
  - scope（M-1）靠用户在登录页地址栏读 `scope=`，分 a / b / b′ / c 四种情况（Task 4 Step 7）。
  - 整体评审放在 Task 4 Step 2，也就是代码和指南都完成之后、交给用户之前：评审发现指令或指南的问题时，不用让用户重做 40–60 分钟。
- **spec 阶段的只读预验证**：
  - 用 T4.5 的代码经 Gateway 跑参照查询 P2：4 行，stderr 为空，`connected+initialized in 634 ms`，`total 10553 ms`；
  - 手工 FAIL 检查（连一个本地不存在的端口，用假 token）：输出是一行 `FAIL: RuntimeError: …`，地址和假 token 的计数都是 0；
  - `gw_latency.py` 对 T3.4 的窗口（2026-09-27T13:40Z–14:10Z）：`50 calls in 31 rows`，最大 9269 ms（`doris___reload_semantic_layer`），PASS。1 分钟粒度的数据 CloudWatch 保留 15 天，也就是到 2026-10-12 左右；
  - CloudTrail：窗口内 client A / B 的 `Token_POST` 有 16 条。authorize 请求不进 CloudTrail，所以 M-1 只能靠浏览器地址栏；
  - `quick/P4-guide.md` 的两张参照表来自 spec 阶段经 Gateway 跑的 P1 / P2，Task 4 Step 3 当场再跑一次；
  - `quick/T0.7-guide.md` 的「连接参数」里列了 `Scope: doris-mcp/invoke`，用户在 T0.7 可能把它填进了连接器设置。所以 P4-guide 的 A1 先记设置里的 scope，否则分不清 authorize 请求里的 scope 是来自设置还是来自 PRM。

**Tech Stack:** Python 3.12（仓库 `.venv`）· MCP SDK（fastmcp Client + httpx）· AWS CLI v2（bedrock-agentcore-control、logs、cloudwatch、cloudtrail，全部只读）· MetricFlow（经 `doris/reconcile.py`）· bash · unittest · Amazon Quick 桌面版（用户侧）

**Spec:** `specs/doris-mcp-quick/requirements.md`（R-10、R-12、R-13、R-32、R-43、R-51；D3、D7、D8、D9）、`specs/doris-mcp-quick/design.md` v0.6（§4.4、§4.5、§8.1、§8.3、§10、§11 P4 行、§13、§14）

## Global Constraints

- 只用 us-east-1、账号 `890717383483`（环境变量里的凭证）；不要用 AWS profile `lijingfz`。本机环境的 `AWS_DEFAULT_REGION` 是 us-west-2，所以每条 AWS 命令都要显式指定 `--region us-east-1` 或 `AWS_REGION=us-east-1`。
- **P4 没有 GATE**：不创建也不修改任何 AWS 资源、Doris 账号 / 权限或安全组。AI 侧只调用这些只读接口：
  - `sts get-caller-identity`；
  - `bedrock-agentcore-control get-gateway` / `get-gateway-target`；
  - `scripts/get-gw-token.sh`：`cognito-idp describe-user-pool-client` 读 client B 的 secret（不输出），再向 Cognito token 端点取 token；
  - 经 Gateway 的 MCP 调用（`list`、`query_metric`、`conns` 用的只读 SQL）；
  - SigV4 `InvokeAgentRuntime`（`reconcile.py mcp --url`、`permission_matrix.py --url`）；
  - `logs filter-log-events`、`cloudwatch get-metric-data`、`cloudtrail lookup-events`；
  - `check-secrets.sh` 的 `secretsmanager get-secret-value`（只比较，不输出）。

  任何写操作（包括 `SYNC=1` 同步 target、改 Gateway、Cognito 或 Doris）都不在本计划内：需要时停下来，另走 GATE。Quick 里的操作全部由用户执行。
- 密码、secret、Cognito ClientSecret、`GW_TOKEN` 不出现在仓库、命令行参数、日志、输出和对话里，**grep 的参数也不行**：要按值查找，只能用 `grep -cF -f <(printf '%s\n' "$PW")`，而且只输出计数。`GW_TOKEN` 只经环境变量交给 `--bearer-env GW_TOKEN`，块末尾 `unset`；每个块自己取一次（token 约 1 小时过期，Task 4 会超过 1 小时）。
- **以下内容不出现在输出里**：Doris 主机地址、Doris 私网 IP、开发机 IP，以及 `RUNTIME_URL` / `GW_URL`。所有可能含这些内容的输出都经过 `MASK`，每个 bash 块开头都定义它：
  ``MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'``
  （Doris 主机地址是 IPv4 字面量，这条 sed 能覆盖）。
- **不要打印**：`dorismcp/agentcore/agentcore.json`（含私网 IP）、`render-agentcore.py --check` 的输出、`agentcore status` 的原始 JSON，以及 `infra/state.env` 的内容（只按变量名使用）。`progress.md`、`design.md`、`quick/T0.7-guide.md`、`prepare/` 里有私网 IP 或 URL，只经 `MASK` 查看。
- 修改规格文件的方式：`progress.md` 只用 `/tmp/p4-progress.py` 修改；`design.md`、`tasks.md` 只用计数检查过的 python 修改（每个锚点必须恰好出现 1 次）。
- Doris 凭证只从 `/home/ubuntu/AI-code/Doris-test/credentials.env` 在**子 shell** 里 `source`（该文件没有 `export` 行），只 export 需要的变量；**永远不要 echo 或 cat 这个文件**。`DORIS_ROOT_*` 从不以原名传给任何进程。
- `demo_ro` 只做 SELECT / SHOW / DESCRIBE（对账的参照 SQL）；**不要用 `demo_ro` 试探写操作**。P4 不用 root。
- `mcp_svc` 只经 Runtime 检查：T3.5 之后开发机以 `mcp_svc` 直连会 1045，这是预期的。MCP 不执行任何 DDL/DML；Quick 里 `doris___execute_query` 的弹窗只在 SQL 是 SELECT / SHOW / DESCRIBE / EXPLAIN 时允许。
- 安全组不改（R-40）；`doris-demo-sg` 现有的开发机 `/32` 规则不动。VPC 里 4 个未挂载的 `launch-wizard-*` SG 由用户决定（P3 T3.5 已记录），本计划不碰。
- Gateway `pragent-github-gw` 和其他项目的日志组、角色都不碰。Gateway 的 `exceptionLevel=DEBUG` 和被清空的 description 都保留到 T5.5。
- 给用户看的内容（`quick/P4-guide.md`、对话）不含 URL、secret、token。Quick 要求重新填 client secret 或 `demo` 密码时，用户按 T0.7 在**自己的终端**里获取，不用 Claude Code 的 `!` 前缀（`!` 的输出会进对话）。
- 不修改 `prepare/`；P4 不改 `mcp-server/`。测试 fixture 只用 TEST-NET 地址（`198.51.100.x`、`203.0.113.x`）和账号 `000000000000`。
- 测试用 unittest：`.venv/bin/python -m unittest discover -s doris/test`、`-s scripts/test`、`-s quick/test`、`-s mcp-server/test -p 'test_agentcore_*.py'`（**不要**加 `-t .`）。shell 测试用假的 `aws` / `python`，不访问 AWS 或 Doris。upstream 离线测试要带 `PYTHON_BIN=$PWD/.venv/bin/python`。
- 代码、注释、脚本输出用英文；计划、progress、给用户的指南用中文。
- 每个任务结束：勾选 `tasks.md` → `/tmp/p4-progress.py` 更新「当前状态」并追加日志 → `bash scripts/check-secrets.sh`（需要有效的 AWS 凭证）→ 暂存区新增行的 IP 计数为 0 → commit（message 结尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`）。全部在分支 `p4-quick` 上，不 push（D8）。

## Review Focus

1. **URL、token、IP 泄漏**：可能经由这些渠道出去 —— `mcp_smoke.py` 的异常（原来是带 URL 的 traceback）、MCP SDK 自己的日志行、`reconcile.py` / `permission_matrix.py` 的错误输出、Doris 拒绝消息里的客户端地址。相关的测试和检查：
   - Task 1：`test_redact.py` 的 8 个；`TestErrorsAreMasked` 的 3 个；`test_the_region_error_does_not_echo_the_url`；`permission_matrix` 的 `test_a_url_with_an_ipv4_host_is_masked_whole`、`test_sdk_log_lines_are_masked`、`test_the_client_address_in_a_denial_is_masked`；`reconcile` 的 `test_remote_errors_mask_the_url_and_ipv4_addresses`、`test_sdk_log_lines_are_masked`；
   - 突变 a1–a11 和 a2d（12 个）；手工 FAIL 检查；每次提交前新增行的 IP 计数。
2. **指令和实际的工具、语义层对不上**：例如指令里写的指标名、维度名或工具名不存在，指标数量不对，同比没有写结束日期。相关的测试和检查：
   - Task 2：`SemanticLayer` 2 个、`Hygiene` 3 个、`Rules` 9 个；
   - 突变 i1–i5。
3. **`gw_latency.py` 算错或漏报**：阈值用了 `>` 而不是 `>=`、混进其他查询的结果、ARN 校验不严、没有排序、慢了还返回 0。相关的测试和检查：
   - Task 3：10 个测试；
   - 突变 m1–m5；
   - 对 T3.4 窗口的在线核对。
4. **答案与参照值不一致**：数据或语义层在 spec 阶段之后变了，或者 agent 用错了指标。相关的检查：
   - Task 4 Step 3 当场重跑参照查询和对账 11/11；
   - Step 7 逐月、逐渠道对照。不一致就停下来。
5. **把 scope 结论说过头**：authorize 请求带了 scope，也不等于 Quick 是按 PRM 请求的（可能来自连接器设置里填的值）；没看到地址也不能写「已证实」。相关的检查：
   - Task 4 Step 7 的 a / b / b′ / c 判断；
   - Step 8 的 python 按情况生成 design 的措辞，每个锚点计数为 1，填写的值不能为空、不能有「…」。

---

## 文件地图

| 文件 | 状态 | 任务 | 作用 |
|---|---|---|---|
| `scripts/redact.py`、`scripts/test/test_redact.py` | 新建 | Task 1 | `redact()`、`redact_sdk_logs()`；8 个测试 |
| `scripts/mcp_smoke.py`、`scripts/test/test_mcp_smoke.py` | 修改 | Task 1 | 异常变成一行 mask 过的 `FAIL:`（URL、token、IPv4）；`--url` 时接管 SDK 日志；docstring 更正；3 个测试 |
| `scripts/agentcore_client.py`、`scripts/test/test_agentcore_client.py` | 修改 | Task 1 | region 的 ValueError 不回显 URL；docstring 更正（凭证只在建 client 时解析一次）；1 个测试 |
| `doris/reconcile.py`、`doris/test/test_reconcile.py` | 修改 | Task 1 | `--url` 进 secrets，错误输出 mask URL 和 IPv4，接管 SDK 日志；`sys.path` 在模块顶部；2 个新测试，1 个改成直接 import |
| `doris/permission_matrix.py`、`doris/test/test_permission_matrix.py` | 修改 | Task 1 | `_mask` 换成 `redact.redact`（直连模式也 mask 客户端地址）；接管 SDK 日志；`sys.path` 在模块顶部；3 个新测试，1 个改成直接 import |
| `doris/test/test_admin_sql.py` | 修改 | Task 1 | T3.6 M2：DROP 位置不对时，在读 secret 之前就拒绝（锁定已有行为）|
| `quick/agent-instructions.md`、`quick/test/test_agent_instructions.py` | 新建 | Task 2 | 「Doris 专家」agent 指令；16 个检查 |
| `scripts/gw_latency.py`、`scripts/test/test_gw_latency.py` | 新建 | Task 3 | Gateway `tools/call` 每分钟、每个工具的耗时；10 个测试 |
| `quick/P4-guide.md` | 新建 | Task 4 | 用户侧操作指南（Part A–D + 回复模板），不含 URL 和 secret |
| `specs/doris-mcp-quick/design.md`、`tasks.md`、`progress.md`、`RESUME.md`、本计划 | 修改 / 新建 | Task 1 Step 1、各任务收尾、Task 4 Step 8 | spec v0.6 随计划提交；Task 4 之后 design 升到 v0.7（M-1、M-3 的结论）|

常用测试命令：

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 最终 161 个
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 最终 75 个
.venv/bin/python -m unittest discover -s quick/test 2>&1 | tail -3                                  # 最终 16 个（Task 2 起才有）
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 89 个（P4 不变）
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3     # 🎉 All tests passed!
for t in doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh infra/test/test-35-runtime-role.sh \
         infra/test/test-40-doris-secret.sh infra/test/test-lib.sh scripts/test/test-check-secrets.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 每行 all passed
```

## 从计划取文件

本计划嵌入了 13 个文件：每个 `<!-- file: NAME sha256=HEX -->` 下面紧跟的代码块就是一个文件，文件内容是块内文本加末尾换行。下面两个小工具先写到 `/tmp`：`p4-extract.py` 按 sha256 校验后写出文件，`p4-progress.py` 修改 `progress.md` 而不打印它（旧日志里有私网 IP）。Task 1 Step 1 执行本节；`/tmp` 丢失后，从任何任务继续之前都先重跑本节。

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
cat > /tmp/p4-extract.py <<'EOF'
"""Write one embedded file of specs/doris-mcp-quick/plans/P4-quick.md to disk, after checking its sha256.

  .venv/bin/python /tmp/p4-extract.py --check          # checks every block's sha256; prints names and line counts
  .venv/bin/python /tmp/p4-extract.py NAME [DEST]      # DEST defaults to NAME (a repo path)
A block is the fenced code block right after a line `<!-- file: NAME sha256=HEX -->`; its text plus a final
newline is the file. Run from the repository root.
"""
import hashlib
import pathlib
import re
import sys

PLAN = pathlib.Path("specs/doris-mcp-quick/plans/P4-quick.md")
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
cat > /tmp/p4-progress.py <<'EOF'
"""Edit specs/doris-mcp-quick/progress.md without printing it: older log entries hold private IPs.

  .venv/bin/python /tmp/p4-progress.py state KEY < TEXT   # the line "- **KEY**：…" of 当前状态 becomes "- **KEY**：TEXT"
  .venv/bin/python /tmp/p4-progress.py log < TEXT         # appends TEXT, a "### …" entry, at the end of 日志
Prints what changed (the key, or the entry's heading) and the new line count; nothing of the old text.
Run from the repository root.
"""
import pathlib
import sys

PROGRESS = pathlib.Path("specs/doris-mcp-quick/progress.md")


def main(argv: list[str]) -> int:
    text = PROGRESS.read_text(encoding="utf-8")
    new = sys.stdin.read().strip("\n")
    if len(argv) == 2 and argv[0] == "state":
        state, sep, log = text.partition("\n## 日志\n")
        prefix = f"- **{argv[1]}**："
        lines = state.split("\n")
        hits = [i for i, line in enumerate(lines) if line.startswith(prefix)]
        if not sep or len(hits) != 1 or not new or "\n" in new:
            print(f"FAIL: {len(hits)} lines of 当前状态 start with {prefix} (want 1), TEXT must be one line")
            return 1
        lines[hits[0]] = prefix + new
        text, what = "\n".join(lines) + sep + log, argv[1]
    elif argv == ["log"] and new.startswith("### "):
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
.venv/bin/python /tmp/p4-extract.py --check; echo "exit=$?"
for f in p4-mut.py p4-mutations.json p4-rows.py p4-token-events.py; do .venv/bin/python /tmp/p4-extract.py "$f" "/tmp/$f"; done
```
期望（实测）：
```
ok   p4-mut.py (57 lines)
ok   p4-mutations.json (24 lines)
ok   scripts/test/test_redact.py (73 lines)
ok   t45-tests.diff (245 lines)
ok   scripts/redact.py (45 lines)
ok   t45-impl.diff (289 lines)
ok   quick/test/test_agent_instructions.py (152 lines)
ok   quick/agent-instructions.md (28 lines)
ok   scripts/test/test_gw_latency.py (122 lines)
ok   scripts/gw_latency.py (99 lines)
ok   quick/P4-guide.md (117 lines)
ok   p4-rows.py (11 lines)
ok   p4-token-events.py (18 lines)
13 blocks, 0 bad
exit=0
p4-mut.py -> /tmp/p4-mut.py (57 lines)
p4-mutations.json -> /tmp/p4-mutations.json (24 lines)
p4-rows.py -> /tmp/p4-rows.py (11 lines)
p4-token-events.py -> /tmp/p4-token-events.py (18 lines)
```

突变检查工具 `p4-mut.py`：每个突变只改一个文件的一处，跑它指定的测试，再把文件按字节恢复；最后确认工作区和运行前完全一样。用法 `.venv/bin/python /tmp/p4-mut.py /tmp/p4-mutations.json GROUP`，GROUP 是 `t45` / `t43` / `t46`。

<!-- file: p4-mut.py sha256=4f4c56edffeb0d1c2a563e27be96d988fc4c12d7bafe53ca81df452532ba0102 -->
```python
"""Mutation checks for plans/P4-quick.md: each mutation changes one file once, runs its tests, restores the file.

  .venv/bin/python /tmp/p4-mut.py /tmp/p4-mutations.json GROUP
One line per mutation: `NAME: caught by TEST[, TEST] (Ran N, FAILED (...))`, `NAME: NOT CAUGHT (...)` or
`NAME: pattern not found once`; then `C/N mutations caught` and whether the tree is back byte for byte.
Exit code 0 only when every mutation of the group was caught and the tree is unchanged. Run from the repo root.
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys


def tree_state(files: set[str]) -> str:
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout
    diff = subprocess.run(["git", "diff"], capture_output=True, check=True).stdout
    return status + hashlib.sha256(diff).hexdigest() + "".join(
        hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() for f in sorted(files))


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
            run = subprocess.run([sys.executable, "-m", "unittest", *m["tests"]], capture_output=True, text=True)
        finally:
            path.write_bytes(original)
        ran = re.search(r"^Ran (\d+) tests?", run.stderr, re.M)
        result = re.search(r"^(FAILED \(.*\)|OK)", run.stderr, re.M)
        summary = f"Ran {ran.group(1) if ran else '?'}, {result.group(1) if result else '?'}"
        failed = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\w+)", run.stderr, re.M)))
        if run.returncode != 0:
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

22 个突变（T4.5 12 个、T4.3 5 个、T4.6 5 个）。每个突变都对应一种「看起来还能用」的错误改法：

<!-- file: p4-mutations.json sha256=9ef73392898a7a19336d697c721f050c964dd557c4ae54047194ba43bf4edf57 -->
```json
[
  {"group": "t45", "name": "a1", "file": "doris/admin_sql.py", "old": "        _check_drops(matches)  # before the secret is read; render() checks again\n", "new": "", "tests": ["discover", "-s", "doris/test", "-p", "test_admin_sql.py"]},
  {"group": "t45", "name": "a2", "file": "scripts/redact.py", "old": "    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):\n        text = text.replace(secret, MASK)\n    return IPV4_RE.sub(\"<ip>\", text)", "new": "    text = IPV4_RE.sub(\"<ip>\", text)\n    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):\n        text = text.replace(secret, MASK)\n    return text", "tests": ["discover", "-s", "scripts/test", "-p", "test_redact.py"]},
  {"group": "t45", "name": "a2d", "file": "scripts/redact.py", "old": "    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):\n        text = text.replace(secret, MASK)\n    return IPV4_RE.sub(\"<ip>\", text)", "new": "    text = IPV4_RE.sub(\"<ip>\", text)\n    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):\n        text = text.replace(secret, MASK)\n    return text", "tests": ["discover", "-s", "doris/test", "-p", "test_permission_matrix.py"]},
  {"group": "t45", "name": "a3", "file": "scripts/redact.py", "old": "key=len, reverse=True)", "new": "key=len)", "tests": ["discover", "-s", "scripts/test", "-p", "test_redact.py"]},
  {"group": "t45", "name": "a4", "file": "scripts/redact.py", "old": "    logger.propagate = False\n", "new": "", "tests": ["discover", "-s", "scripts/test", "-p", "test_redact.py"]},
  {"group": "t45", "name": "a5", "file": "scripts/redact.py", "old": "    logger.handlers[:] = [handler]", "new": "    logger.addHandler(handler)", "tests": ["discover", "-s", "scripts/test", "-p", "test_redact.py"]},
  {"group": "t45", "name": "a6", "file": "scripts/redact.py", "old": "        return redact(super().format(record), self._secrets)  # the traceback too", "new": "        return super().format(record)", "tests": ["discover", "-s", "scripts/test", "-p", "test_redact.py"]},
  {"group": "t45", "name": "a7", "file": "scripts/mcp_smoke.py", "old": "    hidden = [args.url, os.environ.get(args.bearer_env, \"\") if args.bearer_env else \"\"]", "new": "    hidden = [args.url]", "tests": ["discover", "-s", "scripts/test", "-p", "test_mcp_smoke.py"]},
  {"group": "t45", "name": "a8", "file": "scripts/mcp_smoke.py", "old": "    if args.url:\n        redact.redact_sdk_logs(hidden)\n", "new": "", "tests": ["discover", "-s", "scripts/test", "-p", "test_mcp_smoke.py"]},
  {"group": "t45", "name": "a9", "file": "doris/reconcile.py", "old": "        secrets.append(args.url)\n", "new": "", "tests": ["discover", "-s", "doris/test", "-p", "test_reconcile.py"]},
  {"group": "t45", "name": "a10", "file": "doris/permission_matrix.py", "old": "        redact.redact_sdk_logs(secrets, stream=err)  # the MCP SDK logs transport errors itself, URL included\n", "new": "", "tests": ["discover", "-s", "doris/test", "-p", "test_permission_matrix.py"]},
  {"group": "t45", "name": "a11", "file": "scripts/agentcore_client.py", "old": "        raise ValueError(\"cannot tell the region from the URL (not https://bedrock-agentcore.<region>\"\n                         \".amazonaws.com/...); pass --region\")", "new": "        raise ValueError(f\"cannot tell the region from {url!r}; pass --region\")", "tests": ["discover", "-s", "scripts/test", "-p", "test_agentcore_client.py"]},
  {"group": "t43", "name": "i1", "file": "quick/agent-instructions.md", "old": "   - 不要调用 `doris___reload_semantic_layer`，除非用户明确要求；查询时会自动使用最新的语义层。\n", "new": "", "tests": ["discover", "-s", "quick/test"]},
  {"group": "t43", "name": "i2", "file": "quick/agent-instructions.md", "old": "先用 `doris___list_metrics`", "new": "先用 `list_metrics`", "tests": ["discover", "-s", "quick/test"]},
  {"group": "t43", "name": "i3", "file": "quick/agent-instructions.md", "old": "用 `line_gmv`", "new": "用 `item_gmv`", "tests": ["discover", "-s", "quick/test"]},
  {"group": "t43", "name": "i4", "file": "quick/agent-instructions.md", "old": "分渠道看时 group_by `order_entity__channel`", "new": "分渠道看时 group_by `order__channel`", "tests": ["discover", "-s", "quick/test"]},
  {"group": "t43", "name": "i5", "file": "quick/agent-instructions.md", "old": "等 22 个业务指标", "new": "等 20 个业务指标", "tests": ["discover", "-s", "quick/test"]},
  {"group": "t46", "name": "m1", "file": "scripts/gw_latency.py", "old": "if stats.get(\"max\", 0) >= threshold]", "new": "if stats.get(\"max\", 0) > threshold]", "tests": ["discover", "-s", "scripts/test", "-p", "test_gw_latency.py"]},
  {"group": "t46", "name": "m2", "file": "scripts/gw_latency.py", "old": "        if result.get(\"Id\") not in ids:\n            continue\n", "new": "", "tests": ["discover", "-s", "scripts/test", "-p", "test_gw_latency.py"]},
  {"group": "t46", "name": "m3", "file": "scripts/gw_latency.py", "old": "GATEWAY_ARN_RE.fullmatch(", "new": "GATEWAY_ARN_RE.match(", "tests": ["discover", "-s", "scripts/test", "-p", "test_gw_latency.py"]},
  {"group": "t46", "name": "m4", "file": "scripts/gw_latency.py", "old": "    rows = sorted(parse_rows(doc).items())", "new": "    rows = list(parse_rows(doc).items())", "tests": ["discover", "-s", "scripts/test", "-p", "test_gw_latency.py"]},
  {"group": "t46", "name": "m5", "file": "scripts/gw_latency.py", "old": "    return 1 if slow else 0", "new": "    return 0", "tests": ["discover", "-s", "scripts/test", "-p", "test_gw_latency.py"]}
]
```

---

### Task 1：T4.5 URL / IPv4 mask 收口（P3 整体评审、T3.0 / T3.3 / T3.6 的遗留）

来源：progress「P3 整体评审（opus）」的评审建议（T5.5 之前给 `--url` 输出加 URL mask），以及「各任务评审遗留的 minor」里的 T3.0、T3.3 两项和「T3.6 收尾」的 M1、M2。P3 整体评审的其他 Minor：#1、#3、#5、#6 由 design v0.6、RESUME 和本计划在 Step 1 一起提交关闭；#2 已在 P3 修正；#4 在本任务关闭。

| # | 来源 | 问题 | 改动 | 测试 |
|---|---|---|---|---|
| 1 | T3.3 | `agentcore_client.region_from_url` 失败时 ValueError 的消息里带着 URL，调用方会原样打印 | 消息只描述期望的格式，不带 URL | `test_the_region_error_does_not_echo_the_url` |
| 2 | T3.3 | `reconcile._failed` 等错误输出只 mask 了密码，没有 mask `--url` 和 IPv4 | `--url` 加进 secrets，全部改用 `redact.redact` | `test_remote_errors_mask_the_url_and_ipv4_addresses` |
| 3 | T3.3 | `mcp_smoke.py` 连接或调用失败时打印完整 traceback（带 URL）；docstring 说失败会 mask，实际没有 | `main` 捕获异常，输出一行 `FAIL: <类型>: <mask 过的消息>`，exit 1；token 也加进 secrets；docstring 写明 | `test_a_connection_error_is_one_masked_line`、`test_the_bearer_token_is_masked` |
| 4 | T3.3 | `agentcore_client.py` 的 docstring 说每次请求前都重新读取凭证 | 更正：建 client 时解析一次；可刷新的 provider 自己刷新，静态 `AWS_*` 不变 | 无（只改文档）|
| 5 | T3.0 | `permission_matrix` 直连模式下，Doris 的拒绝消息 `'mcp_svc'@'<客户端地址>'` 不是 `DORIS_HOST`，没有被 mask | `_brief` 改用 `redact.redact`，IPv4 一律 mask | `test_the_client_address_in_a_denial_is_masked` |
| 6 | T3.6 M1 | 关闭 session 时的注释写错了原因；SDK 自己记的 `Session termination failed: …` 等日志行不经过 mask | 注释更正；`--url` 模式调用 `redact.redact_sdk_logs` | 三个 `test_sdk_log_lines_are_masked`（`mcp_smoke`、`reconcile`、`permission_matrix`）、`test_redact.py` 的 `RedactSdkLogs` |
| 7 | T3.6 M2 | 两处已有行为没有测试锁住：`admin_sql.main` 在读 secret 之前就检查 DROP 的位置；`permission_matrix` 先 mask URL 再 mask IPv4 | 补 2 个测试（锁定已有行为，所以在 RED 里也通过，由突变 a1、a2d 证明它们有效）| `test_a_misplaced_drop_is_refused_before_the_secret_is_read`、`test_a_url_with_an_ipv4_host_is_masked_whole` |
| 8 | P3 Minor #4 | `reconcile.py`、`permission_matrix.py` 在函数里重复 lazy 插入 `sys.path` | 模块顶部插入一次，直接 `import redact` | `test_default_remote_client_is_the_sigv4_client`、`test_default_remote_connect_uses_the_sigv4_client` 改成直接 import（RED 里是 ERROR）|

**Files:**
- Create: `scripts/redact.py`、`scripts/test/test_redact.py`
- Modify: `scripts/mcp_smoke.py`、`scripts/agentcore_client.py`、`doris/reconcile.py`、`doris/permission_matrix.py`
- Test: `scripts/test/test_mcp_smoke.py`（+3）、`scripts/test/test_agentcore_client.py`（+1）、`doris/test/test_reconcile.py`（+2，改 1）、`doris/test/test_permission_matrix.py`（+3，改 1）、`doris/test/test_admin_sql.py`（+1）。`scripts/test` 53 → 65，`doris/test` 155 → 161
- Modify: `specs/doris-mcp-quick/design.md`、`tasks.md`、`progress.md`、`RESUME.md`、本计划（Step 1 提交）

**Interfaces:**
- Consumes：`96d18ce` 的 `mcp_smoke.main(argv, client_factory=build_client) -> int`、`reconcile._failed(error, secrets, err) -> int` / `reconcile.main(argv, env, …)`、`permission_matrix._brief(error, secrets) -> str` / `permission_matrix.main(argv, env, …)`、`agentcore_client.region_from_url(url) -> str | None` / `sigv4_client(url, region=None, timeout=90.0)`。
- Produces（Task 2–4 和 P5 使用）：
  - `redact.MASK = "***"`、`redact.IPV4_RE`；
  - `redact.redact(text: str, secrets: Iterable[str | None]) -> str`：字面 secret 从长到短换成 `***`，然后 IPv4 换成 `<ip>`；
  - `redact.redact_sdk_logs(secrets, stream=None) -> logging.Handler`：`mcp` logger 只剩这一个 handler，`propagate=False`，traceback 也经过 mask；
  - `mcp_smoke.py`：任何子命令抛出的异常都是一行 `FAIL: <类型>: <消息>`，exit 1，URL 和 token 是 `***`，IPv4 是 `<ip>`；
  - `reconcile.py` / `permission_matrix.py` 在模块顶部把 `scripts/` 加进 `sys.path`，`import redact`；`_mask` 删除。

- [ ] **Step 1：前置检查，建分支，取文件，提交计划和 spec 修改**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
git branch --show-current                                   # 期望：main
git status --short                                          # 期望：下面 5 行
AWS_PAGER= aws sts get-caller-identity --region us-east-1 --query Account --output text   # 期望：890717383483
.venv/bin/python --version                                  # 期望：Python 3.12.3
test -r /home/ubuntu/AI-code/Doris-test/credentials.env && echo "credentials: readable"
git log --oneline -1; git rev-parse --short origin/main    # 期望：96d18ce …；b4cbbf2
```
`git status --short` 期望：
```
 M RESUME.md
 M specs/doris-mcp-quick/design.md
 M specs/doris-mcp-quick/progress.md
 M specs/doris-mcp-quick/tasks.md
?? specs/doris-mcp-quick/plans/P4-quick.md
```
有其他改动就停下来，对照 progress 判断属于哪个任务（不要 reset / checkout）。

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
git switch -c p4-quick
```
然后执行上面的「从计划取文件」，期望输出与那里一致（13 个 `ok`、`13 blocks, 0 bad`）。

spec 阶段的临时目录已经不需要了（代码以本计划嵌入的为准）。先看一眼再删：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
git worktree list                     # 期望：主目录 [p4-quick]，以及 /tmp/p4-stage、/tmp/p4-replay（detached，96d18ce）
for w in /tmp/p4-stage /tmp/p4-replay; do git worktree list | grep -q "^$w " && git worktree remove --force "$w"; done
rm -rf /tmp/p4-build; git worktree prune; git worktree list   # 期望：只剩主目录
```

design 的状态行改成「进行中」，progress 更新「当前状态」。`MODE` 按用户选的执行方式二选一：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - <<'EOF'
import pathlib
p = pathlib.Path("specs/doris-mcp-quick/design.md")
s = p.read_text(encoding="utf-8")
old = "状态：P4 计划已编写（`plans/P4-quick.md`，待用户 review）；"
assert s.count(old) == 1, old
p.write_text(s.replace(old, "状态：P4 进行中（`plans/P4-quick.md`，分支 `p4-quick`）；"), encoding="utf-8")
print("design.md: status line")
EOF
MODE='Native（控制方按 TDD 执行，Task 4 Step 2 由一个 Opus 5.5 reviewer 评审整个分支）'
# MODE='Subagent-driven（implementer / reviewer 全部用 Opus 5.5，Task 4 Step 2 再做整个分支的评审）'
O=$(git rev-parse --short origin/main)
printf '**P4 进行中**（`plans/P4-quick.md`，分支 `p4-quick`，执行方式：%s）。P3 已完成（T3.0–T3.6），已合并到 `main` 并推送到私有仓库（`origin/main` = `%s`）；P0–P3 的过程见日志' "$MODE" "$O" \
  | .venv/bin/python /tmp/p4-progress.py state 阶段
echo 'Task 1（T4.5）：Step 1 已提交计划和 spec 修改（design v0.6、tasks、RESUME）；从 Step 2 继续' | .venv/bin/python /tmp/p4-progress.py state 进行中
echo 'Task 1 Step 2–6（写失败测试 → 实现 → 验证 → 提交），然后 Task 2（T4.3）、Task 3（T4.6）、Task 4（T4.1 + T4.4：先整体评审，再交给用户在 Quick 里操作 40–60 分钟）。P4 没有 GATE' | .venv/bin/python /tmp/p4-progress.py state 下一步
echo 'spec 阶段的 `/tmp/p4-stage`、`/tmp/p4-replay`、`/tmp/p4-build/` 已在 Task 1 Step 1 删除。**权威版本是 `plans/P4-quick.md` 里嵌入的代码**，用 `/tmp/p4-extract.py` 按 sha256 取出（计划「从计划取文件」）；`/tmp` 丢失后先重跑那一节' | .venv/bin/python /tmp/p4-progress.py state 'spec 阶段的临时产物'
```
期望：
```
design.md: status line
阶段: written (N lines)
进行中: written (N lines)
下一步: written (N lines)
spec 阶段的临时产物: written (N lines)
```

提交（新增行的 IP 计数只输出数字；私网 IP 取自 `agentcore.json` 和 `state.env`，不打印）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add RESUME.md specs/doris-mcp-quick/design.md specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md \
        specs/doris-mcp-quick/plans/P4-quick.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
test -n "$v" && git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); unset v   # 期望：0
git commit -q -F - <<'EOF'
docs(p4): P4 plan, design v0.6 (scope M-1 correction, M-3), tasks T4.5/T4.6

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git log --oneline -1
```

- [ ] **Step 2：写失败测试**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p4-extract.py scripts/test/test_redact.py
.venv/bin/python /tmp/p4-extract.py t45-tests.diff /tmp/t45-tests.diff
git apply /tmp/t45-tests.diff && git status --short && git diff --shortstat
```
期望（实测）：
```
scripts/test/test_redact.py -> scripts/test/test_redact.py (73 lines)
t45-tests.diff -> /tmp/t45-tests.diff (245 lines)
 M doris/test/test_admin_sql.py
 M doris/test/test_permission_matrix.py
 M doris/test/test_reconcile.py
 M scripts/test/test_agentcore_client.py
 M scripts/test/test_mcp_smoke.py
?? scripts/test/test_redact.py
 5 files changed, 122 insertions(+), 9 deletions(-)
```

新文件 `scripts/test/test_redact.py`：

<!-- file: scripts/test/test_redact.py sha256=31245f840194c36f5f99204f8e732807039324511f5adb81720e2a1b3c07a54e -->
```python
"""scripts/redact.py: secrets, URLs and IPv4 addresses out of error lines and the MCP SDK's log lines (P4 / T4.5)."""

import io
import logging
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import redact  # noqa: E402

URL = "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/x/invocations?qualifier=DEFAULT"
IP_URL = "http://198.51.100.7:8000/mcp"  # TEST-NET-2
HOST = "198.51.100.7"


class Redact(unittest.TestCase):
    def test_a_secret_becomes_the_mask(self):
        self.assertEqual(redact.redact(f"POST {URL} failed", [URL]), "POST *** failed")

    def test_ipv4_addresses_become_ip(self):
        self.assertEqual(redact.redact("connect to 203.0.113.9:9030 refused", []), "connect to <ip>:9030 refused")

    def test_a_url_with_an_ipv4_host_is_masked_whole(self):
        self.assertEqual(redact.redact(f"POST {IP_URL} failed", [IP_URL]), "POST *** failed")

    def test_longer_secrets_are_replaced_first(self):
        # HOST is part of IP_URL: replacing it first would leave ":8000/mcp" behind.
        self.assertEqual(redact.redact(f"{IP_URL} via {HOST}", [HOST, IP_URL]), "*** via ***")

    def test_empty_secrets_are_ignored(self):
        self.assertEqual(redact.redact("nothing to hide", ["", None]), "nothing to hide")


class RedactSdkLogs(unittest.TestCase):
    def setUp(self):
        logger = logging.getLogger("mcp")
        self.enterContext(mock.patch.object(logger, "handlers", []))
        self.enterContext(mock.patch.object(logger, "propagate", True))
        self.stream = io.StringIO()

    def test_sdk_log_lines_are_redacted(self):
        redact.redact_sdk_logs([URL], self.stream)
        logging.getLogger("mcp.client.streamable_http").warning("Session termination failed: DELETE %s", URL)
        self.assertEqual(self.stream.getvalue(), "WARNING mcp.client.streamable_http: Session termination failed: "
                                                 "DELETE ***\n")

    def test_sdk_tracebacks_are_redacted(self):
        redact.redact_sdk_logs([URL], self.stream)
        try:
            raise RuntimeError(f"Client error '403 Forbidden' for url '{URL}' from 203.0.113.9")
        except RuntimeError:
            logging.getLogger("mcp.client.streamable_http").exception("Error in post_writer")
        text = self.stream.getvalue()
        self.assertIn("Traceback", text)
        self.assertIn("RuntimeError: Client error '403 Forbidden' for url '***' from <ip>", text)
        self.assertNotIn(URL, text)
        self.assertNotIn("203.0.113.9", text)

    def test_one_handler_and_nothing_reaches_the_root_logger(self):
        redact.redact_sdk_logs([URL], io.StringIO())
        handler = redact.redact_sdk_logs([URL], self.stream)
        logger = logging.getLogger("mcp")
        self.assertEqual(logger.handlers, [handler])
        self.assertFalse(logger.propagate)
        with self.assertNoLogs(level="DEBUG"):  # assertNoLogs() watches the root logger
            logging.getLogger("mcp.client").error("POST %s", URL)
        self.assertEqual(self.stream.getvalue(), "ERROR mcp.client: POST ***\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

对 5 个已有测试文件的改动（`git apply`）：

<!-- file: t45-tests.diff sha256=935c278b1a996994a67855dd4713f115896b6d480e6c5bf7ca50de6a308eda78 -->
```diff
diff --git a/doris/test/test_admin_sql.py b/doris/test/test_admin_sql.py
index 1b27dc2..ebc00a4 100644
--- a/doris/test/test_admin_sql.py
+++ b/doris/test/test_admin_sql.py
@@ -189,6 +189,13 @@ class DropUser(unittest.TestCase):
         self.assertIn("must follow a CREATE USER of another mcp_svc identity", output)
         self.assertEqual(conn.executed, [])
 
+    def test_a_misplaced_drop_is_refused_before_the_secret_is_read(self):
+        sql = "DROP USER IF EXISTS 'mcp_svc'@'%';\n" + MIGRATE_SQL.replace("DROP USER IF EXISTS 'mcp_svc'@'%';\n", "")
+        rc, output, conn = run(sql=sql, secret="not json", apply=True)
+        self.assertEqual(rc, 2)
+        self.assertIn("must follow a CREATE USER of another mcp_svc identity", output)
+        self.assertEqual(conn.executed, [])
+
     def test_dropping_an_identity_the_script_also_sets_up_is_refused(self):
         for extra in ("GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%';",
                       "ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';",
diff --git a/doris/test/test_permission_matrix.py b/doris/test/test_permission_matrix.py
index f2d2009..e963eb2 100644
--- a/doris/test/test_permission_matrix.py
+++ b/doris/test/test_permission_matrix.py
@@ -309,6 +309,13 @@ class DryRun(unittest.TestCase):
         self.assertIn("ok    databases", out)
         self.assertIn("3/4 checks pass", out)
 
+    def test_the_client_address_in_a_denial_is_masked(self):
+        # Doris names the client, 'mcp_svc'@'<client address>'; that is not DORIS_HOST (T3.0 minor).
+        rc, out, _, _, _ = run_main(conn=FakeDoris({"SELECT 1 FROM internal.ecom.fact_refund": denied("SELECT")}))
+        self.assertEqual(rc, 1)
+        self.assertIn("FAIL  select: internal.ecom.fact_refund: 1105 SELECT command denied to user "
+                      "'mcp_svc'@'<ip>'", out)
+
     def test_long_messages_are_masked_before_they_are_cut(self):
         # Cutting first would keep a prefix of the password that the mask no longer recognises.
         leak = pymysql.err.OperationalError(1105, "SELECT command denied " + "x" * 130 + PASSWORD)
@@ -513,17 +520,26 @@ def runtime_server(doris: FakeDoris) -> FastMCP:
 class RemoteRuntime(unittest.TestCase):
     """--url: the read-only checks through the deployed Runtime, as mcp_svc from the VPC (P3 / T3.5)."""
 
-    def run_remote(self, argv=(), doris=None, apply=False, remote_error=None, close_error=None):
+    def setUp(self):
+        sdk_logger = logging.getLogger("mcp")  # --url installs a redacting handler on it
+        self.enterContext(mock.patch.object(sdk_logger, "handlers", []))
+        self.enterContext(mock.patch.object(sdk_logger, "propagate", True))
+
+    def run_remote(self, argv=(), doris=None, apply=False, remote_error=None, close_error=None, url=RUNTIME_URL,
+                   on_connect=None):
         doris = doris or FakeDoris({"SELECT CURRENT_USER()": [{"identity": VPC_IDENTITY}]})
         remote_calls = []
 
-        class CloseFails(Client):  # e.g. the session DELETE hits a transport error after the checks
+        class CloseFails(Client):  # a mid-session transport error (e.g. a 403 once the credentials expire),
+            # re-raised by __aexit__; a failed session DELETE is only logged by the SDK
             async def __aexit__(self, *exc_info):
                 await super().__aexit__(*exc_info)
                 raise close_error
 
         def remote_connect(url, region):
             remote_calls.append((url, region))
+            if on_connect:
+                on_connect(url)
             if remote_error:
                 raise remote_error
             return permission_matrix.RuntimeConnection((CloseFails if close_error else Client)(runtime_server(doris)))
@@ -533,7 +549,7 @@ class RemoteRuntime(unittest.TestCase):
 
         out, err = io.StringIO(), io.StringIO()
         env = {"APPLY": "1"} if apply else {}  # no DORIS_* at all: the Runtime has its own settings
-        rc = permission_matrix.main(["--url", RUNTIME_URL, *argv], env=env, connect=no_direct_connect, out=out,
+        rc = permission_matrix.main(["--url", url, *argv], env=env, connect=no_direct_connect, out=out,
                                     err=err, remote_connect=remote_connect)
         return rc, out.getvalue(), err.getvalue(), doris, remote_calls
 
@@ -596,6 +612,21 @@ class RemoteRuntime(unittest.TestCase):
         self.assertEqual(rc, 1)
         self.assertEqual(err.strip(), "FAILED: connect: ConnectionError: POST *** failed")
 
+    def test_a_url_with_an_ipv4_host_is_masked_whole(self):
+        url = "http://198.51.100.7:8000/mcp"  # the IPv4 pattern must not get to it before the URL does
+        rc, _, err, _, _ = self.run_remote(url=url, remote_error=ConnectionError(f"POST {url} failed"))
+        self.assertEqual(rc, 1)
+        self.assertEqual(err.strip(), "FAILED: connect: ConnectionError: POST *** failed")
+
+    def test_sdk_log_lines_are_masked(self):
+        def sdk_logs(url):
+            logging.getLogger("mcp.client.streamable_http").error("Error in post_writer: POST %s via 198.51.100.7",
+                                                                  url)
+
+        rc, out, err, _, _ = self.run_remote(on_connect=sdk_logs)
+        self.assertEqual(rc, 0, out + err)
+        self.assertEqual(err.strip(), "ERROR mcp.client.streamable_http: Error in post_writer: POST *** via <ip>")
+
     def test_a_failed_close_is_one_masked_warning_and_keeps_the_result(self):
         # A passing run stays 0; the old identity with --expect-host stays 1.
         for doris, argv, rc_want, summary in ((None, [], 0, "4/4 checks pass"),
@@ -608,10 +639,7 @@ class RemoteRuntime(unittest.TestCase):
                 self.assertEqual(err.strip(), "WARN: close: ConnectionError: DELETE *** failed")
 
     def test_default_remote_connect_uses_the_sigv4_client(self):
-        scripts = str(ROOT / "scripts")
-        sys.path.insert(0, scripts)
-        self.addCleanup(sys.path.remove, scripts)
-        import agentcore_client
+        import agentcore_client  # permission_matrix puts scripts/ on sys.path
         server = runtime_server(FakeDoris())
         with mock.patch.object(agentcore_client, "sigv4_client", return_value=Client(server)) as factory:
             conn = permission_matrix._runtime_connection(RUNTIME_URL, "us-east-1")
diff --git a/doris/test/test_reconcile.py b/doris/test/test_reconcile.py
index 54da637..8920ba1 100644
--- a/doris/test/test_reconcile.py
+++ b/doris/test/test_reconcile.py
@@ -420,6 +420,11 @@ class Main(unittest.TestCase):
 class Remote(unittest.TestCase):
     """mcp --url: the deployed Runtime over SigV4 (P3 / T3.3); the reference SQL still runs on pymysql."""
 
+    def setUp(self):
+        sdk_logger = logging.getLogger("mcp")  # --url installs a redacting handler on it
+        self.enterContext(mock.patch.object(sdk_logger, "handlers", []))
+        self.enterContext(mock.patch.object(sdk_logger, "propagate", True))
+
     def _client(self):
         names = sorted(local_metric_names(MODELS))
         return FakeClient({"list_metrics": ok([{"name": n, "description": "d"} for n in names],
@@ -474,9 +479,31 @@ class Remote(unittest.TestCase):
         self.assertNotIn("Traceback", out + err)
         self.assertTrue(conn.closed)
 
+    def test_remote_errors_mask_the_url_and_ipv4_addresses(self):
+        def remote(url, _region):
+            raise RuntimeError(f"POST {url} failed; Doris at 198.51.100.9 refused")
+
+        rc, out, err, _ = run_main(["mcp", "--url", RUNTIME_URL], conn=FakeConn([YTD_ROW]), remote=remote)
+        self.assertEqual(rc, 1)
+        self.assertEqual([line for line in err.splitlines() if line.startswith("FAILED:")],
+                         ["FAILED: RuntimeError: POST *** failed; Doris at <ip> refused"])
+        self.assertNotIn("amazonaws.com", out + err)
+
+    def test_sdk_log_lines_are_masked(self):
+        client = self._client()
+
+        def remote(url, _region):
+            logging.getLogger("mcp.client.streamable_http").error("Error in post_writer: POST %s", url)
+            return client
+
+        rc, out, err, _ = run_main(["mcp", "--url", RUNTIME_URL, "--case", "ytd_totals"], conn=FakeConn([YTD_ROW]),
+                                   remote=remote)
+        self.assertEqual(rc, 0, out + err)
+        self.assertIn("ERROR mcp.client.streamable_http: Error in post_writer: POST ***\n", err)
+        self.assertNotIn("amazonaws.com", out + err)
+
     def test_default_remote_client_is_the_sigv4_client(self):
-        sys.path.insert(0, str(ROOT / "scripts"))
-        import agentcore_client
+        import agentcore_client  # reconcile puts scripts/ on sys.path
 
         with mock.patch.object(agentcore_client, "sigv4_client", return_value="client") as sigv4:
             self.assertEqual(reconcile._remote_client(RUNTIME_URL, "us-east-1"), "client")
diff --git a/scripts/test/test_agentcore_client.py b/scripts/test/test_agentcore_client.py
index 8dbc614..4f8e57a 100644
--- a/scripts/test/test_agentcore_client.py
+++ b/scripts/test/test_agentcore_client.py
@@ -129,6 +129,12 @@ class TestSigV4Client(unittest.TestCase):
         with self.assertRaisesRegex(ValueError, "--region"):
             agentcore_client.sigv4_client("http://127.0.0.1:8000/mcp")
 
+    def test_the_region_error_does_not_echo_the_url(self):
+        with self.assertRaises(ValueError) as cm:
+            agentcore_client.sigv4_client("http://198.51.100.7:8000/mcp")
+        self.assertIn("--region", str(cm.exception))
+        self.assertNotIn("198.51.100.7", str(cm.exception))
+
 
 if __name__ == "__main__":
     unittest.main(verbosity=2)
diff --git a/scripts/test/test_mcp_smoke.py b/scripts/test/test_mcp_smoke.py
index 72b6903..ad44e12 100644
--- a/scripts/test/test_mcp_smoke.py
+++ b/scripts/test/test_mcp_smoke.py
@@ -4,6 +4,8 @@ import asyncio
 import contextlib
 import io
 import json
+import logging
+import os
 import re
 import sys
 import tempfile
@@ -67,6 +69,9 @@ def fake_server(state: SimpleNamespace) -> FastMCP:
 class _SmokeCase(unittest.IsolatedAsyncioTestCase):
     def setUp(self):
         self.state = SimpleNamespace(active=0, peak=0, sql=[], processlist=list(PROCESSLIST), clients=0)
+        sdk_logger = logging.getLogger("mcp")  # main() installs a redacting handler on it
+        self.enterContext(mock.patch.object(sdk_logger, "handlers", []))
+        self.enterContext(mock.patch.object(sdk_logger, "propagate", True))
         self.server = fake_server(self.state)
         tmp = tempfile.TemporaryDirectory()
         self.addCleanup(tmp.cleanup)
@@ -233,6 +238,46 @@ class TestConns(_SmokeCase):
         self.assertNotIn("10.1.2.3", out)
 
 
+class TestErrorsAreMasked(_SmokeCase):
+    async def test_a_connection_error_is_one_masked_line(self):
+        def refused(_args):
+            raise ConnectionError("POST http://fake/mcp failed (198.51.100.7)")
+
+        self.factory = refused
+        rc, out = await self.run_main("list")
+        self.assertEqual(rc, 1)
+        self.assertIn("FAIL: ConnectionError: POST *** failed (<ip>)\n", out)
+        self.assertNotIn("fake/mcp", out)
+        self.assertRegex(out, r"(?m)^total \d+ ms$")
+
+    async def test_the_bearer_token_is_masked(self):
+        token = "tok-0123456789abcdef"
+
+        def rejected(_args):
+            raise RuntimeError(f"401 for Bearer {token}")
+
+        self.factory = rejected
+        with mock.patch.dict(os.environ, {"GW_TOKEN": token}):
+            rc, out = await self.run_main("--bearer-env", "GW_TOKEN", "list")
+        self.assertEqual(rc, 1)
+        self.assertIn("FAIL: RuntimeError: 401 for Bearer ***\n", out)
+
+    async def test_sdk_log_lines_are_masked(self):
+        real = self.factory
+
+        def logs_the_url(args):
+            logging.getLogger("mcp.client.streamable_http").warning("Session termination failed: POST %s", args.url)
+            return real(args)
+
+        self.factory = logs_the_url
+        err = io.StringIO()
+        with contextlib.redirect_stderr(err):
+            rc, _ = await self.run_main("list")
+        self.assertEqual(rc, 0)
+        self.assertIn("Session termination failed: POST ***", err.getvalue())
+        self.assertNotIn("fake/mcp", err.getvalue())
+
+
 class TestSigV4Option(unittest.TestCase):
     def _parse_error(self, *argv: str) -> None:
         with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
```

- [ ] **Step 3：确认失败**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
for s in scripts doris; do
  .venv/bin/python -m unittest discover -s $s/test > /tmp/t45-red-$s.log 2>&1; echo "$s rc=$?"
  grep -E '^(FAIL|ERROR):' /tmp/t45-red-$s.log | sed -E 's/ \(.*//' | sort -u; grep -E '^Ran |^OK|^FAILED' /tmp/t45-red-$s.log
done
grep -E "^(ModuleNotFoundError|AssertionError)" /tmp/t45-red-scripts.log /tmp/t45-red-doris.log | sed -E 's/^[^:]+://' | cut -c1-110 | sort | uniq -c | sed -E "$MASK"
```
期望（实测，秒数每次不同；失败原因里的地址是测试用的 fixture，同样经过 mask）：
```
scripts rc=1
ERROR: test_a_connection_error_is_one_masked_line
ERROR: test_redact
ERROR: test_the_bearer_token_is_masked
FAIL: test_sdk_log_lines_are_masked
FAIL: test_the_region_error_does_not_echo_the_url
Ran 58 tests in 1.386s
FAILED (failures=2, errors=3)
doris rc=1
ERROR: test_default_remote_client_is_the_sigv4_client
ERROR: test_default_remote_connect_uses_the_sigv4_client
FAIL: test_remote_errors_mask_the_url_and_ipv4_addresses
FAIL: test_sdk_log_lines_are_masked
FAIL: test_the_client_address_in_a_denial_is_masked
Ran 161 tests in 6.347s
FAILED (failures=4, errors=2)
      1 AssertionError: "FAIL  select: internal.ecom.fact_refund: 1105 SELECT command denied to user 'mcp_svc'@'<ip>'"
      1 AssertionError: '' != 'ERROR mcp.client.streamable_http: Error in post_writer: POST *** via <ip>'
      1 AssertionError: '<ip>' unexpectedly found in "cannot tell the region from 'http://<ip>:8000/mc
      1 AssertionError: 'ERROR mcp.client.streamable_http: Error in post_writer: POST ***\n' not found in ''
      1 AssertionError: 'Session termination failed: POST ***' not found in 'Session termination failed: POST http://f
      1 AssertionError: Lists differ: ['FAI[19 chars]POST <url> chars]sed'] !=
      2 ModuleNotFoundError: No module named 'agentcore_client'
      1 ModuleNotFoundError: No module named 'redact'
```
失败的原因都是功能还不存在：
- `test_redact`：模块 `redact` 还不存在（整个文件算 1 个 ERROR）；
- `test_a_connection_error_is_one_masked_line`、`test_the_bearer_token_is_masked`：异常从 `main` 里抛出（ERROR），还没有 `FAIL:` 行；
- `scripts` 的 `test_sdk_log_lines_are_masked`：SDK 的日志行原样输出；`test_the_region_error_does_not_echo_the_url`：消息里有 URL；
- `test_default_remote_client_is_the_sigv4_client`、`test_default_remote_connect_uses_the_sigv4_client`：旧代码只在函数里插入 `sys.path`，测试直接 `import agentcore_client` 找不到模块（ERROR）；
- `doris` 的 2 个 `test_sdk_log_lines_are_masked`、`test_remote_errors_mask_the_url_and_ipv4_addresses`、`test_the_client_address_in_a_denial_is_masked`：输出里还有 URL、IPv4 或客户端地址（`failures=4` 里 `test_sdk_log_lines_are_masked` 有 2 个，`sort -u` 合并成 1 行）。

`test_a_misplaced_drop_is_refused_before_the_secret_is_read` 和 `permission_matrix` 的 `test_a_url_with_an_ipv4_host_is_masked_whole` 在这里**通过**：它们锁定的是已有行为（minor 7），Step 5 的突变 a1、a2d 证明它们能抓到回退。

- [ ] **Step 4：实现**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p4-extract.py scripts/redact.py
.venv/bin/python /tmp/p4-extract.py t45-impl.diff /tmp/t45-impl.diff
git apply /tmp/t45-impl.diff && git status --short && git diff --shortstat
```
期望（实测）：
```
scripts/redact.py -> scripts/redact.py (45 lines)
t45-impl.diff -> /tmp/t45-impl.diff (289 lines)
 M doris/permission_matrix.py
 M doris/reconcile.py
 M doris/test/test_admin_sql.py
 M doris/test/test_permission_matrix.py
 M doris/test/test_reconcile.py
 M scripts/agentcore_client.py
 M scripts/mcp_smoke.py
 M scripts/test/test_agentcore_client.py
 M scripts/test/test_mcp_smoke.py
?? scripts/redact.py
?? scripts/test/test_redact.py
 9 files changed, 172 insertions(+), 57 deletions(-)
```

新文件 `scripts/redact.py`：

<!-- file: scripts/redact.py sha256=558ef2b9708aedcd0ef584b6dfd447d26eb8430d28a98d85a9c19ba7c8d64351 -->
```python
"""Mask secrets and IPv4 addresses in error lines and in the MCP SDK's own log lines (P4 / T4.5).

    import redact
    redact.redact_sdk_logs([url, token])          # mcp.* log records -> stderr, masked
    print(redact.redact(str(e), [url, token]))    # literal secrets -> ***, then IPv4 -> <ip>

The MCP SDK logs transport failures itself (e.g. "Session termination failed", or an httpx error
whose message carries the full URL); the "mcp" logger has no handler of its own, so without this
those records reach stderr unmasked through logging.lastResort.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, TextIO

MASK = "***"
IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def redact(text: str, secrets: Iterable[str | None]) -> str:
    """Literal secrets -> ***, longest first (a host inside the URL), then every IPv4 address -> <ip>."""
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, MASK)
    return IPV4_RE.sub("<ip>", text)


class _RedactingFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str | None]):
        super().__init__("%(levelname)s %(name)s: %(message)s")
        self._secrets = list(secrets)

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record), self._secrets)  # the traceback too


def redact_sdk_logs(secrets: Iterable[str | None], stream: TextIO | None = None) -> logging.Handler:
    """Send the "mcp" logger's records to stream (default: stderr) through redact(), and nowhere else."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_RedactingFormatter(secrets))
    logger = logging.getLogger("mcp")
    logger.handlers[:] = [handler]
    logger.propagate = False
    return handler
```

对 4 个源文件的改动（`git apply`）：

<!-- file: t45-impl.diff sha256=cdffe50299fa31a929ee67a3f434f65dc9da47c4d064eb1ae10049223ca3c624 -->
```diff
diff --git a/doris/permission_matrix.py b/doris/permission_matrix.py
index 71fe1a1..7235c22 100644
--- a/doris/permission_matrix.py
+++ b/doris/permission_matrix.py
@@ -9,8 +9,9 @@ DORIS_SECRET_ID=doris-mcp/mcp_svc (or DORIS_USER/DORIS_PASSWORD).
 With --url the read-only checks go through the deployed Runtime's execute_query tool over SigV4
 (AWS_* credentials; scripts/agentcore_client.py), i.e. as mcp_svc from the VPC: after P3 / T3.5 that
 is the only place the account can log in from. The probes need a direct connection (APPLY=1 refuses
---url); the URL is masked as *** and IPv4 addresses as <ip>. --expect-host H adds a check that the
-connected identity is exactly 'mcp_svc'@'H'.
+--url); the URL is masked as *** and IPv4 addresses as <ip>, in this script's lines and in the MCP
+SDK's own log lines (scripts/redact.py). --expect-host H adds a check that the connected identity is
+exactly 'mcp_svc'@'H'.
 Read-only checks: SHOW GRANTS equals EXPECTED_GRANTS exactly (R-42), SHOW DATABASES equals
 EXPECTED_DATABASES, every physical table of the models is readable, the workspace has a metadata
 row (else upstream would INSERT it, which needs LOAD_PRIV) and active files.
@@ -37,6 +38,7 @@ from typing import Any, Callable, Iterable, Mapping, Sequence, TextIO
 
 ROOT = Path(__file__).resolve().parents[1]
 sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
+sys.path.insert(0, str(ROOT / "scripts"))  # redact, agentcore_client
 MODELS_DIR = ROOT / "doris" / "semantic" / "ecom"
 
 import pymysql  # noqa: E402
@@ -46,7 +48,8 @@ from store.bootstrap import collect_physical_tables  # noqa: E402
 from store.store import (  # noqa: E402
     DorisStore, clear_service_credentials, set_doris_endpoint, set_service_credentials)
 
-MASK = "***"
+import redact  # noqa: E402
+
 EXPECTED_USER = "mcp_svc"
 EXPECTED_GRANTS: dict[str, dict[str, set[str]]] = {
     "DatabasePrivs": {
@@ -63,7 +66,6 @@ DENIED_ERRNOS = frozenset({1044, 1142, 1143, 1227})
 DENIED_1105 = ("access denied", "command denied")  # Doris 4.1 refuses privileges with errno 1105 (T2.3)
 _WORKSPACE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")  # upstream workspace/create rule
 _LITERAL_RE = re.compile(r"^[A-Za-z0-9_]+$")  # what RuntimeCursor inlines without quoting rules
-_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
 _STORE_LOGGER = "doris_new_mcp.store"
 
 
@@ -138,14 +140,14 @@ def classify_error(error: pymysql.MySQLError) -> str:
     return "error"
 
 
-Secrets = Iterable["str | re.Pattern[str]"]  # literal values -> ***, patterns (IPv4) -> <ip>
+Secrets = Iterable[str]  # literal values -> ***; IPv4 addresses -> <ip> regardless (redact.redact)
 
 
 def _brief(error: pymysql.MySQLError, secrets: Secrets) -> str:
     """errno + message, masked before it is cut (a cut secret no longer matches the mask)."""
     errno = error.args[0] if error.args else "?"
     message = str(error.args[1]) if len(error.args) > 1 else str(error)
-    return f"{errno} {_mask(message.replace('errCode = 2, detailMessage = ', ''), secrets)[:160]}"
+    return f"{errno} {redact.redact(message.replace('errCode = 2, detailMessage = ', ''), secrets)[:160]}"
 
 
 def _rows(cur: Any, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
@@ -243,15 +245,6 @@ def upstream_store_init(settings: Settings, workspace: str) -> tuple[bool, str]:
         clear_service_credentials()
 
 
-def _mask(text: str, secrets: Secrets) -> str:
-    for s in secrets:
-        if isinstance(s, re.Pattern):
-            text = s.sub("<ip>", text)
-        elif s:
-            text = text.replace(s, MASK)
-    return text
-
-
 def _inline(sql: str, params: Sequence[Any] | None) -> str:
     """Fill %s with quoted literals; only plain identifiers (the workspace name) are accepted."""
     if not params:
@@ -339,9 +332,6 @@ class RuntimeConnection:
 
 def _runtime_connection(url: str, region: str | None) -> RuntimeConnection:
     """SigV4 MCP session to a Runtime invoke URL (inbound auth AWS_IAM), see scripts/agentcore_client.py."""
-    scripts = str(ROOT / "scripts")
-    if scripts not in sys.path:
-        sys.path.insert(0, scripts)
     import agentcore_client
     return RuntimeConnection(agentcore_client.sigv4_client(url, region))
 
@@ -371,7 +361,8 @@ def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
         return 2
     settings: Settings | None = None
     if args.url:
-        secrets: list[str | re.Pattern[str]] = [args.url, env.get("DORIS_HOST", ""), _IPV4_RE]
+        secrets = [args.url, env.get("DORIS_HOST", "")]
+        redact.redact_sdk_logs(secrets, stream=err)  # the MCP SDK logs transport errors itself, URL included
     else:
         try:
             settings = load_settings(env)
@@ -382,7 +373,7 @@ def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
     tables = sorted(collect_physical_tables(args.models))
 
     def emit(text: str, stream: TextIO = out) -> None:
-        print(_mask(text, secrets), file=stream)
+        print(redact.redact(text, secrets), file=stream)
 
     try:
         if args.url:
@@ -458,7 +449,9 @@ def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
     finally:
         try:
             conn.close()
-        except Exception as e:  # noqa: BLE001 - e.g. --url: the session DELETE failed; the result stands
+        except Exception as e:  # noqa: BLE001 - the result stands
+            # --url: a mid-session transport error (e.g. a 403 once the credentials expire), re-raised by
+            # __aexit__. A failed session DELETE is only logged by the SDK (masked: redact_sdk_logs).
             emit(f"WARN: close: {type(e).__name__}: {e}", err)
     passed = sum(r.ok for r in results)
     emit(f"{passed}/{len(results)} checks pass")
diff --git a/doris/reconcile.py b/doris/reconcile.py
index fc1b6d1..51e44b4 100644
--- a/doris/reconcile.py
+++ b/doris/reconcile.py
@@ -31,6 +31,7 @@ from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence, TextIO
 
 ROOT = Path(__file__).resolve().parents[1]
 sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
+sys.path.insert(0, str(ROOT / "scripts"))  # redact, agentcore_client
 MODELS_DIR = ROOT / "doris" / "semantic" / "ecom"
 
 import pymysql  # noqa: E402
@@ -41,7 +42,7 @@ from store.bootstrap import bootstrap_from_yaml  # noqa: E402
 from store.compiler import MetricFlowCompiler  # noqa: E402
 from store.manifest import SemanticManifest  # noqa: E402
 
-MASK = "***"
+import redact  # noqa: E402
 MAX_PROBLEMS = 10
 # Ratios and averages are computed in DOUBLE (or scale-6 DECIMAL); everything else is an exact sum/count.
 APPROX_METRICS = frozenset(
@@ -206,16 +207,9 @@ def compare(case: Case, got: Sequence[Mapping[str, Any]], want: Sequence[Mapping
     return problems
 
 
-def _mask(text: str, secrets: Iterable[str]) -> str:
-    for s in secrets:
-        if s:
-            text = text.replace(s, MASK)
-    return text
-
-
 def _failed(error: Exception, secrets: Iterable[str], err: TextIO) -> int:
     """One masked line instead of a traceback: the message may name the host or carry a password."""
-    print(f"FAILED: {type(error).__name__}: {_mask(str(error), secrets)}", file=err)
+    print(f"FAILED: {type(error).__name__}: {redact.redact(str(error), secrets)}", file=err)
     return 1
 
 
@@ -277,10 +271,10 @@ class McpBackend:
         try:
             body = json.loads(text)
         except ValueError:
-            raise ReconcileError(f"{tool}: non-JSON result: {_mask(text, self.secrets)[:300]}") from None
+            raise ReconcileError(f"{tool}: non-JSON result: {redact.redact(text, self.secrets)[:300]}") from None
         if not isinstance(body, dict) or body.get("success") is not True:
             error = body.get("error", body) if isinstance(body, dict) else body
-            raise ReconcileError(f"{tool}: {_mask(json.dumps(error, ensure_ascii=False), self.secrets)[:500]}")
+            raise ReconcileError(f"{tool}: {redact.redact(json.dumps(error, ensure_ascii=False), self.secrets)[:500]}")
         return body
 
     async def metric_names(self) -> set[str]:
@@ -317,7 +311,7 @@ async def reconcile(cases: Sequence[Case], query: Callable[[Case], Awaitable[lis
             failed += 1
             print(f"FAIL  {case.name}: {len(problems)} problem(s)", file=out)
             for problem in problems[:MAX_PROBLEMS]:
-                print(f"      {_mask(problem, secrets)}", file=out)
+                print(f"      {redact.redact(problem, secrets)}", file=out)
         else:
             print(f"ok    {case.name} ({len(want)} rows)", file=out)
     print(f"{len(cases) - failed}/{len(cases)} cases match", file=out)
@@ -334,9 +328,6 @@ def _in_process_client(settings: Settings) -> Any:
 
 def _remote_client(url: str, region: str | None) -> Any:
     """fastmcp Client for a Runtime invoke URL (inbound auth AWS_IAM), see scripts/agentcore_client.py."""
-    scripts = str(ROOT / "scripts")
-    if scripts not in sys.path:
-        sys.path.insert(0, scripts)
     import agentcore_client
 
     return agentcore_client.sigv4_client(url, region)
@@ -394,12 +385,15 @@ def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
     except Exception as e:  # noqa: BLE001 - e.g. boto3 client setup for DORIS_SECRET_ID
         return _failed(e, [env.get("DORIS_PASSWORD", ""), env.get("DORIS_HOST", "")], err)
     secrets = [settings.doris_password, settings.doris_host]  # pymysql errors name the host
+    if args.url:
+        secrets.append(args.url)
+        redact.redact_sdk_logs(secrets, stream=err)  # the MCP SDK logs transport errors itself, URL included
     try:
         conn = connect(host=settings.doris_host, port=settings.doris_port, user=settings.doris_user,
                        password=settings.doris_password, connect_timeout=10, read_timeout=120,
                        autocommit=True, cursorclass=pymysql.cursors.DictCursor)
     except pymysql.MySQLError as e:
-        print(f"FAILED: connect: {_mask(str(e), secrets)}", file=err)
+        print(f"FAILED: connect: {redact.redact(str(e), secrets)}", file=err)
         return 1
 
     logging.disable(logging.WARNING)  # MetricFlow and the server are chatty below ERROR
@@ -419,7 +413,7 @@ def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
                 client = (client_factory or _in_process_client)(dataclasses.replace(settings, workspace_dir=tmp))
                 failed = asyncio.run(_run_mcp(client, args.models, args.workspace, cases, reference, out, secrets))
     except ReconcileError as e:
-        print(f"FAILED: {_mask(str(e), secrets)}", file=err)
+        print(f"FAILED: {redact.redact(str(e), secrets)}", file=err)
         return 1
     except Exception as e:  # noqa: BLE001 - e.g. client_factory / build_server, a transport error
         return _failed(e, secrets, err)
diff --git a/scripts/agentcore_client.py b/scripts/agentcore_client.py
index 59db906..c551bba 100644
--- a/scripts/agentcore_client.py
+++ b/scripts/agentcore_client.py
@@ -4,9 +4,10 @@
     async with sigv4_client(runtime_url) as client:
         await client.list_tools()
 
-Credentials come from the default botocore chain (here: the AWS_* environment variables) and are
-re-read before each request, so refreshed session credentials are picked up. The region comes from
-the URL unless given: this dev box sets AWS_DEFAULT_REGION=us-west-2, the Runtime is in us-east-1.
+Credentials come from the default botocore chain (here: the AWS_* environment variables), resolved
+once when the client is built: a refreshable provider (SSO, assume-role) refreshes itself before each
+signature, static AWS_* keys stay fixed for the client's lifetime. The region comes from the URL
+unless given: this dev box sets AWS_DEFAULT_REGION=us-west-2, the Runtime is in us-east-1.
 One Client is one MCP session (Mcp-Session-Id), i.e. one Runtime microVM; the Gateway opens a new
 session for every tool call.
 """
@@ -59,5 +60,7 @@ class SigV4Auth(httpx.Auth):
 def sigv4_client(url: str, region: str | None = None, timeout: float = 90.0) -> Client:
     region = region or region_from_url(url)
     if not region:
-        raise ValueError(f"cannot tell the region from {url!r}; pass --region")
+        # Not the URL itself: callers print this message, and the URL may carry a host.
+        raise ValueError("cannot tell the region from the URL (not https://bedrock-agentcore.<region>"
+                         ".amazonaws.com/...); pass --region")
     return Client(StreamableHttpTransport(url, auth=SigV4Auth(region)), timeout=timeout)
diff --git a/scripts/mcp_smoke.py b/scripts/mcp_smoke.py
index 194b659..042e04e 100644
--- a/scripts/mcp_smoke.py
+++ b/scripts/mcp_smoke.py
@@ -13,6 +13,9 @@ Examples:
 
 The bearer token is read from the named environment variable and never printed. `time` and `conns`
 print status, timings, error codes and counts only: never tool output, SQL results, hosts or statements.
+A session or call that raises is one FAIL line with the URL and the token masked as *** and IPv4
+addresses as <ip>; with --url the MCP SDK's own log lines go to stderr masked the same way
+(scripts/redact.py).
 Exit code: 0 on success, 1 when a tool call returns an error or a check fails, 2 on a bad calls file.
 """
 
@@ -30,6 +33,8 @@ from pathlib import Path
 from fastmcp import Client
 from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
 
+import redact  # scripts/ is on sys.path when this file is run as a script
+
 DEFAULT_CALLS = Path(__file__).resolve().parent / "smoke_calls.json"
 
 
@@ -300,13 +305,20 @@ def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
 
 async def main(argv: list[str] | None = None, client_factory=build_client) -> int:
     args = parse_args(argv)
+    hidden = [args.url, os.environ.get(args.bearer_env, "") if args.bearer_env else ""]
+    if args.url:
+        redact.redact_sdk_logs(hidden)
     start = time.monotonic()
-    if args.command == "time":
-        rc = await cmd_time(args, client_factory)
-    else:
-        async with client_factory(args) as client:
-            print(f"connected+initialized in {round((time.monotonic() - start) * 1000)} ms")
-            rc = await COMMANDS[args.command](client, args)
+    try:
+        if args.command == "time":
+            rc = await cmd_time(args, client_factory)
+        else:
+            async with client_factory(args) as client:
+                print(f"connected+initialized in {round((time.monotonic() - start) * 1000)} ms")
+                rc = await COMMANDS[args.command](client, args)
+    except Exception as e:  # noqa: BLE001 - one masked line instead of a traceback naming the URL
+        print(f"FAIL: {type(e).__name__}: {redact.redact(str(e), hidden)}")
+        rc = 1
     print(f"total {round((time.monotonic() - start) * 1000)} ms")
     return rc
 
```

- [ ] **Step 5：确认通过；突变；手工 FAIL 检查；在线只读核对**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                                # 期望：Ran 65 tests … OK
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 161 tests … OK
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 期望：Ran 89 tests … OK
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3     # 期望：🎉 All tests passed!
for t in doris/test/test-apply-admin-sql.sh doris/test/test-publish-semantic.sh infra/test/test-35-runtime-role.sh \
         infra/test/test-40-doris-secret.sh infra/test/test-lib.sh scripts/test/test-check-secrets.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 期望：每行 all passed
.venv/bin/python /tmp/p4-mut.py /tmp/p4-mutations.json t45; echo "rc=$?"
```
突变期望（实测）：
```
a1: caught by test_a_misplaced_drop_is_refused_before_the_secret_is_read (Ran 19, FAILED (failures=1))
a2: caught by test_a_url_with_an_ipv4_host_is_masked_whole, test_longer_secrets_are_replaced_first (Ran 8, FAILED (failures=2))
a2d: caught by test_a_url_with_an_ipv4_host_is_masked_whole, test_an_unexpected_error_is_one_masked_line_and_exit_2 (Ran 63, FAILED (failures=2))
a3: caught by test_longer_secrets_are_replaced_first (Ran 8, FAILED (failures=1))
a4: caught by test_one_handler_and_nothing_reaches_the_root_logger (Ran 8, FAILED (failures=1))
a5: caught by test_one_handler_and_nothing_reaches_the_root_logger (Ran 8, FAILED (failures=1))
a6: caught by test_one_handler_and_nothing_reaches_the_root_logger, test_sdk_log_lines_are_redacted, test_sdk_tracebacks_are_redacted (Ran 8, FAILED (failures=3))
a7: caught by test_the_bearer_token_is_masked (Ran 24, FAILED (failures=1))
a8: caught by test_sdk_log_lines_are_masked (Ran 24, FAILED (failures=1))
a9: caught by test_remote_errors_mask_the_url_and_ipv4_addresses, test_sdk_log_lines_are_masked (Ran 39, FAILED (failures=2))
a10: caught by test_sdk_log_lines_are_masked (Ran 63, FAILED (failures=1))
a11: caught by test_the_region_error_does_not_echo_the_url (Ran 14, FAILED (failures=1))
12/12 mutations caught; tree unchanged: True
rc=0
```

手工 FAIL 检查：连一个本地没有服务的端口，用假 token（不是真的 secret），确认输出只有一行 mask 过的 FAIL，地址和 token 的计数都是 0：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
GW_TOKEN=fake-token-0123456789 .venv/bin/python scripts/mcp_smoke.py --url http://127.0.0.1:9/mcp --timeout 5 --bearer-env GW_TOKEN list > /tmp/t45-fail.txt 2>&1; echo "exit=$?"
cat /tmp/t45-fail.txt; grep -cE '127\.0\.0\.1|fake-token' /tmp/t45-fail.txt
```
期望（实测，毫秒数每次不同）：
```
exit=1
FAIL: RuntimeError: Client failed to connect: All connection attempts failed
total 32 ms
0
```

在线只读核对（改过的 `mcp_smoke.py` 经 Gateway、`reconcile.py` / `permission_matrix.py` 经 SigV4 各跑一次）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
source infra/state.env
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN --timeout 60 list --expect 12 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
unset GW_TOKEN
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_USER="$DORIS_RO_USER" DORIS_PASSWORD="$DORIS_RO_PASSWORD" AWS_REGION=us-east-1
  unset DORIS_ROOT_USER DORIS_ROOT_PASSWORD DORIS_RO_USER DORIS_RO_PASSWORD DORIS_ADMIN_PASSWORD
  exec .venv/bin/python doris/reconcile.py mcp --url "$RUNTIME_URL" ) 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
.venv/bin/python doris/permission_matrix.py --url "$RUNTIME_URL" --expect-host '172.31.%' 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
```
期望（实测，毫秒数每次不同）：
```
connected+initialized in 642 ms
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
total 1577 ms
exit=0
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
exit=0
```
其中 `WARNING mcp.client.streamable_http: Session termination failed: 404` 是预期的：经 Runtime 关闭 session 时，Runtime 对 DELETE 回 404，这是 SDK 自己记的一行日志，现在经 `redact_sdk_logs` 输出（有地址也会被 mask）。它出现在哪一段、出不出现，每次可能不同；除这一行以外不应有别的 WARNING 或 traceback。

- [ ] **Step 6：收尾，提交**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - T4.5 <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
echo 'Task 1（T4.5）已完成；Task 2（T4.3）从 Step 1 开始' | .venv/bin/python /tmp/p4-progress.py state 进行中
echo 'Task 2（T4.3 agent 指令），然后 Task 3（T4.6）、Task 4（T4.1 + T4.4：先整体评审，再交给用户在 Quick 里操作 40–60 分钟）。P4 没有 GATE' | .venv/bin/python /tmp/p4-progress.py state 下一步
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p4-progress.py log
### @DATE@ P4 Task 1（T4.5）：URL / IPv4 mask 收口

- 新模块 `scripts/redact.py`：`redact()` 先把字面 secret（URL、token、`DORIS_HOST`）从长到短换成 `***`，再把 IPv4 换成 `<ip>`；`redact_sdk_logs()` 接管 `mcp` logger（唯一的 handler，`propagate=False`）。
- `mcp_smoke.py` 的异常变成一行 mask 过的 `FAIL:`，exit 1；`reconcile.py mcp --url`、`permission_matrix.py` 的错误输出 mask URL 和 IPv4，并接管 SDK 日志；`agentcore_client` 的 ValueError 不回显 URL，docstring 更正；两处 lazy `sys.path` 改成模块顶部一次。
- 关闭的遗留：T3.3 的 URL mask 三项和 docstring；T3.0 的 `permission_matrix` 客户端地址；T3.6 M1（关闭 session 的注释、SDK 日志行）、M2（2 个锁定测试）；P3 整体评审 Minor #4。P3 整体评审的 Minor #1、#3、#5、#6 已由 design v0.6、RESUME 和计划在 Step 1 关闭。
- RED：`scripts/test` Ran 58，`failures=2, errors=3`；`doris/test` Ran 161，`failures=4, errors=2`。两个锁定测试在 RED 里通过，由突变 a1、a2d 证明有效。
- GREEN：`scripts/test` 65、`doris/test` 161、`test_agentcore_*.py` 89、upstream 离线、6 组 shell 全部通过；突变 12/12 被抓到，工作区恢复原样。
- 手工 FAIL 检查：一行 `FAIL: RuntimeError: …`，地址和假 token 计数 0。
- 在线只读：经 Gateway `list` 12 个；`reconcile.py mcp --url` 11/11；`permission_matrix.py --url` 5/5。只读调用：sts、Cognito（`get-gw-token.sh`）、Gateway MCP、SigV4 `InvokeAgentRuntime`、check-secrets 的 `get-secret-value`。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add scripts/redact.py scripts/test/test_redact.py scripts/mcp_smoke.py scripts/test/test_mcp_smoke.py \
        scripts/agentcore_client.py scripts/test/test_agentcore_client.py doris/reconcile.py doris/test/test_reconcile.py \
        doris/permission_matrix.py doris/test/test_permission_matrix.py doris/test/test_admin_sql.py \
        specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
test -n "$v" && git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); unset v   # 期望：0
git commit -q -F - <<'EOF'
fix(p4): T4.5 one redact() for URLs, tokens and IPv4 in errors and MCP SDK logs; T3.6 M2 tests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1   # 期望：工作区干净
```
日志里的数字如果和实测不同，写实测值。

---

### Task 2：T4.3「Doris 专家」agent 指令 + 16 个检查

来源：tasks.md T4.3、design §8.3（角色 / 硬约束 / 演示口径）、§4.4（Quick 指令上限 5 万字符）、§10（「开场 + 第 2 幕」的两个问题）。指令文件由用户手工粘贴进 Quick，所以这些检查就是改动和演示之间唯一的一道关：长度、三段结构、演示依赖的规则、工具名、指标名和维度名、不能出现的内容。

**Files:**
- Create: `quick/agent-instructions.md`、`quick/test/test_agent_instructions.py`（`quick/test` 0 → 16）
- Modify: `specs/doris-mcp-quick/tasks.md`、`progress.md`

**Interfaces:**
- Consumes：`doris/reconcile.py` 的 `MODELS_DIR`、`Case(name, metrics, group_by, where, sql)`、`DirectBackend(models_dir, workspace_dir, fetch=None)`（`.metric_names() -> set[str]`、`.sql(case) -> str`，编译失败抛 `ReconcileError`）；`scripts/smoke_calls.json`（12 个工具，每项有 `tool`）。
- Produces（Task 4 使用）：`quick/agent-instructions.md`，1924 个字符，只用 `doris___` 前缀的工具名；Task 4 的 P4-guide Part B 让用户全文粘贴。

- [ ] **Step 1：写失败测试**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p4-extract.py quick/test/test_agent_instructions.py
```
期望：`quick/test/test_agent_instructions.py -> quick/test/test_agent_instructions.py (152 lines)`

<!-- file: quick/test/test_agent_instructions.py sha256=95aadae73abd86325fb608612e13131b3b068f6b43fb7bb09e0354728f1ef556 -->
```python
"""quick/agent-instructions.md: the instructions of the "Doris 专家" agent in Quick (P4 / T4.3).

The file is pasted into Quick by hand, so these checks are what stands between an edit and the demo: Quick's
size limit, the three parts of design §8.3, the rules the demo depends on, tool names that exist behind the
Gateway, metric and dimension names that the semantic layer publishes and compiles, and nothing that must not
leave the repo.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "doris"))
from reconcile import MODELS_DIR, Case, DirectBackend, ReconcileError  # noqa: E402  (compiles like the server's query_metric)

INSTRUCTIONS = ROOT / "quick" / "agent-instructions.md"
QUICK_LIMIT = 50_000  # characters; design §4.4
GATEWAY_PREFIX = "doris___"  # <target>___<tool>, design §4.5


def _text() -> str:
    return INSTRUCTIONS.read_text(encoding="utf-8")


def _section(title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", _text(), re.M | re.S)
    if match is None:
        raise AssertionError(f"no section '## {title}'")
    return match.group(1)


def setUpModule():
    logging.disable(logging.WARNING)  # MetricFlow is chatty at INFO/WARNING


def tearDownModule():
    logging.disable(logging.NOTSET)


class Shape(unittest.TestCase):
    def test_fits_the_quick_limit(self):
        self.assertLessEqual(len(_text()), QUICK_LIMIT)

    def test_has_exactly_the_three_parts_of_design_8_3(self):
        self.assertEqual(re.findall(r"^## (.+)$", _text(), re.M), ["角色", "硬约束", "演示口径"])


class Rules(unittest.TestCase):
    def test_the_role_is_the_doris_expert_on_the_ecom_cluster(self):
        role = _section("角色")
        for term in ("Doris 专家", "ecom"):
            self.assertIn(term, role)

    def test_answers_rest_on_tool_results(self):
        rules = _section("硬约束")
        for term in ("证据", f"{GATEWAY_PREFIX}check_service_health", f"{GATEWAY_PREFIX}list_metrics",
                     f"{GATEWAY_PREFIX}query_metric", f"{GATEWAY_PREFIX}execute_query"):
            self.assertIn(term, rules)

    def test_read_only_and_ddl_is_proposed_not_run(self):
        rules = _section("硬约束")
        for term in ("只读", "DDL", "不执行", "人工执行"):
            self.assertIn(term, rules)

    def test_the_60_second_limit_and_how_to_stay_under_it(self):
        rules = _section("硬约束")
        for term in ("60 s", "EXPLAIN", "LIMIT", "424"):
            self.assertIn(term, rules)

    def test_the_semantic_layer_is_not_reloaded_unasked(self):
        self.assertIn(f"{GATEWAY_PREFIX}reload_semantic_layer", _section("硬约束"))

    def test_connection_details_are_not_repeated(self):
        rules = _section("硬约束")
        for term in ("主机", "IP", "账号"):
            self.assertIn(term, rules)

    def test_the_demo_day_and_what_this_year_and_last_year_mean(self):
        framing = _section("演示口径")
        for term in ("2026-09-25", "12:00", "中秋", "今年 = 2026", "去年同期 = 2025"):
            self.assertIn(term, framing)

    def test_the_yoy_metrics_need_a_month_grouping_and_an_end_date(self):
        framing = _section("演示口径")
        for term in ("gmv_last_year", "gmv_yoy", "metric_time__month",
                     "metric_time BETWEEN '2026-01-01' AND '2026-09-25'"):
            self.assertIn(term, framing)

    def test_ratios_are_fractions_and_a_zero_yoy_means_no_data(self):
        framing = _section("演示口径")
        for term in ("mini_program_share", "0~1", "无数据"):
            self.assertIn(term, framing)


class SemanticLayer(unittest.TestCase):
    """The names the agent is told to use are what list_metrics publishes and query_metric compiles."""

    @classmethod
    def setUpClass(cls):
        workspace = tempfile.TemporaryDirectory(prefix="t43_")
        cls.addClassCleanup(workspace.cleanup)
        cls.backend = DirectBackend(MODELS_DIR, workspace.name, fetch=None)
        cls.published = cls.backend.metric_names()

    def test_the_metric_count_is_the_published_one(self):
        self.assertIn(f"{len(self.published)} 个业务指标", _section("角色"))

    def test_metric_and_dimension_names_exist_in_the_semantic_layer(self):
        names = {n for n in re.findall(r"`([a-z][a-z0-9_]*)`", _text())
                 if n != "ecom" and not n.startswith(GATEWAY_PREFIX)}
        dimensions = {n for n in names if "__" in n}  # <entity>__<dimension>, metric_time__<grain>
        metrics = names - dimensions
        self.assertTrue(metrics and dimensions)
        self.assertLessEqual(metrics, self.published)
        for dimension in sorted(dimensions):
            with self.subTest(dimension=dimension):
                try:
                    self.backend.sql(Case(dimension, ("gmv",), (dimension,), "", ""))
                except ReconcileError as e:
                    self.fail(f"group_by {dimension}: {e}")


class Hygiene(unittest.TestCase):
    def test_every_tool_named_exists_behind_the_gateway(self):
        calls = json.loads((ROOT / "scripts" / "smoke_calls.json").read_text(encoding="utf-8"))
        tools = {GATEWAY_PREFIX + c["tool"] for c in calls}
        self.assertEqual(len(tools), 12)
        named = set(re.findall(rf"\b{GATEWAY_PREFIX}\w+", _text()))
        self.assertTrue(named)
        self.assertLessEqual(named, tools)

    def test_every_tool_name_has_the_gateway_prefix(self):
        bare = {c["tool"] for c in json.loads((ROOT / "scripts" / "smoke_calls.json").read_text(encoding="utf-8"))}
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

- [ ] **Step 2：确认失败**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s quick/test > /tmp/t43-red.log 2>&1; echo "rc=$?"
grep -cE '^ERROR: ' /tmp/t43-red.log; grep -E '^FileNotFoundError' /tmp/t43-red.log | sort | uniq -c | sed -E 's#/home/[^ ]*/quick/#<repo>/quick/#'
grep -E '^Ran |^OK|^FAILED' /tmp/t43-red.log
```
期望（实测）：
```
rc=1
16
     16 FileNotFoundError: [Errno 2] No such file or directory: '<repo>/quick/agent-instructions.md'
Ran 16 tests in 0.112s
FAILED (errors=16)
```
16 个都因为 `quick/agent-instructions.md` 还不存在而 ERROR（`SemanticLayer` 的 `setUpClass` 能正常编译语义层，出错的是读指令文件）。

- [ ] **Step 3：写指令**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p4-extract.py quick/agent-instructions.md
```
期望：`quick/agent-instructions.md -> quick/agent-instructions.md (28 lines)`

<!-- file: quick/agent-instructions.md sha256=32d53bd13b5c871efe5ed61c015e90cea9a9c8bf24f335c8fbf34670bdb06542 -->
```markdown
# Doris 专家

## 角色

你是 Apache Doris 专家，连接的是一套真实的 Doris 集群。业务库是电商演示库 `ecom`（订单、商品明细、店铺、类目、品牌、地区、退款、评价、埋点）；语义层 workspace 也叫 `ecom`，里面定义了 GMV、订单数、客单价等 22 个业务指标。你的用户是这家电商平台的数据负责人。用中文回答：先给结论，再给支撑结论的数字和依据。

## 硬约束

1. **证据优先。** 回答里的每个数字、每个判断都要来自本次对话里的工具调用结果；拿不到证据就直说，不猜、不编。回答末尾用一两行列出用到的工具和指标名（或 SQL）。
   - 用户要求检查连接，或者本次对话第一次需要数据时，先调用 `doris___check_service_health`。
   - 问业务指标（GMV、订单数、客单价、同比、占比、退款率等）：先用 `doris___list_metrics`（workspace `ecom`）确认指标名和 description，再用 `doris___query_metric` 查询。语义层里没有的，才用 `doris___execute_query` 写 SQL。
   - 能在一次 `doris___query_metric` 里取到的多个指标，放在同一次调用里。每次工具调用都要等 5–10 s（每次都是一次新的冷启动），调用越少，回答越快。
   - 不要调用 `doris___reload_semantic_layer`，除非用户明确要求；查询时会自动使用最新的语义层。
2. **只读。** `doris___execute_query` 只用于 SELECT、SHOW、DESCRIBE、EXPLAIN。不执行任何写操作（INSERT、UPDATE、DELETE、CREATE、ALTER、DROP、TRUNCATE），也不要为了「试一下」去执行。需要建表、改表、建物化视图时，只给出 DDL 和理由，由人工执行。
3. **60 s 超时。** 每次工具调用最多 60 s，超时 Quick 会报 424。明细查询和大表查询先用 EXPLAIN 看计划，再加 LIMIT 或先聚合，不要一次取回成千上万行。遇到 424，把查询缩小后重试一次；仍然失败就告诉用户。
4. **不复述连接信息。** 回答里不出现主机地址、IP、端口、账号、URL。工具结果里有这些时，概括成「Doris FE 连接正常」这样的描述。

## 演示口径

- 演示设定：今天是 2026-09-25（中秋节），现在是 12:00。「今天」「本月」「今年」都按这个时间算，不按系统时钟。
- 今年 = 2026，去年同期 = 2025。订单数据从 2025-01-01 开始，历史订单到 2026-09-24；2026-09-25 上午的订单由演示者现场实时写入，写入之前今天是 0 单，这是正常的。
- 2026 年 9 月只到 25 日。拿它和 2025 年 9 月整月比较时，要说明这一点。
- 同比用 `gmv_last_year`（去年同期 GMV）和 `gmv_yoy`（GMV 同比增长率）。这两个指标必须按月分组（group_by `metric_time__month`），where 必须写结束日期，例如 `metric_time BETWEEN '2026-01-01' AND '2026-09-25'`；不写结束日期，结果会多出 2026-10 到 2026-12 这几行，它们只有去年的值。
- 2025 年及更早的期间没有去年同期数据，`gmv_last_year`、`gmv_yoy` 返回 0 表示「无数据」，不是「持平」。
- 比率类指标返回小数：`mini_program_share`（小程序 GMV 占比）、`gross_margin`、`refund_rate`、`bad_review_rate` 在 0~1 之间，`gmv_yoy` 可能为负，也可能大于 1。展示时换算成百分比。
- 小程序渠道是 `order_entity__channel = 'MINI_PROGRAM'`；分渠道看时 group_by `order_entity__channel`。
- 按类目、品牌、店铺看 GMV 用 `line_gmv`（商品行实付，不含运费）；不要把订单级指标 `gmv`、`order_count`、`aov` 按类目拆分。
- 时间范围写成 `metric_time BETWEEN '…' AND '…'`。
```

- [ ] **Step 4：确认通过**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s quick/test 2>&1 | tail -3
.venv/bin/python -c 'print(len(open("quick/agent-instructions.md", encoding="utf-8").read()), "chars")'
```
期望（实测）：
```
Ran 16 tests in 0.125s

OK
1924 chars
```

- [ ] **Step 5：突变；其他测试不受影响**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p4-mut.py /tmp/p4-mutations.json t43; echo "rc=$?"
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -1     # 期望：OK（161 个，不变）
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -1   # 期望：OK（65 个，不变）
```
突变期望（实测）：
```
i1: caught by test_the_semantic_layer_is_not_reloaded_unasked (Ran 16, FAILED (failures=1))
i2: caught by test_answers_rest_on_tool_results, test_every_tool_name_has_the_gateway_prefix, test_metric_and_dimension_names_exist_in_the_semantic_layer (Ran 16, FAILED (failures=3))
i3: caught by test_metric_and_dimension_names_exist_in_the_semantic_layer (Ran 16, FAILED (failures=1))
i4: caught by test_metric_and_dimension_names_exist_in_the_semantic_layer (Ran 16, FAILED (failures=1))
i5: caught by test_the_metric_count_is_the_published_one (Ran 16, FAILED (failures=1))
5/5 mutations caught; tree unchanged: True
rc=0
```

- [ ] **Step 6：收尾，提交**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - T4.3 <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
echo 'Task 2（T4.3）已完成；Task 3（T4.6）从 Step 1 开始' | .venv/bin/python /tmp/p4-progress.py state 进行中
echo 'Task 3（T4.6 `gw_latency.py`），然后 Task 4（T4.1 + T4.4：先整体评审，再交给用户在 Quick 里操作 40–60 分钟）。P4 没有 GATE' | .venv/bin/python /tmp/p4-progress.py state 下一步
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p4-progress.py log
### @DATE@ P4 Task 2（T4.3）：「Doris 专家」agent 指令

- `quick/agent-instructions.md`：角色 / 硬约束 / 演示口径三段（design §8.3），1924 个字符（Quick 上限 5 万）。硬约束 4 条：证据优先（先 `doris___check_service_health`；业务指标先 `doris___list_metrics` 再 `doris___query_metric`，合并调用；不主动 reload）、只读、60 s 超时、不复述连接信息。
- `quick/test/test_agent_instructions.py` 16 个检查：Shape 2、Rules 9、SemanticLayer 2（`DirectBackend` 本机编译，指标数 22、指标名和维度名都存在）、Hygiene 3（工具名都在 Gateway 的 12 个里且带 `doris___` 前缀；没有 URL / IP / ARN / 账号）。
- RED：16 个 ERROR（指令文件不存在）；GREEN：16 个 OK；突变 i1–i5 5/5 被抓到。`doris/test` 161、`scripts/test` 65 不变。全部离线。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add quick/agent-instructions.md quick/test/test_agent_instructions.py specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
test -n "$v" && git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); unset v   # 期望：0
git commit -q -F - <<'EOF'
feat(p4): T4.3 Doris expert agent instructions + 16 checks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1   # 期望：工作区干净
```

---

### Task 3：T4.6 `scripts/gw_latency.py`（Gateway 侧每次工具调用的耗时，M-3）

来源：tasks.md T4.6；P0 评审 M-3（P0 只测了 Gateway 侧，没有 Quick 侧的耗时）；design §4.4、§13（Quick 60 s 硬上限、`query_timeout` 50 s 时端到端可能超过 60 s）。Quick 从自己的后端调用 Cloud Connector（CloudTrail 里的 UA 是 `Google-HTTP-Java-Client`），所以 Gateway 的 `InvokeGateway` Latency 就是 Quick 每次工具调用等待的时间。T4.4 用它记录每次工具调用的耗时，T5.4 彩排也用它。

**Files:**
- Create: `scripts/gw_latency.py`、`scripts/test/test_gw_latency.py`（`scripts/test` 65 → 75）
- Modify: `specs/doris-mcp-quick/tasks.md`、`progress.md`

**Interfaces:**
- Consumes：CloudWatch 指标 `AWS/Bedrock-AgentCore` `Latency`，维度 `Method, Name, Operation, Protocol, Resource`（`Operation=InvokeGateway`、`Method=tools/call`、`Resource` = Gateway ARN、`Name` = 工具名）；`aws cloudwatch get-metric-data --output json` 的 `MetricDataResults`。
- Produces（Task 4、T5.4 使用）：
  - `gw_latency.queries(gateway_arn) -> list[dict]`：Id `calls` / `avg` / `max`，Label `${PROP('Dim.Name')}`，60 s；
  - `gw_latency.parse_rows(doc) -> {(minute, tool): {"calls", "avg", "max"}}`，minute 是 `YYYY-MM-DDTHH:MM`；
  - CLI：`queries --gateway-arn ARN`（不是 Gateway ARN 时 `FAIL: --gateway-arn is not a Gateway ARN`，exit 2）；`report [--warn-ms 45000] [--limit-ms 60000]`：第一行 `tools/call: N calls in R rows (tool x minute), max M ms (TOOL at MINUTE)`，每行 `  MINUTE  TOOL  n calls  avg … ms  max … ms`，然后 `  [PASS|FAIL] every minute under 60000 ms`，有 ≥ 45000 ms 的再加一行 `  [WARN] …`；exit 0 / 1（超限或没有数据点）/ 2（输入不是 get-metric-data JSON）。只输出工具名、时间和毫秒数，不输出 ARN。

- [ ] **Step 1：写失败测试**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p4-extract.py scripts/test/test_gw_latency.py
```
期望：`scripts/test/test_gw_latency.py -> scripts/test/test_gw_latency.py (122 lines)`

<!-- file: scripts/test/test_gw_latency.py sha256=88e90d134207a8000d554afe671d5d20e46dc9396becdf8e2d246ad4fcfcdd57 -->
```python
"""scripts/gw_latency.py: per-minute latency of the Gateway's tools/call from CloudWatch (P4 / T4.6, P0 review M-3)."""

import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gw_latency  # noqa: E402

ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/doris-mcp-gw-abc123"
T1, T2, T3 = "2026-09-27T13:49:00+00:00", "2026-09-27T13:50:00+00:00", "2026-09-27T13:51:00+00:00"


def result(id_: str, tool: str, points: dict[str, float]) -> dict:
    return {"Id": id_, "Label": tool, "Timestamps": list(points), "Values": list(points.values()),
            "StatusCode": "Complete"}


def minute(tool: str, at: str, calls: int, avg: float, peak: float) -> list[dict]:
    return [result("calls", tool, {at: calls}), result("avg", tool, {at: avg}), result("max", tool, {at: peak})]


def doc(*results: dict) -> str:
    return json.dumps({"MetricDataResults": list(results), "Messages": []})


def run(stdin: str, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    rc = gw_latency.main(["report", *argv], stdin=io.StringIO(stdin), out=out)
    return rc, out.getvalue()


class Queries(unittest.TestCase):
    def test_one_search_per_statistic_labelled_with_the_tool_name(self):
        queries = gw_latency.queries(ARN)
        self.assertEqual([q["Id"] for q in queries], ["calls", "avg", "max"])
        for query, stat in zip(queries, ("SampleCount", "Average", "Maximum")):
            self.assertEqual(query["Label"], "${PROP('Dim.Name')}")
            expression = query["Expression"]
            self.assertTrue(expression.startswith(
                "SEARCH('{AWS/Bedrock-AgentCore,Method,Name,Operation,Protocol,Resource} "), expression)
            self.assertTrue(expression.endswith(f"', '{stat}', 60)"), expression)
            for term in ('MetricName="Latency"', 'Operation="InvokeGateway"', 'Method="tools/call"',
                         f'Resource="{ARN}"'):
                self.assertIn(term, expression)

    def test_the_cli_prints_the_queries_as_json(self):
        out = io.StringIO()
        self.assertEqual(gw_latency.main(["queries", "--gateway-arn", ARN], out=out), 0)
        self.assertEqual(json.loads(out.getvalue()), gw_latency.queries(ARN))

    def test_refuses_a_value_that_is_not_a_gateway_arn(self):
        for bad in ("doris-mcp-gw-abc123", ARN + "\" Name=\"x", ARN.replace("gateway/", "runtime/")):
            with self.subTest(bad=bad):
                out = io.StringIO()
                self.assertEqual(gw_latency.main(["queries", "--gateway-arn", bad], out=out), 2)
                self.assertEqual(out.getvalue(), "FAIL: --gateway-arn is not a Gateway ARN\n")


class Report(unittest.TestCase):
    def test_one_line_per_minute_and_tool_in_time_order(self):
        rc, out = run(doc(*minute("doris___query_metric", T3, 1, 9269, 9269),
                          *minute("doris___check_service_health", T1, 1, 5432, 5432),
                          *minute("doris___list_metrics", T3, 2, 6100.4, 6752)))
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.splitlines(), [
            "tools/call: 4 calls in 3 rows (tool x minute), max 9269 ms (doris___query_metric at 2026-09-27T13:51)",
            "  2026-09-27T13:49  doris___check_service_health           1 calls  avg    5432 ms  max    5432 ms",
            "  2026-09-27T13:51  doris___list_metrics                   2 calls  avg    6100 ms  max    6752 ms",
            "  2026-09-27T13:51  doris___query_metric                   1 calls  avg    9269 ms  max    9269 ms",
            "  [PASS] every minute under 60000 ms",
        ])

    def test_over_the_warning_threshold_is_flagged_but_passes(self):
        rc, out = run(doc(*minute("doris___execute_query", T2, 1, 47000, 47000),
                          *minute("doris___list_tables", T3, 1, 5600, 5600)))
        self.assertEqual(rc, 0, out)
        self.assertIn("  [PASS] every minute under 60000 ms", out)
        self.assertIn("  [WARN] >= 45000 ms (T5.5: lower query_timeout): "
                      "2026-09-27T13:50 doris___execute_query 47000 ms", out)

    def test_reaching_quick_s_limit_fails(self):
        rc, out = run(doc(*minute("doris___execute_query", T2, 1, 60000, 60000)))
        self.assertEqual(rc, 1)
        self.assertIn("  [FAIL] every minute under 60000 ms (1 not: 2026-09-27T13:50 doris___execute_query 60000 ms)",
                      out)

    def test_the_thresholds_are_options(self):
        rc, out = run(doc(*minute("doris___list_tables", T1, 1, 6000, 6000),
                          *minute("doris___query_metric", T2, 1, 9500, 9500)),
                      "--warn-ms", "5000", "--limit-ms", "9000")
        self.assertEqual(rc, 1)
        self.assertIn("  [FAIL] every minute under 9000 ms (1 not: 2026-09-27T13:50 doris___query_metric 9500 ms)", out)
        self.assertIn("  [WARN] >= 5000 ms (T5.5: lower query_timeout): 2026-09-27T13:49 doris___list_tables 6000 ms, "
                      "2026-09-27T13:50 doris___query_metric 9500 ms", out)

    def test_no_datapoints_fails(self):
        rc, out = run(doc(result("calls", "doris___list_tables", {}), result("max", "doris___list_tables", {})))
        self.assertEqual(rc, 1)
        self.assertEqual(out.splitlines(), ["tools/call: 0 calls in 0 rows (tool x minute)",
                                            "  [FAIL] no tools/call datapoints in the window"])

    def test_results_of_other_queries_are_ignored(self):
        rc, out = run(doc(*minute("doris___list_tables", T1, 1, 5600, 5600),
                          result("m_other", "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/x", {T1: 70000})))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("arn:", out)
        self.assertNotIn("70000", out)

    def test_input_that_is_not_get_metric_data_json(self):
        for stdin in ("", "not json", "[]", '{"events": []}', '{"MetricDataResults": 5}'):
            with self.subTest(stdin=stdin):
                rc, out = run(stdin)
                self.assertEqual(rc, 2)
                self.assertEqual(out, "FAIL: input is not get-metric-data JSON (aws cloudwatch get-metric-data "
                                      "--output json)\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2：确认失败**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s scripts/test -p 'test_gw_latency.py' > /tmp/t46-red.log 2>&1; echo "rc=$?"
grep -E '^(FAIL|ERROR):' /tmp/t46-red.log | sed -E 's/ \(.*//'; grep -E '^ModuleNotFoundError|^Ran |^OK|^FAILED' /tmp/t46-red.log
```
期望（实测）：
```
rc=1
ERROR: test_gw_latency
ModuleNotFoundError: No module named 'gw_latency'
Ran 1 test in 0.000s
FAILED (errors=1)
```

- [ ] **Step 3：实现**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p4-extract.py scripts/gw_latency.py
```
期望：`scripts/gw_latency.py -> scripts/gw_latency.py (99 lines)`

<!-- file: scripts/gw_latency.py sha256=164f6fdba57bfbe5ec56228bb666971975d9706b84e2188cae34c97837064b77 -->
```python
#!/usr/bin/env python3
"""Per-minute latency of the Gateway's tools/call, from CloudWatch (P4 / T4.6, P0 review M-3).

Quick calls a Cloud Connector from its own backend, so the Gateway's InvokeGateway Latency is what Quick
waits for on each tool call: the number Quick's 60 s limit applies to.

  q=$(.venv/bin/python scripts/gw_latency.py queries --gateway-arn "$GW_ARN")
  aws cloudwatch get-metric-data --region us-east-1 --start-time "$FROM" --end-time "$TO" \\
      --metric-data-queries "$q" --output json \\
    | .venv/bin/python scripts/gw_latency.py report

Prints tool names, minutes, call counts and milliseconds only: never the ARN.
Exit code: 0 when every minute stays under --limit-ms (--warn-ms only flags), 1 when one does not or there
are no datapoints, 2 when the input is not get-metric-data JSON or --gateway-arn is not a Gateway ARN.
"""

import argparse
import json
import re
import sys

GATEWAY_ARN_RE = re.compile(r"arn:aws:bedrock-agentcore:[a-z0-9-]+:\d{12}:gateway/[A-Za-z0-9-]+")
STATS = (("calls", "SampleCount"), ("avg", "Average"), ("max", "Maximum"))


def queries(gateway_arn: str) -> list[dict]:
    """get-metric-data queries: one SEARCH per statistic over every tool, labelled with the tool name."""
    search = ("{AWS/Bedrock-AgentCore,Method,Name,Operation,Protocol,Resource} MetricName=\"Latency\" "
              f"Operation=\"InvokeGateway\" Method=\"tools/call\" Resource=\"{gateway_arn}\"")
    return [{"Id": id_, "Expression": f"SEARCH('{search}', '{stat}', 60)", "Label": "${PROP('Dim.Name')}"}
            for id_, stat in STATS]


def parse_rows(doc: dict) -> dict[tuple[str, str], dict[str, float]]:
    """{(minute, tool): {"calls": n, "avg": ms, "max": ms}} from the results of queries(); others are skipped."""
    rows: dict[tuple[str, str], dict[str, float]] = {}
    ids = {id_ for id_, _ in STATS}
    for result in doc["MetricDataResults"]:
        if result.get("Id") not in ids:
            continue
        for at, value in zip(result.get("Timestamps") or [], result.get("Values") or []):
            rows.setdefault((str(at)[:16], str(result.get("Label"))), {})[result["Id"]] = float(value)
    return rows


def main(argv: list[str] | None = None, stdin=sys.stdin, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("queries", help="print the --metric-data-queries JSON").add_argument("--gateway-arn", required=True)
    report = sub.add_parser("report", help="summarise get-metric-data JSON from stdin")
    report.add_argument("--warn-ms", type=float, default=45000, help="flag minutes at or above this (T5.5)")
    report.add_argument("--limit-ms", type=float, default=60000, help="fail minutes at or above this (Quick: 60 s)")
    args = parser.parse_args(argv)

    def say(line: str) -> None:
        print(line, file=out)

    if args.command == "queries":
        if not GATEWAY_ARN_RE.fullmatch(args.gateway_arn):
            say("FAIL: --gateway-arn is not a Gateway ARN")
            return 2
        say(json.dumps(queries(args.gateway_arn)))
        return 0

    try:
        doc = json.load(stdin)
        if not isinstance(doc, dict) or not isinstance(doc.get("MetricDataResults"), list):
            raise ValueError
    except ValueError:
        say("FAIL: input is not get-metric-data JSON (aws cloudwatch get-metric-data --output json)")
        return 2

    rows = sorted(parse_rows(doc).items())
    calls = sum(round(stats.get("calls", 0)) for _, stats in rows)
    if not rows:
        say("tools/call: 0 calls in 0 rows (tool x minute)")
        say("  [FAIL] no tools/call datapoints in the window")
        return 1
    (top_minute, top_tool), top = max(rows, key=lambda row: row[1].get("max", 0))
    say(f"tools/call: {calls} calls in {len(rows)} rows (tool x minute), "
        f"max {top.get('max', 0):.0f} ms ({top_tool} at {top_minute})")
    for (minute, tool), stats in rows:
        say(f"  {minute}  {tool:<36} {round(stats.get('calls', 0)):>3} calls  avg {stats.get('avg', 0):>7.0f} ms"
            f"  max {stats.get('max', 0):>7.0f} ms")

    def over(threshold: float) -> list[str]:
        return [f"{minute} {tool} {stats['max']:.0f} ms" for (minute, tool), stats in rows
                if stats.get("max", 0) >= threshold]

    slow = over(args.limit_ms)
    say(f"  [{'FAIL' if slow else 'PASS'}] every minute under {args.limit_ms:.0f} ms"
        + (f" ({len(slow)} not: {', '.join(slow)})" if slow else ""))
    if warned := over(args.warn_ms):
        say(f"  [WARN] >= {args.warn_ms:.0f} ms (T5.5: lower query_timeout): {', '.join(warned)}")
    return 1 if slow else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4：确认通过；突变**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python -m unittest discover -s scripts/test -p 'test_gw_latency.py' 2>&1 | tail -3   # 期望：Ran 10 tests … OK
.venv/bin/python -m unittest discover -s scripts/test 2>&1 | tail -3                          # 期望：Ran 75 tests … OK
.venv/bin/python /tmp/p4-mut.py /tmp/p4-mutations.json t46; echo "rc=$?"
```
突变期望（实测）：
```
m1: caught by test_reaching_quick_s_limit_fails (Ran 10, FAILED (failures=1))
m2: caught by test_results_of_other_queries_are_ignored (Ran 10, FAILED (failures=1))
m3: caught by test_refuses_a_value_that_is_not_a_gateway_arn (Ran 10, FAILED (failures=1))
m4: caught by test_one_line_per_minute_and_tool_in_time_order (Ran 10, FAILED (failures=1))
m5: caught by test_reaching_quick_s_limit_fails, test_the_thresholds_are_options (Ran 10, FAILED (failures=2))
5/5 mutations caught; tree unchanged: True
rc=0
```

- [ ] **Step 5：在线只读核对（T3.4 的窗口）**

T3.4 经 Gateway 的调用在 2026-09-27T13:40Z–14:10Z 之间。CloudWatch 的 1 分钟数据保留 15 天：**2026-10-12 左右之后**这个窗口会是 `0 calls in 0 rows` 加 `[FAIL] no tools/call datapoints`（exit 1），那时跳过本步，改在 Task 4 Step 5 用 P4 自己的窗口核对，并在日志里写明。
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
source infra/state.env
GW_ARN="arn:aws:bedrock-agentcore:us-east-1:${ACCOUNT_ID}:gateway/${GW_ID}"
q=$(.venv/bin/python scripts/gw_latency.py queries --gateway-arn "$GW_ARN")
AWS_PAGER= aws cloudwatch get-metric-data --region us-east-1 --start-time 2026-09-27T13:40:00Z --end-time 2026-09-27T14:10:00Z \
  --metric-data-queries "$q" --output json | .venv/bin/python scripts/gw_latency.py report > /tmp/t46-live.txt; echo "exit=${PIPESTATUS[0]}/${PIPESTATUS[1]}"
sed -n '1p;$p' /tmp/t46-live.txt; grep -c '^  2026' /tmp/t46-live.txt
unset q GW_ARN
```
期望（实测）：
```
exit=0/0
tools/call: 50 calls in 31 rows (tool x minute), max 9269 ms (doris___reload_semantic_layer at 2026-09-27T13:51)
  [PASS] every minute under 60000 ms
31
```
50 是这个窗口里 Gateway 记录的 `tools/call` 数，包括 T3.4 的冒烟、逐次耗时、并发和 DEBUG 泄漏检查里的错误调用，不要和 T3.4 的某一个计数对等。

- [ ] **Step 6：收尾，提交**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - T4.6 <<'EOF'
import pathlib, sys
p = pathlib.Path("specs/doris-mcp-quick/tasks.md"); s = p.read_text(encoding="utf-8")
for tid in sys.argv[1:]:
    old = f"| [ ] | {tid} |"
    assert s.count(old) == 1, old
    s = s.replace(old, f"| [x] | {tid} |")
p.write_text(s, encoding="utf-8"); print("ticked:", *sys.argv[1:])
EOF
echo 'Task 3（T4.6）已完成；Task 4（T4.1 + T4.4）从 Step 1 开始' | .venv/bin/python /tmp/p4-progress.py state 进行中
echo 'Task 4：Step 1 写 `quick/P4-guide.md` → Step 2 整体评审（opus）→ Step 3 预检 → Step 4 交给用户在 Quick 里操作 40–60 分钟 → Step 5–8 核对、判断、收尾。P4 没有 GATE' | .venv/bin/python /tmp/p4-progress.py state 下一步
sed "s/@DATE@/$(date -u +%F)/" <<'EOF' | .venv/bin/python /tmp/p4-progress.py log
### @DATE@ P4 Task 3（T4.6）：`scripts/gw_latency.py`

- 从 CloudWatch 取 Gateway `InvokeGateway` Latency（`Method=tools/call`，按工具名分），按「分钟 × 工具」输出调用数、平均和最大毫秒数；≥ 45000 ms 标 WARN（T5.5 决定是否调低 `query_timeout`），≥ 60000 ms 失败。只输出工具名、时间和毫秒数。
- RED：模块不存在（1 个 ERROR）；GREEN：10 个 OK，`scripts/test` 75 个；突变 m1–m5 5/5 被抓到。
- 在线只读（`cloudwatch get-metric-data`）：T3.4 的窗口 2026-09-27T13:40Z–14:10Z 是 50 calls in 31 rows，最大 9269 ms（`doris___reload_semantic_layer`），PASS。
EOF
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add scripts/gw_latency.py scripts/test/test_gw_latency.py specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
test -n "$v" && git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); unset v   # 期望：0
git commit -q -F - <<'EOF'
feat(p4): T4.6 gw_latency.py Gateway tools/call latency per minute and tool

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline -1   # 期望：工作区干净
```
Step 5 跳过时，日志里的在线一条改成「T3.4 的窗口已过保留期，改在 Task 4 Step 5 核对」。

---

### Task 4：T4.1 + T4.4 Quick 桌面版接入与「开场 + 第 2 幕」（用户一次做完）

来源：tasks.md T4.1、T4.4；design §8.1（工具权限，D7）、§8.3（两个 agent 各只关联自己的连接器，P4 不挂 skills）、§10（「开场 + 第 2 幕」）、§4.5 / §13（scope，M-1）、§4.4 / §13（耗时，M-3）；D9（Local stdio 不做）。

用户侧一次做完：Part A 同步 `doris-mcp` 并设置权限 → Part B 建「Doris 专家」→ Part C 问两个问题 → Part D 对 `doris-mcp-svc` 和「Doris 专家（svc）」再做一遍。AI 侧：写指南、整体评审、预检、交接、事后核对、判断、写结论。

**Files:**
- Create: `quick/P4-guide.md`
- Modify: `specs/doris-mcp-quick/design.md`（v0.7：M-1、M-3 的结论）、`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：Task 1 的 `mcp_smoke.py`（`list --expect 12`、`call`、`conns --prefix doris___ --expect-host-prefix 172.31. --max-idle 610`）、`reconcile.py mcp --url`、`permission_matrix.py --url --expect-host`；Task 2 的 `quick/agent-instructions.md`；Task 3 的 `gw_latency.py queries` / `report`；P3 的 `scripts/audit_check.py`（stdin：`filter-log-events --output json`，输出 `audit: N records (x ok, y failed), 0 unreadable` 和逐工具的行）、`scripts/get-gw-token.sh`。
- Produces：用户的回复（回复模板）；design v0.7；T5.x 需要的实测值（每个问题的总耗时、单次工具调用最长耗时、≥ 45 s 的次数、连接数）。

- [ ] **Step 1：写用户指南**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python /tmp/p4-extract.py quick/P4-guide.md
grep -cE 'https?://|amazonaws|amazoncognito|\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b' quick/P4-guide.md   # 期望：0
```
期望：`quick/P4-guide.md -> quick/P4-guide.md (117 lines)`，然后 `0`。

<!-- file: quick/P4-guide.md sha256=ac8adf39ecd568fbb0ebf9266903993924ed56bfe72671fd4f90f1fa66690f56 -->
````markdown
# P4：Quick 桌面版接入 12 个工具 + 「Doris 专家」agent（T4.1 + T4.4）

> 本文件不包含任何 URL、secret 或 token。连接参数（MCP URL、Token URL、Authorize URL、client ID）见 `quick/T0.7-guide.md` 的「连接参数」。如果 Quick 要求重新填 client secret 或 demo 用户的密码，按 T0.7 的「Step 2：取 secret」在**你自己的终端**里获取，不要用 Claude Code 的 `!` 前缀。

## 注意

- 不要把 URL、secret、token 或登录页的地址粘贴到对话里。登录页地址里有 `state`、`code_challenge` 这类一次性参数，A2 只从中读三项。
- 遇到 424、报错或意料之外的权限弹窗：记下时间、工具名和错误信息原文（先把其中的地址去掉），然后继续往下做。同一个问题最多重试一次。
- 两个连接器、两个 agent 全部做完再回复我，预计 40–60 分钟。

## 准备

- 秒表（手机即可）和记事本。
- 记下这台电脑的时区（回复模板第一行），我按 UTC 对日志。
- Quick 桌面版已登录。

## Part A：同步 `doris-mcp`（User auth），设置工具权限

1. **Customize → Connectors**，打开 `doris-mcp` 的详情页。先看连接设置里有没有 scope 一栏：有就记下填的值，没有这一栏或者是空的就记「无」（A2 的 scope 是不是来自这里，要靠这一项区分）。然后点 **Sync**。
2. 如果弹出登录页，**先不要登录**。看浏览器地址栏，只记三项：
   - `scope=` 的值。`%20` 是空格，`%2F` 是 `/`，例如 `openid%20doris-mcp%2Finvoke` 就是 `openid doris-mcp/invoke`。地址里没有 `scope=` 就记「无」。
   - 有没有 `resource=`：只记「有」或「无」，不抄它的值。
   - `code_challenge_method=` 的值，例如 `S256`。

   记完再用 `demo` 用户登录。如果看不到地址栏（比如是应用内窗口），记「看不到地址」。
   Sync 没有弹出登录页（上次登录的 token 还有效时会这样）：看详情页有没有 Reconnect、Sign in again 这类重新授权的按钮，有就点一次，按上面的方法记三项；没有这类按钮，记「Sync 没有要求登录」，继续往下做。
3. 同步完成后，工具列表应该是 12 个，名字都以 `doris___` 开头，**没有** `doris___net_check`（P3 已经把 P0 的 spike 换成了完整的 server）。记下实际数量。数量不是 12，或者 Sync 失败：停下，把错误信息告诉我。
4. 逐个启用这 12 个工具（新同步的工具默认禁用），权限按下表设置（D7：P4 不是彩排，`execute_query` 用 Ask Each Time；`reload_semantic_layer` 始终 Ask Each Time）：

| 工具 | 权限 |
|---|---|
| `doris___get_query_guide` | Always Allow |
| `doris___check_service_health` | Always Allow |
| `doris___list_databases` | Always Allow |
| `doris___list_tables` | Always Allow |
| `doris___describe_table` | Always Allow |
| `doris___execute_query` | Ask Each Time |
| `doris___list_metrics` | Always Allow |
| `doris___list_dimensions_for_metric` | Always Allow |
| `doris___query_metric` | Always Allow |
| `doris___reload_semantic_layer` | Ask Each Time |
| `doris___list_recent_queries` | Always Allow |
| `doris___get_query_profile` | Always Allow |

## Part B：创建 agent「Doris 专家」

1. 新建一个自定义 agent，名称 `Doris 专家`。
2. 指令：把仓库里 `quick/agent-instructions.md` 的**全文**复制粘贴（约 1900 字符；可以在你自己的终端里 `cat quick/agent-instructions.md` 后复制，这个文件里没有 secret）。
3. 连接器只关联 `doris-mcp`，不挂 skills（skills 在 P5 加）。

## Part C：用「Doris 专家」跑「开场 + 第 2 幕」

新建一个对话，选 agent「Doris 专家」，依次问下面两个问题。每个问题记五项：

- 发送时间（本地时间 hh:mm）；
- 总耗时：按下发送时开始秒表，答案完整显示后停，记秒数；
- Quick 显示的工具调用顺序，例如 `list_metrics → query_metric → query_metric`；
- 权限弹窗：`doris___execute_query` 只在 SQL 是 SELECT、SHOW、DESCRIBE 或 EXPLAIN 时点允许，其他一律拒绝；`doris___reload_semantic_layer` 一律拒绝。记下弹了几次、你怎么选的；
- 424 或其他报错：记原文（去掉其中的地址）。

**问题 1（开场）**：`检查一下 Doris 连接状态`

- 期望：调用 `doris___check_service_health`，回答说明连接正常；不出现主机地址、IP、端口、账号。

**问题 2（第 2 幕）**：`今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比`

- 期望：先 `doris___list_metrics`，再 `doris___query_metric`（按月一次、按渠道一次，也可能合并或多一次）。每次工具调用约 10 s。
- 数字应该和下面的参照值一致（截至 2026-09-25，即演示设定的「今天」；回答里的小数位数可以不同，按它显示的位数对照即可）：

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

- 2026 年 9 月只到 25 日，而去年同期是 2025 年 9 月整月，所以 9 月同比偏低（-0.44%）。回答里应该指出这一点；没指出不算失败，记下即可。
- 合计行的同比和客单价如果回答里没有，不算失败。

## Part D：`doris-mcp-svc`（Service auth）+「Doris 专家（svc）」

1. 打开 `doris-mcp-svc` 的详情页，点 **Sync**（Service auth 不需要登录）。和 A3、A4 一样：确认 12 个 `doris___` 工具，全部启用，权限按同一张表设置。
2. 新建 agent `Doris 专家（svc）`：同样的指令全文；连接器只关联 `doris-mcp-svc`，不挂 skills。每个 agent 只关联一个连接器：两个连接器的工具同名，同时关联会出现重名工具。
3. 新建一个对话，选「Doris 专家（svc）」，按 Part C 把两个问题再问一遍，同样记五项。

## 回复模板

全部做完后，复制下面的模板，填好发给我。不要包含任何 URL、secret 或 token。

```
时区：
A1 连接器设置里的 scope：____（没有或为空记「无」）
A2 登录页：scope=____；resource：有 / 无；code_challenge_method=____（或：Sync 没有要求登录 / 看不到地址）
A3 doris-mcp 工具数：__；D1 doris-mcp-svc 工具数：__
权限：已按表设置（是 / 否，差异：）

「Doris 专家」问题 1：发送 hh:mm，__ s；工具：____；弹窗：__；424 / 报错：
「Doris 专家」问题 2：发送 hh:mm，__ s；工具：____；弹窗：__；424 / 报错：
「Doris 专家（svc）」问题 1：发送 hh:mm，__ s；工具：____；弹窗：__；424 / 报错：
「Doris 专家（svc）」问题 2：发送 hh:mm，__ s；工具：____；弹窗：__；424 / 报错：
其他观察：

答案全文（4 段；其中如有主机地址、IP、端口、账号等连接信息，换成 <已遮盖>）：
```
````

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
echo 'Task 4（T4.1 + T4.4）：Step 1 已提交 `quick/P4-guide.md`；从 Step 2（整体评审）继续' | .venv/bin/python /tmp/p4-progress.py state 进行中
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add quick/P4-guide.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
test -n "$v" && git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); unset v   # 期望：0
git commit -q -F - <<'EOF'
docs(p4): quick/P4-guide.md, the user's steps for T4.1 + T4.4

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git log --oneline -1
```

- [ ] **Step 2：整体评审（opus）**

代码和指南都已完成，在交给用户之前评审整个分支（`main..p4-quick`）：评审发现指令或指南的问题时，不用让用户重做 40–60 分钟。
- 评审包：`git log --oneline main..p4-quick`、`git diff --stat main..p4-quick`、`git diff -U10 main..p4-quick` 写进一个文件，然后 `sed -E -i "$MASK"`（design.md、progress.md 的上下文行里有私网 IP 和 URL），再用 Step 1 提交时的 IP 计数方法对这个文件计数，必须是 `0` 才能交给 reviewer。
- reviewer：一个 Opus 5.5 subagent，用 superpowers:requesting-code-review 的 code-reviewer 模板；给它评审包路径、本计划和 design 的路径、本计划 Review Focus 的全文，以及 progress 里本阶段的 `Ruling:`（如果有）。reviewer 不访问 AWS / Doris，不运行 `APPLY=1`，不读 `credentials.env`。
- Critical / Important：先写能复现问题的测试并确认失败，再修改，确认通过，跑完整测试（「常用测试命令」全部），然后提交 `fix(p4): …`。改了 `quick/agent-instructions.md` 或 `quick/P4-guide.md` 时，Step 4 交给用户的就是改后的版本。
- Minor：不修，记进 progress 的日志（「P4 整体评审（opus）」一条），留给 P5 / T5.5。
- 评审结论和修复写进 progress 日志，按 Task 1 Step 6 的方式提交（check-secrets、IP 计数 0）。

- [ ] **Step 3：预检（只读），记下开始时间**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
source infra/state.env
AWS_PAGER= aws bedrock-agentcore-control get-gateway --region us-east-1 --gateway-identifier "$GW_ID" \
  --query '[status, exceptionLevel, description]' --output text
AWS_PAGER= aws bedrock-agentcore-control get-gateway-target --region us-east-1 --gateway-identifier "$GW_ID" \
  --target-id "$GW_TARGET_ID" --query '[status, lastSynchronizedAt]' --output text
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN --timeout 60 list --expect 12 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
P1='{"workspace":"ecom","metrics":["gmv","order_count","aov","gmv_last_year","gmv_yoy","mini_program_share"],"group_by":["metric_time__month"],"where":"metric_time BETWEEN '"'"'2026-01-01'"'"' AND '"'"'2026-09-25'"'"'"}'
P2='{"workspace":"ecom","metrics":["gmv","order_count"],"group_by":["order_entity__channel"],"where":"metric_time BETWEEN '"'"'2026-01-01'"'"' AND '"'"'2026-09-25'"'"'"}'
for p in "$P1" "$P2"; do
  .venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN --timeout 60 call doris___query_metric "$p" 2>/tmp/p4-ref.err \
    | .venv/bin/python /tmp/p4-rows.py; echo "exit=${PIPESTATUS[0]}/${PIPESTATUS[1]}"; sed -E "$MASK" /tmp/p4-ref.err
done
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN --timeout 60 conns --prefix doris___ --expect-host-prefix 172.31. --max-idle 610 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
unset GW_TOKEN P1 P2
```
期望（实测；毫秒数、`lastSynchronizedAt` 和连接数每次不同）：
```
READY	DEBUG	None
READY	2026-09-27T13:47:18.646791+00:00
connected+initialized in 634 ms
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
total 1550 ms
exit=0
9 rows: metric_time__month gmv order_count aov gmv_last_year gmv_yoy mini_program_share
  2026-01-01  7986117.85  5753  1388.17  5211027.86  0.532541  0.308221
  2026-02-01  4599422.58  2849  1614.40  3986552.32  0.153734  0.333111
  2026-03-01  6391853.90  4526  1412.25  5397104.03  0.184311  0.322586
  2026-04-01  5793467.18  3840  1508.72  4876168.12  0.188118  0.349768
  2026-05-01  8039374.11  5029  1598.60  6164787.89  0.304079  0.315839
  2026-06-01  13657823.71  7821  1746.30  10188029.34  0.340575  0.317359
  2026-07-01  6630639.04  4305  1540.22  5718799.51  0.159445  0.328145
  2026-08-01  6808922.61  4239  1606.26  5742538.20  0.185699  0.327649
  2026-09-01  5754567.17  4633  1242.08  5780111.92  -0.004419  0.320969
exit=0/0
4 rows: order_entity__channel gmv order_count
  APP  28956861.86  19045
  H5  6082330.71  3959
  MINI_PROGRAM  21209275.57  13831
  PC  9413720.01  6160
exit=0/0
connected+initialized in 638 ms
connections: 5 (Query 1, Sleep 4) from 3 distinct hosts; users mcp_svc; max idle 147 s
  [PASS] host prefix 172.31.: 5/5 connections
  [PASS] idle connections <= 610 s: 0 over
total 7537 ms
exit=0
```
`p4-rows.py`（Step 3 用它把 `query_metric` 的结果排成表；浮点数：绝对值小于 10 的保留 6 位，其余保留 2 位）：

<!-- file: p4-rows.py sha256=16851bd894d196f8a72a9a2f2cad4d392e07f64c76bb6ae0af21b117e1f8f7f4 -->
```python
import json, sys
# stdin: mcp_smoke.py call output (query_metric). Prints the rows sorted by the first column, floats rounded.
text = sys.stdin.read()
body = json.loads(text[text.index("{"):text.rindex("}") + 1])
if body.get("success") is not True:
    sys.exit(f"FAIL: {json.dumps(body.get('error'), ensure_ascii=False)[:300]}")
cols, rows = body["data"]["columns"], body["data"]["rows"]
print(f"{len(rows)} rows: {' '.join(cols)}")
for row in sorted(rows, key=lambda r: str(r[cols[0]])):
    print("  " + "  ".join(f"{row[c]:.6f}" if isinstance(row[c], float) and abs(row[c]) < 10
                          else f"{row[c]:.2f}" if isinstance(row[c], float) else str(row[c]) for c in cols))
```

两张表要和 `quick/P4-guide.md` 的参照表一致（指南里是千分位、2 位小数、百分比）。然后对账和权限矩阵（经 Runtime，只读）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
source infra/state.env
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_USER="$DORIS_RO_USER" DORIS_PASSWORD="$DORIS_RO_PASSWORD" AWS_REGION=us-east-1
  unset DORIS_ROOT_USER DORIS_ROOT_PASSWORD DORIS_RO_USER DORIS_RO_PASSWORD DORIS_ADMIN_PASSWORD
  exec .venv/bin/python doris/reconcile.py mcp --url "$RUNTIME_URL" ) 2>&1 | sed -E "$MASK" | tail -1; echo "exit=${PIPESTATUS[0]}"
.venv/bin/python doris/permission_matrix.py --url "$RUNTIME_URL" --expect-host '172.31.%' 2>&1 | sed -E "$MASK" | tail -1; echo "exit=${PIPESTATUS[0]}"
```
期望：`11/11 cases match`、`exit=0`、`5/5 checks pass`、`exit=0`。

任何一项不符合（Gateway 不是 `READY`、target 不是 `READY`、工具不是 12 个、表里的数字和指南不一致、对账不是 11/11、连接数超过 80）：停下来，不交给用户。

最后记下开始时间（毫秒），之后 AI 不再调用 Gateway 或 Runtime，直到用户回复：
```bash
sleep 5; date +%s000 > /tmp/p4-since; sleep 2; date -u -d @$(( $(cat /tmp/p4-since) / 1000 )) +%Y-%m-%dT%H:%M:%SZ
```

- [ ] **Step 4：交给用户，等回复，记下结束时间**

对用户说（中文，不含 URL；指南文件本身也不含 URL 和 secret）：

> P4 的 AI 侧预检都通过了：Gateway 和 target 都是 READY，经 Gateway 能列出 12 个工具，两条参照查询和指南里的表一致，对账 11/11，权限复核 5/5。
> 请按 `quick/P4-guide.md` 在 Quick 桌面版里操作（可以在你自己的终端里 `less quick/P4-guide.md` 查看）：
> - Part A：同步 `doris-mcp`。先打开连接器的编辑页看 scope 一栏，只看不保存，按指南的四种回答之一记下（A1）；弹出登录页时先不要登录，读地址栏的三项（A2）；确认 12 个工具，按表设置权限；
> - Part B：建 agent「Doris 专家」，指令粘贴 `quick/agent-instructions.md` 的全文；
> - Part C：问两个问题，每个问题记五项；
> - Part D：对 `doris-mcp-svc` 和「Doris 专家（svc）」再做一遍。
>
> 全部做完（约 40–60 分钟）后，复制指南最后的回复模板，填好发给我。不要粘贴 URL、secret、token 或登录页的地址。中途有问题可以随时问我。

用户中途提问不算结束，照常回答（不调用 Gateway / Runtime）。收到**填好的回复模板**后，第一件事是记下结束时间，并等 2 分钟让 CloudWatch 的日志和指标到齐：
```bash
date +%s000 > /tmp/p4-until; date -u -d @$(( $(cat /tmp/p4-until) / 1000 )) +%Y-%m-%dT%H:%M:%SZ; sleep 120
```
回复里如果有 URL、token、IP 或账号：不要在输出里复述，写进 progress 时去掉，并提醒用户下次不要粘贴。

`/tmp/p4-since` 或 `/tmp/p4-until` 丢失时：按用户回复里的时区和发送时间重建（UTC，开始取第一个问题之前 5 分钟，结束取最后一个问题之后 5 分钟），例如 `date -u -d '2026-09-28 03:10' +%s000 > /tmp/p4-since`，并在日志里写明是重建的。

- [ ] **Step 5：审计日志、Gateway 耗时、连接数**

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
source infra/state.env
aws logs filter-log-events --region us-east-1 --log-group-name "/aws/bedrock-agentcore/runtimes/${RUNTIME_ID}-DEFAULT" \
  --start-time "$(cat /tmp/p4-since)" --end-time "$(cat /tmp/p4-until)" --filter-pattern '"doris_new_mcp.audit"' --output json \
  | .venv/bin/python scripts/audit_check.py; echo "exit=${PIPESTATUS[1]}"
FROM=$(date -u -d @$(( ($(cat /tmp/p4-since) / 1000 + 59) / 60 * 60 )) +%Y-%m-%dT%H:%M:%SZ)
TO=$(date -u -d @$(( ($(cat /tmp/p4-until) / 1000 + 59) / 60 * 60 )) +%Y-%m-%dT%H:%M:%SZ)
echo "window $FROM .. $TO"
GW_ARN="arn:aws:bedrock-agentcore:us-east-1:${ACCOUNT_ID}:gateway/${GW_ID}"
q=$(.venv/bin/python scripts/gw_latency.py queries --gateway-arn "$GW_ARN")
AWS_PAGER= aws cloudwatch get-metric-data --region us-east-1 --start-time "$FROM" --end-time "$TO" \
  --metric-data-queries "$q" --output json | .venv/bin/python scripts/gw_latency.py report; echo "exit=${PIPESTATUS[1]}"
unset q GW_ARN
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN --timeout 60 conns --prefix doris___ --expect-host-prefix 172.31. --max-idle 610 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
date +%s > /tmp/p4-t0
unset GW_TOKEN
```
期望的形式（数字取决于用户的操作）：
```
audit: N records (N ok, 0 failed), 0 unreadable
  …（逐工具：doris___check_service_health、doris___list_metrics、doris___query_metric 等）
exit=0
window YYYY-MM-DDTHH:MM:00Z .. YYYY-MM-DDTHH:MM:00Z
tools/call: N calls in R rows (tool x minute), max M ms (TOOL at MINUTE)
  …（每分钟、每个工具一行）
  [PASS] every minute under 60000 ms
exit=0
connected+initialized in … ms
connections: C (Query 1, Sleep C-1) from H distinct hosts; users mcp_svc; max idle S s
  [PASS] host prefix 172.31.: C/C connections
  [PASS] idle connections <= 610 s: 0 over
…
exit=0
```
怎么看：
- 审计的 `N` 应该等于 `gw_latency` 的 `calls`。窗口的边界按整分钟取（开始时间向上取整，这样预检的调用不算进来），所以用户如果在开始后的第一分钟内就发出了调用，两边可能差几个。其他原因的差异也只记录、不停下：可能是请求没有执行到 `log_tool_call`（R-32 的缺口），或者出现了 424。
- `max M ms` 和 `[WARN]` 行记进结论（M-3）。`[FAIL]`（≥ 60000 ms）说明有工具调用超过了 Quick 的上限，对照用户记录的 424。
- 连接数 `C` 超过 80（`max_user_connections=100`）：记下来，留给 T5.4 的连接预算，并提醒用户彩排前注意。

- [ ] **Step 6：连接回收（660 s 后）和 CloudTrail**

等到 `p4-t0` 之后 660 s（`wait_timeout` 600 s + 余量；Bash 工具单次最多 10 分钟，所以用下面的循环，可能要跑两次）：
```bash
left=$(( $(cat /tmp/p4-t0) + 660 - $(date +%s) )); [ "$left" -gt 0 ] && sleep "$(( left < 540 ? left : 540 ))"; echo "left $(( $(cat /tmp/p4-t0) + 660 - $(date +%s) )) s"
```
直到输出 `left` 是 0 或负数，然后：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
source infra/state.env
export GW_TOKEN="$(bash scripts/get-gw-token.sh)"
.venv/bin/python scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN --timeout 60 conns --prefix doris___ --expect-host-prefix 172.31. --max-idle 610 2>&1 | sed -E "$MASK"; echo "exit=${PIPESTATUS[0]}"
unset GW_TOKEN
```
期望：`connections: 1 (Query 1) from 1 distinct hosts; users mcp_svc; max idle 0 s`，两个 `[PASS]`，`exit=0`（只剩这次 `SHOW PROCESSLIST` 自己的连接，P-09 在线复核）。

CloudTrail 的事件最多晚 15 分钟才能查到，所以等到 `p4-until` 之后 900 s 再查：
```bash
left=$(( $(cat /tmp/p4-until) / 1000 + 900 - $(date +%s) )); [ "$left" -gt 0 ] && sleep "$(( left < 540 ? left : 540 ))"; echo "left $(( $(cat /tmp/p4-until) / 1000 + 900 - $(date +%s) )) s"
```
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
source infra/state.env
AWS_PAGER= aws cloudtrail lookup-events --region us-east-1 --lookup-attributes AttributeKey=EventName,AttributeValue=Token_POST \
  --start-time "$(date -u -d @$(( $(cat /tmp/p4-since) / 1000 )) +%Y-%m-%dT%H:%M:%SZ)" --output json \
  | CLIENT_A_ID="$CLIENT_A_ID" CLIENT_B_ID="$CLIENT_B_ID" .venv/bin/python /tmp/p4-token-events.py; echo "exit=${PIPESTATUS[1]}"
```
`p4-token-events.py`（只统计本 pool 的 client A / B，只输出选定的字段：不输出来源 IP、code、token 和 resource 的值）：

<!-- file: p4-token-events.py sha256=74657ff80d1bcd81f9afc332257835d3c715b54dcec7e924b2b1473845b982c6 -->
```python
import collections, json, os, sys
# stdin: aws cloudtrail lookup-events --output json (EventName Token_POST). Only client A / B of this pool;
# prints selected fields only: never sourceIPAddress, codes, tokens or the resource URL.
clients = {os.environ["CLIENT_A_ID"]: "A", os.environ["CLIENT_B_ID"]: "B"}
rows = collections.Counter()
for e in json.load(sys.stdin)["Events"]:
    ct = json.loads(e["CloudTrailEvent"])
    extra = ct.get("additionalEventData") or {}
    client = clients.get(extra.get("clientId"))
    if client is None:
        continue
    p = extra.get("requestParameters") or {}
    rows[(ct["eventTime"][:13], client, ",".join(p.get("grant_type") or ["-"]), ",".join(p.get("scope") or ["-"]),
          "resource" in p, (extra.get("responseParameters") or {}).get("status", "-"),
          ct.get("userAgent", "-").split("/")[0])] += 1
print(f"Token_POST (client A / B): {sum(rows.values())}")
for (hour, client, grant, scope, resource, status, ua), n in sorted(rows.items()):
    print(f"  {n:3d}  {hour}h client={client} grant={grant} scope={scope} resource={resource} status={status} ua={ua}")
```

期望的形式：
```
Token_POST (client A / B): N
    n  YYYY-MM-DDTHHh client=A grant=authorization_code scope=… resource=… status=… ua=…
    n  YYYY-MM-DDTHHh client=B grant=client_credentials scope=… resource=… status=… ua=…
exit=0
```
怎么看：`ua=curl` 的 client B 是 AI 自己的 `get-gw-token.sh`，不算。client A 有 `grant=authorization_code` 说明窗口内确实重新登录过（和 A2 对照）；只有 `refresh_token` 或没有 client A，说明没有重新登录，这时 A2 应该是「Sync 没有要求登录」。CloudTrail 看不到 authorize 请求，所以 scope 的结论只来自 A2。

- [ ] **Step 7：判断**

逐项对照用户的回复：

1. **工具数**：A3、D1 都是 12，而且没有 `doris___net_check`。不是 12：停下来，和用户一起看 Sync 的错误（重新同步 target 需要 GATE，不在本计划内）。
2. **数字**：两个 agent 的问题 2，逐月（9 行）、逐渠道（4 行）对照指南的参照表，按回答显示的位数比。有任何一个数不一致：停下来，先经 Gateway 重跑 Step 3 的 P1 / P2，确认是数据、语义层还是 agent 用错了指标，和用户商量；不要为了对上数字去改指令。9 月同比没有说明「只到 25 日」、合计行没有同比或客单价，都不算失败，记下即可。
3. **权限和弹窗**：权限是否按表设置（写进 Step 8 的 `perm`）；弹窗次数和用户的选择。agent 在没有被要求时调用了 `doris___reload_semantic_layer`，或者 `execute_query` 写了非只读 SQL：指令问题，记下来留给 T5.5。
4. **424 和报错**：有的话，对照 Step 5 `gw_latency` 那一分钟的最大耗时。记进结论，留给 T5.5（`query_timeout`）。
5. **连接信息**：答案里出现主机地址、IP、端口或账号（用户已换成 `<已遮盖>`）：违反硬约束 4，指令问题，记下来留给 T5.5。
6. **scope（M-1）**。A2 读的是登录页的地址（Cognito 的 authorize 端点重定向之后的页面），不是 Quick 发出的 authorize 请求本身。下面的判断假定 Cognito 重定向时原样带上请求里的 `scope`、不会自己补上；这一点没有单独验证，所以 design 里写明依据是登录页地址。`ui_scope` 是 A1 的四种回答之一，原样照抄：
   - **a**：A2 的 `scope=` 里有 `doris-mcp/invoke`：Quick 请求了 scope，token 的 scope 不是 Cognito 默认授予的。scope 从哪里来，看 `ui_scope`：
     - 「有 scope 栏，空」或「编辑页里没有 scope 栏」：「Quick 按 Gateway 发布的发现信息（WWW-Authenticate / PRM）请求 scope」**已证实**；
     - 「有 scope 栏，值是 X」或「看不到鉴权设置」：只能说 Quick 请求了 scope，分不清来自连接器设置还是发现信息。
   - **b**：A2 是「无」（登录页地址不带 `scope=`）：Quick 没有请求 scope，token 的 scope 来自 Cognito 默认授予 client A 的全部 scope。功能不受影响。
   - **b′**：A2 有 `scope=`，但里面没有 `doris-mcp/invoke`，而工具调用却成功了：和 Gateway 的 `allowedScopes` 矛盾。**停下来**和用户商量，不写结论。
   - **c**：「Sync 没有要求登录」或「看不到地址」：仍**未证实**，写明原因；T5.3 导入 skills 时如果再次要求登录，按 A2 的方法再看一次。

   `resource=`（登录页地址里有 / 无）和 `code_challenge_method=` 只记录，不影响判断。

1、2 或 6 的 b′ 要停下来的，不做 Step 8。其他问题都记录，进入 Step 8。

- [ ] **Step 8：写结论（design v0.7），收尾，提交**

先把用户回复里的值填进 `V`（`CASE` 按 Step 7 的第 6 项；没有的项留空字符串，脚本会检查当前情况需要的项是否都填了）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
.venv/bin/python - <<'EOF'
import pathlib

CASE = ""  # "a" / "b" / "c"（Step 7 第 6 项）
V = {
    "date": "",      # 用户操作的日期（UTC），例如 2026-09-28
    "scope": "",     # a：A2 的 scope 值（解码后），例如 openid doris-mcp/invoke
    "resource": "",  # a、b：A2 登录页地址里有没有 resource，「有」或「无」
    "method": "",    # a、b：A2 的 code_challenge_method，例如 S256
    "ui_scope": "",  # a、b：A1 的回答原样照抄，四选一：有 scope 栏，值是 X / 有 scope 栏，空 / 编辑页里没有 scope 栏 / 看不到鉴权设置
    "why": "",       # c：原因，例如「Sync 没有要求登录」
    "perm": "",      # 回复里的「权限」：已按表设置写「按 D7」，否则写差异，例如「execute_query 是 Always Allow」
    "q_total": "",   # 每个问题的总耗时，例如「Doris 专家」18 s / 41 s，「Doris 专家（svc）」16 s / 39 s
    "tool_max": "",  # Step 5 gw_latency 的 max（ms），只写数字
    "over45": "",    # Step 5 gw_latency 里 ≥ 45000 ms 的行数，只写数字
    "feel": "",      # 用户「其他观察」的一句话概括（没有就写「无明显问题」）
}
NEED = {"a": ["scope", "resource", "method", "ui_scope"], "b": ["resource", "method", "ui_scope"], "c": ["why"]}
assert CASE in NEED, "CASE must be a, b or c (b' stops at Step 7)"
bad = [k for k in ["date", "perm", "q_total", "tool_max", "over45", "feel"] + NEED[CASE]
       if not V[k].strip() or "…" in V[k] or "____" in V[k]]
assert not bad, f"fill in: {bad}"
assert V["tool_max"].isdigit() and V["over45"].isdigit(), "tool_max / over45: digits only"
UI_EMPTY, UI_UNSEEN, UI_VALUE = ("有 scope 栏，空", "编辑页里没有 scope 栏"), "看不到鉴权设置", "有 scope 栏，值是 "
u = V["ui_scope"].strip()
assert CASE == "c" or u in UI_EMPTY or u == UI_UNSEEN or (u.startswith(UI_VALUE) and u[len(UI_VALUE):].strip()), \
    "ui_scope: one of the four A1 answers, verbatim"

d = V["date"]
FOUND = "Gateway 发布的发现信息（WWW-Authenticate / PRM）"
if CASE == "a":
    if u in UI_EMPTY:
        source = (f"{'连接器鉴权设置里的 scope 栏是空的' if u == UI_EMPTY[0] else '连接器的鉴权设置里没有 scope 栏'}，"
                  f"所以「Quick 按 {FOUND}请求 scope」**已证实**")
    elif u == UI_UNSEEN:
        source = f"看不到连接器的鉴权设置，所以分不清 scope 来自设置还是 {FOUND}"
    else:
        source = f"连接器的鉴权设置里填了 `{u[len(UI_VALUE):].strip()}`，所以分不清 scope 来自设置还是 {FOUND}"
    m1 = (f"登录页地址（authorize 重定向后）带 `scope={V['scope']}`：Quick 请求了 scope，"
          f"token 的 scope 不是 Cognito 默认授予的；{source}")
elif CASE == "b":
    m1 = ("登录页地址（authorize 重定向后）不带 `scope=`：Quick 没有请求 scope，"
          "token 的 scope 来自 Cognito 默认授予 client A 的全部 scope")
else:
    m1 = f"仍**未证实**（{V['why']}）"
params = "" if CASE == "c" else (f"登录页地址里 `resource`：{V['resource']}；`code_challenge_method={V['method']}`。"
                                 "依据是登录页的地址，假定 Cognito 重定向时原样带上 authorize 请求里的 `scope`。")
later = "T5.3 导入 skills 时如果再次要求登录，按 `quick/P4-guide.md` A2 的方法再看一次。" if CASE == "c" else ""
t55 = "T5.5 不必为此调整 `query_timeout`" if V["over45"] == "0" else "T5.5 把 `query_timeout` 调到 40–45 s"
lat = f"每个问题的总耗时 {V['q_total']}；单次工具调用最长 {V['tool_max']} ms，≥ 45 s 的 {V['over45']} 次"
perm = "权限按 D7" if V["perm"].strip() == "按 D7" else f"权限与 D7 不同：{V['perm'].strip()}"

EDITS = [
    ("（Quick 有没有这样做**未证实**，见下面 P0 实测的 scope 一条）",
     f"（Quick 有没有这样做仍**未证实**：{V['why']}，T5.3 再看；见下面 P0 实测的 scope 一条）" if CASE == "c"
     else f"（T4.1 实测，{d}：{m1}；见下面 P0 实测的 scope 一条）"),
    ("    - 结论：**未证实**。T4.1 在 Sync 触发重新授权时，从浏览器里 authorize / login 页面的 URL 读出 `scope`。"
     "只记录三项：scope 的值、有没有 `resource`、`code_challenge_method`，不粘贴 URL。结果是什么都不影响功能。",
     f"    - 结论（T4.1 实测，{d}）：{m1}。{params}{later}结果是什么都不影响功能。"),
    ("但「Quick 按 PRM 请求 scope」**未证实**（v0.6 更正，P0 评审 M-1：请求不带 scope 时 Cognito 会授予 client 的全部 scope），"
     "T4.1 用浏览器 authorize URL 确认。",
     "scope 从哪里来：" + (f"{m1}，T5.3 再看。" if CASE == "c" else f"T4.1 实测，{m1}（P0 评审 M-1 关闭）。")),
    ("端到端耗时没有在 Quick 侧测量（P0 评审 M-3），由 P4 补上：T4.4 用秒表记每个问题的总耗时，"
     "T4.6 的 `scripts/gw_latency.py` 从 Gateway 指标取每次工具调用的耗时。",
     f"✅ Quick 侧耗时（T4.4 / T4.6 实测，{d}，P0 评审 M-3 关闭）：{lat}（秒表 + `scripts/gw_latency.py`）。"),
    ("T4.4 / T4.6 记录 Quick 侧耗时，单次工具调用 ≥ 45 s 的记下来，T5.5 考虑把 `query_timeout` 调到 40–45 s |",
     f"T4.4 / T4.6 实测（{d}）：{lat}；{t55} |"),
    ("T4.4 记录 Quick 侧的体验；明显影响体验时，",
     f"T4.4 实测（{d}）：{lat}；体验：{V['feel']}。明显影响体验时，"),
    ("> 版本：**v0.6** · 2026-09-27 · 状态：P4 进行中（`plans/P4-quick.md`，分支 `p4-quick`）；",
     f"> 版本：**v0.7** · {d} · 状态：P4 已按 `plans/P4-quick.md` 实施完成（T4.1、T4.3–T4.6，分支 `p4-quick`），"
     "整体评审（opus）已完成；"),
    ("\n| v0.6 |",
     f"\n| v0.7 | P4 实测（{d}）：① scope（P0 评审 M-1）：{m1}（§4.5、§13）。② Quick 侧耗时（P0 评审 M-3）：{lat}；"
     f"{t55}（§4.4、§13）。③ `doris-mcp`、`doris-mcp-svc` 两个连接器各 12 个工具，{perm}；两个「Doris 专家」agent 的"
     "「开场 + 第 2 幕」数字与参照值一致 |\n| v0.6 |"),
]
p = pathlib.Path("specs/doris-mcp-quick/design.md")
s = p.read_text(encoding="utf-8")
for old, _ in EDITS:
    assert s.count(old) == 1, f"anchor not found once: {old[:40]}"
for old, new in EDITS:
    s = s.replace(old, new)
p.write_text(s, encoding="utf-8")

t = pathlib.Path("specs/doris-mcp-quick/tasks.md")
s = t.read_text(encoding="utf-8")
for tid in ("T4.1", "T4.4"):
    assert s.count(f"| [ ] | {tid} |") == 1, tid
    s = s.replace(f"| [ ] | {tid} |", f"| [x] | {tid} |")
t.write_text(s, encoding="utf-8")
print(f"design.md: {len(EDITS)} edits (case {CASE}); tasks.md: T4.1, T4.4 ticked")
EOF
```
期望：`design.md: 8 edits (case a|b|c); tasks.md: T4.1, T4.4 ticked`。检查改动（只看新增行，经 MASK）：
```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
git diff -U0 -- specs/doris-mcp-quick/design.md | grep '^+[^+]' | sed -E "$MASK" | cut -c1-300
```

progress：
- 「当前状态」：`阶段` 写「**P4 已完成**（T4.1、T4.3–T4.6，分支 `p4-quick`，整体评审已完成），合并方式和是否推送由用户决定（D8）」加上 `origin/main` 的值；`进行中` 写「无」；`下一步` 写「用户决定 `p4-quick` 的合并方式和是否推送；然后编写 `plans/P5-skills.md`」，并列出留给 P5 的事项（下面的「留给 P5」）。
- 追加日志「### 日期 P4 Task 4（T4.1 + T4.4）：Quick 桌面版接入与「开场 + 第 2 幕」」，记录：
  - 预检结果；开始 / 结束时间（UTC）；
  - 用户回复的要点：A1–A3、D1、权限、4 个问题的耗时、工具顺序和弹窗、424 / 报错、其他观察；答案与参照值的对照结果；
  - 审计记录数和 `gw_latency` 的调用数（以及差异的原因），`max` 和 ≥ 45 s 的次数；
  - 连接数：事后 `C`，660 s 后 1；
  - CloudTrail 的统计（每行的 client、grant、scope、resource、ua 和条数）；
  - scope 的情况（a / b / c）和 design v0.7 的措辞；
  - 留给 P5：Step 7 记下的指令问题；`query_timeout`（T5.5，按 ≥ 45 s 的次数）；连接预算（T5.4 每轮后 `conns`）；Gateway description 和 `exceptionLevel=DEBUG`（T5.5）；是否遮 2003 错误里的 Doris 主机地址（T5.5）；情况 c 时 T5.3 再看 scope；
  - 只读调用清单：sts、`get-gateway` / `get-gateway-target`、Cognito（`get-gw-token.sh`）、Gateway MCP、SigV4 `InvokeAgentRuntime`、`filter-log-events`、`get-metric-data`、`cloudtrail lookup-events`、check-secrets 的 `get-secret-value`；P4 没有 GATE，没有任何写操作。

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
source infra/state.env
bash scripts/check-secrets.sh | tail -1   # 期望：check-secrets: OK (… files scanned)
git add specs/doris-mcp-quick/design.md specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
v="$( { .venv/bin/python -c 'import re; s=open("dorismcp/agentcore/agentcore.json").read(); print("\n".join(sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", s)))))'; printf '%s\n' "$DORIS_PRIVATE_IP" "$DEV_BOX_IP"; } | grep -E '^[0-9.]+$' | sort -u)"
test -n "$v" && git diff --cached -U0 | grep '^+' | grep -cF -f <(printf '%s\n' "$v"); unset v   # 期望：0
git commit -q -F - <<'EOF'
docs(p4): T4.1 + T4.4 Quick connectors and agents, M-1 scope and M-3 latency results; design v0.7

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git status --short; git log --oneline main..p4-quick   # 期望：工作区干净；P4 的提交
```
合并方式和是否推送由用户决定（D8），推送前要再确认一次。

---

## P4 完成标准（对照 design §11 P4 行）

- [ ] 两个连接器同步后都是 12 个 `doris___` 工具，没有 `doris___net_check`；12 个工具都已启用，权限按 D7 的表设置（T4.1；R-10、D7）。
- [ ] 两个 agent 用同一份 `quick/agent-instructions.md`：「Doris 专家」只关联 `doris-mcp`，「Doris 专家（svc）」只关联 `doris-mcp-svc`，都不挂 skills（T4.3、T4.4；design §8.3、D9）。
- [ ] 两条路径都完成了 §10 的「开场 + 第 2 幕」，数字与参照值一致（逐月 9 行、逐渠道 4 行）；参照查询和对账 11/11 在交给用户之前当场复核过（T4.4；R-10、R-13）。
- [ ] 每个问题的总耗时（秒表）和每次工具调用的耗时（`gw_latency.py`）都有记录，没有 424；≥ 45 s 的次数已记录，留给 T5.5（P0 评审 M-3；R-12）。
- [ ] scope 行为有结论，design 已升到 v0.7（P0 评审 M-1）：情况 a / b 写明 scope 的来源；情况 c 写明原因，T5.3 再看。
- [ ] 审计记录数和 Gateway 的调用数已对照，差异已记录（R-32）；事后连接数已记录，660 s 后回到 1（P-09，连接预算）。
- [ ] T4.5：P3 整体评审和 T3.0 / T3.3 / T3.6 的 mask 遗留全部关闭；12 个突变都被测试抓到；手工 FAIL 检查的输出里没有地址和 token（R-43）。
- [ ] 测试全部通过：`doris/test` 161 个、`scripts/test` 75 个、`quick/test` 16 个、`test_agentcore_*.py` 89 个、upstream 离线测试、6 组 shell 测试；T4.3、T4.6 的突变 10 个都被抓到。
- [ ] P4 的提交里没有密码、secret、token、Doris 主机地址、私网 IP 和开发机 IP：每次提交前 `check-secrets` 都是 OK，暂存区新增行的 IP 计数都是 0。
- [ ] 整体评审（opus，Task 4 Step 2）已完成：Critical / Important 都已修复，每个修复都有先红后绿的测试；Minor 记进 progress。
- [ ] 合并方式和是否推送到私有仓库 `lijingfz/Doris-mcp-skill-Demo` 由用户决定（D8），推送前再确认一次。
