"""
Entity extraction node — structured entity extraction with Python date resolver.

Integrates the pure-Python date resolver from the old query_planner.py
and uses LLM for remaining entity extraction.
"""

from __future__ import annotations

import json
import logging
import re
import calendar
from calendar import monthrange
from datetime import date, timedelta
from typing import Any, Dict, Optional

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import ENTITY_EXTRACTION_SYSTEM, ENTITY_EXTRACTION_USER
from app.utils.temporal_context import (
    analysis_window_from_range,
    get_time_context,
    resolve_period_token,
    resolve_relative_dates_from_query,
)

logger = logging.getLogger(__name__)

# ─── Month name → number map (preserved from query_planner.py) ───────────────

_MONTH_NAMES = {}
for _i in range(1, 13):
    _MONTH_NAMES[calendar.month_name[_i].lower()] = _i
    _MONTH_NAMES[calendar.month_abbr[_i].lower()] = _i
_MONTH_NAMES["sept"] = 9

_MONTH_REGEX = r"\b(" + "|".join(_MONTH_NAMES.keys()) + r")(?:\s+(\d{4}))?\b"


def _resolve_dates(question: str) -> Dict[str, Optional[str]]:
    """
    Pure-Python date resolver — resolves relative date expressions without LLM.

    Handles: today, yesterday, this/last week, this/last month, this/last year,
             month names with optional year, between <month> and <month>.
    """
    today = date.today()
    q = question.lower()

    if "today" in q:
        d = today.isoformat()
        return {"from": d, "to": d}

    if "yesterday" in q:
        d = (today - timedelta(days=1)).isoformat()
        return {"from": d, "to": d}

    if "last week" in q:
        monday = today - timedelta(days=today.weekday() + 7)
        sunday = monday + timedelta(days=6)
        return {"from": monday.isoformat(), "to": sunday.isoformat()}

    if "this week" in q:
        monday = today - timedelta(days=today.weekday())
        return {"from": monday.isoformat(), "to": today.isoformat()}
    
    """
    n_months_match = re.search(
        r"(?:last|past|previous)\s+(\d+)\s+months?",
        q,
    )

    if n_months_match:
        n = int(n_months_match.group(1))

        year = today.year
        month = today.month - n

        while month <= 0:
            month += 12
            year -= 1

        start_date = date(year, month, 1)

        return {
            "from": start_date.isoformat(),
            "to": today.isoformat(),
        }
    """
        
    if "last month" in q:
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return {"from": first_prev.isoformat(), "to": last_prev.isoformat()}

    if "this month" in q:
        first = today.replace(day=1)
        return {"from": first.isoformat(), "to": today.isoformat()}

    if "last year" in q:
        y = today.year - 1
        return {"from": f"{y}-01-01", "to": f"{y}-12-31"}

    if "this year" in q:
        return {"from": f"{today.year}-01-01", "to": today.isoformat()}

    quarter_m = re.search(r"\b(?:q|quarter)\s*([1-4])(?:\s*(?:of\s*)?(\d{4}))?\b", q)
    if quarter_m or "this quarter" in q or "last quarter" in q:
        q_num = int(quarter_m.group(1)) if quarter_m else ((today.month - 1) // 3 + 1)
        explicit_year = int(quarter_m.group(2)) if quarter_m and quarter_m.group(2) else None
        if "last quarter" in q:
            q_num -= 1
            year = explicit_year or today.year
            if q_num < 1:
                q_num = 4
                year -= 1
        else:
            year = explicit_year or today.year
        start_month = (q_num - 1) * 3 + 1
        end_month = start_month + 2
        last_day = monthrange(year, end_month)[1]
        return {
            "from": f"{year}-{start_month:02d}-01",
            "to": f"{year}-{end_month:02d}-{last_day:02d}",
        }

    # between <Month> and <Month> [YYYY]
    between_m = re.search(r"between\s+(\w+)\s+and\s+(\w+)(?:\s+(\d{4}))?", q)
    if between_m:
        m1 = _MONTH_NAMES.get(between_m.group(1).lower())
        m2 = _MONTH_NAMES.get(between_m.group(2).lower())
        y = int(between_m.group(3)) if between_m.group(3) else today.year
        if m1 and m2:
            last_day = monthrange(y, m2)[1]
            return {"from": f"{y}-{m1:02d}-01", "to": f"{y}-{m2:02d}-{last_day:02d}"}

    # <MonthName> [YYYY]
    month_m = re.search(_MONTH_REGEX, q)
    if month_m:
        m = _MONTH_NAMES[month_m.group(1)]
        if month_m.group(2):
            y = int(month_m.group(2))
        else:
            y = today.year
            if m > today.month:
                y -= 1
        last_day = monthrange(y, m)[1]
        return {"from": f"{y}-{m:02d}-01", "to": f"{y}-{m:02d}-{last_day:02d}"}

    return {"from": None, "to": None}


def entity_node(state: AgentState) -> dict:
    """
    Extracts structured entities from the user's query.

    1. Pure-Python date resolution (fast, zero LLM tokens)
    2. LLM extraction of merchants, categories, metric, group_by, etc.
    3. Merge: Python dates override LLM output
    """
    query = state.get("standalone_query") or state.get("rewritten_query") or state["user_query"]

    # Step 1: Resolve dates in pure Python
    resolved_dates = _resolve_dates(query)
    time_ctx = get_time_context()

    # Build date hint for LLM — always include today's date
    date_hint = (
        f"\n\n[TIME CONTEXT: Today is {time_ctx['current_date_display']} "
        f"({time_ctx['current_date']}). All relative dates must be computed from this date. "
        f"Do not assume 2024 or any stale year unless the user explicitly names it.]"
    )
    if resolved_dates["from"] or resolved_dates["to"]:
        date_hint += (
            f"\n[PRE-RESOLVED date_range: from={resolved_dates['from']}, "
            f"to={resolved_dates['to']}. Use these exact values.]"
        )

    # Step 2: LLM extraction
    try:
        response = graph_chat_completion(
            node="entity_node",
            purpose="entity_extraction",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": ENTITY_EXTRACTION_SYSTEM.format(**time_ctx)},
                {"role": "user", "content": ENTITY_EXTRACTION_USER.format(
                    query=query, date_hint=date_hint, **time_ctx)},
            ],
            response_format={"type": "json_object"},
            max_tokens=300,
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        entities = json.loads(raw)

        # Step 3: Resolve temporal.period tokens (e.g. last_two_months) if needed
        temporal = entities.get("temporal") or {}
        period_token = temporal.get("period")
        if period_token and not (resolved_dates["from"] and resolved_dates["to"]):
            token_dates = resolve_period_token(period_token)
            if token_dates.get("from") and token_dates.get("to"):
                resolved_dates = token_dates

        # Python-resolved dates always override LLM hallucinations
        if resolved_dates["from"]:
            entities.setdefault("date_range", {})["from"] = resolved_dates["from"]
        if resolved_dates["to"]:
            entities.setdefault("date_range", {})["to"] = resolved_dates["to"]

        entities.setdefault("financial", {"income": None, "expense": None, "savings": None, "emi": None})
        entities.setdefault("investments", {
            "stocks": [], "etfs": [], "mutual_funds": [], "sips": [],
            "bonds": [], "gold": [],
        })
        entities.setdefault("temporal", {"period": None, "fiscal_year": None})
        logger.info("[Node:entity] Extracted: %s", json.dumps(entities, default=str))

    except Exception as exc:
        logger.error("[Node:entity] Extraction failed: %s", exc)
        entities = {
            "transaction_type": None,
            "merchants": [],
            "categories": [],
            "date_range": resolved_dates,
            "metric": "list",
            "group_by": None,
            "sort": None,
            "limit": None,
            "comparison": None,
            "financial": {"income": None, "expense": None, "savings": None, "emi": None},
            "investments": {
                "stocks": [], "etfs": [], "mutual_funds": [], "sips": [],
                "bonds": [], "gold": [],
            },
            "temporal": {"period": None, "fiscal_year": None},
        }

    metadata = dict(state.get("metadata") or {})
    metadata["last_entities"] = entities
    metadata["time_context"] = time_ctx
    metadata["analysis_window"] = analysis_window_from_range(
        entities.get("date_range") if isinstance(entities, dict) else None
    )
    return {"entities": entities, "metadata": metadata}

