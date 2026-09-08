from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "jobs/templates/l3-d4c-post-teacher-recovery-v1.sh"


class D4cPostTeacherRecoveryTests(unittest.TestCase):
    def test_reuses_1870_teacher_and_zero_new_teacher_search(self) -> None:
        s = STAGE.read_text(encoding="utf-8")
        self.assertIn("20260908T054613Z-346c46a2", s)
        self.assertIn("work/teacher/s${i}-events.jsonl", s)
        self.assertIn("new_teacher_searches=0", s)
        self.assertNotIn("d4_search_utility_trace_export", s)

    def test_prepare_uses_canonical_4000_root_manifest(self) -> None:
        s = STAGE.read_text(encoding="utf-8")
        self.assertIn("d4-search-utility-roots.tsv=d4-roots-4000.tsv", s)
        self.assertIn('prepare --roots "$IN/d4-roots-4000.tsv"', s)
        self.assertNotIn('prepare --roots "$IN/d4b-roots.tsv"', s)

    def test_no_strength_or_new_scan_searches(self) -> None:
        s = STAGE.read_text(encoding="utf-8")
        self.assertIn("new_scan_searches=0", s)
        self.assertIn("STRENGTH_GAMES__0", s)
        self.assertIn("STRENGTH_AUTHORIZED__FALSE", s)
        self.assertNotIn("selfplay", s.lower().replace("selfplay_games", ""))


if __name__ == "__main__":
    unittest.main()
