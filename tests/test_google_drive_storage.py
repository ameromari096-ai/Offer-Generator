from pathlib import Path
from unittest.mock import MagicMock

import pytest

from offer_agent.google_drive_storage import GoogleDriveStorageBackend, folder_id_from_share_url
from offer_agent.storage import StorageError

FOLDER_ID = "1ObSywx7unkdc8PCmUHE_vSFzG4F7-I4B"
SHARE_URL = f"https://drive.google.com/drive/folders/{FOLDER_ID}?usp=sharing"


def test_folder_id_from_share_url():
    assert folder_id_from_share_url(SHARE_URL) == FOLDER_ID


def test_folder_id_from_share_url_rejects_non_matching_url():
    with pytest.raises(ValueError):
        folder_id_from_share_url("https://example.com/not-a-drive-link")


def _mock_service(list_result=None, create_result=None):
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = list_result or {"files": []}
    service.files.return_value.create.return_value.execute.return_value = create_result or {}
    return service


def test_exists_false_when_no_matching_file():
    service = _mock_service(list_result={"files": []})
    backend = GoogleDriveStorageBackend(FOLDER_ID, service=service)
    assert backend.exists("Jane Doe - PureHealth - Employment Contract.docx") is False


def test_exists_true_when_matching_file_found():
    service = _mock_service(list_result={"files": [{"id": "abc", "name": "x.docx"}]})
    backend = GoogleDriveStorageBackend(FOLDER_ID, service=service)
    assert backend.exists("x.docx") is True

    # Query scoped to the configured folder and an exact, escaped filename.
    _, kwargs = service.files.return_value.list.call_args
    assert f"'{FOLDER_ID}' in parents" in kwargs["q"]
    assert "name = 'x.docx'" in kwargs["q"]


def test_save_uploads_and_returns_secure_url(tmp_path):
    local_file = tmp_path / "contract.docx"
    local_file.write_bytes(b"fake docx bytes")

    service = _mock_service(
        list_result={"files": []},
        create_result={"id": "file123", "webViewLink": "https://drive.google.com/file/d/file123/view"},
    )
    backend = GoogleDriveStorageBackend(FOLDER_ID, service=service)

    stored = backend.save(local_file, "Jane Doe - PureHealth - Employment Contract.docx")

    assert stored.filename == "Jane Doe - PureHealth - Employment Contract.docx"
    assert stored.secure_url == "https://drive.google.com/file/d/file123/view"
    assert stored.destination_id == FOLDER_ID

    _, kwargs = service.files.return_value.create.call_args
    assert kwargs["body"]["parents"] == [FOLDER_ID]
    assert kwargs["body"]["name"] == "Jane Doe - PureHealth - Employment Contract.docx"


def test_save_refuses_to_overwrite_existing_file(tmp_path):
    local_file = tmp_path / "contract.docx"
    local_file.write_bytes(b"fake docx bytes")

    service = _mock_service(list_result={"files": [{"id": "existing", "name": "x.docx"}]})
    backend = GoogleDriveStorageBackend(FOLDER_ID, service=service)

    with pytest.raises(StorageError):
        backend.save(local_file, "x.docx")

    service.files.return_value.create.assert_not_called()


def test_save_never_touches_permissions_api(tmp_path):
    local_file = tmp_path / "contract.docx"
    local_file.write_bytes(b"fake docx bytes")

    service = _mock_service(
        list_result={"files": []},
        create_result={"id": "file123", "webViewLink": "https://drive.google.com/file/d/file123/view"},
    )
    backend = GoogleDriveStorageBackend(FOLDER_ID, service=service)
    backend.save(local_file, "x.docx")

    service.permissions.assert_not_called()


def test_destination_identifier_is_non_sensitive_label():
    backend = GoogleDriveStorageBackend(FOLDER_ID, service=_mock_service())
    assert backend.destination_identifier() == f"google-drive-folder:{FOLDER_ID}"


def test_requires_service_or_credentials_path():
    with pytest.raises(ValueError):
        GoogleDriveStorageBackend(FOLDER_ID)


def test_from_env_requires_credentials_file(monkeypatch):
    monkeypatch.delenv("GDRIVE_SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.delenv("GDRIVE_OFFER_FOLDER_ID", raising=False)
    with pytest.raises(StorageError):
        GoogleDriveStorageBackend.from_env(default_folder_id=FOLDER_ID)
