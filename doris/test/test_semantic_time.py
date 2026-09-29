"""Offline: metric_time filters on the ecom models compile to the intended time range (P-11, no Doris).

    .venv/bin/python -m unittest discover -s doris/test -v

Compiled through doris/reconcile.py DirectBackend, i.e. bare names resolved and the SQL checked
read-only exactly like the MCP server's query_metric. MetricFlow renders the time constraint as an
inclusive `BETWEEN` aligned to the query grain.
"""

from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
sys.path.insert(0, str(ROOT / "doris"))

from reconcile import MODELS_DIR, Case, DirectBackend, ReconcileError  # noqa: E402

DAY_RANGE = "WHERE DATE_TRUNC('day', order_date) BETWEEN '{}' AND '{}'"


class SemanticTimeRange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.disable(logging.WARNING)  # MetricFlow is chatty at INFO/WARNING
        cls.tmp = tempfile.TemporaryDirectory(prefix="ecom_time_")
        cls.backend = DirectBackend(MODELS_DIR, cls.tmp.name, fetch=None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        logging.disable(logging.NOTSET)

    def sql(self, where: str, group_by: str = "metric_time__day", metrics: tuple[str, ...] = ("gmv",)) -> str:
        return self.backend.sql(Case("t", metrics, (group_by,), where, "SELECT 1"))

    def test_august_with_a_strict_end_is_31_days(self):
        sql = self.sql("metric_time >= '2026-08-01' AND metric_time < '2026-09-01'")
        self.assertIn(DAY_RANGE.format("2026-08-01", "2026-08-31"), sql)
        self.assertNotIn("2026-09-01", sql)

    def test_august_with_a_strict_start_is_31_days(self):
        sql = self.sql("metric_time > '2026-07-31' AND metric_time <= '2026-08-31'")
        self.assertIn(DAY_RANGE.format("2026-08-01", "2026-08-31"), sql)

    def test_strict_end_by_month_stops_before_the_next_month(self):
        # Without the shift the end 2026-10-01 is aligned to 2026-10-31 and October is added.
        sql = self.sql("metric_time >= '2026-09-01' AND metric_time < '2026-10-01'", "metric_time__month")
        self.assertIn(DAY_RANGE.format("2026-09-01", "2026-09-30"), sql)

    def test_day_filters_are_aligned_to_the_month_grain(self):
        # By design (reconcile yoy_2026 depends on it): an inclusive day end covers its whole month.
        sql = self.sql("metric_time >= '2026-09-01' AND metric_time <= '2026-09-25'", "metric_time__month")
        self.assertIn(DAY_RANGE.format("2026-09-01", "2026-09-30"), sql)

    def test_or_between_ranges_is_a_compile_error(self):
        where = ("(metric_time BETWEEN '2025-09-01' AND '2025-09-25') OR "
                 "(metric_time BETWEEN '2026-09-01' AND '2026-09-25')")
        with self.assertRaises(ReconcileError) as caught:
            self.sql(where, "metric_time__year")
        self.assertTrue(str(caught.exception).startswith(
            "compile failed: metric_time filters must be a single range joined with AND"), caught.exception)

    def test_or_in_a_sibling_group_stays_a_where_filter(self):
        sql = self.sql("metric_time >= '2026-08-01' AND (channel = 'APP' OR channel = 'WEB')")
        self.assertIn("Constrain Time Range to [2026-08-01T00:00:00,", sql)
        self.assertIn("WHERE (order_entity__channel = 'APP' OR order_entity__channel = 'WEB')", sql)

    def test_other_time_dimension_stays_a_where_filter(self):
        # order_date resolves to TimeDimension('order_entity__order_date', 'day'), not metric_time.
        sql = self.sql("order_date >= '2026-01-01'")
        self.assertNotIn("Constrain Time Range", sql)
        self.assertIn("WHERE order_entity__order_date__day >= '2026-01-01'", sql)


if __name__ == "__main__":
    unittest.main()
