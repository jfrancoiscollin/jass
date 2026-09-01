#!/usr/bin/env python3
"""Stream exact-fold PatternEval Fisher/gradient diagnostics on JFI data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np

TOOLS = Path(__file__).resolve().parents[2] / "pattern_jass" / "tools"
geometry = os.environ.get("JASS_PATTERNS_DIR")
if geometry:
    sys.path.insert(0, geometry)
sys.path.insert(0, str(TOOLS))
import eval_phase  # noqa: E402
import patterns  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jass_megacorpus_static_readout import (  # noqa: E402
    JNNW_DTYPE, open_counted, open_feat, open_model, score_model, stable_sigmoid,
)


def add_sparse(accumulator, columns, weights):
    np.add.at(accumulator, np.asarray(columns, dtype=np.int64).ravel(),
              np.asarray(weights, dtype=np.float64).ravel())


def quantiles(values):
    return np.quantile(np.asarray(values, dtype=np.float64), [0, .25, .5, .75, .9, .99, 1]).tolist()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fold_exact_model(raw_model, scale, folder, extras):
    """Project an expanded PJTW back into the exact-fold canonical layout."""
    n_pat = patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN
    mg_full = np.asarray(raw_model[:n_pat], dtype=np.float64) / scale
    eg_full = np.asarray(raw_model[n_pat:2*n_pat], dtype=np.float64) / scale
    canonical = folder.rf_canon.ravel()
    signs = folder.rf_sign.ravel().astype(np.float64)
    counts = np.bincount(canonical, minlength=n_pat).astype(np.float64)
    counts[counts == 0] = 1.0
    mg = np.bincount(canonical, weights=signs * mg_full, minlength=n_pat) / counts
    eg = np.bincount(canonical, weights=signs * eg_full, minlength=n_pat) / counts
    dense_mg = np.asarray(raw_model[2*n_pat:2*n_pat+extras], dtype=np.float64) / scale
    dense_eg = np.asarray(raw_model[2*n_pat+extras:], dtype=np.float64) / scale
    return np.concatenate((mg, eg, dense_mg, dense_eg))


def main(argv=None):
    from train_stream import Folder

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--feat", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--train-count", required=True, type=int)
    ap.add_argument("--l2", required=True, type=float)
    ap.add_argument("--chunk", type=int, default=20_000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fisher-out", required=True)
    ap.add_argument("--diagnostics-out", required=True)
    args = ap.parse_args(argv)
    if not args.l2 > 0:
        raise SystemExit("selected JFI lambda must be positive")
    records, count = open_counted(args.data, {b"JNNW": JNNW_DTYPE})
    feat = open_feat(args.feat, count)
    targets = np.load(args.targets, allow_pickle=False, mmap_mode="r")
    if targets.shape != (count,) or not 0 < args.train_count < count:
        raise SystemExit("input alignment/split drift")
    folder = Folder("exact")
    n_pat = patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN
    extras = feat.shape[1]
    n_cols = 2 * (n_pat + extras)
    visits = np.zeros(n_cols, dtype=np.int64)
    squared = np.zeros(n_cols, dtype=np.float64)
    fisher = np.zeros(n_cols, dtype=np.float64)
    gradient = np.zeros(n_cols, dtype=np.float64)
    logits = score_model(args.model, records, feat, 0, args.chunk)[:args.train_count]
    probability = stable_sigmoid(logits)
    residual_all = probability - np.asarray(targets[:args.train_count], dtype=np.float64)
    curvature_all = probability * (1.0 - probability)

    for lo in range(0, args.train_count, args.chunk):
        hi = min(lo + args.chunk, args.train_count)
        rec = records[lo:hi]
        wm = np.ascontiguousarray(rec["wm"]); bm = np.ascontiguousarray(rec["bm"])
        columns, signs = folder.cols_signs(bm, wm)
        wmg = eval_phase.tempo_wmg_bb(wm, bm).astype(np.float64); weg = 1.0 - wmg
        residual = residual_all[lo:hi]; curvature = curvature_all[lo:hi]
        for offset, phase in ((0, wmg), (n_pat, weg)):
            design = signs.astype(np.float64) * phase[:, None]
            flat_columns = columns + offset
            np.add.at(visits, flat_columns.ravel(), 1)
            add_sparse(squared, flat_columns, design * design)
            add_sparse(fisher, flat_columns, design * design * curvature[:, None])
            add_sparse(gradient, flat_columns, design * residual[:, None])
        raw_extras = np.asarray(feat[lo:hi], dtype=np.float64)
        for offset, phase in ((2 * n_pat, wmg), (2 * n_pat + extras, weg)):
            design = raw_extras * phase[:, None]
            block = slice(offset, offset + extras)
            visits[block] += np.count_nonzero(raw_extras, axis=0)
            squared[block] += np.sum(design * design, axis=0)
            fisher[block] += np.sum(design * design * curvature[:, None], axis=0)
            gradient[block] += design.T @ residual

    squared /= args.train_count
    fisher /= args.train_count
    gradient /= args.train_count
    ratio = fisher / args.l2
    unseen = visits == 0
    prior_dominated = (~unseen) & (ratio < 0.1)
    data_dominated = ratio > 10.0
    mixed = ~(unseen | prior_dominated | data_dominated)
    posterior_variance = 1.0 / (fisher + args.l2)
    effective = fisher / (fisher + args.l2)
    zero_information = fisher == 0
    raw_model, scale, _model_n_pat = open_model(args.model, extras)
    canonical_model = fold_exact_model(raw_model, scale, folder, extras)
    ridge_gradient_norm = float(args.l2 * np.linalg.norm(canonical_model))
    np.save(args.fisher_out, fisher.astype(np.float32), allow_pickle=False)
    class_code = np.full(n_cols, 2, dtype=np.uint8)
    class_code[unseen] = 0
    class_code[prior_dominated] = 1
    class_code[data_dominated] = 3
    np.savez_compressed(
        args.diagnostics_out,
        visits=visits.astype(np.uint32),
        squared_design=squared.astype(np.float32),
        fisher=fisher.astype(np.float32),
        data_gradient=gradient.astype(np.float32),
        data_to_l2_precision=ratio.astype(np.float32),
        posterior_variance_proxy=posterior_variance.astype(np.float32),
        identifiability_class=class_code,
    )
    families = {
        "pattern_mg": slice(0, n_pat), "pattern_eg": slice(n_pat, 2*n_pat),
        "dense_mg": slice(2*n_pat, 2*n_pat+extras), "dense_eg": slice(2*n_pat+extras, n_cols),
    }
    family_report = {}
    for name, block in families.items():
        family_report[name] = {
            "coordinates": int(len(fisher[block])),
            "unseen_fraction": float(np.mean(unseen[block])),
            "data_dominated_fraction": float(np.mean(data_dominated[block])),
            "fisher_quantiles": quantiles(fisher[block]),
            "gradient_l2_norm": float(np.linalg.norm(gradient[block])),
            "effective_df": float(np.sum(effective[block])),
        }
    report = {
        "schema": "jass.jfi.patterneval_identifiability.v1",
        "records": args.train_count,
        "coordinates": n_cols,
        "selected_l2": args.l2,
        "class_counts": {
            "UNSEEN": int(np.count_nonzero(unseen)),
            "PRIOR_DOMINATED": int(np.count_nonzero(prior_dominated)),
            "MIXED": int(np.count_nonzero(mixed)),
            "DATA_DOMINATED": int(np.count_nonzero(data_dominated)),
        },
        "fisher_quantiles": quantiles(fisher),
        "posterior_variance_proxy_quantiles": quantiles(posterior_variance),
        "effective_df": float(np.sum(effective)),
        "data_gradient_l2_norm": float(np.linalg.norm(gradient)),
        "ridge_gradient_l2_norm": ridge_gradient_norm,
        "data_to_ridge_gradient_ratio": (
            float(np.linalg.norm(gradient) / ridge_gradient_norm)
            if ridge_gradient_norm > 0 else None
        ),
        "families": family_report,
        "zero_l2_diagnostic_convention": {
            "infinite_posterior_variance_coordinates": int(np.count_nonzero(zero_information)),
            "finite_posterior_variance_quantiles": quantiles(1.0 / fisher[~zero_information]),
            "effective_df": float(np.count_nonzero(~zero_information)),
            "zero_information_effective_df_contribution": 0.0,
        },
        "fisher_file": {
            "path": args.fisher_out, "sha256": sha256_file(args.fisher_out),
            "dtype": "float32", "shape": [n_cols],
        },
        "per_coordinate_file": {
            "path": args.diagnostics_out, "sha256": sha256_file(args.diagnostics_out),
            "format": "npz", "class_codes": {
                "0": "UNSEEN", "1": "PRIOR_DOMINATED", "2": "MIXED", "3": "DATA_DOMINATED",
            },
        },
        "markers": {"TARGET_READS": 1, "SCAN_READS": 0},
    }
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
