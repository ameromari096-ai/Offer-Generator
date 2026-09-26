"""Placeholder and template registry for the Offer Agent.

Placeholder spelling here MUST exactly match the spelling inside the Word
templates (including the templates' own "Supplementary allownce" typo).
Never rename, "fix", or restyle a placeholder — the templates are the
source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Exact placeholder tokens (without the surrounding {{ }}), in the order
# they are introduced by the spec. This is the full set the agent is
# permitted to populate — nothing more, nothing less.
PLACEHOLDERS: tuple[str, ...] = (
    "Ref",
    "candidate title",
    "candidate full name",
    "candidate phone number",
    "candidate email address",
    "candidate first name",
    "job title",
    "date",
    "nationality",
    "line manager",
    "department",
    "basic salary",
    "Supplementary allownce",
    "Total Salary",
    "basic salary per annum",
    "Supplementary allowance per annum",
    "Total Salary per annum",
    "notice period",
)

# Placeholders that are only ever filled by the workflow itself, never by
# field resolution / extraction.
SYSTEM_GENERATED_PLACEHOLDERS: tuple[str, ...] = ("Ref", "date")

# Placeholders that must go through extraction/override/calculation
# resolution before document creation.
RESOLVABLE_PLACEHOLDERS: tuple[str, ...] = tuple(
    p for p in PLACEHOLDERS if p not in SYSTEM_GENERATED_PLACEHOLDERS
)


@dataclass(frozen=True)
class TemplateDefinition:
    key: str  # normalized business-unit key
    display_name: str  # normalized Business Unit name used in filenames/preview
    template_name: str  # exact template name shown to the user
    filename: str  # file name under templates/
    # Exact, case-insensitive Business Unit strings that select this
    # template. Matching is exact-string (case-insensitive), never fuzzy or
    # inferred from other context.
    match_strings: tuple[str, ...]

    def path(self, templates_dir: Path) -> Path:
        return templates_dir / self.filename


TEMPLATES: tuple[TemplateDefinition, ...] = (
    TemplateDefinition(
        key="purehealth",
        display_name="PureHealth",
        template_name="PureHealth Employment Contract",
        filename="PureHealth_Employment_Contract.docx",
        match_strings=("purehealth", "pure health"),
    ),
    TemplateDefinition(
        key="talentone",
        display_name="TalentOne",
        template_name="TalentOne Employment Contract",
        filename="TalentOne_Employment_Contract.docx",
        match_strings=("talentone", "talent one"),
    ),
)


def resolve_template(business_unit_raw: Optional[str]) -> Optional[TemplateDefinition]:
    """Resolve a Business Unit string to its template, case-insensitively.

    Returns None if the value is missing or does not exactly match one of
    the known Business Unit strings. The caller MUST NOT infer a Business
    Unit or template from any other signal (job title, department, email
    domain, etc.) — an unmatched value is a missing/conflicting field to be
    surfaced to the user, never guessed.
    """
    if not business_unit_raw:
        return None
    normalized = " ".join(business_unit_raw.strip().split()).lower()
    for template in TEMPLATES:
        if normalized in template.match_strings:
            return template
    return None


# Human-readable labels for display in the preview / prompts. These are
# presentation-only — the placeholder keys above (with their exact,
# including "Supplementary allownce"'s typo, spelling) are what actually
# gets written into the documents.
PLACEHOLDER_LABELS: dict[str, str] = {
    "Ref": "Reference",
    "candidate title": "Title",
    "candidate full name": "Full name",
    "candidate phone number": "Phone",
    "candidate email address": "Email",
    "candidate first name": "First name",
    "job title": "Job title",
    "date": "Offer date",
    "nationality": "Nationality",
    "line manager": "Line manager",
    "department": "Department",
    "basic salary": "Basic salary (monthly)",
    "Supplementary allownce": "Supplementary allowance (monthly)",
    "Total Salary": "Total Salary (monthly)",
    "basic salary per annum": "Basic salary (annual)",
    "Supplementary allowance per annum": "Supplementary allowance (annual)",
    "Total Salary per annum": "Total Salary (annual)",
    "notice period": "Notice period",
}


def label_for(placeholder: str) -> str:
    return PLACEHOLDER_LABELS.get(placeholder, placeholder)


# The candidate title is a constrained choice, never free text and never
# inferred (not from nationality, name, or any other signal) - the user
# (or an explicit, literal match in a source document) must select one.
TITLE_OPTIONS: tuple[str, ...] = ("Mr.", "Ms.")


def get_template_by_key(key: str) -> TemplateDefinition:
    for template in TEMPLATES:
        if template.key == key:
            return template
    raise KeyError(f"Unknown template key: {key!r}")
