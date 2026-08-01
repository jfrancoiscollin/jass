#!/usr/bin/env python3
"""Publish per-bucket visit counts for an L3 self-play corpus (plan L3_PURE 6.4).

This is the pre-condition gate for the 8cf -> 32cf representation-capacity
comparison: it measures whether the current 8cf geometry is *data-limited*
(most colour-folded buckets are rarely or never visited, so adding capacity
would only make coverage sparser) or *capacity-used* (a large, well-visited
bucket mass, so more resolution could carry signal).

Bucket reconstruction reuses the training path verbatim: `train_stream.Folder`
in colour-fold mode on the men bitboards (`cols_signs(bm, wm)`), exactly what
the L3 fit consumes (no --king-patterns). Must run with PYTHONPATH pointing at
the frozen 8cf geometry so `patterns` is the 8cf variant.

`--fold exact` measures the same corpus in the space the fit now actually
optimises. Since 1 August 2026 every L3 fit runs under `--exact-fold`, which
folds on `rot180 o colour-swap` — the only exact symmetry of the board —
instead of `cs` alone, which is not one. Coverage is a count of *distinct
canonical buckets reached*, so it is defined by the fold: the same corpus
scores differently under the two, and the two numbers must never be compared
to each other. The report states which fold produced it, and the denominator
is the fold's own parameter space.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from pathlib import Path

import numpy as np

import patterns  # noqa: E402  (8cf geometry via PYTHONPATH)

JNNW_HEADER_SIZE = 8
JNNW_RECORD_SIZE = 38
JNNW_DTYPE = np.dtype([
    ("wm", "<u8"),
    ("wk", "<u8"),
    ("bm", "<u8"),
    ("bk", "<u8"),
    ("stm", "u1"),
    ("score", "<i4"),
    ("wdl", "i1"),
])
COLORFOLD_BUCKETS = (3 ** 12 - 1) // 2 + 1


def open_jnnw(path: Path) -> tuple[np.memmap, int]:
    """Read the packed JNNW geometry without importing the SciPy trainer."""
    with path.open("rb") as handle:
        header = handle.read(JNNW_HEADER_SIZE)
    if len(header) != JNNW_HEADER_SIZE or header[:4] != b"JNNW":
        raise SystemExit(f"{path}: invalid JNNW header")
    count = struct.unpack_from("<I", header, 4)[0]
    body = os.path.getsize(path) - JNNW_HEADER_SIZE
    if body < 0 or body % JNNW_RECORD_SIZE:
        raise SystemExit(f"{path}: invalid JNNW body size {body}")
    derived = body // JNNW_RECORD_SIZE
    if count != derived:
        raise SystemExit(f"{path}: header count {count} != file-derived {derived}")
    records = np.memmap(
        path,
        dtype=JNNW_DTYPE,
        mode="r",
        offset=JNNW_HEADER_SIZE,
        shape=(count,),
    )
    return records, count


class ColorFolder:
    """Minimal colour-antisymmetric fold used by the coverage-only audit."""

    def __init__(self) -> None:
        unsigned = np.arange(3 ** 12, dtype=np.int64)
        remaining = unsigned.copy()
        signed = np.zeros_like(unsigned)
        for cell_index in range(12):
            cell = remaining % 3
            remaining //= 3
            signed += np.where(cell == 1, 1, np.where(cell == 2, -1, 0)) * (
                3 ** cell_index
            )
        self.unsigned_to_canonical = np.abs(signed).astype(np.int64)
        self.PAT_BUCKETS = COLORFOLD_BUCKETS
        self.TB = self.PAT_BUCKETS * patterns.NUM_PATTERNS

    def columns(self, black_men: np.ndarray, white_men: np.ndarray) -> np.ndarray:
        indices = patterns.extract_indices(black_men, white_men)
        canonical = self.unsigned_to_canonical[indices]
        offsets = (
            np.arange(patterns.NUM_PATTERNS, dtype=np.int64) * self.PAT_BUCKETS
        )
        return canonical + offsets[None, :]


class ExactFolder:
    """Fold on `rot180 o colour-swap`, the only exact symmetry of the board.

    Shares `build_exact_canon` with the trainer rather than re-deriving the
    orbit here: a coverage audit that disagreed with the fit about which
    buckets are the same bucket would measure nothing useful.

    `canon_col[p, i]` is a canonical id drawn from the *unfolded* space
    `[0, NUM_PATTERNS * 3**12)`, of which exactly half are reachable. Ids are
    therefore remapped to a dense range so the visit array stays the size of
    the real parameter space and `coverage_fraction` keeps its meaning.
    """

    def __init__(self) -> None:
        import symmetry  # noqa: PLC0415 — needs the 8cf `patterns` already bound

        canon_col, _sign = symmetry.build_exact_canon()
        dense = np.full(canon_col.max() + 1, -1, dtype=np.int64)
        reachable = np.unique(canon_col)
        dense[reachable] = np.arange(reachable.size, dtype=np.int64)
        self.canon_dense = dense[canon_col]          # (NP, 3**12) -> [0, TB)
        self.PAT_BUCKETS = int(reachable.size // patterns.NUM_PATTERNS)
        self.TB = int(reachable.size)

    def columns(self, black_men: np.ndarray, white_men: np.ndarray) -> np.ndarray:
        indices = patterns.extract_indices(black_men, white_men)
        pattern_ids = np.arange(patterns.NUM_PATTERNS, dtype=np.int64)
        return self.canon_dense[pattern_ids[None, :], indices]


FOLDERS = {"color": ColorFolder, "exact": ExactFolder}


def compute(data_paths, chunk: int, top_k: int, fold: str = "color") -> dict:
    folder = FOLDERS[fold]()
    NP = patterns.NUM_PATTERNS
    CFB = folder.PAT_BUCKETS            # folded buckets per pattern
    TB = folder.TB                      # trained parameter space under this fold
    visits = np.zeros(TB, dtype=np.int64)
    total_records = 0
    for path in data_paths:
        mm, n = open_jnnw(path)
        for i in range(0, n, chunk):
            rec = mm[i:i + chunk]
            bm = np.ascontiguousarray(rec["bm"])
            wm = np.ascontiguousarray(rec["wm"])
            cols = folder.columns(bm, wm)           # (m, NP) int64 in [0, TB)
            visits += np.bincount(cols.ravel(), minlength=TB)
            total_records += len(rec)
    if total_records == 0:
        raise SystemExit("no records in corpus")

    total_visits = int(visits.sum())
    visited = int((visits > 0).sum())
    thresholds = {f"ge_{k}": int((visits >= k).sum()) for k in (1, 10, 100, 1000)}

    # Only the colour fold keeps one contiguous block of buckets per pattern.
    # `rot180 o cs` maps pattern p onto pattern rp[p], so a canonical id can
    # live under a different pattern than the one that reached it and the
    # blocks are neither contiguous nor equal-sized. Slicing them anyway would
    # produce a per-pattern table that reads plausibly and means nothing.
    per_pattern = None
    if fold == "color":
        per_pattern = []
        for p in range(NP):
            seg = visits[p * CFB:(p + 1) * CFB]
            per_pattern.append({
                "pattern": p,
                "buckets": int(CFB),
                "visited": int((seg > 0).sum()),
                "coverage": round(float((seg > 0).mean()), 6),
                "visit_sum": int(seg.sum()),
            })

    nz = np.sort(visits[visits > 0])[::-1]
    topk_mass = float(nz[:top_k].sum()) / total_visits if total_visits else 0.0
    # Gini of the visit distribution over visited buckets (concentration).
    if nz.size:
        asc = nz[::-1].astype(np.float64)
        cum = np.cumsum(asc)
        gini = float((nz.size + 1 - 2 * (cum.sum() / cum[-1])) / nz.size)
    else:
        gini = 0.0

    coverage = visited / TB
    frac_ge_100 = thresholds["ge_100"] / TB
    # Explicit, conservative heuristic — the human reads the raw metrics too.
    if coverage >= 0.5 and frac_ge_100 >= 0.1:
        heuristic = "capacity_used_more_resolution_worth_testing"
    else:
        heuristic = "data_limited_more_capacity_not_justified"

    return {
        "schema": 1,
        "stage": "l3_bucket_visits",
        "fold": fold,
        "geometry": {
            "num_patterns": int(NP),
            "buckets_per_pattern": int(CFB),
            "trained_buckets_total": int(TB),
            "per_pattern_blocks_are_contiguous": fold == "color",
        },
        "corpus": {
            "files": [str(p) for p in data_paths],
            "total_records": int(total_records),
            "total_bucket_visits": total_visits,
            "visits_per_record": round(total_visits / total_records, 4),
        },
        "coverage": {
            "visited_buckets": visited,
            "coverage_fraction": round(coverage, 6),
            "buckets_with_at_least": thresholds,
            "frac_buckets_ge_100": round(frac_ge_100, 6),
        },
        "concentration": {
            "gini": round(gini, 6),
            f"top_{top_k}_visit_mass_fraction": round(topk_mass, 6),
            "mean_visits_per_visited_bucket": round(total_visits / visited, 4) if visited else 0.0,
        },
        "per_pattern": per_pattern,
        "capacity_heuristic": heuristic,
        "note": "heuristic is diagnostic; 32cf go/no-go is a human decision on coverage + cumulative volume",
        "comparability": "coverage is defined by the fold; never compare a "
                         "color-fold count with an exact-fold one",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", nargs="+", required=True, help="JNNW corpus file(s)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk", type=int, default=500000)
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--fold", choices=sorted(FOLDERS), default="color",
                    help="bucket space to count in; 'exact' is what the fit "
                         "has optimised since 1 August 2026")
    args = ap.parse_args(argv)
    report = compute([Path(p) for p in args.data], args.chunk, args.top_k, args.fold)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("corpus", "coverage", "concentration", "capacity_heuristic")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
