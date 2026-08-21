#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "jobs" / "tools" / "l3_replay_b_promotion_readout.py"
SPEC = importlib.util.spec_from_file_location("l3_replay_b_promotion_readout", MODULE_PATH)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class PromotionReadoutTest(unittest.TestCase):
    def _gate(self, *, view: str, seed: int, pattern_a: str = "/tmp/B.pjtw") -> dict:
        scores = [0.75] * 3000
        return {
            "complete": True,
            "n": 6000,
            "wins_a": 4500,
            "draws": 0,
            "wins_b": 1500,
            "rate": 0.75,
            "pairs": 1,
            "nshards": 12,
            "max_parallel": 12,
            "jass_a": "/tmp/jass",
            "jass_b": "/tmp/jass",
            "pattern_a": pattern_a,
            "pattern_b": "/tmp/curriculum.pjtw",
            "search_params_a": ",".join(f"k{i}=0" for i in range(63)),
            "search_params_b": ",".join(f"k{i}=0" for i in range(63)),
            "movetime": 0.1 if view == "native" else None,
            "depth": None if view == "native" else 9,
            "paired_opening": {
                "method": "paired_colour_opening_cluster_bootstrap",
                "n_openings": 3000,
                "games_per_opening": 2,
                "bootstrap_samples": 200000,
                "seed": seed,
                "rate": 0.75,
                "ci_low": 0.74,
                "ci_high": 0.76,
                "probability_rate_gt_half": 1.0,
                "error_draws": 0,
                "per_opening_scores": scores,
            },
        }

    def test_positive_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            protocol = {
                "schema": "jass.l3_replay_b_promotion_force_protocol.v1",
                "candidate": "B_REPLAY25",
                "baseline": "CURRICULUM",
                "openings_per_pool": 3000,
                "bootstrap_samples": 200000,
                "primary_view": "native_movetime_0.1",
                "q00_can_override_native": False,
                "gate_seeds": {
                    "pool1": {"native": 2026082203, "q00": 2026082204},
                    "pool2": {"native": 2026082205, "q00": 2026082206},
                },
                "combined_seeds": {"native": 2026082207, "q00": 2026082208},
            }
            pools = {
                "verdict": "JASS_REPLAY_B_PROMOTION_TWO_FRESH_POOLS_READY",
                "mutually_disjoint": True,
                "all_historical_overlaps_zero": True,
                "historical_exclusion_count": 21,
                "pools": [
                    {"openings": 3000, "sha256": "a" * 64},
                    {"openings": 3000, "sha256": "b" * 64},
                ],
            }
            models = {
                "verdict": "JASS_REPLAY_B_PROMOTION_MODELS_AUTHENTICATED",
                "candidate": {"label": "B_REPLAY25", "model_raw_sha256": "c" * 64},
                "baseline": {"label": "CURRICULUM", "model_raw_sha256": "d" * 64},
            }
            (root / "protocol.json").write_text(json.dumps(protocol))
            (root / "pools.json").write_text(json.dumps(pools))
            (root / "models.json").write_text(json.dumps(models))
            args = [
                "--protocol", str(root / "protocol.json"),
                "--pool-certificate", str(root / "pools.json"),
                "--model-certificate", str(root / "models.json"),
            ]
            for pool in (1, 2):
                for view in ("native", "q00"):
                    path = root / f"pool{pool}-{view}.json"
                    path.write_text(json.dumps(self._gate(
                        view=view, seed=protocol["gate_seeds"][f"pool{pool}"][view]
                    )))
                    args.extend([f"--pool{pool}-{view}", str(path)])
            args.extend(["--out", str(root / "out.json")])

            # The production combine routine deliberately performs 200,000
            # paired bootstrap replicates. Unit tests exercise the surrounding
            # schema/audit/classification contract without reproducing that
            # expensive scientific computation in CI.
            positive = {
                "pool_rates": [0.75, 0.75],
                "pool_standard_errors": [0.001, 0.001],
                "inter_pool_z": 0.0,
                "inter_pool_compatible_95": True,
                "rate": 0.75,
                "elo_indicative": 190.8485,
                "ci_low": 0.74,
                "ci_high": 0.76,
                "probability_rate_gt_half": 1.0,
                "bootstrap_samples": 200000,
                "bootstrap_seed": 0,
                "openings": 6000,
                "games": 12000,
            }
            with mock.patch.object(mod, "combine", side_effect=[positive, positive]):
                self.assertEqual(mod.main(args), 0)

            result = json.loads((root / "out.json").read_text())
            self.assertEqual(
                result["verdict"],
                "JASS_REPLAY25_B_VS_CURRICULUM_PROMOTION_GATE_PASSED",
            )
            self.assertTrue(result["promotion_review_recommended"])
            self.assertFalse(result["promotion_authorized"])
            self.assertEqual(result["games_total"], 24000)

    def test_model_assignment_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "gate.json"
            path.write_text(json.dumps(self._gate(
                view="native", seed=7, pattern_a="/tmp/A.pjtw"
            )))
            with self.assertRaisesRegex(ValueError, "model assignment drift"):
                mod.audit_gate(
                    path, view="native", pool_index=1, openings=3000,
                    bootstrap_samples=200000, bootstrap_seed=7,
                )

    def test_classification_boundaries(self) -> None:
        base = {
            "pool_rates": [0.51, 0.52],
            "inter_pool_compatible_95": True,
            "ci_low": 0.501,
            "ci_high": 0.53,
            "probability_rate_gt_half": 0.99,
        }
        self.assertEqual(mod.classify(base), "ESTABLISHED_POSITIVE")
        negative = dict(base, pool_rates=[0.49, 0.48], ci_low=0.47, ci_high=0.499,
                        probability_rate_gt_half=0.01)
        self.assertEqual(mod.classify(negative), "ESTABLISHED_NEGATIVE")
        inconclusive = dict(base, ci_low=0.495, probability_rate_gt_half=0.80)
        self.assertEqual(mod.classify(inconclusive), "NOT_ESTABLISHED")


if __name__ == "__main__":
    unittest.main()
