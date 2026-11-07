# Learning the review keywords on LUMI

The review reader in `model/features.py` uses hand-written phrases to spot closed-door complaints. This pipeline
learns those phrase lists from the dev answers instead. It then tests many learner settings on LUMI, each one scored
end to end with the organisers' `evaluate.py`, and keeps a setting only if it really beats the current model.

Everything runs from your laptop with `lumi/lumi.sh`. LUMI does the heavy part: each experiment rebuilds the
features and retrains both model stages, which takes about 5–15 minutes, and the sweep runs up to 24 of them at once.

## What the learner does

`model/keywords.py` labels each dev review by what was true on the special days just before it:

| Class | The review followed a day when… |
|---|---|
| `closed` | the business was closed, but the listing showed it open |
| `early` | it was open but closed earlier than the listing showed |
| `open` | it was open |

It then keeps the word sequences (1–4 words, numbers as `#`, in all four languages) where the share with that label
is reliably high: the lower end of the 95% Wilson interval is above `min_precision`. A longer phrase is dropped if
it contains a shorter phrase that was already kept.

How the lists are used, set by `mode`:

- `union`: they add to the hand-written phrases.
- `replace`: they stand in for the hand-written "closed" and "open" phrases, so you can test the reader with no
  hand-written context. Clock times ("closed already at 14") are still read by the existing patterns.

### Rules that keep the scores honest

- Only reviews and answers dated before 6 Nov 2025 are used, so the strict 2025 back-test stays strict.
- Each dev business is read with a list learned without its fold. These are the same 5 folds as the model, so no
  business is scored with phrases learned from its own answers.
- Every sweep includes three baselines with no keywords and different seeds. Their spread is the noise. The
  winner must beat all three on 2026 and stay within the noise on both 2025 seasons. If nothing does, the pick is
  the current model.

## One-time setup

1. You need a LUMI account with SSH access. Your public key is registered through MyAccessID, and you need a
   project with CPU billing units. Check by hand first: `ssh -i ~/.ssh/id_ed25519 <user>@lumi.csc.fi`.
2. `cp lumi/config.env.example lumi/config.env`, then fill in `LUMI_USER`, `LUMI_PROJECT` (like
   `project_465000123`) and `LUMI_SSH_KEY`.
3. Run these:

```bash
lumi/lumi.sh check     # connects and shows your project's allocation
lumi/lumi.sh sync      # code to /scratch/<project>/<user>/fonecta/repo, data next to it
lumi/lumi.sh setup     # Python environment in /projappl/<project>/<user>/fonecta-env (a few minutes)
lumi/lumi.sh smoke     # one baseline on the debug partition, to test the whole path (about 15 min)
lumi/lumi.sh logs      # follow it. It ends with a line like "baseline: 2026 67.xx | 2025 65.xx | strict 2025 59.xx"
```

## The sweep

```bash
lumi/lumi.sh sweep small   # 19 runs: 3 baselines + 16 settings
lumi/lumi.sh status        # queue, and how many results are in
lumi/lumi.sh fetch         # results to lumi/results/, plus the leaderboard
```

`sweep full` runs 219 settings. Read the cost section first.

`fetch` prints the leaderboard and writes `lumi/results/leaderboard.csv`. The `d_` columns are the difference
from the baseline. Each run's result file also lists the phrases it learned (`keywords`), so you can read what
it found.

## Using the winner

```bash
lumi/lumi.sh final    # rebuilds predictions with the picked setting (on LUMI)
lumi/lumi.sh pull     # predictions_2026.csv, connect/model_decisions.json and model/keywords.json into this repo
python3 ../fonecta_data/FONECTA_CONNECT_SUGGESTS_2026/evaluation/evaluate.py --predictions predictions_2026.csv
```

If the pick is the baseline, skip `final`: the committed predictions already are the baseline.

Once `model/keywords.json` is in the repo, a local rebuild (`model/train.py --write` and the steps before it)
uses it automatically. `CONNECT_KEYWORDS=off` turns it off, and `CONNECT_KEYWORDS=<path>` picks another list.
The web app doesn't need it: it reads the saved model output.

## Cost

Each run takes 16 cores for about 5–15 minutes on the `small` partition, so roughly 2–4 core-hours (CPU billing
units).

| Grid | Runs | Approx. CPU core-hours |
|---|---:|---:|
| `smoke` | 1 | 1–4 |
| `small` | 19 | 40–80 |
| `full` | 219 | 450–900 |

Check your balance with `lumi/lumi.sh check` before a `full` sweep. The model has no GPU code, so GPU
partitions would only waste GPU hours.

## Where things are on LUMI

| Path | What |
|---|---|
| `/scratch/<project>/<user>/fonecta/repo` | Code (synced, `.env` and `lumi/config.env` never leave your laptop) |
| `/scratch/<project>/<user>/fonecta/fonecta_data` | The challenge package (synthetic, CC BY 4.0) |
| `/scratch/<project>/<user>/fonecta/runs/<name>` | One run's keyword list and scores. Feature tables are deleted after the run (`KEEP_RUNS=1` keeps them) |
| `/scratch/<project>/<user>/fonecta/results` | One JSON per run |
| `/scratch/<project>/<user>/fonecta/logs` | Slurm logs |
| `/projappl/<project>/<user>/fonecta-env` | Python environment |

LUMI cleans `/scratch` after 90 days without use, so fetch your results soon after the sweep.

## Troubleshooting

- **`setup` fails on `lumi-container-wrapper`.** It falls back to a plain venv. To retry from scratch:
  `FORCE=1` in front of the setup command on LUMI, or delete the environment folder.
- **A run died.** `lumi/lumi.sh status` lists logs with errors, and `lumi/lumi.sh logs 100` shows the newest
  one. If it ran out of memory, set `LUMI_MEM=48G`. If it ran out of time, set `LUMI_TIME=03:00:00`.
- **Stop everything:** `lumi/lumi.sh cancel`.
