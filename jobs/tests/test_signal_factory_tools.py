#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import selfplay_frontier as SF  # noqa: E402


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FILTER = load("corpus_filter_test", "jobs/tools/corpus_filter.py")
REPORT = load("corpus_signal_report_test", "jobs/tools/corpus_signal_report.py")


def bits(*squares: int) -> int:
    value = 0
    for square in squares:
        value |= 1 << (square - 1)
    return value


def record(*, wm=0, wk=0, bm=0, bk=0, stm=0, wdl=0) -> bytes:
    return struct.pack("<QQQQBib", wm, wk, bm, bk, stm, 0, wdl)


def write_fixture(root: Path, name: str = "source") -> tuple[Path, Path]:
    records = [
        record(wm=bits(31, 32), bm=bits(10), stm=0, wdl=1),
        record(wm=bits(33), wk=bits(40), bm=bits(11), stm=1, wdl=-1),
        record(wm=bits(30), bm=bits(9), stm=0, wdl=0),
        record(wm=bits(29), bm=bits(8, 9), stm=1, wdl=1),
    ]
    rows = [
        SF.Meta(1, 10, 0, 1, 4, 2, 1, 0),
        SF.Meta(1, 10, 0, 3, 4, 2, 1, 0),
        SF.Meta(2, 20, 0, 0, 5, 0xFFFF, 0, 1),
        SF.Meta(3, 30, 1, 2, 6, 0xFFFF, -1, 2),
    ]
    data, meta = root / f"{name}.jnnw", root / f"{name}.jsm"
    SF.write_pair(data, meta, records, rows)
    return data, meta


class SignalFactoryToolTests(unittest.TestCase):
    def test_report_known_properties_and_no_model_omits_fisher(self):
        with tempfile.TemporaryDirectory() as td:
            data, meta = write_fixture(Path(td))
            args = Namespace(
                data=str(data), meta=str(meta), model=None, features=None,
                egdb=None, jass=None, egdb_cache_mb=16, chunk=10,
                phase_mode="tempo",
            )
            fake_coverage = {
                "fold": "exact", "visited_buckets": 7,
                "observations_per_free_parameter": 2.5,
            }
            with mock.patch.object(REPORT, "_coverage", return_value=fake_coverage):
                payload = REPORT.build_report(args)
            self.assertEqual(payload["records"], 4)
            self.assertEqual(payload["games"], 3)
            self.assertEqual(payload["positions_par_partie"]["mean"], 4 / 3)
            self.assertEqual(payload["wdl"]["win"]["count"], 2)
            self.assertEqual(payload["contamination"]["positions"], 1)
            self.assertEqual(payload["plycap"]["games"], 1)
            self.assertEqual(payload["positions"]["with_queens"], 1)
            self.assertEqual(payload["positions"]["piece_count_histogram"], {"2": 1, "3": 3})
            self.assertEqual(payload["sign_convention"]["records_checked_without_tb_relabel"], 4)
            self.assertNotIn("fisher", payload)

    def test_report_empty_corpus_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = root / "empty.jnnw", root / "empty.jsm"
            data.write_bytes(b"JNNW" + struct.pack("<I", 0))
            meta.write_bytes(b"JSM2" + struct.pack("<I", 0))
            with self.assertRaisesRegex(ValueError, "empty corpus"):
                REPORT._scan_corpus(data, meta)

    def test_report_detects_white_vs_stm_pov_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "bad.jnnw"
            meta = root / "bad.jsm"
            SF.write_pair(
                data, meta,
                [record(wm=bits(31), bm=bits(10), stm=1, wdl=1)],
                [SF.Meta(1, 1, 0, 0, 2, 0xFFFF, 1, 0)],
            )
            with self.assertRaisesRegex(ValueError, "POV mismatch"):
                REPORT._scan_corpus(data, meta)

    def test_fisher_uses_aligned_feat_and_model_forward_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = root / "fisher.jnnw", root / "fisher.jsm"
            records = [
                record(wm=bits(31), bm=bits(10), stm=0, wdl=0),
                record(wm=bits(32), bm=bits(11), stm=1, wdl=0),
            ]
            SF.write_pair(
                data, meta, records,
                [
                    SF.Meta(1, 1, 0, 0, 2, 0xFFFF, 0, 0),
                    SF.Meta(2, 2, 0, 0, 2, 0xFFFF, 0, 0),
                ],
            )
            mapped = np.memmap(data, dtype=REPORT.JNNW_DTYPE, mode="r", offset=8, shape=(2,))
            feat = root / "fisher.feat"
            feat.write_bytes(b"FEAT" + struct.pack("<II", 2, 1) + struct.pack("<ff", 0.0, 0.0))
            model = root / "fisher.pjtw"
            weights = [0, 1000, 0, 1000, 0, 0]
            model.write_bytes(
                struct.pack("<IIIII", REPORT.PJTW_MAGIC, 3 | 0x200, 1000, 2, 1)
                + struct.pack("<" + "i" * len(weights), *weights)
            )
            fake_indices = np.array([[0], [1]], dtype=np.int64)
            with (
                mock.patch.object(REPORT.patterns, "TOTAL_BUCKETS", 2),
                mock.patch.object(REPORT.patterns, "extract_indices", return_value=fake_indices),
                mock.patch.object(REPORT.patterns, "flat_feature_columns", side_effect=lambda value: value),
            ):
                fisher = REPORT._fisher(mapped, model, feat, chunk=2, phase_mode="tempo")
            expected = (0.25 + (1.0 / (1.0 + np.exp(-1.0))) * (
                1.0 - 1.0 / (1.0 + np.exp(-1.0))
            )) / 2.0
            self.assertAlmostEqual(fisher["mean"], expected)
            self.assertEqual(fisher["feature_source"],
                             "aligned FEAT dump consumed by train_stream; no extras reimplementation")
            mapped._mmap.close()

    def test_filter_true_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = write_fixture(root)
            out_data, out_meta, manifest = (
                root / "true.jnnw", root / "true.jsm", root / "true.json"
            )
            payload = FILTER.filter_corpus(
                data, meta, FILTER.Selection("true"), out_data, out_meta, manifest
            )
            self.assertEqual(out_data.read_bytes(), data.read_bytes())
            self.assertEqual(out_meta.read_bytes(), meta.read_bytes())
            self.assertEqual(payload["input"]["records"], payload["output"]["records"])
            self.assertEqual(payload, json.loads(manifest.read_text()))

    def test_filter_composition_matches_joint_filter_and_report_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = write_fixture(root)
            a_data, a_meta, a_manifest = root / "a.jnnw", root / "a.jsm", root / "a.json"
            ab_data, ab_meta, ab_manifest = root / "ab.jnnw", root / "ab.jsm", root / "ab.json"
            joint_data, joint_meta, joint_manifest = (
                root / "joint.jnnw", root / "joint.jsm", root / "joint.json"
            )
            FILTER.filter_corpus(
                data, meta, FILTER.Selection("pieces >= 2"),
                a_data, a_meta, a_manifest,
            )
            FILTER.filter_corpus(
                a_data, a_meta, FILTER.Selection("not contaminated"),
                ab_data, ab_meta, ab_manifest,
            )
            joint = FILTER.filter_corpus(
                data, meta, FILTER.Selection("pieces >= 2 and not contaminated"),
                joint_data, joint_meta, joint_manifest,
            )
            self.assertEqual(ab_data.read_bytes(), joint_data.read_bytes())
            self.assertEqual(ab_meta.read_bytes(), joint_meta.read_bytes())
            report, mapped_records, _total = REPORT._scan_corpus(joint_data, joint_meta)
            self.assertEqual(report["records"], joint["output"]["records"])
            mapped_records._mmap.close()

    def test_jsm1_context_filter_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = root / "legacy.jnnw", root / "legacy.jsm"
            SF.write_pair(
                data, meta,
                [record(wm=bits(31), bm=bits(10), stm=0, wdl=0)],
                [SF.Meta(1, 1, 0)],
            )
            with self.assertRaisesRegex(ValueError, "JSM2 is required"):
                FILTER.filter_corpus(
                    data, meta, FILTER.Selection("not contaminated"),
                    root / "out.jnnw", root / "out.jsm", root / "out.json",
                )

    def test_filter_expression_rejects_code_execution(self):
        with self.assertRaisesRegex(ValueError, "Call"):
            FILTER.Selection("__import__('os').system('echo unsafe')")


if __name__ == "__main__":
    unittest.main()
