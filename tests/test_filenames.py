import pytest

from offer_agent.filenames import (
    BUSINESS_UNIT_MISSING,
    CANDIDATE_NAME_MISSING,
    FilenameConflictError,
    resolve_filenames,
)


def test_basic_filename():
    plan = resolve_filenames("Jane Doe", "PureHealth", "42", exists_check=lambda name: False)
    assert plan.docx_filename == "Jane Doe - PureHealth - Employment Contract.docx"
    assert plan.pdf_filename == "Jane Doe - PureHealth - Employment Contract.pdf"
    assert not plan.used_reference_suffix
    assert not plan.warnings


def test_missing_name_and_business_unit_use_placeholders_and_warn():
    plan = resolve_filenames(None, None, "07", exists_check=lambda name: False)
    assert CANDIDATE_NAME_MISSING in plan.docx_filename
    assert BUSINESS_UNIT_MISSING in plan.docx_filename
    assert len(plan.warnings) == 2


def test_conflict_appends_reference(tmp_path):
    existing = {"Jane Doe - PureHealth - Employment Contract.docx"}
    plan = resolve_filenames("Jane Doe", "PureHealth", "42", exists_check=lambda name: name in existing)
    assert plan.used_reference_suffix
    assert plan.docx_filename == "Jane Doe - PureHealth - Employment Contract - 42.docx"
    assert plan.pdf_filename == "Jane Doe - PureHealth - Employment Contract - 42.pdf"


def test_double_conflict_raises_and_never_regenerates_reference():
    existing = {
        "Jane Doe - PureHealth - Employment Contract.docx",
        "Jane Doe - PureHealth - Employment Contract - 42.docx",
    }
    with pytest.raises(FilenameConflictError):
        resolve_filenames("Jane Doe", "PureHealth", "42", exists_check=lambda name: name in existing)


def test_invalid_characters_are_stripped():
    plan = resolve_filenames('Jane "The Best" Doe/Smith', "PureHealth", "01", exists_check=lambda name: False)
    assert "/" not in plan.docx_filename
    assert '"' not in plan.docx_filename
