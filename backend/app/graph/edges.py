"""
graph/edges.py
==============
Conditional routing functions for the FinAssist Brain (Supervisor) graph.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.graph.state import AgentState

logger = logging.getLogger("app.graph")


def route_after_input_guardrail(state: AgentState) -> Literal["brain", "__end__"]:
    """Blocked input → END; otherwise hand control to the Brain."""
    if state.get("input_blocked"):
        logger.info("[Edge] input_guardrail -> __end__ (blocked)")
        return "__end__"
    return "brain"


def route_after_brain(
    state: AgentState,
) -> Literal["nl2sql_agent", "goal_planner_tool", "investment_tool",
             "knowledge_tool", "answer_node", "__end__"]:
    """Dispatch the Brain's resolved decision to a tool, the answer node, or END."""
    action = state.get("next_action") or "finish"

    if action == "nl2sql":
        return "nl2sql_agent"
    if action == "goal_planner":
        return "goal_planner_tool"
    if action == "investment":
        return "investment_tool"
    if action == "knowledge":
        return "knowledge_tool"
    if action == "out_of_scope":
        logger.info("[Edge] brain -> __end__ (out of scope)")
        return "__end__"

    # "finish" (and any fallthrough)
    return "answer_node"


def route_after_sql_validator(state: AgentState) -> Literal["sql_executor", "brain"]:
    """Valid AST → execute; invalid → back to the Brain (error recorded in evidence)."""
    if state.get("sql_valid", False):
        return "sql_executor"
    logger.info("[Edge] sql_validator -> brain (validation failed)")
    return "brain"
