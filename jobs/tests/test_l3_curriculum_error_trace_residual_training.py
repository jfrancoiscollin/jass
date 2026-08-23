#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import unittest

import numpy as np

from jobs.tools import l3_curriculum_error_trace_proxy_preregistration as prereg
from jobs.tools import l3_curriculum_error_trace_residual_training as target
from jobs.tools import l3_curriculum_search_error_atlas as atlas


QUIET = "1-2"
CAPTURE = "3x4 captures=7"


def _profile(index: int, *, max_spread: float = 100.0) -> dict:
    capture_scores = {
        6: -max_spread,
        7: -0.60 * max_spread,
        8: -0.30 * max_spread,
        9: -0.20 * max_spread,
    }
    original = {
        str(depth): {
            "moves": [
                {"action": QUIET, "score": 0.0},
                {"action": CAPTURE, "score": capture_scores[depth]},
            ]
        }
        for depth in prereg.ranker.FEATURE_DEPTHS
    }
    image = {
        depth: {
            "moves": [
                {"action": atlas._mapped_image_action(QUIET), "score": row["moves"][0]["score"]},
                {"action": atlas._mapped_image_action(CAPTURE), "score": row["moves"][1]["score"]},
            ]
        }
        for depth, row in original.items()
    }
    return {
        "source": {
            "opening_id": f"opening-{index}",
            "game_uid": f"game-{index}",
            "exact_state_key": f"state-{index}",
        },
        "trace": {"original": {"depths": original}, "exact_image": {"depths": image}},
    }


def _pairs(discovery: int = 128, confirm: int = 16) -> dict:
    rows = []
    for index in range(discovery + confirm):
        rows.append(
            {
                "pair_id": index,
                "split": "discovery" if index < discovery else "confirm",
                "error": _profile(index * 2),
                "control": _profile(index * 2 + 1),
            }
        )
    return {
        "schema": atlas.SCHEMA_PAIRS,
        "matching_passed": True,
        "matched_pairs": len(rows),
        "pairs_by_split": {"discovery": discovery, "confirm": confirm},
        "pairs": rows,
    }


def _preregistration(pairs: dict) -> dict:
    return {
        "schema": prereg.SCHEMA,
        "verdict": prereg.READY,
        "passed": True,
        "coverage_source": {
            "pairs_sha256": hashlib.sha256(target._canonical(pairs)).hexdigest(),
        },
        "champion_sha256": "champion",
        "jass_sha256": "jass",
        "search_params_sha256": "search",
        "fixed_architecture": {
            "family": "canonical_paired_trace_pairwise_ridge_residual_with_fixed_variability_gate",
            "alpha": prereg.ALPHA,
            "correction_cap_cp": prereg.CAP_CP,
            "risk_gate": {
                "proxy": prereg.SELECTED_PROXY,
                "lower_open": prereg.LOWER_OPEN,
                "upper_closed": prereg.UPPER_CLOSED,
            },
        },
        "validation_action_value_reads": 0,
        "outer_confirm_action_value_reads": 0,
        "diagnostic_fits": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }


class TraceResidualTrainingTests(unittest.TestCase):
    def test_split_is_target_free_reproducible_and_leak_free(self):
        pairs = _pairs()
        registration = _preregistration(pairs)

        reduced, manifest = target.split_profiles(pairs, registration)
        again, again_manifest = target.split_profiles(pairs, registration)

        self.assertEqual(reduced, again)
        self.assertEqual(manifest, again_manifest)
        self.assertEqual(reduced["subset"], "gate_fit")
        self.assertEqual(reduced["pairs_by_split"]["confirm"], 0)
        self.assertGreaterEqual(reduced["matched_pairs"], 64)
        self.assertGreaterEqual(len(manifest["feature_audit_pair_ids"]), 24)
        self.assertEqual(manifest["overlap"], {"opening_id": 0, "game_uid": 0, "exact_state_key": 0})
        self.assertEqual(manifest["action_value_reads"], 0)
        self.assertEqual(manifest["outer_confirm_profile_rows_examined"], 0)

    def test_split_rejects_source_identity_or_sealed_counter_drift(self):
        pairs = _pairs()
        registration = _preregistration(pairs)
        drifted = copy.deepcopy(pairs)
        drifted["pairs"][0]["error"]["trace"]["original"]["depths"]["6"]["moves"][0]["score"] = 1.0
        with self.assertRaisesRegex(ValueError, "source pairs identity drift"):
            target.split_profiles(drifted, registration)

        registration["outer_confirm_action_value_reads"] = 1
        with self.assertRaisesRegex(ValueError, "counter drift"):
            target.split_profiles(pairs, registration)

    def test_decision_intervenes_inside_gate_and_is_identical_outside(self):
        inside = _profile(1, max_spread=100.0)
        features, original_scores, image_scores = target._paired_features(inside)
        delta = features[CAPTURE] - features[QUIET]
        coefficient = 50.0 * delta / float(delta @ delta)
        model = {
            "mean": np.zeros_like(delta).tolist(),
            "rms": np.ones_like(delta).tolist(),
            "coef": coefficient.tolist(),
        }
        state = {
            "profile": inside,
            "features": features,
            "original_scores": original_scores,
            "image_scores": image_scores,
            "values": {QUIET: 0.0, CAPTURE: 100.0},
        }
        repaired = target._decision(state, model, threshold=5.0)
        self.assertTrue(repaired["eligible"])
        self.assertTrue(repaired["intervention"])
        self.assertEqual(repaired["improvement_cp"], 100.0)

        outside = _profile(2, max_spread=200.0)
        outside_features, outside_original, outside_image = target._paired_features(outside)
        state.update(
            profile=outside,
            features=outside_features,
            original_scores=outside_original,
            image_scores=outside_image,
        )
        abstained = target._decision(state, model, threshold=0.0)
        self.assertFalse(abstained["eligible"])
        self.assertFalse(abstained["intervention"])
        self.assertTrue(abstained["outside_gate_bit_identical"])
        self.assertTrue(abstained["abstention_bit_identical"])
        self.assertEqual(abstained["improvement_cp"], 0.0)

    def test_loader_rejects_action_targets_in_gate_profiles(self):
        pairs = _pairs(discovery=1, confirm=0)
        pairs["subset"] = "gate_fit"
        pairs["pairs"][0]["error"]["action_values"] = {QUIET: 0.0}
        with self.assertRaisesRegex(ValueError, "contain action targets"):
            target._load_rows(pairs, [])


if __name__ == "__main__":
    unittest.main()
