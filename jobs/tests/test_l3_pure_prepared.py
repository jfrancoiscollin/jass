#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREPARED = ROOT / "jobs/prepared/l3-pure-c0-20260718"
TEMPLATE = ROOT / "jobs/templates/l3-pure-c0-runner-v3.sh"


class L3PurePreparedTests(unittest.TestCase):
    def test_scripts_are_shell_valid_and_not_queued(self):
        scripts = sorted(PREPARED.glob("*.sh"))
        self.assertEqual(len(scripts), 2)
        for script in (TEMPLATE, *scripts):
            subprocess.run(["bash", "-n", str(script)], check=True)
            self.assertNotIn("/jobs/queue/", str(script))

    def test_arms_are_matched_except_for_frontier(self):
        arm_a = (PREPARED / "ccx33-l3-pure-c0-a-v1.sh").read_text()
        arm_b = (PREPARED / "cpx62-l3-pure-c0-b-v1.sh").read_text()
        for invariant in (
            "NGEN=3 FRESH=500000 NSHARDS=8 PAR_GEN=8",
            "BASE_SEED=314159",
            "SHARD_TIMEOUT=21600",
            "JASS_BUILD_JOBS=8",
        ):
            self.assertIn(invariant, arm_a)
            self.assertIn(invariant, arm_b)
        self.assertIn("FRONTIER_FRAC=0", arm_a)
        self.assertIn("FRONTIER_FRAC=25", arm_b)

    def test_runner_excludes_known_teacher_channels(self):
        text = TEMPLATE.read_text()
        self.assertIn("--drop-plycap", text)
        self.assertIn("--sample-meta-out", text)
        self.assertIn("--warm-start", text)
        self.assertIn("FULL_RUN_APPROVED", text)
        self.assertNotIn("--deep-relabel", text)
        self.assertNotIn("--adjud-material", text)
        self.assertNotIn("--tb-relabel", text)
        self.assertNotIn("--drop-post-eps", text)
        self.assertNotIn("Scan", text)
        self.assertNotIn("master", text.lower())

    def test_warm_start_begins_with_previous_student_only(self):
        text = TEMPLATE.read_text()
        self.assertIn('warm_start_args=()', text)
        self.assertIn('if [ "$generation" -gt 1 ]; then', text)
        self.assertIn('warm_start_args=(--warm-start "$PILOT")', text)
        self.assertIn('"${warm_start_args[@]}" --holdout-count', text)
        self.assertNotIn('--warm-start "$PILOT" --holdout-count', text)

    def test_quiescence_fingerprint_is_explicit_and_manifested(self):
        text = TEMPLATE.read_text()
        expected = (
            "qs_threat_ext=1,qs_sacs=1,qs_sacs_depth0_only=1,"
            "qs_forcing_depth=0,qs_promo_depth=0"
        )
        self.assertIn(f'L3_SEARCH_PARAMS="{expected}"', text)
        self.assertEqual(text.count('--search-params "$L3_SEARCH_PARAMS"'), 1)
        self.assertIn('"search_params_scope":"play_and_label"', text)
        self.assertIn('"search_params_inherited_defaults":False', text)
        self.assertIn('l3-run-config.json', text)
        self.assertIn('search_params_sha256', text)


if __name__ == "__main__":
    unittest.main()
