#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seal the target-free OOS availability campaign after the anchored refit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jobs.tools import l3_curriculum_error_anchored_local_refit as anchored
from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_audit as oos
from jobs.tools import l3_curriculum_error_anchored_local_refit_preregistration as prereg


SCHEMA = "jass.l3_curriculum_error_anchored_local_refit_oos_availability_preregistration.v1"
SCHEMA_TERMINAL = "jass.curriculum_error_anchored_local_refit_oos_availability_preregistration_terminal.v1"
READY = "JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_OOS_AVAILABILITY_PREREGISTERED"
SOURCE_GAMES = 15_360
OPENINGS_PER_POOL = 1_920
PAIR_COUNT_PER_POOL = 300
MIN_ELIGIBLE_STATES = 3_600
MIN_ELIGIBLE_GAMES = 1_800
MIN_ELIGIBLE_OPENINGS = 1_800
MIN_RAW_PAIR_CAPACITY = 1_800
MIN_RAW_PAIR_CAPACITY_PER_POOL = 720
MAX_EXACT_TARGET_MINUTES = 360.0
OOS_PAIRS = prereg.OOS_PAIRS
OOS_POOL1_SEED = prereg.OOS_POOL1_SEED
OOS_POOL2_SEED = prereg.OOS_POOL2_SEED
OOS_SPLIT_SEED = prereg.OOS_SPLIT_SEED
REQUIRED_EXCLUSION_ROLES = (
    "historical_1504",
    "historical_fit_1508",
    "fresh_1515",
    "fresh_1517",
    "availability_1523",
    "confirmation_1524",
)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _check_joint_preregistration(report: dict[str, Any]) -> None:
    if (
        report.get("schema")
        != "jass.curriculum_error_anchored_local_refit_preregistration_terminal.v1"
        or report.get("verdict") != prereg.READY
        or report.get("passed") is not True
        or report.get("anchored_local_refit_authorized") is not True
        or report.get("oos_campaign_authorized") is not False
        or report.get("strength_gate_authorized") is not False
        or report.get("automatic_continuation") is not False
    ):
        raise ValueError("OOS availability requires the sealed joint preregistration")
    sealed = report.get("protocol", {}).get("sealed_oos", {})
    if (
        int(sealed.get("pair_count_exact", -1)) != prereg.OOS_PAIRS
        or sealed.get("two_pools") is not True
        or int(sealed.get("pool1_seed", -1)) != prereg.OOS_POOL1_SEED
        or int(sealed.get("pool2_seed", -1)) != prereg.OOS_POOL2_SEED
        or int(sealed.get("split_seed", -1)) != prereg.OOS_SPLIT_SEED
        or sealed.get("target_free_candidate_order") is not True
        or int(sealed.get("maximum_states_per_source_game", -1)) != 2
        or sealed.get("canonical_state_unique") is not True
        or sealed.get("no_oos_label_used_for_fit_or_selection") is not True
    ):
        raise ValueError("sealed OOS protocol drift")


def _check_exclusions(exclusions: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = sorted(exclusions, key=lambda row: row["role"])
    roles = tuple(row.get("role") for row in normalized)
    if roles != tuple(sorted(REQUIRED_EXCLUSION_ROLES)):
        raise ValueError("OOS exclusion-chain roles are incomplete")
    for row in normalized:
        if (
            not row.get("job")
            or not row.get("attempt")
            or len(str(row.get("code_sha", ""))) != 40
        ):
            raise ValueError("OOS exclusion-chain identity drift")
    if len({(row["job"], row["attempt"]) for row in normalized}) != len(normalized):
        raise ValueError("OOS exclusion-chain identities are not unique")
    return normalized


def preregister(
    joint: dict[str, Any],
    fit_report: dict[str, Any],
    model: dict[str, Any],
    joint_identity: tuple[str, str, str],
    fit_identity: tuple[str, str, str],
    exclusions: list[dict[str, str]],
) -> dict[str, Any]:
    _check_joint_preregistration(joint)
    oos._check_fit(fit_report, model)
    exclusion_chain = _check_exclusions(exclusions)
    identities = joint.get("identities") or {}
    if identities != fit_report.get("identities") or identities != model.get("identities"):
        raise ValueError("OOS availability scientific identity drift")
    if (
        joint.get("support", {}).get("support_sha256") != model.get("support_sha256")
        or fit_report.get("model_sha256") != _digest(model)
    ):
        raise ValueError("OOS availability model/support identity drift")

    protocol = {
        "status": "sealed_after_fit_before_any_oos_game_or_label",
        "fresh_campaign": {
            "games_exact": SOURCE_GAMES,
            "openings_per_pool": OPENINGS_PER_POOL,
            "pool_seeds": [OOS_POOL1_SEED, OOS_POOL2_SEED],
            "split_seed": OOS_SPLIT_SEED,
            "movetime_seconds": 0.1,
            "same_byte_identical_CURRICULUM_both_sides": True,
            "target_free_before_candidate_order": True,
            "opening_and_game_disjoint_from_exclusion_chain": True,
        },
        "fresh_pair_mining": {
            "pair_count_exact": OOS_PAIRS,
            "pair_count_per_pool_exact": PAIR_COUNT_PER_POOL,
            "seed": OOS_SPLIT_SEED,
            "stop_rule": "first_300_valid_pairs_per_pool_in_frozen_pre_target_order",
            "maximum_states_per_source_game": 2,
            "canonical_state_unique": True,
            "target_free_before_selection": True,
        },
        "availability_gate": {
            "minimum_eligible_states": MIN_ELIGIBLE_STATES,
            "minimum_eligible_games": MIN_ELIGIBLE_GAMES,
            "minimum_eligible_openings": MIN_ELIGIBLE_OPENINGS,
            "minimum_raw_pair_capacity": MIN_RAW_PAIR_CAPACITY,
            "minimum_raw_pair_capacity_per_pool": MIN_RAW_PAIR_CAPACITY_PER_POOL,
            "maximum_exact_target_minutes": MAX_EXACT_TARGET_MINUTES,
        },
        "exact_targets_after_availability_pass_only": {
            "judge_depth": 12,
            "same_first_valid_per_pool_order": True,
            "labels_never_used_for_fit_or_candidate_selection": True,
        },
        "exclusion_chain": exclusion_chain,
        "exclusion_chain_sha256": _digest(exclusion_chain),
    }
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "joint_preregistration_source": {
            "job": joint_identity[0],
            "attempt": joint_identity[1],
            "code_sha": joint_identity[2],
        },
        "anchored_fit_source": {
            "job": fit_identity[0],
            "attempt": fit_identity[1],
            "code_sha": fit_identity[2],
        },
        "identities": identities,
        "support_sha256": model["support_sha256"],
        "anchored_model_sha256": fit_report["model_sha256"],
        "protocol": protocol,
        "protocol_sha256": _digest(protocol),
        "fresh_pair_availability_authorized": True,
        "fresh_target_reconstruction_authorized": False,
        "oos_campaign_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "new_targets": 0,
        "oos_reads": 0,
        "diagnostic_fits": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "next_stage": "target_free_oos_availability",
    }


def _identity(value: str) -> dict[str, str]:
    parts = value.split("|", 3)
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("identity must be role|job|attempt|code_sha")
    return {"role": parts[0], "job": parts[1], "attempt": parts[2], "code_sha": parts[3]}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--joint-preregistration", type=Path, required=True)
    root.add_argument("--joint-job", required=True)
    root.add_argument("--joint-attempt", required=True)
    root.add_argument("--joint-code", required=True)
    root.add_argument("--fit-report", type=Path, required=True)
    root.add_argument("--fit-model", type=Path, required=True)
    root.add_argument("--fit-job", required=True)
    root.add_argument("--fit-attempt", required=True)
    root.add_argument("--fit-code", required=True)
    root.add_argument("--exclude-source", action="append", type=_identity, required=True)
    root.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    load = lambda path: json.loads(path.read_text())
    report = preregister(
        load(args.joint_preregistration),
        load(args.fit_report),
        load(args.fit_model),
        (args.joint_job, args.joint_attempt, args.joint_code),
        (args.fit_job, args.fit_attempt, args.fit_code),
        args.exclude_source,
    )
    _publish(args.output, report)
    print(json.dumps({"verdict": report["verdict"], "protocol_sha256": report["protocol_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
