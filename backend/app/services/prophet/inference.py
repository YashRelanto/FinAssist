"""Production expense forecasting API (global Prophet + user share scaling)."""

from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.services.prophet.features import (
    MIN_MONTHS_FOR_FORECAST,
    category_weekly_breakdown,
    create_user_monthly,
    daily_expense_series,
    drop_incomplete_current_month,
    expenses_to_monthly,
    expenses_to_weekly,
    forecast_next_month,
    predict_user_amount,
    top_merchants,
    user_has_enough_history,
)
from app.services.prophet.paths import PRODUCTION_BUNDLE_PATH, PRODUCTION_MANIFEST_PATH
from app.utils.analysis_period import (
    add_months,
    month_start,
    resolve_analysis_window,
    sum_expenses_in_window,
)

logger = logging.getLogger(__name__)

MODEL_NAME = "Prophet (global)"
MAX_HISTORY_WEEKS = 104
MAX_HISTORY_MONTHS = 36

_prophet_bundle: dict[str, Any] | None = None


def _resolve_bundle_path() -> Path | None:
    return PRODUCTION_BUNDLE_PATH if PRODUCTION_BUNDLE_PATH.is_file() else None


def _load_prophet_bundle() -> dict[str, Any] | None:
    global _prophet_bundle
    if _prophet_bundle is not None:
        return _prophet_bundle

    path = _resolve_bundle_path()
    if path is None:
        try:
            from app.core.config import settings
            from app.services.prophet.storage import sync_production_from_storage

            if settings.FORECAST_STORAGE_ENABLED:
                sync_production_from_storage(force=False)
                path = _resolve_bundle_path()
        except Exception as exc:
            logger.debug("Auto storage sync failed: %s", exc)

    if path is None:
        return None

    try:
        _prophet_bundle = joblib.load(path)
        logger.info("Loaded Prophet bundle from %s", path)
        return _prophet_bundle
    except Exception as exc:
        logger.error("Failed to load Prophet bundle: %s", exc)
        return None


def model_is_loaded() -> bool:
    bundle = _load_prophet_bundle()
    return bool(bundle and bundle.get("model") is not None)


def reload_models(*, force_storage_sync: bool = False) -> dict[str, Any]:
    global _prophet_bundle
    _prophet_bundle = None

    try:
        from app.core.config import settings
        from app.services.prophet.storage import sync_production_from_storage

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
            from app.services.prophet.storage import storage_manifest as read_storage_manifest

            storage_manifest = read_storage_manifest()
    except Exception:
        pass

    training_users = bundle.get("training_users", 0) if bundle else 0
    return {
        "loaded": model_is_loaded(),
        "trained_users": training_users,
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
    training_users = bundle.get("training_users", 0) if bundle else 0
    test_mape = bundle.get("test_mape") if bundle else manifest.get("test_mape")
    return {
        "model_type": "prophet",
        "model_name": MODEL_NAME,
        "scope": "global",
        "loaded": model_is_loaded(),
        "granularity": "monthly",
        "trained_users": training_users,
        "trained_at": bundle.get("trained_at") if bundle else manifest.get("trained_at"),
        "test_mape": test_mape,
        "accuracy_pct": _accuracy_from_mape(test_mape),
        "bundle_path": str(path) if path else None,
        "min_months_required": MIN_MONTHS_FOR_FORECAST,
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
        from app.services.prophet.storage import storage_manifest

        return storage_manifest()
    except Exception:
        return {}


def _accuracy_from_mape(mape: float | None) -> float | None:
    if mape is None:
        return None
    capped = min(max(float(mape), 0.0), 1.0)
    return round((1.0 - capped) * 100, 1)


def _predict_next_month(user_id: str, expenses_df: pd.DataFrame) -> float:
    bundle = _load_prophet_bundle()
    if bundle is None or bundle.get("model") is None:
        raise RuntimeError(
            "Forecast model not loaded. Run the nightly training job or POST /api/admin/train-from-db"
        )

    user_monthly = drop_incomplete_current_month(
        create_user_monthly(expenses_df.assign(user_id=str(user_id))),
        date_col="month_start",
    )
    return predict_user_amount(
        forecast_next_month(bundle["model"]),
        user_id,
        user_monthly,
        user_shares=bundle.get("user_shares") or {},
    )


def _trim_weekly_history(weekly: pd.DataFrame) -> pd.DataFrame:
    w = weekly.sort_values("week_start").reset_index(drop=True)
    return w.tail(MAX_HISTORY_WEEKS).reset_index(drop=True) if len(w) > MAX_HISTORY_WEEKS else w


def _trim_monthly_history(monthly: pd.DataFrame) -> pd.DataFrame:
    m = monthly.sort_values("month_start").reset_index(drop=True)
    return m.tail(MAX_HISTORY_MONTHS).reset_index(drop=True) if len(m) > MAX_HISTORY_MONTHS else m


def _build_predicted_month(amount: float, pred_start: date) -> dict[str, Any]:
    last_day = calendar.monthrange(pred_start.year, pred_start.month)[1]
    pred_end = date(pred_start.year, pred_start.month, last_day)
    return {
        "month": pred_start.strftime("%Y-%m"),
        "label": pred_start.strftime("%B %Y"),
        "month_start": pred_start.isoformat(),
        "month_end": pred_end.isoformat(),
        "amount": round(float(amount), 2),
    }


def _next_calendar_month_bounds(reference: date) -> tuple[date, date]:
    first = add_months(month_start(reference), 1)
    last_day = calendar.monthrange(first.year, first.month)[1]
    return first, date(first.year, first.month, last_day)


def _expenses_by_calendar_month(
    expenses: pd.DataFrame,
    *,
    start: date | None,
    end: date,
) -> list[dict[str, Any]]:
    if expenses.empty:
        return []
    df = expenses.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = df["amount"].astype(float).abs()
    if start is None:
        start = df["transaction_date"].min().date()
    cursor = month_start(start)
    end_m = month_start(end)
    rows: list[dict[str, Any]] = []
    while cursor <= end_m:
        month_end_day = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, month_end_day)
        slice_end = min(month_end, end)
        mask = (df["transaction_date"].dt.date >= cursor) & (
            df["transaction_date"].dt.date <= slice_end
        )
        total = float(df.loc[mask, "amount"].sum()) if mask.any() else 0.0
        is_partial = slice_end < month_end
        label = cursor.strftime("%b %Y")
        if is_partial and cursor == end_m:
            label += " (MTD)"
        rows.append(
            {
                "month": cursor.strftime("%Y-%m"),
                "label": label,
                "month_start": cursor.isoformat(),
                "month_end": slice_end.isoformat(),
                "value": round(total, 2),
                "is_forecast": False,
                "is_partial": is_partial,
            }
        )
        cursor = add_months(cursor, 1)
    return rows


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
    return {"count": len(recurring), "monthly_total": round(float(sum(recurring)), 2)}


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
    period: str = "1m",
) -> dict[str, Any]:
    meta = _model_meta()
    window = resolve_analysis_window(period)
    today = date.today()
    period_end = window["end_date"]
    period_start = window["start_date"]
    comp_start = window["comparison_start_date"]
    comp_end = window["comparison_end_date"]

    cat_df = pd.DataFrame(categories) if categories else pd.DataFrame()
    tx_df = pd.DataFrame(transactions) if transactions else pd.DataFrame()

    if tx_df.empty:
        return _empty_response("Not enough transaction history to forecast.", meta, window=window)

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
    tx_rows = tx_df.to_dict(orient="records")
    total_recent = sum_expenses_in_window(tx_rows, start_date=period_start, end_date=period_end)
    total_prev = (
        sum_expenses_in_window(tx_rows, start_date=comp_start, end_date=comp_end)
        if comp_start and comp_end
        else 0.0
    )
    change_pct = round((total_recent - total_prev) / total_prev * 100, 1) if total_prev > 0 else 0.0

    period_start_date = (
        datetime.strptime(period_start, "%Y-%m-%d").date()
        if period_start
        else tx_df["transaction_date"].min().date()
    )
    period_end_date = datetime.strptime(period_end, "%Y-%m-%d").date()
    recent = tx_df[
        (tx_df["transaction_date"].dt.date >= period_start_date)
        & (tx_df["transaction_date"].dt.date <= period_end_date)
    ].copy()

    weekly_full = expenses_to_weekly(tx_df)
    weekly = _trim_weekly_history(weekly_full)
    monthly_full = expenses_to_monthly(tx_df)
    monthly = _trim_monthly_history(monthly_full)

    period_partial = {
        **window,
        "total_analyzed_spending": total_recent,
        "period_change_pct": change_pct,
        "history_months": len(monthly_full),
        "min_months_required": MIN_MONTHS_FOR_FORECAST,
        "merchants": top_merchants(recent),
        "heatmap": daily_expense_series(recent, days=max((today - period_start_date).days + 1, 7)),
        "monthly_chart": _expenses_by_calendar_month(
            recent, start=period_start_date, end=period_end_date
        ),
    }

    if not user_has_enough_history(tx_df):
        return _empty_response(
            f"Need at least {MIN_MONTHS_FOR_FORECAST} months of expenses. "
            f"Currently have {len(monthly)} month(s).",
            meta,
            partial=period_partial,
            window=window,
        )

    if not model_is_loaded():
        return _empty_response(
            "Forecast models are not loaded yet. The nightly training job has not run.",
            meta,
            partial=period_partial,
            window=window,
        )

    next_start, _ = _next_calendar_month_bounds(today)
    try:
        predicted_amount = _predict_next_month(user_id, tx_df)
    except (RuntimeError, KeyError) as exc:
        return _empty_response(str(exc), meta, window=window)

    predicted_month_dict = _build_predicted_month(predicted_amount, next_start)
    predicted_month = predicted_month_dict["amount"]
    prev_period_spend = total_prev if total_prev > 0 else total_recent
    budget_alert = predicted_month > prev_period_spend * 1.1 and prev_period_spend > 0

    monthly_chart = [
        {
            "name": m["label"],
            "month": m["month"],
            "month_start": m["month_start"],
            "month_end": m["month_end"],
            "date_range": m["label"],
            "value": m["value"],
            "is_forecast": False,
            "is_partial": m.get("is_partial", False),
        }
        for m in _expenses_by_calendar_month(recent, start=period_start_date, end=period_end_date)
    ]
    monthly_chart.append(
        {
            "name": predicted_month_dict["label"] + " (predicted)",
            "month": predicted_month_dict["month"],
            "month_start": predicted_month_dict["month_start"],
            "month_end": predicted_month_dict["month_end"],
            "date_range": predicted_month_dict["label"],
            "value": predicted_month_dict["amount"],
            "is_forecast": True,
            "is_partial": False,
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

    comp_label = (
        f"previous {window['months_in_window']} month(s)"
        if window.get("months_in_window")
        else "previous period"
    )

    return {
        "success": True,
        **meta,
        **window,
        "accuracy_pct": meta.get("accuracy_pct"),
        "model_status": get_model_status(),
        "user_model_available": True,
        "enough_history": True,
        "history_weeks": len(weekly_full),
        "history_months": len(monthly_full),
        "weeks_used_for_model": len(weekly),
        "months_used_for_model": len(monthly),
        "prev_period_spend": round(prev_period_spend, 2),
        "prev_month_spend": round(prev_period_spend, 2),
        "total_analyzed_spending": total_recent,
        "period_change_pct": change_pct,
        "period_change_direction": "down" if change_pct < 0 else "up",
        "predicted_next_month": predicted_month,
        "predicted_month_start": predicted_month_dict["month_start"],
        "predicted_month_end": predicted_month_dict["month_end"],
        "predicted_months": [predicted_month_dict],
        "budget_alert": budget_alert,
        "budget_alert_message": (
            f"Predicted spend for {predicted_month_dict['label']} ({round(predicted_month, 0):,.0f}) "
            f"is 10%+ above your {comp_label} ({round(prev_period_spend, 0):,.0f})"
            if budget_alert
            else None
        ),
        "monthly_chart": monthly_chart,
        "category_chart": category_chart,
        "top_categories": [{"name": c, "value": round(v, 2)} for c, v in top_cats],
        "merchants": top_merchants(recent),
        "heatmap": daily_expense_series(recent, days=max((today - period_start_date).days + 1, 7)),
        "flow": {
            "accounts_total": total_recent,
            "active_categories": int(recent["category_id"].nunique()) if "category_id" in recent.columns else 0,
            "identified_merchants": int(recent["merchant_name"].nunique()) if "merchant_name" in recent.columns else 0,
        },
        "insights": {
            "outlier": _detect_outlier(recent),
            "recurring": _detect_recurring(tx_df),
        },
    }


def _empty_response(
    message: str,
    meta: dict[str, Any],
    partial: dict | None = None,
    *,
    window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = {
        "success": False,
        "message": message,
        **meta,
        **(window or resolve_analysis_window()),
        "model_status": get_model_status(),
        "user_model_available": False,
        "enough_history": False,
        "total_analyzed_spending": 0.0,
        "period_change_pct": 0.0,
        "monthly_chart": [],
        "predicted_months": [],
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
