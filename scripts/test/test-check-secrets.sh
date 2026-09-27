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
