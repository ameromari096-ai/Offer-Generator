"""The HTML routes (/, /extract, /preview, /approve) have no login of
their own by default - fine for the desktop app (127.0.0.1 only), not for
a deployment that sits behind the Power Apps API. Setting both
WEBAPP_BASIC_AUTH_USER and WEBAPP_BASIC_AUTH_PASSWORD must gate them with
HTTP Basic Auth, while /api/* (its own X-API-Key check) and /healthz stay
reachable regardless.
"""

import base64

from webapp.app import app


def _basic_auth_header(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_html_routes_open_by_default():
    client = app.test_client()
    assert client.get("/").status_code == 200


def test_basic_auth_blocks_html_routes_when_configured(monkeypatch):
    monkeypatch.setenv("WEBAPP_BASIC_AUTH_USER", "hr")
    monkeypatch.setenv("WEBAPP_BASIC_AUTH_PASSWORD", "s3cret")
    client = app.test_client()

    resp = client.get("/")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers

    resp = client.get("/", headers=_basic_auth_header("hr", "wrong"))
    assert resp.status_code == 401

    resp = client.get("/", headers=_basic_auth_header("hr", "s3cret"))
    assert resp.status_code == 200


def test_basic_auth_never_gates_healthz_or_api(monkeypatch):
    monkeypatch.setenv("WEBAPP_BASIC_AUTH_USER", "hr")
    monkeypatch.setenv("WEBAPP_BASIC_AUTH_PASSWORD", "s3cret")
    monkeypatch.setenv("OFFER_AGENT_API_KEY", "test-key-123")
    client = app.test_client()

    assert client.get("/healthz").status_code == 200
    # No API key given -> the API's own 401, never the basic-auth 401 with WWW-Authenticate.
    resp = client.post("/api/preview", json={})
    assert resp.status_code == 401
    assert "WWW-Authenticate" not in resp.headers
