#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Smoke test for the Day 2 training pipeline.

1. Synthesizes a tiny JNNW dataset (100 records) with random bitboards
   and WDL labels correlated with a simple "more pieces wins" rule.
2. Loads it via master_loader.
3. Extracts pattern indices.
4. Trains 50 iters L-BFGS.
5. Verifies output PJTW file format.

Run : python3 pattern_jass/tools/smoke_test.py
Exit code 0 if all assertions pass, 1 otherwise.
"""

import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import master_loader
import patterns


def make_synthetic_jnnw(path: Path, n: int = 100, seed: int = 42) -> None:
    """Generate a tiny JNNW file with random men bitboards and
    'more_pieces_wins' WDL labels."""
    rng = np.random.default_rng(seed)
    records = bytearray()
    records += b'JNNW'
    records += struct.pack('<I', n)

    # 50-square board, men only. Random fraction of squares filled.
    for _ in range(n):
        # Place 5..15 black men and 5..15 white men on random squares.
        n_black = int(rng.integers(5, 16))
        n_white = int(rng.integers(5, 16))
        all_sqs = list(range(50))
        rng.shuffle(all_sqs)
        black_sqs = all_sqs[:n_black]
        white_sqs = all_sqs[n_black:n_black + n_white]
        wm = sum(1 << s for s in white_sqs)
        bm = sum(1 << s for s in black_sqs)
        wk, bk = 0, 0

        # STM : 0 = white-to-move, 1 = black-to-move.
        stm = int(rng.integers(0, 2))
        score = int(rng.integers(-200, 201))
        # WDL : +1 if STM has more men, -1 if less, 0 if equal.
        stm_pc = n_white if stm == 0 else n_black
        opp_pc = n_black if stm == 0 else n_white
        if   stm_pc > opp_pc: wdl =  1
        elif stm_pc < opp_pc: wdl = -1
        else:                 wdl =  0

        # JNNW record : 4×uint64 + uint8 stm + int32 score + int8 wdl (signed!)
        records += struct.pack('<QQQQBib',
                               wm, wk, bm, bk, stm, score, wdl)
    path.write_bytes(bytes(records))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='pattern_jass_smoke_') as tmp:
        tmp = Path(tmp)
        jnnw = tmp / 'mini.jnnw'
        weights = tmp / 'mini.pjtw'

        print('=== synth dataset ===')
        make_synthetic_jnnw(jnnw, n=200)
        ds = master_loader.load(jnnw)
        assert ds.n_records == 200, f'expected 200 records, got {ds.n_records}'
        # WDL ∈ {-1, 0, +1} only.
        assert set(np.unique(ds.wdl).tolist()) <= {-1, 0, 1}
        # STM ∈ {0, 1}.
        assert set(np.unique(ds.stm).tolist()) <= {0, 1}
        print(f'  loaded {ds.n_records} records OK')

        print('=== pattern extract ===')
        idx = patterns.extract_indices(ds.black_men, ds.white_men)
        assert idx.shape == (200, 8)
        # All indices in bounds.
        assert idx.min() >= 0
        assert idx.max() < patterns.BUCKETS_PER_PATTERN
        print(f'  shape {idx.shape}, range [{idx.min()},{idx.max()}]  OK')

        print('=== train ===')
        train_py = Path(__file__).resolve().parent / 'train.py'
        r = subprocess.run(
            ['python3', str(train_py),
             '--data', str(jnnw),
             '--out',  str(weights),
             '--max-iter', '50',
             '--scale', '1000'],
            capture_output=True, text=True)
        print(r.stdout.rstrip())
        if r.returncode != 0:
            print('TRAIN FAILED :', r.stderr.rstrip(), file=sys.stderr)
            return 1

        print('=== verify weights file ===')
        data = weights.read_bytes()
        m, v, n, s = struct.unpack_from('<IIII', data, 0)
        assert m == 0x57544A50, f'bad magic 0x{m:08X}'
        assert v == 1, f'bad version {v}'
        assert n == patterns.TOTAL_BUCKETS, f'bad count {n}'
        assert s == 1000, f'bad scale {s}'
        expected_size = 16 + 4 * n
        assert len(data) == expected_size, \
            f'size {len(data)} != expected {expected_size}'
        print(f'  magic OK, count={n}, scale={s}, size={len(data)} OK')

    print('SMOKE OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
