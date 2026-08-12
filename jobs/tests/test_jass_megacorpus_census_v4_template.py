# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "jobs/templates/jass-megacorpus-r2-census-v4.sh").read_text()


class MegaCorpusCensusV4TemplateTest(unittest.TestCase):
    def test_census_is_sharded_resumable_and_payload_blind(self) -> None:
        self.assertIn("jass_megacorpus_r2_shards.py", TEXT)
        self.assertIn("--split-depth 2", TEXT)
        self.assertIn("--max-depth 6", TEXT)
        self.assertIn("MEGACORPUS_RESUME_URI", TEXT)
        self.assertIn("checkpoints", TEXT)
        self.assertIn("NO_PAYLOAD_DOWNLOADS", TEXT)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", TEXT)
        self.assertIn("--files-from-raw", TEXT)
        self.assertIn("--no-traverse", TEXT)
        self.assertNotIn("rclone lsjson \"$JASS_OBJSTORE_REMOTE\" --recursive", TEXT)

    def test_timeouts_and_gates_are_bounded(self) -> None:
        self.assertIn('SHARD_TIMEOUT_SECONDS="${SHARD_TIMEOUT_SECONDS:-900}"', TEXT)
        self.assertIn('DISCOVERY_TIMEOUT_SECONDS="${DISCOVERY_TIMEOUT_SECONDS:-300}"', TEXT)
        self.assertIn("invalid bounded timeout", TEXT)
        self.assertIn("payload_objects_downloaded", TEXT)
        self.assertIn("frozen_cohorts_read", TEXT)
        self.assertIn("training_authorized", TEXT)
        self.assertIn("promotion_authorized", TEXT)
        self.assertIn("automatic_next_job", TEXT)


if __name__ == "__main__":
    unittest.main()
