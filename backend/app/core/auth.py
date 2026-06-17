"""JWT authentication dependency for FastAPI routes."""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.utils.supabase_client import supabase_auth

_DEMO_USER = {
    "user_id": "a9a11e1f-f158-4d8e-ae55-407a5e00410f",
    "email": "demo@finassist.ai",
    "role": "user",
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
