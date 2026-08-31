#!/usr/bin/env python3
"""Read-only SB1 audit of C/CURRICULUM/SCAN_EXACT in common PJTW coordinates."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

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


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def open_jnnw(path: str | Path) -> np.memmap:
    with open(path, "rb") as handle:
        header = handle.read(8)
    if len(header) != 8 or header[:4] != b"JNNW":
        raise ValueError(f"{path}: invalid JNNW")
    count = struct.unpack_from("<I", header, 4)[0]
    if Path(path).stat().st_size != 8 + count * JNNW_DTYPE.itemsize:
        raise ValueError(f"{path}: size/count drift")
    return np.memmap(path, dtype=JNNW_DTYPE, mode="r", offset=8, shape=(count,))


def open_feat(path: str | Path, count: int) -> np.memmap:
    with open(path, "rb") as handle:
        header = handle.read(12)
    if len(header) != 12 or header[:4] != b"FEAT":
        raise ValueError(f"{path}: invalid FEAT")
    observed, width = struct.unpack_from("<II", header, 4)
    if observed != count or Path(path).stat().st_size != 12 + count * width * 4:
        raise ValueError(f"{path}: FEAT alignment drift")
    return np.memmap(path, dtype="<f4", mode="r", offset=12, shape=(count, width))


def open_model(path: str | Path, expected_extras: int) -> tuple[np.memmap, int, int, int]:
    with open(path, "rb") as handle:
        header = handle.read(20)
    if len(header) != 20:
        raise ValueError(f"{path}: truncated PJTW")
    magic, version, scale, n_pat, n_ext = struct.unpack("<5I", header)
    expected_pat = patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN
    if magic != 0x57544A50 or (version & 0xFF) != 3 or scale <= 0:
        raise ValueError(f"{path}: invalid PJTW header")
    if n_pat != expected_pat or n_ext != expected_extras:
        raise ValueError(
            f"{path}: geometry drift n_pat={n_pat} n_ext={n_ext}; "
            f"expected {expected_pat}/{expected_extras}"
        )
    total = 2 * (n_pat + n_ext)
    if Path(path).stat().st_size != 20 + total * 4:
        raise ValueError(f"{path}: PJTW size drift")
    weights = np.memmap(path, dtype="<i4", mode="r", offset=20, shape=(total,))
    return weights, scale, n_pat, n_ext


def rms(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=np.float64)
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0


def correlation(a: np.ndarray, b: np.ndarray, weights: np.ndarray | None = None) -> float | None:
    x = np.asarray(a, dtype=np.float64)
    y = np.asarray(b, dtype=np.float64)
    if x.shape != y.shape or not x.size:
        raise ValueError("correlation arrays differ or are empty")
    if weights is None:
        x0 = x - x.mean(); y0 = y - y.mean()
        denom = np.sqrt(np.dot(x0, x0) * np.dot(y0, y0))
        return None if denom == 0.0 else float(np.dot(x0, y0) / denom)
    w = np.asarray(weights, dtype=np.float64)
    if w.shape != x.shape or np.any(w < 0.0):
        raise ValueError("invalid correlation weights")
    total = float(w.sum())
    if total <= 0.0:
        return None
    mx = float(np.dot(w, x) / total); my = float(np.dot(w, y) / total)
    x0 = x - mx; y0 = y - my
    denom = np.sqrt(np.dot(w, x0 * x0) * np.dot(w, y0 * y0))
    return None if denom == 0.0 else float(np.dot(w, x0 * y0) / denom)


def model_blocks(path: str | Path, extras: int) -> dict[str, np.ndarray | int]:
    raw, scale, n_pat, n_ext = open_model(path, extras)
    values = np.asarray(raw, dtype=np.float64) / float(scale)
    return {
        "scale": int(scale), "n_pat": int(n_pat), "n_ext": int(n_ext),
        "pattern_mg": values[:n_pat],
        "pattern_eg": values[n_pat:2 * n_pat],
        "dense_mg": values[2 * n_pat:2 * n_pat + n_ext],
        "dense_eg": values[2 * n_pat + n_ext:],
        "raw": raw,
    }


def pair_family_stats(left: dict, right: dict) -> dict:
    report = {}
    for family in ("pattern_mg", "pattern_eg", "dense_mg", "dense_eg"):
        a = np.asarray(left[family], dtype=np.float64)
        b = np.asarray(right[family], dtype=np.float64)
        report[family] = {
            "rms_left": rms(a),
            "rms_right": rms(b),
            "rms_difference": rms(b - a),
            "correlation": correlation(a, b),
        }
    return report


def pattern_visits(records: np.memmap, train_count: int, chunk: int) -> np.ndarray:
    n_pat = patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN
    counts = np.zeros(n_pat, dtype=np.int64)
    offsets = np.arange(patterns.NUM_PATTERNS, dtype=np.int64) * patterns.BUCKETS_PER_PATTERN
    for lo in range(0, train_count, chunk):
        hi = min(lo + chunk, train_count)
        rec = records[lo:hi]
        cols = patterns.extract_indices(
            np.ascontiguousarray(rec["bm"]), np.ascontiguousarray(rec["wm"])
        ) + offsets[None, :]
        counts += np.bincount(cols.ravel(), minlength=n_pat)
    return counts


def visit_quantile_correlation(
    left: dict, right: dict, visits: np.ndarray, quantiles: int
) -> dict:
    visited = np.flatnonzero(visits > 0)
    if not len(visited):
        raise ValueError("CURRENT training rows visit no pattern buckets")
    order = visited[np.argsort(visits[visited], kind="stable")]
    groups = np.array_split(order, quantiles)
    rows = []
    for index, group in enumerate(groups):
        w = visits[group].astype(np.float64)
        rows.append({
            "quantile": index + 1,
            "buckets": int(len(group)),
            "visit_min": int(visits[group].min()),
            "visit_max": int(visits[group].max()),
            "visits": int(visits[group].sum()),
            "pattern_mg_correlation": correlation(left["pattern_mg"][group], right["pattern_mg"][group], w),
            "pattern_eg_correlation": correlation(left["pattern_eg"][group], right["pattern_eg"][group], w),
        })
    return {
        "visited_buckets": int(len(visited)),
        "quantiles": rows,
        "overall_visit_weighted_pattern_mg_correlation": correlation(
            left["pattern_mg"][visited], right["pattern_mg"][visited], visits[visited]
        ),
        "overall_visit_weighted_pattern_eg_correlation": correlation(
            left["pattern_eg"][visited], right["pattern_eg"][visited], visits[visited]
        ),
    }


def score_components(
    model: dict,
    records: np.memmap,
    feat: np.memmap,
    start: int,
    chunk: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(records) - start
    pattern_score = np.empty(n, dtype=np.float64)
    dense_score = np.empty(n, dtype=np.float64)
    offsets = np.arange(patterns.NUM_PATTERNS, dtype=np.int64) * patterns.BUCKETS_PER_PATTERN
    for lo in range(start, len(records), chunk):
        hi = min(lo + chunk, len(records))
        rec = records[lo:hi]
        wm = np.ascontiguousarray(rec["wm"])
        bm = np.ascontiguousarray(rec["bm"])
        cols = patterns.extract_indices(bm, wm) + offsets[None, :]
        pmg = np.asarray(model["pattern_mg"])[cols].sum(axis=1)
        peg = np.asarray(model["pattern_eg"])[cols].sum(axis=1)
        extras = np.asarray(feat[lo:hi], dtype=np.float64)
        dmg = extras @ np.asarray(model["dense_mg"], dtype=np.float64)
        deg = extras @ np.asarray(model["dense_eg"], dtype=np.float64)
        wmg = eval_phase.tempo_wmg_bb(wm, bm).astype(np.float64)
        sl = slice(lo - start, hi - start)
        pattern_score[sl] = wmg * pmg + (1.0 - wmg) * peg
        dense_score[sl] = wmg * dmg + (1.0 - wmg) * deg
    return pattern_score + dense_score, pattern_score, dense_score


def variance_decomposition(pattern_delta: np.ndarray, dense_delta: np.ndarray) -> dict:
    p = np.asarray(pattern_delta, dtype=np.float64)
    d = np.asarray(dense_delta, dtype=np.float64)
    vp = float(np.var(p)); vd = float(np.var(d)); cov2 = float(2.0 * np.cov(p, d, ddof=0)[0, 1])
    total = float(np.var(p + d))
    return {
        "pattern_variance": vp,
        "dense_variance": vd,
        "twice_covariance": cov2,
        "total_variance": total,
        "identity_residual": total - (vp + vd + cov2),
    }


def parse_model(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    name, path = value.split("=", 1)
    return name, path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--feat", required=True)
    parser.add_argument("--train-count", type=int, required=True)
    parser.add_argument("--model", action="append", type=parse_model, required=True)
    parser.add_argument("--chunk", type=int, default=20000)
    parser.add_argument("--visit-quantiles", type=int, default=5)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    model_paths = dict(args.model)
    if set(model_paths) != {"C", "CURRICULUM", "SCAN_EXACT"} or len(model_paths) != len(args.model):
        raise SystemExit("models must be exactly C, CURRICULUM and SCAN_EXACT")
    records = open_jnnw(args.data)
    if not 0 < args.train_count < len(records):
        raise SystemExit("invalid train count")
    feat = open_feat(args.feat, len(records))
    models = {name: model_blocks(path, feat.shape[1]) for name, path in model_paths.items()}
    visits = pattern_visits(records, args.train_count, args.chunk)

    scores = {}
    for name, model in models.items():
        scores[name] = score_components(model, records, feat, args.train_count, args.chunk)

    pairs = {}
    for left, right in (("C", "CURRICULUM"), ("C", "SCAN_EXACT"), ("CURRICULUM", "SCAN_EXACT")):
        total_l = scores[left][0]; total_r = scores[right][0]
        pairs[f"{right}_vs_{left}"] = {
            "families": pair_family_stats(models[left], models[right]),
            "holdout_score": {
                "n": int(len(total_l)),
                "correlation": correlation(total_l, total_r),
                "rms_difference": rms(total_r - total_l),
            },
            "current_visit_frequency": visit_quantile_correlation(
                models[left], models[right], visits, args.visit_quantiles
            ),
        }

    raw_models = {}
    i32_max = float(np.iinfo(np.int32).max)
    for name, path in model_paths.items():
        raw = np.asarray(models[name]["raw"], dtype=np.int64)
        abs_raw = np.abs(raw.astype(np.float64))
        raw_models[name] = {
            "path": path,
            "sha256": sha256_file(path),
            "bytes": Path(path).stat().st_size,
            "scale": models[name]["scale"],
            "n_pat": models[name]["n_pat"],
            "n_ext": models[name]["n_ext"],
            "nonzero": int(np.count_nonzero(raw)),
            "zero_fraction": float(np.mean(raw == 0)),
            "max_abs_raw": int(abs_raw.max()),
            "p99_abs_raw": float(np.quantile(abs_raw, 0.99)),
            "i32_saturation_fraction": float(np.mean(abs_raw >= i32_max)),
            "family_rms": {family: rms(models[name][family]) for family in ("pattern_mg", "pattern_eg", "dense_mg", "dense_eg")},
        }

    scan_total, scan_pat, scan_dense = scores["SCAN_EXACT"]
    c_total, c_pat, c_dense = scores["C"]
    report = {
        "schema": "jass.sb1.weight_audit.v1",
        "role": "read_only_explanatory_no_gate_no_tuning",
        "inputs": {
            "data": {"path": args.data, "sha256": sha256_file(args.data), "records": int(len(records))},
            "feat": {"path": args.feat, "sha256": sha256_file(args.feat), "width": int(feat.shape[1])},
            "train_count": args.train_count,
            "holdout_count": int(len(records) - args.train_count),
        },
        "models": raw_models,
        "pairwise": pairs,
        "scan_exact_minus_c_score_variance": variance_decomposition(
            scan_pat - c_pat, scan_dense - c_dense
        ),
        "scan_exact_minus_c_holdout": {
            "score_rms_difference": rms(scan_total - c_total),
            "pattern_component_rms_difference": rms(scan_pat - c_pat),
            "dense_component_rms_difference": rms(scan_dense - c_dense),
        },
        "markers": {
            "SCIENTIFIC_DECISION": False,
            "SELECTION": False,
            "RETUNING": False,
            "FRESH_DATA": False,
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
