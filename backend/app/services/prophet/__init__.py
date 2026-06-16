"""Prophet expense forecasting package."""

from app.services.prophet.features import (
    MIN_HISTORY_DAYS,
    MIN_MONTHS_FOR_FORECAST,
    MIN_MONTHS_FOR_PROPHET_USER,
    prepare_global_training_expenses,
)
from app.services.prophet.inference import (
    generate_forecast,
    get_model_status,
    get_production_manifest,
    model_is_loaded,
    reload_models,
)
from app.services.prophet.jobs import (
    MODEL_FILES,
    STAGING_DIR,
    TRAINABLE_MODELS,
    deploy_staging_models,
    get_evaluation_data,
    get_job_details,
    get_run_metrics,
    get_training_dataset_for_run,
    list_datasets,
    list_jobs,
    list_train_runs,
    run_training_sync,
    start_training_job,
)
from app.services.prophet.monitoring import compute_drift_stats, get_production_performance
from app.services.prophet.paths import (
    BUNDLE_FILENAME,
    MODEL_ID,
    PRODUCTION_BUNDLE_PATH,
    PRODUCTION_DIR,
    PRODUCTION_MANIFEST_PATH,
    RUNS_DIR,
    STAGING_BUNDLE_PATH,
)
from app.services.prophet.storage import sync_production_from_storage, upload_production_artifacts
from app.services.prophet.training import (
    fetch_expense_transactions_from_db,
    finalize_production_deployment,
    run_training_pipeline,
    train_bundle,
    train_from_dataframe,
)

__all__ = [
    "BUNDLE_FILENAME",
    "MIN_HISTORY_DAYS",
    "MIN_MONTHS_FOR_FORECAST",
    "MIN_MONTHS_FOR_PROPHET_USER",
    "MODEL_FILES",
    "MODEL_ID",
    "PRODUCTION_BUNDLE_PATH",
    "PRODUCTION_DIR",
    "PRODUCTION_MANIFEST_PATH",
    "RUNS_DIR",
    "STAGING_BUNDLE_PATH",
    "STAGING_DIR",
    "TRAINABLE_MODELS",
    "compute_drift_stats",
    "deploy_staging_models",
    "fetch_expense_transactions_from_db",
    "finalize_production_deployment",
    "generate_forecast",
    "get_evaluation_data",
    "get_job_details",
    "get_model_status",
    "get_production_manifest",
    "get_production_performance",
    "get_run_metrics",
    "get_training_dataset_for_run",
    "list_datasets",
    "list_jobs",
    "list_train_runs",
    "model_is_loaded",
    "prepare_global_training_expenses",
    "reload_models",
    "run_training_pipeline",
    "run_training_sync",
    "start_training_job",
    "sync_production_from_storage",
    "train_bundle",
    "train_from_dataframe",
    "upload_production_artifacts",
]
