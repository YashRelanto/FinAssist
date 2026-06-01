#!/usr/bin/env python3
"""Check local Prophet bundle vs Supabase users and print a test forecast URL."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.forecast_service import generate_forecast, get_model_status, reload_models  # noqa: E402
from app.utils.supabase_client import supabase  # noqa: E402


def main() -> int:
    reload_models(force_storage_sync=False)
    status = get_model_status()
    print("Model loaded:", status["loaded"])
    print("Trained users in bundle:", status["trained_users"])
    print("Bundle:", status.get("bundle_path"))

    manifest_path = ROOT / "models" / "production" / "manifest.json"
    trained_ids: set[str] = set()
    if manifest_path.is_file():
        trained_ids = set(json.loads(manifest_path.read_text()).get("user_ids", []))

    users_res = supabase.table("users").select("user_id,email").limit(50).execute()
    users = users_res.data or []
    print(f"\nSupabase users ({len(users)}):")

    best_uid: str | None = None
    best_weeks = 0

    for u in users:
        uid = str(u.get("user_id", ""))
        has_model = uid in trained_ids
        tx_res = (
            supabase.table("transactions")
            .select("*")
            .eq("user_id", uid)
            .eq("transaction_type", "expense")
            .execute()
        )
        txs = tx_res.data or []
        email = (u.get("email") or "")[:40]
        print(f"  {uid}  model_in_bundle={has_model}  expense_rows={len(txs)}  {email}")

        if has_model and len(txs) > 0:
            cat_res = supabase.table("categories").select("*").execute()
            result = generate_forecast(txs, cat_res.data or [], user_id=uid, days_analyzed=90)
            ok = result.get("success") and result.get("user_model_available")
            pred = result.get("predicted_next_month")
            msg = result.get("message")
            print(f"    -> forecast success={ok} predicted_next_month={pred} message={msg}")

        if has_model:
            from app.services.forecast_features import expenses_to_weekly
            import pandas as pd

            if txs:
                w = expenses_to_weekly(pd.DataFrame(txs))
                if len(w) > best_weeks:
                    best_weeks = len(w)
                    best_uid = uid

    if best_uid:
        print(f"\nTry in browser or curl:")
        print(f"  http://127.0.0.1:8000/api/forecast?user_id={best_uid}&days=90")
    elif trained_ids:
        sample = next(iter(trained_ids))
        print(f"\nNo Supabase user matched bundle; sample trained id:")
        print(f"  http://127.0.0.1:8000/api/forecast?user_id={sample}&days=90")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
