#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Calibrate adaptive L3-IMBALANCE2 penalties from an independent oracle profile.

This tool is diagnostic only. It consumes the immutable material-stratified
EGDB/Scan reference and proposes per-stratum role-aware weights. It never edits
training data and never authorizes a fit.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

CATS = ("win", "draw", "loss")
EXPECTED = tuple(f"{n}v{n+2}" for n in range(1, 19))


def _counts(item: dict[str, Any]) -> dict[str, int]:
    n = int(item["n"])
    rates = item["rates"]
    raw = {cat: int(round(float(rates[cat]) * n)) for cat in CATS}
    delta = n - sum(raw.values())
    if delta:
        raw[max(CATS, key=lambda cat: float(rates[cat]))] += delta
    if any(value < 0 for value in raw.values()) or sum(raw.values()) != n:
        raise ValueError("invalid reconstructed oracle counts")
    return raw


def _rates(counts: dict[str, float]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        raise ValueError("empty counts")
    return {cat: float(counts[cat] / total) for cat in CATS}


def _alpha(rates: dict[str, float]) -> float:
    # Oracle value of the initial +2 side. Drawish/losing strata receive little
    # or no extra penalty; clearly won strata approach the historical 1/2/4.
    return max(0.0, min(1.0, rates["win"] - rates["loss"]))


def _weights(alpha: float) -> dict[str, float]:
    return {
        "expected_result": 1.0,
        "draw": round(1.0 + alpha, 6),
        "upset_result": round(1.0 + 3.0 * alpha, 6),
    }


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2.0
        for j in range(start, end):
            ranks[order[j]] = rank
        start = end
    return ranks


def _corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    den = math.sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    return 0.0 if den == 0 else sum(x * y for x, y in zip(dx, dy, strict=True)) / den


def _pava(values: list[float], weights: list[float]) -> list[float]:
    blocks: list[dict[str, float | int]] = []
    for index, (value, weight) in enumerate(zip(values, weights, strict=True)):
        blocks.append({"start": index, "end": index, "sum": value * weight, "weight": weight})
        while len(blocks) >= 2:
            a, b = blocks[-2], blocks[-1]
            ma = float(a["sum"]) / float(a["weight"])
            mb = float(b["sum"]) / float(b["weight"])
            if ma <= mb:
                break
            blocks[-2:] = [{
                "start": int(a["start"]), "end": int(b["end"]),
                "sum": float(a["sum"]) + float(b["sum"]),
                "weight": float(a["weight"]) + float(b["weight"]),
            }]
    out = [0.0] * len(values)
    for block in blocks:
        mean = float(block["sum"]) / float(block["weight"])
        for index in range(int(block["start"]), int(block["end"]) + 1):
            out[index] = mean
    return out


def calibrate(reference: dict[str, Any], prior_strength: float) -> dict[str, Any]:
    strata = reference.get("strata", {})
    if tuple(sorted(strata, key=lambda s: int(s.split("v", 1)[0]))) != EXPECTED:
        raise ValueError("reference must contain exactly 1v3..18v20")
    if reference.get("perspective") not in (None, "initial_material_up_side"):
        raise ValueError("unexpected oracle perspective")

    source_totals: dict[str, dict[str, float]] = {}
    for item in strata.values():
        source = str(item["source"])
        bucket = source_totals.setdefault(source, {cat: 0.0 for cat in CATS})
        counts = _counts(item)
        for cat in CATS:
            bucket[cat] += counts[cat]
    source_priors = {source: _rates(counts) for source, counts in source_totals.items()}

    rows: list[dict[str, Any]] = []
    for stratum in EXPECTED:
        item = strata[stratum]
        source = str(item["source"])
        counts = _counts(item)
        raw_rates = _rates({cat: float(counts[cat]) for cat in CATS})
        prior = source_priors[source]
        shrunk_counts = {
            cat: counts[cat] + prior_strength * prior[cat] for cat in CATS
        }
        shrunk_rates = _rates(shrunk_counts)
        pool_alphas: dict[str, float] = {}
        for pool, pool_item in sorted(item.get("pools", {}).items()):
            pool_alphas[pool] = round(_alpha(_rates({cat: float(v) for cat, v in _counts(pool_item).items()})), 6)
        rows.append({
            "stratum": stratum,
            "total_pieces": int(item["total_pieces"]),
            "source": source,
            "n": int(item["n"]),
            "oracle_rates": {cat: round(raw_rates[cat], 6) for cat in CATS},
            "alpha_raw": round(_alpha(raw_rates), 6),
            "alpha_shrunk": round(_alpha(shrunk_rates), 6),
            "pool_alpha": pool_alphas,
            "pool_alpha_gap": round(max(pool_alphas.values()) - min(pool_alphas.values()), 6) if len(pool_alphas) >= 2 else None,
        })

    dense = [row["alpha_shrunk"] for row in rows if int(row["stratum"].split("v", 1)[0]) >= 14]
    dense_anchor = sum(dense) / len(dense)
    monotone = _pava([float(row["alpha_shrunk"]) for row in rows], [float(row["n"]) for row in rows])
    for row, mono in zip(rows, monotone, strict=True):
        absolute = float(row["alpha_shrunk"])
        relative = min(1.0, absolute / dense_anchor) if dense_anchor > 0 else 0.0
        row["alpha_monotone_density"] = round(mono, 6)
        row["alpha_dense_normalized"] = round(relative, 6)
        row["proposed_weights_absolute"] = _weights(absolute)
        row["proposed_weights_dense_normalized"] = _weights(relative)

    pieces = [float(row["total_pieces"]) for row in rows]
    alphas = [float(row["alpha_shrunk"]) for row in rows]
    spearman = _corr(_rank(pieces), _rank(alphas))
    low_mean = sum(alphas[:7]) / 7.0
    dense_mean = sum(alphas[-5:]) / 5.0
    gaps = [float(row["pool_alpha_gap"]) for row in rows if row["pool_alpha_gap"] is not None]
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 1.0
    max_gap = max(gaps) if gaps else 1.0
    stable = median_gap <= 0.20 and max_gap <= 0.45
    density_supported = spearman >= 0.35 and dense_mean - low_mean >= 0.08

    if not stable:
        classification = "ORACLE_CURVE_TOO_NOISY_NEEDS_LARGER_CALIBRATION_POOL"
        recommendation = "BUILD_FRESH_C512_ORACLE_CALIBRATION_BEFORE_WEIGHTED_FIT"
    elif density_supported:
        classification = "DENSITY_ADAPTIVE_WEIGHTING_SUPPORTED"
        recommendation = "DESIGN_SEPARATE_W1_WEIGHT_ONLY_PILOT_ON_FRESH_E64_F64"
    else:
        classification = "STRATUM_ORACLE_WEIGHTING_SUPPORTED_DENSITY_ONLY_NOT_SUPPORTED"
        recommendation = "USE_CROSSFIT_STRATUM_OR_POSITION_ORACLE_NOT_A_MANUAL_PIECE_THRESHOLD"

    return {
        "schema": 1,
        "protocol": "l3-imbalance2-w0-oracle-adaptive-weight-calibration",
        "decision": "W0_ORACLE_WEIGHT_CALIBRATION_READY",
        "classification": classification,
        "formula": {
            "alpha": "clip(P_oracle(win)-P_oracle(loss),0,1)",
            "expected_result_weight": "1",
            "draw_weight": "1+alpha",
            "upset_weight": "1+3*alpha",
            "historical_fixed_matrix_recovered_when_alpha": 1,
        },
        "oracle_contract": {
            "exact_sources": ["exact_egdb_wdl"],
            "empirical_sources": sorted(source for source in source_priors if source != "exact_egdb_wdl"),
            "scan_is_exact": False,
            "teacher_calibrated_specialist_only": True,
            "forbidden_for_l3_pure": True,
            "prior_strength": prior_strength,
        },
        "diagnostics": {
            "spearman_material_vs_alpha": round(spearman, 6),
            "low_1v3_to_7v9_mean_alpha": round(low_mean, 6),
            "dense_14v16_to_18v20_mean_alpha": round(dense_mean, 6),
            "dense_anchor_alpha": round(dense_anchor, 6),
            "median_pool_alpha_gap": round(median_gap, 6),
            "max_pool_alpha_gap": round(max_gap, 6),
            "pool_stability_pass": stable,
            "density_only_hypothesis_pass": density_supported,
        },
        "strata": rows,
        "recommendation_for_human_review": recommendation,
        "s1_search_pilot_independent": True,
        "training_authorized": False,
        "weight_policy_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--prior-strength", type=float, default=32.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.prior_strength < 0:
        parser.error("prior strength must be non-negative")
    try:
        result = calibrate(json.loads(Path(args.reference).read_text(encoding="utf-8")), args.prior_strength)
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["decision"])
    print(f"classification={result['classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
