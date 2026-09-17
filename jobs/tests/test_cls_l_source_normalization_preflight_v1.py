from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from jobs.tools import cls_l_normalization_preflight as stage

ROOT = Path(__file__).resolve().parents[2]


class CLSLSourceNormalizationPreflightV1Tests(unittest.TestCase):
    def test_frozen_current2m_and_recipe_constants(self):
        self.assertEqual(stage.RECORDS, 2_000_000)
        self.assertEqual(stage.TRAIN_RECORDS, 1_800_796)
        self.assertEqual(stage.HOLDOUT_RECORDS, 199_204)
        self.assertEqual(stage.EXTRAS, 120)
        self.assertEqual(stage.CHUNK, 20_000)
        self.assertEqual(stage.L2, 1e-5)
        self.assertEqual(stage.FOLD, "exact")
        self.assertTrue(stage.TEMPO_STAGE)
        self.assertEqual(stage.PRUNE_MIN_VISITS, 1)
        self.assertEqual(stage.TERMINAL, "CLS_L_SOURCE_NORMALIZATION_PREFLIGHT_READY_V1")

    def test_wdl_projection_is_black_pov_probability(self):
        wdl = np.asarray([1, 1, 0, -1, -1], dtype=np.int8)
        stm = np.asarray([1, 0, 1, 1, 0], dtype=np.uint8)
        got = stage.wdl_black_probability(wdl, stm)
        np.testing.assert_array_equal(got, np.asarray([1.0, 0.0, 0.5, 0.0, 1.0]))

    def test_local_target_validation_fails_closed(self):
        old_chunk = stage.CHUNK
        stage.CHUNK = 2
        try:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "targets.npy"
                np.save(p, np.asarray([0.0, 0.5, 1.0], dtype=np.float32), allow_pickle=False)
                values = stage.validate_local_targets(p, 3)
                self.assertEqual(values.dtype, np.dtype(np.float32))
                bad = Path(d) / "bad.npy"
                np.save(bad, np.asarray([0.0, 1.1, 0.5], dtype=np.float32), allow_pickle=False)
                with self.assertRaisesRegex(stage.PreflightError, "local_target_range"):
                    stage.validate_local_targets(bad, 3)
        finally:
            stage.CHUNK = old_chunk

    def test_shell_pins_exact_historical_sources_and_never_fits(self):
        shell = (ROOT / "jobs/templates/l3-cls-l-source-normalization-preflight-v1.sh").read_text()
        self.assertIn('ABC_JOB="cpx62-1340-jass-megacorpus-comparative-fit-v1"', shell)
        self.assertIn('ABC_ATTEMPT="20260814T123246Z-2ce07222"', shell)
        self.assertIn('TURNOVER_JOB="home-0977-l3-pure-turnover1to1-train-v1"', shell)
        self.assertIn('TURNOVER_ATTEMPT="20260726T071254Z-336bb984"', shell)
        self.assertIn('CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"', shell)
        self.assertIn('CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"', shell)
        self.assertIn('CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"', shell)
        self.assertIn('--holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED"', shell)
        self.assertIn('cmp "$W/current-manifest-reproduced.json" "$IN/current-manifest.json"', shell)
        self.assertIn("cls_l_normalization_preflight.py", shell)
        self.assertNotIn("train_stream.py --", shell)
        self.assertNotIn("--max-iter", shell)

    def test_profile_is_zero_effect_rehearsal(self):
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-l-source-normalization-preflight-v1.json").read_text())
        self.assertEqual(profile["campaign"], "cls-v1")
        self.assertEqual(profile["stage"], "cls-l-source-normalization-preflight-v1")
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(value == 0 for value in profile["rehearsal_max_effects"].values()))
        self.assertIn("normalization-receipt.json", profile["evidence_outputs"])
        self.assertIn("source-authentication.json", profile["evidence_outputs"])

    def test_merged_cls_l_contract_is_active(self):
        contract = json.loads((ROOT / "docs/experiments/L3_CLS_L_OBJECTIVE_ATTRIBUTION_V1_20260916.json").read_text())
        self.assertEqual(contract["status"], "ACTIVE")
        self.assertEqual(contract["arms"]["MIXED"]["lambda_normalized_gradient"], 0.5)
        self.assertEqual(contract["arms"]["MIXED"]["norm_source"], "TRAIN_ONLY")
        self.assertEqual(contract["parent"]["sha256"], "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1")


if __name__ == "__main__":
    unittest.main()
