from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from jobs.tools import cls_depth_growth_full_launch_stage as launch
from jobs.tools import cls_depth_growth_full_stage as stage

ROOT = Path(__file__).resolve().parents[2]


class CLSDepthGrowthFullV2Tests(unittest.TestCase):
    def test_authenticated_sizing_is_hard_frozen_full(self):
        self.assertEqual(stage.SIZING_JOB, "cpx62-1998-l3-cls-depth-growth-rehearsal-v1")
        self.assertEqual(stage.SIZING_ATTEMPT, "20260916T061338Z-1a27049d")
        self.assertEqual(stage.SIZING_CODE, "1a27049d036a5bd8534ba2cb350c257ac33942c3")
        self.assertEqual(stage.SIZING_RECEIPT_SHA256, "bee34c20c742b3acb0199ec9723fe8135e32e09ffbf82e68e284ddff724d06ad")
        self.assertEqual(stage.PRODUCTION_SIZE_DECISION, "FULL")
        self.assertEqual(stage.PRODUCTION_ROOTS, 512)
        self.assertEqual(stage.ROOTS_PER_PHASE, 128)
        self.assertEqual(stage.BOOTSTRAP_REPLICATES, 100000)
        self.assertEqual(stage.BOOTSTRAP_SEED, 2026091002)

    def test_full_selector_preserves_frozen_source_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deep = root / "deep512.tsv"
            source_ids = []
            with deep.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["parent_id", "canonical_fingerprint", "phase", "subset_hash"],
                    delimiter="\t",
                    lineterminator="\n",
                )
                writer.writeheader()
                idx = 0
                for phase in stage.PHASES:
                    for n in range(128):
                        parent_id = str(10000 + idx)
                        source_ids.append(parent_id)
                        writer.writerow({
                            "parent_id": parent_id,
                            "canonical_fingerprint": f"{phase}-fp-{n:03d}",
                            "phase": phase,
                            "subset_hash": f"x{n:03d}",
                        })
                        idx += 1
            ids = root / "ids.txt"
            selected = stage.select_full(deep, ids)
            self.assertEqual([row["parent_id"] for row in selected], source_ids)
            self.assertEqual(ids.read_text().splitlines(), source_ids)
            self.assertEqual(
                {phase: sum(row["phase"] == phase for row in selected) for phase in stage.PHASES},
                {phase: 128 for phase in stage.PHASES},
            )

    def test_bootstrap_is_deterministic_and_phase_stratified(self):
        arrays = {}
        for phase_index, phase in enumerate(stage.PHASES):
            values = np.zeros((stage.ROOTS_PER_PHASE, 6), dtype=np.float64)
            values[:, :3] = float(phase_index)
            values[:, 3:] = 1.0
            arrays[phase] = values
        first = stage.bootstrap_root_metrics(arrays, replicates=2000, seed=stage.BOOTSTRAP_SEED)
        second = stage.bootstrap_root_metrics(arrays, replicates=2000, seed=stage.BOOTSTRAP_SEED)
        self.assertEqual(first, second)
        self.assertEqual(first["unit"], "root_id")
        self.assertTrue(first["phase_stratified"])
        self.assertEqual(first["phase_quotas_fixed"], {phase: 128 for phase in stage.PHASES})
        self.assertAlmostEqual(first["metrics"]["depth_delta_5000"]["median"], 1.5)
        self.assertAlmostEqual(first["metrics"]["move_agreement_200000"]["median"], 1.0)

    def test_one_common_profile_covers_rehearsal_and_production(self):
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-depth-growth-v2-full.json").read_text())
        self.assertEqual(profile["campaign"], "cls-v1")
        self.assertEqual(profile["required_phases"], launch.PHASES)
        rehearsal = profile["rehearsal_max_effects"]
        production = profile["production_max_effects"]
        self.assertEqual(rehearsal, production)
        self.assertEqual(rehearsal["new_jass_searches"], 3072)
        self.assertEqual(rehearsal["new_scan_searches"], 1536)
        self.assertEqual(rehearsal["test_target_reads"], 0)
        for field in ("fits", "strength_games", "selfplay_games", "promotions", "bakes"):
            self.assertEqual(rehearsal[field], 0)

    def test_no_runtime_resizing_or_depth_surrogate(self):
        text = (ROOT / "jobs/tools/cls_depth_growth_full_stage.py").read_text()
        self.assertIn('PRODUCTION_SIZE_DECISION = "FULL"', text)
        self.assertIn("fresh depth-N searches are forbidden substitutes", text)
        self.assertIn('mode not in {"rehearsal", "production"}', text)
        self.assertNotIn('decision = "FULL" if', text)
        self.assertNotIn("go depth", text)


if __name__ == "__main__":
    unittest.main()
