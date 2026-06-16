"""
Guardrail nodes — Input and Output security validation.

Reuses the existing InputGuard and OutputGuard classes unchanged.
"""

from __future__ import annotations

import logging
from app.graph.state import AgentState
from app.guardrails.input_guard import InputGuard
from app.guardrails.output_guard import OutputGuard
from app.utils.security_logger import log_security_event

logger = logging.getLogger(__name__)


def input_guardrail_node(state: AgentState) -> dict:
    """
    Layer 1 Security: validates the incoming user message.

    Uses InputGuard (regex-based, no LLM) to detect:
      - Prompt injection patterns
      - Suspicious data-access phrases
      - Message length violations
      - Special character floods
      - Profanity

    On block → sets input_blocked=True and final_answer; graph routes to END.
    On pass  → sets input_blocked=False; graph continues.
    """
    user_id = state["user_id"]
    session_id = state["session_id"]
    message = state["user_query"]

    is_safe, error_message = InputGuard.validate(message, user_id)

    if not is_safe:
        log_security_event(
            user_id=user_id,
            thread_id=session_id,
            event_type="input_blocked",
            message=message,
            reason=error_message,
        )
        logger.warning("[Node:input_guardrail] BLOCKED | user=%s | reason=%s", user_id, error_message)
        return {
            "input_blocked": True,
            "input_error": error_message,
            "final_answer": error_message,
            "final_intent": "OUT_OF_SCOPE",
            "sources": ["Security Guardrails"],
        }

    logger.info("[Node:input_guardrail] PASSED | user=%s", user_id)
    return {"input_blocked": False}


def output_guardrail_node(state: AgentState) -> dict:
    """
    Layer 4 Security: validates the LLM-generated answer before delivery.

    Checks:
      1. Sensitive credential leakage → Hard block
      2. Raw SQL in response → Sanitise
      3. Residual PII → Mask

    Sets final_answer to the cleaned (or blocked) response.
    """
    user_id = state["user_id"]
    session_id = state["session_id"]
    raw = state.get("raw_answer") or state.get("final_answer") or ""

    is_safe, cleaned = OutputGuard.validate_and_clean(raw, user_id)

    if not is_safe:
        log_security_event(
            user_id=user_id,
            thread_id=session_id,
            event_type="output_blocked",
            message=state.get("user_query", ""),
            reason="Sensitive credentials or system data detected in LLM output",
        )
        logger.error("[Node:output_guardrail] BLOCKED output | user=%s", user_id)
        return {
            "output_blocked": True,
            "final_answer": cleaned,
            "sources": ["Security Guardrails"],
        }

    logger.info("[Node:output_guardrail] PASSED | user=%s", user_id)
    return {
        "output_blocked": False,
        "final_answer": cleaned,
    }
