#!/usr/bin/env python3
"""Streaming target-blind JFI-C ACTIVE/UNIFORM selector on a frozen universe."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time

import numpy as np

TOOLS = Path(__file__).resolve().parents[2] / "pattern_jass" / "tools"
geometry = os.environ.get("JASS_PATTERNS_DIR")
if geometry:
    sys.path.insert(0, geometry)
sys.path.insert(0, str(TOOLS))
import eval_phase  # noqa: E402
import patterns  # noqa: E402


JNNW_DTYPE = np.dtype([
    ("wm", "<u8"), ("wk", "<u8"), ("bm", "<u8"), ("bk", "<u8"),
    ("stm", "u1"), ("score", "<i4"), ("wdl", "i1"),
])
PIECE_BIN_UPPER = (8, 16, 24, 32, 40)
PHASE_BINS = 4
TIE_SEED = 2026120103
REV10 = np.asarray([
    int(f"{value:010b}"[::-1], 2) for value in range(1 << 10)
], dtype=np.uint64)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def open_jnnw(path):
    with open(path, "rb") as handle:
        header = handle.read(8)
    if len(header) != 8 or header[:4] != b"JNNW":
        raise ValueError(f"{path}: invalid JNNW")
    count = struct.unpack_from("<I", header, 4)[0]
    if Path(path).stat().st_size != 8 + count * JNNW_DTYPE.itemsize:
        raise ValueError(f"{path}: JNNW size/count drift")
    return np.memmap(path, dtype=JNNW_DTYPE, mode="r", offset=8, shape=(count,))


def open_feat(path, count):
    with open(path, "rb") as handle:
        header = handle.read(12)
    if len(header) != 12 or header[:4] != b"FEAT":
        raise ValueError(f"{path}: invalid FEAT")
    rows, width = struct.unpack_from("<II", header, 4)
    if rows != count or Path(path).stat().st_size != 12 + rows * width * 4:
        raise ValueError(f"{path}: FEAT shape drift")
    return np.memmap(path, dtype="<f4", mode="r", offset=12, shape=(rows, width))


def reverse50(values):
    values = np.asarray(values, dtype=np.uint64)
    out = np.zeros(values.shape, dtype=np.uint64)
    for source in range(5):
        block = (values >> np.uint64(10 * source)) & np.uint64(0x3FF)
        out |= REV10[block.astype(np.int64)] << np.uint64(40 - 10 * source)
    return out


def canonical_state(wm, wk, bm, bk, stm):
    wm = np.asarray(wm, dtype=np.uint64); wk = np.asarray(wk, dtype=np.uint64)
    bm = np.asarray(bm, dtype=np.uint64); bk = np.asarray(bk, dtype=np.uint64)
    stm = np.asarray(stm, dtype=np.uint8)
    swm, swk = reverse50(bm), reverse50(bk)
    sbm, sbk = reverse50(wm), reverse50(wk)
    sstm = np.asarray(1 - stm, dtype=np.uint8)
    equal = np.ones(len(wm), dtype=bool)
    use = np.zeros(len(wm), dtype=bool)
    for left, right in ((swm, wm), (swk, wk), (sbm, bm), (sbk, bk), (sstm, stm)):
        use |= equal & (left < right)
        equal &= left == right
    return tuple(np.where(use, sym, raw) for raw, sym in (
        (wm, swm), (wk, swk), (bm, sbm), (bk, sbk), (stm, sstm),
    ))


def sha_tie_keys(row_ids, seed):
    high = np.empty(len(row_ids), dtype=np.uint64)
    low = np.empty(len(row_ids), dtype=np.uint64)
    for index, row_id in enumerate(np.asarray(row_ids)):
        digest = hashlib.sha256(f"{seed}:{int(row_id)}".encode()).digest()
        high[index] = int.from_bytes(digest[:8], "big")
        low[index] = int.from_bytes(digest[8:16], "big")
    return high, low


def representative_indices(canonical, tie_high, tie_low):
    wm, wk, bm, bk, stm = canonical
    order = np.lexsort((tie_low, tie_high, stm, bk, bm, wk, wm))
    different = np.ones(len(order), dtype=bool)
    if len(order) > 1:
        left, right = order[:-1], order[1:]
        different[1:] = (
            (wm[left] != wm[right]) | (wk[left] != wk[right])
            | (bm[left] != bm[right]) | (bk[left] != bk[right])
            | (stm[left] != stm[right])
        )
    return order[different]


def hamilton_quotas(counts, total):
    counts = np.asarray(counts, dtype=np.int64)
    if total < 0 or total > int(counts.sum()):
        raise ValueError("quota total is infeasible")
    exact = counts.astype(np.float64) * total / counts.sum()
    quota = np.floor(exact).astype(np.int64)
    remaining = total - int(quota.sum())
    order = np.lexsort((np.arange(len(counts)), -(exact - quota)))
    quota[order[:remaining]] += 1
    return quota


def select_stratified(scores, strata, tie_high, tie_low, count, *, excluded=None,
                      active=False, quotas=None):
    scores = np.asarray(scores, dtype=np.float64)
    strata = np.asarray(strata, dtype=np.int16)
    available = np.ones(len(scores), dtype=bool)
    if excluded is not None:
        available[np.asarray(excluded, dtype=np.int64)] = False
    max_stratum = int(strata.max(initial=-1)) + 1
    counts = np.bincount(strata[available], minlength=max_stratum)
    if quotas is None:
        quotas = hamilton_quotas(counts, count)
    if len(quotas) != max_stratum or np.any(quotas > counts):
        raise ValueError("stratum quotas are infeasible")
    selected = []
    for stratum, quota in enumerate(quotas):
        if not quota:
            continue
        candidates = np.flatnonzero(available & (strata == stratum))
        if active:
            order = np.lexsort((tie_low[candidates], tie_high[candidates], -scores[candidates]))
        else:
            order = np.lexsort((tie_low[candidates], tie_high[candidates]))
        selected.append(candidates[order[:quota]])
    result = np.concatenate(selected).astype(np.int64, copy=False)
    if len(result) != count:
        raise AssertionError("stratified selection count drift")
    return result, np.asarray(quotas, dtype=np.int64)


def score_design(records, feat, fisher, l2, train_count, chunk):
    from train_stream import Folder

    folder = Folder("exact")
    n_pat = patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN
    extras = feat.shape[1]
    expected = 2 * (n_pat + extras)
    if fisher.shape != (expected,) or not l2 > 0:
        raise ValueError("Fisher/positive-lambda geometry drift")
    denominator = np.asarray(fisher, dtype=np.float64) + l2
    scores = np.empty(train_count, dtype=np.float64)
    strata = np.empty(train_count, dtype=np.int16)
    canonical = tuple(np.empty(train_count, dtype=dtype) for dtype in (
        np.uint64, np.uint64, np.uint64, np.uint64, np.uint8,
    ))
    for start in range(0, train_count, chunk):
        stop = min(start + chunk, train_count)
        rec = records[start:stop]
        if np.any(rec["score"] != 0) or np.any(rec["wdl"] != 0):
            raise ValueError("target-blind selector refuses non-zero score/WDL fields")
        wm = np.ascontiguousarray(rec["wm"]); wk = np.ascontiguousarray(rec["wk"])
        bm = np.ascontiguousarray(rec["bm"]); bk = np.ascontiguousarray(rec["bk"])
        columns, signs = folder.cols_signs(bm, wm)
        wmg = eval_phase.tempo_wmg_bb(wm, bm).astype(np.float64)
        weg = 1.0 - wmg
        value = np.sum((signs * wmg[:, None]) ** 2 / denominator[columns], axis=1)
        value += np.sum((signs * weg[:, None]) ** 2 / denominator[n_pat + columns], axis=1)
        dense = np.asarray(feat[start:stop], dtype=np.float64)
        value += np.sum((dense * wmg[:, None]) ** 2 /
                        denominator[2*n_pat:2*n_pat+extras], axis=1)
        value += np.sum((dense * weg[:, None]) ** 2 /
                        denominator[2*n_pat+extras:], axis=1)
        scores[start:stop] = value
        pieces = eval_phase.piece_count_bb(wm, wk, bm, bk)
        piece_bin = np.searchsorted(np.asarray(PIECE_BIN_UPPER), pieces, side="left")
        if np.any(piece_bin >= len(PIECE_BIN_UPPER)):
            raise ValueError("piece count outside frozen JFI bins")
        phase_bin = np.minimum((wmg * PHASE_BINS).astype(np.int16), PHASE_BINS - 1)
        strata[start:stop] = piece_bin * (PHASE_BINS * 2) + phase_bin * 2 + rec["stm"]
        folded = canonical_state(wm, wk, bm, bk, rec["stm"])
        for destination, values in zip(canonical, folded):
            destination[start:stop] = values
    return scores, strata, canonical


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=("c", "d"), default="c")
    ap.add_argument("--data", required=True)
    ap.add_argument("--feat", required=True)
    ap.add_argument("--candidate-manifest", required=True)
    ap.add_argument("--origin-indices", required=True)
    ap.add_argument("--roles", required=True)
    ap.add_argument("--fisher", required=True)
    ap.add_argument("--l2", required=True, type=float)
    ap.add_argument("--train-count", required=True, type=int)
    ap.add_argument("--count", type=int, default=2_000_000)
    ap.add_argument("--tie-seed", type=int, default=TIE_SEED)
    ap.add_argument("--chunk", type=int, default=20_000)
    ap.add_argument("--active-indices-out", required=True)
    ap.add_argument("--uniform-indices-out")
    ap.add_argument("--active-row-ids-out", required=True)
    ap.add_argument("--uniform-row-ids-out")
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args(argv)
    expected_count = 2_000_000 if args.stage == "c" else 4_000_000
    if args.count != expected_count and argv is None:
        raise SystemExit(f"production JFI-{args.stage.upper()} active count must be {expected_count}")
    if args.stage == "c" and (not args.uniform_indices_out or not args.uniform_row_ids_out):
        raise SystemExit("JFI-C requires UNIFORM output paths")
    if args.stage == "d" and (args.uniform_indices_out or args.uniform_row_ids_out):
        raise SystemExit("JFI-D is ACTIVE-only")
    if args.tie_seed != TIE_SEED:
        raise SystemExit("JFI-C tie seed drift")
    started = time.monotonic()
    records = open_jnnw(args.data)
    feat = open_feat(args.feat, len(records))
    candidate_manifest = json.loads(Path(args.candidate_manifest).read_text())
    if candidate_manifest.get("schema") != "jass.jfi.candidate_universe.v1":
        raise SystemExit("candidate-universe manifest schema drift")
    frozen = candidate_manifest.get("files", {})
    input_digests = {
        "data": sha256_file(args.data),
        "origin_indices": sha256_file(args.origin_indices),
        "roles": sha256_file(args.roles),
    }
    for label, path in (("data", args.data), ("origin_indices", args.origin_indices),
                        ("roles", args.roles)):
        if input_digests[label] != (frozen.get(label) or {}).get("sha256"):
            raise SystemExit(f"candidate-universe {label} SHA drift")
    origin = np.load(args.origin_indices, allow_pickle=False, mmap_mode="r")
    roles = np.load(args.roles, allow_pickle=False, mmap_mode="r")
    fisher = np.load(args.fisher, allow_pickle=False, mmap_mode="r")
    split = candidate_manifest.get("selection", {})
    if (
        origin.shape != (len(records),) or roles.shape != (len(records),)
        or split.get("records") != len(records)
        or split.get("train_candidates") != args.train_count
        or not 0 < args.train_count < len(records)
        or np.any(roles[:args.train_count] != 0) or np.any(roles[args.train_count:] != 1)
    ):
        raise SystemExit("candidate origin/split alignment drift")
    scores, strata, canonical = score_design(
        records, feat, fisher, args.l2, args.train_count, args.chunk,
    )
    tie_high, tie_low = sha_tie_keys(origin[:args.train_count], args.tie_seed)
    representatives = representative_indices(canonical, tie_high, tie_low)
    rep_scores = scores[representatives]
    rep_strata = strata[representatives]
    rep_high = tie_high[representatives]; rep_low = tie_low[representatives]
    active_local, quotas = select_stratified(
        rep_scores, rep_strata, rep_high, rep_low, args.count, active=True,
    )
    active = representatives[active_local]
    active_row_ids = np.asarray(origin[active], dtype=np.uint32)
    np.save(args.active_indices_out, active.astype(np.uint32), allow_pickle=False)
    np.save(args.active_row_ids_out, active_row_ids, allow_pickle=False)
    uniform = None
    if args.stage == "c":
        uniform_local, uniform_quotas = select_stratified(
            rep_scores, rep_strata, rep_high, rep_low, args.count,
            excluded=active_local, active=False, quotas=quotas,
        )
        if not np.array_equal(quotas, uniform_quotas):
            raise AssertionError("ACTIVE/UNIFORM quota drift")
        uniform = representatives[uniform_local]
        uniform_row_ids = np.asarray(origin[uniform], dtype=np.uint32)
        np.save(args.uniform_indices_out, uniform.astype(np.uint32), allow_pickle=False)
        np.save(args.uniform_row_ids_out, uniform_row_ids, allow_pickle=False)
    elapsed = time.monotonic() - started
    counts = np.bincount(rep_strata, minlength=len(quotas))
    report = {
        "schema": (
            "jass.jfi.c_active_uniform_selection.v1" if args.stage == "c"
            else "jass.jfi.d_active_selection.v1"
        ),
        "stage": args.stage,
        "algorithm": "diagonal_leverage_v1",
        "formula": "sum_j x_j^2/(F_j+lambda)",
        "l2": args.l2,
        "tie_break": {"algorithm": "sha256(seed:source_row_id), first 128 bits", "seed": args.tie_seed},
        "candidate_rows": args.train_count,
        "canonical_unique_rows": int(len(representatives)),
        "canonical_duplicates_removed": int(args.train_count - len(representatives)),
        "active_rows": int(len(active)),
        "uniform_rows": int(len(uniform)) if uniform is not None else None,
        "active_uniform_disjoint": (
            bool(not np.intersect1d(active, uniform).size) if uniform is not None else None
        ),
        "dev_excluded": True,
        "inputs": {
            "candidate_manifest": {
                "path": args.candidate_manifest, "sha256": sha256_file(args.candidate_manifest),
            },
            "candidate_data": {"path": args.data, "sha256": input_digests["data"]},
            "candidate_feat": {"path": args.feat, "sha256": sha256_file(args.feat)},
            "origin_indices": {
                "path": args.origin_indices, "sha256": input_digests["origin_indices"],
            },
            "roles": {"path": args.roles, "sha256": input_digests["roles"]},
            "fisher": {"path": args.fisher, "sha256": sha256_file(args.fisher)},
        },
        "stratification": {
            "joint": ["piece_count_bin", "tempo_phase_quartile", "original_stm"],
            "piece_bin_upper_inclusive": list(PIECE_BIN_UPPER),
            "phase_bins": PHASE_BINS,
            "candidate_counts": counts.tolist(), "arm_quotas": quotas.tolist(),
            "quota_algorithm": "Hamilton largest remainder; stratum id tie-break",
        },
        "files": {
            "active_indices": {"path": args.active_indices_out, "sha256": sha256_file(args.active_indices_out)},
            "active_row_ids": {"path": args.active_row_ids_out, "sha256": sha256_file(args.active_row_ids_out)},
        },
        "rate": {"elapsed_seconds": elapsed, "candidate_rows_per_second": args.train_count / elapsed},
        "guards": {
            "TARGET_READS_BEFORE_MANIFEST_FREEZE": 0, "SCAN_READS": 0,
            "source_score_values_required_zero": True, "source_wdl_values_required_zero": True,
        },
    }
    if args.stage == "c":
        report["files"].update({
            "uniform_indices": {
                "path": args.uniform_indices_out, "sha256": sha256_file(args.uniform_indices_out),
            },
            "uniform_row_ids": {
                "path": args.uniform_row_ids_out, "sha256": sha256_file(args.uniform_row_ids_out),
            },
        })
    Path(args.manifest).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
