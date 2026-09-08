from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import scan_oracle_gate0_j12_select as selector

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/experiments/L3_J12_FACTORIAL_GATE0_V1_20260908.json"
STAGE = ROOT / "jobs/templates/l3-scan-oracle-gate0-j12-factorial-v1.sh"
SCORER = ROOT / "jobs/tools/scan_oracle_gate0_j12_factorial.cpp"


class J12FactorialTests(unittest.TestCase):
    def test_prereg_budget_and_zero_strength(self) -> None:
        p = json.loads(PREREG.read_text(encoding="utf-8"))
        self.assertEqual(p["cohort"]["selected_parents"], 512)
        self.assertEqual(p["cohort"]["selected_phase_counts"], {"P0": 128, "P1": 128, "P2": 128, "P3": 128})
        self.assertEqual(p["cohort"]["required_overlap_with_prior_gate0"], 0)
        self.assertTrue(p["cohort"]["target_blind"])
        self.assertEqual(p["runtime"]["budget_nodes_per_parent_per_arm"], 20000)
        self.assertEqual(p["runtime"]["planned_max_jass_nodes"], 40960000)
        self.assertEqual(set(p["runtime"]["arms"]), {"CONTROL", "J1_SCAN_VERIFY", "J2_SCAN_THREAT_REENTRY", "J12_SCAN_VERIFY_THREAT_REENTRY"})
        self.assertEqual(p["guards"]["new_scan_searches"], 0)
        self.assertEqual(p["guards"]["fits"], 0)
        self.assertEqual(p["guards"]["strength_games"], 0)
        self.assertEqual(p["guards"]["selfplay_games"], 0)
        self.assertFalse(p["survivor_rule"]["strength_authorized"])

    def test_selector_is_disjoint_phase_balanced_and_target_blind(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            groups = td / "groups.tsv"
            old = td / "old.txt"
            rows = ["parent_id\tparent_fingerprint\tparent_phase\n"]
            excluded = []
            pid = 0
            for phase in selector.PHASES:
                for j in range(500):
                    rows.append(f"{pid}\tfp-{phase}-{j:03d}\t{phase}\n")
                    if j < 128:
                        excluded.append(pid)
                    pid += 1
            groups.write_text("".join(rows), encoding="utf-8")
            old.write_text("".join(f"{x}\n" for x in excluded), encoding="utf-8")
            meta = selector.load_parent_meta(groups)
            ex = selector.load_excluded(old, meta)
            chosen = selector.select(meta, ex)
            self.assertEqual(len(chosen), 512)
            self.assertFalse(set(chosen) & ex)
            self.assertEqual({p: sum(meta[x][1] == p for x in chosen) for p in selector.PHASES}, {p: 128 for p in selector.PHASES})
            self.assertEqual(selector.PREFIX, "SCAN-J12-FRESH-2026090801:")

    def test_scorer_freezes_factorial_semantics(self) -> None:
        text = SCORER.read_text(encoding="utf-8")
        for arm in ("CONTROL", "J1_SCAN_VERIFY", "J2_SCAN_THREAT_REENTRY", "J12_SCAN_VERIFY_THREAT_REENTRY"):
            self.assertIn(arm, text)
        self.assertIn("p.scan_verify_pruning = true", text)
        self.assertIn("p.qs_threat_ext = false", text)
        self.assertIn("p.scan_threat_reentry = true", text)
        self.assertIn("budget != 20'000", text)
        self.assertIn("required_activation_observed", text)
        self.assertNotIn("assert_activation", text)

    def test_stage_selects_before_motivation_and_scan_reads(self) -> None:
        text = STAGE.read_text(encoding="utf-8")
        self.assertLess(text.index("phase fresh-cohort-select"), text.index("phase authenticate-motivation-and-oracle"))
        self.assertIn("--exclude-ids \"$IN/prior-gate0-ids.txt\"", text)
        self.assertIn("J12_SCAN_VERIFY_THREAT_REENTRY", text)
        self.assertIn("new_scan_searches=0", text)
        self.assertIn("STRENGTH_GAMES__0", text)
        self.assertIn("'selfplay_games':0", text)
        self.assertNotIn("cutechess", text.lower())
        self.assertNotIn("generate_selfplay", text.lower())


if __name__ == "__main__":
    unittest.main()
