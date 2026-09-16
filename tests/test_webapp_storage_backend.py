"""The /approve route must use whichever StorageBackend is configured
via app.config["STORAGE_BACKEND_FACTORY"] (how the desktop app switches
to SharePoint) - not a hardcoded LocalDevStorageBackend - and the result
page must link straight to a remote secure_url instead of assuming a
local copy exists to serve back through our own /download route.
"""

import html as html_module
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from offer_agent.storage import StoredFile


class FakeRemoteStorageBackend:
    """Stands in for SharePoint/Drive: never writes to local disk."""

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
def app_with_restored_storage_config():
    from webapp.app import app

    original_factory = app.config.get("STORAGE_BACKEND_FACTORY")
    original_label = app.config.get("STORAGE_LABEL")
    yield app
    if original_factory is not None:
        app.config["STORAGE_BACKEND_FACTORY"] = original_factory
    if original_label is not None:
        app.config["STORAGE_LABEL"] = original_label


def _extract_offer_json(preview_html: str) -> str:
    match = re.search(r"name=\"offer_json\" value='([^']*)'", preview_html)
    return html_module.unescape(match.group(1))


def test_approve_uses_the_configured_backend_not_a_hardcoded_local_one(app_with_restored_storage_config):
    app = app_with_restored_storage_config
    fake_backend = FakeRemoteStorageBackend()
    app.config["STORAGE_BACKEND_FACTORY"] = lambda: fake_backend
    app.config["STORAGE_LABEL"] = "sharepoint"

    client = app.test_client()
    preview_resp = client.post(
        "/preview",
        data={
            "business_unit": "PureHealth",
            "candidate_full_name": "Test Approve User",
            "candidate_phone": "+971500000000",
            "candidate_email": "test@example.com",
            "nationality": "British",
            "job_title": "Engineer",
            "line_manager": "Manager",
            "department": "Engineering",
            "notice_period": "30",
            "total_salary": "20000",
        },
    )
    assert preview_resp.status_code == 200
    offer_json = _extract_offer_json(preview_resp.get_data(as_text=True))

    approve_resp = client.post("/approve", data={"offer_json": offer_json})
    assert approve_resp.status_code == 200
    result_html = approve_resp.get_data(as_text=True)

    # The fake backend actually received the save() calls - proves the
    # factory override, not LocalDevStorageBackend, was used.
    assert len(fake_backend.saved_filenames) == 2  # docx + pdf

    # Remote secure_url is linked directly, not routed through our own
    # /download endpoint (which would 404 - nothing was written locally).
    assert "https://fake.example/" in result_html
    assert "Open Word (online)" in result_html
    assert "Open PDF (online)" in result_html
    assert "/download/" not in result_html


def test_local_backend_still_uses_the_download_route(app_with_restored_storage_config):
    """Default (unconfigured) behavior must be unchanged."""
    app = app_with_restored_storage_config
    # Explicitly reset to the real default in case another test left an override.
    from offer_agent.storage import LocalDevStorageBackend
    from webapp.app import STORAGE_DIR

    app.config["STORAGE_BACKEND_FACTORY"] = lambda: LocalDevStorageBackend(STORAGE_DIR)
    app.config["STORAGE_LABEL"] = "local"

    client = app.test_client()
    preview_resp = client.post(
        "/preview",
        data={
            "business_unit": "PureHealth",
            "candidate_full_name": "Test Local User",
            "candidate_phone": "+971500000001",
            "candidate_email": "test2@example.com",
            "nationality": "British",
            "job_title": "Engineer",
            "line_manager": "Manager",
            "department": "Engineering",
            "notice_period": "30",
            "total_salary": "20000",
        },
    )
    offer_json = _extract_offer_json(preview_resp.get_data(as_text=True))

    approve_resp = client.post("/approve", data={"offer_json": offer_json})
    result_html = approve_resp.get_data(as_text=True)

    assert "/download/" in result_html
    assert "Download Word" in result_html
    assert "local filesystem on this computer" in result_html
