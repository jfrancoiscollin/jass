import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "scan_blind_spot_atlas", ROOT / "jobs/tools/scan_blind_spot_atlas.py")
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(M)


class ScanScoreExtraction(unittest.TestCase):
    """Le format exact des lignes `info` de Scan 3.1 n'a pas pu être vérifié
    hors des box. Le motif est donc tolérant, et l'absence de score doit
    remonter comme None — jamais comme zéro, qui se confondrait avec un coup
    sans coût."""

    def test_reads_the_last_score_before_done(self):
        lines = ["info depth=8 score=12 nodes=100",
                 "info depth=9 score=-34 nodes=900",
                 "done move=32-28"]
        self.assertEqual(M.extract_scan_score(lines), -34.0)

    def test_tolerates_colon_and_spacing_and_decimals(self):
        self.assertEqual(M.extract_scan_score(["info score: +7.5"]), 7.5)
        self.assertEqual(M.extract_scan_score(["info  score = -2"]), -2.0)

    def test_missing_score_is_none_not_zero(self):
        self.assertIsNone(M.extract_scan_score(["done move=32-28"]))
        self.assertIsNone(M.extract_scan_score([]))


class FenCounting(unittest.TestCase):
    def test_counts_men_and_kings_per_colour(self):
        c = M.parse_fen_counts("W:WK46,K47,31:BK5,12,13,14")
        self.assertEqual((c["wm"], c["wk"], c["bm"], c["bk"]), (1, 2, 3, 1))
        self.assertTrue(c["stm_white"])

    def test_black_to_move(self):
        self.assertFalse(M.parse_fen_counts("B:W31:B12")["stm_white"])

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            M.parse_fen_counts("pas une fen")


class Bucketing(unittest.TestCase):
    def test_material_balance_is_from_the_movers_point_of_view(self):
        # Blanc a une dame (=3) contre trois pions noirs : matériel égal.
        white_to_move = M.parse_fen_counts("W:WK46:B1,2,3")
        white_to_move["forced_capture"] = False
        black_to_move = M.parse_fen_counts("B:WK46:B1,2,3")
        black_to_move["forced_capture"] = False
        self.assertIn("materiel_egal", M.bucket_of(white_to_move))
        self.assertIn("materiel_egal", M.bucket_of(black_to_move))

    def test_advantage_flips_with_the_side_to_move(self):
        w = M.parse_fen_counts("W:WK46,K47:B1")          # blanc +5
        w["forced_capture"] = False
        b = M.parse_fen_counts("B:WK46,K47:B1")
        b["forced_capture"] = False
        self.assertIn("en_avance_3+", M.bucket_of(w))
        self.assertIn("en_retard_3+", M.bucket_of(b))

    def test_forced_capture_separates_tactical_from_quiet(self):
        q = M.parse_fen_counts("W:W31:B12"); q["forced_capture"] = False
        t = M.parse_fen_counts("W:W31:B12"); t["forced_capture"] = True
        self.assertNotEqual(M.bucket_of(q), M.bucket_of(t))


class Aggregation(unittest.TestCase):
    def test_agreement_costs_nothing_and_is_not_a_blind_spot(self):
        a = M.Atlas()
        for _ in range(10):
            a.add("b", "W:W31:B12", agreed=True, cost=None)
        r = a.report(min_positions=1)
        row = r["buckets_ranked"][0]
        self.assertEqual(row["disagreements"], 0)
        self.assertEqual(row["cost_sum"], 0.0)
        self.assertEqual(r["moves_agreed"], 10)

    def test_ranks_by_cost_per_position_not_by_disagreement_rate(self):
        """Un bucket où l'on diverge rarement mais très cher doit passer devant
        un bucket où l'on diverge tout le temps pour presque rien."""
        a = M.Atlas()
        for i in range(100):                       # divergence permanente, 1 pt
            a.add("bavard", "W:W31:B12", agreed=False, cost=1.0)
        for i in range(100):                       # 5 divergences à 100 pts
            a.add("rare", "W:W31:B12", agreed=i >= 5,
                  cost=None if i >= 5 else 100.0)
        r = a.report(min_positions=10)
        self.assertEqual([b["bucket"] for b in r["buckets_ranked"]],
                         ["rare", "bavard"])

    def test_buckets_below_the_floor_are_published_but_not_ranked(self):
        a = M.Atlas()
        a.add("maigre", "W:W31:B12", agreed=False, cost=50.0)
        for _ in range(20):
            a.add("fourni", "W:W31:B12", agreed=False, cost=1.0)
        r = a.report(min_positions=10)
        self.assertEqual([b["bucket"] for b in r["buckets_ranked"]], ["fourni"])
        self.assertEqual([b["bucket"] for b in r["buckets_below_floor"]],
                         ["maigre"])

    def test_unjudged_disagreement_counts_as_disagreement_but_not_as_cost(self):
        a = M.Atlas()
        a.add("b", "W:W31:B12", agreed=False, cost=None)
        r = a.report(min_positions=1)
        row = r["buckets_ranked"][0]
        self.assertEqual(row["disagreements"], 1)
        self.assertEqual(row["cost_sum"], 0.0)
        self.assertEqual(r["disagreements_judged"], 0)


class CliFailsClosed(unittest.TestCase):
    def _run(self, records):
        d = Path(tempfile.mkdtemp())
        src = d / "s.jsonl"
        src.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        out = d / "atlas.json"
        return M.main(["--samples", str(src), "--out", str(out),
                       "--min-positions", "1"]), out

    def test_zero_positions_is_a_failure(self):
        rc, out = self._run([])
        self.assertEqual(rc, 2)
        self.assertFalse(out.exists())

    def test_no_judged_disagreement_is_a_failure(self):
        """Le cas qui compte : Scan tourne mais aucun score n'est lisible. Sans
        cette garde on publierait un atlas de zéros qui ressemble à « aucun
        point aveugle »."""
        rc, out = self._run([{"fen": "W:W31:B12", "agreed": False, "cost": None}])
        self.assertEqual(rc, 3)
        self.assertFalse(out.exists())

    def test_writes_the_atlas_when_something_was_judged(self):
        rc, out = self._run([{"fen": "W:W31:B12", "agreed": False, "cost": 4.0}])
        self.assertEqual(rc, 0)
        self.assertTrue(json.loads(out.read_text())["diagnostic_only"])


if __name__ == "__main__":
    unittest.main()
