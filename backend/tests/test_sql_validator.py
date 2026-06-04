"""
Unit tests for SQL AST and string validation using unittest.
"""

from __future__ import annotations

import unittest

from app.graph.sql.sql_validator import validate_ast, validate_sql_string


class TestSqlValidator(unittest.TestCase):

    def test_validate_ast_valid(self):
        """Valid SELECT AST should return no errors."""
        ast = {
            "operation": "SELECT",
            "tables": ["transactions"],
            "columns": ["amount", "merchant_name"],
            "filters": [
                {"column": "transactions.user_id", "op": "=", "value": "some-uuid"},
                {"column": "transaction_type", "op": "=", "value": "expense"}
            ]
        }
        errors = validate_ast(ast)
        self.assertEqual(len(errors), 0)

    def test_validate_ast_blocked_operation(self):
        """Non-SELECT operation should be blocked."""
        ast = {
            "operation": "DELETE",
            "tables": ["transactions"],
            "filters": [
                {"column": "user_id", "op": "=", "value": "some-uuid"}
            ]
        }
        errors = validate_ast(ast)
        self.assertTrue(any("blocked" in e.lower() or "delete" in e.lower() for e in errors))

    def test_validate_ast_invalid_table(self):
        """Accessing tables not in allowed list should be blocked."""
        ast = {
            "operation": "SELECT",
            "tables": ["secrets_table"],
            "filters": [
                {"column": "user_id", "op": "=", "value": "some-uuid"}
            ]
        }
        errors = validate_ast(ast)
        self.assertTrue(any("allowed" in e.lower() or "secrets_table" in e.lower() for e in errors))

    def test_validate_ast_missing_user_scoping(self):
        """Enforce user_id filter for user-scoped tables."""
        ast = {
            "operation": "SELECT",
            "tables": ["transactions"],
            "columns": ["amount"],
            "filters": [
                {"column": "transaction_type", "op": "=", "value": "expense"}
            ]
        }
        errors = validate_ast(ast)
        self.assertTrue(any("user_id" in e.lower() or "scope" in e.lower() for e in errors))

    def test_validate_ast_invalid_column(self):
        """Accessing columns that don't exist should be blocked."""
        ast = {
            "operation": "SELECT",
            "tables": ["transactions"],
            "columns": ["transactions.invalid_column_name"],
            "filters": [
                {"column": "transactions.user_id", "op": "=", "value": "some-uuid"}
            ]
        }
        errors = validate_ast(ast)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("column" in e.lower() or "invalid_column_name" in e.lower() for e in errors))

    def test_validate_sql_string_blocked(self):
        """Blocked SQL keywords in query string should be flagged."""
        sql = "SELECT * FROM transactions WHERE user_id = '123'; DROP TABLE transactions;"
        errors = validate_sql_string(sql)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("blocked" in e.lower() or "drop" in e.lower() for e in errors))

    def test_validate_sql_string_valid(self):
        """Safe select SQL string should pass."""
        sql = "SELECT amount FROM transactions WHERE user_id = '123' AND transaction_type = 'expense'"
        errors = validate_sql_string(sql)
        self.assertEqual(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
