"""
Semantic resolution node — DB-driven merchant and category normalization.

Queries actual merchant_name values and category main_category values from
Supabase, then uses LLM to fuzzy-match user's extracted entities to real data.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import (
    SEMANTIC_RESOLUTION_SYSTEM,
    SEMANTIC_RESOLUTION_USER,
    SEMANTIC_REASONING_SYSTEM,
    SEMANTIC_REASONING_USER,
)
from app.utils.supabase_client import supabase_db

logger = logging.getLogger(__name__)


def _fetch_db_merchants(user_id: str, limit: int = 100) -> List[str]:
    """Fetch distinct merchant names from user's transactions."""
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
        logger.warning("[semantic] Failed to fetch merchants: %s", exc)
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
        logger.warning("[semantic] Failed to fetch categories: %s", exc)
        return []


def _fetch_user_goals(user_id: str) -> List[Dict]:
    try:
        if not supabase_db:
            return []
        resp = (
            supabase_db.table("goals")
            .select("goal_name, target_amount, current_amount, target_date, status")
            .eq("user_id", user_id)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.warning("[semantic] Failed to fetch goals: %s", exc)
        return []


def _build_semantic_context(state: AgentState, entities: Dict) -> Dict:
    """Financial reasoning layer — maps query objectives to required analyses."""
    query = state.get("standalone_query") or state.get("rewritten_query") or state.get("user_query") or ""
    intent = state.get("intent") or ""
    user_profile = state.get("user_profile") or {}
    goals = user_profile.get("goals") or _fetch_user_goals(state.get("user_id") or "")

    try:
        response = graph_chat_completion(
            node="semantic_node",
            purpose="semantic_reasoning",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": SEMANTIC_REASONING_SYSTEM},
                {"role": "user", "content": SEMANTIC_REASONING_USER.format(
                    query=query,
                    intent=intent,
                    entities=json.dumps(entities, default=str),
                    user_profile=json.dumps(
                        {k: user_profile.get(k) for k in (
                            "income", "risk_profile", "segment", "fixed_emi", "monthly_obligations",
                        )},
                        default=str,
                    ),
                    goals=json.dumps(goals, default=str),
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=250,
            temperature=0.0,
        )
        semantic_context = json.loads(response.choices[0].message.content.strip())
        if goals:
            semantic_context["goal_mapping"] = [
                {
                    "goal": g.get("goal_name"),
                    "target": g.get("target_amount"),
                    "current": g.get("current_amount"),
                    "status": g.get("status"),
                }
                for g in goals
            ]
        logger.info("[Node:semantic] Reasoning: %s", json.dumps(semantic_context, default=str))
        return semantic_context
    except Exception as exc:
        logger.warning("[Node:semantic] Reasoning failed: %s", exc)
        return {"analysis_required": [], "needs_knowledge": intent == "FINANCIAL_KNOWLEDGE"}


def semantic_node(state: AgentState) -> dict:
    """
    Resolves extracted entities against real database values and builds semantic context.

    - Merchant normalization: fuzzy match against user's actual merchant names
    - Category resolution: maps colloquial terms to actual main_category values
    - Semantic reasoning: affordability, cashflow, goal mapping
    """
    entities = state.get("entities", {})
    user_id = state["user_id"]

    extracted_merchants = entities.get("merchants", [])
    extracted_categories = entities.get("categories", [])

    semantic_context = _build_semantic_context(state, entities)

    # If nothing to resolve, pass through with semantic context
    if not extracted_merchants and not extracted_categories:
        logger.info("[Node:semantic] No entities to resolve — pass through")
        return {"resolved_entities": entities, "semantic_context": semantic_context}

    # Fetch real DB data
    db_merchants = _fetch_db_merchants(user_id) if extracted_merchants else []
    db_categories = _fetch_db_categories() if extracted_categories else []

    # If DB returned results, use LLM for fuzzy matching
    if db_merchants or db_categories:
        db_merchants_str = "\n".join(db_merchants) if db_merchants else "No merchant data."
        db_categories_str = "\n".join(
            [f"  {c['main_category']} → {c['sub_category']} (id={c['category_id']})"
             for c in db_categories]
        ) if db_categories else "No category data."

        try:
            response = graph_chat_completion(
                node="semantic_node",
                purpose="semantic_entity_resolution",
                model=settings.active_chat_model,
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

            # Merge resolved names back into entities
            resolved = dict(entities)

            # Update merchants with resolved names
            resolved_merchants = resolution.get("merchants", [])
            if resolved_merchants:
                resolved["merchants"] = [m.get("resolved", m.get("original", ""))
                                         for m in resolved_merchants]

            # Update categories with resolved names + IDs
            resolved_categories = resolution.get("categories", [])
            if resolved_categories:
                resolved["categories"] = [c.get("resolved", c.get("original", ""))
                                          for c in resolved_categories]
                resolved["category_ids"] = [c.get("resolved_id")
                                            for c in resolved_categories
                                            if c.get("resolved_id")]

            logger.info("[Node:semantic] Resolved: %s", json.dumps(resolved, default=str))
            return {"resolved_entities": resolved, "semantic_context": semantic_context}

        except Exception as exc:
            logger.error("[Node:semantic] Resolution failed: %s — using raw entities", exc)

    # Fallback: just try ilike matching for categories
    resolved = dict(entities)
    if extracted_categories and db_categories:
        matched = []
        matched_ids = []
        for cat_term in extracted_categories:
            for db_cat in db_categories:
                if cat_term.lower() in db_cat["main_category"].lower():
                    matched.append(db_cat["main_category"])
                    matched_ids.append(db_cat["category_id"])
                    break
            else:
                matched.append(cat_term)
        resolved["categories"] = matched
        resolved["category_ids"] = matched_ids

    return {"resolved_entities": resolved, "semantic_context": semantic_context}
