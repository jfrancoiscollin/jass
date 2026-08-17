# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from jobs.tools.l3_conditional_targets import (
    JNNW_DTYPE,
    JSM2_DTYPE,
    _sha256,
    game_folds,
)
from jobs.tools.l3_context2_recompose_targets import run


class Context2RecomposeTargetsTests(unittest.TestCase):
    def _fixture(self, root: Path) -> argparse.Namespace:
        fold_seed = 20260811
        by_fold: dict[int, int] = {}
        candidate = 1
        while len(by_fold) < 5:
            fold = int(
                game_folds(np.asarray([candidate], dtype=np.uint64), 5, fold_seed)[0]
            )
            by_fold.setdefault(fold, candidate)
            candidate += 1
        train_openings = [by_fold[index] for index in range(5)]
        holdout_openings = [value + 10_000 for value in train_openings]
        while set(
            int(value)
            for value in game_folds(
                np.asarray(holdout_openings, dtype=np.uint64), 5, fold_seed
            )
        ) != set(range(5)):
            holdout_openings = [value + 10_000 for value in holdout_openings]
        openings = np.repeat(
            np.asarray(train_openings + holdout_openings, dtype=np.uint64), 2
        )
        count = len(openings)
        train_count = len(train_openings) * 2

        records = np.zeros(count, dtype=JNNW_DTYPE)
        records["stm"] = 1
        records["wdl"] = 1
        metadata = np.zeros(count, dtype=JSM2_DTYPE)
        metadata["game_id"] = np.arange(1, count + 1, dtype=np.uint64)
        metadata["opening_id"] = openings
        metadata["game_result"] = 1
        data = root / "data.jnnw"
        meta = root / "meta.jsm"
        with data.open("wb") as handle:
            handle.write(b"JNNW" + struct.pack("<I", count))
            handle.write(records.tobytes())
        with meta.open("wb") as handle:
            handle.write(b"JSM2" + struct.pack("<I", count))
            handle.write(metadata.tobytes())

        pure = np.linspace(0.1, 0.9, count, dtype=np.float32)
        pure_path = root / "pure.npy"
        np.save(pure_path, pure, allow_pickle=False)
        pure_report = {
            "schema": "jass.l3_conditional_targets.v2",
            "context_schema": "ctx2-phase-tactical-30",
            "records": count,
            "train_records": train_count,
            "holdout_records": count - train_count,
            "target": {"alpha": 1.0, "output_pov": "black"},
            "source": {
                "data_sha256": _sha256(data),
                "meta_sha256": _sha256(meta),
            },
            "outputs": {"aligned_sha256": _sha256(pure_path)},
            "mapping": {
                "fold_group": "opening_id",
                "fold_local_rms": True,
                "each_game_total_weight_equal": True,
                "all_groups_fold_disjoint": True,
                "train_holdout_group_overlap": 0,
                "folds": [{"fit": {"converged": True}} for _ in range(5)],
                "final_train_fit": {"fit": {"converged": True}},
            },
        }
        pure_report_path = root / "pure.json"
        pure_report_path.write_text(json.dumps(pure_report), encoding="utf-8")

        reference = np.asarray(
            (1.0 - 0.30) + 0.30 * pure.astype(np.float64), dtype=np.float32
        )
        reference_path = root / "reference.npy"
        np.save(reference_path, reference, allow_pickle=False)
        reference_report = {
            "records": count,
            "train_records": train_count,
            "context_schema": "ctx1-legacy-120",
            "target": {"alpha": 0.3},
            "outputs": {"aligned_sha256": _sha256(reference_path)},
        }
        reference_report_path = root / "reference.json"
        reference_report_path.write_text(json.dumps(reference_report), encoding="utf-8")

        return argparse.Namespace(
            data=str(data),
            meta=str(meta),
            pure_context_target=str(pure_path),
            pure_context_report=str(pure_report_path),
            train_count=train_count,
            aligned_out=str(root / "aligned.npy"),
            shuffled_out=str(root / "shuffled.npy"),
            report=str(root / "report.json"),
            reference_target=str(reference_path),
            reference_report=str(reference_report_path),
            alpha=0.30,
            fold_count=5,
            fold_seed=fold_seed,
            shuffle_seed=20260812,
            shuffle_phase_bins=4,
        )

    def test_recomposes_exact_alpha30_and_preserves_stratified_marginals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = self._fixture(Path(tmp))
            report = run(args)
            pure = np.load(args.pure_context_target)
            aligned = np.load(args.aligned_out)
            shuffled = np.load(args.shuffled_out)
            expected = np.asarray(
                (1.0 - 0.30) + 0.30 * pure.astype(np.float64),
                dtype=np.float32,
            )
            np.testing.assert_allclose(aligned, expected, rtol=0.0, atol=1e-7)
            self.assertFalse(np.array_equal(aligned, shuffled))
            self.assertEqual(report["target"]["alpha"], 0.30)
            self.assertEqual(
                report["strict_protocol"]["shuffle_stratification"],
                "terminal_wdl_black_x_tempo_phase_4_bins",
            )
            self.assertTrue(
                report["strict_protocol"]["all_final_target_marginals_preserved"]
            )
            self.assertAlmostEqual(
                report["reference_ctx1_alpha30"]["aligned_std_ratio"],
                1.0,
                delta=1e-6,
            )

    def test_rejects_uncertified_pure_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = self._fixture(Path(tmp))
            report_path = Path(args.pure_context_report)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["target"]["alpha"] = 0.3
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pure CTX2 alpha=1"):
                run(args)

    def test_outputs_are_no_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = self._fixture(Path(tmp))
            Path(args.aligned_out).touch()
            with self.assertRaisesRegex(ValueError, "no-clobber"):
                run(args)


if __name__ == "__main__":
    unittest.main()
