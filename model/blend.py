#!/usr/bin/env python3
"""Final model: LightGBM (3 seeds, trained on all past special days) blended with TabICLv2 and two history transformers,
plus a stricter rule for 'closed'.

    python model/blend.py --weight 0.4 --hist-weight 0.2 --closed-margin 0.2 [--strict] [--write]

Dev rows get held-out predictions from every model, so the file scores honestly. Test and demo rows come from the final
fits: LightGBM on all dev businesses, the neural models averaged over their five fold models.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from model.train import (AUX, CACHE, CLOSED, LABELS_2025, LABELS_2026, OTHER, SAME, SCORER, choose, extra_rows, fit_predict,  # noqa: E402
                         flag_rule, held_out, load, show, to_preds)


def saved(name: str, row_ids, field: str = "probs") -> np.ndarray:
    """One saved neural model's predictions, in the order of row_ids."""
    nn = np.load(CACHE / name)
    index = pd.Series(np.arange(len(nn["row_id"])), index=nn["row_id"])
    return nn[field][index.loc[row_ids].to_numpy()]


def mix(args, lgbm: np.ndarray, row_ids, field: str = "probs", suffix: str = "") -> np.ndarray:
    """LightGBM and TabICLv2 by --weight, then the average of the transformers by --hist-weight."""
    tab = saved(args.nn.replace(".npz", suffix + ".npz") if suffix else args.nn, row_ids, field)
    hist = np.mean([saved(name.replace(".npz", suffix + ".npz"), row_ids, field) for name in args.hist.split(",")], axis=0)
    assert not np.isnan(tab).any() and not np.isnan(hist).any(), "A neural model is missing rows; run it on all folds"
    return (1 - args.hist_weight) * ((1 - args.weight) * lgbm + args.weight * tab) + args.hist_weight * hist


def strict(args, knobs) -> None:
    """Every model trained only on what was knowable before 6 Nov 2025, on other businesses, then scored on 2025."""
    rows, cands = load("soft_strict.parquet")
    labelled = rows[(rows["cls"] >= 0) & (rows["aux"] == 0)]
    target = labelled[labelled["season"] == 2025].reset_index(drop=True)
    extra = extra_rows(rows)
    extra = extra[(extra["season"] == 2024) & (extra["date"] < "2025-11-06")]
    probs = np.zeros((len(target), 3))
    parts = []
    for fold in sorted(set(labelled["fold"])):
        train = pd.concat([labelled[(labelled["season"] == 2024) & (labelled["fold"] != fold)], extra[extra["fold"] != fold]])
        mask = (target["fold"] == fold).to_numpy()
        train_cands = cands[(cands["season"] == 2024) & (cands["fold"] != fold) & (cands["fold"] >= 0) & (cands["aux"] == 0)]
        cand_pred = cands[(cands["season"] == 2025) & (cands["fold"] == fold) & (cands["aux"] == 0)]
        q, pe, pn = fit_predict(train, target[mask], train_cands, cand_pred, min_season=2024)
        probs[mask] = q
        parts.append(cand_pred.assign(_e=pe, _n=pn))
    cand_pred = pd.concat(parts)
    blended = mix(args, probs, target["row_id"], suffix="_strict")
    decisions = choose(target, blended, cand_pred, cand_pred["_e"].to_numpy(), cand_pred["_n"].to_numpy(), knobs)
    show("2025 strict blend", SCORER.score(to_preds(decisions, target, knobs), str(LABELS_2025)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weight", type=float, default=0.4, help="Share of TabICLv2 in the blend")
    parser.add_argument("--closed-margin", type=float, default=0.2)
    parser.add_argument("--nn", default="nn_tabicl_16k.npz")
    parser.add_argument("--hist", default="nn_hist_deep.npz,nn_hist_past.npz", help="The history transformers, averaged")
    parser.add_argument("--hist-weight", type=float, default=0.2, help="Share of the transformers in the blend")
    parser.add_argument("--strict", action="store_true", help="Also run the strict 2025 back-test")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    start = time.time()
    knobs = {"closed_margin": args.closed_margin}
    rows, cands = load()

    labelled, probs, cand_rows, p_exact, p_near = held_out(rows, cands, seeds=(7, 21, 33), use_extra=True)
    blended = mix(args, probs, labelled["row_id"])
    for season, path in ((2026, LABELS_2026), (2025, LABELS_2025)):
        m = (labelled["season"] == season).to_numpy()
        sub = labelled[m]
        cm = cand_rows["row_id"].isin(set(sub["row_id"])).to_numpy()
        for name, q in (("LightGBM", probs[m]), ("blend", blended[m])):
            dec = choose(sub, q, cand_rows[cm], p_exact[cm], p_near[cm], knobs)
            show(f"{season} {name}", SCORER.score(to_preds(dec, sub, knobs), str(path)))
    print(f"held-out done at {time.time() - start:.0f}s", flush=True)
    if args.strict:
        strict(args, knobs)
    if not args.write:
        return

    target = rows[(rows["season"] == 2026) & (rows["cls"] < 0)]
    cp = cands[cands["row_id"].isin(set(target["row_id"]))]
    train_cands = pd.concat([cand_rows, cands[(cands["aux"] == AUX) & (cands["cls"] == OTHER)]])
    pr, pe, pn = fit_predict(pd.concat([labelled, extra_rows(rows)]), target, train_cands, cp, seeds=(7, 21, 33))
    for name in [args.nn] + args.hist.split(","):
        assert saved(name, target["row_id"], "target").sum(axis=1).min() > 0.99, f"{name} has no test-row predictions; run it on all five folds without --strict"
    pr = mix(args, pr, target["row_id"], "target")

    dev_mask = (labelled["season"] == 2026).to_numpy()
    dev_rows = labelled[dev_mask]
    dev_cmask = cand_rows["row_id"].isin(set(dev_rows["row_id"])).to_numpy()
    parts = [(dev_rows, blended[dev_mask], cand_rows[dev_cmask], p_exact[dev_cmask], p_near[dev_cmask]), (target, pr, cp, pe, pn)]
    decisions, lines = {}, []
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
                used = [col[4:] for col in sources if picked.loc[(row_id, hours)][col]]
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
    print(f"wrote {len(lines)} actions to predictions_2026.csv and connect/model_decisions.json at {time.time() - start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
