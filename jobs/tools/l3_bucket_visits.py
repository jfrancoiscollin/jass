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
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import patterns  # noqa: E402  (8cf geometry via PYTHONPATH)
import train_stream as ts  # noqa: E402


def compute(data_paths, chunk: int, top_k: int) -> dict:
    folder = ts.Folder("color")
    NP = patterns.NUM_PATTERNS
    CFB = folder.PAT_BUCKETS            # colour-folded buckets per pattern
    TB = folder.TB                      # NP * CFB = trained parameter space
    visits = np.zeros(TB, dtype=np.int64)
    total_records = 0
    for path in data_paths:
        mm, n = ts.open_jnnw(str(path))
        for i in range(0, n, chunk):
            rec = mm[i:i + chunk]
            bm = np.ascontiguousarray(rec["bm"])
            wm = np.ascontiguousarray(rec["wm"])
            cols, _ = folder.cols_signs(bm, wm)     # (m, NP) int64 in [0, TB)
            visits += np.bincount(cols.ravel(), minlength=TB)
            total_records += len(rec)
    if total_records == 0:
        raise SystemExit("no records in corpus")

    total_visits = int(visits.sum())
    visited = int((visits > 0).sum())
    thresholds = {f"ge_{k}": int((visits >= k).sum()) for k in (1, 10, 100, 1000)}

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
        "geometry": {
            "num_patterns": int(NP),
            "buckets_per_pattern_colorfold": int(CFB),
            "trained_buckets_total": int(TB),
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
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", nargs="+", required=True, help="JNNW corpus file(s)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk", type=int, default=500000)
    ap.add_argument("--top-k", type=int, default=100)
    args = ap.parse_args(argv)
    report = compute([Path(p) for p in args.data], args.chunk, args.top_k)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("corpus", "coverage", "concentration", "capacity_heuristic")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
