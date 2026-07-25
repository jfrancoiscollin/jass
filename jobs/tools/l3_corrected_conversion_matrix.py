#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aggregate the corrected L3 fixed-defender conversion matrix.

The input documents are produced by ``aggregate_conv_shards.py`` on one
shared JNNW gauge.  Comparisons are paired by position index.  A draw is a
valid non-conversion outcome, so it remains in the paired sample instead of
being silently discarded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


VALID_RESULTS = {"win", "draw", "loss"}
SUMMARY_KEYS = ("n_pos", "n_win", "n_draw", "n_loss", "conversion")


def load_document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def position_outcomes(document: dict[str, Any]) -> dict[int, str]:
    outcomes: dict[int, str] = {}
    for row in document.get("position_results", []):
        result = row.get("result")
        if result not in VALID_RESULTS:
            continue
        index = int(row["index"])
        if index in outcomes:
            raise ValueError(f"duplicate position index {index}")
        outcomes[index] = str(result)
    return outcomes


def paired_conversion(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    *,
    seed: int,
    bootstrap_samples: int,
) -> dict[str, Any]:
    cand = position_outcomes(candidate)
    base = position_outcomes(baseline)
    common = sorted(set(cand) & set(base))
    if not common:
        raise ValueError("paired comparison has no common valid positions")

    cand_win = np.fromiter(
        (cand[index] == "win" for index in common), dtype=np.int8
    )
    base_win = np.fromiter(
        (base[index] == "win" for index in common), dtype=np.int8
    )
    differences = cand_win - base_win
    counts = np.array(
        [
            int(np.count_nonzero(differences == -1)),
            int(np.count_nonzero(differences == 0)),
            int(np.count_nonzero(differences == 1)),
        ],
        dtype=np.int64,
    )

    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    rng = np.random.default_rng(seed)
    bootstrap = rng.multinomial(
        len(common), counts / counts.sum(), size=bootstrap_samples
    )
    bootstrap_delta = (bootstrap[:, 2] - bootstrap[:, 0]) / len(common)

    return {
        "n_common": len(common),
        "candidate_rate": float(cand_win.mean()),
        "baseline_rate": float(base_win.mean()),
        "delta": float(differences.mean()),
        "ci_low": float(np.quantile(bootstrap_delta, 0.025)),
        "ci_high": float(np.quantile(bootstrap_delta, 0.975)),
        "baseline_win_to_candidate_nonwin": int(counts[0]),
        "same_conversion_status": int(counts[1]),
        "baseline_nonwin_to_candidate_win": int(counts[2]),
        "draws_count_as_nonconversion": True,
    }


def force_summary(path: Path) -> dict[str, Any]:
    document = load_document(path)
    keys = ("n", "wins_a", "draws", "wins_b", "rate", "elo", "ci_low", "ci_high")
    return {key: document[key] for key in keys}


def build_matrix(
    *,
    conversion_dir: Path,
    models: list[str],
    strata: list[str],
    baseline: str,
    primary_stratum: str,
    preservation_stratum: str,
    bootstrap_samples: int,
    seed: int,
    force_dir: Path | None = None,
) -> dict[str, Any]:
    if baseline not in models:
        raise ValueError("baseline must be present in models")
    if primary_stratum not in strata or preservation_stratum not in strata:
        raise ValueError("selection strata must be present in strata")
    if len(models) != len(set(models)):
        raise ValueError("models must be unique")

    documents: dict[str, dict[str, dict[str, Any]]] = {}
    conversion: dict[str, dict[str, dict[str, Any]]] = {}
    for model in models:
        documents[model] = {}
        conversion[model] = {}
        for stratum in strata:
            path = conversion_dir / f"{model}-{stratum}.json"
            document = load_document(path)
            documents[model][stratum] = document
            conversion[model][stratum] = {
                key: document[key] for key in SUMMARY_KEYS
            }

    paired_matrix: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for stratum_index, stratum in enumerate(strata):
        paired_matrix[stratum] = {}
        for candidate_index, candidate in enumerate(models):
            paired_matrix[stratum][candidate] = {}
            for baseline_index, comparison_baseline in enumerate(models):
                if candidate == comparison_baseline:
                    continue
                comparison_seed = (
                    seed
                    + stratum_index * 10000
                    + candidate_index * 100
                    + baseline_index
                )
                paired_matrix[stratum][candidate][comparison_baseline] = (
                    paired_conversion(
                        documents[candidate][stratum],
                        documents[comparison_baseline][stratum],
                        seed=comparison_seed,
                        bootstrap_samples=bootstrap_samples,
                    )
                )

    challengers = [model for model in models if model != baseline]
    ranked = sorted(
        challengers,
        key=lambda model: (
            -paired_matrix[primary_stratum][model][baseline]["delta"],
            -paired_matrix[preservation_stratum][model][baseline]["delta"],
            model,
        ),
    )
    best = ranked[0]
    eligibility: dict[str, dict[str, Any]] = {}
    for model in ranked:
        primary = paired_matrix[primary_stratum][model][baseline]
        preservation = paired_matrix[preservation_stratum][model][baseline]
        eligibility[model] = {
            "primary_delta_positive": primary["delta"] > 0,
            "primary_confirmed": primary["ci_low"] > 0,
            "preservation_not_disproved": preservation["ci_high"] >= 0,
            "eligible_for_force_review": (
                primary["delta"] > 0 and preservation["ci_high"] >= 0
            ),
        }

    best_primary = paired_matrix[primary_stratum][best][baseline]
    best_preservation = paired_matrix[preservation_stratum][best][baseline]
    force_candidate = best if best_primary["delta"] > 0 else None
    if force_candidate is None:
        evidence_strength = "no_positive_challenger"
    elif best_primary["ci_low"] > 0 and best_preservation["ci_high"] >= 0:
        evidence_strength = "confirmed_conversion_candidate"
    elif best_preservation["ci_high"] >= 0:
        evidence_strength = "directional_conversion_candidate"
    else:
        evidence_strength = "conversion_tradeoff_candidate"

    force: dict[str, Any] | None = None
    if force_dir is not None and force_candidate is not None:
        force = {}
        for view, opponent in (
            ("q00", "C0"),
            ("native", "C0"),
            ("q00", "GEN2"),
        ):
            key = f"{view}_vs_{opponent}"
            path = force_dir / f"force-{view}-{force_candidate}-vs-{opponent}.json"
            force[key] = force_summary(path)

    return {
        "schema": 1,
        "verdict": "M1_CORRECTED_CONVERSION_MATRIX_READY_HUMAN_REVIEW",
        "evidence_strength": evidence_strength,
        "protocol": {
            "fixed_defender": "GEN2",
            "shared_corrected_stable_gauge": True,
            "old_fen_gauge_excluded": True,
            "paired_unit": "position_index",
            "draw_treatment": "valid_nonconversion",
            "bootstrap_samples": bootstrap_samples,
            "primary": f"{primary_stratum} paired conversion delta vs {baseline}",
            "preservation": (
                f"{preservation_stratum} CI high >= 0 means regression is "
                "not established"
            ),
        },
        "conversion": conversion,
        "paired_matrix": paired_matrix,
        "ranking_vs_baseline": ranked,
        "eligibility": eligibility,
        "selected_challenger_for_force_review": force_candidate,
        "force": force,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversion-dir", type=Path, required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--strata", nargs="+", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--primary-stratum", required=True)
    parser.add_argument("--preservation-stratum", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=955_001)
    parser.add_argument("--force-dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_matrix(
        conversion_dir=args.conversion_dir,
        models=args.models,
        strata=args.strata,
        baseline=args.baseline,
        primary_stratum=args.primary_stratum,
        preservation_stratum=args.preservation_stratum,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
        force_dir=args.force_dir,
    )
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialized, encoding="utf-8")
    if args.summary_out is not None:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
