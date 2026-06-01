"""Tests for transaction balance helpers."""

from app.services.transaction_service import apply_balance_delta


def test_apply_balance_delta_expense():
    assert apply_balance_delta(1000.0, 50.0, "expense") == 950.0


def test_apply_balance_delta_income():
    assert apply_balance_delta(1000.0, 200.0, "income") == 1200.0


def test_apply_balance_delta_transfer_unchanged():
    assert apply_balance_delta(1000.0, 75.0, "transfer") == 1000.0
