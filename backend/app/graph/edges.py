"""
graph/edges.py
==============
Conditional routing functions for the FinAssist v2 LangGraph pipeline.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.graph.state import AgentState

logger = logging.getLogger("app.graph")


def route_after_input_guardrail(
    state: AgentState,
) -> Literal["intent_node", "output_guardrail"]:
    """
    If the user input was blocked by guardrails -> output_guardrail (PII/safety pass).
    Otherwise -> intent_node.
    """
    if state.get("input_blocked"):
        logger.info("[Edge] input_guardrail -> output_guardrail (blocked)")
        return "output_guardrail"
    logger.info("[Edge] input_guardrail -> intent_node")
    return "intent_node"


def route_after_intent(
    state: AgentState,
) -> Literal["context_node", "workflow_relevance_node", "goal_planning_node", "output_guardrail"]:
    """
    If a goal planning workflow is active -> route directly to workflow_relevance_node
    to check if the reply is a slot value.
    If out of scope -> END.
    If new goal planning intent -> start fresh slot filling.
    Otherwise -> context_node (normal flow).
    """
    workflow_active = state.get("workflow_active", False)
    intent = state.get("intent") or "FINANCIAL_KNOWLEDGE"

    if workflow_active:
        logger.info("[Edge] intent -> workflow_relevance_node (active workflow priority)")
        return "workflow_relevance_node"

    if intent == "OUT_OF_SCOPE":
        logger.info("[Edge] intent -> output_guardrail (out of scope)")
        return "output_guardrail"

    if intent == "GOAL_PLANNING":
        logger.info("[Edge] intent -> goal_planning_node (new)")
        return "goal_planning_node"

    logger.info("[Edge] intent -> context_node")
    return "context_node"


def route_after_workflow_relevance(
    state: AgentState,
) -> Literal["goal_planning_node", "context_node"]:
    """
    If latest message is related to active goal planning -> goal_planning_node.
    If unrelated -> context_node (workflow is paused).
    """
    if state.get("workflow_related", True):
        logger.info("[Edge] workflow_relevance -> goal_planning_node")
        return "goal_planning_node"
    logger.info("[Edge] workflow_relevance -> context_node (workflow paused)")
    return "context_node"


def route_after_goal_planning(
    state: AgentState,
) -> Literal["answer_node", "output_guardrail"]:
    """
    If goal slots are missing (final_answer set to a clarification question) -> output_guardrail.
    Otherwise (all slots filled) -> answer_node to generate the plan.
    """
    if state.get("final_answer"):
        logger.info("[Edge] goal_planning -> output_guardrail (clarification needed)")
        return "output_guardrail"
    logger.info("[Edge] goal_planning -> answer_node (completed)")
    return "answer_node"


def route_after_clarification(
    state: AgentState,
) -> Literal["entity_node", "output_guardrail"]:
    """
    If clarification is needed -> output_guardrail (wait for user reply).
    Otherwise -> entity_node (continue Brain pipeline).
    """
    if state.get("clarification_needed"):
        logger.info("[Edge] clarification -> output_guardrail (needs clarification)")
        return "output_guardrail"
    logger.info("[Edge] clarification -> entity_node")
    return "entity_node"
