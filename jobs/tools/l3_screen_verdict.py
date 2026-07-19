#!/usr/bin/env python3
"""Generic control-vs-challengers L3 screen verdict (single-factor sweeps).

Unlike l3_x1_verdict (a fixed 2^(3-1) factorial), this tool takes an arbitrary
baseline plus N challenger cells and evaluates each challenger against the
baseline with the pre-registered screen contract:

  * paired-position conversion, global + P1-P4, bootstrap CI vs baseline;
  * common-search and native equal-time non-regression gates (shared 63-key
    fingerprint on both sides — every cell plays the same game search);
  * a challenger advances iff global paired Δconversion >= threshold, no
    established common-search regression (ci_high < 0.5 rejects) and no
    established stratum regression (ci_high(delta) < 0 rejects, P3 included).

Used by C3-MF (L2 / king-ratio / replay triage) and any later single-factor
screen. Launches no job.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

STRATA = ("p1_net", "p2_moyen", "p3_mince", "p4_egal")
PLAYED_OUTCOMES = {"win", "draw", "loss"}

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
    if set(values) != set(REQUIRED_SEARCH_KEYS):
        missing = sorted(set(REQUIRED_SEARCH_KEYS) - set(values))
        extra = sorted(set(values) - set(REQUIRED_SEARCH_KEYS))
        raise ValueError(f"{label}: expected exactly 63 search keys; missing={missing}, extra={extra}")
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


def _validate_gate(payload: dict, label: str, fp: str, *, require_movetime: bool) -> dict[str, Any]:
    if payload.get("complete") is not True:
        raise ValueError(f"{label}: incomplete gate")
    if payload.get("search_params_a") != fp or payload.get("search_params_b") != fp:
        raise ValueError(f"{label}: gate fingerprint mismatch (shared search required)")
    depth, movetime = payload.get("depth"), payload.get("movetime")
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
    return {"n": n, "rate": round(rate, 6), "ci_low": round(ci_low, 6),
            "ci_high": round(ci_high, 6), "depth": depth, "movetime": movetime,
            "pairs": payload.get("pairs"), "openings_file": payload.get("openings_file")}


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        raise ValueError("empty bootstrap")
    pos = (len(sorted_values) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] * (hi - pos) + sorted_values[hi] * (pos - lo)


def paired_statistics(rows, cells, baseline, replicates, seed) -> dict:
    """rows: list of {cell: 0/1}. Returns per-cell conversion + delta-vs-baseline CIs."""
    if not rows:
        raise ValueError("no all-cell paired conversion positions")
    if replicates < 100:
        raise ValueError("bootstrap requires at least 100 replicates")
    challengers = [c for c in cells if c != baseline]
    n = len(rows)
    conv = {c: sum(r[c] for r in rows) / n for c in cells}
    point = {c: (sum(r[c] - r[baseline] for r in rows) / n) for c in challengers}
    rng = random.Random(seed)
    samples = {c: [] for c in challengers}
    for _ in range(replicates):
        acc = {c: 0.0 for c in challengers}
        for _i in range(n):
            r = rows[rng.randrange(n)]
            for c in challengers:
                acc[c] += r[c] - r[baseline]
        for c in challengers:
            samples[c].append(acc[c] / n)
    metrics = {}
    for c in challengers:
        ordered = sorted(samples[c])
        metrics[c] = {"estimate": round(point[c], 6),
                      "ci_low": round(_percentile(ordered, 0.025), 6),
                      "ci_high": round(_percentile(ordered, 0.975), 6)}
    return {"n_paired": n, "conversion": {c: round(conv[c], 6) for c in cells}, "delta": metrics}


def _load_conversion_rows(root, cells, baseline, cells_spec, common_search):
    rows_by_stratum, diagnostics = {}, {}
    for stratum in STRATA:
        payloads = {}
        for cell in cells:
            conversion = cells_spec[cell].get("conversion")
            if not isinstance(conversion, dict) or set(conversion) != set(STRATA):
                raise ValueError(f"{cell}: conversion map must contain exactly P1-P4")
            payload = _read_json(_resolve(root, conversion[stratum], f"{cell}/{stratum}"), f"{cell}/{stratum}")
            if payload.get("complete") is not True or payload.get("schema") != 2:
                raise ValueError(f"{cell}/{stratum}: schema-2 complete aggregate required")
            if payload.get("stratum") != stratum:
                raise ValueError(f"{cell}/{stratum}: stratum mismatch")
            if payload.get("search_params") != common_search or payload.get("defender_search_params") != common_search:
                raise ValueError(f"{cell}/{stratum}: not under the common search")
            if not isinstance(payload.get("pool_sha256"), str) or not payload["pool_sha256"]:
                raise ValueError(f"{cell}/{stratum}: missing pool SHA-256")
            if not isinstance(payload.get("position_results"), list):
                raise ValueError(f"{cell}/{stratum}: missing position trace")
            payloads[cell] = payload
        base = payloads[baseline]
        for cell in cells:
            if cell == baseline:
                continue
            for key in ("pool_sha256", "expected_records", "depth", "movetime",
                        "defender_jass", "defender_pattern", "defender_search_params"):
                if payloads[cell].get(key) != base.get(key):
                    raise ValueError(f"{cell}/{stratum}: non-comparable conversion {key}")
        outcomes = {}
        for cell in cells:
            mapped = {}
            for item in payloads[cell]["position_results"]:
                if not isinstance(item, dict):
                    raise ValueError(f"{cell}/{stratum}: malformed position trace")
                idx, out = item.get("index"), item.get("result")
                if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
                    raise ValueError(f"{cell}/{stratum}: invalid position index")
                if out not in PLAYED_OUTCOMES | {"error", "skipped_draw_label"}:
                    raise ValueError(f"{cell}/{stratum}: invalid position outcome")
                if idx in mapped:
                    raise ValueError(f"{cell}/{stratum}: duplicate index {idx}")
                mapped[idx] = out
            outcomes[cell] = mapped
        source = set(outcomes[baseline])
        for cell in cells:
            if set(outcomes[cell]) != source:
                raise ValueError(f"{cell}/{stratum}: source-index set differs from baseline")
        rows, excluded = [], 0
        for idx in sorted(source):
            if not all(outcomes[cell][idx] in PLAYED_OUTCOMES for cell in cells):
                excluded += 1
                continue
            rows.append({cell: 1.0 if outcomes[cell][idx] == "win" else 0.0 for cell in cells})
        if not rows:
            raise ValueError(f"{stratum}: no position played successfully by all cells")
        rows_by_stratum[stratum] = rows
        diagnostics[stratum] = {"source_positions": len(source), "paired_positions": len(rows),
                                "excluded_error_or_draw_label": excluded, "pool_sha256": base["pool_sha256"],
                                "raw_conversion": {c: payloads[c].get("conversion") for c in cells}}
    return rows_by_stratum, diagnostics


def build_report(spec, spec_path):
    if spec.get("schema") != 2:
        raise ValueError("verdict spec schema must be 2")
    experiment = spec.get("experiment")
    if not isinstance(experiment, str) or not experiment:
        raise ValueError("verdict spec must name the experiment")
    baseline = spec.get("baseline")
    cells_spec = spec.get("cells")
    if not isinstance(cells_spec, dict) or baseline not in cells_spec or len(cells_spec) < 2:
        raise ValueError("spec must contain a baseline plus >=1 challenger cell")
    cells = sorted(cells_spec)          # deterministic order
    challengers = [c for c in cells if c != baseline]
    root = spec_path.resolve().parent

    common_search = spec.get("common_search_params")
    parse_search_params(common_search, "common search")
    for cell in cells:
        if not isinstance(cells_spec[cell], dict):
            raise ValueError(f"{cell}: cell spec must be an object")
        fp = cells_spec[cell].get("search_params")
        parse_search_params(fp, f"{cell} search")
        if fp != common_search:
            raise ValueError(f"{cell}: screen requires the shared common-search fingerprint")

    rows_by_stratum, conversion_diagnostics = _load_conversion_rows(root, cells, baseline, cells_spec, common_search)
    bootstrap = spec.get("bootstrap", {})
    replicates = int(bootstrap.get("replicates", 10000))
    seed = int(bootstrap.get("seed", 271828))
    statistics = {}
    for offset, stratum in enumerate(STRATA):
        statistics[stratum] = paired_statistics(rows_by_stratum[stratum], cells, baseline, replicates, seed + offset)
    global_rows = [r for stratum in STRATA for r in rows_by_stratum[stratum]]
    statistics["global"] = paired_statistics(global_rows, cells, baseline, replicates, seed + 100)

    common_gates, native_gates = {}, {}
    common_sig = native_sig = None
    for cell in challengers:
        cg = _validate_gate(_read_json(_resolve(root, cells_spec[cell].get("common_gate"), f"{cell} common gate"),
                                       f"{cell} common gate"), f"{cell} common gate", common_search, require_movetime=False)
        common_gates[cell] = cg
        sig = tuple(cg[k] for k in ("n", "depth", "movetime", "pairs", "openings_file"))
        common_sig = sig if common_sig is None else common_sig
        if sig != common_sig:
            raise ValueError(f"{cell}: common gate budget/openings differ")
        ng = _validate_gate(_read_json(_resolve(root, cells_spec[cell].get("native_gate"), f"{cell} native gate"),
                                       f"{cell} native gate"), f"{cell} native gate", common_search, require_movetime=True)
        native_gates[cell] = ng
        sig = tuple(ng[k] for k in ("n", "movetime", "pairs", "openings_file"))
        native_sig = sig if native_sig is None else native_sig
        if sig != native_sig:
            raise ValueError(f"{cell}: native gate budget/openings differ")

    threshold = float(spec.get("conversion_delta_threshold", 0.02))
    if threshold != 0.02:
        raise ValueError("screen threshold is pre-registered at 0.02")

    screen = {}
    for cell in challengers:
        gd = statistics["global"]["delta"][cell]
        strata_delta = {s: statistics[s]["delta"][cell] for s in STRATA}
        common_nr = common_gates[cell]["ci_high"] >= 0.5
        native_nr = native_gates[cell]["ci_high"] >= 0.5
        strata_nr = all(d["ci_high"] >= 0 for d in strata_delta.values())
        p3_nr = strata_delta["p3_mince"]["ci_high"] >= 0
        gain = gd["estimate"] >= threshold
        advance = common_nr and strata_nr and p3_nr and gain
        if common_gates[cell]["ci_low"] > 0.5:
            klass = "learning_gain"
        elif native_gates[cell]["ci_low"] > 0.5:
            klass = "search_gain"
        else:
            klass = "no_established_strength_gain"
        screen[cell] = {
            "cell_meta": cells_spec[cell].get("meta", {}),
            "paired_conversion": {"global": gd, "strata": strata_delta},
            "common_search_non_regression": common_nr,
            "native_search_non_regression": native_nr,
            "p3_non_regression": p3_nr,
            "all_strata_non_regression": strata_nr,
            "conversion_gain_at_least_0_02": gain,
            "advance_to_confirmation": advance,
            "gain_classification": klass,
        }

    eligible = sorted([c for c in challengers if screen[c]["advance_to_confirmation"]],
                      key=lambda c: (-screen[c]["paired_conversion"]["global"]["estimate"], c))
    lead = eligible[0] if eligible else None
    verdict = f"screen_lead_{lead.lower()}" if lead else "screen_no_lead"
    return {
        "schema": 2,
        "experiment": experiment,
        "technical_status": "complete",
        "scientific_verdict": verdict,
        "baseline": baseline,
        "selected_lead": lead,
        "eligible_leads": eligible,
        "automatic_next_job": None,
        "decision_scope": "screen_to_confirmation_only",
        "search_contract": {"parameter_count": len(REQUIRED_SEARCH_KEYS),
                            "common_search_params": common_search,
                            "shared_fingerprint_all_cells": True, "inherited_defaults": False},
        "bootstrap": {"method": "paired_position", "replicates": replicates, "seed": seed},
        "conversion_diagnostics": conversion_diagnostics,
        "paired_statistics": statistics,
        "common_search_gates_vs_baseline": common_gates,
        "native_equal_time_gates_vs_baseline": native_gates,
        "screen": screen,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    spec_path, out_path = Path(args.spec), Path(args.out)
    try:
        report = build_report(_read_json(spec_path, "verdict spec"), spec_path)
    except (OSError, ValueError, TypeError) as exc:
        report = {"schema": 2, "technical_status": "invalid_science", "scientific_verdict": None,
                  "automatic_next_job": None, "error": str(exc)}
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
