"""The keyword learner and the matcher the feature code uses."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from model.keywords import DEFAULTS, label, select, wilson_lower  # noqa: E402
from model.review_text import KeywordMatcher, ngrams, normalise  # noqa: E402


class ReviewTextTest(unittest.TestCase):
    def test_numbers_become_one_word(self):
        self.assertEqual(normalise("Suljettiin jo klo 14.30!"), "suljettiin jo klo #!")
        self.assertIn("jo klo #", ngrams("Suljettiin jo klo 14.30. Harmi.", 3))

    def test_ngrams_stay_inside_a_sentence(self):
        grams = ngrams("Stod framför en stängd dörr. Onödig resa.", 2)
        self.assertIn("stängd dörr", grams)
        self.assertNotIn("dörr onödig", grams)

    def test_dev_business_uses_the_list_learned_without_its_fold(self):
        matcher = KeywordMatcher({"config": {"mode": "union"}, "fold_of": {"FI-00002": 3},
                                  "lists": {"all": {"closed": ["turha reissu"]}, "3": {"closed": ["synd"]}}})
        self.assertEqual(matcher.classes("FI-00002", "Turha reissu."), set())
        self.assertEqual(matcher.classes("FI-00002", "Synd."), {"closed"})
        self.assertEqual(matcher.classes("FI-00001", "Turha reissu."), {"closed"})


class LearnerTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(label([("closed", "10:00-18:00")]), {"closed"})
        self.assertEqual(label([("10:00-14:00", "10:00-18:00")]), {"early"})
        self.assertEqual(label([("10:00-18:00", "10:00-18:00")]), {"open"})
        self.assertEqual(label([("18:00-01:00", "18:00-02:00")]), {"early"})  # Past midnight.
        self.assertEqual(label([("closed", "closed")]), set())
        self.assertEqual(label([]), set())

    def test_wilson_needs_support(self):
        self.assertLess(wilson_lower(3, 3), 0.5)
        self.assertGreater(wilson_lower(40, 40), 0.9)

    def test_select_keeps_reliable_phrases_and_drops_longer_copies(self):
        counts = {"turha": [40, 40, 0, 0], "turha reissu": [40, 40, 0, 0], "kiva": [100, 20, 0, 70], "harvinainen": [3, 3, 0, 0]}
        result = select(counts, [400, 80, 10, 200], dict(DEFAULTS))
        self.assertEqual(result["lists"]["closed"], ["turha"])
        self.assertEqual(result["lists"]["early"], [])


if __name__ == "__main__":
    unittest.main()
