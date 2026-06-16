"""
Schema-driven clarification option sources for FR-4.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.constants.categories import PREDEFINED_MAIN_CATEGORIES
from app.utils.supabase_client import supabase_db

RISK_OPTIONS = ["Low", "Moderate", "High", "Other"]
PERIOD_OPTIONS = ["This month", "Last month", "Last 3 months", "Last 6 months", "Custom range"]
INVESTMENT_TYPE_OPTIONS = ["Mutual Funds", "Stocks", "ETFs", "SIPs", "Bonds", "Gold", "Other"]


def _fetch_db_categories(limit: int = 12) -> List[str]:
    try:
        if not supabase_db:
            return list(PREDEFINED_MAIN_CATEGORIES[:limit])
        resp = supabase_db.table("categories").select("main_category").limit(limit).execute()
        names = list({r["main_category"] for r in (resp.data or []) if r.get("main_category")})
        return sorted(names)[:limit] if names else list(PREDEFINED_MAIN_CATEGORIES[:limit])
    except Exception:
        return list(PREDEFINED_MAIN_CATEGORIES[:limit])


def _fetch_user_merchants(user_id: str, limit: int = 8) -> List[str]:
    try:
        if not supabase_db:
            return []
        resp = (
            supabase_db.table("transactions")
            .select("merchant_name")
            .eq("user_id", user_id)
            .not_.is_("merchant_name", "null")
            .limit(50)
            .execute()
        )
        merchants = list({r["merchant_name"] for r in (resp.data or []) if r.get("merchant_name")})
        return sorted(merchants)[:limit]
    except Exception:
        return []


def build_clarification_option_sources(state: Dict[str, Any]) -> Dict[str, Any]:
    """Build live option catalogs from DB schemas and user profile gaps."""
    user_id = state.get("user_id") or ""
    profile = state.get("user_profile") or {}
    intent = (state.get("intent") or "").upper()

    sources: Dict[str, Any] = {
        "categories": _fetch_db_categories(),
        "merchants": _fetch_user_merchants(user_id),
        "risk_appetite": RISK_OPTIONS,
        "time_periods": PERIOD_OPTIONS,
        "investment_types": INVESTMENT_TYPE_OPTIONS,
    }

    profile_gaps: List[str] = []
    if not profile.get("risk_profile"):
        profile_gaps.append("risk_profile")
    if not profile.get("income") and not profile.get("annual_income"):
        profile_gaps.append("income")
    if intent == "INVESTMENT_ANALYSIS" and not profile.get("goals"):
        profile_gaps.append("financial_goals")
    sources["profile_gaps"] = profile_gaps

    return sources


def format_option_sources_for_prompt(sources: Dict[str, Any]) -> str:
    return json.dumps(sources, default=str, indent=2)
