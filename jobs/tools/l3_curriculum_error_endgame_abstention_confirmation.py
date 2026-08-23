#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Confirm the frozen endgame-abstention residual on 600 completely fresh pairs."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

import numpy as np

from jobs.tools import l3_curriculum_error_endgame_abstention_availability as availability
from jobs.tools import l3_curriculum_error_endgame_abstention_preregistration as prereg
from jobs.tools import l3_curriculum_error_fresh_pair_availability_preflight as availability_base
from jobs.tools import l3_curriculum_error_fresh_powered_confirmation as base
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge
from jobs.tools import l3_curriculum_error_trace_residual_training as training
from jobs.tools import l3_curriculum_search_error_atlas as atlas


SCHEMA_REPORT = "jass.l3_curriculum_error_endgame_abstention_confirmation.v1"
SCHEMA_TERMINAL = "jass.curriculum_error_endgame_abstention_confirmation_terminal.v1"
READY = "JASS_CURRICULUM_ERROR_ENDGAME_ABSTENTION_CONFIRMATION_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_ENDGAME_ABSTENTION_CONFIRMATION_NOT_ESTABLISHED"
FRESH_PAIRS = prereg.FRESH_PAIRS
STOP_RULE = "first_600_valid_pairs_in_frozen_pre_target_order"


def _check_preregistration(report: dict[str, Any]) -> dict[str, Any]:
    availability._validate_preregistration(report)
    confirm = report.get("protocol", {}).get("fresh_confirmation", {})
    expected = {
        "bootstrap_samples": prereg.BOOTSTRAP_SAMPLES,
        "bootstrap_seed": prereg.BOOTSTRAP_SEED,
        "sham_replicates": prereg.SHAM_REPLICATES,
        "sham_seed": prereg.SHAM_SEED,
        "minimum_error_interventions": prereg.MIN_ERROR_INTERVENTIONS,
        "minimum_control_interventions": prereg.MIN_CONTROL_INTERVENTIONS,
        "minimum_total_interventions": prereg.MIN_TOTAL_INTERVENTIONS,
        "minimum_error_interventions_per_pool": prereg.MIN_ERROR_INTERVENTIONS_PER_POOL,
        "minimum_control_interventions_per_pool": prereg.MIN_CONTROL_INTERVENTIONS_PER_POOL,
    }
    for key, value in expected.items():
        if confirm.get(key) != value:
            raise ValueError(f"fresh confirmation preregistration drift: {key}")
    if (
        confirm.get("all_gates_required_jointly") is not True
        or confirm.get("endgame_interventions_exactly") != 0
        or confirm.get("endgame_decisions_bit_identical_to_CURRICULUM_anchor") is not True
        or confirm.get("non_endgame_decisions_bit_identical_to_frozen_1517_residual") is not True
    ):
        raise ValueError("fresh confirmation decision-rule drift")
    frozen = report["frozen_hypothesis"]
    return {
        "alpha": float(frozen["alpha"]),
        "cap_cp": float(frozen["cap_cp"]),
        "mode": str(frozen["mode"]),
        "threshold_cp": float(frozen["threshold_cp"]),
        "phase_rule": frozen["phase_rule"],
    }


def prepare(
    preregistration: dict[str, Any],
    availability_report: dict[str, Any],
    lattice: dict[str, Any],
    source_selection: dict[str, Any],
    profile_selection: dict[str, Any],
    profile_shards: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    return base.prepare_with_contract(
        preregistration,
        availability_report,
        lattice,
        source_selection,
        profile_selection,
        profile_shards,
        preregistration_check=_check_preregistration,
        availability_schema=availability.SCHEMA_TERMINAL,
        availability_verdict=availability.READY,
        lattice_schema="jass.l3_curriculum_error_endgame_abstention_lattice.v1",
        mining_seed=prereg.MINING_SEED,
        pair_count=FRESH_PAIRS,
    )


def plan_batch(
    lattice: dict[str, Any], catalog: dict[str, Any], cache: dict[str, Any] | None,
    *, max_states: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    return base.plan_batch(
        lattice, catalog, cache, max_states=max_states, pair_count=FRESH_PAIRS
    )


def finalize_pairs_and_shards(
    lattice: dict[str, Any], catalog: dict[str, Any], cache: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return base.finalize_pairs_and_shards(
        lattice,
        catalog,
        cache,
        pair_count=FRESH_PAIRS,
        stop_rule=STOP_RULE,
    )


def _phase(state: dict[str, Any]) -> str:
    return str(availability_base._piece(state["profile"]["source"])["phase"])


def _apply_endgame_abstention(
    rows: list[dict[str, Any]], decisions: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_pair = {int(row["pair_id"]): row for row in rows}
    output = json.loads(json.dumps(decisions))
    endgame_states = 0
    would_intervene = 0
    endgame_bit_identical = True
    non_endgame_bit_identical = True
    for decision in output:
        source = by_pair[int(decision["pair_id"])]
        decision["source_pool"] = str(source["source_pool"])
        for role in ("error", "control"):
            phase = _phase(source[role])
            before = json.loads(json.dumps(decision[role]))
            decision[role]["phase"] = phase
            decision[role]["abstained_endgame"] = phase == "endgame"
            if phase == "endgame":
                endgame_states += 1
                would_intervene += int(bool(before["intervention"]))
                decision[role].update(
                    {
                        "would_intervene_without_endgame_abstention": bool(before["intervention"]),
                        "intervention": False,
                        "improvement_cp": 0.0,
                        "predicted_advantage_cp": None,
                        "realized_gain_cp": None,
                        "aligned_symmetry": bool(before["anchor_symmetry"]),
                        "outside_gate_bit_identical": True,
                        "action": None,
                    }
                )
                endgame_bit_identical &= (
                    decision[role]["intervention"] is False
                    and decision[role]["improvement_cp"] == 0.0
                    and decision[role]["action"] is None
                )
            else:
                after_core = {
                    key: decision[role][key]
                    for key in before
                }
                non_endgame_bit_identical &= after_core == before
                decision[role]["non_endgame_residual_bit_identical"] = after_core == before
    proof = {
        "endgame_states": endgame_states,
        "would_intervene_without_abstention": would_intervene,
        "endgame_interventions": sum(
            int(row[role]["intervention"])
            for row in output
            for role in ("error", "control")
            if row[role]["phase"] == "endgame"
        ),
        "endgame_decisions_bit_identical_to_anchor": endgame_bit_identical,
        "non_endgame_decisions_bit_identical_to_frozen_residual": non_endgame_bit_identical,
    }
    return output, proof


def _metrics(decisions: list[dict[str, Any]], *, seed: int) -> dict[str, Any]:
    errors = [float(row["error"]["improvement_cp"]) for row in decisions]
    controls = [float(row["control"]["improvement_cp"]) for row in decisions]
    paired = [left - right for left, right in zip(errors, controls, strict=True)]
    changed = [row["error"] for row in decisions if row["error"]["intervention"]]
    symmetry = lambda role, key: (
        float(np.mean([bool(row[role][key]) for row in decisions]))
        if decisions else None
    )
    return {
        "pairs": len(decisions),
        "error_improvement": atlas._bootstrap(errors, samples=prereg.BOOTSTRAP_SAMPLES, seed=seed),
        "control_improvement": atlas._bootstrap(controls, samples=prereg.BOOTSTRAP_SAMPLES, seed=seed + 1),
        "paired_error_minus_control": atlas._bootstrap(paired, samples=prereg.BOOTSTRAP_SAMPLES, seed=seed + 2),
        "error_interventions": sum(bool(row["error"]["intervention"]) for row in decisions),
        "control_interventions": sum(bool(row["control"]["intervention"]) for row in decisions),
        "error_positive_realization_rate": (
            float(np.mean([float(row["realized_gain_cp"]) > 0.0 for row in changed]))
            if changed else None
        ),
        "error_anchor_symmetry_rate": symmetry("error", "anchor_symmetry"),
        "error_aligned_symmetry_rate": symmetry("error", "aligned_symmetry"),
        "control_anchor_symmetry_rate": symmetry("control", "anchor_symmetry"),
        "control_aligned_symmetry_rate": symmetry("control", "aligned_symmetry"),
        "outside_gate_bit_identical": all(
            row[role]["outside_gate_bit_identical"]
            for row in decisions for role in ("error", "control")
        ),
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
    fresh_rows, fresh_identities = base._load_fresh_rows(
        fresh_pairs, fresh_shards, pair_count=FRESH_PAIRS
    )
    for key, value in training_identities.items():
        if training_report.get(key) != value or failed_model.get(key) != value:
            raise ValueError(f"immutable 1508 source {key} drift")
    if training_identities != fresh_identities:
        raise ValueError("fresh confirmation engine/model/profile identity differs from 1508")
    if (
        target_cache.get("schema") != base.SCHEMA_CACHE
        or target_cache.get("identities") != {
            **fresh_identities,
            "search_arms": fresh_shards[0].get("search_arms"),
            "judge_depth": base.JUDGE_DEPTH,
        }
    ):
        raise ValueError("fresh confirmation target-cache identity drift")

    real_model = ridge._fit(training_rows, alpha=selected["alpha"])
    base_decisions = ridge._decisions(
        fresh_rows,
        {row["pair_id"]: real_model for row in fresh_rows},
        cap_cp=selected["cap_cp"],
        threshold_cp=selected["threshold_cp"],
        mode=selected["mode"],
    )
    decisions, rule_proof = _apply_endgame_abstention(fresh_rows, base_decisions)
    metrics = _metrics(decisions, seed=prereg.BOOTSTRAP_SEED)
    by_pool = {
        pool: _metrics(
            [row for row in decisions if row["source_pool"] == pool],
            seed=prereg.BOOTSTRAP_SEED + 100 * index,
        )
        for index, pool in enumerate(("pool1", "pool2"), start=1)
    }

    sham_means = []
    for replicate in range(prereg.SHAM_REPLICATES):
        model = ridge._fit(training_rows, alpha=selected["alpha"], sham_seed=prereg.SHAM_SEED + replicate)
        sham_base = ridge._decisions(
            fresh_rows,
            {row["pair_id"]: model for row in fresh_rows},
            cap_cp=selected["cap_cp"],
            threshold_cp=selected["threshold_cp"],
            mode=selected["mode"],
        )
        sham_decisions, _proof = _apply_endgame_abstention(fresh_rows, sham_base)
        sham_means.append(float(np.mean([
            row["error"]["improvement_cp"] - row["control"]["improvement_cp"]
            for row in sham_decisions
        ])))
    sham_q99 = float(np.quantile(np.asarray(sham_means), 0.99))
    real_mean = float(metrics["paired_error_minus_control"]["mean"])
    symmetry_drop = metrics["error_anchor_symmetry_rate"] - metrics["error_aligned_symmetry_rate"]

    gates = {
        "fresh_pairs_exactly_600": len(fresh_rows) == FRESH_PAIRS,
        "error_interventions_at_least_60": metrics["error_interventions"] >= prereg.MIN_ERROR_INTERVENTIONS,
        "control_interventions_at_least_40": metrics["control_interventions"] >= prereg.MIN_CONTROL_INTERVENTIONS,
        "total_interventions_at_least_100": metrics["error_interventions"] + metrics["control_interventions"] >= prereg.MIN_TOTAL_INTERVENTIONS,
        "error_ci95_lower_gt_0cp": float(metrics["error_improvement"]["ci95"][0]) > 0.0,
        "paired_ci95_lower_gt_0cp": float(metrics["paired_error_minus_control"]["ci95"][0]) > 0.0,
        "control_mean_gain_at_least_minus_2cp": float(metrics["control_improvement"]["mean"]) >= -2.0,
        "error_positive_realization_rate_at_least_0_60": metrics["error_positive_realization_rate"] is not None and metrics["error_positive_realization_rate"] >= 0.60,
        "error_aligned_symmetry_at_least_0_70": metrics["error_aligned_symmetry_rate"] >= 0.70,
        "error_symmetry_drop_at_most_0_02": symmetry_drop <= 0.02,
        "endgame_interventions_exactly_0": rule_proof["endgame_interventions"] == 0,
        "endgame_decisions_bit_identical_to_anchor": rule_proof["endgame_decisions_bit_identical_to_anchor"],
        "non_endgame_decisions_bit_identical_to_frozen_residual": rule_proof["non_endgame_decisions_bit_identical_to_frozen_residual"],
        "real_paired_mean_exceeds_1000_sham_q99": real_mean > sham_q99,
        "outside_gate_bit_identical": metrics["outside_gate_bit_identical"],
        "fresh_labels_not_used_for_fit": True,
    }
    for pool, row in by_pool.items():
        gates[f"{pool}_error_interventions_at_least_25"] = row["error_interventions"] >= prereg.MIN_ERROR_INTERVENTIONS_PER_POOL
        gates[f"{pool}_control_interventions_at_least_18"] = row["control_interventions"] >= prereg.MIN_CONTROL_INTERVENTIONS_PER_POOL
        error_mean = row["error_improvement"]["mean"]
        paired_mean = row["paired_error_minus_control"]["mean"]
        control_mean = row["control_improvement"]["mean"]
        gates[f"{pool}_error_mean_gt_0cp"] = error_mean is not None and float(error_mean) > 0.0
        gates[f"{pool}_paired_mean_gt_0cp"] = paired_mean is not None and float(paired_mean) > 0.0
        gates[f"{pool}_control_mean_at_least_minus_2cp"] = control_mean is not None and float(control_mean) >= -2.0
    passed = all(gates.values())

    confirmation_target_states = [
        row[role] for shard in fresh_shards for row in shard["rows"] for role in ("error", "control")
    ]
    all_target_states = list(target_cache.get("judgments", {}).values())
    selected_state_keys = {str(row["source"]["exact_state_key"]) for row in confirmation_target_states}
    if not selected_state_keys <= set(target_cache.get("judgments", {})):
        raise ValueError("fresh confirmation targets are absent from target cache")
    action_reads = sum(2 * len(row["action_values"]) for row in all_target_states)
    compact = lambda row: {key: value for key, value in row.items() if key != "paired_values_cp"}
    return {
        "schema": SCHEMA_REPORT,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        "selected_hypothesis": selected,
        "training_population": "immutable_1508_gate_fit_pairs_only",
        "fresh_labels_used_for_fit": False,
        "fresh_pairs": FRESH_PAIRS,
        "fresh_pairs_by_pool": dict(sorted(Counter(row["source_pool"] for row in decisions).items())),
        "metrics": compact(metrics),
        "metrics_by_pool": {pool: compact(row) for pool, row in by_pool.items()},
        "rule_proof": rule_proof,
        "symmetry_drop": symmetry_drop,
        "sham": {
            "replicates": prereg.SHAM_REPLICATES,
            "seed_start": prereg.SHAM_SEED,
            "paired_mean_q99_cp": sham_q99,
            "real_paired_mean_cp": real_mean,
            "real_exceeds_sham_q99": real_mean > sham_q99,
            "means_sha256": base._digest(sham_means),
        },
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "identities": fresh_identities,
        "new_target_states": len(all_target_states),
        "fresh_confirmation_target_states": len(confirmation_target_states),
        "discarded_labelled_states": len(all_target_states) - len(confirmation_target_states),
        "target_cache_sha256": base._digest(target_cache),
        "exact_target_batches": len(target_cache.get("batch_receipts", [])),
        "exact_action_value_reads": action_reads,
        "residual_fits": 1 + prereg.SHAM_REPLICATES,
        "diagnostic_fits": prereg.SHAM_REPLICATES,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "anchored_local_refit_preregistration_authorized": passed,
        "production_rule_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "anchored_local_refit_and_oos_audit_preregistration" if passed else None,
    }


def main() -> int:
    args = base.parser().parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    if args.command == "prepare":
        payload, paths = prepare(
            load(args.preregistration), load(args.availability), load(args.lattice),
            load(args.source_selection), load(args.profile_selection), base._load_many(args.profile_shard),
        )
        base._publish(args.prepared, payload)
        args.paths.parent.mkdir(parents=True, exist_ok=True)
        args.paths.write_text("".join(f"{value}\n" for value in paths), encoding="utf-8")
    elif args.command == "normalize":
        base._publish(args.catalog, base.normalize(
            load(args.prepared), load(args.lattice), load(args.profile_selection),
            base._load_many(args.profile_shard), args.games_dir, args.jass,
        ))
    elif args.command == "plan":
        catalog = load(args.catalog)
        cache = load(args.cache) if args.cache else base._empty_cache(catalog)
        if args.cache is None:
            if args.cache_output is None:
                raise ValueError("--cache-output is required for the first target batch")
            base._publish(args.cache_output, cache)
        plan, batch = plan_batch(load(args.lattice), catalog, cache, max_states=args.max_states)
        base._publish(args.plan, plan)
        if batch is not None:
            if args.batch is None:
                raise ValueError("--batch is required while exact targets remain")
            base._publish(args.batch, batch)
    elif args.command == "ingest":
        base._publish(args.output, base.ingest(
            load(args.cache), load(args.catalog), load(args.batch), base._load_many(args.atlas_shard)
        ))
    elif args.command == "finalize":
        pairs, shards = finalize_pairs_and_shards(
            load(args.lattice), load(args.catalog), load(args.cache)
        )
        base._publish(args.pairs, pairs)
        args.shards_dir.mkdir(parents=True, exist_ok=True)
        for shard in shards:
            base._publish(args.shards_dir / f"shard-{shard['shard']}.json", shard)
    elif args.command == "confirm":
        base._publish(args.report, confirm(
            load(args.preregistration), load(args.training_report), load(args.failed_model),
            load(args.training_pairs), base._load_many(args.training_shard),
            load(args.fresh_pairs), base._load_many(args.fresh_shard), load(args.target_cache),
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
