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
    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY
    )


def load_all_transactions(supabase):
    all_rows = []
    start = 0

    while True:
        response = (
            supabase
            .table("transactions")
            .select(
                "user_id,transaction_date,amount,transaction_type"
            )
            .range(start, start + BATCH_SIZE - 1)
            .execute()
        )

        rows = response.data

        if not rows:
            break

        all_rows.extend(rows)

        print(
            f"Loaded {len(all_rows)} transactions"
        )

        start += BATCH_SIZE

    return pd.DataFrame(all_rows)


# ============================================================
# Filtering
# ============================================================

def filter_expenses(df):
    df = df.copy()

    df = df[
        df["transaction_type"] == "expense"
    ]

    df["transaction_date"] = pd.to_datetime(
        df["transaction_date"]
    )

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

    return df[
        df["user_id"].isin(eligible_users)
    ].copy()


# ============================================================
# Outlier Capping
# ============================================================

def cap_user_outliers(group):
    q1 = group["amount"].quantile(0.25)
    q3 = group["amount"].quantile(0.75)

    iqr = q3 - q1

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    group["amount"] = np.clip(
        group["amount"],
        lower,
        upper
    )

    return group


def cap_all_outliers(df):
    result = []

    for user_id, group in df.groupby("user_id"):
        group = group.copy()

        q1 = group["amount"].quantile(0.25)
        q3 = group["amount"].quantile(0.75)

        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        group["amount"] = np.clip(
            group["amount"],
            lower,
            upper
        )

        result.append(group)

    return pd.concat(result, ignore_index=True)


# ============================================================
# Aggregation
# ============================================================

def create_user_monthly(df):
    return (
        df.groupby(
            [
                "user_id",
                pd.Grouper(
                    key="transaction_date",
                    freq="MS"
                )
            ]
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
        columns={
            "transaction_date": "ds",
            "amount": "y"
        }
    )


# ============================================================
# Prophet
# ============================================================

def train_prophet(prophet_df):
    model = Prophet()

    model.fit(prophet_df)

    return model


def forecast_next_month(model):
    future = model.make_future_dataframe(
        periods=1,
        freq="MS"
    )

    forecast = model.predict(future)

    return forecast.iloc[-1]["yhat"]


# ============================================================
# Scaling
# ============================================================

def get_recent_6_month_shares(user_monthly):

    latest_month = (
        user_monthly["transaction_date"]
        .max()
    )

    cutoff = latest_month - pd.DateOffset(months=6)

    recent = user_monthly[
        user_monthly["transaction_date"] >= cutoff
    ]

    user_avg = (
        recent
        .groupby("user_id")["amount"]
        .mean()
    )

    user_share = (
        user_avg /
        user_avg.sum()
    )

    return user_share

def generate_scaled_predictions(
    global_prediction,
    user_monthly
):

    user_share = (
        get_recent_6_month_shares(
            user_monthly
        )
    )

    predictions = (
        global_prediction *
        user_share
    )

    return predictions.reset_index(
        name="predicted_amount"
    )

# ============================================================
# Evaluation
# ============================================================

def calculate_mape(user_monthly):
    months = sorted(
        user_monthly["transaction_date"].unique()
    )

    if len(months) < 2:
        raise ValueError(
            "Need at least 2 months of data."
        )

    test_month = months[-1]

    train_user_monthly = user_monthly[
        user_monthly["transaction_date"]
        < test_month
    ]

    train_global = create_global_monthly(
        train_user_monthly
    )

    prophet_df = create_prophet_df(
        train_global
    )

    model = train_prophet(
        prophet_df
    )

    global_prediction = (
        forecast_next_month(model)
    )

    user_share = (
        get_recent_6_month_shares(
        train_user_monthly
    )
)

    preds = (
        global_prediction
        * user_share
    )

    preds = preds.reset_index(
        name="predicted"
    )

    actuals = user_monthly[
        user_monthly["transaction_date"]
        == test_month
    ][
        ["user_id", "amount"]
    ]

    eval_df = actuals.merge(
        preds,
        on="user_id",
        how="inner"
    )

    
    eval_df["actual"] = eval_df["amount"]

    eval_df["ape"] = (
        np.abs(
            eval_df["amount"]
            - eval_df["predicted"]
        )
        /
        np.maximum(
            eval_df["amount"],
            1
        )
    )

    eval_df["error"] = (
        eval_df["predicted"]
        - eval_df["actual"]
    )

    eval_df["abs_error"] = (
        np.abs(eval_df["error"])
    )

    actual_global = actuals["amount"].sum()

    print(
        f"Global Actual: {actual_global:.2f}"
    )

    print(
        f"Global Predicted: {global_prediction:.2f}"
    )

    mape = (
        eval_df["ape"].mean()
        * 100
    )

    print(
        eval_df[["user_id", "actual", "predicted", "ape"]]
    )

    return mape

def calculate_mape_walk_forward(user_monthly):

    months = sorted(
        user_monthly["transaction_date"].unique()
    )

    if len(months) < 7:
        raise ValueError(
            "Need at least 7 months of data "
            "for walk-forward validation."
        )

    all_results = []

    for test_month in months[6:]:

        train_user_monthly = user_monthly[
            user_monthly["transaction_date"]
            < test_month
        ]

        actuals = user_monthly[
            user_monthly["transaction_date"]
            == test_month
        ][
            ["user_id", "amount"]
        ]

        if actuals.empty:
            continue

        train_global = create_global_monthly(
            train_user_monthly
        )

        prophet_df = create_prophet_df(
            train_global
        )

        model = train_prophet(
            prophet_df
        )

        global_prediction = (
            forecast_next_month(model)
        )

        user_share = (
            get_recent_6_month_shares(
                train_user_monthly
            )
        )

        preds = (
            global_prediction
            * user_share
        )

        preds = preds.reset_index(
            name="predicted"
        )

        eval_df = actuals.merge(
            preds,
            on="user_id",
            how="inner"
        )

        if len(eval_df) == 0:
            continue

        eval_df["test_month"] = test_month

        eval_df["actual"] = (
            eval_df["amount"]
        )

        eval_df["error"] = (
            eval_df["predicted"]
            - eval_df["actual"]
        )

        eval_df["abs_error"] = (
            np.abs(eval_df["error"])
        )

        eval_df["ape"] = (
            eval_df["abs_error"]
            /
            np.maximum(
                eval_df["actual"],
                1
            )
        )

        actual_global = (
            eval_df["actual"]
            .sum()
        )

        print(
            f"\nMonth: {test_month}"
        )

        print(
            f"Global Actual: "
            f"{actual_global:.2f}"
        )

        print(
            f"Global Predicted: "
            f"{global_prediction:.2f}"
        )

        all_results.append(
            eval_df[
                [
                    "test_month",
                    "user_id",
                    "actual",
                    "predicted",
                    "error",
                    "abs_error",
                    "ape"
                ]
            ]
        )

    if not all_results:
        raise ValueError(
            "No evaluation results generated."
        )

    final_eval_df = pd.concat(
        all_results,
        ignore_index=True
    )

    mape = (
        final_eval_df["ape"]
        .mean()
        * 100
    )

    print("\n==========")
    print(f"Walk-Forward MAPE: {mape:.2f}%")
    print("==========\n")

    final_eval_df.to_csv(
        "walk_forward_evaluation.csv",
        index=False
    )

    return mape, final_eval_df


# ============================================================
# Production Forecast
# ============================================================

def run_production_forecast(user_monthly):
    global_monthly = (
        create_global_monthly(
            user_monthly
        )
    )

    prophet_df = create_prophet_df(
        global_monthly
    )

    model = train_prophet(
        prophet_df
    )

    global_prediction = (
        forecast_next_month(model)
    )

    predictions = (
        generate_scaled_predictions(
            global_prediction,
            user_monthly
        )
    )

    return global_prediction, predictions


# ============================================================
# Main
# ============================================================

def main():
    supabase = create_supabase()

    df = load_all_transactions(
        supabase
    )

    print(
        "Total Transactions:",
        len(df)
    )

    df = filter_expenses(df)

    print(
        "Expense Transactions:",
        len(df)
    )

    df = filter_users_with_6_month_history(
        df
    )

    print(
        "Eligible Transactions:",
        len(df)
    )
    print("Before capping:", df.columns)


    df = cap_all_outliers(df)

    print("After capping:", df.columns)
    print(df.index.names)

    user_monthly = (
        create_user_monthly(df)
    )

    mape, evaluation_df = calculate_mape_walk_forward(
        user_monthly
    )

    print(
        f"Walk-Forward MAPE: "
        f"{mape:.2f}%"
    )

    print(
        evaluation_df.head()
    )

    global_prediction, predictions = (
        run_production_forecast(
            user_monthly
        )
    )

    print(
        f"Global Next Month Prediction: "
        f"{global_prediction:.2f}"
    )

    print(
        predictions.head()
    )


if __name__ == "__main__":
    main()