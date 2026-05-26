from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.supabase_client import supabase
from datetime import datetime
from collections import defaultdict

router = APIRouter(prefix="/api")

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str

@router.post("/login")
async def api_login(req: LoginRequest):
    try:
        # 1. Sign in with Supabase Auth
        auth_res = supabase.auth.sign_in_with_password({
            "email": req.email,
            "password": req.password
        })
        
        if not auth_res.user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
        # 2. Retrieve user record from public.users table
        response = supabase.table("users").select("*").eq("email", req.email).execute()
        if not response.data:
            # Sync user if they somehow exist in auth but not in public table
            full_name = auth_res.user.user_metadata.get("full_name", req.email.split('@')[0]) if auth_res.user.user_metadata else req.email.split('@')[0]
            sync_res = supabase.table("users").insert({
                "user_id": auth_res.user.id,
                "full_name": full_name,
                "email": req.email
            }).execute()
            if not sync_res.data:
                raise HTTPException(status_code=500, detail="User record not found and failed to sync")
            user = sync_res.data[0]
        else:
            user = response.data[0]
            
        return {"success": True, "message": "Login successful!", "user": user}
    except Exception as e:
        print(f"Error in api_login: {e}")
        detail_msg = "Invalid credentials"
        if "Invalid login credentials" in str(e) or "invalid" in str(e).lower():
            detail_msg = "Invalid email or password"
        elif hasattr(e, 'message'):
            detail_msg = e.message
        raise HTTPException(status_code=401, detail=detail_msg)

@router.post("/register")
async def api_register(req: RegisterRequest):
    try:
        # Check if already exists in public table
        check = supabase.table("users").select("*").eq("email", req.email).execute()
        if check.data:
            raise HTTPException(status_code=400, detail="User already exists")
        
        # 1. Sign up with Supabase Auth
        auth_res = supabase.auth.sign_up({
            "email": req.email,
            "password": req.password,
            "options": {
                "data": {
                    "full_name": req.full_name
                }
            }
        })
        
        if not auth_res.user:
            raise HTTPException(status_code=500, detail="Failed to create auth user")
            
        # 2. Insert user into public.users table mapping the user_id to the Supabase UUID
        response = supabase.table("users").insert({
            "user_id": auth_res.user.id,
            "full_name": req.full_name,
            "email": req.email
        }).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Registration failed to sync to ledger")
            
        return {"success": True, "message": "Registration successful!", "user": response.data[0]}
    except Exception as e:
        print(f"Error in api_register: {e}")
        if hasattr(e, 'message'):
            raise HTTPException(status_code=400, detail=e.message)
        raise HTTPException(status_code=500, detail=str(e))

class UserUpdateRequest(BaseModel):
    full_name: str
    email: str

@router.put("/users/{user_id}")
async def update_user_profile(user_id: str, req: UserUpdateRequest):
    try:
        response = supabase.table("users").update({
            "full_name": req.full_name,
            "email": req.email
        }).eq("user_id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found or update failed")
            
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
                try:
                    update_res = supabase.table("users").update({"user_id": req.user_id}).eq("email", req.email).execute()
                    if update_res.data:
                        user = update_res.data[0]
                except Exception as sync_err:
                    print(f"Foreign key prevented direct update, deleting obsolete mismatch row: {sync_err}")
                    # Delete obsolete local row and insert clean Supabase UUID row
                    supabase.table("users").delete().eq("email", req.email).execute()
                    insert_res = supabase.table("users").insert({
                        "user_id": req.user_id,
                        "full_name": req.full_name,
                        "email": req.email
                    }).execute()
                    if insert_res.data:
                        user = insert_res.data[0]
            return {"success": True, "message": "OAuth login successful", "user": user}
        
        # User does not exist, insert user with their Supabase user_id
        response = supabase.table("users").insert({
            "user_id": req.user_id,
            "full_name": req.full_name,
            "email": req.email
        }).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to register OAuth user")
            
        return {"success": True, "message": "OAuth registration successful", "user": response.data[0]}
    except Exception as e:
        print(f"Error in oauth-login: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard-summary")
async def get_dashboard_summary(user_id: str):
    try:
        # 1. Fetch Accounts
        acc_response = supabase.table("accounts").select("*").eq("user_id", user_id).execute()
        accounts = acc_response.data
        total_balance = sum(float(a["current_balance"]) for a in accounts) if accounts else 0
        
        # 2. Fetch Transactions
        trans_response = supabase.table("transactions")\
            .select("amount, transaction_type, transaction_date")\
            .eq("user_id", user_id)\
            .order("transaction_date")\
            .execute()
        transactions = trans_response.data
        
        # 3. Aggregation logic
        monthly_stats = defaultdict(lambda: {"income": 0, "expense": 0})
        current_month_str = datetime.now().strftime("%Y-%m")
        
        for t in transactions:
            date_str = t["transaction_date"]
            month_key = date_str[:7] # YYYY-MM
            amount = abs(float(t["amount"])) # Ensure positive amount for sums
            
            if t["transaction_type"] == "income":
                monthly_stats[month_key]["income"] += amount
            else:
                monthly_stats[month_key]["expense"] += amount
        
        # Current month specific stats
        curr_stats = monthly_stats.get(current_month_str, {"income": 0, "expense": 0})
        
        # Format chart data (last 7 months)
        sorted_months = sorted(monthly_stats.keys())[-7:]
        chart_data = []
        for m in sorted_months:
            inc = monthly_stats[m]["income"]
            exp = monthly_stats[m]["expense"]
            chart_data.append({
                "name": datetime.strptime(m, "%Y-%m").strftime("%b"), # 'Jan', 'Feb', etc.
                "income": inc,
                "expense": exp,
                "net": inc - exp
            })
            
        # 4. Fetch Recent Transactions (last 5)
        recent_res = supabase.table("transactions")\
            .select("*, categories(main_category, sub_category), accounts(account_name)")\
            .eq("user_id", user_id)\
            .order("transaction_date", desc=True)\
            .limit(5)\
            .execute()
        
        recent_transactions = []
        for t in recent_res.data:
            recent_transactions.append({
                "id": t["transaction_id"],
                "date": t["transaction_date"],
                "merchant": t["merchant_name"],
                "amount": float(t["amount"]),
                "type": t["transaction_type"],
                "category": t["categories"]["main_category"] if t["categories"] else "Uncategorized",
                "subCategory": t["categories"]["sub_category"] if t["categories"] else "General",
                "account": t["accounts"]["account_name"] if t["accounts"] else "Unknown"
            })

        return {
            "success": True,
            "summary": {
                "total_balance": total_balance,
                "monthly_income": curr_stats["income"],
                "monthly_expenses": curr_stats["expense"],
                "net_savings": curr_stats["income"] - curr_stats["expense"],
                "savings_rate": round((curr_stats["income"] - curr_stats["expense"]) / curr_stats["income"] * 100, 1) if curr_stats["income"] > 0 else 0
            },
            "chart_data": chart_data,
            "accounts": accounts,
            "recent_transactions": recent_transactions
        }
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
        
        # 2. Get Account Balance & Calculate New Balance
        acc_res = supabase.table("accounts").select("current_balance").eq("account_id", req.account_id).execute()
        if not acc_res.data:
            raise HTTPException(status_code=404, detail="Account not found")
        
        curr_bal = float(acc_res.data[0]["current_balance"])
        # In this DB schema, amount is stored as absolute, type handles sign
        new_bal = curr_bal + req.amount if req.transaction_type == "income" else curr_bal - req.amount
        
        # 3. Insert Transaction
        trans_data = {
            "user_id": req.user_id,
            "account_id": req.account_id,
            "category_id": category_id,
            "amount": req.amount,
            "transaction_type": req.transaction_type,
            "merchant_name": req.merchant_name,
            "description": req.description,
            "transaction_date": req.transaction_date,
            "running_balance": new_bal
        }
        
        supabase.table("transactions").insert(trans_data).execute()
        
        # 4. Update Account Balance
        supabase.table("accounts").update({"current_balance": new_bal}).eq("account_id", req.account_id).execute()
        
        return {"success": True, "message": "Transaction added successfully", "new_balance": new_bal}
        
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
                "category": main_cat,
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

@router.get("/reports")
async def get_reports():
    return {"success": True, "message": "Reports endpoint ready"}
