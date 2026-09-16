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

import hmac
import os
import sys
from pathlib import Path

from flask import Flask, Response, abort, render_template, request, send_from_directory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from offer_agent import fields as fields_module
from offer_agent.preview import build_preview
from offer_agent.reference import ReferenceStore
from offer_agent.storage import LocalDevStorageBackend
from offer_agent.validation import validate_offer
from offer_agent.workflow import finalize_offer, format_completion_output
from webapp.document_parsing import DocumentParseError, extract_text, is_image
from webapp.offer_form import (
    MANDATORY_FIELDS,
    deserialize_offer,
    map_extraction_to_prefill,
    resolved_offer_from_mapping,
    serialize_offer,
)
from webapp.paths import AUDIT_LOG_PATH, REFERENCE_STORE_PATH, STORAGE_DIR, TEMPLATES_DIR
from webapp.regex_extraction import extract_offer_fields_regex

app = Flask(__name__)

from webapp.api import api as api_blueprint  # noqa: E402 - after app creation, avoids a circular import

app.register_blueprint(api_blueprint)


def _default_storage_backend():
    return LocalDevStorageBackend(STORAGE_DIR)


# Which StorageBackend /approve actually uses is overridable (e.g. by the
# desktop app, when it finds a valid SharePoint config) without touching
# this route — set app.config["STORAGE_BACKEND_FACTORY"] to a zero-arg
# callable returning a StorageBackend, and app.config["STORAGE_LABEL"] to
# a short string the templates use to decide how to present downloads.
app.config.setdefault("STORAGE_BACKEND_FACTORY", _default_storage_backend)
app.config.setdefault("STORAGE_LABEL", "local")

# If SHAREPOINT_TENANT_ID etc. are set in the environment (e.g. as Render
# secrets, or on any other server this app is hosted on for the Power Apps
# UI shell), switch to SharePoint storage. Left unset, behavior is
# unchanged - LocalDevStorageBackend, same as before this existed.
if os.environ.get("SHAREPOINT_TENANT_ID"):
    from offer_agent.sharepoint_storage import SharePointStorageBackend

    def _sharepoint_factory():
        return SharePointStorageBackend.from_env()

    app.config["STORAGE_BACKEND_FACTORY"] = _sharepoint_factory
    app.config["STORAGE_LABEL"] = "sharepoint"


@app.context_processor
def _inject_storage_label():
    return {"storage_label": app.config.get("STORAGE_LABEL", "local")}


# The HTML pages below (/, /extract, /preview, /approve) have no login of
# their own - fine for the desktop app (127.0.0.1 only) and for local dev,
# but not for a deployment meant to sit behind the Power Apps API. Setting
# both WEBAPP_BASIC_AUTH_USER and WEBAPP_BASIC_AUTH_PASSWORD turns on HTTP
# Basic Auth for exactly those routes; /api/* keeps its own X-API-Key
# check regardless, and /healthz always stays open for the host's health
# checks. Left unset (the desktop app, local dev), behavior is unchanged.
@app.before_request
def _require_basic_auth_for_html_routes():
    if request.path.startswith("/api/") or request.path == "/healthz":
        return None

    expected_user = os.environ.get("WEBAPP_BASIC_AUTH_USER")
    expected_password = os.environ.get("WEBAPP_BASIC_AUTH_PASSWORD")
    if not expected_user or not expected_password:
        return None

    auth = request.authorization
    valid = (
        auth is not None
        and hmac.compare_digest(auth.username or "", expected_user)
        and hmac.compare_digest(auth.password or "", expected_password)
    )
    if not valid:
        return Response(
            "Authentication required.",
            401,
            {"WWW-Authenticate": 'Basic realm="Offer Agent"'},
        )
    return None

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
        passport_image_note = None
        if _has_file(passport_file):
            if is_image(passport_file.filename):
                # The free/regex extractor has no OCR — an image passport
                # can't be read this way; say so rather than silently
                # ignoring the upload.
                passport_image_note = (
                    "Passport image uploaded, but this deployment's free extraction "
                    "mode can't read images (no OCR) — please confirm name and "
                    "nationality manually."
                )
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
        result = extract_offer_fields_regex(
            hiring_approval_text=hiring_text,
            cv_text=cv_text,
            passport_text=passport_text,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not raised
        return render_template(
            "index.html",
            mandatory_fields=MANDATORY_FIELDS,
            templates=fields_module.TEMPLATES,
            extraction_error=f"Automatic extraction failed: {exc}",
        )

    prefill, business_unit_display, banner_notes = map_extraction_to_prefill(result)
    if passport_image_note:
        banner_notes.append(passport_image_note)

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
    resolved = resolved_offer_from_mapping(request.form)
    validation = validate_offer(resolved)
    preview_text = build_preview(resolved, validation)
    offer_json = serialize_offer(resolved, request.form.get("requested_by", "").strip())
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

    resolved, requested_by = deserialize_offer(offer_json)

    reference_store = ReferenceStore(REFERENCE_STORE_PATH)
    storage = app.config["STORAGE_BACKEND_FACTORY"]()

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
