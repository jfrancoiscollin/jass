#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "jobs/templates/l3-pure-p1-runner-v1.sh"
WRAPPER = ROOT / "jobs/prepared/l3-p1-20260719/cpx62-l3-p1-frozen-v1.sh"
RECIPE = ROOT / "jobs/prepared/l3-p1-20260719/RECIPE.md"


class L3P1PreparedContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = RUNNER.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")
        cls.recipe = RECIPE.read_text(encoding="utf-8")

    def test_frozen_long_lineage_shape(self) -> None:
        for token in (
            'NGEN="${NGEN:-4}"',
            'FRESH="${FRESH:-500000}"',
            'PLAY_DEPTH="${PLAY_DEPTH:-8}"',
            '[ "$NGEN" -eq 4 ]',
            '[ "$FRESH" -eq 500000 ]',
            '[ "$PLAY_DEPTH" -eq 8 ]',
            '"play_depth_schedule"',
            '"complete_p1_training"',
        ):
            self.assertIn(token, self.runner)
        self.assertNotIn('PLAY_DEPTH=10', self.runner)

    def test_scientific_recipe_is_baseline_only(self) -> None:
        for token in (
            '--wdl-zero-score',
            '--search-params-play "$L3_SEARCH_PARAMS"',
            '--pair-openings',
            '--drop-plycap',
            'FRONTIER_FRAC="${FRONTIER_FRAC:-0}"',
            '[ "$FRONTIER_FRAC" -eq 0 ]',
            '"external_teacher_inputs": 0',
            '"geometry": "8cf"',
            '"fresh_corpus_only": True',
        ):
            self.assertIn(token, self.runner)
        self.assertNotIn("--seed-file", self.runner)
        self.assertNotIn("--teacher", self.runner)
        self.assertNotIn("32cf", self.runner)

    def test_q00_full_fingerprint(self) -> None:
        match = re.search(r'L3_BASE_SEARCH_PARAMS="([^"]+)"', self.runner)
        self.assertIsNotNone(match)
        params = dict(token.split("=", 1) for token in match.group(1).split(","))
        self.assertEqual(63, len(params))
        self.assertEqual("0", params["qs_forcing_depth"])
        self.assertEqual("0", params["qs_promo_depth"])
        self.assertIn(
            'qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,'
            'qs_forcing_depth=0,qs_promo_depth=0',
            self.runner,
        )

    def test_wrapper_is_cpx62_launch_ready_but_sha_pinned_externally(self) -> None:
        for token in (
            ': "${EXPECTED_CODE_SHA:?',
            "export FULL_RUN_APPROVED=1",
            "export SCIENTIFIC_GO=1",
            "export NGEN=4 FRESH=500000 NSHARDS=8 PAR_GEN=8 PLAY_DEPTH=8",
            "exec bash jobs/templates/l3-pure-p1-runner-v1.sh",
        ):
            self.assertIn(token, self.wrapper)
        self.assertNotIn("__PIN_", self.wrapper)

    def test_no_automatic_promotion(self) -> None:
        self.assertIn('"automatic_next_job": None', self.runner)
        self.assertIn('"promotion_authorized": False', self.runner)
        self.assertIn("aucune promotion automatique", self.recipe.lower())


if __name__ == "__main__":
    unittest.main()
