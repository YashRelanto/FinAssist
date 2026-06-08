from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from app.services.forecast_service import (
    generate_forecast,
    get_model_status,
    reload_models,
)
from app.utils.analysis_period import DEFAULT_PERIOD, normalize_period
from app.utils.supabase_client import supabase

router = APIRouter(prefix="/api")


@router.get("/forecast")
async def get_forecast(
    user_id: str,
    account_id: str | None = None,
    category_id: str | None = None,
    merchant: str | None = None,
    period: str = Query(default=DEFAULT_PERIOD, description="1m, 3m, 5m, or all"),
):
    try:
        period_key = normalize_period(period)
        # Prophet training + comparisons need deep history; UI metrics use calendar months.
        lookback_days = 730 if period_key != "all" else 3650
        start_date = (date.today() - timedelta(days=lookback_days)).isoformat()

        tx_query = (
            supabase.table("transactions")
            .select(
                "transaction_id,transaction_date,amount,transaction_type,"
                "merchant_name,description,account_id,category_id"
            )
            .eq("user_id", user_id)
            .gte("transaction_date", start_date)
            .order("transaction_date")
        )
        if account_id:
            tx_query = tx_query.eq("account_id", account_id)
        if category_id:
            tx_query = tx_query.eq("category_id", category_id)
        if merchant:
            # Best-effort DB-side filter; forecast_service will also apply a contains filter.
            tx_query = tx_query.ilike("merchant_name", f"%{merchant}%")

        trans_res = tx_query.execute()

        cat_res = (
            supabase.table("categories")
            .select("category_id,main_category,sub_category")
            .execute()
        )

        result = generate_forecast(
            trans_res.data or [],
            cat_res.data or [],
            user_id=user_id,
            account_id=account_id,
            category_id=category_id,
            merchant=merchant,
            period=period_key,
        )
        result["filters"] = {
            "account_id": account_id,
            "category_id": category_id,
            "merchant": merchant,
            "period": period_key,
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
                "label": "Prophet (global)",
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
