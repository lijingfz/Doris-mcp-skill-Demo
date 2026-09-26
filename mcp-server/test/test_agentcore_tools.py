"""P-01/P-06: build_server() exposes upstream's 10 tools + the 2 profile tools with Quick-safe schemas."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastmcp import Client  # noqa: E402

import store.store as st  # noqa: E402
from agentcore_ext.app import build_server  # noqa: E402
from agentcore_ext.settings import load_settings  # noqa: E402
from config.loader import AppConfig  # noqa: E402

UPSTREAM_TOOLS = {
    "get_query_guide", "list_databases", "list_tables", "describe_table", "execute_query",
    "check_service_health", "list_metrics", "list_dimensions_for_metric", "query_metric",
    "reload_semantic_layer",
}
PROFILE_TOOLS = {"list_recent_queries", "get_query_profile"}
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class _BuildCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(st.clear_service_credentials)
        self.workspace = Path(tmp.name) / "ws"
        self.settings = load_settings({
            "DORIS_HOST": "10.9.8.7", "DORIS_USER": "mcp_svc", "DORIS_PASSWORD": "svc-pw",
            "DORIS_MCP_WORKSPACE_DIR": str(self.workspace), "DORIS_MCP_CONFIG_DIR": str(CONFIG_DIR),
        })


class TestToolSurface(_BuildCase):
    async def test_exactly_twelve_tools(self):
        mcp = build_server(self.settings)
        async with Client(mcp) as client:
            names = {t.name for t in await client.list_tools()}
        self.assertEqual(names, UPSTREAM_TOOLS | PROFILE_TOOLS)

    async def test_input_schemas_are_valid_draft7(self):
        # Quick rejects connectors whose tool inputSchema is not valid JSON Schema draft 7.
        mcp = build_server(self.settings)
        async with Client(mcp) as client:
            tools = await client.list_tools()
        for tool in tools:
            with self.subTest(tool=tool.name):
                jsonschema.Draft7Validator.check_schema(tool.inputSchema)
                self.assertEqual(tool.inputSchema.get("type"), "object")
                self.assertTrue(tool.description)

    async def test_no_mcp_auth_and_service_credentials(self):
        mcp = build_server(self.settings)
        self.assertIsNone(mcp.auth)
        self.assertEqual(st.get_effective_credentials(), ("mcp_svc", "svc-pw"))

    async def test_workspace_goes_to_settings_dir(self):
        build_server(self.settings)
        self.assertTrue((self.workspace / "workspaces").is_dir())
        self.assertTrue((self.workspace / "logs").is_dir())

    async def test_invalid_query_id_is_rejected_without_network(self):
        mcp = build_server(self.settings)
        async with Client(mcp) as client:
            result = await client.call_tool("get_query_profile", {"query_id": "../../api/x"}, raise_on_error=False)
        self.assertEqual(json.loads(result.content[0].text)["error"]["code"], "INVALID_PARAMS")


class TestRuntimeConfig(unittest.TestCase):
    def test_config_file_limits(self):
        cc = AppConfig(CONFIG_DIR).cluster
        self.assertEqual((cc.query_timeout, cc.max_rows), (50, 2000))
        self.assertEqual((cc.pool_min_size, cc.pool_max_size, cc.fe_http_port), (0, 5, 8030))


if __name__ == "__main__":
    unittest.main(verbosity=2)
