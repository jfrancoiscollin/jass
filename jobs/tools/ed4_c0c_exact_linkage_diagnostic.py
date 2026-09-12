#!/usr/bin/env python3
"""Fail-closed structural primitives for the ED4 exact-linkage diagnostic.

The stage wrapper deliberately has no fallback manifest.  These helpers only
decode an authenticated TSV header and manifest-allowed structural fields.  A
TSV's other cells remain bytes throughout parsing and are never passed to a
text/CSV/JSON decoder.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import struct
import gzip
import time
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from jobs.tools.adaptive_sibling_b2_exclusions import canonical_fingerprint, format_fingerprint


OUTPUT_NAME = "ed4-c0c-exact-linkage-diagnostic-v1"
STRUCTURAL_FIELDS = frozenset({
    "row_index", "parent_id", "parent_fingerprint", "parent_canonical",
    "parent_stm", "child_fingerprint", "child_canonical", "sibling_identity",
})
JNNW_HEADER_BYTES = 8
JNNW_RECORD_BYTES = 38
JNNW_PREFIX_BYTES = 33


class ExactLinkageError(RuntimeError):
    """A contract violation which must block the diagnostic."""


@dataclass
class SemanticReadLedger:
    transport_bytes_hashed: int = 0
    headers_read: int = 0
    structural_field_values_read: int = 0
    position_identity_records_read: int = 0
    position_identity_records_validated: int = 0
    forbidden_field_values_read: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "transport_bytes_hashed": self.transport_bytes_hashed,
            "headers_read": self.headers_read,
            "structural_field_values_read": self.structural_field_values_read,
            "position_identity_records_read": self.position_identity_records_read,
            "position_identity_records_validated": self.position_identity_records_validated,
            "forbidden_field_values_read": self.forbidden_field_values_read,
        }


@dataclass(frozen=True)
class TsvSchema:
    """A source-specific schema frozen by the companion manifest."""

    columns: tuple[str, ...]
    allowed_fields: frozenset[str]
    expected_rows: int
    parent_count: int
    parent_child_counts: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if not self.columns or len(set(self.columns)) != len(self.columns):
            raise ExactLinkageError("tsv_schema_columns")
        if not self.allowed_fields <= STRUCTURAL_FIELDS:
            raise ExactLinkageError("tsv_schema_forbidden_allowed_field")
        if not self.allowed_fields <= set(self.columns):
            raise ExactLinkageError("tsv_schema_allowed_field_missing")
        if "row_index" not in self.allowed_fields or "parent_id" not in self.allowed_fields:
            raise ExactLinkageError("tsv_schema_required_field_missing")
        if self.expected_rows < 0 or self.parent_count < 0:
            raise ExactLinkageError("tsv_schema_count")
        if self.parent_child_counts is not None:
            if len(self.parent_child_counts) != self.parent_count or any(n < 0 for n in self.parent_child_counts):
                raise ExactLinkageError("tsv_schema_parent_geometry")
            if sum(self.parent_child_counts) != self.expected_rows:
                raise ExactLinkageError("tsv_schema_row_geometry")


def opaque_sha256(payload: bytes, ledger: SemanticReadLedger) -> str:
    """Hash transport bytes without assigning semantic meaning to them."""
    ledger.transport_bytes_hashed += len(payload)
    return hashlib.sha256(payload).hexdigest()


def require_exact_sha256(payload: bytes, expected_sha256: str, ledger: SemanticReadLedger) -> None:
    """Authenticate a payload before its header or structural fields are read."""
    if len(expected_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in expected_sha256):
        raise ExactLinkageError("manifest_sha256")
    if opaque_sha256(payload, ledger) != expected_sha256:
        raise ExactLinkageError("companion_hash_drift")


def require_exact_descriptor_rows(expected: Iterable[tuple[str, ...]], observed: Iterable[tuple[str, ...]]) -> None:
    """Require the manifest's complete descriptor key set, with no aliases."""
    expected_rows, observed_rows = tuple(expected), tuple(observed)
    if len(set(expected_rows)) != len(expected_rows):
        raise ExactLinkageError("manifest_duplicate_descriptor")
    if len(set(observed_rows)) != len(observed_rows):
        raise ExactLinkageError("observed_duplicate_descriptor")
    if len(expected_rows) != len(observed_rows):
        raise ExactLinkageError("descriptor_cardinality")
    if set(expected_rows) != set(observed_rows):
        if set(observed_rows) - set(expected_rows):
            raise ExactLinkageError("novel_descriptor_row")
        raise ExactLinkageError("missing_descriptor_row")


def load_frozen_manifest(path: str, expected_sha256: str) -> dict:
    """Load the private manifest only after authenticating its exact bytes."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ExactLinkageError("exact_linkage_manifest_unavailable") from exc
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ExactLinkageError("exact_linkage_manifest_hash_drift")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExactLinkageError("exact_linkage_manifest_json") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != "jass.ed4.c0c_exact_linkage_manifest.v1":
        raise ExactLinkageError("exact_linkage_manifest_schema")
    if len(manifest.get("failure_rows", [])) != 21 or len(manifest.get("tsv_cases", [])) != 4:
        raise ExactLinkageError("exact_linkage_manifest_cardinality")
    return manifest


def jnnw_prefixes(payload: bytes, expected_count: int, ledger: SemanticReadLedger) -> tuple[bytes, ...]:
    """Read only header plus each record's bytes 0:33; never unpack 33:38."""
    if len(payload) < JNNW_HEADER_BYTES or payload[:4] != b"JNNW":
        raise ExactLinkageError("jnnw_header")
    count = int.from_bytes(payload[4:8], "little")
    if count != expected_count or len(payload) != JNNW_HEADER_BYTES + JNNW_RECORD_BYTES * count:
        raise ExactLinkageError("jnnw_geometry")
    ledger.headers_read += 1
    prefixes = tuple(payload[JNNW_HEADER_BYTES + i * JNNW_RECORD_BYTES:JNNW_HEADER_BYTES + i * JNNW_RECORD_BYTES + JNNW_PREFIX_BYTES]
                     for i in range(count))
    ledger.position_identity_records_read += count
    return prefixes


def prefix_fingerprint(prefix: bytes) -> str:
    """Format one validated 33-byte identity prefix; never touch bytes 33:38."""
    if len(prefix) != JNNW_PREFIX_BYTES:
        raise ExactLinkageError("jnnw_prefix_size")
    wm, wk, bm, bk, stm = struct.unpack("<QQQQB", prefix)
    try:
        # This existing formatter/parser pair enforces 50-bit bounds, disjoint
        # boards, normalized format and STM in {0,1}.
        raw = format_fingerprint(wm, wk, bm, bk, stm)
        canonical_fingerprint(raw)
        return raw
    except (ValueError, RuntimeError) as exc:
        raise ExactLinkageError("jnnw_prefix_invalid") from exc


def _lines(payload: bytes) -> Iterable[bytes]:
    # splitlines does not decode data.  A missing final newline is accepted, as
    # long as it cannot create an extra empty data row.
    for line in payload.splitlines():
        yield line.rstrip(b"\r")


def _decode_structural(value: bytes, field: str, ledger: SemanticReadLedger) -> str:
    try:
        decoded = value.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ExactLinkageError("tsv_structural_utf8") from exc
    ledger.structural_field_values_read += 1
    return decoded


def selective_tsv_rows(payload: bytes, schema: TsvSchema, ledger: SemanticReadLedger) -> tuple[dict[str, str], ...]:
    """Return only allowed structural cells, preserving forbidden cells as bytes.

    This intentionally avoids csv.DictReader and json parsing.  TSV quoting is
    unsupported: the manifest must name an unquoted byte-token TSV schema.
    """
    line_iter = iter(_lines(payload))
    try:
        raw_header = next(line_iter)
    except StopIteration as exc:
        raise ExactLinkageError("tsv_missing_header") from exc
    try:
        header = tuple(cell.decode("utf-8", "strict") for cell in raw_header.split(b"\t"))
    except UnicodeDecodeError as exc:
        raise ExactLinkageError("tsv_header_utf8") from exc
    ledger.headers_read += 1
    if header != schema.columns:
        raise ExactLinkageError("tsv_header_drift")
    allowed_indexes = {i: name for i, name in enumerate(header) if name in schema.allowed_fields}
    rows: list[dict[str, str]] = []
    for ordinal, raw_line in enumerate(line_iter):
        cells = raw_line.split(b"\t")
        if len(cells) != len(header):
            raise ExactLinkageError("tsv_column_count")
        row = {name: _decode_structural(cells[index], name, ledger) for index, name in allowed_indexes.items()}
        try:
            if int(row["row_index"], 10) != ordinal:
                raise ExactLinkageError("tsv_row_index")
            parent_id = int(row["parent_id"], 10)
        except ValueError as exc:
            raise ExactLinkageError("tsv_structural_integer") from exc
        if parent_id < 0 or parent_id >= schema.parent_count:
            raise ExactLinkageError("tsv_parent_id_range")
        rows.append(row)
    if len(rows) != schema.expected_rows:
        raise ExactLinkageError("tsv_row_count")
    validate_row_geometry(rows, schema)
    return tuple(rows)


def validate_row_geometry(rows: Sequence[Mapping[str, str]], schema: TsvSchema) -> None:
    """Require contiguous, nondecreasing parent blocks and unique sibling ids."""
    expected_parent = 0
    current_parent: int | None = None
    closed: set[int] = set()
    sibling_ids: set[str] = set()
    for row in rows:
        parent_id = int(row["parent_id"], 10)
        if current_parent is None:
            if parent_id != 0:
                raise ExactLinkageError("tsv_parent_block_start")
            current_parent = parent_id
        elif parent_id != current_parent:
            closed.add(current_parent)
            if parent_id in closed or parent_id != current_parent + 1:
                raise ExactLinkageError("tsv_parent_block_order")
            current_parent = parent_id
        if "sibling_identity" in row:
            if row["sibling_identity"] in sibling_ids:
                raise ExactLinkageError("tsv_sibling_identity_duplicate")
            sibling_ids.add(row["sibling_identity"])
    if current_parent is None:
        if schema.parent_count != 0:
            raise ExactLinkageError("tsv_parent_block_empty")
    elif current_parent != schema.parent_count - 1:
        raise ExactLinkageError("tsv_parent_block_coverage")


def validate_child_linkage(rows: Sequence[Mapping[str, str]], schema: TsvSchema,
                           child_prefixes: Sequence[bytes], ledger: SemanticReadLedger) -> dict[str, int | str]:
    """Validate same-ordinal child geometry and optional canonical equality."""
    if len(rows) != schema.expected_rows or len(child_prefixes) != schema.expected_rows:
        raise ExactLinkageError("tsv_child_cardinality")
    seen_per_parent = [0] * schema.parent_count
    digest = hashlib.sha256()
    for ordinal, (row, prefix) in enumerate(zip(rows, child_prefixes)):
        parent_id = int(row["parent_id"], 10)
        seen_per_parent[parent_id] += 1
        # Prefixes are structural identity bytes.  Hashing them into a digest is
        # permitted; no identity list is retained or emitted.
        digest.update(prefix)
        raw = prefix_fingerprint(prefix)
        for field in ("child_fingerprint", "child_canonical"):
            if field in row:
                expected = raw if field == "child_fingerprint" else canonical_fingerprint(raw)
                if row[field] != expected:
                    raise ExactLinkageError("tsv_child_prefix_mismatch")
    if schema.parent_child_counts is not None and tuple(seen_per_parent) != schema.parent_child_counts:
        raise ExactLinkageError("tsv_parent_child_geometry")
    return {"linked_rows": len(rows), "child_prefix_digest": digest.hexdigest()}


def validate_parent_linkage(rows: Sequence[Mapping[str, str]], parent_prefixes: Sequence[bytes],
                            ledger: SemanticReadLedger) -> None:
    """Check optional parent canonical/fingerprint fields against indexed parents."""
    for row in rows:
        parent = parent_prefixes[int(row["parent_id"], 10)]
        for field in ("parent_fingerprint", "parent_canonical"):
            if field in row:
                raw = prefix_fingerprint(parent)
                expected = raw if field == "parent_fingerprint" else canonical_fingerprint(raw)
                if row[field] != expected:
                    raise ExactLinkageError("tsv_parent_prefix_mismatch")
        if "parent_stm" in row and row["parent_stm"] != str(parent[32]):
            raise ExactLinkageError("tsv_parent_stm_mismatch")


def descriptor_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (str(row["job_id"]), str(row["attempt_id"]), str(row["path"]))


def _schema_from_manifest(manifest: Mapping[str, object], case: Mapping[str, object]) -> TsvSchema:
    source = manifest["schemas"][case["schema_id"]]  # type: ignore[index]
    return TsvSchema(tuple(source["columns"]), frozenset(source["allowed_fields"]),
                     int(case["expected_data_rows"]), int(case["expected_parent_count"]))


def _canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise ExactLinkageError(code)


def _deadline(deadline: float | None) -> None:
    _need(deadline is None or time.monotonic() < deadline, "exact_linkage_deadline")


def expected_descriptors(manifest) -> dict:
    failures = manifest["failure_rows"]
    _need(len(failures) == 21, "failure_row_cardinality")
    expected = {descriptor_key(r): r for r in failures}
    _need(len(expected) == 21, "failure_row_duplicate")
    for case in manifest["tsv_cases"]:
        for role in ("parents", "children"):
            desc = case[role]
            key = descriptor_key(desc)
            _need(key not in expected or expected[key] == desc, "companion_descriptor_conflict")
            expected[key] = desc
    return expected


def build_synthetic_diagnostic(manifest: Mapping[str, object], payloads: Mapping[tuple[str, str, str], bytes],
                               deadline: float | None = None, transport_hash_bytes: int = 0) -> dict:
    """Execute the exact structural proof over already-authenticated test bytes.

    Production transport must populate this mapping only after C0A/C0B/1931
    metadata authentication. Keeping it injectable makes the no-real-I/O
    contract testable.
    """
    _deadline(deadline)
    ledger = SemanticReadLedger(transport_bytes_hashed=transport_hash_bytes)
    failures = manifest.get("failure_rows")
    if not isinstance(failures, list) or len(failures) != 21:
        raise ExactLinkageError("failure_row_cardinality")
    keys = [descriptor_key(r) for r in failures]
    if len(set(keys)) != 21:
        raise ExactLinkageError("failure_row_duplicate")
    descriptors = expected_descriptors(manifest)
    _need(set(descriptors) == set(payloads), "exact_payload_descriptor_set")
    for key, desc in descriptors.items():
        _deadline(deadline)
        _need(len(payloads[key]) == desc["size_bytes"], "payload_size_drift")
        require_exact_sha256(payloads[key], desc["sha256"], ledger)
    rows: list[dict[str, object]] = []
    by_key = {descriptor_key(row): row for row in failures}
    cases = []
    encountered = set()
    for case in manifest.get("tsv_cases", []):
        schema = _schema_from_manifest(manifest, case)
        aliases = case["aliases"]
        representative = case["representative"]
        raw = payloads[descriptor_key(representative)]
        _deadline(deadline)
        _need(representative in aliases and representative["sha256"] == case["tsv_sha256"], "tsv_representative")
        selected = selective_tsv_rows(raw, schema, ledger)
        parent_key, child_key = descriptor_key(case["parents"]), descriptor_key(case["children"])
        # Companions are provided under their own exact descriptor keys; they
        # are not 1931 failure rows and therefore may only be appended after
        # the frozen 21-row check above by the metadata transport adapter.
        def companion(role, key, count):
            value = payloads[key]
            compression = case[role].get("compression", "none")
            _need(compression in {"none", "gzip"}, "companion_compression")
            if compression == "gzip":
                value = gzip.decompress(value)
            prefixes = jnnw_prefixes(value, count, ledger)
            for index, prefix in enumerate(prefixes):
                if index % 1024 == 0: _deadline(deadline)
                prefix_fingerprint(prefix)
                ledger.position_identity_records_validated += 1
            return prefixes
        parents = companion("parents", parent_key, schema.parent_count)
        children = companion("children", child_key, schema.expected_rows)
        validate_parent_linkage(selected, parents, ledger)
        linkage = validate_child_linkage(selected, schema, children, ledger)
        source_schema = manifest["schemas"][case["schema_id"]]
        header_sha = hashlib.sha256(_canonical(list(schema.columns))).hexdigest()
        _need(header_sha == source_schema["header_canonical_sha256"], "schema_header_hash")
        cases.append({"case_id":case["case_id"], "schema_id":case["schema_id"],
                      "tsv_sha256":case["tsv_sha256"], "header":list(schema.columns),
                      "header_canonical_sha256":header_sha, "column_count":len(schema.columns),
                      "data_rows":len(selected), "parent_count":len(parents), "child_count":len(children),
                      "parents_sha256":case["parents"]["sha256"], "children_sha256":case["children"]["sha256"],
                      "row_width_valid":True, "parent_blocks_complete":True, **linkage})
        for alias in aliases:
            key = descriptor_key(alias)
            _need(key in by_key and alias == by_key[key] and key not in encountered, "tsv_alias_membership")
            _need(payloads[key] == raw, "tsv_alias_drift")
            encountered.add(key)
            rows.append({"descriptor":key, "kind":alias["kind"], "sha256":alias["sha256"],
                         "size_bytes":alias["size_bytes"], "case_id":case["case_id"],
                         "evidence":"exact-tsv-child-linkage-proven"})
    comments = {}
    for alias in manifest["comment_only"]["aliases"]:
        _deadline(deadline)
        key = descriptor_key(alias)
        _need(key in by_key and alias == by_key[key] and key not in encountered, "comment_alias_membership")
        encountered.add(key)
        raw = payloads[descriptor_key(alias)]
        if alias["sha256"] not in comments:
            try:
                text = raw.decode("utf-8", "strict")
            except UnicodeDecodeError as exc:
                raise ExactLinkageError("comment_only_utf8") from exc
            _need(not any(line.split("#",1)[0].strip() for line in text.splitlines()), "comment_only_payload")
            comments[alias["sha256"]] = True
        rows.append({"descriptor":key, "kind":alias["kind"], "sha256":alias["sha256"],
                     "size_bytes":alias["size_bytes"], "evidence":"exact-comment-only-empty-set-proven"})
    invalid = manifest["invalid_stm"]
    _need(invalid.get("complete_coverage_proof") is None and invalid.get("recovery_authorized") is False,
          "unimplemented_coverage_proof")
    inspections = {}
    for alias in invalid["aliases"]:
        _deadline(deadline)
        key = descriptor_key(alias)
        _need(key in by_key and alias == by_key[key] and key not in encountered, "invalid_alias_membership")
        encountered.add(key)
        raw = payloads[descriptor_key(alias)]
        # Strict nominal inspection only; target slots stay opaque.
        if alias["sha256"] not in inspections:
            prefixes = jnnw_prefixes(raw, int(invalid["declared_count"]), ledger)
            histogram = {"zero":0, "one":0, "other":0}
            in_range = disjoint = valid = 0
            projection = hashlib.sha256()
            for index, prefix in enumerate(prefixes):
                if index % 1024 == 0: _deadline(deadline)
                projection.update(prefix)
                wm,wk,bm,bk,stm = struct.unpack("<QQQQB",prefix)
                boards = (wm,wk,bm,bk)
                histogram["zero" if stm == 0 else "one" if stm == 1 else "other"] += 1
                bounds_ok = all(x < (1 << 50) for x in boards)
                disjoint_ok = not any(boards[i]&boards[j] for i in range(4) for j in range(i))
                in_range += bounds_ok
                disjoint += disjoint_ok
                valid += bounds_ok and disjoint_ok and stm in (0,1)
            ledger.position_identity_records_validated += valid
            inspections[alias["sha256"]] = {"magic":"JNNW", "declared_count":len(prefixes),
                "size_equation_valid":True, "nominal_stm_histogram":histogram,
                "strict_nominal_in_range_prefixes":in_range, "strict_nominal_disjoint_prefixes":disjoint,
                "strict_nominal_valid_prefixes":valid, "strict_nominal_projection_sha256":projection.hexdigest(),
                "artifact_causality_proven":False, "authenticated_producer_code":None,
                "shard_count":None, "shard_boundaries":None, "reconstructed_records":None,
                "boundary_crossing_chimeras":None, "incomplete_edge_records":None,
                "alternate_framing_performed":False, "complete_coverage_proven":False}
        rows.append({"descriptor":key, "kind":alias["kind"], "sha256":alias["sha256"],
                     "size_bytes":alias["size_bytes"], "evidence":"unresolved-fail-closed",
                     **inspections[alias["sha256"]]})
    _need(len(rows) == 21 and encountered == set(keys), "recovery_evidence_cardinality")
    _deadline(deadline)
    rows.sort(key=lambda item: item["descriptor"])
    return {"schema": "jass.ed4.c0c_exact_linkage_diagnostic.v1", "output_name": OUTPUT_NAME,
            "state": "completed", "terminal": "ED4_C0C_V7_BLOCKED_BY_INCOMPLETE_STRUCTURAL_COVERAGE",
            "classification":"TECHNICAL_STRUCTURAL_RECOVERY_INVESTIGATION_ONLY",
            "recovery_evidence": rows, "recovery_evidence_sha256":hashlib.sha256(_canonical(rows)).hexdigest(),
            "tsv_cases":cases, "descriptor_count":21, "resolved_descriptor_count":18, "unresolved_descriptor_count":3,
            "read_ledger": ledger.as_dict(),
            "target_reads": 0, "score_reads": 0, "wdl_reads": 0, "qvalue_reads": 0,
            "model_reads": 0, "teacher_calls": 0, "search_calls": 0, "fits": 0,
            "games": 0, "alpha_spent": 0, "scientific_verdict": None,
            "confirmation_authorized": False, "automatic_continuation": False}
