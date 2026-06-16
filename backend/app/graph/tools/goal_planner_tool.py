"""
Goal Planner Tool — affordability analysis for savings / purchase goals.

No slot-filling: the Brain has already resolved the goal parameters (description,
target amount, timeline, funding) via clarification. This tool grounds the plan in
real data — the user's monthly average spend and net flow from their transactions —
and computes a feasibility/affordability snapshot that the answer node turns into a plan.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict

from app.graph.state import AgentState
from app.utils.supabase_client import supabase_db

logger = logging.getLogger(__name__)


def _months_from_timeline(timeline: Any) -> float | None:
    """Best-effort parse of a timeline string/number into a number of months."""
    if timeline is None:
        return None
    if isinstance(timeline, (int, float)):
        return float(timeline)
    text = str(timeline).lower()
    num_match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not num_match:
        return None
    value = float(num_match.group(1))
    if "year" in text or "yr" in text:
        return value * 12.0
    if "week" in text:
        return value / 4.345
    if "day" in text:
        return value / 30.0
    # default unit is months
    return value


def _compute_monthly_aggregates(user_id: str) -> Dict[str, float]:
    """Aggregate the user's transactions by month → average spend and net flow."""
    monthly = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    try:
        if supabase_db:
            resp = (
                supabase_db.table("transactions")
                .select("amount, transaction_type, transaction_date")
                .eq("user_id", user_id)
                .execute()
            )
            for tx in resp.data or []:
                ttype = (tx.get("transaction_type") or "").lower()
                amount = abs(float(tx.get("amount") or 0.0))
                date_str = tx.get("transaction_date") or ""
                month = date_str[:7] if len(date_str) >= 7 else ""
                if not month or ttype not in ("income", "expense"):
                    continue
                monthly[month][ttype] += amount
    except Exception as exc:
        logger.error("[goal_planner] Failed to aggregate transactions: %s", exc)

    n = len(monthly) or 1
    total_expense = sum(m["expense"] for m in monthly.values())
    total_income = sum(m["income"] for m in monthly.values())
    return {
        "months_observed": len(monthly),
        "monthly_avg_spend": round(total_expense / n, 2),
        "monthly_avg_income": round(total_income / n, 2),
        "monthly_net_flow": round((total_income - total_expense) / n, 2),
    }


def goal_planner_tool(state: AgentState) -> dict:
    """Produce a goal-feasibility evidence item grounded in the user's spending."""
    user_id = state.get("user_id") or ""
    task = state.get("brain_task") or {}
    goal = task.get("goal") or {}

    agg = _compute_monthly_aggregates(user_id)
    monthly_net_flow = agg["monthly_net_flow"]

    target = goal.get("target_amount")
    try:
        target = float(target) if target is not None else None
    except (ValueError, TypeError):
        target = None

    months = _months_from_timeline(goal.get("timeline"))

    monthly_savings_needed = None
    feasible = None
    if target is not None and months and months > 0:
        monthly_savings_needed = round(target / months, 2)
        # Feasible if the required monthly saving fits within the user's net flow.
        feasible = monthly_net_flow >= monthly_savings_needed if monthly_net_flow > 0 else False

    data = {
        "goal_description": goal.get("description"),
        "target_amount": target,
        "timeline": goal.get("timeline"),
        "timeline_months": months,
        "funding": goal.get("funding"),
        "monthly_avg_spend": agg["monthly_avg_spend"],
        "monthly_avg_income": agg["monthly_avg_income"],
        "monthly_net_flow": monthly_net_flow,
        "monthly_savings_needed": monthly_savings_needed,
        "feasible": feasible,
        "months_observed": agg["months_observed"],
    }

    summary = (
        f"Goal '{data.get('goal_description')}': target=₹{target}, timeline={goal.get('timeline')}, "
        f"monthly_avg_spend=₹{agg['monthly_avg_spend']}, net_flow=₹{monthly_net_flow}, "
        f"monthly_savings_needed=₹{monthly_savings_needed}, feasible={feasible}"
    )
    logger.info("[goal_planner] %s", summary)

    return {
        "evidence": [{
            "tool": "goal_planner",
            "task": task.get("sub_question") or state.get("user_query"),
            "summary": summary,
            "data": data,
        }],
        "sources": ["Supabase Transactions", "Goal Planner"],
    }
