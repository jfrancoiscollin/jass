#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""Generator (single source of truth) for the v4 ENRICHED pattern geometry.

10x10 FMJD draughts, 50 dark squares. Physical mapping of square n (1..50):
    row  = (n-1)//5                         (0=top .. 9=bottom)
    idx  = (n-1)%5                           (0..4 within the row)
    file = 2*idx + (1 if row even else 0)    (dark squares only)

v3 had 8 VERTICAL bands only (one orientation). v4 adds the orientations a
draughts board actually uses — true physical DIAGONALS (both directions),
HORIZONTAL blocks (advancement), and compact SQUARE blocks — so the additive
pattern class can fit structures the vertical-only set misses.

Run with `--emit` to rewrite the PATTERNS arrays in pattern.hpp and patterns.py
(single source → no hand-transcription drift). Default just validates+prints.
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

SIZE = 12

def nof(row, file):
    if not (0 <= row <= 9 and 0 <= file <= 9):
        return None
    if (file % 2) != (1 if row % 2 == 0 else 0):
        return None
    idx = (file - (1 if row % 2 == 0 else 0)) // 2
    return row * 5 + idx + 1 if 0 <= idx <= 4 else None

def coord(n):
    row, idx = (n - 1) // 5, (n - 1) % 5
    return row, 2 * idx + (1 if row % 2 == 0 else 0)

def _line(n, dr, df, length):
    r, f = coord(n); out = []
    for _ in range(length):
        m = nof(r, f)
        if m is None:
            return None
        out.append(m); r += dr; f += df
    return out

def _band(n, dr, df, perp, length):
    l1 = _line(n, dr, df, length)
    if l1 is None:
        return None
    r0, f0 = coord(n); n2 = nof(r0 + perp[0], f0 + perp[1])
    if n2 is None:
        return None
    l2 = _line(n2, dr, df, length)
    if l2 is None or len(set(l1 + l2)) != 2 * length:
        return None
    return sorted(l1 + l2)

def vband(r0, c0):  # 2 idx-cols x 6 rows (v3 style)
    sqs = [r * 5 + c + 1 for r in range(r0, r0 + 6) for c in (c0, c0 + 1)]
    return sorted(sqs) if r0 + 5 <= 9 and c0 + 1 <= 4 else None

def hblock(r0, c0):  # 3 rows x 4 idx
    sqs = [r * 5 + c + 1 for r in range(r0, r0 + 3) for c in range(c0, c0 + 4)]
    return sorted(sqs) if r0 + 2 <= 9 and c0 + 3 <= 4 else None

def sblock(r0, c0):  # 4 rows x 3 idx
    sqs = [r * 5 + c + 1 for r in range(r0, r0 + 4) for c in range(c0, c0 + 3)]
    return sorted(sqs) if r0 + 3 <= 9 and c0 + 2 <= 4 else None

def dband(n):  # true physical down-right diagonal band (2 parallel x 6)
    return _band(n, 1, 1, (0, 2), 6)

def aband(n):  # true physical anti-diagonal band
    return _band(n, 1, -1, (0, -2), 6)

def _diag_block(n, df, perp):  # 3 parallel diagonals x length 4 = 12 squares
    parts = []
    r0, f0 = coord(n)
    for k in range(3):
        start = nof(r0 + perp[0] * k, f0 + perp[1] * k)
        if start is None:
            return None
        seg = _line(start, 1, df, 4)
        if seg is None:
            return None
        parts += seg
    return sorted(parts) if len(set(parts)) == 12 else None

def dblock(n):   # down-right diagonal block (3 wide x 4 long)
    return _diag_block(n, 1, (0, 2))

def ablock(n):   # anti-diagonal block
    return _diag_block(n, -1, (0, -2))


def build():
    """The curated v4 ENRICHED set (32 patterns), all orientations: 8 vertical
    bands (v3) + 7 down-right diagonals + 8 anti-diagonals + 5 horizontal + 4
    square blocks. This is the proven sweet spot (0154: 0.75 vs hc). The v5
    diagonal-block addition (32->40) regressed and is reverted (see below)."""
    pats: list[tuple[list[int], str]] = []
    # V : 8 v3 vertical bands (top rows 0-5, bottom rows 4-9 ; 4 col-shifts each)
    for half, r0 in (("top", 0), ("bot", 4)):
        for c0 in range(4):
            pats.append((vband(r0, c0), f"v_{half}_{c0}"))
    # D : down-right diagonal bands (all distinct starts)
    seen = set()
    for s in range(1, 51):
        p = dband(s)
        if p and tuple(p) not in seen:
            seen.add(tuple(p)); pats.append((p, f"diag_{len(seen)-1}"))
    # A : anti-diagonal bands
    seen = set()
    for s in range(1, 51):
        p = aband(s)
        if p and tuple(p) not in seen:
            seen.add(tuple(p)); pats.append((p, f"anti_{len(seen)-1}"))
    # H : horizontal 3x4 blocks, spread over the board (advancement)
    for i, (r0, c0) in enumerate([(0, 0), (2, 1), (4, 0), (5, 1), (7, 0)]):
        pats.append((hblock(r0, c0), f"horiz_{i}"))
    # S : compact 4x3 square blocks
    for i, (r0, c0) in enumerate([(0, 1), (3, 0), (3, 2), (6, 1)]):
        pats.append((sblock(r0, c0), f"sq_{i}"))
    # NB: the v5 diagonal-block addition (db/ab, 32->40) regressed play badly
    # (0.75 -> 0.44 vs hc on the same clean 1.4M) and was REVERTED. The dblock/
    # ablock helpers are kept for a future, properly-attributed re-test.
    # validate (12 distinct squares, in 1..50, and globally no duplicate pattern)
    allseen = set()
    for sqs, name in pats:
        assert sqs and len(sqs) == SIZE and len(set(sqs)) == SIZE \
            and all(1 <= x <= 50 for x in sqs), (name, sqs)
        t = tuple(sqs)
        assert t not in allseen, ("duplicate pattern", name)
        allseen.add(t)
    return pats


def emit_hpp(pats):
    lines = []
    for sqs, name in pats:
        body = ", ".join(f"{x:2d}" for x in sqs)
        lines.append(f'    {{{{{body}}}, "{name}"}},')
    return "\n".join(lines)

def emit_py(pats):
    plines, nlines = [], []
    for sqs, name in pats:
        body = ", ".join(f"{x:2d}" for x in sqs)
        plines.append(f"    [{body}],   # {name}")
        nlines.append(f'"{name}"')
    names = ", ".join(nlines)
    return "\n".join(plines), names


def rewrite(path: Path, start: str, end: str, new: str):
    txt = path.read_text()
    pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pat.search(txt):
        sys.exit(f"markers not found in {path}")
    path.write_text(pat.sub(start + "\n" + new + "\n" + end, txt))
    print(f"rewrote {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true", help="rewrite pattern.hpp + patterns.py")
    args = ap.parse_args()
    pats = build()
    n = len(pats)
    by = {}
    for _, nm in pats:
        by[nm.split("_")[0]] = by.get(nm.split("_")[0], 0) + 1
    print(f"v4 enriched set : {n} patterns  {by}")
    print(f"TOTAL_BUCKETS = {n} * 531441 = {n * 531441}")
    for sqs, name in pats:
        print(f"  {name:12s} {sqs}")
    if args.emit:
        root = Path(__file__).resolve().parents[1]
        rewrite(root / "src" / "pattern.hpp",
                "// @GEN-PATTERNS-BEGIN", "// @GEN-PATTERNS-END", emit_hpp(pats))
        body, names = emit_py(pats)
        rewrite(root / "tools" / "patterns.py",
                "# @GEN-PATTERNS-BEGIN", "# @GEN-PATTERNS-END", body)
        rewrite(root / "tools" / "patterns.py",
                "# @GEN-NAMES-BEGIN", "# @GEN-NAMES-END",
                f"PATTERN_NAMES = [{names}]")
        print(f"\nNUM_PATTERNS is now {n} — update pattern.hpp NUM_PATTERNS and the "
              f"run_tests.cpp guards (NUM_PATTERNS={n}, TOTAL_BUCKETS={n*531441}).")


if __name__ == "__main__":
    raise SystemExit(main())
