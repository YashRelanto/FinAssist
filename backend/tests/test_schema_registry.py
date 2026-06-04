"""
Unit tests for checking Schema Registry configuration and validity.
"""

from __future__ import annotations

import unittest

from app.graph.schema_registry import SCHEMA_REGISTRY, ALLOWED_TABLES


class TestSchemaRegistry(unittest.TestCase):

    def test_schema_registry_keys(self):
        """Registry must contain core tables."""
        self.assertIn("transactions", SCHEMA_REGISTRY)
        self.assertIn("categories", SCHEMA_REGISTRY)
        self.assertIn("accounts", SCHEMA_REGISTRY)
        self.assertIn("user_profiles", SCHEMA_REGISTRY)

    def test_allowed_tables(self):
        """Allowed tables set should match registry keys."""
        self.assertEqual(ALLOWED_TABLES, set(SCHEMA_REGISTRY.keys()))

    def test_transactions_columns(self):
        """Transactions table must specify required columns."""
        cols = SCHEMA_REGISTRY["transactions"]["columns"]
        self.assertIn("user_id", cols)
        self.assertIn("amount", cols)
        self.assertIn("transaction_type", cols)
        self.assertIn("category_id", cols)
        self.assertIn("account_id", cols)
        self.assertTrue(SCHEMA_REGISTRY["transactions"]["user_scoped"])

    def test_categories_columns(self):
        """Categories table should have main/sub category columns."""
        cols = SCHEMA_REGISTRY["categories"]["columns"]
        self.assertIn("category_id", cols)
        self.assertIn("main_category", cols)
        self.assertFalse(SCHEMA_REGISTRY["categories"].get("user_scoped", False))


if __name__ == "__main__":
    unittest.main()
