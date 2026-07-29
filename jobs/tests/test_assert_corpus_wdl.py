#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "jobs/tools/assert_corpus_wdl.py"
SPEC = importlib.util.spec_from_file_location("assert_corpus_wdl", MODULE)
WDL = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = WDL
SPEC.loader.exec_module(WDL)


def record(wdl: int) -> bytes:
    return struct.pack("<QQQQBiB", 0, 0, 0, 0, 0, 0, wdl & 0xFF)


class AssertCorpusWdlTests(unittest.TestCase):
    def test_histogram_streams_a_valid_corpus(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.jnnw"
            records = [record(-1), record(0), record(1), record(0)]
            path.write_bytes(b"JNNW" + struct.pack("<I", len(records)) + b"".join(records))

            with mock.patch.object(
                Path, "read_bytes", side_effect=AssertionError("materialised corpus")
            ):
                count, counts = WDL.histogram(path)

            self.assertEqual(count, 4)
            self.assertEqual(counts, {-1: 1, 0: 2, 1: 1})

    def test_histogram_rejects_size_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "truncated.jnnw"
            path.write_bytes(b"JNNW" + struct.pack("<I", 2) + record(0))
            with self.assertRaisesRegex(SystemExit, "taille incohérente"):
                WDL.histogram(path)

    def test_histogram_rejects_out_of_domain_wdl(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "invalid.jnnw"
            path.write_bytes(b"JNNW" + struct.pack("<I", 1) + record(2))
            with self.assertRaisesRegex(SystemExit, "hors domaine"):
                WDL.histogram(path)


if __name__ == "__main__":
    unittest.main()
