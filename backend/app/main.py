# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.responses import RedirectResponse
from app.routes import auth, dashboard
# pyrefly: ignore [missing-import]
import uvicorn

app = FastAPI(title="FinAssist API")

# Include authentication routes
app.include_router(auth.router)
app.include_router(dashboard.router)

@app.get("/")
async def root():
    # Redirect root to login page
    return RedirectResponse(url="/login")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
