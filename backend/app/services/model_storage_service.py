"""Upload/download Prophet model artifacts via Supabase Storage."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.prophet_training_service import (
    BUNDLE_FILENAME,
    PRODUCTION_BUNDLE_PATH,
    PRODUCTION_MANIFEST_PATH,
)

logger = logging.getLogger(__name__)

STORAGE_PREFIX_PRODUCTION = "production"
STORAGE_BUNDLE_KEY = f"{STORAGE_PREFIX_PRODUCTION}/{BUNDLE_FILENAME}"
STORAGE_MANIFEST_KEY = f"{STORAGE_PREFIX_PRODUCTION}/manifest.json"


def _storage_client():
    from app.utils.supabase_client import supabase

    if supabase is None:
        raise RuntimeError("Supabase client is not configured")
    return supabase


def ensure_forecast_bucket() -> str:
    """Create the private forecast-models bucket if it does not exist."""
    bucket = settings.FORECAST_STORAGE_BUCKET
    client = _storage_client()
    try:
        buckets = client.storage.list_buckets() or []
        names = set()
        for item in buckets:
            name = getattr(item, "name", None) or (item.get("name") if isinstance(item, dict) else None)
            if name:
                names.add(name)
        if bucket not in names:
            client.storage.create_bucket(bucket, options={"public": False})
            logger.info("Created Supabase Storage bucket: %s", bucket)
    except Exception as exc:
        logger.debug("Bucket ensure: %s", exc)
    return bucket


def upload_production_artifacts(
    *,
    bundle_path: Path = PRODUCTION_BUNDLE_PATH,
    manifest_path: Path = PRODUCTION_MANIFEST_PATH,
) -> dict[str, str]:
    """Publish local production artifacts to Supabase Storage."""
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Production bundle missing: {bundle_path}")

    bucket = ensure_forecast_bucket()
    client = _storage_client()
    storage = client.storage.from_(bucket)

    with bundle_path.open("rb") as handle:
        storage.upload(
            STORAGE_BUNDLE_KEY,
            handle.read(),
            file_options={
                "content-type": "application/octet-stream",
                "upsert": "true",
                "cache-control": "3600",
            },
        )

    manifest_bytes: bytes
    if manifest_path.is_file():
        manifest_bytes = manifest_path.read_bytes()
    else:
        manifest_bytes = json.dumps({"bundle": STORAGE_BUNDLE_KEY}).encode("utf-8")

    storage.upload(
        STORAGE_MANIFEST_KEY,
        manifest_bytes,
        file_options={
            "content-type": "application/json",
            "upsert": "true",
            "cache-control": "60",
        },
    )

    logger.info(
        "Uploaded forecast models to storage://%s/%s",
        bucket,
        STORAGE_BUNDLE_KEY,
    )
    return {
        "bucket": bucket,
        "bundle_key": STORAGE_BUNDLE_KEY,
        "manifest_key": STORAGE_MANIFEST_KEY,
    }


def download_production_artifacts(
    *,
    bundle_path: Path = PRODUCTION_BUNDLE_PATH,
    manifest_path: Path = PRODUCTION_MANIFEST_PATH,
) -> dict[str, Any]:
    """Download production artifacts from Supabase Storage to local cache."""
    bucket = settings.FORECAST_STORAGE_BUCKET
    client = _storage_client()
    storage = client.storage.from_(bucket)

    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    bundle_bytes = storage.download(STORAGE_BUNDLE_KEY)
    tmp = bundle_path.with_suffix(".joblib.tmp")
    tmp.write_bytes(bundle_bytes)
    tmp.replace(bundle_path)

    manifest_info: dict[str, Any] = {}
    try:
        manifest_bytes = storage.download(STORAGE_MANIFEST_KEY)
        manifest_path.write_bytes(manifest_bytes)
        manifest_info = json.loads(manifest_bytes.decode("utf-8"))
    except Exception as exc:
        logger.warning("Manifest download skipped: %s", exc)

    logger.info("Downloaded forecast models from storage://%s/%s", bucket, STORAGE_BUNDLE_KEY)
    return {
        "bucket": bucket,
        "bundle_path": str(bundle_path),
        "manifest": manifest_info,
    }


def storage_manifest() -> dict[str, Any]:
    """Read manifest.json from storage without downloading the full bundle."""
    bucket = settings.FORECAST_STORAGE_BUCKET
    client = _storage_client()
    try:
        raw = client.storage.from_(bucket).download(STORAGE_MANIFEST_KEY)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _is_storage_not_found(exc: Exception) -> bool:
    text = str(exc).lower()
    return "404" in text or "not_found" in text or "object not found" in text


def sync_production_from_storage(force: bool = False) -> bool:
    """
    Download production bundle from storage when local cache is missing or stale.
    Returns True if a download occurred.
    """
    if not settings.FORECAST_STORAGE_ENABLED:
        return False

    remote = storage_manifest()
    if not remote:
        if PRODUCTION_BUNDLE_PATH.is_file():
            logger.debug("No remote forecast manifest; local production bundle present")
        elif force:
            logger.info(
                "No forecast models in Supabase Storage yet; using local bundle if available"
            )
        return False

    local_trained_at = None
    if PRODUCTION_MANIFEST_PATH.is_file():
        try:
            local = json.loads(PRODUCTION_MANIFEST_PATH.read_text(encoding="utf-8"))
            local_trained_at = local.get("trained_at")
        except Exception:
            local_trained_at = None

    remote_trained_at = remote.get("trained_at")
    local_missing = not PRODUCTION_BUNDLE_PATH.is_file()
    stale = (
        remote_trained_at
        and local_trained_at
        and remote_trained_at > local_trained_at
    )

    if not (force or local_missing or stale):
        return False

    try:
        download_production_artifacts()
        return True
    except Exception as exc:
        if _is_storage_not_found(exc):
            logger.info(
                "Forecast model not in Supabase Storage yet; using local bundle if available"
            )
        else:
            logger.warning("Storage sync failed: %s", exc)
        return False
