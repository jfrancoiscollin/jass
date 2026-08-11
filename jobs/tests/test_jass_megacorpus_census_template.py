# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "jobs/templates/jass-megacorpus-r2-census-v1.sh").read_text()


class MegaCorpusCensusTemplateTest(unittest.TestCase):
    def test_census_is_metadata_only_and_cannot_continue(self) -> None:
        self.assertIn("rclone lsjson", TEXT)
        self.assertIn("--recursive --files-only", TEXT)
        self.assertIn("NO_PAYLOAD_DOWNLOADS", TEXT)
        self.assertIn("CENSUS_ONLY_APPROVED", TEXT)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", TEXT)
        self.assertIn("automatic_next_job\": None", TEXT)
        self.assertIn("training_authorized\": False", TEXT)
        self.assertIn("promotion_authorized\": False", TEXT)
        self.assertIn("frozen_cohorts_read\": 0", TEXT)
        self.assertIn("external_teacher_inputs\": 0", TEXT)

    def test_metadata_copy_filters_never_include_training_payload_suffixes(self) -> None:
        filter_lines = [line for line in TEXT.splitlines() if "--filter '+" in line]
        self.assertTrue(filter_lines)
        joined = "\n".join(filter_lines).lower()
        for suffix in ("jnnw", "jsm.gz", "feat", "pjtw", "frozen"):
            self.assertNotIn(suffix, joined)
        for name in (
            "manifest.json", "inventory.json", "checksums.sha256", "_success", "_failed",
        ):
            self.assertIn(name, joined)
        self.assertIn("paths.jsonl.gz", joined)

    def test_operational_guards_are_bounded(self) -> None:
        self.assertIn('R2_LIST_TIMEOUT_SECONDS="${R2_LIST_TIMEOUT_SECONDS:-1800}"', TEXT)
        self.assertIn(
            'R2_METADATA_TIMEOUT_SECONDS="${R2_METADATA_TIMEOUT_SECONDS:-1800}"',
            TEXT,
        )
        self.assertIn('timeout "${R2_LIST_TIMEOUT_SECONDS}s" rclone lsjson', TEXT)
        self.assertIn('timeout "${R2_METADATA_TIMEOUT_SECONDS}s" rclone copy', TEXT)
        self.assertIn("R2 list timeout outside 60..21600 s", TEXT)
        self.assertIn("R2 metadata timeout outside 60..21600 s", TEXT)
        self.assertIn("sleep 30", TEXT)
        self.assertIn("need 2 GiB free", TEXT)
        self.assertIn("n=0 corpus candidates", TEXT)


if __name__ == "__main__":
    unittest.main()
