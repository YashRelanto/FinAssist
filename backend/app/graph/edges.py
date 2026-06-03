"""
graph/edges.py
==============
All conditional edge router functions for the FinAssist LangGraph pipeline.

Each router:
  - Receives the current FinAssistState
  - Returns a string that names the NEXT NODE (or "__end__")
  - Contains zero business logic — only reads state fields set by nodes

Router inventory:
  route_after_input_guard       → "domain_scope"     | "__end__"
  route_after_domain_scope      → "intent_classifier" | "__end__"
  route_after_intent_classifier → "intent_router"     | "__end__"
  route_after_intent_router     → "nl2sql" | "workflow_relevance" | "rag_retrieval"
  route_after_workflow_relevance→ "workflow_slot" | "intent_router"
  route_after_workflow_slot     → "advisor" | "__end__"
  route_after_advisor           → "nl2sql" | "output_guardrail"
"""

from __future__ import annotations

import logging
from typing import Literal

from app.graph.state import FinAssistState

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────

def route_after_input_guard(
    state: FinAssistState,
) -> Literal["domain_scope", "__end__"]:
    """
    If input was blocked → END (final_answer already set by input_guardrail_node).
    Otherwise → proceed to domain scope validation.
    """
    if state.get("input_blocked"):
        logger.debug("[Edge] input_guard → __end__ (blocked)")
        return "__end__"
    logger.debug("[Edge] input_guard → domain_scope")
    return "domain_scope"


# ─────────────────────────────────────────────────────────────────────────────

def route_after_domain_scope(
    state: FinAssistState,
) -> Literal["intent_classifier", "__end__"]:
    """
    If domain is out-of-scope → END (final_answer already set by domain_scope_node).
    Otherwise → proceed to intent classification.
    """
    if not state.get("domain_supported", True):
        logger.debug("[Edge] domain_scope → __end__ (out_of_scope)")
        return "__end__"
    logger.debug("[Edge] domain_scope → intent_classifier")
    return "intent_classifier"


# ─────────────────────────────────────────────────────────────────────────────

def route_after_intent_classifier(
    state: FinAssistState,
) -> Literal["intent_router", "__end__"]:
    """
    If multi-intent resolution required clarification → END
    (the clarification question is in final_answer).
    Otherwise → proceed to intent routing.
    """
    if state.get("multi_intent_type") == "clarification_required":
        logger.debug("[Edge] intent_classifier → __end__ (clarification_required)")
        return "__end__"
    logger.debug("[Edge] intent_classifier → intent_router")
    return "intent_router"


# ─────────────────────────────────────────────────────────────────────────────

def route_after_intent_router(
    state: FinAssistState,
) -> Literal["nl2sql", "workflow_relevance", "rag_retrieval"]:
    """
    Routes the request to the correct specialised node based on:
      1. selected_intent
      2. workflow_active flag (is a HITL workflow already in progress?)

    Decision matrix:
      personal_transaction                       → nl2sql
      financial_goal_planning + workflow_active  → workflow_relevance (check continuity)
      financial_goal_planning + no active workflow → rag_retrieval (start slot filling fresh — workflow_slot_node handles init)
      financial_knowledge                        → rag_retrieval

    NOTE: When intent=financial_goal_planning and workflow is NOT active, we route to
    rag_retrieval first, then advisor_node triggers WorkflowAgent.process() which will
    initialise a new workflow state.  Alternatively we can route directly to workflow_slot_node.
    We route to workflow_slot_node directly to avoid an unnecessary RAG call for goal planning.
    """
    intent          = state.get("selected_intent", "financial_knowledge")
    workflow_active = state.get("workflow_active", False)

    if intent == "personal_transaction":
        logger.debug("[Edge] intent_router → nl2sql")
        return "nl2sql"

    if intent == "financial_goal_planning":
        if workflow_active:
            logger.debug("[Edge] intent_router → workflow_relevance (active workflow)")
            return "workflow_relevance"
        else:
            # New goal planning request — go directly to slot filling
            logger.debug("[Edge] intent_router → workflow_slot (new workflow)")
            return "workflow_slot"

    # Default: financial_knowledge (and any unexpected intent)
    logger.debug("[Edge] intent_router → rag_retrieval")
    return "rag_retrieval"


# ─────────────────────────────────────────────────────────────────────────────

def route_after_intent_router_goal(
    state: FinAssistState,
) -> Literal["workflow_slot", "rag_retrieval"]:
    """
    Secondary router only used for the financial_goal_planning + no-active-workflow path.
    (Kept separate so the graph topology stays clean and readable.)
    """
    return "workflow_slot"


# ─────────────────────────────────────────────────────────────────────────────

def route_after_workflow_relevance(
    state: FinAssistState,
) -> Literal["workflow_slot", "intent_router"]:
    """
    If the message continues the active workflow → workflow_slot_node (keep filling slots).
    If the user changed topic → route back to intent_router with the paused workflow state.
    The intent_router will then pick the correct branch for the new topic.
    """
    if state.get("workflow_related"):
        logger.debug("[Edge] workflow_relevance → workflow_slot")
        return "workflow_slot"
    logger.debug("[Edge] workflow_relevance → intent_router (topic changed, workflow paused)")
    return "intent_router"


# ─────────────────────────────────────────────────────────────────────────────

def route_after_workflow_slot(
    state: FinAssistState,
) -> Literal["advisor", "__end__"]:
    """
    If workflow_slot_node set final_answer (= still collecting slots) → END.
    If all slots collected (advisor_ready) → advisor_node for final plan generation.
    """
    if state.get("final_answer"):
        logger.debug("[Edge] workflow_slot → __end__ (awaiting clarification)")
        return "__end__"
    logger.debug("[Edge] workflow_slot → advisor (all slots filled)")
    return "advisor"


# ─────────────────────────────────────────────────────────────────────────────

def route_after_advisor(
    state: FinAssistState,
) -> Literal["nl2sql", "output_guardrail"]:
    """
    If AdvisorAgent emitted ROUTE_TO_NL2SQL_TOKEN → reroute to nl2sql_node.
    This is a failsafe: the intent classifier routes to financial_knowledge but
    the LLM detects the question is actually about personal transaction data.
    Otherwise → output_guardrail for PII masking + secret leak check.
    """
    if state.get("route_to_nl2sql"):
        logger.debug("[Edge] advisor → nl2sql (ROUTE_TO_NL2SQL failsafe)")
        return "nl2sql"
    logger.debug("[Edge] advisor → output_guardrail")
    return "output_guardrail"
