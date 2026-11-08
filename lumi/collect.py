#!/usr/bin/env python3
"""Leaderboard of the sweep, and the pick for the final run.

    python3 lumi/collect.py lumi/results              # table, and lumi/results/leaderboard.csv
    python3 lumi/collect.py lumi/results --best       # the winning config as one JSON line, named "final"

Ranked by the 2026 held-out score (the one that matches the hidden test). A setting is only picked if it beats every
baseline (each with a different seed, so their spread is the noise) and doesn't lose more than that spread on the
2025 seasons. Otherwise the pick is the baseline, and the published model stays as it is.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

SEASONS = ("2026", "2025", "strict_2025")


def load(folder: Path) -> list:
    runs = []
    for path in sorted(folder.glob("*.json")):
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "summary" in run and run["name"] != "final":
            runs.append(run)
    return runs


def score(run: dict, season: str) -> float:
    return float(run["summary"][season]["score_0_100"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--best", action="store_true")
    args = parser.parse_args()
    runs = load(args.folder)
    baselines = [r for r in runs if r["config"].get("mode") == "off"]
    if not baselines:
        sys.exit(f"No baseline result in {args.folder} yet")
    base = next((r for r in baselines if not r["config"].get("seed_shift")), baselines[0])
    noise = {s: max(score(r, s) for r in baselines) - min(score(r, s) for r in baselines) for s in SEASONS}
    ceiling = {s: max(score(r, s) for r in baselines) for s in SEASONS}

    def passes(run: dict) -> bool:
        return (score(run, "2026") > ceiling["2026"]
                and all(score(run, s) >= score(base, s) - noise[s] for s in ("2025", "strict_2025")))

    runs.sort(key=lambda r: -score(r, "2026"))
    winner = next((r for r in runs if r["config"].get("mode") != "off" and passes(r)), base)

    if args.best:
        print(json.dumps({**winner["config"], "name": "final", "seed_shift": 0}))
        return

    params = ["mode", "window_days", "ngram_min", "ngram_max", "min_count", "min_precision", "seed_shift"]
    header = ["name", *params, *(f"{s}" for s in SEASONS), *(f"d_{s}" for s in SEASONS), "n_closed", "n_early", "n_open", "minutes"]
    table = []
    for r in runs:
        kw = r.get("keywords") or {}
        table.append([r["name"], *(r["config"].get(p, "") for p in params),
                      *(round(score(r, s), 2) for s in SEASONS), *(round(score(r, s) - score(base, s), 2) for s in SEASONS),
                      len(kw.get("closed", [])), len(kw.get("early", [])), len(kw.get("open", [])), round(r.get("seconds", 0) / 60, 1)])
    with (args.folder / "leaderboard.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([header] + table)

    print(f"{len(runs)} runs. Baseline: 2026 {score(base, '2026'):.2f} | 2025 {score(base, '2025'):.2f} | strict {score(base, 'strict_2025'):.2f}")
    print("Noise (spread of baselines with different seeds): " + " | ".join(f"{s} {noise[s]:.2f}" for s in SEASONS))
    print(f"\n{'name':18s} {'mode':8s} {'win':>3s} {'ngr':>4s} {'min':>4s} {'prec':>5s} {'2026':>6s} {'d2026':>6s} {'d2025':>6s} {'dstrict':>7s} {'kw c/e/o':>9s}")
    for row in table[:30]:
        d = dict(zip(header, row))
        grams = f"{d['ngram_min']}-{d['ngram_max']}" if d["mode"] != "off" else ""
        print(f"{d['name']:18s} {str(d['mode']):8s} {str(d['window_days']):>3s} {grams:>4s} {str(d['min_count']):>4s} {str(d['min_precision']):>5s} "
              f"{d['2026']:6.2f} {d['d_2026']:+6.2f} {d['d_2025']:+6.2f} {d['d_strict_2025']:+7.2f} {d['n_closed']:>3}/{d['n_early']}/{d['n_open']}")
    if winner is base:
        print("\nPick: the baseline. No keyword setting beat it by more than the noise, so keep the current model.")
    else:
        print(f"\nPick: {winner['name']} ({score(winner, '2026') - score(base, '2026'):+.2f} on 2026). Run `lumi/lumi.sh final` to build it.")
    print(f"Full table: {args.folder / 'leaderboard.csv'}")


if __name__ == "__main__":
    main()
