"""Admin training jobs for the Prophet forecast model."""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.prophet.inference import reload_models
from app.services.prophet.paths import (
    BUNDLE_FILENAME,
    MODEL_ID,
    PRODUCTION_BUNDLE_PATH,
    PRODUCTION_MANIFEST_PATH,
    RUNS_DIR,
    STAGING_BUNDLE_PATH,
    STAGING_DIR,
)
from app.services.prophet.training import finalize_production_deployment, run_training_pipeline

PRODUCTION_JOB_ID = "production"
TRAINABLE_MODELS = (MODEL_ID,)
MODEL_FILES = {MODEL_ID: BUNDLE_FILENAME}


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
        with self._lock:
            self.logs.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "level": level,
                    "message": message,
                }
            )

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "job_id": self.job_id,
                "training_mode": MODEL_ID,
                "models": [MODEL_ID],
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


def get_job(job_id: str) -> TrainingJob | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def _run_dir(job_id: str) -> Path:
    return RUNS_DIR / job_id


def _run_bundle_path(job_id: str) -> Path:
    return _run_dir(job_id) / BUNDLE_FILENAME


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
    if STAGING_BUNDLE_PATH.is_file():
        shutil.copy2(STAGING_BUNDLE_PATH, _run_bundle_path(job.job_id))
    manifest = {
        "job_id": job.job_id,
        "model_type": result.get("model_type", MODEL_ID),
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
                "model_type": MODEL_ID,
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
            "model_type": MODEL_ID,
            "status": "completed",
            "label": "Current production",
            "trained_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
    raise ValueError("No production model available")


def _run_summary(job_id: str, *, status: str, metrics: dict[str, Any], label: str | None = None) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "model_type": metrics.get("model_type", MODEL_ID),
        "status": status,
        "started_at": metrics.get("started_at"),
        "finished_at": metrics.get("finished_at"),
        "test_mape": metrics.get("test_mape"),
        "trained_users": metrics.get("trained_users"),
        "trained_transactions": metrics.get("trained_transactions"),
        "trained_at": metrics.get("trained_at"),
        "deployable": status == "completed" and _run_bundle_path(job_id).is_file(),
        **({"label": label} if label else {}),
    }


def list_train_runs(limit: int = 50) -> list[dict[str, Any]]:
    seen: set[str] = set()
    runs: list[dict[str, Any]] = []

    with _jobs_lock:
        mem_jobs = sorted(_jobs.values(), key=lambda j: j.started_at or "", reverse=True)
    for job in mem_jobs:
        seen.add(job.job_id)
        runs.append(
            _run_summary(
                job.job_id,
                status=job.status,
                metrics={**job.metrics, "started_at": job.started_at, "finished_at": job.finished_at},
            )
        )

    if RUNS_DIR.is_dir():
        for run_path in sorted(RUNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not run_path.is_dir() or run_path.name in seen:
                continue
            manifest = _load_disk_run_manifest(run_path.name)
            if manifest:
                runs.append(_run_summary(run_path.name, status=manifest.get("status", "completed"), metrics=manifest))
            elif _run_bundle_path(run_path.name).is_file():
                runs.append(_run_summary(run_path.name, status="completed", metrics={}))

    if PRODUCTION_BUNDLE_PATH.is_file() and PRODUCTION_JOB_ID not in seen:
        try:
            prod = _production_run_metrics()
            runs.append(
                _run_summary(
                    PRODUCTION_JOB_ID,
                    status="completed",
                    metrics=prod,
                    label=prod.get("label"),
                )
            )
            runs[-1]["deployable"] = False
        except ValueError:
            pass

    runs.sort(key=lambda r: r.get("finished_at") or r.get("started_at") or "", reverse=True)
    return runs[:limit]


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    seen: set[str] = set()
    jobs: list[dict[str, Any]] = []

    with _jobs_lock:
        for job in sorted(_jobs.values(), key=lambda j: j.started_at or "", reverse=True):
            seen.add(job.job_id)
            jobs.append(job.to_dict())

    for run in list_train_runs(limit):
        if run["job_id"] in seen or run["job_id"] == PRODUCTION_JOB_ID:
            continue
        seen.add(run["job_id"])
        jobs.append(
            {
                "job_id": run["job_id"],
                "training_mode": MODEL_ID,
                "models": [MODEL_ID],
                "status": run.get("status", "completed"),
                "progress": 100.0,
                "logs": [],
                "metrics": {
                    k: run[k]
                    for k in ("test_mape", "trained_users", "trained_transactions", "trained_at", "model_type")
                    if k in run
                },
                "error": None,
                "started_at": run.get("started_at"),
                "finished_at": run.get("finished_at"),
            }
        )

    jobs.sort(key=lambda j: j.get("started_at") or j.get("finished_at") or "", reverse=True)
    return jobs[:limit]


def get_run_metrics(job_id: str) -> dict[str, Any]:
    if job_id == PRODUCTION_JOB_ID:
        return _production_run_metrics()

    job = get_job(job_id)
    if job:
        return {
            "job_id": job_id,
            "model_type": job.metrics.get("model_type", MODEL_ID),
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
        "trained_transactions",
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
        result = run_training_pipeline(promote=False, log=emit)
        job.metrics = result
        job.status = "completed"
        job.progress = 100.0
        _persist_job_artifacts(job, result)
        job.log(
            "info",
            f"Training complete — {result['trained_users']} users, "
            f"MAPE {result.get('test_mape', 0):.1%}. Deploy from Admin to publish.",
        )
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.log("error", str(exc))
    finally:
        job.finished_at = datetime.now(timezone.utc).isoformat()


def start_training_job(models: list[str] | None = None, dataset_id: str | None = None) -> str:
    _ = dataset_id
    if models and MODEL_ID not in models:
        raise ValueError(f"Unknown model: {models}. Use: {list(TRAINABLE_MODELS)}")
    job_id = str(uuid.uuid4())[:8]
    job = TrainingJob(job_id=job_id)
    with _jobs_lock:
        _jobs[job_id] = job
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    return job_id


def run_training_sync() -> dict[str, Any]:
    return run_training_pipeline(promote=False)


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


def get_training_dataset_for_run(job_id: str, *, sample_limit: int = 100) -> dict[str, Any]:
    from app.services.prophet.features import prepare_global_training_expenses
    from app.services.prophet.training import fetch_expense_transactions_from_db

    metrics = get_run_metrics(job_id)
    as_of = metrics.get("trained_at") or metrics.get("finished_at") or metrics.get("started_at")
    if not as_of:
        raise ValueError(f"Training run {job_id} has no trained_at timestamp")

    transactions = fetch_expense_transactions_from_db(as_of=as_of)
    training_pool = prepare_global_training_expenses(transactions)

    sample_rows: list[dict[str, Any]] = []
    if not training_pool.empty:
        preview = training_pool.sort_values("transaction_date", ascending=False).head(sample_limit)
        for _, row in preview.iterrows():
            sample_rows.append(
                {
                    "user_id": str(row["user_id"]),
                    "transaction_date": row["transaction_date"].date().isoformat(),
                    "amount": float(row["amount"]),
                    "transaction_type": "expense",
                }
            )

    return {
        "job_id": job_id,
        "trained_at": as_of,
        "model_type": metrics.get("model_type"),
        "total_expense_rows": int(len(transactions)),
        "training_rows": int(len(training_pool)),
        "training_users": int(training_pool["user_id"].nunique()) if not training_pool.empty else 0,
        "sample": sample_rows,
    }


def deploy_staging_models(models: list[str] | None = None, job_id: str | None = None) -> dict[str, Any]:
    model_ids = models or [MODEL_ID]
    if any(m not in MODEL_FILES for m in model_ids):
        raise ValueError(f"Unknown models: {model_ids}")

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

    deployed = finalize_production_deployment()
    loaded = reload_models()
    return {
        "deployed": [MODEL_FILES[m] for m in model_ids],
        "job_id": job_id,
        "models": model_ids,
        "loaded": loaded,
        **deployed,
    }


def get_evaluation_data(run_id: str, dataset_id: str | None = None) -> dict[str, Any]:
    _ = dataset_id
    if run_id.startswith("job:"):
        run_id = run_id.split(":", 1)[1].split(":", 1)[0]
    return get_run_metrics(run_id)
