"""
graph/graph.py
==============
Assembles, compiles, and exports the FinAssist Brain (Supervisor) StateGraph.

Flow:  input_guardrail → brain ⇄ {nl2sql | goal_planner | investment | knowledge}
       → (brain finishes) → answer_node → output_guardrail → END

The Brain loops over tools, accumulating `evidence`, until it has enough to finish.
Clarification is handled inside the Brain via `interrupt` (HITL pause/resume).
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END

from app.graph.state import AgentState
from app.graph.nodes import (
    input_guardrail_node,
    output_guardrail_node,
    analytics_node,
    answer_node,
)
from app.graph.brain import brain_node
from app.graph.tools import (
    nl2sql_agent,
    goal_planner_tool,
    investment_tool,
    knowledge_tool,
)
from app.graph.sql import sql_planner, sql_validator, sql_executor
from app.graph.edges import (
    route_after_input_guardrail,
    route_after_brain,
    route_after_sql_validator,
)
from app.graph.checkpointer import get_checkpointer
from app.graph.logging_utils import wrap_graph_node

logger = logging.getLogger(__name__)

_w = wrap_graph_node


def build_graph():
    """Builds the FinAssist supervisor StateGraph."""
    builder = StateGraph(AgentState)

    # ── 1. Nodes ─────────────────────────────────────────────────────────
    builder.add_node("input_guardrail", _w("input_guardrail", input_guardrail_node))
    builder.add_node("brain", _w("brain", brain_node))

    # Tools
    builder.add_node("nl2sql_agent", _w("nl2sql_agent", nl2sql_agent))
    builder.add_node("goal_planner_tool", _w("goal_planner_tool", goal_planner_tool))
    builder.add_node("investment_tool", _w("investment_tool", investment_tool))
    builder.add_node("knowledge_tool", _w("knowledge_tool", knowledge_tool))

    # Reused SQL pipeline (fed by nl2sql_agent)
    builder.add_node("sql_planner", _w("sql_planner", sql_planner))
    builder.add_node("sql_validator", _w("sql_validator", sql_validator))
    builder.add_node("sql_executor", _w("sql_executor", sql_executor))
    builder.add_node("analytics_node", _w("analytics_node", analytics_node))

    # Synthesis + output
    builder.add_node("answer_node", _w("answer_node", answer_node))
    builder.add_node("output_guardrail", _w("output_guardrail", output_guardrail_node))

    # ── 2. Entry ─────────────────────────────────────────────────────────
    builder.add_edge(START, "input_guardrail")

    # ── 3. Routing ───────────────────────────────────────────────────────
    builder.add_conditional_edges(
        "input_guardrail",
        route_after_input_guardrail,
        {"brain": "brain", "__end__": END},
    )

    builder.add_conditional_edges(
        "brain",
        route_after_brain,
        {
            "nl2sql_agent": "nl2sql_agent",
            "goal_planner_tool": "goal_planner_tool",
            "investment_tool": "investment_tool",
            "knowledge_tool": "knowledge_tool",
            "answer_node": "answer_node",
            "__end__": END,
        },
    )

    builder.add_conditional_edges(
        "sql_validator",
        route_after_sql_validator,
        {"sql_executor": "sql_executor", "brain": "brain"},
    )

    # ── 4. NL2SQL chain ──────────────────────────────────────────────────
    builder.add_edge("nl2sql_agent", "sql_planner")
    builder.add_edge("sql_planner", "sql_validator")
    builder.add_edge("sql_executor", "analytics_node")
    builder.add_edge("analytics_node", "brain")     # evidence collected → back to Brain

    # ── 5. Other tools return to the Brain ───────────────────────────────
    builder.add_edge("goal_planner_tool", "brain")
    builder.add_edge("investment_tool", "brain")
    builder.add_edge("knowledge_tool", "brain")

    # ── 6. Finish path ───────────────────────────────────────────────────
    builder.add_edge("answer_node", "output_guardrail")
    builder.add_edge("output_guardrail", END)

    # ── 7. Compile ───────────────────────────────────────────────────────
    checkpointer = get_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("[Graph] FinAssist Supervisor graph compiled successfully")
    return graph


# Singleton instance used by routes/chatbot.py
finassist_graph = build_graph()
