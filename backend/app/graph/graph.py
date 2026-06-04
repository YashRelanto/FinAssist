"""
graph/graph.py
==============
Assembles, compiles, and exports the FinAssist LangGraph StateGraph.

Graph topology (matches the implementation plan exactly):

  START
    └──→ input_guardrail
              ├── BLOCKED ──────────────────────────────────────────→ END
              └── SAFE ──→ domain_scope
                                ├── OUT_OF_SCOPE ──────────────────→ END
                                └── IN_SCOPE ──→ intent_classifier
                                                      ├── CLARIFICATION ────→ END
                                                      └── ROUTABLE ──→ intent_router
                                                                            │
                                      ┌───────────────────────────┬─────────┴──────────────────────────┐
                                      ▼                           ▼                                    ▼
                                  nl2sql                workflow_relevance                      workflow_slot (new)
                                      │                       │         │                           │
                                      │              workflow_slot  intent_router               advisor
                                      │                   │                │                       │
                                      │              advisor/END       rag_retrieval           output_guardrail
                                      │                   │                │                       │
                                      │           output_guardrail    advisor ─(failsafe)→ nl2sql  │
                                      │                   │                │                       │
                                      └───────────────────┴────────────────┴───────────────────────┘
                                                                          END

A module-level singleton `finassist_graph` is exported for use by the chatbot route.
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END

from app.graph.state import FinAssistState
from app.graph.nodes import (
    input_guardrail_node,
    domain_scope_node,
    intent_classifier_node,
    intent_router_node,
    nl2sql_node,
    workflow_relevance_node,
    rag_retrieval_node,
    workflow_slot_node,
    advisor_node,
    output_guardrail_node,
)
from app.graph.edges import (
    route_after_input_guard,
    route_after_domain_scope,
    route_after_intent_classifier,
    route_after_intent_router,
    route_after_workflow_relevance,
    route_after_workflow_slot,
    route_after_advisor,
)
from app.graph.checkpointer import get_checkpointer

logger = logging.getLogger(__name__)


def build_graph():
    """
    Builds and compiles the FinAssist LangGraph StateGraph.

    Returns the compiled graph with a checkpointer attached.
    The checkpointer provides per-thread state persistence (conversation
    history + HITL workflow state) replacing the old sessions.json file.
    """
    builder = StateGraph(FinAssistState)

    # ── Register nodes ────────────────────────────────────────────────────
    builder.add_node("input_guardrail",    input_guardrail_node)
    builder.add_node("domain_scope",       domain_scope_node)
    builder.add_node("intent_classifier",  intent_classifier_node)
    builder.add_node("intent_router",      intent_router_node)
    builder.add_node("nl2sql",             nl2sql_node)
    builder.add_node("workflow_relevance", workflow_relevance_node)
    builder.add_node("rag_retrieval",      rag_retrieval_node)
    builder.add_node("workflow_slot",      workflow_slot_node)
    builder.add_node("advisor",            advisor_node)
    builder.add_node("output_guardrail",   output_guardrail_node)

    # ── Entry edge ────────────────────────────────────────────────────────
    builder.add_edge(START, "input_guardrail")

    # ── Conditional edges (routing) ───────────────────────────────────────
    builder.add_conditional_edges(
        "input_guardrail",
        route_after_input_guard,
        {"domain_scope": "domain_scope", "__end__": END},
    )
    builder.add_conditional_edges(
        "domain_scope",
        route_after_domain_scope,
        {"intent_classifier": "intent_classifier", "__end__": END},
    )
    builder.add_conditional_edges(
        "intent_classifier",
        route_after_intent_classifier,
        {"intent_router": "intent_router", "__end__": END},
    )
    builder.add_conditional_edges(
        "intent_router",
        route_after_intent_router,
        {
            "nl2sql":              "nl2sql",
            "workflow_relevance":  "workflow_relevance",
            "rag_retrieval":       "rag_retrieval",
            "workflow_slot":       "workflow_slot",
        },
    )
    builder.add_conditional_edges(
        "workflow_relevance",
        route_after_workflow_relevance,
        {"workflow_slot": "workflow_slot", "intent_router": "intent_router"},
    )
    builder.add_conditional_edges(
        "workflow_slot",
        route_after_workflow_slot,
        {"advisor": "advisor", "__end__": END},
    )
    builder.add_conditional_edges(
        "advisor",
        route_after_advisor,
        {"nl2sql": "nl2sql", "output_guardrail": "output_guardrail"},
    )

    # ── Fixed edges ───────────────────────────────────────────────────────
    builder.add_edge("nl2sql",          "output_guardrail")
    builder.add_edge("rag_retrieval",   "advisor")
    builder.add_edge("output_guardrail", END)

    # ── Compile with checkpointer ─────────────────────────────────────────
    checkpointer = get_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("[Graph] FinAssist LangGraph compiled successfully")
    return graph


# ── Module-level singleton ────────────────────────────────────────────────────
# Instantiated once when the module is first imported.
# The FastAPI chatbot route imports this directly:
#   from app.graph.graph import finassist_graph
finassist_graph = build_graph()
