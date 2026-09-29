"""P-11: MetricFlowCompiler._extract_time_constraints turns metric_time filters into one time range.

metric_time comparisons become MetricFlow time_constraint_start/end (inclusive, day grain for
date-only literals); everything else stays in the where. OR around a metric_time condition is
rejected with a message for the calling agent, instead of compiling to `WHERE () OR ()`; so is a
NOT before a metric_time condition or around a group enclosing one, instead of the NOT silently
moving onto the next filter.
"""

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from store.compiler import MetricFlowCompiler  # noqa: E402
from tools.semantic import query_metric  # noqa: E402

extract = MetricFlowCompiler._extract_time_constraints
TD = "{{ TimeDimension('metric_time', 'day') }}"
ORDER_DATE = "{{ TimeDimension('order_entity__order_date', 'day') }}"
CHANNEL = "{{ Dimension('order_entity__channel') }}"
OR_RANGES = ("(metric_time BETWEEN '2025-09-01' AND '2025-09-25') OR "
             "(metric_time BETWEEN '2026-09-01' AND '2026-09-25')")
OR_MESSAGE = "metric_time filters must be a single range joined with AND"
NOT_MESSAGE = "metric_time filters cannot be negated with NOT"


def d(*args):
    return datetime(*args)


class TestDocumentedBehaviour(unittest.TestCase):
    """The docstring examples and the forms the server already relied on before P-11."""

    def test_start_only(self):
        self.assertEqual(extract("metric_time >= '2026-02-01'"), (None, d(2026, 2, 1), None))

    def test_start_and_end(self):
        self.assertEqual(extract("metric_time >= '2026-02-01' AND metric_time <= '2026-02-28'"),
                         (None, d(2026, 2, 1), d(2026, 2, 28)))

    def test_other_filters_remain(self):
        self.assertEqual(extract("metric_time >= '2026-02-01' AND channel = 'APP'"),
                         ("channel = 'APP'", d(2026, 2, 1), None))
        self.assertEqual(extract("channel = 'X' AND metric_time >= '2026-01-01' AND region = 'y'"),
                         ("channel = 'X' AND region = 'y'", d(2026, 1, 1), None))

    def test_time_dimension_template(self):
        self.assertEqual(extract(f"{TD} >= '2026-02-01'"), (None, d(2026, 2, 1), None))
        self.assertEqual(extract(f"{TD} >= '2026-02-01' AND {CHANNEL} = 'APP'"),
                         (f"{CHANNEL} = 'APP'", d(2026, 2, 1), None))

    def test_between_is_inclusive(self):
        self.assertEqual(extract("metric_time BETWEEN '2026-01-01' AND '2026-09-24'"),
                         (None, d(2026, 1, 1), d(2026, 9, 24)))
        self.assertEqual(extract("metric_time between '2026-01-01' and '2026-09-24'"),
                         (None, d(2026, 1, 1), d(2026, 9, 24)))

    def test_between_with_other_filter(self):
        # reconcile.py shop case
        self.assertEqual(extract("metric_time BETWEEN '2026-07-01' AND '2026-08-31' AND shop__shop_name = 'x'"),
                         ("shop__shop_name = 'x'", d(2026, 7, 1), d(2026, 8, 31)))

    def test_grain_suffix_names(self):
        self.assertEqual(extract("metric_time__month >= '2026-01-01'"), (None, d(2026, 1, 1), None))
        self.assertEqual(extract("metric_time__day <= '2026-01-31'"), (None, None, d(2026, 1, 31)))

    def test_double_quoted_literals(self):
        self.assertEqual(extract('metric_time >= "2026-02-01" AND metric_time <= "2026-02-28"'),
                         (None, d(2026, 2, 1), d(2026, 2, 28)))

    def test_time_part(self):
        self.assertEqual(extract("metric_time >= '2026-08-01 10:00:00'"), (None, d(2026, 8, 1, 10), None))
        self.assertEqual(extract("metric_time <= '2026-08-01T10:30:00'"), (None, None, d(2026, 8, 1, 10, 30)))

    def test_nothing_to_extract(self):
        for where in (None, "", "   "):
            self.assertEqual(extract(where), (None, None, None))
        self.assertEqual(extract("channel = 'APP'"), ("channel = 'APP'", None, None))

    def test_outer_quotes_only_leftover_is_none(self):
        self.assertEqual(extract("\"metric_time >= '2026-02-01'\""), (None, d(2026, 2, 1), None))


class TestOr(unittest.TestCase):
    def assert_rejected(self, where):
        with self.assertRaises(ValueError) as caught:
            extract(where)
        message = str(caught.exception)
        self.assertTrue(message.startswith(OR_MESSAGE), message)
        for hint in ("no OR", "one query_metric call per range", "_last_year", "grouped by metric_time"):
            self.assertIn(hint, message)

    def test_or_between_ranges(self):
        self.assert_rejected(OR_RANGES)
        self.assert_rejected(OR_RANGES.replace("(", "").replace(")", ""))
        self.assert_rejected(f"({TD} BETWEEN '2025-09-01' AND '2025-09-25') OR ({TD} BETWEEN '2026-09-01' AND '2026-09-25')")

    def test_or_at_the_match_level(self):
        self.assert_rejected("metric_time >= '2026-01-01' AND (channel = 'APP' OR metric_time < '2026-02-01')")
        self.assert_rejected("metric_time >= '2026-01-01' or channel = 'APP'")

    def test_or_at_an_enclosing_level(self):
        self.assert_rejected("channel = 'A' OR (metric_time >= '2026-01-01' AND channel = 'B')")
        self.assert_rejected("(channel = 'A' OR (region = 'x' AND (metric_time >= '2026-01-01'))) AND qty > 1")

    def test_or_in_a_sibling_group_is_kept(self):
        self.assertEqual(extract("metric_time >= '2026-01-01' AND (channel = 'A' OR channel = 'B')"),
                         ("(channel = 'A' OR channel = 'B')", d(2026, 1, 1), None))
        self.assertEqual(extract(f"{TD} >= '2026-01-01' AND ({CHANNEL} = 'A' OR {CHANNEL} = 'B')"),
                         (f"({CHANNEL} = 'A' OR {CHANNEL} = 'B')", d(2026, 1, 1), None))

    def test_or_inside_a_literal_is_not_an_or(self):
        self.assertEqual(extract("metric_time >= '2026-01-01' AND note = 'x OR y'"),
                         ("note = 'x OR y'", d(2026, 1, 1), None))
        self.assertEqual(extract('metric_time >= \'2026-01-01\' AND note = "a or b"'),
                         ('note = "a or b"', d(2026, 1, 1), None))

    def test_parentheses_inside_a_literal_are_ignored(self):
        where = "(channel = 'A' OR note = 'x (') AND metric_time >= '2026-01-01'"
        self.assertEqual(extract(where), ("(channel = 'A' OR note = 'x (')", d(2026, 1, 1), None))

    def test_or_without_metric_time_is_untouched(self):
        self.assertEqual(extract("channel = 'A' OR channel = 'B'"), ("channel = 'A' OR channel = 'B'", None, None))


class TestStrictOperators(unittest.TestCase):
    def test_greater_than_a_date_starts_the_next_day(self):
        self.assertEqual(extract("metric_time > '2026-08-31'"), (None, d(2026, 9, 1), None))
        self.assertEqual(extract("metric_time > '2025-12-31'"), (None, d(2026, 1, 1), None))

    def test_less_than_a_date_ends_the_day_before(self):
        self.assertEqual(extract("metric_time < '2026-09-01'"), (None, None, d(2026, 8, 31)))
        self.assertEqual(extract("metric_time < '2026-03-01'"), (None, None, d(2026, 2, 28)))

    def test_august_with_a_strict_end(self):
        self.assertEqual(extract("metric_time >= '2026-08-01' AND metric_time < '2026-09-01'"),
                         (None, d(2026, 8, 1), d(2026, 8, 31)))

    def test_time_part_shifts_by_one_second(self):
        self.assertEqual(extract("metric_time > '2026-08-01 10:00:00'"), (None, d(2026, 8, 1, 10, 0, 1), None))
        self.assertEqual(extract("metric_time < '2026-08-01T10:00:00'"), (None, None, d(2026, 8, 1, 9, 59, 59)))


class TestTimeDimensionTemplate(unittest.TestCase):
    def test_other_time_dimension_stays_in_where(self):
        where = f"{ORDER_DATE} >= '2026-01-01'"
        self.assertEqual(extract(where), (where, None, None))

    def test_mixed_with_metric_time(self):
        self.assertEqual(extract(f"{TD} >= '2026-01-01' AND {ORDER_DATE} <= '2026-03-31'"),
                         (f"{ORDER_DATE} <= '2026-03-31'", d(2026, 1, 1), None))

    def test_spaces_double_quotes_and_grain(self):
        self.assertEqual(extract("{{ TimeDimension( \"metric_time\" , 'month') }} >= '2026-01-01'"),
                         (None, d(2026, 1, 1), None))
        self.assertEqual(extract("{{TimeDimension('metric_time')}} <= '2026-01-31'"), (None, None, d(2026, 1, 31)))


class TestIntersection(unittest.TestCase):
    def test_latest_start_wins(self):
        self.assertEqual(extract("metric_time >= '2026-03-01' AND metric_time >= '2026-01-01'"),
                         (None, d(2026, 3, 1), None))

    def test_earliest_end_wins(self):
        self.assertEqual(extract("metric_time <= '2026-03-31' AND metric_time BETWEEN '2026-01-01' AND '2026-06-30'"),
                         (None, d(2026, 1, 1), d(2026, 3, 31)))
        self.assertEqual(extract("metric_time BETWEEN '2026-02-01' AND '2026-06-30' AND metric_time > '2026-01-15'"),
                         (None, d(2026, 2, 1), d(2026, 6, 30)))


class TestParenthesizedRange(unittest.TestCase):
    def test_range_group_leaves_exactly_the_other_filter(self):
        self.assertEqual(
            extract("(metric_time >= '2026-01-01' AND metric_time < '2026-02-01') AND channel = 'X'"),
            ("channel = 'X'", d(2026, 1, 1), d(2026, 1, 31)))
        self.assertEqual(
            extract(f"({TD} >= '2026-01-01' AND {TD} < '2026-02-01') AND {CHANNEL} = 'X'"),
            (f"{CHANNEL} = 'X'", d(2026, 1, 1), d(2026, 1, 31)))

    def test_range_group_after_the_other_filter(self):
        self.assertEqual(extract("channel = 'X' AND (metric_time BETWEEN '2026-01-01' AND '2026-01-31')"),
                         ("channel = 'X'", d(2026, 1, 1), d(2026, 1, 31)))

    def test_range_group_after_an_or_group(self):
        self.assertEqual(extract("(channel = 'A' OR channel = 'B') AND (metric_time <= '2026-01-31')"),
                         ("(channel = 'A' OR channel = 'B')", None, d(2026, 1, 31)))

    def test_range_group_alone(self):
        self.assertEqual(extract("((metric_time >= '2026-01-01') AND (metric_time <= '2026-01-31'))"),
                         (None, d(2026, 1, 1), d(2026, 1, 31)))

    def test_group_mixing_time_and_other_filters(self):
        self.assertEqual(extract("(channel = 'X' AND metric_time >= '2026-01-01') AND region = 'y'"),
                         ("(channel = 'X') AND region = 'y'", d(2026, 1, 1), None))


class TestNotIsRejected(unittest.TestCase):
    """NOT directly before a metric_time condition, or before the "(" of a group enclosing it.

    The time constraint is one inclusive range and cannot be negated; extracting the condition anyway
    would leave the NOT on the next filter (or bare) and return silently wrong numbers.
    """

    def assert_rejected(self, where):
        with self.assertRaises(ValueError) as caught:
            extract(where)
        message = str(caught.exception)
        self.assertTrue(message.startswith(NOT_MESSAGE), message)
        for hint in ("one query_metric call per range", "before and one for the period after"):
            self.assertIn(hint, message)

    def test_not_around_a_range_before_another_filter(self):
        # Was ("NOT channel = 'A'", 2026-01-01, None): the NOT moved onto channel, the range was kept.
        self.assert_rejected("NOT (metric_time >= '2026-01-01') AND channel = 'A'")

    def test_not_around_a_range_between_other_filters(self):
        # Was ("channel = 'A' AND NOT region = 'x'", 2026-01-01, 2026-01-31).
        self.assert_rejected(
            "channel = 'A' AND NOT (metric_time BETWEEN '2026-01-01' AND '2026-01-31') AND region = 'x'")

    def test_lone_not_around_a_range(self):
        self.assert_rejected("NOT (metric_time >= '2026-01-01')")
        self.assert_rejected("not(metric_time between '2026-01-01' and '2026-01-31')")
        self.assert_rejected("NOT ((metric_time >= '2026-01-01'))")

    def test_not_without_parentheses(self):
        self.assert_rejected("NOT metric_time >= '2026-01-01'")
        self.assert_rejected("NOT metric_time <= '2026-01-01'")  # was ("NOT", None, 2026-01-01)
        self.assert_rejected(f"{CHANNEL} = 'A' AND NOT {TD} >= '2026-01-01'")
        self.assert_rejected("metric_time <= '2026-12-31' AND NOT metric_time__day >= '2026-06-01'")

    def test_not_around_a_group_with_the_range_and_another_filter(self):
        self.assert_rejected("NOT (metric_time >= '2026-01-01' AND channel = 'A')")
        # Any enclosing group counts, not only the innermost one.
        self.assert_rejected("region = 'x' AND NOT (channel = 'A' AND (metric_time >= '2026-01-01'))")

    def test_not_on_a_sibling_filter_is_kept(self):
        self.assertEqual(extract("metric_time >= '2026-01-01' AND NOT channel = 'A'"),
                         ("NOT channel = 'A'", d(2026, 1, 1), None))
        self.assertEqual(extract("NOT channel = 'A' AND metric_time >= '2026-01-01'"),
                         ("NOT channel = 'A'", d(2026, 1, 1), None))
        self.assertEqual(extract("channel IS NOT NULL AND metric_time >= '2026-01-01'"),
                         ("channel IS NOT NULL", d(2026, 1, 1), None))

    def test_not_inside_a_literal_is_not_a_not(self):
        self.assertEqual(extract("label = 'NOT (' AND metric_time >= '2026-01-01'"),
                         ("label = 'NOT ('", d(2026, 1, 1), None))
        self.assertEqual(extract('label = "NOT (" AND metric_time >= \'2026-01-01\''),
                         ('label = "NOT ("', d(2026, 1, 1), None))

    def test_not_in_a_group_that_does_not_enclose_the_range_is_kept(self):
        self.assertEqual(extract("NOT (channel = 'A') AND metric_time >= '2026-01-01'"),
                         ("NOT (channel = 'A')", d(2026, 1, 1), None))
        self.assertEqual(extract("(NOT channel = 'A') AND metric_time >= '2026-01-01'"),
                         ("(NOT channel = 'A')", d(2026, 1, 1), None))
        self.assertEqual(extract("metric_time >= '2026-01-01' AND (region = 'x' AND NOT channel = 'A')"),
                         ("(region = 'x' AND NOT channel = 'A')", d(2026, 1, 1), None))


class TestMetricTimeIsAWholeWord(unittest.TestCase):
    def test_a_name_ending_in_metric_time_stays_in_where(self):
        for where in ("first_metric_time >= '2026-01-01' AND channel = 'X'",
                      "first_metric_time__day <= '2026-01-31'",
                      "NOT first_metric_time >= '2026-01-01'"):
            with self.subTest(where=where):
                self.assertEqual(extract(where), (where, None, None))

    def test_next_to_a_metric_time_condition(self):
        self.assertEqual(extract("first_metric_time >= '2026-01-01' AND metric_time >= '2026-02-01'"),
                         ("first_metric_time >= '2026-01-01'", d(2026, 2, 1), None))


class _FakeEngineCompiler(MetricFlowCompiler):
    """Engine mode without a manifest: compile() gets as far as _extract_time_constraints."""

    def __init__(self):  # noqa: D107 - no dbt project
        self._engine, self._engine_mode, self._init_error = object(), True, ""


class _NoPool:
    async def execute(self, *args, **kwargs):
        raise AssertionError("the pool must not be used when compile fails")


class TestOrSurfacesAsCompileError(unittest.IsolatedAsyncioTestCase):
    def test_compile_returns_the_message(self):
        for having in (None, "gmv > 0"):
            with self.subTest(having=having):
                sql, command, error = _FakeEngineCompiler().compile(["gmv"], ["metric_time__year"], OR_RANGES,
                                                                    having=having)
                self.assertIsNone(sql)
                self.assertTrue(command.startswith("mf query --metrics gmv"), command)
                self.assertTrue(error.startswith(OR_MESSAGE), error)

    async def test_query_metric_returns_internal_error(self):
        body = json.loads(await query_metric(_FakeEngineCompiler(), _NoPool(), ["gmv"], ["metric_time__year"],
                                             OR_RANGES))
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "INTERNAL_ERROR")
        self.assertTrue(body["error"]["message"].startswith(f"MetricFlow compile error: {OR_MESSAGE}"),
                        body["error"]["message"])


class TestNotSurfacesAsCompileError(unittest.IsolatedAsyncioTestCase):
    async def test_query_metric_returns_internal_error_for_not(self):
        body = json.loads(await query_metric(_FakeEngineCompiler(), _NoPool(), ["gmv"], ["metric_time__day"],
                                             "NOT (metric_time >= '2026-01-01') AND channel = 'A'"))
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "INTERNAL_ERROR")
        self.assertTrue(body["error"]["message"].startswith(f"MetricFlow compile error: {NOT_MESSAGE}"),
                        body["error"]["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
