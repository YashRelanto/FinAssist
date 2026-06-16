"""Prophet feature engineering, evaluation, and chart helpers."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

MIN_HISTORY_DAYS = 180
MIN_MONTHS_FOR_FORECAST = 6
MIN_MONTHS_FOR_PROPHET_USER = 6


def expenses_to_weekly(expenses: pd.DataFrame) -> pd.DataFrame:
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
    return (
        df.groupby("week_start", as_index=False)["amount"]
        .sum()
        .rename(columns={"amount": "weekly_expense"})
        .sort_values("week_start")
        .reset_index(drop=True)
    )


def expenses_to_monthly(expenses: pd.DataFrame) -> pd.DataFrame:
    if expenses.empty:
        return pd.DataFrame(columns=["month_start", "monthly_expense"])

    df = expenses.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = df["amount"].astype(float).abs()
    df["month_start"] = df["transaction_date"].dt.to_period("M").dt.to_timestamp()
    return (
        df.groupby("month_start", as_index=False)["amount"]
        .sum()
        .rename(columns={"amount": "monthly_expense"})
        .sort_values("month_start")
        .reset_index(drop=True)
    )


def daily_expense_series(expenses: pd.DataFrame, days: int = 35) -> list[dict]:
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
    return [
        {
            "date": dt.strftime("%Y-%m-%d"),
            "amount": round(float(amt), 2),
            "intensity": int(min(5, round((amt / max_amt) * 5))) if amt > 0 else 0,
        }
        for dt, amt in zip(daily.index, amounts)
    ]


def top_merchants(expenses: pd.DataFrame, limit: int = 3) -> list[dict]:
    if expenses.empty:
        return []

    df = expenses.copy()
    df["amount"] = df["amount"].astype(float).abs()
    df["merchant_name"] = df["merchant_name"].fillna(df.get("description", "")).replace("", "Unknown")
    grouped = df.groupby("merchant_name")["amount"].sum().sort_values(ascending=False).head(limit)
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
    if expenses.empty:
        return []

    df = expenses.copy()
    if "main_category" not in df.columns and not categories.empty and "category_id" in df.columns:
        df = df.merge(categories[["category_id", "main_category"]], on="category_id", how="left")
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["amount"] = df["amount"].astype(float).abs()
    df["main_category"] = df.get("main_category", pd.Series(dtype=object)).fillna("Other")

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


def filter_expenses(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "transaction_type" in out.columns:
        out = out[out["transaction_type"] == "expense"]
    out["transaction_date"] = pd.to_datetime(out["transaction_date"])
    out["amount"] = out["amount"].astype(float).abs()
    return out


def filter_users_with_min_history(
    df: pd.DataFrame,
    *,
    min_days: int = MIN_HISTORY_DAYS,
    min_months: int = MIN_MONTHS_FOR_PROPHET_USER,
) -> pd.DataFrame:
    if df.empty or "user_id" not in df.columns:
        return df.copy()

    grouped = df.groupby("user_id")["transaction_date"]
    history = grouped.agg(["min", "max"])
    history["history_days"] = (history["max"] - history["min"]).dt.days
    history["month_count"] = grouped.apply(lambda s: s.dt.to_period("M").nunique())
    eligible = history[
        (history["history_days"] >= min_days) | (history["month_count"] >= min_months)
    ].index
    return df[df["user_id"].isin(eligible)].copy()


def prepare_global_training_expenses(transactions: pd.DataFrame) -> pd.DataFrame:
    return filter_users_with_min_history(filter_expenses(transactions))


def cap_all_outliers(df: pd.DataFrame) -> pd.DataFrame:
    result = []
    for _, group in df.groupby("user_id"):
        group = group.copy()
        q1 = group["amount"].quantile(0.25)
        q3 = group["amount"].quantile(0.75)
        iqr = q3 - q1
        group["amount"] = np.clip(group["amount"], q1 - 1.5 * iqr, q3 + 1.5 * iqr)
        result.append(group)
    if not result:
        return df.copy()
    return pd.concat(result, ignore_index=True)


def current_month_start(reference: date | None = None) -> pd.Timestamp:
    ref = reference or date.today()
    return pd.Timestamp(ref.replace(day=1))


def drop_incomplete_current_month(
    monthly: pd.DataFrame,
    *,
    reference: date | None = None,
    date_col: str = "month_start",
) -> pd.DataFrame:
    if monthly.empty:
        return monthly
    cutoff = current_month_start(reference)
    m = monthly.copy()
    m[date_col] = pd.to_datetime(m[date_col])
    return m[m[date_col] < cutoff].copy().reset_index(drop=True)


def create_user_monthly(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["user_id", pd.Grouper(key="transaction_date", freq="MS")])["amount"]
        .sum()
        .reset_index()
        .rename(columns={"transaction_date": "month_start", "amount": "monthly_expense"})
    )


def create_global_monthly(user_monthly: pd.DataFrame) -> pd.DataFrame:
    return (
        user_monthly.groupby("month_start")["monthly_expense"]
        .sum()
        .reset_index()
        .sort_values("month_start")
        .reset_index(drop=True)
    )


def create_prophet_df(global_monthly: pd.DataFrame) -> pd.DataFrame:
    return global_monthly.rename(columns={"month_start": "ds", "monthly_expense": "y"})


def train_prophet(prophet_df: pd.DataFrame):
    from prophet import Prophet

    model = Prophet()
    model.fit(prophet_df)
    return model


def forecast_next_month(model) -> float:
    future = model.make_future_dataframe(periods=1, freq="MS")
    forecast = model.predict(future)
    return float(forecast.iloc[-1]["yhat"])


def get_recent_6_month_shares(user_monthly: pd.DataFrame) -> pd.Series:
    if user_monthly.empty:
        return pd.Series(dtype=float)

    latest_month = user_monthly["month_start"].max()
    cutoff = latest_month - pd.DateOffset(months=5)
    recent = user_monthly[user_monthly["month_start"] >= cutoff]
    user_avg = recent.groupby("user_id")["monthly_expense"].mean()
    total = float(user_avg.sum())
    if total <= 0:
        n = len(user_avg)
        return pd.Series(1.0 / n if n else 0.0, index=user_avg.index)
    return user_avg / total


def predict_user_amount(
    global_prediction: float,
    user_id: str,
    user_monthly: pd.DataFrame,
    *,
    user_shares: dict[str, float] | None = None,
) -> float:
    uid = str(user_id)
    if user_shares and uid in user_shares:
        return max(0.0, global_prediction * user_shares[uid])

    shares = get_recent_6_month_shares(user_monthly)
    if uid in shares.index:
        return max(0.0, global_prediction * float(shares[uid]))

    user_rows = user_monthly[user_monthly["user_id"].astype(str) == uid]
    if user_rows.empty:
        return max(0.0, global_prediction)
    latest_month = user_monthly["month_start"].max()
    cutoff = latest_month - pd.DateOffset(months=5)
    recent = user_rows[user_rows["month_start"] >= cutoff]
    user_avg = float(recent["monthly_expense"].mean()) if not recent.empty else 0.0
    pool_avg = float(
        user_monthly[user_monthly["month_start"] >= cutoff]["monthly_expense"].sum()
        / max(user_monthly["user_id"].nunique(), 1)
    )
    if pool_avg <= 0:
        return max(0.0, global_prediction)
    return max(0.0, global_prediction * (user_avg / pool_avg))


def user_has_enough_history(expenses: pd.DataFrame, *, min_days: int = MIN_HISTORY_DAYS) -> bool:
    if expenses.empty:
        return False
    df = expenses.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    span = (df["transaction_date"].max() - df["transaction_date"].min()).days
    month_count = len(expenses_to_monthly(expenses))
    return month_count >= MIN_MONTHS_FOR_FORECAST or span >= min_days


def calculate_mape_walk_forward(user_monthly: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    months = sorted(user_monthly["month_start"].unique())
    if len(months) < 7:
        raise ValueError("Need at least 7 months of data for walk-forward validation.")

    all_results = []
    for test_month in months[6:]:
        train_user_monthly = user_monthly[user_monthly["month_start"] < test_month]
        actuals = user_monthly[user_monthly["month_start"] == test_month][["user_id", "monthly_expense"]]
        if actuals.empty:
            continue

        train_global = create_global_monthly(train_user_monthly)
        model = train_prophet(create_prophet_df(train_global))
        global_prediction = forecast_next_month(model)
        user_share = get_recent_6_month_shares(train_user_monthly)
        preds = (global_prediction * user_share).reset_index(name="predicted")
        preds.columns = ["user_id", "predicted"]

        eval_df = actuals.merge(preds, on="user_id", how="inner")
        if eval_df.empty:
            continue

        eval_df["test_month"] = test_month
        eval_df["actual"] = eval_df["monthly_expense"]
        eval_df["abs_error"] = (eval_df["predicted"] - eval_df["actual"]).abs()
        eval_df["ape"] = eval_df["abs_error"] / np.maximum(eval_df["actual"], 1)
        all_results.append(eval_df)

    if not all_results:
        raise ValueError("No evaluation results generated.")

    final_eval_df = pd.concat(all_results, ignore_index=True)
    return float(final_eval_df["ape"].mean()), final_eval_df


def calculate_holdout_mape(user_monthly: pd.DataFrame) -> float | None:
    months = sorted(user_monthly["month_start"].unique())
    if len(months) < 2:
        return None

    test_month = months[-1]
    train_user_monthly = user_monthly[user_monthly["month_start"] < test_month]
    train_global = create_global_monthly(train_user_monthly)
    model = train_prophet(create_prophet_df(train_global))
    global_prediction = forecast_next_month(model)
    user_share = get_recent_6_month_shares(train_user_monthly)
    preds = (global_prediction * user_share).reset_index(name="predicted")
    preds.columns = ["user_id", "predicted"]

    actuals = user_monthly[user_monthly["month_start"] == test_month][["user_id", "monthly_expense"]]
    eval_df = actuals.merge(preds, on="user_id", how="inner")
    if eval_df.empty:
        return None

    eval_df["ape"] = (eval_df["predicted"] - eval_df["monthly_expense"]).abs() / np.maximum(
        eval_df["monthly_expense"], 1
    )
    return float(eval_df["ape"].mean())
