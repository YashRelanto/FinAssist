"""Tests for output guard investment disclaimer (FR-16)."""

from __future__ import annotations

import unittest

from app.guardrails.output_guard import OutputGuard


class TestOutputGuardDisclaimer(unittest.TestCase):

    def test_appends_disclaimer_for_investment_content(self):
        text = "You should rebalance your mutual fund portfolio toward index funds."
        cleaned = OutputGuard.append_disclaimer_if_needed(text)
        self.assertIn("SEBI-registered", cleaned)

    def test_skips_disclaimer_for_generic_text(self):
        text = "Your food spending was ₹5,000 this month."
        cleaned = OutputGuard.append_disclaimer_if_needed(text)
        self.assertNotIn("SEBI-registered", cleaned)


if __name__ == "__main__":
    unittest.main()
