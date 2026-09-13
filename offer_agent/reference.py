"""Two-digit random reference number generation.

Exactly one {{Ref}} is generated per approved offer. It is a bare, random
two-digit whole number (00-99) with no month, year, letters, prefix,
suffix, separators, candidate initials, or Business Unit encoded in it, and
it carries no sequence, counter, or uniqueness/duplicate/reservation
semantics.

If document creation is retried for the same approved offer, the
previously generated reference is reused rather than a new one being
drawn. Callers identify "the same approved offer" with a stable
``offer_id`` they mint once, at the moment of approval, and pass on every
retry for that offer.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
from pathlib import Path
from typing import Optional


class ReferenceGenerationError(RuntimeError):
    """Raised when reference generation fails after one retry."""


def generate_reference(rng: Optional[random.Random] = None) -> str:
    """Draw one random whole number from 0 through 99, as exactly two digits."""
    source = rng or random
    number = source.randint(0, 99)
    return f"{number:02d}"


def generate_reference_with_retry(rng: Optional[random.Random] = None) -> str:
    try:
        return generate_reference(rng)
    except Exception:
        try:
            return generate_reference(rng)
        except Exception as exc:
            raise ReferenceGenerationError(
                "Reference generation failed twice; stopping rather than asking "
                "the user to supply a reference manually."
            ) from exc


class ReferenceStore:
    """Durable offer_id -> reference mapping so retries reuse the same ref.

    Backed by a small JSON file. Concurrent access is not a design goal
    here (one offer is handled at a time); writes are atomic (write to a
    temp file then replace) so a crash mid-write cannot corrupt the store.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, data: dict) -> None:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=self.path.name, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, sort_keys=True)
        except BaseException:
            os.unlink(tmp_name)
            raise
        os.replace(tmp_name, self.path)

    def get(self, offer_id: str) -> Optional[str]:
        return self._read().get(offer_id)

    def set(self, offer_id: str, reference: str) -> None:
        data = self._read()
        data[offer_id] = reference
        self._write(data)


def get_or_create_reference(
    store: ReferenceStore,
    offer_id: str,
    rng: Optional[random.Random] = None,
) -> tuple[str, bool]:
    """Return (reference, was_newly_generated) for the given offer_id.

    Reuses an existing reference for this offer_id if one was already
    generated (e.g. a retried document-creation attempt after a PDF
    conversion or storage failure). Never draws a second reference for the
    same offer_id.
    """
    existing = store.get(offer_id)
    if existing is not None:
        return existing, False

    reference = generate_reference_with_retry(rng)
    store.set(offer_id, reference)
    return reference, True
