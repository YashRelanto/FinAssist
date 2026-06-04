"""Calendar-month analysis windows (1 / 3 / 5 months + all time)."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any

VALID_PERIODS = frozenset({"1m", "3m", "5m", "all"})
DEFAULT_PERIOD = "1m"
MONTHS_BY_PERIOD = {"1m": 1, "3m": 3, "5m": 5}


def normalize_period(period: str | None) -> str:
    key = (period or DEFAULT_PERIOD).strip().lower()
    return key if key in VALID_PERIODS else DEFAULT_PERIOD


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, months: int) -> date:
    """Shift by calendar months, clamping day to month length."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last_day))


def resolve_analysis_window(
    period: str | None = None,
    *,
    reference: date | None = None,
) -> dict[str, Any]:
    """
    Current analysis window (inclusive), month-aligned.

    1m on 5 Jun → 1 Jun … 5 Jun (month-to-date).
    3m on 5 Jun → 1 Apr … 5 Jun.
    all → from first transaction through today (start_date None).
    """
    today = reference or date.today()
    key = normalize_period(period)

    if key == "all":
        return {
            "period": key,
            "period_label": "All time",
            "start_date": None,
            "end_date": today.isoformat(),
            "comparison_start_date": None,
            "comparison_end_date": None,
            "months_in_window": None,
        }

    months = MONTHS_BY_PERIOD[key]
    start = add_months(month_start(today), -(months - 1))
    comp_start = add_months(start, -months)
    comp_end = add_months(today, -months)

    return {
        "period": key,
        "period_label": _period_label(key, start, today),
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "comparison_start_date": comp_start.isoformat(),
        "comparison_end_date": comp_end.isoformat(),
        "months_in_window": months,
    }


def _period_label(period: str, start: date, end: date) -> str:
    if period == "1m":
        return end.strftime("%B %Y") + " (month to date)"
    return f"{start.strftime('%b %Y')} – {end.strftime('%b %Y')}"


def filter_rows_by_date(
    rows: list[dict],
    *,
    start_date: str | None,
    end_date: str | None,
    date_field: str = "transaction_date",
) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        d = str(row.get(date_field) or "")[:10]
        if not d:
            continue
        if start_date and d < start_date:
            continue
        if end_date and d > end_date:
            continue
        out.append(row)
    return out


def sum_expenses_in_window(
    rows: list[dict],
    *,
    start_date: str | None,
    end_date: str | None,
) -> float:
    total = 0.0
    for row in filter_rows_by_date(rows, start_date=start_date, end_date=end_date):
        if (row.get("transaction_type") or "").lower() != "expense":
            continue
        total += abs(float(row.get("amount") or 0))
    return round(total, 2)
