# SPDX-License-Identifier: AGPL-3.0-or-later
"""Synthetic proofs required by the frozen CLS-L V1 preregistration."""
from __future__ import annotations

import builtins
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.sparse as sp

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
os.environ.pop("JASS_PATTERNS_DIR", None)

import cls_l_objective as cls_l  # noqa: E402
import train  # noqa: E402


def fixture():
    X = sp.csr_matrix(np.asarray([
        [1.0, 0.0, 0.5],
        [0.0, 1.0, -0.5],
        [1.0, 1.0, 0.25],
        [-0.5, 0.25, 1.0],
        [0.25, -0.75, 0.5],
        [0.75, 0.5, -0.25],
    ], dtype=np.float64))
    local = np.asarray([0.8, 0.2, 0.65, 0.35, 0.7, 0.1], dtype=np.float64)
    wdl = np.asarray([1.0, 0.0, 0.5, 0.0, 1.0, 0.5], dtype=np.float64)
    rows = np.asarray([0, 1, 2, 3, 4], dtype=np.int64)
    parent = np.asarray([0.15, -0.2, 0.05], dtype=np.float64)
    probe = np.asarray([0.3, -0.1, -0.2], dtype=np.float64)
    return X, local, wdl, rows, parent, probe


def native_loss_grad(monkeypatch, X, y, rows, parent, probe, l2):
    captured = {}

    def fake_minimize(fun, x0, jac, method, options):
        del x0, jac, method, options
        loss, grad = fun(probe)
        captured["loss"] = float(loss)
        captured["grad"] = np.asarray(grad, dtype=np.float64).copy()
        return SimpleNamespace(x=probe.copy(), fun=float(loss), nit=0)

    monkeypatch.setattr(train, "minimize", fake_minimize)
    train.train_lbfgs_chunked(
        lambda selected: X[selected],
        rows,
        y,
        l2,
        1,
        True,
        X.shape[1],
        2,
        prior_mean=parent,
        prior_prec=np.full(X.shape[1], l2, dtype=np.float64),
    )
    return captured["loss"], captured["grad"]


@pytest.mark.parametrize("which", ["LOCAL", "WDL"])
def test_single_objective_modes_reproduce_native_loss_and_gradient(monkeypatch, which):
    X, local, wdl, rows, parent, probe = fixture()
    y = local if which == "LOCAL" else wdl
    l2 = 1e-5
    expected_loss, expected_grad = native_loss_grad(
        monkeypatch, X, y, rows, parent, probe, l2
    )
    loss, grad = cls_l.objective_loss_grad(
        lambda selected: X[selected],
        rows,
        probe,
        [cls_l.DataTerm(which, y, 1.0, 1.0)],
        parent=parent,
        l2=l2,
        batch=2,
    )
    assert loss == pytest.approx(expected_loss, rel=0.0, abs=1e-14)
    assert np.allclose(grad, expected_grad, rtol=0.0, atol=1e-14)


def test_mixed_gradient_is_exact_frozen_algebra_and_regularization_once():
    X, local, wdl, rows, parent, probe = fixture()
    build = lambda selected: X[selected]
    norms = cls_l.frozen_gradient_norms(build, rows, local, wdl, parent, batch=2)
    terms = cls_l.mixed_terms(local, wdl, norms)
    loss, grad = cls_l.objective_loss_grad(
        build, rows, probe, terms, parent=parent, l2=1e-5, batch=2
    )
    ll, gl = cls_l.logistic_data_loss_grad(build, rows, local, probe, batch=2)
    lw, gw = cls_l.logistic_data_loss_grad(build, rows, wdl, probe, batch=2)
    diff = probe - parent
    expected_loss = (
        0.5 * ll / norms["LOCAL"]
        + 0.5 * lw / norms["WDL"]
        + 0.5 * 1e-5 * float(np.dot(diff, diff))
    )
    expected_grad = (
        0.5 * gl / norms["LOCAL"]
        + 0.5 * gw / norms["WDL"]
        + 1e-5 * diff
    )
    assert loss == pytest.approx(expected_loss, rel=0.0, abs=1e-14)
    assert np.allclose(grad, expected_grad, rtol=0.0, atol=1e-14)


def test_gradient_normalization_is_train_only():
    X, local, wdl, rows, parent, _probe = fixture()
    build = lambda selected: X[selected]
    before = cls_l.frozen_gradient_norms(build, rows, local, wdl, parent, batch=3)
    local2 = local.copy(); local2[5] = 0.999999
    wdl2 = wdl.copy(); wdl2[5] = 0.123456
    after = cls_l.frozen_gradient_norms(build, rows, local2, wdl2, parent, batch=3)
    assert after == pytest.approx(before, rel=0.0, abs=0.0)


def test_all_arms_share_one_coordinate_geometry_and_fail_closed_on_drift():
    X, local, _wdl, rows, parent, probe = fixture()

    def bad_build(selected):
        return X[selected, :2]

    with pytest.raises(cls_l.ObjectiveError, match="design shape drift"):
        cls_l.objective_loss_grad(
            bad_build,
            rows,
            probe,
            [cls_l.DataTerm("LOCAL", local, 1.0)],
            parent=parent,
            l2=1e-5,
            batch=2,
        )


def test_mixed_contract_is_exactly_two_terms_with_frozen_half_weight():
    _X, local, wdl, _rows, _parent, _probe = fixture()
    terms = cls_l.mixed_terms(local, wdl, {"LOCAL": 2.0, "WDL": 4.0})
    assert [term.name for term in terms] == ["LOCAL", "WDL"]
    assert [term.coefficient for term in terms] == [0.5, 0.5]
    assert [term.scale for term in terms] == [0.25, 0.125]
    with pytest.raises(cls_l.ObjectiveError):
        cls_l.mixed_terms(local, wdl, {"LOCAL": 2.0, "WDL": 4.0, "EXTRA": 1.0})


def test_normalization_kernel_import_does_not_require_scipy_optimize(monkeypatch):
    """The zero-fit preflight may compute norms even if optimizer import is unavailable."""
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "scipy.optimize" or name.startswith("scipy.optimize."):
            raise ImportError("optimizer intentionally unavailable in preflight proof")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    name = "cls_l_objective_without_optimizer"
    spec = importlib.util.spec_from_file_location(name, TOOLS / "cls_l_objective.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        X, local, wdl, rows, parent, _probe = fixture()
        norms = module.frozen_gradient_norms(
            lambda selected: X[selected], rows, local, wdl, parent, batch=2
        )
        assert set(norms) == {"LOCAL", "WDL"}
        assert norms["LOCAL"] > 0.0 and norms["WDL"] > 0.0
    finally:
        sys.modules.pop(name, None)
