import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import desktop.config as cfg


def test_ensure_example_config_creates_file_once(tmp_path, monkeypatch):
    config_dir = tmp_path / "OfferAgent"
    config_path = config_dir / "config.json"
    monkeypatch.setattr(cfg, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cfg, "CONFIG_PATH", config_path)

    returned = cfg.ensure_example_config()
    assert returned == config_path
    assert config_path.is_file()
    template = json.loads(config_path.read_text())
    assert "sharepoint" in template
    assert template["sharepoint"]["tenant_id"] == ""

    # A user filling in the file must never be clobbered by a later call.
    config_path.write_text(json.dumps({"sharepoint": {"tenant_id": "already-configured"}}))
    cfg.ensure_example_config()
    assert json.loads(config_path.read_text())["sharepoint"]["tenant_id"] == "already-configured"


def test_load_sharepoint_config_missing_file_returns_none(tmp_path):
    assert cfg.load_sharepoint_config(tmp_path / "does-not-exist.json") is None


def test_load_sharepoint_config_incomplete_returns_none(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sharepoint": {"tenant_id": "t", "client_id": "c"}}))  # missing secret/site_url
    assert cfg.load_sharepoint_config(path) is None


def test_load_sharepoint_config_no_sharepoint_key_returns_none(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"something_else": {}}))
    assert cfg.load_sharepoint_config(path) is None


def test_load_sharepoint_config_invalid_json_returns_none(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not valid json")
    assert cfg.load_sharepoint_config(path) is None


def test_load_sharepoint_config_complete_returns_dict(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "sharepoint": {
                    "tenant_id": "tenant-1",
                    "client_id": "client-1",
                    "client_secret": "secret-1",
                    "site_url": "https://contoso.sharepoint.com/sites/HR",
                    "folder_path": "Offers",
                }
            }
        )
    )
    result = cfg.load_sharepoint_config(path)
    assert result["tenant_id"] == "tenant-1"
    assert result["folder_path"] == "Offers"
