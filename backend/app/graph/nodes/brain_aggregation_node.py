"""
Brain Aggregation — merges multi-tool outputs into unified reasoning context.
"""

from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import BRAIN_AGGREGATION_SYSTEM, BRAIN_AGGREGATION_USER

logger = logging.getLogger(__name__)


def brain_aggregation_node(state: AgentState) -> dict:
    """
    Combines RAG, agent/SQL, and portfolio results into final_context for the answer node.
    """
    query = state.get("standalone_query") or state.get("rewritten_query") or state.get("user_query") or ""
    rag_results = state.get("rag_results") or {}
    agent_results = state.get("agent_results") or []
    portfolio_results = state.get("portfolio_results") or {}
    semantic_context = state.get("semantic_context") or {}
    user_profile = state.get("user_profile") or {}

    has_rag = bool(rag_results.get("documents"))
    has_agent = bool(agent_results)
    has_portfolio = bool(portfolio_results.get("portfolio_health"))

    if not has_rag and not has_agent and not has_portfolio:
        logger.info("[Node:brain_agg] No tool results — minimal context")
        return {
            "final_context": {
                "status": "no_tool_results",
                "query": query,
            },
        }

    try:
        response = graph_chat_completion(
            node="brain_aggregation_node",
            purpose="context_aggregation",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": BRAIN_AGGREGATION_SYSTEM},
                {"role": "user", "content": BRAIN_AGGREGATION_USER.format(
                    query=query,
                    semantic_context=json.dumps(semantic_context, default=str),
                    rag_results=json.dumps(rag_results, default=str)[:6000],
                    agent_results=json.dumps(agent_results, default=str)[:6000],
                    portfolio_results=json.dumps(portfolio_results, default=str)[:4000],
                    user_profile=json.dumps(
                        {k: user_profile.get(k) for k in (
                            "income", "risk_profile", "segment", "city", "monthly_net_flow",
                            "fixed_emi", "goals", "primary_goal",
                        )},
                        default=str,
                    ),
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=800,
            temperature=0.1,
        )
        final_context = json.loads(response.choices[0].message.content.strip())
        logger.info("[Node:brain_agg] Aggregated context keys: %s", list(final_context.keys()))

    except Exception as exc:
        logger.error("[Node:brain_agg] Aggregation failed: %s — using raw merge", exc)
        final_context = {
            "query": query,
            "key_insights": [],
            "knowledge_summary": " ".join(rag_results.get("documents", [])[:3]),
            "transaction_summary": json.dumps(agent_results, default=str)[:2000],
            "portfolio_summary": json.dumps(
                portfolio_results.get("portfolio_health", {}), default=str
            ),
            "personalization_notes": json.dumps(
                semantic_context.get("goal_mapping") or user_profile.get("goals", []),
                default=str,
            ),
            "contradictions_resolved": "",
            "recommended_focus": semantic_context.get("analysis_required", ["general"])[0]
            if semantic_context.get("analysis_required")
            else "general",
        }

    metadata = dict(state.get("metadata") or {})
    if final_context.get("contradictions_resolved"):
        metadata["contradictions_resolved"] = final_context["contradictions_resolved"]

    return {"final_context": final_context, "metadata": metadata}
