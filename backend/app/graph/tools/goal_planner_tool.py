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
    "travelers", "month", "months", "year", "years", "timeline", "coverage", "fv",
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


# ── Evidence extraction helpers ───────────────────────────────────────────────

def _extract_nl2sql_financials(evidence: List[Dict]) -> Optional[Dict]:
    for e in evidence:
        if e.get("tool") != "nl2sql":
            continue
        data = e.get("data") or {}
        rows = data.get("rows") or []
        analytics = data.get("analytics") or {}
        balances = [float(r["current_balance"] or 0) for r in rows
                    if isinstance(r, dict) and "current_balance" in r]
        return {
            "total_current_balance": sum(balances) if balances else None,
            "total_income":  analytics.get("total_income"),
            "total_expense": analytics.get("total_expense") or analytics.get("total_amount"),
        }
    return None


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
        if any(nr in name for nr in _NON_REDUCIBLE):
            continue
        # Match on the main category OR any of its sub-categories.
        subs = cat.get("subcategories") or []
        haystack = name + " " + " ".join((s.get("name") or "").lower() for s in subs)
        for kw, pct in _REDUCIBLE_KEYWORDS.items():
            if kw in haystack and amount > 500:
                result.append({
                    "category": cat["category"],
                    "current_monthly": round(amount, 2),
                    "suggested_reduction_pct": pct,
                    "potential_saving": round(amount * pct / 100, 2),
                    # sub-category detail so the answer can JUSTIFY the cut
                    "driven_by": [{"name": s.get("name"), "amount": s.get("amount")} for s in subs[:3]],
                })
                break
    result.sort(key=lambda x: x["potential_saving"], reverse=True)
    return result[:4]


def _check_investment_liquidity(gap: float, inv_data: Dict) -> Dict:
    total_current = float(inv_data.get("total_current") or 0)
    holdings = inv_data.get("holdings") or []
    LIQUID_KW = ("liquid", "debt", "fd", "fixed deposit", "savings", "money market",
                 "overnight", "ultra short", "short term")
    liquid_h = [h for h in holdings
                if any(kw in (h.get("name") or "").lower() for kw in LIQUID_KW)]
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
    n = max(len(monthly), 1)
    total_exp = sum(m["expense"] for m in monthly.values())
    total_inc = sum(m["income"] for m in monthly.values())
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
    return {
        "months_observed": len(monthly),
        "monthly_avg_spend": monthly_spend,
        "monthly_avg_income": monthly_income,
        "monthly_net_flow": round(monthly_income - monthly_spend, 2),
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
            liquid += max(0.0, bal)   # a negative balance must not reduce deployable cash
        else:
            # Unknown type: be conservative and treat as illiquid rather than spendable.
            illiquid_accounts.append({"name": r.get("account_name"), "type": atype,
                                      "balance": round(max(0.0, bal), 2)})
    return {
        "liquid_balance": round(liquid, 2),
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
    try:
        if supabase_db:
            resp = (supabase_db.table("transactions")
                    .select("amount, transaction_type, merchant_name, categories(main_category, sub_category)")
                    .eq("user_id", user_id).execute())
            for tx in resp.data or []:
                if (tx.get("transaction_type") or "").lower() != "expense":
                    continue
                amount = abs(float(tx.get("amount") or 0))
                cat_obj = tx.get("categories") or {}
                main = cat_obj.get("main_category") or "Others"
                sub = cat_obj.get("sub_category") or tx.get("merchant_name") or "Other"
                cats[main] += amount
                subs[main][sub] += amount
    except Exception as exc:
        logger.warning("[goal_planner] category breakdown error: %s", exc)
    n = max(months_observed, 1)
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


def _fetch_investment_holdings(user_id: str) -> Optional[Dict]:
    """Lightweight portfolio snapshot at purchase value (no live NAV calls, for speed)."""
    try:
        if supabase_db:
            resp = (supabase_db.table("investments")
                    .select("scheme_name, quantity, purchase_nav")
                    .eq("user_id", user_id).execute())
            rows = resp.data or []
            if not rows:
                return None
            holdings, total = [], 0.0
            for r in rows:
                val = float(r.get("quantity") or 0) * float(r.get("purchase_nav") or 0)
                total += val
                holdings.append({"name": r.get("scheme_name"), "current_value": round(val, 2)})
            for h in holdings:
                h["share_pct"] = round(h["current_value"] / total * 100, 2) if total > 0 else 0.0
            # Values are cost basis (quantity * purchase_nav), NOT live NAV — flag it honestly.
            return {"total_current": round(total, 2), "holdings": holdings,
                    "valuation_basis": "purchase_cost"}
    except Exception as exc:
        logger.warning("[goal_planner] investment fetch error: %s", exc)
    return None


# ── Scenario builder helpers ──────────────────────────────────────────────────

def _sc(tag: str, label: str, recommended: bool,
        monthly_savings_needed: float, net_flow: float, **extra) -> Dict:
    """Build a standard scenario dict."""
    ms = round(monthly_savings_needed, 2)
    return {
        "tag": tag,
        "label": label,
        "recommended": recommended,
        "monthly_savings_needed": ms,
        "feasible": net_flow >= ms if net_flow > 0 else False,
        "shortfall_per_month": round(max(0.0, ms - net_flow), 2),
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


_CAP_UTIL = 0.95   # use 95% of capacity when solving, leaving a small buffer
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


def _deployable(agg: dict) -> float:
    """Idle liquid funds that can seed a down payment, keeping a 3-month emergency buffer."""
    liquid = agg.get("total_current_balance") or 0.0
    buffer = 3 * (agg.get("monthly_avg_spend") or 0.0)
    return round(max(0.0, liquid - buffer), 2)


def _loan_scenarios(*, price: float, existing: float, user_months: float, user_dp_pct: float,
                    surplus: float, cuts: float, rate: float, tenure: int,
                    deployable: float = 0.0,
                    extra_upfront: float = 0.0, down_label: str = "down payment",
                    asset: str = "purchase",
                    instrument: str = "Recurring Deposit or Liquid MF") -> List[Dict]:
    """
    Three DYNAMIC scenarios that RESPECT the user's timeline. Levers tried in order:
      1. deploy idle liquid funds as a lump-sum head-start on the down payment;
      2. raise the down payment % so the EMI fits the monthly capacity;
      3. keep the timeline; stretch only MODESTLY (≤1.5x) if no down payment works;
      4. if it still doesn't fit, right-size the purchase.
        A 'Your Plan'   — exactly the user's inputs (no fund deployment, judged honestly).
        B 'Recommended' — SOLVED to be feasible: deploys spare funds + adjusts the down payment,
                          keeping the timeline (or a modest extension). Always shows the down
                          payment split, EMI, total interest and total cost.
        C 'Right-Size'  — biggest purchase that fits the ORIGINAL timeline (or "buy sooner").
    """
    surplus = max(surplus, 0.0)
    cuts = max(cuts, 0.0)
    price = max(price, 0.0)
    deployable = max(deployable, 0.0)
    user_months = max(1, int(round(user_months)))
    cap = surplus + cuts                      # realistic monthly capacity (discretionary trimmed)
    cuts_note = f" (with ₹{round(cuts):,}/mo spending cuts)" if cuts > 0 else ""
    max_months = _max_stretch_months(user_months)

    def make(tag, label, recommended, dp_pct, months, capacity, P, head_start):
        dp_pct = min(max(dp_pct, 0.0), 100.0)
        dp_amt = round(P * dp_pct / 100.0, 2)
        loan = round(max(0.0, P - dp_amt), 2)
        emi = round(_calc_emi(loan, rate, tenure), 2) if loan > 0 else 0.0
        months = max(1, int(months))
        upfront_need = dp_amt + extra_upfront
        available = existing + head_start
        lump = round(min(upfront_need, available), 2)          # funded now from spare cash/savings
        to_save = round(max(0.0, upfront_need - lump), 2)      # the rest, saved monthly
        save = round(to_save / months, 2)
        interest = round(emi * tenure - loan, 2) if loan > 0 else 0.0
        return {
            "tag": tag, "label": label, "recommended": recommended,
            "purchase_price": round(P, 2),
            "down_payment_pct": round(dp_pct, 1),
            "down_payment_amount": dp_amt,
            "down_payment_from_existing": lump,
            "down_payment_from_savings": to_save,
            "loan_amount": loan,
            "loan_tenure_months": tenure if loan > 0 else 0,
            "estimated_emi": emi,
            "monthly_post_purchase": emi,
            "total_interest_paid": interest,
            "total_cost_of_ownership": round(P + interest + extra_upfront, 2),
            "timeline_months": months,
            "monthly_savings_needed": save,
            "feasible": (save <= capacity + 1) and (emi <= capacity + 1),
            "shortfall_per_month": round(max(0.0, save - capacity), 2),
            "recommended_instrument": instrument,
        }

    def feasible_band(months, capacity, available):
        """[dp_lo, dp_hi] of down-payment % that keeps BOTH EMI and monthly saving within capacity,
        after using `available` (existing + deployable spare funds) as a head-start."""
        c = capacity * _CAP_UTIL
        max_loan = _inv_emi(c, rate, tenure)
        dp_lo = max(0.0, (price - max_loan) / price * 100.0) if price else 0.0                       # EMI fits
        dp_hi = ((c * months + available - extra_upfront) / price * 100.0) if price else 100.0       # saving fits
        return dp_lo, min(100.0, dp_hi)

    # A — user's exact plan, no fund deployment, judged honestly against base surplus
    sc_a = make("A", f"Your Plan — {user_dp_pct:.0f}% {down_label} over {user_months} months",
                False, user_dp_pct, user_months, surplus, price, 0.0)

    # B — SOLVE for feasibility: deploy spare funds, raise the down payment so the EMI fits, keep
    #     the timeline (modest stretch only if no down payment works at all).
    avail_b = existing + deployable
    months_b = user_months
    dp_lo, dp_hi = feasible_band(months_b, cap, avail_b)
    while dp_lo > dp_hi + 0.01 and months_b < max_months:
        months_b = min(months_b + 3, max_months)
        dp_lo, dp_hi = feasible_band(months_b, cap, avail_b)
    if dp_lo <= dp_hi + 0.01:
        dp_b = min(max(user_dp_pct, dp_lo), dp_hi)        # honour the user's % unless EMI forces higher
        deploy_note = f", deploy {_inr(deployable)} now" if deployable > 0 else ""
        ext = "" if months_b == user_months else f" ({months_b-user_months}-month extension)"
        label_b = f"Keep this {asset} — {dp_b:.0f}% {down_label} over {months_b} months{ext}{deploy_note}{cuts_note}"
        sc_b = make("B", label_b, False, dp_b, months_b, cap, price, deployable)
    else:
        dp_b = min(100.0, max(user_dp_pct, dp_lo))
        sc_b = make("B", f"Keep this {asset} — a stretch even at {max_months} months on your budget{cuts_note}",
                    False, dp_b, max_months, cap, price, deployable)

    # C — RIGHT-SIZE: biggest purchase that fits the ORIGINAL timeline (deploying spare funds too).
    dp_frac = min(max(user_dp_pct / 100.0, 0.0), 1.0)
    c = cap * _CAP_UTIL
    avail_c = existing + deployable
    price_by_save = ((c * user_months + avail_c - extra_upfront) / dp_frac) if dp_frac > 0 else float("inf")
    price_by_emi = (_inv_emi(c, rate, tenure) / (1 - dp_frac)) if dp_frac < 1 else float("inf")
    price_c = max(0.0, min(price_by_save, price_by_emi))
    price_c_capped = min(price_c, price)
    out_of_reach = price > 0 and price_c < price * _TARGET_FLOOR_FRAC
    if price_c >= price * 0.98:
        need = max(0.0, price * dp_frac + extra_upfront - avail_c)
        months_fast = max(1, math.ceil(need / c)) if c > 0 else user_months
        sc_c = make("C", f"Buy Sooner — same {asset} in {months_fast} months{cuts_note}",
                    False, user_dp_pct, months_fast, cap, price, deployable)
    elif out_of_reach:
        sc_c = make("C", f"Most you can finance — a {_inr(price_c_capped)} {asset} (your {_inr(price)} target is out of reach in {user_months} months){cuts_note}",
                    False, user_dp_pct, user_months, cap, price_c_capped, deployable)
    else:
        sc_c = make("C", f"Right-Size — a {_inr(price_c_capped)} {asset} fits your {user_months}-month timeline{cuts_note}",
                    False, user_dp_pct, user_months, cap, price_c_capped, deployable)

    # Recommend the plan that actually WORKS.
    (sc_b if sc_b["feasible"] else sc_c)["recommended"] = True
    meta = {"max_financeable_target": round(price_c_capped, 2), "target_out_of_reach": bool(out_of_reach)}
    return [sc_a, sc_b, sc_c], meta


def _savings_scenarios(*, target: float, existing: float, user_months: float,
                       surplus: float, cuts: float, instrument: str, asset: str = "goal",
                       annual_return_pct: float = _SAVINGS_RETURN_PCT) -> tuple:
    """
    Three DYNAMIC scenarios for a cash (no-loan) goal, respecting the user's timeline.
    Money invested for >12 months GROWS, so the monthly contribution needed for long goals is
    the SIP amount (lower than a flat gap/months). Short goals (<=12 months) and 0%-return goals
    (e.g. an emergency fund kept liquid) stay linear.
      A 'Your Plan'   — your timeline.
      B 'Recommended' — keep the timeline if the monthly fits surplus + cuts; else stretch
                        MODESTLY (bounded) to the soonest feasible point.
      C 'Right-Size'  — the largest target reachable within the original timeline (or, if it
                        already fits, the soonest the user could reach it).
    """
    surplus = max(surplus, 0.0)
    cuts = max(cuts, 0.0)
    user_months = max(1, int(round(user_months)))
    cap = surplus + cuts
    c = cap * _CAP_UTIL
    r = annual_return_pct / 100.0
    grows = annual_return_pct > 0
    cuts_note = f" (with ₹{round(cuts):,}/mo spending cuts)" if cuts > 0 else ""
    max_months = _max_stretch_months(user_months)

    def _monthly_for(target_amt, months):
        """Monthly contribution needed to reach target_amt from `existing` over `months`."""
        if months > _RETURN_MIN_MONTHS and grows:
            existing_fv = _corpus_growth(existing, 0.0, r, months)
            need = max(0.0, target_amt - existing_fv)
            return round(_monthly_sip_for_corpus(need, annual_return_pct, months), 2)
        return round(max(0.0, target_amt - existing) / months, 2)

    def _reachable(months):
        """Largest target reachable from `existing` over `months` at full capacity c."""
        if months > _RETURN_MIN_MONTHS and grows:
            return _corpus_growth(existing, c, r, months)
        return existing + c * months

    def build(tag, label, recommended, target_amt, months, capacity):
        months = max(1, int(months))
        save = _monthly_for(target_amt, months)
        return {
            "tag": tag, "label": label, "recommended": recommended,
            "timeline_months": months,
            "monthly_savings_needed": save,
            "target_amount": round(target_amt, 2),
            "gap": round(max(0.0, target_amt - existing), 2),
            "assumed_annual_return_pct": annual_return_pct,
            "feasible": save <= capacity + 1,
            "shortfall_per_month": round(max(0.0, save - capacity), 2),
            "recommended_instrument": instrument,
        }

    # A — your plan
    sc_a = build("A", f"Your Plan — {user_months} months", False, target, user_months, surplus)

    # B — keep the timeline if it fits; else stretch MODESTLY (capped ~1.5x) to the soonest point
    months_b = user_months
    while c > 0 and _monthly_for(target, months_b) > c and months_b < max_months:
        months_b += 1
    if months_b == user_months:
        label_b = f"Keep this target — your {user_months}-month timeline{cuts_note}"
    else:
        label_b = f"Keep this target — {months_b} months (a {months_b-user_months}-month extension){cuts_note}"
    sc_b = build("B", label_b, False, target, months_b, cap)

    # C — right-size the target to the original timeline (or reach sooner if it already fits)
    reachable = _reachable(user_months)
    affordable_target = round(min(reachable, target), 2)
    out_of_reach = target > 0 and affordable_target < target * _TARGET_FLOOR_FRAC
    if reachable >= target * 0.98:
        months_fast = user_months
        while c > 0 and _monthly_for(target, months_fast) <= c and months_fast > 1:
            months_fast -= 1
        months_fast = min(months_fast + 1, user_months)  # smallest months that still fits
        sc_c = build("C", f"Reach Sooner — same target in {months_fast} months{cuts_note}",
                     False, target, months_fast, cap)
    elif out_of_reach:
        sc_c = build("C", f"Most you can save — {_inr(affordable_target)} (your {_inr(target)} target is out of reach in {user_months} months){cuts_note}",
                     False, affordable_target, user_months, cap)
    else:
        sc_c = build("C", f"Right-Size — a {_inr(affordable_target)} target fits your {user_months}-month timeline{cuts_note}",
                     False, affordable_target, user_months, cap)

    # Recommend whichever actually works within the user's (modestly stretched) timeline.
    (sc_b if sc_b["feasible"] else sc_c)["recommended"] = True
    meta = {"max_financeable_target": affordable_target, "target_out_of_reach": bool(out_of_reach)}
    return [sc_a, sc_b, sc_c], meta


def _education_scenarios(*, cost: float, existing: float, user_months: float, self_pct: float,
                         surplus: float, cuts: float, deployable: float,
                         rate: float = 10.5, tenure: int = 180) -> tuple:
    """
    Education NEVER scales the program cost — a PhD/MS/MBA costs what it costs. Every scenario
    funds the FULL program; the only lever is the FINANCING STRUCTURE.

    Education loans are financed almost entirely by debt (up to 100%), with a moratorium during
    study and repayment from HIGHER post-graduation income. So feasibility depends ONLY on whether
    the self-funded slice (paid during study from surplus + short-term cuts) is achievable — it is
    NOT constrained by whether the loan EMI fits today's surplus.

        A 'Your Plan'              — the user's stated self-funded / loan mix.
        B 'Maximise the loan'  (RECOMMENDED) — minimal upfront self-funding (<=5% of cost, capped
                                   by available cash), loan covers the remaining ~95-100%.
        C 'Minimise the loan'      — self-fund the most you can during study → smaller loan, less
                                   interest.
    The program is never "out of reach": financing changes, not the program cost (spec #17).
    """
    surplus = max(surplus, 0.0); cuts = max(cuts, 0.0); cost = max(cost, 0.0)
    deployable = max(deployable, 0.0)
    user_months = max(1, int(round(user_months)))
    avail = existing + deployable
    cuts_note = f" (with ₹{round(cuts):,}/mo spending cuts)" if cuts > 0 else ""
    # The self-funded portion is paid DURING study (surplus + short-term spending cuts).
    save_cap = (surplus + cuts) * _CAP_UTIL
    yrs = max(1, tenure // 12)

    def make(tag, label, recommended, self_amt, months):
        months = max(1, int(months))
        self_amt = min(max(self_amt, 0.0), cost)
        loan_amt = round(max(0.0, cost - self_amt), 2)
        emi = round(_calc_emi(loan_amt, rate, tenure), 2) if loan_amt > 0 else 0.0
        lump = round(min(self_amt, avail), 2)
        to_save = round(max(0.0, self_amt - lump), 2)
        save = round(to_save / months, 2)
        interest = round(emi * tenure - loan_amt, 2) if loan_amt > 0 else 0.0
        return {
            "tag": tag, "label": label, "recommended": recommended,
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
            "monthly_savings_needed": save,
            # Feasibility = can the SELF-FUNDED slice be saved during study? Repayment of the loan
            # happens after graduation from higher income, so the EMI is NOT an affordability gate.
            "feasible": save <= save_cap + 1,
            "shortfall_per_month": round(max(0.0, save - save_cap), 2),
            "recommended_instrument": "Education loan + SIP in debt/liquid MF for the self-funded portion",
        }

    # A — user's stated mix
    sc_a = make("A", f"Your Plan — {self_pct:.0f}% self-funded over {user_months} months",
                False, cost * self_pct / 100.0, user_months)

    # B (RECOMMENDED) — MAXIMISE the loan: self-fund only a minimal upfront slice (<=5% of cost,
    #   capped by available cash); the education loan covers the rest over a {yrs}-year tenure.
    self_b = min(avail, cost * _EDU_MIN_SELF_FRAC)
    loan_pct_b = (cost - self_b) / cost * 100 if cost else 0
    sc_b = make("B", f"Maximise the education loan — {loan_pct_b:.0f}% financed over a {yrs}-year loan{cuts_note}",
                True, self_b, user_months)

    # C — minimise the debt: self-fund the most you can during study → smaller loan, less interest.
    self_c = min(cost, avail + save_cap * user_months)
    sc_c = make("C", f"Minimise the loan — self-fund {self_c / cost * 100:.0f}%, pay less interest{cuts_note}" if cost else "Minimise the loan",
                False, self_c, user_months)

    # B is ALWAYS the recommended route — that's how education is normally financed. Its own
    # `feasible` flag reflects whether the minimal self-funded slice is achievable during study.
    meta = {"max_financeable_target": round(cost, 2), "target_out_of_reach": False}
    return [sc_a, sc_b, sc_c], meta


# ── Type-specific planners ────────────────────────────────────────────────────

def _plan_gadget(goal: dict, agg: dict) -> dict:
    target   = _parse_amount(goal.get("target_amount")) or 0.0
    existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    months   = _months_from_timeline(goal.get("timeline")) or 6.0
    net      = agg["monthly_net_flow"]
    cuts     = agg.get("total_spending_cuts", 0.0)
    scenarios, meta = _savings_scenarios(target=target, existing=existing, user_months=months,
                                   surplus=net, cuts=cuts,
                                   instrument="Liquid Mutual Fund or high-yield savings account")
    rec = next(s for s in scenarios if s["recommended"])
    return {
        "purchase_price": target, "existing_savings": existing, "gap": round(max(0.0, target - existing), 2),
        "monthly_savings_needed": rec["monthly_savings_needed"],
        "recommended_timeline_months": rec["timeline_months"],
        "feasible": rec["feasible"],
        "shortfall_per_month": rec["shortfall_per_month"],
        "recommended_instrument": "Liquid Mutual Fund or high-yield savings account",
        **meta,
        "scenarios": scenarios,
    }


def _plan_car(goal: dict, agg: dict) -> dict:
    price    = _parse_amount(goal.get("target_amount")) or 0.0
    existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    months   = _months_from_timeline(goal.get("timeline")) or 18.0
    pref     = str(goal.get("financing_preference") or "loan").lower()
    user_dp  = _num(goal.get("down_payment_pct"), 100 if "cash" in pref else 30)
    net      = agg["monthly_net_flow"]
    cuts     = agg.get("total_spending_cuts", 0.0)

    scenarios, meta = _loan_scenarios(
        price=price, existing=existing, user_months=months, user_dp_pct=user_dp,
        surplus=net, cuts=cuts, deployable=_deployable(agg),
        rate=10.0, tenure=60, down_label="down payment", asset="car",
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
        "note": "EMI at 10% p.a., 5-year tenure. Verify current rates with your bank.",
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
    net       = agg["monthly_net_flow"]

    cuts = agg.get("total_spending_cuts", 0.0)
    scenarios, meta = _savings_scenarios(target=total, existing=existing, user_months=months,
                                   surplus=net, cuts=cuts,
                                   instrument="Liquid Mutual Fund (instant redemption)")
    rec = next(s for s in scenarios if s["recommended"])
    return {
        "trip_cost_total": round(total, 2), "per_person_cost": round(base_cost, 2),
        "travelers": travelers, "existing_savings": existing,
        "gap": round(max(0.0, total - existing), 2),
        "monthly_savings_needed": rec["monthly_savings_needed"],
        "recommended_timeline_months": rec["timeline_months"],
        "feasible": rec["feasible"],
        "shortfall_per_month": rec["shortfall_per_month"],
        "recommended_instrument": "Liquid Mutual Fund (instant redemption)",
        **meta,
        "scenarios": scenarios,
    }


def _plan_emergency_fund(goal: dict, agg: dict) -> dict:
    user_cov  = _num(goal.get("target_months_coverage"), 6)
    current   = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    spend     = agg["monthly_avg_spend"]
    net       = agg["monthly_net_flow"]
    cuts      = agg.get("total_spending_cuts", 0.0)
    target    = round(spend * user_cov, 2)
    user_months = _months_from_timeline(goal.get("timeline")) or 12.0

    # An emergency fund must stay instantly accessible — assume no growth (kept liquid).
    scenarios, meta = _savings_scenarios(target=target, existing=current, user_months=user_months,
                                   surplus=net, cuts=cuts, annual_return_pct=0.0,
                                   instrument="High-yield savings account + Liquid MF (instant access)")
    rec = next(s for s in scenarios if s["recommended"])
    return {
        "monthly_expense_baseline": spend,
        "target_coverage_months": user_cov,
        "emergency_fund_target": target,
        "current_emergency_savings": current,
        "gap": round(max(0.0, target - current), 2),
        "monthly_savings_needed": rec["monthly_savings_needed"],
        "recommended_timeline_months": rec["timeline_months"],
        "feasible": rec["feasible"],
        "shortfall_per_month": rec["shortfall_per_month"],
        "recommended_instrument": "High-yield savings account + Liquid MF (instant access)",
        **meta,
        "scenarios": scenarios,
    }


def _plan_house(goal: dict, agg: dict) -> dict:
    prop     = _parse_amount(goal.get("target_amount")) or 0.0
    user_dp  = _num(goal.get("down_payment_pct"), 20)
    existing = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    months   = _months_from_timeline(goal.get("timeline")) or 36.0
    stamp    = round(prop * 0.07, 2)  # ~7% India stamp duty + registration
    net      = agg["monthly_net_flow"]
    cuts     = agg.get("total_spending_cuts", 0.0)

    scenarios, meta = _loan_scenarios(
        price=prop, existing=existing, user_months=months, user_dp_pct=user_dp,
        surplus=net, cuts=cuts, deployable=_deployable(agg),
        rate=8.5, tenure=240, extra_upfront=stamp,
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
        "note": "Home loan EMI at 8.5% p.a., 20-year tenure. Verify with your bank.",
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

    # Map the user's stated preference to a self-funded % (the rest is an education loan).
    user_self_pct = 0 if ("full" in pref and "loan" in pref) else (50 if "hybrid" in pref else 100)

    # Loan tenure is configurable (10/15/20-year are common); default to 15 years.
    tenure_years = max(1, int(_num(goal.get("loan_tenure_years"), 15)))
    tenure_months = tenure_years * 12

    # Education program cost is FIXED — the lever is the financing mix, not a cheaper "price".
    scenarios, meta = _education_scenarios(
        cost=cost, existing=existing, user_months=months, self_pct=user_self_pct,
        surplus=net, cuts=cuts, deployable=_deployable(agg), tenure=tenure_months,
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
    cur_inv  = _parse_amount(goal.get("target_amount") or goal.get("existing_savings") or 0) or 0.0
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
    worth   = _parse_amount(goal.get("existing_savings") or 0) or 0.0
    net     = agg["monthly_net_flow"]
    cuts    = agg.get("total_spending_cuts", 0.0)
    invest  = max(0.0, (net + cuts) * 0.7)  # 70% of (surplus + reclaimed spending cuts) invested
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
    net      = agg["monthly_net_flow"]
    cuts     = agg.get("total_spending_cuts", 0.0)

    scenarios, meta = _savings_scenarios(target=budget, existing=existing, user_months=months,
                                   surplus=net, cuts=cuts,
                                   instrument="FD ladder + Recurring Deposit (low-risk, accessible)")
    rec = next(s for s in scenarios if s["recommended"])
    return {
        "wedding_budget": budget, "existing_savings": existing,
        "gap": round(max(0.0, budget - existing), 2),
        "monthly_savings_needed": rec["monthly_savings_needed"],
        "recommended_timeline_months": rec["timeline_months"],
        "feasible": rec["feasible"],
        "shortfall_per_month": rec["shortfall_per_month"],
        "recommended_instrument": "FD ladder + Recurring Deposit (low-risk, accessible)",
        **meta,
        "scenarios": scenarios,
    }


def _plan_multi_goal(goal: dict, agg: dict) -> dict:
    sub_goals = goal.get("sub_goals") or []
    net       = agg["monthly_net_flow"]
    investable = max(0.0, net * 0.8)

    planned = []
    total_needed = 0.0
    for sg in sub_goals:
        target  = _parse_amount(sg.get("target_amount")) or 0.0
        ex      = _parse_amount(sg.get("existing_savings") or 0) or 0.0
        mo      = _months_from_timeline(sg.get("timeline"))
        if target and mo and mo > 0:
            ms = max(0.0, round((target - ex) / mo, 2))
            total_needed += ms
            planned.append({
                "description": sg.get("description"),
                "goal_type": sg.get("goal_type", "generic"),
                "target_amount": target, "timeline_months": mo,
                "monthly_savings_needed": ms,
            })
    planned.sort(key=lambda x: x.get("timeline_months") or float("inf"))

    def _allocate(strategy: str) -> list:
        result = []
        for i, p in enumerate(planned):
            if strategy == "sequential":
                alloc = p["monthly_savings_needed"] if i == 0 else 0.0
            elif strategy == "parallel":
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
    net      = agg["monthly_net_flow"]
    cuts     = agg.get("total_spending_cuts", 0.0)
    scenarios, meta = _savings_scenarios(target=target, existing=existing, user_months=months,
                                   surplus=net, cuts=cuts,
                                   instrument="Liquid MF or FD based on timeline")
    rec = next(s for s in scenarios if s["recommended"])
    return {
        "target_amount": target, "existing_savings": existing, "gap": round(max(0.0, target - existing), 2),
        "monthly_savings_needed": rec["monthly_savings_needed"],
        "recommended_timeline_months": rec["timeline_months"],
        "feasible": rec["feasible"],
        "shortfall_per_month": rec["shortfall_per_month"],
        "recommended_instrument": "Liquid MF or FD based on timeline",
        **meta,
        "scenarios": scenarios,
    }


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

def goal_planner_tool(state: AgentState) -> dict:
    user_id   = state.get("user_id") or ""
    task      = state.get("brain_task") or {}
    goal      = task.get("goal") or {}
    evidence  = state.get("evidence") or []

    # Financial baseline: monthly aggregates + LIQUID balance (credit cards excluded).
    agg          = _compute_monthly_aggregates(user_id)
    balance_info = _get_account_balances(user_id)
    agg["total_current_balance"] = balance_info["liquid_balance"]

    # Spending reduction opportunities — computed BEFORE the planner so scenario C can use the
    # total potential cut to build an "accelerated" feasible plan.
    spending_cats = _extract_spending_categories(evidence)
    if not spending_cats:
        spending_cats = _compute_category_breakdown(user_id, agg["months_observed"])
    spend_ops = _spending_reduction_opportunities(spending_cats) if spending_cats else []
    agg["total_spending_cuts"] = round(sum(o.get("potential_saving", 0) for o in spend_ops), 2)

    # Run type-specific planner
    goal_type = str(goal.get("goal_type") or "generic").lower().strip()
    planner   = _GOAL_PLANNERS.get(goal_type, _plan_generic)
    extra     = planner(goal, agg)

    if spend_ops:
        extra["spending_reduction_opportunities"] = spend_ops
        extra["spending_by_category"] = spending_cats

    # Investment liquidity check — prefer investment evidence, else fetch directly.
    inv_data = _extract_investment_data(evidence) or _fetch_investment_holdings(user_id)
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
        "goal_description": goal.get("description"),
        "target_amount": target_amount,
        "timeline": goal.get("timeline"),
        "timeline_months": _months_from_timeline(goal.get("timeline")),
        # Financial baseline (real, from the database)
        "monthly_avg_spend": agg["monthly_avg_spend"],
        "monthly_avg_income": agg["monthly_avg_income"],
        "monthly_net_flow": agg["monthly_net_flow"],
        "income_source": agg.get("income_source"),
        "liquid_balance": agg.get("total_current_balance"),
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
    summary = (
        f"Goal '{goal_type}' — target=₹{data.get('target_amount')}, "
        f"timeline={goal.get('timeline')}, monthly_needed=₹{ms}, "
        f"net_flow=₹{agg['monthly_net_flow']}, feasible={extra.get('feasible')}, "
        f"scenarios={len(extra.get('scenarios') or [])}"
    )
    logger.info("[goal_planner] %s", summary)

    return {
        "evidence": [{"tool": "goal_planner", "task": task.get("sub_question") or state.get("user_query"),
                      "summary": summary, "data": data}],
        "sources": ["Supabase Transactions", "Goal Planner"],
    }
