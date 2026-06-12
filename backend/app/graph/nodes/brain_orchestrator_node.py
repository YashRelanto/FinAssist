"""
Brain Orchestrator — produces an execution plan without running tools directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import BRAIN_ORCHESTRATOR_SYSTEM, BRAIN_ORCHESTRATOR_USER

logger = logging.getLogger(__name__)

VALID_TOOLS = {"rag", "agent_layer", "agent", "investment_analysis", "investment"}
VALID_AGENTS = {
    "transaction_agent", "transactions_agent", "trend_agent",
    "comparison_agent", "anomaly_agent",
}


def _validate_plan_tools(tools: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """Filter and normalize tool entries against the allowlist."""
    validated: List[Dict[str, Any]] = []
    for entry in tools:
        tool_name = (entry.get("tool") or "").lower()
        if tool_name not in VALID_TOOLS:
            logger.warning("[Node:brain] Dropping unknown tool: %s", tool_name)
            continue
        if tool_name in ("agent_layer", "agent"):
            agent = entry.get("agent") or "transaction_agent"
            if agent not in VALID_AGENTS:
                logger.warning("[Node:brain] Unknown agent %s — defaulting to transaction_agent", agent)
                agent = "transaction_agent"
            entry = {**entry, "tool": "agent_layer", "agent": agent}
        if tool_name in ("investment", "investment_analysis"):
            entry = {**entry, "tool": "investment_analysis"}
            entry.setdefault("args", {})
            entry["args"].setdefault("focus", "full")
        if tool_name == "rag":
            entry.setdefault("args", {})
            if not entry["args"].get("query"):
                entry["args"]["query"] = query
        validated.append(entry)
    return validated


INTENT_TOOL_DEFAULTS: Dict[str, List[Dict[str, Any]]] = {
    "FINANCIAL_KNOWLEDGE": [{"tool": "rag", "args": {}}],
    "GOAL_PLANNING": [{"tool": "rag", "args": {"query": "financial goal planning"}}],
    "TREND_ANALYSIS": [{"tool": "agent_layer", "agent": "trend_agent", "args": {}}],
    "COMPARISON": [{"tool": "agent_layer", "agent": "comparison_agent", "args": {}}],
    "ANOMALY_DETECTION": [{"tool": "agent_layer", "agent": "anomaly_agent", "args": {}}],
    "INVESTMENT_ANALYSIS": [{"tool": "investment_analysis", "args": {"focus": "full"}}],
}


def _default_agent_tool(intent: str) -> Dict[str, Any]:
    agent_map = {
        "TREND_ANALYSIS": "trend_agent",
        "COMPARISON": "comparison_agent",
        "ANOMALY_DETECTION": "anomaly_agent",
    }
    agent = agent_map.get(intent, "transaction_agent")
    return {"tool": "agent_layer", "agent": agent, "args": {}}


def _fallback_plan(state: AgentState) -> Dict[str, Any]:
    intent = state.get("intent") or "FINANCIAL_KNOWLEDGE"
    query = state.get("standalone_query") or state.get("rewritten_query") or state.get("user_query") or ""
    semantic = state.get("semantic_context") or {}
    analysis_required = semantic.get("analysis_required") or []

    tools: List[Dict[str, Any]] = []

    if intent in INTENT_TOOL_DEFAULTS:
        tools = [dict(t) for t in INTENT_TOOL_DEFAULTS[intent]]
    elif intent in (
        "TRANSACTION_QUERY", "SPENDING_SUMMARY", "CATEGORY_ANALYSIS",
        "MERCHANT_ANALYSIS", "ACCOUNT_QUERY",
    ):
        tools = [_default_agent_tool(intent)]
    else:
        tools = [{"tool": "rag", "args": {"query": query}}]

    if "cashflow" in analysis_required or "affordability" in analysis_required:
        if not any(t.get("tool") == "agent_layer" for t in tools):
            tools.insert(0, _default_agent_tool("SPENDING_SUMMARY"))
    if "portfolio_review" in analysis_required or intent == "INVESTMENT_ANALYSIS":
        if not any(t.get("tool") == "investment_analysis" for t in tools):
            tools.append({"tool": "investment_analysis", "args": {"focus": "full"}})
    if semantic.get("needs_knowledge"):
        if not any(t.get("tool") == "rag" for t in tools):
            tools.append({"tool": "rag", "args": {"query": query}})

    if len(tools) > 1:
        intent = "HYBRID_QUERY"

    for t in tools:
        if t.get("tool") == "rag" and not t.get("args", {}).get("query"):
            t.setdefault("args", {})["query"] = query

    return {"tools": tools, "intent_override": intent if len(tools) > 1 else None}


def brain_orchestrator_node(state: AgentState) -> dict:
    """
    Brain produces an execution plan — it does NOT execute tools.
    """
    query = state.get("standalone_query") or state.get("rewritten_query") or state.get("user_query") or ""
    intent = state.get("intent") or "FINANCIAL_KNOWLEDGE"
    entities = state.get("resolved_entities") or state.get("entities") or {}
    semantic_context = state.get("semantic_context") or {}
    user_profile = state.get("user_profile") or {}

    try:
        response = graph_chat_completion(
            node="brain_orchestrator_node",
            purpose="execution_plan",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": BRAIN_ORCHESTRATOR_SYSTEM},
                {"role": "user", "content": BRAIN_ORCHESTRATOR_USER.format(
                    query=query,
                    intent=intent,
                    entities=json.dumps(entities, default=str),
                    semantic_context=json.dumps(semantic_context, default=str),
                    user_profile=json.dumps(
                        {k: user_profile.get(k) for k in (
                            "income", "annual_income", "risk_profile", "segment", "city",
                            "monthly_net_flow", "existing_investments",
                        )},
                        default=str,
                    ),
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=400,
            temperature=0.0,
        )
        plan = json.loads(response.choices[0].message.content.strip())
        tools = _validate_plan_tools(plan.get("tools") or [], query)

        if not tools:
            plan = _fallback_plan(state)
        else:
            plan["tools"] = tools
            if len(tools) > 1:
                plan["intent_override"] = "HYBRID_QUERY"

        logger.info("[Node:brain] Plan: %s", json.dumps(plan, default=str))

    except Exception as exc:
        logger.error("[Node:brain] LLM plan failed: %s — using fallback", exc)
        plan = _fallback_plan(state)

    result: Dict[str, Any] = {"execution_plan": plan}
    override = plan.get("intent_override")
    if override:
        result["intent"] = override
        from app.graph.nodes.intent_node import to_brd_intent
        result["final_intent"] = to_brd_intent(override)

    return result
