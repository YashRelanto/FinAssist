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
    query = state.get("rewritten_query") or state["user_query"]

    # Step 1: Resolve dates in pure Python
    resolved_dates = _resolve_dates(query)

    # Build date hint for LLM
    date_hint = ""
    if resolved_dates["from"] or resolved_dates["to"]:
        date_hint = (
            f"\n\n[SYSTEM NOTE — pre-resolved dates: "
            f"from={resolved_dates['from']}, to={resolved_dates['to']}. "
            f"Use these exact values in date_range fields.]"
        )

    # Step 2: LLM extraction
    try:
        response = graph_chat_completion(
            node="entity_node",
            purpose="entity_extraction",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": ENTITY_EXTRACTION_SYSTEM},
                {"role": "user", "content": ENTITY_EXTRACTION_USER.format(
                    query=query, date_hint=date_hint)},
            ],
            response_format={"type": "json_object"},
            max_tokens=300,
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        entities = json.loads(raw)

        # Step 3: Python dates override LLM
        if resolved_dates["from"]:
            entities.setdefault("date_range", {})["from"] = resolved_dates["from"]
        if resolved_dates["to"]:
            entities.setdefault("date_range", {})["to"] = resolved_dates["to"]

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
        }

    return {"entities": entities}
