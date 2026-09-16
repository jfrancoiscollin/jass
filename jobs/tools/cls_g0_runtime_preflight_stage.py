#!/usr/bin/env python3
"""CPX62 identity preflight for the frozen CLS-G0 runtime gate.

Uses CURRICULUM as both parent and candidate on a deterministic 32-root subset.
This validates build, trace passivity, same-search nodes-to-depth extraction and
frozen readout mechanics before any generation-1 candidate exists.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import cls_depth_growth_stage as base  # noqa: E402
from jobs.tools import cls_search_profile_stage as profile  # noqa: E402
from jobs.tools import cls_g0_runtime_gate as gate  # noqa: E402

SCHEMA = "jass.cls_g0_runtime_tooling_preflight.v1"
TERMINAL = "CLS_G0_RUNTIME_TOOLING_PREFLIGHT_READY_V1"
TECHNICAL_TERMINAL = "CLS_G0_RUNTIME_TOOLING_PREFLIGHT_TECHNICAL_FAILURE_V1"
PREFLIGHT_SEED = 2026091606
ROOTS_PER_PHASE = 8
ROOTS = ROOTS_PER_PHASE * len(gate.PHASES)


class StageError(RuntimeError):
    pass


def canonical_json(value: object) -> bytes:
    return base.canonical_json(value)


def select_roots(deep512: Path, ids: Path, subset: Path) -> list[dict[str, str]]:
    rows = base.read_tsv(deep512)
    chosen: list[dict[str, str]] = []
    for phase in gate.PHASES:
        candidates = [row for row in rows if row.get("phase") == phase]
        if len(candidates) != gate.ROOTS_PER_PHASE:
            raise StageError(f"DEEP512 phase cardinality drift:{phase}")
        candidates.sort(key=lambda row: (
            hashlib.sha256(
                f"{PREFLIGHT_SEED}:{row['canonical_fingerprint']}".encode("utf-8")
            ).hexdigest(),
            row["canonical_fingerprint"],
        ))
        chosen.extend(candidates[:ROOTS_PER_PHASE])
    if len(chosen) != ROOTS or len({row["parent_id"] for row in chosen}) != ROOTS:
        raise StageError("preflight root cardinality drift")
    base.atomic_write(ids, ("\n".join(row["parent_id"] for row in chosen) + "\n").encode())
    fieldnames = list(chosen[0])
    with subset.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(chosen)
    return chosen


def build_probe(work: Path) -> Path:
    # Reuse the exact CLS-D parity configuration to build the production engine
    # libraries, then link only the new G0 probe against those frozen objects.
    (void_exe := base.build_jass(work, profile=False))
    if not void_exe.is_file():
        raise StageError("base parity build did not produce executable")
    build = work / "build-parity"
    exe = work / "cls-g0-runtime-probe"
    defs = [
        "-DJASS_EGDB=1", "-DJASS_ENDGAME_FEATURES=1", "-DJASS_KING_MOBILITY=1",
        "-DJASS_SCAN_PARITY=1", "-DJASS_TEMPO_STAGE=1",
    ]
    base.run([
        "/usr/bin/c++", "-std=c++20", "-O2", "-march=native", *defs,
        f"-I{ROOT / 'src'}", f"-I{ROOT / 'pattern_jass/src'}", f"-I{base.EGDB_SRC}",
        str(ROOT / "jobs/tools/cls_g0_runtime_probe.cpp"),
        str(build / "CMakeFiles/jass_t3_f6_runtime.dir/src/residual_features.cpp.o"),
        str(build / "CMakeFiles/jass_t3_f6_runtime.dir/src/t3_f6.cpp.o"),
        "-o", str(exe), "-Wl,--start-group", str(build / "libjass_lib.a"),
        str(build / "libegdb_intl.a"), "-Wl,--end-group", "-pthread",
    ], timeout=300, log=work / "link-g0-probe.log")
    exe.chmod(0o555)
    return exe


def run_probe(exe: Path, parents: Path, ids: Path, curriculum: Path,
              output: Path, report: Path, log: Path) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("JASS_")}
    env["PATH"] = os.defpath
    base.run([
        str(exe), str(parents), str(ids), str(output), str(report),
        str(curriculum), str(curriculum), str(base.EGDB_DIR),
    ], timeout=1800, log=log, env=env)


def write_subset(rows: list[dict[str, str]], roots: set[str], path: Path) -> None:
    selected = [row for row in rows if row.get("root_id") in roots]
    if len(selected) != len(roots):
        raise StageError("deep-reference subset cardinality drift")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(selected[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)


def verify_identity(probe_rows: list[dict[str, str]], roots: Sequence[str]) -> None:
    indexed = {(row["root_id"], row["arm"]): row for row in probe_rows}
    fields = (
        "nodes_observed", "completed_nominal_depth", "effective_depth",
        "bestmove_canonical", "score_cp", "target_depth", "nodes_to_target",
        "trace_attempts",
    )
    for root in roots:
        parent = indexed.get((root, "parent"))
        candidate = indexed.get((root, "candidate"))
        if parent is None or candidate is None:
            raise StageError(f"missing identity arm:{root}")
        drift = {field: (parent.get(field), candidate.get(field))
                 for field in fields if parent.get(field) != candidate.get(field)}
        if drift:
            raise StageError(f"identity semantic drift:{root}:{drift}")


def run_stage(work: Path, artifacts: Path) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    parents, _parents_meta, deep512, curriculum, _scan = base.fetch_inputs(work / "base-inputs")
    _depth_per_root, deep_reference = profile.authenticate_sources(work / "source-auth", artifacts)

    ids = work / "preflight-root-ids.txt"
    subset = work / "preflight-deep512.tsv"
    selected = select_roots(deep512, ids, subset)
    root_ids = [row["parent_id"] for row in selected]
    root_set = set(root_ids)

    deep_subset = work / "preflight-deep-reference.tsv"
    write_subset(base.read_tsv(deep_reference), root_set, deep_subset)

    exe = build_probe(work / "build")
    probe_tsv = work / "probe.tsv"
    probe_report = work / "probe-report.json"
    run_probe(exe, parents, ids, curriculum, probe_tsv, probe_report, work / "probe.log")
    report = json.loads(probe_report.read_text(encoding="utf-8"))
    if report.get("roots") != ROOTS or report.get("budget_nodes") != gate.PRIMARY_BUDGET \
            or report.get("trace_parity_roots") != ROOTS \
            or report.get("trace_parity_mismatches") != 0 \
            or report.get("nodes_to_depth_rule") != "LAST_COMPLETED_EXACT_ALL_ACTIONS_SEARCHED_AT_TARGET_DEPTH":
        raise StageError("probe report contract drift")

    probe_rows = base.read_tsv(probe_tsv)
    verify_identity(probe_rows, root_ids)
    vectors = gate.paired_vectors(probe_rows, base.read_tsv(subset),
                                  base.read_tsv(deep_subset), roots_per_phase=ROOTS_PER_PHASE)
    metrics = gate.bootstrap(vectors)
    gate_result = gate.decide(metrics)
    if gate_result.get("pass") is not True:
        raise StageError(f"identity candidate failed frozen G0 readout:{gate_result['gates']}")

    outputs = {
        "preflight-root-ids.txt": ids,
        "preflight-deep512.tsv": subset,
        "preflight-deep-reference.tsv": deep_subset,
        "probe.tsv": probe_tsv,
        "probe-report.json": probe_report,
    }
    for name, source in outputs.items():
        shutil.copy2(source, artifacts / name)
    base.atomic_write(artifacts / "gate-readout.json", canonical_json(gate_result))

    summary: dict[str, object] = {
        "schema": SCHEMA,
        "state": "completed",
        "terminal": TERMINAL,
        "scientific_verdict": None,
        "diagnostic_only": True,
        "identity_parent_candidate": True,
        "roots": ROOTS,
        "roots_per_phase": ROOTS_PER_PHASE,
        "preflight_seed": PREFLIGHT_SEED,
        "budget_nodes": gate.PRIMARY_BUDGET,
        "trace_parity_mismatches": 0,
        "g0_identity_pass": True,
        "next_stage": "OPEN_CLS_L_LEARNING_OBJECTIVE_ATTRIBUTION_PREREG",
        "target_reads": 0,
        "candidate_reads": 0,
        "control_evaluations": 0,
        "new_jass_searches": ROOTS * 3,
        "new_scan_searches": 0,
        "fits": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
    }
    base.atomic_write(artifacts / "scientific-summary.json", canonical_json(summary))
    results = (
        "# CLS-G0 runtime tooling identity preflight\n\n"
        f"Terminal: `{TERMINAL}`.\n\n"
        f"Frozen subset: {ROOTS} roots ({ROOTS_PER_PHASE}/phase), seed `{PREFLIGHT_SEED}`.\n\n"
        "CURRICULUM was used byte-identically as parent and candidate. Trace OFF/ON public search "
        "parity passed on every root before candidate-arm measurement; same-search nodes-to-depth "
        "was extracted only from final Exact/all-actions-searched aspiration receipts.\n\n"
        "The frozen G0 readout passed all four gates under identity. No fit, candidate, strength game, "
        "alpha, promotion or bake was consumed.\n"
    )
    base.atomic_write(artifacts / "RESULTS.md", results.encode("utf-8"))
    return summary


if __name__ == "__main__":
    out = Path(os.environ.get("JASS_ARTEFACT_DIR", "artifacts-cls-g0-preflight"))
    work = Path(os.environ.get("JASS_RESULT_DIR", "results-cls-g0-preflight")) / "work"
    try:
        run_stage(work, out)
    except BaseException as exc:
        out.mkdir(parents=True, exist_ok=True)
        base.atomic_write(out / "scientific-summary.json", canonical_json({
            "schema": SCHEMA, "state": "failed", "terminal": TECHNICAL_TERMINAL,
            "scientific_verdict": None, "classification": "TECHNICAL",
            "error_type": type(exc).__name__, "error": str(exc),
            "target_reads": 0, "candidate_reads": 0, "fits": 0,
            "strength_games": 0, "alpha_spent": 0, "promotions": 0, "bakes": 0,
        }))
        raise
