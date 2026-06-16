"""Tests for BRD intent taxonomy mapping."""

from __future__ import annotations

import unittest

from app.graph.nodes.intent_node import to_brd_intent


class TestIntentMapping(unittest.TestCase):

    def test_maps_internal_to_brd(self):
        self.assertEqual(to_brd_intent("TREND_ANALYSIS"), "trend_analysis")
        self.assertEqual(to_brd_intent("HYBRID_QUERY"), "hybrid_query")
        self.assertEqual(to_brd_intent("INVESTMENT_ANALYSIS"), "investment_analysis")
        self.assertEqual(to_brd_intent("FINANCIAL_KNOWLEDGE"), "financial_guidance")


if __name__ == "__main__":
    unittest.main()
