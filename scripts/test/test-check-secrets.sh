#!/usr/bin/env bash
# Offline tests for the Secrets Manager part of scripts/check-secrets.sh. Runs the script inside a
# throwaway git repo with a fake `aws` on PATH; no AWS access, the real credentials file is not read.
#   bash scripts/test/test-check-secrets.sh
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/check-secrets.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAKE_PW="SmPw0123456789abcdefXYZ"
FAKE_PW2="CgPw0123456789abcdefXYZ"
mkdir -p "$TMP/bin" "$TMP/repo/scripts"
# FAKE_SM / FAKE_SM2: what get-secret-value does for doris-mcp/mcp_svc / doris-mcp/cognito-demo-user
# (readable, scheduled = marked for deletion, gone = not found, denied, anything else = expired token);
# FAKE_STS: the account sts get-caller-identity returns (empty: the token is expired).
cat > "$TMP/bin/aws" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
err() { echo "An error occurred ($1) when calling the $2 operation: $3" >&2; exit 254; }
if [[ "$1 $2" == "sts get-caller-identity" ]]; then
  [[ -n "$FAKE_STS" ]] && { echo "$FAKE_STS"; exit 0; }
  err ExpiredToken GetCallerIdentity "The security token included in the request is expired"
fi
[[ "$1 $2" == "secretsmanager get-secret-value" ]] || err InvalidAction "$1 $2" "not faked"
case "$*" in
  *doris-mcp/mcp_svc*) mode="$FAKE_SM" user=mcp_svc pw="$FAKE_PW" ;;
  *doris-mcp/cognito-demo-user*) mode="$FAKE_SM2" user=demo pw="$FAKE_PW2" ;;
  *) mode=gone ;;
esac
case "$mode" in
  readable) printf '{"username":"%s","password":"%s"}\n' "$user" "$pw"; exit 0 ;;
  scheduled) err InvalidRequestException GetSecretValue \
               "You can't perform this operation on the secret because it was marked for deletion." ;;
  gone) err ResourceNotFoundException GetSecretValue "Secrets Manager can't find the specified secret." ;;
  denied) err AccessDeniedException GetSecretValue "User is not authorized to perform: secretsmanager:GetSecretValue" ;;
  *) err ExpiredTokenException GetSecretValue "The security token included in the request is expired" ;;
esac
FAKE
chmod +x "$TMP/bin/aws"
cp "$SRC" "$TMP/repo/scripts/check-secrets.sh"
git -C "$TMP/repo" init -q
echo "hello" > "$TMP/repo/clean.txt"

FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
run_check() { # FAKE_SM [FAKE_SM2 (default: FAKE_SM)] [FAKE_STS] → sets RC, OUT
  : > "$TMP/aws.log"
  # AWS_REGION points elsewhere, like a shell whose default profile is in another region.
  OUT="$(cd "$TMP/repo" && PATH="$TMP/bin:$PATH" FAKE_LOG="$TMP/aws.log" FAKE_PW="$FAKE_PW" FAKE_PW2="$FAKE_PW2" \
    FAKE_SM="$1" FAKE_SM2="${2:-$1}" FAKE_STS="${3:-}" \
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

printf 'demo login: %s\n' "$FAKE_PW2" > "$TMP/repo/leaky.log.txt"
run_check readable
check "leaked password of the second secret fails the check" "1|yes" \
  "$RC|$(has "$OUT" "LEAK: password of secret doris-mcp/cognito-demo-user found in leaky.log.txt")"
rm "$TMP/repo/leaky.log.txt"

# Generic patterns: a placeholder after aws_secret_access_key is not a secret, a real-looking value is.
# The lines are assembled with printf so that this file itself never matches the pattern.
KEY=aws_secret_access_key
FAKE_AWS_SECRET="wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY01"  # the shape of AWS's documented example key
for value in "..." "<secret>" '${AWS_SECRET_ACCESS_KEY}' "" '"<secret>"'; do
  printf '# be.conf\n%s = %s\n' "$KEY" "$value" > "$TMP/repo/be.conf.md"
  run_check readable
  check "placeholder '$value' after $KEY is not a hit" 0 "$RC"
done
printf '# be.conf\n%s = %s\n' "$KEY" "$FAKE_AWS_SECRET" > "$TMP/repo/be.conf.md"
run_check readable
check "a real-looking $KEY fails the check" "1|yes" "$RC|$(has "$OUT" "LEAK: secret-like pattern in be.conf.md")"
check "never prints the $KEY value" no "$(has "$OUT" "$FAKE_AWS_SECRET")"
printf '%s="%s"\n' "$KEY" "$FAKE_AWS_SECRET" > "$TMP/repo/be.conf.md"
run_check readable
check "a quoted $KEY without spaces fails the check" 1 "$RC"
rm "$TMP/repo/be.conf.md"

# An exact-value check that could not run is not a pass (P2 whole review M4).
run_check expired
check "unreadable secrets fail the check" 1 "$RC"
check "the failure names the secret" yes "$(has "$OUT" "FAIL: cannot read secret doris-mcp/mcp_svc")"
check "the last line says FAILED" "check-secrets: FAILED — do not commit" "$(tail -n 1 <<<"$OUT")"

# A secret that infra/99-cleanup.sh deleted has nothing left to compare: skipped, not failed (P5 Task 9).
# "Not found" alone proves nothing (another account's credentials get it for every secret), so it counts
# only when the caller is the account in infra/state.env.
PROJECT_ACCOUNT=111122223333
mkdir -p "$TMP/repo/infra"; printf 'AWS_REGION=us-east-1\nACCOUNT_ID=%s\n' "$PROJECT_ACCOUNT" > "$TMP/repo/infra/state.env"
run_check scheduled
check "secrets marked for deletion are skipped" 0 "$RC"
check "the skip names the secret" yes "$(has "$OUT" "SKIP: secret doris-mcp/mcp_svc is scheduled for deletion")"
check "the OK line counts the skipped secrets" yes "$(has "$(tail -n 1 <<<"$OUT")" "2 deleted secrets skipped")"
run_check gone gone "$PROJECT_ACCOUNT"
check "secrets not found in the project's account are skipped" "0|yes" \
  "$RC|$(has "$OUT" "SKIP: secret doris-mcp/cognito-demo-user no longer exists in the project's account")"
check "asks sts in us-east-1" yes "$(has "$(grep '^sts ' "$TMP/aws.log")" "--region us-east-1")"
run_check gone gone 444455556666
check "not found in another account fails the check" "1|yes" "$RC|$(has "$OUT" "FAIL: cannot read secret doris-mcp/mcp_svc")"
check "never prints the caller's account" no "$(has "$OUT" 444455556666)"
run_check gone gone ""
check "not found with an expired sts token fails the check" 1 "$RC"
run_check denied denied "$PROJECT_ACCOUNT"
check "access denied in the project's account fails the check" 1 "$RC"
run_check expired expired "$PROJECT_ACCOUNT"
check "an expired token fails the check even when sts answers" 1 "$RC"
rm "$TMP/repo/infra/state.env"
run_check gone gone ""
check "not found without infra/state.env fails the check (no account to compare)" 1 "$RC"
run_check gone gone "$PROJECT_ACCOUNT"
check "not found without infra/state.env fails even when sts answers" 1 "$RC"
printf 'AWS_REGION=us-east-1\nACCOUNT_ID=%s\n' "$PROJECT_ACCOUNT" > "$TMP/repo/infra/state.env"

printf 'demo login: %s\n' "$FAKE_PW2" > "$TMP/repo/leaky.log.txt"
run_check scheduled readable
check "a skipped secret does not hide a leak of the other one" "1|yes|yes" \
  "$RC|$(has "$OUT" "SKIP: secret doris-mcp/mcp_svc")|$(has "$OUT" "LEAK: password of secret doris-mcp/cognito-demo-user found in leaky.log.txt")"
rm "$TMP/repo/leaky.log.txt"
run_check scheduled expired
check "an error after a skipped secret still fails the check" "1|yes" "$RC|$(has "$OUT" "FAIL: cannot read secret doris-mcp/cognito-demo-user")"
run_check readable scheduled
check "one readable and one skipped secret pass" "0|yes" "$RC|$(has "$(tail -n 1 <<<"$OUT")" "1 deleted secrets skipped")"
run_check readable
check "the OK line mentions no skips when every secret was read" no "$(has "$(tail -n 1 <<<"$OUT")" "skipped")"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
