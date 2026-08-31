#!/usr/bin/env python3
"""E2 terminal readout with preregistered independent C1/C2/E1 bootstrap subflows."""
from __future__ import annotations

import numpy as np

from jobs.tools import t3_f6_e2_readout as base


def bootstrap(c1, c2, t3_nodes, curriculum_nodes, *, samples=base.BOOTSTRAP, seed=base.BOOTSTRAP_SEED):
    children = np.random.SeedSequence(seed).spawn(3)
    rng_c1 = np.random.Generator(np.random.PCG64(children[0]))
    rng_c2 = np.random.Generator(np.random.PCG64(children[1]))
    rng_e1 = np.random.Generator(np.random.PCG64(children[2]))
    n1, n2, nr = len(c1), len(c2), len(t3_nodes)
    elo1, slope, ratio, delta = [], [], [], []
    invalid = 0
    for start in range(0, samples, 2000):
        m = min(2000, samples - start)
        p1 = c1[rng_c1.integers(0, n1, size=(m, n1), endpoint=False)].mean(axis=1)
        p2 = c2[rng_c2.integers(0, n2, size=(m, n2), endpoint=False)].mean(axis=1)
        idx = rng_e1.integers(0, nr, size=(m, nr), endpoint=False)
        rr = t3_nodes[idx].sum(axis=1) / curriculum_nodes[idx].sum(axis=1)
        valid = (p1 > 0) & (p1 < 1) & (p2 > 0) & (p2 < 1) & np.isfinite(rr) & (rr > 0)
        invalid += int((~valid).sum())
        if not np.any(valid):
            continue
        p1, p2, rr = p1[valid], p2[valid], rr[valid]
        e1 = 400.0 * np.log10(p1 / (1.0 - p1))
        e2 = 400.0 * np.log10(p2 / (1.0 - p2))
        elo1.append(e1); slope.append(e2); ratio.append(rr)
        delta.append(e1 + np.log2(rr) * e2)
    if not elo1:
        raise ValueError("E2 bootstrap has no valid replicates")
    arrays = [np.concatenate(values) for values in (elo1, slope, ratio, delta)]
    ci = lambda values: [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]
    return {
        "samples": samples,
        "seed": seed,
        "prng": "NumPy PCG64",
        "subflow_derivation": "SeedSequence(seed).spawn(3)",
        "subflow_order": ["C1", "C2", "E1"],
        "invalid_replicates": invalid,
        "invalid_fraction": invalid / samples,
        "valid_replicates": int(arrays[0].size),
        "elo_c1_ci95": ci(arrays[0]),
        "slope_c2_ci95": ci(arrays[1]),
        "r_nodes_ci95": ci(arrays[2]),
        "delta_info_ci95": ci(arrays[3]),
    }


base.bootstrap = bootstrap

if __name__ == "__main__":
    raise SystemExit(base.main())
