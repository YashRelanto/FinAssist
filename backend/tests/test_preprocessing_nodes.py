"""
Unit tests for preprocessing nodes (context, entity date resolver, clarification options).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.graph.clarification_options import build_clarification_option_sources
from app.graph.nodes.entity_node import _resolve_dates


class TestEntityDateResolver(unittest.TestCase):

    def test_this_month(self):
        result = _resolve_dates("How much did I spend on food this month?")
        self.assertIsNotNone(result["from"])
        self.assertIsNotNone(result["to"])

    def test_quarter(self):
        result = _resolve_dates("spending in Q2 2025")
        self.assertEqual(result["from"], "2025-04-01")
        self.assertEqual(result["to"], "2025-06-30")


class TestClarificationOptions(unittest.TestCase):

    @patch("app.graph.clarification_options._fetch_db_categories")
    @patch("app.graph.clarification_options._fetch_user_merchants")
    def test_build_option_sources(self, mock_merchants, mock_categories):
        mock_categories.return_value = ["Food & Drinks", "Shopping"]
        mock_merchants.return_value = ["Amazon", "Swiggy"]
        state = {
            "user_id": "u1",
            "intent": "INVESTMENT_ANALYSIS",
            "user_profile": {"risk_profile": ""},
        }
        sources = build_clarification_option_sources(state)
        self.assertIn("Food & Drinks", sources["categories"])
        self.assertIn("risk_profile", sources["profile_gaps"])


if __name__ == "__main__":
    unittest.main()
