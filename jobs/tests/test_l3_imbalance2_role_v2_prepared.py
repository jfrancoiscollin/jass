#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = (ROOT / "jobs/templates/l3-imbalance2-runner-v2.sh").read_text()
TOOL = (ROOT / "jobs/tools/prepare_imbalance2_training.py").read_text()
DOC = (ROOT / "docs/L3_IMBALANCE2_ROLE_V2_PLAN.md").read_text()
PREP = ROOT / "jobs/prepared/l3-imbalance2-role-v2-20260720"


class RoleAwareV2ContractTest(unittest.TestCase):
    def test_tool_has_position_role_domain_matrix(self):
        for token in (
            "ROLE_POLICY_V2 = \"role-aware-v2\"",
            "record_role_bucket",
            "abs(nwm - nbm) != 2 or nwk != nbk",
            '"up_win", "down_loss"',
            '"up_loss", "down_win"',
            '"score_field_used_for_weighting": False',
            '"per_move_criticality_relabel": False',
        ):
            self.assertIn(token, TOOL)

    def test_wrapper_reuses_frozen_v1_and_upgrades_manifest(self):
        for token in (
            "IMBALANCE2_REWEIGHT_POLICY=role-aware-v2",
            "bash jobs/templates/l3-imbalance2-runner-v1.sh",
            "deterministic_role_domain_resample",
            '"lineage"] = "L3-IMBALANCE2-ROLE-V2"',
            '"conversion_weights_stm_pov"',
            '"resilience_weights_stm_pov"',
            '"outside_domain_anchor_weight"',
            '"per_move_criticality_relabel": False',
        ):
            self.assertIn(token, RUNNER)

    def test_prepared_wrappers_target_ccx33_and_guard_parents(self):
        expected = {f"ccx33-l3-imbalance2-role-v2-p{i}.sh" for i in range(1, 5)} | {
            "ccx33-l3-imbalance2-role-v2-probe.sh",
            "ccx33-l3-imbalance2-role-v2-scan-gate.sh",
        }
        actual = {path.name for path in PREP.glob("*.sh")}
        self.assertEqual(expected, actual)
        self.assertFalse(any(name.startswith("cpx62-") for name in actual))

        probe = (PREP / "ccx33-l3-imbalance2-role-v2-probe.sh").read_text()
        for token in (
            "PHASE=P1 PROBE=1",
            "FRESH=54000 NSHARDS=18 PAR_GEN=8",
            "JASS_BUILD_JOBS=8",
            "l3-imbalance2-runner-v2.sh",
            "non-promotable",
        ):
            self.assertIn(token, probe)
        self.assertNotIn("SHARD_TIMEOUT", probe)

        p1 = (PREP / "ccx33-l3-imbalance2-role-v2-p1.sh").read_text()
        self.assertIn("PHASE=P1", p1)
        self.assertNotIn("PROBE=1", p1)
        self.assertNotIn("PARENT_MODEL_URI", p1)
        for token in (
            "FRESH=500000 NSHARDS=18 PAR_GEN=8",
            "JASS_BUILD_JOBS=8",
            "l3-imbalance2-runner-v2.sh",
            "do not queue without explicit go",
        ):
            self.assertIn(token, p1)
        self.assertNotIn("SHARD_TIMEOUT", p1)

        for phase in range(2, 5):
            text = (PREP / f"ccx33-l3-imbalance2-role-v2-p{phase}.sh").read_text()
            self.assertIn(f"PHASE=P{phase}", text)
            self.assertIn("PARENT_MODEL_URI", text)
            self.assertIn("PARENT_MODEL_SHA256", text)
            self.assertIn("PAR_GEN=8", text)
            self.assertIn("JASS_BUILD_JOBS=8", text)
            self.assertNotIn("SHARD_TIMEOUT", text)
            self.assertIn("l3-imbalance2-runner-v2.sh", text)

        gate = (PREP / "ccx33-l3-imbalance2-role-v2-scan-gate.sh").read_text()
        self.assertIn("PLATEAU_APPROVED=1", gate)
        self.assertIn("NSHARDS=8 PAR=8", gate)
        self.assertIn("l3-imbalance2-scan-gate-v1.sh", gate)

    def test_doc_states_equivalence_scope_and_ccx33_probe(self):
        for token in (
            "même multiplicateur global `1 / 2 / 4` que V1",
            "pondération est limitée aux positions réellement dans le domaine exact",
            "criticité par coup",
            "Contrat d’exécution ccx33",
            "PROBE=1",
            "FRESH=54000",
            "L3-PURE",
            "docs/L3_ROLE_V2_DUAL_LINEAGE_PLAN.md",
            "A/B apparié",
            "Aucun palier, merge scientifique ou benchmark externe",
        ):
            self.assertIn(token, DOC)


if __name__ == "__main__":
    unittest.main()
