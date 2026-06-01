"""Admin access checks for model operations."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException

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


async def require_admin(x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    try:
        res = supabase.table("users").select("*").eq("user_id", x_user_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth lookup failed: {exc}") from exc
    if not res.data:
        raise HTTPException(status_code=401, detail="User not found")
    user = res.data[0]
    if not _user_is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
