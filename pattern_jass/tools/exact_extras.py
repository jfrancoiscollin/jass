#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact rot180+colour-swap constraints for ScanEval dense extras.

The production extras are stored as black/white feature pairs.  Under the
exact draughts symmetry T = rot180 + colour-swap, an antisymmetric black-POV
evaluation must satisfy E(T(position)) = -E(position).  Pattern buckets already
encode this contract under ``--exact-fold``; this module applies the same
contract to the dense extras.

For all side-paired features except left/right balance, the fitted weights are
anti-paired (w_black = -w_white, with the king PST additionally rot180-paired).
Balance itself changes sign under rot180, so its two colour coefficients are
equal instead.  Projecting the *features* before optimisation constrains the
fit itself to this subspace; integer projection at serialization is only a
fail-closed exactness guard against floating-point residue.
"""

from __future__ import annotations

import numpy as np

BASE_EXTRAS = 106


def validate_exact_extras_width(n_ext: int) -> int:
    """Validate a production ScanEval extras width and return it.

    The stable 0..105 core is followed only by colour-paired optional features,
    so every supported extension adds an even number of columns.
    """
    n_ext = int(n_ext)
    if n_ext < BASE_EXTRAS or (n_ext - BASE_EXTRAS) % 2:
        raise ValueError(
            f"exact-fold extras width must be >= {BASE_EXTRAS} and pair-aligned, got {n_ext}"
        )
    return n_ext


def _require_last_dim(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values)
    if arr.ndim == 0:
        raise ValueError("extras array must have at least one dimension")
    validate_exact_extras_width(arr.shape[-1])
    return arr


def project_exact_extras(values: np.ndarray) -> np.ndarray:
    """Orthogonally project float extras/features or weights onto exact symmetry.

    Works on shape ``(..., E)``.  Applying this to feature rows before fitting is
    equivalent to parameterising the dense model only in the exact-symmetry
    subspace while keeping the historical full-width parameter layout.
    """
    src = _require_last_dim(values)
    out = np.array(src, copy=True)

    # King PST: black square s is paired with white rot180(s), i.e. index 99-s.
    for i in range(50):
        j = 99 - i
        a = 0.5 * (src[..., i] - src[..., j])
        out[..., i] = a
        out[..., j] = -a

    # Material and mobility are ordinary black/white side pairs.
    for i, j in ((100, 101), (102, 103)):
        a = 0.5 * (src[..., i] - src[..., j])
        out[..., i] = a
        out[..., j] = -a

    # left-right balance changes sign under rot180 as colours swap, therefore
    # the two colour coefficients are equal in an antisymmetric evaluation.
    a = 0.5 * (src[..., 104] + src[..., 105])
    out[..., 104] = a
    out[..., 105] = a

    # Every optional production extra after 105 is stored as a black/white pair
    # (centrality, proximity, safe-mobility, denied, skew, has-king, extra-king).
    for i in range(106, src.shape[-1], 2):
        j = i + 1
        a = 0.5 * (src[..., i] - src[..., j])
        out[..., i] = a
        out[..., j] = -a
    return out


def exact_image_extras(values: np.ndarray) -> np.ndarray:
    """Apply the exact rot180+colour-swap transform to dense feature rows.

    This is primarily an algebraic/test oracle for the production layout.
    """
    src = _require_last_dim(values)
    out = np.array(src, copy=True)
    for i in range(50):
        out[..., i] = src[..., 99 - i]
        out[..., 99 - i] = src[..., i]
    out[..., 100] = src[..., 101]
    out[..., 101] = src[..., 100]
    out[..., 102] = src[..., 103]
    out[..., 103] = src[..., 102]
    out[..., 104] = -src[..., 105]
    out[..., 105] = -src[..., 104]
    for i in range(106, src.shape[-1], 2):
        out[..., i] = src[..., i + 1]
        out[..., i + 1] = src[..., i]
    return out


def _half_away_from_zero(value: int) -> int:
    return (value + 1) // 2 if value >= 0 else -((-value + 1) // 2)


def project_exact_extras_int(weights: np.ndarray) -> np.ndarray:
    """Exact integer projection used as a serialization guard.

    The fit is already constrained in floating point.  This step only removes
    any one-unit residue caused by optimisation/quantisation and constructs the
    paired int32 coefficients structurally.
    """
    src = _require_last_dim(weights)
    if not np.issubdtype(src.dtype, np.integer):
        raise TypeError(f"integer weights required, got {src.dtype}")
    if src.ndim != 1:
        raise ValueError("integer serialization guard expects a 1-D extras block")
    out = np.array(src, copy=True)

    def anti(i: int, j: int) -> None:
        a = _half_away_from_zero(int(src[i]) - int(src[j]))
        out[i] = a
        out[j] = -a

    def same(i: int, j: int) -> None:
        a = _half_away_from_zero(int(src[i]) + int(src[j]))
        out[i] = a
        out[j] = a

    for i in range(50):
        anti(i, 99 - i)
    anti(100, 101)
    anti(102, 103)
    same(104, 105)
    for i in range(106, len(src), 2):
        anti(i, i + 1)
    return out.astype(src.dtype, copy=False)


def exact_extras_residuals(weights: np.ndarray) -> dict[str, object]:
    """Return exact-symmetry residual counts and maximum absolute residual."""
    src = _require_last_dim(weights)
    if src.ndim != 1:
        raise ValueError("residual audit expects a 1-D extras block")
    residuals: list[float] = []
    residuals.extend(float(src[i] + src[99 - i]) for i in range(50))
    residuals.append(float(src[100] + src[101]))
    residuals.append(float(src[102] + src[103]))
    residuals.append(float(src[104] - src[105]))
    residuals.extend(float(src[i] + src[i + 1]) for i in range(106, len(src), 2))
    return {
        "constraint_count": len(residuals),
        "nonzero": sum(value != 0.0 for value in residuals),
        "max_abs": max((abs(value) for value in residuals), default=0.0),
    }
