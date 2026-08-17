# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from jobs.tools.l3_conditional_targets import (
    CTX2_CONTEXT_COMPONENTS,
    JNNW_DTYPE,
    JSM2_DTYPE,
    _sha256,
    game_folds,
)
from jobs.tools.l3_context2_fixed_contribution_audit import audit


def write_counted(path: Path, magic: bytes, rows: np.ndarray) -> None:
    with path.open("wb") as handle:
        handle.write(magic + struct.pack("<I", len(rows)))
        handle.write(rows.tobytes())


def write_feat(path: Path, values: np.ndarray) -> None:
    values = np.asarray(values, dtype="<f4")
    with path.open("wb") as handle:
        handle.write(b"FEAT" + struct.pack("<II", *values.shape))
        handle.write(values.tobytes())


class Context2FixedContributionAuditTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[dict[str, Path], dict]:
        count = 24
        train_count = 16
        fold_count = 2
        fold_seed = 20260811
        records = np.zeros(count, dtype=JNNW_DTYPE)
        records["stm"] = np.arange(count) % 2
        records["wdl"] = np.asarray(([-1, 0, 1] * 8), dtype=np.int8)
        metadata = np.zeros(count, dtype=JSM2_DTYPE)
        metadata["game_id"] = np.arange(1, count + 1, dtype=np.uint64)
        metadata["opening_id"] = np.arange(101, 101 + count, dtype=np.uint64)
        metadata["game_result"] = records["wdl"]
        data = root / "data.jnnw"
        meta = root / "meta.jsm"
        write_counted(data, b"JNNW", records)
        write_counted(meta, b"JSM2", metadata)

        rng = np.random.default_rng(1234)
        features = rng.normal(0.0, 0.12, size=(count, 30)).astype(np.float32)
        features[:, 0] += np.linspace(-0.4, 0.4, count, dtype=np.float32)
        feat = root / "ctx2.feat"
        write_feat(feat, features)

        theta0 = np.linspace(0.9, 0.02, 30)
        theta1 = theta0.copy()
        theta1[1] *= -1.0
        theta_final = 0.5 * (theta0 + theta1)
        folds = game_folds(metadata["opening_id"], fold_count, fold_seed)
        model_ids = np.asarray(folds, dtype=np.int64)
        model_ids[train_count:] = fold_count
        table = np.asarray([theta0, theta1, theta_final])
        prediction = np.tanh(np.sum(features * table[model_ids], axis=1))
        outcomes = np.where(records["stm"] == 1, records["wdl"], -records["wdl"])
        alpha = 0.30
        aligned = np.asarray(
            ((1.0 - alpha) * outcomes + alpha * prediction + 1.0) * 0.5,
            dtype=np.float32,
        )
        aligned_path = root / "aligned.npy"
        np.save(aligned_path, aligned, allow_pickle=False)

        report = {
            "schema": "jass.l3_conditional_targets.v2",
            "context_schema": "ctx2-phase-tactical-30",
            "records": count,
            "train_records": train_count,
            "holdout_records": count - train_count,
            "target": {"alpha": alpha, "output_pov": "black"},
            "source": {
                "data_sha256": _sha256(data),
                "meta_sha256": _sha256(meta),
                "feat_sha256": _sha256(feat),
            },
            "outputs": {"aligned_sha256": _sha256(aligned_path)},
            "mapping": {
                "components": list(CTX2_CONTEXT_COMPONENTS),
                "fold_group": "opening_id",
                "row_weighting": "game_equal",
                "fold_local_rms": True,
                "each_game_total_weight_equal": True,
                "fold_count": fold_count,
                "fold_seed": fold_seed,
                "folds": [
                    {"fold": 0, "theta_raw": theta0.tolist()},
                    {"fold": 1, "theta_raw": theta1.tolist()},
                ],
                "final_train_fit": {"theta_raw": theta_final.tolist()},
            },
        }
        report_path = root / "conditional.json"
        report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
        return {
            "data_path": data,
            "meta_path": meta,
            "feat_path": feat,
            "aligned_target_path": aligned_path,
            "conditional_report_path": report_path,
        }, report

    def test_replays_fold_local_contributions_and_recovers_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths, _ = self.fixture(Path(directory))
            result = audit(**paths, chunk_size=5)
        self.assertEqual(result["verdict"], "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY")
        self.assertLess(result["prediction_recovery_max_absolute_error"], 2e-6)
        self.assertEqual(result["cohorts"]["train_oof"]["rows"], 16)
        self.assertEqual(result["cohorts"]["holdout_final_mapper"]["rows"], 8)
        self.assertEqual(len(result["cohorts"]["all"]["raw_30_components"]), 30)
        self.assertEqual(len(result["cohorts"]["all"]["base_15_components"]), 15)
        self.assertIn(
            "tempo_mid_has_king_delta",
            result["train_oof_rankings"]["raw_coefficient_sign_flip_components"],
        )
        shares = result["cohorts"]["train_oof"]["phase_bank_absolute_logit_share"]
        self.assertAlmostEqual(shares["tempo_mid"] + shares["tempo_end"], 1.0, places=12)
        self.assertEqual(
            result["cohorts"]["train_oof"]["base_15_components"][0]["component"],
            "men_delta",
        )

    def test_rejects_feature_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths, _ = self.fixture(Path(directory))
            with paths["feat_path"].open("ab") as handle:
                handle.write(b"x")
            with self.assertRaisesRegex(ValueError, "FEAT size"):
                audit(**paths, chunk_size=7)


if __name__ == "__main__":
    unittest.main()
