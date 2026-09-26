#!/usr/bin/env bash
# Get a Cognito access token for client B (client_credentials, scope doris-mcp/invoke).
#   export GW_TOKEN="$(bash scripts/get-gw-token.sh)"   # capture only — never echo it
#   bash scripts/get-gw-token.sh --claims                # print decoded claims, not the token
# The client secret is read with the AWS CLI and handed to curl through a header file
# (process substitution) — never on a command line, never printed.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=/dev/null
source "$ROOT/infra/state.env"
: "${COGNITO_POOL_ID:?missing in state.env (T0.5)}" "${CLIENT_B_ID:?}" "${COGNITO_DOMAIN:?}"
export AWS_PAGER=""

secret="$(aws cognito-idp describe-user-pool-client --region "$AWS_REGION" \
  --user-pool-id "$COGNITO_POOL_ID" --client-id "$CLIENT_B_ID" \
  --query UserPoolClient.ClientSecret --output text)"
if ! resp="$(curl -sS --fail-with-body -X POST "https://$COGNITO_DOMAIN/oauth2/token" \
    -H @<(printf 'Authorization: Basic %s\n' "$(printf '%s:%s' "$CLIENT_B_ID" "$secret" | base64 -w0)") \
    --data-urlencode grant_type=client_credentials --data-urlencode scope=doris-mcp/invoke)"; then
  echo "token request failed: $resp" >&2
  exit 1
fi
unset secret
token="$(printf '%s' "$resp" | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')"

if [[ "${1:-}" == "--claims" ]]; then
  printf '%s' "$token" | python3 -c '
import base64, json, sys
part = sys.stdin.read().split(".")[1]
claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
print(json.dumps({k: claims.get(k) for k in ("client_id", "scope", "token_use", "iss", "exp")}, indent=2))'
else
  printf '%s\n' "$token"
fi
