"""Admin-facing training jobs — Prophet per-user models from the database."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.forecast_service import reload_models
from app.services.prophet_training_service import (
    PRODUCTION_BUNDLE_PATH,
    PRODUCTION_MANIFEST_PATH,
    STAGING_BUNDLE_PATH,
    run_training_pipeline,
)


@dataclass
class TrainingJob:
    job_id: str
    status: str = "queued"
    progress: float = 0.0
    logs: list[dict[str, str]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def log(self, level: str, message: str) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        }
        with self._lock:
            self.logs.append(entry)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status,
                "progress": round(self.progress, 1),
                "logs": list(self.logs[-200:]),
                "metrics": dict(self.metrics),
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


_jobs: dict[str, TrainingJob] = {}
_jobs_lock = threading.Lock()

TRAINABLE_MODELS = ("prophet",)
MODEL_FILES = {"prophet": "expense_forecast_prophet.joblib"}


def get_job(job_id: str) -> TrainingJob | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def list_jobs(limit: int = 10) -> list[dict[str, Any]]:
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.started_at or "", reverse=True)
    return [j.to_dict() for j in jobs[:limit]]


def _run_job(job: TrainingJob) -> None:
    job.status = "running"
    job.started_at = datetime.now(timezone.utc).isoformat()
    job.progress = 5.0

    def emit(msg: str) -> None:
        job.log("info", msg)
        job.progress = min(95.0, job.progress + 10)

    try:
        result = run_training_pipeline(promote=True, log=emit)
        reload_models()
        job.metrics = result
        job.status = "completed"
        job.progress = 100.0
        job.log("info", f"Training complete — {result['trained_users']} users")
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.log("error", str(exc))
    finally:
        job.finished_at = datetime.now(timezone.utc).isoformat()


def start_training_job(models: list[str] | None = None, dataset_id: str | None = None) -> str:
    """Start async DB training (dataset_id ignored — always uses Supabase)."""
    _ = models, dataset_id
    job_id = str(uuid.uuid4())[:8]
    job = TrainingJob(job_id=job_id)
    with _jobs_lock:
        _jobs[job_id] = job
    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()
    return job_id


def run_training_sync() -> dict[str, Any]:
    """Synchronous train + promote + upload + reload (cron / scripts)."""
    result = run_training_pipeline(promote=True)
    reload_models(force_storage_sync=False)
    return result


# Stubs for admin routes that referenced CSV datasets
STAGING_DIR = STAGING_BUNDLE_PATH.parent


def list_datasets() -> list[dict[str, Any]]:
    return [
        {
            "id": "database",
            "label": "Supabase (production)",
            "rows": None,
            "users": None,
            "is_default": True,
        }
    ]


def save_uploaded_dataset(*_args, **_kwargs) -> dict[str, Any]:
    raise ValueError("CSV upload training is disabled. Models train from the database only.")


def deploy_staging_models(models: list[str] | None = None) -> dict[str, Any]:
    from app.services.prophet_training_service import promote_staging_to_production

    _ = models
    manifest = promote_staging_to_production()
    loaded = reload_models()
    return {"deployed": [MODEL_FILES["prophet"]], "loaded": loaded, "manifest": manifest}


def list_trained_runs(limit: int = 20) -> list[dict[str, Any]]:
    runs = []
    if PRODUCTION_BUNDLE_PATH.is_file():
        runs.append(
            {
                "run_id": "production:prophet",
                "source": "production",
                "model_type": "prophet",
                "status": "completed",
                "label": "Production Prophet (per user)",
                "evaluable": False,
            }
        )
    if STAGING_BUNDLE_PATH.is_file():
        runs.append(
            {
                "run_id": "staging:prophet",
                "source": "staging",
                "model_type": "prophet",
                "status": "completed",
                "label": "Staging Prophet",
                "evaluable": False,
            }
        )
    runs.extend(list_jobs(limit))
    return runs[:limit]


def get_evaluation_data(run_id: str, dataset_id: str | None = None) -> dict[str, Any]:
    _ = dataset_id
    raise ValueError(f"Evaluation curves are not available for run {run_id}")
