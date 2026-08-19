#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact-fold streaming trainer with structurally constrained dense extras.

This is a narrow compatibility wrapper around ``train_stream.py``.  It keeps the
historical CLI, optimiser, pruning, targets, priors and PJTW layout unchanged,
but when ``--exact-fold`` is requested it projects dense feature rows into the
rot180+colour-swap antisymmetric subspace *before every optimiser forward/grad
pass*.  Parent/warm-start extras are projected into the same subspace so no
null-space component can leak through the continuation prior.

The writer also performs an exact integer pairing check/canonicalisation.  That
is a serialization guard only: the fitted objective itself is already confined
to the exact subspace by the projected design matrix.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Match train_stream.py's direct-execution import surface.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import train_stream as _base  # noqa: E402
from exact_extras import (  # noqa: E402
    exact_extras_residuals,
    project_exact_extras,
    project_exact_extras_int,
)

_ORIG_BUILD_EXTRAS_PHASED = _base.build_extras_phased
_ORIG_PROJECT_CHAMPION_MEAN = _base.project_champion_mean
_ORIG_WRITE_WEIGHTS_V3 = _base.write_weights_v3


def _build_extras_phased_exact(extras, wmg, weg):
    projected = project_exact_extras(extras)
    return _ORIG_BUILD_EXTRAS_PHASED(projected, wmg, weg)


def _project_champion_mean_exact(path, folder, keep, PAT_N, E):
    mu, scale = _ORIG_PROJECT_CHAMPION_MEAN(path, folder, keep, PAT_N, E)
    if folder.mode != "exact":
        raise SystemExit("train_stream_exact.py requires folder.mode=exact")
    expected = 2 * PAT_N + 2 * E
    if len(mu) != expected:
        raise SystemExit(f"projected champion width {len(mu)} != expected {expected}")
    mu = mu.copy()
    mg0 = 2 * PAT_N
    eg0 = mg0 + E
    mu[mg0:mg0 + E] = project_exact_extras(mu[mg0:mg0 + E])
    mu[eg0:eg0 + E] = project_exact_extras(mu[eg0:eg0 + E])
    return mu, scale


def _write_weights_v3_exact(path, pat_mg, pat_eg, ext_mg, ext_eg, scale, king=False):
    ext_mg = project_exact_extras_int(ext_mg)
    ext_eg = project_exact_extras_int(ext_eg)
    mg_audit = exact_extras_residuals(ext_mg)
    eg_audit = exact_extras_residuals(ext_eg)
    if mg_audit["max_abs"] != 0.0 or eg_audit["max_abs"] != 0.0:
        raise SystemExit(
            f"exact extras serialization failed: mg={mg_audit} eg={eg_audit}"
        )
    print(
        "EXACT_EXTRAS_SERIALIZATION "
        + json.dumps({"mg": mg_audit, "eg": eg_audit}, sort_keys=True)
    )
    return _ORIG_WRITE_WEIGHTS_V3(
        path, pat_mg, pat_eg, ext_mg, ext_eg, scale, king=king
    )


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if "--exact-fold" not in args:
        raise SystemExit("train_stream_exact.py is only valid with --exact-fold")
    if any(flag in args for flag in ("--full-fold", "--color-fold")):
        raise SystemExit("--exact-fold cannot be combined with another fold mode")

    # train_stream looks these globals up at runtime from its own module.  Patch
    # only the three seams needed for the exact dense contract; everything else
    # remains the certified historical implementation.
    _base.build_extras_phased = _build_extras_phased_exact
    _base.project_champion_mean = _project_champion_mean_exact
    _base.write_weights_v3 = _write_weights_v3_exact
    return _base.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
