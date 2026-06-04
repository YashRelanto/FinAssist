"""End-to-end Prophet per-user train + predict using sample data (no Supabase required)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pandas as pd
import pytest

from app.services.forecast_features import expenses_to_weekly
from app.services.forecast_service import generate_forecast, reload_models
from app.services.prophet_training_service import (
    MIN_WEEKS_FOR_PROPHET_USER,
    train_from_dataframe,
)

SAMPLE_USER = "test-user-prophet-e2e"


def _build_sample_transactions(weeks: int = 12, base: float = 5000.0) -> pd.DataFrame:
  """Synthetic weekly spend pattern for one user."""
  rows = []
  start = pd.Timestamp("2025-01-06")
  for w in range(weeks):
    week_start = start + pd.Timedelta(days=7 * w)
    weekly_total = base + (w * 120) + (200 if w % 4 == 0 else 0)
    for day_offset in range(3):
      rows.append(
          {
              "user_id": SAMPLE_USER,
              "transaction_date": (week_start + pd.Timedelta(days=day_offset)).strftime("%Y-%m-%d"),
              "amount": round(weekly_total / 3, 2),
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

    tx = _build_sample_transactions(weeks=12)
    train_from_dataframe(tx, output_dir=prod, promote=True)
    reload_models()
    yield prod
    reload_models()


def test_sample_data_has_enough_weeks():
    tx = _build_sample_transactions()
    weekly = expenses_to_weekly(tx)
    assert len(weekly) >= MIN_WEEKS_FOR_PROPHET_USER


def test_train_and_predict_e2e(trained_production_bundle):
    tx = _build_sample_transactions(weeks=12)
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


def test_unknown_user_no_model(trained_production_bundle):
    tx = _build_sample_transactions()
    result = generate_forecast(
        tx.to_dict(orient="records"),
        [],
        user_id=str(uuid.uuid4()),
    )
    assert result["success"] is True
    assert result["user_model_available"] is False
    assert "No Prophet model" in (result.get("message") or "")
