"""LLM narratives for financial health score improvement.

All scores, percentages, and benchmarks are computed in Python.
The LLM only explains pre-computed facts and suggests improvements — it must not calculate.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.graph.logging_utils import create_openai_client
from app.utils.tab_logging import tab_info, tab_warning

logger = logging.getLogger(__name__)

_BENCHMARKS = {
    "savings_rate_good": 20.0,
    "savings_rate_fair": 10.0,
    "debt_to_income_good": 30.0,
    "debt_to_income_fair": 50.0,
    "emergency_months_good": 6.0,
    "emergency_months_fair": 3.0,
    "credit_util_good": 30.0,
    "credit_util_fair": 50.0,
}


def _pillar_status(value: float | None, good_max: float, fair_max: float, *, higher_is_better: bool = True) -> str:
    if value is None:
        return "unknown"
    if higher_is_better:
        if value >= good_max:
            return "strong"
        if value >= fair_max:
            return "fair"
        return "needs_improvement"
    if value <= good_max:
        return "strong"
    if value <= fair_max:
        return "fair"
    return "needs_improvement"


def build_health_insight_facts(
    health: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate health metrics and improvement triggers — no LLM math."""
    score = int(health.get("score") or 0)
    label = health.get("label") or "Needs Work"
    savings_rate = float(health.get("savings_rate") or 0)
    debt_to_income = float(health.get("debt_to_income_pct") or 0)
    net_savings = float(health.get("net_savings") or 0)
    emergency_months = health.get("emergency_buffer_months")
    credit_util = health.get("avg_credit_utilization_pct")
    liquid_balance = float(health.get("total_liquid_balance") or 0)

    profile_income = float((profile or {}).get("income") or 0)
    fixed_rent = float((profile or {}).get("fixed_rent") or 0)
    fixed_emi = float((profile or {}).get("fixed_emi") or 0)
    primary_goal = (profile or {}).get("primary_goal")

    pillars = [
        {
            "pillar": "Savings Rate",
            "value": savings_rate,
            "unit": "percent",
            "status": _pillar_status(savings_rate, _BENCHMARKS["savings_rate_good"], _BENCHMARKS["savings_rate_fair"]),
            "benchmark_good": _BENCHMARKS["savings_rate_good"],
            "benchmark_fair": _BENCHMARKS["savings_rate_fair"],
        },
        {
            "pillar": "Monthly Commitments",
            "value": debt_to_income,
            "unit": "percent",
            "status": _pillar_status(debt_to_income, _BENCHMARKS["debt_to_income_good"], _BENCHMARKS["debt_to_income_fair"], higher_is_better=False),
            "benchmark_good": _BENCHMARKS["debt_to_income_good"],
            "benchmark_fair": _BENCHMARKS["debt_to_income_fair"],
        },
        {
            "pillar": "Emergency Buffer",
            "value": emergency_months,
            "unit": "months",
            "status": _pillar_status(
                float(emergency_months) if emergency_months is not None else None,
                _BENCHMARKS["emergency_months_good"],
                _BENCHMARKS["emergency_months_fair"],
            ),
            "benchmark_good": _BENCHMARKS["emergency_months_good"],
            "benchmark_fair": _BENCHMARKS["emergency_months_fair"],
        },
    ]
    if credit_util is not None:
        pillars.append(
            {
                "pillar": "Credit Utilization",
                "value": float(credit_util),
                "unit": "percent",
                "status": _pillar_status(float(credit_util), _BENCHMARKS["credit_util_good"], _BENCHMARKS["credit_util_fair"], higher_is_better=False),
                "benchmark_good": _BENCHMARKS["credit_util_good"],
                "benchmark_fair": _BENCHMARKS["credit_util_fair"],
            }
        )

    weak_pillars = [p["pillar"] for p in pillars if p["status"] == "needs_improvement"]
    improvement_triggers: list[str] = []

    if savings_rate < _BENCHMARKS["savings_rate_good"]:
        gap = max(0.0, _BENCHMARKS["savings_rate_good"] - savings_rate)
        improvement_triggers.append(
            f"Raise savings rate by {gap:.1f} percentage points to reach the 20% healthy target."
        )
    if debt_to_income > _BENCHMARKS["debt_to_income_good"]:
        improvement_triggers.append(
            f"Monthly commitments are {debt_to_income}% of income — aim below 30% by reducing recurring obligations or increasing income."
        )
    if emergency_months is None or float(emergency_months) < _BENCHMARKS["emergency_months_good"]:
        target = _BENCHMARKS["emergency_months_good"]
        current = float(emergency_months) if emergency_months is not None else 0.0
        improvement_triggers.append(
            f"Build emergency fund toward {target} months of expenses (currently {current} months, ₹{liquid_balance:,.0f} liquid)."
        )
    if credit_util is not None and float(credit_util) > _BENCHMARKS["credit_util_good"]:
        improvement_triggers.append(
            f"Lower credit utilization from {credit_util}% toward under 30% to improve your score."
        )
    if net_savings < 0:
        improvement_triggers.append(
            f"Monthly spending exceeds income by ₹{abs(net_savings):,.0f} — trim discretionary spend first."
        )
    if fixed_rent + fixed_emi > 0 and profile_income > 0:
        fixed_ratio = (fixed_rent + fixed_emi) / profile_income * 100
        if fixed_ratio > 40:
            improvement_triggers.append(
                f"Fixed rent and EMIs are {fixed_ratio:.0f}% of income — high fixed costs limit flexibility."
            )

    points_to_excellent = max(0, 80 - score)
    points_to_good = max(0, 60 - score)

    return {
        "health_score": {
            "score": score,
            "label": label,
            "points_to_good": points_to_good,
            "points_to_excellent": points_to_excellent,
        },
        "metrics": {
            "savings_rate_pct": savings_rate,
            "debt_to_income_pct": debt_to_income,
            "net_savings_inr": round(net_savings, 2),
            "emergency_buffer_months": emergency_months,
            "avg_credit_utilization_pct": credit_util,
            "total_liquid_balance_inr": round(liquid_balance, 2),
        },
        "pillars": pillars,
        "weak_pillars": weak_pillars,
        "improvement_triggers": improvement_triggers,
        "profile": {
            "income_inr": profile_income or None,
            "fixed_rent_inr": fixed_rent or None,
            "fixed_emi_inr": fixed_emi or None,
            "primary_goal": primary_goal,
        },
        "benchmarks": _BENCHMARKS,
    }


def _rule_based_health_insights(facts: dict[str, Any]) -> dict[str, Any]:
    score_info = facts["health_score"]
    metrics = facts["metrics"]
    score = score_info["score"]
    label = score_info["label"]

    analysis_parts = [
        f"Your financial health score is {score}/100 ({label}).",
    ]
    if facts["weak_pillars"]:
        analysis_parts.append(
            f"The main areas to improve are: {', '.join(facts['weak_pillars'])}."
        )
    else:
        analysis_parts.append("Your core pillars are in good shape — focus on maintaining habits.")

    recommendations = facts["improvement_triggers"][:5]
    if not recommendations:
        recommendations = [
            "Keep savings rate above 20% and maintain 6+ months of emergency reserves.",
            "Review subscriptions and recurring charges quarterly.",
        ]

    pillar_insights = []
    for p in facts["pillars"]:
        value = p["value"]
        if value is None:
            insight = f"No data available for {p['pillar']}."
        elif p["status"] == "strong":
            insight = f"{p['pillar']} is strong at {value}{'%' if p['unit'] == 'percent' else ' months' if p['unit'] == 'months' else ''}."
        elif p["status"] == "fair":
            insight = f"{p['pillar']} is fair — small improvements could lift your score."
        else:
            if p["pillar"] == "Savings Rate":
                insight = f"Savings rate is {value}% — target at least 20% of income."
            elif p["pillar"] == "Monthly Commitments":
                insight = f"Monthly commitments are {value}% of income — keep recurring costs under 30%."
            elif p["pillar"] == "Emergency Buffer":
                insight = f"Emergency buffer is {value} months — aim for 6 months of expenses."
            else:
                insight = f"Credit utilization is {value}% — pay down balances below 30%."
        pillar_insights.append({"pillar": p["pillar"], "status": p["status"], "insight": insight})

    return {
        "analysis": " ".join(analysis_parts),
        "recommendations": recommendations,
        "pillar_insights": pillar_insights,
        "source": "rule_based",
    }


def _llm_health_insights(facts: dict[str, Any]) -> dict[str, Any] | None:
    model = settings.financial_health_chat_model
    if not settings.NVIDIA_API_KEY or not model:
        return None

    system = (
        "You are a personal finance coach. All scores, percentages, benchmarks, and pillar "
        "statuses are pre-computed in pre_computed_facts. Your ONLY job is to explain the user's "
        "financial health and give practical, specific recommendations to improve their score. "
        "Do NOT calculate, derive, estimate, or invent any numbers. Use ONLY values from "
        "pre_computed_facts. Write in clear, encouraging prose for an Indian user (use ₹ for INR). "
        "Return valid JSON with keys: "
        "analysis (string, 2-4 sentences summarizing health and biggest gaps), "
        "recommendations (string[], 3-5 actionable steps prioritized by score impact), "
        "pillar_insights ([{pillar, status, insight}] — one per pillar in pre_computed_facts.pillars)."
    )

    try:
        client = create_openai_client()
        started = time.perf_counter()
        tab_info(
            "dashboard",
            "financial health LLM start model=%s score=%s",
            model,
            facts["health_score"].get("score"),
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps({"pre_computed_facts": facts}, default=str),
                },
            ],
            temperature=0.3,
            max_tokens=900,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        parsed["source"] = "llm"
        tab_info(
            "dashboard",
            "financial health LLM done elapsed_ms=%.0f recommendations=%d",
            (time.perf_counter() - started) * 1000,
            len(parsed.get("recommendations") or []),
        )
        return parsed
    except Exception as exc:
        tab_warning("dashboard", "financial health LLM failed: %s", exc)
        logger.warning("[financial_health_insights] LLM failed: %s", exc)
        return None


def build_financial_health_insights_payload(
    health: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
    include_llm: bool = False,
) -> dict[str, Any]:
    facts = build_health_insight_facts(health, profile=profile)
    rule_based = _rule_based_health_insights(facts)
    payload = {
        "success": True,
        "score": facts["health_score"]["score"],
        "label": facts["health_score"]["label"],
        **rule_based,
        "llm_status": "pending" if include_llm else "skipped",
    }
    if not include_llm:
        return payload

    llm_insights = _llm_health_insights(facts)
    if llm_insights:
        payload.update(llm_insights)
        payload["llm_status"] = "complete"
    else:
        payload["llm_status"] = "failed"
    return payload
