"""
Context resolution node — follow-up query rewriting.

Reads conversation history from LangGraph checkpointer state and rewrites
follow-up messages into standalone queries.
"""

from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import CONTEXT_REWRITE_SYSTEM, CONTEXT_REWRITE_USER

logger = logging.getLogger(__name__)


def context_node(state: AgentState) -> dict:
    """
    Resolves follow-up queries by rewriting them with prior context.

    Reads last 5 messages from LangGraph state (persisted by checkpointer)
    and uses LLM to rewrite follow-ups into standalone queries.

    Examples:
      Turn 1: "How much did I spend on food?"
      Turn 2: "What about last month?"
              → rewritten: "How much did I spend on food last month?"
    """
    message = state["user_query"]
    lc_messages = state.get("messages", [])

    # Build history from last 5 messages (excluding current)
    history_lines = []
    for m in lc_messages[-6:-1]:
        role = "User" if m.__class__.__name__ == "HumanMessage" else "Assistant"
        history_lines.append(f"{role}: {m.content}")
    history_str = "\n".join(history_lines) if history_lines else "None."

    # Get previous entities if available from state metadata
    prev_entities = state.get("metadata", {}).get("last_entities", {})
    prev_entities_str = json.dumps(prev_entities) if prev_entities else "None"

    # If no history, skip rewriting
    if not history_lines:
        logger.info("[Node:context] No history — using original query")
        return {"rewritten_query": message, "standalone_query": message}

    try:
        response = graph_chat_completion(
            node="context_node",
            purpose="query_rewrite",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": CONTEXT_REWRITE_SYSTEM},
                {"role": "user", "content": CONTEXT_REWRITE_USER.format(
                    history=history_str,
                    prev_entities=prev_entities_str,
                    message=message,
                )},
            ],
            max_tokens=200,
            temperature=0.0,
        )
        rewritten = response.choices[0].message.content.strip()

        # Strip any accidental quotes the LLM might wrap
        if rewritten.startswith('"') and rewritten.endswith('"'):
            rewritten = rewritten[1:-1]

        if rewritten and rewritten != message:
            logger.info("[Node:context] Rewritten: '%s' → '%s'", message, rewritten)
        else:
            rewritten = message
            logger.info("[Node:context] No rewrite needed")

        return {"rewritten_query": rewritten, "standalone_query": rewritten}

    except Exception as exc:
        logger.error("[Node:context] Rewrite failed: %s — using original", exc)
        return {"rewritten_query": message, "standalone_query": message}
