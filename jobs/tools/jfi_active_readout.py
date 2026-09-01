#!/usr/bin/env python3
"""Frozen JFI-C ACTIVE-vs-UNIFORM common-DEV readout and gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from jass_megacorpus_static_readout import (  # noqa: E402
    JNNW_DTYPE, JSM1_DTYPE, JSM2_DTYPE, cluster_bootstrap_effect, loss_vector,
    metrics, open_counted, open_feat, score_model,
)


BOOTSTRAP_SAMPLES = 100_000
BOOTSTRAP_SEED = 2026120104
STATE_FIELDS = ("wm", "wk", "bm", "bk", "stm")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identifiability_scalars(report):
    coordinates = int(report["coordinates"])
    counts = report["class_counts"]
    posterior = report["posterior_variance_proxy_quantiles"]
    if coordinates <= 0 or sum(int(value) for value in counts.values()) != coordinates:
        raise ValueError("identifiability class-count drift")
    if len(posterior) != 7 or not np.all(np.isfinite(posterior)):
        raise ValueError("identifiability posterior-variance quantile drift")
    return {
        "effective_df": float(report["effective_df"]),
        "data_dominated_fraction": float(counts["DATA_DOMINATED"] / coordinates),
        "posterior_variance_proxy_median": float(posterior[2]),
        "coordinates": coordinates,
        "selected_l2": float(report["selected_l2"]),
        "records": int(report["records"]),
    }


def compare_identifiability(active, uniform):
    a = identifiability_scalars(active)
    u = identifiability_scalars(uniform)
    if a["coordinates"] != u["coordinates"] or a["selected_l2"] != u["selected_l2"]:
        raise ValueError("ACTIVE/UNIFORM identifiability geometry drift")
    diagnostics = {
        "effective_df_active_gt_uniform": a["effective_df"] > u["effective_df"],
        "data_dominated_fraction_active_gt_uniform": (
            a["data_dominated_fraction"] > u["data_dominated_fraction"]
        ),
        "posterior_variance_proxy_median_active_lt_uniform": (
            a["posterior_variance_proxy_median"] < u["posterior_variance_proxy_median"]
        ),
    }
    return a, u, diagnostics, bool(any(diagnostics.values()))


def aligned_dev(active_records, active_meta, active_feat, active_targets,
                uniform_records, uniform_meta, uniform_feat, uniform_targets,
                train_count, chunk):
    count = len(active_records)
    if (
        len(uniform_records) != count or len(active_meta) != count
        or len(uniform_meta) != count or active_feat.shape != uniform_feat.shape
        or active_meta.dtype != uniform_meta.dtype
        or active_targets.shape != (count,) or uniform_targets.shape != (count,)
        or not 0 < train_count < count
    ):
        raise ValueError("ACTIVE/UNIFORM arm alignment drift")
    for lo in range(train_count, count, chunk):
        hi = min(lo + chunk, count)
        for field in STATE_FIELDS:
            if not np.array_equal(active_records[lo:hi][field], uniform_records[lo:hi][field]):
                raise ValueError(f"common DEV state drift in {field}")
        for field in active_meta.dtype.names:
            if not np.array_equal(active_meta[lo:hi][field], uniform_meta[lo:hi][field]):
                raise ValueError(f"common DEV metadata drift in {field}")
        if not np.array_equal(active_feat[lo:hi], uniform_feat[lo:hi]):
            raise ValueError("common DEV feature drift")
        if not np.array_equal(active_targets[lo:hi], uniform_targets[lo:hi]):
            raise ValueError("common DEV target drift")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for arm in ("active", "uniform"):
        ap.add_argument(f"--{arm}-data", required=True)
        ap.add_argument(f"--{arm}-meta", required=True)
        ap.add_argument(f"--{arm}-feat", required=True)
        ap.add_argument(f"--{arm}-targets", required=True)
        ap.add_argument(f"--{arm}-model", required=True)
        ap.add_argument(f"--{arm}-identifiability", required=True)
    ap.add_argument("--train-count", type=int, required=True)
    ap.add_argument("--bootstrap-samples", type=int, default=BOOTSTRAP_SAMPLES)
    ap.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    ap.add_argument("--chunk", type=int, default=20_000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.bootstrap_samples != BOOTSTRAP_SAMPLES or args.bootstrap_seed != BOOTSTRAP_SEED:
        raise SystemExit("JFI-C bootstrap contract drift")

    arm = {}
    for name in ("active", "uniform"):
        records, count = open_counted(getattr(args, f"{name}_data"), {b"JNNW": JNNW_DTYPE})
        metadata, meta_count = open_counted(
            getattr(args, f"{name}_meta"), {b"JSM1": JSM1_DTYPE, b"JSM2": JSM2_DTYPE},
        )
        features = open_feat(getattr(args, f"{name}_feat"), count)
        target = np.load(getattr(args, f"{name}_targets"), allow_pickle=False, mmap_mode="r")
        if meta_count != count:
            raise SystemExit(f"{name} data/metadata count drift")
        arm[name] = (records, metadata, features, target)

    aligned_dev(*arm["active"], *arm["uniform"], args.train_count, args.chunk)
    active_records, active_meta, active_feat, active_target = arm["active"]
    uniform_records, _uniform_meta, uniform_feat, _uniform_target = arm["uniform"]
    active_logits = score_model(
        args.active_model, active_records, active_feat, args.train_count, args.chunk,
    )
    uniform_logits = score_model(
        args.uniform_model, uniform_records, uniform_feat, args.train_count, args.chunk,
    )
    dev_target = np.asarray(active_target[args.train_count:], dtype=np.float64)
    delta = loss_vector(active_logits, dev_target) - loss_vector(uniform_logits, dev_target)
    openings = np.asarray(active_meta[args.train_count:]["opening_id"], dtype=np.uint64)
    bootstrap = cluster_bootstrap_effect(
        delta, openings, samples=args.bootstrap_samples, seed=args.bootstrap_seed,
    )

    active_ident = json.loads(Path(args.active_identifiability).read_text())
    uniform_ident = json.loads(Path(args.uniform_identifiability).read_text())
    active_scalar, uniform_scalar, diagnostics, information_pass = compare_identifiability(
        active_ident, uniform_ident,
    )
    if active_scalar["records"] != args.train_count or uniform_scalar["records"] != args.train_count:
        raise SystemExit("identifiability train-count drift")
    ce_pass = bootstrap["ci_high"] < 0.0
    passed = bool(ce_pass and information_pass)
    report = {
        "schema": "jass.jfi.c_active_vs_uniform.v1",
        "verdict": (
            "JFI_ACTIVE_INFORMATION_GAIN_ESTABLISHED" if passed
            else "JFI_ACTIVE_INFORMATION_GAIN_NOT_ESTABLISHED"
        ),
        "gate": {
            "delta_ce_active_minus_uniform": bootstrap,
            "ci95_high_lt_zero": ce_pass,
            "at_least_one_information_diagnostic_improves": information_pass,
            "pass": passed,
        },
        "dev": {
            "rows": int(len(dev_target)), "unique_openings": int(len(np.unique(openings))),
            "common_state_metadata_features_targets_exact": True,
            "active": metrics(active_logits, dev_target),
            "uniform": metrics(uniform_logits, dev_target),
        },
        "identifiability": {
            "active": active_scalar, "uniform": uniform_scalar,
            "predicted_direction_tests": diagnostics,
            "posterior_scalar": "median over all coordinates of 1/(F_j+lambda)",
        },
        "files": {
            "active_model": {"path": args.active_model, "sha256": sha256_file(args.active_model)},
            "uniform_model": {"path": args.uniform_model, "sha256": sha256_file(args.uniform_model)},
            "active_targets": {"path": args.active_targets, "sha256": sha256_file(args.active_targets)},
            "uniform_targets": {"path": args.uniform_targets, "sha256": sha256_file(args.uniform_targets)},
        },
        "markers": {
            "TARGET_READS_BEFORE_SELECTION_FREEZE": 0, "SCAN_READS": 0,
            "FRESH_OPENINGS": 0, "STRENGTH_GAMES": 0,
        },
        "next_boundary": "GO JFI CANDIDATE" if passed else None,
    }
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
