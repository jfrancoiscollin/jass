# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contracts for train_stream's --prior-precision-file (R2 mechanism only).

OFF by default: with the flag absent, build_sequential_prior must produce the
exact same `prec` array as the pre-existing decay formula (byte-identical,
no reordering). These tests exercise build_sequential_prior / the loader /
the CLI-argument guard directly (no C++ build, no real champion file: the
champion projection itself is monkeypatched, matching the neighbouring
train_stream tests' style).
"""
from __future__ import annotations

import hashlib
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


TB = 6            # tiny canonical folded pattern space
KEEP = np.array([0, 2, 4], dtype=np.int64)   # K=3 kept buckets -> PAT_N=4
PAT_N = len(KEEP) + 1
E = 2             # extras
N = 100
L2 = 1e-4
KEPT_COUNTS = np.array([40, 10, 1], dtype=np.int64)   # visits per kept slot


def _folder():
    return SimpleNamespace(TB=TB)


def _args(**overrides):
    base = dict(
        prior_mean="parent.pjtw",
        prior_visit_scale=0.25,
        prior_decay=stream.PRIOR_DECAY_DEFAULT,
        prior_decay_ext=None,
        prior_alpha_cap=None,
        prior_precision_file=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _fake_project_champion_mean(monkeypatch):
    """build_sequential_prior's first call is project_champion_mean(champion
    file, ...); stub it so no real PJTW v3 file is needed, exactly what the
    function's own mu computation is orthogonal to (only `prec` is under
    test here)."""
    mu = np.zeros(2 * PAT_N + 2 * E, dtype=np.float64)
    monkeypatch.setattr(stream, "project_champion_mean",
                         lambda *a, **k: (mu, 1.0))


def _reference_prec(dec: float, dec_ext: float) -> np.ndarray:
    """Replica of the pre-change 4-line formula (decay path, no alpha-cap)."""
    lam = 0.25
    visits = KEPT_COUNTS.astype(np.float64) / max(N, 1)
    prec_pat = np.full(PAT_N, L2, dtype=np.float64)
    prec_pat[1:] = L2 + dec * lam * visits
    prec_ext_val = L2 + dec_ext * lam
    return np.concatenate([prec_pat, prec_pat,
                           np.full(E, prec_ext_val), np.full(E, prec_ext_val)])


def _save_vec(tmp_path: Path, values: np.ndarray, name: str = "prec.npy") -> Path:
    path = tmp_path / name
    np.save(path, values, allow_pickle=False)
    return path


# --------------------------------------------------------------------------- #
#  Absent flag : byte-identical to the pre-existing decay formula.
# --------------------------------------------------------------------------- #
def test_absent_flag_is_byte_identical_to_pre_change_formula(monkeypatch) -> None:
    _fake_project_champion_mean(monkeypatch)
    args = _args()  # prior_precision_file=None, decay defaults to 1.0
    _, prec = stream.build_sequential_prior(
        args, _folder(), KEEP, KEPT_COUNTS, PAT_N, E, N, L2
    )
    expected = _reference_prec(dec=1.0, dec_ext=1.0)
    assert np.array_equal(prec, expected)


def test_absent_flag_with_explicit_decay_zero_is_byte_identical(monkeypatch) -> None:
    _fake_project_champion_mean(monkeypatch)
    args = _args(prior_decay=0.0)
    _, prec = stream.build_sequential_prior(
        args, _folder(), KEEP, KEPT_COUNTS, PAT_N, E, N, L2
    )
    expected = _reference_prec(dec=0.0, dec_ext=0.0)
    assert np.array_equal(prec, expected)


# --------------------------------------------------------------------------- #
#  Constant-l2 file at decay=0 : identical to the plain decay=0 default.
# --------------------------------------------------------------------------- #
def test_constant_l2_file_matches_default_decay_zero(monkeypatch, tmp_path) -> None:
    _fake_project_champion_mean(monkeypatch)
    vec = np.full(TB, L2, dtype=np.float64)
    path = _save_vec(tmp_path, vec)

    args_file = _args(prior_decay=0.0, prior_precision_file=str(path))
    _, prec_file = stream.build_sequential_prior(
        args_file, _folder(), KEEP, KEPT_COUNTS, PAT_N, E, N, L2
    )

    args_default = _args(prior_decay=0.0)
    _, prec_default = stream.build_sequential_prior(
        args_default, _folder(), KEEP, KEPT_COUNTS, PAT_N, E, N, L2
    )
    assert np.array_equal(prec_file, prec_default)


# --------------------------------------------------------------------------- #
#  Non-constant file : applied precisely, slot0/extras untouched, mg==eg.
# --------------------------------------------------------------------------- #
def test_non_constant_file_is_applied_to_pattern_slots_only(monkeypatch, tmp_path) -> None:
    _fake_project_champion_mean(monkeypatch)
    vec = np.arange(1, TB + 1, dtype=np.float64) * 1e-3   # strictly positive, non-constant
    path = _save_vec(tmp_path, vec)
    args = _args(prior_decay=0.0, prior_precision_file=str(path))
    _, prec = stream.build_sequential_prior(
        args, _folder(), KEEP, KEPT_COUNTS, PAT_N, E, N, L2
    )
    prec_pat_mg = prec[0:PAT_N]
    prec_pat_eg = prec[PAT_N:2 * PAT_N]
    prec_ext_mg = prec[2 * PAT_N:2 * PAT_N + E]
    prec_ext_eg = prec[2 * PAT_N + E:2 * PAT_N + 2 * E]

    np.testing.assert_array_equal(prec_pat_mg[1:], vec[KEEP])
    assert prec_pat_mg[0] == L2
    np.testing.assert_array_equal(prec_pat_mg, prec_pat_eg)   # mg/eg share the bank
    assert np.all(prec_ext_mg == L2)
    assert np.all(prec_ext_eg == L2)


# --------------------------------------------------------------------------- #
#  Loader-level validation : wrong length / non-finite / non-positive / ndim.
# --------------------------------------------------------------------------- #
def test_loader_rejects_wrong_length(tmp_path) -> None:
    path = _save_vec(tmp_path, np.full(TB - 1, L2, dtype=np.float64))
    with pytest.raises(SystemExit, match="length"):
        stream._load_prior_precision_vector(str(path), TB)


def test_loader_rejects_non_finite(tmp_path) -> None:
    vec = np.full(TB, L2, dtype=np.float64)
    vec[1] = np.inf
    path = _save_vec(tmp_path, vec)
    with pytest.raises(SystemExit, match="non-finite"):
        stream._load_prior_precision_vector(str(path), TB)


def test_loader_rejects_non_positive(tmp_path) -> None:
    vec = np.full(TB, L2, dtype=np.float64)
    vec[2] = 0.0
    path = _save_vec(tmp_path, vec)
    with pytest.raises(SystemExit, match="non-positive"):
        stream._load_prior_precision_vector(str(path), TB)


def test_loader_rejects_wrong_ndim(tmp_path) -> None:
    vec = np.full((TB, 1), L2, dtype=np.float64)
    path = _save_vec(tmp_path, vec)
    with pytest.raises(SystemExit, match="1-D"):
        stream._load_prior_precision_vector(str(path), TB)


def test_loader_rejects_bad_dtype(tmp_path) -> None:
    vec = np.full(TB, 1, dtype=np.int32)
    path = _save_vec(tmp_path, vec)
    with pytest.raises(SystemExit, match="dtype"):
        stream._load_prior_precision_vector(str(path), TB)


def test_build_sequential_prior_propagates_loader_failure(monkeypatch, tmp_path) -> None:
    _fake_project_champion_mean(monkeypatch)
    path = _save_vec(tmp_path, np.full(TB + 1, L2, dtype=np.float64))
    args = _args(prior_decay=0.0, prior_precision_file=str(path))
    with pytest.raises(SystemExit, match="length"):
        stream.build_sequential_prior(args, _folder(), KEEP, KEPT_COUNTS, PAT_N, E, N, L2)


# --------------------------------------------------------------------------- #
#  CLI-argument guard : validate_prior_precision_file.
# --------------------------------------------------------------------------- #
def test_validate_accepts_absent_flag() -> None:
    stream.validate_prior_precision_file(_args(prior_precision_file=None))


def test_validate_accepts_well_formed_combination() -> None:
    stream.validate_prior_precision_file(
        _args(prior_decay=0.0, prior_precision_file="prec.npy")
    )
    stream.validate_prior_precision_file(
        _args(prior_decay=0.0, prior_decay_ext=0.0, prior_precision_file="prec.npy")
    )


def test_validate_requires_prior_mean() -> None:
    with pytest.raises(SystemExit, match="requires --prior-mean"):
        stream.validate_prior_precision_file(
            _args(prior_mean=None, prior_decay=0.0, prior_precision_file="prec.npy")
        )


def test_validate_rejects_alpha_cap_combination() -> None:
    with pytest.raises(SystemExit, match="prior-alpha-cap"):
        stream.validate_prior_precision_file(
            _args(prior_decay=0.0, prior_alpha_cap=0.5, prior_precision_file="prec.npy")
        )


def test_validate_rejects_nonzero_decay() -> None:
    with pytest.raises(SystemExit, match="prior-decay 0"):
        stream.validate_prior_precision_file(
            _args(prior_decay=0.5, prior_precision_file="prec.npy")
        )


def test_validate_rejects_default_decay_left_unset() -> None:
    # Default --prior-decay is 1.0 (PRIOR_DECAY_DEFAULT); the file mechanism
    # requires it EXPLICITLY at 0, so leaving it at default must also fail.
    with pytest.raises(SystemExit, match="prior-decay 0"):
        stream.validate_prior_precision_file(
            _args(prior_precision_file="prec.npy")
        )


def test_validate_rejects_nonzero_decay_ext() -> None:
    with pytest.raises(SystemExit, match="prior-decay-ext"):
        stream.validate_prior_precision_file(
            _args(prior_decay=0.0, prior_decay_ext=0.3, prior_precision_file="prec.npy")
        )


def test_validate_accepts_decay_ext_unset() -> None:
    stream.validate_prior_precision_file(
        _args(prior_decay=0.0, prior_decay_ext=None, prior_precision_file="prec.npy")
    )
