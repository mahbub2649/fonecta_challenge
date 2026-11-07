#!/usr/bin/env python3
"""Does the next suggestion get better after an owner replies? Two tests on dev businesses, scored with the organisers' points.

    python3 tools/measure_learning.py [--limit 40]

1. Owner simulator: the same owners answer the same way, with Connect's learning on and off. Only dates after an owner's
   first reply count, because learning can't act before that.
2. Pilot replay: the owners' logged 2025 decisions are given to the learning rules, then this season's suggestions change.

Labels are only used to score. They never reach the engine.
"""
import argparse
import collections
import csv
import importlib.util
import json
import os
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["MOCK_QUIET"] = "1"
os.environ["CONNECT_NO_SANDBOX"] = "1"

from connect import config  # noqa: E402
from connect.engine import Engine  # noqa: E402
from connect.hours import edit_shift  # noqa: E402
from connect.service import Service  # noqa: E402
from connect.store import Store  # noqa: E402
from connect.yext import YextClient  # noqa: E402

sys.path.insert(0, str(config.DATA_DIR / "mock_api"))
import server as mock_server  # noqa: E402

mock_server.STATE_FILE = os.path.join(tempfile.mkdtemp(), "state.json")
mock_server.STORE = mock_server.Store()
_httpd = ThreadingHTTPServer(("127.0.0.1", 0), mock_server.Handler)
threading.Thread(target=_httpd.serve_forever, daemon=True).start()


class Simulated(YextClient):
    """A different seed draws a different set of owner answers."""
    seed = 0

    def owner_response(self, entity_id, day, proposed, channel=None):
        body = {"entityId": entity_id, "date": day, "proposedHours": proposed, "messageId": f"run-{self.seed}"}
        if channel:
            body["channel"] = channel
        return self._mock_post("/sim/v1/owner-response", body)


MOCK = Simulated(f"http://127.0.0.1:{_httpd.server_address[1]}", "demo")

_spec = importlib.util.spec_from_file_location("evaluate", config.DATA_DIR / "evaluation" / "evaluate.py")
SCORER = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SCORER)
LABELS = {(r["entity_id"], r["date"]): r for r in csv.DictReader((config.DATA_DIR / "labels" / "dev_labels_2026.csv").open(encoding="utf-8"))}
MAX_ROUNDS = 14


def points(row: dict, hours: str | None) -> float:
    """The scorer's points for one row, for a suggestion or for staying quiet."""
    truth, shown = row["truth_hours"], row["displayed_hours_at_snapshot"]
    if hours is None:
        return 0.0
    wrong_state = (hours == "closed") != (truth == "closed")
    if row["needs_action"] == "1":
        if hours == truth:
            return 1.0
        if wrong_state:
            return -1.0
        return 0.6 if SCORER.near(hours, truth) else 0.2
    if wrong_state:
        return -1.0
    return -0.1 if hours == shown else -0.5


class NoLearning(Service):
    def _learn(self, case, items, raw_decisions):
        pass


def play(service_class, engine, ids):
    """Every business answers each message until Connect goes quiet. Returns {business: [one record per date asked]}."""
    MOCK.reset()
    service = service_class(engine, Store(":memory:"), MOCK, public_url="http://test")
    out = {}
    for eid in ids:
        records = []
        for round_number in range(MAX_ROUNDS):
            result = service.detect(eid)
            if result["result"] != "CASE":
                break
            case = service.send(result["case_id"])
            view = service.simulate_owner(case["id"]) if case["status"] == "SENT" else case
            for item in view["items"]:
                records.append({"date": item["date"], "proposed": item["proposed"], "decision": item["decision"], "final": item.get("final_hours"), "round": round_number,
                                "notes": item.get("learning_notes") or [], "alternative": item["evidence"].get("alternative")})
            service.store.execute("UPDATE cases SET status = 'EXPIRED' WHERE id = ? AND status IN ('DETECTED', 'SENT')", (case["id"],))
        out[eid] = records
    return out


def summarise(pairs: list) -> dict:
    """pairs: (business, row, hours with learning off, hours with learning on)."""
    total = collections.Counter()
    by_business = collections.defaultdict(float)
    for eid, row, off, on in pairs:
        a, b = points(row, off), points(row, on)
        by_business[eid] += b - a
        total["rows"] += 1
        total["points_off"] += a
        total["points_on"] += b
        total["changed"] += off != on
        for name, hours in (("off", off), ("on", on)):
            total[f"asked_{name}"] += hours is not None
            total[f"exact_{name}"] += hours is not None and row["needs_action"] == "1" and hours == row["truth_hours"]
            total[f"wrong_state_{name}"] += hours is not None and (hours == "closed") != (row["truth_hours"] == "closed")
            total[f"needless_{name}"] += hours is not None and row["needs_action"] != "1"
    gains = list(by_business.values())
    rng = random.Random(7)
    draws = sorted(sum(rng.choices(gains, k=len(gains))) for _ in range(2000)) if gains else [0, 0]
    total["businesses"] = len(gains)
    total["gain"] = total["points_on"] - total["points_off"]
    total["gain_low"], total["gain_high"] = draws[int(len(draws) * .025)], draws[int(len(draws) * .975)]
    return dict(total)


def show(name: str, s: dict) -> None:
    if not s.get("rows"):
        print(f"{name}: no rows")
        return
    print(f"{name}: {s['businesses']} businesses, {s['rows']} dates, {s['changed']} changed")
    print(f"   points {s['points_off']:.1f} -> {s['points_on']:.1f}, gain {s['gain']:+.1f} (95% range {s['gain_low']:+.1f} to {s['gain_high']:+.1f})")
    print(f"   asked {s['asked_off']} -> {s['asked_on']}, exact {s['exact_off']} -> {s['exact_on']}, wrong open/closed {s['wrong_state_off']} -> {s['wrong_state_on']}, needless {s['needless_off']} -> {s['needless_on']}", flush=True)


def simulator_test(engine, ids) -> dict:
    off, on = play(NoLearning, engine, ids), play(Service, engine, ids)
    decisions = collections.Counter(r["decision"] for rows in on.values() for r in rows)
    print("Simulated replies:", dict(decisions))
    offers = [(BY_BUSINESS[e][(e, r["date"])]["truth_hours"], r["proposed"], r["alternative"]) for e, rows in on.items() for r in rows if r["alternative"]]
    print(f"One-tap option offered on {len(offers)} dates: suggestion exactly right on {sum(t == p for t, p, a in offers)}, option exactly right on {sum(t == a for t, p, a in offers)}, "
          f"neither on {sum(t not in (p, a) for t, p, a in offers)}")
    remembered = [(BY_BUSINESS[e][(e, r["date"])]["truth_hours"], r["proposed"]) for e, rows in on.items() for r in rows if any("chose earlier" in n for n in r["notes"])]
    print(f"Owner's earlier choice reused on {len(remembered)} dates: exactly right on {sum(t == p for t, p in remembered)}", flush=True)
    groups = collections.defaultdict(list)
    for eid in ids:
        replied = [r for r in on[eid] if r["decision"] in ("APPROVED", "EDITED", "DECLINED", "AUTO")]
        if not replied:
            continue
        first_round = min(r["round"] for r in replied)
        cut = max(r["date"] for r in on[eid] if r["round"] == first_round)
        kinds = {r["decision"] for r in replied}
        off_map = {r["date"]: r["proposed"] for r in off[eid]}
        on_map = {r["date"]: r["proposed"] for r in on[eid]}
        rows = [(eid, row, off_map.get(day), on_map.get(day)) for (e, day), row in BY_BUSINESS[eid].items() if day > cut]
        groups["all owners who replied"] += rows
        for label, kind in (("owners who edited", "EDITED"), ("owners who declined", "DECLINED")):
            if kind in kinds:
                groups[label] += rows
    return {name: summarise(rows) for name, rows in groups.items()}


def pilot_learned(rows: list) -> dict:
    """The same memory the app builds, from one owner's logged decisions."""
    learned = {}
    for r in rows:
        key, proposed, final = r["day_key"], r["suggested_hours"], r["final_hours"]
        if r["decision"] in ("ACCEPTED", "EDITED") and final:
            learned.setdefault("day_hours", {})[key] = final
        if r["decision"] == "EDITED" and final:
            open_by, close_by = edit_shift(proposed, final)
            if open_by or close_by:
                learned["open_shift"], learned["close_shift"] = open_by, close_by
            if proposed == "closed" and final != "closed":
                learned["closed_asks"] = learned.get("closed_asks", 0) + 1
        if r["decision"] == "REJECTED" and r["owner_comment"] in ("Olemme auki normaalisti.", "We are open as usual.", "Vi har öppet som vanligt."):
            learned.setdefault("skip_days", []).append(key)
            if proposed == "closed":
                learned["closed_doubts"] = learned.get("closed_doubts", 0) + 1
    return learned


def pilot_test(engine, ids) -> dict:
    log = collections.defaultdict(list)
    for r in csv.DictReader((config.DATA_DIR / "data" / "pilot_decision_log_2025.csv").open(encoding="utf-8")):
        log[r["entity_id"]].append(r)
    MOCK.reset()
    service = Service(engine, Store(":memory:"), MOCK, public_url="http://test")
    groups = collections.defaultdict(list)
    for eid in ids:
        replied = [r for r in log.get(eid, []) if r["decision"] != "NO_RESPONSE"]
        if not replied:
            continue
        live = service.live_holidays(eid)
        base = {d.date: d.hours if d.action == "SUGGEST" else None for d in engine.decisions_for(eid, live)}
        after = {d.date: d.hours if d.action == "SUGGEST" else None for d in engine.decisions_for(eid, live, pilot_learned(replied))}
        rows = [(eid, row, base.get(day), after.get(day)) for (e, day), row in BY_BUSINESS[eid].items()]
        groups["all pilot owners who replied"] += rows
        kinds = {r["decision"] for r in replied}
        for label, kind in (("pilot owners who edited", "EDITED"), ("pilot owners who declined", "REJECTED")):
            if kind in kinds:
                groups[label] += rows
    return {name: summarise(rows) for name, rows in groups.items()}


BY_BUSINESS = collections.defaultdict(dict)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Only use this many businesses, for a quick check")
    parser.add_argument("--seed", type=int, default=0, help="Draw a different set of simulated owner answers")
    args = parser.parse_args()
    MOCK.seed = args.seed
    for key, row in LABELS.items():
        BY_BUSINESS[key[0]][key] = row
    ids = sorted(BY_BUSINESS)
    if args.limit:
        ids = random.Random(7).sample(ids, args.limit)
    engine = Engine()
    print(f"{len(ids)} dev businesses", flush=True)
    results = {"simulator": simulator_test(engine, ids), "pilot": pilot_test(engine, ids)}
    print("\n== 1. Owner simulator: dates after the first reply")
    for name, s in results["simulator"].items():
        show(name, s)
    print("\n== 2. Pilot replay: logged 2025 decisions into the 2026 season")
    for name, s in results["pilot"].items():
        show(name, s)
    (config.VAR_DIR / "learning_results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
