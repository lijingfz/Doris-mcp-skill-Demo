"""quick/agent-instructions.md: the instructions of the "Doris 专家" agent in Quick (P4 / T4.3).

The file is pasted into Quick by hand, so these checks are what stands between an edit and the demo: Quick's
size limit, the three parts of design §8.3, the rules the demo depends on, tool names that exist behind the
Gateway, metric and dimension names that the semantic layer publishes and compiles, and nothing that must not
leave the repo.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "doris"))
from reconcile import CASES, MODELS_DIR, Case, DirectBackend, ReconcileError  # noqa: E402  (compiles like the server's query_metric)

INSTRUCTIONS = ROOT / "quick" / "agent-instructions.md"
QUICK_LIMIT = 50_000  # characters; design §4.4
GATEWAY_PREFIX = "doris___"  # <target>___<tool>, design §4.5
GRAINS = ("day", "week", "month", "quarter", "year")  # metric_time__<grain>; every one compiles (SemanticLayer)


def _text() -> str:
    return INSTRUCTIONS.read_text(encoding="utf-8")


def _section(title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", _text(), re.M | re.S)
    if match is None:
        raise AssertionError(f"no section '## {title}'")
    return match.group(1)


def setUpModule():
    logging.disable(logging.WARNING)  # MetricFlow is chatty at INFO/WARNING


def tearDownModule():
    logging.disable(logging.NOTSET)


class Shape(unittest.TestCase):
    def test_fits_the_quick_limit(self):
        self.assertLessEqual(len(_text()), QUICK_LIMIT)

    def test_has_exactly_the_three_parts_of_design_8_3(self):
        self.assertEqual(re.findall(r"^## (.+)$", _text(), re.M), ["角色", "硬约束", "演示口径"])


class Rules(unittest.TestCase):
    def test_the_role_is_the_doris_expert_on_the_ecom_cluster(self):
        role = _section("角色")
        for term in ("Doris 专家", "ecom"):
            self.assertIn(term, role)

    def test_answers_rest_on_tool_results(self):
        rules = _section("硬约束")
        for term in ("证据", f"{GATEWAY_PREFIX}check_service_health", f"{GATEWAY_PREFIX}list_metrics",
                     f"{GATEWAY_PREFIX}query_metric", f"{GATEWAY_PREFIX}execute_query"):
            self.assertIn(term, rules)

    def test_read_only_and_ddl_is_proposed_not_run(self):
        rules = _section("硬约束")
        for term in ("只读", "DDL", "不执行", "人工执行"):
            self.assertIn(term, rules)

    def test_the_60_second_limit_and_how_to_stay_under_it(self):
        rules = _section("硬约束")
        for term in ("60 s", "EXPLAIN", "LIMIT", "424"):
            self.assertIn(term, rules)

    def test_the_semantic_layer_is_not_reloaded_unasked(self):
        self.assertIn(f"{GATEWAY_PREFIX}reload_semantic_layer", _section("硬约束"))

    def test_connection_details_are_not_repeated(self):
        rules = _section("硬约束")
        for term in ("主机", "IP", "账号"):
            self.assertIn(term, rules)

    def test_the_demo_day_and_what_this_year_and_last_year_mean(self):
        framing = _section("演示口径")
        for term in ("2026-09-25", "12:00", "中秋", "今年 = 2026", "去年同期 = 2025"):
            self.assertIn(term, framing)

    def test_the_yoy_metrics_need_a_month_grouping_and_an_end_date(self):
        framing = _section("演示口径")
        for term in ("gmv_last_year", "gmv_yoy", "metric_time__month",
                     "metric_time BETWEEN '2026-01-01' AND '2026-09-25'"):
            self.assertIn(term, framing)

    def test_every_time_grain_of_metric_time_is_named(self):
        framing = _section("演示口径")
        for grain in GRAINS:
            self.assertIn(f"`metric_time__{grain}`", framing)

    def test_filters_follow_the_grain_and_the_same_days_are_compared_by_day(self):
        framing = _section("演示口径")
        for term in ("对齐到分组粒度", "整月", "同期同天数", "group_by `metric_time__day`", "相加"):
            self.assertIn(term, framing)

    def test_one_time_range_per_call_and_no_or(self):
        framing = _section("演示口径")
        for term in ("一次调用只写一个时间范围", "OR"):
            self.assertIn(term, framing)

    def test_time_is_filtered_on_metric_time_not_order_date(self):
        # Only metric_time becomes MetricFlow's time constraint (P-11). A where on order_date, as in the query
        # guide's examples, stays a plain WHERE that also filters the last-year branch, so gmv_last_year and
        # gmv_yoy silently become 0, which the next rule would read as 无数据.
        lines = [line for line in _section("演示口径").splitlines() if "order_date" in line]
        self.assertEqual(len(lines), 1, lines)
        for term in ("时间过滤只写在 metric_time 上", "不要写 order_date 或 order_entity__order_date",
                     "gmv_last_year", "gmv_yoy", "过滤成 0"):
            self.assertIn(term, lines[0])

    def test_diagnosis_uses_the_skills_through_the_adapter(self):
        rules = _section("硬约束")
        for term in ("doris-mcp-adapter", "doris-debug", "doris-profile-reader", "doris-best-practices",
                     "doris-architecture-advisor", "doriscli"):
            self.assertIn(term, rules)

    def test_ratios_are_fractions_and_a_zero_yoy_means_no_data(self):
        framing = _section("演示口径")
        for term in ("mini_program_share", "0~1", "无数据"):
            self.assertIn(term, framing)


class SemanticLayer(unittest.TestCase):
    """The names the agent is told to use are what list_metrics publishes and query_metric compiles."""

    @classmethod
    def setUpClass(cls):
        workspace = tempfile.TemporaryDirectory(prefix="t43_")
        cls.addClassCleanup(workspace.cleanup)
        cls.backend = DirectBackend(MODELS_DIR, workspace.name, fetch=None)
        cls.published = cls.backend.metric_names()

    def test_the_metric_count_is_the_published_one(self):
        self.assertIn(f"{len(self.published)} 个业务指标", _section("角色"))

    def test_metric_and_dimension_names_exist_in_the_semantic_layer(self):
        names = {n for n in re.findall(r"`([a-z][a-z0-9_]*)`", _text())
                 if n != "ecom" and not n.startswith(GATEWAY_PREFIX)}
        dimensions = {n for n in names if "__" in n}  # <entity>__<dimension>, metric_time__<grain>
        metrics = names - dimensions
        self.assertTrue(metrics and dimensions)
        self.assertLessEqual(metrics, self.published)
        for dimension in sorted(dimensions):
            with self.subTest(dimension=dimension):
                try:
                    self.backend.sql(Case(dimension, ("gmv",), (dimension,), "", ""))
                except ReconcileError as e:
                    self.fail(f"group_by {dimension}: {e}")

    def test_the_same_days_comparison_is_a_reconcile_case(self):
        # The same-days recipe in 演示口径 is checked against hand-written SQL on the cluster by reconcile.py.
        case = next((c for c in CASES if c.name == "yoy_same_days_2026_09"), None)
        self.assertIsNotNone(case)
        self.assertEqual((case.metrics, case.group_by), (("gmv", "gmv_last_year"), ("metric_time__day",)))


class Hygiene(unittest.TestCase):
    def test_every_tool_named_exists_behind_the_gateway(self):
        calls = json.loads((ROOT / "scripts" / "smoke_calls.json").read_text(encoding="utf-8"))
        tools = {GATEWAY_PREFIX + c["tool"] for c in calls}
        self.assertEqual(len(tools), 12)
        named = set(re.findall(rf"\b{GATEWAY_PREFIX}\w+", _text()))
        self.assertTrue(named)
        self.assertLessEqual(named, tools)

    def test_every_tool_name_has_the_gateway_prefix(self):
        bare = {c["tool"] for c in json.loads((ROOT / "scripts" / "smoke_calls.json").read_text(encoding="utf-8"))}
        text = re.sub(rf"\b{GATEWAY_PREFIX}\w+", "", _text())
        self.assertEqual({t for t in bare if re.search(rf"\b{t}\b", text)}, set())

    def test_every_skill_named_is_in_quick_skills(self):
        named = set(re.findall(r"\bdoris-[a-z]+(?:-[a-z]+)*", _text()))
        self.assertTrue(named)
        for name in sorted(named):
            with self.subTest(skill=name):
                self.assertTrue((ROOT / "quick" / "skills" / name / "SKILL.md").is_file())

    def test_no_urls_addresses_arns_or_account_ids(self):
        text = _text()
        for pattern in (r"https?://", r"\b\d{1,3}(?:\.\d{1,3}){3}\b", r"\barn:aws", r"\b\d{12}\b",
                        r"amazonaws\.com"):
            self.assertIsNone(re.search(pattern, text), pattern)


if __name__ == "__main__":
    unittest.main()
