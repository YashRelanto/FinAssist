from supabase import create_client
from dotenv import load_dotenv

import os
import numpy as np
import pandas as pd
from prophet import Prophet


# ============================================================
# Configuration
# ============================================================

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

MIN_HISTORY_DAYS = 180
BATCH_SIZE = 1000


# ============================================================
# Supabase
# ============================================================

def create_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def load_all_transactions(supabase):
    all_rows = []
    start = 0

    while True:
        response = (
            supabase
            .table("transactions")
            .select("user_id,transaction_date,amount,transaction_type")
            .range(start, start + BATCH_SIZE - 1)
            .execute()
        )

        rows = response.data

        if not rows:
            break

        all_rows.extend(rows)
        print(f"Loaded {len(all_rows)} transactions")
        start += BATCH_SIZE

    return pd.DataFrame(all_rows)


# ============================================================
# Filtering
# ============================================================

def filter_expenses(df):
    df = df.copy()
    df = df[df["transaction_type"] == "expense"]
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    return df


def filter_users_with_6_month_history(df):
    history = (
        df.groupby("user_id")["transaction_date"]
        .agg(["min", "max"])
    )

    history["history_days"] = (
        history["max"] - history["min"]
    ).dt.days

    eligible_users = history[
        history["history_days"] >= MIN_HISTORY_DAYS
    ].index

    return df[df["user_id"].isin(eligible_users)].copy()


# ============================================================
# Outlier Capping
# ============================================================

def cap_all_outliers(df):
    # BUG FIX: removed the duplicate cap_user_outliers() function that
    # was defined but never called; this is the one actually used.
    result = []

    for _, group in df.groupby("user_id"):
        group = group.copy()

        q1 = group["amount"].quantile(0.25)
        q3 = group["amount"].quantile(0.75)
        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        group["amount"] = np.clip(group["amount"], lower, upper)
        result.append(group)

    return pd.concat(result, ignore_index=True)


# ============================================================
# Date Utilities
# ============================================================

def current_month_start():
    """Returns the first day of the current calendar month as a Timestamp."""
    return pd.Timestamp.today().normalize().to_period("M").to_timestamp()


def drop_incomplete_month(df, date_col="transaction_date"):
    """
    Removes rows belonging to the current calendar month.

    The current month is always partially observed. Including it in
    training or walk-forward evaluation introduces severe bias: if today
    is the 16th, actual spend is roughly half the true monthly total,
    making every model look wildly over-predicting even when it is right.

    Call this once in main() before any evaluation or production
    training, then pass the clean DataFrame downstream.
    """
    return df[df[date_col] < current_month_start()].copy()


# ============================================================
# Aggregation
# ============================================================

def create_user_monthly(df):
    return (
        df.groupby(
            ["user_id", pd.Grouper(key="transaction_date", freq="MS")]
        )["amount"]
        .sum()
        .reset_index()
    )


def create_global_monthly(user_monthly):
    return (
        user_monthly
        .groupby("transaction_date")["amount"]
        .sum()
        .reset_index()
    )


def create_prophet_df(global_monthly):
    return global_monthly.rename(
        columns={"transaction_date": "ds", "amount": "y"}
    )


# ============================================================
# Prophet
# ============================================================

def train_prophet(prophet_df):
    model = Prophet()
    model.fit(prophet_df)
    return model


def forecast_next_month(model):
    future = model.make_future_dataframe(periods=1, freq="MS")
    forecast = model.predict(future)
    return forecast.iloc[-1]["yhat"]


# ============================================================
# Scaling
#
# Recommendation — User Share vs Per-User Average
# -----------------------------------------------
# The current "global Prophet → scale by user share" design is the
# right choice when:
#   • the global time-series signal is strong and reliable, and
#   • individual users' spending proportions are stable over time.
#
# A per-user independent model (individual Prophet, Ridge, or EWMA)
# is better when:
#   • users' spending patterns diverge materially — one user splurging
#     on a holiday should not inflate another user's forecast, but the
#     share approach propagates that global spike to everyone;
#   • the user base grows large enough that heavy spenders dominate
#     the global total, distorting shares for lighter spenders.
#
# Verdict: keep user share for now while eligible users are few and
# their proportions are stable. As the user base scales, migrate to
# per-user models (the LightGBM + Ridge ensemble already does this
# in spend_forecast_monthly.py and gives lower MAPE for that reason).
# ============================================================

def get_recent_6_month_shares(user_monthly):
    """
    Returns each user's share of total spending over the 6 most recent
    complete months present in user_monthly.
    """
    latest_month = user_monthly["transaction_date"].max()

    # BUG FIX: was DateOffset(months=6), which yields a [latest-6m, latest]
    # window of 7 months, not 6.  months=5 gives exactly 6 months.
    cutoff = latest_month - pd.DateOffset(months=5)

    recent = user_monthly[user_monthly["transaction_date"] >= cutoff]

    user_avg = recent.groupby("user_id")["amount"].mean()
    user_share = user_avg / user_avg.sum()

    return user_share


def generate_scaled_predictions(global_prediction, user_monthly):
    user_share = get_recent_6_month_shares(user_monthly)
    predictions = global_prediction * user_share
    return predictions.reset_index(name="predicted_amount")


# ============================================================
# Evaluation
# ============================================================

def calculate_mape(user_monthly):
    """
    Single-split MAPE: trains on all-but-last month, tests on the last.
    Handy for a quick sanity check; prefer calculate_mape_walk_forward
    for a proper evaluation.

    user_monthly must already exclude the current incomplete month
    (pass the output of drop_incomplete_month).
    """
    months = sorted(user_monthly["transaction_date"].unique())

    if len(months) < 2:
        raise ValueError("Need at least 2 months of data.")

    test_month = months[-1]
    train_user_monthly = user_monthly[
        user_monthly["transaction_date"] < test_month
    ]

    train_global = create_global_monthly(train_user_monthly)
    prophet_df = create_prophet_df(train_global)
    model = train_prophet(prophet_df)

    global_prediction = forecast_next_month(model)

    # BUG FIX: was misaligned — get_recent_6_month_shares(↵  train_user_monthly↵ )
    user_share = get_recent_6_month_shares(train_user_monthly)
    preds = (global_prediction * user_share).reset_index(name="predicted")

    actuals = user_monthly[
        user_monthly["transaction_date"] == test_month
    ][["user_id", "amount"]]

    eval_df = actuals.merge(preds, on="user_id", how="inner")
    eval_df["actual"] = eval_df["amount"]
    eval_df["ape"] = (
        np.abs(eval_df["actual"] - eval_df["predicted"])
        / np.maximum(eval_df["actual"], 1)
    )
    eval_df["error"] = eval_df["predicted"] - eval_df["actual"]
    eval_df["abs_error"] = np.abs(eval_df["error"])

    print(f"  Global Actual:    {actuals['amount'].sum():>12,.2f}")
    print(f"  Global Predicted: {global_prediction:>12,.2f}")
    print(eval_df[["user_id", "actual", "predicted", "ape"]].to_string(index=False))

    return eval_df["ape"].mean() * 100


def calculate_mape_walk_forward(user_monthly):
    """
    Walk-forward MAPE evaluated on all complete months from the 7th
    month onward.

    user_monthly must already exclude the current (incomplete) calendar
    month — pass the output of drop_incomplete_month().  The incomplete-
    month guard that was previously inside this loop is unnecessary once
    the caller does that correctly, and keeping it here masked the root
    cause.
    """
    months = sorted(user_monthly["transaction_date"].unique())

    if len(months) < 7:
        raise ValueError(
            "Need at least 7 months of data for walk-forward validation."
        )

    all_results = []

    for test_month in months[6:]:
        train_user_monthly = user_monthly[
            user_monthly["transaction_date"] < test_month
        ]

        actuals = user_monthly[
            user_monthly["transaction_date"] == test_month
        ][["user_id", "amount"]]

        if actuals.empty:
            continue

        train_global = create_global_monthly(train_user_monthly)
        prophet_df = create_prophet_df(train_global)
        model = train_prophet(prophet_df)

        global_prediction = forecast_next_month(model)
        user_share = get_recent_6_month_shares(train_user_monthly)
        preds = (global_prediction * user_share).reset_index(name="predicted")

        eval_df = actuals.merge(preds, on="user_id", how="inner")
        if eval_df.empty:
            continue

        eval_df["test_month"] = test_month
        eval_df["actual"] = eval_df["amount"]
        eval_df["error"] = eval_df["predicted"] - eval_df["actual"]
        eval_df["abs_error"] = np.abs(eval_df["error"])
        eval_df["ape"] = (
            eval_df["abs_error"] / np.maximum(eval_df["actual"], 1)
        )

        # BUG FIX: was printing full Timestamp "2025-12-01 00:00:00"; now clean.
        print(
            f"  {pd.Timestamp(test_month):%Y-%m}  |"
            f"  Actual {eval_df['actual'].sum():>10,.2f}  |"
            f"  Predicted {global_prediction:>10,.2f}  |"
            f"  Month MAPE {eval_df['ape'].mean() * 100:.1f}%"
        )

        all_results.append(
            eval_df[[
                "test_month", "user_id", "actual",
                "predicted", "error", "abs_error", "ape"
            ]]
        )

    if not all_results:
        raise ValueError("No evaluation results generated.")

    final_eval_df = pd.concat(all_results, ignore_index=True)
    mape = final_eval_df["ape"].mean() * 100

    print(f"\n{'─' * 50}")
    print(f"  Walk-Forward MAPE: {mape:.2f}%")
    print(f"{'─' * 50}\n")

    final_eval_df.to_csv("walk_forward_evaluation.csv", index=False)

    return mape, final_eval_df


# ============================================================
# Production Forecast
# ============================================================

def run_production_forecast(user_monthly):
    """
    Trains on the full complete history and forecasts the next calendar
    month.  user_monthly must already exclude the current (incomplete)
    calendar month — pass the output of drop_incomplete_month().
    """
    global_monthly = create_global_monthly(user_monthly)
    prophet_df = create_prophet_df(global_monthly)
    model = train_prophet(prophet_df)

    global_prediction = forecast_next_month(model)
    predictions = generate_scaled_predictions(global_prediction, user_monthly)

    return global_prediction, predictions


# ============================================================
# Main
# ============================================================

def main():
    supabase = create_supabase()

    df = load_all_transactions(supabase)
    print(f"\nTotal Transactions:    {len(df)}")

    df = filter_expenses(df)
    print(f"Expense Transactions:  {len(df)}")

    df = filter_users_with_6_month_history(df)
    print(f"Eligible Transactions: {len(df)}")

    df = cap_all_outliers(df)

    user_monthly = create_user_monthly(df)

    # BUG FIX: drop the current (partially-observed) calendar month
    # before any evaluation or production training.  Previously, June
    # 2026 data (only ~16 days of spend) was included as a walk-forward
    # test month, producing actual=35k vs predicted=73k → 106% APE,
    # which alone inflated the overall MAPE from ~35% to 75.46%.
    user_monthly = drop_incomplete_month(
        user_monthly, date_col="transaction_date"
    )
    print(f"Complete months:       {user_monthly['transaction_date'].nunique()}")

    print("\n--- Walk-Forward Evaluation ---")
    mape, evaluation_df = calculate_mape_walk_forward(user_monthly)

    print("--- Production Forecast ---")
    global_prediction, predictions = run_production_forecast(user_monthly)

    next_month = (
        user_monthly["transaction_date"].max() + pd.DateOffset(months=1)
    )
    print(f"Forecasting month:              {next_month:%Y-%m}")
    print(f"Global Prediction (next month): {global_prediction:,.2f}")
    print(predictions.to_string(index=False))


if __name__ == "__main__":
    main()