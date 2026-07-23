#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "jobs/tools/stable_conversion_matrix.py"
SPEC = importlib.util.spec_from_file_location("stable_conversion_matrix", MODULE)
SCM = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SCM
SPEC.loader.exec_module(SCM)


def synthetic_contract() -> SCM.PoolContract:
    positions = []
    index = 0
    for cell in SCM.EXPECTED_CELLS:
        stratum, adv_field, stm_field = cell.split("|")
        advantaged = adv_field.split("=", 1)[1]
        stm = stm_field.split("=", 1)[1]
        for _ in range(32):
            positions.append(SCM.Position(
                index=index,
                position_id=f"{index + 1:064x}",
                fen=f"{stm}:W31,32:B1,2  {index}",
                cell=cell,
                stratum=stratum,
                advantaged=advantaged,
                stm=stm,
                source_unit=f"source:{index}",
            ))
            index += 1
    return SCM.PoolContract(
        pool_path="pool.fen",
        proof_path="proof.jsonl",
        pool_sha256="a" * 64,
        proof_sha256="b" * 64,
        positions=tuple(positions),
    )


def result_row(
    position: SCM.Position,
    arm: str,
    outcome: str = "D",
    reason: str | None = None,
) -> dict:
    adv_kind, disadv_kind = SCM.ARM_ROLES[arm]
    outcome_white = outcome if position.advantaged == "W" else {
        "W": "L", "D": "D", "L": "W",
    }[outcome]
    plies = 50
    if reason is None:
        if outcome == "D":
            reason = "25-move rule"
        else:
            loser = "W" if outcome_white == "L" else "B"
            plies = 0 if loser == position.stm else 1
            loser_role = "adv" if loser == position.advantaged else "disadv"
            loser_kind = (
                SCM.ARM_ROLES[arm][0]
                if loser_role == "adv" else SCM.ARM_ROLES[arm][1]
            )
            reason = f"no legal move from {arm}-{loser_role}-{loser_kind}"
    return {
        "schema": 1,
        "arm": arm,
        "index": position.index,
        "shard": position.index % SCM.SHARD_COUNT,
        "shards": SCM.SHARD_COUNT,
        "position_id": position.position_id,
        "fen": position.fen,
        "cell": position.cell,
        "stratum": position.stratum,
        "advantaged": position.advantaged,
        "source_unit": position.source_unit,
        "roles": {
            "advantaged_engine": adv_kind,
            "disadvantaged_engine": disadv_kind,
            "white_role": "advantaged" if position.advantaged == "W" else "disadvantaged",
            "black_role": "disadvantaged" if position.advantaged == "W" else "advantaged",
        },
        "outcome_white": outcome_white,
        "outcome_plus2": outcome,
        "reason": reason,
        "plies": plies,
        "elapsed_s": 1.0,
        "error": None,
        "config": {
            "depth": SCM.DEPTH,
            "game_timeout_s": SCM.GAME_TIMEOUT_S,
            "max_plies": SCM.MAX_PLIES,
            "search_params_sha256": "3" * 64,
            "scan_runtime_sha256": "4" * 64,
            "scan_hub_params_sha256": SCM.SCAN_HUB_PARAMS_SHA256,
        },
        "hashes": {
            "pool_sha256": "a" * 64,
            "proof_sha256": "b" * 64,
            "jass": {"sha256": "c" * 64},
            "scan": {"sha256": "d" * 64},
            "scan_runtime": {"sha256": "4" * 64},
            "scan_hub_params": {
                "sha256": SCM.SCAN_HUB_PARAMS_SHA256,
                "params": SCM.SCAN_HUB_PARAMS,
            },
            "g0": {"sha256": "e" * 64},
            "g4": {"sha256": "f" * 64},
            "search_params": {"sha256": "3" * 64},
            "matrix_runner": {"sha256": "1" * 64},
            "referee_harness": {"sha256": "2" * 64},
        },
    }


def matrix_rows(contract: SCM.PoolContract, outcomes: dict[str, str] | None = None):
    outcomes = outcomes or {}
    return {
        arm: [result_row(position, arm, outcomes.get(arm, "D"))
              for position in contract.positions]
        for arm in SCM.ARMS
    }


class StableConversionMatrixTests(unittest.TestCase):
    def test_role_assignment_and_plus2_perspective_are_colour_independent(self):
        adv, disadv = object(), object()
        white, black, roles = SCM.role_assignment("g4_g0", "B", adv, disadv)
        self.assertIs(white, disadv)
        self.assertIs(black, adv)
        self.assertEqual(roles["advantaged_engine"], "g4")
        self.assertEqual(roles["disadvantaged_engine"], "g0")
        self.assertEqual(roles["black_role"], "advantaged")
        self.assertEqual(SCM.outcome_from_advantaged("L", "B"), "W")
        self.assertEqual(SCM.outcome_from_advantaged("W", "B"), "L")
        self.assertEqual(SCM.outcome_from_advantaged("D", "W"), "D")

    def test_play_position_passes_fixed_contract_and_surfaces_engine_exception(self):
        position = synthetic_contract().positions[128]  # adv=B in TOP3 ordering
        adv, disadv = object(), object()
        referee = SimpleNamespace(has_legal_moves=lambda: False)
        bundle = SCM.PlayerBundle(adv, disadv, referee)
        seen = {}

        def fake_game(white, black, ref, fen, **kwargs):
            seen.update(white=white, black=black, ref=ref, fen=fen, kwargs=kwargs)
            return SimpleNamespace(outcome="L", reason="no legal move from x", plies=17)

        ticks = iter((5.0, 6.25))
        row = SCM.play_position(
            position, "g4_g0", 0, {}, bundle,
            play_game=fake_game, clock=lambda: next(ticks),
        )
        expected_white = disadv if position.advantaged == "B" else adv
        self.assertIs(seen["white"], expected_white)
        self.assertEqual(seen["kwargs"], {
            "depth": 10, "max_plies": 400, "game_timeout_s": 120.0,
        })
        expected = "W" if position.advantaged == "B" else "L"
        self.assertEqual(row["outcome_plus2"], expected)
        self.assertIsNone(row["error"])
        self.assertEqual(row["elapsed_s"], 1.25)

        def exploding(*_args, **_kwargs):
            raise TimeoutError("engine wedged")

        ticks = iter((10.0, 10.5))
        failed = SCM.play_position(
            position, "g4_g0", 0, {}, bundle,
            play_game=exploding, clock=lambda: next(ticks),
        )
        self.assertIsNone(failed["outcome_plus2"])
        self.assertIn("TimeoutError", failed["error"])
        self.assertEqual(failed["reason"], "engine exception")

    def test_referee_is_canonical_delegate_and_search_fingerprint_reaches_jass(self):
        sentinel = object()
        original_game = SCM.CVS.play_game
        original_engine = SCM.CVS.JassEngine
        calls = {}
        try:
            SCM.CVS.play_game = lambda *args, **kwargs: (
                calls.update(game=(args, kwargs)) or sentinel
            )
            self.assertIs(SCM.play_game_canonical("w", "b", "r", "fen", depth=10), sentinel)
            self.assertEqual(calls["game"][1]["depth"], 10)

            def fake_engine(path, **kwargs):
                calls["engine"] = (path, kwargs)
                return sentinel

            SCM.CVS.JassEngine = fake_engine
            args = SimpleNamespace(
                jass="jass", g0="g0.pjtw", g4="g4.pjtw",
                search_params="lmr_base=3,razor_max_depth=4",
            )
            self.assertIs(SCM._make_player("g4", "G4", args), sentinel)
            self.assertEqual(calls["engine"][1]["pattern_path"], "g4.pjtw")
            self.assertEqual(
                calls["engine"][1]["search_params"], args.search_params,
            )
        finally:
            SCM.CVS.play_game = original_game
            SCM.CVS.JassEngine = original_engine

    def test_wdl_statistics_report_raw_normalized_and_decisive_conversion(self):
        stats = SCM.wdl_stats(["W", "W", "D", "L"])
        self.assertEqual(stats["n"], 4)
        self.assertEqual((stats["W"], stats["D"], stats["L"]), (2, 1, 1))
        self.assertEqual(stats["score"], 0.625)
        self.assertEqual(stats["win_rate"], 0.5)
        self.assertEqual(stats["draw_rate"], 0.25)
        self.assertEqual(stats["loss_rate"], 0.25)
        self.assertEqual(stats["w_minus_l_raw"], 1)
        self.assertEqual(stats["w_minus_l_normalized"], 0.25)
        self.assertAlmostEqual(stats["decisive_win_rate"], 2 / 3)
        with self.assertRaisesRegex(ValueError, "n=0"):
            SCM.wdl_stats([])

    def test_factorial_paired_deltas_have_declared_directions(self):
        contract = synthetic_contract()
        rows = matrix_rows(contract, {
            "scan_scan": "D",
            "scan_g4": "W",
            "g4_scan": "L",
            "g0_g0": "D",
            "g4_g0": "W",
            "g0_g4": "L",
            "g4_g4": "W",
        })
        report = SCM.aggregate_rows(contract, rows, bootstrap_samples=20, bootstrap_seed=7)
        self.assertTrue(report["gate_ready"])
        self.assertEqual(report["arms"]["g4_g4"]["global"]["W"], 384)
        self.assertEqual(
            report["arms"]["g4_g4"]["global"]["termination_reasons"],
            {"no legal move from g4_g4-disadv-g4": 384},
        )
        global_deltas = report["paired_deltas"]["global"]
        self.assertEqual(global_deltas["attack"]["estimate"], 1.0)
        self.assertEqual(global_deltas["defense"]["estimate"], 1.0)
        self.assertEqual(global_deltas["joint"]["estimate"], 1.0)
        self.assertEqual(global_deltas["interaction"]["estimate"], 1.0)
        self.assertEqual(global_deltas["scan_attack_vs_g4"]["estimate"], 0.0)
        self.assertEqual(global_deltas["scan_defense_vs_g4"]["estimate"], 2.0)
        self.assertEqual(global_deltas["scan_joint_vs_g4"]["estimate"], -1.0)
        self.assertEqual(global_deltas["attack"]["ci95"], [1.0, 1.0])
        self.assertEqual(
            report["estimand"]["name"], "equal_weight_12_cell_standardized",
        )
        self.assertEqual(report["bootstrap"]["seed"], 7)
        self.assertEqual(report["inference"]["primary"], "paired_deltas.global.attack")
        self.assertIn(
            "both roles change",
            report["paired_deltas"]["interpretation"]["scan_joint_vs_g4"],
        )

    def test_strict_floor_duplicate_and_caps_fail_closed_without_stats(self):
        contract = synthetic_contract()
        rows = matrix_rows(contract)
        rows["g0_g0"].pop()
        short = SCM.aggregate_rows(contract, rows, bootstrap_samples=0)
        self.assertFalse(short["gate_ready"])
        self.assertEqual(short["status"], "technical_failure")
        self.assertIsNone(short["paired_deltas"])
        self.assertTrue(any("strict floor" in failure for failure in short["technical_failures"]))

        rows = matrix_rows(contract)
        rows["g4_g4"][0]["reason"] = "game time cap"
        capped = SCM.aggregate_rows(contract, rows, bootstrap_samples=0)
        self.assertFalse(capped["gate_ready"])
        self.assertEqual(capped["arms"]["g4_g4"]["technical_rows"], 1)
        self.assertIsNone(capped["arms"]["g4_g4"]["stats"])

        rows = matrix_rows(contract)
        rows["scan_scan"][1] = dict(rows["scan_scan"][0])
        duplicate = SCM.aggregate_rows(contract, rows, bootstrap_samples=0)
        self.assertFalse(duplicate["gate_ready"])
        self.assertTrue(any("duplicate position_id" in failure
                            for failure in duplicate["technical_failures"]))

        rows = matrix_rows(contract)
        rows["g4_g0"][0]["roles"]["advantaged_engine"] = "g0"
        rows["g4_g0"][1]["outcome_plus2"] = "W"
        perspective = SCM.aggregate_rows(contract, rows, bootstrap_samples=0)
        self.assertFalse(perspective["gate_ready"])
        self.assertTrue(any("role assignment mismatch" in failure
                            for failure in perspective["technical_failures"]))
        self.assertTrue(any("+2 perspective mismatch" in failure
                            for failure in perspective["technical_failures"]))

        rows = matrix_rows(contract)
        rows["g0_g0"][0]["hashes"]["search_params"] = {"sha256": "9" * 64}
        rows["g0_g0"][0]["config"]["search_params_sha256"] = "9" * 64
        search_drift = SCM.aggregate_rows(contract, rows, bootstrap_samples=0)
        self.assertFalse(search_drift["gate_ready"])
        self.assertTrue(any("provenance search_params" in failure
                            for failure in search_drift["technical_failures"]))

        rows = matrix_rows(contract)
        rows["g0_g0"][0]["hashes"]["g0"]["sha256"] = None
        missing_hash = SCM.aggregate_rows(contract, rows, bootstrap_samples=0)
        self.assertFalse(missing_hash["gate_ready"])
        self.assertTrue(any(
            "provenance g0: 1/2688 rows have a missing or invalid SHA256" in failure
            for failure in missing_hash["technical_failures"]
        ))

        rows = matrix_rows(contract)
        rows["g4_g0"][0]["outcome_white"] = "W"
        rows["g4_g0"][0]["outcome_plus2"] = (
            "W" if contract.positions[0].advantaged == "W" else "L"
        )
        draw_mismatch = SCM.aggregate_rows(contract, rows, bootstrap_samples=0)
        self.assertFalse(draw_mismatch["gate_ready"])
        self.assertTrue(any("draw reason/result mismatch" in failure
                            for failure in draw_mismatch["technical_failures"]))

        rows = matrix_rows(contract)
        terminal = rows["g0_g4"][0]
        terminal["reason"] = "no legal move from test"
        terminal["plies"] = 0
        terminal["outcome_white"] = "W"
        terminal["outcome_plus2"] = (
            "W" if contract.positions[0].advantaged == "W" else "L"
        )
        terminal_mismatch = SCM.aggregate_rows(contract, rows, bootstrap_samples=0)
        self.assertFalse(terminal_mismatch["gate_ready"])
        self.assertTrue(any("terminal reason/result mismatch" in failure
                            for failure in terminal_mismatch["technical_failures"]))

    def test_pool_reader_enforces_exact_384_rows_and_12_by_32(self):
        rng = random.Random(1234)
        pool_lines, proof_lines = [], []
        source_index = 0
        for cell in SCM.EXPECTED_CELLS:
            stratum, adv_field, stm_field = cell.split("|")
            low, high = (int(value) for value in stratum.split("v"))
            adv = adv_field.split("=", 1)[1]
            stm = stm_field.split("=", 1)[1]
            for _ in range(32):
                total = low + high
                squares = rng.sample(range(1, 51), total)
                white_count = high if adv == "W" else low
                white = sorted(squares[:white_count])
                black = sorted(squares[white_count:])
                fen = f"{stm}:W{','.join(map(str, white))}:B{','.join(map(str, black))}"
                canonical, position_id, facts = SCM._board_identity(fen)
                pool_lines.append(f"{canonical}  # id={position_id[:16]}")
                proof_lines.append(json.dumps({
                    "schema": 1,
                    "position_id": position_id,
                    "fen": canonical,
                    "cell": cell,
                    "material": facts,
                    "stability": {
                        "scope": "all_legal_first_plies_only",
                        "certifies_theoretical_win": False,
                        "gap_after_any_legal_first_ply": 2,
                        "quiet_white": True,
                        "quiet_black": True,
                        "immediate_promotion_white": False,
                        "immediate_promotion_black": False,
                    },
                    "provenance": {
                        "source_unit": f"opening:{source_index}",
                        "source_outcome_not_used_for_selection": True,
                    },
                }, sort_keys=True))
                source_index += 1

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pool, proof = root / "pool.fen", root / "proof.jsonl"
            pool.write_text("\n".join(pool_lines) + "\n", encoding="utf-8")
            proof.write_text("\n".join(proof_lines) + "\n", encoding="utf-8")
            contract = SCM.load_pool_contract(pool, proof)
            self.assertEqual(len(contract.positions), 384)
            self.assertEqual(len({pos.cell for pos in contract.positions}), 12)

            proof.write_text("\n".join(proof_lines[:-1]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "strict floor"):
                SCM.load_pool_contract(pool, proof)

    def test_progress_heartbeat_is_atomic_and_machine_readable(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "progress.json"
            started = SCM.time.monotonic() - 2.0
            SCM._write_progress(
                path, arm="g0_g0", shard=3, completed=4, expected=24,
                started=started, error_count=1,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["completed"], 4)
            self.assertEqual(payload["expected"], 24)
            self.assertEqual(payload["status"], "running")
            self.assertGreater(payload["games_per_second"], 0)

    def test_aggregate_cli_round_trips_shard_jsonl_to_report(self):
        contract = synthetic_contract()
        rows = matrix_rows(contract)
        original_loader = SCM.load_pool_contract
        try:
            SCM.load_pool_contract = lambda _pool, _proof: contract
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                argv = [
                    "aggregate", "--pool", "pool.fen", "--proof", "proof.jsonl",
                    "--bootstrap-samples", "0", "--output", str(root / "report.json"),
                ]
                for arm in SCM.ARMS:
                    path = root / f"{arm}.jsonl"
                    path.write_text(
                        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows[arm]),
                        encoding="utf-8",
                    )
                    argv.extend(("--result", f"{arm}={path}"))
                run_config = {
                    "arms": list(SCM.ARMS),
                    "games_per_arm": 384,
                    "budget": {
                        "kind": "fixed_depth", "depth": 10, "max_plies": 400,
                    },
                    "timeouts_seconds": {"game": 120},
                    "nshards": 16,
                    "pool": {
                        "pool_sha256": contract.pool_sha256,
                        "proof_sha256": contract.proof_sha256,
                    },
                    "evaluated_models": {"search_params_sha256": "3" * 64},
                    "scan": {
                        "binary_sha256": "d" * 64,
                        "runtime_sha256": "4" * 64,
                        "hub_params": SCM.SCAN_HUB_PARAMS,
                        "hub_params_sha256": SCM.SCAN_HUB_PARAMS_SHA256,
                    },
                }
                run_path = root / "run.json"
                run_path.write_text(
                    json.dumps(run_config, sort_keys=True) + "\n", encoding="utf-8",
                )
                argv.extend(("--run-config", str(run_path)))
                args = SCM.build_parser().parse_args(argv)
                self.assertEqual(SCM.aggregate_command(args), 0)
                report = json.loads((root / "report.json").read_text(encoding="utf-8"))
                self.assertEqual(report["technical_status"], "complete")
                self.assertEqual(report["games_per_arm"], 384)
                self.assertEqual(report["total_games"], 2688)
                self.assertEqual(report["arms"]["scan_scan"]["global"]["n"], 384)
                self.assertIn("run_config", report["inputs"])

                run_config["scan"]["runtime_sha256"] = "5" * 64
                run_path.write_text(
                    json.dumps(run_config, sort_keys=True) + "\n", encoding="utf-8",
                )
                drift_output = root / "drift.json"
                drift_argv = list(argv)
                drift_argv[drift_argv.index(str(root / "report.json"))] = str(drift_output)
                drift_args = SCM.build_parser().parse_args(drift_argv)
                self.assertEqual(SCM.aggregate_command(drift_args), 2)
                drift = json.loads(drift_output.read_text(encoding="utf-8"))
                self.assertTrue(any(
                    "Scan runtime hash mismatch" in failure
                    for failure in drift["technical_failures"]
                ))
        finally:
            SCM.load_pool_contract = original_loader


if __name__ == "__main__":
    unittest.main()
