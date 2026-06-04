"""
Clarification node — Ambiguity detection.
"""

from __future__ import annotations

import json
import logging

import openai

from app.core.config import settings
from app.graph.state import AgentState
from app.utils.prompts import CLARIFICATION_SYSTEM, CLARIFICATION_USER

logger = logging.getLogger(__name__)


def clarification_node(state: AgentState) -> dict:
    """
    Decides if the query is too ambiguous to proceed.
    Sets clarification_needed and clarification_question.
    If clarification is needed, sets final_answer = clarification_question.
    """
    query = state.get("rewritten_query") or state.get("user_query") or ""
    entities = state.get("resolved_entities") or state.get("entities") or {}
    intent = state.get("intent") or "TRANSACTION_QUERY"

    try:
        client = openai.OpenAI(
            api_key=settings.active_api_key,
            base_url=settings.active_base_url,
        )
        response = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": CLARIFICATION_SYSTEM},
                {"role": "user", "content": CLARIFICATION_USER.format(
                    query=query,
                    entities=json.dumps(entities),
                    intent=intent
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content.strip())
        needs_clarification = bool(data.get("needs_clarification", False))
        question = str(data.get("question", "")).strip()

        logger.info("[Node:clarification] needs_clarification=%s question='%s'", needs_clarification, question)

    except Exception as exc:
        logger.error("[Node:clarification] Failed: %s — proceeding safely", exc)
        needs_clarification = False
        question = ""

    result = {
        "clarification_needed": needs_clarification,
        "clarification_question": question,
    }

    if needs_clarification and question:
        result["final_answer"] = question
        result["final_intent"] = intent
        result["sources"] = ["Clarification Decider"]

    return result
