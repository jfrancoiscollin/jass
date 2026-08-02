import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-quiescence-reopen-q01-v1.sh"


class QuiescenceReopenTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_job_namespace_and_authorization_are_guarded(self):
        self.assertIn('[[ "$JASS_JOB_ID" =~ ^home-([0-9]+)- ]]', self.text)
        self.assertIn('"${BASH_REMATCH[1]}" -ge 1200', self.text)
        self.assertIn("FULL_RUN_APPROVED", self.text)
        self.assertIn("SCIENTIFIC_GO", self.text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", self.text)

    def test_every_consumed_input_has_an_explicit_producer(self):
        self.assertIn("cpx62-1117-l3-exact-fold-refit-v1", self.text)
        self.assertIn("home-1004-l3-pure-volume8m-preflight-v2", self.text)
        self.assertIn("home-0954-l3-pure-m1-abextras-validation-v5", self.text)
        self.assertIn("artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz", self.text)
        self.assertIn("artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz", self.text)
        self.assertIn("fetch_t1bis_inputs.py", self.text)

    def test_conversion_aggregator_schema_is_consumed_by_the_readout(self):
        self.assertIn("aggregate_conv_shards.py", self.text)
        tool = (ROOT / "jobs" / "tools" / "l3_quiescence_reopen_verdict.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('("conversion", "n_pos")', tool)
        self.assertIn('{"conversion_rate", "records"}', tool)

    def test_q01_is_a_single_parameter_button(self):
        self.assertIn('Q01="${Q00/qs_sacs=0/qs_sacs=1}"', self.text)
        self.assertIn(
            'Q00_FIXED="${Q00%,scan_verify_pruning=0,scan_threat_reentry=0}"',
            self.text,
        )
        self.assertIn("validate_arm_contract", self.text)
        self.assertNotRegex(self.text, r"exact-fold-refit-v1\.sh|l3-model-gate-v1\.sh|l3-succession-guards-v1\.sh")

    def test_registered_sizing_and_no_continuation(self):
        self.assertIn("EXPECTED_GAMES_PER_VIEW=3000", self.text)
        self.assertIn("TARGET_PER_STRATUM=300", self.text)
        self.assertIn("MIN_PAIRED_PER_STRATUM=270", self.text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", self.text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", self.text)

    def test_same_exact_binary_and_model_are_used_on_both_gate_sides(self):
        self.assertIn('--jass-a "$J8" --jass-b "$J8"', self.text)
        self.assertIn('--pattern-a "$W/EXACT.pjtw" --pattern-b "$W/EXACT.pjtw"', self.text)
        self.assertIn('--search-params-a "$Q01" --search-params-b "$Q00"', self.text)


if __name__ == "__main__":
    unittest.main()
