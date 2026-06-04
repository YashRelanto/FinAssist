"""
SQL Executor — Executes validated SQL against Supabase database.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List

from app.graph.state import AgentState
from app.utils.supabase_client import supabase
from app.graph.schema_registry import SCHEMA_REGISTRY

logger = logging.getLogger(__name__)


def run_query_builder_fallback(ast: Dict[str, Any], user_id: str) -> List[Dict[str, Any]]:
    """
    Translates the SQL AST back to a PostgREST query chain as a fallback.
    """
    if not ast:
        return []

    tables = ast.get("tables") or [ast.get("table", "transactions")]
    table_name = tables[0]

    # Join categories table if categories are joined in AST
    has_categories_join = False
    for join in ast.get("joins", []):
        if join.get("table") == "categories":
            has_categories_join = True
            break

    select_clause = "*, categories(main_category)" if has_categories_join else "*"
    query = supabase.table(table_name).select(select_clause)

    # Inject user_id filter automatically for user_scoped tables
    # (should already be validated/planned, but safe fallback)
    query = query.eq("user_id", user_id)

    # Apply additional filters from AST
    for f in ast.get("filters", []):
        col = f.get("column", "")
        if "." in col:
            col = col.split(".")[-1]

        if col == "user_id":
            continue  # Already applied

        op = str(f.get("op", "=")).upper().strip()
        val = f.get("value")

        # Parse stringified lists
        if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
            import json
            try:
                val = json.loads(val)
            except Exception:
                val = [v.strip().strip("'").strip('"') for v in val[1:-1].split(",") if v.strip()]

        if isinstance(val, str):
            val = val.replace("{{user_id}}", user_id).replace("{user_id}", user_id)

        if op == "=":
            if isinstance(val, list):
                if len(val) == 1:
                    query = query.eq(col, val[0])
                else:
                    query = query.in_(col, val)
            else:
                query = query.eq(col, val)
        elif op == "!=":
            if isinstance(val, list):
                query = query.neq(col, val) # Or multiple neq, standard is single
            else:
                query = query.neq(col, val)
        elif op == ">":
            query = query.gt(col, val)
        elif op == ">=":
            query = query.gte(col, val)
        elif op == "<":
            query = query.lt(col, val)
        elif op == "<=":
            query = query.lte(col, val)
        elif op in ("LIKE", "ILIKE"):
            if isinstance(val, str):
                val_clean = val.replace("%", "")
            else:
                val_clean = val
            query = query.ilike(col, val_clean)
        elif op == "IN":
            if not isinstance(val, list):
                val = [val]
            query = query.in_(col, val)

    # Ordering
    for o in ast.get("order_by", []):
        col = o.get("column", "")
        if "." in col:
            col = col.split(".")[-1]

        allowed_cols = SCHEMA_REGISTRY.get(table_name, {}).get("columns", [])
        if col not in allowed_cols:
            logger.warning("[SQL Executor] Skipping order_by on alias/invalid column '%s'", col)
            if "amount" in allowed_cols:
                query = query.order("amount", desc=True)
            continue

        direction = str(o.get("direction", "DESC")).upper().strip()
        query = query.order(col, desc=(direction == "DESC"))

    # Limit
    limit_val = ast.get("limit")
    if limit_val is not None:
        query = query.limit(limit_val)
    else:
        query = query.limit(50)

    res = query.execute()
    return res.data or []


def sql_executor(state: AgentState) -> dict:
    """
    Executes raw SQL query using RPC, falling back to query builder.
    """
    sql_query = state.get("sql_query")
    sql_ast = state.get("sql_ast") or {}
    user_id = state.get("user_id") or ""
    sql_valid = state.get("sql_valid", True)

    if not sql_valid:
        logger.warning("[Node:sql_executor] Skipping execution due to validation errors")
        return {
            "sql_results": [],
            "sql_error": "SQL validation failed: " + ", ".join(state.get("sql_validation_errors", [])),
        }

    if not sql_query:
        logger.info("[Node:sql_executor] No SQL query to execute")
        return {"sql_results": []}

    results = []
    error_msg = None

    try:
        # Check if comparison dual query
        if isinstance(sql_query, dict):
            # Query A
            try:
                res_a = supabase.rpc("execute_sql", {"sql_query": sql_query["query_a"]}).execute()
                data_a = res_a.data or []
            except Exception:
                logger.info("[Node:sql_executor] RPC failed for comparison query_a, falling back to query builder")
                data_a = run_query_builder_fallback(sql_ast["query_a"], user_id)

            for r in data_a:
                if isinstance(r, dict):
                    r["comparison_target"] = sql_ast["query_a"].get("comparison_target") or "target_a"

            # Query B
            try:
                res_b = supabase.rpc("execute_sql", {"sql_query": sql_query["query_b"]}).execute()
                data_b = res_b.data or []
            except Exception:
                logger.info("[Node:sql_executor] RPC failed for comparison query_b, falling back to query builder")
                data_b = run_query_builder_fallback(sql_ast["query_b"], user_id)

            for r in data_b:
                if isinstance(r, dict):
                    r["comparison_target"] = sql_ast["query_b"].get("comparison_target") or "target_b"

            results = data_a + data_b  # Combined results with labels
        else:
            # Single query
            try:
                res = supabase.rpc("execute_sql", {"sql_query": sql_query}).execute()
                results = res.data or []
            except Exception:
                logger.info("[Node:sql_executor] RPC failed for single query, falling back to query builder")
                results = run_query_builder_fallback(sql_ast, user_id)

    except Exception as exc:
        logger.error("[Node:sql_executor] Supabase execution failed: %s", exc)
        error_msg = str(exc)
        results = []

    return {
        "sql_results": results,
        "sql_error": error_msg,
    }
