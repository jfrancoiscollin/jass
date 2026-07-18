#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared CVH1 conversion-head geometry and binary helpers.

The feature order and sidecar layout are a public contract with
``src/conversion_head.*``. Keep changes schema-versioned and covered by tests.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np

MAGIC = 0x31485643  # "CVH1" little-endian
SCHEMA = 1
FEATURE_NAMES = [
    "total_pieces",
    "leader_men",
    "leader_kings",
    "defender_men",
    "defender_kings",
    "leader_mobility",
    "defender_mobility",
    "mobility_diff",
    "leader_king_centrality",
    "defender_king_centrality",
    "leader_men_advancement",
    "defender_men_advancement",
    "leader_near_promotion",
    "defender_near_promotion",
    "leader_lr_imbalance",
    "defender_lr_imbalance",
]
NUM_FEATURES = len(FEATURE_NAMES)
HEADER = struct.Struct("<IIII9f")
BINARY_SIZE = HEADER.size + 3 * NUM_FEATURES * 4

FULL_BB = (1 << 50) - 1
EVEN_ROW_MASK = sum(0x1F << r for r in (0, 10, 20, 30, 40))
ODD_ROW_MASK = FULL_BB & ~EVEN_ROW_MASK
COL_FIRST_MASK = sum(1 << r for r in range(0, 50, 5))
COL_LAST_MASK = COL_FIRST_MASK << 4
NOT_COL_FIRST = FULL_BB & ~COL_FIRST_MASK
NOT_COL_LAST = FULL_BB & ~COL_LAST_MASK
WHITE_NEAR_PROMO = 0x1F << 5
BLACK_NEAR_PROMO = 0x1F << 40

_SQ = np.arange(50, dtype=np.uint64)
_ROW = (_SQ // 5).astype(np.int16)
_CIN = (_SQ % 5).astype(np.int16)
_COL = np.where((_ROW % 2) == 0, 2 * _CIN + 1, 2 * _CIN).astype(np.int16)
_KING_CENTRAL = ((4.5 - np.abs(_ROW - 4.5)) + (4.5 - np.abs(_COL - 4.5))).astype(np.float64)
_WHITE_ADV = (9 - _ROW).astype(np.float64)
_BLACK_ADV = _ROW.astype(np.float64)
_LEFT = (_COL < 5).astype(np.float64)
_RIGHT = (_COL >= 5).astype(np.float64)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _u64(a: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(a, dtype=np.uint64)


def popcount(a: np.ndarray) -> np.ndarray:
    x = _u64(a)
    if len(x) == 0:
        return np.empty(0, dtype=np.int16)
    return np.unpackbits(x.view(np.uint8)).reshape(len(x), 64).sum(axis=1).astype(np.int16)


def bit_matrix(a: np.ndarray) -> np.ndarray:
    x = _u64(a)
    return ((x[:, None] >> _SQ[None, :]) & np.uint64(1)).astype(np.float64)


def shift_nw(bb: np.ndarray) -> np.ndarray:
    x = _u64(bb)
    return (((x & EVEN_ROW_MASK) >> np.uint64(5))
            | (((x & ODD_ROW_MASK) & NOT_COL_FIRST) >> np.uint64(6))) & FULL_BB


def shift_ne(bb: np.ndarray) -> np.ndarray:
    x = _u64(bb)
    return ((((x & EVEN_ROW_MASK) & NOT_COL_LAST) >> np.uint64(4))
            | ((x & ODD_ROW_MASK) >> np.uint64(5))) & FULL_BB


def shift_sw(bb: np.ndarray) -> np.ndarray:
    x = _u64(bb)
    return (((x & EVEN_ROW_MASK) << np.uint64(5))
            | (((x & ODD_ROW_MASK) & NOT_COL_FIRST) << np.uint64(4))) & FULL_BB


def shift_se(bb: np.ndarray) -> np.ndarray:
    x = _u64(bb)
    return ((((x & EVEN_ROW_MASK) & NOT_COL_LAST) << np.uint64(6))
            | ((x & ODD_ROW_MASK) << np.uint64(5))) & FULL_BB


_SHIFTS = (shift_nw, shift_ne, shift_sw, shift_se)


def king_slide_mobility(kings: np.ndarray, empty: np.ndarray) -> np.ndarray:
    k = _u64(kings)
    e = _u64(empty)
    total = np.zeros(len(k), dtype=np.int32)
    for shift in _SHIFTS:
        frontier = shift(k) & e
        for _ in range(9):
            if not np.any(frontier):
                break
            total += popcount(frontier).astype(np.int32)
            frontier = shift(frontier) & e
    return total


def mobility(men: np.ndarray, kings: np.ndarray, occupied: np.ndarray,
             color: str) -> np.ndarray:
    empty = (~_u64(occupied)) & FULL_BB
    m = _u64(men)
    if color == "white":
        quiet = popcount(shift_nw(m) & empty) + popcount(shift_ne(m) & empty)
    elif color == "black":
        quiet = popcount(shift_sw(m) & empty) + popcount(shift_se(m) & empty)
    else:
        raise ValueError(f"unknown color {color!r}")
    return quiet.astype(np.int32) + king_slide_mobility(kings, empty)


def _piece_sums(bb: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return bit_matrix(bb) @ weights


def extract_features(wm: np.ndarray, wk: np.ndarray,
                     bm: np.ndarray, bk: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(X, leader_sign_black, margin, total_pieces)``.

    Features are leader-relative. Material values are man=1 and king=3.
    """
    wm, wk, bm, bk = map(_u64, (wm, wk, bm, bk))
    if not (len(wm) == len(wk) == len(bm) == len(bk)):
        raise ValueError("bitboard arrays must have equal lengths")
    nwm, nwk, nbm, nbk = map(popcount, (wm, wk, bm, bk))
    white_value = nwm.astype(np.int32) + 3 * nwk.astype(np.int32)
    black_value = nbm.astype(np.int32) + 3 * nbk.astype(np.int32)
    diff = black_value - white_value
    sign = np.sign(diff).astype(np.int8)
    margin = np.abs(diff).astype(np.int16)
    total = (nwm + nwk + nbm + nbk).astype(np.int16)
    leader_black = sign >= 0

    occupied = wm | wk | bm | bk
    mob_w = mobility(wm, wk, occupied, "white")
    mob_b = mobility(bm, bk, occupied, "black")
    cent_w = _piece_sums(wk, _KING_CENTRAL)
    cent_b = _piece_sums(bk, _KING_CENTRAL)
    adv_w = _piece_sums(wm, _WHITE_ADV)
    adv_b = _piece_sums(bm, _BLACK_ADV)
    near_w = popcount(wm & WHITE_NEAR_PROMO).astype(np.float64)
    near_b = popcount(bm & BLACK_NEAR_PROMO).astype(np.float64)
    lr_w = np.abs(_piece_sums(wm, _LEFT) - _piece_sums(wm, _RIGHT))
    lr_b = np.abs(_piece_sums(bm, _LEFT) - _piece_sums(bm, _RIGHT))

    choose = lambda black, white: np.where(leader_black, black, white).astype(np.float64)
    X = np.column_stack([
        total,
        choose(nbm, nwm),
        choose(nbk, nwk),
        choose(nwm, nbm),
        choose(nwk, nbk),
        choose(mob_b, mob_w),
        choose(mob_w, mob_b),
        choose(mob_b - mob_w, mob_w - mob_b),
        choose(cent_b, cent_w),
        choose(cent_w, cent_b),
        choose(adv_b, adv_w),
        choose(adv_w, adv_b),
        choose(near_b, near_w),
        choose(near_w, near_b),
        choose(lr_b, lr_w),
        choose(lr_w, lr_b),
    ]).astype(np.float64, copy=False)
    return X, sign, margin, total


def validate_model(model: dict[str, Any]) -> dict[str, Any]:
    out = dict(model)
    if int(out.get("schema", -1)) != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA}")
    if list(out.get("feature_names", [])) != FEATURE_NAMES:
        raise ValueError("feature_names do not match CVH1 schema")
    out.setdefault("flags", 0)
    if int(out["flags"]) != 0:
        raise ValueError("unsupported CVH1 flags")
    scalars = (
        "lambda_cp", "tanh_scale", "center_logit", "piece_min",
        "piece_full_max", "piece_zero_max", "margin_min", "margin_max", "bias",
    )
    for key in scalars:
        out[key] = float(out[key])
        if not math.isfinite(out[key]):
            raise ValueError(f"{key} must be finite")
    if out["lambda_cp"] < 0 or out["tanh_scale"] <= 0:
        raise ValueError("lambda_cp/tanh_scale out of range")
    if not (out["piece_min"] <= out["piece_full_max"] < out["piece_zero_max"]):
        raise ValueError("invalid piece gate")
    if not (0 <= out["margin_min"] <= out["margin_max"]):
        raise ValueError("invalid margin gate")
    for key in ("mean", "inv_std", "weight"):
        values = np.asarray(out[key], dtype=np.float64)
        if values.shape != (NUM_FEATURES,) or not np.all(np.isfinite(values)):
            raise ValueError(f"{key} must contain {NUM_FEATURES} finite values")
        if key == "inv_std" and np.any(values < 0):
            raise ValueError("inv_std must be non-negative")
        out[key] = values.tolist()
    return out


def encode_model(model: dict[str, Any]) -> bytes:
    m = validate_model(model)
    head = HEADER.pack(
        MAGIC, SCHEMA, NUM_FEATURES, int(m["flags"]),
        m["lambda_cp"], m["tanh_scale"], m["center_logit"],
        m["piece_min"], m["piece_full_max"], m["piece_zero_max"],
        m["margin_min"], m["margin_max"], m["bias"],
    )
    payload = head + struct.pack(f"<{NUM_FEATURES}f", *m["mean"])
    payload += struct.pack(f"<{NUM_FEATURES}f", *m["inv_std"])
    payload += struct.pack(f"<{NUM_FEATURES}f", *m["weight"])
    if len(payload) != BINARY_SIZE:
        raise AssertionError(f"CVH1 size {len(payload)} != {BINARY_SIZE}")
    return payload


def load_json(path: str | Path) -> dict[str, Any]:
    return validate_model(json.loads(Path(path).read_text(encoding="utf-8")))
