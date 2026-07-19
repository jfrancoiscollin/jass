#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = (ROOT / "jobs/templates/l3-imbalance2-runner-v2.sh").read_text()
COMPARE_RUNNER = (ROOT / "jobs/templates/l3-imbalance2-p1-compare-v1.sh").read_text()
TOOL = (ROOT / "jobs/tools/prepare_imbalance2_training.py").read_text()
POOL_TOOL = (ROOT / "jobs/tools/make_imbalance2_pools.py").read_text()
COMPARE_TOOL = (ROOT / "jobs/tools/imbalance2_lineage_compare.py").read_text()
DOC = (ROOT / "docs/L3_IMBALANCE2_ROLE_V2_PLAN.md").read_text()
RECIPE = (ROOT / "jobs/prepared/l3-imbalance2-role-v2-20260720/RECIPE.md").read_text()
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

    def test_wrapper_reuses_v1_and_upgrades_manifest_and_pool_contract(self):
        for token in (
            "IMBALANCE2_REWEIGHT_POLICY=role-aware-v2",
            "bash jobs/templates/l3-imbalance2-runner-v1.sh",
            "deterministic_role_domain_resample",
            'payload["lineage"] = "L3-IMBALANCE2-ROLE-V2"',
            '"conversion_weights_stm_pov"',
            '"resilience_weights_stm_pov"',
            '"outside_domain_anchor_weight"',
            '"per_move_criticality_relabel": False',
            'PLATEAU_PER_STRATUM:-}" = 64',
            'IMBALANCE2_PLATEAU_SEED:-}" = 161803',
            '"protocol": "independent_common_A64_B64"',
            '"records_per_pool": 1152',
        ):
            self.assertIn(token, RUNNER)

    def test_pool_tool_separates_training_and_plateau_seeds(self):
        for token in (
            'p.add_argument(\n        "--plateau-seed"',
            'os.environ.get("IMBALANCE2_PLATEAU_SEED", args.seed)',
            '"training_seed": args.seed',
            '"plateau_seed": plateau_seed',
            '"plateau_records_per_pool": len(STRATA) * args.plateau_per_stratum',
        ):
            self.assertIn(token, POOL_TOOL)

    def test_prepared_wrappers_include_ccx33_lineage_and_cpx62_comparison(self):
        expected = {f"ccx33-l3-imbalance2-role-v2-p{i}.sh" for i in range(1, 5)} | {
            "ccx33-l3-imbalance2-role-v2-probe.sh",
            "ccx33-l3-imbalance2-role-v2-scan-gate.sh",
            "cpx62-l3-imbalance2-p1-v1-v2-a64-compare.sh",
        }
        actual = {path.name for path in PREP.glob("*.sh")}
        self.assertEqual(expected, actual)

        probe = (PREP / "ccx33-l3-imbalance2-role-v2-probe.sh").read_text()
        for token in (
            "PHASE=P1 PROBE=1",
            "FRESH=54000 NSHARDS=18 PAR_GEN=8",
            "PLATEAU_PER_STRATUM=64",
            "IMBALANCE2_PLATEAU_SEED=161803",
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
            "PLATEAU_PER_STRATUM=64",
            "IMBALANCE2_PLATEAU_SEED=161803",
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
            self.assertIn("PLATEAU_PER_STRATUM=64", text)
            self.assertIn("IMBALANCE2_PLATEAU_SEED=161803", text)
            self.assertIn("JASS_BUILD_JOBS=8", text)
            self.assertNotIn("SHARD_TIMEOUT", text)
            self.assertIn("l3-imbalance2-runner-v2.sh", text)

        compare = (PREP / "cpx62-l3-imbalance2-p1-v1-v2-a64-compare.sh").read_text()
        for token in (
            "V1_P1_PREFIX",
            "V2_P1_PREFIX",
            "EXPECTED_V1_JOB_ID",
            "EXPECTED_V2_JOB_ID",
            "DEPTH=10 MAXPLIES=400 NSHARDS=8 PAR=8",
            "BOOTSTRAP=10000 PLATEAU_PER_STRATUM=64 PLATEAU_SEED=161803",
            "18,432 candidate-only d10 games",
            "l3-imbalance2-p1-compare-v1.sh",
        ):
            self.assertIn(token, compare)

        gate = (PREP / "ccx33-l3-imbalance2-role-v2-scan-gate.sh").read_text()
        self.assertIn("PLATEAU_APPROVED=1", gate)
        self.assertIn("NSHARDS=8 PAR=8", gate)
        self.assertIn("l3-imbalance2-scan-gate-v1.sh", gate)

    def test_comparison_is_candidate_only_paired_and_non_promotable(self):
        for token in (
            "historical P1 V1 and new role-aware P1 V2",
            "plateau-a.jnnw.gz",
            "plateau-b.jnnw.gz",
            "18*per",
            "same new pools",
            "imbalance2_plateau.py",
            "imbalance2_lineage_compare.py",
            "candidate-only-a64-b64-reports.tar.gz",
            "'p2_authorized':False",
            "'automatic_next_job':None",
        ):
            self.assertIn(token, COMPARE_RUNNER)
        for token in (
            '"same_pools": True',
            '"same_search_budget": True',
            '"external_references_used": False',
            '"promotion_authorized": False',
            '"automatic_next_job": None',
            '"V2_CLEAR_LEAD_AT_P1"',
        ):
            self.assertIn(token, COMPARE_TOOL)

    def test_doc_states_equivalence_scope_and_combined_p1_campaign(self):
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
            "64 positions par strate",
            "1 152 positions par pool",
            "0847",
            "18 432",
            "Aucun palier, merge scientifique ou benchmark externe",
        ):
            self.assertIn(token, DOC)
        for token in (
            "runner et des wrappers séparés",
            "jamais leurs manifests ni leurs décisions de promotion",
            "A64/B64",
            "re-assess V1",
        ):
            self.assertIn(token, RECIPE)


if __name__ == "__main__":
    unittest.main()
