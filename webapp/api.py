"""JSON API for the Offer Agent, for non-browser clients — specifically a
Power Apps canvas app acting as an Entra-ID-gated UI shell in front of this
same, already-tested engine (no re-implementation of salary math /
notice-period rules / reference generation in Power Fx).

Every route requires a matching X-API-Key header, checked against the
OFFER_AGENT_API_KEY environment variable. This is deliberately fail-closed:
if that variable isn't set, the whole API refuses to serve rather than
defaulting to open. A leaked API URL alone must never be enough to reach
this engine — the caller also needs the key, which only the Power Automate
custom connector (or another server-side caller) holds, never the browser.
"""

from __future__ import annotations

import os
from functools import wraps
from typing import Optional

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from offer_agent.reference import ReferenceStore
from offer_agent.validation import validate_offer
from offer_agent.workflow import finalize_offer
from webapp.document_parsing import DocumentParseError, extract_text, is_image
from webapp.offer_form import (
    deserialize_offer,
    map_extraction_to_prefill,
    resolved_offer_from_mapping,
    serialize_offer,
)
from webapp.paths import AUDIT_LOG_PATH, REFERENCE_STORE_PATH, STORAGE_DIR, TEMPLATES_DIR
from webapp.regex_extraction import extract_offer_fields_regex

api = Blueprint("api", __name__, url_prefix="/api")


def _api_key_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = os.environ.get("OFFER_AGENT_API_KEY")
        if not expected:
            return jsonify(error="API disabled: OFFER_AGENT_API_KEY is not configured on the server."), 503
        got = request.headers.get("X-API-Key")
        if not got or got != expected:
            return jsonify(error="Missing or invalid X-API-Key header."), 401
        return view(*args, **kwargs)

    return wrapped


def _has_file(f) -> bool:
    return f is not None and f.filename


@api.route("/extract", methods=["POST"])
@_api_key_required
def api_extract():
    """multipart/form-data: hiring_approval_file, cv_file, passport_file (each optional,
    but at least one of hiring_approval_file/cv_file is required)."""
    hiring_file = request.files.get("hiring_approval_file")
    cv_file = request.files.get("cv_file")
    passport_file = request.files.get("passport_file")

    if not _has_file(hiring_file) and not _has_file(cv_file):
        return jsonify(error="Upload at least a hiring approval or a CV to extract from."), 400

    try:
        hiring_text = extract_text(hiring_file.filename, hiring_file.read()) if _has_file(hiring_file) else None
        cv_text = extract_text(cv_file.filename, cv_file.read()) if _has_file(cv_file) else None

        passport_text = None
        notes_extra = []
        if _has_file(passport_file):
            if is_image(passport_file.filename):
                notes_extra.append(
                    "Passport image uploaded, but this deployment's free extraction "
                    "mode can't read images (no OCR) — please confirm name and "
                    "nationality manually."
                )
            else:
                passport_text = extract_text(passport_file.filename, passport_file.read())
    except DocumentParseError as exc:
        return jsonify(error=str(exc)), 400

    try:
        result = extract_offer_fields_regex(
            hiring_approval_text=hiring_text,
            cv_text=cv_text,
            passport_text=passport_text,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller, not raised
        return jsonify(error=f"Automatic extraction failed: {exc}"), 400

    prefill, business_unit_display, banner_notes = map_extraction_to_prefill(result)
    banner_notes.extend(notes_extra)

    return jsonify(fields=prefill, business_unit=business_unit_display, notes=banner_notes)


@api.route("/preview", methods=["POST"])
@_api_key_required
def api_preview():
    """JSON body, same field keys as the HTML form:
    {
      "offer_id": "optional, reuse to retry the same offer",
      "business_unit": "PureHealth" | "TalentOne" | raw string from the hiring approval,
      "requested_by": "person@purehealth.ae",
      "fields": {"candidate_full_name": "...", "candidate_phone": "...", ...},
      "unavailable_fields": ["notice_period"],   // form keys confirmed unavailable
      "total_salary_unavailable": false,
      "override_basic": null,
      "override_supplementary": null
    }
    """
    data = request.get_json(silent=True) or {}
    fields_in = data.get("fields") or {}
    unavailable = set(data.get("unavailable_fields") or [])

    form_like = dict(fields_in)
    form_like["offer_id"] = data.get("offer_id")
    form_like["business_unit"] = data.get("business_unit")
    form_like["override_basic"] = data.get("override_basic")
    form_like["override_supplementary"] = data.get("override_supplementary")
    for key in unavailable:
        form_like[f"{key}_unavailable"] = "on"
    if data.get("total_salary_unavailable"):
        form_like["total_salary_unavailable"] = "on"

    resolved = resolved_offer_from_mapping(form_like)
    validation = validate_offer(resolved)
    requested_by = (data.get("requested_by") or "").strip()
    offer_token = serialize_offer(resolved, requested_by)

    return jsonify(
        can_finalize=validation.can_finalize,
        missing_fields=validation.missing_fields,
        conflicts=[c.field for c in validation.conflicts],
        business_unit_recognized=not validation.business_unit_missing_or_unrecognized,
        warnings=validation.warnings,
        offer_token=offer_token,
    )


@api.route("/approve", methods=["POST"])
@_api_key_required
def api_approve():
    """JSON body: {"offer_token": "<from /api/preview>", "requested_by": "optional override"}."""
    data = request.get_json(silent=True) or {}
    offer_token = data.get("offer_token")
    if not offer_token:
        return jsonify(error="Missing offer_token; call /api/preview first."), 400

    resolved, token_requested_by = deserialize_offer(offer_token)
    requested_by = (data.get("requested_by") or "").strip() or token_requested_by

    reference_store = ReferenceStore(REFERENCE_STORE_PATH)
    storage = current_app.config["STORAGE_BACKEND_FACTORY"]()

    outcome = finalize_offer(
        resolved,
        templates_dir=TEMPLATES_DIR,
        reference_store=reference_store,
        storage=storage,
        audit_log_path=AUDIT_LOG_PATH,
        requested_by=requested_by,
    )

    if outcome.status != "created":
        return (
            jsonify(
                status=outcome.status,
                error_code=outcome.error_code,
                error_message=outcome.error_message,
                reference=outcome.reference,
                warnings=outcome.warnings,
            ),
            422,
        )

    def _url_for_local(filename: Optional[str]) -> Optional[str]:
        if filename is None:
            return None
        return f"{request.url_root.rstrip('/')}/api/download/{filename}"

    is_local = current_app.config.get("STORAGE_LABEL", "local") == "local"

    return jsonify(
        status="created",
        reference=outcome.reference,
        creation_date=outcome.creation_date,
        candidate_name=outcome.candidate_name,
        business_unit=outcome.business_unit,
        template_name=outcome.template_name,
        storage_status=outcome.storage_status,
        docx_filename=outcome.docx_filename,
        pdf_filename=outcome.pdf_filename,
        docx_url=_url_for_local(outcome.docx_filename) if is_local else outcome.docx_secure_url,
        pdf_url=_url_for_local(outcome.pdf_filename) if is_local else outcome.pdf_secure_url,
        unresolved_placeholders=outcome.unresolved_placeholders,
        warnings=outcome.warnings,
        audit_status=outcome.audit_status,
    )


@api.route("/download/<path:filename>", methods=["GET"])
@_api_key_required
def api_download(filename: str):
    """Only serves files for the local storage backend. When a remote
    backend (e.g. SharePoint) is configured, /api/approve already returns
    its own secure_url directly and this route is not used."""
    return send_from_directory(STORAGE_DIR, filename, as_attachment=True)


@api.route("/business-units", methods=["GET"])
@_api_key_required
def api_business_units():
    """Lets the canvas app populate its Business Unit dropdown without
    hardcoding template names on the Power Apps side."""
    from offer_agent import fields as fields_module

    return jsonify(business_units=[t.display_name for t in fields_module.TEMPLATES])
