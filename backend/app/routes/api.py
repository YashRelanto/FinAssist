from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.supabase_client import supabase

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
    # Fetch real data for charts (reusing our previous logic)
    trans_response = supabase.table("transactions")\
        .select("transaction_date, running_balance")\
        .eq("user_id", user_id)\
        .order("transaction_date")\
        .execute()
    
    return {
        "success": True, 
        "message": "Dashboard summary loaded",
        "transactions": trans_response.data
    }

@router.get("/transactions")
async def get_transactions():
    return {"success": True, "message": "Transactions endpoint ready"}

@router.get("/accounts")
async def get_accounts():
    return {"success": True, "message": "Accounts endpoint ready"}

@router.get("/reports")
async def get_reports():
    return {"success": True, "message": "Reports endpoint ready"}
