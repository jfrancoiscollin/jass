# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-knob-attribution-v1.sh"


class Context2KnobAttributionTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = TEMPLATE.read_text(encoding="utf-8")

    def test_reuses_certified_curriculum(self) -> None:
        for token in (
            "cpx62-1341-jass-megacorpus-arm-d-fit-v1",
            "20260814T191555Z-18c38a33",
            "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
            "D-c-prior-then-current.pjtw.gz",
        ):
            self.assertIn(token, self.script)

    def test_one_factor_cells_are_preregistered(self) -> None:
        for token in (
            "BASE          8   8    60",
            "BASEBIS       8   8    60",
            "ROP16        16   8    60",
            "EPS16         8  16    60",
            "DECAY120      8   8   120",
            "NODECAY       8   8     0",
            "TOPK3M30      8   8    60    3     30",
            "DEPTH10       8   8    60    0      0    10",
        ):
            self.assertIn(token, self.script)

    def test_matched_rng_and_complete_metadata_contract(self) -> None:
        for token in (
            "--split-selfplay-rngs",
            "split_selfplay_rngs=1",
            "--pair-openings",
            "--sample-meta-format jsm2",
            "--renamespace-nested",
            "BASE_SEED=1618033",
            "REPLICATE_SEED=2718281",
        ):
            self.assertIn(token, self.script)

    def test_attribution_is_diagnostic_and_guarded(self) -> None:
        for token in (
            "l3_context2_activation_census.py compare",
            "max(2*noise,0.05)",
            "relative_draw_shift_vs_base",
            "wdl_side_skew",
            "diagnostic_only':True",
            "fits_run':0",
            "force_games_played':0",
            "frozen_read':False",
            "promotion_authorized':False",
            "automatic_next_job':None",
        ):
            self.assertIn(token, self.script)

    def test_persistent_numpy_is_reused(self) -> None:
        self.assertIn("persistent numeric runtime absent; do not reinstall", self.script)
        self.assertNotIn("pip install", self.script)


if __name__ == "__main__":
    unittest.main()
