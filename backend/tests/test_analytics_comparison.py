"""Tests for comparison analytics with labeled SQL results."""

from __future__ import annotations

import unittest

from app.graph.nodes.analytics_node import analytics_node


class TestAnalyticsComparison(unittest.TestCase):

    def test_labeled_period_comparison(self):
        state = {
            "sql_results": [
                {"amount": 100.0, "comparison_target": "target_a"},
                {"amount": 50.0, "comparison_target": "target_a"},
                {"amount": 80.0, "comparison_target": "target_b"},
            ],
            "selected_agent": "comparison",
            "resolved_entities": {"comparison": {"targets": ["last_two_months"]}},
        }
        result = analytics_node(state)
        comparison = result["analytics_results"]["comparison"]
        self.assertEqual(comparison["target_a_total"], 150.0)
        self.assertEqual(comparison["target_b_total"], 80.0)
        self.assertEqual(comparison["difference"], 70.0)


if __name__ == "__main__":
    unittest.main()
