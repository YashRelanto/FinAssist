"""End-to-end global Prophet train + predict using sample data (no Supabase required)."""

from __future__ import annotations

import uuid

import pandas as pd
import pytest

from app.services.prophet.features import (
    MIN_MONTHS_FOR_PROPHET_USER,
    calculate_holdout_mape,
    cap_all_outliers,
    create_user_monthly,
    drop_incomplete_current_month,
    get_recent_6_month_shares,
    predict_user_amount,
    prepare_global_training_expenses,
    user_has_enough_history,
)
from app.services.prophet.inference import generate_forecast, reload_models
from app.services.prophet.training import train_bundle, train_from_dataframe

SAMPLE_USER = "test-user-prophet-e2e"


def _build_sample_transactions(months: int = 8, base: float = 5000.0) -> pd.DataFrame:
    rows = []
    start = pd.Timestamp("2025-01-06")
    for m in range(months):
        month_start = start + pd.DateOffset(months=m)
        monthly_total = base + (m * 120) + (200 if m % 4 == 0 else 0)
        for day_offset in range(3):
            rows.append(
                {
                    "user_id": SAMPLE_USER,
                    "transaction_date": (month_start + pd.Timedelta(days=day_offset)).strftime("%Y-%m-%d"),
                    "amount": round(monthly_total / 3, 2),
                    "transaction_type": "expense",
                    "merchant_name": "Sample Store",
                    "category_id": "cat-1",
                },
            )
    return pd.DataFrame(rows)


@pytest.fixture
def trained_production_bundle(tmp_path, monkeypatch):
    import app.core.config as cfg
    import app.services.prophet.inference as inference
    import app.services.prophet.paths as paths

    monkeypatch.setattr(cfg.settings, "FORECAST_STORAGE_ENABLED", False)

    prod = tmp_path / "production"
    staging = tmp_path / "staging"
    bundle_name = "expense_forecast_prophet.joblib"
    monkeypatch.setattr(paths, "PRODUCTION_DIR", prod)
    monkeypatch.setattr(paths, "STAGING_DIR", staging)
    monkeypatch.setattr(paths, "PRODUCTION_BUNDLE_PATH", prod / bundle_name)
    monkeypatch.setattr(paths, "STAGING_BUNDLE_PATH", staging / bundle_name)
    monkeypatch.setattr(paths, "PRODUCTION_MANIFEST_PATH", prod / "manifest.json")
    monkeypatch.setattr(inference, "PRODUCTION_BUNDLE_PATH", prod / bundle_name)
    monkeypatch.setattr(inference, "PRODUCTION_MANIFEST_PATH", prod / "manifest.json")

    train_from_dataframe(_build_sample_transactions(months=8), output_dir=prod, promote=True)
    reload_models()
    yield prod
    reload_models()


def test_holdout_mape_computed_with_minimum_months():
    tx = _build_sample_transactions(months=MIN_MONTHS_FOR_PROPHET_USER)
    pool = prepare_global_training_expenses(tx)
    user_monthly = drop_incomplete_current_month(create_user_monthly(cap_all_outliers(pool)))
    mape = calculate_holdout_mape(user_monthly)
    assert mape is not None
    assert 0.0 <= mape <= 1.0


def test_training_bundle_uses_scaled_mape_for_multi_user():
    tx_high = _build_sample_transactions(months=MIN_MONTHS_FOR_PROPHET_USER, base=12000.0)
    tx_high["user_id"] = "second-user"
    tx_two = pd.concat(
        [_build_sample_transactions(months=MIN_MONTHS_FOR_PROPHET_USER, base=5000.0), tx_high],
        ignore_index=True,
    )
    bundle_one = train_bundle(_build_sample_transactions(months=MIN_MONTHS_FOR_PROPHET_USER))
    bundle_two = train_bundle(tx_two)
    assert bundle_one["test_mape"] is not None
    assert bundle_two["test_mape"] is not None
    assert bundle_two["training_users"] == 2
    assert "user_shares" in bundle_two


def test_training_bundle_includes_test_mape():
    tx = _build_sample_transactions(months=MIN_MONTHS_FOR_PROPHET_USER)
    bundle = train_bundle(tx)
    assert bundle["test_mape"] is not None
    assert bundle["test_mape"] < 0.5
    assert bundle["trained_transactions"] == len(tx)
    assert bundle["model"] is not None
    assert SAMPLE_USER in bundle["user_shares"]


def test_user_shares_sum_to_one():
    tx_high = _build_sample_transactions(months=8, base=9000.0)
    tx_high["user_id"] = "second-user"
    tx = pd.concat([_build_sample_transactions(months=8), tx_high], ignore_index=True)
    pool = prepare_global_training_expenses(tx)
    user_monthly = drop_incomplete_current_month(create_user_monthly(cap_all_outliers(pool)))
    shares = get_recent_6_month_shares(user_monthly)
    assert abs(float(shares.sum()) - 1.0) < 1e-6


def test_sample_data_has_enough_months():
    assert user_has_enough_history(_build_sample_transactions())


def test_train_and_predict_e2e(trained_production_bundle):
    tx = _build_sample_transactions(months=8)
    result = generate_forecast(tx.to_dict(orient="records"), [], user_id=SAMPLE_USER, period="1m")
    assert result["success"] is True
    assert result["user_model_available"] is True
    assert result["predicted_next_month"] > 0
    assert len(result["predicted_months"]) >= 1
    assert sum(m["amount"] for m in result["predicted_months"]) == result["predicted_next_month"]


def test_global_model_serves_any_user_with_history(trained_production_bundle):
    tx = _build_sample_transactions()
    result = generate_forecast(tx.to_dict(orient="records"), [], user_id=str(uuid.uuid4()), period="1m")
    assert result["success"] is True
    assert result["user_model_available"] is True
    assert result["predicted_next_month"] > 0


def test_prepare_global_training_expenses_excludes_income_and_short_history():
    long_user = "user-long"
    short_user = "user-short"
    rows = []
    start = pd.Timestamp("2025-01-06")
    for m in range(8):
        month_start = start + pd.DateOffset(months=m)
        rows.append(
            {"user_id": long_user, "transaction_date": month_start.strftime("%Y-%m-%d"), "amount": 100.0, "transaction_type": "expense"},
        )
        rows.append(
            {"user_id": long_user, "transaction_date": month_start.strftime("%Y-%m-%d"), "amount": 5000.0, "transaction_type": "income"},
        )
    for m in range(2):
        month_start = start + pd.DateOffset(months=m)
        rows.append(
            {"user_id": short_user, "transaction_date": month_start.strftime("%Y-%m-%d"), "amount": 50.0, "transaction_type": "expense"},
        )
    pool = prepare_global_training_expenses(pd.DataFrame(rows))
    assert len(pool) == 8
    assert set(pool["user_id"]) == {long_user}
    assert set(pool["transaction_type"]) == {"expense"}


def test_predict_user_amount_uses_bundle_share():
    tx = _build_sample_transactions(months=8)
    bundle = train_bundle(tx)
    pool = prepare_global_training_expenses(tx)
    user_monthly = drop_incomplete_current_month(create_user_monthly(cap_all_outliers(pool)))
    pred = predict_user_amount(10000.0, SAMPLE_USER, user_monthly, user_shares=bundle["user_shares"])
    assert pred > 0


def test_insufficient_history_no_forecast(trained_production_bundle):
    tx = _build_sample_transactions(months=2)
    result = generate_forecast(tx.to_dict(orient="records"), [], user_id=SAMPLE_USER)
    assert result["success"] is True
    assert result["user_model_available"] is False
    assert "months" in (result.get("message") or "").lower()
