#!/usr/bin/env bash
# P5 — Checks before and after each rehearsal / the demo. Read-only: AWS reads, MCP calls through the Gateway
# (tools/list, a fixed read-only flow, the connection count) and the Runtime (reconcile, permission matrix).
#   bash scripts/demo-check.sh pre                          # before: is everything up and consistent?
#   bash scripts/demo-check.sh post --since MS --until MS   # after: audit records and latency of that window
# MS = epoch milliseconds (e.g. `date +%s%3N` when the rehearsal starts and ends).
# pre:  account (== ACCOUNT_ID), Gateway READY, target READY, token, tools/list = 12 tools, the doris___ flow,
#       reconcile (read-only Doris account, over the Runtime), permission matrix, connections (host prefix
#       172.31., idle <= 610 s) and their count <= MAX_CONNS (mcp_svc has max_user_connections=100).
# post: audit (every doris_new_mcp.audit record of the window, audit_check --failures), latency (the window
#       widened to whole minutes: --since down, --until up; gw_latency report), token, connections as in pre.
# Each check prints [PASS] / [FAIL] NAME and its output indented; every child's stdout+stderr goes through MASK
# (IPv4 addresses -> <ip>, https URLs -> <url>). Last line: `demo-check MODE: N/M passed`.
# The Gateway token is never exported, never on a command line, never printed: it reaches mcp_smoke.py only,
# through its environment (--bearer-env GW_TOKEN). DORIS_* and GW_TOKEN from the caller are dropped. Only
# reconcile sees Doris credentials: DORIS_HOST / DORIS_PORT / DORIS_USER / DORIS_PASSWORD, set from the read-only
# account of CREDENTIALS_FILE in a subshell (DORIS_ROOT_* never reach any child).
# Env knobs: STATE_FILE=infra/state.env   PYTHON=.venv/bin/python (of the repo)   MAX_CONNS=80
#            CREDENTIALS_FILE=/home/ubuntu/AI-code/Doris-test/credentials.env
#            TOKEN_CMD="bash scripts/get-gw-token.sh" (split on whitespace, no quoting; the default reads the
#            repo's infra/state.env, whatever STATE_FILE says)
# Exit code: 0 when every check passes, 1 when one fails, 2 on bad arguments or an incomplete state file.
set -uo pipefail
set +x # `bash -x` would print the Gateway token and the Doris passwords

MASK='s/\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b/<ip>/g; s#https://[^ )"`]+#<url>#g'
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() { # [REASON]
  [[ -z "${1-}" ]] || echo "demo-check: $1" >&2
  echo "usage: $0 pre | post --since MS --until MS   (MS: epoch milliseconds)" >&2
  exit 2
}

MODE="${1-}"; (( $# )) && shift
case "$MODE" in
  pre) (( $# == 0 )) || usage "pre takes no arguments" ;;
  post)
    SINCE="" UNTIL=""
    while (( $# )); do
      case "$1" in
        --since) (( $# >= 2 )) || usage "--since needs a value"; SINCE="$2"; shift 2 ;;
        --until) (( $# >= 2 )) || usage "--until needs a value"; UNTIL="$2"; shift 2 ;;
        *) usage "unknown argument '$1'" ;;
      esac
    done
    [[ "$SINCE" =~ ^[1-9][0-9]{12}$ && "$UNTIL" =~ ^[1-9][0-9]{12}$ ]] \
      || usage "--since and --until are required, in epoch milliseconds (13 digits)"
    (( SINCE < UNTIL )) || usage "--since must be before --until" ;;
  *) usage ;;
esac

STATE_FILE="${STATE_FILE:-$ROOT/infra/state.env}"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-/home/ubuntu/AI-code/Doris-test/credentials.env}"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
TOKEN_CMD="${TOKEN_CMD:-bash scripts/get-gw-token.sh}"
MAX_CONNS="${MAX_CONNS:-80}"
[[ "$MAX_CONNS" =~ ^(0|[1-9][0-9]*)$ ]] || usage "MAX_CONNS must be a number"
for v in STATE_FILE CREDENTIALS_FILE; do [[ "${!v}" == /* ]] || printf -v "$v" '%s/%s' "$PWD" "${!v}"; done

# shellcheck source=/dev/null
source "$STATE_FILE" || { echo "demo-check: cannot read $STATE_FILE" >&2; exit 2; }
unset GW_TOKEN "${!DORIS_@}" # the caller's and the state file's (DORIS_SG, ...): no child may inherit them
export AWS_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER=""
NEEDED=(ACCOUNT_ID GW_ID GW_URL)
[[ "$MODE" == pre ]] && NEEDED+=(GW_TARGET_ID RUNTIME_URL) || NEEDED+=(RUNTIME_ID)
for key in "${NEEDED[@]}"; do
  [[ -n "${!key:-}" ]] || { echo "demo-check: $key missing in $STATE_FILE" >&2; exit 2; }
done
cd "$ROOT" || exit 2

GW_TOKEN="" TMPFILES=()
trap 'unset GW_TOKEN; rm -f "${TMPFILES[@]}"' EXIT

PASSED=0 TOTAL=0
report() { # NAME RC OUTPUT — the verdict line, then the (already masked) output indented
  TOTAL=$((TOTAL + 1))
  if [[ "$2" == 0 ]]; then PASSED=$((PASSED + 1)); echo "[PASS] $1"; else echo "[FAIL] $1"; fi
  [[ -z "$3" ]] || sed 's/^/    /' <<<"$3"
}
check() { # NAME CMD... — passes when CMD exits 0; sets OUT to its masked stdout+stderr
  local name="$1" rc; shift
  OUT="$("$@" 2>&1 | sed -E "$MASK"; exit "${PIPESTATUS[0]}")"; rc=$?
  report "$name" "$rc" "$OUT"
}

account_ok() {
  local account
  account="$(aws sts get-caller-identity --region "$AWS_REGION" --query Account --output text)" || return 1
  if [[ "$account" == "$ACCOUNT_ID" ]]; then echo "the caller's account is ACCOUNT_ID"; return 0; fi
  echo "the caller's account is not ACCOUNT_ID of $STATE_FILE"; return 1
}
ready() { # CMD... — prints the status it returns; passes on READY
  local status
  status="$("$@")" || return 1
  echo "status: $status"
  [[ "$status" == READY ]]
}
get_token() { # sets GW_TOKEN (not exported); its stderr is masked, its stdout never printed
  local err rc argv
  err="$(mktemp)"; TMPFILES+=("$err")
  read -ra argv <<<"$TOKEN_CMD"
  GW_TOKEN="$("${argv[@]}" 2>"$err")"; rc=$?
  if (( rc == 0 )) && [[ -z "$GW_TOKEN" ]]; then echo "the token command printed nothing" >>"$err"; rc=1; fi
  (( rc == 0 )) || GW_TOKEN=""
  report token "$rc" "$(sed -E "$MASK" "$err")"
}
smoke() { # SUBCOMMAND ARGS... — mcp_smoke.py through the Gateway; the token only in its environment
  [[ -n "$GW_TOKEN" ]] || { echo "skipped: no Gateway token"; return 1; }
  GW_TOKEN="$GW_TOKEN" "$PYTHON" scripts/mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN --timeout 60 "$@"
}
reconcile() { # the read-only Doris account only; no GW_TOKEN, no other DORIS_* variable
  ( source "$CREDENTIALS_FILE" || exit 1
    host="${DORIS_HOST-}" port="${DORIS_MYSQL_PORT:-9030}" user="${DORIS_RO_USER-}" password="${DORIS_RO_PASSWORD-}"
    unset GW_TOKEN "${!DORIS_@}" # whether or not the file exports them
    [[ -n "$user" && -n "$password" ]] || { echo "DORIS_RO_USER / DORIS_RO_PASSWORD missing in $CREDENTIALS_FILE"; exit 1; }
    export DORIS_HOST="$host" DORIS_PORT="$port" DORIS_USER="$user" DORIS_PASSWORD="$password" AWS_REGION
    exec "$PYTHON" doris/reconcile.py mcp --url "$RUNTIME_URL" )
}
conns_max() { # the `connections: N` count of the last conns check <= MAX_CONNS
  local n
  n="$(sed -nE 's/^connections: ([0-9]+).*/\1/p' <<<"$CONNS_OUT" | head -1)"
  [[ -n "$n" ]] || { echo "no 'connections: N' line in the conns output"; return 1; }
  echo "connections: $n, MAX_CONNS: $MAX_CONNS"
  (( n <= MAX_CONNS ))
}
conns() {
  check conns smoke conns --prefix doris___ --expect-host-prefix 172.31. --max-idle 610
  CONNS_OUT="$OUT"
  check "conns <= MAX_CONNS" conns_max
}
audit() {
  aws logs filter-log-events --region "$AWS_REGION" --log-group-name "/aws/bedrock-agentcore/runtimes/${RUNTIME_ID}-DEFAULT" \
      --start-time "$SINCE" --end-time "$UNTIL" --filter-pattern '"doris_new_mcp.audit"' --output json \
    | "$PYTHON" scripts/audit_check.py --failures
}
minute_floor() { date -u -d "@$(( $1 / 1000 / 60 * 60 ))" +%Y-%m-%dT%H:%M:%SZ; } # MS -> ISO-8601, its whole minute
minute_ceil() { date -u -d "@$(( ($1 / 1000 + 59) / 60 * 60 ))" +%Y-%m-%dT%H:%M:%SZ; } # MS -> ISO-8601, next whole minute
latency() {
  local from to q
  from="$(minute_floor "$SINCE")" && to="$(minute_ceil "$UNTIL")" || return 1 # a call in the first minute counts
  echo "window $from .. $to"
  q="$("$PYTHON" scripts/gw_latency.py queries --gateway-arn "arn:aws:bedrock-agentcore:${AWS_REGION}:${ACCOUNT_ID}:gateway/${GW_ID}")" \
    || return 1
  aws cloudwatch get-metric-data --region "$AWS_REGION" --start-time "$from" --end-time "$to" --metric-data-queries "$q" \
      --output json \
    | "$PYTHON" scripts/gw_latency.py report
}

if [[ "$MODE" == pre ]]; then
  check account account_ok
  check "gateway READY" ready aws bedrock-agentcore-control get-gateway --gateway-identifier "$GW_ID" \
    --region "$AWS_REGION" --query status --output text
  check "target READY" ready aws bedrock-agentcore-control get-gateway-target --gateway-identifier "$GW_ID" \
    --target-id "$GW_TARGET_ID" --region "$AWS_REGION" --query status --output text
  get_token
  check "list 12 tools" smoke list --expect 12
  check flow smoke flow --prefix doris___
  check reconcile reconcile
  check "permission matrix" "$PYTHON" doris/permission_matrix.py --url "$RUNTIME_URL" --expect-host '172.31.%'
  conns
else
  check audit audit
  check latency latency
  get_token
  conns
fi

echo "demo-check $MODE: $PASSED/$TOTAL passed"
(( PASSED == TOTAL ))
