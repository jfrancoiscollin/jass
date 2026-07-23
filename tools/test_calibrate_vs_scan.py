#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Focused tests for calibrate_vs_scan's FMJD 25-move clock."""

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import calibrate_vs_scan as jobs_calibrate
from tools import calibrate_vs_scan as root_calibrate


CALIBRATION_MODULES = (root_calibrate, jobs_calibrate)


def _unique_scripted_fen(side, ordinal, black_token="K1"):
    # Encode the ordinal in harmless extra white kings so long scripted tests
    # do not accidentally trigger the repetition rule they are not testing.
    extras = [f"K{square}" for bit, square in enumerate(range(2, 8))
              if ordinal & (1 << bit)]
    white = ",".join(["K28", *extras])
    return f"{side}:W{white}:B{black_token}"


class _ScriptedEngine:
    def __init__(self, label, moves):
        self.label = label
        self._moves = iter(moves)

    def new_game(self):
        pass

    def go_from(self, *_args, **_kwargs):
        return next(self._moves)


class _ScriptedReferee:
    def __init__(self, fens_after_moves, has_legal_moves=True):
        self._fens_after_moves = iter(fens_after_moves)
        self._fen = ""
        self._has_legal_moves = has_legal_moves

    def set_position_fen(self, fen):
        self._fen = fen

    def scan_pos(self):
        return "W" + "e" * 50, []

    def apply_move(self, _move):
        self._fen = next(self._fens_after_moves)
        return True

    def current_fen(self):
        return self._fen

    def has_legal_moves(self):
        return self._has_legal_moves


class _RecordingHub:
    def __init__(self):
        self.commands = []

    def _send(self, command):
        self.commands.append(command)

    def _read_until(self, _predicate):
        return ["ok"]


class TestAdvance25MoveClock(unittest.TestCase):
    def test_jass_threads_use_the_native_setoption_contract(self):
        for module in CALIBRATION_MODULES:
            with self.subTest(module=module.__name__):
                original_init = module.EngineProc.__init__
                original_send = module.EngineProc._send
                original_read = module.EngineProc._read_until
                try:
                    def fake_init(instance, _argv, label, cwd=None):
                        instance.label = label
                        instance.commands = []

                    def fake_send(instance, command):
                        instance.commands.append(command)

                    def fake_read(instance, _predicate, timeout_s=60.0):
                        return ["ready"] if instance.commands[-1] == "hello" else ["ok"]

                    module.EngineProc.__init__ = fake_init
                    module.EngineProc._send = fake_send
                    module.EngineProc._read_until = fake_read
                    engine = module.JassEngine("jass", threads=4)
                    self.assertEqual(
                        engine.commands, ["hello", "setoption threads 4"],
                    )
                finally:
                    module.EngineProc.__init__ = original_init
                    module.EngineProc._send = original_send
                    module.EngineProc._read_until = original_read

    def test_scan_runtime_parameter_contract_is_complete_and_parseable(self):
        echoed = [
            'id name=Scan version=3.1 author="Fabien Letouzey"',
            *[
                f"param name={name} value={value} type=test"
                for name, value in root_calibrate.ScanEngine.RUNTIME_PARAMS
            ],
            "wait",
        ]
        for module in CALIBRATION_MODULES:
            with self.subTest(module=module.__name__):
                expected = dict(module.ScanEngine.RUNTIME_PARAMS)
                self.assertEqual(module.ScanEngine._hub_params(echoed), expected)
                self.assertEqual(set(expected), {
                    "variant", "book", "book-ply", "book-margin",
                    "ponder", "threads", "tt-size", "bb-size",
                })
                self.assertEqual(expected["variant"], "normal")
                self.assertEqual(expected["book"], "false")
                self.assertEqual(expected["threads"], "1")
                self.assertEqual(expected["tt-size"], "24")
                self.assertEqual(expected["bb-size"], "0")

    def test_capture_application_preserves_exact_captured_set(self):
        for module in CALIBRATION_MODULES:
            with self.subTest(module=module.__name__):
                move = module.Move(34, 43, (38, 17, 29))
                self.assertEqual(
                    move.jass_apply_str(), "34x43 captures=17,29,38"
                )
                with self.assertRaisesRegex(
                    ValueError, "lacks captured-square identity"
                ):
                    module.parse_jass_bestmove(
                        "bestmove 34x43 score=0 depth=10 nodes=1"
                    )
                with self.assertRaisesRegex(ValueError, "unparseable Scan move"):
                    module.parse_scan_move("34x43")

    def test_referee_sends_exact_capture_identity(self):
        for module in CALIBRATION_MODULES:
            with self.subTest(module=module.__name__):
                hub = _RecordingHub()
                referee = module.Referee.__new__(module.Referee)
                referee.j = hub
                referee._scan_history = []
                move = module.Move(34, 43, (17, 29, 38))

                self.assertTrue(referee.apply_move(move))
                self.assertEqual(
                    hub.commands, ["apply 34x43 captures=17,29,38"]
                )
                self.assertEqual(referee._scan_history, ["34x43x17x29x38"])

    def test_capture_resets_clock_even_when_a_king_moves(self):
        for module in CALIBRATION_MODULES:
            with self.subTest(module=module.__name__):
                move = module.Move(28, 17, (22,))
                self.assertEqual(
                    module._advance_25_move_clock(49, "W:WK28:B22", move),
                    0,
                )

    def test_quiet_man_move_resets_clock_for_either_colour(self):
        for module in CALIBRATION_MODULES:
            cases = (
                ("W:W28:BK1", module.Move(28, 23)),
                ("B:WK50:B22", module.Move(22, 27)),
            )
            for fen, move in cases:
                with self.subTest(module=module.__name__, fen=fen):
                    self.assertEqual(
                        module._advance_25_move_clock(49, fen, move), 0)

    def test_promoting_man_move_resets_clock(self):
        for module in CALIBRATION_MODULES:
            with self.subTest(module=module.__name__):
                self.assertEqual(
                    module._advance_25_move_clock(
                        49, "W:W6:BK40", module.Move(6, 1)),
                    0,
                )

    def test_quiet_king_move_advances_clock(self):
        for module in CALIBRATION_MODULES:
            with self.subTest(module=module.__name__):
                self.assertEqual(
                    module._advance_25_move_clock(
                        49, "W:WK28:BK1", module.Move(28, 23)),
                    50,
                )

    def test_play_game_does_not_adjudicate_after_late_man_move(self):
        # The first 49 plies are quiet king moves. On ply 50 Black moves a
        # man, so the clock must reset instead of producing a 25-move draw.
        for module in CALIBRATION_MODULES:
            with self.subTest(module=module.__name__):
                white = _ScriptedEngine(
                    "white", [module.Move(28, 23)] * 25)
                black = _ScriptedEngine(
                    "black", [module.Move(1, 6)] * 25)
                fens = []
                for ply in range(1, 51):
                    side = "B" if ply % 2 else "W"
                    black_piece = "1" if ply == 49 else "K1"
                    fens.append(_unique_scripted_fen(
                        side, ply, black_token=black_piece))
                referee = _ScriptedReferee(fens)

                result = module.play_game(
                    white, black, referee, "W:WK28:BK1",
                    depth=1, max_plies=50)

                self.assertEqual(result.reason, "ply cap")

    def test_play_game_adjudicates_threefold_repetition(self):
        cycle = [
            "B:WK23:BK1",
            "W:WK23:BK6",
            "B:WK28:BK6",
            "W:WK28:BK1",
        ]
        for module in CALIBRATION_MODULES:
            with self.subTest(module=module.__name__):
                white = _ScriptedEngine(
                    "white", [module.Move(28, 23), module.Move(23, 28)] * 2)
                black = _ScriptedEngine(
                    "black", [module.Move(1, 6), module.Move(6, 1)] * 2)
                referee = _ScriptedReferee(cycle * 2)

                result = module.play_game(
                    white, black, referee, "W:WK28:BK1",
                    depth=1, max_plies=20)

                self.assertEqual(result.reason, "3-fold repetition")
                self.assertEqual(result.plies, 8)

    def test_terminal_position_precedes_25_move_draw(self):
        for module in CALIBRATION_MODULES:
            with self.subTest(module=module.__name__):
                white = _ScriptedEngine("white", [module.Move(28, 23)] * 25)
                black = _ScriptedEngine("black", [module.Move(1, 6)] * 25)
                fens = []
                for ply in range(1, 51):
                    side = "B" if ply % 2 else "W"
                    fens.append(_unique_scripted_fen(side, ply))
                referee = _ScriptedReferee(fens, has_legal_moves=False)

                result = module.play_game(
                    white, black, referee, "W:WK28:BK1",
                    depth=1, max_plies=60)

                self.assertEqual(result.outcome, "L")
                self.assertEqual(result.reason, "no legal move from white")
                self.assertEqual(result.plies, 50)


if __name__ == "__main__":
    unittest.main()
