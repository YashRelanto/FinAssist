"""Shared account queries for API routes and analysis services."""

from __future__ import annotations

from typing import Any

from app.utils.supabase_client import supabase

ACCOUNT_BASE_COLUMNS = (
    "account_id,user_id,account_name,account_type,current_balance,bank_name,account_holder,account_number,ifsc,created_at"
)


def fetch_user_accounts(user_id: str) -> list[dict[str, Any]]:
    if supabase is None:
        return []
    uid = (user_id or "").strip()
    if not uid:
        return []

    try:
        res = (
            supabase.table("accounts")
            .select(f"{ACCOUNT_BASE_COLUMNS},credit_limit")
            .eq("user_id", uid)
            .order("created_at", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        print(f"accounts select (with credit_limit) failed, retrying: {exc}")
        try:
            res = (
                supabase.table("accounts")
                .select(ACCOUNT_BASE_COLUMNS)
                .eq("user_id", uid)
                .order("created_at", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as exc2:
            print(f"accounts select fallback failed: {exc2}")
            res = (
                supabase.table("accounts")
                .select(ACCOUNT_BASE_COLUMNS)
                .eq("user_id", uid)
                .execute()
            )
            return res.data or []


def insert_account(row: dict[str, Any]) -> dict[str, Any]:
    if supabase is None:
        raise RuntimeError("Supabase is not configured")

    payload = dict(row)
    try:
        response = supabase.table("accounts").insert(payload).execute()
    except Exception as exc:
        if "credit_limit" in str(exc).lower() and "credit_limit" in payload:
            payload.pop("credit_limit", None)
            response = supabase.table("accounts").insert(payload).execute()
        else:
            raise

    if not response.data:
        raise RuntimeError("Failed to create account")
    return response.data[0]
