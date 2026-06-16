"""
Router node — DEPRECATED. Superseded by brain_orchestrator + tool_runner.

Kept for reference only; not wired into the compiled graph.
"""

from __future__ import annotations

import logging
from app.graph.state import AgentState

logger = logging.getLogger(__name__)

INTENT_TO_AGENT = {
    "TRANSACTION_QUERY":   "transaction",
    "SPENDING_SUMMARY":    "transaction",
    "CATEGORY_ANALYSIS":   "transaction",
    "MERCHANT_ANALYSIS":   "transaction",
    "ACCOUNT_QUERY":       "transaction",
    "TREND_ANALYSIS":      "trend",
    "COMPARISON":          "comparison",
    "ANOMALY_DETECTION":   "anomaly",
    "FINANCIAL_KNOWLEDGE": "knowledge",
    "PORTFOLIO_ANALYSIS":  "investment_analysis",
}


def router_node(state: AgentState) -> dict:
    """
    Sets the selected_agent based on the intent.
    """
    intent = state.get("intent") or "FINANCIAL_KNOWLEDGE"
    selected_agent = INTENT_TO_AGENT.get(intent, "knowledge")
    logger.info("[Node:router] intent=%s -> selected_agent=%s", intent, selected_agent)
    return {"selected_agent": selected_agent}
