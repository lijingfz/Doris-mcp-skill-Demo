"""P-10: a failed tool call carries its error text in the audit log; query_metric logs its filters.

The audit record is read back from the `doris_new_mcp.audit` logger, so params, mf_command and
error go through log_tool_call's mask_sensitive exactly as they do on AgentCore (CloudWatch).
The Doris pool and the semantic workspace are fakes: no connection is opened.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastmcp import Client  # noqa: E402

import store.store as st  # noqa: E402
from config.loader import AppConfig  # noqa: E402
from core.response import ErrorCode, error_response, success_response  # noqa: E402
from server import _audit_error, create_server  # noqa: E402
from store.watcher import MultiWorkspaceWatcher  # noqa: E402

SVC = ("mcp_svc", "svc-pw")
DORIS_ERROR = "(1105, \"errCode = 2, detailMessage = Unknown column 'nope' in 'v_paid_order'\")"
CHANNEL = "{{ Dimension('order_entity__channel') }}"


class TestAuditError(unittest.TestCase):
    def test_success_is_none(self):
        self.assertIsNone(_audit_error(success_response({"rows": []})))

    def test_failure_is_code_and_message(self):
        result = error_response(ErrorCode.INVALID_SQL, "Only read-only queries are allowed", {"sql": "DELETE"})
        self.assertEqual(_audit_error(result), "INVALID_SQL: Only read-only queries are allowed")

    def test_not_json_or_not_an_object_is_none(self):
        for result in ("", "not json", "[1, 2]", '"text"', "null", '{"data": 1}'):
            with self.subTest(result=result):
                self.assertIsNone(_audit_error(result))

    def test_missing_code_or_message(self):
        cases = {
            '{"success": false, "error": {"message": "boom"}}': "boom",
            '{"success": false, "error": {"code": "QUERY_TIMEOUT"}}': "QUERY_TIMEOUT",
            '{"success": false, "error": "boom"}': "boom",
            '{"success": false}': "unknown error",
        }
        for result, expected in cases.items():
            with self.subTest(result=result):
                self.assertEqual(_audit_error(result), expected)

    def test_truncated_to_300_chars(self):
        error = _audit_error(error_response(ErrorCode.CONNECTION_ERROR, "x" * 400))
        self.assertEqual(len(error), 300)
        self.assertEqual(error, ("CONNECTION_ERROR: " + "x" * 400)[:300])


class FakePool:
    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.sql = rows or [], error, []

    async def execute(self, sql, database=None, max_rows=None):
        self.sql.append(sql)
        if self.error:
            raise self.error
        return self.rows, list(self.rows[0]) if self.rows else []


class FakeCompiler:
    """resolve_* like the real compiler for `month`/`channel`; compile returns a fixed (sql, command, error)."""

    def __init__(self, sql="SELECT 1 AS gmv", error=""):
        self.sql, self.error, self.compiled = sql, error, []

    def resolve_group_by(self, metrics, names):
        return ["metric_time__month" if n == "month" else n for n in names]

    def resolve_where(self, metrics, where):
        return where.replace("channel", CHANNEL)

    def compile(self, metrics, group_by, where, order_by, limit, having):
        self.compiled.append(where)
        return (None if self.error else self.sql), "mf query", self.error


class _AuditCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(st.clear_service_credentials)
        root = Path(tmp.name)
        (root / "config").mkdir()
        self.server = create_server(config_dir=str(root / "config"), config=AppConfig(root / "config"),
                                    machine_ip="198.51.100.7", service_credentials=SVC,
                                    workspace_dir=str(root / "ws"))

    async def call(self, tool, args, pool, compiler=None):
        """Call a tool; return (result body, audit record, raw audit line)."""
        workspace = SimpleNamespace(enabled=True, is_ready=lambda: True, last_reload_error="", compiler=compiler)
        with patch("core.pool_manager.PoolManager.get_or_create_local_pool", AsyncMock(return_value=pool)), \
                patch.object(MultiWorkspaceWatcher, "ensure_fresh", return_value=workspace), \
                self.assertLogs("doris_new_mcp.audit", "INFO") as logs:
            async with Client(self.server) as client:
                result = await client.call_tool(tool, args, raise_on_error=False)
        (line,) = [r.getMessage() for r in logs.records]
        record = json.loads(line)
        self.assertEqual(record["tool"], tool)
        return json.loads(result.content[0].text), record, line


class TestExecuteQueryAudit(_AuditCase):
    async def test_failure_records_the_error_text(self):
        body, record, _ = await self.call("execute_query", {"sql": "SELECT nope FROM v_paid_order", "database": "ecom"},
                                          FakePool(error=RuntimeError(DORIS_ERROR)))
        self.assertEqual(body["error"]["code"], "CONNECTION_ERROR")
        self.assertFalse(record["success"])
        self.assertEqual(record["error"], f"CONNECTION_ERROR: {DORIS_ERROR}")
        self.assertEqual(record["params"], {"sql": "SELECT nope FROM v_paid_order", "database": "ecom"})

    async def test_rejected_sql_records_the_reason(self):
        pool = FakePool()
        body, record, _ = await self.call("execute_query", {"sql": "DELETE FROM v_paid_order"}, pool)
        self.assertEqual(body["error"]["code"], "INVALID_SQL")
        self.assertEqual(record["error"], f"INVALID_SQL: {body['error']['message']}")
        self.assertEqual(pool.sql, [])

    async def test_success_records_no_error(self):
        body, record, _ = await self.call("execute_query", {"sql": "SELECT 1 AS n"}, FakePool(rows=[{"n": 1}]))
        self.assertTrue(body["success"])
        self.assertTrue(record["success"])
        self.assertNotIn("error", record)

    async def test_sql_is_masked_and_cut_to_200_chars(self):
        sql = "SELECT * FROM t WHERE password = 'hunter2-pw' AND x IN (" + "1, " * 100 + "1)"
        _, record, line = await self.call("execute_query", {"sql": sql}, FakePool(rows=[{"n": 1}]))
        self.assertEqual(record["params"]["sql"], sql[:200].replace("hunter2-pw", "****"))
        self.assertNotIn("hunter2-pw", line)

    async def test_error_echoing_a_password_is_masked(self):
        # Doris echoes the offending SQL in its error; the audit error goes through mask_sensitive.
        error = RuntimeError("(1105, \"errCode = 2, detailMessage = Syntax error near password = 'hunter2-pw'\")")
        _, record, line = await self.call("execute_query", {"sql": "SELECT 1"}, FakePool(error=error))
        self.assertIn("near password = '****'", record["error"])
        self.assertNotIn("hunter2-pw", line)


class TestQueryMetricAudit(_AuditCase):
    FILTERED = {"workspace": "ecom", "metrics": ["gmv"], "group_by": ["month"], "where": "channel = 'APP'",
                "having": "gmv > 100", "order_by": ["-gmv"], "limit": 5}

    async def test_records_resolved_filters(self):
        compiler = FakeCompiler()
        body, record, _ = await self.call("query_metric", self.FILTERED, FakePool(rows=[{"gmv": 1}]), compiler)
        self.assertTrue(body["success"])
        self.assertEqual(compiler.compiled, [f"{CHANNEL} = 'APP'"])
        self.assertEqual(record["params"], {
            "metrics": "['gmv']", "group_by": "['metric_time__month']", "where": f"{CHANNEL} = 'APP'",
            "having": "gmv > 100", "order_by": "['-gmv']", "limit": "5",
        })
        self.assertEqual(record["mf_command"],
                         f"mf query --metrics gmv --group-by metric_time__month --where \"{CHANNEL} = 'APP'\" "
                         "--order-by -gmv --limit 5 --having \"gmv > 100\"")
        self.assertTrue(record["success"])
        self.assertNotIn("error", record)

    async def test_unset_filters_are_logged_empty_and_left_out_of_mf_command(self):
        # One rule: every filter key is always in params (a stable schema for Logs Insights);
        # mf_command only carries the options that were set.
        _, record, _ = await self.call("query_metric", {"workspace": "ecom", "metrics": ["gmv", "aov"]},
                                       FakePool(rows=[{"gmv": 1}]), FakeCompiler())
        self.assertEqual(record["params"], {"metrics": "['gmv', 'aov']", "group_by": "[]", "where": "",
                                            "having": "", "order_by": "[]", "limit": "0"})
        self.assertEqual(record["mf_command"], "mf query --metrics gmv,aov")

    async def test_double_quotes_in_where_are_escaped_in_mf_command(self):
        args = {"workspace": "ecom", "metrics": ["gmv"], "where": 'region = "east"'}
        _, record, _ = await self.call("query_metric", args, FakePool(rows=[{"gmv": 1}]), FakeCompiler())
        self.assertEqual(record["mf_command"], 'mf query --metrics gmv --where "region = \\"east\\""')

    async def test_compile_failure_records_the_error_text(self):
        compiler = FakeCompiler(error="Unknown dimension 'nope'")
        pool = FakePool()
        body, record, _ = await self.call("query_metric", self.FILTERED, pool, compiler)
        self.assertEqual(body["error"]["code"], "INTERNAL_ERROR")
        self.assertFalse(record["success"])
        self.assertEqual(record["error"], "INTERNAL_ERROR: MetricFlow compile error: Unknown dimension 'nope'")
        self.assertEqual(record["params"]["where"], f"{CHANNEL} = 'APP'")
        self.assertEqual(pool.sql, [])

    async def test_doris_failure_records_the_error_text(self):
        _, record, _ = await self.call("query_metric", self.FILTERED, FakePool(error=RuntimeError(DORIS_ERROR)),
                                       FakeCompiler())
        self.assertFalse(record["success"])
        self.assertEqual(record["error"], f"CONNECTION_ERROR: {DORIS_ERROR}")

    async def test_success_is_parsed_not_substring_matched(self):
        # A compact JSON body has no '"success": true' substring; success comes from the parsed result.
        compact = json.dumps({"success": True, "data": {"columns": ["gmv"], "rows": [{"gmv": 1}]}},
                             separators=(",", ":"))
        with patch("tools.semantic.query_metric", AsyncMock(return_value=compact)):
            _, record, _ = await self.call("query_metric", self.FILTERED, FakePool(), FakeCompiler())
        self.assertTrue(record["success"])
        self.assertNotIn("error", record)

    async def test_password_literal_in_where_is_masked(self):
        args = {"workspace": "ecom", "metrics": ["gmv"], "where": "user__password = 'hunter2-pw'"}
        _, record, line = await self.call("query_metric", args, FakePool(rows=[{"gmv": 1}]), FakeCompiler())
        self.assertEqual(record["params"]["where"], "user__password = '****'")
        self.assertIn("--where \"user__password = '****'\"", record["mf_command"])
        self.assertNotIn("hunter2-pw", line)

    async def test_double_quoted_password_in_where_is_masked(self):
        # mf_command escapes the double quotes; masked only afterwards, the value would stay in clear.
        args = {"workspace": "ecom", "metrics": ["gmv"], "where": 'user__password = "hunter2-pw"'}
        _, record, line = await self.call("query_metric", args, FakePool(rows=[{"gmv": 1}]), FakeCompiler())
        self.assertEqual(record["params"]["where"], 'user__password = "****"')
        self.assertIn('--where "user__password = ', record["mf_command"])
        self.assertIn("****", record["mf_command"])
        self.assertNotIn("hunter2-pw", line)

    async def test_double_quoted_token_in_having_is_masked(self):
        args = {"workspace": "ecom", "metrics": ["gmv"], "having": 'api_token = "fake-tok-123"'}
        _, record, line = await self.call("query_metric", args, FakePool(rows=[{"gmv": 1}]), FakeCompiler())
        self.assertEqual(record["params"]["having"], 'api_token = "****"')
        self.assertIn('--having "api_token = ', record["mf_command"])
        self.assertIn("****", record["mf_command"])
        self.assertNotIn("fake-tok-123", line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
