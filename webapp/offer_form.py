"""Offer-building logic shared by the HTML web app and the JSON API.

Everything here works on a plain Mapping (a Flask form or a parsed JSON
dict both satisfy ``.get(key, default)``) so it has no dependency on
Flask's request object and no import-time dependency on webapp.app -
avoiding a circular import once webapp.api registers its own blueprint.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Mapping, Optional, Tuple

from offer_agent import fields as fields_module
from offer_agent.models import FieldValue, ResolvedOffer
from webapp.extraction_schema import ExtractionResult

MANDATORY_FIELDS = [
    ("candidate_full_name", "candidate full name", "Candidate full name"),
    ("candidate_phone", "candidate phone number", "Candidate phone number"),
    ("candidate_email", "candidate email address", "Candidate email address"),
    ("nationality", "nationality", "Nationality"),
    ("job_title", "job title", "Job title"),
    ("line_manager", "line manager", "Line manager"),
    ("department", "department", "Department"),
    ("notice_period", "notice period", "Notice period (calendar days)"),
]

_TITLE_PATTERN = re.compile(r"^(mr|mrs|ms|miss|dr|prof)\.?\s+", re.IGNORECASE)

# Maps both the ExtractionResult attribute name and its space-separated
# placeholder-style alias to the web form's field key.
_ATTR_TO_FORM_KEY = {
    "candidate_full_name": "candidate_full_name",
    "candidate full name": "candidate_full_name",
    "candidate_first_name": "candidate_first_name",
    "candidate first name": "candidate_first_name",
    "candidate_phone_number": "candidate_phone",
    "candidate phone number": "candidate_phone",
    "candidate_email_address": "candidate_email",
    "candidate email address": "candidate_email",
    "nationality": "nationality",
    "job_title": "job_title",
    "job title": "job_title",
    "line_manager": "line_manager",
    "line manager": "line_manager",
    "department": "department",
    "notice_period": "notice_period",
    "notice period": "notice_period",
    "total_salary": "total_salary",
    "total salary": "total_salary",
    "business_unit_raw": "business_unit",
    "business unit": "business_unit",
}


def derive_first_name(full_name: str) -> str:
    stripped = _TITLE_PATTERN.sub("", full_name.strip())
    return stripped.split(" ")[0] if stripped else ""


def map_extraction_to_prefill(result: ExtractionResult):
    """Turn an ExtractionResult into (prefill dict, business_unit_display, banner_notes)."""
    prefill = {
        "candidate_full_name": result.candidate_full_name.value or "",
        "candidate_first_name": (result.candidate_first_name.value if result.candidate_first_name else "") or "",
        "candidate_phone": result.candidate_phone_number.value or "",
        "candidate_email": result.candidate_email_address.value or "",
        "nationality": result.nationality.value or "",
        "job_title": result.job_title.value or "",
        "line_manager": result.line_manager.value or "",
        "department": result.department.value or "",
        "notice_period": result.notice_period.value or "",
        "total_salary": result.total_salary.value or "",
    }

    banner_notes = list(result.notes)
    conflicted_keys = set()
    for conflict in result.conflicts:
        form_key = _ATTR_TO_FORM_KEY.get(conflict.field.strip())
        if form_key:
            conflicted_keys.add(form_key)
        options = "; ".join(f'"{o.value}" ({o.source})' for o in conflict.options)
        banner_notes.append(f'Conflict on "{conflict.field}": {options} — please choose manually below.')

    for key in conflicted_keys:
        if key in prefill:
            prefill[key] = ""

    business_unit_display = None
    if "business_unit" not in conflicted_keys and result.business_unit_raw:
        template = fields_module.resolve_template(result.business_unit_raw)
        if template:
            business_unit_display = template.display_name
        else:
            banner_notes.append(
                f'Business Unit "{result.business_unit_raw}" from the hiring approval did not '
                "match PureHealth or TalentOne exactly — please select it manually."
            )

    return prefill, business_unit_display, banner_notes


def resolved_offer_from_mapping(form: Mapping) -> ResolvedOffer:
    """Build a ResolvedOffer from a Flask form or an equivalent plain dict.

    ``<field>_unavailable`` flags follow the HTML checkbox convention
    (present with value "on"), which JSON API callers should also use -
    see webapp.api for the JSON-native adapter.
    """
    offer_id = form.get("offer_id") or f"web-{uuid.uuid4().hex[:12]}"
    business_unit_raw = (form.get("business_unit") or "").strip()

    field_values = {}
    for form_key, placeholder, _label in MANDATORY_FIELDS:
        value = (form.get(form_key) or "").strip()
        unavailable = form.get(f"{form_key}_unavailable") == "on"
        if unavailable:
            field_values[placeholder] = FieldValue(None, "user", confirmed_unavailable=True)
        elif value:
            field_values[placeholder] = FieldValue(value, "user")
        # else: leave absent -> reported as missing by validate_offer

    first_name = (form.get("candidate_first_name") or "").strip()
    full_name = (form.get("candidate_full_name") or "").strip()
    if not first_name and full_name:
        first_name = derive_first_name(full_name)
    if first_name:
        field_values["candidate first name"] = FieldValue(first_name, "user")

    total_salary = (form.get("total_salary") or "").strip()
    total_salary_unavailable = form.get("total_salary_unavailable") == "on"
    if total_salary_unavailable:
        field_values["Total Salary"] = FieldValue(None, "user", confirmed_unavailable=True)
    elif total_salary:
        field_values["Total Salary"] = FieldValue(total_salary, "user")

    override_basic = (form.get("override_basic") or "").strip() or None
    override_supplementary = (form.get("override_supplementary") or "").strip() or None

    return ResolvedOffer(
        offer_id=offer_id,
        business_unit_raw=business_unit_raw or None,
        fields=field_values,
        salary_override_monthly_basic=override_basic,
        salary_override_monthly_supplementary=override_supplementary,
        input_filenames=["manual-web-entry"],
    )


def serialize_offer(resolved: ResolvedOffer, requested_by: str) -> str:
    payload = {
        "offer_id": resolved.offer_id,
        "business_unit_raw": resolved.business_unit_raw,
        "fields": {
            name: {"value": fv.value, "source": fv.source, "confirmed_unavailable": fv.confirmed_unavailable}
            for name, fv in resolved.fields.items()
        },
        "salary_override_monthly_basic": resolved.salary_override_monthly_basic,
        "salary_override_monthly_supplementary": resolved.salary_override_monthly_supplementary,
        "input_filenames": resolved.input_filenames,
        "requested_by": requested_by,
    }
    return json.dumps(payload)


def deserialize_offer(raw: str) -> Tuple[ResolvedOffer, str]:
    payload = json.loads(raw)
    fields_out = {
        name: FieldValue(v["value"], v["source"], confirmed_unavailable=v["confirmed_unavailable"])
        for name, v in payload["fields"].items()
    }
    resolved = ResolvedOffer(
        offer_id=payload["offer_id"],
        business_unit_raw=payload["business_unit_raw"],
        fields=fields_out,
        salary_override_monthly_basic=payload["salary_override_monthly_basic"],
        salary_override_monthly_supplementary=payload["salary_override_monthly_supplementary"],
        input_filenames=payload["input_filenames"],
    )
    return resolved, payload.get("requested_by") or "web-user"
