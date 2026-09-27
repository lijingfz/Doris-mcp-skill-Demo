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
