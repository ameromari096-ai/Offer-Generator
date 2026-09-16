"""Filesystem locations shared by the HTML web app and the JSON API.

Kept separate from webapp/app.py so webapp/api.py can use the same paths
without importing app.py (which would create a circular import once app.py
registers the API blueprint).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# When PyInstaller-frozen (the Windows desktop build), bundled read-only
# resources (this package, the docx templates) live under sys._MEIPASS,
# extracted fresh into a temp dir each run - never a place to write
# generated contracts, the reference store, or the audit log. Those go to
# a writable per-user directory instead. Unfrozen (normal dev / the web
# deployment), behavior is unchanged: everything lives under the repo.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    DATA_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "OfferAgent"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"

STORAGE_DIR = DATA_DIR / "storage"
TEMPLATES_DIR = BASE_DIR / "templates"
REFERENCE_STORE_PATH = DATA_DIR / "reference_store.json"
AUDIT_LOG_PATH = DATA_DIR / "audit.jsonl"
