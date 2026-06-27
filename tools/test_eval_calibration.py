#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Unit test for eval_calibration.py — the K-fitter must recover a known K from
# synthetic outcomes, and the JNNW reader must round-trip score/wdl.
import math
import os
import random
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_calibration import fit_K, _read_scored, reliability, REC  # noqa: E402


def test_fit_recovers_K():
    random.seed(42)
    K_true = 120.0
    scores, ys = [], []
    for _ in range(40000):
        x = random.uniform(-600, 600)
        p = 1.0 / (1.0 + math.exp(-x / K_true))
        scores.append(x)
        ys.append(1.0 if random.random() < p else 0.0)
    K = fit_K(scores, ys)
    assert abs(K - K_true) < 12.0, f"fit_K recovered {K:.1f}, expected ~{K_true}"
    # well-calibrated synthetic data -> low ECE at the fitted K
    ece, _ = reliability(scores, ys, K)
    assert ece < 0.03, f"ECE too high for synthetic well-calibrated data: {ece:.4f}"
    print(f"[1] fit_K OK : recovered K={K:.1f} (true {K_true}), ECE={ece:.4f}")


def test_read_scored_roundtrip():
    recs = [
        (0b111, 0, 0b111000, 0, 0, 250, 1),    # win,  6 pieces
        (0b1, 0, 0b10, 0, 1, -180, -1),         # loss, 2 pieces
        (0b11, 0, 0b1100, 0, 0, 5, 0),          # draw -> dropped
    ]
    body = b"".join(REC.pack(*r) for r in recs)
    fd, path = tempfile.mkstemp(suffix=".jnnw")
    os.write(fd, b"JNNW" + struct.pack("<I", len(recs)) + body)
    os.close(fd)
    try:
        scores, ys, pcs = _read_scored(path)
    finally:
        os.unlink(path)
    assert scores == [250.0, -180.0], scores      # draw dropped
    assert ys == [1.0, 0.0], ys
    assert pcs == [6, 2], pcs
    print("[2] _read_scored OK (score/wdl/piece-count, draws dropped)")


if __name__ == "__main__":
    test_fit_recovers_K()
    test_read_scored_roundtrip()
    print("ALL eval_calibration TESTS PASSED")
