#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a provenance-first catalogue from a read-only R2 object census.

The tool never opens a corpus payload.  It consumes the JSON emitted by
``rclone lsjson`` plus a local mirror containing only runner control metadata.
Every JNNW object is catalogued, but nothing is automatically admitted to a
training set: clean runner-v3 sources are marked ``review``; incomplete,
derived, or ambiguous sources are quarantined; failed/corrupt runs are
rejected.  Missing historical facts remain explicit ``null`` values.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import time
from typing import Any, Iterable


CATALOG_SCHEMA = "jass.megacorpus.catalog.v1"
ATTEMPT_SCHEMA = "jass.megacorpus.runner_attempt.v1"
CANDIDATE_SCHEMA = "jass.megacorpus.corpus_candidate.v1"

DATA_SUFFIXES = (".jnnw.gz", ".jnnw")
META_SUFFIXES = (".jsm.gz", ".jsm")
MODEL_SUFFIXES = (".pjtw.gz", ".pjtw")
RISK_PATTERNS = {
    "derived_mix": re.compile(r"(?:^|[-_.])(mix|merge|blend)(?:[-_.]|$)", re.I),
    "split_or_holdout": re.compile(r"(?:^|[-_.])(split|holdout|test)(?:[-_.]|$)", re.I),
    "specialist_or_filtered": re.compile(
        r"(?:^|[-_.])(hard|replay|filter|seed|caps?|candidate)(?:[-_.]|$)", re.I
    ),
    "external_or_teacher": re.compile(
        r"(?:^|[-_.])(scan|teacher|master|pcblues|egdb|oracle|relabel)(?:[-_.]|$)",
        re.I,
    ),
}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_id(*parts: object) -> str:
    encoded = "\0".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def normalize_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid object path: {value!r}")
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"unsafe object path: {value!r}")
    normalized = str(path)
    if normalized in {"", "."}:
        raise ValueError(f"invalid object path: {value!r}")
    return normalized


def load_object_index(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read rclone object index {path}: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("rclone object index must be a non-empty JSON array")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict) or item.get("IsDir") is True:
            continue
        object_path = normalize_relative_path(item.get("Path"))
        if object_path in seen:
            raise ValueError(f"duplicate R2 object path: {object_path}")
        seen.add(object_path)
        size = item.get("Size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"object {index} has invalid size: {size!r}")
        modtime = item.get("ModTime")
        if modtime is not None and not isinstance(modtime, str):
            raise ValueError(f"object {index} has invalid ModTime")
        rows.append({"path": object_path, "size_bytes": size, "modtime": modtime})
    if not rows:
        raise ValueError("rclone object index contains no files")
    rows.sort(key=lambda row: row["path"])
    return rows


def parse_checksums(raw: bytes) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError(f"invalid checksums.sha256 line {line_number}")
        name = normalize_relative_path(match.group(2))
        if name in rows:
            raise ValueError(f"duplicate checksum path: {name}")
        rows[name] = match.group(1)
    if not rows:
        raise ValueError("empty checksums.sha256")
    return rows


def inventory_map(payload: object) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise ValueError("inventory.json has no files list")
    rows: dict[str, dict[str, Any]] = {}
    for item in payload["files"]:
        if not isinstance(item, dict):
            raise ValueError("inventory row is not an object")
        name = normalize_relative_path(item.get("path"))
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError(f"invalid inventory metadata for {name}")
        if name in rows:
            raise ValueError(f"duplicate inventory path: {name}")
        rows[name] = {"size_bytes": size, "sha256": digest}
    return rows


def _json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _read_metadata(metadata_root: Path, relative: str) -> bytes:
    path = metadata_root.joinpath(*PurePosixPath(relative).parts)
    if not path.is_file():
        raise ValueError(f"metadata mirror is missing {relative}")
    return path.read_bytes()


def attempt_roots(objects: Iterable[dict[str, Any]]) -> list[str]:
    roots = []
    for row in objects:
        parts = PurePosixPath(row["path"]).parts
        if len(parts) == 4 and parts[0] == "runs" and parts[3] == "manifest.json":
            roots.append("/".join(parts[:3]))
    return sorted(set(roots))


def audit_attempt(
    root: str,
    *,
    metadata_root: Path,
    object_map: dict[str, dict[str, Any]],
    remote_root: str,
) -> dict[str, Any]:
    parts = PurePosixPath(root).parts
    expected_job, expected_attempt = parts[1], parts[2]
    errors: list[str] = []
    manifest: dict[str, Any] = {}
    inventory: dict[str, dict[str, Any]] = {}
    checksums: dict[str, str] = {}
    raw: dict[str, bytes] = {}
    for name in ("manifest.json", "inventory.json", "checksums.sha256"):
        relative = f"{root}/{name}"
        try:
            raw[name] = _read_metadata(metadata_root, relative)
        except ValueError as exc:
            errors.append(str(exc))
    if "manifest.json" in raw:
        try:
            manifest = _json_bytes(raw["manifest.json"], "manifest.json")
        except ValueError as exc:
            errors.append(str(exc))
    if "inventory.json" in raw:
        try:
            inventory = inventory_map(_json_bytes(raw["inventory.json"], "inventory.json"))
        except ValueError as exc:
            errors.append(str(exc))
    if "checksums.sha256" in raw:
        try:
            checksums = parse_checksums(raw["checksums.sha256"])
        except ValueError as exc:
            errors.append(str(exc))

    if manifest:
        if manifest.get("job_id") != expected_job:
            errors.append("manifest job_id differs from R2 prefix")
        if manifest.get("attempt_id") != expected_attempt:
            errors.append("manifest attempt_id differs from R2 prefix")
    state = manifest.get("state")
    exit_code = manifest.get("exit_code")
    expected_marker = None
    if state == "completed" and exit_code == 0:
        expected_marker = "_SUCCESS"
    elif state == "failed" and isinstance(exit_code, int) and exit_code != 0:
        expected_marker = "_FAILED"
    else:
        errors.append("manifest state/exit_code is not a valid terminal pair")
    if expected_marker and f"{root}/{expected_marker}" not in object_map:
        errors.append(f"missing {expected_marker} marker")
    other_marker = "_FAILED" if expected_marker == "_SUCCESS" else "_SUCCESS"
    if expected_marker and f"{root}/{other_marker}" in object_map:
        errors.append(f"conflicting {other_marker} marker")

    if manifest and inventory and checksums:
        manifest_meta = inventory.get("manifest.json")
        manifest_sha = sha256_bytes(raw["manifest.json"])
        if (
            manifest_meta is None
            or manifest_meta["sha256"] != manifest_sha
            or manifest_meta["size_bytes"] != len(raw["manifest.json"])
            or checksums.get("manifest.json") != manifest_sha
        ):
            errors.append("manifest digest/size metadata is inconsistent")
        if checksums.get("inventory.json") != sha256_bytes(raw["inventory.json"]):
            errors.append("inventory digest differs from checksums.sha256")
        for name, item in inventory.items():
            full_name = f"{root}/{name}"
            listed = object_map.get(full_name)
            if listed is None:
                errors.append(f"inventory object is absent from R2 listing: {name}")
            elif listed["size_bytes"] != item["size_bytes"]:
                errors.append(f"R2 listing size differs from inventory for {name}")
            if name not in checksums:
                errors.append(f"inventory object has no checksum entry: {name}")
            elif checksums[name] != item["sha256"]:
                errors.append(f"checksum differs from inventory for {name}")

    verified = not errors
    if verified and state == "completed":
        audit_state = "verified_completed"
    elif verified and state == "failed":
        audit_state = "verified_failed"
    else:
        audit_state = "unverified"
    return {
        "schema": ATTEMPT_SCHEMA,
        "source_id": stable_id(remote_root.rstrip("/"), root),
        "r2_prefix": f"{remote_root.rstrip('/')}/{root}",
        "job_id": expected_job,
        "attempt_id": expected_attempt,
        "audit_state": audit_state,
        "audit_errors": sorted(set(errors)),
        "manifest": {
            key: manifest.get(key)
            for key in (
                "state",
                "exit_code",
                "code_sha",
                "code_ref",
                "host",
                "started_at",
                "ended_at",
            )
        },
        "inventory": inventory,
    }


def strip_suffix(name: str, suffixes: Iterable[str]) -> tuple[str, str] | None:
    lower = name.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            return name[: -len(suffix)], suffix
    return None


def risk_tags(path: str) -> list[str]:
    return sorted(tag for tag, pattern in RISK_PATTERNS.items() if pattern.search(path))


def build_candidate(
    row: dict[str, Any],
    *,
    object_map: dict[str, dict[str, Any]],
    attempts: dict[str, dict[str, Any]],
    remote_root: str,
) -> dict[str, Any]:
    path = row["path"]
    parsed = strip_suffix(path, DATA_SUFFIXES)
    if parsed is None:
        raise ValueError(f"not a JNNW object: {path}")
    base, _suffix = parsed
    parts = PurePosixPath(path).parts
    run_root = "/".join(parts[:3]) if len(parts) >= 4 and parts[0] == "runs" else None
    attempt = attempts.get(run_root or "")
    artifact_rel = "/".join(parts[3:]) if attempt else None
    inventory_item = attempt["inventory"].get(artifact_rel) if attempt and artifact_rel else None

    exact_meta = [base + suffix for suffix in META_SUFFIXES if base + suffix in object_map]
    directory = str(PurePosixPath(path).parent)
    same_dir_meta = [
        item_path
        for item_path in object_map
        if str(PurePosixPath(item_path).parent) == directory
        and strip_suffix(item_path, META_SUFFIXES) is not None
    ]
    if exact_meta:
        meta_path = exact_meta[0]
        pairing = "exact_basename"
    elif len(same_dir_meta) == 1:
        meta_path = same_dir_meta[0]
        pairing = "only_sidecar_in_directory"
    else:
        meta_path = None
        pairing = "missing_or_ambiguous"

    models: list[dict[str, Any]] = []
    if attempt:
        for name, item in sorted(attempt["inventory"].items()):
            if strip_suffix(name, MODEL_SUFFIXES):
                models.append({"path": name, **item})

    tags = risk_tags(path)
    reasons: list[str] = []
    disposition = "review"
    if row["size_bytes"] <= (8 if path.lower().endswith(".jnnw") else 0):
        disposition = "reject"
        reasons.append("empty_or_header_only_payload")
    if attempt and attempt["audit_state"] == "verified_failed":
        disposition = "reject"
        reasons.append("failed_runner_attempt")
    elif attempt is None:
        if disposition != "reject":
            disposition = "quarantine"
        reasons.append("outside_runner_attempt_needs_historical_reconstruction")
    elif attempt["audit_state"] != "verified_completed":
        if disposition != "reject":
            disposition = "quarantine"
        reasons.append("runner_metadata_not_verified")
    if meta_path is None:
        if disposition != "reject":
            disposition = "quarantine"
        reasons.append("aligned_jsm_missing_or_ambiguous")
    if tags:
        if disposition != "reject":
            disposition = "quarantine"
        reasons.append("derived_or_special_domain_requires_lineage_review")

    source_id = attempt["source_id"] if attempt else stable_id(remote_root, path)
    data_sha = inventory_item.get("sha256") if inventory_item else None
    unknown = []
    if not attempt or not attempt["manifest"].get("started_at"):
        unknown.append("generation_date")
    unknown.extend(
        [
            "generation_index",
            "generator_model_sha256",
            "selfplay_search_parameters",
            "exploration_parameters",
            "adjudication_parameters",
            "parent_corpus_ids",
        ]
    )
    return {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": stable_id(source_id, path, data_sha or "sha-unknown"),
        "source_id": source_id,
        "source_class": "runner_attempt" if attempt else "historical_or_unmanaged_object",
        "data": {
            "r2_uri": f"{remote_root.rstrip('/')}/{path}",
            "path": path,
            "size_bytes": row["size_bytes"],
            "r2_modtime": row.get("modtime"),
            "declared_sha256": data_sha,
            "payload_bytes_verified": False,
        },
        "metadata": {
            "r2_uri": f"{remote_root.rstrip('/')}/{meta_path}" if meta_path else None,
            "path": meta_path,
            "pairing": pairing,
            "schema": None,
            "record_count": None,
        },
        "origin": {
            "job_id": attempt["job_id"] if attempt else None,
            "attempt_id": attempt["attempt_id"] if attempt else None,
            "code_sha": attempt["manifest"].get("code_sha") if attempt else None,
            "host": attempt["manifest"].get("host") if attempt else None,
            "started_at": attempt["manifest"].get("started_at") if attempt else None,
            "ended_at": attempt["manifest"].get("ended_at") if attempt else None,
            "generation_index": None,
            "generator_models_in_same_attempt": models,
            "generator_model_sha256": None,
            "selfplay_parameters": None,
            "parent_corpus_ids": None,
            "unknown_fields": unknown,
        },
        "quality": {
            "disposition": disposition,
            "reasons": sorted(set(reasons)),
            "risk_tags": tags,
            "strength_or_loss_used_for_classification": False,
            "automatic_training_admission": False,
        },
    }


def load_snapshot_candidates(
    metadata_root: Path,
    *,
    remote_root: str,
) -> list[dict[str, Any]]:
    """Expand path manifests without restoring any archived Git blob."""
    rows: list[dict[str, Any]] = []
    historical = metadata_root / "historical"
    if not historical.is_dir():
        return rows
    for manifest_path in sorted(historical.rglob("paths.jsonl.gz")):
        relative_manifest = manifest_path.relative_to(metadata_root).as_posix()
        archive_prefix = relative_manifest.rsplit("/manifests/paths.jsonl.gz", 1)[0]
        try:
            with gzip.open(manifest_path, "rt", encoding="utf-8") as handle:
                entries = [json.loads(line) for line in handle if line.strip()]
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid historical path manifest {relative_manifest}: {exc}") from exc
        normalized: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"non-object entry in {relative_manifest}")
            branch = entry.get("branch")
            git_path = normalize_relative_path(entry.get("path"))
            oid = entry.get("oid")
            if branch not in {"main", "develop"}:
                raise ValueError(f"invalid branch in {relative_manifest}: {branch!r}")
            if not isinstance(oid, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid) is None:
                raise ValueError(f"invalid Git blob oid in {relative_manifest}")
            normalized.append({"branch": branch, "path": git_path, "oid": oid})
        index = {(item["branch"], item["path"]): item for item in normalized}
        for entry in normalized:
            parsed = strip_suffix(entry["path"], DATA_SUFFIXES)
            if parsed is None:
                continue
            base, _suffix = parsed
            meta_entry = next(
                (
                    index[(entry["branch"], base + suffix)]
                    for suffix in META_SUFFIXES
                    if (entry["branch"], base + suffix) in index
                ),
                None,
            )
            source_id = stable_id(remote_root, archive_prefix, entry["branch"], entry["oid"])
            rows.append({
                "schema": CANDIDATE_SCHEMA,
                "candidate_id": stable_id(source_id, entry["path"], entry["oid"]),
                "source_id": source_id,
                "source_class": "historical_git_snapshot",
                "data": {
                    "r2_uri": None,
                    "path": entry["path"],
                    "size_bytes": None,
                    "r2_modtime": None,
                    "declared_sha256": entry["oid"] if len(entry["oid"]) == 64 else None,
                    "git_blob_oid": entry["oid"],
                    "archive_locator": {
                        "archive_prefix": f"{remote_root.rstrip('/')}/{archive_prefix}",
                        "branch": entry["branch"],
                        "path": entry["path"],
                        "paths_manifest": relative_manifest,
                    },
                    "payload_bytes_verified": False,
                },
                "metadata": {
                    "r2_uri": None,
                    "path": meta_entry["path"] if meta_entry else None,
                    "git_blob_oid": meta_entry["oid"] if meta_entry else None,
                    "pairing": "exact_basename" if meta_entry else "missing_or_ambiguous",
                    "schema": None,
                    "record_count": None,
                },
                "origin": {
                    "job_id": None,
                    "attempt_id": None,
                    "code_sha": None,
                    "host": None,
                    "started_at": None,
                    "ended_at": None,
                    "generation_index": None,
                    "generator_models_in_same_attempt": [],
                    "generator_model_sha256": None,
                    "selfplay_parameters": None,
                    "parent_corpus_ids": None,
                    "unknown_fields": [
                        "generation_date", "generation_index", "generator_model_sha256",
                        "selfplay_search_parameters", "exploration_parameters",
                        "adjudication_parameters", "parent_corpus_ids",
                    ],
                },
                "quality": {
                    "disposition": "quarantine",
                    "reasons": [
                        "historical_git_snapshot_requires_blob_restore_and_lineage_review",
                        *([] if meta_entry else ["aligned_jsm_missing_or_ambiguous"]),
                    ],
                    "risk_tags": risk_tags(entry["path"]),
                    "strength_or_loss_used_for_classification": False,
                    "automatic_training_admission": False,
                },
            })
    return rows


def atomic_write(path: Path, raw: bytes) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    payload = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )
    atomic_write(path, payload)


def run(args: argparse.Namespace) -> dict[str, Any]:
    objects = load_object_index(Path(args.object_index))
    object_map = {row["path"]: row for row in objects}
    attempt_rows = [
        audit_attempt(
            root,
            metadata_root=Path(args.metadata_root),
            object_map=object_map,
            remote_root=args.remote_root,
        )
        for root in attempt_roots(objects)
    ]
    attempts = {
        "/".join(("runs", row["job_id"], row["attempt_id"])): row
        for row in attempt_rows
    }
    direct_candidates = [
        build_candidate(
            row,
            object_map=object_map,
            attempts=attempts,
            remote_root=args.remote_root,
        )
        for row in objects
        if strip_suffix(row["path"], DATA_SUFFIXES) is not None
    ]
    snapshot_candidates = load_snapshot_candidates(
        Path(args.metadata_root), remote_root=args.remote_root
    )
    candidates = direct_candidates + snapshot_candidates
    candidates.sort(key=lambda row: (row["data"]["path"], row["candidate_id"]))
    if not candidates:
        raise ValueError("R2 census found zero JNNW corpus candidates")

    out = Path(args.out_dir)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    object_rows = [
        {"schema": "jass.megacorpus.r2_object.v1", **row}
        for row in objects
    ]
    write_jsonl(out / "r2-objects.jsonl", object_rows)
    write_jsonl(out / "runner-attempts.jsonl", attempt_rows)
    write_jsonl(out / "corpus-candidates.jsonl", candidates)

    top_level = Counter(PurePosixPath(row["path"]).parts[0] for row in objects)
    attempt_counts = Counter(row["audit_state"] for row in attempt_rows)
    dispositions = Counter(row["quality"]["disposition"] for row in candidates)
    risk_counts = Counter(
        tag for row in candidates for tag in row["quality"]["risk_tags"]
    )
    summary = {
        "schema": CATALOG_SCHEMA,
        "operation": "read_only_r2_census",
        "remote_root": args.remote_root.rstrip("/"),
        "object_count": len(objects),
        "object_bytes": sum(row["size_bytes"] for row in objects),
        "objects_by_top_level_prefix": dict(sorted(top_level.items())),
        "runner_attempt_count": len(attempt_rows),
        "runner_attempts_by_audit_state": dict(sorted(attempt_counts.items())),
        "corpus_candidate_count": len(candidates),
        "direct_corpus_candidate_count": len(direct_candidates),
        "historical_snapshot_candidate_count": len(snapshot_candidates),
        "candidate_bytes_known": sum(
            row["data"]["size_bytes"] or 0 for row in candidates
        ),
        "candidate_bytes_unknown_count": sum(
            row["data"]["size_bytes"] is None for row in candidates
        ),
        "candidates_by_disposition": dict(sorted(dispositions.items())),
        "candidate_risk_tags": dict(sorted(risk_counts.items())),
        "payload_objects_downloaded": 0,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
        "catalog_files": {},
    }
    for name in ("r2-objects.jsonl", "runner-attempts.jsonl", "corpus-candidates.jsonl"):
        path = out / name
        summary["catalog_files"][name] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    atomic_write(
        out / "catalog-summary.json",
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object-index", required=True)
    parser.add_argument("--metadata-root", required=True)
    parser.add_argument("--remote-root", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    try:
        summary = run(args)
    except (OSError, ValueError) as exc:
        print(f"jass_megacorpus_catalog: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
