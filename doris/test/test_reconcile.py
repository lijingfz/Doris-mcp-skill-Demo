"""Offline tests for doris/reconcile.py (no Doris connection, no MCP server).

    .venv/bin/python -m unittest discover -s doris/test -v

The live runs are `reconcile.py direct` (T2.4) and `reconcile.py mcp` (T2.6); here the
connection and the MCP client are fakes, while the semantic models are compiled for real.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import logging
import re
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
sys.path.insert(0, str(ROOT / "doris"))

import pymysql  # noqa: E402

import reconcile  # noqa: E402
from core.sql_validator import validate_readonly  # noqa: E402
from reconcile import (  # noqa: E402
    APPROX_METRICS, CASES, Case, DirectBackend, McpBackend, ReconcileError, compare, local_metric_names, normalize,
)

MODELS = ROOT / "doris" / "semantic" / "ecom"
PASSWORD = "Pw0123456789abcdefXYZ"
ENV = {"DORIS_HOST": "10.0.0.1", "DORIS_PORT": "9030", "DORIS_USER": "demo_ro", "DORIS_PASSWORD": PASSWORD}
MONEY = Case("money", ("gmv", "order_count"), ("order_entity__channel",), "", "SELECT 1")
RATIO = Case("ratio", ("refund_rate",), ("metric_time__month",), "", "SELECT 1")
YTD_ROW = {"gmv": Decimal("65442236.24"), "order_count": 42770, "buyer_count": 20187,
           "discount_amount": Decimal("4430032.46"), "aov": 1530.0967089081132}


def setUpModule():
    logging.disable(logging.WARNING)  # MetricFlow is chatty at INFO/WARNING


def tearDownModule():
    logging.disable(logging.NOTSET)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        self.conn.executed.append(sql)

    def fetchall(self):
        return [dict(r) for r in self.conn.rows]


class FakeConn:
    def __init__(self, rows):
        self.rows, self.executed, self.closed = rows, [], False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class FakeClient:
    """Stands in for fastmcp.Client: returns canned tool bodies as MCP text content."""

    def __init__(self, bodies):
        self.bodies, self.calls = bodies, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def call_tool(self, name, args, raise_on_error=True):
        self.calls.append((name, args, raise_on_error))
        body = self.bodies[name]
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class FailingClient(FakeClient):
    """FakeClient whose query_metric raises `error` for one metric list (a transport error, not a tool error)."""

    def __init__(self, bodies, fail_metrics, error):
        super().__init__(bodies)
        self.fail_metrics, self.error = list(fail_metrics), error

    async def call_tool(self, name, args, raise_on_error=True):
        if name == "query_metric" and args["metrics"] == self.fail_metrics:
            self.calls.append((name, args, raise_on_error))
            raise self.error
        return await super().call_tool(name, args, raise_on_error)


def ok(data, meta=None):
    return {"success": True, "data": data, **({"meta": meta} if meta else {})}


def run_main(argv, env=ENV, conn=None, connect=None, client=None, factory=None):
    out, err, seen = io.StringIO(), io.StringIO(), {}

    def fake_connect(**kwargs):
        seen.update(kwargs)
        return conn

    rc = reconcile.main(argv, env=env, connect=connect or fake_connect, out=out, err=err,
                        client_factory=factory or ((lambda settings: client) if client else None))
    return rc, out.getvalue(), err.getvalue(), seen


class Normalize(unittest.TestCase):
    def test_values_are_encoded_like_the_mcp_response(self):
        # Mirrors core.response._Encoder, so direct rows and MCP rows compare alike.
        self.assertEqual(normalize(Decimal("65442236.24")), 65442236.24)
        self.assertIsInstance(normalize(Decimal("1")), float)
        self.assertEqual(normalize(dt.date(2026, 1, 1)), "2026-01-01")
        self.assertEqual(normalize(dt.datetime(2026, 1, 1, 8, 30)), "2026-01-01T08:30:00")
        self.assertEqual(normalize(b"APP"), "APP")
        self.assertEqual(normalize(42770), 42770)
        self.assertIsNone(normalize(None))


class Compare(unittest.TestCase):
    def test_equal_rows_in_any_order_match(self):
        got = [{"order_entity__channel": "APP", "gmv": 2.5, "order_count": 2},
               {"order_entity__channel": "PC", "gmv": 1.0, "order_count": 1}]
        want = [{"order_entity__channel": "PC", "gmv": Decimal("1.00"), "order_count": 1},
                {"order_entity__channel": "APP", "gmv": Decimal("2.50"), "order_count": 2}]
        self.assertEqual(compare(MONEY, got, want), [])

    def test_missing_and_unexpected_rows_are_reported(self):
        got = [{"order_entity__channel": "APP", "gmv": 1, "order_count": 1}]
        want = [{"order_entity__channel": "PC", "gmv": 1, "order_count": 1}]
        problems = compare(MONEY, got, want)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("missing row ('PC',)", problems[0])
        self.assertIn("unexpected row ('APP',)", problems[1])

    def test_money_must_match_to_the_cent(self):
        want = [{"order_entity__channel": "APP", "gmv": Decimal("100.00"), "order_count": 1}]
        close = [{"order_entity__channel": "APP", "gmv": 100.004, "order_count": 1}]
        off = [{"order_entity__channel": "APP", "gmv": 100.01, "order_count": 1}]
        self.assertEqual(compare(MONEY, close, want), [])
        (problem,) = compare(MONEY, off, want)
        self.assertIn("gmv", problem)

    def test_ratios_must_match_to_six_decimals(self):
        want = [{"metric_time__month": dt.date(2026, 7, 1), "refund_rate": Decimal("0.173913")}]
        close = [{"metric_time__month": "2026-07-01", "refund_rate": 0.17391304347826086}]
        off = [{"metric_time__month": "2026-07-01", "refund_rate": 0.1740}]
        self.assertEqual(compare(RATIO, close, want), [])
        self.assertEqual(len(compare(RATIO, off, want)), 1)

    def test_null_metric_counts_as_zero(self):
        # upstream query_metric turns NULL metric cells (FULL OUTER JOIN gaps) into 0
        got = [{"order_entity__channel": "H5", "gmv": 0, "order_count": 0}]
        want = [{"order_entity__channel": "H5", "gmv": None, "order_count": None}]
        self.assertEqual(compare(MONEY, got, want), [])

    def test_empty_reference_is_a_failure(self):
        # Zero rows on both sides would "match" even when both filters are wrong.
        self.assertEqual(len(compare(MONEY, [], [])), 1)

    def test_missing_columns_are_reported(self):
        got = [{"channel": "APP", "gmv": 1, "order_count": 1}]
        want = [{"order_entity__channel": "APP", "gmv": 1, "order_count": 1}]
        (problem,) = compare(MONEY, got, want)
        self.assertIn("order_entity__channel", problem)

    def test_duplicate_keys_are_reported(self):
        row = {"order_entity__channel": "APP", "gmv": 1, "order_count": 1}
        self.assertTrue(any("duplicate" in p for p in compare(MONEY, [row, row], [row])))


class Cases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names = local_metric_names(MODELS)

    def test_cases_cover_every_metric(self):
        covered = set().union(*(c.metrics for c in CASES))
        self.assertEqual(covered, self.names)

    def test_case_names_are_unique(self):
        names = [c.name for c in CASES]
        self.assertEqual(len(names), len(set(names)))

    def test_approx_metrics_exist(self):
        self.assertLessEqual(APPROX_METRICS, self.names)

    def test_offset_metric_cases_have_an_end_date(self):
        # Unbounded, the dim_date spine (to 2026-12-31) adds 2026-10..12 rows holding only last-year values.
        for case in CASES:
            if {"gmv_last_year", "gmv_yoy"} & set(case.metrics):
                with self.subTest(case=case.name):
                    self.assertRegex(case.where, r"metric_time BETWEEN '[0-9-]+' AND '[0-9-]+'")

    def test_reference_sql_is_read_only_and_aliases_every_column(self):
        for case in CASES:
            with self.subTest(case=case.name):
                self.assertEqual(validate_readonly(case.reference_sql), (True, ""))
                for col in case.columns:
                    self.assertRegex(case.reference_sql, re.compile(rf"\bAS\s+{col}\b", re.IGNORECASE))

    def test_every_case_compiles_to_read_only_sql(self):
        with tempfile.TemporaryDirectory() as ws:
            backend = DirectBackend(MODELS, ws, fetch=None)
            for case in CASES:
                with self.subTest(case=case.name):
                    self.assertEqual(validate_readonly(backend.sql(case)), (True, ""))


class Direct(unittest.TestCase):
    def test_query_executes_the_compiled_sql(self):
        seen = []
        with tempfile.TemporaryDirectory() as ws:
            backend = DirectBackend(MODELS, ws, fetch=lambda sql: seen.append(sql) or [{"x": 1}])
            case = next(c for c in CASES if c.name == "refund_rate_5_1")
            self.assertEqual(asyncio.run(backend.query(case)), [{"x": 1}])
        (sql,) = seen
        self.assertIn("fact_refund", sql)
        self.assertIn("深圳极速数码配件专营店", sql)

    def test_uncompilable_case_raises(self):
        bad = Case("bad", ("gmv_yoy",), (), "", "SELECT 1")  # offset metric without metric_time
        with tempfile.TemporaryDirectory() as ws:
            with self.assertRaises(ReconcileError):
                DirectBackend(MODELS, ws, fetch=None).sql(bad)


class Mcp(unittest.TestCase):
    def test_query_calls_query_metric_like_an_agent(self):
        client = FakeClient({"query_metric": ok({"columns": ["gmv"], "rows": [{"gmv": 1.5}]})})
        rows = asyncio.run(McpBackend(client, "ecom").query(
            Case("c", ("gmv",), ("metric_time__month",), "metric_time >= '2026-01-01'", "SELECT 1")))
        self.assertEqual(rows, [{"gmv": 1.5}])
        self.assertEqual(client.calls, [("query_metric", {
            "workspace": "ecom", "metrics": ["gmv"], "group_by": ["metric_time__month"],
            "where": "metric_time >= '2026-01-01'"}, False)])

    def test_tool_error_raises_with_its_code(self):
        client = FakeClient({"query_metric": {"success": False,
                                              "error": {"code": "VALIDATION_ERROR", "message": "bad dim"}}})
        with self.assertRaisesRegex(ReconcileError, "VALIDATION_ERROR"):
            asyncio.run(McpBackend(client, "ecom").query(MONEY))

    def test_non_json_result_raises(self):
        client = FakeClient({"query_metric": "Error calling tool"})
        with self.assertRaisesRegex(ReconcileError, "non-JSON"):
            asyncio.run(McpBackend(client, "ecom").query(MONEY))

    def test_metric_names_reads_one_full_page(self):
        client = FakeClient({"list_metrics": ok([{"name": "gmv", "description": "d"}], {"total_count": 1})})
        self.assertEqual(asyncio.run(McpBackend(client, "ecom").metric_names()), {"gmv"})
        self.assertEqual(client.calls[0][1], {"workspace": "ecom", "page_size": 100})

    def test_metric_names_refuses_a_partial_page(self):
        client = FakeClient({"list_metrics": ok([{"name": "gmv", "description": "d"}],
                                                {"total_count": 150, "next_page_token": "t:100"})})
        with self.assertRaises(ReconcileError):
            asyncio.run(McpBackend(client, "ecom").metric_names())


class Run(unittest.TestCase):
    def test_reconcile_counts_failures_and_masks_secrets(self):
        cases = [MONEY, Case("broken", ("gmv",), (), "", "SELECT 1"), Case("off", ("gmv",), (), "", "SELECT 2")]
        row = {"order_entity__channel": "APP", "gmv": 1, "order_count": 1}

        async def query(case):
            if case.name == "broken":
                raise pymysql.OperationalError(1045, f"Access denied (using password: {PASSWORD})")
            return [row] if case.name == "money" else [{"gmv": 2}]

        out = io.StringIO()
        failed = asyncio.run(reconcile.reconcile(cases, query, lambda case: [row] if case.name == "money"
                                                 else [{"gmv": 1}], out, secrets=[PASSWORD]))
        text = out.getvalue()
        self.assertEqual(failed, 2)
        self.assertIn("ok    money (1 rows)", text)
        self.assertIn("FAIL  broken", text)
        self.assertIn("FAIL  off", text)
        self.assertNotIn(PASSWORD, text)


class Main(unittest.TestCase):
    def test_missing_host_is_a_usage_error(self):
        rc, _, err, _ = run_main(["direct"], env={"DORIS_USER": "u", "DORIS_PASSWORD": "p"})
        self.assertEqual(rc, 2)
        self.assertIn("DORIS_HOST", err)

    def test_unknown_case_is_a_usage_error(self):
        rc, _, err, _ = run_main(["direct", "--case", "nope"], conn=FakeConn([]))
        self.assertEqual(rc, 2)
        self.assertIn("nope", err)

    def test_connect_error_is_masked(self):
        # pymysql puts the host in its connect errors: "Can't connect to MySQL server on '<host>' ...".
        def boom(**_):
            raise pymysql.OperationalError(2003, f"Can't connect to MySQL server on '10.0.0.1' ({PASSWORD})")

        rc, out, err, _ = run_main(["direct"], connect=boom)
        self.assertEqual(rc, 1)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("10.0.0.1", out + err)
        self.assertIn("***", err)

    def test_direct_runs_compiled_and_reference_sql_on_one_connection(self):
        conn = FakeConn([YTD_ROW])
        rc, out, _, seen = run_main(["direct", "--case", "ytd_totals"], conn=conn)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(conn.executed), 2)  # compiled SQL + reference SQL
        self.assertIn("v_paid_order", conn.executed[0])
        self.assertTrue(conn.closed)
        self.assertEqual((seen["host"], seen["port"], seen["user"]), ("10.0.0.1", 9030, "demo_ro"))
        self.assertIs(seen["cursorclass"], pymysql.cursors.DictCursor)
        self.assertIn("1/1 cases match", out)

    def test_mcp_checks_published_metrics_then_reconciles(self):
        names = sorted(local_metric_names(MODELS))
        client = FakeClient({"list_metrics": ok([{"name": n, "description": "d"} for n in names],
                                                {"total_count": len(names)}),
                             "query_metric": ok({"columns": list(YTD_ROW), "rows": [json.loads(
                                 json.dumps(YTD_ROW, default=float))]})})
        conn = FakeConn([YTD_ROW])
        rc, out, _, _ = run_main(["mcp", "--case", "ytd_totals"], conn=conn, client=client)
        self.assertEqual(rc, 0, out)
        self.assertEqual([c[0] for c in client.calls], ["list_metrics", "query_metric"])
        self.assertEqual(len(conn.executed), 1)  # only the reference SQL runs on the direct connection
        self.assertIn(f"published metrics: {len(names)} match", out)

    def test_mcp_fails_when_published_metrics_differ(self):
        client = FakeClient({"list_metrics": ok([{"name": "gmv", "description": "d"}], {"total_count": 1}),
                             "query_metric": ok({"columns": list(YTD_ROW), "rows": [json.loads(
                                 json.dumps(YTD_ROW, default=float))]})})
        rc, out, _, _ = run_main(["mcp", "--case", "ytd_totals"], conn=FakeConn([YTD_ROW]), client=client)
        self.assertEqual(rc, 1)
        self.assertIn("published metrics differ", out)
        self.assertIn("missing", out)

    def test_unexpected_case_error_fails_only_that_case_and_is_masked(self):
        # e.g. a fastmcp transport error (or a KeyError on a malformed body) whose text names the host
        names = sorted(local_metric_names(MODELS))
        ytd = next(c for c in CASES if c.name == "ytd_totals")
        row = {"order_entity__channel": "APP", "gmv": Decimal("2.50"), "order_count": 2}
        client = FailingClient({"list_metrics": ok([{"name": n, "description": "d"} for n in names],
                                                   {"total_count": len(names)}),
                                "query_metric": ok({"columns": list(row), "rows": [json.loads(
                                    json.dumps(row, default=float))]})},
                               ytd.metrics, RuntimeError(f"lost connection to 10.0.0.1 ({PASSWORD})"))
        rc, out, err, _ = run_main(["mcp", "--case", "ytd_totals", "--case", "channel_ytd"],
                                   conn=FakeConn([row]), client=client)
        self.assertEqual(rc, 1, out + err)
        self.assertIn("FAIL  ytd_totals", out)
        self.assertIn("RuntimeError: lost connection to *** (***)", out)
        self.assertIn("ok    channel_ytd (1 rows)", out)  # the run goes on after the failed case
        self.assertIn("1/2 cases match", out)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("10.0.0.1", out + err)

    def test_setup_errors_are_one_masked_line_without_traceback(self):
        # client_factory / build_server, or a non-SettingsError out of load_settings (e.g. boto3 client setup)
        boom = RuntimeError(f"cannot start server on 10.0.0.1 ({PASSWORD})")

        def factory(_settings):
            raise boom

        conn = FakeConn([YTD_ROW])
        runs = {"client_factory": run_main(["mcp", "--case", "ytd_totals"], conn=conn, factory=factory)}
        self.assertTrue(conn.closed)
        with mock.patch.object(reconcile, "load_settings", side_effect=boom):
            runs["load_settings"] = run_main(["mcp"], conn=FakeConn([]))
        for step, (rc, out, err, _) in runs.items():
            with self.subTest(step=step):
                self.assertEqual(rc, 1)
                self.assertEqual([line for line in err.splitlines() if line.startswith("FAILED:")],
                                 ["FAILED: RuntimeError: cannot start server on *** (***)"])
                self.assertNotIn("Traceback", out + err)
                self.assertNotIn(PASSWORD, out + err)
                self.assertNotIn("10.0.0.1", out + err)


if __name__ == "__main__":
    unittest.main()
