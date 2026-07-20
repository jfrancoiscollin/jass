#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREP = ROOT / "jobs/prepared/l3-imbalance2-role-v2-20260720"
CPX62 = PREP / "cpx62-l3-imbalance2-a64-b64-difficulty-reference.sh"
CCX33 = PREP / "alternate-box/ccx33-l3-imbalance2-a64-b64-difficulty-reference.sh"


class DifficultyReferenceWrapperParityTest(unittest.TestCase):
    def test_both_box_wrappers_parse_and_share_scientific_contract(self):
        for path in (CPX62, CCX33):
            subprocess.run(
                ["bash", "-n", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )

        cpx = CPX62.read_text(encoding="utf-8")
        ccx = CCX33.read_text(encoding="utf-8")
        for token in (
            "V2_P1_PREFIX",
            "EXPECTED_V2_JOB_ID",
            "SCAN_BIN",
            "FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 REFERENCE_GO=1",
            "DEPTH=10 MAXPLIES=400 NSHARDS=8 PAR=8 SHARD_TIMEOUT=21600",
            "PLATEAU_PER_STRATUM=64 PLATEAU_SEED=161803 EXACT_MAX_PIECES=6",
            "JASS_BUILD_JOBS=8",
            "l3-imbalance2-difficulty-reference-v1.sh",
        ):
            self.assertIn(token, cpx)
            self.assertIn(token, ccx)

        self.assertIn("cpx62-l3-imbalance2-a64-b64-difficulty-reference", cpx)
        self.assertIn("ccx33-l3-imbalance2-a64-b64-difficulty-reference", ccx)
        self.assertIn("same scientific contract as cpx62 wrapper", ccx)


if __name__ == "__main__":
    unittest.main()
