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
FIXTURE = ROOT / "jobs/tests/fixtures/hard_mining_v1.json"
SPEC = importlib.util.spec_from_file_location("selfplay_frontier_hard", MODULE)
SF = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SF
SPEC.loader.exec_module(SF)


def bits(squares: list[int]) -> int:
    value = 0
    for square in squares:
        value |= 1 << (square - 1)
    return value


def make_record(row: dict) -> bytes:
    return struct.pack(
        "<QQQQBiB",
        bits(row.get("white_men", [])),
        bits(row.get("white_kings", [])),
        bits(row.get("black_men", [])),
        bits(row.get("black_kings", [])),
        row["stm"],
        row["score"],
        row["wdl"] & 0xFF,
    )


class HardMiningV1Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def prepare(self, root: Path):
        records = [make_record(row) for row in self.fixture["records"]]
        rows = [
            SF.Meta(row["game_id"], row["opening_id"], row["seeded"])
            for row in self.fixture["records"]
        ]
        data = root / "input.jnnw"
        meta = root / "input.jsm"
        SF.write_pair(data, meta, records, rows)
        train_count = self.fixture["train_records"]
        manifest = root / "split.json"
        split = {
            "schema": 1,
            "operation": "split",
            "split_unit": "opening_id",
            "seed": 17,
            "holdout_mod": 10,
            "records": len(records),
            "train_records": train_count,
            "holdout_records": len(records) - train_count,
            "train_openings": len(
                {row.opening_id for row in rows[:train_count]}
            ),
            "holdout_openings": len(
                {row.opening_id for row in rows[train_count:]}
            ),
            "tail_is_holdout": True,
        }
        manifest.write_text(
            json.dumps(split, sort_keys=True) + "\n", encoding="utf-8"
        )
        return records, rows, data, meta, manifest

    def arguments(
        self, root: Path, data: Path, meta: Path, split: Path, suffix: str = ""
    ) -> Namespace:
        return Namespace(
            data=str(data),
            meta=str(meta),
            split_manifest=str(split),
            out_replay=str(root / f"hard-replay{suffix}.jnnw"),
            out_meta=str(root / f"hard-replay{suffix}.jsm"),
            out_seeds=str(root / f"hard-seeds{suffix}.jnnw"),
            manifest=str(root / f"hard-mining-manifest{suffix}.json"),
            max_records=6,
            seed=271828,
            signal="failed_conversion",
            one_per_game=True,
            colour_mirror=True,
            code_sha=self.fixture["code_sha"],
        )

    @staticmethod
    def read_jnnw(path: Path) -> list[bytes]:
        count, body = SF._read_counted(path, SF.JNNW_MAGIC, SF.JNNW_REC)
        return [
            body[index * SF.JNNW_REC:(index + 1) * SF.JNNW_REC]
            for index in range(count)
        ]

    def test_reference_fixture_is_aligned_deterministic_and_train_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_records, source_meta, data, meta, split = self.prepare(root)
            args = self.arguments(root, data, meta, split, "-a")

            self.assertEqual(SF.do_mine_hard(args), 0)
            first_bytes = {
                name: Path(getattr(args, name)).read_bytes()
                for name in ("out_replay", "out_meta", "out_seeds")
            }
            second_args = self.arguments(root, data, meta, split, "-b")
            self.assertEqual(SF.do_mine_hard(second_args), 0)
            second_bytes = {
                name: Path(getattr(second_args, name)).read_bytes()
                for name in ("out_replay", "out_meta", "out_seeds")
            }
            self.assertEqual(first_bytes, second_bytes)
            self.assertFalse(any(root.glob("*.tmp")))

            replay, replay_meta = SF.read_pair(
                Path(args.out_replay), Path(args.out_meta)
            )
            seeds = self.read_jnnw(Path(args.out_seeds))
            expected = self.fixture["expected"]
            self.assertEqual(len(replay), expected["output_records"])
            self.assertEqual(len(replay_meta), len(replay))
            self.assertEqual(len(seeds), len(replay))

            train_records = source_records[: self.fixture["train_records"]]
            train_meta = source_meta[: self.fixture["train_records"]]
            records_by_game: dict[int, list[bytes]] = {}
            for record, row in zip(train_records, train_meta):
                records_by_game.setdefault(row.game_id, []).append(record)

            base_games = []
            for index in range(0, len(replay), 2):
                original = replay[index]
                mirrored = replay[index + 1]
                original_meta = replay_meta[index]
                self.assertEqual(replay_meta[index + 1], original_meta)
                self.assertIn(original, records_by_game[original_meta.game_id])
                self.assertEqual(
                    mirrored, SF._mirror_record_preserve_targets(original)
                )
                self.assertEqual(mirrored[33:], original[33:])
                self.assertEqual(seeds[index][:33], original[:33])
                self.assertEqual(seeds[index + 1][:33], mirrored[:33])
                base_games.append(original_meta.game_id)

            self.assertEqual(len(base_games), len(set(base_games)))
            self.assertNotIn(100, base_games)
            holdout_openings = {
                row.opening_id
                for row in source_meta[self.fixture["train_records"] :]
            }
            self.assertFalse(
                {row.opening_id for row in replay_meta} & holdout_openings
            )
            self.assertTrue(all(record[33:] == b"\0" * 5 for record in seeds))
            self.assertEqual(
                len({SF._canonical_position(row) for row in replay}),
                expected["selected_base_positions"],
            )

            payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            self.assertEqual(payload["operation"], "mine-hard")
            self.assertEqual(payload["selection_scope"], "train_only")
            self.assertEqual(payload["holdout_records_examined_for_signal"], 0)
            self.assertEqual(payload["external_teacher_inputs"], 0)
            self.assertEqual(
                payload["candidates"]["signal_records"],
                expected["signal_records"],
            )
            self.assertEqual(
                payload["candidates"]["after_one_per_game"],
                expected["after_one_per_game"],
            )
            self.assertEqual(
                payload["candidates"]["after_canonical_dedup"],
                expected["after_canonical_dedup"],
            )
            self.assertEqual(
                payload["selection"]["base_positions"],
                expected["selected_base_positions"],
            )
            self.assertEqual(payload["deduplication"]["one_per_game_dropped"], 1)
            self.assertEqual(
                payload["deduplication"]["canonical_position_dropped"], 1
            )
            self.assertTrue(
                payload["targets"]["hard_replay_original_wdl_and_score_preserved"]
            )
            self.assertTrue(payload["targets"]["hard_seeds_score_zero"])
            self.assertTrue(payload["targets"]["hard_seeds_wdl_zero"])
            self.assertTrue(payload["split"]["verified_opening_disjoint"])
            self.assertEqual(payload["split"]["selected_holdout_opening_overlap"], 0)
            self.assertTrue(payload["selection"]["by_category"])
            for output in payload["outputs"].values():
                self.assertEqual(len(output["sha256"]), 64)
            second_payload = json.loads(
                Path(second_args.manifest).read_text(encoding="utf-8")
            )
            self.assertEqual(
                {
                    key: value["sha256"]
                    for key, value in payload["outputs"].items()
                },
                {
                    key: value["sha256"]
                    for key, value in second_payload["outputs"].items()
                },
            )

    def test_rejects_truncated_or_misaligned_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, data, meta, split = self.prepare(root)
            args = self.arguments(root, data, meta, split)

            data.write_bytes(data.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, "size"):
                SF.do_mine_hard(args)

            _, _, data, meta, split = self.prepare(root)
            raw_meta = meta.read_bytes()
            count = struct.unpack_from("<I", raw_meta, 4)[0]
            meta.write_bytes(raw_meta[:4] + struct.pack("<I", count - 1)
                             + raw_meta[8:-SF.META_REC])
            with self.assertRaisesRegex(ValueError, "count mismatch"):
                SF.do_mine_hard(self.arguments(root, data, meta, split))

    def test_rejects_incompatible_or_leaking_split_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, rows, data, meta, split = self.prepare(root)
            args = self.arguments(root, data, meta, split)

            payload = json.loads(split.read_text(encoding="utf-8"))
            payload["tail_is_holdout"] = False
            split.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incompatible tail_is_holdout"):
                SF.do_mine_hard(args)

            _, _, data, meta, split = self.prepare(root)
            payload = json.loads(split.read_text(encoding="utf-8"))
            payload["train_records"] += 1
            split.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "record counts"):
                SF.do_mine_hard(self.arguments(root, data, meta, split))

            _, rows, data, meta, split = self.prepare(root)
            leaking_rows = list(rows)
            leaking_rows[-1] = SF.Meta(
                leaking_rows[-1].game_id, leaking_rows[0].opening_id, 0
            )
            source_records = self.read_jnnw(data)
            SF.write_pair(data, meta, source_records, leaking_rows)
            payload = json.loads(split.read_text(encoding="utf-8"))
            payload["holdout_openings"] = len(
                {
                    row.opening_id
                    for row in leaking_rows[self.fixture["train_records"] :]
                }
            )
            split.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "leak across train/holdout"):
                SF.do_mine_hard(self.arguments(root, data, meta, split))

    def test_requires_explicit_v1_safety_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, data, meta, split = self.prepare(root)
            args = self.arguments(root, data, meta, split)

            args.one_per_game = False
            with self.assertRaisesRegex(ValueError, "one-per-game"):
                SF.do_mine_hard(args)
            args.one_per_game = True
            args.colour_mirror = False
            with self.assertRaisesRegex(ValueError, "colour-mirror"):
                SF.do_mine_hard(args)
            args.colour_mirror = True
            args.max_records = 5
            with self.assertRaisesRegex(ValueError, "even integer"):
                SF.do_mine_hard(args)
            args.max_records = 6
            args.code_sha = "short"
            with self.assertRaisesRegex(ValueError, "40-hex"):
                SF.do_mine_hard(args)


if __name__ == "__main__":
    unittest.main()
