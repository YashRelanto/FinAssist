#!/usr/bin/env python3
"""Train production Prophet bundle from data/processed/transactions.csv (dev / smoke test)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.forecast_service import generate_forecast, reload_models  # noqa: E402
from app.services.prophet_training_service import train_from_dataframe  # noqa: E402


def main() -> int:
    tx_path = ROOT / "data" / "processed" / "transactions.csv"
    if not tx_path.is_file():
        print(f"Missing {tx_path}", file=sys.stderr)
        return 1

    tx = pd.read_csv(tx_path, parse_dates=["transaction_date"])
    result = train_from_dataframe(tx, promote=True)
    reload_models()

    sample_user = str(tx["user_id"].iloc[0])
    forecast = generate_forecast(
        tx[tx["user_id"] == sample_user].to_dict(orient="records"),
        [],
        user_id=sample_user,
    )

    print("Train:", result)
    print("Sample user:", sample_user)
    print("Forecast success:", forecast.get("success"))
    print("Predicted 4 weeks:", forecast.get("predicted_next_month"))
    print("Recent weekly avg:", forecast.get("recent_weekly_avg"))
    return 0 if forecast.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
