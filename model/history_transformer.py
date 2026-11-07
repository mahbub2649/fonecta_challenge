#!/usr/bin/env python3
"""Business-history transformer: reads a business's past special days as a sequence, then predicts its coming days.

Each sequence is what was knowable at one snapshot. Labels:
- Coming days of dev businesses in training folds: the true class.
- Past days of those businesses: the true class, including hidden days.
- Past days with an entry, for every business: hide the entry at random and predict it. No answers needed, which is how
  test businesses teach the model. Held-out businesses join this part too, as test businesses would.

    python model/history_transformer.py --epochs 80 --patience 10 --d 128 --layers 4 --drop .3 --seeds 7,21 --tag _deep
    python model/history_transformer.py --epochs 80 --patience 10 --d 128 --past-weight 1.0 --seeds 7,21 --tag _past
    python model/history_transformer.py --strict ...     # trained only on what was knowable before 6 Nov 2025

Output: var/model/nn_hist<tag>.npz, in the same format as neural.py.
"""
import argparse, json, random, sys, time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from connect import config  # noqa: E402

CACHE = config.VAR_DIR / "model"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
PAST_NUM = ["regular_closed", "reg_len", "calls", "views", "actions", "calls_base", "views_base", "calls_ratio", "views_ratio", "m2_ratio", "m3_ratio", "m4_ratio",
            "m5_ratio", "rev_closed_day", "rev_open_day", "rev_wrong_closed_day", "rev_d_close", "rev_d_arrived", "rev_confirmed", "rev_named", "rev_near",
            "edit_n", "edit_closed", "edit_open", "edit_rejected", "rev_week_differs"]
LOG = {"calls", "views", "actions", "calls_base", "views_base"}
QUERY_NUM = ["regular_closed", "reg_len", "shown_closed", "shown_close", "shown_open", "lead_days", "official_holiday", "peer_no_entry", "peer_closed", "peer_special",
             "peer_regular", "peer_closed_among", "peer_d_close", "peer_d_open", "in_mall", "mall_eq_regular", "is_event", "event_km", "p_snow", "in_school_break",
             "has_entry_now", "n_upcoming_entered", "n_upcoming_closed"]
BIZ_NUM = ["tenure_days", "views_30d", "views_90d", "calls_30d", "actions_30d", "views_trend", "actions_trend", "reviews_90d", "n_entries", "n_entries_closed", "n_entries_special",
           "entered_in_time_share", "rev_outdated_n", "rev_seasonal_n", "rev_week_n", "standing", "pilot_n", "pilot_rejected", "pilot_edited"]
STATE = {"closed": 1, "REGULAR": 2}  # Anything else entered is special (3). 0 means no entry, 4 means hidden on purpose.
LABEL_OF_STATE = {1: 0, 2: 1, 3: 2}


def scale(frame, columns):
    out = []
    for c in columns:
        v = pd.to_numeric(frame[c], errors="coerce").astype("float32").to_numpy()
        if c in LOG:
            v = np.log1p(np.maximum(v, 0))
        elif "ratio" in c:
            v = np.log(np.maximum(v, 1e-3))
        out.append(v)
    x = np.stack(out, 1)
    return x


class Data:
    def __init__(self, soft="soft.parquet", past_file="past.parquet"):
        t = time.time()
        rows = pd.read_parquet(CACHE / "rows.parquet")
        rows["fold"] = rows["entity_id"].map(json.loads((CACHE / "folds.json").read_text())).fillna(-1).astype(int)
        rows = rows[~rows["split"].isin(["aux", "extra"])].reset_index(drop=True)
        known = rows["truth"].notna()
        rows["cls"] = -1
        rows.loc[known & (rows["truth"] == "closed"), "cls"] = 0
        rows.loc[known & (rows["truth"] != "closed") & (rows["truth"] == rows["shown"]), "cls"] = 1
        rows.loc[known & (rows["truth"] != "closed") & (rows["truth"] != rows["shown"]), "cls"] = 2
        past = pd.read_parquet(CACHE / past_file)
        keys = sorted(set(past["day_key"].astype(str)) | set(rows["day_key"].astype(str)))
        self.key_id = {k: i + 1 for i, k in enumerate(keys)}
        self.segment_id = {k: i for i, k in enumerate(sorted(set(rows["segment"].astype(str))))}
        self.country_id = {k: i for i, k in enumerate(sorted(set(rows["country"].astype(str))))}
        self.tier_id = {k: i for i, k in enumerate(sorted(set(rows["tier"].astype(str))))}
        snap = {2024: pd.Timestamp("2024-11-06"), 2025: pd.Timestamp("2025-11-06"), 2026: pd.Timestamp("2026-11-06")}
        px, qx, bx = scale(past, PAST_NUM), scale(rows, QUERY_NUM), scale(rows, BIZ_NUM)
        px_mean, px_std = np.nanmean(px, 0), np.nanstd(px, 0) + 1e-6
        qx_mean, qx_std = np.nanmean(qx, 0), np.nanstd(qx, 0) + 1e-6
        bx_mean, bx_std = np.nanmean(bx, 0), np.nanstd(bx, 0) + 1e-6
        self.n_past = px.shape[1] * 2; self.n_query = qx.shape[1] * 2; self.n_biz = bx.shape[1] * 2
        def norm(x, m, s):
            return np.nan_to_num(np.concatenate([(x - m) / s, np.isnan(x).astype("float32")], 1), nan=0.0).astype("float32")
        px, qx, bx = norm(px, px_mean, px_std), norm(qx, qx_mean, qx_std), norm(bx, bx_mean, bx_std)
        self.seqs = []
        qgroups = {k: g for k, g in rows.groupby(["season", "entity_id"], sort=False).groups.items()}
        pgroups = past.groupby(["season", "entity_id"], sort=False).indices
        past_keys = past["day_key"].astype(str).map(self.key_id).to_numpy().astype("int64")
        row_keys = rows["day_key"].astype(str).map(self.key_id).to_numpy().astype("int64")
        first_row = rows.groupby("entity_id", sort=False).head(1).set_index("entity_id")
        for (season, eid), pidx in pgroups.items():
            qidx = np.asarray(qgroups.get((season, eid), []), dtype=int)
            pidx = np.asarray(pidx)
            pidx = pidx[np.argsort(past["date"].to_numpy()[pidx])]
            dates = pd.to_datetime(past["date"].to_numpy()[pidx])
            hours = past["entry_hours"].to_numpy()[pidx]; has = past["has_entry"].to_numpy()[pidx]
            state = np.array([0 if not h else STATE.get(e, 3) for h, e in zip(has, hours)])
            qrow = rows.iloc[qidx] if len(qidx) else None
            first = qrow.iloc[0] if len(qidx) else rows[rows["entity_id"] == eid].iloc[0] if (rows["entity_id"] == eid).any() else None
            if first is None:
                continue
            bi = int(first.name)
            self.seqs.append({
                "season": season, "eid": eid, "fold": int(first["fold"]),
                "biz": bx[bi], "seg": self.segment_id[str(first["segment"])], "cty": self.country_id[str(first["country"])], "tier": self.tier_id[str(first["tier"])],
                "p_num": px[pidx], "p_key": past_keys[pidx], "p_wd": past["weekday"].to_numpy()[pidx].astype("int64"),
                "p_mon": past["month"].to_numpy()[pidx].astype("int64"), "p_gap": ((snap[season] - dates).days.to_numpy() / 365.0).astype("float32"),
                "p_state": state.astype("int64"), "p_truth": past["cls"].to_numpy()[pidx].astype("int64"),
                "q_num": qx[qidx] if len(qidx) else np.zeros((0, self.n_query), "float32"),
                "q_key": row_keys[qidx], "q_wd": rows["weekday"].to_numpy()[qidx].astype("int64"),
                "q_mon": rows["month"].to_numpy()[qidx].astype("int64"), "q_state": rows["entry_now_state"].to_numpy()[qidx].astype("int64"),
                "q_cls": rows["cls"].to_numpy()[qidx].astype("int64"), "q_row": rows["row_id"].to_numpy()[qidx].astype("int64"),
                "q_gap": (-rows["lead_days"].to_numpy()[qidx] / 365.0).astype("float32"),
            })
        self.rows = rows
        self.n_key = len(keys) + 1
        print(f"built {len(self.seqs)} sequences in {time.time() - t:.0f}s; tokens per sequence about {int(np.median([len(s['p_key']) + len(s['q_key']) for s in self.seqs]))}", flush=True)


class Model(nn.Module):
    def __init__(self, data, d=64, layers=3, heads=4, drop=.2):
        super().__init__()
        self.key = nn.Embedding(data.n_key, d); self.wd = nn.Embedding(7, 8); self.mon = nn.Embedding(13, 8); self.state = nn.Embedding(6, 16)
        self.seg = nn.Embedding(len(data.segment_id), d); self.cty = nn.Embedding(len(data.country_id), 8); self.tier = nn.Embedding(len(data.tier_id), 8)
        side = 8 + 8 + 16 + 1
        self.past = nn.Linear(data.n_past + side + d, d); self.query = nn.Linear(data.n_query + side + d, d); self.biz = nn.Linear(data.n_biz + d + 16, d)
        self.kind = nn.Embedding(3, d)
        layer = nn.TransformerEncoderLayer(d, heads, d * 2, drop, batch_first=True, norm_first=True, activation="gelu")
        self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(d); self.drop = nn.Dropout(drop)
        self.head_q = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Dropout(drop), nn.Linear(d, 3)); self.head_p = nn.Linear(d, 3)

    def forward(self, b):
        pk = torch.cat([self.key(b["p_key"]), self.wd(b["p_wd"]), self.mon(b["p_mon"]), self.state(b["p_state"]), b["p_gap"].unsqueeze(-1), b["p_num"]], -1)
        qk = torch.cat([self.key(b["q_key"]), self.wd(b["q_wd"]), self.mon(b["q_mon"]), self.state(b["q_state"]), b["q_gap"].unsqueeze(-1), b["q_num"]], -1)
        p = self.past(pk) + self.kind.weight[0]; q = self.query(qk) + self.kind.weight[1]
        c = self.biz(torch.cat([b["biz"], self.seg(b["seg"]), self.cty(b["cty"]), self.tier(b["tier"])], -1)).unsqueeze(1) + self.kind.weight[2]
        x = self.drop(torch.cat([c, p, q], 1))
        pad = torch.cat([torch.zeros(len(c), 1, dtype=torch.bool, device=c.device), b["p_pad"], b["q_pad"]], 1)
        h = self.norm(self.enc(x, src_key_padding_mask=pad))
        n = p.shape[1]
        return self.head_p(h[:, 1:1 + n]), self.head_q(h[:, 1 + n:])


def collate(seqs, train_labels, rng, mask_rate=.3, aux_weight=.5):
    P = max(len(s["p_key"]) for s in seqs); Q = max(max(len(s["q_key"]) for s in seqs), 1); n = len(seqs)
    np0 = seqs[0]["p_num"].shape[1]; nq0 = seqs[0]["q_num"].shape[1] if seqs[0]["q_num"].ndim == 2 else 0
    b = {k: np.zeros((n, P), "int64") for k in ("p_key", "p_wd", "p_mon", "p_state")}
    b.update({k: np.zeros((n, Q), "int64") for k in ("q_key", "q_wd", "q_mon", "q_state")})
    b["p_gap"] = np.zeros((n, P), "float32"); b["q_gap"] = np.zeros((n, Q), "float32")
    b["p_num"] = np.zeros((n, P, np0), "float32"); b["q_num"] = np.zeros((n, Q, nq0), "float32")
    b["p_pad"] = np.ones((n, P), bool); b["q_pad"] = np.ones((n, Q), bool)
    b["biz"] = np.stack([s["biz"] for s in seqs]); b["seg"] = np.array([s["seg"] for s in seqs]); b["cty"] = np.array([s["cty"] for s in seqs]); b["tier"] = np.array([s["tier"] for s in seqs])
    py = np.full((n, P), -100, "int64"); pw = np.zeros((n, P), "float32"); qy = np.full((n, Q), -100, "int64")
    for i, s in enumerate(seqs):
        a, c = len(s["p_key"]), len(s["q_key"])
        for k in ("p_key", "p_wd", "p_mon", "p_gap", "p_num"):
            b[k][i, :a] = s[k]
        state = s["p_state"].copy()
        b["p_pad"][i, :a] = False
        if rng is not None:
            hide = (state > 0) & (rng.random(a) < mask_rate)
            for j in np.where(hide)[0]:
                py[i, j] = LABEL_OF_STATE[state[j]]; pw[i, j] = aux_weight
            state[hide] = 4
            if train_labels(s):
                truth = s["p_truth"]; ok = (truth >= 0) & (s["p_state"] == 0)
                py[i, :a][ok] = truth[ok]; pw[i, :a][ok] = 1.0
                py[i, :a][hide & (truth >= 0)] = truth[hide & (truth >= 0)]; pw[i, :a][hide & (truth >= 0)] = 1.0
        b["p_state"][i, :a] = state
        if c:
            for k in ("q_key", "q_wd", "q_mon", "q_state", "q_gap", "q_num"):
                b[k][i, :c] = s[k]
            b["q_pad"][i, :c] = False
            if rng is not None and train_labels(s):
                qy[i, :c] = s["q_cls"]
    out = {k: torch.as_tensor(v, device=DEVICE) for k, v in b.items()}
    return out, torch.as_tensor(py, device=DEVICE), torch.as_tensor(pw, device=DEVICE), torch.as_tensor(qy, device=DEVICE)


@torch.no_grad()
def predict(model, seqs, batch=64):
    model.eval(); ids, probs = [], []
    order = sorted((s for s in seqs if len(s["q_key"])), key=lambda s: len(s["p_key"]))
    for i in range(0, len(order), batch):
        part = order[i:i + batch]
        b, *_ = collate(part, lambda s: False, None)
        with torch.amp.autocast("cuda", enabled=DEVICE == "cuda"):
            _, q = model(b)
        q = torch.softmax(q.float(), -1).cpu().numpy()
        for j, s in enumerate(part):
            ids.append(s["q_row"]); probs.append(q[j, :len(s["q_key"])])
    return (np.concatenate(ids), np.concatenate(probs)) if ids else (np.array([], "int64"), np.zeros((0, 3)))


def logloss(ids, probs, by_row):
    y = np.array([by_row[i] for i in ids]); return float(-np.mean(np.log(np.clip(probs[np.arange(len(y)), y], 1e-6, 1))))


def fit(data, k, args, seed, strict=False):
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
    rng = np.random.RandomState(seed)
    dev_ids = sorted({s["eid"] for s in data.seqs if s["fold"] >= 0 and s["fold"] != k})
    rng.shuffle(dev_ids)
    val_ids = set(dev_ids[:len(dev_ids) // 10]); train_ids = set(dev_ids[len(dev_ids) // 10:])
    allowed = {2024} if strict else {2024, 2025, 2026}
    labelled = lambda s: s["eid"] in train_ids and s["season"] in allowed
    if strict:
        # Only what was knowable at the 2025 snapshot, or before, joins training.
        train = [s for s in data.seqs if s["season"] in (2024, 2025) and (s["season"] == 2024 or len(s["p_key"]))]
    else:
        train = list(data.seqs)
    by_row = {int(i): int(c) for i, c in zip(data.rows["row_id"], data.rows["cls"])}
    val = [s for s in data.seqs if s["eid"] in val_ids and (s["season"] in allowed if strict else True) and (s["q_cls"] >= 0).any()]
    model = Model(data, d=args.d, layers=args.layers, drop=args.drop).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=.01)
    steps = args.epochs * (len(train) // args.batch + 1)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps, pct_start=.1)
    scaler = torch.amp.GradScaler("cuda", enabled=DEVICE == "cuda")
    best, best_state, bad = 9.0, None, 0
    query_loss = nn.CrossEntropyLoss(ignore_index=-100); past_loss = nn.CrossEntropyLoss(ignore_index=-100, reduction="none")
    for epoch in range(args.epochs):
        t = time.time(); model.train(); order = rng.permutation(len(train)); total = 0.0; seen = 0
        for i in range(0, len(train), args.batch):
            part = [train[j] for j in order[i:i + args.batch]]
            b, py, pw, qy = collate(part, labelled, rng)
            with torch.amp.autocast("cuda", enabled=DEVICE == "cuda"):
                pl, ql = model(b)
                loss_p = (past_loss(pl.reshape(-1, 3), py.reshape(-1)) * pw.reshape(-1)).sum() / pw.sum().clamp(min=1)
                loss = args.past_weight * loss_p
                if (qy >= 0).any():
                    loss = loss + query_loss(ql.reshape(-1, 3), qy.reshape(-1))
            opt.zero_grad(set_to_none=True); scaler.scale(loss).backward(); scaler.unscale_(opt); nn.utils.clip_grad_norm_(model.parameters(), 1.0); scaler.step(opt); scaler.update(); sched.step()
            total += float(loss) * len(part); seen += len(part)
        vi, vp = predict(model, val)
        keep = np.array([by_row[int(x)] >= 0 for x in vi])
        vl = logloss(vi[keep], vp[keep], by_row)
        print(f"  fold {k} seed {seed} epoch {epoch + 1:2d}: train loss {total / seen:.4f}, validation log-loss {vl:.4f}, {time.time() - t:.0f}s, GPU {torch.cuda.max_memory_allocated() / 1e9 if DEVICE == 'cuda' else 0:.1f} GB", flush=True)
        if vl < best - 1e-4:
            best, bad = vl, 0; best_state = {n: v.detach().cpu().clone() for n, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= args.patience:
                break
    model.load_state_dict(best_state)
    return model, best


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--folds", default="0,1,2,3,4"); a.add_argument("--epochs", type=int, default=14); a.add_argument("--batch", type=int, default=48)
    a.add_argument("--d", type=int, default=64); a.add_argument("--layers", type=int, default=3); a.add_argument("--drop", type=float, default=.2)
    a.add_argument("--lr", type=float, default=1e-3); a.add_argument("--patience", type=int, default=3); a.add_argument("--past-weight", type=float, default=.5)
    a.add_argument("--seeds", default="7"); a.add_argument("--tag", default=""); a.add_argument("--strict", action="store_true")
    args = a.parse_args(); start = time.time()
    data = Data(past_file="past_strict.parquet" if args.strict else "past.parquet")
    n = len(data.rows); index = {int(r): i for i, r in enumerate(data.rows["row_id"])}
    probs = np.full((n, 3), np.nan); target = np.zeros((n, 3)); folds = [int(x) for x in args.folds.split(",")]; seeds = [int(x) for x in args.seeds.split(",")]
    by_row = {int(i): int(c) for i, c in zip(data.rows["row_id"], data.rows["cls"])}
    for k in folds:
        fold_sum = {}
        for seed in seeds:
            model, best = fit(data, k, args, seed, args.strict)
            test = [s for s in data.seqs if s["fold"] == k and (s["season"] == 2025 if args.strict else True) and (s["q_cls"] >= 0).any()]
            i, p = predict(model, test)
            for r, q in zip(i, p):
                fold_sum[int(r)] = fold_sum.get(int(r), 0) + q / len(seeds)
            if not args.strict and len(folds) == 5:
                ti, tp = predict(model, [s for s in data.seqs if s["fold"] == -1 and s["season"] == 2026])
                for r, q in zip(ti, tp):
                    target[index[int(r)]] += q / (5 * len(seeds))
        ids = np.array(list(fold_sum)); p = np.array([fold_sum[int(i)] for i in ids])
        keep = np.array([by_row[int(i)] >= 0 for i in ids])
        probs[[index[int(i)] for i in ids]] = p
        print(f"FOLD {k}: held-out log-loss {logloss(ids[keep], p[keep], by_row):.4f}, accuracy {(p[keep].argmax(1) == np.array([by_row[int(i)] for i in ids[keep]])).mean():.4f}, {time.time() - start:.0f}s", flush=True)
    name = f"nn_hist{args.tag}.npz"
    np.savez(CACHE / name, row_id=data.rows["row_id"].to_numpy(), probs=probs, target=target)
    print(f"saved {name} at {time.time() - start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
