#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-contribution-seed-miner-v1.sh"


class ContributionSeedMinerTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_exact_sources(self):
        self.assertIn("cpx62-1409-l3-context2-intervention-corpus-v1/20260818T184956Z-3465ec72", self.text)
        self.assertIn("cpx62-1411-l3-context2-intervention-mapper-screen-v1/20260818T200558Z-9ec9195a", self.text)
        self.assertIn("cpx62-1413-l3-context2-contribution-autopsy-readout-v1/20260818T204712Z-2d6e9599", self.text)

    def test_protocol_is_exact_and_cpx_only(self):
        self.assertIn("MINER_SEED=2026081806", self.text)
        self.assertIn("PER_POOL=4096", self.text)
        self.assertIn('"$(hostname)" = cpx62', self.text)
        self.assertIn('"$(nproc)" -eq 16', self.text)
        self.assertIn("--dump-conditional-context-v2", self.text)
        self.assertIn("([0-9]+[a-z]?)", self.text)
        self.assertIn("seed-miner-v[0-9]+", self.text)

    def test_forbidden_actions_are_absent(self):
        for forbidden in (
            "--gen-data-wdl",
            "fit_pattern",
            "run_jass_gate_bounded",
            "calibrate_vs_scan",
            "frozen_test",
        ):
            self.assertNotIn(forbidden, self.text)

    def test_publishes_six_seed_pools_and_no_continuation(self):
        for pool in (
            "blocked_man",
            "center_presence",
            "king_centrality",
            "king_safe_mobility",
            "legal_capture_option",
            "neutral",
        ):
            self.assertIn(f'"$W/seeds/$pool.jnnw"', self.text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", self.text)
        self.assertIn("SELFPLAY_GENERATED__FALSE", self.text)

    def test_failed_miner_is_self_diagnosing(self):
        self.assertIn("JASS_CONTEXT2_CONTRIBUTION_SEED_MINER_ROOT_CAUSE_READY", self.text)
        self.assertIn("root-cause.json", self.text)
        self.assertIn("ROOT_CAUSE__", self.text)

    def test_persistent_numeric_runtime_provides_exact_solver(self):
        self.assertIn("import numpy,scipy", self.text)
        self.assertIn("from scipy.optimize import milp", self.text)


if __name__ == "__main__":
    unittest.main()
