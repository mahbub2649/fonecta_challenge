# Research and references

Work we looked at while building Connect Suggests, and what we did with it. We tested ideas against the organisers' scorer, so a paper's claims didn't decide anything on their own.

Most papers were reviewed at abstract or summary level, not studied in full. Many of the newest results are the authors' own claims, and we haven't independently replicated them.

## Models for tabular data

| Reference | Why we looked at it | What we did |
|---|---|---|
| [TabArena: A Living Benchmark for Machine Learning on Tabular Data](https://arxiv.org/abs/2506.16791) | Reports that deep learning and foundation models can match boosted trees, and that ensembles across model types lead | Led us to blend TabICLv2 with LightGBM |
| [TabICLv2: A better, faster, scalable, and open tabular foundation model](https://arxiv.org/abs/2602.11139) | A transformer foundation model built for larger tables | Used in the final blend. See the results below |
| [TabICL: A Tabular Foundation Model for In-Context Learning on Large Data](https://arxiv.org/abs/2502.05564) | The original version, and how it scales | Background for TabICLv2 |
| [TabPFN-3: Technical Report](https://arxiv.org/abs/2605.13986) | Reports beating tuned boosted trees | Considered, not tested |
| [Exploring Differences Between Tabular Enterprise Data and Public Benchmarks](https://arxiv.org/abs/2606.30452) | Whether benchmark rankings carry over to real tables | A reminder to trust our own scores over benchmarks |

We also tested RealMLP on one fold. It was clearly weaker than LightGBM and didn't help a blend, so we dropped it.

## Treating holidays as a recommender problem

Businesses are like users, holidays are like items, and entered hours are like ratings. The gaps aren't random, because some owners enter hours and others don't.

| Reference | Why we looked at it | What we did |
|---|---|---|
| [Missing Not at Random in Matrix Completion](https://arxiv.org/abs/1910.12774) | Estimating and correcting for informative gaps | Tested low-rank completion of the business-by-holiday table |
| [Synthetic Nearest Neighbors](https://arxiv.org/abs/2609.13586) | Matrix completion when data is missing not at random | Background for the same test |

## Costs and limited labels

| Reference | Why we looked at it | What we did |
|---|---|---|
| [Instance-Dependent Cost-Sensitive Learning for Detecting Transfer Fraud](https://arxiv.org/abs/2005.02488) | Boosting that weighs each row by what a mistake costs | Tested row weights. Our decision layer already chooses actions using the scorer's own points |
| [Revisiting Self-Training with Regularized Pseudo-Labeling for Tabular Data](https://arxiv.org/abs/2302.14013) | Learning from confident guesses on unlabelled rows | Tested a simple form of pseudo-labelling on test rows |

## Sequences of events

| Reference | Why we looked at it | What we did |
|---|---|---|
| [Attention Is All You Need](https://arxiv.org/abs/1706.03762) | The original transformer and its multi-head self-attention | Our history transformer uses this encoder, through PyTorch's implementation. It has no decoder, and it replaces position encodings with each day's time gap. The code is in `model/history_transformer.py` |
| [HT-Transformer: Event Sequences Classification by Accumulating Prefix](https://arxiv.org/abs/2508.01474) | Transformers over event histories. It notes they often lose to RNNs when predicting future targets | Tested a transformer over each business's history. Alone it was weaker than LightGBM, but it cut wrong calls in a blend. We didn't test an RNN |
| [EMIT: Event-Based Masked Auto Encoding for Irregular Time Series](https://arxiv.org/abs/2409.16554) | Pretraining when labels are scarce | Not used directly. Our history transformer has a similar task, hiding past entries and predicting them, but trains it alongside the main task |

## How opening hours are detected in practice

| Reference | Why we looked at it | What we did |
|---|---|---|
| [Mobility-Embedded POIs](https://arxiv.org/abs/2601.21149) | Learning place behaviour, including opening hours and closures, from human movement | Supports the idea of using demand signals as traces |
| [Google Maps keeps your business information up-to-date with AI](https://blog.mapspeople.com/google-maps-keeps-your-business-information-up-to-date-with-ai) | Reports signals such as the last profile update, similar shops and Popular Times | Our signals are close equivalents: entries, peers and analytics |
| [US9154915B2: ascertaining the operating hours of a business](https://patents.google.com/patent/US9154915) | Estimating hours from indirect signals | Background only |

## Language models

| Reference | Why we looked at it | What we did |
|---|---|---|
| [boltuix/bert-mini](https://huggingface.co/boltuix/bert-mini) | A small model that could read reviews | Decided not to train it. It's English-only, and on dev, even a perfect reader of all unread reviews added only about 1 point on 2026 and nothing clear on 2025 |

## Outside data we tested

| Source | What we learned |
|---|---|
| [Nager.Date public holidays API](https://date.nager.at) | Every live holiday for FI, SE and NO in 2025 and 2026 is already in the package's calendar, so it adds nothing to the score |
| [GeoNames](https://www.geonames.org) (CC BY 4.0) | Real population matched 25 of 28 cities. With computed daylight hours, it gave no clear gain, since the hidden answers are synthetic |

## Experiment results

Scored with the organisers' `evaluate.py` on dev businesses each model never saw. Differences under about 0.2 are within noise. All rows use a blend with a stricter rule for suggesting "closed", except the first. The bold row is the model in this repository. The others are the earlier blend of LightGBM and TabICLv2, and experiments on top of it, and aren't included.

| Version | Score, 2026 | Score, 2025 | Wrong calls, 2026 / 2025 |
|---|---:|---:|---:|
| LightGBM only, with the review reader update | 67.56 | 65.52 | 395 / 432 |
| Earlier blend with the stricter rule | 67.98 | 66.05 | 317 / 329 |
| Adding matrix completion | 68.04 | 66.31 | 318 / 322 |
| Adding less weight on the 2024 season | 68.03 | 65.93 | 318 / 333 |
| Adding more weight on hard rows | 67.87 | 65.94 | 316 / 332 |
| Adding city population and daylight | 68.01 | 66.13 | 317 / 330 |
| Adding pseudo-labels | 67.91 | 65.98 | 322 / 334 |
| Adding past entries from all businesses to training | 68.13 | 66.24 | 310 / 332 |
| Training the open or closed model on all past special days | 68.30 | 66.17 | 308 / 323 |
| Also training the hours picker on those days, at half weight | 67.94 | 66.04 | 311 / 330 |
| Adding the history transformer, deep version at 0.25 | 68.28 | 66.08 | 293 / 303 |
| Adding the history transformer, past-weighted version at 0.20 | 68.39 | 65.98 | 296 / 316 |
| Adding all past days and the deep transformer at 0.25 | 68.73 | 66.14 | 290 / 297 |
| **All past days and both transformer versions at 0.20** | **68.62** | **66.27** | **292 / 311** |

We picked the all-past-days and transformer mixes after trying 30, so their gains may be slightly flattering.

In the stricter test, trained only on data from before the 2025 snapshot, all past days alone scored 61.20 with 573 wrong calls, against 60.30 with 554 for the earlier blend. The model in this repository scored 61.10 with 511 wrong calls, using a mix we fixed before running this test.

## Software and data

Third-party components and their licences are listed in the [README](README.md#third-party-code-data-and-licences). The challenge data is the "Connect Suggests simulator, Since AI ry 2026", under CC BY 4.0.
