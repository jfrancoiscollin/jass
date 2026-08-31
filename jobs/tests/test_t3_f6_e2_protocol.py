from __future__ import annotations

import hashlib
import math
import unittest

import numpy as np

from jobs.tools import t3_f6_e2_pool_select as pool
from jobs.tools import t3_f6_e2_readout as readout


class E2ProtocolTests(unittest.TestCase):
    def test_frozen_geometry_and_seeds(self) -> None:
        self.assertEqual(pool.GENERATION_SEED, 2026100101)
        self.assertEqual(pool.SELECTION_SEED, 2026100102)
        self.assertEqual(pool.EXECUTION_SEED, 2026100104)
        self.assertEqual(pool.CANDIDATES, 30000)
        self.assertEqual(pool.CELL_SIZES, {"C1": 750, "C2": 400, "C3": 200})
        self.assertEqual(readout.BOOTSTRAP_REPS, 200000)
        self.assertEqual(readout.BOOTSTRAP_SEED, 2026100103)
        self.assertEqual(readout.EXPECTED_GAMES, {"C1": 1500, "C2": 800, "C3": 400})

    def test_selection_hash_is_exact_preregistered_string(self) -> None:
        identity = "fixture-canonical-identity"
        expected = hashlib.sha256(b"2026100102:fixture-canonical-identity").digest()
        self.assertEqual(pool.digest(pool.SELECTION_SEED, identity), expected)
        execution = hashlib.sha256(b"2026100104:fixture-canonical-identity").digest()
        self.assertEqual(pool.digest(pool.EXECUTION_SEED, identity), execution)

    def test_elo_definition(self) -> None:
        self.assertEqual(readout.elo_scalar(0.5), 0.0)
        p = 0.6
        self.assertAlmostEqual(readout.elo_scalar(p), 400.0 * math.log10(p / (1.0 - p)))
        with self.assertRaises(ValueError):
            readout.elo_scalar(0.0)
        with self.assertRaises(ValueError):
            readout.elo_scalar(1.0)

    def test_bootstrap_substream_derivation_is_stable(self) -> None:
        ss1 = np.random.SeedSequence(readout.BOOTSTRAP_SEED)
        a1, b1, c1 = [np.random.default_rng(x) for x in ss1.spawn(3)]
        ss2 = np.random.SeedSequence(readout.BOOTSTRAP_SEED)
        a2, b2, c2 = [np.random.default_rng(x) for x in ss2.spawn(3)]
        self.assertTrue(np.array_equal(a1.integers(0, 100, 32), a2.integers(0, 100, 32)))
        self.assertTrue(np.array_equal(b1.integers(0, 100, 32), b2.integers(0, 100, 32)))
        self.assertTrue(np.array_equal(c1.integers(0, 100, 32), c2.integers(0, 100, 32)))


if __name__ == "__main__":
    unittest.main()
