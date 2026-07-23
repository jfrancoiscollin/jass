#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from jobs.tests.test_stable_conversion_matrix import result_row, synthetic_contract


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/l3_conversion_2x2_report.py"
spec = importlib.util.spec_from_file_location("l3_conversion_2x2_report", TOOL)
report = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(report)


class Conversion2x2ReportTests(unittest.TestCase):
    def test_single_pinned_ply_cap_is_adjudicated_and_audited(self):
        contract = synthetic_contract()
        affected = contract.positions[170]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "standard_off/g0_g4"
            directory.mkdir(parents=True)
            handles = [
                (directory / f"s{shard}.jsonl").open("w", encoding="utf-8")
                for shard in range(16)
            ]
            try:
                for position in contract.positions:
                    row = result_row(position, "g0_g4", "D")
                    if position.position_id == affected.position_id:
                        row["reason"] = "ply cap"
                        row["plies"] = 400
                    handles[position.index % 16].write(
                        __import__("json").dumps(row) + "\n"
                    )
            finally:
                for handle in handles:
                    handle.close()

            with self.assertRaisesRegex(ValueError, "technical_rows=1"):
                report.validated_arm(
                    contract, Path(tmp), "standard_off", "g0_g4"
                )

            adjudications = []
            rows = report.validated_arm(
                contract,
                Path(tmp),
                "standard_off",
                "g0_g4",
                salvage={
                    "candidate": "standard_off",
                    "arm": "g0_g4",
                    "position_id": affected.position_id,
                    "cell": affected.cell,
                    "plies": 400,
                },
                adjudications=adjudications,
            )
            self.assertEqual(
                rows[affected.position_id]["reason"],
                report.matrix.SALVAGE_DRAW_REASON,
            )
            self.assertEqual(len(adjudications), 1)
            self.assertEqual(adjudications[0]["changes_to_raw_games"], 1)

    def test_factor_endpoints(self):
        cells = {
            "standard_off": {"attack_effect": 0.10},
            "standard_on": {"attack_effect": 0.00},
            "top3_off": {"attack_effect": -0.20},
            "top3_on": {"attack_effect": -0.50},
        }
        values = report.factor_endpoints(cells, "attack_effect")
        self.assertAlmostEqual(values["start_top3_main_effect"], -0.40)
        self.assertAlmostEqual(values["reweight_on_main_effect"], -0.20)
        self.assertAlmostEqual(values["start_x_reweight_interaction"], -0.20)

    def test_candidate_role_directions(self):
        ids = ["a", "b"]
        control = {
            key: {"outcome_plus2": outcome}
            for key, outcome in zip(ids, ("W", "L"), strict=True)
        }
        arms = {
            "g4_g0": {
                key: {"outcome_plus2": "W"} for key in ids
            },
            "g0_g4": {
                key: {"outcome_plus2": "L"} for key in ids
            },
            "g4_g4": {
                key: {"outcome_plus2": outcome}
                for key, outcome in zip(ids, ("W", "L"), strict=True)
            },
        }
        values = report.candidate_endpoints(ids, control, arms)
        self.assertEqual(values["attack_effect"], 1.0)
        self.assertEqual(values["defence_effect"], 1.0)
        self.assertEqual(values["joint_effect"], 0.0)
        self.assertEqual(values["role_interaction"], 0.0)

    def test_balanced_guard_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "s0.log").write_text("RESULT 30 20 14\n", encoding="utf-8")
            value = report.balanced_result(directory, 64)
            self.assertEqual(value["games"], 64)
            self.assertEqual(value["candidate_score_rate"], 0.625)
            (directory / "s1.log").write_text(
                "game skipped (timeout)\nRESULT 0 1 0\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "hidden as draw"):
                report.balanced_result(directory, 65)

    def test_end_to_end_matrix_and_balanced_round_trip(self):
        contract = synthetic_contract()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            matrix_root = root / "matrix"
            balanced_root = root / "balanced"

            def write_arm(directory: Path, arm: str, outcome: str = "D") -> None:
                directory.mkdir(parents=True)
                handles = [
                    (directory / f"s{shard}.jsonl").open("w", encoding="utf-8")
                    for shard in range(16)
                ]
                try:
                    for position in contract.positions:
                        row = result_row(position, arm, outcome)
                        handle = handles[position.index % 16]
                        handle.write(__import__("json").dumps(row) + "\n")
                finally:
                    for handle in handles:
                        handle.close()

            write_arm(matrix_root / "common/g0_g0", "g0_g0")
            for candidate in report.CANDIDATES:
                for arm in report.ARMS:
                    write_arm(matrix_root / candidate / arm, arm)
                directory = balanced_root / candidate
                directory.mkdir(parents=True)
                for shard in range(8):
                    (directory / f"s{shard}.log").write_text(
                        "RESULT 8 0 8\n", encoding="utf-8"
                    )

            original = report.matrix.load_pool_contract
            report.matrix.load_pool_contract = lambda *_: contract
            try:
                payload = report.build_report(SimpleNamespace(
                    pool=root / "pool.fen",
                    proof=root / "proof.jsonl",
                    matrix_root=matrix_root,
                    balanced_root=balanced_root,
                    balanced_games=128,
                    balanced_floor=0.40,
                    bootstrap=100,
                    seed=271828,
                ))
                affected = contract.positions[170]
                shard_path = (
                    matrix_root
                    / "standard_off/g0_g4"
                    / f"s{affected.index % 16}.jsonl"
                )
                shard_rows = [
                    __import__("json").loads(line)
                    for line in shard_path.read_text(encoding="utf-8").splitlines()
                ]
                for row in shard_rows:
                    if row["position_id"] == affected.position_id:
                        row["reason"] = "ply cap"
                        row["plies"] = 400
                shard_path.write_text(
                    "\n".join(
                        __import__("json").dumps(row) for row in shard_rows
                    ) + "\n",
                    encoding="utf-8",
                )
                salvaged = report.build_report(SimpleNamespace(
                    pool=root / "pool.fen",
                    proof=root / "proof.jsonl",
                    matrix_root=matrix_root,
                    balanced_root=balanced_root,
                    balanced_games=128,
                    balanced_floor=0.40,
                    bootstrap=100,
                    seed=271828,
                    salvage_candidate="standard_off",
                    salvage_arm="g0_g4",
                    salvage_position_id=affected.position_id,
                    salvage_cell=affected.cell,
                    salvage_plies=400,
                ))
            finally:
                report.matrix.load_pool_contract = original
            self.assertEqual(payload["decision"], "CONVERSION_2X2_G1_SCREEN_READY")
            self.assertTrue(payload["balanced_guard"]["pass"])
            self.assertEqual(payload["contract"]["positions"], 384)
            self.assertEqual(payload["candidate_endpoints"]["top3_on"]["attack_effect"], 0.0)
            self.assertEqual(
                salvaged["technical_status"],
                "derived_complete_single_ply_cap",
            )
            self.assertFalse(salvaged["original_zero_cap_gate_ready"])
            self.assertEqual(len(salvaged["adjudications"]), 1)


if __name__ == "__main__":
    unittest.main()
