#!/usr/bin/env python3
"""One-off: train per-user Prophet from Supabase (or exit with instructions)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.prophet.inference import reload_models  # noqa: E402
from app.services.prophet.jobs import run_training_sync  # noqa: E402


def main() -> int:
    try:
        result = run_training_sync()
        print("Bootstrap OK:", result)
        return 0
    except Exception as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        print("Ensure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set in .env", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
