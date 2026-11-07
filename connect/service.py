"""The whole chain: detect, suggest, contact, decide, apply and confirm, plus learning from each reply.

Guardrails, all enforced here:
- Nothing is written without the owner's approval, or standing permission the owner gave.
- No reply is never treated as approval.
- A business that looks closed for good goes to a person, and the owner gets no message.
- Opt-outs block every message.
- The owner is told "done" only after a read-back confirms the write.
"""
from __future__ import annotations

import json
import secrets
import threading
from datetime import date

from . import config, messages
from .engine import Decision, Engine
from .hours import day_to_string, edit_shift, is_valid
from .store import Store, now
from .yext import YextClient, YextError

AUTO_BASES = {"LAST_YEAR", "SHOPPING_CENTRE", "YOUR_CHOICE"}
DECLINE_REASONS = {"open_as_usual", "dont_ask", "wrong", "stop", ""}

STORYLINES = {
    "FI-D0001": "Fonecta's own example: last year's exceptions, nothing entered this year",
    "FI-D0002": "Closed on Sundays, but opens for Father's Day lunch",
    "FI-D0003": "Florist with special opening days",
    "FI-D0004": "Inside a shopping centre that has published its hours",
    "FI-D0005": "Season opening depends on snow",
    "FI-D0006": "Summer terrace that forgot its winter closure",
    "FI-D0007": "Closes between Christmas and New Year",
    "SE-D0008": "Swedish: closed on Julafton, early opening on Lucia",
    "NO-D0009": "Norwegian: no history to copy on some days",
    "FI-D0010": "Next to the arena: open later on event nights",
    "FI-D0011": "Closed for good: flag it, don't suggest",
    "FI-D0012": "Standing permission: apply, then inform",
    "FI-D0013": "Hours already right: stay quiet",
    "FI-D0014": "Opens earlier during school holidays",
    "NO-D0015": "24/7 gym: nothing to change",
    "SE-D0016": "Changed regular hours, never updated the listing",
    "FI-D0017": "New customer: no history, no earlier decisions",
}
QUIET_TEXT = {
    "ALREADY_ENTERED": "the owner has already entered these hours",
    "MATCHES_SHOWN": "the evidence matches what Google already shows",
    "NO_EVIDENCE": "no strong evidence, so Connect doesn't guess",
    "OWNER_SAID_NO": "the owner asked not to be asked about this day",
    "OWNER_DOUBTS_CLOSED": "the owner stays open on similar days",
    "NOT_CONFIDENT": "the evidence isn't strong enough to message about",
    "LISTING_CLOSED": "the listing is already published as permanently closed",
}


class Service:
    def __init__(self, engine: Engine, store: Store, mock: YextClient, sandbox: YextClient | None = None,
                 public_url: str | None = None):
        self.engine, self.store, self.mock, self.sandbox = engine, store, mock, sandbox
        self.public_url = (public_url or config.PUBLIC_URL).rstrip("/")
        self._overview = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------ small lookups

    def _contact(self, eid: str) -> dict:
        return self.engine.contacts.get(eid, {})

    def _language(self, eid: str) -> str:
        return messages.language_for(self._contact(eid).get("preferred_language")
                                     or self.engine.entities[eid]["meta"].get("language"))

    def _first_name(self, eid: str) -> str:
        return self._contact(eid).get("contact_first_name") or self.engine.entities[eid]["name"]

    def _prefs(self, eid: str) -> dict:
        contact = self._contact(eid)
        row = self.store.one("SELECT * FROM preferences WHERE entity_id = ?", (eid,)) or {}
        standing = row.get("standing_permission")
        opted = row.get("opted_out")
        return {"standing": bool(int(contact.get("standing_permission_holidays") or 0) if standing is None else standing),
                "opted_out": bool(int(contact.get("opted_out_of_suggestions") or 0) if opted is None else opted)}

    def _set_pref(self, eid: str, column: str, value: int) -> None:
        current = self._prefs(eid)
        merged = {"standing_permission": int(current["standing"]), "opted_out": int(current["opted_out"]), column: value}
        self.store.execute(
            "INSERT INTO preferences (entity_id, standing_permission, opted_out) VALUES (?,?,?) "
            "ON CONFLICT(entity_id) DO UPDATE SET standing_permission = excluded.standing_permission, opted_out = excluded.opted_out",
            (eid, merged["standing_permission"], merged["opted_out"]))

    def _has_history(self, eid: str) -> bool:
        return any(key[0] == eid for key in self.engine.history)

    def _link(self, case: dict) -> str:
        return f"{self.public_url}/o/{case['token']}"

    def _items(self, case_id: int) -> list:
        rows = self.store.all("SELECT * FROM items WHERE case_id = ? ORDER BY date", (case_id,))
        for row in rows:
            row["evidence"] = json.loads(row["evidence"] or "{}")
            row["learning_notes"] = json.loads(row["learning_notes"] or "[]")
        return rows

    def live_holidays(self, eid: str) -> dict:
        """Holiday hours as Connect's backend has them right now. An 'isRegularHours' entry shows regular hours."""
        entries = self.mock.get_entity(eid).get("hours", {}).get("holidayHours", [])
        return {h["date"]: day_to_string(h) for h in entries if not h.get("isRegularHours")}

    def _case(self, case_id: int) -> dict:
        case = self.store.one("SELECT * FROM cases WHERE id = ?", (case_id,))
        if not case:
            raise KeyError(f"No case {case_id}")
        return case

    def _case_by_token(self, token: str) -> dict | None:
        return self.store.one("SELECT * FROM cases WHERE token = ?", (token,))

    # ------------------------------------------------------------ steps 1 and 2: detect and suggest

    def detect(self, eid: str) -> dict:
        """Create the next case for a business, or explain why Connect stays quiet."""
        if eid not in self.engine.entities:
            raise KeyError(f"Unknown business {eid}")
        with self._lock:
            open_case = self.store.one("SELECT * FROM cases WHERE entity_id = ? AND status IN ('DETECTED','SENT') ORDER BY id LIMIT 1", (eid,))
            if open_case:
                return {"result": "OPEN_CASE", "case_id": open_case["id"]}
            learned = self.store.get_learned(eid)
            decisions = self.engine.decisions_for(eid, self.live_holidays(eid), learned)
            flags = [d for d in decisions if d.action == "FLAG"]
            if flags:
                return self._create_flag(eid, flags)
            handled = {r["date"] for r in self.store.all("SELECT date FROM items WHERE entity_id = ?", (eid,))}
            suggestions = sorted((d for d in decisions if d.action == "SUGGEST" and d.date not in handled),
                                 key=lambda d: d.date)
            if not suggestions:
                return self._record_quiet(eid, decisions)
            batch = self._first_batch(suggestions)
            return self._create_case(eid, batch, len(decisions), len(suggestions))

    @staticmethod
    def _first_batch(suggestions: list) -> list:
        """Dates close together go in one message, so an owner isn't messaged about each one."""
        batch = [suggestions[0]]
        for decision in suggestions[1:]:
            gap = (date.fromisoformat(decision.date) - date.fromisoformat(batch[-1].date)).days
            if gap > config.BATCH_GAP_DAYS or len(batch) >= config.MAX_DATES_PER_MESSAGE:
                break
            batch.append(decision)
        return batch

    def _record_quiet(self, eid: str, decisions: list) -> dict:
        reasons = {}
        for decision in decisions:
            key = decision.quiet_reason or ("HANDLED" if decision.action == "SUGGEST" else "NO_EVIDENCE")
            reasons[key] = reasons.get(key, 0) + 1
        readable = {QUIET_TEXT.get(k, "already handled in an earlier message"): v for k, v in reasons.items()}
        summary = "No message: " + "; ".join(f"{v} {'day' if v == 1 else 'days'}, {k}" for k, v in readable.items())
        self.store.log("DETECT", "connect", summary, eid, data={"days_checked": len(decisions)})
        return {"result": "QUIET", "days_checked": len(decisions), "reasons": readable, "summary": summary}

    def _create_flag(self, eid: str, flags: list) -> dict:
        existing = self.store.one("SELECT id FROM cases WHERE entity_id = ? AND kind = 'FLAG'", (eid,))
        if existing:
            return {"result": "FLAG", "case_id": existing["id"]}
        now_text = now()
        case_id = self.store.execute(
            "INSERT INTO cases (entity_id, kind, status, created_at) VALUES (?, 'FLAG', 'NEEDS_HUMAN', ?)", (eid, now_text)).lastrowid
        first = flags[0]
        self.store.execute(
            "INSERT INTO items (case_id, entity_id, date, day_key, day_name_local, shown, proposed, basis, mode, confidence, evidence, learning_notes, expected_views, views_from_last_year, decision) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'HUMAN')",
            (case_id, eid, first.date, first.day_key, first.day_name_local, first.shown, "", first.basis, "FLAG", 1.0,
             json.dumps(first.evidence, ensure_ascii=False), "[]", 0, 0))
        self.store.log("DETECT", "connect", f"Looks closed for good. {len(flags)} upcoming days affected, sent to a person. No message to the owner.",
                       eid, case_id, first.evidence)
        return {"result": "FLAG", "case_id": case_id}

    def _create_case(self, eid: str, batch: list, days_checked: int, remaining: int) -> dict:
        contact = self._contact(eid)
        channel = contact.get("preferred_channel") or "EMAIL"
        case_id = self.store.execute(
            "INSERT INTO cases (entity_id, kind, status, token, channel, language, expires_on, created_at) VALUES (?, 'SUGGESTION', 'DETECTED', ?, ?, ?, ?, ?)",
            (eid, secrets.token_urlsafe(24), channel, self._language(eid), batch[-1].date, now())).lastrowid
        for d in batch:
            self.store.execute(
                "INSERT INTO items (case_id, entity_id, date, day_key, day_name_local, shown, proposed, basis, mode, confidence, evidence, learning_notes, expected_views, views_from_last_year) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (case_id, eid, d.date, d.day_key, d.day_name_local, d.shown, d.hours, d.basis, d.mode, d.confidence,
                 json.dumps(d.evidence, ensure_ascii=False), json.dumps(d.learning_notes, ensure_ascii=False),
                 d.expected_views, int(d.views_from_last_year)))
            self.store.log("DETECT", "connect", f"{d.date}: Google shows {d.shown}, evidence points to {d.hours}.", eid, case_id,
                           {"basis": d.basis, "evidence": d.evidence})
            self.store.log("SUGGEST", "connect",
                           f"{d.date}: {d.mode.lower()} {d.hours}, from {d.basis}, confidence {d.confidence:.2f}.", eid, case_id,
                           {"expected_views": d.expected_views, "learning_notes": d.learning_notes})
            for note in d.learning_notes:
                self.store.log("LEARN", "connect", note, eid, case_id)
        return {"result": "CASE", "case_id": case_id, "days_checked": days_checked, "remaining_after": remaining - len(batch)}

    # ------------------------------------------------------------ step 3: contact

    def _save_message(self, case: dict, kind: str, body: str, body_en: str, channel: str | None = None) -> None:
        self.store.execute("INSERT INTO messages (case_id, kind, channel, language, body, body_en, sent_at) VALUES (?,?,?,?,?,?,?)",
                           (case["id"], kind, channel or case["channel"], case["language"], body, body_en, now()))

    def send(self, case_id: int) -> dict:
        with self._lock:
            case = self._case(case_id)
            eid = case["entity_id"]
            if case["status"] != "DETECTED":
                return self.case_view(case_id)
            prefs = self._prefs(eid)
            if prefs["opted_out"]:
                self.store.execute("UPDATE cases SET status = 'BLOCKED_OPT_OUT' WHERE id = ?", (case_id,))
                self.store.log("CONTACT", "connect", "Owner has opted out. No message sent, nothing written.", eid, case_id)
                return self.case_view(case_id)
            items = self._items(case_id)
            auto = [i for i in items if prefs["standing"] and i["basis"] in AUTO_BASES
                    and i["confidence"] >= config.AUTO_APPLY_THRESHOLD and i["mode"] == "SUGGEST"]
            auto_ids = {i["id"] for i in auto}
            ask = [i for i in items if i["id"] not in auto_ids]
            window = self._contact(eid).get("best_contact_window")
            if auto:
                self._apply_with_standing(case, auto)
            if ask:
                first, business, link = self._first_name(eid), self.engine.entities[eid]["name"], self._link(case)
                no_history = not self._has_history(eid)
                body = messages.offer(first, business, ask, link, case["language"], case["channel"], no_history)
                body_en = messages.offer(first, business, ask, link, "en", case["channel"], no_history)
                self._save_message(case, "OFFER", body, body_en)
                self.store.log("CONTACT", "connect",
                               f"Offer sent by {case['channel']} in {case['language']} (simulated delivery). "
                               f"In production it would go in the owner's window, {window}.", eid, case_id)
            self.store.execute("UPDATE cases SET status = ? WHERE id = ?", ("SENT" if ask else "DONE", case_id))
            return self.case_view(case_id)

    def _apply_with_standing(self, case: dict, items: list) -> None:
        eid = case["entity_id"]
        for item in items:
            self.store.execute("UPDATE items SET decision = 'AUTO', final_hours = ?, decided_by = 'standing_permission', decided_at = ? WHERE id = ?",
                               (item["proposed"], now(), item["id"]))
        self.store.log("DECIDE", "standing_permission", f"{len(items)} dates applied under the owner's standing permission.", eid, case["id"])
        written = self._write_items(case, [i["id"] for i in items])
        if written:
            first, business, link = self._first_name(eid), self.engine.entities[eid]["name"], self._link(case)
            listings = self.where_it_shows(eid)
            self._save_message(case, "AUTO_APPLIED", messages.auto_applied(first, business, written, listings, link, case["language"]),
                               messages.auto_applied(first, business, written, listings, link, "en"))
            self.store.log("CONTACT", "connect", "Owner informed of the change, with a one-tap undo link.", eid, case["id"])

    def remind(self, case_id: int) -> dict:
        """One reminder at most, then Connect stays quiet. Silence never becomes a yes."""
        with self._lock:
            case = self._case(case_id)
            eid = case["entity_id"]
            if self.store.one("SELECT id FROM messages WHERE case_id = ? AND kind = 'REMINDER'", (case_id,)) or case["status"] != "SENT":
                return self.case_view(case_id)
            if self._prefs(eid)["opted_out"]:
                return self.case_view(case_id)
            pending = [i for i in self._items(case_id) if i["decision"] in ("PENDING", "NO_REPLY")]
            first, business, link = self._first_name(eid), self.engine.entities[eid]["name"], self._link(case)
            self._save_message(case, "REMINDER", messages.reminder(first, business, pending, link, case["language"]),
                               messages.reminder(first, business, pending, link, "en"))
            self.store.log("CONTACT", "connect", "One reminder sent. No more after this.", eid, case_id)
            return self.case_view(case_id)

    # ------------------------------------------------------------ step 4: decide

    def decide(self, token: str, decisions: list, actor: str = "owner") -> dict:
        with self._lock:
            case = self._case_by_token(token)
            if not case:
                raise KeyError("Unknown link")
            if self._expired(case):
                raise PermissionError("expired")
            items = {i["id"]: i for i in self._items(case["id"])}
            to_write, declined = [], []
            for decision in decisions:
                item = items.get(decision.get("item"))
                if not item:
                    raise ValueError("That date isn't part of this message")
                if item["decision"] not in ("PENDING", "NO_REPLY"):
                    continue  # A repeated tap changes nothing.
                action = decision.get("action")
                if action == "approve":
                    self._record(item, "APPROVED", item["proposed"], actor)
                    to_write.append(item["id"])
                elif action == "edit":
                    hours = str(decision.get("hours", "")).strip().lower()
                    if not is_valid(hours):
                        raise ValueError(f"Invalid hours: {hours!r}")
                    final = "APPROVED" if hours == item["proposed"] else "EDITED"
                    self._record(item, final, hours, actor)
                    to_write.append(item["id"])
                elif action == "decline":
                    why = decision.get("reason", "")
                    if why not in DECLINE_REASONS:
                        raise ValueError("Unknown reason")
                    self._record(item, "DECLINED", None, actor, why)
                    declined.append(item["id"])
                else:
                    raise ValueError(f"Unknown action: {action!r}")
            self._learn(case, [items[i] for i in to_write + declined], decisions)
            written = self._write_items(case, to_write) if to_write else []
            self._send_followups(case, written, to_write, declined)
            self._finish_if_complete(case["id"])
            return self.owner_view(token)

    def _record(self, item: dict, decision: str, final: str | None, actor: str, why: str = "") -> None:
        self.store.execute("UPDATE items SET decision = ?, final_hours = ?, decline_reason = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                           (decision, final, why, actor, now(), item["id"]))
        item.update(decision=decision, final_hours=final, decline_reason=why)
        text = {"APPROVED": f"approved {final}", "EDITED": f"changed {item['proposed']} to {final}",
                "DECLINED": f"declined{' (' + why + ')' if why else ''}. Nothing written."}[decision]
        self.store.log("DECIDE", actor, f"{item['date']}: {text}", item["entity_id"], item["case_id"])

    def _send_followups(self, case: dict, written: list, to_write: list, declined: list) -> None:
        eid = case["entity_id"]
        first, business = self._first_name(eid), self.engine.entities[eid]["name"]
        if written:
            listings = self.where_it_shows(eid)
            prefs = self._prefs(eid)
            offered = self.store.one("SELECT id FROM messages WHERE case_id = ? AND kind = 'CONFIRMATION'", (case["id"],))
            offer_link = None if prefs["standing"] or prefs["opted_out"] or offered else self._link(case)
            self._save_message(case, "CONFIRMATION",
                               messages.confirmation(first, business, written, listings, case["language"], offer_link),
                               messages.confirmation(first, business, written, listings, "en", offer_link))
            self.store.log("APPLY", "connect", "Owner told the change is saved, and where it will show.", eid, case["id"])
        if len(written) < len(to_write):
            self._save_message(case, "WRITE_FAILED", messages.write_failed(case["language"]), messages.write_failed("en"))
        if declined and not to_write:
            self._save_message(case, "DECLINED", messages.declined(first, case["language"]), messages.declined(first, "en"))

    def _finish_if_complete(self, case_id: int) -> None:
        items = self._items(case_id)
        waiting = [i for i in items if i["decision"] in ("PENDING", "NO_REPLY") or i["write_status"] == "FAILED"]
        if not waiting:
            self.store.execute("UPDATE cases SET status = 'DONE' WHERE id = ?", (case_id,))

    def _expired(self, case: dict) -> bool:
        return bool(case["expires_on"]) and self.engine.today.isoformat() > case["expires_on"]

    # ------------------------------------------------------------ learning

    def _learn(self, case: dict, items: list, raw_decisions: list) -> None:
        eid = case["entity_id"]
        learned = self.store.get_learned(eid)
        for item in items:
            key, proposed, final = item["day_key"], item["proposed"], item.get("final_hours")
            if item["decision"] in ("APPROVED", "EDITED"):
                learned.setdefault("day_hours", {})[key] = final
            if item["decision"] == "EDITED":
                open_by, close_by = edit_shift(proposed, final)
                if open_by or close_by:
                    learned["open_shift"], learned["close_shift"] = open_by, close_by
                    self.store.log("LEARN", "connect",
                                   f"Owner moved the opening by {open_by:+d} min and the closing by {close_by:+d} min. "
                                   "Later suggestions for this owner move the same way.", eid, case["id"])
                if proposed == "closed" and final != "closed":
                    learned["closed_doubts"] = learned.get("closed_doubts", 0) + 1
                    self.store.log("LEARN", "connect", "Owner opens on a day Connect thought was closed. Later 'closed' guesses need more proof.", eid, case["id"])
            if item["decision"] == "DECLINED":
                why = item.get("decline_reason")
                if why in ("open_as_usual", "dont_ask"):
                    learned.setdefault("skip_days", [])
                    if key not in learned["skip_days"]:
                        learned["skip_days"].append(key)
                    self.store.log("LEARN", "connect", f"Connect won't ask about {key} again.", eid, case["id"])
                if why == "open_as_usual" and proposed == "closed":
                    learned["closed_doubts"] = learned.get("closed_doubts", 0) + 1
                    self.store.log("LEARN", "connect", "Owner stays open on a day Connect thought was closed. Later 'closed' guesses need more proof.", eid, case["id"])
                if why == "stop":
                    self._set_pref(eid, "opted_out", 1)
                    self.store.log("LEARN", "connect", "Owner opted out. No more suggestions will be sent.", eid, case["id"])
        self.store.set_learned(eid, learned)

    def set_standing(self, token: str, enabled: bool) -> dict:
        case = self._case_by_token(token)
        if not case:
            raise KeyError("Unknown link")
        self._set_pref(case["entity_id"], "standing_permission", int(enabled))
        self.store.log("LEARN", "owner", "Owner gave standing permission for public holidays." if enabled
                       else "Owner turned off standing permission.", case["entity_id"], case["id"])
        return self.owner_view(token)

    # ------------------------------------------------------------ step 5: apply and confirm

    def _sandbox_id(self, eid: str) -> str:
        """The test business in the Yext sandbox that stands in for this synthetic one."""
        row = self.store.one("SELECT sandbox_id FROM sandbox_entities WHERE entity_id = ?", (eid,))
        if row:
            return row["sandbox_id"]
        sandbox_id = f"connect-demo-{eid.lower()}"
        try:
            self.sandbox.get_entity(sandbox_id)
        except YextError as error:
            if error.status != 404:
                raise
            source = self.engine.entities[eid]
            entity = {
                "meta": {"id": sandbox_id, "countryCode": source["meta"]["countryCode"], "language": source["meta"]["language"]},
                "name": f"TEST {source['name']} (Since AI sandbox)",
                "address": source["address"],
                "description": "Test entity for the Since AI hackathon, based on synthetic data. Not a real business.",
                "hours": self.engine.regular_week(eid),
            }
            note = ""
            try:
                self.sandbox.create_entity(entity)
            except YextError as create_error:
                # The sandbox account doesn't allow every language (Norwegian is refused). Hours don't depend on it.
                if "PROFILE_LANGUAGE_INELIGIBLE" not in str(create_error):
                    raise
                refused = entity["meta"]["language"]
                entity["meta"]["language"] = "en"
                self.sandbox.create_entity(entity)
                note = f" The account refused language '{refused}', so this test record uses 'en'."
            self.store.log("APPLY", "connect", f"Created test business {sandbox_id} in the Yext sandbox.{note}", eid)
        self.store.execute("INSERT OR REPLACE INTO sandbox_entities (entity_id, sandbox_id) VALUES (?, ?)", (eid, sandbox_id))
        return sandbox_id

    def _write_items(self, case: dict, item_ids: list) -> list:
        """Write a message's dates in one call: sandbox first, then Connect's own record.

        An item counts as written only if every read-back matches. If not, the owner is told nothing changed.
        """
        eid = case["entity_id"]
        items = [self.store.one("SELECT * FROM items WHERE id = ?", (i,)) for i in item_ids]
        changes = {i["date"]: i["final_hours"] for i in items}
        sandbox_id, restore = None, None
        try:
            entries = self.mock.get_entity(eid).get("hours", {}).get("holidayHours", [])
            before = {h["date"]: day_to_string(h) for h in entries if not h.get("isRegularHours")}
            sandbox_after = {}
            if self.sandbox:
                sandbox_id = self._sandbox_id(eid)
                current = self.sandbox.get_entity(sandbox_id).get("hours", {}).get("holidayHours", [])
                current = {h["date"]: day_to_string(h) for h in current if not h.get("isRegularHours")}
                restore = {day: current.get(day) for day in changes}
                sandbox_after = self.sandbox.write_holidays(sandbox_id, changes)
                self._check_readback(sandbox_after, changes, "sandbox ")
            self._check_readback(self.mock.write_holidays(eid, changes), changes, "")
        except YextError as error:
            self._put_back(restore, sandbox_id, eid, case["id"])
            for item in items:
                self.store.execute("UPDATE items SET write_status = 'FAILED', write_error = ? WHERE id = ?", (str(error)[:300], item["id"]))
            self.store.log("APPLY", "connect", f"Write failed for {', '.join(changes)}, so the owner is told nothing changed. {error}", eid, case["id"])
            return []
        target = "the Yext sandbox and Connect's record" if self.sandbox else "the local Yext mock (no sandbox key set)"
        for item in items:
            readback = json.dumps(sandbox_after[item["date"]]) if self.sandbox else None
            self.store.execute("UPDATE items SET write_status = 'WRITTEN', write_error = NULL, previous_hours = ?, sandbox_readback = ? WHERE id = ?",
                               (before.get(item["date"]), readback, item["id"]))
            self.store.log("APPLY", "connect", f"{item['date']}: wrote {item['final_hours']} to {target}. Read-back matches.", eid, case["id"],
                           {"sandbox_readback": readback})
        return items

    def _put_back(self, restore: dict | None, sandbox_id: str | None, eid: str, case_id: int) -> None:
        """A failed write must leave nothing behind, because the owner is told nothing changed."""
        if not restore:
            return
        try:
            self.sandbox.write_holidays(sandbox_id, restore)
        except YextError as error:
            self.store.log("APPLY", "connect", f"Could not put the sandbox back, so a person must check {sandbox_id}. {error}", eid, case_id)

    @staticmethod
    def _check_readback(after: dict, changes: dict, label: str) -> None:
        for day, hours in changes.items():
            if after.get(day) is None or day_to_string(after[day]) != hours:
                raise YextError(0, f"{label}read-back for {day} showed {after.get(day)}")

    def retry_failed(self, case_id: int) -> dict:
        with self._lock:
            case = self._case(case_id)
            failed = [i["id"] for i in self._items(case_id) if i["write_status"] == "FAILED"]
            written = self._write_items(case, failed)
            if written:
                self._send_followups(case, written, [i["id"] for i in written], [])
            self._finish_if_complete(case_id)
            return self.case_view(case_id)

    def undo(self, token: str, item_id: int) -> dict:
        """The owner always has the last word, even after a change is live."""
        with self._lock:
            case = self._case_by_token(token)
            if not case:
                raise KeyError("Unknown link")
            item = next((i for i in self._items(case["id"]) if i["id"] == item_id), None)
            if not item or item["write_status"] != "WRITTEN":
                raise ValueError("That change can't be undone")
            eid = case["entity_id"]
            sandbox_id, restore = None, None
            try:
                change = {item["date"]: item["previous_hours"]}
                if self.sandbox:
                    sandbox_id = self._sandbox_id(eid)
                    restore = {item["date"]: item["final_hours"]}
                    self.sandbox.write_holidays(sandbox_id, change)
                self.mock.write_holidays(eid, change)
            except YextError as error:
                self._put_back(restore, sandbox_id, eid, case["id"])
                self.store.log("APPLY", "connect", f"{item['date']}: undo failed. {error}", eid, case["id"])
                raise ValueError("The undo didn't go through. Nothing else changed.") from None
            self.store.execute("UPDATE items SET decision = 'UNDONE', write_status = 'UNDONE' WHERE id = ?", (item_id,))
            learned = self.store.get_learned(eid)
            learned.get("day_hours", {}).pop(item["day_key"], None)
            learned.setdefault("skip_days", [])
            if item["day_key"] not in learned["skip_days"]:
                learned["skip_days"].append(item["day_key"])
            self.store.set_learned(eid, learned)
            first = self._first_name(eid)
            self._save_message(case, "UNDONE", messages.undone(first, item, case["language"]), messages.undone(first, item, "en"))
            self.store.log("DECIDE", "owner", f"{item['date']}: undid the change. Connect won't ask about {item['day_key']} again.", eid, case["id"])
            return self.owner_view(token)

    def where_it_shows(self, eid: str) -> list:
        """Publishers where the change is being sent, fastest first. Timing comes from the simulator's listing data."""
        live = [x for x in self.mock.listings(eid) if x.get("status") == "LIVE"]
        live.sort(key=lambda x: x["typicalUpdateSpeedSeconds"])
        return [{"name": x["publisherName"], "seconds": x["typicalUpdateSpeedSeconds"], "url": x.get("listingUrl"),
                 "expected_live_by": x.get("expectedLiveBy")} for x in live]

    # ------------------------------------------------------------ the mock's owner simulator

    def simulate_owner(self, case_id: int) -> dict:
        """Let the challenge's statistical owner reply, instead of tapping by hand. It may not reply at all."""
        with self._lock:
            case = self._case(case_id)
            if case["status"] != "SENT":
                return self.case_view(case_id)
            decisions = []
            for item in self._items(case_id):
                if item["decision"] != "PENDING":
                    continue
                reply = self.mock.owner_response(case["entity_id"], item["date"], item["proposed"], case["channel"])
                if reply["decision"] == "ACCEPTED":
                    decisions.append({"item": item["id"], "action": "approve"})
                elif reply["decision"] == "EDITED":
                    decisions.append({"item": item["id"], "action": "edit", "hours": reply["final_hours"]})
                elif reply["decision"] == "REJECTED":
                    decisions.append({"item": item["id"], "action": "decline", "reason": "wrong"})
                else:
                    self.store.execute("UPDATE items SET decision = 'NO_REPLY' WHERE id = ?", (item["id"],))
                    self.store.log("DECIDE", "owner_simulator", f"{item['date']}: no reply. Nothing written.", case["entity_id"], case_id)
            if decisions:
                self.decide(case["token"], decisions, actor="owner_simulator")
            return self.case_view(case_id)

    # ------------------------------------------------------------ views for the two web pages

    def owner_view(self, token: str) -> dict:
        case = self._case_by_token(token)
        if not case:
            raise KeyError("Unknown link")
        lang = case["language"]
        eid = case["entity_id"]
        items = []
        for item in self._items(case["id"]):
            items.append({
                "id": item["id"], "day": messages.day_name(item["day_key"], lang, item["day_name_local"]),
                "date": messages.date_label(item["date"], lang), "shown": messages.hours_label(item["shown"], lang),
                "proposed": item["proposed"], "proposed_label": messages.hours_label(item["proposed"], lang),
                "reason": messages.reason(item, lang), "mode": item["mode"], "decision": item["decision"],
                "final_label": messages.hours_label(item["final_hours"], lang) if item["final_hours"] else None,
                "write_status": item["write_status"], "views": item["expected_views"] if item["views_from_last_year"] else None,
            })
        prefs = self._prefs(eid)
        written = any(i["write_status"] == "WRITTEN" for i in items)
        listings = [{"name": x["name"], "eta": messages.eta_label(x["seconds"], lang)} for x in self.where_it_shows(eid)] if written else []
        return {"business": self.engine.entities[eid]["name"], "first_name": self._first_name(eid), "language": lang,
                "ui": messages.UI[lang], "status": case["status"], "expired": self._expired(case), "items": items,
                "listings": listings, "standing": prefs["standing"], "opted_out": prefs["opted_out"]}

    def case_view(self, case_id: int) -> dict:
        case = self._case(case_id)
        items = self._items(case_id)
        for item in items:
            item["reason_en"] = messages.reason(item, "en")
        return {**case, "link": self._link(case) if case["token"] else None, "items": items,
                "messages": self.store.all("SELECT * FROM messages WHERE case_id = ? ORDER BY id", (case_id,)),
                "sandbox_active": bool(self.sandbox)}

    def business_view(self, eid: str) -> dict:
        ent = self.engine.entities.get(eid)
        if not ent:
            raise KeyError(f"Unknown business {eid}")
        cases = self.store.all("SELECT id FROM cases WHERE entity_id = ? ORDER BY id", (eid,))
        sandbox = self.store.one("SELECT sandbox_id FROM sandbox_entities WHERE entity_id = ?", (eid,))
        contact = self._contact(eid)
        return {
            "id": eid, "name": ent["name"], "city": ent["address"]["city"], "segment": ent.get("c_segment"),
            "customer_since": ent.get("c_connectCustomerSince"), "storyline": STORYLINES.get(eid, ""),
            "channel": contact.get("preferred_channel"), "language": self._language(eid),
            "window": contact.get("best_contact_window"), "preferences": self._prefs(eid),
            "learned": self.store.get_learned(eid), "has_history": self._has_history(eid),
            "cases": [self.case_view(c["id"]) for c in cases],
            "events": self.store.all("SELECT * FROM events WHERE entity_id = ? ORDER BY id", (eid,)),
            "sandbox_id": sandbox["sandbox_id"] if sandbox else None,
            "listings": self.where_it_shows(eid),
        }

    def list_businesses(self) -> list:
        out = []
        for eid in sorted(STORYLINES, key=lambda x: x.split("-")[1]):
            ent = self.engine.entities.get(eid)
            if not ent:
                continue
            case = self.store.one("SELECT id, status FROM cases WHERE entity_id = ? ORDER BY id DESC LIMIT 1", (eid,))
            out.append({"id": eid, "name": ent["name"], "city": ent["address"]["city"], "storyline": STORYLINES[eid],
                        "status": case["status"] if case else None})
        return out

    def overview(self) -> dict:
        """What the same rules decide across all 3,000 customers, ranked by search views at stake."""
        if self._overview is None:
            suggest, flag, quiet, views = 0, 0, 0, 0
            contacted, flagged, ranking = set(), set(), {}
            customers = [e for e in self.engine.targets if e in self.engine.entities and "-D0" not in e]
            for eid in customers:
                opted_out = bool(int(self._contact(eid).get("opted_out_of_suggestions") or 0))
                for decision in self.engine.decisions_for(eid):
                    if decision.action == "SUGGEST" and opted_out:
                        quiet += 1
                    elif decision.action == "SUGGEST":
                        suggest += 1
                        views += decision.expected_views
                        contacted.add(eid)
                        ranking[eid] = ranking.get(eid, 0) + decision.expected_views
                    elif decision.action == "FLAG":
                        flag += 1
                        flagged.add(eid)
                    else:
                        quiet += 1
            top = sorted(ranking.items(), key=lambda kv: -kv[1])[:5]
            contacts = self.engine.contacts.values()
            self._overview = {
                "sandbox_active": bool(self.sandbox),
                "businesses": len(customers), "suggestions": suggest, "quiet_days": quiet,
                "owners_to_contact": len(contacted), "flagged_businesses": len(flagged), "views_at_stake": views,
                "opted_out": sum(int(c.get("opted_out_of_suggestions") or 0) for c in contacts),
                "standing_permission": sum(int(c.get("standing_permission_holidays") or 0) for c in contacts),
                "pilot_confidence": {k: round(v, 3) for k, v in self.engine.confidence_by_basis.items()},
                "top": [{"id": e, "name": self.engine.entities[e]["name"], "city": self.engine.entities[e]["address"]["city"],
                         "views": v} for e, v in top],
            }
        return self._overview

    def reset(self) -> None:
        """Clear the demo: local state, the mock's writes, and holiday hours on our own sandbox test businesses."""
        with self._lock:
            if self.sandbox:
                for row in self.store.all("SELECT sandbox_id FROM sandbox_entities"):
                    try:
                        self.sandbox.clear_holidays(row["sandbox_id"])
                    except YextError:
                        pass  # A failed clean-up of a test business shouldn't block the demo.
            self.mock.reset()
            self.store.reset()


__all__ = ["Service", "Decision"]
