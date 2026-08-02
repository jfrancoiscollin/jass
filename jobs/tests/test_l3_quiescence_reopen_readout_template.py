import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-quiescence-reopen-readout-v1.sh"


class QuiescenceReopenReadoutTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_is_readout_only_and_uses_immutable_source(self):
        self.assertIn("SOURCE_RESULT_URI", self.text)
        self.assertIn("EXPECTED_SOURCE_ATTEMPT", self.text)
        self.assertIn("immutable source checksum mismatch", self.text)
        self.assertNotIn("match_gate.py", self.text)
        self.assertNotIn("aggregate_conv_shards.py", self.text)
        self.assertNotIn("cmake", self.text)

    def test_registered_failure_is_checked_before_recovery(self):
        self.assertIn("Object of type bool_ is not JSON serializable", self.text)
        self.assertIn('"state": "failed"', self.text)
        self.assertIn('"exit_code": 1', self.text)

    def test_nomenclature_pin_and_no_continuation_are_enforced(self):
        self.assertIn("-codex-.*-at-([0-9a-f]{8})-v", self.text)
        self.assertIn('"${BASH_REMATCH[1]}" -ge 1200', self.text)
        self.assertIn("visible SHA mismatch", self.text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", self.text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", self.text)


if __name__ == "__main__":
    unittest.main()
