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
from app.services.analytics_service import _inr, build_weekend_behavior_insight
from app.core.llm_client import create_openai_client
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


def _monthly_trajectory_text(evolution: list[dict[str, Any]]) -> str:
    active = [m for m in evolution if float(m.get("amount") or 0) > 0]
    if len(active) < 2:
        if len(active) == 1:
            return (
                f"Spend was recorded in {active[0]['label']} only "
                f"(₹{float(active[0]['amount']):,.0f})."
            )
        return "No monthly spend recorded yet for this category."
    first, last = active[0], active[-1]
    delta = float(last["amount"]) - float(first["amount"])
    if delta > 0:
        direction = "increased"
    elif delta < 0:
        direction = "decreased"
    else:
        direction = "held steady"
    return (
        f"Monthly spend {direction} from ₹{float(first['amount']):,.0f} in {first['label']} "
        f"to ₹{float(last['amount']):,.0f} in {last['label']}."
    )


def _category_trend_insight_text(t: dict[str, Any]) -> str:
    cat = t["category"]
    total = float(t.get("total_inr") or 0)
    label = t["trend_label"]
    growth = int(t.get("consecutive_growth_months") or 0)
    mom = t.get("mom_change_pct")
    trajectory = _monthly_trajectory_text(t.get("monthly_evolution") or [])

    parts = [f"{cat} totals ₹{total:,.0f} in the selected period.", trajectory]
    if label == "rising_streak":
        parts.append(
            f"Spending has climbed for {growth} consecutive months — a sustained rise worth monitoring."
        )
    elif label == "rising" and mom is not None:
        parts.append(f"The latest month is up {mom}% versus the prior month.")
    elif label == "falling" and mom is not None:
        parts.append(f"The latest month is down {abs(mom)}% versus the prior month.")
    else:
        parts.append("Spending is relatively stable month to month.")
    return " ".join(p for p in parts if p)


def _category_suggestion_text(t: dict[str, Any]) -> str:
    cat = t["category"]
    label = t["trend_label"]
    if label == "rising_streak":
        return f"Set a weekly cap for {cat} and review which merchants are driving the streak."
    if label == "rising":
        return f"Compare {cat} merchants and pause discretionary purchases until spend normalizes."
    if label == "falling":
        return f"Keep {cat} on track — redirect the savings toward your primary financial goal."
    return f"Track {cat} weekly against your budget to catch shifts early."


def _merchant_insight_strings(facts: dict[str, Any]) -> tuple[str, str]:
    fastest = facts["merchants"].get("fastest_growing")
    conc = facts["merchants"].get("concentration") or {}
    if fastest:
        fastest_insight = fastest.get("growth_insight") or (
            f"{fastest['name']} spending rose {fastest.get('growth_display', f'+{fastest['growth_pct']}%')} "
            f"vs the prior period ({_inr(float(fastest.get('prior_total') or 0))} → "
            f"{_inr(float(fastest.get('current_total') or 0))})."
        )
    else:
        fastest_insight = "No merchant growth data for the comparison window."
    conc_insight = (
        f"Top {conc.get('top_n', 5)} merchants account for "
        f"{conc.get('pct_of_total', 0)}% of total spending."
        if conc.get("pct_of_total")
        else ""
    )
    return fastest_insight, conc_insight


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
    growth_list = merchant.get("merchant_growth") or []
    top_merchants = merchant.get("top_merchants") or []
    conc = merchant.get("concentration") or {}

    top_share = share[0] if share else None
    fastest = growth_list[0] if growth_list else None
    behavior_peak_day = behavior.get("peak_spending_day")
    behavior_peak_amount = float(behavior.get("peak_spending_day_amount") or 0)
    if not behavior_peak_day and heatmap:
        peak_entry = max(heatmap, key=lambda x: float(x.get("amount") or 0))
        if float(peak_entry.get("amount") or 0) > 0:
            behavior_peak_day = peak_entry.get("day")
            behavior_peak_amount = float(peak_entry.get("amount") or 0)
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
        category_analysis_facts.append(
            {
                "category": t["category"],
                "headline": f"{t['category']} spending trend",
                "analysis": _category_trend_insight_text(t),
                "suggestion": _category_suggestion_text(t),
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
            "period_label": period_label,
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
            "weekday_categories": wknd.get("weekday_categories", []),
            "weekend_categories": wknd.get("weekend_categories", []),
            "peak_spending_day": behavior_peak_day,
            "peak_spending_day_amount_inr": behavior_peak_amount or None,
            "peak_insight": behavior.get("peak_insight"),
            "day_of_week_heatmap": heatmap,
        },
        "flags": {
            "has_growing_categories": bool(growing_cats),
            "merchant_concentration_high": conc.get("pct_of_total", 0) >= 40,
            "weekend_spending_elevated": bool(wknd.get("weekend_elevated")),
        },
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

    exec_bullets: list[str] = [
        (
            f"Total spend for {summary.get('period_label') or 'the selected period'}: "
            f"₹{summary['total_spend_inr']:,.0f} across {summary['transaction_count']} transactions."
        ),
    ]
    if summary.get("top_category_pct"):
        exec_bullets.append(
            f"{summary['top_category']} is your biggest expense at {summary['top_category_pct']}% of total spend."
        )

    # Highlight rising categories
    growing_cats = [
        t for t in facts.get("category_trends", [])
        if t.get("is_growing_streak")
    ]
    if growing_cats:
        g = growing_cats[0]
        exec_bullets.append(
            f"{g['category']} has been rising for {g['consecutive_growth_months']} consecutive months — review this trend."
        )

    # MoM insight for top category
    top_trend = next(
        (t for t in facts.get("category_trends", []) if t["category"] == summary.get("top_category")),
        None,
    )
    if top_trend and top_trend.get("mom_change_pct") is not None:
        mom = top_trend["mom_change_pct"]
        direction = "up" if mom > 0 else "down"
        exec_bullets.append(
            f"{top_trend['category']} is {direction} {abs(mom)}% month-over-month."
        )

    # Merchant concentration
    conc = facts.get("merchants", {}).get("concentration", {})
    if conc.get("pct_of_total", 0) >= 40:
        exec_bullets.append(
            f"Top {conc.get('top_n', 5)} merchants account for {conc['pct_of_total']}% of spend — consider diversifying."
        )

    # Forecast
    if forecast.get("predicted_next_month_inr"):
        exec_bullets.append(
            f"Predicted spend for {forecast.get('predicted_month_label') or 'next month'}: "
            f"₹{forecast['predicted_next_month_inr']:,.0f}."
        )

    analysis_by_cat = {
        c["category"]: c["analysis"] for c in facts["category_analysis_facts"]
    }
    category_trends_out = [
        {
            "category": t["category"],
            "insight": analysis_by_cat.get(t["category"])
            or _category_trend_insight_text(t),
        }
        for t in facts["category_trends"]
    ]

    fastest_insight, conc_insight = _merchant_insight_strings(facts)
    behavior = facts["behavior"]

    time_insight = behavior.get("peak_insight") or (
        f"Highest spend falls on {behavior.get('peak_spending_day')}s "
        f"(₹{float(behavior.get('peak_spending_day_amount_inr') or 0):,.0f})."
        if behavior.get("peak_spending_day")
        and float(behavior.get("peak_spending_day_amount_inr") or 0) > 0
        else "Spending is spread evenly across the week."
    )

    recommendations = facts["recommendation_triggers"][:4]
    if not recommendations:
        recommendations = ["Keep monitoring category trends weekly."]

    return {
        "executive_summary": exec_bullets,
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
            "weekend": behavior.get("weekend_insight")
            or "Not enough spending data for weekday vs weekend comparison.",
            "time_of_day": time_insight,
        },
        "source": "rule_based",
    }


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse LLM JSON output with repair for truncated responses."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty LLM response")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    # Close truncated string + braces (common when max_tokens cuts off mid-field)
    repaired = text
    if repaired.count('"') % 2 == 1:
        repaired += '"'
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")
    repaired += "]" * max(0, open_brackets)
    repaired += "}" * max(0, open_braces)
    return json.loads(repaired)


def _normalize_merchant_insights(
    merchant_insights: dict[str, Any] | None,
    facts: dict[str, Any],
) -> dict[str, str]:
    """Ensure merchant insight fields are strings (LLM may echo raw fact objects)."""
    mi = merchant_insights or {}
    default_fastest, default_conc = _merchant_insight_strings(facts)

    fastest_growing = mi.get("fastest_growing")
    if not isinstance(fastest_growing, str):
        fastest_growing = default_fastest

    concentration = mi.get("concentration")
    if not isinstance(concentration, str):
        concentration = default_conc

    return {
        "fastest_growing": fastest_growing,
        "concentration": concentration,
    }


def _llm_narrate_facts(facts: dict[str, Any]) -> dict[str, Any] | None:
    if not settings.NVIDIA_API_KEY or not settings.analytics_chat_model:
        return None

    system = (
        "You are a concise financial analyst. All numbers, percentages, rankings, and "
        "classifications are already computed in pre_computed_facts. "
        "Your ONLY job is to turn these pre-computed facts into short, actionable insights. "
        "Do NOT calculate, derive, estimate, or invent any numbers or categories. "
        "For behavior_insights.weekend, provide a detailed category analysis of spending behavior on weekends vs weekdays. "
        "Use pre_computed_facts.behavior.weekday_categories and pre_computed_facts.behavior.weekend_categories to compare which categories dominate on weekends versus weekdays. "
        "Use ONLY values present in pre_computed_facts.\n\n"
        "Return valid JSON with these keys:\n"
        "- executive_summary: a JSON ARRAY of 4-6 short bullet-point strings (each ≤25 words). "
        "Each bullet must deliver ONE specific, actionable insight — not just restate a number. "
        "Focus on: biggest expense category and its trend, any rising spending streaks, "
        "notable anomalies, merchant concentration risks, and one concrete saving opportunity.\n"
        "- recommendations: string[] — 3-4 specific, actionable recommendations.\n"
        "- category_trends: [{category, insight}] — cover every category in pre_computed_facts.category_trends.\n"
        "- category_analysis: [{category, headline, analysis, suggestion}] — cover every category in category_analysis_facts.\n"
        "- merchant_insights: {fastest_growing, concentration} — strings.\n"
        "- behavior_insights: {weekend, time_of_day} — each must be a JSON ARRAY of 2-3 short bullet-point strings."
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
            max_tokens=2500,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = _parse_llm_json(raw)
        parsed["source"] = "llm"
        if parsed.get("merchant_insights"):
            parsed["merchant_insights"] = _normalize_merchant_insights(
                parsed.get("merchant_insights"),
                facts,
            )
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
