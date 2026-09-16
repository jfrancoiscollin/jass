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

    def test_execution_remains_blocked_until_g0_preflight_pin(self) -> None:
        pre = self.c["g0_tooling_preflight"]
        if self.c["status"] == "ACTIVE":
            self.assertRegex(pre["attempt_id"], r"^20260916T\d{6}Z-[0-9a-f]{8}$")
            self.assertRegex(pre["code_sha"], r"^[0-9a-f]{40}$")
            self.assertRegex(pre["launch_receipt_sha256"], r"^[0-9a-f]{64}$")
        else:
            self.assertEqual(self.c["status"], "DRAFT_PENDING_G0_TOOLING_PREFLIGHT_PIN")
            self.assertIsNone(pre["attempt_id"])
            self.assertIsNone(pre["code_sha"])
            self.assertIsNone(pre["launch_receipt_sha256"])

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
