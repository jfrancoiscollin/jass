#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Target-free availability screen for the preregistered endgame abstention test."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jobs.tools import l3_curriculum_error_endgame_abstention_preregistration as prereg
from jobs.tools import l3_curriculum_error_fresh_pair_availability_preflight as base


SCHEMA_REPORT = "jass.l3_curriculum_error_endgame_abstention_availability.v1"
SCHEMA_TERMINAL = "jass.curriculum_error_endgame_abstention_availability_terminal.v1"
READY = "JASS_CURRICULUM_ERROR_ENDGAME_ABSTENTION_AVAILABILITY_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_ENDGAME_ABSTENTION_AVAILABILITY_NOT_ESTABLISHED"
SOURCE_GAMES = prereg.SOURCE_GAMES
MIN_ELIGIBLE_STATES = 3_600
MIN_ELIGIBLE_GAMES = 1_800
MIN_ELIGIBLE_OPENINGS = 1_800
MIN_RAW_PAIR_CAPACITY = 1_800
MIN_RAW_PAIR_CAPACITY_PER_POOL = 720
MAX_EXACT_TARGET_MINUTES = 360.0
SCHEMA_SELECTION = base.SCHEMA_SELECTION


def _validate_preregistration(report: dict[str, Any]) -> None:
    if (
        report.get("schema")
        != "jass.curriculum_error_endgame_abstention_preregistration_terminal.v1"
        or report.get("verdict") != prereg.READY
        or report.get("passed") is not True
        or report.get("fresh_pair_availability_authorized") is not True
        or report.get("fresh_target_reconstruction_authorized") is not False
    ):
        raise ValueError("availability requires certified endgame-abstention preregistration")
    campaign = report.get("protocol", {}).get("fresh_campaign", {})
    mining = report.get("protocol", {}).get("fresh_pair_mining", {})
    rule = report.get("frozen_hypothesis", {}).get("phase_rule", {})
    if (
        int(campaign.get("games_exact", -1)) != SOURCE_GAMES
        or int(campaign.get("openings_per_pool", -1)) != prereg.OPENINGS_PER_POOL
        or tuple(campaign.get("pool_seeds", ())) != prereg.POOL_SEEDS
        or int(campaign.get("split_seed", -1)) != prereg.SPLIT_SEED
        or int(mining.get("pair_count_exact", -1)) != prereg.FRESH_PAIRS
        or int(mining.get("seed", -1)) != prereg.MINING_SEED
        or int(mining.get("maximum_states_per_source_game", -1)) != base.MAX_STATES_PER_GAME
        or campaign.get("target_free_before_candidate_order") is not True
        or rule.get("abstain_exact_value") != "endgame"
        or rule.get("all_other_phases_use_frozen_residual_bit_identically") is not True
    ):
        raise ValueError("endgame-abstention availability protocol drift")


def prepare_profile_selection(selection: dict[str, Any]) -> dict[str, Any]:
    return base.prepare_profile_selection(selection, seed=prereg.MINING_SEED)


def audit(
    preregistration: dict[str, Any],
    selection: dict[str, Any],
    shards: list[dict[str, Any]],
    profile_cost: dict[str, Any],
    historical_exact_cost: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    report, lattice = base.audit_with_contract(
        preregistration,
        selection,
        shards,
        profile_cost,
        historical_exact_cost,
        preregistration_validator=_validate_preregistration,
        source_games=SOURCE_GAMES,
        pair_count=prereg.FRESH_PAIRS,
        mining_seed=prereg.MINING_SEED,
        min_eligible_states=MIN_ELIGIBLE_STATES,
        min_eligible_games=MIN_ELIGIBLE_GAMES,
        min_eligible_openings=MIN_ELIGIBLE_OPENINGS,
        min_raw_pair_capacity=MIN_RAW_PAIR_CAPACITY,
        min_raw_pair_capacity_per_pool=MIN_RAW_PAIR_CAPACITY_PER_POOL,
        max_exact_target_minutes=MAX_EXACT_TARGET_MINUTES,
    )
    passed = bool(report["passed"])
    report.update(
        {
            "schema": SCHEMA_REPORT,
            "verdict": READY if passed else NOT_ESTABLISHED,
            "availability_contract": {
                "fresh_pairs": prereg.FRESH_PAIRS,
                "source_games": SOURCE_GAMES,
                "minimum_raw_pair_capacity": MIN_RAW_PAIR_CAPACITY,
                "minimum_raw_pair_capacity_per_pool": MIN_RAW_PAIR_CAPACITY_PER_POOL,
                "maximum_exact_target_minutes": MAX_EXACT_TARGET_MINUTES,
                "phase_rule": "abstain_when_phase_equals_endgame",
            },
            "next_stage": "fresh_endgame_abstention_confirmation" if passed else None,
        }
    )
    lattice["schema"] = "jass.l3_curriculum_error_endgame_abstention_lattice.v1"
    lattice["pair_count_required"] = prereg.FRESH_PAIRS
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
        base._publish(args.output, output)
        print(json.dumps({"profile_rows": len(output["rows"]), "loss_games": output["loss_games"]}, sort_keys=True))
        return 0
    report, lattice = audit(
        json.loads(args.preregistration.read_text()),
        json.loads(args.selection.read_text()),
        [json.loads(path.read_text()) for path in args.profile_shard],
        json.loads(args.profile_cost.read_text()),
        json.loads(args.historical_exact_cost.read_text()),
    )
    report["preregistration_sha256"] = base._sha256(args.preregistration)
    report["selection_sha256"] = base._sha256(args.selection)
    report["profile_shard_sha256"] = sorted(base._sha256(path) for path in args.profile_shard)
    report["historical_exact_cost_sha256"] = base._sha256(args.historical_exact_cost)
    base._publish(args.report, report)
    base._publish(args.lattice, lattice)
    print(json.dumps({"verdict": report["verdict"], "capacity": report["raw_pair_capacity"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
