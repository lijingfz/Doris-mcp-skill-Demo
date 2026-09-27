#!/usr/bin/env bash
# P3 / T3.1 — IAM execution role for AgentCore Runtime dorismcp, replacing the agentcore CLI's CDK role
# (which may invoke any Bedrock model and write X-Ray; design §7).
#   * trust: bedrock-agentcore, this account's resources in this region only
#   * inline policy doris-mcp-runtime: the runtime's own log groups + GetSecretValue on DORIS_SECRET_ARN
#     (the secret uses the AWS managed key, so no kms:Decrypt)
# agentcore.json references the role via executionRoleArn (scripts/render-agentcore.py --phase server);
# the CDK then imports it and adds no policies, so this policy is all the runtime can do.
# Dry-run by default. APPLY=1 to execute. Safe to re-run (re-applies the inline policy).
source "$(dirname "$0")/lib.sh"

ROLE_NAME=doris-mcp-runtime-role
POLICY_NAME=doris-mcp-runtime
RUNTIME_NAME=dorismcp_dorismcp # <agentcore project>_<runtime>; log groups are runtimes/<runtime-id>-<endpoint>

if [[ "$APPLY" == "1" ]]; then
  : "${DORIS_SECRET_ARN:?DORIS_SECRET_ARN missing in state.env - finish T2.1 first}"
  if [[ "$DORIS_SECRET_ARN" != "arn:aws:secretsmanager:$AWS_REGION:$ACCOUNT_ID:secret:doris-mcp/mcp_svc-"* ]]; then
    log "FATAL: DORIS_SECRET_ARN is not the doris-mcp/mcp_svc secret of this account/region"; exit 1
  fi
fi
DORIS_SECRET_ARN="${DORIS_SECRET_ARN:-$(placeholder doris-secret-arn)}"
export ACCOUNT_ID AWS_REGION RUNTIME_NAME DORIS_SECRET_ARN

render_tmp() { # FILE → path of a rendered copy in $RENDERED
  RENDERED="$(mktemp)"; _PRIVATE_TMPS+=("$RENDERED"); render "$1" > "$RENDERED"
  [[ "$APPLY" == "1" ]] || { log "rendered $(basename "$1"):"; cat "$RENDERED" >&2; }
}

# get-role: distinguish "not found" from every other failure, so a missing permission or an
# expired session never falls through to create-role.
RT_ROLE_ARN=""
if out="$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text 2>&1)"; then
  RT_ROLE_ARN="$(none_to_empty "$out")"
elif [[ "$out" != *NoSuchEntity* ]]; then
  log "FATAL: get-role $ROLE_NAME failed: $out"; exit 1
fi

role_is_new=0
if [[ -z "$RT_ROLE_ARN" ]]; then
  render_tmp "$INFRA_DIR/policies/runtime-trust.json"
  RT_ROLE_ARN="$(run aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document "file://$RENDERED" --tags "Key=Project,Value=$PROJECT_TAG" \
    --description "AgentCore Runtime dorismcp: own logs + the doris-mcp/mcp_svc secret" \
    --query Role.Arn --output text)"
  RT_ROLE_ARN="${RT_ROLE_ARN:-$(placeholder runtime-role-arn)}"
  role_is_new=1
else
  log "role exists: $RT_ROLE_ARN"
fi
render_tmp "$INFRA_DIR/policies/runtime-exec.json"
run aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" \
  --policy-document "file://$RENDERED"
[[ "$APPLY" == "1" && "$role_is_new" == "1" ]] && { log "waiting 15s for IAM propagation"; sleep 15; }
is_placeholder "$RT_ROLE_ARN" || state_set RT_ROLE_ARN "$RT_ROLE_ARN"
log "done (APPLY=$APPLY)"
