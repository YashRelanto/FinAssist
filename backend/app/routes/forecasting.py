from fastapi import APIRouter, HTTPException, Query

from app.services.forecast_service import (
    generate_forecast,
    get_model_status,
    reload_models,
)
from app.utils.supabase_client import supabase

router = APIRouter(prefix="/api")


@router.get("/forecast")
async def get_forecast(
    user_id: str,
    account_id: str | None = None,
    category_id: str | None = None,
    merchant: str | None = None,
    days: int = Query(default=30, ge=7, le=90),
):
    try:
        trans_res = (
            supabase.table("transactions")
            .select("*")
            .eq("user_id", user_id)
            .order("transaction_date")
            .execute()
        )
        cat_res = supabase.table("categories").select("*").execute()

        result = generate_forecast(
            trans_res.data or [],
            cat_res.data or [],
            user_id=user_id,
            account_id=account_id,
            category_id=category_id,
            merchant=merchant,
            days_analyzed=days,
        )
        result["filters"] = {
            "account_id": account_id,
            "category_id": category_id,
            "merchant": merchant,
            "days": days,
        }
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/forecast/models")
async def get_forecast_models():
    status = get_model_status()
    return {
        "success": True,
        "default": "prophet",
        "models": [
            {
                "id": "prophet",
                "label": "Prophet (per user)",
                "loaded": status["loaded"],
                "accuracy_pct": status["accuracy_pct"],
                "trained_users": status["trained_users"],
                "trained_at": status["trained_at"],
            }
        ],
        "status": status,
    }


@router.get("/forecast/model-status")
async def forecast_model_status():
    status = get_model_status()
    return {"success": True, "status": status}


@router.post("/forecast/reload-model")
async def forecast_reload_model():
    loaded = reload_models(force_storage_sync=True)
    return {"success": loaded.get("loaded", False), **loaded}
