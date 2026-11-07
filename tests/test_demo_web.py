"""The public demo's passcode gate. Run with: python3 -m unittest discover tests"""
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo_web.server import MAX_FAILED_LOGINS, make_demo_handler  # noqa: E402


class FakeService:
    resets = 0

    def overview(self):
        return {"secret_console_data": True}

    def owner_view(self, token):
        return {"business": "Kahvila Aurora", "token": token}

    def reset(self):
        FakeService.resets += 1

    def transcribe_reply(self, token, audio, content_type):
        return {"status": "heard", "text": f"{len(audio)} bytes of {content_type}"}


class PasscodeGateTest(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_demo_handler(FakeService(), "open-sesame"))
        self.httpd.RequestHandlerClass.log_message = lambda *args: None
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        FakeService.resets = 0

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def call(self, path, body=None, cookie=None):
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode(), error.headers

    def login(self):
        status, _, headers = self.call("/login", {"passcode": "open-sesame"})
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";")[0]

    def test_console_and_changes_are_closed_without_the_passcode(self):
        status, body, _ = self.call("/api/overview")
        self.assertEqual(status, 404)
        self.assertNotIn("secret_console_data", body)
        self.assertEqual(self.call("/api/reset", {})[0], 404)
        self.assertEqual(FakeService.resets, 0)
        self.assertIn("Demo passcode", self.call("/")[1])

    def test_connecting_from_this_machine_is_not_enough(self):
        # A tunnel or proxy makes every visitor look local, so the console's usual rule must not apply here.
        self.assertEqual(self.call("/console.js")[0], 404)

    def test_wrong_passcode_and_forged_cookie_are_refused(self):
        self.assertEqual(self.call("/login", {"passcode": "wrong"})[0], 401)
        self.assertEqual(self.call("/api/overview", cookie="connect_demo=forged")[0], 404)

    def test_passcode_opens_the_console(self):
        cookie = self.login()
        self.assertEqual(self.call("/api/overview", cookie=cookie)[0], 200)
        self.assertEqual(self.call("/api/reset", {}, cookie=cookie)[0], 200)
        self.assertEqual(FakeService.resets, 1)
        self.assertNotIn("open-sesame", cookie)

    def test_mobile_needs_the_passcode(self):
        self.assertIn("Demo passcode", self.call("/mobile")[1])
        self.assertEqual(self.call("/mobile.js")[0], 404)
        cookie = self.login()
        self.assertIn("Connect for owners", self.call("/mobile", cookie=cookie)[1])
        self.assertEqual(self.call("/mobile.js", cookie=cookie)[0], 200)

    def test_owner_links_stay_open_without_the_passcode(self):
        self.assertEqual(self.call("/api/o/abc")[0], 200)
        self.assertEqual(self.call("/o/abc")[0], 200)

    def test_voice_upload_takes_audio_only(self):
        request = urllib.request.Request(self.base + "/api/o/abc/transcribe", data=b"12345", headers={"Content-Type": "audio/webm;codecs=opus"})
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(json.loads(response.read())["text"], "5 bytes of audio/webm")
        self.assertEqual(self.call("/api/o/abc/transcribe", {"a": 1})[0], 400)

    def test_repeated_wrong_passcodes_are_slowed_down(self):
        for _ in range(MAX_FAILED_LOGINS):
            self.call("/login", {"passcode": "wrong"})
        self.assertEqual(self.call("/login", {"passcode": "open-sesame"})[0], 429)


if __name__ == "__main__":
    unittest.main()
