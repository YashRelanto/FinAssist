"""
graph/graph.py
==============
Assembles, compiles, and exports the FinAssist v2 LangGraph StateGraph.
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END

from app.graph.state import AgentState
from app.graph.nodes import (
    input_guardrail_node,
    intent_node,
    context_node,
    entity_node,
    semantic_node,
    clarification_node,
    router_node,
    goal_planning_node,
    workflow_relevance_node,
    rag_node,
    analytics_node,
    answer_node,
    output_guardrail_node,
)
from app.graph.agents import (
    transaction_agent,
    comparison_agent,
    trend_agent,
    anomaly_agent,
)
from app.graph.sql import (
    sql_planner,
    sql_validator,
    sql_executor,
)
from app.graph.edges import (
    route_after_input_guardrail,
    route_after_intent,
    route_after_workflow_relevance,
    route_after_goal_planning,
    route_after_clarification,
    route_after_router,
    route_after_sql_validator,
)
from app.graph.checkpointer import get_checkpointer
from app.graph.logging_utils import wrap_graph_node

logger = logging.getLogger(__name__)

_w = wrap_graph_node


def build_graph():
    """
    Builds the FinAssist LangGraph StateGraph.
    """
    builder = StateGraph(AgentState)

    # ── 1. Register Core Nodes ──────────────────────────────────────────
    builder.add_node("input_guardrail", _w("input_guardrail", input_guardrail_node))
    builder.add_node("intent_node", _w("intent_node", intent_node))
    builder.add_node("context_node", _w("context_node", context_node))
    builder.add_node("entity_node", _w("entity_node", entity_node))
    builder.add_node("semantic_node", _w("semantic_node", semantic_node))
    builder.add_node("clarification_node", _w("clarification_node", clarification_node))
    builder.add_node("router_node", _w("router_node", router_node))
    builder.add_node("goal_planning_node", _w("goal_planning_node", goal_planning_node))
    builder.add_node("workflow_relevance_node", _w("workflow_relevance_node", workflow_relevance_node))
    builder.add_node("rag_node", _w("rag_node", rag_node))
    builder.add_node("analytics_node", _w("analytics_node", analytics_node))
    builder.add_node("answer_node", _w("answer_node", answer_node))
    builder.add_node("output_guardrail", _w("output_guardrail", output_guardrail_node))

    # ── 2. Register Specialized Agent Nodes ─────────────────────────────
    builder.add_node("transaction_agent", _w("transaction_agent", transaction_agent))
    builder.add_node("comparison_agent", _w("comparison_agent", comparison_agent))
    builder.add_node("trend_agent", _w("trend_agent", trend_agent))
    builder.add_node("anomaly_agent", _w("anomaly_agent", anomaly_agent))

    # ── 3. Register SQL Pipeline Nodes ──────────────────────────────────
    builder.add_node("sql_planner", _w("sql_planner", sql_planner))
    builder.add_node("sql_validator", _w("sql_validator", sql_validator))
    builder.add_node("sql_executor", _w("sql_executor", sql_executor))

    # ── 4. Set entry edge ───────────────────────────────────────────────
    builder.add_edge(START, "input_guardrail")

    # ── 5. Setup Conditional / Routing Edges ───────────────────────────
    builder.add_conditional_edges(
        "input_guardrail",
        route_after_input_guardrail,
        {
            "intent_node": "intent_node",
            "__end__": END,
        },
    )

    builder.add_conditional_edges(
        "intent_node",
        route_after_intent,
        {
            "context_node": "context_node",
            "workflow_relevance_node": "workflow_relevance_node",
            "goal_planning_node": "goal_planning_node",
            "__end__": END,
        },
    )

    builder.add_conditional_edges(
        "workflow_relevance_node",
        route_after_workflow_relevance,
        {
            "goal_planning_node": "goal_planning_node",
            "context_node": "context_node",
        },
    )

    builder.add_conditional_edges(
        "goal_planning_node",
        route_after_goal_planning,
        {
            "answer_node": "answer_node",
            "__end__": END,
        },
    )

    builder.add_conditional_edges(
        "clarification_node",
        route_after_clarification,
        {
            "router_node": "router_node",
            "__end__": END,
        },
    )

    builder.add_conditional_edges(
        "router_node",
        route_after_router,
        {
            "transaction_agent": "transaction_agent",
            "comparison_agent": "comparison_agent",
            "trend_agent": "trend_agent",
            "anomaly_agent": "anomaly_agent",
            "rag_node": "rag_node",
        },
    )

    builder.add_conditional_edges(
        "sql_validator",
        route_after_sql_validator,
        {
            "sql_executor": "sql_executor",
            "answer_node": "answer_node",
        },
    )

    # ── 6. Fixed Edges ──────────────────────────────────────────────────
    builder.add_edge("context_node", "entity_node")
    builder.add_edge("entity_node", "semantic_node")
    builder.add_edge("semantic_node", "clarification_node")

    # Connect agents to SQL pipeline
    builder.add_edge("transaction_agent", "sql_planner")
    builder.add_edge("comparison_agent", "sql_planner")
    builder.add_edge("trend_agent", "sql_planner")
    builder.add_edge("anomaly_agent", "sql_planner")

    builder.add_edge("sql_planner", "sql_validator")
    builder.add_edge("sql_executor", "analytics_node")
    builder.add_edge("analytics_node", "answer_node")

    # Connect RAG path to answer
    builder.add_edge("rag_node", "answer_node")

    # End path
    builder.add_edge("answer_node", "output_guardrail")
    builder.add_edge("output_guardrail", END)

    # ── 7. Compile with checkpointer ────────────────────────────────────
    checkpointer = get_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("[Graph] FinAssist LangGraph v2 compiled successfully")
    return graph


# Singleton instance used by routes/chatbot.py
finassist_graph = build_graph()
