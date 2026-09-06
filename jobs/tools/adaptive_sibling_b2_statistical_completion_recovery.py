#!/usr/bin/env python3
"""Complete frozen B2 after the authenticated 1815 projection-binding failure.

The recovery is deliberately narrow. It fetches the immutable failed 1815
bundle, reproduces its classified readout failure, and may repair only the
three cryptographic binding fields of a projection receipt. Every policy,
cost, exactness and q200-noninterference field must match a fresh deterministic
projection from the authenticated allocation object. The normal X readout,
production R=200000 statistics and terminal publisher then run unchanged.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
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

from jobs.tools import adaptive_sibling_b2_allocation_input as common  # noqa: E402
from jobs.tools import adaptive_sibling_b2_projection as projection  # noqa: E402
from jobs.tools import adaptive_sibling_b2_readout as readout  # noqa: E402
from jobs.tools import adaptive_sibling_b2_statistics as statistics  # noqa: E402
from jobs.tools import adaptive_sibling_b2_terminal_publish as publisher  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b2_statistical_completion_recovery.v1"
SOURCE_JOB = "cpx62-1815-l3-decision-math-b2-allocation-readout-terminal-historical-receipt-serialization-repair-v1"
SOURCE_ATTEMPT = "20260906T002518Z-d3657332"
X = "d3657332c3a5609a5501a9ff130f5d5c19488c7f"
SOURCE_PREFIX = f"r2:jass-data/runs/{SOURCE_JOB}/{SOURCE_ATTEMPT}"
SOURCE_MANIFEST_REMOTE = "b2-allocation-readout-terminal/bundle/readout-inputs.json"
SOURCE_FAILURE_REMOTE = "b2-allocation-readout-terminal/readout-build-failure-v1.json"
EXPECTED_FAILURE = {
    "class": "PROJECTION_BINDING_INVALID",
    "stage": "PROJECTION_RECEIPT",
    "parent_id": 1216,
    "global_row_index": None,
    "horizon": None,
}
HASH_FIELDS = frozenset({
    "projection_input_sha256", "decision_input_sha256", "decision_output_sha256",
})
DECISION_OUTPUT_FIELDS = (
    "parent_id", "ordered_rows", "S5_rows", "S50_rows", "S200_charge_rows",
    "pre_q200_choice_row_or_null", "exact_shortcut_reason", "sole_survivor_reason",
    "uncertified_shadow",
)
ALLOWED_VERDICTS = frozenset({
    "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1",
    "B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1",
    "B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1",
})


class RecoveryError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def descriptor(path: Path, **extra: object) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    if resolved.is_symlink() or not resolved.is_file():
        raise RecoveryError(f"not a regular file: {path}")
    return {
        "local_name": resolved.name,
        "sha256": sha_file(resolved),
        "size_bytes": resolved.stat().st_size,
        **extra,
    }


def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise RecoveryError(f"refusing existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RecoveryError(f"refusing existing temporary: {temporary}")
    try:
        temporary.write_bytes(raw)
        os.replace(temporary, path)
        if path.read_bytes() != raw:
            raise RecoveryError(f"output roundtrip mismatch: {path}")
    except BaseException:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def load_json(path: Path, *, canonical_required: bool = False) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"cannot read JSON {path}: {exc}") from exc
    if type(value) is not dict:
        raise RecoveryError(f"JSON root is not object: {path}")
    if canonical_required and raw != canonical(value):
        raise RecoveryError(f"JSON is not canonical: {path}")
    return value


def exact(left: object, right: object) -> bool:
    return canonical(left) == canonical(right)


def run(argv: Sequence[str], *, cwd: Path, timeout: int, log: Path) -> None:
    with log.open("wb") as stream:
        completed = subprocess.run(
            list(argv), cwd=str(cwd), stdout=stream, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
    if completed.returncode != 0:
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        raise RecoveryError(
            f"command failed rc={completed.returncode}: {' '.join(argv)}\n"
            + "\n".join(tail)
        )


def validate_fetch_receipt(path: Path) -> dict[str, Any]:
    value = load_json(path)
    expected = {
        "state": "verified", "result_state": "failed", "exit_code": 1,
        "job_id": SOURCE_JOB, "attempt_id": SOURCE_ATTEMPT,
        "code_sha": X, "prefix": SOURCE_PREFIX,
    }
    for key, wanted in expected.items():
        if type(value.get(key)) is not type(wanted) or value.get(key) != wanted:
            raise RecoveryError(f"fetch receipt {key} mismatch")
    return value


def fetch_files(mappings: Sequence[tuple[str, str]], out_dir: Path,
                report: Path, log: Path) -> dict[str, Any]:
    if out_dir.exists() or out_dir.is_symlink():
        raise RecoveryError(f"fetch destination exists: {out_dir}")
    argv = [
        "/usr/bin/python3", "jobs/tools/fetch_result_files.py",
        "--prefix", SOURCE_PREFIX, "--expected-state", "failed",
    ]
    for remote, local in mappings:
        argv.extend(["--file", f"{remote}={local}"])
    argv.extend(["--out-dir", str(out_dir), "--report", str(report)])
    run(argv, cwd=ROOT, timeout=600, log=log)
    return validate_fetch_receipt(report)


def collect_descriptors(value: object) -> dict[str, tuple[str, int]]:
    found: dict[str, tuple[str, int]] = {}
    def visit(node: object) -> None:
        if type(node) is dict:
            if {"local_name", "sha256", "size_bytes"}.issubset(node):
                name = node["local_name"]
                digest = node["sha256"]
                size = node["size_bytes"]
                if type(name) is not str or Path(name).name != name \
                        or type(digest) is not str or len(digest) != 64 \
                        or type(size) is not int or size <= 0:
                    raise RecoveryError("invalid FileV1 descriptor in source manifest")
                previous = found.get(name)
                current = (digest, size)
                if previous is not None and previous != current:
                    raise RecoveryError(f"descriptor disagreement for {name}")
                found[name] = current
            for child in node.values():
                visit(child)
        elif type(node) is list:
            for child in node:
                visit(child)
    visit(value)
    return found


def authenticate_descriptor_set(bundle: Path, descriptors: Mapping[str, tuple[str, int]]) -> None:
    for name, (digest, size) in descriptors.items():
        path = bundle / name
        if path.is_symlink() or not path.is_file() \
                or path.stat().st_size != size or sha_file(path) != digest:
            raise RecoveryError(f"bundle descriptor mismatch: {name}")


def receipt_without_hashes(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key not in HASH_FIELDS}


def readout_hashes(allocation: Mapping[str, Any], allocation_line: bytes,
                   fresh_receipt: Mapping[str, Any]) -> dict[str, str]:
    decision_view = {
        "schema": allocation["schema"], "parent_id": allocation["parent_id"],
        "phase": allocation["phase"], "stm": allocation["stm"],
        "rows": [
            {key: value for key, value in row.items() if key != "nodes200k"}
            for row in allocation["rows"]
        ],
    }
    decision_output = {key: fresh_receipt[key] for key in DECISION_OUTPUT_FIELDS}
    return {
        "projection_input_sha256": sha(allocation_line),
        "decision_input_sha256": sha(canonical(decision_view)),
        "decision_output_sha256": sha(canonical(decision_output)),
    }


def repair_projection_receipts(
    allocations: Sequence[Mapping[str, Any]], allocation_lines: Sequence[bytes],
    receipts: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not (len(allocations) == len(allocation_lines) == len(receipts) == 4000):
        raise RecoveryError("recovery requires exactly 4000 allocation/receipt records")
    repaired: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for parent_id, (allocation, line, stored) in enumerate(
            zip(allocations, allocation_lines, receipts)):
        if allocation.get("parent_id") != parent_id or stored.get("parent_id") != parent_id:
            raise RecoveryError(f"parent order mismatch at {parent_id}")
        parsed = projection.parse_parent(dict(allocation))
        fresh, _fresh_raw = projection.project_parent(parsed)
        if not exact(receipt_without_hashes(stored), receipt_without_hashes(fresh)):
            differing = sorted(
                key for key in set(stored) | set(fresh)
                if key not in HASH_FIELDS and not exact(stored.get(key), fresh.get(key))
            )
            raise RecoveryError(
                f"parent {parent_id} policy/cost receipt drift: {differing}")
        wanted = readout_hashes(allocation, line, fresh)
        if fresh["decision_input_sha256"] != wanted["decision_input_sha256"] \
                or fresh["decision_output_sha256"] != wanted["decision_output_sha256"]:
            raise RecoveryError(f"parent {parent_id} decision hash semantics drift")
        corrected = dict(stored)
        changed_fields = []
        for key in HASH_FIELDS:
            if corrected[key] != wanted[key]:
                corrected[key] = wanted[key]
                changed_fields.append(key)
        repaired.append(corrected)
        if changed_fields:
            changes.append({"parent_id": parent_id, "fields": sorted(changed_fields)})
    return repaired, changes


def rebuild_projection_manifest(original: Mapping[str, Any], allocation_raw: bytes,
                                repaired: Sequence[Mapping[str, Any]]) \
        -> tuple[dict[str, Any], bytes, bytes]:
    lines = [canonical(dict(receipt)) for receipt in repaired]
    receipts_raw = b"".join(lines)
    manifest = copy.deepcopy(dict(original))
    manifest["input_jsonl_sha256"] = sha(allocation_raw)
    manifest["allocation_receipts_jsonl_sha256"] = sha(receipts_raw)
    manifest["parent_receipts"] = [
        {
            "parent_id": parent_id,
            "allocation_receipt_sha256": sha(line),
            "projection_input_sha256": receipt["projection_input_sha256"],
            "decision_input_sha256": receipt["decision_input_sha256"],
            "decision_output_sha256": receipt["decision_output_sha256"],
        }
        for parent_id, (receipt, line) in enumerate(zip(repaired, lines))
    ]
    return manifest, receipts_raw, canonical(manifest)


def failure_summary(stage: str, error: str, **extra: object) -> dict[str, object]:
    return {
        "schema": SCHEMA, "state": "failed", "failure_stage": stage,
        "error": error, "scientific_verdict": None,
        "source_job": SOURCE_JOB, "source_attempt": SOURCE_ATTEMPT,
        "code_sha": X, "fresh_data_reads": 0, "new_teacher_searches": 0,
        "fits": 0, "strength_games": 0, "promotions": 0, "bakes": 0,
        **extra,
    }


def publish_failure(artifact_dir: Path, summary: Mapping[str, object]) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for name in ("attempt-diagnostic.json", "scientific-summary.json"):
        path = artifact_dir / name
        if path.exists() or path.is_symlink():
            raise RecoveryError(f"refusing existing failure artifact: {name}")
        write_new(path, canonical(dict(summary)))


def run_recovery(work_dir: Path, artifact_dir: Path) -> dict[str, object]:
    if work_dir.exists() or work_dir.is_symlink():
        raise RecoveryError("work directory must be absent")
    work_dir.mkdir(parents=True)
    seed = work_dir / "seed"
    seed_report = work_dir / "seed-fetch.json"
    fetch_files([
        (SOURCE_MANIFEST_REMOTE, "readout-inputs.json"),
        (SOURCE_FAILURE_REMOTE, "readout-build-failure-v1.json"),
    ], seed, seed_report, work_dir / "seed-fetch.log")

    source_manifest_path = seed / "readout-inputs.json"
    source_manifest, source_manifest_raw = readout.read_canonical_json(source_manifest_path)
    source_failure, source_failure_raw = readout.read_canonical_json(
        seed / "readout-build-failure-v1.json")
    checked_failure = readout._validate_build_failure_receipt(source_failure)
    if checked_failure["failure"] != EXPECTED_FAILURE \
            or checked_failure["expected_input_manifest_sha256"] != sha(source_manifest_raw) \
            or checked_failure["actual_input_manifest_sha256"] != sha(source_manifest_raw) \
            or checked_failure["input_manifest_authenticated"] is not True \
            or checked_failure["tool_binding_authenticated"] is not True \
            or checked_failure["preregistration_authenticated"] is not True \
            or any(value != 0 for value in checked_failure["counters"].values()):
        raise RecoveryError("1815 failure receipt is not the frozen authenticated projection failure")

    descriptors = collect_descriptors(source_manifest)
    extras = {
        "verified-historical.json", "source-manifest.json", "legacy-terminal-summary.json",
    }
    mappings = [
        (f"b2-allocation-readout-terminal/bundle/{name}", name)
        for name in sorted(set(descriptors) | extras)
    ]
    bundle = work_dir / "bundle"
    bundle_report = work_dir / "bundle-fetch.json"
    fetch_files(mappings, bundle, bundle_report, work_dir / "bundle-fetch.log")
    write_new(bundle / "readout-inputs.json", source_manifest_raw)
    authenticate_descriptor_set(bundle, descriptors)

    original_manifest = bundle / "readout-inputs.json"
    original_sha = sha(source_manifest_raw)
    common.authenticate_common_manifest(
        original_manifest, original_sha, expected_schema=readout.BUILD_INPUT_SCHEMA,
        exact_root_keys=frozenset({"allocation", "code_sha", "preregistration", "projection",
                                   "schema", "selection", "teacher_merge", "tools"}),
        exact_tool_keys=frozenset({"allocation_input", "projection", "readout", "statistics",
                                   "statistical_preflight_receipt"}),
    )

    original_failure = work_dir / "reproduced-readout-failure.json"
    original_rich = work_dir / "reproduced-rich"
    rc = readout.build_command(argparse.Namespace(
        input_manifest=original_manifest,
        expected_input_manifest_sha256=original_sha,
        out_dir=original_rich,
        failure_receipt=original_failure,
    ))
    if rc != 4 or original_rich.exists():
        raise RecoveryError("1815 failure did not reproduce fail-closed before recovery")
    reproduced, _ = readout.read_canonical_json(original_failure)
    reproduced = readout._validate_build_failure_receipt(reproduced)
    if reproduced["failure"] != EXPECTED_FAILURE:
        raise RecoveryError(f"1815 failure reproduction drifted: {reproduced['failure']}")

    allocation_desc = source_manifest["allocation"]["input_jsonl"]
    projection_desc = source_manifest["projection"]["receipts_jsonl"]
    projection_manifest_desc = source_manifest["projection"]["manifest"]
    allocation_path = bundle / allocation_desc["local_name"]
    receipts_path = bundle / projection_desc["local_name"]
    projection_manifest_path = bundle / projection_manifest_desc["local_name"]
    allocations, allocation_lines, allocation_raw = readout._parse_jsonl(allocation_path, rows=4000)
    receipts, _receipt_lines, _receipts_raw = readout._parse_jsonl(receipts_path, rows=4000)
    projection_manifest, _ = readout.read_canonical_json(projection_manifest_path)
    repaired, changes = repair_projection_receipts(
        allocations, allocation_lines, receipts)
    if not changes or 1216 not in {item["parent_id"] for item in changes}:
        raise RecoveryError(
            "authenticated 1815 failure is not explained by permitted binding metadata drift")

    recovered_bundle = work_dir / "recovered-bundle"
    shutil.copytree(bundle, recovered_bundle)
    repaired_receipts_path = recovered_bundle / "allocation-receipts-recovered-v1.jsonl"
    repaired_manifest_path = recovered_bundle / "projection-manifest-recovered-v1.json"
    repaired_manifest, repaired_raw, repaired_manifest_raw = rebuild_projection_manifest(
        projection_manifest, allocation_raw, repaired)
    write_new(repaired_receipts_path, repaired_raw)
    write_new(repaired_manifest_path, repaired_manifest_raw)

    recovered_manifest = copy.deepcopy(source_manifest)
    recovered_manifest["projection"]["receipts_jsonl"] = descriptor(
        repaired_receipts_path, rows=4000,
        row_schema=readout.ALLOCATION_RECEIPT_SCHEMA)
    recovered_manifest["projection"]["manifest"] = descriptor(repaired_manifest_path)
    recovered_manifest_path = recovered_bundle / "readout-inputs-recovered-v1.json"
    recovered_manifest_raw = canonical(recovered_manifest)
    write_new(recovered_manifest_path, recovered_manifest_raw)
    recovered_sha = sha(recovered_manifest_raw)

    common.authenticate_common_manifest(
        recovered_manifest_path, recovered_sha,
        expected_schema=readout.BUILD_INPUT_SCHEMA,
        exact_root_keys=frozenset({"allocation", "code_sha", "preregistration", "projection",
                                   "schema", "selection", "teacher_merge", "tools"}),
        exact_tool_keys=frozenset({"allocation_input", "projection", "readout", "statistics",
                                   "statistical_preflight_receipt"}),
    )
    rich_dir = work_dir / "rich"
    post_failure = work_dir / "post-recovery-readout-failure.json"
    rc = readout.build_command(argparse.Namespace(
        input_manifest=recovered_manifest_path,
        expected_input_manifest_sha256=recovered_sha,
        out_dir=rich_dir,
        failure_receipt=post_failure,
    ))
    if rc != 0 or post_failure.exists():
        details = load_json(post_failure, canonical_required=True) if post_failure.exists() else None
        raise RecoveryError(f"recovered X readout did not pass: {details}")

    rich_report = rich_dir / "rich-to-sufficient-report-v1.json"
    rich_jsonl = rich_dir / "parent-stats-rich-v1.jsonl"
    sufficient_jsonl = rich_dir / "parent-stats-sufficient-v1.jsonl"
    rich_report_value = load_json(rich_report, canonical_required=True)
    if rich_report_value.get("status") != "VALID" \
            or rich_report_value.get("population", {}).get("parents") != 4000:
        raise RecoveryError("recovered rich readout is not VALID/4000")
    for source in (rich_report, rich_jsonl, sufficient_jsonl):
        shutil.copyfile(source, recovered_bundle / source.name)

    tools = recovered_manifest["tools"]
    preflight_path = recovered_bundle / tools["statistical_preflight_receipt"]["local_name"]
    preflight_receipt = load_json(preflight_path, canonical_required=True)
    runtime_value = preflight_receipt.get("runtime")
    runtime_keys = (
        "python_executable", "python_implementation", "python_version",
        "platform", "machine", "libc", "nproc",
    )
    if type(runtime_value) is not dict or any(key not in runtime_value for key in runtime_keys):
        raise RecoveryError("preflight runtime receipt is incomplete")
    runtime = {key: runtime_value[key] for key in runtime_keys}

    terminal_manifest = {
        "schema": readout.TERMINAL_INPUT_SCHEMA,
        "code_sha": X,
        "preregistration": recovered_manifest["preregistration"],
        "rich_input_manifest": descriptor(recovered_manifest_path),
        "rich_to_sufficient_report": descriptor(recovered_bundle / rich_report.name),
        "rich_jsonl": descriptor(
            recovered_bundle / rich_jsonl.name, rows=4000, row_schema=readout.RICH_SCHEMA),
        "sufficient_jsonl": descriptor(
            recovered_bundle / sufficient_jsonl.name, rows=4000,
            row_schema=statistics.INPUT_SCHEMA),
        "statistics_tool": tools["statistics"],
        "terminal_tool": tools["readout"],
        "preflight": {
            "receipt": tools["statistical_preflight_receipt"],
            "verdict": readout.PREFLIGHT_VERDICT,
            "runtime": runtime,
        },
        "support": {
            "historical_exclusion_receipt": descriptor(
                recovered_bundle / "verified-historical.json"),
            "source_manifest": descriptor(recovered_bundle / "source-manifest.json"),
            "selection_report": recovered_manifest["selection"]["report"],
            "teacher_merge_report": recovered_manifest["teacher_merge"]["report"],
            "teacher_merge_publication_receipt":
                recovered_manifest["teacher_merge"]["publication_receipt"],
            "teacher_native_verification_receipt":
                recovered_manifest["teacher_merge"]["native_verification_receipt"],
            "allocation_input_report": recovered_manifest["allocation"]["report"],
            "projection_manifest": recovered_manifest["projection"]["manifest"],
            "legacy_equivalence_terminal_summary": descriptor(
                recovered_bundle / "legacy-terminal-summary.json"),
        },
    }
    terminal_manifest_path = recovered_bundle / "terminal-inputs-recovered-v1.json"
    terminal_manifest_raw = canonical(terminal_manifest)
    write_new(terminal_manifest_path, terminal_manifest_raw)
    terminal_dir = work_dir / "terminal"
    started_stats = time.monotonic()
    readout.finalize_command(argparse.Namespace(
        input_manifest=terminal_manifest_path,
        expected_input_manifest_sha256=sha(terminal_manifest_raw),
        out_dir=terminal_dir,
    ))
    statistics_seconds = time.monotonic() - started_stats
    terminal_report = load_json(terminal_dir / "b2-terminal-report-v1.json", canonical_required=True)
    verdict = terminal_report.get("verdict")
    if verdict not in ALLOWED_VERDICTS:
        raise RecoveryError(f"terminal verdict outside frozen set: {verdict}")

    publication = publisher.publish(
        input_manifest=terminal_manifest_path,
        expected_input_manifest_sha256=sha(terminal_manifest_raw),
        terminal_dir=terminal_dir,
        code_sha=X,
        artifact_dir=artifact_dir,
    )
    if publication.get("verdict") != verdict \
            or publication.get("automatic_downstream_jobs") != 0 \
            or publication.get("promotion_authorized") is not False \
            or publication.get("bake_authorized") is not False \
            or publication.get("byte_roundtrip_verified") is not True:
        raise RecoveryError("terminal publication guard mismatch")

    stats_path = terminal_dir / "b2-statistics-v1.json"
    stats_value = load_json(stats_path, canonical_required=True) if stats_path.exists() else None
    execution_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    summary = {
        "schema": SCHEMA,
        "state": "completed",
        "execution_sha": execution_sha,
        "scientific_code_sha": X,
        "source_job": SOURCE_JOB,
        "source_attempt": SOURCE_ATTEMPT,
        "source_failure": EXPECTED_FAILURE,
        "source_failure_receipt_sha256": sha(source_failure_raw),
        "source_manifest_sha256": sha(source_manifest_raw),
        "recovered_manifest_sha256": recovered_sha,
        "binding_recovery": {
            "parents_changed": len(changes),
            "changes": changes,
            "policy_cost_counter_fields_changed": 0,
            "allowed_fields": sorted(HASH_FIELDS),
        },
        "statistics": {
            "executed": stats_value is not None,
            "status": None if stats_value is None else stats_value.get("status"),
            "scientific_gates_evaluated": terminal_report["statistics"]["scientific_gates_evaluated"],
            "all_gates_passed": terminal_report["statistics"]["all_gates_passed"],
            "bootstrap_replications": (
                None if stats_value is None else stats_value.get("bootstrap_replications")),
            "bootstrap_seed": None if stats_value is None else stats_value.get("bootstrap_seed"),
            "elapsed_seconds": round(statistics_seconds, 6),
        },
        "support": terminal_report["support"],
        "verdict": verdict,
        "scientific_verdict": verdict,
        "fresh_data_reads": 0,
        "new_teacher_searches": 0,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        "b3_authorized": False,
        "automatic_downstream_jobs": 0,
        "next_stage": "STOP_B2_TERMINAL",
    }
    for name, value in (("b2-statistical-completion-recovery.json", summary),
                        ("scientific-summary.json", summary)):
        path = artifact_dir / name
        if path.exists() or path.is_symlink():
            raise RecoveryError(f"terminal publisher unexpectedly owns {name}")
        write_new(path, canonical(value))
    markers = {
        f"VERDICT__{verdict}": verdict,
        "NEW_TEACHER_SEARCHES__0": "0",
        "FITS__0": "0",
        "STRENGTH_GAMES__0": "0",
        "PROMOTION_AUTHORIZED__FALSE": "false",
        "BAKE_AUTHORIZED__FALSE": "false",
        "B3_AUTHORIZED__FALSE": "false",
        "AUTOMATIC_DOWNSTREAM_JOBS__0": "0",
        "STOP_AFTER_B2": "STOP_AFTER_B2",
        "NEXT_STAGE__STOP_B2_TERMINAL": "STOP_B2_TERMINAL",
    }
    for name, text in markers.items():
        path = artifact_dir / name
        if path.exists() or path.is_symlink():
            raise RecoveryError(f"marker collision: {name}")
        write_new(path, (text + "\n").encode("ascii"))
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_recovery(args.work_dir.resolve(), args.artifact_dir.resolve())
    except Exception as exc:
        summary = failure_summary("RECOVERY", f"{type(exc).__name__}: {exc}")
        try:
            publish_failure(args.artifact_dir.resolve(), summary)
        except Exception as publish_exc:
            print(f"recovery failure publication failed: {publish_exc}", file=sys.stderr)
        print(f"adaptive_sibling_b2_statistical_completion_recovery: {exc}", file=sys.stderr)
        return 4
    print(canonical({
        "schema": SCHEMA, "state": summary["state"], "verdict": summary["verdict"],
        "next_stage": summary["next_stage"],
    }).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
