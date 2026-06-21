"""
Investment Tool — portfolio, savings, and asset-allocation analysis.

Computes live portfolio metrics (holdings, current NAV, gains, allocation shares)
and aggregate savings metrics, runs the specialised investment-analysis prompt to
produce a narrative, and returns everything as an `evidence` item. The answer node
uses the narrative as the answer text and builds a portfolio-allocation pie chart
from the holdings data.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import urllib.request
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.graph.llm import graph_chat_completion
from app.graph.state import AgentState
from app.utils.supabase_client import supabase_db as supabase
from app.utils.prompts import INVESTMENT_ANALYSIS_SYSTEM, INVESTMENT_ANALYSIS_USER

logger = logging.getLogger(__name__)

# Risk-free rate (~India T-bill) used for Sharpe / Sortino / Treynor.
RF_ANNUAL = 0.065
# A Nifty-50 index fund scheme code on api.mfapi.in, used as the MARKET benchmark for beta / alpha /
# treynor. If it can't be fetched (or histories don't align) those three are reported as null.
_BENCHMARK_SCHEME_CODE = "120716"  # UTI Nifty 50 Index Fund (benchmark proxy)


def _monthly_nav_map(scheme_data: Optional[Dict]) -> Dict[str, float]:
    """{'YYYY-MM': nav} taking the LATEST NAV in each month (mfapi returns latest-first)."""
    out: Dict[str, float] = {}
    for entry in (scheme_data or {}).get("data", []) or []:
        try:
            dd, mm, yyyy = entry["date"].split("-")          # 'DD-MM-YYYY'
            ym = f"{yyyy}-{mm}"
            if ym not in out:                                # first seen = latest in that month
                out[ym] = float(entry["nav"])
        except Exception:
            continue
    return out


def _pct_returns(values: List[float]) -> List[float]:
    return [values[i] / values[i - 1] - 1.0 for i in range(1, len(values)) if values[i - 1]]


def _fetch_scheme_history(code: str) -> Optional[Dict]:
    try:
        req = urllib.request.Request(f"https://api.mfapi.in/mf/{code}", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode())
    except Exception as exc:
        logger.warning("[investment] history fetch failed for %s: %s", code, exc)
        return None


def _risk_ratios(port_returns: List[float], bench_returns: Optional[List[float]]) -> Dict[str, Any]:
    """Annualised risk-adjusted ratios from MONTHLY returns. Benchmark-dependent ratios
    (beta/alpha/treynor) are null when no aligned benchmark series is available."""
    out: Dict[str, Any] = {"sharpe": None, "sortino": None, "treynor": None, "alpha": None,
                           "beta": None, "volatility_pct": None, "months": len(port_returns)}
    if len(port_returns) < 3:
        return out
    rf_m = RF_ANNUAL / 12.0
    mean_p = statistics.fmean(port_returns)
    sd_p = statistics.pstdev(port_returns)
    if sd_p > 0:
        out["volatility_pct"] = round(sd_p * math.sqrt(12) * 100, 2)
        out["sharpe"] = round((mean_p - rf_m) / sd_p * math.sqrt(12), 2)
    downside = [min(0.0, r - rf_m) for r in port_returns]
    dd = math.sqrt(statistics.fmean([d * d for d in downside]))
    if dd > 0:
        out["sortino"] = round((mean_p - rf_m) / dd * math.sqrt(12), 2)
    if bench_returns and len(bench_returns) == len(port_returns) and len(bench_returns) >= 3:
        mean_b = statistics.fmean(bench_returns)
        var_b = statistics.pvariance(bench_returns)
        if var_b > 0:
            cov = statistics.fmean([(port_returns[i] - mean_p) * (bench_returns[i] - mean_b)
                                    for i in range(len(port_returns))])
            beta = cov / var_b
            out["beta"] = round(beta, 2)
            out["alpha"] = round(((mean_p - rf_m) - beta * (mean_b - rf_m)) * 12 * 100, 2)  # annualised %
            if beta != 0:
                out["treynor"] = round((mean_p - rf_m) * 12 / beta, 4)
    return out


def _diversification(holdings: List[Dict]) -> Dict[str, Any]:
    """Concentration snapshot: holding count, top-holding %, Herfindahl index, and a verdict."""
    n = len(holdings)
    shares = sorted((float(h.get("share_pct") or 0) for h in holdings), reverse=True)
    top = shares[0] if shares else 0.0
    hhi = round(sum((s / 100.0) ** 2 for s in shares), 3)   # 1.0 = single holding, →0 = well spread
    if n <= 1 or top >= 60:
        verdict = "Highly concentrated — most of the portfolio sits in one or two holdings."
    elif n <= 3 or top >= 40:
        verdict = "Moderately concentrated — consider spreading across more funds / asset classes."
    else:
        verdict = "Reasonably diversified across holdings."
    return {"holdings_count": n, "top_holding_pct": round(top, 2), "hhi": hhi, "verdict": verdict}


def _fmt_ratios(r: Dict[str, Any]) -> str:
    labels = [("sharpe", "Sharpe ratio"), ("sortino", "Sortino ratio"), ("treynor", "Treynor ratio"),
              ("alpha", "Alpha (annualised %)"), ("beta", "Beta"),
              ("volatility_pct", "Volatility / std-dev (annualised %)")]
    lines = [f"- {lbl}: {r[k]}" for k, lbl in labels if r.get(k) is not None]
    if not lines:
        return (f"Not enough NAV history to compute risk ratios "
                f"(have {r.get('months', 0)} monthly returns; need ~3+).")
    return "\n".join(lines) + f"\n(From {r.get('months')} monthly returns; risk-free {RF_ANNUAL * 100:.1f}% p.a.)"


def _fmt_div(d: Dict[str, Any]) -> str:
    return (f"- Holdings: {d['holdings_count']}\n"
            f"- Top holding: {d['top_holding_pct']}% of portfolio\n"
            f"- Concentration index (HHI): {d['hhi']}\n"
            f"- Verdict: {d['verdict']}")


def investment_tool(state: AgentState) -> dict:
    """Analyse the user's portfolio + savings and return an evidence item."""
    user_id = state.get("user_id") or ""
    task = state.get("brain_task") or {}
    query = task.get("sub_question") or state.get("user_query") or ""

    if not user_id or not supabase:
        return {
            "evidence": [{
                "tool": "investment",
                "task": query,
                "summary": "User profile unavailable.",
                "data": {"narrative": "I could not locate your investment data. Please log in and try again."},
            }],
            "sources": ["Supabase Database"],
        }

    try:
        # 1. Profile (income, rent, EMI)
        prof_res = supabase.table("user_profiles").select("income, fixed_rent, fixed_emi").eq("user_id", user_id).execute()
        profile_data = prof_res.data[0] if prof_res.data else {}
        monthly_income = float(profile_data.get("income") or 0.0)
        fixed_rent = float(profile_data.get("fixed_rent") or 0.0)
        fixed_emi = float(profile_data.get("fixed_emi") or 0.0)

        # 2. Investments + live NAVs
        inv_res = supabase.table("investments").select("*").eq("user_id", user_id).execute()
        db_investments = inv_res.data or []

        scheme_data_cache: Dict[str, Any] = {}
        for code in {inv["scheme_code"] for inv in db_investments}:
            try:
                req = urllib.request.Request(f"https://api.mfapi.in/mf/{code}", headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req) as response:
                    scheme_data_cache[code] = json.loads(response.read().decode())
            except Exception as e:
                logger.error("[investment] NAV fetch failed for %s: %s", code, e)

        holdings_map: Dict[str, Any] = {}
        for inv in db_investments:
            code = inv["scheme_code"]
            qty = float(inv["quantity"] or 0.0)
            purch_nav = float(inv["purchase_nav"] or 0.0)
            current_nav = purch_nav
            if code in scheme_data_cache:
                nav_list = scheme_data_cache[code].get("data", [])
                if nav_list:
                    try:
                        current_nav = float(nav_list[0]["nav"])
                    except Exception:
                        pass
            h = holdings_map.setdefault(code, {"name": inv["scheme_name"], "quantity": 0.0,
                                               "invested_value": 0.0, "current_nav": current_nav})
            h["quantity"] += qty
            h["invested_value"] += qty * purch_nav

        total_invested_val = total_current_val = 0.0
        for h in holdings_map.values():
            h["current_value"] = h["quantity"] * h["current_nav"]
            h["gain"] = h["current_value"] - h["invested_value"]
            h["gain_pct"] = (h["gain"] / h["invested_value"] * 100.0) if h["invested_value"] > 0 else 0.0
            total_invested_val += h["invested_value"]
            total_current_val += h["current_value"]

        holdings: List[Dict[str, Any]] = []
        portfolio_summary_lines = []
        for code, h in holdings_map.items():
            share = (h["current_value"] / total_current_val * 100.0) if total_current_val > 0 else 0.0
            holdings.append({"name": h["name"], "current_value": round(h["current_value"], 2),
                             "share_pct": round(share, 2), "gain_pct": round(h["gain_pct"], 2)})
            portfolio_summary_lines.append(
                f"- {h['name']} ({code}): invested ₹{h['invested_value']:,.2f}, "
                f"current ₹{h['current_value']:,.2f}, gain {h['gain_pct']:.2f}%, share {share:.2f}%"
            )

        total_gain_val = total_current_val - total_invested_val
        total_gain_pct = (total_gain_val / total_invested_val * 100.0) if total_invested_val > 0 else 0.0
        portfolio_summary = (
            f"Total Invested: ₹{total_invested_val:,.2f}; Current Value: ₹{total_current_val:,.2f}; "
            f"P/L: ₹{total_gain_val:,.2f} ({total_gain_pct:.2f}%)\n" + "\n".join(portfolio_summary_lines)
        ) if db_investments else "No active investments found."

        # 2b. Risk-adjusted ratios + diversification from monthly NAV history (best-effort).
        nav_maps = {code: _monthly_nav_map(scheme_data_cache.get(code)) for code in holdings_map}
        common_months = sorted(set.intersection(*[set(m.keys()) for m in nav_maps.values()])) if nav_maps else []
        port_returns: List[float] = []
        if len(common_months) >= 4:
            series = [sum(holdings_map[code]["quantity"] * nav_maps[code][mo] for code in holdings_map)
                      for mo in common_months]
            port_returns = _pct_returns(series)
        bench_returns = None
        if common_months:
            bmap = _monthly_nav_map(_fetch_scheme_history(_BENCHMARK_SCHEME_CODE))
            bvals = [bmap[mo] for mo in common_months if mo in bmap]
            if len(bvals) == len(common_months):
                bench_returns = _pct_returns(bvals)
        risk_ratios = _risk_ratios(port_returns, bench_returns)
        diversification = _diversification(holdings)

        # 3. Transaction aggregates
        tx_res = supabase.table("transactions").select(
            "amount, transaction_type, transaction_date, categories(main_category)"
        ).eq("user_id", user_id).execute()
        transactions = tx_res.data or []

        total_income = total_expenses = 0.0
        category_totals: Dict[str, float] = {}
        monthly_stats: Dict[str, Dict[str, float]] = {}
        for tx in transactions:
            ttype = (tx.get("transaction_type") or "").lower()
            amount = abs(float(tx.get("amount") or 0.0))
            month = (tx.get("transaction_date") or "")[:7]
            if ttype == "income":
                total_income += amount
                if month:
                    monthly_stats.setdefault(month, {"income": 0.0, "expense": 0.0})["income"] += amount
            elif ttype == "expense":
                total_expenses += amount
                if month:
                    monthly_stats.setdefault(month, {"income": 0.0, "expense": 0.0})["expense"] += amount
                cat = (tx.get("categories") or {}).get("main_category") or "Others"
                category_totals[cat] = category_totals.get(cat, 0.0) + amount

        net_savings = total_income - total_expenses
        net_savings_rate = (net_savings / total_income * 100.0) if total_income > 0 else 0.0

        monthly_savings = [
            f"- {m}: savings rate {((s['income'] - s['expense']) / s['income'] * 100.0) if s['income'] > 0 else 0:.2f}% "
            f"(income ₹{s['income']:,.2f}, expense ₹{s['expense']:,.2f})"
            for m, s in sorted(monthly_stats.items())
        ]
        monthly_savings_str = "\n".join(monthly_savings) if monthly_savings else "No monthly history."
        category_expenses_str = "\n".join(
            f"- {c}: ₹{a:,.2f}" for c, a in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
        ) or "No expenses logged."

        # 4. Narrative via specialised prompt
        user_msg = INVESTMENT_ANALYSIS_USER.format(
            monthly_income=f"₹{monthly_income:,.2f}", fixed_rent=f"₹{fixed_rent:,.2f}",
            fixed_emi=f"₹{fixed_emi:,.2f}", portfolio_summary=portfolio_summary,
            risk_metrics=_fmt_ratios(risk_ratios), diversification=_fmt_div(diversification),
            net_savings=f"₹{net_savings:,.2f}", net_savings_rate=f"{net_savings_rate:.2f}%",
            monthly_savings_trajectory=monthly_savings_str, category_expenses=category_expenses_str, query=query,
        )
        response = graph_chat_completion(
            node="investment_tool", purpose="portfolio_guidance",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": INVESTMENT_ANALYSIS_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=800, temperature=0.2,
        )
        narrative = response.choices[0].message.content.strip()

        data = {
            "narrative": narrative,
            "holdings": holdings,
            "total_invested": round(total_invested_val, 2),
            "total_current": round(total_current_val, 2),
            "total_gain_pct": round(total_gain_pct, 2),
            "net_savings": round(net_savings, 2),
            "net_savings_rate": round(net_savings_rate, 2),
            "risk_ratios": risk_ratios,
            "diversification": diversification,
        }
        logger.info("[investment] Completed analysis for user %s (%d holdings)", user_id, len(holdings))
        return {
            "evidence": [{"tool": "investment", "task": query,
                          "summary": f"Portfolio worth ₹{total_current_val:,.2f}, {len(holdings)} holdings.",
                          "data": data}],
            "sources": ["Supabase Investments", "Supabase Transactions", "Supabase User Profiles"],
        }
    except Exception as exc:
        logger.error("[investment] Analysis failed: %s", exc)
        return {
            "evidence": [{"tool": "investment", "task": query, "summary": "Analysis error.",
                          "data": {"narrative": "I encountered an error while analyzing your portfolio. Please try again."}}],
            "sources": ["System Fallback"],
        }
