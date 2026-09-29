"""scripts/mcp_smoke.py: --sigv4, `time` and `conns` (P3 / T3.3, T3.4) against an in-process fake server."""

import asyncio
import contextlib
import io
import json
import logging
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastmcp import Client, FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcp_smoke  # noqa: E402

SHIPPED_CALLS = Path(__file__).resolve().parents[1] / "smoke_calls.json"
GW_HOST = "gw-0123.gateway.example.test"
GW_URL = f"https://{GW_HOST}/mcp"
RUNTIME_HOST = "runtime-0123.example.test"
RUNTIME_URL = f"https://{RUNTIME_HOST}/runtimes/rt-0123/invocations?qualifier=DEFAULT"
PROXY = f"uvx mcp-proxy-for-aws@latest {RUNTIME_URL} --service bedrock-agentcore --region us-east-1"
OK = json.dumps({"success": True, "data": {}})
PROCESSLIST = [
    {"Id": 11, "User": "mcp_svc", "Host": "172.31.5.6:40001", "Command": "Query", "Time": "0",
     "Info": "SHOW PROCESSLIST"},
    {"Id": 12, "User": "mcp_svc", "Host": "172.31.7.8:40002", "Command": "Sleep", "Time": "42", "Info": ""},
    {"Id": 13, "User": "mcp_svc", "Host": "172.31.7.8:40003", "Command": "Sleep", "Time": 7, "Info": None},
]


def fake_server(state: SimpleNamespace) -> FastMCP:
    mcp = FastMCP("fake")

    @mcp.tool
    async def ok_tool() -> str:
        return OK

    @mcp.tool(name="doris___ok_tool")
    async def prefixed_ok_tool() -> str:
        return OK

    @mcp.tool
    async def slow(ms: int = 0) -> str:
        state.active += 1
        state.peak = max(state.peak, state.active)
        await asyncio.sleep(ms / 1000)
        state.active -= 1
        return OK

    @mcp.tool
    async def fails() -> str:
        return json.dumps({"success": False, "error": {"code": "QUERY_TIMEOUT", "message": "host 10.1.2.3"}})

    @mcp.tool
    async def boom() -> str:
        raise RuntimeError("detail naming 10.1.2.3")

    @mcp.tool
    async def execute_query(sql: str) -> str:
        state.sql.append(sql)
        if state.processlist is None:
            return json.dumps({"success": False, "error": {"code": "CONNECTION_ERROR", "message": "10.1.2.3"}})
        return json.dumps({"success": True, "data": {"columns": list(PROCESSLIST[0]), "rows": state.processlist}})

    return mcp


class _SmokeCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = SimpleNamespace(active=0, peak=0, sql=[], processlist=list(PROCESSLIST), clients=0)
        sdk_logger = logging.getLogger("mcp")  # main() installs a redacting handler on it
        self.enterContext(mock.patch.object(sdk_logger, "handlers", []))
        self.enterContext(mock.patch.object(sdk_logger, "propagate", True))
        self.server = fake_server(self.state)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def factory(self, _args) -> Client:
        self.state.clients += 1
        return Client(self.server)

    def calls_file(self, calls) -> str:
        path = self.tmp / "calls.json"
        path.write_text(json.dumps(calls))
        return str(path)

    async def run_main(self, *argv: str, target: tuple[str, str] = ("--url", "http://fake/mcp")) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = await mcp_smoke.main([*target, *argv], client_factory=self.factory)
        return rc, out.getvalue()


class TestTime(_SmokeCase):
    async def test_all_ok_within_budget(self):
        rc, out = await self.run_main("time", "--calls", self.calls_file(
            [{"tool": "ok_tool", "params": {}}, {"tool": "slow", "params": {"ms": 5}}]))
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"(?m)^  ok +\d+ ms  ok_tool$")
        self.assertRegex(out, r"(?m)^  ok +\d+ ms  slow$")
        self.assertRegex(out, r"time: 2 calls \(1 parallel\), 0 errors, 0 over 60000 ms; "
                              r"p50 \d+ ms, p95 \d+ ms, max \d+ ms")

    async def test_a_tool_error_fails_the_run_with_its_code_only(self):
        rc, out = await self.run_main("time", "--calls", self.calls_file(
            [{"tool": "ok_tool", "params": {}}, {"tool": "fails", "params": {}}]))
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"(?m)^  ERR +\d+ ms  fails  \(QUERY_TIMEOUT\)$")
        self.assertIn("1 errors", out)
        self.assertNotIn("10.1.2.3", out)

    async def test_a_raised_tool_error_is_counted_without_its_message(self):
        with self.assertLogs("fastmcp", "ERROR"):  # the fake server logs the traceback; keep it off the console
            rc, out = await self.run_main("time", "--calls", self.calls_file([{"tool": "boom", "params": {}}]))
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"(?m)^  ERR +\d+ ms  boom  \(tool error\)$")
        self.assertNotIn("10.1.2.3", out)

    async def test_a_transport_failure_is_counted_and_the_run_continues(self):
        calls = self.calls_file([{"tool": "ok_tool", "params": {}}, {"tool": "ok_tool", "params": {}}])
        real = self.factory
        seen = []

        def flaky(args):
            seen.append(1)
            if len(seen) == 1:
                raise ConnectionError("connect to 10.1.2.3 refused")
            return real(args)

        self.factory = flaky
        rc, out = await self.run_main("time", "--calls", calls, "--fresh")
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"(?m)^  ERR +\d+ ms  ok_tool  \(ConnectionError\)$")
        self.assertRegex(out, r"(?m)^  ok +\d+ ms  ok_tool$")
        self.assertNotIn("10.1.2.3", out)

    async def test_over_budget_fails(self):
        rc, out = await self.run_main("time", "--budget-ms", "1", "--calls", self.calls_file(
            [{"tool": "slow", "params": {"ms": 30}}]))
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"(?m)^  SLOW +\d+ ms  slow$")
        self.assertIn("1 over 1 ms", out)

    async def test_parallel_runs_calls_concurrently(self):
        rc, out = await self.run_main("time", "--parallel", "5", "--calls", self.calls_file(
            [{"tool": "slow", "params": {"ms": 100}}] * 5))
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.state.peak, 5)
        self.assertIn("5 calls (5 parallel)", out)

    async def test_parallel_is_capped(self):
        await self.run_main("time", "--parallel", "2", "--calls", self.calls_file(
            [{"tool": "slow", "params": {"ms": 50}}] * 6))
        self.assertEqual(self.state.peak, 2)

    async def test_shared_session_by_default(self):
        await self.run_main("time", "--repeat", "3", "--calls", self.calls_file([{"tool": "ok_tool", "params": {}}]))
        self.assertEqual(self.state.clients, 1)

    async def test_fresh_opens_one_session_per_call(self):
        # Through the Gateway every tool call is a new Runtime session; --fresh times that path directly.
        rc, out = await self.run_main("time", "--fresh", "--repeat", "3", "--calls",
                                      self.calls_file([{"tool": "ok_tool", "params": {}}]))
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.state.clients, 3)
        self.assertIn("3 calls (1 parallel, fresh session each)", out)

    async def test_prefix_is_prepended(self):
        rc, out = await self.run_main("time", "--prefix", "doris___", "--calls",
                                      self.calls_file([{"tool": "ok_tool", "params": {}}]))
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"(?m)^  ok +\d+ ms  doris___ok_tool$")

    async def test_bad_calls_file_is_a_usage_error(self):
        for calls in ({"tool": "ok_tool"}, [{"params": {}}], [{"tool": "ok_tool", "params": []}]):
            with self.subTest(calls=calls):
                rc, out = await self.run_main("time", "--calls", self.calls_file(calls))
                self.assertEqual(rc, 2)
                self.assertEqual(self.state.clients, 0)

    async def test_bad_parallel_or_repeat_is_a_usage_error(self):
        for option in ("--parallel", "--repeat"):
            with self.subTest(option=option), self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    await self.run_main("time", option, "0")


class TestShippedCalls(unittest.TestCase):
    def test_one_read_only_call_per_server_tool(self):
        calls = mcp_smoke.load_calls(SHIPPED_CALLS)
        self.assertEqual({c["tool"] for c in calls}, {
            "get_query_guide", "list_databases", "list_tables", "describe_table", "execute_query",
            "check_service_health", "list_metrics", "list_dimensions_for_metric", "query_metric",
            "reload_semantic_layer", "list_recent_queries", "get_query_profile"})
        self.assertEqual(len(calls), 12)
        sql = [c["params"]["sql"] for c in calls if c["tool"] == "execute_query"]
        self.assertEqual(len(sql), 1)
        self.assertRegex(sql[0], r"^SELECT ")


class TestConns(_SmokeCase):
    async def test_counts_only_never_hosts_or_statements(self):
        rc, out = await self.run_main("conns")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.state.sql, ["SHOW PROCESSLIST"])
        self.assertIn("connections: 3 (Query 1, Sleep 2) from 2 distinct hosts; users mcp_svc; max idle 42 s", out)
        self.assertIsNone(re.search(r"\d+\.\d+\.\d+\.\d+", out), out)
        self.assertNotIn("SHOW PROCESSLIST", out)

    async def test_expected_host_prefix(self):
        rc, out = await self.run_main("conns", "--expect-host-prefix", "172.31.")
        self.assertEqual(rc, 0, out)
        self.assertIn("[PASS] host prefix 172.31.: 3/3 connections", out)

    async def test_a_connection_from_elsewhere_fails_the_prefix_check(self):
        self.state.processlist.append({"Id": 14, "User": "mcp_svc", "Host": "203.0.113.9:5000",
                                       "Command": "Sleep", "Time": "3", "Info": ""})
        rc, out = await self.run_main("conns", "--expect-host-prefix", "172.31.")
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] host prefix 172.31.: 3/4 connections", out)
        self.assertNotIn("203.0.113.9", out)

    async def test_max_idle(self):
        rc, out = await self.run_main("conns", "--max-idle", "40")
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] idle connections <= 40 s: 1 over", out)
        rc, out = await self.run_main("conns", "--max-idle", "600")
        self.assertEqual(rc, 0, out)
        self.assertIn("[PASS] idle connections <= 600 s: 0 over", out)

    async def test_query_error_fails_with_its_code_only(self):
        self.state.processlist = None
        rc, out = await self.run_main("conns", "--prefix", "")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: SHOW PROCESSLIST: CONNECTION_ERROR", out)
        self.assertNotIn("10.1.2.3", out)


class TestErrorsAreMasked(_SmokeCase):
    async def test_a_connection_error_is_one_masked_line(self):
        def refused(_args):
            raise ConnectionError("POST http://fake/mcp failed (198.51.100.7)")

        self.factory = refused
        rc, out = await self.run_main("list")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: ConnectionError: POST *** failed (<ip>)\n", out)
        self.assertNotIn("fake/mcp", out)
        self.assertRegex(out, r"(?m)^total \d+ ms$")

    async def test_the_bearer_token_is_masked(self):
        token = "tok-0123456789abcdef"

        def rejected(_args):
            raise RuntimeError(f"401 for Bearer {token}")

        self.factory = rejected
        with mock.patch.dict(os.environ, {"GW_TOKEN": token}):
            rc, out = await self.run_main("--bearer-env", "GW_TOKEN", "list")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: RuntimeError: 401 for Bearer ***\n", out)

    async def test_sdk_log_lines_are_masked(self):
        real = self.factory

        def logs_the_url(args):
            logging.getLogger("mcp.client.streamable_http").warning("Session termination failed: POST %s", args.url)
            return real(args)

        self.factory = logs_the_url
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc, _ = await self.run_main("list")
        self.assertEqual(rc, 0)
        self.assertIn("Session termination failed: POST ***", err.getvalue())
        self.assertNotIn("fake/mcp", err.getvalue())

    async def test_a_dns_error_naming_only_the_host_is_masked(self):
        def unresolved(_args):
            raise ConnectionError(f"Failed to resolve '{GW_HOST}' ([Errno -2] Name or service not known)")

        self.factory = unresolved
        rc, out = await self.run_main("list", target=("--url", GW_URL))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: ConnectionError: Failed to resolve '***' ([Errno -2] Name or service not known)\n", out)
        self.assertNotIn("gw-0123", out)

    async def test_the_url_in_a_stdio_command_is_masked(self):
        def refused(_args):
            raise RuntimeError(f"POST {RUNTIME_URL} failed; cannot resolve {RUNTIME_HOST}")

        self.factory = refused
        rc, out = await self.run_main("list", target=("--stdio", PROXY))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: RuntimeError: POST *** failed; cannot resolve ***\n", out)
        self.assertNotIn("runtime-0123", out)

    async def test_sdk_log_lines_are_masked_in_stdio_mode(self):
        real = self.factory

        def logs_the_url(args):
            logging.getLogger("mcp.client.stdio").warning("Session termination failed: POST %s (%s)",
                                                          RUNTIME_URL, RUNTIME_HOST)
            return real(args)

        self.factory = logs_the_url
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc, _ = await self.run_main("list", target=("--stdio", PROXY))
        self.assertEqual(rc, 0)
        self.assertIn("WARNING mcp.client.stdio: Session termination failed: POST *** (***)\n", err.getvalue())
        self.assertNotIn("runtime-0123", err.getvalue())


class TestHiddenValues(unittest.TestCase):
    def hidden(self, *argv: str) -> list[str]:
        return mcp_smoke.hidden_values(mcp_smoke.parse_args([*argv, "list"]))

    def test_the_url_and_its_host(self):
        self.assertEqual(self.hidden("--url", GW_URL), [GW_URL, GW_HOST])

    def test_the_host_name_without_port_or_user(self):
        # A DNS error names the bare host: "Failed to resolve 'gw-0123...' ([Errno -2] ...)".
        url = f"https://svc@{GW_HOST}:8443/mcp"
        self.assertEqual(self.hidden("--url", url), [url, GW_HOST])

    def test_the_url_in_a_stdio_command_and_its_host(self):
        self.assertEqual(self.hidden("--stdio", PROXY), [RUNTIME_URL, RUNTIME_HOST])

    def test_a_stdio_command_without_a_url_hides_nothing(self):
        self.assertEqual(self.hidden("--stdio", "python -m doris_mcp_server --transport stdio"), [])

    def test_the_bearer_token(self):
        with mock.patch.dict(os.environ, {"GW_TOKEN": "tok-0123456789abcdef"}):
            self.assertEqual(self.hidden("--url", GW_URL, "--bearer-env", "GW_TOKEN"),
                             [GW_URL, GW_HOST, "tok-0123456789abcdef"])
        with mock.patch.dict(os.environ, {"GW_TOKEN": ""}):
            self.assertEqual(self.hidden("--url", GW_URL, "--bearer-env", "GW_TOKEN"), [GW_URL, GW_HOST])


class TestSigV4Option(unittest.TestCase):
    def _parse_error(self, *argv: str) -> None:
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            mcp_smoke.parse_args(list(argv))
        self.assertEqual(cm.exception.code, 2)

    def test_sigv4_needs_url(self):
        self._parse_error("--stdio", "server", "--sigv4", "list")

    def test_sigv4_excludes_a_bearer_token(self):
        self._parse_error("--url", "https://x/mcp", "--sigv4", "--bearer-env", "GW_TOKEN", "list")

    def test_sigv4_client_gets_url_region_and_timeout(self):
        args = mcp_smoke.parse_args(["--url", "https://x/mcp", "--sigv4", "--region", "us-east-1",
                                     "--timeout", "30", "list"])
        import agentcore_client
        with mock.patch.object(agentcore_client, "sigv4_client", return_value="client") as factory:
            self.assertEqual(mcp_smoke.build_client(args), "client")
        factory.assert_called_once_with("https://x/mcp", "us-east-1", timeout=30.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
