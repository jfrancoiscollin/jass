from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_context3_decision_flip_autopsy import (
    aggregate,
    exact_image_fen,
    exact_image_move,
    parse_best_line,
    select_openings,
)


class DecisionFlipAutopsyTests(unittest.TestCase):
    def test_exact_image_is_an_involution(self) -> None:
        fen = "W:W31,32,K40:B1,20,K7"
        self.assertEqual(exact_image_fen(exact_image_fen(fen)), fen)
        self.assertEqual(exact_image_move("31-27"), "20-24")
        self.assertEqual(exact_image_move("40x12"), "11x39")

    def test_parse_best_line(self) -> None:
        self.assertEqual(
            parse_best_line("bestmove 31-27 score=-19 depth=9 nodes=1234 pv=31-27"),
            {"score": -19, "depth": 9, "nodes": 1234},
        )

    def test_selection_is_deterministic_and_balanced(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pools = []
            for label, side in (("p1", "W"), ("p2", "B")):
                path = root / f"{label}.fen"
                path.write_text(
                    "\n".join(
                        f"{side}:W{31+i}:B{1+i}" for i in range(10)
                    )
                    + "\n",
                    encoding="utf-8",
                )
                pools.append((label, path))
            first = select_openings(pools, per_pool=4, seed=17)
            second = select_openings(pools, per_pool=4, seed=17)
            self.assertEqual(first, second)
            self.assertEqual(first["total"], 8)
            self.assertEqual(
                [row["pool_index"] for row in first["rows"]].count(1), 4
            )

    def test_aggregate_detects_harmful_aligned_choices(self) -> None:
        selection = {
            "total": 24,
            "rows": [{"ordinal": index} for index in range(24)],
        }
        rows = []
        for index in range(24):
            rows.append(
                {
                    "ordinal": index,
                    "pool_index": 1 if index < 12 else 2,
                    "piece_count": 20,
                    "flipped": True,
                    "judgements": {
                        label: {"aligned_minus_shuffled_cp": -10 - index}
                        for label in ("CURRICULUM", "ALIGNED", "SHUFFLED")
                    },
                    "consensus_aligned_minus_shuffled_cp": -10 - index,
                    "exact_symmetry": {
                        "models": {
                            label: {
                                "score_delta": 0,
                            }
                            for label in ("CURRICULUM", "ALIGNED", "SHUFFLED")
                        }
                    },
                }
            )
        report = aggregate(
            selection,
            [
                {
                    "shard": 0,
                    "rows": rows,
                }
            ],
            bootstrap_samples=2000,
            bootstrap_seed=4,
        )
        self.assertEqual(
            report["verdict"],
            "JASS_CONTEXT3_DECISION_CHANNEL_CONFIRMED_HARMFUL",
        )
        self.assertTrue(report["perspective_guards"]["all_scores_exact"])
        self.assertLess(
            report["deep_judges"]["CURRICULUM"]["ci95_cp"][1], 0
        )


if __name__ == "__main__":
    unittest.main()
