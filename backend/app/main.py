from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from app.routes import statement_parser, chatbot, api, forecasting, admin, internal
import uvicorn
import logging
import colorlog

# ── Configure colorful logging ────────────────────────────────────────────
# Idempotent setup: this module can be imported twice in one process (once as
# "__main__" via `python app/main.py`, then again as "app.main" when uvicorn
# imports it). Guard against attaching the handler twice, which would otherwise
# emit every log line in duplicate.
_LOG_FORMAT = "%(asctime)s — %(name)s — %(levelname)s — %(message)s"
_root = logging.getLogger()
_root.setLevel(logging.INFO)

if not any(getattr(h, "_finassist_handler", False) for h in _root.handlers):
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s" + _LOG_FORMAT.replace("%(message)s", "%(reset)s%(message)s"),
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        },
        reset=True,
        style='%',
    ))
    handler._finassist_handler = True  # marker so re-import doesn't add a duplicate
    _root.addHandler(handler)

# Quieten noisy third-party loggers (HTTP client request lines, etc.).
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
for _noisy in ("httpx", "httpcore", "openai", "urllib3", "hpack", "supabase", "postgrest"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


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
    from app.services.prophet.inference import reload_models

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
    # Scope the auto-reloader to the source package only. Otherwise the watcher
    # also sees runtime writes (chroma_db/, security_events.json, models/, data/,
    # *.pyc) under the working dir and restarts the server mid-request.
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
        reload_includes=["*.py"],
        reload_excludes=["*.pyc", "__pycache__/*", "*.json", "*.log", "*.sqlite3"],
    )
