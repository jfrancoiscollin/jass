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
            "WDL": "eabe71068dbc6aeb519a61c730d18586e75c8b72308ecd340de08fe2e18deed6",
            "HIER": "95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628",
        })
        self.assertEqual(stage.HIER_SOURCE_JOB, "cpx62-2062-l3-cls-hier-l2-hier-candidate-rehearsal-v1")
        self.assertEqual(stage.HIER_SOURCE_ATTEMPT, "20260919T142226Z-a28f1049")
        self.assertEqual(stage.HIER_SOURCE_CODE, "a28f10491d94ca451932b0e7b46df7cdf3b7e1c8")
        self.assertEqual(
            stage.HIER_SOURCE_LAUNCH_RECEIPT,
            "68203e5cd3fe40ea92c24bc2dfdc83c94cc52c257bbea871ed4e149b0873194e",
        )
        self.assertEqual(stage.EXPECTED_SEARCHES, 1536)
        self.assertEqual(gate.ROOTS, 512)
        self.assertEqual(gate.ROOTS_PER_PHASE, 128)
        self.assertEqual(gate.PRIMARY_BUDGET, 200_000)
        self.assertEqual(gate.BOOTSTRAP_REPLICATES, 100_000)
        self.assertEqual(gate.BOOTSTRAP_SEED, 2026091605)


    def test_hier_source_authentication_is_fail_closed_and_one_factor(self) -> None:
        source = (ROOT / "jobs/tools/cls_g0_valid_arm_stage.py").read_text(encoding="utf-8")
        self.assertIn('"terminal": "CLS_HIER_CANDIDATE_FIT_READY_V1"', source)
        self.assertIn('"hier_l2": 1e-5', source)
        self.assertIn('"l2": 1e-5', source)
        self.assertIn('"varied_factor": "hier_l2"', source)
        self.assertIn('"next_stage": "RUN_FROZEN_CLS_G0"', source)
        self.assertIn('"promotion_authorized": False', source)
        self.assertIn('"bake_authorized": False', source)
        self.assertIn('return authenticate_hier_candidate(work)', source)

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

    def test_native_probe_executes_exact_frozen_id_file_order(self) -> None:
        # Regression for 2045: consume the frozen ID file in its exact ordinal order.
        probe = (ROOT / "jobs/tools/cls_g0_runtime_probe.cpp").read_text(encoding="utf-8")
        self.assertIn("std::vector<std::uint32_t> load_ids", probe)
        self.assertIn("out.push_back(id);", probe)
        self.assertIn("const std::vector<std::uint32_t>& ids", probe)
        self.assertIn("ordered_positions[static_cast<std::size_t>(where - ids.begin())] = position;", probe)
        self.assertIn("roots.push_back({ids[ordinal], *ordered_positions[ordinal]});", probe)
        self.assertNotIn("std::unordered_set<std::uint32_t> load_ids", probe)

    def test_candidate_probe_keeps_same_search_and_no_depth_surrogate(self) -> None:
        probe = (ROOT / "jobs/tools/cls_g0_runtime_probe.cpp").read_text(encoding="utf-8")
        candidate = (ROOT / "jobs/tools/cls_g0_valid_arm_stage.py").read_text(encoding="utf-8")
        self.assertIn("same_public_result(off.result, on.result)", probe)
        self.assertIn("SearchDecisionBound::Exact", probe)
        self.assertIn("attempt.all_actions_searched", probe)
        self.assertNotIn("go depth", probe.lower())
        self.assertIn("std::vector<std::optional<std::uint64_t>> candidate_nodes_to_target", probe)
        self.assertIn("candidate_missing_roots", probe)
        self.assertIn('\\"nodes_to_depth_surrogate_used\\": false', probe)
        self.assertNotIn("missing/invalid candidate same-search nodes-to-depth", probe)
        self.assertIn("invalid candidate same-search nodes-to-depth", probe)
        self.assertIn("str(parent), str(candidate)", candidate)
        self.assertIn('"new_scan_searches": 0', candidate)
        self.assertIn('"strength_games": 0', candidate)
        self.assertIn('"promotion_authorized": False', candidate)
        self.assertIn('"bake_authorized": False', candidate)

    def test_missing_same_search_receipt_is_terminal_fail_without_surrogate(self) -> None:
        report = {
            "parent_nodes_to_depth_missing_roots": [],
            "candidate_nodes_to_depth_missing_roots": [20],
            "hard_nodes_to_depth_failure_count": 1,
            "hard_nodes_to_depth_failure_roots": [20],
            "nodes_to_depth_surrogate_used": False,
        }
        result = stage.hard_nodes_to_depth_failure_result(report, ["10", "20"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["terminal"], gate.FAIL_TERMINAL)
        self.assertFalse(result["pass"])
        self.assertFalse(result["gates"]["nodes_to_depth"]["pass"])
        self.assertEqual(result["gates"]["nodes_to_depth"]["threshold"], gate.NODES_TO_DEPTH_CEILING)
        self.assertEqual(result["hard_nodes_to_depth_failure"]["roots"], ["20"])
        self.assertFalse(result["hard_nodes_to_depth_failure"]["surrogate_used"])
        self.assertFalse(result["bootstrap"]["performed"])
        self.assertEqual(result["bootstrap"]["seed"], gate.BOOTSTRAP_SEED)
        self.assertEqual(result["alpha_spent"], 0)
        self.assertFalse(result["promotion_authorized"])
        self.assertFalse(result["bake_authorized"])

    def test_missing_receipt_hard_inventory_uses_frozen_root_order(self) -> None:
        report = {
            "parent_nodes_to_depth_missing_roots": [10],
            "candidate_nodes_to_depth_missing_roots": [20],
            "hard_nodes_to_depth_failure_count": 2,
            "hard_nodes_to_depth_failure_roots": [20, 10],
            "nodes_to_depth_surrogate_used": False,
        }
        result = stage.hard_nodes_to_depth_failure_result(report, ["20", "10"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["hard_nodes_to_depth_failure"]["roots"], ["20", "10"])

    def test_missing_receipt_inventory_drift_fails_technically(self) -> None:
        bad = {
            "parent_nodes_to_depth_missing_roots": [],
            "candidate_nodes_to_depth_missing_roots": [30],
            "hard_nodes_to_depth_failure_count": 1,
            "hard_nodes_to_depth_failure_roots": [30],
            "nodes_to_depth_surrogate_used": False,
        }
        with self.assertRaises(stage.StageError):
            stage.hard_nodes_to_depth_failure_result(bad, ["10", "20"])


if __name__ == "__main__":
    unittest.main()
