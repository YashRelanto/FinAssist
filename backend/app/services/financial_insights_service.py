"""LLM narratives layered on deterministic spending analytics.

All numbers, percentages, rankings, and classifications are computed in Python.
The LLM only turns pre-computed facts into readable prose — it must not calculate.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.services.analytics_service import build_weekend_behavior_insight
from app.graph.logging_utils import create_openai_client
from app.utils.tab_logging import tab_debug, tab_info, tab_warning

logger = logging.getLogger(__name__)


def _mom_direction(mom: float | None) -> str | None:
    if mom is None:
        return None
    if mom > 0:
        return "up"
    if mom < 0:
        return "down"
    return "flat"


def _trend_label(consecutive_growth: int, mom: float | None) -> str:
    if consecutive_growth >= 2:
        return "rising_streak"
    if mom is not None and mom > 10:
        return "rising"
    if mom is not None and mom < -10:
        return "falling"
    return "stable"


def build_precomputed_insight_facts(
    analytics: dict[str, Any],
    *,
    predicted_next_month: float | None = None,
    predicted_month_label: str | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate every metric the narrator needs — no LLM math."""
    period_label = analytics.get("period_label") or "the selected period"
    total_spend = float(analytics.get("total_spend") or 0)
    txn_count = int(analytics.get("transaction_count") or 0)
    share = analytics.get("category_share") or []
    trends = analytics.get("category_trends") or []
    merchant = analytics.get("merchant_analytics") or {}
    behavior = analytics.get("spending_behavior") or {}
    wknd = behavior.get("weekday_vs_weekend") or {}
    heatmap = behavior.get("day_of_week_heatmap") or []
    freq = behavior.get("transaction_frequency") or {}
    growth_list = merchant.get("merchant_growth") or []
    top_merchants = merchant.get("top_merchants") or []
    conc = merchant.get("concentration") or {}

    top_share = share[0] if share else None
    fastest = growth_list[0] if growth_list else None
    peak_day = max(heatmap, key=lambda x: x.get("amount", 0), default=None)
    behavior_peak_day = behavior.get("peak_spending_day")
    behavior_peak_amount = float(behavior.get("peak_spending_day_amount") or 0)
    growing_cats = [
        t for t in trends if (t.get("consecutive_growth_months") or 0) >= 2
    ]

    category_facts: list[dict[str, Any]] = []
    for t in trends[:8]:
        mom = t.get("mom_change_pct")
        growth = int(t.get("consecutive_growth_months") or 0)
        label = _trend_label(growth, mom)
        category_facts.append(
            {
                "category": t.get("category"),
                "total_inr": t.get("total"),
                "mom_change_pct": mom,
                "mom_direction": _mom_direction(mom),
                "consecutive_growth_months": growth,
                "trend_label": label,
                "monthly_evolution": t.get("monthly_evolution") or [],
                "is_growing_streak": growth >= 2,
            }
        )

    category_analysis_facts: list[dict[str, Any]] = []
    for t in category_facts[:5]:
        mom = t.get("mom_change_pct")
        direction = t.get("mom_direction")
        if mom is not None and direction:
            analysis = (
                f"Month-over-month change is {abs(mom)}% {direction} "
                f"for {t['category']}."
            )
        else:
            analysis = f"Not enough history for month-over-month comparison for {t['category']}."
        category_analysis_facts.append(
            {
                "category": t["category"],
                "headline": f"{t['category']} spending trend",
                "analysis": analysis,
                "suggestion": f"Track {t['category']} weekly against your budget.",
                "trend_label": t["trend_label"],
                "total_inr": t["total_inr"],
            }
        )

    recommendation_triggers: list[str] = []
    if growing_cats:
        g = growing_cats[0]
        recommendation_triggers.append(
            f"Review {g['category']} — spending rose for "
            f"{g['consecutive_growth_months']} consecutive months."
        )
    if conc.get("pct_of_total", 0) >= 40:
        recommendation_triggers.append(
            f"Top {conc.get('top_n', 5)} merchants account for "
            f"{conc['pct_of_total']}% of spend — consider diversifying."
        )
    weekend_mult = float(wknd.get("weekend_multiplier") or 0)
    if weekend_mult >= 1.5:
        recommendation_triggers.append(
            "Weekend spending is elevated — set a weekend budget cap."
        )

    exec_facts: list[str] = [
        f"Total spend: ₹{total_spend:,.2f}",
        f"Transaction count: {txn_count}",
    ]
    if top_share:
        exec_facts.append(
            f"Top category: {top_share['category']} at {top_share['pct']}% "
            f"(₹{top_share['amount']:,.2f})"
        )
    if predicted_next_month:
        exec_facts.append(
            f"Predicted next month ({predicted_month_label or 'next month'}): "
            f"₹{predicted_next_month:,.2f}"
        )

    return {
        "period": {
            "key": analytics.get("period"),
            "label": period_label,
            "start_date": analytics.get("start_date"),
            "end_date": analytics.get("end_date"),
        },
        "spending_summary": {
            "total_spend_inr": round(total_spend, 2),
            "transaction_count": txn_count,
            "top_category": top_share["category"] if top_share else None,
            "top_category_pct": top_share["pct"] if top_share else None,
            "top_category_amount_inr": top_share["amount"] if top_share else None,
        },
        "forecast": {
            "predicted_next_month_inr": predicted_next_month,
            "predicted_month_label": predicted_month_label,
        },
        "category_share": share,
        "category_trends": category_facts,
        "category_analysis_facts": category_analysis_facts,
        "merchants": {
            "top_merchants": top_merchants,
            "fastest_growing": fastest,
            "merchant_growth": growth_list[:10],
            "concentration": conc,
        },
        "behavior": {
            "weekday_total_inr": wknd.get("weekday_total"),
            "weekend_total_inr": wknd.get("weekend_total"),
            "weekday_avg_per_day_inr": wknd.get("weekday_avg_per_day"),
            "weekend_avg_per_day_inr": wknd.get("weekend_avg_per_day"),
            "weekend_multiplier": weekend_mult,
            "weekend_elevated": bool(wknd.get("weekend_elevated")),
            "weekend_insight": behavior.get("weekend_insight")
            or build_weekend_behavior_insight(wknd, heatmap),
            "peak_spending_day": behavior_peak_day or (peak_day.get("day") if peak_day else None),
            "peak_spending_day_amount_inr": (
                behavior_peak_amount
                if behavior_peak_amount > 0
                else (peak_day.get("amount") if peak_day else None)
            ),
            "day_of_week_heatmap": heatmap,
            "avg_transactions_per_active_day": freq.get("avg_per_day"),
            "total_days_with_transactions": freq.get("total_days_with_txns"),
            "total_transactions": freq.get("total_txns"),
        },
        "flags": {
            "has_growing_categories": bool(growing_cats),
            "merchant_concentration_high": conc.get("pct_of_total", 0) >= 40,
            "weekend_spending_elevated": bool(wknd.get("weekend_elevated")),
        },
        "executive_facts": exec_facts,
        "recommendation_triggers": recommendation_triggers,
        "profile": {
            "income_inr": profile.get("income") if profile else None,
            "primary_goal": profile.get("primary_goal") if profile else None,
            "biggest_category": profile.get("biggest_category") if profile else None,
        },
    }


def _narrate_from_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Deterministic narration templates — no LLM."""
    summary = facts["spending_summary"]
    forecast = facts["forecast"]

    exec_parts = [
        f"You spent ₹{summary['total_spend_inr']:,.0f} across "
        f"{summary['transaction_count']} transactions."
    ]
    if summary.get("top_category_pct"):
        exec_parts.append(
            f"{summary['top_category']} leads at {summary['top_category_pct']}% of total spend."
        )
    if forecast.get("predicted_next_month_inr"):
        exec_parts.append(
            f"Predicted spend for {forecast.get('predicted_month_label') or 'next month'}: "
            f"₹{forecast['predicted_next_month_inr']:,.0f}."
        )

    category_trends_out: list[dict[str, str]] = []
    for t in facts["category_trends"]:
        label = t["trend_label"]
        growth = t["consecutive_growth_months"]
        mom = t["mom_change_pct"]
        cat = t["category"]
        if label == "rising_streak":
            insight = f"{cat} spending has grown consistently for {growth} months."
        elif label == "rising":
            insight = f"{cat} rose {mom}% month-over-month."
        elif label == "falling":
            insight = f"{cat} fell {abs(mom)}% month-over-month."
        else:
            insight = f"{cat} spending is relatively stable this period."
        category_trends_out.append({"category": cat, "insight": insight})

    fastest = facts["merchants"].get("fastest_growing")
    conc = facts["merchants"].get("concentration") or {}
    behavior = facts["behavior"]

    fastest_insight = (
        f"{fastest['name']} is your fastest growing merchant (+{fastest['growth_pct']}%)."
        if fastest
        else "No merchant growth data for the comparison window."
    )
    conc_insight = (
        f"Top {conc.get('top_n', 5)} merchants account for "
        f"{conc.get('pct_of_total', 0)}% of total spending."
        if conc.get("pct_of_total")
        else ""
    )

    weekend_insight = behavior.get("weekend_insight") or build_weekend_behavior_insight(
        {
            "weekend_multiplier": behavior.get("weekend_multiplier"),
            "weekday_avg_per_day": behavior.get("weekday_avg_per_day_inr"),
            "weekend_avg_per_day": behavior.get("weekend_avg_per_day_inr"),
        },
        behavior.get("day_of_week_heatmap") or [],
    )

    peak = behavior.get("peak_spending_day")
    peak_amt = behavior.get("peak_spending_day_amount_inr") or 0
    time_insight = (
        f"Highest spend falls on {peak}s (₹{peak_amt:,.0f})."
        if peak and peak_amt > 0
        else "Spending is spread evenly across the week."
    )

    avg = behavior.get("avg_transactions_per_active_day")
    freq_insight = (
        f"You average {avg} transactions per active day."
        if avg
        else "Limited transaction frequency data for this period."
    )

    recommendations = facts["recommendation_triggers"][:4]
    if not recommendations:
        recommendations = ["Keep monitoring category trends weekly."]

    return {
        "executive_summary": " ".join(exec_parts),
        "recommendations": recommendations,
        "category_trends": category_trends_out,
        "category_analysis": [
            {
                "category": c["category"],
                "headline": c["headline"],
                "analysis": c["analysis"],
                "suggestion": c["suggestion"],
            }
            for c in facts["category_analysis_facts"]
        ],
        "merchant_insights": {
            "fastest_growing": fastest_insight,
            "concentration": conc_insight,
        },
        "behavior_insights": {
            "weekend": weekend_insight,
            "time_of_day": time_insight,
            "frequency": freq_insight,
        },
        "source": "rule_based",
    }


def _llm_narrate_facts(facts: dict[str, Any]) -> dict[str, Any] | None:
    if not settings.NVIDIA_API_KEY or not settings.analytics_chat_model:
        return None

    system = (
        "You are a financial narrator. All numbers, percentages, rankings, and "
        "classifications are already computed in pre_computed_facts. "
        "Your ONLY job is to explain these facts in clear, concise prose. "
        "Do NOT calculate, derive, estimate, or invent any numbers or categories. "
        "For behavior_insights.weekend, use pre_computed_facts.behavior.weekend_insight verbatim. "
        "Do NOT recalculate weekday/weekend comparisons. "
        "Use ONLY values present in pre_computed_facts. "
        "Return valid JSON with keys: executive_summary (string), recommendations (string[]), "
        "category_trends ([{category, insight}]), category_analysis "
        "([{category, headline, analysis, suggestion}]), "
        "merchant_insights ({fastest_growing, concentration}), "
        "behavior_insights ({weekend, time_of_day, frequency}). "
        "For category_trends and category_analysis, cover every category listed in "
        "pre_computed_facts.category_trends and category_analysis_facts."
    )

    try:
        client = create_openai_client()
        started = time.perf_counter()
        tab_info(
            "analytics",
            "LLM narration start model=%s categories=%d",
            settings.analytics_chat_model,
            len(facts.get("category_trends") or []),
        )
        response = client.chat.completions.create(
            model=settings.analytics_chat_model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps({"pre_computed_facts": facts}, default=str),
                },
            ],
            temperature=0.2,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        parsed["source"] = "llm"
        tab_info(
            "analytics",
            "LLM narration done elapsed_ms=%.0f recommendations=%d",
            (time.perf_counter() - started) * 1000,
            len(parsed.get("recommendations") or []),
        )
        return parsed
    except Exception as exc:
        tab_warning("analytics", "LLM narration failed: %s", exc)
        logger.warning("[financial_insights] LLM narration failed: %s", exc)
        return None


def build_financial_insights_payload(
    analytics: dict[str, Any],
    *,
    predicted_next_month: float | None = None,
    predicted_month_label: str | None = None,
    profile: dict[str, Any] | None = None,
    include_llm: bool = False,
) -> dict[str, Any]:
    facts = build_precomputed_insight_facts(
        analytics,
        predicted_next_month=predicted_next_month,
        predicted_month_label=predicted_month_label,
        profile=profile,
    )
    tab_debug(
        "analytics",
        "insight facts total_spend=%s flags=%s triggers=%d",
        facts["spending_summary"].get("total_spend_inr"),
        facts.get("flags"),
        len(facts.get("recommendation_triggers") or []),
    )
    rule_based = _narrate_from_facts(facts)
    payload = {
        "success": True,
        "period": analytics.get("period"),
        **rule_based,
        "llm_status": "pending" if include_llm else "skipped",
    }
    if not include_llm:
        tab_info("analytics", "insights source=%s (instant)", rule_based.get("source"))
        return payload

    llm_insights = _llm_narrate_facts(facts)
    if llm_insights:
        payload.update(llm_insights)
        payload["llm_status"] = "complete"
    else:
        payload["llm_status"] = "failed"
    tab_info("analytics", "insights source=%s", payload.get("source"))
    return payload
