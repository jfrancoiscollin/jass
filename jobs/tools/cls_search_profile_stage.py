#!/usr/bin/env python3
"""Read-only CLS-D search-profile diagnostic over authenticated 2000 + 2008 outputs."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
from typing import Iterable

import numpy as np

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import cls_depth_growth_stage as base  # noqa: E402

SCHEMA = "jass.cls_search_profile.v1"
REHEARSAL_TERMINAL = "CLS_SEARCH_PROFILE_REHEARSAL_READY_V1"
PRODUCTION_TERMINAL = "CLS_SEARCH_PROFILE_DIAGNOSTIC_COMPLETE_V1"
TECHNICAL_TERMINAL = "CLS_SEARCH_PROFILE_TECHNICAL_FAILURE_V1"
DEPTH_JOB = "cpx62-2000-l3-cls-depth-growth-full-production-v2"
DEPTH_ATTEMPT = "20260916T083204Z-7a5f44ec"
DEPTH_CODE = "7a5f44ec1681c2471b1815f8767b4008b11e3a54"
DEPTH_RECEIPT = "3155272745b458af68e35de06bf6921b20fdf8639913287be6d71075e3349a42"
MIRROR_JOB = "cpx62-2008-l3-cls-mirror-scale-production-v3"
MIRROR_ATTEMPT = "20260916T161938Z-92984c1f"
MIRROR_CODE = "92984c1f8ac9563225f930c1c3d77b80e581e05d"
MIRROR_RECEIPT = "2ac13b1e61dffc7d73217a8daba111aed9028b7a006020d081ebd6aa3480b004"
DEPTH_PREFIX = f"r2:jass-data/runs/{DEPTH_JOB}/{DEPTH_ATTEMPT}"
MIRROR_PREFIX = f"r2:jass-data/runs/{MIRROR_JOB}/{MIRROR_ATTEMPT}"
COHORT_SHA = "478abc0fe2fe1fcd8c2157f532ba796745c645ff4f03dac8fd21c2ff851f137e"
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
ROOTS = 512
ROOTS_PER_PHASE = 128
BUDGETS = (5_000, 50_000, 200_000)
DEEP_BUDGET = 1_000_000
PHASES = ("P0", "P1", "P2", "P3")
BOOTSTRAP_REPLICATES = 100_000
BOOTSTRAP_SEED = 2026091004


class StageError(RuntimeError):
    pass


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StageError(f"not_object:{path.name}")
    return value


def numeric(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    if value in ("", "NA", None):
        raise StageError(f"missing_numeric:{key}")
    return float(value)


def safe_ratio(a: float, b: float) -> float:
    return a / b if b else 0.0


def summarize_jass(rows: list[dict[str, str]], *, deep: bool = False) -> dict[str, float]:
    if not rows:
        raise StageError("empty_jass_rows")
    nodes = sum(numeric(r, "nodes_observed") for r in rows)
    qnodes = sum(numeric(r, "qnodes") for r in rows)
    eval_calls = sum(numeric(r, "eval_calls") for r in rows)
    cutoffs = sum(numeric(r, "cutoffs") for r in rows)
    fm = sum(numeric(r, "first_move_cutoffs") for r in rows)
    pvs = sum(numeric(r, "pvs_researches") for r in rows)
    moves = sum(numeric(r, "moves_searched") for r in rows)
    nps = np.asarray([numeric(r, "nps") for r in rows], dtype=np.float64)
    depth = np.asarray([numeric(r, "completed_nominal_depth") for r in rows], dtype=np.float64)
    if deep:
        probes = sum(numeric(r, "tt_probes") for r in rows)
        hits = sum(numeric(r, "tt_hits") for r in rows)
        tt_hit = safe_ratio(hits, probes)
        wall_ms = sum(numeric(r, "wall_us") for r in rows) / 1000.0
    else:
        tt_hit = float(np.mean([numeric(r, "tt_hit_rate") for r in rows]))
        wall_ms = sum(numeric(r, "wall_ms") for r in rows)
    return {
        "rows": len(rows),
        "mean_nps": float(nps.mean()),
        "median_nps": float(np.median(nps)),
        "mean_completed_nominal_depth": float(depth.mean()),
        "median_completed_nominal_depth": float(np.median(depth)),
        "qnodes_per_node": safe_ratio(qnodes, nodes),
        "eval_calls_per_node": safe_ratio(eval_calls, nodes),
        "tt_hit_rate": tt_hit,
        "cutoffs_per_node": safe_ratio(cutoffs, nodes),
        "first_move_cutoff_share": safe_ratio(fm, cutoffs),
        "pvs_researches_per_move": safe_ratio(pvs, moves),
        "moves_searched_per_node": safe_ratio(moves, nodes),
        "wall_ms_sum": wall_ms,
    }


def summarize_scan(rows: list[dict[str, str]]) -> dict[str, float]:
    if not rows:
        raise StageError("empty_scan_rows")
    nps = np.asarray([numeric(r, "nps") for r in rows], dtype=np.float64)
    depth = np.asarray([numeric(r, "completed_nominal_depth") for r in rows], dtype=np.float64)
    return {
        "rows": len(rows),
        "mean_nps": float(nps.mean()),
        "median_nps": float(np.median(nps)),
        "mean_completed_nominal_depth": float(depth.mean()),
        "median_completed_nominal_depth": float(np.median(depth)),
        "wall_ms_sum": sum(numeric(r, "wall_ms") for r in rows),
        "internal_counters_available": False,
    }


def root_vector(jass: dict[str, str], scan: dict[str, str]) -> list[float]:
    jnps, snps = numeric(jass, "nps"), numeric(scan, "nps")
    if jnps <= 0 or snps <= 0:
        raise StageError("nonpositive_nps")
    nodes = numeric(jass, "nodes_observed")
    cutoffs = numeric(jass, "cutoffs")
    moves = numeric(jass, "moves_searched")
    return [
        math.log(jnps / snps),
        numeric(jass, "completed_nominal_depth") - numeric(scan, "completed_nominal_depth"),
        safe_ratio(numeric(jass, "qnodes"), nodes),
        safe_ratio(numeric(jass, "eval_calls"), nodes),
        numeric(jass, "tt_hit_rate"),
        safe_ratio(numeric(jass, "cutoffs"), nodes),
        safe_ratio(numeric(jass, "first_move_cutoffs"), cutoffs),
        safe_ratio(numeric(jass, "pvs_researches"), moves),
        safe_ratio(moves, nodes),
    ]


def bootstrap(vectors: dict[str, np.ndarray]) -> dict[str, object]:
    labels = []
    base_labels = [
        "log_nps_ratio_jass_scan", "completed_depth_delta_jass_scan", "qnodes_per_node",
        "eval_calls_per_node", "tt_hit_rate", "cutoffs_per_node", "first_move_cutoff_share",
        "pvs_researches_per_move", "moves_searched_per_node",
    ]
    for budget in BUDGETS:
        labels.extend(f"{name}_{budget}" for name in base_labels)
    samples = np.zeros((BOOTSTRAP_REPLICATES, len(labels)), dtype=np.float64)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    chunk = 1000
    for phase in PHASES:
        values = vectors[phase]
        if values.shape != (ROOTS_PER_PHASE, len(labels)):
            raise StageError(f"bootstrap_shape:{phase}:{values.shape}")
        for start in range(0, BOOTSTRAP_REPLICATES, chunk):
            stop = min(start + chunk, BOOTSTRAP_REPLICATES)
            idx = rng.integers(0, ROOTS_PER_PHASE, size=(stop - start, ROOTS_PER_PHASE))
            samples[start:stop] += values[idx].mean(axis=1) / len(PHASES)
    q = np.quantile(samples, [0.025, 0.5, 0.975], axis=0)
    return {
        "schema": "jass.cls_search_profile_bootstrap.v1",
        "unit": "root_id",
        "phase_stratified": True,
        "phase_quotas_fixed": {phase: ROOTS_PER_PHASE for phase in PHASES},
        "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
        "metrics": {label: {"q025": float(q[0, i]), "median": float(q[1, i]), "q975": float(q[2, i])}
                    for i, label in enumerate(labels)},
    }


def authenticate_sources(work: Path, artifacts: Path) -> tuple[Path, Path]:
    depth = work / "depth-2000"
    mirror = work / "mirror-2008"
    base.fetch_completed(
        DEPTH_PREFIX, job=DEPTH_JOB, attempt=DEPTH_ATTEMPT, code=DEPTH_CODE,
        mappings=[
            ("artefacts/per_root.tsv", "per_root.tsv"),
            ("artefacts/manifest.json", "manifest.json"),
            ("artefacts/scientific-summary.json", "scientific-summary.json"),
            ("artefacts/launch-receipt.json", "launch-receipt.json"),
            ("artefacts/root-selection.json", "root-selection.json"),
        ], out_dir=depth, report=work / "verified-depth-2000.json",
    )
    base.fetch_completed(
        MIRROR_PREFIX, job=MIRROR_JOB, attempt=MIRROR_ATTEMPT, code=MIRROR_CODE,
        mappings=[
            ("artefacts/deep_reference.tsv", "deep_reference.tsv"),
            ("artefacts/manifest.json", "manifest.json"),
            ("artefacts/scientific-summary.json", "scientific-summary.json"),
            ("artefacts/launch-receipt.json", "launch-receipt.json"),
            ("artefacts/root-selection.json", "root-selection.json"),
        ], out_dir=mirror, report=work / "verified-mirror-2008.json",
    )
    if base.sha_file(depth / "launch-receipt.json") != DEPTH_RECEIPT:
        raise StageError("depth_receipt_drift")
    if base.sha_file(mirror / "launch-receipt.json") != MIRROR_RECEIPT:
        raise StageError("mirror_receipt_drift")
    dsum, msum = read_json(depth / "scientific-summary.json"), read_json(mirror / "scientific-summary.json")
    required_d = {
        "state": "completed", "terminal": "DEPTH_GROWTH_JASS_VS_SCAN_V2_COMPLETE",
        "mode": "production", "diagnostic_only": True, "roots": ROOTS,
        "roots_per_phase": ROOTS_PER_PHASE, "target_reads": 0, "candidate_reads": 0,
        "control_evaluations": 0, "fits": 0, "strength_games": 0, "alpha_spent": 0,
    }
    required_m = {
        "state": "completed", "terminal": "CLS_MIRROR_SCALE_DIAGNOSTIC_COMPLETE_V1",
        "mode": "production", "diagnostic_only": True, "roots": ROOTS,
        "deep_budget_nodes": DEEP_BUDGET, "target_reads": 0, "candidate_reads": 0,
        "control_evaluations": 0, "fits": 0, "strength_games": 0, "alpha_spent": 0,
    }
    for key, expected in required_d.items():
        if dsum.get(key) != expected:
            raise StageError(f"depth_summary_drift:{key}")
    for key, expected in required_m.items():
        if msum.get(key) != expected:
            raise StageError(f"mirror_summary_drift:{key}")
    if tuple(dsum.get("budgets_nodes", [])) != BUDGETS:
        raise StageError("depth_budget_drift")
    if (dsum.get("launch") or {}).get("receipt_sha256") != DEPTH_RECEIPT:
        raise StageError("depth_launch_drift")
    if (msum.get("launch") or {}).get("receipt_sha256") != MIRROR_RECEIPT:
        raise StageError("mirror_launch_drift")
    droot, mroot = read_json(depth / "root-selection.json"), read_json(mirror / "root-selection.json")
    if droot.get("parent_ids") != mroot.get("parent_ids") or len(droot.get("parent_ids", [])) != ROOTS:
        raise StageError("source_root_order_drift")
    auth = {
        "schema": "jass.cls_search_profile_source_authentication.v1",
        "authenticated": True,
        "depth": {"job_id": DEPTH_JOB, "attempt_id": DEPTH_ATTEMPT, "code_sha": DEPTH_CODE,
                  "receipt_sha256": DEPTH_RECEIPT, "per_root_sha256": base.sha_file(depth / "per_root.tsv")},
        "mirror": {"job_id": MIRROR_JOB, "attempt_id": MIRROR_ATTEMPT, "code_sha": MIRROR_CODE,
                   "receipt_sha256": MIRROR_RECEIPT, "deep_reference_sha256": base.sha_file(mirror / "deep_reference.tsv")},
        "cohort_identity_sha256": COHORT_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "roots": ROOTS,
        "target_reads": 0,
        "fits": 0,
        "strength_games": 0,
        "alpha_spent": 0,
    }
    base.atomic_write(artifacts / "source-authentication.json", base.canonical_json(auth))
    return depth / "per_root.tsv", mirror / "deep_reference.tsv"


def build_profile(shallow_rows: list[dict[str, str]], deep_rows: list[dict[str, str]]) -> tuple[dict, dict]:
    expected = ROOTS * len(BUDGETS)
    phase_by_root = {}
    for row in shallow_rows:
        if row.get("engine") == "JASS_PARITY":
            phase_by_root.setdefault(row["root_id"], row["phase"])
    if len(phase_by_root) != ROOTS or {p: sum(v == p for v in phase_by_root.values()) for p in PHASES} != {p: ROOTS_PER_PHASE for p in PHASES}:
        raise StageError("phase_shape_drift")
    parity = {(r["root_id"], int(r["budget"])): r for r in shallow_rows if r["engine"] == "JASS_PARITY"}
    prof = {(r["root_id"], int(r["budget"])): r for r in shallow_rows if r["engine"] == "JASS_PROFILE"}
    scan = {(r["root_id"], int(r["budget"])): r for r in shallow_rows if r["engine"] == "SCAN"}
    if len(parity) != expected or len(prof) != expected or len(scan) != expected or set(parity) != set(scan) or set(parity) != set(prof):
        raise StageError("shallow_shape_drift")
    for key in parity:
        for field in ("nodes_observed", "completed_nominal_depth", "seldepth", "bestmove_canonical", "score_cp",
                      "branching", "forced_capture_at_root", "max_capture_len", "pieces", "stm"):
            if parity[key].get(field) != prof[key].get(field):
                raise StageError(f"parity_profile_semantic_drift:{field}")
    deep_map = {r["root_id"]: r for r in deep_rows}
    if len(deep_map) != ROOTS or set(deep_map) != set(phase_by_root) or any(int(r["budget"]) != DEEP_BUDGET for r in deep_rows):
        raise StageError("deep_shape_drift")

    by_budget = {}
    by_phase = {phase: {} for phase in PHASES}
    vectors = {phase: [] for phase in PHASES}
    for budget in BUDGETS:
        jrows = [r for r in parity.values() if int(r["budget"]) == budget]
        prows = [r for r in prof.values() if int(r["budget"]) == budget]
        srows = [r for r in scan.values() if int(r["budget"]) == budget]
        js, ss = summarize_jass(jrows), summarize_scan(srows)
        by_budget[str(budget)] = {
            "jass_parity": js,
            "scan": ss,
            "jass_profile_instrumentation_wall_ratio": safe_ratio(sum(numeric(r, "wall_ms") for r in prows), js["wall_ms_sum"]),
        }
        for phase in PHASES:
            pj = [r for r in jrows if r["phase"] == phase]
            ps = [r for r in srows if r["phase"] == phase]
            by_phase[phase][str(budget)] = {"jass_parity": summarize_jass(pj), "scan": summarize_scan(ps)}
    for phase in PHASES:
        ids = [root for root, p in phase_by_root.items() if p == phase]
        if len(ids) != ROOTS_PER_PHASE:
            raise StageError("phase_ids_drift")
        for root in ids:
            vec = []
            for budget in BUDGETS:
                vec.extend(root_vector(parity[(root, budget)], scan[(root, budget)]))
            vectors[phase].append(vec)
    boot = bootstrap({phase: np.asarray(values, dtype=np.float64) for phase, values in vectors.items()})
    deep_summary = summarize_jass(list(deep_map.values()), deep=True)
    frontier = [
        {"budget_nodes": b, "mean_completed_nominal_depth": by_budget[str(b)]["jass_parity"]["mean_completed_nominal_depth"],
         "median_completed_nominal_depth": by_budget[str(b)]["jass_parity"]["median_completed_nominal_depth"]}
        for b in BUDGETS
    ] + [{"budget_nodes": DEEP_BUDGET, "mean_completed_nominal_depth": deep_summary["mean_completed_nominal_depth"],
          "median_completed_nominal_depth": deep_summary["median_completed_nominal_depth"]}]
    profile = {
        "schema": "jass.cls_search_profile_readout.v1",
        "diagnostic_only": True,
        "classification": None,
        "roots": ROOTS,
        "budgets_nodes": list(BUDGETS),
        "deep_budget_nodes": DEEP_BUDGET,
        "by_budget": by_budget,
        "by_phase": by_phase,
        "jass_deep_1m": deep_summary,
        "fixed_node_completed_depth_frontier": frontier,
        "nodes_to_depth": {
            "available": False,
            "reason": "same-search nodes-to-depth snapshots unavailable; fresh depth-N/interpolated surrogate forbidden",
        },
        "scan_internal_counters": {
            "available": False,
            "fields": ["qnodes", "eval_calls", "tt_hit_rate", "cutoffs", "first_move_cutoffs", "pvs_researches", "moves_searched"],
            "imputation": False,
        },
    }
    return profile, boot


def run_stage(work: Path, artifacts: Path) -> dict[str, object]:
    mode = os.environ.get("LAUNCH_MODE")
    if mode not in {"rehearsal", "production"}:
        raise StageError("LAUNCH_MODE must be rehearsal or production")
    if work.exists() or work.is_symlink():
        raise StageError("work directory must be absent")
    work.mkdir(parents=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    shallow_path, deep_path = authenticate_sources(work, artifacts)
    shallow_rows, deep_rows = base.read_tsv(shallow_path), base.read_tsv(deep_path)
    if len(shallow_rows) != ROOTS * len(BUDGETS) * 3 or len(deep_rows) != ROOTS:
        raise StageError("source_cardinality_drift")
    profile, boot = build_profile(shallow_rows, deep_rows)
    base.atomic_write(artifacts / "search-profile.json", base.canonical_json(profile))
    base.atomic_write(artifacts / "bootstrap.json", base.canonical_json(boot))
    terminal = REHEARSAL_TERMINAL if mode == "rehearsal" else PRODUCTION_TERMINAL
    manifest = {
        "schema": "jass.cls_search_profile_manifest.v1",
        "terminal": terminal,
        "mode": mode,
        "diagnostic_only": True,
        "cohort_identity_sha256": COHORT_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "roots": ROOTS,
        "roots_per_phase": ROOTS_PER_PHASE,
        "budgets_nodes": list(BUDGETS),
        "deep_budget_nodes": DEEP_BUDGET,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "nodes_to_depth_available": False,
        "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
        "new_jass_searches": 0, "new_scan_searches": 0,
        "fits": 0, "strength_games": 0, "selfplay_games": 0,
        "alpha_spent": 0, "promotions": 0, "bakes": 0,
    }
    base.atomic_write(artifacts / "manifest.json", base.canonical_json(manifest))
    lines = ["# CLS-D search-profile V1", "", f"Terminal: `{terminal}`.", "",
             "Read-only authenticated reuse of depth/growth 2000 and mirror-scale 2008; no new engine search.", "",
             "| budget | Jass mean NPS | Scan mean NPS | Jass mean depth | Scan mean depth | eval/node | qnodes/node | TT hit | first-move cutoff share |",
             "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for b in BUDGETS:
        cell = profile["by_budget"][str(b)]
        j, s = cell["jass_parity"], cell["scan"]
        lines.append(f"| {b:,} | {j['mean_nps']:.3f} | {s['mean_nps']:.3f} | {j['mean_completed_nominal_depth']:.3f} | {s['mean_completed_nominal_depth']:.3f} | {j['eval_calls_per_node']:.6f} | {j['qnodes_per_node']:.6f} | {j['tt_hit_rate']:.6f} | {j['first_move_cutoff_share']:.6f} |")
    lines += ["", f"Deep Jass reference: {DEEP_BUDGET:,} exact nodes; mean depth {profile['jass_deep_1m']['mean_completed_nominal_depth']:.3f}.",
              f"Bootstrap: {BOOTSTRAP_REPLICATES} paired phase-stratified roots, seed `{BOOTSTRAP_SEED}`.",
              "", "True same-search nodes-to-depth remains unavailable; no fresh depth-N or interpolated surrogate was used.",
              "", "Descriptive search-profile evidence only; no bottleneck classification, promotion, bake or scale-up."]
    base.atomic_write(artifacts / "RESULTS.md", ("\n".join(lines) + "\n").encode())
    summary = {
        "schema": SCHEMA,
        "state": "completed",
        "terminal": terminal,
        "scientific_verdict": None,
        "classification": None,
        "diagnostic_only": True,
        "mode": mode,
        "roots": ROOTS,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "nodes_to_depth_available": False,
        "next_stage": "QUEUE_EXACT_PRODUCTION_SAME_COMMON_SPEC" if mode == "rehearsal" else "CONTINUE_TO_DRAW_PENTANOMIAL_THROUGHPUT_DIAGNOSTIC",
        "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
        "new_jass_searches": 0, "new_scan_searches": 0,
        "fits": 0, "strength_games": 0, "selfplay_games": 0,
        "alpha_spent": 0, "promotions": 0, "bakes": 0,
    }
    base.atomic_write(artifacts / "scientific-summary.json", base.canonical_json(summary))
    return summary


def main() -> int:
    result = Path(os.environ["JASS_RESULT_DIR"])
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    try:
        run_stage(result / "cls-search-profile-work", artifact)
        return 0
    except BaseException as exc:
        artifact.mkdir(parents=True, exist_ok=True)
        base.atomic_write(artifact / "scientific-summary.json", base.canonical_json({
            "schema": SCHEMA, "state": "failed", "terminal": TECHNICAL_TERMINAL,
            "scientific_verdict": None, "classification": "TECHNICAL",
            "error_type": type(exc).__name__, "error": str(exc)[:2000],
            "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
            "new_jass_searches": 0, "new_scan_searches": 0,
            "fits": 0, "strength_games": 0, "selfplay_games": 0,
            "alpha_spent": 0, "promotions": 0, "bakes": 0,
        }))
        print(f"CLS search-profile TECHNICAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
