"""
Unit tests for tool runner multi-agent isolation.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.graph.state import make_initial_state
from app.graph.tools.tool_runner import _sql_query_to_str, execute_tool_plan


class TestToolRunner(unittest.TestCase):

    def test_sql_query_to_str_handles_comparison_dict(self):
        dual = {"query_a": "SELECT 1", "query_b": "SELECT 2"}
        self.assertEqual(_sql_query_to_str(dual), "SELECT 1; SELECT 2")
        self.assertEqual(_sql_query_to_str("SELECT 3"), "SELECT 3")

    @patch("app.graph.tools.tool_runner._execute_agent_tool")
    def test_comparison_agent_sql_query_join(self, mock_agent):
        mock_agent.return_value = {
            "agent": "comparison",
            "sql_query": {"query_a": "SELECT a", "query_b": "SELECT b"},
            "sql_results": [],
            "analytics_results": {"status": "no_data"},
        }
        state = make_initial_state("u1", "s1", "compare spendings", {})
        plan = {"tools": [{"tool": "agent_layer", "agent": "comparison_agent", "args": {}}]}
        result = execute_tool_plan(state, plan)
        self.assertEqual(result["sql_query"], "SELECT a; SELECT b")
        self.assertEqual(result["tool_errors"], [])

    @patch("app.graph.tools.tool_runner._execute_rag_tool")
    @patch("app.graph.tools.tool_runner._execute_agent_tool")
    def test_multi_agent_accumulates_results(self, mock_agent, mock_rag):
        mock_rag.return_value = {"documents": ["doc1"], "sources": ["KB"]}
        mock_agent.side_effect = [
            {"agent": "trend", "sql_results": [{"amount": 100}], "analytics_results": {"trend": "up"}},
            {"agent": "transaction", "sql_results": [{"amount": 50}], "analytics_results": {"total": 50}},
        ]
        state = make_initial_state("u1", "s1", "hybrid query", {})
        plan = {
            "tools": [
                {"tool": "rag", "args": {"query": "inflation"}},
                {"tool": "agent_layer", "agent": "trend_agent", "args": {}},
                {"tool": "agent_layer", "agent": "transaction_agent", "args": {}},
            ]
        }
        result = execute_tool_plan(state, plan)
        self.assertEqual(len(result["agent_results"]), 2)
        self.assertEqual(len(result["sql_results"]), 2)
        self.assertIn("trend", result["analytics_results"].get("agents", {}))


if __name__ == "__main__":
    unittest.main()
