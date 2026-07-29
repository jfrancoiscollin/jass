#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-hard-replay-train-v1.sh"


class HardReplayTrainTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_preregisters_the_constant_volume_single_factor_design(self):
        self.assertIn('FRESH_RECORDS=${FRESH_RECORDS:-1000000}', self.text)
        self.assertIn('REPLAY_RECORDS=${REPLAY_RECORDS:-1000000}', self.text)
        self.assertIn('"single_factor": "historical_replay_selection_policy"', self.text)
        self.assertIn('"same_fresh_corpus": True', self.text)
        self.assertIn('"same_fit": True', self.text)
        self.assertIn('"same_holdout": True', self.text)
        self.assertIn(
            '"primary_contrast": "HARD_REPLAY minus UNIFORM_REPLAY"', self.text
        )

    def test_authenticates_catalogue_history_and_parent(self):
        for token in (
            "EXPECTED_PREFLIGHT_JOB",
            "EXPECTED_PREFLIGHT_ATTEMPT",
            "EXPECTED_HISTORY_JOB",
            "EXPECTED_HISTORY_ATTEMPT",
            "EXPECTED_HISTORY_CODE_SHA",
            "HISTORY_ARM",
            "EXPECTED_PARENT_JOB",
            "PARENT_MODEL_SHA",
        ):
            self.assertIn(token, self.text)
        self.assertIn(
            'cmp -s "$IN/source-split.json" "$ART/history-split.json"',
            self.text,
        )
        self.assertIn("hard replay preflight certificate mismatch", self.text)
        self.assertIn(
            "historical raw JNNW hash differs from preflight certificate",
            self.text,
        )

    def test_generates_fresh_once_and_checks_policy_counters(self):
        self.assertIn('phase generate-common-fresh', self.text)
        self.assertEqual(self.text.count('--gen-data-wdl "$count"'), 1)
        self.assertIn("--split-selfplay-rngs", self.text)
        self.assertIn('--explore-topk "$TOPK"', self.text)
        self.assertIn('--explore-margin "$EXPLORE_MARGIN"', self.text)
        self.assertIn("topk3 fresh generation ranked zero plies", self.text)
        self.assertIn("uniform fresh generation ranked", self.text)
        self.assertIn(
            'ranked = sum(counters.get("topk_ranked_plies", []))',
            self.text,
        )
        self.assertIn("fresh-policy-check.json", self.text)
        self.assertIn("fresh record count", self.text)

    def test_assembly_and_fits_share_one_holdout(self):
        self.assertIn("jobs/tools/l3_hard_replay_assembly.py", self.text)
        self.assertIn("--out-control-data", self.text)
        self.assertIn("--out-treatment-data", self.text)
        self.assertIn('"records"]["common_holdout"]', self.text)
        self.assertEqual(self.text.count('--holdout-count "$HOLDOUT"'), 1)
        self.assertIn("for arm in control treatment", self.text)
        self.assertIn("--warm-start \"$W/PARENT.pjtw\"", self.text)
        self.assertIn("--l2 \"$L2\"", self.text)

    def test_fails_closed_and_never_promotes_or_continues(self):
        self.assertIn("FULL_RUN_APPROVED", self.text)
        self.assertIn("SCIENTIFIC_GO", self.text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", self.text)
        self.assertIn('"promotion_authorized": False', self.text)
        self.assertIn('"automatic_next_job": None', self.text)
        self.assertIn('"external_teacher_inputs": 0', self.text)
        self.assertIn("JASS_CONTROL_SUMMARY.json", self.text)
        self.assertIn("logs.tar.gz", self.text)


if __name__ == "__main__":
    unittest.main()
