#!/usr/bin/env python3
"""Compile the authenticated, historical-only B2 parent exclusion universe.

The caller fetches each source with ``fetch_result_files.py`` and supplies its
verification report.  This tool never accesses the network and never reads a
teacher, score, label, model, or search result.  It accepts only the identity
TSV and opening-FEN artifacts named by the frozen source catalog.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.tb_frontier_symmetry_dedup import (  # noqa: E402
    canonical_fingerprint as reference_canonical_fingerprint,
)


CATALOG_SCHEMA = "jass.adaptive_sibling_b2_exclusion_sources.v1"
OUTPUT_SCHEMA = "jass.adaptive_sibling_b2_historical_exclusion_manifest.v1"
CANONICALIZATION = "min(exact,rotate180_plus_colour_swap_and_invert_stm)"
SOURCE_TYPES = {"parent_tsv", "home_scan_parent_tsv", "fen"}
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
COMPACT_PARENT_FIELDS = [
    "parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm",
    "pieces", "legal_moves", "phase", "source_row_index", "sample_hash",
]
CATALOG_PARENT_FIELDS = [
    "parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm",
    "pieces", "legal_moves", "phase", "partition", "source_identity",
    "source_bucket", "candidate_id", "source_path", "source_row_index", "sample_hash",
]
HOME_SCAN_FIELDS = [
    "parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm",
    "pieces", "legal_moves", "phase", "source_shard", "source_row_index",
    "selection_hash", "subset_hash", "in_deep512", "in_ultra256",
]
CATALOG_PARENT_SOURCE_IDS = {"00-dssd-a", "04-micro-m3", "06-q1"}


class ContractError(RuntimeError):
    """A fail-closed catalog, receipt, payload, or output contract violation."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rotate50(bitboard: int) -> int:
    if bitboard < 0 or bitboard >> 50:
        raise ContractError("bitboard outside 50 playable squares")
    result = 0
    while bitboard:
        bit = (bitboard & -bitboard).bit_length() - 1
        bitboard &= bitboard - 1
        result |= 1 << (49 - bit)
    return result


def parse_fingerprint(value: str) -> tuple[int, int, int, int, int]:
    parts = value.split(":")
    if len(parts) != 5:
        raise ContractError(f"bad parent fingerprint: {value!r}")
    try:
        wm, wk, bm, bk = (int(part, 16) for part in parts[:4])
        stm = int(parts[4])
    except ValueError as exc:
        raise ContractError(f"bad parent fingerprint: {value!r}") from exc
    if stm not in (0, 1):
        raise ContractError("parent fingerprint STM is not 0 or 1")
    boards = (wm, wk, bm, bk)
    if any(board < 0 or board >> 50 for board in boards):
        raise ContractError("parent fingerprint bitboard outside 50 squares")
    occupied = 0
    for board in boards:
        if occupied & board:
            raise ContractError("parent fingerprint has overlapping pieces")
        occupied |= board
    return wm, wk, bm, bk, stm


def format_fingerprint(wm: int, wk: int, bm: int, bk: int, stm: int) -> str:
    return f"{wm:013x}:{wk:013x}:{bm:013x}:{bk:013x}:{stm}"


def canonical_fingerprint(value: str) -> str:
    wm, wk, bm, bk, stm = parse_fingerprint(value)
    exact = format_fingerprint(wm, wk, bm, bk, stm)
    symmetric = format_fingerprint(
        rotate50(bm), rotate50(bk), rotate50(wm), rotate50(wk), 1 - stm
    )
    return min(exact, symmetric)


def verify_reference_canonicalization(sample_count: int = 256) -> int:
    """Prove the local port against the pinned repository helper on valid boards."""
    if sample_count <= 0:
        raise ContractError("canonicalization reference sample must be non-empty")
    for sample in range(sample_count):
        digest = hashlib.sha512(f"PR771-B2-canonical-port:{sample}".encode("ascii")).digest()
        boards = [0, 0, 0, 0]
        for square in range(50):
            owner = digest[square] % 5
            if owner:
                boards[owner - 1] |= 1 << square
        value = format_fingerprint(*boards, sample & 1)
        local = canonical_fingerprint(value)
        reference = reference_canonical_fingerprint(value)
        if local != reference:
            raise ContractError(f"canonicalization port mismatch at sample {sample}")
        wm, wk, bm, bk, stm = parse_fingerprint(value)
        symmetric = format_fingerprint(
            rotate50(bm), rotate50(bk), rotate50(wm), rotate50(wk), 1 - stm
        )
        if canonical_fingerprint(symmetric) != local:
            raise ContractError(f"canonicalization rotation mismatch at sample {sample}")
    return sample_count


def _fen_side(chunk: str, expected_colour: str) -> tuple[int, int]:
    if not chunk or chunk[0] != expected_colour:
        raise ContractError(f"FEN must contain one {expected_colour} piece field")
    men = 0
    kings = 0
    body = chunk[1:]
    if not body:
        return men, kings
    for raw_token in body.split(","):
        token = raw_token.strip()
        if not token:
            raise ContractError("FEN contains an empty square token")
        is_king = token.startswith("K")
        if is_king:
            token = token[1:]
        if not token or "K" in token:
            raise ContractError(f"bad FEN square token: {raw_token!r}")
        pieces = token.split("-")
        if len(pieces) > 2:
            raise ContractError(f"bad FEN range: {raw_token!r}")
        try:
            bounds = [int(part) for part in pieces]
        except ValueError as exc:
            raise ContractError(f"bad FEN square token: {raw_token!r}") from exc
        lo, hi = bounds[0], bounds[-1]
        if not (1 <= lo <= hi <= 50):
            raise ContractError(f"FEN square/range outside 1..50: {raw_token!r}")
        target = kings if is_king else men
        for square in range(lo, hi + 1):
            bit = 1 << (square - 1)
            if (men | kings) & bit:
                raise ContractError(f"duplicate FEN square {square}")
            target |= bit
        if is_king:
            kings = target
        else:
            men = target
    return men, kings


def canonical_fen(fen: str) -> str:
    parts = [part.strip() for part in fen.split(":")]
    if len(parts) != 3 or parts[0] not in ("W", "B"):
        raise ContractError(f"bad Jass FEN: {fen!r}")
    if {parts[1][:1], parts[2][:1]} != {"W", "B"}:
        raise ContractError("FEN must contain exactly one W and one B field")
    fields = {part[0]: part for part in parts[1:]}
    wm, wk = _fen_side(fields["W"], "W")
    bm, bk = _fen_side(fields["B"], "B")
    if (wm | wk) & (bm | bk):
        raise ContractError("FEN has a square occupied by both colours")
    stm = 0 if parts[0] == "W" else 1
    return canonical_fingerprint(format_fingerprint(wm, wk, bm, bk, stm))


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _safe_leaf(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or Path(value).name != value:
        raise ContractError(f"catalog {field} must be a non-empty basename")
    return value


def load_catalog(path: Path) -> tuple[dict, bytes]:
    try:
        raw = path.read_bytes()
        catalog = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read catalog {path}: {exc}") from exc
    if not isinstance(catalog, dict) or catalog.get("schema") != CATALOG_SCHEMA:
        raise ContractError("catalog schema mismatch")
    if catalog.get("universe") != "PR771_B2_V1_HISTORICAL_40":
        raise ContractError("catalog universe mismatch")
    if catalog.get("canonicalization") != CANONICALIZATION:
        raise ContractError("catalog canonicalization mismatch")
    sources = catalog.get("sources")
    if not isinstance(sources, list) or len(sources) != 40:
        raise ContractError("catalog must contain exactly 40 sources")
    seen: dict[str, set[str]] = {name: set() for name in ("source_id", "local_name", "receipt_name")}
    counts = {kind: 0 for kind in SOURCE_TYPES}
    expected_keys = {
        "ordinal", "source_id", "type", "job_id", "attempt_id", "code_sha",
        "prefix", "artifact_path", "local_name", "receipt_name",
    }
    for ordinal, source in enumerate(sources):
        if not isinstance(source, dict) or set(source) != expected_keys:
            raise ContractError(f"catalog source {ordinal} fields mismatch")
        if type(source["ordinal"]) is not int or source["ordinal"] != ordinal:
            raise ContractError(f"catalog source ordinal drift at {ordinal}")
        if source["type"] not in SOURCE_TYPES:
            raise ContractError(f"catalog source {ordinal} type mismatch")
        counts[source["type"]] += 1
        if not isinstance(source["source_id"], str) or not ID_RE.fullmatch(source["source_id"]):
            raise ContractError(f"catalog source {ordinal} has bad source_id")
        for field in ("source_id", "local_name", "receipt_name"):
            value = source[field] if field == "source_id" else _safe_leaf(source[field], field)
            if value in seen[field]:
                raise ContractError(f"duplicate catalog {field}: {value}")
            seen[field].add(value)
        job = source["job_id"]
        attempt = source["attempt_id"]
        if not isinstance(job, str) or not job or not isinstance(attempt, str) or not attempt:
            raise ContractError(f"catalog source {ordinal} missing job/attempt")
        expected_prefix = f"r2:jass-data/runs/{job}/{attempt}"
        if source["prefix"] != expected_prefix:
            raise ContractError(f"catalog source {ordinal} prefix mismatch")
        if not isinstance(source["code_sha"], str) or not GIT_SHA_RE.fullmatch(source["code_sha"]):
            raise ContractError(f"catalog source {ordinal} code SHA mismatch")
        artifact = source["artifact_path"]
        artifact_path = Path(artifact) if isinstance(artifact, str) else Path("/")
        if (not isinstance(artifact, str) or not artifact.startswith("artefacts/")
                or artifact_path.is_absolute() or ".." in artifact_path.parts):
            raise ContractError(f"catalog source {ordinal} artifact path unsafe")
        suffix = source["local_name"]
        if source["type"] == "fen" and not suffix.endswith(".fen"):
            raise ContractError(f"catalog FEN source {ordinal} local suffix mismatch")
        if source["type"] == "parent_tsv" and not suffix.endswith(".tsv.gz"):
            raise ContractError(f"catalog parent TSV source {ordinal} local suffix mismatch")
        if source["type"] == "home_scan_parent_tsv" and not suffix.endswith(".tsv"):
            raise ContractError(f"catalog HomeScan source {ordinal} local suffix mismatch")
    if counts != {"parent_tsv": 10, "home_scan_parent_tsv": 1, "fen": 29}:
        raise ContractError(f"catalog source type cardinality mismatch: {counts}")
    return catalog, raw


def _load_receipt(path: Path, source: dict, artifact: Path) -> dict:
    try:
        receipt_raw = path.read_bytes()
        receipt = json.loads(receipt_raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read receipt {path.name}: {exc}") from exc
    checks = {
        "schema": 1,
        "state": "verified",
        "prefix": source["prefix"],
        "job_id": source["job_id"],
        "attempt_id": source["attempt_id"],
        "code_sha": source["code_sha"],
        "result_state": "completed",
        "exit_code": 0,
    }
    if not isinstance(receipt, dict):
        raise ContractError(f"receipt {path.name} is not an object")
    for field, expected in checks.items():
        if type(receipt.get(field)) is not type(expected) or receipt.get(field) != expected:
            raise ContractError(f"receipt {path.name} {field} mismatch")
    files = receipt.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        raise ContractError(f"receipt {path.name} must authenticate exactly one file")
    item = files[0]
    if item.get("path") != source["artifact_path"] or item.get("local_name") != source["local_name"]:
        raise ContractError(f"receipt {path.name} selected file mismatch")
    size = item.get("size_bytes")
    digest = item.get("sha256")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ContractError(f"receipt {path.name} has invalid file size")
    if not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
        raise ContractError(f"receipt {path.name} has invalid file SHA")
    try:
        actual_size = artifact.stat().st_size
    except OSError as exc:
        raise ContractError(f"missing source artifact {artifact.name}") from exc
    if actual_size != size or sha256_file(artifact) != digest:
        raise ContractError(f"source artifact {artifact.name} differs from receipt")
    return {
        "receipt_sha256": sha256_bytes(receipt_raw),
        "artifact_sha256": digest,
        "artifact_size_bytes": size,
    }


def _open_tsv(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", newline="") \
        if path.name.endswith(".gz") else path.open("r", encoding="utf-8", newline="")


def load_parent_tsv(path: Path, *, expected_fields: list[str]) -> list[str]:
    identities: list[str] = []
    try:
        with _open_tsv(path) as stream:
            reader = csv.reader(stream, delimiter="\t")
            try:
                fields = next(reader)
            except StopIteration as exc:
                raise ContractError(f"empty parent TSV: {path.name}") from exc
            if len(fields) != len(set(fields)):
                raise ContractError(f"duplicate parent TSV field: {path.name}")
            if fields != expected_fields:
                raise ContractError(f"parent TSV field drift for {path.name}: {fields!r}")
            indexes = {field: fields.index(field) for field in (
                "parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm"
            )}
            expected_parent = 0
            for line_number, values in enumerate(reader, 2):
                if len(values) != len(fields):
                    raise ContractError(f"{path.name}:{line_number}: TSV width mismatch")
                try:
                    parent_id = int(values[indexes["parent_id"]])
                    parent_stm = int(values[indexes["parent_stm"]])
                except ValueError as exc:
                    raise ContractError(f"{path.name}:{line_number}: bad parent integer") from exc
                if parent_id != expected_parent:
                    raise ContractError(f"{path.name}:{line_number}: parent_id is not contiguous")
                expected_parent += 1
                raw = values[indexes["raw_fingerprint"]].strip()
                declared = values[indexes["canonical_fingerprint"]].strip()
                parsed = parse_fingerprint(raw)
                if format_fingerprint(*parsed) != raw:
                    raise ContractError(f"{path.name}:{line_number}: raw fingerprint is not normalized")
                canonical = canonical_fingerprint(raw)
                if declared != canonical:
                    raise ContractError(f"{path.name}:{line_number}: canonical fingerprint mismatch")
                if parent_stm != parsed[4]:
                    raise ContractError(f"{path.name}:{line_number}: parent_stm mismatch")
                identities.append(canonical)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ContractError(f"cannot parse parent TSV {path.name}: {exc}") from exc
    if not identities:
        raise ContractError(f"parent TSV is empty: {path.name}")
    if len(set(identities)) != len(identities):
        raise ContractError(f"parent TSV contains duplicate canonical parents: {path.name}")
    return identities


def load_fen(path: Path) -> list[str]:
    identities: list[str] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            for line_number, raw_line in enumerate(stream, 1):
                fen = raw_line.split("#", 1)[0].strip()
                if not fen:
                    continue
                try:
                    identities.append(canonical_fen(fen))
                except ContractError as exc:
                    raise ContractError(f"{path.name}:{line_number}: {exc}") from exc
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"cannot parse FEN source {path.name}: {exc}") from exc
    if not identities:
        raise ContractError(f"FEN source is empty: {path.name}")
    return identities


def _resolved(path: Path) -> Path:
    return path.resolve(strict=False)


def compile_exclusions(
    *, catalog_path: Path, input_dir: Path, receipt_dir: Path,
    out_union: Path, out_manifest: Path,
) -> dict:
    catalog, catalog_raw = load_catalog(catalog_path)
    reference_checks = verify_reference_canonicalization()
    union_tmp = out_union.with_name(out_union.name + ".tmp")
    manifest_tmp = out_manifest.with_name(out_manifest.name + ".tmp")
    output_paths = [out_union, out_manifest, union_tmp, manifest_tmp]
    resolved_outputs = [_resolved(path) for path in output_paths]
    if len(set(resolved_outputs)) != 4:
        raise ContractError("output and temporary paths must be pairwise distinct")
    source_paths = [catalog_path]
    for source in catalog["sources"]:
        source_paths.extend((
            input_dir / source["local_name"], receipt_dir / source["receipt_name"]
        ))
    resolved_sources = [_resolved(path) for path in source_paths]
    if len(set(resolved_sources)) != len(resolved_sources):
        raise ContractError("catalog, source artifacts, and receipts must be pairwise distinct")
    if set(resolved_outputs) & set(resolved_sources):
        raise ContractError("output/temporary path aliases a catalog, source, or receipt")
    if out_union.exists() or out_manifest.exists():
        raise ContractError("output path already exists")
    union: set[str] = set()
    source_reports = []
    total_rows = 0
    for source in catalog["sources"]:
        artifact = input_dir / source["local_name"]
        receipt_path = receipt_dir / source["receipt_name"]
        verified = _load_receipt(receipt_path, source, artifact)
        if source["type"] == "fen":
            identities = load_fen(artifact)
        else:
            if source["type"] == "home_scan_parent_tsv":
                expected_fields = HOME_SCAN_FIELDS
            elif source["source_id"] in CATALOG_PARENT_SOURCE_IDS:
                expected_fields = CATALOG_PARENT_FIELDS
            else:
                expected_fields = COMPACT_PARENT_FIELDS
            identities = load_parent_tsv(artifact, expected_fields=expected_fields)
        unique = set(identities)
        overlap = unique & union
        union.update(unique)
        total_rows += len(identities)
        source_reports.append({
            "ordinal": source["ordinal"],
            "source_id": source["source_id"],
            "type": source["type"],
            "job_id": source["job_id"],
            "attempt_id": source["attempt_id"],
            "code_sha": source["code_sha"],
            "prefix": source["prefix"],
            "artifact_path": source["artifact_path"],
            "local_name": source["local_name"],
            "receipt_name": source["receipt_name"],
            **verified,
            "rows": len(identities),
            "unique_canonical": len(unique),
            "duplicates_within_source": len(identities) - len(unique),
            "overlap_with_prior_sources": len(overlap),
            "cumulative_unique_canonical": len(union),
        })
    if not union:
        raise ContractError("historical exclusion union is empty")
    union_raw = "".join(f"{identity}\n" for identity in sorted(union)).encode("ascii")
    manifest = {
        "schema": OUTPUT_SCHEMA,
        "universe": catalog["universe"],
        "historical_authentication_only": True,
        "confirmation_freeze": False,
        "scores_or_labels_read": 0,
        "M1_alias_of_RichD_C": True,
        "m1_alias_attestation": {
            "alias_job_id": "cpx62-1591-l3-micro-search-budget-curve-m1-v1",
            "alias_attempt_id": "20260827T114726Z-f6f96f42",
            "source_id": "02-rich-d-c",
            "new_source_added": False,
        },
        "canonicalization": CANONICALIZATION,
        "canonicalization_reference": {
            "helper": "jobs.tools.tb_frontier_symmetry_dedup.canonical_fingerprint",
            "deterministic_valid_samples": reference_checks,
            "byte_equivalent": True,
        },
        "catalog_file_sha256": sha256_bytes(catalog_raw),
        "source_count": len(source_reports),
        "source_type_counts": {
            kind: sum(item["type"] == kind for item in source_reports)
            for kind in sorted(SOURCE_TYPES)
        },
        "input_rows": total_rows,
        "union_unique_canonical": len(union),
        "union_sha256": sha256_bytes(union_raw),
        "union_serialization": "lowercase normalized fingerprints, sorted bytewise, LF terminated",
        "sources": source_reports,
    }
    manifest_raw = canonical_json_bytes(manifest)
    out_union.parent.mkdir(parents=True, exist_ok=True)
    out_manifest.parent.mkdir(parents=True, exist_ok=True)
    if union_tmp.exists() or manifest_tmp.exists():
        raise ContractError("temporary output path already exists")
    try:
        union_tmp.write_bytes(union_raw)
        manifest_tmp.write_bytes(manifest_raw)
        os.replace(union_tmp, out_union)
        os.replace(manifest_tmp, out_manifest)
    except Exception:
        union_tmp.unlink(missing_ok=True)
        manifest_tmp.unlink(missing_ok=True)
        out_union.unlink(missing_ok=True)
        out_manifest.unlink(missing_ok=True)
        raise
    return manifest


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--out-union", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = compile_exclusions(
            catalog_path=args.catalog,
            input_dir=args.input_dir,
            receipt_dir=args.receipt_dir,
            out_union=args.out_union,
            out_manifest=args.out_manifest,
        )
        print(json.dumps({
            "source_count": manifest["source_count"],
            "union_unique_canonical": manifest["union_unique_canonical"],
            "union_sha256": manifest["union_sha256"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"adaptive_sibling_b2_exclusions: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
