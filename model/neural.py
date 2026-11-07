#!/usr/bin/env python3
"""Neural models for the open-or-closed decision: RealMLP, TabM, TabICLv2 (a transformer foundation model).

Saves held-out class probabilities for dev rows, and fold-averaged ones for test and demo rows, in var/model/nn_<name>.npz.

    python model/neural.py realmlp [--folds 0] [--soft soft.parquet]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from model.train import CACHE, CATEGORICAL, EXTRA, load, row_columns  # noqa: E402


TABICL_VIEWS = 4


def prepare(rows: pd.DataFrame) -> tuple:
    cols = row_columns(rows)
    numeric = [c for c in cols if c not in CATEGORICAL]
    x = rows[cols].copy()
    for col in numeric:
        x[col] = pd.to_numeric(x[col], errors="coerce").astype("float32")
    # Missing values are meaningful here, so keep a flag where a useful share is missing.
    medians = x[numeric].median()
    flags = {}
    for col in numeric:
        share = x[col].isna().mean()
        if 0.02 < share < 0.98:
            flags[col + "_na"] = x[col].isna().astype("float32")
    x[numeric] = x[numeric].fillna(medians).fillna(0.0)
    x = pd.concat([x, pd.DataFrame(flags, index=x.index)], axis=1)
    keep = [c for c in x.columns if c in CATEGORICAL or x[c].nunique() > 1]
    return x[keep], [c for c in CATEGORICAL if c in keep]


def make_model(name: str, seed: int):
    if name == "realmlp":
        from pytabkit import RealMLP_TD_Classifier
        return RealMLP_TD_Classifier(device="cuda", random_state=seed, n_cv=1, n_refit=0, val_metric_name="cross_entropy", verbosity=0)
    if name == "tabm":
        from pytabkit import TabM_D_Classifier
        return TabM_D_Classifier(device="cuda", random_state=seed, n_cv=1, n_refit=0, val_metric_name="cross_entropy", verbosity=0)
    if name == "tabicl":
        from tabicl import TabICLClassifier
        return TabICLClassifier(device="cuda", random_state=seed, n_estimators=TABICL_VIEWS, batch_size=1, verbose=False)
    raise ValueError(name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--folds", default="0,1,2,3,4")
    parser.add_argument("--soft", default="soft.parquet")
    parser.add_argument("--max-train", type=int, default=0, help="Use a random sample of training rows")
    parser.add_argument("--tag", default="")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--strict", action="store_true", help="Train on the 2024 season only, predict 2025: the strict back-test")
    parser.add_argument("--all-days", action="store_true", help="Also train on past special days outside the scored window")
    args = parser.parse_args()
    start = time.time()
    rows, _ = load(args.soft)
    x, cats = prepare(rows)
    labelled_mask = ((rows["cls"] >= 0) & (rows["aux"] == 0)).to_numpy()
    target_mask = ((rows["season"] == 2026) & (rows["cls"] < 0)).to_numpy()
    y = rows["cls"].to_numpy()
    fold = rows["fold"].to_numpy()
    probs = np.full((len(rows), 3), np.nan)
    target_sum = np.zeros((len(rows), 3))
    folds = [int(f) for f in args.folds.split(",")]
    print(f"{args.name}: {x.shape[1]} columns, {int(labelled_mask.sum())} labelled rows, folds {folds}", flush=True)
    rng = np.random.RandomState(args.seed)
    if args.strict:
        season = rows["season"].to_numpy()
        labelled_mask = labelled_mask & np.isin(season, [2024, 2025])
    extra_mask = ((rows["cls"] >= 0) & (rows["aux"] == EXTRA)).to_numpy() if args.all_days else np.zeros(len(rows), bool)
    if args.strict:  # Only what was knowable at the 2025 snapshot.
        extra_mask &= ((rows["season"] == 2024) & (rows["date"] < "2025-11-06")).to_numpy()
    for k in folds:
        train = np.where((extra_mask | (labelled_mask & ((rows["season"].to_numpy() == 2024) if args.strict else True))) & (fold != k))[0]
        if args.max_train and len(train) > args.max_train:
            train = rng.choice(train, args.max_train, replace=False)
        model = make_model(args.name, args.seed)
        t = time.time()
        if args.name == "tabicl":
            encoded = x.copy()
            for col in cats:
                encoded[col] = encoded[col].cat.codes.astype("float32")
            model.fit(encoded.iloc[train], y[train])
            test = np.where(labelled_mask & (fold == k) & ((rows["season"].to_numpy() == 2025) if args.strict else True))[0]
            batches = [model.predict_proba(encoded.iloc[test[i:i + 2000]]) for i in range(0, len(test), 2000)]
            probs[test] = np.vstack(batches)
            if len(folds) == 5 and not args.strict:
                tgt = np.where(target_mask)[0]
                target_sum[tgt] += np.vstack([model.predict_proba(encoded.iloc[tgt[i:i + 2000]]) for i in range(0, len(tgt), 2000)]) / 5
        else:
            model.fit(x.iloc[train], y[train], cat_col_names=cats)
            test = np.where(labelled_mask & (fold == k) & ((rows["season"].to_numpy() == 2025) if args.strict else True))[0]
            probs[test] = model.predict_proba(x.iloc[test])
            if len(folds) == 5 and not args.strict:
                tgt = np.where(target_mask)[0]
                target_sum[tgt] += model.predict_proba(x.iloc[tgt]) / 5
        m = probs[test]
        ll = -np.mean(np.log(np.clip(m[np.arange(len(test)), y[test]], 1e-6, 1)))
        print(f"  fold {k}: log-loss {ll:.4f}, accuracy {(m.argmax(1) == y[test]).mean():.4f}, {time.time() - t:.0f}s", flush=True)
    name = f"nn_{args.name}{args.tag}.npz"
    np.savez(CACHE / name, row_id=rows["row_id"].to_numpy(), probs=probs, target=target_sum)
    print(f"saved {name} at {time.time() - start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
