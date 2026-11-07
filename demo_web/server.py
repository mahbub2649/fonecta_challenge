#!/usr/bin/env python3
"""The public demo: the same Connect backend with a passcode in front of the console. It only writes to the mock.

    CONNECT_DEMO_PASSCODE=... python3 demo_web/server.py

Owner links stay open without the passcode, as they do for a real owner. Everything else needs it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CONNECT_NO_SANDBOX"] = "1"  # The public demo never holds or uses a Yext key.

from connect.web import make_handler  # noqa: E402

STATIC = Path(__file__).parent / "static"
COOKIE = "connect_demo"
MOBILE = {"/mobile": ("mobile.html", "text/html; charset=utf-8"), "/mobile.css": ("mobile.css", "text/css; charset=utf-8"),
          "/mobile.js": ("mobile.js", "text/javascript; charset=utf-8"), "/future": ("future.html", "text/html; charset=utf-8"),
          "/future.js": ("future.js", "text/javascript; charset=utf-8")}
MAX_FAILED_LOGINS = 20
FAILED_LOGIN_WINDOW = 600


def make_demo_handler(service, passcode: str):
    base = make_handler(service)
    ticket = hmac.new(passcode.encode(), b"connect-demo-session", hashlib.sha256).hexdigest()
    failures = []
    lock = threading.Lock()

    class DemoHandler(base):
        def _is_local(self) -> bool:
            """The console's rule is "this machine only". Here, it means "has the passcode"."""
            for part in (self.headers.get("Cookie") or "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == COOKIE and hmac.compare_digest(value, ticket):
                    return True
            return False

        def _send(self, status: int, raw: bytes, content_type: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Robots-Tag", "noindex")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def _reply(self, status: int, data: dict, extra: dict | None = None) -> None:
            self._send(status, json.dumps(data).encode(), "application/json", extra)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/healthz":
                return self._reply(200, {"ok": True})
            if path in ("/", "/mobile", "/future") and not self._is_local():
                return self._send(200, (STATIC / "login.html").read_bytes(), "text/html; charset=utf-8")
            if path in MOBILE and self._is_local():
                name, content_type = MOBILE[path]
                return self._send(200, (STATIC / name).read_bytes(), content_type)
            return super().do_GET()

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/login":
                return self._login()
            if path == "/logout":
                return self._reply(200, {"ok": True}, {"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
            return super().do_POST()

        def _login(self) -> None:
            now = time.time()
            with lock:
                failures[:] = [t for t in failures if now - t < FAILED_LOGIN_WINDOW]
                if len(failures) >= MAX_FAILED_LOGINS:
                    return self._reply(429, {"error": "Too many tries. Wait a few minutes."})
            try:
                offered = str(self._body().get("passcode", ""))
            except (ValueError, json.JSONDecodeError):
                return self._reply(400, {"error": "Send JSON"})
            if not hmac.compare_digest(offered.encode(), passcode.encode()):
                with lock:
                    failures.append(now)
                return self._reply(401, {"error": "That passcode isn't right."})
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            self._reply(200, {"ok": True}, {"Set-Cookie": f"{COOKIE}={ticket}; Path=/; Max-Age=86400; HttpOnly; SameSite=Lax{secure}"})

    return DemoHandler


def main() -> None:
    passcode = os.environ.get("CONNECT_DEMO_PASSCODE", "")
    if not passcode:
        sys.exit("Set CONNECT_DEMO_PASSCODE first. The public demo won't start without one.")
    # Imported here, so importing this file for its tests doesn't load the challenge data.
    from connect import config
    from connect.engine import Engine
    from connect.service import Service
    from connect.store import Store
    from connect.yext import YextClient
    from run import start_mock

    config.VAR_DIR.mkdir(parents=True, exist_ok=True)
    service = Service(Engine(), Store(config.VAR_DIR / "connect.db"), YextClient(start_mock(), "demo"), None)
    threading.Thread(target=service.overview, daemon=True).start()
    port = int(os.environ.get("PORT", config.PORT))
    print(f"Connect Suggests demo on port {port}. Writes go to the local mock only.", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), make_demo_handler(service, passcode)).serve_forever()


if __name__ == "__main__":
    main()
