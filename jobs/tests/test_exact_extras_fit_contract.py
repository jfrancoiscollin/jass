#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
import unittest
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[2] / "pattern_jass" / "tools"
sys.path.insert(0, str(TOOLS))

from exact_extras import (  # noqa: E402
    exact_extras_residuals,
    exact_image_extras,
    project_exact_extras,
    project_exact_extras_int,
)


class ExactExtrasFitContractTests(unittest.TestCase):
    def test_old_raw_dense_path_can_break_exact_symmetry(self):
        x = np.zeros(120, dtype=np.float64)
        x[0] = 1.0
        tx = exact_image_extras(x)
        unconstrained = np.zeros(120, dtype=np.float64)
        unconstrained[0] = 7.0
        # This is precisely the old failure mode: the raw dense design allowed
        # one orbit member to carry an independent coefficient.
        self.assertNotEqual(float(x @ unconstrained + tx @ unconstrained), 0.0)

    def test_projected_design_is_antisymmetric_for_any_optimizer_vector(self):
        rng = np.random.default_rng(1425)
        x = rng.normal(size=(32, 120))
        tx = exact_image_extras(x)
        arbitrary_optimizer_weights = rng.normal(size=120)
        lhs = project_exact_extras(x) @ arbitrary_optimizer_weights
        rhs = project_exact_extras(tx) @ arbitrary_optimizer_weights
        np.testing.assert_allclose(lhs + rhs, 0.0, rtol=0.0, atol=1e-12)

    def test_projected_parent_is_inside_exact_subspace(self):
        rng = np.random.default_rng(1426)
        parent = rng.normal(size=120)
        projected = project_exact_extras(parent)
        audit = exact_extras_residuals(projected)
        self.assertLessEqual(audit["max_abs"], 1e-15)
        self.assertEqual(audit["nonzero"], 0)

    def test_integer_serialization_guard_is_structurally_exact(self):
        rng = np.random.default_rng(1427)
        raw = rng.integers(-100000, 100001, size=120, dtype=np.int32)
        projected = project_exact_extras_int(raw)
        audit = exact_extras_residuals(projected)
        self.assertEqual(audit["max_abs"], 0.0)
        self.assertEqual(audit["nonzero"], 0)
        for i in range(50):
            self.assertEqual(int(projected[i]), -int(projected[99 - i]))
        self.assertEqual(int(projected[100]), -int(projected[101]))
        self.assertEqual(int(projected[102]), -int(projected[103]))
        self.assertEqual(int(projected[104]), int(projected[105]))
        for i in range(106, 120, 2):
            self.assertEqual(int(projected[i]), -int(projected[i + 1]))

    def test_supported_optional_widths_remain_pair_aligned(self):
        for width in (106, 110, 112, 114, 116, 120):
            x = np.arange(width, dtype=np.float64)
            projected = project_exact_extras(x)
            self.assertEqual(projected.shape, (width,))
            self.assertLessEqual(exact_extras_residuals(projected)["max_abs"], 1e-15)


if __name__ == "__main__":
    unittest.main()
