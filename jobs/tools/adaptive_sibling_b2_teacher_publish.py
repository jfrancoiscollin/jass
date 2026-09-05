#!/usr/bin/env python3
"""Fail-closed publication seal for prospective PR771 B2 teacher merge outputs.

The search/merge process has already produced and natively verified its payloads.
This publisher does not search, select, fit, score, or evaluate a scientific gate.
It re-authenticates the immutable merge report, extracts the embedded native legal
verification receipt, copies the closed portable payload set byte-for-byte, and
publishes the exact teacher-publication receipt consumed by the B2 allocation and
readout tools.

The production wrapper MUST authenticate X/Y/S/F and the sealed selection before
starting the teacher.  This post-search seal cannot retroactively replace that
pre-read barrier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b2_teacher_merge as merger  # noqa: E402


PUBLICATION_SCHEMA = "jass.adaptive_sibling_b2_teacher_merge_publication.v1"
MERGE_SCHEMA = merger.REPORT_SCHEMA
NATIVE_SCHEMA = merger.NATIVE_SCHEMA
PARENTS = merger.PARENTS
MIN_ACTIONS = merger.MIN_ACTIONS
MAX_ACTIONS = merger.MAX_ACTIONS
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
GIT_RE = re.compile(r"[0-9a-f]{40}\Z")
REPORT_KEYS = {
    "adapter", "aggregate", "build", "code_sha", "counters", "identity_order",
    "identity_tuple", "input_manifest", "native_verification", "outputs",
    "scientific_scope", "schema", "selection", "shards", "teacher_runtime",
}


class PublishError(RuntimeError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise PublishError(f"{label} must be a regular non-symlink file")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise PublishError(f"cannot resolve {label}: {exc}") from exc


def _sha(value: object, label: str) -> str:
    if type(value) is not str or not SHA_RE.fullmatch(value):
        raise PublishError(f"{label} must be lowercase SHA256")
    return value


def _git_sha(value: object, label: str) -> str:
    if type(value) is not str or not GIT_RE.fullmatch(value):
        raise PublishError(f"{label} must be a full lowercase Git SHA")
    return value


def _integer(value: object, label: str, lo: int = 0, hi: int = (1 << 63) - 1) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise PublishError(f"{label} must be integer in [{lo},{hi}]")
    return value


def _expect_keys(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        actual = sorted(value) if isinstance(value, Mapping) else type(value).__name__
        raise PublishError(f"{label} keys mismatch: {actual}")
    return value


def _read_canonical(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    path = _strict_file(path, label)
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublishError(f"invalid {label} JSON: {exc}") from exc
    if type(value) is not dict or raw != canonical_json_bytes(value):
        raise PublishError(f"{label} must be canonical compact JSON/LF")
    return value, raw


def descriptor(path: Path, **extra: object) -> dict[str, Any]:
    path = _strict_file(path, path.name)
    return {"local_name": path.name, "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size, **extra}


def _descriptor_actual(path: Path, declared: object, label: str,
                       extras: set[str] = set()) -> Mapping[str, Any]:
    item = _expect_keys(declared, {"local_name", "sha256", "size_bytes", *extras}, label)
    if item["local_name"] != path.name:
        raise PublishError(f"{label} local_name mismatch")
    _sha(item["sha256"], f"{label}.sha256")
    _integer(item["size_bytes"], f"{label}.size_bytes", 1)
    actual = _strict_file(path, label)
    if actual.stat().st_size != item["size_bytes"] or sha256_file(actual) != item["sha256"]:
        raise PublishError(f"{label} byte descriptor mismatch")
    return item


def _without_local(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "local_name"}


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink() or os.path.lexists(path):
        raise PublishError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-b2-publish")
    if temp.exists() or temp.is_symlink() or os.path.lexists(temp):
        raise PublishError(f"refusing existing temporary {temp}")
    try:
        with temp.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        if path.is_symlink() or path.read_bytes() != raw:
            raise PublishError(f"published bytes differ: {path.name}")
    except BaseException:
        temp.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def _copy_new(source: Path, destination: Path) -> dict[str, Any]:
    raw = _strict_file(source, source.name).read_bytes()
    _write_new(destination, raw)
    return descriptor(destination)


def _prepare_artifact_dir(path: Path) -> None:
    if path.is_symlink():
        raise PublishError("artifact directory cannot be a symlink")
    if not path.exists():
        path.mkdir(parents=True)
        return
    if not path.is_dir():
        raise PublishError("artifact path is not a directory")
    entries = list(path.iterdir())
    if entries and not (len(entries) == 1 and entries[0].name == "runner-launch.json"
                        and entries[0].is_file() and not entries[0].is_symlink()):
        raise PublishError("artifact directory must be empty or contain only runner-launch.json")


def _validate_native(native: Mapping[str, Any], *, rows: int,
                     report: Mapping[str, Any]) -> None:
    if native.get("schema") != NATIVE_SCHEMA or native.get("verification_complete") is not True:
        raise PublishError("native verification receipt is not complete")
    expected_counts = {
        "actions_verified": rows, "catalogue_actions_generated": rows,
        "catalogues_verified": PARENTS, "duplicate_semantic_actions": 0,
        "extra_actions": 0, "forbidden_reordering": 0, "missing_actions": 0,
        "nonzero_child_targets": 0, "nonzero_parent_targets": 0,
        "parent_after_matches": rows, "parent_count_matches": PARENTS,
        "parents_verified": PARENTS, "semantic_rows_verified": rows,
    }
    for key, expected in expected_counts.items():
        if type(native.get(key)) is not int or native.get(key) != expected:
            raise PublishError(f"native verification {key} mismatch")
    children = _expect_keys(native.get("children"),
        {"local_name", "sha256", "size_bytes", "records", "record_size_bytes"},
        "native children")
    semantic = _expect_keys(native.get("semantic_actions"),
        {"local_name", "sha256", "size_bytes", "rows", "row_schema"},
        "native semantic actions")
    if _without_local(children) != _without_local(report["outputs"]["children_jnnw"]):
        raise PublishError("native children descriptor differs from merge output")
    if _without_local(semantic) != _without_local(report["outputs"]["semantic_actions"]):
        raise PublishError("native semantic descriptor differs from merge output")


def publish(*, input_manifest: Path, expected_input_manifest_sha256: str,
            merge_report: Path, expected_merge_report_sha256: str,
            children_jnnw: Path, groups_tsv: Path, semantic_actions: Path,
            code_sha: str, artifact_dir: Path) -> dict[str, Any]:
    _git_sha(code_sha, "code SHA")
    _sha(expected_input_manifest_sha256, "expected input manifest SHA")
    _sha(expected_merge_report_sha256, "expected merge report SHA")
    input_manifest = _strict_file(input_manifest, "teacher input manifest")
    merge_report = _strict_file(merge_report, "teacher merge report")
    if sha256_file(input_manifest) != expected_input_manifest_sha256:
        raise PublishError("teacher input manifest external SHA mismatch")
    if sha256_file(merge_report) != expected_merge_report_sha256:
        raise PublishError("teacher merge report external SHA mismatch")

    report, report_raw = _read_canonical(merge_report, "teacher merge report")
    _expect_keys(report, REPORT_KEYS, "teacher merge report")
    if report.get("schema") != MERGE_SCHEMA or report.get("code_sha") != code_sha:
        raise PublishError("teacher merge report schema/code mismatch")
    expected_input = descriptor(input_manifest)
    if report.get("input_manifest") != expected_input:
        raise PublishError("teacher merge report input manifest descriptor mismatch")

    outputs = _expect_keys(report.get("outputs"),
        {"children_jnnw", "groups_tsv", "semantic_actions"}, "teacher outputs")
    child_decl = _descriptor_actual(children_jnnw, outputs["children_jnnw"],
                                    "children JNNW", {"records", "record_size_bytes"})
    group_decl = _descriptor_actual(groups_tsv, outputs["groups_tsv"],
                                    "groups TSV", {"rows"})
    semantic_decl = _descriptor_actual(semantic_actions, outputs["semantic_actions"],
                                       "semantic actions", {"rows", "row_schema"})
    rows = _integer(group_decl["rows"], "teacher rows", MIN_ACTIONS, MAX_ACTIONS)
    if child_decl["records"] != rows or child_decl["record_size_bytes"] != 38 \
            or semantic_decl["rows"] != rows \
            or semantic_decl["row_schema"] != merger.SEMANTIC_SCHEMA:
        raise PublishError("teacher output cardinality/schema mismatch")
    counters = _expect_keys(report.get("counters"), {
        "captured_bitboards_reconstructed", "children_records", "duplicate_path_entries",
        "duplicate_semantic_actions", "extra_actions", "forbidden_reordering",
        "full_catalogues_verified", "global_rows_rebased", "groups_rows",
        "missing_actions", "nonzero_child_targets", "parent_child_transitions_verified",
        "parents", "parents_with_legal_count_match", "processed_parent_rows",
        "semantic_actions", "semantic_ledger_rows", "shards"}, "merge counters")
    for key, expected in {
        "children_records": rows, "duplicate_semantic_actions": 0, "extra_actions": 0,
        "forbidden_reordering": 0, "full_catalogues_verified": PARENTS,
        "global_rows_rebased": rows, "groups_rows": rows, "missing_actions": 0,
        "nonzero_child_targets": 0, "parent_child_transitions_verified": rows,
        "parents": PARENTS, "parents_with_legal_count_match": PARENTS,
        "processed_parent_rows": PARENTS, "semantic_actions": rows,
        "semantic_ledger_rows": rows, "shards": merger.SHARDS,
    }.items():
        if type(counters.get(key)) is not int or counters.get(key) != expected:
            raise PublishError(f"merge counter {key} mismatch")
    scope = report.get("scientific_scope")
    if scope != {"calibration": False, "fits": 0, "model_selection": False,
                 "promotion_authorized": False, "strength_games": 0,
                 "training": False, "tuning": False}:
        raise PublishError("teacher merge scientific scope drift")
    native_wrapper = _expect_keys(report.get("native_verification"),
                                  {"receipt", "sha256", "size_bytes"},
                                  "native verification wrapper")
    native = _expect_keys(native_wrapper["receipt"], set(native_wrapper["receipt"]),
                          "native receipt")
    native_raw = canonical_json_bytes(native)
    if native_wrapper["sha256"] != sha256_bytes(native_raw) \
            or native_wrapper["size_bytes"] != len(native_raw):
        raise PublishError("native verification wrapper bytes mismatch")
    _validate_native(native, rows=rows, report=report)

    _prepare_artifact_dir(artifact_dir)
    source_paths = [input_manifest, children_jnnw, groups_tsv, semantic_actions, merge_report]
    if len({str(_strict_file(p, p.name)) for p in source_paths}) != len(source_paths):
        raise PublishError("teacher publication inputs alias")
    published_input = _copy_new(input_manifest, artifact_dir / input_manifest.name)
    published_children = _copy_new(children_jnnw, artifact_dir / children_jnnw.name)
    published_groups = _copy_new(groups_tsv, artifact_dir / groups_tsv.name)
    published_semantic = _copy_new(semantic_actions, artifact_dir / semantic_actions.name)
    published_report = _copy_new(merge_report, artifact_dir / merge_report.name)
    native_path = artifact_dir / "native-verification-receipt.json"
    _write_new(native_path, native_raw)

    publication = {
        "schema": PUBLICATION_SCHEMA,
        "code_sha": code_sha,
        "input_manifest": published_input,
        "byte_roundtrip_verified": True,
        "artifacts": {
            "children_jnnw": published_children,
            "groups_tsv": published_groups,
            "semantic_actions": published_semantic,
            "merge_report": published_report,
        },
    }
    publication_path = artifact_dir / "teacher-publication-receipt.json"
    _write_new(publication_path, canonical_json_bytes(publication))
    reread, raw = _read_canonical(publication_path, "teacher publication receipt")
    if reread != publication or raw != canonical_json_bytes(publication):
        raise PublishError("teacher publication receipt roundtrip mismatch")
    if _read_canonical(native_path, "native verification receipt")[0] != native:
        raise PublishError("native verification receipt roundtrip mismatch")
    return publication


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--expected-input-manifest-sha256", required=True)
    parser.add_argument("--merge-report", type=Path, required=True)
    parser.add_argument("--expected-merge-report-sha256", required=True)
    parser.add_argument("--children-jnnw", type=Path, required=True)
    parser.add_argument("--groups-tsv", type=Path, required=True)
    parser.add_argument("--semantic-actions", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = publish(
            input_manifest=args.input_manifest,
            expected_input_manifest_sha256=args.expected_input_manifest_sha256,
            merge_report=args.merge_report,
            expected_merge_report_sha256=args.expected_merge_report_sha256,
            children_jnnw=args.children_jnnw,
            groups_tsv=args.groups_tsv,
            semantic_actions=args.semantic_actions,
            code_sha=args.code_sha,
            artifact_dir=args.artifact_dir,
        )
    except (PublishError, OSError, ValueError) as exc:
        print(f"adaptive_sibling_b2_teacher_publish: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes({"schema": PUBLICATION_SCHEMA,
                                "receipt": "teacher-publication-receipt.json",
                                "code_sha": result["code_sha"]}).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
