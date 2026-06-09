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
) -> Literal["intent_node", "__end__"]:
    """
    If the user input was blocked by guardrails -> END.
    Otherwise -> intent_node.
    """
    if state.get("input_blocked"):
        logger.info("[Edge] input_guardrail -> __end__ (blocked)")
        return "__end__"
    logger.info("[Edge] input_guardrail -> intent_node")
    return "intent_node"


def route_after_intent(
    state: AgentState,
) -> Literal["context_node", "workflow_relevance_node", "goal_planning_node", "__end__"]:
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
        logger.info("[Edge] intent -> __end__ (out of scope)")
        return "__end__"

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
) -> Literal["answer_node", "__end__"]:
    """
    If goal slots are missing (final_answer set to a clarification question) -> END.
    Otherwise (all slots filled) -> answer_node to generate the plan.
    """
    if state.get("final_answer"):
        logger.info("[Edge] goal_planning -> __end__ (clarification needed)")
        return "__end__"
    logger.info("[Edge] goal_planning -> answer_node (completed)")
    return "answer_node"


def route_after_clarification(
    state: AgentState,
) -> Literal["router_node", "__end__"]:
    """
    If query is too ambiguous -> END.
    Otherwise -> router_node.
    """
    if state.get("clarification_needed"):
        logger.info("[Edge] clarification -> __end__ (ambiguous)")
        return "__end__"
    logger.info("[Edge] clarification -> router_node")
    return "router_node"


def route_after_router(
    state: AgentState,
) -> Literal["transaction_agent", "comparison_agent", "trend_agent", "anomaly_agent", "rag_node"]:
    """
    Routes the execution to the corresponding specialized agent node or RAG node.
    """
    selected_agent = state.get("selected_agent") or "knowledge"

    if selected_agent == "transaction":
        logger.info("[Edge] router -> transaction_agent")
        return "transaction_agent"
    if selected_agent == "comparison":
        logger.info("[Edge] router -> comparison_agent")
        return "comparison_agent"
    if selected_agent == "trend":
        logger.info("[Edge] router -> trend_agent")
        return "trend_agent"
    if selected_agent == "anomaly":
        logger.info("[Edge] router -> anomaly_agent")
        return "anomaly_agent"

    logger.info("[Edge] router -> rag_node")
    return "rag_node"


def route_after_sql_validator(
    state: AgentState,
) -> Literal["sql_executor", "answer_node"]:
    """
    If the planned SQL AST is valid -> sql_executor.
    If invalid -> answer_node directly (it will format the validation error).
    """
    if state.get("sql_valid", True):
        logger.info("[Edge] sql_validator -> sql_executor")
        return "sql_executor"
    logger.info("[Edge] sql_validator -> answer_node (failed validation)")
    return "answer_node"
