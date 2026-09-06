#!/usr/bin/env python3
"""Execute the B3 real adaptive-teacher parity gate on the consumed B2 cohort.

This stage owns all implementation work: authenticate/fetch immutable B2 inputs,
render/build the real adaptive teacher, run 16 one-thread shards, merge the real
outputs in canonical parent/action order, and compare them with B2 full-teacher
observations plus sealed projection receipts. No fresh cohort, fit, game,
promotion or bake is allowed.
"""
from __future__ import annotations

import argparse
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
from typing import Iterable, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import adaptive_sibling_b2_readout as b2_readout  # noqa: E402
from jobs.tools import adaptive_sibling_b2_statistical_completion_recovery as b2_recovery  # noqa: E402
from jobs.tools import adaptive_sibling_b3_parity as parity  # noqa: E402
from jobs.tools import adaptive_sibling_b3_teacher_source as teacher_source  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b3_parity_stage.v1"
B2_TEACHER_JOB = "cpx62-1801-l3-decision-math-b2-full-teacher-publish-empty-artifact-repair-v1"
B2_TEACHER_ATTEMPT = "20260905T214101Z-d3657332"
B2_TEACHER_PREFIX = f"r2:jass-data/runs/{B2_TEACHER_JOB}/{B2_TEACHER_ATTEMPT}"
X = "d3657332c3a5609a5501a9ff130f5d5c19488c7f"
CURRICULUM_JOB = "cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT = "20260814T191555Z-18c38a33"
CURRICULUM_PREFIX = f"r2:jass-data/runs/{CURRICULUM_JOB}/{CURRICULUM_ATTEMPT}"
CURRICULUM_RAW_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
CURRICULUM_GZ_SHA = "59114babe3724e17ce145616d23e34b8cd90459b7a8e0c224505d258c2b1e597"
SHARDS = 16
TEACHER_TIMEOUT_SECONDS = 390
EGDB_DIR = Path("/root/egdb_extracted/app")
EGDB_SRC = Path("/root/egdb_intl")


class StageError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise StageError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise StageError(f"refusing existing temporary {tmp}")
    try:
        tmp.write_bytes(raw)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def run(argv: Sequence[str], *, cwd: Path = ROOT, timeout: int = 900,
        log: Path | None = None, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    stdout = subprocess.PIPE if log is None else log.open("wb")
    try:
        completed = subprocess.run(
            list(argv), cwd=str(cwd), stdout=stdout, stderr=subprocess.STDOUT,
            timeout=timeout, check=False, env=None if env is None else dict(env),
        )
    finally:
        if log is not None:
            stdout.close()  # type: ignore[union-attr]
    if completed.returncode != 0:
        detail = ""
        if log is not None and log.exists():
            detail = "\n" + "\n".join(log.read_text(errors="replace").splitlines()[-80:])
        elif completed.stdout:
            detail = "\n" + completed.stdout.decode(errors="replace")[-8000:]
        raise StageError(f"command failed rc={completed.returncode}: {' '.join(argv)}{detail}")
    return completed


def fetch_completed(prefix: str, *, job: str, attempt: str,
                    mappings: Sequence[tuple[str, str]], out_dir: Path,
                    report: Path, expected_code: str | None = None) -> None:
    argv = ["/usr/bin/python3", "jobs/tools/fetch_result_files.py",
            "--prefix", prefix, "--expected-state", "completed"]
    for remote, local in mappings:
        argv.extend(["--file", f"{remote}={local}"])
    argv.extend(["--out-dir", str(out_dir), "--report", str(report)])
    run(argv, timeout=600, log=report.with_suffix(".log"))
    value = json.loads(report.read_text(encoding="utf-8"))
    required = {"state": "verified", "result_state": "completed",
                "job_id": job, "attempt_id": attempt, "prefix": prefix}
    for key, expected in required.items():
        if value.get(key) != expected:
            raise StageError(f"fetch receipt {key} mismatch for {job}")
    if expected_code is not None and value.get("code_sha") != expected_code:
        raise StageError(f"fetch receipt code_sha mismatch for {job}")


def fetch_b2_inputs(work: Path) -> tuple[Path, Path, Path]:
    teacher = work / "b2-teacher"
    fetch_completed(
        B2_TEACHER_PREFIX, job=B2_TEACHER_JOB, attempt=B2_TEACHER_ATTEMPT,
        expected_code=X,
        mappings=[
            ("artefacts/parents.jnnw", "parents.jnnw"),
            ("artefacts/merged-groups.tsv", "merged-groups.tsv"),
            ("artefacts/teacher-publication-receipt.json", "teacher-publication-receipt.json"),
        ],
        out_dir=teacher, report=work / "b2-teacher-fetch.json",
    )

    seed = work / "b2-readout-seed"
    b2_recovery.fetch_files(
        [(b2_recovery.SOURCE_MANIFEST_REMOTE, "readout-inputs.json")],
        seed, work / "b2-readout-seed-fetch.json", work / "b2-readout-seed-fetch.log")
    manifest, _ = b2_readout.read_canonical_json(seed / "readout-inputs.json")
    groups_desc = manifest["teacher_merge"]["groups_tsv"]
    groups = teacher / "merged-groups.tsv"
    if groups_desc.get("local_name") != groups.name \
            or groups_desc.get("size_bytes") != groups.stat().st_size \
            or groups_desc.get("sha256") != sha_file(groups):
        raise StageError("1801 merged-groups.tsv disagrees with authenticated 1815 manifest")

    receipt_desc = manifest["projection"]["receipts_jsonl"]
    remote = f"b2-allocation-readout-terminal/bundle/{receipt_desc['local_name']}"
    receipts_dir = work / "b2-receipts"
    b2_recovery.fetch_files(
        [(remote, "allocation-receipts.jsonl")],
        receipts_dir, work / "b2-receipts-fetch.json", work / "b2-receipts-fetch.log")
    receipts = receipts_dir / "allocation-receipts.jsonl"
    if receipt_desc.get("size_bytes") != receipts.stat().st_size \
            or receipt_desc.get("sha256") != sha_file(receipts):
        raise StageError("projection receipts disagree with authenticated 1815 manifest")
    return teacher / "parents.jnnw", groups, receipts


def fetch_curriculum(work: Path) -> Path:
    target = work / "curriculum"
    fetch_completed(
        CURRICULUM_PREFIX, job=CURRICULUM_JOB, attempt=CURRICULUM_ATTEMPT,
        mappings=[("artefacts/D-c-prior-then-current.pjtw.gz", "curriculum.pjtw.gz")],
        out_dir=target, report=work / "curriculum-fetch.json",
    )
    gz = target / "curriculum.pjtw.gz"
    if sha_file(gz) != CURRICULUM_GZ_SHA:
        raise StageError("CURRICULUM gzip SHA mismatch")
    raw = target / "curriculum.pjtw"
    if raw.exists():
        raise StageError("CURRICULUM raw output collision")
    with gzip.open(gz, "rb") as source, raw.open("wb") as dest:
        shutil.copyfileobj(source, dest)
    if sha_file(raw) != CURRICULUM_RAW_SHA:
        raise StageError("CURRICULUM raw SHA mismatch")
    return raw


def build_teacher(work: Path) -> tuple[Path, dict[str, object]]:
    if not EGDB_DIR.is_dir() or not EGDB_SRC.is_dir():
        raise StageError("required CPX EGDB directories are absent")
    if not any(path.name.startswith("db7-") for path in EGDB_DIR.iterdir() if path.is_file()):
        raise StageError("EGDB7 data absent")
    generated = work / "rendered-b3-teacher.cpp"
    receipt_path = work / "b3-render-receipt.json"
    receipt = teacher_source.render_file(ROOT / "src/deep_sibling_teacher.cpp", generated, receipt_path)
    build = work / "build"
    run([
        "/usr/bin/cmake", "-S", str(ROOT), "-B", str(build), "-G", "Unix Makefiles",
        "-DCMAKE_BUILD_TYPE=Release", "-DJASS_EGDB=ON", f"-DJASS_EGDB_SRC_DIR={EGDB_SRC}",
        "-DJASS_ENDGAME_FEATURES=ON", "-DJASS_KING_MOBILITY=ON",
        "-DJASS_SCAN_PARITY=ON", "-DJASS_TEMPO_STAGE=ON",
    ], timeout=240, log=work / "cmake-configure.log")
    run(["/usr/bin/cmake", "--build", str(build), "--target", "jass_lib", "egdb_intl",
         "jass_t3_f6_runtime", "-j", "8"], timeout=900, log=work / "cmake-build.log")
    exe = work / "jass_adaptive_sibling_b3_teacher"
    run([
        "/usr/bin/c++", "-std=c++20", "-O2", "-march=native", "-DJASS_EGDB=1",
        f"-I{ROOT / 'src'}", f"-I{ROOT / 'pattern_jass/src'}", f"-I{EGDB_SRC}",
        str(generated),
        str(build / "CMakeFiles/jass_t3_f6_runtime.dir/src/residual_features.cpp.o"),
        str(build / "CMakeFiles/jass_t3_f6_runtime.dir/src/t3_f6.cpp.o"),
        "-o", str(exe), "-Wl,--start-group", str(build / "libjass_lib.a"),
        str(build / "libegdb_intl.a"), "-Wl,--end-group", "-pthread",
    ], timeout=240, log=work / "b3-link.log")
    exe.chmod(0o755)
    return exe, receipt


def sanitized_teacher_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("JASS_")}
    env["PATH"] = os.defpath
    return env


def run_shards(exe: Path, parents: Path, curriculum: Path, work: Path) -> list[dict[str, object]]:
    shard_root = work / "shards"
    shard_root.mkdir()
    processes: list[tuple[int, subprocess.Popen[bytes], object]] = []
    env = sanitized_teacher_env()
    started = time.monotonic()
    for shard in range(SHARDS):
        child = shard_root / f"children-{shard:02d}.jnnw"
        groups = shard_root / f"groups-{shard:02d}.tsv"
        report = shard_root / f"report-{shard:02d}.json"
        log_path = shard_root / f"teacher-{shard:02d}.log"
        handle = log_path.open("wb")
        argv = [str(exe), str(parents), str(child), str(groups), str(report),
                str(curriculum), str(EGDB_DIR), str(shard), str(SHARDS), "16", "256"]
        process = subprocess.Popen(argv, cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT, env=env)
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
                            f"B3 teacher shard {shard} failed rc={rc}: "
                            + "\n".join(log.read_text(errors="replace").splitlines()[-80:]))
            processes = alive
            if processes:
                time.sleep(0.25)
        if processes:
            raise StageError("B3 teacher shards exceeded frozen 390 s technical bound")
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
    reports = []
    for shard in range(SHARDS):
        report = json.loads((shard_root / f"report-{shard:02d}.json").read_text(encoding="utf-8"))
        if report.get("schema") != "jass.adaptive_sibling_b3_teacher_extract.v1" \
                or report.get("adaptive_policy_real") is not True \
                or report.get("m5_cp") != 100 or report.get("m50_cp") != 60 \
                or report.get("minimum_survivors") != 2 \
                or report.get("full_ladder_executed") is not False:
            raise StageError(f"B3 teacher report contract mismatch shard {shard}")
        reports.append(report)
    write_new(work / "teacher-duration.json", canonical({
        "schema": "jass.adaptive_sibling_b3_teacher_duration.v1",
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "shards": SHARDS,
        "timeout_seconds": TEACHER_TIMEOUT_SECONDS,
    }))
    return reports


def merge_groups(work: Path) -> Path:
    shard_root = work / "shards"
    header: list[str] | None = None
    all_rows: list[dict[str, str]] = []
    for shard in range(SHARDS):
        path = shard_root / f"groups-{shard:02d}.tsv"
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames is None:
                raise StageError(f"missing groups header shard {shard}")
            if header is None:
                header = list(reader.fieldnames)
            elif list(reader.fieldnames) != header:
                raise StageError("B3 shard group headers differ")
            rows = list(reader)
            for local, row in enumerate(rows):
                row["_local"] = str(local)
                row["_shard"] = str(shard)
                all_rows.append(row)
    if header is None or not all_rows:
        raise StageError("no B3 group rows")
    all_rows.sort(key=lambda row: (int(row["parent_id"]), int(row["_local"])))
    out = work / "b3-merged-groups.tsv"
    with out.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for global_index, row in enumerate(all_rows):
            row = dict(row)
            row.pop("_local", None); row.pop("_shard", None)
            row["row_index"] = str(global_index)
            writer.writerow(row)
    return out


def aggregate_reports(reports: Sequence[Mapping[str, object]]) -> dict[str, object]:
    sums = {}
    for field in ("processed_parent_rows", "emitted_siblings", "cheap_searches", "screen_searches",
                  "teacher_searches", "cheap_nodes", "screen_nodes", "teacher_nodes",
                  "rule_terminal_children", "exact_tb_children", "engine_constructions"):
        values = [report.get(field) for report in reports]
        if any(type(value) is not int for value in values):
            raise StageError(f"report field {field} is not integer in every shard")
        sums[field] = sum(values)  # type: ignore[arg-type]
    if sums["processed_parent_rows"] != 4000:
        raise StageError("B3 real teacher did not process exactly 4000 parents")
    if sums["engine_constructions"] != sums["cheap_searches"] + sums["screen_searches"] + sums["teacher_searches"]:
        raise StageError("fresh Engine count differs from real search count")
    return sums


def run_stage(work_dir: Path, artifact_dir: Path) -> dict[str, object]:
    if work_dir.exists() or work_dir.is_symlink():
        raise StageError("work-dir must be absent")
    work_dir.mkdir(parents=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    parents, b2_groups, receipts = fetch_b2_inputs(work_dir)
    curriculum = fetch_curriculum(work_dir)
    exe, render_receipt = build_teacher(work_dir)
    reports = run_shards(exe, parents, curriculum, work_dir)
    merged = merge_groups(work_dir)
    parity_report = parity.compare(b2_groups, receipts, merged)
    if parity_report.get("verdict") != parity.VERDICT:
        raise StageError(f"B3 parity blocked: {parity_report.get('mismatches')}")
    aggregate = aggregate_reports(reports)
    if aggregate["cheap_nodes"] + aggregate["screen_nodes"] + aggregate["teacher_nodes"] != parity_report["total_nodes"]:
        raise StageError("teacher aggregate nodes differ from parity checker")
    summary = {
        "schema": SCHEMA,
        "state": "completed",
        "verdict": parity.VERDICT,
        "scientific_verdict": None,
        "b2_terminal_prerequisite": "B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1",
        "b2_parents_replayed": 4000,
        "fresh_b3_parents": 0,
        "policy": {"M5": 100, "M50": 60, "minimum_survivors": 2},
        "budgets_nodes": [5000, 50000, 200000],
        "teacher": aggregate,
        "parity": {
            "rows": parity_report["rows"],
            "total_nodes": parity_report["total_nodes"],
            "actual_searches": parity_report["actual_searches"],
            "actual_nodes": parity_report["actual_nodes"],
            "zero_cost_parent_ids": parity_report["zero_cost_parent_ids"],
            "mismatch_count": len(parity_report["mismatches"]),
        },
        "rendered_source_sha256": render_receipt["rendered_source_sha256"],
        "new_teacher_searches_on_consumed_b2_fixture": aggregate["cheap_searches"] + aggregate["screen_searches"] + aggregate["teacher_searches"],
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        "fresh_b3_generation_authorized": True,
        "next_stage": "B3_FRESH_ADAPTIVE_CORPUS_PREREGISTRATION",
    }
    for name, value in (("b3-real-adaptive-parity.json", parity_report),
                        ("b3-teacher-aggregate.json", aggregate),
                        ("b3-render-receipt.json", render_receipt),
                        ("scientific-summary.json", summary)):
        write_new(artifact_dir / name, canonical(value))
    return summary


def failure_summary(error: str) -> dict[str, object]:
    return {
        "schema": SCHEMA, "state": "failed", "error": error,
        "scientific_verdict": None, "fresh_b3_parents": 0,
        "fits": 0, "strength_games": 0, "promotions": 0, "bakes": 0,
        "fresh_b3_generation_authorized": False,
        "next_stage": "STOP_B3_PARITY_TECHNICAL",
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = run_stage(args.work_dir.resolve(), args.artifact_dir.resolve())
    except Exception as exc:
        summary = failure_summary(f"{type(exc).__name__}: {exc}")
        try:
            args.artifact_dir.mkdir(parents=True, exist_ok=True)
            for name in ("attempt-diagnostic.json", "scientific-summary.json"):
                path = args.artifact_dir / name
                if not path.exists():
                    write_new(path, canonical(summary))
        except Exception as publish_exc:
            print(f"B3 parity failure publication failed: {publish_exc}", file=sys.stderr)
        print(f"adaptive_sibling_b3_parity_stage: {exc}", file=sys.stderr)
        return 4
    print(canonical({"state": summary["state"], "verdict": summary["verdict"],
                     "next_stage": summary["next_stage"]}).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
