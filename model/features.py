"""Leak-safe features for every (business, special day), as known at a snapshot date.

Rules this file keeps:
- It never opens labels/, so dev and test businesses get features the same way.
- Everything dated on or after the snapshot is ignored: entries, edits, reviews, analytics and the pilot log.
- It never reads mock_api/ (the simulator's internals).
"""
from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from model.review_text import KeywordMatcher

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
RELATED_KEYS = ["FATHERS_DAY", "BLACK_FRIDAY", "INDEPENDENCE_DAY", "LUCIA", "DEC23", "XMAS_EVE", "XMAS_DAY", "BOXING_DAY",
                "INTERDAY", "NYE", "NEW_YEARS_DAY", "EPIPHANY_EVE", "EPIPHANY", "EASTER_SATURDAY", "GOOD_FRIDAY", "MAY_DAY",
                "MIDSUMMER_EVE"]
STATE = {None: 0, "closed": 1, "REGULAR": 2}  # Anything else is special hours (3).
CLOSED_FOR_GOOD = ("lopettanut", "pysyvästi", "stängt för gott", "permanent", "lagt ned", "stengt for godt", "closed down",
                   "lokalen är tom", "tilat tyhjinä")
CLOSED_WORDS = ("kiinni", "suljettu", "stängt", "stengt", "closed", "låst")
# Phrases naming a special day, in fi / sv / nb / en. Most specific first: "lille julaften" also contains "julaften".
REVIEW_DAYS = [(k, re.compile(p)) for k, p in [
    ("DEC23", r"aatonaat|dagen före julafton|lillejul|lille julaft"),
    ("EPIPHANY_EVE", r"loppiaisaat|trettondagsafton|helligtrekongersaft|epiphany eve"),
    ("EPIPHANY", r"loppiai|trettondag|helligtrekonger|epiphany"),
    ("XMAS_EVE", r"jouluaat|julafton|julaft|christmas eve"),
    ("XMAS_DAY", r"joulupäiv|juldag|første juledag|1\. juledag|christmas day"),
    ("BOXING_DAY", r"tapaninpäiv|annandag jul|andre juledag|2\. juledag|boxing day"),
    ("INTERDAY", r"välipäiv|mellandag|romjul"),
    ("NYE", r"uudenvuodenaat|nyårsafton|nyttårsaft|new year's eve"),
    ("NEW_YEARS_DAY", r"uudenvuodenpäiv|nyårsdag|nyttårsdag|new year's day"),
    ("INDEPENDENCE_DAY", r"itsenäisyyspäiv|självständighet|independence day"),
    ("FATHERS_DAY", r"isänpäiv|fars dag|farsdag|father's day"),
    ("LUCIA", r"lucia"),
    ("BLACK_FRIDAY", r"black friday"),
    ("EVENT", r"tapahtumailta|evenemanget|arrangementet"),
    ("SCHOOL_BREAK", r"lomaviikolla|under lovet|i ferien"),
]]
TIME = r"(\d{1,2}(?:[.:]\d{2})?)"
RE_CLOSE_AT = re.compile(r"suljettiin jo klo " + TIME + r"|stängde de redan " + TIME + r"|stengte de allerede " + TIME + r"|closed already at " + TIME)
RE_ARRIVED = re.compile(r"klo " + TIME + r" ja ovet olivat jo kiinni")
RE_WRONG_CLOSED = re.compile(r"olittekin auki|actually open|hade ju öppet|hadde jo åpent")
RE_THANKS_OPEN = re.compile(r"olitte auki|olla auki|hade öppet|hadde åpent|holdt åpent|being open|you were open")
RE_CLOSED = re.compile(r"kiinni|suljet|stängt|stängd|stengt|closed|pimeänä|släckt|mörkt|ei ollut|it wasn't")
RE_WEEK = re.compile(r"(?:nykyään auki vain|numera öppet bara|nå bare åpent|now only open) (.+)")
RE_OUTDATED = re.compile(r"aukioloajat ovat muuttuneet|uusi omistaja|öppettiderna har ändrats|ny ägare|åpningstidene er endret|ny eier|hours have changed|new owner")
RE_SEASONAL = re.compile(r"on tauolla|talvella kiinni|stängt på vintern|stengt om vinteren|closed in winter|closed for the winter|closed in the winter|closed during winter")
RE_REPLY_CONFIRMS = re.compile(r"olimme pyhinä kiinni|aukiolotiedot olivat väärin|unohdimme|öppettiderna var fel|vi glömde|forgot|hours were wrong|åpningstidene var feil|vi glemte")
WEEK_TOKENS = {"ma": 0, "ti": 1, "ke": 2, "to": 3, "pe": 4, "la": 5, "su": 6, "mån": 0, "tis": 1, "ons": 2, "tor": 3, "fre": 4, "lör": 5, "sön": 6,
               "man": 0, "tir": 1, "lør": 5, "søn": 6, "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def clock(text: str) -> int:
    """'14', '14.30' or '14:30' as minutes."""
    parts = re.split(r"[.:]", text)
    return int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)


def clock_range(text: str) -> str | None:
    m = re.fullmatch(TIME + "–" + TIME, text.strip())
    return f"{to_str(clock(m.group(1)))}-{to_str(clock(m.group(2)))}" if m else None


def parse_week(text: str) -> dict | None:
    """'ma–pe 10–18, la 10–15' as {weekday index: hours}. Days not listed are closed ("now only open...")."""
    text = text.split(", päivittäkää")[0].rstrip(". ")
    week = {i: "closed" for i in range(7)}
    found = False
    for part in text.split(", "):
        m = re.match(r"([a-zåäöø]+)(?:–([a-zåäöø]+))? (.+)", part)
        if not m or m.group(1) not in WEEK_TOKENS:
            return None
        first = WEEK_TOKENS[m.group(1)]
        last = WEEK_TOKENS.get(m.group(2), first) if m.group(2) else first
        spans = [clock_range(x) for x in re.split(r" ja | och | og | and ", m.group(3))]
        if not all(spans):
            return None
        for i in range(first, last + 1):
            week[i] = ",".join(spans)
        found = True
    return week if found else None


LIVE_SNAPSHOT = date(2026, 11, 6)
GENERIC_SHIFTS = [(0, -60), (0, -120), (0, -180), (0, -240), (60, 0), (120, 0), (0, 60), (0, 120), (-60, 0), (60, -60), (60, -120)]


def to_min(text: str) -> int:
    return int(text[:2]) * 60 + int(text[3:5])


def to_str(minutes: int) -> str:
    minutes = int(minutes) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def day_str(obj: dict | None) -> str:
    if not obj or obj.get("isClosed"):
        return "closed"
    return ",".join(f"{i['start']}-{i['end']}" for i in obj.get("openIntervals", [])) or "closed"


def span(hours: str | None) -> tuple:
    """(first open, last close) in minutes, with a close past midnight above 1440. (nan, nan) if there are none."""
    if not hours or hours in ("closed", "REGULAR"):
        return (np.nan, np.nan)
    parts = hours.split(",")
    start, end = to_min(parts[0][:5]), to_min(parts[-1][6:11])
    return (start, end if end > start or hours == "00:00-23:59" else end + 1440)


def shifted(hours: str, open_by: float, close_by: float) -> str | None:
    """Move the first opening and last closing. None if the result isn't sensible."""
    if hours in ("closed", "REGULAR") or np.isnan(open_by) or np.isnan(close_by):
        return None
    start, end = span(hours)
    start, end = start + open_by, end + close_by
    if end - start < 60 or end - start >= 1440 or start < 0:
        return None
    parts = hours.split(",")
    if len(parts) == 1:
        return f"{to_str(start)}-{to_str(end)}"
    return f"{to_str(start)}-{parts[0][6:11]},{parts[-1][:5]}-{to_str(end)}"


def cycle(d: date) -> int:
    return d.year if d.month >= 2 else d.year - 1


def keyword_matcher() -> KeywordMatcher | None:
    """Learned review keywords (model/keywords.py). CONNECT_KEYWORDS=off turns them off, a path picks a file,
    and unset uses model/keywords.json if it exists. With none, the hand-written phrases above work alone."""
    choice = os.environ.get("CONNECT_KEYWORDS", "")
    if choice == "off":
        return None
    path = Path(choice) if choice else Path(__file__).with_name("keywords.json")
    if not path.exists():
        if choice:
            raise FileNotFoundError(f"CONNECT_KEYWORDS points to a missing file: {path}")
        return None
    return KeywordMatcher(json.loads(path.read_text(encoding="utf-8")))


class Data:
    """All the challenge's input files, except labels/ and mock_api/."""

    def __init__(self, root: Path):
        data = Path(root) / "data"
        self.root = Path(root)
        ents = json.loads((data / "entities.json").read_text(encoding="utf-8"))["response"]["entities"]
        self.ents = {e["meta"]["id"]: e for e in ents}
        self.hol = defaultdict(list)
        with (data / "holiday_hours_history.jsonl").open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                h = r["holidayHours"]
                self.hol[r["entity_id"]].append({
                    "date": r["date"], "key": r["day_key"], "at": r["entered_at"], "source": r["source"],
                    "hours": "REGULAR" if h.get("isRegularHours") else day_str(h)})
        for rows in self.hol.values():
            rows.sort(key=lambda r: r["at"])
        self.reg = defaultdict(list)
        with (data / "regular_hours_history.jsonl").open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                self.reg[r["entity_id"]].append(r)
        cal = self._csv(data / "calendar_special_days.csv")
        self.dates_by_key = defaultdict(list)
        self.day_info = {}
        for r in cal:
            d = date.fromisoformat(r["date"])
            self.dates_by_key[(r["country"], r["day_key"])].append(d)
            self.day_info[(r["country"], r["date"])] = r
        self.day_info_items = sorted(self.day_info.items())
        self.peers = {(r["country"], r["city_tier"], r["segment"], r["day_key"]): r for r in self._csv(data / "peer_benchmarks.csv")}
        self.tiers = {r["city"]: r["city_tier"] for r in self._csv(data / "cities.csv")}
        self.contacts = {r["entity_id"]: r for r in self._csv(data / "customer_contacts.csv")}
        self.archetype = {r["segment"]: r["archetype"] for r in self._csv(data / "categories.csv")}
        self.pilot = defaultdict(list)
        for r in self._csv(data / "pilot_decision_log_2025.csv"):
            self.pilot[r["entity_id"]].append(r)
        self.normals = {(r["city"], int(r["month"]), int(r["day"])): r for r in self._csv(data / "weather_normals.csv")}
        self.weather = {(r["city"], r["date"]): r for r in self._csv(data / "weather_daily.csv")}
        self.breaks = defaultdict(list)
        for r in self._csv(data / "school_breaks.csv"):
            self.breaks[r["country"]].append((r["start"], r["end"]))
        events = json.loads((data / "local_events.json").read_text(encoding="utf-8"))["data"]
        self.events = {e["@id"]: e for e in events}
        self.keywords = keyword_matcher()
        self._load_reviews(data)
        self._load_edits(data)
        self._load_analytics(data)

    @staticmethod
    def _csv(path: Path) -> list:
        with path.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _load_reviews(self, data: Path) -> None:
        """Read what reviewers say in four languages, and tie each statement to the past day it's about."""
        reviews = json.loads((data / "reviews.json").read_text(encoding="utf-8"))["response"]["reviews"]
        dates_by_country = defaultdict(list)
        for (country, day_text) in self.day_info:
            dates_by_country[country].append(day_text)
        for days in dates_by_country.values():
            days.sort()
        self.rev_key = defaultdict(list)  # eid -> (when, key) for closed-door complaints
        self.rev_closed = defaultdict(list)  # eid -> when, any closed-door complaint
        self.rev_gone = defaultdict(list)  # eid -> when, "closed for good"
        self.rev_all = defaultdict(list)  # eid -> when
        self.rev_day = defaultdict(list)  # (eid, day) -> statements about that day
        self.rev_week = defaultdict(list)  # eid -> (when, {weekday: hours})
        self.rev_outdated = defaultdict(list)  # eid -> when
        self.rev_seasonal = defaultdict(list)  # eid -> when
        for r in reviews:
            eid = r["locationId"]
            ent = self.ents.get(eid)
            if not ent:
                continue
            when = datetime.fromtimestamp(r["publisherDate"] / 1000).date().isoformat()
            self.rev_all[eid].append(when)
            text = (r.get("content") or "").lower()
            if not text:
                continue
            week = RE_WEEK.search(text)
            if week:
                parsed = parse_week(week.group(1))
                if parsed:
                    self.rev_week[eid].append((when, parsed))
                continue
            if RE_OUTDATED.search(text):
                self.rev_outdated[eid].append(when)
                continue
            if any(w in text for w in CLOSED_FOR_GOOD):
                self.rev_gone[eid].append(when)
                continue
            if RE_SEASONAL.search(text) and not any(k.search(text) for _, k in REVIEW_DAYS):
                self.rev_seasonal[eid].append(when)
                continue
            kind, minutes = None, np.nan
            # Learned keywords: "union" adds to the hand-written phrases, "replace" stands in for the
            # hand-written closed and open phrases. Clock times are still read by the patterns above.
            learned = self.keywords.classes(eid, text) if self.keywords else set()
            hand = not (self.keywords and self.keywords.mode == "replace")
            m = RE_CLOSE_AT.search(text)
            if RE_WRONG_CLOSED.search(text):
                kind = "open_shown_closed"
            elif m:
                kind, minutes = "close_at", clock(next(g for g in m.groups() if g))
            elif RE_ARRIVED.search(text):
                kind, minutes = "arrived", clock(RE_ARRIVED.search(text).group(1))
            elif hand and RE_THANKS_OPEN.search(text):
                kind = "open"
            elif hand and RE_CLOSED.search(text):
                kind = "closed"
            elif learned:
                kind = next(c for c in ("closed", "early", "open") if c in learned)
            if not kind:
                continue
            key = next((k for k, pattern in REVIEW_DAYS if pattern.search(text)), None)
            country = ent["meta"]["countryCode"]
            day = self._day_for(country, key, when, dates_by_country[country])
            confirmed = any(RE_REPLY_CONFIRMS.search((c.get("content") or "").lower()) for c in (r.get("comments") or []))
            if kind in ("closed", "close_at", "arrived", "early"):
                self.rev_closed[eid].append(when)
                if key:
                    self.rev_key[eid].append((when, key))
            if day:
                self.rev_day[(eid, day)].append({"when": when, "kind": kind, "minutes": minutes, "confirmed": confirmed,
                                                 "learned": learned})

    def _day_for(self, country: str, key: str | None, when: str, days: list) -> str | None:
        """The latest date of the named day before the review, or the latest special day if it's unnamed."""
        limit = (date.fromisoformat(when) - timedelta(days=60)).isoformat()
        if key:
            named = [d.isoformat() for d in self.dates_by_key.get((country, key), []) if limit <= d.isoformat() <= when]
            if named:
                return named[-1]
        near = (date.fromisoformat(when) - timedelta(days=21)).isoformat()
        unnamed = [d for d in days if near <= d <= when]
        return unnamed[-1] if unnamed else None

    def _load_edits(self, data: Path) -> None:
        edits = json.loads((data / "publisher_suggestions.json").read_text(encoding="utf-8"))["response"]["suggestions"]
        self.edit_day = defaultdict(list)  # (eid, date) -> (created, hours, status)
        self.edit_week = defaultdict(list)  # (eid, weekday) -> (created, hours, status)
        self.edit_gone = defaultdict(list)  # eid -> (created, status)
        for e in edits:
            eid, created, status = e["locationId"], e["dateCreated"][:10], e["status"]
            if e["fieldName"] == "closed":
                self.edit_gone[eid].append((created, status))
                continue
            content = json.loads(e["suggestedContent"])
            for item in content.get("holidayHours", []):
                self.edit_day[(eid, item["date"])].append((created, day_str(item), status))
            for weekday in DAYS:
                if weekday in content:
                    self.edit_week[(eid, weekday)].append((created, day_str(content[weekday]), status))

    def _load_analytics(self, data: Path) -> None:
        metrics = ["GOOGLE_SEARCH_VIEWS", "GOOGLE_PHONE_CALLS", "GOOGLE_CUSTOMER_ACTIONS", "GOOGLE_MAP_VIEWS", "PROFILE_VIEWS", "GOOGLE_SEARCH_QUERIES"]
        a = pd.read_parquet(data / "analytics_daily.parquet", columns=["date", "entity_id"] + metrics)
        a["date"] = pd.to_datetime(a["date"])
        self.day0 = a["date"].min().date()
        n_days = (a["date"].max().date() - self.day0).days + 1
        ids = {eid: i for i, eid in enumerate(sorted(a["entity_id"].unique()))}
        self.an_index = ids
        self.an = np.full((len(ids), n_days, len(metrics)), np.nan, dtype=np.float32)
        ei = a["entity_id"].map(ids).to_numpy()
        di = (a["date"] - pd.Timestamp(self.day0)).dt.days.to_numpy()
        for m, metric in enumerate(metrics):
            self.an[ei, di, m] = a[metric].to_numpy()

    # ---------------------------------------------------------------- as-of views

    def regular(self, eid: str, d: date, asof: date) -> str:
        cands = [r for r in self.reg[eid] if r["effective_from"] == "before-2024" or r["effective_from"] < asof.isoformat()]
        best = max(cands, key=lambda r: "0000" if r["effective_from"] == "before-2024" else r["effective_from"])
        return day_str(best["hours"][DAYS[d.weekday()]])

    def entries(self, eid: str, asof: date) -> dict:
        """date -> latest entry entered before the snapshot."""
        limit = asof.isoformat()
        out = {}
        for r in self.hol.get(eid, []):
            if r["at"] < limit:
                out[r["date"]] = r
        return out

    def analytics_ratio(self, eid: str, d: date, metric: int) -> float:
        """That day's value against the same weekday in the 8 weeks before it."""
        i = self.an_index.get(eid)
        day = (d - self.day0).days
        if i is None or day < 7 or day >= self.an.shape[1]:
            return np.nan
        value = self.an[i, day, metric]
        past = [self.an[i, day - 7 * w, metric] for w in range(1, 9) if day - 7 * w >= 0]
        past = [p for p in past if not np.isnan(p)]
        if np.isnan(value) or not past:
            return np.nan
        return float((value + 1) / (np.mean(past) + 1))

    def analytics_recent(self, eid: str, asof: date, days: int, metric: int = 0) -> float:
        i = self.an_index.get(eid)
        end = min((asof - self.day0).days, self.an.shape[1])
        if i is None or end <= 0:
            return np.nan
        window = self.an[i, max(0, end - days):end, metric]
        return float(np.nanmean(window)) if np.any(~np.isnan(window)) else np.nan


class PopulationModes:
    """Most common special hours by business type and day, from everyone's entries before the snapshot."""

    def __init__(self, data: Data, asof: date):
        limit = asof.isoformat()
        hours, deltas = defaultdict(Counter), defaultdict(Counter)
        for eid, rows in data.hol.items():
            ent = data.ents.get(eid)
            if not ent or ent.get("c_segment") == "shopping_centre":
                continue
            segment = ent["c_segment"]
            latest = {}
            for r in rows:
                if r["at"] < limit:
                    latest[r["date"]] = r
            for day_text, r in latest.items():
                if r["hours"] in ("closed", "REGULAR"):
                    continue
                hours[(segment, r["key"])][r["hours"]] += 1
                reg = data.regular(eid, date.fromisoformat(day_text), asof)
                if reg != "closed":
                    a, b = span(r["hours"]), span(reg)
                    deltas[(segment, r["key"])][(a[0] - b[0], a[1] - b[1])] += 1
        self.hours = hours
        self.deltas = deltas


def previous_dates(data: Data, country: str, key: str, d: date, years_back: int) -> list:
    """The same special day N years ago. Days with several dates (between-holidays) use the closest calendar match."""
    found = [x for x in data.dates_by_key.get((country, key), []) if cycle(x) == cycle(d) - years_back]
    if not found:
        return []
    target = d.replace(year=2000 + (1 if d.month == 1 else 0))
    return sorted(found, key=lambda x: abs((x.replace(year=2000 + (1 if x.month == 1 else 0)) - target).days))


def state_code(hours: str | None) -> int:
    return STATE.get(hours, 3)


def build_row(data: Data, modes: PopulationModes, eid: str, d: date, key: str, event_id: str, asof: date) -> tuple:
    """Return (row features, candidate hours -> set of sources, shown hours)."""
    ent = data.ents[eid]
    country = ent["meta"]["countryCode"]
    segment = ent["c_segment"]
    city = ent["address"]["city"]
    tier = data.tiers.get(city, "town")
    d_text, limit = d.isoformat(), asof.isoformat()
    entries = data.entries(eid, asof)
    this_entry = entries.get(d_text)
    if asof == LIVE_SNAPSHOT:
        # entities.json is the live listing at this snapshot. The version log can disagree with it.
        regular = day_str(ent["hours"].get(DAYS[d.weekday()]))
    else:
        regular = data.regular(eid, d, asof)
    listing_closed = asof == LIVE_SNAPSHOT and bool(ent.get("closed"))
    shown = regular if this_entry is None or this_entry["hours"] == "REGULAR" else this_entry["hours"]
    if listing_closed:
        shown = "closed"
    reg_open, reg_close = span(regular)
    shown_open, shown_close = span(shown)
    info = data.day_info.get((country, d_text), {})
    since = ent.get("c_connectCustomerSince") or "2000-01-01"
    contact = data.contacts.get(eid, {})

    row = {
        "entity_id": eid, "date": d_text, "day_key": key, "shown": shown, "listing_closed": int(listing_closed), "segment": segment, "country": country,
        "tier": tier, "archetype": data.archetype.get(segment, ""), "day_class": info.get("day_class", key),
        "day_type": info.get("day_type", key), "weekday": d.weekday(), "month": d.month,
        "official_holiday": int(info.get("official_public_holiday") or 0), "lead_days": (d - asof).days,
        "regular_closed": int(regular == "closed"), "reg_open": reg_open, "reg_close": reg_close,
        "reg_len": reg_close - reg_open, "shown_closed": int(shown == "closed"), "shown_open": shown_open,
        "shown_close": shown_close, "has_entry_now": int(this_entry is not None),
        "entry_now_state": state_code(this_entry["hours"]) if this_entry else 0,
        "entry_now_lead": (d - date.fromisoformat(this_entry["at"][:10])).days if this_entry else np.nan,
        "tenure_days": (asof - date.fromisoformat(since)).days, "standing": int(contact.get("standing_permission_holidays") or 0),
        "two_intervals": int("," in regular),
    }

    candidates = defaultdict(set)
    shares = defaultdict(dict)

    def add(hours, source, share=None):
        if hours and hours not in ("closed", "REGULAR") and hours != shown:
            candidates[hours].add(source)
            if share is not None:
                shares[hours][source] = max(share, shares[hours].get(source, 0.0))

    # The same day in earlier years.
    for years in (1, 2):
        past = previous_dates(data, country, key, d, years)
        p = past[0] if past else None
        prefix = f"y{years}_"
        entry = None
        if p is not None:
            entry = entries.get(p.isoformat())
        hours = entry["hours"] if entry else None
        reg_then = data.regular(eid, p, asof) if p is not None else None
        then_open, then_close = span(reg_then)
        e_open, e_close = span(hours)
        row[prefix + "state"] = state_code(hours)
        row[prefix + "same_weekday"] = int(p.weekday() == d.weekday()) if p is not None else -1
        row[prefix + "reg_closed"] = int(reg_then == "closed") if p is not None else -1
        row[prefix + "d_open"] = e_open - then_open
        row[prefix + "d_close"] = e_close - then_close
        row[prefix + "open"] = e_open
        row[prefix + "close"] = e_close
        row[prefix + "lead"] = (p - date.fromisoformat(entry["at"][:10])).days if entry else np.nan
        row[prefix + "source"] = {"OWNER_UI": 1, "CONNECT_SUGGESTION": 2, "FONECTA_SUPPORT": 3, "API_INTEGRATION": 4}.get(entry["source"], 0) if entry else 0
        row[prefix + "calls_ratio"] = data.analytics_ratio(eid, p, 1) if p is not None else np.nan
        row[prefix + "views_ratio"] = data.analytics_ratio(eid, p, 0) if p is not None else np.nan
        row[prefix + "actions_ratio"] = data.analytics_ratio(eid, p, 2) if p is not None else np.nan
        # User edits naming that past date. They can arrive after the day, so they rebuild the habit.
        edits = [x for x in data.edit_day.get((eid, p.isoformat()), []) if x[0] < limit] if p is not None else []
        row[prefix + "edit_state"] = state_code(edits[-1][1]) if edits else 0
        row[prefix + "edit_rejected"] = int(any(x[2] == "REJECTED" for x in edits))
        row[prefix + "edit_n"] = len(edits)
        said = [x for x in data.rev_day.get((eid, p.isoformat()), []) if x["when"] < limit] if p is not None else []
        close_at = [x["minutes"] for x in said if x["kind"] == "close_at"]
        arrived = [x["minutes"] for x in said if x["kind"] == "arrived"]
        row[prefix + "rev_closed"] = sum(x["kind"] == "closed" for x in said)
        row[prefix + "rev_open"] = sum(x["kind"] in ("open", "open_shown_closed") for x in said)
        row[prefix + "rev_close_at"] = close_at[-1] if close_at else np.nan
        row[prefix + "rev_arrived"] = arrived[-1] if arrived else np.nan
        row[prefix + "rev_confirmed"] = int(any(x["confirmed"] for x in said))
        row[prefix + "rev_d_close"] = (close_at[-1] if close_at else np.nan) - then_close
        row[prefix + "rev_d_arrived"] = (arrived[-1] if arrived else np.nan) - then_close
        if data.keywords:  # Only with learned keywords, so the model without them is unchanged.
            row[prefix + "rev_early"] = sum(x["kind"] == "early" for x in said)
            for cls in ("closed", "early", "open"):
                row[prefix + "kw_" + cls] = sum(cls in x["learned"] for x in said)
        if reg_then not in (None, "closed") and regular != "closed":
            for name, values in (("rev_close", close_at), ("rev_arrived", arrived)):
                for minutes in values[-1:]:
                    # Someone arriving to a closed door came about 20 minutes after closing (checked on dev).
                    close = minutes - (20 if name == "rev_arrived" else 0)
                    add(shifted(regular, 0, close - then_close), f"{prefix}{name}")
                    add(shifted(reg_then, 0, close - then_close), f"{prefix}{name}")
        if hours:
            add(hours, f"{prefix}entry")
            if hours not in ("closed", "REGULAR") and reg_then not in (None, "closed") and regular != "closed":
                add(shifted(regular, e_open - then_open, e_close - then_close), f"{prefix}delta")
        if hours == "REGULAR" and p is not None:
            add(reg_then, f"{prefix}regular_then")
        for x in edits:
            add(x[1], f"{prefix}edit")
            if x[1] != "closed" and reg_then not in (None, "closed") and regular != "closed":
                a = span(x[1])
                add(shifted(regular, a[0] - then_open, a[1] - then_close), f"{prefix}edit_delta")

    # This business's habits as a whole.
    past_entries = [r for day_text, r in entries.items() if day_text < limit]
    n = len(past_entries)
    row["n_entries"] = n
    row["n_entries_closed"] = sum(r["hours"] == "closed" for r in past_entries)
    row["n_entries_special"] = sum(r["hours"] not in ("closed", "REGULAR") for r in past_entries)
    row["n_entries_regular"] = sum(r["hours"] == "REGULAR" for r in past_entries)
    row["closed_share"] = row["n_entries_closed"] / n if n else np.nan
    row["special_share"] = row["n_entries_special"] / n if n else np.nan
    leads = [(date.fromisoformat(r["date"]) - date.fromisoformat(r["at"][:10])).days for r in past_entries]
    row["entered_in_time_share"] = float(np.mean([x > 0 for x in leads])) if leads else np.nan
    row["entry_lead_median"] = float(np.median(leads)) if leads else np.nan
    last_year = [r for r in past_entries if r["date"] >= (asof - timedelta(days=365)).isoformat()]
    row["n_entries_12m"] = len(last_year)
    upcoming = [r for day_text, r in entries.items() if day_text >= limit]
    row["n_upcoming_entered"] = len(upcoming)
    row["n_upcoming_closed"] = sum(r["hours"] == "closed" for r in upcoming)
    latest_by_key = {}
    for day_text in sorted(entries):
        if day_text < limit:
            latest_by_key[entries[day_text]["key"]] = entries[day_text]["hours"]
    for k in RELATED_KEYS:
        row[f"key_{k}"] = state_code(latest_by_key.get(k))
    row["same_class_closed"] = np.nan
    if info.get("day_class"):
        same = [r for r in past_entries if data.day_info.get((country, r["date"]), {}).get("day_class") == info["day_class"]]
        row["same_class_n"] = len(same)
        if same:
            row["same_class_closed"] = sum(r["hours"] == "closed" for r in same) / len(same)
    else:
        row["same_class_n"] = 0
    own_deltas, own_hours = Counter(), Counter()
    for r in past_entries:
        if r["hours"] in ("closed", "REGULAR"):
            continue
        own_hours[r["hours"]] += 1
        reg = data.regular(eid, date.fromisoformat(r["date"]), asof)
        if reg != "closed":
            a, b = span(r["hours"]), span(reg)
            own_deltas[(a[0] - b[0], a[1] - b[1])] += 1
    total_own = max(1, sum(own_hours.values()))
    for hours, count in own_hours.most_common(3):
        add(hours, "own_hours", count / total_own)
    if regular != "closed":
        total_delta = max(1, sum(own_deltas.values()))
        for (x, y), count in own_deltas.most_common(3):
            add(shifted(regular, x, y), "own_delta", count / total_delta)
    row["own_mode_d_close"] = own_deltas.most_common(1)[0][0][1] if own_deltas else np.nan
    row["own_mode_d_open"] = own_deltas.most_common(1)[0][0][0] if own_deltas else np.nan

    # Peers.
    cell = data.peers.get((country, tier, segment, key)) or {}
    def fnum(name):
        value = cell.get(name)
        return float(value) if value not in (None, "") else np.nan
    row["peer_n"] = fnum("n_entity_days")
    row["peer_no_entry"] = fnum("share_no_exception_entered")
    row["peer_closed"] = fnum("share_entered_closed")
    row["peer_special"] = fnum("share_entered_special_hours")
    row["peer_regular"] = fnum("share_entered_regular")
    row["peer_closed_among"] = fnum("closed_share_among_entered")
    peer_open, peer_close = cell.get("median_open_special"), cell.get("median_close_special")
    row["peer_open"] = to_min(peer_open) if peer_open else np.nan
    row["peer_close"] = to_min(peer_close) if peer_close else np.nan
    row["peer_d_close"] = row["peer_close"] - reg_close
    row["peer_d_open"] = row["peer_open"] - reg_open
    if peer_open and peer_close:
        add(f"{peer_open}-{peer_close}", "peer_median")
        if regular != "closed":
            add(f"{to_str(reg_open)}-{peer_close}", "peer_close")
            add(f"{peer_open}-{to_str(reg_close)}", "peer_open")

    # Same-type businesses' most common hours and changes.
    pop_hours = modes.hours.get((segment, key), Counter())
    total_pop = max(1, sum(pop_hours.values()))
    for hours, count in pop_hours.most_common(4):
        add(hours, "pop_hours", count / total_pop)
    if regular != "closed":
        pop_deltas = modes.deltas.get((segment, key), Counter())
        total_pop_delta = max(1, sum(pop_deltas.values()))
        for (x, y), count in pop_deltas.most_common(4):
            add(shifted(regular, x, y), "pop_delta", count / total_pop_delta)
        for x, y in GENERIC_SHIFTS:
            add(shifted(regular, x, y), "generic")

    # Shopping centre.
    mall = ent.get("c_shoppingCenterEntityId")
    row["in_mall"] = int(bool(mall))
    mall_hours = None
    if mall:
        mall_entries = data.entries(mall, asof)
        mall_entry = mall_entries.get(d_text)
        mall_hours = mall_entry["hours"] if mall_entry else None
        matches = total = 0
        for day_text, r in entries.items():
            other = mall_entries.get(day_text)
            if other and day_text < limit:
                total += 1
                matches += r["hours"] == other["hours"]
        row["mall_follow_n"] = total
        row["mall_follow_share"] = matches / total if total else np.nan
        add(mall_hours, "mall")
    else:
        row["mall_follow_n"] = 0
        row["mall_follow_share"] = np.nan
    row["mall_state"] = state_code(mall_hours)
    a = span(mall_hours)
    row["mall_open"], row["mall_close"] = a
    row["mall_eq_regular"] = int(mall_hours == regular) if mall_hours else -1

    # Complaints, edits and closure signs.
    complaints = [(w, k) for w, k in data.rev_key.get(eid, []) if w < limit]
    row["rev_key_n"] = sum(k == key for _, k in complaints)
    row["rev_key_any"] = len(complaints)
    row["rev_closed_n"] = sum(w < limit for w in data.rev_closed.get(eid, []))
    recent = (asof - timedelta(days=180)).isoformat()
    row["rev_gone_recent"] = sum(recent <= w < limit for w in data.rev_gone.get(eid, []))
    row["rev_gone_all"] = sum(w < limit for w in data.rev_gone.get(eid, []))
    gone = [x for x in data.edit_gone.get(eid, []) if x[0] < limit]
    row["edit_gone_n"] = len(gone)
    row["edit_gone_recent"] = sum(x[0] >= recent for x in gone)
    row["edit_gone_accepted"] = sum(x[1] == "ACCEPTED" for x in gone)
    row["edit_gone_rejected"] = sum(x[1] == "REJECTED" for x in gone)
    row["reviews_90d"] = sum((asof - timedelta(days=90)).isoformat() <= w < limit for w in data.rev_all.get(eid, []))
    weekday = DAYS[d.weekday()]
    week_edits = [x for x in data.edit_week.get((eid, weekday), []) if x[0] < limit]
    row["week_edit_n"] = len(week_edits)
    row["week_edit_rejected"] = sum(x[2] == "REJECTED" for x in week_edits)
    row["week_edit_differs"] = int(any(x[1] != regular for x in week_edits))
    row["week_edit_recent_n"] = sum(x[0] >= (asof - timedelta(days=365)).isoformat() for x in week_edits)
    for x in week_edits[-2:]:
        add(x[1], "week_edit")
    said_week = [x for x in data.rev_week.get(eid, []) if x[0] < limit]
    row["rev_week_n"] = len(said_week)
    row["rev_week_differs"] = -1
    row["rev_week_closed"] = -1
    if said_week:
        hours_then = said_week[-1][1][d.weekday()]
        row["rev_week_differs"] = int(hours_then != regular)
        row["rev_week_closed"] = int(hours_then == "closed")
        add(hours_then, "rev_week")
        if regular != "closed" and hours_then != "closed" and asof:
            week_a, week_b = span(hours_then), span(regular)
            row["rev_week_d_close"] = week_a[1] - week_b[1]
    row.setdefault("rev_week_d_close", np.nan)
    row["rev_outdated_n"] = sum(w < limit for w in data.rev_outdated.get(eid, []))
    row["rev_outdated_recent"] = sum((asof - timedelta(days=365)).isoformat() <= w < limit for w in data.rev_outdated.get(eid, []))
    row["rev_seasonal_n"] = sum(w < limit for w in data.rev_seasonal.get(eid, []))
    all_week = sum(len([x for x in data.edit_week.get((eid, w), []) if x[0] < limit]) for w in DAYS)
    row["week_edit_any"] = all_week
    day_edit_now = [x for x in data.edit_day.get((eid, d_text), []) if x[0] < limit]
    row["edit_now_state"] = state_code(day_edit_now[-1][1]) if day_edit_now else 0
    for x in day_edit_now:
        add(x[1], "edit_now")

    # The 2025 pilot: what this owner said about this kind of day. Only visible once it has happened.
    sent = [r for r in data.pilot.get(eid, []) if r["sent_at"][:10] < limit]
    row["pilot_n"] = len(sent)
    row["pilot_replied"] = sum(r["decision"] != "NO_RESPONSE" for r in sent)
    row["pilot_rejected"] = sum(r["decision"] == "REJECTED" for r in sent)
    row["pilot_edited"] = sum(r["decision"] == "EDITED" for r in sent)
    same_key = [r for r in sent if r["day_key"] == key]
    row["pilot_key"] = {"": 0, "NO_RESPONSE": 1, "ACCEPTED": 2, "EDITED": 3, "REJECTED": 4}.get(same_key[-1]["decision"] if same_key else "", 0)
    row["pilot_key_closed"] = int(same_key[-1]["suggested_hours"] == "closed") if same_key else -1
    row["pilot_says_open"] = int(any("auki" in r["owner_comment"].lower() or "öppet" in r["owner_comment"].lower()
                                     or "open" in r["owner_comment"].lower() for r in same_key))
    for r in same_key:
        if r["decision"] == "EDITED":
            add(r["final_hours"], "pilot_edit")
    row["standing_pilot"] = int(any(r["standing_permission_granted"] in ("1", "True", "true") for r in sent))

    # Demand and context.
    row["views_30d"] = data.analytics_recent(eid, asof, 30)
    row["views_90d"] = data.analytics_recent(eid, asof, 90)
    row["views_365d"] = data.analytics_recent(eid, asof, 365)
    row["views_trend"] = (row["views_30d"] + 1) / (row["views_365d"] + 1) if not np.isnan(row["views_365d"]) else np.nan
    row["calls_30d"] = data.analytics_recent(eid, asof, 30, 1)
    row["actions_30d"] = data.analytics_recent(eid, asof, 30, 2)
    row["actions_trend"] = (row["actions_30d"] + 0.1) / (data.analytics_recent(eid, asof, 365, 2) + 0.1) \
        if not np.isnan(row["actions_30d"]) else np.nan
    normal = data.normals.get((city, d.month, d.day), {})
    row["p_snow"] = float(normal["p_snow_depth_ge_10cm"]) if normal else np.nan
    row["t_normal"] = float(normal["tmean_normal_c"]) if normal else np.nan
    row["in_school_break"] = int(any(a <= d_text <= b for a, b in data.breaks.get(country, [])))
    recent_weather = data.weather.get((city, (asof - timedelta(days=1)).isoformat()), {})
    row["snow_now"] = float(recent_weather["snow_depth_cm"]) if recent_weather.get("snow_depth_cm") not in (None, "") else np.nan
    last_year_weather = data.weather.get((city, (d - timedelta(days=364)).isoformat()), {})
    row["snow_last_year"] = float(last_year_weather["snow_depth_cm"]) if last_year_weather.get("snow_depth_cm") not in (None, "") else np.nan
    event = data.events.get(event_id) if event_id else None
    row["is_event"] = int(bool(event))
    row["event_attendance"] = float(event.get("x_expected_attendance") or 0) if event else 0.0
    if event:
        lon, lat = event["location"]["position"]["coordinates"]
        geo = ent.get("geocodedCoordinate") or {}
        row["event_km"] = float(np.hypot((geo.get("latitude", lat) - lat) * 111, (geo.get("longitude", lon) - lon) * 55))
        row["event_end"] = to_min(event["end_time"][11:16]) if event.get("end_time") else np.nan
    else:
        row["event_km"] = np.nan
        row["event_end"] = np.nan
    row["n_candidates"] = len(candidates)
    row["_shares"] = dict(shares)
    return row, candidates, shown


SOURCES = ["y1_entry", "y1_delta", "y1_regular_then", "y1_edit", "y1_edit_delta", "y2_entry", "y2_delta", "y2_regular_then",
           "y2_edit", "y2_edit_delta", "own_hours", "own_delta", "peer_median", "peer_close", "peer_open", "pop_hours",
           "pop_delta", "generic", "mall", "week_edit", "edit_now", "pilot_edit", "y1_rev_close", "y1_rev_arrived",
           "y2_rev_close", "y2_rev_arrived", "rev_week"]


def candidate_features(cand: str, sources: set, row: dict) -> dict:
    start, end = span(cand)
    out = {f"src_{s}": int(s in sources) for s in SOURCES}
    share = row.get("_shares", {}).get(cand, {})
    out.update({
        "share_own_hours": share.get("own_hours", 0.0), "share_own_delta": share.get("own_delta", 0.0),
        "share_pop_hours": share.get("pop_hours", 0.0), "share_pop_delta": share.get("pop_delta", 0.0),
        "cand": cand, "cand_open": start, "cand_close": end, "cand_len": end - start, "cand_two": int("," in cand),
        "cand_d_open_reg": start - row["reg_open"], "cand_d_close_reg": end - row["reg_close"],
        "cand_d_open_shown": start - row["shown_open"], "cand_d_close_shown": end - row["shown_close"],
        "cand_n_sources": len(sources), "cand_n_strong": len(sources - {"generic", "pop_hours", "pop_delta", "peer_close", "peer_open"}),
        "cand_d_close_peer": end - row["peer_close"], "cand_d_open_peer": start - row["peer_open"],
        "cand_d_close_y1": end - row["y1_close"], "cand_d_open_y1": start - row["y1_open"],
        "cand_d_close_own": (end - row["reg_close"]) - row["own_mode_d_close"],
    })
    return out


def past_day_rows(data: Data, eid: str, asof: date) -> list:
    """One row per past special day for this business: what's on record, and the traces that day left behind."""
    ent = data.ents[eid]
    country = ent["meta"]["countryCode"]
    limit = asof.isoformat()
    entries = data.entries(eid, asof)
    by_key = defaultdict(list)
    for r in entries.values():
        if r["date"] < limit:
            by_key[r["key"]].append(r["hours"])
    past = [r for r in entries.values() if r["date"] < limit]
    n = len(past)
    closed_share = sum(r["hours"] == "closed" for r in past) / n if n else np.nan
    special_share = sum(r["hours"] not in ("closed", "REGULAR") for r in past) / n if n else np.nan
    complaints = [x for x in data.rev_key.get(eid, []) if x[0] < limit]
    any_closed = [w for w in data.rev_closed.get(eid, []) if w < limit]
    i = data.an_index.get(eid)
    outdated = sum(w < limit for w in data.rev_outdated.get(eid, []))
    seasonal = sum(w < limit for w in data.rev_seasonal.get(eid, []))
    out = []
    for (c, day_text), info in data.day_info_items:
        if c != country or day_text >= limit:
            continue
        p = date.fromisoformat(day_text)
        key = info["day_key"]
        entry = entries.get(day_text)
        said = [x for x in data.rev_day.get((eid, day_text), []) if x["when"] < limit]
        close_at = [x["minutes"] for x in said if x["kind"] == "close_at"]
        arrived = [x["minutes"] for x in said if x["kind"] == "arrived"]
        said_week = [x for x in data.rev_week.get(eid, []) if x[0] < limit]
        week_hours = said_week[-1][1] if said_week else None
        regular = data.regular(eid, p, asof)
        after = (p + timedelta(days=30)).isoformat()
        soon = (p + timedelta(days=10)).isoformat()
        edits = [x for x in data.edit_day.get((eid, day_text), []) if x[0] < limit]
        others = by_key.get(key, [])
        calls = views = actions = calls_base = views_base = np.nan
        extra = {f"m{m}_ratio": np.nan for m in (2, 3, 4, 5)}
        if i is not None:
            day = (p - data.day0).days
            if 0 <= day < data.an.shape[1]:
                calls, views, actions = data.an[i, day, 1], data.an[i, day, 0], data.an[i, day, 2]
                weeks = [day - 7 * w for w in range(1, 9) if day - 7 * w >= 0]
                if weeks:
                    base = data.an[i, weeks]
                    known = ~np.isnan(base)
                    means = np.where(known.any(axis=0), np.nansum(base, axis=0) / np.maximum(known.sum(axis=0), 1), np.nan)
                    calls_base, views_base = float(means[1]), float(means[0])
                    for m in extra:
                        k = int(m[1])
                        value = data.an[i, day, k]
                        extra[m] = float((value + 1) / (means[k] + 1)) if not np.isnan(value) and not np.isnan(means[k]) else np.nan
        learned = {}
        if data.keywords:  # Only with learned keywords, so the model without them is unchanged.
            learned["rev_early_day"] = sum(x["kind"] == "early" for x in said)
            for cls in ("closed", "early", "open"):
                learned["kw_" + cls + "_day"] = sum(cls in x["learned"] for x in said)
        out.append({
            **learned,
            "entity_id": eid, "date": day_text, "day_key": key, "day_class": info["day_class"], "day_type": info["day_type"],
            "segment": ent["c_segment"], "country": country, "tier": data.tiers.get(ent["address"]["city"], "town"),
            "weekday": p.weekday(), "month": p.month, "regular_closed": int(regular == "closed"), "regular": regular,
            "reg_len": span(regular)[1] - span(regular)[0], "has_entry": int(entry is not None),
            "entry_hours": entry["hours"] if entry else "", "entry_in_time": int(entry["at"][:10] < day_text) if entry else -1,
            "entry_at": entry["at"][:10] if entry else "",
            "calls": calls, "views": views, "actions": actions, "calls_base": calls_base, "views_base": views_base,
            "calls_ratio": (calls + 1) / (calls_base + 1) if not np.isnan(calls) and not np.isnan(calls_base) else np.nan,
            "views_ratio": (views + 1) / (views_base + 1) if not np.isnan(views) and not np.isnan(views_base) else np.nan,
            **extra,
            "rev_closed_day": sum(x["kind"] == "closed" for x in said),
            "rev_open_day": sum(x["kind"] == "open" for x in said),
            "rev_wrong_closed_day": sum(x["kind"] == "open_shown_closed" for x in said),
            "rev_close_at": close_at[-1] if close_at else np.nan,
            "rev_arrived": arrived[-1] if arrived else np.nan,
            "rev_d_close": (close_at[-1] if close_at else np.nan) - span(regular)[1],
            "rev_d_arrived": (arrived[-1] if arrived else np.nan) - span(regular)[1],
            "rev_confirmed": int(any(x["confirmed"] for x in said)),
            "rev_week_differs": int(week_hours is not None and week_hours[p.weekday()] != regular),
            "rev_outdated": outdated, "rev_seasonal": seasonal,
            "rev_named": sum(k == key and day_text <= w <= after for w, k in complaints),
            "rev_near": sum(day_text <= w <= soon for w in any_closed),
            "edit_n": len(edits), "edit_closed": int(any(x[1] == "closed" for x in edits)),
            "edit_open": int(any(x[1] != "closed" and x[1] != regular for x in edits)),
            "edit_rejected": int(any(x[2] == "REJECTED" for x in edits)),
            "other_years_closed": sum(h == "closed" for h in others), "other_years_special": sum(h not in ("closed", "REGULAR") for h in others),
            "other_years_regular": sum(h == "REGULAR" for h in others), "closed_share": closed_share, "special_share": special_share, "n_entries": n,
        })
    return out
