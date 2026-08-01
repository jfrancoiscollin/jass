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
                no_wdl_check=True,
            ))
            self.assertEqual(rc, 0)
            records, rows = SF.read_pair(out_data, out_meta)
            self.assertEqual(records, [rec_a, rec_b])
            self.assertNotEqual(rows[0].game_id, rows[1].game_id)
            self.assertEqual([row.seeded for row in rows], [0, 1])

    def test_nested_merge_remaps_ids_but_preserves_opening_groups(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = [
                record(wm=bits(31), bm=bits(10), wdl=1),
                record(wm=bits(32), bm=bits(11), wdl=0),
                record(wm=bits(33), bm=bits(12), wdl=-1),
            ]
            nested = 7 << 48
            a = self.write_pair(
                root, "nested", records,
                [
                    SF.Meta(nested | 10, nested | 20, 0),
                    SF.Meta(nested | 11, nested | 20, 0),
                    SF.Meta(nested | 12, nested | 21, 0),
                ],
            )
            out_data, out_meta = root / "all.jnnw", root / "all.jsm"
            rc = SF.do_merge(Namespace(
                pair=[[str(a[0]), str(a[1])]],
                out_data=str(out_data), out_meta=str(out_meta), manifest=None,
                renamespace_nested=True,
            ))
            self.assertEqual(rc, 0)
            merged_records, rows = SF.read_pair(out_data, out_meta)
            self.assertEqual(merged_records, records)
            self.assertEqual(rows[0].opening_id, rows[1].opening_id)
            self.assertNotEqual(rows[1].opening_id, rows[2].opening_id)
            self.assertTrue(all(row.opening_id < (2 << 48) for row in rows))

    def test_mix_is_exact_deterministic_aligned_and_preserves_opening_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d10_records = [
                record(wm=bits(31 + (index % 10)), bm=bits(10), score=index, wdl=1)
                for index in range(12)
            ]
            d12_records = [
                record(wm=bits(31 + (index % 10)), bm=bits(11), score=100 + index, wdl=-1)
                for index in range(12)
            ]
            d10_rows = [
                SF.Meta(index // 2, 100 + index // 4, 0) for index in range(12)
            ]
            d12_rows = [
                SF.Meta(index // 2, 100 + index // 4, 0) for index in range(12)
            ]
            d10 = self.write_pair(root, "d10", d10_records, d10_rows)
            d12 = self.write_pair(root, "d12", d12_records, d12_rows)

            outputs = []
            for suffix in ("a", "b"):
                out_data = root / f"mix-{suffix}.jnnw"
                out_meta = root / f"mix-{suffix}.jsm"
                manifest = root / f"mix-{suffix}.json"
                rc = SF.do_mix(Namespace(
                    source=[
                        ["D10", str(d10[0]), str(d10[1]), "5"],
                        ["D12", str(d12[0]), str(d12[1]), "1"],
                    ],
                    target_records=6,
                    seed=271828,
                    out_data=str(out_data),
                    out_meta=str(out_meta),
                    manifest=str(manifest),
                ))
                self.assertEqual(rc, 0)
                outputs.append((out_data.read_bytes(), out_meta.read_bytes()))
                payload = json.loads(manifest.read_text())
                self.assertEqual(payload["records"], 6)
                self.assertEqual(
                    [source["selected_records"] for source in payload["sources"]],
                    [5, 1],
                )
                self.assertTrue(all(
                    len(source["selected_data_sha256"]) == 64
                    and len(source["selected_meta_sha256"]) == 64
                    for source in payload["sources"]
                ))
                self.assertEqual(
                    payload["opening_id_policy"],
                    "preserved_across_sources_for_common_holdout_fold",
                )
                records_out, rows_out = SF.read_pair(out_data, out_meta)
                self.assertEqual(len(records_out), len(rows_out))
                self.assertEqual(len(records_out), 6)
                self.assertTrue(all(row.opening_id in {100, 101, 102} for row in rows_out))
                self.assertEqual(len({row.game_id >> 56 for row in rows_out}), 2)
            self.assertEqual(outputs[0], outputs[1])

    def test_mix_rejects_a_quota_larger_than_its_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pair = self.write_pair(
                root,
                "tiny",
                [record(wm=bits(31), bm=bits(10), wdl=1)],
                [SF.Meta(1, 1, 0)],
            )
            with self.assertRaisesRegex(ValueError, "quota"):
                SF.do_mix(Namespace(
                    source=[["TINY", str(pair[0]), str(pair[1]), "1"]],
                    target_records=2,
                    seed=1,
                    out_data=str(root / "out.jnnw"),
                    out_meta=str(root / "out.jsm"),
                    manifest=None,
                ))

    def test_mix_can_namespace_unrelated_opening_ids_by_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = [
                record(wm=bits(31), bm=bits(10), score=1, wdl=1),
                record(wm=bits(32), bm=bits(11), score=2, wdl=-1),
            ]
            parent = self.write_pair(
                root,
                "parent",
                records,
                [SF.Meta(1, 7, 0), SF.Meta(2, 8, 0)],
            )
            fresh = self.write_pair(
                root,
                "fresh",
                records,
                [SF.Meta(1, 7, 0), SF.Meta(2, 8, 0)],
            )
            out_data, out_meta = root / "mix.jnnw", root / "mix.jsm"
            manifest = root / "mix.json"
            rc = SF.do_mix(Namespace(
                source=[
                    ["PARENT", str(parent[0]), str(parent[1]), "1"],
                    ["FRESH", str(fresh[0]), str(fresh[1]), "1"],
                ],
                target_records=4,
                seed=141421,
                out_data=str(out_data),
                out_meta=str(out_meta),
                manifest=str(manifest),
                namespace_openings=True,
            ))
            self.assertEqual(rc, 0)
            _, rows = SF.read_pair(out_data, out_meta)
            self.assertEqual({row.opening_id >> 56 for row in rows}, {1, 2})
            self.assertEqual(len({row.opening_id for row in rows}), 4)
            payload = json.loads(manifest.read_text())
            self.assertEqual(
                payload["opening_id_policy"],
                "source_namespaced_for_independent_temporal_corpora",
            )
            self.assertEqual(payload["source_opening_id_overlaps"]["PARENT__FRESH"], 2)

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

    def test_mine_regret_selects_one_worst_parent_error_per_game(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            positions = [
                record(wm=bits(31, 32), bm=bits(10), stm=0, score=0, wdl=1),
                record(wm=bits(33, 34), bm=bits(11), stm=0, score=0, wdl=1),
                record(wm=bits(35), bm=bits(12, 13), stm=1, score=0, wdl=-1),
                record(wm=bits(36), bm=bits(14, 15), stm=1, score=0, wdl=-1),
            ]
            rows = [
                SF.Meta(1, 10, 0), SF.Meta(1, 10, 0),
                SF.Meta(2, 20, 1), SF.Meta(2, 20, 1),
            ]
            data, meta = self.write_pair(root, "raw", positions, rows)
            # For game 1, a large negative score contradicts a win. For game 2,
            # a large positive score contradicts a loss. The other position in
            # each game is confidently correct and must not be selected.
            scored = [
                positions[0][:33] + struct.pack("<i", -400) + struct.pack("<b", 1),
                positions[1][:33] + struct.pack("<i", 400) + struct.pack("<b", 1),
                positions[2][:33] + struct.pack("<i", 300) + struct.pack("<b", -1),
                positions[3][:33] + struct.pack("<i", -300) + struct.pack("<b", -1),
            ]
            scored_path = root / "scored.jnnw"
            scored_path.write_bytes(
                SF.JNNW_MAGIC + struct.pack("<I", len(scored)) + b"".join(scored)
            )
            out, manifest = root / "regret.jnnw", root / "regret.json"
            rc = SF.do_mine_regret(Namespace(
                data=str(data), meta=str(meta), scored_data=str(scored_path),
                out=str(out), manifest=str(manifest), max_positions=4,
                score_scale_cp=100.0, min_regret=0.0, seed=23,
            ))
            self.assertEqual(rc, 0)
            output = SF.read_jnnw(out)
            self.assertEqual(len(output), 4)
            selected_positions = {row[:33] for row in output}
            self.assertIn(positions[0][:33], selected_positions)
            self.assertIn(positions[2][:33], selected_positions)
            self.assertNotIn(positions[1][:33], selected_positions)
            self.assertNotIn(positions[3][:33], selected_positions)
            self.assertTrue(
                all(struct.unpack_from("<i", row, 33)[0] == 0 for row in output)
            )
            self.assertTrue(
                all(struct.unpack_from("<b", row, 37)[0] == 0 for row in output)
            )
            payload = json.loads(manifest.read_text())
            self.assertEqual(payload["candidate_games"], 2)
            self.assertEqual(
                payload["selection_unit"],
                "one_highest_regret_position_per_game",
            )
            self.assertTrue(payload["labels_used_for_selection_only"])
            self.assertEqual(payload["external_teacher_inputs"], 0)

    def test_mine_regret_rejects_misaligned_scored_corpus(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = record(wm=bits(31), bm=bits(10), wdl=1)
            data, meta = self.write_pair(
                root, "raw", [source], [SF.Meta(1, 1, 0)],
            )
            scored = record(wm=bits(32), bm=bits(10), score=-300, wdl=1)
            scored_path = root / "scored.jnnw"
            scored_path.write_bytes(
                SF.JNNW_MAGIC + struct.pack("<I", 1) + scored
            )
            with self.assertRaisesRegex(ValueError, "position mismatch"):
                SF.do_mine_regret(Namespace(
                    data=str(data), meta=str(meta), scored_data=str(scored_path),
                    out=str(root / "out.jnnw"), manifest=None, max_positions=2,
                    score_scale_cp=100.0, min_regret=0.0, seed=1,
                ))

    def test_profile_reports_diversity_and_material_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = [
                record(wm=bits(31, 32), bm=bits(10), stm=0, wdl=1),
                record(wm=bits(33, 34), bm=bits(11), stm=0, wdl=0),
                record(wm=bits(30), bm=bits(9), stm=1, wdl=-1),
            ]
            rows = [
                SF.Meta(1, 10, 0),
                SF.Meta(2, 10, 0),
                SF.Meta(3, 20, 0),
            ]
            data, meta = self.write_pair(root, "raw", records, rows)
            manifest = root / "profile.json"
            rc = SF.do_profile(Namespace(
                data=str(data), meta=str(meta), manifest=str(manifest),
            ))
            self.assertEqual(rc, 0)
            payload = json.loads(manifest.read_text())
            self.assertTrue(payload["diagnostic_only"])
            self.assertEqual(payload["records"], 3)
            self.assertEqual(payload["games"], 3)
            self.assertEqual(payload["openings"], 2)
            self.assertEqual(payload["unique_positions"], 3)
            self.assertEqual(payload["material_stratum_records"]["p3_thin"], 2)
            self.assertEqual(payload["material_stratum_records"]["p4_equal"], 1)
            self.assertEqual(
                payload["record_level_conversion"]["p3_thin"]["converted_records"], 1)
            self.assertEqual(
                payload["record_level_conversion_unit"],
                "correlated_position_record_not_gate",
            )


if __name__ == "__main__":
    unittest.main()
