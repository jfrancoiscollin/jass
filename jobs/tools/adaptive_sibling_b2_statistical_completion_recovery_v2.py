#!/usr/bin/env python3
"""Complete frozen B2 with the exact-zero-cost compatibility established by 1827.

This v2 recovery deliberately leaves every immutable source/allocation/projection
byte unchanged.  It authenticates the original 1815 typed failure and bundle,
proves that a fresh X projection is byte-equivalent for all 4,000 parents, then
installs the narrow exact-zero-cost compatibility and runs the unchanged X
readout/statistics/terminal publisher semantics.  No policy, cohort, score,
threshold, gate, seed, bootstrap count or teacher observation is changed.
"""
from __future__ import annotations

import argparse
import json
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
from jobs.tools import adaptive_sibling_b2_exact_zero_cost_compat as compat  # noqa: E402
from jobs.tools import adaptive_sibling_b2_readout as readout  # noqa: E402
from jobs.tools import adaptive_sibling_b2_statistics as statistics  # noqa: E402
from jobs.tools import adaptive_sibling_b2_terminal_publish as publisher  # noqa: E402
from jobs.tools import adaptive_sibling_b2_statistical_completion_recovery as base  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b2_statistical_completion_recovery.v2"


class RecoveryV2Error(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return base.canonical(value)


def load_json(path: Path, *, canonical_required: bool = False) -> dict[str, Any]:
    return base.load_json(path, canonical_required=canonical_required)


def _authenticate_source_failure(seed: Path, manifest_raw: bytes) -> bytes:
    failure_path = seed / "readout-build-failure-v1.json"
    source_failure, source_failure_raw = readout.read_canonical_json(failure_path)
    checked = readout._validate_build_failure_receipt(source_failure)
    if checked["failure"] != base.EXPECTED_FAILURE \
            or checked["expected_input_manifest_sha256"] != base.sha(manifest_raw) \
            or checked["actual_input_manifest_sha256"] != base.sha(manifest_raw) \
            or checked["input_manifest_authenticated"] is not True \
            or checked["tool_binding_authenticated"] is not True \
            or checked["preregistration_authenticated"] is not True \
            or any(value != 0 for value in checked["counters"].values()):
        raise RecoveryV2Error("1815 failure receipt is not the frozen authenticated failure")
    return source_failure_raw


def _authenticate_projection_identity(bundle: Path, manifest: Mapping[str, Any]) -> None:
    allocation_path = bundle / manifest["allocation"]["input_jsonl"]["local_name"]
    receipt_path = bundle / manifest["projection"]["receipts_jsonl"]["local_name"]
    allocations, allocation_lines, _ = readout._parse_jsonl(allocation_path, rows=4000)
    receipts, _receipt_lines, _ = readout._parse_jsonl(receipt_path, rows=4000)
    _same, changes = base.repair_projection_receipts(allocations, allocation_lines, receipts)
    if changes:
        raise RecoveryV2Error(
            f"projection receipts are not byte-equivalent to fresh X projection: {changes[:8]}"
        )


def _zero_cost_audit(rich_jsonl: Path, sufficient_jsonl: Path) -> dict[str, object]:
    zero_rich: list[int] = []
    with rich_jsonl.open("r", encoding="ascii") as handle:
        for line in handle:
            value = json.loads(line)
            costs = value["costs"]
            if costs["full_nodes_total"] == 0:
                if costs["shadow_nodes_total"] != 0:
                    raise RecoveryV2Error("zero full-node rich parent has nonzero shadow cost")
                if value["fully_nonexact"] is not False:
                    raise RecoveryV2Error("zero full-node rich parent is unexpectedly fully nonexact")
                zero_rich.append(value["parent_id"])
    rows, _ = statistics.load_parent_stats_sufficient_jsonl(sufficient_jsonl)
    zero_sufficient = [row.parent_id for row in rows if row.full_nodes == 0]
    if zero_rich != zero_sufficient:
        raise RecoveryV2Error("rich/sufficient zero-cost parent identity mismatch")
    if 1216 not in zero_rich:
        raise RecoveryV2Error("authenticated parent 1216 is not present in zero-cost audit")
    return {
        "zero_full_parent_count": len(zero_rich),
        "zero_full_parent_ids": zero_rich,
        "parent_1216_present": True,
        "all_zero_full_have_zero_shadow": True,
        "all_zero_full_are_not_fully_nonexact": True,
    }


def run_recovery(work_dir: Path, artifact_dir: Path) -> dict[str, object]:
    if work_dir.exists() or work_dir.is_symlink():
        raise RecoveryV2Error("work directory must be absent")
    work_dir.mkdir(parents=True)

    seed = work_dir / "seed"
    base.fetch_files([
        (base.SOURCE_MANIFEST_REMOTE, "readout-inputs.json"),
        (base.SOURCE_FAILURE_REMOTE, "readout-build-failure-v1.json"),
    ], seed, work_dir / "seed-fetch.json", work_dir / "seed-fetch.log")
    source_manifest_path = seed / "readout-inputs.json"
    source_manifest, source_manifest_raw = readout.read_canonical_json(source_manifest_path)
    source_failure_raw = _authenticate_source_failure(seed, source_manifest_raw)

    descriptors = base.collect_descriptors(source_manifest)
    extras = {"verified-historical.json", "source-manifest.json", "legacy-terminal-summary.json"}
    mappings = [
        (f"b2-allocation-readout-terminal/bundle/{name}", name)
        for name in sorted(set(descriptors) | extras)
    ]
    bundle = work_dir / "bundle"
    base.fetch_files(mappings, bundle, work_dir / "bundle-fetch.json", work_dir / "bundle-fetch.log")
    base.write_new(bundle / "readout-inputs.json", source_manifest_raw)
    base.authenticate_descriptor_set(bundle, descriptors)

    original_manifest = bundle / "readout-inputs.json"
    original_sha = base.sha(source_manifest_raw)
    common.authenticate_common_manifest(
        original_manifest, original_sha, expected_schema=readout.BUILD_INPUT_SCHEMA,
        exact_root_keys=frozenset({"allocation", "code_sha", "preregistration", "projection",
                                   "schema", "selection", "teacher_merge", "tools"}),
        exact_tool_keys=frozenset({"allocation_input", "projection", "readout", "statistics",
                                   "statistical_preflight_receipt"}),
    )
    _authenticate_projection_identity(bundle, source_manifest)

    compat_receipt = compat.install()

    rich_dir = work_dir / "rich"
    failure_receipt = work_dir / "compat-readout-failure.json"
    rc = readout.build_command(argparse.Namespace(
        input_manifest=original_manifest,
        expected_input_manifest_sha256=original_sha,
        out_dir=rich_dir,
        failure_receipt=failure_receipt,
    ))
    if rc != 0 or failure_receipt.exists():
        details = load_json(failure_receipt, canonical_required=True) if failure_receipt.exists() else None
        raise RecoveryV2Error(f"exact-zero-cost compatible X readout did not pass: {details}")

    rich_report = rich_dir / "rich-to-sufficient-report-v1.json"
    rich_jsonl = rich_dir / "parent-stats-rich-v1.jsonl"
    sufficient_jsonl = rich_dir / "parent-stats-sufficient-v1.jsonl"
    rich_report_value = load_json(rich_report, canonical_required=True)
    if rich_report_value.get("status") != "VALID" \
            or rich_report_value.get("population", {}).get("parents") != 4000:
        raise RecoveryV2Error("compatible rich readout is not VALID/4000")
    zero_cost = _zero_cost_audit(rich_jsonl, sufficient_jsonl)

    terminal_bundle = work_dir / "terminal-bundle"
    shutil.copytree(bundle, terminal_bundle)
    for source in (rich_report, rich_jsonl, sufficient_jsonl):
        shutil.copyfile(source, terminal_bundle / source.name)

    tools = source_manifest["tools"]
    preflight_path = terminal_bundle / tools["statistical_preflight_receipt"]["local_name"]
    preflight_receipt = load_json(preflight_path, canonical_required=True)
    runtime_value = preflight_receipt.get("runtime")
    runtime_keys = (
        "python_executable", "python_implementation", "python_version",
        "platform", "machine", "libc", "nproc",
    )
    if type(runtime_value) is not dict or any(key not in runtime_value for key in runtime_keys):
        raise RecoveryV2Error("preflight runtime receipt is incomplete")
    runtime = {key: runtime_value[key] for key in runtime_keys}

    terminal_manifest = {
        "schema": readout.TERMINAL_INPUT_SCHEMA,
        "code_sha": base.X,
        "preregistration": source_manifest["preregistration"],
        "rich_input_manifest": base.descriptor(original_manifest),
        "rich_to_sufficient_report": base.descriptor(terminal_bundle / rich_report.name),
        "rich_jsonl": base.descriptor(
            terminal_bundle / rich_jsonl.name, rows=4000, row_schema=readout.RICH_SCHEMA),
        "sufficient_jsonl": base.descriptor(
            terminal_bundle / sufficient_jsonl.name, rows=4000,
            row_schema=statistics.INPUT_SCHEMA),
        "statistics_tool": tools["statistics"],
        "terminal_tool": tools["readout"],
        "preflight": {
            "receipt": tools["statistical_preflight_receipt"],
            "verdict": readout.PREFLIGHT_VERDICT,
            "runtime": runtime,
        },
        "support": {
            "historical_exclusion_receipt": base.descriptor(
                terminal_bundle / "verified-historical.json"),
            "source_manifest": base.descriptor(terminal_bundle / "source-manifest.json"),
            "selection_report": source_manifest["selection"]["report"],
            "teacher_merge_report": source_manifest["teacher_merge"]["report"],
            "teacher_merge_publication_receipt":
                source_manifest["teacher_merge"]["publication_receipt"],
            "teacher_native_verification_receipt":
                source_manifest["teacher_merge"]["native_verification_receipt"],
            "allocation_input_report": source_manifest["allocation"]["report"],
            "projection_manifest": source_manifest["projection"]["manifest"],
            "legacy_equivalence_terminal_summary": base.descriptor(
                terminal_bundle / "legacy-terminal-summary.json"),
        },
    }
    terminal_manifest_path = terminal_bundle / "terminal-inputs-exact-zero-compat-v2.json"
    terminal_manifest_raw = canonical(terminal_manifest)
    base.write_new(terminal_manifest_path, terminal_manifest_raw)

    terminal_dir = work_dir / "terminal"
    started_stats = time.monotonic()
    readout.finalize_command(argparse.Namespace(
        input_manifest=terminal_manifest_path,
        expected_input_manifest_sha256=base.sha(terminal_manifest_raw),
        out_dir=terminal_dir,
    ))
    statistics_seconds = time.monotonic() - started_stats
    terminal_report = load_json(terminal_dir / "b2-terminal-report-v1.json", canonical_required=True)
    verdict = terminal_report.get("verdict")
    if verdict not in base.ALLOWED_VERDICTS:
        raise RecoveryV2Error(f"terminal verdict outside frozen set: {verdict}")

    publication = publisher.publish(
        input_manifest=terminal_manifest_path,
        expected_input_manifest_sha256=base.sha(terminal_manifest_raw),
        terminal_dir=terminal_dir,
        code_sha=base.X,
        artifact_dir=artifact_dir,
    )
    if publication.get("verdict") != verdict \
            or publication.get("automatic_downstream_jobs") != 0 \
            or publication.get("promotion_authorized") is not False \
            or publication.get("bake_authorized") is not False \
            or publication.get("byte_roundtrip_verified") is not True:
        raise RecoveryV2Error("terminal publication guard mismatch")

    stats_path = terminal_dir / "b2-statistics-v1.json"
    stats_value = load_json(stats_path, canonical_required=True) if stats_path.exists() else None
    execution_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    summary = {
        "schema": SCHEMA,
        "state": "completed",
        "execution_sha": execution_sha,
        "scientific_code_sha": base.X,
        "source_job": base.SOURCE_JOB,
        "source_attempt": base.SOURCE_ATTEMPT,
        "source_failure": base.EXPECTED_FAILURE,
        "source_failure_receipt_sha256": base.sha(source_failure_raw),
        "source_manifest_sha256": base.sha(source_manifest_raw),
        "projection_receipts_changed": 0,
        "binding_recovery": {
            "parents_changed": 0,
            "changes": [],
            "policy_cost_counter_fields_changed": 0,
            "allowed_fields": sorted(base.HASH_FIELDS),
        },
        "exact_zero_cost_compat": {
            "enabled": True,
            "implementation_commit": compat_receipt.implementation_commit,
            "frozen_paths_unchanged": compat_receipt.frozen_paths_unchanged,
            "readout_zero_full_total_enabled": compat_receipt.readout_zero_full_total_enabled,
            "statistics_zero_full_nodes_enabled": compat_receipt.statistics_zero_full_nodes_enabled,
            "zero_full_requires_zero_shadow": compat_receipt.zero_full_requires_zero_shadow,
            **zero_cost,
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
    for name in ("b2-statistical-completion-recovery.json", "scientific-summary.json"):
        path = artifact_dir / name
        if path.exists() or path.is_symlink():
            raise RecoveryV2Error(f"terminal publisher unexpectedly owns {name}")
        base.write_new(path, canonical(summary))
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
            raise RecoveryV2Error(f"marker collision: {name}")
        base.write_new(path, (text + "\n").encode("ascii"))
    return summary


def failure_summary(error: str) -> dict[str, object]:
    return {
        "schema": SCHEMA, "state": "failed", "failure_stage": "RECOVERY",
        "error": error, "scientific_verdict": None,
        "source_job": base.SOURCE_JOB, "source_attempt": base.SOURCE_ATTEMPT,
        "scientific_code_sha": base.X, "fresh_data_reads": 0,
        "new_teacher_searches": 0, "fits": 0, "strength_games": 0,
        "promotions": 0, "bakes": 0, "next_stage": "STOP_B2_RECOVERY_TECHNICAL",
    }


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
        summary = failure_summary(f"{type(exc).__name__}: {exc}")
        try:
            base.publish_failure(args.artifact_dir.resolve(), summary)
        except Exception as publish_exc:
            print(f"recovery v2 failure publication failed: {publish_exc}", file=sys.stderr)
        print(f"adaptive_sibling_b2_statistical_completion_recovery_v2: {exc}", file=sys.stderr)
        return 4
    print(canonical({
        "schema": SCHEMA, "state": summary["state"], "verdict": summary["verdict"],
        "next_stage": summary["next_stage"],
    }).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
