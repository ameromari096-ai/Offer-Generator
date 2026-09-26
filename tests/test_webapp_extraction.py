"""Tests for the webapp's document-upload -> auto-fill flow, using the
free, no-API-key regex extractor (webapp.regex_extraction). No mocking
needed here - this is real local logic, no network call.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CV_PATH = Path(
    "/root/.claude/uploads/4a239c4e-e7e3-538f-95a0-da1e1c6cd170/62289f71-Delfim_dos_Santos_CV.pdf"
)
HIRING_APPROVAL_PATH = Path(
    "/root/.claude/uploads/4a239c4e-e7e3-538f-95a0-da1e1c6cd170/"
    "780015c1-Hiring_Approval_-_Delfim_Dos_Santos-_Executive_Director_Commercial_-_PureHealth.msg"
)

pytestmark = pytest.mark.skipif(
    not (CV_PATH.exists() and HIRING_APPROVAL_PATH.exists()),
    reason="sample uploaded documents not present in this environment",
)


@pytest.fixture
def client():
    from webapp.app import app

    app.config["TESTING"] = True
    return app.test_client()


def test_extract_parses_real_documents_and_prefills_form(client):
    with open(HIRING_APPROVAL_PATH, "rb") as f1, open(CV_PATH, "rb") as f2:
        resp = client.post(
            "/extract",
            data={
                "hiring_approval_file": (f1, "approval.msg"),
                "cv_file": (f2, "cv.pdf"),
            },
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Correctly extracted from the hiring approval, not the CV's lowercase variant.
    assert 'value="Delfim Dos Santos"' in html
    # From the CV (phone/email aren't in the hiring approval).
    assert 'value="+971 56 545 4940"' in html
    assert 'value="delfimsantos@live.com"' in html
    assert 'value="Executive Director Commercial"' in html
    assert 'value="Group Chief Commercial Officer"' in html
    assert 'value="90000"' in html  # Proposed Salary, not Previous Salary or the band figures

    # Notice period: only the Contract Terms section's "3 months" counts,
    # converted to days - not the unrelated "1 Month" under Remarks.
    assert 'name="notice_period" id="notice_period" placeholder="e.g. 90" value="90"' in html
    assert "converted from hiring approval" in html

    # Business Unit resolved and auto-selected.
    assert 'value="PureHealth" selected' in html

    # Department: the hiring approval lists both "Division" (Commercial
    # Office) and "Department" (Commercial) as distinct fields - the
    # offer's department must take the "Department" value specifically,
    # not treat the difference from "Division" as a conflict.
    department_match = re.search(r'name="department" id="department" value="([^"]*)"', html)
    assert department_match.group(1) == "Commercial"
    assert "Conflict on" not in html

    # Nationality is never stated anywhere in either document -> must stay blank, never guessed.
    assert 'name="nationality" id="nationality" value=""' in html


def test_extract_requires_at_least_one_document(client):
    resp = client.post("/extract", data={}, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert "Upload at least" in resp.get_data(as_text=True)


def test_extract_handles_a_passport_image_upload_gracefully(client, tmp_path):
    fake_image = tmp_path / "passport.png"
    fake_image.write_bytes(b"\x89PNG\r\n\x1a\nnot a real png but that's fine for this test")

    with open(CV_PATH, "rb") as cv_f, open(fake_image, "rb") as passport_f:
        resp = client.post(
            "/extract",
            data={
                "cv_file": (cv_f, "cv.pdf"),
                "passport_file": (passport_f, "passport.png"),
            },
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "can&#39;t read images" in html or "can't read images" in html
