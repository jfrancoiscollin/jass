"""An engine that fails to move must abort the cell, not lose the game.

Both regressions covered here were found while diagnosing the TURNOVER
probe against Scan (home-0997/0998), where a cell reported 0.0 with four
losses out of four and looked like a crushing defeat rather than a broken
run. The third test pins the book asymmetry: `no_book=True` was declared by
every caller and honoured by none.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import calibrate_vs_scan as cvs  # noqa: E402


class FakeJass:
    """Duck-types JassEngine closely enough for play_game: the loop only
    branches on `isinstance(..., JassEngine)`, so this stands in for the
    Scan side (which play_game addresses through `go_from`)."""
    label = "FakeScan"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def new_game(self):
        pass

    def go_from(self, scan_pos, scan_moves, depth=None, movetime=None):
        self.calls += 1
        return self.replies.pop(0)


class FakeReferee:
    def __init__(self, has_moves, fen="W:W31:B20"):
        self._has_moves = has_moves
        self._fen = fen

    def set_position_fen(self, fen):
        self._fen = fen

    def current_fen(self):
        return self._fen

    def has_legal_moves(self):
        return self._has_moves

    def scan_pos(self):
        return ("W" + "e" * 50, [])

    def apply_move(self, move):
        return True


class NoMoveRaisesTest(unittest.TestCase):
    def test_missing_move_with_legal_moves_available_aborts(self):
        """The old code scored this as a loss for the failing side."""
        engine = FakeJass([None])
        with self.assertRaises(cvs.EngineFailure) as ctx:
            cvs.play_game(engine, engine, FakeReferee(has_moves=True),
                          "W:W31:B20", depth=4)
        self.assertIn("FakeScan", str(ctx.exception))
        self.assertIn("no move", str(ctx.exception))

    def test_null_move_with_legal_moves_available_aborts(self):
        engine = FakeJass([cvs.Move(0, 0, [])])
        with self.assertRaises(cvs.EngineFailure):
            cvs.play_game(engine, engine, FakeReferee(has_moves=True),
                          "W:W31:B20", depth=4)

    def test_missing_move_in_a_terminal_position_is_still_a_loss(self):
        """A side with nothing to play has genuinely lost — unchanged."""
        engine = FakeJass([None])
        result = cvs.play_game(engine, engine, FakeReferee(has_moves=False),
                               "W:W31:B20", depth=4)
        self.assertEqual(result.outcome, "L")
        self.assertIn("no legal move", result.reason)


class JassArgvTest(unittest.TestCase):
    def test_no_book_alone_does_not_disable_the_book(self):
        """Preserved on purpose: every gate published so far ran this way."""
        argv = cvs.jass_argv("/bin/jass", no_book=True)
        self.assertNotIn("--no-book", argv)

    def test_enforce_no_book_disables_the_book(self):
        argv = cvs.jass_argv("/bin/jass", no_book=True, enforce_no_book=True)
        self.assertIn("--no-book", argv)

    def test_an_explicit_book_wins_over_enforce_no_book(self):
        argv = cvs.jass_argv("/bin/jass", no_book=True, enforce_no_book=True,
                             book_path="/tmp/b.bok")
        self.assertIn("--book", argv)
        self.assertNotIn("--no-book", argv)

    def test_pattern_and_search_params_are_still_wired(self):
        argv = cvs.jass_argv("/bin/jass", pattern_path="/tmp/m.pjtw",
                             search_params="lmr_base=0")
        self.assertEqual(argv, ["/bin/jass", "--pattern", "/tmp/m.pjtw",
                                "--search-params", "lmr_base=0"])


if __name__ == "__main__":
    unittest.main()
