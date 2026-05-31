#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Export a PatternEmbedMLP PyTorch checkpoint (`.pt`) to JPAT v8 format
for C++ inference (cf. src/pattern_network.cpp, paradigm shift A).

Layout (cf. pattern_network.hpp v8 doc) :
   [0..4)    magic = "JPAT"
   [4..8)    uint32 version = 8
   [8..12)   uint32 num_patterns
   [12..16)  int32  bias
   [16..20)  int32  man_value
   [20..24)  int32  king_value
   [24..25)  uint8  encoding_base (3)
   [25..29)  int32  balance      = 0
   [29..229) int32[50] king_pst  = 0
   [229..233) int32 bias_eg      = 0
   [233..237) int32 man_value_eg = 0
   [237..241) int32 king_value_eg= 0
   [241..245) int32 balance_eg   = 0
   [245..445) int32[50] king_pst_eg = 0
   [445..449) int32 mobility_mg = 0
   [449..453) int32 mobility_eg = 0
   [453..454) uint8 mlp_hidden  = 0   (v7 MLP head OFF for v8 files)
   [454..455) uint8 embed_dim
   [455..456) uint8 v8_mlp_hidden
   float32[N × embed_dim × v8_mlp_hidden] v8_mlp_w1
   float32[v8_mlp_hidden]                 v8_mlp_b1
   float32[v8_mlp_hidden]                 v8_mlp_w2
   float32                                v8_mlp_b2
   For each pattern :
     uint8  K
     uint8[K] squares
     float32[base^K × embed_dim] embedding_table

Usage :
   python3 tools/embed_pt_to_jpat.py --in model.pt --out model.jpat
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from train_pattern import PATTERN_SETS  # noqa: E402
from train_pattern_embed import PatternEmbedMLP  # noqa: E402


def export(model: PatternEmbedMLP, patterns: list[list[int]],
           out_path: Path, output_scale: float = 1.0,
           stm_flip: int = 1) -> int:
    n = len(patterns)
    ed = model.embed_dim
    h  = model.mlp_hidden
    base = model.base

    # Skeleton scalars (cast to int32 cp). The Python model uses floats,
    # the C++ skeleton uses int32. Round to nearest cp. `output_scale`
    # rescales the whole eval (skeleton + MLP) without retraining ;
    # useful when the trained model is overconfident in absolute scale
    # but rank-correlates well with the reference (typical calibration
    # mismatch between MSE-trained eval and search-quality eval).
    bias       = int(round(model.bias.item()       * output_scale))
    man_value  = int(round(model.man_value.item()  * output_scale))
    king_value = int(round(model.king_value.item() * output_scale))

    # MLP weights, float32, contiguous.
    # Python : nn.Linear(in_dim → h) stores weight as (h, in_dim) ;
    # the JPAT v8 on-disk layout expects row-major [in_dim, h] (cf. C++
    # eval loop `concat[ii] * v8_mlp_w1_[ii * h + hi]`). So we transpose
    # Python's (h, in_dim) to (in_dim, h) before writing.
    w1 = model.mlp[0].weight.detach().cpu().numpy().astype(np.float32)  # (h, in_dim)
    b1 = model.mlp[0].bias.detach().cpu().numpy().astype(np.float32)    # (h,)
    w2 = model.mlp[2].weight.detach().cpu().numpy().astype(np.float32)  # (1, h)
    b2 = float(model.mlp[2].bias.detach().cpu().item())                  # scalar
    # output_scale propagates to the MLP via the final linear layer
    # (w2 and b2 are linear at output ; ReLU + earlier layers stay
    # unchanged). Embedding tables also stay unchanged.
    w2 = w2 * output_scale
    b2 = b2 * output_scale
    in_dim = n * ed
    assert w1.shape == (h, in_dim), f"w1 shape {w1.shape} vs ({h},{in_dim})"
    assert w2.shape == (1, h),      f"w2 shape {w2.shape} vs (1,{h})"
    w1_t = np.ascontiguousarray(w1.T)   # (in_dim, h)
    w2_flat = np.ascontiguousarray(w2.reshape(h))

    # Per-pattern embedding tables : (base^K, embed_dim) row-major.
    emb_tables = []
    for pi, p in enumerate(patterns):
        e = model.embeddings[pi].weight.detach().cpu().numpy().astype(np.float32)
        assert e.shape == (base ** len(p), ed), \
            f"pattern {pi} embed shape {e.shape}"
        emb_tables.append(np.ascontiguousarray(e))

    with out_path.open("wb") as f:
        f.write(b"JPAT")
        f.write(struct.pack("<I", 8))           # version
        f.write(struct.pack("<I", n))           # num_patterns
        f.write(struct.pack("<i", bias))
        f.write(struct.pack("<i", man_value))
        f.write(struct.pack("<i", king_value))
        f.write(struct.pack("<B", base))        # encoding_base
        # v4 : balance + king_pst[50]  (zeros)
        f.write(struct.pack("<i", 0))
        f.write(np.zeros(50, dtype=np.int32).tobytes())
        # v5 : bias_eg/man_eg/king_eg/balance_eg/king_pst_eg[50]  (zeros)
        f.write(struct.pack("<iiii", 0, 0, 0, 0))
        f.write(np.zeros(50, dtype=np.int32).tobytes())
        # v6 : mobility_mg/eg  (zeros)
        f.write(struct.pack("<ii", 0, 0))
        # v7 : mlp_hidden = 0  (v7 head OFF for v8 files)
        f.write(struct.pack("<B", 0))
        # v8 : embed_dim, v8_mlp_hidden, v8_stm_flip, MLP weights
        f.write(struct.pack("<BBB", ed, h, stm_flip))
        f.write(w1_t.tobytes())
        f.write(b1.tobytes())
        f.write(w2_flat.tobytes())
        f.write(struct.pack("<f", b2))
        # patterns : K + squares + float32 embeddings (no int32 weights)
        for pi, p in enumerate(patterns):
            f.write(struct.pack("<B", len(p)))
            f.write(bytes(p))
            f.write(emb_tables[pi].tobytes())

    return out_path.stat().st_size


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in",  dest="in_path",  required=True, type=Path)
    ap.add_argument("--out", dest="out_path", required=True, type=Path)
    ap.add_argument("--output-scale", type=float, default=1.0,
                    help="multiplicative scale applied to the whole eval "
                         "(skeleton + MLP). Use e.g. 0.7 to dampen an "
                         "overconfident eval without retraining.")
    args = ap.parse_args(argv)

    ckpt = torch.load(args.in_path, map_location="cpu", weights_only=False)
    cfg = ckpt["config"]
    patterns = PATTERN_SETS[cfg["patterns_name"]]
    model = PatternEmbedMLP(patterns, base=cfg["base"],
                            embed_dim=cfg["embed_dim"],
                            mlp_hidden=cfg["mlp_hidden"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    stm_flip = 1 if cfg.get("stm_flip", True) else 0
    sz = export(model, patterns, args.out_path,
                output_scale=args.output_scale, stm_flip=stm_flip)
    print(f"wrote {args.out_path} ({sz} bytes) "
          f"v8 patterns={cfg['patterns_name']} base={cfg['base']} "
          f"embed_dim={cfg['embed_dim']} mlp_hidden={cfg['mlp_hidden']} "
          f"bias={int(round(model.bias.item()))} "
          f"man={int(round(model.man_value.item()))} "
          f"king={int(round(model.king_value.item()))}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
