"""Converts the completed DOCX into a PDF via LibreOffice headless.

The PDF is always produced FROM the already-completed DOCX — this module
never renders a PDF independently from raw field values, so the DOCX and
PDF are guaranteed to carry identical values, reference, branding, and
wording.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class PdfConversionError(RuntimeError):
    """Raised when LibreOffice fails to convert the DOCX to PDF."""


# LibreOffice's Windows installer doesn't add soffice.exe to PATH, unlike
# most Linux package managers — check the standard install locations
# (both Program Files variants, either drive layout) before giving up.
_WINDOWS_FALLBACK_PATHS = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


def _find_soffice() -> str:
    for candidate in ("soffice", "libreoffice"):
        path = shutil.which(candidate)
        if path:
            return path

    if sys.platform == "win32":
        for candidate in _WINDOWS_FALLBACK_PATHS:
            if os.path.isfile(candidate):
                return candidate

    raise PdfConversionError(
        "No LibreOffice ('soffice'/'libreoffice') executable found on PATH"
        + (" or in the standard Program Files install location" if sys.platform == "win32" else "")
        + "; cannot convert DOCX to PDF. Install LibreOffice"
        + (" (https://www.libreoffice.org/download/) and re-run" if sys.platform == "win32" else "")
        + "."
    )


def convert_docx_to_pdf(docx_path: Path, output_path: Path, timeout: int = 120) -> Path:
    """Convert ``docx_path`` to a PDF at exactly ``output_path``.

    LibreOffice's ``--convert-to`` only lets you choose an output
    directory (the filename is derived from the input), so conversion is
    done into a scratch directory and the result is then moved/renamed to
    ``output_path``.
    """
    docx_path = Path(docx_path)
    output_path = Path(output_path)
    if not docx_path.is_file():
        raise PdfConversionError(f"DOCX not found for conversion: {docx_path}")

    soffice = _find_soffice()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as scratch_dir:
        cmd = [
            soffice,
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            scratch_dir,
            str(docx_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfConversionError(
                f"LibreOffice conversion timed out after {timeout}s for {docx_path}"
            ) from exc

        produced = Path(scratch_dir) / (docx_path.stem + ".pdf")
        if result.returncode != 0 or not produced.is_file():
            raise PdfConversionError(
                "LibreOffice conversion failed "
                f"(exit code {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
            )

        shutil.move(str(produced), str(output_path))

    return output_path
