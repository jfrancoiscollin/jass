#!/usr/bin/env python3
"""Read-only CLS-D draw/pentanomial/throughput diagnostic over historical CPX62 paired gates."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys

import numpy as np

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import cls_depth_growth_stage as base  # noqa: E402

SCHEMA = "jass.cls_draw_pentanomial_throughput.v1"
REHEARSAL_TERMINAL = "CLS_DRAW_PENTANOMIAL_THROUGHPUT_REHEARSAL_READY_V1"
PRODUCTION_TERMINAL = "CLS_DRAW_PENTANOMIAL_THROUGHPUT_DIAGNOSTIC_COMPLETE_V1"
TECHNICAL_TERMINAL = "CLS_DRAW_PENTANOMIAL_THROUGHPUT_TECHNICAL_FAILURE_V1"

POOL1_JOB = "cpx62-1568-l3-tb-policy-move-ordering-force-pool1-v1"
POOL1_ATTEMPT = "20260825T234756Z-146f3464"
POOL2_JOB = "cpx62-1569-l3-tb-policy-move-ordering-force-pool2-v1"
POOL2_ATTEMPT = "20260826T061618Z-146f3464"
SOURCE_CODE = "146f34647dae489c6d2817748fd767aa65b93d87"
POOL1_PREFIX = f"r2:jass-data/runs/{POOL1_JOB}/{POOL1_ATTEMPT}"
POOL2_PREFIX = f"r2:jass-data/runs/{POOL2_JOB}/{POOL2_ATTEMPT}"

CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
POLICY_SHA = "f894bb12778c59d85e666163508c2ef51ad080c9eb37667719c2926f2404d3c4"

OPENINGS_PER_POOL = 3000
PAIRS_PER_POOL = 3000
GAMES_PER_POOL = 6000
NATIVE_GAMES = 12000
NATIVE_PAIRS = 6000
SOURCE_CAMPAIGN_STRENGTH_GAMES = 24000
SOURCE_NATIVE_FILE_SIZES = (36739, 36775)
SOURCE_BOOTSTRAP_SEEDS = (2026083011, 2026083021)
MOVETIME_SECONDS = 0.1
MAX_PARALLEL = 8
MAX_PLIES = 160
GAME_TIMEOUT_SECONDS = 180.0
POOL1_STAGE_WALL_SECONDS = 5364.0
POOL2_STAGE_WALL_SECONDS = 5588.0
SOURCE_TOTAL_PAIRS_ALL_VIEWS = 12000
BOOTSTRAP_REPLICATES = 100_000
BOOTSTRAP_SEED = 2026091005
PAIR_SCORE_GRID = (0.0, 0.5, 1.0, 1.5, 2.0)


class StageError(RuntimeError):
    pass


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StageError(f"not_object:{path.name}")
    return value


def canonical_counts(scores: np.ndarray) -> dict[str, int]:
    """Count 0/0.5/1/1.5/2 point outcomes from normalized paired scores."""
    points = np.asarray(scores, dtype=np.float64) * 2.0
    allowed = np.asarray(PAIR_SCORE_GRID, dtype=np.float64)
    if points.ndim != 1 or not np.all(np.isin(points, allowed)):
        raise StageError("pentanomial_score_grid_drift")
    return {
        "0": int(np.sum(points == 0.0)),
        "0.5": int(np.sum(points == 0.5)),
        "1": int(np.sum(points == 1.0)),
        "1.5": int(np.sum(points == 1.5)),
        "2": int(np.sum(points == 2.0)),
    }


def search_throughput(pair_count: int, max_parallel: int, telemetry: dict) -> dict[str, float]:
    """Convert aggregate engine search wall to an 8-way CPX62 search-capacity estimate."""
    try:
        a = float(telemetry["a"]["wall_seconds"])
        b = float(telemetry["b"]["wall_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise StageError("telemetry_wall_seconds_missing") from exc
    total = a + b
    if pair_count <= 0 or max_parallel <= 0 or total <= 0:
        raise StageError("invalid_throughput_inputs")
    return {
        "aggregate_engine_search_wall_seconds": total,
        "serial_engine_search_seconds_per_pair": total / pair_count,
        "parallelized_search_wall_seconds_estimate": total / max_parallel,
        "cpx62_search_capacity_pairs_per_hour": pair_count * max_parallel * 3600.0 / total,
    }


def validate_native(raw: dict, *, source_seed: int, expected_size: int, path: Path) -> tuple[np.ndarray, dict]:
    if path.stat().st_size != expected_size:
        raise StageError(f"source_size_drift:{path.name}:{path.stat().st_size}")
    w, d, l = int(raw.get("wins_a", -1)), int(raw.get("draws", -1)), int(raw.get("wins_b", -1))
    if raw.get("complete") is not True or int(raw.get("n", -1)) != GAMES_PER_POOL or w + d + l != GAMES_PER_POOL:
        raise StageError("source_wdl_shape_drift")
    if int(raw.get("pairs", -1)) != 1 or int(raw.get("nshards", -1)) != 8:
        raise StageError("source_pair_shard_drift")
    if int(raw.get("max_parallel", -1)) != MAX_PARALLEL:
        raise StageError("source_parallelism_drift")
    if int(raw.get("max_plies", -1)) != MAX_PLIES:
        raise StageError("source_max_plies_drift")
    if not math.isclose(float(raw.get("movetime", -1)), MOVETIME_SECONDS, rel_tol=0.0, abs_tol=1e-12):
        raise StageError("source_movetime_drift")
    if raw.get("depth") is not None:
        raise StageError("native_source_depth_must_be_null")
    if not math.isclose(float(raw.get("game_timeout", -1)), GAME_TIMEOUT_SECONDS, rel_tol=0.0, abs_tol=1e-12):
        raise StageError("source_game_timeout_drift")
    if raw.get("pattern_a_sha256") != CURRICULUM_SHA or raw.get("pattern_b_sha256") != CURRICULUM_SHA:
        raise StageError("source_curriculum_drift")

    paired = raw.get("paired_opening")
    if not isinstance(paired, dict):
        raise StageError("paired_opening_missing")
    if paired.get("method") != "paired_colour_opening_cluster_bootstrap":
        raise StageError("paired_method_drift")
    if int(paired.get("n_openings", -1)) != OPENINGS_PER_POOL or int(paired.get("games_per_opening", -1)) != 2:
        raise StageError("paired_opening_shape_drift")
    if int(paired.get("bootstrap_samples", -1)) != 200000 or int(paired.get("seed", -1)) != source_seed:
        raise StageError("source_bootstrap_drift")
    if int(paired.get("error_draws", -1)) != 0:
        raise StageError("historical_native_technical_errors")

    scores = np.asarray(paired.get("per_opening_scores", []), dtype=np.float64)
    if scores.shape != (OPENINGS_PER_POOL,):
        raise StageError(f"paired_score_shape_drift:{scores.shape}")
    counts = canonical_counts(scores)
    rate = (w + 0.5 * d) / GAMES_PER_POOL
    if not math.isclose(float(raw.get("rate", rate)), rate, rel_tol=0.0, abs_tol=1e-6):
        raise StageError("raw_rate_drift")
    if not math.isclose(float(paired.get("rate", -1)), rate, rel_tol=0.0, abs_tol=1e-12):
        raise StageError("paired_rate_drift")
    if not math.isclose(float(scores.mean()), rate, rel_tol=0.0, abs_tol=1e-12):
        raise StageError("pair_mean_rate_drift")

    throughput = search_throughput(PAIRS_PER_POOL, MAX_PARALLEL, paired.get("telemetry", {}))
    return scores, {
        "wins": w,
        "draws": d,
        "losses": l,
        "games": GAMES_PER_POOL,
        "pairs": PAIRS_PER_POOL,
        "score_rate": rate,
        "draw_rate": d / GAMES_PER_POOL,
        "pentanomial_counts": counts,
        "pair_score_variance_normalized": float(np.var(scores)),
        "pair_points_variance": float(np.var(scores * 2.0)),
        "throughput": throughput,
    }


def authenticate_sources(work: Path, artifacts: Path) -> tuple[dict, dict]:
    roots: list[Path] = []
    for idx, (prefix, job, attempt) in enumerate((
        (POOL1_PREFIX, POOL1_JOB, POOL1_ATTEMPT),
        (POOL2_PREFIX, POOL2_JOB, POOL2_ATTEMPT),
    ), start=1):
        out = work / f"pool{idx}"
        base.fetch_completed(
            prefix, job=job, attempt=attempt, code=SOURCE_CODE,
            mappings=[
                ("artefacts/force/force-native.json", "force-native.json"),
                ("artefacts/scientific-summary.json", "scientific-summary.json"),
            ],
            out_dir=out, report=work / f"verified-pool{idx}.json",
        )
        roots.append(out)

    p1sum, p2sum = read_json(roots[0] / "scientific-summary.json"), read_json(roots[1] / "scientific-summary.json")
    if p1sum.get("schema") != "jass.l3_tb_policy_move_ordering_force_pool1.v1":
        raise StageError("pool1_summary_schema_drift")
    if p2sum.get("schema") != "jass.l3_tb_policy_move_ordering_force_pool2.v1":
        raise StageError("pool2_summary_schema_drift")
    for payload in (p1sum, p2sum):
        if payload.get("code_sha") != SOURCE_CODE or payload.get("curriculum_raw_sha256") != CURRICULUM_SHA:
            raise StageError("source_identity_drift")
        if payload.get("packed_policy_sha256") != POLICY_SHA:
            raise StageError("source_policy_drift")
        if int(payload.get("fits", -1)) != 0 or int(payload.get("new_selfplay", -1)) != 0:
            raise StageError("source_effect_boundary_drift")
        if payload.get("promotion_authorized") is not False or payload.get("automatic_promotion") is not False:
            raise StageError("source_promotion_boundary_drift")
    if int(p1sum.get("strength_games", -1)) != 12000:
        raise StageError("pool1_strength_game_count_drift")
    if int(p2sum.get("pool2_strength_games", -1)) != 12000 or int(p2sum.get("campaign_strength_games", -1)) != SOURCE_CAMPAIGN_STRENGTH_GAMES:
        raise StageError("pool2_strength_game_count_drift")

    native: list[dict] = []
    hashes: list[str] = []
    for idx, root in enumerate(roots):
        path = root / "force-native.json"
        raw = read_json(path)
        scores, summary = validate_native(
            raw, source_seed=SOURCE_BOOTSTRAP_SEEDS[idx],
            expected_size=SOURCE_NATIVE_FILE_SIZES[idx], path=path,
        )
        native.append({"scores": scores, "summary": summary})
        hashes.append(base.sha_file(path))

    auth = {
        "schema": "jass.cls_draw_pentanomial_throughput_source_authentication.v1",
        "authenticated": True,
        "sources": [
            {"job_id": POOL1_JOB, "attempt_id": POOL1_ATTEMPT, "code_sha": SOURCE_CODE,
             "native_force_sha256": hashes[0], "native_force_size_bytes": SOURCE_NATIVE_FILE_SIZES[0],
             "source_bootstrap_seed": SOURCE_BOOTSTRAP_SEEDS[0]},
            {"job_id": POOL2_JOB, "attempt_id": POOL2_ATTEMPT, "code_sha": SOURCE_CODE,
             "native_force_sha256": hashes[1], "native_force_size_bytes": SOURCE_NATIVE_FILE_SIZES[1],
             "source_bootstrap_seed": SOURCE_BOOTSTRAP_SEEDS[1]},
        ],
        "curriculum_sha256": CURRICULUM_SHA,
        "policy_sha256": POLICY_SHA,
        "historical_campaign_strength_games": SOURCE_CAMPAIGN_STRENGTH_GAMES,
        "historical_native_games_consumed": NATIVE_GAMES,
        "historical_native_pairs_consumed": NATIVE_PAIRS,
        "new_strength_games": 0,
        "target_reads": 0,
        "fits": 0,
        "alpha_spent": 0,
    }
    base.atomic_write(artifacts / "source-authentication.json", base.canonical_json(auth))
    return native[0], native[1]


def pooled_bootstrap(a: np.ndarray, b: np.ndarray) -> dict:
    if a.shape != (OPENINGS_PER_POOL,) or b.shape != (OPENINGS_PER_POOL,):
        raise StageError("bootstrap_source_shape_drift")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    samples = np.empty(BOOTSTRAP_REPLICATES, dtype=np.float64)
    chunk = 250
    for start in range(0, BOOTSTRAP_REPLICATES, chunk):
        stop = min(start + chunk, BOOTSTRAP_REPLICATES)
        take = stop - start
        ia = rng.integers(0, OPENINGS_PER_POOL, size=(take, OPENINGS_PER_POOL))
        ib = rng.integers(0, OPENINGS_PER_POOL, size=(take, OPENINGS_PER_POOL))
        samples[start:stop] = 0.5 * (a[ia].mean(axis=1) + b[ib].mean(axis=1))
    q = np.quantile(samples, [0.025, 0.5, 0.975])
    return {
        "schema": "jass.cls_draw_pentanomial_throughput_bootstrap.v1",
        "unit": "paired_opening",
        "pool_stratified": True,
        "pool_quotas_fixed": {"pool1": OPENINGS_PER_POOL, "pool2": OPENINGS_PER_POOL},
        "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
        "score_rate": {"q025": float(q[0]), "median": float(q[1]), "q975": float(q[2])},
        "probability_rate_gt_half": float(np.mean(samples > 0.5)),
    }


def build_diagnostic(pool1: dict, pool2: dict) -> tuple[dict, dict]:
    p1, p2 = pool1["summary"], pool2["summary"]
    scores = np.concatenate([pool1["scores"], pool2["scores"]])
    w, d, l = p1["wins"] + p2["wins"], p1["draws"] + p2["draws"], p1["losses"] + p2["losses"]
    if w + d + l != NATIVE_GAMES or scores.shape != (NATIVE_PAIRS,):
        raise StageError("pooled_shape_drift")
    telemetry_total = p1["throughput"]["aggregate_engine_search_wall_seconds"] + p2["throughput"]["aggregate_engine_search_wall_seconds"]
    pooled_throughput = {
        "aggregate_engine_search_wall_seconds": telemetry_total,
        "serial_engine_search_seconds_per_pair": telemetry_total / NATIVE_PAIRS,
        "parallelized_search_wall_seconds_estimate": telemetry_total / MAX_PARALLEL,
        "cpx62_search_capacity_pairs_per_hour": NATIVE_PAIRS * MAX_PARALLEL * 3600.0 / telemetry_total,
        "max_parallel": MAX_PARALLEL,
        "scope": "native_0.1s_per_move_search_time_only",
    }
    mixed_stage_wall = POOL1_STAGE_WALL_SECONDS + POOL2_STAGE_WALL_SECONDS
    diagnostic = {
        "schema": SCHEMA,
        "historical_read_only": True,
        "native_time_control": {"movetime_seconds_per_move": MOVETIME_SECONDS, "max_plies": MAX_PLIES,
                                "game_timeout_seconds": GAME_TIMEOUT_SECONDS, "pairs_per_opening": 1,
                                "openings_per_pool": OPENINGS_PER_POOL, "pools": 2},
        "per_pool": {"pool1": p1, "pool2": p2},
        "pooled": {
            "games": NATIVE_GAMES, "pairs": NATIVE_PAIRS, "wins": w, "draws": d, "losses": l,
            "score_rate": (w + 0.5 * d) / NATIVE_GAMES, "draw_rate": d / NATIVE_GAMES,
            "pentanomial_counts": canonical_counts(scores),
            "pair_score_variance_normalized": float(np.var(scores)),
            "pair_points_variance": float(np.var(scores * 2.0)), "technical_error_draws": 0,
        },
        "throughput": pooled_throughput,
        "conservative_mixed_stage_context": {
            "scope": "historical_full_stage_all_views_including_build_auth_profile_and_q00",
            "pairs_all_views": SOURCE_TOTAL_PAIRS_ALL_VIEWS, "wall_seconds": mixed_stage_wall,
            "pairs_per_hour": SOURCE_TOTAL_PAIRS_ALL_VIEWS * 3600.0 / mixed_stage_wall,
            "not_primary_native_throughput": True,
        },
        "pentanomial_available_for_future_strength_gate": True,
        "future_sprt_sizing_inputs_ready": True,
        "sprt_boundaries_frozen_here": False,
        "final_bottleneck_classification": None,
    }
    return diagnostic, pooled_bootstrap(pool1["scores"], pool2["scores"])


def manifest_for(artifacts: Path) -> dict:
    names = ["draw-pentanomial-throughput.json", "bootstrap.json", "source-authentication.json", "RESULTS.md", "scientific-summary.json"]
    return {"schema": "jass.cls_draw_pentanomial_throughput_manifest.v1",
            "files": {name: base.sha_file(artifacts / name) for name in names}}


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

    pooled, throughput = diagnostic["pooled"], diagnostic["throughput"]
    counts = pooled["pentanomial_counts"]
    results = (
        "# CLS-D draw / pentanomial / throughput diagnostic V1\n\n"
        f"- mode: `{mode}`\n"
        f"- historical native games: {NATIVE_GAMES}; paired openings: {NATIVE_PAIRS}\n"
        f"- raw draw rate: {pooled['draw_rate']:.6f}\n"
        f"- pentanomial counts [0,0.5,1,1.5,2]: {[counts[k] for k in ('0','0.5','1','1.5','2')]}\n"
        f"- pair-score variance (normalized): {pooled['pair_score_variance_normalized']:.8f}\n"
        f"- pooled score rate: {pooled['score_rate']:.6f}; bootstrap 95% "
        f"[{boot['score_rate']['q025']:.6f}, {boot['score_rate']['q975']:.6f}]\n"
        f"- CPX62 native search-capacity estimate: {throughput['cpx62_search_capacity_pairs_per_hour']:.2f} pairs/hour "
        "(8-way, search time only)\n"
        "- no new games, search, target read, fit, alpha, promotion or bake occurred.\n"
        "- this stage does not publish the final SEARCH / DECISION-EVAL / COST / mixed classification.\n"
    )
    base.atomic_write(artifacts / "RESULTS.md", results.encode())
    summary = {
        "schema": SCHEMA, "state": "completed",
        "terminal": REHEARSAL_TERMINAL if mode == "rehearsal" else PRODUCTION_TERMINAL,
        "mode": mode, "diagnostic_only": True, "scientific_verdict": None, "classification": None,
        "historical_source_strength_games": SOURCE_CAMPAIGN_STRENGTH_GAMES,
        "historical_native_games_consumed": NATIVE_GAMES, "historical_native_pairs_consumed": NATIVE_PAIRS,
        "draw_rate": pooled["draw_rate"], "pentanomial_counts": counts,
        "pair_score_variance_normalized": pooled["pair_score_variance_normalized"],
        "cpx62_search_capacity_pairs_per_hour": throughput["cpx62_search_capacity_pairs_per_hour"],
        "bootstrap_replicates": BOOTSTRAP_REPLICATES, "bootstrap_seed": BOOTSTRAP_SEED,
        "pentanomial_available_for_future_strength_gate": True, "future_sprt_sizing_inputs_ready": True,
        "sprt_boundaries_frozen_here": False,
        "next_stage": "QUEUE_EXACT_PRODUCTION_SAME_COMMON_SPEC" if mode == "rehearsal" else "PUBLISH_CLS_BOTTLENECK_CLASSIFICATION",
        "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
        "new_jass_searches": 0, "new_scan_searches": 0, "fits": 0, "strength_games": 0,
        "selfplay_games": 0, "alpha_spent": 0, "promotions": 0, "bakes": 0,
    }
    base.atomic_write(artifacts / "scientific-summary.json", base.canonical_json(summary))
    base.atomic_write(artifacts / "manifest.json", base.canonical_json(manifest_for(artifacts)))
    return summary


def main() -> int:
    artifacts = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    try:
        summary = run_stage(result / "cls-draw-pentanomial-throughput-work", artifacts)
    except BaseException as exc:
        failure = {
            "schema": SCHEMA, "state": "failed", "terminal": TECHNICAL_TERMINAL,
            "scientific_verdict": None, "classification": "TECHNICAL",
            "error_type": type(exc).__name__, "error": str(exc)[:2000],
            "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
            "new_jass_searches": 0, "new_scan_searches": 0, "fits": 0, "strength_games": 0,
            "selfplay_games": 0, "alpha_spent": 0, "promotions": 0, "bakes": 0,
        }
        artifacts.mkdir(parents=True, exist_ok=True)
        base.atomic_write(artifacts / "scientific-summary.json", base.canonical_json(failure))
        print(f"CLS draw/pentanomial/throughput TECHNICAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
