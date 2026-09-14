#!/usr/bin/env python3
"""Target-host adapter for the frozen ED4-FRESH D confirmation stage.

CPX62 launch regressions exposed failures in NumPy's Python-sequence conversion
paths before any confirmation target was opened.  This adapter changes no
confirmation identities, gates, bootstrap seed, strata, replicate count, alpha
or target protocol.  It materializes numeric vectors by allocating fixed-size
NumPy arrays and assigning scalar values one-by-one, avoiding ``asarray``,
``array`` and ``fromiter`` conversion of Python sequences.  All bootstrap RNG,
vectorized resampling, reductions and quantiles remain the frozen NumPy recipe.

The base stage remains the scientific source of truth.  The adapter installs
only the two sequence-materialization entry points used by D statistics and
then delegates to the base stage.  Rehearsal and production therefore still
share one command/common spec and differ only by LAUNCH_MODE.
"""
from __future__ import annotations

import traceback
from typing import Iterable, Sequence

import numpy as np

from jobs.tools import ed4_fresh_d_confirmation_stage as base


def _float_vector(values: Iterable[float], size: int) -> np.ndarray:
    """Materialize an exact float64 vector without Python-sequence conversion."""
    out = np.empty(size, dtype=np.float64)
    observed = 0
    for observed, value in enumerate(values, start=1):
        base.need(observed <= size, "float_vector_overflow")
        out[observed - 1] = float(value)
    base.need(observed == size, "float_vector_size")
    return out


def _gather_float(values: np.ndarray, indices: Sequence[int]) -> np.ndarray:
    """Gather float64 values without NumPy converting a Python index sequence."""
    out = np.empty(len(indices), dtype=np.float64)
    for offset, index in enumerate(indices):
        out[offset] = values[int(index)]
    return out


def bootstrap_parent_one_sided(
    delta: Sequence[float] | np.ndarray,
    cells: list[str],
    seed: int,
    alpha: float = base.BLOCK_ALPHA,
) -> dict:
    base.need(len(delta) == len(cells) and len(delta) > 0, "bootstrap_alignment")
    values = _float_vector(delta, len(delta))
    rng = np.random.default_rng(seed)
    boots = np.zeros(base.BOOTSTRAPS, dtype=float)
    for cell in sorted(set(cells)):
        indices = [index for index, label in enumerate(cells) if label == cell]
        base.need(len(indices) == base.CELL_QUOTA, "bootstrap_cell_quota")
        x = _gather_float(values, indices)
        for start in range(0, base.BOOTSTRAPS, 250):
            end = min(start + 250, base.BOOTSTRAPS)
            sample = rng.integers(0, len(x), size=(end - start, len(x)))
            boots[start:end] += x[sample].sum(axis=1) / len(values)
    return {
        "mean": float(values.mean()),
        "lower": float(np.quantile(boots, alpha)),
        "upper": float(np.quantile(boots, 1.0 - alpha)),
        "one_sided_alpha": float(alpha),
        "bootstrap_replicates": base.BOOTSTRAPS,
        "cluster_unit": "parent",
        "strata": "phase_x_stm",
    }


def comparison(base_rows: list[dict], candidate_rows: list[dict], seed: int) -> dict:
    base.need(
        [row["parent_id"] for row in base_rows] == [row["parent_id"] for row in candidate_rows],
        "parent_population_mismatch",
    )
    delta = _float_vector(
        (a["regret"] - b["regret"] for a, b in zip(base_rows, candidate_rows)),
        len(base_rows),
    )
    cells = [row["cell"] for row in base_rows]
    out = bootstrap_parent_one_sided(delta, cells, seed)
    hit_delta = _float_vector(
        (b["hit"] - a["hit"] for a, b in zip(base_rows, candidate_rows)),
        len(base_rows),
    )
    out.update(
        top_hit_delta=float(hit_delta.mean()),
        improved=int(np.sum(delta > 0)),
        harmed=int(np.sum(delta < 0)),
        unchanged=int(np.sum(delta == 0)),
        decision_changes=sum(a["choice"] != b["choice"] for a, b in zip(base_rows, candidate_rows)),
    )
    return out


def install() -> None:
    base.bootstrap_parent_one_sided = bootstrap_parent_one_sided
    base.comparison = comparison


def main() -> int:
    install()
    return base.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
