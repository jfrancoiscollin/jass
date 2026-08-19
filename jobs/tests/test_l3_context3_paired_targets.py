import unittest

import numpy as np

from jobs.tools.l3_context3_paired_targets import compose_targets


class Context3PairedTargetsTests(unittest.TestCase):
    def test_aligned_and_shuffled_are_exactly_marginal_matched(self) -> None:
        count = 80
        predictions = np.linspace(-0.9, 0.9, count)
        outcomes = np.zeros(count)
        folds = np.arange(count, dtype=np.int8) % 5
        strata = np.zeros(count, dtype=np.int16)
        aligned, shuffled, report = compose_targets(
            predictions,
            outcomes,
            folds,
            strata,
            40,
            alpha=0.30,
            shuffle_seed=71,
        )
        self.assertEqual(aligned.dtype, np.float32)
        self.assertEqual(shuffled.dtype, np.float32)
        self.assertFalse(np.array_equal(aligned, shuffled))
        self.assertEqual(report["fixed_point_count"], 0)
        self.assertTrue(report["all_final_target_marginals_preserved"])
        for start, stop in ((0, 40), (40, count)):
            for fold in range(5):
                members = np.flatnonzero(folds[start:stop] == fold) + start
                np.testing.assert_array_equal(
                    np.sort(aligned[members]), np.sort(shuffled[members])
                )

    def test_rejects_invalid_alpha(self) -> None:
        values = np.zeros(20)
        with self.assertRaisesRegex(ValueError, "alpha"):
            compose_targets(
                values,
                values,
                np.arange(20, dtype=np.int8) % 5,
                np.zeros(20, dtype=np.int16),
                10,
                alpha=0.0,
                shuffle_seed=3,
            )


if __name__ == "__main__":
    unittest.main()
