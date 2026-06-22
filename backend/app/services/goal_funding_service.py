"""Resolve the live value of money sources linked to a savings goal.

A goal's ``funding_sources`` is a list of ``{type, id, name}`` entries where:
  - ``mutual_fund``  -> id is the scheme_code (current value = units * live NAV)
  - ``fixed_deposit``-> id is the fd_id (current value = accrued FD value today)
  - ``account``      -> id is the account_id (current value = current_balance)

The funded amount of a goal is the sum of the current value of every linked source,
so updating any source (NAV move, FD accrual, balance edit) is reflected automatically.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from app.services.accounts_service import fetch_user_accounts
from app.utils.supabase_client import supabase

VALID_SOURCE_TYPES = {"mutual_fund", "fixed_deposit", "account"}


def normalize_funding_sources(raw: Any) -> list[dict[str, str]]:
    """Coerce stored/incoming funding_sources into a clean list of {type, id, name}."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, list):
        return []

    cleaned: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        s_type = str(item.get("type") or "").strip()
        s_id = str(item.get("id") or "").strip()
        if s_type not in VALID_SOURCE_TYPES or not s_id:
            continue
        key = (s_type, s_id)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"type": s_type, "id": s_id, "name": str(item.get("name") or "")})
    return cleaned


def _fetch_live_nav(scheme_code: str) -> float:
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as response:
        parsed = json.loads(response.read().decode())
    nav_list = parsed.get("data", []) if isinstance(parsed, dict) else []
    if nav_list:
        return float(nav_list[0]["nav"])
    return 0.0


def _mutual_fund_values(user_id: str) -> dict[str, dict[str, Any]]:
    """{scheme_code: {current_value, name}} using live NAV with purchase-NAV fallback."""
    res = supabase.table("investments").select("*").eq("user_id", user_id).execute()
    rows = res.data or []
    by_scheme: dict[str, dict[str, Any]] = {}
    for inv in rows:
        code = str(inv.get("scheme_code") or "")
        if not code:
            continue
        agg = by_scheme.setdefault(
            code, {"qty": 0.0, "invested": 0.0, "name": inv.get("scheme_name") or code}
        )
        qty = float(inv.get("quantity") or 0)
        agg["qty"] += qty
        agg["invested"] += qty * float(inv.get("purchase_nav") or 0)

    values: dict[str, dict[str, Any]] = {}
    for code, agg in by_scheme.items():
        if agg["qty"] <= 0:
            continue
        nav = 0.0
        try:
            nav = _fetch_live_nav(code)
        except Exception as exc:
            print(f"[goal_funding] live NAV fetch failed for {code}: {exc}")
        # No live NAV (just-added scheme or transient miss) -> neutral value at avg purchase NAV.
        if nav <= 0:
            nav = agg["invested"] / agg["qty"] if agg["qty"] else 0.0
        values[code] = {
            "current_value": round(agg["qty"] * nav, 2),
            "name": agg["name"],
        }
    return values


def _fixed_deposit_values(user_id: str) -> dict[str, dict[str, Any]]:
    """{fd_id: {current_value, name}} from accrued FD value today."""
    from app.graph.tools.goal_planner_tool import _fd_metrics

    res = (
        supabase.table("fixed_deposits")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )
    values: dict[str, dict[str, Any]] = {}
    for fd in res.data or []:
        fd_id = str(fd.get("fd_id") or "")
        if not fd_id:
            continue
        metrics = _fd_metrics(fd)
        label = fd.get("label") or fd.get("bank_name") or "Fixed Deposit"
        values[fd_id] = {
            "current_value": float(metrics["current_value"]),
            "name": str(label),
        }
    return values


def _account_values(user_id: str) -> dict[str, dict[str, Any]]:
    """{account_id: {current_value, name}} from the account's current balance."""
    values: dict[str, dict[str, Any]] = {}
    for acc in fetch_user_accounts(user_id):
        acc_id = str(acc.get("account_id") or "")
        if not acc_id:
            continue
        values[acc_id] = {
            "current_value": float(acc.get("current_balance") or 0),
            "name": str(acc.get("account_name") or "Account"),
        }
    return values


def fetch_source_values(user_id: str, needed_types: set[str]) -> dict[str, dict[str, dict[str, Any]]]:
    """Live value snapshot for every requested source type, keyed by source id.

    Only the requested types are queried so goals without (e.g.) MF links never trigger
    a NAV network call.
    """
    out: dict[str, dict[str, dict[str, Any]]] = {
        "mutual_fund": {},
        "fixed_deposit": {},
        "account": {},
    }
    if not user_id:
        return out
    try:
        if "mutual_fund" in needed_types:
            out["mutual_fund"] = _mutual_fund_values(user_id)
        if "fixed_deposit" in needed_types:
            out["fixed_deposit"] = _fixed_deposit_values(user_id)
        if "account" in needed_types:
            out["account"] = _account_values(user_id)
    except Exception as exc:
        print(f"[goal_funding] source value fetch error: {exc}")
    return out


def compute_funded_amount(
    funding_sources: list[dict[str, str]],
    source_values: dict[str, dict[str, dict[str, Any]]],
) -> tuple[float, list[dict[str, Any]]]:
    """Total live value of a goal's linked sources plus a per-source breakdown."""
    total = 0.0
    breakdown: list[dict[str, Any]] = []
    for src in funding_sources:
        s_type = src.get("type", "")
        s_id = src.get("id", "")
        info = source_values.get(s_type, {}).get(s_id)
        value = float(info["current_value"]) if info else 0.0
        total += value
        breakdown.append(
            {
                "type": s_type,
                "id": s_id,
                "name": (info or {}).get("name") or src.get("name") or "",
                "current_value": round(value, 2),
                "available": info is not None,
            }
        )
    return round(total, 2), breakdown


def needed_types_for_goals(goals: list[dict[str, Any]]) -> set[str]:
    needed: set[str] = set()
    for goal in goals:
        for src in normalize_funding_sources(goal.get("funding_sources")):
            needed.add(src["type"])
    return needed
