"""
Goal Planning Node — HITL slot filling for savings and investment goals.
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from langchain_core.messages import HumanMessage, AIMessage

from app.graph.state import AgentState
from app.utils.workflow_logic import WorkflowLogic

logger = logging.getLogger(__name__)


def goal_planning_node(state: AgentState) -> dict:
    """
    Executes the slot filling process.
    If slots are missing -> returns next question and stops (routes to END).
    If all slots are filled -> returns workflow_active=False and proceeds to answer generation.
    """
    message = state.get("user_query") or ""
    workflow_state = state.get("workflow_state") or {}
    lc_messages = state.get("messages") or []

    # Convert LangChain messages -> history dicts
    history = []
    for m in lc_messages[-10:]:
        if isinstance(m, HumanMessage) or m.__class__.__name__ == "HumanMessage":
            history.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage) or m.__class__.__name__ == "AIMessage":
            history.append({"role": "assistant", "content": m.content})

    logger.info("[Node:goal_planning] workflow_type=%s collected=%s",
                workflow_state.get("workflow_type"),
                list(workflow_state.get("collected_information", {}).keys()))

    requires_clarification, next_question, updated_state = WorkflowLogic.process(
        message, history, workflow_state
    )

    if requires_clarification:
        return {
            "workflow_state": updated_state,
            "workflow_active": True,
            "final_answer": next_question,
            "final_intent": "GOAL_PLANNING",
            "sources": ["Clarification Planner"],
        }
    else:
        # All slots filled
        return {
            "workflow_state": updated_state,
            "workflow_active": False,
        }
