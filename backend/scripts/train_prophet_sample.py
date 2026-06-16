#!/usr/bin/env python3
"""Train Prophet bundle from data/processed/transactions.csv (dev / smoke test)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.prophet.inference import generate_forecast, reload_models  # noqa: E402
from app.services.prophet.training import finalize_production_deployment, train_from_dataframe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Promote staging bundle to production after training",
    )
    args = parser.parse_args()

    tx_path = ROOT / "data" / "processed" / "transactions.csv"
    if not tx_path.is_file():
        print(f"Missing {tx_path}", file=sys.stderr)
        return 1

    tx = pd.read_csv(tx_path, parse_dates=["transaction_date"])
    result = train_from_dataframe(tx, promote=False)
    if args.deploy:
        finalize_production_deployment()
        result["production_path"] = str(
            ROOT / "models" / "prophet" / "production" / "expense_forecast_prophet.joblib",
        )
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
    print("Predicted next month:", forecast.get("predicted_next_month"))
    return 0 if forecast.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
