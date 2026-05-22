# pyrefly: ignore [missing-import]
from supabase import create_client, Client
from app.core.config import settings

def get_supabase_client() -> Client:
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        print("\n" + "="*80)
        print(" WARNING: SUPABASE_URL or SUPABASE_KEY environment variables are missing!")
        print(" Backend API routes will fall back to local simulation mode.")
        print("="*80 + "\n")
        return None
    try:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        print("\n[OK] Supabase client initialized successfully.\n")
        return client
    except Exception as e:
        print(f"\n WARNING: Failed to initialize Supabase client: {e}")
        print(" Falling back to simulation mode.\n")
        return None

supabase = get_supabase_client()
