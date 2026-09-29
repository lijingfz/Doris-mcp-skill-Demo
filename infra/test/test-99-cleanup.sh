#!/usr/bin/env bash
# Offline tests for infra/99-cleanup.sh. A fake `aws` (python: a JSON "world" of the project's resources,
# --query evaluated with jmespath like the real CLI) and a fake `sleep` on PATH record every call; no AWS access.
#   bash infra/test/test-99-cleanup.sh
set -uo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
FAKE_PY=""
for py in python3 "$INFRA_DIR/../.venv/bin/python"; do
  if "$py" -c 'import jmespath' 2>/dev/null; then FAKE_PY="$(command -v "$py")"; break; fi
done
[[ -n "$FAKE_PY" ]] || { echo "FAIL setup: no python with jmespath for the fake aws"; echo "1 failed"; exit 1; }

# Fake AWS CLI over $FAKE_WORLD (JSON, rewritten by every write). Logs "$*" to $FAKE_LOG and the region the
# call would use to $FAKE_LOG.region. Errors look like the real CLI's (stderr "An error occurred (Code)", exit 254).
{ echo "#!$FAKE_PY"; cat <<'FAKE'
import json, os, sys
import jmespath

argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(" ".join(argv) + "\n")
with open(os.environ["FAKE_LOG"] + ".region", "a") as f:
    f.write(os.environ.get("AWS_REGION", "-") + "\n")
service, op, rest = argv[0], argv[1], argv[2:]
opts, key = {}, None
for a in rest:
    if a.startswith("--"):
        key = a[2:]; opts[key] = []
    elif key is not None:
        opts[key].append(a)
one = lambda k: opts[k][0]
world_path = os.environ["FAKE_WORLD"]
w = json.load(open(world_path))


def fail(code, op_name, msg="fake error"):
    sys.stderr.write(f"\nAn error occurred ({code}) when calling the {op_name} operation: {msg}\n")
    sys.exit(254)


def filters():
    out = {}
    for f in opts.get("filters", []):
        name, values = f.split(",Values=", 1)
        out[name.removeprefix("Name=")] = values.split(",")
    return out


def text(v):
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, list):
        if all(not isinstance(x, (list, dict)) for x in v):
            return "\t".join(text(x) for x in v)
        return "\n".join(text(x) for x in v)
    if isinstance(v, dict):
        return "\t".join(text(v[k]) for k in sorted(v))
    return str(v)


def enis_in_use():
    """The Runtime's ENIs go some polls after its stack, the endpoints' with the endpoints."""
    if w["stacks"] or any(e["State"] != "deleted" for e in w["vpc_endpoints"]):
        return True
    if w["eni_polls"] > 0:
        w["eni_polls"] -= 1
        return True
    return False


def gateway(gid, op_name):
    if gid not in w["gateways"]:
        fail("ResourceNotFoundException", op_name, f"Gateway {gid} not found")
    return w["gateways"][gid]


def role(name, op_name):
    if name not in w["roles"]:
        fail("NoSuchEntity", op_name, f"The role with name {name} cannot be found.")
    return w["roles"][name]


resp = {}
call = f"{service} {op}"
if w.get("deny") == call:
    fail("AccessDeniedException", op, "not authorized")
if call == "sts get-caller-identity":
    resp = {"Account": w["account"], "UserId": "AIDAFIXTURE", "Arn": f"arn:aws:iam::{w['account']}:user/fixture"}
elif call == "bedrock-agentcore-control get-gateway":
    g = gateway(one("gateway-identifier"), "GetGateway")
    resp = {k: g[k] for k in ("gatewayId", "name", "gatewayArn", "status")}
elif call == "bedrock-agentcore-control list-tags-for-resource":
    g = [g for g in w["gateways"].values() if g["gatewayArn"] == one("resource-arn")]
    if not g:
        fail("ResourceNotFoundException", "ListTagsForResource")
    resp = {"tags": g[0]["tags"]}
elif call == "bedrock-agentcore-control get-gateway-target":
    t = gateway(one("gateway-identifier"), "GetGatewayTarget")["targets"].get(one("target-id"))
    if t is None:
        fail("ResourceNotFoundException", "GetGatewayTarget", "Target not found")
    if t["status"] == "DELETING":
        t["polls"] -= 1
        if t["polls"] < 0:
            del gateway(one("gateway-identifier"), "GetGatewayTarget")["targets"][one("target-id")]
            json.dump(w, open(world_path, "w"))
            fail("ResourceNotFoundException", "GetGatewayTarget", "Target not found")
    resp = {"targetId": one("target-id"), "name": t["name"], "status": t["status"]}
elif call == "bedrock-agentcore-control delete-gateway-target":
    t = gateway(one("gateway-identifier"), "DeleteGatewayTarget")["targets"][one("target-id")]
    t["status"] = "DELETING"
    resp = {"targetId": one("target-id"), "status": "DELETING"}
elif call == "bedrock-agentcore-control delete-gateway":
    g = gateway(one("gateway-identifier"), "DeleteGateway")
    if g["targets"]:
        fail("ValidationException", "DeleteGateway", "Gateway has targets")
    del w["gateways"][one("gateway-identifier")]
    resp = {"gatewayId": one("gateway-identifier"), "status": "DELETING"}
elif call == "cloudformation describe-stacks":
    s = w["stacks"].get(one("stack-name"))
    if s is None:
        fail("ValidationError", "DescribeStacks", f"Stack with id {one('stack-name')} does not exist")
    resp = {"Stacks": [s]}
elif call == "cloudformation delete-stack":
    w["stacks"].pop(one("stack-name"), None)
elif call == "cloudformation wait":
    assert opts == {"stack-name": [w["stack_name"]]} and rest[0] == "stack-delete-complete", rest
elif call == "ec2 describe-vpc-endpoints":
    ids = filters()["vpc-endpoint-id"]
    for e in w["vpc_endpoints"]:  # deleting -> deleted after one more poll; deleted ones linger
        if e["VpcEndpointId"] in ids and e["State"] == "deleting":
            e["polls"] -= 1
            if e["polls"] < 0:
                e["State"] = "deleted"
    resp = {"VpcEndpoints": [{k: v for k, v in e.items() if k != "polls"} for e in w["vpc_endpoints"]
                             if e["VpcEndpointId"] in ids]}
elif call == "ec2 delete-vpc-endpoints":
    bad = []
    for i in opts["vpc-endpoint-ids"]:
        e = [e for e in w["vpc_endpoints"] if e["VpcEndpointId"] == i]
        if e:
            e[0].update(State="deleting", polls=1)
        else:
            bad.append({"ResourceId": i, "Error": {"Code": "InvalidVpcEndpoint.NotFound"}})
    resp = {"Unsuccessful": bad}
elif call == "cognito-idp describe-user-pool":
    p = w["user_pools"].get(one("user-pool-id"))
    if p is None:
        fail("ResourceNotFoundException", "DescribeUserPool", "User pool does not exist.")
    resp = {"UserPool": {"Id": one("user-pool-id"), "Name": "doris-mcp-quick", "UserPoolTags": p["UserPoolTags"],
                         "DeletionProtection": "INACTIVE"}}
elif call == "cognito-idp describe-user-pool-domain":
    owner = w["domains"].get(one("domain"))
    resp = {"DomainDescription": {"UserPoolId": owner, "Domain": one("domain")} if owner else {}}
elif call == "cognito-idp delete-user-pool-domain":
    if w["domains"].get(one("domain")) != one("user-pool-id"):
        fail("InvalidParameterException", "DeleteUserPoolDomain", "No such domain for this pool")
    del w["domains"][one("domain")]
elif call == "cognito-idp delete-user-pool":
    if one("user-pool-id") in w["domains"].values():
        fail("InvalidParameterException", "DeleteUserPool", "User pool has a domain configured")
    del w["user_pools"][one("user-pool-id")]
elif call == "secretsmanager describe-secret":
    s = w["secrets"].get(one("secret-id"))
    if s is None:
        fail("ResourceNotFoundException", "DescribeSecret", "Secrets Manager can't find the specified secret.")
    resp = {"Name": one("secret-id"), **s}
elif call == "secretsmanager delete-secret":
    s = w["secrets"].get(one("secret-id"))
    if s is None or s.get("DeletedDate"):
        fail("InvalidRequestException", "DeleteSecret", "already scheduled for deletion or missing")
    if "force-delete-without-recovery" in opts:
        del w["secrets"][one("secret-id")]
    else:
        days = int(one("recovery-window-in-days"))
        if not 7 <= days <= 30:
            fail("InvalidParameterException", "DeleteSecret", "recovery window out of range")
        s["DeletedDate"] = "2026-10-05T00:00:00+00:00"
elif call == "ec2 describe-security-group-rules":
    gid = filters()["group-id"]
    resp = {"SecurityGroupRules": [r for r in w["sg_rules"] if r["GroupId"] in gid]}
elif op in ("revoke-security-group-ingress", "revoke-security-group-egress"):
    egress = op.endswith("egress")
    for rid in opts["security-group-rule-ids"]:
        r = [r for r in w["sg_rules"] if r["SecurityGroupRuleId"] == rid and r["GroupId"] == one("group-id")
             and r["IsEgress"] == egress]
        if not r:
            fail("InvalidSecurityGroupRuleId.NotFound", op, rid)
        w["sg_rules"].remove(r[0])
    resp = {"Return": True}
elif call == "ec2 describe-security-groups":
    gid = filters()["group-id"]
    resp = {"SecurityGroups": [g for g in w["security_groups"] if g["GroupId"] in gid]}
elif call == "ec2 describe-network-interfaces":
    gid = filters()["group-id"]
    resp = {"NetworkInterfaces": [{"NetworkInterfaceId": "eni-fixture", "Groups": [{"GroupId": g} for g in gid]}]
            if enis_in_use() else []}
elif call == "ec2 delete-security-group":
    gid = one("group-id")
    if any(r.get("ReferencedGroupInfo", {}).get("GroupId") == gid and r["GroupId"] != gid for r in w["sg_rules"]):
        fail("DependencyViolation", "DeleteSecurityGroup", "resource has a dependent object")
    if w["stacks"] or any(e["State"] != "deleted" for e in w["vpc_endpoints"]) or w["eni_polls"] > 0:
        fail("DependencyViolation", "DeleteSecurityGroup", "in use by a network interface")
    w["security_groups"] = [g for g in w["security_groups"] if g["GroupId"] != gid]
    w["sg_rules"] = [r for r in w["sg_rules"] if r["GroupId"] != gid]
elif call == "iam list-role-tags":
    resp = {"Tags": role(one("role-name"), "ListRoleTags")["Tags"], "IsTruncated": False}
elif call == "iam list-role-policies":
    resp = {"PolicyNames": role(one("role-name"), "ListRolePolicies")["policies"], "IsTruncated": False}
elif call == "iam delete-role-policy":
    role(one("role-name"), "DeleteRolePolicy")["policies"].remove(one("policy-name"))
elif call == "iam delete-role":
    if role(one("role-name"), "DeleteRole")["policies"]:
        fail("DeleteConflict", "DeleteRole", "Cannot delete entity, must delete policies first.")
    del w["roles"][one("role-name")]
else:
    sys.stderr.write(f"fake aws: unexpected call: {' '.join(argv)}\n")
    sys.exit(99)
json.dump(w, open(world_path, "w"))
if "query" in opts:
    resp = jmespath.search(one("query"), resp)
if opts.get("output") == ["text"]:
    print(text(resp))
elif resp:
    print(json.dumps(resp, indent=4))
FAKE
} > "$TMP/bin/aws"
printf '#!/usr/bin/env bash\nprintf "sleep %%s\\n" "$*" >> "$FAKE_LOG"\n' > "$TMP/bin/sleep"
chmod +x "$TMP/bin/aws" "$TMP/bin/sleep"

# new_world [PYTHON-STATEMENTS] — the demo's resources, all present and tagged; the statements edit `w`.
new_world() {
  python3 - "$TMP/world.json" "${1-}" <<'PY'
import json, sys
tag = lambda v="doris-mcp-demo", k="Project": [{"Key": "Name", "Value": "fixture"}, {"Key": k, "Value": v}]
rule = lambda rid, gid, egress, port, **peer: {"SecurityGroupRuleId": rid, "GroupId": gid, "IsEgress": egress,
    "IpProtocol": "tcp", "FromPort": port, "ToPort": port, **peer}
ref = lambda g: {"ReferencedGroupInfo": {"GroupId": g, "UserId": "111122223333"}}
w = {
    "account": "111122223333", "stack_name": "AgentCore-dorismcp-default", "eni_polls": 2,
    "gateways": {
        "gw-fixture0001": {"gatewayId": "gw-fixture0001", "name": "doris-mcp-gw", "status": "READY",
                           "gatewayArn": "arn:aws:bedrock-agentcore:us-east-1:111122223333:gateway/gw-fixture0001",
                           "tags": {"Project": "doris-mcp-demo"},
                           "targets": {"TGTFIXTURE1": {"name": "doris", "status": "READY", "polls": 1}}},
        "gw-other0002": {"gatewayId": "gw-other0002", "name": "pragent-github-gw", "status": "READY",
                         "gatewayArn": "arn:aws:bedrock-agentcore:us-east-1:111122223333:gateway/gw-other0002",
                         "tags": {}, "targets": {}}},
    "stacks": {"AgentCore-dorismcp-default": {
        "StackName": "AgentCore-dorismcp-default", "StackStatus": "UPDATE_COMPLETE",
        "Tags": [{"Key": "agentcore:project-name", "Value": "dorismcp"},
                 {"Key": "agentcore:target-name", "Value": "default"}]}},
    "vpc_endpoints": [{"VpcEndpointId": i, "State": "available", "Tags": tag()}
                      for i in ("vpce-s3fixture", "vpce-logsfixture", "vpce-smfixture")],
    "user_pools": {"us-east-1_EXAMPLE": {"UserPoolTags": {"Project": "doris-mcp-demo"}}},
    "domains": {"doris-mcp-111122223333": "us-east-1_EXAMPLE"},
    "secrets": {n: {"ARN": f"arn:aws:secretsmanager:us-east-1:111122223333:secret:{n}-AbCdEf", "Tags": tag()[1:]}
                for n in ("doris-mcp/cognito-demo-user", "doris-mcp/mcp_svc")},
    # doris-demo-sg: the two rules 10-network.sh added, then rules that are not ours (the dev box's /32 carries
    # the project tag on purpose: the selector is the reference to doris-mcp-rt, the tag only a second check).
    "sg_rules": [
        rule("sgr-doris9030", "sg-doris", False, 9030, **ref("sg-rt"), Tags=tag()),
        rule("sgr-doris8030", "sg-doris", False, 8030, **ref("sg-rt"), Tags=tag()),
        rule("sgr-dorisdev", "sg-doris", False, 9030, CidrIpv4="203.0.113.10/32", Tags=tag()),
        rule("sgr-dorisother", "sg-doris", False, 9030, **ref("sg-other"), Tags=[]),
        rule("sgr-dorisegress", "sg-doris", True, 443, **ref("sg-other"), Tags=[]),
        rule("sgr-rt9030", "sg-rt", True, 9030, **ref("sg-doris"), Tags=tag()),
        rule("sgr-rt8030", "sg-rt", True, 8030, **ref("sg-doris"), Tags=tag()),
        rule("sgr-rtvpce", "sg-rt", True, 443, **ref("sg-vpce"), Tags=tag()),
        rule("sgr-rts3", "sg-rt", True, 443, PrefixListId="pl-fixture", Tags=tag()),
        rule("sgr-vpcert", "sg-vpce", False, 443, **ref("sg-rt"), Tags=tag())],
    "security_groups": [{"GroupId": g, "GroupName": n, "Tags": tag()}
                        for g, n in (("sg-rt", "doris-mcp-rt"), ("sg-vpce", "doris-mcp-vpce"))]
                       + [{"GroupId": "sg-doris", "GroupName": "doris-demo-sg", "Tags": []}],
    "roles": {"doris-mcp-gateway-role": {"Tags": tag()[1:], "policies": ["invoke-dorismcp-runtime"]},
              "doris-mcp-runtime-role": {"Tags": tag()[1:], "policies": ["doris-mcp-runtime"]}},
}
exec(sys.argv[2])
json.dump(w, open(sys.argv[1], "w"))
PY
}
FAILS=0
check() { # NAME EXPECTED ACTUAL
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
# run_script APPLY [VAR=value...] — runs the script against the current world and a fresh state.env;
# sets RC, OUT, LOG, WRITES (the mutating calls, in order) and DRY (the DRY-RUN lines, in order).
run_script() {
  local apply="$1"; shift
  : > "$TMP/aws.log"; : > "$TMP/aws.log.region"
  printf '%s\n' '# test state' 'AWS_REGION=us-east-1' 'ACCOUNT_ID=111122223333' 'GW_ID=gw-fixture0001' \
    'GW_TARGET_ID=TGTFIXTURE1' 'VPCE_S3=vpce-s3fixture' 'VPCE_LOGS=vpce-logsfixture' 'VPCE_SECRETSMANAGER=vpce-smfixture' \
    'COGNITO_POOL_ID=us-east-1_EXAMPLE' 'COGNITO_DOMAIN=doris-mcp-111122223333.auth.us-east-1.amazoncognito.com' \
    'DORIS_SG=sg-doris' 'RT_SG=sg-rt' 'VPCE_SG=sg-vpce' > "$TMP/state.env"
  cp "$TMP/state.env" "$TMP/state.env.orig"
  OUT="$(env -u STACK_NAME -u SECRET_RECOVERY_DAYS -u FORCE_DELETE_SECRETS "$@" PATH="$TMP/bin:$PATH" \
    FAKE_LOG="$TMP/aws.log" FAKE_WORLD="$TMP/world.json" APPLY="$apply" STATE_FILE="$TMP/state.env" \
    bash "$INFRA_DIR/99-cleanup.sh" 2>&1)"
  RC=$?
  LOG="$(cat "$TMP/aws.log")"
  WRITES="$(grep -E '^[a-z0-9-]+ (delete-|revoke-|wait )' <<<"$LOG" | grep -v '^sleep')"
  DRY="$(sed -n 's/^DRY-RUN: aws //p' <<<"$OUT")"
}
has() { [[ "$1" == *"$2"* ]] && echo yes || echo no; }
count() { grep -c -- "$2" <<<"$1"; }
# The full teardown, in order: target (then its wait), Gateway, stack, endpoints, Cognito, secrets,
# doris-demo-sg's two rules, the SG cross-references, both SGs, the roles' inline policies and the roles.
ALL_WRITES="bedrock-agentcore-control delete-gateway-target --gateway-identifier gw-fixture0001 --target-id TGTFIXTURE1
bedrock-agentcore-control delete-gateway --gateway-identifier gw-fixture0001
cloudformation delete-stack --stack-name AgentCore-dorismcp-default
cloudformation wait stack-delete-complete --stack-name AgentCore-dorismcp-default
ec2 delete-vpc-endpoints --vpc-endpoint-ids vpce-s3fixture vpce-logsfixture vpce-smfixture
cognito-idp delete-user-pool-domain --domain doris-mcp-111122223333 --user-pool-id us-east-1_EXAMPLE
cognito-idp delete-user-pool --user-pool-id us-east-1_EXAMPLE
secretsmanager delete-secret --secret-id doris-mcp/cognito-demo-user --recovery-window-in-days 7
secretsmanager delete-secret --secret-id doris-mcp/mcp_svc --recovery-window-in-days 7
ec2 revoke-security-group-ingress --group-id sg-doris --security-group-rule-ids sgr-doris9030 sgr-doris8030
ec2 revoke-security-group-egress --group-id sg-rt --security-group-rule-ids sgr-rtvpce
ec2 revoke-security-group-ingress --group-id sg-vpce --security-group-rule-ids sgr-vpcert
ec2 delete-security-group --group-id sg-rt
ec2 delete-security-group --group-id sg-vpce
iam delete-role-policy --role-name doris-mcp-gateway-role --policy-name invoke-dorismcp-runtime
iam delete-role --role-name doris-mcp-gateway-role
iam delete-role-policy --role-name doris-mcp-runtime-role --policy-name doris-mcp-runtime
iam delete-role --role-name doris-mcp-runtime-role"
SG_AND_IAM_WRITES="$(sed -n '/revoke-security-group-egress/,$p' <<<"$ALL_WRITES")"

# --- dry-run -----------------------------------------------------------------
new_world; run_script 0
check "dry-run: exit 0" 0 "$RC"
check "dry-run: no delete / revoke / wait call" "" "$WRITES"
check "dry-run: every DRY-RUN line, in order" "$ALL_WRITES" "$DRY"
check "dry-run: checks the account first" "sts get-caller-identity --query Account --output text" "$(head -1 <<<"$LOG")"
check "dry-run: no sleep" 0 "$(count "$LOG" '^sleep')"
check "dry-run: state.env unchanged" "" "$(diff "$TMP/state.env.orig" "$TMP/state.env")"

# --- apply, everything present -------------------------------------------------
new_world; run_script 1
check "apply: exit 0" 0 "$RC"
check "apply: deletes in dependency order" "$ALL_WRITES" "$WRITES"
check "apply: target gone before delete-gateway (polled get-gateway-target)" yes \
  "$(sed -n '/delete-gateway-target/,/delete-gateway --/p' <<<"$LOG" | grep -q 'get-gateway-target' && echo yes || echo no)"
check "apply: waits for the endpoints before Cognito" yes \
  "$(sed -n '/delete-vpc-endpoints/,/delete-user-pool-domain/p' <<<"$LOG" | grep -q 'describe-vpc-endpoints' && echo yes || echo no)"
check "apply: polls the ENIs (20 s apart) until free, before the SG revokes" "yes|2" \
  "$(sed -n '/revoke-security-group-ingress --group-id sg-doris/,/revoke-security-group-egress/p' <<<"$LOG" | grep -q 'describe-network-interfaces --filters Name=group-id,Values=sg-rt,sg-vpce' && echo yes || echo no)|$(count "$LOG" '^sleep 20$')"
check "apply: the other project's Gateway untouched" yes \
  "$(python3 -c 'import json,sys; print("yes" if "gw-other0002" in json.load(open(sys.argv[1]))["gateways"] else "no")' "$TMP/world.json")"
check "apply: doris-demo-sg keeps its other rules (dev /32, other SG, egress)" "sgr-dorisdev sgr-dorisother sgr-dorisegress" \
  "$(python3 -c 'import json,sys; print(" ".join(r["SecurityGroupRuleId"] for r in json.load(open(sys.argv[1]))["sg_rules"] if r["GroupId"] == "sg-doris"))' "$TMP/world.json")"
check "apply: state.env unchanged (kept as the record)" "" "$(diff "$TMP/state.env.orig" "$TMP/state.env")"
check "apply: says state.env is kept and the Doris side is separate" "yes|yes" \
  "$(has "$OUT" "state.env")|$(has "$OUT" "DROP USER mcp_svc")"
check "apply: every call in the state's region" "us-east-1" "$(sort -u "$TMP/aws.log.region")"

# re-run after a full teardown: nothing left, nothing to do
run_script 1
check "re-run after a full teardown: exit 0, no write" "0|" "$RC|$WRITES"
check "re-run after a full teardown: says already deleted" yes "$(has "$OUT" "already deleted")"

# caller's AWS_REGION does not win over state.env
new_world; run_script 0 AWS_REGION=eu-west-1 AWS_DEFAULT_REGION=eu-west-1
check "caller AWS_REGION=eu-west-1: calls still in us-east-1" "us-east-1" "$(sort -u "$TMP/aws.log.region")"

# --- refusals: nothing is deleted ----------------------------------------------
new_world 'w["account"] = "000000000000"'; run_script 1
check "wrong account: fails" 1 "$RC"
check "wrong account: no write" "" "$WRITES"
check "wrong account: FATAL" yes "$(has "$OUT" "FATAL")"
check "wrong account: no call after sts" "sts get-caller-identity --query Account --output text" "$LOG"

# refuse PYTHON-EDIT NAME — a world edit that must stop the run with FATAL before any write
refuse() {
  new_world "$1"; run_script 1
  check "$2: fails" 1 "$RC"
  check "$2: FATAL" yes "$(has "$OUT" "FATAL")"
  check "$2: no write at all" "" "$WRITES"
}
refuse 'w["gateways"]["gw-fixture0001"]["name"] = "pragent-github-gw"' "Gateway named otherwise"
refuse 'w["gateways"]["gw-fixture0001"]["tags"] = {"Project": "other"}' "Gateway tagged for another project"
refuse 'w["gateways"]["gw-fixture0001"]["tags"] = {}' "Gateway without tags"
refuse 'w["stacks"]["AgentCore-dorismcp-default"]["Tags"][0]["Value"] = "otherproject"' "stack of another agentcore project"
refuse 'w["vpc_endpoints"][2]["Tags"] = []' "VPC endpoint without the tag"
refuse 'w["user_pools"]["us-east-1_EXAMPLE"]["UserPoolTags"] = {"Project": "other"}' "user pool tagged otherwise"
refuse 'w["domains"]["doris-mcp-111122223333"] = "us-east-1_OTHER"' "Cognito domain of another pool"
refuse 'w["secrets"]["doris-mcp/mcp_svc"]["Tags"] = []' "secret without the tag"
refuse 'w["sg_rules"][1]["Tags"] = []' "doris-demo-sg rule referencing RT_SG without the tag"
refuse 'w["security_groups"][1]["Tags"] = [{"Key": "Project", "Value": "other"}]' "SG tagged otherwise"
refuse 'w["roles"]["doris-mcp-runtime-role"]["Tags"] = []' "IAM role without the tag"
refuse 'w["deny"] = "bedrock-agentcore-control get-gateway"' "get-gateway denied (not the same as deleted)"
refuse 'w["deny"] = "iam list-role-tags"' "list-role-tags denied (not the same as deleted)"
refuse 'w["deny"] = "secretsmanager describe-secret"' "describe-secret denied (not the same as deleted)"

new_world; run_script 1 SECRET_RECOVERY_DAYS=3
check "SECRET_RECOVERY_DAYS=3: fails before any AWS call" "1|" "$RC|$LOG"
new_world; run_script 1 SECRET_RECOVERY_DAYS=08
check "SECRET_RECOVERY_DAYS=08: fails before any AWS call" "1|" "$RC|$LOG"

# --- ENIs still in use ----------------------------------------------------------
new_world 'w["eni_polls"] = 10**6'; run_script 1
check "ENIs stay: fails" 1 "$RC"
check "ENIs stay: says to re-run later" yes "$(has "$OUT" "re-run later")"
check "ENIs stay: bounded wait (30 polls, 29 x 20 s)" "30|29" \
  "$(count "$LOG" 'describe-network-interfaces')|$(count "$LOG" '^sleep 20$')"
check "ENIs stay: no SG deleted, no cross-reference revoked, no role touched" 0 \
  "$(grep -cE 'delete-security-group|revoke-security-group-egress|group-id sg-vpce|iam delete' <<<"$WRITES")"
check "ENIs stay: everything before the SG step done" \
  "$(sed -n '1,/revoke-security-group-ingress --group-id sg-doris/p' <<<"$ALL_WRITES")" "$WRITES"
# ... then the ENIs go away: the re-run skips what is gone and finishes
python3 -c 'import json,sys; w=json.load(open(sys.argv[1])); w["eni_polls"]=0; json.dump(w, open(sys.argv[1], "w"))' "$TMP/world.json"
run_script 1
check "re-run after the ENI timeout: exit 0" 0 "$RC"
check "re-run after the ENI timeout: only the SG and IAM steps" "$SG_AND_IAM_WRITES" "$WRITES"
check "re-run after the ENI timeout: gone resources logged as already deleted" "yes|yes|yes|yes" \
  "$(has "$OUT" "Gateway gw-fixture0001 already deleted")|$(has "$OUT" "AgentCore-dorismcp-default already deleted")|$(has "$OUT" "vpce-smfixture already deleted")|$(has "$OUT" "us-east-1_EXAMPLE already deleted")"
check "re-run after the ENI timeout: secrets already scheduled are left alone" "0|yes" \
  "$(count "$LOG" 'delete-secret')|$(has "$OUT" "doris-mcp/mcp_svc already scheduled for deletion")"

# partial state: the target alone is gone; the stack is already being deleted
new_world 'w["gateways"]["gw-fixture0001"]["targets"] = {}'; run_script 1
check "target already gone: exit 0, delete-gateway without delete-gateway-target" "0|0|1" \
  "$RC|$(count "$WRITES" 'delete-gateway-target')|$(count "$WRITES" 'delete-gateway --gateway-identifier gw-fixture0001')"

# --- secrets knobs --------------------------------------------------------------
new_world; run_script 1 FORCE_DELETE_SECRETS=1
check "FORCE_DELETE_SECRETS=1: both secrets deleted without recovery" "2|0" \
  "$(count "$WRITES" 'delete-secret --secret-id doris-mcp/[a-z_-]* --force-delete-without-recovery$')|$(count "$WRITES" 'recovery-window')"
new_world; run_script 0 SECRET_RECOVERY_DAYS=30
check "SECRET_RECOVERY_DAYS=30: 30-day recovery window" 2 "$(count "$DRY" 'delete-secret --secret-id doris-mcp/[a-z_-]* --recovery-window-in-days 30$')"
new_world; run_script 0 FORCE_DELETE_SECRETS=0
check "FORCE_DELETE_SECRETS=0: the 7-day default" 2 "$(count "$DRY" 'delete-secret --secret-id doris-mcp/[a-z_-]* --recovery-window-in-days 7$')"

# --- STACK_NAME knob ------------------------------------------------------------
new_world 'w["stacks"] = {"AgentCore-dorismcp-other": dict(w["stacks"]["AgentCore-dorismcp-default"], StackName="AgentCore-dorismcp-other")}; w["stack_name"] = "AgentCore-dorismcp-other"'
run_script 1 STACK_NAME=AgentCore-dorismcp-other
check "STACK_NAME override: that stack is deleted and waited for" "0|1|1" \
  "$RC|$(count "$WRITES" '^cloudformation delete-stack --stack-name AgentCore-dorismcp-other$')|$(count "$WRITES" '^cloudformation wait stack-delete-complete --stack-name AgentCore-dorismcp-other$')"

if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS failed"; exit 1; fi
echo "all passed"
