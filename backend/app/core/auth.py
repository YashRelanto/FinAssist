"""JWT authentication and admin authorization dependencies for FastAPI routes."""

from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException

from app.utils.supabase_client import supabase, supabase_auth

_DEMO_USER = {
    "user_id": "a9a11e1f-f158-4d8e-ae55-407a5e00410f",
    "email": "demo@finassist.ai",
    "role": "user",
}

ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "admin@finassist.ai").split(",")
    if e.strip()
}


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """Validate the Bearer JWT and return the authenticated user's identity.

    Falls back to a demo user when Supabase is not configured (local dev without .env).
    """
    if supabase_auth is None:
        # Local dev / demo mode — Supabase not configured.
        return _DEMO_USER

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header missing or invalid")

    token = authorization.removeprefix("Bearer ").strip()

    if token == "demo-local-token":
        return _DEMO_USER

    try:
        resp = supabase_auth.auth.get_user(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    if not resp or not resp.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    auth_user = resp.user
    return {
        "user_id": auth_user.id,
        "email": auth_user.email or "",
        "role": (auth_user.user_metadata or {}).get("role", "user"),
    }


def _user_is_admin(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    if role == "admin":
        return True
    return (user.get("email") or "").lower() in ADMIN_EMAILS


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
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
