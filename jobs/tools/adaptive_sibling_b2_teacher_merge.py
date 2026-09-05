#!/usr/bin/env python3
"""Strict physical merger for the prospective PR771 B2 teacher artifacts.

This tool authenticates a sealed 16-shard teacher run, preserves all historical
teacher values, derives a structural action ledger, and requires the native
move-generator verifier before atomically publishing any output.  It performs
no selection, scoring, fitting, gating, or search.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b2_select as selector  # noqa: E402
from jobs.tools import adaptive_sibling_b2_teacher_source as teacher  # noqa: E402
from jobs.tools.adaptive_sibling_b2_exclusions import (  # noqa: E402
    canonical_fingerprint,
    format_fingerprint,
    parse_fingerprint,
)


INPUT_SCHEMA = "jass.adaptive_sibling_b2_teacher_merge_inputs.v1"
REPORT_SCHEMA = "jass.adaptive_sibling_b2_teacher_merge.v1"
SEMANTIC_SCHEMA = "jass.adaptive_sibling_b2_semantic_action.v1"
NATIVE_SCHEMA = "jass.adaptive_sibling_b2_teacher_merge_native_verification.v1"
PARENTS = 4_000
SHARDS = 16
RECORD_SIZE = 38
MIN_ACTIONS = 8_000
MAX_ACTIONS = 64_000
UINT32_MAX = (1 << 32) - 1
UINT64_MAX = (1 << 64) - 1
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
PLAYABLE = (1 << 50) - 1
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
GIT_RE = re.compile(r"[0-9a-f]{40}\Z")
UINT_RE = re.compile(r"0|[1-9][0-9]*\Z")
INT_RE = re.compile(r"0|-?[1-9][0-9]*\Z")

GROUP_FIELDS = [
    "row_index", "parent_id", "parent_fingerprint", "parent_stm", "parent_pieces",
    "from", "to", "num_captures", "promotes", "moving_king", "captured_kings",
    "material_count_delta_parent", "child_pieces", "child_legal_moves",
    "child_forced_capture", "child_rule_terminal", "child_tb_exact",
    "exact_parent_utility", "t_baseline_parent", "q5k_parent", "q50_parent",
    "q200_parent", "nodes5k", "nodes50k", "nodes200k", "completed_depth5k",
    "completed_depth50k", "completed_depth200k", "effective_depth5k",
    "effective_depth50k", "effective_depth200k", "aborted5k", "aborted50k",
    "aborted200k", "stop5k", "stop50k", "stop200k", "elapsed_us5k",
    "elapsed_us50k", "elapsed_us200k", "pv5k_enters_egdb",
    "pv50k_enters_egdb", "pv200k_enters_egdb",
]
BOOL_FIELDS = {
    "promotes", "moving_king", "child_forced_capture", "child_rule_terminal",
    "child_tb_exact", "aborted5k", "aborted50k", "aborted200k",
    "pv5k_enters_egdb", "pv50k_enters_egdb", "pv200k_enters_egdb",
}
UINT64_FIELDS = {
    "nodes5k", "nodes50k", "nodes200k", "elapsed_us5k", "elapsed_us50k",
    "elapsed_us200k",
}
SCORE_FIELDS = {"t_baseline_parent", "q5k_parent", "q50_parent", "q200_parent"}
DEPTH_FIELDS = {
    "completed_depth5k", "completed_depth50k", "completed_depth200k",
    "effective_depth5k", "effective_depth50k", "effective_depth200k",
}
STOP_FIELDS = {"stop5k", "stop50k", "stop200k"}
STOP_VALUES = {"none", "nodes", "time", "external"}
SELECTION_REPORT_KEYS = {
    "schema", "code_sha", "selection_contract_sha256", "source_manifest_sha256",
    "curriculum_sha256", "exclusion", "selection_seed", "selection_hash_algorithm",
    "selection_hash_payload", "canonicalization", "representative_order", "final_order",
    "cell_order", "cell_quota", "top_up", "source_shards", "counters",
    "support_before_sampling", "selected_by_phase_stm", "selected", "source_raw_records",
    "unique_selected_canonical", "forbidden_overlap", "target_blind",
    "raw_source_jnnw_inputs", "source_score_bytes_read", "source_wdl_bytes_read",
    "source_labels_read", "output_target_nonzero_records", "outputs", "fits",
    "training", "calibration", "tuning", "model_selection", "strength_games",
    "promotion_authorized",
}


class MergeError(RuntimeError):
    """An input, structural, native-verification, or publication violation."""


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


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MergeError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise MergeError(f"non-finite JSON constant: {value}")


def read_json(path: Path, *, canonical: bool) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MergeError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MergeError(f"JSON root is not an object: {path}")
    if canonical and raw != canonical_json_bytes(value):
        raise MergeError(f"JSON is not canonical ASCII/LF: {path}")
    return value, raw


def expect_keys(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise MergeError(f"{label} fields mismatch: {actual!r}")
    return value


def strict_int(value: object, label: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise MergeError(f"{label} must be an integer in {lo}..{hi}")
    return value


def strict_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise MergeError(f"{label} must be lowercase SHA256")
    return value


def safe_leaf(value: object, label: str) -> str:
    if (not isinstance(value, str) or not value or "\0" in value or value in (".", "..")
            or "/" in value or "\\" in value or Path(value).name != value):
        raise MergeError(f"{label} must be a safe basename")
    return value


def file_descriptor(value: object, label: str, *, kind: str = "file") -> dict[str, Any]:
    extra: set[str]
    if kind == "file":
        extra = set()
    elif kind == "jnnw":
        extra = {"records", "record_size_bytes"}
    elif kind == "lines":
        extra = {"rows"}
    elif kind == "semantic":
        extra = {"rows", "row_schema"}
    else:  # pragma: no cover - internal programming error
        raise AssertionError(kind)
    item = expect_keys(value, {"local_name", "sha256", "size_bytes", *extra}, label)
    safe_leaf(item["local_name"], f"{label}.local_name")
    strict_sha(item["sha256"], f"{label}.sha256")
    strict_int(item["size_bytes"], f"{label}.size_bytes", 1, (1 << 63) - 1)
    if kind == "jnnw":
        strict_int(item["records"], f"{label}.records", 0, UINT32_MAX)
        if item["record_size_bytes"] != RECORD_SIZE or type(item["record_size_bytes"]) is not int:
            raise MergeError(f"{label}.record_size_bytes must be 38")
    if kind in ("lines", "semantic"):
        strict_int(item["rows"], f"{label}.rows", 0, UINT32_MAX)
    if kind == "semantic" and item["row_schema"] != SEMANTIC_SCHEMA:
        raise MergeError(f"{label}.row_schema mismatch")
    return item


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.resolve(strict=False)))).casefold()


def _existing_file(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise MergeError(f"{label} must not be a symbolic link")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise MergeError(f"missing {label}: {path}") from exc
    if not resolved.is_file():
        raise MergeError(f"{label} is not a regular file: {path}")
    return resolved


def _same_file(left: Path, right: Path, label: str) -> None:
    try:
        same = os.path.samefile(left, right)
    except OSError as exc:
        raise MergeError(f"cannot compare {label} paths") from exc
    if not same:
        raise MergeError(f"{label} path differs from authenticated manifest")


def verify_descriptor(path: Path, descriptor: Mapping[str, Any], label: str) -> Path:
    resolved = _existing_file(path, label)
    if resolved.stat().st_size != descriptor["size_bytes"] or sha256_file(resolved) != descriptor["sha256"]:
        raise MergeError(f"{label} size/SHA mismatch")
    return resolved


def _manifest_file(base: Path, descriptor: Mapping[str, Any], label: str) -> Path:
    path = base / descriptor["local_name"]
    return verify_descriptor(path, descriptor, label)


def _check_distinct(paths: Sequence[tuple[Path, str]], *, allow_same: set[frozenset[str]] = set()) -> None:
    for index, (left, left_label) in enumerate(paths):
        for right, right_label in paths[index + 1:]:
            if frozenset((left_label, right_label)) in allow_same:
                continue
            if _path_key(left) == _path_key(right):
                raise MergeError(f"path alias: {left_label} and {right_label}")
            if left.exists() and right.exists():
                try:
                    if os.path.samefile(left, right):
                        raise MergeError(f"filesystem alias: {left_label} and {right_label}")
                except OSError as exc:
                    raise MergeError(f"cannot compare paths: {left_label}, {right_label}") from exc


def _refuse_existing_or_symlink(paths: Iterable[Path]) -> None:
    for path in paths:
        if path.exists() or path.is_symlink():
            raise MergeError(f"refusing existing output/temporary: {path}")


def parse_jnnw(path: Path, expected_records: int, label: str) -> tuple[bytes, list[tuple[int, int, int, int, int]]]:
    raw = path.read_bytes()
    if len(raw) != 8 + expected_records * RECORD_SIZE or raw[:4] != b"JNNW" \
            or struct.unpack_from("<I", raw, 4)[0] != expected_records:
        raise MergeError(f"{label} JNNW header/count/size/trailing mismatch")
    rows: list[tuple[int, int, int, int, int]] = []
    for index in range(expected_records):
        record = raw[8 + index * RECORD_SIZE:8 + (index + 1) * RECORD_SIZE]
        wm, wk, bm, bk, stm = struct.unpack_from("<QQQQB", record)
        occupied = wm | wk | bm | bk
        if stm not in (0, 1) or occupied & ~PLAYABLE or ((wm & wk) | (wm & bm) | (wm & bk) | (wk & bm) | (wk & bk) | (bm & bk)):
            raise MergeError(f"{label} invalid board at row {index}")
        if record[33:38] != b"\0" * 5:
            raise MergeError(f"{label} nonzero target at row {index}")
        rows.append((wm, wk, bm, bk, stm))
    return raw, rows


def _uint_text(value: str, label: str, hi: int = UINT32_MAX) -> int:
    if not UINT_RE.fullmatch(value):
        raise MergeError(f"{label} is not a canonical unsigned integer")
    parsed = int(value)
    if parsed > hi:
        raise MergeError(f"{label} exceeds {hi}")
    return parsed


def _int_text(value: str, label: str, lo: int = INT32_MIN, hi: int = INT32_MAX) -> int:
    if not INT_RE.fullmatch(value):
        raise MergeError(f"{label} is not a canonical integer")
    parsed = int(value)
    if not lo <= parsed <= hi:
        raise MergeError(f"{label} outside {lo}..{hi}")
    return parsed


def read_parents_tsv(path: Path, parent_rows: Sequence[tuple[int, int, int, int, int]]) -> tuple[list[dict[str, Any]], bytes]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise MergeError("parents TSV must be LF terminated without CR")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise MergeError("parents TSV must be ASCII") from exc
    if not lines or lines[0].split("\t") != selector.OUTPUT_FIELDS or len(lines) != PARENTS + 1:
        raise MergeError("parents TSV header/cardinality mismatch")
    result: list[dict[str, Any]] = []
    canonical_seen: set[str] = set()
    previous_order: tuple[bytes, str] | None = None
    for parent_id, line in enumerate(lines[1:]):
        values = line.split("\t")
        if len(values) != len(selector.OUTPUT_FIELDS):
            raise MergeError(f"parents TSV width mismatch at {parent_id}")
        text = dict(zip(selector.OUTPUT_FIELDS, values))
        if _uint_text(text["parent_id"], "parent_id") != parent_id:
            raise MergeError("parents TSV parent_id sequence mismatch")
        wm, wk, bm, bk, stm = parent_rows[parent_id]
        raw_fp = format_fingerprint(wm, wk, bm, bk, stm)
        if text["raw_fingerprint"] != raw_fp or format_fingerprint(*parse_fingerprint(raw_fp)) != raw_fp:
            raise MergeError(f"parent raw fingerprint mismatch at {parent_id}")
        canonical = canonical_fingerprint(raw_fp)
        if text["canonical_fingerprint"] != canonical or canonical in canonical_seen:
            raise MergeError(f"parent canonical fingerprint mismatch/duplicate at {parent_id}")
        canonical_seen.add(canonical)
        if _uint_text(text["parent_stm"], "parent_stm", 1) != stm:
            raise MergeError(f"parent STM mismatch at {parent_id}")
        pieces = occupied_count(parent_rows[parent_id])
        if _uint_text(text["pieces"], "pieces", 40) != pieces or pieces < 9:
            raise MergeError(f"parent piece count mismatch at {parent_id}")
        legal = _uint_text(text["legal_moves"], "legal_moves", 16)
        if legal < 2:
            raise MergeError(f"parent legal count outside 2..16 at {parent_id}")
        if text["phase"] != selector.phase_for(pieces):
            raise MergeError(f"parent phase mismatch at {parent_id}")
        source_shard = _uint_text(text["source_shard"], "source_shard", SHARDS - 1)
        source_row = _uint_text(text["source_row_index"], "source_row_index", selector.RAW_RECORDS_PER_SHARD - 1)
        if not SHA_RE.fullmatch(text["selection_hash"]) or text["selection_hash"] != selector.selection_hash(canonical):
            raise MergeError(f"parent selection hash mismatch at {parent_id}")
        order = (bytes.fromhex(text["selection_hash"]), canonical)
        if previous_order is not None and not previous_order < order:
            raise MergeError("parents TSV final selection order is not strict")
        previous_order = order
        result.append({**text, "parent_id_int": parent_id, "stm_int": stm, "pieces_int": pieces,
                       "legal_moves_int": legal, "source_shard_int": source_shard,
                       "source_row_index_int": source_row})
    return result, raw


def occupied_count(row: tuple[int, int, int, int, int]) -> int:
    return (row[0] | row[1] | row[2] | row[3]).bit_count()


def read_groups(path: Path, expected_rows: int, shard: int) -> tuple[list[dict[str, str]], bytes]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise MergeError(f"shard {shard} groups TSV serialization mismatch")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise MergeError(f"shard {shard} groups TSV must be ASCII") from exc
    if not lines or lines[0].split("\t") != GROUP_FIELDS or len(lines) != expected_rows + 1:
        raise MergeError(f"shard {shard} groups TSV header/cardinality mismatch")
    rows: list[dict[str, str]] = []
    for local, line in enumerate(lines[1:]):
        values = line.split("\t")
        if len(values) != len(GROUP_FIELDS):
            raise MergeError(f"shard {shard} groups width mismatch at {local}")
        row = dict(zip(GROUP_FIELDS, values))
        if _uint_text(row["row_index"], "row_index") != local:
            raise MergeError(f"shard {shard} local row_index mismatch")
        for field in BOOL_FIELDS:
            _uint_text(row[field], field, 1)
        for field in UINT64_FIELDS:
            _uint_text(row[field], field, UINT64_MAX)
        for field in SCORE_FIELDS:
            _int_text(row[field], field)
        for field in DEPTH_FIELDS:
            _int_text(row[field], field, 0, INT32_MAX)
        for field in STOP_FIELDS:
            if row[field] not in STOP_VALUES:
                raise MergeError(f"unknown {field} value")
        _uint_text(row["parent_id"], "parent_id", PARENTS - 1)
        _uint_text(row["parent_stm"], "parent_stm", 1)
        _uint_text(row["parent_pieces"], "parent_pieces", 40)
        _uint_text(row["from"], "from", 50)
        _uint_text(row["to"], "to", 50)
        _uint_text(row["num_captures"], "num_captures", 20)
        _uint_text(row["captured_kings"], "captured_kings", 20)
        _int_text(row["material_count_delta_parent"], "material_count_delta_parent", -40, 40)
        _uint_text(row["child_pieces"], "child_pieces", 40)
        _uint_text(row["child_legal_moves"], "child_legal_moves", UINT32_MAX)
        utility = _int_text(row["exact_parent_utility"], "exact_parent_utility", -1, 2)
        if utility not in (-1, 0, 1, 2):
            raise MergeError("exact_parent_utility outside {-1,0,1,2}")
        exact = _uint_text(row["child_rule_terminal"], "child_rule_terminal", 1) \
            + _uint_text(row["child_tb_exact"], "child_tb_exact", 1)
        if exact > 1 or (exact == 0) != (utility == 2):
            raise MergeError("exact flags and exact_parent_utility disagree")
        if _uint_text(row["captured_kings"], "captured_kings", 20) > _uint_text(row["num_captures"], "num_captures", 20):
            raise MergeError("captured_kings exceeds num_captures")
        for field, budget in (("nodes5k", 5_000), ("nodes50k", 50_000), ("nodes200k", 200_000)):
            if _uint_text(row[field], field, UINT64_MAX) > budget:
                raise MergeError(f"{field} exceeds exact-node budget")
        if _uint_text(row["from"], "from", 50) < 1 or _uint_text(row["to"], "to", 50) < 1:
            raise MergeError("move square outside 1..50")
        rows.append(row)
    return rows, raw


def structural_action(parent: tuple[int, int, int, int, int], child: tuple[int, int, int, int, int],
                      group: Mapping[str, str], parent_meta: Mapping[str, Any], shard: int,
                      local_index: int, global_index: int) -> dict[str, Any]:
    wm, wk, bm, bk, stm = parent
    cwm, cwk, cbm, cbk, cstm = child
    if cstm != 1 - stm:
        raise MergeError("child STM does not invert parent STM")
    parent_own_m, parent_own_k = (wm, wk) if stm == 0 else (bm, bk)
    parent_opp_m, parent_opp_k = (bm, bk) if stm == 0 else (wm, wk)
    child_own_m, child_own_k = (cwm, cwk) if stm == 0 else (cbm, cbk)
    child_opp_m, child_opp_k = (cbm, cbk) if stm == 0 else (cwm, cwk)
    if child_opp_m & ~parent_opp_m or child_opp_k & ~parent_opp_k:
        raise MergeError("opponent piece added or changed type")
    captured_m = parent_opp_m & ~child_opp_m
    captured_k = parent_opp_k & ~child_opp_k
    captured = captured_m | captured_k
    if child_opp_m != (parent_opp_m & ~captured) or child_opp_k != (parent_opp_k & ~captured):
        raise MergeError("opponent transition mismatch")
    from_sq = _uint_text(group["from"], "from", 50)
    to_sq = _uint_text(group["to"], "to", 50)
    if from_sq < 1 or to_sq < 1:
        raise MergeError("move square outside 1..50")
    from_bit, to_bit = 1 << (from_sq - 1), 1 << (to_sq - 1)
    if from_sq != to_sq and to_bit & (wm | wk | bm | bk):
        raise MergeError("move destination is occupied in parent")
    moving_king = bool(_uint_text(group["moving_king"], "moving_king", 1))
    promotes = bool(_uint_text(group["promotes"], "promotes", 1))
    if moving_king != bool(parent_own_k & from_bit) or (not moving_king and not (parent_own_m & from_bit)):
        raise MergeError("moving piece/type does not match parent")
    expected_m = parent_own_m & ~from_bit
    expected_k = parent_own_k & ~from_bit
    if moving_king or promotes:
        expected_k |= to_bit
    else:
        expected_m |= to_bit
    if child_own_m != expected_m or child_own_k != expected_k:
        raise MergeError("moving side transition does not match from/to/promotion")
    if moving_king and promotes:
        raise MergeError("king move cannot be marked as promotion")
    num_captures = _uint_text(group["num_captures"], "num_captures", 20)
    captured_kings = _uint_text(group["captured_kings"], "captured_kings", 20)
    if captured.bit_count() != num_captures or captured_k.bit_count() != captured_kings:
        raise MergeError("capture bitboard/count mismatch")
    parent_pieces = occupied_count(parent)
    child_pieces = occupied_count(child)
    material_delta = (child_own_m | child_own_k).bit_count() - (child_opp_m | child_opp_k).bit_count() \
        - ((parent_own_m | parent_own_k).bit_count() - (parent_opp_m | parent_opp_k).bit_count())
    if (_uint_text(group["parent_pieces"], "parent_pieces", 40) != parent_pieces
            or _uint_text(group["child_pieces"], "child_pieces", 40) != child_pieces
            or _int_text(group["material_count_delta_parent"], "material_count_delta_parent", -40, 40) != material_delta):
        raise MergeError("piece/material counters differ from parent/child boards")
    if child_pieces < 1:
        raise MergeError("child piece count outside 1..40")
    if (group["parent_fingerprint"] != parent_meta["raw_fingerprint"]
            or group["parent_fingerprint"] != format_fingerprint(*parent)):
        raise MergeError("groups parent fingerprint mismatch")
    return {
        "captured_kings": captured_kings,
        "captured_square_bitboard": captured,
        "child_fingerprint": format_fingerprint(*child),
        "child_pieces": child_pieces,
        "from": from_sq,
        "global_row_index": global_index,
        "local_row_index": local_index,
        "material_count_delta_parent": material_delta,
        "num_captures": num_captures,
        "parent_fingerprint": group["parent_fingerprint"],
        "parent_id": parent_meta["parent_id_int"],
        "parent_legal_moves": parent_meta["legal_moves_int"],
        "parent_pieces": parent_pieces,
        "promotes": promotes,
        "schema": SEMANTIC_SCHEMA,
        "source_shard": shard,
        "to": to_sq,
    }


def _validate_selection_report(report: dict[str, Any], manifest: dict[str, Any],
                               contract: dict[str, Any], parent_jnnw: Mapping[str, Any],
                               parent_tsv: Mapping[str, Any], identities: Mapping[str, Any]) -> None:
    expect_keys(report, SELECTION_REPORT_KEYS, "selection report")
    constants = {
        "schema": selector.SELECTION_REPORT_SCHEMA, "code_sha": manifest["code_sha"],
        "selection_contract_sha256": manifest["selection"]["contract"]["sha256"],
        "curriculum_sha256": manifest["teacher_runtime"]["curriculum"]["sha256"],
        "selection_seed": selector.SELECTION_SEED, "selection_hash_algorithm": "sha256",
        "selection_hash_payload": "{selection_seed_decimal}:{canonical_fingerprint}",
        "canonicalization": "min(exact,rotate180_plus_colour_swap_and_invert_stm)",
        "representative_order": ["raw_fingerprint_ascii", "source_shard_uint", "source_row_index_uint"],
        "final_order": ["selection_hash_bytes", "canonical_fingerprint_ascii"],
        "cell_order": selector.CELL_ORDER, "cell_quota": selector.CELL_QUOTA,
        "top_up": False, "selected": PARENTS, "forbidden_overlap": 0,
        "target_blind": True, "raw_source_jnnw_inputs": 0, "source_score_bytes_read": 0,
        "source_wdl_bytes_read": 0, "source_labels_read": 0,
        "output_target_nonzero_records": 0, "fits": 0, "training": False,
        "calibration": False, "tuning": False, "model_selection": False,
        "strength_games": 0, "promotion_authorized": False,
    }
    for key, expected in constants.items():
        if report[key] != expected or type(report[key]) is not type(expected):
            raise MergeError(f"selection report {key} mismatch")
    if report["selected_by_phase_stm"] != {cell: 500 for cell in selector.CELL_ORDER}:
        raise MergeError("selection report cell counts mismatch")
    strict_sha(report["source_manifest_sha256"], "selection report source manifest SHA")
    exclusion = expect_keys(
        report["exclusion"],
        {"receipt_sha256", "manifest_sha256", "union_sha256", "union_unique_canonical"},
        "selection report exclusion",
    )
    for key in ("receipt_sha256", "manifest_sha256", "union_sha256"):
        strict_sha(exclusion[key], f"selection report exclusion {key}")
    contract_exclusion = contract["exclusion"]
    if (exclusion["manifest_sha256"] != contract_exclusion["manifest_sha256"]
            or exclusion["union_sha256"] != contract_exclusion["union_sha256"]):
        raise MergeError("selection report exclusion provenance differs from sealed contract")
    if strict_int(exclusion["union_unique_canonical"], "selection union count", 1, UINT32_MAX) \
            != contract_exclusion["union_unique_canonical"]:
        raise MergeError("selection report exclusion union count mismatch")
    if strict_int(report["source_raw_records"], "selection source raw records", 0, UINT32_MAX) \
            != SHARDS * selector.RAW_RECORDS_PER_SHARD:
        raise MergeError("selection report source raw record count mismatch")
    if strict_int(report["unique_selected_canonical"], "unique selected canonical", 0, UINT32_MAX) != PARENTS:
        raise MergeError("selection report unique selected count mismatch")
    counters = expect_keys(
        report["counters"],
        {"filtered_occurrences", "historical_excluded_occurrences",
         "exact_duplicate_occurrences_removed", "symmetry_duplicate_occurrences_removed",
         "unique_canonical_after_exclusion"},
        "selection report counters",
    )
    for key, value in counters.items():
        strict_int(value, f"selection counter {key}", 0, UINT32_MAX)
    support = expect_keys(report["support_before_sampling"], set(selector.CELL_ORDER), "selection support")
    for cell in selector.CELL_ORDER:
        strict_int(support[cell], f"selection support {cell}", 500, UINT32_MAX)
    source_shards = report["source_shards"]
    if not isinstance(source_shards, list) or len(source_shards) != SHARDS:
        raise MergeError("selection report source shard coverage mismatch")
    source_keys = {
        "source_shard", "seed", "producer_argv", "producer_argv_sha256",
        "raw_jnnw_sha256", "filter_argv", "filter_argv_sha256", "filtered_jnnw",
        "filtered_meta", "filter_report", "filter_counters",
    }
    filter_counter_keys = {
        "source_rows", "invalid_rows", "piece_eligible_rows", "exact_duplicates",
        "below_min_moves", "above_max_moves", "duplicate_move_entries", "selected_parents",
    }
    for shard, source in enumerate(source_shards):
        item = expect_keys(source, source_keys, f"selection source shard {shard}")
        if strict_int(item["source_shard"], "selection source shard", 0, SHARDS - 1) != shard \
                or strict_int(item["seed"], "selection source seed", 0, UINT32_MAX) \
                != selector.SOURCE_SEED_BASE + shard:
            raise MergeError("selection source shard identity mismatch")
        for key in ("producer_argv", "filter_argv"):
            if (not isinstance(item[key], list) or not item[key]
                    or any(not isinstance(token, str) or not token or "\0" in token for token in item[key])):
                raise MergeError(f"selection source shard {shard} {key} invalid")
        for key in ("producer_argv_sha256", "raw_jnnw_sha256", "filter_argv_sha256"):
            strict_sha(item[key], f"selection source shard {shard} {key}")
        for key in ("filtered_jnnw", "filtered_meta", "filter_report"):
            file_descriptor(item[key], f"selection source shard {shard} {key}")
        filter_counts = expect_keys(
            item["filter_counters"], filter_counter_keys,
            f"selection source shard {shard} filter counters",
        )
        for key, value in filter_counts.items():
            strict_int(value, f"selection source shard {shard} counter {key}", 0, UINT32_MAX)
        if filter_counts["source_rows"] != selector.RAW_RECORDS_PER_SHARD or filter_counts["invalid_rows"] != 0:
            raise MergeError(f"selection source shard {shard} source/invalid counters mismatch")
        if filter_counts["piece_eligible_rows"] != (
            filter_counts["exact_duplicates"] + filter_counts["below_min_moves"]
            + filter_counts["above_max_moves"] + filter_counts["selected_parents"]
        ):
            raise MergeError(f"selection source shard {shard} filter counters do not reconcile")
    if counters["filtered_occurrences"] != sum(
        source["filter_counters"]["selected_parents"] for source in source_shards
    ):
        raise MergeError("selection filtered occurrence count mismatch")
    if counters["unique_canonical_after_exclusion"] != sum(support.values()):
        raise MergeError("selection unique canonical/support count mismatch")
    if counters["filtered_occurrences"] != (
        counters["historical_excluded_occurrences"]
        + counters["exact_duplicate_occurrences_removed"]
        + counters["symmetry_duplicate_occurrences_removed"]
        + counters["unique_canonical_after_exclusion"]
    ):
        raise MergeError("selection deduplication counters do not reconcile")
    outputs = expect_keys(report["outputs"], {"parents_jnnw", "parents_tsv", "ordered_identities"}, "selection outputs")
    report_j = expect_keys(outputs["parents_jnnw"], {"sha256", "size_bytes", "records"}, "selection report parents_jnnw")
    strict_sha(report_j["sha256"], "selection report parents_jnnw SHA")
    strict_int(report_j["size_bytes"], "selection report parents_jnnw size", 1, (1 << 63) - 1)
    strict_int(report_j["records"], "selection report parents_jnnw records", PARENTS, PARENTS)
    report_t = expect_keys(outputs["parents_tsv"], {"sha256", "size_bytes", "rows"}, "selection report parents_tsv")
    strict_sha(report_t["sha256"], "selection report parents_tsv SHA")
    strict_int(report_t["size_bytes"], "selection report parents_tsv size", 1, (1 << 63) - 1)
    strict_int(report_t["rows"], "selection report parents_tsv rows", PARENTS, PARENTS)
    report_i = expect_keys(outputs["ordered_identities"], {"sha256", "size_bytes", "rows", "serialization"}, "selection report ordered identities")
    strict_sha(report_i["sha256"], "selection report ordered identities SHA")
    strict_int(report_i["size_bytes"], "selection report ordered identities size", 1, (1 << 63) - 1)
    strict_int(report_i["rows"], "selection report ordered identities rows", PARENTS, PARENTS)
    if report_i["serialization"] != "canonical_fingerprint_ascii, one per line, LF terminated":
        raise MergeError("selection report ordered identities serialization mismatch")
    expected_j = {key: parent_jnnw[key] for key in ("sha256", "size_bytes", "records")}
    expected_t = {key: parent_tsv[key] for key in ("sha256", "size_bytes", "rows")}
    if outputs["parents_jnnw"] != expected_j or outputs["parents_tsv"] != expected_t or outputs["ordered_identities"] != identities:
        raise MergeError("selection report output descriptors mismatch")


def _adapter_receipt(path: Path, manifest: dict[str, Any], base: Path, rendered: Path) -> dict[str, Any]:
    receipt, _ = read_json(path, canonical=False)
    expected_keys = {
        "schema", "base_source_path", "base_source_sha256", "base_source_normalized_sha256",
        "rendered_source_path", "rendered_source_sha256", "rendered_source_bytes", "budgets_nodes",
        "fresh_engine_each_search", "engine_constructions_per_sibling", "book_enabled",
        "threads_per_search", "node_limit_mode", "egdb_build_required",
        "egdb_configuration_source", "egdb_cache_mb", "jass_prefixed_environment",
        "engine_lifecycle_changed", "frozen_budgets_columns_and_score_semantics_changed",
    }
    expect_keys(receipt, expected_keys, "adapter receipt")
    expected = {
        "schema": teacher.ADAPTER_SCHEMA, "base_source_sha256": sha256_file(base),
        "base_source_normalized_sha256": teacher.BASE_SOURCE_NORMALIZED_SHA256,
        "rendered_source_sha256": sha256_file(rendered), "rendered_source_bytes": rendered.stat().st_size,
        "budgets_nodes": list(teacher.BUDGETS), "fresh_engine_each_search": True,
        "engine_constructions_per_sibling": 3, "book_enabled": False, "threads_per_search": 1,
        "node_limit_mode": "exact", "egdb_build_required": True,
        "egdb_configuration_source": "explicit_positional_arguments", "egdb_cache_mb": 256,
        "jass_prefixed_environment": [], "engine_lifecycle_changed": True,
        "frozen_budgets_columns_and_score_semantics_changed": False,
    }
    for key, value in expected.items():
        if receipt[key] != value or type(receipt[key]) is not type(value):
            raise MergeError(f"adapter receipt {key} mismatch")
    if (not isinstance(receipt["base_source_path"], str)
            or not isinstance(receipt["rendered_source_path"], str)
            or "\0" in receipt["base_source_path"] or "\0" in receipt["rendered_source_path"]
            or Path(receipt["base_source_path"]).name != base.name
            or Path(receipt["rendered_source_path"]).name != rendered.name):
        raise MergeError("adapter receipt source basenames mismatch")
    normalized = teacher._normalize_source(base.read_bytes())
    if sha256_bytes(normalized) != teacher.BASE_SOURCE_NORMALIZED_SHA256:
        raise MergeError("adapter base normalized SHA mismatch")
    expected_rendered = teacher.render(normalized.decode("utf-8")).encode("utf-8")
    if rendered.read_bytes() != expected_rendered:
        raise MergeError("rendered teacher source is not byte-reproducible")
    return receipt


def validate_manifest(manifest_path: Path, expected_sha: str) -> tuple[dict[str, Any], bytes, dict[str, Path]]:
    strict_sha(expected_sha, "expected input manifest SHA")
    manifest, raw = read_json(manifest_path, canonical=True)
    if sha256_bytes(raw) != expected_sha:
        raise MergeError("input manifest SHA mismatch")
    expect_keys(manifest, {"adapter", "build", "code_sha", "schema", "selection", "shards", "teacher_runtime"}, "input manifest")
    if manifest["schema"] != INPUT_SCHEMA or not isinstance(manifest["code_sha"], str) or not GIT_RE.fullmatch(manifest["code_sha"]):
        raise MergeError("input manifest schema/code SHA mismatch")
    selection = expect_keys(manifest["selection"], {"cell_order", "cell_quota", "contract", "forbidden_overlap", "ordered_identities", "parents_jnnw", "parents_tsv", "report", "report_schema", "selected", "target_blind"}, "manifest selection")
    if selection["cell_order"] != selector.CELL_ORDER or selection["target_blind"] is not True or selection["report_schema"] != selector.SELECTION_REPORT_SCHEMA:
        raise MergeError("manifest selection constants mismatch")
    strict_int(selection["cell_quota"], "manifest cell quota", 500, 500)
    strict_int(selection["forbidden_overlap"], "manifest forbidden overlap", 0, 0)
    strict_int(selection["selected"], "manifest selected", PARENTS, PARENTS)
    descriptors: list[tuple[str, dict[str, Any]]] = []
    for name in ("contract", "report"):
        descriptors.append((f"selection.{name}", file_descriptor(selection[name], f"selection.{name}")))
    pj = file_descriptor(selection["parents_jnnw"], "selection.parents_jnnw", kind="jnnw")
    pt = file_descriptor(selection["parents_tsv"], "selection.parents_tsv", kind="lines")
    oi = expect_keys(selection["ordered_identities"], {"sha256", "size_bytes", "rows", "serialization"}, "selection.ordered_identities")
    strict_sha(oi["sha256"], "ordered identities SHA")
    strict_int(oi["size_bytes"], "ordered identities size", 1, (1 << 63) - 1)
    strict_int(oi["rows"], "ordered identities rows", PARENTS, PARENTS)
    if oi["serialization"] != "canonical_fingerprint_ascii, one per line, LF terminated":
        raise MergeError("ordered identities serialization mismatch")
    if pj["records"] != PARENTS or pj["size_bytes"] != 8 + PARENTS * RECORD_SIZE or pt["rows"] != PARENTS:
        raise MergeError("manifest parent descriptors mismatch")
    descriptors += [("selection.parents_jnnw", pj), ("selection.parents_tsv", pt)]
    adapter = expect_keys(manifest["adapter"], {"base_source", "base_source_normalized_sha256", "receipt", "receipt_schema", "rendered_source", "tool"}, "manifest adapter")
    if adapter["base_source_normalized_sha256"] != teacher.BASE_SOURCE_NORMALIZED_SHA256 or adapter["receipt_schema"] != teacher.ADAPTER_SCHEMA:
        raise MergeError("manifest adapter constants mismatch")
    for name in ("base_source", "receipt", "rendered_source", "tool"):
        descriptors.append((f"adapter.{name}", file_descriptor(adapter[name], f"adapter.{name}")))
    if adapter["rendered_source"]["size_bytes"] != 23_035:
        raise MergeError("rendered teacher source size drift")
    build = expect_keys(manifest["build"], {"build_type", "cmake_cache", "cmake_options", "compiler_id", "compiler_version", "merge_tool", "teacher_executable", "verifier_executable", "verifier_source"}, "manifest build")
    if build["build_type"] != "Release" or not isinstance(build["compiler_id"], str) or not build["compiler_id"] or not isinstance(build["compiler_version"], str) or not build["compiler_version"]:
        raise MergeError("manifest build identity mismatch")
    if not isinstance(build["cmake_options"], list) or not build["cmake_options"] or any(not isinstance(x, str) or not x or "\0" in x for x in build["cmake_options"]) or len(set(build["cmake_options"])) != len(build["cmake_options"]):
        raise MergeError("manifest CMake options invalid")
    for name in ("cmake_cache", "merge_tool", "teacher_executable", "verifier_executable", "verifier_source"):
        descriptors.append((f"build.{name}", file_descriptor(build[name], f"build.{name}")))
    runtime = expect_keys(manifest["teacher_runtime"], {"curriculum", "egdb", "jass_prefixed_environment", "node_limit_mode", "threads_per_search", "tt_mb"}, "teacher runtime")
    if runtime["jass_prefixed_environment"] != [] or runtime["node_limit_mode"] != "exact":
        raise MergeError("teacher runtime constants mismatch")
    strict_int(runtime["threads_per_search"], "teacher threads per search", 1, 1)
    strict_int(runtime["tt_mb"], "teacher tt_mb", 1, UINT64_MAX)
    descriptors.append(("teacher_runtime.curriculum", file_descriptor(runtime["curriculum"], "teacher_runtime.curriculum")))
    egdb = expect_keys(runtime["egdb"], {"cache_mb", "directory_local_name", "identity_manifest", "max_pieces"}, "teacher runtime EGDB")
    strict_int(egdb["cache_mb"], "teacher EGDB cache", 256, 256)
    safe_leaf(egdb["directory_local_name"], "EGDB directory local name")
    strict_int(egdb["max_pieces"], "EGDB max pieces", 1, 40)
    descriptors.append(("teacher_runtime.egdb.identity_manifest", file_descriptor(egdb["identity_manifest"], "teacher_runtime.egdb.identity_manifest")))
    shards = manifest["shards"]
    if not isinstance(shards, list) or len(shards) != SHARDS:
        raise MergeError("manifest must contain exactly 16 shards")
    for index, item in enumerate(shards):
        shard = expect_keys(item, {"children_jnnw", "command_argv", "exit_code", "groups_tsv", "report_json", "report_schema", "shard", "state"}, f"shard {index}")
        if shard["shard"] != index or type(shard["shard"]) is not int or shard["state"] != "completed" or shard["exit_code"] != 0 or type(shard["exit_code"]) is not int or shard["report_schema"] != teacher.SHARD_SCHEMA:
            raise MergeError(f"manifest shard {index} constants mismatch")
        if not isinstance(shard["command_argv"], list) or len(shard["command_argv"]) != 11 or any(not isinstance(x, str) or not x or "\0" in x for x in shard["command_argv"]):
            raise MergeError(f"manifest shard {index} argv invalid")
        cj = file_descriptor(shard["children_jnnw"], f"shard {index} children", kind="jnnw")
        gt = file_descriptor(shard["groups_tsv"], f"shard {index} groups", kind="lines")
        rj = file_descriptor(shard["report_json"], f"shard {index} report")
        if not 500 <= cj["records"] <= 4_000 or gt["rows"] != cj["records"] or cj["size_bytes"] != 8 + cj["records"] * RECORD_SIZE:
            raise MergeError(f"manifest shard {index} cardinality mismatch")
        descriptors += [(f"shard.{index}.children", cj), (f"shard.{index}.groups", gt), (f"shard.{index}.report", rj)]
    base = manifest_path.parent
    if manifest_path.is_symlink():
        raise MergeError("input manifest must not be a symbolic link")
    names = [descriptor["local_name"] for _, descriptor in descriptors]
    if len({_path_key(base / name) for name in names}) != len(names):
        raise MergeError("manifest local_name values are not unique")
    resolved: dict[str, Path] = {}
    seen: list[tuple[Path, str]] = []
    for label, descriptor in descriptors:
        path = _manifest_file(base, descriptor, label)
        for previous, previous_label in seen:
            if os.path.samefile(path, previous):
                raise MergeError(f"manifest filesystem alias: {label} and {previous_label}")
        seen.append((path, label))
        resolved[label] = path
    return manifest, raw, resolved


def _resolve_argv_path(token: str, base: Path) -> Path:
    path = Path(token)
    return path if path.is_absolute() else base / path


def validate_shard_argv(item: Mapping[str, Any], manifest: Mapping[str, Any], files: Mapping[str, Path], base: Path) -> None:
    shard = item["shard"]
    argv = item["command_argv"]
    matches = [
        (0, files["build.teacher_executable"], "teacher executable"),
        (1, files["selection.parents_jnnw"], "parents JNNW"),
        (2, files[f"shard.{shard}.children"], "shard children"),
        (3, files[f"shard.{shard}.groups"], "shard groups"),
        (4, files[f"shard.{shard}.report"], "shard report"),
        (5, files["teacher_runtime.curriculum"], "CURRICULUM"),
    ]
    for position, expected, label in matches:
        actual = _existing_file(_resolve_argv_path(argv[position], base), f"argv {label}")
        _same_file(actual, expected, f"shard {shard} {label}")
    if Path(argv[6]).name != manifest["teacher_runtime"]["egdb"]["directory_local_name"]:
        raise MergeError(f"shard {shard} EGDB argv basename mismatch")
    expected_numbers = [str(shard), str(SHARDS), str(manifest["teacher_runtime"]["tt_mb"]), "256"]
    if argv[7:11] != expected_numbers:
        raise MergeError(f"shard {shard} numeric argv mismatch")


def validate_native_receipt(receipt: dict[str, Any], *, n: int, parents: Mapping[str, Any],
                            children_tmp: Path, semantic_tmp: Path, verifier: Path,
                            manifest: Mapping[str, Any]) -> None:
    keys = {"actions_verified", "build_provenance_declared", "catalogue_actions_generated", "catalogues_verified", "children", "duplicate_semantic_actions", "executable", "extra_actions", "forbidden_reordering", "identity_order", "identity_tuple", "missing_actions", "nonzero_child_targets", "nonzero_parent_targets", "parent_after_matches", "parent_count_matches", "parents", "parents_verified", "schema", "semantic_actions", "semantic_rows_verified", "verification_complete"}
    expect_keys(receipt, keys, "native receipt")
    expected_counts = {"actions_verified": n, "catalogue_actions_generated": n, "catalogues_verified": PARENTS, "duplicate_semantic_actions": 0, "extra_actions": 0, "forbidden_reordering": 0, "missing_actions": 0, "nonzero_child_targets": 0, "nonzero_parent_targets": 0, "parent_after_matches": n, "parent_count_matches": PARENTS, "parents_verified": PARENTS, "semantic_rows_verified": n}
    for key, value in expected_counts.items():
        if receipt[key] != value or type(receipt[key]) is not int:
            raise MergeError(f"native receipt {key} mismatch")
    if receipt["schema"] != NATIVE_SCHEMA or receipt["verification_complete"] is not True or receipt["identity_order"] != ["from", "to", "captured_square_bitboard_uint64", "promotes"] or receipt["identity_tuple"] != ["from", "to", "num_captures", "promotes", "captured_square_bitboard"]:
        raise MergeError("native receipt identity/schema/completion mismatch")
    expected_build = {"build_type": manifest["build"]["build_type"], "cmake_cache_sha256": manifest["build"]["cmake_cache"]["sha256"], "code_sha": manifest["code_sha"], "compiler_id": manifest["build"]["compiler_id"], "compiler_version": manifest["build"]["compiler_version"], "verifier_source_sha256": manifest["build"]["verifier_source"]["sha256"]}
    if receipt["build_provenance_declared"] != expected_build:
        raise MergeError("native receipt build provenance mismatch")
    expected_parents = {"local_name": parents["local_name"], "record_size_bytes": 38, "records": PARENTS, "sha256": parents["sha256"], "size_bytes": parents["size_bytes"]}
    expected_children = {"local_name": children_tmp.name, "record_size_bytes": 38, "records": n, "sha256": sha256_file(children_tmp), "size_bytes": children_tmp.stat().st_size}
    expected_semantic = {"local_name": semantic_tmp.name, "row_schema": SEMANTIC_SCHEMA, "rows": n, "sha256": sha256_file(semantic_tmp), "size_bytes": semantic_tmp.stat().st_size}
    expected_exe = {"local_name": verifier.name, "sha256": sha256_file(verifier), "size_bytes": verifier.stat().st_size}
    file_descriptor(receipt["parents"], "native receipt parents", kind="jnnw")
    file_descriptor(receipt["children"], "native receipt children", kind="jnnw")
    file_descriptor(receipt["semantic_actions"], "native receipt semantic actions", kind="semantic")
    file_descriptor(receipt["executable"], "native receipt executable")
    if receipt["parents"] != expected_parents or receipt["children"] != expected_children or receipt["semantic_actions"] != expected_semantic or receipt["executable"] != expected_exe:
        raise MergeError("native receipt payload/executable descriptors mismatch")


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = _existing_file(args.input_manifest, "input manifest")
    manifest, manifest_raw, files = validate_manifest(manifest_path, args.expected_input_manifest_sha256)
    base = manifest_path.parent

    def require_inputs_stable() -> None:
        current, current_raw, current_files = validate_manifest(
            manifest_path, args.expected_input_manifest_sha256
        )
        if current_raw != manifest_raw or current != manifest or set(current_files) != set(files):
            raise MergeError("input manifest changed during merger execution")
        for label, original in files.items():
            if not os.path.samefile(original, current_files[label]):
                raise MergeError(f"authenticated input identity changed: {label}")
        if sha256_file(files["adapter.tool"]) != sha256_file(Path(teacher.__file__)):
            raise MergeError("imported adapter tool changed during merger execution")
        if sha256_file(files["build.merge_tool"]) != sha256_file(Path(__file__)):
            raise MergeError("running merge tool changed during merger execution")
    direct = [
        (args.selection_report, "CLI selection report", files["selection.report"], manifest["selection"]["report"]["local_name"]),
        (args.parents_jnnw, "CLI parents JNNW", files["selection.parents_jnnw"], manifest["selection"]["parents_jnnw"]["local_name"]),
        (args.parents_tsv, "CLI parents TSV", files["selection.parents_tsv"], manifest["selection"]["parents_tsv"]["local_name"]),
        (args.legal_verifier, "CLI legal verifier", files["build.verifier_executable"], manifest["build"]["verifier_executable"]["local_name"]),
    ]
    for provided, label, expected, expected_name in direct:
        if provided.name != expected_name:
            raise MergeError(f"{label} basename differs from authenticated manifest")
        _same_file(_existing_file(provided, label), expected, label)
    if os.name != "nt" and not os.access(files["build.verifier_executable"], os.X_OK):
        raise MergeError("legal verifier is not executable")
    for option, prefix in ((args.shard_children, "children"), (args.shard_groups, "groups"), (args.shard_report, "report")):
        if len(option) != SHARDS:
            raise MergeError(f"exactly 16 --shard-{prefix} paths are required")
        by_name = {Path(path).name: path for path in option}
        if len(by_name) != SHARDS:
            raise MergeError(f"duplicate --shard-{prefix} basename")
        for shard in range(SHARDS):
            expected = files[f"shard.{shard}.{prefix}"]
            name = manifest["shards"][shard][{"children": "children_jnnw", "groups": "groups_tsv", "report": "report_json"}[prefix]]["local_name"]
            if name not in by_name:
                raise MergeError(f"missing CLI {prefix} path for shard {shard}")
            _same_file(_existing_file(by_name[name], f"CLI shard {shard} {prefix}"), expected, f"shard {shard} {prefix}")
    outputs = [args.out_children, args.out_groups, args.out_semantic_actions, args.report]
    for index, path in enumerate(outputs):
        safe_leaf(path.name, f"output {index} basename")
    temps = [Path(str(path) + ".tmp") for path in outputs]
    native_receipt = args.report.parent / "native-verification-receipt.json.tmp"
    native_internal_tmp = Path(str(native_receipt) + ".tmp")
    all_input_paths = [(manifest_path, "input manifest"), *[(path, label) for label, path in files.items()]]
    _check_distinct([*all_input_paths, *[(path, f"output {i}") for i, path in enumerate(outputs)], *[(path, f"temporary {i}") for i, path in enumerate(temps)], (native_receipt, "native receipt"), (native_internal_tmp, "native receipt temporary")])
    _refuse_existing_or_symlink([*outputs, *temps, native_receipt, native_internal_tmp])
    selection_report, selection_raw = read_json(files["selection.report"], canonical=True)
    if sha256_bytes(selection_raw) != strict_sha(args.expected_selection_report_sha256, "expected selection report SHA"):
        raise MergeError("selection report external SHA mismatch")
    if sha256_bytes(selection_raw) != manifest["selection"]["report"]["sha256"]:
        raise MergeError("selection report manifest SHA mismatch")
    contract, contract_raw = selector.load_contract(files["selection.contract"])
    if sha256_bytes(contract_raw) != manifest["selection"]["contract"]["sha256"]:
        raise MergeError("selection contract descriptor mismatch")
    parents_raw, parent_boards = parse_jnnw(files["selection.parents_jnnw"], PARENTS, "parents")
    parent_meta, parent_tsv_raw = read_parents_tsv(files["selection.parents_tsv"], parent_boards)
    identities_raw = "".join(f"{row['canonical_fingerprint']}\n" for row in parent_meta).encode("ascii")
    identities = manifest["selection"]["ordered_identities"]
    if len(identities_raw) != identities["size_bytes"] or sha256_bytes(identities_raw) != identities["sha256"]:
        raise MergeError("ordered identities bytes mismatch")
    _validate_selection_report(selection_report, manifest, contract, manifest["selection"]["parents_jnnw"], manifest["selection"]["parents_tsv"], identities)
    by_cell = {cell: 0 for cell in selector.CELL_ORDER}
    for row in parent_meta:
        by_cell[f"{row['phase']}_stm{row['stm_int']}"] += 1
    if by_cell != {cell: 500 for cell in selector.CELL_ORDER}:
        raise MergeError("parents TSV phase/STM cell counts mismatch")
    if contract["cell_order"] != selector.CELL_ORDER or contract["cell_quota"] != 500:
        raise MergeError("selection contract constants mismatch")
    _adapter_receipt(files["adapter.receipt"], manifest, files["adapter.base_source"], files["adapter.rendered_source"])
    if sha256_file(files["adapter.tool"]) != sha256_file(Path(teacher.__file__)):
        raise MergeError("adapter tool bytes differ from the imported audited implementation")
    if sha256_file(files["build.merge_tool"]) != sha256_file(Path(__file__)):
        raise MergeError("merge tool descriptor bytes differ from this implementation")
    read_json(files["teacher_runtime.egdb.identity_manifest"], canonical=False)
    reports: list[dict[str, Any]] = []
    groups_by_shard: list[list[dict[str, str]]] = []
    children_by_shard: list[list[bytes]] = []
    children_boards_by_shard: list[list[tuple[int, int, int, int, int]]] = []
    for shard, item in enumerate(manifest["shards"]):
        validate_shard_argv(item, manifest, files, base)
        report, _ = read_json(files[f"shard.{shard}.report"], canonical=False)
        teacher.validate_shard_report(report)
        if report["shard"] != shard or report["tt_mb"] != manifest["teacher_runtime"]["tt_mb"] or report["egdb_max_pieces"] != manifest["teacher_runtime"]["egdb"]["max_pieces"]:
            raise MergeError(f"shard {shard} report runtime mismatch")
        count = item["children_jnnw"]["records"]
        if report["emitted_siblings"] != count:
            raise MergeError(f"shard {shard} report/payload count mismatch")
        child_raw, child_boards = parse_jnnw(files[f"shard.{shard}.children"], count, f"shard {shard} children")
        groups, _ = read_groups(files[f"shard.{shard}.groups"], count, shard)
        group_sums = {
            "rule_terminal_children": sum(_uint_text(row["child_rule_terminal"], "child_rule_terminal", 1) for row in groups),
            "exact_tb_children": sum(_uint_text(row["child_tb_exact"], "child_tb_exact", 1) for row in groups),
            "cheap_nodes": sum(_uint_text(row["nodes5k"], "nodes5k", UINT64_MAX) for row in groups),
            "screen_nodes": sum(_uint_text(row["nodes50k"], "nodes50k", UINT64_MAX) for row in groups),
            "teacher_nodes": sum(_uint_text(row["nodes200k"], "nodes200k", UINT64_MAX) for row in groups),
        }
        for key, value in group_sums.items():
            if report[key] != value:
                raise MergeError(f"shard {shard} groups/report {key} mismatch")
        reports.append(report)
        groups_by_shard.append(groups)
        children_by_shard.append([child_raw[8 + i * RECORD_SIZE:8 + (i + 1) * RECORD_SIZE] for i in range(count)])
        children_boards_by_shard.append(child_boards)
    aggregate = teacher.merge_reports(reports)
    n = aggregate["emitted_siblings"]
    if not MIN_ACTIONS <= n <= MAX_ACTIONS:
        raise MergeError("global action count outside 8000..64000")
    cursors = [0] * SHARDS
    output_records: list[bytes] = []
    output_group_lines: list[str] = []
    semantics: list[dict[str, Any]] = []
    duplicate_path_entries = aggregate["duplicate_move_entries"]
    for parent_id in range(PARENTS):
        shard = parent_id % SHARDS
        count = parent_meta[parent_id]["legal_moves_int"]
        previous_order: tuple[int, int, int, bool] | None = None
        identities_seen: set[tuple[int, int, int, bool, int]] = set()
        for _ in range(count):
            local = cursors[shard]
            if local >= len(groups_by_shard[shard]):
                raise MergeError(f"shard {shard} ends within parent {parent_id}")
            group = groups_by_shard[shard][local]
            if _uint_text(group["parent_id"], "parent_id", PARENTS - 1) != parent_id:
                raise MergeError(f"shard {shard} parent blocks are not contiguous modulo order")
            if _uint_text(group["parent_stm"], "parent_stm", 1) != parent_meta[parent_id]["stm_int"]:
                raise MergeError("groups parent STM mismatch")
            action = structural_action(parent_boards[parent_id], children_boards_by_shard[shard][local], group, parent_meta[parent_id], shard, local, len(output_records))
            order = (action["from"], action["to"], action["captured_square_bitboard"], action["promotes"])
            identity = (action["from"], action["to"], action["num_captures"], action["promotes"], action["captured_square_bitboard"])
            if previous_order is not None and not previous_order < order:
                raise MergeError(f"teacher semantic order is not strict for parent {parent_id}")
            if identity in identities_seen:
                raise MergeError(f"duplicate semantic action for parent {parent_id}")
            previous_order = order
            identities_seen.add(identity)
            output_records.append(children_by_shard[shard][local])
            output_group_lines.append("\t".join([str(len(output_records) - 1), *[group[field] for field in GROUP_FIELDS[1:]]]))
            semantics.append(action)
            cursors[shard] += 1
    if any(cursors[shard] != len(groups_by_shard[shard]) for shard in range(SHARDS)):
        raise MergeError("one or more shard payloads contain trailing parent/action rows")
    children_bytes = b"JNNW" + struct.pack("<I", n) + b"".join(output_records)
    groups_bytes = ("\t".join(GROUP_FIELDS) + "\n" + "\n".join(output_group_lines) + "\n").encode("ascii")
    semantic_bytes = b"".join(canonical_json_bytes(row) for row in semantics)
    require_inputs_stable()
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    try:
        for path, raw in zip(temps[:3], (children_bytes, groups_bytes, semantic_bytes)):
            path.write_bytes(raw)
            if path.read_bytes() != raw:
                raise MergeError(f"temporary payload roundtrip failed: {path}")
        verifier = files["build.verifier_executable"]
        command = [str(verifier), "verify", "--parents-jnnw", str(files["selection.parents_jnnw"]), "--children-jnnw", str(temps[0]), "--semantic-actions", str(temps[2]), "--verifier-executable", str(verifier), "--expected-parents-sha256", manifest["selection"]["parents_jnnw"]["sha256"], "--expected-children-sha256", sha256_bytes(children_bytes), "--expected-semantic-actions-sha256", sha256_bytes(semantic_bytes), "--expected-verifier-executable-sha256", manifest["build"]["verifier_executable"]["sha256"], "--code-sha", manifest["code_sha"], "--verifier-source-sha256", manifest["build"]["verifier_source"]["sha256"], "--cmake-cache-sha256", manifest["build"]["cmake_cache"]["sha256"], "--build-type", manifest["build"]["build_type"], "--compiler-id", manifest["build"]["compiler_id"], "--compiler-version", manifest["build"]["compiler_version"], "--receipt", str(native_receipt)]
        completed = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={}, timeout=120, check=False)
        if completed.returncode != 0:
            raise MergeError(f"native legal verifier failed with exit {completed.returncode}: {completed.stderr.decode('utf-8', 'replace')[-2000:]}")
        if completed.stdout:
            raise MergeError("native legal verifier wrote unexpected stdout")
        native, native_raw = read_json(native_receipt, canonical=True)
        validate_native_receipt(native, n=n, parents=manifest["selection"]["parents_jnnw"], children_tmp=temps[0], semantic_tmp=temps[2], verifier=verifier, manifest=manifest)
        require_inputs_stable()
        report = {
            "adapter": manifest["adapter"], "aggregate": aggregate,
            "build": manifest["build"],
            "code_sha": manifest["code_sha"],
            "counters": {"captured_bitboards_reconstructed": n, "children_records": n,
                "duplicate_path_entries": duplicate_path_entries, "duplicate_semantic_actions": 0,
                "extra_actions": 0, "forbidden_reordering": 0, "full_catalogues_verified": PARENTS,
                "global_rows_rebased": n, "groups_rows": n, "missing_actions": 0,
                "nonzero_child_targets": 0, "parent_child_transitions_verified": n,
                "parents": PARENTS, "parents_with_legal_count_match": PARENTS,
                "processed_parent_rows": PARENTS, "semantic_actions": n,
                "semantic_ledger_rows": n, "shards": SHARDS},
            "identity_order": ["from", "to", "captured_square_bitboard_uint64", "promotes"],
            "identity_tuple": ["from", "to", "num_captures", "promotes", "captured_square_bitboard"],
            "input_manifest": {"local_name": manifest_path.name, "sha256": sha256_bytes(manifest_raw), "size_bytes": len(manifest_raw)},
            "native_verification": {"receipt": native, "sha256": sha256_bytes(native_raw), "size_bytes": len(native_raw)},
            "outputs": {
                "children_jnnw": {"local_name": args.out_children.name, "record_size_bytes": 38, "records": n, "sha256": sha256_bytes(children_bytes), "size_bytes": len(children_bytes)},
                "groups_tsv": {"local_name": args.out_groups.name, "rows": n, "sha256": sha256_bytes(groups_bytes), "size_bytes": len(groups_bytes)},
                "semantic_actions": {"local_name": args.out_semantic_actions.name, "row_schema": SEMANTIC_SCHEMA, "rows": n, "sha256": sha256_bytes(semantic_bytes), "size_bytes": len(semantic_bytes)}},
            "scientific_scope": {"calibration": False, "fits": 0, "model_selection": False,
                "promotion_authorized": False, "strength_games": 0, "training": False, "tuning": False},
            "schema": REPORT_SCHEMA,
            "selection": {"contract": manifest["selection"]["contract"],
                "ordered_identities": manifest["selection"]["ordered_identities"],
                "parents_jnnw": manifest["selection"]["parents_jnnw"],
                "parents_tsv": manifest["selection"]["parents_tsv"],
                "report": manifest["selection"]["report"]},
            "shards": manifest["shards"], "teacher_runtime": manifest["teacher_runtime"],
        }
        report_bytes = canonical_json_bytes(report)
        temps[3].write_bytes(report_bytes)
        if temps[3].read_bytes() != report_bytes:
            raise MergeError("temporary merge report roundtrip failed")
        for temp, final, expected in zip(temps, outputs, (children_bytes, groups_bytes, semantic_bytes, report_bytes)):
            os.replace(temp, final)
            published.append(final)
            if final.read_bytes() != expected:
                raise MergeError(f"published output roundtrip failed: {final}")
        return report
    except BaseException:
        for path in [*temps, native_receipt, native_internal_tmp, *published]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        native_receipt.unlink(missing_ok=True)
        native_internal_tmp.unlink(missing_ok=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--expected-input-manifest-sha256", required=True)
    parser.add_argument("--selection-report", type=Path, required=True)
    parser.add_argument("--expected-selection-report-sha256", required=True)
    parser.add_argument("--parents-jnnw", type=Path, required=True)
    parser.add_argument("--parents-tsv", type=Path, required=True)
    parser.add_argument("--shard-children", type=Path, action="append", required=True)
    parser.add_argument("--shard-groups", type=Path, action="append", required=True)
    parser.add_argument("--shard-report", type=Path, action="append", required=True)
    parser.add_argument("--legal-verifier", type=Path, required=True)
    parser.add_argument("--out-children", type=Path, required=True)
    parser.add_argument("--out-groups", type=Path, required=True)
    parser.add_argument("--out-semantic-actions", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run(args)
    except (MergeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes({"schema": REPORT_SCHEMA, "actions": report["counters"]["semantic_actions"], "report_sha256": sha256_file(args.report)}).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
