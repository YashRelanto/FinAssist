"""
NL2SQL Tool — generalised SQL AST generator for the Brain supervisor.

Replaces the old per-intent agents (transaction / comparison / trend / anomaly).
The Brain hands this tool a sub-question, extracted entities, and an analysis_type;
the tool resolves colloquial merchant/category names against the live DB, then asks
the LLM to emit a SQL AST. The AST then flows through the unchanged
sql_planner → sql_validator → sql_executor → analytics_node chain.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from app.core.config import settings
from app.graph.llm import graph_chat_completion
from app.graph.state import AgentState
from app.graph.schema_registry import render_schema_for_prompt
from app.utils.prompts import (
    SQL_GENERATION_SYSTEM,
    SQL_GENERATION_USER,
    SEMANTIC_RESOLUTION_SYSTEM,
    SEMANTIC_RESOLUTION_USER,
)
from app.utils.supabase_client import supabase_db

logger = logging.getLogger(__name__)


# ── Semantic resolution helpers (ported from the old semantic_node) ──────────

def _fetch_db_merchants(user_id: str, limit: int = 100) -> List[str]:
    """Fetch distinct merchant names from the user's transactions."""
    try:
        if not supabase_db:
            return []
        resp = (
            supabase_db.table("transactions")
            .select("merchant_name")
            .eq("user_id", user_id)
            .not_.is_("merchant_name", "null")
            .limit(limit)
            .execute()
        )
        merchants = list({r["merchant_name"] for r in (resp.data or []) if r.get("merchant_name")})
        return sorted(merchants)
    except Exception as exc:
        logger.warning("[nl2sql] Failed to fetch merchants: %s", exc)
        return []


def _fetch_db_categories() -> List[Dict]:
    """Fetch all categories from the categories table."""
    try:
        if not supabase_db:
            return []
        resp = (
            supabase_db.table("categories")
            .select("category_id, main_category, sub_category")
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.warning("[nl2sql] Failed to fetch categories: %s", exc)
        return []


def resolve_entities(entities: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    Resolve user's colloquial merchant/category terms to real DB values so that
    grouping and filtering stay accurate. Falls back to ilike matching, then to
    the raw entities if the DB or LLM is unavailable.
    """
    entities = dict(entities or {})
    extracted_merchants = entities.get("merchants") or []
    extracted_categories = entities.get("categories") or []

    if not extracted_merchants and not extracted_categories:
        return entities

    db_merchants = _fetch_db_merchants(user_id) if extracted_merchants else []
    db_categories = _fetch_db_categories() if extracted_categories else []

    if db_merchants or db_categories:
        db_merchants_str = "\n".join(db_merchants) if db_merchants else "No merchant data."
        db_categories_str = "\n".join(
            f"  {c['main_category']} → {c['sub_category']} (id={c['category_id']})"
            for c in db_categories
        ) if db_categories else "No category data."

        try:
            response = graph_chat_completion(
                node="nl2sql_agent",
                purpose="semantic_entity_resolution",
                model=settings.tool_model,
                messages=[
                    {"role": "system", "content": SEMANTIC_RESOLUTION_SYSTEM},
                    {"role": "user", "content": SEMANTIC_RESOLUTION_USER.format(
                        merchants=json.dumps(extracted_merchants),
                        categories=json.dumps(extracted_categories),
                        db_merchants=db_merchants_str,
                        db_categories=db_categories_str,
                    )},
                ],
                response_format={"type": "json_object"},
                max_tokens=300,
                temperature=0.0,
            )
            resolution = json.loads(response.choices[0].message.content.strip())

            resolved = dict(entities)
            res_merchants = resolution.get("merchants", [])
            if res_merchants:
                resolved["merchants"] = [m.get("resolved", m.get("original", "")) for m in res_merchants]

            res_categories = resolution.get("categories", [])
            if res_categories:
                resolved["categories"] = [c.get("resolved", c.get("original", "")) for c in res_categories]
                resolved["category_ids"] = [c.get("resolved_id") for c in res_categories if c.get("resolved_id")]

            logger.info("[nl2sql] Resolved entities: %s", json.dumps(resolved, default=str))
            return resolved
        except Exception as exc:
            logger.error("[nl2sql] Semantic resolution failed: %s — falling back to ilike", exc)

    # Fallback: simple substring matching for categories
    resolved = dict(entities)
    if extracted_categories and db_categories:
        matched, matched_ids = [], []
        for cat_term in extracted_categories:
            for db_cat in db_categories:
                if str(cat_term).lower() in db_cat["main_category"].lower():
                    matched.append(db_cat["main_category"])
                    matched_ids.append(db_cat["category_id"])
                    break
            else:
                matched.append(cat_term)
        resolved["categories"] = matched
        resolved["category_ids"] = matched_ids
    return resolved


# ── The tool node ────────────────────────────────────────────────────────────

def nl2sql_agent(state: AgentState) -> dict:
    """
    Generate a SQL AST from the Brain's task. Sets `sql_ast` and `analysis_type`
    for the downstream SQL chain.
    """
    task = state.get("brain_task") or {}
    query = task.get("sub_question") or state.get("user_query") or ""
    entities = task.get("entities") or {}
    analysis_type = (task.get("analysis_type") or "basic").lower()
    user_id = state.get("user_id") or ""

    # Resolve entity names against the live DB for accurate grouping/filtering.
    resolved = resolve_entities(entities, user_id)

    if analysis_type == "comparison":
        agent_instructions = (
            "This is a COMPARISON question. Return TWO queries (query_a and query_b), each a full "
            "single AST with a 'comparison_target' label, comparing the two entities/periods. "
            "Always filter by user_id using '{{user_id}}'."
        )
    elif analysis_type == "trend":
        agent_instructions = (
            "This is a TREND question over time. Return rows ordered by transaction_date so monthly "
            "aggregation is possible; include transaction_date and amount. Filter by user_id with '{{user_id}}'."
        )
    elif analysis_type == "anomaly":
        agent_instructions = (
            "This is an ANOMALY question. Return the individual transactions (transaction_id, "
            "transaction_date, amount, merchant_name) so statistical outliers can be detected. "
            "Filter by user_id with '{{user_id}}'."
        )
    else:
        agent_instructions = (
            "Generate a single SQL AST for the requested transactions or aggregates (sum, count, "
            "average, max, min, or list). Group by main_category (JOIN categories) or merchant_name "
            "when a breakdown is requested. Always filter by user_id using '{{user_id}}'."
        )

    try:
        response = graph_chat_completion(
            node="nl2sql_agent",
            purpose="sql_ast_generation",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": SQL_GENERATION_SYSTEM},
                {"role": "user", "content": SQL_GENERATION_USER.format(
                    schema=render_schema_for_prompt(),
                    current_date=datetime.now().strftime("%Y-%m-%d"),
                    query=query,
                    analysis_type=analysis_type,
                    entities=json.dumps(resolved, default=str),
                    agent_instructions=agent_instructions,
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=600,
            temperature=0.0,
        )
        sql_ast = json.loads(response.choices[0].message.content.strip())
        logger.info("[nl2sql] Generated AST (analysis_type=%s)", analysis_type)
    except Exception as exc:
        logger.error("[nl2sql] AST generation failed: %s", exc)
        sql_ast = {}

    return {"sql_ast": sql_ast, "analysis_type": analysis_type}
