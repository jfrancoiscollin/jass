#!/usr/bin/env python3
"""Bounded target-blind timing probe for the frozen JFI-C selector."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

try:
    from .jfi_active_select_stream import (
        open_feat, open_jnnw, representative_indices, score_design, sha_tie_keys,
    )
    from .jfi_candidate_prefix import MAX_RECORDS, sha256_file
except ImportError:  # direct script execution from jobs/tools
    from jfi_active_select_stream import (
        open_feat, open_jnnw, representative_indices, score_design, sha_tie_keys,
    )
    from jfi_candidate_prefix import MAX_RECORDS, sha256_file


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--feat", required=True)
    ap.add_argument("--origin-indices", required=True)
    ap.add_argument("--fisher", required=True)
    ap.add_argument("--l2", required=True, type=float)
    ap.add_argument("--full-train-candidates", required=True, type=int)
    ap.add_argument("--chunk", type=int, default=20_000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    records = open_jnnw(args.data)
    feat = open_feat(args.feat, len(records))
    origin = np.load(args.origin_indices, allow_pickle=False, mmap_mode="r")
    fisher = np.load(args.fisher, allow_pickle=False, mmap_mode="r")
    if (
        not 0 < len(records) <= MAX_RECORDS or origin.shape != (len(records),)
        or args.full_train_candidates < len(records) or not args.l2 > 0
        or np.any(records["score"] != 0) or np.any(records["wdl"] != 0)
    ):
        raise SystemExit("bounded target-blind selector sizer contract drift")
    started = time.monotonic()
    scores, strata, canonical = score_design(
        records, feat, fisher, args.l2, len(records), args.chunk,
    )
    tie_high, tie_low = sha_tie_keys(origin, 2026120103)
    representatives = representative_indices(canonical, tie_high, tie_low)
    elapsed = time.monotonic() - started
    rate = len(records) / elapsed
    report = {
        "schema": "jass.jfi.c_selector_sizer.v1",
        "role": "bounded_preflight_no_arm_selection",
        "rows": len(records), "seconds": elapsed, "rows_per_second": rate,
        "full_train_candidates": args.full_train_candidates,
        "projected_full_selector_seconds": args.full_train_candidates / rate,
        "canonical_unique_rows": int(len(representatives)),
        "score_quantiles": np.quantile(scores, [0, .25, .5, .75, .9, .99, 1]).tolist(),
        "strata_observed": int(len(np.unique(strata))),
        "l2": args.l2,
        "inputs": {
            "data_sha256": sha256_file(args.data),
            "feat_sha256": sha256_file(args.feat),
            "origin_indices_sha256": sha256_file(args.origin_indices),
            "fisher_sha256": sha256_file(args.fisher),
        },
        "guards": {
            "TARGET_READS": 0, "SCAN_READS": 0, "ARM_SELECTIONS": 0,
            "FULL_FITS": 0,
        },
    }
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
