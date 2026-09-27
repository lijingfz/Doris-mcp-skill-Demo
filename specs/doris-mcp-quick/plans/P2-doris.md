# P2 Doris 与语义层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务执行本计划。步骤用复选框（`- [ ]`）跟踪。
> **断线恢复：** 先按仓库根目录 `CLAUDE.md` 的恢复协议执行，再从 `progress.md`「当前状态」里写的任务/步骤继续。本计划里所有命令都在仓库根目录 `/home/ubuntu/AI-code/Doris-mcp-skill-Demo` 下运行，除非步骤里明确写了 `cd`。**执行顺序是 T2.1 → T2.4 → T2.5 → T2.2 → T2.3 → T2.6 → T2.7**，不是编号顺序（原因见 Architecture）；本文按执行顺序排列。
> **代码来源：** 本计划中的全部代码和测试已在 spec 阶段于临时目录完成 TDD（117 个 Python 测试 + 4 组 shell 测试全部通过；T2.7 新增的 5 个测试也在临时目录走完 RED → GREEN，agentcore 测试共 82 个），并用 `demo_ro` 对真实 Doris **只读**跑通了 `reconcile.py direct`（11/11 个对账用例到分一致）。4 个 GATE 写操作（建 secret、发布语义层、建账号授权、写探针）在 spec 阶段**都没有执行**，它们的「期望」是按代码推导的。执行时照抄即可；如果某一步的实际输出与「期望」不一致，先停下来查原因，不要改测试去迁就实现。

**Goal:** 为 P3 的 Runtime 备好 Doris 侧的全部前提：Secrets Manager `doris-mcp/mcp_svc`、最小权限服务账号 `mcp_svc`、发布到 `system_mcp` 的 `ecom` 语义层（10 个 YAML、22 个指标），并证明两件事：① `mcp_svc` 的权限恰好是 R-42 列出的那些，所有写操作都被 Doris 拒绝；② 经 MCP server 调用 `query_metric` 的结果与故事线 SQL 逐行到分一致。

**Architecture:**
- **发布走「方案 C」**：`doris/publish_semantic.py` 在本机进程内直接调用 upstream 的 `DorisStore`（staging → commit），用 root 连 Doris 公网 IP；不起 Web UI（upstream 的写接口只认 Doris 角色 `admin`，root 很可能被拒），也**不调用** upstream 的 `commit_staging`（它会执行 `GRANT SELECT_PRIV … TO '%'`）。发布前做离线校验（bootstrap + MetricFlow 引擎初始化 + 重名检查）和物理表校验；发布后回读 active，与本地文件逐字节比对。
- **root 操作都经过 wrapper**（`doris/publish-semantic.sh`、`doris/apply-admin-sql.sh`）：在子 shell 里 `source` credentials.env，只有 `APPLY=1` 时才把 root 密码以新变量名 `DORIS_ADMIN_PASSWORD` export 给 python。`mcp_svc` 的密码从 Secrets Manager 经管道进入 python，只在内存里填进 SQL。
- **顺序**：T2.1 secret → T2.4 模型 + 对账脚本（用 `demo_ro` 只读验证）→ T2.5 root 发布（同时创建 `system_mcp` 和 `ecom` 的元数据行，所以 `mcp_svc` 不需要 LOAD_PRIV）→ T2.2 建 `mcp_svc` → T2.3 权限矩阵（要检查已发布的 `ecom`）→ T2.6 用 `mcp_svc` 经 MCP 对账 → T2.7 P1 / P0 整体评审小修（纯离线，用户 2026-09-26 决定并入本阶段）。

**Tech Stack:** Python 3.12（仓库 `.venv`，P1 已装好）· upstream @f235832 的 `store.store.DorisStore`、`store.bootstrap`、MetricFlow 编译器 · pymysql · P1 的 `agentcore_ext.settings` / `agentcore_ext.app` · AWS CLI v2（Secrets Manager）· bash · unittest

**Spec:** `specs/doris-mcp-quick/requirements.md`（R-21、R-26、R-31、R-35、R-42、R-43；D1、D6）、`specs/doris-mcp-quick/design.md`（§4.2、§6.1、§6.3、§11 P2 行、§14）

## Global Constraints

- 只用 us-east-1、账号 `890717383483`（环境变量里的凭证）；不要用 AWS profile `lijingfz`。本机环境的 `AWS_DEFAULT_REGION` 是 us-west-2，所以访问 Secrets Manager 的命令都要显式指定 `--region us-east-1` 或 `AWS_REGION=us-east-1`。
- **GATE**（CLAUDE.md）：本计划有 4 个 GATE —— T2.1 建 secret、T2.5 以 root 发布语义层、T2.2 以 root 建 `mcp_svc` 并授权、T2.3 以 `mcp_svc` 跑写探针。每个 GATE 都先展示 dry-run 输出，用户明确确认后才用 `APPLY=1` 执行；一次确认只对应那一次操作。
- 密码和 secret 不出现在仓库、命令行参数、日志、输出和对话里；**Doris 主机地址也不出现在输出里**（所有脚本都把它 mask 成 `***`）。Doris 凭证只从 `/home/ubuntu/AI-code/Doris-test/credentials.env` 在**子 shell** 里 `source`（该文件没有 `export` 行，source 后变量不会自动传给子进程），只 export 需要的变量；**永远不要 echo 或 cat 这个文件**。`DORIS_ROOT_*` 从不以原名传给任何进程。
- `demo_ro` 只做 SELECT / SHOW / DESCRIBE。**不要用 `demo_ro` 试探写操作**：spec 阶段自动模式已经拒绝过这类命令，不要以任何方式重试。写探针只在 T2.3 的 GATE 之后以 `mcp_svc` 执行。
- root 只执行两类写操作：T2.5 的语义层发布（`system_mcp` 库、3 张表、元数据行、staging/active 行），以及 T2.2 的 `doris/01_mcp_user.sql`（4 条语句）。不执行 upstream 的 `commit_staging`、`grant_select_on_physical_tables`、`grant_workspace_access`。MCP 本身不执行 DDL/DML。
- `mcp_svc` 的权限 = R-42：「只有 `SELECT_PRIV ON internal.ecom.*` 和 `SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.*`，没有 ADMIN/LOAD/ALTER/DROP」。另外 Doris 给每个用户默认列出 `internal.information_schema`、`internal.mysql` 的 `Select_priv` 和 workload group `normal` 的 `Usage_priv`（requirements v1.3 的 R-42 验收已接受这几项）。host 先用 `'%'`（D6），P3 T3.5 收紧为 `'172.31.%'`。
- 不修改 `mcp-server/`（P1 已完成；唯一例外是 T2.7 的 P1 整体评审小修，用户 2026-09-26 决定并入本阶段）和 `prepare/`。
- 测试用 unittest，命令是 `.venv/bin/python -m unittest discover -s doris/test`（**不要**加 `-t .`，会导入失败）。shell 测试用假的 `aws` / `python`，不访问 AWS 或 Doris。
- 代码、注释、脚本输出用英文；计划和 progress 用中文。
- 每个任务结束：勾选 `tasks.md` → 更新 `progress.md`（「当前状态」+ 追加日志）→ `bash scripts/check-secrets.sh` → commit（message 结尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`）。全部在分支 `p2-doris` 上，不 push。

## Review Focus

1. **密码和 Doris 主机地址泄漏**：root 密码、`mcp_svc` 密码、Doris 公网 IP 可能经由 pymysql 异常消息（`Can't connect to MySQL server on '<host>'`）、dry-run 打印的 SQL、命令行参数、临时文件泄漏。→ T2.1 test-40 的 `apply/missing: password never in argv`、`password never in output`、`temp file removed`，以及 check-secrets 块 1b（`leaked Secrets Manager password fails the check`）；T2.4 `test_connect_error_is_masked`；T2.5 `test_database_errors_are_masked` 和 wrapper 的 `dry-run: admin password NOT exported`、`e2e dry-run: no secret or host in output`；T2.2 `test_connect_errors_hide_the_host_and_both_passwords`。
2. **写探针本身造成写入**：权限矩阵要证明写操作被拒，但如果某条权限多给了，探针就会真的执行。→ T2.3 `test_every_write_probe_is_a_no_op_if_it_were_allowed`（每个探针都是 0 行 / 不存在的行 / `IF EXISTS` 不存在的表 / `IF NOT EXISTS` 已存在的库 / 已有的授权 / 只读 ADMIN 命令），`test_runs_only_read_only_statements_and_lists_the_probes`（dry-run 只执行 SELECT/SHOW）。
3. **通过校验但上线后会坏的模型**：upstream 的 `validate` 不初始化 MetricFlow 引擎，缺 `agg_time_dimension`、重复的 measure 名都能 commit 上去；push 会悄悄跳过文件；版本号不变时 MCP 侧不会 reload。→ T2.5 `test_engine_init_failure_is_rejected`、`test_duplicate_measure_is_rejected`、`test_merged_staging_must_equal_the_local_models`、`test_semantic_version_must_advance`、`test_never_runs_upstream_grant_or_commit_hooks`。
4. **看起来对、其实错的数字**：订单级 GMV 含运费、明细级不含；明细类指标要过滤已支付订单，退款率（故事 5.1）不过滤；同比需要 time spine 覆盖到结束日期；`<` 会被编译成 `<=`。→ T2.4 `test_item_level_gmv_is_paid_filtered`、`test_refund_rate_follows_story_5_1`、`test_offset_metric_cases_have_an_end_date`、`test_money_must_match_to_the_cent`；T2.4 Step 9 和 T2.6 Step 1 对真实 Doris 逐行比对。
5. **`mcp_svc` 权限多了或少了**：多了违反 R-42；少了会让 Runtime 上的 upstream store 初始化失败（CREATE IF NOT EXISTS）或缺元数据行时尝试 INSERT。→ T2.3 `test_extra_scopes_and_roles_are_reported`、`test_demo_ro_lacks_system_mcp`、`test_a_cached_success_cannot_hide_a_failure`、`test_missing_metadata_row_fails_with_a_hint`；T2.2 `test_statement_outside_the_allowlist_is_rejected`、`test_statements_are_exactly_the_r42_account_setup`。

---

## 文件地图

| 文件 | 状态 | 任务 | 作用 |
|---|---|---|---|
| `infra/40-doris-secret.sh` | 新建 | T2.1 | 创建 secret `doris-mcp/mcp_svc`（Secrets Manager 生成 32 位字母数字密码）；已存在时不改动；ARN 写入 `state.env` |
| `infra/test/test-40-doris-secret.sh` | 新建 | T2.1 | 离线测试（假 `aws`）：23 项检查 |
| `scripts/check-secrets.sh` | 修改 | T2.1 | 新增块 1b：Secrets Manager 里的密码精确值扫描 |
| `scripts/test/test-check-secrets.sh` | 新建 | T2.1 | 块 1b 的离线测试（假 `aws`）：10 项检查 |
| `infra/state.env` | 修改 | T2.1 | `DORIS_SECRET_ARN`（由脚本在 APPLY=1 时写入）|
| `doris/semantic/ecom/*.yaml` | 新建 | T2.4 | 10 个文件：project（time spine `dim_date`）、6 个维度模型、4 个事实模型、metrics；共 22 个指标 |
| `doris/test/test_semantic_models.py` | 新建 | T2.4 | 模型离线测试（bootstrap、引擎、编译出的 SQL）：12 个测试 |
| `doris/reconcile.py` | 新建 | T2.4、T2.6 | 对账：`direct`（编译本地 YAML，pymysql 执行）/ `mcp`（进程内 MCP server）× 11 个故事线用例 |
| `doris/test/test_reconcile.py` | 新建 | T2.4 | 29 个测试 |
| `doris/publish_semantic.py` | 新建 | T2.5 | 方案 C 发布：离线校验 → 物理表校验 → staging → commit → 回读比对 |
| `doris/test/test_publish_semantic.py` | 新建 | T2.5 | 25 个测试（假 store 按 upstream staging 语义实现）|
| `doris/publish-semantic.sh`、`doris/test/test-publish-semantic.sh` | 新建 | T2.5 | root wrapper + 12 项离线检查 |
| `doris/admin_sql.py` | 新建 | T2.2 | 以 root 执行账号 SQL：白名单、密码只在内存里填入、输出 mask |
| `doris/01_mcp_user.sql` | 新建 | T2.2 | `mcp_svc` 的 4 条语句（design §6.1），只含占位符 |
| `doris/test/test_admin_sql.py`、`test_mcp_user_sql.py` | 新建 | T2.2 | 11 + 1 个测试 |
| `doris/apply-admin-sql.sh`、`doris/test/test-apply-admin-sql.sh` | 新建 | T2.2 | root wrapper（secret 经管道传入）+ 14 项离线检查 |
| `doris/permission_matrix.py`、`doris/test/test_permission_matrix.py` | 新建 | T2.3 | `mcp_svc` 权限矩阵：4 项只读检查 + store_init + 9 个写探针；39 个测试 |
| `mcp-server/src/tools/profile.py`、`mcp-server/src/agentcore_ext/settings.py`、`app.py` 及对应的 `test_agentcore_{profile,settings,app}.py` | 修改 | T2.7 | P1 整体评审 ①–④：profile 文本 mask、secret 读取错误不链接原异常、`build_server` 失败时 exit 2、端口测试；新增 5 个测试（77 → 82）|
| `quick/T0.7-guide.md`、`.gitignore` | 修改 | T2.7 | P0 整体评审 M-2（取 secret 的命令改成单行）、M-8（CodeZip staging 注释）|

常用测试命令：

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3   # 本阶段全部 Python 测试（最终 117 个）
for t in infra/test/test-40-doris-secret.sh scripts/test/test-check-secrets.sh \
         doris/test/test-publish-semantic.sh doris/test/test-apply-admin-sql.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                 # 4 组 shell 测试，每组最后一行 all passed
```

---

### Task T2.1：Secrets Manager `doris-mcp/mcp_svc` + check-secrets 精确值扫描

**Files:**
- Create：`infra/40-doris-secret.sh`、`infra/test/test-40-doris-secret.sh`、`scripts/test/test-check-secrets.sh`
- Modify：`scripts/check-secrets.sh`（在块 1 和块 2 之间插入块 1b）、`infra/state.env`（APPLY=1 时由脚本写入）、`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：P0 的 `infra/lib.sh`：`log`（写 stderr）、`run`（dry-run 时只打印）、`state_set KEY VALUE`（只在 APPLY=1 时写 `STATE_FILE`）、`private_tmp` → `$PRIVATE_TMP`（0600，EXIT 时删除）、`$APPLY`、`$PROJECT_TAG`、`AWS_REGION`（默认 us-east-1）
- Produces：us-east-1 的 secret `doris-mcp/mcp_svc` = `{"username":"mcp_svc","password":<32 位字母数字>}`；`infra/state.env` 的 `DORIS_SECRET_ARN`；`scripts/check-secrets.sh` 块 1b 读取 `SM_SECRETS`（默认 `doris-mcp/mcp_svc doris-mcp/cognito-demo-user`）的 `password` 字段，在所有待提交文件里查找（区域 `SM_REGION`，默认 us-east-1）。T2.2 的 `doris/apply-admin-sql.sh`、T2.3 / T2.6 的 `DORIS_SECRET_ID=doris-mcp/mcp_svc`、P3 的 Runtime 都读这个 secret。

- [ ] **Step 1：确认前置条件，建分支，提交计划**

```bash
git branch --show-current     # 期望：main
git status --short
```
期望：恰好 5 行 —— `?? specs/doris-mcp-quick/plans/P2-doris.md`，以及 `specs/doris-mcp-quick/` 下 ` M` 的 `design.md`、`progress.md`、`requirements.md`、`tasks.md`（这是用户 review 过的计划和 spec 修订）。如果还有其他改动，先停下来问用户。

```bash
aws sts get-caller-identity --query Account --output text              # 期望：890717383483
.venv/bin/python --version                                             # 期望：Python 3.12.x
test -r /home/ubuntu/AI-code/Doris-test/credentials.env && echo "credentials.env readable"
bash scripts/check-secrets.sh | tail -1                                # 期望：check-secrets: OK (… files scanned)
git switch -c p2-doris
git add specs/doris-mcp-quick/plans/P2-doris.md specs/doris-mcp-quick/{design,progress,requirements,tasks}.md
git commit -m "docs(p2): P2 plan (Doris and semantic layer); design v0.4, requirements v1.3

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2：写失败测试 `infra/test/test-40-doris-secret.sh`**

假的 `aws` 放在 PATH 最前面，记录每一次调用；四种情况：secret 不存在 / 已存在 / 已计划删除 / describe 无权限。

```bash
#!/usr/bin/env bash
# Offline tests for infra/40-doris-secret.sh. A fake `aws` on PATH records every call; no AWS access.
#   bash infra/test/test-40-doris-secret.sh
set -uo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAKE_PW="FakePw0123456789abcdefXYZ"
mkdir -p "$TMP/bin"
# Fake AWS CLI. FAKE_SECRET = missing | exists | deleted | denied.
cat > "$TMP/bin/aws" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
case "$1 $2" in
  "secretsmanager describe-secret")
    case "$FAKE_SECRET" in
      exists)  printf 'arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-AbCdEf\tNone\n' ;;
      deleted) printf 'arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-AbCdEf\t2026-09-20T00:00:00+00:00\n' ;;
      denied)  echo "An error occurred (AccessDeniedException) when calling the DescribeSecret operation" >&2; exit 254 ;;
      *)       echo "An error occurred (ResourceNotFoundException) when calling the DescribeSecret operation: Secrets Manager can't find the specified secret." >&2; exit 254 ;;
    esac ;;
  "secretsmanager get-random-password") echo "$FAKE_PW" ;;
  "secretsmanager create-secret")
    for a in "$@"; do [[ "$a" == file://* ]] && { cat "${a#file://}" > "$FAKE_CAPTURE"; echo "${a#file://}" > "$FAKE_CAPTURE.path"; }; done
    echo "arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-NeW123" ;;
  *) echo "fake aws: unexpected call: $*" >&2; exit 99 ;;
esac
FAKE
chmod +x "$TMP/bin/aws"

FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
# run_script FAKE_SECRET APPLY — runs the script against a fresh copy of state.env; sets RC, OUT, LOG.
run_script() {
  : > "$TMP/aws.log"; rm -f "$TMP/capture" "$TMP/capture.path"
  printf '%s\n' '# test state' 'AWS_REGION=us-east-1' 'ACCOUNT_ID=111122223333' > "$TMP/state.env"
  OUT="$(PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" FAKE_CAPTURE="$TMP/capture" FAKE_PW="$FAKE_PW" \
    FAKE_SECRET="$1" APPLY="$2" STATE_FILE="$TMP/state.env" bash "$INFRA_DIR/40-doris-secret.sh" 2>&1)"
  RC=$?
  LOG="$(cat "$TMP/aws.log")"
}
has() { [[ "$1" == *"$2"* ]] && echo yes || echo no; }

run_script missing 0
check "dry-run: exit 0" 0 "$RC"
check "dry-run: shows the create-secret command" yes "$(has "$OUT" "DRY-RUN: aws secretsmanager create-secret")"
check "dry-run: never creates the secret" no "$(has "$LOG" "create-secret")"
check "dry-run: never generates a password" no "$(has "$LOG" "get-random-password")"
check "dry-run: state.env unchanged" no "$(has "$(cat "$TMP/state.env")" "DORIS_SECRET_ARN")"

run_script missing 1
check "apply/missing: exit 0" 0 "$RC"
check "apply/missing: create-secret called once" 1 "$(grep -c 'create-secret' <<<"$LOG")"
check "apply/missing: secret passed as file://" yes "$(has "$LOG" "--secret-string file://")"
check "apply/missing: tagged with Project" yes "$(has "$LOG" "Key=Project,Value=doris-mcp-demo")"
check "apply/missing: secret JSON is {username: mcp_svc, password: generated}" "mcp_svc|$FAKE_PW" \
  "$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["username"] + "|" + d["password"])' "$TMP/capture" 2>&1)"
check "apply/missing: password never in argv" no "$(has "$LOG" "$FAKE_PW")"
check "apply/missing: password never in output" no "$(has "$OUT" "$FAKE_PW")"
check "apply/missing: temp file removed" no "$([[ -e "$(cat "$TMP/capture.path" 2>/dev/null)" ]] && echo yes || echo no)"
check "apply/missing: ARN recorded in state.env" \
  "DORIS_SECRET_ARN=arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-NeW123" \
  "$(grep '^DORIS_SECRET_ARN=' "$TMP/state.env")"

run_script exists 1
check "apply/exists: exit 0" 0 "$RC"
check "apply/exists: secret left unchanged (no create)" no "$(has "$LOG" "create-secret")"
check "apply/exists: no new password generated" no "$(has "$LOG" "get-random-password")"
check "apply/exists: ARN recorded in state.env" \
  "DORIS_SECRET_ARN=arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-AbCdEf" \
  "$(grep '^DORIS_SECRET_ARN=' "$TMP/state.env")"

run_script deleted 1
check "apply/pending-deletion: fails" 1 "$RC"
check "apply/pending-deletion: tells the operator to restore" yes "$(has "$OUT" "restore-secret")"
check "apply/pending-deletion: no create" no "$(has "$LOG" "create-secret")"

run_script denied 1
check "apply/describe-denied: fails instead of creating" 1 "$RC"
check "apply/describe-denied: no create" no "$(has "$LOG" "create-secret")"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
```

- [ ] **Step 3：运行测试，确认失败**

```bash
bash infra/test/test-40-doris-secret.sh 2>&1 | grep -E '^FAIL|failed$' | tail -3
```
期望：`FAIL … expected '0', got '127'` 这类行（127 = 脚本还不存在），最后一行 `13 failed`。

- [ ] **Step 4：写 `infra/40-doris-secret.sh`**

```bash
#!/usr/bin/env bash
# P2 / T2.1 — Secrets Manager secret for the Doris service account.
#   doris-mcp/mcp_svc = {"username":"mcp_svc","password":<get-random-password, 32 alphanumerics>}
# The password is generated by Secrets Manager into a 0600 temp file; it is never printed or passed
# as a command-line argument. An existing secret is left untouched (re-run safe): doris/apply-admin-sql.sh
# always sets mcp_svc's Doris password from whatever the secret holds.
# Dry-run by default. APPLY=1 to execute.
source "$(dirname "$0")/lib.sh"

SECRET_NAME=doris-mcp/mcp_svc
SVC_USER=mcp_svc

# describe-secret: distinguish "not found" from every other failure, so a missing permission or an
# expired session never falls through to create-secret.
ARN="" DELETED=""
if out="$(aws secretsmanager describe-secret --secret-id "$SECRET_NAME" \
            --query '[ARN, DeletedDate]' --output text 2>&1)"; then
  read -r ARN DELETED <<<"$out"
elif [[ "$out" != *ResourceNotFoundException* ]]; then
  log "FATAL: describe-secret $SECRET_NAME failed: $out"; exit 1
fi

if [[ -n "$DELETED" && "$DELETED" != "None" ]]; then
  log "FATAL: $SECRET_NAME is scheduled for deletion ($DELETED)."
  log "       Restore it first (GATE): aws secretsmanager restore-secret --secret-id $SECRET_NAME"
  exit 1
elif [[ -n "$ARN" ]]; then
  log "secret exists: $SECRET_NAME (left unchanged)"
elif [[ "$APPLY" != "1" ]]; then
  log "DRY-RUN: get-random-password --password-length 32 --exclude-punctuation --require-each-included-type"
  run aws secretsmanager create-secret --name "$SECRET_NAME" --tags "Key=Project,Value=$PROJECT_TAG" \
    --description "Doris service account for the doris-mcp Runtime" \
    --secret-string "file://<0600 temp file: {\"username\":\"$SVC_USER\",\"password\":<generated>}>"
else
  private_tmp
  pw="$(aws secretsmanager get-random-password --password-length 32 --exclude-punctuation \
    --require-each-included-type --query RandomPassword --output text)"
  printf '{"username":"%s","password":"%s"}' "$SVC_USER" "$pw" > "$PRIVATE_TMP"
  unset pw
  ARN="$(aws secretsmanager create-secret --name "$SECRET_NAME" --tags "Key=Project,Value=$PROJECT_TAG" \
    --description "Doris service account for the doris-mcp Runtime" \
    --secret-string "file://$PRIVATE_TMP" --query ARN --output text)"
  rm -f "$PRIVATE_TMP"
  log "secret $SECRET_NAME created"
fi

[[ -n "$ARN" ]] && state_set DORIS_SECRET_ARN "$ARN"
log "done (APPLY=$APPLY)"
```

- [ ] **Step 5：运行测试，确认通过**

```bash
bash infra/test/test-40-doris-secret.sh 2>&1 | tail -1   # 期望：all passed（23 项）
bash infra/test/test-lib.sh 2>&1 | tail -1                # 期望：all passed（P0 的 lib.sh 测试不受影响）
```

- [ ] **Step 6：写失败测试 `scripts/test/test-check-secrets.sh`**

在临时 git 仓库里跑真实的 `scripts/check-secrets.sh`；假的 `aws` 返回一个 secret，其密码被写进一个待提交文件。测试时故意把 `AWS_REGION` 设成别的区域，确认块 1b 固定读 us-east-1。

```bash
#!/usr/bin/env bash
# Offline tests for the Secrets Manager part of scripts/check-secrets.sh. Runs the script inside a
# throwaway git repo with a fake `aws` on PATH; no AWS access, the real credentials file is not read.
#   bash scripts/test/test-check-secrets.sh
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/check-secrets.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAKE_PW="SmPw0123456789abcdefXYZ"
mkdir -p "$TMP/bin" "$TMP/repo/scripts"
cat > "$TMP/bin/aws" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
if [[ "$1 $2" == "secretsmanager get-secret-value" && "$FAKE_SM" == "readable" && "$*" == *doris-mcp/mcp_svc* ]]; then
  printf '{"username":"mcp_svc","password":"%s"}\n' "$FAKE_PW"; exit 0
fi
echo "An error occurred (ResourceNotFoundException) when calling the GetSecretValue operation" >&2; exit 254
FAKE
chmod +x "$TMP/bin/aws"
cp "$SRC" "$TMP/repo/scripts/check-secrets.sh"
git -C "$TMP/repo" init -q
echo "hello" > "$TMP/repo/clean.txt"

FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
run_check() { # FAKE_SM → sets RC, OUT
  : > "$TMP/aws.log"
  # AWS_REGION points elsewhere, like a shell whose default profile is in another region.
  OUT="$(cd "$TMP/repo" && PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" FAKE_PW="$FAKE_PW" FAKE_SM="$1" \
    AWS_REGION=eu-west-1 AWS_DEFAULT_REGION=eu-west-1 CRED_FILE="$TMP/no-such-file" bash scripts/check-secrets.sh 2>&1)"
  RC=$?
}
has() { [[ "$1" == *"$2"* ]] && echo yes || echo no; }

run_check readable
check "clean repo passes" 0 "$RC"
check "reads doris-mcp/mcp_svc" yes "$(has "$(cat "$TMP/aws.log")" "--secret-id doris-mcp/mcp_svc")"
check "reads doris-mcp/cognito-demo-user" yes "$(has "$(cat "$TMP/aws.log")" "--secret-id doris-mcp/cognito-demo-user")"
check "reads the secrets in us-east-1 whatever AWS_REGION says" 2 "$(grep -c -- '--region us-east-1' "$TMP/aws.log")"

printf 'debug: pw=%s\n' "$FAKE_PW" > "$TMP/repo/leaky.log.txt"
run_check readable
check "leaked Secrets Manager password fails the check" 1 "$RC"
check "names the secret and the file" yes "$(has "$OUT" "LEAK: password of secret doris-mcp/mcp_svc found in leaky.log.txt")"
check "never prints the password" no "$(has "$OUT" "$FAKE_PW")"
check "password never in any aws argv" no "$(has "$(cat "$TMP/aws.log")" "$FAKE_PW")"

run_check unreadable
check "unreadable secrets are skipped with a warning, not a failure" 0 "$RC"
check "warning names the secret" yes "$(has "$OUT" "WARN: cannot read secret doris-mcp/mcp_svc")"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
```

- [ ] **Step 7：运行测试，确认失败**

```bash
bash scripts/test/test-check-secrets.sh 2>&1 | grep -E '^FAIL|failed$'
```
期望：6 行 `FAIL`（`reads doris-mcp/mcp_svc`、`reads doris-mcp/cognito-demo-user`、`reads the secrets in us-east-1 whatever AWS_REGION says`、`leaked Secrets Manager password fails the check`、`names the secret and the file`、`warning names the secret`），最后一行 `6 failed`。

- [ ] **Step 8：在 `scripts/check-secrets.sh` 里插入块 1b**

插在 `# 2) Generic patterns: …` 这一行**之前**，后面空一行。密码只保存在 shell 变量里，经进程替换交给 grep，不进 argv、不打印。

```bash
# 1b) Passwords held only in Secrets Manager (created by infra/*.sh, always in us-east-1). The value
#     stays in a shell variable and reaches grep through a process substitution — never argv, never printed.
for sid in ${SM_SECRETS:-doris-mcp/mcp_svc doris-mcp/cognito-demo-user}; do
  if ! pw="$(aws secretsmanager get-secret-value --region "${SM_REGION:-us-east-1}" --secret-id "$sid" \
               --query SecretString --output text 2>/dev/null |
             python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])' 2>/dev/null)" || [[ ${#pw} -lt 4 ]]; then
    echo "WARN: cannot read secret $sid — skipped its exact-value check"
    continue
  fi
  while IFS= read -r f; do
    echo "LEAK: password of secret $sid found in $f"
    fail=1
  done < <(grep -lIF -f <(printf '%s\n' "$pw") -- "${files[@]}" 2>/dev/null)
done
unset pw
```

```bash
git diff --stat scripts/check-secrets.sh   # 期望：1 file changed, 16 insertions(+)
```

- [ ] **Step 9：运行测试，确认通过；扫描仓库**

```bash
bash scripts/test/test-check-secrets.sh 2>&1 | tail -1   # 期望：all passed（10 项）
bash scripts/check-secrets.sh
```
期望：`WARN: cannot read secret doris-mcp/mcp_svc — skipped its exact-value check`（secret 还没建；`doris-mcp/cognito-demo-user` 是 P0 建的，能读到，所以没有 WARN），最后一行 `check-secrets: OK (… files scanned)`。

- [ ] **Step 10：dry-run**

```bash
bash infra/40-doris-secret.sh
git diff --stat infra/state.env   # 期望：无输出
```
期望（时间戳不同）：
```
[..] APPLY=0 region=us-east-1 state=/home/ubuntu/AI-code/Doris-mcp-skill-Demo/infra/state.env
[..] DRY-RUN: get-random-password --password-length 32 --exclude-punctuation --require-each-included-type
DRY-RUN: aws secretsmanager create-secret --name doris-mcp/mcp_svc --tags Key=Project\,Value=doris-mcp-demo --description Doris\ service\ account\ for\ the\ doris-mcp\ Runtime --secret-string file://\<0600\ temp\ file:\ \{\"username\":\"mcp_svc\"\,\"password\":\<generated\>\}\>
[..] done (APPLY=0)
```

- [ ] **Step 11：GATE —— 展示并等待确认**

向用户展示 Step 10 的输出，并说明：
- 将在 us-east-1 创建 1 个 secret `doris-mcp/mcp_svc`（tag `Project=doris-mcp-demo`，约 $0.40/月）；
- 密码由 Secrets Manager 生成，不显示，只经过一个 0600 临时文件（用完立即删除），不进命令行参数；
- 回滚（也需要 GATE）：`aws secretsmanager delete-secret --region us-east-1 --secret-id doris-mcp/mcp_svc --recovery-window-in-days 7`。

用户明确确认后执行：
```bash
APPLY=1 bash infra/40-doris-secret.sh
```
期望：`secret doris-mcp/mcp_svc created`、`state: DORIS_SECRET_ARN=arn:aws:secretsmanager:us-east-1:890717383483:secret:doris-mcp/mcp_svc-XXXXXX`（XXXXXX 是随机后缀）、`done (APPLY=1)`。

- [ ] **Step 12：验证（只读）**

```bash
aws secretsmanager get-secret-value --region us-east-1 --secret-id doris-mcp/mcp_svc --query SecretString --output text |
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["username"], len(d["password"]), d["password"].isalnum())'
grep '^DORIS_SECRET_ARN=' infra/state.env
bash infra/40-doris-secret.sh 2>&1 | grep -E 'exists|done'
bash scripts/check-secrets.sh
```
期望：`mcp_svc 32 True`（只打印用户名、长度和是否全是字母数字，不打印密码）；state.env 里有 `DORIS_SECRET_ARN=arn:aws:secretsmanager:us-east-1:890717383483:secret:doris-mcp/mcp_svc-……`；重跑脚本输出 `secret exists: doris-mcp/mcp_svc (left unchanged)` 和 `done (APPLY=0)`；check-secrets 不再有 WARN，最后一行 `check-secrets: OK (…)`。

- [ ] **Step 13：收尾**

勾选 T2.1；progress「当前状态」写 T2.1 完成、下一步 T2.4，「已创建的 AWS 资源」加上 Secrets Manager `doris-mcp/mcp_svc`；日志记录 ARN 后缀和 Step 12 的结果。

```bash
bash scripts/check-secrets.sh
git add infra/40-doris-secret.sh infra/test/test-40-doris-secret.sh infra/state.env \
        scripts/check-secrets.sh scripts/test/test-check-secrets.sh \
        specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "feat(p2): T2.1 Secrets Manager doris-mcp/mcp_svc; check-secrets scans Secrets Manager passwords

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T2.4：`ecom` 语义模型 + 对账脚本（demo_ro 只读验证）

**Files:**
- Create：`doris/semantic/ecom/{project,brands,categories,regions,shops,orders,order_items,refunds,reviews,metrics}.yaml`、`doris/test/test_semantic_models.py`、`doris/reconcile.py`、`doris/test/test_reconcile.py`
- Modify：`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：upstream `store.bootstrap.bootstrap_from_yaml`、`collect_physical_tables`；`metricflow` 编译器（`mcp-server/src`）；P1 的 `agentcore_ext.settings.load_settings(env) -> Settings`（`doris_host`、`doris_port`、`doris_user`、`doris_password`；`DORIS_SECRET_ID` 或 `DORIS_USER`/`DORIS_PASSWORD`）和 `agentcore_ext.app.build_server`（`mcp` 模式）
- Produces：
  - `doris/semantic/ecom/`：workspace `ecom` 的 10 个文件，22 个指标，9 张物理表（`dim_brand`、`dim_date`、`dim_region`、`dim_shop`、`fact_order_item`、`fact_refund`、`fact_review`、`v_category`、`v_paid_order`）。维度名：`order_entity__channel`、`shop__shop_name`、`shop__region__area`、`category__cat1_name`、`brand__brand_tier` 等。
  - `doris/reconcile.py`：`python doris/reconcile.py {direct|mcp} [--models DIR] [--workspace ecom] [--case NAME ...]`，exit 0 = 全部一致，1 = 不一致或运行错误，2 = 用法或配置错误；`CASES`（11 个 `Case(name, metrics, group_by, where, reference_sql)`）；`local_metric_names(models_dir) -> set[str]`。T2.5 用它的模型目录，T2.6 用 `mcp` 模式。

模型要点（YAML 注释里也写了）：
- entity 叫 `order_entity`（`order` 是 SQL 保留字）；`shop_id` 是 entity，按店铺过滤要写 `shop__shop_name`。
- 订单级指标来自 `v_paid_order`（含运费）；明细级 `line_gmv` / `qty` / `gross_profit` 加已支付过滤（`order_entity__order_status IS NOT NULL`，即能关联到 `v_paid_order`）；`refund_rate` = 退款件数 / 明细件数，按故事 5.1 **不**过滤已支付。
- 订单级指标不能按 `cat1` 切（fan-out），要用明细级指标；`review_count` 没有 `channel` 维度。
- 同比（`gmv_last_year`、`gmv_yoy`）需要 `metric_time` 和结束日期；time spine `dim_date` 覆盖到 2026-12-31。
- YAML 里字面量 `$` 要写成 `$$`；必须恰好有一个 project 文档；缺 `agg_time_dimension` 能通过 bootstrap，但引擎初始化会失败（T2.5 的离线校验会拦住）。

- [ ] **Step 1：写失败测试 `doris/test/test_semantic_models.py`**

```python
"""Offline tests for the ecom semantic models in doris/semantic/ecom (no Doris connection).

    .venv/bin/python -m unittest discover -s doris/test -v

The models are compiled with the vendored upstream MetricFlow engine exactly as the MCP server
compiles them (bootstrap -> MetricFlowCompiler). Numbers are checked against Doris by
doris/reconcile.py, not here.
"""

from __future__ import annotations

import logging
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
MODELS = ROOT / "doris" / "semantic" / "ecom"

from metricflow.semantic_interfaces.parsing.dir_to_model import (  # noqa: E402
    parse_directory_of_yaml_files_to_semantic_manifest,
)
from metricflow.semantic_interfaces.validations.semantic_manifest_validator import (  # noqa: E402
    SemanticManifestValidator,
)
from store.bootstrap import _copy_and_normalize_models, bootstrap_from_yaml, collect_physical_tables  # noqa: E402
from store.compiler import MetricFlowCompiler  # noqa: E402
from store.manifest import SemanticManifest  # noqa: E402
from store.watcher import _check_staging_duplicates  # noqa: E402

EXPECTED_METRICS = {
    # orders (v_paid_order): measures with create_metric (upstream default)
    "gmv", "order_count", "buyer_count", "discount_amount",
    # orders: explicit metrics
    "aov", "gmv_mini_program", "mini_program_share", "gmv_last_year", "gmv_yoy",
    # order_items (fact_order_item): explicit metrics only
    "line_gmv", "qty", "gross_profit", "gross_margin", "item_count", "refunded_item_count", "refund_rate",
    # refunds (fact_refund) / reviews (fact_review)
    "refund_count", "refund_amount", "review_count", "avg_rating", "bad_review_count", "bad_review_rate",
}
EXPECTED_TABLES = {
    f"internal.ecom.{t}"
    for t in ("v_paid_order", "fact_order_item", "fact_refund", "fact_review",
              "v_category", "dim_brand", "dim_shop", "dim_region", "dim_date")
}
PII_TABLES = {"internal.ecom.dim_user", "internal.ecom.dim_user_address"}
OFFSET_METRICS = {"gmv_last_year", "gmv_yoy"}  # offset_window metrics need metric_time in group_by
# Doris rejects these as bare aliases (`order_id AS order` is a syntax error on Doris 4.1).
RESERVED_ALIAS_RE = re.compile(
    r"\bAS\s+(order|group|user|key|range|rank|partition|table|index|desc|asc|limit|select|from|where)\b",
    re.IGNORECASE,
)


class EcomSemanticModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.disable(logging.WARNING)  # MetricFlow is chatty at INFO/WARNING
        cls.ws = Path(tempfile.mkdtemp(prefix="ecom_ws_"))
        cls.ok, cls.err = bootstrap_from_yaml(MODELS, cls.ws)
        cls.compiler = MetricFlowCompiler(cls.ws) if cls.ok else None
        cls.manifest = SemanticManifest(cls.ws / "target" / "semantic_manifest.json") if cls.ok else None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.ws, ignore_errors=True)
        logging.disable(logging.NOTSET)

    def setUp(self):
        self.assertTrue(self.ok, f"bootstrap_from_yaml failed: {self.err}")

    def compile(self, metrics, group_by=None, where=None):
        sql, _cmd, err = self.compiler.compile(list(metrics), group_by, where)
        return sql, err

    def test_engine_mode(self):
        self.assertTrue(self.compiler.is_engine_mode, self.compiler.init_error)

    def test_no_duplicate_names(self):
        errors, _warnings = _check_staging_duplicates(MODELS)
        self.assertEqual(errors, [])

    def test_manifest_has_no_blocking_issues(self):
        tmp = Path(tempfile.mkdtemp(prefix="ecom_norm_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        _copy_and_normalize_models(MODELS, tmp)
        parsed = parse_directory_of_yaml_files_to_semantic_manifest(
            directory=str(tmp), apply_transformations=True, raise_issues_as_exceptions=False)
        result = SemanticManifestValidator().validate_semantic_manifest(parsed.semantic_manifest)
        self.assertFalse(result.has_blocking_issues, [str(i) for i in result.all_issues])

    def test_metric_names_are_exact(self):
        self.assertEqual({m["name"] for m in self.manifest.list_metrics()}, EXPECTED_METRICS)

    def test_every_metric_has_a_description(self):
        # list_metrics returns only name + description; the description is what the LLM reads.
        missing = [m["name"] for m in self.manifest.list_metrics() if len((m["description"] or "").strip()) < 4]
        self.assertEqual(missing, [])

    def test_physical_tables_are_exact_and_exclude_pii(self):
        tables = collect_physical_tables(MODELS)
        self.assertEqual(tables, EXPECTED_TABLES)
        self.assertFalse(tables & PII_TABLES)

    def test_every_metric_compiles_by_month(self):
        failed = {}
        for name in sorted(EXPECTED_METRICS):
            sql, err = self.compile([name], ["metric_time__month"])
            if not sql:
                failed[name] = (err or "")[:200]
        self.assertEqual(failed, {})

    def test_compiled_sql_has_no_reserved_word_aliases(self):
        for name in sorted(EXPECTED_METRICS):
            group_by = ["metric_time__month"] if name in OFFSET_METRICS else None
            sql, err = self.compile([name], group_by)
            with self.subTest(metric=name):
                self.assertIsNotNone(sql, err)
                self.assertIsNone(RESERVED_ALIAS_RE.search(sql), RESERVED_ALIAS_RE.search(sql))

    def test_item_level_gmv_is_paid_filtered(self):
        # Line-level GMV must only count items of paid orders (cancelled item rows would add ~9.15M).
        for name in ("line_gmv", "qty", "gross_profit", "gross_margin"):
            sql, err = self.compile([name])
            with self.subTest(metric=name):
                self.assertIsNotNone(sql, err)
                self.assertIn("fact_order_item", sql)
                self.assertIn("v_paid_order", sql)

    def test_refund_rate_follows_story_5_1(self):
        # Story 5.1: refunds of any status / all order items (not paid-filtered), by item order month.
        sql, err = self.compile(["refund_rate"], ["metric_time__month"])
        self.assertIsNotNone(sql, err)
        self.assertIn("fact_refund", sql)
        self.assertIn("fact_order_item", sql)
        self.assertNotIn("v_paid_order", sql)

    def test_bare_names_resolve_to_the_intended_dimensions(self):
        resolve = self.compiler.resolve_group_by
        self.assertEqual(resolve(["gmv"], ["channel"]), ["order_entity__channel"])
        self.assertEqual(resolve(["gmv"], ["month"]), ["metric_time__month"])
        self.assertEqual(resolve(["gmv"], ["area"]), ["region__area"])
        self.assertEqual(resolve(["line_gmv"], ["cat1_name"]), ["category__cat1_name"])
        self.assertEqual(resolve(["line_gmv"], ["brand_tier"]), ["brand__brand_tier"])
        for metric in ("line_gmv", "refund_count", "review_count", "refund_rate"):
            with self.subTest(metric=metric):
                (resolved,) = resolve([metric], ["shop_type"])
                self.assertTrue(resolved.endswith("shop__shop_type"), resolved)

    def test_offset_metrics_need_metric_time(self):
        for name in sorted(OFFSET_METRICS):
            with self.subTest(metric=name):
                self.assertIsNone(self.compile([name])[0])
                self.assertIsNotNone(self.compile([name], ["metric_time__month"])[0])
                description = self.manifest.get_metric(name)["description"]
                self.assertIn("metric_time", description)
                # The dim_date spine runs to 2026-12-31: without an end date the offset rows of
                # 2025-10..12 come back as future months with no current value (reconcile yoy_2026).
                self.assertIn("结束日期", description)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 12 tests`、`FAILED (failures=12)`；失败信息是 `AssertionError: False is not true : bootstrap_from_yaml failed: models/ directory not found: …/doris/semantic/ecom`（模型目录还不存在）。

- [ ] **Step 3：写 10 个 YAML**

`doris/semantic/ecom/project.yaml`：

```yaml
# ecom semantic layer (P2 / T2.4, design §6.3). Published to Doris system_mcp by doris/publish-semantic.sh.
# Time spine for offset metrics (gmv_last_year / gmv_yoy): dim_date has one row per day, 2025-01-01..2026-12-31.
time_config:
  calendar:
    - table: internal.ecom.dim_date
      column: full_date
      grain: day
```

`doris/semantic/ecom/brands.yaml`：

```yaml
# Brand dimension.
semantic_model:
  name: brands
  description: 品牌（dim_brand）
  node_relation:
    database: internal
    schema_name: ecom
    alias: dim_brand
  entities:
    - name: brand
      type: primary
      expr: brand_id
  dimensions:
    - name: brand_name
      description: 品牌名
      type: categorical
    - name: brand_tier
      description: 品牌层级 国际品牌 / 国货品牌 / 新锐品牌
      type: categorical
```

`doris/semantic/ecom/categories.yaml`：

```yaml
# Category dimension. fact_order_item.category_id is always a level-3 category; v_category expands it.
semantic_model:
  name: categories
  description: 商品类目（视图 v_category，三级类目展开到二级、一级）
  node_relation:
    database: internal
    schema_name: ecom
    alias: v_category
  entities:
    - name: category
      type: primary
      expr: category_id
  dimensions:
    - name: cat1_name
      description: 一级类目，如 手机数码 / 食品生鲜 / 家居家装
      type: categorical
    - name: cat2_name
      description: 二级类目
      type: categorical
    - name: cat3_name
      description: 三级类目，如 月饼礼盒
      type: categorical
```

`doris/semantic/ecom/regions.yaml`：

```yaml
# Region dimension (city grain). On orders it is the delivery city; on shops it is the shop's city.
semantic_model:
  name: regions
  description: 地区（dim_region，城市粒度；订单上是收货城市）
  node_relation:
    database: internal
    schema_name: ecom
    alias: dim_region
  entities:
    - name: region
      type: primary
      expr: region_id
  dimensions:
    - name: area
      description: 大区 华北 / 东北 / 华东 / 华中 / 华南 / 西南 / 西北
      type: categorical
    - name: province
      description: 省份
      type: categorical
    - name: city
      description: 城市
      type: categorical
    - name: city_tier
      description: 城市等级 一线 / 新一线 / 二线 / 三线 / 四线及以下
      type: categorical
```

`doris/semantic/ecom/shops.yaml`：

```yaml
# Shop dimension.
semantic_model:
  name: shops
  description: 店铺（dim_shop）
  node_relation:
    database: internal
    schema_name: ecom
    alias: dim_shop
  entities:
    - name: shop
      type: primary
      expr: shop_id
    - name: region
      type: foreign
      expr: region_id
  dimensions:
    - name: shop_name
      description: 店铺名，如 深圳极速数码配件专营店
      type: categorical
    - name: shop_type
      description: 店铺类型 自营 / 旗舰店 / 专营店 / 普通店
      type: categorical
    - name: shop_level
      description: 店铺星级 1~5
      type: categorical
```

`doris/semantic/ecom/orders.yaml`：

```yaml
# Order-level facts. Source is the view v_paid_order (fact_order without CANCELLED / PENDING_PAYMENT),
# so every metric here is paid-only, like the story SQL. pay_amount includes freight.
# The entity is named order_entity: an entity named `order` compiles to `... AS order`, a Doris syntax error.
semantic_model:
  name: orders
  description: 有效订单（视图 v_paid_order = fact_order 去掉 CANCELLED / PENDING_PAYMENT，含 REFUNDED），一行一单，按下单日期 order_date 统计
  node_relation:
    database: internal
    schema_name: ecom
    alias: v_paid_order
  defaults:
    agg_time_dimension: order_date
  entities:
    - name: order_entity
      type: primary
      expr: order_id
    - name: shop
      type: foreign
      expr: shop_id
    - name: region
      type: foreign
      expr: region_id
  measures:
    - name: gmv
      description: GMV（成交额）= 有效订单实付金额 pay_amount 之和（含运费），单位元；按下单日期
      label: GMV
      agg: sum
      expr: pay_amount
    - name: order_count
      description: 有效订单数（已支付，含已退款订单）
      label: 订单数
      agg: count_distinct
      expr: order_id
    - name: buyer_count
      description: 下单买家数（去重 user_id）；按月分组时是当月去重，不能跨月相加
      label: 买家数
      agg: count_distinct
      expr: user_id
    - name: discount_amount
      description: 优惠金额 = 活动立减 discount_amount + 优惠券抵扣 coupon_amount，单位元
      label: 优惠金额
      agg: sum
      expr: discount_amount + coupon_amount
  dimensions:
    - name: order_date
      description: 下单日期
      type: time
      type_params:
        time_granularity: day
    - name: channel
      description: 下单渠道 APP / MINI_PROGRAM / H5 / PC
      type: categorical
    - name: device_os
      description: 设备系统 Android / iOS / HarmonyOS / Windows / macOS
      type: categorical
    - name: is_first_order
      description: 是否首单 1 / 0
      type: categorical
    - name: order_status
      description: 订单状态 PAID / SHIPPED / DELIVERED / COMPLETED / REFUNDED
      type: categorical
    - name: promo_id
      description: 所属大促 ID，日常订单为 NULL
      type: categorical
```

`doris/semantic/ecom/order_items.yaml`：

```yaml
# Line-level facts (one row per order item). No measure becomes a metric by itself (create_metric: false):
# the metrics in metrics.yaml add the paid-order filter where the story SQL has it.
semantic_model:
  name: order_items
  description: 订单明细（fact_order_item），一行一个商品行，按下单日期 order_date 统计；金额不含运费
  node_relation:
    database: internal
    schema_name: ecom
    alias: fact_order_item
  defaults:
    agg_time_dimension: order_date
  entities:
    - name: order_item
      type: primary
      expr: item_id
    - name: order_entity
      type: foreign
      expr: order_id
    - name: shop
      type: foreign
      expr: shop_id
    - name: category
      type: foreign
      expr: category_id
    - name: brand
      type: foreign
      expr: brand_id
  measures:
    - name: item_pay_amount
      description: 明细实付金额（不含运费）
      agg: sum
      expr: pay_amount
      create_metric: false
    - name: item_quantity
      description: 商品件数
      agg: sum
      expr: quantity
      create_metric: false
    - name: item_profit
      description: 明细毛利 = 实付 - 成本
      agg: sum
      expr: pay_amount - cost_amount
      create_metric: false
    - name: item_rows
      description: 明细行数
      agg: count_distinct
      expr: item_id
      create_metric: false
  dimensions:
    - name: order_date
      description: 下单日期
      type: time
      type_params:
        time_granularity: day
```

`doris/semantic/ecom/refunds.yaml`：

```yaml
# After-sales refunds, counted by application date. Refunds and order items are 1:1 on item_id.
semantic_model:
  name: refunds
  description: 售后退款（fact_refund），一行一个退款申请（与订单明细 1:1），按申请日期 apply_date 统计
  node_relation:
    database: internal
    schema_name: ecom
    alias: fact_refund
  defaults:
    agg_time_dimension: apply_date
  entities:
    - name: refund
      type: primary
      expr: refund_id
    - name: order_item
      type: unique
      expr: item_id
    - name: shop
      type: foreign
      expr: shop_id
  measures:
    - name: refund_count
      description: 退款申请数（任意状态），按申请日期
      label: 退款数
      agg: count_distinct
      expr: refund_id
    - name: refund_amount
      description: 退款申请金额（任意状态，单位元），按申请日期；只看已退款用 where refund_status = 'REFUNDED'
      label: 退款金额
      agg: sum
      expr: refund_amount
  dimensions:
    - name: apply_date
      description: 退款申请日期
      type: time
      type_params:
        time_granularity: day
    - name: refund_reason
      description: 退款原因，如 质量问题
      type: categorical
    - name: refund_type
      description: 售后类型 RETURN_REFUND（退货退款）/ REFUND_ONLY（仅退款）/ EXCHANGE（换货）
      type: categorical
    - name: refund_status
      description: 退款状态 REFUNDED / REJECTED / EXCHANGED / PROCESSING
      type: categorical
```

`doris/semantic/ecom/reviews.yaml`：

```yaml
# Product reviews, counted by review date.
semantic_model:
  name: reviews
  description: 商品评价（fact_review），一行一条评价，按评价日期 review_date 统计
  node_relation:
    database: internal
    schema_name: ecom
    alias: fact_review
  defaults:
    agg_time_dimension: review_date
  entities:
    - name: review
      type: primary
      expr: review_id
    - name: shop
      type: foreign
      expr: shop_id
  measures:
    - name: review_count
      description: 评价数，按评价日期
      label: 评价数
      agg: count_distinct
      expr: review_id
    - name: avg_rating
      description: 平均评分（1~5 分），按评价日期
      label: 平均评分
      agg: average
      expr: rating
    - name: bad_review_count
      description: 差评数（rating <= 2），按评价日期
      label: 差评数
      agg: sum
      expr: "CASE WHEN rating <= 2 THEN 1 ELSE 0 END"
  dimensions:
    - name: review_date
      description: 评价日期
      type: time
      type_params:
        time_granularity: day
    - name: has_image
      description: 是否带图 1 / 0
      type: categorical
```

`doris/semantic/ecom/metrics.yaml`：

```yaml
# Explicit metrics. Measures of orders / refunds / reviews also become metrics of the same name
# (upstream adds create_metric: true); order_items measures do not.
# Filters use `order_entity__...` dimensions; see orders.yaml for why the entity is not called `order`.

# ---- orders (v_paid_order) ----
metric:
  name: aov
  description: 客单价 AOV = GMV / 订单数，单位元（已支付订单，含运费）
  label: 客单价
  type: ratio
  type_params:
    numerator:
      name: gmv
    denominator:
      name: order_count
---
metric:
  name: gmv_mini_program
  description: 小程序渠道（channel = MINI_PROGRAM）的 GMV，单位元
  label: 小程序 GMV
  type: simple
  type_params:
    measure: gmv
  filter: "{{ Dimension('order_entity__channel') }} = 'MINI_PROGRAM'"
---
metric:
  name: mini_program_share
  description: 小程序 GMV 占比 = 小程序 GMV / GMV（0~1）
  label: 小程序 GMV 占比
  type: ratio
  type_params:
    numerator:
      name: gmv_mini_program
    denominator:
      name: gmv
---
metric:
  name: gmv_last_year
  description: 去年同期 GMV（metric_time 偏移 1 年），单位元；必须按 metric_time 分组（如 group_by metric_time__month），where 要写结束日期（如 metric_time BETWEEN '2026-01-01' AND '2026-09-25'），否则会多出没有本期值的未来月份
  label: 去年同期 GMV
  type: derived
  type_params:
    expr: gmv_ly
    metrics:
      - name: gmv
        offset_window: 1 year
        alias: gmv_ly
---
metric:
  name: gmv_yoy
  description: GMV 同比增长率 = (GMV - 去年同期 GMV) / 去年同期 GMV；必须按 metric_time 分组（如 group_by metric_time__month），where 要写结束日期（如 metric_time BETWEEN '2026-01-01' AND '2026-09-25'），否则会多出没有本期值的未来月份
  label: GMV 同比
  type: derived
  type_params:
    expr: (gmv - gmv_ly) / NULLIF(gmv_ly, 0)
    metrics:
      - name: gmv
      - name: gmv
        offset_window: 1 year
        alias: gmv_ly
---
# ---- order_items (fact_order_item) ----
metric:
  name: line_gmv
  description: 明细 GMV = 已支付订单的商品行实付金额之和（不含运费），单位元；按类目 / 品牌 / 店铺分析 GMV 时用它
  label: 明细 GMV
  type: simple
  type_params:
    measure: item_pay_amount
  filter: "{{ Dimension('order_entity__order_status') }} IS NOT NULL"
---
metric:
  name: qty
  description: 销量 = 已支付订单的商品件数
  label: 销量
  type: simple
  type_params:
    measure: item_quantity
  filter: "{{ Dimension('order_entity__order_status') }} IS NOT NULL"
---
metric:
  name: gross_profit
  description: 毛利 = 已支付订单的商品行（实付 - 成本）之和，单位元
  label: 毛利
  type: simple
  type_params:
    measure: item_profit
  filter: "{{ Dimension('order_entity__order_status') }} IS NOT NULL"
---
metric:
  name: gross_margin
  description: 毛利率 = 毛利 / 明细 GMV（0~1）
  label: 毛利率
  type: ratio
  type_params:
    numerator:
      name: gross_profit
    denominator:
      name: line_gmv
---
metric:
  name: item_count
  description: 商品行数（全部订单明细，含已取消订单），按下单日期；退款率 refund_rate 的分母
  label: 商品行数
  type: simple
  type_params:
    measure: item_rows
---
metric:
  name: refunded_item_count
  description: 发生过退款申请（任意状态）的商品行数，按商品下单日期；退款率 refund_rate 的分子
  label: 退款商品行数
  type: simple
  type_params:
    measure: item_rows
  filter: "{{ Dimension('order_item__refund_status') }} IS NOT NULL"
---
metric:
  name: refund_rate
  description: 退款率 = 发生退款申请的商品行数 / 商品行数（0~1），按商品下单月统计（故事 5.1 口径，不过滤支付状态）；按店铺看用 group_by shop__shop_name
  label: 退款率
  type: ratio
  type_params:
    numerator:
      name: refunded_item_count
    denominator:
      name: item_count
---
# ---- reviews (fact_review) ----
metric:
  name: bad_review_rate
  description: 差评率 = 差评数（rating <= 2）/ 评价数（0~1），按评价日期
  label: 差评率
  type: ratio
  type_params:
    numerator:
      name: bad_review_count
    denominator:
      name: review_count
```

- [ ] **Step 4：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 12 tests`、`OK`。

- [ ] **Step 5：写失败测试 `doris/test/test_reconcile.py`**

```python
"""Offline tests for doris/reconcile.py (no Doris connection, no MCP server).

    .venv/bin/python -m unittest discover -s doris/test -v

The live runs are `reconcile.py direct` (T2.4) and `reconcile.py mcp` (T2.6); here the
connection and the MCP client are fakes, while the semantic models are compiled for real.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import logging
import re
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
sys.path.insert(0, str(ROOT / "doris"))

import pymysql  # noqa: E402

import reconcile  # noqa: E402
from core.sql_validator import validate_readonly  # noqa: E402
from reconcile import (  # noqa: E402
    APPROX_METRICS, CASES, Case, DirectBackend, McpBackend, ReconcileError, compare, local_metric_names, normalize,
)

MODELS = ROOT / "doris" / "semantic" / "ecom"
PASSWORD = "Pw0123456789abcdefXYZ"
ENV = {"DORIS_HOST": "10.0.0.1", "DORIS_PORT": "9030", "DORIS_USER": "demo_ro", "DORIS_PASSWORD": PASSWORD}
MONEY = Case("money", ("gmv", "order_count"), ("order_entity__channel",), "", "SELECT 1")
RATIO = Case("ratio", ("refund_rate",), ("metric_time__month",), "", "SELECT 1")
YTD_ROW = {"gmv": Decimal("65442236.24"), "order_count": 42770, "buyer_count": 20187,
           "discount_amount": Decimal("4430032.46"), "aov": 1530.0967089081132}


def setUpModule():
    logging.disable(logging.WARNING)  # MetricFlow is chatty at INFO/WARNING


def tearDownModule():
    logging.disable(logging.NOTSET)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        self.conn.executed.append(sql)

    def fetchall(self):
        return [dict(r) for r in self.conn.rows]


class FakeConn:
    def __init__(self, rows):
        self.rows, self.executed, self.closed = rows, [], False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class FakeClient:
    """Stands in for fastmcp.Client: returns canned tool bodies as MCP text content."""

    def __init__(self, bodies):
        self.bodies, self.calls = bodies, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def call_tool(self, name, args, raise_on_error=True):
        self.calls.append((name, args, raise_on_error))
        body = self.bodies[name]
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


def ok(data, meta=None):
    return {"success": True, "data": data, **({"meta": meta} if meta else {})}


def run_main(argv, env=ENV, conn=None, connect=None, client=None):
    out, err, seen = io.StringIO(), io.StringIO(), {}

    def fake_connect(**kwargs):
        seen.update(kwargs)
        return conn

    rc = reconcile.main(argv, env=env, connect=connect or fake_connect, out=out, err=err,
                        client_factory=(lambda settings: client) if client else None)
    return rc, out.getvalue(), err.getvalue(), seen


class Normalize(unittest.TestCase):
    def test_values_are_encoded_like_the_mcp_response(self):
        # Mirrors core.response._Encoder, so direct rows and MCP rows compare alike.
        self.assertEqual(normalize(Decimal("65442236.24")), 65442236.24)
        self.assertIsInstance(normalize(Decimal("1")), float)
        self.assertEqual(normalize(dt.date(2026, 1, 1)), "2026-01-01")
        self.assertEqual(normalize(dt.datetime(2026, 1, 1, 8, 30)), "2026-01-01T08:30:00")
        self.assertEqual(normalize(b"APP"), "APP")
        self.assertEqual(normalize(42770), 42770)
        self.assertIsNone(normalize(None))


class Compare(unittest.TestCase):
    def test_equal_rows_in_any_order_match(self):
        got = [{"order_entity__channel": "APP", "gmv": 2.5, "order_count": 2},
               {"order_entity__channel": "PC", "gmv": 1.0, "order_count": 1}]
        want = [{"order_entity__channel": "PC", "gmv": Decimal("1.00"), "order_count": 1},
                {"order_entity__channel": "APP", "gmv": Decimal("2.50"), "order_count": 2}]
        self.assertEqual(compare(MONEY, got, want), [])

    def test_missing_and_unexpected_rows_are_reported(self):
        got = [{"order_entity__channel": "APP", "gmv": 1, "order_count": 1}]
        want = [{"order_entity__channel": "PC", "gmv": 1, "order_count": 1}]
        problems = compare(MONEY, got, want)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("missing row ('PC',)", problems[0])
        self.assertIn("unexpected row ('APP',)", problems[1])

    def test_money_must_match_to_the_cent(self):
        want = [{"order_entity__channel": "APP", "gmv": Decimal("100.00"), "order_count": 1}]
        close = [{"order_entity__channel": "APP", "gmv": 100.004, "order_count": 1}]
        off = [{"order_entity__channel": "APP", "gmv": 100.01, "order_count": 1}]
        self.assertEqual(compare(MONEY, close, want), [])
        (problem,) = compare(MONEY, off, want)
        self.assertIn("gmv", problem)

    def test_ratios_must_match_to_six_decimals(self):
        want = [{"metric_time__month": dt.date(2026, 7, 1), "refund_rate": Decimal("0.173913")}]
        close = [{"metric_time__month": "2026-07-01", "refund_rate": 0.17391304347826086}]
        off = [{"metric_time__month": "2026-07-01", "refund_rate": 0.1740}]
        self.assertEqual(compare(RATIO, close, want), [])
        self.assertEqual(len(compare(RATIO, off, want)), 1)

    def test_null_metric_counts_as_zero(self):
        # upstream query_metric turns NULL metric cells (FULL OUTER JOIN gaps) into 0
        got = [{"order_entity__channel": "H5", "gmv": 0, "order_count": 0}]
        want = [{"order_entity__channel": "H5", "gmv": None, "order_count": None}]
        self.assertEqual(compare(MONEY, got, want), [])

    def test_empty_reference_is_a_failure(self):
        # Zero rows on both sides would "match" even when both filters are wrong.
        self.assertEqual(len(compare(MONEY, [], [])), 1)

    def test_missing_columns_are_reported(self):
        got = [{"channel": "APP", "gmv": 1, "order_count": 1}]
        want = [{"order_entity__channel": "APP", "gmv": 1, "order_count": 1}]
        (problem,) = compare(MONEY, got, want)
        self.assertIn("order_entity__channel", problem)

    def test_duplicate_keys_are_reported(self):
        row = {"order_entity__channel": "APP", "gmv": 1, "order_count": 1}
        self.assertTrue(any("duplicate" in p for p in compare(MONEY, [row, row], [row])))


class Cases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names = local_metric_names(MODELS)

    def test_cases_cover_every_metric(self):
        covered = set().union(*(c.metrics for c in CASES))
        self.assertEqual(covered, self.names)

    def test_case_names_are_unique(self):
        names = [c.name for c in CASES]
        self.assertEqual(len(names), len(set(names)))

    def test_approx_metrics_exist(self):
        self.assertLessEqual(APPROX_METRICS, self.names)

    def test_offset_metric_cases_have_an_end_date(self):
        # Unbounded, the dim_date spine (to 2026-12-31) adds 2026-10..12 rows holding only last-year values.
        for case in CASES:
            if {"gmv_last_year", "gmv_yoy"} & set(case.metrics):
                with self.subTest(case=case.name):
                    self.assertRegex(case.where, r"metric_time BETWEEN '[0-9-]+' AND '[0-9-]+'")

    def test_reference_sql_is_read_only_and_aliases_every_column(self):
        for case in CASES:
            with self.subTest(case=case.name):
                self.assertEqual(validate_readonly(case.reference_sql), (True, ""))
                for col in case.columns:
                    self.assertRegex(case.reference_sql, re.compile(rf"\bAS\s+{col}\b", re.IGNORECASE))

    def test_every_case_compiles_to_read_only_sql(self):
        with tempfile.TemporaryDirectory() as ws:
            backend = DirectBackend(MODELS, ws, fetch=None)
            for case in CASES:
                with self.subTest(case=case.name):
                    self.assertEqual(validate_readonly(backend.sql(case)), (True, ""))


class Direct(unittest.TestCase):
    def test_query_executes_the_compiled_sql(self):
        seen = []
        with tempfile.TemporaryDirectory() as ws:
            backend = DirectBackend(MODELS, ws, fetch=lambda sql: seen.append(sql) or [{"x": 1}])
            case = next(c for c in CASES if c.name == "refund_rate_5_1")
            self.assertEqual(asyncio.run(backend.query(case)), [{"x": 1}])
        (sql,) = seen
        self.assertIn("fact_refund", sql)
        self.assertIn("深圳极速数码配件专营店", sql)

    def test_uncompilable_case_raises(self):
        bad = Case("bad", ("gmv_yoy",), (), "", "SELECT 1")  # offset metric without metric_time
        with tempfile.TemporaryDirectory() as ws:
            with self.assertRaises(ReconcileError):
                DirectBackend(MODELS, ws, fetch=None).sql(bad)


class Mcp(unittest.TestCase):
    def test_query_calls_query_metric_like_an_agent(self):
        client = FakeClient({"query_metric": ok({"columns": ["gmv"], "rows": [{"gmv": 1.5}]})})
        rows = asyncio.run(McpBackend(client, "ecom").query(
            Case("c", ("gmv",), ("metric_time__month",), "metric_time >= '2026-01-01'", "SELECT 1")))
        self.assertEqual(rows, [{"gmv": 1.5}])
        self.assertEqual(client.calls, [("query_metric", {
            "workspace": "ecom", "metrics": ["gmv"], "group_by": ["metric_time__month"],
            "where": "metric_time >= '2026-01-01'"}, False)])

    def test_tool_error_raises_with_its_code(self):
        client = FakeClient({"query_metric": {"success": False,
                                              "error": {"code": "VALIDATION_ERROR", "message": "bad dim"}}})
        with self.assertRaisesRegex(ReconcileError, "VALIDATION_ERROR"):
            asyncio.run(McpBackend(client, "ecom").query(MONEY))

    def test_non_json_result_raises(self):
        client = FakeClient({"query_metric": "Error calling tool"})
        with self.assertRaisesRegex(ReconcileError, "non-JSON"):
            asyncio.run(McpBackend(client, "ecom").query(MONEY))

    def test_metric_names_reads_one_full_page(self):
        client = FakeClient({"list_metrics": ok([{"name": "gmv", "description": "d"}], {"total_count": 1})})
        self.assertEqual(asyncio.run(McpBackend(client, "ecom").metric_names()), {"gmv"})
        self.assertEqual(client.calls[0][1], {"workspace": "ecom", "page_size": 100})

    def test_metric_names_refuses_a_partial_page(self):
        client = FakeClient({"list_metrics": ok([{"name": "gmv", "description": "d"}],
                                                {"total_count": 150, "next_page_token": "t:100"})})
        with self.assertRaises(ReconcileError):
            asyncio.run(McpBackend(client, "ecom").metric_names())


class Run(unittest.TestCase):
    def test_reconcile_counts_failures_and_masks_secrets(self):
        cases = [MONEY, Case("broken", ("gmv",), (), "", "SELECT 1"), Case("off", ("gmv",), (), "", "SELECT 2")]
        row = {"order_entity__channel": "APP", "gmv": 1, "order_count": 1}

        async def query(case):
            if case.name == "broken":
                raise pymysql.OperationalError(1045, f"Access denied (using password: {PASSWORD})")
            return [row] if case.name == "money" else [{"gmv": 2}]

        out = io.StringIO()
        failed = asyncio.run(reconcile.reconcile(cases, query, lambda case: [row] if case.name == "money"
                                                 else [{"gmv": 1}], out, secrets=[PASSWORD]))
        text = out.getvalue()
        self.assertEqual(failed, 2)
        self.assertIn("ok    money (1 rows)", text)
        self.assertIn("FAIL  broken", text)
        self.assertIn("FAIL  off", text)
        self.assertNotIn(PASSWORD, text)


class Main(unittest.TestCase):
    def test_missing_host_is_a_usage_error(self):
        rc, _, err, _ = run_main(["direct"], env={"DORIS_USER": "u", "DORIS_PASSWORD": "p"})
        self.assertEqual(rc, 2)
        self.assertIn("DORIS_HOST", err)

    def test_unknown_case_is_a_usage_error(self):
        rc, _, err, _ = run_main(["direct", "--case", "nope"], conn=FakeConn([]))
        self.assertEqual(rc, 2)
        self.assertIn("nope", err)

    def test_connect_error_is_masked(self):
        # pymysql puts the host in its connect errors: "Can't connect to MySQL server on '<host>' ...".
        def boom(**_):
            raise pymysql.OperationalError(2003, f"Can't connect to MySQL server on '10.0.0.1' ({PASSWORD})")

        rc, out, err, _ = run_main(["direct"], connect=boom)
        self.assertEqual(rc, 1)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("10.0.0.1", out + err)
        self.assertIn("***", err)

    def test_direct_runs_compiled_and_reference_sql_on_one_connection(self):
        conn = FakeConn([YTD_ROW])
        rc, out, _, seen = run_main(["direct", "--case", "ytd_totals"], conn=conn)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(conn.executed), 2)  # compiled SQL + reference SQL
        self.assertIn("v_paid_order", conn.executed[0])
        self.assertTrue(conn.closed)
        self.assertEqual((seen["host"], seen["port"], seen["user"]), ("10.0.0.1", 9030, "demo_ro"))
        self.assertIs(seen["cursorclass"], pymysql.cursors.DictCursor)
        self.assertIn("1/1 cases match", out)

    def test_mcp_checks_published_metrics_then_reconciles(self):
        names = sorted(local_metric_names(MODELS))
        client = FakeClient({"list_metrics": ok([{"name": n, "description": "d"} for n in names],
                                                {"total_count": len(names)}),
                             "query_metric": ok({"columns": list(YTD_ROW), "rows": [json.loads(
                                 json.dumps(YTD_ROW, default=float))]})})
        conn = FakeConn([YTD_ROW])
        rc, out, _, _ = run_main(["mcp", "--case", "ytd_totals"], conn=conn, client=client)
        self.assertEqual(rc, 0, out)
        self.assertEqual([c[0] for c in client.calls], ["list_metrics", "query_metric"])
        self.assertEqual(len(conn.executed), 1)  # only the reference SQL runs on the direct connection
        self.assertIn(f"published metrics: {len(names)} match", out)

    def test_mcp_fails_when_published_metrics_differ(self):
        client = FakeClient({"list_metrics": ok([{"name": "gmv", "description": "d"}], {"total_count": 1}),
                             "query_metric": ok({"columns": list(YTD_ROW), "rows": [json.loads(
                                 json.dumps(YTD_ROW, default=float))]})})
        rc, out, _, _ = run_main(["mcp", "--case", "ytd_totals"], conn=FakeConn([YTD_ROW]), client=client)
        self.assertEqual(rc, 1)
        self.assertIn("published metrics differ", out)
        self.assertIn("missing", out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 13 tests`、`FAILED (errors=1)`，报错是 `ModuleNotFoundError: No module named 'reconcile'`。

- [ ] **Step 7：写 `doris/reconcile.py`**

```python
"""Reconcile the ecom semantic metrics with the storyline SQL (P2 / T2.4, T2.6; R-26).

    python doris/reconcile.py direct [--models DIR] [--case NAME ...]   # compile the local YAML, run via pymysql
    python doris/reconcile.py mcp [--workspace ecom] [--case NAME ...]  # in-process MCP server: list_metrics + query_metric

Connection: agentcore_ext.settings.load_settings(os.environ) -- DORIS_HOST, DORIS_PORT and either
DORIS_SECRET_ID or DORIS_USER/DORIS_PASSWORD. Every statement is a SELECT; the MCP server may run its
CREATE ... IF NOT EXISTS on system_mcp. Each case runs the metric query and a hand-written reference
SQL (column aliases = the semantic output columns) and compares the rows by the group-by key.
Exit 0 when every case matches, 1 on a mismatch or runtime error, 2 on usage/configuration errors.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import json
import logging
import math
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
MODELS_DIR = ROOT / "doris" / "semantic" / "ecom"

import pymysql  # noqa: E402

from agentcore_ext.settings import Settings, SettingsError, load_settings  # noqa: E402
from core.sql_validator import validate_readonly  # noqa: E402
from store.bootstrap import bootstrap_from_yaml  # noqa: E402
from store.compiler import MetricFlowCompiler  # noqa: E402
from store.manifest import SemanticManifest  # noqa: E402

MASK = "***"
MAX_PROBLEMS = 10
# Ratios and averages are computed in DOUBLE (or scale-6 DECIMAL); everything else is an exact sum/count.
APPROX_METRICS = frozenset(
    {"aov", "mini_program_share", "gmv_yoy", "gross_margin", "refund_rate", "avg_rating", "bad_review_rate"})
YTD = "metric_time BETWEEN '2026-01-01' AND '2026-09-24'"
YTD_SQL = "BETWEEN '2026-01-01' AND '2026-09-24'"


class ReconcileError(RuntimeError):
    """A case could not be run; messages never contain secret values."""


@dataclasses.dataclass(frozen=True)
class Case:
    name: str
    metrics: tuple[str, ...]
    group_by: tuple[str, ...]  # fully qualified, so the output column names are fixed
    where: str  # bare names, as an agent writes them; resolved like the server does
    reference_sql: str

    @property
    def columns(self) -> tuple[str, ...]:
        return self.group_by + self.metrics


CASES: tuple[Case, ...] = (
    Case("ytd_totals", ("gmv", "order_count", "buyer_count", "discount_amount", "aov"), (), YTD, f"""
        SELECT SUM(pay_amount) AS gmv, COUNT(DISTINCT order_id) AS order_count,
               COUNT(DISTINCT user_id) AS buyer_count, SUM(discount_amount + coupon_amount) AS discount_amount,
               CAST(SUM(pay_amount) AS DOUBLE) / COUNT(DISTINCT order_id) AS aov
        FROM ecom.v_paid_order WHERE order_date {YTD_SQL}"""),
    # Story 2.2 has no end date: 2026-09 includes the live orders of 09-25.
    Case("monthly_2026", ("gmv", "order_count", "buyer_count"), ("metric_time__month",),
         "metric_time >= '2026-01-01'", """
        SELECT DATE_TRUNC('month', order_date) AS metric_time__month, SUM(pay_amount) AS gmv,
               COUNT(DISTINCT order_id) AS order_count, COUNT(DISTINCT user_id) AS buyer_count
        FROM ecom.v_paid_order WHERE order_date >= '2026-01-01'
        GROUP BY DATE_TRUNC('month', order_date)"""),
    # Offset metrics need an end date: the dim_date spine runs to 2026-12-31, so an open range adds
    # 2026-10..12 rows that hold only last-year values. 2026-09 (to 09-25) is compared with all of 2025-09.
    Case("yoy_2026", ("gmv", "gmv_last_year", "gmv_yoy"), ("metric_time__month",),
         "metric_time BETWEEN '2026-01-01' AND '2026-09-25'", """
        SELECT t.m AS metric_time__month, t.gmv AS gmv, l.gmv AS gmv_last_year,
               (t.gmv - l.gmv) / NULLIF(l.gmv, 0) AS gmv_yoy
        FROM (SELECT DATE_TRUNC('month', order_date) AS m, SUM(pay_amount) AS gmv
              FROM ecom.v_paid_order WHERE order_date >= '2026-01-01'
              GROUP BY DATE_TRUNC('month', order_date)) t
        LEFT JOIN (SELECT MONTHS_ADD(DATE_TRUNC('month', order_date), 12) AS m, SUM(pay_amount) AS gmv
                   FROM ecom.v_paid_order WHERE order_date < '2026-01-01'
                   GROUP BY MONTHS_ADD(DATE_TRUNC('month', order_date), 12)) l ON l.m = t.m"""),
    Case("channel_ytd", ("gmv", "order_count"), ("order_entity__channel",), YTD, f"""
        SELECT channel AS order_entity__channel, SUM(pay_amount) AS gmv, COUNT(DISTINCT order_id) AS order_count
        FROM ecom.v_paid_order WHERE order_date {YTD_SQL} GROUP BY channel"""),
    Case("area_ytd", ("gmv", "order_count", "buyer_count", "aov"), ("region__area",), YTD, f"""
        SELECT r.area AS region__area, SUM(o.pay_amount) AS gmv, COUNT(DISTINCT o.order_id) AS order_count,
               COUNT(DISTINCT o.user_id) AS buyer_count,
               CAST(SUM(o.pay_amount) AS DOUBLE) / COUNT(DISTINCT o.order_id) AS aov
        FROM ecom.v_paid_order o JOIN ecom.dim_region r ON r.region_id = o.region_id
        WHERE o.order_date {YTD_SQL} GROUP BY r.area"""),
    # Story 2.5: all quarters, 2026-Q3 includes 09-25.
    Case("mini_program_quarterly", ("gmv", "gmv_mini_program", "mini_program_share"), ("metric_time__quarter",),
         "", """
        SELECT DATE_TRUNC('quarter', order_date) AS metric_time__quarter, SUM(pay_amount) AS gmv,
               SUM(IF(channel = 'MINI_PROGRAM', pay_amount, 0)) AS gmv_mini_program,
               CAST(SUM(IF(channel = 'MINI_PROGRAM', pay_amount, 0)) AS DOUBLE) / SUM(pay_amount)
                   AS mini_program_share
        FROM ecom.v_paid_order GROUP BY DATE_TRUNC('quarter', order_date)"""),
    # Item-level metrics count only items of paid orders.
    Case("cat1_items_ytd", ("line_gmv", "qty", "gross_profit", "gross_margin"), ("category__cat1_name",), YTD, f"""
        SELECT c.cat1_name AS category__cat1_name, SUM(i.pay_amount) AS line_gmv, SUM(i.quantity) AS qty,
               SUM(i.pay_amount - i.cost_amount) AS gross_profit,
               CAST(SUM(i.pay_amount - i.cost_amount) AS DOUBLE) / SUM(i.pay_amount) AS gross_margin
        FROM ecom.fact_order_item i
        JOIN ecom.v_paid_order o ON o.order_id = i.order_id
        JOIN ecom.v_category c ON c.category_id = i.category_id
        WHERE i.order_date {YTD_SQL} GROUP BY c.cat1_name"""),
    Case("brand_tier_ytd", ("line_gmv", "gross_profit"), ("brand__brand_tier",), YTD, f"""
        SELECT b.brand_tier AS brand__brand_tier, SUM(i.pay_amount) AS line_gmv,
               SUM(i.pay_amount - i.cost_amount) AS gross_profit
        FROM ecom.fact_order_item i
        JOIN ecom.v_paid_order o ON o.order_id = i.order_id
        JOIN ecom.dim_brand b ON b.brand_id = i.brand_id
        WHERE i.order_date {YTD_SQL} GROUP BY b.brand_tier"""),
    # Story 5.1: refunds of any status / all item rows (cancelled orders included), by item order month.
    Case("refund_rate_5_1", ("refund_rate", "refunded_item_count", "item_count"),
         ("shop__shop_name", "metric_time__month"),
         "metric_time BETWEEN '2026-07-01' AND '2026-08-31' AND shop__shop_name = '深圳极速数码配件专营店'", """
        SELECT s.shop_name AS shop__shop_name, DATE_TRUNC('month', i.order_date) AS metric_time__month,
               COUNT(r.refund_id) AS refunded_item_count, COUNT(*) AS item_count,
               CAST(COUNT(r.refund_id) AS DOUBLE) / COUNT(*) AS refund_rate
        FROM ecom.fact_order_item i
        JOIN ecom.dim_shop s ON s.shop_id = i.shop_id
        LEFT JOIN ecom.fact_refund r ON r.item_id = i.item_id
        WHERE i.order_date BETWEEN '2026-07-01' AND '2026-08-31' AND s.shop_name = '深圳极速数码配件专营店'
        GROUP BY s.shop_name, DATE_TRUNC('month', i.order_date)"""),
    Case("reviews_by_shop_type_ytd", ("review_count", "avg_rating", "bad_review_count", "bad_review_rate"),
         ("shop__shop_type",), YTD, f"""
        SELECT s.shop_type AS shop__shop_type, COUNT(DISTINCT v.review_id) AS review_count,
               AVG(v.rating) AS avg_rating, SUM(IF(v.rating <= 2, 1, 0)) AS bad_review_count,
               CAST(SUM(IF(v.rating <= 2, 1, 0)) AS DOUBLE) / COUNT(DISTINCT v.review_id) AS bad_review_rate
        FROM ecom.fact_review v JOIN ecom.dim_shop s ON s.shop_id = v.shop_id
        WHERE v.review_date {YTD_SQL} GROUP BY s.shop_type"""),
    Case("refunds_by_reason_ytd", ("refund_count", "refund_amount"), ("refund__refund_reason",), YTD, f"""
        SELECT refund_reason AS refund__refund_reason, COUNT(DISTINCT refund_id) AS refund_count,
               SUM(refund_amount) AS refund_amount
        FROM ecom.fact_refund WHERE apply_date {YTD_SQL} GROUP BY refund_reason"""),
)


def normalize(value: Any) -> Any:
    """Encode like core.response._Encoder, so direct rows and MCP rows compare alike."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _number(value: Any) -> float:
    value = normalize(value)
    if value is None:  # upstream query_metric reports NULL metric cells as 0
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _close(metric: str, a: float, b: float) -> bool:
    if metric in APPROX_METRICS:
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
    return abs(a - b) <= 0.005


def compare(case: Case, got: Sequence[Mapping[str, Any]], want: Sequence[Mapping[str, Any]]) -> list[str]:
    """Problems found when matching semantic rows (got) with reference rows (want) by group-by key."""
    if not want:
        return ["reference SQL returned no rows"]
    problems: list[str] = []
    indexes = []
    for side, rows in (("semantic", got), ("reference", want)):
        index: dict[tuple, Mapping[str, Any]] = {}
        for row in rows:
            absent = [c for c in case.columns if c not in row]
            if absent:
                return [f"{side} rows lack columns {absent} (have {sorted(row)})"]
            key = tuple(normalize(row[c]) for c in case.group_by)
            if key in index:
                problems.append(f"{side}: duplicate row {key}")
            index[key] = row
        indexes.append(index)
    got_index, want_index = indexes
    problems += [f"missing row {k}" for k in sorted(want_index.keys() - got_index.keys(), key=repr)]
    problems += [f"unexpected row {k}" for k in sorted(got_index.keys() - want_index.keys(), key=repr)]
    for key in sorted(got_index.keys() & want_index.keys(), key=repr):
        for metric in case.metrics:
            a, b = _number(got_index[key][metric]), _number(want_index[key][metric])
            if not _close(metric, a, b):
                problems.append(f"{key} {metric}: semantic {a!r} != reference {b!r}")
    return problems


def _mask(text: str, secrets: Iterable[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, MASK)
    return text


def fetch(conn: Any, sql: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return list(cur.fetchall())


class DirectBackend:
    """Compile like the server's query_metric (bare names resolved, read-only check); run the SQL via fetch."""

    def __init__(self, models_dir: Path | str, workspace_dir: Path | str,
                 fetch: Callable[[str], list[dict[str, Any]]] | None):
        ws = Path(workspace_dir)
        ok, error = bootstrap_from_yaml(Path(models_dir), ws)
        if not ok:
            raise ReconcileError(f"bootstrap {models_dir}: {error}")
        self.compiler = MetricFlowCompiler(ws)
        if not self.compiler.is_engine_mode:
            raise ReconcileError(f"MetricFlow engine unavailable: {self.compiler.init_error}")
        self.manifest = SemanticManifest(ws / "target" / "semantic_manifest.json")
        self._fetch = fetch

    def metric_names(self) -> set[str]:
        return {m["name"] for m in self.manifest.list_metrics()}

    def sql(self, case: Case) -> str:
        metrics = list(case.metrics)
        group_by = self.compiler.resolve_group_by(metrics, list(case.group_by)) if case.group_by else None
        where = self.compiler.resolve_where(metrics, case.where) if case.where else None
        sql, _command, error = self.compiler.compile(metrics, group_by, where)
        if not sql:
            raise ReconcileError(f"compile failed: {(error or 'empty SQL')[:300]}")
        ok, message = validate_readonly(sql)
        if not ok:
            raise ReconcileError(f"compiled SQL is not read-only: {message}")
        return sql

    async def query(self, case: Case) -> list[dict[str, Any]]:
        return self._fetch(self.sql(case))


def local_metric_names(models_dir: Path | str) -> set[str]:
    with tempfile.TemporaryDirectory(prefix="reconcile_names_") as ws:
        return DirectBackend(models_dir, ws, fetch=None).metric_names()


class McpBackend:
    """Call the semantic tools the way an agent does, through a fastmcp Client."""

    def __init__(self, client: Any, workspace: str):
        self.client, self.workspace = client, workspace

    async def _call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.call_tool(tool, args, raise_on_error=False)
        text = "".join(getattr(c, "text", "") for c in result.content)
        try:
            body = json.loads(text)
        except ValueError:
            raise ReconcileError(f"{tool}: non-JSON result: {text[:300]}") from None
        if not isinstance(body, dict) or body.get("success") is not True:
            error = body.get("error", body) if isinstance(body, dict) else body
            raise ReconcileError(f"{tool}: {json.dumps(error, ensure_ascii=False)[:500]}")
        return body

    async def metric_names(self) -> set[str]:
        body = await self._call("list_metrics", {"workspace": self.workspace, "page_size": 100})
        meta = body.get("meta") or {}
        if meta.get("next_page_token"):
            raise ReconcileError(f"list_metrics: more than one page ({meta.get('total_count')} metrics)")
        return {m["name"] for m in body["data"]}

    async def query(self, case: Case) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"workspace": self.workspace, "metrics": list(case.metrics)}
        if case.group_by:
            args["group_by"] = list(case.group_by)
        if case.where:
            args["where"] = case.where
        return (await self._call("query_metric", args))["data"]["rows"]


async def reconcile(cases: Sequence[Case], query: Callable[[Case], Awaitable[list[dict[str, Any]]]],
                    reference: Callable[[Case], list[dict[str, Any]]], out: TextIO,
                    secrets: Iterable[str] = ()) -> int:
    """Run every case, print one line per case; returns the number of failed cases."""
    secrets = list(secrets)
    failed = 0
    for case in cases:
        want: list[dict[str, Any]] = []
        try:
            got = await query(case)
            want = reference(case)
            problems = compare(case, got, want)
        except (ReconcileError, pymysql.MySQLError) as e:
            problems = [f"{type(e).__name__}: {e}"]
        if problems:
            failed += 1
            print(f"FAIL  {case.name}: {len(problems)} problem(s)", file=out)
            for problem in problems[:MAX_PROBLEMS]:
                print(f"      {_mask(problem, secrets)}", file=out)
        else:
            print(f"ok    {case.name} ({len(want)} rows)", file=out)
    print(f"{len(cases) - failed}/{len(cases)} cases match", file=out)
    return failed


def _in_process_client(settings: Settings) -> Any:
    from fastmcp import Client

    from agentcore_ext.app import build_server

    return Client(build_server(settings))


async def _run_mcp(client: Any, models_dir: Path, workspace: str, cases: Sequence[Case],
                   reference: Callable[[Case], list[dict[str, Any]]], out: TextIO, secrets: Sequence[str]) -> int:
    expected = local_metric_names(models_dir)
    failed = 0
    async with client:
        backend = McpBackend(client, workspace)
        published = await backend.metric_names()
        if published == expected:
            print(f"published metrics: {len(published)} match {models_dir}", file=out)
        else:
            failed += 1
            print(f"FAIL  published metrics differ from {models_dir}: missing {sorted(expected - published)}, "
                  f"extra {sorted(published - expected)}", file=out)
        failed += await reconcile(cases, backend.query, reference, out, secrets)
    return failed


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None,
         connect: Callable[..., Any] = pymysql.connect, out: TextIO = sys.stdout, err: TextIO = sys.stderr,
         client_factory: Callable[[Settings], Any] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile ecom semantic metrics with the storyline SQL.")
    parser.add_argument("mode", choices=("direct", "mcp"))
    parser.add_argument("--models", type=Path, default=MODELS_DIR, help="local semantic YAML directory")
    parser.add_argument("--workspace", default="ecom", help="MCP workspace (mcp mode)")
    parser.add_argument("--case", action="append", default=[], help="run only this case (repeatable)")
    args = parser.parse_args(argv)

    cases = list(CASES)
    if args.case:
        unknown = sorted(set(args.case) - {c.name for c in CASES})
        if unknown:
            print(f"ERROR: unknown case(s): {', '.join(unknown)}", file=err)
            return 2
        cases = [c for c in CASES if c.name in args.case]
    try:
        settings = load_settings(os.environ if env is None else env)
    except SettingsError as e:
        print(f"ERROR: {e}", file=err)
        return 2
    secrets = [settings.doris_password, settings.doris_host]  # pymysql errors name the host
    try:
        conn = connect(host=settings.doris_host, port=settings.doris_port, user=settings.doris_user,
                       password=settings.doris_password, connect_timeout=10, read_timeout=120,
                       autocommit=True, cursorclass=pymysql.cursors.DictCursor)
    except pymysql.MySQLError as e:
        print(f"FAILED: connect: {_mask(str(e), secrets)}", file=err)
        return 1

    logging.disable(logging.WARNING)  # MetricFlow and the server are chatty below ERROR
    try:
        with tempfile.TemporaryDirectory(prefix="reconcile_") as tmp:
            def reference(case: Case) -> list[dict[str, Any]]:
                return fetch(conn, case.reference_sql)

            if args.mode == "direct":
                backend = DirectBackend(args.models, tmp, fetch=lambda sql: fetch(conn, sql))
                failed = asyncio.run(reconcile(cases, backend.query, reference, out, secrets))
            else:
                # A fresh workspace dir, so the server reads the published models from Doris, not a cache.
                client = (client_factory or _in_process_client)(dataclasses.replace(settings, workspace_dir=tmp))
                failed = asyncio.run(_run_mcp(client, args.models, args.workspace, cases, reference, out, secrets))
    except ReconcileError as e:
        print(f"FAILED: {_mask(str(e), secrets)}", file=err)
        return 1
    finally:
        conn.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 41 tests`、`OK`。

- [ ] **Step 9：用 `demo_ro` 对真实 Doris 对账（只读）**

`direct` 模式在本机编译 YAML，用 pymysql 执行编译出的 SELECT 和对照 SQL，不访问 `system_mcp`。

```bash
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_USER="$DORIS_RO_USER" DORIS_PASSWORD="$DORIS_RO_PASSWORD" AWS_REGION=us-east-1
  exec .venv/bin/python doris/reconcile.py direct )
echo "exit=$?"
```
期望（spec 阶段实测）：
```
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
参考数字（故事线，2026-01-01 ~ 2026-09-24）：GMV 65,442,236.24 / 订单 42,770 / 买家 20,187 / 优惠 4,430,032.46 / AOV 1530.10；华东 23,011,223.15 / 14,785 / 7,149 / AOV 1556.39；同比 2026-01 +53.25%、2026-06 +34.06%、2026-09 −0.44%；小程序占比 25.8% → 32.58%；故事 5.1 退款率 07 月 17.39%、08 月 22.08%。

- [ ] **Step 10：收尾**

勾选 T2.4；progress「当前状态」写 T2.4 完成、下一步 T2.5（GATE）；日志记录 Step 9 的结果。

```bash
bash scripts/check-secrets.sh
git add doris/semantic doris/test/test_semantic_models.py doris/reconcile.py doris/test/test_reconcile.py \
        specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "feat(p2): T2.4 ecom semantic models (10 files, 22 metrics) and storyline reconciliation (11/11 as demo_ro)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T2.5：以 root 发布 `ecom` 语义层（方案 C）

**Files:**
- Create：`doris/publish_semantic.py`、`doris/test/test_publish_semantic.py`、`doris/publish-semantic.sh`、`doris/test/test-publish-semantic.sh`
- Modify：`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：T2.4 的 `doris/semantic/ecom/`；upstream `store.store`：`DorisStore(workspace)`（`fetch(dir) -> StoreState`、`staging_list()`、`staging_discard()`、`staging_upsert(name, content)`、`staging_delete(name)`、`staging_fetch(dir)`、`staging_commit() -> StoreState`；`StoreState.semantic_version`）、`set_doris_endpoint(host, port)`、`set_request_credentials(user, password)`；`store.bootstrap.bootstrap_from_yaml`、`collect_physical_tables`、`pre_validate_physical(models_dir, db_host=, db_port=, db_user=, db_password=) -> (ok, error)`
- Produces：
  - `doris/publish_semantic.py`：`read_models(dir) -> dict[str, str]`、`offline_check(dir) -> list[str]`（指标名；失败时抛 `PublishError`）、`publish(store, local, out) -> int`、`main(argv, env, out, err, store_factory, physical_check) -> int`；exit 0 / 1（校验或数据库失败）/ 2（用法）。
  - `doris/publish-semantic.sh [--models DIR] [--workspace ecom]`：dry-run 默认；`APPLY=1` 发布。
  - Doris：库 `system_mcp`，表 `workspace_metadata`、`active_store_ecom`、`staging_store_ecom`；`ecom` 的 `semantic_version=2`（upstream 初始化时插入的元数据行是 1，第一次 commit 后是 2），10 个 active 文件。T2.3、T2.6 依赖这些。

- [ ] **Step 1：写失败测试 `doris/test/test_publish_semantic.py`**

假 store 按 upstream `DorisStore` 的 staging 语义实现（`store/store.py`）；离线校验真实运行。

```python
"""Offline tests for doris/publish_semantic.py (no Doris connection).

    .venv/bin/python -m unittest discover -s doris/test -v

The store is a fake with upstream DorisStore's staging semantics (store/store.py: fetch,
staging_list/discard/upsert/delete/fetch/commit); the offline model checks run for real.
The live publish is the T2.5 GATE step.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
sys.path.insert(0, str(ROOT / "doris"))

import pymysql  # noqa: E402

import publish_semantic  # noqa: E402
from publish_semantic import PublishError, offline_check, read_models  # noqa: E402
from store.store import StoreState  # noqa: E402

MODELS = ROOT / "doris" / "semantic" / "ecom"
PASSWORD = "RootPw0123456789abcXYZ"
ENV = {"DORIS_HOST": "10.0.0.1", "DORIS_PORT": "9030", "DORIS_ADMIN_USER": "root",
       "DORIS_ADMIN_PASSWORD": PASSWORD, "APPLY": "1"}
LOCAL = read_models(MODELS)


def setUpModule():
    logging.disable(logging.WARNING)  # MetricFlow logs parse errors at ERROR; the tests assert on them


def tearDownModule():
    logging.disable(logging.NOTSET)


class FakeStore:
    """In-memory DorisStore: active files, staging rows (action, content), semantic_version."""

    def __init__(self, active=None, staging=None, version=1, workspace="ecom"):
        self.workspace = workspace
        self.active = dict(active or {})
        self.staging = dict(staging or {})
        self.version = version
        self.calls = []

    @staticmethod
    def _write(local_dir, files):
        local_dir.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (local_dir / name).write_text(content, encoding="utf-8")

    def _state(self):
        return StoreState(revision=str(self.version), semantic_version=self.version)

    def fetch(self, local_dir):
        self.calls.append("fetch")
        self._write(local_dir, self.active)
        return self._state()

    def staging_list(self):
        self.calls.append("staging_list")
        return [{"filename": n, "action": a} for n, (a, _) in sorted(self.staging.items())]

    def staging_discard(self):
        self.calls.append("staging_discard")
        self.staging.clear()

    def staging_upsert(self, name, content):
        self.calls.append(("upsert", name))
        self.staging[name] = ("upsert", content)

    def staging_delete(self, name):
        self.calls.append(("delete", name))
        if name in self.staging:
            del self.staging[name]
            return "removed"
        if name in self.active:
            self.staging[name] = ("delete", None)
            return "staged"
        return "not_found"

    def _merged(self):
        merged = dict(self.active)
        for name, (action, content) in self.staging.items():
            if action == "delete":
                merged.pop(name, None)
            else:
                merged[name] = content
        return merged

    def staging_fetch(self, local_dir):
        self.calls.append("staging_fetch")
        self._write(local_dir, self._merged())
        return StoreState(revision="merged")

    def staging_commit(self):
        self.calls.append("staging_commit")
        if self.staging:
            self.active = self._merged()
            self.staging.clear()
            self.version += 1
        return self._state()

    def writes(self):
        return [c for c in self.calls if c not in ("fetch", "staging_list", "staging_fetch")]


def run_main(argv=(), env=ENV, store=None, physical=None):
    out, err, seen = io.StringIO(), io.StringIO(), {"factory": [], "physical": []}

    def factory(workspace):
        seen["factory"].append(workspace)
        return store

    def check(models_dir):
        seen["physical"].append((models_dir, len(seen["factory"])))
        return physical or (True, "")

    rc = publish_semantic.main(list(argv), env=env, out=out, err=err, store_factory=factory, physical_check=check)
    return rc, out.getvalue(), err.getvalue(), seen


def models_copy(test):
    tmp = Path(tempfile.mkdtemp(prefix="publish_models_"))
    test.addCleanup(shutil.rmtree, tmp, True)
    shutil.copytree(MODELS, tmp / "m")
    return tmp / "m"


class ReadModels(unittest.TestCase):
    def test_reads_every_yaml_file_by_name(self):
        self.assertEqual(sorted(LOCAL), sorted(p.name for p in MODELS.glob("*.yaml")))
        self.assertEqual(LOCAL["project.yaml"], (MODELS / "project.yaml").read_text(encoding="utf-8"))

    def test_ignores_non_yaml_files(self):
        m = models_copy(self)
        (m / "notes.txt").write_text("x", encoding="utf-8")
        self.assertEqual(read_models(m), LOCAL)


class OfflineCheck(unittest.TestCase):
    def test_returns_the_metric_names(self):
        self.assertEqual(len(offline_check(MODELS)), 22)
        self.assertIn("gmv_yoy", offline_check(MODELS))

    def test_duplicate_model_name_is_rejected(self):
        m = models_copy(self)
        shutil.copy(m / "shops.yaml", m / "shops_copy.yaml")
        with self.assertRaisesRegex(PublishError, "shops"):
            offline_check(m)

    def test_duplicate_measure_is_rejected(self):
        # Bootstrap and the engine accept it; MetricFlow would silently keep only one `gmv`.
        m = models_copy(self)
        refunds = m / "refunds.yaml"
        refunds.write_text(refunds.read_text(encoding="utf-8").replace("- name: refund_amount", "- name: gmv"),
                           encoding="utf-8")
        with self.assertRaisesRegex(PublishError, "Duplicate measure 'gmv'"):
            offline_check(m)

    def test_engine_init_failure_is_rejected(self):
        # Bootstrap accepts a measure model without agg_time_dimension; upstream validate_staging would
        # pass it and every query_metric on the workspace would then fail.
        m = models_copy(self)
        refunds = m / "refunds.yaml"
        text = refunds.read_text(encoding="utf-8")
        refunds.write_text(text.replace("  defaults:\n    agg_time_dimension: apply_date\n", ""), encoding="utf-8")
        self.assertNotEqual(refunds.read_text(encoding="utf-8"), text)
        with self.assertRaisesRegex(PublishError, "MetricFlow engine"):
            offline_check(m)

    def test_unparseable_models_are_rejected(self):
        m = models_copy(self)
        (m / "metrics.yaml").write_text("metric:\n  name: [unclosed\n", encoding="utf-8")
        with self.assertRaises(PublishError):
            offline_check(m)


class DryRun(unittest.TestCase):
    def test_dry_run_checks_offline_and_never_connects(self):
        env = {k: v for k, v in ENV.items() if k not in ("APPLY", "DORIS_ADMIN_PASSWORD")}
        rc, out, err, seen = run_main(env=env, store=FakeStore())
        self.assertEqual(rc, 0, err)
        self.assertEqual(seen, {"factory": [], "physical": []})
        self.assertIn("offline checks ok: 10 files, 22 metrics, 9 physical tables", out)
        self.assertIn("DRY-RUN: would publish workspace=ecom as root", out)
        self.assertIn("metrics.yaml", out)
        self.assertIn("APPLY=1 to publish", out)
        self.assertNotIn("10.0.0.1", out + err)

    def test_broken_models_fail_before_anything_else(self):
        m = models_copy(self)
        shutil.copy(m / "shops.yaml", m / "shops_copy.yaml")
        store = FakeStore()
        rc, _, err, seen = run_main(["--models", str(m)], store=store)
        self.assertEqual(rc, 1)
        self.assertIn("FAILED", err)
        self.assertEqual((seen["factory"], seen["physical"], store.calls), ([], [], []))

    def test_missing_or_empty_models_dir_is_a_usage_error(self):
        empty = Path(tempfile.mkdtemp(prefix="publish_empty_"))
        self.addCleanup(shutil.rmtree, empty, True)
        for models in (empty, empty / "nope"):
            with self.subTest(models=models):
                rc, _, err, _ = run_main(["--models", str(models)], store=FakeStore())
                self.assertEqual(rc, 2)
                self.assertIn("no YAML files", err)

    def test_workspace_must_be_an_identifier(self):
        # The name becomes part of table names: system_mcp.active_store_<workspace>.
        rc, _, err, seen = run_main(["--workspace", "ecom; DROP TABLE x"], store=FakeStore())
        self.assertEqual(rc, 2)
        self.assertIn("workspace", err)
        self.assertEqual(seen["factory"], [])


class Apply(unittest.TestCase):
    def test_first_publish_uploads_every_file_and_bumps_the_version(self):
        store = FakeStore()
        rc, out, err, seen = run_main(store=store)
        self.assertEqual(rc, 0, err)
        self.assertEqual(store.active, LOCAL)
        self.assertEqual(store.version, 2)
        self.assertEqual(seen["factory"], ["ecom"])
        self.assertIn("published workspace=ecom semantic_version=2", out)
        self.assertIn("+10 ~0 -0", out)

    def test_physical_check_runs_before_the_store_is_opened(self):
        # DorisStore('ecom') already writes (CREATE TABLE IF NOT EXISTS + metadata row).
        _, _, _, seen = run_main(store=FakeStore())
        self.assertEqual(seen["physical"], [(MODELS, 0)])

    def test_staging_is_discarded_before_upserts_and_committed_last(self):
        store = FakeStore(staging={"junk.yaml": ("upsert", "semantic_model: {}")})
        rc, _, err, _ = run_main(store=store)
        self.assertEqual(rc, 0, err)
        writes = store.writes()
        self.assertEqual(writes[0], "staging_discard")
        self.assertEqual(writes[-1], "staging_commit")
        self.assertNotIn("junk.yaml", store.active)

    def test_changed_and_stale_remote_files_are_replaced_and_deleted(self):
        active = dict(LOCAL, **{"old.yaml": "semantic_model: {}", "shops.yaml": "stale"})
        store = FakeStore(active=active, version=5)
        rc, out, err, _ = run_main(store=store)
        self.assertEqual(rc, 0, err)
        self.assertEqual(store.active, LOCAL)
        self.assertIn(("delete", "old.yaml"), store.calls)
        self.assertIn("published workspace=ecom semantic_version=6", out)
        self.assertIn("+0 ~1 -1", out)

    def test_up_to_date_store_is_left_alone(self):
        store = FakeStore(active=LOCAL, version=7)
        rc, out, err, _ = run_main(store=store)
        self.assertEqual(rc, 0, err)
        self.assertEqual(store.writes(), [])
        self.assertIn("up to date: workspace=ecom semantic_version=7", out)

    def test_leftover_staging_is_not_up_to_date(self):
        # Someone's pending rows would be committed by the next Web UI commit: clear them via a full publish.
        store = FakeStore(active=LOCAL, staging={"junk.yaml": ("upsert", "semantic_model: {}")}, version=4)
        rc, out, err, _ = run_main(store=store)
        self.assertEqual(rc, 0, err)
        self.assertEqual((store.active, store.staging, store.version), (LOCAL, {}, 5))
        self.assertIn("published workspace=ecom semantic_version=5", out)

    def test_failed_physical_check_stops_before_any_write(self):
        store = FakeStore()
        rc, _, err, seen = run_main(store=store, physical=(False, "Table internal.ecom.dim_brand: 1142 denied"))
        self.assertEqual(rc, 1)
        self.assertIn("dim_brand", err)
        self.assertEqual((seen["factory"], store.calls), ([], []))

    def test_merged_staging_must_equal_the_local_models(self):
        class DroppingStore(FakeStore):  # like upstream push, which silently skips files
            def staging_upsert(self, name, content):
                if name != "metrics.yaml":
                    super().staging_upsert(name, content)

        store = DroppingStore()
        rc, _, err, _ = run_main(store=store)
        self.assertEqual(rc, 1)
        self.assertIn("metrics.yaml", err)
        self.assertNotIn("staging_commit", store.calls)
        self.assertEqual((store.staging, store.calls[-1]), ({}, "staging_discard"))

    def test_active_must_equal_the_local_models_after_commit(self):
        class LossyStore(FakeStore):
            def staging_commit(self):
                self.calls.append("staging_commit")
                self.staging.clear()
                self.version += 1
                return self._state()

        rc, _, err, _ = run_main(store=LossyStore())
        self.assertEqual(rc, 1)
        self.assertIn("after commit", err)

    def test_semantic_version_must_advance(self):
        # ensure_fresh on the MCP side only reloads when semantic_version changes.
        class StuckStore(FakeStore):
            def staging_commit(self):
                version = self.version
                state = super().staging_commit()
                self.version = version
                return StoreState(revision=str(version), semantic_version=version)

        rc, _, err, _ = run_main(store=StuckStore(version=3))
        self.assertEqual(rc, 1)
        self.assertIn("semantic_version did not advance", err)

    def test_missing_environment_is_a_usage_error(self):
        for key in ("DORIS_HOST", "DORIS_ADMIN_USER", "DORIS_ADMIN_PASSWORD"):
            with self.subTest(missing=key):
                env = {k: v for k, v in ENV.items() if k != key}
                rc, _, err, seen = run_main(env=env, store=FakeStore())
                self.assertEqual(rc, 2)
                self.assertIn(key, err)
                self.assertEqual(seen["physical"], [])

    def test_database_errors_are_masked(self):
        class DeniedStore(FakeStore):
            def staging_discard(self):
                raise pymysql.OperationalError(2003, f"Can't connect to MySQL server on '10.0.0.1' ({PASSWORD})")

        rc, out, err, _ = run_main(store=DeniedStore())
        self.assertEqual(rc, 1)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("10.0.0.1", out + err)
        self.assertIn("***", err)


class Wiring(unittest.TestCase):
    def test_default_store_and_physical_check_use_the_admin_connection(self):
        store = FakeStore()
        with mock.patch.object(publish_semantic, "set_doris_endpoint") as endpoint, \
                mock.patch.object(publish_semantic, "set_request_credentials") as creds, \
                mock.patch.object(publish_semantic, "DorisStore", return_value=store) as doris_store, \
                mock.patch.object(publish_semantic, "pre_validate_physical", return_value=(True, "")) as physical:
            rc = publish_semantic.main([], env=ENV, out=io.StringIO(), err=io.StringIO())
        self.assertEqual(rc, 0)
        endpoint.assert_called_once_with("10.0.0.1", 9030)
        creds.assert_called_once_with("root", PASSWORD)
        doris_store.assert_called_once_with("ecom")
        physical.assert_called_once_with(MODELS, db_host="10.0.0.1", db_port=9030, db_user="root",
                                         db_password=PASSWORD)

    def test_never_runs_upstream_grant_or_commit_hooks(self):
        # upstream commit_staging GRANTs SELECT_PRIV on system_mcp.* and every model table TO '%'.
        source = Path(publish_semantic.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"grant_select_on_physical_tables|grant_workspace_access|commit_staging\(",
                                    source))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 42 tests`、`FAILED (errors=1)`，报错是 `ModuleNotFoundError: No module named 'publish_semantic'`。

- [ ] **Step 3：写 `doris/publish_semantic.py`**

```python
"""Publish the ecom semantic models to the Doris semantic store (P2 / T2.5; design §6.3, plan C).

Normally invoked through doris/publish-semantic.sh, which supplies the environment:
    python doris/publish_semantic.py [--models DIR] [--workspace ecom]           # dry-run: offline only
    APPLY=1 python doris/publish_semantic.py [--models DIR] [--workspace ecom]   # GATE: publish as admin

env    DORIS_HOST, DORIS_PORT (9030), DORIS_ADMIN_USER, DORIS_ADMIN_PASSWORD (APPLY=1 only); APPLY=1 publishes
Runs upstream's store layer in-process: no MCP server, no admin-role check and none of upstream
commit_staging's follow-ups (reload, GRANT SELECT_PRIV ... TO '%'). The gate mirrors upstream
validate_staging and adds the engine check it skips: the models must bootstrap, initialise the
MetricFlow engine, have no duplicate model/measure names and pass pre_validate_physical (DESCRIBE);
the merged active+staging set must equal the local files before staging_commit, and the active
set must equal them afterwards. Exit 0 ok (published or up to date), 1 failure, 2 usage/configuration.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
MODELS_DIR = ROOT / "doris" / "semantic" / "ecom"

import pymysql  # noqa: E402

from store.bootstrap import bootstrap_from_yaml, collect_physical_tables, pre_validate_physical  # noqa: E402
from store.compiler import MetricFlowCompiler  # noqa: E402
from store.manifest import SemanticManifest  # noqa: E402
from store.store import DorisStore, set_doris_endpoint, set_request_credentials  # noqa: E402
from store.watcher import _check_staging_duplicates  # noqa: E402

MASK = "***"
_WORKSPACE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")  # upstream workspace/create rule


class PublishError(RuntimeError):
    """The models or the store failed a check; messages never contain secret values."""


def read_models(models_dir: Path) -> dict[str, str]:
    """{relative name: text} of every *.yml / *.yaml file under models_dir (empty if it does not exist)."""
    if not models_dir.is_dir():
        return {}
    return {p.relative_to(models_dir).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(models_dir.rglob("*")) if p.suffix in (".yml", ".yaml") and p.is_file()}


def offline_check(models_dir: Path) -> list[str]:
    """Upstream's validate gate plus the engine init it skips; returns the sorted metric names."""
    errors, _warnings = _check_staging_duplicates(models_dir)
    if errors:
        raise PublishError(errors[0])
    with tempfile.TemporaryDirectory(prefix="publish_ws_") as tmp:
        ws = Path(tmp)
        ok, error = bootstrap_from_yaml(models_dir, ws)
        if not ok:
            raise PublishError(f"bootstrap: {error}")
        compiler = MetricFlowCompiler(ws)
        if not compiler.is_engine_mode:
            raise PublishError(f"MetricFlow engine: {compiler.init_error}")
        manifest = SemanticManifest(ws / "target" / "semantic_manifest.json")
        return sorted(m["name"] for m in manifest.list_metrics())


def _differing(a: Mapping[str, str], b: Mapping[str, str]) -> list[str]:
    return sorted(n for n in a.keys() | b.keys() if a.get(n) != b.get(n))


def publish(store: Any, local: Mapping[str, str], out: TextIO) -> int:
    """Make the store's active models equal `local`; returns the published semantic_version."""
    with tempfile.TemporaryDirectory(prefix="publish_") as tmp:
        before = store.fetch(Path(tmp, "active"))
        remote = read_models(Path(tmp, "active"))
        pending = store.staging_list()
        added = sorted(local.keys() - remote.keys())
        removed = sorted(remote.keys() - local.keys())
        changed = sorted(n for n in local.keys() & remote.keys() if local[n] != remote[n])
        print(f"remote: semantic_version={before.semantic_version}, {len(remote)} files; "
              f"staging: {len(pending)} rows", file=out)
        if not (added or changed or removed or pending):
            print(f"up to date: workspace={store.workspace} semantic_version={before.semantic_version}", file=out)
            return before.semantic_version
        print(f"plan: add {added}, change {changed}, remove {removed}", file=out)

        store.staging_discard()
        for name in sorted(local):
            store.staging_upsert(name, local[name])
        for name in removed:
            store.staging_delete(name)
        store.staging_fetch(Path(tmp, "merged"))
        differing = _differing(read_models(Path(tmp, "merged")), local)
        if differing:
            store.staging_discard()
            raise PublishError(f"merged staging differs from the local models in {differing}; staging discarded")
        after = store.staging_commit()

        store.fetch(Path(tmp, "published"))
        differing = _differing(read_models(Path(tmp, "published")), local)
        if differing:
            raise PublishError(f"active models differ from the local models after commit in {differing}")
    if after.semantic_version <= before.semantic_version:
        raise PublishError(f"semantic_version did not advance ({before.semantic_version} -> "
                           f"{after.semantic_version})")
    print(f"published workspace={store.workspace} semantic_version={after.semantic_version} "
          f"({len(local)} files: +{len(added)} ~{len(changed)} -{len(removed)})", file=out)
    return after.semantic_version


def _doris_store(workspace: str, *, host: str, port: int, user: str, password: str) -> DorisStore:
    set_doris_endpoint(host, port)
    set_request_credentials(user, password)  # store connections run as the admin, updated_by = admin
    return DorisStore(workspace)  # CREATE DATABASE/TABLE IF NOT EXISTS + metadata row


def _mask(text: str, secrets: Sequence[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, MASK)
    return text


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None,
         out: TextIO = sys.stdout, err: TextIO = sys.stderr,
         store_factory: Callable[[str], Any] | None = None,
         physical_check: Callable[[Path], tuple[bool, str]] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish semantic models to the Doris semantic store.")
    parser.add_argument("--models", type=Path, default=MODELS_DIR, help="local semantic YAML directory")
    parser.add_argument("--workspace", default="ecom", help="semantic workspace")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env

    if not _WORKSPACE_RE.match(args.workspace):
        print(f"ERROR: workspace must match {_WORKSPACE_RE.pattern}", file=err)
        return 2
    local = read_models(args.models)
    if not local:
        print(f"ERROR: no YAML files in {args.models}", file=err)
        return 2

    logging.disable(logging.WARNING)  # MetricFlow and the store are chatty below ERROR
    try:
        metrics = offline_check(args.models)
        tables = collect_physical_tables(args.models)
    except PublishError as e:
        print(f"FAILED: offline checks: {e}", file=err)
        return 1
    print(f"offline checks ok: {len(local)} files, {len(metrics)} metrics, {len(tables)} physical tables "
          "(bootstrap, MetricFlow engine, duplicate names)", file=out)

    admin = env.get("DORIS_ADMIN_USER") or "<admin>"
    if env.get("APPLY") != "1":
        ws = args.workspace
        print(f"DRY-RUN: would publish workspace={ws} as {admin}:", file=out)
        for name, text in local.items():
            data = text.encode("utf-8")
            print(f"  file: {name} ({len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()[:12]})", file=out)
        print(f"  1. pre_validate_physical: DESCRIBE the {len(tables)} physical tables, check column exprs", file=out)
        print(f"  2. DorisStore('{ws}'): CREATE DATABASE/TABLE IF NOT EXISTS "
              f"system_mcp.{{workspace_metadata,active_store_{ws},staging_store_{ws}}}", file=out)
        print(f"  3. compare active_store_{ws} with the local files; stop if equal and staging is empty", file=out)
        print(f"  4. staging: discard, upsert {len(local)} files, delete remote files not in {args.models}", file=out)
        print("  5. merged staging == local -> staging_commit (semantic_version + 1) -> active == local", file=out)
        print("DRY-RUN: no GRANT is executed; APPLY=1 to publish", file=out)
        return 0

    missing = [k for k in ("DORIS_HOST", "DORIS_ADMIN_USER", "DORIS_ADMIN_PASSWORD") if not env.get(k)]
    if missing:
        print(f"ERROR: missing environment: {', '.join(missing)}", file=err)
        return 2
    host, port = env["DORIS_HOST"], int(env.get("DORIS_PORT") or 9030)
    password = env["DORIS_ADMIN_PASSWORD"]
    connection = {"host": host, "port": port, "user": admin, "password": password}
    factory = store_factory or functools.partial(_doris_store, **connection)
    physical = physical_check or functools.partial(
        pre_validate_physical, db_host=host, db_port=port, db_user=admin, db_password=password)
    try:
        ok, error = physical(args.models)
        if not ok:
            raise PublishError(f"physical check: {error}")
        print(f"physical check ok: {len(tables)} tables and their column exprs exist", file=out)
        publish(factory(args.workspace), local, out)
    except (RuntimeError, OSError, pymysql.MySQLError) as e:
        print(f"FAILED: {_mask(str(e), [password, host])}", file=err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 66 tests`、`OK`。

- [ ] **Step 5：写失败测试 `doris/test/test-publish-semantic.sh`**

假的 credentials 文件 + 假的 python 记录收到的环境变量；最后用真的 python 跑一次端到端 dry-run。

```bash
#!/usr/bin/env bash
# Offline tests for doris/publish-semantic.sh: fake credentials file, stub python.
# Checks what reaches the python process (env names, argv); no Doris.
#   bash doris/test/test-publish-semantic.sh
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/publish-semantic.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
# Stub python: records argv and the names of DORIS_* / APPLY env vars (values only for non-secrets).
cat > "$TMP/bin/stub-python" <<'STUB'
#!/usr/bin/env bash
{ echo "argv: $*"
  for v in $(compgen -e | grep -E '^(DORIS_|APPLY$)' | sort); do
    case "$v" in *PASSWORD*) echo "env: $v=<set>" ;; *) echo "env: $v=${!v}" ;; esac
  done; } > "$STUB_OUT"
STUB
chmod +x "$TMP/bin/stub-python"
printf '%s\n' 'DORIS_HOST=198.51.100.7' 'DORIS_MYSQL_PORT=9030' 'DORIS_HTTP_PORT=8030' \
  'DORIS_ROOT_USER=root' 'DORIS_ROOT_PASSWORD=RootPw0123456789' \
  'DORIS_RO_USER=demo_ro' 'DORIS_RO_PASSWORD=RoPw0123456789' > "$TMP/cred.env"

FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
run_wrapper() { # APPLY [ARGS...] → sets RC, REC (what the stub saw)
  local apply="$1"; shift
  : > "$TMP/stub.out"
  env -u DORIS_HOST -u DORIS_ROOT_PASSWORD -u DORIS_RO_PASSWORD STUB_OUT="$TMP/stub.out" \
    PYTHON_BIN="$TMP/bin/stub-python" DORIS_CRED_FILE="$TMP/cred.env" APPLY="$apply" \
    bash "$SCRIPT" "$@" > "$TMP/out.txt" 2>&1
  RC=$?; REC="$(cat "$TMP/stub.out")"
}
has() { [[ "$1" == *"$2"* ]] && echo yes || echo no; }

run_wrapper 0 --workspace ecom
check "dry-run: exit 0" 0 "$RC"
check "dry-run: runs publish_semantic.py with the arguments" yes \
  "$(has "$REC" "doris/publish_semantic.py --workspace ecom")"
check "dry-run: host, port and admin user exported" "yes|yes|yes" \
  "$(has "$REC" "env: DORIS_HOST=198.51.100.7")|$(has "$REC" "env: DORIS_PORT=9030")|$(has "$REC" "env: DORIS_ADMIN_USER=root")"
check "dry-run: admin password NOT exported" no "$(has "$REC" "DORIS_ADMIN_PASSWORD")"
check "dry-run: APPLY=0 reaches python" yes "$(has "$REC" "env: APPLY=0")"
check "never exports root/ro variables by their original names" "no|no" \
  "$(has "$REC" "DORIS_ROOT_")|$(has "$REC" "DORIS_RO_")"

run_wrapper 1
check "apply: admin password exported" yes "$(has "$REC" "env: DORIS_ADMIN_PASSWORD=<set>")"
check "apply: APPLY=1 reaches python" yes "$(has "$REC" "env: APPLY=1")"

run_wrapper ""
check "APPLY unset behaves as dry-run" "yes|no" "$(has "$REC" "env: APPLY=0")|$(has "$REC" "DORIS_ADMIN_PASSWORD")"

# End to end with the real publish_semantic.py (dry-run never connects).
REAL_PY="${REAL_PYTHON_BIN:-$(cd "$(dirname "$SCRIPT")/.." && pwd)/.venv/bin/python}"
E2E="$(env -u DORIS_ROOT_PASSWORD PYTHON_BIN="$REAL_PY" DORIS_CRED_FILE="$TMP/cred.env" APPLY=0 bash "$SCRIPT" 2>&1)"
check "e2e dry-run: offline checks pass" yes "$(has "$E2E" "offline checks ok: 10 files, 22 metrics, 9 physical tables")"
check "e2e dry-run: plan names the admin and the workspace" yes "$(has "$E2E" "DRY-RUN: would publish workspace=ecom as root")"
check "e2e dry-run: no secret or host in output" "no|no|no" \
  "$(has "$E2E" "RootPw0123")|$(has "$E2E" "RoPw0123")|$(has "$E2E" "198.51.100.7")"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
```

- [ ] **Step 6：运行测试，确认失败**

```bash
bash doris/test/test-publish-semantic.sh 2>&1 | tail -1
```
期望：`9 failed`（wrapper 还不存在）。

- [ ] **Step 7：写 `doris/publish-semantic.sh`**

```bash
#!/usr/bin/env bash
# P2 / T2.5 — publish doris/semantic/ecom to the Doris semantic store (system_mcp, workspace ecom) as root.
#   bash doris/publish-semantic.sh [--models DIR] [--workspace ecom]           # dry-run: offline checks + plan
#   APPLY=1 bash doris/publish-semantic.sh [--models DIR] [--workspace ecom]   # GATE: only after the user confirms
# credentials.env is sourced in a subshell; only host/port, the admin user and (APPLY=1 only) the admin
# password are exported, under new names, to the python process.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CRED="${DORIS_CRED_FILE:-/home/ubuntu/AI-code/Doris-test/credentials.env}"
PY="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
export APPLY="${APPLY:-0}"

( source "$CRED"
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_ADMIN_USER="$DORIS_ROOT_USER"
  [[ "$APPLY" == "1" ]] && export DORIS_ADMIN_PASSWORD="$DORIS_ROOT_PASSWORD"
  exec "$PY" "$ROOT/doris/publish_semantic.py" "$@" )
```

- [ ] **Step 8：运行测试，确认通过**

```bash
bash doris/test/test-publish-semantic.sh 2>&1 | tail -1   # 期望：all passed（12 项）
```

- [ ] **Step 9：dry-run（不连 Doris）**

```bash
bash doris/publish-semantic.sh
```
期望：
```
offline checks ok: 10 files, 22 metrics, 9 physical tables (bootstrap, MetricFlow engine, duplicate names)
DRY-RUN: would publish workspace=ecom as root:
  file: brands.yaml (453 bytes, sha256 …)
  …（按文件名排序，共 10 行：brands 453、categories 705、metrics 4297、order_items 1512、orders 2308、project 324、refunds 1528、regions 782、reviews 1151、shops 629 字节）
  1. pre_validate_physical: DESCRIBE the 9 physical tables, check column exprs
  2. DorisStore('ecom'): CREATE DATABASE/TABLE IF NOT EXISTS system_mcp.{workspace_metadata,active_store_ecom,staging_store_ecom}
  3. compare active_store_ecom with the local files; stop if equal and staging is empty
  4. staging: discard, upsert 10 files, delete remote files not in /home/ubuntu/AI-code/Doris-mcp-skill-Demo/doris/semantic/ecom
  5. merged staging == local -> staging_commit (semantic_version + 1) -> active == local
DRY-RUN: no GRANT is executed; APPLY=1 to publish
```

- [ ] **Step 10：GATE —— 展示并等待确认**

向用户展示 Step 9 的输出，并说明：
- 以 root 连 Doris，先 DESCRIBE 9 张物理表（只读）；
- upstream `DorisStore('ecom')` 会创建库 `system_mcp` 和 3 张表 `workspace_metadata`、`active_store_ecom`、`staging_store_ecom`，并插入 `ecom` 的元数据行（`semantic_version=1`）；
- 写入 10 行 staging，commit 后 active 有 10 个文件，`semantic_version` 变为 2；
- **不执行任何 GRANT**（不调用 upstream `commit_staging`）；不修改 `ecom` 库；
- 回滚（也需要 GATE）：root 执行 `DROP DATABASE system_mcp`（本阶段之前它不存在）。

用户明确确认后执行：
```bash
APPLY=1 bash doris/publish-semantic.sh
```
期望：
```
offline checks ok: 10 files, 22 metrics, 9 physical tables (bootstrap, MetricFlow engine, duplicate names)
physical check ok: 9 tables and their column exprs exist
remote: semantic_version=1, 0 files; staging: 0 rows
plan: add ['brands.yaml', 'categories.yaml', 'metrics.yaml', 'order_items.yaml', 'orders.yaml', 'project.yaml', 'refunds.yaml', 'regions.yaml', 'reviews.yaml', 'shops.yaml'], change [], remove []
published workspace=ecom semantic_version=2 (10 files: +10 ~0 -0)
```
退出码 0。发布后的内容在 T2.3（`semantic store` 检查）和 T2.6（`published metrics: 22 match …`）里以 `mcp_svc` 身份复核。

- [ ] **Step 11：收尾**

勾选 T2.5；progress「当前状态」写 T2.5 完成、下一步 T2.2（GATE），「Doris 变更」写 `system_mcp` 库 + 3 张表，`ecom` semantic_version=2；日志记录 Step 10 的实际输出。

```bash
bash scripts/check-secrets.sh
git add doris/publish_semantic.py doris/test/test_publish_semantic.py doris/publish-semantic.sh \
        doris/test/test-publish-semantic.sh specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "feat(p2): T2.5 publish the ecom semantic layer in-process as root (plan C, no GRANT)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T2.2：以 root 创建 `mcp_svc` 并授权

**Files:**
- Create：`doris/admin_sql.py`、`doris/test/test_admin_sql.py`、`doris/01_mcp_user.sql`、`doris/test/test_mcp_user_sql.py`、`doris/apply-admin-sql.sh`、`doris/test/test-apply-admin-sql.sh`
- Modify：`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：T2.1 的 secret `doris-mcp/mcp_svc`（SecretString JSON，经 stdin 传入）
- Produces：
  - `doris/admin_sql.py FILE.sql`（stdin = SecretString）：`load_statements(text) -> list[str]`、`render(statements, values) -> list[str]`（白名单外的语句、未知占位符都抛 `AdminSqlError`）、`main(argv, stdin, env, connect, out, err) -> int`；dry-run 打印 `DRY-RUN SQL: …`（密码显示为 `***`），`APPLY=1` 执行后打印 `SHOW GRANTS`。
  - `doris/01_mcp_user.sql`：4 条语句，只含占位符 `${MCP_SVC_PASSWORD}`。
  - `doris/apply-admin-sql.sh FILE.sql`：secret → 管道 → `admin_sql.py`。
  - Doris：用户 `'mcp_svc'@'%'`，权限 = R-42。T2.3、T2.6、P3 用它。

- [ ] **Step 1：写失败测试 `doris/test/test_admin_sql.py`**

```python
"""Offline tests for doris/admin_sql.py (no Doris connection; a fake connect() records statements).

    .venv/bin/python -m unittest discover -s doris/test -v
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import admin_sql  # noqa: E402

PW = "Abc123def456GHI789jkl012MNO345pq"
SECRET = json.dumps({"username": "mcp_svc", "password": PW})
ENV = {"DORIS_HOST": "10.0.0.1", "DORIS_PORT": "9030", "DORIS_ADMIN_USER": "root", "DORIS_ADMIN_PASSWORD": "rootpw-xyz"}
SQL = """-- header comment
CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%';
"""


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, stmt):
        self.conn.executed.append(stmt)
        if self.conn.fail_on and self.conn.fail_on in stmt:
            raise admin_sql.pymysql.MySQLError(1105, f"errCode = 2, detailMessage = bad statement: {stmt}")

    def fetchall(self):
        return (("'mcp_svc'@'%'", "Yes", "internal.ecom: Select_priv"),)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, fail_on=None):
        self.executed: list[str] = []
        self.fail_on = fail_on
        self.kwargs = {}

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass


def run(sql=SQL, secret=SECRET, env=None, apply=False, fail_on=None, connect_error=None):
    env = dict(ENV if env is None else env)
    if apply:
        env["APPLY"] = "1"
    conn = FakeConn(fail_on)

    def connect(**kwargs):
        conn.kwargs = kwargs
        if connect_error:
            raise connect_error
        return conn

    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
        f.write(sql)
    out, err = io.StringIO(), io.StringIO()
    rc = admin_sql.main([f.name], stdin=io.StringIO(secret), env=env, connect=connect, out=out, err=err)
    Path(f.name).unlink()
    return rc, out.getvalue() + err.getvalue(), conn


class LoadStatements(unittest.TestCase):
    def test_splits_on_semicolons_and_drops_comment_lines(self):
        stmts = admin_sql.load_statements(SQL)
        self.assertEqual(len(stmts), 3)
        self.assertTrue(stmts[0].startswith("CREATE USER IF NOT EXISTS"))
        self.assertFalse(any("header comment" in s for s in stmts))


class Render(unittest.TestCase):
    def test_unknown_placeholder_is_an_error(self):
        with self.assertRaises(admin_sql.AdminSqlError):
            admin_sql.render(["ALTER USER 'x'@'%' IDENTIFIED BY '${OTHER}'"], {"MCP_SVC_PASSWORD": PW})

    def test_statement_outside_the_allowlist_is_rejected(self):
        for stmt in ("DROP USER 'mcp_svc'@'%'", "SET GLOBAL enable_profile = true", "SELECT 1",
                     "GRANT ADMIN_PRIV ON *.*.* TO 'mcp_svc'@'%'", "GRANT SELECT_PRIV ON *.*.* TO 'mcp_svc'@'%'"):
            with self.subTest(stmt=stmt), self.assertRaises(admin_sql.AdminSqlError):
                admin_sql.render([stmt], {})


class Main(unittest.TestCase):
    def test_dry_run_prints_masked_statements_and_never_connects(self):
        rc, output, conn = run()
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN SQL: CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '***'", output)
        self.assertNotIn(PW, output)
        self.assertEqual(conn.executed, [])

    def test_apply_executes_rendered_statements_then_shows_grants(self):
        rc, output, conn = run(apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(len(conn.executed), 4)
        # Filled in memory (a literal password after IDENTIFIED BY would trip scripts/check-secrets.sh).
        self.assertEqual(conn.executed[0], admin_sql.load_statements(SQL)[0].replace("${MCP_SVC_PASSWORD}", PW))
        self.assertEqual(conn.executed[-1], "SHOW GRANTS FOR 'mcp_svc'@'%'")
        self.assertEqual(conn.kwargs["user"], "root")
        self.assertEqual(conn.kwargs["password"], "rootpw-xyz")
        self.assertNotIn(PW, output)
        self.assertNotIn("rootpw-xyz", output)

    def test_error_messages_are_masked_and_execution_stops(self):
        rc, output, conn = run(apply=True, fail_on="ALTER USER")
        self.assertEqual(rc, 1)
        self.assertEqual(len(conn.executed), 2)
        self.assertIn("FAILED", output)
        self.assertNotIn(PW, output)

    def test_connect_errors_hide_the_host_and_both_passwords(self):
        error = admin_sql.pymysql.MySQLError(2003, f"Can't connect to MySQL server on '10.0.0.1' (rootpw-xyz {PW})")
        rc, output, conn = run(apply=True, connect_error=error)
        self.assertEqual(rc, 1)
        for secret in ("10.0.0.1", "rootpw-xyz", PW):
            self.assertNotIn(secret, output)
        self.assertIn("***", output)
        self.assertEqual(conn.executed, [])

    def test_secret_username_must_match_the_sql(self):
        rc, output, conn = run(secret=json.dumps({"username": "someone", "password": PW}), apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("mcp_svc", output)
        self.assertEqual(conn.executed, [])

    def test_password_that_needs_quoting_is_refused(self):
        for bad in ("short1", "has'quote0123456789", "back\\slash0123456789", "sp ace0123456789abc"):
            with self.subTest(bad=bad):
                rc, output, conn = run(secret=json.dumps({"username": "mcp_svc", "password": bad}), apply=True)
                self.assertEqual(rc, 2)
                self.assertNotIn(bad, output)
                self.assertEqual(conn.executed, [])

    def test_malformed_secret_is_refused(self):
        rc, output, _ = run(secret="not json", apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("username", output)

    def test_missing_admin_credentials_is_refused(self):
        env = {k: v for k, v in ENV.items() if k != "DORIS_ADMIN_PASSWORD"}
        rc, output, conn = run(env=env, apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("DORIS_ADMIN_PASSWORD", output)
        self.assertEqual(conn.executed, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 67 tests`、`FAILED (errors=1)`，报错是 `ModuleNotFoundError: No module named 'admin_sql'`。

- [ ] **Step 3：写 `doris/admin_sql.py`**

```python
"""Run a doris/*.sql account script as the Doris admin (design §6.1, P2 / T2.2).

Normally invoked through doris/apply-admin-sql.sh, which supplies stdin and the environment:
    <SecretString on stdin> | [APPLY=1] python doris/admin_sql.py doris/01_mcp_user.sql

stdin  Secrets Manager SecretString {"username": ..., "password": ...} of the service account
env    DORIS_HOST, DORIS_PORT (9030), DORIS_ADMIN_USER, DORIS_ADMIN_PASSWORD; APPLY=1 executes
The SQL may reference ${MCP_SVC_PASSWORD}; it is filled in memory only. Dry-run (default) prints the
statements with the password masked and never connects. Only account statements for the secret's
user are accepted: CREATE USER IF NOT EXISTS / ALTER USER ... IDENTIFIED BY / GRANT of SELECT_PRIV
and CREATE_PRIV on a single internal database.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO

import pymysql

MASK = "***"
_PASSWORD_RE = re.compile(r"^[A-Za-z0-9]{16,128}$")
_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z_]+)\}")
_IDENT = r"(?P<ident>'(?P<user>[a-z_][a-z0-9_]*)'@'[0-9.%]+')"
_PRIV = r"(?:SELECT_PRIV|CREATE_PRIV)"
_ALLOWED = (
    re.compile(rf"^CREATE USER IF NOT EXISTS {_IDENT} IDENTIFIED BY '[^']*'$"),
    re.compile(rf"^ALTER USER {_IDENT} IDENTIFIED BY '[^']*'$"),
    re.compile(rf"^GRANT {_PRIV}(?:, {_PRIV})* ON internal\.[a-z_][a-z0-9_]*\.\* TO {_IDENT}$"),
)


class AdminSqlError(ValueError):
    """Rejected input; messages never contain secret values."""


def load_statements(text: str) -> list[str]:
    """Split on ';', drop '--' comment lines, collapse whitespace."""
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    return [" ".join(part.split()) for part in body.split(";") if part.strip()]


def _match(stmt: str) -> re.Match[str]:
    for pattern in _ALLOWED:
        m = pattern.match(stmt)
        if m:
            return m
    raise AdminSqlError(f"statement not allowed: {stmt}")


def render(statements: Sequence[str], values: Mapping[str, str]) -> list[str]:
    """Check every statement against the allowlist, then fill ${NAME} placeholders."""

    def fill(m: re.Match[str]) -> str:
        if m.group(1) not in values:
            raise AdminSqlError(f"unknown placeholder ${{{m.group(1)}}}")
        return values[m.group(1)]

    return [_PLACEHOLDER_RE.sub(fill, stmt) for stmt in statements if _match(stmt)]


def _read_secret(raw: str) -> tuple[str, str]:
    try:
        doc = json.loads(raw)
        user, password = doc["username"], doc["password"]
    except (ValueError, TypeError, KeyError):
        raise AdminSqlError("stdin must be the secret JSON with 'username' and 'password'") from None
    if not isinstance(user, str) or not isinstance(password, str) or not _PASSWORD_RE.match(password):
        raise AdminSqlError("the secret's password must be 16-128 letters/digits (see infra/40-doris-secret.sh)")
    return user, password


def _mask(text: str, secrets: Sequence[str]) -> str:
    for s in secrets:
        text = text.replace(s, MASK)
    return text


def main(
    argv: Sequence[str],
    stdin: TextIO = sys.stdin,
    env: Mapping[str, str] = os.environ,
    connect: Callable[..., Any] = pymysql.connect,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
) -> int:
    if len(argv) != 1:
        print("usage: <secret JSON on stdin> | [APPLY=1] python doris/admin_sql.py FILE.sql", file=err)
        return 2
    try:
        statements = load_statements(Path(argv[0]).read_text(encoding="utf-8"))
        matches = [_match(s) for s in statements]
        user, password = _read_secret(stdin.read())
        targets = {m.group("user") for m in matches}
        if targets != {user}:
            raise AdminSqlError(f"the SQL targets {sorted(targets)} but the secret is for {user!r}")
        rendered = render(statements, {"MCP_SVC_PASSWORD": password})
    except (OSError, AdminSqlError) as e:
        print(f"ERROR: {e}", file=err)
        return 2
    identities = sorted({m.group("ident") for m in matches})
    shown = [_mask(s, [password]) for s in rendered]

    if env.get("APPLY") != "1":
        for s in shown:
            print(f"DRY-RUN SQL: {s}", file=out)
        print(f"DRY-RUN: {len(shown)} statements as {env.get('DORIS_ADMIN_USER') or '<admin>'}; "
              "APPLY=1 to execute", file=out)
        return 0

    missing = [k for k in ("DORIS_HOST", "DORIS_ADMIN_USER", "DORIS_ADMIN_PASSWORD") if not env.get(k)]
    if missing:
        print(f"ERROR: missing environment: {', '.join(missing)}", file=err)
        return 2
    secrets = [password, env["DORIS_ADMIN_PASSWORD"], env["DORIS_HOST"]]  # pymysql errors name the host
    try:
        conn = connect(host=env["DORIS_HOST"], port=int(env.get("DORIS_PORT") or 9030),
                       user=env["DORIS_ADMIN_USER"], password=env["DORIS_ADMIN_PASSWORD"],
                       connect_timeout=10, read_timeout=60, autocommit=True)
    except pymysql.MySQLError as e:
        print(f"FAILED: connect: {_mask(str(e), secrets)}", file=err)
        return 1
    try:
        with conn.cursor() as cur:
            for stmt, text in zip(rendered, shown):
                try:
                    cur.execute(stmt)
                except pymysql.MySQLError as e:
                    print(f"FAILED: {text}\n  {_mask(str(e), secrets)}", file=err)
                    return 1
                print(f"ok: {text}", file=out)
            for ident in identities:
                cur.execute(f"SHOW GRANTS FOR {ident}")
                for row in cur.fetchall():
                    print(f"grants: {_mask(' | '.join(map(str, row)), secrets)}", file=out)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 77 tests`、`OK`。

- [ ] **Step 5：写失败测试 `doris/test/test_mcp_user_sql.py`**

锁定 SQL 文件的内容恰好是 R-42 的账号设置。

```python
"""Contract test: doris/01_mcp_user.sql grants exactly what R-42 allows (offline).

    .venv/bin/python -m unittest discover -s doris/test -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

DORIS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DORIS_DIR))

import admin_sql  # noqa: E402

PW = "Abc123def456GHI789jkl012MNO345pq"


# Written with the placeholder: a literal password after IDENTIFIED BY trips scripts/check-secrets.sh.
EXPECTED = [
    "CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}'",
    "ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}'",
    "GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%'",
    "GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'%'",
]


class McpUserSql(unittest.TestCase):
    def test_statements_are_exactly_the_r42_account_setup(self):
        stmts = admin_sql.load_statements((DORIS_DIR / "01_mcp_user.sql").read_text(encoding="utf-8"))
        self.assertEqual(stmts, EXPECTED)
        self.assertEqual(admin_sql.render(stmts, {"MCP_SVC_PASSWORD": PW}),
                         [s.replace("${MCP_SVC_PASSWORD}", PW) for s in EXPECTED])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 78 tests`、`FAILED (errors=1)`，出错的是 `test_statements_are_exactly_the_r42_account_setup`（`FileNotFoundError`：SQL 文件还不存在）。

- [ ] **Step 7：写 `doris/01_mcp_user.sql`**

```sql
-- P2 / T2.2 — Doris service account for the doris-mcp Runtime (design §6.1, R-42).
-- Run as root through doris/apply-admin-sql.sh (dry-run by default; APPLY=1 only after the GATE).
-- ${MCP_SVC_PASSWORD} is filled in memory from Secrets Manager doris-mcp/mcp_svc; never write it here.
-- Re-run safe: CREATE ... IF NOT EXISTS, ALTER USER converges the password to the secret, GRANT is additive.
-- Host '%' for now (D6: P2 connects from the dev box); P3 T3.5 narrows it to '172.31.%'.
-- No ADMIN / LOAD / ALTER / DROP. CREATE on system_mcp only lets upstream's CREATE ... IF NOT EXISTS pass.
CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%';
GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'%';
```

- [ ] **Step 8：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 78 tests`、`OK`。

- [ ] **Step 9：写失败测试 `doris/test/test-apply-admin-sql.sh`**

```bash
#!/usr/bin/env bash
# Offline tests for doris/apply-admin-sql.sh: fake `aws`, fake credentials file, stub python.
# Checks what reaches the python process (env names, stdin); no AWS, no Doris.
#   bash doris/test/test-apply-admin-sql.sh
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/apply-admin-sql.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
cat > "$TMP/bin/aws" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
[[ "$1 $2" == "secretsmanager get-secret-value" ]] && { echo '{"username":"mcp_svc","password":"SvcPw0123456789abcdef"}'; exit 0; }
exit 99
FAKE
# Stub python: records argv, the names of DORIS_* / APPLY env vars (values only for non-secrets), and stdin.
cat > "$TMP/bin/stub-python" <<'STUB'
#!/usr/bin/env bash
{ echo "argv: $*"
  for v in $(compgen -e | grep -E '^(DORIS_|APPLY$)' | sort); do
    case "$v" in *PASSWORD*) echo "env: $v=<set>" ;; *) echo "env: $v=${!v}" ;; esac
  done
  echo "stdin: $(cat)"; } > "$STUB_OUT"
STUB
chmod +x "$TMP/bin/aws" "$TMP/bin/stub-python"
printf '%s\n' 'DORIS_HOST=198.51.100.7' 'DORIS_MYSQL_PORT=9030' 'DORIS_HTTP_PORT=8030' \
  'DORIS_ROOT_USER=root' 'DORIS_ROOT_PASSWORD=RootPw0123456789' \
  'DORIS_RO_USER=demo_ro' 'DORIS_RO_PASSWORD=RoPw0123456789' > "$TMP/cred.env"

FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
run_wrapper() { # APPLY → sets RC, REC (what the stub saw), LOG (aws calls)
  : > "$TMP/aws.log"; : > "$TMP/stub.out"
  env -u DORIS_HOST -u DORIS_ROOT_PASSWORD -u DORIS_RO_PASSWORD PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" \
    STUB_OUT="$TMP/stub.out" PYTHON_BIN="$TMP/bin/stub-python" DORIS_CRED_FILE="$TMP/cred.env" APPLY="$1" \
    bash "$SCRIPT" doris/01_mcp_user.sql > "$TMP/out.txt" 2>&1
  RC=$?; REC="$(cat "$TMP/stub.out")"; LOG="$(cat "$TMP/aws.log")"
}
has() { [[ "$1" == *"$2"* ]] && echo yes || echo no; }

run_wrapper 0
check "dry-run: exit 0" 0 "$RC"
check "dry-run: reads the mcp_svc secret" yes "$(has "$LOG" "get-secret-value --secret-id doris-mcp/mcp_svc")"
check "dry-run: secret arrives on stdin" yes "$(has "$REC" 'stdin: {"username":"mcp_svc"')"
check "dry-run: SQL file passed through" yes "$(has "$REC" "doris/01_mcp_user.sql")"
check "dry-run: host and port exported" "yes|yes" \
  "$(has "$REC" "env: DORIS_HOST=198.51.100.7")|$(has "$REC" "env: DORIS_PORT=9030")"
check "dry-run: admin password NOT exported" no "$(has "$REC" "DORIS_ADMIN_PASSWORD")"
check "dry-run: APPLY=0 reaches python" yes "$(has "$REC" "env: APPLY=0")"
check "never exports root/ro variables by their original names" "no|no" \
  "$(has "$REC" "DORIS_ROOT_")|$(has "$REC" "DORIS_RO_")"

run_wrapper 1
check "apply: admin user and password exported" "yes|yes" \
  "$(has "$REC" "env: DORIS_ADMIN_USER=root")|$(has "$REC" "env: DORIS_ADMIN_PASSWORD=<set>")"
check "apply: APPLY=1 reaches python" yes "$(has "$REC" "env: APPLY=1")"
check "no secret value in any aws argv" "no|no" "$(has "$LOG" "SvcPw0123")|$(has "$LOG" "RootPw0123")"

# End to end with the real admin_sql.py (dry-run never connects).
REAL_PY="${REAL_PYTHON_BIN:-$(cd "$(dirname "$SCRIPT")/.." && pwd)/.venv/bin/python}"
E2E="$(cd "$(dirname "$SCRIPT")/.." && env -u DORIS_ROOT_PASSWORD PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" \
  PYTHON_BIN="$REAL_PY" DORIS_CRED_FILE="$TMP/cred.env" APPLY=0 bash "$SCRIPT" doris/01_mcp_user.sql 2>&1)"
check "e2e dry-run: prints masked CREATE USER" yes \
  "$(has "$E2E" "DRY-RUN SQL: CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '***'")"
check "e2e dry-run: 4 statements as root" yes "$(has "$E2E" "DRY-RUN: 4 statements as root;")"
check "e2e dry-run: no secret or host in output" "no|no|no" \
  "$(has "$E2E" "SvcPw0123")|$(has "$E2E" "RootPw0123")|$(has "$E2E" "198.51.100.7")"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
```

- [ ] **Step 10：运行测试，确认失败**

```bash
bash doris/test/test-apply-admin-sql.sh 2>&1 | tail -1
```
期望：`10 failed`（wrapper 还不存在）。

- [ ] **Step 11：写 `doris/apply-admin-sql.sh`**

```bash
#!/usr/bin/env bash
# P2 / T2.2 — run a doris/*.sql account script as the Doris admin (root).
#   bash doris/apply-admin-sql.sh doris/01_mcp_user.sql            # dry-run: masked statements, no connection
#   APPLY=1 bash doris/apply-admin-sql.sh doris/01_mcp_user.sql    # GATE: only after the user confirms
# The service-account password flows Secrets Manager → pipe → admin_sql.py (never argv, disk or output).
# credentials.env is sourced in a subshell; only host/port, the admin user and (APPLY=1 only) the admin
# password are exported, under new names, to the python process.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SQL="${1:?usage: [APPLY=1] bash doris/apply-admin-sql.sh doris/01_mcp_user.sql}"
CRED="${DORIS_CRED_FILE:-/home/ubuntu/AI-code/Doris-test/credentials.env}"
PY="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
SECRET_ID="${DORIS_SECRET_ID:-doris-mcp/mcp_svc}"
export AWS_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER="" APPLY="${APPLY:-0}"

aws secretsmanager get-secret-value --secret-id "$SECRET_ID" --query SecretString --output text |
  ( source "$CRED"
    export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_ADMIN_USER="$DORIS_ROOT_USER"
    [[ "$APPLY" == "1" ]] && export DORIS_ADMIN_PASSWORD="$DORIS_ROOT_PASSWORD"
    exec "$PY" "$ROOT/doris/admin_sql.py" "$SQL" )
```

- [ ] **Step 12：运行测试，确认通过**

```bash
bash doris/test/test-apply-admin-sql.sh 2>&1 | tail -1   # 期望：all passed（14 项）
```

- [ ] **Step 13：dry-run（读取真实 secret，不连 Doris）**

```bash
bash doris/apply-admin-sql.sh doris/01_mcp_user.sql
```
期望：
```
DRY-RUN SQL: CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '***'
DRY-RUN SQL: ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '***'
DRY-RUN SQL: GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%'
DRY-RUN SQL: GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'%'
DRY-RUN: 4 statements as root; APPLY=1 to execute
```

- [ ] **Step 14：GATE —— 展示并等待确认**

向用户展示 Step 13 的输出，并说明：
- 以 root 执行这 4 条语句：创建 `'mcp_svc'@'%'`（已存在则跳过），把密码设为 secret 里的值（`ALTER USER`，所以重跑也会收敛到 secret），授予 `internal.ecom` 的 SELECT 和 `internal.system_mcp` 的 SELECT + CREATE；
- 密码从 Secrets Manager 经管道进入 python，只在内存里填进 SQL，不进命令行参数、文件和输出；
- 不授予 ADMIN / LOAD / ALTER / DROP；host `'%'` 按 D6，P3 T3.5 收紧；
- 执行后打印 `SHOW GRANTS FOR 'mcp_svc'@'%'`；
- 回滚（也需要 GATE）：root 执行 `DROP USER 'mcp_svc'@'%'`。

用户明确确认后执行：
```bash
APPLY=1 bash doris/apply-admin-sql.sh doris/01_mcp_user.sql
```
期望：4 行 `ok: …`（与 dry-run 相同，密码为 `***`），然后是 `grants: …` 行，其中 DatabasePrivs 含 `internal.ecom: Select_priv` 和 `internal.system_mcp: Select_priv,Create_priv`（另有 Doris 默认的 `internal.information_schema: Select_priv`、`internal.mysql: Select_priv`；顺序可能不同）。退出码 0。

- [ ] **Step 15：收尾**

勾选 T2.2；progress「当前状态」写 T2.2 完成、下一步 T2.3，「Doris 变更」加上用户 `'mcp_svc'@'%'` 及其权限；日志记录 Step 14 的 `grants:` 行。

```bash
bash scripts/check-secrets.sh
git add doris/admin_sql.py doris/test/test_admin_sql.py doris/01_mcp_user.sql doris/test/test_mcp_user_sql.py \
        doris/apply-admin-sql.sh doris/test/test-apply-admin-sql.sh \
        specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "feat(p2): T2.2 create mcp_svc with the R-42 grants (password from Secrets Manager via stdin)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T2.3：`mcp_svc` 权限矩阵

**Files:**
- Create：`doris/permission_matrix.py`、`doris/test/test_permission_matrix.py`
- Modify：`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：T2.2 的 `mcp_svc`、T2.5 的 `system_mcp` / `ecom`；P1 的 `agentcore_ext.settings.load_settings`；upstream `store.store`：`DorisStore.discover_workspaces()`、`DorisStore(workspace)`、`DorisStore._table_cache`、`set_doris_endpoint`、`set_service_credentials`、`clear_service_credentials`（P1 的 P-03）；`store.bootstrap.collect_physical_tables`
- Produces：`python doris/permission_matrix.py [--models DIR] [--workspace ecom]`，dry-run 执行 4 项只读检查并列出探针，`APPLY=1` 再执行 store_init + 9 个写探针；exit 0 / 1 / 2。模块内：`EXPECTED_GRANTS`、`EXPECTED_DATABASES`、`write_probes(identity) -> list[Probe]`、`parse_grants(row)`、`grant_problems(actual, expected)`、`classify_error(error) -> "denied" | "error"`。P3 T3.5 收紧 host 后用它复测。

检查项：
- 只读：`SHOW GRANTS` 与 `EXPECTED_GRANTS` 完全一致（R-42 + Doris 默认项）；`SHOW DATABASES` = `ecom, information_schema, mysql, system_mcp`；9 张物理表都可 SELECT；`ecom` 有元数据行和 active 文件（没有元数据行时 upstream 会 INSERT，而 `mcp_svc` 没有 LOAD_PRIV）。
- 探针（APPLY=1）：upstream store 初始化必须**成功**；9 个写操作必须**被拒**（errno 1044 / 1142 / 1143 / 1227，或 1105 且消息含 denied）。每个写探针即使被允许也不改变任何东西。

- [ ] **Step 1：写失败测试 `doris/test/test_permission_matrix.py`**

```python
"""Offline tests for doris/permission_matrix.py (no Doris connection).

    .venv/bin/python -m unittest discover -s doris/test -v

The connection is a fake that answers by SQL prefix; SHOW GRANTS rows have the shape Doris 4.1
returns (checked as demo_ro in P2 planning). The live run is T2.3: read-only checks first, the
probes only after the GATE.
"""

from __future__ import annotations

import io
import logging
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
sys.path.insert(0, str(ROOT / "doris"))

import pymysql  # noqa: E402

import permission_matrix  # noqa: E402
from agentcore_ext.settings import load_settings  # noqa: E402
from permission_matrix import classify_error, grant_problems, parse_grants, write_probes  # noqa: E402
from store.bootstrap import collect_physical_tables  # noqa: E402

MODELS = ROOT / "doris" / "semantic" / "ecom"
PASSWORD = "SvcPw0123456789abcXYZ"
ENV = {"DORIS_HOST": "10.0.0.1", "DORIS_PORT": "9030", "DORIS_USER": "mcp_svc", "DORIS_PASSWORD": PASSWORD}
IDENTITY = "'mcp_svc'@'%'"


def grants_row(database_privs, **columns):
    row = {"UserIdentity": IDENTITY, "Comment": "", "Password": "Yes", "RequireSan": None, "Roles": "",
           "GlobalPrivs": None, "CatalogPrivs": None, "DatabasePrivs": database_privs, "TablePrivs": None,
           "ColPrivs": None, "ResourcePrivs": None, "CloudClusterPrivs": None, "CloudStagePrivs": None,
           "StorageVaultPrivs": None, "WorkloadGroupPrivs": "normal: Usage_priv", "ComputeGroupPrivs": None}
    row.update(columns)
    return row


DEFAULT_DBS = "internal.information_schema: Select_priv; internal.mysql: Select_priv"
MCP_SVC_GRANTS = grants_row(f"internal.ecom: Select_priv; {DEFAULT_DBS}; internal.system_mcp: Select_priv,Create_priv")
DEMO_RO_GRANTS = grants_row(f"internal.ecom: Select_priv; {DEFAULT_DBS}", UserIdentity="'demo_ro'@'%'")


def denied(action="LOAD"):
    return pymysql.err.OperationalError(
        1142, f"errCode = 2, detailMessage = {action} command denied to user 'mcp_svc'@'10.0.0.9' for table x")


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append(sql)
        response = self.conn.default
        for key in sorted(self.conn.responses, key=len, reverse=True):
            if sql.startswith(key):
                response = self.conn.responses[key]
                break
        if isinstance(response, BaseException):
            raise response
        self.rows = [dict(r) for r in response]

    def fetchall(self):
        return self.rows


class FakeDoris:
    """Answers by the longest matching SQL prefix; anything else gets `default` (a write denial)."""

    def __init__(self, overrides=None, default=None):
        self.responses = {
            "SELECT CURRENT_USER()": [{"identity": IDENTITY}],
            "SHOW GRANTS": [MCP_SVC_GRANTS],
            "SHOW DATABASES": [{"Database": d} for d in ("ecom", "information_schema", "mysql", "system_mcp")],
            "SHOW PROPERTY": [{"Key": "max_user_connections", "Value": "100"}, {"Key": "query_timeout", "Value": "-1"}],
            "SELECT 1 FROM ": [{"1": 1}],
            "SELECT semantic_version FROM system_mcp.workspace_metadata": [{"semantic_version": 2}],
            "SELECT COUNT(*) AS files FROM system_mcp.active_store_ecom": [{"files": 10}],
        }
        self.responses.update(overrides or {})
        self.default = default if default is not None else denied()
        self.executed, self.closed = [], False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


def run_main(argv=(), env=ENV, conn=None, apply=False, store_init=None, connect=None):
    out, err, seen = io.StringIO(), io.StringIO(), {"connect": {}, "store_init": []}
    conn = conn or FakeDoris()
    env = dict(env, **({"APPLY": "1"} if apply else {}))

    def fake_connect(**kwargs):
        seen["connect"] = kwargs
        return conn

    def fake_store_init(settings, workspace):
        seen["store_init"].append((settings.doris_user, workspace))
        return store_init or (True, "discover_workspaces -> ecom; tables ensured")

    rc = permission_matrix.main(list(argv), env=env, connect=connect or fake_connect, out=out, err=err,
                                store_init=fake_store_init)
    return rc, out.getvalue(), err.getvalue(), conn, seen


class ParseGrants(unittest.TestCase):
    def test_parses_the_doris_show_grants_row(self):
        self.assertEqual(parse_grants(DEMO_RO_GRANTS), {
            "DatabasePrivs": {"internal.ecom": {"Select_priv"}, "internal.information_schema": {"Select_priv"},
                              "internal.mysql": {"Select_priv"}},
            "WorkloadGroupPrivs": {"normal": {"Usage_priv"}},
        })

    def test_several_privileges_with_or_without_spaces(self):
        for privs in ("Select_priv,Create_priv", "Select_priv, Create_priv"):
            with self.subTest(privs=privs):
                parsed = parse_grants({"DatabasePrivs": f"internal.system_mcp: {privs}"})
                self.assertEqual(parsed, {"DatabasePrivs": {"internal.system_mcp": {"Select_priv", "Create_priv"}}})

    def test_global_privileges_and_roles_have_no_object(self):
        parsed = parse_grants({"GlobalPrivs": "Node_priv,Admin_priv", "Roles": "operator", "TablePrivs": ""})
        self.assertEqual(parsed, {"GlobalPrivs": {"*": {"Node_priv", "Admin_priv"}}, "Roles": {"*": {"operator"}}})

    def test_non_privilege_columns_are_ignored(self):
        parsed = parse_grants({"UserIdentity": IDENTITY, "Password": "Yes", "Comment": "x", "RequireSan": None})
        self.assertEqual(parsed, {})


class GrantProblems(unittest.TestCase):
    def test_the_r42_grants_pass(self):
        self.assertEqual(grant_problems(parse_grants(MCP_SVC_GRANTS)), [])

    def test_an_extra_privilege_is_reported(self):
        row = grants_row(f"internal.ecom: Select_priv,Load_priv; {DEFAULT_DBS}; "
                         "internal.system_mcp: Select_priv,Create_priv")
        self.assertEqual(grant_problems(parse_grants(row)), ["DatabasePrivs internal.ecom: unexpected Load_priv"])

    def test_a_missing_privilege_is_reported(self):
        row = grants_row(f"internal.ecom: Select_priv; {DEFAULT_DBS}; internal.system_mcp: Select_priv")
        self.assertEqual(grant_problems(parse_grants(row)), ["DatabasePrivs internal.system_mcp: missing Create_priv"])

    def test_extra_scopes_and_roles_are_reported(self):
        row = dict(MCP_SVC_GRANTS, GlobalPrivs="Admin_priv", Roles="admin",
                   TablePrivs="internal.dw.orders: Select_priv")
        self.assertEqual(grant_problems(parse_grants(row)), [
            "GlobalPrivs *: unexpected Admin_priv",
            "Roles *: unexpected admin",
            "TablePrivs internal.dw.orders: unexpected Select_priv",
        ])

    def test_demo_ro_lacks_system_mcp(self):
        self.assertEqual(grant_problems(parse_grants(DEMO_RO_GRANTS)),
                         ["DatabasePrivs internal.system_mcp: missing Create_priv, Select_priv"])


class ClassifyError(unittest.TestCase):
    def test_privilege_error_codes_are_denials(self):
        for errno in (1044, 1142, 1143, 1227):
            with self.subTest(errno=errno):
                self.assertEqual(classify_error(pymysql.err.OperationalError(errno, "no")), "denied")

    def test_doris_generic_errors_that_say_denied_are_denials(self):
        # Seen as demo_ro: (1105, "... SHOW CREATE TABLE command denied to user 'demo_ro'@'...' for table ...")
        for message in ("errCode = 2, detailMessage = SHOW CREATE TABLE command denied to user 'demo_ro'@'x'",
                        "errCode = 2, detailMessage = Access denied; you need (at least one of) the (LOAD) "
                        "privilege(s) for this operation"):
            with self.subTest(message=message):
                self.assertEqual(classify_error(pymysql.err.OperationalError(1105, message)), "denied")

    def test_other_errors_are_not_denials(self):
        for errno, message in ((1105, "errCode = 2, detailMessage = Unknown table 'mcp_perm_probe'"),
                               (1064, "errCode = 2, detailMessage = Syntax error"),
                               # A login failure says "denied" too, but it is not Doris refusing the write.
                               (1045, "Access denied for user 'mcp_svc'@'x' (using password: YES)"),
                               (2013, "Lost connection to MySQL server during query")):
            with self.subTest(errno=errno):
                self.assertEqual(classify_error(pymysql.err.OperationalError(errno, message)), "error")


# A write probe must change nothing even if Doris allowed it (e.g. if R-42 were broken).
NO_OP_SHAPES = (
    r"INSERT INTO (\S+) SELECT \* FROM \1 WHERE 1 = 0",
    r"UPDATE \S+ SET (\w+) = \1 WHERE \w+ = 'mcp_perm_probe'",
    r"DELETE FROM \S+ WHERE \w+ = 'mcp_perm_probe'",
    r"DROP TABLE IF EXISTS \w+\.mcp_perm_probe",
    r"CREATE DATABASE IF NOT EXISTS ecom",  # exists
    r"GRANT SELECT_PRIV ON internal\.ecom\.\* TO '\w+'@'[^']+'",  # already held
    r"ADMIN SHOW FRONTEND CONFIG LIKE '[\w%]+'",  # read-only
)


class WriteProbes(unittest.TestCase):
    def test_every_write_probe_is_a_no_op_if_it_were_allowed(self):
        for probe in write_probes(IDENTITY):
            with self.subTest(probe=probe.name):
                self.assertEqual(sum(bool(re.fullmatch(s, probe.sql)) for s in NO_OP_SHAPES), 1, probe.sql)

    def test_probes_cover_load_create_drop_grant_and_admin(self):
        verbs = {p.sql.split()[0] for p in write_probes(IDENTITY)}
        self.assertEqual(verbs, {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "GRANT", "ADMIN"})
        targets = " ".join(p.sql for p in write_probes(IDENTITY))
        for schema in ("ecom.", "system_mcp."):
            self.assertIn(f"INSERT INTO {schema}", targets)
            self.assertIn(f"DROP TABLE IF EXISTS {schema}", targets)

    def test_names_are_unique(self):
        names = [p.name for p in write_probes(IDENTITY)]
        self.assertEqual(len(names), len(set(names)))

    def test_grant_probe_targets_the_connected_identity(self):
        grant = [p for p in write_probes("'mcp_svc'@'172.31.%'") if p.sql.startswith("GRANT")]
        self.assertEqual([p.sql for p in grant], ["GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'172.31.%'"])


class DryRun(unittest.TestCase):
    def test_runs_only_read_only_statements_and_lists_the_probes(self):
        rc, out, err, conn, seen = run_main()
        self.assertEqual(rc, 0, err)
        self.assertEqual({s.split()[0] for s in conn.executed}, {"SELECT", "SHOW"})
        self.assertEqual(seen["store_init"], [])
        self.assertTrue(conn.closed)
        for line in (f"connected as {IDENTITY}", "ok    grants", "ok    databases: ecom, information_schema, "
                     "mysql, system_mcp", "ok    select: 9 physical tables", "ok    semantic store: workspace ecom "
                     "semantic_version=2, 10 active files", "info  max_user_connections=100",
                     "DRY-RUN probes", "4/4 checks pass"):
            self.assertIn(line, out)
        for probe in write_probes(IDENTITY):
            self.assertIn(probe.sql, out)
        self.assertIn("store_init", out)

    def test_select_covers_every_physical_table_of_the_models(self):
        _, _, _, conn, _ = run_main()
        selected = [s[len("SELECT 1 FROM "):-len(" LIMIT 1")] for s in conn.executed if s.startswith("SELECT 1 FROM")]
        self.assertEqual(selected, sorted(collect_physical_tables(MODELS)))
        self.assertIn("internal.ecom.v_paid_order", selected)

    def test_grant_mismatch_fails_and_the_other_checks_still_run(self):
        row = grants_row(f"internal.ecom: Select_priv,Load_priv; {DEFAULT_DBS}; "
                         "internal.system_mcp: Select_priv,Create_priv")
        rc, out, _, _, _ = run_main(conn=FakeDoris({"SHOW GRANTS": [row]}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  grants: DatabasePrivs internal.ecom: unexpected Load_priv", out)
        self.assertIn("ok    semantic store", out)
        self.assertIn("3/4 checks pass", out)

    def test_visible_databases_must_be_exactly_the_expected_ones(self):
        dbs = [{"Database": d} for d in ("dw", "ecom", "information_schema", "mysql")]
        rc, out, _, _, _ = run_main(conn=FakeDoris({"SHOW DATABASES": dbs}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  databases: missing system_mcp; unexpected dw", out)

    def test_an_unreadable_table_fails(self):
        conn = FakeDoris({"SELECT 1 FROM internal.ecom.dim_brand": denied("SELECT")})
        rc, out, _, _, _ = run_main(conn=conn)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  select: internal.ecom.dim_brand: 1142", out)

    def test_missing_metadata_row_fails_with_a_hint(self):
        # Upstream would INSERT the row on first use, which needs LOAD_PRIV: T2.5 must publish first.
        rc, out, _, conn, _ = run_main(conn=FakeDoris({"SELECT semantic_version FROM system_mcp.workspace_metadata": []}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  semantic store: no workspace_metadata row for ecom", out)
        self.assertIn("T2.5", out)

    def test_empty_active_store_fails(self):
        rc, out, _, _, _ = run_main(conn=FakeDoris({"SELECT COUNT(*) AS files FROM system_mcp.active_store_ecom":
                                                    [{"files": 0}]}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  semantic store: workspace ecom has no active files", out)

    def test_a_check_that_errors_is_reported_by_name_and_the_rest_still_run(self):
        rc, out, _, _, _ = run_main(conn=FakeDoris({"SHOW GRANTS": denied("SHOW")}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  grants: 1142", out)
        self.assertIn("ok    databases", out)
        self.assertIn("3/4 checks pass", out)

    def test_show_property_failure_is_only_informational(self):
        rc, out, err, _, _ = run_main(conn=FakeDoris({"SHOW PROPERTY": denied("SHOW")}))
        self.assertEqual(rc, 0, err)
        self.assertIn("info  max_user_connections=unavailable (1142", out)

    def test_another_account_is_a_usage_error(self):
        conn = FakeDoris({"SELECT CURRENT_USER()": [{"identity": "'demo_ro'@'%'"}]})
        rc, _, err, _, _ = run_main(conn=conn)
        self.assertEqual(rc, 2)
        self.assertIn("mcp_svc", err)
        self.assertEqual(conn.executed, ["SELECT CURRENT_USER() AS identity"])

    def test_configuration_errors_are_usage_errors(self):
        for argv, env, text in (([], {"DORIS_USER": "mcp_svc", "DORIS_PASSWORD": PASSWORD}, "DORIS_HOST"),
                                (["--workspace", "ecom; DROP"], ENV, "workspace")):
            with self.subTest(text=text):
                rc, _, err, conn, seen = run_main(argv, env=env)
                self.assertEqual(rc, 2)
                self.assertIn(text, err)
                self.assertEqual((conn.executed, seen["connect"]), ([], {}))

    def test_connection_parameters(self):
        _, _, _, _, seen = run_main()
        kwargs = seen["connect"]
        self.assertEqual((kwargs["host"], kwargs["port"], kwargs["user"], kwargs["password"]),
                         ("10.0.0.1", 9030, "mcp_svc", PASSWORD))
        self.assertIs(kwargs["cursorclass"], pymysql.cursors.DictCursor)
        self.assertTrue(kwargs["autocommit"])

    def test_connect_errors_are_masked(self):
        def refuse(**kwargs):
            raise pymysql.err.OperationalError(1045, f"Access denied for 'mcp_svc' on 10.0.0.1 using {PASSWORD}")

        rc, out, err, _, _ = run_main(connect=refuse)
        self.assertEqual(rc, 1)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("10.0.0.1", out + err)
        self.assertIn("***", err)


class Apply(unittest.TestCase):
    def test_all_writes_denied_and_store_init_ok_passes(self):
        rc, out, err, conn, seen = run_main(apply=True)
        self.assertEqual(rc, 0, err)
        self.assertEqual(seen["store_init"], [("mcp_svc", "ecom")])
        probes = write_probes(IDENTITY)
        for probe in probes:
            self.assertEqual(conn.executed.count(probe.sql), 1, probe.sql)
            self.assertIn(f"ok    probe {probe.name}: denied (1142", out)
        self.assertIn("ok    probe store_init: discover_workspaces -> ecom", out)
        total = 4 + 1 + len(probes)
        self.assertIn(f"{total}/{total} checks pass", out)
        self.assertNotIn("DRY-RUN", out)

    def test_an_allowed_write_fails(self):
        conn = FakeDoris({"INSERT INTO ecom.dim_brand": []})
        rc, out, _, _, _ = run_main(conn=conn, apply=True)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  probe load_ecom: ALLOWED, expected denied", out)

    def test_any_other_error_is_inconclusive(self):
        conn = FakeDoris({"DROP TABLE IF EXISTS ecom.": pymysql.err.OperationalError(1105, "Unknown table")})
        rc, out, _, _, _ = run_main(conn=conn, apply=True)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  probe drop_ecom: inconclusive, expected denied: 1105 Unknown table", out)

    def test_store_init_failure_fails(self):
        rc, out, _, _, _ = run_main(apply=True, store_init=(False, "Table init failed: CREATE command denied"))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  probe store_init: Table init failed: CREATE command denied", out)

    def test_store_init_database_error_is_caught_and_the_probes_still_run(self):
        def broken(settings, workspace):
            raise pymysql.err.OperationalError(1044, "Access denied for user 'mcp_svc' to database 'system_mcp'")

        out = io.StringIO()
        conn = FakeDoris()
        rc = permission_matrix.main([], env=dict(ENV, APPLY="1"), connect=lambda **kw: conn, out=out,
                                    err=io.StringIO(), store_init=broken)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  probe store_init: 1044", out.getvalue())
        self.assertIn("ok    probe admin", out.getvalue())

    def test_probe_messages_are_masked(self):
        leak = pymysql.err.OperationalError(1142, f"LOAD command denied ({PASSWORD} @ 10.0.0.1)")
        rc, out, err, _, _ = run_main(conn=FakeDoris(default=leak), apply=True)
        self.assertEqual(rc, 0, err)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("10.0.0.1", out + err)


class FakeStoreClass:
    """Stands in for store.store.DorisStore: class-level table cache, discover, logging init failure."""

    _table_cache: dict = {}
    workspaces = ["ecom"]
    fail = None

    @classmethod
    def discover_workspaces(cls):
        return list(cls.workspaces)

    def __init__(self, workspace):
        if self._table_cache.get(workspace):
            return
        if self.fail:
            logging.getLogger("doris_new_mcp.store").warning(
                f"Table init failed for workspace '{workspace}': {self.fail}")
        else:
            type(self)._table_cache[workspace] = True


class UpstreamStoreInit(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(ENV)
        store = type("Store", (FakeStoreClass,), {"_table_cache": {}})
        self.store = store
        patches = {name: mock.patch.object(permission_matrix, name) for name in
                   ("set_doris_endpoint", "set_service_credentials", "clear_service_credentials")}
        patches["DorisStore"] = mock.patch.object(permission_matrix, "DorisStore", store)
        self.mocks = {name: p.start() for name, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)

    def test_runs_upstream_init_as_the_service_account(self):
        ok, detail = permission_matrix.upstream_store_init(self.settings, "ecom")
        self.assertTrue(ok, detail)
        self.mocks["set_doris_endpoint"].assert_called_once_with("10.0.0.1", 9030)
        self.mocks["set_service_credentials"].assert_called_once_with("mcp_svc", PASSWORD)
        self.mocks["clear_service_credentials"].assert_called_once_with()
        self.assertTrue(self.store._table_cache["ecom"])

    def test_a_cached_success_cannot_hide_a_failure(self):
        self.store._table_cache["ecom"] = True
        self.store.fail = "(1142, 'CREATE command denied to user mcp_svc')"
        ok, detail = permission_matrix.upstream_store_init(self.settings, "ecom")
        self.assertFalse(ok)
        self.assertIn("CREATE command denied", detail)

    def test_an_undiscovered_workspace_fails(self):
        self.store.workspaces = []
        ok, detail = permission_matrix.upstream_store_init(self.settings, "ecom")
        self.assertFalse(ok)
        self.assertIn("discover_workspaces found []", detail)

    def test_credentials_are_cleared_when_discovery_raises(self):
        with mock.patch.object(self.store, "discover_workspaces",
                               side_effect=pymysql.err.OperationalError(1044, "denied")):
            with self.assertRaises(pymysql.MySQLError):
                permission_matrix.upstream_store_init(self.settings, "ecom")
        self.mocks["clear_service_credentials"].assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 79 tests`、`FAILED (errors=1)`，报错是 `ModuleNotFoundError: No module named 'permission_matrix'`。

- [ ] **Step 3：写 `doris/permission_matrix.py`**

```python
"""Check the Doris privileges of the MCP service account mcp_svc (P2 / T2.3; R-21, R-42).

    python doris/permission_matrix.py [--workspace ecom]           # read-only checks + the probe list
    APPLY=1 python doris/permission_matrix.py [--workspace ecom]   # GATE: also run the probes

Connection: agentcore_ext.settings.load_settings(os.environ) -- DORIS_HOST, DORIS_PORT and
DORIS_SECRET_ID=doris-mcp/mcp_svc (or DORIS_USER/DORIS_PASSWORD).
Read-only checks: SHOW GRANTS equals EXPECTED_GRANTS exactly (R-42), SHOW DATABASES equals
EXPECTED_DATABASES, every physical table of the models is readable, the workspace has a metadata
row (else upstream would INSERT it, which needs LOAD_PRIV) and active files.
Probes (APPLY=1): upstream's semantic-store init (CREATE ... IF NOT EXISTS) must pass as the service
account, and every write must be denied by Doris (R-21). Each write probe changes nothing even if it
were allowed: 0 rows, a missing row, IF EXISTS on an absent table, IF NOT EXISTS on an existing
database, a grant the account already holds, or a read-only ADMIN command.
Exit 0 when every check passes, 1 when one fails, 2 on usage/configuration errors.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
MODELS_DIR = ROOT / "doris" / "semantic" / "ecom"

import pymysql  # noqa: E402

from agentcore_ext.settings import Settings, SettingsError, load_settings  # noqa: E402
from store.bootstrap import collect_physical_tables  # noqa: E402
from store.store import (  # noqa: E402
    DorisStore, clear_service_credentials, set_doris_endpoint, set_service_credentials)

MASK = "***"
EXPECTED_USER = "mcp_svc"
EXPECTED_GRANTS: dict[str, dict[str, set[str]]] = {
    "DatabasePrivs": {
        "internal.ecom": {"Select_priv"},
        "internal.system_mcp": {"Select_priv", "Create_priv"},
        # Doris lists these for every user (demo_ro too): read-only system schemas.
        "internal.information_schema": {"Select_priv"},
        "internal.mysql": {"Select_priv"},
    },
    "WorkloadGroupPrivs": {"normal": {"Usage_priv"}},  # Doris default workload group
}
EXPECTED_DATABASES = frozenset({"ecom", "system_mcp", "information_schema", "mysql"})
DENIED_ERRNOS = frozenset({1044, 1142, 1143, 1227})
_WORKSPACE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")  # upstream workspace/create rule
_STORE_LOGGER = "doris_new_mcp.store"


@dataclasses.dataclass(frozen=True)
class Result:
    ok: bool
    name: str
    detail: str


@dataclasses.dataclass(frozen=True)
class Probe:
    name: str
    sql: str
    why: str


def write_probes(identity: str) -> list[Probe]:
    """Writes Doris must deny for `identity`; each is a no-op if it were allowed."""
    return [
        Probe("load_ecom", "INSERT INTO ecom.dim_brand SELECT * FROM ecom.dim_brand WHERE 1 = 0",
              "no LOAD_PRIV on ecom (0 rows)"),
        Probe("load_system_mcp", "INSERT INTO system_mcp.workspace_metadata "
              "SELECT * FROM system_mcp.workspace_metadata WHERE 1 = 0", "no LOAD_PRIV on system_mcp (0 rows)"),
        Probe("update_system_mcp", "UPDATE system_mcp.workspace_metadata SET semantic_version = semantic_version "
              "WHERE workspace = 'mcp_perm_probe'", "no LOAD_PRIV on system_mcp (no such row)"),
        Probe("delete_system_mcp", "DELETE FROM system_mcp.staging_store_ecom WHERE filename = 'mcp_perm_probe'",
              "no LOAD_PRIV on system_mcp (no such row)"),
        Probe("create_ecom", "CREATE DATABASE IF NOT EXISTS ecom", "no CREATE_PRIV on ecom (exists)"),
        Probe("drop_ecom", "DROP TABLE IF EXISTS ecom.mcp_perm_probe", "no DROP_PRIV on ecom (absent table)"),
        Probe("drop_system_mcp", "DROP TABLE IF EXISTS system_mcp.mcp_perm_probe",
              "no DROP_PRIV on system_mcp (absent table)"),
        Probe("grant", f"GRANT SELECT_PRIV ON internal.ecom.* TO {identity}", "no GRANT_PRIV (already held)"),
        Probe("admin", "ADMIN SHOW FRONTEND CONFIG LIKE 'qe_max_connection'", "no ADMIN_PRIV (read-only)"),
    ]


def parse_grants(row: Mapping[str, Any]) -> dict[str, dict[str, set[str]]]:
    """{column: {object: privileges}} of the non-empty *Privs columns and Roles of a SHOW GRANTS row."""
    parsed: dict[str, dict[str, set[str]]] = {}
    for column, value in row.items():
        if not (column.endswith("Privs") or column == "Roles") or not value:
            continue
        scopes: dict[str, set[str]] = {}
        for entry in str(value).split(";"):
            obj, sep, privs = entry.strip().rpartition(": ")
            scopes[obj if sep else "*"] = {p.strip() for p in privs.split(",") if p.strip()}
        parsed[column] = scopes
    return parsed


def grant_problems(actual: Mapping[str, Mapping[str, set[str]]],
                   expected: Mapping[str, Mapping[str, set[str]]] = EXPECTED_GRANTS) -> list[str]:
    problems = []
    for column in sorted(actual.keys() | expected.keys()):
        got, want = actual.get(column, {}), expected.get(column, {})
        for obj in sorted(got.keys() | want.keys()):
            missing, extra = want.get(obj, set()) - got.get(obj, set()), got.get(obj, set()) - want.get(obj, set())
            if missing:
                problems.append(f"{column} {obj}: missing {', '.join(sorted(missing))}")
            if extra:
                problems.append(f"{column} {obj}: unexpected {', '.join(sorted(extra))}")
    return problems


def classify_error(error: pymysql.MySQLError) -> str:
    """'denied' for a privilege error, 'error' for anything else."""
    errno = error.args[0] if error.args else None
    message = str(error.args[1]) if len(error.args) > 1 else ""
    if errno in DENIED_ERRNOS or (errno == 1105 and "denied" in message.lower()):
        return "denied"
    return "error"


def _brief(error: pymysql.MySQLError) -> str:
    errno = error.args[0] if error.args else "?"
    message = str(error.args[1]) if len(error.args) > 1 else str(error)
    return f"{errno} {message.replace('errCode = 2, detailMessage = ', '')[:160]}"


def _rows(cur: Any, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return list(cur.fetchall())


def check_grants(cur: Any) -> Result:
    rows = _rows(cur, "SHOW GRANTS")
    if len(rows) != 1:
        return Result(False, "grants", f"SHOW GRANTS returned {len(rows)} rows")
    problems = grant_problems(parse_grants(rows[0]))
    return Result(not problems, "grants", "; ".join(problems) or
                  "exactly internal.ecom SELECT, internal.system_mcp SELECT+CREATE (+ Doris defaults)")


def check_databases(cur: Any) -> Result:
    seen = {next(iter(r.values())) for r in _rows(cur, "SHOW DATABASES")}
    missing, extra = sorted(EXPECTED_DATABASES - seen), sorted(seen - EXPECTED_DATABASES)
    problems = ([f"missing {', '.join(missing)}"] if missing else []) + \
               ([f"unexpected {', '.join(extra)}"] if extra else [])
    return Result(not problems, "databases", "; ".join(problems) or ", ".join(sorted(seen)))


def check_select(cur: Any, tables: Sequence[str]) -> Result:
    failed = []
    for table in tables:
        try:
            _rows(cur, f"SELECT 1 FROM {table} LIMIT 1")
        except pymysql.MySQLError as e:
            failed.append(f"{table}: {_brief(e)}")
    return Result(not failed, "select", "; ".join(failed) or f"{len(tables)} physical tables of the models")


def check_semantic_store(cur: Any, workspace: str) -> Result:
    rows = _rows(cur, "SELECT semantic_version FROM system_mcp.workspace_metadata WHERE workspace = %s",
                 (workspace,))
    if not rows:
        return Result(False, "semantic store", f"no workspace_metadata row for {workspace}: publish first (T2.5); "
                      "upstream would INSERT it, which needs LOAD_PRIV")
    files = _rows(cur, f"SELECT COUNT(*) AS files FROM system_mcp.active_store_{workspace}")[0]["files"]
    if not files:
        return Result(False, "semantic store", f"workspace {workspace} has no active files")
    return Result(True, "semantic store",
                  f"workspace {workspace} semantic_version={rows[0]['semantic_version']}, {files} active files")


def max_user_connections(cur: Any) -> str:
    try:
        props = {r["Key"]: r["Value"] for r in _rows(cur, "SHOW PROPERTY")}
    except pymysql.MySQLError as e:
        return f"unavailable ({_brief(e)})"
    return props.get("max_user_connections", "?")


def run_probe(cur: Any, probe: Probe) -> Result:
    name = f"probe {probe.name}"
    try:
        _rows(cur, probe.sql)
    except pymysql.MySQLError as e:
        if classify_error(e) == "denied":
            return Result(True, name, f"denied ({_brief(e)})")
        return Result(False, name, f"inconclusive, expected denied: {_brief(e)}")
    return Result(False, name, "ALLOWED, expected denied")


class _Messages(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def upstream_store_init(settings: Settings, workspace: str) -> tuple[bool, str]:
    """What every semantic tool call runs first, as the service account (service-credential mode)."""
    set_doris_endpoint(settings.doris_host, settings.doris_port)
    set_service_credentials(settings.doris_user, settings.doris_password)
    try:
        found = DorisStore.discover_workspaces()  # CREATE DATABASE IF NOT EXISTS system_mcp; SHOW TABLES
        if workspace not in found:
            return False, f"discover_workspaces found {sorted(found)}, not {workspace!r}"
        DorisStore._table_cache.pop(workspace, None)
        logger, handler = logging.getLogger(_STORE_LOGGER), _Messages()
        logger.addHandler(handler)
        try:
            DorisStore(workspace)  # CREATE DATABASE/TABLE IF NOT EXISTS, metadata SELECT; logs and swallows errors
        finally:
            logger.removeHandler(handler)
        if not DorisStore._table_cache.get(workspace):
            return False, "; ".join(handler.messages) or "table init failed"
        return True, f"discover_workspaces -> {workspace}; CREATE DATABASE/TABLE IF NOT EXISTS + metadata SELECT ok"
    finally:
        clear_service_credentials()


def _mask(text: str, secrets: Iterable[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, MASK)
    return text


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None,
         connect: Callable[..., Any] = pymysql.connect, out: TextIO = sys.stdout, err: TextIO = sys.stderr,
         store_init: Callable[[Settings, str], tuple[bool, str]] = upstream_store_init) -> int:
    parser = argparse.ArgumentParser(description="Check the Doris privileges of mcp_svc.")
    parser.add_argument("--models", type=Path, default=MODELS_DIR, help="semantic YAML directory (tables)")
    parser.add_argument("--workspace", default="ecom", help="semantic workspace")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env

    if not _WORKSPACE_RE.match(args.workspace):
        print(f"ERROR: workspace must match {_WORKSPACE_RE.pattern}", file=err)
        return 2
    try:
        settings = load_settings(env)
    except SettingsError as e:
        print(f"ERROR: {e}", file=err)
        return 2
    tables = sorted(collect_physical_tables(args.models))
    secrets = [settings.doris_password, settings.doris_host]

    def emit(text: str, stream: TextIO = out) -> None:
        print(_mask(text, secrets), file=stream)

    try:
        conn = connect(host=settings.doris_host, port=settings.doris_port, user=settings.doris_user,
                       password=settings.doris_password, connect_timeout=10, read_timeout=60,
                       autocommit=True, cursorclass=pymysql.cursors.DictCursor)
    except pymysql.MySQLError as e:
        emit(f"FAILED: connect: {e}", err)
        return 1
    results: list[Result] = []
    try:
        with conn.cursor() as cur:
            identity = _rows(cur, "SELECT CURRENT_USER() AS identity")[0]["identity"]
            if not identity.startswith(f"'{EXPECTED_USER}'@"):
                emit(f"ERROR: this checks {EXPECTED_USER}; connected as {identity}", err)
                return 2
            emit(f"connected as {identity}")
            checks: list[tuple[str, Callable[[Any], Result]]] = [
                ("grants", check_grants), ("databases", check_databases),
                ("select", lambda c: check_select(c, tables)),
                ("semantic store", lambda c: check_semantic_store(c, args.workspace))]
            for name, check in checks:
                try:
                    results.append(check(cur))
                except pymysql.MySQLError as e:
                    results.append(Result(False, name, _brief(e)))
                emit(_line(results[-1]))
            emit(f"info  max_user_connections={max_user_connections(cur)}")

            probes = write_probes(identity)
            if env.get("APPLY") != "1":
                emit("DRY-RUN probes (APPLY=1 to run; each write is a no-op if it were allowed):")
                emit(f"  store_init         expect ok      upstream DorisStore('{args.workspace}') as {EXPECTED_USER}: "
                     "CREATE DATABASE/TABLE IF NOT EXISTS + metadata SELECT")
                for probe in probes:
                    emit(f"  {probe.name:<18} expect denied  {probe.sql}   -- {probe.why}")
            else:
                try:
                    ok, detail = store_init(settings, args.workspace)
                except pymysql.MySQLError as e:
                    ok, detail = False, _brief(e)
                results.append(Result(ok, "probe store_init", detail))
                emit(_line(results[-1]))
                for probe in probes:
                    results.append(run_probe(cur, probe))
                    emit(_line(results[-1]))
    except pymysql.MySQLError as e:
        emit(f"FAILED: {_brief(e)}", err)
        return 1
    finally:
        conn.close()
    passed = sum(r.ok for r in results)
    emit(f"{passed}/{len(results)} checks pass")
    return 0 if passed == len(results) else 1


def _line(result: Result) -> str:
    return f"{'ok  ' if result.ok else 'FAIL'}  {result.name}: {result.detail}"


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3
```
期望：`Ran 117 tests`、`OK`。

- [ ] **Step 5：以 `mcp_svc` 跑只读检查（dry-run）**

凭证来自 Secrets Manager（`DORIS_SECRET_ID`）；credentials.env 只提供主机和端口。

```bash
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_SECRET_ID=doris-mcp/mcp_svc AWS_REGION=us-east-1
  exec .venv/bin/python doris/permission_matrix.py )
echo "exit=$?"
```
期望：
```
connected as 'mcp_svc'@'%'
ok    grants: exactly internal.ecom SELECT, internal.system_mcp SELECT+CREATE (+ Doris defaults)
ok    databases: ecom, information_schema, mysql, system_mcp
ok    select: 9 physical tables of the models
ok    semantic store: workspace ecom semantic_version=2, 10 active files
info  max_user_connections=…（也可能是 unavailable (…)，只作记录）
DRY-RUN probes (APPLY=1 to run; each write is a no-op if it were allowed):
  store_init         expect ok      upstream DorisStore('ecom') as mcp_svc: CREATE DATABASE/TABLE IF NOT EXISTS + metadata SELECT
  load_ecom          expect denied  INSERT INTO ecom.dim_brand SELECT * FROM ecom.dim_brand WHERE 1 = 0   -- no LOAD_PRIV on ecom (0 rows)
  …（共 9 个：load_ecom、load_system_mcp、update_system_mcp、delete_system_mcp、create_ecom、drop_ecom、drop_system_mcp、grant、admin）
4/4 checks pass
exit=0
```
如果 `grants` 是 FAIL，说明 Doris 列出了预期之外的默认项：停下来把 FAIL 行给用户看，由用户决定是否修改 R-42 的验收，不要直接改 `EXPECTED_GRANTS`。

- [ ] **Step 6：GATE —— 展示并等待确认**

向用户展示 Step 5 的输出（含探针列表），并说明：
- 以 `mcp_svc` 执行 upstream store 初始化（`CREATE DATABASE/TABLE IF NOT EXISTS`，对象都已存在）和 9 个写探针；
- 期望全部被 Doris 拒绝；即使某条被允许，也不改变任何数据：0 行 INSERT、条件匹配不到任何行的 UPDATE/DELETE、`DROP TABLE IF EXISTS` 一张不存在的表、`CREATE DATABASE IF NOT EXISTS` 已存在的 `ecom`、重复授予已有的权限、只读的 `ADMIN SHOW FRONTEND CONFIG`；
- 如果有探针被允许（ALLOWED），说明权限多给了：停下来报告，不自行修改权限。

用户明确确认后执行：
```bash
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_SECRET_ID=doris-mcp/mcp_svc AWS_REGION=us-east-1 APPLY=1
  exec .venv/bin/python doris/permission_matrix.py )
echo "exit=$?"
```
期望：前 6 行同 Step 5，然后：
```
ok    probe store_init: discover_workspaces -> ecom; CREATE DATABASE/TABLE IF NOT EXISTS + metadata SELECT ok
ok    probe load_ecom: denied (<errno> …)
…（9 个探针都是 ok … denied）
14/14 checks pass
exit=0
```
如果 harness 拦住了这条命令，请用户在提示符里输入 `! <上面的命令>` 自己执行（输出已 mask，不含密码和主机）。

- [ ] **Step 7：收尾**

勾选 T2.3；progress「当前状态」写 T2.3 完成、下一步 T2.6；日志记录 Step 5/6 的结果，包括每个探针被拒时的 errno 和 `max_user_connections`。

```bash
bash scripts/check-secrets.sh
git add doris/permission_matrix.py doris/test/test_permission_matrix.py \
        specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "test(p2): T2.3 mcp_svc permission matrix (exact grants, store init ok, 9 write probes denied)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T2.6：以 `mcp_svc` 经 MCP 对账 + P2 验收

**Files:**
- Modify：`tasks.md`、`progress.md`（如果实测与 design §6.3 不一致，也改 `design.md`）

**Interfaces:**
- Consumes：T2.4 的 `doris/reconcile.py`（`mcp` 模式：P1 的 `build_server` 在进程内以服务账号启动 MCP server，经 fastmcp Client 调用 `list_metrics`、`query_metric`）；T2.5 发布的 `ecom`；T2.2 的 `mcp_svc`
- Produces：R-26 的验收证据；P3 可以直接部署（Runtime 用同一个 secret、同一个 workspace）

- [ ] **Step 1：以 `mcp_svc` 经 MCP server 对账**

```bash
( source /home/ubuntu/AI-code/Doris-test/credentials.env
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_SECRET_ID=doris-mcp/mcp_svc AWS_REGION=us-east-1
  exec .venv/bin/python doris/reconcile.py mcp )
echo "exit=$?"
```
期望：第一行 `published metrics: 22 match /home/ubuntu/AI-code/Doris-mcp-skill-Demo/doris/semantic/ecom`，然后 11 行 `ok    <case> (<n> rows)`（行数同 T2.4 Step 9），最后 `11/11 cases match`、`exit=0`。

- [ ] **Step 2：全部离线测试**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 117 tests / OK
for t in infra/test/test-40-doris-secret.sh scripts/test/test-check-secrets.sh \
         doris/test/test-publish-semantic.sh doris/test/test-apply-admin-sql.sh infra/test/test-lib.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 期望：每行 all passed
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 期望：Ran 77 tests / OK
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3     # 期望：🎉 All tests passed!
git status --short                                                                                   # 期望：只有 tasks.md、progress.md
```

- [ ] **Step 3：收尾**

勾选 T2.6；progress「当前状态」写 T2.6 完成、下一步 T2.7（P1 / P0 评审小修）；日志记录 Step 1 的结果和 Step 2 的测试数。如果 T2.3 / T2.6 的实测与 design §6.1 / §6.3 的描述不一致，同一个 commit 里更新 design.md 并在变更记录里加一行。

```bash
bash scripts/check-secrets.sh
git add specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "test(p2): T2.6 query_metric via the MCP server as mcp_svc matches the storyline SQL (11/11)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T2.7：P1 / P0 整体评审小修（纯离线）

来源：`progress.md`「2026-09-26 P1 整体评审」的 ①–④ 和「2026-09-26 P0 整体评审（opus）」的 M-2、M-8。用户 2026-09-26 决定把它们并入 P2 分支，放在最后。P0 的 M-1、M-3、M-4 已记进 tasks.md 的 T4.1、T4.4、T3.4；M-5、M-6、M-7、M-9 不做。本任务不连 Doris，也不碰 AWS，没有 GATE。

**Files:**
- Modify：`mcp-server/src/tools/profile.py`（`get_query_profile`）、`mcp-server/src/agentcore_ext/settings.py`（`_credentials_from_secret`）、`mcp-server/src/agentcore_ext/app.py`（import、`main()`）
- Test：`mcp-server/test/test_agentcore_profile.py`、`test_agentcore_settings.py`、`test_agentcore_app.py`（共新增 5 个测试，77 → 82）
- Modify：`quick/T0.7-guide.md`（Step 2）、`.gitignore`（CodeZip staging 注释）、`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：P1 的 `get_query_profile(target, query_id, mode="summary", max_chars=20000, *, scope="all", transport=None) -> str`、`load_settings(env=None, secrets_client=None) -> Settings`、`build_server(settings, *, profile_transport=None) -> FastMCP`、`main() -> None`；upstream 的 `core.sensitive_mask.mask_sensitive(text: str) -> str`
- Produces：签名都不变，只改三处行为。
  1. `get_query_profile` 返回的 `profile_text` 和 `total_chars` 都基于 `mask_sensitive` 之后的文本。
  2. 读 secret 失败时抛出的 `SettingsError` 不再链接原异常（`__cause__ is None`）。
  3. `build_server` 抛异常时，`main()` 记一行 ERROR 日志 `Cannot build the MCP server: <类型>: <mask 后的消息>`，然后 `sys.exit(2)`，和配置错误的退出码一致。T2.6 的 `reconcile.py mcp` 直接调用 `build_server`，不经过 `main()`，不受影响。

- [ ] **Step 1：确认分支和工作区**

```bash
git branch --show-current && git status --short
```
期望：只输出 `p2-doris`（T2.6 已提交，工作区干净）。

- [ ] **Step 2：写失败的测试**

`mcp-server/test/test_agentcore_profile.py`：在 `TestGetQueryProfile` 的 `test_full_mode_returns_everything` 之前插入下面的测试。profile 里的 SQL 可能跨行，所以要对整段文本做 mask，只处理 `Sql Statement:` 那一行是不够的。

```python
    async def test_profile_text_is_masked_like_the_sql_preview(self):
        # The profile repeats the whole SQL, which can span lines; list_recent_queries masks its preview.
        text = PROFILE.replace("  - Task Type: QUERY",
                               "  - Sql Statement: SELECT 1\nFROM t WHERE password = 'hunter2-pw'\n  - Task Type: QUERY")
        cases = (("summary", "v2", FakeFe(v2=lambda qid: _ok({"profile": text}))),
                 ("full", "api_text", FakeFe(api_text=lambda qid: httpx.Response(200, text=text))))
        for mode, source, fe in cases:
            with self.subTest(mode=mode):
                data = _body(await get_query_profile(TARGET, QID, mode=mode, transport=fe.transport()))["data"]
                self.assertEqual(data["source"], source)
                self.assertIn("FROM t WHERE password = '****'", data["profile_text"])
                self.assertNotIn("hunter2-pw", data["profile_text"])

```

`mcp-server/test/test_agentcore_settings.py`：在 `TestSettingsErrors` 末尾，也就是 `test_secret_read_failure_names_only_the_error_type` 之后，追加：

```python

    def test_secret_read_failure_does_not_chain_the_original_error(self):
        # A chained error prints its own message (here with the password) in any traceback.
        env = {**BASE, "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}
        client = FakeSecrets(error=TimeoutError(f"endpoint timeout, password={SECRET_PW}"))
        with self.assertRaises(SettingsError) as ctx:
            load_settings(env, secrets_client=client)
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)
```

`mcp-server/test/test_agentcore_app.py` 改三处：

1. 顶部 import 在 `import json` 之前加一行 `import contextlib`。
2. 在 `TestHttpContract` 的 `test_initialize_and_list_tools_without_auth` 之后插入评审 ④ 的端口测试。它固定的是现有行为：
```python

    def test_non_default_ports_reach_the_cluster_config_and_the_fe_url(self):
        env = {**self.env, "DORIS_PORT": "19030", "DORIS_HTTP_PORT": "18030"}
        with patch.object(app_mod, "create_server", wraps=app_mod.create_server) as create, \
                patch.object(app_mod, "register_profile_tools") as register:
            app_mod.build_server(load_settings(env))
        cluster = create.call_args.kwargs["config"].cluster
        self.assertEqual((cluster.fe_host, cluster.fe_mysql_port, cluster.fe_http_port), ("10.9.8.7", 19030, 18030))
        self.assertEqual(register.call_args.args[1].base_url, "http://10.9.8.7:18030")
```
3. 在 `TestMain` 末尾，也就是 `test_bad_settings_exit_2_with_a_clear_message` 之后，追加评审 ③ 的两个测试：
```python

    def _main_exit(self, env, build_error=None):
        build = patch.object(app_mod, "build_server", side_effect=build_error) if build_error else contextlib.nullcontext()
        with patch.dict(os.environ, env, clear=True), \
                patch.object(app_mod, "configure_logging"), build, \
                patch.object(FastMCP, "run") as run, \
                self.assertLogs("doris_new_mcp.agentcore", "ERROR") as logs, \
                self.assertRaises(SystemExit) as exit_:
            app_mod.main()
        run.assert_not_called()
        return exit_.exception.code, logs.output

    def test_build_errors_exit_2_with_one_line(self):
        # e.g. a workspace dir that cannot be created; no traceback, same exit code as bad settings.
        with tempfile.NamedTemporaryFile() as not_a_dir:
            code, output = self._main_exit({**self.env, "DORIS_MCP_WORKSPACE_DIR": f"{not_a_dir.name}/ws"})
        self.assertEqual(code, 2)
        self.assertEqual(len(output), 1)
        self.assertIn("Cannot build the MCP server: NotADirectoryError", output[0])

    def test_build_error_messages_are_masked(self):
        code, output = self._main_exit(self.env, RuntimeError("pool init failed: password=svc-pw"))
        self.assertEqual(code, 2)
        self.assertIn("RuntimeError: pool init failed: password=****", output[0])
        self.assertNotIn("svc-pw", "\n".join(output))
```

- [ ] **Step 3：运行测试，确认失败**

```bash
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | grep -E '^(FAIL|ERROR):|^Ran|^FAILED' | sed 's/ (test_agentcore.*//'
```
期望：
```
ERROR: test_build_error_messages_are_masked
ERROR: test_build_errors_exit_2_with_one_line
FAIL: test_profile_text_is_masked_like_the_sql_preview
FAIL: test_profile_text_is_masked_like_the_sql_preview
FAIL: test_secret_read_failure_does_not_chain_the_original_error
Ran 82 tests in …s
FAILED (failures=3, errors=2)
```
- profile 测试出现两次，分别是 summary 和 full 两个 subTest。
- 两个 ERROR 是因为 `main()` 没有捕获 `NotADirectoryError` / `RuntimeError`。
- 端口测试 `test_non_default_ports_reach_the_cluster_config_and_the_fe_url` 现在就能通过：评审 ④ 指出的是缺测试，不是 bug。下一步用变异确认它能抓住问题。

- [ ] **Step 4：变异检查端口测试**

在临时副本里把 FE URL 的端口写死成 8030，端口测试必须失败；仓库里的文件不动：

```bash
T=$(mktemp -d) && cp -r mcp-server "$T/" && sed -i 's/:{settings.doris_http_port}"/:8030"/' "$T/mcp-server/src/agentcore_ext/app.py" && .venv/bin/python -m unittest discover -s "$T/mcp-server/test" -p test_agentcore_app.py -k test_non_default_ports 2>&1 | grep -E 'AssertionError|^Ran|^FAILED'; rm -rf "$T"
git status --short
```
期望：
- 前三行依次是 `AssertionError: 'http://10.9.8.7:8030' != 'http://10.9.8.7:18030'`、`Ran 1 test in …s`、`FAILED (failures=1)`。
- `git status` 只列出 3 个测试文件。

- [ ] **Step 5：实现三处修复**

`mcp-server/src/tools/profile.py`（`get_query_profile` 里）：`mask_sensitive` 已经在文件顶部 import 过。把

```python
    shown = summarize_profile(text) if mode == "summary" else text
```
替换为
```python
    # The profile repeats the whole SQL (possibly over several lines); mask it like the list preview.
    text = mask_sensitive(text)
    shown = summarize_profile(text) if mode == "summary" else text
```

`mcp-server/src/agentcore_ext/settings.py`（`_credentials_from_secret` 里）：把
```python
    except Exception as e:  # noqa: BLE001 - re-raised with context, never with the secret
        raise SettingsError(f"cannot read secret {secret_id}: {type(e).__name__}") from e
```
替换为
```python
    except Exception as e:  # noqa: BLE001 - only the type: the message may carry request details
        raise SettingsError(f"cannot read secret {secret_id}: {type(e).__name__}") from None
```

`mcp-server/src/agentcore_ext/app.py`：
- 在 `from core.charset import CharsetMiddleware` 之后加一行 `from core.sensitive_mask import mask_sensitive`。
- 把 `main()` 里的
```python
    mcp = build_server(settings)
```
替换为
```python
    try:
        mcp = build_server(settings)
    except Exception as e:  # noqa: BLE001 - one masked line and exit 2, like bad settings
        logger.error("Cannot build the MCP server: %s: %s", type(e).__name__, mask_sensitive(str(e)))
        sys.exit(2)
```

- [ ] **Step 6：运行测试，确认通过**

```bash
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3
git status --short
```
期望：
- 测试输出 `Ran 82 tests`、`OK`。
- `git status` 列出 6 个文件：3 个 src 文件和 3 个测试文件。

- [ ] **Step 7：P0 评审 M-2、M-8 两处文字修正**

M-2：`quick/T0.7-guide.md`「Step 2：取 secret」一节，把说明行和代码块整体替换为下面的内容。原来是多行续行的写法，T0.7 时用户照抄后没有任何输出；design §4.4 已改成单行写法：

````markdown
请在**你自己的终端**里执行，不要用 Claude Code 的 `!` 前缀，这样 secret 不会进入对话。每条命令都是单行，整行复制；`--region`、`--output text`、`--no-cli-pager` 都不能省，否则本机 CLI 配置可能让命令没有任何输出（T0.7 实测）。凭证必须属于账号 `890717383483`。

```bash
# client A secret
aws cognito-idp describe-user-pool-client --region us-east-1 --user-pool-id us-east-1_btuTL63V3 --client-id 2q9be1ub7s5nh8ph4sl87uemr2 --query UserPoolClient.ClientSecret --output text --no-cli-pager
# client B secret
aws cognito-idp describe-user-pool-client --region us-east-1 --user-pool-id us-east-1_btuTL63V3 --client-id 4bf7hnvsugn9trphjtmsfldb4s --query UserPoolClient.ClientSecret --output text --no-cli-pager
# demo 用户名和密码
aws secretsmanager get-secret-value --region us-east-1 --secret-id doris-mcp/cognito-demo-user --query SecretString --output text --no-cli-pager
```
````

M-8：根 `.gitignore` 第 23 行的注释不对。P0 实测 staging 在 `dorismcp/agentcore/.cache/` 下，不在 codeLocation 里。把这行
```
# CodeZip staging: the CLI installs deps into <codeLocation>/agentcore/<runtime>/staging (~107 MB)
```
替换为下面两行，后面的两条 ignore 规则不变：
```
# CodeZip staging lands in dorismcp/agentcore/.cache/<runtime>/staging (~107 MB), ignored there by .cache/*.
# The two entries below only guard against CLI output inside a codeLocation.
```

验证：
```bash
grep -c -- '--no-cli-pager' quick/T0.7-guide.md
grep -n 'CodeZip staging' .gitignore
git check-ignore -q dorismcp/agentcore/.cache/dorismcp/staging/x && echo ignored
```
期望：
- 第一条输出 `4`：3 条命令，加上说明行里提到的一次。
- 第二条输出 `23:# CodeZip staging lands in dorismcp/agentcore/.cache/<runtime>/staging (~107 MB), ignored there by .cache/*.`
- 第三条输出 `ignored`。

- [ ] **Step 8：全部离线测试**

```bash
.venv/bin/python -m unittest discover -s doris/test 2>&1 | tail -3                                  # 期望：Ran 117 tests / OK
for t in infra/test/test-40-doris-secret.sh scripts/test/test-check-secrets.sh \
         doris/test/test-publish-semantic.sh doris/test/test-apply-admin-sql.sh infra/test/test-lib.sh; do
  printf '%s: ' "$t"; bash "$t" 2>&1 | tail -1
done                                                                                                 # 期望：每行 all passed
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' 2>&1 | tail -3    # 期望：Ran 82 tests / OK
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3     # 期望：🎉 All tests passed!
```

- [ ] **Step 9：收尾**

1. 勾选 T2.7。
2. progress「当前状态」写：P2 完成（分支 `p2-doris`，等待整体评审和用户决定合并方式），下一步编写 `plans/P3-deploy.md`；P1 / P0 评审小修已在 T2.7 完成，M-1、M-3、M-4 在 T4.1、T4.4、T3.4。
3. 日志记录 Step 3 和 Step 6 的测试数，以及 Step 4 的变异结果。

```bash
bash scripts/check-secrets.sh
git add mcp-server/src/tools/profile.py mcp-server/src/agentcore_ext/settings.py mcp-server/src/agentcore_ext/app.py \
        mcp-server/test/test_agentcore_profile.py mcp-server/test/test_agentcore_settings.py mcp-server/test/test_agentcore_app.py \
        quick/T0.7-guide.md .gitignore specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "fix(mcp): T2.7 mask profile text, exit 2 on build errors, unchained secret errors

P1 final review items 1-4, P0 review M-2 (single-line secret commands) and M-8 (staging comment).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## P2 完成标准（对照 design §11 P2 行）

- [x] Secrets Manager `doris-mcp/mcp_svc` 存在（32 位字母数字密码），`infra/state.env` 有 `DORIS_SECRET_ARN`；`scripts/check-secrets.sh` 能读到它并做精确值扫描（T2.1）
- [x] `ecom` 已发布到 `system_mcp`：`semantic_version=2`、10 个 active 文件；没有执行任何 GRANT（T2.5，T2.3 复核）
- [x] `mcp_svc` 的 `SHOW GRANTS` 恰好是 R-42 + Doris 默认项；upstream store 初始化通过；9 个写探针全部被 Doris 拒绝（T2.3，14/14）
- [x] `query_metric`（`mcp_svc`，经 MCP server）与故事线 SQL 11/11 到分一致；已发布的 22 个指标与本地模型一致（T2.6）
- [x] P1 整体评审 ①–④ 和 P0 整体评审 M-2、M-8 已修；M-1、M-3、M-4 已记进 tasks.md 的 T4.1、T4.4、T3.4（T2.7）
- [x] 测试：`doris/test` 119 个（T2.4 的评审修复新增 2 个）、4 组 shell 测试 + `test-lib.sh`、P1 的 `test_agentcore_*.py` 82 个（T2.7 新增 5 个）、upstream 离线测试，全部通过（T2.7 Step 8）
- [x] 密码和 Doris 主机地址没有出现在任何输出、日志和提交里；每次提交前 check-secrets（含块 1b）都是 OK
