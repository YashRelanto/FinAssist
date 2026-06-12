"""
Intent classification node — 11-intent classifier.
"""

from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import INTENT_SYSTEM, INTENT_USER

logger = logging.getLogger(__name__)

VALID_INTENTS = {
    "TRANSACTION_QUERY", "SPENDING_SUMMARY", "CATEGORY_ANALYSIS",
    "MERCHANT_ANALYSIS", "ACCOUNT_QUERY", "TREND_ANALYSIS",
    "COMPARISON", "ANOMALY_DETECTION", "GOAL_PLANNING",
    "FINANCIAL_KNOWLEDGE", "INVESTMENT_ANALYSIS", "HYBRID_QUERY",
    "OUT_OF_SCOPE",
}

# BRD intent taxonomy → internal classifier labels
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


def intent_node(state: AgentState) -> dict:
    """
    Classifies the user's message into one of 11 intents.

    Uses conversation history for context but classifies only the latest message.
    On OUT_OF_SCOPE → sets final_answer and routes to END.
    """
    message = state["user_query"]
    lc_messages = state.get("messages", [])

    # Build history string from last 5 messages
    history_lines = []
    for m in lc_messages[-6:-1]:
        role = "User" if m.__class__.__name__ == "HumanMessage" else "Assistant"
        history_lines.append(f"{role}: {m.content}")
    history_str = "\n".join(history_lines) if history_lines else "None."

    try:
        response = graph_chat_completion(
            node="intent_node",
            purpose="intent_classification",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM},
                {"role": "user", "content": INTENT_USER.format(
                    history=history_str, message=message)},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content.strip())
        intent = str(data.get("intent", "FINANCIAL_KNOWLEDGE")).upper().strip()
        confidence = float(data.get("confidence", 0.5))

        if intent not in VALID_INTENTS:
            intent = "FINANCIAL_KNOWLEDGE"

        logger.info("[Node:intent] intent=%s confidence=%.2f", intent, confidence)

    except Exception as exc:
        logger.error("[Node:intent] Failed: %s — defaulting to FINANCIAL_KNOWLEDGE", exc)
        intent = "FINANCIAL_KNOWLEDGE"
        confidence = 0.5

    result = {
        "intent": intent,
        "confidence": confidence,
        "final_intent": to_brd_intent(intent),
    }

    if intent == "OUT_OF_SCOPE":
        result["final_answer"] = (
            "This assistant specialises in personal finance and financial planning. "
            "Please ask a finance-related question."
        )
        result["sources"] = ["Domain Scope Validator"]

    return result
