#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "jnnw_doe.py"
SPEC = importlib.util.spec_from_file_location("jnnw_doe", MODULE_PATH)
assert SPEC and SPEC.loader
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


def record(square: int, *, stm: int = 0, score: int = 10, wdl: int = 1) -> bytes:
    return struct.pack("<QQQQBib", 1 << (square - 1), 0, 1 << ((square + 10) - 1), 0, stm, score, wdl)


class JnnwDoeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fen_to_record_layout(self) -> None:
        rec = D._parse_fen("B:W1,K2:B3,K4")
        self.assertEqual(len(rec), D.REC)
        wm, wk, bm, bk, stm, score, wdl = struct.unpack("<QQQQBib", rec)
        self.assertEqual((wm, wk, bm, bk), (1, 2, 4, 8))
        self.assertEqual((stm, score, wdl), (1, 0, 0))

    def test_sample_deduplicates_and_excludes(self) -> None:
        source = self.root / "source.jnnw"
        excluded = self.root / "excluded.fen"
        out = self.root / "sample.jnnw"
        # Position 1 occurs twice; position 2 is explicitly excluded.
        D._write(source, [record(1), record(1, score=99, wdl=-1), record(2), record(3), record(4)])
        excluded.write_text("W:W2:B12\n", encoding="utf-8")
        args = argparse.Namespace(input=str(source), output=str(out), count=2, exclude_fen=[str(excluded)])
        D.cmd_sample(args)
        n, body = D._read(out)
        rows = list(D._records(body))
        self.assertEqual(n, 2)
        self.assertEqual(len({D._record_key(r) for r in rows}), 2)
        self.assertNotIn(D._record_key(record(2)), {D._record_key(r) for r in rows})

    def test_contiguous_split_merge_preserves_order(self) -> None:
        source = self.root / "source.jnnw"
        prefix = self.root / "shard"
        merged = self.root / "merged.jnnw"
        rows = [record(i) for i in range(1, 10)]
        D._write(source, rows)
        D.cmd_split(argparse.Namespace(input=str(source), prefix=str(prefix), shards=4))
        D.cmd_merge(argparse.Namespace(prefix=str(prefix), source_prefix=None, output=str(merged), shards=4, expected=9))
        _, body = D._read(merged)
        self.assertEqual(list(D._records(body)), rows)

    def test_merge_rejects_reordered_relabelled_positions(self) -> None:
        source = self.root / "source.jnnw"
        src_prefix = self.root / "src"
        rel_prefix = self.root / "rel"
        rows = [record(i) for i in range(1, 7)]
        D._write(source, rows)
        D.cmd_split(argparse.Namespace(input=str(source), prefix=str(src_prefix), shards=2))
        for shard in range(2):
            _, body = D._read(f"{src_prefix}.{shard:03d}.jnnw")
            shard_rows = list(D._records(body))
            if shard == 1:
                shard_rows.reverse()
            D._write(f"{rel_prefix}.{shard:03d}.jnnw", shard_rows)
        with self.assertRaisesRegex(ValueError, "changed/reordered"):
            D.cmd_merge(argparse.Namespace(prefix=str(rel_prefix), source_prefix=str(src_prefix), output=str(self.root / "bad.jnnw"), shards=2, expected=6))

    def test_normalize_changes_only_wdl(self) -> None:
        reference = self.root / "reference.jnnw"
        relabelled = self.root / "relabelled.jnnw"
        out = self.root / "normalized.jnnw"
        ref_rows = [record(1, score=123, wdl=1), record(2, score=-456, wdl=-1)]
        lab_rows = [ref_rows[0][:33] + struct.pack("<ib", 9999, -1), ref_rows[1][:33] + struct.pack("<ib", 8888, 0)]
        D._write(reference, ref_rows)
        D._write(relabelled, lab_rows)
        D.cmd_normalize_labels(argparse.Namespace(reference=str(reference), relabeled=str(relabelled), output=str(out)))
        _, body = D._read(out)
        rows = list(D._records(body))
        self.assertEqual(rows[0][:37], ref_rows[0][:37])
        self.assertEqual(rows[1][:37], ref_rows[1][:37])
        self.assertEqual(struct.unpack_from("<b", rows[0], 37)[0], -1)
        self.assertEqual(struct.unpack_from("<b", rows[1], 37)[0], 0)

    def test_keep_decisive_drops_draw_labels(self) -> None:
        src = self.root / "src.jnnw"
        out = self.root / "out.jnnw"
        D._write(src, [record(1, wdl=1), record(2, wdl=0), record(3, wdl=-1)])
        D.cmd_keep_decisive(argparse.Namespace(input=str(src), output=str(out)))
        _, body = D._read(out)
        rows = list(D._records(body))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r[37] != 0 for r in rows))

    def test_build_cells_has_same_unique_positions_and_only_expected_factors(self) -> None:
        onp = self.root / "onp.jnnw"
        adj = self.root / "adj.jnnw"
        gym = self.root / "gym.jnnw"
        outdir = self.root / "cells"
        manifest = self.root / "manifest.json"
        onp_rows = [record(1, wdl=1), record(2, wdl=-1)]
        adj_rows = [onp_rows[0][:37] + b"\xff", onp_rows[1][:37] + b"\x01"]
        gym_rows = [record(20, wdl=1), record(21, wdl=-1)]
        D._write(onp, onp_rows)
        D._write(adj, adj_rows)
        D._write(gym, gym_rows)
        D.cmd_build_cells(argparse.Namespace(base_onp=str(onp), base_adj=str(adj), gym=str(gym), gym_mult=3, out_dir=str(outdir), manifest=str(manifest)))
        man = json.loads(manifest.read_text())
        self.assertEqual(man["base_records"], 2)
        self.assertEqual(man["gym_unique_records"], 2)
        self.assertEqual(man["cells"]["onp_g1"]["records"], 4)
        self.assertEqual(man["cells"]["onp_g3"]["records"], 8)
        for name in ("onp_g1", "adj_g1", "onp_g3", "adj_g3"):
            _, body = D._read(outdir / f"{name}.jnnw")
            keys = {D._record_key(r) for r in D._records(body)}
            self.assertEqual(len(keys), 4)
        D.cmd_verify_cells(argparse.Namespace(out_dir=str(outdir), manifest=str(manifest)))


if __name__ == "__main__":
    unittest.main()
