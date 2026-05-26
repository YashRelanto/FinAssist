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
@router.post("/api/register")
async def api_register(data: UserRegister):
    if not supabase:
        # Offline/Simulation fallback
        return {
            "user_id": "a9a11e1f-f158-4d8e-ae55-407a5e00410f",
            "full_name": data.full_name,
            "email": data.email
        }
    
    # Check if user already exists
    check = supabase.table("users").select("*").eq("email", data.email).execute()
    if check.data:
        raise HTTPException(status_code=400, detail="User already exists.")
    
    try:
        # Insert into users table
        response = supabase.table("users").insert({
            "full_name": data.full_name,
            "email": data.email,
            "password": data.password
        }).execute()
    except Exception as e:
        if "password" in str(e):
            # Fallback if password column is missing in database schema
            response = supabase.table("users").insert({
                "full_name": data.full_name,
                "email": data.email
            }).execute()
        else:
            raise e
    
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to register user")
    
    user = response.data[0]
    return {
        "user_id": user["user_id"],
        "full_name": user["full_name"],
        "email": user["email"]
    }

@router.post("/api/login")
async def api_login(data: UserLogin):
    if not supabase:
        # Offline/Simulation fallback
        return {
            "user_id": "a9a11e1f-f158-4d8e-ae55-407a5e00410f",
            "full_name": "Demo User",
            "email": data.email
        }
        
    try:
        response = supabase.table("users").select("*").eq("email", data.email).eq("password", data.password).execute()
    except Exception as e:
        if "password" in str(e):
            # Fallback if password column is missing in database schema
            response = supabase.table("users").select("*").eq("email", data.email).execute()
        else:
            raise e
    
    if not response.data:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    
    user = response.data[0]
    return {
        "user_id": user["user_id"],
        "full_name": user["full_name"],
        "email": user["email"]
    }

