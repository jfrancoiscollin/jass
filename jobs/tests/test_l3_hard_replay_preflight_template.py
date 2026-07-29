#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-hard-replay-preflight-v1.sh"


class HardReplayPreflightTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_source_and_reproduces_split_before_mining(self):
        self.assertIn('--expected-state "$EXPECTED_HISTORY_STATE"', self.text)
        self.assertIn('"$EXPECTED_HISTORY_ATTEMPT"', self.text)
        self.assertIn('"$EXPECTED_HISTORY_CODE_SHA"', self.text)
        self.assertIn('"$HISTORY_DATA_GZ_SHA"', self.text)
        self.assertIn('"$HISTORY_META_GZ_SHA"', self.text)
        self.assertIn('"$HISTORY_DATA_SHA"', self.text)
        self.assertIn('"$HISTORY_META_SHA"', self.text)
        self.assertLess(
            self.text.index("phase reproduce-historical-split"),
            self.text.index("phase mine-hard-replay-twice"),
        )
        self.assertIn(
            'cmp -s "$IN/source-split.json" "$ART/history-split.json"',
            self.text,
        )

    def test_mining_is_train_only_exact_and_bit_deterministic(self):
        self.assertIn("--signal failed_conversion", self.text)
        self.assertIn("--one-per-game --colour-mirror", self.text)
        self.assertIn("--split-manifest", self.text)
        self.assertIn("mine_once a", self.text)
        self.assertIn("mine_once b", self.text)
        self.assertIn("hard replay is not bit deterministic", self.text)
        self.assertIn("insufficient hard replay capacity", self.text)
        self.assertIn('REPLAY_RECORDS=${REPLAY_RECORDS:-1000000}', self.text)

    def test_has_runtime_and_non_promotion_guards(self):
        self.assertIn("FULL_RUN_APPROVED", self.text)
        self.assertIn("SCIENTIFIC_GO", self.text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", self.text)
        self.assertIn('"promotion_authorized": False', self.text)
        self.assertIn('"automatic_next_job": None', self.text)
        self.assertIn('"external_teacher_inputs": 0', self.text)
        self.assertIn("JASS_CONTROL_SUMMARY.json", self.text)
        self.assertIn("logs.tar.gz", self.text)
        self.assertIn("time_fr=", self.text)


if __name__ == "__main__":
    unittest.main()
