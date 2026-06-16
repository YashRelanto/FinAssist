"""
graph/schema_registry.py
========================
Database schema metadata for the FinAssist SQL pipeline.

Used by:
  - sql_validator.py   : to verify only allowed tables/columns are queried
  - sql_planner.py     : to build valid SQL with correct column names
  - semantic_node.py   : to resolve entity names against actual DB schema
  - agents/*           : to construct SQL AST with valid references

IMPORTANT: No hardcoded category names, merchant names, or business data.
           Only structural metadata (table names, column names, relationships).
"""

from __future__ import annotations

from typing import Dict, List, Set

# ─── Schema Registry ─────────────────────────────────────────────────────────
# Maps each table to its columns, whether it requires user_id filtering,
# and foreign key relationships.

SCHEMA_REGISTRY: Dict[str, dict] = {
    "transactions": {
        "columns": [
            "transaction_id", "user_id", "account_id", "category_id",
            "transaction_date", "amount", "transaction_type",
            "merchant_name", "description", "running_balance",
        ],
        "user_scoped": True,
        "foreign_keys": {
            "category_id": "categories.category_id",
            "account_id": "accounts.account_id",
        },
        "primary_key": "transaction_id",
    },

    "categories": {
        "columns": [
            "category_id", "main_category", "sub_category",
        ],
        "user_scoped": False,
        "foreign_keys": {},
        "primary_key": "category_id",
    },

    "accounts": {
        "columns": [
            "account_id", "user_id", "account_name", "account_type",
            "current_balance", "created_at",
        ],
        "user_scoped": True,
        "foreign_keys": {
            "user_id": "users.user_id",
        },
        "primary_key": "account_id",
    },

    "users": {
        "columns": [
            "user_id", "full_name", "email", "created_at", "deleted_at",
        ],
        "user_scoped": True,
        "foreign_keys": {},
        "primary_key": "user_id",
    },

    "user_profiles": {
        "columns": [
            "user_id", "onboarded", "income", "city_tier",
            "fixed_rent", "fixed_emi", "biggest_category",
            "primary_goal", "created_at",
        ],
        "user_scoped": True,
        "foreign_keys": {
            "user_id": "users.user_id",
        },
        "primary_key": "user_id",
    },
}

# ─── Derived sets for fast validation ─────────────────────────────────────────

ALLOWED_TABLES: Set[str] = set(SCHEMA_REGISTRY.keys())

READ_ONLY_OPS: Set[str] = {"SELECT"}

# Blocked SQL keywords (any appearance in generated SQL → reject)
BLOCKED_KEYWORDS: Set[str] = {
    "DELETE", "UPDATE", "DROP", "INSERT", "ALTER",
    "TRUNCATE", "CREATE", "GRANT", "REVOKE", "EXEC",
}

# ─── Join definitions (pre-built for common agent queries) ────────────────────

STANDARD_JOINS = {
    "transactions_categories": {
        "left_table": "transactions",
        "right_table": "categories",
        "left_column": "category_id",
        "right_column": "category_id",
        "join_type": "LEFT",
    },
    "transactions_accounts": {
        "left_table": "transactions",
        "right_table": "accounts",
        "left_column": "account_id",
        "right_column": "account_id",
        "join_type": "LEFT",
    },
}


# ─── Utility functions ───────────────────────────────────────────────────────

def is_valid_table(table_name: str) -> bool:
    """Check if a table name is in the allowed set."""
    return table_name in ALLOWED_TABLES


def is_valid_column(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the specified table."""
    table = SCHEMA_REGISTRY.get(table_name)
    if not table:
        return False
    return column_name in table["columns"]


def is_user_scoped(table_name: str) -> bool:
    """Check if a table requires user_id filtering."""
    table = SCHEMA_REGISTRY.get(table_name)
    if not table:
        return False
    return table.get("user_scoped", False)


def get_all_columns(table_name: str) -> List[str]:
    """Return all column names for a table, or empty list if unknown."""
    table = SCHEMA_REGISTRY.get(table_name)
    if not table:
        return []
    return list(table["columns"])
