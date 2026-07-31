"""Le collecteur testé contre des moteurs FACTICES.

Ce qui est vérifié ici, c'est la seule chose qu'on ne verrait pas échouer en
production : la **convention de signe**. Un signe inversé ne plante rien, ne vide
aucun fichier, ne déclenche aucun garde-fou — il rend simplement un atlas
exactement à l'envers, où les buckets qu'on joue le mieux sont présentés comme
nos points aveugles. Il n'y a pas de symptôme, seulement une conclusion fausse.

Le reste (qui joue, quand on juge, ce qu'on fait d'un score illisible) est testé
parce que chacun de ces chemins décide silencieusement du contenu du corpus.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "scan_blind_spot_collector", ROOT / "jobs/tools/scan_blind_spot_collector.py")
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["scan_blind_spot_collector"] = M
SPEC.loader.exec_module(M)

ATLAS = M._load("scan_blind_spot_atlas", "jobs/tools/scan_blind_spot_atlas.py")


class FakeMove:
    def __init__(self, frm, to, captures=()):
        self.frm, self.to, self.captures = frm, to, tuple(captures)

    @property
    def is_capture(self):
        return bool(self.captures)

    def scan_str(self):
        return f"{self.frm}-{self.to}"


class FakeJass:
    """Joue toujours 31-27 ; c'est assez pour être d'accord ou non."""

    def __init__(self, move=None):
        self.move = move if move is not None else FakeMove(31, 27)

    def set_position_fen(self, fen):
        pass

    def go(self, depth=None):
        return self.move

    def close(self):
        pass


class FakeScan:
    """Rend un coup fixe pour jouer, et des scores scriptés pour juger.

    `judge_scores` associe le coup joué (scan_str) au score que Scan annonce
    DANS L'ENFANT — donc du point de vue de l'adversaire, comme le vrai Scan.
    """

    def __init__(self, play_move, judge_scores, no_score_for=()):
        self.play_move = play_move
        self.judge_scores = judge_scores
        self.no_score_for = set(no_score_for)
        self.judged_calls = []

    def new_game(self):
        pass

    def go_from_verbose(self, start, moves, depth=None, movetime=None):
        if not moves:                       # on lui demande de JOUER
            return self.play_move, ["info depth=6 score=0.10", "done move=x"]
        last = moves[-1]                    # on lui demande de JUGER un enfant
        self.judged_calls.append(last)
        if last in self.no_score_for:
            return None, ["done move=32-28"]        # aucun score lisible
        s = self.judge_scores[last]
        return None, [f"info depth=8 score={s}", "done move=32-28"]

    def close(self):
        pass


class FakeReferee:
    """Position minimale : un FEN fixe, N coups puis plus rien."""

    def __init__(self, plies=1, fen="W:W31,32,33:B1,2,3"):
        self.fen, self.left = fen, plies

    def set_position_fen(self, fen):
        pass

    def current_fen(self):
        return self.fen

    def scan_pos(self):
        return "Weee", []

    def apply_move(self, m):
        self.left -= 1
        return self.left > 0

    def close(self):
        pass


def make_cv(jass, scan, referee):
    ns = types.SimpleNamespace()
    ns.JassEngine = lambda *a, **k: jass
    ns.ScanEngine = lambda *a, **k: scan
    ns.Referee = lambda *a, **k: referee
    return ns


def collector(jass, scan, referee, play_depth=6, judge_depth=8, max_plies=1):
    return M.Collector(make_cv(jass, scan, referee), ATLAS, "j", "s", None,
                       play_depth, judge_depth, max_plies)


class SignConvention(unittest.TestCase):
    def test_our_worse_move_yields_a_POSITIVE_cost(self):
        """Le test qui protège la conclusion. Scan juge son enfant à -0.50 (bon
        pour NOUS après retournement : +0.50) et le nôtre à +0.20 (donc -0.20
        pour nous). Notre coup est moins bon → le coût DOIT être positif."""
        jass = FakeJass(FakeMove(31, 27))
        scan = FakeScan(FakeMove(32, 28),
                        {"32-28": -0.50, "31-27": 0.20})
        recs = collector(jass, scan, FakeReferee()).play_game("f", True)
        rec = recs[0]
        self.assertFalse(rec["agreed"])
        self.assertAlmostEqual(rec["scan_score_best"], 0.50)
        self.assertAlmostEqual(rec["scan_score_ours"], -0.20)
        self.assertAlmostEqual(rec["cost"], 0.70)
        self.assertGreater(rec["cost"], 0)

    def test_a_better_move_of_ours_yields_a_negative_cost_and_is_counted(self):
        """Quelques négatifs sont sains : le juge est plus profond que le
        joueur. Ils doivent être comptés, pas écrasés."""
        jass = FakeJass(FakeMove(31, 27))
        scan = FakeScan(FakeMove(32, 28), {"32-28": 0.10, "31-27": -0.40})
        c = collector(jass, scan, FakeReferee())
        rec = c.play_game("f", True)[0]
        self.assertLess(rec["cost"], 0)
        self.assertEqual(c.negative_costs, 1)

    def test_the_guard_tolerates_a_few_negatives_and_rejects_a_majority(self):
        self.assertTrue(M.sign_convention_ok(1, 100))
        self.assertTrue(M.sign_convention_ok(24, 100))
        self.assertFalse(M.sign_convention_ok(25, 100))
        self.assertFalse(M.sign_convention_ok(90, 100))
        # Rien de jugé : ce n'est pas au garde-fou de signe de crier.
        self.assertTrue(M.sign_convention_ok(0, 0))

    def test_judging_asks_scan_about_BOTH_children(self):
        jass = FakeJass(FakeMove(31, 27))
        scan = FakeScan(FakeMove(32, 28), {"32-28": 0.0, "31-27": 0.0})
        collector(jass, scan, FakeReferee()).play_game("f", True)
        self.assertEqual(sorted(scan.judged_calls), ["31-27", "32-28"])


class WhatGetsRecorded(unittest.TestCase):
    def test_agreement_is_recorded_with_no_cost_and_no_judging(self):
        """L'accord doit rester dans le corpus : c'est le dénominateur du taux
        de désaccord. Mais il ne doit coûter aucun appel de juge."""
        same = FakeMove(31, 27)
        jass = FakeJass(same)
        scan = FakeScan(FakeMove(31, 27), {})
        c = collector(jass, scan, FakeReferee())
        rec = c.play_game("f", True)[0]
        self.assertTrue(rec["agreed"])
        self.assertNotIn("cost", rec)
        self.assertEqual(scan.judged_calls, [])
        self.assertEqual(c.judged, 0)

    def test_an_unreadable_score_is_an_unjudged_disagreement_not_a_zero_cost(self):
        """Un coût nul se confondrait avec un accord et diluerait le bucket."""
        jass = FakeJass(FakeMove(31, 27))
        scan = FakeScan(FakeMove(32, 28), {"31-27": 0.1},
                        no_score_for=["32-28"])
        c = collector(jass, scan, FakeReferee())
        rec = c.play_game("f", True)[0]
        self.assertFalse(rec["agreed"])
        self.assertNotIn("cost", rec)
        self.assertEqual(c.unjudged, 1)
        self.assertEqual(c.judged, 0)

    def test_only_our_plies_are_recorded(self):
        """Aux coups de Scan on ne mesure rien : l'atlas parle de NOS décisions.
        Ici Jass joue les Noirs, la position est au trait Blanc → rien."""
        jass = FakeJass(FakeMove(31, 27))
        scan = FakeScan(FakeMove(32, 28), {})
        recs = collector(jass, scan, FakeReferee(plies=1)).play_game("f", False)
        self.assertEqual(recs, [])

    def test_forced_capture_is_carried_through_to_the_bucket(self):
        jass = FakeJass(FakeMove(31, 26, captures=(21,)))
        scan = FakeScan(FakeMove(32, 28), {"32-28": 0.0, "31-26": 0.0})
        rec = collector(jass, scan, FakeReferee()).play_game("f", True)[0]
        self.assertTrue(rec["forced_capture"])


class RoundTripIntoTheAggregator(unittest.TestCase):
    def test_what_the_collector_writes_is_what_the_atlas_reads(self):
        """Le round-trip écriture→lecture exigé avant de queuer : les clés
        émises ici doivent être exactement celles que l'agrégateur consomme."""
        jass = FakeJass(FakeMove(31, 27))
        scan = FakeScan(FakeMove(32, 28), {"32-28": -0.5, "31-27": 0.2})
        rec = collector(jass, scan, FakeReferee()).play_game("f", True)[0]
        family, cost, clipped = ATLAS.classify_sample(rec)
        self.assertEqual(family, "ordinaire")
        self.assertAlmostEqual(cost, 0.70)
        counts = ATLAS.parse_fen_counts(rec["fen"])
        counts["forced_capture"] = rec["forced_capture"]
        self.assertIsInstance(ATLAS.bucket_of(counts), str)

    def test_a_saturated_disagreement_routes_to_the_conversion_family(self):
        """Scan voit un gain forcé après son coup, pas après le nôtre."""
        jass = FakeJass(FakeMove(31, 27))
        scan = FakeScan(FakeMove(32, 28), {"32-28": -99.97, "31-27": -0.04})
        rec = collector(jass, scan, FakeReferee()).play_game("f", True)[0]
        self.assertAlmostEqual(rec["scan_score_best"], 99.97)
        self.assertEqual(ATLAS.classify_sample(rec)[0], "conversion")
        self.assertTrue(ATLAS.is_conversion_miss(rec))


if __name__ == "__main__":
    unittest.main()
