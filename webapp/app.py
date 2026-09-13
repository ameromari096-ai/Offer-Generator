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
