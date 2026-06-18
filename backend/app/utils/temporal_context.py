"""Current time context and relative date-range resolution for chat analytics."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from app.utils.analysis_period import add_months, month_start

_WORD_TO_NUM = {
    "one": 1,
    "two": 2,
    "couple": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def get_time_context(*, reference: datetime | None = None) -> dict[str, str]:
    """Snapshot of 'now' for LLM prompts and metadata."""
    now = reference or datetime.now()
    today = now.date()
    return {
        "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_date": today.isoformat(),
        "current_date_display": today.strftime("%d %B %Y"),
        "current_year": str(today.year),
        "current_month": today.strftime("%B %Y"),
    }


def resolve_last_n_calendar_months(
    n: int,
    *,
    reference: date | None = None,
) -> tuple[str, str]:
    """
    Last N complete calendar months before the current month.

    Example: reference 2026-06-15, n=2 → 2026-04-01 … 2026-05-31 (April + May).
    """
    if n < 1:
        raise ValueError("n must be >= 1")

    today = reference or date.today()
    first_of_current = month_start(today)
    end = first_of_current - timedelta(days=1)
    start = add_months(month_start(end), -(n - 1))
    return start.isoformat(), end.isoformat()


def format_date_range_label(start: str | None, end: str | None) -> str:
    if not start and not end:
        return "All time"
    if start and end:
        start_d = date.fromisoformat(start[:10])
        end_d = date.fromisoformat(end[:10])
        if start_d.year == end_d.year and start_d.month == end_d.month:
            return start_d.strftime("%B %Y")
        return f"{start_d.strftime('%b %Y')} – {end_d.strftime('%b %Y')}"
    if start:
        return f"from {start}"
    return f"through {end}"


def analysis_window_from_range(
    date_range: dict[str, Any] | None,
    *,
    reference: date | None = None,
) -> dict[str, Any]:
    """Build a structured analysis window from entity date_range."""
    today = reference or date.today()
    dr = date_range or {}
    start = dr.get("from")
    end = dr.get("to")
    label = format_date_range_label(start, end)
    return {
        "start_date": start,
        "end_date": end or today.isoformat(),
        "period_label": label,
        **get_time_context(reference=datetime.combine(today, datetime.min.time())),
    }


def _parse_count(raw: str) -> int | None:
    key = raw.lower().strip()
    if key.isdigit():
        return int(key)
    return _WORD_TO_NUM.get(key)


def resolve_period_token(
    period: str | None,
    *,
    reference: date | None = None,
) -> dict[str, str | None]:
    """Map temporal.period tokens (e.g. last_two_months) to concrete ISO dates."""
    if not period:
        return {"from": None, "to": None}

    token = period.lower().strip().replace("-", "_").replace(" ", "_")
    today = reference or date.today()

    if token in ("this_month", "current_month"):
        return {"from": month_start(today).isoformat(), "to": today.isoformat()}

    if token in ("last_month", "previous_month"):
        first_this = month_start(today)
        last_prev = first_this - timedelta(days=1)
        return {"from": month_start(last_prev).isoformat(), "to": last_prev.isoformat()}

    if token in ("this_year", "current_year"):
        return {"from": f"{today.year}-01-01", "to": today.isoformat()}

    if token in ("last_year", "previous_year"):
        y = today.year - 1
        return {"from": f"{y}-01-01", "to": f"{y}-12-31"}

    match = re.match(r"last_(\d+|one|two|three|four|five|six|twelve)_months?", token)
    if match:
        n = _parse_count(match.group(1))
        if n:
            start, end = resolve_last_n_calendar_months(n, reference=today)
            return {"from": start, "to": end}

    if token in ("last_two_months", "past_two_months", "previous_two_months"):
        start, end = resolve_last_n_calendar_months(2, reference=today)
        return {"from": start, "to": end}

    if token in ("last_three_months", "past_three_months"):
        start, end = resolve_last_n_calendar_months(3, reference=today)
        return {"from": start, "to": end}

    return {"from": None, "to": None}


def resolve_relative_dates_from_query(
    question: str,
    *,
    reference: date | None = None,
) -> dict[str, str | None]:
    """
    Resolve relative date phrases in natural language to ISO date bounds.
    Returns {"from": ..., "to": ...} with nulls when no relative phrase matched.
    """
    today = reference or date.today()
    q = question.lower()

    last_n = re.search(
        r"\b(?:last|past|previous|recent)\s+"
        r"(\d+|one|two|couple|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+months?\b",
        q,
    )
    if last_n:
        n = _parse_count(last_n.group(1))
        if n:
            start, end = resolve_last_n_calendar_months(n, reference=today)
            return {"from": start, "to": end}

    if re.search(r"\b(?:last|past|previous)\s+couple\s+of\s+months?\b", q):
        start, end = resolve_last_n_calendar_months(2, reference=today)
        return {"from": start, "to": end}

    return {"from": None, "to": None}
