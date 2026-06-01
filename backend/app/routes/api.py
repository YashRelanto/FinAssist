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
from app.services.transaction_service import create_transaction_record
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
        acc_response = (
            supabase.table("accounts").select("*").eq("user_id", user_id).execute()
        )
        accounts = acc_response.data or []

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
        # 1. Fetch Transactions with filtering
        query = supabase.table("transactions")\
            .select("*")\
            .eq("user_id", user_id)
        
        if start_date:
            query = query.gte("transaction_date", start_date)
        if end_date:
            query = query.lte("transaction_date", end_date)
            
        trans_res = query.order("transaction_date", desc=True).execute()
        transactions = trans_res.data
        
        # 2. Fetch Categories for mapping
        cat_res = supabase.table("categories").select("*").execute()
        cat_map = {c["category_id"]: (c["main_category"], c["sub_category"]) for c in cat_res.data}
        
        # 3. Fetch Accounts for mapping
        acc_res = supabase.table("accounts").select("account_id, account_name").eq("user_id", user_id).execute()
        acc_map = {a["account_id"]: a["account_name"] for a in acc_res.data}
        
        # 4. Map and Format
        formatted = []
        for t in transactions:
            main_cat, sub_cat = cat_map.get(t["category_id"], ("Uncategorized", "General"))
            formatted.append({
                "id": t["transaction_id"],
                "date": t["transaction_date"],
                "merchant": t["merchant_name"] or t["description"] or "Unknown",
                "category": normalize_category_name(main_cat),
                "subCategory": sub_cat,
                "amount": float(t["amount"]),
                "account": acc_map.get(t["account_id"], "Unknown Account"),
                "account_id": t["account_id"],
                "category_id": t["category_id"],
                "type": t["transaction_type"],
                "notes": t["description"]
            })
            
        return {"success": True, "data": formatted}
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/transactions/{trans_id}")
async def update_transaction(trans_id: str, req: TransactionCreate):
    try:
        # 1. Map Category
        cat_res = supabase.table("categories")\
            .select("category_id")\
            .eq("main_category", req.main_category)\
            .eq("sub_category", req.sub_category)\
            .execute()
        
        if not cat_res.data:
            cat_res = supabase.table("categories")\
                .select("category_id")\
                .eq("main_category", req.main_category)\
                .eq("sub_category", "General")\
                .execute()
        
        category_id = cat_res.data[0]["category_id"] if cat_res.data else None
        
        # 2. Update Transaction
        update_data = {
            "account_id": req.account_id,
            "category_id": category_id,
            "amount": req.amount,
            "transaction_type": req.transaction_type,
            "merchant_name": req.merchant_name,
            "description": req.description,
            "transaction_date": req.transaction_date
        }
        
        supabase.table("transactions").update(update_data).eq("transaction_id", trans_id).execute()
        
        # Note: In a real app, you'd also need to adjust balances, but for now we'll keep it simple
        return {"success": True, "message": "Transaction updated successfully"}
    except Exception as e:
        print(f"Error updating transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

@router.post("/accounts")
async def create_account(req: AccountCreate):
    try:
        response = supabase.table("accounts").insert({
            "user_id": req.user_id,
            "account_name": req.account_name,
            "account_type": req.account_type,
            "current_balance": req.current_balance
        }).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create account")
            
        return {"success": True, "message": "Account created successfully", "data": response.data[0]}
    except Exception as e:
        print(f"Error creating account: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/accounts")
async def get_accounts(user_id: str):
    res = supabase.table("accounts").select("*").eq("user_id", user_id).execute()
    return {"success": True, "data": res.data}

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
        budget_res = (
            supabase.table("budgets")
            .select("*, categories(main_category, sub_category)")
            .eq("user_id", user_id)
            .execute()
        )
        trans_response = (
            supabase.table("transactions")
            .select(
                "transaction_id, amount, transaction_type, transaction_date, category_id"
            )
            .eq("user_id", user_id)
            .order("transaction_date")
            .execute()
        )
        goals_res = (
            supabase.table("goals").select("*").eq("user_id", user_id).execute()
        )
        return build_budget_goals_payload(
            budgets=budget_res.data or [],
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


