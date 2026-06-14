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
    "FINANCIAL_KNOWLEDGE", "OUT_OF_SCOPE", "PORTFOLIO_ANALYSIS",
}


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
    }

    if intent == "OUT_OF_SCOPE":
        result["final_answer"] = (
            "This assistant specialises in personal finance and financial planning. "
            "Please ask a finance-related question."
        )
        result["final_intent"] = "OUT_OF_SCOPE"
        result["sources"] = ["Domain Scope Validator"]

    return result
