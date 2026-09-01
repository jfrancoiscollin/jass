#!/usr/bin/env python3
"""JFI-A path-independence and JFI-B frozen one-SE readout."""
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
    JNNW_DTYPE, JSM1_DTYPE, JSM2_DTYPE, loss_vector, open_counted, open_feat,
    open_model, score_model, stable_sigmoid,
)

L2_BOOTSTRAP_SAMPLES = 100_000
L2_BOOTSTRAP_SEED = 2026120101
PATH_RMS_LIMIT = 0.5
PATH_MAX_ABS_LIMIT = 2.0
# The preregistration leaves "compatible with optimizer tolerance" operational.
# This absolute objective tolerance is frozen before any full-fit metric is read.
OBJECTIVE_ABS_LIMIT = 1e-6
PARAMETER_CHUNK = 1_000_000


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clustered_bootstrap_means(values, clusters, samples, seed):
    values = np.asarray(values, dtype=np.float64)
    clusters = np.asarray(clusters)
    if values.shape != clusters.shape or not len(values):
        raise ValueError("values/clusters must be aligned and non-empty")
    unique, inverse = np.unique(clusters, return_inverse=True)
    sums = np.bincount(inverse, weights=values).astype(np.float64)
    counts = np.bincount(inverse).astype(np.float64)
    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=np.float64)
    batch = max(1, min(1024, 2_000_000 // len(unique)))
    for start in range(0, samples, batch):
        stop = min(start + batch, samples)
        selected = rng.integers(0, len(unique), size=(stop - start, len(unique)))
        draws[start:stop] = sums[selected].sum(axis=1) / counts[selected].sum(axis=1)
    return draws


def select_positive_l2_one_se(losses_by_l2, clusters, samples=L2_BOOTSTRAP_SAMPLES,
                              seed=L2_BOOTSTRAP_SEED):
    positive = sorted(value for value in losses_by_l2 if value > 0)
    if not positive:
        raise ValueError("at least one positive lambda is required")
    means = {value: float(np.mean(losses_by_l2[value])) for value in losses_by_l2}
    best = min(positive, key=lambda value: (means[value], value))
    draws = clustered_bootstrap_means(losses_by_l2[best], clusters, samples, seed)
    best_se = float(np.std(draws, ddof=1))
    threshold = means[best] + best_se
    eligible = [value for value in positive if means[value] <= threshold]
    selected = max(eligible)
    return {
        "best_positive_l2": best,
        "best_positive_ce": means[best],
        "best_cluster_bootstrap_se": best_se,
        "one_se_threshold": threshold,
        "eligible_positive_l2": eligible,
        "selected_l2": selected,
        "mean_ce": {str(value): means[value] for value in sorted(means)},
        "bootstrap_samples": samples,
        "bootstrap_seed": seed,
        "zero_l2_diagnostic_only": 0.0 in losses_by_l2,
    }


def path_pair(left_scores, right_scores, left_objective, right_objective,
              holdout_start=0):
    delta = np.asarray(right_scores, dtype=np.float64) - np.asarray(
        left_scores, dtype=np.float64
    )
    holdout = delta[holdout_start:]
    if not len(holdout):
        raise ValueError("path comparison requires a non-empty holdout")
    objective_delta = abs(float(right_objective) - float(left_objective))
    report = {
        "holdout_score_rms": float(np.sqrt(np.mean(holdout * holdout))),
        "serialized_score_max_abs": float(np.max(np.abs(delta))),
        "objective_abs_difference": objective_delta,
    }
    report["score_rms"] = report["holdout_score_rms"]
    report["pass"] = bool(
        report["holdout_score_rms"] <= PATH_RMS_LIMIT
        and report["serialized_score_max_abs"] <= PATH_MAX_ABS_LIMIT
        and objective_delta <= OBJECTIVE_ABS_LIMIT
    )
    return report


def assignment(value):
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    return value.split("=", 1)


def l2_assignment(value):
    raw, path = assignment(value)
    return float(raw), path


def family_ranges(total, extras, pattern_coordinates):
    expected = 2 * (pattern_coordinates + extras)
    if total != expected:
        raise ValueError(f"parameter geometry drift: {total} != {expected}")
    return {
        "pattern_mg": (0, pattern_coordinates),
        "pattern_eg": (pattern_coordinates, 2 * pattern_coordinates),
        "dense_mg": (2 * pattern_coordinates, 2 * pattern_coordinates + extras),
        "dense_eg": (2 * pattern_coordinates + extras, expected),
    }


def vector_comparison(left, right, *, left_scale=1.0, right_scale=1.0,
                      ranges=None):
    if left.shape != right.shape or left.ndim != 1:
        raise ValueError("parameter vectors are not aligned")
    sums = {name: 0.0 for name in (ranges or {})}
    counts = {name: stop - start for name, (start, stop) in (ranges or {}).items()}
    squared = 0.0
    changed = 0
    maximum = 0.0
    for lo in range(0, len(left), PARAMETER_CHUNK):
        hi = min(lo + PARAMETER_CHUNK, len(left))
        left_chunk = np.asarray(left[lo:hi], dtype=np.float64) / left_scale
        right_chunk = np.asarray(right[lo:hi], dtype=np.float64) / right_scale
        delta = right_chunk - left_chunk
        squared += float(np.dot(delta, delta))
        changed += int(np.count_nonzero(delta))
        maximum = max(maximum, float(np.max(np.abs(delta), initial=0.0)))
        for name, (start, stop) in (ranges or {}).items():
            overlap_start = max(lo, start)
            overlap_stop = min(hi, stop)
            if overlap_start < overlap_stop:
                part = delta[overlap_start - lo:overlap_stop - lo]
                sums[name] += float(np.dot(part, part))
    result = {
        "rms": float(np.sqrt(squared / len(left))),
        "max_abs": maximum,
        "changed_coordinates": changed,
        "changed_fraction": float(changed / len(left)),
    }
    if ranges:
        result["family_rms"] = {
            name: float(np.sqrt(sums[name] / counts[name])) for name in ranges
        }
    return result


def arm_metrics(path, raw_path, scores, targets, train_count, extras):
    weights, scale, pattern_coordinates = open_model(path, extras)
    raw = np.load(raw_path, allow_pickle=False, mmap_mode="r")
    if raw.ndim != 1 or (len(raw) - 2 * extras) % 2:
        raise ValueError(f"{raw_path}: raw optimizer geometry drift")
    train_scores = scores[:train_count]
    holdout_scores = scores[train_count:]
    train_targets = targets[:train_count]
    holdout_targets = targets[train_count:]
    probabilities = stable_sigmoid(scores)
    return {
        "pjtw": {
            "path": path,
            "sha256": sha256_file(path),
            "scale": scale,
            "coordinates": int(len(weights)),
            "exact_reload": True,
        },
        "raw_weights": {
            "path": raw_path,
            "sha256": sha256_file(raw_path),
            "coordinates": int(len(raw)),
        },
        "train_ce": float(np.mean(loss_vector(train_scores, train_targets))),
        "holdout_ce": float(np.mean(loss_vector(holdout_scores, holdout_targets))),
        "score_rms": float(np.sqrt(np.mean(scores * scores))),
        "prediction_rms_vs_target": float(np.sqrt(np.mean((probabilities - targets) ** 2))),
        "pattern_coordinates": int(pattern_coordinates),
    }


def contrast_metrics(left_name, right_name, models, raws, scores, optimizers,
                     targets, train_count, extras):
    left_weights, left_scale, left_n_pat = models[left_name]
    right_weights, right_scale, right_n_pat = models[right_name]
    if left_n_pat != right_n_pat:
        raise ValueError("serialized model geometry drift")
    left_raw = raws[left_name]
    right_raw = raws[right_name]
    raw_pattern_coordinates = len(left_raw) // 2 - extras
    path = path_pair(
        scores[left_name], scores[right_name],
        optimizers[left_name]["final_objective"],
        optimizers[right_name]["final_objective"],
        holdout_start=train_count,
    )
    left_predictions = stable_sigmoid(scores[left_name][train_count:])
    right_predictions = stable_sigmoid(scores[right_name][train_count:])
    path["holdout_prediction_rms"] = float(
        np.sqrt(np.mean((right_predictions - left_predictions) ** 2))
    )
    path["raw_parameter_displacement"] = vector_comparison(
        left_raw, right_raw,
        ranges=family_ranges(len(left_raw), extras, raw_pattern_coordinates),
    )
    path["quantized_parameter_displacement"] = vector_comparison(
        left_weights, right_weights, left_scale=left_scale, right_scale=right_scale,
        ranges=family_ranges(len(left_weights), extras, left_n_pat),
    )
    path["holdout_ce_difference_right_minus_left"] = float(
        np.mean(loss_vector(scores[right_name][train_count:], targets[train_count:]))
        - np.mean(loss_vector(scores[left_name][train_count:], targets[train_count:]))
    )
    return path


def write_json(path, payload):
    if path:
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--feat", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--train-count", required=True, type=int)
    ap.add_argument("--factorial-model", action="append", type=assignment, required=True)
    ap.add_argument("--factorial-raw", action="append", type=assignment, required=True)
    ap.add_argument("--factorial-optimizer", action="append", type=assignment, required=True)
    ap.add_argument("--l2-model", action="append", type=l2_assignment, required=True)
    ap.add_argument("--bootstrap-samples", type=int, default=L2_BOOTSTRAP_SAMPLES)
    ap.add_argument("--bootstrap-seed", type=int, default=L2_BOOTSTRAP_SEED)
    ap.add_argument("--chunk", type=int, default=20_000)
    ap.add_argument("--factorial-out")
    ap.add_argument("--path-out")
    ap.add_argument("--l2-out")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    records, count = open_counted(args.data, {b"JNNW": JNNW_DTYPE})
    meta, meta_count = open_counted(args.meta, {b"JSM1": JSM1_DTYPE, b"JSM2": JSM2_DTYPE})
    feat = open_feat(args.feat, count)
    targets = np.load(args.targets, allow_pickle=False, mmap_mode="r")
    if meta_count != count or targets.shape != (count,) or not 0 < args.train_count < count:
        raise SystemExit("input alignment/split drift")
    openings = np.asarray(meta[args.train_count:]["opening_id"], dtype=np.uint64)
    holdout_targets = np.asarray(targets[args.train_count:], dtype=np.float64)

    factorial_paths = dict(args.factorial_model)
    raw_paths = dict(args.factorial_raw)
    optimizer_paths = dict(args.factorial_optimizer)
    expected_arms = {"A", "B", "C", "D"}
    if set(factorial_paths) != expected_arms or set(raw_paths) != expected_arms:
        raise SystemExit("factorial models/raw weights must be exactly A,B,C,D")
    if set(optimizer_paths) != expected_arms:
        raise SystemExit("factorial optimizers must be exactly A,B,C,D")
    score_cache = {}

    def scores_for(path):
        if path not in score_cache:
            score_cache[path] = score_model(path, records, feat, 0, args.chunk)
        return score_cache[path]

    factorial_scores = {name: scores_for(path) for name, path in factorial_paths.items()}
    optimizers = {name: json.loads(Path(path).read_text()) for name, path in optimizer_paths.items()}
    if not all(item.get("success") and "final_objective" in item for item in optimizers.values()):
        raise SystemExit("factorial optimizer not healthy or lacks final_objective")
    models = {name: open_model(path, feat.shape[1]) for name, path in factorial_paths.items()}
    raws = {
        name: np.load(path, allow_pickle=False, mmap_mode="r") for name, path in raw_paths.items()
    }
    arms = {
        name: {
            **arm_metrics(factorial_paths[name], raw_paths[name], factorial_scores[name],
                          targets, args.train_count, feat.shape[1]),
            "optimizer": optimizers[name],
        }
        for name in sorted(expected_arms)
    }
    contrast_names = {
        "A_vs_B_init_at_curriculum_center": ("A", "B"),
        "C_vs_D_init_at_zero_center": ("C", "D"),
        "A_vs_C_center_at_curriculum_init": ("A", "C"),
        "B_vs_D_center_at_zero_init": ("B", "D"),
    }
    contrasts = {
        name: contrast_metrics(left, right, models, raws, factorial_scores, optimizers,
                               targets, args.train_count, feat.shape[1])
        for name, (left, right) in contrast_names.items()
    }
    path_pairs = {
        "A_vs_B_curriculum_center": contrasts["A_vs_B_init_at_curriculum_center"],
        "C_vs_D_zero_center": contrasts["C_vs_D_init_at_zero_center"],
    }
    path_pass = all(item["pass"] for item in path_pairs.values())

    l2_paths = dict(args.l2_model)
    if set(l2_paths) != {0.0, 1e-6, 1e-5, 1e-4}:
        raise SystemExit("L2 grid drift")
    l2_scores = {value: scores_for(path) for value, path in l2_paths.items()}
    losses = {
        value: loss_vector(scores[args.train_count:], holdout_targets)
        for value, scores in l2_scores.items()
    }
    selection = select_positive_l2_one_se(
        losses, openings, samples=args.bootstrap_samples, seed=args.bootstrap_seed,
    )
    factorial_report = {
        "schema": "jass.jfi.a_factorial_summary.v1",
        "arms": arms,
        "contrasts": contrasts,
        "rows": count,
        "train_rows": args.train_count,
        "holdout_rows": count - args.train_count,
        "markers": {"SCAN_READS": 0, "FRESH_OPENINGS": 0, "STRENGTH_GAMES": 0},
    }
    path_report = {
        "schema": "jass.jfi.a_path_independence.v1",
        "verdict": (
            "JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED" if path_pass
            else "JFI_OPTIMIZER_PATH_DEPENDENCE_DETECTED"
        ),
        "pairs": path_pairs,
        "limits": {
            "holdout_score_rms": PATH_RMS_LIMIT,
            "serialized_score_max_abs": PATH_MAX_ABS_LIMIT,
            "objective_abs_difference": OBJECTIVE_ABS_LIMIT,
        },
        "markers": {"SCAN_READS": 0, "FRESH_OPENINGS": 0, "STRENGTH_GAMES": 0},
    }
    l2_report = {
        "schema": "jass.jfi.b_l2_curve.v1",
        **selection,
        "holdout_rows": int(len(openings)),
        "unique_openings": int(len(np.unique(openings))),
        "markers": {"SCAN_READS": 0, "FRESH_OPENINGS": 0, "STRENGTH_GAMES": 0},
    }
    report = {
        "schema": "jass.jfi.fit_readout.v2",
        "factorial": factorial_report,
        "path_independence": path_report,
        "l2_selection": l2_report,
        "next_boundary": "GO JFI ACTIVE" if path_pass else None,
    }
    write_json(args.factorial_out, factorial_report)
    write_json(args.path_out, path_report)
    write_json(args.l2_out, l2_report)
    write_json(args.out, report)
    return 0 if path_pass else 3


if __name__ == "__main__":
    raise SystemExit(main())
