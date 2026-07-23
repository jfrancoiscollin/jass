#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only autopsy of L3-PURE versus the TOP3 specialist recipe.

The tool consumes immutable manifests, generation profiles, G4 PJTW weights,
and the raw 0908/0921 stable-conversion matrices.  It does not train, play,
promote, or authorize a follow-up job.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import struct
import tarfile
from typing import Any

import numpy as np


OUTCOME = {"L": -1, "D": 0, "W": 1}
G4_ROLE_SIGN = {
    "g4_g0": 1,    # G4 is the +2 attacker.
    "g0_g4": -1,   # G4 is the -2 defender.
    "g4_scan": 1,
    "scan_g4": -1,
}
PATTERN_NAMES = (
    "v_top0", "v_top1", "v_top2", "v_top3",
    "v_bot0", "v_bot1", "v_bot2", "v_bot3",
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def profile_row(path: Path, generation: int) -> dict[str, Any]:
    value = read_json(path)
    records = int(value["records"])
    phases = value["phase_records"]
    wdl = value["wdl_stm"]
    conversion = value["record_level_conversion"]
    return {
        "generation": generation,
        "records": records,
        "games": int(value["games"]),
        "records_per_game_mean": float(value["records_per_game"]["mean"]),
        "unique_position_ratio": float(value["unique_position_ratio"]),
        "opening_rate": float(phases["opening"] / records),
        "endgame_plus_deep_rate": float(
            (phases["endgame"] + phases["deep_endgame"]) / records
        ),
        "draw_rate_stm": float(wdl["draw"] / records),
        "record_level_conversion": {
            name: float(conversion[name]["rate"])
            for name in ("p1_clear", "p2_medium", "p3_thin")
        },
        "source_records": value["source_records"],
    }


def lineage_profiles(directory: Path, *, with_reweight: bool) -> dict[str, Any]:
    generations = []
    reweights = []
    for generation in range(1, 5):
        generations.append(profile_row(
            directory / f"g{generation}-profile.json", generation
        ))
        if with_reweight:
            value = read_json(directory / f"g{generation}-reweight.json")
            training = int(value["training_records"])
            exact = int(value["domain"]["records"])
            source = value["source_training_buckets"]
            resampled = value["resampled_training_buckets"]
            resampled_exact = sum(
                int(count) for bucket, count in resampled.items()
                if bucket != "anchor_outside_exact_2men_equal_kings"
            )
            reweights.append({
                "generation": generation,
                "training_records": training,
                "holdout_records_untouched": int(value["holdout_records_untouched"]),
                "exact_domain_records": exact,
                "exact_domain_rate_of_training": float(exact / training),
                "resampled_exact_domain_records": resampled_exact,
                "resampled_exact_domain_rate_of_training": float(
                    resampled_exact / training
                ),
                "outside_domain_anchor_records": int(
                    value["domain"]["outside_domain_anchor_records"]
                ),
                "source_training_buckets": source,
                "resampled_training_buckets": resampled,
                "weight_semantics": value["weight_semantics"],
                "per_move_criticality_relabel": bool(
                    value["per_move_criticality_relabel"]
                ),
            })
    return {"generations": generations, "reweights": reweights}


def compare_manifests(pure_path: Path, specialist_path: Path) -> dict[str, Any]:
    pure = read_json(pure_path)
    specialist = read_json(specialist_path)
    pure_recipe = pure["recipe"]
    spec_recipe = specialist["recipe"]
    pure_fit = pure_recipe["fit"]
    spec_fit = spec_recipe["fit"]
    same_search = (
        pure["search_params_count"] == specialist["search_params_count"] == 63
        and pure_recipe["search_params"] == specialist["search_params"]
    )
    same_optimizer = all(
        pure_fit[key] == spec_fit[key]
        for key in ("chunk", "color_fold", "l2", "loss", "max_iter", "target", "tempo_stage")
    )
    return {
        "same_geometry": pure_recipe["geometry"] == specialist["geometry"] == "8cf",
        "same_search_contract": same_search,
        "same_optimizer_contract": same_optimizer,
        "same_bootstrap": pure_recipe["start"] == "G0_material"
        and specialist["recipe"]["bootstrap"] == "G0 material men=1 king=3",
        "same_exploration_contract": (
            pure_recipe["exploration"]["epsilon_percent"]
            == spec_recipe["epsilon_percent"]
            and pure_recipe["exploration"]["random_open_plies"]
            == spec_recipe["random_open_plies"]
            and pure_recipe["exploration"]["decay_plies"]
            == spec_recipe["explore_decay_plies"]
        ),
        "same_terminal_wdl_no_external_teacher": (
            pure["training_sources"] == ["selfplay_terminal_wdl"]
            and specialist["trajectory_policy"]
            == "terminal WDL self-play only; no static TB teacher"
            and not specialist["external_teacher_used"]
            and not specialist["scan_used_for_training"]
            and not specialist["gen2_used_for_training"]
        ),
        "intentional_differences": {
            "source_positions_per_generation": {
                "pure": int(pure_recipe["positions_per_generation"]),
                "specialist": int(specialist["source_positions_per_generation"]),
            },
            "start_distribution": {
                "pure": "standard balanced start",
                "specialist": specialist["start_distribution"],
            },
            "start_strata": {
                "pure": None,
                "specialist": specialist["start_strata"],
            },
            "role_aware_resampling": {
                "pure": None,
                "specialist": spec_fit["role_aware_fixed_resampling"],
            },
        },
        "specialist_original_gate": specialist["evaluation"],
    }


def read_matrix_tar(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            member_path = PurePosixPath(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"{path}: unsafe tar member {member.name!r}")
            if not member.isfile() or member_path.suffix != ".jsonl":
                continue
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError(f"{path}: cannot read {member.name}")
            for lineno, raw in enumerate(handle, 1):
                row = json.loads(raw)
                key = (str(row["arm"]), str(row["position_id"]))
                if key in rows:
                    raise ValueError(
                        f"{path}:{member.name}:{lineno}: duplicate {key}"
                    )
                rows[key] = row
    if not rows:
        raise ValueError(f"{path}: no matrix rows")
    return rows


def _outcome(row: dict[str, Any]) -> str:
    outcome = row.get("outcome_plus2")
    if outcome not in OUTCOME:
        raise ValueError(
            f"{row.get('arm')}/{row.get('position_id')}: invalid outcome {outcome!r}"
        )
    return str(outcome)


def compare_matrices(specialist_tar: Path, pure_tar: Path) -> dict[str, Any]:
    specialist = read_matrix_tar(specialist_tar)
    pure = read_matrix_tar(pure_tar)
    if set(specialist) != set(pure):
        missing = sorted(set(specialist) - set(pure))[:5]
        extra = sorted(set(pure) - set(specialist))[:5]
        raise ValueError(f"matrix key mismatch; missing={missing}, extra={extra}")

    by_arm: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    pool_hashes = {"specialist": set(), "pure": set()}
    for key in sorted(specialist):
        spec_row = specialist[key]
        pure_row = pure[key]
        for field in ("arm", "position_id", "fen", "cell", "stratum", "advantaged"):
            if spec_row[field] != pure_row[field]:
                raise ValueError(f"{key}: paired field differs: {field}")
        by_arm[key[0]].append((spec_row, pure_row))
        pool_hashes["specialist"].add(spec_row["hashes"]["pool_sha256"])
        pool_hashes["pure"].add(pure_row["hashes"]["pool_sha256"])

    arms: dict[str, Any] = {}
    for arm, pairs in sorted(by_arm.items()):
        transitions = Counter()
        specialist_wdl = Counter()
        pure_wdl = Counter()
        cell_deltas: dict[str, list[float]] = defaultdict(list)
        role_deltas = []
        changed_examples = []
        for spec_row, pure_row in pairs:
            spec_outcome = _outcome(spec_row)
            pure_outcome = _outcome(pure_row)
            transitions[f"{spec_outcome}->{pure_outcome}"] += 1
            specialist_wdl[spec_outcome] += 1
            pure_wdl[pure_outcome] += 1
            raw_delta = OUTCOME[pure_outcome] - OUTCOME[spec_outcome]
            cell_deltas[str(spec_row["cell"])].append(float(raw_delta))
            if arm in G4_ROLE_SIGN:
                role_delta = float(G4_ROLE_SIGN[arm] * raw_delta)
                role_deltas.append(role_delta)
                if role_delta:
                    changed_examples.append({
                        "position_id": spec_row["position_id"],
                        "cell": spec_row["cell"],
                        "specialist": spec_outcome,
                        "pure": pure_outcome,
                        "g4_role_delta": role_delta,
                    })
        item: dict[str, Any] = {
            "n": len(pairs),
            "specialist_wdl_plus2": dict(sorted(specialist_wdl.items())),
            "pure_wdl_plus2": dict(sorted(pure_wdl.items())),
            "transition_counts_specialist_to_pure": dict(sorted(transitions.items())),
            "mean_plus2_outcome_delta": float(np.mean([
                OUTCOME[_outcome(p)] - OUTCOME[_outcome(s)] for s, p in pairs
            ])),
            "cells": {
                cell: {"n": len(values), "mean_plus2_outcome_delta": float(np.mean(values))}
                for cell, values in sorted(cell_deltas.items())
            },
        }
        if role_deltas:
            item["g4_role_effect_pure_minus_specialist"] = {
                "mean": float(np.mean(role_deltas)),
                "improved_positions": int(sum(value > 0 for value in role_deltas)),
                "regressed_positions": int(sum(value < 0 for value in role_deltas)),
                "unchanged_positions": int(sum(value == 0 for value in role_deltas)),
                "changed_examples": changed_examples[:24],
            }
        arms[arm] = item

    controls = {}
    for arm in ("g0_g0", "scan_scan"):
        pairs = by_arm.get(arm, [])
        controls[arm] = {
            "n": len(pairs),
            "identical_outcomes": int(sum(_outcome(s) == _outcome(p) for s, p in pairs)),
            "identical_plies": int(sum(s["plies"] == p["plies"] for s, p in pairs)),
        }
    return {
        "paired_rows": len(specialist),
        "paired_positions_per_arm": sorted({len(value) for value in by_arm.values()}),
        "arms": arms,
        "controls": controls,
        "pool_sha256": {
            label: sorted(values) for label, values in pool_hashes.items()
        },
        "same_pool_hash": pool_hashes["specialist"] == pool_hashes["pure"],
    }


def parse_pjtw(path: Path) -> dict[str, Any]:
    raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    if len(raw) < 20 or raw[:4] != b"PJTW":
        raise ValueError(f"{path}: invalid PJTW")
    version, scale, n_pat, n_ext = struct.unpack_from("<IIII", raw, 4)
    weights = np.frombuffer(raw, dtype="<i4", offset=20)
    expected = 2 * (n_pat + n_ext)
    if weights.size != expected:
        raise ValueError(f"{path}: {weights.size} weights, expected {expected}")
    return {
        "version": int(version),
        "scale": int(scale),
        "n_pat": int(n_pat),
        "n_ext": int(n_ext),
        "raw_bytes": len(raw),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": sha256(path),
        "pattern_mg": weights[:n_pat],
        "pattern_eg": weights[n_pat:2 * n_pat],
        "extra_mg": weights[2 * n_pat:2 * n_pat + n_ext],
        "extra_eg": weights[2 * n_pat + n_ext:],
    }


def _finite(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def vector_delta(pure: np.ndarray, specialist: np.ndarray) -> dict[str, Any]:
    if pure.shape != specialist.shape:
        raise ValueError(f"weight shape mismatch {pure.shape} != {specialist.shape}")
    left = pure.astype(np.float64)
    right = specialist.astype(np.float64)
    delta = right - left
    abs_delta = np.abs(delta)
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    corr = (
        float(np.corrcoef(left, right)[0, 1])
        if left.size and np.std(left) and np.std(right) else None
    )
    return {
        "n": int(left.size),
        "changed": int(np.count_nonzero(delta)),
        "changed_rate": float(np.count_nonzero(delta) / left.size) if left.size else 0.0,
        "mean_absolute_delta_raw": float(np.mean(abs_delta)) if left.size else 0.0,
        "rms_delta_raw": float(np.sqrt(np.mean(delta * delta))) if left.size else 0.0,
        "max_absolute_delta_raw": float(np.max(abs_delta)) if left.size else 0.0,
        "pure_rms_raw": float(np.sqrt(np.mean(left * left))) if left.size else 0.0,
        "specialist_rms_raw": float(np.sqrt(np.mean(right * right))) if left.size else 0.0,
        "cosine_similarity": _finite(float(np.dot(left, right) / denom)) if denom else None,
        "pearson_correlation": _finite(corr) if corr is not None else None,
        "opposite_nonzero_signs": int(np.count_nonzero(left * right < 0)),
        "absolute_delta_quantiles_raw": {
            str(q): float(np.quantile(abs_delta, q))
            for q in (0.5, 0.9, 0.95, 0.99, 0.999)
        } if left.size else {},
    }


def compare_models(pure_path: Path, specialist_path: Path) -> dict[str, Any]:
    pure = parse_pjtw(pure_path)
    specialist = parse_pjtw(specialist_path)
    for key in ("version", "scale", "n_pat", "n_ext", "raw_bytes"):
        if pure[key] != specialist[key]:
            raise ValueError(f"model contract differs at {key}")
    blocks = {}
    if pure["n_pat"] % len(PATTERN_NAMES) == 0:
        width = pure["n_pat"] // len(PATTERN_NAMES)
        for phase in ("pattern_mg", "pattern_eg"):
            blocks[phase] = {
                name: vector_delta(
                    pure[phase][index * width:(index + 1) * width],
                    specialist[phase][index * width:(index + 1) * width],
                )
                for index, name in enumerate(PATTERN_NAMES)
            }
    metadata_keys = (
        "version", "scale", "n_pat", "n_ext", "raw_bytes",
        "raw_sha256", "compressed_sha256",
    )
    return {
        "pure": {key: pure[key] for key in metadata_keys},
        "specialist": {key: specialist[key] for key in metadata_keys},
        "banks": {
            bank: vector_delta(pure[bank], specialist[bank])
            for bank in ("pattern_mg", "pattern_eg", "extra_mg", "extra_eg")
        },
        "pattern_blocks": blocks,
        "interpretation_limit": (
            "Weight drift is observational: sparse pattern correlations and dense "
            "extra-weight changes localise a different fitted function but cannot "
            "separate the start-distribution effect from role-aware resampling."
        ),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    manifest_comparison = compare_manifests(
        args.pure_dir / "l3-pure-p1-manifest.json",
        args.specialist_dir / "l3-imbalance2-top3-p1-manifest.json",
    )
    profiles = {
        "pure": lineage_profiles(args.pure_dir, with_reweight=False),
        "specialist": lineage_profiles(args.specialist_dir, with_reweight=True),
    }
    matrices = compare_matrices(args.specialist_matrix_tar, args.pure_matrix_tar)
    models = compare_models(
        args.pure_dir / "g4.pjtw.gz",
        args.specialist_dir / "g4.pjtw.gz",
    )
    return {
        "schema": 1,
        "decision": "TOP3_SPECIALIST_RECIPE_FAILURE_LOCALIZED_FACTORS_CONFOUNDED",
        "scope": "read_only_post_hoc_autopsy",
        "inputs": {
            "pure_manifest_sha256": sha256(args.pure_dir / "l3-pure-p1-manifest.json"),
            "specialist_manifest_sha256": sha256(
                args.specialist_dir / "l3-imbalance2-top3-p1-manifest.json"
            ),
            "specialist_matrix_tar_sha256": sha256(args.specialist_matrix_tar),
            "pure_matrix_tar_sha256": sha256(args.pure_matrix_tar),
        },
        "manifest_comparison": manifest_comparison,
        "profiles": profiles,
        "paired_conversion_matrix": matrices,
        "model_weight_comparison": models,
        "findings": [
            "Architecture, search, optimizer, exploration, bootstrap, and terminal-WDL/no-teacher contracts match.",
            "The specialist changes start distribution, corpus volume, and role-aware resampling together.",
            "The paired matrix controls reproduce exactly, so the large role deltas are attributable to the substituted G4 model on this pool.",
            "TOP3 source trajectories contain almost no opening records and are dominated by endgame/deep-endgame records.",
            "Only a small minority of specialist training records remain in the exact +2-men/equal-kings domain where 1/2/4 resampling applies.",
            "The specialist G4 fitted function differs materially from L3-PURE, especially in dense extras; weight inspection alone is not causal.",
        ],
        "causal_limits": [
            "This historical comparison does not isolate TOP3 starts from role-aware 1/2/4 resampling.",
            "It does not isolate the fourfold source-volume increase.",
            "Correlated record-level conversion rates are diagnostics, not independent game-level gates.",
            "No single mechanism may be declared causal without a controlled ablation.",
        ],
        "minimal_followup_doe": {
            "design": "2x2 start-distribution x reweighting ablation",
            "fixed": [
                "same G0 parent",
                "same 8cf architecture and 63 search parameters",
                "same self-play depth, seeds, exploration, source volume, split, optimizer, and terminal-WDL labels",
                "same stable TOP3 paired conversion gate",
            ],
            "arms": [
                {"start": "standard", "reweight": "none"},
                {"start": "standard", "reweight": "role-aware-v2"},
                {"start": "TOP3", "reweight": "none"},
                {"start": "TOP3", "reweight": "role-aware-v2"},
            ],
            "primary_endpoints": [
                "paired G4 attack delta",
                "paired G4 defence delta",
                "joint and interaction deltas",
                "balanced-position regression guard",
            ],
            "authorization": {
                "prepared": False,
                "launch_authorized": False,
                "automatic_next_job": None,
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pure-dir", type=Path, required=True)
    parser.add_argument("--specialist-dir", type=Path, required=True)
    parser.add_argument("--specialist-matrix-tar", type=Path, required=True)
    parser.add_argument("--pure-matrix-tar", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "decision": report["decision"],
        "out": str(args.out),
        "paired_rows": report["paired_conversion_matrix"]["paired_rows"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
