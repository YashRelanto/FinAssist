"""
Goal Planner Tool — deep, scenario-based affordability analysis for 10 goal types.

Every planner produces THREE scenarios (A / B / C) so the user sees trade-offs, not just
one number.  The recommended scenario is always B (user's actual choice / sensible default).
All scenarios share a consistent structure so chart builders work generically.
"""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.graph.state import AgentState
from app.utils.supabase_client import supabase_db

logger = logging.getLogger(__name__)


# ── Amount / timeline parsing ─────────────────────────────────────────────────

def _parse_amount(v: Any) -> Optional[float]:
    """Parse human-entered amounts: '₹2L', '50k', '2,50,000', '12-15 lakh' → float."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    s = s.replace("₹", "").replace(",", "").replace(" ", "")
    # Range like "12-15" → take midpoint
    range_m = re.match(r"^([\d.]+)[-–]([\d.]+)(.*)", s)
    if range_m:
        lo, hi, suffix = float(range_m.group(1)), float(range_m.group(2)), range_m.group(3).strip()
        mid = (lo + hi) / 2
        s = f"{mid}{suffix}"
    try:
        m = re.search(r"[\d.]+", s)
        if not m:
            return None
        num = float(m.group())
        # Unit detection via substring so plurals work: lakh/lakhs/lac/lacs, cr/crore/crores.
        if "cr" in s or "crore" in s:
            return num * 10_000_000
        if "lakh" in s or "lac" in s:
            return num * 100_000
        if "million" in s or "mn" in s:
            return num * 1_000_000
        if s.endswith("l"):              # bare "13.5l" shorthand for lakh
            return num * 100_000
        if s.endswith("k") or "thousand" in s:
            return num * 1_000
        return num
    except Exception:
        return None


def _months_from_timeline(timeline: Any) -> Optional[float]:
    """Default is months"""
    if timeline is None:
        return None
    if isinstance(timeline, (int, float)):
        return float(timeline)
    text = str(timeline).lower().strip()
    # Range like "1-1.5 years" → take midpoint
    range_m = re.match(r"^([\d.]+)[-–]([\d.]+)\s*(year|yr|month|mon)", text)
    if range_m:
        lo, hi = float(range_m.group(1)), float(range_m.group(2))
        unit = range_m.group(3)
        mid = (lo + hi) / 2
        return mid * 12 if "year" in unit or "yr" in unit else mid
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    value = float(m.group(1))
    if "year" in text or "yr" in text:
        return value * 12.0
    if "week" in text:
        return value / 4.345
    if "day" in text:
        return value / 30.0
    return value  # assume months


def _num(v: Any, default: float) -> float:
    """Extract a number from any value the model may send: '30%', '6 months', 'age 24', 24."""
    if v is None:
        return float(default)
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group()) if m else float(default)


def _inr(amount: Any) -> str:
    """Format a number in Indian grouping with a ₹ prefix: 1350000 -> '₹13,50,000'."""
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    neg = n < 0
    n = abs(round(n))
    s = str(int(n))
    if len(s) > 3:
        last3 = s[-3:]
        rest = s[:-3]
        # group the remaining digits in pairs (Indian system)
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        s = ",".join(parts) + "," + last3
    return f"{'-' if neg else ''}₹{s}"


# Field-name tokens that identify a money amount vs. a non-money number (pct/age/months).
_MONEY_TOKENS = {
    "amount", "saving", "savings", "emi", "balance", "income", "spend", "flow", "gap",
    "payment", "loan", "interest", "cost", "value", "target", "shortfall", "needed",
    "allocated", "potential", "monthly", "corpus", "sip", "worth", "investment", "fund",
    "price", "budget", "total", "outgo", "commitment", "outstanding", "liquid", "stamp", "duty",
}
_SKIP_TOKENS = {
    "pct", "percent", "age", "rate", "count", "ratio", "share", "tenure", "observed",
    "travelers", "month", "months", "y  ear", "years", "timeline", "coverage", "fv",
}


def _attach_inr(obj: Any) -> Any:
    """
    Recursively add a ₹-formatted sibling (key + '_inr') for every MONETARY number so the
    answer/caption models copy a correct full-rupee string and never rescale to 'lakhs'.
    """
    if isinstance(obj, list):
        for item in obj:
            _attach_inr(item)
    elif isinstance(obj, dict):
        for key in list(obj.keys()):
            val = obj[key]
            if isinstance(val, (dict, list)):
                _attach_inr(val)
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                parts = set(str(key).lower().split("_"))
                if parts & _SKIP_TOKENS:
                    continue
                if parts & _MONEY_TOKENS:
                    obj[f"{key}_inr"] = _inr(val)
    return obj


# ── Financial helpers ─────────────────────────────────────────────────────────

def _calc_emi(principal: float, annual_rate_pct: float, tenure_months: int) -> float:
    if tenure_months <= 0 or principal <= 0:
        return 0.0
    r = (annual_rate_pct / 100.0) / 12.0
    if r == 0:
        return principal / tenure_months
    return principal * r * (1 + r) ** tenure_months / ((1 + r) ** tenure_months - 1)


def _monthly_sip_for_corpus(target: float, annual_return_pct: float, tenure_months: int) -> float:
    if tenure_months <= 0 or target <= 0:
        return 0.0
    r = (annual_return_pct / 100.0) / 12.0
    if r == 0:
        return target / tenure_months
    return target * r / ((1 + r) ** tenure_months - 1)


def _corpus_growth(current: float, monthly: float, annual_return: float, months: int) -> float:
    r = annual_return / 12.0
    return current * (1 + r) ** months + (
        monthly * ((1 + r) ** months - 1) / r if r else monthly * months
    )


def _years_to_fi(current: float, monthly: float, corpus: float, annual_return: float = 0.12) -> float:
    if monthly <= 0 and current >= corpus:
        return 0.0
    r = annual_return / 12.0
    for n in range(1, 601):
        fv = _corpus_growth(current, monthly, annual_return, n)
        if fv >= corpus:
            return round(n / 12.0, 1)
    return None  # FI not reachable within 50 years on these assumptions


# ── Fixed-deposit valuation ───────────────────────────────────────────────────

_FD_COMPOUND_N = {"monthly": 12, "quarterly": 4, "half-yearly": 2, "annually": 1}


def _parse_date(v: Any) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _fd_value(principal: float, rate_pct: float, comp_freq: str, years: float,
              payout_type: str = "cumulative") -> float:
    """Value of an FD after `years` at `rate_pct` p.a. with the given compounding."""
    principal = max(0.0, float(principal or 0))
    if years <= 0:
        return principal
    # A payout FD pays interest out periodically, so the corpus stays at principal.
    if str(payout_type or "").lower() == "payout":
        return principal
    r = float(rate_pct or 0) / 100.0
    cf = str(comp_freq or "quarterly").lower()
    if cf == "simple":
        return principal * (1 + r * years)
    n = _FD_COMPOUND_N.get(cf, 4)
    return principal * (1 + r / n) ** (n * years)


def _fd_years(start: Optional[date], end: Optional[date]) -> float:
    if not start or not end:
        return 0.0
    return max(0.0, (end - start).days / 365.25)


def _fd_metrics(fd: Dict[str, Any], as_of: Optional[date] = None) -> Dict[str, Any]:
    """
    Per-FD value snapshot: current accrued value, maturity value, and the net cash if the FD is
    broken TODAY (interest recomputed at a penalised rate) plus the cost of doing so.
    """
    as_of = as_of or date.today()
    start = _parse_date(fd.get("start_date"))
    maturity = _parse_date(fd.get("maturity_date"))
    principal = float(fd.get("principal_amount") or 0)
    rate = float(fd.get("interest_rate_pct") or 0)
    comp = fd.get("compounding_frequency") or "quarterly"
    payout = fd.get("payout_type") or "cumulative"
    penalty = float(fd.get("premature_penalty_pct") or 1.0)

    full_term = _fd_years(start, maturity)
    elapsed = min(_fd_years(start, as_of), full_term) if start else 0.0
    matured = bool(maturity and as_of >= maturity)

    maturity_value = round(_fd_value(principal, rate, comp, full_term, payout), 2)
    if matured:
        current_value = break_value = maturity_value
    else:
        current_value = round(_fd_value(principal, rate, comp, elapsed, payout), 2)
        # Premature withdrawal: interest accrues at a reduced (penalised) rate for the elapsed time.
        break_value = round(_fd_value(principal, max(0.0, rate - penalty), comp, elapsed, payout), 2)
    return {
        "principal_amount": round(principal, 2),
        "current_value": current_value,
        "maturity_value": maturity_value,
        "break_value": break_value,                              # net cash if broken today
        "break_cost": round(max(0.0, current_value - break_value), 2),  # interest given up to break
        "matured": matured,
        "days_to_maturity": (maturity - as_of).days if maturity else None,
        "full_term_years": round(full_term, 2),
    }


def _fetch_fixed_deposits(user_id: str) -> List[Dict[str, Any]]:
    """Active FDs for the user with their computed current / maturity / break values."""
    rows: List[Dict] = []
    try:
        if supabase_db:
            resp = (supabase_db.table("fixed_deposits").select("*")
                    .eq("user_id", user_id).eq("is_active", True).execute())
            rows = resp.data or []
    except Exception as exc:
        logger.warning("[goal_planner] FD fetch error: %s", exc)
    out = []
    for r in rows:
        m = _fd_metrics(r)
        out.append({
            "fd_id": r.get("fd_id"),
            "bank_name": r.get("bank_name"),
            "label": r.get("label"),
            "interest_rate_pct": r.get("interest_rate_pct"),
            "maturity_date": r.get("maturity_date"),
            **m,
        })
    return out


def _fd_matches(fd: Dict[str, Any], idx: int, identifiers: List[str]) -> bool:
    """True if this FD matches ANY user-supplied identifier (fd_id, bank/label substring,
    or 1-based index). Used to resolve list-style funding selections like 'break only my SBI FD'."""
    hay = " ".join(str(fd.get(k) or "") for k in ("bank_name", "label", "fd_id")).lower()
    for ident in identifiers:
        token = str(ident).strip().lower()
        if not token:
            continue
        if token == str(fd.get("fd_id") or "").lower():
            return True
        if token.isdigit() and int(token) == idx:        # 1-based positional reference
            return True
        if token in hay or hay and any(w in hay for w in token.split() if len(w) > 2):
            return True
    return False


def _fd_funding_view(fds: List[Dict[str, Any]], goal_end_date: Optional[date],
                     selection: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Per-FD funding view evaluated AT THE GOAL'S TIMELINE END, plus whether it is selected for
    funding under the current `funding_selection`.

    Valuation rule (spec):
      • FD matures on/before the goal end-date → usable at its FULL maturity value, no penalty
        (it has simply become cash by the time the goal lands).
      • FD matures AFTER the goal end-date → to use it you must break it early → usable at the
        penalised break value, forfeiting `penalty_if_broken` of interest.

    Selection rule (drives what-if): matured-by-end FDs need no breaking, so they are always
    counted. A still-locked FD counts only when it would be broken:
      "auto" (default) / "all" → break it;  "none" / "matured_only" → leave it;
      list of identifiers → break only the FDs that match (bank/label/fd_id/index).
    """
    break_fds = selection.get("break_fds", "auto")
    identifiers = break_fds if isinstance(break_fds, list) else []
    out: List[Dict[str, Any]] = []
    for idx, fd in enumerate(fds, start=1):
        maturity = _parse_date(fd.get("maturity_date"))
        matures_by_end = bool(fd.get("matured")) or bool(
            maturity and goal_end_date and maturity <= goal_end_date
        )
        if matures_by_end:
            usable = round(float(fd.get("maturity_value") or 0.0), 2)
            penalty = 0.0
            selected = True
        else:
            usable = round(float(fd.get("break_value") or 0.0), 2)
            penalty = round(float(fd.get("break_cost") or 0.0), 2)
            if identifiers:
                selected = _fd_matches(fd, idx, identifiers)
            else:
                selected = break_fds in ("auto", "all")
        out.append({
            **fd,
            "matures_by_goal_end": matures_by_end,
            "usable_value": usable,
            "penalty_if_broken": penalty,
            "selected": selected,
        })
    return out


def _resolve_funding_selection(goal: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the effective funding selection that drives _deployable / _funding_sources.

    Precedence: defaults → text-fallback parsing of the goal/sub-question (generalises the old
    `deploy_all` keyword detection) → the brain's EXPLICIT `goal.funding_selection` (wins).
    The brain is the primary path; the text fallback only fills gaps when the brain omits a field.
    """
    sel: Dict[str, Any] = {
        "bank_use_pct": round((1.0 - _BANK_RETAIN_FRAC) * 100.0, 1),   # keep 10% by default
        "bank_use_amount": None,
        "use_liquid_funds": True,
        "break_fds": "auto",
    }

    txt = " ".join(str(goal.get(k) or "") for k in
                   ("funding", "financing_preference", "loan_preference", "description")).lower()
    txt += " " + str(task.get("sub_question") or "").lower()

    # "use everything / all my money" → deploy 100% of bank cash and break every FD.
    if "everything" in txt or ("all" in txt and any(w in txt for w in ("money", "fund", "saving", "cash"))):
        sel["bank_use_pct"] = 100.0
        sel["break_fds"] = "all"
    # "don't break / without breaking / keep my FDs" → never break (matured-by-end still usable).
    if re.search(r"(don'?t|do not|without|never|no need to|keep|leave)\s+\w*\s*break", txt) \
            or "without breaking" in txt or ("keep" in txt and ("fd" in txt or "deposit" in txt)):
        sel["break_fds"] = "none"
    elif "break" in txt and ("fd" in txt or "deposit" in txt):
        only_m = re.search(r"break\s+(?:only\s+)?(?:my\s+|the\s+|a\s+)?([a-z][a-z ]*?)\s*(?:fd|fixed deposit)", txt)
        name = (only_m.group(1).strip() if only_m else "")
        for filler in ("my ", "the ", "a ", "only "):
            name = name.replace(filler, "")
        if "only" in txt and name and name not in ("my", "the", "a"):
            sel["break_fds"] = [name]
        else:
            sel["break_fds"] = "all"
    # Bank cash fraction: "half my bank cash" / "use 50% of my savings".
    if re.search(r"half\s+(?:of\s+)?(?:my\s+|the\s+)?(?:bank|saving|cash|balance)", txt):
        sel["bank_use_pct"] = 50.0
    pct_m = re.search(r"(\d{1,3})\s*%\s*(?:of\s+)?(?:my\s+|the\s+)?(?:bank|saving|cash|balance)", txt)
    if pct_m:
        sel["bank_use_pct"] = float(pct_m.group(1))

    # Brain's explicit structured selection wins over the text fallback.
    raw = goal.get("funding_selection")
    if isinstance(raw, dict):
        for k in ("bank_use_pct", "bank_use_amount", "use_liquid_funds", "break_fds"):
            if raw.get(k) is not None:
                sel[k] = raw[k]

    if sel["break_fds"] == "matured_only":          # alias — only matured-by-end FDs, never break
        sel["break_fds"] = "none"
    return sel


# Mutual-fund name tokens that indicate a readily-redeemable (near-cash) holding.
_LIQUID_INV_KW = ("liquid", "debt", "fd", "fixed deposit", "savings", "money market",
                  "overnight", "ultra short", "short term", "arbitrage")


def _liquid_fund_current_value(inv_data: Optional[Dict]) -> float:
    """Current market value of liquid/debt holdings (near-cash). Uses each holding's
    `current_value`, which the caller fills from LIVE NAV (see _fetch_investment_holdings)."""
    holdings = (inv_data or {}).get("holdings") or []
    return round(sum(float(h.get("current_value") or 0) for h in holdings
                     if any(kw in (h.get("name") or "").lower() for kw in _LIQUID_INV_KW)), 2)


def _liquid_fund_value_at(inv_data: Optional[Dict], months: float,
                          annual_return_pct: Optional[float] = None) -> float:
    """Liquid-fund value at the goal horizon: current value grown at a debt-fund return for goals
    longer than _RETURN_MIN_MONTHS; kept flat (liquid) for short goals."""
    if annual_return_pct is None:
        annual_return_pct = _SAVINGS_RETURN_PCT
    current = _liquid_fund_current_value(inv_data)
    if current <= 0 or months <= _RETURN_MIN_MONTHS or annual_return_pct <= 0:
        return current
    return round(_corpus_growth(current, 0.0, annual_return_pct / 100.0, int(round(months))), 2)


# Back-compat alias: existing callers expect the goal-horizon value via `_liquid_fund_value`.
def _liquid_fund_value(inv_data: Optional[Dict], months: float = 0.0) -> float:
    return _liquid_fund_value_at(inv_data, months) if months else _liquid_fund_current_value(inv_data)


# ── Evidence extraction helpers ───────────────────────────────────────────────

def _extract_spending_categories(evidence: List[Dict]) -> List[Dict]:
    """Pull category breakdown from nl2sql evidence."""
    for e in evidence:
        if e.get("tool") != "nl2sql":
            continue
        analytics = (e.get("data") or {}).get("analytics") or {}
        bd = analytics.get("category_breakdown")
        if not bd:
            continue
        if isinstance(bd, list):
            return [{"category": str(k), "amount": float(v)} for k, v in bd[:10]]
        if isinstance(bd, dict):
            return [{"category": str(k), "amount": float(v)} for k, v in list(bd.items())[:10]]
    return []


def _extract_investment_data(evidence: List[Dict]) -> Optional[Dict]:
    for e in evidence:
        if e.get("tool") == "investment":
            return e.get("data") or {}
    return None


_REDUCIBLE_KEYWORDS = {
    "dining": 30, "restaurant": 30, "food": 20, "cafe": 40, "coffee": 40,
    "bar": 50, "alcohol": 50, "liquor": 50,
    "entertainment": 40, "movie": 40, "gaming": 40,
    "shopping": 30, "clothing": 30, "fashion": 30, "apparel": 30,
    "subscription": 35, "streaming": 35, "ott": 35,
    "cab": 25, "taxi": 25, "ride": 25, "uber": 25, "ola": 25,
    "delivery": 40, "swiggy": 40, "zomato": 40,
    "beauty": 30, "salon": 30, "spa": 40, "personal care": 25,
    "gifts": 25, "miscellaneous": 20, "misc": 20,
}

# Categories that are income or essential/fixed — never suggest "cutting" these.
_NON_REDUCIBLE = ("income", "salary", "rent", "emi", "loan", "insurance", "investment",
                  "tax", "utilities", "education", "medical", "health", "savings")

def _spending_reduction_opportunities(categories: List[Dict]) -> List[Dict]:
    """Identify reducible categories with sub-category justification + potential monthly saving."""
    result = []
    for cat in categories:
        name = (cat.get("category") or "").lower()
        amount = float(cat.get("amount") or 0)
        if amount <= 500:
            continue
        if any(nr in name for nr in _NON_REDUCIBLE):
            continue
        # Match on the main category OR any of its sub-categories.
        subs = cat.get("subcategories") or []
        haystack = name + " " + " ".join((s.get("name") or "").lower() for s in subs)
        # Score ALL keyword matches and pick the HIGHEST reduction — never first-match-wins
        # (dict order must not silently determine the recommendation).
        matches = [(kw, pct) for kw, pct in _REDUCIBLE_KEYWORDS.items() if kw in haystack]
        if not matches:
            continue
        best_kw, best_pct = max(matches, key=lambda kp: kp[1])
        result.append({
            "category": cat["category"],
            "current_monthly": round(amount, 2),
            "suggested_reduction_pct": best_pct,
            "matched_keyword": best_kw,
            "potential_saving": round(amount * best_pct / 100, 2),
            # sub-category detail so the answer can JUSTIFY the cut
            "driven_by": [{"name": s.get("name"), "amount": s.get("amount")} for s in subs[:3]],
        })
    result.sort(key=lambda x: x["potential_saving"], reverse=True)
    return result[:4]


def _check_investment_liquidity(gap: float, inv_data: Dict) -> Dict:
    total_current = float(inv_data.get("total_current") or 0)
    holdings = inv_data.get("holdings") or []
    liquid_h = [h for h in holdings
                if any(kw in (h.get("name") or "").lower() for kw in _LIQUID_INV_KW)]
    liquid_val = round(sum(float(h.get("current_value") or 0) for h in liquid_h), 2)
    if liquid_val == 0 and total_current > 0:
        liquid_val = round(total_current * 0.15, 2)  # conservative estimate

    if gap <= 0:
        note = "Goal is already funded — no liquidation needed."
    elif liquid_val >= gap:
        note = f"₹{liquid_val:,.0f} in liquid investments can fully fund the gap — no monthly savings needed if you choose to use them."
    elif liquid_val > 0:
        months_saved = round(liquid_val / max(gap / 12, 1), 1)
        note = f"₹{liquid_val:,.0f} in liquid investments can reduce your saving period by ~{months_saved} months."
    else:
        note = "Portfolio is primarily equity — avoid liquidating for short-term goals; keep invested."

    basis = inv_data.get("valuation_basis") or "current_nav"
    if basis == "purchase_cost":
        note += (" Note: portfolio values are estimated from purchase cost (not live NAV), so the "
                 "actual liquidatable value may differ.")
    return {
        "total_portfolio_value": round(total_current, 2),
        "estimated_liquid_value": liquid_val,
        "gap": round(gap, 2),
        "can_fully_cover": liquid_val >= gap > 0,
        "valuation_basis": basis,
        "recommendation": note,
    }


# ── Direct DB fallbacks ───────────────────────────────────────────────────────

def _compute_monthly_aggregates(user_id: str) -> Dict[str, float]:
    monthly: Dict[str, Dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    try:
        if supabase_db:
            resp = (supabase_db.table("transactions")
                    .select("amount, transaction_type, transaction_date")
                    .eq("user_id", user_id).execute())
            for tx in resp.data or []:
                ttype = (tx.get("transaction_type") or "").lower()
                amount = abs(float(tx.get("amount") or 0.0))
                date_str = tx.get("transaction_date") or ""
                month = date_str[:7] if len(date_str) >= 7 else ""
                if not month or ttype not in ("income", "expense"):
                    continue
                monthly[month][ttype] += amount
    except Exception as exc:
        logger.error("[goal_planner] aggregate error: %s", exc)
    # Base everything on the user's RECENT behaviour — the last 6 months that have data reflect
    # current capacity far better than stale history. (e.g. don't ask someone to save more than
    # they have actually been saving lately.)
    recent_keys = sorted(monthly.keys())[-6:]
    n = max(len(recent_keys), 1)
    total_exp = sum(monthly[m]["expense"] for m in recent_keys)
    total_inc = sum(monthly[m]["income"] for m in recent_keys)
    monthly_income = round(total_inc / n, 2)

    # If there are no income transactions, fall back to the declared profile income so
    # the snapshot reflects a real number rather than ₹0.
    income_source = "transactions"
    if monthly_income <= 0:
        try:
            if supabase_db:
                pr = supabase_db.table("user_profiles").select("income").eq("user_id", user_id).execute()
                if pr.data:
                    monthly_income = round(float(pr.data[0].get("income") or 0), 2)
                    income_source = "profile" if monthly_income > 0 else "unknown"
        except Exception as exc:
            logger.warning("[goal_planner] profile income fallback failed: %s", exc)

    monthly_spend = round(total_exp / n, 2)
    net_flow = round(monthly_income - monthly_spend, 2)
    return {
        "months_observed": len(recent_keys),
        "months_analyzed": len(recent_keys),
        "monthly_avg_spend": monthly_spend,
        "monthly_avg_income": monthly_income,
        "monthly_net_flow": net_flow,
        # How much of income the user actually keeps, and the realistic slice of that surplus we
        # may ask them to commit to a goal (NOT all of it — see _CAP_UTIL).
        "savings_rate_pct": round(net_flow / monthly_income * 100, 1) if monthly_income > 0 else 0.0,
        "monthly_savings_capacity": round(max(0.0, net_flow) * _CAP_UTIL, 2),
        "income_source": income_source,
    }


# Account-type substrings that are NOT deployable cash (locked / long-term instruments).
_NON_LIQUID_TYPES = ("epf", "ppf", "fixed", "fd", "deposit", "nps", "locked",
                     "retirement", "gratuity", "sukanya", "bond", "ulip")
# Account-type substrings that ARE liquid spendable cash.
_LIQUID_TYPES = ("saving", "current", "cash", "checking", "wallet", "bank")


def _classify_balances(rows: List[Dict]) -> Dict[str, Any]:
    """
    Split account rows into liquid (spendable), credit (liability), and illiquid (locked) buckets.
    - Credit-card balances are LIABILITIES, never a funding source.
    - EPF/PPF/FD/NPS etc. are locked and NOT deployable cash.
    - Negative balances never reduce the liquid total (clamped to 0).
    """
    liquid = 0.0
    liquid_accounts: List[Dict] = []
    credit_accounts: List[Dict] = []
    illiquid_accounts: List[Dict] = []
    for r in (rows or []):
        atype = (r.get("account_type") or "").lower()
        bal = float(r.get("current_balance") or 0)
        if "credit" in atype:
            credit_accounts.append({"name": r.get("account_name"), "outstanding": round(bal, 2)})
        elif any(t in atype for t in _NON_LIQUID_TYPES):
            illiquid_accounts.append({"name": r.get("account_name"), "type": atype,
                                      "balance": round(max(0.0, bal), 2)})
        elif atype == "" or any(t in atype for t in _LIQUID_TYPES):
            b = max(0.0, bal)         # a negative balance must not reduce deployable cash
            liquid += b
            if b > 0:                 # keep the per-account detail so we can name WHICH bank to use
                liquid_accounts.append({"name": r.get("account_name") or "Bank account",
                                        "type": atype or "savings", "balance": round(b, 2)})
        else:
            # Unknown type: be conservative and treat as illiquid rather than spendable.
            illiquid_accounts.append({"name": r.get("account_name"), "type": atype,
                                      "balance": round(max(0.0, bal), 2)})
    liquid_accounts.sort(key=lambda a: a["balance"], reverse=True)
    return {
        "liquid_balance": round(liquid, 2),
        "liquid_accounts": liquid_accounts,
        "credit_accounts": credit_accounts,
        "illiquid_accounts": illiquid_accounts,
    }


def _get_account_balances(user_id: str) -> Dict[str, Any]:
    """Fetch account rows from Supabase and classify them (liquid / credit / illiquid)."""
    rows: List[Dict] = []
    try:
        if supabase_db:
            resp = (supabase_db.table("accounts")
                    .select("account_name, account_type, current_balance")
                    .eq("user_id", user_id).execute())
            rows = resp.data or []
    except Exception as exc:
        logger.warning("[goal_planner] balance fetch error: %s", exc)
    return _classify_balances(rows)


def _compute_category_breakdown(user_id: str, months_observed: int) -> List[Dict]:
    """
    Monthly-average expense by main category, each with its top sub-categories, straight
    from Supabase (no nl2sql). Sub-categories let the planner justify WHY a cut is suggested.
    """
    cats: Dict[str, float] = defaultdict(float)
    subs: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    rows: List[Dict] = []
    try:
        if supabase_db:
            resp = (supabase_db.table("transactions")
                    .select("amount, transaction_type, transaction_date, merchant_name, categories(main_category, sub_category)")
                    .eq("user_id", user_id).execute())
            rows = resp.data or []
    except Exception as exc:
        logger.warning("[goal_planner] category breakdown error: %s", exc)
    # Same recent window as the aggregates (last 6 months with data) so category averages line up
    # with the monthly spend the surplus is computed from.
    recent = set(sorted({(t.get("transaction_date") or "")[:7] for t in rows
                          if (t.get("transaction_date") or "")})[-6:])
    for tx in rows:
        if (tx.get("transaction_type") or "").lower() != "expense":
            continue
        month = (tx.get("transaction_date") or "")[:7]
        if recent and month not in recent:
            continue
        amount = abs(float(tx.get("amount") or 0))
        cat_obj = tx.get("categories") or {}
        main = cat_obj.get("main_category") or "Others"
        sub = cat_obj.get("sub_category") or tx.get("merchant_name") or "Other"
        cats[main] += amount
        subs[main][sub] += amount
    n = max(len(recent) or months_observed, 1)
    items = sorted(cats.items(), key=lambda x: x[1], reverse=True)
    out = []
    for main, total in items[:10]:
        top_subs = sorted(subs[main].items(), key=lambda x: x[1], reverse=True)[:3]
        out.append({
            "category": main,
            "amount": round(total / n, 2),
            "subcategories": [{"name": s, "amount": round(v / n, 2)} for s, v in top_subs],
        })
    return out


def _fetch_investment_holdings(user_id: str, live_nav: bool = False) -> Optional[Dict]:
    """Portfolio snapshot.

    By DEFAULT values holdings at PURCHASE NAV — a pure DB read, no network — so hot paths like
    the dashboard summary and financial-health-insights endpoints stay fast. Pass `live_nav=True`
    (the goal planner) to value liquid/debt holdings at their true LIVE market NAV via mfapi
    (per-scheme network calls, ~seconds), falling back to purchase NAV per holding on failure.
    """
    fetch_hist = latest = None
    if live_nav:
        from app.graph.tools.investment_tool import _fetch_scheme_history, _latest_nav
        fetch_hist, latest = _fetch_scheme_history, _latest_nav
    try:
        if not supabase_db:
            return None
        cols = "scheme_name, scheme_code, quantity, purchase_nav" if live_nav else "scheme_name, quantity, purchase_nav"
        resp = supabase_db.table("investments").select(cols).eq("user_id", user_id).execute()
        rows = resp.data or []
        if not rows:
            return None
        holdings, total = [], 0.0
        for r in rows:
            qty = float(r.get("quantity") or 0)
            nav = float(r.get("purchase_nav") or 0)
            if live_nav and r.get("scheme_code"):
                live = latest(fetch_hist(r.get("scheme_code")))
                if live and live > 0:
                    nav = live
            val = qty * nav
            total += val
            holdings.append({"name": r.get("scheme_name"), "current_value": round(val, 2)})
        for h in holdings:
            h["share_pct"] = round(h["current_value"] / total * 100, 2) if total > 0 else 0.0
        return {"total_current": round(total, 2), "holdings": holdings,
                "valuation_basis": "live_nav" if live_nav else "purchase_cost"}
    except Exception as exc:
        logger.warning("[goal_planner] investment fetch error: %s", exc)
    return None


# ── Scenario builder helpers ──────────────────────────────────────────────────

def _sc(tag: str, label: str, recommended: bool,
        monthly_savings_needed: float, net_flow: float, **extra) -> Dict:
    """Build a standard scenario dict."""
    ms = round(monthly_savings_needed, 2)
    safe = net_flow * _CAP_UTIL   # only ~70% of surplus may be committed — keep a lifestyle cushion
    return {
        "tag": tag,
        "label": label,
        "recommended": recommended,
        "monthly_savings_needed": ms,
        "feasible": safe >= ms if net_flow > 0 else False,
        "shortfall_per_month": round(max(0.0, ms - safe), 2),
        **extra,
    }


def _inv_emi(emi_budget: float, annual_rate_pct: float, tenure_months: int) -> float:
    """Largest loan principal whose EMI fits within emi_budget (inverse of _calc_emi)."""
    if emi_budget <= 0 or tenure_months <= 0:
        return 0.0
    r = (annual_rate_pct / 100.0) / 12.0
    if r == 0:
        return emi_budget * tenure_months
    return emi_budget * ((1 + r) ** tenure_months - 1) / (r * (1 + r) ** tenure_months)


_CAP_UTIL = 0.70   # only ask the user to commit ~70% of their realistic monthly surplus to a goal,
                   # never all of it — a lifestyle cushion stays untouched (realistic affordability)
_BANK_RETAIN_FRAC = 0.10   # by default keep 10% of idle bank cash untouched; the other 90% is
                           # deployable toward the goal (the user may override to use 100%).
_SAVINGS_RETURN_PCT = 7.0   # expected p.a. return for cash goals >12 months (debt/hybrid MF)
_RETURN_MIN_MONTHS = 12     # only assume growth for goals longer than this
_TARGET_FLOOR_FRAC = 0.5   # if a goal can only be financed below this fraction of what the user
                           # asked, it's "out of reach" — not merely right-sizable.
_EDU_MIN_SELF_FRAC = 0.05  # education is financed loan-first; self-fund at most this small slice
                           # upfront (capped by available cash) so the loan covers ~95-100%.


def _max_stretch_months(user_months: int) -> int:
    """How far we'll EVER stretch a timeline: at most ~50% beyond what the user asked
    (so 15 months → ~23, never doubling). For very short goals, allow a small additive."""
    return min(max(user_months + 3, math.ceil(user_months * 1.5)), 360)


def _funding_components(agg: dict) -> tuple:
    """(bank_surplus, near_cash, fd_value) deployable under the resolved `funding_selection`."""
    sel = agg.get("funding_selection") or {}
    liquid = agg.get("total_current_balance") or 0.0
    # Keep 10% of idle bank cash by default (bank_use_pct = 90); the user may override to 100%.
    pct = float(sel.get("bank_use_pct", (1.0 - _BANK_RETAIN_FRAC) * 100.0))
    bank_surplus = max(0.0, liquid * pct / 100.0)
    cap = sel.get("bank_use_amount")
    if cap is not None:
        bank_surplus = min(bank_surplus, max(0.0, float(cap)))
    near_cash = (agg.get("liquid_fund_value") or 0.0) if sel.get("use_liquid_funds", True) else 0.0
    # FDs contribute their usable value AT THE GOAL END only when selected (matured-by-end FDs are
    # always selected; still-locked FDs only if the selection says to break them).
    fd_value = sum(f.get("usable_value") or 0.0
                   for f in (agg.get("fd_funding_view") or []) if f.get("selected"))
    return round(bank_surplus, 2), round(near_cash, 2), round(fd_value, 2)


def _deployable(agg: dict) -> float:
    """
    Funds that can genuinely seed a goal, drawn from THREE sources (see `_funding_sources`):
      1. idle bank cash, keeping 10% in the account by default (overridable per what-if);
      2. liquid / debt mutual funds (redeemable in ~1 day) — near-cash;
      3. fixed deposits, valued AT THE GOAL'S TIMELINE END — at full maturity value if they
         mature by then, otherwise at their net break value (premature-withdrawal penalty).
    The scenario builders only ever draw the amount a goal actually needs (lump = min(need, avail)),
    so surfacing the full pool here lets FDs + liquid funds influence EVERY goal without forcing
    their use on goals that don't need them.
    """
    bank_surplus, near_cash, fd_value = _funding_components(agg)
    return round(bank_surplus + near_cash + fd_value, 2)


def _funding_sources(agg: dict) -> Dict[str, Any]:
    """
    Breakdown of EVERY asset and whether it can seed the goal — so the answer is transparent about
    what is used AND justifies what is NOT (e.g. equity kept invested, no liquid funds on record).
    FD entries distinguish ones that MATURE by the goal date (usable in full, no penalty) from ones
    that must be BROKEN early (penalty), and respect the user's funding selection.
    """
    sel = agg.get("funding_selection") or {}
    bank_surplus, near_cash, fd_value = _funding_components(agg)
    portfolio = round(agg.get("portfolio_value") or 0.0, 2)
    equity_other = round(max(0.0, portfolio - (agg.get("liquid_fund_value") or 0.0)), 2)  # kept invested

    # Name the exact bank accounts that hold the idle cash (largest first) so the answer can say
    # precisely which account to draw from.
    bank_accounts = [{"name": a.get("name"), "balance": round(float(a.get("balance") or 0), 2)}
                     for a in (agg.get("liquid_accounts") or []) if (a.get("balance") or 0) > 0]
    bank_pct = float(sel.get("bank_use_pct", (1.0 - _BANK_RETAIN_FRAC) * 100.0))
    keep_pct = max(0.0, round(100.0 - bank_pct, 1))
    buffer_note = ("using your FULL balance, nothing kept aside (as you asked)"
                   if bank_pct >= 100.0 else f"keeping {keep_pct:.0f}% in your accounts")
    reasons: List[str] = []
    if bank_surplus > 0:
        named_banks = ", ".join(f"{a['name']} ({_inr(a['balance'])})" for a in bank_accounts) or "your bank account"
        reasons.append(f"Bank savings: {_inr(bank_surplus)} can be set aside now ({buffer_note}) from {named_banks}.")
    else:
        reasons.append("Bank savings: nothing applied (after keeping your chosen cash cushion).")
    if not sel.get("use_liquid_funds", True):
        reasons.append("Liquid/debt funds: left untouched as you asked.")
    else:
        reasons.append(
            f"Liquid/debt funds: {_inr(near_cash)} available (near-cash, used first)."
            if near_cash > 0 else
            "Liquid/debt funds: none on record, so none used."
        )

    view = agg.get("fd_funding_view") or []
    matured_used = [f for f in view if f.get("selected") and f.get("matures_by_goal_end")]
    broken_used  = [f for f in view if f.get("selected") and not f.get("matures_by_goal_end")]
    kept_locked  = [f for f in view if not f.get("selected")]

    def _fd_name(f):
        return (f.get("bank_name") or f.get("label") or "FD")
    if matured_used:
        named = "; ".join(f"{_fd_name(f)} FD ({_inr(f.get('usable_value'))} at maturity)" for f in matured_used)
        reasons.append(f"Fixed deposits maturing by your goal date — usable in full, no penalty: {named}.")
    if broken_used:
        named = "; ".join(
            f"{_fd_name(f)} FD ({_inr(f.get('usable_value'))} if broken now, forfeiting {_inr(f.get('penalty_if_broken'))})"
            for f in broken_used
        )
        reasons.append(f"Fixed deposits broken early (small interest penalty applies): {named}.")
    if kept_locked:
        named = "; ".join(f"{_fd_name(f)} FD" for f in kept_locked)
        reasons.append(f"Fixed deposits left intact (not matured by your goal date and not broken): {named}.")
    if not view:
        reasons.append("Fixed deposits: none on record.")
    if equity_other > 0:
        reasons.append(
            f"Equity / other investments: {_inr(equity_other)} is kept invested — liquidating growth "
            "assets for this goal isn't advisable, so it is NOT counted as funding."
        )
    return {
        "from_bank_savings": bank_surplus,
        "from_liquid_funds": near_cash,
        "from_fixed_deposits": fd_value,
        "deployable_total": round(bank_surplus + near_cash + fd_value, 2),
        "equity_or_other_not_counted": equity_other,
        "requires_breaking_fd": bool(broken_used),
        "bank_accounts": bank_accounts,                 # which accounts hold the idle cash
        "bank_use_pct": round(bank_pct, 1),
        "fixed_deposits": view,                          # per-FD funding view (named, with selection)
        "funding_selection": sel,                        # the resolved selection that produced this
        "explanation": reasons,
    }


def _max_sustainable_save(agg: dict) -> float:
    """Most the user can be asked to save per month: current surplus + reclaimable category cuts.
    The saving phase may use this in full; the permanent EMI is capped at 70% of it (see _loan_scenarios)."""
    return round(max(0.0, agg.get("monthly_net_flow", 0.0))
                 + max(0.0, agg.get("total_spending_cuts", 0.0)), 2)


def _minimal_deployment(gap: float, agg: dict, include_bank: bool = True) -> dict:
    """Cover `gap` with the LEAST-disruptive assets, in order:
       1. FDs maturing by the goal date  (free — already becoming cash),
       2. liquid/debt funds              (partial redemption to the EXACT amount needed),
       3. bank cash                      (only when include_bank — keeping the chosen cushion),
       4. a still-locked FD broken ONLY if still short — the one whose usable value is CLOSEST
          to the remaining need (minimise forfeited interest; never break everything).

    Set include_bank=False for the LIQUIDITY scenarios (C/D), where bank cash is already counted
    as 'available cash' and only FDs / liquid funds are 'broken'.
    """
    gap = max(0.0, round(gap, 2))
    used = {"from_fds_matured": 0.0, "from_liquid": 0.0, "from_bank": 0.0,
            "from_fds_broken": 0.0, "fds_broken": [], "penalty_paid": 0.0}
    remaining = gap
    view = agg.get("fd_funding_view") or []

    for fd in view:                                   # 1. matured-by-goal-end FDs (free)
        if remaining <= 0:
            break
        if fd.get("matures_by_goal_end"):
            take = min(remaining, float(fd.get("usable_value") or 0.0))
            used["from_fds_matured"] += take
            remaining -= take

    if remaining > 0:                                 # 2. liquid/debt funds (exact partial)
        take = min(remaining, float(agg.get("liquid_fund_value") or 0.0))
        used["from_liquid"] += take
        remaining -= take

    if include_bank and remaining > 0:                # 3. bank cash (keep cushion)
        sel = agg.get("funding_selection") or {}
        pct = float(sel.get("bank_use_pct", (1.0 - _BANK_RETAIN_FRAC) * 100.0))
        bank_avail = max(0.0, float(agg.get("total_current_balance") or 0.0) * pct / 100.0)
        take = min(remaining, bank_avail)
        used["from_bank"] += take
        remaining -= take

    if remaining > 0:                                 # 4. break the FD closest to the remaining need
        locked = [fd for fd in view if not fd.get("matures_by_goal_end")]
        locked.sort(key=lambda fd: abs(float(fd.get("usable_value") or 0.0) - remaining))
        for fd in locked:
            if remaining <= 0:
                break
            take = min(remaining, float(fd.get("usable_value") or 0.0))
            if take <= 0:
                continue
            used["from_fds_broken"] += take
            used["penalty_paid"] += float(fd.get("penalty_if_broken") or 0.0)
            used["fds_broken"].append(fd.get("bank_name") or fd.get("label") or "FD")
            remaining -= take

    for k in ("from_fds_matured", "from_liquid", "from_bank", "from_fds_broken", "penalty_paid"):
        used[k] = round(used[k], 2)
    used["deployed_total"] = round(gap - remaining, 2)
    used["shortfall_uncovered"] = round(max(0.0, remaining), 2)
    return used


def _loan_scenarios(*, price: float, existing: float, user_months: float, user_dp_pct: float,
                    surplus: float, cuts: float, rate: float, tenure: int,
                    agg: dict,
                    extra_upfront: float = 0.0, down_label: str = "down payment",
                    asset: str = "purchase",
                    instrument: str = "Recurring Deposit or Liquid MF") -> tuple:
    """
    FOUR orthogonal scenarios. Bank cash (+ any earmarked existing savings) is 'available cash' in
    EVERY scenario; only FDs / liquid FUNDS are ever 'broken' (scenarios C/D).

      A — Baseline. Current saving rate, no cuts, no breaking. The user's exact down payment %.
          Feasible if the down payment is reachable from cash + saving×timeline AND the EMI fits
          70% of current saving.
      B — Spending cuts. Same as A but saving = surplus + reclaimable category cuts; the bank grows
          faster and the EMI is judged against 70% of that higher saving. (Cut breakdown attached.)
      C — Liquidity (no cuts). Break MINIMAL least-disruptive FDs/funds to RAISE the down payment →
          shrink the loan → bring the EMI within 70% of current saving.
      D — Everything. Cuts AND liquidity; liquidity raises the down payment and may also be reserved
          to PRE-FUND the EMI shortfall the saving can't cover. The 'throw everything at it' plan.

    Recommended = the first FEASIBLE scenario in order A→B→C→D; all four are always returned.
    """
    price = max(price, 0.0)
    months = max(1, int(round(user_months)))
    save = max(0.0, surplus)
    cuts = max(0.0, cuts)
    updated_save = save + cuts
    bank = max(0.0, float(agg.get("total_current_balance") or 0.0))
    available_now = bank + max(0.0, existing)          # cash on hand (bank + earmarked savings)
    user_dp_pct = min(max(user_dp_pct, 0.0), 100.0)
    zero_deploy = _minimal_deployment(0.0, agg)
    cuts_note = f" (with ₹{round(cuts):,}/mo spending cuts)" if cuts > 0 else ""

    def build(tag, label, *, dp_pct, capacity, deployment, emi_reserve_monthly=0.0):
        """One scenario. `capacity` = the monthly saving this scenario assumes (A/C: save; B/D:
        updated_save). `deployment` = FD/liquid funds broken (C/D). `emi_reserve_monthly` = part of
        the EMI pre-funded from liquidity (D)."""
        dp_pct = min(max(dp_pct, 0.0), 100.0)
        dp_amt = round(price * dp_pct / 100.0, 2)
        loan = round(max(0.0, price - dp_amt), 2)
        emi = round(_calc_emi(loan, rate, tenure), 2) if loan > 0 else 0.0
        interest = round(emi * tenure - loan, 2) if loan > 0 else 0.0
        upfront = dp_amt + extra_upfront
        deployed = deployment["deployed_total"]
        cash_now = available_now + deployed                      # cash + broken funds available today
        to_save = round(max(0.0, upfront - cash_now), 2)         # the rest, saved monthly
        monthly_save = round(to_save / months, 2)
        # Down payment is reachable if cash + broken funds + saving×timeline covers the upfront.
        dp_feasible = upfront <= cash_now + capacity * months + 1
        # The EMI must fit 70% of this scenario's saving, after any pre-funded reserve.
        emi_self = max(0.0, emi - emi_reserve_monthly)
        emi_feasible = emi_self <= _CAP_UTIL * capacity + 1
        # Per-SOURCE split of the down payment (so the answer/card can name where each rupee comes
        # from). `deployed` is FD + liquid funds broken; the rest of the lump is bank cash.
        lump = round(min(upfront, cash_now), 2)
        dp_from_fd_amount = round(float(deployment.get("from_fds_matured") or 0)
                                  + float(deployment.get("from_fds_broken") or 0), 2)
        dp_from_liquid_amount = round(float(deployment.get("from_liquid") or 0), 2)
        dp_from_bank_amount = round(max(0.0, lump - dp_from_fd_amount - dp_from_liquid_amount), 2)
        return {
            "tag": tag, "label": label, "recommended": False,
            "purchase_price": round(price, 2),
            "down_payment_pct": round(dp_pct, 1),
            "down_payment_amount": dp_amt,
            "down_payment_from_existing": lump,
            "down_payment_from_savings": to_save,
            "dp_from_bank_amount": dp_from_bank_amount,
            "dp_from_fd_amount": dp_from_fd_amount,
            "dp_from_liquid_amount": dp_from_liquid_amount,
            "dp_from_savings_amount": to_save,
            "loan_amount": loan,
            "loan_tenure_months": tenure if loan > 0 else 0,
            "loan_rate_pct": round(rate, 2),
            "estimated_emi": emi,
            "monthly_post_purchase": emi,
            "emi_pre_funded_monthly": round(emi_reserve_monthly, 2),
            "total_interest_paid": interest,
            "total_cost_of_ownership": round(price + interest + extra_upfront, 2),
            "timeline_months": months,
            "monthly_savings_needed": monthly_save,
            "assumed_monthly_saving": round(capacity, 2),
            # Bank-balance story (precomputed so the answer never does its own arithmetic):
            "available_balance_now": round(available_now, 2),
            "total_savings_pot": round(capacity * months, 2),
            "balance_after_upfront": round(available_now + deployed + capacity * months - upfront, 2),
            "deployment": deployment,
            "feasible": bool(dp_feasible and emi_feasible),
            "emi_fits_capacity": bool(emi_feasible),
            "down_payment_fundable": bool(dp_feasible),
            "shortfall_per_month": round(max(0.0, monthly_save - capacity), 2),
            "recommended_instrument": instrument,
        }

    # A — baseline: user's down payment %, current saving, no cuts, no breaking.
    sc_a = build("A", f"Baseline — {user_dp_pct:.0f}% {down_label} over {months} months on your current savings",
                 dp_pct=user_dp_pct, capacity=save, deployment=zero_deploy)

    # B — spending cuts: same plan, judged against the higher (surplus + cuts) saving.
    sc_b = build("B", f"With spending cuts — {user_dp_pct:.0f}% {down_label}, freeing ₹{round(cuts):,}/mo from your budget",
                 dp_pct=user_dp_pct, capacity=updated_save, deployment=zero_deploy)

    # C — liquidity (no cuts): raise the down payment with MINIMAL broken funds so the EMI fits
    #     70% of CURRENT saving — but NEVER beyond what the user can actually fund (bank + savings +
    #     all breakable liquidity). If the funds can't reach that down payment, C keeps the real
    #     (higher) loan/EMI and stays infeasible rather than inventing an unfundable down payment.
    user_dp_amt = round(price * user_dp_pct / 100.0, 2)
    max_loan_c = _inv_emi(_CAP_UTIL * save, rate, tenure)
    dp_needed_c = max(user_dp_amt, price - max_loan_c)                 # to bring EMI within 70% of saving
    liquidity_all = _minimal_deployment(price + extra_upfront, agg, include_bank=False)["deployed_total"]
    max_fundable_c = available_now + save * months + liquidity_all - extra_upfront
    dp_amt_c = min(price, max(user_dp_amt, min(dp_needed_c, max_fundable_c)))
    dp_pct_c = (dp_amt_c / price * 100.0) if price else user_dp_pct
    shortfall_c = max(0.0, dp_amt_c + extra_upfront - available_now - save * months)
    deploy_c = _minimal_deployment(shortfall_c, agg, include_bank=False)
    sc_c = build("C", f"Free up liquidity — break the minimum needed to make the EMI affordable",
                 dp_pct=dp_pct_c, capacity=save, deployment=deploy_c)

    # D — EVERYTHING: spending cuts AND break ALL useful liquidity to MAXIMISE the down payment
    #     (smallest loan, least interest); pre-fund any EMI the saving still can't cover. This is the
    #     all-in plan, so it deploys more than C's minimal break — distinguishing it from B and C.
    liquidity_all = _minimal_deployment(price + extra_upfront, agg, include_bank=False)["deployed_total"]
    # Throw bank cash + cuts-boosted savings + every breakable fund at the down payment (cap at price).
    dp_amt_d = min(price, max(round(price * user_dp_pct / 100.0, 2),
                              available_now + updated_save * months + liquidity_all - extra_upfront))
    dp_pct_d = (dp_amt_d / price * 100.0) if price else user_dp_pct
    loan_d = max(0.0, price - dp_amt_d)
    emi_d = _calc_emi(loan_d, rate, tenure) if loan_d > 0 else 0.0
    reserve_monthly_d = max(0.0, emi_d - _CAP_UTIL * updated_save)     # EMI the saving can't cover
    # Liquidity actually broken = the down-payment beyond bank + cuts-boosted savings, plus any reserve.
    shortfall_dp_d = max(0.0, dp_amt_d + extra_upfront - available_now - updated_save * months)
    deploy_d = _minimal_deployment(shortfall_dp_d + reserve_monthly_d * tenure, agg, include_bank=False)
    sc_d = build("D", f"Everything in — spending cuts + break funds for the biggest down payment / smallest loan{cuts_note}",
                 dp_pct=dp_pct_d, capacity=updated_save, deployment=deploy_d,
                 emi_reserve_monthly=reserve_monthly_d)

    scenarios = [sc_a, sc_b, sc_c, sc_d]
    feasible = next((s for s in scenarios if s["feasible"]), None)
    # Recommend the first feasible scenario (least disruptive). If none works, fall back to D (the
    # fullest effort) so there is always a headline plan; meta flags that it is not affordable.
    (feasible or sc_d)["recommended"] = True
    any_feasible = feasible is not None
    meta = {"target_out_of_reach": not any_feasible, "max_financeable_target": round(price, 2),
            "any_feasible": any_feasible}
    return scenarios, meta


def _savings_scenarios(*, target: float, existing: float, user_months: float,
                       surplus: float, cuts: float, instrument: str, agg: dict,
                       asset: str = "goal",
                       annual_return_pct: float = _SAVINGS_RETURN_PCT) -> tuple:
    """
    FOUR scenarios for a cash (no-loan) goal — the no-EMI counterpart of _loan_scenarios. Bank cash
    (+ earmarked existing savings) is 'available cash' in every scenario; only FDs / liquid FUNDS
    are broken (C/D). A goal is feasible when the chosen resources reach the target by the timeline.

      A — Baseline: bank cash + current saving × timeline.
      B — Spending cuts: bank cash + (saving + cuts) × timeline.
      C — Liquidity (no cuts): bank cash + current saving × timeline + minimal broken funds.
      D — Everything: bank cash + (saving + cuts) × timeline + broken funds.
    """
    surplus = max(surplus, 0.0)
    cuts = max(cuts, 0.0)
    months = max(1, int(round(user_months)))
    save = surplus
    updated_save = surplus + cuts
    bank = max(0.0, float(agg.get("total_current_balance") or 0.0))
    available_now = bank + max(0.0, existing)          # cash on hand
    r = annual_return_pct / 100.0
    grows = annual_return_pct > 0
    zero_deploy = _minimal_deployment(0.0, agg)

    def _reach(base, capacity):
        """Value reached by the goal date from `base` cash contributing `capacity`/month."""
        if months > _RETURN_MIN_MONTHS and grows:
            return _corpus_growth(base, capacity, r, months)
        return base + capacity * months

    def build(tag, label, *, capacity, deployment):
        deploy = deployment["deployed_total"]
        base = available_now + deploy
        reached = _reach(base, capacity)
        # Monthly contribution actually needed to hit the target from cash + broken funds.
        if months > _RETURN_MIN_MONTHS and grows:
            need = max(0.0, target - _corpus_growth(base, 0.0, r, months))
            monthly = round(_monthly_sip_for_corpus(need, annual_return_pct, months), 2)
        else:
            monthly = round(max(0.0, target - base) / months, 2)
        return {
            "tag": tag, "label": label, "recommended": False,
            "timeline_months": months,
            "monthly_savings_needed": monthly,
            "assumed_monthly_saving": round(capacity, 2),
            "target_amount": round(target, 2),
            "gap": round(max(0.0, target - available_now), 2),
            "available_balance_now": round(available_now, 2),
            "total_savings_pot": round(capacity * months, 2),
            "deployed_now": round(deploy, 2),
            "deployment": deployment,
            "assumed_annual_return_pct": annual_return_pct,
            "projected_value_at_goal": round(reached, 2),
            "feasible": bool(reached >= target - 1),
            "shortfall_per_month": round(max(0.0, monthly - capacity), 2),
            "recommended_instrument": instrument,
        }

    # A — baseline.
    sc_a = build("A", f"Baseline — {months} months on your current savings", capacity=save, deployment=zero_deploy)
    # B — spending cuts.
    sc_b = build("B", f"With spending cuts — freeing ₹{round(cuts):,}/mo from your budget", capacity=updated_save, deployment=zero_deploy)
    # C — liquidity (no cuts): break minimal funds for the gap current saving can't reach.
    gap_c = max(0.0, target - available_now - save * months)
    sc_c = build("C", "Free up liquidity — break the minimum needed to reach the target",
                 capacity=save, deployment=_minimal_deployment(gap_c, agg, include_bank=False))
    # D — everything: cuts + liquidity.
    gap_d = max(0.0, target - available_now - updated_save * months)
    sc_d = build("D", "Everything in — spending cuts + liquidity to reach the target",
                 capacity=updated_save, deployment=_minimal_deployment(gap_d, agg, include_bank=False))

    scenarios = [sc_a, sc_b, sc_c, sc_d]
    feasible = next((s for s in scenarios if s["feasible"]), None)
    (feasible or sc_d)["recommended"] = True
    any_feasible = feasible is not None
    meta = {"target_out_of_reach": not any_feasible, "max_financeable_target": round(target, 2),
            "any_feasible": any_feasible}
    return scenarios, meta


def _education_scenarios(*, cost: float, existing: float, user_months: float, self_pct: float,
                         surplus: float, cuts: float, agg: dict,
                         rate: float = 10.5, tenure: int = 180) -> tuple:
    """
    Education NEVER scales the program cost — a PhD/MS/MBA costs what it costs. Every scenario
    funds the FULL program; the only lever is the FINANCING STRUCTURE.

    Education loans finance up to 100% of the cost with a moratorium during study and repayment
    from HIGHER post-graduation income, so the program is ALWAYS financeable and the post-grad EMI
    is informational — NOT gated on today's saving. The four scenarios apply the A/B/C/D effort
    ladder to the SELF-FUNDED slice: the more you self-fund, the smaller the loan and the interest.

      A — Baseline: self-fund what bank cash + current saving allow; loan covers the rest.
      B — Spending cuts: self-fund more from (saving + cuts) → smaller loan.
      C — Liquidity (no cuts): break minimal FDs/funds to self-fund more → smaller loan.
      D — Everything: cuts + liquidity → most self-funding, smallest loan, least interest.
    """
    surplus = max(surplus, 0.0); cuts = max(cuts, 0.0); cost = max(cost, 0.0)
    months = max(1, int(round(user_months)))
    save = surplus
    updated_save = surplus + cuts
    bank = max(0.0, float(agg.get("total_current_balance") or 0.0))
    available_now = bank + max(0.0, existing)
    yrs = max(1, tenure // 12)
    zero_deploy = _minimal_deployment(0.0, agg)

    def make(tag, label, *, capacity, deployment):
        deploy = deployment["deployed_total"]
        cash_now = available_now + deploy
        # Self-fund the most these resources allow over the study period; loan covers the remainder.
        self_amt = min(cost, cash_now + capacity * months)
        loan_amt = round(max(0.0, cost - self_amt), 2)
        emi = round(_calc_emi(loan_amt, rate, tenure), 2) if loan_amt > 0 else 0.0
        lump = round(min(self_amt, cash_now), 2)
        to_save = round(max(0.0, self_amt - lump), 2)
        monthly = round(to_save / months, 2)
        interest = round(emi * tenure - loan_amt, 2) if loan_amt > 0 else 0.0
        return {
            "tag": tag, "label": label, "recommended": False,
            "purchase_price": round(cost, 2),                       # ALWAYS the full program cost
            "down_payment_pct": round(self_amt / cost * 100, 1) if cost else 0.0,
            "down_payment_amount": round(self_amt, 2),
            "down_payment_from_existing": lump,
            "down_payment_from_savings": to_save,
            "loan_amount": loan_amt,
            "loan_tenure_months": tenure if loan_amt > 0 else 0,
            "estimated_emi": emi, "monthly_post_purchase": emi,
            "post_graduation_emi": emi,   # repaid from higher post-degree income, NOT today's surplus
            "total_interest_paid": interest,
            "total_cost_of_ownership": round(cost + interest, 2),
            "timeline_months": months,
            "monthly_savings_needed": monthly,
            "assumed_monthly_saving": round(capacity, 2),
            "deployment": deployment,
            # The program is always financeable (loan covers any remainder); the self-funded slice
            # here is only ever what the resources actually allow.
            "feasible": True,
            "shortfall_per_month": 0.0,
            "recommended_instrument": "Education loan (tax benefit u/s 80E) + SIP for the self-funded slice",
        }

    sc_a = make("A", f"Baseline — self-fund from current savings over a {yrs}-year loan",
                capacity=save, deployment=zero_deploy)
    sc_b = make("B", f"With spending cuts — free up ₹{round(cuts):,}/mo to self-fund more, shrinking the loan",
                capacity=updated_save, deployment=zero_deploy)
    # C/D self-fund the remaining loan with broken funds (no cuts in C). Size the deployment to the
    # loan that baseline self-funding still leaves.
    loan_after_a = max(0.0, cost - (available_now + save * months))
    sc_c = make("C", "Free up liquidity — break the minimum needed to cut the loan further",
                capacity=save, deployment=_minimal_deployment(loan_after_a, agg, include_bank=False))
    loan_after_b = max(0.0, cost - (available_now + updated_save * months))
    sc_d = make("D", "Everything in — cuts + liquidity for the smallest possible loan",
                capacity=updated_save, deployment=_minimal_deployment(loan_after_b, agg, include_bank=False))

    scenarios = [sc_a, sc_b, sc_c, sc_d]
    scenarios[0]["recommended"] = True          # baseline is least-disruptive; all are feasible
    meta = {"max_financeable_target": round(cost, 2), "target_out_of_reach": False, "any_feasible": True}
    return scenarios, meta


# ── Type-specific planners ────────────────────────────────────────────────────

def _savings_goal(goal: dict, agg: dict, *, target: float, existing: float, months: float,
                  instrument: str, extra: dict, annual_return_pct: float = _SAVINGS_RETURN_PCT) -> dict:
    """
    Shared body for every cash (no-loan) goal. Runs `_savings_scenarios` (deploying spare assets)
    and merges the recommended scenario's headline numbers with the goal-specific `extra` fields.
    """
    scenarios, meta = _savings_scenarios(
        target=target, existing=existing, user_months=months,
        surplus=agg["monthly_net_flow"], cuts=agg.get("total_spending_cuts", 0.0),
        agg=agg, instrument=instrument, annual_return_pct=annual_return_pct,
    )
    rec = next(s for s in scenarios if s["recommended"])
    return {
        **extra,
        "monthly_savings_needed": rec["monthly_savings_needed"],
        "recommended_timeline_months": rec["timeline_months"],
        "feasible": rec["feasible"],
        "shortfall_per_month": rec["shortfall_per_month"],
        "recommended_instrument": instrument,
        **meta,
        "scenarios": scenarios,
    }


def _plan_gadget(goal: dict, agg: dict) -> dict:
    target   = _parse_amount(goal.get("target_amount")) or 0.0
    existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    months   = _months_from_timeline(goal.get("timeline")) or 6.0
    return _savings_goal(goal, agg, target=target, existing=existing, months=months,
                         instrument="Liquid Mutual Fund or high-yield savings account",
                         extra={"purchase_price": target, "existing_savings": existing,
                                "gap": round(max(0.0, target - existing), 2)})


def _plan_car(goal: dict, agg: dict) -> dict:
    price    = _parse_amount(goal.get("target_amount")) or 0.0
    existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    months   = _months_from_timeline(goal.get("timeline")) or 18.0
    pref     = str(goal.get("financing_preference") or "loan").lower()
    user_dp  = _num(goal.get("down_payment_pct"), 100 if "cash" in pref else 30)
    net      = agg["monthly_net_flow"]
    cuts     = agg.get("total_spending_cuts", 0.0)
    tenure_months = max(1, int(_num(goal.get("loan_tenure_months"), 60)))
    rate = _num(goal.get("loan_interest_rate_pct"), 10.0)
    # "What car can I afford?" → COMPUTE the max price (down payment + biggest EMI-affordable loan).
    if goal.get("find_max_affordable"):
        price = _max_affordable_price(goal, agg, rate, tenure_months, months)
    user_dp  = _resolve_down_payment_pct(goal, agg, price, months, user_dp)   # what-if dp overrides

    scenarios, meta = _loan_scenarios(
        price=price, existing=existing, user_months=months, user_dp_pct=user_dp,
        surplus=net, cuts=cuts, agg=agg,
        rate=rate, tenure=tenure_months, down_label="down payment", asset="car",
        instrument="Recurring Deposit or Liquid MF for the down payment",
    )
    rec = next(s for s in scenarios if s["recommended"])
    return {
        "vehicle_price": price,
        "financing": "cash" if rec["loan_amount"] <= 0 else "loan",
        "down_payment_pct": rec["down_payment_pct"],
        "down_payment_needed": rec["down_payment_amount"],
        "down_payment_from_existing": rec["down_payment_from_existing"],
        "down_payment_from_savings": rec["down_payment_from_savings"],
        "loan_amount": rec["loan_amount"],
        "loan_tenure_months": rec["loan_tenure_months"],
        "estimated_emi": rec["estimated_emi"],
        "total_interest_paid": rec["total_interest_paid"],
        "total_cost_of_ownership": rec["total_cost_of_ownership"],
        "existing_savings": existing,
        "monthly_to_save_for_down_payment": rec["monthly_savings_needed"],
        "total_monthly_outgo_after_purchase": rec["monthly_post_purchase"],
        "monthly_savings_needed": rec["monthly_savings_needed"],
        "recommended_timeline_months": rec["timeline_months"],
        "feasible": rec["feasible"],
        "shortfall_per_month": rec["shortfall_per_month"],
        "note": f"EMI at 10% p.a., {tenure_months // 12}-year ({tenure_months}-month) tenure. "
                "Verify current rates with your bank.",
        "recommended_instrument": "Recurring Deposit or Liquid MF for the down payment",
        **meta,
        "scenarios": scenarios,
    }


def _plan_travel(goal: dict, agg: dict) -> dict:
    base_cost = _parse_amount(goal.get("target_amount")) or 0.0
    existing  = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    months    = _months_from_timeline(goal.get("timeline")) or 6.0
    travelers = int(_num(goal.get("travelers"), 1))
    total     = base_cost * travelers if travelers > 1 else base_cost
    return _savings_goal(goal, agg, target=total, existing=existing, months=months,
                         instrument="Liquid Mutual Fund (instant redemption)",
                         extra={"trip_cost_total": round(total, 2), "per_person_cost": round(base_cost, 2),
                                "travelers": travelers, "existing_savings": existing,
                                "gap": round(max(0.0, total - existing), 2)})


def _plan_emergency_fund(goal: dict, agg: dict) -> dict:
    user_cov  = _num(goal.get("target_months_coverage"), 6)
    current   = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    spend     = agg["monthly_avg_spend"]
    target    = round(spend * user_cov, 2)
    months    = _months_from_timeline(goal.get("timeline")) or 12.0
    # An emergency fund must stay instantly accessible — assume no growth (kept liquid).
    return _savings_goal(goal, agg, target=target, existing=current, months=months, annual_return_pct=0.0,
                         instrument="High-yield savings account + Liquid MF (instant access)",
                         extra={"monthly_expense_baseline": spend, "target_coverage_months": user_cov,
                                "emergency_fund_target": target, "current_emergency_savings": current,
                                "gap": round(max(0.0, target - current), 2)})


def _plan_house(goal: dict, agg: dict) -> dict:
    prop     = _parse_amount(goal.get("target_amount")) or 0.0
    user_dp  = _num(goal.get("down_payment_pct"), 20)
    existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    months   = _months_from_timeline(goal.get("timeline")) or 36.0
    rate     = _num(goal.get("loan_interest_rate_pct"), 8.5)
    if goal.get("find_max_affordable"):                       # "what house can I afford?"
        prop = _max_affordable_price(goal, agg, rate, 240, months)
    user_dp  = _resolve_down_payment_pct(goal, agg, prop, months, user_dp)   # what-if dp overrides
    stamp_pct = _num(goal.get("stamp_duty_pct"), 7.0)        # rough default; varies by state
    stamp     = round(prop * stamp_pct / 100.0, 2)
    net      = agg["monthly_net_flow"]
    cuts     = agg.get("total_spending_cuts", 0.0)

    scenarios, meta = _loan_scenarios(
        price=prop, existing=existing, user_months=months, user_dp_pct=user_dp,
        surplus=net, cuts=cuts, agg=agg,
        rate=rate, tenure=240, extra_upfront=stamp,
        down_label="down payment", asset="home",
        instrument="Equity MF SIP (if >3 years away) + FD / RD closer to purchase",
    )
    rec = next(s for s in scenarios if s["recommended"])
    return {
        "property_value": prop,
        "down_payment_pct": rec["down_payment_pct"],
        "down_payment_amount": rec["down_payment_amount"],
        "stamp_duty_registration_estimate": stamp,
        "total_upfront_needed": round(rec["down_payment_amount"] + stamp, 2),
        "existing_savings": existing,
        "monthly_savings_needed": rec["monthly_savings_needed"],
        "recommended_timeline_months": rec["timeline_months"],
        "feasible": rec["feasible"],
        "shortfall_per_month": rec["shortfall_per_month"],
        "home_loan_amount": rec["loan_amount"],
        "estimated_home_loan_emi": rec["estimated_emi"],
        "note": f"Home loan EMI at 8.5% p.a., 20-year tenure. Stamp duty + registration estimated "
                f"at {stamp_pct:.0f}% — a ROUGH figure that varies 4–10% by state, gender and "
                f"property type; verify your state's rate. Verify loan rates with your bank.",
        "stamp_duty_pct_assumed": stamp_pct,
        "recommended_instrument": "Equity MF SIP (if >3 years away) + FD / RD closer to purchase",
        **meta,
        "scenarios": scenarios,
    }


def _plan_education(goal: dict, agg: dict) -> dict:
    cost     = _parse_amount(goal.get("target_amount")) or 0.0
    existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    months   = _months_from_timeline(goal.get("timeline")) or 24.0
    pref     = str(goal.get("loan_preference") or "hybrid").lower()
    net      = agg["monthly_net_flow"]
    cuts     = agg.get("total_spending_cuts", 0.0)

    # Map the user's stated preference to a self-funded % (the rest is an education loan):
    #   hybrid / both → 50%;  loan / full loan / debt → 0% self;  self-funded / cash → 100%.
    if "hybrid" in pref or "both" in pref:
        user_self_pct = 50
    elif "loan" in pref or "debt" in pref or "full" in pref:
        user_self_pct = 0
    else:
        user_self_pct = 100

    # Loan tenure is configurable (10/15/20-year are common); default to 15 years.
    tenure_years = max(1, int(_num(goal.get("loan_tenure_years"), 15)))
    tenure_months = tenure_years * 12
    edu_rate = _num(goal.get("loan_interest_rate_pct"), 10.5)

    # Education program cost is FIXED — the lever is the financing mix, not a cheaper "price".
    scenarios, meta = _education_scenarios(
        cost=cost, existing=existing, user_months=months, self_pct=user_self_pct,
        surplus=net, cuts=cuts, agg=agg, tenure=tenure_months, rate=edu_rate,
    )
    rec = next(s for s in scenarios if s["recommended"])
    return {
        "total_program_cost": cost, "existing_savings": existing,
        "financing": pref,
        "self_funded_pct": rec["down_payment_pct"],
        "self_funded_amount": rec["down_payment_amount"],
        "self_funded_from_existing": rec["down_payment_from_existing"],
        "self_funded_from_savings": rec["down_payment_from_savings"],
        "loan_amount": rec["loan_amount"],
        "estimated_loan_emi": rec["estimated_emi"],
        "total_interest_paid": rec["total_interest_paid"],
        "total_cost_of_ownership": rec["total_cost_of_ownership"],
        "monthly_savings_needed": rec["monthly_savings_needed"],
        "recommended_timeline_months": rec["timeline_months"],
        "feasible": rec["feasible"],
        "shortfall_per_month": rec["shortfall_per_month"],
        "note": f"Education loan EMI at 10.5% p.a. over a {tenure_years}-year tenure (repayment "
                "starts after a moratorium during study; education loans can finance up to 100% of "
                "the program). Explore scholarships, fellowships and funded/stipend programs — many "
                "PhDs are fully funded.",
        "recommended_instrument": "Education loan + SIP in debt/liquid MF for the self-funded portion",
        **meta,
        "scenarios": scenarios,
    }


def _plan_retirement(goal: dict, agg: dict) -> dict:
    cur_age  = _num(goal.get("current_age"), 30)
    ret_age  = _num(goal.get("target_age"), 60)
    ret_exp  = _parse_amount(goal.get("monthly_retirement_expenses") or agg["monthly_avg_spend"]) or agg["monthly_avg_spend"]
    # Current invested corpus is read AUTOMATICALLY from the user's tracked portfolio + fixed
    # deposits (held to maturity) — we don't ask for it. Fall back to any explicitly provided
    # savings only if nothing is on record.
    cur_inv  = round((agg.get("portfolio_value") or 0.0) + (agg.get("fd_current_value") or 0.0), 2) \
        or _parse_amount(goal.get("existing_savings") or 0) or 0.0
    yrs      = max(0.0, ret_age - cur_age)
    mo       = yrs * 12
    net      = agg["monthly_net_flow"]

    annual_ret_exp = ret_exp * 12
    base_corpus    = annual_ret_exp * 25  # 4% withdrawal rule

    # Guard: if the user is already at/over their target retirement age there is no accumulation
    # window — return an honest result rather than dividing by a zero-month horizon (spec #6).
    if mo <= 0:
        return {
            "current_age": cur_age, "target_retirement_age": ret_age,
            "years_to_retirement": 0,
            "monthly_expenses_in_retirement": ret_exp,
            "corpus_target_today_value": round(base_corpus, 2),
            "current_investments": cur_inv,
            "monthly_sip_needed": 0.0,
            "feasible": True,
            "shortfall_per_month": 0.0,
            "already_retired": True,
            "note": "Your current age is at or beyond the target retirement age — you are already "
                    "at/over retirement. Shift focus from accumulation to a withdrawal plan (SWP) "
                    "from your existing corpus.",
            "recommended_instrument": "Systematic Withdrawal Plan (SWP) from existing corpus",
            "scenarios": [],
        }

    def _ret_sc(tag, label, recommended, annual_return):
        infl_rate = 0.06
        infl_corpus = round(base_corpus * (1 + infl_rate) ** yrs, 2)
        existing_fv = round(cur_inv * (1 + annual_return / 12) ** mo, 2)
        remaining   = max(0.0, infl_corpus - existing_fv)
        sip = round(_monthly_sip_for_corpus(remaining, annual_return * 100, int(mo)), 2) if mo > 0 else remaining
        return _sc(tag, label, recommended, sip, net,
                   annual_return_pct=annual_return * 100,
                   inflation_adjusted_corpus=infl_corpus,
                   existing_investments_fv=existing_fv,
                   monthly_sip_needed=sip,
                   total_months=int(mo),
                   instrument=(
                       "FD + Debt MF + PPF" if annual_return <= 0.07
                       else "Balanced MF + NPS" if annual_return <= 0.10
                       else "Equity SIP (Flexicap + Largecap) + NPS"))

    scenarios = [
        _ret_sc("A", "Conservative (7% p.a. — debt/FD portfolio)", False, 0.07),
        _ret_sc("B", "Moderate (10% p.a. — balanced portfolio)", True, 0.10),
        _ret_sc("C", "Aggressive (12% p.a. — equity SIP)", False, 0.12),
    ]
    rec = scenarios[1]
    return {
        "current_age": cur_age, "target_retirement_age": ret_age,
        "years_to_retirement": yrs,
        "monthly_expenses_in_retirement": ret_exp,
        "corpus_target_today_value": round(base_corpus, 2),
        "inflation_adjusted_corpus": rec["inflation_adjusted_corpus"],
        "current_investments": cur_inv,
        "monthly_sip_needed": rec["monthly_sip_needed"],
        "feasible": rec["feasible"],
        "shortfall_per_month": rec["shortfall_per_month"],
        "note": "4% withdrawal rule; 6% inflation; actual returns vary.",
        "recommended_instrument": "Equity SIP (Largecap + Flexicap) + NPS (tax benefit u/s 80CCD)",
        "scenarios": scenarios,
    }


def _plan_fire(goal: dict, agg: dict) -> dict:
    exp     = _parse_amount(goal.get("target_amount") or goal.get("monthly_retirement_expenses")) or agg["monthly_avg_spend"]
    # Current net worth is read AUTOMATICALLY from portfolio + fixed deposits + liquid balances —
    # we don't ask. Honour an explicitly provided figure only if present.
    worth   = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    if worth <= 0:
        worth = round((agg.get("portfolio_value") or 0.0)
                      + (agg.get("fd_current_value") or 0.0)
                      + (agg.get("total_current_balance") or 0.0), 2)
    net     = agg["monthly_net_flow"]
    cuts    = agg.get("total_spending_cuts", 0.0)
    invest  = max(0.0, (net + cuts) * _CAP_UTIL)  # 70% of (surplus + reclaimed spending cuts) invested
    RETURN  = 0.12

    def _fire_sc(tag, label, recommended, exp_mult):
        monthly_exp = round(exp * exp_mult, 2)
        corpus_4pct = round(monthly_exp * 12 * 25, 2)
        corpus_3pct = round(monthly_exp * 12 * 33, 2)
        yrs_4 = _years_to_fi(worth, invest, corpus_4pct, RETURN)
        return _sc(tag, label, recommended, invest, net,
                   monthly_lifestyle_expenses=monthly_exp,
                   fi_corpus_4pct=corpus_4pct,
                   fi_corpus_conservative=corpus_3pct,
                   years_to_fi=yrs_4,
                   monthly_investment=invest)

    scenarios = [
        _fire_sc("A", "Lean FIRE (75% of current expenses)", False, 0.75),
        _fire_sc("B", "Regular FIRE (100% — your target)", True, 1.00),
        _fire_sc("C", "Fat FIRE (150% — comfortable lifestyle)", False, 1.50),
    ]
    rec = scenarios[1]
    return {
        "desired_monthly_expenses": exp,
        "current_net_worth": worth,
        "fi_corpus_4pct_rule": rec["fi_corpus_4pct"],
        "fi_corpus_conservative_3pct": rec["fi_corpus_conservative"],
        "monthly_investment_assumed": invest,
        "years_to_fi": rec["years_to_fi"],
        "feasible": rec["years_to_fi"] is not None and rec["years_to_fi"] < 40,
        "note": "FIRE at 12% equity return; actual returns vary. Consult a SEBI-RIA.",
        "recommended_instrument": "Equity SIP (Flexicap + Midcap) + PPF + International MF",
        "scenarios": scenarios,
        "phases": [
            {"phase": "Accumulation (Y0–Y5)", "focus": "Maximise savings rate, equity SIP"},
            {"phase": "Growth (Y5–FI)", "focus": "Diversify into debt, reduce equity risk"},
            {"phase": "FI Maintenance", "focus": "Systematic Withdrawal Plan (SWP) from corpus"},
        ],
    }


def _plan_wedding(goal: dict, agg: dict) -> dict:
    budget   = _parse_amount(goal.get("target_amount")) or 0.0
    existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    months   = _months_from_timeline(goal.get("timeline")) or 18.0
    return _savings_goal(goal, agg, target=budget, existing=existing, months=months,
                         instrument="FD ladder + Recurring Deposit (low-risk, accessible)",
                         extra={"wedding_budget": budget, "existing_savings": existing,
                                "gap": round(max(0.0, budget - existing), 2)})


def _plan_multi_goal(goal: dict, agg: dict) -> dict:
    sub_goals = goal.get("sub_goals") or []
    net       = agg["monthly_net_flow"]
    investable = max(0.0, net * _CAP_UTIL)

    planned = []
    total_needed = 0.0
    for sg in sub_goals:
        target  = _parse_amount(sg.get("target_amount")) or 0.0
        ex      = _parse_amount(sg.get("existing_savings") or 0) or 0.0
        mo      = _months_from_timeline(sg.get("timeline"))
        if target and mo and mo > 0:
            gap = max(0.0, target - ex)
            ms = round(gap / mo, 2)
            total_needed += ms
            planned.append({
                "description": sg.get("description"),
                "goal_type": sg.get("goal_type", "generic"),
                "target_amount": target, "timeline_months": mo,
                "gap": round(gap, 2),
                "monthly_savings_needed": ms,
            })
    planned.sort(key=lambda x: x.get("timeline_months") or float("inf"))

    def _allocate(strategy: str) -> list:
        if strategy == "sequential":
            # Fund goals one after another at FULL capacity: compute each goal's funding window
            # (gap / investable, rounded up) and schedule them back-to-back.
            result = []
            start = 0
            for p in planned:
                if investable > 0:
                    duration = max(1, math.ceil(p["gap"] / investable))
                    alloc = round(min(investable, p["gap"]), 2)
                else:
                    duration = int(p.get("timeline_months") or 1)
                    alloc = 0.0
                result.append({
                    **p,
                    "allocated_monthly": alloc,
                    "start_month": start + 1,
                    "end_month": start + duration,
                    "funding_window": f"Month {start + 1}–{start + duration}",
                })
                start += duration
            return result
        result = []
        for i, p in enumerate(planned):
            if strategy == "parallel":
                prop  = p["monthly_savings_needed"] / max(total_needed, 1)
                alloc = round(investable * prop, 2)
            else:  # hybrid: 60% to most urgent, 40% split
                if i == 0:
                    alloc = round(investable * 0.60, 2)
                else:
                    rest_prop = p["monthly_savings_needed"] / max(total_needed - planned[0]["monthly_savings_needed"], 1)
                    alloc = round(investable * 0.40 * rest_prop, 2)
            result.append({**p, "allocated_monthly": alloc})
        return result

    sc_a = _sc("A", "Sequential (fastest goal first, then next)", False, total_needed, net,
               strategy="sequential", goals=_allocate("sequential"))
    sc_b = _sc("B", "Parallel (proportional split across all goals)", True, total_needed, net,
               strategy="parallel", goals=_allocate("parallel"))
    sc_c = _sc("C", "Hybrid (60% most urgent, 40% split rest)", False, total_needed, net,
               strategy="hybrid", goals=_allocate("hybrid"))

    return {
        "planned_goals": _allocate("parallel"),
        "total_monthly_needed": round(total_needed, 2),
        "available_investable_monthly": round(investable, 2),
        "feasible": investable >= total_needed,
        "monthly_shortfall": round(max(0.0, total_needed - investable), 2),
        "recommended_instrument": "Separate goal-linked RD or MF per goal for clear tracking",
        "scenarios": [sc_a, sc_b, sc_c],
    }


def _plan_generic(goal: dict, agg: dict) -> dict:
    target   = _parse_amount(goal.get("target_amount")) or 0.0
    existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    months   = _months_from_timeline(goal.get("timeline")) or 12.0
    return _savings_goal(goal, agg, target=target, existing=existing, months=months,
                         instrument="Liquid MF or FD based on timeline",
                         extra={"target_amount": target, "existing_savings": existing,
                                "gap": round(max(0.0, target - existing), 2)})


def _apply_what_if(agg: dict, goal: dict) -> dict:
    """Apply goal-level what-if overrides that affect the financial snapshot. Currently:
    `monthly_savings_override` replaces the user's modelled monthly surplus (so feasibility,
    the EMI cap and SIP all reflect the hypothetical saving rate)."""
    override = goal.get("monthly_savings_override")
    if override is not None:
        val = _parse_amount(override)
        if val is not None and val >= 0:
            agg = {**agg, "monthly_net_flow": float(val), "total_spending_cuts": 0.0}
    return agg


def _resolve_down_payment_pct(goal: dict, agg: dict, price: float, months: float,
                              default_pct: float) -> float:
    """What-if down-payment overrides (for loan goals). Precedence:
       1. `down_payment_amount` — an explicit ₹ figure → converted to a % of the price.
       2. `down_payment_source` — "savings" sets the down payment to all available cash + saving
          over the timeline; "everything"/"all"/"liquidity" ALSO adds every breakable FD/liquid fund.
       3. otherwise the user's stated `down_payment_pct` (default).
    Lets a what-if say "increase my down payment to whatever I save" or "use everything"."""
    if price <= 0:
        return default_pct
    amt = _parse_amount(goal.get("down_payment_amount"))
    if amt is None:
        src = str(goal.get("down_payment_source") or "").lower().strip()
        if src:
            bank = max(0.0, float(agg.get("total_current_balance") or 0.0))
            existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
            save = max(0.0, float(agg.get("monthly_net_flow") or 0.0))
            amt = bank + existing + save * max(1.0, months)
            if any(k in src for k in ("everything", "all", "liquid", "fd", "fund")):
                amt += _minimal_deployment(price, agg, include_bank=False)["deployed_total"]
    if amt is None or amt <= 0:
        return default_pct
    return min(100.0, max(0.0, amt / price * 100.0))


def _max_affordable_price(goal: dict, agg: dict, rate: float, tenure: int, months: float) -> float:
    """Largest purchase the user can afford = down payment (from the chosen funds) + the BIGGEST loan
    whose EMI fits 70% of their monthly saving. Used by "what … can I afford?" what-ifs so the price
    is COMPUTED, not guessed by the model."""
    save = max(0.0, float(agg.get("monthly_net_flow") or 0.0))
    max_loan = _inv_emi(_CAP_UTIL * save, rate, tenure)               # EMI ≤ 70% of saving
    bank = max(0.0, float(agg.get("total_current_balance") or 0.0))
    existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    down = bank + existing + save * max(1.0, months)                 # bank + saving over the timeline
    src = str(goal.get("down_payment_source") or "everything").lower()
    if any(k in src for k in ("everything", "all", "liquid", "fd", "fund")):
        down += _minimal_deployment(1e12, agg, include_bank=False)["deployed_total"]   # + broken FDs/funds
    return round(down + max_loan, 2)


_GOAL_PLANNERS = {
    "gadget_purchase": _plan_gadget,
    "car":             _plan_car,
    "travel":          _plan_travel,
    "emergency_fund":  _plan_emergency_fund,
    "house":           _plan_house,
    "education":       _plan_education,
    "retirement":      _plan_retirement,
    "fire":            _plan_fire,
    "wedding":         _plan_wedding,
    "multi_goal":      _plan_multi_goal,
}


# ── Main tool node ────────────────────────────────────────────────────────────

def _goal_summary(goal_type: str, target_amount: Any, timeline: Any,
                  monthly_needed: Any, net_flow: Any, feasible: Any, n_scenarios: int) -> str:
    """One-line evidence summary that never renders '₹None' for a missing target."""
    target_display = _inr(target_amount) if target_amount else "N/A"
    return (
        f"Goal '{goal_type}' — target={target_display}, "
        f"timeline={timeline}, monthly_needed={_inr(monthly_needed or 0)}, "
        f"net_flow={_inr(net_flow)}, feasible={feasible}, "
        f"scenarios={n_scenarios}"
    )


def goal_planner_tool(state: AgentState) -> dict:
    user_id   = state.get("user_id") or ""
    task      = state.get("brain_task") or {}
    goal      = task.get("goal") or {}
    evidence  = state.get("evidence") or []

    # A what-if BUILDS ON the prior goal. The supervisor LLM is unreliable at re-extracting every
    # field from history (it often drops target_amount → price 0 → no loan), so merge the persisted
    # `last_goal` underneath and let the what-if's explicit (non-null) overrides win on top. This
    # makes what-ifs cumulative ("…and also at 15% interest") and robust to dropped fields.
    if goal.get("what_if"):
        prior = state.get("last_goal") or {}
        if prior:
            merged = dict(prior)
            for k, v in goal.items():
                if v not in (None, "") and not (k == "what_if" and v is False):
                    merged[k] = v
            goal = merged
            task = {**task, "goal": goal}

    # Financial baseline: monthly aggregates + LIQUID balance (credit cards excluded).
    agg          = _compute_monthly_aggregates(user_id)
    balance_info = _get_account_balances(user_id)
    agg["total_current_balance"] = balance_info["liquid_balance"]
    agg["liquid_accounts"]       = balance_info.get("liquid_accounts") or []

    # Resolve the funding selection that drives every funding decision: how much idle bank cash to
    # deploy (keep 10% by default), whether to use liquid funds, and which FDs to break. The brain
    # may pass an explicit `goal.funding_selection` for what-ifs ("break only my SBI FD", "use half
    # my bank cash"); otherwise it is inferred from the goal/sub-question text.
    agg["funding_selection"] = _resolve_funding_selection(goal, task)

    # Spending reduction opportunities — computed BEFORE the planner so scenario C can use the
    # total potential cut to build an "accelerated" feasible plan.
    spending_cats = _extract_spending_categories(evidence)
    if not spending_cats:
        spending_cats = _compute_category_breakdown(user_id, agg["months_observed"])
    spend_ops = _spending_reduction_opportunities(spending_cats) if spending_cats else []
    agg["total_spending_cuts"] = round(sum(o.get("potential_saving", 0) for o in spend_ops), 2)

    # Investment portfolio + fixed deposits — fetched UP-FRONT (before the planner) so EVERY goal
    # can draw on them as a genuine funding source. We never ask the user for these figures.
    inv_data = _extract_investment_data(evidence) or _fetch_investment_holdings(user_id, live_nav=True)
    fds = _fetch_fixed_deposits(user_id)

    # Evaluate each FD AT THE GOAL'S TIMELINE END: matured-by-then FDs are usable in full (no
    # penalty); still-locked FDs are usable only at their penalised break value, and only if the
    # funding selection chooses to break them. Fall back to a 12-month horizon if no timeline given.
    _goal_months  = _months_from_timeline(goal.get("timeline")) or 12.0
    goal_end_date = date.today() + timedelta(days=int(round(_goal_months * 30.44)))
    fd_view = _fd_funding_view(fds, goal_end_date, agg["funding_selection"])

    agg["portfolio_value"]    = round(float((inv_data or {}).get("total_current") or 0.0), 2)
    agg["liquid_fund_value"]        = _liquid_fund_value(inv_data, _goal_months)   # value at goal end
    agg["liquid_fund_current_value"] = _liquid_fund_current_value(inv_data)        # value today
    agg["fd_current_value"]   = round(sum(f.get("current_value") or 0.0 for f in fds), 2)  # held-to-maturity
    agg["fd_breakable_value"] = round(sum(f.get("break_value") or 0.0 for f in fds), 2)    # net if broken now
    agg["fd_funding_view"]    = fd_view                                         # per-FD value at goal end + selection
    agg["goal_end_date"]      = goal_end_date.isoformat()
    agg["fd_list"]            = fds                                              # for naming sources by bank

    # What-if overrides (e.g. "what if I save ₹15,000/mo") adjust the snapshot before planning.
    what_if = bool(goal.get("what_if"))
    agg = _apply_what_if(agg, goal)

    # Run type-specific planner
    goal_type = str(goal.get("goal_type") or "generic").lower().strip()
    planner   = _GOAL_PLANNERS.get(goal_type, _plan_generic)
    extra     = planner(goal, agg)

    # A what-if returns a single direct computation (scenario A) — no A/B/C report.
    # A what-if answers ONE specific question, so it keeps a SINGLE scenario (the recommended /
    # best-fit one under the overridden assumptions) — but still rendered in FULL detail (a card
    # with its money trail + charts), not a one-line answer.
    if what_if:
        scns = extra.get("scenarios") or []
        if scns:
            keep = dict(next((s for s in scns if s.get("recommended")), scns[0]))
            keep["recommended"] = True
            extra["scenarios"] = [keep]
        extra["what_if"] = True
        extra["what_if_summary"] = goal.get("description") or task.get("sub_question") or "What-if analysis"

    if spend_ops:
        extra["spending_reduction_opportunities"] = spend_ops
        extra["spending_by_category"] = spending_cats

    # Where the deployable seed money comes from (bank cash / liquid funds / breakable FDs) — so
    # the answer is transparent that some funding may require breaking an FD.
    extra["funding_sources"] = _funding_sources(agg)
    extra["funding_selection_applied"] = agg["funding_selection"]

    # Compact self-funded-vs-loan split for the funding pie (answer_node), taken from the
    # RECOMMENDED scenario's actual funding: loan + the deployment it breaks (FD/liquid) + the
    # cash/savings remainder of the down payment.
    _rec = next((s for s in (extra.get("scenarios") or []) if s.get("recommended")), None) or {}
    _dep = _rec.get("deployment") or {}
    _loan = round(float(_rec.get("loan_amount") or 0.0), 2)
    _liquid = round(float(_dep.get("from_liquid") or 0.0), 2)
    _fd = round(float(_dep.get("from_fds_matured") or 0.0) + float(_dep.get("from_fds_broken") or 0.0), 2)
    # The self-funded slice (down payment for loan goals, or the whole target for savings goals)
    # minus the broken funds is the bank-cash / savings part.
    _selffunded = float(_rec.get("down_payment_amount") or _rec.get("target_amount") or 0.0)
    _bank = round(max(0.0, _selffunded - _liquid - _fd), 2)
    extra["funding_breakdown"] = {"loan": _loan, "bank": _bank, "fd": _fd, "liquid": _liquid}
    if fds:
        extra["fixed_deposits"] = fd_view              # per-FD value at goal end + selection
        extra["fixed_deposits_summary"] = {
            "count": len(fds),
            "total_current_value": agg["fd_current_value"],
            "total_break_value": agg["fd_breakable_value"],
            "total_maturity_value": round(sum(f.get("maturity_value") or 0.0 for f in fds), 2),
            "matured_by_goal_end_count": sum(1 for f in fd_view if f.get("matures_by_goal_end")),
            "selected_usable_value": round(sum(f.get("usable_value") or 0.0
                                               for f in fd_view if f.get("selected")), 2),
            "goal_end_date": agg["goal_end_date"],
        }

    # Investment liquidity check — uses the portfolio fetched above.
    if inv_data:
        gap = extra.get("gap") or max(0.0, (extra.get("target_amount") or 0) - (extra.get("existing_savings") or 0))
        extra["investment_liquidity_check"] = _check_investment_liquidity(gap, inv_data)
        extra["portfolio_holdings"] = inv_data.get("holdings") or []

    target_amount = _parse_amount(goal.get("target_amount"))
    credit_accounts = balance_info.get("credit_accounts") or []
    illiquid_accounts = balance_info.get("illiquid_accounts") or []
    payment_source_note = (
        "Credit-card balances are debt, not spendable funds — they are excluded from your "
        "liquid balance and must NEVER be treated as a way to pay for this goal."
        if credit_accounts else
        "All listed balances are liquid (spendable) funds."
    )

    data = {
        "goal_type": goal_type,
        "what_if": what_if,
        "goal_description": goal.get("description"),
        "target_amount": target_amount,
        "timeline": goal.get("timeline"),
        "timeline_months": _months_from_timeline(goal.get("timeline")),
        # Financial baseline (real, from the database)
        "monthly_avg_spend": agg["monthly_avg_spend"],
        "monthly_avg_income": agg["monthly_avg_income"],
        "monthly_net_flow": agg["monthly_net_flow"],
        "savings_rate_pct": agg.get("savings_rate_pct"),
        "monthly_savings_capacity": agg.get("monthly_savings_capacity"),
        "months_analyzed": agg.get("months_analyzed"),
        "income_source": agg.get("income_source"),
        "liquid_balance": agg.get("total_current_balance"),
        "liquid_accounts": agg.get("liquid_accounts") or [],
        "credit_accounts": credit_accounts,
        "illiquid_accounts": illiquid_accounts,
        "payment_source_note": payment_source_note,
        "months_observed": agg["months_observed"],
        **extra,
    }

    # Attach a ₹-formatted sibling ('<key>_inr') to EVERY monetary number throughout the
    # data — including inside each scenario — so the answer/caption models copy a correct
    # full-rupee string (₹27,000) and never rescale to "lakhs" or do their own arithmetic.
    _attach_inr(data)

    ms      = extra.get("monthly_savings_needed") or extra.get("total_monthly_needed") or 0
    summary = _goal_summary(
        goal_type, data.get("target_amount"), goal.get("timeline"),
        ms, agg["monthly_net_flow"], extra.get("feasible"),
        len(extra.get("scenarios") or []),
    )
    logger.info("[goal_planner] %s", summary)

    return {
        "evidence": [{"tool": "goal_planner", "task": task.get("sub_question") or state.get("user_query"),
                      "summary": summary, "data": data}],
        "sources": ["Supabase Transactions", "Goal Planner"],
        # Persist the resolved goal so the NEXT what-if can build on it (carries target_amount,
        # timeline, etc. even when the supervisor LLM drops them).
        "last_goal": goal,
    }
