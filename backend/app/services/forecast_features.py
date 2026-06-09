"""Shared feature engineering for expense forecasting (training + inference)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

MIN_WEEKS_FOR_FORECAST = 8
MIN_MONTHS_FOR_FORECAST = 6
MIN_MONTHS_FOR_PROPHET_USER = 6


def expenses_to_weekly(expenses: pd.DataFrame) -> pd.DataFrame:
    """Aggregate expense rows to ISO-week totals ordered by week start."""
    if expenses.empty:
        return pd.DataFrame(columns=["week_start", "weekly_expense"])

    df = expenses.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = df["amount"].astype(float).abs()
    iso = df["transaction_date"].dt.isocalendar()
    df["week_start"] = pd.to_datetime(
        iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2) + "-1",
        format="%G-W%V-%u",
    )
    weekly = (
        df.groupby("week_start", as_index=False)["amount"]
        .sum()
        .rename(columns={"amount": "weekly_expense"})
        .sort_values("week_start")
        .reset_index(drop=True)
    )
    return weekly


def daily_expense_series(expenses: pd.DataFrame, days: int = 35) -> list[dict]:
    """Last N days of daily spend for heatmap (0–5 intensity)."""
    if expenses.empty:
        return [{"date": None, "amount": 0.0, "intensity": 0} for _ in range(days)]

    df = expenses.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = df["amount"].astype(float).abs()
    end = df["transaction_date"].max().normalize()
    start = end - timedelta(days=days - 1)
    daily = (
        df.groupby(df["transaction_date"].dt.normalize())["amount"]
        .sum()
        .reindex(pd.date_range(start, end, freq="D"), fill_value=0.0)
    )
    amounts = daily.values
    max_amt = float(amounts.max()) if amounts.max() > 0 else 1.0
    result = []
    for dt, amt in zip(daily.index, amounts):
        intensity = int(min(5, round((amt / max_amt) * 5))) if amt > 0 else 0
        result.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "amount": round(float(amt), 2),
                "intensity": intensity,
            }
        )
    return result


def top_merchants(expenses: pd.DataFrame, limit: int = 3) -> list[dict]:
    if expenses.empty:
        return []

    df = expenses.copy()
    df["amount"] = df["amount"].astype(float).abs()
    df["merchant_name"] = df["merchant_name"].fillna(df.get("description", "")).replace("", "Unknown")
    grouped = (
        df.groupby("merchant_name")["amount"]
        .sum()
        .sort_values(ascending=False)
        .head(limit)
    )
    max_val = float(grouped.max()) if len(grouped) else 1.0
    return [
        {"name": name, "value": round(float(val), 2), "total": round(max_val, 2)}
        for name, val in grouped.items()
    ]


def category_weekly_breakdown(
    expenses: pd.DataFrame,
    categories: pd.DataFrame,
    weeks: int = 4,
) -> list[dict]:
    """Last N weeks total expense per main category (for chart legend)."""
    if expenses.empty:
        return []

    df = expenses.copy()
    if (
        "main_category" not in df.columns
        and not categories.empty
        and "category_id" in df.columns
    ):
        df = df.merge(
            categories[["category_id", "main_category"]],
            on="category_id",
            how="left",
        )
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = df["amount"].astype(float).abs()
    if "main_category" not in df.columns:
        df["main_category"] = "Other"
    else:
        df["main_category"] = df["main_category"].fillna("Other")

    end = df["transaction_date"].max()
    start = end - timedelta(weeks=weeks * 7)
    df = df[df["transaction_date"] >= start]

    iso = df["transaction_date"].dt.isocalendar()
    df["week_start"] = pd.to_datetime(
        iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2) + "-1",
        format="%G-W%V-%u",
    )
    week_labels = sorted(df["week_start"].unique())[-weeks:]
    chart = []
    for i, ws in enumerate(week_labels):
        chunk = df[df["week_start"] == ws]
        by_cat = chunk.groupby("main_category")["amount"].sum().to_dict()
        chart.append(
            {
                "name": f"Week {i + 1}",
                "value": round(float(chunk["amount"].sum()), 2),
                "by_category": {k: round(float(v), 2) for k, v in by_cat.items()},
            }
        )
    return chart


def prophet_future_frame(weekly: pd.DataFrame, steps: int) -> pd.DataFrame:
    w = weekly.sort_values("week_start").reset_index(drop=True)
    last = pd.Timestamp(w["week_start"].iloc[-1])
    dates = [last + timedelta(days=7 * (i + 1)) for i in range(steps)]
    return pd.DataFrame({"ds": dates})


def sanitize_prophet_predictions(raw: np.ndarray, weekly: pd.DataFrame) -> list[float]:
    floor = float(weekly["weekly_expense"].tail(4).mean())
    if floor <= 0:
        floor = float(weekly["weekly_expense"].mean())
    preds: list[float] = []
    for v in raw:
        y = float(v)
        if not np.isfinite(y) or y < 0:
            y = floor
        preds.append(max(0.0, y))
    if sum(preds) <= 0 and floor > 0:
        return [floor] * len(raw)
    return preds


def prophet_predict_weeks(model, weekly: pd.DataFrame, steps: int) -> list[float]:
    future = prophet_future_frame(weekly, steps)
    forecast = model.predict(future)
    return sanitize_prophet_predictions(forecast["yhat"].values, weekly)


def safe_mape(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """MAPE with floor on denominator so small targets do not explode the metric."""
    yt = np.asarray(list(y_true), dtype=float)
    yp = np.clip(np.asarray(list(y_pred), dtype=float), 0.0, None)
    if len(yt) == 0:
        return 1.0
    denom = np.maximum(np.abs(yt), np.median(yt[yt > 0]) if np.any(yt > 0) else 1.0)
    return float(np.mean(np.abs(yt - yp) / denom))


# ─────────────────────────────────────────────────────────────
# Daily-granularity helpers (inference fallbacks for legacy bundles)
# ─────────────────────────────────────────────────────────────

def expenses_to_daily(expenses: pd.DataFrame) -> pd.DataFrame:
    """Aggregate expense rows to daily totals with zero-filled date gaps."""
    if expenses.empty:
        return pd.DataFrame(columns=["date", "daily_expense"])
    df = expenses.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = df["amount"].astype(float).abs()
    agg = (
        df.groupby(df["transaction_date"].dt.normalize())["amount"]
        .sum()
        .reset_index()
        .rename(columns={"transaction_date": "date", "amount": "daily_expense"})
    )
    full_range = pd.date_range(agg["date"].min(), agg["date"].max(), freq="D")
    daily = agg.set_index("date").reindex(full_range, fill_value=0.0).reset_index()
    daily.columns = ["date", "daily_expense"]
    return daily.sort_values("date").reset_index(drop=True)


def prophet_future_frame_daily(last_date: pd.Timestamp, steps: int) -> pd.DataFrame:
    """Generate `steps` consecutive daily future dates starting after last_date."""
    dates = [last_date + timedelta(days=i + 1) for i in range(steps)]
    return pd.DataFrame({"ds": dates})


def sanitize_daily_predictions(raw: np.ndarray, daily: pd.DataFrame) -> list[float]:
    """Floor negative / non-finite daily predictions to the recent daily mean."""
    floor = max(float(daily["daily_expense"].tail(28).mean()), 0.0)
    preds: list[float] = []
    for v in raw:
        y = float(v)
        if not np.isfinite(y) or y < 0:
            y = floor
        preds.append(max(0.0, y))
    return preds


def dow_spending_ratios(expenses: pd.DataFrame, lookback_weeks: int = 8) -> list[float]:
    """
    Return a 7-element list of daily spend fractions [Mon … Sun] that sum to 1.0.
    Used to distribute weekly totals when only a weekly-trained model is available
    (backward-compatibility fallback).
    Defaults to a weekend-weighted pattern when there is insufficient data.
    """
    # Weekend-weighted default: Sat/Sun ≈ 1.5× weekday weight
    default_raw = [1.0, 1.0, 1.0, 1.0, 1.0, 1.5, 1.5]
    default_total = sum(default_raw)
    default = [r / default_total for r in default_raw]

    if expenses.empty:
        return default

    df = expenses.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = df["amount"].astype(float).abs()
    cutoff = df["transaction_date"].max() - timedelta(weeks=lookback_weeks)
    df = df[df["transaction_date"] >= cutoff]
    if df.empty:
        return default

    df["dow"] = df["transaction_date"].dt.dayofweek  # 0 = Mon … 6 = Sun
    by_dow = df.groupby("dow")["amount"].sum().reindex(range(7), fill_value=0.0)
    total = float(by_dow.sum())
    if total <= 0:
        return default
    return (by_dow / total).tolist()


# ─────────────────────────────────────────────────────────────
# Monthly-granularity Prophet helpers (primary training path)
# ─────────────────────────────────────────────────────────────

MONTHLY_REGRESSOR_COLUMNS = [
    "lag_1",
    "lag_2",
    "lag_3",
    "rolling_mean_3",
    "rolling_mean_6",
    "rolling_std_3",
    "trend_3",
    "level_ratio",
    "month_sin",
    "month_cos",
]


def expenses_to_monthly(expenses: pd.DataFrame) -> pd.DataFrame:
    """Aggregate expense rows to calendar-month totals ordered by month start."""
    if expenses.empty:
        return pd.DataFrame(columns=["month_start", "monthly_expense"])

    df = expenses.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = df["amount"].astype(float).abs()
    df["month_start"] = df["transaction_date"].dt.to_period("M").dt.to_timestamp()
    monthly = (
        df.groupby("month_start", as_index=False)["amount"]
        .sum()
        .rename(columns={"amount": "monthly_expense"})
        .sort_values("month_start")
        .reset_index(drop=True)
    )
    return monthly


def drop_incomplete_current_month(
    monthly: pd.DataFrame,
    *,
    reference: date | None = None,
) -> pd.DataFrame:
    """
    Remove the in-progress calendar month.

    Month-to-date totals are not comparable to full-month Prophet forecasts and
    inflate hold-out MAPE toward 100%.
    """
    if monthly.empty:
        return monthly
    today = reference or date.today()
    current_month = pd.Timestamp(today.replace(day=1))
    m = monthly.copy().sort_values("month_start").reset_index(drop=True)
    m["month_start"] = pd.to_datetime(m["month_start"])
    if m["month_start"].iloc[-1] >= current_month:
        m = m.iloc[:-1]
    return m.reset_index(drop=True)


def attach_monthly_regressors(monthly: pd.DataFrame) -> pd.DataFrame:
    """
    Monthly autoregressive + calendar features for Prophet regressors.

    Each row uses only expenses from prior months so training does not leak the
    current month's target into its regressors. Short histories back-fill lags
    from the earliest available months (same rule as inference).
    """
    m = monthly.copy().sort_values("month_start").reset_index(drop=True)
    reg_rows: list[dict[str, float]] = []
    for i in range(len(m)):
        if i == 0:
            reg_rows.append({col: np.nan for col in MONTHLY_REGRESSOR_COLUMNS})
            continue
        hist = m.iloc[:i][["month_start", "monthly_expense"]]
        target_ds = pd.Timestamp(m["month_start"].iloc[i])
        reg_rows.append(monthly_regressor_row(hist, target_ds))
    reg_df = pd.DataFrame(reg_rows)
    return pd.concat([m.reset_index(drop=True), reg_df], axis=1)


def build_prophet_monthly_frame(monthly: pd.DataFrame) -> pd.DataFrame:
    """Prophet training frame: ds, y, and monthly regressor columns."""
    m = attach_monthly_regressors(monthly)
    frame = pd.DataFrame(
        {
            "ds": m["month_start"],
            "y": m["monthly_expense"].clip(lower=1.0),
        }
    )
    for col in MONTHLY_REGRESSOR_COLUMNS:
        frame[col] = m[col]
    return frame.dropna(subset=MONTHLY_REGRESSOR_COLUMNS).reset_index(drop=True)


def monthly_regressor_row(history: pd.DataFrame, target_ds: pd.Timestamp) -> dict[str, float]:
    """Regressor values for one future month using observed history only."""
    h = history.sort_values("month_start").reset_index(drop=True)
    e = h["monthly_expense"].astype(float).values
    n = len(e)
    if n < 1:
        raise ValueError("monthly history required for regressor row")

    lag_1 = float(e[-1])
    lag_2 = float(e[-2]) if n >= 2 else lag_1
    lag_3 = float(e[-3]) if n >= 3 else lag_2
    tail3 = e[-min(3, n) :]
    tail6 = e[-min(6, n) :]
    rolling_mean_3 = float(np.mean(tail3))
    rolling_mean_6 = float(np.mean(tail6))
    rolling_std_3 = float(np.std(tail3, ddof=0)) if len(tail3) >= 2 else 0.0
    trend_3 = float((e[-1] - e[-4]) / 3.0) if n >= 4 else 0.0
    level_ratio = float(np.clip(lag_1 / max(rolling_mean_6, 1.0), 0.1, 5.0))
    month_num = int(pd.Timestamp(target_ds).month)
    return {
        "lag_1": lag_1,
        "lag_2": lag_2,
        "lag_3": lag_3,
        "rolling_mean_3": rolling_mean_3,
        "rolling_mean_6": rolling_mean_6,
        "rolling_std_3": rolling_std_3,
        "trend_3": trend_3,
        "level_ratio": level_ratio,
        "month_sin": float(np.sin(2 * np.pi * month_num / 12.0)),
        "month_cos": float(np.cos(2 * np.pi * month_num / 12.0)),
    }


def model_uses_monthly_regressors(model) -> bool:
    return bool(getattr(model, "extra_regressors", None))


def create_prophet_model_monthly(
    month_count: int,
    *,
    use_regressors: bool = True,
    regressor_columns: list[str] | None = None,
):
    """Prophet config tuned for calendar-month expense totals."""
    from prophet import Prophet

    model = Prophet(
        growth="linear" if month_count >= 12 else "flat",
        weekly_seasonality=False,
        yearly_seasonality=month_count >= 12,
        daily_seasonality=False,
        seasonality_mode="multiplicative",
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
    )
    if use_regressors:
        for col in regressor_columns or MONTHLY_REGRESSOR_COLUMNS:
            model.add_regressor(col, standardize=True)
    return model


def prophet_future_frame_monthly(monthly: pd.DataFrame, steps: int) -> pd.DataFrame:
    """Generate `steps` consecutive monthly future dates after the last observed month."""
    m = monthly.sort_values("month_start").reset_index(drop=True)
    last = pd.Timestamp(m["month_start"].iloc[-1])
    dates = [last + pd.DateOffset(months=i + 1) for i in range(steps)]
    return pd.DataFrame({"ds": dates})


def prophet_future_frame_monthly_with_regressors(
    monthly: pd.DataFrame,
    steps: int,
) -> pd.DataFrame:
    """Future Prophet rows with ds + monthly regressors for the next `steps` months."""
    m = monthly.sort_values("month_start").reset_index(drop=True)
    last = pd.Timestamp(m["month_start"].iloc[-1])
    rows: list[dict[str, float | pd.Timestamp]] = []
    for i in range(steps):
        target_ds = last + pd.DateOffset(months=i + 1)
        rows.append({"ds": target_ds, **monthly_regressor_row(m, target_ds)})
    return pd.DataFrame(rows)


def sanitize_monthly_predictions(raw: np.ndarray, monthly: pd.DataFrame) -> list[float]:
    """Floor negative / non-finite monthly predictions to the recent monthly mean."""
    floor = max(float(monthly["monthly_expense"].tail(3).mean()), 0.0)
    preds: list[float] = []
    for v in raw:
        y = float(v)
        if not np.isfinite(y) or y < 0:
            y = floor
        preds.append(max(0.0, y))
    return preds


def prophet_predict_months(
    model,
    monthly: pd.DataFrame,
    steps: int,
    *,
    use_regressors: bool | None = None,
) -> list[float]:
    if use_regressors is None:
        use_regressors = model_uses_monthly_regressors(model)

    history = monthly.sort_values("month_start").reset_index(drop=True)
    preds: list[float] = []
    for _ in range(steps):
        if use_regressors:
            future = prophet_future_frame_monthly_with_regressors(history, 1)
        else:
            future = prophet_future_frame_monthly(history, 1)
        forecast = model.predict(future)
        pred = sanitize_monthly_predictions(forecast["yhat"].values, history)[0]
        preds.append(pred)
        next_month = pd.Timestamp(history["month_start"].iloc[-1]) + pd.DateOffset(months=1)
        history = pd.concat(
            [
                history,
                pd.DataFrame(
                    {
                        "month_start": [next_month],
                        "monthly_expense": [pred],
                    }
                ),
            ],
            ignore_index=True,
        )
    return preds


def filter_users_with_min_month_history(
    transactions: pd.DataFrame,
    *,
    min_months: int = MIN_MONTHS_FOR_PROPHET_USER,
) -> pd.DataFrame:
    """Keep rows only for users with at least `min_months` distinct calendar months."""
    if transactions.empty or "user_id" not in transactions.columns:
        return transactions.copy()

    tx = transactions.copy()
    tx["transaction_date"] = pd.to_datetime(tx["transaction_date"])
    month_counts = (
        tx.groupby("user_id")["transaction_date"]
        .apply(lambda s: s.dt.to_period("M").nunique())
    )
    eligible = month_counts[month_counts >= min_months].index
    return tx[tx["user_id"].isin(eligible)].reset_index(drop=True)


def prepare_global_training_expenses(
    transactions: pd.DataFrame,
    *,
    min_months: int = MIN_MONTHS_FOR_PROPHET_USER,
) -> pd.DataFrame:
    """
    Training pool for global Prophet models:

    1. Keep expense rows only (income/credit rows are excluded — the model forecasts spend).
    2. Keep users with at least `min_months` distinct calendar months of expense activity.
    3. Return every expense row for those qualifying users (no per-user models).
    """
    if transactions.empty:
        return transactions.copy()

    tx = transactions.copy()
    if "transaction_type" in tx.columns:
        tx = tx[tx["transaction_type"] == "expense"].copy()
    if tx.empty or "user_id" not in tx.columns:
        return tx.reset_index(drop=True)

    return filter_users_with_min_month_history(tx, min_months=min_months)


def build_global_prophet_ds_y_frame(transactions: pd.DataFrame) -> pd.DataFrame:
    """Pooled global monthly series as Prophet ds/y (no extra regressors)."""
    monthly = drop_incomplete_current_month(expenses_to_monthly(transactions))
    m = monthly.sort_values("month_start").reset_index(drop=True)
    if m.empty:
        return pd.DataFrame(columns=["ds", "y"])
    return pd.DataFrame(
        {
            "ds": pd.to_datetime(m["month_start"]),
            "y": m["monthly_expense"].astype(float).clip(lower=0.0),
        }
    )


def prophet_default_holdout_mape(
    prophet_df: pd.DataFrame,
    *,
    train_ratio: float = 0.6,
) -> float | None:
    """
    60/40 chronological hold-out MAPE using default Prophet (ds + y only).
    Matches the admin reference: train on first 60%, predict the remaining months.
    """
    if prophet_df.empty or len(prophet_df) < 3:
        return None

    df = prophet_df.sort_values("ds").reset_index(drop=True)
    split = int(len(df) * train_ratio)
    if split < 2 or split >= len(df):
        return None

    train_df = df.iloc[:split][["ds", "y"]].copy()
    test_df = df.iloc[split:][["ds", "y"]].copy()
    if float(test_df["y"].sum()) <= 0:
        return None

    from prophet import Prophet

    model = Prophet()
    model.fit(train_df)
    forecast = model.predict(test_df[["ds"]])
    pred = np.clip(forecast["yhat"].values.astype(float), 0.0, None)
    actual = test_df["y"].astype(float).values
    return min(safe_mape(actual, pred), 1.0)


def prophet_holdout_mape_monthly(
    monthly: pd.DataFrame,
    *,
    reference: date | None = None,
) -> float | None:
    """One-month hold-out MAPE on the last *complete* calendar month."""
    complete = drop_incomplete_current_month(monthly, reference=reference)
    if len(complete) < 2:
        return None
    m = complete.sort_values("month_start").reset_index(drop=True)
    hold_y = float(m["monthly_expense"].iloc[-1])
    if hold_y <= 0:
        return None
    train = m.iloc[:-1]
    if train.empty:
        return None
    try:
        train_df = build_prophet_monthly_frame(train)
        if train_df.empty:
            return None
        model = create_prophet_model_monthly(len(train_df), use_regressors=True)
        model.fit(train_df)
        pred = prophet_predict_months(model, train, 1)[0]
        return min(safe_mape([hold_y], [pred]), 1.0)
    except Exception:
        return None
