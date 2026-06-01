"""Tests for realistic amount shaping in seed_user_from_raw.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "seed_user_from_raw.py"

_spec = importlib.util.spec_from_file_location("seed_user_from_raw", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)


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
