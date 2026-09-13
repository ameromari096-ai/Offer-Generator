# Offer Agent

Generates approved employment contracts (DOCX + PDF) from a hiring
approval, candidate CV, an optional passport, and user overrides —
selecting the correct Word template by Business Unit, populating its
`{{placeholder}}` fields, and never touching legal wording or branding.

The full behavioral spec — source priority, the notice-period extraction
rule, salary math, the two-digit reference rule, filenames, storage,
audit, and error handling — lives in
[`.claude/skills/offer-agent/SKILL.md`](.claude/skills/offer-agent/SKILL.md).
This repository is the implementation behind that skill:

- `offer_agent/` — the deterministic parts of the workflow (template
  selection, salary calculation, reference generation, filename/conflict
  handling, DOCX population, PDF conversion, storage interface, audit
  logging, preview rendering, validation, and the end-to-end orchestrator).
  Extraction from free-text sources and priority/conflict resolution is a
  language-understanding task the calling agent performs — this package
  only enforces the mechanical rules exactly and identically every time.
- `templates/` — the two approved Word templates
  (`PureHealth_Employment_Contract.docx`, `TalentOne_Employment_Contract.docx`).
- `tests/` — unit and end-to-end tests.

## Setup

```bash
pip install -r requirements-dev.txt
```

DOCX→PDF conversion shells out to LibreOffice. The `libreoffice-core`
package alone is **not** enough — it fails to load any document
("source file could not be loaded") because the Writer component isn't
installed. Install:

```bash
apt-get install -y libreoffice-writer
```

## Running the tests

```bash
pytest
```

Tests marked `slow` exercise a real LibreOffice DOCX→PDF conversion.

## Wiring up real storage

`offer_agent.storage.StorageBackend` is the integration point for "the
administrator-configured authenticated organizational storage action"
the spec requires (e.g. a SharePoint/OneDrive/Google Drive connector).
No destination is hard-coded here — implement `StorageBackend` against
whatever authenticated connector this deployment has configured and pass
it into `finalize_offer(...)`. `offer_agent.storage.LocalDevStorageBackend`
is provided only for local development and tests; it is **not** an
approved destination and must never be used to handle real candidate
data. If no backend is configured, `NotConfiguredStorageBackend` makes
every call fail loudly instead of silently falling back to a local path.

## Minimal end-to-end example

```python
from pathlib import Path
from offer_agent.models import ResolvedOffer, FieldValue
from offer_agent.reference import ReferenceStore
from offer_agent.storage import LocalDevStorageBackend  # dev/test only
from offer_agent.validation import validate_offer
from offer_agent.preview import build_preview
from offer_agent.workflow import finalize_offer, format_completion_output

resolved = ResolvedOffer(
    offer_id="offer-2026-09-13-jane-doe",
    business_unit_raw="PureHealth",
    fields={
        "candidate full name": FieldValue("Jane Marie Doe", "cv"),
        "candidate phone number": FieldValue("+971500000000", "cv"),
        "candidate email address": FieldValue("jane@example.com", "cv"),
        "candidate first name": FieldValue("Jane", "calculation"),
        "job title": FieldValue("Software Engineer", "hiring_approval"),
        "nationality": FieldValue("Canadian", "cv"),
        "line manager": FieldValue("John Smith", "hiring_approval"),
        "department": FieldValue("Engineering", "hiring_approval"),
        "notice period": FieldValue("30", "hiring_approval"),
        "Total Salary": FieldValue("20500", "hiring_approval"),
    },
)

# 1. Mandatory preview — show this and get explicit approval first.
validation = validate_offer(resolved)
print(build_preview(resolved, validation))

# 2. Only after approval:
outcome = finalize_offer(
    resolved,
    templates_dir=Path("templates"),
    reference_store=ReferenceStore(Path("data/reference_store.json")),
    storage=LocalDevStorageBackend(Path("data/storage")),  # swap for real storage
    audit_log_path=Path("data/audit.jsonl"),
    requested_by="hr@example.com",
)
print(format_completion_output(outcome))
```
