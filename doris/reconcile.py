"""Reconcile the ecom semantic metrics with the storyline SQL (P2 / T2.4, T2.6; R-26).

    python doris/reconcile.py direct [--models DIR] [--case NAME ...]   # compile the local YAML, run via pymysql
    python doris/reconcile.py mcp [--workspace ecom] [--case NAME ...]  # in-process MCP server: list_metrics + query_metric

Connection: agentcore_ext.settings.load_settings(os.environ) -- DORIS_HOST, DORIS_PORT and either
DORIS_SECRET_ID or DORIS_USER/DORIS_PASSWORD. Every statement is a SELECT; the MCP server may run its
CREATE ... IF NOT EXISTS on system_mcp. Each case runs the metric query and a hand-written reference
SQL (column aliases = the semantic output columns) and compares the rows by the group-by key.
Exit 0 when every case matches, 1 on a mismatch or runtime error, 2 on usage/configuration errors.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import json
import logging
import math
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
MODELS_DIR = ROOT / "doris" / "semantic" / "ecom"

import pymysql  # noqa: E402

from agentcore_ext.settings import Settings, SettingsError, load_settings  # noqa: E402
from core.sql_validator import validate_readonly  # noqa: E402
from store.bootstrap import bootstrap_from_yaml  # noqa: E402
from store.compiler import MetricFlowCompiler  # noqa: E402
from store.manifest import SemanticManifest  # noqa: E402

MASK = "***"
MAX_PROBLEMS = 10
# Ratios and averages are computed in DOUBLE (or scale-6 DECIMAL); everything else is an exact sum/count.
APPROX_METRICS = frozenset(
    {"aov", "mini_program_share", "gmv_yoy", "gross_margin", "refund_rate", "avg_rating", "bad_review_rate"})
YTD = "metric_time BETWEEN '2026-01-01' AND '2026-09-24'"
YTD_SQL = "BETWEEN '2026-01-01' AND '2026-09-24'"


class ReconcileError(RuntimeError):
    """A case could not be run; messages never contain secret values."""


@dataclasses.dataclass(frozen=True)
class Case:
    name: str
    metrics: tuple[str, ...]
    group_by: tuple[str, ...]  # fully qualified, so the output column names are fixed
    where: str  # bare names, as an agent writes them; resolved like the server does
    reference_sql: str

    @property
    def columns(self) -> tuple[str, ...]:
        return self.group_by + self.metrics


CASES: tuple[Case, ...] = (
    Case("ytd_totals", ("gmv", "order_count", "buyer_count", "discount_amount", "aov"), (), YTD, f"""
        SELECT SUM(pay_amount) AS gmv, COUNT(DISTINCT order_id) AS order_count,
               COUNT(DISTINCT user_id) AS buyer_count, SUM(discount_amount + coupon_amount) AS discount_amount,
               CAST(SUM(pay_amount) AS DOUBLE) / COUNT(DISTINCT order_id) AS aov
        FROM ecom.v_paid_order WHERE order_date {YTD_SQL}"""),
    # Story 2.2 has no end date: 2026-09 includes the live orders of 09-25.
    Case("monthly_2026", ("gmv", "order_count", "buyer_count"), ("metric_time__month",),
         "metric_time >= '2026-01-01'", """
        SELECT DATE_TRUNC('month', order_date) AS metric_time__month, SUM(pay_amount) AS gmv,
               COUNT(DISTINCT order_id) AS order_count, COUNT(DISTINCT user_id) AS buyer_count
        FROM ecom.v_paid_order WHERE order_date >= '2026-01-01'
        GROUP BY DATE_TRUNC('month', order_date)"""),
    # Offset metrics need an end date: the dim_date spine runs to 2026-12-31, so an open range adds
    # 2026-10..12 rows that hold only last-year values. 2026-09 (to 09-25) is compared with all of 2025-09.
    Case("yoy_2026", ("gmv", "gmv_last_year", "gmv_yoy"), ("metric_time__month",),
         "metric_time BETWEEN '2026-01-01' AND '2026-09-25'", """
        SELECT t.m AS metric_time__month, t.gmv AS gmv, l.gmv AS gmv_last_year,
               (t.gmv - l.gmv) / NULLIF(l.gmv, 0) AS gmv_yoy
        FROM (SELECT DATE_TRUNC('month', order_date) AS m, SUM(pay_amount) AS gmv
              FROM ecom.v_paid_order WHERE order_date >= '2026-01-01'
              GROUP BY DATE_TRUNC('month', order_date)) t
        LEFT JOIN (SELECT MONTHS_ADD(DATE_TRUNC('month', order_date), 12) AS m, SUM(pay_amount) AS gmv
                   FROM ecom.v_paid_order WHERE order_date < '2026-01-01'
                   GROUP BY MONTHS_ADD(DATE_TRUNC('month', order_date), 12)) l ON l.m = t.m"""),
    Case("channel_ytd", ("gmv", "order_count"), ("order_entity__channel",), YTD, f"""
        SELECT channel AS order_entity__channel, SUM(pay_amount) AS gmv, COUNT(DISTINCT order_id) AS order_count
        FROM ecom.v_paid_order WHERE order_date {YTD_SQL} GROUP BY channel"""),
    Case("area_ytd", ("gmv", "order_count", "buyer_count", "aov"), ("region__area",), YTD, f"""
        SELECT r.area AS region__area, SUM(o.pay_amount) AS gmv, COUNT(DISTINCT o.order_id) AS order_count,
               COUNT(DISTINCT o.user_id) AS buyer_count,
               CAST(SUM(o.pay_amount) AS DOUBLE) / COUNT(DISTINCT o.order_id) AS aov
        FROM ecom.v_paid_order o JOIN ecom.dim_region r ON r.region_id = o.region_id
        WHERE o.order_date {YTD_SQL} GROUP BY r.area"""),
    # Story 2.5: all quarters, 2026-Q3 includes 09-25.
    Case("mini_program_quarterly", ("gmv", "gmv_mini_program", "mini_program_share"), ("metric_time__quarter",),
         "", """
        SELECT DATE_TRUNC('quarter', order_date) AS metric_time__quarter, SUM(pay_amount) AS gmv,
               SUM(IF(channel = 'MINI_PROGRAM', pay_amount, 0)) AS gmv_mini_program,
               CAST(SUM(IF(channel = 'MINI_PROGRAM', pay_amount, 0)) AS DOUBLE) / SUM(pay_amount)
                   AS mini_program_share
        FROM ecom.v_paid_order GROUP BY DATE_TRUNC('quarter', order_date)"""),
    # Item-level metrics count only items of paid orders.
    Case("cat1_items_ytd", ("line_gmv", "qty", "gross_profit", "gross_margin"), ("category__cat1_name",), YTD, f"""
        SELECT c.cat1_name AS category__cat1_name, SUM(i.pay_amount) AS line_gmv, SUM(i.quantity) AS qty,
               SUM(i.pay_amount - i.cost_amount) AS gross_profit,
               CAST(SUM(i.pay_amount - i.cost_amount) AS DOUBLE) / SUM(i.pay_amount) AS gross_margin
        FROM ecom.fact_order_item i
        JOIN ecom.v_paid_order o ON o.order_id = i.order_id
        JOIN ecom.v_category c ON c.category_id = i.category_id
        WHERE i.order_date {YTD_SQL} GROUP BY c.cat1_name"""),
    Case("brand_tier_ytd", ("line_gmv", "gross_profit"), ("brand__brand_tier",), YTD, f"""
        SELECT b.brand_tier AS brand__brand_tier, SUM(i.pay_amount) AS line_gmv,
               SUM(i.pay_amount - i.cost_amount) AS gross_profit
        FROM ecom.fact_order_item i
        JOIN ecom.v_paid_order o ON o.order_id = i.order_id
        JOIN ecom.dim_brand b ON b.brand_id = i.brand_id
        WHERE i.order_date {YTD_SQL} GROUP BY b.brand_tier"""),
    # Story 5.1: refunds of any status / all item rows (cancelled orders included), by item order month.
    Case("refund_rate_5_1", ("refund_rate", "refunded_item_count", "item_count"),
         ("shop__shop_name", "metric_time__month"),
         "metric_time BETWEEN '2026-07-01' AND '2026-08-31' AND shop__shop_name = '深圳极速数码配件专营店'", """
        SELECT s.shop_name AS shop__shop_name, DATE_TRUNC('month', i.order_date) AS metric_time__month,
               COUNT(r.refund_id) AS refunded_item_count, COUNT(*) AS item_count,
               CAST(COUNT(r.refund_id) AS DOUBLE) / COUNT(*) AS refund_rate
        FROM ecom.fact_order_item i
        JOIN ecom.dim_shop s ON s.shop_id = i.shop_id
        LEFT JOIN ecom.fact_refund r ON r.item_id = i.item_id
        WHERE i.order_date BETWEEN '2026-07-01' AND '2026-08-31' AND s.shop_name = '深圳极速数码配件专营店'
        GROUP BY s.shop_name, DATE_TRUNC('month', i.order_date)"""),
    Case("reviews_by_shop_type_ytd", ("review_count", "avg_rating", "bad_review_count", "bad_review_rate"),
         ("shop__shop_type",), YTD, f"""
        SELECT s.shop_type AS shop__shop_type, COUNT(DISTINCT v.review_id) AS review_count,
               AVG(v.rating) AS avg_rating, SUM(IF(v.rating <= 2, 1, 0)) AS bad_review_count,
               CAST(SUM(IF(v.rating <= 2, 1, 0)) AS DOUBLE) / COUNT(DISTINCT v.review_id) AS bad_review_rate
        FROM ecom.fact_review v JOIN ecom.dim_shop s ON s.shop_id = v.shop_id
        WHERE v.review_date {YTD_SQL} GROUP BY s.shop_type"""),
    Case("refunds_by_reason_ytd", ("refund_count", "refund_amount"), ("refund__refund_reason",), YTD, f"""
        SELECT refund_reason AS refund__refund_reason, COUNT(DISTINCT refund_id) AS refund_count,
               SUM(refund_amount) AS refund_amount
        FROM ecom.fact_refund WHERE apply_date {YTD_SQL} GROUP BY refund_reason"""),
)


def normalize(value: Any) -> Any:
    """Encode like core.response._Encoder, so direct rows and MCP rows compare alike."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _number(value: Any) -> float:
    value = normalize(value)
    if value is None:  # upstream query_metric reports NULL metric cells as 0
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _close(metric: str, a: float, b: float) -> bool:
    if metric in APPROX_METRICS:
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
    return abs(a - b) <= 0.005


def compare(case: Case, got: Sequence[Mapping[str, Any]], want: Sequence[Mapping[str, Any]]) -> list[str]:
    """Problems found when matching semantic rows (got) with reference rows (want) by group-by key."""
    if not want:
        return ["reference SQL returned no rows"]
    problems: list[str] = []
    indexes = []
    for side, rows in (("semantic", got), ("reference", want)):
        index: dict[tuple, Mapping[str, Any]] = {}
        for row in rows:
            absent = [c for c in case.columns if c not in row]
            if absent:
                return [f"{side} rows lack columns {absent} (have {sorted(row)})"]
            key = tuple(normalize(row[c]) for c in case.group_by)
            if key in index:
                problems.append(f"{side}: duplicate row {key}")
            index[key] = row
        indexes.append(index)
    got_index, want_index = indexes
    problems += [f"missing row {k}" for k in sorted(want_index.keys() - got_index.keys(), key=repr)]
    problems += [f"unexpected row {k}" for k in sorted(got_index.keys() - want_index.keys(), key=repr)]
    for key in sorted(got_index.keys() & want_index.keys(), key=repr):
        for metric in case.metrics:
            a, b = _number(got_index[key][metric]), _number(want_index[key][metric])
            if not _close(metric, a, b):
                problems.append(f"{key} {metric}: semantic {a!r} != reference {b!r}")
    return problems


def _mask(text: str, secrets: Iterable[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, MASK)
    return text


def _failed(error: Exception, secrets: Iterable[str], err: TextIO) -> int:
    """One masked line instead of a traceback: the message may name the host or carry a password."""
    print(f"FAILED: {type(error).__name__}: {_mask(str(error), secrets)}", file=err)
    return 1


def fetch(conn: Any, sql: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return list(cur.fetchall())


class DirectBackend:
    """Compile like the server's query_metric (bare names resolved, read-only check); run the SQL via fetch."""

    def __init__(self, models_dir: Path | str, workspace_dir: Path | str,
                 fetch: Callable[[str], list[dict[str, Any]]] | None):
        ws = Path(workspace_dir)
        ok, error = bootstrap_from_yaml(Path(models_dir), ws)
        if not ok:
            raise ReconcileError(f"bootstrap {models_dir}: {error}")
        self.compiler = MetricFlowCompiler(ws)
        if not self.compiler.is_engine_mode:
            raise ReconcileError(f"MetricFlow engine unavailable: {self.compiler.init_error}")
        self.manifest = SemanticManifest(ws / "target" / "semantic_manifest.json")
        self._fetch = fetch

    def metric_names(self) -> set[str]:
        return {m["name"] for m in self.manifest.list_metrics()}

    def sql(self, case: Case) -> str:
        metrics = list(case.metrics)
        group_by = self.compiler.resolve_group_by(metrics, list(case.group_by)) if case.group_by else None
        where = self.compiler.resolve_where(metrics, case.where) if case.where else None
        sql, _command, error = self.compiler.compile(metrics, group_by, where)
        if not sql:
            raise ReconcileError(f"compile failed: {(error or 'empty SQL')[:300]}")
        ok, message = validate_readonly(sql)
        if not ok:
            raise ReconcileError(f"compiled SQL is not read-only: {message}")
        return sql

    async def query(self, case: Case) -> list[dict[str, Any]]:
        return self._fetch(self.sql(case))


def local_metric_names(models_dir: Path | str) -> set[str]:
    with tempfile.TemporaryDirectory(prefix="reconcile_names_") as ws:
        return DirectBackend(models_dir, ws, fetch=None).metric_names()


class McpBackend:
    """Call the semantic tools the way an agent does, through a fastmcp Client."""

    def __init__(self, client: Any, workspace: str):
        self.client, self.workspace = client, workspace

    async def _call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.call_tool(tool, args, raise_on_error=False)
        text = "".join(getattr(c, "text", "") for c in result.content)
        try:
            body = json.loads(text)
        except ValueError:
            raise ReconcileError(f"{tool}: non-JSON result: {text[:300]}") from None
        if not isinstance(body, dict) or body.get("success") is not True:
            error = body.get("error", body) if isinstance(body, dict) else body
            raise ReconcileError(f"{tool}: {json.dumps(error, ensure_ascii=False)[:500]}")
        return body

    async def metric_names(self) -> set[str]:
        body = await self._call("list_metrics", {"workspace": self.workspace, "page_size": 100})
        meta = body.get("meta") or {}
        if meta.get("next_page_token"):
            raise ReconcileError(f"list_metrics: more than one page ({meta.get('total_count')} metrics)")
        return {m["name"] for m in body["data"]}

    async def query(self, case: Case) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"workspace": self.workspace, "metrics": list(case.metrics)}
        if case.group_by:
            args["group_by"] = list(case.group_by)
        if case.where:
            args["where"] = case.where
        return (await self._call("query_metric", args))["data"]["rows"]


async def reconcile(cases: Sequence[Case], query: Callable[[Case], Awaitable[list[dict[str, Any]]]],
                    reference: Callable[[Case], list[dict[str, Any]]], out: TextIO,
                    secrets: Iterable[str] = ()) -> int:
    """Run every case, print one line per case; returns the number of failed cases."""
    secrets = list(secrets)
    failed = 0
    for case in cases:
        want: list[dict[str, Any]] = []
        try:
            got = await query(case)
            want = reference(case)
            problems = compare(case, got, want)
        except Exception as e:  # noqa: BLE001 - fails only this case; printed masked below, no traceback
            problems = [f"{type(e).__name__}: {e}"]
        if problems:
            failed += 1
            print(f"FAIL  {case.name}: {len(problems)} problem(s)", file=out)
            for problem in problems[:MAX_PROBLEMS]:
                print(f"      {_mask(problem, secrets)}", file=out)
        else:
            print(f"ok    {case.name} ({len(want)} rows)", file=out)
    print(f"{len(cases) - failed}/{len(cases)} cases match", file=out)
    return failed


def _in_process_client(settings: Settings) -> Any:
    from fastmcp import Client

    from agentcore_ext.app import build_server

    return Client(build_server(settings))


async def _run_mcp(client: Any, models_dir: Path, workspace: str, cases: Sequence[Case],
                   reference: Callable[[Case], list[dict[str, Any]]], out: TextIO, secrets: Sequence[str]) -> int:
    expected = local_metric_names(models_dir)
    failed = 0
    async with client:
        backend = McpBackend(client, workspace)
        published = await backend.metric_names()
        if published == expected:
            print(f"published metrics: {len(published)} match {models_dir}", file=out)
        else:
            failed += 1
            print(f"FAIL  published metrics differ from {models_dir}: missing {sorted(expected - published)}, "
                  f"extra {sorted(published - expected)}", file=out)
        failed += await reconcile(cases, backend.query, reference, out, secrets)
    return failed


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None,
         connect: Callable[..., Any] = pymysql.connect, out: TextIO = sys.stdout, err: TextIO = sys.stderr,
         client_factory: Callable[[Settings], Any] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile ecom semantic metrics with the storyline SQL.")
    parser.add_argument("mode", choices=("direct", "mcp"))
    parser.add_argument("--models", type=Path, default=MODELS_DIR, help="local semantic YAML directory")
    parser.add_argument("--workspace", default="ecom", help="MCP workspace (mcp mode)")
    parser.add_argument("--case", action="append", default=[], help="run only this case (repeatable)")
    args = parser.parse_args(argv)

    cases = list(CASES)
    if args.case:
        unknown = sorted(set(args.case) - {c.name for c in CASES})
        if unknown:
            print(f"ERROR: unknown case(s): {', '.join(unknown)}", file=err)
            return 2
        cases = [c for c in CASES if c.name in args.case]
    env = os.environ if env is None else env
    try:
        settings = load_settings(env)
    except SettingsError as e:
        print(f"ERROR: {e}", file=err)
        return 2
    except Exception as e:  # noqa: BLE001 - e.g. boto3 client setup for DORIS_SECRET_ID
        return _failed(e, [env.get("DORIS_PASSWORD", ""), env.get("DORIS_HOST", "")], err)
    secrets = [settings.doris_password, settings.doris_host]  # pymysql errors name the host
    try:
        conn = connect(host=settings.doris_host, port=settings.doris_port, user=settings.doris_user,
                       password=settings.doris_password, connect_timeout=10, read_timeout=120,
                       autocommit=True, cursorclass=pymysql.cursors.DictCursor)
    except pymysql.MySQLError as e:
        print(f"FAILED: connect: {_mask(str(e), secrets)}", file=err)
        return 1

    logging.disable(logging.WARNING)  # MetricFlow and the server are chatty below ERROR
    try:
        with tempfile.TemporaryDirectory(prefix="reconcile_") as tmp:
            def reference(case: Case) -> list[dict[str, Any]]:
                return fetch(conn, case.reference_sql)

            if args.mode == "direct":
                backend = DirectBackend(args.models, tmp, fetch=lambda sql: fetch(conn, sql))
                failed = asyncio.run(reconcile(cases, backend.query, reference, out, secrets))
            else:
                # A fresh workspace dir, so the server reads the published models from Doris, not a cache.
                client = (client_factory or _in_process_client)(dataclasses.replace(settings, workspace_dir=tmp))
                failed = asyncio.run(_run_mcp(client, args.models, args.workspace, cases, reference, out, secrets))
    except ReconcileError as e:
        print(f"FAILED: {_mask(str(e), secrets)}", file=err)
        return 1
    except Exception as e:  # noqa: BLE001 - e.g. client_factory / build_server, a transport error
        return _failed(e, secrets, err)
    finally:
        conn.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
