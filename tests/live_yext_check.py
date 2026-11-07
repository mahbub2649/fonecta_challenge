#!/usr/bin/env python3
"""Live checks against a real Yext sandbox, using the key in .env or ../.env. It never prints the key.

    python3 tests/live_yext_check.py

It isn't part of `unittest discover`, so the normal tests never touch the sandbox. It only changes records whose ID
starts with "connect-". It removes the records it creates and puts back the holiday hours it finds.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["MOCK_QUIET"] = "1"
if "CONNECT_ENV_FILE" not in os.environ and not (ROOT / ".env").exists() and (ROOT.parent / ".env").exists():
    os.environ["CONNECT_ENV_FILE"] = str(ROOT.parent / ".env")

from connect import config  # noqa: E402
from connect.engine import Engine  # noqa: E402
from connect.hours import day_to_string, is_valid, string_to_day  # noqa: E402
from connect.service import STORYLINES, Service  # noqa: E402
from connect.store import Store  # noqa: E402
from connect.yext import YextClient, YextError  # noqa: E402

sys.path.insert(0, str(config.DATA_DIR / "mock_api"))
import server as mock_server  # noqa: E402

if not config.SANDBOX_KEY:
    sys.exit("No sandbox key found. Set YEXT_API_KEY in .env first.")

_temp = tempfile.mkdtemp()
mock_server.STATE_FILE = os.path.join(_temp, "state.json")
mock_server.STORE = mock_server.Store()
_httpd = ThreadingHTTPServer(("127.0.0.1", 0), mock_server.Handler)
threading.Thread(target=_httpd.serve_forever, daemon=True).start()
MOCK_URL = f"http://127.0.0.1:{_httpd.server_address[1]}"
ENGINE = Engine()
FINDINGS = []
OURS = ("connect-apitest-", "connect-demo-")


def note(text: str) -> None:
    FINDINGS.append(text)


class OurRecordsOnly(YextClient):
    """Refuses to change anything but our own test records, before any request is sent."""

    def __init__(self, base_url=None, api_key=None):
        super().__init__(base_url or config.SANDBOX_URL, api_key if api_key is not None else config.SANDBOX_KEY)
        self.puts = 0

    def _request(self, method, path, params=None, body=None):
        if method != "GET":
            target = (body or {}).get("meta", {}).get("id", "") if path == "entities" else path.split("/", 1)[-1]
            if not target.startswith(OURS):
                raise AssertionError(f"Refused to change {target}: not one of our test records")
        if method == "PUT":
            self.puts += 1
        return super()._request(method, path, params, body)

    def delete_entity(self, entity_id):
        try:
            self._request("DELETE", f"entities/{entity_id}")
        except json.JSONDecodeError:
            pass  # A successful delete can have an empty body.


LIVE = OurRecordsOnly()
READER = YextClient(config.SANDBOX_URL, config.SANDBOX_KEY)  # A separate client, so checks don't rely on the write path.
BEFORE = {}


def holidays(entity_id) -> dict:
    entries = READER.get_entity(entity_id).get("hours", {}).get("holidayHours", [])
    return {h["date"]: day_to_string(h) for h in entries}


def setUpModule():
    for eid in STORYLINES:
        sandbox_id = f"connect-demo-{eid.lower()}"
        try:
            BEFORE[sandbox_id] = READER.get_entity(sandbox_id).get("hours", {})
        except YextError as error:
            if error.status != 404:
                raise
            BEFORE[sandbox_id] = None


def tearDownModule():
    created = restored = 0
    for sandbox_id, hours in BEFORE.items():
        try:
            if hours is None:
                READER.get_entity(sandbox_id)  # It raises if the run never created this one.
                LIVE.delete_entity(sandbox_id)
                created += 1
            else:
                LIVE._request("PUT", f"entities/{sandbox_id}", body={"hours": {**hours, "holidayHours": hours.get("holidayHours", [])}})
                restored += 1
        except YextError as error:
            if error.status != 404:
                note(f"CLEAN-UP PROBLEM on {sandbox_id}: {error}")
    note(f"Clean-up: restored holiday hours on {restored} existing test records, removed {created} created in this run")


class ApiContract(unittest.TestCase):
    """What the sandbox itself does with the requests our client sends."""

    @classmethod
    def setUpClass(cls):
        cls.id_ = f"connect-apitest-{uuid.uuid4().hex[:10]}"
        source = ENGINE.entities["FI-D0017"]
        cls.name = f"TEST {source['name']} (Since AI sandbox)"
        cls.week = ENGINE.regular_week("FI-D0017")
        LIVE.create_entity({"meta": {"id": cls.id_, "countryCode": source["meta"]["countryCode"], "language": source["meta"]["language"]},
                            "name": cls.name, "address": source["address"], "description": "Test entity for the Since AI hackathon. Not a real business.",
                            "hours": cls.week})
        cls.addClassCleanup(LIVE.delete_entity, cls.id_)

    def setUp(self):
        LIVE.clear_holidays(self.id_)

    def test_a_wrong_key_is_refused_and_not_echoed(self):
        secret = "definitely-not-a-real-key-123"
        with self.assertRaises(YextError) as caught:
            YextClient(config.SANDBOX_URL, secret).get_entity(self.id_)
        self.assertIn(caught.exception.status, (401, 403))
        self.assertNotIn(secret, str(caught.exception))
        note(f"Wrong key: refused with HTTP {caught.exception.status}")

    def test_b_missing_record_is_a_404_without_the_key(self):
        with self.assertRaises(YextError) as caught:
            READER.get_entity(f"connect-apitest-missing-{uuid.uuid4().hex[:6]}")
        self.assertEqual(caught.exception.status, 404)
        self.assertNotIn(config.SANDBOX_KEY, str(caught.exception))

    def test_c_created_record_reads_back(self):
        entity = READER.get_entity(self.id_)
        self.assertEqual(entity["meta"]["id"], self.id_)
        self.assertEqual(entity["name"], self.name)
        self.assertEqual(entity["address"]["city"], ENGINE.entities["FI-D0017"]["address"]["city"])
        for day, value in self.week.items():
            self.assertEqual(day_to_string(entity["hours"].get(day)), day_to_string(value), day)

    def test_d_each_kind_of_hours_reads_back_exactly(self):
        cases = {"2026-12-24": "07:30-13:00", "2026-12-25": "closed", "2026-12-26": "10:00-14:00,17:00-22:00", "2026-12-31": "18:00-02:00", "2027-01-01": "16:00-00:00"}
        after = LIVE.write_holidays(self.id_, cases)
        for day, hours in cases.items():
            self.assertEqual(day_to_string(after[day]), hours, day)
        self.assertEqual(holidays(self.id_), cases)

    def test_e_a_second_write_keeps_other_dates_regular_hours_and_details(self):
        before = READER.get_entity(self.id_)
        LIVE.write_holidays(self.id_, {"2026-12-24": "07:30-13:00"})
        LIVE.write_holidays(self.id_, {"2026-12-25": "closed"})
        after = READER.get_entity(self.id_)
        self.assertEqual(holidays(self.id_), {"2026-12-24": "07:30-13:00", "2026-12-25": "closed"})
        self.assertEqual(after["name"], before["name"])
        self.assertEqual(after["address"], before["address"])
        for day in self.week:
            self.assertEqual(after["hours"].get(day), before["hours"].get(day), day)

    def test_f_many_dates_in_one_call(self):
        changes = {f"2026-12-{d:02d}": "09:00-15:00" for d in range(1, 16)}
        LIVE.puts = 0
        LIVE.write_holidays(self.id_, changes)
        self.assertEqual(LIVE.puts, 1)
        self.assertEqual(holidays(self.id_), changes)

    def test_g_overwriting_a_date_and_repeating_a_write(self):
        LIVE.write_holidays(self.id_, {"2026-12-24": "07:30-13:00"})
        LIVE.write_holidays(self.id_, {"2026-12-24": "09:00-12:00"})
        self.assertEqual(holidays(self.id_), {"2026-12-24": "09:00-12:00"})
        LIVE.write_holidays(self.id_, {"2026-12-24": "09:00-12:00"})
        self.assertEqual(holidays(self.id_), {"2026-12-24": "09:00-12:00"})

    def test_h_removing_one_date_keeps_the_rest(self):
        LIVE.write_holidays(self.id_, {"2026-12-24": "07:30-13:00", "2026-12-25": "closed"})
        LIVE.write_holidays(self.id_, {"2026-12-24": None})
        self.assertEqual(holidays(self.id_), {"2026-12-25": "closed"})
        LIVE.clear_holidays(self.id_)
        self.assertEqual(holidays(self.id_), {})
        self.assertEqual(day_to_string(READER.get_entity(self.id_)["hours"].get("monday")), day_to_string(self.week.get("monday")))

    def test_i_a_write_can_be_read_straight_away(self):
        for minute in range(10):
            hours = f"09:{minute:02d}-15:00"
            LIVE.write_holidays(self.id_, {"2026-12-24": hours})
            self.assertEqual(holidays(self.id_)["2026-12-24"], hours, "the read after the write was stale")

    def test_j_every_hours_string_the_model_can_suggest(self):
        decisions = json.loads((ROOT / "connect" / "model_decisions.json").read_text(encoding="utf-8"))
        strings = sorted({r["hours"] for days in decisions.values() for r in days.values() if r["action"] == "SUGGEST"})
        dates = [f"2027-{m:02d}-{d:02d}" for m in range(2, 10) for d in range(1, 29)]
        refused = []
        for start in range(0, len(strings), 25):
            batch = strings[start:start + 25]
            changes = dict(zip(dates[start:start + 25], batch))
            try:
                after = LIVE.write_holidays(self.id_, changes)
            except YextError:
                after = {}
                for day, hours in changes.items():
                    try:
                        after.update(LIVE.write_holidays(self.id_, {day: hours}))
                    except YextError as error:
                        refused.append((hours, str(error)[:160]))
            for day, hours in changes.items():
                if after.get(day) is not None:
                    self.assertEqual(day_to_string(after[day]), hours)
            LIVE.clear_holidays(self.id_)
        note(f"Hours strings the model can suggest: {len(strings)} tried, {len(refused)} refused {refused[:6] if refused else ''}")
        self.assertEqual(refused, [])

    def test_k_owner_edits_our_validator_accepts_also_work_on_yext(self):
        edits = ["closed", "07:30-14:00", "09:00-12:00,13:00-17:00", "08:00-10:00,11:00-13:00,14:00-16:00", "23:00-01:00", "00:00-23:59", "00:30-06:00",
                 "10:00-24:00", "24:00-10:00", "00:00-24:00", "10:05-14:55", "9:00-17:00", "22:00-02:00,03:00-04:00", "10:00-12:00,12:00-14:00", "10:00-12:00,12:01-14:00", "10:00-20:00,21:00-02:00"]
        problems = []
        for hours in edits:
            if not is_valid(hours):
                continue
            try:
                after = LIVE.write_holidays(self.id_, {"2027-03-01": hours})
                if day_to_string(after["2027-03-01"]) != hours:
                    problems.append(f"{hours} read back as {day_to_string(after['2027-03-01'])}")
            except YextError as error:
                problems.append(f"{hours} refused: {str(error)[:150]}")
        note(f"Owner edits: {len([e for e in edits if is_valid(e)])} pass our validator, {len(problems)} fail on Yext {problems}")
        self.assertEqual(problems, [])

    def test_l_refused_writes_change_nothing(self):
        LIVE.write_holidays(self.id_, {"2026-12-24": "07:30-13:00"})
        before = holidays(self.id_)
        hours = READER.get_entity(self.id_)["hours"]
        outcomes = {}
        for label, entry in {"hour 25": {"date": "2026-12-25", **string_to_day("25:00-26:00")}, "bad date": {"date": "2026-13-45", "isClosed": True},
                             "no hours": {"date": "2026-12-25"}}.items():
            body = {"hours": {**hours, "holidayHours": hours["holidayHours"] + [entry]}}
            try:
                LIVE._request("PUT", f"entities/{self.id_}", body=body)
                outcomes[label] = "accepted"
                LIVE._request("PUT", f"entities/{self.id_}", body={"hours": hours})
            except YextError as error:
                outcomes[label] = f"refused {error.status}"
                self.assertEqual(holidays(self.id_), before, label)
        note(f"Bad writes: {outcomes}")
        self.assertEqual(outcomes["hour 25"].split()[0], "refused")
        self.assertEqual(outcomes["bad date"].split()[0], "refused")

    def test_m_the_season_boundaries_are_accepted(self):
        changes = {"2026-11-07": "closed", "2027-01-06": "10:00-14:00"}
        LIVE.write_holidays(self.id_, changes)
        self.assertEqual(holidays(self.id_), changes)

    def test_n_our_guard_blocks_records_that_are_not_ours(self):
        with self.assertRaises(AssertionError):
            LIVE._request("PUT", "entities/bench-01", body={"hours": {}})
        with self.assertRaises(AssertionError):
            LIVE._request("DELETE", "entities/SinceAI09")

    def test_o_read_only_endpoints(self):
        results = {}
        for label, path, params in (("listings", "listings/listings", {"locationIds": self.id_}), ("publisher suggestions", "listings/publishersuggestions", {"locationIds": self.id_}),
                                    ("reviews", "reviews", {"locationIds": self.id_, "limit": 5})):
            try:
                response = READER._request("GET", path, params)["response"]
                results[label] = {k: (len(v) if isinstance(v, list) else v) for k, v in response.items() if k != "pageToken"}
            except YextError as error:
                results[label] = f"HTTP {error.status}"
        note(f"Other sandbox endpoints for a new test record: {results}")


class ChainOnSandbox(unittest.TestCase):
    """The whole product against the real sandbox, checked with a separate client."""

    def setUp(self):
        self.mock = YextClient(MOCK_URL, "demo")
        self.mock.reset()
        self.service = Service(ENGINE, Store(":memory:"), self.mock, LIVE, public_url="http://test")

    def fresh(self, eid):
        sandbox_id = f"connect-demo-{eid.lower()}"
        try:
            LIVE.clear_holidays(sandbox_id)
        except YextError as error:
            if error.status != 404:
                raise
        return sandbox_id

    def open_case(self, eid):
        result = self.service.detect(eid)
        self.assertEqual(result["result"], "CASE", eid)
        return self.service.send(result["case_id"])

    def approve_all(self, case):
        return self.service.decide(case["token"], [{"item": i["id"], "action": "approve"} for i in case["items"] if i["decision"] == "PENDING"])

    def test_a_all_five_steps_for_every_demo_business(self):
        lines = []
        for eid in STORYLINES:
            sandbox_id = self.fresh(eid)
            expected, messages_sent, kinds = {}, 0, set()
            for _ in range(4):  # Keeps going as the "Detect the next dates" button does.
                result = self.service.detect(eid)
                if result["result"] != "CASE":
                    kinds.add(result["result"])
                    break
                case = self.service.send(result["case_id"])
                messages_sent += 1
                if case["status"] != "DONE":
                    self.assertTrue(any(c in case["messages"][0]["body"] for c in (case["link"],)), eid)
                    self.approve_all(case)
                case = self.service.case_view(case["id"])
                for item in case["items"]:
                    self.assertEqual(item["write_status"], "WRITTEN", f"{eid} {item['date']}: {item.get('write_error')}")
                    expected[item["date"]] = item["final_hours"]
                confirmation = case["messages"][-1]
                self.assertIn(confirmation["kind"], ("CONFIRMATION", "AUTO_APPLIED"), eid)
                publishers = [x["name"] for x in self.service.where_it_shows(eid)]
                self.assertTrue(publishers, f"{eid} has nowhere to show")
                self.assertIn(publishers[0], confirmation["body"], eid)
            if expected:
                self.assertEqual(holidays(sandbox_id), expected, f"{eid}: the sandbox doesn't match what the owner approved")
            lines.append(f"{eid}: {messages_sent} messages, {len(expected)} dates on the sandbox, then {sorted(kinds) or 'stopped at 4'}")
        note("Every demo business:\n    " + "\n    ".join(lines))

    def test_b_sending_and_opening_the_link_write_nothing(self):
        sandbox_id = self.fresh("FI-D0001")
        case = self.open_case("FI-D0001")
        self.service.owner_view(case["token"])
        self.service.owner_view(case["token"])
        try:
            self.assertEqual(holidays(sandbox_id), {})
        except YextError as error:
            self.assertEqual(error.status, 404)

    def test_c_an_edit_writes_the_owner_hours(self):
        sandbox_id = self.fresh("FI-D0001")
        case = self.open_case("FI-D0001")
        first = case["items"][0]
        self.service.decide(case["token"], [{"item": first["id"], "action": "edit", "hours": "07:30-14:00"}])
        self.assertEqual(holidays(sandbox_id), {first["date"]: "07:30-14:00"})
        self.assertNotEqual(first["proposed"], "07:30-14:00")

    def test_d_a_decline_writes_nothing(self):
        sandbox_id = self.fresh("FI-D0001")
        case = self.open_case("FI-D0001")
        self.service.decide(case["token"], [{"item": i["id"], "action": "decline", "reason": "wrong"} for i in case["items"]])
        try:
            self.assertEqual(holidays(sandbox_id), {})
        except YextError as error:
            self.assertEqual(error.status, 404)
        self.assertEqual(self.service.case_view(case["id"])["messages"][-1]["kind"], "DECLINED")

    def test_e_approve_edit_and_decline_in_one_reply_is_one_write(self):
        for eid in STORYLINES:
            sandbox_id = self.fresh(eid)
            result = self.service.detect(eid)
            if result["result"] == "CASE":
                case = self.service.send(result["case_id"])
                if case["status"] != "DONE" and len(case["items"]) >= 3:
                    break
        else:
            self.fail("No demo business has a first message with three dates")
        items = case["items"]
        replies = [{"item": items[0]["id"], "action": "approve"}, {"item": items[1]["id"], "action": "edit", "hours": "11:11-12:12"}]
        replies += [{"item": i["id"], "action": "decline", "reason": "wrong"} for i in items[2:]]
        LIVE.puts = 0
        self.service.decide(case["token"], replies)
        self.assertLessEqual(LIVE.puts, 1)
        self.assertEqual(holidays(sandbox_id), {items[0]["date"]: items[0]["proposed"], items[1]["date"]: "11:11-12:12"})

    def test_f_undo_takes_the_date_off_the_sandbox(self):
        sandbox_id = self.fresh("FI-D0001")
        case = self.open_case("FI-D0001")
        self.approve_all(case)
        first, second = case["items"][:2]
        self.service.undo(case["token"], first["id"])
        self.assertEqual(holidays(sandbox_id), {second["date"]: second["proposed"]})

    def test_g_standing_permission_writes_then_can_be_undone(self):
        sandbox_id = self.fresh("FI-D0012")
        case = self.open_case("FI-D0012")
        self.assertEqual(case["messages"][-1]["kind"], "AUTO_APPLIED")
        written = {i["date"]: i["final_hours"] for i in case["items"]}
        self.assertEqual(holidays(sandbox_id), written)
        item = case["items"][0]
        self.service.undo(case["token"], item["id"])
        self.assertNotIn(item["date"], holidays(sandbox_id))

    def test_h_opt_out_blocks_any_write(self):
        sandbox_id = self.fresh("FI-D0001")
        self.service._set_pref("FI-D0001", "opted_out", 1)
        case = self.open_case("FI-D0001")
        self.assertEqual(case["status"], "BLOCKED_OPT_OUT")
        self.assertEqual(case["messages"], [])
        try:
            self.assertEqual(holidays(sandbox_id), {})
        except YextError as error:
            self.assertEqual(error.status, 404)

    def test_i_a_flag_and_a_quiet_business_never_write(self):
        for eid in ("FI-D0011", "NO-D0015"):
            sandbox_id = self.fresh(eid)
            result = self.service.detect(eid)
            if result["result"] == "CASE":
                self.assertEqual(self.service.case_view(result["case_id"])["kind"], "FLAG", eid)
            try:
                self.assertEqual(holidays(sandbox_id), {}, eid)
            except YextError as error:
                self.assertEqual(error.status, 404)

    def test_j_languages_keep_the_owner_message_when_the_record_falls_back(self):
        for eid, word in (("SE-D0008", "Google"), ("NO-D0009", "Google")):
            sandbox_id = self.fresh(eid)
            case = self.open_case(eid)
            self.assertIn(case["language"], ("sv", "nb"), eid)
            self.assertIn(word, case["messages"][0]["body"])
            self.approve_all(case)
            self.assertEqual(holidays(sandbox_id), {i["date"]: i["proposed"] for i in case["items"]}, eid)
        note(f"Sandbox record language for NO-D0009: {READER.get_entity('connect-demo-no-d0009')['meta']['language']}, owner message language: nb")

    def test_k_a_bad_key_means_the_owner_is_told_nothing_changed_and_retry_works(self):
        sandbox_id = self.fresh("FI-D0001")
        LIVE.get_entity(self.service._sandbox_id("FI-D0001"))
        case = self.open_case("FI-D0001")
        self.service.sandbox = OurRecordsOnly(api_key="definitely-not-a-real-key-123")
        view = self.service.decide(case["token"], [{"item": i["id"], "action": "approve"} for i in case["items"]])
        self.assertTrue(all(i["write_status"] == "FAILED" for i in view["items"]))
        self.assertEqual(holidays(sandbox_id), {})
        self.assertEqual(self.mock.get_entity("FI-D0001")["hours"].get("holidayHours", []), [])
        latest = self.service.case_view(case["id"])["messages"][-1]
        self.assertNotEqual(latest["kind"], "CONFIRMATION")
        self.assertNotIn("definitely-not-a-real-key-123", json.dumps(self.service.case_view(case["id"]), default=str))
        self.service.sandbox = LIVE
        self.service.retry_failed(case["id"])
        self.assertEqual(holidays(sandbox_id), {i["date"]: i["proposed"] for i in case["items"]})
        self.assertEqual(self.service.case_view(case["id"])["messages"][-1]["kind"], "CONFIRMATION")

    def test_l_an_unreachable_sandbox_is_also_reported_as_nothing_changed(self):
        self.fresh("FI-D0001")
        case = self.open_case("FI-D0001")
        self.service.sandbox = OurRecordsOnly(base_url="http://127.0.0.1:9", api_key="x")
        view = self.service.decide(case["token"], [{"item": i["id"], "action": "approve"} for i in case["items"]])
        self.assertTrue(all(i["write_status"] == "FAILED" for i in view["items"]))
        self.assertNotEqual(self.service.case_view(case["id"])["messages"][-1]["kind"], "CONFIRMATION")

    def test_m_a_read_back_that_does_not_match_is_not_confirmed(self):
        self.fresh("FI-D0001")
        case = self.open_case("FI-D0001")

        class WrongReadBack(OurRecordsOnly):
            def write_holidays(self, entity_id, changes):
                return {day: {"isClosed": True} if hours != "closed" else {"openIntervals": [{"start": "01:00", "end": "02:00"}]} for day, hours in changes.items()}

        self.service.sandbox = WrongReadBack()
        view = self.service.decide(case["token"], [{"item": i["id"], "action": "approve"} for i in case["items"]])
        self.assertTrue(all(i["write_status"] == "FAILED" for i in view["items"]))
        self.assertNotEqual(self.service.case_view(case["id"])["messages"][-1]["kind"], "CONFIRMATION")

    def test_n_if_our_own_record_fails_the_owner_is_not_misled(self):
        sandbox_id = self.fresh("FI-D0001")
        case = self.open_case("FI-D0001")
        good = self.service.mock.write_holidays

        def down(*_):
            raise YextError(503, "record store down")

        self.service.mock.write_holidays = down
        view = self.service.decide(case["token"], [{"item": i["id"], "action": "approve"} for i in case["items"]])
        self.service.mock.write_holidays = good
        status = {i["write_status"] for i in view["items"]}
        left = holidays(sandbox_id)
        note(f"Connect's record fails after the sandbox write: status {status}, dates left on the sandbox: {sorted(left)}")
        self.assertEqual(left, {}, "the owner was told nothing changed, but the sandbox holds the change")

    def test_n2_a_failed_undo_keeps_the_change_on_the_sandbox(self):
        sandbox_id = self.fresh("FI-D0001")
        case = self.open_case("FI-D0001")
        self.approve_all(case)
        before = holidays(sandbox_id)
        good = self.service.mock.write_holidays

        def down(*_):
            raise YextError(503, "record store down")

        self.service.mock.write_holidays = down
        try:
            with self.assertRaises(ValueError):
                self.service.undo(case["token"], case["items"][0]["id"])
        finally:
            self.service.mock.write_holidays = good
        self.assertEqual(holidays(sandbox_id), before)

    def test_o_confirmation_uses_the_businesss_live_listings(self):
        self.fresh("FI-D0001")
        case = self.open_case("FI-D0001")
        self.approve_all(case)
        data = json.loads((config.DATA_DIR / "data" / "listings.json").read_text(encoding="utf-8"))["listings"]
        rows = [x for x in data if x.get("entityId") == "FI-D0001" or x.get("locationId") == "FI-D0001"]
        expected = {x["publisherName"] for x in rows if x.get("status") == "LIVE"}
        shown = {x["name"] for x in self.service.where_it_shows("FI-D0001")}
        self.assertTrue(expected)
        self.assertEqual(shown, expected)
        self.assertNotIn("Facebook", shown)  # Opted out in listings.json, so it must not be claimed.
        body = self.service.case_view(case["id"])["messages"][-1]["body"]
        fastest = [x["name"] for x in self.service.where_it_shows("FI-D0001")][:4]
        self.assertTrue(all(name in body for name in fastest), body)
        self.assertIn(f"{len(expected) - 4} muuta", body)
        note(f"FI-D0001 confirmation: names {fastest}, plus {len(expected) - 4} more, out of {sorted(expected)}")

    def test_p_reset_clears_the_sandbox_holidays(self):
        sandbox_id = self.fresh("FI-D0001")
        self.approve_all(self.open_case("FI-D0001"))
        self.assertTrue(holidays(sandbox_id))
        self.service.reset()
        self.assertEqual(holidays(sandbox_id), {})

    def test_q_the_key_is_never_stored_or_shown(self):
        self.fresh("FI-D0001")
        case = self.open_case("FI-D0001")
        self.approve_all(case)
        for table in ("cases", "items", "messages", "preferences", "learned", "events", "sandbox_entities"):
            self.assertNotIn(config.SANDBOX_KEY, json.dumps([dict(r) for r in self.service.store.all(f"SELECT * FROM {table}")], default=str), table)
        self.assertNotIn(config.SANDBOX_KEY, json.dumps(self.service.business_view("FI-D0001"), default=str))
        self.assertNotIn(config.SANDBOX_KEY, json.dumps(self.service.owner_view(case["token"]), default=str))


if __name__ == "__main__":
    outcome = unittest.main(exit=False, verbosity=2).result
    print("\nFindings:")
    for line in FINDINGS:
        print(" -", line)
    sys.exit(0 if outcome.wasSuccessful() else 1)
