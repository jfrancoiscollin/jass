#!/usr/bin/env python3
import argparse
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools import l3_context3_independent_information_screen as ctx3
from jobs.tools.l3_conditional_targets import JSM2_DTYPE


class Context3IndependentInformationTests(unittest.TestCase):
    def test_feature_bank_is_antisymmetric(self):
        rng = np.random.default_rng(7)
        raw = rng.normal(size=(20, 30))
        tempo = rng.uniform(size=20)
        np.testing.assert_allclose(
            ctx3.feature_bank(-raw, tempo),
            -ctx3.feature_bank(raw, tempo),
            atol=1e-12,
        )
        self.assertEqual(ctx3.feature_bank(raw, tempo).shape, (20, 80))
        self.assertEqual(len(ctx3.component_names()), 80)

    def test_covariance_novelty_finds_nonlinear_direction(self):
        rng = np.random.default_rng(11)
        raw = rng.normal(size=(2000, 30))
        tempo = rng.uniform(size=2000)
        bank = ctx3.feature_bank(raw, tempo)
        stats = ctx3.empty_stats(ctx3.FULL_WIDTH)
        ctx3.add_stats(stats, bank, rng.normal(size=len(bank)), np.ones(len(bank)))
        novelty = ctx3.covariance_novelty(stats, ctx3.CANDIDATE_COLUMNS["odd_curvature"])
        self.assertGreater(novelty["residual_effective_dimension"], 2.0)
        self.assertGreater(novelty["median_residual_variance_fraction"], 0.01)

    def test_shuffle_preserves_cohort_fold_and_stratum(self):
        folds = np.repeat(np.arange(6), 40).astype(np.int8)
        train_count = 200
        folds[train_count:] = 5
        strata = np.tile(np.repeat(np.arange(4), 10), 6).astype(np.int16)
        sources, report = ctx3.shuffled_sources(folds, strata, train_count, 19)
        np.testing.assert_array_equal(folds[sources], folds)
        np.testing.assert_array_equal(strata[sources], strata)
        self.assertEqual(report["fixed_point_count"], 0)
        self.assertFalse(np.any(sources == np.arange(len(sources))))

    def test_cluster_interval_is_deterministic(self):
        values = np.linspace(-0.1, 0.2, 300)
        weights = np.ones(300)
        openings = np.repeat(np.arange(100), 3)
        first = ctx3.cluster_interval(values, weights, openings, replicates=128, seed=23)
        second = ctx3.cluster_interval(values, weights, openings, replicates=128, seed=23)
        self.assertEqual(first, second)
        self.assertGreater(first["estimate"], 0.0)

    def test_end_to_end_small_screen(self):
        rng = np.random.default_rng(29)
        count, train_count = 1200, 900
        records = np.zeros(count, dtype=ctx3.JNNW_DTYPE)
        metadata = np.zeros(count, dtype=JSM2_DTYPE)
        x = rng.uniform(-2.0, 2.0, size=count)
        outcomes = np.where(np.abs(x) > 1.0, np.sign(x), 0).astype(np.int8)
        for index in range(count):
            records[index]["wm"] = 1 << (index % 20)
            records[index]["wk"] = 1 << (30 + index % 10)
            records[index]["bm"] = 1 << (20 + index % 20)
            records[index]["bk"] = 1 << (40 + index % 10)
            records[index]["stm"] = 1
            records[index]["wdl"] = outcomes[index]
            metadata[index]["game_id"] = 10000 + index
            metadata[index]["opening_id"] = 20000 + index
            metadata[index]["ply"] = index % 40
            metadata[index]["game_plies"] = 40
            metadata[index]["game_result"] = outcomes[index]
        features = np.zeros((count, 30), dtype="<f4")
        features[:, 0] = x.astype(np.float32)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            data = root / "source.jnnw"
            meta = root / "source.jsm"
            feat = root / "source.feat"
            report = root / "screen.json"
            data.write_bytes(struct.pack("<4sI", b"JNNW", count) + records.tobytes())
            meta.write_bytes(struct.pack("<4sI", b"JSM2", count) + metadata.tobytes())
            feat.write_bytes(struct.pack("<4sII", b"FEAT", count, 30) + features.tobytes())
            payload = ctx3.run(argparse.Namespace(
                data=str(data), meta=str(meta), features=str(feat), report=str(report),
                train_count=train_count, fold_seed=31, shuffle_seed=37,
                bootstrap_seed=41, bootstrap_replicates=64, ridge=1e-4,
                chunk_size=200,
            ))
            self.assertEqual(payload["schema"], "jass.l3_context3_independent_information_screen.v1")
            self.assertIn(payload["selected_candidate"], ctx3.CANDIDATE_COLUMNS)
            self.assertEqual(payload["source"]["train_holdout_opening_overlap"], 0)
            self.assertTrue(report.exists())
            self.assertEqual(json.loads(report.read_text())["verdict"], payload["verdict"])


if __name__ == "__main__":
    unittest.main()
