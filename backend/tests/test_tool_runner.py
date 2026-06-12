"""
Unit tests for tool runner multi-agent isolation.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.graph.state import make_initial_state
from app.graph.tools.tool_runner import execute_tool_plan


class TestToolRunner(unittest.TestCase):

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
