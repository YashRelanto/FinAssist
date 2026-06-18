"""
SQL Planner — Converts SQL AST dictionaries to raw SQL strings.
"""

from __future__ import annotations

import logging
from typing import Dict, Any
import json

from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def generate_sql(ast: Dict[str, Any], user_id: str) -> str:
    """
    Constructs a SELECT query from a single AST dictionary.
    """
    if not ast:
        return ""

    # Columns selection
    cols = ast.get("columns") or ["*"]
    columns_str = ", ".join(cols)

    # Tables selection
    tables = ast.get("tables") or [ast.get("table", "transactions")]
    from_str = f"FROM {tables[0]}"

    # Joins selection
    joins_list = []
    for join in ast.get("joins", []):
        j_type = join.get("type", "LEFT")
        j_table = join.get("table")
        on_clause = join.get("on") or {}
        if "left" in on_clause and "right" in on_clause:
            left_col = on_clause["left"]
            right_col = on_clause["right"]
        else:
            # Handle simple key-value dict mappings if present
            left_col, right_col = list(on_clause.items())[0]
        joins_list.append(f"{j_type} JOIN {j_table} ON {left_col} = {right_col}")
    joins_str = " ".join(joins_list)

    # Filters (Where clause)
    filters_list = []
    for f in ast.get("filters", []):
        col = f["column"]
        op = str(f.get("op", "=")).upper().strip()
        val = f["value"]

        # Parse stringified lists (e.g. '["uuid-1"]')
        if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
            import json
            try:
                val = json.loads(val)
            except Exception:
                val = [v.strip().strip("'").strip('"') for v in val[1:-1].split(",") if v.strip()]

        if isinstance(val, (list, tuple)):
            if len(val) == 1:
                filters_list.append(f"{col} = '{val[0]}'")
            else:
                items_str = ", ".join(f"'{v}'" for v in val)
                filters_list.append(f"{col} IN ({items_str})")
        elif isinstance(val, str):
            val_str = val.replace("{{user_id}}", user_id).replace("{user_id}", user_id)
            if op == "IN":
                filters_list.append(f"{col} IN ('{val_str}')")
            else:
                filters_list.append(f"{col} {op} '{val_str}'")
        elif val is None:
            if op == "=" or op == "IS":
                filters_list.append(f"{col} IS NULL")
            else:
                filters_list.append(f"{col} IS NOT NULL")
        else:
            filters_list.append(f"{col} {op} {val}")

    where_str = ""
    if filters_list:
        where_str = f"WHERE " + " AND ".join(filters_list)

    # Group by
    group_by_list = ast.get("group_by", [])
    group_by_str = ""
    if group_by_list:
        group_by_str = f"GROUP BY " + ", ".join(group_by_list)

    # Order by
    order_by_list = ast.get("order_by", [])
    order_by_str = ""
    if order_by_list:
        order_clauses = []
        for o in order_by_list:
            col = o["column"]
            direction = o.get("direction", "DESC")
            order_clauses.append(f"{col} {direction}")
        order_by_str = f"ORDER BY " + ", ".join(order_clauses)

    # Limit
    limit_val = ast.get("limit")
    limit_str = ""
    if limit_val is not None:
        limit_str = f"LIMIT {limit_val}"

    # Combine parts
    parts = [
        f"SELECT {columns_str}",
        from_str,
    ]
    if joins_str:
        parts.append(joins_str)
    if where_str:
        parts.append(where_str)
    if group_by_str:
        parts.append(group_by_str)
    if order_by_str:
        parts.append(order_by_str)
    if limit_str:
        parts.append(limit_str)

    return " ".join(parts)


def sql_planner(state: AgentState) -> dict:
    """
    Compiles sql_ast to sql_query.
    Supports dual comparison queries (query_a and query_b).
    """
    sql_ast = state.get("sql_ast") or {}
    user_id = state.get("user_id") or ""

    if not sql_ast:
        logger.info("[Node:sql_planner] Empty AST")
        return {"sql_query": ""}

    if "query_a" in sql_ast and "query_b" in sql_ast:
        query_a_sql = generate_sql(sql_ast["query_a"], user_id)
        query_b_sql = generate_sql(sql_ast["query_b"], user_id)
        result = {
            "query_a": query_a_sql,
            "query_b": query_b_sql,
        }
        logger.info("[Node:sql_planner] Generated comparison queries: %s", json.dumps(result))
        return {"sql_query": result}
    else:
        sql_query = generate_sql(sql_ast, user_id)
        logger.info("[Node:sql_planner] Generated SQL query: %s", sql_query)
        return {"sql_query": sql_query}
