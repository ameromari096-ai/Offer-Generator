"""SharePoint implementation of ``StorageBackend``, via Microsoft Graph.

Uses an Azure AD (Entra ID) app registration authenticating with the
OAuth2 client-credentials flow (app-only, no signed-in user) — the
SharePoint equivalent of the Google Drive backend's service account.

Scope the app's Graph permission to **Sites.Selected** (least privilege)
and grant it access to just this one site via a Graph permission grant —
never the tenant-wide Sites.ReadWrite.All. This mirrors sharing one Drive
folder with a service account instead of granting access to an entire
Drive: the app should only ever be able to reach the one destination this
deployment actually uses.

This backend never touches SharePoint's own sharing/permissions — it
only saves into a location whose existing access control already governs
who can open the file, and reads back the ``webUrl`` SharePoint already
assigned it. It never creates a public/anonymous sharing link.

Uploads use Graph's simple-upload endpoint (a single PUT), which is
capped at 4 MB per file — comfortably above the size of a generated
DOCX/PDF contract (well under 1 MB each). A future template that grows
past that would need the resumable upload-session API instead; this
backend does not implement that.
"""

from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import quote, urlparse

from .storage import StorageError, StoredFile

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def parse_site_url(url: str) -> Tuple[str, str]:
    """Splits a SharePoint site URL into (hostname, site_path).

    e.g. ``https://contoso.sharepoint.com/sites/HR`` ->
    ``("contoso.sharepoint.com", "sites/HR")``.
    """
    parsed = urlparse(url)
    hostname = parsed.netloc
    path = parsed.path.strip("/")
    if not hostname or not path:
        raise ValueError(f"Not a valid SharePoint site URL: {url!r}")
    return hostname, path


def _encode_path(path: str) -> str:
    return "/".join(quote(segment, safe="") for segment in path.strip("/").split("/") if segment)


class SharePointStorageBackend:
    """Saves contracts into one folder of one SharePoint document library."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        site_hostname: str,
        site_path: str,
        folder_path: str = "",
        drive_name: Optional[str] = None,
        *,
        session=None,
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.site_hostname = site_hostname
        self.site_path = site_path.strip("/")
        self.folder_path = folder_path.strip("/")
        self.drive_name = drive_name
        self._session = session  # injectable for tests; defaults to `requests` module

        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._site_id: Optional[str] = None
        self._drive_id: Optional[str] = None

    @classmethod
    def from_site_url(
        cls,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        site_url: str,
        folder_path: str = "",
        drive_name: Optional[str] = None,
        *,
        session=None,
    ) -> "SharePointStorageBackend":
        hostname, site_path = parse_site_url(site_url)
        return cls(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            site_hostname=hostname,
            site_path=site_path,
            folder_path=folder_path,
            drive_name=drive_name,
            session=session,
        )

    @classmethod
    def from_env(cls) -> "SharePointStorageBackend":
        """Build from SHAREPOINT_TENANT_ID / SHAREPOINT_CLIENT_ID /
        SHAREPOINT_CLIENT_SECRET / SHAREPOINT_SITE_URL, with optional
        SHAREPOINT_FOLDER_PATH and SHAREPOINT_DRIVE_NAME."""
        import os

        env_required = {
            "tenant_id": "SHAREPOINT_TENANT_ID",
            "client_id": "SHAREPOINT_CLIENT_ID",
            "client_secret": "SHAREPOINT_CLIENT_SECRET",
        }
        values = {}
        for key, env_name in env_required.items():
            value = os.environ.get(env_name)
            if not value:
                raise StorageError(f"{env_name} is not set; cannot authenticate to SharePoint.")
            values[key] = value

        site_url = os.environ.get("SHAREPOINT_SITE_URL")
        if not site_url:
            raise StorageError(
                "SHAREPOINT_SITE_URL is not set (e.g. https://contoso.sharepoint.com/sites/HR)."
            )

        return cls.from_site_url(
            tenant_id=values["tenant_id"],
            client_id=values["client_id"],
            client_secret=values["client_secret"],
            site_url=site_url,
            folder_path=os.environ.get("SHAREPOINT_FOLDER_PATH", ""),
            drive_name=os.environ.get("SHAREPOINT_DRIVE_NAME"),
        )

    # --- HTTP plumbing -------------------------------------------------

    @property
    def _http(self):
        if self._session is not None:
            return self._session
        try:
            import requests
        except ImportError as exc:
            raise StorageError(
                "The 'requests' package is not installed; add it to your environment "
                "to use SharePointStorageBackend."
            ) from exc
        self._session = requests
        return self._session

    def _get_token(self) -> str:
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token
        try:
            response = self._http.post(
                f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"SharePoint authentication request failed: {exc}") from exc

        if response.status_code != 200:
            raise StorageError(
                f"SharePoint authentication failed ({response.status_code}): {response.text}"
            )

        payload = response.json()
        self._access_token = payload["access_token"]
        self._token_expiry = time.time() + payload.get("expires_in", 3600)
        return self._access_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _get_site_id(self) -> str:
        if self._site_id:
            return self._site_id
        url = f"{GRAPH_BASE}/sites/{self.site_hostname}:/{self.site_path}"
        response = self._http.get(url, headers=self._headers(), timeout=30)
        if response.status_code != 200:
            raise StorageError(
                f"Could not resolve SharePoint site '{self.site_hostname}/{self.site_path}' "
                f"({response.status_code}): {response.text}"
            )
        self._site_id = response.json()["id"]
        return self._site_id

    def _get_drive_id(self) -> str:
        if self._drive_id:
            return self._drive_id
        site_id = self._get_site_id()
        if self.drive_name:
            response = self._http.get(
                f"{GRAPH_BASE}/sites/{site_id}/drives", headers=self._headers(), timeout=30
            )
            if response.status_code != 200:
                raise StorageError(f"Could not list document libraries ({response.status_code}): {response.text}")
            drives = response.json().get("value", [])
            match = next((d for d in drives if d.get("name") == self.drive_name), None)
            if not match:
                raise StorageError(f"No document library named '{self.drive_name}' found on this site.")
            self._drive_id = match["id"]
        else:
            response = self._http.get(
                f"{GRAPH_BASE}/sites/{site_id}/drive", headers=self._headers(), timeout=30
            )
            if response.status_code != 200:
                raise StorageError(f"Could not resolve the default document library ({response.status_code}): {response.text}")
            self._drive_id = response.json()["id"]
        return self._drive_id

    def _item_path_url(self, filename: str) -> str:
        drive_id = self._get_drive_id()
        full_path = f"{self.folder_path}/{filename}" if self.folder_path else filename
        return f"{GRAPH_BASE}/drives/{drive_id}/root:/{_encode_path(full_path)}"

    # --- StorageBackend interface ---------------------------------------

    def exists(self, filename: str) -> bool:
        response = self._http.get(self._item_path_url(filename), headers=self._headers(), timeout=30)
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        raise StorageError(
            f"SharePoint lookup failed for {filename!r} ({response.status_code}): {response.text}"
        )

    def save(self, local_path: Path, filename: str) -> StoredFile:
        if self.exists(filename):
            raise StorageError(f"Refusing to overwrite existing file in SharePoint: {filename}")

        mimetype, _ = mimetypes.guess_type(filename)
        data = Path(local_path).read_bytes()
        headers = self._headers()
        headers["Content-Type"] = mimetype or "application/octet-stream"

        response = self._http.put(
            f"{self._item_path_url(filename)}:/content", headers=headers, data=data, timeout=60
        )
        if response.status_code not in (200, 201):
            raise StorageError(
                f"SharePoint upload failed for {filename!r} ({response.status_code}): {response.text}"
            )

        payload = response.json()
        return StoredFile(
            filename=filename, secure_url=payload["webUrl"], destination_id=self._get_drive_id()
        )

    def destination_identifier(self) -> str:
        label = f"sharepoint:{self.site_hostname}/{self.site_path}"
        if self.folder_path:
            label += f"/{self.folder_path}"
        return label
