"""Shared feature engineering for expense forecasting (training + inference)."""

from __future__ import annotations

from datetime import timedelta
from typing import Iterable

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_4",
    "rolling_mean_4",
    "rolling_mean_8",
    "rolling_std_4",
    "trend_4",
    "level_ratio",
    "week_of_year",
    "month",
    "week_sin",
    "week_cos",
]

MIN_WEEKS_FOR_FORECAST = 8
MIN_WEEKS_FOR_PROPHET_USER = 8
PROPHET_HOLDOUT_MIN_WEEKS = 9


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


def _level_ratio_series(weekly_expense: pd.Series) -> pd.Series:
    baseline = weekly_expense.shift(1).rolling(8, min_periods=3).mean().clip(lower=1.0)
    return (weekly_expense.shift(1) / baseline).clip(0.1, 5.0)


def build_supervised_weekly(weekly: pd.DataFrame) -> pd.DataFrame:
    """One row per week with lags and target = next week's expense."""
    if len(weekly) < MIN_WEEKS_FOR_FORECAST:
        return pd.DataFrame()

    w = weekly.copy().sort_values("week_start").reset_index(drop=True)
    w["lag_1"] = w["weekly_expense"].shift(1)
    w["lag_2"] = w["weekly_expense"].shift(2)
    w["lag_3"] = w["weekly_expense"].shift(3)
    w["lag_4"] = w["weekly_expense"].shift(4)
    w["rolling_mean_4"] = w["weekly_expense"].shift(1).rolling(4, min_periods=2).mean()
    w["rolling_mean_8"] = w["weekly_expense"].shift(1).rolling(8, min_periods=3).mean()
    w["rolling_std_4"] = w["weekly_expense"].shift(1).rolling(4, min_periods=2).std()
    w["trend_4"] = w["weekly_expense"].shift(1).diff(3) / 3.0
    w["level_ratio"] = _level_ratio_series(w["weekly_expense"])
    w["week_of_year"] = w["week_start"].dt.isocalendar().week.astype(int)
    w["month"] = w["week_start"].dt.month
    w["week_sin"] = np.sin(2 * np.pi * w["week_of_year"] / 52.0)
    w["week_cos"] = np.cos(2 * np.pi * w["week_of_year"] / 52.0)
    w["target"] = w["weekly_expense"].shift(-1)
    w = w.dropna(subset=FEATURE_COLUMNS + ["target"]).reset_index(drop=True)
    return w


def latest_feature_row(weekly: pd.DataFrame) -> pd.DataFrame | None:
    """Feature vector for the week after the last observed week."""
    if len(weekly) < 5:
        return None

    w = weekly.copy().sort_values("week_start").reset_index(drop=True)
    expenses = w["weekly_expense"].values
    next_start = w["week_start"].iloc[-1] + timedelta(days=7)
    week_of_year = int(next_start.isocalendar().week)
    month = int(next_start.month)

    rolling_mean_8 = float(np.mean(expenses[-min(8, len(expenses)) :]))
    rolling_mean_4 = float(np.mean(expenses[-4:]))
    row = {
        "lag_1": expenses[-1],
        "lag_2": expenses[-2],
        "lag_3": expenses[-3],
        "lag_4": expenses[-4],
        "rolling_mean_4": rolling_mean_4,
        "rolling_mean_8": rolling_mean_8,
        "rolling_std_4": float(np.std(expenses[-4:], ddof=0)),
        "trend_4": float((expenses[-1] - expenses[-4]) / 3.0) if len(expenses) >= 4 else 0.0,
        "level_ratio": float(np.clip(expenses[-1] / max(rolling_mean_8, 1.0), 0.1, 5.0)),
        "week_of_year": week_of_year,
        "month": month,
        "week_sin": float(np.sin(2 * np.pi * week_of_year / 52.0)),
        "week_cos": float(np.cos(2 * np.pi * week_of_year / 52.0)),
    }
    return pd.DataFrame([row])


def feature_matrix(rows: pd.DataFrame) -> np.ndarray:
    return rows[FEATURE_COLUMNS].astype(float).values


def build_training_frame(
    transactions: pd.DataFrame,
    categories: pd.DataFrame,
) -> pd.DataFrame:
    """Global training set: all users' weekly expense → next-week target."""
    if transactions.empty:
        return pd.DataFrame()

    tx = transactions.merge(categories, on="category_id", how="left")
    tx = tx[tx["transaction_type"] == "expense"].copy()
    if tx.empty:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for user_id, group in tx.groupby("user_id"):
        weekly = expenses_to_weekly(group)
        supervised = build_supervised_weekly(weekly)
        if supervised.empty:
            continue
        supervised["user_id"] = user_id
        frames.append(supervised)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


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


def create_prophet_model(week_count: int):
    """Prophet config tuned for short weekly expense series."""
    from prophet import Prophet

    return Prophet(
        growth="flat" if week_count < 26 else "linear",
        weekly_seasonality=True,
        yearly_seasonality=week_count >= 52,
        daily_seasonality=False,
        seasonality_mode="multiplicative",
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
    )


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


def prophet_holdout_mape(weekly: pd.DataFrame) -> float | None:
    """One-step hold-out MAPE using the same date alignment as inference."""
    if len(weekly) < PROPHET_HOLDOUT_MIN_WEEKS:
        return None
    w = weekly.sort_values("week_start").reset_index(drop=True)
    hold_y = float(w["weekly_expense"].iloc[-1])
    if hold_y <= 0:
        return None
    train = w.iloc[:-1]
    train_df = pd.DataFrame(
        {"ds": train["week_start"], "y": train["weekly_expense"].clip(lower=1.0)},
    )
    model = create_prophet_model(len(train_df))
    model.fit(train_df)
    pred = prophet_predict_weeks(model, train, 1)[0]
    return min(safe_mape([hold_y], [pred]), 1.0)


# ─────────────────────────────────────────────────────────────
# Daily-granularity Prophet helpers
# These are used when models are trained on daily data (the
# recommended approach — see prophet_training_service.py).
# ─────────────────────────────────────────────────────────────

MIN_DAYS_FOR_PROPHET_USER = 56  # 8 weeks of daily expense data


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


def create_prophet_model_daily(day_count: int):
    """
    Prophet config tuned for *daily* expense data.
    weekly_seasonality=True lets Prophet learn Mon–Sun spending rhythms,
    which is what makes weekend predictions higher than weekday ones.
    """
    from prophet import Prophet

    return Prophet(
        growth="linear" if day_count >= 90 else "flat",
        weekly_seasonality=True,        # Captures Mon–Sun day-of-week effects
        yearly_seasonality=day_count >= 365,
        daily_seasonality=False,
        seasonality_mode="additive",
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
    )


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


def prophet_holdout_mape_daily(daily: pd.DataFrame) -> float | None:
    """7-day hold-out MAPE for a daily-trained Prophet model."""
    if len(daily) < MIN_DAYS_FOR_PROPHET_USER + 7:
        return None
    d = daily.sort_values("date").reset_index(drop=True)
    hold_total = float(d["daily_expense"].iloc[-7:].sum())
    if hold_total <= 0:
        return None
    train = d.iloc[:-7]
    train_df = pd.DataFrame({
        "ds": train["date"],
        "y": train["daily_expense"].clip(lower=0.0),
    })
    model = create_prophet_model_daily(len(train_df))
    model.fit(train_df)
    future = prophet_future_frame_daily(pd.Timestamp(train["date"].iloc[-1]), 7)
    forecast = model.predict(future)
    pred_preds = sanitize_daily_predictions(forecast["yhat"].values, train)
    pred_total = sum(pred_preds)
    return min(safe_mape([hold_total], [pred_total]), 1.0)
