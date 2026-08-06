from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "l3_trajectory_equal_weights.py"
)
SPEC = importlib.util.spec_from_file_location("l3_trajectory_equal_weights", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
trajectory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trajectory)


def _write_jnnw(path: Path, wdls: list[int]) -> None:
    records = b"".join(
        struct.pack("<QQQQBib", 0, 0, 0, 0, 0, 0, wdl) for wdl in wdls
    )
    path.write_bytes(b"JNNW" + struct.pack("<I", len(wdls)) + records)


def _write_jsm2(path: Path, rows: list[tuple[int, int, int, int, int, int, int, int]]) -> None:
    body = b"".join(struct.pack("<QQBHHHbB", *row) for row in rows)
    path.write_bytes(b"JSM2" + struct.pack("<I", len(rows)) + body)


def _write_jsm1(path: Path, rows: list[tuple[int, int, int]]) -> None:
    body = b"".join(struct.pack("<QQB", *row) for row in rows)
    path.write_bytes(b"JSM1" + struct.pack("<I", len(rows)) + body)


class TrajectoryEqualWeightsTests(unittest.TestCase):
    def test_equalises_train_game_mass_and_keeps_holdout_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "corpus.jnnw"
            meta = root / "corpus.jsm"
            row_weights_path = root / "row-weights.npy"
            weights_path = root / "game-weights.npy"
            report_path = root / "report.json"
            _write_jnnw(data, [1, 1, 1, 0, -1, -1])
            _write_jsm2(
                meta,
                [
                    # TRAIN: game 10 has three retained rows, game 11 has one.
                    (10, 100, 0, 0, 80, 0xFFFF, 1, 0),
                    (10, 100, 0, 4, 80, 0xFFFF, 1, 0),
                    (10, 100, 0, 8, 80, 0xFFFF, 1, 0),
                    (11, 101, 0, 3, 60, 0xFFFF, 0, 0),
                    # HOLDOUT: a distinct opening and game.
                    (20, 200, 0, 1, 70, 0xFFFF, -1, 0),
                    (20, 200, 0, 5, 70, 0xFFFF, -1, 0),
                ],
            )

            self.assertEqual(
                trajectory.main(
                    [
                        "--data", str(data),
                        "--meta", str(meta),
                        "--holdout-count", "2",
                        "--out-row-weights", str(row_weights_path),
                        "--out-game-weights", str(weights_path),
                        "--out-report", str(report_path),
                    ]
                ),
                0,
            )

            weights = np.load(weights_path, allow_pickle=False)
            row_weights = np.load(row_weights_path, allow_pickle=False)
            self.assertEqual(weights.dtype, np.dtype(np.float32))
            np.testing.assert_array_equal(row_weights, np.ones(6, dtype=np.float32))
            np.testing.assert_allclose(weights, [1 / 3, 1 / 3, 1 / 3, 1, 1, 1])
            normalized = weights[:4].astype(np.float64) / float(weights[:4].mean())
            self.assertAlmostEqual(float(normalized[:3].sum()), 2.0, delta=1e-6)
            self.assertAlmostEqual(float(normalized[3]), 2.0, delta=1e-6)

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(
                report["split"],
                {
                    "records": 6,
                    "train_records": 4,
                    "holdout_records": 2,
                    "train_games": 2,
                    "holdout_games": 1,
                    "train_openings": 2,
                    "holdout_openings": 1,
                    "games_crossing_boundary": 0,
                    "openings_crossing_boundary": 0,
                },
            )
            self.assertEqual(
                report["row_equal_control"]["record_mass_result_distribution"]
                ["white_win"]["count"],
                3,
            )
            self.assertEqual(
                report["row_equal_control"]["game_result_distribution"]
                ["white_win"]["count"],
                1,
            )
            self.assertEqual(
                report["trajectory_equal_treatment"]["equal_total_mass_per_game"],
                2.0,
            )
            self.assertEqual(report["output"]["row_weights"]["dtype"], "float32")
            self.assertEqual(report["output"]["game_weights"]["dtype"], "float32")

    def test_rejects_game_crossing_train_holdout_boundary_without_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "corpus.jnnw"
            meta = root / "corpus.jsm"
            row_weights_path = root / "row-weights.npy"
            weights_path = root / "game-weights.npy"
            report_path = root / "report.json"
            _write_jnnw(data, [1, 0, -1, 1])
            _write_jsm2(
                meta,
                [
                    (10, 100, 0, 0, 80, 0xFFFF, 1, 0),
                    (11, 101, 0, 0, 80, 0xFFFF, 0, 0),
                    (12, 102, 0, 0, 80, 0xFFFF, -1, 0),
                    (10, 100, 0, 4, 80, 0xFFFF, 1, 0),
                ],
            )

            with self.assertRaisesRegex(SystemExit, "game_id values cross"):
                trajectory.main(
                    [
                        "--data", str(data), "--meta", str(meta),
                        "--holdout-count", "1",
                        "--out-row-weights", str(row_weights_path),
                        "--out-game-weights", str(weights_path),
                        "--out-report", str(report_path),
                    ]
                )
            self.assertFalse(weights_path.exists())
            self.assertFalse(row_weights_path.exists())
            self.assertFalse(report_path.exists())

    def test_rejects_jsm1_without_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "corpus.jnnw"
            meta = root / "corpus.jsm"
            row_weights_path = root / "row-weights.npy"
            weights_path = root / "game-weights.npy"
            report_path = root / "report.json"
            _write_jnnw(data, [0, 0])
            _write_jsm1(meta, [(1, 1, 0), (2, 2, 0)])

            with self.assertRaisesRegex(SystemExit, "requires JSM2"):
                trajectory.main(
                    [
                        "--data", str(data), "--meta", str(meta),
                        "--holdout-count", "0",
                        "--out-row-weights", str(row_weights_path),
                        "--out-game-weights", str(weights_path),
                        "--out-report", str(report_path),
                    ]
                )
            self.assertFalse(weights_path.exists())
            self.assertFalse(row_weights_path.exists())
            self.assertFalse(report_path.exists())

    def test_rejects_jnnw_jsm2_pov_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "corpus.jnnw"
            meta = root / "corpus.jsm"
            row_weights_path = root / "row-weights.npy"
            weights_path = root / "game-weights.npy"
            report_path = root / "report.json"
            _write_jnnw(data, [-1])
            _write_jsm2(meta, [(1, 1, 0, 0, 20, 0xFFFF, 1, 0)])

            with self.assertRaisesRegex(SystemExit, "POV mismatch"):
                trajectory.main(
                    [
                        "--data", str(data), "--meta", str(meta),
                        "--holdout-count", "0",
                        "--out-row-weights", str(row_weights_path),
                        "--out-game-weights", str(weights_path),
                        "--out-report", str(report_path),
                    ]
                )
            self.assertFalse(weights_path.exists())
            self.assertFalse(row_weights_path.exists())
            self.assertFalse(report_path.exists())

    def test_no_clobber_keeps_existing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "corpus.jnnw"
            meta = root / "corpus.jsm"
            row_weights_path = root / "row-weights.npy"
            weights_path = root / "game-weights.npy"
            report_path = root / "report.json"
            _write_jnnw(data, [1, -1])
            _write_jsm2(
                meta,
                [
                    (1, 1, 0, 0, 20, 0xFFFF, 1, 0),
                    (2, 2, 0, 0, 20, 0xFFFF, -1, 0),
                ],
            )
            weights_path.write_bytes(b"owned")

            with self.assertRaisesRegex(SystemExit, "refusing to overwrite"):
                trajectory.main(
                    [
                        "--data", str(data), "--meta", str(meta),
                        "--holdout-count", "0",
                        "--out-row-weights", str(row_weights_path),
                        "--out-game-weights", str(weights_path),
                        "--out-report", str(report_path),
                    ]
                )
            self.assertEqual(weights_path.read_bytes(), b"owned")
            self.assertFalse(row_weights_path.exists())
            self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
