#!/usr/bin/env python3
"""Run the preregistered B3 fresh 1,000-parent complete full-ladder reference audit.

This stage consumes only the sealed target-blind audit subset, then reuses the
unchanged B2 full-teacher renderer to execute 5k/50k/200k exact-node searches
for every unresolved legal sibling.  The resulting reference artifact family is
physically separate from the adaptive corpus and cannot backfill adaptive labels.
No fit, game, promotion or bake is reachable here.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import adaptive_sibling_b2_teacher_source as full_teacher  # noqa: E402
from jobs.tools import adaptive_sibling_b3_fresh_audit_subset as audit_subset  # noqa: E402
from jobs.tools import adaptive_sibling_b3_parity_stage as parity_stage  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b3_fresh_full_ladder_audit.v1"
VERDICT = "B3_FRESH_FULL_LADDER_AUDIT_COMPLETE_V1"
AUDIT_PARENTS = 1_000
SHARDS = 16
TT_MB = 16
EGDB_CACHE_MB = 256
TEACHER_TIMEOUT_SECONDS = 390
SOURCE_JOB = "cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1"
SOURCE_ATTEMPT = "20260906T141235Z-29084b25"
SOURCE_CODE_SHA = "29084b25789b1a88c19a86f73c476eedc52acbc6"
SOURCE_PREFIX = (
    "r2:jass-data/runs/cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1/"
    "20260906T141235Z-29084b25"
)


class StageError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return parity_stage.canonical(value)


def write_new(path: Path, raw: bytes) -> None:
    parity_stage.write_new(path, raw)


def descriptor(path: Path, **extra: object) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise StageError(f"not a regular file: {path}")
    return {"local_name": path.name, "sha256": parity_stage.sha_file(path),
            "size_bytes": path.stat().st_size, **extra}


def _matches_descriptor(value: object, path: Path, **extras: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    expected = descriptor(path, **extras)
    return all(value.get(key) == item for key, item in expected.items())


def fetch_and_verify_subset(args: argparse.Namespace, work: Path) -> tuple[Path, dict[str, Any]]:
    root = work / "audit-subset"
    mappings = [
        ("artefacts/b3-fresh-audit-subset-seal.json", "b3-fresh-audit-subset-seal.json"),
        ("artefacts/b3-fresh-audit-parents.jnnw", "b3-fresh-audit-parents.jnnw"),
        ("artefacts/b3-fresh-audit-parents.tsv", "b3-fresh-audit-parents.tsv"),
        ("artefacts/b3-fresh-audit-identities.txt", "b3-fresh-audit-identities.txt"),
        ("artefacts/b3-fresh-audit-source-parent-ids.txt", "b3-fresh-audit-source-parent-ids.txt"),
    ]
    parity_stage.fetch_completed(
        args.subset_prefix, job=args.subset_job, attempt=args.subset_attempt,
        expected_code=args.subset_code_sha, mappings=mappings,
        out_dir=root, report=work / "audit-subset-fetch.json",
    )
    seal_path = root / "b3-fresh-audit-subset-seal.json"
    try:
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StageError("invalid B3 audit subset seal JSON") from exc
    if seal.get("schema") != audit_subset.SCHEMA or seal.get("verdict") != audit_subset.VERDICT \
            or seal.get("state") != "completed":
        raise StageError("B3 audit subset seal schema/verdict/state mismatch")
    audit = seal.get("audit")
    expected_audit = {
        "seed": audit_subset.AUDIT_SEED,
        "parents": AUDIT_PARENTS,
        "per_cell": audit_subset.AUDIT_PER_CELL,
        "selection": "sha256(seed_decimal:canonical_fingerprint), lowest per cell",
        "tie_break": ["canonical_fingerprint_ascii", "source_parent_id_uint"],
        "target_blind": True,
    }
    if audit != expected_audit:
        raise StageError("B3 audit subset frozen selection contract mismatch")
    source = seal.get("source")
    if not isinstance(source, Mapping):
        raise StageError("B3 audit subset source identity missing")
    expected_source = {
        "job_id": SOURCE_JOB, "attempt_id": SOURCE_ATTEMPT,
        "code_sha": SOURCE_CODE_SHA, "prefix": SOURCE_PREFIX,
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            raise StageError(f"B3 audit subset source {key} mismatch")
    if any(seal.get(key) != 0 for key in (
        "teacher_score_reads", "teacher_label_reads", "reference_audit_reads",
        "fits", "strength_games", "promotions", "bakes",
    )):
        raise StageError("B3 audit subset seal reports forbidden reads/side effects")
    outputs = seal.get("outputs")
    if not isinstance(outputs, Mapping):
        raise StageError("B3 audit subset outputs missing")
    paths = {
        "parents_jnnw": (root / "b3-fresh-audit-parents.jnnw",
                         {"records": AUDIT_PARENTS, "record_size_bytes": 38}),
        "parents_tsv": (root / "b3-fresh-audit-parents.tsv", {"rows": AUDIT_PARENTS}),
        "ordered_identities": (
            root / "b3-fresh-audit-identities.txt",
            {"rows": AUDIT_PARENTS,
             "serialization": "canonical_fingerprint_ascii, one per line, LF terminated"}),
        "source_parent_ids": (
            root / "b3-fresh-audit-source-parent-ids.txt",
            {"rows": AUDIT_PARENTS,
             "serialization": "source_parent_id_decimal, one per line, LF terminated"}),
    }
    for key, (path, extras) in paths.items():
        if not _matches_descriptor(outputs.get(key), path, **extras):
            raise StageError(f"B3 audit subset {key} descriptor mismatch")
    cells = outputs.get("cells")
    if not isinstance(cells, Mapping) or len(cells) != 8 \
            or set(cells.values()) != {audit_subset.AUDIT_PER_CELL}:
        raise StageError("B3 audit subset cell counts mismatch")

    parents = root / "b3-fresh-audit-parents.jnnw"
    raw = parents.read_bytes()
    if len(raw) != 8 + 38 * AUDIT_PARENTS or raw[:4] != b"JNNW" \
            or int.from_bytes(raw[4:8], "little") != AUDIT_PARENTS:
        raise StageError("B3 audit parent JNNW count/size mismatch")
    for index in range(AUDIT_PARENTS):
        target = 8 + 38 * index + 33
        if raw[target:target + 5] != b"\0" * 5:
            raise StageError(f"B3 audit parent target bytes nonzero at {index}")
    return parents, seal


def build_full_teacher(work: Path) -> tuple[Path, dict[str, Any]]:
    if not parity_stage.EGDB_DIR.is_dir() or not parity_stage.EGDB_SRC.is_dir():
        raise StageError("required CPX EGDB directories are absent")
    if not any(path.name.startswith("db7-") for path in parity_stage.EGDB_DIR.iterdir()
               if path.is_file()):
        raise StageError("EGDB7 data absent")
    generated = work / "rendered-b3-full-ladder-audit-teacher.cpp"
    receipt_path = work / "b3-full-ladder-render-receipt.json"
    try:
        receipt = full_teacher.render_file(
            ROOT / "src/deep_sibling_teacher.cpp", generated, receipt_path)
    except (OSError, ValueError) as exc:
        raise StageError(f"full teacher render failed: {exc}") from exc
    if receipt.get("budgets_nodes") != [5_000, 50_000, 200_000] \
            or receipt.get("fresh_engine_each_search") is not True \
            or receipt.get("engine_constructions_per_sibling") != 3 \
            or receipt.get("node_limit_mode") != "exact" \
            or receipt.get("egdb_cache_mb") != EGDB_CACHE_MB \
            or receipt.get("frozen_budgets_columns_and_score_semantics_changed") is not False:
        raise StageError("full teacher render receipt contract mismatch")

    build = work / "build"
    parity_stage.run([
        "/usr/bin/cmake", "-S", str(ROOT), "-B", str(build), "-G", "Unix Makefiles",
        "-DCMAKE_BUILD_TYPE=Release", "-DJASS_EGDB=ON",
        f"-DJASS_EGDB_SRC_DIR={parity_stage.EGDB_SRC}",
        "-DJASS_ENDGAME_FEATURES=ON", "-DJASS_KING_MOBILITY=ON",
        "-DJASS_SCAN_PARITY=ON", "-DJASS_TEMPO_STAGE=ON",
    ], timeout=240, log=work / "cmake-configure.log")
    parity_stage.run([
        "/usr/bin/cmake", "--build", str(build), "--target", "jass_lib", "egdb_intl",
        "jass_t3_f6_runtime", "-j", "8",
    ], timeout=900, log=work / "cmake-build.log")
    exe = work / "jass_b3_full_ladder_audit_teacher"
    parity_stage.run([
        "/usr/bin/c++", "-std=c++20", "-O2", "-march=native", "-DJASS_EGDB=1",
        f"-I{ROOT / 'src'}", f"-I{ROOT / 'pattern_jass/src'}",
        f"-I{parity_stage.EGDB_SRC}", str(generated),
        str(build / "CMakeFiles/jass_t3_f6_runtime.dir/src/residual_features.cpp.o"),
        str(build / "CMakeFiles/jass_t3_f6_runtime.dir/src/t3_f6.cpp.o"),
        "-o", str(exe), "-Wl,--start-group", str(build / "libjass_lib.a"),
        str(build / "libegdb_intl.a"), "-Wl,--end-group", "-pthread",
    ], timeout=240, log=work / "b3-full-ladder-link.log")
    exe.chmod(0o755)
    return exe, receipt


def _int(report: Mapping[str, Any], key: str, lo: int = 0,
         hi: int = (1 << 64) - 1) -> int:
    value = report.get(key)
    if type(value) is not int or not lo <= value <= hi:
        raise StageError(f"full audit report {key} invalid")
    return value


def validate_full_report(report: Mapping[str, Any], expected_shard: int) -> None:
    if frozenset(report) != full_teacher.SHARD_REPORT_KEYS:
        raise StageError("full audit shard report field set mismatch")
    expected = {
        "schema": full_teacher.SHARD_SCHEMA,
        "input_parents": AUDIT_PARENTS,
        "shard": expected_shard,
        "nshards": SHARDS,
        "book_enabled": False,
        "threads_per_search": 1,
        "fresh_tt_each_search": True,
        "fresh_engine_each_search": True,
        "jass_prefixed_environment_count": 0,
        "egdb_configuration_source": "explicit_positional_arguments",
        "egdb_required_available": True,
        "egdb_cache_mb": EGDB_CACHE_MB,
        "node_limit_mode": "exact",
        "cheap_budget_nodes": 5_000,
        "screen_budget_nodes": 50_000,
        "teacher_budget_nodes": 200_000,
        "tt_mb": TT_MB,
        "teacher_scores_produced": True,
        "stable_pairs_selected": False,
        "fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    for key, value in expected.items():
        if report.get(key) != value or type(report.get(key)) is not type(value):
            raise StageError(f"full audit shard {expected_shard} {key} mismatch")
    _int(report, "egdb_max_pieces", 1, 40)
    if _int(report, "source_rows") != AUDIT_PARENTS:
        raise StageError("full audit source_rows mismatch")
    processed = len(range(expected_shard, AUDIT_PARENTS, SHARDS))
    if _int(report, "processed_parent_rows") != processed or _int(report, "invalid_rows") != 0:
        raise StageError("full audit processed/invalid parent count mismatch")
    emitted = _int(report, "emitted_siblings")
    if not 2 * processed <= emitted <= 16 * processed:
        raise StageError("full audit emitted siblings outside frozen support")
    if _int(report, "rule_terminal_children") + _int(report, "exact_tb_children") > emitted:
        raise StageError("full audit exact child counters exceed siblings")
    for key in ("cheap_searches", "screen_searches", "teacher_searches"):
        if _int(report, key) != emitted:
            raise StageError(f"full audit {key} must equal emitted siblings")
    if _int(report, "engine_constructions") != 3 * emitted:
        raise StageError("full audit Engine constructions must equal 3*emitted")
    for key, budget in (("cheap_nodes", 5_000), ("screen_nodes", 50_000),
                        ("teacher_nodes", 200_000)):
        if _int(report, key) > emitted * budget:
            raise StageError(f"full audit {key} exceeds exact-node cap")


def run_shards(exe: Path, parents: Path, curriculum: Path, work: Path) -> list[dict[str, Any]]:
    shard_root = work / "shards"
    shard_root.mkdir()
    processes: list[tuple[int, subprocess.Popen[bytes], Any]] = []
    env = parity_stage.sanitized_teacher_env()
    started = time.monotonic()
    for shard in range(SHARDS):
        child = shard_root / f"children-{shard:02d}.jnnw"
        groups = shard_root / f"groups-{shard:02d}.tsv"
        report = shard_root / f"report-{shard:02d}.json"
        log_path = shard_root / f"teacher-{shard:02d}.log"
        handle = log_path.open("wb")
        argv = [str(exe), str(parents), str(child), str(groups), str(report),
                str(curriculum), str(parity_stage.EGDB_DIR), str(shard), str(SHARDS),
                str(TT_MB), str(EGDB_CACHE_MB)]
        process = subprocess.Popen(
            argv, cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT, env=env)
        processes.append((shard, process, handle))
    deadline = time.monotonic() + TEACHER_TIMEOUT_SECONDS
    try:
        while processes and time.monotonic() < deadline:
            alive = []
            for shard, process, handle in processes:
                rc = process.poll()
                if rc is None:
                    alive.append((shard, process, handle))
                else:
                    handle.close()
                    if rc != 0:
                        log = shard_root / f"teacher-{shard:02d}.log"
                        raise StageError(
                            f"full audit teacher shard {shard} failed rc={rc}: "
                            + "\n".join(log.read_text(errors="replace").splitlines()[-80:]))
            processes = alive
            if processes:
                time.sleep(0.25)
        if processes:
            raise StageError("full audit teacher shards exceeded frozen 390 s bound")
    except BaseException:
        for _shard, process, handle in processes:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
            if not handle.closed:
                handle.close()
        raise
    reports: list[dict[str, Any]] = []
    for shard in range(SHARDS):
        try:
            report = json.loads((shard_root / f"report-{shard:02d}.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise StageError(f"invalid full audit report shard {shard}") from exc
        if not isinstance(report, dict):
            raise StageError(f"full audit report shard {shard} is not an object")
        validate_full_report(report, shard)
        reports.append(report)
    write_new(work / "full-audit-duration.json", canonical({
        "schema": "jass.adaptive_sibling_b3_fresh_full_ladder_duration.v1",
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "shards": SHARDS,
        "timeout_seconds": TEACHER_TIMEOUT_SECONDS,
    }))
    return reports


def aggregate_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(reports) != SHARDS:
        raise StageError("full audit requires exactly 16 shard reports")
    for shard, report in enumerate(reports):
        validate_full_report(report, shard)
    fields = full_teacher.SUM_FIELDS
    sums = {field: sum(int(report[field]) for report in reports) for field in fields}
    emitted = sums["emitted_siblings"]
    if sums["processed_parent_rows"] != AUDIT_PARENTS:
        raise StageError("full audit aggregate did not process exactly 1000 parents")
    if sums["invalid_rows"] != 0:
        raise StageError("full audit aggregate contains invalid parents")
    if not (sums["cheap_searches"] == emitted == sums["screen_searches"]
            == sums["teacher_searches"]):
        raise StageError("full audit aggregate did not execute complete ladder")
    if sums["engine_constructions"] != 3 * emitted:
        raise StageError("full audit aggregate Engine count mismatch")
    return {
        "schema": "jass.adaptive_sibling_b3_fresh_full_ladder_aggregate.v1",
        "input_parents": AUDIT_PARENTS,
        "shards": SHARDS,
        "budgets_nodes": [5_000, 50_000, 200_000],
        "full_ladder_executed": True,
        "fresh_engine_each_search": True,
        "book_enabled": False,
        "threads_per_search": 1,
        "tt_mb": TT_MB,
        "egdb_cache_mb": EGDB_CACHE_MB,
        **sums,
    }


def run_stage(args: argparse.Namespace) -> dict[str, object]:
    if args.work_dir.exists() or args.work_dir.is_symlink():
        raise StageError("work-dir must be absent")
    args.work_dir.mkdir(parents=True)
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    parents, subset_seal = fetch_and_verify_subset(args, args.work_dir)
    curriculum = parity_stage.fetch_curriculum(args.work_dir)
    exe, render_receipt = build_full_teacher(args.work_dir)
    reports = run_shards(exe, parents, curriculum, args.work_dir)
    groups = parity_stage.merge_groups(args.work_dir)
    aggregate = aggregate_reports(reports)
    groups_out = args.artifact_dir / "b3-fresh-full-ladder-audit-groups.tsv"
    shutil.copyfile(groups, groups_out)
    subset_identity = {
        "job_id": args.subset_job,
        "attempt_id": args.subset_attempt,
        "code_sha": args.subset_code_sha,
        "prefix": args.subset_prefix,
        "seal_sha256": parity_stage.sha_file(
            args.work_dir / "audit-subset/b3-fresh-audit-subset-seal.json"),
        "parents_jnnw": subset_seal["outputs"]["parents_jnnw"],
        "ordered_identities": subset_seal["outputs"]["ordered_identities"],
        "source_parent_ids": subset_seal["outputs"]["source_parent_ids"],
    }
    summary = {
        "schema": SCHEMA,
        "state": "completed",
        "verdict": VERDICT,
        "audit_subset": subset_identity,
        "audit_parents": AUDIT_PARENTS,
        "audit_seed": audit_subset.AUDIT_SEED,
        "reference_only": True,
        "full_ladder_executed": True,
        "budgets_nodes": [5_000, 50_000, 200_000],
        "teacher": aggregate,
        "reference_groups": descriptor(groups_out, rows=aggregate["emitted_siblings"]),
        "rendered_source_sha256": render_receipt["rendered_source_sha256"],
        "adaptive_corpus_reads": 0,
        "adaptive_corpus_writes": 0,
        "full_ladder_backfill_authorized": False,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        "next_stage": "B3_FRESH_CORPUS_TRANSFER_READOUT",
    }
    for name, value in (
        ("b3-fresh-full-ladder-audit-aggregate.json", aggregate),
        ("b3-fresh-full-ladder-audit-render-receipt.json", render_receipt),
        ("b3-fresh-full-ladder-audit-subset-identity.json", subset_identity),
        ("scientific-summary.json", summary),
    ):
        write_new(args.artifact_dir / name, canonical(value))
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--subset-job", required=True)
    parser.add_argument("--subset-attempt", required=True)
    parser.add_argument("--subset-code-sha", required=True)
    parser.add_argument("--subset-prefix", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        summary = run_stage(parse_args(argv))
    except Exception as exc:
        print(f"adaptive_sibling_b3_fresh_full_ladder_audit: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"state": summary["state"], "verdict": summary["verdict"],
                      "next_stage": summary["next_stage"]},
                     sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
