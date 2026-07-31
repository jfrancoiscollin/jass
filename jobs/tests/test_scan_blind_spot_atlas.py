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
        """Un bucket où l'on diverge rarement mais cher doit passer devant un
        bucket où l'on diverge tout le temps pour presque rien.

        Les coûts restent dans l'échelle ordinaire mesurée (0.00-1.00) : au-delà
        du seuil de saturation l'échantillon changerait de famille, ce qui est
        testé séparément."""
        a = M.Atlas()
        for _ in range(100):                       # divergence permanente, 0.02
            a.add("bavard", "W:W31:B12", agreed=False, cost=0.02)
        for i in range(100):                       # 5 divergences à 1.0
            a.add("rare", "W:W31:B12", agreed=i >= 5,
                  cost=None if i >= 5 else 1.0)
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


class SaturationIsNotCost(unittest.TestCase):
    """L'échelle de Scan a été mesurée le 2026-07-31 : décimaux en unités-pion,
    et un gain forcé sature à ~99.97. Sommer ça brut ferait qu'un désaccord sur
    une position gagnée pèse plus de mille désaccords ordinaires."""

    def test_a_forced_win_is_routed_to_the_conversion_family(self):
        fam, cost, clipped = M.classify_sample(
            {"cost": 99.93, "scan_score_best": 99.97, "scan_score_ours": 0.04})
        self.assertEqual(fam, "conversion")
        self.assertIsNone(cost)
        self.assertFalse(clipped)

    def test_an_ordinary_cost_is_clipped_not_dropped(self):
        fam, cost, clipped = M.classify_sample({"cost": 4.0})
        self.assertEqual(fam, "ordinaire")
        self.assertEqual(cost, M.COST_CLIP)
        self.assertTrue(clipped)
        fam, cost, clipped = M.classify_sample({"cost": 0.04})
        self.assertEqual((fam, cost, clipped), ("ordinaire", 0.04, False))

    def test_saturation_is_detected_from_cost_alone_when_scores_are_absent(self):
        """Le collecteur peut n'émettre que le coût ; l'échelle ordinaire ne
        monte pas jusqu'à 50, donc un tel coût ne peut être qu'une saturation."""
        self.assertEqual(M.classify_sample({"cost": 99.93})[0], "conversion")

    def test_both_children_winning_is_not_a_conversion_miss(self):
        rec = {"cost": 0.0, "scan_score_best": 99.97, "scan_score_ours": 99.97}
        self.assertEqual(M.classify_sample(rec)[0], "conversion")
        self.assertFalse(M.is_conversion_miss(rec))

    def test_scan_wins_and_we_do_not_is_a_conversion_miss(self):
        self.assertTrue(M.is_conversion_miss(
            {"scan_score_best": 99.97, "scan_score_ours": 0.04}))

    def test_one_won_endgame_does_not_outrank_a_real_blind_spot(self):
        """LE test de non-régression. Avant la mesure, ce bucket-ci aurait été
        classé premier sur la foi d'un seul désaccord à ~100."""
        a = M.Atlas()
        for _ in range(100):        # vrai point aveugle : cher, systématique
            a.add("vrai_point_aveugle", "W:W31:B12", agreed=False, cost=0.5)
        for i in range(100):        # une seule finale gagnée ratée
            if i == 0:
                a.add("contient_une_finale_gagnee", "W:WK46:B5", agreed=False,
                      cost=None, family="conversion", conversion_miss=True)
            else:
                a.add("contient_une_finale_gagnee", "W:W31:B12", agreed=True,
                      cost=None)
        r = a.report(min_positions=10)
        self.assertEqual(r["buckets_ranked"][0]["bucket"], "vrai_point_aveugle")
        # Et la conversion ratée n'est pas perdue pour autant : elle est ailleurs.
        self.assertEqual(r["conversion_misses"], 1)
        self.assertEqual([c["bucket"] for c in r["conversion_family"]],
                         ["contient_une_finale_gagnee"])

    def test_conversion_positions_do_not_dilute_the_ordinary_denominator(self):
        """Le biais inverse : un bucket plein de finales gagnées ne doit pas
        voir son coût ordinaire divisé par des positions qui n'en font pas
        partie."""
        a = M.Atlas()
        for _ in range(10):
            a.add("b", "W:W31:B12", agreed=False, cost=1.0)
        for _ in range(90):
            a.add("b", "W:WK46:B5", agreed=True, cost=None, family="conversion")
        row = a.report(min_positions=1)["buckets_ranked"][0]
        self.assertEqual(row["ordinary_positions"], 10)
        self.assertEqual(row["cost_per_position"], 1.0)   # 10/10, pas 10/100

    def test_clipping_is_counted_and_published(self):
        a = M.Atlas()
        a.add("b", "W:W31:B12", agreed=False, cost=M.COST_CLIP, clipped=True)
        a.add("b", "W:W31:B12", agreed=False, cost=0.1)
        r = a.report(min_positions=1)
        self.assertEqual(r["costs_clipped"], 1)
        self.assertEqual(r["buckets_ranked"][0]["costs_clipped"], 1)

    def test_a_conversion_disagreement_still_counts_as_judged(self):
        """Sans ça, un corpus fait uniquement de conversions déclencherait le
        garde-fou « Scan est muet » alors que Scan a parfaitement parlé."""
        a = M.Atlas()
        a.add("b", "W:WK46:B5", agreed=False, cost=None,
              family="conversion", conversion_miss=True)
        self.assertEqual(a.report(min_positions=1)["disagreements_judged"], 1)


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
