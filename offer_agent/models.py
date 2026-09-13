"""Core data model for a single offer moving through the workflow.

Extraction from the hiring approval, CV, and passport, and the
priority/conflict resolution across those sources, is a language
understanding task performed by the calling agent (see
.claude/skills/offer-agent/SKILL.md). This module only defines the shapes
that carry the *result* of that resolution into the deterministic parts of
the workflow (validation, preview, salary, document generation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Source labels, in priority order (highest first), matching the spec.
SOURCE_USER_VALUE = "user"
SOURCE_PASSPORT = "passport"
SOURCE_HIRING_APPROVAL = "hiring_approval"
SOURCE_CV = "cv"
SOURCE_CALCULATION = "calculation"
SOURCE_UNAVAILABLE = "confirmed_unavailable"

SOURCE_PRIORITY = (
    SOURCE_USER_VALUE,
    SOURCE_PASSPORT,
    SOURCE_HIRING_APPROVAL,
    SOURCE_CV,
    SOURCE_CALCULATION,
)


@dataclass
class FieldValue:
    """The resolved value for one placeholder field.

    ``value`` is None only when ``confirmed_unavailable`` is True (the user
    explicitly confirmed the value cannot be obtained) — any other missing
    field is incomplete and must still be requested from the user before
    the offer can be finalized.
    """

    value: Optional[str]
    source: str
    confirmed_unavailable: bool = False


@dataclass
class ConflictOption:
    value: str
    source: str


@dataclass
class FieldConflict:
    field: str
    options: List[ConflictOption]


@dataclass
class ResolvedOffer:
    """The result of extraction + priority/conflict resolution for one offer.

    ``offer_id`` is minted once by the calling agent at the moment the
    candidate/business-unit identity is first established for this offer,
    and reused on every retry of the same approved offer so that reference
    generation and audit records tie back to a single offer.
    """

    offer_id: str
    business_unit_raw: Optional[str]
    fields: Dict[str, FieldValue] = field(default_factory=dict)
    conflicts: List[FieldConflict] = field(default_factory=list)
    user_overrides: Dict[str, str] = field(default_factory=dict)
    salary_override_monthly_basic: Optional[str] = None
    salary_override_monthly_supplementary: Optional[str] = None
    input_filenames: List[str] = field(default_factory=list)

    def get(self, name: str) -> Optional[FieldValue]:
        return self.fields.get(name)

    def value_or_none(self, name: str) -> Optional[str]:
        fv = self.fields.get(name)
        return fv.value if fv else None
