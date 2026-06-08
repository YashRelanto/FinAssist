"""Train a global Prophet model from Supabase (or in-memory DataFrames) for production."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import pandas as pd

from app.services.forecast_features import (
    MIN_MONTHS_FOR_PROPHET_USER,
    create_prophet_model_monthly,
    drop_incomplete_current_month,
    expenses_to_monthly,
    prophet_holdout_mape_monthly,
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
    Fit one global Prophet model on pooled monthly expense totals across all users.
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

    training_users = int(tx["user_id"].nunique())
    monthly_all = expenses_to_monthly(tx)
    month_count = len(monthly_all)

    if month_count < MIN_MONTHS_FOR_PROPHET_USER:
        raise ValueError(
            f"Need at least {MIN_MONTHS_FOR_PROPHET_USER} months of pooled expense history; "
            f"got {month_count}",
        )

    monthly = drop_incomplete_current_month(monthly_all)
    complete_month_count = len(monthly)
    if complete_month_count < 2:
        raise ValueError(
            "Need at least 2 complete calendar months after excluding the in-progress month",
        )

    mape = prophet_holdout_mape_monthly(monthly_all)
    if mape is None:
        emit(
            f"Hold-out MAPE unavailable ({complete_month_count} complete months; "
            "need 2+ complete months with positive last-month spend)",
        )
    else:
        emit(f"Hold-out test MAPE: {mape:.3f}")

    m = monthly.sort_values("month_start").reset_index(drop=True)
    train_df = pd.DataFrame(
        {
            "ds": m["month_start"],
            "y": m["monthly_expense"].clip(lower=1.0),
        }
    )
    model = create_prophet_model_monthly(len(train_df))
    model.fit(train_df)
    emit(
        f"Trained global monthly Prophet on {complete_month_count} complete month(s) "
        f"({month_count} calendar months incl. MTD) from {training_users} user(s)",
    )

    trained_at = datetime.now(timezone.utc).isoformat()
    global_monthly = m.assign(month_start=m["month_start"].astype(str))[
        ["month_start", "monthly_expense"]
    ].to_dict(orient="records")
    bundle = {
        "model_name": "Prophet",
        "model_type": "prophet",
        "scope": "global",
        "granularity": "monthly",
        "model": model,
        "global_monthly": global_monthly,
        "test_mape": mape,
        "horizon_weeks": HORIZON_WEEKS,
        "training_users": training_users,
        "trained_users": training_users,
        "trained_at": trained_at,
        "min_months": MIN_MONTHS_FOR_PROPHET_USER,
        "complete_months": complete_month_count,
        "calendar_months": month_count,
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
    manifest = {
        "model_type": "prophet",
        "scope": bundle.get("scope", "global"),
        "trained_at": bundle.get("trained_at"),
        "trained_users": bundle.get("trained_users"),
        "training_users": bundle.get("training_users", bundle.get("trained_users")),
        "horizon_weeks": bundle.get("horizon_weeks"),
        "min_weeks": bundle.get("min_weeks"),
        "min_months": bundle.get("min_months"),
        "test_mape": bundle.get("test_mape"),
        "global_months": len(bundle.get("global_monthly") or []),
        "complete_months": bundle.get("complete_months"),
        "calendar_months": bundle.get("calendar_months"),
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
    logger.info("Promoted Prophet bundle to production (%s training users)", manifest["trained_users"])
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
    emit(f"Wrote staging bundle (global model, {bundle['training_users']} training users)")

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
