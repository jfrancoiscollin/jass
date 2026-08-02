#!/usr/bin/env python3
"""Contract-complete verdict for the one-cell quiescence reopening replay.

Q01 and Q00 use the same EXACT model and current engine.  The only permitted
search difference is ``qs_sacs=0 -> 1``.  Fixed-depth strength and per-stratum
conversion are diagnostics; equal-time strength and pooled paired conversion
are the two pre-registered co-primary outcomes.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np

try:
    from l3_q1_verdict import REQUIRED_SEARCH_KEYS, parse_search_params as parse_historical
except ImportError:  # pragma: no cover - package import in unit tests
    from jobs.tools.l3_q1_verdict import (
        REQUIRED_SEARCH_KEYS,
        parse_search_params as parse_historical,
    )


ARMS = ("Q00", "Q01")
STRATA = ("p3_mince", "p4_egal")
PLAYED = {"win", "draw", "loss"}
EXPECTED_POOL_SHA = {
    "p3_mince": "cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91",
    "p4_egal": "0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac",
}
CONFIDENCE = 0.975
CURRENT_SEARCH_KEYS = REQUIRED_SEARCH_KEYS + (
    "scan_verify_pruning",
    "scan_threat_reentry",
)


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected a JSON object")
    return value


def parse_current_search_params(spec: str, label: str) -> dict[str, int]:
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
    required = set(CURRENT_SEARCH_KEYS)
    if set(values) != required:
        missing = sorted(required - set(values))
        extra = sorted(set(values) - required)
        raise ValueError(
            f"{label}: expected exactly 65 current search keys; "
            f"missing={missing}, extra={extra}"
        )
    return values


def validate_arm_contract(q00: str, q01: str, defender_q00: str) -> dict[str, Any]:
    base = parse_current_search_params(q00, "Q00")
    sacs = parse_current_search_params(q01, "Q01")
    defender = parse_historical(defender_q00, "fixed defender Q00")
    expected = {
        "qs_threat_ext": 0,
        "qs_sacs_depth0_only": 1,
        "qs_forcing_depth": 0,
        "qs_promo_depth": 0,
        "scan_verify_pruning": 0,
        "scan_threat_reentry": 0,
    }
    for label, values in (("Q00", base), ("Q01", sacs)):
        for key, wanted in expected.items():
            if values[key] != wanted:
                raise ValueError(f"{label}: {key}={values[key]}, expected {wanted}")
    if base["qs_sacs"] != 0 or sacs["qs_sacs"] != 1:
        raise ValueError("Q00/Q01 must set qs_sacs to 0/1 respectively")
    differences = sorted(key for key in CURRENT_SEARCH_KEYS if base[key] != sacs[key])
    if differences != ["qs_sacs"]:
        raise ValueError(f"Q00/Q01 must differ only on qs_sacs, got {differences}")
    drift = sorted(key for key in REQUIRED_SEARCH_KEYS if base[key] != defender[key])
    if drift:
        raise ValueError(f"fixed defender Q00 differs on historical keys: {drift}")
    return {
        "attacker_parameter_count": len(CURRENT_SEARCH_KEYS),
        "defender_parameter_count": len(REQUIRED_SEARCH_KEYS),
        "differences": differences,
    }


def gate_summary(
    document: dict[str, Any],
    *,
    label: str,
    q00: str,
    q01: str,
    expected_games: int,
    native: bool,
) -> tuple[dict[str, Any], list[str]]:
    if document.get("complete") is not True:
        raise ValueError(f"{label}: incomplete gate")
    if document.get("search_params_a") != q01 or document.get("search_params_b") != q00:
        raise ValueError(f"{label}: Q01/Q00 search fingerprints are not the registered arms")
    if document.get("jass_a") != document.get("jass_b"):
        raise ValueError(f"{label}: arms do not share the same engine")
    if document.get("pattern_a") != document.get("pattern_b"):
        raise ValueError(f"{label}: arms do not share the same EXACT model")
    if native:
        if document.get("depth") is not None or document.get("movetime") != 0.1:
            raise ValueError(f"{label}: expected equal movetime=0.1")
    elif document.get("depth") != 9 or document.get("movetime") is not None:
        raise ValueError(f"{label}: expected fixed depth=9")

    counters = tuple(document.get(key) for key in ("wins_a", "draws", "wins_b"))
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counters):
        raise ValueError(f"{label}: invalid raw W/D/L counters")
    wins, draws, losses = counters
    n = wins + draws + losses
    if document.get("n") != n or n <= 0:
        raise ValueError(f"{label}: n does not match raw W/D/L counters")
    rate = (wins + 0.5 * draws) / n
    variance = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    z = NormalDist().inv_cdf(0.5 + CONFIDENCE / 2)
    radius = z * math.sqrt(variance / n)
    low, high = max(0.0, rate - radius), min(1.0, rate + radius)
    issues = [] if n == expected_games else [f"{label}: n={n}, expected exactly {expected_games}"]
    return {
        "n": n,
        "wins_q01": wins,
        "draws": draws,
        "wins_q00": losses,
        "rate_q01": round(rate, 6),
        "delta_from_null": round(rate - 0.5, 6),
        "ci97_5": [round(low, 6), round(high, 6)],
        "null": 0.5,
        "established_movement": low > 0.5 or high < 0.5,
        "direction": "positive" if low > 0.5 else "negative" if high < 0.5 else "flat",
    }, issues


def conversion_document(
    path: Path,
    *,
    arm: str,
    stratum: str,
    fingerprint: str,
    defender_fingerprint: str,
) -> dict[str, Any]:
    document = read_json(path, f"{arm}/{stratum}")
    stale = sorted({"conversion_rate", "records"} & set(document))
    if stale:
        raise ValueError(f"{arm}/{stratum}: stale aggregate keys present: {stale}")
    for key in ("conversion", "n_pos"):
        if key not in document:
            raise ValueError(f"{arm}/{stratum}: missing real aggregate key {key}")
    if document.get("complete") is not True or document.get("schema") != 2:
        raise ValueError(f"{arm}/{stratum}: complete schema-2 aggregate required")
    if document.get("stratum") != stratum:
        raise ValueError(f"{arm}/{stratum}: stratum mismatch")
    if document.get("expected_records") != 300 or document.get("accounted_records") != 300:
        raise ValueError(f"{arm}/{stratum}: expected/accounted records must both be 300")
    if document.get("pool_sha256") != EXPECTED_POOL_SHA[stratum]:
        raise ValueError(f"{arm}/{stratum}: immutable gauge SHA mismatch")
    if document.get("search_params") != fingerprint:
        raise ValueError(f"{arm}/{stratum}: attacker fingerprint mismatch")
    if document.get("defender_search_params") != defender_fingerprint:
        raise ValueError(f"{arm}/{stratum}: defender fingerprint mismatch")
    if document.get("depth") != 10 or document.get("movetime") is not None:
        raise ValueError(f"{arm}/{stratum}: expected fixed conversion depth=10")

    counters = tuple(document.get(key) for key in ("n_pos", "n_win", "n_draw", "n_loss"))
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counters):
        raise ValueError(f"{arm}/{stratum}: invalid conversion counters")
    n_pos, wins, draws, losses = counters
    if n_pos != wins + draws + losses or n_pos <= 0:
        raise ValueError(f"{arm}/{stratum}: W/D/L does not match n_pos")
    expected_conversion = wins / n_pos
    conversion = document["conversion"]
    if not isinstance(conversion, (int, float)) or isinstance(conversion, bool):
        raise ValueError(f"{arm}/{stratum}: conversion must be numeric")
    if not math.isclose(float(conversion), expected_conversion, abs_tol=5.1e-7):
        raise ValueError(f"{arm}/{stratum}: conversion does not match n_win/n_pos")

    rows = document.get("position_results")
    if not isinstance(rows, list) or len(rows) != 300:
        raise ValueError(f"{arm}/{stratum}: position_results must contain 300 rows")
    indices: set[int] = set()
    outcome_counts: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{arm}/{stratum}: malformed position row")
        index, outcome = row.get("index"), row.get("result")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ValueError(f"{arm}/{stratum}: invalid position index")
        if index in indices:
            raise ValueError(f"{arm}/{stratum}: duplicate position index {index}")
        if outcome not in PLAYED | {"error", "skipped_draw_label"}:
            raise ValueError(f"{arm}/{stratum}: invalid position outcome {outcome!r}")
        indices.add(index)
        outcome_counts[outcome] += 1
    if indices != set(range(300)):
        raise ValueError(f"{arm}/{stratum}: source index coverage is not exactly 0..299")
    expected_outcomes = {
        "win": wins,
        "draw": draws,
        "loss": losses,
        "error": document.get("n_errors", 0),
        "skipped_draw_label": document.get("n_skipped_draw_label", 0),
    }
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0
           for value in expected_outcomes.values()):
        raise ValueError(f"{arm}/{stratum}: invalid error/skip counters")
    if outcome_counts != Counter(expected_outcomes):
        raise ValueError(f"{arm}/{stratum}: position trace does not match aggregate counters")
    if sum(expected_outcomes.values()) != 300:
        raise ValueError(f"{arm}/{stratum}: played/error/skip accounting is not 300")
    return document


def paired_conversion(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    *,
    bootstrap_samples: int,
    seed: int,
) -> tuple[dict[str, Any], list[tuple[int, int]]]:
    if bootstrap_samples < 1000:
        raise ValueError("bootstrap requires at least 1000 samples")

    def played_rows(document: dict[str, Any]) -> dict[int, str]:
        return {
            int(row["index"]): str(row["result"])
            for row in document["position_results"]
            if row["result"] in PLAYED
        }

    cand, base = played_rows(candidate), played_rows(baseline)
    common = sorted(set(cand) & set(base))
    if not common:
        raise ValueError("paired conversion has no common played positions")
    pairs = [(int(cand[index] == "win"), int(base[index] == "win")) for index in common]
    differences = np.fromiter((a - b for a, b in pairs), dtype=np.int8)
    counts = np.array(
        [np.count_nonzero(differences == -1), np.count_nonzero(differences == 0),
         np.count_nonzero(differences == 1)],
        dtype=np.int64,
    )
    rng = np.random.default_rng(seed)
    samples = rng.multinomial(len(common), counts / counts.sum(), size=bootstrap_samples)
    deltas = (samples[:, 2] - samples[:, 0]) / len(common)
    tail = (1.0 - CONFIDENCE) / 2.0
    low, high = np.quantile(deltas, [tail, 1.0 - tail])
    delta = float(differences.mean())
    return {
        "n_common": len(common),
        "q01_conversion": round(sum(a for a, _ in pairs) / len(common), 6),
        "q00_conversion": round(sum(b for _, b in pairs) / len(common), 6),
        "delta_q01_minus_q00": round(delta, 6),
        "ci97_5": [round(float(low), 6), round(float(high), 6)],
        "null": 0.0,
        "established_movement": bool(low > 0 or high < 0),
        "direction": "positive" if low > 0 else "negative" if high < 0 else "flat",
        "q00_win_to_q01_nonwin": int(counts[0]),
        "same_conversion_status": int(counts[1]),
        "q00_nonwin_to_q01_win": int(counts[2]),
    }, pairs


def build_report(
    *,
    fixed_gate_path: Path,
    native_gate_path: Path,
    conversion_dir: Path,
    q00: str,
    q01: str,
    defender_q00: str,
    expected_games_per_view: int,
    min_paired_per_stratum: int,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    arm_contract = validate_arm_contract(q00, q01, defender_q00)
    fixed, fixed_issues = gate_summary(
        read_json(fixed_gate_path, "fixed gate"), label="fixed gate", q00=q00,
        q01=q01, expected_games=expected_games_per_view, native=False,
    )
    native, native_issues = gate_summary(
        read_json(native_gate_path, "native gate"), label="native gate", q00=q00,
        q01=q01, expected_games=expected_games_per_view, native=True,
    )

    documents: dict[str, dict[str, dict[str, Any]]] = {arm: {} for arm in ARMS}
    for arm, fingerprint in (("Q00", q00), ("Q01", q01)):
        for stratum in STRATA:
            documents[arm][stratum] = conversion_document(
                conversion_dir / f"{arm}-{stratum}.json",
                arm=arm, stratum=stratum, fingerprint=fingerprint,
                defender_fingerprint=defender_q00,
            )

    comparable = ("pool_sha256", "jass", "defender_jass", "pattern", "defender_pattern")
    per_stratum: dict[str, dict[str, Any]] = {}
    pooled_pairs: list[tuple[int, int]] = []
    issues = fixed_issues + native_issues
    for offset, stratum in enumerate(STRATA):
        q00_doc, q01_doc = documents["Q00"][stratum], documents["Q01"][stratum]
        for key in comparable:
            if q00_doc.get(key) != q01_doc.get(key):
                raise ValueError(f"{stratum}: Q00/Q01 conversion differs on {key}")
        summary, pairs = paired_conversion(
            q01_doc, q00_doc, bootstrap_samples=bootstrap_samples, seed=seed + offset,
        )
        per_stratum[stratum] = summary
        pooled_pairs.extend(pairs)
        if summary["n_common"] < min_paired_per_stratum:
            issues.append(
                f"{stratum}: n_common={summary['n_common']}, minimum={min_paired_per_stratum}"
            )

    cand_rows = {"position_results": []}
    base_rows = {"position_results": []}
    for index, (candidate, baseline) in enumerate(pooled_pairs):
        cand_rows["position_results"].append(
            {"index": index, "result": "win" if candidate else "loss"}
        )
        base_rows["position_results"].append(
            {"index": index, "result": "win" if baseline else "loss"}
        )
    pooled, _ = paired_conversion(
        cand_rows, base_rows, bootstrap_samples=bootstrap_samples, seed=seed + 100,
    )

    if issues:
        verdict = "QUIESCENCE_REOPEN_INCONCLUSIVE"
    elif native["established_movement"] or pooled["established_movement"]:
        verdict = "QUIESCENCE_REOPEN_0812"
    else:
        verdict = "QUIESCENCE_CLOSE_CONFIRMED"
    return {
        "schema": 1,
        "experiment": "L3-QUIESCENCE-Q01-REOPEN",
        "technical_status": "inconclusive" if issues else "complete",
        "scientific_verdict": verdict,
        "code_scope": "current job SHA for both EXACT arms; fixed 9c1d1e8e defender",
        "historical_bug_is_hypothesis_not_cause": True,
        "arm_contract": arm_contract,
        "sizing": {
            "expected_games_per_force_view": expected_games_per_view,
            "expected_conversion_records_per_arm_stratum": 300,
            "minimum_paired_per_stratum": min_paired_per_stratum,
        },
        "decision_rule": {
            "co_primary": ["native_equal_time_strength", "pooled_p3_p4_conversion"],
            "confidence_each": CONFIDENCE,
            "multiplicity": "Bonferroni: two co-primary 97.5% central intervals",
            "fixed_depth_is_diagnostic_only": True,
            "separate_strata_are_diagnostic_only": True,
        },
        "force": {"fixed_depth_9": fixed, "native_movetime_0_1": native},
        "conversion": {"per_stratum": per_stratum, "pooled_p3_p4": pooled},
        "technical_issues": issues,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixed-gate", required=True, type=Path)
    parser.add_argument("--native-gate", required=True, type=Path)
    parser.add_argument("--conversion-dir", required=True, type=Path)
    parser.add_argument("--q00", required=True)
    parser.add_argument("--q01", required=True)
    parser.add_argument("--defender-q00", required=True)
    parser.add_argument("--expected-games-per-view", type=int, default=3000)
    parser.add_argument("--min-paired-per-stratum", type=int, default=270)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_report(
            fixed_gate_path=args.fixed_gate,
            native_gate_path=args.native_gate,
            conversion_dir=args.conversion_dir,
            q00=args.q00,
            q01=args.q01,
            defender_q00=args.defender_q00,
            expected_games_per_view=args.expected_games_per_view,
            min_paired_per_stratum=args.min_paired_per_stratum,
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 4
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
