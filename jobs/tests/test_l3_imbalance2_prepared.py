#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = (ROOT / "jobs/templates/l3-imbalance2-runner-v1.sh").read_text()
GATE = (ROOT / "jobs/templates/l3-imbalance2-scan-gate-v1.sh").read_text()
DOC = (ROOT / "docs/L3_IMBALANCE2_PLAN.md").read_text()
PREP = ROOT / "jobs/prepared/l3-imbalance2-20260719"


class ContractTest(unittest.TestCase):
    def test_training_curriculum_and_p1_recipe(self):
        for token in ("FRESH:-500000", "NSHARDS:-18", "PAR_GEN:-8", "--seed-frac 100",
                      "--random-open-plies \"$RANDOM_OPEN_PLIES\"", "--wdl-zero-score",
                      "--drop-plycap", "--pair-openings", "FRONTIER_FRAC:-0"):
            self.assertIn(token, RUNNER)
        self.assertIn("for shard in $(seq 0 17)", RUNNER)
        self.assertIn("P1) START_GEN=1;  END_GEN=4;  PLAY_DEPTH=8", RUNNER)
        self.assertIn("P2) START_GEN=5;  END_GEN=8;  PLAY_DEPTH=10", RUNNER)
        self.assertIn("P3) START_GEN=9;  END_GEN=12; PLAY_DEPTH=12", RUNNER)
        self.assertIn("P4) START_GEN=13; END_GEN=16; PLAY_DEPTH=14", RUNNER)
        self.assertNotIn("--tb-relabel", RUNNER)
        self.assertNotIn("--adjud-material", RUNNER)
        self.assertNotIn("--drop-post-eps", RUNNER)

    def test_prepared_wrappers_exist(self):
        expected = {f"cpx62-l3-imbalance2-p{i}-v1.sh" for i in range(1, 5)} | {
            "cpx62-l3-imbalance2-scan-gate-v1.sh"}
        self.assertEqual(expected, {p.name for p in PREP.glob("*.sh")})
        p1 = (PREP / "cpx62-l3-imbalance2-p1-v1.sh").read_text()
        self.assertIn("PHASE=P1", p1)
        self.assertNotIn("PARENT_MODEL_URI", p1)
        for phase in range(2, 5):
            text = (PREP / f"cpx62-l3-imbalance2-p{phase}-v1.sh").read_text()
            self.assertIn("PARENT_MODEL_URI", text)
            self.assertIn("PARENT_MODEL_SHA256", text)

    def test_stop_gate_requires_two_pools(self):
        self.assertIn("pool-a-decision.json", GATE)
        self.assertIn("pool-b-decision.json", GATE)
        self.assertIn("STOP_LINEAGE_SCAN_EQUIVALENT", GATE)
        self.assertIn("a['pass'] and b['pass']", GATE)
        self.assertIn("automatic_next_job':None", GATE)

    def test_doc_contract(self):
        for n in (1, 6, 12, 18):
            self.assertRegex(DOC, rf"{n}\s*v\s*{n+2}")
        self.assertIn("Scan ne fournit aucune donnée d’entraînement", DOC)
        self.assertIn("deux pools indépendants", DOC)


if __name__ == "__main__":
    unittest.main()
