#!/usr/bin/env bash
# P0 / T0.6 — AgentCore Gateway: Quick (Cognito JWT) → Gateway → Runtime (IAM SigV4).
#   * IAM role doris-mcp-gateway-role: assumable by bedrock-agentcore (this account's gateways);
#     may only InvokeAgentRuntime on RUNTIME_ARN
#   * Gateway doris-mcp-gw: MCP, CUSTOM_JWT (Cognito discovery URL, clients A+B, scope doris-mcp/invoke)
#   * Target doris: mcpServer endpoint = Runtime invoke URL, outbound GATEWAY_IAM_ROLE SigV4
# Env knobs:  GW_ALLOWED_SCOPES="doris-mcp/invoke" (set to "" to drop the scope check)
#             SYNC=1  → synchronize-gateway-targets (after the Runtime's tools changed)
# Dry-run by default. APPLY=1 to execute. Safe to re-run (re-applies role policy + authorizer).
source "$(dirname "$0")/lib.sh"

ROLE_NAME=doris-mcp-gateway-role
GW_NAME=doris-mcp-gw
TARGET_NAME=doris
GW_ALLOWED_SCOPES="${GW_ALLOWED_SCOPES-doris-mcp/invoke}"

if [[ "$APPLY" == "1" ]]; then
  : "${RUNTIME_ARN:?RUNTIME_ARN missing in state.env - finish T0.4 first}"
  : "${DISCOVERY_URL:?DISCOVERY_URL missing - finish T0.5 first}" "${CLIENT_A_ID:?}" "${CLIENT_B_ID:?}"
fi
RUNTIME_ARN="${RUNTIME_ARN:-$(placeholder runtime-arn)}"
DISCOVERY_URL="${DISCOVERY_URL:-$(placeholder discovery-url)}"
CLIENT_A_ID="${CLIENT_A_ID:-$(placeholder client-a)}"
CLIENT_B_ID="${CLIENT_B_ID:-$(placeholder client-b)}"
RUNTIME_URL="$(runtime_url "$RUNTIME_ARN")"
export ACCOUNT_ID AWS_REGION RUNTIME_ARN

render_tmp() { # FILE → path of a rendered copy in $RENDERED
  RENDERED="$(mktemp)"; _PRIVATE_TMPS+=("$RENDERED"); render "$1" > "$RENDERED"
  [[ "$APPLY" == "1" ]] || { log "rendered $(basename "$1"):"; cat "$RENDERED" >&2; }
}

# --- IAM role ---------------------------------------------------------------
GW_ROLE_ARN="$(none_to_empty "$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text 2>/dev/null || true)")"
role_is_new=0
if [[ -z "$GW_ROLE_ARN" ]]; then
  render_tmp "$INFRA_DIR/policies/gateway-trust.json"
  GW_ROLE_ARN="$(run aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document "file://$RENDERED" --tags "Key=Project,Value=$PROJECT_TAG" \
    --description "AgentCore Gateway doris-mcp-gw outbound SigV4 to Runtime dorismcp" \
    --query Role.Arn --output text)"
  GW_ROLE_ARN="${GW_ROLE_ARN:-$(placeholder gateway-role-arn)}"
  role_is_new=1
else
  log "role exists: $GW_ROLE_ARN"
fi
render_tmp "$INFRA_DIR/policies/gateway-invoke-runtime.json"
run aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name invoke-dorismcp-runtime \
  --policy-document "file://$RENDERED"
[[ "$APPLY" == "1" && "$role_is_new" == "1" ]] && { log "waiting 15s for IAM propagation"; sleep 15; }
is_placeholder "$GW_ROLE_ARN" || state_set GW_ROLE_ARN "$GW_ROLE_ARN"

# --- gateway ----------------------------------------------------------------
AUTHZ="$(python3 - "$DISCOVERY_URL" "$CLIENT_A_ID" "$CLIENT_B_ID" "$GW_ALLOWED_SCOPES" <<'PY'
import json, sys
url, a, b, scopes = sys.argv[1:5]
cfg = {"discoveryUrl": url, "allowedClients": [a, b]}
if scopes:
    cfg["allowedScopes"] = scopes.split(",")
print(json.dumps({"customJWTAuthorizer": cfg}))
PY
)"
GW_COMMON=(--name "$GW_NAME" --role-arn "$GW_ROLE_ARN" --protocol-type MCP
  --authorizer-type CUSTOM_JWT --authorizer-configuration "$AUTHZ" --exception-level DEBUG)

GW_ID="$(none_to_empty "$(aws bedrock-agentcore-control list-gateways \
  --query "items[?name=='$GW_NAME'].gatewayId | [0]" --output text)")"
if [[ -z "$GW_ID" ]]; then
  GW_ID="$(run aws bedrock-agentcore-control create-gateway "${GW_COMMON[@]}" \
    --description "Quick desktop -> Doris MCP (Runtime dorismcp)" --tags "Project=$PROJECT_TAG" \
    --query gatewayId --output text)"
  GW_ID="${GW_ID:-$(placeholder gateway-id)}"
else
  log "gateway exists: $GW_ID (re-applying authorizer, scopes='$GW_ALLOWED_SCOPES')"
  run aws bedrock-agentcore-control update-gateway --gateway-identifier "$GW_ID" "${GW_COMMON[@]}" \
    --query status --output text >/dev/null
fi

wait_status() { # get-command-args... → waits for READY
  [[ "$APPLY" == "1" ]] || return 0
  local status=""
  for _ in $(seq 1 60); do
    status="$(aws bedrock-agentcore-control "$@" --query status --output text)"
    case "$status" in
      READY) log "$1 → READY"; return 0 ;;
      FAILED|UPDATE_UNSUCCESSFUL)
        aws bedrock-agentcore-control "$@" --query statusReasons --output json >&2; exit 1 ;;
    esac
    sleep 5
  done
  log "FATAL: timeout waiting for READY (last status: $status)"; exit 1
}
wait_status get-gateway --gateway-identifier "$GW_ID"
if ! is_placeholder "$GW_ID"; then
  state_set GW_ID "$GW_ID"
  state_set GW_URL "$(aws bedrock-agentcore-control get-gateway --gateway-identifier "$GW_ID" --query gatewayUrl --output text)"
fi

# --- target -----------------------------------------------------------------
TARGET_CFG="$(python3 -c 'import json, sys; print(json.dumps({"mcp": {"mcpServer": {"endpoint": sys.argv[1]}}}))' "$RUNTIME_URL")"
CREDS="[{\"credentialProviderType\":\"GATEWAY_IAM_ROLE\",\"credentialProvider\":{\"iamCredentialProvider\":{\"service\":\"bedrock-agentcore\",\"region\":\"$AWS_REGION\"}}}]"
TARGET_ID=""
is_placeholder "$GW_ID" || TARGET_ID="$(none_to_empty "$(aws bedrock-agentcore-control list-gateway-targets \
  --gateway-identifier "$GW_ID" --query "items[?name=='$TARGET_NAME'].targetId | [0]" --output text)")"
if [[ -z "$TARGET_ID" ]]; then
  TARGET_ID="$(run aws bedrock-agentcore-control create-gateway-target --gateway-identifier "$GW_ID" \
    --name "$TARGET_NAME" --description "AgentCore Runtime dorismcp (SigV4)" \
    --target-configuration "$TARGET_CFG" --credential-provider-configurations "$CREDS" \
    --query targetId --output text)"
  TARGET_ID="${TARGET_ID:-$(placeholder target-id)}"
elif [[ "${SYNC:-0}" == "1" ]]; then
  run aws bedrock-agentcore-control synchronize-gateway-targets --gateway-identifier "$GW_ID" \
    --target-id-list "$TARGET_ID" >/dev/null
else
  log "target exists: $TARGET_ID (SYNC=1 to re-list tools)"
fi
wait_status get-gateway-target --gateway-identifier "$GW_ID" --target-id "$TARGET_ID"
is_placeholder "$TARGET_ID" || state_set GW_TARGET_ID "$TARGET_ID"
log "done (APPLY=$APPLY)"
