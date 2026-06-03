"""
NL2SQL Query Planner
====================
Converts a user's natural language question into a structured QuerySpec dict
that can be executed against Supabase by query_executor.py.

Two-phase approach:
  1. Pure-Python date resolution  — resolves relative expressions ("this month",
     "last week", "May", etc.) without any LLM call.
  2. LLM extraction               — extracts metric, transaction_type, merchant,
     category, limit, sort, group_by using the system prompt in prompts.py.

The LLM is given ALREADY-RESOLVED dates so it never has to guess calendar
arithmetic.  Date fields in the LLM output are merged with Python-resolved
values (Python wins when both are present).
"""

import json
import logging
import re
import calendar
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

import openai

from app.core.config import settings
from app.utils.prompts import NL2SQL_PLANNER_SYSTEM, NL2SQL_PLANNER_USER

logger = logging.getLogger(__name__)

# ─── Type alias ──────────────────────────────────────────────────────────────

QuerySpec = Dict[str, Any]

_EMPTY_SPEC: QuerySpec = {
    "metric": "list",
    "transaction_type": None,
    "merchant": None,
    "category": None,
    "date_from": None,
    "date_to": None,
    "limit": None,
    "sort": None,
    "group_by": None,
}

# ─── Month name → number map ─────────────────────────────────────────────────

_MONTH_NAMES = {}
for _i in range(1, 13):
    _MONTH_NAMES[calendar.month_name[_i].lower()] = _i
    _MONTH_NAMES[calendar.month_abbr[_i].lower()] = _i
_MONTH_NAMES["sept"] = 9  # Add common alternative abbreviation

_MONTH_REGEX = r"\b(" + "|".join(_MONTH_NAMES.keys()) + r")(?:\s+(\d{4}))?\b"


# ─── Pure-Python Date Resolver ────────────────────────────────────────────────

def _resolve_dates(question: str) -> Dict[str, Optional[str]]:
    """
    Scan the question text for recognised date expressions and return
    {"date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD"} or nulls.

    Handles:
      - today / yesterday
      - this week / last week
      - this month / last month
      - this year  / last year
      - <MonthName> [YYYY]            e.g. "May", "May 2026"
      - between <Month> and <Month>   e.g. "between Jan and March"
      - from <date> to <date>         (left as null — LLM handles specific dates)
    """
    today = date.today()
    q = question.lower()

    # ── today ──────────────────────────────────────────────────────────────
    if "today" in q:
        d = today.isoformat()
        return {"date_from": d, "date_to": d}

    # ── yesterday ─────────────────────────────────────────────────────────
    if "yesterday" in q:
        d = (today - timedelta(days=1)).isoformat()
        return {"date_from": d, "date_to": d}

    # ── last week ─────────────────────────────────────────────────────────
    if "last week" in q:
        # Monday–Sunday of the previous calendar week
        monday = today - timedelta(days=today.weekday() + 7)
        sunday = monday + timedelta(days=6)
        return {"date_from": monday.isoformat(), "date_to": sunday.isoformat()}

    # ── this week ─────────────────────────────────────────────────────────
    if "this week" in q:
        monday = today - timedelta(days=today.weekday())
        return {"date_from": monday.isoformat(), "date_to": today.isoformat()}

    # ── last month ────────────────────────────────────────────────────────
    if "last month" in q:
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return {"date_from": first_prev.isoformat(), "date_to": last_prev.isoformat()}

    # ── this month ────────────────────────────────────────────────────────
    if "this month" in q:
        first = today.replace(day=1)
        return {"date_from": first.isoformat(), "date_to": today.isoformat()}

    # ── last year ─────────────────────────────────────────────────────────
    if "last year" in q:
        y = today.year - 1
        return {"date_from": f"{y}-01-01", "date_to": f"{y}-12-31"}

    # ── this year ─────────────────────────────────────────────────────────
    if "this year" in q:
        return {"date_from": f"{today.year}-01-01", "date_to": today.isoformat()}

    # ── between <Month> and <Month> [YYYY] ───────────────────────────────
    between_m = re.search(
        r"between\s+(\w+)\s+and\s+(\w+)(?:\s+(\d{4}))?", q
    )
    if between_m:
        m1 = _MONTH_NAMES.get(between_m.group(1).lower())
        m2 = _MONTH_NAMES.get(between_m.group(2).lower())
        y = int(between_m.group(3)) if between_m.group(3) else today.year
        if m1 and m2:
            last_day = monthrange(y, m2)[1]
            return {
                "date_from": f"{y}-{m1:02d}-01",
                "date_to":   f"{y}-{m2:02d}-{last_day:02d}",
            }

    # ── <MonthName> [YYYY] ────────────────────────────────────────────────
    month_m = re.search(_MONTH_REGEX, q)
    if month_m:
        m = _MONTH_NAMES[month_m.group(1)]
        # Year: explicit > current year; but if month is in the future use last year
        if month_m.group(2):
            y = int(month_m.group(2))
        else:
            y = today.year
            if m > today.month:
                y -= 1            # "May" asked in Feb 2026 → May 2025
        last_day = monthrange(y, m)[1]
        return {
            "date_from": f"{y}-{m:02d}-01",
            "date_to":   f"{y}-{m:02d}-{last_day:02d}",
        }

    # ── No recognised expression ──────────────────────────────────────────
    return {"date_from": None, "date_to": None}


# ─── LLM Spec Extractor ───────────────────────────────────────────────────────

def _call_planner_llm(question: str, resolved_dates: Dict[str, Optional[str]]) -> QuerySpec:
    """
    Call the LLM with the planner system prompt and return the parsed QuerySpec.

    We inject the already-resolved date values into the user message so the
    model does not need to reason about calendar arithmetic.
    """
    # Enrich question with resolved dates as a hint
    date_hint = ""
    if resolved_dates["date_from"] or resolved_dates["date_to"]:
        date_hint = (
            f"\n\n[SYSTEM NOTE — pre-resolved dates: "
            f"date_from={resolved_dates['date_from']}, "
            f"date_to={resolved_dates['date_to']}. "
            f"Use these exact values in date_from/date_to fields of your JSON output.]"
        )

    user_content = NL2SQL_PLANNER_USER.format(question=question) + date_hint

    client = openai.OpenAI(
        api_key=settings.active_api_key,
        base_url=settings.active_base_url,
    )

    response = client.chat.completions.create(
        model=settings.active_chat_model,
        messages=[
            {"role": "system", "content": NL2SQL_PLANNER_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        temperature=0.0,    # Deterministic extraction
        max_tokens=256,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if the model wraps output despite instructions
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


# ─── Spec Validator / Sanitiser ──────────────────────────────────────────────

_VALID_METRICS = {"sum", "count", "average", "max", "min", "latest", "list"}
_VALID_TX_TYPES = {"expense", "income", None}
_VALID_SORTS = {"asc", "desc", "transaction_date_desc", None}
_VALID_GROUP_BY = {"category", "merchant", None}


def _sanitise(spec: Dict[str, Any]) -> QuerySpec:
    """
    Ensure the spec conforms to the expected shape and valid enum values.
    Unknown or invalid values are replaced with safe defaults.
    """
    sanitised: QuerySpec = dict(_EMPTY_SPEC)  # start from defaults

    metric = str(spec.get("metric", "list")).lower()
    sanitised["metric"] = metric if metric in _VALID_METRICS else "list"

    tx_type = spec.get("transaction_type")
    if isinstance(tx_type, str):
        tx_type = tx_type.lower()
    sanitised["transaction_type"] = tx_type if tx_type in _VALID_TX_TYPES else None

    sanitised["merchant"] = spec.get("merchant") or None
    sanitised["category"] = spec.get("category") or None

    sanitised["date_from"] = spec.get("date_from") or None
    sanitised["date_to"]   = spec.get("date_to")   or None

    limit = spec.get("limit")
    sanitised["limit"] = int(limit) if isinstance(limit, (int, float)) and limit > 0 else None

    sort_val = spec.get("sort")
    if isinstance(sort_val, str):
        sort_val = sort_val.lower()
    sanitised["sort"] = sort_val if sort_val in _VALID_SORTS else None

    group_by = spec.get("group_by")
    if isinstance(group_by, str):
        group_by = group_by.lower()
    sanitised["group_by"] = group_by if group_by in _VALID_GROUP_BY else None

    # Default limit for max/min metrics
    if sanitised["metric"] in {"max", "min", "latest"} and sanitised["limit"] is None:
        sanitised["limit"] = 1

    return sanitised


# ─── Public API ───────────────────────────────────────────────────────────────

async def plan_query(user_question: str) -> QuerySpec:
    """
    Convert a natural language financial question into a structured QuerySpec.

    Steps:
      1. Pure-Python date resolution (fast, zero LLM tokens)
      2. LLM extraction of all other fields
      3. Merge: Python-resolved dates override LLM date output
      4. Sanitise and return

    Falls back to a safe default spec on any error so the pipeline can
    always continue (caller may then use the fallback summary path).
    """
    try:
        # Step 1 — resolve dates in pure Python
        resolved_dates = _resolve_dates(user_question)

        # Step 2 — call LLM for remaining fields
        raw_spec = _call_planner_llm(user_question, resolved_dates)

        # Step 3 — Python dates take precedence over LLM guesses
        if resolved_dates["date_from"]:
            raw_spec["date_from"] = resolved_dates["date_from"]
        if resolved_dates["date_to"]:
            raw_spec["date_to"] = resolved_dates["date_to"]

        # Step 4 — sanitise
        spec = _sanitise(raw_spec)
        logger.info("[QueryPlanner] spec=%s", json.dumps(spec))
        return spec

    except json.JSONDecodeError as e:
        logger.warning("[QueryPlanner] LLM returned invalid JSON: %s", e)
    except Exception as e:
        logger.error("[QueryPlanner] Unexpected error: %s", e)

    # Fallback: minimal spec that will trigger the legacy summary path
    fallback = dict(_EMPTY_SPEC)
    fallback["metric"] = "list"
    logger.warning("[QueryPlanner] Returning fallback spec")
    return fallback
