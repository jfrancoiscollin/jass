"""Unit contracts for the direct move-decision ranker screen."""

from importlib import util
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SPEC = util.spec_from_file_location(
    "l3_decision_ranker_screen_tested",
    ROOT / "jobs" / "tools" / "l3_decision_ranker_screen.py",
)
assert SPEC is not None and SPEC.loader is not None
SCREEN = util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCREEN)


class DecisionRankerScreenTest(unittest.TestCase):
    def test_pair_features_are_parent_pov_symmetric(self) -> None:
        top1 = np.zeros(30, dtype=np.float64)
        top2 = np.arange(1, 31, dtype=np.float64)
        black = SCREEN.pair_feature_vector(
            top1,
            top2,
            root_side="B",
            choice_top1_cp=12,
            choice_top2_cp=4,
            piece_count=20,
            legal_children=6,
            top1_capture=False,
            top2_capture=True,
        )
        white = SCREEN.pair_feature_vector(
            top1,
            top2,
            root_side="W",
            choice_top1_cp=12,
            choice_top2_cp=4,
            piece_count=20,
            legal_children=6,
            top1_capture=False,
            top2_capture=True,
        )
        np.testing.assert_array_equal(black[:30], -white[:30])
        np.testing.assert_array_equal(black[30:], white[30:])
        self.assertEqual(len(black), len(SCREEN.PAIR_FEATURE_NAMES))

    def _rows(self, *, signal: bool) -> list[dict]:
        rng = np.random.default_rng(555 if signal else 556)
        rows = []
        ordinal = 0
        for pool in (1, 2):
            for index in range(160):
                positive = index % 4 == 0
                judge = 40.0 if positive else -40.0
                vector = rng.normal(0.0, 0.25, len(SCREEN.PAIR_FEATURE_NAMES))
                if signal:
                    vector[0] = 1.0 if positive else -1.0
                    vector[1] = 0.5 if positive else -0.5
                rows.append(
                    {
                        "ordinal": ordinal,
                        "pool_index": pool,
                        "pool_label": f"POOL{pool}",
                        "fen": f"B:W31-50:B1-20 #{pool}-{index}",
                        "judge_top2_minus_top1_cp": judge,
                        "audit_top2_minus_top1_cp": judge,
                        "judge_class": 1 if positive else -1,
                        "audit_class": 1 if positive else -1,
                        "stable_non_tie": True,
                        "pair_features": [float(value) for value in vector],
                    }
                )
                ordinal += 1
        return rows

    def test_strong_oof_decision_signal_passes(self) -> None:
        result = SCREEN.aggregate_rows(
            self._rows(signal=True),
            folds=5,
            fold_seed=2026082311,
            ridge=0.1,
            target_clip_cp=200.0,
            shuffle_seed=2026082312,
            bootstrap_samples=5000,
            bootstrap_seed=2026082313,
            min_total=240,
            min_per_pool=80,
            min_positive=30,
            min_negative=120,
            min_stable_fraction=0.65,
            min_interventions=20,
            max_intervention_rate=0.35,
        )
        self.assertTrue(result["screen_passed"])
        self.assertEqual(
            result["verdict"], "JASS_DECISION_RANKER_MECHANISM_SCREEN_PASSED"
        )
        self.assertGreater(result["aligned_vs_shuffled_gain"]["ci95_cp"][0], 0.0)
        self.assertEqual(result["shuffle_control"]["fixed_points"], 0)
        self.assertEqual(
            result["sample"]["aligned_interventions"],
            sum(row["shuffled_flip"] for row in result["rows"]),
        )

    def test_noise_does_not_pass_mechanistic_gate(self) -> None:
        result = SCREEN.aggregate_rows(
            self._rows(signal=False),
            folds=5,
            fold_seed=2026082311,
            ridge=0.1,
            target_clip_cp=200.0,
            shuffle_seed=2026082312,
            bootstrap_samples=3000,
            bootstrap_seed=2026082313,
            min_total=240,
            min_per_pool=80,
            min_positive=30,
            min_negative=120,
            min_stable_fraction=0.65,
            min_interventions=20,
            max_intervention_rate=0.35,
        )
        self.assertFalse(result["screen_passed"])
        self.assertEqual(
            result["verdict"], "JASS_DECISION_RANKER_MECHANISM_SCREEN_FAILED"
        )

    def test_score_shuffle_is_fixed_point_free_and_cell_preserving(self) -> None:
        rows = self._rows(signal=True)[:80] + self._rows(signal=True)[160:240]
        folds = [SCREEN._fold_for(row, folds=5, seed=2026082311) for row in rows]
        scores = np.arange(len(rows), dtype=np.float64)
        shuffled, report = SCREEN._shuffle_scores(
            rows, scores, folds, seed=2026082312
        )
        self.assertEqual(report["fixed_points"], 0)
        np.testing.assert_array_equal(np.sort(shuffled), scores)
        for pool in (1, 2):
            for fold in range(5):
                mask = np.asarray(
                    [
                        int(row["pool_index"]) == pool and folds[index] == fold
                        for index, row in enumerate(rows)
                    ]
                )
                np.testing.assert_array_equal(
                    np.sort(shuffled[mask]), np.sort(scores[mask])
                )

    def test_duplicate_parent_is_rejected(self) -> None:
        rows = self._rows(signal=True)
        rows[1]["ordinal"] = rows[0]["ordinal"]
        with self.assertRaisesRegex(ValueError, "duplicate decision ordinal"):
            SCREEN.aggregate_rows(
                rows,
                folds=5,
                fold_seed=2026082311,
                ridge=0.1,
                target_clip_cp=200.0,
                shuffle_seed=2026082312,
                bootstrap_samples=100,
                bootstrap_seed=2026082313,
                min_total=240,
                min_per_pool=80,
                min_positive=30,
                min_negative=120,
                min_stable_fraction=0.65,
                min_interventions=20,
                max_intervention_rate=0.35,
            )


if __name__ == "__main__":
    unittest.main()
