#!/usr/bin/env python3
"""Upsert runtime `dorismcp` in dorismcp/agentcore/agentcore.json and fill aws-targets.json.

  --phase spike   codeLocation ../spike/p0-mcp/  (P0 / T0.4)
  --phase server  codeLocation ../mcp-server/    (P3 / T3.2: adds DORIS_SECRET_ID, PROFILE_SCOPE)

Values come from infra/state.env. Only non-secret values are written; env var names that
look like secrets are refused. codeLocation is relative to the project dir (dorismcp/).
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJECT_DIR = ROOT / "dorismcp" / "agentcore"
RUNTIME_NAME = "dorismcp"
CODE_LOCATIONS = {"spike": "../spike/p0-mcp/", "server": "../mcp-server/"}
SECRET_LIKE = re.compile(r"PASSWORD|TOKEN|SECRET_VALUE|ACCESS_KEY")


def load_state(path: pathlib.Path) -> dict[str, str]:
    state = {}
    for line in path.read_text().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
        if m:
            state[m.group(1)] = m.group(2)
    return state


def runtime_entry(phase: str, state: dict[str, str]) -> dict:
    env = {"DORIS_HOST": state["DORIS_PRIVATE_IP"], "DORIS_PORT": "9030", "DORIS_HTTP_PORT": "8030"}
    if phase == "server":
        env |= {"DORIS_SECRET_ID": "doris-mcp/mcp_svc", "PROFILE_SCOPE": "all"}
    bad = [k for k in env if SECRET_LIKE.search(k)]
    if bad:
        sys.exit(f"refusing secret-looking env vars: {bad}")
    return {
        "name": RUNTIME_NAME,
        "build": "CodeZip",
        "entrypoint": "mcp_server.py",
        "codeLocation": CODE_LOCATIONS[phase],
        "runtimeVersion": "PYTHON_3_12",
        "envVars": [{"name": k, "value": v} for k, v in env.items()],
        "networkMode": "VPC",
        "networkConfig": {
            "subnets": [state["SUBNET_AZ4"], state["SUBNET_AZ1"], state["SUBNET_AZ2"]],
            "securityGroups": [state["RT_SG"]],
        },
        "instrumentation": {"enableOtel": False},
        "protocol": "MCP",
        "authorizerType": "AWS_IAM",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phase", choices=sorted(CODE_LOCATIONS), required=True)
    parser.add_argument("--check", action="store_true", help="print the entry, do not write")
    args = parser.parse_args()

    state = load_state(ROOT / "infra" / "state.env")
    missing = [k for k in ("DORIS_PRIVATE_IP", "SUBNET_AZ4", "SUBNET_AZ1", "SUBNET_AZ2", "RT_SG") if not state.get(k)]
    if missing:
        sys.exit(f"missing in infra/state.env: {missing} (run T0.2 first)")
    entry = runtime_entry(args.phase, state)
    if args.check:
        print(json.dumps(entry, indent=2))
        return

    config_path = PROJECT_DIR / "agentcore.json"
    config = json.loads(config_path.read_text())
    runtimes = [r for r in config.get("runtimes", []) if r.get("name") != RUNTIME_NAME]
    config["runtimes"] = runtimes + [entry]
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    targets_path = PROJECT_DIR / "aws-targets.json"
    targets_path.write_text(json.dumps(
        [{"name": "default", "account": state["ACCOUNT_ID"], "region": state["AWS_REGION"]}], indent=2) + "\n")
    print(f"wrote {config_path.relative_to(ROOT)} (runtime {RUNTIME_NAME}, phase {args.phase}) and aws-targets.json")


if __name__ == "__main__":
    main()
