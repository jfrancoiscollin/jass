#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Label exactly 300 frozen-order OOS pairs per pool and audit the anchored refit."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_audit as auditor
from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_availability as availability
from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_availability_preregistration as prereg
from jobs.tools import l3_curriculum_error_fresh_powered_confirmation as base


PAIR_COUNT_BY_POOL = {"pool1": prereg.PAIR_COUNT_PER_POOL, "pool2": prereg.PAIR_COUNT_PER_POOL}
PAIR_COUNT = sum(PAIR_COUNT_BY_POOL.values())
STOP_RULE = "first_300_valid_pairs_per_pool_in_frozen_pre_target_order"


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
        preregistration_check=availability._validate_preregistration,
        availability_schema=availability.SCHEMA_TERMINAL,
        availability_verdict=availability.READY,
        lattice_schema=availability.SCHEMA_LATTICE,
        mining_seed=prereg.OOS_SPLIT_SEED,
        pair_count=PAIR_COUNT,
    )


def plan_batch(
    lattice: dict[str, Any],
    catalog: dict[str, Any],
    cache: dict[str, Any] | None,
    *,
    max_states: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    return base.plan_batch(
        lattice,
        catalog,
        cache,
        max_states=max_states,
        pair_count=PAIR_COUNT,
        pair_count_by_pool=PAIR_COUNT_BY_POOL,
    )


def finalize_pairs_and_shards(
    lattice: dict[str, Any], catalog: dict[str, Any], cache: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return base.finalize_pairs_and_shards(
        lattice,
        catalog,
        cache,
        pair_count=PAIR_COUNT,
        pair_count_by_pool=PAIR_COUNT_BY_POOL,
        stop_rule=STOP_RULE,
    )


def audit(
    fit_report: dict[str, Any],
    model: dict[str, Any],
    pairs: dict[str, Any],
    shards: list[dict[str, Any]],
    target_cache: dict[str, Any],
    *,
    champion_sha256: str,
) -> dict[str, Any]:
    rows, identities = base._load_fresh_rows(pairs, shards, pair_count=PAIR_COUNT)
    if Counter(row["source_pool"] for row in rows) != Counter(PAIR_COUNT_BY_POOL):
        raise ValueError("anchored OOS dataset is not exactly 300 pairs per pool")
    expected_cache_identity = {
        **identities,
        "search_arms": shards[0].get("search_arms"),
        "judge_depth": base.JUDGE_DEPTH,
    }
    if (
        target_cache.get("schema") != base.SCHEMA_CACHE
        or target_cache.get("identities") != expected_cache_identity
    ):
        raise ValueError("anchored OOS target-cache identity drift")
    selected_keys = {
        str(row[role]["source"]["exact_state_key"])
        for pair in pairs["pairs"]
        for role in ("error", "control")
    }
    judgments = target_cache.get("judgments", {})
    if not selected_keys <= set(judgments):
        raise ValueError("anchored OOS selected targets are absent from cache")
    report = auditor.audit(
        fit_report, model, pairs, shards, champion_sha256=champion_sha256
    )
    all_targets = list(judgments.values())
    report.update(
        {
            "selection_rule": STOP_RULE,
            "pairs_by_pool": dict(sorted(PAIR_COUNT_BY_POOL.items())),
            "new_target_states": len(all_targets),
            "selected_target_states": len(selected_keys),
            "discarded_labelled_states": len(all_targets) - len(selected_keys),
            "exact_target_batches": len(target_cache.get("batch_receipts", [])),
            "exact_action_value_reads": sum(
                2 * len(row.get("action_values", {})) for row in all_targets
            ),
            "oos_labels_used_for_fit_or_selection": False,
            "candidate_order_fixed_before_targets": True,
            "target_cache_sha256": base._digest(target_cache),
        }
    )
    return report


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
    ingest = sub.add_parser("ingest")
    for name in ("cache", "catalog", "batch"):
        ingest.add_argument(f"--{name}", type=Path, required=True)
    ingest.add_argument("--atlas-shard", type=Path, action="append", required=True)
    ingest.add_argument("--output", type=Path, required=True)
    final = sub.add_parser("finalize")
    for name in ("lattice", "catalog", "cache"):
        final.add_argument(f"--{name}", type=Path, required=True)
    final.add_argument("--pairs", type=Path, required=True)
    final.add_argument("--shards-dir", type=Path, required=True)
    check = sub.add_parser("audit")
    for name in ("fit-report", "fit-model", "fresh-pairs", "target-cache", "champion"):
        check.add_argument(f"--{name}", type=Path, required=True)
    check.add_argument("--fresh-shard", type=Path, action="append", required=True)
    check.add_argument("--report", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    if args.command == "prepare":
        payload, paths = prepare(
            load(args.preregistration),
            load(args.availability),
            load(args.lattice),
            load(args.source_selection),
            load(args.profile_selection),
            base._load_many(args.profile_shard),
        )
        base._publish(args.prepared, payload)
        args.paths.parent.mkdir(parents=True, exist_ok=True)
        args.paths.write_text("".join(f"{value}\n" for value in paths), encoding="utf-8")
    elif args.command == "normalize":
        base._publish(
            args.catalog,
            base.normalize(
                load(args.prepared),
                load(args.lattice),
                load(args.profile_selection),
                base._load_many(args.profile_shard),
                args.games_dir,
                args.jass,
            ),
        )
    elif args.command == "plan":
        catalog = load(args.catalog)
        cache = load(args.cache) if args.cache else base._empty_cache(catalog)
        if args.cache is None:
            if args.cache_output is None:
                raise ValueError("--cache-output is required for the first target batch")
            base._publish(args.cache_output, cache)
        plan, batch = plan_batch(
            load(args.lattice), catalog, cache, max_states=args.max_states
        )
        base._publish(args.plan, plan)
        if batch is not None:
            if args.batch is None:
                raise ValueError("--batch is required while exact targets remain")
            base._publish(args.batch, batch)
    elif args.command == "ingest":
        base._publish(
            args.output,
            base.ingest(
                load(args.cache),
                load(args.catalog),
                load(args.batch),
                base._load_many(args.atlas_shard),
            ),
        )
    elif args.command == "finalize":
        pairs, shards = finalize_pairs_and_shards(
            load(args.lattice), load(args.catalog), load(args.cache)
        )
        base._publish(args.pairs, pairs)
        args.shards_dir.mkdir(parents=True, exist_ok=True)
        for shard in shards:
            base._publish(args.shards_dir / f"shard-{shard['shard']}.json", shard)
    elif args.command == "audit":
        champion_sha256 = hashlib.sha256(args.champion.read_bytes()).hexdigest()
        base._publish(
            args.report,
            audit(
                load(args.fit_report),
                load(args.fit_model),
                load(args.fresh_pairs),
                base._load_many(args.fresh_shard),
                load(args.target_cache),
                champion_sha256=champion_sha256,
            ),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
