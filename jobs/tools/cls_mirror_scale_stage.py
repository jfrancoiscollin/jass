#!/usr/bin/env python3
"""CLS-D mirror-scale diagnostic with current-code Jass1M parent-root reference."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
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
from jobs.tools import cls_depth_growth_full_stage as full  # noqa: E402

SCHEMA = "jass.cls_mirror_scale.v1"
REHEARSAL_TERMINAL = "CLS_MIRROR_SCALE_REHEARSAL_READY_V1"
PRODUCTION_TERMINAL = "CLS_MIRROR_SCALE_DIAGNOSTIC_COMPLETE_V1"
TECHNICAL_TERMINAL = "CLS_MIRROR_SCALE_TECHNICAL_FAILURE_V1"
SOURCE_JOB = "cpx62-2000-l3-cls-depth-growth-full-production-v2"
SOURCE_ATTEMPT = "20260916T083204Z-7a5f44ec"
SOURCE_CODE = "7a5f44ec1681c2471b1815f8767b4008b11e3a54"
SOURCE_PREFIX = f"r2:jass-data/runs/{SOURCE_JOB}/{SOURCE_ATTEMPT}"
SOURCE_RECEIPT_SHA256 = "3155272745b458af68e35de06bf6921b20fdf8639913287be6d71075e3349a42"
ROOTS = 512
ROOTS_PER_PHASE = 128
SHALLOW_BUDGETS = (5_000, 50_000, 200_000)
DEEP_BUDGET = 1_000_000
BOOTSTRAP_REPLICATES = 100_000
BOOTSTRAP_SEED = 2026091003
PHASES = base.PHASES


class StageError(base.StageError):
    pass


def authenticate_source(work: Path, artifacts: Path, selected: Sequence[dict[str, str]]) -> Path:
    out = work / "depth-growth-2000"
    report = work / "verified-depth-growth-2000.json"
    base.fetch_completed(
        SOURCE_PREFIX, job=SOURCE_JOB, attempt=SOURCE_ATTEMPT, code=SOURCE_CODE,
        mappings=[
            ("artefacts/per_root.tsv", "per_root.tsv"),
            ("artefacts/manifest.json", "manifest.json"),
            ("artefacts/scientific-summary.json", "scientific-summary.json"),
            ("artefacts/launch-receipt.json", "launch-receipt.json"),
            ("artefacts/root-selection.json", "root-selection.json"),
            ("artefacts/full-root-ids.txt", "full-root-ids.txt"),
        ], out_dir=out, report=report,
    )
    if base.sha_file(out / "launch-receipt.json") != SOURCE_RECEIPT_SHA256:
        raise StageError("2000 launch receipt SHA drift")
    summary = json.loads((out / "scientific-summary.json").read_text(encoding="utf-8"))
    required = {
        "state": "completed", "terminal": "DEPTH_GROWTH_JASS_VS_SCAN_V2_COMPLETE",
        "mode": "production", "diagnostic_only": True, "roots": ROOTS,
        "roots_per_phase": ROOTS_PER_PHASE, "target_reads": 0, "candidate_reads": 0,
        "control_evaluations": 0, "fits": 0, "strength_games": 0, "alpha_spent": 0,
    }
    for key, value in required.items():
        if summary.get(key) != value:
            raise StageError(f"2000 summary {key} drift")
    if tuple(summary.get("budgets_nodes", [])) != SHALLOW_BUDGETS:
        raise StageError("2000 shallow budget drift")
    launch = summary.get("launch") or {}
    if launch.get("receipt_sha256") != SOURCE_RECEIPT_SHA256 or launch.get("mode") != "production":
        raise StageError("2000 Launch-V2 authentication drift")

    root_sel = json.loads((out / "root-selection.json").read_text(encoding="utf-8"))
    expected_ids = [int(row["parent_id"]) for row in selected]
    expected_fps = [row["canonical_fingerprint"] for row in selected]
    if root_sel.get("parent_ids") != expected_ids or root_sel.get("canonical_fingerprints") != expected_fps:
        raise StageError("2000 root selection/order drift")
    if [int(x) for x in (out / "full-root-ids.txt").read_text().split()] != expected_ids:
        raise StageError("2000 root id file drift")

    rows = base.read_tsv(out / "per_root.tsv")
    if len(rows) != ROOTS * len(SHALLOW_BUDGETS) * 3:
        raise StageError("2000 per_root cardinality drift")
    counts = {}
    for engine in ("JASS_PARITY", "JASS_PROFILE", "SCAN"):
        for budget in SHALLOW_BUDGETS:
            n = sum(r.get("engine") == engine and int(r.get("budget", -1)) == budget for r in rows)
            counts[f"{engine}:{budget}"] = n
            if n != ROOTS:
                raise StageError(f"2000 per_root shape drift {engine}/{budget}")
    auth = {
        "schema": "jass.cls_mirror_source_authentication.v1", "authenticated": True,
        "job_id": SOURCE_JOB, "attempt_id": SOURCE_ATTEMPT, "code_sha": SOURCE_CODE,
        "receipt_sha256": SOURCE_RECEIPT_SHA256, "per_root_sha256": base.sha_file(out / "per_root.tsv"),
        "cohort_identity_sha256": base.COHORT_SHA, "roots": ROOTS, "row_counts": counts,
        "target_reads": 0, "fits": 0, "strength_games": 0, "alpha_spent": 0,
    }
    base.atomic_write(artifacts / "source-authentication.json", base.canonical_json(auth))
    return out / "per_root.tsv"


def build_deep_jass(work: Path) -> Path:
    if not base.EGDB_DIR.is_dir() or not base.EGDB_SRC.is_dir():
        raise StageError("required CPX EGDB directories absent")
    build = work / "build-deep-parity"
    base.run([
        "/usr/bin/cmake", "-S", str(ROOT), "-B", str(build), "-G", "Unix Makefiles",
        "-DCMAKE_BUILD_TYPE=Release", "-DJASS_EGDB=ON", f"-DJASS_EGDB_SRC_DIR={base.EGDB_SRC}",
        "-DJASS_ENDGAME_FEATURES=ON", "-DJASS_KING_MOBILITY=ON", "-DJASS_SCAN_PARITY=ON",
        "-DJASS_TEMPO_STAGE=ON", "-DJASS_TIME_BREAKDOWN=OFF",
    ], timeout=240, log=work / "cmake-deep-configure.log")
    base.run(["/usr/bin/cmake", "--build", str(build), "--target", "jass_lib", "egdb_intl",
              "jass_t3_f6_runtime", "-j", "8"], timeout=900, log=work / "cmake-deep-build.log")
    exe = work / "cls-mirror-scale-jass"
    base.run([
        "/usr/bin/c++", "-std=c++20", "-O2", "-march=native", "-DJASS_EGDB=1",
        "-DJASS_ENDGAME_FEATURES=1", "-DJASS_KING_MOBILITY=1", "-DJASS_SCAN_PARITY=1",
        "-DJASS_TEMPO_STAGE=1", f"-I{ROOT / 'src'}", f"-I{ROOT / 'pattern_jass/src'}",
        f"-I{base.EGDB_SRC}", str(ROOT / "jobs/tools/cls_mirror_scale_jass.cpp"),
        str(build / "CMakeFiles/jass_t3_f6_runtime.dir/src/residual_features.cpp.o"),
        str(build / "CMakeFiles/jass_t3_f6_runtime.dir/src/t3_f6.cpp.o"),
        "-o", str(exe), "-Wl,--start-group", str(build / "libjass_lib.a"),
        str(build / "libegdb_intl.a"), "-Wl,--end-group", "-pthread",
    ], timeout=300, log=work / "link-deep.log")
    exe.chmod(0o555)
    return exe


def run_deep(exe: Path, parents: Path, ids: Path, curriculum: Path, output: Path, report: Path, log: Path) -> None:
    base.run([str(exe), str(parents), str(ids), str(output), str(report), str(curriculum), str(base.EGDB_DIR)],
             timeout=2400, log=log, env=base.sanitized_env())


def aggregate(shallow_rows: list[dict[str, str]], deep_rows: list[dict[str, str]],
              selected: Sequence[dict[str, str]]) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    phase_of = {row["parent_id"]: row["phase"] for row in selected}
    parity = {(r["root_id"], int(r["budget"])): r for r in shallow_rows if r["engine"] == "JASS_PARITY"}
    scan = {(r["root_id"], int(r["budget"])): r for r in shallow_rows if r["engine"] == "SCAN"}
    deep = {r["root_id"]: r for r in deep_rows}
    if len(deep) != ROOTS or len(parity) != ROOTS * len(SHALLOW_BUDGETS) or len(scan) != len(parity):
        raise StageError("paired mirror shape drift")
    if set(deep) != {row["parent_id"] for row in selected}:
        raise StageError("deep reference identities drift")
    overall = {}
    by_phase = {phase: {} for phase in PHASES}
    vectors = {phase: [] for phase in PHASES}
    for budget in SHALLOW_BUDGETS:
        mirror_vals, cross_vals = [], []
        for row in selected:
            root = row["parent_id"]
            key = (root, budget)
            if key not in parity or key not in scan:
                raise StageError(f"missing paired mirror row {root}/{budget}")
            mirror_vals.append(1.0 if parity[key]["bestmove_canonical"] == deep[root]["bestmove_canonical"] else 0.0)
            cross_vals.append(1.0 if parity[key]["bestmove_canonical"] == scan[key]["bestmove_canonical"] else 0.0)
        m, c = float(np.mean(mirror_vals)), float(np.mean(cross_vals))
        overall[str(budget)] = {"mirror_agreement": m, "cross_engine_agreement": c, "mirror_excess": m - c}
        for phase in PHASES:
            ids = [r["parent_id"] for r in selected if r["phase"] == phase]
            mv = [1.0 if parity[(root, budget)]["bestmove_canonical"] == deep[root]["bestmove_canonical"] else 0.0 for root in ids]
            cv = [1.0 if parity[(root, budget)]["bestmove_canonical"] == scan[(root, budget)]["bestmove_canonical"] else 0.0 for root in ids]
            mm, cc = float(np.mean(mv)), float(np.mean(cv))
            by_phase[phase][str(budget)] = {"mirror_agreement": mm, "cross_engine_agreement": cc, "mirror_excess": mm - cc}
    for phase in PHASES:
        for row in [r for r in selected if r["phase"] == phase]:
            root = row["parent_id"]
            vec = []
            for budget in SHALLOW_BUDGETS:
                key = (root, budget)
                m = 1.0 if parity[key]["bestmove_canonical"] == deep[root]["bestmove_canonical"] else 0.0
                c = 1.0 if parity[key]["bestmove_canonical"] == scan[key]["bestmove_canonical"] else 0.0
                vec.extend((m, c, m - c))
            vectors[phase].append(vec)
    arrays = {phase: np.asarray(values, dtype=np.float64) for phase, values in vectors.items()}
    depths = np.asarray([float(deep[r["parent_id"]]["completed_nominal_depth"]) for r in selected])
    nps = np.asarray([float(deep[r["parent_id"]]["nps"]) for r in selected])
    nodes = np.asarray([float(deep[r["parent_id"]]["nodes_observed"]) for r in selected])
    return ({
        "schema": "jass.cls_mirror_scale_aggregates.v1", "diagnostic_only": True,
        "roots": ROOTS, "roots_per_phase": ROOTS_PER_PHASE, "deep_budget_nodes": DEEP_BUDGET,
        "shallow_budgets_nodes": list(SHALLOW_BUDGETS), "overall": overall, "by_phase": by_phase,
        "deep_reference": {"mean_completed_nominal_depth": float(depths.mean()),
                           "median_completed_nominal_depth": float(np.median(depths)),
                           "mean_nps": float(nps.mean()), "median_nps": float(np.median(nps)),
                           "mean_nodes_observed": float(nodes.mean())},
        "classification": None,
    }, arrays)


def bootstrap(arrays: dict[str, np.ndarray]) -> dict[str, object]:
    labels = []
    for budget in SHALLOW_BUDGETS:
        labels += [f"mirror_agreement_{budget}", f"cross_engine_agreement_{budget}", f"mirror_excess_{budget}"]
    samples = np.zeros((BOOTSTRAP_REPLICATES, len(labels)), dtype=np.float64)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    chunk = 1000
    for phase in PHASES:
        values = arrays[phase]
        if values.shape != (ROOTS_PER_PHASE, len(labels)):
            raise StageError(f"mirror bootstrap shape drift {phase}: {values.shape}")
        for start in range(0, BOOTSTRAP_REPLICATES, chunk):
            stop = min(start + chunk, BOOTSTRAP_REPLICATES)
            idx = rng.integers(0, ROOTS_PER_PHASE, size=(stop - start, ROOTS_PER_PHASE))
            samples[start:stop] += values[idx].mean(axis=1) / len(PHASES)
    q = np.quantile(samples, [0.025, 0.5, 0.975], axis=0)
    return {"schema": "jass.cls_mirror_scale_bootstrap.v1", "unit": "root_id",
            "phase_stratified": True, "replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED,
            "metrics": {label: {"q025": float(q[0, i]), "median": float(q[1, i]), "q975": float(q[2, i])}
                        for i, label in enumerate(labels)}}


def run_stage(work: Path, artifacts: Path) -> dict[str, object]:
    mode = os.environ.get("LAUNCH_MODE")
    if mode not in {"rehearsal", "production"}:
        raise StageError("LAUNCH_MODE must be rehearsal or production")
    if work.exists() or work.is_symlink():
        raise StageError("work directory must be absent")
    work.mkdir(parents=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    if os.statvfs(str(artifacts)).f_bavail * os.statvfs(str(artifacts)).f_frsize < 3 * 1024**3:
        raise StageError("less than 3 GiB free before CLS mirror diagnostic")
    started = time.monotonic()
    parents, _metadata, deep_tsv, curriculum, _scan = base.fetch_inputs(work)
    ids = work / "full-root-ids.txt"
    selected = full.select_full(deep_tsv, ids)
    base.atomic_write(artifacts / "full-root-ids.txt", ids.read_bytes())
    base.atomic_write(artifacts / "root-selection.json", base.canonical_json({
        "schema": "jass.cls_mirror_root_selection.v1", "roots": ROOTS,
        "per_phase": ROOTS_PER_PHASE, "order": "authenticated deep512.tsv source order",
        "parent_ids": [int(r["parent_id"]) for r in selected],
        "canonical_fingerprints": [r["canonical_fingerprint"] for r in selected],
        "cohort_identity_sha256": base.COHORT_SHA,
    }))
    source_per_root = authenticate_source(work, artifacts, selected)
    exe = build_deep_jass(work)
    deep_out, deep_report = work / "deep-reference.tsv", work / "deep-reference.json"
    run_deep(exe, parents, ids, curriculum, deep_out, deep_report, work / "deep-reference.log")
    deep_rows = base.read_tsv(deep_out)
    if len(deep_rows) != ROOTS or any(int(r.get("budget", -1)) != DEEP_BUDGET for r in deep_rows):
        raise StageError("deep reference output shape/budget drift")
    base.atomic_write(artifacts / "deep_reference.tsv", deep_out.read_bytes())
    shallow_rows = base.read_tsv(source_per_root)
    aggregates, arrays = aggregate(shallow_rows, deep_rows, selected)
    boot = bootstrap(arrays)
    evidence = {"schema": "jass.cls_mirror_scale_evidence.v1", "diagnostic_only": True,
                "classification": None, "interpretation": "bias-bound descriptive contrast only",
                "overall": aggregates["overall"], "bootstrap": boot["metrics"],
                "note": "Positive mirror excess can indicate same-engine/evaluator convergence explains part of cross-engine divergence; it is not causal attribution."}
    base.atomic_write(artifacts / "aggregates.json", base.canonical_json(aggregates))
    base.atomic_write(artifacts / "bootstrap.json", base.canonical_json(boot))
    base.atomic_write(artifacts / "mirror-evidence.json", base.canonical_json(evidence))
    terminal = REHEARSAL_TERMINAL if mode == "rehearsal" else PRODUCTION_TERMINAL
    manifest = {"schema": "jass.cls_mirror_scale_manifest.v1", "terminal": terminal, "mode": mode,
                "diagnostic_only": True, "cohort_identity_sha256": base.COHORT_SHA,
                "curriculum_sha256": base.CURRICULUM_SHA, "source_job": SOURCE_JOB,
                "source_attempt": SOURCE_ATTEMPT, "source_receipt_sha256": SOURCE_RECEIPT_SHA256,
                "roots": ROOTS, "roots_per_phase": ROOTS_PER_PHASE,
                "shallow_budgets_nodes": list(SHALLOW_BUDGETS), "deep_budget_nodes": DEEP_BUDGET,
                "bootstrap_replicates": BOOTSTRAP_REPLICATES, "bootstrap_seed": BOOTSTRAP_SEED,
                "new_jass_searches": ROOTS, "new_scan_searches": 0,
                "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
                "fits": 0, "strength_games": 0, "selfplay_games": 0, "alpha_spent": 0,
                "promotions": 0, "bakes": 0, "elapsed_seconds": time.monotonic() - started}
    base.atomic_write(artifacts / "manifest.json", base.canonical_json(manifest))
    lines = ["# CLS-D mirror-scale V1", "", f"Terminal: `{terminal}`.", "",
             f"Frozen DEEP512 roots: {ROOTS} ({ROOTS_PER_PHASE}/phase). Deep Jass reference: {DEEP_BUDGET:,} exact requested nodes.", "",
             "| shallow budget | Jass→Jass1M | Jass→Scan same budget | mirror excess |", "|---:|---:|---:|---:|"]
    for b in SHALLOW_BUDGETS:
        x = aggregates["overall"][str(b)]
        lines.append(f"| {b:,} | {x['mirror_agreement']:.6f} | {x['cross_engine_agreement']:.6f} | {x['mirror_excess']:.6f} |")
    lines += ["", f"Bootstrap: {BOOTSTRAP_REPLICATES} paired phase-stratified root replicates, seed `{BOOTSTRAP_SEED}`.",
              "", "Descriptive bias-bound evidence only. No final CLS bottleneck classification, promotion, bake or scale-up."]
    base.atomic_write(artifacts / "RESULTS.md", ("\n".join(lines) + "\n").encode())
    summary = {"schema": SCHEMA, "state": "completed", "terminal": terminal, "scientific_verdict": None,
               "diagnostic_only": True, "mode": mode, "roots": ROOTS, "deep_budget_nodes": DEEP_BUDGET,
               "bootstrap_replicates": BOOTSTRAP_REPLICATES, "bootstrap_seed": BOOTSTRAP_SEED,
               "next_stage": "QUEUE_EXACT_PRODUCTION_SAME_COMMON_SPEC" if mode == "rehearsal" else "CONTINUE_CLS_DIAGNOSTICS_PER_MASTER_PLAN",
               "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
               "new_jass_searches": ROOTS, "new_scan_searches": 0, "fits": 0,
               "strength_games": 0, "selfplay_games": 0, "alpha_spent": 0, "promotions": 0, "bakes": 0}
    base.atomic_write(artifacts / "scientific-summary.json", base.canonical_json(summary))
    return summary


def main() -> int:
    result = Path(os.environ["JASS_RESULT_DIR"])
    artifacts = Path(os.environ["JASS_ARTEFACT_DIR"])
    try:
        run_stage(result / "cls-mirror-scale-work", artifacts)
        return 0
    except BaseException as exc:
        artifacts.mkdir(parents=True, exist_ok=True)
        base.atomic_write(artifacts / "scientific-summary.json", base.canonical_json({
            "schema": SCHEMA, "state": "failed", "terminal": TECHNICAL_TERMINAL,
            "scientific_verdict": None, "classification": "TECHNICAL",
            "error_type": type(exc).__name__, "error": str(exc)[:2000],
            "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
            "fits": 0, "strength_games": 0, "selfplay_games": 0, "alpha_spent": 0,
            "promotions": 0, "bakes": 0,
        }))
        print(f"CLS mirror TECHNICAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
