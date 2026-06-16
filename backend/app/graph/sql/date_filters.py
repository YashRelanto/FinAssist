"""Inject entity date_range filters into SQL ASTs."""

from __future__ import annotations

import copy
from typing import Any


def _strip_date_filters(filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        f for f in filters
        if "transaction_date" not in str(f.get("column", "")).lower()
    ]


def apply_entity_date_filters(
    ast: dict[str, Any],
    entities: dict[str, Any] | None,
) -> dict[str, Any]:
    """Ensure transaction_date bounds from resolved entities are in the AST."""
    if not ast:
        return ast

    date_range = (entities or {}).get("date_range") or {}
    start = date_range.get("from")
    end = date_range.get("to")
    if not start and not end:
        return ast

    patched = copy.deepcopy(ast)
    filters = _strip_date_filters(list(patched.get("filters") or []))

    if start:
        filters.append({
            "column": "transactions.transaction_date",
            "op": ">=",
            "value": start,
        })
    if end:
        filters.append({
            "column": "transactions.transaction_date",
            "op": "<=",
            "value": end,
        })

    patched["filters"] = filters
    return patched


def apply_entity_date_filters_to_ast(
    sql_ast: dict[str, Any],
    entities: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply date filters to a single AST or dual comparison AST."""
    if not sql_ast:
        return sql_ast

    if "query_a" in sql_ast and "query_b" in sql_ast:
        return {
            **sql_ast,
            "query_a": apply_entity_date_filters(sql_ast.get("query_a") or {}, entities),
            "query_b": apply_entity_date_filters(sql_ast.get("query_b") or {}, entities),
        }

    return apply_entity_date_filters(sql_ast, entities)
