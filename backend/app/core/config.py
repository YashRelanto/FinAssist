import os

# ── Load .env from the project root or backend directory (works regardless of CWD) ─────────────────
_ROOT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_ENV_FILE = os.path.join(_ROOT_DIR, ".env")
_BACKEND_ENV_FILE = os.path.join(_ROOT_DIR, "backend", ".env")

try:
    from dotenv import load_dotenv
    if os.path.exists(_BACKEND_ENV_FILE):
        load_dotenv(dotenv_path=_BACKEND_ENV_FILE, override=False)
    if os.path.exists(_ENV_FILE):
        load_dotenv(dotenv_path=_ENV_FILE, override=False)
except ImportError:
    pass


class Settings:
    # ── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # ── NVIDIA NIM ────────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "nvidia"
    NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
    NVIDIA_CHAT_MODEL: str = os.getenv("NVIDIA_CHAT_MODEL", "meta/llama-3.1-8b-instruct")
    NVIDIA_BASE_URL: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

    # Aliases used by chatbot_engine
    @property
    def active_api_key(self) -> str:
        return self.NVIDIA_API_KEY

    @property
    def active_chat_model(self) -> str:
        return self.NVIDIA_CHAT_MODEL

    @property
    def active_base_url(self) -> str:
        return self.NVIDIA_BASE_URL

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    CHROMA_DB_PATH: str = os.getenv(
        "CHROMA_DB_PATH",
        os.path.normpath(os.path.join(_ROOT_DIR, "backend", "chroma_db"))
    )

    # ── Sessions ──────────────────────────────────────────────────────────────
    SESSIONS_FILE: str = os.getenv(
        "SESSIONS_FILE",
        os.path.normpath(os.path.join(_ROOT_DIR, "backend", "sessions.json"))
    )


settings = Settings()
