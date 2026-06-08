"""Tests for yearly user seeding in seed_user_from_raw.py."""

from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "seed_user_from_raw.py"

_spec = importlib.util.spec_from_file_location("seed_user_from_raw", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)


def test_pick_expense_amount_tiers():
    rng = __import__("random").Random(42)
    amounts = [_mod._pick_expense_amount(rng) for _ in range(1000)]
    small = sum(1 for a in amounts if 10 <= a <= 2000)
    medium = sum(1 for a in amounts if 2000 < a <= 5000)
    large = sum(1 for a in amounts if 5000 < a <= 10000)
    assert small >= 600
    assert medium >= 50
    assert large >= 10


def test_build_yearly_expenses_stays_under_salary_per_month():
    end = date(2025, 6, 30)
    start, _ = _mod._history_date_range(end_at=end, days=365)
    rows = _mod._build_yearly_expense_transactions(
        user_id="u1",
        account_id="a1",
        categories=[
            {"category_id": "c1", "main_category": "Food & Drinks", "sub_category": "General"},
            {"category_id": "c2", "main_category": "Shopping", "sub_category": "General"},
            {"category_id": "c3", "main_category": "Transportation", "sub_category": "General"},
            {"category_id": "c4", "main_category": "Life & Entertainment", "sub_category": "General"},
        ],
        fallback_expense_cat="c1",
        end_at=end,
        days=365,
    )
    income_rows = _mod._build_monthly_income_transactions(
        user_id="u1",
        account_id="a1",
        income_category_id="c1",
        start=start,
        end=end,
    )
    df = pd.DataFrame(rows + income_rows)
    df["month"] = pd.to_datetime(df["transaction_date"]).dt.to_period("M")
    for month, group in df.groupby("month"):
        inc = float(group.loc[group["transaction_type"] == "income", "amount"].sum())
        exp = float(group.loc[group["transaction_type"] == "expense", "amount"].sum())
        if inc > 0:
            assert exp < inc, f"Month {month} overspent"


def test_small_expenses_are_common():
    amounts = [
        _mod._realistic_expense_amount("Food & Drinks::Cafes & Coffee", f"k{i}")
        for i in range(200)
    ]
    small = sum(1 for a in amounts if a <= 2000)
    assert small >= 100


def test_rare_large_expenses_exist():
    amounts = [
        _mod._realistic_expense_amount("Shopping::General", f"r{i}")
        for i in range(500)
    ]
    assert any(a >= 5000 for a in amounts)


def test_ensure_net_savings_boosts_income():
    df = pd.DataFrame(
        [
            {"transaction_type": "income", "amount": 50000.0},
            {"transaction_type": "expense", "amount": 48000.0},
        ]
    )
    out = _mod._ensure_net_savings(df, min_ratio=0.18)
    income = float(out.loc[out["transaction_type"] == "income", "amount"].sum())
    expense = float(out.loc[out["transaction_type"] == "expense", "amount"].sum())
    assert income > expense


def test_monthly_salary_is_fixed():
    rows = _mod._build_monthly_income_transactions(
        user_id="u1",
        account_id="a1",
        income_category_id="c1",
        start=date(2025, 1, 1),
        end=date(2025, 12, 31),
    )
    amounts = [r["amount"] for r in rows]
    assert len(amounts) == 12
    assert all(a == _mod.MONTHLY_SALARY for a in amounts)
