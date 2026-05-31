#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Pearson correlation between a PatternEmbedMLP (.pt PyTorch) and a
reference NNUE on a sample of positions from a JNNW dataset.

Python-side counterpart to `pattern_eval_correlation.py` : since the
embedding-MLP prototype lives in PyTorch (not the C++ JPAT format),
we evaluate it in-process here and compare to the C++ NNUE eval of
the same positions (via `--rewrite-scores-with-nnue`).

Usage:
    python3 tools/pattern_embed_correlation.py \\
        --embed path.pt --ref v7-nnue.bin --data sample.jnnw \\
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
import torch

sys.path.insert(0, str(Path(__file__).parent))
from train_pattern import (PATTERN_SETS, load_jnnw, pattern_indices,  # noqa: E402
                           material_diffs)
from train_pattern_embed import PatternEmbedMLP  # noqa: E402


RECORD_SZ = 38
HEADER_SZ = 8
SCORE_OFFSET_IN_RECORD = 33


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


def eval_embed_on_jnnw(model: PatternEmbedMLP, patterns: list[list[int]],
                       sample: Path) -> np.ndarray:
    bbs, stm, _score, _wdl = load_jnnw(sample, 0)
    pidx = pattern_indices(bbs, patterns, base=model.base)
    mat_diff, king_diff = material_diffs(bbs)
    # White-POV sign-flip (same as training)
    mat_diff[stm == 1] *= -1
    king_diff[stm == 1] *= -1
    model.eval()
    with torch.no_grad():
        out = model(torch.from_numpy(pidx),
                    torch.from_numpy(mat_diff),
                    torch.from_numpy(king_diff))
    # Flip back to side-to-move POV to match C++ rewrite-scores output
    scores = out.numpy().astype(np.float64)
    scores[stm == 1] *= -1
    return scores


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--embed", required=True, type=Path)
    p.add_argument("--ref",   required=True, type=Path)
    p.add_argument("--data",  required=True, type=Path)
    p.add_argument("--n",     type=int, default=1000)
    p.add_argument("--seed",  type=int, default=42)
    p.add_argument("--jass",  type=Path, default=Path("./build/jass"))
    args = p.parse_args(argv)

    ckpt = torch.load(args.embed, map_location="cpu", weights_only=False)
    cfg = ckpt["config"]
    patterns = PATTERN_SETS[cfg["patterns_name"]]
    model = PatternEmbedMLP(patterns, base=cfg["base"],
                            embed_dim=cfg["embed_dim"],
                            mlp_hidden=cfg["mlp_hidden"])
    model.load_state_dict(ckpt["state_dict"])

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        sample = td_path / "sample.jnnw"
        scored_ref = td_path / "scored-ref.jnnw"

        n_used = subsample_jnnw(args.data, sample, args.n, args.seed)
        print(f"subsampled {n_used} records from {args.data}", flush=True)

        subprocess.run(
            [str(args.jass), "--rewrite-scores-with-nnue",
             str(sample), str(scored_ref), "--nnue", str(args.ref)],
            check=True, capture_output=True,
        )
        sr = read_scores(scored_ref).astype(np.float64)
        sp = eval_embed_on_jnnw(model, patterns, sample)

    if sp.std() == 0 or sr.std() == 0:
        print(f"degenerate: one of the score arrays is constant "
              f"(embed_std={sp.std():.3f}, ref_std={sr.std():.3f})")
        print("pearson_r = nan")
        return 0

    r = float(np.corrcoef(sp, sr)[0, 1])
    print(f"pearson_r = {r:+.4f}  (n={n_used})")
    print(f"embed : range=[{sp.min():.0f}, {sp.max():.0f}]  "
          f"mean={sp.mean():.1f}  std={sp.std():.1f}")
    print(f"ref   : range=[{sr.min():.0f}, {sr.max():.0f}]  "
          f"mean={sr.mean():.1f}  std={sr.std():.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
