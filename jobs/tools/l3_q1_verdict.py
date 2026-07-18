#!/usr/bin/env python3
"""Build the contract-complete L3-PURE C1-Q1 scientific verdict.

The input is one JSON specification that names the four conversion aggregates,
the three common-search gates and the three native equal-time gates. The tool
refuses inherited search defaults, unpaired conversion traces, missing views or
post-hoc cost claims. It never launches a subsequent experiment.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any


CELLS = ("Q00", "Q10", "Q01", "Q11")
CHALLENGERS = ("Q10", "Q01", "Q11")
STRATA = ("p1_net", "p2_moyen", "p3_mince", "p4_egal")
PLAYED_OUTCOMES = {"win", "draw", "loss"}
EXPECTED_Q1 = {
    "Q00": (0, 0),
    "Q10": (1, 0),
    "Q01": (0, 1),
    "Q11": (1, 1),
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
    q00, q10, q01, q11 = (row[cell] for cell in CELLS)
    return {
        "delta_Q10": q10 - q00,
        "delta_Q01": q01 - q00,
        "delta_Q11": q11 - q00,
        "threat": ((q10 - q00) + (q11 - q01)) / 2,
        "sacs": ((q01 - q00) + (q11 - q10)) / 2,
        # Half-contrast preserves the scale used by the original 0806 report.
        "interaction": (q11 + q00 - q10 - q01) / 2,
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
        "conversion": {
            cell: round(conversions[cell] / n, 6) for cell in CELLS
        },
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

        baseline = payloads["Q00"]
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
        source_indices = set(outcomes["Q00"])
        for cell in CHALLENGERS:
            if set(outcomes[cell]) != source_indices:
                raise ValueError(f"{cell}/{stratum}: source-index set differs from Q00")

        rows: list[dict[str, float]] = []
        excluded = 0
        for index in sorted(source_indices):
            if not all(outcomes[cell][index] in PLAYED_OUTCOMES for cell in CELLS):
                excluded += 1
                continue
            rows.append(
                {
                    cell: 1.0 if outcomes[cell][index] == "win" else 0.0
                    for cell in CELLS
                }
            )
        if not rows:
            raise ValueError(f"{stratum}: no position played successfully by all cells")
        rows_by_stratum[stratum] = rows
        diagnostics[stratum] = {
            "source_positions": len(source_indices),
            "paired_positions": len(rows),
            "excluded_error_or_draw_label": excluded,
            "pool_sha256": baseline["pool_sha256"],
            "raw_conversion": {
                cell: payloads[cell].get("conversion") for cell in CELLS
            },
        }
    return rows_by_stratum, diagnostics


def _cost_branch(
    root: Path,
    cell_spec: dict,
    conversion_non_regression: bool,
    force_non_regression: bool,
) -> dict[str, Any]:
    evidence_path = cell_spec.get("cost_evidence")
    if evidence_path is None:
        return {
            "available": False,
            "passes": False,
            "reason": "no_pre_registered_comparable_cost_evidence",
        }
    payload = _read_json(_resolve(root, evidence_path, "cost evidence"), "cost evidence")
    guards = ("complete", "comparable", "same_positions", "same_budget")
    if not all(payload.get(key) is True for key in guards):
        return {
            "available": False,
            "passes": False,
            "reason": "cost_evidence_not_comparable",
        }
    candidate = _number(payload, "candidate", "cost evidence")
    baseline = _number(payload, "baseline", "cost evidence")
    if baseline <= 0 or candidate < 0:
        raise ValueError("cost evidence: costs must be non-negative with baseline > 0")
    reduction = (baseline - candidate) / baseline
    passes = reduction >= 0.20 and conversion_non_regression and force_non_regression
    return {
        "available": True,
        "passes": passes,
        "metric": payload.get("metric"),
        "candidate": candidate,
        "baseline": baseline,
        "relative_reduction": round(reduction, 6),
        "conversion_non_regression": conversion_non_regression,
        "force_non_regression": force_non_regression,
    }


def build_report(spec: dict[str, Any], spec_path: Path) -> dict[str, Any]:
    if spec.get("schema") != 2:
        raise ValueError("verdict spec schema must be 2")
    if spec.get("baseline") != "Q00":
        raise ValueError("Q1 baseline must be Q00")
    cells_spec = spec.get("cells")
    if not isinstance(cells_spec, dict) or set(cells_spec) != set(CELLS):
        raise ValueError("verdict spec must contain exactly Q00/Q10/Q01/Q11")
    root = spec_path.resolve().parent

    common_search = spec.get("common_search_params")
    common_values = parse_search_params(common_search, "common search")
    cell_search: dict[str, str] = {}
    for cell in CELLS:
        if not isinstance(cells_spec[cell], dict):
            raise ValueError(f"{cell}: cell spec must be an object")
        fingerprint = cells_spec[cell].get("search_params")
        values = parse_search_params(fingerprint, f"{cell} native search")
        expected_threat, expected_sacs = EXPECTED_Q1[cell]
        expected = {
            "qs_threat_ext": expected_threat,
            "qs_sacs": expected_sacs,
            "qs_sacs_depth0_only": 1,
            "qs_forcing_depth": 0,
            "qs_promo_depth": 0,
        }
        for key, value in expected.items():
            if values[key] != value:
                raise ValueError(f"{cell}: {key}={values[key]}, expected {value}")
        cell_search[cell] = fingerprint
    if common_search != cell_search["Q00"]:
        raise ValueError("common-search fingerprint must be the full Q00 fingerprint")
    for key in ("qs_forcing_depth", "qs_promo_depth", "qs_threat_ext", "qs_sacs"):
        if common_values[key] != 0:
            raise ValueError(f"common search must keep Q1 {key}=0")

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
            common_payload,
            f"{cell} common gate",
            common_search,
            common_search,
            require_movetime=False,
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
            native_payload,
            f"{cell} native gate",
            cell_search[cell],
            cell_search["Q00"],
            require_movetime=True,
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
        raise ValueError("C1-Q1 conversion screen threshold is pre-registered at 0.02")

    screen: dict[str, dict] = {}
    for cell in CHALLENGERS:
        metric_key = f"delta_{cell}"
        global_delta = statistics["global"]["metrics"][metric_key]
        strata_delta = {
            stratum: statistics[stratum]["metrics"][metric_key]
            for stratum in STRATA
        }
        common_non_regression = common_gates[cell]["ci_high"] >= 0.5
        native_non_regression = native_gates[cell]["ci_high"] >= 0.5
        strata_non_regression = all(
            row["ci_high"] >= 0 for row in strata_delta.values()
        )
        p3_non_regression = strata_delta["p3_mince"]["ci_high"] >= 0
        conversion_gain = global_delta["estimate"] >= threshold
        conversion_non_regression = global_delta["ci_high"] >= 0 and strata_non_regression
        force_non_regression = common_non_regression and native_non_regression
        cost = _cost_branch(
            root,
            cells_spec[cell],
            conversion_non_regression,
            force_non_regression,
        )
        advance = (
            common_non_regression
            and strata_non_regression
            and p3_non_regression
            and (conversion_gain or cost["passes"])
        )
        if common_gates[cell]["ci_low"] > 0.5:
            gain_classification = "learning_gain"
        elif native_gates[cell]["ci_low"] > 0.5:
            gain_classification = "search_gain"
        else:
            gain_classification = "no_established_strength_gain"
        screen[cell] = {
            "paired_conversion": {
                "global": global_delta,
                "strata": strata_delta,
            },
            "common_search_non_regression": common_non_regression,
            "native_search_non_regression": native_non_regression,
            "p3_non_regression": p3_non_regression,
            "all_strata_non_regression": strata_non_regression,
            "conversion_gain_at_least_0_02": conversion_gain,
            "cost_branch": cost,
            "advance_to_confirmation": advance,
            "gain_classification": gain_classification,
        }

    eligible = [cell for cell in CHALLENGERS if screen[cell]["advance_to_confirmation"]]
    eligible.sort(
        key=lambda cell: (
            -screen[cell]["paired_conversion"]["global"]["estimate"], cell
        )
    )
    lead = eligible[0] if eligible else None
    verdict = f"q1_lead_{lead.lower()}" if lead else "q1_no_lead"
    return {
        "schema": 2,
        "experiment": "L3-PURE-C1-Q1",
        "technical_status": "complete",
        "scientific_verdict": verdict,
        "baseline": "Q00",
        "selected_lead": lead,
        "eligible_leads": eligible,
        "automatic_next_job": None,
        "decision_scope": "screen_to_confirmation_only",
        "search_contract": {
            "parameter_count": len(REQUIRED_SEARCH_KEYS),
            "common_search_params": common_search,
            "native_search_params": cell_search,
            "inherited_defaults": False,
        },
        "bootstrap": {"method": "paired_position", "replicates": replicates, "seed": seed},
        "conversion_diagnostics": conversion_diagnostics,
        "paired_statistics": statistics,
        "factorial_effects_global": {
            key: statistics["global"]["metrics"][key]
            for key in ("threat", "sacs", "interaction")
        },
        "common_search_gates_vs_Q00": common_gates,
        "native_equal_time_gates_vs_Q00": native_gates,
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
            "experiment": "L3-PURE-C1-Q1",
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
