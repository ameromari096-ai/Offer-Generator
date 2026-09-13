"""Builds the mandatory pre-approval preview shown to the user.

No reference is generated and no document is created before this preview
is shown and explicitly approved.
"""

from __future__ import annotations

from typing import Optional

from . import fields as fields_module
from .models import ResolvedOffer
from .salary import format_aed
from .validation import ValidationResult

OFFER_ONLY_OPTIONS = ("Approve and create", "Correct a field", "Cancel")


def _val(resolved: ResolvedOffer, name: str) -> str:
    fv = resolved.get(name)
    if fv is None:
        return "Not yet provided"
    if fv.value in (None, ""):
        return "{{" + name + "}} (confirmed unavailable)" if fv.confirmed_unavailable else "Not yet provided"
    return fv.value


def _list_or_none(items) -> str:
    items = list(items)
    if not items:
        return "None"
    return "\n".join(f"  - {item}" for item in items)


def build_preview(resolved: ResolvedOffer, validation: ValidationResult) -> str:
    template = validation.template
    business_unit_display = (
        template.display_name if template else (resolved.business_unit_raw or "Missing")
    )
    template_name = template.template_name if template else "Unresolved (Business Unit not recognized)"

    if validation.salary_confirmed_unavailable:
        monthly_basic = monthly_supp = monthly_total = "{{...}} (confirmed unavailable)"
        annual_basic = annual_supp = annual_total = "{{...}} (confirmed unavailable)"
    elif validation.salary_result and validation.salary_result.breakdown:
        b = validation.salary_result.breakdown
        monthly_basic = format_aed(b.monthly_basic)
        monthly_supp = format_aed(b.monthly_supplementary)
        monthly_total = format_aed(b.monthly_total)
        annual_basic = format_aed(b.annual_basic)
        annual_supp = format_aed(b.annual_supplementary)
        annual_total = format_aed(b.annual_total)
    else:
        monthly_basic = monthly_supp = monthly_total = "Not yet available"
        annual_basic = annual_supp = annual_total = "Not yet available"

    if validation.salary_confirmed_unavailable:
        salary_result_line = "Not calculated (Total Salary confirmed unavailable)"
    elif validation.salary_result is None:
        salary_result_line = "Not yet available"
    elif validation.salary_result.balanced:
        line = "Balanced"
        if validation.salary_result.used_override:
            line += " (approved override breakdown)"
        salary_result_line = line
    else:
        salary_result_line = "DISCREPANCY — correction required:\n" + _list_or_none(
            validation.salary_result.discrepancies
        )

    overrides_lines = (
        [f"{fields_module.label_for(k)}: {v}" for k, v in resolved.user_overrides.items()]
        if resolved.user_overrides
        else []
    )

    missing_labels = [fields_module.label_for(f) for f in validation.missing_fields]
    if validation.business_unit_missing_or_unrecognized:
        missing_labels.append(
            "Business Unit (must exactly match 'PureHealth' or 'TalentOne'/'Talent One')"
        )

    unresolved_labels = [
        "{{" + f + "}}" for f in validation.unresolved_placeholders
    ]

    conflict_lines = []
    for conflict in validation.conflicts:
        options = "; ".join(f"{o.value} ({o.source})" for o in conflict.options)
        conflict_lines.append(f"{fields_module.label_for(conflict.field)}: {options} — selection required")

    sections = [
        "Candidate:",
        f"  Full name: {_val(resolved, 'candidate full name')}",
        f"  First name: {_val(resolved, 'candidate first name')}",
        f"  Phone: {_val(resolved, 'candidate phone number')}",
        f"  Email: {_val(resolved, 'candidate email address')}",
        f"  Nationality: {_val(resolved, 'nationality')}",
        "",
        "Employment:",
        f"  Job title: {_val(resolved, 'job title')}",
        f"  Line manager: {_val(resolved, 'line manager')}",
        f"  Department: {_val(resolved, 'department')}",
        f"  Business Unit: {business_unit_display}",
        f"  Template: {template_name}",
        f"  Notice period: {_val(resolved, 'notice period')}",
        f"  Offer date: {_val(resolved, 'date')}",
        "",
        "Monthly compensation:",
        f"  Basic salary: {monthly_basic}",
        f"  Supplementary allowance: {monthly_supp}",
        f"  Total Salary: {monthly_total}",
        "",
        "Annual compensation:",
        f"  Basic salary: {annual_basic}",
        f"  Supplementary allowance: {annual_supp}",
        f"  Total Salary: {annual_total}",
        "",
        "Validation:",
        f"  Salary result: {salary_result_line}",
        f"  User overrides:\n{_list_or_none(overrides_lines)}",
        f"  Missing fields:\n{_list_or_none(missing_labels)}",
        f"  Unresolved placeholders:\n{_list_or_none(unresolved_labels)}",
        f"  Conflicts:\n{_list_or_none(conflict_lines)}",
        f"  Warnings:\n{_list_or_none(validation.warnings)}",
        "",
        "Reference:",
        "  To be generated automatically after approval",
        "",
        "Offer only:",
        *[f"  - {opt}" for opt in OFFER_ONLY_OPTIONS],
    ]

    if unresolved_labels:
        sections.insert(
            0,
            "WARNING: the following placeholders will remain unresolved in "
            f"the generated documents: {', '.join(unresolved_labels)}\n",
        )

    return "\n".join(sections)
