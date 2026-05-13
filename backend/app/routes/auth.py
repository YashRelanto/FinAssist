# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Form, Request, HTTPException
# pyrefly: ignore [missing-import]
from fastapi.responses import HTMLResponse, RedirectResponse
from app.utils.supabase_client import supabase

router = APIRouter()

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
    # Simple check against users table
    response = supabase.table("users").select("*").eq("email", email).eq("password", password).execute()
    
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
    
    # Insert into users table
    response = supabase.table("users").insert({"full_name": full_name, "email": email, "password": password}).execute()
    
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to register user")
    
    user_id = response.data[0]["user_id"]
    return RedirectResponse(url=f"/home?user_id={user_id}", status_code=303)

