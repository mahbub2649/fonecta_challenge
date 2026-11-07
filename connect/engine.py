"""Steps 1 and 2: decide what each business needs for each special day, and why.

The decision comes from the trained model's saved output (connect/model_decisions.json, built by model/train.py),
so the web app needs no machine-learning libraries. The rule ladder (last year, shopping centre, peers), adapted from
the challenge package's examples/baseline.py (MIT, Since AI ry), explains each decision and is the fallback if the
file is missing. The owner's own past decisions then adjust the result in `apply_learning`.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import config
from .hours import day_to_string, shift

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
CLOSED_FOR_GOOD_WORDS = ("lopettanut", "pysyvästi", "stängt för gott", "permanent", "lagt ned", "stengt for godt",
                         "closed down", "lokalen är tom", "tilat tyhjinä")
WRONG_HOURS_WORDS = ("kiinni", "suljettu", "stängt", "stängd", "stengt", "closed")
PILOT_BASIS = {"LAST_YEAR_EXCEPTION": "LAST_YEAR", "SHOPPING_CENTRE_HOURS": "SHOPPING_CENTRE", "PEER_MAJORITY": "PEERS"}
YOUR_CHOICE_CONFIDENCE = 0.98


def _cycle(d: date) -> int:
    return d.year if d.month >= 2 else d.year - 1


@dataclass
class Decision:
    entity_id: str
    date: str
    day_key: str
    action: str  # SUGGEST | NO_ACTION | FLAG
    shown: str
    hours: str = ""
    basis: str | None = None  # LAST_YEAR | SHOPPING_CENTRE | PEERS | YOUR_CHOICE | CLOSED_SIGNALS
    mode: str = "SUGGEST"  # SUGGEST states it, ASK words it as a question
    confidence: float = 0.0
    quiet_reason: str = ""  # ALREADY_ENTERED | MATCHES_SHOWN | NO_EVIDENCE | OWNER_SAID_NO | OWNER_DOUBTS_CLOSED
    evidence: dict = field(default_factory=dict)
    expected_views: int = 0
    views_from_last_year: bool = False
    day_name_local: str = ""
    learning_notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class Engine:
    def __init__(self, data_dir: Path | None = None, today: date | None = None, views_path: Path | None = None, use_model: bool = True):
        self.root = Path(data_dir or config.DATA_DIR)
        model_path = config.ROOT / "connect" / "model_decisions.json"
        self.model = json.loads(model_path.read_text(encoding="utf-8")) if use_model and model_path.exists() else None
        self.today = today or config.TODAY
        data = self.root / "data"
        entities = json.loads((data / "entities.json").read_text(encoding="utf-8"))["response"]["entities"]
        self.entities = {e["meta"]["id"]: e for e in entities}
        self.history = defaultdict(list)
        with (data / "holiday_hours_history.jsonl").open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                self.history[(row["entity_id"], row["date"])].append(row)
        self.regular_history = defaultdict(list)
        with (data / "regular_hours_history.jsonl").open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                self.regular_history[row["entity_id"]].append(row)
        self.calendar = self._csv(data / "calendar_special_days.csv")
        self.dates_by_key = defaultdict(list)
        self.calendar_names = {}
        for row in self.calendar:
            self.dates_by_key[(row["country"], row["day_key"])].append(date.fromisoformat(row["date"]))
            self.calendar_names[(row["country"], row["date"])] = row["name_local"]
        self.peers = {(r["country"], r["city_tier"], r["segment"], r["day_key"]): r
                      for r in self._csv(data / "peer_benchmarks.csv")}
        self.city_tiers = {r["city"]: r["city_tier"] for r in self._csv(data / "cities.csv")}
        self.contacts = {r["entity_id"]: r for r in self._csv(data / "customer_contacts.csv")}
        self.targets = defaultdict(list)
        for row in self._csv(self.root / "evaluation" / "targets_2026.csv"):
            self.targets[row["entity_id"]].append(row)
        self.confidence_by_basis = self._pilot_confidence(data / "pilot_decision_log_2025.csv")
        self._load_signals(data)
        self.views = self._load_views(views_path)

    @staticmethod
    def _csv(path: Path) -> list:
        with path.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _pilot_confidence(self, path: Path) -> dict:
        """Share of owners who replied in the 2025 pilot and accepted, for each kind of evidence."""
        counts = defaultdict(lambda: {"ACCEPTED": 0, "EDITED": 0, "REJECTED": 0})
        for row in self._csv(path):
            basis = PILOT_BASIS.get(row["basis"])
            if basis and row["decision"] in counts[basis]:
                counts[basis][row["decision"]] += 1
        return {basis: c["ACCEPTED"] / max(1, sum(c.values())) for basis, c in counts.items()}

    def _load_signals(self, data: Path) -> None:
        cutoff_ms = datetime(self.today.year, self.today.month, self.today.day).timestamp() * 1000
        reviews = json.loads((data / "reviews.json").read_text(encoding="utf-8"))["response"]["reviews"]
        suggestions = json.loads((data / "publisher_suggestions.json").read_text(encoding="utf-8"))["response"]["suggestions"]
        self.closed_signal = set()
        self.closure_evidence = defaultdict(list)
        self.complaints = defaultdict(list)
        for review in reviews:
            if review["publisherDate"] >= cutoff_ms:
                continue
            text = (review.get("content") or "").lower()
            when = datetime.fromtimestamp(review["publisherDate"] / 1000).date().isoformat()
            if review["publisherDate"] > cutoff_ms - 150 * 86400000 and any(w in text for w in CLOSED_FOR_GOOD_WORDS):
                self.closed_signal.add(review["locationId"])
                self.closure_evidence[review["locationId"]].append(
                    {"source": "Review", "date": when, "text": review["content"][:160]})
            if any(w in text for w in WRONG_HOURS_WORDS):
                self.complaints[review["locationId"]].append(
                    {"source": "Review", "date": when, "text": review["content"][:160]})
        self.hour_edits = defaultdict(list)
        for item in suggestions:
            created = item["dateCreated"][:10]
            if created >= self.today.isoformat():
                continue
            if item["fieldName"] == "closed":
                self.closed_signal.add(item["locationId"])
                self.closure_evidence[item["locationId"]].append(
                    {"source": "Google user edit", "date": created, "text": f"Marked as closed ({item['status']})"})
            elif item["fieldName"] == "hours":
                self.hour_edits[item["locationId"]].append(
                    {"source": "Google user edit", "date": created, "text": f"Proposed new hours ({item['status']})"})

    @staticmethod
    def _load_views(path: Path | None) -> dict:
        path = Path(path or config.ROOT / "connect" / "views.json")
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"average": {}, "by_date": {}}

    # ------------------------------------------------------------ what is shown today

    def regular_hours(self, eid: str, d: date) -> str:
        if self.today == config.TODAY:  # entities.json is the live listing at this snapshot.
            return day_to_string(self.entities[eid]["hours"].get(DAYS[d.weekday()]))
        candidates = [r for r in self.regular_history[eid]
                      if r["effective_from"] == "before-2024" or r["effective_from"] < self.today.isoformat()]
        best = max(candidates, key=lambda r: "0000" if r["effective_from"] == "before-2024" else r["effective_from"])
        return day_to_string(best["hours"][DAYS[d.weekday()]])

    def entry(self, eid: str, d: date) -> str | None:
        rows = [r for r in self.history.get((eid, d.isoformat()), []) if r["entered_at"] < self.today.isoformat()]
        if not rows:
            return None
        hours = max(rows, key=lambda r: r["entered_at"])["holidayHours"]
        return "REGULAR" if hours.get("isRegularHours") else day_to_string(hours)

    def shown(self, eid: str, d: date, live_holidays: dict | None = None) -> str:
        """What publishers show: live writes first, then the audit log, then regular hours."""
        if live_holidays and d.isoformat() in live_holidays:
            return live_holidays[d.isoformat()]
        if self.entities[eid].get("closed"):
            return "closed"
        entered = self.entry(eid, d)
        return self.regular_hours(eid, d) if entered in (None, "REGULAR") else entered

    # ------------------------------------------------------------ the rule ladder

    def base_decision(self, eid: str, d: date, key: str, live_holidays: dict | None = None) -> Decision:
        ent = self.entities[eid]
        shown = self.shown(eid, d, live_holidays)
        decision = Decision(eid, d.isoformat(), key, "NO_ACTION", shown)
        if eid in self.closed_signal and not ent.get("closed"):
            decision.action, decision.basis = "FLAG", "CLOSED_SIGNALS"
            decision.confidence = 1.0
            decision.evidence = {"signals": self.closure_evidence[eid][:4]}
            return decision

        candidate, basis, evidence = None, None, {}
        mall = ent.get("c_shoppingCenterEntityId")
        if mall:
            mall_hours = self.entry(mall, d)
            if mall_hours and mall_hours != "REGULAR":
                candidate, basis = mall_hours, "SHOPPING_CENTRE"
                evidence = {"mall": self.entities[mall]["name"], "mall_hours": mall_hours}
        if candidate is None:
            previous = [x for x in self.dates_by_key[(ent["meta"]["countryCode"], key)] if _cycle(x) == _cycle(d) - 1]
            for p in previous:
                last = self.entry(eid, p)
                if last is not None:
                    candidate = self.regular_hours(eid, d) if last == "REGULAR" else last
                    basis = "LAST_YEAR"
                    evidence = {"last_date": p.isoformat(), "last_hours": last}
        if candidate is None:
            cell = self.peers.get((ent["meta"]["countryCode"], self.city_tiers[ent["address"]["city"]],
                                   ent["c_segment"], key))
            if cell and cell["closed_share_among_entered"] and float(cell["closed_share_among_entered"]) >= 0.7 \
                    and float(cell["share_entered_closed"]) >= 0.15 and shown != "closed":
                candidate, basis = "closed", "PEERS"
                evidence = {"peer_share": float(cell["closed_share_among_entered"]),
                            "peer_count": int(cell["n_entity_days"]), "segment": ent["c_segment"]}
        decision.basis, decision.evidence = basis, evidence
        if candidate and candidate != shown:
            decision.action, decision.hours = "SUGGEST", candidate
            decision.confidence = self.confidence_by_basis.get(basis, 0.5)
        elif self.entry(eid, d) is not None or (live_holidays and d.isoformat() in live_holidays):
            decision.quiet_reason = "ALREADY_ENTERED"
        elif candidate:
            decision.quiet_reason = "MATCHES_SHOWN"
        else:
            decision.quiet_reason = "NO_EVIDENCE"
        return decision

    # ------------------------------------------------------------ the model's decision, with its reason

    def model_decision(self, eid: str, d: date, key: str, live_holidays: dict | None = None) -> Decision:
        ladder = self.base_decision(eid, d, key, live_holidays)
        if self.model is None:
            return ladder
        saved = self.model.get(eid, {}).get(d.isoformat())
        decision = Decision(eid, d.isoformat(), key, "NO_ACTION", ladder.shown, basis=ladder.basis, evidence=ladder.evidence)
        if self.entities[eid].get("closed"):
            decision.basis, decision.evidence, decision.quiet_reason = None, {}, "LISTING_CLOSED"
            return decision
        if saved and saved["action"] == "FLAG":
            decision.action, decision.basis, decision.confidence = "FLAG", "CLOSED_SIGNALS", 1.0
            decision.evidence = {"signals": self.closure_evidence[eid][:4]}
            return decision
        if not saved or saved["hours"] == ladder.shown:
            already = self.entry(eid, d) is not None or (live_holidays and d.isoformat() in live_holidays)
            decision.quiet_reason = "ALREADY_ENTERED" if already else (ladder.quiet_reason if ladder.action == "NO_ACTION" else "NOT_CONFIDENT")
            return decision
        decision.action, decision.hours, decision.confidence = "SUGGEST", saved["hours"], saved["confidence"]
        decision.basis, decision.evidence = self._explain(eid, d, key, saved, ladder)
        return decision

    def _explain(self, eid: str, d: date, key: str, saved: dict, ladder: Decision) -> tuple:
        """The clearest true reason for the model's choice, in plain evidence the owner can check."""
        hours, sources = saved["hours"], set(saved.get("sources") or [])
        if ladder.action == "SUGGEST" and ladder.hours == hours:
            return ladder.basis, ladder.evidence
        ent = self.entities[eid]
        country = ent["meta"]["countryCode"]
        cycle_now = _cycle(d)
        last_dates = [x for x in self.dates_by_key[(country, key)] if _cycle(x) == cycle_now - 1]
        older_dates = [x for x in self.dates_by_key[(country, key)] if _cycle(x) == cycle_now - 2]
        for p in last_dates:
            for item in self.complaints.get(eid, []):
                gap = (date.fromisoformat(item["date"]) - p).days
                if hours == "closed" and 0 <= gap <= 21:
                    return "REVIEW_CLOSED", {"last_date": p.isoformat(), "signals": [item]}
        if hours == "closed":
            cell = self.peers.get((country, self.city_tiers[ent["address"]["city"]], ent["c_segment"], key))
            if cell and cell["closed_share_among_entered"] and float(cell["closed_share_among_entered"]) >= 0.5:
                return "PEERS", {"peer_share": float(cell["closed_share_among_entered"]), "peer_count": int(cell["n_entity_days"]), "segment": ent["c_segment"]}
            return "PATTERN", {}
        if "mall" in sources and ent.get("c_shoppingCenterEntityId"):
            return "SHOPPING_CENTRE", {"mall": self.entities[ent["c_shoppingCenterEntityId"]]["name"], "mall_hours": hours}
        if "pilot_edit" in sources:
            return "YOUR_CHOICE", {"your_hours": hours}
        if sources & {"y1_entry", "y1_delta"}:
            for p in last_dates:
                last = self.entry(eid, p)
                if last and last not in ("closed", "REGULAR"):
                    return "LAST_YEAR", {"last_date": p.isoformat(), "last_hours": last}
        if sources & {"y1_rev_close", "y1_rev_arrived", "y2_rev_close", "y2_rev_arrived"}:
            return "REVIEW_TIME", {"close_time": hours.split(",")[-1].split("-")[1]}
        if "rev_week" in sources:
            return "REVIEW_WEEK", {"week_hours": hours}
        if sources & {"y2_entry", "y2_delta"}:
            for p in older_dates:
                older = self.entry(eid, p)
                if older and older not in ("closed", "REGULAR"):
                    return "OLDER_YEAR", {"older_date": p.isoformat(), "older_hours": older}
        return "PATTERN", {}

    # ------------------------------------------------------------ what the owner has taught us

    def apply_learning(self, decision: Decision, learned: dict) -> Decision:
        """Learning: earlier edits and declines change the next suggestion for this owner."""
        if decision.action == "FLAG":
            return decision
        key = decision.day_key
        if key in learned.get("skip_days", []):
            decision.action, decision.hours, decision.quiet_reason = "NO_ACTION", "", "OWNER_SAID_NO"
            decision.learning_notes.append(f"Owner declined {key} earlier, so Connect stays quiet.")
            return decision
        chosen = learned.get("day_hours", {}).get(key)
        if chosen:
            if chosen == decision.shown:
                decision.action, decision.hours, decision.quiet_reason = "NO_ACTION", "", "MATCHES_SHOWN"
                return decision
            decision.action, decision.hours, decision.basis = "SUGGEST", chosen, "YOUR_CHOICE"
            decision.evidence = {**decision.evidence, "your_hours": chosen}
            decision.confidence = YOUR_CHOICE_CONFIDENCE
            decision.learning_notes.append(f"Uses the hours the owner chose earlier for {key}.")
        elif decision.action == "SUGGEST" and decision.hours != "closed" and decision.basis != "SHOPPING_CENTRE":
            moved = shift(decision.hours, learned.get("open_shift", 0), learned.get("close_shift", 0))
            if moved != decision.hours:
                decision.learning_notes.append(
                    f"Moved {decision.hours} to {moved}, because the owner changed a similar day the same way.")
                decision.evidence = {**decision.evidence, "shifted_from": decision.hours}
                decision.hours = moved
                if moved == decision.shown:
                    decision.action, decision.hours, decision.quiet_reason = "NO_ACTION", "", "MATCHES_SHOWN"
                    return decision
        if decision.action == "SUGGEST" and decision.hours == "closed" and learned.get("closed_doubts", 0):
            if decision.basis == "PEERS":
                decision.action, decision.hours, decision.quiet_reason = "NO_ACTION", "", "OWNER_DOUBTS_CLOSED"
                decision.learning_notes.append("Owner said they stay open, so a peer pattern alone is not enough.")
                return decision
            decision.confidence *= 0.6
            decision.learning_notes.append("Owner said they stayed open on a similar day, so Connect asks first.")
        return decision

    # ------------------------------------------------------------ for one business

    def decisions_for(self, eid: str, live_holidays: dict | None = None, learned: dict | None = None) -> list:
        out = []
        for row in self.targets.get(eid, []):
            d = date.fromisoformat(row["date"])
            decision = self.model_decision(eid, d, row["day_key"], live_holidays)
            if learned:
                decision = self.apply_learning(decision, learned)
            decision.mode = "SUGGEST" if decision.confidence >= config.SUGGEST_THRESHOLD else "ASK"
            decision.day_name_local = self.calendar_names.get(
                (self.entities[eid]["meta"]["countryCode"], row["date"]), row["day_key"].replace("_", " ").title())
            if decision.action == "SUGGEST":
                self._attach_context(decision, d)
            out.append(decision)
        return out

    def _attach_context(self, decision: Decision, d: date) -> None:
        """Findability: search views at stake, and any complaints near this day last year."""
        eid = decision.entity_id
        country = self.entities[eid]["meta"]["countryCode"]
        previous = [x for x in self.dates_by_key[(country, decision.day_key)] if _cycle(x) == _cycle(d) - 1]
        by_date = self.views.get("by_date", {}).get(eid, {})
        # Connect can't quote last year's views for a customer who joined after that day.
        since = self.entities[eid].get("c_connectCustomerSince") or ""
        last_year_views = next((by_date[p.isoformat()] for p in previous
                                if p.isoformat() in by_date and p.isoformat() >= since), None)
        decision.views_from_last_year = last_year_views is not None
        decision.expected_views = int(last_year_views if last_year_views is not None
                                      else self.views.get("average", {}).get(eid, 0))
        signals = []
        for p in previous:
            for item in self.complaints.get(eid, []) + self.hour_edits.get(eid, []):
                gap = (date.fromisoformat(item["date"]) - p).days
                if -14 <= gap <= 14:
                    signals.append(item)
        if signals:
            decision.evidence = {**decision.evidence, "signals": signals[:3]}

    def regular_week(self, eid: str) -> dict:
        return {k: v for k, v in self.entities[eid]["hours"].items() if k in DAYS}
