#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""Compute TD-leaf(λ) targets from `jass --gen-tdleaf` output.

`jass --gen-tdleaf` plays self-play games with a pattern eval and writes, per
move, the LEAF position of the search PV plus its value V_leaf (white-POV) in
the score field of a JNNW file, grouped by game via a `<out>.games` sidecar
(`<n_records> <result>` per game, result ∈ {-1,0,1} white-POV).

We turn the per-game value sequence V_0..V_{T-1} into the forward-view
λ-return target for each leaf:

    δ_j   = V_{j+1} - V_j           (j < T-1)
    δ_{T-1} = Z - V_{T-1}           (Z = result · terminal_cp, the game outcome)
    S_t   = δ_t + λ·S_{t+1}         (computed backward; S_{T-1} = δ_{T-1})
    G_t   = V_t + S_t               (the TD-leaf λ-return target, white-POV)

The output is a JNNW of the SAME leaf positions with `score` = G_t converted
to STM-POV (the convention train.py expects). Feed it to train.py with the
aligned handcrafted skeleton to re-fit the pattern on the bootstrapped
targets — iterating this is TD-leaf(λ).
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

HEADER_SZ = 8
RECORD_SZ = 38   # QQQQ(32) + stm(1) + score int32(4) + wdl(1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--leaves", required=True, type=Path,
                    help="JNNW from --gen-tdleaf (score = V_leaf white-POV)")
    ap.add_argument("--games", required=True, type=Path,
                    help="<leaves>.games sidecar (n_records result per game)")
    ap.add_argument("--out", required=True, type=Path,
                    help="output JNNW (score = λ-return target, STM-POV)")
    ap.add_argument("--lam", type=float, default=0.7,
                    help="TD-λ decay (0=TD(0) bootstrap, 1=Monte-Carlo)")
    ap.add_argument("--terminal-cp", type=float, default=5000.0,
                    help="cp value of a win (loss = -this, draw = 0)")
    args = ap.parse_args(argv)

    raw = args.leaves.read_bytes()
    assert raw[:4] == b"JNNW", f"{args.leaves}: bad magic"
    n_total = struct.unpack_from("<I", raw, 4)[0]
    assert HEADER_SZ + n_total * RECORD_SZ <= len(raw), "truncated leaves file"

    games = []
    for line in args.games.read_text().split("\n"):
        line = line.strip()
        if not line:
            continue
        n_str, res_str = line.split()
        games.append((int(n_str), int(res_str)))
    assert sum(n for n, _ in games) == n_total, (
        f"games index sum {sum(n for n,_ in games)} != {n_total} records")

    lam = args.lam
    out = bytearray()
    out += b"JNNW"
    out += struct.pack("<I", n_total)

    idx = 0   # record index
    for n, result in games:
        # gather V_white for this game
        V = [0.0] * n
        recs = []
        for k in range(n):
            off = HEADER_SZ + (idx + k) * RECORD_SZ
            rec = raw[off:off + RECORD_SZ]
            v_white = struct.unpack_from("<i", rec, 33)[0]
            V[k] = float(v_white)
            recs.append(rec)
        Z = result * args.terminal_cp
        # backward λ-return
        S_next = 0.0
        targets = [0.0] * n
        for t in range(n - 1, -1, -1):
            v_next = Z if t == n - 1 else V[t + 1]
            delta = v_next - V[t]
            S = delta + (lam * S_next if t < n - 1 else 0.0)
            targets[t] = V[t] + S
            S_next = S
        # write records with score = target in STM-POV
        for k in range(n):
            rec = bytearray(recs[k])
            stm = rec[32]                      # 0=white, 1=black
            g_white = targets[k]
            g_stm = g_white if stm == 0 else -g_white
            struct.pack_into("<i", rec, 33, int(round(g_stm)))
            out += rec
        idx += n

    args.out.write_bytes(out)
    print(f"wrote {n_total} TD-leaf targets → {args.out} "
          f"(λ={lam}, terminal=±{args.terminal_cp:.0f}cp, {len(games)} games)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
