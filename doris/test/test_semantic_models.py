"""Offline tests for the ecom semantic models in doris/semantic/ecom (no Doris connection).

    .venv/bin/python -m unittest discover -s doris/test -v

The models are compiled with the vendored upstream MetricFlow engine exactly as the MCP server
compiles them (bootstrap -> MetricFlowCompiler). Numbers are checked against Doris by
doris/reconcile.py, not here.
"""

from __future__ import annotations

import logging
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
MODELS = ROOT / "doris" / "semantic" / "ecom"

from metricflow.semantic_interfaces.parsing.dir_to_model import (  # noqa: E402
    parse_directory_of_yaml_files_to_semantic_manifest,
)
from metricflow.semantic_interfaces.validations.semantic_manifest_validator import (  # noqa: E402
    SemanticManifestValidator,
)
from store.bootstrap import _copy_and_normalize_models, bootstrap_from_yaml, collect_physical_tables  # noqa: E402
from store.compiler import MetricFlowCompiler  # noqa: E402
from store.manifest import SemanticManifest  # noqa: E402
from store.watcher import _check_staging_duplicates  # noqa: E402

EXPECTED_METRICS = {
    # orders (v_paid_order): measures with create_metric (upstream default)
    "gmv", "order_count", "buyer_count", "discount_amount",
    # orders: explicit metrics
    "aov", "gmv_mini_program", "mini_program_share", "gmv_last_year", "gmv_yoy",
    # order_items (fact_order_item): explicit metrics only
    "line_gmv", "qty", "gross_profit", "gross_margin", "item_count", "refunded_item_count", "refund_rate",
    # refunds (fact_refund) / reviews (fact_review)
    "refund_count", "refund_amount", "review_count", "avg_rating", "bad_review_count", "bad_review_rate",
}
EXPECTED_TABLES = {
    f"internal.ecom.{t}"
    for t in ("v_paid_order", "fact_order_item", "fact_refund", "fact_review",
              "v_category", "dim_brand", "dim_shop", "dim_region", "dim_date")
}
PII_TABLES = {"internal.ecom.dim_user", "internal.ecom.dim_user_address"}
OFFSET_METRICS = {"gmv_last_year", "gmv_yoy"}  # offset_window metrics need metric_time in group_by
# Doris rejects these as bare aliases (`order_id AS order` is a syntax error on Doris 4.1).
RESERVED_ALIAS_RE = re.compile(
    r"\bAS\s+(order|group|user|key|range|rank|partition|table|index|desc|asc|limit|select|from|where)\b",
    re.IGNORECASE,
)


class EcomSemanticModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.disable(logging.WARNING)  # MetricFlow is chatty at INFO/WARNING
        cls.ws = Path(tempfile.mkdtemp(prefix="ecom_ws_"))
        cls.ok, cls.err = bootstrap_from_yaml(MODELS, cls.ws)
        cls.compiler = MetricFlowCompiler(cls.ws) if cls.ok else None
        cls.manifest = SemanticManifest(cls.ws / "target" / "semantic_manifest.json") if cls.ok else None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.ws, ignore_errors=True)
        logging.disable(logging.NOTSET)

    def setUp(self):
        self.assertTrue(self.ok, f"bootstrap_from_yaml failed: {self.err}")

    def compile(self, metrics, group_by=None, where=None):
        sql, _cmd, err = self.compiler.compile(list(metrics), group_by, where)
        return sql, err

    def test_engine_mode(self):
        self.assertTrue(self.compiler.is_engine_mode, self.compiler.init_error)

    def test_no_duplicate_names(self):
        errors, _warnings = _check_staging_duplicates(MODELS)
        self.assertEqual(errors, [])

    def test_manifest_has_no_blocking_issues(self):
        tmp = Path(tempfile.mkdtemp(prefix="ecom_norm_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        _copy_and_normalize_models(MODELS, tmp)
        parsed = parse_directory_of_yaml_files_to_semantic_manifest(
            directory=str(tmp), apply_transformations=True, raise_issues_as_exceptions=False)
        result = SemanticManifestValidator().validate_semantic_manifest(parsed.semantic_manifest)
        self.assertFalse(result.has_blocking_issues, [str(i) for i in result.all_issues])

    def test_metric_names_are_exact(self):
        self.assertEqual({m["name"] for m in self.manifest.list_metrics()}, EXPECTED_METRICS)

    def test_every_metric_has_a_description(self):
        # list_metrics returns only name + description; the description is what the LLM reads.
        missing = [m["name"] for m in self.manifest.list_metrics() if len((m["description"] or "").strip()) < 4]
        self.assertEqual(missing, [])

    def test_physical_tables_are_exact_and_exclude_pii(self):
        tables = collect_physical_tables(MODELS)
        self.assertEqual(tables, EXPECTED_TABLES)
        self.assertFalse(tables & PII_TABLES)

    def test_every_metric_compiles_by_month(self):
        failed = {}
        for name in sorted(EXPECTED_METRICS):
            sql, err = self.compile([name], ["metric_time__month"])
            if not sql:
                failed[name] = (err or "")[:200]
        self.assertEqual(failed, {})

    def test_compiled_sql_has_no_reserved_word_aliases(self):
        for name in sorted(EXPECTED_METRICS):
            group_by = ["metric_time__month"] if name in OFFSET_METRICS else None
            sql, err = self.compile([name], group_by)
            with self.subTest(metric=name):
                self.assertIsNotNone(sql, err)
                self.assertIsNone(RESERVED_ALIAS_RE.search(sql), RESERVED_ALIAS_RE.search(sql))

    def test_item_level_gmv_is_paid_filtered(self):
        # Line-level GMV must only count items of paid orders (cancelled item rows would add ~9.15M).
        for name in ("line_gmv", "qty", "gross_profit", "gross_margin"):
            sql, err = self.compile([name])
            with self.subTest(metric=name):
                self.assertIsNotNone(sql, err)
                self.assertIn("fact_order_item", sql)
                self.assertIn("v_paid_order", sql)

    def test_refund_rate_follows_story_5_1(self):
        # Story 5.1: refunds of any status / all order items (not paid-filtered), by item order month.
        sql, err = self.compile(["refund_rate"], ["metric_time__month"])
        self.assertIsNotNone(sql, err)
        self.assertIn("fact_refund", sql)
        self.assertIn("fact_order_item", sql)
        self.assertNotIn("v_paid_order", sql)

    def test_bare_names_resolve_to_the_intended_dimensions(self):
        resolve = self.compiler.resolve_group_by
        self.assertEqual(resolve(["gmv"], ["channel"]), ["order_entity__channel"])
        self.assertEqual(resolve(["gmv"], ["month"]), ["metric_time__month"])
        self.assertEqual(resolve(["gmv"], ["area"]), ["region__area"])
        self.assertEqual(resolve(["line_gmv"], ["cat1_name"]), ["category__cat1_name"])
        self.assertEqual(resolve(["line_gmv"], ["brand_tier"]), ["brand__brand_tier"])
        for metric in ("line_gmv", "refund_count", "review_count", "refund_rate"):
            with self.subTest(metric=metric):
                (resolved,) = resolve([metric], ["shop_type"])
                self.assertTrue(resolved.endswith("shop__shop_type"), resolved)

    def test_offset_metrics_need_metric_time(self):
        for name in sorted(OFFSET_METRICS):
            with self.subTest(metric=name):
                self.assertIsNone(self.compile([name])[0])
                self.assertIsNotNone(self.compile([name], ["metric_time__month"])[0])
                description = self.manifest.get_metric(name)["description"]
                self.assertIn("metric_time", description)
                # The dim_date spine runs to 2026-12-31: without an end date the offset rows of
                # 2025-10..12 come back as future months with no current value (reconcile yoy_2026).
                self.assertIn("结束日期", description)
                # Upstream query_metric rewrites NULL metric cells to 0 (tools/semantic.py): periods before
                # 2026 have no prior-year data, so the description must say 0 means "no data", not "flat".
                self.assertIn("2025-01-01", description)
                self.assertIn("无数据", description)


if __name__ == "__main__":
    unittest.main()
