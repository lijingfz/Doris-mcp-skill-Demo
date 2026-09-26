#!/usr/bin/env bash
# Shared helpers for infra/*.sh — source it, do not execute it.
#
# Safety model:
#   * Read-only AWS calls (describe/list/get) run directly.
#   * Every mutating call goes through `run`: printed (DRY-RUN) by default,
#     executed only when APPLY=1.
#   * Resource IDs are recorded in infra/state.env via `state_set` (APPLY=1 only).
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="${STATE_FILE:-$INFRA_DIR/state.env}"
APPLY="${APPLY:-0}"
PROJECT_TAG="doris-mcp-demo"
export AWS_PAGER=""

# Recorded state wins over the environment, except for the override knobs a script lists in
# STATE_CALLER_WINS (set before sourcing this file), e.g. `QUICK_CALLBACK=… bash infra/20-cognito.sh`.
declare -A _CALLER_WINS=()
for _k in ${STATE_CALLER_WINS:-}; do [[ -n "${!_k+x}" ]] && _CALLER_WINS[$_k]="${!_k}"; done
# shellcheck source=/dev/null
source "$STATE_FILE"
for _k in "${!_CALLER_WINS[@]}"; do printf -v "$_k" '%s' "${_CALLER_WINS[$_k]}"; done
unset _k _CALLER_WINS
export AWS_REGION="${AWS_REGION:-us-east-1}" AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }

# run CMD...  — execute when APPLY=1, otherwise print the quoted command to stderr.
run() {
  if [[ "$APPLY" == "1" ]]; then
    "$@"
  else
    { printf 'DRY-RUN:'; printf ' %q' "$@"; printf '\n'; } >&2
  fi
}

# placeholder NAME — stand-in ID for a resource that a dry-run would create.
placeholder() { printf '<new:%s>' "$1"; }
is_placeholder() { [[ "$1" == "<new:"* ]]; }

# none_to_empty VALUE — AWS CLI text output prints "None" for missing values.
none_to_empty() { [[ "$1" == "None" ]] && echo "" || echo "$1"; }

# state_set KEY VALUE — upsert KEY=VALUE into state.env and export it (APPLY=1 only).
state_set() {
  local key="$1" value="$2"
  if [[ "$APPLY" != "1" ]]; then log "DRY-RUN: state_set $key=$value"; return 0; fi
  if grep -q "^$key=" "$STATE_FILE"; then
    sed -i "s|^$key=.*|$key=$value|" "$STATE_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$STATE_FILE"
  fi
  export "$key=$value"
  log "state: $key=$value"
}

# render FILE — print FILE with ${VAR} references expanded from the environment.
render() { python3 -c 'import os,sys; sys.stdout.write(os.path.expandvars(open(sys.argv[1]).read()))' "$1"; }

# private_tmp — create a 0600 temp file for secret-bearing CLI input (AWS CLI cannot read
# /dev/fd or stdin for file:// parameters). Callers must remove it; the EXIT trap is a backstop.
_PRIVATE_TMPS=()
private_tmp() { local f; f="$(umask 077; mktemp)"; _PRIVATE_TMPS+=("$f"); PRIVATE_TMP="$f"; }
trap 'rm -f "${_PRIVATE_TMPS[@]}"' EXIT

# tags NAME — EC2 TagSpecification tag list for a named project resource.
runtime_url() { # RUNTIME_ARN → SigV4 invoke URL of the DEFAULT endpoint
  printf 'https://bedrock-agentcore.%s.amazonaws.com/runtimes/%s/invocations?qualifier=DEFAULT' "$AWS_REGION" \
    "$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1")"; }
tags() { printf 'Tags=[{Key=Name,Value=%s},{Key=Project,Value=%s}]' "$1" "$PROJECT_TAG"; }

log "APPLY=$APPLY region=$AWS_REGION state=$STATE_FILE"
