"""Model performance and drift — Prophet production bundle."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.services.forecast_features import expenses_to_weekly
from app.services.forecast_service import get_model_status
from app.services.prophet_training_service import (
    PRODUCTION_BUNDLE_PATH,
    PRODUCTION_MANIFEST_PATH,
    fetch_expense_transactions_from_db,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
METADATA_PATH = PROJECT_ROOT / "models" / "production" / "training_metadata.json"


def _load_metadata() -> dict[str, Any]:
    if not METADATA_PATH.is_file():
        return {}
    try:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_production_performance() -> dict[str, Any]:
    status = get_model_status()
    bundle_info = None
    if PRODUCTION_BUNDLE_PATH.is_file():
        try:
            stat = PRODUCTION_BUNDLE_PATH.stat()
            bundle = joblib.load(PRODUCTION_BUNDLE_PATH)
            bundle_info = {
                "path": str(PRODUCTION_BUNDLE_PATH),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "trained_users": bundle.get("training_users")
                or bundle.get("trained_users")
                or len(bundle.get("per_user", {})),
                "scope": bundle.get("scope", "global"),
                "test_mape": bundle.get("test_mape"),
                "trained_at": bundle.get("trained_at"),
            }
        except Exception:
            bundle_info = None

    manifest = {}
    if PRODUCTION_MANIFEST_PATH.is_file():
        try:
            manifest = json.loads(PRODUCTION_MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "status": status,
        "bundle": bundle_info,
        "manifest": manifest,
        "metadata": _load_metadata(),
    }


def compute_drift_stats() -> dict[str, Any]:
    metadata = _load_metadata()
    baseline = metadata.get("baseline_weekly") or {}
    baseline_mean = float(baseline.get("mean") or 0)
    baseline_std = float(baseline.get("std") or 1) or 1.0

    try:
        transactions = fetch_expense_transactions_from_db()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

    if transactions.empty:
        return {"status": "insufficient_data", "message": "No transactions in database"}

    weekly_means = []
    for _, group in transactions.groupby("user_id"):
        weekly = expenses_to_weekly(group)
        if not weekly.empty:
            weekly_means.append(float(weekly["weekly_expense"].mean()))

    if len(weekly_means) < 2:
        return {
            "status": "insufficient_data",
            "message": "Need more users/weeks for drift analysis",
        }

    recent_mean = float(pd.Series(weekly_means).mean())
    recent_std = float(pd.Series(weekly_means).std()) if len(weekly_means) > 1 else 0.0

    mean_shift_sigma = abs(recent_mean - baseline_mean) / baseline_std if baseline_std else 0.0
    std_ratio = recent_std / baseline_std if baseline_std else 1.0

    if mean_shift_sigma >= 2.0:
        drift_level = "high"
    elif mean_shift_sigma >= 1.0:
        drift_level = "medium"
    else:
        drift_level = "low"

    return {
        "status": "ok",
        "drift_level": drift_level,
        "mean_shift_sigma": round(mean_shift_sigma, 3),
        "std_ratio": round(std_ratio, 3),
        "baseline": {"mean": round(baseline_mean, 2), "std": round(baseline_std, 2)},
        "recent": {"mean": round(recent_mean, 2), "std": round(recent_std, 2)},
        "recommendation": (
            "Retrain recommended — spending levels shifted vs last training baseline"
            if drift_level == "high"
            else "Monitor drift"
            if drift_level == "medium"
            else "Stable"
        ),
    }


def save_training_baseline_from_db() -> None:
    """Persist aggregate weekly spend baseline after training."""
    try:
        transactions = fetch_expense_transactions_from_db()
    except Exception:
        return
    if transactions.empty:
        return

    vals = []
    for _, group in transactions.groupby("user_id"):
        weekly = expenses_to_weekly(group)
        if not weekly.empty:
            vals.extend(weekly["weekly_expense"].astype(float).tolist())

    if not vals:
        return

    series = pd.Series(vals)
    metadata = _load_metadata()
    metadata["baseline_weekly"] = {
        "mean": float(series.mean()),
        "std": float(series.std()) if len(series) > 1 else 0.0,
        "weeks": len(series),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
