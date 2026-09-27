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
CALLER_ENV=()  # extra VAR=value pairs the caller has already exported
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
run_wrapper() { # APPLY [ARGS...] → sets RC, REC (what the stub saw)
  local apply="$1"; shift
  : > "$TMP/stub.out"
  env -u DORIS_HOST -u DORIS_ROOT_PASSWORD -u DORIS_RO_PASSWORD "${CALLER_ENV[@]}" STUB_OUT="$TMP/stub.out" \
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

# M1: `source` keeps the export attribute of a variable the caller already exported, so without the
# wrapper's unset the file's root/ro values (and the caller's admin password) would reach python.
CALLER_ENV=(DORIS_ROOT_USER=caller DORIS_ROOT_PASSWORD=CallerRootPw DORIS_RO_USER=caller
            DORIS_RO_PASSWORD=CallerRoPw DORIS_ADMIN_PASSWORD=CallerAdminPw)
run_wrapper 0
CALLER_ENV=()
check "caller-exported: dry-run exit 0, admin user from the file" "0|yes" "$RC|$(has "$REC" "env: DORIS_ADMIN_USER=root")"
check "caller-exported DORIS_ROOT_* / DORIS_RO_* / DORIS_ADMIN_PASSWORD do not reach python" "no|no|no" \
  "$(has "$REC" "DORIS_ROOT_")|$(has "$REC" "DORIS_RO_")|$(has "$REC" "DORIS_ADMIN_PASSWORD")"

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
