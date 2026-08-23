#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seal the loss-first sibling-ranking campaign after the 1541 tail audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "jass.l3_curriculum_error_loss_first_sibling_rank_preregistration.v1"
READY = "JASS_CURRICULUM_ERROR_LOSS_FIRST_SIBLING_RANK_PREREGISTERED"
SOURCE_SCHEMA = "jass.curriculum_error_loss_first_provenance_audit_terminal.v1"
SOURCE_VERDICT = "JASS_CURRICULUM_ERROR_LOSS_FIRST_PROVENANCE_AUDIT_READY"
SOURCE_CODE = "ecade10eb382c5bfd4511e1b2713c594fe3c6ceb"
POOL_SEEDS = (2026082341, 2026082342)
SPLIT_SEED = 2026082343
MATCH_SEED = 2026082344
BOOTSTRAP_SEED = 2026082345
SHAM_SEED = 2026082346


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(_canonical(value)); tmp.replace(path)


def preregister(source: dict[str, Any]) -> dict[str, Any]:
    tail = source.get("loss_tail", {})
    contract = source.get("loss_first_acquisition_contract", {})
    if (
        source.get("schema") != SOURCE_SCHEMA
        or source.get("code_sha") != SOURCE_CODE
        or source.get("verdict") != SOURCE_VERDICT
        or source.get("passed") is not True
        or source.get("scientific_status")
        != "raw_cp_endpoint_tail_dominated__loss_first_rank_supervision_required"
        or source.get("next_stage") != "preregister_loss_first_sibling_rank_corpus"
        or tail.get("score_scale_tail_dominated") is not True
        or int(tail.get("sentinel_scale_loss_count", -1)) != 2
        or float(tail.get("sentinel_scale_loss_share", 0.0)) < 0.70
        or contract.get("name") != "loss_first_sibling_rank_corpus_v1"
    ):
        raise ValueError("requires exact certified 1541 sentinel-tail audit")
    for key in (
        "anchored_local_refit_authorized", "production_model_authorized",
        "strength_gate_authorized", "promotion_authorized", "automatic_continuation",
    ):
        if source.get(key) is not False:
            raise ValueError(f"1541 forbidden authorization drift: {key}")

    source_campaign = {
        "champion": "CURRICULUM byte-identical both sides",
        "pools": 2,
        "openings_per_pool": 384,
        "games_per_opening": 2,
        "total_games": 1536,
        "native_movetime_seconds": 0.1,
        "pool_seeds": list(POOL_SEEDS),
        "all_games_retained": True,
        "all_decisions_dumped": True,
        "opening_pools_disjoint_from_all_authenticated_historical_pools": True,
        "source_stage_has_no_deep_targets": True,
    }
    acquisition = {
        "selection_blinded_to": [
            "terminal outcome", "deep teacher action", "deep score", "regret",
        ],
        "selection_inputs": [
            "shallow d6-d9 action/PV instability", "phase", "piece_count",
            "king_count", "capture_or_quiet", "legal_action_count",
        ],
        "candidate_strata": "pool x phase x kings x capture_or_quiet x legal_action_count_bin",
        "per_opening_vote_cap": 1,
        "per_game_state_cap": 2,
        "canonical_state_unique": True,
        "split_unit": "connected opening_id/game_uid/canonical_state component",
        "split_seed": SPLIT_SEED,
        "match_seed": MATCH_SEED,
    }
    teacher = {
        "identity": "same byte-identical CURRICULUM model and exact-fold/tempo-stage engine",
        "budgets": ["depth10", "depth12"],
        "actions": "all legal sibling actions in both exact orientations",
        "accepted_only_if": [
            "top-action agrees at depth10 and depth12",
            "WDL ordering agrees at depth10 and depth12",
            "rot180+colour-swap action mapping and ordering agree",
            "search result is exact or its bound is compatible with every asserted preference",
        ],
        "raw_cp_sentinels_used_as_loss_magnitude": False,
    }
    labels = {
        "primary": "per-state equal-weight listwise teacher ordering",
        "secondary": "pairwise teacher preference for teacher-top versus each legal sibling",
        "teacher_margin_cap_cp": 200.0,
        "per_state_total_loss_mass": 1.0,
        "per_opening_total_loss_mass": 1.0,
        "raw_cp_mean": "diagnostic_only",
        "error_definition": "native champion action not teacher-top and stable regret >=50cp",
        "control_definition": "native champion action teacher-top or stable regret <=10cp",
        "matching_without_replacement": "pool x phase x kings x capture_or_quiet x branching_bin",
    }
    screen = {
        "cross_fit": "pool1 fit -> pool2 evaluate and pool2 fit -> pool1 evaluate",
        "candidate_parameter_geometry": "sparse PatternEval PV-leaf teacher-minus-sibling Jacobians",
        "coordinate_discovery": {
            "minimum_error_openings": 12,
            "minimum_sign_consistency": 0.75,
            "maximum_canonical_buckets": 128,
            "MG_and_EG_coupled_by_bucket": True,
            "dense_extras_trainable": False,
        },
        "diagnostic_fit": {
            "loss": "bounded pairwise logistic plus listwise cross-entropy",
            "prior_mean": "CURRICULUM",
            "outside_selected_region": "exactly frozen",
            "per_opening_equal_weight": True,
            "optimizer_convergence_required": True,
        },
        "primary_gates": [
            "both held-out pools improve teacher-top hit rate",
            "both held-out pools reduce stable >=50cp error rate",
            "paired error-minus-control improvement lower CI95 > 0",
            "control teacher-top hit rate does not regress by more than 0.5 percentage point",
            "orientation symmetry >=99.9%",
            "selected coordinate cosine across pool fits >=0.50",
            "real score exceeds familywise q99 of 1000 opening-cluster label shams",
        ],
        "bootstrap": {"samples": 200000, "seed": BOOTSTRAP_SEED, "unit": "opening component"},
        "shams": {"replicates": 1000, "seed": SHAM_SEED, "strata": "matching strata"},
        "fresh_confirmation_after_pass_required": True,
    }
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "scientific_status": "loss_first_sibling_rank_campaign_preregistered",
        "source": {
            "job": "cpx62-1541-l3-curriculum-error-loss-first-provenance-audit-v1",
            "attempt": "20260823T151026Z-ecade10e",
            "code_sha": SOURCE_CODE,
            "report_sha256": _digest(source),
        },
        "source_campaign": source_campaign,
        "acquisition": acquisition,
        "teacher": teacher,
        "labels": labels,
        "mechanistic_screen": screen,
        "seeds": {
            "pool1": POOL_SEEDS[0], "pool2": POOL_SEEDS[1],
            "split": SPLIT_SEED, "match": MATCH_SEED,
            "bootstrap": BOOTSTRAP_SEED, "sham": SHAM_SEED,
        },
        "new_exact_target_computations": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "source_campaign_authorized": True,
        "deep_sibling_labeling_authorized_after_source_audit": True,
        "anchored_local_refit_authorized": False,
        "production_model_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "fresh_loss_first_source_campaign",
    }


def parser() -> argparse.ArgumentParser:
    output = argparse.ArgumentParser(description=__doc__)
    output.add_argument("--source-report", type=Path, required=True)
    output.add_argument("--report", type=Path, required=True)
    return output


def main() -> int:
    args = parser().parse_args()
    report = preregister(json.loads(args.source_report.read_text(encoding="utf-8")))
    _publish(args.report, report)
    print(json.dumps({"verdict": report["verdict"], "next_stage": report["next_stage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
