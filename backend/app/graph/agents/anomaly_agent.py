"""
Anomaly Agent — Generates SQL AST to retrieve recent transactions for anomaly detection.
"""

from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import SQL_GENERATION_SYSTEM, SQL_GENERATION_USER

logger = logging.getLogger(__name__)


def anomaly_agent(state: AgentState) -> dict:
    """
    Generates a SQL AST to fetch transaction history (e.g. last 3 months)
    without aggregation so that the analytics node can calculate anomalies.
    """
    query = state.get("rewritten_query") or state.get("user_query") or ""
    intent = state.get("intent") or "ANOMALY_DETECTION"
    entities = state.get("resolved_entities") or state.get("entities") or {}

    agent_instructions = (
        "Generate a SQL AST to fetch transaction details (transaction_date, amount, merchant_name, "
        "main_category) for the last 3 months. Do NOT group or aggregate the data. "
        "This raw transaction history will be used by the analytics node to calculate z-score outliers. "
        "Always enforce filtering by user_id using '{{user_id}}'."
    )

    try:
        response = graph_chat_completion(
            node="anomaly_agent",
            purpose="anomaly_sql_ast_generation",
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
        logger.info("[Agent:anomaly] Generated SQL AST: %s", json.dumps(sql_ast))
    except Exception as exc:
        logger.error("[Agent:anomaly] LLM AST generation failed: %s", exc)
        sql_ast = {}

    return {"sql_ast": sql_ast}
