#!/usr/bin/env python3
"""Launch-V2 stage for the preregistered CLS-D depth/growth rehearsal.

Rehearsal only: authenticate the frozen Scan-ceiling DEEP512 cohort and pinned
Scan/CURRICULUM runtime, select 32 deterministic roots (8/phase), build Jass
PARITY/PROFILE from the same code with only JASS_TIME_BREAKDOWN differing,
execute the frozen {5k,50k,200k} exact-node ladder, verify PARITY/PROFILE
identity, run pinned Scan on the same roots, and publish sizing evidence for the
FULL-vs-LITE production choice. No confirmation target, fit, game or alpha.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

SCHEMA = "jass.cls_depth_growth_rehearsal.v1"
TERMINAL = "CLS_DEPTH_GROWTH_REHEARSAL_READY_V1"
SELECTION_JOB = "home-1651-l3-scan-ceiling-selection-v1"
SELECTION_ATTEMPT = "20260829T133348Z-28e12fba"
SELECTION_CODE = "28e12fba0ead14def244ffc442b15937f65edc0e"
SELECTION_PREFIX = f"r2:jass-data/runs/{SELECTION_JOB}/{SELECTION_ATTEMPT}"
PREFLIGHT_JOB = "home-1650-l3-scan-ceiling-preflight-v1"
PREFLIGHT_ATTEMPT = "20260829T132800Z-28e12fba"
PREFLIGHT_CODE = SELECTION_CODE
PREFLIGHT_PREFIX = f"r2:jass-data/runs/{PREFLIGHT_JOB}/{PREFLIGHT_ATTEMPT}"
COHORT_SHA = "478abc0fe2fe1fcd8c2157f532ba796745c645ff4f03dac8fd21c2ff851f137e"
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
SCAN_BINARY_SHA = "96b80c6aec1592f856a78ad7617ca6224b26be926800a6e37ede3b26f4e9cfa1"
SCAN_EVAL_SHA = "0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba"
SCAN_INI_SHA = "dc201a7debaf98bb869fb3d6b641adb219df71b0ea22004b2d9b6f51cdb69538"
SCAN_COMMIT = "7aae17e7b7bfc47744601afb1ee7655e18983ce5"
REHEARSAL_SEED = 2026091001
BOOTSTRAP_SEED = 2026091002
BUDGETS = (5_000, 50_000, 200_000)
PHASES = ("P0", "P1", "P2", "P3")
EGDB_DIR = Path("/root/egdb_extracted/app")
EGDB_SRC = Path("/root/egdb_intl")


class StageError(RuntimeError):
    pass


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def run(argv: Sequence[str], *, cwd: Path = ROOT, timeout: int = 900,
        log: Path | None = None, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    handle = None if log is None else log.open("wb")
    try:
        cp = subprocess.run(list(argv), cwd=str(cwd),
                            stdout=subprocess.PIPE if handle is None else handle,
                            stderr=subprocess.STDOUT, timeout=timeout, check=False,
                            env=None if env is None else dict(env))
    finally:
        if handle is not None:
            handle.close()
    if cp.returncode != 0:
        tail = ""
        if log is not None and log.exists():
            tail = "\n" + "\n".join(log.read_text(errors="replace").splitlines()[-80:])
        elif cp.stdout:
            tail = "\n" + cp.stdout.decode(errors="replace")[-8000:]
        raise StageError(f"command failed rc={cp.returncode}: {' '.join(argv)}{tail}")
    return cp


def fetch_completed(prefix: str, *, job: str, attempt: str, code: str,
                    mappings: Sequence[tuple[str, str]], out_dir: Path, report: Path) -> None:
    argv = ["/usr/bin/python3", "jobs/tools/fetch_result_files.py", "--prefix", prefix,
            "--expected-state", "completed"]
    for remote, local in mappings:
        argv.extend(["--file", f"{remote}={local}"])
    argv.extend(["--out-dir", str(out_dir), "--report", str(report)])
    run(argv, timeout=600, log=report.with_suffix(".log"))
    receipt = json.loads(report.read_text(encoding="utf-8"))
    required = {"state": "verified", "result_state": "completed", "exit_code": 0,
                "job_id": job, "attempt_id": attempt, "code_sha": code, "prefix": prefix}
    for key, expected in required.items():
        if receipt.get(key) != expected:
            raise StageError(f"authenticated fetch {key} drift for {job}")


def fetch_inputs(work: Path) -> tuple[Path, Path, Path, Path, Path]:
    selection = work / "selection"
    fetch_completed(
        SELECTION_PREFIX, job=SELECTION_JOB, attempt=SELECTION_ATTEMPT, code=SELECTION_CODE,
        mappings=[
            ("artefacts/parents.jnnw.gz", "parents.jnnw.gz"),
            ("artefacts/parents.tsv", "parents.tsv"),
            ("artefacts/deep512.tsv", "deep512.tsv"),
            ("artefacts/selection-report.json", "selection-report.json"),
            ("artefacts/cohort-freeze-before-score.json", "cohort-freeze-before-score.json"),
        ],
        out_dir=selection, report=work / "verified-selection.json",
    )
    report = json.loads((selection / "selection-report.json").read_text(encoding="utf-8"))
    if report.get("schema") != "jass.scan_ceiling_target_blind_selection.v1" \
            or report.get("passed") is not True or report.get("deep512") != 512 \
            or report.get("deep512_by_phase") != {phase: 128 for phase in PHASES} \
            or report.get("forbidden_overlap") != 0 \
            or report.get("cohort_identity_sha256") != COHORT_SHA:
        raise StageError("frozen DEEP512 selection contract drift")
    if sha_file(selection / "parents.tsv") != report.get("parents_tsv_sha256") \
            or sha_file(selection / "deep512.tsv") != report.get("deep512_tsv_sha256"):
        raise StageError("selection metadata hash drift")
    parents = selection / "parents.jnnw"
    with gzip.open(selection / "parents.jnnw.gz", "rb") as source, parents.open("wb") as dest:
        shutil.copyfileobj(source, dest)
    if sha_file(parents) != report.get("parents_jnnw_sha256"):
        raise StageError("parents JNNW hash drift")

    preflight = work / "preflight"
    fetch_completed(
        PREFLIGHT_PREFIX, job=PREFLIGHT_JOB, attempt=PREFLIGHT_ATTEMPT, code=PREFLIGHT_CODE,
        mappings=[
            ("artefacts/curriculum.pjtw", "curriculum.pjtw"),
            ("artefacts/scan-home-compiled.gz", "scan-home-compiled.gz"),
            ("artefacts/scan-data-eval", "scan-data-eval"),
            ("artefacts/scan.ini", "scan.ini"),
            ("artefacts/scan-build-manifest.json", "scan-build-manifest.json"),
        ],
        out_dir=preflight, report=work / "verified-preflight.json",
    )
    if sha_file(preflight / "curriculum.pjtw") != CURRICULUM_SHA:
        raise StageError("CURRICULUM SHA drift")
    scan_dir = work / "scan-runtime"
    (scan_dir / "data").mkdir(parents=True)
    scan = scan_dir / "scan"
    with gzip.open(preflight / "scan-home-compiled.gz", "rb") as source, scan.open("wb") as dest:
        shutil.copyfileobj(source, dest)
    scan.chmod(0o555)
    shutil.copy2(preflight / "scan-data-eval", scan_dir / "data" / "eval")
    shutil.copy2(preflight / "scan.ini", scan_dir / "scan.ini")
    if sha_file(scan) != SCAN_BINARY_SHA or sha_file(scan_dir / "data" / "eval") != SCAN_EVAL_SHA \
            or sha_file(scan_dir / "scan.ini") != SCAN_INI_SHA:
        raise StageError("pinned Scan runtime bytes drift")
    return parents, selection / "parents.tsv", selection / "deep512.tsv", preflight / "curriculum.pjtw", scan


def select_rehearsal(deep_tsv: Path, out_ids: Path) -> list[dict[str, str]]:
    with deep_tsv.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"parent_id", "canonical_fingerprint", "phase"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise StageError("deep512.tsv fields drift")
        rows = list(reader)
    chosen: list[dict[str, str]] = []
    for phase in PHASES:
        candidates = [row for row in rows if row["phase"] == phase]
        if len(candidates) != 128:
            raise StageError(f"DEEP512 phase cardinality drift for {phase}")
        candidates.sort(key=lambda row: (
            hashlib.sha256(f"{REHEARSAL_SEED}:{row['canonical_fingerprint']}".encode()).hexdigest(),
            row["canonical_fingerprint"],
        ))
        chosen.extend(candidates[:8])
    if len(chosen) != 32 or len({row["parent_id"] for row in chosen}) != 32:
        raise StageError("rehearsal root selection cardinality drift")
    atomic_write(out_ids, ("\n".join(row["parent_id"] for row in chosen) + "\n").encode())
    return chosen


def build_jass(work: Path, *, profile: bool) -> Path:
    if not EGDB_DIR.is_dir() or not EGDB_SRC.is_dir():
        raise StageError("required CPX EGDB directories absent")
    name = "profile" if profile else "parity"
    build = work / f"build-{name}"
    argv = [
        "/usr/bin/cmake", "-S", str(ROOT), "-B", str(build), "-G", "Unix Makefiles",
        "-DCMAKE_BUILD_TYPE=Release", "-DJASS_EGDB=ON", f"-DJASS_EGDB_SRC_DIR={EGDB_SRC}",
        "-DJASS_ENDGAME_FEATURES=ON", "-DJASS_KING_MOBILITY=ON",
        "-DJASS_SCAN_PARITY=ON", "-DJASS_TEMPO_STAGE=ON",
        f"-DJASS_TIME_BREAKDOWN={'ON' if profile else 'OFF'}",
    ]
    run(argv, timeout=240, log=work / f"cmake-{name}-configure.log")
    run(["/usr/bin/cmake", "--build", str(build), "--target", "jass_lib", "egdb_intl",
         "jass_t3_f6_runtime", "-j", "8"], timeout=900, log=work / f"cmake-{name}-build.log")
    exe = work / f"cls-depth-growth-jass-{name}"
    compile_defs = ["-DJASS_EGDB=1", "-DJASS_ENDGAME_FEATURES=1", "-DJASS_KING_MOBILITY=1",
                    "-DJASS_SCAN_PARITY=1", "-DJASS_TEMPO_STAGE=1"]
    if profile:
        compile_defs.append("-DJASS_TIME_BREAKDOWN=1")
    run([
        "/usr/bin/c++", "-std=c++20", "-O2", "-march=native", *compile_defs,
        f"-I{ROOT / 'src'}", f"-I{ROOT / 'pattern_jass/src'}", f"-I{EGDB_SRC}",
        str(ROOT / "jobs/tools/cls_depth_growth_jass.cpp"),
        str(build / "CMakeFiles/jass_t3_f6_runtime.dir/src/residual_features.cpp.o"),
        str(build / "CMakeFiles/jass_t3_f6_runtime.dir/src/t3_f6.cpp.o"),
        "-o", str(exe), "-Wl,--start-group", str(build / "libjass_lib.a"),
        str(build / "libegdb_intl.a"), "-Wl,--end-group", "-pthread",
    ], timeout=300, log=work / f"link-{name}.log")
    exe.chmod(0o555)
    return exe


def sanitized_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("JASS_")}
    env["PATH"] = os.defpath
    return env


def run_jass(exe: Path, parents: Path, ids: Path, curriculum: Path,
             output: Path, report: Path, log: Path) -> None:
    run([str(exe), str(parents), str(ids), str(output), str(report), str(curriculum),
         str(EGDB_DIR), ",".join(str(value) for value in BUDGETS)],
        timeout=900, log=log, env=sanitized_env())


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def verify_parity(parity: Path, profile: Path) -> dict[str, object]:
    a, b = read_tsv(parity), read_tsv(profile)
    if len(a) != 96 or len(b) != 96:
        raise StageError("PARITY/PROFILE rehearsal row cardinality drift")
    keys = ("root_id", "budget", "nodes_observed", "completed_nominal_depth",
            "effective_depth", "bestmove_canonical", "score_cp", "branching",
            "forced_capture_at_root", "max_capture_len", "pieces", "stm")
    mismatches = []
    for index, (left, right) in enumerate(zip(a, b)):
        bad = {key: (left.get(key), right.get(key)) for key in keys if left.get(key) != right.get(key)}
        if bad:
            mismatches.append({"row": index, "fields": bad})
    if mismatches:
        raise StageError(f"Jass PARITY/PROFILE semantic mismatch: {mismatches[:3]}")
    return {"rows": len(a), "mismatches": 0, "fields_compared": list(keys)}


def run_scan(scan: Path, parents: Path, metadata: Path, ids: Path,
             output: Path, report: Path, log: Path) -> None:
    run(["/usr/bin/python3", "jobs/tools/cls_depth_growth_scan.py",
         "--scan", str(scan), "--parents", str(parents), "--metadata", str(metadata),
         "--root-ids", str(ids), "--budgets", ",".join(str(value) for value in BUDGETS),
         "--timeout-seconds", "180", "--output", str(output), "--report", str(report),
         "--source-commit", SCAN_COMMIT], timeout=1200, log=log, env=sanitized_env())


def merge_rows(parity_path: Path, profile_path: Path, scan_path: Path,
               out_path: Path) -> tuple[list[dict[str, str]], dict[str, object]]:
    parity, profile, scan = read_tsv(parity_path), read_tsv(profile_path), read_tsv(scan_path)
    shape = {(row["root_id"], row["budget"]): row for row in parity}
    fields = [
        "root_id", "phase", "stm", "pieces", "branching", "forced_capture_at_root",
        "max_capture_len", "budget_kind", "budget", "nodes_requested", "nodes_observed",
        "node_semantics", "engine", "completed_nominal_depth", "seldepth", "wall_ms", "nps",
        "bestmove_canonical", "score_cp", "terminal_flag", "qnodes", "eval_calls", "tt_hit_rate",
        "cutoffs", "first_move_cutoffs", "pvs_researches", "moves_searched",
    ]
    merged: list[dict[str, str]] = []
    for engine_name, rows in (("JASS_PARITY", parity), ("JASS_PROFILE", profile)):
        for row in rows:
            tt_probes, tt_hits = int(row["tt_probes"]), int(row["tt_hits"])
            merged.append({
                "root_id": row["root_id"], "phase": "", "stm": row["stm"], "pieces": row["pieces"],
                "branching": row["branching"], "forced_capture_at_root": row["forced_capture_at_root"],
                "max_capture_len": row["max_capture_len"], "budget_kind": "nodes", "budget": row["budget"],
                "nodes_requested": row["budget"], "nodes_observed": row["nodes_observed"],
                "node_semantics": "exact_cap; node-stopped rows equal N; complete MAX_PLY rows may end below N",
                "engine": engine_name, "completed_nominal_depth": row["completed_nominal_depth"],
                "seldepth": row["effective_depth"], "wall_ms": format(int(row["wall_us"]) / 1000.0, ".6f"),
                "nps": row["nps"], "bestmove_canonical": row["bestmove_canonical"], "score_cp": row["score_cp"],
                "terminal_flag": "0", "qnodes": row["qnodes"], "eval_calls": row["eval_calls"],
                "tt_hit_rate": format(tt_hits / tt_probes if tt_probes else 0.0, ".9f"),
                "cutoffs": row["cutoffs"], "first_move_cutoffs": row["first_move_cutoffs"],
                "pvs_researches": row["pvs_researches"], "moves_searched": row["moves_searched"],
            })
    for row in scan:
        key = (row["root_id"], row["budget"])
        base = shape.get(key)
        if base is None:
            raise StageError("Scan row lacks corresponding Jass PARITY row")
        row = dict(row)
        row["forced_capture_at_root"] = base["forced_capture_at_root"]
        row["max_capture_len"] = base["max_capture_len"]
        merged.append(row)

    # phase comes from Scan metadata rows; propagate to Jass rows.
    phases = {row["root_id"]: row["phase"] for row in scan}
    for row in merged:
        if not row.get("phase"):
            row["phase"] = phases[row["root_id"]]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader(); writer.writerows(merged)

    primary = {(r["root_id"], r["budget"]): r for r in merged if r["engine"] == "JASS_PARITY"}
    scans = {(r["root_id"], r["budget"]): r for r in merged if r["engine"] == "SCAN"}
    agreement = sum(primary[key]["bestmove_canonical"] == scans[key]["bestmove_canonical"] for key in primary)
    return merged, {"pairs": len(primary), "canonical_bestmove_agreement": agreement,
                    "agreement_rate": agreement / len(primary)}


def aggregate(merged: list[dict[str, str]], move_agreement: dict[str, object]) -> dict[str, object]:
    by_engine_budget: dict[str, dict[str, object]] = {}
    for engine in ("JASS_PARITY", "JASS_PROFILE", "SCAN"):
        for budget in BUDGETS:
            rows = [r for r in merged if r["engine"] == engine and int(r["budget"]) == budget]
            if len(rows) != 32:
                raise StageError(f"aggregate row count drift {engine}/{budget}")
            numeric = lambda field: [float(r[field]) for r in rows if r[field] not in ("NA", "")]
            depths = numeric("completed_nominal_depth"); nps = numeric("nps"); wall = numeric("wall_ms")
            by_engine_budget[f"{engine}:{budget}"] = {
                "roots": len(rows), "mean_completed_nominal_depth": sum(depths) / len(depths),
                "mean_nps": sum(nps) / len(nps), "wall_ms_sum": sum(wall),
            }
    phase_depth_delta: dict[str, dict[str, float]] = {}
    for phase in PHASES:
        phase_depth_delta[phase] = {}
        for budget in BUDGETS:
            j = [float(r["completed_nominal_depth"]) for r in merged
                 if r["engine"] == "JASS_PARITY" and r["phase"] == phase and int(r["budget"]) == budget]
            s = [float(r["completed_nominal_depth"]) for r in merged
                 if r["engine"] == "SCAN" and r["phase"] == phase and int(r["budget"]) == budget]
            phase_depth_delta[phase][str(budget)] = sum(a - b for a, b in zip(j, s)) / len(j)
    return {
        "schema": "jass.cls_depth_growth_aggregates.v1",
        "diagnostic_only": True,
        "by_engine_budget": by_engine_budget,
        "jass_minus_scan_completed_depth_by_phase": phase_depth_delta,
        "canonical_root_move": move_agreement,
        "cross_engine_depth_curve_available": False,
        "nodes_by_depth": None,
        "depth_growth_contrasts": None,
        "scaling_label_enabled": False,
        "bootstrap_replicates_for_production": 100000,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }


def run_stage(work: Path, artifacts: Path) -> dict[str, object]:
    if os.environ.get("LAUNCH_MODE") != "rehearsal":
        raise StageError("v1 implementation authorizes rehearsal only")
    if work.exists() or work.is_symlink():
        raise StageError("work directory must be absent")
    work.mkdir(parents=True); artifacts.mkdir(parents=True, exist_ok=True)
    if os.statvfs(str(artifacts)).f_bavail * os.statvfs(str(artifacts)).f_frsize < 3 * 1024**3:
        raise StageError("less than 3 GiB free before CLS-D input fetch")
    started = time.monotonic()
    parents, metadata, deep, curriculum, scan = fetch_inputs(work)
    ids = work / "rehearsal-root-ids.txt"
    selected = select_rehearsal(deep, ids)
    atomic_write(artifacts / "rehearsal-root-ids.txt", ids.read_bytes())
    atomic_write(artifacts / "root-selection.json", canonical_json({
        "schema": "jass.cls_depth_growth_root_selection.v1", "seed": REHEARSAL_SEED,
        "roots": 32, "per_phase": 8,
        "parent_ids": [int(row["parent_id"]) for row in selected],
        "canonical_fingerprints": [row["canonical_fingerprint"] for row in selected],
        "source_cohort_sha256": COHORT_SHA,
    }))

    parity_exe = build_jass(work, profile=False)
    profile_exe = build_jass(work, profile=True)
    parity_tsv, profile_tsv = work / "jass-parity.tsv", work / "jass-profile.tsv"
    parity_report, profile_report = work / "jass-parity.json", work / "jass-profile.json"
    run_jass(parity_exe, parents, ids, curriculum, parity_tsv, parity_report, work / "jass-parity.log")
    run_jass(profile_exe, parents, ids, curriculum, profile_tsv, profile_report, work / "jass-profile.log")
    parity_check = verify_parity(parity_tsv, profile_tsv)
    atomic_write(artifacts / "jass-parity-profile.json", canonical_json(parity_check))

    scan_tsv, scan_report = work / "scan.tsv", work / "scan.json"
    run_scan(scan, parents, metadata, ids, scan_tsv, scan_report, work / "scan.log")
    merged, agreement = merge_rows(parity_tsv, profile_tsv, scan_tsv, artifacts / "per_root.tsv")
    aggregates = aggregate(merged, agreement)
    atomic_write(artifacts / "aggregates.json", canonical_json(aggregates))

    primary_wall_s = sum(float(r["wall_ms"]) for r in merged
                         if r["engine"] in ("JASS_PARITY", "SCAN")) / 1000.0
    projected_full = primary_wall_s * (512 / 32)
    decision = "FULL" if projected_full <= 2400.0 else "LITE"
    sizing = {
        "schema": "jass.cls_depth_growth_sizing.v1",
        "rehearsal_roots": 32,
        "primary_wall_seconds": primary_wall_s,
        "projected_full_512_wall_seconds": projected_full,
        "hard_stage_cap_seconds": 2700,
        "full_threshold_seconds": 2400,
        "production_size_decision": decision,
        "production_roots": 512 if decision == "FULL" else 256,
        "third_adaptation_allowed": False,
    }
    atomic_write(artifacts / "sizing.json", canonical_json(sizing))
    elapsed = time.monotonic() - started
    manifest = {
        "schema": "jass.cls_depth_growth_manifest.v1",
        "terminal": TERMINAL,
        "mode": "rehearsal",
        "diagnostic_only": True,
        "cohort_identity_sha256": COHORT_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "scan": {"commit": SCAN_COMMIT, "binary_sha256": SCAN_BINARY_SHA,
                 "eval_sha256": SCAN_EVAL_SHA, "ini_sha256": SCAN_INI_SHA},
        "budgets_nodes": list(BUDGETS),
        "root_selection_seed": REHEARSAL_SEED,
        "cross_engine_depth_curve_available": False,
        "depth_curve_disable_reason": "Jass same-search per-depth snapshots are not exposed without changing frozen semantics; fresh depth-N searches are forbidden substitutes",
        "parity_profile_mismatches": 0,
        "production_size_decision": decision,
        "elapsed_seconds": elapsed,
        "target_reads": 0, "fits": 0, "strength_games": 0, "alpha_spent": 0,
        "promotion_authorized": False, "bake": False,
    }
    atomic_write(artifacts / "manifest.json", canonical_json(manifest))
    results_md = (
        "# CLS-D depth/growth V2 — rehearsal\n\n"
        f"Terminal: `{TERMINAL}`. 32 frozen DEEP512 roots (8/phase), budgets 5k/50k/200k.\n\n"
        f"Jass PARITY/PROFILE semantic mismatches: **0**. Canonical Jass/Scan root-move agreement: "
        f"{agreement['canonical_bestmove_agreement']}/{agreement['pairs']} ({agreement['agreement_rate']:.3f}).\n\n"
        f"Projected FULL-512 primary wall: **{projected_full:.1f}s**; frozen production sizing decision: **{decision}**.\n\n"
        "Cross-engine nodes-by-depth / SCALING contrasts are disabled because symmetric same-search Jass snapshots are not available; no fresh depth-N surrogate is used.\n"
    )
    atomic_write(artifacts / "RESULTS.md", results_md.encode())
    summary = {
        "schema": SCHEMA, "state": "completed", "terminal": TERMINAL,
        "scientific_verdict": None, "diagnostic_only": True,
        "rehearsal_roots": 32, "budgets_nodes": list(BUDGETS),
        "parity_profile_mismatches": 0,
        "canonical_root_move_agreement_rate": agreement["agreement_rate"],
        "cross_engine_depth_curve_available": False,
        "production_size_decision": decision,
        "projected_full_wall_seconds": projected_full,
        "next_stage": "RUN_CLS_DEPTH_GROWTH_PRODUCTION_V2",
        "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
        "new_jass_searches": 192, "new_scan_searches": 96,
        "fits": 0, "strength_games": 0, "alpha_spent": 0,
        "promotions": 0, "bakes": 0,
    }
    atomic_write(artifacts / "scientific-summary.json", canonical_json(summary))
    return summary


def main() -> int:
    result_dir = Path(os.environ["JASS_RESULT_DIR"])
    artifact_dir = Path(os.environ["JASS_ARTEFACT_DIR"])
    work = result_dir / "cls-depth-growth-work"
    try:
        run_stage(work, artifact_dir)
        return 0
    except BaseException as exc:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        failure = {
            "schema": SCHEMA, "state": "failed", "terminal": "CLS_DEPTH_GROWTH_TECHNICAL_FAILURE_V1",
            "scientific_verdict": None, "classification": "TECHNICAL",
            "error_type": type(exc).__name__, "error": str(exc)[:2000],
            "target_reads": 0, "fits": 0, "strength_games": 0, "alpha_spent": 0,
            "promotions": 0, "bakes": 0,
        }
        atomic_write(artifact_dir / "scientific-summary.json", canonical_json(failure))
        print(f"CLS-D TECHNICAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
