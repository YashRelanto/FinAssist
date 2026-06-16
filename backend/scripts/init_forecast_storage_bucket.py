#!/usr/bin/env python3
"""Create the forecast-models Supabase Storage bucket (if missing)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.prophet.storage import ensure_forecast_bucket  # noqa: E402


def main() -> int:
    try:
        bucket = ensure_forecast_bucket()
        print(f"Bucket ready: {bucket}")
        return 0
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        print("Run supabase db push or apply supabase/migrations/*_forecast_models_storage.sql", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
