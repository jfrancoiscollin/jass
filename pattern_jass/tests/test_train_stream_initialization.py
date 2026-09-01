#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
SCIPY_AVAILABLE = importlib.util.find_spec("scipy") is not None
if SCIPY_AVAILABLE:
    import scipy.sparse as sp
    import train
    from train import train_lbfgs_chunked
    import train_stream
else:  # pragma: no cover
    sp = None
    train_lbfgs_chunked = None
    train_stream = None


@unittest.skipUnless(SCIPY_AVAILABLE, "SciPy is required by the production trainer")
class IndependentInitializationTests(unittest.TestCase):
    def test_prior_centre_accepts_independent_zero_and_file_initialization(self) -> None:
        matrix = sp.csr_matrix(
            np.asarray([[1.0, 0.0], [1.0, 1.0], [1.0, -1.0], [1.0, 2.0]])
        )
        target = np.asarray([0.0, 1.0, 0.0, 1.0])
        prior = np.asarray([0.4, -0.3])
        precision = np.asarray([1e-3, 1e-3])

        def build(selected):
            return matrix[selected]

        results = []
        for initial in (np.zeros(2), np.asarray([-1.5, 1.25])):
            fitted, objective, _ = train_lbfgs_chunked(
                build,
                np.arange(len(target)),
                target,
                1e-3,
                200,
                True,
                2,
                4,
                prior_mean=prior,
                prior_prec=precision,
                initial_mean=initial,
                gtol=1e-10,
            )
            results.append((fitted, objective))

        # L-BFGS may stop at slightly different points inside the same requested
        # gradient tolerance; the objective and solution must nevertheless agree
        # at a scale far below the preregistered serialized-score thresholds.
        np.testing.assert_allclose(results[0][0], results[1][0], atol=1e-5, rtol=0)
        self.assertLess(abs(results[0][1] - results[1][1]), 1e-10)

    def test_legacy_prior_still_initializes_at_prior(self) -> None:
        matrix = sp.csr_matrix(np.asarray([[1.0], [1.0]]))
        prior = np.asarray([0.75])
        captured = {}

        def fake_minimize(fun, x0, **kwargs):
            captured["x0"] = x0.copy()
            _loss, gradient = fun(x0)
            return SimpleNamespace(
                x=x0.copy(), fun=0.0, nit=0, success=True, status=0,
                message="captured", nfev=1, jac=gradient,
            )

        with mock.patch.object(train, "minimize", side_effect=fake_minimize):
            fitted, _objective, iterations = train_lbfgs_chunked(
                lambda selected: matrix[selected],
                np.arange(2),
                np.asarray([0.0, 1.0]),
                1e-4,
                1,
                True,
                1,
                2,
                prior_mean=prior,
                prior_prec=np.asarray([1e-4]),
            )
        self.assertEqual(iterations, 0)
        np.testing.assert_array_equal(captured["x0"], prior)
        np.testing.assert_array_equal(fitted, prior)

    def test_initialization_cli_contract(self) -> None:
        base = SimpleNamespace(
            init_mode="legacy", init_file=None, warm_start=None, trainable_region=None
        )
        train_stream.validate_initialization_args(base)
        train_stream.validate_initialization_args(
            SimpleNamespace(
                init_mode="zero", init_file=None, warm_start=None, trainable_region=None
            )
        )
        train_stream.validate_initialization_args(
            SimpleNamespace(
                init_mode="file", init_file="start.pjtw", warm_start=None,
                trainable_region=None,
            )
        )
        with self.assertRaisesRegex(SystemExit, "requires --init-file"):
            train_stream.validate_initialization_args(
                SimpleNamespace(
                    init_mode="file", init_file=None, warm_start=None, trainable_region=None
                )
            )
        with self.assertRaisesRegex(SystemExit, "requires --init-mode file"):
            train_stream.validate_initialization_args(
                SimpleNamespace(
                    init_mode="zero", init_file="start.pjtw", warm_start=None,
                    trainable_region=None,
                )
            )
        with self.assertRaisesRegex(SystemExit, "legacy file-initialization alias"):
            train_stream.validate_initialization_args(
                SimpleNamespace(
                    init_mode="zero", init_file=None, warm_start="old.pjtw",
                    trainable_region=None,
                )
            )
        with self.assertRaisesRegex(SystemExit, "freezes outside coordinates"):
            train_stream.validate_initialization_args(
                SimpleNamespace(
                    init_mode="zero", init_file=None, warm_start=None,
                    trainable_region="region.json",
                )
            )


if __name__ == "__main__":
    unittest.main()
