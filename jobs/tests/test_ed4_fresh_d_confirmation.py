from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from jobs.tools import ed4_fresh_d_confirmation_stage as d


class FreshDConfirmationTests(unittest.TestCase):
    def test_frozen_campaign_constants(self):
        self.assertEqual(d.D_SOURCE[0], "cpx62-1937-l3-ed4-fresh-d-source-production-v1")
        self.assertEqual(d.D_SOURCE[1], "20260913T073800Z-9673030c")
        self.assertEqual(d.CANDIDATE_SHA256, "2e856652efdd1d2758a949a5d4a29557fa31f4a64d55505ae6dc41482b641f5b")
        self.assertEqual(d.D_MASTER_SEED, 202609120401)
        self.assertEqual(d.NODE_BUDGET, 200000)
        self.assertEqual(d.PARENTS, 512)
        self.assertEqual(d.CELL_QUOTA, 64)
        self.assertAlmostEqual(d.FAMILY_ALPHA_K, 0.025)
        self.assertAlmostEqual(d.BLOCK_ALPHA, 0.025 / 3.0)

    def test_stratified_one_sided_bootstrap_constant_gain(self):
        cells = [f"P{phase}_stm{stm}" for phase in range(4) for stm in (0, 1) for _ in range(64)]
        delta = np.ones(512, dtype=float)
        report = d.bootstrap_parent_one_sided(delta, cells, 202609140901)
        self.assertEqual(report["cluster_unit"], "parent")
        self.assertEqual(report["strata"], "phase_x_stm")
        self.assertAlmostEqual(report["mean"], 1.0)
        self.assertAlmostEqual(report["lower"], 1.0)
        self.assertAlmostEqual(report["upper"], 1.0)
        self.assertAlmostEqual(report["one_sided_alpha"], 0.025 / 3.0)

    def test_decision_groups_requires_exact_64_per_cell(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parents = root / "parents.tsv"
            groups = root / "groups.tsv"
            parents.write_text("parent_id\tparent_fingerprint\tcanonical_fingerprint\tparent_phase\tparent_stm\tsplit\ttrajectory_index\tseed\n", encoding="utf-8")
            groups.write_text("row_index\tsibling_identity\tchild_fingerprint\tchild_rule_terminal\tchild_legal_moves\tparent_id\tparent_phase\tparent_stm\tsplit\n", encoding="utf-8")
            with parents.open("a", encoding="utf-8") as p, groups.open("a", encoding="utf-8") as g:
                row = 0
                pid = 0
                for phase in range(4):
                    for stm in (0, 1):
                        for local in range(64):
                            p.write(f"{pid}\tp{pid}\tc{pid}\tP{phase}\t{stm}\tdecision\t{local}\t{d.D_MASTER_SEED + 1}\n")
                            for sibling in range(2):
                                g.write(f"{row}\t{pid}:{sibling}\tx{row}\t0\t2\t{pid}\tP{phase}\t{stm}\tdecision\n")
                                row += 1
                            pid += 1
            parsed = d.decision_groups(root)
            self.assertEqual(len(parsed), 512)
            self.assertEqual(sum(len(group["rows"]) for group in parsed), 1024)

    def test_launch_profile_has_zero_target_rehearsal(self):
        root = Path(__file__).resolve().parents[2]
        profile = json.loads((root / "jobs/launch_profiles/ed4-fresh-d-confirmation-v1.json").read_text())
        self.assertEqual(profile["command"][1], "jobs/tools/ed4_fresh_d_confirmation_stage.py")
        self.assertEqual(profile["rehearsal_max_effects"]["test_target_reads"], 0)
        self.assertEqual(profile["rehearsal_max_effects"]["new_scan_searches"], 0)
        self.assertEqual(profile["production_max_effects"]["test_target_reads"], 8192)
        self.assertEqual(profile["production_max_effects"]["new_scan_searches"], 8192)


if __name__ == "__main__":
    unittest.main()
