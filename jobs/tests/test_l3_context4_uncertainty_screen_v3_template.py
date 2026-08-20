#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "jobs/templates/l3-context4-uncertainty-screen-v2.sh"
WRAPPER = ROOT / "jobs/templates/l3-context4-uncertainty-screen-v3.sh"


class Context4UncertaintyScreenV3TemplateTests(unittest.TestCase):
    def test_v3_technical_substitution_anchors_are_unique(self):
        base = BASE.read_text(encoding="utf-8")
        anchors = (
            r"^cpx62-[0-9]+-l3-context4-uncertainty-screen-v2$",
            "fetch \"$FORCE_ROOT\" verified-1428.json \\\n  --file artefacts/JASS_CONTROL_SUMMARY.json=force-summary.json \\\n",
            "from jobs.tools.l3_context4_source_contract import validate_1428_force_summary",
            "force=json.load(open(src/'force-summary.json'))\nreadout=json.load(open(src/'readout.json'))",
            "try:\n    validate_1428_force_summary(force)\nexcept ValueError as exc:\n    raise SystemExit(str(exc)) from exc",
            "if force.get('promotion_authorized') is not False:\n    raise SystemExit('1428 promotion scope drift')\n",
        )
        for anchor in anchors:
            with self.subTest(anchor=anchor):
                self.assertEqual(base.count(anchor), 1)

    def test_locked_science_matches_preregistered_v2(self):
        base = BASE.read_text(encoding="utf-8")
        locked = {
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
        }
        for key, expected in locked.items():
            with self.subTest(key=key):
                self.assertEqual(
                    re.findall(rf"(?m)^{re.escape(key)}=(\S+)$", base),
                    [expected],
                )

    def test_wrapper_only_targets_authentication_boundary(self):
        wrapper = WRAPPER.read_text(encoding="utf-8")
        for required in (
            "context3-two-pool-force-readout.json=force-readout.json",
            "validate_1428_force_readout(force_readout)",
            "scientific_protocol_changed\": False",
            "runner_summary_missing_scientific_promotion_field",
        ):
            with self.subTest(required=required):
                self.assertIn(required, wrapper)
        for forbidden in (
            "PER_POOL=",
            "CHOICE_DEPTH=",
            "JUDGE_DEPTH=",
            "UNCERTAINTY_CP=",
            "SELECTION_SEED=",
            "SHUFFLE_SEED=",
            "BOOTSTRAP_SEED=",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, wrapper)


if __name__ == "__main__":
    unittest.main()
