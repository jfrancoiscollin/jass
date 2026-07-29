#!/usr/bin/env python3
from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from jobs.tools import l3_reverse_seed_matching as matching
from tools import selfplay_frontier as frontier


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "jobs/tests/fixtures/reverse_seed_matching_v1.json"


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


class ReverseSeedMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_cli_imports_from_outside_repository(self) -> None:
        script = ROOT / "jobs/tools/l3_reverse_seed_matching.py"
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--history-data", completed.stdout)

    def prepare_source(
        self, root: Path, records_payload: list[dict] | None = None
    ) -> tuple[Path, Path, Path, list[dict]]:
        rows_payload = list(records_payload or self.fixture["records"])
        train_rows = [row for row in rows_payload if row["role"] != "holdout"]
        holdout_rows = [row for row in rows_payload if row["role"] == "holdout"]
        rows_payload = train_rows + holdout_rows
        records = [make_record(row) for row in rows_payload]
        rows = [
            frontier.Meta(row["game_id"], row["opening_id"], row["seeded"])
            for row in rows_payload
        ]
        data = root / "history.fit.jnnw"
        meta = root / "history.fit.jsm"
        frontier.write_pair(data, meta, records, rows)
        train_count = len(train_rows)
        split_payload = {
            "schema": 1,
            "operation": "split",
            "split_unit": "opening_id",
            "seed": 577215,
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
        split = root / "history-split.json"
        split.write_text(
            json.dumps(split_payload, sort_keys=True) + "\n", encoding="utf-8"
        )
        return data, meta, split, rows_payload

    def mine_hard(
        self, root: Path, data: Path, meta: Path, split: Path
    ) -> Namespace:
        args = Namespace(
            data=str(data),
            meta=str(meta),
            split_manifest=str(split),
            out_replay=str(root / "hard-replay.jnnw"),
            out_meta=str(root / "hard-replay.jsm"),
            out_seeds=str(root / "hard-seeds.jnnw"),
            manifest=str(root / "hard-mining.json"),
            max_records=6,
            seed=1618033,
            signal="failed_conversion",
            one_per_game=True,
            colour_mirror=True,
            code_sha=self.fixture["code_sha"],
        )
        self.assertEqual(frontier.do_mine_hard(args), 0)
        return args

    def match_args(
        self,
        root: Path,
        data: Path,
        meta: Path,
        split: Path,
        hard: Namespace,
        suffix: str = "",
    ) -> Namespace:
        return Namespace(
            history_data=str(data),
            history_meta=str(meta),
            history_split_manifest=str(split),
            hard_replay=hard.out_replay,
            hard_meta=hard.out_meta,
            hard_seeds=hard.out_seeds,
            hard_manifest=hard.manifest,
            expected_hard_code_sha=self.fixture["code_sha"],
            source_temporal_id=self.fixture["source_temporal_id"],
            matching_seed=3141592,
            code_sha=self.fixture["matcher_code_sha"],
            out_control_seeds=str(root / f"control-seeds{suffix}.jnnw"),
            out_treatment_seeds=str(root / f"treatment-seeds{suffix}.jnnw"),
            manifest=str(root / f"matching{suffix}.json"),
        )

    @staticmethod
    def read_seeds(path: str | Path) -> list[bytes]:
        count, body = frontier._read_counted(
            Path(path), frontier.JNNW_MAGIC, frontier.JNNW_REC
        )
        return [
            body[index * frontier.JNNW_REC:(index + 1) * frontier.JNNW_REC]
            for index in range(count)
        ]

    def test_builds_deterministic_index_matched_colour_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, meta, split, source_payload = self.prepare_source(root)
            hard = self.mine_hard(root, data, meta, split)
            first = self.match_args(root, data, meta, split, hard, "-a")
            second = self.match_args(root, data, meta, split, hard, "-b")

            first_manifest = matching.build_matched_catalogues(first)
            second_manifest = matching.build_matched_catalogues(second)
            control = self.read_seeds(first.out_control_seeds)
            treatment = self.read_seeds(first.out_treatment_seeds)

            self.assertEqual(
                Path(first.out_control_seeds).read_bytes(),
                Path(second.out_control_seeds).read_bytes(),
            )
            self.assertEqual(
                Path(first.out_treatment_seeds).read_bytes(),
                Path(second.out_treatment_seeds).read_bytes(),
            )
            self.assertEqual(len(control), len(treatment))
            self.assertEqual(len(control), 6)
            source_temporal_id = self.fixture["source_temporal_id"]
            for index in range(0, len(control), 2):
                self.assertEqual(
                    control[index + 1], frontier.mirror_record(control[index])
                )
                self.assertEqual(
                    treatment[index + 1],
                    frontier.mirror_record(treatment[index]),
                )
                self.assertEqual(control[index][33:], b"\0" * 5)
                self.assertEqual(treatment[index][33:], b"\0" * 5)
                self.assertEqual(
                    matching._stratum(control[index], source_temporal_id),
                    matching._stratum(treatment[index], source_temporal_id),
                )

            source_by_game = {
                row["game_id"]: row for row in source_payload
                if row["role"] != "holdout"
            }
            hard_games = {
                row.game_id
                for row in frontier.read_pair(
                    Path(hard.out_replay), Path(hard.out_meta)
                )[1]
            }
            selected_positions = {
                frontier._canonical_position(record)
                for record in control[::2]
            }
            selected_source_games = set()
            for row in source_payload:
                if row["role"] == "holdout":
                    continue
                if frontier._canonical_position(make_record(row)) in selected_positions:
                    selected_source_games.add(row["game_id"])
            self.assertTrue(selected_source_games)
            self.assertFalse(selected_source_games & hard_games)
            self.assertTrue(selected_source_games <= set(source_by_game))

            self.assertEqual(
                first_manifest["matched_base_positions_by_stratum"],
                second_manifest["matched_base_positions_by_stratum"],
            )
            self.assertTrue(
                first_manifest["causal_certificate"]["same_index_ordered_strata"]
            )
            self.assertFalse(
                first_manifest["causal_certificate"]["control_selection_uses_wdl"]
            )
            self.assertFalse(first_manifest["training_authorized"])
            self.assertTrue(first_manifest["probe_authorized"])
            self.assertIsNone(first_manifest["automatic_next_job"])
            self.assertEqual(first_manifest["external_teacher_inputs"], 0)

    def test_fails_closed_when_a_matched_stratum_has_no_distinct_control(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            limited = [
                row for row in self.fixture["records"]
                if row["role"] != "control_thin"
            ]
            data, meta, split, _ = self.prepare_source(root, limited)
            hard = self.mine_hard(root, data, meta, split)
            args = self.match_args(root, data, meta, split, hard)
            with self.assertRaisesRegex(ValueError, "capacity insufficient"):
                matching.build_matched_catalogues(args)

    def test_candidate_buffer_is_bounded_by_unique_game_not_records(self) -> None:
        row = self.fixture["records"][1]
        record = make_record(row)
        stratum = matching._stratum(
            record, self.fixture["source_temporal_id"]
        )
        heap: list[tuple[int, int]] = []
        by_game: dict[int, matching.RankedCandidate] = {}

        for source_index in range(50):
            meta = frontier.Meta(8001, 9001, 0)
            matching._push_candidate(
                heap,
                by_game,
                matching.RankedCandidate(
                    matching._game_priority(8001, stratum, 3141592),
                    matching._candidate_priority(
                        record,
                        meta,
                        3141592,
                        self.fixture["source_temporal_id"],
                    ),
                    source_index,
                    record,
                    meta,
                ),
                3,
            )
        self.assertEqual(set(by_game), {8001})

        for game_id in (8002, 8003, 8004, 8005):
            meta = frontier.Meta(game_id, game_id + 1000, 0)
            matching._push_candidate(
                heap,
                by_game,
                matching.RankedCandidate(
                    matching._game_priority(game_id, stratum, 3141592),
                    matching._candidate_priority(
                        record,
                        meta,
                        3141592,
                        self.fixture["source_temporal_id"],
                    ),
                    game_id,
                    record,
                    meta,
                ),
                3,
            )

        self.assertEqual(len(heap), 3)
        self.assertEqual(len(by_game), 3)
        self.assertEqual(
            set(by_game),
            {-entry[1] for entry in heap},
        )

    def test_authentication_and_unseeded_source_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            altered = [dict(row) for row in self.fixture["records"]]
            altered[1]["seeded"] = 1
            data, meta, split, _ = self.prepare_source(root, altered)
            hard = self.mine_hard(root, data, meta, split)
            args = self.match_args(root, data, meta, split, hard)
            with self.assertRaisesRegex(ValueError, "not pure unseeded"):
                matching.build_matched_catalogues(args)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, meta, split, _ = self.prepare_source(root)
            hard = self.mine_hard(root, data, meta, split)
            seed_path = Path(hard.out_seeds)
            raw = bytearray(seed_path.read_bytes())
            raw[-1] ^= 1
            seed_path.write_bytes(raw)
            args = self.match_args(root, data, meta, split, hard)
            with self.assertRaisesRegex(ValueError, "output mismatch"):
                matching.build_matched_catalogues(args)

    def test_rejects_overwrite_and_invalid_identity_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, meta, split, _ = self.prepare_source(root)
            hard = self.mine_hard(root, data, meta, split)
            args = self.match_args(root, data, meta, split, hard)
            Path(args.out_control_seeds).write_bytes(b"occupied")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                matching.build_matched_catalogues(args)

            Path(args.out_control_seeds).unlink()
            args.code_sha = "short"
            with self.assertRaisesRegex(ValueError, "40-hex"):
                matching.build_matched_catalogues(args)


if __name__ == "__main__":
    unittest.main()
