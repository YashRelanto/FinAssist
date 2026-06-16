"""
Investment Analysis Engine — portfolio insights from live Supabase holdings.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.utils.supabase_client import supabase

logger = logging.getLogger(__name__)

INVESTMENT_DISCLAIMER = (
    "This is general financial information, not SEBI-registered investment advice. "
    "Consult a qualified advisor before making investment decisions."
)

ASSET_TYPES = ("mutual_fund", "stock", "etf", "bond", "gold", "sip")


def _fetch_scheme_nav(scheme_code: str) -> Dict[str, Any]:
    try:
        url = f"https://api.mfapi.in/mf/{scheme_code}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except Exception as exc:
        logger.warning("[investment] NAV fetch failed for %s: %s", scheme_code, exc)
        return {}


def _fetch_gold_rate_inr() -> float:
    """Best-effort gold rate per gram (24K) in INR."""
    try:
        url = "https://api.goldapi.io/api/XAU/INR"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode())
            return float(data.get("price", 0)) / 31.1035
    except Exception:
        return 0.0


def _profile_aware_recommendations(
    holdings: List[Dict[str, Any]],
    portfolio_health: Dict[str, Any],
    profile: Dict[str, Any],
) -> List[str]:
    recs: List[str] = []
    gain_pct = portfolio_health.get("total_gain_percentage", 0)
    risk = (profile.get("risk_profile") or "").lower()
    income = float(profile.get("income") or 0)
    emi = float(profile.get("fixed_emi") or 0)
    goals = profile.get("goals") or []

    if gain_pct < 0:
        recs.append(
            "Review underperforming holdings and consider rebalancing toward diversified index funds."
        )
    elif gain_pct > 15:
        recs.append("Strong gains detected — consider partial profit booking if goals are near-term.")

    concentrated = [h for h in holdings if h.get("portfolio_share", 0) > 40]
    if concentrated:
        recs.append(
            f"Reduce concentration in {concentrated[0].get('name', 'top holding')} "
            f"({concentrated[0]['portfolio_share']:.1f}% of portfolio)."
        )

    asset_types = {h.get("asset_type") for h in holdings}
    if len(asset_types) < 2:
        recs.append(
            "Diversify across mutual funds, equity, debt, and gold for better risk-adjusted returns."
        )

    if risk == "conservative" and any(h.get("asset_type") in ("stock", "etf") for h in holdings):
        recs.append(
            "Your risk profile is conservative but you hold equity — review allocation vs comfort level."
        )
    elif risk == "aggressive" and not any(h.get("asset_type") in ("stock", "etf") for h in holdings):
        recs.append("Aggressive risk profile with limited equity exposure — consider increasing equity allocation.")

    if income > 0 and emi > 0:
        emi_ratio = emi / income
        if emi_ratio > 0.4:
            recs.append(
                f"EMIs consume {emi_ratio:.0%} of income — prioritize debt reduction before new investments."
            )

    for goal in goals[:2]:
        target = float(goal.get("target_amount") or 0)
        current = float(goal.get("current_amount") or 0)
        if target > 0 and current < target * 0.5:
            recs.append(
                f"Goal '{goal.get('goal_name')}' is below 50% funded — increase SIP allocation if cashflow allows."
            )

    if not recs:
        recs.append("Continue SIPs and review asset allocation annually.")
    return recs


def _apply_focus(result: Dict[str, Any], focus: str) -> Dict[str, Any]:
    if focus == "performance":
        return {
            "portfolio_health": result.get("portfolio_health"),
            "holdings": result.get("holdings"),
            "recommendations": [
                r for r in result.get("recommendations", [])
                if "gain" in r.lower() or "perform" in r.lower() or "SIP" in r
            ] or result.get("recommendations", [])[:2],
            "focus": focus,
        }
    if focus == "allocation":
        by_type: Dict[str, float] = {}
        for h in result.get("holdings", []):
            at = h.get("asset_type", "mutual_fund")
            by_type[at] = by_type.get(at, 0) + h.get("portfolio_share", 0)
        return {
            "portfolio_health": {
                "allocation_by_asset_type": by_type,
                "scheme_count": result.get("portfolio_health", {}).get("scheme_count"),
            },
            "holdings": result.get("holdings"),
            "recommendations": [
                r for r in result.get("recommendations", [])
                if "concentrat" in r.lower() or "diversif" in r.lower() or "allocation" in r.lower()
            ] or result.get("recommendations", [])[:2],
            "focus": focus,
        }
    result["focus"] = focus
    return result


def analyze_portfolio(
    user_id: str,
    user_profile: Optional[Dict[str, Any]] = None,
    focus: str = "full",
) -> Dict[str, Any]:
    """
    Build portfolio health metrics and recommendations from Supabase holdings.
    Supports mutual funds (live NAV), and other asset types via stored purchase_nav.
    """
    profile = user_profile or {}
    empty = {
        "portfolio_health": {
            "status": "no_holdings",
            "total_invested": 0.0,
            "current_value": 0.0,
            "total_gain": 0.0,
            "total_gain_percentage": 0.0,
            "portfolio_cagr": "0.0%",
            "scheme_count": 0,
            "allocation_by_asset_type": {},
        },
        "holdings": [],
        "recommendations": [
            "Start a diversified SIP aligned with your risk profile to build long-term wealth.",
        ],
        "disclaimer": INVESTMENT_DISCLAIMER,
    }

    if not supabase:
        return {**empty, "error": "Database unavailable"}

    try:
        res = supabase.table("investments").select("*").eq("user_id", user_id).execute()
        db_investments: List[Dict[str, Any]] = res.data or []
    except Exception as exc:
        logger.error("[investment] Failed to fetch holdings: %s", exc)
        return {**empty, "error": str(exc)}

    if not db_investments:
        return _apply_focus(empty, focus)

    mf_codes = list({
        inv["scheme_code"]
        for inv in db_investments
        if (inv.get("asset_type") or "mutual_fund") in ("mutual_fund", "sip")
    })
    scheme_cache = {code: _fetch_scheme_nav(code) for code in mf_codes}
    gold_rate = _fetch_gold_rate_inr()

    holdings_map: Dict[str, Dict[str, Any]] = {}
    for inv in db_investments:
        asset_type = (inv.get("asset_type") or "mutual_fund").lower()
        code = inv.get("scheme_code") or inv.get("symbol") or "unknown"
        qty = float(inv.get("quantity") or 0)
        purch_nav = float(inv.get("purchase_nav") or 0)
        name = inv.get("scheme_name") or inv.get("symbol") or code
        key = f"{asset_type}:{code}"

        current_price = purch_nav
        if asset_type in ("mutual_fund", "sip") and code in scheme_cache:
            nav_list = scheme_cache[code].get("data", [])
            if nav_list:
                current_price = float(nav_list[0]["nav"])
        elif asset_type == "gold" and gold_rate > 0:
            current_price = gold_rate

        if key not in holdings_map:
            holdings_map[key] = {
                "asset_type": asset_type,
                "scheme_code": code,
                "symbol": code,
                "name": name,
                "scheme_name": name,
                "quantity": 0.0,
                "invested": 0.0,
                "current_nav": current_price,
                "current_value": 0.0,
                "gain": 0.0,
                "gain_percent": 0.0,
            }

        h = holdings_map[key]
        h["quantity"] += qty
        h["invested"] += qty * purch_nav
        if current_price > 0:
            h["current_nav"] = current_price

    holdings: List[Dict[str, Any]] = []
    total_invested = 0.0
    total_current = 0.0

    for h in holdings_map.values():
        if h["quantity"] <= 0:
            continue
        h["current_value"] = h["quantity"] * h["current_nav"]
        h["gain"] = h["current_value"] - h["invested"]
        h["gain_percent"] = (h["gain"] / h["invested"] * 100) if h["invested"] > 0 else 0.0
        total_invested += h["invested"]
        total_current += h["current_value"]
        holdings.append(h)

    for h in holdings:
        h["portfolio_share"] = (
            (h["current_value"] / total_current * 100) if total_current > 0 else 0.0
        )

    total_gain = total_current - total_invested
    gain_pct = (total_gain / total_invested * 100) if total_invested > 0 else 0.0

    earliest = datetime.now().date()
    for inv in db_investments:
        d_str = inv.get("transaction_date")
        if not d_str:
            continue
        d = datetime.strptime(d_str, "%Y-%m-%d").date()
        if d < earliest:
            earliest = d
    years = max((datetime.now().date() - earliest).days / 365.0, 0.01)
    cagr = (
        ((total_current / total_invested) ** (1 / years) - 1) * 100
        if total_invested > 0 and total_current > 0
        else 0.0
    )

    allocation_by_type: Dict[str, float] = {}
    for h in holdings:
        at = h.get("asset_type", "mutual_fund")
        allocation_by_type[at] = allocation_by_type.get(at, 0) + h.get("portfolio_share", 0)

    portfolio_health = {
        "status": "healthy" if gain_pct >= 0 else "underperforming",
        "total_invested": round(total_invested, 2),
        "current_value": round(total_current, 2),
        "total_gain": round(total_gain, 2),
        "total_gain_percentage": round(gain_pct, 2),
        "portfolio_cagr": f"{cagr:.1f}%",
        "scheme_count": len(holdings),
        "allocation_by_asset_type": {k: round(v, 2) for k, v in allocation_by_type.items()},
    }

    recommendations = _profile_aware_recommendations(holdings, portfolio_health, profile)

    logger.info(
        "[investment] user=%s holdings=%d invested=%.2f current=%.2f",
        user_id,
        len(holdings),
        total_invested,
        total_current,
    )

    result = {
        "portfolio_health": portfolio_health,
        "holdings": holdings,
        "recommendations": recommendations,
        "disclaimer": INVESTMENT_DISCLAIMER,
    }
    return _apply_focus(result, focus)
