"""Tests for detailed spending analysis."""

from __future__ import annotations

import unittest

from app.services.spending_analysis_service import build_detailed_spending_analysis


def _row(date: str, amount: float, category: str, merchant: str) -> dict:
    return {
        "transaction_date": date,
        "amount": amount,
        "transaction_type": "expense",
        "merchant_name": merchant,
        "categories": {"main_category": category},
    }


class TestSpendingAnalysis(unittest.TestCase):

    def test_monthly_comparison_two_months(self):
        rows = [
            _row("2026-04-05", 5000, "Food & Drinks", "Swiggy"),
            _row("2026-04-12", 3000, "Shopping", "Flipkart"),
            _row("2026-05-03", 7000, "Food & Drinks", "Zomato"),
            _row("2026-05-15", 4000, "Life & Entertainment", "Netflix"),
        ]
        report = build_detailed_spending_analysis(rows)
        self.assertEqual(report["months_analysed"], 2)
        self.assertEqual(report["overall_total_spent_inr"], 19000.0)
        self.assertEqual(len(report["monthly_comparison"]), 2)
        april = report["monthly_comparison"][0]
        may = report["monthly_comparison"][1]
        self.assertEqual(april["total_spent_inr"], 8000.0)
        self.assertEqual(may["total_spent_inr"], 11000.0)
        self.assertEqual(may["vs_previous_month_inr"], 3000.0)
        self.assertIn("category_shifts_vs_previous", may)


    def test_render_answer_uses_exact_totals(self):
        detailed = build_detailed_spending_analysis([
            _row("2026-04-10", 31789, "Food & Drinks", "Swiggy"),
        ])
        # Single month synthetic — test format contains amount
        text = __import__(
            "app.services.spending_analysis_service", fromlist=["render_spending_analysis_answer"]
        ).render_spending_analysis_answer(detailed)
        self.assertIn("₹31,789.00", text)

    def test_excludes_income_and_investment_categories(self):
        rows = [
            _row("2026-04-05", 5000, "Food & Drinks", "Swiggy"),
            {
                "transaction_date": "2026-04-06",
                "amount": 99999,
                "transaction_type": "expense",
                "merchant_name": "Salary",
                "categories": {"main_category": "Income"},
            },
            {
                "transaction_date": "2026-04-07",
                "amount": 88888,
                "transaction_type": "expense",
                "merchant_name": "MF",
                "categories": {"main_category": "Investments"},
            },
        ]
        report = build_detailed_spending_analysis(rows)
        self.assertEqual(report["overall_total_spent_inr"], 5000.0)
        self.assertEqual(report["transaction_count"], 1)


    def test_filter_expense_rows(self):
        from app.services.spending_analysis_service import filter_expense_rows, is_valid_expense_row

        rows = [
            _row("2026-04-05", 100, "Food & Drinks", "A"),
            {"transaction_date": "2026-04-06", "amount": 200, "transaction_type": "income"},
        ]
        self.assertEqual(len(filter_expense_rows(rows)), 1)
        self.assertTrue(is_valid_expense_row(rows[0]))
        self.assertFalse(is_valid_expense_row(rows[1]))


    def test_two_month_comparison_narrative(self):
        rows = [
            _row("2026-04-05", 20000, "Food & Drinks", "Swiggy"),
            _row("2026-04-12", 11789, "Shopping", "Flipkart"),
            _row("2026-05-03", 15000, "Food & Drinks", "Zomato"),
            _row("2026-05-15", 13058, "Transportation", "Uber"),
        ]
        from app.services.spending_analysis_service import (
            build_detailed_spending_analysis,
            render_spending_analysis_answer,
        )
        detailed = build_detailed_spending_analysis(rows)
        text = render_spending_analysis_answer(detailed, user_profile={"primary_goal": "Save More Money"})
        self.assertIn("₹31,789.00", text)
        self.assertIn("₹28,058.00", text)
        self.assertIn("decreased", text.lower())
        self.assertNotIn("₹1,23,450", text)


if __name__ == "__main__":
    unittest.main()
