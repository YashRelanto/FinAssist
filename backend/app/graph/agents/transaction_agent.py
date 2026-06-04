"""
Transaction Agent — Generates SQL AST for transaction queries and summaries.
"""

from __future__ import annotations

import json
import logging

import openai

from app.core.config import settings
from app.graph.state import AgentState
from app.utils.prompts import SQL_GENERATION_SYSTEM, SQL_GENERATION_USER

logger = logging.getLogger(__name__)


def transaction_agent(state: AgentState) -> dict:
    """
    Generates a single SQL AST for transaction/spending/account queries.
    """
    query = state.get("rewritten_query") or state.get("user_query") or ""
    intent = state.get("intent") or "TRANSACTION_QUERY"
    entities = state.get("resolved_entities") or state.get("entities") or {}

    agent_instructions = (
        "Generate a single SQL AST to retrieve the requested transactions or aggregates "
        "(sum, count, average, max, min, or list). If the user asks for a breakdown by category "
        "or merchant, group by main_category (requires JOIN with categories table) or merchant_name. "
        "Always enforce filtering by user_id using '{{user_id}}'."
    )

    try:
        client = openai.OpenAI(
            api_key=settings.active_api_key,
            base_url=settings.active_base_url,
        )
        response = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": SQL_GENERATION_SYSTEM},
                {"role": "user", "content": SQL_GENERATION_USER.format(
                    query=query,
                    intent=intent,
                    entities=json.dumps(entities),
                    agent_instructions=agent_instructions,
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.0,
        )
        sql_ast = json.loads(response.choices[0].message.content.strip())
        logger.info("[Agent:transaction] Generated SQL AST: %s", json.dumps(sql_ast))
    except Exception as exc:
        logger.error("[Agent:transaction] LLM AST generation failed: %s", exc)
        sql_ast = {}

    return {"sql_ast": sql_ast}
