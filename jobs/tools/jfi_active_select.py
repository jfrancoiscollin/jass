#!/usr/bin/env python3
"""Target-blind JFI diagonal-leverage scorer with deterministic tie-breaking."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


FORBIDDEN_KEYS = {"target", "targets", "wdl", "outcome", "score", "scan"}


def leverage_scores(indptr, indices, values, fisher, l2):
    if not l2 > 0:
        raise ValueError("JFI active selection requires a strictly positive l2")
    indptr = np.asarray(indptr, dtype=np.int64)
    indices = np.asarray(indices, dtype=np.int64)
    values = np.asarray(values, dtype=np.float64)
    fisher = np.asarray(fisher, dtype=np.float64)
    if indptr[0] != 0 or indptr[-1] != len(indices) or indices.shape != values.shape:
        raise ValueError("invalid CSR design")
    if np.any(indices < 0) or np.any(indices >= len(fisher)) or np.any(fisher < 0):
        raise ValueError("invalid Fisher/index values")
    terms = values * values / (fisher[indices] + l2)
    row_index = np.repeat(np.arange(len(indptr) - 1, dtype=np.int64), np.diff(indptr))
    return np.bincount(row_index, weights=terms, minlength=len(indptr) - 1)


def deterministic_order(scores, row_ids, seed):
    row_ids = np.asarray(row_ids).astype("U")
    tie = np.asarray([
        hashlib.sha256(f"{seed}:{row_id}".encode()).hexdigest() for row_id in row_ids
    ])
    return np.lexsort((tie, -np.asarray(scores, dtype=np.float64)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design", required=True)
    ap.add_argument("--fisher", required=True)
    ap.add_argument("--l2", required=True, type=float)
    ap.add_argument("--count", required=True, type=int)
    ap.add_argument("--tie-seed", required=True, type=int)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    with np.load(args.design, allow_pickle=False) as archive:
        forbidden = {
            name for name in archive.files
            if any(token in name.lower() for token in FORBIDDEN_KEYS)
        }
        if forbidden:
            raise SystemExit(f"target-blind selector refuses forbidden arrays: {sorted(forbidden)}")
        required = {"indptr", "indices", "data", "row_id"}
        missing = required.difference(archive.files)
        if missing:
            raise SystemExit(f"design archive missing: {sorted(missing)}")
        scores = leverage_scores(
            archive["indptr"], archive["indices"], archive["data"],
            np.load(args.fisher, allow_pickle=False), args.l2,
        )
        row_ids = archive["row_id"].astype("U")
    if not 0 < args.count <= len(row_ids):
        raise SystemExit("--count must be in [1, rows]")
    selected = deterministic_order(scores, row_ids, args.tie_seed)[:args.count]
    payload = {
        "schema": "jass.jfi.active_selection_skeleton.v1",
        "algorithm": "diagonal_leverage_v1",
        "l2": args.l2,
        "tie_seed": args.tie_seed,
        "rows": int(len(row_ids)),
        "selected": int(args.count),
        "row_ids": row_ids[selected].tolist(),
        "TARGET_READS": 0,
        "SCAN_READS": 0,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
