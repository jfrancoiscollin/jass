#!/usr/bin/env python3
"""Mechanical compatibility repair for CLS-D historical draw/pentanomial sources.

The frozen 1568/1569 producer received max-plies/game-timeout/pattern identity on
its command line but did not serialize those fields, nor search-wall telemetry,
into force-native.json.  This module authenticates exactly the fields that the
frozen producer actually serialized.  Identity is still fail-closed through the
historical scientific summaries and exact file sizes.  Missing telemetry is
reported as unavailable; it is never reconstructed or invented.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np

from jobs.tools import cls_draw_pentanomial_throughput_stage as legacy
from jobs.tools import cls_depth_growth_stage as base

SCHEMA = legacy.SCHEMA
REHEARSAL_TERMINAL = legacy.REHEARSAL_TERMINAL
PRODUCTION_TERMINAL = legacy.PRODUCTION_TERMINAL
TECHNICAL_TERMINAL = legacy.TECHNICAL_TERMINAL
StageError = legacy.StageError

UNSERIALIZED_LEGACY_FIELDS = (
    "max_plies",
    "game_timeout",
    "pattern_a_sha256",
    "pattern_b_sha256",
)
THROUGHPUT_STATUS = "UNAVAILABLE_LEGACY_SOURCE_NO_SEARCH_WALL_TELEMETRY"


def validate_native(raw: dict, *, source_seed: int, expected_size: int, path: Path) -> tuple[np.ndarray, dict]:
    """Validate the exact schema emitted by frozen run_jass_gate_bounded.py."""
    if path.stat().st_size != expected_size:
        raise StageError(f"source_size_drift:{path.name}:{path.stat().st_size}")

    w = int(raw.get("wins_a", -1))
    d = int(raw.get("draws", -1))
    l = int(raw.get("wins_b", -1))
    if raw.get("complete") is not True or int(raw.get("n", -1)) != legacy.GAMES_PER_POOL:
        raise StageError("source_wdl_shape_drift")
    if w + d + l != legacy.GAMES_PER_POOL:
        raise StageError("source_wdl_shape_drift")
    if int(raw.get("pairs", -1)) != 1 or int(raw.get("nshards", -1)) != 8:
        raise StageError("source_pair_shard_drift")
    if int(raw.get("max_parallel", -1)) != legacy.MAX_PARALLEL:
        raise StageError("source_parallelism_drift")
    if not math.isclose(float(raw.get("movetime", -1)), legacy.MOVETIME_SECONDS, rel_tol=0.0, abs_tol=1e-12):
        raise StageError("source_movetime_drift")
    if raw.get("depth") is not None:
        raise StageError("native_source_depth_must_be_null")

    # Exact frozen producer schema: these invocation fields were never emitted.
    present = [name for name in UNSERIALIZED_LEGACY_FIELDS if name in raw]
    if present:
        raise StageError("legacy_serialization_contract_drift:" + ",".join(present))

    paired = raw.get("paired_opening")
    if not isinstance(paired, dict):
        raise StageError("paired_opening_missing")
    if paired.get("method") != "paired_colour_opening_cluster_bootstrap":
        raise StageError("paired_method_drift")
    if int(paired.get("n_openings", -1)) != legacy.OPENINGS_PER_POOL:
        raise StageError("paired_opening_shape_drift")
    if int(paired.get("games_per_opening", -1)) != 2:
        raise StageError("paired_opening_shape_drift")
    if int(paired.get("bootstrap_samples", -1)) != 200000 or int(paired.get("seed", -1)) != source_seed:
        raise StageError("source_bootstrap_drift")
    if int(paired.get("error_draws", -1)) != 0:
        raise StageError("historical_native_technical_errors")
    if "telemetry" in paired:
        raise StageError("legacy_serialization_contract_drift:telemetry")

    scores = np.asarray(paired.get("per_opening_scores", []), dtype=np.float64)
    if scores.shape != (legacy.OPENINGS_PER_POOL,):
        raise StageError(f"paired_score_shape_drift:{scores.shape}")
    counts = legacy.canonical_counts(scores)
    rate = (w + 0.5 * d) / legacy.GAMES_PER_POOL
    if not math.isclose(float(raw.get("rate", rate)), rate, rel_tol=0.0, abs_tol=1e-6):
        raise StageError("raw_rate_drift")
    if not math.isclose(float(paired.get("rate", -1)), rate, rel_tol=0.0, abs_tol=1e-12):
        raise StageError("paired_rate_drift")
    if not math.isclose(float(scores.mean()), rate, rel_tol=0.0, abs_tol=1e-12):
        raise StageError("pair_mean_rate_drift")

    return scores, {
        "wins": w,
        "draws": d,
        "losses": l,
        "games": legacy.GAMES_PER_POOL,
        "pairs": legacy.PAIRS_PER_POOL,
        "score_rate": rate,
        "draw_rate": d / legacy.GAMES_PER_POOL,
        "pentanomial_counts": counts,
        "pair_score_variance_normalized": float(np.var(scores)),
        "pair_points_variance": float(np.var(scores * 2.0)),
        "throughput": {
            "primary_native_search_wall_telemetry_available": False,
            "status": THROUGHPUT_STATUS,
            "cpx62_search_capacity_pairs_per_hour": None,
        },
    }


def authenticate_sources(work: Path, artifacts: Path) -> tuple[dict, dict]:
    roots: list[Path] = []
    specs = (
        (legacy.POOL1_PREFIX, legacy.POOL1_JOB, legacy.POOL1_ATTEMPT),
        (legacy.POOL2_PREFIX, legacy.POOL2_JOB, legacy.POOL2_ATTEMPT),
    )
    for idx, (prefix, job, attempt) in enumerate(specs, start=1):
        out = work / f"pool{idx}"
        base.fetch_completed(
            prefix,
            job=job,
            attempt=attempt,
            code=legacy.SOURCE_CODE,
            mappings=[
                ("artefacts/force/force-native.json", "force-native.json"),
                ("artefacts/scientific-summary.json", "scientific-summary.json"),
            ],
            out_dir=out,
            report=work / f"verified-pool{idx}.json",
        )
        roots.append(out)

    summaries = [legacy.read_json(root / "scientific-summary.json") for root in roots]
    if summaries[0].get("schema") != "jass.l3_tb_policy_move_ordering_force_pool1.v1":
        raise StageError("pool1_summary_schema_drift")
    if summaries[1].get("schema") != "jass.l3_tb_policy_move_ordering_force_pool2.v1":
        raise StageError("pool2_summary_schema_drift")
    for payload in summaries:
        if payload.get("code_sha") != legacy.SOURCE_CODE:
            raise StageError("source_identity_drift")
        if payload.get("curriculum_raw_sha256") != legacy.CURRICULUM_SHA:
            raise StageError("source_identity_drift")
        if payload.get("packed_policy_sha256") != legacy.POLICY_SHA:
            raise StageError("source_policy_drift")
        if int(payload.get("fits", -1)) != 0 or int(payload.get("new_selfplay", -1)) != 0:
            raise StageError("source_effect_boundary_drift")
        if payload.get("promotion_authorized") is not False or payload.get("automatic_promotion") is not False:
            raise StageError("source_promotion_boundary_drift")
    if int(summaries[0].get("strength_games", -1)) != 12000:
        raise StageError("pool1_strength_game_count_drift")
    if int(summaries[1].get("pool2_strength_games", -1)) != 12000:
        raise StageError("pool2_strength_game_count_drift")
    if int(summaries[1].get("campaign_strength_games", -1)) != legacy.SOURCE_CAMPAIGN_STRENGTH_GAMES:
        raise StageError("pool2_strength_game_count_drift")

    native: list[dict] = []
    hashes: list[str] = []
    for idx, root in enumerate(roots):
        path = root / "force-native.json"
        scores, summary = validate_native(
            legacy.read_json(path),
            source_seed=legacy.SOURCE_BOOTSTRAP_SEEDS[idx],
            expected_size=legacy.SOURCE_NATIVE_FILE_SIZES[idx],
            path=path,
        )
        native.append({"scores": scores, "summary": summary})
        hashes.append(base.sha_file(path))

    auth = {
        "schema": "jass.cls_draw_pentanomial_throughput_source_authentication.v2",
        "authenticated": True,
        "legacy_producer_schema": "run_jass_gate_bounded.py@146f3464",
        "legacy_unserialized_invocation_fields": list(UNSERIALIZED_LEGACY_FIELDS),
        "native_search_wall_telemetry_available": False,
        "sources": [
            {"job_id": legacy.POOL1_JOB, "attempt_id": legacy.POOL1_ATTEMPT, "code_sha": legacy.SOURCE_CODE,
             "native_force_sha256": hashes[0], "native_force_size_bytes": legacy.SOURCE_NATIVE_FILE_SIZES[0],
             "source_bootstrap_seed": legacy.SOURCE_BOOTSTRAP_SEEDS[0]},
            {"job_id": legacy.POOL2_JOB, "attempt_id": legacy.POOL2_ATTEMPT, "code_sha": legacy.SOURCE_CODE,
             "native_force_sha256": hashes[1], "native_force_size_bytes": legacy.SOURCE_NATIVE_FILE_SIZES[1],
             "source_bootstrap_seed": legacy.SOURCE_BOOTSTRAP_SEEDS[1]},
        ],
        "curriculum_sha256": legacy.CURRICULUM_SHA,
        "policy_sha256": legacy.POLICY_SHA,
        "historical_campaign_strength_games": legacy.SOURCE_CAMPAIGN_STRENGTH_GAMES,
        "historical_native_games_consumed": legacy.NATIVE_GAMES,
        "historical_native_pairs_consumed": legacy.NATIVE_PAIRS,
        "new_strength_games": 0,
        "target_reads": 0,
        "fits": 0,
        "alpha_spent": 0,
    }
    base.atomic_write(artifacts / "source-authentication.json", base.canonical_json(auth))
    return native[0], native[1]


def build_diagnostic(pool1: dict, pool2: dict) -> tuple[dict, dict]:
    p1, p2 = pool1["summary"], pool2["summary"]
    scores = np.concatenate([pool1["scores"], pool2["scores"]])
    w = p1["wins"] + p2["wins"]
    d = p1["draws"] + p2["draws"]
    l = p1["losses"] + p2["losses"]
    if w + d + l != legacy.NATIVE_GAMES or scores.shape != (legacy.NATIVE_PAIRS,):
        raise StageError("pooled_shape_drift")

    mixed_wall = legacy.POOL1_STAGE_WALL_SECONDS + legacy.POOL2_STAGE_WALL_SECONDS
    throughput = {
        "primary_native_search_wall_telemetry_available": False,
        "status": THROUGHPUT_STATUS,
        "cpx62_search_capacity_pairs_per_hour": None,
        "scope": "native_0.1s_per_move_search_time_only",
    }
    diagnostic = {
        "schema": SCHEMA,
        "historical_read_only": True,
        "native_time_control": {
            "movetime_seconds_per_move": legacy.MOVETIME_SECONDS,
            "max_plies": legacy.MAX_PLIES,
            "game_timeout_seconds": legacy.GAME_TIMEOUT_SECONDS,
            "pairs_per_opening": 1,
            "openings_per_pool": legacy.OPENINGS_PER_POOL,
            "pools": 2,
            "invocation_contract_authenticated_from_frozen_control_job": True,
            "invocation_fields_not_serialized_in_native_payload": list(UNSERIALIZED_LEGACY_FIELDS),
        },
        "pool1": p1,
        "pool2": p2,
        "pooled": {
            "wins": w,
            "draws": d,
            "losses": l,
            "games": legacy.NATIVE_GAMES,
            "pairs": legacy.NATIVE_PAIRS,
            "score_rate": (w + 0.5 * d) / legacy.NATIVE_GAMES,
            "draw_rate": d / legacy.NATIVE_GAMES,
            "pentanomial_counts": legacy.canonical_counts(scores),
            "pair_score_variance_normalized": float(np.var(scores)),
            "pair_points_variance": float(np.var(scores * 2.0)),
            "technical_error_draws": 0,
        },
        "throughput": throughput,
        "conservative_mixed_stage_context": {
            "scope": "historical_full_stage_all_views_including_build_auth_profile_and_q00",
            "pairs_all_views": legacy.SOURCE_TOTAL_PAIRS_ALL_VIEWS,
            "wall_seconds": mixed_wall,
            "pairs_per_hour": legacy.SOURCE_TOTAL_PAIRS_ALL_VIEWS * 3600.0 / mixed_wall,
            "not_primary_native_throughput": True,
        },
        "pentanomial_available_for_future_strength_gate": True,
        "future_sprt_sizing_inputs_ready": False,
        "throughput_limitation": THROUGHPUT_STATUS,
        "sprt_boundaries_frozen_here": False,
        "final_bottleneck_classification": None,
    }
    return diagnostic, legacy.pooled_bootstrap(pool1["scores"], pool2["scores"])


def manifest_for(artifacts: Path) -> dict:
    names = [
        "draw-pentanomial-throughput.json",
        "bootstrap.json",
        "source-authentication.json",
        "RESULTS.md",
        "scientific-summary.json",
    ]
    return {
        "schema": "jass.cls_draw_pentanomial_throughput_manifest.v2",
        "files": {name: base.sha_file(artifacts / name) for name in names},
    }


def run_stage(work: Path, artifacts: Path) -> dict:
    mode = os.environ.get("LAUNCH_MODE", "")
    if mode not in {"rehearsal", "production"}:
        raise StageError("LAUNCH_MODE must be rehearsal or production")
    work.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    p1, p2 = authenticate_sources(work, artifacts)
    diagnostic, boot = build_diagnostic(p1, p2)
    base.atomic_write(artifacts / "draw-pentanomial-throughput.json", base.canonical_json(diagnostic))
    base.atomic_write(artifacts / "bootstrap.json", base.canonical_json(boot))

    pooled = diagnostic["pooled"]
    mixed = diagnostic["conservative_mixed_stage_context"]
    results = (
        "# CLS-D draw / pentanomial / throughput diagnostic V1\n\n"
        f"- mode: `{mode}`\n"
        f"- native historical games/pairs: {legacy.NATIVE_GAMES}/{legacy.NATIVE_PAIRS}\n"
        f"- draw rate: {pooled['draw_rate']:.6f}\n"
        f"- pentanomial counts: {pooled['pentanomial_counts']}\n"
        f"- pair-score variance (normalized): {pooled['pair_score_variance_normalized']:.8f}\n"
        f"- pooled score rate: {pooled['score_rate']:.6f}; bootstrap 95% "
        f"[{boot['score_rate']['q025']:.6f}, {boot['score_rate']['q975']:.6f}]\n"
        f"- native search-only throughput: unavailable ({THROUGHPUT_STATUS}); legacy producer did not serialize search-wall telemetry.\n"
        f"- conservative all-view full-stage context: {mixed['pairs_per_hour']:.2f} pairs/hour; explicitly non-primary.\n"
        "- no new games, search, target read, fit, alpha, promotion or bake occurred.\n"
        "- this stage does not publish the final SEARCH / DECISION-EVAL / COST / mixed classification.\n"
    )
    base.atomic_write(artifacts / "RESULTS.md", results.encode())

    summary = {
        "schema": SCHEMA,
        "state": "completed",
        "terminal": REHEARSAL_TERMINAL if mode == "rehearsal" else PRODUCTION_TERMINAL,
        "mode": mode,
        "diagnostic_only": True,
        "scientific_verdict": None,
        "classification": None,
        "historical_source_strength_games": legacy.SOURCE_CAMPAIGN_STRENGTH_GAMES,
        "historical_native_games_consumed": legacy.NATIVE_GAMES,
        "historical_native_pairs_consumed": legacy.NATIVE_PAIRS,
        "draw_rate": pooled["draw_rate"],
        "pentanomial_counts": pooled["pentanomial_counts"],
        "pair_score_variance_normalized": pooled["pair_score_variance_normalized"],
        "native_search_throughput_available": False,
        "cpx62_search_capacity_pairs_per_hour": None,
        "throughput_limitation": THROUGHPUT_STATUS,
        "conservative_mixed_stage_pairs_per_hour": mixed["pairs_per_hour"],
        "bootstrap_replicates": legacy.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": legacy.BOOTSTRAP_SEED,
        "pentanomial_available_for_future_strength_gate": True,
        "future_sprt_sizing_inputs_ready": False,
        "sprt_boundaries_frozen_here": False,
        "next_stage": "QUEUE_EXACT_PRODUCTION_SAME_COMMON_SPEC" if mode == "rehearsal" else "PUBLISH_CLS_BOTTLENECK_CLASSIFICATION",
        "target_reads": 0,
        "candidate_reads": 0,
        "control_evaluations": 0,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "fits": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
    }
    base.atomic_write(artifacts / "scientific-summary.json", base.canonical_json(summary))
    base.atomic_write(artifacts / "manifest.json", base.canonical_json(manifest_for(artifacts)))
    return summary
