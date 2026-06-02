from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.admin_auth import require_admin
from app.services.model_monitoring_service import compute_drift_stats, get_production_performance
from app.services.model_training_service import (
    TRAINABLE_MODELS,
    MODEL_FILES,
    STAGING_DIR,
    deploy_staging_models,
    get_evaluation_data,
    get_job_details,
    get_run_metrics,
    list_datasets,
    list_jobs,
    list_train_runs,
    run_training_sync,
    save_uploaded_dataset,
    start_training_job,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class TrainRequest(BaseModel):
    models: list[str] = Field(default_factory=lambda: ["prophet"])
    dataset_id: str = "database"


class DeployRequest(BaseModel):
    job_id: str | None = Field(
        default=None,
        description="Training job id whose saved artifact should be promoted to production.",
    )
    models: list[str] | None = Field(
        default_factory=lambda: ["prophet"],
        description="Which model types to deploy from the selected run.",
    )


@router.get("/overview")
async def admin_overview(
    job_id: str | None = Query(default=None, description="Training job id to inspect"),
    _user=Depends(require_admin),
):
    drift = compute_drift_stats()
    if job_id:
        try:
            run = get_run_metrics(job_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"success": True, "run": run, "drift": drift}

    performance = get_production_performance()
    return {"success": True, "performance": performance, "drift": drift}


@router.get("/drift")
async def admin_drift(_user=Depends(require_admin)):
    return {"success": True, "drift": compute_drift_stats()}


@router.get("/performance")
async def admin_performance(_user=Depends(require_admin)):
    return {"success": True, "performance": get_production_performance()}


@router.get("/datasets")
async def admin_list_datasets(_user=Depends(require_admin)):
    return {"success": True, "datasets": list_datasets()}


@router.post("/dataset/upload")
async def admin_upload_dataset(
    transactions: UploadFile = File(..., description="transactions.csv"),
    categories: UploadFile | None = File(None, description="Optional categories.csv"),
    _user=Depends(require_admin),
):
    if not transactions.filename or not transactions.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="transactions file must be a .csv")

    tx_bytes = await transactions.read()
    cat_bytes = None
    cat_name = None
    if categories and categories.filename:
        if not categories.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="categories file must be a .csv")
        cat_bytes = await categories.read()
        cat_name = categories.filename

    try:
        meta = save_uploaded_dataset(tx_bytes, transactions.filename, cat_bytes, cat_name)
        return {"success": True, "dataset": meta}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/train-from-db")
async def admin_train_from_db_sync(_user=Depends(require_admin)):
    """Train per-user Prophet models from Supabase and promote to production (blocking)."""
    try:
        result = run_training_sync()
        return {"success": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/train")
async def admin_start_train(body: TrainRequest, _user=Depends(require_admin)):
    invalid = [m for m in body.models if m not in TRAINABLE_MODELS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid models: {invalid}. Use: {list(TRAINABLE_MODELS)}",
        )
    if not body.models:
        raise HTTPException(status_code=400, detail="Select at least one model to train")
    try:
        job_id = start_training_job(models=body.models, dataset_id=body.dataset_id)
        return {"success": True, "job_id": job_id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/train/jobs")
async def admin_list_jobs(_user=Depends(require_admin)):
    return {"success": True, "jobs": list_jobs()}


@router.get("/train/runs")
async def admin_list_trained_runs(_user=Depends(require_admin)):
    return {"success": True, "runs": list_train_runs()}


@router.get("/train/{job_id}")
async def admin_train_status(job_id: str, _user=Depends(require_admin)):
    details = get_job_details(job_id)
    if not details:
        raise HTTPException(status_code=404, detail="Training job not found")
    return {"success": True, **details}


@router.get("/staging")
async def admin_list_staged(_user=Depends(require_admin)):
    """Return which models are currently available in the staging directory."""
    staged = []
    for model_id, filename in MODEL_FILES.items():
        path = STAGING_DIR / filename
        if path.is_file():
            staged.append({"id": model_id, "filename": filename})
    return {"success": True, "staged": staged}


@router.post("/deploy")
async def admin_deploy(body: DeployRequest = DeployRequest(), _user=Depends(require_admin)):
    try:
        result = deploy_staging_models(models=body.models, job_id=body.job_id)
        return {"success": True, **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/evaluation")
async def admin_evaluation(
    run_id: str = Query(..., description="e.g. job:abc12345:gradient_boosting"),
    dataset_id: str | None = Query(default=None),
    _user=Depends(require_admin),
):
    try:
        data = get_evaluation_data(run_id=run_id, dataset_id=dataset_id)
        return {"success": True, "evaluation": data}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
