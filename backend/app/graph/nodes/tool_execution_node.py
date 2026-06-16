"""
Tool Execution Node — runs the Brain's execution plan via the code layer.
"""

from __future__ import annotations

import logging

from app.graph.state import AgentState
from app.graph.tools.tool_runner import execute_tool_plan

logger = logging.getLogger(__name__)


def tool_execution_node(state: AgentState) -> dict:
    """
    Dispatches each tool in execution_plan and stores results in state buckets.
    """
    execution_plan = state.get("execution_plan") or {}
    tools = execution_plan.get("tools") or []

    if not tools:
        logger.warning("[Node:tool_execution] Empty execution plan")
        return {
            "rag_results": {},
            "agent_results": [],
            "portfolio_results": {},
        }

    logger.info("[Node:tool_execution] Executing %d tool(s)", len(tools))
    results = execute_tool_plan(state, execution_plan)

    return {
        "rag_results": results.get("rag_results", {}),
        "agent_results": results.get("agent_results", []),
        "portfolio_results": results.get("portfolio_results", {}),
        "selected_agent": results.get("selected_agent", ""),
        "sql_results": results.get("sql_results", []),
        "sql_query": results.get("sql_query", ""),
        "analytics_results": results.get("analytics_results", {}),
        "retrieved_context": results.get("retrieved_context", []),
        "context_sources": results.get("context_sources", []),
        "rag_confidence": results.get("rag_confidence", 1.0),
        "metadata": {
            **(state.get("metadata") or {}),
            **(results.get("metadata") or {}),
            "tool_errors": results.get("tool_errors", []),
        },
    }
