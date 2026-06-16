"""Storage upload/download helpers for forecast models."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from app.services.prophet import storage as storage_mod


def test_upload_production_artifacts_calls_storage(monkeypatch, tmp_path):
    bundle = tmp_path / "expense_forecast_prophet.joblib"
    manifest = tmp_path / "manifest.json"
    bundle.write_bytes(b"fake-model")
    manifest.write_text(json.dumps({"trained_at": "2026-01-01T00:00:00Z"}), encoding="utf-8")

    mock_storage = MagicMock()
    mock_client = MagicMock()
    mock_client.storage.from_.return_value = mock_storage
    monkeypatch.setattr(storage_mod, "_storage_client", lambda: mock_client)
    monkeypatch.setattr(storage_mod, "ensure_forecast_bucket", lambda: "forecast-models")

    refs = storage_mod.upload_production_artifacts(bundle_path=bundle, manifest_path=manifest)
    assert refs["bucket"] == "forecast-models"
    assert mock_storage.upload.call_count == 2


def test_download_production_artifacts_writes_local(monkeypatch, tmp_path):
    bundle = tmp_path / "expense_forecast_prophet.joblib"
    manifest = tmp_path / "manifest.json"

    mock_storage = MagicMock()
    mock_storage.download.side_effect = [
        b"model-bytes",
        json.dumps({"trained_at": "2026-01-02"}).encode("utf-8"),
    ]
    mock_client = MagicMock()
    mock_client.storage.from_.return_value = mock_storage
    monkeypatch.setattr(storage_mod, "_storage_client", lambda: mock_client)

    result = storage_mod.download_production_artifacts(bundle_path=bundle, manifest_path=manifest)
    assert bundle.read_bytes() == b"model-bytes"
    assert result["manifest"]["trained_at"] == "2026-01-02"
