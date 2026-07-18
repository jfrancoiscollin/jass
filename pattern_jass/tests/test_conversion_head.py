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
