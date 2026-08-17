# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from jobs.tools.l3_conditional_targets import JNNW_DTYPE, JSM2_DTYPE, tempo_phase_from_records
from jobs.tools.l3_context2_activation_census import (
    _iter_game_segments,
    analyze,
    compare,
    sample_complete_games,
)


def write_counted(path: Path, magic: bytes, rows: np.ndarray) -> None:
    with path.open("wb") as handle:
        handle.write(magic + struct.pack("<I", len(rows)))
        handle.write(rows.tobytes())


def write_feat(path: Path, values: np.ndarray) -> None:
    values = np.asarray(values, dtype="<f4")
    with path.open("wb") as handle:
        handle.write(b"FEAT" + struct.pack("<II", *values.shape))
        handle.write(values.tobytes())


class Context2ActivationCensusTests(unittest.TestCase):
    def make_source(self, root: Path) -> tuple[Path, Path, np.ndarray, np.ndarray]:
        records = np.zeros(36, dtype=JNNW_DTYPE)
        metadata = np.zeros(36, dtype=JSM2_DTYPE)
        row = 0
        for opening in range(6):
            for colour in range(2):
                game = opening * 2 + colour
                for ply in range(3):
                    records[row]["wm"] = np.uint64(1 << (10 + (game + ply) % 20))
                    records[row]["bm"] = np.uint64(1 << (30 + (game + ply) % 15))
                    records[row]["stm"] = (game + ply) % 2
                    records[row]["wdl"] = (-1, 0, 1)[game % 3]
                    metadata[row] = (game, 100 + opening, 0, ply, 3, 0xFFFF, 0, 0)
                    row += 1
        data = root / "source.jnnw"
        meta = root / "source.jsm"
        write_counted(data, b"JNNW", records)
        write_counted(meta, b"JSM2", metadata)
        return data, meta, records, metadata

    def test_segmenter_handles_chunk_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, metadata = self.make_source(Path(directory))
            segments = list(_iter_game_segments(metadata, chunk_size=2))
            self.assertEqual(len(segments), 12)
            self.assertEqual(segments[0], (0, 100, 0, 3))
            self.assertEqual(segments[-1], (11, 105, 33, 36))

    def test_sampler_keeps_exact_complete_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, meta, _, _ = self.make_source(root)
            out_data, out_meta = root / "sample.jnnw", root / "sample.jsm"
            manifest = root / "sample.json"
            result = sample_complete_games(
                argparse.Namespace(
                    data=str(data),
                    meta=str(meta),
                    out_data=str(out_data),
                    out_meta=str(out_meta),
                    manifest=str(manifest),
                    games=4,
                    games_per_opening=2,
                    seed=20260817,
                )
            )
            self.assertEqual(result["sample"]["records"], 12)
            self.assertEqual(result["sample"]["games"], 4)
            self.assertEqual(result["sample"]["openings"], 2)
            raw = np.memmap(out_meta, dtype=JSM2_DTYPE, mode="r", offset=8, shape=(12,))
            openings, counts = np.unique(raw["opening_id"], return_counts=True)
            self.assertEqual(len(openings), 2)
            self.assertEqual(counts.tolist(), [6, 6])
            del raw

    def test_analyser_separates_base_and_phase_banks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, meta, records, _ = self.make_source(root)
            wmg = tempo_phase_from_records(records).astype(np.float32)
            base = np.empty((len(records), 15), dtype=np.float32)
            for component in range(15):
                base[:, component] = (component + 1) * np.where(
                    np.arange(len(records)) % 5 == 0, 0.0, 1.0
                )
            feat_values = np.concatenate(
                (wmg[:, None] * base, (1.0 - wmg[:, None]) * base), axis=1
            )
            feat = root / "ctx2.feat"
            write_feat(feat, feat_values)
            report, csv_path, markdown = root / "report.json", root / "report.csv", root / "report.md"
            result = analyze(
                argparse.Namespace(
                    data=str(data),
                    meta=str(meta),
                    feat=str(feat),
                    report=str(report),
                    csv=str(csv_path),
                    markdown=str(markdown),
                    expected_games=12,
                    expected_openings=6,
                    material_threshold=1e-6,
                    rare_threshold=1e-3,
                    rank_rows=36,
                )
            )
            self.assertTrue(result["diagnostics"]["all_15_base_signals_materially_active"])
            self.assertEqual(len(result["raw_30_channels"]), 30)
            self.assertEqual(len(result["base_15_signals"]), 15)
            self.assertLess(result["phase"]["recomposition_max_absolute_error"], 1e-5)
            self.assertEqual(json.loads(report.read_text())["population"]["games"], 12)
            self.assertIn("king_denied_delta", markdown.read_text())

    def test_compare_uses_baseline_replicate_as_component_noise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # The production component names are required by compare.
            from jobs.tools.l3_conditional_targets import CTX2_BASE_COMPONENTS
            paths = {}
            for name, shift in (("BASE", 0.0), ("BASEBIS", 0.01), ("EPS16", 0.03)):
                paths[name] = root / f"{name}.json"
                paths[name].write_text(
                    json.dumps({"base_15_signals": {
                        component: {
                            "active_position_rate_material": 0.10 + shift,
                            "mean_absolute": 0.20 + shift,
                            "rms": 0.30 + shift,
                        }
                        for component in CTX2_BASE_COMPONENTS
                    }}), encoding="utf-8"
                )
            output = root / "effects.json"
            result = compare(argparse.Namespace(
                cell=[f"{name}={path}" for name, path in paths.items()],
                baseline="BASE", replicate="BASEBIS", report=str(output),
            ))
            first = result["effects"][0]
            self.assertAlmostEqual(first["activation_delta_percentage_points"], 3.0)
            self.assertAlmostEqual(first["baseline_replicate_noise_percentage_points"], 1.0)
            self.assertAlmostEqual(first["absolute_effect_over_seed_noise"], 3.0)


if __name__ == "__main__":
    unittest.main()
