"""Dashboard metric calculations aligned with public schema transaction types."""

from __future__ import annotations

from collections import defaultdict
import calendar
from datetime import date, datetime, timedelta
from typing import Any

from app.utils.analysis_period import (
    ALL_DASHBOARD_PERIODS,
    add_months,
    filter_rows_by_date,
    month_start,
    normalize_period,
    resolve_analysis_window,
    sum_expenses_in_window,
)

INCOME_TYPE = "income"
EXPENSE_TYPE = "expense"
TRANSFER_TYPE = "transfer"

# Display normalization (DB category names → UI palette keys)
CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "Financial Expense": "Financial Expense",
    "Financial Expenses": "Financial Expense",
    "Communication/PC": "Communication/PC",
    "others": "Others",
    "Others": "Others",
}


def normalize_category_name(name: str | None) -> str:
    if not name:
        return "Others"
    return CATEGORY_DISPLAY_NAMES.get(name, name)


def transaction_amount_value(raw_amount: Any, transaction_type: str) -> float:
    """Return a positive magnitude for aggregation by type."""
    value = abs(float(raw_amount or 0))
    if value == 0:
        return 0.0
    return value


def month_key_from_date(date_value: Any) -> str:
    """Extract YYYY-MM from ISO date string or date object."""
    if date_value is None:
        return ""
    text = str(date_value)
    return text[:7] if len(text) >= 7 else ""


def aggregate_monthly_stats(transactions: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """
    Sum income and expense per calendar month.
    Transfers are excluded from both buckets.
    """
    monthly: dict[str, dict[str, float]] = defaultdict(
        lambda: {"income": 0.0, "expense": 0.0}
    )
    for row in transactions:
        tx_type = (row.get("transaction_type") or "").lower()
        if tx_type == TRANSFER_TYPE:
            continue
        month = month_key_from_date(row.get("transaction_date"))
        if not month:
            continue
        amount = transaction_amount_value(row.get("amount"), tx_type)
        if tx_type == INCOME_TYPE:
            monthly[month]["income"] += amount
        elif tx_type == EXPENSE_TYPE:
            monthly[month]["expense"] += amount
    return dict(monthly)


def compute_summary(
    accounts: list[dict[str, Any]],
    monthly_stats: dict[str, dict[str, float]],
    *,
    reference: datetime | None = None,
    profile_income: float = 0.0,
) -> dict[str, float]:
    ref = reference or datetime.now()
    current_month = ref.strftime("%Y-%m")
    curr = monthly_stats.get(current_month, {"income": 0.0, "expense": 0.0})
    income = profile_income if profile_income > 0.0 else curr["income"]
    expense = curr["expense"]
    net = income - expense
    savings_rate = round((net / income) * 100, 1) if income > 0 else 0.0
    # Do not include credit card borrowed amount in "current balance".
    # Credit cards represent outstanding borrowed (often stored as negative balance).
    total_balance = 0.0
    for acc in accounts:
        if (acc.get("account_type") or "").lower() == "credit_card":
            continue
        total_balance += float(acc.get("current_balance") or 0)
    return {
        "total_balance": total_balance,
        "monthly_income": income,
        "monthly_expenses": expense,
        "net_savings": net,
        "savings_rate": savings_rate,
    }



def build_chart_data(
    monthly_stats: dict[str, dict[str, float]],
    *,
    last_n_months: int = 7,
    reference: datetime | None = None,
) -> list[dict[str, Any]]:
    ref = reference or datetime.now()
    current_month = ref.strftime("%Y-%m")
    months = sorted(monthly_stats.keys())
    if current_month not in months and current_month:
        months.append(current_month)
    months = sorted(set(months))[-last_n_months:]
    chart: list[dict[str, Any]] = []
    for month in months:
        stats = monthly_stats.get(month, {"income": 0.0, "expense": 0.0})
        income = stats["income"]
        expense = stats["expense"]
        chart.append(
            {
                "name": datetime.strptime(month, "%Y-%m").strftime("%b"),
                "month": month,
                "income": income,
                "expense": expense,
                "net": income - expense,
            }
        )
    return chart


def format_recent_transactions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recent: list[dict[str, Any]] = []
    for row in rows:
        categories = row.get("categories") or {}
        accounts = row.get("accounts") or {}
        tx_type = (row.get("transaction_type") or EXPENSE_TYPE).lower()
        raw_amount = float(row.get("amount") or 0)
        display_amount = transaction_amount_value(raw_amount, tx_type)
        if tx_type == EXPENSE_TYPE:
            display_amount = -display_amount
        recent.append(
            {
                "id": row["transaction_id"],
                "date": row["transaction_date"],
                "merchant": row.get("merchant_name") or row.get("description") or "Unknown",
                "amount": display_amount,
                "type": tx_type,
                "category": normalize_category_name(categories.get("main_category")),
                "subCategory": categories.get("sub_category") or "General",
                "account": accounts.get("account_name") or "Unknown",
            }
        )
    return recent


def aggregate_expense_by_category(
    transactions: list[dict[str, Any]],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Expense totals by main category for a date window."""
    totals: dict[str, float] = defaultdict(float)
    for row in transactions:
        if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
            continue
        date_str = str(row.get("transaction_date") or "")
        if start_date and date_str < start_date:
            continue
        if end_date and date_str > end_date:
            continue
        cat = normalize_category_name(
            (row.get("categories") or {}).get("main_category")
        )
        totals[cat] += transaction_amount_value(row.get("amount"), EXPENSE_TYPE)
    return [
        {"name": name, "value": value}
        for name, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def compute_budget_utilization(
    budgets: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    *,
    reference: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    For each active budget, sum matching category expenses within the budget window.

    Expenses match on main category (all subcategories) and the normalized period
    window so mid-month budget creation still counts earlier month spend.
    """
    ref = reference or datetime.now()
    today = ref.date() if hasattr(ref, "date") else ref
    today_str = today.isoformat() if isinstance(today, date) else ref.strftime("%Y-%m-%d")
    result: list[dict[str, Any]] = []

    for budget in budgets:
        start, end = normalize_budget_window(budget, reference=today)
        if end < today_str and budget.get("end_date"):
            continue
        if start > today_str:
            continue

        limit = float(budget.get("amount") or 0)
        spent = 0.0
        for row in transactions:
            if not _transaction_matches_budget(row, budget):
                continue
            date_str = str(row.get("transaction_date") or "")[:10]
            if date_str < start or date_str > end:
                continue
            spent += transaction_amount_value(row.get("amount"), EXPENSE_TYPE)

        utilization = round((spent / limit) * 100, 1) if limit > 0 else 0.0
        threshold = float(budget.get("alert_threshold") or 80)
        categories = budget.get("categories") or {}
        result.append(
            {
                "id": budget.get("budget_id"),
                "budget_name": budget.get("budget_name"),
                "category": normalize_category_name(categories.get("main_category")),
                "limit": limit,
                "spent": round(spent, 2),
                "utilization_pct": utilization,
                "alert_threshold": threshold,
                "over_budget": utilization >= 100,
                "alert": utilization >= threshold,
            }
        )
    return sorted(result, key=lambda item: item["utilization_pct"], reverse=True)


def resolve_budget_period_dates(
    period: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    reference: date | None = None,
) -> tuple[str, str]:
    """Return inclusive start/end dates aligned to the budget period (calendar month by default)."""
    ref = reference or date.today()
    if start_date and end_date:
        return start_date, end_date

    period_key = (period or "monthly").strip().lower()
    if period_key == "weekly":
        week_start = ref - timedelta(days=ref.weekday())
        week_end = week_start + timedelta(days=6)
        return week_start.isoformat(), week_end.isoformat()
    if period_key == "yearly":
        return date(ref.year, 1, 1).isoformat(), date(ref.year, 12, 31).isoformat()

    start = month_start(ref)
    last_day = calendar.monthrange(ref.year, ref.month)[1]
    end = date(ref.year, ref.month, last_day)
    return start.isoformat(), end.isoformat()


def normalize_budget_window(
    budget: dict[str, Any],
    *,
    reference: date | None = None,
) -> tuple[str, str]:
    """
    Normalize stored budget dates to the full active period window.

    Monthly budgets always use the calendar month containing the start date so
    existing transactions earlier in the month count toward utilization.
    """
    ref = reference or date.today()
    period = (budget.get("period") or "monthly").strip().lower()
    raw_start = str(budget.get("start_date") or ref.isoformat())
    raw_end = str(budget.get("end_date") or ref.isoformat())

    if period == "monthly":
        start_dt = datetime.strptime(raw_start[:10], "%Y-%m-%d").date()
        end_dt = datetime.strptime(raw_end[:10], "%Y-%m-%d").date()
        month_begin = month_start(start_dt)
        last_day = calendar.monthrange(end_dt.year, end_dt.month)[1]
        month_end = date(end_dt.year, end_dt.month, last_day)
        return month_begin.isoformat(), month_end.isoformat()

    if period == "yearly":
        start_dt = datetime.strptime(raw_start[:10], "%Y-%m-%d").date()
        return date(start_dt.year, 1, 1).isoformat(), date(start_dt.year, 12, 31).isoformat()

    if period == "weekly":
        start_dt = datetime.strptime(raw_start[:10], "%Y-%m-%d").date()
        week_start = start_dt - timedelta(days=start_dt.weekday())
        week_end = week_start + timedelta(days=6)
        return week_start.isoformat(), week_end.isoformat()

    return raw_start[:10], raw_end[:10]


def _transaction_matches_budget(row: dict[str, Any], budget: dict[str, Any]) -> bool:
    if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
        return False

    row_cat_id = row.get("category_id")
    budget_cat_id = budget.get("category_id")
    if budget_cat_id and row_cat_id == budget_cat_id:
        return True

    budget_main = normalize_category_name((budget.get("categories") or {}).get("main_category"))
    row_main = normalize_category_name((row.get("categories") or {}).get("main_category"))
    if budget_main and row_main and budget_main == row_main:
        return True

    return False


def compute_net_savings(transactions: list[dict[str, Any]]) -> float:
    """Cumulative income minus expenses (ignores transfers)."""
    income = 0.0
    expense = 0.0
    for row in transactions:
        tx_type = (row.get("transaction_type") or "").lower()
        if tx_type == TRANSFER_TYPE:
            continue
        amount = transaction_amount_value(row.get("amount"), tx_type)
        if tx_type == INCOME_TYPE:
            income += amount
        elif tx_type == EXPENSE_TYPE:
            expense += amount
    return round(max(income - expense, 0.0), 2)


def compute_savings_trajectory(
    transactions: list[dict[str, Any]],
    *,
    reference: datetime | None = None,
) -> dict[str, Any]:
    """Month-over-month net savings for the Budget & Goals trajectory card."""
    ref = reference or datetime.now()
    stats = aggregate_monthly_stats(transactions)
    current_month = ref.strftime("%Y-%m")

    if ref.month == 1:
        prev_month = f"{ref.year - 1}-12"
    else:
        prev_month = f"{ref.year}-{ref.month - 1:02d}"

    cur = stats.get(current_month, {"income": 0.0, "expense": 0.0})
    prev = stats.get(prev_month, {"income": 0.0, "expense": 0.0})
    current_net = cur["income"] - cur["expense"]
    prev_net = prev["income"] - prev["expense"]

    if prev_net > 0:
        growth_pct = round(((current_net - prev_net) / prev_net) * 100)
    elif current_net > 0:
        growth_pct = 100
    else:
        growth_pct = 0

    has_data = any(
        (row.get("transaction_type") or "").lower() in (INCOME_TYPE, EXPENSE_TYPE)
        for row in transactions
    )

    if not has_data:
        description = (
            "Once you log income and expenses, we will project your savings "
            "trajectory from your real transaction history."
        )
    elif current_net >= prev_net:
        description = (
            f"You saved {max(growth_pct, 0)}% more this month than last month. "
            f"Net savings this month: {round(current_net, 2):,.2f} "
            f"(income {round(cur['income'], 2):,.2f} minus expenses "
            f"{round(cur['expense'], 2):,.2f})."
        )
    else:
        description = (
            f"Net savings this month are {round(current_net, 2):,.2f}, "
            f"down from {round(prev_net, 2):,.2f} last month. "
            "Review category budgets below to stay on track."
        )

    stroke_pct = min(100, max(0, growth_pct + 50)) if has_data else 0

    return {
        "has_data": has_data,
        "monthly_income": round(cur["income"], 2),
        "monthly_expenses": round(cur["expense"], 2),
        "monthly_net_savings": round(current_net, 2),
        "previous_month_net": round(prev_net, 2),
        "savings_growth_pct": growth_pct,
        "title": "Financial Trajectory" if has_data else "No Trajectory Data Yet",
        "description": description,
        "stroke_pct": stroke_pct,
    }


def format_goals_for_ui(goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    icons = ["Target", "ShieldCheck", "PlaneTakeoff", "Laptop"]
    colors = ["bg-primary", "bg-secondary", "bg-tertiary", "bg-outline"]
    formatted: list[dict[str, Any]] = []
    for index, goal in enumerate(goals):
        target = float(goal.get("target_amount") or 0)
        current = float(goal.get("current_amount") or 0)
        progress_pct = round((current / target) * 100) if target > 0 else 0
        formatted.append(
            {
                "id": goal.get("goal_id"),
                "userId": goal.get("user_id"),
                "label": goal.get("goal_name"),
                "sub": goal.get("description") or "",
                "target": target,
                "current": current,
                "date": goal.get("target_date"),
                "status": goal.get("status"),
                "progress_pct": min(progress_pct, 100),
                "icon": icons[index % len(icons)],
                "color": colors[index % len(colors)],
            }
        )
    return formatted


def build_budget_goals_payload(
    *,
    budgets: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    reference: datetime | None = None,
) -> dict[str, Any]:
    ref = reference or datetime.now()
    trajectory = compute_savings_trajectory(transactions, reference=ref)
    return {
        "success": True,
        "budget_utilization": compute_budget_utilization(
            budgets, transactions, reference=ref
        ),
        "goals": format_goals_for_ui(goals),
        "trajectory": trajectory,
    }


def compute_summary_for_window(
    accounts: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    *,
    window: dict[str, Any],
    profile_income: float = 0.0,
    profile_fixed_rent: float = 0.0,
    profile_fixed_emi: float = 0.0,
) -> dict[str, float]:
    """Income/expense/net for the selected calendar analysis window.

    - `monthly_income` is taken directly from the user_profiles table (stagnant).
    - `fixed_expense` is the sum of `fixed_rent` + `fixed_emi` from the profile.
    - `net_inflow` / `net_outflow` are calculated from transactions within the window.
    - `net_savings` = `net_inflow` - `net_outflow` and `savings_rate` is relative to `monthly_income`.
    """
    rows = transactions
    income_tx = 0.0
    expense_tx = 0.0
    for row in filter_rows_by_date(
        rows,
        start_date=window.get("start_date"),
        end_date=window.get("end_date"),
    ):
        tx_type = (row.get("transaction_type") or "").lower()
        if tx_type == TRANSFER_TYPE:
            continue
        amount = transaction_amount_value(row.get("amount"), tx_type)
        if tx_type == INCOME_TYPE:
            income_tx += amount
        elif tx_type == EXPENSE_TYPE:
            expense_tx += amount

    # Monthly income is always taken from the profile (stagnant)
    monthly_income = float(profile_income or 0.0)
    fixed_expense = float((profile_fixed_rent or 0.0) + (profile_fixed_emi or 0.0))

    net_inflow = income_tx
    net_outflow = expense_tx
    net = net_inflow - net_outflow
    savings_rate = round((net / monthly_income) * 100, 1) if monthly_income > 0 else 0.0

    comp_start = window.get("comparison_start_date")
    comp_end = window.get("comparison_end_date")
    comp_expense = (
        sum_expenses_in_window(rows, start_date=comp_start, end_date=comp_end)
        if comp_start and comp_end
        else 0.0
    )
    expense_change_pct = (
        round((expense_tx - comp_expense) / comp_expense * 100)
        if comp_expense > 0
        else None
    )

    total_balance = 0.0
    for acc in accounts:
        if (acc.get("account_type") or "").lower() == "credit_card":
            continue
        total_balance += float(acc.get("current_balance") or 0)

    # Preserve the existing `monthly_expenses` key for compatibility while adding
    # new fields requested by the UI and placing them in the desired order.
    return {
        "total_balance": total_balance,
        "monthly_income": round(monthly_income, 2),
        "fixed_expense": round(fixed_expense, 2),
        "net_inflow": round(net_inflow, 2),
        "net_outflow": round(net_outflow, 2),
        "monthly_expenses": round(expense_tx, 2),
        "expense_change_pct": expense_change_pct,
        "net_savings": round(net, 2),
        "savings_rate": savings_rate,
    }


def _calendar_months_in_window(window: dict[str, Any]) -> list[str]:
    """Every YYYY-MM from window start through end (inclusive), month-aligned."""
    start_str = window.get("start_date")
    end_str = (window.get("end_date") or date.today().isoformat())[:10]
    if not start_str:
        return []
    start_dt = datetime.strptime(start_str[:10], "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
    months: list[str] = []
    cursor = month_start(start_dt)
    end_month = month_start(end_dt)
    while cursor <= end_month:
        months.append(cursor.strftime("%Y-%m"))
        cursor = add_months(cursor, 1)
    return months


def build_daily_chart_data_for_window(
    transactions: list[dict[str, Any]],
    *,
    window: dict[str, Any],
) -> list[dict[str, Any]]:
    """Daily expense/income points for each day in a single-month analysis window."""
    start_str = window.get("start_date")
    end_str = (window.get("end_date") or date.today().isoformat())[:10]
    if not start_str:
        return []

    daily: dict[str, dict[str, float]] = defaultdict(
        lambda: {"income": 0.0, "expense": 0.0}
    )
    for row in filter_rows_by_date(
        transactions,
        start_date=start_str,
        end_date=end_str,
    ):
        tx_type = (row.get("transaction_type") or "").lower()
        if tx_type == TRANSFER_TYPE:
            continue
        day = str(row.get("transaction_date") or "")[:10]
        if not day:
            continue
        amount = transaction_amount_value(row.get("amount"), tx_type)
        if tx_type == INCOME_TYPE:
            daily[day]["income"] += amount
        elif tx_type == EXPENSE_TYPE:
            daily[day]["expense"] += amount

    start_dt = datetime.strptime(start_str[:10], "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
    chart: list[dict[str, Any]] = []
    cursor = start_dt
    while cursor <= end_dt:
        day = cursor.isoformat()
        stats = daily.get(day, {"income": 0.0, "expense": 0.0})
        income = stats["income"]
        expense = stats["expense"]
        chart.append(
            {
                "name": cursor.strftime("%d"),
                "date": day,
                "income": income,
                "expense": expense,
                "net": income - expense,
            }
        )
        cursor += timedelta(days=1)
    return chart


def build_chart_data_for_window(
    monthly_stats: dict[str, dict[str, float]],
    *,
    window: dict[str, Any],
    transactions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Expense/income points for the analysis window (daily for 1m, monthly otherwise)."""
    period = window.get("period", "1m")
    if period == "1m" and transactions is not None:
        return build_daily_chart_data_for_window(transactions, window=window)

    if period == "all":
        months = sorted(monthly_stats.keys()) if monthly_stats else []
    else:
        months = _calendar_months_in_window(window)

    if not months:
        return []

    chart: list[dict[str, Any]] = []
    for month in months[-12:]:
        stats = monthly_stats.get(month, {"income": 0.0, "expense": 0.0})
        income = stats["income"]
        expense = stats["expense"]
        chart.append(
            {
                "name": datetime.strptime(month, "%Y-%m").strftime("%b %Y"),
                "month": month,
                "income": income,
                "expense": expense,
                "net": income - expense,
            }
        )
    return chart


def aggregate_top_spending_by_merchant(
    transactions: list[dict[str, Any]],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Top merchants by total expense amount within the analysis window."""
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for row in filter_rows_by_date(
        transactions,
        start_date=start_date,
        end_date=end_date,
    ):
        if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
            continue
        merchant = (
            row.get("merchant_name") or row.get("description") or "Unknown"
        ).strip() or "Unknown"
        amount = transaction_amount_value(row.get("amount"), EXPENSE_TYPE)
        totals[merchant] += amount
        counts[merchant] += 1
    return [
        {
            "merchant": name,
            "total": round(amount, 2),
            "count": counts[name],
        }
        for name, amount in sorted(totals.items(), key=lambda item: item[1], reverse=True)[
            :limit
        ]
    ]


def detect_spending_anomalies(
    transactions: list[dict[str, Any]],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    threshold_ratio: float = 1.5,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Flag expense transactions that exceed the merchant average by a threshold."""
    merchant_amounts: dict[str, list[float]] = defaultdict(list)
    window_rows: list[dict[str, Any]] = []

    for row in filter_rows_by_date(
        transactions,
        start_date=start_date,
        end_date=end_date,
    ):
        if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
            continue
        merchant = (
            row.get("merchant_name") or row.get("description") or "Unknown"
        ).strip() or "Unknown"
        amount = transaction_amount_value(row.get("amount"), EXPENSE_TYPE)
        if amount <= 0:
            continue
        merchant_amounts[merchant].append(amount)
        window_rows.append({"merchant": merchant, "amount": amount})

    anomalies: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for item in window_rows:
        merchant = item["merchant"]
        amount = item["amount"]
        amounts = merchant_amounts[merchant]
        if len(amounts) < 2:
            continue
        avg = sum(amounts) / len(amounts)
        if amount < avg * threshold_ratio:
            continue
        key = (merchant, amount)
        if key in seen:
            continue
        seen.add(key)
        anomalies.append(
            {
                "merchant": merchant,
                "amount": round(amount, 2),
                "avg_amount": round(avg, 2),
                "pct_above_avg": round(((amount - avg) / avg) * 100),
            }
        )

    anomalies.sort(key=lambda row: row["pct_above_avg"], reverse=True)
    return anomalies[:limit]


def _health_label(score: int) -> str:
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Fair"
    return "Needs Work"


def compute_financial_health(
    summary: dict[str, float],
    accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive a 0–100 health score from real profile, balance, and spend data."""
    monthly_income = float(summary.get("monthly_income") or 0)
    net_savings = float(summary.get("net_savings") or 0)
    savings_rate = float(summary.get("savings_rate") or 0)
    fixed_expense = float(summary.get("fixed_expense") or 0)
    net_outflow = float(summary.get("net_outflow") or 0)
    total_balance = float(summary.get("total_balance") or 0)

    debt_to_income = (
        round((fixed_expense / monthly_income) * 100, 1) if monthly_income > 0 else 0.0
    )
    monthly_burn = fixed_expense if fixed_expense > 0 else net_outflow
    emergency_months: float | None = None
    if monthly_burn > 0 and total_balance > 0:
        emergency_months = round(total_balance / monthly_burn, 1)

    utilizations: list[float] = []
    for acc in accounts:
        if (acc.get("account_type") or "").lower() != "credit_card":
            continue
        credit_limit = float(acc.get("credit_limit") or 0)
        if credit_limit <= 0:
            continue
        borrowed = abs(float(acc.get("current_balance") or 0))
        utilizations.append(borrowed / credit_limit)
    avg_credit_util = (
        round(sum(utilizations) / len(utilizations) * 100, 1) if utilizations else None
    )

    score_parts: list[float] = []
    if monthly_income > 0:
        score_parts.append(min(40.0, max(0.0, savings_rate * 0.4)))
    if debt_to_income <= 30:
        score_parts.append(25.0)
    elif debt_to_income <= 50:
        score_parts.append(15.0)
    elif debt_to_income <= 70:
        score_parts.append(8.0)
    if emergency_months is not None:
        if emergency_months >= 6:
            score_parts.append(20.0)
        elif emergency_months >= 3:
            score_parts.append(12.0)
        elif emergency_months >= 1:
            score_parts.append(6.0)
    if avg_credit_util is not None:
        if avg_credit_util <= 30:
            score_parts.append(15.0)
        elif avg_credit_util <= 50:
            score_parts.append(10.0)
        elif avg_credit_util <= 75:
            score_parts.append(5.0)

    score = min(100, round(sum(score_parts)))
    return {
        "score": score,
        "label": _health_label(score),
        "savings_rate": savings_rate,
        "debt_to_income_pct": debt_to_income,
        "net_savings": round(net_savings, 2),
        "emergency_buffer_months": emergency_months,
        "avg_credit_utilization_pct": avg_credit_util,
        "total_liquid_balance": round(total_balance, 2),
    }


def compute_overall_financial_health(
    *,
    accounts: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    profile_income: float = 0.0,
    profile_fixed_rent: float = 0.0,
    profile_fixed_emi: float = 0.0,
    reference: datetime | None = None,
) -> dict[str, Any]:
    """Period-independent health score using trailing 6-month average spend."""
    ref = reference or datetime.now()
    ref_date = ref.date() if hasattr(ref, "date") else ref
    fixed_expense = float(profile_fixed_rent or 0) + float(profile_fixed_emi or 0)
    monthly_income = float(profile_income or 0)

    monthly_stats = aggregate_monthly_stats(transactions)
    recent_months: list[str] = []
    cursor = month_start(ref_date)
    for _ in range(6):
        recent_months.append(cursor.strftime("%Y-%m"))
        cursor = add_months(cursor, -1)
    recent_months.reverse()
    monthly_expenses = [
        float(monthly_stats.get(m, {}).get("expense", 0.0)) for m in recent_months
    ]
    avg_monthly_expense = (
        sum(monthly_expenses) / len(monthly_expenses) if monthly_expenses else 0.0
    )

    total_balance = 0.0
    for acc in accounts:
        if (acc.get("account_type") or "").lower() == "credit_card":
            continue
        total_balance += float(acc.get("current_balance") or 0)

    net_savings = monthly_income - avg_monthly_expense
    savings_rate = (
        round((net_savings / monthly_income) * 100, 1) if monthly_income > 0 else 0.0
    )

    summary = {
        "monthly_income": monthly_income,
        "fixed_expense": fixed_expense,
        "net_outflow": round(avg_monthly_expense, 2),
        "net_savings": round(net_savings, 2),
        "savings_rate": savings_rate,
        "total_balance": total_balance,
    }
    return compute_financial_health(summary, accounts)


def enrich_chart_data_with_forecast(
    chart_data: list[dict[str, Any]],
    *,
    predicted_next_month: float | None,
    predicted_month_label: str | None,
    predicted_month: str | None,
    period: str,
) -> list[dict[str, Any]]:
    """Add actual_expense / predicted_expense series for dotted forecast line."""
    enriched: list[dict[str, Any]] = []
    for point in chart_data:
        row = dict(point)
        expense = float(row.get("expense") or 0)
        row["actual_expense"] = expense
        row["predicted_expense"] = None
        enriched.append(row)

    if not predicted_next_month or predicted_next_month <= 0:
        return enriched

    if enriched:
        enriched[-1]["predicted_expense"] = float(enriched[-1].get("actual_expense") or 0)

    label = predicted_month_label or "Next month"
    if period == "1m":
        short_name = label.split()[0][:3] if label else "Nxt"
    else:
        short_name = label[:7] if len(label) > 7 else label

    enriched.append(
        {
            "name": short_name,
            "date": f"{predicted_month}-01" if predicted_month else None,
            "month": predicted_month,
            "is_forecast": True,
            "income": 0.0,
            "expense": None,
            "net": None,
            "actual_expense": None,
            "predicted_expense": round(float(predicted_next_month), 2),
        }
    )
    return enriched


def build_period_dashboard_slice(
    *,
    accounts: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    monthly_stats: dict[str, dict[str, float]],
    period: str,
    reference: datetime,
    profile_income: float = 0.0,
    profile_fixed_rent: float = 0.0,
    profile_fixed_emi: float = 0.0,
    forecast_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Metrics and chart series for a single analysis period."""
    window = resolve_analysis_window(period, reference=reference.date())
    summary = compute_summary_for_window(
        accounts,
        transactions,
        window=window,
        profile_income=profile_income,
        profile_fixed_rent=profile_fixed_rent,
        profile_fixed_emi=profile_fixed_emi,
    )
    start_date = window.get("start_date")
    end_date = window.get("end_date")
    chart_granularity = "daily" if period == "1m" else "monthly"
    raw_chart = build_chart_data_for_window(
        monthly_stats,
        window=window,
        transactions=transactions,
    )
    predicted_next_month = (forecast_meta or {}).get("predicted_next_month")
    chart_data = enrich_chart_data_with_forecast(
        raw_chart,
        predicted_next_month=predicted_next_month,
        predicted_month_label=(forecast_meta or {}).get("predicted_month_label"),
        predicted_month=(forecast_meta or {}).get("predicted_month"),
        period=period,
    )

    return {
        **window,
        "chart_granularity": chart_granularity,
        "summary": summary,
        "chart_data": chart_data,
        "predicted_next_month": predicted_next_month,
        "predicted_month_label": (forecast_meta or {}).get("predicted_month_label"),
        "expense_breakdown_month": aggregate_expense_by_category(
            transactions,
            start_date=start_date,
            end_date=end_date,
        ),
        "top_spending": aggregate_top_spending_by_merchant(
            transactions,
            start_date=start_date,
            end_date=end_date,
        ),
        "spending_anomalies": detect_spending_anomalies(
            transactions,
            start_date=start_date,
            end_date=end_date,
        ),
    }


def resolve_dashboard_forecast_meta(
    user_id: str,
    transactions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve next-month forecast for dashboard charts (aligned with /api/forecast)."""
    from app.services.prophet.inference import get_next_month_prediction

    try:
        meta = get_next_month_prediction(user_id, transactions)
        if meta:
            return meta

        lookback = (date.today() - timedelta(days=730)).isoformat()
        recent = [
            t
            for t in transactions
            if str(t.get("transaction_date") or "")[:10] >= lookback
        ]
        if recent:
            return get_next_month_prediction(user_id, recent)
        return None
    except Exception:
        return None


def build_dashboard_payload(
    *,
    user_id: str,
    accounts: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    recent_rows: list[dict[str, Any]],
    budgets: list[dict[str, Any]],
    reference: datetime | None = None,
    profile_income: float = 0.0,
    profile_fixed_rent: float = 0.0,
    profile_fixed_emi: float = 0.0,
    period: str = "1m",
) -> dict[str, Any]:
    ref = reference or datetime.now()
    period_key = normalize_period(period)
    monthly_stats = aggregate_monthly_stats(transactions)

    forecast_meta = resolve_dashboard_forecast_meta(user_id, transactions)

    period_data = {
        p: build_period_dashboard_slice(
            accounts=accounts,
            transactions=transactions,
            monthly_stats=monthly_stats,
            period=p,
            reference=ref,
            profile_income=profile_income,
            profile_fixed_rent=profile_fixed_rent,
            profile_fixed_emi=profile_fixed_emi,
            forecast_meta=forecast_meta,
        )
        for p in ALL_DASHBOARD_PERIODS
    }
    active = period_data[period_key]
    financial_health = compute_overall_financial_health(
        accounts=accounts,
        transactions=transactions,
        profile_income=profile_income,
        profile_fixed_rent=profile_fixed_rent,
        profile_fixed_emi=profile_fixed_emi,
        reference=ref,
    )

    return {
        "success": True,
        "period": period_key,
        "period_data": period_data,
        "financial_health": financial_health,
        "forecast": forecast_meta,
        **active,
        "accounts": accounts,
        "recent_transactions": format_recent_transactions(recent_rows),
        "budget_utilization": compute_budget_utilization(
            budgets, transactions, reference=ref
        ),
    }

