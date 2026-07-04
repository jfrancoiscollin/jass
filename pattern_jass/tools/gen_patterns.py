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


def _distinct(fns, cap=99):
    """All distinct 12-square patterns from the given (fn, tag) generators,
    swept over every start square; deduped globally. `cap` limits the total."""
    out, seen = [], set()
    for fn, tag in fns:
        k = 0
        for s in range(1, 51):
            p = fn(s)
            if p and tuple(p) not in seen:
                seen.add(tuple(p)); out.append((p, f"{tag}_{k}")); k += 1
                if len(out) >= cap:
                    return out
    return out


def build_v6():
    """piste 1 — DIAGONAL-DENSE : the board is a diagonal game ; replace the
    (misaligned) vertical bands by a dense set aligned on the movement axes —
    every distinct down-right / anti-diagonal BAND and 3-wide BLOCK, plus a few
    horizontal/square blocks for full coverage. Tests whether aligning + densi-
    fying the geometry (Scan's mechanism) beats v4's vertical bands."""
    pats = _distinct([(dband, "diag"), (aband, "anti"),
                      (dblock, "db"),  (ablock, "ab")], cap=44)
    for i, (r0, c0) in enumerate([(0, 0), (4, 1), (7, 0)]):
        pats.append((hblock(r0, c0), f"horiz_{i}"))
    for i, (r0, c0) in enumerate([(3, 0)]):
        pats.append((sblock(r0, c0), f"sq_{i}"))
    return pats


def build_v7():
    """piste 2 — REGION-SPECIALISED : spend the windows where the information
    is dense — the two promotion bands (rows 0-2 and 7-9), the long central
    diagonals, the left/right edges and the centre — rather than tiling uni-
    formly. Draughts-specific placement (back rank, edges weak, centre strong)."""
    pats, seen = [], set()
    def add(p, name):
        if p and tuple(p) not in seen:
            seen.add(tuple(p)); pats.append((p, name))
    # Promotion bands : 3×4 horizontal blocks on the top (0-2) and bottom (7-9).
    for c0 in (0, 1):
        add(hblock(0, c0), f"promo_top_{c0}")
        add(hblock(7, c0), f"promo_bot_{c0}")
    # Long central diagonals (both directions), densest near the centre.
    for s in range(18, 34):
        add(dband(s), f"cdiag_{s}")
        add(aband(s), f"cadiag_{s}")
    # Left / right edge vertical bands (edge men are weak — worth watching).
    for half, r0 in (("top", 0), ("bot", 4)):
        add(vband(r0, 0), f"edgeL_{half}")
        add(vband(r0, 3), f"edgeR_{half}")
    # Centre compact blocks (central control).
    for i, (r0, c0) in enumerate([(3, 0), (3, 2), (4, 1)]):
        add(sblock(r0, c0), f"centre_{i}")
    return pats


def build(variant="v4"):
    """v4 ENRICHED set (32 patterns) : 8 vertical bands (v3) + 7 down-right
    diagonals + 8 anti-diagonals + 5 horizontal + 4 square blocks. The proven
    sweet spot (0165 reliable: 0.72 vs hc). variant="v5" appends 8 3×4 diagonal
    BLOCKS (->40) — that addition regressed in earlier (confounded) tests; the
    geometry investigation (0166) re-measures it cleanly with an l2 sweep.
    variant="v6" (diagonal-dense) and "v7" (region-specialised) are the Scan-
    route geometries (prepared ahead — run via 0186/0187)."""
    if variant == "v6":
        pats = build_v6()
    elif variant == "v7":
        pats = build_v7()
    elif variant in ("v3", "8cf"):
        # 8cf : the 8 v3 VERTICAL bands ONLY (= Scan's vertical-band subset). A
        # strict subset of v4's geometry (v4 = these 8 + diagonals/horiz/squares).
        # Used by the famine learning-curve (8cf vs 32cf at growing volume).
        pats = [(vband(r0, c0), f"v_{half}_{c0}")
                for half, r0 in (("top", 0), ("bot", 4)) for c0 in range(4)]
    else:
        pats = _build_v4_v5(variant)
    # validate (12 distinct squares, in 1..50, and globally no duplicate pattern)
    allseen = set()
    for sqs, name in pats:
        assert sqs and len(sqs) == SIZE and len(set(sqs)) == SIZE \
            and all(1 <= x <= 50 for x in sqs), (name, sqs)
        t = tuple(sqs)
        assert t not in allseen, ("duplicate pattern", name)
        allseen.add(t)
    return pats


def _build_v4_v5(variant="v4"):
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
    if variant == "v5":
        # +8 3×4 diagonal blocks (4 per direction, evenly spread) → 40 patterns.
        for tag, fn in (("db", dblock), ("ab", ablock)):
            distinct, seen = [], set()
            for s in range(1, 51):
                p = fn(s)
                if p and tuple(p) not in seen:
                    seen.add(tuple(p)); distinct.append(p)
            n = len(distinct)
            for j, gi in enumerate(sorted({(i * n) // 4 for i in range(4)})):
                pats.append((distinct[gi], f"{tag}_{j}"))
    # validate (12 distinct squares, in 1..50, and globally no duplicate pattern)
    allseen = set()
    for sqs, name in pats:
        assert sqs and len(sqs) == SIZE and len(set(sqs)) == SIZE \
            and all(1 <= x <= 50 for x in sqs), (name, sqs)
        t = tuple(sqs)
        assert t not in allseen, ("duplicate pattern", name)
        allseen.add(t)
    return pats


def lr_close(pats):
    """Close the pattern set under the spatial group {rot180, left-right reflection}
    so EVERY pattern's mirror/rotation is present → the symmetry fold (train.py
    --full-fold) ties all patterns (exact LR over the whole set, not just vband/sq).
    Added patterns inherit their source name + a _r/_l/_rl tag. NB: grows the count
    (32->54) so the eval does more lookups; the added patterns are weight-TIED by
    the fold (no new free params)."""
    def rot(s):  # rot180 on FMJD 50-square board
        return 51 - s
    def lr(n):   # left-right = reverse the 5 squares within the row
        r = (n - 1) // 5; i = (n - 1) % 5
        return r * 5 + (4 - i) + 1
    canon = lambda sqs: tuple(sorted(sqs))
    have = {canon(s): nm for s, nm in pats}
    out = list(pats)
    ops = [("_r", lambda S: [rot(s) for s in S]),
           ("_l", lambda S: [lr(s) for s in S]),
           ("_rl", lambda S: [lr(rot(s)) for s in S])]
    changed = True
    while changed:
        changed = False
        for sqs, name in list(out):
            for tag, op in ops:
                im = op(sqs); key = canon(im)
                if key not in have:
                    base = name.split("_lr")[0]
                    have[key] = f"{base}{tag}"
                    out.append((sorted(im), f"{base}{tag}"))
                    changed = True
    return out


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


def _sub_count(path: Path, n: int):
    txt = path.read_text()
    txt = re.sub(r"NUM_PATTERNS  = \d+;", f"NUM_PATTERNS  = {n};", txt)
    txt = re.sub(r"NUM_PATTERNS, std::size_t\{\d+\}", f"NUM_PATTERNS, std::size_t{{{n}}}", txt)
    txt = re.sub(r"TOTAL_BUCKETS, std::uint32_t\{\d+ \* 531441\}",
                 f"TOTAL_BUCKETS, std::uint32_t{{{n} * 531441}}", txt)
    path.write_text(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true", help="rewrite pattern.hpp + patterns.py")
    ap.add_argument("--variant", choices=["v4", "v5", "v6", "v7"], default="v4",
                    help="v4=32 (sweet spot), v5=40 (diag blocks), "
                         "v6=diagonal-dense, v7=region-specialised (Scan route)")
    ap.add_argument("--lr-close", action="store_true",
                    help="close the set under {rot180, LR} so reflection folds ALL "
                         "patterns (32->54). Names get _r/_l/_rl tags.")
    ap.add_argument("--drop", default="",
                    help="comma-separated pattern NAMES to remove (RFE geometry "
                         "pruning, e.g. anti_0,sq_3); validated against the built set")
    args = ap.parse_args()
    pats = build(args.variant)
    if args.lr_close:
        pats = lr_close(pats)
    if args.drop:
        drop = {x.strip() for x in args.drop.split(",") if x.strip()}
        have = {nm for _, nm in pats}
        missing = drop - have
        if missing:
            sys.exit(f"--drop: unknown pattern name(s): {sorted(missing)}")
        pats = [(s, nm) for s, nm in pats if nm not in drop]
        print(f"dropped {len(drop)} patterns {sorted(drop)} -> {len(pats)} remain")
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
        # Patch the NUM_PATTERNS constant + run_tests guards so a variant switch
        # is a single command (the count is not inside the @GEN markers).
        _sub_count(root / "src" / "pattern.hpp", n)
        _sub_count(root / "tests" / "run_tests.cpp", n)
        print(f"\nNUM_PATTERNS set to {n} ({args.variant}); TOTAL_BUCKETS={n*531441}.")


if __name__ == "__main__":
    raise SystemExit(main())
