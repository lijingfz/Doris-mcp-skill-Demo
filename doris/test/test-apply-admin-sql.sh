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
