#!/usr/bin/env python3
"""Build the feature tables once, so experiments are quick. Writes to var/model/ (git-ignored).

Answers are joined here only as a separate column for dev rows. Features are computed before any answer is read.
"""
from __future__ import annotations

import csv
import os
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connect import config  # noqa: E402
from model.features import Data, PopulationModes, build_row, candidate_features  # noqa: E402

OUT = config.VAR_DIR / "model"
SNAPSHOTS = {2024: date(2024, 11, 6), 2025: date(2025, 11, 6), 2026: date(2026, 11, 6)}


def season_of(d: date) -> int | None:
    """Rows from 7 Nov to 6 Jan belong to the season that starts that November."""
    if (d.month == 11 and d.day >= 7) or d.month == 12:
        return d.year
    if d.month == 1 and d.day <= 6:
        return d.year - 1
    return None


def read_csv(path: Path) -> list:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    start = time.time()
    root = config.DATA_DIR
    data = Data(root)
    print(f"loaded data in {time.time() - start:.0f}s", flush=True)
    splits = {r["entity_id"]: r["split"] for r in read_csv(root / "data" / "splits.csv")}
    dev = {e for e, s in splits.items() if s == "dev"}

    # Which rows we need: every 2026 target, plus dev rows from the two earlier seasons (answers come from the history).
    wanted = {}
    for r in read_csv(root / "evaluation" / "targets_2026.csv"):
        wanted[(r["entity_id"], r["date"])] = (r["day_key"], r["event_id"], 2026, r["split"])
    truth = {}
    for r in read_csv(root / "labels" / "dev_truth_history.csv"):
        d = date.fromisoformat(r["date"])
        season = season_of(d)
        if season in (2024, 2025) and r["entity_id"] in dev:
            wanted[(r["entity_id"], r["date"])] = (r["day_key"], r["event_id"], season, "dev")
            truth[(r["entity_id"], r["date"])] = r["truth_hours"]
    for r in read_csv(root / "evaluation" / "targets_2025_backtest.csv"):
        wanted.setdefault((r["entity_id"], r["date"]), (r["day_key"], r["event_id"], 2025, "dev"))
    for name in ("dev_labels_2025_backtest.csv", "dev_labels_2026.csv"):
        for r in read_csv(root / "labels" / name):
            truth[(r["entity_id"], r["date"])] = r["truth_hours"]
    # Test businesses' own past entries are inputs, not answers. They teach the hours picker what special hours look like.
    aux = set()
    for eid, entries in data.hol.items():
        ent = data.ents.get(eid)
        if eid in dev or not ent or ent.get("c_segment") == "shopping_centre":
            continue
        latest = {}
        for r in entries:
            latest[r["date"]] = r
        for r in latest.values():
            if season_of(date.fromisoformat(r["date"])) == 2025 and r["hours"] not in ("closed", "REGULAR") and (eid, r["date"]) not in wanted:
                wanted[(eid, r["date"])] = (r["key"], "", 2025, "aux")
                truth[(eid, r["date"])] = r["hours"]
                aux.add((eid, r["date"]))
    # Late entries on non-dev businesses: entered after a season's snapshot but before the day. At the snapshot the
    # listing still showed what it showed, so each one is an honest example of a day whose truth was hidden then.
    # They train the open/closed model, not just the hours picker. MODEL_LATE_ROWS=0 turns them off.
    late_rows = os.environ.get("MODEL_LATE_ROWS", "1") == "1"
    late = 0
    if late_rows:
        for eid, entries in data.hol.items():
            ent = data.ents.get(eid)
            if eid in dev or not ent or ent.get("c_segment") == "shopping_centre":
                continue
            latest = {}
            for r in entries:
                latest[r["date"]] = r
            for r in latest.values():
                season = season_of(date.fromisoformat(r["date"]))
                if season not in (2024, 2025) or r["hours"] == "REGULAR" or (eid, r["date"]) in wanted:
                    continue
                if SNAPSHOTS[season].isoformat() <= r["at"][:10] < r["date"]:
                    wanted[(eid, r["date"])] = (r["key"], "", season, "aux_late")
                    truth[(eid, r["date"])] = r["hours"]
                    late += 1
    print(f"{len(wanted)} rows to build, {len(aux)} from entries on non-dev businesses, {late} late entries", flush=True)

    modes = {s: PopulationModes(data, snap) for s, snap in SNAPSHOTS.items()}
    print(f"population modes done at {time.time() - start:.0f}s", flush=True)
    rows, cands = [], []
    for n, ((eid, d_text), (key, event_id, season, split)) in enumerate(sorted(wanted.items())):
        if eid not in data.ents:
            continue
        d = date.fromisoformat(d_text)
        row, candidates, _ = build_row(data, modes[season], eid, d, key, event_id, SNAPSHOTS[season])
        row.update(season=season, split=split, row_id=n, truth=truth.get((eid, d_text)))
        if late_rows:
            row["late_row"] = int(split == "aux_late")  # Lets the model allow for owners who enter only changes.
        for cand, sources in candidates.items():
            cands.append({"row_id": n, **candidate_features(cand, sources, row)})
        row.pop("_shares", None)
        rows.append(row)
        if n % 20000 == 0:
            print(f"  {n} rows, {time.time() - start:.0f}s", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(OUT / "rows.parquet")
    pd.DataFrame(cands).to_parquet(OUT / "candidates.parquet")
    print(f"wrote {len(rows)} rows, {len(cands)} candidates to {OUT} in {time.time() - start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
