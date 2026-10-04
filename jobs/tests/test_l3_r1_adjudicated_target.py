# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contracts for the R1 adjudicated-relabel external target builder.

Covers docs/experiments/L3_R1_ADJUDICATED_RELABEL_V1_20260909.md §3.3/§4.2.
"""
from __future__ import annotations

import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs" / "tools" / "l3_r1_adjudicated_target.py"
SPEC = importlib.util.spec_from_file_location("l3_r1_adjudicated_target", TOOL)
assert SPEC is not None and SPEC.loader is not None
TARGET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TARGET)


def _write_jnnw(path: Path, records: np.ndarray) -> None:
    assert records.dtype == TARGET.JNNW_DTYPE
    with path.open("wb") as handle:
        handle.write(b"JNNW")
        handle.write(struct.pack("<I", records.shape[0]))
        handle.write(records.tobytes())


def _make_records(n: int) -> np.ndarray:
    records = np.zeros(n, dtype=TARGET.JNNW_DTYPE)
    return records


def _write_tags(path: Path, tags: np.ndarray) -> None:
    path.write_bytes(tags.astype(np.uint8).tobytes())


class R1AdjudicatedTargetTest(unittest.TestCase):
    def _paths(self, tmp: Path):
        return {
            "original": tmp / "orig.jnnw",
            "relabelled": tmp / "relab.jnnw",
            "tags": tmp / "tags.bin",
            "out_r1": tmp / "y_r1.npy",
            "out_adj": tmp / "y_adj.npy",
            "report": tmp / "report.json",
        }

    def _run(self, paths, alpha=None, context30=None, min_draw=None, max_draw=None, max_skew=None):
        argv = [
            "--original", str(paths["original"]),
            "--relabelled", str(paths["relabelled"]),
            "--source-tags", str(paths["tags"]),
            "--out-r1", str(paths["out_r1"]),
            "--out-adj", str(paths["out_adj"]),
            "--report", str(paths["report"]),
        ]
        if alpha is not None:
            argv += ["--alpha", str(alpha)]
        if context30 is not None:
            argv += ["--context30", str(context30)]
        if min_draw is not None:
            argv += ["--min-draw-share", str(min_draw)]
        if max_draw is not None:
            argv += ["--max-draw-share", str(max_draw)]
        if max_skew is not None:
            argv += ["--max-side-skew", str(max_skew)]
        return TARGET.main(argv)

    # ------------------------------------------------------------------
    # Happy path: known confusion matrix + reversal rate + phase bins.
    # ------------------------------------------------------------------
    def _happy_fixture(self, tmp: Path):
        paths = self._paths(tmp)
        # 12 records, balanced so the guard passes: draw share must be in
        # [0.10, 0.60] and |win-loss| <= 0.10 on the ADJUDICATED (relabelled)
        # wdl byte.
        n = 12
        orig = _make_records(n)
        relab = _make_records(n)

        # stm alternates so black-POV conversion is exercised both ways.
        stm = np.array([0, 1] * 6, dtype=np.uint8)
        orig["stm"] = stm
        relab["stm"] = stm

        # A distinct bitboard combination per record so no two are equal,
        # kept identical between original and relabelled (position must not
        # change under relabel).
        for i in range(n):
            orig["wm"][i] = 1 << (i % 50)
            orig["wk"][i] = 1 << ((i + 1) % 50 + 50)
            orig["bm"][i] = 1 << ((i + 2) % 50 + 4)
            orig["bk"][i] = 1 << ((i + 3) % 50 + 20)
        for field in ("wm", "wk", "bm", "bk"):
            relab[field] = orig[field]

        # Terminal (original) WDL, STM POV: 5 win, 4 draw, 3 loss.
        term_wdl = np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, -1, -1, -1], dtype=np.int8)
        orig["wdl"] = term_wdl
        orig["score"] = term_wdl.astype(np.int32) * 100

        # Adjudicated WDL, STM POV: term_wdl with index 4 flipped win->loss.
        # Result is balanced (4 win / 4 draw / 4 loss, skew 0), so the
        # default guard passes, with exactly one known reversal (index 4).
        adj_wdl = np.array([1, 1, 1, 1, -1, 0, 0, 0, 0, -1, -1, -1], dtype=np.int8)
        relab["wdl"] = adj_wdl
        relab["score"] = adj_wdl.astype(np.int32) * 55

        tags = np.array([0, 1, 2] * 4, dtype=np.uint8)

        _write_jnnw(paths["original"], orig)
        _write_jnnw(paths["relabelled"], relab)
        _write_tags(paths["tags"], tags)
        return paths, stm, term_wdl, adj_wdl, tags

    def test_happy_path_confusion_matrix_and_reversal_rate(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths, stm, term_wdl, adj_wdl, tags = self._happy_fixture(tmp)
            rc = self._run(paths)
            self.assertEqual(rc, 0)

            import json
            report = json.loads(paths["report"].read_text())
            self.assertEqual(report["schema"], "jass.l3.r1_adjudicated_target.v1")
            self.assertEqual(report["n_records"], 12)
            self.assertEqual(report["guard"]["status"], "R1_LABEL_GUARD_PASS")

            # Hand-computed confusion matrix, order (-1, 0, 1) x (-1, 0, 1).
            expected = [[0, 0, 0] for _ in range(3)]
            order = {-1: 0, 0: 1, 1: 2}
            for t, a in zip(term_wdl.tolist(), adj_wdl.tolist()):
                expected[order[t]][order[a]] += 1
            self.assertEqual(report["confusion_matrix_terminal_x_adjudicated"]["matrix"], expected)

            reversed_count = int(np.count_nonzero(term_wdl != adj_wdl))
            self.assertEqual(reversed_count, 1)
            self.assertAlmostEqual(report["reversal_rate"]["global"], 1 / 12)

            self.assertEqual(report["source_tag_counts"], {"search": 4, "tb": 4, "terminal": 4})

            # y_r1 outputs exist, float32, length 12, in [0,1].
            y_r1 = np.load(paths["out_r1"])
            y_adj = np.load(paths["out_adj"])
            self.assertEqual(y_r1.dtype, np.float32)
            self.assertEqual(y_adj.dtype, np.float32)
            self.assertEqual(y_r1.shape, (12,))
            self.assertTrue(bool(np.all((y_r1 >= 0.0) & (y_r1 <= 1.0))))

            p_term = np.where(stm == 1, term_wdl, -term_wdl).astype(np.float64)
            p_term = (p_term + 1.0) / 2.0
            p_adj = np.where(stm == 1, adj_wdl, -adj_wdl).astype(np.float64)
            p_adj = (p_adj + 1.0) / 2.0
            expected_y_r1 = (0.5 * p_term + 0.5 * p_adj).astype(np.float32)
            expected_y_adj = p_adj.astype(np.float32)
            np.testing.assert_allclose(y_r1, expected_y_r1, atol=1e-6)
            np.testing.assert_allclose(y_adj, expected_y_adj, atol=1e-6)

    # ------------------------------------------------------------------
    # Alpha edge cases.
    # ------------------------------------------------------------------
    def test_alpha_zero_equals_pure_adjudicated(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths, stm, term_wdl, adj_wdl, tags = self._happy_fixture(tmp)
            rc = self._run(paths, alpha=0.0)
            self.assertEqual(rc, 0)
            y_r1 = np.load(paths["out_r1"])
            y_adj = np.load(paths["out_adj"])
            np.testing.assert_allclose(y_r1, y_adj, atol=1e-6)

    def test_alpha_one_equals_pure_terminal(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths, stm, term_wdl, adj_wdl, tags = self._happy_fixture(tmp)
            rc = self._run(paths, alpha=1.0)
            self.assertEqual(rc, 0)
            y_r1 = np.load(paths["out_r1"])
            p_term = np.where(stm == 1, term_wdl, -term_wdl).astype(np.float64)
            p_term = ((p_term + 1.0) / 2.0).astype(np.float32)
            np.testing.assert_allclose(y_r1, p_term, atol=1e-6)

    # ------------------------------------------------------------------
    # Black-POV conversion.
    # ------------------------------------------------------------------
    def test_black_to_move_pov_conversion(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths = self._paths(tmp)
            n = 4
            orig = _make_records(n)
            relab = _make_records(n)
            # stm=1 (black to move), wdl=+1 (STM POV) -> already black POV
            # win -> p_term should be 1.0.
            orig["stm"] = np.array([1, 1, 0, 0], dtype=np.uint8)
            relab["stm"] = orig["stm"]
            for field in ("wm", "wk", "bm", "bk"):
                orig[field] = np.arange(n, dtype=np.uint64) + 1
                relab[field] = orig[field]
            orig["wdl"] = np.array([1, 0, 1, -1], dtype=np.int8)
            # Keep guard band satisfiable with such a small n by choosing an
            # adjudicated distribution with a draw and balanced sides.
            relab["wdl"] = np.array([1, 0, 1, -1], dtype=np.int8)
            tags = np.array([0, 1, 2, 0], dtype=np.uint8)
            _write_jnnw(paths["original"], orig)
            _write_jnnw(paths["relabelled"], relab)
            _write_tags(paths["tags"], tags)

            # This 4-record corpus has draw share 0.25 (in band) but win/loss
            # skew of |0.5-0.25|=0.25 > 0.10 default -> guard would fail.
            # Widen the skew band explicitly since POV-conversion is the
            # point of this test, not the guard.
            rc = self._run(paths, max_skew=1.0)
            self.assertEqual(rc, 0)
            y_r1 = np.load(paths["out_r1"])
            # Record 0: stm=1, wdl=+1 -> p_term=p_adj=1.0 -> y_r1=1.0.
            self.assertAlmostEqual(float(y_r1[0]), 1.0, places=6)
            # Record 2: stm=0, wdl=+1 (white wins, STM POV) -> black POV = -1
            # -> p = 0.0.
            self.assertAlmostEqual(float(y_r1[2]), 0.0, places=6)
            # Record 3: stm=0, wdl=-1 (white loses) -> black POV = +1 -> p=1.0.
            self.assertAlmostEqual(float(y_r1[3]), 1.0, places=6)

    # ------------------------------------------------------------------
    # Phase binning.
    # ------------------------------------------------------------------
    def test_phase_binning_matches_main_cpp_thresholds(self):
        # pieces >= 30 -> opening(0), >=22 -> midgame(1), >=15 -> late-mid(2),
        # >=8 -> endgame(3), else -> deep-eg(4).
        pieces = np.array([32, 25, 16, 9, 3], dtype=np.int64)
        expected = np.array([0, 1, 2, 3, 4], dtype=np.int64)
        got = TARGET._phase_index(pieces)
        np.testing.assert_array_equal(got, expected)

    def test_reversal_rate_by_phase_lands_in_expected_bucket(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths = self._paths(tmp)
            n = 6
            orig = _make_records(n)
            relab = _make_records(n)
            orig["stm"] = np.zeros(n, dtype=np.uint8)
            relab["stm"] = orig["stm"]
            # Record 0: 32 total pieces (opening). Records 1-5: few pieces
            # (deep-eg), distinct bitboards so no duplicate-position issue.
            orig["wm"][0] = (1 << 16) - 1          # 16 men
            orig["wk"][0] = ((1 << 16) - 1) << 16   # 16 kings -> 32 pieces
            for i in range(1, n):
                orig["wm"][i] = 1 << i
            for field in ("wm", "wk", "bm", "bk"):
                relab[field] = orig[field]
            # Terminal all draws, adjudicated flips record 0 (opening) only.
            orig["wdl"] = np.zeros(n, dtype=np.int8)
            adj = np.zeros(n, dtype=np.int8)
            adj[0] = 1
            relab["wdl"] = adj
            tags = np.zeros(n, dtype=np.uint8)
            _write_jnnw(paths["original"], orig)
            _write_jnnw(paths["relabelled"], relab)
            _write_tags(paths["tags"], tags)

            rc = self._run(paths, min_draw=0.0, max_draw=1.0, max_skew=1.0)
            self.assertEqual(rc, 0)
            import json
            report = json.loads(paths["report"].read_text())
            by_phase = report["reversal_rate"]["by_phase"]
            self.assertEqual(by_phase["opening"]["n"], 1)
            self.assertAlmostEqual(by_phase["opening"]["reversal_rate"], 1.0)
            self.assertEqual(by_phase["deep-eg"]["n"], 5)
            self.assertAlmostEqual(by_phase["deep-eg"]["reversal_rate"], 0.0)

    # ------------------------------------------------------------------
    # Guard failure: no npy written, report written, exit 6.
    # ------------------------------------------------------------------
    def test_guard_failure_all_decisive_relabel(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths = self._paths(tmp)
            n = 8
            orig = _make_records(n)
            relab = _make_records(n)
            orig["stm"] = np.zeros(n, dtype=np.uint8)
            relab["stm"] = orig["stm"]
            for i in range(n):
                orig["wm"][i] = 1 << i
            for field in ("wm", "wk", "bm", "bk"):
                relab[field] = orig[field]
            orig["wdl"] = np.array([1, -1, 1, -1, 1, -1, 1, -1], dtype=np.int8)
            # All decisive (zero draws) -> guard must fail (draw share 0 < 0.10).
            relab["wdl"] = np.array([1, -1, 1, -1, 1, -1, 1, -1], dtype=np.int8)
            tags = np.zeros(n, dtype=np.uint8)
            _write_jnnw(paths["original"], orig)
            _write_jnnw(paths["relabelled"], relab)
            _write_tags(paths["tags"], tags)

            rc = self._run(paths)
            self.assertEqual(rc, 6)
            self.assertFalse(paths["out_r1"].exists())
            self.assertFalse(paths["out_adj"].exists())
            self.assertTrue(paths["report"].exists())
            import json
            report = json.loads(paths["report"].read_text())
            self.assertEqual(report["guard"]["status"], "R1_LABEL_GUARD_FAILED")

    # ------------------------------------------------------------------
    # Fail-closed contract violations -> exit 2.
    # ------------------------------------------------------------------
    def test_count_mismatch_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths, *_ = self._happy_fixture(tmp)
            # Overwrite relabelled with a shorter file (different count).
            paths["relabelled"].unlink()
            short = _make_records(4)
            for field in ("wm", "wk", "bm", "bk", "stm", "wdl", "score"):
                pass
            _write_jnnw(paths["relabelled"], short)
            with self.assertRaises(SystemExit) as ctx:
                self._run(paths)
            self.assertEqual(ctx.exception.code, 2)

    def test_bitboard_mismatch_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths, *_ = self._happy_fixture(tmp)
            # Corrupt one record's bitboard in the relabelled file only.
            data = bytearray(paths["relabelled"].read_bytes())
            # First record starts right after the 8-byte header.
            offset = TARGET.JNNW_HEADER_SIZE
            data[offset] ^= 0xFF
            paths["relabelled"].write_bytes(bytes(data))
            with self.assertRaises(SystemExit) as ctx:
                self._run(paths)
            self.assertEqual(ctx.exception.code, 2)

    def test_tags_size_mismatch_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths, *_ = self._happy_fixture(tmp)
            paths["tags"].unlink()
            paths["tags"].write_bytes(bytes([0, 1, 2]))  # too short
            with self.assertRaises(SystemExit) as ctx:
                self._run(paths)
            self.assertEqual(ctx.exception.code, 2)

    def test_tags_value_out_of_range_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths, *_ = self._happy_fixture(tmp)
            paths["tags"].unlink()
            bad = np.array([0, 1, 2, 3, 0, 1, 2, 0, 1, 2, 0, 1], dtype=np.uint8)
            _write_tags(paths["tags"], bad)
            with self.assertRaises(SystemExit) as ctx:
                self._run(paths)
            self.assertEqual(ctx.exception.code, 2)

    def test_no_clobber_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths, *_ = self._happy_fixture(tmp)
            paths["out_r1"].write_bytes(b"pre-existing")
            with self.assertRaises(SystemExit) as ctx:
                self._run(paths)
            self.assertEqual(ctx.exception.code, 2)

    # ------------------------------------------------------------------
    # context30 stats path.
    # ------------------------------------------------------------------
    def test_context30_stats_path(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            paths, *_ = self._happy_fixture(tmp)
            ctx_path = tmp / "context30.npy"
            ctx = np.full(12, 0.5, dtype=np.float32)
            np.save(ctx_path, ctx)
            rc = self._run(paths, context30=ctx_path)
            self.assertEqual(rc, 0)
            import json
            report = json.loads(paths["report"].read_text())
            self.assertIn("context30_comparison", report)
            comp = report["context30_comparison"]
            self.assertIn("mean_abs_diff_vs_y_r1", comp)
            self.assertIn("stats", comp)
            self.assertAlmostEqual(comp["stats"]["mean"], 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
