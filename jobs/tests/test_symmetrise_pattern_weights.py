"""La symétrisation testée sur une géométrie minuscule mais RÉELLE.

Deux patterns de deux cases suffisent à exercer toute la logique (appariement
miroir, permutation d'index, échange de couleurs, projection entière) sans
manipuler 4,2 millions de poids à chaque test.

Ce qui compte ici : la projection doit rendre le modèle **exactement**
antisymétrique, en entiers. Un résidu d'une unité passerait inaperçu et ruinerait
l'argument entier — on projette précisément pour supprimer une quantité dont on
affirme qu'elle ne peut pas exister.
"""

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "symmetrise_pattern_weights", ROOT / "jobs/tools/symmetrise_pattern_weights.py")
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["symmetrise_pattern_weights"] = M
SPEC.loader.exec_module(M)

# Deux cases par pattern → 9 index. p0 = {1,2}, son miroir {50,49} = p1.
TINY_HEADER = """
inline constexpr std::array<Pattern, NUM_PATTERNS> PATTERNS = {{
    {{ 1, 2 }},
    {{ 50, 49 }},
}};
"""


def tiny_header() -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "pattern.hpp"
    p.write_text(TINY_HEADER)
    return p


class Geometry(unittest.TestCase):
    def setUp(self):
        self.pats = M.load_patterns(tiny_header())

    def test_patterns_pair_under_the_board_mirror(self):
        self.assertEqual(M.mirror_partner(self.pats, 0), 1)
        self.assertEqual(M.mirror_partner(self.pats, 1), 0)

    def test_the_index_map_is_an_involution(self):
        """Appliquer miroir+échange deux fois doit rendre l'identité — sans quoi
        poser `v_q = -v_p∘σ⁻¹` serait faux."""
        s01 = M.index_map(self.pats, 0, 1)
        s10 = M.index_map(self.pats, 1, 0)
        np.testing.assert_array_equal(s10[s01], np.arange(9))

    def test_colours_are_swapped_by_the_map(self):
        # index = c0*1 + c1*3 avec 0=vide, 1=noir, 2=blanc.
        # p0 case0=carré1, case1=carré2 ; p1 case0=carré50, case1=carré49.
        # 51-1=50 → case0 de p1 ; 51-2=49 → case1 de p1. La permutation est
        # l'identité, seules les couleurs s'échangent.
        s = M.index_map(self.pats, 0, 1)
        self.assertEqual(s[0], 0)                    # vide,vide → vide,vide
        self.assertEqual(s[1 + 0 * 3], 2 + 0 * 3)    # noir,vide → blanc,vide
        self.assertEqual(s[2 + 1 * 3], 1 + 2 * 3)    # blanc,noir → noir,blanc

    def test_a_pattern_without_a_mirror_partner_is_refused(self):
        d = Path(tempfile.mkdtemp())
        h = d / "pattern.hpp"
        h.write_text("inline constexpr std::array<Pattern, NUM_PATTERNS> "
                     "PATTERNS = {{\n    {{ 1, 2 }},\n    {{ 3, 4 }},\n}};\n")
        with self.assertRaises(ValueError):
            M.mirror_partner(M.load_patterns(h), 0)


class Projection(unittest.TestCase):
    def setUp(self):
        self.pats = M.load_patterns(tiny_header())

    def test_projection_is_exactly_antisymmetric_in_integers(self):
        rng = np.random.default_rng(3)
        pat = rng.integers(-500, 500, size=(2, 9)).astype(np.int64)
        self.assertGreater(M.violation_share(pat, self.pats), 0.0)
        out = M.symmetrise(pat, self.pats)
        self.assertEqual(M.violation_share(out, self.pats), 0.0)
        # et la relation tenue case par case, pas seulement en énergie
        sigma = M.index_map(self.pats, 0, 1)
        np.testing.assert_array_equal(out[0], -out[1][sigma])

    def test_a_fractional_half_still_lands_exactly(self):
        """Moitié fractionnaire des deux côtés. Le résultat doit rester
        exactement antisymétrique — ce qui tient ici parce que la moitié
        opposée est POSÉE, et tiendrait donc même sous un arrondi non
        symétrique."""
        pat = np.zeros((2, 9), dtype=np.int64)
        pat[0, 0] = 3          # (3 + 0)/2 = 1.5 → fractionnaire des deux côtés
        out = M.symmetrise(pat, self.pats)
        self.assertEqual(M.violation_share(out, self.pats), 0.0)
        sigma = M.index_map(self.pats, 0, 1)
        np.testing.assert_array_equal(out[0], -out[1][sigma])

    def test_an_already_symmetric_model_is_left_alone(self):
        rng = np.random.default_rng(11)
        pat = np.zeros((2, 9), dtype=np.int64)
        pat[0] = rng.integers(-500, 500, size=9)
        sigma = M.index_map(self.pats, 0, 1)
        inv = np.empty_like(sigma); inv[sigma] = np.arange(9)
        pat[1] = -pat[0][inv]
        self.assertEqual(M.violation_share(pat, self.pats), 0.0)
        np.testing.assert_array_equal(M.symmetrise(pat, self.pats), pat)

    def test_projection_is_idempotent(self):
        rng = np.random.default_rng(5)
        pat = rng.integers(-300, 300, size=(2, 9)).astype(np.int64)
        once = M.symmetrise(pat, self.pats)
        np.testing.assert_array_equal(M.symmetrise(once, self.pats), once)


class FileRoundTrip(unittest.TestCase):
    def _write(self, path, n_pat, n_ext, w):
        with open(path, "wb") as fh:
            fh.write(struct.pack("<5I", 0x57544A50, 3, 1000, n_pat, n_ext))
            fh.write(w.astype("<i4").tobytes())

    def test_header_and_extras_survive_untouched(self):
        d = Path(tempfile.mkdtemp())
        src, out = d / "a.pjtw", d / "b.pjtw"
        rng = np.random.default_rng(7)
        n_pat, n_ext = 18, 4                      # 2 patterns × 9 buckets
        w = rng.integers(-400, 400, size=2 * (n_pat + n_ext)).astype(np.int64)
        self._write(src, n_pat, n_ext, w)
        rc = M.main(["--in", str(src), "--out", str(out),
                     "--header", str(tiny_header())])
        self.assertEqual(rc, 0)
        m2, v2, s2, np2, ne2, w2 = M.read_pjtw(out)
        self.assertEqual((m2, v2, s2, np2, ne2), (0x57544A50, 3, 1000, n_pat, n_ext))
        # les extras ne sont PAS symétrisés — limite assumée, donc verrouillée
        np.testing.assert_array_equal(w2[2 * n_pat:], w[2 * n_pat:])

    def test_a_header_that_does_not_divide_n_pat_is_refused(self):
        d = Path(tempfile.mkdtemp())
        src, out = d / "a.pjtw", d / "b.pjtw"
        self._write(src, 19, 0, np.zeros(38, dtype=np.int64))   # 19 % 2 != 0
        self.assertEqual(M.main(["--in", str(src), "--out", str(out),
                                 "--header", str(tiny_header())]), 2)


if __name__ == "__main__":
    unittest.main()
