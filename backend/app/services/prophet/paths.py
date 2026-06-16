"""Filesystem paths for Prophet model artifacts."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
MODELS_DIR = PROJECT_ROOT / "models" / "prophet"
STAGING_DIR = MODELS_DIR / "staging"
PRODUCTION_DIR = MODELS_DIR / "production"
RUNS_DIR = MODELS_DIR / "runs"

BUNDLE_FILENAME = "expense_forecast_prophet.joblib"
STAGING_BUNDLE_PATH = STAGING_DIR / BUNDLE_FILENAME
PRODUCTION_BUNDLE_PATH = PRODUCTION_DIR / BUNDLE_FILENAME
PRODUCTION_MANIFEST_PATH = PRODUCTION_DIR / "manifest.json"
TRAINING_METADATA_PATH = PRODUCTION_DIR / "training_metadata.json"

MODEL_ID = "prophet"
