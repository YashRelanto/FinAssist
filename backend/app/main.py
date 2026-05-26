# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, dashboard, statement_parser, chatbot
# pyrefly: ignore [missing-import]
import uvicorn

app = FastAPI(title="FinAssist API")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include authentication routes
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(statement_parser.router)
app.include_router(chatbot.router)

@app.get("/")
async def root():
    # Redirect root to login page
    return RedirectResponse(url="/login")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
