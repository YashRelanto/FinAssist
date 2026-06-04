"""
NL2SQL Query Executor
=====================
Converts a QuerySpec (produced by query_planner.py) into targeted Supabase
queries and returns pre-computed aggregates + row samples.

Design principles:
  - All filtering happens at the DB layer (Supabase RPC / PostgREST).
  - Python-side aggregation is used for sum/count/average/max/min so we
    never ask the LLM to do arithmetic.
  - Category matching supports both main_category and sub_category lookups
    to handle natural-language category names like "food" or "groceries".
  - The returned dict is deliberately compact — only what the answer
    generator needs.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.utils.supabase_client import supabase

logger = logging.getLogger(__name__)

# ─── Type alias ──────────────────────────────────────────────────────────────

QuerySpec = Dict[str, Any]
ExecutionResult = Dict[str, Any]

# Maximum rows to fetch for list/detail queries
_LIST_FETCH_LIMIT = 50

# Maximum rows to return in the result payload (for the answer prompt)
_RESULT_SAMPLE_SIZE = 15


# ─── Category ID Resolver ─────────────────────────────────────────────────────

def _resolve_category_ids(category_name: str) -> List[str]:
    """
    Given a natural-language category string (e.g. "food", "groceries",
    "Food & Drinks"), return a list of matching category_id strings from
    the categories table.

    Matching strategy:
      1. Exact sub_category match (case-insensitive)
      2. Partial sub_category match
      3. Exact main_category match (returns ALL sub-category IDs under it)
      4. Partial main_category match
    """
    try:
        cat_rows = supabase.table("categories").select("id, category_name").execute()
        rows = cat_rows.data or []
    except Exception as e:
        logger.warning("[QueryExecutor] Failed to fetch categories: %s", e)
        return []

    name_lower = category_name.lower().strip()

    # Try to pull main_category and sub_category from each row.
    # The schema exposes a single 'category_name' column in the plan spec,
    # but the actual table has 'main_category' and 'sub_category'.
    # Re-fetch with both columns.
    try:
        cat_rows = (
            supabase.table("categories")
            .select("id, main_category, sub_category")
            .execute()
        )
        rows = cat_rows.data or []
    except Exception as e:
        logger.warning("[QueryExecutor] Failed to fetch categories (wide): %s", e)
        return []

    matched_ids: List[str] = []

    # Pass 1: exact sub_category
    for r in rows:
        if (r.get("sub_category") or "").lower() == name_lower:
            matched_ids.append(str(r["id"]))
    if matched_ids:
        return matched_ids

    # Pass 2: partial sub_category
    for r in rows:
        if name_lower in (r.get("sub_category") or "").lower():
            matched_ids.append(str(r["id"]))
    if matched_ids:
        return matched_ids

    # Pass 3: exact main_category
    for r in rows:
        if (r.get("main_category") or "").lower() == name_lower:
            matched_ids.append(str(r["id"]))
    if matched_ids:
        return matched_ids

    # Pass 4: partial main_category
    for r in rows:
        if name_lower in (r.get("main_category") or "").lower():
            matched_ids.append(str(r["id"]))

    return matched_ids


# ─── Supabase Query Builder ───────────────────────────────────────────────────

def _build_and_fetch(user_id: str, spec: QuerySpec) -> List[Dict]:
    """
    Build a Supabase query from the spec and return raw transaction rows.

    Filters applied at DB level:
      - user_id          (always)
      - transaction_type (when spec["transaction_type"] is set)
      - merchant_name    (ilike partial match when spec["merchant"] is set)
      - transaction_date (gte/lte when date_from/date_to are set)
      - category_id      (in list when spec["category"] resolves to IDs)
      - ordering         (by transaction_date desc by default)
      - limit            (capped at _LIST_FETCH_LIMIT for safety)
    """
    query = (
        supabase.table("transactions")
        .select(
            "id, transaction_date, amount, transaction_type, "
            "merchant_name, description, category_id, categories(main_category)"
        )
        .eq("user_id", user_id)
    )

    # ── transaction_type filter ───────────────────────────────────────────
    if spec.get("transaction_type"):
        query = query.eq("transaction_type", spec["transaction_type"])

    # ── merchant filter (case-insensitive partial match) ──────────────────
    if spec.get("merchant"):
        query = query.ilike("merchant_name", f"%{spec['merchant']}%")

    # ── date range filters ────────────────────────────────────────────────
    if spec.get("date_from"):
        query = query.gte("transaction_date", spec["date_from"])
    if spec.get("date_to"):
        query = query.lte("transaction_date", spec["date_to"])

    # ── category filter ───────────────────────────────────────────────────
    if spec.get("category"):
        cat_ids = _resolve_category_ids(spec["category"])
        if cat_ids:
            query = query.in_("category_id", cat_ids)
        else:
            logger.warning(
                "[QueryExecutor] Category '%s' not found in categories table — "
                "skipping category filter", spec["category"]
            )

    # ── ordering ──────────────────────────────────────────────────────────
    sort_val = spec.get("sort", "transaction_date_desc")
    if sort_val == "asc":
        query = query.order("amount", desc=False)
    elif sort_val == "desc":
        query = query.order("amount", desc=True)
    else:
        # Default: newest first
        query = query.order("transaction_date", desc=True)

    # ── limit ─────────────────────────────────────────────────────────────
    fetch_limit = min(spec.get("limit") or _LIST_FETCH_LIMIT, _LIST_FETCH_LIMIT)
    query = query.limit(fetch_limit)

    result = query.execute()
    return result.data or []


# ─── Python-side Aggregators ──────────────────────────────────────────────────

def _aggregate(rows: List[Dict], spec: QuerySpec) -> Dict[str, Any]:
    """
    Compute the requested metric from the fetched rows entirely in Python.
    Returns a dict describing the result.
    """
    metric = spec.get("metric", "list")
    amounts = [r.get("amount", 0) for r in rows]

    if metric == "sum":
        return {"total": round(sum(amounts), 2), "count": len(rows)}

    if metric == "count":
        return {"count": len(rows)}

    if metric == "average":
        avg = round(sum(amounts) / len(amounts), 2) if amounts else 0.0
        return {"average": avg, "count": len(rows)}

    if metric == "max":
        if rows:
            top = max(rows, key=lambda r: r.get("amount", 0))
            return {
                "max_amount": top.get("amount"),
                "transaction": top,
            }
        return {"max_amount": None, "transaction": None}

    if metric == "min":
        if rows:
            bot = min(rows, key=lambda r: r.get("amount", 0))
            return {
                "min_amount": bot.get("amount"),
                "transaction": bot,
            }
        return {"min_amount": None, "transaction": None}

    if metric in {"latest", "list"}:
        return {"count": len(rows)}

    return {}


def _group_aggregate(rows: List[Dict], group_by: str, metric: str) -> List[Dict]:
    """
    Group rows by 'category_id' or 'merchant_name' and aggregate per group.
    Returns a sorted list of {group, total/count, transaction_count}.
    """
    buckets: Dict[str, List[float]] = defaultdict(list)

    for r in rows:
        if group_by == "merchant":
            key = r.get("merchant_name") or r.get("description") or "Unknown"
        else:
            # group_by == "category": extract main_category from joined categories table
            cat_obj = r.get("categories")
            if cat_obj and isinstance(cat_obj, dict):
                key = cat_obj.get("main_category") or r.get("category_id") or "Uncategorized"
            else:
                key = r.get("category_id") or "Uncategorized"
        buckets[key].append(r.get("amount", 0))

    results = []
    for group, amounts in buckets.items():
        entry: Dict[str, Any] = {"group": group, "transaction_count": len(amounts)}
        if metric in {"sum", "list"}:
            entry["total"] = round(sum(amounts), 2)
        elif metric == "average":
            entry["average"] = round(sum(amounts) / len(amounts), 2) if amounts else 0.0
        elif metric == "count":
            entry["count"] = len(amounts)
        results.append(entry)

    # Sort by total descending (fall back to count)
    results.sort(key=lambda x: x.get("total", x.get("count", 0)), reverse=True)
    return results


# ─── Public API ───────────────────────────────────────────────────────────────

async def execute_query(user_id: str, spec: QuerySpec) -> ExecutionResult:
    """
    Execute a QuerySpec against Supabase and return a compact result dict:

      {
        "spec":      QuerySpec,
        "rows":      [up to _RESULT_SAMPLE_SIZE row dicts],
        "aggregate": {metric-specific computed values},
        "groups":    [group-by breakdown list] | [],
        "total_fetched": int,
        "empty": bool,
      }

    Falls back gracefully on Supabase errors.
    """
    try:
        rows = _build_and_fetch(user_id, spec)
    except Exception as e:
        logger.error("[QueryExecutor] Supabase fetch failed: %s", e)
        return {
            "spec": spec,
            "rows": [],
            "aggregate": {},
            "groups": [],
            "total_fetched": 0,
            "empty": True,
            "error": str(e),
        }

    total_fetched = len(rows)
    empty = total_fetched == 0

    # ── Aggregate ─────────────────────────────────────────────────────────
    aggregate = _aggregate(rows, spec)

    # ── Group-by breakdown ────────────────────────────────────────────────
    groups: List[Dict] = []
    if spec.get("group_by") and not empty:
        groups = _group_aggregate(rows, spec["group_by"], spec.get("metric", "sum"))

    # ── Row sample for the answer prompt ─────────────────────────────────
    sample_rows = rows[:_RESULT_SAMPLE_SIZE]

    result: ExecutionResult = {
        "spec": spec,
        "rows": sample_rows,
        "aggregate": aggregate,
        "groups": groups,
        "total_fetched": total_fetched,
        "empty": empty,
    }

    logger.info(
        "[QueryExecutor] metric=%s fetched=%d empty=%s groups=%d",
        spec.get("metric"), total_fetched, empty, len(groups),
    )
    return result
