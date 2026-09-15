from __future__ import annotations

import json
import unittest
from pathlib import Path

from jobs.tools import ed5_fresh_decision_source_disjoint_stage as s
from jobs.tools import ed5_fresh_decision_source_stage as parent


class Ed5FreshDecisionSourceDisjointTests(unittest.TestCase):
    def test_repair_is_bound_to_preregistered_reserve_and_authenticated_ed3_collision(self):
        self.assertEqual(parent.MASTER, 202609140501)
        self.assertEqual(parent.RESERVE, 202609140511)
        self.assertEqual(s.PRIMARY_DIAGNOSIS["source"], "ED3_CONFIRMATION_1884")
        self.assertEqual(s.PRIMARY_DIAGNOSIS["count"], 12)
        self.assertEqual(
            s.PRIMARY_DIAGNOSIS["digest"],
            "b2ee650ab4b82c501a7116c236d8e64f70ca628639986a2f5fd4d4d83cbfc863",
        )

    def test_full_forbidden_universe_requires_ed2_ed3_ed4_w_and_s(self):
        sources = {name: {f"canon-{name}"} for name in s.REQUIRED_FORBIDDEN_SOURCES}
        forbidden = s.build_forbidden_universe(sources)
        self.assertEqual(len(forbidden), len(s.REQUIRED_FORBIDDEN_SOURCES))
        for name in ("ED2_P0", "ED3_CONFIRMATION_1884", "ED5_W1988", "ED5_S1984"):
            self.assertIn(f"canon-{name}", forbidden)

        missing = dict(sources)
        missing.pop("ED3_CONFIRMATION_1884")
        with self.assertRaisesRegex(ValueError, "d_reserve_forbidden_sources_missing"):
            s.build_forbidden_universe(missing)

        empty = dict(sources)
        empty["ED2_P0"] = set()
        with self.assertRaisesRegex(ValueError, "d_reserve_forbidden_sources_empty"):
            s.build_forbidden_universe(empty)

    def test_reserve_collision_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "d_reserve_canonical_collision_with_forbidden_universe"):
            s.assert_disjoint({"fresh", "old-ed3"}, {"old-ed3", "old-ed2"})
        s.assert_disjoint({"fresh-a", "fresh-b"}, {"old-ed3", "old-ed2"})

    def test_profile_is_zero_target_zero_search_and_uses_disjoint_stage(self):
        profile = Path(__file__).resolve().parents[1] / "launch_profiles/ed5-fresh-d-source-disjoint-v2.json"
        obj = json.loads(profile.read_text())
        self.assertEqual(
            obj["command"],
            ["/usr/bin/python3", "jobs/tools/ed5_fresh_decision_source_disjoint_stage.py"],
        )
        for mode in ("rehearsal_max_effects", "production_max_effects"):
            self.assertEqual(obj[mode]["test_target_reads"], 0)
            self.assertEqual(obj[mode]["new_scan_searches"], 0)
            self.assertEqual(obj[mode]["new_jass_searches"], 0)
            self.assertEqual(obj[mode]["fits"], 0)
            self.assertEqual(obj[mode]["strength_games"], 0)
            self.assertEqual(obj[mode]["promotions"], 0)
            self.assertEqual(obj[mode]["bakes"], 0)


if __name__ == "__main__":
    unittest.main()
