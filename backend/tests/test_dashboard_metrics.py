"""Unit tests for dashboard metric aggregation."""

from datetime import datetime

from app.services.dashboard_metrics_service import (
    aggregate_monthly_stats,
    build_chart_data,
    compute_budget_utilization,
    compute_savings_trajectory,
    compute_summary,
    format_recent_transactions,
    transaction_amount_value,
)


def test_transaction_amount_always_positive_magnitude():
    assert transaction_amount_value(-50, "expense") == 50
    assert transaction_amount_value(50, "income") == 50


def test_aggregate_monthly_stats_excludes_transfers():
    rows = [
        {"transaction_date": "2026-05-10", "amount": 1000, "transaction_type": "income"},
        {"transaction_date": "2026-05-12", "amount": 200, "transaction_type": "expense"},
        {"transaction_date": "2026-05-13", "amount": 500, "transaction_type": "transfer"},
    ]
    stats = aggregate_monthly_stats(rows)
    assert stats["2026-05"]["income"] == 1000
    assert stats["2026-05"]["expense"] == 200


def test_compute_summary_current_calendar_month():
    accounts = [{"current_balance": 1500}, {"current_balance": 500}]
    stats = {
        "2026-05": {"income": 4000, "expense": 2500},
        "2026-04": {"income": 3000, "expense": 1000},
    }
    summary = compute_summary(
        accounts, stats, reference=datetime(2026, 5, 30)
    )
    assert summary["total_balance"] == 2000
    assert summary["monthly_income"] == 4000
    assert summary["monthly_expenses"] == 2500
    assert summary["net_savings"] == 1500
    assert summary["savings_rate"] == 37.5


def test_build_chart_data_includes_current_month():
    stats = {"2026-03": {"income": 1, "expense": 2}}
    chart = build_chart_data(stats, reference=datetime(2026, 5, 1))
    months = [point["month"] for point in chart]
    assert "2026-05" in months
    assert chart[-1]["net"] == -0.0 or chart[-1]["income"] == 0


def test_format_recent_transactions_expense_sign():
    rows = [
        {
            "transaction_id": "t1",
            "transaction_date": "2026-05-01",
            "merchant_name": "Store",
            "amount": 42,
            "transaction_type": "expense",
            "categories": {"main_category": "Shopping", "sub_category": "General"},
            "accounts": {"account_name": "Checking"},
        }
    ]
    formatted = format_recent_transactions(rows)
    assert formatted[0]["amount"] == -42
    assert formatted[0]["type"] == "expense"


def test_budget_utilization_for_active_period():
    budgets = [
        {
            "budget_id": "b1",
            "budget_name": "Food",
            "category_id": "c-food",
            "amount": 1000,
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "alert_threshold": 80,
            "categories": {"main_category": "Food & Drinks"},
        }
    ]
    transactions = [
        {
            "transaction_type": "expense",
            "category_id": "c-food",
            "transaction_date": "2026-05-15",
            "amount": 900,
        }
    ]
    util = compute_budget_utilization(
        budgets, transactions, reference=datetime(2026, 5, 20)
    )
    assert len(util) == 1
    assert util[0]["spent"] == 900
    assert util[0]["utilization_pct"] == 90.0
    assert util[0]["alert"] is True


def test_savings_trajectory_from_transactions():
    transactions = [
        {"transaction_date": "2026-05-10", "amount": 5000, "transaction_type": "income"},
        {"transaction_date": "2026-05-12", "amount": 2000, "transaction_type": "expense"},
        {"transaction_date": "2026-04-15", "amount": 4000, "transaction_type": "income"},
        {"transaction_date": "2026-04-20", "amount": 2500, "transaction_type": "expense"},
    ]
    trajectory = compute_savings_trajectory(
        transactions, reference=datetime(2026, 5, 20)
    )
    assert trajectory["has_data"] is True
    assert trajectory["monthly_net_savings"] == 3000
    assert trajectory["previous_month_net"] == 1500
    assert trajectory["savings_growth_pct"] == 100
