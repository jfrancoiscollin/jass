#!/usr/bin/env python3
"""Offline, target-blind selector for the prospective PR771 B2 cohort contract.

The only position payload accepted here is the output of the board/STM-only
parent filter.  Raw generator JNNW files, labels, scores and WDL values are not
CLI inputs.  The source launcher is deliberately separate: this module merely
validates its declarative canonical manifest and checks the already-filtered
outputs against the descriptors carried by that manifest.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.adaptive_sibling_b2_exclusions import (  # noqa: E402
    ContractError,
    canonical_fingerprint,
    canonical_json_bytes,
    format_fingerprint,
    parse_fingerprint,
    sha256_bytes,
    sha256_file,
)


CONTRACT_SCHEMA = "jass.adaptive_sibling_b2_selection_contract.v1"
SOURCE_MANIFEST_SCHEMA = "jass.adaptive_sibling_b2_source_preparation.v1"
SELECTION_REPORT_SCHEMA = "jass.adaptive_sibling_b2_target_blind_selection.v1"
EXCLUSION_MANIFEST_SCHEMA = "jass.adaptive_sibling_b2_historical_exclusion_manifest.v1"
EXPECTED_CONTRACT_SHA256 = "5e94e0b8a71089d01959212debcfe0b90700714d96693097b519090462fe0e66"
JNNW_RECORD_SIZE = 38
SOURCE_SHARDS = 16
RAW_RECORDS_PER_SHARD = 10_000
SELECTION_SEED = 2_026_110_716
SOURCE_SEED_BASE = 2_026_110_700
CELL_QUOTA = 500
OUTPUT_RECORDS = 4_000
UINT32_MAX = (1 << 32) - 1
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
UINT_TEXT_RE = re.compile(r"0|[1-9][0-9]*\Z")

FILTER_FIELDS = [
    "row_index", "source_row_index", "parent_fingerprint", "parent_stm",
    "pieces", "legal_moves",
]
OUTPUT_FIELDS = [
    "parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm",
    "pieces", "legal_moves", "phase", "source_shard", "source_row_index",
    "selection_hash",
]
PHASES = {"P0": (30, 40), "P1": (20, 29), "P2": (12, 19), "P3": (9, 11)}
CELL_ORDER = [f"{phase}_stm{stm}" for phase in PHASES for stm in (0, 1)]
REQUIRED_ABSENT_ENV = [
    "JASS_DENSE_REMAP", "JASS_DSSD_MOVE_ORDER_POLICY", "JASS_EGDB_CACHE_MB",
    "JASS_EGDB_MTC_PATH", "JASS_EGDB_PATH", "JASS_NO_SCAN_ACC",
    "JASS_SEARCH_PARAMS", "JASS_T3_F6_MODEL", "JASS_TB_MOVE_ORDER_POLICY",
    "JASS_TRACE_ROOT",
]
FILTER_REPORT_KEYS = {
    "schema", "input", "labels_used_from_sources", "source_score_bytes_read",
    "source_wdl_bytes_read", "min_pieces", "max_pieces",
    "min_semantic_legal_moves", "max_semantic_legal_moves", "source_rows",
    "invalid_rows", "piece_eligible_rows", "exact_duplicates",
    "below_min_moves", "above_max_moves", "duplicate_move_entries",
    "selected_parents",
}


@dataclass(frozen=True)
class Candidate:
    canonical: str
    raw_fingerprint: str
    record: bytes
    stm: int
    pieces: int
    legal_moves: int
    phase: str
    source_shard: int
    source_row_index: int
    selection_hash: str

    @property
    def representative_key(self) -> tuple[str, int, int]:
        return self.raw_fingerprint, self.source_shard, self.source_row_index

    @property
    def sort_key(self) -> tuple[bytes, str]:
        return bytes.fromhex(self.selection_hash), self.canonical


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContractError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant: {value}")


def _read_json(path: Path, *, canonical: bool = False) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_json_constant
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"JSON root is not an object: {path}")
    if canonical and raw != canonical_json_bytes(value):
        raise ContractError(f"JSON is not canonical UTF-8/LF: {path}")
    return value, raw


def _expect_keys(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ContractError(f"{label} fields mismatch: {actual!r}")
    return value


def _strict_int(value: object, label: str, lo: int = 0, hi: int = UINT32_MAX) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise ContractError(f"{label} must be an integer in {lo}..{hi}")
    return value


def _strict_uint_text(value: str, label: str, hi: int = UINT32_MAX) -> int:
    if not UINT_TEXT_RE.fullmatch(value):
        raise ContractError(f"{label} is not a canonical unsigned integer")
    parsed = int(value)
    if parsed > hi:
        raise ContractError(f"{label} exceeds {hi}")
    return parsed


def _strict_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ContractError(f"{label} is not a lowercase SHA256")
    return value


def _strict_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ContractError(f"{label} must be a non-empty path string")
    return value


def _safe_leaf(value: object, label: str) -> str:
    path = _strict_path(value, label)
    if path in (".", "..") or "/" in path or "\\" in path or Path(path).name != path:
        raise ContractError(f"{label} must be a basename")
    return path


def _descriptor(value: object, label: str, *, allow_empty: bool = False) -> dict[str, Any]:
    item = _expect_keys(value, {"local_name", "sha256", "size_bytes"}, label)
    _safe_leaf(item["local_name"], f"{label}.local_name")
    _strict_sha(item["sha256"], f"{label}.sha256")
    _strict_int(item["size_bytes"], f"{label}.size_bytes", 0 if allow_empty else 1, (1 << 63) - 1)
    return item


def _sha_argv(argv: list[str]) -> str:
    return sha256_bytes(canonical_json_bytes(argv))


def load_contract(path: Path) -> tuple[dict[str, Any], bytes]:
    contract, raw = _read_json(path, canonical=True)
    if sha256_bytes(raw) != EXPECTED_CONTRACT_SHA256:
        raise ContractError("selection contract bytes differ from the reviewed v1 contract")
    if contract.get("schema") != CONTRACT_SCHEMA:
        raise ContractError("selection contract schema mismatch")
    # These comparisons turn accidental edits into a terminal failure rather than a new protocol.
    checks = {
        "cell_order": CELL_ORDER,
        "cell_quota": CELL_QUOTA,
        "phases": {key: list(value) for key, value in PHASES.items()},
        "top_up": False,
        "symmetry_dedup_before_cell_sampling": True,
    }
    for field, expected in checks.items():
        if contract.get(field) != expected:
            raise ContractError(f"selection contract {field} drift")
    hash_contract = contract.get("hash")
    if not isinstance(hash_contract, dict) or hash_contract.get("selection_seed") != SELECTION_SEED:
        raise ContractError("selection hash contract drift")
    golden = hash_contract.get("golden")
    if not isinstance(golden, dict) or selection_hash(golden.get("canonical_fingerprint", "")) != golden.get("digest"):
        raise ContractError("selection hash golden vector mismatch")
    if contract.get("producer", {}).get("source_manifest_schema") != SOURCE_MANIFEST_SCHEMA:
        raise ContractError("source manifest schema contract drift")
    if contract.get("selection_report_schema") != SELECTION_REPORT_SCHEMA:
        raise ContractError("selection report schema contract drift")
    return contract, raw


def selection_hash(canonical: str) -> str:
    return hashlib.sha256(f"{SELECTION_SEED}:{canonical}".encode("utf-8")).hexdigest()


def phase_for(pieces: int) -> str:
    for phase, (lo, hi) in PHASES.items():
        if lo <= pieces <= hi:
            return phase
    raise ContractError(f"piece count outside frozen phases: {pieces}")


def _validate_environment(value: object) -> dict[str, Any]:
    env = _expect_keys(
        value,
        {"egdb_source", "jass_prefixed_environment", "required_absent", "transmitted_names"},
        "source manifest producer_environment",
    )
    if env["egdb_source"] != "none":
        raise ContractError("producer environment EGDB source must be none")
    transmitted = env["transmitted_names"]
    if transmitted != []:
        raise ContractError("producer transmitted environment names must be empty")
    if env["jass_prefixed_environment"] != []:
        raise ContractError("producer jass_prefixed_environment must be empty")
    if env["required_absent"] != REQUIRED_ABSENT_ENV:
        raise ContractError("producer required-absent environment list drift")
    return env


def _validate_build(value: object) -> dict[str, Any]:
    build = _expect_keys(
        value,
        {"build_type", "cmake_cache_sha256", "cmake_options", "code_sha", "compiler_id", "compiler_version"},
        "source manifest build",
    )
    if not isinstance(build["code_sha"], str) or not GIT_SHA_RE.fullmatch(build["code_sha"]):
        raise ContractError("source manifest build.code_sha mismatch")
    _strict_sha(build["cmake_cache_sha256"], "source manifest build.cmake_cache_sha256")
    for field in ("build_type", "compiler_id", "compiler_version"):
        if not isinstance(build[field], str) or not build[field]:
            raise ContractError(f"source manifest build.{field} must be non-empty")
    options = build["cmake_options"]
    if (not isinstance(options, list) or any(not isinstance(option, str) or not option for option in options)
            or options != sorted(set(options))):
        raise ContractError("source manifest cmake_options must be sorted and unique")
    return build


def _validate_binary(value: object, label: str) -> dict[str, Any]:
    binary = _expect_keys(value, {"resolved_path", "sha256"}, label)
    _strict_path(binary["resolved_path"], f"{label}.resolved_path")
    _strict_sha(binary["sha256"], f"{label}.sha256")
    return binary


def validate_source_manifest(path: Path, contract: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    """Validate the source launcher's canonical, target-free receipt manifest."""
    manifest, raw = _read_json(path, canonical=True)
    _expect_keys(
        manifest,
        {"schema", "selection_contract_sha256", "build", "curriculum", "jass_executable",
         "parent_filter_executable", "producer_environment", "producer_barrier", "shards"},
        "source manifest",
    )
    if manifest["schema"] != SOURCE_MANIFEST_SCHEMA:
        raise ContractError("source manifest schema mismatch")
    if manifest["selection_contract_sha256"] != sha256_bytes(canonical_json_bytes(contract)):
        raise ContractError("source manifest selection contract SHA mismatch")
    _validate_build(manifest["build"])
    curriculum = _expect_keys(manifest["curriculum"], {"resolved_path", "sha256"}, "source manifest curriculum")
    _strict_path(curriculum["resolved_path"], "source manifest curriculum.resolved_path")
    if curriculum["sha256"] != contract["curriculum"]["decompressed_sha256"]:
        raise ContractError("source manifest CURRICULUM SHA mismatch")
    jass_binary = _validate_binary(manifest["jass_executable"], "source manifest jass_executable")
    filter_binary = _validate_binary(manifest["parent_filter_executable"], "source manifest parent_filter_executable")
    _validate_environment(manifest["producer_environment"])

    barrier = _expect_keys(
        manifest["producer_barrier"],
        {"alive_barrier_count", "child_count", "child_exec_preserves_pid", "distinct_identity",
         "direct_child_ppid_required", "launcher_pid", "non_zombie_required", "passed",
         "records_per_child", "seeds", "unique_pids_at_barrier"},
        "source manifest producer_barrier",
    )
    launcher_pid = _strict_int(barrier["launcher_pid"], "producer_barrier.launcher_pid", 1, (1 << 63) - 1)
    barrier_expected = {
        "alive_barrier_count": SOURCE_SHARDS,
        "child_count": SOURCE_SHARDS,
        "child_exec_preserves_pid": True,
        "distinct_identity": ["pid", "proc_starttime"],
        "direct_child_ppid_required": True,
        "non_zombie_required": True,
        "passed": True,
        "records_per_child": RAW_RECORDS_PER_SHARD,
        "seeds": "2026110700+source_shard",
        "unique_pids_at_barrier": True,
    }
    for field, expected in barrier_expected.items():
        if type(barrier[field]) is not type(expected) or barrier[field] != expected:
            raise ContractError(f"producer barrier {field} mismatch")

    shards = manifest["shards"]
    if not isinstance(shards, list) or len(shards) != SOURCE_SHARDS:
        raise ContractError("source manifest must contain exactly 16 shards")
    seen_pids: set[int] = set()
    seen_processes: set[tuple[int, int]] = set()
    seen_raw_hashes: set[str] = set()
    seen_names: set[str] = set()
    for expected_shard, shard_value in enumerate(shards):
        shard = _expect_keys(shard_value, {"source_shard", "seed", "producer", "filter"}, f"source shard {expected_shard}")
        if _strict_int(shard["source_shard"], "source_shard", 0, 15) != expected_shard:
            raise ContractError("source shards must be ordered and exhaustive 0..15")
        expected_seed = SOURCE_SEED_BASE + expected_shard
        if shard["seed"] != expected_seed or type(shard["seed"]) is not int:
            raise ContractError(f"source shard {expected_shard} seed mismatch")
        producer = _expect_keys(
            shard["producer"],
            {"argv", "argv_sha256", "duration_milliseconds", "exit_code", "launch_monotonic_ns",
             "log", "pid", "post_exec", "ppid", "proc_starttime", "process_state", "raw_jnnw"},
            f"source shard {expected_shard} producer",
        )
        argv = producer["argv"]
        if not isinstance(argv, list) or any(not isinstance(token, str) for token in argv):
            raise ContractError(f"source shard {expected_shard} argv must be a string array")
        raw_row = _expect_keys(
            producer["raw_jnnw"],
            {"header_count", "local_name", "magic", "record_size_bytes", "sha256", "size_bytes", "trailing_bytes"},
            f"source shard {expected_shard} raw_jnnw",
        )
        raw_name = _safe_leaf(raw_row["local_name"], "raw_jnnw.local_name")
        if raw_name != f"shard-{expected_shard:02d}.jnnw":
            raise ContractError(f"source shard {expected_shard} raw filename mismatch")
        raw_sha = _strict_sha(raw_row["sha256"], "raw_jnnw.sha256")
        if raw_sha in seen_raw_hashes:
            raise ContractError("duplicate raw source shard SHA")
        seen_raw_hashes.add(raw_sha)
        raw_expected = {
            "magic": "JNNW", "header_count": RAW_RECORDS_PER_SHARD,
            "record_size_bytes": JNNW_RECORD_SIZE,
            "size_bytes": 8 + JNNW_RECORD_SIZE * RAW_RECORDS_PER_SHARD,
            "trailing_bytes": 0,
        }
        for field, expected in raw_expected.items():
            if type(raw_row[field]) is not type(expected) or raw_row[field] != expected:
                raise ContractError(f"source shard {expected_shard} raw {field} mismatch")
        expected_argv = [
            jass_binary["resolved_path"], "--gen-data-wdl", "10000", raw_name,
            "4", "8", "260", str(expected_seed), "--nnue", curriculum["resolved_path"],
            "--wdl-zero-score", "--random-open-plies", "8", "--explore-eps", "8",
            "--explore-decay-plies", "60", "--pair-openings", "--drop-plycap",
        ]
        if argv != expected_argv or producer["argv_sha256"] != _sha_argv(argv):
            raise ContractError(f"source shard {expected_shard} producer argv mismatch")
        pid = _strict_int(producer["pid"], "producer.pid", 1, (1 << 63) - 1)
        starttime = _strict_int(producer["proc_starttime"], "producer.proc_starttime", 1, (1 << 63) - 1)
        if producer["ppid"] != launcher_pid or type(producer["ppid"]) is not int:
            raise ContractError(f"source shard {expected_shard} is not a direct launcher child")
        state = producer["process_state"]
        if not isinstance(state, str) or state not in {"R", "S", "D", "T", "t", "W", "K", "P", "I"}:
            raise ContractError(f"source shard {expected_shard} barrier state invalid")
        _strict_int(producer["launch_monotonic_ns"], "producer.launch_monotonic_ns", 1, (1 << 63) - 1)
        _strict_int(producer["duration_milliseconds"], "producer.duration_milliseconds", 0, (1 << 63) - 1)
        post_exec = _expect_keys(
            producer["post_exec"],
            {"argv_sha256", "executable_sha256", "resolved_executable", "verified"},
            f"source shard {expected_shard} post_exec",
        )
        if (
            post_exec["verified"] is not True
            or post_exec["resolved_executable"] != jass_binary["resolved_path"]
            or post_exec["executable_sha256"] != jass_binary["sha256"]
            or post_exec["argv_sha256"] != producer["argv_sha256"]
            or type(producer["exit_code"]) is not int
            or producer["exit_code"] != 0
        ):
            raise ContractError(f"source shard {expected_shard} producer did not verify/exit zero")
        if pid in seen_pids or (pid, starttime) in seen_processes:
            raise ContractError("producer PID or PID/starttime pair reused")
        seen_pids.add(pid)
        seen_processes.add((pid, starttime))
        log = _descriptor(producer["log"], f"source shard {expected_shard} log", allow_empty=True)
        if log["local_name"] in seen_names:
            raise ContractError("duplicate source manifest local filename")
        seen_names.add(log["local_name"])

        filt = _expect_keys(
            shard["filter"],
            {"argv", "argv_sha256", "duration_milliseconds", "exit_code", "filtered_jnnw",
             "filtered_meta", "report", "source_jnnw_sha256"},
            f"source shard {expected_shard} filter",
        )
        if filt["source_jnnw_sha256"] != raw_sha:
            raise ContractError(f"source shard {expected_shard} filter/raw SHA mismatch")
        descriptors = {
            name: _descriptor(filt[name], f"source shard {expected_shard} {name}")
            for name in ("filtered_jnnw", "filtered_meta", "report")
        }
        for item in descriptors.values():
            if item["local_name"] in seen_names:
                raise ContractError("duplicate source manifest local filename")
            seen_names.add(item["local_name"])
        filter_argv = filt["argv"]
        if not isinstance(filter_argv, list) or any(not isinstance(token, str) for token in filter_argv):
            raise ContractError(f"source shard {expected_shard} filter argv must be a string array")
        expected_filter_argv = [
            filter_binary["resolved_path"], raw_name,
            descriptors["filtered_jnnw"]["local_name"], descriptors["filtered_meta"]["local_name"],
            descriptors["report"]["local_name"], "9", "40", "2", "16",
        ]
        if filter_argv != expected_filter_argv or filt["argv_sha256"] != _sha_argv(filter_argv):
            raise ContractError(f"source shard {expected_shard} filter argv mismatch")
        _strict_int(filt["duration_milliseconds"], "filter.duration_milliseconds", 0, (1 << 63) - 1)
        if type(filt["exit_code"]) is not int or filt["exit_code"] != 0:
            raise ContractError(f"source shard {expected_shard} filter exit mismatch")
    return manifest, raw


def _match_inputs(paths: list[Path], shards: list[dict[str, Any]], descriptor_name: str) -> dict[int, Path]:
    if len(paths) != SOURCE_SHARDS:
        raise ContractError(f"--{descriptor_name.replace('_', '-')} requires exactly 16 paths")
    by_name: dict[str, Path] = {}
    for path in paths:
        if path.name in by_name:
            raise ContractError(f"duplicate CLI {descriptor_name} basename: {path.name}")
        by_name[path.name] = path
    mapped: dict[int, Path] = {}
    for shard in shards:
        index = shard["source_shard"]
        name = shard["filter"][descriptor_name]["local_name"]
        if name not in by_name:
            raise ContractError(f"missing CLI {descriptor_name} for shard {index}: {name}")
        mapped[index] = by_name.pop(name)
    if by_name:
        raise ContractError(f"unknown CLI {descriptor_name} files: {sorted(by_name)}")
    return mapped


def _verify_descriptor_file(path: Path, descriptor: dict[str, Any], label: str) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ContractError(f"missing {label}: {path}") from exc
    if size != descriptor["size_bytes"] or sha256_file(path) != descriptor["sha256"]:
        raise ContractError(f"{label} differs from source manifest: {path.name}")


def _load_filter_report(path: Path, raw_name: str, selected: int) -> dict[str, Any]:
    report, _ = _read_json(path)
    _expect_keys(report, FILTER_REPORT_KEYS, f"filter report {path.name}")
    expected = {
        "schema": "jass.deep_sibling.parent_filter.v1",
        "labels_used_from_sources": False,
        "source_score_bytes_read": False,
        "source_wdl_bytes_read": False,
        "min_pieces": 9,
        "max_pieces": 40,
        "min_semantic_legal_moves": 2,
        "max_semantic_legal_moves": 16,
        "source_rows": RAW_RECORDS_PER_SHARD,
        "invalid_rows": 0,
        "selected_parents": selected,
    }
    for field, value in expected.items():
        if type(report[field]) is not type(value) or report[field] != value:
            raise ContractError(f"filter report {path.name} {field} mismatch")
    if Path(_strict_path(report["input"], "filter report input")).name != raw_name:
        raise ContractError(f"filter report {path.name} raw input mismatch")
    counter_names = (
        "piece_eligible_rows", "exact_duplicates", "below_min_moves",
        "above_max_moves", "duplicate_move_entries",
    )
    for field in counter_names:
        _strict_int(report[field], f"filter report {field}", 0, RAW_RECORDS_PER_SHARD * 16)
    if report["piece_eligible_rows"] != (
        report["exact_duplicates"] + report["below_min_moves"]
        + report["above_max_moves"] + report["selected_parents"]
    ):
        raise ContractError(f"filter report {path.name} counters do not reconcile")
    if report["piece_eligible_rows"] > report["source_rows"]:
        raise ContractError(f"filter report {path.name} piece count exceeds source")
    return report


def _load_filtered_shard(jnnw: Path, meta: Path, source_shard: int) -> tuple[list[Candidate], int]:
    try:
        raw = jnnw.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read filtered JNNW {jnnw}") from exc
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ContractError(f"filtered JNNW has bad header: {jnnw.name}")
    declared = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + JNNW_RECORD_SIZE * declared:
        raise ContractError(f"filtered JNNW count/size mismatch: {jnnw.name}")
    try:
        meta_raw = meta.read_bytes()
        if not meta_raw.endswith(b"\n") or b"\r" in meta_raw:
            raise ContractError(f"filtered TSV is not LF terminated: {meta.name}")
        text = meta_raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"cannot read filtered TSV {meta}") from exc
    reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t")
    try:
        fields = next(reader)
    except StopIteration as exc:
        raise ContractError(f"empty filtered TSV: {meta.name}") from exc
    if fields != FILTER_FIELDS or len(fields) != len(set(fields)):
        raise ContractError(f"filtered TSV fields mismatch: {fields!r}")
    candidates: list[Candidate] = []
    seen_source_rows: set[int] = set()
    for row_index, values in enumerate(reader):
        if len(values) != len(FILTER_FIELDS):
            raise ContractError(f"{meta.name}:{row_index + 2}: TSV width mismatch")
        row = dict(zip(FILTER_FIELDS, values))
        if _strict_uint_text(row["row_index"], "row_index") != row_index:
            raise ContractError(f"{meta.name}:{row_index + 2}: compact row_index mismatch")
        source_row = _strict_uint_text(row["source_row_index"], "source_row_index")
        if source_row >= RAW_RECORDS_PER_SHARD:
            raise ContractError(f"{meta.name}:{row_index + 2}: source_row_index outside raw shard")
        if source_row in seen_source_rows:
            raise ContractError(f"{meta.name}:{row_index + 2}: duplicate source_row_index")
        seen_source_rows.add(source_row)
        record = raw[8 + row_index * JNNW_RECORD_SIZE:8 + (row_index + 1) * JNNW_RECORD_SIZE]
        if len(record) != JNNW_RECORD_SIZE:
            raise ContractError(f"filtered JNNW truncated at {row_index}")
        if record[33:38] != b"\0" * 5:
            raise ContractError(f"filtered JNNW contains a nonzero target at {row_index}")
        wm, wk, bm, bk, record_stm = struct.unpack_from("<QQQQB", record, 0)
        parsed_fp = format_fingerprint(wm, wk, bm, bk, record_stm)
        # parse_fingerprint also rejects overlap and bits outside the 50-square board.
        parse_fingerprint(parsed_fp)
        fingerprint = row["parent_fingerprint"]
        if fingerprint != parsed_fp or format_fingerprint(*parse_fingerprint(fingerprint)) != fingerprint:
            raise ContractError(f"{meta.name}:{row_index + 2}: board/fingerprint mismatch")
        stm = _strict_uint_text(row["parent_stm"], "parent_stm", 1)
        if stm != record_stm:
            raise ContractError(f"{meta.name}:{row_index + 2}: STM mismatch")
        pieces = _strict_uint_text(row["pieces"], "pieces", 40)
        if pieces != (wm | wk | bm | bk).bit_count():
            raise ContractError(f"{meta.name}:{row_index + 2}: piece count mismatch")
        legal_moves = _strict_uint_text(row["legal_moves"], "legal_moves", 16)
        if legal_moves < 2:
            raise ContractError(f"{meta.name}:{row_index + 2}: legal move count outside filter")
        canonical = canonical_fingerprint(fingerprint)
        candidates.append(Candidate(
            canonical=canonical,
            raw_fingerprint=fingerprint,
            record=record,
            stm=stm,
            pieces=pieces,
            legal_moves=legal_moves,
            phase=phase_for(pieces),
            source_shard=source_shard,
            source_row_index=source_row,
            selection_hash=selection_hash(canonical),
        ))
    if len(candidates) != declared:
        raise ContractError(f"filtered JNNW/TSV row count mismatch: {jnnw.name}")
    return candidates, declared


def _load_exclusion_manifest(path: Path, contract: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    expected = contract["exclusion"]
    manifest, raw = _read_json(path, canonical=True)
    if sha256_bytes(raw) != expected["manifest_sha256"]:
        raise ContractError("historical exclusion manifest SHA mismatch")
    checks = {
        "schema": EXCLUSION_MANIFEST_SCHEMA,
        "universe": expected["universe"],
        "source_count": 40,
        "union_unique_canonical": expected["union_unique_canonical"],
        "union_sha256": expected["union_sha256"],
        "canonicalization": contract["canonicalization"],
        "historical_authentication_only": True,
        "confirmation_freeze": False,
        "scores_or_labels_read": 0,
        "M1_alias_of_RichD_C": True,
    }
    for field, value in checks.items():
        if type(manifest.get(field)) is not type(value) or manifest.get(field) != value:
            raise ContractError(f"historical exclusion manifest {field} mismatch")
    return manifest, raw


def _load_exclusion_receipt(
    path: Path, union_path: Path, manifest_path: Path, contract: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    receipt, raw = _read_json(path)
    expected = contract["exclusion"]
    checks = {
        "schema": 1,
        "state": "verified",
        "prefix": expected["prefix"],
        "job_id": expected["job_id"],
        "attempt_id": expected["attempt_id"],
        "code_sha": expected["code_sha"],
        "result_state": "completed",
        "exit_code": 0,
    }
    for field, value in checks.items():
        if type(receipt.get(field)) is not type(value) or receipt.get(field) != value:
            raise ContractError(f"historical exclusion receipt {field} mismatch")
    files = receipt.get("files")
    if not isinstance(files, list) or len(files) != 2:
        raise ContractError("historical exclusion receipt must authenticate exactly two files")
    expected_files = {
        expected["union_artifact_path"]: (union_path, expected["union_sha256"]),
        expected["manifest_artifact_path"]: (manifest_path, expected["manifest_sha256"]),
    }
    seen: set[str] = set()
    for item in files:
        entry = _expect_keys(item, {"path", "local_name", "sha256", "size_bytes"}, "exclusion receipt file")
        artifact_path = entry["path"]
        if artifact_path not in expected_files or artifact_path in seen:
            raise ContractError("historical exclusion receipt file set mismatch")
        seen.add(artifact_path)
        local_path, expected_sha = expected_files[artifact_path]
        if entry["local_name"] != local_path.name or entry["sha256"] != expected_sha:
            raise ContractError("historical exclusion receipt filename/SHA mismatch")
        size = _strict_int(entry["size_bytes"], "exclusion receipt file size", 1, (1 << 63) - 1)
        if local_path.stat().st_size != size or sha256_file(local_path) != expected_sha:
            raise ContractError("historical exclusion file differs from receipt")
    if seen != set(expected_files):
        raise ContractError("historical exclusion receipt is incomplete")
    return receipt, raw


def _load_exclusion_union(path: Path, contract: dict[str, Any]) -> set[str]:
    expected = contract["exclusion"]
    if sha256_file(path) != expected["union_sha256"]:
        raise ContractError("historical exclusion union SHA mismatch")
    try:
        raw = path.read_bytes()
        if not raw.endswith(b"\n") or b"\r" in raw:
            raise ContractError("historical exclusion union is not canonical LF text")
        text = raw.decode("ascii")
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"cannot read historical exclusion union: {exc}") from exc
    lines = text.splitlines()
    if len(lines) != expected["union_unique_canonical"]:
        raise ContractError("historical exclusion union cardinality mismatch")
    previous = ""
    for line in lines:
        if not line or line <= previous or canonical_fingerprint(line) != line:
            raise ContractError("historical exclusion union is not sorted unique canonical ASCII")
        previous = line
    return set(lines)


def _path_key(path: Path) -> str:
    try:
        value = path.resolve(strict=False)
    except OSError:
        value = path.absolute()
    return str(value).replace("\\", "/").casefold()


def _guard_paths(inputs: list[Path], outputs: list[Path]) -> list[Path]:
    temps = [Path(str(path) + ".tmp") for path in outputs]
    all_paths = inputs + outputs + temps
    keys: dict[str, Path] = {}
    for path in all_paths:
        key = _path_key(path)
        if key in keys:
            raise ContractError(f"input/output/temp path alias: {keys[key]} and {path}")
        keys[key] = path
    for path in outputs + temps:
        if path.exists():
            raise ContractError(f"refusing existing output/temp path: {path}")
    return temps


def select_candidates(candidates: list[Candidate], excluded: set[str]) -> tuple[list[Candidate], dict[str, Any]]:
    representatives: dict[str, Candidate] = {}
    counters = {
        "filtered_occurrences": len(candidates),
        "historical_excluded_occurrences": 0,
        "exact_duplicate_occurrences_removed": 0,
        "symmetry_duplicate_occurrences_removed": 0,
    }
    for candidate in candidates:
        if candidate.canonical in excluded:
            counters["historical_excluded_occurrences"] += 1
            continue
        previous = representatives.get(candidate.canonical)
        if previous is None:
            representatives[candidate.canonical] = candidate
            continue
        if candidate.pieces != previous.pieces or candidate.legal_moves != previous.legal_moves:
            raise ContractError("canonical class disagrees on pieces or semantic legal moves")
        if candidate.raw_fingerprint == previous.raw_fingerprint:
            counters["exact_duplicate_occurrences_removed"] += 1
            if candidate.stm != previous.stm:
                raise ContractError("exact duplicate disagrees on STM")
        else:
            counters["symmetry_duplicate_occurrences_removed"] += 1
        if candidate.representative_key < previous.representative_key:
            representatives[candidate.canonical] = candidate

    by_cell: dict[str, list[Candidate]] = {cell: [] for cell in CELL_ORDER}
    for candidate in representatives.values():
        by_cell[f"{candidate.phase}_stm{candidate.stm}"].append(candidate)
    support = {cell: len(by_cell[cell]) for cell in CELL_ORDER}
    selected: list[Candidate] = []
    for cell in CELL_ORDER:
        ordered = sorted(by_cell[cell], key=lambda candidate: candidate.sort_key)
        if len(ordered) < CELL_QUOTA:
            raise ContractError(f"insufficient target-blind support in {cell}: {len(ordered)} < {CELL_QUOTA}")
        selected.extend(ordered[:CELL_QUOTA])
    selected.sort(key=lambda candidate: candidate.sort_key)
    if len(selected) != OUTPUT_RECORDS or len({candidate.canonical for candidate in selected}) != OUTPUT_RECORDS:
        raise ContractError("selected cohort cardinality/identity uniqueness mismatch")
    counters["unique_canonical_after_exclusion"] = len(representatives)
    return selected, {"counters": counters, "support_before_sampling": support}


def _write_jnnw(path: Path, selected: list[Candidate]) -> None:
    with path.open("wb") as stream:
        stream.write(b"JNNW" + struct.pack("<I", len(selected)))
        for candidate in selected:
            stream.write(candidate.record)


def _write_tsv(path: Path, selected: list[Candidate]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for parent_id, candidate in enumerate(selected):
            writer.writerow({
                "parent_id": parent_id,
                "canonical_fingerprint": candidate.canonical,
                "raw_fingerprint": candidate.raw_fingerprint,
                "parent_stm": candidate.stm,
                "pieces": candidate.pieces,
                "legal_moves": candidate.legal_moves,
                "phase": candidate.phase,
                "source_shard": candidate.source_shard,
                "source_row_index": candidate.source_row_index,
                "selection_hash": candidate.selection_hash,
            })


def _verify_outputs(jnnw: Path, tsv: Path, selected: list[Candidate]) -> bytes:
    raw = jnnw.read_bytes()
    expected_jnnw = b"JNNW" + struct.pack("<I", OUTPUT_RECORDS) + b"".join(c.record for c in selected)
    if raw != expected_jnnw or any(raw[8 + i * JNNW_RECORD_SIZE + 33:8 + (i + 1) * JNNW_RECORD_SIZE] != b"\0" * 5 for i in range(OUTPUT_RECORDS)):
        raise ContractError("JNNW output self-verification failed")
    tsv_raw = tsv.read_bytes()
    if not tsv_raw.endswith(b"\n") or b"\r" in tsv_raw:
        raise ContractError("TSV output serialization drift")
    reader = csv.DictReader(io.StringIO(tsv_raw.decode("utf-8"), newline=""), delimiter="\t")
    if reader.fieldnames != OUTPUT_FIELDS:
        raise ContractError("TSV output fields drift")
    rows = list(reader)
    if len(rows) != OUTPUT_RECORDS:
        raise ContractError("TSV output row count drift")
    for parent_id, (row, candidate) in enumerate(zip(rows, selected)):
        expected = {
            "parent_id": str(parent_id), "canonical_fingerprint": candidate.canonical,
            "raw_fingerprint": candidate.raw_fingerprint, "parent_stm": str(candidate.stm),
            "pieces": str(candidate.pieces), "legal_moves": str(candidate.legal_moves),
            "phase": candidate.phase, "source_shard": str(candidate.source_shard),
            "source_row_index": str(candidate.source_row_index),
            "selection_hash": candidate.selection_hash,
        }
        if row != expected:
            raise ContractError(f"TSV output self-verification failed at parent {parent_id}")
    identities = "".join(f"{candidate.canonical}\n" for candidate in selected).encode("ascii")
    return identities


def _build_report(
    contract: dict[str, Any],
    contract_raw: bytes,
    source_manifest: dict[str, Any],
    source_manifest_raw: bytes,
    exclusion_receipt_raw: bytes,
    exclusion_manifest_raw: bytes,
    union_path: Path,
    selected: list[Candidate],
    selection_receipt: dict[str, Any],
    filter_reports: list[dict[str, Any]],
    out_jnnw: Path,
    out_tsv: Path,
    identities: bytes,
) -> dict[str, Any]:
    selected_by_cell = {
        cell: sum(f"{candidate.phase}_stm{candidate.stm}" == cell for candidate in selected)
        for cell in CELL_ORDER
    }
    if selected_by_cell != {cell: CELL_QUOTA for cell in CELL_ORDER}:
        raise ContractError("selected cell counts drift")
    shards = []
    for source, filter_report in zip(source_manifest["shards"], filter_reports):
        shards.append({
            "source_shard": source["source_shard"],
            "seed": source["seed"],
            "producer_argv": source["producer"]["argv"],
            "producer_argv_sha256": source["producer"]["argv_sha256"],
            "raw_jnnw_sha256": source["producer"]["raw_jnnw"]["sha256"],
            "filter_argv": source["filter"]["argv"],
            "filter_argv_sha256": source["filter"]["argv_sha256"],
            "filtered_jnnw": source["filter"]["filtered_jnnw"],
            "filtered_meta": source["filter"]["filtered_meta"],
            "filter_report": source["filter"]["report"],
            "filter_counters": {field: filter_report[field] for field in (
                "source_rows", "invalid_rows", "piece_eligible_rows", "exact_duplicates",
                "below_min_moves", "above_max_moves", "duplicate_move_entries", "selected_parents",
            )},
        })
    return {
        "schema": SELECTION_REPORT_SCHEMA,
        "code_sha": source_manifest["build"]["code_sha"],
        "selection_contract_sha256": sha256_bytes(contract_raw),
        "source_manifest_sha256": sha256_bytes(source_manifest_raw),
        "curriculum_sha256": source_manifest["curriculum"]["sha256"],
        "exclusion": {
            "receipt_sha256": sha256_bytes(exclusion_receipt_raw),
            "manifest_sha256": sha256_bytes(exclusion_manifest_raw),
            "union_sha256": sha256_file(union_path),
            "union_unique_canonical": contract["exclusion"]["union_unique_canonical"],
        },
        "selection_seed": SELECTION_SEED,
        "selection_hash_algorithm": "sha256",
        "selection_hash_payload": "{selection_seed_decimal}:{canonical_fingerprint}",
        "canonicalization": "min(exact,rotate180_plus_colour_swap_and_invert_stm)",
        "representative_order": ["raw_fingerprint_ascii", "source_shard_uint", "source_row_index_uint"],
        "final_order": ["selection_hash_bytes", "canonical_fingerprint_ascii"],
        "cell_order": CELL_ORDER,
        "cell_quota": CELL_QUOTA,
        "top_up": False,
        "source_shards": shards,
        **selection_receipt,
        "selected_by_phase_stm": selected_by_cell,
        "selected": len(selected),
        "source_raw_records": SOURCE_SHARDS * RAW_RECORDS_PER_SHARD,
        "unique_selected_canonical": len({candidate.canonical for candidate in selected}),
        "forbidden_overlap": 0,
        "target_blind": True,
        "raw_source_jnnw_inputs": 0,
        "source_score_bytes_read": 0,
        "source_wdl_bytes_read": 0,
        "source_labels_read": 0,
        "output_target_nonzero_records": 0,
        "outputs": {
            "parents_jnnw": {"sha256": sha256_file(out_jnnw), "size_bytes": out_jnnw.stat().st_size, "records": OUTPUT_RECORDS},
            "parents_tsv": {"sha256": sha256_file(out_tsv), "size_bytes": out_tsv.stat().st_size, "rows": OUTPUT_RECORDS},
            "ordered_identities": {
                "sha256": sha256_bytes(identities), "size_bytes": len(identities), "rows": OUTPUT_RECORDS,
                "serialization": "canonical_fingerprint_ascii, one per line, LF terminated",
            },
        },
        "fits": 0,
        "training": False,
        "calibration": False,
        "tuning": False,
        "model_selection": False,
        "strength_games": 0,
        "promotion_authorized": False,
    }


def run(args: argparse.Namespace, *, contract_override: dict[str, Any] | None = None) -> dict[str, Any]:
    if contract_override is None:
        contract, contract_raw = load_contract(args.contract)
    else:
        contract = contract_override
        contract_raw = canonical_json_bytes(contract)
    source_manifest, source_raw = validate_source_manifest(args.source_manifest, contract)
    jnnw_by_shard = _match_inputs(args.filtered_jnnw, source_manifest["shards"], "filtered_jnnw")
    meta_by_shard = _match_inputs(args.filtered_meta, source_manifest["shards"], "filtered_meta")
    report_by_shard = _match_inputs(args.filter_report, source_manifest["shards"], "report")

    inputs = [args.contract, args.source_manifest, *args.filtered_jnnw, *args.filtered_meta,
              *args.filter_report, args.exclusion_union, args.exclusion_manifest, args.exclusion_receipt]
    outputs = [args.out_jnnw, args.out_tsv, args.report]
    temps = _guard_paths(inputs, outputs)
    _load_exclusion_manifest(args.exclusion_manifest, contract)
    _, exclusion_receipt_raw = _load_exclusion_receipt(
        args.exclusion_receipt, args.exclusion_union, args.exclusion_manifest, contract
    )
    excluded = _load_exclusion_union(args.exclusion_union, contract)

    all_candidates: list[Candidate] = []
    filter_reports: list[dict[str, Any]] = []
    for shard in source_manifest["shards"]:
        index = shard["source_shard"]
        filt = shard["filter"]
        _verify_descriptor_file(jnnw_by_shard[index], filt["filtered_jnnw"], "filtered JNNW")
        _verify_descriptor_file(meta_by_shard[index], filt["filtered_meta"], "filtered metadata")
        _verify_descriptor_file(report_by_shard[index], filt["report"], "filter report")
        candidates, declared = _load_filtered_shard(jnnw_by_shard[index], meta_by_shard[index], index)
        filter_report = _load_filter_report(
            report_by_shard[index], shard["producer"]["raw_jnnw"]["local_name"], declared
        )
        filter_reports.append(filter_report)
        all_candidates.extend(candidates)
    selected, selection_receipt = select_candidates(all_candidates, excluded)
    if any(candidate.canonical in excluded for candidate in selected):
        raise ContractError("historical exclusion overlap survived selection")

    for path in temps:
        path.parent.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    try:
        _write_jnnw(temps[0], selected)
        _write_tsv(temps[1], selected)
        identities = _verify_outputs(temps[0], temps[1], selected)
        _, exclusion_manifest_raw = _load_exclusion_manifest(args.exclusion_manifest, contract)
        report = _build_report(
            contract, contract_raw, source_manifest, source_raw, exclusion_receipt_raw, exclusion_manifest_raw,
            args.exclusion_union, selected, selection_receipt, filter_reports, temps[0], temps[1], identities,
        )
        temps[2].write_bytes(canonical_json_bytes(report))
        reread, report_raw = _read_json(temps[2], canonical=True)
        if reread != report:
            raise ContractError("selection report self-verification failed")
        for temp, final in zip(temps, outputs):
            os.replace(temp, final)
            published.append(final)
        result = {
            "schema": SELECTION_REPORT_SCHEMA,
            "selected": OUTPUT_RECORDS,
            "report_sha256": sha256_bytes(report_raw),
            "parents_jnnw_sha256": report["outputs"]["parents_jnnw"]["sha256"],
            "parents_tsv_sha256": report["outputs"]["parents_tsv"]["sha256"],
            "ordered_identities_sha256": report["outputs"]["ordered_identities"]["sha256"],
        }
        return result
    except Exception:
        for path in temps:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        for path in published:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--filtered-jnnw", type=Path, nargs="+", required=True)
    parser.add_argument("--filtered-meta", type=Path, nargs="+", required=True)
    parser.add_argument("--filter-report", type=Path, nargs="+", required=True)
    parser.add_argument("--exclusion-union", type=Path, required=True)
    parser.add_argument("--exclusion-manifest", type=Path, required=True)
    parser.add_argument("--exclusion-receipt", type=Path, required=True)
    parser.add_argument("--out-jnnw", type=Path, required=True)
    parser.add_argument("--out-tsv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(parse_args(argv))
    except (ContractError, OSError, UnicodeError, csv.Error, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
