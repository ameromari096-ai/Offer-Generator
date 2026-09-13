"""Fills {{placeholder}} tokens in the approved Word template.

Only the literal ``{{...}}`` text placeholders are touched. Word
MERGEFIELD field codes present in these templates (``REF_NO``,
``CONTRACT_TYPE``, ``MONTHLY_TOTAL_SALARY``) are legacy mail-merge fields,
not plain text runs — they are structurally distinct from the ``{{...}}``
runs and this module never reads or writes them, so legal wording,
branding, and those field codes are left exactly as authored.

A placeholder whose resolved value is ``None`` is retained verbatim
(exact spelling, braces included) rather than being blanked out, per the
"missing data" rule: unresolved placeholders must survive into the
document and be disclosed, never silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Optional

import docx

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


@dataclass
class FillResult:
    output_path: Path
    resolved_count: int
    unresolved_placeholders: list[str] = field(default_factory=list)
    unexpected_placeholders: list[str] = field(default_factory=list)


def _iter_paragraphs(parent) -> Iterable:
    if hasattr(parent, "paragraphs"):
        for paragraph in parent.paragraphs:
            yield paragraph
    if hasattr(parent, "tables"):
        for table in parent.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from _iter_paragraphs(cell)


def _all_paragraphs(document) -> Iterable:
    yield from _iter_paragraphs(document)
    for section in document.sections:
        for header_or_footer in (
            section.header,
            section.footer,
            section.first_page_header,
            section.first_page_footer,
            section.even_page_header,
            section.even_page_footer,
        ):
            if header_or_footer is not None:
                yield from _iter_paragraphs(header_or_footer)


def find_placeholders_in_document(path: Path) -> set[str]:
    """Return the set of distinct ``{{...}}`` keys found in a docx file."""
    document = docx.Document(str(path))
    found: set[str] = set()
    for paragraph in _all_paragraphs(document):
        full_text = "".join(run.text for run in paragraph.runs)
        for match in PLACEHOLDER_PATTERN.finditer(full_text):
            found.add(match.group(1))
    return found


def fill_placeholders(
    template_path: Path,
    output_path: Path,
    values: Dict[str, Optional[str]],
) -> FillResult:
    """Populate the template's placeholders and save the result.

    ``values`` maps the exact placeholder key (without braces, e.g.
    ``"candidate full name"``) to its resolved string, or to ``None`` when
    the value is confirmed unavailable and the placeholder must be
    retained.

    A placeholder found in the template that has no entry in ``values`` at
    all is left untouched and reported separately (``unexpected_placeholders``)
    — this should not happen with the approved templates, and signals the
    template and the field registry have drifted apart.
    """
    document = docx.Document(str(template_path))

    resolved_count = 0
    unresolved: set[str] = set()
    unexpected: set[str] = set()

    def _substitute(match: re.Match) -> str:
        nonlocal resolved_count
        key = match.group(1)
        if key not in values:
            unexpected.add(match.group(0))
            return match.group(0)
        value = values[key]
        if value is None:
            unresolved.add(match.group(0))
            return match.group(0)
        resolved_count += 1
        return str(value)

    for paragraph in _all_paragraphs(document):
        full_text = "".join(run.text for run in paragraph.runs)
        if "{{" not in full_text:
            continue
        new_text = PLACEHOLDER_PATTERN.sub(_substitute, full_text)
        if new_text == full_text:
            continue
        runs = paragraph.runs
        if not runs:
            continue
        runs[0].text = new_text
        for run in runs[1:]:
            run.text = ""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output_path))

    return FillResult(
        output_path=output_path,
        resolved_count=resolved_count,
        unresolved_placeholders=sorted(unresolved),
        unexpected_placeholders=sorted(unexpected),
    )
