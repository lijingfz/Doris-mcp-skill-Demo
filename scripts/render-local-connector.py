#!/usr/bin/env python3
"""Write quick/local-connector.json: Quick desktop Local stdio connector -> mcp-proxy-for-aws -> Runtime.

  scripts/render-local-connector.py [--aws-profile doris-demo]

RUNTIME_URL comes from infra/state.env (set by infra/30-gateway.sh). The file holds no secrets:
the proxy signs with the AWS profile on the laptop running Quick desktop.
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aws-profile", default="doris-demo", help="AWS profile name on the Quick desktop machine")
    args = parser.parse_args()

    state = dict(re.findall(r"^([A-Z0-9_]+)=(.*)$", (ROOT / "infra" / "state.env").read_text(), re.M))
    if not state.get("RUNTIME_URL"):
        sys.exit("RUNTIME_URL missing in infra/state.env (run infra/30-gateway.sh first)")
    connector = {
        "mcpServers": {
            "doris-agentcore": {
                "command": "uvx",
                "args": ["mcp-proxy-for-aws@latest", state["RUNTIME_URL"],
                         "--service", "bedrock-agentcore", "--region", state["AWS_REGION"], "--timeout", "55"],
                "env": {"AWS_PROFILE": args.aws_profile},
            }
        }
    }
    out = ROOT / "quick" / "local-connector.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(connector, indent=2) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
