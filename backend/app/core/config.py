import os

# ── Load .env from the project root or backend directory (works regardless of CWD) ─────────────────
_ROOT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_ENV_FILE = os.path.join(_ROOT_DIR, ".env")

try:
    from dotenv import load_dotenv
    if os.path.exists(_ENV_FILE):
        load_dotenv(dotenv_path=_ENV_FILE, override=False)
except ImportError:
    pass


class Settings:
    # ── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    # Legacy name; prefer SUPABASE_SERVICE_ROLE_KEY for backend DB access.
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")

    @property
    def supabase_db_key(self) -> str:
        """Service role (or legacy SUPABASE_KEY) for server-side table access."""
        return self.SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_KEY

    @property
    def supabase_auth_key(self) -> str:
        """Anon/publishable key for end-user auth; falls back to DB key if unset."""
        return self.SUPABASE_ANON_KEY or self.SUPABASE_KEY

    # ── NVIDIA NIM ────────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "nvidia"
    NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
    NVIDIA_CHAT_MODEL: str = os.getenv("NVIDIA_CHAT_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
    NVIDIA_ACCOUNT_HUB_MODEL: str = os.getenv(
        "NVIDIA_ACCOUNT_HUB_MODEL",
        "meta/llama-3.1-70b-instruct",
    )
    NVIDIA_BASE_URL: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

    # config.py
    active_chat_model: str = "meta/llama-3.3-70b-instruct"
    brain_model: str = "meta/llama-3.3-70b-instruct"        # 70B for reliable goal routing
    tool_model: str = "meta/llama-3.3-70b-instruct"         # SQL + answers
    knowledge_model: str = "meta/llama-3.1-8b-instruct"     # RAG summarisation
    fast_model: str = "meta/llama-3.1-8b-instruct"          # cheap captions / justifications

    @property
    def active_api_key(self) -> str:
        return self.NVIDIA_API_KEY

    @property
    def active_chat_model(self) -> str:
        return self.NVIDIA_CHAT_MODEL

    @property
    def active_base_url(self) -> str:
        return self.NVIDIA_BASE_URL

    @property
    def account_hub_model(self) -> str:
        return self.NVIDIA_ACCOUNT_HUB_MODEL

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    CHROMA_DB_PATH: str = os.getenv(
        "CHROMA_DB_PATH",
        os.path.normpath(os.path.join(_ROOT_DIR, "backend", "chroma_db"))
    )

    # ── Forecast model storage / cron ─────────────────────────────────────────
    FORECAST_STORAGE_BUCKET: str = os.getenv("FORECAST_STORAGE_BUCKET", "forecast-models")
    FORECAST_STORAGE_ENABLED: str = os.getenv("FORECAST_STORAGE_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    FORECAST_CRON_SECRET: str = os.getenv("FORECAST_CRON_SECRET", "")
    FORECAST_SYNC_ON_STARTUP: bool = os.getenv("FORECAST_SYNC_ON_STARTUP", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    # Public URL of this API (Edge Function calls POST {url}/api/internal/train-forecast)
    TRAINING_WORKER_URL: str = os.getenv("TRAINING_WORKER_URL", "http://localhost:8000")


settings = Settings()
