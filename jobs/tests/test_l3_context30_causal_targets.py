"""Unit contracts for the stronger WDL-stratified causal shuffle."""
from importlib import util
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SPEC = util.spec_from_file_location(
    "l3_conditional_targets", ROOT / "jobs" / "tools" / "l3_conditional_targets.py"
)
assert SPEC is not None and SPEC.loader is not None
TARGETS = util.module_from_spec(SPEC)
SPEC.loader.exec_module(TARGETS)


class Context30CausalTargetsTest(unittest.TestCase):
    def test_wdl_stratification_preserves_complete_target_multisets(self) -> None:
        # Two cohorts × two folds × three WDL strata × three rows leaves every
        # causal cell large enough for a fixed-point-free rotation.
        cells = []
        for cohort in range(2):
            for fold in range(2):
                for outcome in (-1.0, 0.0, 1.0):
                    for replica in range(3):
                        cells.append((cohort, fold, outcome, replica))
        folds = np.asarray([row[1] for row in cells], dtype=np.int8)
        outcomes = np.asarray([row[2] for row in cells], dtype=np.float64)
        predictions = np.linspace(-0.95, 0.95, len(cells), dtype=np.float64)
        train_count = len(cells) // 2
        shuffled, report = TARGETS.shuffled_within_cohort_folds(
            predictions, folds, train_count, 20260812, outcomes
        )
        self.assertEqual(report["fixed_point_count"], 0)
        self.assertEqual(report["stratification"], "terminal_wdl_black")
        self.assertTrue(report["all_sources_within_same_stratum"])
        aligned = (0.70 * outcomes + 0.30 * predictions + 1.0) / 2.0
        control = (0.70 * outcomes + 0.30 * shuffled + 1.0) / 2.0
        for start, stop in ((0, train_count), (train_count, len(cells))):
            for fold in (0, 1):
                for outcome in (-1.0, 0.0, 1.0):
                    mask = np.zeros(len(cells), dtype=bool)
                    mask[start:stop] = True
                    mask &= folds == fold
                    mask &= outcomes == outcome
                    np.testing.assert_array_equal(
                        np.sort(aligned[mask]), np.sort(control[mask])
                    )
