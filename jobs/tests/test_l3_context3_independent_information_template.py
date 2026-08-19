#!/usr/bin/env python3
import unittest
from pathlib import Path


TEMPLATE = Path("jobs/templates/l3-context3-independent-information-screen-v1.sh")


class Context3IndependentInformationTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_read_only_contract(self):
        self.assertIn("BOOTSTRAP_REPLICATES=5000", self.text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", self.text)
        self.assertNotIn("--gen-data-wdl", self.text)
        self.assertNotIn("jass_vs_jass", self.text)
        self.assertNotIn("rank_finetune", self.text)
        self.assertIn("'selfplay_generated':False", self.text)
        self.assertIn("'patterneval_fits_run':0", self.text)
        self.assertIn("'frozen_read':False", self.text)
        self.assertIn("'promotion_authorized':False", self.text)

    def test_authenticates_chain(self):
        for job in (
            "cpx62-1409-l3-context2-intervention-corpus-v1",
            "cpx62-1411-l3-context2-intervention-mapper-screen-v1",
            "cpx62-1415a-l3-context2-shared-information-readout-v1",
        ):
            self.assertIn(job, self.text)
        self.assertEqual(self.text.count("--expected-state completed"), 3)

    def test_runtime_and_reporting_guards(self):
        self.assertIn('"$(nproc)" -eq 16', self.text)
        self.assertIn("persistent numeric runtime absent; do not reinstall", self.text)
        self.assertIn("eta_minutes=15-35", self.text)
        self.assertIn("reporting-roundtrip", self.text)
        self.assertIn("git show \"$EXPECTED_CODE_SHA:$file\" | cmp", self.text)
        self.assertIn("timeout 4500s", self.text)


if __name__ == "__main__":
    unittest.main()
