#!/usr/bin/env python3
"""
Seed a Supabase user with transactions from data/raw/transactions_raw.csv.

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
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.utils.supabase_client import supabase  # noqa: E402

RAW_CSV = ROOT / "data" / "raw" / "transactions_raw.csv"
DEFAULT_EMAIL = "suyash.bhadouria@relanto.ai"
DEFAULT_SOURCE_RAW_USER = "usr_8fca52e4"  # richest row count in raw file
MIN_SAVINGS_RATIO = 0.18  # income should exceed expenses by at least ~18%

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
    source_raw_user: str,
    retrain: bool,
    shift_to_today: bool,
) -> None:
    if supabase is None:
        raise RuntimeError("Supabase client not configured")

    users = supabase.table("users").select("user_id,email,full_name").eq("email", email).execute()
    if not users.data:
        raise ValueError(f"No user found for email {email}")
    target_user_id = users.data[0]["user_id"]
    print(f"Target user: {email} ({target_user_id})")

    raw = pd.read_csv(RAW_CSV)
    subset = raw[raw["user_id"] == source_raw_user].copy()
    if subset.empty:
        raise ValueError(f"No rows for source raw user {source_raw_user}")

    print(f"Source raw user {source_raw_user}: {len(subset)} rows ({subset['date'].min()} .. {subset['date'].max()})")

    cats_res = supabase.table("categories").select("category_id,main_category,sub_category").execute()
    categories = cats_res.data or []
    cat_maps = _build_category_maps(categories)

    # Replace existing seed data for this user
    supabase.table("transactions").delete().eq("user_id", target_user_id).execute()
    supabase.table("accounts").delete().eq("user_id", target_user_id).execute()
    print("Cleared existing accounts/transactions for user")

    account_id_map: dict[str, str] = {}

    for raw_acc in sorted(subset["account_id"].unique()):
        new_id = str(uuid.uuid4())
        account_id_map[raw_acc] = new_id

    opening = _opening_balances(list(account_id_map.values()))

    for raw_acc, new_id in account_id_map.items():
        supabase.table("accounts").insert(
            {
                "account_id": new_id,
                "user_id": target_user_id,
                "account_name": _account_display_name(raw_acc),
                "account_type": _infer_account_type(raw_acc),
                "current_balance": opening[new_id],
                "created_at": datetime.utcnow().isoformat(),
            },
        ).execute()

    print(f"Created {len(account_id_map)} accounts")

    rows: list[dict] = []
    for _, r in subset.iterrows():
        raw_acc = r["account_id"]
        acc_id = account_id_map[raw_acc]
        tag = r.get("tags")
        txn_type = _txn_type(r["transaction_type"], tag)
        seed_key = str(r.get("reference_id") or r.name)
        amount = _realistic_amount(txn_type, tag, seed_key)
        cat_id = _tag_to_category_id(tag, categories, cat_maps)
        if txn_type == "income":
            income_cats = [c for c in categories if c["main_category"] == "Income"]
            if income_cats:
                cat_id = income_cats[0]["category_id"]

        rows.append(
            {
                "transaction_id": str(uuid.uuid4()),
                "user_id": target_user_id,
                "account_id": acc_id,
                "category_id": cat_id,
                "transaction_date": pd.to_datetime(r["date"]).strftime("%Y-%m-%d"),
                "amount": round(amount, 2),
                "transaction_type": txn_type,
                "merchant_name": str(r.get("merchant_name") or "Unknown")[:200],
                "description": str(r.get("remark") or r.get("merchant_name") or "")[:500] or None,
            },
        )

    tx_df = pd.DataFrame(rows)
    tx_df = _ensure_net_savings(tx_df)
    if shift_to_today:
        tx_df = _shift_dates_to_recent(tx_df)
        print(f"Shifted dates to {tx_df['transaction_date'].min()} .. {tx_df['transaction_date'].max()}")
    tx_df = _running_balances(tx_df, opening)
    tx_df["transaction_date"] = pd.to_datetime(tx_df["transaction_date"]).dt.strftime("%Y-%m-%d")
    tx_df["running_balance"] = tx_df["running_balance"].astype(float).round(2)

    final_by_account = _final_balances(tx_df, opening)
    for acc_id, balance in final_by_account.items():
        supabase.table("accounts").update({"current_balance": balance}).eq("account_id", acc_id).execute()

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

    expense_df = tx_df[tx_df["transaction_type"] == "expense"].copy()
    expense_df["week"] = pd.to_datetime(expense_df["transaction_date"]).dt.to_period("W")
    expense_weeks = expense_df["week"].nunique()
    print(f"Inserted {len(records)} transactions ({expense_weeks} expense weeks)")

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
    print(f"  http://127.0.0.1:8000/api/forecast?user_id={target_user_id}&days=90")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Supabase user from raw transactions CSV")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--source-raw-user", default=DEFAULT_SOURCE_RAW_USER)
    parser.add_argument("--retrain", action="store_true", help="Retrain production Prophet bundle after seed")
    parser.add_argument(
        "--no-shift-dates",
        action="store_true",
        help="Keep original CSV dates (dashboard 'this month' will be empty if data is old)",
    )
    args = parser.parse_args()

    try:
        seed_user(
            email=args.email,
            source_raw_user=args.source_raw_user,
            retrain=args.retrain,
            shift_to_today=not args.no_shift_dates,
        )
        return 0
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
