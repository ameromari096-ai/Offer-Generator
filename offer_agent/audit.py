"""Append-only audit trail for completed (or failed) offer generations.

Deliberately excludes anything the spec forbids recording: passport
details beyond name/nationality (which aren't stored here either — only
the resolved candidate name/nationality that also appear in the contract),
file contents, credentials, tokens, and connection details.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class AuditRecord:
    reference: str
    creation_timestamp: str
    requested_by: str
    candidate_name: str
    business_unit: str
    template_name: str
    job_title: str
    notice_period: str
    monthly_compensation: Dict[str, str]
    annual_compensation: Dict[str, str]
    currency: str
    input_filenames: List[str]
    user_overrides: Dict[str, str]
    unresolved_placeholders: List[str]
    destination_identifier: Optional[str]
    docx_filename: Optional[str]
    docx_secure_url: Optional[str]
    pdf_filename: Optional[str]
    pdf_secure_url: Optional[str]
    generation_status: str
    delivery_status: str
    warnings: List[str] = field(default_factory=list)

    @staticmethod
    def now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()


def write_audit_record(audit_log_path: Path, record: AuditRecord) -> None:
    """Append one JSON line to the audit log, atomically."""
    audit_log_path = Path(audit_log_path)
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(asdict(record), sort_keys=True)

    # Append atomically-ish: open in append mode and rely on POSIX append
    # semantics for a single line write; a temp-file+replace dance isn't
    # meaningful for an append-only log shared across offers.
    with audit_log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
