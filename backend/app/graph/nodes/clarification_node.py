"""
Clarification node — Ambiguity detection.
"""

from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
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

    unmatched_categories = entities.get("unmatched_categories", [])
    if unmatched_categories:
        import difflib
        from app.graph.nodes.semantic_node import _fetch_db_categories
        db_categories = _fetch_db_categories()
        unique_categories = sorted(list({c["main_category"] for c in db_categories if c.get("main_category")}))
        
        closest = []
        for uc in unmatched_categories:
            matches = difflib.get_close_matches(uc, unique_categories, n=3, cutoff=0.1)
            closest.extend(matches)
        closest = sorted(list(set(closest)))
        if not closest:
            closest = unique_categories[:3]
        
        unmatched_str = ", ".join(unmatched_categories)
        closest_str = ", ".join(closest)
        question = f"I cannot find any category called {unmatched_str} but these are the closest matching categories: {closest_str}."
        
        logger.info("[Node:clarification] unmatched categories detected: %s", question)
        return {
            "clarification_needed": True,
            "clarification_question": question,
            "final_answer": question,
            "final_intent": intent,
            "sources": ["Clarification Decider"]
        }

    try:
        response = graph_chat_completion(
            node="clarification_node",
            purpose="clarification_check",
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
