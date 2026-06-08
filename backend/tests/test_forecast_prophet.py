"""End-to-end global Prophet train + predict using sample data (no Supabase required)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pandas as pd
import pytest

from app.services.forecast_features import (
    MIN_MONTHS_FOR_PROPHET_USER,
    MONTHLY_REGRESSOR_COLUMNS,
    attach_monthly_regressors,
    build_prophet_monthly_frame,
    drop_incomplete_current_month,
    expenses_to_monthly,
    model_uses_monthly_regressors,
    prophet_holdout_mape_monthly,
)
from app.services.forecast_service import generate_forecast, reload_models
from app.services.prophet_training_service import train_from_dataframe, train_prophet_bundle_from_transactions

SAMPLE_USER = "test-user-prophet-e2e"


def _build_sample_transactions(months: int = 8, base: float = 5000.0) -> pd.DataFrame:
  """Synthetic monthly spend pattern for one user."""
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
    """Train sample bundle into a temp production directory."""
    import app.core.config as cfg
    import app.services.forecast_service as fs
    import app.services.prophet_training_service as pts

    monkeypatch.setattr(cfg.settings, "FORECAST_STORAGE_ENABLED", False)

    prod = tmp_path / "production"
    staging = tmp_path / "staging"
    monkeypatch.setattr(pts, "PRODUCTION_DIR", prod)
    monkeypatch.setattr(pts, "STAGING_DIR", staging)
    monkeypatch.setattr(pts, "PRODUCTION_BUNDLE_PATH", prod / "expense_forecast_prophet.joblib")
    monkeypatch.setattr(pts, "STAGING_BUNDLE_PATH", staging / "expense_forecast_prophet.joblib")
    monkeypatch.setattr(pts, "PRODUCTION_MANIFEST_PATH", prod / "manifest.json")

    monkeypatch.setattr(fs, "PRODUCTION_DIR", prod)
    monkeypatch.setattr(fs, "PRODUCTION_BUNDLE_PATH", prod / "expense_forecast_prophet.joblib")
    monkeypatch.setattr(fs, "PRODUCTION_MANIFEST_PATH", prod / "manifest.json")

    tx = _build_sample_transactions(months=8)
    train_from_dataframe(tx, output_dir=prod, promote=True)
    reload_models()
    yield prod
    reload_models()


def test_holdout_mape_computed_with_minimum_months():
    tx = _build_sample_transactions(months=MIN_MONTHS_FOR_PROPHET_USER)
    monthly = expenses_to_monthly(tx)
    mape = prophet_holdout_mape_monthly(monthly)
    assert mape is not None
    assert 0.0 <= mape <= 1.0


def test_training_bundle_includes_test_mape():
    tx = _build_sample_transactions(months=MIN_MONTHS_FOR_PROPHET_USER)
    bundle = train_prophet_bundle_from_transactions(tx)
    assert bundle["test_mape"] is not None
    assert bundle["test_mape"] < 0.5
    assert bundle["regressor_columns"] == MONTHLY_REGRESSOR_COLUMNS
    assert model_uses_monthly_regressors(bundle["model"])


def test_monthly_regressors_are_built_from_history():
    tx = _build_sample_transactions(months=MIN_MONTHS_FOR_PROPHET_USER)
    monthly = expenses_to_monthly(tx)
    frame = build_prophet_monthly_frame(monthly)
    assert not frame.empty
    for col in MONTHLY_REGRESSOR_COLUMNS:
        assert col in frame.columns
        assert frame[col].notna().all()
    enriched = attach_monthly_regressors(monthly)
    assert enriched["lag_1"].iloc[-1] == monthly["monthly_expense"].iloc[-2]


def test_partial_current_month_does_not_inflate_mape():
    tx = _build_sample_transactions(months=6)
    tx["transaction_date"] = pd.to_datetime(tx["transaction_date"]) + pd.DateOffset(years=1)
    tx.loc[tx["transaction_date"].dt.month == 6, "amount"] *= 0.1
    monthly = expenses_to_monthly(tx)
    ref = pd.Timestamp("2026-06-07").date()
    mape = prophet_holdout_mape_monthly(monthly, reference=ref)
    assert mape is not None
    assert mape < 0.65


def test_sample_data_has_enough_months():
    tx = _build_sample_transactions()
    monthly = expenses_to_monthly(tx)
    assert len(monthly) >= MIN_MONTHS_FOR_PROPHET_USER


def test_train_and_predict_e2e(trained_production_bundle):
    tx = _build_sample_transactions(months=8)
    result = generate_forecast(
        tx.to_dict(orient="records"),
        [],
        user_id=SAMPLE_USER,
        period="1m",
    )

    assert result["success"] is True
    assert result["user_model_available"] is True
    assert result["predicted_next_month"] > 0
    assert len(result["predicted_months"]) >= 1
    assert sum(m["amount"] for m in result["predicted_months"]) == result["predicted_next_month"]
    assert len(result["monthly_chart"]) >= 1
    forecast_bars = [b for b in result["monthly_chart"] if b.get("is_forecast")]
    assert len(forecast_bars) == 1


def test_global_model_serves_any_user_with_history(trained_production_bundle):
    tx = _build_sample_transactions()
    result = generate_forecast(
        tx.to_dict(orient="records"),
        [],
        user_id=str(uuid.uuid4()),
        period="1m",
    )
    assert result["success"] is True
    assert result["user_model_available"] is True
    assert result["predicted_next_month"] > 0


def test_insufficient_history_no_forecast(trained_production_bundle):
    tx = _build_sample_transactions(months=2)
    result = generate_forecast(
        tx.to_dict(orient="records"),
        [],
        user_id=SAMPLE_USER,
    )
    assert result["success"] is True
    assert result["user_model_available"] is False
    assert "months" in (result.get("message") or "").lower()
