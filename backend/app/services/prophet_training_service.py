"""Train per-user Prophet models from Supabase (or in-memory DataFrames) for production."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd

from app.services.forecast_features import (
    MIN_DAYS_FOR_PROPHET_USER,
    MIN_WEEKS_FOR_PROPHET_USER,
    create_prophet_model_daily,
    expenses_to_daily,
    expenses_to_weekly,
    prophet_holdout_mape,
    prophet_holdout_mape_daily,
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"
STAGING_DIR = MODELS_DIR / "staging"
PRODUCTION_DIR = MODELS_DIR / "production"

STAGING_BUNDLE_PATH = STAGING_DIR / "expense_forecast_prophet.joblib"
PRODUCTION_BUNDLE_PATH = PRODUCTION_DIR / "expense_forecast_prophet.joblib"
PRODUCTION_MANIFEST_PATH = PRODUCTION_DIR / "manifest.json"

BUNDLE_FILENAME = "expense_forecast_prophet.joblib"
HORIZON_WEEKS = 4

LogFn = Callable[[str], None] | None


def _default_log(msg: str) -> None:
    logger.info(msg)


def fetch_expense_transactions_from_db() -> pd.DataFrame:
    """Load all expense transactions from Supabase."""
    from app.utils.supabase_client import supabase

    if supabase is None:
        raise RuntimeError("Supabase is not configured (SUPABASE_URL / service role key missing)")

    rows: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        res = (
            supabase.table("transactions")
            .select("user_id,transaction_date,amount,transaction_type")
            .eq("transaction_type", "expense")
            .order("transaction_date")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = res.data or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    if not rows:
        return pd.DataFrame(
            columns=["user_id", "transaction_date", "amount", "transaction_type"],
        )

    df = pd.DataFrame(rows)
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = df["amount"].astype(float).abs()
    return df


def train_prophet_bundle_from_transactions(
    transactions: pd.DataFrame,
    *,
    log: LogFn = None,
) -> dict[str, Any]:
    """
    Fit one Prophet model per user with enough weekly history.
    Returns the bundle dict (not yet written to disk).
    """
    emit = log or _default_log

    if transactions.empty:
        raise ValueError("No transactions provided for training")

    tx = transactions.copy()
    if "transaction_type" in tx.columns:
        tx = tx[tx["transaction_type"] == "expense"].copy()
    if tx.empty:
        raise ValueError("No expense transactions to train on")

    if "user_id" not in tx.columns:
        raise ValueError("transactions must include user_id")

    per_user_models: dict[str, Any] = {}
    per_user_mapes: list[float] = []
    skipped_users: list[dict[str, Any]] = []

    for user_id, group in tx.groupby("user_id"):
        uid = str(user_id)

        # Build daily series (zero-fills gaps between first and last date)
        daily = expenses_to_daily(group)
        day_count = len(daily)

        if day_count < MIN_DAYS_FOR_PROPHET_USER:
            skipped_users.append(
                {"user_id": uid, "days": day_count, "reason": "insufficient_days"}
            )
            continue

        # Compute 7-day hold-out MAPE for evaluation
        mape = prophet_holdout_mape_daily(daily)
        if mape is not None:
            per_user_mapes.append(mape)

        d = daily.sort_values("date").reset_index(drop=True)
        train_df = pd.DataFrame(
            {
                "ds": d["date"],
                # clip at 0 to avoid log-scale issues with zero-spend days
                "y": d["daily_expense"].clip(lower=0.0),
            }
        )
        model = create_prophet_model_daily(len(train_df))
        model.fit(train_df)
        per_user_models[uid] = model
        emit(f"Trained daily Prophet for user {uid[:8]}… ({day_count} days)")

    if not per_user_models:
        raise ValueError(
            f"No users met the minimum of {MIN_DAYS_FOR_PROPHET_USER} days of expense history",
        )

    trained_at = datetime.now(timezone.utc).isoformat()
    bundle = {
        "model_name": "Prophet",
        "model_type": "prophet",
        "granularity": "daily",          # <-- tells forecast_service this is a daily model
        "per_user": per_user_models,
        "test_mape": float(np.mean(per_user_mapes)) if per_user_mapes else None,
        "horizon_weeks": HORIZON_WEEKS,
        "trained_users": len(per_user_models),
        "trained_at": trained_at,
        "min_days": MIN_DAYS_FOR_PROPHET_USER,
        "skipped_users": skipped_users,
    }
    return bundle


def write_bundle(bundle: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)


def _record_training_run(bundle: dict[str, Any], storage_refs: dict[str, str] | None) -> None:
    try:
        from app.core.config import settings
        from app.utils.supabase_client import supabase

        if supabase is None:
            return
        supabase.table("forecast_model_runs").insert(
            {
                "trained_at": bundle.get("trained_at"),
                "trained_users": bundle.get("trained_users"),
                "test_mape": bundle.get("test_mape"),
                "storage_bucket": (storage_refs or {}).get("bucket", settings.FORECAST_STORAGE_BUCKET),
                "storage_bundle_key": (storage_refs or {}).get(
                    "bundle_key",
                    "production/expense_forecast_prophet.joblib",
                ),
                "status": "completed",
            },
        ).execute()
    except Exception as exc:
        logger.debug("forecast_model_runs insert skipped: %s", exc)


def write_manifest(bundle: dict[str, Any], path: Path = PRODUCTION_MANIFEST_PATH) -> dict[str, Any]:
    per_user: dict = bundle.get("per_user", {})
    manifest = {
        "model_type": "prophet",
        "trained_at": bundle.get("trained_at"),
        "trained_users": bundle.get("trained_users"),
        "horizon_weeks": bundle.get("horizon_weeks"),
        "min_weeks": bundle.get("min_weeks"),
        "test_mape": bundle.get("test_mape"),
        "user_ids": sorted(per_user.keys()),
        "skipped_count": len(bundle.get("skipped_users") or []),
        "bundle_path": str(PRODUCTION_BUNDLE_PATH),
    }
    from app.core.config import settings

    if settings.FORECAST_STORAGE_ENABLED:
        manifest["storage_bucket"] = settings.FORECAST_STORAGE_BUCKET
        manifest["storage_bundle_key"] = f"production/{BUNDLE_FILENAME}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def promote_staging_to_production() -> dict[str, Any]:
    """Atomically promote staging bundle + write manifest."""
    if not STAGING_BUNDLE_PATH.is_file():
        raise FileNotFoundError(f"Staging bundle missing: {STAGING_BUNDLE_PATH}")

    PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PRODUCTION_BUNDLE_PATH.with_suffix(".joblib.tmp")
    shutil.copy2(STAGING_BUNDLE_PATH, tmp)
    tmp.replace(PRODUCTION_BUNDLE_PATH)

    bundle = joblib.load(PRODUCTION_BUNDLE_PATH)
    manifest = write_manifest(bundle)
    logger.info("Promoted Prophet bundle to production (%s users)", manifest["trained_users"])
    return manifest


def run_training_pipeline(
    *,
    promote: bool = True,
    log: LogFn = None,
) -> dict[str, Any]:
    """
    Full nightly pipeline: fetch DB → train → staging → production.
    """
    emit = log or _default_log
    emit("Fetching expense transactions from database…")
    transactions = fetch_expense_transactions_from_db()
    emit(f"Loaded {len(transactions)} expense rows for {transactions['user_id'].nunique()} users")

    bundle = train_prophet_bundle_from_transactions(transactions, log=log)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    write_bundle(bundle, STAGING_BUNDLE_PATH)
    emit(f"Wrote staging bundle ({bundle['trained_users']} users)")

    result: dict[str, Any] = {
        "trained_users": bundle["trained_users"],
        "test_mape": bundle.get("test_mape"),
        "trained_at": bundle["trained_at"],
        "staging_path": str(STAGING_BUNDLE_PATH),
    }

    if promote:
        manifest = promote_staging_to_production()
        result["production_path"] = str(PRODUCTION_BUNDLE_PATH)
        result["manifest"] = manifest
        try:
            from app.services.model_monitoring_service import save_training_baseline_from_db

            save_training_baseline_from_db()
        except Exception as exc:
            emit(f"Baseline metadata skipped: {exc}")

        try:
            from app.core.config import settings
            from app.services.model_storage_service import upload_production_artifacts

            if settings.FORECAST_STORAGE_ENABLED:
                storage_refs = upload_production_artifacts()
                result["storage"] = storage_refs
                _record_training_run(bundle, storage_refs)
                emit(f"Uploaded production bundle to Supabase Storage ({storage_refs['bucket']})")
        except Exception as exc:
            emit(f"Storage upload failed: {exc}")
            raise

    return result


def train_from_dataframe(
    transactions: pd.DataFrame,
    *,
    output_dir: Path | None = None,
    promote: bool = True,
) -> dict[str, Any]:
    """Train from an in-memory DataFrame (tests / manual runs)."""
    bundle = train_prophet_bundle_from_transactions(transactions)
    out_dir = output_dir or PRODUCTION_DIR
    staging = out_dir.parent / "staging" if output_dir else STAGING_DIR
    production = out_dir

    staging.mkdir(parents=True, exist_ok=True)
    production.mkdir(parents=True, exist_ok=True)

    staging_path = staging / BUNDLE_FILENAME
    write_bundle(bundle, staging_path)

    if promote:
        prod_path = production / BUNDLE_FILENAME
        tmp = prod_path.with_suffix(".joblib.tmp")
        shutil.copy2(staging_path, tmp)
        tmp.replace(prod_path)
        write_manifest(bundle, production / "manifest.json")
        return {
            "trained_users": bundle["trained_users"],
            "production_path": str(prod_path),
            "manifest_path": str(production / "manifest.json"),
        }

    return {"trained_users": bundle["trained_users"], "staging_path": str(staging_path)}
