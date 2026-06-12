from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.logging_config import configure_logging
from app.routes import statement_parser, chatbot, api, forecasting, admin, internal
import uvicorn

configure_logging()

app = FastAPI(title="FinAssist API")

# Add CORS middleware to allow the React frontend to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"], # Explicit origins required when credentials=True
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_api_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response

app.include_router(api.router)
app.include_router(statement_parser.router)
app.include_router(chatbot.router)
app.include_router(forecasting.router)
app.include_router(admin.router)
app.include_router(internal.router)


@app.on_event("startup")
async def sync_forecast_models_on_startup():
    from app.core.config import settings
    from app.services.forecast_service import reload_models

    if settings.FORECAST_SYNC_ON_STARTUP and settings.FORECAST_STORAGE_ENABLED:
        reload_models(force_storage_sync=False)

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
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        access_log=False,
        log_config=None,
    )
