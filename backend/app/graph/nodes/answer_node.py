"""
Answer Node — synthesises the final structured response from collected evidence.

Produces:
  - final_answer : concise natural-language text
  - artifacts    : visualization specs (chart data filled deterministically from
                   evidence so no numbers are hallucinated)
  - sources      : attribution list

Mode is chosen from the evidence:
  goal_planner   → feasibility plan (FINASSIST_SYSTEM_PROMPT) + net-flow/savings bar
  investment     → tool-authored narrative + portfolio-allocation pie
  knowledge      → RAG answer (ANSWER_KNOWLEDGE_SYSTEM)
  nl2sql / data  → ANSWER_VIZ_SYSTEM (concise text + chart-type choice)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import (
    ANSWER_VIZ_SYSTEM,
    ANSWER_KNOWLEDGE_SYSTEM,
    FINASSIST_SYSTEM_PROMPT,
    GOAL_PLAN_SYSTEM,
    CHART_CAPTION_SYSTEM,
)

logger = logging.getLogger(__name__)


# ── chart builders (deterministic — data comes only from evidence) ───────────

def _chart(chart_type: str, title: str, x: str, y: str, data: List[Dict]) -> Dict[str, Any]:
    return {"type": "chart", "chart_type": chart_type, "title": title,
            "x_field": x, "y_field": y, "data": data}


def _artifacts_from_analytics(analytics: Dict[str, Any], chart_type: str, title: str) -> List[Dict]:
    if not analytics or chart_type in (None, "none", ""):
        return []
    if chart_type == "line" and analytics.get("trend"):
        data = [{"period": p["period"], "amount": round(p["amount"], 2)} for p in analytics["trend"]]
        return [_chart("line", title or "Trend", "period", "amount", data)]
    comp = analytics.get("comparison")
    if chart_type == "bar" and comp:
        data = [
            {"label": comp.get("target_a_name", "A"), "amount": round(comp.get("target_a_total", 0), 2)},
            {"label": comp.get("target_b_name", "B"), "amount": round(comp.get("target_b_total", 0), 2)},
        ]
        return [_chart("bar", title or "Comparison", "label", "amount", data)]
    breakdown = analytics.get("category_breakdown") or analytics.get("merchant_breakdown")
    if breakdown and chart_type in ("bar", "pie"):
        data = [{"label": str(k), "amount": round(float(v), 2)} for k, v in breakdown[:10]]
        return [_chart(chart_type, title or "Breakdown", "label", "amount", data)]
    return []


def _portfolio_pie(inv_data: Dict[str, Any]) -> List[Dict]:
    holdings = inv_data.get("holdings") or []
    if not holdings:
        return []
    data = [{"label": h["name"], "value": h["share_pct"]} for h in holdings if h.get("share_pct")]
    return [_chart("pie", "Portfolio Allocation", "label", "value", data)] if data else []


# ── Goal-specific chart builders (all deterministic from goal_planner evidence) ──

def _scenarios_comparison_bar(scenarios: List[Dict]) -> List[Dict]:
    """Bar comparing monthly_savings_needed across A / B / C scenarios."""
    data = [
        {"label": f"{s['tag']}: {s['label']}", "amount": s.get("monthly_savings_needed") or 0}
        for s in (scenarios or [])
        if s.get("monthly_savings_needed") is not None
    ]
    return [_chart("bar", "Scenario Comparison — Monthly Savings Required", "label", "amount", data)] if len(data) >= 2 else []


def _budget_impact_bar(g: Dict[str, Any]) -> List[Dict]:
    """Show income vs baseline expenses vs goal commitment vs remaining surplus."""
    income   = g.get("monthly_avg_income") or 0
    expenses = g.get("monthly_avg_spend") or 0
    needed   = g.get("monthly_savings_needed") or g.get("total_monthly_needed") or 0
    surplus  = round(max(0.0, income - expenses - needed), 2)
    if not income:
        return []
    data = [
        {"label": "Monthly Income",     "amount": round(income, 2)},
        {"label": "Fixed Expenses",     "amount": round(expenses, 2)},
        {"label": "Goal Commitment",    "amount": round(needed, 2)},
        {"label": "Remaining Surplus",  "amount": surplus},
    ]
    return [_chart("bar", "Monthly Budget After Goal Commitment", "label", "amount", data)]


def _savings_progress_line(g: Dict[str, Any]) -> List[Dict]:
    """Month-by-month accumulation toward the target (no returns — simple linear save)."""
    target   = float(g.get("target_amount") or g.get("wedding_budget") or g.get("emergency_fund_target") or 0)
    existing = float(g.get("existing_savings") or g.get("current_emergency_savings") or 0)
    monthly  = float(g.get("monthly_savings_needed") or 0)
    months   = int(g.get("timeline_months") or 12)
    if target <= 0 or monthly <= 0:
        return []
    data, balance = [], existing
    for mo in range(0, min(months + 1, 37)):
        data.append({"period": f"M{mo}", "amount": round(balance, 2)})
        if balance >= target:
            break
        balance += monthly
    if len(data) < 2:
        return []
    return [_chart("line", "Savings Progress Toward Goal", "period", "amount", data)]


def _fi_growth_line(g: Dict[str, Any]) -> List[Dict]:
    """Corpus growth projection for retirement / FIRE goals."""
    current = float(g.get("current_investments") or g.get("current_net_worth") or 0)
    sip     = float(g.get("monthly_sip_needed") or g.get("monthly_investment_assumed") or 0)
    target  = float(g.get("inflation_adjusted_corpus") or g.get("fi_corpus_4pct_rule") or 0)
    if target <= 0 or sip <= 0:
        return []
    r, data = 0.12 / 12, []
    for year in range(0, 41, 2):
        n  = year * 12
        fv = current * (1 + r) ** n + (sip * ((1 + r) ** n - 1) / r if n > 0 else 0)
        data.append({"period": f"Y{year}", "amount": round(fv)})
        if fv >= target:
            break
    return [_chart("line", "Projected Corpus Growth (12% p.a.)", "period", "amount", data)] if len(data) >= 2 else []


def _emi_comparison_bar(scenarios: List[Dict]) -> List[Dict]:
    """Bar comparing EMI across loan scenarios (car / house / education)."""
    data = [
        {"label": f"{s['tag']}: {s['label']}", "amount": s.get("estimated_emi") or s.get("estimated_home_loan_emi") or s.get("estimated_loan_emi") or 0}
        for s in (scenarios or [])
    ]
    data = [d for d in data if d["amount"] > 0]
    return [_chart("bar", "EMI Comparison Across Scenarios", "label", "amount", data)] if len(data) >= 2 else []


def _multi_goal_bar(g: Dict[str, Any]) -> List[Dict]:
    planned = g.get("planned_goals") or []
    if not planned:
        return []
    data = [{"label": p.get("description") or f"Goal {i+1}",
             "amount": p.get("allocated_monthly") or p.get("monthly_savings_needed") or 0}
            for i, p in enumerate(planned)]
    return [_chart("bar", "Monthly Allocation per Goal", "label", "amount", data)]


def _spending_reduction_bar(g: Dict[str, Any]) -> List[Dict]:
    """Bar showing potential monthly savings from reducible categories (from goal data)."""
    ops = g.get("spending_reduction_opportunities") or []
    if ops:
        data = [{"label": o.get("category"), "amount": o.get("potential_saving") or 0} for o in ops]
        data = [d for d in data if d["amount"] > 0]
        if data:
            return [_chart("bar", "Potential Monthly Savings from Spending Cuts", "label", "amount", data)]
    # Fall back to raw category spend
    cats = g.get("spending_by_category") or []
    if cats:
        data = [{"label": c.get("category"), "amount": c.get("amount") or 0} for c in cats[:8]]
        return [_chart("bar", "Monthly Spending by Category", "label", "amount", data)] if data else []
    return []


def _goal_facts_for_captions(g: Dict[str, Any]) -> Dict[str, Any]:
    """Compact facts that let the caption model explain what each number means."""
    from app.graph.tools.goal_planner_tool import _attach_inr

    scenarios = []
    for s in (g.get("scenarios") or []):
        is_cash = (s.get("estimated_emi") in (0, 0.0, None)) and (s.get("down_payment_pct") in (100, 100.0))
        scenarios.append({
            "label": s.get("label"),
            "monthly_saving_before_purchase": s.get("monthly_savings_needed"),
            "emi_after_purchase": s.get("estimated_emi") or s.get("estimated_home_loan_emi") or s.get("estimated_loan_emi") or 0,
            "down_payment_pct": s.get("down_payment_pct"),
            "is_full_cash_no_loan": bool(is_cash),
        })
    facts = {
        "goal_type": g.get("goal_type"),
        "target_amount": g.get("target_amount"),
        "monthly_net_surplus": g.get("monthly_net_flow"),
        "monthly_income": g.get("monthly_avg_income"),
        "scenarios": scenarios,
    }
    # Add ₹-formatted siblings so captions never rescale to "lakhs".
    return _attach_inr(facts)


def _attach_chart_captions(artifacts: List[Dict], g: Dict[str, Any]) -> None:
    """Generate a plain-English caption per chart via the cheap 8B model (grounded in numbers)."""
    if not artifacts:
        return
    charts_for_prompt = [
        {"index": i, "title": a.get("title"), "data": a.get("data")}
        for i, a in enumerate(artifacts)
    ]
    payload = {"facts": _goal_facts_for_captions(g), "charts": charts_for_prompt}
    try:
        completion = graph_chat_completion(
            node="answer_node", purpose="chart_captions", model=settings.fast_model,
            messages=[{"role": "system", "content": CHART_CAPTION_SYSTEM},
                      {"role": "user", "content": json.dumps(payload, default=str)}],
            response_format={"type": "json_object"}, max_tokens=500, temperature=0.1,
        )
        captions = (json.loads(completion.choices[0].message.content.strip()) or {}).get("captions") or []
        for art, cap in zip(artifacts, captions):
            if isinstance(cap, str) and cap.strip():
                art["caption"] = cap.strip()
    except Exception as exc:
        logger.warning("[answer_node] caption generation failed: %s", exc)


def _select_goal_artifacts(goal_type: str, g: Dict[str, Any]) -> List[Dict]:
    """Build up to 4 charts for a goal planning result — all from goal_planner data."""
    charts: List[Dict] = []
    scenarios = g.get("scenarios") or []

    # Chart 1: Scenario comparison (universal — most important)
    charts += _scenarios_comparison_bar(scenarios)

    # Chart 2: Budget impact (universal)
    charts += _budget_impact_bar(g)

    # Chart 3: Goal-type specific
    if goal_type in ("retirement", "fire"):
        charts += _fi_growth_line(g)
    elif goal_type in ("car", "house", "education"):
        emi_charts = _emi_comparison_bar(scenarios)
        charts += emi_charts if emi_charts else _savings_progress_line(g)
    elif goal_type == "multi_goal":
        charts += _multi_goal_bar(g)
    else:
        charts += _savings_progress_line(g)

    # Chart 4: Spending reduction opportunities
    if len(charts) < 4:
        charts += _spending_reduction_bar(g)

    # Portfolio pie if room remains and holdings are present
    if len(charts) < 4 and g.get("portfolio_holdings"):
        charts += _portfolio_pie({"holdings": g["portfolio_holdings"]})

    return charts[:4]


# ── profile helpers ──────────────────────────────────────────────────────────

def _profile_fields(profile: Dict[str, Any]) -> Dict[str, str]:
    income = profile.get("income", "unknown")
    income_display = f"₹{income:,.0f} per month" if isinstance(income, (int, float)) else str(income)
    return {
        "current_date": datetime.now().strftime("%d %B %Y"),
        "income_display": income_display,
        "city": str(profile.get("city", "India")),
        "real_time_balances": str(profile.get("real_time_balances", "N/A")),
        "monthly_net_flow": str(profile.get("monthly_net_flow", "N/A")),
    }


def _find(evidence: List[Dict], tool: str) -> Optional[Dict]:
    for e in evidence:
        if e.get("tool") == tool:
            return e
    return None


# ── node ───────────────────────────────────────────────────────────────────

def answer_node(state: AgentState) -> dict:
    evidence = state.get("evidence") or []
    user_query = state.get("user_query") or ""
    profile = state.get("user_profile") or {}
    sources = state.get("sources") or []

    goal_ev = _find(evidence, "goal_planner")
    inv_ev = _find(evidence, "investment")
    nl2sql_evs = [e for e in evidence if e.get("tool") == "nl2sql"]
    retrieved = state.get("retrieved_context") or []

    answer = ""
    artifacts: List[Dict] = []
    intent = "FINANCIAL_KNOWLEDGE"

    try:
        # ── Goal planning ──
        if goal_ev:
            intent = "GOAL_PLANNING"
            g = goal_ev.get("data") or {}

            # goal_planner data already includes scenarios, spending reduction, and the
            # investment liquidity check (it fetches all of this directly from the DB).
            ctx = json.dumps(g, indent=2, default=str)

            fields = _profile_fields(profile)
            system_prompt = GOAL_PLAN_SYSTEM.format(context_text=ctx, **fields)

            completion = graph_chat_completion(
                node="answer_node", purpose="goal_plan", model=settings.active_chat_model,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_query}],
                max_tokens=1400, temperature=0.15,
            )
            answer = completion.choices[0].message.content.strip()
            goal_type = str(g.get("goal_type") or "generic").lower()
            artifacts = _select_goal_artifacts(goal_type, g)
            _attach_chart_captions(artifacts, g)

        # ── Investment ──
        elif inv_ev:
            intent = "PORTFOLIO_ANALYSIS"
            data = inv_ev.get("data") or {}
            answer = data.get("narrative") or "Here is your portfolio analysis."
            artifacts = _portfolio_pie(data)

        # ── Data (nl2sql) ──
        elif nl2sql_evs:
            intent = "TRANSACTION_QUERY"
            evidence_blob = json.dumps(
                [{"task": e.get("task"), "summary": e.get("summary"), "data": e.get("data")} for e in nl2sql_evs],
                indent=2, default=str,
            )
            completion = graph_chat_completion(
                node="answer_node", purpose="data_answer", model=settings.active_chat_model,
                messages=[{"role": "system", "content": ANSWER_VIZ_SYSTEM},
                          {"role": "user", "content": f"User question: {user_query}\n\nEvidence:\n{evidence_blob}"}],
                response_format={"type": "json_object"}, max_tokens=600, temperature=0.1,
            )
            parsed = json.loads(completion.choices[0].message.content.strip())
            answer = parsed.get("answer", "")
            chart = parsed.get("chart") or {}
            if parsed.get("needs_visualization") and chart.get("chart_type") not in (None, "none"):
                # Use the last nl2sql analytics (most complete) for chart data.
                analytics = (nl2sql_evs[-1].get("data") or {}).get("analytics") or {}
                artifacts = _artifacts_from_analytics(analytics, chart.get("chart_type"), chart.get("title", ""))
            if not sources:
                sources = ["Supabase Transactions"]

        # ── Knowledge / general fallback ──
        else:
            intent = "FINANCIAL_KNOWLEDGE"
            context_text = "\n\n---\n\n".join(retrieved) if retrieved else (
                "No specific documents retrieved. Use your general financial expertise to answer safely."
            )
            fields = _profile_fields(profile)
            system_prompt = ANSWER_KNOWLEDGE_SYSTEM.format(context_text=context_text, **fields)
            completion = graph_chat_completion(
                node="answer_node", purpose="knowledge_answer", model=settings.active_chat_model,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_query}],
                max_tokens=600, temperature=0.2,
            )
            answer = completion.choices[0].message.content.strip()
            if not sources:
                sources = ["FinAssist Knowledge Base"]

    except Exception as exc:
        logger.error("[Node:answer] Synthesis failed: %s", exc)
        answer = "I encountered a temporary issue generating your response. Please try again in a moment."
        sources = sources or ["System Fallback"]

    logger.info("[Node:answer] intent=%s artifacts=%d", intent, len(artifacts))
    return {
        "final_answer": answer,
        "artifacts": artifacts,
        "sources": sources,
        "final_intent": intent,
        "messages": [AIMessage(content=answer)],
    }
