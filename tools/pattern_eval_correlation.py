#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
H5 — Pearson correlation between a pattern network and a reference
network (typically v7) on a sample of positions from a JNNW dataset.

Provides a non-binary progress metric for the self-play loop : even if
the pattern net loses 0/54 vs v6, a rising Pearson r vs v7 indicates
the pattern eval is *qualitatively* converging toward something useful
(or not).

Implementation : reuses the C++ `--rewrite-scores-with-nnue` mode
twice (once with pattern, once with ref) on a subsampled JNNW, then
parses the two output files for the int32 score field and computes
Pearson r.

Usage:
    python3 tools/pattern_eval_correlation.py \\
        --pattern path.jpat --ref v7-nnue.bin --data sample.jnnw \\
        [--n 1000] [--seed 42] [--jass ./build/jass]
"""
from __future__ import annotations

import argparse
import random
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


RECORD_SZ = 38
HEADER_SZ = 8
SCORE_OFFSET_IN_RECORD = 33  # 32 (bbs) + 1 (stm) = 33; int32 score follows


def subsample_jnnw(src: Path, dst: Path, n: int, seed: int) -> int:
    raw = src.read_bytes()
    assert raw[:4] == b"JNNW", f"{src}: bad magic"
    total = struct.unpack_from("<I", raw, 4)[0]
    n_use = min(n, total)
    rng = random.Random(seed)
    idx = sorted(rng.sample(range(total), n_use))
    chunks = [raw[HEADER_SZ + i * RECORD_SZ:HEADER_SZ + (i + 1) * RECORD_SZ]
              for i in idx]
    with dst.open("wb") as f:
        f.write(b"JNNW")
        f.write(struct.pack("<I", n_use))
        for c in chunks:
            f.write(c)
    return n_use


def read_scores(p: Path) -> np.ndarray:
    raw = p.read_bytes()
    assert raw[:4] == b"JNNW", f"{p}: bad magic"
    cnt = struct.unpack_from("<I", raw, 4)[0]
    out = np.empty(cnt, dtype=np.int32)
    for i in range(cnt):
        off = HEADER_SZ + i * RECORD_SZ + SCORE_OFFSET_IN_RECORD
        out[i] = struct.unpack_from("<i", raw, off)[0]
    return out


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pattern", required=True, type=Path)
    p.add_argument("--ref",     required=True, type=Path,
                   help="reference NNUE (e.g. v7 quantised .bin)")
    p.add_argument("--data",    required=True, type=Path,
                   help="JNNW dataset to subsample positions from")
    p.add_argument("--n",       type=int, default=1000)
    p.add_argument("--seed",    type=int, default=42)
    p.add_argument("--jass",    type=Path, default=Path("./build/jass"))
    args = p.parse_args(argv)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        sample = td_path / "sample.jnnw"
        scored_pat = td_path / "scored-pat.jnnw"
        scored_ref = td_path / "scored-ref.jnnw"

        n_used = subsample_jnnw(args.data, sample, args.n, args.seed)
        print(f"subsampled {n_used} records from {args.data}", flush=True)

        for net, out in [(args.pattern, scored_pat), (args.ref, scored_ref)]:
            subprocess.run(
                [str(args.jass), "--rewrite-scores-with-nnue",
                 str(sample), str(out), "--nnue", str(net)],
                check=True, capture_output=True,
            )

        sp = read_scores(scored_pat).astype(np.float64)
        sr = read_scores(scored_ref).astype(np.float64)

    if sp.std() == 0 or sr.std() == 0:
        print(f"degenerate: one of the score arrays is constant "
              f"(pattern_std={sp.std():.3f}, ref_std={sr.std():.3f})")
        print("pearson_r = nan")
        return 0

    r = float(np.corrcoef(sp, sr)[0, 1])
    print(f"pearson_r = {r:+.4f}  (n={n_used})")
    print(f"pattern : range=[{sp.min():.0f}, {sp.max():.0f}]  "
          f"mean={sp.mean():.1f}  std={sp.std():.1f}")
    print(f"ref     : range=[{sr.min():.0f}, {sr.max():.0f}]  "
          f"mean={sr.mean():.1f}  std={sr.std():.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
