"""Tests for relative date resolution and time context."""

from __future__ import annotations

import unittest
from datetime import date

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


if __name__ == "__main__":
    unittest.main()
