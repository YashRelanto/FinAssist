"""Sync Supabase Auth users with public.users and public.user_profiles."""

from __future__ import annotations

import logging
from typing import Any

from app.utils.supabase_client import supabase_db

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = {
    "onboarded": False,
    "income": 0,
    "city_tier": "Metro",
    "fixed_rent": 0,
    "fixed_emi": 0,
    "biggest_category": "",
    "primary_goal": "",
}


def _extract_error_message(exc: Exception) -> str:
    if hasattr(exc, "message"):
        msg = exc.message
        if isinstance(msg, dict):
            return str(msg.get("message", msg))
        return str(msg)
    return str(exc)


def ensure_user_with_profile(user_id: str, email: str, full_name: str) -> dict[str, Any]:
    """
    Return merged user + profile. Creates missing rows using the service-role DB client.
    """
    if not supabase_db:
        raise RuntimeError("Database client is not configured")

    uid = str(user_id)
    u_res = supabase_db.table("users").select("*").eq("user_id", uid).execute()
    if not u_res.data:
        logger.info("Creating public.users row for auth user %s", uid)
        u_res = (
            supabase_db.table("users")
            .insert({"user_id": uid, "full_name": full_name, "email": email})
            .execute()
        )
        if not u_res.data:
            raise RuntimeError("Failed to create user profile row")

    user = u_res.data[0]

    p_res = supabase_db.table("user_profiles").select("*").eq("user_id", uid).execute()
    if not p_res.data:
        logger.info("Creating public.user_profiles row for auth user %s", uid)
        profile_row = {"user_id": uid, **DEFAULT_PROFILE}
        p_res = supabase_db.table("user_profiles").insert(profile_row).execute()
        if not p_res.data:
            raise RuntimeError("Failed to create user_profiles row")

    profile = p_res.data[0]
    role = (user.get("role") or "user").lower()

    return {
        "user_id": user["user_id"],
        "full_name": user["full_name"],
        "email": user["email"],
        "role": role,
        "onboarded": profile["onboarded"],
        "income": float(profile["income"]),
        "city_tier": profile["city_tier"],
        "fixed_rent": float(profile["fixed_rent"]),
        "fixed_emi": float(profile["fixed_emi"]),
        "biggest_category": profile["biggest_category"],
        "primary_goal": profile["primary_goal"],
    }


def auth_error_detail(exc: Exception) -> tuple[int, str]:
    """Map Supabase/auth exceptions to HTTP status and a safe user-facing message."""
    err_msg = _extract_error_message(exc).lower()
    raw = _extract_error_message(exc)

    if (
        "email not confirmed" in err_msg
        or "email_not_confirmed" in err_msg
        or ("confirm" in err_msg and "email" in err_msg)
    ):
        return 400, "email_not_confirmed"

    if "invalid login credentials" in err_msg or (
        "invalid" in err_msg and "credential" in err_msg
    ):
        return 401, "Invalid email or password"

    if "row-level security" in err_msg or "42501" in raw:
        logger.error("RLS blocked profile sync: %s", raw)
        return 500, "Account setup failed. Please contact support."

    if "user already exists" in err_msg or "already registered" in err_msg:
        return 400, "User already exists"

    return 401, "Invalid email or password"
