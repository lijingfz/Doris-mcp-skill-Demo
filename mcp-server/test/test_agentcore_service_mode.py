"""P-04: create_server(service_credentials=, workspace_dir=) for AgentCore.

Service mode: no MCP-level auth (Runtime IAM / Gateway JWT guard the edge),
every tool uses one service-account pool, and the store layer falls back to
the same credentials. Without service credentials upstream behavior is kept.
"""

import contextvars
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastmcp import Client  # noqa: E402

import store.store as st  # noqa: E402
from config.loader import AppConfig  # noqa: E402
from server import create_server  # noqa: E402

SVC = ("mcp_svc", "svc-pw")


class _ServerCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config_dir = self.root / "config"
        self.config_dir.mkdir()
        self.addCleanup(st.clear_service_credentials)

    def build(self, **kwargs):
        return create_server(config_dir=str(self.config_dir), config=AppConfig(self.config_dir), **kwargs)

    async def call_list_databases(self, server):
        async with Client(server) as client:
            result = await client.call_tool("list_databases", {}, raise_on_error=False)
        return json.loads(result.content[0].text)


class TestServiceMode(_ServerCase):
    async def test_service_mode_disables_mcp_auth(self):
        server = self.build(service_credentials=SVC, workspace_dir=str(self.root / "ws"))
        self.assertIsNone(server.auth)

    async def test_service_mode_installs_store_fallback(self):
        self.build(service_credentials=SVC, workspace_dir=str(self.root / "ws"))
        self.assertEqual(contextvars.Context().run(st.get_effective_credentials), SVC)

    async def test_tools_use_the_service_account_pool(self):
        server = self.build(service_credentials=SVC, workspace_dir=str(self.root / "ws"))
        acquire = AsyncMock(side_effect=RuntimeError("doris unreachable"))
        with patch("core.pool_manager.PoolManager.get_or_create_local_pool", acquire):
            body = await self.call_list_databases(server)
        acquire.assert_awaited_once()
        self.assertEqual(acquire.await_args.args[:2], SVC)
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "CONNECTION_ERROR")

    async def test_service_password_not_in_error_payload(self):
        server = self.build(service_credentials=SVC, workspace_dir=str(self.root / "ws"))
        acquire = AsyncMock(side_effect=RuntimeError("doris unreachable"))
        with patch("core.pool_manager.PoolManager.get_or_create_local_pool", acquire):
            body = await self.call_list_databases(server)
        self.assertNotIn(SVC[1], json.dumps(body))


class TestUpstreamModeUnchanged(_ServerCase):
    async def test_default_mode_keeps_credential_verifier(self):
        server = self.build(workspace_dir=str(self.root / "ws"))
        self.assertIsNotNone(server.auth)

    async def test_default_mode_clears_stale_service_credentials(self):
        st.set_service_credentials(*SVC)
        self.build(workspace_dir=str(self.root / "ws"))
        self.assertIsNone(contextvars.Context().run(st.get_effective_credentials))

    async def test_default_mode_without_token_never_opens_a_pool(self):
        server = self.build(workspace_dir=str(self.root / "ws"))
        acquire = AsyncMock()
        with patch("core.pool_manager.PoolManager.get_or_create_local_pool", acquire):
            body = await self.call_list_databases(server)
        acquire.assert_not_awaited()
        self.assertFalse(body["success"])


class TestWorkspaceDir(_ServerCase):
    async def test_parameter_wins(self):
        self.build(workspace_dir=str(self.root / "ws"))
        self.assertTrue((self.root / "ws" / "workspaces").is_dir())
        self.assertTrue((self.root / "ws" / "logs").is_dir())
        self.assertFalse((self.root / "workspace").exists())

    async def test_env_var_used_when_no_parameter(self):
        with patch.dict(os.environ, {"DORIS_MCP_WORKSPACE_DIR": str(self.root / "env-ws")}):
            self.build()
        self.assertTrue((self.root / "env-ws" / "workspaces").is_dir())
        self.assertFalse((self.root / "workspace").exists())

    async def test_upstream_default_next_to_config_dir(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DORIS_MCP_WORKSPACE_DIR", None)
            self.build()
        self.assertTrue((self.root / "workspace" / "workspaces").is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
