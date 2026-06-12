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
    brain_orchestrator_node,
    tool_execution_node,
    brain_aggregation_node,
    goal_planning_node,
    workflow_relevance_node,
    answer_node,
    output_guardrail_node,
)
from app.graph.edges import (
    route_after_input_guardrail,
    route_after_intent,
    route_after_workflow_relevance,
    route_after_goal_planning,
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
    builder.add_node("brain_orchestrator", _w("brain_orchestrator", brain_orchestrator_node))
    builder.add_node("tool_execution", _w("tool_execution", tool_execution_node))
    builder.add_node("brain_aggregation", _w("brain_aggregation", brain_aggregation_node))
    builder.add_node("goal_planning_node", _w("goal_planning_node", goal_planning_node))
    builder.add_node("workflow_relevance_node", _w("workflow_relevance_node", workflow_relevance_node))
    builder.add_node("answer_node", _w("answer_node", answer_node))
    builder.add_node("output_guardrail", _w("output_guardrail", output_guardrail_node))

    # ── Entry ───────────────────────────────────────────────────────────
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
            "workflow_relevance_node": "workflow_relevance_node",
            "goal_planning_node": "goal_planning_node",
            "output_guardrail": "output_guardrail",
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
        {"answer_node": "answer_node", "output_guardrail": "output_guardrail"},
    )

    builder.add_conditional_edges(
        "clarification_node",
        route_after_clarification,
        {
            "entity_node": "entity_node",
            "output_guardrail": "output_guardrail",
        },
    )

    # ── Brain-centric linear flow ───────────────────────────────────────
    builder.add_edge("context_node", "clarification_node")
    builder.add_edge("entity_node", "semantic_node")
    builder.add_edge("semantic_node", "brain_orchestrator")
    builder.add_edge("brain_orchestrator", "tool_execution")
    builder.add_edge("tool_execution", "brain_aggregation")
    builder.add_edge("brain_aggregation", "answer_node")
    builder.add_edge("answer_node", "output_guardrail")
    builder.add_edge("output_guardrail", END)

    checkpointer = get_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("[Graph] FinAssist Brain-Centric LangGraph compiled successfully")
    return graph


finassist_graph = build_graph()
