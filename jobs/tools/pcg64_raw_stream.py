#!/usr/bin/env python3
"""Write an infinite little-endian uint64 stream from NumPy PCG64(seed)."""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--chunk", type=int, default=65536)
    args = ap.parse_args()
    if args.seed <= 0 or args.chunk <= 0:
        raise ValueError("invalid frozen PCG64 stream arguments")
    rng = np.random.Generator(np.random.PCG64(args.seed))
    out = sys.stdout.buffer
    try:
        while True:
            raw = rng.bit_generator.random_raw(args.chunk).astype("<u8", copy=False).tobytes(order="C")
            out.write(raw)
            out.flush()
    except BrokenPipeError:
        try:
            out.close()
        except BrokenPipeError:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
