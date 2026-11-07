#!/usr/bin/env python3
"""Start the Connect Suggests demo: the web app plus the challenge's Yext mock, in one process.

    python3 run.py

Standard library only. Set YEXT_API_KEY in .env to write to the real Yext sandbox as well.
"""
from __future__ import annotations

import os
import sys
import threading
from http.server import ThreadingHTTPServer

sys.dont_write_bytecode = True  # Leave the challenge package folder untouched.

from connect import config  # noqa: E402
from connect.engine import Engine  # noqa: E402
from connect.service import Service  # noqa: E402
from connect.store import Store  # noqa: E402
from connect.web import make_handler  # noqa: E402
from connect.yext import YextClient  # noqa: E402


def start_mock(port: int = 0) -> str:
    """Run the package's mock on a private port. Its state file goes in var/, not in the package."""
    mock_dir = config.DATA_DIR / "mock_api"
    if not (mock_dir / "server.py").exists():
        sys.exit(f"Can't find the challenge package at {config.DATA_DIR}. Set CONNECT_DATA_DIR to its folder.")
    sys.path.insert(0, str(mock_dir))
    os.environ.setdefault("MOCK_QUIET", "1")
    import server as mock_server

    config.VAR_DIR.mkdir(parents=True, exist_ok=True)
    mock_server.STATE_FILE = str(config.VAR_DIR / "mock_state.json")
    mock_server.STORE = mock_server.Store()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), mock_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}"


def main() -> None:
    mock_url = start_mock()
    sandbox = YextClient(config.SANDBOX_URL, config.SANDBOX_KEY) if config.SANDBOX_KEY else None
    service = Service(Engine(), Store(config.VAR_DIR / "connect.db"), YextClient(mock_url, "demo"), sandbox)
    threading.Thread(target=service.overview, daemon=True).start()
    httpd = ThreadingHTTPServer((config.HOST, config.PORT), make_handler(service))
    print(f"Connect Suggests: http://127.0.0.1:{config.PORT}")
    print("Writes go to:", "the Yext sandbox and the local mock" if sandbox else "the local mock only (no YEXT_API_KEY)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
