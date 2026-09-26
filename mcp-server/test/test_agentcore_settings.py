"""P-06: runtime settings from environment variables / Secrets Manager (src/agentcore_ext/settings.py)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agentcore_ext.settings import SettingsError, load_settings  # noqa: E402

PW = "env-s3cret"
SECRET_PW = "sm-s3cret"
BASE = {"DORIS_HOST": "10.0.0.5", "DORIS_USER": "demo_ro", "DORIS_PASSWORD": PW}


class FakeSecrets:
    def __init__(self, secret_string=None, error=None):
        self.secret_string = secret_string
        self.error = error
        self.calls = []

    def get_secret_value(self, SecretId):
        self.calls.append(SecretId)
        if self.error:
            raise self.error
        return {"SecretString": self.secret_string}


def _secret(**doc):
    return FakeSecrets(json.dumps(doc))


class TestLoadSettings(unittest.TestCase):
    def test_env_credentials_and_defaults(self):
        s = load_settings(BASE)
        self.assertEqual((s.doris_host, s.doris_port, s.doris_http_port), ("10.0.0.5", 9030, 8030))
        self.assertEqual((s.doris_user, s.doris_password), ("demo_ro", PW))
        self.assertEqual((s.profile_scope, s.mcp_port), ("all", 8000))
        self.assertEqual(s.workspace_dir, str(Path(tempfile.gettempdir()) / "doris-mcp-workspace"))
        self.assertEqual(Path(s.config_dir), Path(__file__).resolve().parent.parent / "config")

    def test_overrides(self):
        s = load_settings({
            **BASE, "DORIS_PORT": "19030", "DORIS_HTTP_PORT": "18030", "PROFILE_SCOPE": "self",
            "DORIS_MCP_WORKSPACE_DIR": "/tmp/ws", "DORIS_MCP_CONFIG_DIR": "/tmp/cfg", "MCP_PORT": "8080",
        })
        self.assertEqual((s.doris_port, s.doris_http_port, s.profile_scope), (19030, 18030, "self"))
        self.assertEqual((s.workspace_dir, s.config_dir, s.mcp_port), ("/tmp/ws", "/tmp/cfg", 8080))

    def test_empty_env_password_is_allowed(self):
        self.assertEqual(load_settings({**BASE, "DORIS_PASSWORD": ""}).doris_password, "")

    def test_secret_wins_over_env_credentials(self):
        client = _secret(username="mcp_svc", password=SECRET_PW)
        s = load_settings({**BASE, "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}, secrets_client=client)
        self.assertEqual((s.doris_user, s.doris_password), ("mcp_svc", SECRET_PW))
        self.assertEqual(client.calls, ["doris-mcp/mcp_svc"])

    def test_secret_without_env_credentials(self):
        env = {"DORIS_HOST": "h", "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}
        s = load_settings(env, secrets_client=_secret(username="mcp_svc", password=SECRET_PW))
        self.assertEqual(s.doris_user, "mcp_svc")

    def test_repr_hides_password(self):
        self.assertNotIn(PW, repr(load_settings(BASE)))


class TestSettingsErrors(unittest.TestCase):
    def assertSettingsError(self, env, fragment, client=None):
        with self.assertRaises(SettingsError) as ctx:
            load_settings(env, secrets_client=client)
        message = str(ctx.exception)
        self.assertIn(fragment, message)
        for secret in (PW, SECRET_PW):
            self.assertNotIn(secret, message)

    def test_missing_host(self):
        self.assertSettingsError({**BASE, "DORIS_HOST": "  "}, "DORIS_HOST is required")

    def test_missing_credentials(self):
        self.assertSettingsError({"DORIS_HOST": "h"}, "set DORIS_SECRET_ID, or DORIS_USER and DORIS_PASSWORD")
        self.assertSettingsError({"DORIS_HOST": "h", "DORIS_USER": "u"}, "DORIS_PASSWORD")

    def test_bad_scope(self):
        self.assertSettingsError({**BASE, "PROFILE_SCOPE": "everyone"}, "PROFILE_SCOPE")

    def test_bad_ports(self):
        self.assertSettingsError({**BASE, "DORIS_PORT": "abc"}, "DORIS_PORT must be an integer")
        self.assertSettingsError({**BASE, "DORIS_HTTP_PORT": "70000"}, "DORIS_HTTP_PORT out of range")
        self.assertSettingsError({**BASE, "MCP_PORT": "0"}, "MCP_PORT out of range")

    def test_secret_not_json_or_missing_keys(self):
        env = {**BASE, "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}
        for client in (FakeSecrets(SECRET_PW), _secret(user="mcp_svc", password=SECRET_PW), FakeSecrets(None)):
            self.assertSettingsError(env, "must be JSON with 'username' and 'password'", client)

    def test_secret_with_empty_values(self):
        env = {**BASE, "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}
        self.assertSettingsError(env, "empty or non-string", _secret(username="mcp_svc", password=""))
        self.assertSettingsError(env, "empty or non-string", _secret(username=7, password=SECRET_PW))

    def test_secret_read_failure_names_only_the_error_type(self):
        env = {**BASE, "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}
        client = FakeSecrets(error=TimeoutError(f"endpoint timeout, password={SECRET_PW}"))
        self.assertSettingsError(env, "cannot read secret doris-mcp/mcp_svc: TimeoutError", client)


if __name__ == "__main__":
    unittest.main(verbosity=2)
