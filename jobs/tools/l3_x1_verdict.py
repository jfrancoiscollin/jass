#!/usr/bin/env python3
"""Build the contract-complete L3-PURE C2-X1 exploration screen verdict.

X1 is a resolution-III half-fraction of 2^3 (generator C=AB) plus a centre run:

    A = opening plies, B = initial epsilon, C = end of decay.

    CONTROL  +/+/+   (recette courante, baseline)
    X_LLH    -/-/+
    X_HLL    +/-/-
    X_LHL    -/+/-
    X_CENTER 0/0/0    (curvature diagnostic, not a lead candidate)

Unlike C1-Q1, every cell plays the *same* game search (only the trained
distribution differs), so common-search and native gates carry the identical
63-key fingerprint on both sides. The tool refuses inherited defaults, a
divergent fingerprint between cells, unpaired conversion traces, a missing view
or a missing cell. It never launches a subsequent experiment.

Pre-registered decision (plan L3_PURE_PLAN.md 6.1 / 7): a corner advances to
confirmation against CONTROL iff its global paired conversion gain is at least
+0.02, no established common-search regression (ci_high < 0.5 rejects) and no
established stratum regression (ci_high(delta) < 0 rejects), P3 explicitly
included. The centre is only tested for curvature against the mean of the four
corners.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any


CONTROL = "CONTROL"
CORNERS = ("X_LLH", "X_HLL", "X_LHL")           # non-control factorial corners
FACTORIAL = (CONTROL, "X_LLH", "X_HLL", "X_LHL")  # the four 2^(3-1) runs
CENTER = "X_CENTER"
CELLS = (CONTROL, "X_LLH", "X_HLL", "X_LHL", CENTER)
CHALLENGERS = ("X_LLH", "X_HLL", "X_LHL", CENTER)  # everything gated vs CONTROL
STRATA = ("p1_net", "p2_moyen", "p3_mince", "p4_egal")
PLAYED_OUTCOMES = {"win", "draw", "loss"}

# Coded factor levels per cell (A opening, B epsilon, C decay); +1/-1/0.
CODES = {
    CONTROL: (+1, +1, +1),
    "X_LLH": (-1, -1, +1),
    "X_HLL": (+1, -1, -1),
    "X_LHL": (-1, +1, -1),
    CENTER:  (0, 0, 0),
}

REQUIRED_SEARCH_KEYS = (
    "rfp_max_depth", "rfp_margin", "nmp_min_depth", "nmp_min_pieces",
    "nmp_r_base", "nmp_r_div", "singular_min_depth", "singular_margin",
    "lmr_min_depth", "lmr_first_full_moves", "lmr_first_full_pv",
    "lmr_first_full_nonpv", "lmr_base", "lmr_depth_div", "lmr_idx_div",
    "lmr_hist_div", "lmr_formula", "lmr_log_base", "lmr_log_mul",
    "lmr_bc_ld", "lmr_bc_lidx", "lmp_d1", "lmp_d2", "lmp_d3",
    "lmp_max_depth", "history_max", "hist_malus", "hist_mode", "prob_shift",
    "hist_pure", "hist_order_captures", "aspiration_initial", "use_pvs",
    "razor_max_depth", "razor_margin", "probcut_min_depth", "probcut_margin",
    "probcut_reduction", "ext_promotion", "ext_forcing", "forcing_ext_cap",
    "ext_single_reply", "use_improving", "use_conthist", "iid_min_depth",
    "iid_reduction", "no_reduce_forcing", "qs_forcing_depth",
    "qs_promo_depth", "qs_threat_ext", "qs_sacs", "qs_sacs_depth0_only",
    "multicut_min_depth", "multicut_reduction", "multicut_moves",
    "multicut_cuts", "tm_next_iter_pct", "tm_min_depth", "drawish_scaling",
    "eg_pieces", "eg_no_nmp", "eg_no_lmp", "eg_no_lmr",
)


def parse_search_params(spec: str, label: str) -> dict[str, int]:
    if not isinstance(spec, str) or not spec:
        raise ValueError(f"{label}: missing resolved search fingerprint")
    values: dict[str, int] = {}
    for token in spec.split(","):
        if token.count("=") != 1:
            raise ValueError(f"{label}: malformed search token {token!r}")
        key, raw = token.split("=", 1)
        if key in values:
            raise ValueError(f"{label}: duplicate search key {key}")
        try:
            values[key] = int(raw)
        except ValueError as exc:
            raise ValueError(f"{label}: non-integer value for {key}") from exc
    required = set(REQUIRED_SEARCH_KEYS)
    if set(values) != required:
        missing = sorted(required - set(values))
        extra = sorted(set(values) - required)
        raise ValueError(
            f"{label}: expected exactly 63 search keys; missing={missing}, extra={extra}"
        )
    return values


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label}: expected a JSON object")
    return payload


def _resolve(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}: missing path")
    path = Path(value)
    return path if path.is_absolute() else root / path


def _number(payload: dict, key: str, label: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{label}: invalid numeric {key}")
    return float(value)


def _validate_gate(
    payload: dict,
    label: str,
    expected_a: str,
    expected_b: str,
    *,
    require_movetime: bool,
) -> dict[str, Any]:
    if payload.get("complete") is not True:
        raise ValueError(f"{label}: incomplete gate")
    if payload.get("search_params_a") != expected_a:
        raise ValueError(f"{label}: side-A search fingerprint mismatch")
    if payload.get("search_params_b") != expected_b:
        raise ValueError(f"{label}: side-B search fingerprint mismatch")
    depth = payload.get("depth")
    movetime = payload.get("movetime")
    if require_movetime:
        if depth is not None or not isinstance(movetime, (int, float)) or movetime <= 0:
            raise ValueError(f"{label}: native view must use equal positive movetime")
    elif (depth is None) == (movetime is None):
        raise ValueError(f"{label}: common view must record exactly one search budget")
    n = payload.get("n")
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise ValueError(f"{label}: invalid game count")
    rate = _number(payload, "rate", label)
    ci_low = _number(payload, "ci_low", label)
    ci_high = _number(payload, "ci_high", label)
    if not (0 <= ci_low <= rate <= ci_high <= 1):
        raise ValueError(f"{label}: inconsistent rate/CI")
    return {
        "n": n,
        "rate": round(rate, 6),
        "ci_low": round(ci_low, 6),
        "ci_high": round(ci_high, 6),
        "elo": payload.get("elo"),
        "depth": depth,
        "movetime": movetime,
        "pairs": payload.get("pairs"),
        "openings_file": payload.get("openings_file"),
        "search_params_a": expected_a,
        "search_params_b": expected_b,
    }


def _percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("cannot take percentile of empty bootstrap")
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _row_metrics(row: dict[str, float]) -> dict[str, float]:
    control = row[CONTROL]
    llh, hll, lhl, center = row["X_LLH"], row["X_HLL"], row["X_LHL"], row[CENTER]
    # Aliased main effects over the four corners (C=AB, so A=BC, B=AC, C=AB).
    effect_a = ((hll + control) - (llh + lhl)) / 2       # opening plies (+ = 8)
    effect_b = ((lhl + control) - (llh + hll)) / 2       # epsilon (+ = 8 %)
    effect_c = ((llh + control) - (hll + lhl)) / 2       # decay (+ = 60)
    corners_mean = (control + llh + hll + lhl) / 4
    return {
        "delta_X_LLH": llh - control,
        "delta_X_HLL": hll - control,
        "delta_X_LHL": lhl - control,
        "delta_X_CENTER": center - control,
        "effect_A_opening": effect_a,
        "effect_B_epsilon": effect_b,
        "effect_C_decay": effect_c,
        "curvature_center_vs_corners": center - corners_mean,
    }


def paired_statistics(rows: list[dict[str, float]], replicates: int, seed: int) -> dict:
    if not rows:
        raise ValueError("no all-cell paired conversion positions")
    if replicates < 100:
        raise ValueError("bootstrap requires at least 100 replicates")
    keys = tuple(_row_metrics(rows[0]))
    point_sums = {key: 0.0 for key in keys}
    conversions = {cell: 0.0 for cell in CELLS}
    for row in rows:
        for cell in CELLS:
            conversions[cell] += row[cell]
        for key, value in _row_metrics(row).items():
            point_sums[key] += value
    n = len(rows)
    point = {key: point_sums[key] / n for key in keys}

    rng = random.Random(seed)
    samples = {key: [] for key in keys}
    for _ in range(replicates):
        sums = {key: 0.0 for key in keys}
        for _position in range(n):
            metrics = _row_metrics(rows[rng.randrange(n)])
            for key in keys:
                sums[key] += metrics[key]
        for key in keys:
            samples[key].append(sums[key] / n)

    metrics_report = {}
    for key in keys:
        ordered = sorted(samples[key])
        metrics_report[key] = {
            "estimate": round(point[key], 6),
            "ci_low": round(_percentile(ordered, 0.025), 6),
            "ci_high": round(_percentile(ordered, 0.975), 6),
        }
    return {
        "n_paired": n,
        "conversion": {cell: round(conversions[cell] / n, 6) for cell in CELLS},
        "metrics": metrics_report,
    }


def _load_conversion_rows(
    root: Path,
    cells_spec: dict,
    common_search: str,
) -> tuple[dict[str, list[dict[str, float]]], dict]:
    rows_by_stratum: dict[str, list[dict[str, float]]] = {}
    diagnostics: dict[str, Any] = {}
    for stratum in STRATA:
        payloads: dict[str, dict] = {}
        for cell in CELLS:
            conversion = cells_spec[cell].get("conversion")
            if not isinstance(conversion, dict) or set(conversion) != set(STRATA):
                raise ValueError(f"{cell}: conversion map must contain exactly P1-P4")
            path = _resolve(root, conversion[stratum], f"{cell}/{stratum}")
            payload = _read_json(path, f"{cell}/{stratum}")
            if payload.get("complete") is not True or payload.get("schema") != 2:
                raise ValueError(f"{cell}/{stratum}: schema-2 complete aggregate required")
            if payload.get("stratum") != stratum:
                raise ValueError(f"{cell}/{stratum}: stratum mismatch")
            if payload.get("search_params") != common_search:
                raise ValueError(f"{cell}/{stratum}: candidate is not under common search")
            if payload.get("defender_search_params") != common_search:
                raise ValueError(f"{cell}/{stratum}: defender is not under common search")
            if not isinstance(payload.get("pool_sha256"), str) or not payload["pool_sha256"]:
                raise ValueError(f"{cell}/{stratum}: missing pool SHA-256")
            if not isinstance(payload.get("position_results"), list):
                raise ValueError(f"{cell}/{stratum}: missing position trace")
            payloads[cell] = payload

        baseline = payloads[CONTROL]
        comparable_keys = (
            "pool_sha256", "expected_records", "depth", "movetime",
            "defender_jass", "defender_pattern", "defender_search_params",
        )
        for cell in CHALLENGERS:
            for key in comparable_keys:
                if payloads[cell].get(key) != baseline.get(key):
                    raise ValueError(f"{cell}/{stratum}: non-comparable conversion {key}")

        outcomes: dict[str, dict[int, str]] = {}
        for cell in CELLS:
            mapped: dict[int, str] = {}
            for item in payloads[cell]["position_results"]:
                if not isinstance(item, dict):
                    raise ValueError(f"{cell}/{stratum}: malformed position trace")
                index, outcome = item.get("index"), item.get("result")
                if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                    raise ValueError(f"{cell}/{stratum}: invalid position index")
                if outcome not in PLAYED_OUTCOMES | {"error", "skipped_draw_label"}:
                    raise ValueError(f"{cell}/{stratum}: invalid position outcome")
                if index in mapped:
                    raise ValueError(f"{cell}/{stratum}: duplicate position index {index}")
                mapped[index] = outcome
            outcomes[cell] = mapped
        source_indices = set(outcomes[CONTROL])
        for cell in CHALLENGERS:
            if set(outcomes[cell]) != source_indices:
                raise ValueError(f"{cell}/{stratum}: source-index set differs from CONTROL")

        rows: list[dict[str, float]] = []
        excluded = 0
        for index in sorted(source_indices):
            if not all(outcomes[cell][index] in PLAYED_OUTCOMES for cell in CELLS):
                excluded += 1
                continue
            rows.append(
                {cell: 1.0 if outcomes[cell][index] == "win" else 0.0 for cell in CELLS}
            )
        if not rows:
            raise ValueError(f"{stratum}: no position played successfully by all cells")
        rows_by_stratum[stratum] = rows
        diagnostics[stratum] = {
            "source_positions": len(source_indices),
            "paired_positions": len(rows),
            "excluded_error_or_draw_label": excluded,
            "pool_sha256": baseline["pool_sha256"],
            "raw_conversion": {cell: payloads[cell].get("conversion") for cell in CELLS},
        }
    return rows_by_stratum, diagnostics


def build_report(spec: dict[str, Any], spec_path: Path) -> dict[str, Any]:
    if spec.get("schema") != 2:
        raise ValueError("verdict spec schema must be 2")
    if spec.get("baseline") != CONTROL:
        raise ValueError("X1 baseline must be CONTROL")
    cells_spec = spec.get("cells")
    if not isinstance(cells_spec, dict) or set(cells_spec) != set(CELLS):
        raise ValueError("verdict spec must contain exactly the five X1 cells")
    root = spec_path.resolve().parent

    common_search = spec.get("common_search_params")
    parse_search_params(common_search, "common search")
    # Every cell shares one game search in X1: fingerprints must be identical.
    for cell in CELLS:
        if not isinstance(cells_spec[cell], dict):
            raise ValueError(f"{cell}: cell spec must be an object")
        fingerprint = cells_spec[cell].get("search_params")
        parse_search_params(fingerprint, f"{cell} search")
        if fingerprint != common_search:
            raise ValueError(f"{cell}: X1 requires the shared common-search fingerprint")

    rows_by_stratum, conversion_diagnostics = _load_conversion_rows(
        root, cells_spec, common_search
    )
    bootstrap = spec.get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        raise ValueError("bootstrap must be an object")
    replicates = int(bootstrap.get("replicates", 10000))
    seed = int(bootstrap.get("seed", 271828))
    statistics: dict[str, dict] = {}
    for offset, stratum in enumerate(STRATA):
        statistics[stratum] = paired_statistics(
            rows_by_stratum[stratum], replicates, seed + offset
        )
    global_rows = [row for stratum in STRATA for row in rows_by_stratum[stratum]]
    statistics["global"] = paired_statistics(global_rows, replicates, seed + 100)

    common_gates: dict[str, dict] = {}
    native_gates: dict[str, dict] = {}
    common_signature = native_signature = None
    for cell in CHALLENGERS:
        common_payload = _read_json(
            _resolve(root, cells_spec[cell].get("common_gate"), f"{cell} common gate"),
            f"{cell} common gate",
        )
        common_gates[cell] = _validate_gate(
            common_payload, f"{cell} common gate",
            common_search, common_search, require_movetime=False,
        )
        signature = tuple(
            common_gates[cell][key]
            for key in ("n", "depth", "movetime", "pairs", "openings_file")
        )
        common_signature = signature if common_signature is None else common_signature
        if signature != common_signature:
            raise ValueError(f"{cell}: common gate budget/openings differ")

        native_payload = _read_json(
            _resolve(root, cells_spec[cell].get("native_gate"), f"{cell} native gate"),
            f"{cell} native gate",
        )
        native_gates[cell] = _validate_gate(
            native_payload, f"{cell} native gate",
            common_search, common_search, require_movetime=True,
        )
        signature = tuple(
            native_gates[cell][key]
            for key in ("n", "movetime", "pairs", "openings_file")
        )
        native_signature = signature if native_signature is None else native_signature
        if signature != native_signature:
            raise ValueError(f"{cell}: native gate budget/openings differ")

    threshold = float(spec.get("conversion_delta_threshold", 0.02))
    if threshold != 0.02:
        raise ValueError("C2-X1 conversion screen threshold is pre-registered at 0.02")

    screen: dict[str, dict] = {}
    for cell in CHALLENGERS:
        metric_key = f"delta_{cell}"
        global_delta = statistics["global"]["metrics"][metric_key]
        strata_delta = {
            stratum: statistics[stratum]["metrics"][metric_key] for stratum in STRATA
        }
        common_non_regression = common_gates[cell]["ci_high"] >= 0.5
        native_non_regression = native_gates[cell]["ci_high"] >= 0.5
        strata_non_regression = all(row["ci_high"] >= 0 for row in strata_delta.values())
        p3_non_regression = strata_delta["p3_mince"]["ci_high"] >= 0
        conversion_gain = global_delta["estimate"] >= threshold
        # The centre is a curvature probe, never a lead candidate (plan 6.1).
        is_lead_candidate = cell in CORNERS
        advance = (
            is_lead_candidate
            and common_non_regression
            and strata_non_regression
            and p3_non_regression
            and conversion_gain
        )
        if common_gates[cell]["ci_low"] > 0.5:
            gain_classification = "learning_gain"
        elif native_gates[cell]["ci_low"] > 0.5:
            gain_classification = "search_gain"
        else:
            gain_classification = "no_established_strength_gain"
        screen[cell] = {
            "coded_levels_ABC": list(CODES[cell]),
            "lead_candidate": is_lead_candidate,
            "paired_conversion": {"global": global_delta, "strata": strata_delta},
            "common_search_non_regression": common_non_regression,
            "native_search_non_regression": native_non_regression,
            "p3_non_regression": p3_non_regression,
            "all_strata_non_regression": strata_non_regression,
            "conversion_gain_at_least_0_02": conversion_gain,
            "advance_to_confirmation": advance,
            "gain_classification": gain_classification,
        }

    eligible = [cell for cell in CORNERS if screen[cell]["advance_to_confirmation"]]
    eligible.sort(
        key=lambda cell: (-screen[cell]["paired_conversion"]["global"]["estimate"], cell)
    )
    lead = eligible[0] if eligible else None
    verdict = f"x1_lead_{lead.lower()}" if lead else "x1_no_lead"
    curvature = statistics["global"]["metrics"]["curvature_center_vs_corners"]
    return {
        "schema": 2,
        "experiment": "L3-PURE-C2-X1",
        "technical_status": "complete",
        "scientific_verdict": verdict,
        "baseline": CONTROL,
        "selected_lead": lead,
        "eligible_leads": eligible,
        "automatic_next_job": None,
        "decision_scope": "screen_to_confirmation_only",
        "search_contract": {
            "parameter_count": len(REQUIRED_SEARCH_KEYS),
            "common_search_params": common_search,
            "shared_fingerprint_all_cells": True,
            "inherited_defaults": False,
        },
        "bootstrap": {"method": "paired_position", "replicates": replicates, "seed": seed},
        "conversion_diagnostics": conversion_diagnostics,
        "paired_statistics": statistics,
        "factorial_effects_global": {
            key: statistics["global"]["metrics"][key]
            for key in ("effect_A_opening", "effect_B_epsilon", "effect_C_decay")
        },
        "curvature_global": curvature,
        "common_search_gates_vs_control": common_gates,
        "native_equal_time_gates_vs_control": native_gates,
        "screen": screen,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    spec_path = Path(args.spec)
    out_path = Path(args.out)
    try:
        spec = _read_json(spec_path, "verdict spec")
        report = build_report(spec, spec_path)
    except (OSError, ValueError, TypeError) as exc:
        report = {
            "schema": 2,
            "experiment": "L3-PURE-C2-X1",
            "technical_status": "invalid_science",
            "scientific_verdict": None,
            "automatic_next_job": None,
            "error": str(exc),
        }
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
