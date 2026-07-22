#!/usr/bin/env python3
"""Static contract for the seeded-conversion sampler."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "jobs" / "templates" / "l3-imbalance2-top3-selfplay-v1.sh"
WRAPPER = ROOT / "jobs" / "prepared" / "l3-imbalance2-seed-clean-20260722" / "ccx33-l3-imbalance2-seed-clean-screen-v1.sh"


class SeedCleanSamplingContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = (ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
        cls.runner = RUNNER.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")

    def test_sample_initial_flag_is_parsed_and_reported(self) -> None:
        self.assertIn('a == "--sample-initial"', self.main)
        self.assertIn('sample_initial = true;', self.main)
        self.assertIn('sample_initial=" << (sample_initial ? "true" : "false")', self.main)

    def test_forced_initial_sample_keeps_normal_filters(self) -> None:
        self.assertIn('(sample_initial && ply == 0)', self.main)
        self.assertIn('&& (!quiet_only || position_quiet);', self.main)
        self.assertIn('generated + static_cast<int>(game_samples.size()) < n', self.main)

    def test_screen_is_small_and_seed_clean(self) -> None:
        subprocess.run(["bash", "-n", str(RUNNER)], check=True)
        subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
        for token in (
            "SEED_CLEAN=1", "GENERATIONS=1", "FRESH=100000",
            "RANDOM_OPEN_PLIES=0", "EXPLORE_EPS=0",
            "WIN_WEIGHT=1 DRAW_WEIGHT=1 LOSS_WEIGHT=1",
        ):
            self.assertIn(token, self.wrapper)
        self.assertIn("--quiet-only --sample-initial", self.runner)
        self.assertIn("pair_flags=()", self.runner)
        self.assertIn("natural_unweighted_wdl", self.runner)
        self.assertIn('timeout "$GEN_SHARD_TIMEOUT"', self.runner)
        self.assertIn('timeout "$EVAL_SHARD_TIMEOUT"', self.runner)


if __name__ == "__main__":
    unittest.main()
