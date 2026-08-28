#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixed residual-family probe for L3_RESIDUAL_FEATURE_DISCOVERY_V1_20260828.

The learner is deliberately tiny: D1 enters only as an immutable baseline with
coefficient exactly 1.0; the only trainable parameters are residual feature
weights.  No intercept, D1 rescale, search score, source identity or split flag
can enter the feature matrix.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

CTX2_WIDTH = 15
F1_WIDTH = 12
F2_WIDTH = 14
F3_WIDTH = 12
F4_WIDTH = 16
F5_WIDTH = 12
ALL_NEW_WIDTH = F1_WIDTH + F2_WIDTH + F3_WIDTH + F4_WIDTH + F5_WIDTH
TOTAL_WIDTH = CTX2_WIDTH + ALL_NEW_WIDTH

FAMILY_SLICES: dict[str, slice | np.ndarray] = {
    "CTX2_REF": slice(0, 15),
    "F1_CAPTURE_GEOMETRY": slice(15, 27),
    "F2_RESPONSE_FRONTIER": slice(27, 41),
    "F3_PROMOTION_RACE": slice(41, 53),
    "F4_STRUCTURE_GRAPH": slice(53, 69),
    "F5_KING_GEOMETRY_PLUS": slice(69, 81),
    "F6_ALL_NEW": slice(15, 81),
}
ELIGIBLE_FAMILIES = tuple(k for k in FAMILY_SLICES if k != "CTX2_REF")
L2 = 1e-3
MAXITER = 500
GTOL = 1e-7
MAXCOR = 10
PAIR_CAP = 250_000
PAIR_ORDER_SEED = 2026090701
SHAM_SEED_BASE = 2026090703

FORBIDDEN_FEATURE_TOKENS = (
    "q1000", "q5k", "q50", "q200", "wdl", "outcome", "d1", "t2",
    "source", "split", "partition", "holdout", "label", "target",
)

@dataclass(frozen=True)
class ProbeArtifact:
    family: str
    mean: np.ndarray
    std: np.ndarray
    weights: np.ndarray
    d1_sha256: str
    optimizer: dict[str, object]

    def predict(self, features: np.ndarray, d1_parent: np.ndarray) -> np.ndarray:
        x = np.asarray(features, dtype=np.float64)
        d1 = np.asarray(d1_parent, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != len(self.mean) or d1.shape != (len(x),):
            raise ValueError("probe prediction geometry drift")
        z = (x - self.mean) / self.std
        return d1 + z @ self.weights

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema": "jass.l3_residual_feature_probe.v1",
            "family": self.family,
            "d1_coefficient": 1.0,
            "intercept": 0.0,
            "d1_sha256": self.d1_sha256,
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "weights": self.weights.tolist(),
            "optimizer": self.optimizer,
        }

    @staticmethod
    def from_json_dict(obj: dict[str, object]) -> "ProbeArtifact":
        if obj.get("schema") != "jass.l3_residual_feature_probe.v1":
            raise ValueError("probe artifact schema drift")
        if float(obj.get("d1_coefficient", 0.0)) != 1.0 or float(obj.get("intercept", 1.0)) != 0.0:
            raise ValueError("D1 fixed-baseline contract drift")
        return ProbeArtifact(
            family=str(obj["family"]),
            mean=np.asarray(obj["mean"], dtype=np.float64),
            std=np.asarray(obj["std"], dtype=np.float64),
            weights=np.asarray(obj["weights"], dtype=np.float64),
            d1_sha256=str(obj["d1_sha256"]),
            optimizer=dict(obj["optimizer"]),
        )


def read_rffd(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) < 12 or raw[:4] != b"RFFD":
        raise ValueError("bad RFFD header")
    n, width = struct.unpack_from("<II", raw, 4)
    if width != TOTAL_WIDTH:
        raise ValueError(f"RFFD width drift: {width} != {TOTAL_WIDTH}")
    expected = 12 + int(n) * int(width) * 4
    if len(raw) != expected:
        raise ValueError("RFFD size/count drift")
    return np.frombuffer(raw, dtype="<f4", offset=12, count=n * width).reshape(n, width).astype(np.float64)


def family_matrix(all_features: np.ndarray, family: str) -> np.ndarray:
    if family not in FAMILY_SLICES:
        raise ValueError(f"unknown residual family {family!r}")
    x = np.asarray(all_features, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != TOTAL_WIDTH:
        raise ValueError("residual feature geometry drift")
    out = x[:, FAMILY_SLICES[family]]
    if not np.all(np.isfinite(out)):
        raise ValueError("nonfinite residual feature")
    return np.ascontiguousarray(out, dtype=np.float64)


def validate_feature_names(names: Sequence[str]) -> None:
    lowered = [str(name).lower() for name in names]
    for name in lowered:
        if any(token in name for token in FORBIDDEN_FEATURE_TOKENS):
            raise ValueError(f"forbidden residual feature input: {name}")


def deterministic_pair_cap(
    good: np.ndarray,
    bad: np.ndarray,
    parent_fingerprint: Sequence[str],
    *,
    cap: int = PAIR_CAP,
    seed: int = PAIR_ORDER_SEED,
) -> np.ndarray:
    g = np.asarray(good, dtype=np.int64)
    b = np.asarray(bad, dtype=np.int64)
    if g.shape != b.shape or len(parent_fingerprint) != len(g):
        raise ValueError("pair cap geometry drift")
    order = list(range(len(g)))
    order.sort(key=lambda i: (
        hashlib.sha256(f"{seed}|{parent_fingerprint[i]}|{int(g[i])}|{int(b[i])}".encode()).digest(),
        str(parent_fingerprint[i]), int(g[i]), int(b[i]),
    ))
    if len(order) > cap:
        order = order[:cap]
    return np.asarray(order, dtype=np.int64)


def fit_normalization(features: np.ndarray, good: np.ndarray, bad: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(features, dtype=np.float64)
    rows = np.unique(np.concatenate((np.asarray(good, dtype=np.int64), np.asarray(bad, dtype=np.int64))))
    if len(rows) == 0:
        raise ValueError("no training rows")
    train = x[rows]
    mean = train.mean(axis=0)
    std = train.std(axis=0)
    std[std < 1e-12] = 1.0
    if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(std)):
        raise ValueError("nonfinite normalization")
    return mean, std


def fit_probe(
    family: str,
    features: np.ndarray,
    d1_parent: np.ndarray,
    good: np.ndarray,
    bad: np.ndarray,
    *,
    d1_sha256: str,
    l2: float = L2,
) -> ProbeArtifact:
    x = np.asarray(features, dtype=np.float64)
    d1 = np.asarray(d1_parent, dtype=np.float64)
    g = np.asarray(good, dtype=np.int64)
    b = np.asarray(bad, dtype=np.int64)
    if x.ndim != 2 or d1.shape != (len(x),) or g.shape != b.shape or len(g) == 0:
        raise ValueError("probe fit geometry drift")
    if np.any(g < 0) or np.any(b < 0) or np.any(g >= len(x)) or np.any(b >= len(x)):
        raise ValueError("pair row out of range")
    mean, std = fit_normalization(x, g, b)
    z = (x - mean) / std
    pair_x = z[g] - z[b]
    d1_margin = d1[g] - d1[b]
    n = float(len(g))

    def fg(weights: np.ndarray) -> tuple[float, np.ndarray]:
        margin = d1_margin + pair_x @ weights
        loss = float(np.sum(np.logaddexp(0.0, -margin)) / n + 0.5 * l2 * np.dot(weights, weights))
        q = -expit(-margin) / n
        grad = pair_x.T @ q + l2 * weights
        return loss, np.asarray(grad, dtype=np.float64)

    initial = np.zeros(x.shape[1], dtype=np.float64)
    result = minimize(
        fg, initial, jac=True, method="L-BFGS-B",
        options={"maxiter": MAXITER, "gtol": GTOL, "maxcor": MAXCOR},
    )
    weights = np.asarray(result.x, dtype=np.float64)
    if not np.all(np.isfinite(weights)) or not np.isfinite(float(result.fun)):
        raise ValueError("nonfinite residual optimizer")
    receipt: dict[str, object] = {
        "method": "L-BFGS-B",
        "zero_init": True,
        "success": bool(result.success),
        "status": int(result.status),
        "message": str(result.message),
        "iterations": int(result.nit),
        "objective": float(result.fun),
        "gradient_inf_norm": float(np.max(np.abs(result.jac))) if len(result.jac) else 0.0,
        "l2": float(l2),
        "maxiter": MAXITER,
        "gtol": GTOL,
        "maxcor": MAXCOR,
        "pairs": int(len(g)),
    }
    return ProbeArtifact(family, mean, std, weights, d1_sha256, receipt)


def parent_sign(fingerprint: str, cohort: str, sham_index: int, *, seed_base: int = SHAM_SEED_BASE) -> float:
    if sham_index < 0 or sham_index >= 32:
        raise ValueError("sham index outside frozen 0..31")
    digest = hashlib.sha256(f"{seed_base}|{cohort}|{sham_index}|{fingerprint}".encode()).digest()
    return 1.0 if (digest[0] & 1) else -1.0


def apply_parent_sign_sham(
    features: np.ndarray,
    row_parent_fingerprint: Sequence[str],
    *,
    cohort: str,
    sham_index: int,
) -> np.ndarray:
    x = np.asarray(features, dtype=np.float64)
    if len(row_parent_fingerprint) != len(x):
        raise ValueError("sham parent alignment drift")
    signs = np.asarray(
        [parent_sign(str(fp), cohort, sham_index) for fp in row_parent_fingerprint],
        dtype=np.float64,
    )
    return x * signs[:, None]


def save_artifact(path: Path, artifact: ProbeArtifact) -> None:
    path.write_text(json.dumps(artifact.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_artifact(path: Path) -> ProbeArtifact:
    return ProbeArtifact.from_json_dict(json.loads(path.read_text(encoding="utf-8")))
