# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract tests for train_stream's aligned per-row sample weights."""
from __future__ import annotations

import hashlib
import json
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

import train  # noqa: E402
import train_stream as stream  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _args(
    tmp_path: Path,
    weights_path: Path | None,
    *,
    report_name: str = "weights.json",
    weight_min: float | None = 0.01,
    weight_max: float | None = 100.0,
) -> SimpleNamespace:
    data = tmp_path / "aligned.jnnw"
    feat = tmp_path / "aligned.feat"
    data.write_bytes(b"synthetic-data-provenance")
    feat.write_bytes(b"synthetic-feat-provenance")
    return SimpleNamespace(
        sample_weights=str(weights_path) if weights_path is not None else None,
        weight_normalization="mean-train-1",
        weight_min=weight_min,
        weight_max=weight_max,
        weights_report=str(tmp_path / report_name) if report_name else None,
        data=str(data),
        feat=str(feat),
        out=str(tmp_path / "model.pjtw"),
        holdout_frac=0.0,
        holdout_count=0,
    )


def _save(tmp_path: Path, values: np.ndarray, name: str = "weights.npy") -> Path:
    path = tmp_path / name
    np.save(path, values, allow_pickle=False)
    return path


def _capture_chunk_objective(
    monkeypatch: pytest.MonkeyPatch,
    X: sp.csr_matrix,
    y: np.ndarray,
    train_rows: np.ndarray,
    sample_weights: np.ndarray | None,
    *,
    batch: int,
) -> tuple[float, np.ndarray]:
    captured: dict[str, object] = {}
    probe = np.linspace(-0.35, 0.45, X.shape[1], dtype=np.float64)

    def fake_minimize(fun, x0, jac, method, options):
        del x0, jac, method, options
        loss, gradient = fun(probe)
        captured["loss"] = float(loss)
        captured["gradient"] = np.asarray(gradient).copy()
        return SimpleNamespace(x=probe.copy(), fun=loss, nit=0)

    monkeypatch.setattr(train, "minimize", fake_minimize)
    train.train_lbfgs_chunked(
        lambda selected: X[selected],
        train_rows,
        y,
        l2=0.07,
        max_iter=1,
        logistic=True,
        n_cols=X.shape[1],
        batch=batch,
        sw_all=sample_weights,
    )
    return float(captured["loss"]), np.asarray(captured["gradient"])


def test_all_ones_take_exact_legacy_none_path_and_report_is_deterministic(
    tmp_path: Path,
) -> None:
    path = _save(tmp_path, np.ones(7, dtype=np.float32))
    source_sha = _sha256(path)

    args_a = _args(
        tmp_path,
        path,
        report_name="report-a.json",
        weight_min=1.0,
        weight_max=1.0,
    )
    optimizer_weights_a, report_a = stream._load_sample_weights(
        args_a, n_records=7, train_n=5, hold_count=2
    )
    assert optimizer_weights_a is None
    assert report_a["optimizer"] == {
        "sw_all_used": False,
        "uniform_after_normalization": True,
    }
    assert report_a["normalization"]["normalized_train_mean"] == 1.0
    assert report_a["effective_sample_size"]["ess"] == 5.0
    assert report_a["split"]["holdout_weighted"] is False
    assert report_a["source"]["sha256"] == source_sha
    assert _sha256(path) == source_sha

    args_b = _args(
        tmp_path,
        path,
        report_name="report-b.json",
        weight_min=1.0,
        weight_max=1.0,
    )
    optimizer_weights_b, report_b = stream._load_sample_weights(
        args_b, n_records=7, train_n=5, hold_count=2
    )
    assert optimizer_weights_b is None
    assert report_b == report_a
    assert Path(args_a.weights_report).read_bytes() == Path(args_b.weights_report).read_bytes()
    assert not list(tmp_path.glob(".*.tmp-*"))


def test_train_only_normalization_stats_and_kish_ess(tmp_path: Path) -> None:
    path = _save(
        tmp_path,
        np.asarray([1.0, 2.0, 3.0, 4.0, 100.0, 100.0], dtype=np.float32),
    )
    args = _args(tmp_path, path, weight_min=1.0, weight_max=100.0)
    optimizer_weights, report = stream._load_sample_weights(
        args, n_records=6, train_n=4, hold_count=2
    )

    np.testing.assert_allclose(
        optimizer_weights[:4],
        np.asarray([0.4, 0.8, 1.2, 1.6], dtype=np.float64),
        rtol=0.0,
        atol=3e-16,
    )
    # Tail values are aligned for indexing, but cannot affect fit or normalisation.
    np.testing.assert_allclose(
        optimizer_weights[4:],
        np.asarray([40.0, 40.0], dtype=np.float64),
        rtol=0.0,
        atol=1e-14,
    )
    assert report["normalization"]["raw_train_mean"] == 2.5
    assert report["normalization"]["factor"] == 0.4
    assert report["normalized_train"]["mean"] == 1.0
    assert report["raw_train"]["quantiles"]["p50"] == 2.5
    assert report["effective_sample_size"]["ess"] == pytest.approx(10.0 / 3.0)
    assert report["effective_sample_size"]["ess_fraction"] == pytest.approx(5.0 / 6.0)
    assert report["validation"]["clipping_applied"] is False
    assert report["aligned_inputs"]["data_sha256"] == _sha256(Path(args.data))
    assert report["aligned_inputs"]["feat_sha256"] == _sha256(Path(args.feat))


@pytest.mark.parametrize(
    ("values", "n_records", "message"),
    [
        (np.ones(4, dtype=np.float64), 4, "dtype must be float32"),
        (np.ones((2, 2), dtype=np.float32), 4, "must be a 1-D"),
        (np.ones(3, dtype=np.float32), 4, "length 3 != data records 4"),
        (
            np.asarray([1.0, np.nan, 1.0, 1.0], dtype=np.float32),
            4,
            "NaN or infinity",
        ),
        (
            np.asarray([1.0, np.inf, 1.0, 1.0], dtype=np.float32),
            4,
            "NaN or infinity",
        ),
        (
            np.asarray([1.0, 0.0, 1.0, 1.0], dtype=np.float32),
            4,
            "strictly positive",
        ),
        (
            np.asarray([1.0, -0.5, 1.0, 1.0], dtype=np.float32),
            4,
            "strictly positive",
        ),
    ],
)
def test_invalid_weight_vectors_fail_closed(
    tmp_path: Path,
    values: np.ndarray,
    n_records: int,
    message: str,
) -> None:
    path = _save(tmp_path, values)
    args = _args(tmp_path, path)
    with pytest.raises(SystemExit, match=message):
        stream._load_sample_weights(
            args, n_records=n_records, train_n=n_records - 1, hold_count=1
        )
    assert not Path(args.weights_report).exists()


def test_bounds_are_validation_only_and_never_clip_input(tmp_path: Path) -> None:
    values = np.asarray([0.25, 0.5, 1.5, 2.0], dtype=np.float32)
    path = _save(tmp_path, values)
    before = path.read_bytes()
    args = _args(tmp_path, path, weight_min=0.5, weight_max=1.5)

    with pytest.raises(SystemExit, match="outside validation bounds"):
        stream._load_sample_weights(
            args, n_records=4, train_n=3, hold_count=1
        )
    assert path.read_bytes() == before
    np.testing.assert_array_equal(np.load(path, allow_pickle=False), values)
    assert not Path(args.weights_report).exists()


@pytest.mark.parametrize(
    ("protected_attribute", "protected_flag"),
    [
        ("sample_weights", "--sample-weights"),
        ("data", "--data"),
        ("feat", "--feat"),
        ("out", "--out"),
    ],
)
def test_weights_report_must_not_alias_any_input_or_output(
    tmp_path: Path,
    protected_attribute: str,
    protected_flag: str,
) -> None:
    path = _save(tmp_path, np.ones(4, dtype=np.float32))
    args = _args(tmp_path, path, weight_min=1.0, weight_max=1.0)
    protected_path = Path(getattr(args, protected_attribute))
    before = protected_path.read_bytes() if protected_path.exists() else None
    args.weights_report = str(protected_path)

    with pytest.raises(SystemExit, match=protected_flag):
        stream._load_sample_weights(args, n_records=4, train_n=4, hold_count=0)
    if before is None:
        assert not protected_path.exists()
    else:
        assert protected_path.read_bytes() == before
    assert not list(tmp_path.glob(".*.tmp-*"))


def test_weights_report_refuses_preexisting_target(tmp_path: Path) -> None:
    path = _save(tmp_path, np.ones(4, dtype=np.float32))
    args = _args(tmp_path, path, weight_min=1.0, weight_max=1.0)
    report_path = Path(args.weights_report)
    sentinel = b"do-not-clobber\n"
    report_path.write_bytes(sentinel)

    with pytest.raises(SystemExit, match="already exists"):
        stream._load_sample_weights(args, n_records=4, train_n=4, hold_count=0)
    assert report_path.read_bytes() == sentinel
    assert not list(tmp_path.glob(".*.tmp-*"))


def test_atomic_report_failure_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _save(
        tmp_path,
        np.asarray([1.0, 2.0, 1.0, 2.0], dtype=np.float32),
    )
    args = _args(tmp_path, path, weight_min=1.0, weight_max=2.0)

    def fail_publish(source, target):
        del source, target
        raise OSError("synthetic publish failure")

    monkeypatch.setattr(stream.os, "link", fail_publish)
    with pytest.raises(SystemExit, match="cannot atomically publish"):
        stream._load_sample_weights(args, n_records=4, train_n=4, hold_count=0)
    assert not Path(args.weights_report).exists()
    assert not list(tmp_path.glob(".*.tmp-*"))


@pytest.mark.parametrize("isolated", ["weight_min", "weight_max", "weights_report"])
def test_weight_options_require_sample_weights(
    tmp_path: Path, isolated: str
) -> None:
    args = _args(
        tmp_path,
        None,
        report_name="",
        weight_min=None,
        weight_max=None,
    )
    setattr(
        args,
        isolated,
        str(tmp_path / "report.json") if isolated == "weights_report" else 1.0,
    )
    with pytest.raises(SystemExit, match="require --sample-weights"):
        stream._load_sample_weights(args, n_records=4, train_n=4, hold_count=0)


@pytest.mark.parametrize("missing", ["weight_min", "weight_max", "weights_report"])
def test_sample_weights_require_complete_validation_contract(
    tmp_path: Path, missing: str
) -> None:
    path = _save(tmp_path, np.ones(4, dtype=np.float32))
    args = _args(tmp_path, path)
    setattr(args, missing, None)
    with pytest.raises(SystemExit, match=f"--{missing.replace('_', '-')}"):
        stream._load_sample_weights(args, n_records=4, train_n=4, hold_count=0)


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [(0.0, 1.0), (-1.0, 1.0), (2.0, 1.0), (np.nan, 1.0), (1.0, np.inf)],
)
def test_invalid_bounds_fail_closed(
    tmp_path: Path, minimum: float, maximum: float
) -> None:
    path = _save(tmp_path, np.ones(4, dtype=np.float32))
    args = _args(tmp_path, path, weight_min=minimum, weight_max=maximum)
    with pytest.raises(SystemExit, match="must be finite"):
        stream._load_sample_weights(args, n_records=4, train_n=4, hold_count=0)


def test_weighted_chunk_gradient_matches_full_matrix_gradient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del tmp_path
    rng = np.random.default_rng(20260729)
    dense = rng.normal(size=(11, 5))
    dense[np.abs(dense) < 0.45] = 0.0
    X = sp.csr_matrix(dense)
    y = rng.choice(np.asarray([0.0, 0.5, 1.0]), size=11)
    train_rows = np.arange(8, dtype=np.int64)
    weights = np.asarray(
        [0.4, 0.8, 1.2, 1.6, 0.7, 1.3, 0.9, 1.1, 25.0, 50.0, 75.0],
        dtype=np.float64,
    )
    weights[:8] /= weights[:8].mean()

    probe = np.linspace(-0.35, 0.45, X.shape[1], dtype=np.float64)
    full_capture: dict[str, object] = {}

    def fake_full_minimize(fun, x0, jac, method, options):
        del x0, jac, method, options
        loss, gradient = fun(probe)
        full_capture["loss"] = float(loss)
        full_capture["gradient"] = np.asarray(gradient).copy()
        return SimpleNamespace(x=probe.copy(), fun=loss, nit=0)

    monkeypatch.setattr(train, "minimize", fake_full_minimize)
    train.train_lbfgs(
        X[train_rows],
        y[train_rows],
        l2=0.07,
        max_iter=1,
        logistic=True,
        sw=weights[train_rows],
    )

    chunk_loss, chunk_gradient = _capture_chunk_objective(
        monkeypatch,
        X,
        y,
        train_rows,
        weights,
        batch=3,
    )
    assert chunk_loss == pytest.approx(float(full_capture["loss"]), abs=1e-14)
    np.testing.assert_allclose(
        chunk_gradient,
        np.asarray(full_capture["gradient"]),
        rtol=1e-13,
        atol=1e-14,
    )


def test_holdout_is_unweighted_and_tail_weights_cannot_change_fit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_train = [1.0, 2.0, 3.0, 4.0]
    path_a = _save(
        tmp_path,
        np.asarray(raw_train + [5.0, 6.0], dtype=np.float32),
        "weights-a.npy",
    )
    path_b = _save(
        tmp_path,
        np.asarray(raw_train + [50.0, 60.0], dtype=np.float32),
        "weights-b.npy",
    )
    args_a = _args(
        tmp_path, path_a, report_name="a.json", weight_min=1.0, weight_max=60.0
    )
    args_b = _args(
        tmp_path, path_b, report_name="b.json", weight_min=1.0, weight_max=60.0
    )
    weights_a, _ = stream._load_sample_weights(
        args_a, n_records=6, train_n=4, hold_count=2
    )
    weights_b, _ = stream._load_sample_weights(
        args_b, n_records=6, train_n=4, hold_count=2
    )
    np.testing.assert_array_equal(weights_a[:4], weights_b[:4])
    assert not np.array_equal(weights_a[4:], weights_b[4:])

    X = sp.csr_matrix(
        np.asarray(
            [
                [1.0, 0.0],
                [0.0, 1.0],
                [1.0, 1.0],
                [-1.0, 0.5],
                [0.2, 1.3],
                [-0.7, 0.4],
            ]
        )
    )
    y = np.asarray([1.0, 0.0, 0.5, 1.0, 0.0, 1.0])
    train_rows = np.arange(4, dtype=np.int64)
    loss_a, gradient_a = _capture_chunk_objective(
        monkeypatch, X, y, train_rows, weights_a, batch=2
    )
    loss_b, gradient_b = _capture_chunk_objective(
        monkeypatch, X, y, train_rows, weights_b, batch=2
    )
    assert loss_a == loss_b
    np.testing.assert_array_equal(gradient_a, gradient_b)

    fitted = np.asarray([0.3, -0.2])
    holdout_loss, n_val = stream._holdout_logloss(
        lambda selected: X[selected],
        y,
        fitted,
        train_n=4,
        n_records=6,
        chunk=1,
    )
    logits = X[4:6] @ fitted
    probabilities = 0.5 * (np.tanh(0.5 * logits) + 1.0)
    expected = -np.mean(
        y[4:6] * np.log(probabilities + 1e-12)
        + (1.0 - y[4:6]) * np.log(1.0 - probabilities + 1e-12)
    )
    assert n_val == 2
    assert holdout_loss == pytest.approx(float(expected), abs=1e-15)


def test_weighted_optimizer_is_deterministic() -> None:
    X = sp.csr_matrix(
        np.asarray(
            [
                [1.0, 0.0, 0.2],
                [0.0, 1.0, -0.1],
                [1.0, 1.0, 0.3],
                [-1.0, 0.5, 0.0],
                [0.2, 1.3, 0.7],
                [-0.7, 0.4, -0.2],
            ]
        )
    )
    y = np.asarray([1.0, 0.0, 0.5, 1.0, 0.0, 1.0])
    rows = np.arange(len(y), dtype=np.int64)
    weights = np.asarray([0.5, 0.75, 1.0, 1.25, 1.1, 1.4], dtype=np.float64)
    weights /= weights.mean()

    def fit():
        return train.train_lbfgs_chunked(
            lambda selected: X[selected],
            rows,
            y,
            l2=0.03,
            max_iter=30,
            logistic=True,
            n_cols=X.shape[1],
            batch=2,
            sw_all=weights,
        )

    first = fit()
    second = fit()
    np.testing.assert_array_equal(first[0], second[0])
    assert first[1:] == second[1:]


@pytest.mark.parametrize(
    ("holdout_frac", "holdout_count", "message"),
    [
        (np.nan, 0, "must be finite"),
        (1.0, 0, "must be finite"),
        (0.0, 4, "must be in"),
        (0.25, 1, "mutually exclusive"),
    ],
)
def test_holdout_split_validation(
    holdout_frac: float, holdout_count: int, message: str
) -> None:
    args = SimpleNamespace(
        holdout_frac=holdout_frac,
        holdout_count=holdout_count,
    )
    with pytest.raises(SystemExit, match=message):
        stream._resolve_holdout(args, n_records=4)
