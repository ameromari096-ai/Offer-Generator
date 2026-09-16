"""Desktop entry point: runs the Offer Agent in a native window.

Fully local — nothing is exposed to the network (the server binds only
to 127.0.0.1, on a random free port picked at startup), so there is no
public URL anyone else could reach, unlike the web deployment. Uses the
same webapp.app Flask application via waitress, a pure-Python WSGI
server that — unlike gunicorn — runs on Windows.

Storage defaults to LocalDevStorageBackend (this computer only), same as
the web app. If %APPDATA%\\OfferAgent\\config.json has a filled-in
"sharepoint" section, that's used instead — see desktop/config.py and
the README's "Windows desktop app" section for the one-time Azure AD
setup this requires. Misconfiguration (or SharePoint access not granted
yet) surfaces as a clear error on the result page rather than silently
falling back — per the same "never silently invent a destination" rule
the web app follows.
"""

from __future__ import annotations

import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import webview
from waitress import serve

from desktop.config import ensure_example_config, load_sharepoint_config
from webapp.app import app

HOST = "127.0.0.1"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _run_server(port: int) -> None:
    serve(app, host=HOST, port=port, threads=4)


def _configure_storage() -> None:
    ensure_example_config()
    sharepoint_config = load_sharepoint_config()
    if not sharepoint_config:
        return  # config.json absent/not filled in yet -> stay on local storage

    from offer_agent.sharepoint_storage import SharePointStorageBackend

    def _sharepoint_factory():
        return SharePointStorageBackend.from_site_url(
            tenant_id=sharepoint_config["tenant_id"],
            client_id=sharepoint_config["client_id"],
            client_secret=sharepoint_config["client_secret"],
            site_url=sharepoint_config["site_url"],
            folder_path=sharepoint_config.get("folder_path", ""),
            drive_name=sharepoint_config.get("drive_name") or None,
        )

    app.config["STORAGE_BACKEND_FACTORY"] = _sharepoint_factory
    app.config["STORAGE_LABEL"] = "sharepoint"


def main() -> None:
    _configure_storage()

    port = _free_port()
    server_thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    server_thread.start()

    webview.create_window(
        "Offer Agent — PureHealth",
        f"http://{HOST}:{port}/",
        width=1024,
        height=820,
        min_size=(760, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
