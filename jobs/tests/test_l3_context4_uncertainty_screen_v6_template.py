#!/usr/bin/env python3
import unittest
from pathlib import Path


class Context4UncertaintyScreenV6TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path("jobs/templates/l3-context4-uncertainty-screen-v6.sh")
        cls.text = cls.path.read_text(encoding="utf-8")

    def test_wraps_exact_v5_blob_and_only_advances_nomenclature(self):
        self.assertIn(
            'EXPECTED_BASE_BLOB="14ff09418f1f3bb3ee572a61267ede645257a716"',
            self.text,
        )
        self.assertIn("l3-context4-uncertainty-screen-v5.sh", self.text)
        self.assertIn("uncertainty-screen-v6$", self.text)
        self.assertIn("text.count(old) != 1", self.text)

    def test_records_1445_root_cause_and_no_scientific_change(self):
        self.assertIn("1428_force_summary_contract", self.text)
        self.assertIn("1428 unexpectedly refit", self.text)
        self.assertIn('"scientific_protocol_changed": False', self.text)
        self.assertIn("byte-for-byte", self.text)

    def test_revalidates_all_locked_phase1_parameters(self):
        for key, expected in {
            "PER_POOL": "256",
            "CHOICE_DEPTH": "9",
            "JUDGE_DEPTH": "12",
            "UNCERTAINTY_CP": "20",
            "SELECTION_SEED": "2026082007",
            "SHUFFLE_SEED": "2026082008",
            "BOOTSTRAP_SEED": "2026082009",
            "BOOTSTRAP": "100000",
            "MIN_TOTAL": "48",
            "MIN_PER_POOL": "16",
            "MIN_ALIGNED_FLIPS": "12",
        }.items():
            self.assertIn(f'"{key}": "{expected}"', self.text)


if __name__ == "__main__":
    unittest.main()
