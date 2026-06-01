"""Production expense forecasting using per-user Prophet models."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.services.forecast_features import (
    MIN_WEEKS_FOR_FORECAST,
    category_weekly_breakdown,
    daily_expense_series,
    expenses_to_weekly,
    prophet_future_frame,
    prophet_predict_weeks,
    safe_mape,
    top_merchants,
)
from app.services.prophet_training_service import (
    PRODUCTION_BUNDLE_PATH,
    PRODUCTION_MANIFEST_PATH,
    PRODUCTION_DIR,
)

logger = logging.getLogger(__name__)

MODEL_NAME = "Prophet (per user)"
HORIZON_WEEKS = 4
MAX_HISTORY_WEEKS = 104

_prophet_bundle: dict[str, Any] | None = None


def _resolve_bundle_path() -> Path | None:
    if PRODUCTION_BUNDLE_PATH.is_file():
        return PRODUCTION_BUNDLE_PATH
    return None


def _load_prophet_bundle() -> dict[str, Any] | None:
    global _prophet_bundle
    if _prophet_bundle is not None:
        return _prophet_bundle

    path = _resolve_bundle_path()
    if path is None:
        try:
            from app.core.config import settings
            from app.services.model_storage_service import sync_production_from_storage

            if settings.FORECAST_STORAGE_ENABLED:
                sync_production_from_storage(force=False)
                path = _resolve_bundle_path()
        except Exception as exc:
            logger.debug("Auto storage sync failed: %s", exc)

    if path is None:
        return None

    try:
        _prophet_bundle = joblib.load(path)
        logger.info("Loaded per-user Prophet bundle from %s", path)
        return _prophet_bundle
    except Exception as exc:
        logger.error("Failed to load Prophet bundle: %s", exc)
        return None


def model_is_loaded() -> bool:
    bundle = _load_prophet_bundle()
    return bundle is not None and bool(bundle.get("per_user"))


def reload_models(*, force_storage_sync: bool = False) -> dict[str, Any]:
    global _prophet_bundle
    _prophet_bundle = None

    try:
        from app.core.config import settings
        from app.services.model_storage_service import sync_production_from_storage

        if settings.FORECAST_STORAGE_ENABLED:
            sync_production_from_storage(force=force_storage_sync)
    except Exception as exc:
        logger.warning("Storage sync on reload skipped: %s", exc)

    bundle = _load_prophet_bundle()
    manifest = get_production_manifest()
    storage_manifest: dict[str, Any] = {}
    try:
        from app.core.config import settings
        if settings.FORECAST_STORAGE_ENABLED:
            from app.services.model_storage_service import storage_manifest as read_storage_manifest

            storage_manifest = read_storage_manifest()
    except Exception:
        pass

    return {
        "loaded": bundle is not None,
        "trained_users": len(bundle.get("per_user", {})) if bundle else 0,
        "trained_at": bundle.get("trained_at") if bundle else None,
        "manifest": manifest,
        "storage_manifest": storage_manifest,
    }


def get_production_manifest() -> dict[str, Any]:
    if not PRODUCTION_MANIFEST_PATH.is_file():
        return {}
    try:
        return json.loads(PRODUCTION_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_model_status() -> dict[str, Any]:
    bundle = _load_prophet_bundle()
    manifest = get_production_manifest()
    path = _resolve_bundle_path()
    return {
        "model_type": "prophet",
        "model_name": MODEL_NAME,
        "loaded": bundle is not None,
        "trained_users": len(bundle.get("per_user", {})) if bundle else 0,
        "trained_at": bundle.get("trained_at") if bundle else manifest.get("trained_at"),
        "test_mape": bundle.get("test_mape") if bundle else manifest.get("test_mape"),
        "accuracy_pct": _accuracy_from_mape(
            bundle.get("test_mape") if bundle else manifest.get("test_mape"),
        ),
        "bundle_path": str(path) if path else None,
        "horizon_weeks": HORIZON_WEEKS,
        "min_weeks_required": MIN_WEEKS_FOR_FORECAST,
        "manifest": manifest,
        "storage_enabled": _storage_enabled(),
        "storage_manifest": _safe_storage_manifest(),
    }


def _storage_enabled() -> bool:
    try:
        from app.core.config import settings

        return settings.FORECAST_STORAGE_ENABLED
    except Exception:
        return False


def _safe_storage_manifest() -> dict[str, Any]:
    try:
        from app.services.model_storage_service import storage_manifest

        return storage_manifest()
    except Exception:
        return {}


def _accuracy_from_mape(mape: float | None) -> float | None:
    if mape is None:
        return None
    capped = min(max(float(mape), 0.0), 1.0)
    return round((1.0 - capped) * 100, 1)


def _user_has_trained_model(user_id: str) -> bool:
    bundle = _load_prophet_bundle()
    if not bundle:
        return False
    return str(user_id) in bundle.get("per_user", {})


def _prophet_forecast_for_user(weekly: pd.DataFrame, user_id: str, steps: int) -> list[float]:
    bundle = _load_prophet_bundle()
    if bundle is None:
        raise RuntimeError(
            "Forecast model not loaded. Run the nightly training job or POST /api/admin/train-from-db",
        )

    model = bundle.get("per_user", {}).get(str(user_id))
    if model is None:
        raise KeyError(
            f"No trained Prophet model for user {user_id}. "
            "User needs more expense history or wait for the next nightly train.",
        )

    w = weekly.copy().sort_values("week_start").reset_index(drop=True)
    return prophet_predict_weeks(model, w, steps)


def _trim_weekly_history(weekly: pd.DataFrame) -> pd.DataFrame:
    w = weekly.sort_values("week_start").reset_index(drop=True)
    if len(w) <= MAX_HISTORY_WEEKS:
        return w
    return w.tail(MAX_HISTORY_WEEKS).reset_index(drop=True)


def _build_predicted_weeks(future_preds: list[float], weekly: pd.DataFrame) -> list[dict[str, Any]]:
    future = prophet_future_frame(weekly, len(future_preds))
    weeks: list[dict[str, Any]] = []
    for j, (pred, week_start) in enumerate(zip(future_preds, future["ds"], strict=True)):
        weeks.append(
            {
                "week": j + 1,
                "label": f"Week +{j + 1}",
                "week_start": pd.Timestamp(week_start).strftime("%Y-%m-%d"),
                "amount": round(float(pred), 2),
            },
        )
    return weeks


def _detect_outlier(expenses: pd.DataFrame) -> dict | None:
    if len(expenses) < 5:
        return None
    amounts = expenses["amount"].astype(float).abs()
    mean = amounts.mean()
    std = amounts.std()
    if std <= 0:
        return None
    idx = amounts.idxmax()
    row = expenses.loc[idx]
    val = float(amounts.loc[idx])
    if val < mean + 2 * std:
        return None
    return {
        "amount": round(val, 2),
        "merchant": row.get("merchant_name") or row.get("description") or "Unknown",
        "category": row.get("main_category", "Uncategorized"),
    }


def _detect_recurring(expenses: pd.DataFrame) -> dict | None:
    if expenses.empty:
        return None
    df = expenses.copy()
    df["amount"] = df["amount"].astype(float).abs()
    df["merchant_name"] = df["merchant_name"].fillna("Unknown")
    df["month"] = pd.to_datetime(df["transaction_date"]).dt.to_period("M")
    recurring = []
    for merchant, grp in df.groupby("merchant_name"):
        if grp["month"].nunique() >= 3 and len(grp) >= 3:
            amt_mean = grp["amount"].mean()
            if amt_mean > 0 and (grp["amount"].std() / amt_mean) < 0.15:
                recurring.append(amt_mean)
    if not recurring:
        return None
    return {
        "count": len(recurring),
        "monthly_total": round(float(sum(recurring)), 2),
    }


def _model_meta() -> dict[str, Any]:
    status = get_model_status()
    return {
        "model_type": "prophet",
        "model_name": status["model_name"],
        "model_loaded": status["loaded"],
        "accuracy_pct": status["accuracy_pct"],
        "trained_at": status["trained_at"],
        "trained_users_in_bundle": status["trained_users"],
    }


def generate_forecast(
    transactions: list[dict],
    categories: list[dict],
    *,
    user_id: str,
    account_id: str | None = None,
    category_id: str | None = None,
    merchant: str | None = None,
    days_analyzed: int = 30,
) -> dict[str, Any]:
    meta = _model_meta()
    cat_df = pd.DataFrame(categories) if categories else pd.DataFrame()
    tx_df = pd.DataFrame(transactions) if transactions else pd.DataFrame()

    if tx_df.empty:
        return _empty_response("Not enough transaction history to forecast.", meta)

    tx_df = tx_df[tx_df["transaction_type"] == "expense"].copy()
    if account_id:
        tx_df = tx_df[tx_df["account_id"] == account_id]
    if category_id:
        tx_df = tx_df[tx_df["category_id"] == category_id]
    if merchant:
        mask = tx_df["merchant_name"].fillna("").str.contains(merchant, case=False, na=False)
        tx_df = tx_df[mask]

    if not cat_df.empty and "category_id" in tx_df.columns:
        tx_df = tx_df.merge(
            cat_df[["category_id", "main_category", "sub_category"]],
            on="category_id",
            how="left",
        )

    tx_df["transaction_date"] = pd.to_datetime(tx_df["transaction_date"])
    end = tx_df["transaction_date"].max()
    start = end - timedelta(days=days_analyzed)
    recent = tx_df[tx_df["transaction_date"] >= start].copy()
    prev_start = start - timedelta(days=days_analyzed)
    previous = tx_df[(tx_df["transaction_date"] >= prev_start) & (tx_df["transaction_date"] < start)]

    total_recent = float(recent["amount"].astype(float).abs().sum()) if not recent.empty else 0.0
    total_prev = float(previous["amount"].astype(float).abs().sum()) if not previous.empty else 0.0
    change_pct = round((total_recent - total_prev) / total_prev * 100, 1) if total_prev > 0 else 0.0

    weekly_full = expenses_to_weekly(tx_df)
    weekly = _trim_weekly_history(weekly_full)
    enough_history = len(weekly) >= MIN_WEEKS_FOR_FORECAST

    if not enough_history:
        return _empty_response(
            f"Need at least {MIN_WEEKS_FOR_FORECAST} weeks of expenses (~2 months). "
            f"Currently have {len(weekly)} week(s).",
            meta,
            partial={
                "total_analyzed_spending": round(total_recent, 2),
                "period_change_pct": change_pct,
                "merchants": top_merchants(recent),
                "heatmap": daily_expense_series(recent),
            },
        )

    if not model_is_loaded():
        return _empty_response(
            "Forecast models are not loaded yet. The nightly training job has not run.",
            meta,
            partial={
                "total_analyzed_spending": round(total_recent, 2),
                "period_change_pct": change_pct,
            },
        )

    if not _user_has_trained_model(user_id):
        return _empty_response(
            "No Prophet model is available for your account yet. "
            f"You need at least {MIN_WEEKS_FOR_FORECAST} weeks of expenses; "
            "models are refreshed every night after the training job runs.",
            meta,
            partial={
                "total_analyzed_spending": round(total_recent, 2),
                "period_change_pct": change_pct,
                "merchants": top_merchants(recent),
                "heatmap": daily_expense_series(recent),
            },
        )

    try:
        future_preds = _prophet_forecast_for_user(weekly, user_id, HORIZON_WEEKS)
    except (RuntimeError, KeyError) as exc:
        return _empty_response(str(exc), meta)

    predicted_weeks = _build_predicted_weeks(future_preds, weekly)
    predicted_month = round(sum(w["amount"] for w in predicted_weeks), 2)
    avg_monthly = float(weekly["weekly_expense"].tail(4).sum())
    recent_weekly_mean = float(weekly["weekly_expense"].tail(4).mean())
    budget_alert = predicted_month > avg_monthly * 1.1

    holdout_mape = None
    if len(weekly) >= 10:
        hold = float(weekly.iloc[-1]["weekly_expense"])
        train_w = weekly.iloc[:-1]
        try:
            pred_hold = _prophet_forecast_for_user(train_w, user_id, 1)
            if pred_hold:
                holdout_mape = safe_mape([hold], pred_hold)
        except (RuntimeError, KeyError):
            holdout_mape = None

    last_weeks = weekly.tail(4).reset_index(drop=True)
    weekly_chart = []
    for i, row in last_weeks.iterrows():
        weekly_chart.append(
            {
                "name": f"Week {i + 1}",
                "value": round(float(row["weekly_expense"]), 2),
                "is_forecast": False,
            }
        )
    for j, pred in enumerate(future_preds):
        weekly_chart.append(
            {
                "name": f"Week +{j + 1}",
                "value": round(pred, 2),
                "is_forecast": True,
            }
        )

    category_chart = category_weekly_breakdown(
        recent,
        cat_df[["category_id", "main_category"]] if not cat_df.empty else pd.DataFrame(),
    )

    top_cats = []
    if category_chart:
        all_cats: dict[str, float] = {}
        for w in category_chart:
            for cat, val in w.get("by_category", {}).items():
                all_cats[cat] = all_cats.get(cat, 0.0) + val
        top_cats = sorted(all_cats.items(), key=lambda x: -x[1])[:3]

    display_accuracy = (
        _accuracy_from_mape(holdout_mape) if holdout_mape is not None else meta.get("accuracy_pct")
    )

    return {
        "success": True,
        **meta,
        "accuracy_pct": display_accuracy,
        "model_status": get_model_status(),
        "user_model_available": True,
        "enough_history": True,
        "history_weeks": len(weekly_full),
        "weeks_used_for_model": len(weekly),
        "recent_weekly_avg": round(recent_weekly_mean, 2),
        "total_analyzed_spending": round(total_recent, 2),
        "period_change_pct": change_pct,
        "period_change_direction": "down" if change_pct < 0 else "up",
        "predicted_next_month": predicted_month,
        "predicted_weeks": predicted_weeks,
        "budget_alert": budget_alert,
        "budget_alert_message": (
            "Spending is likely to exceed your recent monthly average"
            if budget_alert
            else None
        ),
        "weekly_chart": weekly_chart[-8:],
        "category_chart": category_chart,
        "top_categories": [{"name": c, "value": round(v, 2)} for c, v in top_cats],
        "merchants": top_merchants(recent),
        "heatmap": daily_expense_series(recent),
        "flow": {
            "accounts_total": round(total_recent, 2),
            "active_categories": int(recent["category_id"].nunique()) if "category_id" in recent.columns else 0,
            "identified_merchants": int(recent["merchant_name"].nunique()) if "merchant_name" in recent.columns else 0,
        },
        "insights": {
            "outlier": _detect_outlier(recent),
            "recurring": _detect_recurring(tx_df),
        },
        "horizon_weeks": HORIZON_WEEKS,
    }


def _empty_response(
    message: str,
    meta: dict[str, Any],
    partial: dict | None = None,
) -> dict[str, Any]:
    base = {
        "success": False,
        "message": message,
        **meta,
        "model_status": get_model_status(),
        "user_model_available": False,
        "enough_history": False,
        "total_analyzed_spending": 0.0,
        "period_change_pct": 0.0,
        "weekly_chart": [],
        "predicted_weeks": [],
        "category_chart": [],
        "merchants": [],
        "heatmap": [],
        "flow": {"accounts_total": 0, "active_categories": 0, "identified_merchants": 0},
        "insights": {"outlier": None, "recurring": None},
    }
    if partial:
        base.update(partial)
        base["success"] = True
    return base
