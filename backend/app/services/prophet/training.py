"""Train and deploy the global Prophet expense forecast model."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import pandas as pd

from app.services.prophet.features import (
    MIN_MONTHS_FOR_PROPHET_USER,
    calculate_holdout_mape,
    calculate_mape_walk_forward,
    cap_all_outliers,
    create_global_monthly,
    create_prophet_df,
    create_user_monthly,
    drop_incomplete_current_month,
    filter_expenses,
    forecast_next_month,
    get_recent_6_month_shares,
    prepare_global_training_expenses,
    train_prophet,
)
from app.services.prophet.paths import (
    BUNDLE_FILENAME,
    MODEL_ID,
    PRODUCTION_BUNDLE_PATH,
    PRODUCTION_DIR,
    PRODUCTION_MANIFEST_PATH,
    STAGING_BUNDLE_PATH,
    STAGING_DIR,
)

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None] | None


def _default_log(msg: str) -> None:
    logger.info(msg)


def fetch_expense_transactions_from_db(
    *,
    as_of: datetime | str | None = None,
) -> pd.DataFrame:
    from app.utils.supabase_client import supabase

    if supabase is None:
        raise RuntimeError("Supabase is not configured (SUPABASE_URL / service role key missing)")

    as_of_date: str | None = None
    if as_of is not None:
        if isinstance(as_of, str):
            as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        else:
            as_of_dt = as_of
        as_of_date = as_of_dt.date().isoformat()

    rows: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        query = (
            supabase.table("transactions")
            .select("user_id,transaction_date,amount,transaction_type")
            .eq("transaction_type", "expense")
            .order("transaction_date")
        )
        if as_of_date:
            query = query.lte("transaction_date", as_of_date)
        res = query.range(offset, offset + page_size - 1).execute()
        batch = res.data or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    if not rows:
        return pd.DataFrame(columns=["user_id", "transaction_date", "amount", "transaction_type"])

    return filter_expenses(pd.DataFrame(rows))


def _build_training_frames(transactions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    tx = cap_all_outliers(prepare_global_training_expenses(transactions))
    user_monthly = drop_incomplete_current_month(
        create_user_monthly(tx),
        date_col="month_start",
    )
    return tx, user_monthly


def train_bundle(transactions: pd.DataFrame, *, log: LogFn = None) -> dict[str, Any]:
    emit = log or _default_log

    if transactions.empty:
        raise ValueError("No transactions provided for training")
    if "user_id" not in transactions.columns:
        raise ValueError("transactions must include user_id")

    tx, user_monthly = _build_training_frames(transactions)
    if tx.empty:
        raise ValueError(
            f"No expense transactions from users with >={MIN_MONTHS_FOR_PROPHET_USER} "
            "months of history",
        )

    training_users = int(tx["user_id"].nunique())
    month_count = int(user_monthly["month_start"].nunique())
    if month_count < MIN_MONTHS_FOR_PROPHET_USER:
        raise ValueError(
            f"Need at least {MIN_MONTHS_FOR_PROPHET_USER} complete months; got {month_count}",
        )

    emit(
        f"Training pool: {len(tx)} expense row(s) from {training_users} user(s), "
        f"{month_count} complete month(s)",
    )

    mape: float | None = None
    try:
        if month_count >= 7:
            mape, _ = calculate_mape_walk_forward(user_monthly)
            emit(f"Walk-forward MAPE: {mape:.1%}")
        else:
            mape = calculate_holdout_mape(user_monthly)
            if mape is not None:
                emit(f"Hold-out MAPE: {mape:.1%}")
    except Exception as exc:
        emit(f"MAPE evaluation skipped: {exc}")

    global_monthly = create_global_monthly(user_monthly)
    prophet_df = create_prophet_df(global_monthly)
    model = train_prophet(prophet_df)
    global_prediction = forecast_next_month(model)
    emit(f"Trained global Prophet on {len(prophet_df)} month(s); next-month global={global_prediction:,.2f}")

    user_shares = {
        str(uid): float(share)
        for uid, share in get_recent_6_month_shares(user_monthly).items()
    }

    return {
        "model_name": "Prophet",
        "model_type": MODEL_ID,
        "scope": "global",
        "granularity": "monthly",
        "model": model,
        "global_monthly": global_monthly.assign(
            month_start=global_monthly["month_start"].astype(str),
        )[["month_start", "monthly_expense"]].to_dict(orient="records"),
        "user_shares": user_shares,
        "test_mape": mape,
        "training_users": training_users,
        "trained_users": training_users,
        "trained_transactions": int(len(tx)),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "min_months": MIN_MONTHS_FOR_PROPHET_USER,
        "complete_months": month_count,
    }


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
    from app.core.config import settings

    manifest = {
        "model_type": bundle.get("model_type", MODEL_ID),
        "scope": bundle.get("scope", "global"),
        "trained_at": bundle.get("trained_at"),
        "trained_users": bundle.get("trained_users"),
        "trained_transactions": bundle.get("trained_transactions"),
        "training_users": bundle.get("training_users", bundle.get("trained_users")),
        "min_months": bundle.get("min_months"),
        "test_mape": bundle.get("test_mape"),
        "global_months": len(bundle.get("global_monthly") or []),
        "complete_months": bundle.get("complete_months"),
        "bundle_path": str(PRODUCTION_BUNDLE_PATH),
    }
    if settings.FORECAST_STORAGE_ENABLED:
        manifest["storage_bucket"] = settings.FORECAST_STORAGE_BUCKET
        manifest["storage_bundle_key"] = f"production/{BUNDLE_FILENAME}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def promote_staging_to_production() -> dict[str, Any]:
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


def finalize_production_deployment(*, log: LogFn = None) -> dict[str, Any]:
    emit = log or _default_log
    manifest = promote_staging_to_production()
    result: dict[str, Any] = {
        "manifest": manifest,
        "production_path": str(PRODUCTION_BUNDLE_PATH),
    }

    try:
        from app.services.prophet.monitoring import save_training_baseline_from_db

        save_training_baseline_from_db()
    except Exception as exc:
        emit(f"Baseline metadata skipped: {exc}")

    try:
        from app.core.config import settings
        from app.services.prophet.storage import upload_production_artifacts

        if settings.FORECAST_STORAGE_ENABLED:
            storage_refs = upload_production_artifacts()
            result["storage"] = storage_refs
            _record_training_run(joblib.load(PRODUCTION_BUNDLE_PATH), storage_refs)
            emit(f"Uploaded production bundle to Supabase Storage ({storage_refs['bucket']})")
    except Exception as exc:
        emit(f"Storage upload failed: {exc}")
        raise

    return result


def run_training_pipeline(*, promote: bool = False, log: LogFn = None) -> dict[str, Any]:
    emit = log or _default_log
    emit("Fetching expense transactions from database…")
    transactions = fetch_expense_transactions_from_db()
    emit(f"Loaded {len(transactions)} expense rows for {transactions['user_id'].nunique()} users")

    bundle = train_bundle(transactions, log=log)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    write_bundle(bundle, STAGING_BUNDLE_PATH)
    emit(f"Wrote staging bundle ({bundle['training_users']} training users)")

    result: dict[str, Any] = {
        "trained_users": bundle["trained_users"],
        "trained_transactions": bundle.get("trained_transactions"),
        "test_mape": bundle.get("test_mape"),
        "trained_at": bundle["trained_at"],
        "staging_path": str(STAGING_BUNDLE_PATH),
        "model_type": bundle.get("model_type"),
    }

    if promote:
        result.update(finalize_production_deployment(log=emit))

    return result


def train_from_dataframe(
    transactions: pd.DataFrame,
    *,
    output_dir: Path | None = None,
    promote: bool = False,
) -> dict[str, Any]:
    bundle = train_bundle(transactions)
    production = output_dir or PRODUCTION_DIR
    staging = production.parent / "staging" if output_dir else STAGING_DIR

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
            "test_mape": bundle.get("test_mape"),
            "production_path": str(prod_path),
            "manifest_path": str(production / "manifest.json"),
        }

    return {
        "trained_users": bundle["trained_users"],
        "test_mape": bundle.get("test_mape"),
        "staging_path": str(staging_path),
    }
