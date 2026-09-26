"""End-to-end offer generation workflow, run only after explicit approval.

Implements the post-approval sequence from the spec:

1. Set the final creation date.
2. Generate {{Ref}} as one random two-digit number (reusing it on retry).
3. Select the approved template.
4. Populate resolved fields.
5. Retain approved unresolved placeholders.
6. Generate DOCX from the approved Word template.
7. Convert the completed DOCX to PDF.
8. Verify matching values, reference, placeholders.
9. Apply filenames and check conflicts.
10. Save both files through the storage tool.
11. Retrieve authenticated links to both files.
12. Return both files directly when supported.
13. Write the audit record.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import fields as fields_module
from .audit import AuditRecord, write_audit_record
from .dates import format_offer_date
from .docx_fill import fill_placeholders, find_placeholders_in_document
from .docx_to_pdf import PdfConversionError, convert_docx_to_pdf
from .filenames import FilenameConflictError, resolve_filenames
from .models import ResolvedOffer
from .reference import ReferenceGenerationError, ReferenceStore, get_or_create_reference
from .salary import format_amount
from .storage import StorageBackend, StorageError
from .validation import ValidationResult, validate_offer

# Error codes returned in OfferOutcome.error_code
ERR_VALIDATION_FAILED = "VALIDATION_FAILED"
ERR_REFERENCE_GENERATION_FAILED = "REFERENCE_GENERATION_FAILED"
ERR_FILENAME_CONFLICT = "FILENAME_CONFLICT"
ERR_DOCX_GENERATION_FAILED = "DOCX_GENERATION_FAILED"
ERR_PDF_CONVERSION_FAILED = "PDF_CONVERSION_FAILED"
ERR_STORAGE_FAILED = "STORAGE_FAILED"


@dataclass
class OfferOutcome:
    status: str  # "created" | "blocked" | "error"
    reference: Optional[str] = None
    creation_date: Optional[str] = None
    candidate_name: Optional[str] = None
    business_unit: Optional[str] = None
    template_name: Optional[str] = None
    storage_status: str = "Not attempted"
    docx_filename: Optional[str] = None
    docx_content_bytes: Optional[bytes] = None
    docx_secure_url: Optional[str] = None
    pdf_filename: Optional[str] = None
    pdf_content_bytes: Optional[bytes] = None
    pdf_secure_url: Optional[str] = None
    unresolved_placeholders: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    audit_status: str = "Not attempted"
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        return (
            self.status == "created"
            and self.docx_secure_url is not None
            and self.pdf_secure_url is not None
        )


def _build_fill_values(resolved: ResolvedOffer, validation: ValidationResult, reference: str, offer_date: str) -> dict:
    values: dict = {"Ref": reference, "date": offer_date}

    for name in fields_module.RESOLVABLE_PLACEHOLDERS:
        if name in (
            "basic salary",
            "Supplementary allownce",
            "Total Salary",
            "basic salary per annum",
            "Supplementary allowance per annum",
            "Total Salary per annum",
        ):
            continue
        fv = resolved.get(name)
        values[name] = fv.value if fv else None

    if validation.salary_confirmed_unavailable or validation.salary_result is None or not validation.salary_result.balanced:
        for name in (
            "basic salary",
            "Supplementary allownce",
            "Total Salary",
            "basic salary per annum",
            "Supplementary allowance per annum",
            "Total Salary per annum",
        ):
            values[name] = None
    else:
        b = validation.salary_result.breakdown
        values["basic salary"] = format_amount(b.monthly_basic)
        values["Supplementary allownce"] = format_amount(b.monthly_supplementary)
        values["Total Salary"] = format_amount(b.monthly_total)
        values["basic salary per annum"] = format_amount(b.annual_basic)
        values["Supplementary allowance per annum"] = format_amount(b.annual_supplementary)
        values["Total Salary per annum"] = format_amount(b.annual_total)

    return values


def finalize_offer(
    resolved: ResolvedOffer,
    *,
    templates_dir: Path,
    reference_store: ReferenceStore,
    storage: StorageBackend,
    audit_log_path: Path,
    requested_by: str,
) -> OfferOutcome:
    """Run the full post-approval workflow. Call only after explicit user approval."""
    validation = validate_offer(resolved)
    if not validation.can_finalize:
        return OfferOutcome(
            status="blocked",
            error_code=ERR_VALIDATION_FAILED,
            error_message=(
                "Offer is not ready for finalization: missing_fields="
                f"{validation.missing_fields}, conflicts="
                f"{[c.field for c in validation.conflicts]}, "
                f"business_unit_missing={validation.business_unit_missing_or_unrecognized}"
            ),
            warnings=validation.warnings,
        )

    # Step 1: set the final creation date.
    offer_date = format_offer_date()

    # Step 2: generate (or reuse) the two-digit reference.
    try:
        reference, _generated = get_or_create_reference(reference_store, resolved.offer_id)
    except ReferenceGenerationError as exc:
        return OfferOutcome(status="error", error_code=ERR_REFERENCE_GENERATION_FAILED, error_message=str(exc))

    # Step 3: template already resolved by validation.
    template = validation.template
    assert template is not None  # guaranteed by validation.can_finalize

    candidate_full_name = resolved.value_or_none("candidate full name")

    # Step 9 (checked early so we never do wasted work on a doomed filename):
    # apply filenames and check conflicts against the storage destination.
    try:
        filename_plan = resolve_filenames(
            candidate_full_name,
            template.display_name,
            reference,
            exists_check=storage.exists,
        )
    except FilenameConflictError as exc:
        return OfferOutcome(
            status="error",
            reference=reference,
            error_code=ERR_FILENAME_CONFLICT,
            error_message=str(exc),
        )
    except StorageError as exc:
        return OfferOutcome(status="error", reference=reference, error_code=ERR_STORAGE_FAILED, error_message=str(exc))

    warnings: List[str] = list(validation.warnings) + list(filename_plan.warnings)

    # Steps 4-5: populate resolved fields, retaining approved unresolved placeholders.
    fill_values = _build_fill_values(resolved, validation, reference, offer_date)

    with tempfile.TemporaryDirectory(prefix="offer-agent-") as work_dir_str:
        work_dir = Path(work_dir_str)
        docx_work_path = work_dir / filename_plan.docx_filename
        pdf_work_path = work_dir / filename_plan.pdf_filename

        # Step 6: generate DOCX from the approved template.
        try:
            fill_result = fill_placeholders(template.path(templates_dir), docx_work_path, fill_values)
        except Exception as exc:  # noqa: BLE001 - surfaced as a workflow error, not raised
            return OfferOutcome(
                status="error",
                reference=reference,
                error_code=ERR_DOCX_GENERATION_FAILED,
                error_message=f"DOCX generation failed: {exc}",
            )

        # Step 7: convert the completed DOCX to PDF (never generated independently).
        try:
            convert_docx_to_pdf(docx_work_path, pdf_work_path)
        except PdfConversionError as exc:
            return OfferOutcome(
                status="error",
                reference=reference,
                error_code=ERR_PDF_CONVERSION_FAILED,
                error_message=str(exc),
            )

        # Step 8: verify remaining placeholders are exactly the approved
        # unresolved set — nothing extra leaked through, nothing expected
        # is missing.
        expected_unresolved = set(fill_result.unresolved_placeholders)
        actual_remaining = {"{{" + p + "}}" for p in find_placeholders_in_document(docx_work_path)}
        if actual_remaining != expected_unresolved:
            warnings.append(
                "Post-fill verification found unexpected remaining placeholders: "
                f"{sorted(actual_remaining - expected_unresolved)}; expected only "
                f"{sorted(expected_unresolved)}."
            )
        if fill_result.unexpected_placeholders:
            warnings.append(
                f"Template contains placeholders outside the known field set: "
                f"{fill_result.unexpected_placeholders}"
            )

        # Step 10: save both files through the storage tool.
        try:
            docx_stored = storage.save(docx_work_path, filename_plan.docx_filename)
            pdf_stored = storage.save(pdf_work_path, filename_plan.pdf_filename)
        except StorageError as exc:
            return OfferOutcome(
                status="error",
                reference=reference,
                error_code=ERR_STORAGE_FAILED,
                error_message=str(exc),
            )

        docx_bytes = docx_work_path.read_bytes()
        pdf_bytes = pdf_work_path.read_bytes()

    # Step 12/13: audit. A failure here still returns the created files,
    # with a clear warning, per spec.
    audit_status = "Recorded"
    try:
        write_audit_record(
            audit_log_path,
            AuditRecord(
                reference=reference,
                creation_timestamp=AuditRecord.now_utc(),
                requested_by=requested_by,
                candidate_name=candidate_full_name or "Candidate Name Missing",
                business_unit=template.display_name,
                template_name=template.template_name,
                job_title=resolved.value_or_none("job title") or "",
                notice_period=resolved.value_or_none("notice period") or "",
                monthly_compensation={
                    "basic": fill_values.get("basic salary") or "",
                    "supplementary": fill_values.get("Supplementary allownce") or "",
                    "total": fill_values.get("Total Salary") or "",
                },
                annual_compensation={
                    "basic": fill_values.get("basic salary per annum") or "",
                    "supplementary": fill_values.get("Supplementary allowance per annum") or "",
                    "total": fill_values.get("Total Salary per annum") or "",
                },
                currency="AED",
                input_filenames=list(resolved.input_filenames),
                user_overrides=dict(resolved.user_overrides),
                unresolved_placeholders=fill_result.unresolved_placeholders,
                destination_identifier=storage.destination_identifier(),
                docx_filename=docx_stored.filename,
                docx_secure_url=docx_stored.secure_url,
                pdf_filename=pdf_stored.filename,
                pdf_secure_url=pdf_stored.secure_url,
                generation_status="success",
                delivery_status="success",
                warnings=warnings,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        audit_status = "Failed"
        warnings.append(f"Audit recording failed after file creation: {exc}")

    return OfferOutcome(
        status="created",
        reference=reference,
        creation_date=offer_date,
        candidate_name=candidate_full_name or "Candidate Name Missing",
        business_unit=template.display_name,
        template_name=template.template_name,
        storage_status=f"Destination confirmed ({storage.destination_identifier()})",
        docx_filename=docx_stored.filename,
        docx_content_bytes=docx_bytes,
        docx_secure_url=docx_stored.secure_url,
        pdf_filename=pdf_stored.filename,
        pdf_content_bytes=pdf_bytes,
        pdf_secure_url=pdf_stored.secure_url,
        unresolved_placeholders=fill_result.unresolved_placeholders,
        warnings=warnings,
        audit_status=audit_status,
    )


def format_completion_output(outcome: OfferOutcome, downloads_available: bool = True) -> str:
    """Render the mandatory completion response. Never includes raw contentBytes."""
    if outcome.status != "created":
        return (
            "Status: Employment contract NOT created\n"
            f"Error code: {outcome.error_code}\n"
            f"Error message: {outcome.error_message}\n"
            f"Reference: {outcome.reference or 'Not generated'}\n"
        )

    word_download = "Attached" if downloads_available else "Unavailable — direct attachments not supported"
    pdf_download = "Attached" if downloads_available else "Unavailable — direct attachments not supported"

    unresolved = ", ".join(outcome.unresolved_placeholders) if outcome.unresolved_placeholders else "None"
    warnings = "; ".join(outcome.warnings) if outcome.warnings else "None"

    return (
        "Status: Employment contract created\n"
        f"Reference: {outcome.reference}\n"
        f"Candidate: {outcome.candidate_name}\n"
        f"Business Unit: {outcome.business_unit}\n"
        f"Template: {outcome.template_name}\n"
        f"Creation date: {outcome.creation_date}\n"
        "Downloads:\n"
        f"  Word: {word_download}\n"
        f"  PDF: {pdf_download}\n"
        "Online files:\n"
        f"  Word: {outcome.docx_secure_url}\n"
        f"  PDF: {outcome.pdf_secure_url}\n"
        f"Storage: {outcome.storage_status}\n"
        f"Unresolved placeholders: {unresolved}\n"
        f"Warnings: {warnings}\n"
        f"Audit: {outcome.audit_status}\n"
    )
