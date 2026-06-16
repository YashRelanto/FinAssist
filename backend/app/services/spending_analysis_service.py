"""Deterministic spending analysis from real transaction rows."""

from __future__ import annotations

import logging
from calendar import month_name
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

EXCLUDED_EXPENSE_CATEGORIES = frozenset({
    "income",
    "investments",
    "investment",
    "goals",
    "goal",
})

SPENDING_ANALYSIS_INTENTS = frozenset({
    "TREND_ANALYSIS",
    "SPENDING_SUMMARY",
    "COMPARISON",
    "TRANSACTION_QUERY",
    "CATEGORY_ANALYSIS",
    "MERCHANT_ANALYSIS",
    "HYBRID_QUERY",
    "ANOMALY_DETECTION",
})

EXPENSE_SELECT = (
    "transaction_id, transaction_date, amount, transaction_type, "
    "merchant_name, description, category_id, "
    "categories(main_category, sub_category)"
)


def fetch_expenses_in_window(
    user_id: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Load all expense transactions in range directly from Supabase (no row cap)."""
    from app.utils.supabase_client import supabase_db

    client = supabase_db
    if client is None:
        from app.utils.supabase_client import supabase
        client = supabase
    if client is None:
        logger.warning("[spending] No Supabase client — cannot fetch expenses")
        return []

    try:
        res = (
            client.table("transactions")
            .select(EXPENSE_SELECT)
            .eq("user_id", user_id)
            .eq("transaction_type", "expense")
            .gte("transaction_date", start_date)
            .lte("transaction_date", end_date)
            .order("transaction_date")
            .execute()
        )
        rows = res.data or []
        logger.info(
            "[spending] Fetched %d expense rows for user=%s window=%s..%s",
            len(rows), user_id[:8], start_date, end_date,
        )
        return rows
    except Exception as exc:
        logger.error("[spending] Expense fetch failed: %s", exc)
        return []


def format_inr(amount: float) -> str:
    return f"₹{amount:,.2f}"


def render_spending_analysis_answer(
    detailed: dict[str, Any],
    *,
    user_profile: dict[str, Any] | None = None,
) -> str:
    """
    Build the user-facing spending analysis entirely from verified computed data.
    No LLM — numbers cannot be hallucinated.
    """
    profile = user_profile or {}
    monthly = detailed.get("monthly_comparison") or []
    if not monthly:
        return "I couldn't find any expense transactions for the requested period."

    paragraphs: list[str] = []

    window = detailed.get("analysis_window") or {}
    label = window.get("period_label") or "the selected period"
    paragraphs.append(
        f"Here is your spending analysis for {label} "
        f"({detailed.get('transaction_count', 0)} expense transactions in total)."
    )

    for m in monthly:
        paragraphs.append(
            f"In {m['period_label']}, you spent {format_inr(m['total_spent_inr'])} "
            f"across {m['transaction_count']} transactions."
        )

    if len(monthly) >= 2:
        earlier, later = monthly[-2], monthly[-1]
        delta = later.get("vs_previous_month_inr")
        pct = later.get("vs_previous_month_pct")
        if delta is not None:
            direction = "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged"
            pct_str = f" ({abs(pct)}%)" if pct is not None else ""
            paragraphs.append(
                f"Comparing {earlier['period_label']} to {later['period_label']}, "
                f"spending {direction} by {format_inr(abs(delta))}{pct_str}."
            )
        for shift in later.get("category_shifts_vs_previous") or []:
            change = shift["change_inr"]
            if abs(change) < 0.01:
                continue
            verb = "rose" if change > 0 else "fell"
            paragraphs.append(
                f"{shift['category']} {verb} by {format_inr(abs(change))} "
                f"(from {format_inr(shift['earlier_inr'])} to {format_inr(shift['later_inr'])})."
            )

    for m in monthly:
        cats = m.get("top_categories") or []
        if cats:
            top = ", ".join(
                f"{c['name']} {format_inr(c['amount_inr'])}" for c in cats[:5]
            )
            paragraphs.append(f"Top categories in {m['period_label']}: {top}.")

    combined_merchants = detailed.get("combined_top_merchants") or []
    if combined_merchants:
        top_m = ", ".join(
            f"{m['name']} {format_inr(m['amount_inr'])}" for m in combined_merchants[:5]
        )
        paragraphs.append(f"Top merchants overall: {top_m}.")

    combined_cats = detailed.get("combined_category_breakdown") or []
    if combined_cats and len(monthly) == 1:
        top_c = ", ".join(
            f"{c['name']} {format_inr(c['amount_inr'])}" for c in combined_cats[:5]
        )
        paragraphs.append(f"Overall category breakdown: {top_c}.")

    primary_goal = profile.get("primary_goal") or ""
    goals = profile.get("goals") or []
    goal_line = ""
    if goals:
        g = goals[0]
        goal_line = (
            f" Your active goal '{g.get('goal_name')}' targets "
            f"{format_inr(float(g.get('target_amount') or 0))} "
            f"(saved {format_inr(float(g.get('current_amount') or 0))} so far)."
        )

    hints = detailed.get("suggestion_hints") or []
    rec_parts: list[str] = []
    if len(monthly) >= 2:
        later = monthly[-1]
        increases = [
            s for s in (later.get("category_shifts_vs_previous") or [])
            if s.get("change_inr", 0) > 0
        ]
        if increases:
            top_inc = increases[0]
            rec_parts.append(
                f"Focus on reducing {top_inc['category']} spending, which grew the most "
                f"({format_inr(top_inc['change_inr'])} month-over-month)."
            )
        delta = later.get("vs_previous_month_inr")
        if delta is not None and delta > 0:
            rec_parts.append(
                f"Your total spend rose {format_inr(delta)} last month — review discretionary "
                f"categories above to align with saving more."
            )
        elif delta is not None and delta < 0:
            rec_parts.append(
                f"You spent {format_inr(abs(delta))} less last month — keep this trend to build savings."
            )

    if primary_goal:
        rec_parts.append(f"Given your goal to '{primary_goal}', redirect any reduced spending into savings.")

    if rec_parts:
        paragraphs.append("Recommendations: " + " ".join(rec_parts) + goal_line)
    elif goal_line:
        paragraphs.append("Recommendations:" + goal_line)

    return " ".join(paragraphs)


def _category_from_row(row: dict) -> str:
    cat = row.get("main_category")
    if not cat:
        cat_obj = row.get("categories")
        if isinstance(cat_obj, dict):
            cat = cat_obj.get("main_category")
    return str(cat or "Uncategorized")


def is_valid_expense_row(row: dict) -> bool:
    """Expense transactions only — excludes income, investments, and goals."""
    if not isinstance(row, dict) or row.get("amount") is None:
        return False
    if (row.get("transaction_type") or "").lower() != "expense":
        return False
    return _category_from_row(row).lower().strip() not in EXCLUDED_EXPENSE_CATEGORIES


def filter_expense_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if is_valid_expense_row(r)]


def _date_window_from_state(state: dict) -> tuple[str | None, str | None]:
    resolved = state.get("resolved_entities") or state.get("entities") or {}
    date_range = resolved.get("date_range") or {}
    start = date_range.get("from")
    end = date_range.get("to")
    if not start and not end:
        window = (state.get("metadata") or {}).get("analysis_window") or {}
        start = window.get("start_date")
        end = window.get("end_date")
    if not start and not end:
        analytics_window = (state.get("analytics_results") or {}).get("analysis_window") or {}
        start = analytics_window.get("start_date")
        end = analytics_window.get("end_date")
    return start, end


def resolve_spending_analysis(state: dict) -> dict[str, Any] | None:
    """
    Return verified spending figures from pipeline state or a direct DB fetch.
    Used before any LLM answer so amounts cannot be invented.
    """
    from app.utils.temporal_context import analysis_window_from_range

    candidates: list[dict[str, Any] | None] = [
        (state.get("final_context") or {}).get("verified_spending_numbers"),
        (state.get("analytics_results") or {}).get("detailed_analysis"),
    ]
    for agent_result in state.get("agent_results") or []:
        candidates.append(
            (agent_result.get("analytics_results") or {}).get("detailed_analysis")
        )

    for detailed in candidates:
        if detailed and detailed.get("monthly_comparison"):
            return detailed

    user_id = state.get("user_id") or ""
    start, end = _date_window_from_state(state)
    if not (user_id and start and end):
        return None

    rows = fetch_expenses_in_window(user_id, start, end)
    if not rows:
        return None

    window = analysis_window_from_range({"from": start, "to": end})
    return build_detailed_spending_analysis(
        rows,
        analysis_window=window,
        user_profile=state.get("user_profile") or {},
    )


def _month_label(period: str) -> str:
    try:
        year, month = period.split("-")
        return f"{month_name[int(month)]} {year}"
    except (ValueError, IndexError, KeyError):
        return period


def _top_items(items: dict[str, float], limit: int = 5) -> list[dict[str, Any]]:
    return [
        {"name": name, "amount_inr": round(amount, 2)}
        for name, amount in sorted(items.items(), key=lambda x: x[1], reverse=True)[:limit]
    ]


def _category_shifts(
    earlier: dict[str, float],
    later: dict[str, float],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    shifts: list[dict[str, Any]] = []
    for cat in set(earlier) | set(later):
        before = earlier.get(cat, 0.0)
        after = later.get(cat, 0.0)
        delta = after - before
        if abs(delta) < 0.01:
            continue
        shifts.append({
            "category": cat,
            "earlier_inr": round(before, 2),
            "later_inr": round(after, 2),
            "change_inr": round(delta, 2),
            "change_pct": round(delta / before * 100, 1) if before else None,
        })
    shifts.sort(key=lambda x: abs(x["change_inr"]), reverse=True)
    return shifts[:limit]


def build_detailed_spending_analysis(
    rows: list[dict],
    *,
    analysis_window: dict[str, Any] | None = None,
    user_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a structured spending report from raw transaction rows.
    All amounts come from actual user data — no estimates.
    """
    expenses = filter_expense_rows(rows)

    monthly: dict[str, dict[str, Any]] = {}
    for row in expenses:
        period = str(row.get("transaction_date") or "")[:7]
        if len(period) != 7:
            continue
        amt = abs(float(row.get("amount") or 0))
        bucket = monthly.setdefault(
            period,
            {"total": 0.0, "count": 0, "categories": {}, "merchants": {}},
        )
        bucket["total"] += amt
        bucket["count"] += 1
        cat = _category_from_row(row)
        bucket["categories"][cat] = bucket["categories"].get(cat, 0.0) + amt
        merch = str(row.get("merchant_name") or row.get("description") or "Unknown")
        bucket["merchants"][merch] = bucket["merchants"].get(merch, 0.0) + amt

    sorted_periods = sorted(monthly.keys())
    monthly_comparison: list[dict[str, Any]] = []

    for i, period in enumerate(sorted_periods):
        data = monthly[period]
        entry: dict[str, Any] = {
            "period": period,
            "period_label": _month_label(period),
            "total_spent_inr": round(data["total"], 2),
            "transaction_count": data["count"],
            "top_categories": _top_items(data["categories"]),
            "top_merchants": _top_items(data["merchants"]),
        }
        if i > 0:
            prev_total = monthly_comparison[i - 1]["total_spent_inr"]
            delta = entry["total_spent_inr"] - prev_total
            entry["vs_previous_month_inr"] = round(delta, 2)
            entry["vs_previous_month_pct"] = (
                round(delta / prev_total * 100, 1) if prev_total else None
            )
            entry["category_shifts_vs_previous"] = _category_shifts(
                monthly[sorted_periods[i - 1]]["categories"],
                data["categories"],
            )
        monthly_comparison.append(entry)

    combined_categories: dict[str, float] = {}
    combined_merchants: dict[str, float] = {}
    for period in sorted_periods:
        for cat, amt in monthly[period]["categories"].items():
            combined_categories[cat] = combined_categories.get(cat, 0.0) + amt
        for merch, amt in monthly[period]["merchants"].items():
            combined_merchants[merch] = combined_merchants.get(merch, 0.0) + amt

    overall_total = round(sum(m["total_spent_inr"] for m in monthly_comparison), 2)
    month_count = len(monthly_comparison)

    suggestion_hints: list[str] = []
    if month_count >= 2:
        earlier = monthly_comparison[-2]
        later = monthly_comparison[-1]
        delta = later.get("vs_previous_month_inr", 0)
        if delta > 0:
            suggestion_hints.append(
                f"Total spending increased by ₹{delta:,.2f} ({later.get('vs_previous_month_pct')}%) "
                f"from {earlier['period_label']} to {later['period_label']}."
            )
            for shift in later.get("category_shifts_vs_previous") or []:
                if shift["change_inr"] > 0:
                    suggestion_hints.append(
                        f"{shift['category']} rose by ₹{shift['change_inr']:,.2f} "
                        f"(from ₹{shift['earlier_inr']:,.2f} to ₹{shift['later_inr']:,.2f})."
                    )
        elif delta < 0:
            suggestion_hints.append(
                f"Total spending decreased by ₹{abs(delta):,.2f} "
                f"from {earlier['period_label']} to {later['period_label']} — positive for savings."
            )

    primary_goal = (user_profile or {}).get("primary_goal") or ""
    if primary_goal and overall_total > 0:
        suggestion_hints.append(
            f"User's stated primary goal is '{primary_goal}' — tie recommendations to that goal."
        )

    return {
        "analysis_window": analysis_window or {},
        "transaction_count": len(expenses),
        "months_analysed": month_count,
        "overall_total_spent_inr": overall_total,
        "average_monthly_spend_inr": round(overall_total / month_count, 2) if month_count else 0.0,
        "monthly_comparison": monthly_comparison,
        "combined_category_breakdown": _top_items(combined_categories, limit=10),
        "combined_top_merchants": _top_items(combined_merchants, limit=10),
        "suggestion_hints": suggestion_hints[:8],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
