"""Free, rule-based (no LLM, no API key, no billing) extraction of offer
fields from a hiring approval / CV / passport text.

Trades robustness for zero cost: it looks for the exact label text the
hiring-approval templates we've seen use ("Candidate Recommended", "Job
Title", "Reporting Line", "Division"/"Department", "Business Unit",
"Proposed Salary", "Notice Period" under a Contract Terms section) either
as its own line immediately followed by the value on the next non-empty
line (the shape produced by our own .msg/.eml/.docx-table parsing), or as
"Label: Value" on one line. A hiring approval in a very different layout
will simply extract less — the user reviews and fills gaps manually on
the pre-filled form either way.

Produces the same ExtractionResult shape as llm_extraction.py so the
Flask route and its prefill/conflict-mapping logic don't care which
extractor produced it.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from webapp.extraction_schema import ExtractedField, ExtractionResult, FieldConflict

_WS = re.compile(r"[ \t ]+")


def _lines(text: str) -> List[str]:
    return [_WS.sub(" ", ln).strip() for ln in text.splitlines()]


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


# Canonical hiring-approval label -> field key. "division" is tracked
# separately from "department" so the two can be compared for a conflict
# rather than one silently overwriting the other.
_LABEL_TO_KEY = {
    "candidate recommended": "candidate_full_name",
    "job title": "job_title",
    "reporting line": "line_manager",
    "department": "department",
    "division": "division",
    "business unit": "business_unit_raw",
    "proposed salary": "total_salary",
}

_LABEL_VALUE_ON_SAME_LINE = re.compile(
    r"^(candidate recommended|job title|reporting line|department|division|"
    r"business unit|proposed salary)\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)

_CONTRACT_TERMS_HEADERS = {"contract terms", "contract term details", "contract term"}
_OTHER_SECTION_HEADERS = {
    "new hire details",
    "separation details",
    "remarks",
    "compensation details",
}


def _find_label_value_pairs(lines: List[str]) -> dict:
    """Returns canonical_key -> first matched value string, or None if absent."""
    results: dict = {}

    for line in lines:
        same_line = _LABEL_VALUE_ON_SAME_LINE.match(line)
        if same_line:
            key = _LABEL_TO_KEY.get(_norm(same_line.group(1)))
            value = same_line.group(2).strip()
            if key and key not in results and value:
                results[key] = value

    n = len(lines)
    i = 0
    while i < n:
        key = _LABEL_TO_KEY.get(_norm(lines[i]))
        if key and key not in results:
            j = i + 1
            while j < n and not lines[j]:
                j += 1
            if j < n:
                results[key] = lines[j]
                i = j
                continue
        i += 1

    return results


def _find_notice_period_in_contract_terms(lines: List[str]) -> Optional[str]:
    n = len(lines)
    start = None
    for idx, line in enumerate(lines):
        if _norm(line) in _CONTRACT_TERMS_HEADERS:
            start = idx
            break
    if start is None:
        return None

    end = n
    for idx in range(start + 1, n):
        if _norm(lines[idx]) in _OTHER_SECTION_HEADERS:
            end = idx
            break

    for idx in range(start + 1, end):
        same_line = re.match(r"^notice period\s*[:\-]\s*(.+)$", lines[idx], re.IGNORECASE)
        if same_line:
            return same_line.group(1).strip()
        if _norm(lines[idx]) == "notice period":
            j = idx + 1
            while j < end and not lines[j]:
                j += 1
            if j < end:
                return lines[j]
    return None


_MONTHS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*month", re.IGNORECASE)
_DAYS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:calendar\s+)?day", re.IGNORECASE)
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def _notice_period_to_days(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (days_value, note). note is set only on a unit conversion."""
    months_match = _MONTHS_PATTERN.search(raw)
    if months_match:
        days = int(float(months_match.group(1)) * 30)
        note = (
            f'Notice period: {days} (converted from hiring approval\'s '
            f'"{raw.strip()}", months x 30)'
        )
        return str(days), note
    days_match = _DAYS_PATTERN.search(raw)
    if days_match:
        return days_match.group(1), None
    number_match = _NUMBER_PATTERN.search(raw)
    if number_match:
        return number_match.group(0), None
    return None, None


def _clean_money(value: str) -> Optional[str]:
    cleaned = re.sub(r"[^\d.]", "", value)
    return cleaned or None


_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_PATTERN = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
_NATIONALITY_LABEL_PATTERN = re.compile(r"^nationality\s*[:\-]?\s*(.+)$", re.IGNORECASE)


def _extract_email(text: str) -> Optional[str]:
    match = _EMAIL_PATTERN.search(text)
    return match.group(0) if match else None


def _extract_phone(text: str) -> Optional[str]:
    for match in _PHONE_PATTERN.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 7 <= len(digits) <= 15:
            return match.group(0).strip()
    return None


def _extract_nationality_explicit(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    for line in text.splitlines():
        match = _NATIONALITY_LABEL_PATTERN.match(line.strip())
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


def extract_offer_fields_regex(
    hiring_approval_text: Optional[str] = None,
    cv_text: Optional[str] = None,
    passport_text: Optional[str] = None,
) -> ExtractionResult:
    notes: List[str] = []
    conflicts: List[FieldConflict] = []

    hiring_lines = _lines(hiring_approval_text) if hiring_approval_text else []
    pairs = _find_label_value_pairs(hiring_lines) if hiring_lines else {}

    candidate_full_name = pairs.get("candidate_full_name")
    candidate_full_name_source = "hiring_approval" if candidate_full_name else None
    job_title = pairs.get("job_title")
    line_manager = pairs.get("line_manager")
    business_unit_raw = pairs.get("business_unit_raw")

    # "Division" and "Department" are distinct fields in the hiring
    # approval template (Division is the broader org unit, Department the
    # specific one) - they routinely differ and that is not a conflict.
    # The offer's department field must equal the hiring approval's own
    # "Department" value exactly; "Division" is only a fallback for the
    # rare hiring approval that omits "Department" entirely.
    department_val = pairs.get("department")
    division_val = pairs.get("division")
    department = department_val or division_val

    total_salary_raw = pairs.get("total_salary")
    total_salary = _clean_money(total_salary_raw) if total_salary_raw else None

    notice_period_raw = _find_notice_period_in_contract_terms(hiring_lines) if hiring_lines else None
    notice_period_days = None
    if notice_period_raw:
        notice_period_days, note = _notice_period_to_days(notice_period_raw)
        if note:
            notes.append(note)

    cv_nonempty_lines = [ln for ln in _lines(cv_text) if ln] if cv_text else []
    if not candidate_full_name and cv_nonempty_lines:
        candidate_full_name = cv_nonempty_lines[0]
        candidate_full_name_source = "cv"

    candidate_phone = _extract_phone(cv_text) if cv_text else None
    candidate_email = _extract_email(cv_text) if cv_text else None

    nationality = (
        _extract_nationality_explicit(passport_text)
        or _extract_nationality_explicit(hiring_approval_text)
        or _extract_nationality_explicit(cv_text)
    )
    nationality_source = "passport" if passport_text and _extract_nationality_explicit(passport_text) else (
        "hiring_approval" if hiring_approval_text and _extract_nationality_explicit(hiring_approval_text) else "cv"
    )

    return ExtractionResult(
        business_unit_raw=business_unit_raw,
        candidate_full_name=ExtractedField(value=candidate_full_name, source=candidate_full_name_source or "cv"),
        candidate_first_name=None,
        candidate_phone_number=ExtractedField(value=candidate_phone, source="cv"),
        candidate_email_address=ExtractedField(value=candidate_email, source="cv"),
        nationality=ExtractedField(value=nationality, source=nationality_source),
        job_title=ExtractedField(value=job_title, source="hiring_approval"),
        line_manager=ExtractedField(value=line_manager, source="hiring_approval"),
        department=ExtractedField(value=department, source="hiring_approval"),
        notice_period=ExtractedField(value=notice_period_days, source="hiring_approval"),
        total_salary=ExtractedField(value=total_salary, source="hiring_approval"),
        conflicts=conflicts,
        notes=notes,
    )
