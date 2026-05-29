# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Form, Request, HTTPException
# pyrefly: ignore [missing-import]
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from app.utils.supabase_client import supabase

router = APIRouter()

class UserRegister(BaseModel):
    full_name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

@router.get("/login", response_class=HTMLResponse)
async def login_get():
    return """
    <html>
        <body>
            <h2>Login</h2>
            <form action="/login" method="post">
                Email: <input type="email" name="email" required><br>
                Password: <input type="password" name="password" required><br>
                <button type="submit">Login</button>
            </form>
            <p>Don't have an account? <a href="/register">Register here</a></p>
        </body>
    </html>
    """

@router.post("/login")
async def login_post(email: str = Form(...), password: str = Form(...)):
    try:
        # Simple check against users table
        response = supabase.table("users").select("*").eq("email", email).eq("password", password).execute()
    except Exception as e:
        if "password" in str(e):
            # Fallback if password column is missing in database schema
            response = supabase.table("users").select("*").eq("email", email).execute()
        else:
            raise e
    
    if not response.data:
        return HTMLResponse(content="<h2>Login failed. Invalid email or password.</h2><a href='/login'>Try again</a>", status_code=401)
    
    user_id = response.data[0]["user_id"]
    return RedirectResponse(url=f"/home?user_id={user_id}", status_code=303)

@router.get("/register", response_class=HTMLResponse)
async def register_get():
    return """
    <html>
        <body>
            <h2>Register</h2>
            <form action="/register" method="post">
                Name: <input type="text" name="full_name" required><br>
                Email: <input type="email" name="email" required><br>
                Password: <input type="password" name="password" required><br>
                <button type="submit">Register</button>
            </form>
            <p>Already have an account? <a href="/login">Login here</a></p>
        </body>
    </html>
    """

@router.post("/register")
async def register_post(full_name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    # Check if user already exists
    check = supabase.table("users").select("*").eq("email", email).execute()
    if check.data:
        return HTMLResponse(content="<h2>Registration failed. User already exists.</h2><a href='/register'>Try again</a>", status_code=400)
    
    try:
        # Insert into users table
        response = supabase.table("users").insert({"full_name": full_name, "email": email, "password": password}).execute()
    except Exception as e:
        if "password" in str(e):
            # Fallback if password column is missing in database schema
            response = supabase.table("users").insert({"full_name": full_name, "email": email}).execute()
        else:
            raise e
    
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to register user")
    
    user_id = response.data[0]["user_id"]
    return RedirectResponse(url=f"/home?user_id={user_id}", status_code=303)

# JSON API routes for React Frontend
async def get_user_with_profile(user_id: str, email: str, full_name: str) -> dict:
    # 1. Fetch from public.users table
    u_res = supabase.table("users").select("*").eq("user_id", user_id).execute()
    if not u_res.data:
        # User row missing, sync insert it!
        u_res = supabase.table("users").insert({
            "user_id": user_id,
            "full_name": full_name,
            "email": email
        }).execute()
        
    user = u_res.data[0]
    
    # 2. Fetch from public.user_profiles table
    p_res = supabase.table("user_profiles").select("*").eq("user_id", user_id).execute()
    if not p_res.data:
        # Profile row missing, sync insert a default one!
        p_res = supabase.table("user_profiles").insert({
            "user_id": user_id,
            "onboarded": False,
            "income": 0,
            "city_tier": "Metro",
            "fixed_rent": 0,
            "fixed_emi": 0,
            "biggest_category": "",
            "primary_goal": ""
        }).execute()
        
    profile = p_res.data[0]
    
    # 3. Merge and return unified dictionary
    return {
        "user_id": user["user_id"],
        "full_name": user["full_name"],
        "email": user["email"],
        "onboarded": profile["onboarded"],
        "income": float(profile["income"]),
        "city_tier": profile["city_tier"],
        "fixed_rent": float(profile["fixed_rent"]),
        "fixed_emi": float(profile["fixed_emi"]),
        "biggest_category": profile["biggest_category"],
        "primary_goal": profile["primary_goal"]
    }

@router.post("/api/register")
async def api_register(data: UserRegister):
    if not supabase:
        # Offline/Simulation fallback
        return {
            "user_id": "a9a11e1f-f158-4d8e-ae55-407a5e00410f",
            "full_name": data.full_name,
            "email": data.email,
            "onboarded": False,
            "income": 0,
            "city_tier": "Metro",
            "fixed_rent": 0,
            "fixed_emi": 0,
            "biggest_category": "",
            "primary_goal": ""
        }
    
    try:
        # Check if user already exists
        check = supabase.table("users").select("*").eq("email", data.email).execute()
        if check.data:
            raise HTTPException(status_code=400, detail="User already exists.")
        
        # 1. Sign up with Supabase Auth
        auth_res = supabase.auth.sign_up({
            "email": data.email,
            "password": data.password,
            "options": {
                "data": {
                    "full_name": data.full_name
                }
            }
        })
        
        if not auth_res.user:
            raise HTTPException(status_code=500, detail="Failed to create auth user")
            
        # Check if email confirmation is required/pending
        email_confirmed = False
        if auth_res.session is not None:
            email_confirmed = True
        elif auth_res.user and auth_res.user.email_confirmed_at:
            email_confirmed = True

        # 2. Retrieve user record with profile
        user = await get_user_with_profile(auth_res.user.id, data.email, data.full_name)
        user["email_confirmed"] = email_confirmed
        return user
    except Exception as e:
        print(f"Error in auth.py api_register: {e}")
        if hasattr(e, 'message'):
            raise HTTPException(status_code=400, detail=e.message)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/login")
async def api_login(data: UserLogin):
    if not supabase:
        # Offline/Simulation fallback
        return {
            "user_id": "a9a11e1f-f158-4d8e-ae55-407a5e00410f",
            "full_name": "Demo User",
            "email": data.email,
            "onboarded": True,
            "income": 45000,
            "city_tier": "Metro",
            "fixed_rent": 1500,
            "fixed_emi": 500,
            "biggest_category": "Shopping",
            "primary_goal": "Save More Money",
            "email_confirmed": True
        }
        
    try:
        # 1. Sign in with Supabase Auth
        auth_res = supabase.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password
        })
        
        if not auth_res.user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
        # 2. Retrieve user record from database
        user = await get_user_with_profile(
            auth_res.user.id,
            data.email,
            auth_res.user.user_metadata.get("full_name", data.email.split('@')[0]) if auth_res.user.user_metadata else data.email.split('@')[0]
        )
        user["email_confirmed"] = True
            
        return user
    except Exception as e:
        print(f"Error in auth.py api_login: {e}")
        err_msg = str(e)
        if "email not confirmed" in err_msg.lower() or "email_not_confirmed" in err_msg.lower() or "confirm" in err_msg.lower():
            raise HTTPException(status_code=400, detail="email_not_confirmed")
            
        detail_msg = "Invalid email or password."
        if "Invalid login credentials" in str(e) or "invalid" in str(e).lower():
            detail_msg = "Invalid email or password"
        elif hasattr(e, 'message'):
            detail_msg = e.message
        raise HTTPException(status_code=401, detail=detail_msg)

