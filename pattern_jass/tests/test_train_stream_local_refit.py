#!/usr/bin/env python3
from __future__ import annotations

import sys
import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import numpy as np

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
SCIPY_AVAILABLE = importlib.util.find_spec("scipy") is not None
if SCIPY_AVAILABLE:
    import scipy.sparse as sp
    from train import train_lbfgs_chunked  # noqa: E402
    import train_stream  # noqa: E402
else:  # pragma: no cover - scientific CI installs SciPy
    sp = None
    train_lbfgs_chunked = None
    train_stream = None


@unittest.skipUnless(SCIPY_AVAILABLE, "SciPy is required by the production trainer")
class StrictLocalRefitTests(unittest.TestCase):
    def test_frozen_coordinates_remain_exact(self) -> None:
        matrix = sp.csr_matrix(
            np.asarray(
                [
                    [1.0, 2.0, 0.0],
                    [1.0, 0.0, 3.0],
                    [1.0, 1.0, 1.0],
                    [1.0, -1.0, 2.0],
                ]
            )
        )
        y = np.asarray([1.0, 0.0, 1.0, 0.0])
        initial = np.asarray([0.25, -0.5, 0.75])
        mask = np.asarray([False, True, False], dtype=bool)

        def build(selected):
            return matrix[selected]

        diagnostics = {}
        fitted, _loss, _iterations = train_lbfgs_chunked(
            build,
            np.arange(len(y)),
            y,
            1e-4,
            25,
            True,
            3,
            4,
            initial_mean=initial,
            trainable_mask=mask,
            optimizer_diagnostics=diagnostics,
        )
        self.assertEqual(fitted[0], initial[0])
        self.assertEqual(fitted[2], initial[2])
        self.assertNotEqual(fitted[1], initial[1])
        self.assertTrue(diagnostics["local_refit"])
        self.assertEqual(diagnostics["trainable_coordinates"], 1)
        self.assertEqual(diagnostics["frozen_coordinates"], 2)

    def test_mask_requires_an_explicit_frozen_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "frozen model"):
            train_lbfgs_chunked(
                lambda selected: sp.eye(len(selected), 2, format="csr"),
                np.arange(2),
                np.asarray([0.0, 1.0]),
                1e-4,
                1,
                True,
                2,
                2,
                trainable_mask=np.asarray([True, False]),
            )

    def test_region_maps_only_confirmed_exact_fold_buckets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            champion = root / "champion.pjtw"
            champion.write_bytes(b"authenticated champion")
            champion_hash = hashlib.sha256(champion.read_bytes()).hexdigest()
            region = root / "region.json"
            region.write_text(
                json.dumps(
                    {
                        "schema": train_stream.ERROR_REGION_SCHEMA,
                        "fold": "exact_rot180_colour_swap",
                        "fit_authorized": True,
                        "promotion_authorized": False,
                        "champion_sha256": champion_hash,
                        "pattern_columns_full": [2, 6],
                        "extras": [],
                        "confirmation": [
                            {"full_pattern_column": 2},
                            {"full_pattern_column": 6},
                        ],
                        "strict_fit_contract": {
                            "train_dense_extras": False,
                            "freeze_everything_else_at_champion": True,
                        },
                    }
                )
            )
            args = SimpleNamespace(
                trainable_region=str(region),
                trainable_region_report=str(root / "report.json"),
                prior_mean=str(champion),
                prune_min_visits=1,
                data=str(root / "data.jnnw"),
                feat=str(root / "features.bin"),
                out=str(root / "candidate.pjtw"),
            )
            folder = SimpleNamespace(
                mode="exact",
                rf_canon=np.arange(12, dtype=np.int64).reshape(3, 4),
            )
            remap = np.zeros(12, dtype=np.int64)
            remap[2] = 1
            remap[6] = 2
            with (
                mock.patch.object(train_stream.patterns, "TOTAL_BUCKETS", 12),
                mock.patch.object(train_stream.patterns, "BUCKETS_PER_PATTERN", 4),
            ):
                mask, prepared = train_stream._prepare_trainable_region(
                    args, folder, remap, pat_n=3, extras_n=2
                )
            self.assertEqual(np.flatnonzero(mask).tolist(), [1, 2, 4, 5])
            self.assertEqual(prepared["trainable_coordinates"], 4)
            self.assertEqual(prepared["frozen_coordinates"], 6)


if __name__ == "__main__":
    unittest.main()
