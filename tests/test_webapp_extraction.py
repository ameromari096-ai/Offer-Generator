"""Tests for the webapp's document-upload -> auto-fill flow.

These do not call the real Claude API (no network, no API key needed) —
webapp.app.extract_offer_fields is patched with a canned result so we can
verify document parsing (real) and the extraction -> form-prefill mapping
(real) in isolation from the LLM call itself.
"""

import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webapp.llm_extraction import ConflictOption, ExtractedField, ExtractionResult, FieldConflict

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


def _canned_result_with_department_conflict():
    return ExtractionResult(
        business_unit_raw="PureHealth",
        candidate_full_name=ExtractedField(value="Delfim Dos Santos", source="hiring_approval"),
        candidate_first_name=ExtractedField(value="Delfim", source="hiring_approval"),
        candidate_phone_number=ExtractedField(value="+971 56 545 4940", source="cv"),
        candidate_email_address=ExtractedField(value="delfimsantos@live.com", source="cv"),
        nationality=ExtractedField(value=None, source="hiring_approval"),
        job_title=ExtractedField(value="Executive Director Commercial", source="hiring_approval"),
        line_manager=ExtractedField(value="Group Chief Commercial Officer", source="hiring_approval"),
        department=ExtractedField(value=None, source="hiring_approval"),
        notice_period=ExtractedField(value="90", source="hiring_approval"),
        total_salary=ExtractedField(value="90000", source="hiring_approval"),
        conflicts=[
            FieldConflict(
                field="department",
                options=[
                    ConflictOption(value="Commercial Office", source="hiring_approval (Division)"),
                    ConflictOption(value="Commercial", source="hiring_approval (Department)"),
                ],
            )
        ],
        notes=['Notice period: 90 (converted from hiring approval\'s "3 months", months x 30)'],
    )


def test_extract_parses_real_documents_and_prefills_form(client):
    canned = _canned_result_with_department_conflict()
    with patch("webapp.app.extract_offer_fields", return_value=canned) as mock_extract:
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
    call_kwargs = mock_extract.call_args.kwargs
    # Real document parsing ran (not mocked) - the extracted text reached the LLM call.
    assert "Delfim Dos Santos" in call_kwargs["hiring_approval_text"]
    assert "Delfim dos Santos" in call_kwargs["cv_text"]

    html = resp.get_data(as_text=True)
    assert 'value="Delfim Dos Santos"' in html
    assert 'value="+971 56 545 4940"' in html
    assert 'value="90"' in html

    # Business Unit auto-selected since it resolved cleanly.
    assert "PureHealth" in html

    # Department has a conflict -> left blank, not silently guessed.
    department_match = re.search(r'name="department" id="department" value="([^"]*)"', html)
    assert department_match.group(1) == ""
    assert "Conflict on" in html


def test_extract_failure_fails_gracefully_not_a_crash(client):
    with patch("webapp.app.extract_offer_fields", side_effect=RuntimeError("no credentials")):
        with open(CV_PATH, "rb") as f:
            resp = client.post(
                "/extract",
                data={"cv_file": (f, "cv.pdf")},
                content_type="multipart/form-data",
            )
    assert resp.status_code == 200
    assert "Automatic extraction failed" in resp.get_data(as_text=True)


def test_extract_requires_at_least_one_document(client):
    resp = client.post("/extract", data={}, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert "Upload at least" in resp.get_data(as_text=True)
