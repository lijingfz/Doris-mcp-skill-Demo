#!/usr/bin/env bash
# Offline tests for infra/35-runtime-role.sh. Fake `aws` and `sleep` on PATH record every call; no AWS access.
#   bash infra/test/test-35-runtime-role.sh
set -uo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
SECRET_ARN="arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-AbCdEf"
ROLE_ARN="arn:aws:iam::111122223333:role/doris-mcp-runtime-role"
mkdir -p "$TMP/bin"
# Fake AWS CLI. FAKE_ROLE = missing | exists | warn | foreign | denied | badcreate.
# file:// documents are copied to $FAKE_DIR.
cat > "$TMP/bin/aws" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
doc() { for a in "$@"; do [[ "$a" == file://* ]] && cat "${a#file://}"; done; }
case "$1 $2" in
  "iam get-role")
    case "$FAKE_ROLE" in
      exists)  echo "arn:aws:iam::111122223333:role/doris-mcp-runtime-role" ;;
      warn)    echo "warning: this CLI version is deprecated" >&2
               echo "arn:aws:iam::111122223333:role/doris-mcp-runtime-role" ;;
      foreign) echo "arn:aws:iam::999999999999:role/doris-mcp-runtime-role" ;;
      denied)  echo "An error occurred (AccessDenied) when calling the GetRole operation" >&2; exit 254 ;;
      *)       echo "An error occurred (NoSuchEntity) when calling the GetRole operation: The role with name doris-mcp-runtime-role cannot be found." >&2; exit 254 ;;
    esac ;;
  "iam create-role")
    doc "$@" > "$FAKE_DIR/trust.json"
    if [[ "$FAKE_ROLE" == badcreate ]]; then echo "arn:aws:iam::111122223333:role/other-role"
    else echo "arn:aws:iam::111122223333:role/doris-mcp-runtime-role"; fi ;;
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
check "apply/bare * secret ARN: fails" 1 "$RC"
check "apply/bare * secret ARN: no IAM write" 0 "$(grep -cE 'create-role|put-role-policy' <<<"$LOG")"
run_script missing 1 "arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-*"
check "apply/secret ARN mcp_svc-*: fails" 1 "$RC"
check "apply/secret ARN mcp_svc-*: no IAM write" 0 "$(grep -cE 'create-role|put-role-policy' <<<"$LOG")"
run_script missing 1 "arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-??????"
check "apply/secret ARN mcp_svc-??????: fails" 1 "$RC"
check "apply/secret ARN mcp_svc-??????: no IAM write" 0 "$(grep -cE 'create-role|put-role-policy' <<<"$LOG")"
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

# The role ARN ends up in state.env, which every infra script sources: only the exact ARN may get there.
run_script warn 1 "$SECRET_ARN"
check "apply/get-role warning on stderr: exit 0" 0 "$RC"
check "apply/get-role warning on stderr: no create-role" no "$(has "$LOG" "create-role")"
check "apply/get-role warning on stderr: RT_ROLE_ARN is the clean ARN" "RT_ROLE_ARN=$ROLE_ARN" "$(grep '^RT_ROLE_ARN=' "$TMP/state.env")"
check "apply/get-role warning on stderr: warning not in state.env" 0 "$(grep -c 'warning' "$TMP/state.env")"

run_script badcreate 1 "$SECRET_ARN"
check "apply/create-role other ARN: fails" 1 "$RC"
check "apply/create-role other ARN: no put-role-policy" 0 "$(grep -c 'put-role-policy' <<<"$LOG")"
check "apply/create-role other ARN: state.env unchanged" no "$(has "$(cat "$TMP/state.env")" "RT_ROLE_ARN")"
check "apply/create-role other ARN: FATAL does not echo it" no "$(has "$OUT" "other-role")"

run_script foreign 1 "$SECRET_ARN"
check "apply/get-role other-account ARN: fails" 1 "$RC"
check "apply/get-role other-account ARN: no IAM write" 0 "$(grep -cE 'create-role|put-role-policy' <<<"$LOG")"
run_script foreign 0 "$SECRET_ARN"
check "dry-run/get-role other-account ARN: fails" 1 "$RC"
check "dry-run/get-role other-account ARN: no state_set" no "$(has "$OUT" "state_set")"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
