#!/usr/bin/env python3
"""Target-data preflight for frozen B2 recovery before any bootstrap.

This stage is deliberately non-scientific. It fetches the immutable 1815
bundle, reproduces the authenticated readout failure and asks a narrower
question before a full recovery is allowed: does a fresh deterministic X
projection satisfy the X readout consumer on every parent?

The preflight emits the first exact producer/consumer divergence, including
parent id, typed failure class/stage, the underlying ReadoutError message and
field-level receipt differences. It never runs statistics, teacher search,
fits, strength games, promotion or bake.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import adaptive_sibling_b2_projection as projection  # noqa: E402
from jobs.tools import adaptive_sibling_b2_readout as readout  # noqa: E402
from jobs.tools import adaptive_sibling_b2_statistical_completion_recovery as recovery  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b2_recovery_admissibility_preflight.v1"
READY = "B2_RECOVERY_ADMISSIBILITY_PASS"
BLOCKED = "B2_RECOVERY_ADMISSIBILITY_BLOCKED"


class PreflightError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return recovery.canonical(value)


def exact(left: object, right: object) -> bool:
    return canonical(left) == canonical(right)


def json_diff(left: object, right: object, path: str = "$") -> list[dict[str, object]]:
    """Return a bounded deterministic structural diff suitable for GitOps status."""
    output: list[dict[str, object]] = []
    def walk(a: object, b: object, where: str) -> None:
        if len(output) >= 64:
            return
        if type(a) is not type(b):
            output.append({"path": where, "kind": "type", "left_type": type(a).__name__,
                           "right_type": type(b).__name__})
            return
        if isinstance(a, dict):
            keys = sorted(set(a) | set(b))
            for key in keys:
                child = f"{where}.{key}"
                if key not in a:
                    output.append({"path": child, "kind": "missing_left"})
                elif key not in b:
                    output.append({"path": child, "kind": "missing_right"})
                else:
                    walk(a[key], b[key], child)
                if len(output) >= 64:
                    return
            return
        if isinstance(a, list):
            if len(a) != len(b):
                output.append({"path": where, "kind": "length", "left": len(a), "right": len(b)})
            for index, (av, bv) in enumerate(zip(a, b)):
                walk(av, bv, f"{where}[{index}]")
                if len(output) >= 64:
                    return
            return
        if a != b:
            item: dict[str, object] = {"path": where, "kind": "value"}
            # Never expose credential-like material. Receipts contain no secrets,
            # but hashes and small scalar values are enough for diagnosis.
            if isinstance(a, (bool, int)) or a is None:
                item["left"] = a
            elif isinstance(a, str):
                item["left"] = a if len(a) <= 96 else a[:96] + "…"
            if isinstance(b, (bool, int)) or b is None:
                item["right"] = b
            elif isinstance(b, str):
                item["right"] = b if len(b) <= 96 else b[:96] + "…"
            output.append(item)
    walk(left, right, path)
    return output


def failure_details(exc: BaseException) -> dict[str, object]:
    cause = exc.__cause__
    message = str(cause if cause is not None else exc)
    result: dict[str, object] = {"exception": type(exc).__name__, "message": message}
    if isinstance(exc, readout.BuildValidationFailure):
        result.update({
            "failure_class": exc.failure_class,
            "failure_stage": exc.stage,
            "parent_id": exc.parent_id,
            "global_row_index": exc.global_row_index,
            "horizon": exc.horizon,
        })
    return result


def classify_divergence(*, stored_failed: bool, fresh_failed: bool,
                        differences: Sequence[Mapping[str, object]]) -> dict[str, object]:
    paths = [str(item.get("path", "")) for item in differences]
    allowed_suffixes = {f"$.{name}" for name in recovery.HASH_FIELDS}
    hash_only = bool(paths) and set(paths).issubset(allowed_suffixes)
    if stored_failed and not fresh_failed and hash_only:
        return {"admissible": True, "classification": "STALE_BINDING_METADATA_ONLY"}
    if fresh_failed:
        return {"admissible": False, "classification": "PRODUCER_CONSUMER_CONTRACT_MISMATCH"}
    if differences and not hash_only:
        return {"admissible": False, "classification": "NON_BINDING_RECEIPT_DRIFT"}
    if stored_failed and not fresh_failed and not differences:
        return {"admissible": False, "classification": "FAILURE_NOT_EXPLAINED_BY_RECEIPT_BYTES"}
    return {"admissible": False, "classification": "UNEXPECTED_PREFLIGHT_STATE"}


def group_by_parent(groups: Sequence[Mapping[str, str]], group_lines: Sequence[bytes],
                    semantics: Sequence[Mapping[str, Any]], semantic_lines: Sequence[bytes]) \
        -> tuple[list[list[Mapping[str, str]]], list[list[bytes]],
                 list[list[Mapping[str, Any]]], list[list[bytes]]]:
    groups_by_parent: list[list[Mapping[str, str]]] = [[] for _ in range(4000)]
    group_lines_by_parent: list[list[bytes]] = [[] for _ in range(4000)]
    semantics_by_parent: list[list[Mapping[str, Any]]] = [[] for _ in range(4000)]
    semantic_lines_by_parent: list[list[bytes]] = [[] for _ in range(4000)]
    for group, line in zip(groups, group_lines):
        parent_id = int(group["parent_id"])
        if not 0 <= parent_id < 4000:
            raise PreflightError("teacher parent id outside 0..3999")
        groups_by_parent[parent_id].append(group)
        group_lines_by_parent[parent_id].append(line)
    for semantic, line in zip(semantics, semantic_lines):
        parent_id = semantic.get("parent_id")
        if type(parent_id) is not int or not 0 <= parent_id < 4000:
            raise PreflightError("semantic parent id outside 0..3999")
        semantics_by_parent[parent_id].append(semantic)
        semantic_lines_by_parent[parent_id].append(line)
    return groups_by_parent, group_lines_by_parent, semantics_by_parent, semantic_lines_by_parent


def invoke_parent(*, selection: Mapping[str, Any], selection_line: bytes,
                  groups: Sequence[Mapping[str, str]], group_lines: Sequence[bytes],
                  semantics: Sequence[Mapping[str, Any]], semantic_lines: Sequence[bytes],
                  allocation: Mapping[str, Any], allocation_line: bytes,
                  receipt: Mapping[str, Any], receipt_line: bytes) -> dict[str, object]:
    try:
        readout.build_rich_parent(
            selection=selection, selection_line=selection_line,
            groups=groups, group_lines=group_lines,
            semantics=semantics, semantic_lines=semantic_lines,
            allocation=allocation, allocation_line=allocation_line,
            receipt=receipt, receipt_line=receipt_line,
        )
        return {"passed": True, "failure": None}
    except Exception as exc:
        return {"passed": False, "failure": failure_details(exc)}


def diagnose_population(bundle: Path, manifest: Mapping[str, Any]) -> dict[str, object]:
    selections, selection_lines, _ = readout._parse_tsv(
        bundle / manifest["selection"]["parents_tsv"]["local_name"], readout.SELECTION_FIELDS)
    groups, group_lines, _ = readout._parse_tsv(
        bundle / manifest["teacher_merge"]["groups_tsv"]["local_name"], readout.GROUP_FIELDS)
    semantics, semantic_lines, _ = readout._parse_jsonl(
        bundle / manifest["teacher_merge"]["semantic_actions"]["local_name"])
    allocations, allocation_lines, _ = readout._parse_jsonl(
        bundle / manifest["allocation"]["input_jsonl"]["local_name"], rows=4000)
    receipts, receipt_lines, _ = readout._parse_jsonl(
        bundle / manifest["projection"]["receipts_jsonl"]["local_name"], rows=4000)
    grouped = group_by_parent(groups, group_lines, semantics, semantic_lines)
    groups_by_parent, group_lines_by_parent, semantics_by_parent, semantic_lines_by_parent = grouped

    parents_checked = 0
    for parent_id in range(4000):
        stored = invoke_parent(
            selection=selections[parent_id], selection_line=selection_lines[parent_id],
            groups=groups_by_parent[parent_id], group_lines=group_lines_by_parent[parent_id],
            semantics=semantics_by_parent[parent_id], semantic_lines=semantic_lines_by_parent[parent_id],
            allocation=allocations[parent_id], allocation_line=allocation_lines[parent_id],
            receipt=receipts[parent_id], receipt_line=receipt_lines[parent_id],
        )
        parsed = projection.parse_parent(dict(allocations[parent_id]))
        fresh_receipt, fresh_line = projection.project_parent(parsed)
        fresh = invoke_parent(
            selection=selections[parent_id], selection_line=selection_lines[parent_id],
            groups=groups_by_parent[parent_id], group_lines=group_lines_by_parent[parent_id],
            semantics=semantics_by_parent[parent_id], semantic_lines=semantic_lines_by_parent[parent_id],
            allocation=allocations[parent_id], allocation_line=allocation_lines[parent_id],
            receipt=fresh_receipt, receipt_line=fresh_line,
        )
        differences = json_diff(receipts[parent_id], fresh_receipt)
        parents_checked += 1
        if not stored["passed"] or not fresh["passed"] or differences:
            classification = classify_divergence(
                stored_failed=not bool(stored["passed"]),
                fresh_failed=not bool(fresh["passed"]), differences=differences)
            return {
                "parents_checked": parents_checked,
                "first_divergence": {
                    "parent_id": parent_id,
                    "stored_consumer": stored,
                    "fresh_producer_consumer": fresh,
                    "stored_vs_fresh_receipt_differences": differences,
                    "stored_receipt_sha256": recovery.sha(receipt_lines[parent_id]),
                    "fresh_receipt_sha256": recovery.sha(fresh_line),
                    **classification,
                },
                "admissible": bool(classification["admissible"]),
                "classification": classification["classification"],
            }
    return {"parents_checked": parents_checked, "first_divergence": None,
            "admissible": False, "classification": "SOURCE_FAILURE_DID_NOT_REPRODUCE"}


def run_preflight(work_dir: Path, artifact_dir: Path) -> dict[str, object]:
    if work_dir.exists() or work_dir.is_symlink():
        raise PreflightError("work directory must be absent")
    work_dir.mkdir(parents=True)
    seed = work_dir / "seed"
    recovery.fetch_files([
        (recovery.SOURCE_MANIFEST_REMOTE, "readout-inputs.json"),
        (recovery.SOURCE_FAILURE_REMOTE, "readout-build-failure-v1.json"),
    ], seed, work_dir / "seed-fetch.json", work_dir / "seed-fetch.log")
    manifest_path = seed / "readout-inputs.json"
    manifest, manifest_raw = readout.read_canonical_json(manifest_path)
    source_failure, _ = readout.read_canonical_json(seed / "readout-build-failure-v1.json")
    checked = readout._validate_build_failure_receipt(source_failure)
    if checked["failure"] != recovery.EXPECTED_FAILURE \
            or checked["expected_input_manifest_sha256"] != recovery.sha(manifest_raw) \
            or checked["actual_input_manifest_sha256"] != recovery.sha(manifest_raw) \
            or checked["input_manifest_authenticated"] is not True \
            or checked["tool_binding_authenticated"] is not True \
            or checked["preregistration_authenticated"] is not True \
            or any(value != 0 for value in checked["counters"].values()):
        raise PreflightError("source failure receipt is not frozen authenticated 1815 failure")

    descriptors = recovery.collect_descriptors(manifest)
    extras = {"verified-historical.json", "source-manifest.json", "legacy-terminal-summary.json"}
    mappings = [(f"b2-allocation-readout-terminal/bundle/{name}", name)
                for name in sorted(set(descriptors) | extras)]
    bundle = work_dir / "bundle"
    recovery.fetch_files(mappings, bundle, work_dir / "bundle-fetch.json", work_dir / "bundle-fetch.log")
    recovery.write_new(bundle / "readout-inputs.json", manifest_raw)
    recovery.authenticate_descriptor_set(bundle, descriptors)

    diagnostic = diagnose_population(bundle, manifest)
    verdict = READY if diagnostic["admissible"] else BLOCKED
    summary = {
        "schema": SCHEMA, "state": "completed", "verdict": verdict,
        "scientific_verdict": None,
        "source_job": recovery.SOURCE_JOB, "source_attempt": recovery.SOURCE_ATTEMPT,
        "scientific_code_sha": recovery.X,
        "admissible": diagnostic["admissible"],
        "classification": diagnostic["classification"],
        "parents_checked": diagnostic["parents_checked"],
        "first_divergence": diagnostic["first_divergence"],
        "bootstrap_replications_executed": 0,
        "statistics_invocations": 0,
        "fresh_data_reads": 0, "new_teacher_searches": 0, "fits": 0,
        "strength_games": 0, "promotions": 0, "bakes": 0,
        "next_stage": "B2_STATISTICAL_COMPLETION_READY" if diagnostic["admissible"]
                      else "STOP_B2_RECOVERY_CONTRACT_BLOCKED",
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for name in ("b2-recovery-admissibility.json", "scientific-summary.json"):
        path = artifact_dir / name
        if path.exists() or path.is_symlink():
            raise PreflightError(f"refusing existing artifact {name}")
        recovery.write_new(path, canonical(summary))
    return summary


def failure_summary(error: str) -> dict[str, object]:
    return {
        "schema": SCHEMA, "state": "failed", "verdict": None,
        "scientific_verdict": None, "error": error,
        "bootstrap_replications_executed": 0, "statistics_invocations": 0,
        "fresh_data_reads": 0, "new_teacher_searches": 0, "fits": 0,
        "strength_games": 0, "promotions": 0, "bakes": 0,
        "next_stage": "STOP_B2_RECOVERY_PREFLIGHT_TECHNICAL",
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_preflight(args.work_dir.resolve(), args.artifact_dir.resolve())
    except Exception as exc:
        summary = failure_summary(f"{type(exc).__name__}: {exc}")
        try:
            args.artifact_dir.mkdir(parents=True, exist_ok=True)
            for name in ("attempt-diagnostic.json", "scientific-summary.json"):
                path = args.artifact_dir / name
                if not path.exists():
                    recovery.write_new(path, canonical(summary))
        except Exception as publish_exc:
            print(f"preflight failure publication failed: {publish_exc}", file=sys.stderr)
        print(f"adaptive_sibling_b2_recovery_admissibility_preflight: {exc}", file=sys.stderr)
        return 4
    print(canonical({"schema": SCHEMA, "state": summary["state"],
                     "verdict": summary["verdict"], "next_stage": summary["next_stage"]}
                    ).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
