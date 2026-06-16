"""BRD intent taxonomy mapping (shared by chat API and tests)."""

from __future__ import annotations

BRD_INTENT_MAP = {
    "TREND_ANALYSIS": "trend_analysis",
    "TRANSACTION_QUERY": "transaction_analysis",
    "SPENDING_SUMMARY": "transaction_analysis",
    "CATEGORY_ANALYSIS": "transaction_analysis",
    "MERCHANT_ANALYSIS": "transaction_analysis",
    "ACCOUNT_QUERY": "transaction_analysis",
    "COMPARISON": "comparison_analysis",
    "ANOMALY_DETECTION": "anomaly_detection",
    "INVESTMENT_ANALYSIS": "investment_analysis",
    "FINANCIAL_KNOWLEDGE": "financial_guidance",
    "GOAL_PLANNING": "financial_guidance",
    "HYBRID_QUERY": "hybrid_query",
    "OUT_OF_SCOPE": "out_of_scope",
}


def to_brd_intent(intent: str) -> str:
    """Normalize internal intent enum to BRD/API snake_case label."""
    return BRD_INTENT_MAP.get((intent or "").upper(), "financial_guidance")
