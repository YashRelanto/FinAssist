from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.utils.supabase_client import supabase, supabase_auth, supabase_db
from app.core.auth import get_current_user
from app.services.user_profile_service import (
    ensure_user_with_profile,
    auth_error_detail,
)
from app.services.dashboard_metrics_service import (
    build_budget_goals_payload,
    build_dashboard_payload,
    compute_net_savings,
    normalize_category_name,
    resolve_budget_period_dates,
)
from app.services.accounts_service import fetch_user_accounts, insert_account
from app.services.transaction_service import (
    create_transaction_record,
    update_transaction_record,
)
from datetime import datetime

router = APIRouter(prefix="/api")


# ── Authorization helpers ─────────────────────────────────────────────────────

def _fetch_owner(table: str, pk_col: str, pk_val: str) -> str:
    """Return the user_id that owns a resource row, or raise 404."""
    res = supabase.table(table).select("user_id").eq(pk_col, pk_val).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"{table} record not found")
    return res.data[0]["user_id"]


def _assert_owner(resource_user_id: str, current_user: dict) -> None:
    """Raise 403 if current user doesn't own the resource. Admins bypass."""
    if current_user.get("role") == "admin":
        return
    if resource_user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")


# ─────────────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str


def _display_name_from_auth_user(auth_user, fallback_email: str) -> str:
    meta = auth_user.user_metadata or {}
    return meta.get("full_name") or fallback_email.split("@")[0]


def _login_payload(
    user: dict,
    email_confirmed: bool = True,
    *,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> dict:
    """Flat + nested shape so auth clients receive both response shapes."""
    body = {**user, "email_confirmed": email_confirmed, "success": True}
    body["user"] = user
    if access_token:
        body["access_token"] = access_token
    if refresh_token:
        body["refresh_token"] = refresh_token
    return body


class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/auth/refresh")
async def refresh_token(req: RefreshRequest):
    """Exchange a Supabase refresh token for a new access token."""
    if not supabase_auth:
        raise HTTPException(status_code=503, detail="Auth service not configured")
    try:
        resp = supabase_auth.auth.refresh_session(req.refresh_token)
        if not resp or not resp.session:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        return {
            "access_token": resp.session.access_token,
            "refresh_token": resp.session.refresh_token,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token refresh failed") from exc


@router.post("/login")
async def api_login(req: LoginRequest):
    if not supabase_auth or not supabase_db:
        return _login_payload(
            {
                "user_id": "a9a11e1f-f158-4d8e-ae55-407a5e00410f",
                "full_name": "Demo User",
                "email": req.email,
                "role": "user",
                "onboarded": False,
                "income": 45000,
                "city_tier": "Metro",
                "fixed_rent": 1500,
                "fixed_emi": 500,
                "biggest_category": "Shopping",
                "primary_goal": "Save More Money",
            },
            access_token="demo-local-token",
        )

    try:
        auth_res = supabase_auth.auth.sign_in_with_password({
            "email": req.email,
            "password": req.password,
        })
        if not auth_res.user:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        full_name = _display_name_from_auth_user(auth_res.user, req.email)
        user = ensure_user_with_profile(auth_res.user.id, req.email, full_name)
        session = auth_res.session
        return _login_payload(
            user,
            access_token=session.access_token if session else None,
            refresh_token=session.refresh_token if session else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in api_login: {e}")
        status, detail = auth_error_detail(e)
        raise HTTPException(status_code=status, detail=detail)


@router.post("/register")
async def api_register(req: RegisterRequest):
    if not supabase_auth or not supabase_db:
        return _login_payload({
            "user_id": "a9a11e1f-f158-4d8e-ae55-407a5e00410f",
            "full_name": req.full_name,
            "email": req.email,
            "role": "user",
            "onboarded": False,
            "income": 0,
            "city_tier": "Metro",
            "fixed_rent": 0,
            "fixed_emi": 0,
            "biggest_category": "",
            "primary_goal": "",
        }, email_confirmed=False)

    try:
        auth_res = supabase_auth.auth.sign_up({
            "email": req.email,
            "password": req.password,
            "options": {"data": {"full_name": req.full_name}},
        })
        if not auth_res.user:
            raise HTTPException(status_code=500, detail="Failed to create auth user")

        email_confirmed = auth_res.session is not None or bool(
            auth_res.user.email_confirmed_at
        )
        user = ensure_user_with_profile(auth_res.user.id, req.email, req.full_name)
        session = auth_res.session
        return _login_payload(
            user,
            email_confirmed=email_confirmed,
            access_token=session.access_token if session else None,
            refresh_token=session.refresh_token if session else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in api_register: {e}")
        status, detail = auth_error_detail(e)
        raise HTTPException(status_code=status, detail=detail)

class UserUpdateRequest(BaseModel):
    full_name: str
    email: str
    onboarded: Optional[bool] = None
    income: Optional[float] = None
    city_tier: Optional[str] = None
    fixed_rent: Optional[float] = None
    fixed_emi: Optional[float] = None
    biggest_category: Optional[str] = None
    primary_goal: Optional[str] = None

@router.put("/users/{user_id}")
async def update_user_profile(
    user_id: str,
    req: UserUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(user_id, current_user)
    db = supabase_db or supabase
    try:
        response = db.table("users").update({
            "full_name": req.full_name,
            "email": req.email
        }).eq("user_id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found or update failed")
            
        profile_data = {}
        if req.onboarded is not None: profile_data["onboarded"] = req.onboarded
        if req.income is not None: profile_data["income"] = req.income
        if req.city_tier is not None: profile_data["city_tier"] = req.city_tier
        if req.fixed_rent is not None: profile_data["fixed_rent"] = req.fixed_rent
        if req.fixed_emi is not None: profile_data["fixed_emi"] = req.fixed_emi
        if req.biggest_category is not None: profile_data["biggest_category"] = req.biggest_category
        if req.primary_goal is not None: profile_data["primary_goal"] = req.primary_goal
        
        if profile_data:
            prof_check = db.table("user_profiles").select("*").eq("user_id", user_id).execute()
            if prof_check.data:
                db.table("user_profiles").update(profile_data).eq("user_id", user_id).execute()
            else:
                profile_data["user_id"] = user_id
                db.table("user_profiles").insert(profile_data).execute()
            
        return {"success": True, "message": "Profile updated successfully", "user": response.data[0]}
    except Exception as e:
        print(f"Error updating user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class OAuthLoginRequest(BaseModel):
    user_id: str
    email: str
    full_name: str

@router.post("/oauth-login")
async def api_oauth_login(req: OAuthLoginRequest):
    db = supabase_db or supabase
    if not db:
        return {
            "success": True,
            "message": "OAuth login successful",
            "user": {
                "user_id": req.user_id,
                "full_name": req.full_name,
                "email": req.email,
                "role": "user",
                "onboarded": False,
                "income": 0,
                "city_tier": "Metro",
                "fixed_rent": 0,
                "fixed_emi": 0,
                "biggest_category": "",
                "primary_goal": "",
            },
        }

    try:
        check = db.table("users").select("*").eq("email", req.email).execute()
        if check.data:
            user = check.data[0]
            if user["user_id"] != req.user_id:
                old_user_id = user["user_id"]
                try:
                    temp_email = f"obsolete_{old_user_id}@{req.email}"
                    db.table("users").update({"email": temp_email}).eq("user_id", old_user_id).execute()
                    db.table("users").insert({
                        "user_id": req.user_id,
                        "full_name": req.full_name,
                        "email": req.email,
                    }).execute()
                    db.table("user_profiles").update({"user_id": req.user_id}).eq("user_id", old_user_id).execute()
                    db.table("accounts").update({"user_id": req.user_id}).eq("user_id", old_user_id).execute()
                    db.table("transactions").update({"user_id": req.user_id}).eq("user_id", old_user_id).execute()
                    db.table("users").delete().eq("user_id", old_user_id).execute()
                except Exception as sync_err:
                    print(f"Failed self-healing user_id update: {sync_err}")

            user_profile = ensure_user_with_profile(req.user_id, req.email, req.full_name)
            return {"success": True, "message": "OAuth login successful", "user": user_profile}

        user_profile = ensure_user_with_profile(req.user_id, req.email, req.full_name)
        return {"success": True, "message": "OAuth registration successful", "user": user_profile}
    except Exception as e:
        print(f"Error in oauth-login: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard-summary")
async def get_dashboard_summary(
    period: str = "1m",
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        from app.utils.analysis_period import normalize_period

        period_key = normalize_period(period)
        accounts = fetch_user_accounts(user_id)

        transactions: list = []
        tx_select = (
            "transaction_id, amount, transaction_type, transaction_date, "
            "merchant_name, description, is_recurring, recurrence_period, recurrence_skips, "
            "category_id, account_id, categories(main_category, sub_category)"
        )
        page_size = 1000
        offset = 0
        while True:
            trans_response = (
                supabase.table("transactions")
                .select(tx_select)
                .eq("user_id", user_id)
                .order("transaction_date")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = trans_response.data or []
            if not batch:
                break
            transactions.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size

        accounts_dict = {acc["account_id"]: acc for acc in accounts}
        recent_rows = []
        for tx in reversed(transactions):
            tx_copy = dict(tx)
            acc_id = tx_copy.get("account_id")
            tx_copy["accounts"] = {"account_name": accounts_dict[acc_id].get("account_name")} if acc_id and acc_id in accounts_dict else None
            recent_rows.append(tx_copy)
            if len(recent_rows) >= 8:
                break

        budget_res = (
            supabase.table("budgets")
            .select("*, categories(main_category, sub_category)")
            .eq("user_id", user_id)
            .execute()
        )

        prof_res = (
            supabase.table("user_profiles")
            .select("income, fixed_rent, fixed_emi")
            .eq("user_id", user_id)
            .execute()
        )
        profile_income = 0.0
        profile_fixed_rent = 0.0
        profile_fixed_emi = 0.0
        if prof_res.data:
            profile_income = float(prof_res.data[0].get("income") or 0.0)
            profile_fixed_rent = float(prof_res.data[0].get("fixed_rent") or 0.0)
            profile_fixed_emi = float(prof_res.data[0].get("fixed_emi") or 0.0)

        # Near-cash assets that extend the emergency runway — must be valued identically to the
        # /financial-health-insights endpoint so the hero score matches the AI analysis.
        from app.graph.tools.goal_planner_tool import (
            _fetch_fixed_deposits,
            _fetch_investment_holdings,
            _liquid_fund_value,
        )

        liquid_funds_value = _liquid_fund_value(_fetch_investment_holdings(user_id))
        fixed_deposits_value = round(
            sum(float(fd.get("break_value") or 0) for fd in _fetch_fixed_deposits(user_id)), 2
        )

        return build_dashboard_payload(
            user_id=user_id.strip(),
            accounts=accounts,
            transactions=transactions,
            recent_rows=recent_rows,
            budgets=budget_res.data or [],
            profile_income=profile_income,
            profile_fixed_rent=profile_fixed_rent,
            profile_fixed_emi=profile_fixed_emi,
            liquid_funds_value=liquid_funds_value,
            fixed_deposits_value=fixed_deposits_value,
            period=period_key,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in dashboard-summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _build_spending_analytics_response(
    user_id: str,
    *,
    period: str,
    account_id: str | None,
    category_id: str | None,
    merchant: str | None,
) -> dict:
    """Shared spending-analytics payload builder (category trends, merchants, behavior)."""
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        import time

        from app.services.analytics_service import build_spending_analytics_payload
        from app.utils.analysis_period import normalize_period
        from app.utils.tab_logging import mask_user_id, tab_error, tab_info

        period_key = normalize_period(period)
        tab_info(
            "analytics",
            "spending-analytics start user=%s period=%s filters=%s",
            mask_user_id(user_id),
            period_key,
            {"account_id": account_id, "category_id": category_id, "merchant": merchant},
        )
        started = time.perf_counter()

        trans_response = (
            supabase.table("transactions")
            .select(
                "transaction_id, amount, transaction_type, transaction_date, "
                "merchant_name, description, account_id, category_id, "
                "categories(main_category, sub_category)"
            )
            .eq("user_id", user_id)
            .order("transaction_date")
            .execute()
        )
        transactions = trans_response.data or []
        payload = build_spending_analytics_payload(
            transactions,
            period=period_key,
            account_id=account_id,
            category_id=category_id,
            merchant=merchant,
        )
        tab_info(
            "analytics",
            "spending-analytics done user=%s elapsed_ms=%.0f txns=%d total_spend=%s categories=%d",
            mask_user_id(user_id),
            (time.perf_counter() - started) * 1000,
            len(transactions),
            payload.get("total_spend"),
            len(payload.get("category_trends") or []),
        )
        return payload
    except Exception as e:
        from app.utils.tab_logging import mask_user_id, tab_error

        tab_error("analytics", "spending-analytics failed user=%s: %s", mask_user_id(user_id), e)
        print(f"Error in spending-analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spending-analytics")
async def get_spending_analytics(
    period: str = "3m",
    account_id: str | None = None,
    category_id: str | None = None,
    merchant: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Spending analytics for the Analytics/Forecasting view (category trends, merchants, behaviour)."""
    return _build_spending_analytics_response(
        current_user["user_id"],
        period=period,
        account_id=account_id,
        category_id=category_id,
        merchant=merchant,
    )


@router.get("/financial-insights")
async def get_financial_insights(
    user_id: str,
    period: str = "3m",
    account_id: str | None = None,
    category_id: str | None = None,
    merchant: str | None = None,
    llm: str | None = None,
):
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        import asyncio
        import time

        from app.services.analytics_service import build_spending_analytics_payload
        from app.services.financial_insights_service import build_financial_insights_payload
        from app.services.prophet.inference import get_next_month_prediction
        from app.utils.analysis_period import normalize_period
        from app.utils.tab_logging import mask_user_id, tab_error, tab_info

        include_llm = (llm or "").strip().lower() in ("1", "true", "yes", "on")
        period_key = normalize_period(period)
        tab_info(
            "analytics",
            "financial-insights start user=%s period=%s llm=%s filters=%s",
            mask_user_id(user_id),
            period_key,
            include_llm,
            {"account_id": account_id, "category_id": category_id, "merchant": merchant},
        )
        started = time.perf_counter()

        trans_response = (
            supabase.table("transactions")
            .select(
                "transaction_id, amount, transaction_type, transaction_date, "
                "merchant_name, description, account_id, category_id, "
                "categories(main_category, sub_category)"
            )
            .eq("user_id", user_id)
            .order("transaction_date")
            .execute()
        )
        transactions = trans_response.data or []

        analytics = build_spending_analytics_payload(
            transactions,
            period=period_key,
            account_id=account_id,
            category_id=category_id,
            merchant=merchant,
        )

        forecast_meta = None
        try:
            forecast_meta = get_next_month_prediction(user_id.strip(), transactions)
        except Exception:
            forecast_meta = None

        prof_res = (
            supabase.table("user_profiles")
            .select("income, fixed_rent, fixed_emi, primary_goal, biggest_category")
            .eq("user_id", user_id)
            .execute()
        )
        profile = prof_res.data[0] if prof_res.data else {}

        build_kwargs = dict(
            analytics=analytics,
            predicted_next_month=(forecast_meta or {}).get("predicted_next_month"),
            predicted_month_label=(forecast_meta or {}).get("predicted_month_label"),
            profile=profile,
            include_llm=include_llm,
        )
        if include_llm:
            payload = await asyncio.to_thread(build_financial_insights_payload, **build_kwargs)
        else:
            payload = build_financial_insights_payload(**build_kwargs)
        tab_info(
            "analytics",
            "financial-insights done user=%s elapsed_ms=%.0f source=%s llm_status=%s recommendations=%d",
            mask_user_id(user_id),
            (time.perf_counter() - started) * 1000,
            payload.get("source"),
            payload.get("llm_status"),
            len(payload.get("recommendations") or []),
        )
        return payload
    except Exception as e:
        from app.utils.tab_logging import mask_user_id, tab_error

        tab_error("analytics", "financial-insights failed user=%s: %s", mask_user_id(user_id), e)
        print(f"Error in financial-insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/financial-health-insights")
async def get_financial_health_insights(user_id: str, llm: str | None = None):
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        import asyncio
        import time

        from app.services.dashboard_metrics_service import compute_overall_financial_health
        from app.services.financial_health_insights_service import (
            build_financial_health_insights_payload,
        )
        from app.utils.tab_logging import mask_user_id, tab_error, tab_info

        include_llm = (llm or "").strip().lower() in ("1", "true", "yes", "on")
        tab_info(
            "dashboard",
            "financial-health-insights start user=%s llm=%s",
            mask_user_id(user_id),
            include_llm,
        )
        started = time.perf_counter()

        accounts = fetch_user_accounts(user_id)
        trans_response = (
            supabase.table("transactions")
            .select(
                "transaction_id, amount, transaction_type, transaction_date, "
                "merchant_name, description, is_recurring, recurrence_period, recurrence_skips, "
                "category_id, categories(main_category, sub_category)"
            )
            .eq("user_id", user_id)
            .order("transaction_date")
            .execute()
        )
        transactions = trans_response.data or []

        prof_res = (
            supabase.table("user_profiles")
            .select("income, fixed_rent, fixed_emi, primary_goal")
            .eq("user_id", user_id)
            .execute()
        )
        profile = prof_res.data[0] if prof_res.data else {}

        # Near-cash assets that extend the emergency runway, valued consistently with the goal
        # planner: liquid/debt mutual funds (redeemable in ~1 day) and FDs at their accessible-now
        # value (break value net of penalty; matured FDs at full value).
        from app.graph.tools.goal_planner_tool import (
            _fetch_fixed_deposits,
            _fetch_investment_holdings,
            _liquid_fund_value,
        )

        liquid_funds_value = _liquid_fund_value(_fetch_investment_holdings(user_id))
        fixed_deposits_value = round(
            sum(float(fd.get("break_value") or 0) for fd in _fetch_fixed_deposits(user_id)), 2
        )

        health = compute_overall_financial_health(
            accounts=accounts,
            transactions=transactions,
            profile_income=float(profile.get("income") or 0),
            profile_fixed_rent=float(profile.get("fixed_rent") or 0),
            profile_fixed_emi=float(profile.get("fixed_emi") or 0),
            liquid_funds_value=liquid_funds_value,
            fixed_deposits_value=fixed_deposits_value,
            user_id=user_id,
        )

        build_kwargs = dict(health=health, profile=profile, include_llm=include_llm)
        if include_llm:
            payload = await asyncio.to_thread(
                build_financial_health_insights_payload, **build_kwargs
            )
        else:
            payload = build_financial_health_insights_payload(**build_kwargs)
        tab_info(
            "dashboard",
            "financial-health-insights done user=%s elapsed_ms=%.0f source=%s llm_status=%s score=%s",
            mask_user_id(user_id),
            (time.perf_counter() - started) * 1000,
            payload.get("source"),
            payload.get("llm_status"),
            payload.get("score"),
        )
        return payload
    except Exception as e:
        from app.utils.tab_logging import mask_user_id, tab_error

        tab_error(
            "dashboard",
            "financial-health-insights failed user=%s: %s",
            mask_user_id(user_id),
            e,
        )
        print(f"Error in financial-health-insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TransactionCreate(BaseModel):
    user_id: Optional[str] = None  # ignored — identity comes from JWT
    account_id: str
    amount: float
    transaction_type: str
    merchant_name: str
    description: str
    main_category: str
    sub_category: str = "General"
    transaction_date: str
    is_recurring: Optional[bool] = False
    recurrence_period: Optional[str] = None
    recurrence_skips: Optional[int] = 0

@router.post("/transactions")
async def create_transaction(
    req: TransactionCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        result = create_transaction_record(
            user_id=current_user["user_id"],
            account_id=req.account_id,
            amount=req.amount,
            transaction_type=req.transaction_type,
            merchant_name=req.merchant_name,
            description=req.description,
            main_category=req.main_category,
            sub_category=req.sub_category,
            transaction_date=req.transaction_date,
            is_recurring=req.is_recurring or False,
            recurrence_period=req.recurrence_period,
            recurrence_skips=req.recurrence_skips or 0,
        )
        return {
            "success": True,
            "message": "Transaction added successfully",
            "new_balance": result["new_balance"],
            "account_id": result["account_id"],
            "transaction_id": result["transaction"].get("transaction_id"),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/transactions")
async def get_transactions(
    start_date: str = None,
    end_date: str = None,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    try:
        # Single query with joins (avoids N+1 / extra mapping queries)
        query = (
            supabase.table("transactions")
            .select(
                "transaction_id,transaction_date,amount,transaction_type,merchant_name,description,"
                "account_id,category_id,is_recurring,recurrence_period,recurrence_skips,"
                "running_balance,"
                "categories(main_category,sub_category),"
                "accounts(account_name)"
            )
            .eq("user_id", user_id)
        )

        if start_date:
            query = query.gte("transaction_date", start_date)
        if end_date:
            query = query.lte("transaction_date", end_date)

        trans_res = query.order("transaction_date", desc=True).execute()
        rows = trans_res.data or []

        formatted = []
        for row in rows:
            categories = row.get("categories") or {}
            accounts = row.get("accounts") or {}
            formatted.append(
                {
                    "id": row["transaction_id"],
                    "date": row["transaction_date"],
                    "merchant": row.get("merchant_name") or row.get("description") or "Unknown",
                    "category": normalize_category_name(categories.get("main_category")),
                    "subCategory": categories.get("sub_category") or "General",
                    "amount": float(row.get("amount") or 0),
                    "account": accounts.get("account_name") or "Unknown Account",
                    "account_id": row.get("account_id"),
                    "category_id": row.get("category_id"),
                    "type": row.get("transaction_type"),
                    "notes": row.get("description"),
                    "runningBalance": float(row["running_balance"])
                    if row.get("running_balance") is not None
                    else None,
                    "is_recurring": bool(row.get("is_recurring")),
                    "recurrence_period": row.get("recurrence_period"),
                    "recurrence_skips": int(row.get("recurrence_skips") or 0),
                }
            )
        return {"success": True, "data": formatted}
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upcoming-payments")
async def get_upcoming_payments(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        from datetime import date, timedelta
        
        # Query recurring transactions
        res = (
            supabase.table("transactions")
            .select(
                "transaction_id,transaction_date,amount,transaction_type,merchant_name,description,"
                "account_id,category_id,is_recurring,recurrence_period,recurrence_skips,"
                "categories(main_category,sub_category),"
                "accounts(account_name)"
            )
            .eq("user_id", user_id)
            .eq("is_recurring", True)
            .execute()
        )
        
        rows = res.data or []
        upcoming = []
        today = date.today()
        
        def add_months(sourcedate: date, months: int) -> date:
            month = sourcedate.month - 1 + months
            year = sourcedate.year + month // 12
            month = month % 12 + 1
            day = min(sourcedate.day, [31,
                29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month-1])
            return date(year, month, day)

        def add_years(sourcedate: date, years: int) -> date:
            try:
                return sourcedate.replace(year=sourcedate.year + years)
            except ValueError:
                return sourcedate.replace(year=sourcedate.year + years, day=28)

        for row in rows:
            base_date_str = row.get("transaction_date")
            period = row.get("recurrence_period")
            skips = int(row.get("recurrence_skips") or 0)
            
            if not base_date_str or not period:
                continue
                
            try:
                base_date = datetime.strptime(base_date_str, "%Y-%m-%d").date()
            except Exception:
                continue
                
            step = skips + 1
            current = base_date
            
            # Advance past dates on or before today so the next charge is in the future.
            iterations = 0
            while current <= today and iterations < 100:
                iterations += 1
                if period == "daily":
                    current += timedelta(days=step)
                elif period == "weekly":
                    current += timedelta(weeks=step)
                elif period == "monthly":
                    current = add_months(current, step)
                elif period == "yearly":
                    current = add_years(current, step)
                else:
                    break

            categories_info = row.get("categories") or {}
            accounts_info = row.get("accounts") or {}
            
            upcoming.append({
                "id": row["transaction_id"],
                "merchant": row.get("merchant_name") or row.get("description") or "Unknown",
                "category": normalize_category_name(categories_info.get("main_category")),
                "subCategory": categories_info.get("sub_category") or "General",
                "amount": float(row.get("amount") or 0),
                "account": accounts_info.get("account_name") or "Unknown Account",
                "account_id": row.get("account_id"),
                "type": row.get("transaction_type"),
                "notes": row.get("description"),
                "next_date": current.strftime("%Y-%m-%d"),
                "recurrence_period": period,
                "recurrence_skips": skips
            })
            
        upcoming.sort(key=lambda x: x["next_date"])
        return {"success": True, "data": upcoming}
    except Exception as e:
        print(f"Error fetching upcoming payments: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/transactions/{trans_id}")
async def update_transaction(
    trans_id: str,
    req: TransactionCreate,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(_fetch_owner("transactions", "transaction_id", trans_id), current_user)
    try:
        result = update_transaction_record(
            transaction_id=trans_id,
            user_id=current_user["user_id"],
            account_id=req.account_id,
            amount=req.amount,
            transaction_type=req.transaction_type,
            merchant_name=req.merchant_name,
            description=req.description,
            main_category=req.main_category,
            sub_category=req.sub_category,
            transaction_date=req.transaction_date,
            is_recurring=req.is_recurring or False,
            recurrence_period=req.recurrence_period,
            recurrence_skips=req.recurrence_skips or 0,
        )
        return {
            "success": True,
            "message": "Transaction updated successfully",
            "account_id": result["account_id"],
            "new_balance": result["new_balance"],
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.delete("/transactions/{trans_id}")
async def delete_transaction(
    trans_id: str,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(_fetch_owner("transactions", "transaction_id", trans_id), current_user)
    try:
        supabase.table("transactions").delete().eq("transaction_id", trans_id).execute()
        return {"success": True, "message": "Transaction deleted successfully"}
    except Exception as e:
        print(f"Error deleting transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class AccountCreate(BaseModel):
    user_id: Optional[str] = None  # ignored — identity comes from JWT
    account_name: str
    account_type: str
    current_balance: float = 0.0
    credit_limit: float | None = None
    bank_name: str | None = None
    account_holder: str | None = None
    account_number: str | None = None
    ifsc: str | None = None

@router.post("/accounts")
async def create_account(
    req: AccountCreate,
    current_user: dict = Depends(get_current_user),
):
    uid = current_user["user_id"]
    try:
        row = {
            "user_id": uid,
            "account_name": req.account_name,
            "account_type": req.account_type,
            "current_balance": req.current_balance,
        }
        if req.credit_limit is not None and req.account_type == "credit_card":
            row["credit_limit"] = req.credit_limit
        if req.bank_name is not None:
            row["bank_name"] = req.bank_name
        if req.account_holder is not None:
            row["account_holder"] = req.account_holder
        if req.account_number is not None:
            row["account_number"] = req.account_number
        if req.ifsc is not None:
            row["ifsc"] = req.ifsc

        created = insert_account(row)
        return {"success": True, "message": "Account created successfully", "data": created}
    except Exception as e:
        print(f"Error creating account: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.put("/accounts/{account_id}")
async def update_account(
    account_id: str,
    req: AccountCreate,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(_fetch_owner("accounts", "account_id", account_id), current_user)
    try:
        row = {
            "account_name": req.account_name,
            "account_type": req.account_type,
            "current_balance": req.current_balance,
            "bank_name": req.bank_name,
            "account_holder": req.account_holder,
            "account_number": req.account_number,
            "ifsc": req.ifsc
        }
        if req.credit_limit is not None and req.account_type == "credit_card":
            row["credit_limit"] = req.credit_limit
        else:
            row["credit_limit"] = None

        res = supabase.table("accounts").update(row).eq("account_id", account_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Account not found or update failed")
        return {"success": True, "message": "Account updated successfully", "data": res.data[0]}
    except Exception as e:
        print(f"Error updating account: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts")
async def get_accounts(current_user: dict = Depends(get_current_user)):
    uid = current_user["user_id"].strip()
    return {"success": True, "data": fetch_user_accounts(uid)}

@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(_fetch_owner("accounts", "account_id", account_id), current_user)
    try:
        # Cascade delete transactions associated with this account first
        supabase.table("transactions").delete().eq("account_id", account_id).execute()
        supabase.table("accounts").delete().eq("account_id", account_id).execute()
        return {"success": True, "message": "Account and associated transactions deleted successfully"}
    except Exception as e:
        print(f"Error deleting account: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class BudgetCreate(BaseModel):
    user_id: Optional[str] = None  # ignored — identity comes from JWT
    category_name: str
    budget_name: str
    amount: float
    period: str = "monthly"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    alert_threshold: float = 80.0

class GoalCreate(BaseModel):
    user_id: Optional[str] = None  # ignored — identity comes from JWT
    goal_name: str
    description: Optional[str] = ""
    target_amount: float
    current_amount: float = 0.0
    target_date: str
    status: str = "active"

@router.get("/budget-goals-summary")
async def get_budget_goals_summary(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        uid = user_id.strip()
        budget_res = (
            supabase.table("budgets")
            .select("*, categories(main_category, sub_category)")
            .eq("user_id", uid)
            .execute()
        )

        # Only fetch the minimum transaction window needed for:
        # - budget utilization (from earliest active budget start)
        # - trajectory (needs current + previous month)
        from datetime import date

        today = date.today()
        first_of_this_month = today.replace(day=1).isoformat()
        if today.month == 1:
            first_of_prev_month = date(today.year - 1, 12, 1).isoformat()
        else:
            first_of_prev_month = date(today.year, today.month - 1, 1).isoformat()

        budgets = budget_res.data or []
        budget_starts = [str(b.get("start_date") or "") for b in budgets if b.get("start_date")]
        min_budget_start = min(budget_starts) if budget_starts else first_of_this_month
        min_tx_date = min(min_budget_start, first_of_prev_month)

        trans_response = (
            supabase.table("transactions")
            .select(
                "transaction_id, amount, transaction_type, transaction_date, category_id, "
                "categories(main_category, sub_category)"
            )
            .eq("user_id", uid)
            .gte("transaction_date", min_tx_date)
            .order("transaction_date")
            .execute()
        )
        goal_tx_select = "amount, transaction_type"
        goal_transactions: list = []
        page_size = 1000
        offset = 0
        while True:
            goal_tx_res = (
                supabase.table("transactions")
                .select(goal_tx_select)
                .eq("user_id", uid)
                .order("transaction_date")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = goal_tx_res.data or []
            if not batch:
                break
            goal_transactions.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size

        goals_res = (
            supabase.table("goals").select("*").eq("user_id", uid).execute()
        )
        return build_budget_goals_payload(
            budgets=budgets,
            transactions=trans_response.data or [],
            goals=goals_res.data or [],
            goal_transactions=goal_transactions,
        )
    except Exception as e:
        print(f"Error fetching budget-goals summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/budgets")
async def get_budgets(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        res = supabase.table("budgets").select("*, categories(main_category, sub_category)").eq("user_id", user_id).execute()
        formatted = []
        for b in res.data:
            cat = b.get("categories", {}) or {}
            formatted.append({
                "id": b["budget_id"],
                "userId": b["user_id"],
                "categoryId": b["category_id"],
                "categoryName": cat.get("main_category", "Others"),
                "budgetName": b["budget_name"],
                "amount": float(b["amount"]) if b["amount"] is not None else 0.0,
                "period": b["period"],
                "startDate": b["start_date"],
                "endDate": b["end_date"],
                "alertThreshold": float(b["alert_threshold"]) if b["alert_threshold"] is not None else 80.0
            })
        return {"success": True, "data": formatted}
    except Exception as e:
        print(f"Error fetching budgets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/budgets")
async def create_budget(
    req: BudgetCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        cat_res = supabase.table("categories")\
            .select("category_id")\
            .ilike("main_category", req.category_name)\
            .ilike("sub_category", "General")\
            .execute()
        
        if not cat_res.data:
            cat_res = supabase.table("categories")\
                .select("category_id")\
                .ilike("main_category", "Others")\
                .ilike("sub_category", "General")\
                .execute()
                
        category_id = cat_res.data[0]["category_id"] if cat_res.data else None

        start_date, end_date = resolve_budget_period_dates(
            req.period,
            start_date=req.start_date,
            end_date=req.end_date,
        )

        insert_data = {
            "user_id": current_user["user_id"],
            "category_id": category_id,
            "budget_name": req.budget_name,
            "amount": req.amount,
            "period": req.period,
            "start_date": start_date,
            "end_date": end_date,
            "alert_threshold": req.alert_threshold
        }
        
        res = supabase.table("budgets").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create budget")
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        print(f"Error creating budget: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/budgets/{budget_id}")
async def update_budget(
    budget_id: str,
    req: BudgetCreate,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(_fetch_owner("budgets", "budget_id", budget_id), current_user)
    try:
        cat_res = supabase.table("categories")\
            .select("category_id")\
            .ilike("main_category", req.category_name)\
            .ilike("sub_category", "General")\
            .execute()
            
        category_id = cat_res.data[0]["category_id"] if cat_res.data else None

        start_date, end_date = resolve_budget_period_dates(
            req.period,
            start_date=req.start_date,
            end_date=req.end_date,
        )

        update_data = {
            "budget_name": req.budget_name,
            "amount": req.amount,
            "period": req.period,
            "start_date": start_date,
            "end_date": end_date,
            "alert_threshold": req.alert_threshold
        }
        if category_id:
            update_data["category_id"] = category_id
            
        res = supabase.table("budgets").update(update_data).eq("budget_id", budget_id).execute()
        return {"success": True, "data": res.data[0] if res.data else None}
    except Exception as e:
        print(f"Error updating budget: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/budgets/{budget_id}")
async def delete_budget(
    budget_id: str,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(_fetch_owner("budgets", "budget_id", budget_id), current_user)
    try:
        supabase.table("budgets").delete().eq("budget_id", budget_id).execute()
        return {"success": True, "message": "Budget deleted successfully"}
    except Exception as e:
        print(f"Error deleting budget: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/goals")
async def get_goals(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        res = supabase.table("goals").select("*").eq("user_id", user_id).execute()
        formatted = []
        for g in res.data:
            formatted.append({
                "id": g["goal_id"],
                "userId": g["user_id"],
                "label": g["goal_name"],
                "sub": g["description"] or "",
                "target": float(g["target_amount"]) if g["target_amount"] is not None else 0.0,
                "current": float(g["current_amount"]) if g["current_amount"] is not None else 0.0,
                "date": g["target_date"],
                "status": g["status"],
                "icon": "Target",
                "color": "bg-primary"
            })
        return {"success": True, "data": formatted}
    except Exception as e:
        print(f"Error fetching goals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/goals")
async def create_goal(
    req: GoalCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        uid = current_user["user_id"]
        current_amount = float(req.current_amount or 0)
        if current_amount <= 0:
            tx_res = (
                supabase.table("transactions")
                .select("amount, transaction_type")
                .eq("user_id", uid)
                .execute()
            )
            current_amount = compute_net_savings(tx_res.data or [])

        insert_data = {
            "user_id": uid,
            "goal_name": req.goal_name,
            "description": req.description,
            "target_amount": req.target_amount,
            "current_amount": current_amount,
            "target_date": req.target_date,
            "status": req.status
        }
        res = supabase.table("goals").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create goal")
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        print(f"Error creating goal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/goals/{goal_id}")
async def update_goal(
    goal_id: str,
    req: GoalCreate,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(_fetch_owner("goals", "goal_id", goal_id), current_user)
    try:
        update_data = {
            "goal_name": req.goal_name,
            "description": req.description,
            "target_amount": req.target_amount,
            "current_amount": req.current_amount,
            "target_date": req.target_date,
            "status": req.status
        }
        res = supabase.table("goals").update(update_data).eq("goal_id", goal_id).execute()
        return {"success": True, "data": res.data[0] if res.data else None}
    except Exception as e:
        print(f"Error updating goal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: str,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(_fetch_owner("goals", "goal_id", goal_id), current_user)
    try:
        supabase.table("goals").delete().eq("goal_id", goal_id).execute()
        return {"success": True, "message": "Goal deleted successfully"}
    except Exception as e:
        print(f"Error deleting goal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/categories")
async def get_categories():
    try:
        res = supabase.table("categories").select("main_category").execute()
        # Extract unique main categories, normalize, and sort
        unique_cats = sorted(list(set(normalize_category_name(c["main_category"]) for c in res.data if c.get("main_category"))))
        return {"success": True, "data": unique_cats}
    except Exception as e:
        print(f"Error fetching categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/reports")
async def get_reports():
    return {"success": True, "message": "Reports endpoint ready"}

# ============================================================
# MUTUAL FUND / INVESTMENT TRACKER ENDPOINTS
# ============================================================

from pydantic import BaseModel

class InvestmentCreate(BaseModel):
    user_id: Optional[str] = None  # ignored — identity comes from JWT
    scheme_code: str
    scheme_name: str
    transaction_date: str  # YYYY-MM-DD
    quantity: float
    purchase_nav: float

@router.get("/investments/search")
async def search_mutual_funds(q: str):
    import urllib.request
    import urllib.parse
    import json
    try:
        encoded_q = urllib.parse.quote(q)
        url = f"https://api.mfapi.in/mf/search?q={encoded_q}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
        
        # Smart ranking logic: Prioritize words starting with q (e.g. Bandhan for 'band')
        q_lower = q.lower().strip()
        def get_rank(item):
            name = item.get("schemeName", "").lower()
            if name.startswith(q_lower):
                return 0
            words = name.split()
            if any(w.startswith(q_lower) for w in words):
                return 1
            if q_lower in name:
                return 2
            return 3

        sorted_data = sorted(data, key=get_rank)
        
        results = []
        for item in sorted_data[:15]:  # Limit to top 15 best-matched results
            results.append({
                "schemeCode": str(item.get("schemeCode")),
                "schemeName": item.get("schemeName")
            })
        return {"success": True, "data": results}
    except Exception as e:
        print(f"Error searching mutual funds: {e}")
        return {"success": False, "detail": str(e)}

@router.get("/investments/nav")
async def get_historical_nav(scheme_code: str, date: str):
    import urllib.request
    import json
    from datetime import datetime, timedelta
    try:
        url = f"https://api.mfapi.in/mf/{scheme_code}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode())
        
        nav_entries = res_data.get("data", [])
        if not nav_entries:
            return {"success": False, "detail": "No NAV data found"}
            
        target_date = datetime.strptime(date, "%Y-%m-%d")
        
        # Build date-to-nav map
        date_to_nav = {}
        for entry in nav_entries:
            try:
                date_str = entry["date"]
                parts = date_str.split("-")
                year_part = parts[2]
                fmt = "%d-%m-%y" if len(year_part) == 2 else "%d-%m-%Y"
                d = datetime.strptime(date_str, fmt)
                date_to_nav[d.date()] = float(entry["nav"])
            except Exception:
                continue
                
        # Find exact or closest preceding date
        found_nav = None
        for i in range(10):
            check_date = (target_date - timedelta(days=i)).date()
            if check_date in date_to_nav:
                found_nav = date_to_nav[check_date]
                break
                
        if found_nav is None:
            # Fallback to the oldest available NAV or latest
            found_nav = float(nav_entries[0]["nav"])
            
        return {"success": True, "nav": found_nav}
    except Exception as e:
        print(f"Error fetching historical NAV: {e}")
        return {"success": False, "detail": str(e)}

@router.post("/investments")
async def create_investment(
    req: InvestmentCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        insert_data = {
            "user_id": current_user["user_id"],
            "scheme_code": req.scheme_code,
            "scheme_name": req.scheme_name,
            "transaction_date": req.transaction_date,
            "quantity": req.quantity,
            "purchase_nav": req.purchase_nav
        }
        res = supabase.table("investments").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to log investment")
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        print(f"Error creating investment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/investments/{investment_id}")
async def delete_investment(
    investment_id: str,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(_fetch_owner("investments", "investment_id", investment_id), current_user)
    try:
        supabase.table("investments").delete().eq("investment_id", investment_id).execute()
        return {"success": True, "message": "Holding transaction deleted successfully"}
    except Exception as e:
        print(f"Error deleting investment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/investments")
async def get_user_investments(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    import urllib.request
    import json
    from datetime import datetime, timedelta
    try:
        # 1. Fetch user logged investments
        res = supabase.table("investments").select("*").eq("user_id", user_id).execute()
        db_investments = res.data or []
        
        if not db_investments:
            return {
                "success": True,
                "holdings": [],
                "summary": {
                    "total_invested": 0.0,
                    "current_value": 0.0,
                    "total_gain": 0.0,
                    "total_gain_percentage": 0.0,
                    "portfolio_cagr": "0.0%"
                },
                "chart_data": [],
                "raw_transactions": []
            }
            
        # 2. Get unique scheme codes to batch fetch live/historical NAV
        unique_schemes = list(set(inv["scheme_code"] for inv in db_investments))
        scheme_data_cache = {}
        
        for code in unique_schemes:
            try:
                url = f"https://api.mfapi.in/mf/{code}"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=8) as response:
                    parsed = json.loads(response.read().decode())
                    scheme_data_cache[code] = parsed
            except Exception as e:
                print(f"Error fetching cache for {code}: {e}")
                
        # 3. Aggregate holdings
        holdings_map = {}
        total_invested_val = 0.0
        total_current_val = 0.0
        
        for inv in db_investments:
            code = inv["scheme_code"]
            qty = float(inv["quantity"])
            purch_nav = float(inv["purchase_nav"])
            name = inv["scheme_name"]
            
            # Fetch current live NAV
            current_nav = 0.0
            day_change = 0.0
            if code in scheme_data_cache:
                nav_list = scheme_data_cache[code].get("data", [])
                if nav_list:
                    current_nav = float(nav_list[0]["nav"])
                    if len(nav_list) > 1:
                        prev_nav = float(nav_list[1]["nav"])
                        day_change = current_nav - prev_nav
            
            if code not in holdings_map:
                holdings_map[code] = {
                    "ticker": code,
                    "name": name,
                    "qty": 0.0,
                    "invested": 0.0,
                    "avg_nav": 0.0,
                    "current_nav": current_nav,
                    "current_value": 0.0,
                    "gain": 0.0,
                    "gain_percent": 0.0,
                    "day_pnl": 0.0
                }
                
            h = holdings_map[code]
            h["qty"] += qty
            h["invested"] += (qty * purch_nav)
            h["day_pnl"] += (qty * day_change)
            
        # Complete holding metrics calculations
        holdings = []
        for code, h in holdings_map.items():
            if h["qty"] > 0:
                h["avg_nav"] = h["invested"] / h["qty"]
                # If the live NAV couldn't be fetched (e.g. a just-added scheme or a transient
                # mfapi miss), fall back to the average purchase NAV so the holding shows a neutral
                # P&L — NOT a spurious total loss (current_value would otherwise be 0).
                if h["current_nav"] <= 0:
                    h["current_nav"] = h["avg_nav"]
                h["current_value"] = h["qty"] * h["current_nav"]
                h["gain"] = h["current_value"] - h["invested"]
                h["gain_percent"] = (h["gain"] / h["invested"] * 100) if h["invested"] > 0 else 0
                
                total_invested_val += h["invested"]
                total_current_val += h["current_value"]
                holdings.append(h)
                
        # Calculate portfolio shares
        for h in holdings:
            h["portfolio_share"] = (h["current_value"] / total_current_val * 100) if total_current_val > 0 else 0
            
        total_gain = total_current_val - total_invested_val
        total_gain_percentage = (total_gain / total_invested_val * 100) if total_invested_val > 0 else 0
        
        # 4. Generate high-fidelity historical data for line chart
        # Find earliest investment date
        earliest_date = datetime.now().date()
        for inv in db_investments:
            d_obj = datetime.strptime(inv["transaction_date"], "%Y-%m-%d").date()
            if d_obj < earliest_date:
                earliest_date = d_obj
                
        # Prep date-to-nav maps for all cached schemes
        scheme_history_maps = {}
        for code, s_data in scheme_data_cache.items():
            h_map = {}
            for entry in s_data.get("data", []):
                try:
                    parts = entry["date"].split("-")
                    fmt = "%d-%m-%y" if len(parts[2]) == 2 else "%d-%m-%Y"
                    d = datetime.strptime(entry["date"], fmt).date()
                    h_map[d] = float(entry["nav"])
                except Exception:
                    continue
            scheme_history_maps[code] = h_map
            
        # Build timeline from earliest_date to today
        timeline = []
        curr_ptr = earliest_date
        today = datetime.now().date()
        
        # Decide step size dynamically (e.g. daily if short time, weekly if > 6 months)
        total_days = (today - earliest_date).days
        step_days = 7 if total_days > 90 else 1
        if total_days == 0:
            total_days = 1
            
        while curr_ptr <= today:
            timeline.append(curr_ptr)
            curr_ptr += timedelta(days=step_days)
        if today not in timeline:
            timeline.append(today)
            
        chart_data = []
        for t_date in timeline:
            t_invested = 0.0
            t_current = 0.0
            
            for inv in db_investments:
                inv_date = datetime.strptime(inv["transaction_date"], "%Y-%m-%d").date()
                if inv_date <= t_date:
                    qty = float(inv["quantity"])
                    purch_nav = float(inv["purchase_nav"])
                    code = inv["scheme_code"]
                    
                    t_invested += (qty * purch_nav)
                    
                    # Find NAV on t_date
                    nav_map = scheme_history_maps.get(code, {})
                    c_nav = 0.0
                    for offset in range(10):
                        check_d = t_date - timedelta(days=offset)
                        if check_d in nav_map:
                            c_nav = nav_map[check_d]
                            break
                    if c_nav == 0.0 and nav_map:
                        # Fallback to nearest date in history
                        c_nav = float(scheme_data_cache[code]["data"][0]["nav"])
                        
                    t_current += (qty * c_nav)
            
            # Format date for frontend
            chart_data.append({
                "name": t_date.strftime("%b %y").upper(),
                "dateStr": t_date.strftime("%Y-%m-%d"),
                "invested": round(t_invested, 2),
                "current": round(t_current, 2)
            })
            
        # Simple CAGR calculation over portfolio life
        years = max(total_days / 365.0, 0.01)
        cagr_val = 0.0
        if total_invested_val > 0 and total_current_val > 0:
            cagr_val = ((total_current_val / total_invested_val) ** (1 / years) - 1) * 100
        
        summary = {
            "total_invested": round(total_invested_val, 2),
            "current_value": round(total_current_val, 2),
            "total_gain": round(total_gain, 2),
            "total_gain_percentage": round(total_gain_percentage, 2),
            "portfolio_cagr": f"{cagr_val:.1f}%"
        }
        
        # Inject live current NAV inside raw transaction list for detail views
        enriched_transactions = []
        for inv in db_investments:
            code = inv["scheme_code"]
            c_nav = 0.0
            if code in scheme_data_cache:
                nav_list = scheme_data_cache[code].get("data", [])
                if nav_list:
                    c_nav = float(nav_list[0]["nav"])
            # Live NAV unavailable → fall back to this purchase's NAV (neutral P&L, no fake loss).
            if c_nav <= 0:
                c_nav = float(inv["purchase_nav"])

            enriched_transactions.append({
                "investment_id": inv["investment_id"],
                "user_id": inv["user_id"],
                "scheme_code": inv["scheme_code"],
                "scheme_name": inv["scheme_name"],
                "transaction_date": inv["transaction_date"],
                "quantity": float(inv["quantity"]),
                "purchase_nav": float(inv["purchase_nav"]),
                "current_nav": c_nav
            })
        
        return {
            "success": True,
            "holdings": holdings,
            "summary": summary,
            "chart_data": chart_data,
            "raw_transactions": enriched_transactions
        }
    except Exception as e:
        print(f"Error fetching user investments: {e}")
        return {"success": False, "detail": str(e)}


# ============================================================
# FIXED DEPOSIT ENDPOINTS
# ============================================================

class FixedDepositCreate(BaseModel):
    user_id: Optional[str] = None  # ignored — identity comes from JWT
    bank_name: Optional[str] = None
    label: Optional[str] = None
    principal_amount: float
    interest_rate_pct: float
    start_date: str        # YYYY-MM-DD
    maturity_date: str     # YYYY-MM-DD
    compounding_frequency: str = "quarterly"   # monthly | quarterly | half-yearly | annually | simple
    payout_type: str = "cumulative"            # cumulative | payout
    premature_penalty_pct: float = 1.0


@router.get("/fixed-deposits")
async def list_fixed_deposits(current_user: dict = Depends(get_current_user)):
    """All active FDs for the user, each enriched with current / maturity / break values."""
    user_id = current_user["user_id"]
    from app.graph.tools.goal_planner_tool import _fd_metrics
    try:
        res = (supabase.table("fixed_deposits").select("*")
               .eq("user_id", user_id).eq("is_active", True)
               .order("maturity_date").execute())
        rows = res.data or []
        out = []
        total_principal = total_current = total_maturity = 0.0
        for r in rows:
            m = _fd_metrics(r)
            total_principal += m["principal_amount"]
            total_current += m["current_value"]
            total_maturity += m["maturity_value"]
            out.append({**r, **m})
        return {
            "success": True,
            "fixed_deposits": out,
            "summary": {
                "count": len(out),
                "total_principal": round(total_principal, 2),
                "total_current_value": round(total_current, 2),
                "total_maturity_value": round(total_maturity, 2),
            },
        }
    except Exception as e:
        print(f"Error listing fixed deposits: {e}")
        return {"success": False, "detail": str(e)}


@router.post("/fixed-deposits")
async def create_fixed_deposit(
    req: FixedDepositCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        insert_data = {
            "user_id": current_user["user_id"],
            "bank_name": req.bank_name,
            "label": req.label,
            "principal_amount": req.principal_amount,
            "interest_rate_pct": req.interest_rate_pct,
            "start_date": req.start_date,
            "maturity_date": req.maturity_date,
            "compounding_frequency": req.compounding_frequency,
            "payout_type": req.payout_type,
            "premature_penalty_pct": req.premature_penalty_pct,
        }
        res = supabase.table("fixed_deposits").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create fixed deposit")
        return {"success": True, "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating fixed deposit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/fixed-deposits/{fd_id}")
async def delete_fixed_deposit(
    fd_id: str,
    current_user: dict = Depends(get_current_user),
):
    _assert_owner(_fetch_owner("fixed_deposits", "fd_id", fd_id), current_user)
    try:
        supabase.table("fixed_deposits").delete().eq("fd_id", fd_id).execute()
        return {"success": True, "message": "Fixed deposit deleted successfully"}
    except Exception as e:
        print(f"Error deleting fixed deposit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


