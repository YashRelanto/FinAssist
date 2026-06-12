"""
Clarification node — ambiguity detection with iterative Q&A support.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.graph.clarification_options import (
    build_clarification_option_sources,
    format_option_sources_for_prompt,
)
from app.utils.prompts import CLARIFICATION_SYSTEM, CLARIFICATION_USER

logger = logging.getLogger(__name__)


def _build_clarification_history(messages: list, prior_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect Q&A pairs from conversation when user answered a prior clarification."""
    history = list(prior_history)
    lc_messages = messages or []

    if len(lc_messages) >= 2:
        prev = lc_messages[-2]
        curr = lc_messages[-1]
        if isinstance(prev, AIMessage) and isinstance(curr, HumanMessage):
            prev_text = (prev.content or "").strip()
            if prev_text.endswith("?"):
                entry = {"question": prev_text, "answer": (curr.content or "").strip()}
                if not history or history[-1].get("answer") != entry["answer"]:
                    history.append(entry)

    return history


def clarification_node(state: AgentState) -> dict:
    """
    Determines whether sufficient information exists to answer the query.
    Supports iterative clarification with structured options.
    """
    query = state.get("standalone_query") or state.get("rewritten_query") or state.get("user_query") or ""
    intent = state.get("intent") or "TRANSACTION_QUERY"
    user_profile = state.get("user_profile") or {}
    prior_history = state.get("clarification_history") or []
    messages = state.get("messages") or []

    clarification_history = _build_clarification_history(messages, prior_history)

    if clarification_history and len(clarification_history) >= 3:
        logger.info("[Node:clarification] Max clarification rounds reached — proceeding")
        return {
            "clarification_needed": False,
            "clarification_complete": True,
            "clarification_history": clarification_history,
            "clarification_options": [],
        }

    option_sources = build_clarification_option_sources(state)
    option_sources_str = format_option_sources_for_prompt(option_sources)

    try:
        response = graph_chat_completion(
            node="clarification_node",
            purpose="clarification_check",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": CLARIFICATION_SYSTEM},
                {"role": "user", "content": CLARIFICATION_USER.format(
                    query=query,
                    user_profile=json.dumps(
                        {k: user_profile.get(k) for k in ("risk_profile", "income", "segment", "city", "goals")},
                        default=str,
                    ),
                    clarification_history=json.dumps(clarification_history, default=str),
                    intent=intent,
                    option_sources=option_sources_str,
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content.strip())
        needs_clarification = bool(data.get("needs_clarification", False))
        question = str(data.get("question", "")).strip()
        options = data.get("options") or []
        if not isinstance(options, list):
            options = []
        options = [str(o).strip() for o in options if str(o).strip()][:6]

        logger.info(
            "[Node:clarification] needs_clarification=%s question='%s' options=%s",
            needs_clarification, question, options,
        )

    except Exception as exc:
        logger.error("[Node:clarification] Failed: %s — proceeding safely", exc)
        needs_clarification = False
        question = ""
        options = []

    result: Dict[str, Any] = {
        "clarification_needed": needs_clarification,
        "clarification_question": question,
        "clarification_options": options,
        "clarification_history": clarification_history,
        "clarification_complete": not needs_clarification,
    }

    if needs_clarification and question:
        answer_text = question
        if options:
            answer_text = f"{question}\n\nOptions: {', '.join(options)}"
        result["final_answer"] = answer_text
        result["final_intent"] = intent
        result["sources"] = ["Clarification Decider"]

    return result
