"""Google Drive implementation of ``StorageBackend``.

Uses a Google service account (not an interactive OAuth login) so the
agent can save files unattended. A service account only sees files and
folders that have been explicitly shared with it — sharing the *link* is
not enough — so the one-time setup is:

1. Create a Google Cloud project (or reuse one) and enable the Google
   Drive API.
2. Create a service account in that project and download its JSON key.
3. Share the destination Drive folder with the service account's email
   address (the ``client_email`` field in the JSON key) as **Editor**.
4. Point this backend at the key file and the folder id, either directly
   or via the ``GDRIVE_SERVICE_ACCOUNT_FILE`` / ``GDRIVE_OFFER_FOLDER_ID``
   environment variables (see ``from_env``).

This backend never calls the Drive permissions API — it only relies on
whatever sharing the folder already has, and never creates an "anyone
with the link" or other public permission. It also never overwrites an
existing file: ``save`` refuses if a file with the target name is already
in the folder (the workflow's own filename-conflict check normally
prevents this from being reached at all).
"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Optional

from .storage import StorageError, StoredFile

DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive",)

_FOLDER_URL_PATTERN = re.compile(r"/folders/([a-zA-Z0-9_-]+)")

# The administrator-configured destination folder for this deployment:
# https://drive.google.com/drive/folders/1ObSywx7unkdc8PCmUHE_vSFzG4F7-I4B
OFFER_FOLDER_ID = "1ObSywx7unkdc8PCmUHE_vSFzG4F7-I4B"


def folder_id_from_share_url(url: str) -> str:
    """Extract the folder id out of a Drive "share" URL.

    e.g. ``https://drive.google.com/drive/folders/<id>?usp=sharing`` -> ``<id>``.
    """
    match = _FOLDER_URL_PATTERN.search(url)
    if not match:
        raise ValueError(f"Could not find a folder id in Drive URL: {url!r}")
    return match.group(1)


def _escape_drive_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveStorageBackend:
    """Saves contracts into one pre-shared Google Drive folder."""

    def __init__(self, folder_id: str, *, service=None, credentials_path: Optional[str] = None):
        if service is None and credentials_path is None:
            raise ValueError("Provide either an already-built `service` or a `credentials_path`.")
        self.folder_id = folder_id
        self._service = service
        self._credentials_path = credentials_path

    @classmethod
    def from_service_account_file(cls, credentials_path: str, folder_id: str) -> "GoogleDriveStorageBackend":
        return cls(folder_id, credentials_path=credentials_path)

    @classmethod
    def from_env(cls, default_folder_id: Optional[str] = OFFER_FOLDER_ID) -> "GoogleDriveStorageBackend":
        """Build from ``GDRIVE_SERVICE_ACCOUNT_FILE`` and ``GDRIVE_OFFER_FOLDER_ID``.

        ``default_folder_id`` is used only if ``GDRIVE_OFFER_FOLDER_ID`` is unset;
        it defaults to this deployment's configured folder
        (https://drive.google.com/drive/folders/1ObSywx7unkdc8PCmUHE_vSFzG4F7-I4B).
        """
        import os

        credentials_path = os.environ.get("GDRIVE_SERVICE_ACCOUNT_FILE")
        folder_id = os.environ.get("GDRIVE_OFFER_FOLDER_ID", default_folder_id)
        if not credentials_path:
            raise StorageError(
                "GDRIVE_SERVICE_ACCOUNT_FILE is not set; cannot authenticate to Google Drive."
            )
        if not folder_id:
            raise StorageError(
                "GDRIVE_OFFER_FOLDER_ID is not set and no default_folder_id was provided."
            )
        return cls.from_service_account_file(credentials_path, folder_id)

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise StorageError(
                "google-api-python-client / google-auth are not installed; "
                "add them to your environment to use GoogleDriveStorageBackend."
            ) from exc

        try:
            credentials = service_account.Credentials.from_service_account_file(
                self._credentials_path, scopes=list(DRIVE_SCOPES)
            )
        except (FileNotFoundError, ValueError) as exc:
            raise StorageError(f"Could not load Google service account credentials: {exc}") from exc

        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return self._service

    def _find_file(self, filename: str) -> Optional[dict]:
        service = self._get_service()
        escaped = _escape_drive_query_value(filename)
        query = (
            f"'{self.folder_id}' in parents and name = '{escaped}' and trashed = false"
        )
        try:
            response = (
                service.files()
                .list(
                    q=query,
                    fields="files(id, name, webViewLink)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    pageSize=1,
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Google Drive lookup failed for {filename!r}: {exc}") from exc

        files = response.get("files", [])
        return files[0] if files else None

    def exists(self, filename: str) -> bool:
        return self._find_file(filename) is not None

    def save(self, local_path: Path, filename: str) -> StoredFile:
        if self.exists(filename):
            raise StorageError(f"Refusing to overwrite existing file in Drive folder: {filename}")

        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise StorageError(
                "google-api-python-client is not installed; add it to your environment "
                "to use GoogleDriveStorageBackend."
            ) from exc

        service = self._get_service()
        mimetype, _ = mimetypes.guess_type(filename)
        media = MediaFileUpload(str(local_path), mimetype=mimetype, resumable=False)
        metadata = {"name": filename, "parents": [self.folder_id]}

        try:
            created = (
                service.files()
                .create(
                    body=metadata,
                    media_body=media,
                    fields="id, webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Google Drive upload failed for {filename!r}: {exc}") from exc

        secure_url = created.get("webViewLink") or f"https://drive.google.com/file/d/{created['id']}/view"
        return StoredFile(filename=filename, secure_url=secure_url, destination_id=self.folder_id)

    def destination_identifier(self) -> str:
        return f"google-drive-folder:{self.folder_id}"
