from __future__ import annotations

import unittest
from unittest import mock

from jobs.tools import t3_f6_home_q00_sizer_v4 as sizer


class HomeQ00SizerV4Tests(unittest.TestCase):
    def corpus(self) -> list[str]:
        return [f"P0|{index:04d}" for index in range(2048)] + [
            f"P1|{index:04d}" for index in range(2048)
        ]

    def test_selection_is_fixed_score_blind_and_balanced(self) -> None:
        corpus = self.corpus()
        fake_phase = lambda fen: fen.split("|", 1)[0]
        with mock.patch.object(sizer, "phase", side_effect=fake_phase):
            first = sizer.choose_roots(corpus)
            second = sizer.choose_roots(list(corpus))

        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)
        self.assertEqual(len(set(first)), 16)
        self.assertEqual(sum(row.startswith("P0|") for row in first), 8)
        self.assertEqual(sum(row.startswith("P1|") for row in first), 8)
        self.assertEqual(sizer.DEPTH, 9)
        self.assertEqual(sizer.ORDER_SEED, 2026092505)

    def test_wrong_corpus_cardinality_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "must contain 4096"):
            sizer.choose_roots(["P0|one"])

    def test_selection_hash_is_order_sensitive_and_deterministic(self) -> None:
        roots = ["a", "b", "c"]
        self.assertEqual(sizer.selection_sha256(roots), sizer.selection_sha256(roots))
        self.assertNotEqual(
            sizer.selection_sha256(roots), sizer.selection_sha256(list(reversed(roots)))
        )


if __name__ == "__main__":
    unittest.main()
