"""Desktop entry point: runs the Offer Agent in a native window.

Fully local — nothing is exposed to the network (the server binds only
to 127.0.0.1, on a random free port picked at startup), so there is no
public URL anyone else could reach, unlike the web deployment. Uses the
same webapp.app Flask application (LocalDevStorageBackend, free regex
extraction, no API keys) via waitress, a pure-Python WSGI server that —
unlike gunicorn — runs on Windows.
"""

from __future__ import annotations

import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import webview
from waitress import serve

from webapp.app import app

HOST = "127.0.0.1"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _run_server(port: int) -> None:
    serve(app, host=HOST, port=port, threads=4)


def main() -> None:
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
