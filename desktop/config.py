"""Local, file-based settings for the desktop app.

A double-click .exe shouldn't require setting Windows environment
variables (the friction that made this desktop app hard to configure in
the first place) — instead, a plain JSON file the user can open in
Notepad. Created automatically on first run with an empty template if
one doesn't exist yet.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "OfferAgent"
CONFIG_PATH = CONFIG_DIR / "config.json"

_SHAREPOINT_REQUIRED_KEYS = ("tenant_id", "client_id", "client_secret", "site_url")

_EXAMPLE_CONFIG = {
    "sharepoint": {
        "tenant_id": "",
        "client_id": "",
        "client_secret": "",
        "site_url": "https://contoso.sharepoint.com/sites/HR",
        "folder_path": "Offers",
        "drive_name": "",
    }
}


def ensure_example_config() -> Path:
    """Creates config.json with an empty template if it doesn't exist yet.

    Never overwrites an existing file — safe to call on every startup.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(_EXAMPLE_CONFIG, indent=2))
    return CONFIG_PATH


def load_sharepoint_config(config_path: Path = CONFIG_PATH) -> Optional[dict]:
    """Returns the sharepoint config dict if present and fully filled in,
    else None (meaning: fall back to local storage)."""
    if not config_path.is_file():
        return None
    try:
        data = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    sharepoint = data.get("sharepoint")
    if not isinstance(sharepoint, dict):
        return None
    if not all(sharepoint.get(key) for key in _SHAREPOINT_REQUIRED_KEYS):
        return None
    return sharepoint
