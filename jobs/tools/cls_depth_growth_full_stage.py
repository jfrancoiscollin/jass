#!/usr/bin/env python3
"""Frozen FULL-512 CLS-D depth/growth stage after authenticated sizing.

This is the production-capable successor to the 32-root sizing rehearsal.  The
1998 rehearsal mechanically selected FULL (512 roots) under the preregistered
<=2400 s rule.  That decision is now hard-frozen: this module has no runtime
FULL/LITE adaptation and runs exactly the frozen DEEP512 cohort in source order
for both the production-shaped rehearsal and production.  The two launch modes
share one implementation/profile and differ only by LAUNCH_MODE.

No confirmation target, fit, strength game, alpha, promotion or bake is read or
spent.  Cross-engine nodes-by-depth/SCALING remains disabled because symmetric
same-search Jass snapshots are unavailable; fresh depth-N searches are never
substituted.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import sys
import time
from typing import Sequence

import numpy as np

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import cls_depth_growth_stage as base  # noqa: E402

SCHEMA = "jass.cls_depth_growth_full.v2"
REHEARSAL_TERMINAL = "CLS_DEPTH_GROWTH_FULL_REHEARSAL_READY_V2"
PRODUCTION_TERMINAL = "DEPTH_GROWTH_JASS_VS_SCAN_V2_COMPLETE"

# Authenticated sizing source.  These bytes are evidence, not a tunable input.
SIZING_JOB = "cpx62-1998-l3-cls-depth-growth-rehearsal-v1"
SIZING_ATTEMPT = "20260916T061338Z-1a27049d"
SIZING_CODE = "1a27049d036a5bd8534ba2cb350c257ac33942c3"
SIZING_PREFIX = f"r2:jass-data/runs/{SIZING_JOB}/{SIZING_ATTEMPT}"
SIZING_RECEIPT_SHA256 = "bee34c20c742b3acb0199ec9723fe8135e32e09ffbf82e68e284ddff724d06ad"
SIZING_COMMON_SPEC_SHA256 = "bf6a01bd24a1ee204d835790a3e9828cbd09e262821481a8d235b54d777ed0ff"

# The preregistered mechanical sizing decision is now immutable.
PRODUCTION_SIZE_DECISION = "FULL"
PRODUCTION_ROOTS = 512
ROOTS_PER_PHASE = 128
BOOTSTRAP_REPLICATES = 100_000
BUDGETS = base.BUDGETS
PHASES = base.PHASES
BOOTSTRAP_SEED = base.BOOTSTRAP_SEED


class StageError(base.StageError):
    pass


def authenticate_sizing(work: Path, artifacts: Path) -> dict[str, object]:
    out = work / "sizing-source"
    report = work / "verified-sizing-source.json"
    base.fetch_completed(
        SIZING_PREFIX,
        job=SIZING_JOB,
        attempt=SIZING_ATTEMPT,
        code=SIZING_CODE,
        mappings=[
            ("artefacts/sizing.json", "sizing.json"),
            ("artefacts/scientific-summary.json", "scientific-summary.json"),
            ("artefacts/launch-receipt.json", "launch-receipt.json"),
            ("artefacts/manifest.json", "manifest.json"),
        ],
        out_dir=out,
        report=report,
    )
    if base.sha_file(out / "launch-receipt.json") != SIZING_RECEIPT_SHA256:
        raise StageError("1998 authenticated launch receipt SHA drift")

    sizing = json.loads((out / "sizing.json").read_text(encoding="utf-8"))
    expected = {
        "production_size_decision": PRODUCTION_SIZE_DECISION,
        "production_roots": PRODUCTION_ROOTS,
        "full_threshold_seconds": 2400,
        "third_adaptation_allowed": False,
    }
    for key, value in expected.items():
        if sizing.get(key) != value:
            raise StageError(f"1998 sizing {key} drift")
    projected = float(sizing.get("projected_full_512_wall_seconds", float("inf")))
    if not projected <= 2400.0:
        raise StageError("1998 sizing no longer justifies preregistered FULL choice")

    summary = json.loads((out / "scientific-summary.json").read_text(encoding="utf-8"))
    launch = summary.get("launch") or {}
    required_summary = {
        "state": "completed",
        "terminal": "CLS_DEPTH_GROWTH_REHEARSAL_READY_V1",
        "production_size_decision": "FULL",
        "target_reads": 0,
        "candidate_reads": 0,
        "control_evaluations": 0,
        "fits": 0,
        "strength_games": 0,
        "alpha_spent": 0,
    }
    for key, value in required_summary.items():
        if summary.get(key) != value:
            raise StageError(f"1998 summary {key} drift")
    if launch.get("receipt_sha256") != SIZING_RECEIPT_SHA256 \
            or launch.get("common_spec_sha256") != SIZING_COMMON_SPEC_SHA256 \
            or launch.get("mode") != "rehearsal":
        raise StageError("1998 Launch-V2 sizing authentication drift")

    authentication = {
        "schema": "jass.cls_depth_growth_sizing_authentication.v1",
        "job_id": SIZING_JOB,
        "attempt_id": SIZING_ATTEMPT,
        "code_sha": SIZING_CODE,
        "receipt_sha256": SIZING_RECEIPT_SHA256,
        "common_spec_sha256": SIZING_COMMON_SPEC_SHA256,
        "sizing_sha256": base.sha_file(out / "sizing.json"),
        "projected_full_512_wall_seconds": projected,
        "production_size_decision": PRODUCTION_SIZE_DECISION,
        "production_roots": PRODUCTION_ROOTS,
        "authenticated": True,
    }
    base.atomic_write(artifacts / "sizing-source-authentication.json", base.canonical_json(authentication))
    return authentication


def select_full(deep_tsv: Path, out_ids: Path) -> list[dict[str, str]]:
    """Use the entire frozen DEEP512 cohort, preserving its sealed source order."""
    with deep_tsv.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"parent_id", "canonical_fingerprint", "phase"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise StageError("deep512.tsv fields drift")
        rows = list(reader)
    if len(rows) != PRODUCTION_ROOTS:
        raise StageError("DEEP512 production cardinality drift")
    if len({row["parent_id"] for row in rows}) != PRODUCTION_ROOTS \
            or len({row["canonical_fingerprint"] for row in rows}) != PRODUCTION_ROOTS:
        raise StageError("DEEP512 production identities are not unique")
    counts = {phase: sum(row["phase"] == phase for row in rows) for phase in PHASES}
    if counts != {phase: ROOTS_PER_PHASE for phase in PHASES}:
        raise StageError(f"DEEP512 phase cardinality drift: {counts}")
    base.atomic_write(out_ids, ("\n".join(row["parent_id"] for row in rows) + "\n").encode())
    return rows


def verify_parity(parity: Path, profile: Path, roots: int) -> dict[str, object]:
    a, b = base.read_tsv(parity), base.read_tsv(profile)
    expected_rows = roots * len(BUDGETS)
    if len(a) != expected_rows or len(b) != expected_rows:
        raise StageError("PARITY/PROFILE FULL row cardinality drift")
    keys = (
        "root_id", "budget", "nodes_observed", "completed_nominal_depth",
        "effective_depth", "bestmove_canonical", "score_cp", "branching",
        "forced_capture_at_root", "max_capture_len", "pieces", "stm",
    )
    mismatches = []
    for index, (left, right) in enumerate(zip(a, b)):
        bad = {key: (left.get(key), right.get(key)) for key in keys if left.get(key) != right.get(key)}
        if bad:
            mismatches.append({"row": index, "fields": bad})
            if len(mismatches) >= 3:
                break
    if mismatches:
        raise StageError(f"Jass PARITY/PROFILE semantic mismatch: {mismatches}")
    return {"rows": len(a), "mismatches": 0, "fields_compared": list(keys)}


def aggregate_full(merged: list[dict[str, str]]) -> dict[str, object]:
    by_engine_budget: dict[str, dict[str, object]] = {}
    for engine in ("JASS_PARITY", "JASS_PROFILE", "SCAN"):
        for budget in BUDGETS:
            rows = [r for r in merged if r["engine"] == engine and int(r["budget"]) == budget]
            if len(rows) != PRODUCTION_ROOTS:
                raise StageError(f"FULL aggregate row count drift {engine}/{budget}")
            depths = np.asarray([float(r["completed_nominal_depth"]) for r in rows], dtype=float)
            nps = np.asarray([float(r["nps"]) for r in rows], dtype=float)
            wall = np.asarray([float(r["wall_ms"]) for r in rows], dtype=float)
            by_engine_budget[f"{engine}:{budget}"] = {
                "roots": len(rows),
                "mean_completed_nominal_depth": float(depths.mean()),
                "median_completed_nominal_depth": float(np.median(depths)),
                "mean_nps": float(nps.mean()),
                "median_nps": float(np.median(nps)),
                "wall_ms_sum": float(wall.sum()),
            }

    phase_depth_delta: dict[str, dict[str, float]] = {}
    for phase in PHASES:
        phase_depth_delta[phase] = {}
        for budget in BUDGETS:
            j = {r["root_id"]: float(r["completed_nominal_depth"]) for r in merged
                 if r["engine"] == "JASS_PARITY" and r["phase"] == phase and int(r["budget"]) == budget}
            s = {r["root_id"]: float(r["completed_nominal_depth"]) for r in merged
                 if r["engine"] == "SCAN" and r["phase"] == phase and int(r["budget"]) == budget}
            if set(j) != set(s) or len(j) != ROOTS_PER_PHASE:
                raise StageError(f"paired FULL phase shape drift {phase}/{budget}")
            phase_depth_delta[phase][str(budget)] = float(np.mean([j[root] - s[root] for root in j]))

    parity = {(r["root_id"], int(r["budget"])): r for r in merged if r["engine"] == "JASS_PARITY"}
    scans = {(r["root_id"], int(r["budget"])): r for r in merged if r["engine"] == "SCAN"}
    if set(parity) != set(scans) or len(parity) != PRODUCTION_ROOTS * len(BUDGETS):
        raise StageError("paired FULL Jass/Scan shape drift")
    agreements = sum(parity[key]["bestmove_canonical"] == scans[key]["bestmove_canonical"] for key in parity)

    parity_wall = sum(float(r["wall_ms"]) for r in merged if r["engine"] == "JASS_PARITY")
    profile_wall = sum(float(r["wall_ms"]) for r in merged if r["engine"] == "JASS_PROFILE")
    return {
        "schema": "jass.cls_depth_growth_aggregates.v2",
        "diagnostic_only": True,
        "production_size_decision": PRODUCTION_SIZE_DECISION,
        "roots": PRODUCTION_ROOTS,
        "roots_per_phase": ROOTS_PER_PHASE,
        "by_engine_budget": by_engine_budget,
        "jass_minus_scan_completed_depth_by_phase": phase_depth_delta,
        "canonical_root_move": {
            "pairs": len(parity),
            "canonical_bestmove_agreement": agreements,
            "agreement_rate": agreements / len(parity),
        },
        "jass_profile_wall_over_parity_wall": profile_wall / parity_wall if parity_wall else None,
        "cross_engine_depth_curve_available": False,
        "nodes_by_depth": None,
        "depth_growth_contrasts": None,
        "scaling_label_enabled": False,
        "fixed_depth_diagnostics_enabled": False,
        "fixed_depth_disable_reason": "fresh depth-N searches are forbidden substitutes for symmetric same-search snapshots",
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }


def root_metric_arrays(merged: list[dict[str, str]], selected: Sequence[dict[str, str]]) -> dict[str, np.ndarray]:
    parity = {(r["root_id"], int(r["budget"])): r for r in merged if r["engine"] == "JASS_PARITY"}
    scans = {(r["root_id"], int(r["budget"])): r for r in merged if r["engine"] == "SCAN"}
    arrays: dict[str, np.ndarray] = {}
    for phase in PHASES:
        rows = [row for row in selected if row["phase"] == phase]
        if len(rows) != ROOTS_PER_PHASE:
            raise StageError(f"bootstrap phase root count drift for {phase}")
        values: list[list[float]] = []
        for row in rows:
            root = row["parent_id"]
            vector: list[float] = []
            for budget in BUDGETS:
                key = (root, budget)
                if key not in parity or key not in scans:
                    raise StageError(f"bootstrap paired row missing for root {root}/{budget}")
                vector.append(float(parity[key]["completed_nominal_depth"]) -
                              float(scans[key]["completed_nominal_depth"]))
            for budget in BUDGETS:
                key = (root, budget)
                vector.append(1.0 if parity[key]["bestmove_canonical"] == scans[key]["bestmove_canonical"] else 0.0)
            values.append(vector)
        arrays[phase] = np.asarray(values, dtype=np.float64)
    return arrays


def bootstrap_root_metrics(arrays: dict[str, np.ndarray], *, replicates: int = BOOTSTRAP_REPLICATES,
                           seed: int = BOOTSTRAP_SEED) -> dict[str, object]:
    """Paired phase-stratified bootstrap; root is the resampling unit."""
    labels = [f"depth_delta_{budget}" for budget in BUDGETS] + [f"move_agreement_{budget}" for budget in BUDGETS]
    samples = np.zeros((replicates, len(labels)), dtype=np.float64)
    rng = np.random.default_rng(seed)
    chunk = 1000
    for phase in PHASES:
        values = arrays[phase]
        if values.shape != (ROOTS_PER_PHASE, len(labels)):
            raise StageError(f"bootstrap array shape drift for {phase}: {values.shape}")
        for start in range(0, replicates, chunk):
            stop = min(start + chunk, replicates)
            idx = rng.integers(0, ROOTS_PER_PHASE, size=(stop - start, ROOTS_PER_PHASE))
            samples[start:stop] += values[idx].mean(axis=1) / len(PHASES)
    quantiles = np.quantile(samples, [0.025, 0.5, 0.975], axis=0)
    metrics = {}
    for column, label in enumerate(labels):
        metrics[label] = {
            "q025": float(quantiles[0, column]),
            "median": float(quantiles[1, column]),
            "q975": float(quantiles[2, column]),
        }
    return {
        "schema": "jass.cls_depth_growth_bootstrap.v1",
        "unit": "root_id",
        "phase_stratified": True,
        "phase_quotas_fixed": {phase: ROOTS_PER_PHASE for phase in PHASES},
        "replicates": replicates,
        "seed": seed,
        "metrics": metrics,
    }


def bottleneck_evidence(aggregates: dict[str, object], bootstrap: dict[str, object]) -> dict[str, object]:
    by = aggregates["by_engine_budget"]
    depth = {}
    throughput = {}
    for budget in BUDGETS:
        j = by[f"JASS_PARITY:{budget}"]
        s = by[f"SCAN:{budget}"]
        depth[str(budget)] = {
            "jass_mean_completed_nominal_depth": j["mean_completed_nominal_depth"],
            "scan_mean_completed_nominal_depth": s["mean_completed_nominal_depth"],
            "jass_minus_scan": j["mean_completed_nominal_depth"] - s["mean_completed_nominal_depth"],
            "bootstrap_ci": bootstrap["metrics"][f"depth_delta_{budget}"],
        }
        throughput[str(budget)] = {
            "jass_mean_nps": j["mean_nps"],
            "scan_mean_nps": s["mean_nps"],
            "jass_over_scan_mean_nps": j["mean_nps"] / s["mean_nps"] if s["mean_nps"] else None,
        }
    return {
        "schema": "jass.cls_depth_growth_bottleneck_evidence.v1",
        "diagnostic_only": True,
        "classification": None,
        "search": {"completed_nominal_depth": depth},
        "decision_eval": {
            "canonical_root_move_agreement_rate": aggregates["canonical_root_move"]["agreement_rate"],
            "agreement_bootstrap_by_budget": {
                str(b): bootstrap["metrics"][f"move_agreement_{b}"] for b in BUDGETS
            },
        },
        "cost": {
            "throughput": throughput,
            "jass_profile_wall_over_parity_wall": aggregates["jass_profile_wall_over_parity_wall"],
        },
        "scaling": {
            "enabled": False,
            "reason": "symmetric continuous-search Jass nodes-by-depth snapshots unavailable; fresh depth-N substitutes forbidden",
        },
        "localized": {"phase_depth_delta": aggregates["jass_minus_scan_completed_depth_by_phase"]},
        "note": "Descriptive evidence only; final CLS bottleneck classification waits for all preregistered diagnostics.",
    }


def run_stage(work: Path, artifacts: Path) -> dict[str, object]:
    mode = os.environ.get("LAUNCH_MODE")
    if mode not in {"rehearsal", "production"}:
        raise StageError("LAUNCH_MODE must be rehearsal or production")
    if work.exists() or work.is_symlink():
        raise StageError("work directory must be absent")
    work.mkdir(parents=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    if os.statvfs(str(artifacts)).f_bavail * os.statvfs(str(artifacts)).f_frsize < 3 * 1024**3:
        raise StageError("less than 3 GiB free before CLS-D input fetch")

    started = time.monotonic()
    sizing_auth = authenticate_sizing(work, artifacts)
    parents, metadata, deep, curriculum, scan = base.fetch_inputs(work)
    ids = work / "full-root-ids.txt"
    selected = select_full(deep, ids)
    base.atomic_write(artifacts / "full-root-ids.txt", ids.read_bytes())
    base.atomic_write(artifacts / "root-selection.json", base.canonical_json({
        "schema": "jass.cls_depth_growth_root_selection.v2",
        "selection": "FULL",
        "roots": PRODUCTION_ROOTS,
        "per_phase": ROOTS_PER_PHASE,
        "order": "authenticated deep512.tsv source order",
        "parent_ids": [int(row["parent_id"]) for row in selected],
        "canonical_fingerprints": [row["canonical_fingerprint"] for row in selected],
        "source_cohort_sha256": base.COHORT_SHA,
        "sizing_receipt_sha256": SIZING_RECEIPT_SHA256,
    }))

    parity_exe = base.build_jass(work, profile=False)
    profile_exe = base.build_jass(work, profile=True)
    parity_tsv, profile_tsv = work / "jass-parity.tsv", work / "jass-profile.tsv"
    parity_report, profile_report = work / "jass-parity.json", work / "jass-profile.json"
    base.run_jass(parity_exe, parents, ids, curriculum, parity_tsv, parity_report, work / "jass-parity.log")
    base.run_jass(profile_exe, parents, ids, curriculum, profile_tsv, profile_report, work / "jass-profile.log")
    parity_check = verify_parity(parity_tsv, profile_tsv, PRODUCTION_ROOTS)
    base.atomic_write(artifacts / "jass-parity-profile.json", base.canonical_json(parity_check))

    scan_tsv, scan_report = work / "scan.tsv", work / "scan.json"
    base.run_scan(scan, parents, metadata, ids, scan_tsv, scan_report, work / "scan.log")
    merged, _ = base.merge_rows(parity_tsv, profile_tsv, scan_tsv, artifacts / "per_root.tsv")
    aggregates = aggregate_full(merged)
    arrays = root_metric_arrays(merged, selected)
    bootstrap = bootstrap_root_metrics(arrays)
    evidence = bottleneck_evidence(aggregates, bootstrap)
    base.atomic_write(artifacts / "aggregates.json", base.canonical_json(aggregates))
    base.atomic_write(artifacts / "bootstrap.json", base.canonical_json(bootstrap))
    base.atomic_write(artifacts / "bottleneck-evidence.json", base.canonical_json(evidence))

    elapsed = time.monotonic() - started
    terminal = REHEARSAL_TERMINAL if mode == "rehearsal" else PRODUCTION_TERMINAL
    manifest = {
        "schema": "jass.cls_depth_growth_manifest.v2",
        "terminal": terminal,
        "mode": mode,
        "diagnostic_only": True,
        "cohort_identity_sha256": base.COHORT_SHA,
        "curriculum_sha256": base.CURRICULUM_SHA,
        "scan": {"commit": base.SCAN_COMMIT, "binary_sha256": base.SCAN_BINARY_SHA,
                 "eval_sha256": base.SCAN_EVAL_SHA, "ini_sha256": base.SCAN_INI_SHA},
        "budgets_nodes": list(BUDGETS),
        "production_size_decision": PRODUCTION_SIZE_DECISION,
        "roots": PRODUCTION_ROOTS,
        "roots_per_phase": ROOTS_PER_PHASE,
        "root_order": "authenticated deep512.tsv source order",
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "sizing_source": sizing_auth,
        "cross_engine_depth_curve_available": False,
        "depth_curve_disable_reason": "Jass same-search per-depth snapshots are not exposed without changing frozen semantics; fresh depth-N searches are forbidden substitutes",
        "fixed_depth_diagnostics_enabled": False,
        "parity_profile_mismatches": 0,
        "elapsed_seconds": elapsed,
        "target_reads": 0,
        "candidate_reads": 0,
        "control_evaluations": 0,
        "fits": 0,
        "strength_games": 0,
        "alpha_spent": 0,
        "promotion_authorized": False,
        "bake": False,
    }
    base.atomic_write(artifacts / "manifest.json", base.canonical_json(manifest))

    agreement = aggregates["canonical_root_move"]
    results_md = (
        f"# CLS-D depth/growth V2 — {mode}\n\n"
        f"Terminal: `{terminal}`. Frozen **FULL-512** cohort (128/phase), budgets 5k/50k/200k.\n\n"
        f"Sizing source: `{SIZING_JOB}/{SIZING_ATTEMPT}`, receipt `{SIZING_RECEIPT_SHA256}`; "
        f"projected FULL wall {sizing_auth['projected_full_512_wall_seconds']:.3f}s <= 2400s.\n\n"
        f"Jass PARITY/PROFILE semantic mismatches: **0**. Canonical Jass/Scan root-move agreement: "
        f"{agreement['canonical_bestmove_agreement']}/{agreement['pairs']} ({agreement['agreement_rate']:.6f}).\n\n"
        f"Paired phase-stratified bootstrap: {BOOTSTRAP_REPLICATES} replicates, seed `{BOOTSTRAP_SEED}`.\n\n"
        "Cross-engine nodes-by-depth / SCALING and fresh fixed-depth surrogates remain disabled. "
        "See `bottleneck-evidence.json` for preregistered descriptive evidence; no final CLS bottleneck classification is made here.\n"
    )
    base.atomic_write(artifacts / "RESULTS.md", results_md.encode())

    summary = {
        "schema": SCHEMA,
        "state": "completed",
        "terminal": terminal,
        "scientific_verdict": None,
        "diagnostic_only": True,
        "mode": mode,
        "production_size_decision": PRODUCTION_SIZE_DECISION,
        "roots": PRODUCTION_ROOTS,
        "roots_per_phase": ROOTS_PER_PHASE,
        "budgets_nodes": list(BUDGETS),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "parity_profile_mismatches": 0,
        "canonical_root_move_agreement_rate": agreement["agreement_rate"],
        "cross_engine_depth_curve_available": False,
        "next_stage": "QUEUE_EXACT_PRODUCTION_SAME_COMMON_SPEC" if mode == "rehearsal" else "CONTINUE_CLS_DIAGNOSTICS_PER_MASTER_PLAN",
        "target_reads": 0,
        "candidate_reads": 0,
        "control_evaluations": 0,
        "new_jass_searches": PRODUCTION_ROOTS * len(BUDGETS) * 2,
        "new_scan_searches": PRODUCTION_ROOTS * len(BUDGETS),
        "fits": 0,
        "strength_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
    }
    base.atomic_write(artifacts / "scientific-summary.json", base.canonical_json(summary))
    return summary


def main() -> int:
    result_dir = Path(os.environ["JASS_RESULT_DIR"])
    artifact_dir = Path(os.environ["JASS_ARTEFACT_DIR"])
    work = result_dir / "cls-depth-growth-full-work"
    try:
        run_stage(work, artifact_dir)
        return 0
    except BaseException as exc:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        failure = {
            "schema": SCHEMA,
            "state": "failed",
            "terminal": "DEPTH_GROWTH_JASS_VS_SCAN_V2_TECHNICAL_FAILURE",
            "scientific_verdict": None,
            "classification": "TECHNICAL",
            "error_type": type(exc).__name__,
            "error": str(exc)[:2000],
            "target_reads": 0,
            "candidate_reads": 0,
            "control_evaluations": 0,
            "fits": 0,
            "strength_games": 0,
            "alpha_spent": 0,
            "promotions": 0,
            "bakes": 0,
        }
        base.atomic_write(artifact_dir / "scientific-summary.json", base.canonical_json(failure))
        print(f"CLS-D TECHNICAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
