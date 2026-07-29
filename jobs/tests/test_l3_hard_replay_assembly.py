#!/usr/bin/env python3
from __future__ import annotations

import json
import struct
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from jobs.tools import l3_hard_replay_assembly as assembly
from tools import selfplay_frontier as frontier


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "jobs/tests/fixtures/hard_mining_v1.json"


def _bits(squares: list[int]) -> int:
    value = 0
    for square in squares:
        value |= 1 << (square - 1)
    return value


def _record(row: dict) -> bytes:
    return struct.pack(
        "<QQQQBiB",
        _bits(row.get("white_men", [])),
        _bits(row.get("white_kings", [])),
        _bits(row.get("black_men", [])),
        _bits(row.get("black_kings", [])),
        row["stm"],
        row["score"],
        row["wdl"] & 0xFF,
    )


def _split_manifest(
    path: Path, rows: list[frontier.Meta], train_count: int, seed: int
) -> None:
    payload = {
        "schema": 1,
        "operation": "split",
        "split_unit": "opening_id",
        "seed": seed,
        "holdout_mod": 10,
        "records": len(rows),
        "train_records": train_count,
        "holdout_records": len(rows) - train_count,
        "train_openings": len({row.opening_id for row in rows[:train_count]}),
        "holdout_openings": len({row.opening_id for row in rows[train_count:]}),
        "tail_is_holdout": True,
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


class HardReplayAssemblyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def _prepare(self, root: Path) -> dict[str, Path]:
        history_records = [_record(row) for row in self.fixture["records"]]
        history_rows = [
            frontier.Meta(row["game_id"], row["opening_id"], row["seeded"])
            for row in self.fixture["records"]
        ]
        history_data = root / "history.fit.jnnw"
        history_meta = root / "history.fit.jsm"
        history_split = root / "history-split.json"
        frontier.write_pair(
            history_data, history_meta, history_records, history_rows
        )
        _split_manifest(
            history_split,
            history_rows,
            self.fixture["train_records"],
            seed=17,
        )

        hard_data = root / "hard-replay.jnnw"
        hard_meta = root / "hard-replay.jsm"
        hard_seeds = root / "hard-seeds.jnnw"
        hard_manifest = root / "hard-mining.json"
        frontier.do_mine_hard(
            Namespace(
                data=str(history_data),
                meta=str(history_meta),
                split_manifest=str(history_split),
                out_replay=str(hard_data),
                out_meta=str(hard_meta),
                out_seeds=str(hard_seeds),
                manifest=str(hard_manifest),
                max_records=6,
                seed=271828,
                signal="failed_conversion",
                one_per_game=True,
                colour_mirror=True,
                code_sha=self.fixture["code_sha"],
            )
        )

        fresh_records = []
        fresh_rows = []
        for index in range(24):
            fresh_records.append(
                struct.pack(
                    "<QQQQBiB",
                    1 << (index % 20),
                    0,
                    1 << (20 + index % 20),
                    0,
                    index % 2,
                    index - 12,
                    (-1, 0, 1)[index % 3] & 0xFF,
                )
            )
            fresh_rows.append(frontier.Meta(1000 + index, 2000 + index, 0))
        fresh_data = root / "fresh.fit.jnnw"
        fresh_meta = root / "fresh.fit.jsm"
        fresh_split = root / "fresh-split.json"
        frontier.write_pair(fresh_data, fresh_meta, fresh_records, fresh_rows)
        _split_manifest(fresh_split, fresh_rows, train_count=18, seed=29)

        return {
            "history_data": history_data,
            "history_meta": history_meta,
            "history_split": history_split,
            "hard_data": hard_data,
            "hard_meta": hard_meta,
            "hard_manifest": hard_manifest,
            "fresh_data": fresh_data,
            "fresh_meta": fresh_meta,
            "fresh_split": fresh_split,
        }

    def _args(
        self, root: Path, inputs: dict[str, Path], suffix: str
    ) -> Namespace:
        return Namespace(
            history_data=str(inputs["history_data"]),
            history_meta=str(inputs["history_meta"]),
            history_split_manifest=str(inputs["history_split"]),
            fresh_data=str(inputs["fresh_data"]),
            fresh_meta=str(inputs["fresh_meta"]),
            fresh_split_manifest=str(inputs["fresh_split"]),
            hard_data=str(inputs["hard_data"]),
            hard_meta=str(inputs["hard_meta"]),
            hard_manifest=str(inputs["hard_manifest"]),
            replay_records=6,
            fresh_records=24,
            uniform_seed=314159,
            code_sha=self.fixture["code_sha"],
            hard_manifest_code_sha=self.fixture["code_sha"],
            out_control_data=str(root / f"control{suffix}.jnnw"),
            out_control_meta=str(root / f"control{suffix}.jsm"),
            out_treatment_data=str(root / f"treatment{suffix}.jnnw"),
            out_treatment_meta=str(root / f"treatment{suffix}.jsm"),
            manifest=str(root / f"assembly{suffix}.json"),
        )

    def test_assembles_deterministic_arms_with_a_bit_identical_common_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._prepare(root)
            args_a = self._args(root, inputs, "-a")
            args_b = self._args(root, inputs, "-b")

            first = assembly.assemble(args_a)
            second = assembly.assemble(args_b)

            for stem in (
                "out_control_data",
                "out_control_meta",
                "out_treatment_data",
                "out_treatment_meta",
            ):
                self.assertEqual(
                    Path(getattr(args_a, stem)).read_bytes(),
                    Path(getattr(args_b, stem)).read_bytes(),
                )
            self.assertFalse(any(root.glob("*.tmp")))

            control, control_meta = frontier.read_pair(
                Path(args_a.out_control_data), Path(args_a.out_control_meta)
            )
            treatment, treatment_meta = frontier.read_pair(
                Path(args_a.out_treatment_data), Path(args_a.out_treatment_meta)
            )
            self.assertEqual(len(control), 30)
            self.assertEqual(len(treatment), 30)
            self.assertEqual(control[6:], treatment[6:])
            self.assertEqual(control_meta[6:], treatment_meta[6:])
            self.assertEqual(control[-6:], treatment[-6:])
            self.assertEqual(control_meta[-6:], treatment_meta[-6:])

            control_train_openings = {
                row.opening_id for row in control_meta[:-6]
            }
            treatment_train_openings = {
                row.opening_id for row in treatment_meta[:-6]
            }
            holdout_openings = {row.opening_id for row in control_meta[-6:]}
            self.assertFalse(control_train_openings & holdout_openings)
            self.assertFalse(treatment_train_openings & holdout_openings)

            self.assertEqual(
                first["single_factor"], "historical_replay_selection_policy"
            )
            self.assertEqual(first["records"]["historical_replay_per_arm"], 6)
            self.assertEqual(first["records"]["fresh_per_arm"], 24)
            self.assertEqual(first["records"]["common_holdout"], 6)
            self.assertTrue(
                first["causal_certificate"]["only_replay_selection_policy_differs"]
            )
            self.assertTrue(
                first["common_holdout"]["bit_identical_between_arms"]
            )
            self.assertFalse(first["promotion_authorized"])
            self.assertIsNone(first["automatic_next_job"])
            self.assertEqual(
                first["treatment"]["hard_manifest_code_sha"],
                self.fixture["code_sha"],
            )
            self.assertEqual(
                first["common_holdout"], second["common_holdout"]
            )

    def test_authenticates_manifest_sha_independently_from_fit_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._prepare(root)
            args = self._args(root, inputs, "-separate-sha")
            args.code_sha = "2" * 40

            result = assembly.assemble(args)

            self.assertEqual(result["code_sha"], "2" * 40)
            self.assertEqual(
                result["treatment"]["hard_manifest_code_sha"],
                self.fixture["code_sha"],
            )

            inputs = self._prepare(root / "wrong-manifest-sha")
            args = self._args(root / "wrong-manifest-sha", inputs, "-bad-sha")
            args.hard_manifest_code_sha = "3" * 40
            with self.assertRaisesRegex(ValueError, "certificate mismatch"):
                assembly.assemble(args)

    def test_fails_closed_on_hard_manifest_drift_and_existing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._prepare(root)
            payload = json.loads(
                inputs["hard_manifest"].read_text(encoding="utf-8")
            )
            payload["selection"]["output_records"] = 4
            inputs["hard_manifest"].write_text(
                json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "certificate mismatch"):
                assembly.assemble(self._args(root, inputs, "-bad"))

            inputs = self._prepare(root / "fresh")
            args = self._args(root / "fresh", inputs, "-existing")
            Path(args.out_control_data).write_bytes(b"occupied")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                assembly.assemble(args)

    def test_fails_closed_on_fresh_count_or_split_leak(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._prepare(root)
            args = self._args(root, inputs, "-count")
            args.fresh_records = 22
            with self.assertRaisesRegex(ValueError, "fresh corpus count"):
                assembly.assemble(args)

            inputs = self._prepare(root / "leak")
            records, rows = frontier.read_pair(
                inputs["fresh_data"], inputs["fresh_meta"]
            )
            rows[-1] = frontier.Meta(
                rows[-1].game_id, rows[0].opening_id, rows[-1].seeded
            )
            frontier.write_pair(
                inputs["fresh_data"], inputs["fresh_meta"], records, rows
            )
            split = json.loads(
                inputs["fresh_split"].read_text(encoding="utf-8")
            )
            split["holdout_openings"] = len(
                {row.opening_id for row in rows[18:]}
            )
            inputs["fresh_split"].write_text(
                json.dumps(split, sort_keys=True) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "leak across train/holdout"):
                assembly.assemble(self._args(root / "leak", inputs, "-leak"))


if __name__ == "__main__":
    unittest.main()
