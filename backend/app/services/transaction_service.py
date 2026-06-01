"""Create transactions and keep account balances in sync."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import HTTPException

from app.utils.supabase_client import supabase_db

logger = logging.getLogger(__name__)


def _resolve_category_id(main_category: str, sub_category: str) -> str | None:
    if not supabase_db:
        return None
    cat_res = (
        supabase_db.table("categories")
        .select("category_id")
        .ilike("main_category", main_category)
        .ilike("sub_category", sub_category)
        .execute()
    )
    if not cat_res.data:
        cat_res = (
            supabase_db.table("categories")
            .select("category_id")
            .ilike("main_category", main_category)
            .ilike("sub_category", "General")
            .execute()
        )
    if cat_res.data:
        return cat_res.data[0]["category_id"]
    fallback = (
        supabase_db.table("categories")
        .select("category_id")
        .ilike("main_category", "Others")
        .ilike("sub_category", "General")
        .execute()
    )
    return fallback.data[0]["category_id"] if fallback.data else None


def _resolve_account(user_id: str, account_id_or_name: str) -> tuple[str, dict[str, Any]]:
    if not supabase_db:
        raise HTTPException(status_code=503, detail="Database unavailable")

    account_id = account_id_or_name
    acc_res = None

    try:
        uuid.UUID(account_id_or_name)
        acc_res = (
            supabase_db.table("accounts")
            .select("*")
            .eq("account_id", account_id_or_name)
            .eq("user_id", user_id)
            .execute()
        )
    except ValueError:
        pass

    if not acc_res or not acc_res.data:
        acc_check = (
            supabase_db.table("accounts")
            .select("*")
            .eq("user_id", user_id)
            .eq("account_name", account_id_or_name)
            .execute()
        )
        if acc_check.data:
            acc_res = acc_check
            account_id = acc_check.data[0]["account_id"]
        else:
            new_acc = (
                supabase_db.table("accounts")
                .insert(
                    {
                        "user_id": user_id,
                        "account_name": account_id_or_name,
                        "account_type": "checking",
                        "current_balance": 0.0,
                    }
                )
                .execute()
            )
            if not new_acc.data:
                raise HTTPException(status_code=500, detail="Failed to create account")
            acc_res = new_acc
            account_id = new_acc.data[0]["account_id"]

    return account_id, acc_res.data[0]


def apply_balance_delta(current_balance: float, amount: float, transaction_type: str) -> float:
    """DB stores positive amounts; type determines balance direction."""
    magnitude = abs(float(amount))
    tx_type = (transaction_type or "expense").lower()
    if tx_type == "income":
        return current_balance + magnitude
    if tx_type == "transfer":
        return current_balance
    return current_balance - magnitude


def create_transaction_record(
    *,
    user_id: str,
    account_id: str,
    amount: float,
    transaction_type: str,
    merchant_name: str,
    description: str,
    main_category: str,
    sub_category: str = "General",
    transaction_date: str,
) -> dict[str, Any]:
    """
    Insert a transaction and update the linked account's current_balance.
    Returns transaction row plus balance metadata.
    """
    if not supabase_db:
        raise HTTPException(status_code=503, detail="Database unavailable")

    category_id = _resolve_category_id(main_category, sub_category)
    if not category_id:
        raise HTTPException(status_code=400, detail="Could not resolve category")

    resolved_account_id, account = _resolve_account(user_id, account_id)
    curr_bal = float(account.get("current_balance") or 0)
    stored_amount = abs(float(amount))
    new_bal = apply_balance_delta(curr_bal, stored_amount, transaction_type)

    trans_data = {
        "user_id": user_id,
        "account_id": resolved_account_id,
        "category_id": category_id,
        "amount": stored_amount,
        "transaction_type": transaction_type.lower(),
        "merchant_name": merchant_name,
        "description": description,
        "transaction_date": transaction_date,
        "running_balance": new_bal,
    }

    insert_res = supabase_db.table("transactions").insert(trans_data).execute()
    if not insert_res.data:
        raise HTTPException(status_code=500, detail="Failed to insert transaction")

    update_res = (
        supabase_db.table("accounts")
        .update({"current_balance": new_bal})
        .eq("account_id", resolved_account_id)
        .eq("user_id", user_id)
        .select("account_id, current_balance")
        .execute()
    )
    if not update_res.data:
        logger.error(
            "Transaction inserted but account balance not updated: account_id=%s user_id=%s",
            resolved_account_id,
            user_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Transaction saved but account balance could not be updated",
        )

    row = insert_res.data[0]
    return {
        "transaction": row,
        "account_id": resolved_account_id,
        "account_name": account.get("account_name"),
        "previous_balance": curr_bal,
        "new_balance": new_bal,
    }
