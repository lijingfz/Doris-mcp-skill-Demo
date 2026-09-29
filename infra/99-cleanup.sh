#!/usr/bin/env bash
# P5 / T5.6 — Tear down the demo's AWS resources after the demo. Deletes only what state.env records, in
# dependency order (each step removes what blocks the next one):
#   1. Gateway target, then (once the target is gone) the Gateway doris-mcp-gw
#   2. CloudFormation stack AgentCore-dorismcp-default (the Runtime), waiting for stack-delete-complete
#   3. VPC endpoints S3 / logs / secretsmanager, waiting until they are gone (their ENIs use doris-mcp-vpce)
#   4. Cognito hosted UI domain (a pool with a domain cannot be deleted), then the user pool
#   5. secrets doris-mcp/cognito-demo-user and doris-mcp/mcp_svc (recovery window, see the knobs)
#   6. doris-demo-sg: only its ingress rules that reference doris-mcp-rt; its other rules are never touched
#   7. waits until no network interface uses doris-mcp-rt / doris-mcp-vpce (the Runtime's ENIs are released
#      asynchronously, minutes after the stack), revokes their cross-references, deletes both SGs
#   8. IAM roles doris-mcp-gateway-role and doris-mcp-runtime-role (inline policies first)
# Every check runs before the first delete: the caller's account must be ACCOUNT_ID, every resource must carry
# Project=doris-mcp-demo (the stack: agentcore:project-name=dorismcp), the Gateway must be named doris-mcp-gw;
# any mismatch or unexpected error -> FATAL, nothing deleted. A resource already gone is logged and skipped,
# so a partial run can simply be re-run.
# Not touched: state.env (kept as the record), log groups, the X-Ray/transaction search setting, other projects.
# Doris side (DROP USER mcp_svc, DROP DATABASE system_mcp) is a separate step.
# Env knobs:  STACK_NAME=AgentCore-dorismcp-default
#             SECRET_RECOVERY_DAYS=7 (7-30)   FORCE_DELETE_SECRETS=1 → delete the secrets without recovery
# Dry-run by default. APPLY=1 to execute.
source "$(dirname "$0")/lib.sh"

STACK_NAME="${STACK_NAME:-AgentCore-dorismcp-default}"
SECRET_RECOVERY_DAYS="${SECRET_RECOVERY_DAYS:-7}"
FORCE_DELETE_SECRETS="${FORCE_DELETE_SECRETS:-0}"
GW_NAME=doris-mcp-gw
SECRETS=(doris-mcp/cognito-demo-user doris-mcp/mcp_svc)
ROLES=(doris-mcp-gateway-role doris-mcp-runtime-role)

DONE=() # what step 2 deleted (or would delete), for the summary
fatal() { log "FATAL: $* (${#DONE[@]} deleted so far)"; exit 1; }

[[ "$SECRET_RECOVERY_DAYS" =~ ^([7-9]|[12][0-9]|30)$ ]] || fatal "SECRET_RECOVERY_DAYS must be 7-30"
case "$FORCE_DELETE_SECRETS" in
  1) SECRET_ARGS=(--force-delete-without-recovery) ;;
  0) SECRET_ARGS=(--recovery-window-in-days "$SECRET_RECOVERY_DAYS") ;;
  *) fatal "FORCE_DELETE_SECRETS must be 0 or 1" ;;
esac
for key in ACCOUNT_ID GW_ID GW_TARGET_ID VPCE_S3 VPCE_LOGS VPCE_SECRETSMANAGER COGNITO_POOL_ID COGNITO_DOMAIN \
           DORIS_SG RT_SG VPCE_SG; do
  [[ -n "${!key:-}" ]] && ! is_placeholder "${!key}" || fatal "$key missing in $STATE_FILE"
done
DOMAIN_PREFIX="${COGNITO_DOMAIN%%.*}" # state has the full host <prefix>.auth.<region>.amazoncognito.com

# probe NOT_FOUND CMD... — a read; sets OUT ("None" -> ""). Returns 1 when the error output contains
# NOT_FOUND (the resource is gone); any other failure (access denied, expired session, ...) is FATAL, so it
# can never pass for "already deleted". fetch CMD... — a read that must succeed.
private_tmp; ERR_FILE="$PRIVATE_TMP"
probe() {
  local not_found="$1"; shift
  if OUT="$("$@" 2>"$ERR_FILE")"; then OUT="$(none_to_empty "$OUT")"; return 0; fi
  if [[ -n "$not_found" ]] && grep -q -- "$not_found" "$ERR_FILE"; then OUT=""; return 1; fi
  fatal "$1 $2 $3 failed: $(cat "$ERR_FILE")"
}
fetch() { probe "" "$@"; }
gone() { log "$1 already deleted"; }
require_tag() { # WHAT VALUE — VALUE is the resource's Project tag
  [[ "$2" == "$PROJECT_TAG" ]] || fatal "$1 is not tagged Project=$PROJECT_TAG (found '$(none_to_empty "$2")')"
}
# wait_gone TRIES SECONDS MESSAGE CHECK... — APPLY=1 only: polls CHECK until it succeeds, TRIES times at most,
# SECONDS apart; FATAL with MESSAGE when it never does.
wait_gone() {
  local tries="$1" secs="$2" message="$3" i; shift 3
  [[ "$APPLY" == "1" ]] || return 0
  for ((i = 1; i <= tries; i++)); do
    "$@" && return 0
    (( i == tries )) || sleep "$secs"
  done
  fatal "$message"
}

# --- 1. checks (read-only) --------------------------------------------------
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$ACCOUNT_ID" ]] \
  || fatal "the caller's account is not ACCOUNT_ID of $STATE_FILE"

DEL_GW=0 DEL_TARGET=0
if probe ResourceNotFoundException aws bedrock-agentcore-control get-gateway --gateway-identifier "$GW_ID" \
     --query '[name, gatewayArn]' --output text; then
  read -r name arn <<<"$OUT"
  [[ "$name" == "$GW_NAME" ]] || fatal "Gateway $GW_ID is named '$name', not $GW_NAME"
  fetch aws bedrock-agentcore-control list-tags-for-resource --resource-arn "$arn" --query tags.Project --output text
  require_tag "Gateway $GW_ID" "$OUT"; DEL_GW=1
  if probe ResourceNotFoundException aws bedrock-agentcore-control get-gateway-target --gateway-identifier "$GW_ID" \
       --target-id "$GW_TARGET_ID" --query status --output text; then DEL_TARGET=1; else gone "Gateway target $GW_TARGET_ID"; fi
else
  gone "Gateway $GW_ID"
fi

DEL_STACK=0
if probe 'does not exist' aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
     --query "Stacks[0].Tags[?Key=='agentcore:project-name'].Value | [0]" --output text; then
  [[ "$OUT" == dorismcp ]] || fatal "stack $STACK_NAME is not tagged agentcore:project-name=dorismcp"
  DEL_STACK=1
else
  gone "stack $STACK_NAME"
fi

VPCES=()
for id in "$VPCE_S3" "$VPCE_LOGS" "$VPCE_SECRETSMANAGER"; do
  fetch aws ec2 describe-vpc-endpoints --filters "Name=vpc-endpoint-id,Values=$id" \
    --query "VpcEndpoints[?State!='deleted'] | [0].[VpcEndpointId, Tags[?Key=='Project'].Value | [0]]" --output text
  if [[ -z "$OUT" ]]; then gone "VPC endpoint $id"; continue; fi
  read -r _ tag <<<"$OUT"; require_tag "VPC endpoint $id" "$tag"; VPCES+=("$id")
done

DEL_POOL=0 DEL_DOMAIN=0
if probe ResourceNotFoundException aws cognito-idp describe-user-pool --user-pool-id "$COGNITO_POOL_ID" \
     --query UserPool.UserPoolTags.Project --output text; then
  require_tag "user pool $COGNITO_POOL_ID" "$OUT"; DEL_POOL=1
else
  gone "user pool $COGNITO_POOL_ID"
fi
fetch aws cognito-idp describe-user-pool-domain --domain "$DOMAIN_PREFIX" --query DomainDescription.UserPoolId --output text
case "$OUT" in
  "") gone "Cognito domain $DOMAIN_PREFIX" ;;
  "$COGNITO_POOL_ID") DEL_DOMAIN=1 ;;
  *) fatal "Cognito domain $DOMAIN_PREFIX belongs to another user pool" ;;
esac

DEL_SECRETS=()
for s in "${SECRETS[@]}"; do
  if ! probe ResourceNotFoundException aws secretsmanager describe-secret --secret-id "$s" \
       --query "[DeletedDate, Tags[?Key=='Project'].Value | [0]]" --output text; then gone "secret $s"; continue; fi
  read -r deleted tag <<<"$OUT"
  if [[ "$deleted" != None ]]; then log "secret $s already scheduled for deletion"; continue; fi
  require_tag "secret $s" "$tag"; DEL_SECRETS+=("$s")
done

# doris-demo-sg is not ours: only the ingress rules 10-network.sh added (referencing doris-mcp-rt, tagged).
fetch aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$DORIS_SG" \
  --query "SecurityGroupRules[?!IsEgress && ReferencedGroupInfo.GroupId=='$RT_SG'].[SecurityGroupRuleId, Tags[?Key=='Project'].Value | [0]]" \
  --output text
DORIS_RULES=()
while read -r rule tag; do
  [[ -n "$rule" ]] || continue
  require_tag "$DORIS_SG rule $rule" "$tag"; DORIS_RULES+=("$rule")
done <<<"$OUT"
(( ${#DORIS_RULES[@]} )) || gone "$DORIS_SG ingress from $RT_SG"

SGS=()
for sg in "$RT_SG" "$VPCE_SG"; do
  fetch aws ec2 describe-security-groups --filters "Name=group-id,Values=$sg" \
    --query "SecurityGroups[0].[GroupId, Tags[?Key=='Project'].Value | [0]]" --output text
  if [[ -z "$OUT" ]]; then gone "security group $sg"; continue; fi
  read -r _ tag <<<"$OUT"; require_tag "security group $sg" "$tag"; SGS+=("$sg")
done

DEL_ROLES=()
for role in "${ROLES[@]}"; do
  if ! probe NoSuchEntity aws iam list-role-tags --role-name "$role" --query "Tags[?Key=='Project'].Value | [0]" \
       --output text; then gone "IAM role $role"; continue; fi
  require_tag "IAM role $role" "$OUT"; DEL_ROLES+=("$role")
done
log "checks passed"

# --- 2. deletes, in dependency order ----------------------------------------
target_gone() {
  ! probe ResourceNotFoundException aws bedrock-agentcore-control get-gateway-target --gateway-identifier "$GW_ID" \
    --target-id "$GW_TARGET_ID" --query status --output text
}
vpces_gone() {
  fetch aws ec2 describe-vpc-endpoints --filters "Name=vpc-endpoint-id,Values=$(IFS=,; echo "${VPCES[*]}")" \
    --query "VpcEndpoints[?State!='deleted'].VpcEndpointId" --output text
  [[ -z "$OUT" ]]
}
enis_gone() {
  fetch aws ec2 describe-network-interfaces --filters "Name=group-id,Values=$RT_SG,$VPCE_SG" \
    --query 'length(NetworkInterfaces)' --output text
  [[ "$OUT" == 0 ]]
}
revoke_refs() { # ingress|egress GROUP PEER — revoke GROUP's rules in that direction that reference PEER
  local egress=false ids; [[ "$1" == egress ]] && egress=true
  fetch aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$2" \
    --query "SecurityGroupRules[?IsEgress==\`$egress\` && ReferencedGroupInfo.GroupId=='$3'].SecurityGroupRuleId" --output text
  read -ra ids <<<"$OUT"
  (( ${#ids[@]} )) || return 0
  run aws ec2 "revoke-security-group-$1" --group-id "$2" --security-group-rule-ids "${ids[@]}" >/dev/null
}

if (( DEL_TARGET )); then
  run aws bedrock-agentcore-control delete-gateway-target --gateway-identifier "$GW_ID" --target-id "$GW_TARGET_ID" >/dev/null
  wait_gone 30 5 "Gateway target $GW_TARGET_ID still exists after 150 s" target_gone
  DONE+=("Gateway target")
fi
if (( DEL_GW )); then
  run aws bedrock-agentcore-control delete-gateway --gateway-identifier "$GW_ID" >/dev/null; DONE+=("Gateway")
fi
if (( DEL_STACK )); then
  run aws cloudformation delete-stack --stack-name "$STACK_NAME"
  run aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" \
    || fatal "stack $STACK_NAME did not reach DELETE_COMPLETE (see its events in the CloudFormation console)"
  DONE+=("stack $STACK_NAME")
fi
if (( ${#VPCES[@]} )); then
  run aws ec2 delete-vpc-endpoints --vpc-endpoint-ids "${VPCES[@]}" >/dev/null
  wait_gone 30 10 "VPC endpoints ${VPCES[*]} still exist after 300 s" vpces_gone
  DONE+=("${#VPCES[@]} VPC endpoints")
fi
if (( DEL_DOMAIN )); then
  run aws cognito-idp delete-user-pool-domain --domain "$DOMAIN_PREFIX" --user-pool-id "$COGNITO_POOL_ID"
  DONE+=("Cognito domain")
fi
if (( DEL_POOL )); then
  run aws cognito-idp delete-user-pool --user-pool-id "$COGNITO_POOL_ID"; DONE+=("user pool")
fi
for s in "${DEL_SECRETS[@]}"; do
  run aws secretsmanager delete-secret --secret-id "$s" "${SECRET_ARGS[@]}" >/dev/null; DONE+=("secret $s")
done
if (( ${#DORIS_RULES[@]} )); then
  run aws ec2 revoke-security-group-ingress --group-id "$DORIS_SG" --security-group-rule-ids "${DORIS_RULES[@]}" >/dev/null
  DONE+=("${#DORIS_RULES[@]} $DORIS_SG rules")
fi
if (( ${#SGS[@]} )); then
  wait_gone 30 20 "network interfaces still use $RT_SG / $VPCE_SG after about 10 minutes. Runtime ENIs are released asynchronously; re-run later" enis_gone
  revoke_refs egress "$RT_SG" "$VPCE_SG"
  revoke_refs ingress "$VPCE_SG" "$RT_SG"
  for sg in "${SGS[@]}"; do run aws ec2 delete-security-group --group-id "$sg"; DONE+=("SG $sg"); done
fi
for role in "${DEL_ROLES[@]}"; do
  fetch aws iam list-role-policies --role-name "$role" --query PolicyNames --output text
  read -ra policies <<<"$OUT"
  for p in "${policies[@]}"; do run aws iam delete-role-policy --role-name "$role" --policy-name "$p"; done
  run aws iam delete-role --role-name "$role"; DONE+=("role $role")
done

[[ "$APPLY" == "1" ]] && verb=deleted || verb="dry-run, APPLY=1 would delete"
printf -v list '%s, ' "${DONE[@]}"; list="${list%, }"
log "done ($verb: ${list:-nothing}). Kept: $STATE_FILE (the record), log groups, X-Ray settings. Doris side (DROP USER mcp_svc, DROP DATABASE system_mcp) is a separate step."
