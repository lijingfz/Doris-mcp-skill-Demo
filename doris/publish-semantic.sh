#!/usr/bin/env bash
# P2 / T2.5 — publish doris/semantic/ecom to the Doris semantic store (system_mcp, workspace ecom) as root.
#   bash doris/publish-semantic.sh [--models DIR] [--workspace ecom]           # dry-run: offline checks + plan
#   APPLY=1 bash doris/publish-semantic.sh [--models DIR] [--workspace ecom]   # GATE: only after the user confirms
# credentials.env is sourced in a subshell; only host/port, the admin user and (APPLY=1 only) the admin
# password are exported, under new names, to the python process.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CRED="${DORIS_CRED_FILE:-/home/ubuntu/AI-code/Doris-test/credentials.env}"
PY="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
export APPLY="${APPLY:-0}"

( source "$CRED"
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_ADMIN_USER="$DORIS_ROOT_USER"
  [[ "$APPLY" == "1" ]] && export DORIS_ADMIN_PASSWORD="$DORIS_ROOT_PASSWORD"
  exec "$PY" "$ROOT/doris/publish_semantic.py" "$@" )
