"""Deterministic spending analytics for the Analytics tab."""

from __future__ import annotations

import calendar
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from app.services.dashboard_metrics_service import (
    EXPENSE_TYPE,
    normalize_category_name,
    transaction_amount_value,
)
from app.utils.analysis_period import (
    filter_rows_by_date,
    resolve_analysis_window,
)
from app.utils.tab_logging import tab_debug

logger = logging.getLogger(__name__)

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _calendar_weekday_weekend_counts(
    start_date: str | None,
    end_date: str | None,
) -> tuple[int, int]:
    """Count Mon–Fri vs Sat–Sun calendar days in the analysis window."""
    if not start_date or not end_date:
        return 0, 0
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return 0, 0
    if end < start:
        return 0, 0

    weekday_days = 0
    weekend_days = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() >= 5:
            weekend_days += 1
        else:
            weekday_days += 1
        cursor += timedelta(days=1)
    return weekday_days, weekend_days


def _heatmap_intensity(amount: float, max_amount: float) -> int:
    if max_amount <= 0 or amount <= 0:
        return 0
    return min(5, max(1, round((amount / max_amount) * 5)))


def build_weekend_behavior_insight(
    wknd: dict[str, Any],
    heatmap: list[dict[str, Any]],
) -> str:
    """Narrate weekday vs weekend using per-day averages (matches the chart)."""
    mult = float(wknd.get("weekend_multiplier") or 0)
    wk_avg = float(wknd.get("weekday_avg_per_day") or 0)
    we_avg = float(wknd.get("weekend_avg_per_day") or 0)

    if wk_avg <= 0 and we_avg <= 0:
        return "Not enough spending data for weekday vs weekend comparison."

    if mult >= 1.1:
        text = f"Weekend spending averages {mult}× more per day than weekdays."
    elif 0 < mult < 0.9:
        text = f"Weekday spending averages {round(1 / mult, 2)}× more per day than weekends."
    else:
        text = "Weekday and weekend spending are balanced on a per-day basis."

    peak = max(heatmap, key=lambda x: float(x.get("amount") or 0), default=None) if heatmap else None
    if mult >= 1.1 and peak and peak.get("day") in ("Sat", "Sun"):
        text += f" Peak activity is on {peak['day']}."
    return text


def _category_from_row(row: dict[str, Any]) -> str:
    cats = row.get("categories") or {}
    return normalize_category_name(cats.get("main_category"))


def _merchant_from_row(row: dict[str, Any]) -> str:
    name = (row.get("merchant_name") or row.get("description") or "Unknown").strip()
    return name or "Unknown"


def filter_analytics_transactions(
    rows: list[dict[str, Any]],
    *,
    account_id: str | None = None,
    category_id: str | None = None,
    merchant: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    merchant_q = (merchant or "").strip().lower()
    for row in rows:
        if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
            continue
        if account_id and str(row.get("account_id") or "") != account_id:
            continue
        if category_id and str(row.get("category_id") or "") != category_id:
            continue
        if merchant_q:
            m = _merchant_from_row(row).lower()
            if merchant_q not in m:
                continue
        out.append(row)
    return out


def _month_label(month_key: str) -> str:
    try:
        y, m = month_key.split("-")
        return calendar.month_abbr[int(m)]
    except (ValueError, IndexError):
        return month_key


def _months_between(start: date, end: date, *, cap: int = 12) -> list[str]:
    months: list[str] = []
    cur = start.replace(day=1)
    end_month = end.replace(day=1)
    while cur <= end_month and len(months) < cap:
        months.append(cur.strftime("%Y-%m"))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


def _consecutive_growth_months(amounts: list[float]) -> int:
    if len(amounts) < 2:
        return 0
    streak = 0
    for i in range(len(amounts) - 1, 0, -1):
        if amounts[i] > amounts[i - 1]:
            streak += 1
        else:
            break
    return streak


def build_category_trends(
    rows: list[dict[str, Any]],
    *,
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    if not end_date:
        return []

    end_d = date.fromisoformat(end_date)
    start_d = date.fromisoformat(start_date) if start_date else end_d.replace(day=1)
    month_keys = _months_between(start_d, end_d)

    by_cat_month: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in filter_rows_by_date(rows, start_date=start_date, end_date=end_date):
        if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
            continue
        d = str(row.get("transaction_date") or "")[:10]
        mk = d[:7]
        if mk not in month_keys:
            continue
        cat = _category_from_row(row)
        by_cat_month[cat][mk] += transaction_amount_value(row.get("amount"), EXPENSE_TYPE)

    totals = {cat: sum(m.values()) for cat, m in by_cat_month.items()}
    sorted_cats = sorted(totals.keys(), key=lambda c: totals[c], reverse=True)

    trends: list[dict[str, Any]] = []
    for cat in sorted_cats:
        monthly = by_cat_month[cat]
        evolution = [
            {
                "month": mk,
                "label": _month_label(mk),
                "amount": round(monthly.get(mk, 0.0), 2),
            }
            for mk in month_keys
        ]
        amounts = [e["amount"] for e in evolution]
        mom_change_pct: float | None = None
        if len(amounts) >= 2 and amounts[-2] > 0:
            mom_change_pct = round(
                ((amounts[-1] - amounts[-2]) / amounts[-2]) * 100, 1
            )
        trends.append(
            {
                "category": cat,
                "total": round(totals[cat], 2),
                "monthly_evolution": evolution,
                "consecutive_growth_months": _consecutive_growth_months(amounts),
                "mom_change_pct": mom_change_pct,
            }
        )
    return trends


def build_category_share(
    rows: list[dict[str, Any]],
    *,
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    totals: dict[str, float] = defaultdict(float)
    sub_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in filter_rows_by_date(rows, start_date=start_date, end_date=end_date):
        if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
            continue
        cat = _category_from_row(row)
        amt = transaction_amount_value(row.get("amount"), EXPENSE_TYPE)
        totals[cat] += amt

        # Extract sub_category
        cats_obj = row.get("categories") or {}
        sub_cat = str(cats_obj.get("sub_category") or "General").strip() or "General"
        sub_totals[cat][sub_cat] += amt

    grand = sum(totals.values())
    if grand <= 0:
        return []

    result: list[dict[str, Any]] = []
    for name, amount in sorted(totals.items(), key=lambda x: x[1], reverse=True):
        # Build subcategory breakdown
        subs = sub_totals.get(name, {})
        sub_list = [
            {
                "sub_category": sub_name,
                "amount": round(sub_amount, 2),
                "pct": round((sub_amount / amount) * 100, 1) if amount > 0 else 0,
            }
            for sub_name, sub_amount in sorted(subs.items(), key=lambda x: x[1], reverse=True)
        ]

        result.append({
            "category": name,
            "amount": round(amount, 2),
            "pct": round((amount / grand) * 100, 1),
            "subcategories": sub_list,
        })

    return result


def build_merchant_analytics(
    transactions: list[dict[str, Any]],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    top_n: int = 5,
    comparison_start: str | None,
    comparison_end: str | None,
) -> dict[str, Any]:
    current: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0.0, "txn_count": 0}
    )
    prior: dict[str, float] = defaultdict(float)

    for row in filter_rows_by_date(transactions, start_date=start_date, end_date=end_date):
        if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
            continue
        name = _merchant_from_row(row)
        amt = transaction_amount_value(row.get("amount"), EXPENSE_TYPE)
        current[name]["total"] += amt
        current[name]["txn_count"] += 1

    for row in filter_rows_by_date(
        transactions, start_date=comparison_start, end_date=comparison_end
    ):
        if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
            continue
        name = _merchant_from_row(row)
        prior[name] += transaction_amount_value(row.get("amount"), EXPENSE_TYPE)

    top_merchants = sorted(
        [
            {
                "name": name,
                "total": round(data["total"], 2),
                "txn_count": data["txn_count"],
            }
            for name, data in current.items()
        ],
        key=lambda x: x["total"],
        reverse=True,
    )[:top_n]

    growth: list[dict[str, Any]] = []
    for name, data in current.items():
        cur = data["total"]
        prev = prior.get(name, 0.0)
        if prev <= 0 or cur <= 0:
            continue
        growth.append(
            {
                "name": name,
                "current_total": round(cur, 2),
                "prior_total": round(prev, 2),
                "growth_pct": round(((cur - prev) / prev) * 100, 1),
            }
        )
    growth.sort(key=lambda x: x["growth_pct"], reverse=True)

    period_total = sum(d["total"] for d in current.values())
    top5_total = sum(m["total"] for m in top_merchants)
    concentration_pct = round((top5_total / period_total) * 100, 1) if period_total > 0 else 0.0

    return {
        "top_merchants": top_merchants,
        "merchant_growth": growth[:10],
        "concentration": {"top_n": top_n, "pct_of_total": concentration_pct},
    }


def build_spending_behavior(
    rows: list[dict[str, Any]],
    *,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    weekday_total = 0.0
    weekend_total = 0.0
    day_totals: dict[int, float] = defaultdict(float)
    weekday_category_totals: dict[str, float] = defaultdict(float)
    weekend_category_totals: dict[str, float] = defaultdict(float)
    days_with_txns: set[str] = set()
    txn_count = 0

    for row in filter_rows_by_date(rows, start_date=start_date, end_date=end_date):
        if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
            continue
        d_str = str(row.get("transaction_date") or "")[:10]
        if not d_str:
            continue
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        amt = transaction_amount_value(row.get("amount"), EXPENSE_TYPE)
        txn_count += 1
        days_with_txns.add(d_str)
        wd = d.weekday()
        day_totals[wd] += amt
        cat_name = (row.get("categories") or {}).get("main_category") or row.get("main_category") or "Uncategorized"
        if wd >= 5:
            weekend_total += amt
            weekend_category_totals[cat_name] += amt
        else:
            weekday_total += amt
            weekday_category_totals[cat_name] += amt

    weekday_days, weekend_days = _calendar_weekday_weekend_counts(start_date, end_date)
    weekday_avg_per_day = (
        round(weekday_total / weekday_days, 2) if weekday_days > 0 else 0.0
    )
    weekend_avg_per_day = (
        round(weekend_total / weekend_days, 2) if weekend_days > 0 else 0.0
    )
    if weekday_avg_per_day > 0:
        weekend_multiplier = round(weekend_avg_per_day / weekday_avg_per_day, 2)
    elif weekend_avg_per_day > 0:
        weekend_multiplier = 1.0
    else:
        weekend_multiplier = 0.0

    max_day = max(day_totals.values()) if day_totals else 0.0
    day_of_week_heatmap = [
        {
            "day": WEEKDAY_NAMES[i],
            "day_index": i,
            "amount": round(day_totals.get(i, 0.0), 2),
            "intensity": _heatmap_intensity(day_totals.get(i, 0.0), max_day),
        }
        for i in range(7)
    ]
    peak_entry = max(day_of_week_heatmap, key=lambda x: x["amount"], default=None)
    peak_day = peak_entry["day"] if peak_entry and peak_entry["amount"] > 0 else None
    peak_amount = peak_entry["amount"] if peak_entry and peak_entry["amount"] > 0 else 0.0
    peak_insight = (
        f"Highest spend falls on {peak_day}s (₹{peak_amount:,.0f})."
        if peak_day
        else "Spending is spread across the week."
    )

    total_days = len(days_with_txns)
    avg_per_day = round(txn_count / total_days, 2) if total_days > 0 else 0.0

    weekday_vs_weekend = {
        "weekday_total": round(weekday_total, 2),
        "weekend_total": round(weekend_total, 2),
        "weekday_avg_per_day": weekday_avg_per_day,
        "weekend_avg_per_day": weekend_avg_per_day,
        "weekday_days_in_period": weekday_days,
        "weekend_days_in_period": weekend_days,
        "weekend_multiplier": weekend_multiplier,
        "weekend_elevated": weekend_multiplier >= 1.5,
        "weekday_categories": [{"category": k, "amount": round(v, 2)} for k, v in sorted(weekday_category_totals.items(), key=lambda x: x[1], reverse=True)[:5]],
        "weekend_categories": [{"category": k, "amount": round(v, 2)} for k, v in sorted(weekend_category_totals.items(), key=lambda x: x[1], reverse=True)[:5]],
    }

    return {
        "weekday_vs_weekend": weekday_vs_weekend,
        "weekend_insight": build_weekend_behavior_insight(weekday_vs_weekend, day_of_week_heatmap),
        "day_of_week_heatmap": day_of_week_heatmap,
        "peak_spending_day": peak_day,
        "peak_spending_day_amount": peak_amount,
        "peak_insight": peak_insight,
        "time_of_day_available": False,
        "transaction_frequency": {
            "avg_per_day": avg_per_day,
            "total_days_with_txns": total_days,
            "total_txns": txn_count,
        },
    }


def build_spending_analytics_payload(
    transactions: list[dict[str, Any]],
    *,
    period: str = "3m",
    account_id: str | None = None,
    category_id: str | None = None,
    merchant: str | None = None,
    reference: datetime | None = None,
) -> dict[str, Any]:
    ref = reference or datetime.now()
    window = resolve_analysis_window(period, reference=ref.date())
    filtered = filter_analytics_transactions(
        transactions,
        account_id=account_id,
        category_id=category_id,
        merchant=merchant,
    )

    start_date = window.get("start_date")
    end_date = window.get("end_date")
    total_spend = sum(
        transaction_amount_value(r.get("amount"), EXPENSE_TYPE)
        for r in filter_rows_by_date(filtered, start_date=start_date, end_date=end_date)
    )

    payload = {
        "success": True,
        "period": window.get("period"),
        "start_date": start_date,
        "end_date": end_date,
        "total_spend": round(total_spend, 2),
        "transaction_count": len(
            filter_rows_by_date(filtered, start_date=start_date, end_date=end_date)
        ),
        "filters": {
            "account_id": account_id,
            "category_id": category_id,
            "merchant": merchant,
        },
        "category_trends": build_category_trends(
            filtered, start_date=start_date, end_date=end_date
        ),
        "category_share": build_category_share(
            filtered, start_date=start_date, end_date=end_date
        ),
        "merchant_analytics": build_merchant_analytics(
            filtered,
            start_date=start_date,
            end_date=end_date,
            comparison_start=window.get("comparison_start_date"),
            comparison_end=window.get("comparison_end_date"),
        ),
        "spending_behavior": build_spending_behavior(
            filtered, start_date=start_date, end_date=end_date
        ),
    }
    tab_debug(
        "analytics",
        "aggregated period=%s total_spend=%s categories=%d merchants=%d",
        window.get("period"),
        payload["total_spend"],
        len(payload["category_trends"]),
        len(payload["merchant_analytics"].get("top_merchants") or []),
    )
    return payload
