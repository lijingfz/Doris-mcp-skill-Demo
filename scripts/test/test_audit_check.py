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


class TestFailures(_Case):
    """--failures: each failed call's time, tool and error (IPv4-masked, cut), plus query_metric's filters."""

    SUMMARY = ("audit: 2 records (1 ok, 1 failed), 0 unreadable\n"
               "  execute_query                  0 ok   1 failed  (expected >= 1)\n"
               "  list_metrics                   1 ok   0 failed  (expected >= 1)\n"
               "  [PASS] every expected call audited: 2/2 tools\n")

    def two_calls(self) -> str:
        return events(audit_line("execute_query", False, error="CONNECTION_ERROR: 198.51.100.7"),
                      audit_line("list_metrics"))

    def test_without_the_flag_the_output_is_unchanged(self):
        self.assertEqual(self.run_check(self.two_calls(), "--calls", str(self.calls)), (0, self.SUMMARY))

    def test_the_section_follows_the_unchanged_summary(self):
        rc, out = self.run_check(self.two_calls(), "--calls", str(self.calls), "--failures")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out, self.SUMMARY + "failures: 1\n"
                              "  2026-09-27T08:00:00+0000  execute_query  CONNECTION_ERROR: <ip>\n")

    def test_the_error_text_is_shown_ip_masked(self):
        _, out = self.run_check(events(audit_line(
            "execute_query", False, error="CONNECTION_ERROR: (2003, \"Can't connect to MySQL server on "
                                          "'198.51.100.7' ([Errno 111] Connection refused)\")")), "--failures")
        self.assertEqual(out.splitlines()[-2:], [
            "failures: 1",
            "  2026-09-27T08:00:00+0000  execute_query  CONNECTION_ERROR: (2003, \"Can't connect to MySQL server "
            "on '<ip>' ([Errno 111] Connection refused)\")"])
        self.assertNotIn("198.51.100.7", out)

    def test_a_failure_without_an_error_says_not_recorded(self):
        # Records written before the server recorded the error text have no "error" key.
        _, out = self.run_check(events(audit_line("describe_table", False)), "--failures")
        self.assertEqual(out.splitlines()[-1], "  2026-09-27T08:00:00+0000  describe_table  (not recorded)")

    def test_the_error_is_cut_at_200_chars(self):
        error = "QUERY_ERROR: " + "x" * 287  # 300 chars, the server's cap
        _, out = self.run_check(events(audit_line("execute_query", False, error=error)), "--failures")
        self.assertEqual(out.splitlines()[-1], "  2026-09-27T08:00:00+0000  execute_query  " + error[:200])

    def test_an_address_across_the_cut_is_masked_not_split(self):
        head = "CONNECTION_ERROR: " + "y" * 172 + " at "  # the address starts at char 194
        _, out = self.run_check(events(audit_line("execute_query", False, error=head + "203.0.113.45:9030 refused")),
                                "--failures")
        self.assertEqual(out.splitlines()[-1],
                         "  2026-09-27T08:00:00+0000  execute_query  " + (head + "<ip>:9030 refused")[:200])
        self.assertNotIn("203.0", out)

    def test_a_multi_line_error_stays_on_one_line(self):
        _, out = self.run_check(events(audit_line("query_metric", False, params={"where": "a = 1\n  AND b = 2"},
                                                  error="QUERY_ERROR: first line\n  second line")), "--failures")
        self.assertEqual(out.splitlines()[-2:], ["  2026-09-27T08:00:00+0000  query_metric  QUERY_ERROR: first line "
                                                 "second line",
                                                 "      where: a = 1 AND b = 2"])

    def test_query_metric_failures_show_group_by_where_and_having_ip_masked(self):
        full = {"metrics": "['secret_metric_x']", "group_by": "['metric_time__month', 'user__city']",
                "where": "{{ Dimension('order__client_ip') }} = '203.0.113.9'", "having": "gmv > 100",
                "order_by": "['-secret_order_y']", "limit": "10"}
        _, out = self.run_check(events(
            audit_line("query_metric", False, params=full, query_path="metricflow",
                       mf_command="mf query --metrics secret_mf_z", error="INVALID_PARAMS: unknown user__city"),
            audit_line("query_metric", False, timestamp="2026-09-27T08:01:00+0000",
                       params={"metrics": "['gmv']", "group_by": "['metric_time__day']"}, error="QUERY_TIMEOUT")),
            "--failures")
        self.assertEqual(out.splitlines()[-7:], [
            "failures: 2",
            "  2026-09-27T08:00:00+0000  query_metric  INVALID_PARAMS: unknown user__city",
            "      group_by: ['metric_time__month', 'user__city']",
            "      where: {{ Dimension('order__client_ip') }} = '<ip>'",
            "      having: gmv > 100",
            "  2026-09-27T08:01:00+0000  query_metric  QUERY_TIMEOUT",
            "      group_by: ['metric_time__day']"])
        for leaked in ("secret_metric_x", "secret_order_y", "secret_mf_z", "203.0.113.9", "client-abc"):
            self.assertNotIn(leaked, out)

    def test_never_prints_sql_other_params_or_client_ids(self):
        _, out = self.run_check(events(
            audit_line("execute_query", False, error="QUERY_ERROR: Unknown column 'x'"),  # params.sql = SECRET_SQL
            audit_line("describe_table", False, params={"table": "secret_table_w"}, error="TABLE_NOT_FOUND")),
            "--failures")
        self.assertIn("  2026-09-27T08:00:00+0000  describe_table  TABLE_NOT_FOUND", out)
        for leaked in (SECRET_SQL, "phone", "dim_user", "secret_table_w", "client-abc"):
            self.assertNotIn(leaked, out)

    def test_failures_are_listed_in_timestamp_order(self):
        # filter-log-events interleaves the log streams of several runtime sessions.
        _, out = self.run_check(events(
            audit_line("list_tables", False, timestamp="2026-09-27T08:02:00+0000", error="E3"),
            audit_line("describe_table", False, timestamp="2026-09-27T08:00:00+0000", error="E1"),
            audit_line("list_metrics", timestamp="2026-09-27T07:59:00+0000"),
            audit_line("execute_query", False, timestamp="2026-09-27T08:01:00+0000", error="E2"),
            audit_line("get_query_profile", None, timestamp="2026-09-27T07:58:00+0000", error="E0")),  # not True
            "--failures")
        self.assertIn("audit: 5 records (1 ok, 4 failed)", out)
        self.assertEqual(out.splitlines()[-5:], ["failures: 4",
                                                 "  2026-09-27T07:58:00+0000  get_query_profile  E0",
                                                 "  2026-09-27T08:00:00+0000  describe_table  E1",
                                                 "  2026-09-27T08:01:00+0000  execute_query  E2",
                                                 "  2026-09-27T08:02:00+0000  list_tables  E3"])

    def test_no_failures(self):
        rc, out = self.run_check(events(audit_line("list_metrics")), "--failures")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.splitlines()[-1], "failures: 0")

    def test_the_exit_code_is_unchanged(self):
        # Failed tool calls are still audited calls: they alone never fail the check.
        both_failed = events(*(audit_line(t, False, error="QUERY_TIMEOUT") for t in ("execute_query", "list_metrics")))
        self.assertEqual(self.run_check(both_failed, "--calls", str(self.calls), "--failures")[0], 0)
        rc, out = self.run_check(events(audit_line("execute_query", False, error="QUERY_TIMEOUT")),
                                 "--calls", str(self.calls), "--failures")
        self.assertEqual(rc, 1)
        self.assertEqual(out.splitlines()[-2:], ["failures: 1",
                                                 "  2026-09-27T08:00:00+0000  execute_query  QUERY_TIMEOUT"])
        self.assertEqual(self.run_check("not json", "--failures")[0], 2)


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
