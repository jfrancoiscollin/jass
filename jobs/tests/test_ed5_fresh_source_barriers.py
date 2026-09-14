from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class Ed5FreshSourceBarrierTests(unittest.TestCase):
    def text(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def profile(self, name: str) -> dict:
        return json.loads(self.text(f"jobs/launch_profiles/{name}"))

    def test_w_seed_and_information_boundary_are_frozen(self):
        text = self.text("jobs/tools/ed5_fresh_w_source_stage.py")
        self.assertIn("PRIMARY = 202609140502", text)
        self.assertIn("RESERVE = 202609140512", text)
        self.assertIn("if primary_overlap:", text)
        self.assertIn('"target_reads": 0', text)
        self.assertIn('"scan_searches": 0', text)
        self.assertIn('"jass_searches": 0', text)
        self.assertIn('"fits": 0', text)
        self.assertIn('"alpha_spent": 0', text)
        self.assertIn("PRODUCTION_OPENINGS", text)
        self.assertIn("PRODUCTION_POSITIONS", text)

    def test_s_seed_and_collision_only_reserve_are_frozen(self):
        text = self.text("jobs/tools/ed5_fresh_s_source_stage.py")
        self.assertIn("PRIMARY = 202609140503", text)
        self.assertIn("RESERVE = 202609140513", text)
        self.assertIn("reserve_used = bool(d_overlap or w_overlap)", text)
        self.assertIn('"confirmation_roots": 512 if mode == "production" else 16', text)
        self.assertIn('"target_reads": 0', text)
        self.assertIn('"scan_searches": 0', text)
        self.assertIn('"jass_searches": 0', text)

    def test_disjointness_binds_known_consumed_ed4_digests(self):
        text = self.text("jobs/tools/ed5_fresh_dws_disjointness_stage.py")
        for digest in (
            "6a3194f0ca6d0db95a87d3c01bcce33f6cfb2c35e4b55dd7f43c7568125b3634",
            "25dc7654ff5423fb132d2060f137c077bf4f326a55b26218ef06736178d2361a",
            "6bee36811ced2b4622169a67a3a2e4c0b6b737ded6633070c1041d0ba96e5615",
        ):
            self.assertIn(digest, text)
        self.assertIn("ED2_P0", text)
        self.assertIn("ED3_CONFIRMATION_1884", text)
        self.assertIn('"target_reads": 0', text)
        self.assertIn('"next_stage": "RUN_ED5_D_CONFIRMATION" if all_clear', text)

    def test_launch_profiles_forbid_science_side_effects(self):
        for name in (
            "ed5-fresh-w-source-v1.json",
            "ed5-fresh-s-source-v1.json",
            "ed5-fresh-dws-historical-disjointness-v1.json",
        ):
            profile = self.profile(name)
            self.assertEqual(profile["campaign"], "ed5-q200k-choice-k2")
            for mode in ("rehearsal_max_effects", "production_max_effects"):
                effects = profile[mode]
                self.assertEqual(effects["fits"], 0)
                self.assertEqual(effects["new_scan_searches"], 0)
                self.assertEqual(effects["new_jass_searches"], 0)
                self.assertEqual(effects["strength_games"], 0)
                self.assertEqual(effects["test_target_reads"], 0)
                self.assertEqual(effects["promotions"], 0)
                self.assertEqual(effects["bakes"], 0)


if __name__ == "__main__":
    unittest.main()
