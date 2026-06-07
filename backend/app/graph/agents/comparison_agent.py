"""
Comparison Agent — Generates two SQL ASTs for comparison queries (A vs B).
"""

from __future__ import annotations

import json
import logging

import openai

from app.core.config import settings
from app.graph.state import AgentState
from app.utils.prompts import SQL_GENERATION_SYSTEM, SQL_GENERATION_USER

logger = logging.getLogger(__name__)


def comparison_agent(state: AgentState) -> dict:
    """
    Generates two SQL ASTs in a JSON object with keys 'query_a' and 'query_b'.
    """
    query = state.get("rewritten_query") or state.get("user_query") or ""
    intent = state.get("intent") or "COMPARISON"
    entities = state.get("resolved_entities") or state.get("entities") or {}

    agent_instructions = (
        "Generate exactly TWO SQL ASTs inside a single JSON object. The keys of the outer object must be "
        "'query_a' and 'query_b' representing the two targets/periods being compared. "
        "For example, if comparing Food vs Travel, query_a should select Food expenses and query_b "
        "should select Travel expenses. If comparing this month vs last month, query_a should have date filters "
        "for this month and query_b should have date filters for last month. "
        "Format of the output must be:\n"
        "{\n"
        "  \"query_a\": { ...AST... },\n"
        "  \"query_b\": { ...AST... }\n"
        "}\n"
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
            max_tokens=800,
            temperature=0.0,
        )
        sql_ast = json.loads(response.choices[0].message.content.strip())
        logger.info("[Agent:comparison] Generated dual SQL ASTs: %s", json.dumps(sql_ast))
    except Exception as exc:
        logger.error("[Agent:comparison] LLM AST generation failed: %s", exc)
        sql_ast = {}

    return {"sql_ast": sql_ast}
