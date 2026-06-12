"""
Tool execution layer — dispatches Brain execution plans to RAG, agents, and investment analysis.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.graph.agents import (
    anomaly_agent,
    comparison_agent,
    transaction_agent,
    trend_agent,
)
from app.graph.nodes.analytics_node import analytics_node
from app.graph.nodes.rag_node import run_rag_retrieval
from app.graph.sql import sql_executor, sql_planner, sql_validator
from app.graph.state import AgentState
from app.services.investment_analysis_service import analyze_portfolio

logger = logging.getLogger(__name__)

AGENT_FN_MAP = {
    "transaction_agent": transaction_agent,
    "transactions_agent": transaction_agent,
    "trend_agent": trend_agent,
    "comparison_agent": comparison_agent,
    "anomaly_agent": anomaly_agent,
}

INTENT_AGENT_DEFAULTS = {
    "TRANSACTION_QUERY": "transaction_agent",
    "SPENDING_SUMMARY": "transaction_agent",
    "CATEGORY_ANALYSIS": "transaction_agent",
    "MERCHANT_ANALYSIS": "transaction_agent",
    "ACCOUNT_QUERY": "transaction_agent",
    "TREND_ANALYSIS": "trend_agent",
    "COMPARISON": "comparison_agent",
    "ANOMALY_DETECTION": "anomaly_agent",
}


def _run_sql_pipeline(state: AgentState) -> Dict[str, Any]:
    """AST → SQL → validate → execute → analytics."""
    merged: Dict[str, Any] = dict(state)
    updates: Dict[str, Any] = {}

    for step in (sql_planner, sql_validator):
        step_updates = step(merged)  # type: ignore[arg-type]
        merged.update(step_updates)
        updates.update(step_updates)

    if merged.get("sql_valid"):
        exec_updates = sql_executor(merged)  # type: ignore[arg-type]
        merged.update(exec_updates)
        updates.update(exec_updates)

        analytics_updates = analytics_node(merged)  # type: ignore[arg-type]
        merged.update(analytics_updates)
        updates.update(analytics_updates)
    else:
        updates["analytics_results"] = {"status": "sql_validation_failed"}

    return updates


def _execute_agent_tool(state: AgentState, agent_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    agent_key = agent_name if agent_name.endswith("_agent") else f"{agent_name}_agent"
    agent_fn = AGENT_FN_MAP.get(agent_key) or AGENT_FN_MAP.get(agent_name)

    if not agent_fn:
        intent = state.get("intent") or ""
        agent_key = INTENT_AGENT_DEFAULTS.get(intent, "transaction_agent")
        agent_fn = AGENT_FN_MAP[agent_key]

    work_state: AgentState = dict(state)
    if args.get("category") or args.get("period"):
        entities = dict(work_state.get("resolved_entities") or work_state.get("entities") or {})
        if args.get("category"):
            entities.setdefault("categories", [])
            if args["category"] not in entities["categories"]:
                entities["categories"].append(args["category"])
        if args.get("period"):
            entities["period"] = args["period"]
        work_state["resolved_entities"] = entities

    agent_updates = agent_fn(work_state)  # type: ignore[operator]
    work_state.update(agent_updates)

    selected = agent_key.replace("_agent", "")
    work_state["selected_agent"] = selected

    sql_updates = _run_sql_pipeline(work_state)
    work_state.update(sql_updates)

    return {
        "agent": selected,
        "args": args,
        "sql_ast": work_state.get("sql_ast"),
        "sql_query": work_state.get("sql_query"),
        "sql_valid": work_state.get("sql_valid"),
        "sql_results": work_state.get("sql_results"),
        "sql_error": work_state.get("sql_error"),
        "analytics_results": work_state.get("analytics_results"),
    }


def _execute_rag_tool(state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query") or state.get("standalone_query") or state.get("rewritten_query") or state.get("user_query") or ""
    rag_updates = run_rag_retrieval(query=query, intent=state.get("intent") or "FINANCIAL_KNOWLEDGE")
    return {
        "query": query,
        "documents": rag_updates.get("retrieved_context", []),
        "sources": rag_updates.get("context_sources", []),
        "confidence": rag_updates.get("rag_confidence", 1.0),
    }


def _execute_investment_tool(state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
    user_id = state.get("user_id") or ""
    profile = state.get("user_profile") or {}
    focus = args.get("focus") or "full"
    return analyze_portfolio(user_id, user_profile=profile, focus=focus)


def execute_tool_plan(state: AgentState, execution_plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute all tools in a Brain execution plan and return aggregated result buckets.
    """
    tools: List[Dict[str, Any]] = execution_plan.get("tools") or []
    rag_results: Dict[str, Any] = {}
    agent_results: List[Dict[str, Any]] = []
    portfolio_results: Dict[str, Any] = {}
    tool_errors: List[str] = []

    for entry in tools:
        tool_name = (entry.get("tool") or "").lower()
        args = entry.get("args") or {}
        agent_name = entry.get("agent") or ""

        try:
            if tool_name == "rag":
                rag_results = _execute_rag_tool(state, args)
            elif tool_name in ("agent_layer", "agent"):
                agent_result = _execute_agent_tool(state, agent_name, args)
                agent_results.append(agent_result)
            elif tool_name in ("investment_analysis", "investment"):
                portfolio_results = _execute_investment_tool(state, args)
            else:
                tool_errors.append(f"Unknown tool: {tool_name}")
        except Exception as exc:
            logger.error("[tool_runner] Tool %s failed: %s", tool_name, exc)
            tool_errors.append(f"{tool_name}: {exc}")

    selected_agent = ""
    if agent_results:
        selected_agent = agent_results[-1].get("agent", "")

    merged_sql_results: Any = []
    merged_analytics: Dict[str, Any] = {"agents": {}}
    sql_queries: List[str] = []
    for ar in agent_results:
        agent_key = ar.get("agent") or "unknown"
        rows = ar.get("sql_results") or []
        if rows:
            merged_sql_results.extend(rows if isinstance(rows, list) else [rows])
        if ar.get("sql_query"):
            sql_queries.append(ar["sql_query"])
        if ar.get("analytics_results"):
            merged_analytics["agents"][agent_key] = ar["analytics_results"]
    if agent_results:
        last = agent_results[-1]
        merged_analytics.update(last.get("analytics_results") or {})
        if not merged_sql_results:
            merged_sql_results = last.get("sql_results") or []

    metadata = dict(state.get("metadata") or {})
    if tool_errors:
        metadata["tool_errors"] = tool_errors

    return {
        "rag_results": rag_results,
        "agent_results": agent_results,
        "portfolio_results": portfolio_results,
        "selected_agent": selected_agent,
        "sql_results": merged_sql_results,
        "analytics_results": merged_analytics,
        "sql_query": "; ".join(sql_queries) if sql_queries else "",
        "metadata": metadata,
        "retrieved_context": rag_results.get("documents", []),
        "context_sources": rag_results.get("sources", []),
        "rag_confidence": rag_results.get("confidence", 1.0),
        "tool_errors": tool_errors,
    }
