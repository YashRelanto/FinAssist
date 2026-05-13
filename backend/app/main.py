from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, dashboard, api
import uvicorn

app = FastAPI(title="FinAssist API")

# Add CORS middleware to allow the React frontend to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include authentication and dashboard routes
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(api.router)

@app.get("/")
async def root():
    # Redirect root to the React Frontend during development
    return RedirectResponse(url="http://localhost:3000/login")

@app.get("/login")
async def login_redirect():
    return RedirectResponse(url="http://localhost:3000/login")

@app.get("/home")
async def home_redirect():
    return RedirectResponse(url="http://localhost:3000/dashboard")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
