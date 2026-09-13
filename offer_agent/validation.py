"""Validates a resolved offer before preview / before finalization.

Distinguishes two very different situations for a field with no value:

* Genuinely missing (not yet asked, or asked and not yet answered) — this
  BLOCKS the offer; the field must be requested from the user.
* Confirmed unavailable (the user explicitly said the value cannot be
  obtained) — this does NOT block the offer; the placeholder is retained
  in both documents and disclosed in the preview and completion output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import fields as fields_module
from .fields import TemplateDefinition
from .models import FieldConflict, ResolvedOffer
from .salary import SalaryResult, compute_salary

SALARY_PLACEHOLDERS = (
    "basic salary",
    "Supplementary allownce",
    "Total Salary",
    "basic salary per annum",
    "Supplementary allowance per annum",
    "Total Salary per annum",
)

NON_SALARY_MANDATORY_FIELDS = tuple(
    p for p in fields_module.RESOLVABLE_PLACEHOLDERS if p not in SALARY_PLACEHOLDERS
)


@dataclass
class ValidationResult:
    template: Optional[TemplateDefinition]
    business_unit_missing_or_unrecognized: bool
    missing_fields: List[str] = field(default_factory=list)
    unresolved_placeholders: List[str] = field(default_factory=list)
    conflicts: List[FieldConflict] = field(default_factory=list)
    salary_result: Optional[SalaryResult] = None
    salary_confirmed_unavailable: bool = False
    warnings: List[str] = field(default_factory=list)

    @property
    def can_finalize(self) -> bool:
        if self.business_unit_missing_or_unrecognized:
            return False
        if self.missing_fields:
            return False
        if self.conflicts:
            return False
        if self.salary_confirmed_unavailable:
            return True
        return bool(self.salary_result and self.salary_result.balanced)


def validate_offer(resolved: ResolvedOffer) -> ValidationResult:
    template = fields_module.resolve_template(resolved.business_unit_raw)
    business_unit_missing = template is None

    missing_fields: List[str] = []
    unresolved_placeholders: List[str] = []
    warnings: List[str] = list()

    for name in NON_SALARY_MANDATORY_FIELDS:
        fv = resolved.get(name)
        if fv is None or (fv.value in (None, "") and not fv.confirmed_unavailable):
            missing_fields.append(name)
        elif fv.value in (None, "") and fv.confirmed_unavailable:
            unresolved_placeholders.append(name)

    salary_result: Optional[SalaryResult] = None
    salary_confirmed_unavailable = False

    total_fv = resolved.get("Total Salary")
    if total_fv is None or (total_fv.value in (None, "") and not total_fv.confirmed_unavailable):
        missing_fields.append("Total Salary")
    elif total_fv.value in (None, "") and total_fv.confirmed_unavailable:
        salary_confirmed_unavailable = True
        unresolved_placeholders.extend(SALARY_PLACEHOLDERS)
    else:
        salary_result = compute_salary(
            total_fv.value,
            resolved.salary_override_monthly_basic,
            resolved.salary_override_monthly_supplementary,
        )
        warnings.extend(salary_result.warnings)
        if not salary_result.balanced:
            warnings.extend(salary_result.discrepancies)

    return ValidationResult(
        template=template,
        business_unit_missing_or_unrecognized=business_unit_missing,
        missing_fields=missing_fields,
        unresolved_placeholders=unresolved_placeholders,
        conflicts=list(resolved.conflicts),
        salary_result=salary_result,
        salary_confirmed_unavailable=salary_confirmed_unavailable,
        warnings=warnings,
    )
