from pathlib import Path

import pytest

from offer_agent.models import ConflictOption, FieldConflict, FieldValue, ResolvedOffer
from offer_agent.reference import ReferenceStore
from offer_agent.storage import LocalDevStorageBackend, NotConfiguredStorageBackend, StorageError
from offer_agent.validation import validate_offer
from offer_agent.workflow import (
    ERR_FILENAME_CONFLICT,
    ERR_VALIDATION_FAILED,
    finalize_offer,
    format_completion_output,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _complete_offer(offer_id="offer-1", business_unit="PureHealth", total_salary="20500"):
    return ResolvedOffer(
        offer_id=offer_id,
        business_unit_raw=business_unit,
        fields={
            "candidate full name": FieldValue("Jane Marie Doe", "cv"),
            "candidate phone number": FieldValue("+971500000000", "cv"),
            "candidate email address": FieldValue("jane@example.com", "cv"),
            "candidate first name": FieldValue("Jane", "calculation"),
            "job title": FieldValue("Software Engineer", "hiring_approval"),
            "nationality": FieldValue("Canadian", "cv"),
            "line manager": FieldValue("John Smith", "hiring_approval"),
            "department": FieldValue("Engineering", "hiring_approval"),
            "notice period": FieldValue("30", "hiring_approval"),
            "Total Salary": FieldValue(total_salary, "hiring_approval"),
        },
        input_filenames=["hiring_approval.pdf", "cv.pdf"],
    )


@pytest.mark.slow
def test_finalize_offer_end_to_end(tmp_path):
    resolved = _complete_offer(offer_id="offer-e2e")
    storage = LocalDevStorageBackend(tmp_path / "storage")
    reference_store = ReferenceStore(tmp_path / "refs.json")
    audit_log = tmp_path / "audit.jsonl"

    outcome = finalize_offer(
        resolved,
        templates_dir=TEMPLATES_DIR,
        reference_store=reference_store,
        storage=storage,
        audit_log_path=audit_log,
        requested_by="hr@example.com",
    )

    assert outcome.success, outcome.error_message
    assert len(outcome.reference) == 2
    assert outcome.docx_filename == "Jane Marie Doe - PureHealth - Employment Contract.docx"
    assert outcome.pdf_filename == "Jane Marie Doe - PureHealth - Employment Contract.pdf"
    assert outcome.docx_secure_url is not None
    assert outcome.pdf_secure_url is not None
    assert not outcome.unresolved_placeholders
    assert outcome.audit_status == "Recorded"
    assert audit_log.exists()

    text = format_completion_output(outcome)
    assert "Status: Employment contract created" in text
    assert outcome.reference in text
    assert "VALUE[" not in text


@pytest.mark.slow
def test_retry_reuses_same_reference(tmp_path):
    resolved = _complete_offer(offer_id="offer-retry")
    storage_dir = tmp_path / "storage"
    reference_store = ReferenceStore(tmp_path / "refs.json")
    audit_log = tmp_path / "audit.jsonl"

    outcome1 = finalize_offer(
        resolved,
        templates_dir=TEMPLATES_DIR,
        reference_store=reference_store,
        storage=LocalDevStorageBackend(storage_dir),
        audit_log_path=audit_log,
        requested_by="hr@example.com",
    )
    assert outcome1.success

    # Simulate a retry for the SAME approved offer (e.g. after a transient
    # failure) with a fresh storage backend pointed elsewhere; the
    # reference must be reused, never regenerated.
    outcome2 = finalize_offer(
        resolved,
        templates_dir=TEMPLATES_DIR,
        reference_store=reference_store,
        storage=LocalDevStorageBackend(tmp_path / "storage2"),
        audit_log_path=audit_log,
        requested_by="hr@example.com",
    )
    assert outcome2.success
    assert outcome1.reference == outcome2.reference


def test_missing_mandatory_fields_block_finalize(tmp_path):
    resolved = ResolvedOffer(
        offer_id="offer-incomplete",
        business_unit_raw="PureHealth",
        fields={
            "candidate full name": FieldValue("Jane Doe", "cv"),
        },
    )
    outcome = finalize_offer(
        resolved,
        templates_dir=TEMPLATES_DIR,
        reference_store=ReferenceStore(tmp_path / "refs.json"),
        storage=LocalDevStorageBackend(tmp_path / "storage"),
        audit_log_path=tmp_path / "audit.jsonl",
        requested_by="hr@example.com",
    )
    assert outcome.status == "blocked"
    assert outcome.error_code == ERR_VALIDATION_FAILED
    assert outcome.reference is None  # no reference generated for a blocked offer


def test_conflicts_block_finalize(tmp_path):
    resolved = _complete_offer(offer_id="offer-conflict")
    resolved.conflicts = [
        FieldConflict(
            field="job title",
            options=[
                ConflictOption("Software Engineer", "hiring_approval"),
                ConflictOption("Senior Software Engineer", "user"),
            ],
        )
    ]
    outcome = finalize_offer(
        resolved,
        templates_dir=TEMPLATES_DIR,
        reference_store=ReferenceStore(tmp_path / "refs.json"),
        storage=LocalDevStorageBackend(tmp_path / "storage"),
        audit_log_path=tmp_path / "audit.jsonl",
        requested_by="hr@example.com",
    )
    assert outcome.status == "blocked"


def test_unresolved_notice_period_is_retained_and_disclosed(tmp_path):
    resolved = _complete_offer(offer_id="offer-unresolved")
    resolved.fields["notice period"] = FieldValue(None, "confirmed_unavailable", confirmed_unavailable=True)

    outcome = finalize_offer(
        resolved,
        templates_dir=TEMPLATES_DIR,
        reference_store=ReferenceStore(tmp_path / "refs.json"),
        storage=LocalDevStorageBackend(tmp_path / "storage"),
        audit_log_path=tmp_path / "audit.jsonl",
        requested_by="hr@example.com",
    )
    assert outcome.success
    assert outcome.unresolved_placeholders == ["{{notice period}}"]


def test_not_configured_storage_backend_stops_with_storage_error(tmp_path):
    resolved = _complete_offer(offer_id="offer-nostorage")
    outcome = finalize_offer(
        resolved,
        templates_dir=TEMPLATES_DIR,
        reference_store=ReferenceStore(tmp_path / "refs.json"),
        storage=NotConfiguredStorageBackend(),
        audit_log_path=tmp_path / "audit.jsonl",
        requested_by="hr@example.com",
    )
    assert outcome.status == "error"


def test_business_unit_not_inferred_when_missing(tmp_path):
    resolved = _complete_offer(offer_id="offer-no-bu", business_unit=None)
    validation = validate_offer(resolved)
    assert validation.business_unit_missing_or_unrecognized
    assert not validation.can_finalize
