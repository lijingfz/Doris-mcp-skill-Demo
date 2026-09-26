#!/usr/bin/env bash
# Offline tests for infra/lib.sh state loading. No AWS calls.
#   bash infra/test/test-lib.sh
set -uo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
STATE="$TMP/state.env"
printf '%s\n' '# test state' 'AWS_REGION=us-east-1' 'QUICK_CALLBACK=https://old.example/cb' 'GW_ID=gw-from-state' > "$STATE"

FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
# load ENV... — source lib.sh in a clean subshell with ENV set; print QUICK_CALLBACK|GW_ID|AWS_REGION.
load() {
  env -u QUICK_CALLBACK -u GW_ID -u AWS_REGION -u STATE_CALLER_WINS "$@" STATE_FILE="$STATE" \
    bash -c 'source "$1/lib.sh" 2>/dev/null; printf "%s|%s|%s" "$QUICK_CALLBACK" "$GW_ID" "$AWS_REGION"' _ "$INFRA_DIR"
}

check "state values load when caller sets nothing" \
  "https://old.example/cb|gw-from-state|us-east-1" "$(load)"
check "caller value wins for keys listed in STATE_CALLER_WINS" \
  "https://new.example/cb|gw-from-state|us-east-1" \
  "$(load STATE_CALLER_WINS=QUICK_CALLBACK QUICK_CALLBACK=https://new.example/cb)"
check "state wins for keys not listed (caller AWS_REGION / GW_ID ignored)" \
  "https://old.example/cb|gw-from-state|us-east-1" \
  "$(load STATE_CALLER_WINS=QUICK_CALLBACK AWS_REGION=us-west-2 GW_ID=gw-from-caller)"
check "listed key falls back to state when caller leaves it unset" \
  "https://old.example/cb|gw-from-state|us-east-1" "$(load STATE_CALLER_WINS=QUICK_CALLBACK)"

# 20-cognito.sh must list QUICK_CALLBACK before it sources lib.sh, or the documented
# `QUICK_CALLBACK=… bash infra/20-cognito.sh` override is silently replaced by state.env.
wins_line="$(grep -n '^STATE_CALLER_WINS=.*QUICK_CALLBACK' "$INFRA_DIR/20-cognito.sh" | head -1 | cut -d: -f1)"
source_line="$(grep -n '^source .*lib.sh' "$INFRA_DIR/20-cognito.sh" | head -1 | cut -d: -f1)"
check "20-cognito.sh declares QUICK_CALLBACK caller-wins before sourcing lib.sh" \
  "yes" "$([[ -n "$wins_line" && -n "$source_line" && "$wins_line" -lt "$source_line" ]] && echo yes || echo no)"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
