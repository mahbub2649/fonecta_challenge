#!/usr/bin/env python3
"""Write the sweep's configs, one JSON object per line.

    python3 lumi/grid.py --size small > lumi/grid.jsonl

Every grid starts with three baselines (no keywords, different seeds). How far apart they land is the noise:
a keyword setting is only better if it beats the baselines by more than that.
"""
from __future__ import annotations

import argparse
import itertools
import json

GRIDS = {
    "smoke": {},
    "small": {"mode": ["union", "replace"], "window_days": [14, 21], "ngram_min": [1, 2], "ngram_max": [3],
              "min_count": [10], "min_precision": [0.6, 0.8]},
    "full": {"mode": ["union", "replace"], "window_days": [7, 14, 21], "ngram_min": [1, 2], "ngram_max": [3, 4],
             "min_count": [5, 10, 20], "min_precision": [0.5, 0.65, 0.8]},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", choices=sorted(GRIDS), default="small")
    args = parser.parse_args()
    lines = [{"name": "baseline", "mode": "off"}]
    if args.size != "smoke":
        lines += [{"name": f"baseline-seed{s}", "mode": "off", "seed_shift": s} for s in (100, 200)]
    grid = GRIDS[args.size]
    for n, values in enumerate(itertools.product(*grid.values()) if grid else []):
        lines.append({"name": f"kw-{n:03d}", **dict(zip(grid, values))})
    for line in lines:
        print(json.dumps(line))


if __name__ == "__main__":
    main()
