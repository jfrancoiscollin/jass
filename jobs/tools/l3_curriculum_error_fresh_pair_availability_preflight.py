#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Target-free availability screen for the frozen 300-pair confirmation.

The fresh campaign is allowed to expose game outcomes and root-search traces,
but never a deeper action judgement.  Candidate order, canonical uniqueness,
the two-states-per-game cap and the matching lattice are all sealed before the
first exact action target can be reconstructed by a later job.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

from jobs.tools import l3_curriculum_error_learning as learning
from jobs.tools import l3_curriculum_error_residual_power_extension_preregistration as power
from jobs.tools import l3_curriculum_error_trace_proxy_preregistration as proxy
from jobs.tools import l3_curriculum_error_trace_variability_screen as trace
from jobs.tools import l3_curriculum_search_error_atlas as profiles


# Reuse the production profile-selection envelope so the existing root-trace
# dumper can consume this deliberately different, role-tagged risk set.
SCHEMA_SELECTION = profiles.SCHEMA_SELECTION
SCHEMA_REPORT = "jass.l3_curriculum_error_fresh_pair_availability_preflight.v1"
SCHEMA_TERMINAL = "jass.curriculum_error_fresh_pair_availability_terminal.v1"
READY = "JASS_CURRICULUM_ERROR_FRESH_PAIR_AVAILABILITY_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_FRESH_PAIR_AVAILABILITY_NOT_ESTABLISHED"
SOURCE_GAMES = 7680
PREPROFILE_STATES_PER_GAME = 6
MAX_STATES_PER_GAME = 2
MIN_ELIGIBLE_STATES = 1800
MIN_ELIGIBLE_GAMES = 900
MIN_ELIGIBLE_OPENINGS = 900
MIN_RAW_PAIR_CAPACITY = 900
MIN_RAW_PAIR_CAPACITY_PER_POOL = 360
MAX_EXACT_TARGET_MINUTES = 360.0
MAX_NEIGHBOURS_PER_STATE = 24
FORBIDDEN_TARGET_KEYS = {
    "action_values",
    "exact_teacher_action",
    "judged",
    "child_original",
    "child_exact_image",
    "root_cp",
    "teacher",
    "regret_cp",
    "move_differs",
}


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _forbidden(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key) in FORBIDDEN_TARGET_KEYS:
                found.add(str(key))
            found.update(_forbidden(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(_forbidden(nested))
    return found


def _pool(source_file: str) -> str:
    normalized = source_file.replace("\\", "/")
    for name in ("games-pool1", "games-pool2"):
        if f"/{name}/" in f"/{normalized}":
            return name.removeprefix("games-")
    raise ValueError(f"cannot recover source pool from {source_file!r}")


def _order_key(row: dict[str, Any], *, seed: int, namespace: str) -> bytes:
    text = "|".join(
        (
            str(seed),
            namespace,
            str(row["exact_state_key"]),
            str(row["opening_id"]),
            str(row["game_uid"]),
            str(row["ordinal"]),
        )
    )
    return hashlib.sha256(text.encode()).digest()


def prepare_profile_selection(
    selection: dict[str, Any], *, seed: int = power.MINING_SEED
) -> dict[str, Any]:
    if selection.get("schema") != learning.SCHEMA_SELECTION:
        raise ValueError("fresh selection schema drift")
    if int(selection.get("external_teacher_inputs", -1)) != 0:
        raise ValueError("fresh selection contains external teacher inputs")
    if int(selection.get("fit_count", -1)) != 0:
        raise ValueError("fresh selection contains a fit")
    rows = list(selection.get("rows", []))
    if len(rows) != int(selection.get("decisions", -1)):
        raise ValueError("fresh selection decision count drift")
    if _forbidden(rows):
        raise ValueError("fresh selection contains exact action targets")

    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("outcome") == "loss":
            by_game[str(row["game_uid"])].append(row)
    provisional: list[dict[str, Any]] = []
    for game_uid in sorted(by_game):
        ranked = sorted(
            by_game[game_uid],
            key=lambda row: _order_key(row, seed=seed, namespace="preprofile"),
        )
        provisional.extend(ranked[:PREPROFILE_STATES_PER_GAME])

    # The same canonical state may occur in two independently generated games.
    # Which copy survives is fixed without consulting a trace or action label.
    owner: dict[str, dict[str, Any]] = {}
    for row in provisional:
        key = str(row["exact_state_key"])
        incumbent = owner.get(key)
        if incumbent is None or _order_key(
            row, seed=seed, namespace="canonical"
        ) < _order_key(incumbent, seed=seed, namespace="canonical"):
            owner[key] = row
    ordered = sorted(
        owner.values(), key=lambda row: _order_key(row, seed=seed, namespace="profile")
    )
    output_rows = []
    for index, row in enumerate(ordered):
        output_rows.append(
            {
                "role": "fresh_target_free_candidate",
                "profile_ordinal": index,
                "source_pool": _pool(str(row["source_file"])),
                "source": row,
            }
        )
    counts = {
        pool: sum(row["source_pool"] == pool for row in output_rows)
        for pool in ("pool1", "pool2")
    }
    return {
        "schema": SCHEMA_SELECTION,
        "source_selection_sha256": hashlib.sha256(_canonical(selection)).hexdigest(),
        "mining_seed": seed,
        "source_games": int(selection["games"]),
        "source_decisions": len(rows),
        "loss_games": len(by_game),
        "preprofile_states_per_game": PREPROFILE_STATES_PER_GAME,
        "preprofile_rows_before_canonical_dedup": len(provisional),
        "canonical_duplicates_removed": len(provisional) - len(ordered),
        "rows_by_pool": counts,
        "rows": output_rows,
        "target_free": True,
        "exact_action_value_reads": 0,
        "fits": 0,
    }


def _piece(source: dict[str, Any]) -> dict[str, Any]:
    return profiles._piece_features(str(source["fen"]))


def _candidate_row(profile: dict[str, Any], *, seed: int) -> dict[str, Any]:
    source = profile["source"]
    values = trace._profile_values(profile)
    score = float(values[proxy.SELECTED_PROXY])
    return {
        "ordinal": int(source["ordinal"]),
        "opening_id": str(source["opening_id"]),
        "game_uid": str(source["game_uid"]),
        "exact_state_key": str(source["exact_state_key"]),
        "outcome": str(source["outcome"]),
        "ply": int(source["ply"]),
        "actual_move": str(source["actual_move"]),
        "source_pool": str(profile["source_pool"]),
        "piece_features": _piece(source),
        "legal_moves": int(profile["legal_moves"]),
        "proxy_name": proxy.SELECTED_PROXY,
        "proxy_value_cp": score,
        "candidate_order_sha256": _order_key(
            source, seed=seed, namespace="postprofile"
        ).hex(),
    }


def _distance(left: dict[str, Any], right: dict[str, Any]) -> int | None:
    if left["source_pool"] != right["source_pool"]:
        return None
    if left["game_uid"] == right["game_uid"] or left["opening_id"] == right["opening_id"]:
        return None
    if left["outcome"] != right["outcome"]:
        return None
    lp, rp = left["piece_features"], right["piece_features"]
    if lp["phase"] != rp["phase"]:
        return None
    if ("x" in left["actual_move"]) != ("x" in right["actual_move"]):
        return None
    diffs = {
        "pieces": abs(int(lp["piece_count"]) - int(rp["piece_count"])),
        "kings": abs(int(lp["king_count"]) - int(rp["king_count"])),
        "balance": abs(
            int(lp["stm_material_balance"]) - int(rp["stm_material_balance"])
        ),
        "legal": abs(int(left["legal_moves"]) - int(right["legal_moves"])),
        "ply": abs(int(left["ply"]) - int(right["ply"])),
        "proxy": abs(float(left["proxy_value_cp"]) - float(right["proxy_value_cp"])),
    }
    if (
        diffs["pieces"] > 2
        or diffs["kings"] > 1
        or diffs["balance"] > 2
        or diffs["legal"] > 3
        or diffs["ply"] > 12
        or diffs["proxy"] > 50.0
    ):
        return None
    return int(
        12 * diffs["pieces"]
        + 10 * diffs["kings"]
        + 8 * diffs["balance"]
        + 7 * diffs["legal"]
        + diffs["ply"]
        + round(diffs["proxy"])
    )


def _lattice(
    candidates: list[dict[str, Any]], *, seed: int
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_pool = {
        pool: [row for row in candidates if row["source_pool"] == pool]
        for pool in ("pool1", "pool2")
    }
    edges: list[dict[str, Any]] = []
    capacities: dict[str, int] = {}
    for pool, rows in by_pool.items():
        left = [
            row
            for row in rows
            if int(row["candidate_order_sha256"][:16], 16) % 2 == 0
        ]
        right = [
            row
            for row in rows
            if int(row["candidate_order_sha256"][:16], 16) % 2 == 1
        ]
        adjacency: dict[str, list[tuple[int, bytes, dict[str, Any]]]] = {}
        for source in left:
            ranked = []
            for target in right:
                cost = _distance(source, target)
                if cost is None:
                    continue
                tie = hashlib.sha256(
                    f"{seed}|edge|{source['exact_state_key']}|{target['exact_state_key']}".encode()
                ).digest()
                ranked.append((cost, tie, target))
            ranked.sort(key=lambda item: (item[0], item[1]))
            adjacency[source["exact_state_key"]] = ranked[:MAX_NEIGHBOURS_PER_STATE]
            for cost, tie, target in adjacency[source["exact_state_key"]]:
                edges.append(
                    {
                        "source_pool": pool,
                        "left_exact_state_key": source["exact_state_key"],
                        "right_exact_state_key": target["exact_state_key"],
                        "distance": cost,
                        "candidate_edge_order_sha256": tie.hex(),
                    }
                )

        owner: dict[str, str] = {}
        match: dict[str, str] = {}

        def augment(state: str, visited: set[str]) -> bool:
            for _cost, _tie, target in adjacency.get(state, []):
                target_key = str(target["exact_state_key"])
                if target_key in visited:
                    continue
                visited.add(target_key)
                incumbent = owner.get(target_key)
                if incumbent is None or augment(incumbent, visited):
                    owner[target_key] = state
                    match[state] = target_key
                    return True
            return False

        left.sort(key=lambda row: bytes.fromhex(row["candidate_order_sha256"]))
        for row in left:
            augment(str(row["exact_state_key"]), set())
        capacities[pool] = len(match)
    edges.sort(
        key=lambda row: (
            bytes.fromhex(row["candidate_edge_order_sha256"]),
            row["left_exact_state_key"],
            row["right_exact_state_key"],
        )
    )
    return edges, capacities


def _validate_preregistration(report: dict[str, Any]) -> None:
    if (
        report.get("schema") != power.SCHEMA
        or report.get("verdict") != power.READY
        or report.get("passed") is not True
        or report.get("fresh_pair_mining_authorized") is not True
        or report.get("fresh_target_reconstruction_authorized") is not False
    ):
        raise ValueError("fresh availability requires the certified 1514 preregistration")
    mining = report.get("protocol", {}).get("fresh_pair_mining", {})
    if (
        int(mining.get("pair_count_exact", -1)) != power.FRESH_PAIRS
        or int(mining.get("seed", -1)) != power.MINING_SEED
        or int(mining.get("maximum_states_per_source_game", -1))
        != MAX_STATES_PER_GAME
        or mining.get("target_free_before_selection") is not True
    ):
        raise ValueError("frozen fresh-pair protocol drift")


def audit(
    preregistration: dict[str, Any],
    selection: dict[str, Any],
    shards: list[dict[str, Any]],
    profile_cost: dict[str, Any],
    historical_exact_cost: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    _validate_preregistration(preregistration)
    if selection.get("schema") != SCHEMA_SELECTION or selection.get("target_free") is not True:
        raise ValueError("profile selection drift")
    if int(selection.get("source_games", -1)) != SOURCE_GAMES:
        raise ValueError(f"fresh campaign must contain exactly {SOURCE_GAMES} games")
    if len(shards) != 16 or {int(row.get("shard", -1)) for row in shards} != set(range(16)):
        raise ValueError("profile shards incomplete")
    digest = hashlib.sha256(_canonical(selection)).hexdigest()
    if any(row.get("schema") != profiles.SCHEMA_PROFILE_SHARD for row in shards):
        raise ValueError("profile shard schema drift")
    if any(row.get("selection_sha256") != digest for row in shards):
        raise ValueError("profile selection identity drift")
    rows = [row for shard in shards for row in shard.get("rows", [])]
    rows.sort(key=lambda row: int(row["profile_ordinal"]))
    if [int(row["profile_ordinal"]) for row in rows] != list(range(len(selection["rows"]))):
        raise ValueError("profile rows do not exactly cover the selection")
    forbidden = _forbidden(rows)
    if forbidden:
        raise ValueError(f"profile payload contains exact targets: {sorted(forbidden)}")

    raw = [_candidate_row(row, seed=power.MINING_SEED) for row in rows]
    annulus = [
        row
        for row in raw
        if proxy.LOWER_OPEN < float(row["proxy_value_cp"]) <= proxy.UPPER_CLOSED
    ]
    annulus.sort(key=lambda row: bytes.fromhex(row["candidate_order_sha256"]))
    selected: list[dict[str, Any]] = []
    game_counts: dict[str, int] = defaultdict(int)
    state_seen: set[str] = set()
    for row in annulus:
        game = str(row["game_uid"])
        state = str(row["exact_state_key"])
        if state in state_seen or game_counts[game] >= MAX_STATES_PER_GAME:
            continue
        state_seen.add(state)
        game_counts[game] += 1
        selected.append(row)
    edges, capacities = _lattice(selected, seed=power.MINING_SEED)
    total_capacity = sum(capacities.values())

    if profile_cost.get("passed") is not True:
        raise ValueError("profile cost preflight did not pass")
    hist_total = int(historical_exact_cost.get("total_pairs", 0))
    hist_minutes = float(historical_exact_cost.get("projected_minutes", 0.0))
    if hist_total <= 0 or hist_minutes <= 0.0 or historical_exact_cost.get("passed") is not True:
        raise ValueError("historical exact-target cost certificate drift")
    projected_exact_minutes = hist_minutes * power.FRESH_PAIRS / hist_total
    games = {str(row["game_uid"]) for row in selected}
    openings = {str(row["opening_id"]) for row in selected}
    pool_counts = {
        pool: sum(row["source_pool"] == pool for row in selected)
        for pool in ("pool1", "pool2")
    }
    gates = {
        "source_games_exactly_7680": int(selection["source_games"]) == SOURCE_GAMES,
        "both_pools_profiled": all(int(selection["rows_by_pool"].get(pool, 0)) > 0 for pool in ("pool1", "pool2")),
        "eligible_states_at_least_1800": len(selected) >= MIN_ELIGIBLE_STATES,
        "eligible_games_at_least_900": len(games) >= MIN_ELIGIBLE_GAMES,
        "eligible_openings_at_least_900": len(openings) >= MIN_ELIGIBLE_OPENINGS,
        "raw_pair_capacity_at_least_900": total_capacity >= MIN_RAW_PAIR_CAPACITY,
        "pool1_capacity_at_least_360": capacities["pool1"] >= MIN_RAW_PAIR_CAPACITY_PER_POOL,
        "pool2_capacity_at_least_360": capacities["pool2"] >= MIN_RAW_PAIR_CAPACITY_PER_POOL,
        "canonical_states_unique": len(state_seen) == len(selected),
        "maximum_two_states_per_game": max(game_counts.values(), default=0) <= MAX_STATES_PER_GAME,
        "exact_target_cost_at_most_360_minutes": projected_exact_minutes <= MAX_EXACT_TARGET_MINUTES,
        "exact_action_targets_absent": not forbidden,
    }
    passed = all(gates.values())
    lattice = {
        "schema": "jass.l3_curriculum_error_fresh_pair_lattice.v1",
        "mining_seed": power.MINING_SEED,
        "candidate_order_fixed_before_targets": True,
        "candidate_states": selected,
        "candidate_edges": edges,
        "raw_pair_capacity_by_pool": capacities,
        "raw_pair_capacity": total_capacity,
        "maximum_states_per_source_game": MAX_STATES_PER_GAME,
        "exact_action_value_reads": 0,
    }
    report = {
        "schema": SCHEMA_REPORT,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        "fresh_pair_count_required": power.FRESH_PAIRS,
        "source_games": int(selection["source_games"]),
        "profiled_states": len(rows),
        "annulus_states_before_caps": len(annulus),
        "eligible_states": len(selected),
        "eligible_games": len(games),
        "eligible_openings": len(openings),
        "eligible_states_by_pool": pool_counts,
        "raw_pair_capacity": total_capacity,
        "raw_pair_capacity_by_pool": capacities,
        "candidate_edges": len(edges),
        "proxy": {
            "name": proxy.SELECTED_PROXY,
            "lower_open_cp": proxy.LOWER_OPEN,
            "upper_closed_cp": proxy.UPPER_CLOSED,
        },
        "profile_cost": profile_cost,
        "historical_exact_target_cost": historical_exact_cost,
        "projected_exact_target_minutes_for_300_pairs": projected_exact_minutes,
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "fresh_target_reconstruction_authorized": passed,
        "new_targets": 0,
        "exact_action_value_reads": 0,
        "holdout_reads": 0,
        "fits": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": SOURCE_GAMES,
        "frozen_reads": 0,
        "production_rule_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "fresh_exact_label_and_powered_confirmation" if passed else None,
    }
    return report, lattice


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--selection", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("audit")
    check.add_argument("--preregistration", type=Path, required=True)
    check.add_argument("--selection", type=Path, required=True)
    check.add_argument("--profile-shard", action="append", type=Path, required=True)
    check.add_argument("--profile-cost", type=Path, required=True)
    check.add_argument("--historical-exact-cost", type=Path, required=True)
    check.add_argument("--report", type=Path, required=True)
    check.add_argument("--lattice", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "prepare":
        output = prepare_profile_selection(json.loads(args.selection.read_text()))
        _publish(args.output, output)
        print(json.dumps({"profile_rows": len(output["rows"]), "loss_games": output["loss_games"]}, sort_keys=True))
        return 0
    report, lattice = audit(
        json.loads(args.preregistration.read_text()),
        json.loads(args.selection.read_text()),
        [json.loads(path.read_text()) for path in args.profile_shard],
        json.loads(args.profile_cost.read_text()),
        json.loads(args.historical_exact_cost.read_text()),
    )
    report["preregistration_sha256"] = _sha256(args.preregistration)
    report["selection_sha256"] = _sha256(args.selection)
    report["profile_shard_sha256"] = sorted(_sha256(path) for path in args.profile_shard)
    report["historical_exact_cost_sha256"] = _sha256(args.historical_exact_cost)
    _publish(args.report, report)
    _publish(args.lattice, lattice)
    print(json.dumps({"verdict": report["verdict"], "capacity": report["raw_pair_capacity"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
