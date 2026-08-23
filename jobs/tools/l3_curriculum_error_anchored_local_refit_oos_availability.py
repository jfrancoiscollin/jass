#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Target-free availability screen for the sealed anchored-refit OOS audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_availability_preregistration as prereg
from jobs.tools import l3_curriculum_error_fresh_pair_availability_preflight as base


SCHEMA_REPORT = "jass.l3_curriculum_error_anchored_local_refit_oos_availability.v1"
SCHEMA_TERMINAL = "jass.curriculum_error_anchored_local_refit_oos_availability_terminal.v1"
SCHEMA_LATTICE = "jass.l3_curriculum_error_anchored_local_refit_oos_lattice.v1"
READY = "JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_OOS_AVAILABILITY_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_OOS_AVAILABILITY_NOT_ESTABLISHED"
SCHEMA_SELECTION = base.SCHEMA_SELECTION


def _validate_preregistration(report: dict[str, Any]) -> None:
    if (
        report.get("schema") != prereg.SCHEMA_TERMINAL
        or report.get("verdict") != prereg.READY
        or report.get("passed") is not True
        or report.get("fresh_pair_availability_authorized") is not True
        or report.get("fresh_target_reconstruction_authorized") is not False
        or report.get("oos_campaign_authorized") is not False
    ):
        raise ValueError("OOS availability requires its sealed preregistration")
    campaign = report.get("protocol", {}).get("fresh_campaign", {})
    mining = report.get("protocol", {}).get("fresh_pair_mining", {})
    if (
        int(campaign.get("games_exact", -1)) != prereg.SOURCE_GAMES
        or int(campaign.get("openings_per_pool", -1)) != prereg.OPENINGS_PER_POOL
        or tuple(campaign.get("pool_seeds", ()))
        != (prereg.OOS_POOL1_SEED, prereg.OOS_POOL2_SEED)
        or int(campaign.get("split_seed", -1)) != prereg.OOS_SPLIT_SEED
        or campaign.get("target_free_before_candidate_order") is not True
        or int(mining.get("pair_count_exact", -1)) != prereg.OOS_PAIRS
        or int(mining.get("pair_count_per_pool_exact", -1)) != prereg.PAIR_COUNT_PER_POOL
        or int(mining.get("seed", -1)) != prereg.OOS_SPLIT_SEED
        or mining.get("stop_rule")
        != "first_300_valid_pairs_per_pool_in_frozen_pre_target_order"
        or int(mining.get("maximum_states_per_source_game", -1)) != base.MAX_STATES_PER_GAME
        or mining.get("target_free_before_selection") is not True
    ):
        raise ValueError("anchored OOS availability protocol drift")


def prepare_profile_selection(selection: dict[str, Any]) -> dict[str, Any]:
    return base.prepare_profile_selection(selection, seed=prereg.OOS_SPLIT_SEED)


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
        source_games=prereg.SOURCE_GAMES,
        pair_count=prereg.OOS_PAIRS,
        mining_seed=prereg.OOS_SPLIT_SEED,
        min_eligible_states=prereg.MIN_ELIGIBLE_STATES,
        min_eligible_games=prereg.MIN_ELIGIBLE_GAMES,
        min_eligible_openings=prereg.MIN_ELIGIBLE_OPENINGS,
        min_raw_pair_capacity=prereg.MIN_RAW_PAIR_CAPACITY,
        min_raw_pair_capacity_per_pool=prereg.MIN_RAW_PAIR_CAPACITY_PER_POOL,
        max_exact_target_minutes=prereg.MAX_EXACT_TARGET_MINUTES,
    )
    passed = bool(report["passed"])
    report.update(
        {
            "schema": SCHEMA_REPORT,
            "verdict": READY if passed else NOT_ESTABLISHED,
            "pairs_required_by_pool": {"pool1": prereg.PAIR_COUNT_PER_POOL, "pool2": prereg.PAIR_COUNT_PER_POOL},
            "oos_target_reconstruction_authorized": passed,
            "next_stage": "exact_label_first_300_valid_pairs_per_pool_then_oos_audit" if passed else None,
        }
    )
    lattice.update(
        {
            "schema": SCHEMA_LATTICE,
            "pair_count_required": prereg.OOS_PAIRS,
            "pair_count_required_by_pool": {"pool1": prereg.PAIR_COUNT_PER_POOL, "pool2": prereg.PAIR_COUNT_PER_POOL},
            "selection_rule": "first_300_valid_pairs_per_pool_in_frozen_pre_target_order",
        }
    )
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
