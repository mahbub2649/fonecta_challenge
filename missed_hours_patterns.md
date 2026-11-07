# Missed special-hours days: patterns for the model work

Basis: 2026 dev labels, held-out predictions (`predictions_2026.csv`, score 67.66).

**Population.** 4,603 rows where we stayed silent, the listing shows open hours and the truth is also open. Of these, 525 (11.4%) need an hours change ("needs change"); the rest are regular days. All rates below are the share of abstained rows that need a change. Lift is that rate divided by the 11.4% base rate.

## What predicts "needs a change"

| Pattern | Need-change rate | Lift |
|---|---|---|
| Peers enter special hours on 20-40% of days | 38% | 3.3x |
| Peers enter special hours on 5-20% of days | 25% | 2.2x |
| Peers enter special hours on 5% or fewer days | 4% | 0.3x |
| XMAS_EVE | 33% | 2.9x |
| NYE | 31% | 2.7x |
| EPIPHANY_EVE | 26% | 2.3x |
| FATHERS_DAY, LUCIA | 1% | near zero |
| Bakery, hair salon, clothing store, real estate agency | 20-22% | about 1.8x |
| Official public holiday | 18% | 1.6x |
| In a shopping centre | 6% | 0.5x |
| Regular hours longer than 15 hours | 4% | 0.3x |

Notes:
- The two upper peer bands hold 73% of the misses.
- Thursday shows a 31% rate, but that is most likely NYE and Christmas Eve falling on Thursdays in 2026, so treat it as a confound.
- INTERDAY has a low rate (6%) but high volume, and makes up 15% of the misses.

## What the change looks like

- 69% of the misses change only the closing time. The opening time is unchanged on 363 of 525.
- The shift is day specific. Median close shift against the shown hours:
  - XMAS_EVE and XMAS_DAY: about -300 minutes
  - NEW_YEARS_DAY: -330
  - NYE and EPIPHANY_EVE: -180
  - BOXING_DAY, EPIPHANY, INTERDAY: -120
  - BLACK_FRIDAY and DEC23: +60 (stay open later)
- The most common single close shifts are +60 (74 rows), -120 (57) and -60 (50).
- The hours picker is not the bottleneck. The true hours are among the candidates on 98% of these rows, and the top candidate is exact on 57% of the misses.

## Why they were missed

- The second stage gave a median `P(other)` of 0.32 on these rows. The joint `P(other) x P(exact)` fell below `MIN_EXACT = 0.25` on 476 of the 523 wrong-hours misses.
- The first stage (`past_days.py`) recovers only 57% of past days with special hours (3,166 of 5,547). Most of the rest are labelled "same as regular".
- 95% of the missed rows have no entry for the same day in the last two years, so they look like regular days on most traces. Call spikes do not discriminate (40% on missed rows against 39% on regular days). Reviews with clock times are almost absent (1%).

## The finding to act on

A small classifier separates needs-change rows from regular days among the abstained rows with AUC 0.88. Almost all of that signal comes from the first-stage feature `soft_key_other`. The next feature, `peer_special`, carries about a tenth of its weight.

So the first stage is where to work. Sharper `soft_key_other` estimates, especially on days with no entry in the last two years, are the lever.

Caveat: even the top 5% of abstained rows by this score need a change only 52% of the time, which is break-even for an hours suggestion. Better calibration alone will not unlock much. The gain has to come from better discrimination in the first stage.

## What I ruled out at the decision layer

- Calibration of `P(closed)` is already good, and isotonic recalibration adds nothing meaningful.
- A knob sweep (`margin`, `closed_margin`, `min_exact`) moves the score by about 0.1 to 0.3 at most. `margin = -0.02` with `min_exact = 0.15` gave +0.09 on 2026 and +0.28 on 2025.
- Near-miss hours credit is not available. `near` is 0 in both seasons, because true times fall on the full hour and candidates move in 60-minute steps.
