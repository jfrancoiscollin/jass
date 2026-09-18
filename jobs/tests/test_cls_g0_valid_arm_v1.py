from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_g0_runtime_gate as gate
from jobs.tools import cls_g0_valid_arm_stage as stage

ROOT = Path(__file__).resolve().parents[2]


class CLSG0ValidArmV1Tests(unittest.TestCase):
    def test_candidate_source_and_frozen_gate_constants_are_exact(self) -> None:
        self.assertEqual(stage.SOURCE_JOB, "cpx62-2041-l3-cls-l-valid-arms-recovery-2038-v1")
        self.assertEqual(stage.SOURCE_ATTEMPT, "20260918T065139Z-c5067fce")
        self.assertEqual(stage.SOURCE_CODE, "c5067fcefddb48b49313686473d7b0c057a14028")
        self.assertEqual(stage.CURRICULUM_SHA, "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1")
        self.assertEqual(stage.ARM_MODEL_SHA, {
            "LOCAL": "197998003db3d221d38e81577cfa381e8227d67705efc1c86b87205ddebbe450",
            "WDL": "eabe71068dbc6aeb519a61c730d18586e75c8b72308fe2e18deed6",
        })
        self.assertEqual(stage.EXPECTED_SEARCHES, 1536)
        self.assertEqual(gate.ROOTS, 512)
        self.assertEqual(gate.ROOTS_PER_PHASE, 128)
        self.assertEqual(gate.PRIMARY_BUDGET, 200_000)
        self.assertEqual(gate.BOOTSTRAP_REPLICATES, 100_000)
        self.assertEqual(gate.BOOTSTRAP_SEED, 2026091605)

    def test_green_tooling_preflight_is_pinned(self) -> None:
        self.assertEqual(stage.TOOLING_JOB, "cpx62-2018-l3-cls-g0-runtime-tooling-preflight-v3")
        self.assertEqual(stage.TOOLING_ATTEMPT, "20260917T001938Z-ad151a09")
        self.assertEqual(stage.TOOLING_CODE, "ad151a0961a077e5c95a5503a8ee734f5c4cf0b6")
        self.assertEqual(stage.TOOLING_LAUNCH_RECEIPT, "887f9f46adc3bf2cd014dd3a5cd8361ebe8c6ad84833f14099beba3e1e165d52")

    def test_profile_allows_only_frozen_runtime_search_effect(self) -> None:
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-g0-valid-arm-runtime-v1.json").read_text())
        self.assertEqual(profile["campaign"], "cls-v1")
        self.assertEqual(profile["required_phases"], [stage.PHASE])
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        effects = profile["production_max_effects"]
        self.assertEqual(effects["new_jass_searches"], 1536)
        for key in ("fits", "new_scan_searches", "strength_games", "selfplay_games",
                    "promotions", "bakes", "test_target_reads"):
            self.assertEqual(effects[key], 0)

    def test_full_root_order_is_preserved_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = []
            deep512_rows = []
            deep_rows = []
            for pidx, phase in enumerate(gate.PHASES):
                for n in range(gate.ROOTS_PER_PHASE):
                    rid = str(pidx * gate.ROOTS_PER_PHASE + n)
                    ids.append(rid)
                    deep512_rows.append({"parent_id": rid, "phase": phase, "canonical_fingerprint": f"fp-{rid}"})
                    deep_rows.append({"root_id": rid, "budget": str(gate.DEEP_BUDGET), "bestmove_canonical": f"{n+1}-{n+2}"})
            # Deliberately reverse source-file order: frozen production order must win.
            deep512_rows.reverse()
            deep_rows.reverse()
            selection = root / "root-selection.json"
            selection.write_text(json.dumps({"parent_ids": [int(v) for v in ids]}), encoding="utf-8")
            deep512 = root / "deep512.tsv"
            deep = root / "deep.tsv"
            for path, rows in ((deep512, deep512_rows), (deep, deep_rows)):
                with path.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(rows)
            out_ids = root / "ids.txt"
            out_phase = root / "ordered-phase.tsv"
            out_deep = root / "ordered-deep.tsv"
            got = stage.freeze_full_root_order(deep512, selection, deep, out_ids, out_phase, out_deep)
            self.assertEqual(got, ids)
            self.assertEqual(out_ids.read_text().splitlines(), ids)
            with out_phase.open(newline="", encoding="utf-8") as stream:
                self.assertEqual([r["parent_id"] for r in csv.DictReader(stream, delimiter="\t")], ids)
            with out_deep.open(newline="", encoding="utf-8") as stream:
                self.assertEqual([r["root_id"] for r in csv.DictReader(stream, delimiter="\t")], ids)

    def test_candidate_probe_keeps_same_search_and_no_depth_surrogate(self) -> None:
        probe = (ROOT / "jobs/tools/cls_g0_runtime_probe.cpp").read_text(encoding="utf-8")
        candidate = (ROOT / "jobs/tools/cls_g0_valid_arm_stage.py").read_text(encoding="utf-8")
        self.assertIn("same_public_result(off.result, on.result)", probe)
        self.assertIn("SearchDecisionBound::Exact", probe)
        self.assertIn("attempt.all_actions_searched", probe)
        self.assertNotIn("go depth", probe.lower())
        self.assertIn("str(parent), str(candidate)", candidate)
        self.assertIn('"new_scan_searches": 0', candidate)
        self.assertIn('"strength_games": 0', candidate)
        self.assertIn('"promotion_authorized": False', candidate)
        self.assertIn('"bake_authorized": False', candidate)


if __name__ == "__main__":
    unittest.main()
