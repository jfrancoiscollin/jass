#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Triage a MegaCorpus P0 catalogue without opening any corpus payload.

P1 turns the fail-closed P0 catalogue into a bounded review queue and an
evidence-only lineage graph.  It deliberately does not infer ancestry from
filenames and never admits a candidate to training.  Clean ``review`` rows are
eligible only for a later, explicitly authorised payload sample.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Iterable, Iterator, TextIO


CANDIDATE_SCHEMA = "jass.megacorpus.corpus_candidate.v1"
ATTEMPT_SCHEMA = "jass.megacorpus.runner_attempt.v1"
OUTPUT_SCHEMA = "jass.megacorpus.p1_triage.v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
ALLOWED_DISPOSITIONS = {"review", "quarantine", "reject"}
ALLOWED_SOURCE_CLASSES = {
    "runner_attempt", "historical_or_unmanaged_object", "historical_git_snapshot",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def open_text(path: Path) -> Iterator[TextIO]:
    if path.name.lower().endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            yield handle
    else:
        with path.open("rt", encoding="utf-8") as handle:
            yield handle


def load_jsonl(path: Path, *, schema: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open_text(path) as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}: invalid JSON line {line_number}: {exc}") from exc
            if not isinstance(row, dict) or row.get("schema") != schema:
                raise ValueError(f"{path}: invalid schema at line {line_number}")
            rows.append(row)
    if not rows:
        raise ValueError(f"{path}: empty JSONL input")
    return rows


def require_mapping(row: dict[str, Any], name: str) -> dict[str, Any]:
    value = row.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"candidate {row.get('candidate_id')!r}: {name} is not an object")
    return value


def validate_candidates(rows: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for row in rows:
        candidate_id = row.get("candidate_id")
        source_id = row.get("source_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError("candidate has no stable candidate_id")
        if candidate_id in seen:
            raise ValueError(f"duplicate candidate_id: {candidate_id}")
        seen.add(candidate_id)
        if not isinstance(source_id, str) or not source_id:
            raise ValueError(f"candidate {candidate_id}: source_id is missing")
        if row.get("source_class") not in ALLOWED_SOURCE_CLASSES:
            raise ValueError(f"candidate {candidate_id}: invalid source_class")
        data = require_mapping(row, "data")
        quality = require_mapping(row, "quality")
        origin = require_mapping(row, "origin")
        if not isinstance(data.get("path"), str) or not data["path"]:
            raise ValueError(f"candidate {candidate_id}: data.path is missing")
        size = data.get("size_bytes")
        if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 0):
            raise ValueError(f"candidate {candidate_id}: invalid size_bytes")
        digest = data.get("declared_sha256")
        if digest is not None and (not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None):
            raise ValueError(f"candidate {candidate_id}: invalid declared_sha256")
        disposition = quality.get("disposition")
        if disposition not in ALLOWED_DISPOSITIONS:
            raise ValueError(f"candidate {candidate_id}: invalid disposition {disposition!r}")
        for key in ("reasons", "risk_tags"):
            value = quality.get(key)
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError(f"candidate {candidate_id}: invalid quality.{key}")
        parents = origin.get("parent_corpus_ids")
        if parents is not None and (
            not isinstance(parents, list) or any(not isinstance(parent, str) or not parent for parent in parents)
        ):
            raise ValueError(f"candidate {candidate_id}: invalid parent_corpus_ids")
        if quality.get("automatic_training_admission") is not False:
            raise ValueError(f"candidate {candidate_id}: P0 admission guard is not false")


def validate_attempts(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_source: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_id = row.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("runner attempt has no source_id")
        if source_id in by_source:
            raise ValueError(f"duplicate runner attempt source_id: {source_id}")
        if row.get("audit_state") not in {"verified_completed", "verified_failed", "unverified"}:
            raise ValueError(f"runner attempt {source_id}: invalid audit_state")
        by_source[source_id] = row
    return by_source


def recovery_route(candidate: dict[str, Any]) -> str:
    quality = candidate["quality"]
    disposition = quality["disposition"]
    reasons = set(quality["reasons"])
    if disposition == "reject":
        return "reject_catalogue_evidence"
    if disposition == "review":
        return "sample_after_human_review"
    if candidate.get("source_class") == "historical_git_snapshot":
        return "restore_snapshot_metadata_first"
    if "runner_metadata_not_verified" in reasons:
        return "repair_runner_audit"
    if "outside_runner_attempt_needs_historical_reconstruction" in reasons:
        return "reconstruct_unmanaged_provenance"
    if "aligned_jsm_missing_or_ambiguous" in reasons:
        return "resolve_aligned_sidecar"
    if "derived_or_special_domain_requires_lineage_review" in reasons:
        return "resolve_derived_lineage"
    return "manual_quarantine_review"


def preliminary_bucket(candidate: dict[str, Any]) -> str:
    disposition = candidate["quality"]["disposition"]
    if disposition == "review":
        return "sample"
    return disposition


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


def write_json(path: Path, payload: object) -> None:
    atomic_write(path, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    raw = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )
    atomic_write(path, raw)


def candidate_triage_row(candidate: dict[str, Any]) -> dict[str, Any]:
    data = candidate["data"]
    metadata = candidate["metadata"]
    quality = candidate["quality"]
    origin = candidate["origin"]
    return {
        "schema": "jass.megacorpus.p1_candidate_decision.v1",
        "candidate_id": candidate["candidate_id"],
        "source_id": candidate["source_id"],
        "source_class": candidate.get("source_class"),
        "data_path": data["path"],
        "data_r2_uri": data.get("r2_uri"),
        "size_bytes": data.get("size_bytes"),
        "declared_sha256": data.get("declared_sha256"),
        "metadata_path": metadata.get("path"),
        "metadata_pairing": metadata.get("pairing"),
        "job_id": origin.get("job_id"),
        "attempt_id": origin.get("attempt_id"),
        "catalogue_disposition": quality["disposition"],
        "preliminary_bucket": preliminary_bucket(candidate),
        "recovery_route": recovery_route(candidate),
        "reasons": sorted(set(quality["reasons"])),
        "risk_tags": sorted(set(quality["risk_tags"])),
        "payload_sample_authorized": False,
        "accepted_for_training": False,
        "strength_or_loss_used_for_classification": False,
    }


def review_row(candidate: dict[str, Any]) -> dict[str, Any]:
    triage = candidate_triage_row(candidate)
    return {
        key: triage[key]
        for key in (
            "candidate_id", "source_id", "data_path", "data_r2_uri", "size_bytes",
            "declared_sha256", "metadata_path", "metadata_pairing", "job_id",
            "attempt_id", "recovery_route", "payload_sample_authorized",
            "accepted_for_training",
        )
    }


def lineage_graph(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    sources: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        source_id = candidate["source_id"]
        source = sources.setdefault(source_id, {
            "schema": "jass.megacorpus.p1_lineage_graph.v1",
            "kind": "node",
            "node_type": "source",
            "node_id": source_id,
            "source_class": candidate.get("source_class"),
        })
        if source["source_class"] != candidate.get("source_class"):
            raise ValueError(f"source {source_id}: inconsistent source_class")
    rows.extend(sources[key] for key in sorted(sources))

    known_nodes = set(sources)
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        known_nodes.add(candidate_id)
        rows.append({
            "schema": "jass.megacorpus.p1_lineage_graph.v1",
            "kind": "node",
            "node_type": "candidate",
            "node_id": candidate_id,
            "data_path": candidate["data"]["path"],
            "declared_sha256": candidate["data"].get("declared_sha256"),
        })
        rows.append({
            "schema": "jass.megacorpus.p1_lineage_graph.v1",
            "kind": "edge",
            "edge_type": "source_contains_candidate",
            "from": candidate["source_id"],
            "to": candidate_id,
            "evidence": "p0_catalogue_source_id",
        })

    duplicate_groups: list[dict[str, Any]] = []
    by_digest: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        digest = candidate["data"].get("declared_sha256")
        if digest:
            by_digest[digest].append(candidate)
    for digest, group in sorted(by_digest.items()):
        if len(group) < 2:
            continue
        sizes = {candidate["data"].get("size_bytes") for candidate in group}
        if len({size for size in sizes if size is not None}) > 1:
            raise ValueError(f"declared SHA {digest} has inconsistent known sizes")
        ids = sorted(candidate["candidate_id"] for candidate in group)
        canonical = ids[0]
        duplicate_groups.append({
            "schema": "jass.megacorpus.p1_exact_duplicate_group.v1",
            "declared_sha256": digest,
            "canonical_candidate_id": canonical,
            "candidate_ids": ids,
            "known_size_bytes": next(iter(sizes)) if len(sizes) == 1 else None,
            "payload_bytes_verified": False,
            "evidence": "catalogue_declared_sha256_only",
        })
        for duplicate in ids[1:]:
            rows.append({
                "schema": "jass.megacorpus.p1_lineage_graph.v1",
                "kind": "edge",
                "edge_type": "declared_exact_duplicate",
                "from": duplicate,
                "to": canonical,
                "evidence": {"declared_sha256": digest, "payload_bytes_verified": False},
            })

    for candidate in candidates:
        for parent in candidate["origin"].get("parent_corpus_ids") or []:
            rows.append({
                "schema": "jass.megacorpus.p1_lineage_graph.v1",
                "kind": "edge",
                "edge_type": "explicit_parent",
                "from": parent,
                "to": candidate["candidate_id"],
                "evidence": "origin.parent_corpus_ids",
                "parent_resolved_in_catalogue": parent in known_nodes,
            })
    rows.sort(key=lambda row: (
        row["kind"], row.get("node_type", ""), row.get("node_id", ""),
        row.get("edge_type", ""), row.get("from", ""), row.get("to", ""),
    ))
    return rows, duplicate_groups


def run(args: argparse.Namespace) -> dict[str, Any]:
    candidate_path = Path(args.candidates)
    attempt_path = Path(args.attempts)
    candidates = load_jsonl(candidate_path, schema=CANDIDATE_SCHEMA)
    attempts = load_jsonl(attempt_path, schema=ATTEMPT_SCHEMA)
    validate_candidates(candidates)
    attempts_by_source = validate_attempts(attempts)
    candidates.sort(key=lambda row: (row["data"]["path"], row["candidate_id"]))

    for candidate in candidates:
        if candidate.get("source_class") == "runner_attempt" and candidate["source_id"] not in attempts_by_source:
            raise ValueError(f"candidate {candidate['candidate_id']}: runner source is absent")

    triage_rows = [candidate_triage_row(candidate) for candidate in candidates]
    graph_rows, duplicate_groups = lineage_graph(candidates)
    review_candidates = [review_row(candidate) for candidate in candidates if preliminary_bucket(candidate) == "sample"]

    disposition_counts = Counter(row["catalogue_disposition"] for row in triage_rows)
    bucket_counts = Counter(row["preliminary_bucket"] for row in triage_rows)
    route_counts = Counter(row["recovery_route"] for row in triage_rows)
    source_counts = Counter(row["source_class"] for row in triage_rows)
    reason_counts = Counter(reason for row in triage_rows for reason in row["reasons"])
    risk_counts = Counter(tag for row in triage_rows for tag in row["risk_tags"])
    bytes_by_bucket = Counter()
    unknown_bytes_by_bucket = Counter()
    for row in triage_rows:
        if row["size_bytes"] is None:
            unknown_bytes_by_bucket[row["preliminary_bucket"]] += 1
        else:
            bytes_by_bucket[row["preliminary_bucket"]] += row["size_bytes"]

    reason_sets = Counter(tuple(row["reasons"]) for row in triage_rows if row["preliminary_bucket"] == "quarantine")
    quarantine_groups = [{
        "reasons": list(reasons),
        "candidate_count": count,
    } for reasons, count in sorted(reason_sets.items(), key=lambda item: (-item[1], item[0]))]

    out = Path(args.out_dir)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "candidate-triage.jsonl", triage_rows)
    write_jsonl(out / "lineage-graph.jsonl", graph_rows)
    write_jsonl(out / "exact-duplicate-groups.jsonl", duplicate_groups)
    write_json(out / "review-candidates.json", {
        "schema": OUTPUT_SCHEMA,
        "candidate_count": len(review_candidates),
        "payload_sample_authorized": False,
        "training_authorized": False,
        "candidates": review_candidates,
    })
    write_json(out / "quarantine-groups.json", {
        "schema": OUTPUT_SCHEMA,
        "candidate_count": bucket_counts.get("quarantine", 0),
        "groups": quarantine_groups,
    })

    summary = {
        "schema": OUTPUT_SCHEMA,
        "operation": "metadata_only_p1_triage",
        "candidate_count": len(candidates),
        "runner_attempt_count": len(attempts),
        "catalogue_dispositions": dict(sorted(disposition_counts.items())),
        "preliminary_buckets": dict(sorted(bucket_counts.items())),
        "recovery_routes": dict(sorted(route_counts.items())),
        "source_classes": dict(sorted(source_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "risk_tag_counts": dict(sorted(risk_counts.items())),
        "known_bytes_by_preliminary_bucket": dict(sorted(bytes_by_bucket.items())),
        "unknown_size_candidates_by_preliminary_bucket": dict(sorted(unknown_bytes_by_bucket.items())),
        "payload_sample_candidate_count": len(review_candidates),
        "training_accept_count": 0,
        "exact_duplicate_group_count": len(duplicate_groups),
        "exact_duplicate_candidate_count": sum(len(group["candidate_ids"]) for group in duplicate_groups),
        "lineage_node_count": sum(row["kind"] == "node" for row in graph_rows),
        "lineage_edge_count": sum(row["kind"] == "edge" for row in graph_rows),
        "filename_inferred_lineage_edge_count": 0,
        "inputs": {
            "candidates_sha256": sha256_file(candidate_path),
            "attempts_sha256": sha256_file(attempt_path),
        },
        "payload_objects_downloaded": 0,
        "frozen_cohorts_read": 0,
        "strength_or_loss_read": False,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
        "verdict": "JASS_MEGACORPUS_P1_TRIAGE_READY",
    }
    write_json(out / "p1-summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--attempts", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    try:
        summary = run(args)
    except (OSError, ValueError) as exc:
        print(f"jass_megacorpus_p1_triage: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
