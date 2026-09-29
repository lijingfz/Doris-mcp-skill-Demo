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
