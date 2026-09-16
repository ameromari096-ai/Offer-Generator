"""The /api/* JSON routes exist for non-browser callers (a Power Apps
canvas app calling through a custom connector) and must:
- refuse to serve at all when OFFER_AGENT_API_KEY isn't configured (fail closed),
- require a matching X-API-Key header otherwise,
- drive the exact same engine (validate_offer / finalize_offer) as the HTML routes,
- honor whichever StorageBackend app.config["STORAGE_BACKEND_FACTORY"] provides.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from offer_agent.storage import StoredFile


class FakeRemoteStorageBackend:
    def __init__(self):
        self.saved_filenames = []

    def exists(self, filename):
        return False

    def save(self, local_path, filename):
        self.saved_filenames.append(filename)
        return StoredFile(
            filename=filename,
            secure_url=f"https://fake.example/{filename}",
            destination_id="fake-drive",
        )

    def destination_identifier(self):
        return "fake:test-destination"


@pytest.fixture
def app_with_restored_config(monkeypatch):
    from webapp.app import app

    monkeypatch.setenv("OFFER_AGENT_API_KEY", "test-key-123")
    original_factory = app.config.get("STORAGE_BACKEND_FACTORY")
    original_label = app.config.get("STORAGE_LABEL")
    yield app
    if original_factory is not None:
        app.config["STORAGE_BACKEND_FACTORY"] = original_factory
    if original_label is not None:
        app.config["STORAGE_LABEL"] = original_label


def _valid_fields():
    return {
        "fields": {
            "candidate_full_name": "Test API User",
            "candidate_phone": "+971500000000",
            "candidate_email": "test@example.com",
            "nationality": "British",
            "job_title": "Engineer",
            "line_manager": "Manager",
            "department": "Engineering",
            "notice_period": "30",
            "total_salary": "20000",
        },
        "business_unit": "PureHealth",
        "requested_by": "hr@purehealth.ae",
    }


def test_api_disabled_without_env_var(app_with_restored_config, monkeypatch):
    app = app_with_restored_config
    monkeypatch.delenv("OFFER_AGENT_API_KEY", raising=False)
    client = app.test_client()
    resp = client.post("/api/preview", json=_valid_fields())
    assert resp.status_code == 503


def test_api_rejects_missing_or_wrong_key(app_with_restored_config):
    app = app_with_restored_config
    client = app.test_client()

    resp = client.post("/api/preview", json=_valid_fields())
    assert resp.status_code == 401

    resp = client.post("/api/preview", json=_valid_fields(), headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_preview_then_approve_with_remote_backend(app_with_restored_config):
    app = app_with_restored_config
    fake_backend = FakeRemoteStorageBackend()
    app.config["STORAGE_BACKEND_FACTORY"] = lambda: fake_backend
    app.config["STORAGE_LABEL"] = "sharepoint"

    client = app.test_client()
    headers = {"X-API-Key": "test-key-123"}

    preview_resp = client.post("/api/preview", json=_valid_fields(), headers=headers)
    assert preview_resp.status_code == 200
    preview_data = preview_resp.get_json()
    assert preview_data["can_finalize"] is True
    offer_token = preview_data["offer_token"]

    approve_resp = client.post("/api/approve", json={"offer_token": offer_token}, headers=headers)
    assert approve_resp.status_code == 200
    approve_data = approve_resp.get_json()
    assert approve_data["status"] == "created"
    assert approve_data["docx_url"].startswith("https://fake.example/")
    assert approve_data["pdf_url"].startswith("https://fake.example/")
    assert len(fake_backend.saved_filenames) == 2


def test_preview_reports_missing_fields(app_with_restored_config):
    app = app_with_restored_config
    client = app.test_client()
    headers = {"X-API-Key": "test-key-123"}

    resp = client.post("/api/preview", json={"fields": {}, "business_unit": None}, headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["can_finalize"] is False
    assert "candidate full name" in data["missing_fields"]


def test_approve_local_backend_returns_download_url(app_with_restored_config):
    from offer_agent.storage import LocalDevStorageBackend
    from webapp.paths import STORAGE_DIR

    app = app_with_restored_config
    app.config["STORAGE_BACKEND_FACTORY"] = lambda: LocalDevStorageBackend(STORAGE_DIR)
    app.config["STORAGE_LABEL"] = "local"

    client = app.test_client()
    headers = {"X-API-Key": "test-key-123"}

    preview_resp = client.post("/api/preview", json=_valid_fields(), headers=headers)
    offer_token = preview_resp.get_json()["offer_token"]

    approve_resp = client.post("/api/approve", json={"offer_token": offer_token}, headers=headers)
    data = approve_resp.get_json()
    assert data["status"] == "created"
    assert "/api/download/" in data["docx_url"]
    assert "/api/download/" in data["pdf_url"]


def test_business_units_endpoint(app_with_restored_config):
    app = app_with_restored_config
    client = app.test_client()
    resp = client.get("/api/business-units", headers={"X-API-Key": "test-key-123"})
    assert resp.status_code == 200
    assert "PureHealth" in resp.get_json()["business_units"]
