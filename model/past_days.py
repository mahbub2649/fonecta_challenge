#!/usr/bin/env python3
"""First stage: estimate what each business really did on past special days it never entered.

Input is traces only: phone spikes, complaints naming the day, user edits. Dev answers train it, and each dev business
is estimated by models that never saw it. Output is one table of habit features per target row: var/model/soft.parquet.

    python model/past_days.py [--before YYYY-MM-DD]

--before limits the first stage's training to days before that date, for the strict back-test.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connect import config  # noqa: E402
from sklearn.metrics import log_loss, roc_auc_score  # noqa: E402

from model.features import RELATED_KEYS, Data, past_day_rows, previous_dates  # noqa: E402

CACHE = config.VAR_DIR / "model"
SNAPSHOTS = {2024: date(2024, 11, 6), 2025: date(2025, 11, 6), 2026: date(2026, 11, 6)}
CATEGORICAL = ["day_key", "day_class", "day_type", "segment", "country", "tier"]
NOT_FEATURES = {"entity_id", "date", "regular", "has_entry", "entry_hours", "entry_in_time", "truth", "cls", "fold", "season"}
PARAMS = dict(objective="multiclass", num_class=3, n_estimators=300, learning_rate=0.04, num_leaves=31, min_child_samples=30, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.6, reg_lambda=5.0, n_jobs=10, verbose=-1, random_state=3)
N_FOLDS = 5


def fold_map(dev_ids: list) -> dict:
    """Fixed folds by business, shared with the second stage."""
    path = CACHE / "folds.json"
    if path.exists():
        return json.loads(path.read_text())
    order = np.random.RandomState(11).permutation(sorted(dev_ids))
    folds = {str(eid): int(i % N_FOLDS) for i, eid in enumerate(order)}
    path.write_text(json.dumps(folds))
    return folds


def build_tables(data: Data, dev: set) -> pd.DataFrame:
    tables = []
    for season, snap in SNAPSHOTS.items():
        ids = [e for e in data.ents if data.ents[e].get("c_segment") != "shopping_centre" and (season >= 2025 or e in dev)]
        rows = []
        for eid in ids:
            rows.extend(past_day_rows(data, eid, snap))
        table = pd.DataFrame(rows)
        table["season"] = season
        tables.append(table)
    return pd.concat(tables, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", default=None)
    parser.add_argument("--passes", type=int, default=0, help="Extra passes that read the business's other days. Tested: they make it worse")
    args = parser.parse_args()
    start = time.time()
    root = config.DATA_DIR
    data = Data(root)
    with (root / "data" / "splits.csv").open(encoding="utf-8") as f:
        splits = {r["entity_id"]: r["split"] for r in csv.DictReader(f)}
    dev = {e for e, s in splits.items() if s == "dev"}
    folds = fold_map(sorted(dev))
    past = build_tables(data, dev)
    print(f"{len(past)} past-day rows at {time.time() - start:.0f}s", flush=True)

    with (root / "labels" / "dev_truth_history.csv").open(encoding="utf-8") as f:
        truth = {(r["entity_id"], r["date"]): r["truth_hours"] for r in csv.DictReader(f)}
    past["truth"] = [truth.get(k) for k in zip(past["entity_id"], past["date"])]
    past["fold"] = past["entity_id"].map(folds).fillna(-1).astype(int)
    known = past["truth"].notna()
    past["cls"] = -1
    past.loc[known & (past["truth"] == "closed"), "cls"] = 0
    past.loc[known & (past["truth"] != "closed") & (past["truth"] == past["regular"]), "cls"] = 1
    past.loc[known & (past["truth"] != "closed") & (past["truth"] != past["regular"]), "cls"] = 2
    for col in CATEGORICAL:
        past[col] = pd.Categorical(past[col], categories=sorted(past[col].unique()))
    features = [c for c in past.columns if c not in NOT_FEATURES]

    # Train on the fullest view: the latest snapshot, days with no entry. These are the days whose truth is hidden.
    train_mask = (past["season"] == 2026) & (past["cls"] >= 0) & (past["has_entry"] == 0)
    if args.before:
        train_mask &= past["date"] < args.before
    print(f"first-stage training rows: {int(train_mask.sum())}, classes {past.loc[train_mask, 'cls'].value_counts().to_dict()}", flush=True)

    def fit_pass(columns: list) -> np.ndarray:
        probs = np.zeros((len(past), 3))
        fold = past["fold"].to_numpy()
        for k in range(N_FOLDS):
            tr = past[train_mask & (past["fold"] != k)]
            model = lgb.LGBMClassifier(**PARAMS)
            model.fit(tr[columns], tr["cls"], categorical_feature=CATEGORICAL)
            pred = model.predict_proba(past[columns])
            probs[fold == k] = pred[fold == k]
            probs[fold == -1] += pred[fold == -1] / N_FOLDS
        return probs

    def report(probs: np.ndarray, name: str) -> None:
        mask = train_mask.to_numpy() if not args.before else ((past["season"] == 2026) & (past["cls"] >= 0) & (past["has_entry"] == 0)).to_numpy()
        check = past["cls"].to_numpy()[mask]
        hidden_open = (past["regular_closed"].to_numpy() == 0)[mask]
        guess = probs[mask].argmax(1)
        print(f"{name}: held-out accuracy on hidden past days {(guess == check).mean():.4f}, where regular hours are open {(guess == check)[hidden_open].mean():.4f}", flush=True)
        y, q = check[hidden_open], probs[mask][hidden_open]
        keep = y != 0
        print(f"  open days: closed AUC {roc_auc_score(y == 0, q[:, 0]):.4f} | other-vs-same AUC {roc_auc_score(y[keep] == 2, q[keep, 2] / (q[keep, 1] + q[keep, 2])):.4f} | log-loss {log_loss(y, q, labels=[0, 1, 2]):.4f}", flush=True)
        print("  confusion (true rows, guessed columns) closed/same/other:", pd.crosstab(y, q.argmax(1)).to_numpy().tolist(), flush=True)

    probs = fit_pass(features)
    report(probs, "pass 1")

    # Second pass: each day also sees this business's estimated behaviour on its other days.
    for pass_number in range(args.passes):
        soft_closed = probs[:, 0].copy()
        soft_other = probs[:, 2].copy()
        entered = (past["has_entry"] == 1).to_numpy()
        hours = past["entry_hours"].to_numpy()
        soft_closed[entered] = (hours[entered] == "closed").astype(float)
        soft_other[entered] = (~np.isin(hours[entered], ["closed", "REGULAR"])).astype(float)
        past["_c"], past["_o"] = soft_closed, soft_other
        for group, cols in (("ent", ["season", "entity_id"]), ("key", ["season", "entity_id", "day_key"]), ("cls", ["season", "entity_id", "day_class"])):
            g = past.groupby(cols, observed=True)
            for short in ("_c", "_o"):
                total, count = g[short].transform("sum"), g[short].transform("count")
                past[f"loo_{group}{short}"] = (total - past[short]) / (count - 1).replace(0, np.nan)
        columns = features + [c for c in past.columns if c.startswith("loo_")]
        probs = fit_pass(columns)
        report(probs, f"pass {pass_number + 2}")
    past["p_closed"], past["p_same"], past["p_other"] = probs[:, 0], probs[:, 1], probs[:, 2]

    # Replace estimates with the record where an entry exists.
    entered = past["has_entry"] == 1
    closed = entered & (past["entry_hours"] == "closed")
    special = entered & ~past["entry_hours"].isin(["closed", "REGULAR"])
    past["soft_closed"] = past["p_closed"]
    past["soft_other"] = past["p_other"]
    past.loc[entered, ["soft_closed", "soft_other"]] = 0.0
    past.loc[closed, "soft_closed"] = 1.0
    past.loc[special, "soft_other"] = 1.0
    past.to_parquet(CACHE / ("past_strict.parquet" if args.before else "past.parquet"))  # The history transformer reads this.

    rows = pd.read_parquet(CACHE / "rows.parquet", columns=["row_id", "entity_id", "date", "day_key", "season", "day_class", "day_type", "country"])
    out = []
    groups = {key: g for key, g in past.groupby(["season", "entity_id"], observed=True)}
    for (season, eid), targets in rows.groupby(["season", "entity_id"]):
        g = groups.get((season, eid))
        if g is None:
            continue
        lookup = dict(zip(g["date"], zip(g["soft_closed"], g["soft_other"], g["calls_ratio"])))
        hidden = g[g["has_entry"] == 0]
        all_closed, all_other = g["soft_closed"].mean(), g["soft_other"].mean()
        hidden_closed = hidden["p_closed"].mean() if len(hidden) else np.nan
        hidden_other = hidden["p_other"].mean() if len(hidden) else np.nan
        calls = hidden["calls_ratio"].mean() if len(hidden) else np.nan
        by_class = g.groupby("day_class", observed=True)[["soft_closed", "soft_other"]].mean()
        by_type = g.groupby("day_type", observed=True)[["soft_closed", "soft_other"]].mean()
        by_key = g.groupby("day_key", observed=True)[["soft_closed", "soft_other"]].mean()
        last_by_key = g.sort_values("date").groupby("day_key", observed=True)["soft_closed"].last()
        related = {f"soft_key_{k}": last_by_key.get(k, np.nan) for k in RELATED_KEYS}
        for t in targets.itertuples(index=False):
            d = date.fromisoformat(t.date)
            rec = {"row_id": t.row_id, "soft_all_closed": all_closed, "soft_all_other": all_other, "soft_hidden_closed": hidden_closed,
                   "soft_hidden_other": hidden_other, "soft_calls_lift": calls, **related}
            for years in (1, 2):
                prev = previous_dates(data, t.country, t.day_key, d, years)
                value = lookup.get(prev[0].isoformat()) if prev else None
                rec[f"soft_y{years}_closed"] = value[0] if value else np.nan
                rec[f"soft_y{years}_other"] = value[1] if value else np.nan
            rec["soft_key_closed"] = by_key["soft_closed"].get(t.day_key, np.nan)
            rec["soft_key_other"] = by_key["soft_other"].get(t.day_key, np.nan)
            rec["soft_class_closed"] = by_class["soft_closed"].get(t.day_class, np.nan)
            rec["soft_class_other"] = by_class["soft_other"].get(t.day_class, np.nan)
            rec["soft_type_closed"] = by_type["soft_closed"].get(t.day_type, np.nan)
            rec["soft_type_other"] = by_type["soft_other"].get(t.day_type, np.nan)
            out.append(rec)
    name = "soft_strict.parquet" if args.before else "soft.parquet"
    pd.DataFrame(out).to_parquet(CACHE / name)
    print(f"wrote {len(out)} rows to {name} at {time.time() - start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
