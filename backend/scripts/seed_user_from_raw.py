#!/usr/bin/env python3
"""
Seed a Supabase user with daily expense history tuned for the daily Prophet model.

Each calendar day gets expense rows whose daily total follows real behaviour:
weekdays ~100–250 INR, weekends ~2,000–5,000 INR. History spans 90 consecutive days
(>= MIN_DAYS_FOR_PROPHET_USER) ending near today so nightly training can fit
weekly_seasonality.

Usage:
  PYTHONPATH=backend python backend/scripts/seed_user_from_raw.py
  PYTHONPATH=backend python backend/scripts/seed_user_from_raw.py --email suyash.bhadouria@relanto.ai --retrain
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.forecast_features import MIN_DAYS_FOR_PROPHET_USER  # noqa: E402
from app.utils.supabase_client import supabase  # noqa: E402

DEFAULT_EMAIL = "suyash.bhadouria@relanto.ai"
MIN_SAVINGS_RATIO = 0.18  # income should exceed expenses by at least ~18%

# Daily Prophet training needs a continuous daily expense series (see expenses_to_daily).
PROPHET_HISTORY_DAYS = max(90, MIN_DAYS_FOR_PROPHET_USER)
WEEKDAY_DAILY_RANGE = (100, 250)
WEEKEND_DAILY_RANGE = (2000, 5000)
MONTHLY_SALARY = 85000.0

# Realistic INR tiers for seeded demo data
SMALL_EXPENSE = [
    10, 12, 15, 20, 25, 30, 35, 45, 55, 65, 75, 80, 99, 100, 120, 150, 180, 200, 220, 250,
]
MEDIUM_EXPENSE = [
    300, 350, 400, 450, 500, 550, 650, 750, 800, 900, 1000, 1200, 1500, 1800, 2000, 2500, 3500, 5000,
]
LARGE_EXPENSE = [6000, 7500, 8000, 10000, 12000, 15000]
RARE_EXPENSE = [20000, 21000, 25000]

SALARY_INCOME = [65000, 72000, 78000, 85000, 92000, 98000]
OTHER_INCOME = [500, 750, 1000, 1500, 2500, 3500, 5000, 8000]

MAIN_ALIASES = {
    "Financial Expenses": "Financial Expense",
    "Communication/PC": "Communication/PC",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("&", "and").replace("-", " ")).strip()


def _build_category_maps(categories: list[dict]) -> tuple[dict[tuple[str, str]], dict[str, str], str]:
    """(main, norm_sub) -> id, main -> default id, fallback expense id."""
    exact: dict[tuple[str, str], str] = {}
    by_main: dict[str, list[tuple[str, str]]] = {}
    default_by_main: dict[str, str] = {}
    fallback_expense = categories[0]["category_id"]

    for row in categories:
        cid = row["category_id"]
        main = row["main_category"]
        sub = row["sub_category"]
        exact[(main, _norm(sub))] = cid
        by_main.setdefault(main, []).append((_norm(sub), cid))
        if _norm(sub) in ("general", "others", "other"):
            default_by_main[main] = cid
        if row["main_category"] == "Food & Drinks" and _norm(sub) == "general":
            fallback_expense = cid

    for main, subs in by_main.items():
        if main not in default_by_main and subs:
            default_by_main[main] = subs[0][1]

    return exact, default_by_main, fallback_expense


def _tag_to_category_id(tag: str | None, categories: list[dict], maps: tuple) -> str:
    exact, default_by_main, fallback = maps
    if not tag or "::" not in str(tag):
        return fallback

    main_raw, sub_raw = str(tag).split("::", 1)
    main = MAIN_ALIASES.get(main_raw.strip(), main_raw.strip())
    sub_n = _norm(sub_raw)

    if (main, sub_n) in exact:
        return exact[(main, sub_n)]

    candidates = [(s, c) for (m, s), c in exact.items() if m == main]
    for sub_key, cid in candidates:
        if sub_n == sub_key or sub_n in sub_key or sub_key in sub_n:
            return cid

    if main in default_by_main:
        return default_by_main[main]

    for row in categories:
        if row["main_category"] == main:
            return row["category_id"]

    return fallback


def _infer_account_type(account_key: str) -> str:
    key = account_key.lower()
    if "cc" in key or "credit" in key:
        return "credit_card"
    if "wallet" in key or "gpay" in key or "paytm" in key:
        return "wallet"
    if "invest" in key:
        return "investment"
    if "current" in key:
        return "checking"
    return "savings"


def _account_display_name(account_key: str) -> str:
    bank = account_key.replace("acc_", "").split("_")[0].upper()
    mapping = {
        "HDFC": "HDFC Bank",
        "ICICI": "ICICI Bank",
        "SBI": "SBI",
        "KOTAK": "Kotak Mahindra",
        "AXIS": "Axis Bank",
        "YES": "Yes Bank",
    }
    return mapping.get(bank, bank.title())


def _txn_type(raw_type: str, tag: str | None) -> str:
    if str(raw_type).lower() == "credit":
        return "income"
    if tag and str(tag).startswith("Income::"):
        return "income"
    return "expense"


def _rng_for_row(seed_key: str) -> random.Random:
    return random.Random(hash(seed_key) & 0xFFFFFFFF)


def _realistic_expense_amount(tag: str | None, seed_key: str) -> float:
    """Map each expense to small day-to-day amounts with occasional large payments."""
    rng = _rng_for_row(seed_key)
    tag_l = (tag or "").lower()

    if "housing::rent" in tag_l or tag_l.endswith("::rent"):
        return float(rng.choice([12000, 15000, 18000, 20000, 21000]))
    if "credit card bill" in tag_l or "loan emi" in tag_l:
        return float(rng.choice([5000, 6500, 8000, 10000, 12000, 15000]))
    if "mutual fund" in tag_l or "sip" in tag_l or "ppf" in tag_l or "nps" in tag_l:
        return float(rng.choice([1000, 1500, 2000, 2500, 3000, 5000]))
    if "subscriptions" in tag_l:
        return float(rng.choice([99, 129, 149, 199, 299, 499, 649, 999]))
    if any(k in tag_l for k in ("cafe", "coffee", "snack", "bakery", "bar")):
        return float(rng.choice([10, 20, 35, 55, 80, 100, 120, 150, 250]))
    if any(k in tag_l for k in ("fuel", "metro", "bus", "taxi", "ride", "transport")):
        return float(rng.choice([20, 45, 55, 100, 150, 250, 350, 650]))
    if "grocery" in tag_l or "food & drinks::general" in tag_l:
        return float(rng.choice([150, 250, 350, 450, 550, 650, 800, 1000]))
    if "electronics" in tag_l or "electronic" in tag_l:
        return float(rng.choice([500, 650, 1000, 1500, 2500, 5000, 10000]))

    roll = rng.random()
    if roll < 0.03:
        return float(rng.choice(RARE_EXPENSE))
    if roll < 0.15:
        return float(rng.choice(LARGE_EXPENSE))
    if roll < 0.40:
        return float(rng.choice(MEDIUM_EXPENSE))
    return float(rng.choice(SMALL_EXPENSE))


def _realistic_income_amount(tag: str | None, seed_key: str) -> float:
    rng = _rng_for_row(f"{seed_key}:income")
    tag_l = (tag or "").lower()
    if "salary" in tag_l or "wage" in tag_l or "invoice" in tag_l:
        return float(rng.choice(SALARY_INCOME))
    if "refund" in tag_l or "cashback" in tag_l:
        return float(rng.choice([100, 150, 250, 500, 750, 1000]))
    return float(rng.choice(OTHER_INCOME))


def _realistic_amount(txn_type: str, tag: str | None, seed_key: str) -> float:
    if txn_type == "income":
        return _realistic_income_amount(tag, seed_key)
    return _realistic_expense_amount(tag, seed_key)


def _ensure_net_savings(tx_df: pd.DataFrame, *, min_ratio: float = MIN_SAVINGS_RATIO) -> pd.DataFrame:
    """Boost salary/income rows so total earnings exceed spending with room to save."""
    df = tx_df.copy()
    income_mask = df["transaction_type"] == "income"
    expense_total = float(df.loc[df["transaction_type"] == "expense", "amount"].sum())
    income_total = float(df.loc[income_mask, "amount"].sum())
    if expense_total <= 0 or income_total <= 0:
        return df

    target_income = expense_total * (1.0 + min_ratio)
    if income_total >= target_income:
        return df

    scale = target_income / income_total
    df.loc[income_mask, "amount"] = (df.loc[income_mask, "amount"] * scale).round(2)
    return df


def _opening_balances(account_ids: list[str]) -> dict[str, float]:
    """Modest starting balances per account before transaction history."""
    openings: dict[str, float] = {}
    for acc_id in account_ids:
        openings[acc_id] = round(random.Random(hash(acc_id) & 0xFFFFFFFF).uniform(8000, 22000), 2)
    return openings


def _shift_dates_to_recent(df: pd.DataFrame, *, end_at: date | None = None) -> pd.DataFrame:
    """Move transaction history so the latest row is near today (dashboard uses current month)."""
    out = df.copy()
    parsed = pd.to_datetime(out["transaction_date"])
    if parsed.empty:
        return out
    end = pd.Timestamp(end_at or date.today())
    latest = parsed.max()
    delta = end - latest
    out["transaction_date"] = (parsed + delta).dt.strftime("%Y-%m-%d")
    return out


def _rng_for_day(day: date, *, salt: str = "daily") -> random.Random:
    return random.Random(hash((day.isoformat(), salt)) & 0xFFFFFFFF)


def _daily_expense_target(day: date) -> float:
    """Per-day expense total: low on Mon–Fri, high on Sat–Sun (Prophet weekly seasonality)."""
    rng = _rng_for_day(day)
    lo, hi = WEEKEND_DAILY_RANGE if day.weekday() >= 5 else WEEKDAY_DAILY_RANGE
    return float(rng.randint(lo, hi))


def _split_daily_amount(total: float, day: date) -> list[float]:
    """Split a daily total into 1–3 expense rows (still sums to the daily target)."""
    rng = _rng_for_day(day, salt="split")
    total = round(total, 2)
    if total <= 0:
        return []
    n_parts = rng.randint(1, 3)
    if n_parts == 1:
        return [total]
    weights = [rng.random() for _ in range(n_parts)]
    weight_sum = sum(weights)
    parts = [round(total * w / weight_sum, 2) for w in weights]
    drift = round(total - sum(parts), 2)
    parts[-1] = round(parts[-1] + drift, 2)
    return [p for p in parts if p > 0]


def _pick_expense_category(day: date, categories: list[dict], fallback_id: str) -> str:
    """Weekend → leisure/shopping; weekday → food & transport-style categories."""
    rng = _rng_for_day(day, salt="cat")
    weekend = day.weekday() >= 5
    preferred_mains = (
        ["Entertainment", "Shopping", "Food & Drinks"]
        if weekend
        else ["Food & Drinks", "Transportation", "Communication/PC"]
    )
    for main in preferred_mains:
        matches = [c["category_id"] for c in categories if c["main_category"] == main]
        if matches:
            return rng.choice(matches)
    return fallback_id


def _merchant_for_day(day: date, part_index: int) -> str:
    rng = _rng_for_day(day, salt=f"merchant:{part_index}")
    if day.weekday() >= 5:
        return rng.choice(
            ["Weekend Restaurant", "Mall Shopping", "Entertainment Venue", "Travel Booking", "Hotel Stay"],
        )
    return rng.choice(
        ["Grocery Store", "Cafe", "Metro Card", "Fuel Station", "Quick Bite", "Pharmacy"],
    )


def _history_date_range(*, end_at: date | None = None, days: int = PROPHET_HISTORY_DAYS) -> tuple[date, date]:
    end = end_at or date.today()
    start = end - timedelta(days=days - 1)
    return start, end


def _build_prophet_daily_transactions(
    *,
    user_id: str,
    account_id: str,
    categories: list[dict],
    fallback_expense_cat: str,
    end_at: date | None = None,
    days: int = PROPHET_HISTORY_DAYS,
) -> list[dict]:
    """One expense row set per calendar day so expenses_to_daily() has full daily coverage."""
    start, end = _history_date_range(end_at=end_at, days=days)
    rows: list[dict] = []
    current = start
    while current <= end:
        daily_total = _daily_expense_target(current)
        cat_id = _pick_expense_category(current, categories, fallback_expense_cat)
        for idx, amount in enumerate(_split_daily_amount(daily_total, current)):
            rows.append(
                {
                    "transaction_id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "account_id": account_id,
                    "category_id": cat_id,
                    "transaction_date": current.strftime("%Y-%m-%d"),
                    "amount": amount,
                    "transaction_type": "expense",
                    "merchant_name": _merchant_for_day(current, idx)[:200],
                    "description": f"Daily spend ({current.strftime('%a')})"[:500],
                },
            )
        current += timedelta(days=1)
    return rows


def _build_monthly_income_transactions(
    *,
    user_id: str,
    account_id: str,
    income_category_id: str,
    start: date,
    end: date,
) -> list[dict]:
    """Salary on the 1st of each month within the expense history window."""
    rows: list[dict] = []
    month_cursor = date(start.year, start.month, 1)
    while month_cursor <= end:
        if month_cursor >= start:
            rows.append(
                {
                    "transaction_id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "account_id": account_id,
                    "category_id": income_category_id,
                    "transaction_date": month_cursor.strftime("%Y-%m-%d"),
                    "amount": MONTHLY_SALARY,
                    "transaction_type": "income",
                    "merchant_name": "Employer Payroll",
                    "description": "Monthly salary",
                },
            )
        if month_cursor.month == 12:
            month_cursor = date(month_cursor.year + 1, 1, 1)
        else:
            month_cursor = date(month_cursor.year, month_cursor.month + 1, 1)
    return rows


def _default_accounts(user_id: str) -> list[dict]:
    """Primary savings + credit card used for seeded daily spend."""
    savings_id = str(uuid.uuid4())
    credit_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    return [
        {
            "account_id": savings_id,
            "user_id": user_id,
            "account_name": "HDFC Bank",
            "account_type": "savings",
            "current_balance": 0.0,
            "created_at": now,
        },
        {
            "account_id": credit_id,
            "user_id": user_id,
            "account_name": "ICICI Credit Card",
            "account_type": "credit_card",
            "current_balance": 0.0,
            "credit_limit": 50000.0,
            "created_at": now,
        },
    ]


def _running_balances(df: pd.DataFrame, opening_balances: dict[str, float]) -> pd.DataFrame:
    """Forward-compute running balance from realistic opening amounts."""
    df = df.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df = df.sort_values(["account_id", "transaction_date"])

    def _per_account(group: pd.DataFrame) -> pd.DataFrame:
        account_id = group.name
        balance = float(opening_balances.get(account_id, 10000.0))
        balances: list[float] = []
        for _, row in group.iterrows():
            balances.append(round(balance, 2))
            amount = float(row["amount"])
            if row["transaction_type"] == "income":
                balance += amount
            else:
                balance -= amount
        g = group.copy()
        g["account_id"] = account_id
        g["running_balance"] = balances
        return g

    return df.groupby("account_id", group_keys=False).apply(_per_account)


def _final_balances(tx_df: pd.DataFrame, opening_balances: dict[str, float]) -> dict[str, float]:
    finals: dict[str, float] = {}
    for acc_id, group in tx_df.groupby("account_id"):
        balance = float(opening_balances.get(acc_id, 10000.0))
        for _, row in group.sort_values("transaction_date").iterrows():
            amount = float(row["amount"])
            if row["transaction_type"] == "income":
                balance += amount
            else:
                balance -= amount
        finals[str(acc_id)] = round(balance, 2)
    return finals


def seed_user(
    *,
    email: str,
    retrain: bool,
    history_days: int = PROPHET_HISTORY_DAYS,
) -> None:
    if supabase is None:
        raise RuntimeError("Supabase client not configured")

    users = supabase.table("users").select("user_id,email,full_name").eq("email", email).execute()
    if not users.data:
        raise ValueError(f"No user found for email {email}")
    target_user_id = users.data[0]["user_id"]
    print(f"Target user: {email} ({target_user_id})")

    if history_days < MIN_DAYS_FOR_PROPHET_USER:
        raise ValueError(
            f"history_days={history_days} is below Prophet minimum {MIN_DAYS_FOR_PROPHET_USER}",
        )

    cats_res = supabase.table("categories").select("category_id,main_category,sub_category").execute()
    categories = cats_res.data or []
    _, _, fallback_expense = _build_category_maps(categories)
    income_cats = [c for c in categories if c["main_category"] == "Income"]
    income_cat_id = income_cats[0]["category_id"] if income_cats else fallback_expense

    # Delete all prior data for this user (same email → same user_id)
    supabase.table("transactions").delete().eq("user_id", target_user_id).execute()
    supabase.table("accounts").delete().eq("user_id", target_user_id).execute()
    supabase.table("budgets").delete().eq("user_id", target_user_id).execute()
    supabase.table("goals").delete().eq("user_id", target_user_id).execute()
    print("Cleared existing accounts, transactions, budgets, and goals for user")

    account_rows = _default_accounts(target_user_id)
    savings_id = account_rows[0]["account_id"]
    credit_id = account_rows[1]["account_id"]
    account_type_by_newid = {savings_id: "savings", credit_id: "credit_card"}

    opening = _opening_balances([savings_id, credit_id])
    opening_signed = dict(opening)
    opening_signed[credit_id] = -abs(float(opening_signed[credit_id]))

    for acc in account_rows:
        acc_id = acc["account_id"]
        acc_type = account_type_by_newid[acc_id]
        payload = {
            **acc,
            "current_balance": opening_signed[acc_id],
        }
        if acc_type == "credit_card":
            payload["credit_limit"] = acc.get("credit_limit") or 50000.0
        supabase.table("accounts").insert(payload).execute()

    print(f"Created {len(account_rows)} accounts")

    hist_start, hist_end = _history_date_range(days=history_days)
    print(
        f"Generating {history_days} days of daily expenses "
        f"({hist_start} .. {hist_end}): weekdays {WEEKDAY_DAILY_RANGE}, weekends {WEEKEND_DAILY_RANGE}",
    )

    # All daily expense totals land on savings so expenses_to_daily() matches weekday/weekend tiers.
    expense_rows = _build_prophet_daily_transactions(
        user_id=target_user_id,
        account_id=savings_id,
        categories=categories,
        fallback_expense_cat=fallback_expense,
        end_at=hist_end,
        days=history_days,
    )

    income_rows = _build_monthly_income_transactions(
        user_id=target_user_id,
        account_id=savings_id,
        income_category_id=income_cat_id,
        start=hist_start,
        end=hist_end,
    )
    rows = expense_rows + income_rows
    tx_df = pd.DataFrame(rows)
    tx_df = _ensure_net_savings(tx_df)
    print(f"Date range: {tx_df['transaction_date'].min()} .. {tx_df['transaction_date'].max()}")
    tx_df = _running_balances(tx_df, opening_signed)
    tx_df["transaction_date"] = pd.to_datetime(tx_df["transaction_date"]).dt.strftime("%Y-%m-%d")
    tx_df["running_balance"] = tx_df["running_balance"].astype(float).round(2)

    final_by_account = _final_balances(tx_df, opening_signed)
    for acc_id, balance in final_by_account.items():
        supabase.table("accounts").update({"current_balance": balance}).eq("account_id", acc_id).execute()

    # Now that we know the actual borrowed range for credit cards, set credit_limit
    # so utilization warnings behave realistically.
    credit_limit_updates: dict[str, float] = {}
    for acc_id, acct_type in account_type_by_newid.items():
        if acct_type != "credit_card":
            continue
        acc_rows = tx_df[tx_df["account_id"] == acc_id]
        max_borrowed = (
            float(acc_rows["running_balance"].abs().max())
            if not acc_rows.empty
            else abs(float(opening_signed.get(acc_id, 0.0)))
        )
        credit_limit_updates[acc_id] = round(max(max_borrowed * 1.25, 1.0), 2)

    for acc_id, credit_limit in credit_limit_updates.items():
        supabase.table("accounts").update({"credit_limit": credit_limit}).eq("account_id", acc_id).eq(
            "user_id", target_user_id
        ).execute()

    income_total = float(tx_df.loc[tx_df["transaction_type"] == "income", "amount"].sum())
    expense_total = float(tx_df.loc[tx_df["transaction_type"] == "expense", "amount"].sum())
    net_savings = income_total - expense_total
    savings_rate = (net_savings / income_total * 100) if income_total else 0.0
    print(
        f"Amount profile: income={income_total:,.2f} expenses={expense_total:,.2f} "
        f"net_savings={net_savings:,.2f} ({savings_rate:.1f}%)"
    )

    records = tx_df.astype(object).where(pd.notnull(tx_df), None).to_dict(orient="records")
    batch_size = 200
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        supabase.table("transactions").upsert(batch, on_conflict="transaction_id").execute()
        print(f"  transactions {start + 1}-{min(start + batch_size, len(records))} / {len(records)}")

    from app.services.forecast_features import expenses_to_daily

    expense_df = tx_df[tx_df["transaction_type"] == "expense"].copy()
    daily = expenses_to_daily(expense_df)
    weekend_avg = float(daily.loc[pd.to_datetime(daily["date"]).dt.dayofweek >= 5, "daily_expense"].mean())
    weekday_avg = float(daily.loc[pd.to_datetime(daily["date"]).dt.dayofweek < 5, "daily_expense"].mean())
    print(
        f"Inserted {len(records)} transactions ({len(daily)} Prophet daily points, "
        f"weekday avg={weekday_avg:,.0f} weekend avg={weekend_avg:,.0f})",
    )

    supabase.table("users").update({"full_name": "Suyash Bhadouria"}).eq("user_id", target_user_id).execute()

    if retrain:
        print("Training Prophet models from database…")
        from app.services.forecast_service import reload_models
        from app.services.prophet_training_service import run_training_pipeline

        result = run_training_pipeline(promote=True)
        reload_models(force_storage_sync=False)
        print(
            f"Training done: users={result['trained_users']} mape={result.get('test_mape')} "
            f"path={result.get('production_path')}",
        )

    print("\nTest forecast:")
    print(f"  http://127.0.0.1:8000/api/forecast?user_id={target_user_id}&period=1m")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed Supabase user with daily expense history for Prophet training",
    )
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--retrain", action="store_true", help="Retrain production Prophet bundle after seed")
    parser.add_argument(
        "--history-days",
        type=int,
        default=PROPHET_HISTORY_DAYS,
        help=f"Consecutive days of expense history (min {MIN_DAYS_FOR_PROPHET_USER})",
    )
    args = parser.parse_args()

    try:
        seed_user(
            email=args.email,
            retrain=args.retrain,
            history_days=args.history_days,
        )
        return 0
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
