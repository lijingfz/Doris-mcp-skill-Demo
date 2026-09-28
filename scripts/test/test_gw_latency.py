"""scripts/gw_latency.py: per-minute latency of the Gateway's tools/call from CloudWatch (P4 / T4.6, P0 review M-3)."""

import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gw_latency  # noqa: E402

ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/doris-mcp-gw-abc123"
T1, T2, T3 = "2026-09-27T13:49:00+00:00", "2026-09-27T13:50:00+00:00", "2026-09-27T13:51:00+00:00"


def result(id_: str, tool: str, points: dict[str, float]) -> dict:
    return {"Id": id_, "Label": tool, "Timestamps": list(points), "Values": list(points.values()),
            "StatusCode": "Complete"}


def minute(tool: str, at: str, calls: int, avg: float, peak: float) -> list[dict]:
    return [result("calls", tool, {at: calls}), result("avg", tool, {at: avg}), result("max", tool, {at: peak})]


def doc(*results: dict) -> str:
    return json.dumps({"MetricDataResults": list(results), "Messages": []})


def run(stdin: str, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    rc = gw_latency.main(["report", *argv], stdin=io.StringIO(stdin), out=out)
    return rc, out.getvalue()


class Queries(unittest.TestCase):
    def test_one_search_per_statistic_labelled_with_the_tool_name(self):
        queries = gw_latency.queries(ARN)
        self.assertEqual([q["Id"] for q in queries], ["calls", "avg", "max"])
        for query, stat in zip(queries, ("SampleCount", "Average", "Maximum")):
            self.assertEqual(query["Label"], "${PROP('Dim.Name')}")
            expression = query["Expression"]
            self.assertTrue(expression.startswith(
                "SEARCH('{AWS/Bedrock-AgentCore,Method,Name,Operation,Protocol,Resource} "), expression)
            self.assertTrue(expression.endswith(f"', '{stat}', 60)"), expression)
            for term in ('MetricName="Latency"', 'Operation="InvokeGateway"', 'Method="tools/call"',
                         f'Resource="{ARN}"'):
                self.assertIn(term, expression)

    def test_the_cli_prints_the_queries_as_json(self):
        out = io.StringIO()
        self.assertEqual(gw_latency.main(["queries", "--gateway-arn", ARN], out=out), 0)
        self.assertEqual(json.loads(out.getvalue()), gw_latency.queries(ARN))

    def test_refuses_a_value_that_is_not_a_gateway_arn(self):
        for bad in ("doris-mcp-gw-abc123", ARN + "\" Name=\"x", ARN.replace("gateway/", "runtime/")):
            with self.subTest(bad=bad):
                out = io.StringIO()
                self.assertEqual(gw_latency.main(["queries", "--gateway-arn", bad], out=out), 2)
                self.assertEqual(out.getvalue(), "FAIL: --gateway-arn is not a Gateway ARN\n")


class Report(unittest.TestCase):
    def test_one_line_per_minute_and_tool_in_time_order(self):
        rc, out = run(doc(*minute("doris___query_metric", T3, 1, 9269, 9269),
                          *minute("doris___check_service_health", T1, 1, 5432, 5432),
                          *minute("doris___list_metrics", T3, 2, 6100.4, 6752)))
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.splitlines(), [
            "tools/call: 4 calls in 3 rows (tool x minute), max 9269 ms (doris___query_metric at 2026-09-27T13:51)",
            "  2026-09-27T13:49  doris___check_service_health           1 calls  avg    5432 ms  max    5432 ms",
            "  2026-09-27T13:51  doris___list_metrics                   2 calls  avg    6100 ms  max    6752 ms",
            "  2026-09-27T13:51  doris___query_metric                   1 calls  avg    9269 ms  max    9269 ms",
            "  [PASS] every minute under 60000 ms",
        ])

    def test_over_the_warning_threshold_is_flagged_but_passes(self):
        rc, out = run(doc(*minute("doris___execute_query", T2, 1, 47000, 47000),
                          *minute("doris___list_tables", T3, 1, 5600, 5600)))
        self.assertEqual(rc, 0, out)
        self.assertIn("  [PASS] every minute under 60000 ms", out)
        self.assertIn("  [WARN] >= 45000 ms (T5.5: lower query_timeout): "
                      "2026-09-27T13:50 doris___execute_query 47000 ms", out)

    def test_reaching_quick_s_limit_fails(self):
        rc, out = run(doc(*minute("doris___execute_query", T2, 1, 60000, 60000)))
        self.assertEqual(rc, 1)
        self.assertIn("  [FAIL] every minute under 60000 ms (1 not: 2026-09-27T13:50 doris___execute_query 60000 ms)",
                      out)

    def test_the_thresholds_are_options(self):
        rc, out = run(doc(*minute("doris___list_tables", T1, 1, 6000, 6000),
                          *minute("doris___query_metric", T2, 1, 9500, 9500)),
                      "--warn-ms", "5000", "--limit-ms", "9000")
        self.assertEqual(rc, 1)
        self.assertIn("  [FAIL] every minute under 9000 ms (1 not: 2026-09-27T13:50 doris___query_metric 9500 ms)", out)
        self.assertIn("  [WARN] >= 5000 ms (T5.5: lower query_timeout): 2026-09-27T13:49 doris___list_tables 6000 ms, "
                      "2026-09-27T13:50 doris___query_metric 9500 ms", out)

    def test_no_datapoints_fails(self):
        rc, out = run(doc(result("calls", "doris___list_tables", {}), result("max", "doris___list_tables", {})))
        self.assertEqual(rc, 1)
        self.assertEqual(out.splitlines(), ["tools/call: 0 calls in 0 rows (tool x minute)",
                                            "  [FAIL] no tools/call datapoints in the window"])

    def test_results_of_other_queries_are_ignored(self):
        rc, out = run(doc(*minute("doris___list_tables", T1, 1, 5600, 5600),
                          result("m_other", "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/x", {T1: 70000})))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("arn:", out)
        self.assertNotIn("70000", out)

    def test_input_that_is_not_get_metric_data_json(self):
        for stdin in ("", "not json", "[]", '{"events": []}', '{"MetricDataResults": 5}'):
            with self.subTest(stdin=stdin):
                rc, out = run(stdin)
                self.assertEqual(rc, 2)
                self.assertEqual(out, "FAIL: input is not get-metric-data JSON (aws cloudwatch get-metric-data "
                                      "--output json)\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
