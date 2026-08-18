#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-contribution-balanced-pilot-v1.sh"


class ContributionBalancedPilotTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_exact_seed_attempt_and_parent(self):
        for token in (
            "cpx62-1414b-l3-context2-contribution-seed-miner-v2/20260818T222026Z-f614cb53",
            "f614cb533b1f39e131f577069018ea5a866274e6",
            "cpx62-1341-jass-megacorpus-arm-d-fit-v1",
            "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
        ):
            self.assertIn(token, self.text)

    def test_exact_six_cell_protocol(self):
        for token in (
            "blocked_man center_presence king_centrality king_safe_mobility legal_capture_option neutral",
            "PREFLIGHT_RECORDS=10000",
            "CELL_RECORDS=100000",
            "FRESH_SEED=2026081807",
            "PRODUCERS=12",
            "MAX_BUDGET_MIN=45",
            "--seed-frac 100",
            "--explore-topk 3",
            "--explore-margin 30",
            "--random-open-plies 8",
            "--explore-eps 8",
            "--explore-decay-plies 60",
        ):
            self.assertIn(token, self.text)

    def test_preflight_is_excluded_and_fail_closed(self):
        self.assertIn("exact-10k-per-cell-preflight", self.text)
        self.assertIn("preflight budget exceeded", self.text)
        self.assertIn("--expected-per-cell \"$PREFLIGHT_RECORDS\"", self.text)
        self.assertIn("--expected-per-cell \"$CELL_RECORDS\"", self.text)
        self.assertIn("context2-contribution-balanced-600k.jnnw", self.text)

    def test_forbidden_actions_absent(self):
        for token in (
            "train_stream.py",
            "fit_pattern",
            "run_jass_gate_bounded",
            "frozen_test",
            "promotion.json",
            "pip install",
        ):
            self.assertNotIn(token, self.text)
        for marker in (
            "FITS_RUN__0",
            "FORCE_GAMES_PLAYED__0",
            "FROZEN_READ__FALSE",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(marker, self.text)


if __name__ == "__main__":
    unittest.main()
