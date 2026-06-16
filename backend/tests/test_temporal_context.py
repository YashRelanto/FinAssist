"""Tests for relative date resolution and time context."""

from __future__ import annotations

import unittest
from datetime import date

from app.graph.nodes.entity_node import _resolve_dates
from app.graph.sql.date_filters import apply_entity_date_filters
from app.utils.temporal_context import (
    resolve_last_n_calendar_months,
    resolve_period_token,
    resolve_relative_dates_from_query,
)


class TestTemporalContext(unittest.TestCase):

    def test_last_two_calendar_months_from_june(self):
        start, end = resolve_last_n_calendar_months(2, reference=date(2026, 6, 15))
        self.assertEqual(start, "2026-04-01")
        self.assertEqual(end, "2026-05-31")

    def test_resolve_relative_query_last_two_months(self):
        result = resolve_relative_dates_from_query(
            "analyse my spendings for last two months from now",
            reference=date(2026, 6, 15),
        )
        self.assertEqual(result["from"], "2026-04-01")
        self.assertEqual(result["to"], "2026-05-31")

    def test_resolve_period_token_last_two_months(self):
        result = resolve_period_token("last_two_months", reference=date(2026, 6, 15))
        self.assertEqual(result["from"], "2026-04-01")
        self.assertEqual(result["to"], "2026-05-31")

    def test_entity_resolver_last_2_months(self):
        result = _resolve_dates("analyse my last 2 months spending")
        # Uses live date.today(); at least verify shape
        self.assertIsNotNone(result["from"])
        self.assertIsNotNone(result["to"])
        self.assertLess(result["from"], result["to"])

    def test_apply_entity_date_filters(self):
        ast = {
            "operation": "SELECT",
            "tables": ["transactions"],
            "filters": [
                {"column": "transactions.user_id", "op": "=", "value": "{{user_id}}"},
            ],
        }
        entities = {"date_range": {"from": "2026-04-01", "to": "2026-05-31"}}
        patched = apply_entity_date_filters(ast, entities)
        cols = [f["column"] for f in patched["filters"]]
        self.assertIn("transactions.transaction_date", cols)


if __name__ == "__main__":
    unittest.main()
