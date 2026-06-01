# pyrefly: ignore [missing-import]
"""
Supabase clients for FinAssist backend.

- supabase_auth: anon/publishable key — sign-in / sign-up only (never used for table writes).
- supabase_db: service role key — all PostgREST table access (bypasses RLS, stable session).

Using one client for both causes sign_in to replace the service-role JWT with the user's
JWT, which re-enables RLS and breaks profile sync inserts.
"""

from supabase import create_client, Client

from app.core.config import settings

def _create_client(url: str, key: str, label: str) -> Client | None:
    if not url or not key:
        return None
    try:
        client = create_client(url, key)
        print(f"\n[OK] Supabase {label} client initialized.\n")
        return client
    except Exception as e:
        print(f"\n WARNING: Failed to initialize Supabase {label} client: {e}\n")
        return None


def get_supabase_clients() -> tuple[Client | None, Client | None]:
    url = settings.SUPABASE_URL
    db_key = settings.supabase_db_key
    auth_key = settings.supabase_auth_key

    if not url or not db_key:
        print("\n" + "=" * 80)
        print(" WARNING: SUPABASE_URL or database key (SUPABASE_SERVICE_ROLE_KEY /")
        print("          SUPABASE_KEY) is missing. API routes will use simulation mode.")
        print("=" * 80 + "\n")
        return None, None

    db_client = _create_client(url, db_key, "database (service)")
    auth_client = _create_client(url, auth_key, "auth") if auth_key else db_client
    return db_client, auth_client


supabase_db, supabase_auth = get_supabase_clients()

# Backward-compatible alias: table routes use service-role DB client.
supabase = supabase_db
