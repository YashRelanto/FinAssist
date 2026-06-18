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


def test_build_daily_chart_data_for_one_month_window():
    from app.services.dashboard_metrics_service import build_daily_chart_data_for_window
    from app.utils.analysis_period import resolve_analysis_window

    transactions = [
        {"transaction_date": "2026-06-01", "amount": 100, "transaction_type": "expense"},
        {"transaction_date": "2026-06-03", "amount": 50, "transaction_type": "expense"},
        {"transaction_date": "2026-06-03", "amount": 200, "transaction_type": "income"},
        {"transaction_date": "2026-06-05", "amount": 75, "transaction_type": "expense"},
    ]
    window = resolve_analysis_window("1m", reference=datetime(2026, 6, 5).date())
    chart = build_daily_chart_data_for_window(transactions, window=window)

    assert len(chart) == 5
    assert chart[0] == {
        "name": "01",
        "date": "2026-06-01",
        "income": 0.0,
        "expense": 100.0,
        "net": -100.0,
    }
    assert chart[2]["expense"] == 50.0
    assert chart[2]["income"] == 200.0
    assert chart[4]["expense"] == 75.0


def test_build_chart_data_for_window_uses_daily_points_for_one_month():
    from app.services.dashboard_metrics_service import build_chart_data_for_window
    from app.utils.analysis_period import resolve_analysis_window

    window = resolve_analysis_window("1m", reference=datetime(2026, 6, 5).date())
    transactions = [
        {"transaction_date": "2026-06-02", "amount": 40, "transaction_type": "expense"},
    ]
    chart = build_chart_data_for_window({}, window=window, transactions=transactions)

    assert len(chart) == 5
    assert all(point.get("date") for point in chart)
    assert chart[1]["expense"] == 40.0


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
            "category_id": "c-food-general",
            "amount": 1000,
            "period": "monthly",
            "start_date": "2026-05-15",
            "end_date": "2026-06-15",
            "alert_threshold": 80,
            "categories": {"main_category": "Food & Drinks"},
        }
    ]
    transactions = [
        {
            "transaction_type": "expense",
            "category_id": "c-food-restaurant",
            "categories": {"main_category": "Food & Drinks", "sub_category": "Restaurant"},
            "transaction_date": "2026-05-01",
            "amount": 400,
        },
        {
            "transaction_type": "expense",
            "category_id": "c-food-restaurant",
            "categories": {"main_category": "Food & Drinks", "sub_category": "Restaurant"},
            "transaction_date": "2026-05-20",
            "amount": 500,
        },
    ]
    util = compute_budget_utilization(
        budgets, transactions, reference=datetime(2026, 5, 20)
    )
    assert len(util) == 1
    assert util[0]["spent"] == 900
    assert util[0]["utilization_pct"] == 90.0
    assert util[0]["alert"] is True


def test_budget_utilization_counts_start_of_month_when_budget_created_mid_month():
    budgets = [
        {
            "budget_id": "b2",
            "budget_name": "Food",
            "category_id": "c-food-general",
            "amount": 1000,
            "period": "monthly",
            "start_date": "2026-06-07",
            "end_date": "2026-07-07",
            "alert_threshold": 80,
            "categories": {"main_category": "Food & Drinks"},
        }
    ]
    transactions = [
        {
            "transaction_type": "expense",
            "category_id": "c-food-general",
            "categories": {"main_category": "Food & Drinks"},
            "transaction_date": "2026-06-01",
            "amount": 300,
        },
        {
            "transaction_type": "expense",
            "category_id": "c-food-general",
            "categories": {"main_category": "Food & Drinks"},
            "transaction_date": "2026-06-07",
            "amount": 200,
        },
    ]
    util = compute_budget_utilization(
        budgets, transactions, reference=datetime(2026, 6, 7)
    )
    assert util[0]["spent"] == 500


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


def test_aggregate_top_spending_by_merchant():
    from app.services.dashboard_metrics_service import aggregate_top_spending_by_merchant

    rows = [
        {
            "transaction_date": "2026-05-01",
            "amount": 100,
            "transaction_type": "expense",
            "merchant_name": "Swiggy",
        },
        {
            "transaction_date": "2026-05-02",
            "amount": 200,
            "transaction_type": "expense",
            "merchant_name": "Swiggy",
        },
        {
            "transaction_date": "2026-05-03",
            "amount": 50,
            "transaction_type": "expense",
            "merchant_name": "Amazon",
        },
    ]
    top = aggregate_top_spending_by_merchant(
        rows, start_date="2026-05-01", end_date="2026-05-31"
    )
    assert top[0]["merchant"] == "Swiggy"
    assert top[0]["total"] == 300
    assert top[0]["count"] == 2


def test_build_dashboard_payload_includes_all_period_chart_data():
    from unittest.mock import patch

    from app.services.dashboard_metrics_service import (
        build_dashboard_payload,
        enrich_chart_data_with_forecast,
    )

    transactions = [
        {"transaction_date": "2026-06-01", "amount": 100, "transaction_type": "expense"},
        {"transaction_date": "2026-05-15", "amount": 200, "transaction_type": "expense"},
        {"transaction_date": "2026-04-10", "amount": 50, "transaction_type": "expense"},
    ]
    forecast_meta = {
        "predicted_next_month": 500.0,
        "predicted_month_label": "July 2026",
        "predicted_month": "2026-07",
    }
    with patch(
        "app.services.prophet.inference.get_next_month_prediction",
        return_value=forecast_meta,
    ):
        payload = build_dashboard_payload(
            user_id="test-user",
            accounts=[{"current_balance": 1000, "account_type": "checking"}],
            transactions=transactions,
            recent_rows=[],
            budgets=[],
            profile_income=50000,
            reference=datetime(2026, 6, 5),
            period="1m",
        )

    assert "period_data" in payload
    for period in ("1m", "3m", "6m", "1y", "all"):
        assert period in payload["period_data"]
        assert "chart_data" in payload["period_data"][period]
        assert len(payload["period_data"][period]["chart_data"]) > 0
        assert "financial_health" not in payload["period_data"][period]

    assert payload["period_data"]["1m"]["chart_granularity"] == "daily"
    assert payload["period_data"]["3m"]["chart_granularity"] == "monthly"
    assert "financial_health" in payload
    assert payload["financial_health"]["score"] >= 0

    chart = payload["period_data"]["3m"]["chart_data"]
    forecast_point = chart[-1]
    assert forecast_point.get("is_forecast") is True
    assert forecast_point.get("predicted_expense") == 500.0


def test_financial_health_identical_across_period_slices():
    from unittest.mock import patch

    from app.services.dashboard_metrics_service import build_dashboard_payload

    transactions = [
        {"transaction_date": "2026-06-01", "amount": 100, "transaction_type": "expense"},
        {"transaction_date": "2026-05-15", "amount": 200, "transaction_type": "expense"},
        {"transaction_date": "2026-04-10", "amount": 50, "transaction_type": "income"},
    ]
    with patch(
        "app.services.prophet.inference.get_next_month_prediction",
        return_value=None,
    ):
        payload = build_dashboard_payload(
            user_id="test-user",
            accounts=[{"current_balance": 10000, "account_type": "savings"}],
            transactions=transactions,
            recent_rows=[],
            budgets=[],
            profile_income=80000,
            reference=datetime(2026, 6, 5),
            period="1m",
        )

    root_health = payload["financial_health"]
    for period in ("1m", "3m", "6m", "1y", "all"):
        assert payload["period_data"][period].get("financial_health") is None
    assert root_health == payload["financial_health"]


def test_enrich_chart_data_with_forecast():
    from app.services.dashboard_metrics_service import enrich_chart_data_with_forecast

    chart = [
        {"name": "Apr", "expense": 100},
        {"name": "May", "expense": 200},
    ]
    enriched = enrich_chart_data_with_forecast(
        chart,
        predicted_next_month=250,
        predicted_month_label="July 2026",
        predicted_month="2026-07",
        period="3m",
    )
    assert enriched[-1]["is_forecast"] is True
    assert enriched[-1]["predicted_expense"] == 250
    assert enriched[-2]["predicted_expense"] == 200
    assert enriched[0]["actual_expense"] == 100


def test_compute_financial_health_score():
    from app.services.dashboard_metrics_service import compute_financial_health

    summary = {
        "monthly_income": 100000,
        "net_savings": 20000,
        "savings_rate": 20.0,
        "fixed_expense": 25000,
        "net_outflow": 80000,
        "total_balance": 150000,
    }
    accounts = [
        {"account_type": "savings", "current_balance": 150000},
        {
            "account_type": "credit_card",
            "current_balance": -20000,
            "credit_limit": 100000,
        },
    ]
    health = compute_financial_health(summary, accounts)
    assert 0 <= health["score"] <= 100
    assert health["debt_to_income_pct"] == 25.0
    assert health["monthly_commitments_pct"] == 25.0


def test_overall_financial_health_includes_liquid_funds_and_fds():
    from app.services.dashboard_metrics_service import compute_overall_financial_health

    accounts = [{"account_type": "savings", "current_balance": 60000}]
    # 120000 expense averaged over the trailing 6 months → lifestyle burn 20000/month.
    transactions = [
        {"transaction_date": "2026-06-05", "amount": 120000, "transaction_type": "expense"},
    ]
    kwargs = dict(
        accounts=accounts,
        transactions=transactions,
        profile_income=100000,
        reference=datetime(2026, 6, 30),
    )

    bank_only = compute_overall_financial_health(**kwargs)
    with_assets = compute_overall_financial_health(
        liquid_funds_value=30000, fixed_deposits_value=30000, **kwargs
    )

    # Liquid balance + breakdown now combine bank cash with near-cash investments.
    assert bank_only["total_liquid_balance"] == 60000.0
    assert with_assets["total_liquid_balance"] == 120000.0
    assert with_assets["liquid_breakdown"] == {
        "bank_balance": 60000.0,
        "liquid_funds": 30000.0,
        "fixed_deposits": 30000.0,
    }
    # Adding near-cash assets extends the emergency runway (3 → 6 months here) and never
    # lowers the score.
    assert bank_only["lifestyle_buffer_months"] == 3.0
    assert with_assets["lifestyle_buffer_months"] == 6.0
    assert with_assets["score"] >= bank_only["score"]


def test_overall_financial_health_defaults_to_bank_only():
    from app.services.dashboard_metrics_service import compute_overall_financial_health

    health = compute_overall_financial_health(
        accounts=[{"account_type": "savings", "current_balance": 40000}],
        transactions=[{"transaction_date": "2026-06-05", "amount": 60000, "transaction_type": "expense"}],
        profile_income=50000,
        reference=datetime(2026, 6, 30),
    )
    # No near-cash assets passed → breakdown shows bank only, totals unchanged.
    assert health["liquid_breakdown"] == {
        "bank_balance": 40000.0,
        "liquid_funds": 0.0,
        "fixed_deposits": 0.0,
    }
    assert health["total_liquid_balance"] == 40000.0


def test_compute_monthly_recurring_obligations():
    from app.services.dashboard_metrics_service import compute_monthly_recurring_obligations

    transactions = [
        {
            "is_recurring": True,
            "transaction_type": "expense",
            "amount": 499,
            "recurrence_period": "monthly",
            "recurrence_skips": 0,
            "merchant_name": "Netflix",
            "categories": {"main_category": "Life & Entertainment"},
        },
        {
            "is_recurring": True,
            "transaction_type": "expense",
            "amount": 1200,
            "recurrence_period": "weekly",
            "recurrence_skips": 0,
            "merchant_name": "Gym",
            "categories": {"main_category": "Life & Entertainment"},
        },
    ]
    total = compute_monthly_recurring_obligations(
        transactions,
        profile_fixed_rent=15000,
        profile_fixed_emi=5000,
    )
    assert total == round(15000 + 5000 + 499 + 1200 * (52 / 12), 2)


def test_compute_survival_burn():
    from app.services.dashboard_metrics_service import compute_survival_burn

    transactions = [
        {
            "is_recurring": True,
            "transaction_type": "expense",
            "amount": 20000,
            "recurrence_period": "monthly",
            "recurrence_skips": 0,
            "merchant_name": "Rent",
            "categories": {"main_category": "Housing", "sub_category": "Rent"},
            "transaction_date": "2026-06-01",
        },
        {
            "is_recurring": True,
            "transaction_type": "expense",
            "amount": 1200,
            "recurrence_period": "monthly",
            "recurrence_skips": 0,
            "merchant_name": "Airtel Broadband",
            "categories": {"main_category": "Communication/PC"},
            "transaction_date": "2026-06-05",
        },
        {
            "transaction_type": "expense",
            "amount": 2500,
            "merchant_name": "BigBasket Groceries",
            "categories": {"main_category": "Food & Drinks"},
            "transaction_date": "2026-06-10",
        },
        {
            "transaction_type": "expense",
            "amount": 3000,
            "merchant_name": "BigBasket Groceries",
            "categories": {"main_category": "Food & Drinks"},
            "transaction_date": "2026-05-10",
        },
    ]
    burn = compute_survival_burn(transactions, profile_fixed_rent=0, profile_fixed_emi=0)
    # Essential living averages across 6 calendar months (most months are zero).
    assert burn == round(20000 + 1200 + (2500 + 3000) / 6, 2)
