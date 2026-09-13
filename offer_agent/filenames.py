"""Filename construction and conflict handling for generated contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

_INVALID_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

CANDIDATE_NAME_MISSING = "Candidate Name Missing"
BUSINESS_UNIT_MISSING = "Business Unit Missing"


class FilenameConflictError(RuntimeError):
    """Raised when both the plain and reference-suffixed filenames already exist."""


def sanitize_component(value: str) -> str:
    """Strip characters that are invalid in filenames and collapse whitespace."""
    cleaned = _INVALID_CHARS.sub("", value)
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


@dataclass
class FilenamePlan:
    docx_filename: str
    pdf_filename: str
    used_reference_suffix: bool
    warnings: list[str] = field(default_factory=list)


def _base_name(candidate_full_name: Optional[str], business_unit_display: Optional[str]) -> tuple[str, list[str]]:
    warnings: list[str] = []

    name = sanitize_component(candidate_full_name) if candidate_full_name else ""
    if not name:
        name = CANDIDATE_NAME_MISSING
        warnings.append(
            "Candidate full name is missing; filenames use "
            f"'{CANDIDATE_NAME_MISSING}' as a placeholder."
        )

    business_unit = sanitize_component(business_unit_display) if business_unit_display else ""
    if not business_unit:
        business_unit = BUSINESS_UNIT_MISSING
        warnings.append(
            "Business Unit is missing; filenames use "
            f"'{BUSINESS_UNIT_MISSING}' as a placeholder."
        )

    base = f"{name} - {business_unit} - Employment Contract"
    return base, warnings


def resolve_filenames(
    candidate_full_name: Optional[str],
    business_unit_display: Optional[str],
    reference: str,
    exists_check: Callable[[str], bool],
) -> FilenamePlan:
    """Build the DOCX/PDF filename pair, avoiding any overwrite.

    ``exists_check`` is called with a candidate filename (docx or pdf) and
    must return True if a file of that name already exists at the
    destination the files will actually be saved to (the storage backend
    the workflow is configured with) — not necessarily the local
    filesystem.

    Never overwrites an existing contract. If the plain filename pair is
    taken, the two-digit reference is appended once. If that is also
    taken, this raises ``FilenameConflictError`` rather than generating a
    different reference to dodge the conflict.
    """
    base, warnings = _base_name(candidate_full_name, business_unit_display)

    docx_name = f"{base}.docx"
    pdf_name = f"{base}.pdf"

    if not exists_check(docx_name) and not exists_check(pdf_name):
        return FilenamePlan(
            docx_filename=docx_name,
            pdf_filename=pdf_name,
            used_reference_suffix=False,
            warnings=warnings,
        )

    suffixed_base = f"{base} - {reference}"
    suffixed_docx = f"{suffixed_base}.docx"
    suffixed_pdf = f"{suffixed_base}.pdf"

    if exists_check(suffixed_docx) or exists_check(suffixed_pdf):
        raise FilenameConflictError(
            f"Both '{docx_name}'/'{pdf_name}' and the reference-suffixed "
            f"'{suffixed_docx}'/'{suffixed_pdf}' already exist. Stopping "
            "without generating a different reference to resolve this."
        )

    warnings.append(
        f"'{docx_name}' already existed, so the reference ({reference}) was "
        "appended to the filenames to avoid overwriting the existing contract."
    )
    return FilenamePlan(
        docx_filename=suffixed_docx,
        pdf_filename=suffixed_pdf,
        used_reference_suffix=True,
        warnings=warnings,
    )


def local_directory_exists_check(directory: Path) -> Callable[[str], bool]:
    """Convenience exists_check for a local filesystem directory (dev/testing)."""
    directory = Path(directory)

    def _check(filename: str) -> bool:
        return (directory / filename).exists()

    return _check
