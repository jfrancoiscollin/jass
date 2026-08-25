#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

MODULE = Path(__file__).resolve().parents[1] / "tools" / "tb_frontier_pairwise.py"
spec = importlib.util.spec_from_file_location("tb_frontier_pairwise", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def m(idx: int, pid: int, color: int, utility: int, from_sq: int, to_sq: int):
    return mod.RowMeta(
        row_index=idx,
        parent_id=pid,
        fingerprint=f"p{pid}",
        parent_stm=color,
        from_sq=from_sq,
        to_sq=to_sq,
        num_captures=1,
        promotes=0,
        moving_king=0,
        captured_kings=0,
        utility=utility,
        child_tb_wdl_stm=-utility,
    )


def test_pair_direction_and_metric() -> None:
    meta = [m(0, 0, 0, 1, 10, 20), m(1, 0, 0, 0, 11, 21), m(2, 0, 0, -1, 12, 22)]
    assert mod.informative_pairs([0, 1, 2], meta) == [(0, 1), (0, 2), (1, 2)]
    good = np.asarray([3.0, 2.0, 1.0])
    bad = -good
    assert mod.parent_metric([0, 1, 2], meta, good) == (1.0, 1.0, 0.0)
    pa, hit, regret = mod.parent_metric([0, 1, 2], meta, bad)
    assert pa == 0.0 and hit == 0.0 and regret == 2.0


def test_pairwise_fit_learns_separable_signal() -> None:
    # A one-dimensional exact preference repeated with small nuisance columns.
    rng = np.random.default_rng(7)
    signal = np.ones((200, 1), dtype=np.float64)
    nuisance = rng.normal(scale=0.05, size=(200, 4))
    d = np.concatenate([signal, nuisance], axis=1)
    w, receipt = mod.fit_pairwise(d, l2=1e-3, maxiter=200, gtol=1e-7)
    assert receipt["success"]
    assert w[0] > 0
    assert float(np.mean((d @ w) > 0.0)) > 0.99


def test_split_is_parent_stable() -> None:
    a = mod.split_is_holdout("abc", 2026082801, 5)
    assert a == mod.split_is_holdout("abc", 2026082801, 5)
    # Different fingerprints must be independently hashed; this checks the
    # function does not accidentally depend on row index/global ordering.
    vals = {mod.split_is_holdout(f"p{i}", 2026082801, 5) for i in range(100)}
    assert vals == {False, True}


if __name__ == "__main__":
    test_pair_direction_and_metric()
    test_pairwise_fit_learns_separable_signal()
    test_split_is_parent_stable()
    print("TB_FRONTIER_PAIRWISE_TESTS_OK")
