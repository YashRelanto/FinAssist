#!/usr/bin/env python3
"""
Nightly cron entrypoint: train per-user Prophet models from Supabase and promote to production.

Example crontab (2 AM daily):
  0 2 * * * cd /path/to/FinAssistAI && PYTHONPATH=backend python backend/scripts/train_prophet_from_db.py >> logs/forecast_train.log 2>&1
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.forecast_service import reload_models  # noqa: E402
from app.services.model_monitoring_service import save_training_baseline_from_db  # noqa: E402
from app.services.prophet_training_service import run_training_pipeline  # noqa: E402


def main() -> int:
    try:
        result = run_training_pipeline(promote=True)
        save_training_baseline_from_db()
        reload_models()
        print(
            f"OK trained_users={result['trained_users']} "
            f"mape={result.get('test_mape')} "
            f"path={result.get('production_path')}",
        )
        return 0
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
