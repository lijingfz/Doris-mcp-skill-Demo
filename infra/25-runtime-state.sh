#!/usr/bin/env bash
# P0 / T0.4 (and after every `agentcore deploy`) — record the deployed Runtime in state.env.
# Read-only on AWS. The agentcore CLI deploys runtime `dorismcp` of project `dorismcp` as
# `dorismcp_dorismcp`. Dry-run prints what would be recorded; APPLY=1 writes state.env.
source "$(dirname "$0")/lib.sh"

RUNTIME_NAME="${RUNTIME_NAME:-dorismcp_dorismcp}"
read -r arn rid < <(aws bedrock-agentcore-control list-agent-runtimes \
  --query "agentRuntimes[?agentRuntimeName=='$RUNTIME_NAME'] | [0].[agentRuntimeArn, agentRuntimeId]" --output text)
if [[ -z "$arn" || "$arn" == "None" ]]; then log "FATAL: runtime $RUNTIME_NAME not found (agentcore deploy first)"; exit 1; fi
read -r status role version < <(aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id "$rid" \
  --query '[status, roleArn, agentRuntimeVersion]' --output text)
log "runtime $RUNTIME_NAME: status=$status version=$version"
[[ "$status" == "READY" ]] || log "WARN: runtime is not READY yet"

state_set RUNTIME_ARN "$arn"
state_set RUNTIME_ID "$rid"
state_set RUNTIME_ROLE_ARN "$role"
state_set RUNTIME_URL "$(runtime_url "$arn")"
