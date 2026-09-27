#!/usr/bin/env bash
# P2 / T2.2 — run a doris/*.sql account script as the Doris admin (root).
#   bash doris/apply-admin-sql.sh doris/01_mcp_user.sql            # dry-run: masked statements, no connection
#   APPLY=1 bash doris/apply-admin-sql.sh doris/01_mcp_user.sql    # GATE: only after the user confirms
# The service-account password flows Secrets Manager → pipe → admin_sql.py (never argv, disk or output).
# credentials.env is sourced in a subshell; only host/port, the admin user and (APPLY=1 only) the admin
# password are exported, under new names, to the python process.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SQL="${1:?usage: [APPLY=1] bash doris/apply-admin-sql.sh doris/01_mcp_user.sql}"
CRED="${DORIS_CRED_FILE:-/home/ubuntu/AI-code/Doris-test/credentials.env}"
PY="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
SECRET_ID="${DORIS_SECRET_ID:-doris-mcp/mcp_svc}"
export AWS_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER="" APPLY="${APPLY:-0}"

aws secretsmanager get-secret-value --secret-id "$SECRET_ID" --query SecretString --output text |
  ( source "$CRED"
    export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_ADMIN_USER="$DORIS_ROOT_USER"
    [[ "$APPLY" == "1" ]] && export DORIS_ADMIN_PASSWORD="$DORIS_ROOT_PASSWORD"
    exec "$PY" "$ROOT/doris/admin_sql.py" "$SQL" )
