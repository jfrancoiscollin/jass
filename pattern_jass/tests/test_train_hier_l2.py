"""Unit contracts for the hierarchical penalty used by train_stream."""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

# The objective itself only needs the sparse-design matrix protocol. Keep this
# focused unit test runnable in lightweight environments where SciPy is absent;
# production and end-to-end tests still exercise the real package.
try:
    import scipy.sparse  # noqa: F401
except ModuleNotFoundError:
    scipy = types.ModuleType("scipy")
    sparse = types.ModuleType("scipy.sparse")
    optimize = types.ModuleType("scipy.optimize")
    sparse.csr_matrix = type("csr_matrix", (), {})
    optimize.minimize = lambda *args, **kwargs: None
    scipy.sparse = sparse
    scipy.optimize = optimize
    sys.modules["scipy"] = scipy
    sys.modules["scipy.sparse"] = sparse
    sys.modules["scipy.optimize"] = optimize

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
os.environ.pop("JASS_PATTERNS_DIR", None)

import train  # noqa: E402


class _ZeroDesign:
    def __init__(self, rows, columns):
        self.rows = rows
        self.columns = columns

    def __matmul__(self, weights):
        return np.zeros(self.rows, dtype=np.float64)

    @property
    def T(self):
        return _ZeroTranspose(self.columns)


class _ZeroTranspose:
    def __init__(self, columns):
        self.columns = columns

    def __matmul__(self, residuals):
        return np.zeros(self.columns, dtype=np.float64)


def _capture(probe, *, l2, hier_l2):
    captured = {}

    def fake_minimize(fun, x0, jac, method, options):
        del x0, jac, method, options
        loss, gradient = fun(probe)
        captured["loss"] = loss
        captured["gradient"] = gradient.copy()
        return SimpleNamespace(
            x=probe.copy(), fun=loss, nit=0, success=True, status=0,
            message="captured", nfev=1, jac=gradient.copy(),
        )

    with mock.patch.object(train, "minimize", fake_minimize):
        train.train_lbfgs_chunked(
            lambda selected: _ZeroDesign(len(selected), len(probe)),
            np.asarray([0], dtype=np.int64),
            np.asarray([0.5], dtype=np.float64),
            l2=l2,
            max_iter=1,
            logistic=True,
            n_cols=len(probe),
            batch=1,
            hier_l2=hier_l2,
            slot_pattern=np.asarray([-1, 0, 0, 1, 1], dtype=np.int32),
            pat_n=5,
            n_patterns=2,
        )
    return float(captured["loss"]), np.asarray(captured["gradient"])


class HierL2ObjectiveTest(unittest.TestCase):
    def test_hier_penalty_is_added_and_skips_fallback(self):
        probe = np.asarray(
            [99, 1, 3, 10, 14, 88, 5, 9, 20, 26, 7, -4], dtype=np.float64
        )
        l2 = 0.07
        hier = 0.03
        loss, gradient = _capture(probe, l2=l2, hier_l2=hier)

        # Logistic data term for a zero design and y=.5 is log(2). The hierarchical
        # squared deviations are 2+8 in MG and 8+18 in EG, never slots 0 or extras.
        expected_hier_gradient = hier * np.asarray(
            [0, -1, 1, -2, 2, 0, -2, 2, -3, 3, 0, 0], dtype=np.float64
        )
        expected_loss = (
            np.log(2.0) + 0.5 * l2 * np.dot(probe, probe) + 0.5 * hier * 36
        )
        np.testing.assert_allclose(loss, expected_loss, rtol=0, atol=3e-12)
        np.testing.assert_allclose(gradient, l2 * probe + expected_hier_gradient)

    def test_hier_zero_is_exact_legacy_ridge(self):
        probe = np.linspace(-0.4, 0.7, 12)
        l2 = 3e-5
        loss, gradient = _capture(probe, l2=l2, hier_l2=0.0)
        np.testing.assert_allclose(
            loss, np.log(2.0) + 0.5 * l2 * np.dot(probe, probe)
        )
        np.testing.assert_allclose(gradient, l2 * probe)


if __name__ == "__main__":
    unittest.main()
