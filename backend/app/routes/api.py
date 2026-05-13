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
    response = supabase.table("users").select("*").eq("email", req.email).eq("password", req.password).execute()
    if not response.data:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = response.data[0]
    return {"success": True, "message": "Login successful!", "user": user}

@router.post("/register")
async def api_register(req: RegisterRequest):
    # Check if exists
    check = supabase.table("users").select("*").eq("email", req.email).execute()
    if check.data:
        raise HTTPException(status_code=400, detail="User already exists")
    
    response = supabase.table("users").insert({
        "full_name": req.full_name,
        "email": req.email,
        "password": req.password
    }).execute()
    
    if not response.data:
        raise HTTPException(status_code=500, detail="Registration failed")
        
    return {"success": True, "message": "Registration successful!", "user": response.data[0]}

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
            "accounts": accounts
        }
    except Exception as e:
        print(f"Error in dashboard-summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/transactions")
async def get_transactions():
    return {"success": True, "message": "Transactions endpoint ready"}

@router.get("/accounts")
async def get_accounts():
    return {"success": True, "message": "Accounts endpoint ready"}

@router.get("/reports")
async def get_reports():
    return {"success": True, "message": "Reports endpoint ready"}
