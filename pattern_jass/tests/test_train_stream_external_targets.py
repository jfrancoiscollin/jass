# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contracts for train_stream's aligned external target sidecar."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
os.environ.pop("JASS_PATTERNS_DIR", None)

import train_stream as stream  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _args(tmp_path: Path, values: Path | None, *, target: str = "external"):
    data = tmp_path / "aligned.jnnw"
    feat = tmp_path / "aligned.feat"
    data.write_bytes(b"data-provenance")
    feat.write_bytes(b"feat-provenance")
    return SimpleNamespace(
        target=target,
        target_values=str(values) if values is not None else None,
        targets_report=str(tmp_path / "targets.json") if values is not None else None,
        sample_weights=None,
        weights_report=None,
        optimizer_report=str(tmp_path / "optimizer.json"),
        data=str(data),
        feat=str(feat),
        out=str(tmp_path / "model.pjtw"),
    )


def _save(tmp_path: Path, values: np.ndarray) -> Path:
    path = tmp_path / "targets.npy"
    np.save(path, values, allow_pickle=False)
    return path


def test_external_targets_are_loaded_without_mutation_or_normalisation(
    tmp_path: Path,
) -> None:
    values = np.asarray([0.0, 0.25, 0.5, 0.75, 1.0], dtype=np.float32)
    path = _save(tmp_path, values)
    before = path.read_bytes()
    args = _args(tmp_path, path)

    loaded, report = stream._load_target_values(
        args, n_records=5, train_n=3, hold_count=2
    )

    np.testing.assert_array_equal(loaded, values)
    assert path.read_bytes() == before
    assert report["source"]["sha256"] == _sha256(path)
    assert report["source"]["pov"] == "black"
    assert report["split"]["holdout_uses_external_targets"] is True
    assert report["train"]["mean"] == pytest.approx(0.25)
    assert report["validation"]["clipping_applied"] is False
    assert json.loads(Path(args.targets_report).read_text())["operation"] == (
        "train_stream_external_targets"
    )
    assert not list(tmp_path.glob(".*.tmp-*"))


@pytest.mark.parametrize(
    ("values", "n_records", "message"),
    [
        (np.ones(4, dtype=np.float64), 4, "dtype must be float32"),
        (np.ones((2, 2), dtype=np.float32), 4, "must be a 1-D"),
        (np.ones(3, dtype=np.float32), 4, "length 3 != data records 4"),
        (
            np.asarray([0.0, np.nan, 0.5, 1.0], dtype=np.float32),
            4,
            "NaN or infinity",
        ),
        (
            np.asarray([-0.01, 0.0, 0.5, 1.0], dtype=np.float32),
            4,
            "outside black-POV probability interval",
        ),
        (
            np.asarray([0.0, 0.5, 1.01, 1.0], dtype=np.float32),
            4,
            "outside black-POV probability interval",
        ),
    ],
)
def test_external_targets_fail_closed(
    tmp_path: Path, values: np.ndarray, n_records: int, message: str
) -> None:
    path = _save(tmp_path, values)
    args = _args(tmp_path, path)
    with pytest.raises(SystemExit, match=message):
        stream._load_target_values(
            args, n_records=n_records, train_n=max(1, n_records - 1), hold_count=1
        )
    assert not Path(args.targets_report).exists()


def test_external_target_flags_are_explicit_and_paired(tmp_path: Path) -> None:
    path = _save(tmp_path, np.ones(4, dtype=np.float32))
    args = _args(tmp_path, path, target="wdl")
    with pytest.raises(SystemExit, match="require --target external"):
        stream._load_target_values(args, 4, 4, 0)

    args = _args(tmp_path, None, target="external")
    with pytest.raises(SystemExit, match="requires --target-values"):
        stream._load_target_values(args, 4, 4, 0)


@pytest.mark.parametrize(
    ("attribute", "flag"),
    [
        ("target_values", "--target-values"),
        ("data", "--data"),
        ("feat", "--feat"),
        ("out", "--out"),
        ("optimizer_report", "--optimizer-report"),
    ],
)
def test_targets_report_cannot_alias_inputs_or_output(
    tmp_path: Path, attribute: str, flag: str
) -> None:
    path = _save(tmp_path, np.ones(4, dtype=np.float32))
    args = _args(tmp_path, path)
    protected = Path(getattr(args, attribute))
    before = protected.read_bytes() if protected.exists() else None
    args.targets_report = str(protected)

    with pytest.raises(SystemExit, match=flag):
        stream._load_target_values(args, 4, 4, 0)
    if before is None:
        assert not protected.exists()
    else:
        assert protected.read_bytes() == before


def test_default_wdl_path_returns_none_without_side_effects(tmp_path: Path) -> None:
    args = _args(tmp_path, None, target="wdl")
    values, report = stream._load_target_values(args, 4, 4, 0)
    assert values is None
    assert report is None
    assert not list(tmp_path.glob("*.json"))
