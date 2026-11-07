#!/usr/bin/env python3
"""Where the points are lost, from the saved held-out predictions. Uses dev answers, for analysis only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from model.train import CACHE, CLOSED, LABELS_2026, OTHER, SAME, choose, load  # noqa: E402
from connect import config  # noqa: E402


def main() -> None:
    rows, cands = load()
    saved = np.load(CACHE / "oof.npz")
    labelled = rows[rows["cls"] >= 0].copy()
    cand_rows = cands[cands["cls"] >= 0]
    mask = (labelled["season"] == 2026).to_numpy()
    sub = labelled[mask].copy()
    cmask = cand_rows["row_id"].isin(set(sub["row_id"])).to_numpy()
    decisions = choose(sub, saved["probs"][mask], cand_rows[cmask], saved["p_exact"][cmask], saved["p_near"][cmask], {})
    sub["action"] = [d[2] for d in decisions]
    sub["hours"] = [d[3] for d in decisions]
    p = saved["probs"][mask]
    sub["p_closed"], sub["p_same"], sub["p_other"] = p[:, 0], p[:, 1], p[:, 2]
    labels = pd.read_csv(LABELS_2026)
    sub = sub.merge(labels[["entity_id", "date", "expected_action", "mismatch_type", "displayed_hours_at_snapshot"]], on=["entity_id", "date"])

    def points(r):
        exp, a, h, truth, shown = r.expected_action, r.action, r.hours, r.truth, r.displayed_hours_at_snapshot
        if exp == "SUGGEST":
            if a != "SUGGEST":
                return 0.0
            if h == truth:
                return 1.0
            return -1.0 if (h == "closed") != (truth == "closed") else 0.2
        if exp == "FLAG":
            return 0.3 if (a == "SUGGEST" and h == "closed") else (-1.0 if a == "SUGGEST" else 0.0)
        if a == "SUGGEST":
            return -0.1 if h == shown else (-1.0 if (h == "closed") != (shown == "closed") else -0.5)
        return 0.0

    sub["pts"] = sub.apply(points, axis=1)
    sub["need"] = (sub["expected_action"] != "NO_ACTION").astype(int)
    print("points", round(sub["pts"].sum()), "of", sub["need"].sum(), "=", round(100 * sub["pts"].sum() / sub["need"].sum(), 2))
    print("\nBy expected class:\n", sub.groupby(["cls", "action"]).size().unstack(fill_value=0))
    for col in ("day_key", "segment", "y1_state", "in_mall"):
        g = sub.groupby(col, observed=True).agg(need=("need", "sum"), pts=("pts", "sum"), n=("pts", "size"))
        g["score"] = (100 * g["pts"] / g["need"].clip(lower=1)).round(1)
        g["lost"] = (g["need"] - g["pts"]).round(0)
        print(f"\nBy {col}:\n", g.sort_values("lost", ascending=False).head(16).to_string())

    print("\nCalibration of P(closed), by bin (shown open):")
    open_rows = sub[sub["shown"] != "closed"]
    bins = pd.cut(open_rows["p_closed"], [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1])
    print(open_rows.groupby(bins, observed=True).agg(n=("cls", "size"), actual=("cls", lambda x: (x == CLOSED).mean()), mean_p=("p_closed", "mean")).round(3).to_string())

    print("\nShown mismatches:")
    bad = sub[sub["shown"] != sub["displayed_hours_at_snapshot"]]
    print(len(bad), bad[["entity_id", "date", "day_key", "shown", "displayed_hours_at_snapshot", "truth", "expected_action", "segment"]].head(12).to_string())

    data_reg = pd.read_csv(config.DATA_DIR / "labels" / "dev_regular_hours_truth.csv")
    gone = data_reg[data_reg["permanently_closed"] == 1]["entity_id"].tolist()
    print("\nClosed for good on dev:", gone)
    cols = ["rev_gone_recent", "rev_gone_all", "edit_gone_n", "edit_gone_recent", "edit_gone_accepted", "edit_gone_rejected", "views_trend", "actions_trend", "reviews_90d"]
    ent = sub.groupby("entity_id")[cols].first()
    ent["is_gone"] = ent.index.isin(gone).astype(int)
    print(ent[ent["is_gone"] == 1].round(2).to_string())
    sig = ent[(ent["rev_gone_all"] > 0) | (ent["edit_gone_n"] > 0)]
    print("\nAny closure signal:\n", sig.round(2).to_string())
    print("\nviews_trend quantiles, not gone:", ent[ent["is_gone"] == 0]["views_trend"].quantile([0, .001, .01, .05, .5]).round(2).to_dict())
    print("actions_trend quantiles, not gone:", ent[ent["is_gone"] == 0]["actions_trend"].quantile([0, .001, .01, .05, .5]).round(2).to_dict())
    print("outdated listings on dev:", int(data_reg["listing_is_outdated"].sum()))
    outdated = set(data_reg[data_reg["listing_is_outdated"] == 1]["entity_id"])
    x = sub[sub["entity_id"].isin(outdated)]
    print("outdated: rows", len(x), "points", round(x["pts"].sum()), "need", x["need"].sum(), "week_edit_any mean", x["week_edit_any"].mean().round(2), "others", sub[~sub["entity_id"].isin(outdated)]["week_edit_any"].mean().round(2))


if __name__ == "__main__":
    main()
