"""
Answer Node — synthesises the final structured response from collected evidence.

Produces:
  - final_answer : concise natural-language text
  - artifacts    : visualization specs (chart data filled deterministically from
                   evidence so no numbers are hallucinated)
  - sources      : attribution list

Mode is chosen from the evidence:
  goal_planner   → feasibility plan (GOAL_PLAN_SYSTEM) + net-flow/savings bar
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
from app.graph.llm import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import (
    ANSWER_VIZ_SYSTEM,
    ANSWER_KNOWLEDGE_SYSTEM,
    GOAL_PLAN_SYSTEM,
    GOAL_WHATIF_SYSTEM,
    GOAL_CARDS_SYSTEM,
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

_SCENARIO_SHORT = {"A": "Baseline", "B": "Spending Cuts", "C": "Free Up Liquidity", "D": "Everything"}


def _scenarios_comparison_bar(scenarios: List[Dict]) -> List[Dict]:
    """Bar comparing the EMI (loan goals) or monthly saving (cash goals) across A/B/C/D — the real
    monthly commitment of each scenario, not just the down-payment set-aside."""
    has_emi = any((s.get("estimated_emi") or 0) > 0 for s in (scenarios or []))
    field = "estimated_emi" if has_emi else "monthly_savings_needed"
    title = ("Monthly EMI by Scenario" if has_emi else "Monthly Saving by Scenario")
    data = [
        {"label": _SCENARIO_SHORT.get(s.get("tag"), s.get("tag")), "amount": s.get(field) or 0}
        for s in (scenarios or [])
    ]
    data = [d for d in data if d["amount"] is not None]
    return [_chart("bar", title, "label", "amount", data)] if len(data) >= 2 else []


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
        {"label": _SCENARIO_SHORT.get(s.get("tag"), s.get("tag") or ""),
         "amount": s.get("estimated_emi") or s.get("estimated_home_loan_emi") or s.get("estimated_loan_emi") or 0}
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


def _funding_sources_bar(g: Dict[str, Any]) -> List[Dict]:
    """Bar of WHERE the deployable seed money comes from — bank cash / liquid funds / breakable FDs
    (and the equity deliberately left invested) — so the user sees their idle assets at a glance."""
    fs = g.get("funding_sources") or {}
    pairs = [("Bank cash", fs.get("from_bank_savings")),
             ("Liquid funds", fs.get("from_liquid_funds")),
             ("Fixed deposits", fs.get("from_fixed_deposits")),
             ("Equity (kept invested)", fs.get("equity_or_other_not_counted"))]
    data = [{"label": lbl, "amount": round(float(v), 2)} for lbl, v in pairs if v and float(v) > 0]
    return [_chart("bar", "Your Available Funds", "label", "amount", data)] if len(data) >= 2 else []


def _funding_split_pie(g: Dict[str, Any]) -> List[Dict]:
    """Pie: how the goal is funded — Loan-financed vs self-funded sources (Bank / FD / Liquid).
    Slices are SHARES (% of total funding) so captions render as percentages, not raw rupees."""
    fb = g.get("funding_breakdown") or {}
    pairs = [("Loan-financed", fb.get("loan")), ("Bank cash", fb.get("bank")),
             ("Fixed deposits", fb.get("fd")), ("Liquid funds", fb.get("liquid"))]
    amounts = [(lbl, float(v)) for lbl, v in pairs if v and float(v) > 0]
    total = sum(a for _, a in amounts)
    if total <= 0:
        return []
    data = [{"label": lbl, "value": round(amt / total * 100, 1), "amount": round(amt, 2)}
            for lbl, amt in amounts]
    return [_chart("pie", "How This Goal Is Funded (% of total)", "label", "value", data)]


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
    from app.graph.tools.goal_planner_tool import _inr

    # Pre-format every chart number as a ₹ string so the (cheap) caption model copies it verbatim
    # and CANNOT rescale it (it was inflating ₹42,000 → "₹42,00,000"). Percentages stay as-is.
    charts_for_prompt = []
    for i, a in enumerate(artifacts):
        is_pct = a.get("y_field") == "value"
        pts = []
        for d in (a.get("data") or []):
            label = d.get("label") or d.get("period") or ""
            # For a percentage chart use `value` (the %); for a money chart use `amount`. NEVER mix
            # them — a pie carries BOTH (value=%, amount=₹), and reading the ₹ as a % printed
            # garbage like "₹28,49,949.6%".
            amt = d.get("value") if is_pct else d.get("amount", d.get("value"))
            if isinstance(amt, (int, float)) and not isinstance(amt, bool):
                shown = f"{round(amt, 1)}%" if is_pct else _inr(amt)
            else:
                shown = amt
            pts.append({"label": label, "value": shown})
        charts_for_prompt.append({"index": i, "title": a.get("title"), "points": pts})
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
    """Build 2-3 charts for a goal planning result — all from goal_planner data."""
    scenarios = g.get("scenarios") or []
    # A what-if has a SINGLE scenario whose detail charts live on its card — globally show the
    # budget-impact bar + the funding split (so the breakdown is visible up front), but no scenario
    # comparison and no wrong "savings progress" filler.
    if g.get("what_if") or len(scenarios) < 2:
        return _budget_impact_bar(g) + _funding_split_pie(g)
    charts: List[Dict] = []

    # Chart 1: Scenario comparison (universal — most important)
    charts += _scenarios_comparison_bar(scenarios)
    # Chart 2: Budget impact (universal)
    charts += _budget_impact_bar(g)
    # Chart 3: Self-funded vs loan-financed split (Bank / FD / Liquid slices).
    charts += _funding_split_pie(g)

    # If we still have fewer than 3, fill with a goal-type-specific chart.
    if len(charts) < 3:
        if goal_type in ("retirement", "fire"):
            charts += _fi_growth_line(g)
        elif goal_type in ("car", "house", "education"):
            charts += _emi_comparison_bar(scenarios) or _savings_progress_line(g)
        elif goal_type == "multi_goal":
            charts += _multi_goal_bar(g)
        else:
            charts += _savings_progress_line(g)
    # Last-resort fillers to reach a minimum of 2 charts.
    if len(charts) < 2:
        charts += _spending_reduction_bar(g)
    if len(charts) < 2 and g.get("portfolio_holdings"):
        charts += _portfolio_pie({"holdings": g["portfolio_holdings"]})

    return charts[:3]


# ── Per-scenario cards (interactive, one per A/B/C/D) ────────────────────────

_CARD_META = {
    "A": ("Baseline", "Your current savings — no spending cuts, no funds broken"),
    "B": ("Spending Cuts", "Free up money from wasteful categories to save more"),
    "C": ("Free Up Liquidity", "Break the minimum FDs / liquid funds needed"),
    "D": ("Everything", "Spending cuts and liquidity combined"),
}


def _bank_trajectory(s: Dict[str, Any], is_loan: bool) -> List[Dict]:
    """Line of bank balance month-by-month: grows by the scenario's monthly saving, then the down
    payment (loan goal) or the goal outflow (cash goal) is taken at the timeline end."""
    start = float(s.get("available_balance_now") or 0)
    saving = float(s.get("assumed_monthly_saving") or 0)
    months = int(s.get("timeline_months") or 0)
    if months <= 0:
        return []
    end = float(s.get("balance_after_upfront") if is_loan else s.get("projected_value_at_goal") or 0)
    pts, step = [], max(1, months // 6)
    for m in range(0, months + 1, step):
        pts.append({"period": f"M{m}", "amount": round(start + saving * m, 2)})
    if pts[-1]["period"] != f"M{months}":
        pts.append({"period": f"M{months}", "amount": round(start + saving * months, 2)})
    label = "After buy" if is_loan else "Goal"
    pts.append({"period": label, "amount": round(end, 2)})
    return [_chart("line", "Bank Balance Over Time", "period", "amount", pts)] if len(pts) >= 2 else []


def _scenario_funding_pie(s: Dict[str, Any]) -> List[Dict]:
    """Funding split for THIS scenario: loan vs bank cash vs broken FD/liquid (as % of total)."""
    dep = s.get("deployment") or {}
    loan = float(s.get("loan_amount") or 0)
    liquid = float(dep.get("from_liquid") or 0)
    fd = float(dep.get("from_fds_matured") or 0) + float(dep.get("from_fds_broken") or 0)
    self_funded = float(s.get("down_payment_amount") or s.get("target_amount") or 0)
    bank = max(0.0, self_funded - liquid - fd)
    pairs = [("Loan-financed", loan), ("Bank cash", bank), ("Fixed deposits", fd), ("Liquid funds", liquid)]
    amounts = [(lbl, v) for lbl, v in pairs if v > 0]
    total = sum(v for _, v in amounts)
    if total <= 0:
        return []
    data = [{"label": lbl, "value": round(v / total * 100, 1), "amount": round(v, 2)} for lbl, v in amounts]
    return [_chart("pie", "How This Scenario Is Funded (%)", "label", "value", data)]


def _scenario_cut_bar(g: Dict[str, Any]) -> List[Dict]:
    """Spending-cut breakdown (only meaningful for the cuts scenarios B and D)."""
    ops = g.get("spending_reduction_opportunities") or []
    data = [{"label": o.get("category"), "amount": o.get("potential_saving") or 0} for o in ops]
    data = [d for d in data if d["amount"] > 0]
    return [_chart("bar", "Monthly Saving from Spending Cuts", "label", "amount", data)] if data else []


def _scenario_metrics(s: Dict[str, Any], is_loan: bool) -> List[Dict]:
    """Key figures shown in the card's detail (pre-formatted ₹ strings copied verbatim), including
    a clear per-SOURCE breakdown of the down payment (bank cash + broken FDs + liquid + savings)."""
    from app.graph.tools.goal_planner_tool import _inr

    def inr(key):
        return s.get(f"{key}_inr") or s.get(key)
    rows = [("Bank balance now", inr("available_balance_now")),
            ("Monthly saving assumed", inr("assumed_monthly_saving"))]
    dep = s.get("deployment") or {}
    from_liquid = float(dep.get("from_liquid") or 0)
    from_fds = float(dep.get("from_fds_matured") or 0) + float(dep.get("from_fds_broken") or 0)
    if is_loan:
        # Split the down payment into its real sources so it's clear WHERE the money comes from.
        upfront_now = float(s.get("down_payment_from_existing") or 0)        # cash + broken funds now
        bank_cash = max(0.0, upfront_now - from_liquid - from_fds)           # the bank/cash portion
        saved = float(s.get("down_payment_from_savings") or 0)
        bal_after = float(s.get("balance_after_upfront") or 0)
        bal_row = (("Bank left after buying", inr("balance_after_upfront")) if bal_after >= 0
                   else ("Funding shortfall", _inr(abs(bal_after))))
        rows += [("Down payment (total)", inr("down_payment_amount"))]
        # Down-payment sources (only the non-zero ones):
        if bank_cash > 0:
            rows.append(("  • from bank cash", _inr(bank_cash)))
        if from_fds > 0:
            names = ", ".join(dep.get("fds_broken") or []) or "FD"
            rows.append((f"  • from broken FDs ({names})", _inr(from_fds)))
        if from_liquid > 0:
            rows.append(("  • from liquid funds", _inr(from_liquid)))
        if saved > 0:
            rows.append(("  • saved over timeline", _inr(saved) + f" ({inr('monthly_savings_needed')}/mo)"))
        rows += [
            ("Loan amount", inr("loan_amount")),
            ("EMI / month", inr("estimated_emi")),
            ("Total interest", inr("total_interest_paid")),
            ("Total cost", inr("total_cost_of_ownership")),
            bal_row,
        ]
        if float(s.get("penalty_paid") or dep.get("penalty_paid") or 0) > 0:
            rows.append(("Interest forfeited (breaking FDs)", dep.get("penalty_paid_inr") or _inr(dep.get("penalty_paid") or 0)))
        # Assumptions, stated plainly.
        if s.get("loan_amount"):
            rows.append(("Assumes loan", f"{s.get('loan_rate_pct')}% p.a. over {s.get('loan_tenure_months')} months"))
    else:
        rows += [
            ("Target", inr("target_amount")),
            ("Saved over timeline", inr("total_savings_pot")),
            ("Projected at goal", inr("projected_value_at_goal")),
        ]
        if from_liquid > 0:
            rows.append(("  • from liquid funds", _inr(from_liquid)))
        if from_fds > 0:
            rows.append((f"  • from broken FDs ({', '.join(dep.get('fds_broken') or []) or 'FD'})", _inr(from_fds)))
    return [{"label": k, "value": str(v)} for k, v in rows if v not in (None, "", "₹0", 0)]


def _proscons_for_cards(cards: List[Dict], g: Dict[str, Any]) -> None:
    """One cheap LLM pass writes pros/cons + a bottom_line for ALL cards, grounded in the facts."""
    facts = {"goal_type": g.get("goal_type"), "target_amount": g.get("target_amount_inr") or g.get("target_amount"),
             "current_monthly_saving": g.get("monthly_net_flow_inr"),
             "reclaimable_cuts": g.get("total_spending_cuts_inr") or g.get("total_spending_cuts"),
             "cards": [{"tag": c["tag"], "name": c["title"], "feasible": c["feasible"],
                        # explicit flags so the model never mislabels (e.g. "no lifestyle change" for D)
                        "uses_spending_cuts": c.get("uses_cuts", False),
                        "breaks_funds": c.get("breaks_funds", False),
                        "metrics": c["metrics"]} for c in cards]}
    try:
        completion = graph_chat_completion(
            node="answer_node", purpose="scenario_cards", model=settings.fast_model,
            messages=[{"role": "system", "content": GOAL_CARDS_SYSTEM},
                      {"role": "user", "content": json.dumps(facts, default=str)}],
            response_format={"type": "json_object"}, max_tokens=700, temperature=0.2,
        )
        out = (json.loads(completion.choices[0].message.content.strip()) or {}).get("cards") or []
        by_tag = {c.get("tag"): c for c in out if isinstance(c, dict)}
        for card in cards:
            pc = by_tag.get(card["tag"]) or {}
            card["pros"] = [p for p in (pc.get("pros") or []) if isinstance(p, str)]
            card["cons"] = [c for c in (pc.get("cons") or []) if isinstance(c, str)]
            card["bottom_line"] = pc.get("bottom_line") if isinstance(pc.get("bottom_line"), str) else ""
    except Exception as exc:
        logger.warning("[answer_node] scenario card pros/cons failed: %s", exc)


def _build_scenario_cards(goal_type: str, g: Dict[str, Any]) -> List[Dict]:
    """Build one interactive card per scenario (A/B/C/D): title, feasibility, key metrics,
    per-card charts, and (via one LLM pass) pros/cons."""
    scenarios = g.get("scenarios") or []
    what_if = bool(g.get("what_if"))
    # A normal plan shows all four scenarios; a what-if shows the SINGLE scenario it kept.
    if (not what_if and len(scenarios) < 2) or not scenarios:
        return []
    is_loan = goal_type in ("car", "house", "education")
    cards: List[Dict] = []
    for s in scenarios:
        tag = s.get("tag")
        if what_if:
            title, subtitle = "What-if result", g.get("what_if_summary") or s.get("label", "")
        else:
            title, subtitle = _CARD_META.get(tag, (s.get("label", tag), ""))
        uses_cuts = tag in ("B", "D")
        breaks_funds = bool((s.get("deployment") or {}).get("deployed_total"))
        charts = _bank_trajectory(s, is_loan) + _scenario_funding_pie(s)
        metrics = _scenario_metrics(s, is_loan)
        if uses_cuts:                              # name HOW the extra monthly cash is freed up
            charts += _scenario_cut_bar(g)
            for o in (g.get("spending_reduction_opportunities") or [])[:5]:
                amt = o.get("potential_saving_inr") or o.get("potential_saving")
                if amt and o.get("category"):
                    metrics.append({"label": f"Cut {o['category']}", "value": f"−{amt}/mo"})
        cards.append({
            "tag": tag, "title": title, "subtitle": subtitle,
            "recommended": bool(s.get("recommended")),
            "feasible": bool(s.get("feasible")),
            "uses_cuts": uses_cuts, "breaks_funds": breaks_funds,
            "headline": s.get("estimated_emi_inr") if is_loan else s.get("monthly_savings_needed_inr"),
            "metrics": metrics,
            "charts": charts,
            "pros": [], "cons": [], "bottom_line": "",
        })
    _proscons_for_cards(cards, g)
    return cards


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
    scenario_cards: List[Dict] = []
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
            goal_type = str(g.get("goal_type") or "generic").lower()

            # The main response is a SHORT verdict + why + comparison table; the per-scenario detail
            # lives in interactive cards (built below). What-ifs get the SAME detailed cards + charts
            # — just a question-focused text answer instead of the standard verdict.
            artifacts = _select_goal_artifacts(goal_type, g)
            scenario_cards = _build_scenario_cards(goal_type, g)
            if g.get("what_if"):
                system_prompt = GOAL_WHATIF_SYSTEM.format(context_text=ctx, **fields)
                max_tokens = 900
            else:
                system_prompt = GOAL_PLAN_SYSTEM.format(context_text=ctx, **fields)
                max_tokens = 900

            completion = graph_chat_completion(
                node="answer_node", purpose="goal_plan", model=settings.active_chat_model,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_query}],
                max_tokens=max_tokens, temperature=0.15,
            )
            answer = completion.choices[0].message.content.strip()
            if getattr(completion.choices[0], "finish_reason", None) == "length":
                logger.warning("[answer_node] goal_plan answer hit the %d-token cap and was "
                               "truncated (goal_type=%s)", max_tokens, goal_type)
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

    logger.info("[Node:answer] intent=%s artifacts=%d cards=%d", intent, len(artifacts), len(scenario_cards))
    return {
        "final_answer": answer,
        "artifacts": artifacts,
        "scenario_cards": scenario_cards,
        "sources": sources,
        "final_intent": intent,
        "messages": [AIMessage(content=answer)],
    }
