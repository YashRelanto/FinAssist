"""Admin-facing training jobs — global Prophet model from the database."""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.forecast_service import reload_models
from app.services.prophet_training_service import (
    PRODUCTION_BUNDLE_PATH,
    PRODUCTION_MANIFEST_PATH,
    STAGING_BUNDLE_PATH,
    run_training_pipeline,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = PROJECT_ROOT / "models" / "runs"
PRODUCTION_JOB_ID = "production"


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


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.started_at or "", reverse=True)
    return [j.to_dict() for j in jobs[:limit]]


def _run_dir(job_id: str) -> Path:
    return RUNS_DIR / job_id


def _run_bundle_path(job_id: str) -> Path:
    return _run_dir(job_id) / MODEL_FILES["prophet"]


def _load_disk_run_manifest(job_id: str) -> dict[str, Any] | None:
    manifest_path = _run_dir(job_id) / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _persist_job_artifacts(job: TrainingJob, result: dict[str, Any]) -> None:
    run_dir = _run_dir(job.job_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    if PRODUCTION_BUNDLE_PATH.is_file():
        shutil.copy2(PRODUCTION_BUNDLE_PATH, _run_bundle_path(job.job_id))
    manifest = {
        "job_id": job.job_id,
        "model_type": "prophet",
        "status": "completed",
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        **result,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def _production_run_metrics() -> dict[str, Any]:
    if PRODUCTION_MANIFEST_PATH.is_file():
        try:
            manifest = json.loads(PRODUCTION_MANIFEST_PATH.read_text(encoding="utf-8"))
            return {
                "job_id": PRODUCTION_JOB_ID,
                "model_type": "prophet",
                "status": "completed",
                "label": "Current production",
                **manifest,
            }
        except Exception:
            pass
    if PRODUCTION_BUNDLE_PATH.is_file():
        stat = PRODUCTION_BUNDLE_PATH.stat()
        return {
            "job_id": PRODUCTION_JOB_ID,
            "model_type": "prophet",
            "status": "completed",
            "label": "Current production",
            "trained_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
    raise ValueError("No production model available")


def _run_summary_from_job(job: TrainingJob) -> dict[str, Any]:
    bundle_path = _run_bundle_path(job.job_id)
    return {
        "job_id": job.job_id,
        "model_type": "prophet",
        "status": job.status,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "test_mape": job.metrics.get("test_mape"),
        "trained_users": job.metrics.get("trained_users"),
        "trained_at": job.metrics.get("trained_at"),
        "deployable": job.status == "completed"
        and (bundle_path.is_file() or PRODUCTION_BUNDLE_PATH.is_file()),
    }


def _run_summary_from_disk(job_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    bundle_path = _run_bundle_path(job_id)
    return {
        "job_id": job_id,
        "model_type": manifest.get("model_type", "prophet"),
        "status": manifest.get("status", "completed"),
        "started_at": manifest.get("started_at"),
        "finished_at": manifest.get("finished_at"),
        "test_mape": manifest.get("test_mape"),
        "trained_users": manifest.get("trained_users"),
        "trained_at": manifest.get("trained_at"),
        "deployable": bundle_path.is_file(),
    }


def list_train_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Training runs keyed by job_id for admin overview / deploy selectors."""
    seen: set[str] = set()
    runs: list[dict[str, Any]] = []

    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.started_at or "", reverse=True)
    for job in jobs:
        seen.add(job.job_id)
        runs.append(_run_summary_from_job(job))

    if RUNS_DIR.is_dir():
        disk_dirs = sorted(
            (p for p in RUNS_DIR.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for run_path in disk_dirs:
            job_id = run_path.name
            if job_id in seen:
                continue
            manifest = _load_disk_run_manifest(job_id)
            if manifest:
                runs.append(_run_summary_from_disk(job_id, manifest))
            elif _run_bundle_path(job_id).is_file():
                runs.append(
                    {
                        "job_id": job_id,
                        "model_type": "prophet",
                        "status": "completed",
                        "deployable": True,
                    }
                )

    if PRODUCTION_BUNDLE_PATH.is_file() and PRODUCTION_JOB_ID not in seen:
        try:
            prod = _production_run_metrics()
            runs.append(
                {
                    "job_id": PRODUCTION_JOB_ID,
                    "model_type": "prophet",
                    "status": "completed",
                    "started_at": prod.get("trained_at"),
                    "finished_at": prod.get("trained_at"),
                    "test_mape": prod.get("test_mape"),
                    "trained_users": prod.get("trained_users"),
                    "trained_at": prod.get("trained_at"),
                    "deployable": False,
                    "label": prod.get("label"),
                }
            )
        except ValueError:
            pass

    runs.sort(key=lambda r: r.get("finished_at") or r.get("started_at") or "", reverse=True)
    return runs[:limit]


def get_run_metrics(job_id: str) -> dict[str, Any]:
    if job_id == PRODUCTION_JOB_ID:
        return _production_run_metrics()

    job = get_job(job_id)
    if job:
        return {
            "job_id": job_id,
            "model_type": "prophet",
            "status": job.status,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "error": job.error,
            **job.metrics,
        }

    manifest = _load_disk_run_manifest(job_id)
    if manifest:
        return manifest

    raise ValueError(f"Training run not found: {job_id}")


def get_job_details(job_id: str) -> dict[str, Any] | None:
    job = get_job(job_id)
    if job:
        return job.to_dict()

    if job_id == PRODUCTION_JOB_ID:
        metrics = _production_run_metrics()
        return {
            "job_id": PRODUCTION_JOB_ID,
            "status": "completed",
            "progress": 100.0,
            "logs": [],
            "metrics": metrics,
            "error": None,
            "started_at": metrics.get("trained_at"),
            "finished_at": metrics.get("trained_at"),
        }

    manifest = _load_disk_run_manifest(job_id)
    if not manifest:
        return None

    metric_keys = {
        "trained_users",
        "test_mape",
        "trained_at",
        "staging_path",
        "production_path",
        "manifest",
        "storage",
    }
    return {
        "job_id": job_id,
        "status": manifest.get("status", "completed"),
        "progress": 100.0,
        "logs": [],
        "metrics": {k: manifest[k] for k in metric_keys if k in manifest},
        "error": manifest.get("error"),
        "started_at": manifest.get("started_at"),
        "finished_at": manifest.get("finished_at"),
    }


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
        _persist_job_artifacts(job, result)
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


def deploy_staging_models(
    models: list[str] | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    from app.services.prophet_training_service import promote_staging_to_production

    model_ids = models or list(MODEL_FILES.keys())
    invalid = [m for m in model_ids if m not in MODEL_FILES]
    if invalid:
        raise ValueError(f"Unknown models: {invalid}")

    if job_id:
        if job_id == PRODUCTION_JOB_ID:
            raise ValueError("Production is already deployed")
        bundle_path = _run_bundle_path(job_id)
        if not bundle_path.is_file():
            raise FileNotFoundError(f"No saved model artifact for job {job_id}")
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle_path, STAGING_BUNDLE_PATH)
    elif not STAGING_BUNDLE_PATH.is_file():
        raise FileNotFoundError(f"Staging bundle missing: {STAGING_BUNDLE_PATH}")

    manifest = promote_staging_to_production()
    loaded = reload_models()
    deployed = [MODEL_FILES[m] for m in model_ids]
    return {
        "deployed": deployed,
        "job_id": job_id,
        "models": model_ids,
        "loaded": loaded,
        "manifest": manifest,
    }


def list_trained_runs(limit: int = 50) -> list[dict[str, Any]]:
    return list_train_runs(limit)


def get_evaluation_data(run_id: str, dataset_id: str | None = None) -> dict[str, Any]:
    _ = dataset_id
    if run_id.startswith("job:"):
        job_id = run_id.split(":", 1)[1].split(":", 1)[0]
        return get_run_metrics(job_id)
    return get_run_metrics(run_id)
