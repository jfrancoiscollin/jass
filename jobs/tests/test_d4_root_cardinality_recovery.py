from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class D4RootCardinalityRecoveryTests(unittest.TestCase):
    def test_generator_header_and_recovery_guard_are_compatible(self) -> None:
        main = (ROOT / "src/main.cpp").read_text(encoding="utf-8")
        stage = (ROOT / "jobs/templates/l3-d4-search-utility-offline-v1.sh").read_text(encoding="utf-8")
        recovery = (ROOT / "jobs/templates/l3-d4-search-utility-offline-cardinality-recovery-v1.sh").read_text(encoding="utf-8")

        self.assertIn('<< "# count=" << count', main)
        self.assertIn("grep -cve '^[[:space:]]*$'", stage)
        self.assertIn("grep -cvE '^[[:space:]]*(#|$)'", recovery)
        self.assertIn("expected exactly one cardinality guard", recovery)

    def test_comment_aware_fixture_counts_only_payload_rows(self) -> None:
        rows = [
            "# count=3 min_ply=8 max_ply=32 min_pieces=20 seed=1",
            "W:W31:B20",
            "B:W31:B20",
            "",
            "   # another comment",
            "W:W30:B21",
        ]
        payload = [r for r in rows if r.strip() and not r.lstrip().startswith("#")]
        self.assertEqual(len(payload), 3)


if __name__ == "__main__":
    unittest.main()
