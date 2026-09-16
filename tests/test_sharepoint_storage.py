from pathlib import Path
from unittest.mock import MagicMock

import pytest

from offer_agent.sharepoint_storage import SharePointStorageBackend, parse_site_url
from offer_agent.storage import StorageError

SITE_URL = "https://contoso.sharepoint.com/sites/HR"


def test_parse_site_url():
    hostname, site_path = parse_site_url(SITE_URL)
    assert hostname == "contoso.sharepoint.com"
    assert site_path == "sites/HR"


def test_parse_site_url_rejects_non_site_url():
    with pytest.raises(ValueError):
        parse_site_url("https://contoso.sharepoint.com")


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


def _backend(session, **kwargs):
    return SharePointStorageBackend.from_site_url(
        tenant_id="tenant-1",
        client_id="client-1",
        client_secret="secret-1",
        site_url=SITE_URL,
        session=session,
        **kwargs,
    )


def test_get_token_caches_and_authenticates_with_client_credentials():
    session = MagicMock()
    session.post.return_value = _mock_response(200, {"access_token": "tok-abc", "expires_in": 3600})
    backend = _backend(session)

    token1 = backend._get_token()
    token2 = backend._get_token()  # should be cached, not a second POST

    assert token1 == "tok-abc"
    assert token2 == "tok-abc"
    assert session.post.call_count == 1

    _, kwargs = session.post.call_args
    assert kwargs["data"]["grant_type"] == "client_credentials"
    assert kwargs["data"]["scope"] == "https://graph.microsoft.com/.default"
    assert "login.microsoftonline.com/tenant-1" in session.post.call_args[0][0]


def test_get_token_failure_raises_storage_error():
    session = MagicMock()
    session.post.return_value = _mock_response(401, text="invalid client secret")
    backend = _backend(session)

    with pytest.raises(StorageError):
        backend._get_token()


def test_exists_false_when_not_found():
    session = MagicMock()
    session.post.return_value = _mock_response(200, {"access_token": "tok", "expires_in": 3600})
    session.get.side_effect = [
        _mock_response(200, {"id": "site-1"}),  # site resolution
        _mock_response(200, {"id": "drive-1"}),  # default drive resolution
        _mock_response(404, text="not found"),  # exists() lookup
    ]
    backend = _backend(session)

    assert backend.exists("Jane Doe - PureHealth - Employment Contract.docx") is False


def test_exists_true_when_found():
    session = MagicMock()
    session.post.return_value = _mock_response(200, {"access_token": "tok", "expires_in": 3600})
    session.get.side_effect = [
        _mock_response(200, {"id": "site-1"}),
        _mock_response(200, {"id": "drive-1"}),
        _mock_response(200, {"id": "item-1"}),
    ]
    backend = _backend(session)

    assert backend.exists("x.docx") is True


def test_save_uploads_and_returns_secure_url(tmp_path):
    local_file = tmp_path / "contract.docx"
    local_file.write_bytes(b"fake docx bytes")

    session = MagicMock()
    session.post.return_value = _mock_response(200, {"access_token": "tok", "expires_in": 3600})
    session.get.side_effect = [
        _mock_response(200, {"id": "site-1"}),
        _mock_response(200, {"id": "drive-1"}),
        _mock_response(404, text="not found"),  # exists() check inside save()
    ]
    session.put.return_value = _mock_response(
        201, {"id": "item-2", "webUrl": "https://contoso.sharepoint.com/sites/HR/Shared%20Documents/x.docx"}
    )
    backend = _backend(session, folder_path="Offers")

    stored = backend.save(local_file, "Jane Doe - PureHealth - Employment Contract.docx")

    assert stored.filename == "Jane Doe - PureHealth - Employment Contract.docx"
    assert stored.secure_url == "https://contoso.sharepoint.com/sites/HR/Shared%20Documents/x.docx"
    assert stored.destination_id == "drive-1"

    put_url = session.put.call_args[0][0]
    assert "drives/drive-1/root:/Offers/" in put_url
    assert put_url.endswith(":/content")


def test_save_refuses_to_overwrite_existing_file(tmp_path):
    local_file = tmp_path / "contract.docx"
    local_file.write_bytes(b"fake docx bytes")

    session = MagicMock()
    session.post.return_value = _mock_response(200, {"access_token": "tok", "expires_in": 3600})
    session.get.side_effect = [
        _mock_response(200, {"id": "site-1"}),
        _mock_response(200, {"id": "drive-1"}),
        _mock_response(200, {"id": "existing-item"}),  # exists() -> True
    ]
    backend = _backend(session)

    with pytest.raises(StorageError):
        backend.save(local_file, "x.docx")

    session.put.assert_not_called()


def test_uses_named_drive_when_specified():
    session = MagicMock()
    session.post.return_value = _mock_response(200, {"access_token": "tok", "expires_in": 3600})
    session.get.side_effect = [
        _mock_response(200, {"id": "site-1"}),
        _mock_response(
            200,
            {"value": [{"name": "Other Library", "id": "drive-x"}, {"name": "HR Contracts", "id": "drive-hr"}]},
        ),
        _mock_response(404),
    ]
    backend = _backend(session, drive_name="HR Contracts")

    assert backend.exists("x.docx") is False
    assert backend._drive_id == "drive-hr"


def test_destination_identifier_is_non_sensitive_label():
    session = MagicMock()
    backend = _backend(session, folder_path="Offers")
    assert backend.destination_identifier() == "sharepoint:contoso.sharepoint.com/sites/HR/Offers"


def test_from_env_requires_credentials(monkeypatch):
    for var in ("SHAREPOINT_TENANT_ID", "SHAREPOINT_CLIENT_ID", "SHAREPOINT_CLIENT_SECRET", "SHAREPOINT_SITE_URL"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(StorageError):
        SharePointStorageBackend.from_env()
