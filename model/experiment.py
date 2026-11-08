#!/usr/bin/env python3
"""One experiment, end to end: learn keywords, rebuild features, run both model stages, score with evaluate.py.

    python model/experiment.py --config '{"name": "kw-001", "mode": "union", ...}' --run-dir runs/kw-001 \
        --out results/kw-001.json [--write]

Each run keeps its own var/ folder, so many can run side by side. mode "off" is the baseline: no keywords.
--write also writes predictions_2026.csv and connect/model_decisions.json, and puts the keyword list in
model/keywords.json, so later rebuilds use it too.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRICT_BEFORE = "2025-11-06"  # The strict back-test's snapshot. Keywords only learn from before it.


def run(cmd: list, env: dict) -> None:
    print("+", " ".join(cmd[1:]), flush=True)
    subprocess.run(cmd, env=env, cwd=ROOT, check=True)


def summary(scores: dict) -> dict:
    keys = ("score_0_100", "precision_exact", "recall_exact", "harmful_suggestions", "search_views_protected_pct")
    return {season: {k: s.get(k) for k in keys} for season, s in scores.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="JSON object, or a path to one")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    text = Path(args.config).read_text() if Path(args.config).is_file() else args.config
    cfg = json.loads(text)
    mode = cfg.get("mode", "off")
    start = time.time()

    run_dir = Path(args.run_dir).resolve()
    var = run_dir / "var"
    var.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CONNECT_VAR_DIR": str(var), "PYTHONDONTWRITEBYTECODE": "1"}
    env["MODEL_SEED_SHIFT"] = str(cfg.get("seed_shift", 0))
    py = sys.executable
    keywords = run_dir / "keywords.json"
    if mode == "off":
        env["CONNECT_KEYWORDS"] = "off"
    else:
        learner = {k: v for k, v in cfg.items() if k not in ("name", "seed_shift")}
        run([py, "model/keywords.py", "--config", json.dumps(learner), "--out", str(keywords), "--before", STRICT_BEFORE], env)
        env["CONNECT_KEYWORDS"] = str(keywords)
    run([py, "model/build_dataset.py"], env)
    run([py, "model/past_days.py", "--before", STRICT_BEFORE], env)
    run([py, "model/past_days.py"], env)
    scores_path = var / "scores.json"
    run([py, "model/train.py", "--strict", "--results", str(scores_path)] + (["--write"] if args.write else []), env)

    scores = json.loads(scores_path.read_text())
    result = {"name": cfg.get("name", run_dir.name), "config": cfg, "summary": summary(scores), "scores": scores,
              "seconds": round(time.time() - start)}
    if keywords.exists():
        learned = json.loads(keywords.read_text(encoding="utf-8"))
        result["keywords"] = learned["lists"]["all"]
        result["config"] = {**learned["config"], **cfg}  # Show the defaults the learner filled in.
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.write:
        target = ROOT / "model" / "keywords.json"
        if keywords.exists():
            shutil.copy(keywords, target)
        elif target.exists():
            target.unlink()  # The baseline won, so later rebuilds shouldn't pick up an old list.
    s = result["summary"]
    print(f"{result['name']}: 2026 {s['2026']['score_0_100']:.2f} | 2025 {s['2025']['score_0_100']:.2f} | "
          f"strict 2025 {s['strict_2025']['score_0_100']:.2f} | {result['seconds']}s", flush=True)


if __name__ == "__main__":
    main()
