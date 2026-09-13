"""A small Flask front-end over the offer_agent engine.

Manual field entry (no automated CV/hiring-approval parsing here — that
extraction step is the language-understanding work the offer-agent
Claude skill does; this web app is for driving the same deterministic
engine — template selection, salary math, reference generation, DOCX
fill, PDF conversion, filenames, storage, audit — from a browser form
instead of a chat).

Storage is local (offer_agent.storage.LocalDevStorageBackend), per
explicit deployment choice, so this app needs no external credentials to
run.
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from pathlib import Path

from flask import Flask, abort, render_template, request, send_from_directory

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from offer_agent import fields as fields_module
from offer_agent.models import FieldValue, ResolvedOffer
from offer_agent.preview import build_preview
from offer_agent.reference import ReferenceStore
from offer_agent.storage import LocalDevStorageBackend
from offer_agent.validation import validate_offer
from offer_agent.workflow import finalize_offer, format_completion_output
from webapp.document_parsing import DocumentParseError, extract_text, image_media_type, is_image
from webapp.llm_extraction import ExtractionResult, extract_offer_fields

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = DATA_DIR / "storage"
TEMPLATES_DIR = BASE_DIR / "templates"
REFERENCE_STORE_PATH = DATA_DIR / "reference_store.json"
AUDIT_LOG_PATH = DATA_DIR / "audit.jsonl"

app = Flask(__name__)

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


def _map_extraction_to_prefill(result: ExtractionResult):
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


def derive_first_name(full_name: str) -> str:
    stripped = _TITLE_PATTERN.sub("", full_name.strip())
    return stripped.split(" ")[0] if stripped else ""


def _resolved_offer_from_form(form) -> ResolvedOffer:
    offer_id = form.get("offer_id") or f"web-{uuid.uuid4().hex[:12]}"
    business_unit_raw = form.get("business_unit", "").strip()

    field_values = {}
    for form_key, placeholder, _label in MANDATORY_FIELDS:
        value = form.get(form_key, "").strip()
        unavailable = form.get(f"{form_key}_unavailable") == "on"
        if unavailable:
            field_values[placeholder] = FieldValue(None, "user", confirmed_unavailable=True)
        elif value:
            field_values[placeholder] = FieldValue(value, "user")
        # else: leave absent -> reported as missing by validate_offer

    first_name = form.get("candidate_first_name", "").strip()
    full_name = form.get("candidate_full_name", "").strip()
    if not first_name and full_name:
        first_name = derive_first_name(full_name)
    if first_name:
        field_values["candidate first name"] = FieldValue(first_name, "user")

    total_salary = form.get("total_salary", "").strip()
    total_salary_unavailable = form.get("total_salary_unavailable") == "on"
    if total_salary_unavailable:
        field_values["Total Salary"] = FieldValue(None, "user", confirmed_unavailable=True)
    elif total_salary:
        field_values["Total Salary"] = FieldValue(total_salary, "user")

    override_basic = form.get("override_basic", "").strip() or None
    override_supplementary = form.get("override_supplementary", "").strip() or None

    return ResolvedOffer(
        offer_id=offer_id,
        business_unit_raw=business_unit_raw or None,
        fields=field_values,
        salary_override_monthly_basic=override_basic,
        salary_override_monthly_supplementary=override_supplementary,
        input_filenames=["manual-web-entry"],
    )


def _serialize_offer(resolved: ResolvedOffer) -> str:
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
        "requested_by": request.form.get("requested_by", "").strip(),
    }
    return json.dumps(payload)


def _deserialize_offer(raw: str) -> tuple[ResolvedOffer, str]:
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


@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        mandatory_fields=MANDATORY_FIELDS,
        templates=fields_module.TEMPLATES,
    )


@app.route("/extract", methods=["POST"])
def extract():
    hiring_file = request.files.get("hiring_approval_file")
    cv_file = request.files.get("cv_file")
    passport_file = request.files.get("passport_file")

    def _has_file(f):
        return f is not None and f.filename

    if not _has_file(hiring_file) and not _has_file(cv_file):
        return render_template(
            "index.html",
            mandatory_fields=MANDATORY_FIELDS,
            templates=fields_module.TEMPLATES,
            extraction_error="Upload at least a hiring approval or a CV to extract from.",
        )

    try:
        hiring_text = extract_text(hiring_file.filename, hiring_file.read()) if _has_file(hiring_file) else None
        cv_text = extract_text(cv_file.filename, cv_file.read()) if _has_file(cv_file) else None

        passport_text = None
        passport_image_b64 = None
        passport_image_media_type = None
        if _has_file(passport_file):
            if is_image(passport_file.filename):
                passport_image_b64 = base64.standard_b64encode(passport_file.read()).decode("utf-8")
                passport_image_media_type = image_media_type(passport_file.filename)
            else:
                passport_text = extract_text(passport_file.filename, passport_file.read())
    except DocumentParseError as exc:
        return render_template(
            "index.html",
            mandatory_fields=MANDATORY_FIELDS,
            templates=fields_module.TEMPLATES,
            extraction_error=str(exc),
        )

    try:
        result = extract_offer_fields(
            hiring_approval_text=hiring_text,
            cv_text=cv_text,
            passport_text=passport_text,
            passport_image_base64=passport_image_b64,
            passport_image_media_type=passport_image_media_type,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not raised
        return render_template(
            "index.html",
            mandatory_fields=MANDATORY_FIELDS,
            templates=fields_module.TEMPLATES,
            extraction_error=(
                "Automatic extraction failed (is ANTHROPIC_API_KEY set on this "
                f"deployment?): {exc}"
            ),
        )

    prefill, business_unit_display, banner_notes = _map_extraction_to_prefill(result)

    return render_template(
        "index.html",
        mandatory_fields=MANDATORY_FIELDS,
        templates=fields_module.TEMPLATES,
        prefill=prefill,
        business_unit_prefill=business_unit_display,
        banner_notes=banner_notes,
    )


@app.route("/preview", methods=["POST"])
def preview():
    resolved = _resolved_offer_from_form(request.form)
    validation = validate_offer(resolved)
    preview_text = build_preview(resolved, validation)
    offer_json = _serialize_offer(resolved)
    return render_template(
        "preview.html",
        preview_text=preview_text,
        can_finalize=validation.can_finalize,
        offer_json=offer_json,
    )


@app.route("/approve", methods=["POST"])
def approve():
    offer_json = request.form.get("offer_json")
    if not offer_json:
        abort(400, "Missing offer data; please start over.")

    resolved, requested_by = _deserialize_offer(offer_json)

    reference_store = ReferenceStore(REFERENCE_STORE_PATH)
    storage = LocalDevStorageBackend(STORAGE_DIR)

    outcome = finalize_offer(
        resolved,
        templates_dir=TEMPLATES_DIR,
        reference_store=reference_store,
        storage=storage,
        audit_log_path=AUDIT_LOG_PATH,
        requested_by=requested_by,
    )

    completion_text = format_completion_output(outcome)
    return render_template(
        "result.html",
        outcome=outcome,
        completion_text=completion_text,
    )


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename: str):
    return send_from_directory(STORAGE_DIR, filename, as_attachment=True)


@app.route("/healthz", methods=["GET"])
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
