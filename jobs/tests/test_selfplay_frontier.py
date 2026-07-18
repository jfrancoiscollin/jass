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

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools/selfplay_frontier.py"
SPEC = importlib.util.spec_from_file_location("selfplay_frontier", MODULE)
SF = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SF
SPEC.loader.exec_module(SF)


def bits(*squares: int) -> int:
    value = 0
    for square in squares:
        value |= 1 << (square - 1)
    return value


def record(*, wm=0, wk=0, bm=0, bk=0, stm=0, score=123, wdl=0) -> bytes:
    return struct.pack("<QQQQBiB", wm, wk, bm, bk, stm, score, wdl & 0xFF)


class SelfplayFrontierTests(unittest.TestCase):
    def write_pair(self, root: Path, name: str, records: list[bytes], rows):
        data = root / f"{name}.jnnw"
        meta = root / f"{name}.jsm"
        SF.write_pair(data, meta, records, rows)
        return data, meta

    def test_merge_namespaces_ids_and_preserves_alignment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rec_a = record(wm=bits(31, 32), bm=bits(10), stm=0, wdl=-1)
            rec_b = record(wm=bits(30), bm=bits(9, 10), stm=1, wdl=1)
            a = self.write_pair(root, "a", [rec_a], [SF.Meta(1, 1, 0)])
            b = self.write_pair(root, "b", [rec_b], [SF.Meta(1, 1, 1)])
            out_data, out_meta = root / "all.jnnw", root / "all.jsm"
            rc = SF.do_merge(Namespace(
                pair=[[str(a[0]), str(a[1])], [str(b[0]), str(b[1])]],
                out_data=str(out_data), out_meta=str(out_meta), manifest=None,
            ))
            self.assertEqual(rc, 0)
            records, rows = SF.read_pair(out_data, out_meta)
            self.assertEqual(records, [rec_a, rec_b])
            self.assertNotEqual(rows[0].game_id, rows[1].game_id)
            self.assertEqual([row.seeded for row in rows], [0, 1])

    def test_split_keeps_paired_opening_together_and_in_tail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            seed, mod = 7, 2
            opening_train = next(i for i in range(1, 100)
                                  if SF._opening_fold(i, seed, mod) != 0)
            opening_hold = next(i for i in range(1, 100)
                                 if SF._opening_fold(i, seed, mod) == 0)
            records = [record(wm=bits(31 + i), bm=bits(10), wdl=1) for i in range(4)]
            rows = [
                SF.Meta(1, opening_train, 0), SF.Meta(2, opening_train, 0),
                SF.Meta(3, opening_hold, 0), SF.Meta(4, opening_hold, 0),
            ]
            data, meta = self.write_pair(root, "raw", records, rows)
            out_data, out_meta = root / "split.jnnw", root / "split.jsm"
            manifest = root / "split.json"
            rc = SF.do_split(Namespace(
                data=str(data), meta=str(meta), out_data=str(out_data),
                out_meta=str(out_meta), holdout_mod=mod, seed=seed,
                manifest=str(manifest),
            ))
            self.assertEqual(rc, 0)
            _, split_rows = SF.read_pair(out_data, out_meta)
            payload = json.loads(manifest.read_text())
            self.assertEqual(payload["holdout_records"], 2)
            self.assertTrue(all(row.opening_id == opening_hold for row in split_rows[-2:]))
            self.assertTrue(all(row.opening_id == opening_train for row in split_rows[:2]))

    def test_mine_uses_actual_wdl_but_zeros_seed_targets_and_mirrors(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # White has +1 material. First game loses (frontier failure), second wins.
            failed = record(wm=bits(31, 32), bm=bits(10), stm=0, score=-900, wdl=-1)
            converted = record(wm=bits(33, 34), bm=bits(11), stm=0, score=800, wdl=1)
            data, meta = self.write_pair(
                root, "raw", [failed, converted],
                [SF.Meta(1, 1, 0), SF.Meta(2, 2, 1)],
            )
            out, manifest = root / "frontier.jnnw", root / "frontier.json"
            rc = SF.do_mine(Namespace(
                data=str(data), meta=str(meta), out=str(out), manifest=str(manifest),
                max_positions=4, min_pieces=2, max_pieces=24,
                margin_min=1, margin_max=3, converted_fraction=0.5, seed=19,
            ))
            self.assertEqual(rc, 0)
            raw = out.read_bytes()
            count = struct.unpack_from("<I", raw, 4)[0]
            self.assertEqual(count, 4)
            output = [raw[8 + i * SF.JNNW_REC:8 + (i + 1) * SF.JNNW_REC]
                      for i in range(count)]
            self.assertTrue(all(struct.unpack_from("<i", row, 33)[0] == 0 for row in output))
            self.assertTrue(all(struct.unpack_from("<b", row, 37)[0] == 0 for row in output))
            self.assertEqual(output[1], SF.mirror_record(output[0]))
            payload = json.loads(manifest.read_text())
            self.assertTrue(payload["labels_used_for_selection_only"])
            self.assertEqual(payload["external_teacher_inputs"], 0)
            self.assertEqual(payload["selected_kind"]["failed_conversion"], 1)


if __name__ == "__main__":
    unittest.main()
