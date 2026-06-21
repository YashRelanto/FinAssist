"""Admin access checks for model operations."""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException

from app.core.auth import get_current_user
from app.utils.supabase_client import supabase

ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "admin@finassist.ai").split(",")
    if e.strip()
}


def _user_is_admin(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    if role == "admin":
        return True
    return (user.get("email") or "").lower() in ADMIN_EMAILS


async def require_admin(current_user: dict = Depends(get_current_user)):
    """Validate Bearer JWT, then ensure the authenticated user is an admin."""
    user_id = current_user["user_id"]
    try:
        res = supabase.table("users").select("*").eq("user_id", user_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth lookup failed: {exc}") from exc
    if not res.data:
        raise HTTPException(status_code=401, detail="User not found")
    user = res.data[0]
    if not user.get("email"):
        user = {**user, "email": current_user.get("email", "")}
    if not _user_is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
