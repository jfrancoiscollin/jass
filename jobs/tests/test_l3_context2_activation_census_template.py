# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-activation-census100k-v1.sh"


class Context2ActivationCensusTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = TEMPLATE.read_text(encoding="utf-8")

    def test_exact_complete_paired_game_population(self) -> None:
        for token in (
            "SAMPLE_GAMES=100000",
            "SAMPLE_OPENINGS=50000",
            "SAMPLE_SEED=2026081701",
            "--games-per-opening 2",
            "complete_opening_groups",
            "--expected-games \"$SAMPLE_GAMES\"",
            "--expected-openings \"$SAMPLE_OPENINGS\"",
        ):
            self.assertIn(token, self.script)

    def test_uses_authenticated_general_selfplay_source(self) -> None:
        for token in (
            "home-1044-l3-pure-hard-replay-large-source-v1",
            "20260729T070032Z-477da64d",
            "SOURCE_RECORDS=40000000",
            "split_selfplay_rngs",
            "pair_openings",
            "post_drawn_root_fix",
            "data_raw_sha256",
            "meta_raw_sha256",
        ):
            self.assertIn(token, self.script)

    def test_measures_banks_and_reconstructed_base(self) -> None:
        for token in (
            "--dump-conditional-context-v2",
            "l3_context2_activation_census.py analyze",
            "--material-threshold 1e-6",
            "--rare-threshold 1e-3",
            "all_30_channels_materially_active",
            "all_15_base_signals_materially_active",
            "recomposition_max_absolute_error",
        ):
            self.assertIn(token, self.script)

    def test_is_read_only_and_reuses_persistent_numpy(self) -> None:
        self.assertIn("persistent numeric runtime absent; do not reinstall", self.script)
        self.assertNotIn("pip install", self.script)
        for token in (
            "selfplay_generated':False",
            "fits_run':0",
            "force_games_played':0",
            "frozen_read':False",
            "promotion_authorized':False",
            "automatic_next_job':None",
        ):
            self.assertIn(token, self.script)


if __name__ == "__main__":
    unittest.main()
