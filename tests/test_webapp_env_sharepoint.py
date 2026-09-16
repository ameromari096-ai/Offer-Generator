"""webapp.app must switch its default STORAGE_BACKEND_FACTORY to SharePoint
when SHAREPOINT_TENANT_ID (and friends) are present in the environment at
import time - this is how a hosted deployment (e.g. behind the Power Apps
API) is wired to SharePoint, mirroring desktop/app.py's config-file-driven
equivalent but via env vars, since a hosted server has no per-user
%APPDATA%\\OfferAgent\\config.json to read.
"""

import importlib
import sys


def _reload_app_module():
    for name in ("webapp.app", "webapp.api"):
        sys.modules.pop(name, None)
    return importlib.import_module("webapp.app")


def test_sharepoint_env_vars_switch_default_backend(monkeypatch):
    monkeypatch.setenv("SHAREPOINT_TENANT_ID", "tenant-1")
    monkeypatch.setenv("SHAREPOINT_CLIENT_ID", "client-1")
    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", "secret-1")
    monkeypatch.setenv("SHAREPOINT_SITE_URL", "https://contoso.sharepoint.com/sites/HR")

    app_module = _reload_app_module()
    try:
        assert app_module.app.config["STORAGE_LABEL"] == "sharepoint"
        from offer_agent.sharepoint_storage import SharePointStorageBackend

        backend = app_module.app.config["STORAGE_BACKEND_FACTORY"]()
        assert isinstance(backend, SharePointStorageBackend)
        assert backend.site_hostname == "contoso.sharepoint.com"
    finally:
        for key in (
            "SHAREPOINT_TENANT_ID",
            "SHAREPOINT_CLIENT_ID",
            "SHAREPOINT_CLIENT_SECRET",
            "SHAREPOINT_SITE_URL",
        ):
            monkeypatch.delenv(key, raising=False)
        _reload_app_module()  # restore the default (local) config for later tests


def test_without_env_vars_default_backend_is_local():
    app_module = _reload_app_module()
    assert app_module.app.config["STORAGE_LABEL"] == "local"
