#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import unittest

import numpy as np

from jobs.tests import test_l3_curriculum_error_trace_residual_training as fixtures
from jobs.tools import l3_curriculum_error_trace_residual_feature_audit as target
from jobs.tools import l3_curriculum_error_trace_residual_training as training
from jobs.tools import l3_curriculum_search_error_atlas as atlas


def _training_inputs(pairs: dict) -> tuple[dict, dict, dict, dict, dict]:
    registration = fixtures._preregistration(pairs)
    gate_fit, manifest = training.split_profiles(pairs, registration)
    gate_digest = hashlib.sha256(target._canonical(gate_fit)).hexdigest()
    prereg_digest = hashlib.sha256(target._canonical(registration)).hexdigest()
    report = {
        "schema": training.SCHEMA,
        "verdict": training.READY,
        "passed": True,
        "champion_sha256": "champion",
        "jass_sha256": "jass",
        "search_params_sha256": "search",
        "gate_fit_pairs_sha256": gate_digest,
        "preregistration_sha256": prereg_digest,
        "gate_fit_action_value_reads": len(gate_fit["pairs"]) * 2,
        "feature_audit_action_value_reads": 0,
        "outer_confirm_action_value_reads": 0,
        "pattern_eval_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }
    placeholder = {
        "mean": [0.0] * 20,
        "rms": [1.0] * 20,
        "coef": [0.0] * 20,
    }
    model = {
        "schema": training.MODEL_SCHEMA,
        "authorized_for_feature_audit": True,
        "authorized_for_production": False,
        "promotion_authorized": False,
        "fixed_architecture": registration["fixed_architecture"],
        "selected_threshold_cp": 5.0,
        "aligned_model": placeholder,
        "shuffled_model": placeholder,
        "champion_sha256": "champion",
        "jass_sha256": "jass",
        "search_params_sha256": "search",
        "gate_fit_pairs_sha256": gate_digest,
        "preregistration_sha256": prereg_digest,
    }
    return registration, gate_fit, manifest, report, model


def _audit_shards(pairs: dict) -> list[dict]:
    digest = hashlib.sha256(target._canonical(pairs)).hexdigest()
    rows = []
    for pair in pairs["pairs"]:
        values = {
            fixtures.QUIET: {"root_cp": 0.0},
            fixtures.CAPTURE: {"root_cp": 100.0},
        }
        control = {
            fixtures.QUIET: {"root_cp": 0.0},
            fixtures.CAPTURE: {"root_cp": 0.0},
        }
        rows.append(
            {
                "pair_id": pair["pair_id"],
                "split": pair["split"],
                "error": {"action_values": values},
                "control": {"action_values": control},
            }
        )
    return [
        {
            "schema": atlas.SCHEMA_ATLAS_SHARD,
            "pairs_sha256": digest,
            "champion_sha256": "champion",
            "jass_sha256": "jass",
            "search_params_sha256": "search",
            "shard": shard,
            "nshards": 16,
            "max_pairs": 0,
            "rows": [row for row in rows if int(row["pair_id"]) % 16 == shard],
        }
        for shard in range(16)
    ]


class TraceResidualFeatureAuditTests(unittest.TestCase):
    def test_materialization_reproduces_sealed_split_without_targets(self):
        pairs = fixtures._pairs()
        registration, gate_fit, manifest, report, model = _training_inputs(pairs)

        audit_pairs, certificate = target.materialize(
            pairs, registration, manifest, gate_fit, report, model
        )

        self.assertEqual(audit_pairs["subset"], "feature_audit")
        self.assertEqual(audit_pairs["matched_pairs"], len(manifest["feature_audit_pair_ids"]))
        self.assertGreaterEqual(audit_pairs["matched_pairs"], 24)
        self.assertEqual(certificate["overlap"], {"opening_id": 0, "game_uid": 0, "exact_state_key": 0})
        self.assertEqual(certificate["feature_audit_action_value_reads"], 0)
        self.assertEqual(certificate["outer_confirm_action_value_reads"], 0)
        self.assertEqual(certificate["residual_fits"], 0)

    def test_materialization_rejects_any_split_or_training_identity_drift(self):
        pairs = fixtures._pairs()
        registration, gate_fit, manifest, report, model = _training_inputs(pairs)
        drifted = copy.deepcopy(manifest)
        drifted["feature_audit_pair_ids"] = drifted["feature_audit_pair_ids"][:-1]
        with self.assertRaisesRegex(ValueError, "split manifest drift"):
            target.materialize(pairs, registration, drifted, gate_fit, report, model)

        model["authorized_for_feature_audit"] = False
        with self.assertRaisesRegex(ValueError, "authorization drift"):
            target.materialize(pairs, registration, manifest, gate_fit, report, model)

    def test_fixed_aligned_model_passes_synthetic_oos_without_refit(self):
        pairs = fixtures._pairs()
        registration, gate_fit, manifest, report, model = _training_inputs(pairs)
        audit_pairs, _ = target.materialize(pairs, registration, manifest, gate_fit, report, model)
        profile = audit_pairs["pairs"][0]["error"]
        features, _, _ = training._paired_features(profile)
        delta = features[fixtures.CAPTURE] - features[fixtures.QUIET]
        coefficient = 50.0 * delta / float(delta @ delta)
        model["aligned_model"] = {
            "mean": np.zeros_like(delta).tolist(),
            "rms": np.ones_like(delta).tolist(),
            "coef": coefficient.tolist(),
        }
        model["shuffled_model"] = {
            "mean": np.zeros_like(delta).tolist(),
            "rms": np.ones_like(delta).tolist(),
            "coef": np.zeros_like(delta).tolist(),
        }

        result = target.audit(
            registration, report, model, audit_pairs, _audit_shards(audit_pairs)
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["verdict"], target.READY)
        self.assertEqual(result["residual_fits"], 0)
        self.assertEqual(result["outer_confirm_action_value_reads"], 0)
        self.assertTrue(result["outer_confirm_authorized"])
        self.assertFalse(result["production_rule_authorized"])
        self.assertGreater(result["aligned"]["error_improvement"]["mean"], 0.0)
        self.assertGreater(
            result["aligned_minus_shuffled"]["paired_error_minus_control"]["ci95"][0],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
