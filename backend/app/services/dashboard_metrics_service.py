"""Dashboard metric calculations aligned with public schema transaction types."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

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
    For each active budget, sum expenses in [start_date, end_date] for its category_id.
    """
    ref = reference or datetime.now()
    today = ref.strftime("%Y-%m-%d")
    result: list[dict[str, Any]] = []

    for budget in budgets:
        start = str(budget.get("start_date") or today)
        end = str(budget.get("end_date") or today)
        if end < today and budget.get("end_date"):
            continue
        if start > today:
            continue

        category_id = budget.get("category_id")
        limit = float(budget.get("amount") or 0)
        spent = 0.0
        for row in transactions:
            if (row.get("transaction_type") or "").lower() != EXPENSE_TYPE:
                continue
            if row.get("category_id") != category_id:
                continue
            date_str = str(row.get("transaction_date") or "")
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


def build_dashboard_payload(
    *,
    accounts: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    recent_rows: list[dict[str, Any]],
    budgets: list[dict[str, Any]],
    reference: datetime | None = None,
    profile_income: float = 0.0,
) -> dict[str, Any]:
    ref = reference or datetime.now()
    monthly_stats = aggregate_monthly_stats(transactions)
    current_month = ref.strftime("%Y-%m")
    month_start = f"{current_month}-01"
    month_end = ref.strftime("%Y-%m-%d")

    return {
        "success": True,
        "summary": compute_summary(accounts, monthly_stats, reference=ref, profile_income=profile_income),
        "chart_data": build_chart_data(monthly_stats, reference=ref),
        "accounts": accounts,
        "recent_transactions": format_recent_transactions(recent_rows),
        "expense_breakdown_month": aggregate_expense_by_category(
            transactions,
            start_date=month_start,
            end_date=month_end,
        ),
        "budget_utilization": compute_budget_utilization(
            budgets, transactions, reference=ref
        ),
    }

