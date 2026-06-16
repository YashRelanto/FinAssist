"""Tests for input query normalization (FR-1)."""

from __future__ import annotations

import unittest

from app.guardrails.input_guard import normalize_query


class TestInputNormalization(unittest.TestCase):

    def test_collapses_whitespace(self):
        self.assertEqual(normalize_query("  hello   world  "), "hello world")

    def test_normalizes_unicode_quotes(self):
        self.assertEqual(normalize_query("what\u2019s my balance"), "what's my balance")


if __name__ == "__main__":
    unittest.main()
