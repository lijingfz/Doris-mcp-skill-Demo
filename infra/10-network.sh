#!/usr/bin/env bash
# P0 / T0.2 — Network for AgentCore Runtime (VPC mode) → Doris.
#   * SG doris-mcp-rt   (Runtime ENIs): no ingress; egress only tcp 9030/8030 → Doris SG,
#                                        tcp 443 → doris-mcp-vpce, tcp 443 → S3 prefix list
#   * SG doris-mcp-vpce (interface endpoints): ingress tcp 443 from doris-mcp-rt only; no egress
#   * doris-demo-sg: + ingress tcp 9030/8030 from doris-mcp-rt (SG reference, no CIDR)
#   * VPC endpoints: S3 (Gateway, main route table); logs + secretsmanager (Interface, private DNS)
# Dry-run by default. APPLY=1 to execute. Safe to re-run.
source "$(dirname "$0")/lib.sh"

S3_SERVICE="com.amazonaws.$AWS_REGION.s3"
INTERFACE_SERVICES=(logs secretsmanager)

sg_lookup() {
  none_to_empty "$(aws ec2 describe-security-groups \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=$1" \
    --query 'SecurityGroups[0].GroupId' --output text)"
}

# ensure_sg NAME DESCRIPTION → prints the group ID (or a placeholder in dry-run)
ensure_sg() {
  local name="$1" desc="$2" id
  id="$(sg_lookup "$name")"
  if [[ -n "$id" ]]; then log "SG $name exists: $id"; echo "$id"; return; fi
  id="$(run aws ec2 create-security-group --vpc-id "$VPC_ID" --group-name "$name" \
    --description "$desc" --tag-specifications "ResourceType=security-group,$(tags "$name")" \
    --query GroupId --output text)"
  echo "${id:-$(placeholder "$name")}"
}

# revoke_default_egress SG — remove the allow-all egress rule a new SG gets by default
revoke_default_egress() {
  local sg="$1" n=1
  if ! is_placeholder "$sg"; then
    n="$(aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$sg" \
      --query "length(SecurityGroupRules[?IsEgress && IpProtocol=='-1' && CidrIpv4=='0.0.0.0/0'])" --output text)"
  fi
  if [[ "$n" == "0" ]]; then log "SG $sg: default egress already removed"; return; fi
  run aws ec2 revoke-security-group-egress --group-id "$sg" \
    --ip-permissions 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}]' >/dev/null
}

# allow ingress|egress SG PORT sg|pl PEER DESCRIPTION — idempotent single-port TCP rule
allow() {
  local dir="$1" sg="$2" port="$3" kind="$4" peer="$5" desc="$6" egress=false match perm n=0
  [[ "$dir" == egress ]] && egress=true
  case "$kind" in
    sg) match="ReferencedGroupInfo.GroupId=='$peer'"
        perm="IpProtocol=tcp,FromPort=$port,ToPort=$port,UserIdGroupPairs=[{GroupId=$peer,Description=$desc}]" ;;
    pl) match="PrefixListId=='$peer'"
        perm="IpProtocol=tcp,FromPort=$port,ToPort=$port,PrefixListIds=[{PrefixListId=$peer,Description=$desc}]" ;;
    *)  log "FATAL: unsupported peer kind $kind (only SG references and prefix lists)"; exit 1 ;;
  esac
  if ! is_placeholder "$sg" && ! is_placeholder "$peer"; then
    n="$(aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$sg" \
      --query "length(SecurityGroupRules[?IsEgress==\`$egress\` && IpProtocol=='tcp' && FromPort==\`$port\` && ToPort==\`$port\` && $match])" \
      --output text)"
  fi
  if [[ "$n" != "0" ]]; then log "rule exists: $dir $sg tcp/$port $peer"; return; fi
  run aws ec2 "authorize-security-group-$dir" --group-id "$sg" --ip-permissions "$perm" \
    --tag-specifications "ResourceType=security-group-rule,$(tags "$desc")" >/dev/null
}

vpce_lookup() { # SERVICE TYPE
  none_to_empty "$(aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" \
    "Name=service-name,Values=$1" "Name=vpc-endpoint-type,Values=$2" \
    "Name=vpc-endpoint-state,Values=pending,available" \
    --query 'VpcEndpoints[0].VpcEndpointId' --output text)"
}

wait_vpce_available() { # ID...
  [[ "$APPLY" == "1" ]] || return 0
  local id state
  for id in "$@"; do
    for _ in $(seq 1 40); do
      state="$(aws ec2 describe-vpc-endpoints --vpc-endpoint-ids "$id" --query 'VpcEndpoints[0].State' --output text)"
      [[ "$state" == "available" ]] && { log "$id available"; break; }
      sleep 10
    done
    [[ "$state" == "available" ]] || { log "FATAL: $id state=$state"; exit 1; }
  done
}

# --- security groups --------------------------------------------------------
RT_SG="$(ensure_sg doris-mcp-rt "AgentCore Runtime dorismcp ENIs - egress to Doris and VPC endpoints only")"
VPCE_SG="$(ensure_sg doris-mcp-vpce "Interface VPC endpoints for doris-mcp - 443 from doris-mcp-rt only")"
revoke_default_egress "$RT_SG"
revoke_default_egress "$VPCE_SG"

allow egress  "$RT_SG"     9030 sg "$DORIS_SG"       doris-mcp-rt-to-doris-mysql
allow egress  "$RT_SG"     8030 sg "$DORIS_SG"       doris-mcp-rt-to-doris-http
allow egress  "$RT_SG"     443  sg "$VPCE_SG"        doris-mcp-rt-to-vpce
allow egress  "$RT_SG"     443  pl "$S3_PREFIX_LIST" doris-mcp-rt-to-s3
allow ingress "$VPCE_SG"   443  sg "$RT_SG"          doris-mcp-vpce-from-rt
allow ingress "$DORIS_SG"  9030 sg "$RT_SG"          doris-mysql-from-mcp-rt
allow ingress "$DORIS_SG"  8030 sg "$RT_SG"          doris-http-from-mcp-rt
is_placeholder "$RT_SG"   || state_set RT_SG "$RT_SG"
is_placeholder "$VPCE_SG" || state_set VPCE_SG "$VPCE_SG"

# --- VPC endpoints ----------------------------------------------------------
new_endpoints=()
VPCE_S3="$(vpce_lookup "$S3_SERVICE" Gateway)"
if [[ -z "$VPCE_S3" ]]; then
  VPCE_S3="$(run aws ec2 create-vpc-endpoint --vpc-id "$VPC_ID" --vpc-endpoint-type Gateway \
    --service-name "$S3_SERVICE" --route-table-ids "$MAIN_RTB" \
    --tag-specifications "ResourceType=vpc-endpoint,$(tags doris-mcp-s3)" \
    --query VpcEndpoint.VpcEndpointId --output text)"
  VPCE_S3="${VPCE_S3:-$(placeholder vpce-s3)}"
  is_placeholder "$VPCE_S3" || new_endpoints+=("$VPCE_S3")
else
  log "S3 gateway endpoint exists: $VPCE_S3"
fi
is_placeholder "$VPCE_S3" || state_set VPCE_S3 "$VPCE_S3"

for svc in "${INTERFACE_SERVICES[@]}"; do
  key="VPCE_$(echo "$svc" | tr '[:lower:]' '[:upper:]')"
  id="$(vpce_lookup "com.amazonaws.$AWS_REGION.$svc" Interface)"
  if [[ -z "$id" ]]; then
    id="$(run aws ec2 create-vpc-endpoint --vpc-id "$VPC_ID" --vpc-endpoint-type Interface \
      --service-name "com.amazonaws.$AWS_REGION.$svc" --subnet-ids "$SUBNET_AZ4" "$SUBNET_AZ1" \
      --security-group-ids "$VPCE_SG" --private-dns-enabled \
      --tag-specifications "ResourceType=vpc-endpoint,$(tags "doris-mcp-$svc")" \
      --query VpcEndpoint.VpcEndpointId --output text)"
    id="${id:-$(placeholder "vpce-$svc")}"
    is_placeholder "$id" || new_endpoints+=("$id")
  else
    log "$svc interface endpoint exists: $id"
  fi
  is_placeholder "$id" || state_set "$key" "$id"
done
[[ ${#new_endpoints[@]} -eq 0 ]] || wait_vpce_available "${new_endpoints[@]}"

# --- self-check: no open inbound anywhere we touched ------------------------
for sg in "$RT_SG" "$VPCE_SG" "$DORIS_SG"; do
  is_placeholder "$sg" && continue
  open="$(aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$sg" \
    --query "length(SecurityGroupRules[?!IsEgress && (CidrIpv4=='0.0.0.0/0' || CidrIpv6=='::/0')])" --output text)"
  [[ "$open" == "0" ]] || { log "FATAL: $sg has an open inbound rule"; exit 1; }
  log "self-check $sg: no open inbound rule"
done
if ! is_placeholder "$RT_SG"; then
  log "doris-mcp-rt rules:"
  aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$RT_SG" \
    --query 'SecurityGroupRules[].[IsEgress,IpProtocol,FromPort,ReferencedGroupInfo.GroupId||PrefixListId||CidrIpv4]' \
    --output text >&2
fi
log "done (APPLY=$APPLY)"
