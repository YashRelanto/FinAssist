"""
Trend Agent — Generates SQL AST for trend analysis queries.
"""

from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import SQL_GENERATION_SYSTEM, SQL_GENERATION_USER

logger = logging.getLogger(__name__)


def trend_agent(state: AgentState) -> dict:
    """
    Generates a single SQL AST for trend analysis over time.
    """
    query = state.get("rewritten_query") or state.get("user_query") or ""
    intent = state.get("intent") or "TREND_ANALYSIS"
    entities = state.get("resolved_entities") or state.get("entities") or {}

    metric = (entities.get("metric") or "").lower()
    tx_type = entities.get("transaction_type")
    trend_focus = "expense"
    if tx_type == "income" or metric in ("income", "salary"):
        trend_focus = "income"
    elif metric in ("savings", "saving"):
        trend_focus = "savings"

    agent_instructions = (
        f"Generate a single SQL AST for {trend_focus} trend analysis grouped by month "
        "over the last 6-12 months. "
        f"Filter transaction_type to {'income' if trend_focus == 'income' else 'expense'} "
        f"when analyzing {trend_focus} trends. "
        "For savings trends, return both income and expense rows so analytics can compute net savings. "
        "Select transaction_date and amount; group by month when possible. "
        "Always enforce filtering by user_id using '{{user_id}}'."
    )

    try:
        response = graph_chat_completion(
            node="trend_agent",
            purpose="trend_sql_ast_generation",
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
        logger.info("[Agent:trend] Generated SQL AST: %s", json.dumps(sql_ast))
    except Exception as exc:
        logger.error("[Agent:trend] LLM AST generation failed: %s", exc)
        sql_ast = {}

    return {"sql_ast": sql_ast}
