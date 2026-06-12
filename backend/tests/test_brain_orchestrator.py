"""
Unit tests for Brain-Centric orchestration components.
"""

from __future__ import annotations

import unittest

from app.graph.nodes.brain_orchestrator_node import _fallback_plan
from app.graph.state import make_initial_state


class TestBrainOrchestrator(unittest.TestCase):

    def test_fallback_rag_for_knowledge(self):
        state = make_initial_state(
            user_id="u1",
            session_id="s1",
            user_query="What is SIP?",
            user_profile={},
        )
        state["intent"] = "FINANCIAL_KNOWLEDGE"
        state["standalone_query"] = "What is SIP?"

        plan = _fallback_plan(state)
        self.assertTrue(plan["tools"])
        self.assertEqual(plan["tools"][0]["tool"], "rag")

    def test_fallback_hybrid_for_affordability(self):
        state = make_initial_state(
            user_id="u1",
            session_id="s1",
            user_query="Can I buy a 15 lakh car?",
            user_profile={"income": 80000},
        )
        state["intent"] = "HYBRID_QUERY"
        state["semantic_context"] = {
            "analysis_required": ["cashflow", "affordability", "emi_impact"],
            "needs_knowledge": True,
        }

        plan = _fallback_plan(state)
        tool_names = [t["tool"] for t in plan["tools"]]
        self.assertIn("agent_layer", tool_names)
        self.assertIn("rag", tool_names)

    def test_fallback_investment_analysis(self):
        state = make_initial_state(
            user_id="u1",
            session_id="s1",
            user_query="How is my portfolio performing?",
            user_profile={},
        )
        state["intent"] = "INVESTMENT_ANALYSIS"

        plan = _fallback_plan(state)
        self.assertEqual(plan["tools"][0]["tool"], "investment_analysis")


if __name__ == "__main__":
    unittest.main()
