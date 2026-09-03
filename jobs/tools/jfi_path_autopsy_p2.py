#!/usr/bin/env python3
"""JFI path-dependence autopsy P2: no-refit production-score decomposition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from jass_megacorpus_static_readout import (  # noqa: E402
    JNNW_DTYPE,
    JSM1_DTYPE,
    JSM2_DTYPE,
    loss_vector,
    open_counted,
    open_feat,
    open_model,
    score_model,
)
from jfi_fit_readout import (  # noqa: E402
    family_ranges,
    sha256_file,
    vector_comparison,
)

CE_TOL = 1e-10
SCORE_RMS_TOL = 1e-9
PATH_RMS_LIMIT = 0.5
PATH_MAX_ABS_LIMIT = 2.0
INTERPOLATION_T = (0.0, 0.25, 0.5, 0.75, 1.0)
CONVEX_SLACK = 1e-12
DELTA_THRESHOLDS_CP = (0.1, 0.5, 1.0, 2.0, 5.0)
PAIR_NAMES = {
    "A_vs_B_curriculum_center": ("A", "B"),
    "C_vs_D_zero_center": ("C", "D"),
}
REFERENCE_CONTRAST = {
    "A_vs_B_curriculum_center": "A_vs_B_init_at_curriculum_center",
    "C_vs_D_zero_center": "C_vs_D_init_at_zero_center",
}


def assignment(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    return tuple(value.split("=", 1))  # type: ignore[return-value]


def mean_ce(scores: np.ndarray, targets: np.ndarray) -> float:
    return float(np.mean(loss_vector(scores, targets)))


def endpoint_metrics(scores: np.ndarray, targets: np.ndarray, train_count: int) -> dict:
    return {
        "train_ce": mean_ce(scores[:train_count], targets[:train_count]),
        "holdout_ce": mean_ce(scores[train_count:], targets[train_count:]),
        "score_rms": float(np.sqrt(np.mean(np.asarray(scores, dtype=np.float64) ** 2))),
    }


def abs_delta_summary(delta: np.ndarray) -> dict:
    delta = np.asarray(delta, dtype=np.float64)
    absolute = np.abs(delta)
    qs = np.quantile(absolute, [0.50, 0.90, 0.99, 0.999, 1.0])
    return {
        "rows": int(len(delta)),
        "score_delta_rms": float(np.sqrt(np.mean(delta * delta))),
        "score_delta_max_abs": float(np.max(absolute)),
        "abs_score_delta_quantiles_cp": {
            "p50": float(qs[0]),
            "p90": float(qs[1]),
            "p99": float(qs[2]),
            "p99_9": float(qs[3]),
            "max": float(qs[4]),
        },
        "abs_score_delta_ge_cp_counts": {
            str(threshold): int(np.count_nonzero(absolute >= threshold))
            for threshold in DELTA_THRESHOLDS_CP
        },
    }


def interpolation_curve(left: np.ndarray, right: np.ndarray,
                        targets: np.ndarray, train_count: int) -> dict:
    rows = []
    all_losses = []
    train_losses = []
    holdout_losses = []
    for t in INTERPOLATION_T:
        scores = (1.0 - t) * left + t * right
        all_ce = mean_ce(scores, targets)
        train_ce = mean_ce(scores[:train_count], targets[:train_count])
        holdout_ce = mean_ce(scores[train_count:], targets[train_count:])
        all_losses.append(all_ce)
        train_losses.append(train_ce)
        holdout_losses.append(holdout_ce)
        rows.append({"t": t, "all_ce": all_ce, "train_ce": train_ce, "holdout_ce": holdout_ce})

    def sampled_convex(values: list[float]) -> tuple[bool, list[dict]]:
        checks = []
        passed = True
        for idx in range(1, len(values) - 1):
            bound = 0.5 * (values[idx - 1] + values[idx + 1]) + CONVEX_SLACK
            ok = values[idx] <= bound
            passed = passed and ok
            checks.append({
                "t": INTERPOLATION_T[idx],
                "value": values[idx],
                "neighbor_linear_bound_plus_slack": bound,
                "pass": bool(ok),
            })
        return bool(passed), checks

    all_pass, all_checks = sampled_convex(all_losses)
    train_pass, train_checks = sampled_convex(train_losses)
    holdout_pass, holdout_checks = sampled_convex(holdout_losses)
    return {
        "points": rows,
        "convexity_slack": CONVEX_SLACK,
        "sampled_convex": {
            "all": all_pass,
            "train": train_pass,
            "holdout": holdout_pass,
        },
        "checks": {
            "all": all_checks,
            "train": train_checks,
            "holdout": holdout_checks,
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--feat", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--train-count", required=True, type=int)
    ap.add_argument("--model", action="append", type=assignment, required=True)
    ap.add_argument("--raw", action="append", type=assignment, required=True)
    ap.add_argument("--reference-summary", required=True)
    ap.add_argument("--chunk", type=int, default=20_000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    models = dict(args.model)
    raws = dict(args.raw)
    expected = {"A", "B", "C", "D"}
    if set(models) != expected or set(raws) != expected:
        raise SystemExit("models/raws must be exactly A,B,C,D")

    records, count = open_counted(args.data, {b"JNNW": JNNW_DTYPE})
    _meta, meta_count = open_counted(args.meta, {b"JSM1": JSM1_DTYPE, b"JSM2": JSM2_DTYPE})
    feat = open_feat(args.feat, count)
    targets = np.load(args.targets, allow_pickle=False, mmap_mode="r")
    if meta_count != count or targets.shape != (count,) or not 0 < args.train_count < count:
        raise SystemExit("input alignment/split drift")

    reference = json.loads(Path(args.reference_summary).read_text())
    if reference.get("schema") != "jass.jfi.a_factorial_summary.v1":
        raise SystemExit("reference factorial summary schema drift")

    scores = {
        name: score_model(path, records, feat, 0, args.chunk)
        for name, path in sorted(models.items())
    }
    endpoint = {}
    endpoint_reproduction = True
    for name in sorted(expected):
        got = endpoint_metrics(scores[name], targets, args.train_count)
        ref = reference["arms"][name]
        checks = {
            "train_ce": abs(got["train_ce"] - float(ref["train_ce"])) <= CE_TOL,
            "holdout_ce": abs(got["holdout_ce"] - float(ref["holdout_ce"])) <= CE_TOL,
            "score_rms": abs(got["score_rms"] - float(ref["score_rms"])) <= SCORE_RMS_TOL,
        }
        serialized_sha = sha256_file(models[name])
        raw_sha = sha256_file(raws[name])
        hash_checks = {
            "pjtw": serialized_sha == ref["pjtw"]["sha256"],
            "raw": raw_sha == ref["raw_weights"]["sha256"],
        }
        ok = all(checks.values()) and all(hash_checks.values())
        endpoint_reproduction = endpoint_reproduction and ok
        endpoint[name] = {
            "computed": got,
            "reference": {
                "train_ce": ref["train_ce"],
                "holdout_ce": ref["holdout_ce"],
                "score_rms": ref["score_rms"],
            },
            "absolute_tolerances": {"ce": CE_TOL, "score_rms_cp": SCORE_RMS_TOL},
            "checks": checks,
            "hashes": {
                "pjtw": serialized_sha,
                "raw": raw_sha,
                "reference_pjtw": ref["pjtw"]["sha256"],
                "reference_raw": ref["raw_weights"]["sha256"],
                "checks": hash_checks,
            },
            "reproduced": bool(ok),
        }

    pair_reports = {}
    material_score_effect = False
    for pair_name, (left_name, right_name) in PAIR_NAMES.items():
        left = np.asarray(scores[left_name], dtype=np.float64)
        right = np.asarray(scores[right_name], dtype=np.float64)
        delta = right - left
        train_stats = abs_delta_summary(delta[:args.train_count])
        holdout_stats = abs_delta_summary(delta[args.train_count:])
        all_max = float(np.max(np.abs(delta)))
        score_limits_pass = bool(
            holdout_stats["score_delta_rms"] <= PATH_RMS_LIMIT
            and all_max <= PATH_MAX_ABS_LIMIT
        )
        material_score_effect = material_score_effect or not score_limits_pass

        left_ser, left_scale, left_pat_n = open_model(models[left_name], feat.shape[1])
        right_ser, right_scale, right_pat_n = open_model(models[right_name], feat.shape[1])
        if left_pat_n != right_pat_n:
            raise SystemExit("serialized model geometry drift")
        left_raw = np.load(raws[left_name], allow_pickle=False, mmap_mode="r")
        right_raw = np.load(raws[right_name], allow_pickle=False, mmap_mode="r")
        if left_raw.shape != right_raw.shape or left_raw.ndim != 1:
            raise SystemExit("raw model geometry drift")
        raw_pat_n = len(left_raw) // 2 - feat.shape[1]
        recomputed = {
            "raw_parameter_displacement": vector_comparison(
                left_raw,
                right_raw,
                ranges=family_ranges(len(left_raw), feat.shape[1], raw_pat_n),
            ),
            "quantized_parameter_displacement": vector_comparison(
                left_ser,
                right_ser,
                left_scale=left_scale,
                right_scale=right_scale,
                ranges=family_ranges(len(left_ser), feat.shape[1], left_pat_n),
            ),
        }
        ref_contrast = reference["contrasts"][REFERENCE_CONTRAST[pair_name]]
        pair_reports[pair_name] = {
            "left": left_name,
            "right": right_name,
            "train_score_delta": train_stats,
            "holdout_score_delta": holdout_stats,
            "serialized_score_max_abs_all_rows": all_max,
            "original_limits": {
                "holdout_score_rms": PATH_RMS_LIMIT,
                "serialized_score_max_abs": PATH_MAX_ABS_LIMIT,
            },
            "original_score_limits_pass": score_limits_pass,
            "interpolation": interpolation_curve(left, right, targets, args.train_count),
            "parameter_displacement_recomputed": recomputed,
            "parameter_displacement_reference": {
                "raw_parameter_displacement": ref_contrast["raw_parameter_displacement"],
                "quantized_parameter_displacement": ref_contrast["quantized_parameter_displacement"],
            },
        }

    if not endpoint_reproduction:
        verdict = "JFI_PATH_DEPENDENCE_AUTOPSY_TECHNICAL_INCONCLUSIVE"
        p3_authorized = False
    elif material_score_effect:
        verdict = "JFI_PATH_DEPENDENCE_MATERIAL_SCORE_EFFECT_CONFIRMED"
        p3_authorized = False
    else:
        verdict = "JFI_PATH_AUTOPSY_P2_READY_FOR_P3"
        p3_authorized = True

    payload = {
        "schema": "jass.jfi.path_autopsy.p2.v1",
        "verdict": verdict,
        "p3_authorized": p3_authorized,
        "rows": count,
        "train_rows": args.train_count,
        "holdout_rows": count - args.train_count,
        "endpoint_reproduction": endpoint_reproduction,
        "endpoints": endpoint,
        "pairs": pair_reports,
        "fixed_interpolation_t": list(INTERPOLATION_T),
        "markers": {
            "NEW_FITS": 0,
            "REFITS": 0,
            "FRESH_OPENINGS": 0,
            "STRENGTH_GAMES": 0,
            "SCAN_WEIGHT_READS": 0,
            "SCAN_SCORE_READS": 0,
            "SCAN_TARGET_READS": 0,
            "PROMOTION_AUTHORIZED": False,
        },
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
