"""The web app. Owners reach /o/<token>, and everything else answers on this machine only."""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from .service import Service
from .voice import MAX_AUDIO

STATIC = Path(__file__).parent / "static"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8"}
PAGES = {"/": "console.html", "/console.css": "console.css", "/console.js": "console.js"}
MAX_BODY = 64 * 1024
LOCALHOST = {"127.0.0.1", "::1"}


def make_handler(service: Service):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ConnectSuggests/1.0"

        def log_message(self, fmt, *args):
            pass  # Request paths contain owner tokens, so they aren't logged.

        def _json(self, code: int, payload) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _file(self, name: str) -> None:
            path = STATIC / name
            raw = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPES[path.suffix])
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Robots-Tag", "noindex")
            self.end_headers()
            self.wfile.write(raw)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ValueError("Request too large")
            if length and "application/json" not in (self.headers.get("Content-Type") or ""):
                raise ValueError("Send JSON")
            return json.loads(self.rfile.read(length).decode() or "{}") if length else {}

        def _is_local(self) -> bool:
            return self.client_address[0] in LOCALHOST

        def _guard(self, fn, *args) -> None:
            try:
                fn(*args)
            except KeyError as error:
                self._json(404, {"error": str(error).strip("'\"")})
            except PermissionError:
                self._json(410, {"error": "expired"})
            except (ValueError, json.JSONDecodeError) as error:
                self._json(400, {"error": str(error)})

        def do_GET(self):
            self._guard(self._get)

        def do_POST(self):
            self._guard(self._post)

        def _get(self):
            path = urlparse(self.path).path
            # GET never changes anything, so an email link scanner can't approve a change.
            if re.fullmatch(r"/o/[\w-]+", path):
                return self._file("owner.html")
            if path in ("/owner.css", "/owner.js"):
                return self._file(path[1:])
            match = re.fullmatch(r"/api/o/([\w-]+)", path)
            if match:
                return self._json(200, service.owner_view(match.group(1)))
            if not self._is_local():
                return self._json(404, {"error": "Not found"})
            if path in PAGES:
                return self._file(PAGES[path])
            if path == "/api/businesses":
                return self._json(200, service.list_businesses())
            if path == "/api/overview":
                return self._json(200, service.overview())
            match = re.fullmatch(r"/api/business/([\w-]+)", path)
            if match:
                return self._json(200, service.business_view(match.group(1)))
            self._json(404, {"error": "Not found"})

        def _post(self):
            path = urlparse(self.path).path
            match = re.fullmatch(r"/api/o/([\w-]+)/transcribe", path)
            if match:
                content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip()
                length = int(self.headers.get("Content-Length") or 0)
                if not content_type.startswith("audio/") or not 0 < length <= MAX_AUDIO:
                    raise ValueError("Send a short audio clip")
                return self._json(200, service.transcribe_reply(match.group(1), self.rfile.read(length), content_type))
            body = self._body()
            match = re.fullmatch(r"/api/o/([\w-]+)/speak", path)
            if match:
                raw = service.speak(match.group(1), str(body.get("speech_id", "")))
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)
                return None
            match = re.fullmatch(r"/api/o/([\w-]+)/(decide|standing|undo|interpret|confirm)", path)
            if match:
                token, action = match.groups()
                if action == "interpret":
                    return self._json(200, service.interpret_reply(token, body.get("text", "")))
                if action == "confirm":
                    return self._json(200, service.confirm_plan(token, str(body.get("plan_id", ""))))
                if action == "decide":
                    return self._json(200, service.decide(token, body.get("decisions", [])))
                if action == "standing":
                    return self._json(200, service.set_standing(token, bool(body.get("enabled"))))
                return self._json(200, service.undo(token, int(body.get("item", 0))))
            if not self._is_local():
                return self._json(404, {"error": "Not found"})
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                raise ValueError("Send JSON")  # Stops other sites posting to this local console.
            if path == "/api/reset":
                service.reset()
                return self._json(200, {"reset": True})
            match = re.fullmatch(r"/api/business/([\w-]+)/detect", path)
            if match:
                return self._json(200, service.detect(match.group(1)))
            match = re.fullmatch(r"/api/case/(\d+)/(send|simulate|remind|retry)", path)
            if match:
                case_id, action = int(match.group(1)), match.group(2)
                run = {"send": service.send, "simulate": service.simulate_owner,
                       "remind": service.remind, "retry": service.retry_failed}[action]
                return self._json(200, run(case_id))
            self._json(404, {"error": "Not found"})

    return Handler
