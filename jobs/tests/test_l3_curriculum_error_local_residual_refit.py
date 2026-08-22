from __future__ import annotations

from types import SimpleNamespace
import unittest

import numpy as np

from jobs.tools import l3_curriculum_error_local_residual_refit as refit


def decision(label: str, values: dict[int, float], opening: str) -> dict:
    return {
        "label": label,
        "source": {"opening_id": opening},
        "forced_single_action": False,
        "gradient": [
            {
                "coordinate": coordinate,
                "value": value,
                "representative_full_column": coordinate % 12,
            }
            for coordinate, value in sorted(values.items())
        ],
    }


def pair(pair_id: int, split: str, error: dict[int, float], control: dict[int, float]) -> dict:
    return {
        "pair_id": pair_id,
        "split": split,
        "error": decision("error", error, f"e-{pair_id}"),
        "control": decision("control", control, f"c-{pair_id}"),
    }


def reclassified_pair(pair_id: int, split: str = "discovery") -> dict:
    result = pair(pair_id, split, {}, {1: 1.0})
    result["error"].update({
        "informative_ranking": False,
        "reclassified_exact_non_error": True,
        "reclassification_reason": "exact_reclassified_historical_optimal",
        "rival_action": None,
        "gradient": [],
    })
    return result


class CurriculumErrorLocalResidualRefitTests(unittest.TestCase):
    def test_reclassified_pair_and_control_are_excluded_from_every_fit_statistic(self) -> None:
        rows = [
            pair(index, "discovery", {0: 1.0}, {1: 1.0})
            for index in range(290)
        ] + [
            reclassified_pair(index)
            for index in range(290, 353)
        ]
        report = {
            "informative_error_pairs": 290,
            "reclassified_exact_non_errors": {
                "total": 63,
                "excluded_with_their_controls_from_fit_statistics": True,
                "zero_vectors_used_as_observations": False,
            },
        }
        informative, excluded = refit._informative_rows(rows, report)
        self.assertEqual(len(informative), 290)
        self.assertEqual(len(excluded), 63)
        self.assertFalse(any(row["pair_id"] >= 290 for row in informative))

    def test_refit_fails_closed_on_non_290_informative_atlas(self) -> None:
        report = {
            "informative_error_pairs": 289,
            "reclassified_exact_non_errors": {
                "total": 1,
                "excluded_with_their_controls_from_fit_statistics": True,
                "zero_vectors_used_as_observations": False,
            },
        }
        with self.assertRaisesRegex(ValueError, "not 290"):
            refit._informative_rows([reclassified_pair(0)], report)

    def test_matches_same_pattern_and_phase_support(self) -> None:
        rows = [
            pair(index, "discovery", {1: 1.0}, {2: 0.5})
            for index in range(8)
        ]
        sham, matching = refit._match_sham_direction(
            rows,
            {1: 1},
            {1: 1, 2: 2},
            total=12,
            buckets_per_pattern=4,
        )
        self.assertEqual(sham, {2: 1})
        self.assertEqual(matching[0]["error_canonical_bucket"], 1)
        self.assertEqual(matching[0]["sham_canonical_bucket"], 2)

    def test_step_is_nonzero_when_rank_gain_beats_anchor(self) -> None:
        rows = [pair(index, "discovery", {0: 1.0}, {1: 1.0}) for index in range(20)]
        ticks, metrics = refit._choose_step(
            rows,
            {0: 0.0, 1: 0.0},
            {0: 1},
            scale=64,
            grid=[0, 1, 2, 4, 8],
            rank_scale=1.0,
            control_anchor=0.25,
            trust_anchor=0.001,
        )
        self.assertGreater(ticks, 0)
        self.assertLess(
            next(row["objective"] for row in metrics if row["ticks"] == ticks),
            metrics[0]["objective"],
        )

    def test_integer_update_freezes_outside_and_preserves_exact_orbits(self) -> None:
        folder = SimpleNamespace(
            rf_canon=np.asarray([[0, 1, 2], [2, 1, 0]], dtype=np.int64),
            rf_sign=np.asarray([[1, 1, 1], [-1, -1, -1]], dtype=np.int8),
        )
        source = np.zeros(14, dtype=np.int32)  # 2*TB plus two untouched extras
        target, audit = refit._apply_direction_ints(
            source,
            {0: 1, 7: -1},
            ticks=3,
            folder=folder,
            total=6,
        )
        self.assertEqual(target[0], 3)
        self.assertEqual(target[5], -3)
        self.assertEqual(target[7], -3)
        self.assertEqual(target[10], 3)
        self.assertTrue(np.array_equal(target[12:], source[12:]))
        self.assertEqual(audit["changed_outside_region"], 0)
        self.assertTrue(audit["exact_fold_orbits_coherent"])

    def test_confirmation_requires_error_over_sham_without_control_harm(self) -> None:
        rows = [pair(index, "confirm", {0: 1.0}, {1: 1.0}) for index in range(12)]
        metrics, gates = refit._evaluate(
            rows,
            {0: 0.1},
            {2: 0.1},
            bootstrap_samples=1000,
            seed=17,
            control_tolerance=0.0,
        )
        self.assertTrue(all(gates.values()))
        self.assertGreater(metrics["error_minus_sham"]["ci95"][0], 0.0)
        self.assertEqual(metrics["control_gain"]["mean"], 0.0)

    def test_calibration_split_is_deterministic_and_nonempty(self) -> None:
        rows = [pair(index, "discovery", {0: 1.0}, {1: 1.0}) for index in range(100)]
        left = refit._calibration_split(rows, seed=23)
        right = refit._calibration_split(rows, seed=23)
        self.assertEqual(
            [[row["pair_id"] for row in split] for split in left],
            [[row["pair_id"] for row in split] for split in right],
        )
        self.assertTrue(left[0])
        self.assertTrue(left[1])


if __name__ == "__main__":
    unittest.main()
