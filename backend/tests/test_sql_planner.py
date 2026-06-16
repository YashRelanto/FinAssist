"""
Unit tests for SQL planner (FR-10).
"""

from __future__ import annotations

import unittest

from app.graph.sql.sql_planner import generate_sql


class TestSqlPlanner(unittest.TestCase):

    def test_single_ast_generates_select(self):
        ast = {
            "operation": "SELECT",
            "tables": ["transactions"],
            "columns": ["amount", "transaction_date"],
            "filters": [
                {"column": "transactions.user_id", "op": "=", "value": "{{user_id}}"},
                {"column": "transaction_type", "op": "=", "value": "expense"},
            ],
            "limit": 50,
        }
        sql = generate_sql(ast, "user-123")
        self.assertTrue(sql.upper().startswith("SELECT"))
        self.assertIn("user-123", sql)
        self.assertIn("transactions", sql)

    def test_dual_comparison_ast(self):
        from app.graph.sql.sql_planner import sql_planner

        ast_a = {
            "tables": ["transactions"],
            "columns": ["amount"],
            "filters": [{"column": "user_id", "op": "=", "value": "{{user_id}}"}],
        }
        result = sql_planner({
            "user_id": "u1",
            "sql_ast": {"query_a": ast_a, "query_b": ast_a},
        })
        sql_query = result["sql_query"]
        self.assertIn("query_a", sql_query)
        self.assertIn("query_b", sql_query)
        self.assertTrue(sql_query["query_a"].upper().startswith("SELECT"))


if __name__ == "__main__":
    unittest.main()
