#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aggregate the matched G1 conversion start-distribution x reweighting screen."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path
import random
import re
import sys
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stable_conversion_matrix as matrix


CANDIDATES = ("standard_off", "standard_on", "top3_off", "top3_on")
ARMS = ("g4_g0", "g0_g4", "g4_g4")
VALUE = {"L": -1.0, "D": 0.0, "W": 1.0}
RESULT_RE = re.compile(r"^RESULT\s+(\d+)\s+(\d+)\s+(\d+)\s*$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(paths):
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{lineno}: expected object")
            rows.append(value)
    return rows


def validated_arm(
    contract: matrix.PoolContract, root: Path, candidate: str, arm: str,
    *,
    salvage: dict[str, Any] | None = None,
    salvages: list[dict[str, Any]] | None = None,
    adjudications: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    if salvage is not None and salvages is not None:
        raise ValueError("use salvage or salvages, not both")
    pinned = list(salvages or ([salvage] if salvage is not None else []))
    expected_caps = [
        item for item in pinned
        if item["candidate"] == candidate and item["arm"] == arm
    ]
    directory = root / ("common" if arm == "g0_g0" else candidate) / arm
    rows = read_jsonl(directory.glob("s*.jsonl"))
    by_id, failures = matrix.validate_arm_rows(contract, arm, rows)
    technical = [
        row for row in by_id.values()
        if row.get("error") or str(row.get("reason", "")).lower() in matrix.CAP_REASONS
    ]
    if failures:
        raise ValueError(
            f"{candidate}/{arm}: validation failures={failures[:8]} "
            f"technical_rows={len(technical)}"
        )
    if len(technical) != len(expected_caps):
        raise ValueError(
            f"{candidate}/{arm}: validation failures=[] "
            f"technical_rows={len(technical)} expected_pinned={len(expected_caps)}"
        )
    if technical:
        expected_by_id = {item["position_id"]: item for item in expected_caps}
        if len(expected_by_id) != len(expected_caps):
            raise ValueError(f"{candidate}/{arm}: duplicate pinned position")
        observed_by_id = {item["position_id"]: item for item in technical}
        if set(observed_by_id) != set(expected_by_id):
            raise ValueError(
                f"{candidate}/{arm}: pinned position mismatch "
                f"observed={sorted(observed_by_id)} expected={sorted(expected_by_id)}"
            )
        by_id = copy.deepcopy(by_id)
        for position_id in sorted(expected_by_id):
            cap = observed_by_id[position_id]
            pinned_cap = expected_by_id[position_id]
            expected = {
                "position_id": pinned_cap["position_id"],
                "cell": pinned_cap["cell"],
                "reason": "ply cap",
                "plies": pinned_cap["plies"],
                "outcome_white": "D",
                "outcome_plus2": "D",
                "error": None,
            }
            if "shard" in pinned_cap:
                expected["shard"] = pinned_cap["shard"]
            mismatches = {
                key: (cap.get(key), value)
                for key, value in expected.items()
                if cap.get(key) != value
            }
            if mismatches:
                raise ValueError(
                    f"{candidate}/{arm}: pinned ply-cap mismatch {mismatches}"
                )
            raw_sha = hashlib.sha256(
                (
                    json.dumps(cap, sort_keys=True, separators=(",", ":")) + "\n"
                ).encode()
            ).hexdigest()
            by_id[position_id]["reason"] = matrix.SALVAGE_DRAW_REASON
            if adjudications is not None:
                adjudications.append({
                    "policy": "pinned 400-ply cap adjudicated as draw; no replay",
                    **pinned_cap,
                    "raw_row_sha256": raw_sha,
                    "raw_reason": "ply cap",
                    "derived_reason": matrix.SALVAGE_DRAW_REASON,
                    "changes_to_raw_games": 1,
                })
        _, derived_failures = matrix.validate_arm_rows(
            contract,
            arm,
            list(by_id.values()),
            additional_draw_reasons=frozenset({matrix.SALVAGE_DRAW_REASON}),
        )
        if derived_failures:
            raise ValueError(
                f"{candidate}/{arm}: adjudicated validation failed "
                f"{derived_failures[:8]}"
            )
    return by_id


def balanced_result(directory: Path, expected_games: int) -> dict[str, Any]:
    a_wins = draws = b_wins = 0
    paths = sorted(directory.glob("s*.log"))
    if not paths:
        raise ValueError(f"{directory}: no balanced guard logs")
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "game skipped" in text:
            raise ValueError(f"{path}: engine exception/timeout hidden as draw")
        matches = [
            RESULT_RE.match(line) for line in text.splitlines()
            if RESULT_RE.match(line)
        ]
        if len(matches) != 1:
            raise ValueError(f"{path}: expected one RESULT line, got {len(matches)}")
        match = matches[0]
        assert match is not None
        a, d, b = map(int, match.groups())
        a_wins += a
        draws += d
        b_wins += b
    games = a_wins + draws + b_wins
    if games != expected_games:
        raise ValueError(f"{directory}: balanced n={games}, expected {expected_games}")
    return {
        "games": games,
        "candidate_wins": a_wins,
        "draws": draws,
        "g0_wins": b_wins,
        "candidate_score_rate": (a_wins + 0.5 * draws) / games,
    }


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values)


def candidate_endpoints(
    ids: list[str],
    control: dict[str, dict[str, Any]],
    arms: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, float]:
    y00 = mean(VALUE[control[key]["outcome_plus2"]] for key in ids)
    y10 = mean(VALUE[arms["g4_g0"][key]["outcome_plus2"]] for key in ids)
    y01 = mean(VALUE[arms["g0_g4"][key]["outcome_plus2"]] for key in ids)
    y11 = mean(VALUE[arms["g4_g4"][key]["outcome_plus2"]] for key in ids)
    return {
        "g0_g0": y00,
        "candidate_attack": y10,
        "candidate_defence_opponent_plus2": y01,
        "candidate_joint": y11,
        "attack_effect": y10 - y00,
        "defence_effect": y00 - y01,
        "joint_effect": y11 - y00,
        "role_interaction": y11 - y10 - y01 + y00,
    }


def factor_endpoints(cells: dict[str, dict[str, float]], endpoint: str) -> dict[str, float]:
    a = cells["standard_off"][endpoint]
    b = cells["standard_on"][endpoint]
    c = cells["top3_off"][endpoint]
    d = cells["top3_on"][endpoint]
    return {
        "start_top3_main_effect": 0.5 * ((c - a) + (d - b)),
        "reweight_on_main_effect": 0.5 * ((b - a) + (d - c)),
        "start_x_reweight_interaction": d - c - b + a,
        "reweight_with_standard_start": b - a,
        "reweight_with_top3_start": d - c,
        "top3_start_with_reweight_off": c - a,
        "top3_start_with_reweight_on": d - b,
    }


def percentile(values: list[float], q: float) -> float:
    values = sorted(values)
    return values[int(q * (len(values) - 1))]


def bootstrap(
    *,
    contract: matrix.PoolContract,
    control: dict[str, dict[str, Any]],
    candidate_arms: dict[str, dict[str, dict[str, dict[str, Any]]]],
    samples: int,
    seed: int,
) -> dict[str, Any]:
    cells: dict[str, list[str]] = defaultdict(list)
    for position in contract.positions:
        cells[position.cell].append(position.position_id)
    if sorted(len(ids) for ids in cells.values()) != [32] * 12:
        raise ValueError("bootstrap requires 12 cells x 32 positions")
    rng = random.Random(seed)
    endpoint_names = ("attack_effect", "defence_effect", "joint_effect", "role_interaction")
    draws: dict[str, dict[str, list[float]]] = {
        endpoint: defaultdict(list) for endpoint in endpoint_names
    }
    candidate_draws: dict[str, dict[str, list[float]]] = {
        candidate: defaultdict(list) for candidate in CANDIDATES
    }
    for _ in range(samples):
        ids = []
        for cell in sorted(cells):
            source = cells[cell]
            ids.extend(source[rng.randrange(len(source))] for _ in source)
        endpoints = {
            candidate: candidate_endpoints(ids, control, candidate_arms[candidate])
            for candidate in CANDIDATES
        }
        for candidate in CANDIDATES:
            for endpoint in endpoint_names:
                candidate_draws[candidate][endpoint].append(endpoints[candidate][endpoint])
        for endpoint in endpoint_names:
            factors = factor_endpoints(endpoints, endpoint)
            for factor, value in factors.items():
                draws[endpoint][factor].append(value)
    return {
        "samples": samples,
        "seed": seed,
        "candidate_intervals": {
            candidate: {
                endpoint: [
                    percentile(values, 0.025), percentile(values, 0.975)
                ]
                for endpoint, values in sorted(candidate_draws[candidate].items())
            }
            for candidate in CANDIDATES
        },
        "factor_intervals": {
            endpoint: {
                factor: [percentile(values, 0.025), percentile(values, 0.975)]
                for factor, values in sorted(factors.items())
            }
            for endpoint, factors in sorted(draws.items())
        },
    }


def provenance(
    control: dict[str, dict[str, Any]],
    candidates: dict[str, dict[str, dict[str, dict[str, Any]]]],
) -> dict[str, Any]:
    common_fields = ("pool_sha256", "proof_sha256")
    record_fields = ("jass", "g0", "search_params", "matrix_runner", "referee_harness")
    common: dict[str, set[str]] = {field: set() for field in common_fields}
    records: dict[str, set[str]] = {field: set() for field in record_fields}
    g4_hashes: dict[str, set[str]] = {candidate: set() for candidate in CANDIDATES}
    groups = [control]
    for candidate in CANDIDATES:
        groups.extend(candidates[candidate].values())
    for group in groups:
        for row in group.values():
            hashes = row["hashes"]
            for field in common_fields:
                common[field].add(str(hashes[field]))
            for field in record_fields:
                records[field].add(str(hashes[field]["sha256"]))
    for candidate in CANDIDATES:
        for group in candidates[candidate].values():
            for row in group.values():
                g4_hashes[candidate].add(str(row["hashes"]["g4"]["sha256"]))
    failures = []
    for field, values in {**common, **records}.items():
        if len(values) != 1:
            failures.append(f"{field}: expected one hash, got {sorted(values)}")
    for candidate, values in g4_hashes.items():
        if len(values) != 1:
            failures.append(f"{candidate}/g4: expected one hash, got {sorted(values)}")
    if failures:
        raise ValueError("provenance mismatch: " + "; ".join(failures))
    return {
        "common": {field: next(iter(values)) for field, values in common.items()},
        "engine": {field: next(iter(values)) for field, values in records.items()},
        "candidate_g4": {
            candidate: next(iter(values)) for candidate, values in g4_hashes.items()
        },
    }


def effect_signal(value: float, interval: list[float], threshold: float = 0.05) -> bool:
    excludes_zero = interval[0] > 0 or interval[1] < 0
    return abs(value) >= threshold and excludes_zero


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    contract = matrix.load_pool_contract(args.pool, args.proof)
    salvage_manifest = getattr(args, "salvage_manifest", None)
    salvage_values = (
        getattr(args, "salvage_candidate", None),
        getattr(args, "salvage_arm", None),
        getattr(args, "salvage_position_id", None),
        getattr(args, "salvage_cell", None),
    )
    if any(salvage_values) and not all(salvage_values):
        raise ValueError("single-ply-cap salvage parameters must be all-or-none")
    if salvage_manifest is not None and any(salvage_values):
        raise ValueError("salvage manifest and single-cap parameters are exclusive")
    salvages: list[dict[str, Any]] = []
    if all(salvage_values):
        salvages.append({
            "candidate": salvage_values[0],
            "arm": salvage_values[1],
            "position_id": salvage_values[2],
            "cell": salvage_values[3],
            "plies": getattr(args, "salvage_plies", 400),
        })
    if salvage_manifest is not None:
        manifest = json.loads(Path(salvage_manifest).read_text(encoding="utf-8"))
        if manifest.get("schema") != 1:
            raise ValueError("salvage manifest schema must be 1")
        items = manifest.get("adjudications")
        if not isinstance(items, list) or not items:
            raise ValueError("salvage manifest requires non-empty adjudications")
        required = {"candidate", "arm", "position_id", "cell", "plies", "shard"}
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not required.issubset(item):
                raise ValueError(f"invalid salvage manifest entry {index}")
            if item["candidate"] not in CANDIDATES or item["arm"] not in ARMS:
                raise ValueError(f"invalid salvage target {index}")
            if (
                item["plies"] != 400
                or not isinstance(item["shard"], int)
                or not 0 <= item["shard"] < 16
            ):
                raise ValueError(f"invalid salvage cap contract {index}")
            salvages.append({key: item[key] for key in sorted(required)})
    identities = {
        (item["candidate"], item["arm"], item["position_id"])
        for item in salvages
    }
    if len(identities) != len(salvages):
        raise ValueError("duplicate salvage manifest identity")
    adjudications: list[dict[str, Any]] = []
    control = validated_arm(
        contract,
        args.matrix_root,
        "common",
        "g0_g0",
        salvages=salvages,
        adjudications=adjudications,
    )
    ids = [position.position_id for position in contract.positions]
    candidate_arms = {
        candidate: {
            arm: validated_arm(
                contract,
                args.matrix_root,
                candidate,
                arm,
                salvages=salvages,
                adjudications=adjudications,
            )
            for arm in ARMS
        }
        for candidate in CANDIDATES
    }
    if len(adjudications) != len(salvages):
        raise ValueError(
            f"expected {len(salvages)} pinned ply-cap adjudications, "
            f"got {len(adjudications)}"
        )
    endpoints = {
        candidate: candidate_endpoints(ids, control, candidate_arms[candidate])
        for candidate in CANDIDATES
    }
    factors = {
        endpoint: factor_endpoints(endpoints, endpoint)
        for endpoint in ("attack_effect", "defence_effect", "joint_effect", "role_interaction")
    }
    boot = bootstrap(
        contract=contract,
        control=control,
        candidate_arms=candidate_arms,
        samples=args.bootstrap,
        seed=args.seed,
    )
    balanced = {
        candidate: balanced_result(
            args.balanced_root / candidate, args.balanced_games
        )
        for candidate in CANDIDATES
    }
    signals = []
    for endpoint, values in factors.items():
        for factor, value in values.items():
            interval = boot["factor_intervals"][endpoint][factor]
            if effect_signal(value, interval):
                signals.append({
                    "endpoint": endpoint,
                    "factor": factor,
                    "effect": value,
                    "bootstrap_95": interval,
                })
    guards_ok = all(
        item["candidate_score_rate"] >= args.balanced_floor
        for item in balanced.values()
    )
    return {
        "schema": 1,
        "decision": "CONVERSION_2X2_G1_SCREEN_READY",
        "technical_status": (
            "complete" if not adjudications else
            "derived_complete_single_ply_cap" if len(adjudications) == 1 else
            f"derived_complete_{len(adjudications)}_ply_caps"
        ),
        "original_zero_cap_gate_ready": not bool(adjudications),
        "adjudications": adjudications,
        "adjudication_sensitivity_bounds": {
            "raw_games_changed": len(adjudications),
            "max_abs_candidate_endpoint_shift_per_adjudicated_game":
                1.0 / len(ids),
            "max_abs_any_factor_effect_shift_conservative":
                len(adjudications) / len(ids),
        },
        "causal_unit": "one common stable TOP3 position",
        "source_corpus_reuse": {
            "standard_off_on_share_identical_G1_selfplay": True,
            "top3_off_on_share_identical_G1_selfplay": True,
        },
        "contract": {
            "positions": len(ids),
            "cells": 12,
            "positions_per_cell": 32,
            "candidates": list(CANDIDATES),
            "arms_per_candidate": list(ARMS),
            "balanced_games_per_candidate": args.balanced_games,
            "balanced_score_floor": args.balanced_floor,
            "bootstrap_samples": args.bootstrap,
            "bootstrap_seed": args.seed,
        },
        "provenance": provenance(control, candidate_arms),
        "candidate_endpoints": endpoints,
        "factor_effects": factors,
        "bootstrap": boot,
        "balanced_guard": {
            "pass": guards_ok,
            "candidates": balanced,
        },
        "factor_signals_abs_ge_0_05_ci_excludes_zero": signals,
        "promotion_authorized": False,
        "training_continuation_authorized": False,
        "automatic_next_job": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--matrix-root", type=Path, required=True)
    parser.add_argument("--balanced-root", type=Path, required=True)
    parser.add_argument("--balanced-games", type=int, default=128)
    parser.add_argument("--balanced-floor", type=float, default=0.40)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=271828)
    parser.add_argument("--salvage-candidate", choices=CANDIDATES)
    parser.add_argument("--salvage-arm", choices=ARMS)
    parser.add_argument("--salvage-position-id")
    parser.add_argument("--salvage-cell")
    parser.add_argument("--salvage-plies", type=int, default=400)
    parser.add_argument("--salvage-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "decision": report["decision"],
        "balanced_guard": report["balanced_guard"]["pass"],
        "signals": len(report["factor_signals_abs_ge_0_05_ci_excludes_zero"]),
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
