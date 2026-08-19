import tempfile
import unittest
from pathlib import Path
import gc

import numpy as np

from jobs.tools.l3_context3_exact_tanh_mapper_screen import _write_matrix, evaluate
from jobs.tools.l3_context3_independent_information_screen import (
    BASE_WIDTH,
    CANDIDATE_COLUMNS,
    feature_bank,
)


class Context3ExactTanhMapperScreenTests(unittest.TestCase):
    def test_evaluate_requires_both_baseline_and_shuffle_causal_gains(self) -> None:
        outcomes = np.tile(np.asarray([-1.0, 1.0]), 50)
        baseline = np.zeros_like(outcomes)
        aligned = 0.9 * outcomes
        shuffled = 0.2 * outcomes
        weights = np.ones_like(outcomes)
        openings = np.arange(len(outcomes), dtype=np.uint64)
        folds = np.arange(len(outcomes), dtype=np.int8) % 5
        contrasts, guards = evaluate(
            baseline=baseline,
            aligned=aligned,
            shuffled=shuffled,
            outcomes=outcomes,
            weights=weights,
            openings=openings,
            folds=folds,
            train_count=80,
            bootstrap_replicates=200,
            bootstrap_seed=17,
        )
        self.assertTrue(all(guards.values()))
        self.assertGreater(contrasts["aligned_vs_ctx2_holdout"]["ci95"][0], 0.0)
        self.assertGreater(contrasts["aligned_vs_shuffled_holdout"]["ci95"][0], 0.0)

        _, bad = evaluate(
            baseline=baseline,
            aligned=aligned,
            shuffled=outcomes,
            outcomes=outcomes,
            weights=weights,
            openings=openings,
            folds=folds,
            train_count=80,
            bootstrap_replicates=200,
            bootstrap_seed=17,
        )
        self.assertFalse(bad["aligned_beats_shuffled_oof_ci95"])
        self.assertFalse(bad["aligned_beats_shuffled_holdout_ci95"])

    def test_feature_shuffle_preserves_ctx2_and_moves_only_augmentation(self) -> None:
        rng = np.random.default_rng(4)
        raw = rng.normal(size=(12, BASE_WIDTH)).astype(np.float32)
        tempo = np.linspace(0.05, 0.95, len(raw), dtype=np.float32)
        donors = np.arange(len(raw) - 1, -1, -1, dtype=np.int64)
        columns = CANDIDATE_COLUMNS["combined"]
        with tempfile.TemporaryDirectory() as directory:
            matrix = _write_matrix(
                Path(directory) / "shuffled.npy",
                raw,
                tempo,
                columns,
                chunk_size=5,
                donors=donors,
            )
            expected = feature_bank(raw, tempo)
            donor = feature_bank(raw[donors], tempo[donors])
            np.testing.assert_allclose(matrix[:, :BASE_WIDTH], expected[:, :BASE_WIDTH])
            np.testing.assert_allclose(matrix[:, BASE_WIDTH:], donor[:, BASE_WIDTH:])
            del matrix
            gc.collect()


if __name__ == "__main__":
    unittest.main()
