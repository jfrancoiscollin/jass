from __future__ import annotations

import unittest

from jobs.tools import d1_listwise_fit as impl
from jobs.tools import d1_listwise_fit_historical_split as compat


class D1HistoricalSplitTests(unittest.TestCase):
    def test_frozen_current_manifest_cardinality(self) -> None:
        self.assertEqual(compat.HISTORICAL_HOLDOUT, 199_204)
        self.assertEqual(compat.HISTORICAL_TRAIN, 1_800_796)
        self.assertEqual(compat.HISTORICAL_HOLDOUT + compat.HISTORICAL_TRAIN, 2_000_000)

    def test_compat_entrypoint_only_patches_split_cardinality(self) -> None:
        old_holdout, old_train = impl.HOLDOUT, impl.TRAIN
        try:
            compat.apply_historical_split()
            self.assertEqual(impl.HOLDOUT, 199_204)
            self.assertEqual(impl.TRAIN, 1_800_796)
            self.assertEqual(impl.RECORDS, 2_000_000)
            self.assertEqual(impl.LAMBDA, {"WDL_CONTROL": 0.0, "WDL_LISTWISE": 1.0})
            self.assertEqual(impl.L2, 1e-5)
            self.assertEqual(impl.MAX_ITER, 2_000)
            self.assertEqual(impl.MAXCOR, 20)
            self.assertEqual(impl.GTOL, 1e-4)
        finally:
            impl.HOLDOUT, impl.TRAIN = old_holdout, old_train


if __name__ == "__main__":
    unittest.main()
