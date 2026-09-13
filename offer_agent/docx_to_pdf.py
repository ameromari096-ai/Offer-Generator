"""Converts the completed DOCX into a PDF via LibreOffice headless.

The PDF is always produced FROM the already-completed DOCX — this module
never renders a PDF independently from raw field values, so the DOCX and
PDF are guaranteed to carry identical values, reference, branding, and
wording.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class PdfConversionError(RuntimeError):
    """Raised when LibreOffice fails to convert the DOCX to PDF."""


def _find_soffice() -> str:
    for candidate in ("soffice", "libreoffice"):
        path = shutil.which(candidate)
        if path:
            return path
    raise PdfConversionError(
        "No LibreOffice ('soffice'/'libreoffice') executable found on PATH; "
        "cannot convert DOCX to PDF."
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
