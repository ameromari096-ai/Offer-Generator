"""Extracts plain text from uploaded hiring-approval / CV / passport files.

Supported: .pdf, .docx, .msg (Outlook), .eml, .txt. Images (for a passport
photo) are passed through as-is for vision input rather than text-extracted.
"""

from __future__ import annotations

import io
import re
import subprocess
import tempfile
from email import policy
from email.parser import BytesParser
from pathlib import Path

import docx as docx_lib
from pypdf import PdfReader

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class DocumentParseError(RuntimeError):
    pass


def is_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_SUFFIXES


def image_media_type(filename: str) -> str:
    return IMAGE_MEDIA_TYPES[Path(filename).suffix.lower()]


def _pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _docx_to_text(data: bytes) -> str:
    document = docx_lib.Document(io.BytesIO(data))

    parts = []

    def _walk(parent):
        for paragraph in parent.paragraphs:
            parts.append(paragraph.text)
        for table in getattr(parent, "tables", []):
            for row in table.rows:
                for cell in row.cells:
                    _walk(cell)

    _walk(document)
    return "\n".join(parts)


def _eml_bytes_to_text(data: bytes) -> str:
    msg = BytesParser(policy=policy.default).parsebytes(data)
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None:
        return ""
    text = body.get_content()
    if body.get_content_type() == "text/html":
        text = re.sub("<[^>]+>", " ", text)
    return text


def _msg_to_text(data: bytes) -> str:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        msg_path = tmp / "input.msg"
        msg_path.write_bytes(data)
        result = subprocess.run(
            ["msgconvert", "input.msg"],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        eml_path = tmp / "input.eml"
        if result.returncode != 0 or not eml_path.exists():
            raise DocumentParseError(
                f"Failed to convert .msg file (is msgconvert installed?): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return _eml_bytes_to_text(eml_path.read_bytes())


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _pdf_to_text(data)
    if suffix == ".docx":
        return _docx_to_text(data)
    if suffix == ".msg":
        return _msg_to_text(data)
    if suffix == ".eml":
        return _eml_bytes_to_text(data)
    if suffix == ".txt":
        return data.decode("utf-8", errors="replace")
    raise DocumentParseError(f"Unsupported file type: {suffix or '(none)'}")
