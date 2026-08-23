#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest
from unittest import mock

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_anchored_local_refit as anchored
from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_audit as target


def _decision(pair_id: int, pool: str, *, candidate: bool) -> dict:
    changed_control = candidate and pair_id < 20
    return {
        "pair_id": pair_id,
        "source_pool": pool,
        "error": {
            "improvement_cp": 10.0 if candidate else 0.0,
            "intervention": True,
            "action": "new" if candidate else "old",
            "predicted_advantage_cp": 10.0 if candidate else 0.0,
            "realized_gain_cp": 10.0 if candidate else 0.0,
            "anchor_symmetry": True,
            "aligned_symmetry": True,
            "outside_gate_bit_identical": True,
        },
        "control": {
            "improvement_cp": 0.0,
            "intervention": changed_control,
            "action": "new" if changed_control else None,
            "predicted_advantage_cp": 0.0 if changed_control else None,
            "realized_gain_cp": 0.0 if changed_control else None,
            "anchor_symmetry": True,
            "aligned_symmetry": True,
            "outside_gate_bit_identical": True,
        },
    }


def _model() -> dict:
    width = len(ranker.FEATURE_NAMES)
    base = [1.0] * width
    coefficient = base.copy()
    coefficient[0] = 1.1
    coefficient[1] = 1.1
    return {
        "schema": anchored.MODEL_SCHEMA,
        "feature_names": list(ranker.FEATURE_NAMES),
        "mean": [0.0] * width,
        "rms": [1.0] * width,
        "base_coef": base,
        "coef": coefficient,
        "support_indices": [0, 1],
        "support_names": list(ranker.FEATURE_NAMES[:2]),
        "support_sha256": "a" * 64,
        "delta": [0.1, 0.1],
        "identities": {
            "champion_sha256": "champion",
            "jass_sha256": "jass",
            "search_params_sha256": "search",
        },
        "authorized_for_oos_audit": True,
        "authorized_for_strength": False,
        "authorized_for_promotion": False,
    }


def _fit_report(model: dict) -> dict:
    return {
        "schema": target.FIT_TERMINAL_SCHEMA,
        "verdict": anchored.READY,
        "passed": True,
        "oos_labels_used_for_fit": False,
        "oos_availability_preregistration_authorized": True,
        "strength_gate_authorized": False,
        "failed_gates": [],
        "gates": {"all": True},
        "model_sha256": target._digest(model),
        "support": {"support_sha256": model["support_sha256"]},
        "model_candidates_fit": 1,
        "residual_production_fits": 1,
        "pattern_eval_fits": 0,
        "oos_reads": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }


def _proof() -> dict:
    return {
        "endgame_interventions": 0,
        "endgame_decisions_bit_identical_to_anchor": True,
        "non_endgame_decisions_bit_identical_to_frozen_residual": True,
    }


class AnchoredLocalRefitOosAuditTests(unittest.TestCase):
    def test_strict_incremental_pass_authorizes_only_strength_preregistration(self) -> None:
        rows = [
            {"pair_id": index, "source_pool": "pool1" if index < 300 else "pool2"}
            for index in range(600)
        ]
        baseline = [
            _decision(index, row["source_pool"], candidate=False)
            for index, row in enumerate(rows)
        ]
        candidate = [
            _decision(index, row["source_pool"], candidate=True)
            for index, row in enumerate(rows)
        ]
        model = _model()
        with (
            mock.patch.object(target, "_run_rule", side_effect=[(baseline, _proof()), (candidate, _proof())]),
            mock.patch.object(target.prereg, "OOS_BOOTSTRAP_SAMPLES", 2_000),
        ):
            report = target.audit_rows(
                rows, _fit_report(model), model, champion_sha256="champion"
            )

        self.assertEqual(report["verdict"], target.READY)
        self.assertEqual(report["incremental_metrics"]["error_decision_changes"], 600)
        self.assertEqual(report["incremental_metrics"]["control_decision_changes"], 20)
        self.assertTrue(report["two_pool_strength_gate_preregistration_authorized"])
        self.assertFalse(report["promotion_authorized"])
        self.assertFalse(report["automatic_continuation"])

    def test_no_incremental_changes_fails_scientifically(self) -> None:
        rows = [
            {"pair_id": index, "source_pool": "pool1" if index < 300 else "pool2"}
            for index in range(600)
        ]
        decisions = [
            _decision(index, row["source_pool"], candidate=False)
            for index, row in enumerate(rows)
        ]
        model = _model()
        with (
            mock.patch.object(target, "_run_rule", side_effect=[(decisions, _proof()), (copy.deepcopy(decisions), _proof())]),
            mock.patch.object(target.prereg, "OOS_BOOTSTRAP_SAMPLES", 500),
        ):
            report = target.audit_rows(
                rows, _fit_report(model), model, champion_sha256="champion"
            )

        self.assertEqual(report["verdict"], target.NOT_ESTABLISHED)
        self.assertFalse(report["two_pool_strength_gate_preregistration_authorized"])
        self.assertIn("error_decision_changes_at_least_20", report["failed_gates"])

    def test_pattern_eval_hash_drift_fails_identity_gate(self) -> None:
        rows = [
            {"pair_id": index, "source_pool": "pool1" if index < 300 else "pool2"}
            for index in range(600)
        ]
        decisions = [
            _decision(index, row["source_pool"], candidate=False)
            for index, row in enumerate(rows)
        ]
        model = _model()
        with (
            mock.patch.object(target, "_run_rule", side_effect=[(decisions, _proof()), (copy.deepcopy(decisions), _proof())]),
            mock.patch.object(target.prereg, "OOS_BOOTSTRAP_SAMPLES", 100),
        ):
            report = target.audit_rows(
                rows, _fit_report(model), model, champion_sha256="wrong"
            )
        self.assertFalse(report["identity"]["pattern_eval_sha256_identical"])
        self.assertFalse(report["gates"]["identity_guards_all_pass"])


if __name__ == "__main__":
    unittest.main()
