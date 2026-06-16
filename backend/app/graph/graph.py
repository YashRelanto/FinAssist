"""
graph/graph.py
==============
Assembles, compiles, and exports the FinAssist Brain-Centric LangGraph StateGraph.
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
    investment_analysis_agent,
)
from app.graph.sql import (
    sql_planner,
    sql_validator,
    sql_executor,
)
from app.graph.edges import (
    route_after_input_guardrail,
    route_after_intent,
    route_after_clarification,
)
from app.graph.checkpointer import get_checkpointer
from app.graph.logging_utils import wrap_graph_node

logger = logging.getLogger(__name__)

_w = wrap_graph_node


def build_graph():
    """
    Builds the FinAssist Brain-Centric LangGraph StateGraph.

    Flow:
      Input Guardrails → Intent → Context → Clarification → Entity → Semantic
      → Brain Orchestrator → Tool Execution → Brain Aggregation → Answer → Output Guardrails
    """
    builder = StateGraph(AgentState)

    # ── Core pipeline nodes ─────────────────────────────────────────────
    builder.add_node("input_guardrail", _w("input_guardrail", input_guardrail_node))
    builder.add_node("intent_node", _w("intent_node", intent_node))
    builder.add_node("context_node", _w("context_node", context_node))
    builder.add_node("clarification_node", _w("clarification_node", clarification_node))
    builder.add_node("entity_node", _w("entity_node", entity_node))
    builder.add_node("semantic_node", _w("semantic_node", semantic_node))
    builder.add_node("clarification_node", _w("clarification_node", clarification_node))
    builder.add_node("router_node", _w("router_node", router_node))
    builder.add_node("rag_node", _w("rag_node", rag_node))
    builder.add_node("analytics_node", _w("analytics_node", analytics_node))
    builder.add_node("answer_node", _w("answer_node", answer_node))
    builder.add_node("output_guardrail", _w("output_guardrail", output_guardrail_node))

    # ── 2. Register Specialized Agent Nodes ─────────────────────────────
    builder.add_node("transaction_agent", _w("transaction_agent", transaction_agent))
    builder.add_node("comparison_agent", _w("comparison_agent", comparison_agent))
    builder.add_node("trend_agent", _w("trend_agent", trend_agent))
    builder.add_node("anomaly_agent", _w("anomaly_agent", anomaly_agent))
    builder.add_node("investment_analysis_agent", _w("investment_analysis_agent", investment_analysis_agent))

    # ── 3. Register SQL Pipeline Nodes ──────────────────────────────────
    builder.add_node("sql_planner", _w("sql_planner", sql_planner))
    builder.add_node("sql_validator", _w("sql_validator", sql_validator))
    builder.add_node("sql_executor", _w("sql_executor", sql_executor))

    # ── 4. Set entry edge ───────────────────────────────────────────────
    builder.add_edge(START, "input_guardrail")

    # ── Conditional routing ─────────────────────────────────────────────
    builder.add_conditional_edges(
        "input_guardrail",
        route_after_input_guardrail,
        {"intent_node": "intent_node", "output_guardrail": "output_guardrail"},
    )

    builder.add_conditional_edges(
        "intent_node",
        route_after_intent,
        {
            "context_node": "context_node",
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
            "investment_analysis_agent": "investment_analysis_agent",
            "rag_node": "rag_node",
        },
    )

    # ── Brain-centric linear flow ───────────────────────────────────────
    builder.add_edge("context_node", "clarification_node")
    builder.add_edge("entity_node", "semantic_node")
    builder.add_edge("semantic_node", "clarification_node")

    # Connect agents to SQL pipeline
    builder.add_edge("transaction_agent", "sql_planner")
    builder.add_edge("comparison_agent", "sql_planner")
    builder.add_edge("trend_agent", "sql_planner")
    builder.add_edge("anomaly_agent", "sql_planner")
    builder.add_edge("investment_analysis_agent", "output_guardrail")

    builder.add_edge("sql_planner", "sql_validator")
    builder.add_edge("sql_executor", "analytics_node")
    builder.add_edge("analytics_node", "answer_node")

    # Connect RAG path to answer
    builder.add_edge("rag_node", "answer_node")

    # End path
    builder.add_edge("answer_node", "output_guardrail")
    builder.add_edge("output_guardrail", END)

    checkpointer = get_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("[Graph] FinAssist Brain-Centric LangGraph compiled successfully")
    return graph


finassist_graph = build_graph()
