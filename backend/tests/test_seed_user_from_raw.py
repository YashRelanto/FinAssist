"""Tests for Prophet-oriented daily seeding in seed_user_from_raw.py."""

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


def test_daily_expense_target_weekend_vs_weekday():
    saturday = date(2025, 6, 7)
    monday = date(2025, 6, 9)
    weekend_amounts = [_mod._daily_expense_target(saturday + timedelta(days=7 * i)) for i in range(8)]
    weekday_amounts = [_mod._daily_expense_target(monday + timedelta(days=i)) for i in range(5)]
    assert all(_mod.WEEKEND_DAILY_RANGE[0] <= a <= _mod.WEEKEND_DAILY_RANGE[1] for a in weekend_amounts)
    assert all(_mod.WEEKDAY_DAILY_RANGE[0] <= a <= _mod.WEEKDAY_DAILY_RANGE[1] for a in weekday_amounts)
    assert min(weekend_amounts) > max(weekday_amounts)


def test_build_prophet_daily_transactions_covers_each_day():
    start, end = _mod._history_date_range(end_at=date(2025, 6, 30), days=60)
    rows = _mod._build_prophet_daily_transactions(
        user_id="u1",
        account_id="a1",
        categories=[{"category_id": "c1", "main_category": "Food & Drinks", "sub_category": "General"}],
        fallback_expense_cat="c1",
        end_at=end,
        days=60,
    )
    df = pd.DataFrame(rows)
    daily = df.groupby("transaction_date")["amount"].sum()
    assert len(daily) == 60
    assert daily.index.min() == start.isoformat()
    assert daily.index.max() == end.isoformat()


def test_small_expenses_are_common():
    amounts = [
        _mod._realistic_expense_amount("Food & Drinks::Cafes & Coffee", f"k{i}")
        for i in range(200)
    ]
    small = sum(1 for a in amounts if a <= 250)
    assert small >= 100


def test_rare_large_expenses_exist():
    amounts = [
        _mod._realistic_expense_amount("Shopping::General", f"r{i}")
        for i in range(500)
    ]
    assert any(a >= 10000 for a in amounts)


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
