"""Shared extraction result shape, used by whichever extractor backend is
wired into the Flask app (webapp.regex_extraction, free and default; or
webapp.llm_extraction, an available but not wired-in higher-robustness
alternative that requires an Anthropic API key and billing).

Kept dependency-free beyond pydantic so the free/default path never needs
the `anthropic` package installed at all.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ExtractedField(BaseModel):
    value: Optional[str] = None
    source: str  # "hiring_approval" | "cv" | "passport" | "user"
    confirmed_unavailable: bool = False


class ConflictOption(BaseModel):
    value: str
    source: str


class FieldConflict(BaseModel):
    field: str
    options: List[ConflictOption]


class ExtractionResult(BaseModel):
    business_unit_raw: Optional[str] = None
    candidate_full_name: ExtractedField
    candidate_first_name: Optional[ExtractedField] = None
    candidate_phone_number: ExtractedField
    candidate_email_address: ExtractedField
    nationality: ExtractedField
    job_title: ExtractedField
    line_manager: ExtractedField
    department: ExtractedField
    notice_period: ExtractedField
    total_salary: ExtractedField
    conflicts: List[FieldConflict] = []
    notes: List[str] = []
