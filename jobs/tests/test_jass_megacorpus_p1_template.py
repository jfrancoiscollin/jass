# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "jass-megacorpus-p1-triage-v1.sh"


class MegaCorpusP1TemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_fetch_is_exact_and_metadata_only(self) -> None:
        self.assertIn("catalog-summary.json corpus-candidates.jsonl.gz runner-attempts.jsonl.gz", self.text)
        self.assertIn('rclone copyto "$P0_ATTEMPT_URI/$name"', self.text)
        self.assertNotIn("rclone copy ", self.text)
        self.assertNotIn("rclone sync", self.text)
        self.assertNotIn("r2-objects.jsonl", self.text)
        self.assertIn("P0 digest mismatch", self.text)
        self.assertIn("P0 row count mismatch", self.text)
        self.assertIn("jass.megacorpus.catalog.v1", self.text)

    def test_guards_and_no_continuation_are_explicit(self) -> None:
        for guard in (
            "METADATA_ONLY_APPROVED", "NO_PAYLOAD_DOWNLOADS", "NO_FROZEN_READS",
            "NO_AUTOMATIC_CONTINUATION", "PAYLOAD_SAMPLE_AUTHORIZED__FALSE",
            "TRAINING_AUTHORIZED__FALSE", "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(guard, self.text)
        self.assertNotIn("train_from_replay", self.text)
        self.assertNotIn("self-play", self.text.lower())

    def test_outputs_are_transportable(self) -> None:
        self.assertIn("scientific-summary.json", self.text)
        self.assertIn("JASS_CONTROL_SUMMARY.json", self.text)
        self.assertIn("60000", self.text)
        self.assertIn("VERDICT__JASS_MEGACORPUS_P1_TRIAGE_READY", self.text)


if __name__ == "__main__":
    unittest.main()
