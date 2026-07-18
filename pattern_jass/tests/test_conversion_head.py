# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import conversion_head as ch  # noqa: E402
from train_conversion_head import equal_group_weights, grouped_split  # noqa: E402


def bb(*squares: int) -> np.ndarray:
    value = sum(1 << (sq - 1) for sq in squares)
    return np.asarray([value], dtype=np.uint64)


def model() -> dict:
    return {
        "schema": ch.SCHEMA,
        "feature_names": ch.FEATURE_NAMES,
        "flags": 0,
        "lambda_cp": 10.0,
        "tanh_scale": 1.0,
        "center_logit": 0.0,
        "piece_min": 8.0,
        "piece_full_max": 12.0,
        "piece_zero_max": 20.0,
        "margin_min": 1.0,
        "margin_max": 1.0,
        "bias": 0.0,
        "mean": [0.0] * ch.NUM_FEATURES,
        "inv_std": [1.0] * ch.NUM_FEATURES,
        "weight": [0.0] * ch.NUM_FEATURES,
    }


def test_binary_contract() -> None:
    payload = ch.encode_model(model())
    assert len(payload) == ch.BINARY_SIZE == 244
    magic, schema, n_features, flags = struct.unpack_from("<IIII", payload, 0)
    assert magic == ch.MAGIC
    assert schema == ch.SCHEMA
    assert n_features == ch.NUM_FEATURES
    assert flags == 0


def test_leader_relative_counts_match_contract() -> None:
    # Black: K1 + men 2..5 = value 7. White: K31 + men 32..34 = value 6.
    X, sign, margin, pieces = ch.extract_features(
        bb(32, 33, 34), bb(31), bb(2, 3, 4, 5), bb(1))
    assert sign.tolist() == [1]
    assert margin.tolist() == [1]
    assert pieces.tolist() == [9]
    assert X[0, ch.FEATURE_NAMES.index("leader_men")] == 4
    assert X[0, ch.FEATURE_NAMES.index("leader_kings")] == 1
    assert X[0, ch.FEATURE_NAMES.index("defender_men")] == 3
    assert X[0, ch.FEATURE_NAMES.index("defender_kings")] == 1


def test_group_split_has_no_leakage_and_equal_mass() -> None:
    groups = np.asarray(["a", "a", "a", "b", "c", "c", "d"])
    train, hold = grouped_split(groups, holdout_frac=0.25, seed=7)
    assert train.any() and hold.any()
    assert set(groups[train]) & set(groups[hold]) == set()

    weights = equal_group_weights(groups)
    masses = {g: float(weights[groups == g].sum()) for g in np.unique(groups)}
    assert max(masses.values()) - min(masses.values()) < 1e-12


def test_rejects_wrong_feature_order() -> None:
    bad = model()
    bad["feature_names"] = list(reversed(ch.FEATURE_NAMES))
    try:
        ch.encode_model(bad)
    except ValueError as exc:
        assert "feature_names" in str(exc)
    else:
        raise AssertionError("wrong feature order accepted")


# --- Python<->C++ numeric parity lock -------------------------------------- #
# Golden feature vectors for three fixed positions. The SAME positions and the
# SAME golden values are asserted in tests/test_conversion_head.cpp against the
# C++ compute_features(). If either extractor drifts (a shift bit-mask, a row/col
# convention, a mobility rule), one side fails and the mismatch is caught before
# any offline-fitted head is applied to differently-computed runtime features.
# Squares are 1..50 (bit = square-1); FEN mirror is in the C++ test.
PARITY_GOLDEN = {
    # W:WK28,21,22,23:BK7,11,12,13,16
    "A_black_leader": (
        dict(wm=(21, 22, 23), wk=(28,), bm=(11, 12, 13, 16), bk=(7,)),
        [9, 4, 1, 3, 1, 7, 13, -6, 3, 8, 9, 15, 0, 0, 2, 1], 1, 1, 9),
    # W:WK8,26,27,28,29,30,31:BK40,11,12,13,14,15
    "B_white_leader": (
        dict(wm=(26, 27, 28, 29, 30, 31), wk=(8,), bm=(11, 12, 13, 14, 15), bk=(40,)),
        [13, 6, 1, 5, 1, 11, 14, -3, 5, 3, 23, 10, 0, 0, 2, 1], -1, 1, 13),
    # W:WK28,6,7,21,22:BK10,41,42,16,17
    "C_tie_promo_lr": (
        dict(wm=(6, 7, 21, 22), wk=(28,), bm=(41, 42, 16, 17), bk=(10,)),
        [10, 4, 1, 4, 1, 10, 13, -3, 2, 8, 22, 26, 2, 2, 4, 4], 0, 0, 10),
}


def test_python_c_parity_golden() -> None:
    for name, (p, feats, sign, margin, total) in PARITY_GOLDEN.items():
        X, s, m, t = ch.extract_features(bb(*p["wm"]), bb(*p["wk"]),
                                         bb(*p["bm"]), bb(*p["bk"]))
        assert list(X[0]) == [float(v) for v in feats], f"{name}: feature mismatch"
        assert int(s[0]) == sign and int(m[0]) == margin and int(t[0]) == total, name
