"""scripts/audit_check.py: count doris_new_mcp.audit records in filter-log-events output (P3 / T3.3, R-32)."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_check  # noqa: E402

SECRET_SQL = "SELECT phone FROM ecom.dim_user WHERE user_id = 42"


def audit_line(tool: str, success: bool = True, **extra) -> str:
    record = {"timestamp": "2026-09-27T08:00:00+0000", "tool": tool, "client_id": "client-abc",
              "params": {"sql": SECRET_SQL}, "success": success, "duration_ms": 12.5, "query_path": "direct", **extra}
    return f"[2026-09-27 08:00:00,123] INFO doris_new_mcp.audit: {json.dumps(record)}\n"


def events(*messages: str) -> str:
    return json.dumps({"events": [{"logStreamName": "2026/09/27/[runtime-logs]s1", "timestamp": 1, "message": m}
                                  for m in messages], "searchedLogStreams": []})


class _Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.calls = Path(tmp.name) / "calls.json"
        self.calls.write_text(json.dumps([{"tool": "execute_query", "params": {"sql": "SELECT 1"}},
                                          {"tool": "list_metrics", "params": {"workspace": "ecom"}}]))

    def run_check(self, stdin: str, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        rc = audit_check.main(list(argv), stdin=io.StringIO(stdin), out=out)
        return rc, out.getvalue()


class TestAuditCheck(_Case):
    def test_every_expected_call_audited(self):
        rc, out = self.run_check(events(audit_line("execute_query"), audit_line("list_metrics"),
                                        audit_line("execute_query"), audit_line("list_metrics")),
                                 "--calls", str(self.calls), "--repeat", "2")
        self.assertEqual(rc, 0, out)
        self.assertIn("audit: 4 records (4 ok, 0 failed), 0 unreadable", out)
        self.assertRegex(out, r"(?m)^  execute_query +2 ok +0 failed  \(expected >= 2\)$")
        self.assertIn("[PASS] every expected call audited: 2/2 tools", out)

    def test_a_missing_call_fails(self):
        rc, out = self.run_check(events(audit_line("execute_query"), audit_line("list_metrics"),
                                        audit_line("list_metrics")),
                                 "--calls", str(self.calls), "--repeat", "2")
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] every expected call audited: 1/2 tools (short: execute_query 1/2)", out)

    def test_failed_calls_count_as_audited(self):
        # R-32 is about the record existing; the smoke run itself checks success.
        rc, out = self.run_check(events(audit_line("execute_query", False, error="(1105, 'host 10.1.2.3')"),
                                        audit_line("list_metrics")),
                                 "--calls", str(self.calls))
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"(?m)^  execute_query +0 ok +1 failed")

    def test_never_prints_params_errors_or_client_ids(self):
        _, out = self.run_check(events(audit_line("execute_query", False, error="(1105, 'host 10.1.2.3')")))
        for leaked in (SECRET_SQL, "phone", "10.1.2.3", "client-abc", "1105"):
            self.assertNotIn(leaked, out)

    def test_other_log_lines_are_ignored(self):
        rc, out = self.run_check(events("[2026-09-27 08:00:00,1] INFO uvicorn.access: 169.254.0.1 GET /ping 200\n",
                                        audit_line("list_metrics")))
        self.assertEqual(rc, 0, out)
        self.assertIn("audit: 1 records", out)
        self.assertNotIn("169.254.0.1", out)

    def test_an_unreadable_record_fails(self):
        rc, out = self.run_check(events("[x] INFO doris_new_mcp.audit: {\"tool\": \"execute_q", audit_line("list_metrics")))
        self.assertEqual(rc, 1)
        self.assertIn("1 unreadable", out)
        self.assertIn("[FAIL] unreadable audit records: 1", out)

    def test_no_expectation_just_counts(self):
        rc, out = self.run_check(events(audit_line("get_query_guide")))
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"(?m)^  get_query_guide +1 ok +0 failed$")

    def test_no_records_with_an_expectation_fails(self):
        rc, out = self.run_check(events(), "--calls", str(self.calls))
        self.assertEqual(rc, 1)
        self.assertIn("audit: 0 records", out)

    def test_input_that_is_not_filter_log_events_json(self):
        for stdin in ("", "not json", "[]"):
            with self.subTest(stdin=stdin):
                rc, out = self.run_check(stdin)
                self.assertEqual(rc, 2)
                self.assertIn("FAIL: input is not", out)


class TestRealAuditLine(_Case):
    def test_reads_what_the_runtime_writes_to_stderr(self):
        # The server's own logging setup (agentcore_ext.app.configure_logging) and audit writer, in a
        # child process so this process's loggers stay untouched.
        code = """if True:
            import sys, tempfile
            from core.audit import init_audit_log, log_tool_call
            from agentcore_ext.app import configure_logging
            init_audit_log(tempfile.mkdtemp() + "/audit.log")
            configure_logging()
            log_tool_call("execute_query", params={"sql": "SELECT 1"}, success=True, duration_ms=3)
            log_tool_call("list_metrics", params={"workspace": "ecom"}, success=False, error="boom")
        """
        src = Path(__file__).resolve().parents[2] / "mcp-server" / "src"
        proc = subprocess.run([sys.executable, "-c", code], cwd=src, env={**os.environ, "PYTHONPATH": str(src)},
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        rc, out = self.run_check(events(*proc.stderr.splitlines(keepends=True)), "--calls", str(self.calls))
        self.assertEqual(rc, 0, out)
        self.assertIn("audit: 2 records (1 ok, 1 failed), 0 unreadable", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
