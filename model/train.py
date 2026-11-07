#!/usr/bin/env python3
"""Train and score the suggestion model, then write predictions_2026.csv.

    python model/build_dataset.py        # once
    python model/train.py                # scoreboard only
    python model/train.py --write        # also write predictions_2026.csv and connect/model_decisions.json

Scores come from the organisers' evaluate.py:
- "2026 held-out": each dev business is predicted by models that never saw it. This matches the hidden test
  (new businesses, same season), so it's the number to trust.
- "2025 strict": trained only on what was knowable before 6 Nov 2025, on other businesses.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connect import config  # noqa: E402

CACHE = config.VAR_DIR / "model"
LABELS_2026 = config.DATA_DIR / "labels" / "dev_labels_2026.csv"
LABELS_2025 = config.DATA_DIR / "labels" / "dev_labels_2025_backtest.csv"
CATEGORICAL = ["day_key", "segment", "country", "tier", "archetype", "day_class", "day_type"]
ID_COLUMNS = {"entity_id", "date", "shown", "season", "split", "row_id", "truth", "cls", "fold", "listing_closed", "aux"}
ROW_PARAMS = dict(objective="multiclass", num_class=3, n_estimators=450, learning_rate=0.03, num_leaves=15, min_child_samples=25,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.3, reg_lambda=5.0, n_jobs=10, verbose=-1, random_state=7)
CAND_PARAMS = dict(objective="binary", n_estimators=350, learning_rate=0.04, num_leaves=31, min_child_samples=20,
                   subsample=0.8, subsample_freq=1, colsample_bytree=0.6, reg_lambda=5.0, n_jobs=10, verbose=-1, random_state=7)
CLOSED, SAME, OTHER = 0, 1, 2
MIN_EXACT = 0.25  # The least chance of exactly right hours that justifies messaging an owner.
AUX, EXTRA = 1, 2  # Values of "aux": test businesses' own entries, and dev businesses' other special days. Neither is ever scored.


def load_scorer():
    spec = importlib.util.spec_from_file_location("evaluate", config.DATA_DIR / "evaluation" / "evaluate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCORER = load_scorer()


def near(a: str, b: str) -> bool:
    return SCORER.near(a, b)


def load(soft: str | None = "soft.parquet") -> tuple:
    rows = pd.read_parquet(CACHE / "rows.parquet")
    cands = pd.read_parquet(CACHE / "candidates.parquet")
    if soft and (CACHE / soft).exists():
        rows = rows.merge(pd.read_parquet(CACHE / soft), on="row_id", how="left")
    rows["fold"] = rows["entity_id"].map(json.loads((CACHE / "folds.json").read_text())).fillna(-1).astype(int)
    rows["aux"] = (rows["split"] == "aux").astype(int) * AUX + (rows["split"] == "extra").astype(int) * EXTRA
    regular = rows["truth"] == "REGULAR"  # An entry saying "regular hours" means the truth is what's listed.
    rows.loc[regular, "truth"] = rows.loc[regular, "shown"]
    rows["cls"] = -1
    known = rows["truth"].notna()
    rows.loc[known & (rows["truth"] == "closed"), "cls"] = CLOSED
    rows.loc[known & (rows["truth"] != "closed") & (rows["truth"] == rows["shown"]), "cls"] = SAME
    rows.loc[known & (rows["truth"] != "closed") & (rows["truth"] != rows["shown"]), "cls"] = OTHER
    for col in CATEGORICAL:
        rows[col] = pd.Categorical(rows[col], categories=sorted(rows[col].dropna().unique()))
    extra = ["weekday", "peer_special", "peer_regular", "reg_len", "special_share", "n_entries_special", "in_mall", "y1_state"]
    extra += [c for c in ("soft_y1_other", "soft_key_other", "soft_all_other") if c in rows.columns]
    cands = cands.merge(rows[["row_id", "truth", "cls", "entity_id", "season", "fold", "aux"] + CATEGORICAL + extra], on="row_id", how="left")
    known_truth = cands["truth"].notna() & (cands["truth"] != "closed")
    cands["exact"] = 0
    cands.loc[known_truth, "exact"] = (cands.loc[known_truth, "cand"] == cands.loc[known_truth, "truth"]).astype(int)
    cands["near"] = 0
    pairs = cands.loc[known_truth, ["cand", "truth"]].drop_duplicates()
    is_near = {(a, b) for a, b in zip(pairs["cand"], pairs["truth"]) if near(a, b)}
    cands.loc[known_truth, "near"] = [int((a, b) in is_near) for a, b in zip(cands.loc[known_truth, "cand"], cands.loc[known_truth, "truth"])]
    return rows, cands


def row_columns(rows: pd.DataFrame) -> list:
    return [c for c in rows.columns if c not in ID_COLUMNS]


def cand_columns(cands: pd.DataFrame) -> list:
    return [c for c in cands.columns if c not in {"row_id", "cand", "truth", "cls", "entity_id", "season", "exact", "near", "fold", "aux"}]


def fit_predict(rows_train, rows_pred, cands_train, cands_pred, seeds=(7,), min_season=2025) -> tuple:
    """Return (row probabilities, candidate P(exact), candidate P(near or exact)) for the prediction sets."""
    r_cols, c_cols = row_columns(rows_train), cand_columns(cands_train)
    probs = np.zeros((len(rows_pred), 3))
    p_exact = np.zeros(len(cands_pred))
    p_near = np.zeros(len(cands_pred))
    # The hours picker learns on rows where the truth is open and differs from what's shown, as that's when it pays.
    # The 2024 season has too little history behind it, so it would teach the wrong lesson.
    other = cands_train[(cands_train["cls"] == OTHER) & (cands_train["season"] >= min_season)]
    for seed in seeds:
        model = lgb.LGBMClassifier(**{**ROW_PARAMS, "random_state": seed})
        model.fit(rows_train[r_cols], rows_train["cls"], categorical_feature=CATEGORICAL)
        probs += model.predict_proba(rows_pred[r_cols]) / len(seeds)
        if len(cands_pred):
            exact = lgb.LGBMClassifier(**{**CAND_PARAMS, "random_state": seed})
            exact.fit(other[c_cols], other["exact"], categorical_feature=CATEGORICAL)
            p_exact += exact.predict_proba(cands_pred[c_cols])[:, 1] / len(seeds)
            close = lgb.LGBMClassifier(**{**CAND_PARAMS, "random_state": seed + 1})
            close.fit(other[c_cols], other["near"], categorical_feature=CATEGORICAL)
            p_near += close.predict_proba(cands_pred[c_cols])[:, 1] / len(seeds)
    return probs, p_exact, p_near


def choose(rows: pd.DataFrame, probs: np.ndarray, cands: pd.DataFrame, p_exact, p_near, knobs: dict) -> list:
    """Pick the action with the highest expected points, using the scorer's own values."""
    cands = cands.assign(p_exact=p_exact, p_near=np.maximum(p_near, p_exact))
    if knobs.get("normalise", True):
        # At most one candidate can be exactly right, so the row's chances can't sum above 1.
        total = cands.groupby("row_id")["p_exact"].transform("sum").clip(lower=1.0)
        cands["p_near"] = (cands["p_near"] - cands["p_exact"]).clip(lower=0) + cands["p_exact"] / total
        cands["p_exact"] = cands["p_exact"] / total
    cands["value"] = cands["p_exact"] + 0.6 * (cands["p_near"] - cands["p_exact"]) + 0.2 * (1 - cands["p_near"])
    best = cands.sort_values("value", ascending=False).drop_duplicates("row_id").set_index("row_id")
    out = []
    margin = knobs.get("margin", 0.0)
    closed_margin = knobs.get("closed_margin", margin)
    for i, row in enumerate(rows.itertuples(index=False)):
        p_closed, p_same, p_other = probs[i]
        shown_closed = row.shown == "closed"
        options = [("NO_ACTION", "", 0.0)]
        if row.listing_closed:  # Already published as permanently closed, so it's already right.
            out.append((row.entity_id, row.date, "NO_ACTION", "", 0.0))
            continue
        if not shown_closed:
            options.append(("SUGGEST", "closed", p_closed - p_same - p_other - closed_margin))
        if row.row_id in best.index:
            pick = best.loc[row.row_id]
            value = -p_closed - (0.0 if shown_closed else 0.5 * p_same) + p_other * pick["value"] - margin
            if shown_closed:  # Already-right rows here are truly closed, and a suggestion of open is the wrong state.
                value = -p_closed + (p_same + p_other) * pick["value"] - margin
            # Partial credit would pay for wild guesses, but no owner should get one. Tested on both seasons: it costs nothing.
            if p_other * pick["p_exact"] >= knobs.get("min_exact", MIN_EXACT):
                options.append(("SUGGEST", pick["cand"], value))
        action, hours, value = max(options, key=lambda x: x[2])
        out.append((row.entity_id, row.date, action, hours, round(float(value), 4)))
    return out


def flag_rule(rows: pd.DataFrame, knobs: dict) -> np.ndarray:
    """Looks closed for good: reviews saying so, or a recent user edit that wasn't refused."""
    gone = rows["rev_gone_recent"] >= knobs.get("flag_reviews", 1)
    edits = (rows["edit_gone_recent"] - rows["edit_gone_rejected"]) >= knobs.get("flag_edits", 1)
    return ((gone | edits) & (rows["listing_closed"] == 0)).to_numpy()


def to_preds(decisions: list, rows: pd.DataFrame, knobs: dict) -> dict:
    flags = flag_rule(rows, knobs)
    preds = {}
    for (eid, day, action, hours, value), flag in zip(decisions, flags):
        if flag:
            action, hours = "FLAG", ""
        if action != "NO_ACTION":
            preds[(eid, day)] = (action, hours, str(value))
    return preds


def show(name: str, result: dict) -> None:
    b = result["breakdown"]
    print(f"{name:26s} score {result['score_0_100']:6.2f} | prec {result['precision_exact']:.3f} recall {result['recall_exact']:.3f} | "
          f"harmful {result['harmful_suggestions']:4d} | views {result['search_views_protected_pct']:5.1f}% door {result['closed_door_views_prevented_pct']:5.1f}% | "
          f"exact {b.get('exact', 0)} near {b.get('near', 0)} off {b.get('same_state_off', 0)} missed {b.get('missed', 0)} spam {b.get('spam_wrong_hours', 0)} "
          f"redundant {b.get('redundant_confirm', 0)} flag {b.get('flag_correct', 0)}/{b.get('unneeded_flag', 0)}", flush=True)


def extra_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """Past special days outside the scored November to January window. They train the open-or-closed model only."""
    return rows[(rows["cls"] >= 0) & (rows["aux"] == EXTRA)]


def held_out(rows, cands, seeds=(7,), use_aux=True, use_extra=False) -> tuple:
    """Out-of-fold predictions: no business is ever predicted by a model trained on it. Folds match the first stage."""
    labelled = rows[(rows["cls"] >= 0) & (rows["aux"] == 0)].copy()
    extra = extra_rows(rows) if use_extra else rows.iloc[0:0]
    probs = np.zeros((len(labelled), 3))
    cand_rows = cands[(cands["cls"] >= 0) & (cands["aux"] == 0)]
    aux = cands[(cands["aux"] == AUX) & (cands["cls"] == OTHER)] if use_aux else cands.iloc[0:0]
    p_exact = np.zeros(len(cand_rows))
    p_near = np.zeros(len(cand_rows))
    row_fold = labelled["fold"].to_numpy()
    cand_fold = cand_rows["fold"].to_numpy()
    for fold in sorted(set(row_fold)):
        tr, te = pd.concat([labelled[row_fold != fold], extra[extra["fold"] != fold]]), labelled[row_fold == fold]
        ct = pd.concat([cand_rows[cand_fold != fold], aux])
        cp = cand_rows[cand_fold == fold]
        pr, pe, pn = fit_predict(tr, te, ct, cp, seeds)
        probs[row_fold == fold] = pr
        p_exact[cand_fold == fold] = pe
        p_near[cand_fold == fold] = pn
    return labelled, probs, cand_rows, p_exact, p_near


def evaluate(labelled, probs, cand_rows, p_exact, p_near, knobs) -> dict:
    results = {}
    for season, path in ((2026, LABELS_2026), (2025, LABELS_2025)):
        mask = (labelled["season"] == season).to_numpy()
        subset = labelled[mask]
        ids = set(subset["row_id"])
        cmask = cand_rows["row_id"].isin(ids).to_numpy()
        decisions = choose(subset, probs[mask], cand_rows[cmask], p_exact[cmask], p_near[cmask], knobs)
        results[season] = SCORER.score(to_preds(decisions, subset, knobs), str(path))
    return results


def strict_2025(knobs, soft="soft_strict.parquet") -> dict:
    """Both stages trained only on what was knowable before 6 Nov 2025, and on other businesses."""
    rows, cands = load(soft)
    labelled = rows[(rows["cls"] >= 0) & (rows["aux"] == 0)]
    target = labelled[labelled["season"] == 2025]
    preds = {}
    row_fold = labelled["fold"]
    for fold in sorted(set(row_fold)):
        tr = labelled[(labelled["season"] == 2024) & (row_fold != fold)]
        te = target[target["fold"] == fold]
        ct = cands[(cands["season"] == 2024) & (cands["fold"] != fold) & (cands["fold"] >= 0) & (cands["aux"] == 0)]
        cp = cands[(cands["season"] == 2025) & (cands["fold"] == fold) & (cands["aux"] == 0)]
        pr, pe, pn = fit_predict(tr, te, ct, cp, min_season=2024)
        preds.update(to_preds(choose(te, pr, cp, pe, pn, knobs), te, knobs))
    return SCORER.score(preds, str(LABELS_2025))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Also run the strict 2025 back-test")
    parser.add_argument("--soft", default="soft.parquet", help="Which first-stage feature file to use")
    args = parser.parse_args()
    start = time.time()
    rows, cands = load(args.soft)
    labelled = rows[(rows["cls"] >= 0) & (rows["aux"] == 0)]
    print(f"{len(rows)} rows, {len(cands)} candidates, {labelled['cls'].value_counts().to_dict()}", flush=True)
    other = labelled[labelled["cls"] == OTHER]
    covered = set(cands.loc[(cands["cls"] == OTHER) & (cands["exact"] == 1) & (cands["aux"] == 0), "row_id"])
    print(f"Candidate list has the exact truth on {len(covered) / max(1, len(other)):.1%} of 'other hours' rows", flush=True)
    labels = pd.read_csv(LABELS_2026)
    joined = labels.merge(rows[rows["season"] == 2026][["entity_id", "date", "shown"]], on=["entity_id", "date"])
    print(f"Our 'shown' matches the label's on {(joined['shown'] == joined['displayed_hours_at_snapshot']).mean():.2%} of 2026 rows", flush=True)

    knobs = {"margin": 0.0, "closed_margin": 0.0}
    labelled, probs, cand_rows, p_exact, p_near = held_out(rows, cands)
    other_cands = (cand_rows["cls"] == OTHER).to_numpy()
    top = cand_rows[other_cands].assign(_p=p_exact[other_cands]).sort_values("_p", ascending=False).drop_duplicates("row_id")
    print(f"Hours picker: exact on {top['exact'].mean():.3f} of 'other hours' rows", {int(k): round(v, 3) for k, v in top.groupby("y1_state")["exact"].mean().items()}, flush=True)
    print(f"held-out models done at {time.time() - start:.0f}s", flush=True)
    results = evaluate(labelled, probs, cand_rows, p_exact, p_near, knobs)
    show("2026 held-out", results[2026])
    show("2025 held-out", results[2025])
    if args.strict:
        show("2025 strict (past only)", strict_2025(knobs, args.soft.replace(".parquet", "_strict.parquet")))
    np.savez(CACHE / "oof.npz", probs=probs, p_exact=p_exact, p_near=p_near)
    if args.write:
        write_outputs(rows, cands, labelled, probs, cand_rows, p_exact, p_near, knobs)
    print(f"done in {time.time() - start:.0f}s", flush=True)


def write_outputs(rows, cands, labelled, probs, cand_rows, p_exact, p_near, knobs) -> None:
    """Dev rows keep their held-out predictions, so checking the file gives an honest score.

    Test and demo rows come from a final fit on all dev businesses.
    """
    target = rows[(rows["season"] == 2026) & (rows["cls"] < 0)]
    ids = set(target["row_id"])
    cp = cands[cands["row_id"].isin(ids)]
    train_cands = pd.concat([cand_rows, cands[(cands["aux"] == AUX) & (cands["cls"] == OTHER)]])
    pr, pe, pn = fit_predict(labelled, target, train_cands, cp, seeds=(7, 21, 33))

    dev_mask = (labelled["season"] == 2026).to_numpy()
    dev_rows = labelled[dev_mask]
    dev_cmask = cand_rows["row_id"].isin(set(dev_rows["row_id"])).to_numpy()
    parts = [(dev_rows, probs[dev_mask], cand_rows[dev_cmask], p_exact[dev_cmask], p_near[dev_cmask]), (target, pr, cp, pe, pn)]

    decisions = {}
    lines = []
    for subset, q, c, a, b in parts:
        chosen = choose(subset, q, c, a, b, knobs)
        flags = flag_rule(subset, knobs)
        sources = [col for col in c.columns if col.startswith("src_")]
        picked = c.assign(_e=a).sort_values("_e", ascending=False).drop_duplicates(["row_id", "cand"]).set_index(["row_id", "cand"])
        exact_of = dict(zip(zip(c["row_id"], c["cand"]), a))
        for (eid, day, action, hours, _), flag, row_id, p in zip(chosen, flags, subset["row_id"], q):
            if flag:
                action, hours = "FLAG", ""
            if action == "NO_ACTION":
                continue
            if hours == "closed":
                confidence, used = float(p[CLOSED]), []
            elif action == "SUGGEST":
                confidence = float(p[OTHER] * min(1.0, exact_of.get((row_id, hours), 0.0)))
                source_row = picked.loc[(row_id, hours)]
                used = [col[4:] for col in sources if source_row[col]]
            else:
                confidence, used = 1.0, []
            lines.append((eid, day, action, hours, round(confidence, 3)))
            decisions.setdefault(eid, {})[day] = {"action": action, "hours": hours, "confidence": round(confidence, 3), "p_closed": round(float(p[CLOSED]), 3),
                                                  "p_same": round(float(p[SAME]), 3), "p_other": round(float(p[OTHER]), 3), "sources": used}
    lines.sort()
    with (ROOT / "predictions_2026.csv").open("w", encoding="utf-8") as f:
        f.write("entity_id,date,action,hours,confidence\n")
        for eid, day, action, hours, confidence in lines:
            quoted = f'"{hours}"' if "," in hours else hours
            f.write(f"{eid},{day},{action},{quoted},{confidence}\n")
    (ROOT / "connect" / "model_decisions.json").write_text(json.dumps(decisions, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(lines)} actions to predictions_2026.csv and connect/model_decisions.json", flush=True)


if __name__ == "__main__":
    main()
