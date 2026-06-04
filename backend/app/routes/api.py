from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.utils.supabase_client import supabase, supabase_auth, supabase_db
from app.services.user_profile_service import (
    ensure_user_with_profile,
    auth_error_detail,
)
from app.services.dashboard_metrics_service import (
    build_budget_goals_payload,
    build_dashboard_payload,
    normalize_category_name,
)
from app.services.account_hub_analysis_service import generate_account_hub_analysis
from app.services.accounts_service import fetch_user_accounts, insert_account
from app.services.transaction_service import (
    create_transaction_record,
    update_transaction_record,
)
from datetime import datetime

router = APIRouter(prefix="/api")

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
    """Flat + nested shape so Login.tsx and other clients both work."""
    body = {**user, "email_confirmed": email_confirmed, "success": True}
    body["user"] = user
    if access_token:
        body["access_token"] = access_token
    if refresh_token:
        body["refresh_token"] = refresh_token
    return body


@router.post("/login")
async def api_login(req: LoginRequest):
    if not supabase_auth or not supabase_db:
        return _login_payload(
            {
                "user_id": "a9a11e1f-f158-4d8e-ae55-407a5e00410f",
                "full_name": "Demo User",
                "email": req.email,
                "role": "user",
                "onboarded": True,
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
async def update_user_profile(user_id: str, req: UserUpdateRequest):
    try:
        # 1. Update basic user info in public.users table
        response = supabase.table("users").update({
            "full_name": req.full_name,
            "email": req.email
        }).eq("user_id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found or update failed")
            
        # 2. Update/Upsert onboarding metrics in public.user_profiles table
        profile_data = {}
        if req.onboarded is not None: profile_data["onboarded"] = req.onboarded
        if req.income is not None: profile_data["income"] = req.income
        if req.city_tier is not None: profile_data["city_tier"] = req.city_tier
        if req.fixed_rent is not None: profile_data["fixed_rent"] = req.fixed_rent
        if req.fixed_emi is not None: profile_data["fixed_emi"] = req.fixed_emi
        if req.biggest_category is not None: profile_data["biggest_category"] = req.biggest_category
        if req.primary_goal is not None: profile_data["primary_goal"] = req.primary_goal
        
        if profile_data:
            prof_check = supabase.table("user_profiles").select("*").eq("user_id", user_id).execute()
            if prof_check.data:
                supabase.table("user_profiles").update(profile_data).eq("user_id", user_id).execute()
            else:
                profile_data["user_id"] = user_id
                supabase.table("user_profiles").insert(profile_data).execute()
            
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
    try:
        # Check if user already exists
        check = supabase.table("users").select("*").eq("email", req.email).execute()
        if check.data:
            user = check.data[0]
            # Self-healing mismatch correction: update old user_id to match Supabase Auth UUID
            if user["user_id"] != req.user_id:
                old_user_id = user["user_id"]
                try:
                    # 1. Update the email of the old user row to free up the unique constraint
                    temp_email = f"obsolete_{old_user_id}@{req.email}"
                    supabase.table("users").update({"email": temp_email}).eq("user_id", old_user_id).execute()
                    
                    # 2. Insert the new user row with the correct user_id and email
                    supabase.table("users").insert({
                        "user_id": req.user_id,
                        "full_name": req.full_name,
                        "email": req.email,
                    }).execute()
                    
                    # 3. Update referencing tables
                    supabase.table("user_profiles").update({"user_id": req.user_id}).eq("user_id", old_user_id).execute()
                    supabase.table("accounts").update({"user_id": req.user_id}).eq("user_id", old_user_id).execute()
                    supabase.table("transactions").update({"user_id": req.user_id}).eq("user_id", old_user_id).execute()
                    
                    # 4. Safely delete obsolete mismatch row
                    supabase.table("users").delete().eq("user_id", old_user_id).execute()
                except Exception as sync_err:
                    print(f"Failed self-healing user_id update: {sync_err}")
            
            user_profile = ensure_user_with_profile(req.user_id, req.email, req.full_name)
            return {"success": True, "message": "OAuth login successful", "user": user_profile}
        
        # User does not exist, sync insert both user and user profile
        user_profile = ensure_user_with_profile(req.user_id, req.email, req.full_name)
        return {"success": True, "message": "OAuth registration successful", "user": user_profile}
    except Exception as e:
        print(f"Error in oauth-login: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard-summary")
async def get_dashboard_summary(user_id: str):
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        accounts = fetch_user_accounts(user_id)

        trans_response = (
            supabase.table("transactions")
            .select(
                "transaction_id, amount, transaction_type, transaction_date, "
                "category_id, categories(main_category, sub_category)"
            )
            .eq("user_id", user_id)
            .order("transaction_date")
            .execute()
        )
        transactions = trans_response.data or []

        recent_res = (
            supabase.table("transactions")
            .select("*, categories(main_category, sub_category), accounts(account_name)")
            .eq("user_id", user_id)
            .order("transaction_date", desc=True)
            .limit(5)
            .execute()
        )

        budget_res = (
            supabase.table("budgets")
            .select("*, categories(main_category, sub_category)")
            .eq("user_id", user_id)
            .execute()
        )

        prof_res = (
            supabase.table("user_profiles")
            .select("income")
            .eq("user_id", user_id)
            .execute()
        )
        profile_income = 0.0
        if prof_res.data:
            profile_income = float(prof_res.data[0].get("income") or 0.0)

        return build_dashboard_payload(
            accounts=accounts,
            transactions=transactions,
            recent_rows=recent_res.data or [],
            budgets=budget_res.data or [],
            profile_income=profile_income,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in dashboard-summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account-hub-analysis")
async def get_account_hub_analysis(user_id: str):
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        return generate_account_hub_analysis(user_id.strip())
    except Exception as e:
        print(f"Error in account-hub-analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TransactionCreate(BaseModel):
    user_id: str
    account_id: str
    amount: float
    transaction_type: str
    merchant_name: str
    description: str
    main_category: str
    sub_category: str = "General"
    transaction_date: str

@router.post("/transactions")
async def create_transaction(req: TransactionCreate):
    try:
        result = create_transaction_record(
            user_id=req.user_id,
            account_id=req.account_id,
            amount=req.amount,
            transaction_type=req.transaction_type,
            merchant_name=req.merchant_name,
            description=req.description,
            main_category=req.main_category,
            sub_category=req.sub_category,
            transaction_date=req.transaction_date,
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
async def get_transactions(user_id: str, start_date: str = None, end_date: str = None):
    try:
        # Single query with joins (avoids N+1 / extra mapping queries)
        query = (
            supabase.table("transactions")
            .select(
                "transaction_id,transaction_date,amount,transaction_type,merchant_name,description,"
                "account_id,category_id,"
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
                }
            )
        return {"success": True, "data": formatted}
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/transactions/{trans_id}")
async def update_transaction(trans_id: str, req: TransactionCreate):
    try:
        result = update_transaction_record(
            transaction_id=trans_id,
            user_id=req.user_id,
            account_id=req.account_id,
            amount=req.amount,
            transaction_type=req.transaction_type,
            merchant_name=req.merchant_name,
            description=req.description,
            main_category=req.main_category,
            sub_category=req.sub_category,
            transaction_date=req.transaction_date,
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
async def delete_transaction(trans_id: str):
    try:
        supabase.table("transactions").delete().eq("transaction_id", trans_id).execute()
        return {"success": True, "message": "Transaction deleted successfully"}
    except Exception as e:
        print(f"Error deleting transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class AccountCreate(BaseModel):
    user_id: str
    account_name: str
    account_type: str
    current_balance: float = 0.0
    credit_limit: float | None = None
    bank_name: str | None = None
    account_holder: str | None = None
    account_number: str | None = None
    ifsc: str | None = None

@router.post("/accounts")
async def create_account(req: AccountCreate):
    uid = (req.user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id is required")
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
async def update_account(account_id: str, req: AccountCreate):
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
async def get_accounts(user_id: str):
    uid = (user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id is required")
    return {"success": True, "data": fetch_user_accounts(uid)}

@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    try:
        supabase.table("accounts").delete().eq("account_id", account_id).execute()
        return {"success": True, "message": "Account deleted successfully"}
    except Exception as e:
        print(f"Error deleting account: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class BudgetCreate(BaseModel):
    user_id: str
    category_name: str
    budget_name: str
    amount: float
    period: str = "monthly"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    alert_threshold: float = 80.0

class GoalCreate(BaseModel):
    user_id: str
    goal_name: str
    description: Optional[str] = ""
    target_amount: float
    current_amount: float = 0.0
    target_date: str
    status: str = "active"

@router.get("/budget-goals-summary")
async def get_budget_goals_summary(user_id: str):
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
                "transaction_id, amount, transaction_type, transaction_date, category_id"
            )
            .eq("user_id", uid)
            .gte("transaction_date", min_tx_date)
            .order("transaction_date")
            .execute()
        )
        goals_res = (
            supabase.table("goals").select("*").eq("user_id", uid).execute()
        )
        return build_budget_goals_payload(
            budgets=budgets,
            transactions=trans_response.data or [],
            goals=goals_res.data or [],
        )
    except Exception as e:
        print(f"Error fetching budget-goals summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/budgets")
async def get_budgets(user_id: str):
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
async def create_budget(req: BudgetCreate):
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
        
        start_date = req.start_date
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
            
        end_date = req.end_date
        if not end_date:
            from datetime import timedelta
            end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            
        insert_data = {
            "user_id": req.user_id,
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
async def update_budget(budget_id: str, req: BudgetCreate):
    try:
        cat_res = supabase.table("categories")\
            .select("category_id")\
            .ilike("main_category", req.category_name)\
            .ilike("sub_category", "General")\
            .execute()
            
        category_id = cat_res.data[0]["category_id"] if cat_res.data else None
        
        start_date = req.start_date
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
            
        end_date = req.end_date
        if not end_date:
            from datetime import timedelta
            end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            
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
async def delete_budget(budget_id: str):
    try:
        supabase.table("budgets").delete().eq("budget_id", budget_id).execute()
        return {"success": True, "message": "Budget deleted successfully"}
    except Exception as e:
        print(f"Error deleting budget: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/goals")
async def get_goals(user_id: str):
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
async def create_goal(req: GoalCreate):
    try:
        insert_data = {
            "user_id": req.user_id,
            "goal_name": req.goal_name,
            "description": req.description,
            "target_amount": req.target_amount,
            "current_amount": req.current_amount,
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
async def update_goal(goal_id: str, req: GoalCreate):
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
async def delete_goal(goal_id: str):
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
    user_id: str
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
async def create_investment(req: InvestmentCreate):
    try:
        insert_data = {
            "user_id": req.user_id,
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
async def delete_investment(investment_id: str):
    try:
        supabase.table("investments").delete().eq("investment_id", investment_id).execute()
        return {"success": True, "message": "Holding transaction deleted successfully"}
    except Exception as e:
        print(f"Error deleting investment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/investments")
async def get_user_investments(user_id: str):
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
                with urllib.request.urlopen(req) as response:
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


