"""Internal endpoints invoked by Supabase Edge Functions (cron / webhooks)."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.services.model_training_service import run_training_sync

router = APIRouter(prefix="/api/internal", tags=["internal"])


def _verify_cron_secret(authorization: str | None) -> None:
    expected = settings.FORECAST_CRON_SECRET
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="FORECAST_CRON_SECRET is not configured on the API server",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.post("/train-forecast")
async def internal_train_forecast(authorization: str | None = Header(default=None)):
    """
    Triggered by Supabase Edge Function on schedule.
    Trains per-user Prophet models from DB, uploads to Storage, reloads cache.
    """
    _verify_cron_secret(authorization)
    try:
        result = run_training_sync()
        return {"success": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
