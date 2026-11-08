"""Review text as word n-grams, and the learned keyword lists that classify it.

Shared by the keyword learner (model/keywords.py) and the feature code (model/features.py), so a phrase is
found the same way when it is learned and when it is used. Standard library only.
"""
from __future__ import annotations

import re

_NUMBER = re.compile(r"\d+(?:[.:]\d+)?")
_SENTENCE = re.compile(r"[.!?;]+|\n+")
_TOKEN = re.compile(r"[#\w]+")
CLASSES = ("closed", "early", "open")  # Closed on the day / closed earlier than shown / open on the day.


def normalise(text: str) -> str:
    """Lower case, and every number or clock time as '#', so '14.30' and '16' are the same word."""
    return _NUMBER.sub("#", (text or "").lower())


def ngrams(text: str, n_max: int) -> set:
    """Every run of 1..n_max words inside one sentence."""
    out = set()
    for sentence in _SENTENCE.split(normalise(text)):
        tokens = _TOKEN.findall(sentence)
        for n in range(1, n_max + 1):
            for i in range(len(tokens) - n + 1):
                out.add(" ".join(tokens[i:i + n]))
    return out


class KeywordMatcher:
    """Applies a keywords.json file. Dev businesses use the list learned without their own fold."""

    def __init__(self, payload: dict):
        self.mode = payload["config"].get("mode", "union")
        self.fold_of = payload.get("fold_of", {})
        self.lists = {fold: {cls: set(phrases) for cls, phrases in by_class.items()}
                      for fold, by_class in payload["lists"].items()}
        lengths = [len(p.split()) for by_class in self.lists.values() for phrases in by_class.values() for p in phrases]
        self.n_max = max(lengths, default=1)

    def classes(self, eid: str, text: str) -> set:
        fold = self.fold_of.get(eid)
        lists = self.lists.get(str(fold), self.lists["all"]) if fold is not None else self.lists["all"]
        grams = ngrams(text, self.n_max)
        return {cls for cls, phrases in lists.items() if grams & phrases}
