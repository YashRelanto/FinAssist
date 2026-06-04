"""
SQL Validator — Enforces read-only safety, schema compliance, and user scoping.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Any, List

from app.graph.state import AgentState
from app.graph.schema_registry import SCHEMA_REGISTRY, ALLOWED_TABLES

logger = logging.getLogger(__name__)

BLOCKLIST = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "REPLACE", "EXEC", "EXECUTE",
}


def validate_ast(ast: Dict[str, Any]) -> List[str]:
    """
    Checks the structure of a single AST dict for security and registry compliance.
    """
    errors = []
    if not ast:
        return ["Empty AST provided"]

    # 1. Operation check
    op = str(ast.get("operation", "SELECT")).upper().strip()
    if op != "SELECT":
        errors.append(f"Operation '{op}' is blocked. Only SELECT queries are permitted.")

    # 2. Tables check
    tables = ast.get("tables") or [ast.get("table")]
    all_query_tables = []
    for t in tables:
        if t:
            all_query_tables.append(t)
            if t not in ALLOWED_TABLES:
                errors.append(f"Table '{t}' is not in allowed database tables.")

    # Joined tables check
    for join in ast.get("joins", []):
        j_table = join.get("table")
        if j_table:
            all_query_tables.append(j_table)
            if j_table not in ALLOWED_TABLES:
                errors.append(f"Joined table '{j_table}' is not in allowed database tables.")

    # 3. Columns check (optional but safe column validation)
    # Check that any references to columns belong to schema columns
    for col_expr in ast.get("columns", []):
        col_expr_str = str(col_expr).lower()
        # Find any matching table.column pattern
        for t in all_query_tables:
            if t in SCHEMA_REGISTRY:
                # If table name prefix is in expression, check that one of its columns is matched
                if f"{t}." in col_expr_str:
                    col_found = False
                    for col in SCHEMA_REGISTRY[t]["columns"]:
                        if f"{t}.{col}" in col_expr_str:
                            col_found = True
                            break
                    if not col_found:
                        errors.append(f"Expression '{col_expr}' references invalid column in table '{t}'.")

    # 4. User scoping check
    # Every user-scoped table MUST have a filter on user_id
    for t in all_query_tables:
        if t in SCHEMA_REGISTRY and SCHEMA_REGISTRY[t].get("user_scoped", False):
            has_user_filter = False
            for f in ast.get("filters", []):
                col = str(f.get("column") or "")
                if col in ("user_id", f"{t}.user_id"):
                    has_user_filter = True
                    break
            if not has_user_filter:
                errors.append(f"Security policy violation: Table '{t}' requires user_id filtering.")

    return errors


def validate_sql_string(sql: str) -> List[str]:
    """
    Scans the SQL query string for keywords in the blocklist to prevent command injection.
    """
    errors = []
    if not sql:
        return ["Empty SQL string"]

    # Extract all alphanumeric words
    tokens = set(re.findall(r"\b\w+\b", sql.upper()))
    for blocked_word in BLOCKLIST:
        if blocked_word in tokens:
            errors.append(f"SQL query blocked. Statement contains restricted keyword: {blocked_word}")

    return errors


def sql_validator(state: AgentState) -> dict:
    """
    Validates ASTs and SQL strings in AgentState.
    """
    sql_ast = state.get("sql_ast") or {}
    sql_query = state.get("sql_query") or ""

    errors = []

    # Validate AST
    if "query_a" in sql_ast and "query_b" in sql_ast:
        errors.extend(validate_ast(sql_ast["query_a"]))
        errors.extend(validate_ast(sql_ast["query_b"]))
    else:
        errors.extend(validate_ast(sql_ast))

    # Validate SQL String
    if isinstance(sql_query, dict):
        errors.extend(validate_sql_string(sql_query.get("query_a", "")))
        errors.extend(validate_sql_string(sql_query.get("query_b", "")))
    else:
        errors.extend(validate_sql_string(sql_query))

    is_valid = len(errors) == 0
    if not is_valid:
        logger.error("[Node:sql_validator] Validation failed: %s", errors)

    return {
        "sql_valid": is_valid,
        "sql_validation_errors": errors,
    }
