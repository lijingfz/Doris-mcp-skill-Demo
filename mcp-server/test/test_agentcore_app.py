"""P-01: AgentCore HTTP contract - GET /ping, stateless streamable HTTP on /mcp, stderr logging, main()."""

import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastmcp import FastMCP  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import store.store as st  # noqa: E402
from agentcore_ext import app as app_mod  # noqa: E402
from agentcore_ext.settings import load_settings  # noqa: E402

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _rpc(client, method, params=None, id_=1):
    resp = client.post("/mcp", headers=MCP_HEADERS, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})
    if resp.headers["content-type"].startswith("text/event-stream"):
        data = [line[5:].strip() for line in resp.text.splitlines() if line.startswith("data:")]
        return resp, json.loads(data[-1])
    return resp, resp.json()


class _AppCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(st.clear_service_credentials)
        self.env = {
            "DORIS_HOST": "10.9.8.7", "DORIS_USER": "mcp_svc", "DORIS_PASSWORD": "svc-pw",
            "DORIS_MCP_WORKSPACE_DIR": str(Path(tmp.name) / "ws"), "DORIS_MCP_CONFIG_DIR": str(CONFIG_DIR),
        }


class TestHttpContract(_AppCase):
    def client(self):
        mcp = app_mod.build_server(load_settings(self.env))
        http = mcp.http_app(path=app_mod.MCP_PATH, stateless_http=True, middleware=app_mod.HTTP_MIDDLEWARE)
        return TestClient(http)

    def test_ping_is_healthy(self):
        with self.client() as client:
            resp = client.get("/ping")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "Healthy")
        self.assertIsInstance(resp.json()["time_of_last_update"], int)

    def test_initialize_and_list_tools_without_auth(self):
        with self.client() as client:
            resp, init = _rpc(client, "initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            })
            self.assertEqual(resp.status_code, 200)
            self.assertIn("tools", init["result"]["capabilities"])
            self.assertNotIn("mcp-session-id", {k.lower() for k in resp.headers})
            resp, listed = _rpc(client, "tools/list", id_=2)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(listed["result"]["tools"]), 12)

    def test_sse_responses_declare_utf8(self):
        # Without CharsetMiddleware the header is a bare text/event-stream and
        # clients decode Chinese result text as ISO-8859-1.
        with self.client() as client:
            resp, _ = _rpc(client, "tools/list")
        self.assertEqual(resp.headers["content-type"], "text/event-stream; charset=utf-8")


class TestMain(_AppCase):
    def test_runs_the_agentcore_contract(self):
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(app_mod, "configure_logging"), \
                patch.object(FastMCP, "run") as run:
            app_mod.main()
        kwargs = run.call_args.kwargs
        self.assertEqual(
            {k: kwargs[k] for k in ("transport", "host", "port", "path", "stateless_http")},
            {"transport": "streamable-http", "host": "0.0.0.0", "port": 8000, "path": "/mcp", "stateless_http": True},
        )
        self.assertIs(kwargs["middleware"], app_mod.HTTP_MIDDLEWARE)

    def test_bad_settings_exit_2_with_a_clear_message(self):
        env = {**self.env, "DORIS_PORT": "not-a-port"}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(app_mod, "configure_logging"), \
                patch.object(FastMCP, "run") as run, \
                self.assertLogs("doris_new_mcp.agentcore", "ERROR") as logs, \
                self.assertRaises(SystemExit) as exit_:
            app_mod.main()
        self.assertEqual(exit_.exception.code, 2)
        self.assertIn("DORIS_PORT must be an integer", logs.output[0])
        self.assertNotIn("svc-pw", "\n".join(logs.output))
        run.assert_not_called()


class TestConfigureLogging(unittest.TestCase):
    def setUp(self):
        self.loggers = [logging.getLogger(), logging.getLogger("doris_new_mcp.audit")]
        before = {id(lg): list(lg.handlers) for lg in self.loggers}
        level = logging.getLogger().level

        def restore():
            for lg in self.loggers:
                lg.handlers[:] = before[id(lg)]
            logging.getLogger().setLevel(level)

        self.addCleanup(restore)

    def test_root_and_audit_log_to_stderr_once(self):
        app_mod.configure_logging()
        app_mod.configure_logging()
        for lg in self.loggers:
            ours = [h for h in lg.handlers if getattr(h, "_agentcore_stderr", False)]
            self.assertEqual(len(ours), 1, lg.name)
            self.assertIs(ours[0].stream, sys.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
