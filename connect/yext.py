"""Yext Management API client. The same code talks to the local mock and the real sandbox.

Adapted from the challenge package's examples/yext_client.py (MIT, Since AI ry). The key travels in a header,
so it never appears in a URL, a log line or an error message.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .hours import string_to_day


class YextError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"Yext returned {status}: {message}")
        self.status = status


class YextClient:
    def __init__(self, base_url: str, api_key: str, version: str = "20261101"):
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.version = version

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        query = urllib.parse.urlencode({"v": self.version, **(params or {})})
        request = urllib.request.Request(
            f"{self.base}/v2/accounts/me/{path}?{query}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"api-key": self.key, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            raise YextError(error.code, error.read().decode(errors="replace")[:300]) from None
        except urllib.error.URLError as error:
            raise YextError(0, f"could not connect: {error.reason}") from None

    def get_entity(self, entity_id: str) -> dict:
        return self._request("GET", f"entities/{urllib.parse.quote(entity_id)}")["response"]

    def create_entity(self, entity: dict) -> dict:
        return self._request("POST", "entities", {"entityType": "location"}, entity)["response"]

    def listings(self, entity_id: str) -> list:
        return self._request("GET", "listings/listings", {"locationIds": entity_id})["response"].get("listings", [])

    def write_holidays(self, entity_id: str, changes: dict) -> dict:
        """Read, merge, write the full hours object in one call, then read back.

        `changes` maps a date to hours, or to None to remove that date. Yext replaces the holiday list as a whole,
        so a blind write would erase every other date. Returns {date: entry as read back, or None if absent}.
        """
        full_hours = self.get_entity(entity_id).get("hours", {})
        merged = [h for h in full_hours.get("holidayHours", []) if h.get("date") not in changes]
        merged += [{"date": day, **string_to_day(hours)} for day, hours in changes.items() if hours is not None]
        full_hours["holidayHours"] = sorted(merged, key=lambda h: h["date"])
        self._request("PUT", f"entities/{urllib.parse.quote(entity_id)}", body={"hours": full_hours})
        after = {h.get("date"): h for h in self.get_entity(entity_id).get("hours", {}).get("holidayHours", [])}
        return {day: after.get(day) for day in changes}

    def clear_holidays(self, entity_id: str) -> None:
        full_hours = self.get_entity(entity_id).get("hours", {})
        full_hours["holidayHours"] = []
        self._request("PUT", f"entities/{urllib.parse.quote(entity_id)}", body={"hours": full_hours})

    # -- Only on the challenge's local mock

    def _mock_post(self, path: str, body: dict) -> dict:
        request = urllib.request.Request(f"{self.base}{path}", method="POST", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode())["response"]
        except urllib.error.HTTPError as error:
            raise YextError(error.code, error.read().decode(errors="replace")[:300]) from None

    def owner_response(self, entity_id: str, day: str, proposed: str, channel: str | None = None) -> dict:
        body = {"entityId": entity_id, "date": day, "proposedHours": proposed}
        if channel:
            body["channel"] = channel
        return self._mock_post("/sim/v1/owner-response", body)

    def reset(self) -> None:
        self._mock_post("/mock/reset", {})
