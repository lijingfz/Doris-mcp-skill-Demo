"""scripts/render-agentcore.py: the runtime entry written to dorismcp/agentcore/agentcore.json (P3 / T3.1).

    .venv/bin/python -m unittest discover -s scripts/test -p 'test_*.py' -v
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SCRIPT = Path(__file__).resolve().parents[1] / "render-agentcore.py"
_spec = importlib.util.spec_from_file_location("render_agentcore", _SCRIPT)
render = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render)

ROLE = "arn:aws:iam::111122223333:role/doris-mcp-runtime-role"
CDK_ROLE = "arn:aws:iam::111122223333:role/AgentCore-dorismcp-defaul-ApplicationAgentDorismcpR-30Mcwi4tCmaV"
STATE = {
    "ACCOUNT_ID": "111122223333", "AWS_REGION": "us-east-1", "DORIS_PRIVATE_IP": "10.9.8.7",
    "SUBNET_AZ4": "subnet-a", "SUBNET_AZ1": "subnet-b", "SUBNET_AZ2": "subnet-c", "RT_SG": "sg-rt",
    "RT_ROLE_ARN": ROLE,
}


def _env(entry: dict) -> dict:
    return {e["name"]: e["value"] for e in entry["envVars"]}


class TestServerEntry(unittest.TestCase):
    def test_uses_the_project_execution_role(self):
        self.assertEqual(render.runtime_entry("server", STATE)["executionRoleArn"], ROLE)

    def test_requires_the_project_role(self):
        state = {k: v for k, v in STATE.items() if k != "RT_ROLE_ARN"}
        with self.assertRaises(SystemExit) as cm:
            render.runtime_entry("server", state)
        self.assertIn("RT_ROLE_ARN", str(cm.exception))
        self.assertIn("infra/35-runtime-role.sh", str(cm.exception))

    def test_refuses_the_cdk_role(self):
        # The CLI's own role may invoke any Bedrock model (design §7); P3 replaces it.
        with self.assertRaises(SystemExit):
            render.runtime_entry("server", {**STATE, "RT_ROLE_ARN": CDK_ROLE})

    def test_refuses_a_role_of_another_account(self):
        with self.assertRaises(SystemExit):
            render.runtime_entry("server", {**STATE, "RT_ROLE_ARN": ROLE.replace("111122223333", "999999999999")})

    def test_reads_the_service_account_from_secrets_manager(self):
        entry = render.runtime_entry("server", STATE)
        self.assertEqual(_env(entry), {"DORIS_HOST": "10.9.8.7", "DORIS_PORT": "9030", "DORIS_HTTP_PORT": "8030",
                                       "DORIS_SECRET_ID": "doris-mcp/mcp_svc", "PROFILE_SCOPE": "all"})
        self.assertEqual(entry["codeLocation"], "../mcp-server/")

    def test_keeps_the_vpc_and_iam_inbound_auth(self):
        entry = render.runtime_entry("server", STATE)
        self.assertEqual(entry["networkConfig"], {"subnets": ["subnet-a", "subnet-b", "subnet-c"],
                                                  "securityGroups": ["sg-rt"]})
        self.assertEqual((entry["networkMode"], entry["authorizerType"], entry["protocol"]),
                         ("VPC", "AWS_IAM", "MCP"))


class TestSpikeEntry(unittest.TestCase):
    def test_spike_keeps_the_cli_role(self):
        # P0 history: the spike phase never set a role; RT_ROLE_ARN is not needed to re-render it.
        state = {k: v for k, v in STATE.items() if k != "RT_ROLE_ARN"}
        self.assertNotIn("executionRoleArn", render.runtime_entry("spike", state))


class TestMain(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.project = self.root / "dorismcp" / "agentcore"
        self.project.mkdir(parents=True)
        (self.root / "infra").mkdir()
        (self.root / "infra" / "state.env").write_text("# state\n" + "".join(f"{k}={v}\n" for k, v in STATE.items()))
        self.config = self.project / "agentcore.json"
        self.config.write_text(json.dumps({"name": "dorismcp", "runtimes": [
            {"name": "other", "build": "CodeZip"}, {"name": "dorismcp", "codeLocation": "../spike/p0-mcp/"}]}))
        for name, value in (("ROOT", self.root), ("PROJECT_DIR", self.project)):
            patcher = mock.patch.object(render, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _main(self, *argv: str) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            render.main(list(argv))
        return out.getvalue()

    def test_check_prints_without_writing(self):
        before = self.config.read_text()
        printed = json.loads(self._main("--phase", "server", "--check"))
        self.assertEqual(printed["executionRoleArn"], ROLE)
        self.assertEqual(self.config.read_text(), before)
        self.assertFalse((self.project / "aws-targets.json").exists())

    def test_write_replaces_only_the_dorismcp_runtime(self):
        self._main("--phase", "server")
        runtimes = json.loads(self.config.read_text())["runtimes"]
        self.assertEqual([r["name"] for r in runtimes], ["other", "dorismcp"])
        self.assertEqual(runtimes[1]["executionRoleArn"], ROLE)
        self.assertEqual(json.loads((self.project / "aws-targets.json").read_text()),
                         [{"name": "default", "account": "111122223333", "region": "us-east-1"}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
