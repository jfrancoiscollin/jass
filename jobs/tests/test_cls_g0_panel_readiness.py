from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock

from jobs.tools import cls_g0_panel_readiness as subject


def fens(n=2100):
    return [f"W:W{a},{b}:B{c}" for a in range(3, 51) for b in range(a + 1, 51)
            for c in range(1, 3)][:n]


def raw(pool):
    return ("# jass synthetic opening pool\n# seed=2026092011\n" +
            "\n".join(f"{fen} # synthetic-opening-{index}" for index, fen in enumerate(pool)) + "\n").encode()


class ReadinessContractTests(unittest.TestCase):
    @staticmethod
    def _game(task, white):
        request = ({"side": "A", "wall_seconds": .119, "requested_movetime_ms": 100}
                   if task["kind"] == "timed" else {"side": "A", "wall_seconds": .4, "requested_depth": 3})
        return {"opening": task["opening"], "a_is_white": white, "outcome": "D", "score_a": .5,
                "reason": "3-fold repetition", "plies": 1, "fens": [task["opening"], task["opening"]],
                "moves": ["1-2"], "warmup_requests": [{"side": "A", "requested_depth": 1}, {"side": "B", "requested_depth": 1}],
                "requests": [request], "game_wall_seconds": .2}

    def test_frozen_budget_and_task_plan(self):
        pool = fens(subject.POOL_SIZE)
        seal = subject.seal_openings(raw(pool), raw(pool), set())
        tasks = subject.make_readiness_tasks(Path("/scratch"), Path("/scratch/jass"), seal, set())
        self.assertEqual((subject.TOTAL_GAMES, subject.MAX_SEARCHES), (56, 9072))
        self.assertEqual(len(tasks), 28)
        self.assertTrue(all(task["mode"] == "rehearsal" and task["arm_a"] == task["arm_b"] for task in tasks))
        self.assertEqual(sum(task["kind"] == "deterministic" for task in tasks), 4)
        self.assertEqual(sum(task["kind"] == "timed" for task in tasks), 24)

    def test_replay_seeded_selection_is_stable_and_excluded(self):
        pool = fens(subject.POOL_SIZE)
        forbidden = {subject.canonical_identity(pool[0])}
        first = subject.seal_openings(raw(pool), raw(pool), forbidden)
        second = subject.seal_openings(raw(pool), raw(pool), forbidden)
        self.assertEqual(first, second)
        self.assertNotIn(next(iter(forbidden)), {r["canonical"] for r in first["main"] + first["representative"]})
        with self.assertRaisesRegex(ValueError, "POOL_REPLAY_MISMATCH"):
            subject.seal_openings(raw(pool), raw(list(reversed(pool))), set())
        with self.assertRaisesRegex(ValueError, "POOL_REPLAY_MISMATCH"):
            subject.seal_openings(raw(pool), raw(pool) + b"trailing", set())
        with self.assertRaisesRegex(ValueError, "POOL_REPLAY_MISMATCH"):
            subject.seal_openings(raw(pool), raw(pool).replace(b"synthetic-opening-0", b"synthetic-opening-X", 1), set())

    def test_exact_audit_gate_fails_closed(self):
        record = {"job_id": subject.AUDIT_2072_JOB, "attempt_id": subject.AUDIT_2072_ATTEMPT,
                  "code_sha": subject.AUDIT_2072_CODE, "terminal": subject.AUDIT_2072_TERMINAL,
                  "publication_verdict": subject.AUDIT_2072_VERDICT, "launch_receipt_sha256": subject.AUDIT_2072_LAUNCH_RECEIPT}
        receipt = {"record": record, "readback": {**record, "verdict": subject.AUDIT_2072_VERDICT,
                   "new_match_admitted": False, "completed_phases": ["authenticate-archives", "verify-native-continuity", "replay-2069", "audit-all-g0-roots", "publish-audit"],
                   "summary": {"terminal": subject.AUDIT_2072_TERMINAL, "historical_2069_raw_audit_passed": True, "native_continuity_passed": True,
                               "frozen_g0_verdicts": {"HIER": "FAIL", "LOCAL": "FAIL", "WDL": "FAIL"}},
                   "raw_audit": {"passed": True, "historical_requests_verified": 62005, "native_terminal_legality_checks": 576},
                   "publication": {"state": "verified", "result_state": "completed",
                       "job_id": subject.AUDIT_2072_JOB, "attempt_id": subject.AUDIT_2072_ATTEMPT,
                       "code_sha": subject.AUDIT_2072_CODE, "host": "cpx62", "exit_code": 0, "files": [
                       {"local_name": "launch-receipt.json", "sha256": subject.AUDIT_2072_LAUNCH_RECEIPT},
                       {"local_name": "historical-2069-raw-audit.json", "sha256": "dd5fd56e6782fc89459fbff936d127029b602fa648ab494d7ca50cc819c9f389"}]}}}
        subject.require_authenticated_audit_2072(receipt)
        receipt["readback"]["summary"]["native_continuity_passed"] = False
        with self.assertRaisesRegex(ValueError, "AUDIT_2072_NATIVE_CONTINUITY"):
            subject.require_authenticated_audit_2072(receipt)

    def test_committed_2072_readback_is_a_parser_fixture_only(self):
        path = Path(__file__).resolve().parents[2] / "docs/operations/CLS_PANEL_AUDIT_2072_READBACK_20260921.json"
        fixture = __import__("json").loads(path.read_text(encoding="utf-8"))
        subject.require_authenticated_audit_2072(fixture)
        subject.require_authenticated_audit_2072(fixture["readback"])

    def test_explicit_model_loader_rejects_unverified_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); model = root / "CURRICULUM.pjtw"; model.write_bytes(b"model")
            task = {"arm_a": "CURRICULUM", "arm_b": "CURRICULUM", "model_a": str(model), "model_b": str(model)}
            with self.assertRaisesRegex(ValueError, "MODEL_SHA"):
                subject.validate_explicit_models(task)

    def test_effect_accounting_counts_failed_started_work(self):
        subject.validate_effect_counts({"strength_games": 56, "new_jass_searches": 9072})
        with self.assertRaisesRegex(ValueError, "READINESS_GAME_BUDGET"):
            subject.validate_effect_counts({"strength_games": 57, "new_jass_searches": 0})
        with self.assertRaisesRegex(ValueError, "READINESS_FORBIDDEN_EFFECT"):
            subject.validate_effect_counts({"strength_games": 0, "new_jass_searches": 0, "fits": 1})

    def test_pair_wall_factor_uses_independent_whole_block_clock(self):
        pool = fens(subject.POOL_SIZE); seal = subject.seal_openings(raw(pool), raw(pool), set())
        tasks = subject.make_readiness_tasks(Path("/scratch"), Path("/scratch/jass"), seal, set())
        rows = [{**{k: task[k] for k in ("task_id", "opening", "arm_a", "arm_b", "kind")},
                 "games": [self._game(task, True), self._game(task, False)], "pair_wall_seconds": 1.0} for task in tasks]
        report = subject.validate_readiness_rows(rows, tasks, timed_block_wall_seconds=60.0)
        self.assertEqual(report["parallelism_factor"], 10.0)
        self.assertTrue(all(value <= 3000 for value in report["projected_main_work_seconds"].values()))
        with self.assertRaisesRegex(ValueError, "NOMINAL_CADENCE"):
            bad = rows[4]["games"][0]; bad["requests"][0]["wall_seconds"] = .121
            subject.validate_readiness_rows(rows, tasks, timed_block_wall_seconds=60.0)

    def test_adapter_warms_fresh_players_and_separates_depth3_from_timed(self):
        events = []
        class Move:
            def jass_apply_str(self): return "1-2"
        class Engine:
            def __init__(self, _exe, *, label, **_kwargs): events.append(("open", label)); self.label = label
            def new_game(self): events.append(("new", self.label))
            def set_position_fen(self, _fen): events.append(("fen", self.label))
            def go(self, *, depth): return self.go_verbose(depth=depth)
            def go_verbose(self, **_kwargs): return Move(), ["ready depth=3 nodes=1 evalcalls=1"]
            def close(self): events.append(("close", self.label))
        class Referee:
            def __init__(self, _exe): events.append(("ref",))
            def apply_move(self, _move): return True
            def close(self): events.append(("close", "ref"))
        call = {}
        def play_game(white, _black, _ref, opening, **kwargs):
            call.update(kwargs)
            white.go_verbose(depth=3)
            return SimpleNamespace(outcome="D", reason="3-fold repetition", plies=1,
                                   fens=[opening, opening], moves=["1-2"])
        fake = SimpleNamespace(JassEngine=Engine, Referee=Referee, play_game=play_game)
        task = {"mode": "rehearsal", "kind": "deterministic", "arm_a": "CURRICULUM", "arm_b": "CURRICULUM",
                "exe": "fake", "model_a": "a", "model_b": "b", "opening": "W:W3,4:B1"}
        counts = {"strength_games": 0, "new_jass_searches": 0}
        with mock.patch.dict(sys.modules, {"jobs.tools.calibrate_vs_scan": fake}), \
             mock.patch.object(subject, "validate_explicit_models"), \
             mock.patch.object(subject.time, "monotonic", side_effect=iter(range(1, 100))):
            row = subject.native_self_pair(task, True, counts, lambda: None)
        self.assertEqual(counts["strength_games"], 1)
        self.assertEqual([q["requested_depth"] for q in row["warmup_requests"]], [1, 1])
        self.assertEqual(row["requests"][0]["requested_depth"], 3)
        self.assertNotIn("requested_movetime_ms", row["requests"][0])
        self.assertEqual((call["depth"], call["movetime"], call["max_plies"], call["game_timeout_s"]), (3, None, 160, 60))
        self.assertEqual(events.count(("open", "A")), 1)
        self.assertEqual(events.count(("open", "B")), 1)

    def test_adapter_counts_failed_startup_and_closes_owned_engine(self):
        events = []
        class Engine:
            def __init__(self, _exe, *, label, **_kwargs):
                events.append(("open", label))
                if label == "B": raise RuntimeError("synthetic startup failure")
                self.label = label
            def new_game(self): pass
            def set_position_fen(self, _fen): pass
            def go(self, *, depth): return None
            def close(self): events.append(("close", self.label))
        fake = SimpleNamespace(JassEngine=Engine, Referee=object, play_game=lambda *_a, **_k: None)
        task = {"mode": "rehearsal", "kind": "timed", "arm_a": "CURRICULUM", "arm_b": "CURRICULUM",
                "exe": "fake", "model_a": "a", "model_b": "b", "opening": "W:W3,4:B1"}
        counts = {"strength_games": 0, "new_jass_searches": 0}
        with mock.patch.dict(sys.modules, {"jobs.tools.calibrate_vs_scan": fake}), \
             mock.patch.object(subject, "validate_explicit_models"):
            with self.assertRaisesRegex(RuntimeError, "startup failure"):
                subject.native_self_pair(task, True, counts, lambda: None)
        self.assertEqual(counts["strength_games"], 1)
        self.assertIn(("close", "A"), events)


if __name__ == "__main__":
    unittest.main()
