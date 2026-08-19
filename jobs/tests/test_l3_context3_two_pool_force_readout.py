import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools.l3_context3_two_pool_force_readout import build_report


def _write_gate(
    path: Path,
    *,
    ones: int,
    view: str,
    bootstrap_seed: int,
) -> None:
    scores = np.concatenate(
        (np.ones(ones, dtype=np.float64), np.zeros(3000 - ones, dtype=np.float64))
    )
    wins = 2 * ones
    losses = 6000 - wins
    rate = wins / 6000.0
    search = ",".join(f"p{i}=0" for i in range(63))
    payload = {
        "complete": True,
        "n": 6000,
        "wins_a": wins,
        "draws": 0,
        "wins_b": losses,
        "rate": rate,
        "pairs": 1,
        "nshards": 12,
        "max_parallel": 12,
        "jass_a": "/tmp/jass",
        "jass_b": "/tmp/jass",
        "pattern_a": "/tmp/aligned.pjtw",
        "pattern_b": "/tmp/shuffled.pjtw",
        "search_params_a": search,
        "search_params_b": search,
        "depth": None if view == "native" else 9,
        "movetime": 0.1 if view == "native" else None,
        "paired_opening": {
            "method": "paired_colour_opening_cluster_bootstrap",
            "n_openings": 3000,
            "games_per_opening": 2,
            "bootstrap_samples": 200000,
            "seed": bootstrap_seed,
            "rate": rate,
            "ci_low": rate - 0.01,
            "ci_high": rate + 0.01,
            "probability_rate_gt_half": 1.0 if rate > 0.5 else 0.0,
            "error_draws": 0,
            "per_opening_scores": scores.tolist(),
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class Context3TwoPoolForceReadoutTests(unittest.TestCase):
    def _report(self, native_ones: tuple[int, int]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {}
            for pool_index in (1, 2):
                for view in ("native", "q00"):
                    path = root / f"pool{pool_index}-{view}.json"
                    ones = native_ones[pool_index - 1] if view == "native" else 1600
                    _write_gate(
                        path,
                        ones=ones,
                        view=view,
                        bootstrap_seed=2026081908 + pool_index,
                    )
                    paths[(pool_index, view)] = path
            return build_report(
                gate_paths=paths,
                pool_certificate={
                    "verdict": "JASS_CONTEXT3_TWO_FRESH_POOLS_READY",
                    "mutually_disjoint": True,
                    "pools": [
                        {"openings": 3000, "sha256": "a" * 64},
                        {"openings": 3000, "sha256": "b" * 64},
                    ],
                },
                model_certificate={
                    "verdict": "JASS_CONTEXT3_FORCE_MODELS_AUTHENTICATED",
                    "distinct": True,
                },
                bootstrap_samples=2000,
                native_seed=2026081911,
                q00_seed=2026081912,
                gate_bootstrap_seeds={1: 2026081909, 2: 2026081910},
            )

    def test_establishes_compatible_positive_native_effect(self) -> None:
        report = self._report((1700, 1680))
        self.assertEqual(
            report["verdict"],
            "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_ESTABLISHED_POSITIVE",
        )
        self.assertTrue(report["decision"]["primary_established_positive"])
        self.assertFalse(report["decision"]["q00_can_override_primary"])
        self.assertEqual(report["protocol"]["games_total"], 24000)
        self.assertEqual(report["protocol"]["frozen_cohorts_read"], 0)

    def test_one_nonpositive_native_pool_closes_primary(self) -> None:
        report = self._report((1700, 1490))
        self.assertEqual(
            report["verdict"],
            "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED",
        )
        self.assertFalse(report["decision"]["both_native_pool_points_positive"])
        self.assertFalse(report["decision"]["primary_established_positive"])

    def test_rejects_non_disjoint_pools(self) -> None:
        with self.assertRaisesRegex(ValueError, "not mutually disjoint"):
            build_report(
                gate_paths={},
                pool_certificate={
                    "verdict": "JASS_CONTEXT3_TWO_FRESH_POOLS_READY",
                    "mutually_disjoint": False,
                },
                model_certificate={},
                bootstrap_samples=10,
                native_seed=1,
                q00_seed=2,
                gate_bootstrap_seeds={1: 3, 2: 4},
            )


if __name__ == "__main__":
    unittest.main()
