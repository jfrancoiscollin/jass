#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact-label and independently confirm one frozen CURRICULUM repair rule.

The module deliberately separates target-free preparation, historical move
normalisation, batched exact judgements, first-valid-pair selection and final
statistics.  This makes the first 300 disagreement/agreement pairs auditable
without fitting on, ranking by, or repeatedly peeking at the fresh targets.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from jobs.tools import l3_curriculum_error_fresh_pair_availability_preflight as availability
from jobs.tools import l3_curriculum_error_learning as learning
from jobs.tools import l3_curriculum_error_residual_power_extension_preregistration as power
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge
from jobs.tools import l3_curriculum_error_trace_residual_training as training
from jobs.tools import l3_curriculum_search_error_atlas as atlas
from jobs.tools import l3_curriculum_error_action_ranker as ranker


SCHEMA_PREPARED = "jass.l3_curriculum_error_fresh_confirmation_prepared.v1"
SCHEMA_CATALOG = "jass.l3_curriculum_error_fresh_confirmation_catalog.v1"
SCHEMA_CACHE = "jass.l3_curriculum_error_fresh_confirmation_target_cache.v1"
SCHEMA_PLAN = "jass.l3_curriculum_error_fresh_confirmation_batch_plan.v1"
SCHEMA_REPORT = "jass.l3_curriculum_error_fresh_powered_confirmation.v1"
READY = "JASS_CURRICULUM_ERROR_FRESH_POWERED_CONFIRMATION_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_FRESH_POWERED_CONFIRMATION_NOT_ESTABLISHED"
FRESH_PAIRS = power.FRESH_PAIRS
JUDGE_DEPTH = 12
NSHARDS = 16


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _load_many(paths: Iterable[Path]) -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _check_preregistration(report: dict[str, Any]) -> dict[str, Any]:
    if (
        report.get("schema") != power.SCHEMA
        or report.get("verdict") != power.READY
        or report.get("passed") is not True
    ):
        raise ValueError("fresh confirmation preregistration drift")
    selected = report.get("selected_hypothesis") or {}
    expected = {
        "alpha": 300.0,
        "cap_cp": 100.0,
        "mode": "strict_both_change",
        "threshold_cp": 10.0,
    }
    for key, value in expected.items():
        if selected.get(key) != value:
            raise ValueError(f"frozen hypothesis drift: {key}")
    protocol = report.get("protocol", {})
    mining = protocol.get("fresh_pair_mining", {})
    confirm = protocol.get("fresh_confirmation", {})
    if (
        int(mining.get("pair_count_exact", -1)) != FRESH_PAIRS
        or int(mining.get("seed", -1)) != power.MINING_SEED
        or mining.get("stop_rule") != "first_300_valid_pairs_in_frozen_pre_target_order"
        or int(confirm.get("bootstrap_samples", -1)) != power.BOOTSTRAP_SAMPLES
        or int(confirm.get("sham_replicates", -1)) != power.SHAM_REPLICATES
    ):
        raise ValueError("fresh confirmation frozen protocol drift")
    return selected


def _profile_rows(shards: list[dict[str, Any]], selection: dict[str, Any]) -> dict[int, dict[str, Any]]:
    if len(shards) != NSHARDS or {int(row.get("shard", -1)) for row in shards} != set(range(NSHARDS)):
        raise ValueError("fresh profile shards incomplete")
    selection_digest = _digest(selection)
    if any(
        row.get("schema") != atlas.SCHEMA_PROFILE_SHARD
        or row.get("selection_sha256") != selection_digest
        or int(row.get("max_rows", -1)) != 0
        for row in shards
    ):
        raise ValueError("fresh profile shard identity/execution drift")
    rows = [item for shard in shards for item in shard.get("rows", [])]
    rows.sort(key=lambda row: int(row["profile_ordinal"]))
    if [int(row["profile_ordinal"]) for row in rows] != list(range(len(selection["rows"]))):
        raise ValueError("fresh profile shard coverage drift")
    if availability._forbidden(rows):
        raise ValueError("fresh target-free profiles contain exact action targets")
    return {int(row["source"]["ordinal"]): row for row in rows}


def prepare(
    preregistration: dict[str, Any],
    availability_report: dict[str, Any],
    lattice: dict[str, Any],
    source_selection: dict[str, Any],
    profile_selection: dict[str, Any],
    profile_shards: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    _check_preregistration(preregistration)
    if (
        availability_report.get("schema") != "jass.l3_curriculum_error_fresh_pair_availability_terminal.v1"
        or availability_report.get("verdict") != availability.READY
        or availability_report.get("passed") is not True
        or availability_report.get("fresh_target_reconstruction_authorized") is not True
    ):
        raise ValueError("fresh confirmation requires passed 1515 availability")
    if (
        lattice.get("schema") != "jass.l3_curriculum_error_fresh_pair_lattice.v1"
        or int(lattice.get("mining_seed", -1)) != power.MINING_SEED
        or lattice.get("candidate_order_fixed_before_targets") is not True
        or int(lattice.get("exact_action_value_reads", -1)) != 0
    ):
        raise ValueError("fresh lattice identity/target-free drift")
    if source_selection.get("schema") != learning.SCHEMA_SELECTION:
        raise ValueError("fresh source selection schema drift")
    if profile_selection.get("schema") != atlas.SCHEMA_SELECTION:
        raise ValueError("fresh profile selection schema drift")
    by_ordinal = _profile_rows(profile_shards, profile_selection)
    candidate_states = list(lattice.get("candidate_states", []))
    if len(candidate_states) < 2 * FRESH_PAIRS:
        raise ValueError("fresh lattice has fewer than 600 candidate states")
    state_pool = {
        str(row["exact_state_key"]): str(row["source_pool"])
        for row in candidate_states
    }
    edges = list(lattice.get("candidate_edges", []))
    expected_edges = sorted(
        edges,
        key=lambda row: (
            bytes.fromhex(str(row["candidate_edge_order_sha256"])),
            str(row["left_exact_state_key"]),
            str(row["right_exact_state_key"]),
        ),
    )
    if edges != expected_edges:
        raise ValueError("fresh lattice edge order is not the frozen canonical order")
    for edge in edges:
        left, right, pool = (
            str(edge["left_exact_state_key"]),
            str(edge["right_exact_state_key"]),
            str(edge["source_pool"]),
        )
        if left == right or state_pool.get(left) != pool or state_pool.get(right) != pool:
            raise ValueError("fresh lattice edge endpoint/pool drift")
    ordinals = [int(row["ordinal"]) for row in candidate_states]
    if len(ordinals) != len(set(ordinals)) or any(value not in by_ordinal for value in ordinals):
        raise ValueError("fresh lattice candidate/profile coverage drift")

    source_rows = {int(row["ordinal"]): row for row in source_selection.get("rows", [])}
    source_manifests = list(source_selection.get("sources", []))
    source_manifest = {
        learning._source_relative_key(str(row["path"])): row
        for row in source_manifests
    }
    if len(source_manifest) != len(source_manifests):
        raise ValueError("fresh source manifest contains duplicate stable game paths")
    required_sources: dict[str, dict[str, Any]] = {}
    rows = []
    for new_ordinal, old_ordinal in enumerate(ordinals):
        original = source_rows.get(old_ordinal)
        if original is None:
            raise ValueError(f"candidate references unknown source ordinal {old_ordinal}")
        profile = by_ordinal[old_ordinal]
        if str(original["exact_state_key"]) != str(profile["source"]["exact_state_key"]):
            raise ValueError("candidate source/profile exact-state drift")
        relative = learning._source_relative_key(str(original["source_file"]))
        manifest = source_manifest.get(relative)
        if manifest is None:
            raise ValueError(f"candidate game absent from source manifest: {relative}")
        required_sources[relative] = manifest
        rows.append({**original, "source_ordinal": old_ordinal, "ordinal": new_ordinal})
    paths = [f"artefacts/{name}" for name in sorted(required_sources)]
    prepared = {
        "schema": SCHEMA_PREPARED,
        "preregistration_sha256": _digest(preregistration),
        "availability_sha256": _digest(availability_report),
        "lattice_sha256": _digest(lattice),
        "source_selection_sha256": _digest(source_selection),
        "profile_selection_sha256": _digest(profile_selection),
        "profile_shard_sha256": sorted(_digest(row) for row in profile_shards),
        "candidate_states": len(rows),
        "candidate_games": len(required_sources),
        "transition_selection": {
            "schema": learning.SCHEMA_SELECTION,
            "sources": [required_sources[name] for name in sorted(required_sources)],
            "games": len(required_sources),
            "decisions": len(rows),
            "rows": rows,
        },
        "remote_game_paths": paths,
        "target_free": True,
        "exact_action_value_reads": 0,
        "fits": 0,
    }
    return prepared, paths


def normalize(
    prepared: dict[str, Any],
    lattice: dict[str, Any],
    profile_selection: dict[str, Any],
    profile_shards: list[dict[str, Any]],
    game_dirs: list[Path],
    jass: str,
) -> dict[str, Any]:
    if prepared.get("schema") != SCHEMA_PREPARED or prepared.get("target_free") is not True:
        raise ValueError("fresh prepared selection drift")
    if prepared.get("lattice_sha256") != _digest(lattice):
        raise ValueError("fresh prepared/lattice identity drift")
    transition_selection = prepared["transition_selection"]
    sidecar = learning.build_transition_sidecar(transition_selection, game_dirs)
    rows = list(transition_selection["rows"])
    transitions = list(sidecar["transitions"])
    legal = learning._dump_legal_lines(jass, [str(row["fen"]) for row in rows])
    cv = learning._cv_module()
    referee = cv.Referee(jass)
    actual_by_source: dict[int, str] = {}
    disambiguated = 0
    try:
        for row, transition, legal_line in zip(rows, transitions, legal, strict=True):
            move, needed = learning._resolve_historical_transition(
                str(row["actual_move"]), legal_line, cv,
                fen=str(row["fen"]), next_fen=str(transition["next_fen"]),
                referee=referee,
            )
            actual_by_source[int(row["source_ordinal"])] = move.jass_apply_str()
            disambiguated += int(needed)
    finally:
        referee.close()
    by_ordinal = _profile_rows(profile_shards, profile_selection)
    catalog: dict[str, dict[str, Any]] = {}
    for candidate in lattice["candidate_states"]:
        ordinal = int(candidate["ordinal"])
        profile = json.loads(json.dumps(by_ordinal[ordinal]))
        source = profile["source"]
        if str(source["exact_state_key"]) != str(candidate["exact_state_key"]):
            raise ValueError("fresh candidate/profile state drift during normalization")
        source["actual_apply"] = actual_by_source[ordinal]
        key = str(source["exact_state_key"])
        if key in catalog:
            raise ValueError("fresh normalized exact state is not unique")
        catalog[key] = profile
    return {
        "schema": SCHEMA_CATALOG,
        "prepared_sha256": _digest(prepared),
        "lattice_sha256": _digest(lattice),
        "states": len(catalog),
        "historical_moves_normalized": len(actual_by_source),
        "successor_state_disambiguations": disambiguated,
        "resolution_method": learning.RESOLUTION_METHOD,
        "catalog": catalog,
        "exact_action_value_reads": 0,
        "fits": 0,
    }


def _empty_cache(catalog: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA_CACHE,
        "catalog_sha256": _digest(catalog),
        "identities": None,
        "judgments": {},
        "batch_receipts": [],
    }


def _accepted(
    lattice: dict[str, Any], judgments: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], set[str], list[str]]:
    accepted: list[dict[str, Any]] = []
    used: set[str] = set()
    unresolved: list[str] = []
    # Never commit a later edge while an earlier eligible edge is still
    # unlabelled: that would make the selected set depend on batch size.
    blocked_by_unknown_prefix = False
    for edge_index, edge in enumerate(lattice["candidate_edges"]):
        left = str(edge["left_exact_state_key"])
        right = str(edge["right_exact_state_key"])
        if left in used or right in used:
            continue
        missing = [key for key in (left, right) if key not in judgments]
        if missing:
            blocked_by_unknown_prefix = True
            unresolved.extend(missing)
            continue
        if blocked_by_unknown_prefix:
            continue
        lrow, rrow = judgments[left], judgments[right]
        lbad = str(lrow["exact_teacher_action"]) != str(lrow["historical_action"])
        rbad = str(rrow["exact_teacher_action"]) != str(rrow["historical_action"])
        if lbad == rbad:
            continue
        error, control = (left, right) if lbad else (right, left)
        accepted.append({
            "edge_index": edge_index,
            "source_pool": edge["source_pool"],
            "distance": edge["distance"],
            "error_exact_state_key": error,
            "control_exact_state_key": control,
        })
        used.update((left, right))
        if len(accepted) == FRESH_PAIRS:
            break
    return accepted, used, unresolved


def plan_batch(
    lattice: dict[str, Any], catalog: dict[str, Any], cache: dict[str, Any] | None,
    *, max_states: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if catalog.get("schema") != SCHEMA_CATALOG or catalog.get("lattice_sha256") != _digest(lattice):
        raise ValueError("fresh catalog/lattice identity drift")
    if cache is None:
        cache = _empty_cache(catalog)
    if cache.get("schema") != SCHEMA_CACHE or cache.get("catalog_sha256") != _digest(catalog):
        raise ValueError("fresh target cache identity drift")
    judgments = cache["judgments"]
    accepted, _used, unresolved = _accepted(lattice, judgments)
    if len(accepted) == FRESH_PAIRS:
        return {
            "schema": SCHEMA_PLAN,
            "status": "complete",
            "accepted_pairs": accepted,
            "judged_states": len(judgments),
            "target_states_requested": 0,
        }, None
    requested = []
    seen = set(judgments)
    for key in unresolved:
        if key in seen:
            continue
        if key not in catalog["catalog"]:
            raise ValueError(f"lattice references state absent from catalog: {key}")
        requested.append(key)
        seen.add(key)
        if len(requested) >= max_states:
            break
    if len(requested) % 2:
        for key in catalog["catalog"]:
            if key not in seen:
                requested.append(key)
                break
    if not requested:
        raise ValueError(
            f"fresh exact labels exhaust lattice at {len(accepted)}/{FRESH_PAIRS} pairs"
        )
    if len(requested) % 2:
        raise ValueError("fresh exact target planner ended with an unpairable state")
    pairs = []
    for index in range(0, len(requested), 2):
        left, right = requested[index:index + 2]
        pairs.append({
            "pair_id": len(pairs), "split": "fresh_target_batch", "distance": 0,
            "error": catalog["catalog"][left], "control": catalog["catalog"][right],
        })
    batch = {
        "schema": atlas.SCHEMA_PAIRS,
        "matching_passed": True,
        "matched_pairs": len(pairs),
        "pairs_by_split": {"fresh_target_batch": len(pairs)},
        "pairs": pairs,
        "subset": "fresh_exact_target_batch",
        "target_state_keys": requested,
    }
    return {
        "schema": SCHEMA_PLAN,
        "status": "needs_targets",
        "accepted_pairs_so_far": len(accepted),
        "judged_states": len(judgments),
        "target_states_requested": len(requested),
        "target_state_keys_sha256": _digest(requested),
    }, batch


def ingest(
    cache: dict[str, Any], catalog: dict[str, Any], batch: dict[str, Any],
    shards: list[dict[str, Any]],
) -> dict[str, Any]:
    if cache.get("schema") != SCHEMA_CACHE or cache.get("catalog_sha256") != _digest(catalog):
        raise ValueError("fresh ingest cache identity drift")
    if len(shards) != NSHARDS or {int(row.get("shard", -1)) for row in shards} != set(range(NSHARDS)):
        raise ValueError("fresh exact batch shards incomplete")
    batch_digest = _digest(batch)
    if any(
        row.get("schema") != atlas.SCHEMA_ATLAS_SHARD
        or row.get("pairs_sha256") != batch_digest
        or int(row.get("nshards", -1)) != NSHARDS
        or int(row.get("max_pairs", -1)) != 0
        or int(row.get("judge_depth", -1)) != JUDGE_DEPTH
        for row in shards
    ):
        raise ValueError("fresh exact batch shard identity/execution drift")
    identity_keys = ("champion_sha256", "jass_sha256", "search_params_sha256")
    identities = {
        key: next(iter({str(row.get(key, "")) for row in shards}))
        for key in identity_keys
    }
    if any(len({str(row.get(key, "")) for row in shards}) != 1 or not identities[key] for key in identity_keys):
        raise ValueError("fresh exact batch engine identity drift")
    search_arms = shards[0].get("search_arms")
    if any(row.get("search_arms") != search_arms for row in shards):
        raise ValueError("fresh exact batch search-arm drift")
    identity = {**identities, "search_arms": search_arms, "judge_depth": JUDGE_DEPTH}
    if cache["identities"] is not None and cache["identities"] != identity:
        raise ValueError("fresh exact target identity changed between batches")
    judged = dict(cache["judgments"])
    expected = set(batch["target_state_keys"])
    observed = set()
    for shard in shards:
        for pair in shard.get("rows", []):
            for role in ("error", "control"):
                row = pair[role]
                key = str(row["source"]["exact_state_key"])
                if key in judged or key in observed:
                    raise ValueError(f"fresh exact target state repeated: {key}")
                if key not in expected:
                    raise ValueError(f"fresh exact target state not requested: {key}")
                if str(row["historical_action"]) != str(catalog["catalog"][key]["source"]["actual_apply"]):
                    raise ValueError("fresh exact target historical-action drift")
                observed.add(key)
                judged[key] = row
    if observed != expected:
        raise ValueError("fresh exact target batch coverage drift")
    return {
        **cache,
        "identities": identity,
        "judgments": judged,
        "batch_receipts": [
            *cache["batch_receipts"],
            {"pairs_sha256": batch_digest, "states": len(observed),
             "shard_sha256": sorted(_digest(row) for row in shards)},
        ],
    }


def finalize_pairs_and_shards(
    lattice: dict[str, Any], catalog: dict[str, Any], cache: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    accepted, _used, _unresolved = _accepted(lattice, cache["judgments"])
    if len(accepted) != FRESH_PAIRS:
        raise ValueError(f"fresh exact target cache has {len(accepted)}/{FRESH_PAIRS} pairs")
    pairs = []
    for pair_id, row in enumerate(accepted):
        pairs.append({
            "pair_id": pair_id,
            "split": "fresh_confirmation",
            "distance": row["distance"],
            "source_pool": row["source_pool"],
            "edge_index": row["edge_index"],
            "error": catalog["catalog"][row["error_exact_state_key"]],
            "control": catalog["catalog"][row["control_exact_state_key"]],
        })
    error_openings = {
        str(row["error"]["source"]["opening_id"]) for row in pairs
    }
    control_openings = {
        str(row["control"]["source"]["opening_id"]) for row in pairs
    }
    game_counts = Counter(
        str(row[role]["source"]["game_uid"])
        for row in pairs
        for role in ("error", "control")
    )
    pair_payload = {
        "schema": atlas.SCHEMA_PAIRS,
        "matching_passed": True,
        "matched_pairs": FRESH_PAIRS,
        "pairs_by_split": {"fresh_confirmation": FRESH_PAIRS},
        "pairs_by_pool": dict(sorted(Counter(row["source_pool"] for row in pairs).items())),
        "pairs": pairs,
        "subset": "fresh_confirmation",
        "candidate_order_fixed_before_targets": True,
        "stop_rule": "first_300_valid_pairs_in_frozen_pre_target_order",
        "label_based_ranking": False,
        "error_openings": len(error_openings),
        "control_openings": len(control_openings),
        "error_control_opening_overlap": len(error_openings & control_openings),
        "maximum_states_per_source_game": max(game_counts.values(), default=0),
        "fit_count": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    pairs_digest = _digest(pair_payload)
    identity = cache.get("identities") or {}
    shards = []
    for shard_id in range(NSHARDS):
        rows = []
        for pair in pairs:
            if int(pair["pair_id"]) % NSHARDS != shard_id:
                continue
            rows.append({
                "pair_id": pair["pair_id"],
                "split": pair["split"],
                "error": cache["judgments"][str(pair["error"]["source"]["exact_state_key"])],
                "control": cache["judgments"][str(pair["control"]["source"]["exact_state_key"])],
            })
        shards.append({
            "schema": atlas.SCHEMA_ATLAS_SHARD,
            "pairs_sha256": pairs_digest,
            "champion_sha256": identity.get("champion_sha256"),
            "jass_sha256": identity.get("jass_sha256"),
            "search_params_sha256": identity.get("search_params_sha256"),
            "search_arms": identity.get("search_arms"),
            "shard": shard_id,
            "nshards": NSHARDS,
            "max_pairs": 0,
            "judge_depth": JUDGE_DEPTH,
            "rows": rows,
            "repacked_from_authenticated_batches": True,
            "batch_receipts_sha256": _digest(cache["batch_receipts"]),
        })
    return pair_payload, shards


def _load_fresh_rows(
    pairs: dict[str, Any], shards: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if (
        pairs.get("schema") != atlas.SCHEMA_PAIRS
        or pairs.get("subset") != "fresh_confirmation"
        or pairs.get("matching_passed") is not True
        or int(pairs.get("matched_pairs", -1)) != FRESH_PAIRS
    ):
        raise ValueError("fresh confirmation pair source drift")
    if len(shards) != NSHARDS or {int(row.get("shard", -1)) for row in shards} != set(range(NSHARDS)):
        raise ValueError("fresh confirmation atlas incomplete")
    digest = _digest(pairs)
    if any(
        row.get("schema") != atlas.SCHEMA_ATLAS_SHARD
        or row.get("pairs_sha256") != digest
        or int(row.get("max_pairs", -1)) != 0
        for row in shards
    ):
        raise ValueError("fresh confirmation atlas identity drift")
    identities = {}
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        values = {str(row.get(key, "")) for row in shards}
        if len(values) != 1 or not next(iter(values)):
            raise ValueError(f"fresh confirmation {key} drift")
        identities[key] = next(iter(values))
    profiles = {int(row["pair_id"]): row for row in pairs["pairs"]}
    judged = {int(row["pair_id"]): row for shard in shards for row in shard["rows"]}
    if set(profiles) != set(range(FRESH_PAIRS)) or set(judged) != set(profiles):
        raise ValueError("fresh confirmation pair coverage drift")
    ordered_profiles = [profiles[index] for index in range(FRESH_PAIRS)]
    if [int(row["edge_index"]) for row in ordered_profiles] != sorted(
        int(row["edge_index"]) for row in ordered_profiles
    ):
        raise ValueError("fresh confirmation did not preserve frozen edge order")
    states = [
        str(row[role]["source"]["exact_state_key"])
        for row in ordered_profiles
        for role in ("error", "control")
    ]
    if len(states) != len(set(states)):
        raise ValueError("fresh confirmation reuses a canonical state")
    game_counts = Counter(
        str(row[role]["source"]["game_uid"])
        for row in ordered_profiles
        for role in ("error", "control")
    )
    if max(game_counts.values(), default=0) > 2:
        raise ValueError("fresh confirmation exceeds two states per source game")
    rows = []
    for pair_id in range(FRESH_PAIRS):
        row = {"pair_id": pair_id, "source_pool": profiles[pair_id]["source_pool"]}
        for role in ("error", "control"):
            profile = profiles[pair_id][role]
            exact = judged[pair_id][role]
            features, original_scores, image_scores = training._paired_features(profile)
            values = ranker._true_values(exact)
            if set(features) != set(values):
                raise ValueError("fresh feature/judge action set drift")
            disagree = str(exact["exact_teacher_action"]) != str(exact["historical_action"])
            if disagree != (role == "error"):
                raise ValueError("fresh pair exact label drift")
            row[role] = {
                "profile": profile, "features": features,
                "original_scores": original_scores, "image_scores": image_scores,
                "values": values,
            }
        rows.append(row)
    return rows, identities


def _confirmation_metrics(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [float(row["error"]["improvement_cp"]) for row in decisions]
    controls = [float(row["control"]["improvement_cp"]) for row in decisions]
    paired = [left - right for left, right in zip(errors, controls, strict=True)]
    changed = [row["error"] for row in decisions if row["error"]["intervention"]]
    symmetry = lambda role, key: float(np.mean([bool(row[role][key]) for row in decisions]))
    return {
        "error_improvement": atlas._bootstrap(errors, samples=power.BOOTSTRAP_SAMPLES, seed=power.BOOTSTRAP_SEED),
        "control_improvement": atlas._bootstrap(controls, samples=power.BOOTSTRAP_SAMPLES, seed=power.BOOTSTRAP_SEED + 1),
        "paired_error_minus_control": atlas._bootstrap(paired, samples=power.BOOTSTRAP_SAMPLES, seed=power.BOOTSTRAP_SEED + 2),
        "error_interventions": sum(bool(row["error"]["intervention"]) for row in decisions),
        "control_interventions": sum(bool(row["control"]["intervention"]) for row in decisions),
        "error_positive_realization_rate": float(np.mean([float(row["realized_gain_cp"]) > 0.0 for row in changed])) if changed else None,
        "error_anchor_symmetry_rate": symmetry("error", "anchor_symmetry"),
        "error_aligned_symmetry_rate": symmetry("error", "aligned_symmetry"),
        "control_anchor_symmetry_rate": symmetry("control", "anchor_symmetry"),
        "control_aligned_symmetry_rate": symmetry("control", "aligned_symmetry"),
        "outside_gate_bit_identical": all(row[role]["outside_gate_bit_identical"] for row in decisions for role in ("error", "control")),
        "paired_values_cp": paired,
    }


def confirm(
    preregistration: dict[str, Any], training_report: dict[str, Any], failed_model: dict[str, Any],
    training_pairs: dict[str, Any], training_shards: list[dict[str, Any]],
    fresh_pairs: dict[str, Any], fresh_shards: list[dict[str, Any]],
    target_cache: dict[str, Any],
) -> dict[str, Any]:
    selected = _check_preregistration(preregistration)
    ridge._check_source(training_report, failed_model)
    training_rows, training_identities = training._load_rows(training_pairs, training_shards)
    fresh_rows, fresh_identities = _load_fresh_rows(fresh_pairs, fresh_shards)
    for key, value in training_identities.items():
        if training_report.get(key) != value or failed_model.get(key) != value:
            raise ValueError(f"immutable 1508 source {key} drift")
    if training_identities != fresh_identities:
        raise ValueError("fresh confirmation engine/model/profile identity differs from 1508")
    if (
        target_cache.get("schema") != SCHEMA_CACHE
        or target_cache.get("identities") != {
            **fresh_identities,
            "search_arms": fresh_shards[0].get("search_arms"),
            "judge_depth": JUDGE_DEPTH,
        }
    ):
        raise ValueError("fresh confirmation target-cache identity drift")
    alpha, cap = float(selected["alpha"]), float(selected["cap_cp"])
    threshold, mode = float(selected["threshold_cp"]), str(selected["mode"])
    real_model = ridge._fit(training_rows, alpha=alpha)
    decisions = ridge._decisions(
        fresh_rows, {row["pair_id"]: real_model for row in fresh_rows},
        cap_cp=cap, threshold_cp=threshold, mode=mode,
    )
    metrics = _confirmation_metrics(decisions)
    real_mean = float(metrics["paired_error_minus_control"]["mean"])
    sham_means = []
    for replicate in range(power.SHAM_REPLICATES):
        model = ridge._fit(training_rows, alpha=alpha, sham_seed=power.SHAM_SEED + replicate)
        sham_decisions = ridge._decisions(
            fresh_rows, {row["pair_id"]: model for row in fresh_rows},
            cap_cp=cap, threshold_cp=threshold, mode=mode,
        )
        sham_means.append(float(np.mean([
            row["error"]["improvement_cp"] - row["control"]["improvement_cp"]
            for row in sham_decisions
        ])))
    sham_q99 = float(np.quantile(np.asarray(sham_means), 0.99))
    symmetry_drop = metrics["error_anchor_symmetry_rate"] - metrics["error_aligned_symmetry_rate"]
    gates = {
        "fresh_pairs_exactly_300": len(fresh_rows) == FRESH_PAIRS,
        "error_interventions_at_least_30": metrics["error_interventions"] >= power.MIN_ERROR_INTERVENTIONS,
        "control_interventions_at_least_20": metrics["control_interventions"] >= power.MIN_CONTROL_INTERVENTIONS,
        "total_interventions_at_least_50": metrics["error_interventions"] + metrics["control_interventions"] >= power.MIN_TOTAL_INTERVENTIONS,
        "error_ci95_lower_gt_0cp": float(metrics["error_improvement"]["ci95"][0]) > 0.0,
        "paired_ci95_lower_gt_0cp": float(metrics["paired_error_minus_control"]["ci95"][0]) > 0.0,
        "control_mean_gain_at_least_minus_2cp": float(metrics["control_improvement"]["mean"]) >= -2.0,
        "error_positive_realization_rate_at_least_0_60": metrics["error_positive_realization_rate"] is not None and metrics["error_positive_realization_rate"] >= 0.60,
        "error_aligned_symmetry_at_least_0_70": metrics["error_aligned_symmetry_rate"] >= 0.70,
        "error_symmetry_drop_at_most_0_02": symmetry_drop <= 0.02,
        "real_paired_mean_exceeds_1000_sham_q99": real_mean > sham_q99,
        "outside_gate_bit_identical": metrics["outside_gate_bit_identical"],
        "fresh_labels_not_used_for_fit": True,
    }
    passed = all(gates.values())
    confirmation_target_states = [
        row[role]
        for shard in fresh_shards
        for row in shard["rows"]
        for role in ("error", "control")
    ]
    all_target_states = list(target_cache.get("judgments", {}).values())
    selected_state_keys = {
        str(row["source"]["exact_state_key"])
        for row in confirmation_target_states
    }
    if not selected_state_keys <= set(target_cache.get("judgments", {})):
        raise ValueError("fresh confirmation targets are absent from target cache")
    action_reads = sum(2 * len(row["action_values"]) for row in all_target_states)
    compact_metrics = {key: value for key, value in metrics.items() if key != "paired_values_cp"}
    return {
        "schema": SCHEMA_REPORT,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        "selected_hypothesis": selected,
        "training_population": "immutable_1508_gate_fit_pairs_only",
        "fresh_extension_labels_used_for_fit": False,
        "fresh_pairs": FRESH_PAIRS,
        "fresh_pairs_by_pool": fresh_pairs["pairs_by_pool"],
        "metrics": compact_metrics,
        "symmetry_drop": symmetry_drop,
        "sham": {
            "replicates": power.SHAM_REPLICATES,
            "seed_start": power.SHAM_SEED,
            "paired_mean_q99_cp": sham_q99,
            "real_paired_mean_cp": real_mean,
            "real_exceeds_sham_q99": real_mean > sham_q99,
            "means_sha256": _digest(sham_means),
        },
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "identities": fresh_identities,
        "new_target_states": len(all_target_states),
        "fresh_confirmation_target_states": len(confirmation_target_states),
        "discarded_labelled_states": len(all_target_states) - len(confirmation_target_states),
        "target_cache_sha256": _digest(target_cache),
        "exact_target_batches": len(target_cache.get("batch_receipts", [])),
        "exact_action_value_reads": action_reads,
        "residual_fits": 1 + power.SHAM_REPLICATES,
        "diagnostic_fits": power.SHAM_REPLICATES,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "production_rule_authorized": passed,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "separate_immutable_production_refit_and_sealed_feature_audit_preregistration" if passed else None,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    for name in ("preregistration", "availability", "lattice", "source-selection", "profile-selection"):
        prep.add_argument(f"--{name}", type=Path, required=True)
    prep.add_argument("--profile-shard", type=Path, action="append", required=True)
    prep.add_argument("--prepared", type=Path, required=True)
    prep.add_argument("--paths", type=Path, required=True)
    norm = sub.add_parser("normalize")
    for name in ("prepared", "lattice", "profile-selection"):
        norm.add_argument(f"--{name}", type=Path, required=True)
    norm.add_argument("--profile-shard", type=Path, action="append", required=True)
    norm.add_argument("--games-dir", type=Path, action="append", required=True)
    norm.add_argument("--jass", required=True)
    norm.add_argument("--catalog", type=Path, required=True)
    plan = sub.add_parser("plan")
    for name in ("lattice", "catalog"):
        plan.add_argument(f"--{name}", type=Path, required=True)
    plan.add_argument("--cache", type=Path)
    plan.add_argument("--cache-output", type=Path)
    plan.add_argument("--max-states", type=int, default=256)
    plan.add_argument("--plan", type=Path, required=True)
    plan.add_argument("--batch", type=Path)
    ingest_parser = sub.add_parser("ingest")
    for name in ("cache", "catalog", "batch"):
        ingest_parser.add_argument(f"--{name}", type=Path, required=True)
    ingest_parser.add_argument("--atlas-shard", type=Path, action="append", required=True)
    ingest_parser.add_argument("--output", type=Path, required=True)
    final = sub.add_parser("finalize")
    for name in ("lattice", "catalog", "cache"):
        final.add_argument(f"--{name}", type=Path, required=True)
    final.add_argument("--pairs", type=Path, required=True)
    final.add_argument("--shards-dir", type=Path, required=True)
    check = sub.add_parser("confirm")
    for name in ("preregistration", "training-report", "failed-model", "training-pairs", "fresh-pairs", "target-cache"):
        check.add_argument(f"--{name}", type=Path, required=True)
    check.add_argument("--training-shard", type=Path, action="append", required=True)
    check.add_argument("--fresh-shard", type=Path, action="append", required=True)
    check.add_argument("--report", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    if args.command == "prepare":
        payload, paths = prepare(
            load(args.preregistration), load(args.availability), load(args.lattice),
            load(args.source_selection), load(args.profile_selection), _load_many(args.profile_shard),
        )
        _publish(args.prepared, payload)
        args.paths.parent.mkdir(parents=True, exist_ok=True)
        args.paths.write_text("".join(f"{value}\n" for value in paths), encoding="utf-8")
    elif args.command == "normalize":
        _publish(args.catalog, normalize(
            load(args.prepared), load(args.lattice), load(args.profile_selection),
            _load_many(args.profile_shard), args.games_dir, args.jass,
        ))
    elif args.command == "plan":
        catalog = load(args.catalog)
        cache = load(args.cache) if args.cache else _empty_cache(catalog)
        if args.cache is None:
            if args.cache_output is None:
                raise ValueError("--cache-output is required for the first target batch")
            _publish(args.cache_output, cache)
        plan, batch = plan_batch(load(args.lattice), catalog, cache, max_states=args.max_states)
        _publish(args.plan, plan)
        if batch is not None:
            if args.batch is None:
                raise ValueError("--batch is required while exact targets remain")
            _publish(args.batch, batch)
    elif args.command == "ingest":
        _publish(args.output, ingest(
            load(args.cache), load(args.catalog), load(args.batch), _load_many(args.atlas_shard)
        ))
    elif args.command == "finalize":
        pairs, shards = finalize_pairs_and_shards(load(args.lattice), load(args.catalog), load(args.cache))
        _publish(args.pairs, pairs)
        args.shards_dir.mkdir(parents=True, exist_ok=True)
        for shard in shards:
            _publish(args.shards_dir / f"shard-{shard['shard']}.json", shard)
    elif args.command == "confirm":
        _publish(args.report, confirm(
            load(args.preregistration), load(args.training_report), load(args.failed_model),
            load(args.training_pairs), _load_many(args.training_shard),
            load(args.fresh_pairs), _load_many(args.fresh_shard), load(args.target_cache),
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
