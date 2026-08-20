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

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SF_PATH = ROOT / "tools" / "selfplay_frontier.py"
SF_SPEC = importlib.util.spec_from_file_location("selfplay_frontier", SF_PATH)
SF = importlib.util.module_from_spec(SF_SPEC)
assert SF_SPEC.loader is not None
sys.modules[SF_SPEC.name] = SF
SF_SPEC.loader.exec_module(SF)

MIX_PATH = ROOT / "tools" / "contextual_replay_mix.py"
MIX_SPEC = importlib.util.spec_from_file_location("contextual_replay_mix", MIX_PATH)
MIX = importlib.util.module_from_spec(MIX_SPEC)
assert MIX_SPEC.loader is not None
sys.modules[MIX_SPEC.name] = MIX
MIX_SPEC.loader.exec_module(MIX)


def bits(*squares: int) -> int:
    value = 0
    for square in squares:
        value |= 1 << (square - 1)
    return value


def record(*, wm=0, wk=0, bm=0, bk=0, stm=0, score=0, wdl=0) -> bytes:
    return struct.pack("<QQQQBiB", wm, wk, bm, bk, stm, score, wdl & 0xFF)


def score_of(raw: bytes) -> int:
    return struct.unpack_from("<i", raw, 33)[0]


class ContextualReplayMixTests(unittest.TestCase):
    def write_pair(self, root: Path, name: str, records, rows):
        data = root / f"{name}.jnnw"
        meta = root / f"{name}.jsm"
        SF.write_pair(data, meta, list(records), list(rows))
        return data, meta

    def args(self, root: Path, old, new, *, old_train: int, new_train: int, seed=17, targets=False):
        kwargs = dict(
            old_data=str(old[0]), old_meta=str(old[1]), old_train_count=old_train,
            new_data=str(new[0]), new_meta=str(new[1]), new_train_count=new_train,
            old_share=0.25, new_share=0.75, seed=seed,
            out_data=str(root / "mix.jnnw"), out_meta=str(root / "mix.jsm"),
            out_weights=str(root / "mix-weights.npy"), manifest=str(root / "mix.json"),
            downgrade_meta=None, old_targets=None, new_targets=None, out_targets=None,
        )
        if targets:
            kwargs.update(
                old_targets=str(root / "old-targets.npy"),
                new_targets=str(root / "new-targets.npy"),
                out_targets=str(root / "mix-targets.npy"),
            )
        return Namespace(**kwargs)

    def make_sources(self, root: Path):
        # OLD train prefix: four whole opening groups of two rows each.  Two
        # holdout rows use scores 900+ and must never enter replay.
        old_records = []
        old_rows = []
        for opening in range(4):
            for ply in range(2):
                old_records.append(record(
                    wm=bits(31 + opening),
                    wk=bits(45) if opening >= 2 else 0,
                    bm=bits(10, 11),
                    score=opening * 10 + ply,
                    wdl=1 if opening % 2 == 0 else -1,
                ))
                old_rows.append(SF.Meta(opening * 10 + ply, 100 + opening, opening == 3))
        old_records += [
            record(wm=bits(31), bm=bits(10), score=900, wdl=1),
            record(wm=bits(32), bm=bits(11), score=901, wdl=-1),
        ]
        old_rows += [SF.Meta(90, 190, 0), SF.Meta(91, 191, 0)]

        # NEW train prefix: six rows, then two holdout sentinels 990+.
        new_records = [
            record(wm=bits(35 + (i % 4)), bm=bits(12, 13), score=100 + i,
                   wdl=1 if i % 2 == 0 else -1)
            for i in range(6)
        ] + [
            record(wm=bits(40), bm=bits(14), score=990, wdl=0),
            record(wm=bits(41), bm=bits(15), score=991, wdl=0),
        ]
        new_rows = [SF.Meta(200 + i, 300 + i // 2, 0) for i in range(8)]
        return (
            self.write_pair(root, "old", old_records, old_rows),
            self.write_pair(root, "new", new_records, new_rows),
            old_records, new_records,
        )

    def test_keeps_all_new_train_excludes_both_holdouts_and_uses_whole_old_openings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old, new, old_records, _ = self.make_sources(root)
            args = self.args(root, old, new, old_train=8, new_train=6)
            payload = MIX.build_replay_mix(args)
            mixed_records, mixed_rows = SF.read_pair(Path(args.out_data), Path(args.out_meta))
            old_n = payload["row_budget"]["selected_old_replay_records"]
            self.assertEqual(len(mixed_records), old_n + 6)
            scores = [score_of(row) for row in mixed_records]
            self.assertNotIn(900, scores)
            self.assertNotIn(901, scores)
            self.assertNotIn(990, scores)
            self.assertNotIn(991, scores)
            self.assertEqual(scores[old_n:], list(range(100, 106)))

            selected_old_scores = scores[:old_n]
            selected_openings = {score // 10 for score in selected_old_scores}
            for opening in selected_openings:
                expected = {opening * 10, opening * 10 + 1}
                self.assertEqual(
                    {score for score in selected_old_scores if score // 10 == opening},
                    expected,
                )
            self.assertEqual(
                payload["selection"]["selected_old_openings"], len(selected_openings)
            )
            # Source namespaces must make OLD and NEW IDs disjoint.
            self.assertTrue(all((row.opening_id >> 56) == 1 for row in mixed_rows[:old_n]))
            self.assertTrue(all((row.opening_id >> 56) == 2 for row in mixed_rows[old_n:]))

    def test_sample_weights_make_effective_mass_25_75_independent_of_row_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old, new, _, _ = self.make_sources(root)
            args = self.args(root, old, new, old_train=8, new_train=6)
            payload = MIX.build_replay_mix(args)
            old_n = payload["row_budget"]["selected_old_replay_records"]
            weights = np.load(args.out_weights, allow_pickle=False)
            old_mass = float(np.sum(weights[:old_n], dtype=np.float64))
            new_mass = float(np.sum(weights[old_n:], dtype=np.float64))
            self.assertAlmostEqual(old_mass / (old_mass + new_mass), 0.25, places=7)
            self.assertAlmostEqual(new_mass / (old_mass + new_mass), 0.75, places=7)
            self.assertEqual(weights.dtype, np.dtype(np.float32))
            self.assertTrue(np.all(weights > 0.0))

    def test_external_targets_follow_selected_records_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old, new, old_records, new_records = self.make_sources(root)
            np.save(root / "old-targets.npy", np.linspace(0.01, 0.99, len(old_records), dtype=np.float32))
            np.save(root / "new-targets.npy", np.linspace(0.11, 0.88, len(new_records), dtype=np.float32))
            args = self.args(root, old, new, old_train=8, new_train=6, targets=True)
            payload = MIX.build_replay_mix(args)
            mixed_records, _ = SF.read_pair(Path(args.out_data), Path(args.out_meta))
            mixed_targets = np.load(args.out_targets, allow_pickle=False)
            old_targets = np.load(args.old_targets, allow_pickle=False)
            new_targets = np.load(args.new_targets, allow_pickle=False)
            old_n = payload["row_budget"]["selected_old_replay_records"]
            by_score = {score_of(raw): old_targets[index] for index, raw in enumerate(old_records[:8])}
            for index, raw in enumerate(mixed_records[:old_n]):
                self.assertEqual(mixed_targets[index], by_score[score_of(raw)])
            np.testing.assert_array_equal(mixed_targets[old_n:], new_targets[:6])

    def test_same_seed_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old, new, _, _ = self.make_sources(root)
            snapshots = []
            for suffix in ("a", "b"):
                run = root / suffix
                run.mkdir()
                args = self.args(run, old, new, old_train=8, new_train=6, seed=271828)
                MIX.build_replay_mix(args)
                snapshots.append((
                    Path(args.out_data).read_bytes(),
                    Path(args.out_meta).read_bytes(),
                    Path(args.out_weights).read_bytes(),
                ))
            self.assertEqual(snapshots[0], snapshots[1])

    def test_mixed_jsm_schemas_require_explicit_downgrade(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_records = [record(score=1), record(score=2)]
            old = self.write_pair(root, "old", old_records, [SF.Meta(1, 1, 0), SF.Meta(2, 2, 0)])
            new_records = [record(score=10), record(score=11)]
            new_rows = [
                SF.Meta(10, 10, 0, 0, 2, 0xFFFF, 1, 0),
                SF.Meta(11, 11, 0, 1, 2, 0xFFFF, -1, 0),
            ]
            new = self.write_pair(root, "new", new_records, new_rows)
            args = self.args(root, old, new, old_train=2, new_train=2)
            with self.assertRaisesRegex(ValueError, "metadata schemas differ"):
                MIX.build_replay_mix(args)

            args.downgrade_meta = "jsm1"
            payload = MIX.build_replay_mix(args)
            self.assertEqual(Path(args.out_meta).read_bytes()[:4], b"JSM1")
            self.assertTrue(payload["metadata"]["downgraded_to_jsm1"])

    def test_rejects_invalid_effective_mass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old, new, _, _ = self.make_sources(root)
            args = self.args(root, old, new, old_train=8, new_train=6)
            args.old_share = 0.30
            args.new_share = 0.75
            with self.assertRaisesRegex(ValueError, "must equal 1"):
                MIX.build_replay_mix(args)


if __name__ == "__main__":
    unittest.main()
