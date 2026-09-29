#!/usr/bin/env bash
# Offline tests for scripts/demo-check.sh: fake `aws` on PATH, a fake PYTHON and a fake TOKEN_CMD that record
# argv and which DORIS_* / GW_TOKEN variables reach them (names; values only as match/other), and print canned
# output with a TEST-NET address and an https URL for the mask. No AWS, no Doris, no Gateway.
#   bash scripts/test/test-demo-check.sh
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/demo-check.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
TOKEN="tok-fixture-9f8e7d6c5b4a"

# names VAR... helper for the fakes: the DORIS_* and GW_TOKEN variables in the environment, sorted.
cat > "$TMP/names.sh" <<'NAMES'
names() { compgen -e | grep -E '^(DORIS_|GW_TOKEN$)' | sort | paste -sd ' '; }
token_state() { if [[ -z "${GW_TOKEN+x}" ]]; then echo none; elif [[ "$GW_TOKEN" == tok-fixture-9f8e7d6c5b4a ]]; then echo match; else echo other; fi; }
NAMES
# Fake AWS CLI. FAKE_ACCOUNT, FAKE_GW_STATUS, FAKE_TARGET_STATUS; FAKE_AWS_FAIL="service operation" fails that call.
cat > "$TMP/bin/aws" <<'FAKE'
#!/usr/bin/env bash
source "$FAKE_DIR/names.sh"
{ echo "aws: $*"; echo "aws-env $1.$2: $(names)"; } >> "$FAKE_LOG"
if [[ "$1 $2" == "${FAKE_AWS_FAIL:-}" ]]; then
  echo "An error occurred (ExpiredToken) calling https://api.example.test/x from 198.51.100.23" >&2; exit 254
fi
case "$1 $2" in
  "sts get-caller-identity") echo "${FAKE_ACCOUNT:-111122223333}" ;;
  "bedrock-agentcore-control get-gateway") echo "${FAKE_GW_STATUS:-READY}" ;;
  "bedrock-agentcore-control get-gateway-target") echo "${FAKE_TARGET_STATUS:-READY}" ;;
  "logs filter-log-events") echo '{"events": [{"message": "doris_new_mcp.audit: {}"}]}' ;;
  "cloudwatch get-metric-data") echo '{"MetricDataResults": []}' ;;
  *) echo "fake aws: unexpected call: $*" >&2; exit 99 ;;
esac
FAKE
# Fake PYTHON: "$PYTHON" SCRIPT ARGS... ; the tag is the script's name plus its subcommand, if any.
# FAKE_FAIL=TAG makes that one exit 1; FAKE_TOOLS (12) and FAKE_CONNS (12) shape mcp_smoke's output.
cat > "$TMP/bin/fake-python" <<'FAKE'
#!/usr/bin/env bash
source "$FAKE_DIR/names.sh"
script="$(basename "$1" .py)"; tag="$script"
for a in "${@:2}"; do case "$a" in list|flow|conns|queries|report) tag="$script.$a"; break ;; esac; done
{ echo "py: $*"; echo "py-env $tag: $(names)"; echo "py-token $tag: $(token_state)"
  echo "py-region $tag: ${AWS_REGION:-none}"
  if [[ "$tag" == reconcile ]]; then
    case "${DORIS_PASSWORD-}" in ro-pass-fixture) pw=ro ;; root-pass-fixture) pw=root ;; "") pw=none ;; *) pw=other ;; esac
    echo "py-doris: ${DORIS_HOST-none}|${DORIS_PORT-none}|${DORIS_USER-none}|$pw"
  fi
  case "$tag" in audit_check|gw_latency.report) echo "py-stdin $tag: $(head -c 20)" ;; esac; } >> "$FAKE_LOG"
if [[ "$tag" == "${FAKE_FAIL:-}" ]]; then echo "FAIL: fixture failure talking to 198.51.100.23"; exit 1; fi
case "$tag" in
  mcp_smoke.list)
    for ((i = 1; i <= ${FAKE_TOOLS:-12}; i++)); do echo "  doris___tool$i"; done; echo "tools: ${FAKE_TOOLS:-12}"
    [[ "${FAKE_TOOLS:-12}" == 12 ]] || { echo "FAIL: expected 12 tools"; exit 1; } ;;
  mcp_smoke.flow) echo "connected+initialized in 640 ms (https://gw.example.test/mcp)"; echo "  [PASS] profile"
    echo "flow: 6/6 passed" ;;
  mcp_smoke.conns) echo "connections: ${FAKE_CONNS:-12} (Sleep ${FAKE_CONNS:-12}) from 2 distinct hosts; users mcp_svc; max idle 30 s"
    echo "  [PASS] host prefix 172.31.: ${FAKE_CONNS:-12}/${FAKE_CONNS:-12} connections"
    echo "  [PASS] idle connections <= 610 s: 0 over" ;;
  reconcile) echo "reference SQL on 198.51.100.7:9030"; echo "11/11 cases match" ;;
  permission_matrix) echo "identity mcp_svc@172.31.%"; echo "5/5 checks pass" ;;
  audit_check) echo "audit: 40 records, 0 failures" ;;
  gw_latency.queries) echo '[{"Id": "q1"}]' ;;
  gw_latency.report) echo "doris___execute_query 10:05 3 calls max 820 ms" ;;
  *) echo "fake python: unexpected: $*" >&2; exit 99 ;;
esac
FAKE
# Fake TOKEN_CMD: prints the fixture token; FAKE_TOKEN_FAIL=1 fails with an error naming a URL and an address.
cat > "$TMP/token.sh" <<'FAKE'
source "$FAKE_DIR/names.sh"
echo "token-env: $(names)" >> "$FAKE_LOG"
if [[ "${FAKE_TOKEN_FAIL:-}" == 1 ]]; then echo "token request failed: https://auth.example.test/oauth2/token 198.51.100.24" >&2; exit 1; fi
echo "tok-fixture-9f8e7d6c5b4a"
FAKE
chmod +x "$TMP/bin/aws" "$TMP/bin/fake-python"
CRED_LINES=('DORIS_HOST=198.51.100.7' 'DORIS_MYSQL_PORT=9030' 'DORIS_HTTP_PORT=8030' 'DORIS_ROOT_USER=root'
  'DORIS_ROOT_PASSWORD=root-pass-fixture' 'DORIS_RO_USER=demo_ro' 'DORIS_RO_PASSWORD=ro-pass-fixture')
printf '%s\n' "${CRED_LINES[@]}" > "$TMP/cred.env"
printf 'export %s\n' "${CRED_LINES[@]}" > "$TMP/cred-export.env"
printf '%s\n' '# test state' 'AWS_REGION=us-east-1' 'ACCOUNT_ID=111122223333' 'GW_ID=gw-fixture0001' \
  'GW_TARGET_ID=TGTFIXTURE1' 'GW_URL=https://gw.example.test/mcp' 'RUNTIME_ID=dorismcp_dorismcp-AbCdEf1234' \
  'RUNTIME_URL=https://runtime.example.test/invocations?qualifier=DEFAULT' 'DORIS_SG=sg-doris' \
  'DORIS_SECRET_ARN=arn:aws:secretsmanager:us-east-1:111122223333:secret:doris-mcp/mcp_svc-AbCdEf' > "$TMP/state.env"

FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
EXTRA=()  # VAR=value pairs for the next run (the caller's environment, fake knobs)
CRED="$TMP/cred.env"
# run_check ARGS... — sets RC, OUT (stdout), ERR (stderr), LOG (what the fakes saw)
run_check() {
  : > "$TMP/fake.log"
  OUT="$(env -u GW_TOKEN -u MAX_CONNS -u TOKEN_CMD -u PYTHON -u CREDENTIALS_FILE -u AWS_REGION "${EXTRA[@]}" \
    PATH="$TMP/bin:$PATH" FAKE_DIR="$TMP" FAKE_LOG="$TMP/fake.log" STATE_FILE="$TMP/state.env" \
    PYTHON="$TMP/bin/fake-python" CREDENTIALS_FILE="$CRED" TOKEN_CMD="bash $TMP/token.sh" \
    bash "$SCRIPT" "$@" 2>"$TMP/err")"
  RC=$?; ERR="$(cat "$TMP/err")"; LOG="$(cat "$TMP/fake.log")"
}
has() { [[ "$1" == *"$2"* ]] && echo yes || echo no; }
count() { grep -c -- "$2" <<<"$1"; }
field() { sed -n "s/^$2: //p" <<<"$1"; } # LOG PREFIX → the recorded values, one per line
verdicts() { grep -E '^\[(PASS|FAIL)\] ' <<<"$OUT"; }
# The DORIS_* names that reached a child other than reconcile, as "child: NAME" lines.
doris_elsewhere() {
  grep -E '^(aws-env|token-env|py-env)' <<<"$LOG" | grep -v '^py-env reconcile:' | grep -E 'DORIS_' \
    | sed -E 's/^([^:]*):.*/\1/' | paste -sd ' '
}
# The token and the credential values must never show up in an argv, in the output or in the log.
leaks() { grep -cE -- "$TOKEN|root-pass-fixture|ro-pass-fixture|caller-(token|root|ro|admin)" <<<"$OUT
$ERR
$LOG"; }
SMOKE="scripts/mcp_smoke.py --url https://gw.example.test/mcp --bearer-env GW_TOKEN --timeout 60"
RT_URL="https://runtime.example.test/invocations?qualifier=DEFAULT"
PRE_PASS="[PASS] account
[PASS] gateway READY
[PASS] target READY
[PASS] token
[PASS] list 12 tools
[PASS] flow
[PASS] reconcile
[PASS] permission matrix
[PASS] conns
[PASS] conns <= MAX_CONNS"

# --- pre, everything fine --------------------------------------------------------------
run_check pre
check "pre: exit 0" 0 "$RC"
check "pre: every check passes, in order" "$PRE_PASS" "$(verdicts)"
check "pre: summary line" "demo-check pre: 10/10 passed" "$(tail -1 <<<"$OUT")"
check "pre: AWS reads (account, Gateway, target), with the region" \
  "sts get-caller-identity --region us-east-1 --query Account --output text
bedrock-agentcore-control get-gateway --gateway-identifier gw-fixture0001 --region us-east-1 --query status --output text
bedrock-agentcore-control get-gateway-target --gateway-identifier gw-fixture0001 --target-id TGTFIXTURE1 --region us-east-1 --query status --output text" \
  "$(field "$LOG" aws)"
check "pre: python children and their arguments, in order" \
  "$SMOKE list --expect 12
$SMOKE flow --prefix doris___
doris/reconcile.py mcp --url $RT_URL
doris/permission_matrix.py --url $RT_URL --expect-host 172.31.%
$SMOKE conns --prefix doris___ --expect-host-prefix 172.31. --max-idle 610" "$(field "$LOG" py)"
check "pre: the token is in mcp_smoke's environment, and only there" \
  "py-token mcp_smoke.list: match|py-token mcp_smoke.flow: match|py-token reconcile: none|py-token permission_matrix: none|py-token mcp_smoke.conns: match" \
  "$(grep '^py-token' <<<"$LOG" | paste -sd '|')"
check "pre: no GW_TOKEN in the environment of aws or the token command" 0 "$(grep -E '^(aws-env|token-env)' <<<"$LOG" | grep -c GW_TOKEN)"
check "pre: the token and the credential values never in argv, output or log" 0 "$(leaks)"
check "pre: reconcile gets exactly DORIS_HOST/PORT/USER/PASSWORD" "DORIS_HOST DORIS_PASSWORD DORIS_PORT DORIS_USER" \
  "$(field "$LOG" "py-env reconcile")"
check "pre: reconcile's Doris settings are the read-only account's" "198.51.100.7|9030|demo_ro|ro" "$(field "$LOG" py-doris)"
check "pre: reconcile runs in us-east-1" us-east-1 "$(field "$LOG" "py-region reconcile")"
check "pre: no DORIS_* variable reaches any other child (state.env's DORIS_SG included)" "" "$(doris_elsewhere)"
check "pre: output masked (no IPv4, no https URL; <ip> and <url> shown)" "0|0|yes|yes" \
  "$(count "$OUT" '198\.51\.100\.')|$(count "$OUT" 'https://')|$(has "$OUT" '<ip>')|$(has "$OUT" '<url>')"
check "pre: nothing on stderr" "" "$ERR"

# --- the credentials file with export lines, and a caller who exported a token and Doris variables ---------
CRED="$TMP/cred-export.env"
EXTRA=(GW_TOKEN=caller-token-fixture DORIS_ROOT_USER=caller-root DORIS_ROOT_PASSWORD=caller-root-pw
       DORIS_RO_USER=caller-ro DORIS_RO_PASSWORD=caller-ro-pw DORIS_ADMIN_PASSWORD=caller-admin-pw DORIS_HOST=203.0.113.99)
run_check pre
check "caller-exported + export lines: exit 0, all checks pass" "0|$PRE_PASS" "$RC|$(verdicts)"
check "caller-exported + export lines: reconcile still gets exactly the four, from the file" \
  "DORIS_HOST DORIS_PASSWORD DORIS_PORT DORIS_USER|198.51.100.7|9030|demo_ro|ro" \
  "$(field "$LOG" "py-env reconcile")|$(field "$LOG" py-doris)"
check "caller-exported + export lines: no DORIS_* anywhere else" "" "$(doris_elsewhere)"
check "caller-exported + export lines: mcp_smoke gets the fresh token, nobody else any" \
  "match match match|0" \
  "$(grep '^py-token mcp_smoke' <<<"$LOG" | sed 's/.*: //' | paste -sd ' ')|$(grep -E '^(aws-env|token-env)|^py-env (reconcile|permission_matrix)' <<<"$LOG" | grep -c GW_TOKEN)"
check "caller-exported + export lines: no leak" 0 "$(leaks)"
CRED="$TMP/cred.env"; EXTRA=()

# --- one check fails: [FAIL], the count, exit 1 ----------------------------------------------------------
fails_one() { # NAME EXPECTED-FAIL-LINE SUMMARY ARGS... (with EXTRA set by the caller)
  local name="$1" line="$2" summary="$3"; shift 3
  run_check "$@"
  check "$name: exit 1" 1 "$RC"
  check "$name: $line" yes "$(has "$(verdicts)" "$line")"
  check "$name: summary" "$summary" "$(tail -1 <<<"$OUT")"
  check "$name: masked, no leak" "0|0|0" "$(count "$OUT" '198\.51\.100\.')|$(count "$OUT" 'https://')|$(leaks)"
}
EXTRA=(FAKE_ACCOUNT=000000000000); fails_one "wrong account" "[FAIL] account" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_GW_STATUS=UPDATING); fails_one "Gateway UPDATING" "[FAIL] gateway READY" "demo-check pre: 9/10 passed" pre
check "Gateway UPDATING: the status is shown" yes "$(has "$OUT" "UPDATING")"
EXTRA=(FAKE_TARGET_STATUS=FAILED); fails_one "target FAILED" "[FAIL] target READY" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_AWS_FAIL="bedrock-agentcore-control get-gateway"); fails_one "get-gateway error" "[FAIL] gateway READY" \
  "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_TOOLS=11); fails_one "11 tools" "[FAIL] list 12 tools" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_FAIL=reconcile); fails_one "reconcile fails" "[FAIL] reconcile" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_FAIL=permission_matrix); fails_one "permission matrix fails" "[FAIL] permission matrix" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_CONNS=81); fails_one "81 connections" "[FAIL] conns <= MAX_CONNS" "demo-check pre: 9/10 passed" pre
check "81 connections: conns itself passes, the count is shown" "yes|yes" "$(has "$OUT" "[PASS] conns")|$(has "$OUT" "81")"
EXTRA=(FAKE_CONNS=80); run_check pre
check "80 connections (= MAX_CONNS): passes" "0|demo-check pre: 10/10 passed" "$RC|$(tail -1 <<<"$OUT")"
EXTRA=(FAKE_CONNS=6 MAX_CONNS=5); fails_one "MAX_CONNS=5, 6 connections" "[FAIL] conns <= MAX_CONNS" "demo-check pre: 9/10 passed" pre
EXTRA=(FAKE_CONNS=5 MAX_CONNS=5); run_check pre
check "MAX_CONNS=5, 5 connections: passes" 0 "$RC"

EXTRA=(FAKE_TOKEN_FAIL=1); run_check pre
check "no token: exit 1" 1 "$RC"
check "no token: the Gateway checks fail without calling mcp_smoke; the Runtime checks still run" \
  "[PASS] account
[PASS] gateway READY
[PASS] target READY
[FAIL] token
[FAIL] list 12 tools
[FAIL] flow
[PASS] reconcile
[PASS] permission matrix
[FAIL] conns
[FAIL] conns <= MAX_CONNS|demo-check pre: 5/10 passed|0" "$(verdicts)|$(tail -1 <<<"$OUT")|$(count "$LOG" '^py: scripts/mcp_smoke')"
check "no token: says why, token error masked" "yes|0|0" \
  "$(has "$OUT" "skipped: no Gateway token")|$(count "$OUT$ERR" '198\.51\.100\.')|$(count "$OUT$ERR" 'https://')"
EXTRA=()

# --- post -------------------------------------------------------------------------------------------
ms() { echo $(( $(date -u -d "$1" +%s) * 1000 + $2 )); } # ISO-8601 MILLIS → epoch ms
SINCE="$(ms 2026-09-28T10:00:30Z 500)" UNTIL="$(ms 2026-09-28T10:30:00Z 0)"
run_check post --since "$SINCE" --until "$UNTIL"
check "post: exit 0" 0 "$RC"
check "post: checks in order" "[PASS] audit
[PASS] latency
[PASS] token
[PASS] conns
[PASS] conns <= MAX_CONNS|demo-check post: 5/5 passed" "$(verdicts)|$(tail -1 <<<"$OUT")"
check "post: filter-log-events on the Runtime's log group, the exact window in ms, audit records only" \
  "logs filter-log-events --region us-east-1 --log-group-name /aws/bedrock-agentcore/runtimes/dorismcp_dorismcp-AbCdEf1234-DEFAULT --start-time $SINCE --end-time $UNTIL --filter-pattern \"doris_new_mcp.audit\" --output json" \
  "$(grep '^aws: logs' <<<"$LOG" | sed 's/^aws: //')"
check "post: audit_check --failures reads filter-log-events' output" "scripts/audit_check.py --failures|{\"events\": [{\"messag" \
  "$(field "$LOG" py | grep audit_check)|$(field "$LOG" "py-stdin audit_check")"
check "post: latency window widened to whole minutes (since 10:00:30.5 -> 10:00, until 10:30 stays)" \
  "cloudwatch get-metric-data --region us-east-1 --start-time 2026-09-28T10:00:00Z --end-time 2026-09-28T10:30:00Z --metric-data-queries [{\"Id\": \"q1\"}] --output json" \
  "$(grep '^aws: cloudwatch' <<<"$LOG" | sed 's/^aws: //')"
check "post: gw_latency queries for this Gateway's ARN, report reads get-metric-data's output" \
  "scripts/gw_latency.py queries --gateway-arn arn:aws:bedrock-agentcore:us-east-1:111122223333:gateway/gw-fixture0001|scripts/gw_latency.py report|{\"MetricDataResults\"" \
  "$(field "$LOG" py | grep gw_latency | paste -sd '|')|$(field "$LOG" "py-stdin gw_latency.report")"
check "post: no pre-only check (sts, Gateway status, reconcile, permission matrix, list, flow)" 0 \
  "$(grep -cE 'sts |get-gateway|reconcile|permission_matrix| list | flow ' <<<"$(field "$LOG" aws; field "$LOG" py)")"
check "post: token only in mcp_smoke conns; no leak" "py-token mcp_smoke.conns: match|0" \
  "$(grep '^py-token' <<<"$LOG" | grep -v ': none$' | paste -sd '|')|$(leaks)"
SINCE="$(ms 2026-09-28T10:00:59Z 999)" UNTIL="$(ms 2026-09-28T10:29:01Z 0)"
run_check post --since "$SINCE" --until "$UNTIL"
check "post: since 10:00:59.999 -> 10:00, until 10:29:01 -> 10:30" "--start-time 2026-09-28T10:00:00Z --end-time 2026-09-28T10:30:00Z" \
  "$(grep '^aws: cloudwatch' <<<"$LOG" | grep -oE -- '--start-time [^ ]+ --end-time [^ ]+')"
EXTRA=(FAKE_FAIL=audit_check); fails_one "audit failures" "[FAIL] audit" "demo-check post: 4/5 passed" post --since "$SINCE" --until "$UNTIL"
EXTRA=(FAKE_FAIL=gw_latency.report); fails_one "slow minute" "[FAIL] latency" "demo-check post: 4/5 passed" post --since "$SINCE" --until "$UNTIL"
EXTRA=(FAKE_AWS_FAIL="logs filter-log-events"); fails_one "filter-log-events error" "[FAIL] audit" "demo-check post: 4/5 passed" \
  post --since "$SINCE" --until "$UNTIL"
EXTRA=()

# --- bad arguments: usage on stderr, exit 2, nothing runs ---------------------------------------------
bad() { # NAME ARGS...
  local name="$1"; shift
  run_check "$@"
  check "bad arguments ($name): exit 2, usage on stderr, no call" "2|yes||" "$RC|$(has "$ERR" "usage:")|$LOG|$OUT"
}
S=1790000000000
bad "none"; bad "unknown mode" bogus; bad "pre with an argument" pre --since "$S"
bad "post without a window" post; bad "post without --until" post --since "$S"
bad "post without --since" post --until "$S"; bad "--until without a value" post --since "$S" --until
bad "non-numeric --since" post --since abc --until "$S"; bad "seconds, not ms" post --since 1790000000 --until 1790000060
bad "since = until" post --since "$S" --until "$S"; bad "since > until" post --since $((S + 60000)) --until "$S"
bad "unknown option" post --since "$S" --until $((S + 60000)) --verbose
EXTRA=(MAX_CONNS=eighty); bad "MAX_CONNS not a number" pre; EXTRA=()

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
