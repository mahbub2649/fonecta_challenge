#!/usr/bin/env python3
"""Learn review keyword lists from dev answers: which phrases mean the business was closed, closed early or open.

    python model/keywords.py --config '{"mode": "union", "window_days": 21, ...}' --out var/keywords.json

A review is labelled by what was true on the special days in the `window_days` before it: closed although the
listing showed open, open but closing earlier than shown, or open. A phrase is kept if, in the reviews that contain
it, the lower bound of the share with that label is high enough (Wilson interval, 95%).

Honesty rules:
- Only reviews and answers dated before --before (default 6 Nov 2025) are used, so the strict 2025 back-test is
  still strict and the lists hold nothing from the season being scored.
- Each dev business gets a list learned without its own fold (the same folds as the model), and every other
  business gets the list learned from all dev businesses. No business is scored with a list learned from it.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connect import config  # noqa: E402
from model.folds import N_FOLDS, fold_map  # noqa: E402
from model.review_text import CLASSES, ngrams  # noqa: E402

DEFAULTS = {"mode": "union", "window_days": 21, "ngram_min": 1, "ngram_max": 3, "min_count": 10, "min_precision": 0.7,
            "min_lift": 1.5, "max_keywords": 60}


def wilson_lower(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = k / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / (1 + z * z / n)


def last_close(hours: str) -> int | None:
    """Closing time in minutes, past midnight above 1440."""
    if not hours or hours == "closed":
        return None
    start, end = hours.split(",")[0][:5], hours.split(",")[-1][6:11]
    a, b = int(start[:2]) * 60 + int(start[3:]), int(end[:2]) * 60 + int(end[3:])
    return b if b > a else b + 1440


def label(days: list) -> set:
    """Labels for one review from (truth, shown) on the special days just before it."""
    out = set()
    for truth, shown in days:
        if truth == "closed" and shown != "closed":
            out.add("closed")
        elif truth != "closed" and shown != "closed":
            t, s = last_close(truth), last_close(shown)
            if t is not None and s is not None and t < s:
                out.add("early")
        if truth != "closed":
            out.add("open")
    if out & {"closed", "early"}:
        out.discard("open")
    return out


def select(counts: dict, totals: dict, cfg: dict) -> dict:
    """counts[gram] = [n, k_closed, k_early, k_open]; totals = [n, k...]. Returns {class: [phrases]} and stats."""
    lists, stats = {}, {}
    n_all = max(1, totals[0])
    for c, cls in enumerate(CLASSES, start=1):
        base = totals[c] / n_all
        floor = max(cfg["min_precision"], base * cfg["min_lift"])
        passing = []
        for gram, row in counts.items():
            n, k = row[0], row[c]
            if n >= cfg["min_count"] and k and len(gram.split()) >= cfg["ngram_min"]:
                lb = wilson_lower(k, n)
                if lb >= floor:
                    passing.append((gram, n, k, lb))
        # Shortest phrases first: a longer phrase that contains a kept one adds nothing.
        passing.sort(key=lambda x: (len(x[0].split()), -x[3]))
        kept = []
        for gram, n, k, lb in passing:
            padded = f" {gram} "
            if not any(f" {other} " in padded for other, *_ in kept):
                kept.append((gram, n, k, lb))
        kept.sort(key=lambda x: -x[3])
        kept = kept[:cfg["max_keywords"]]
        lists[cls] = [g for g, *_ in kept]
        stats[cls] = {"base_rate": round(base, 4), "floor": round(floor, 4),
                      "top": [[g, n, k, round(lb, 3)] for g, n, k, lb in kept[:15]]}
    return {"lists": lists, "stats": stats}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="{}", help="JSON object; missing keys use the defaults")
    parser.add_argument("--out", required=True)
    parser.add_argument("--before", default="2025-11-06")
    args = parser.parse_args()
    cfg = {**DEFAULTS, **json.loads(args.config)}
    if cfg["mode"] not in ("union", "replace"):
        sys.exit("mode must be union or replace (off means: don't run this script)")
    start = time.time()
    root = config.DATA_DIR
    with (root / "data" / "splits.csv").open(encoding="utf-8") as f:
        dev = {r["entity_id"] for r in csv.DictReader(f) if r["split"] == "dev"}
    folds = fold_map(sorted(dev))

    truth = defaultdict(dict)
    with (root / "labels" / "dev_truth_history.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["entity_id"] in dev and r["date"] < args.before:
                truth[r["entity_id"]][r["date"]] = (r["truth_hours"], r["displayed_hours_that_day"])

    reviews = json.loads((root / "data" / "reviews.json").read_text(encoding="utf-8"))["response"]["reviews"]
    # Per fold: gram -> [n, k_closed, k_early, k_open], and the totals.
    counts = [defaultdict(lambda: [0, 0, 0, 0]) for _ in range(N_FOLDS)]
    totals = [[0, 0, 0, 0] for _ in range(N_FOLDS)]
    used = 0
    for r in reviews:
        eid, text = r["locationId"], r.get("content") or ""
        if eid not in folds or not text:
            continue
        when = datetime.fromtimestamp(r["publisherDate"] / 1000).date()
        if when.isoformat() >= args.before:
            continue
        days = truth.get(eid, {})
        window = [days[d] for d in ((when - timedelta(days=k)).isoformat() for k in range(cfg["window_days"] + 1)) if d in days]
        labels = label(window)
        flags = [1] + [int(c in labels) for c in CLASSES]
        fold = folds[eid]
        for i, v in enumerate(flags):
            totals[fold][i] += v
        for gram in ngrams(text, cfg["ngram_max"]):
            row = counts[fold][gram]
            for i, v in enumerate(flags):
                row[i] += v
        used += 1

    def merged(skip: int | None) -> tuple:
        out, tot = defaultdict(lambda: [0, 0, 0, 0]), [0, 0, 0, 0]
        for f in range(N_FOLDS):
            if f == skip:
                continue
            for i in range(4):
                tot[i] += totals[f][i]
            for gram, row in counts[f].items():
                acc = out[gram]
                for i in range(4):
                    acc[i] += row[i]
        return out, tot

    lists, stats = {}, {}
    for name, skip in [("all", None)] + [(str(f), f) for f in range(N_FOLDS)]:
        result = select(*merged(skip), cfg)
        lists[name], stats[name] = result["lists"], result["stats"]
    payload = {"version": 1, "config": cfg, "before": args.before, "reviews_used": used, "classes": list(CLASSES),
               "fold_of": folds, "lists": lists, "stats": stats["all"]}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    sizes = {c: len(lists["all"][c]) for c in CLASSES}
    print(f"learned from {used} reviews in {time.time() - start:.0f}s: {sizes} -> {out}", flush=True)
    for c in CLASSES:
        print(f"  {c}: " + " | ".join(g for g, *_ in stats["all"][c]["top"][:8]), flush=True)


if __name__ == "__main__":
    main()
