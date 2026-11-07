"""Fixed folds by business, shared by every stage that learns from dev answers.

Each dev business sits in one fold, and anything it is scored with was learned from the other folds.
"""
from __future__ import annotations

import json

import numpy as np

from connect import config

N_FOLDS = 5


def fold_map(dev_ids) -> dict:
    """{entity_id: fold}. Written once to var/model/folds.json and reused, so all stages agree."""
    path = config.VAR_DIR / "model" / "folds.json"
    if path.exists():
        return json.loads(path.read_text())
    order = np.random.RandomState(11).permutation(sorted(dev_ids))
    folds = {str(eid): int(i % N_FOLDS) for i, eid in enumerate(order)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(folds))
    return folds
