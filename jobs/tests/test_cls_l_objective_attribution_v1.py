from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/experiments/L3_CLS_L_OBJECTIVE_ATTRIBUTION_V1_20260916.json"


class CLSLObjectiveAttributionV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.c = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_one_factor_three_levels_only(self) -> None:
        amend = self.c["one_axis_amendment"]
        self.assertTrue(amend["enabled"])
        self.assertEqual(amend["varied_factor"], "learning_objective")
        self.assertEqual(amend["levels"], ["LOCAL", "WDL", "MIXED"])
        self.assertTrue(amend["all_other_axes_fixed"])
        self.assertTrue(amend["fourth_arm_forbidden"])

    def test_parent_and_distribution_are_frozen(self) -> None:
        self.assertEqual(
            self.c["parent"]["sha256"],
            "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
        )
        dist = self.c["distribution"]
        self.assertEqual(dist["records"], 2_000_000)
        self.assertEqual(dist["holdout_mod"], 10)
        self.assertEqual(dist["split_seed"], 577215)
        self.assertEqual(dist["new_selfplay"], 0)

    def test_recipe_is_identical_across_arms(self) -> None:
        recipe = self.c["common_recipe"]
        self.assertEqual(recipe["architecture"], "8cf_exact_fold_tempo_120_extras")
        self.assertEqual(recipe["extras"], 120)
        self.assertEqual(recipe["l2"], 1e-5)
        self.assertEqual(recipe["max_iterations"], 2000)
        self.assertEqual(recipe["lbfgs_maxcor"], 20)
        self.assertEqual(recipe["lbfgs_gtol"], 1e-4)
        self.assertFalse(recipe["holdout_early_stopping"])

    def test_mixed_normalization_is_train_only_and_lambda_frozen(self) -> None:
        mixed = self.c["arms"]["MIXED"]
        self.assertEqual(mixed["lambda_normalized_gradient"], 0.5)
        self.assertEqual(mixed["norm_source"], "TRAIN_ONLY")
        self.assertEqual(mixed["normalization_point"], "projected_CURRICULUM_w0")
        self.assertTrue(mixed["holdout_for_norm_forbidden"])
        self.assertTrue(mixed["lambda_sweep_forbidden"])

    def test_execution_is_active_only_with_exact_green_g0_preflight_pin(self) -> None:
        self.assertEqual(self.c["status"], "ACTIVE")
        pre = self.c["g0_tooling_preflight"]
        self.assertEqual(pre["job_id"], "cpx62-2018-l3-cls-g0-runtime-tooling-preflight-v3")
        self.assertEqual(pre["attempt_id"], "20260917T001938Z-ad151a09")
        self.assertEqual(pre["code_sha"], "ad151a0961a077e5c95a5503a8ee734f5c4cf0b6")
        self.assertEqual(
            pre["launch_receipt_sha256"],
            "887f9f46adc3bf2cd014dd3a5cd8361ebe8c6ad84833f14099beba3e1e165d52",
        )
        self.assertEqual(pre["required_terminal"], "CLS_G0_RUNTIME_TOOLING_PREFLIGHT_READY_V1")
        self.assertTrue(pre["required_identity_pass"])
        self.assertEqual(pre["required_trace_parity_mismatches"], 0)
        self.assertEqual(pre["authenticated_state"], "completed")
        self.assertEqual(pre["authenticated_exit_code"], 0)
        self.assertTrue(pre["authenticated_g0_identity_pass"])
        self.assertEqual(pre["authenticated_trace_parity_mismatches"], 0)
        self.assertEqual(pre["authenticated_target_reads"], 0)
        self.assertEqual(pre["authenticated_fits"], 0)
        self.assertEqual(pre["authenticated_strength_games"], 0)
        self.assertEqual(pre["authenticated_alpha_spent"], 0)
        self.assertEqual(pre["authenticated_promotions"], 0)
        self.assertEqual(pre["authenticated_bakes"], 0)

    def test_no_proxy_can_promote(self) -> None:
        fit = self.c["fit_boundary"]
        downstream = self.c["downstream"]
        self.assertEqual(fit["confirmation_reads"], 0)
        self.assertEqual(fit["strength_games"], 0)
        self.assertEqual(fit["alpha_spent"], 0)
        self.assertFalse(fit["promotion_authorized"])
        self.assertFalse(fit["bake_authorized"])
        self.assertTrue(downstream["strength_required_for_continuation"])
        self.assertFalse(downstream["automatic_promotion"])


if __name__ == "__main__":
    unittest.main()
