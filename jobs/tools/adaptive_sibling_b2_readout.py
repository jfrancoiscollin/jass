#!/usr/bin/env python3
"""Build and finalize the prospective PR771 B2 sealed readout.

The build command joins authenticated teacher observations only after the
allocation receipts have been sealed.  It never executes allocation policy or
search.  The finalize command delegates the fixed analysis to the published
statistics module and never exposes its private test hook through the CLI.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Iterable, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b2_statistics as statistics  # noqa: E402


BUILD_INPUT_SCHEMA = "jass.adaptive_sibling_b2_readout_inputs.v1"
TERMINAL_INPUT_SCHEMA = "jass.adaptive_sibling_b2_terminal_readout_inputs.v1"
RICH_SCHEMA = "jass.adaptive_sibling_b2_parent_stats_rich.v1"
REPORT_SCHEMA = "jass.adaptive_sibling_b2_rich_to_sufficient.v1"
TERMINAL_SCHEMA = "jass.adaptive_sibling_b2_terminal_readout.v1"
BUILD_FAILURE_SCHEMA = "jass.adaptive_sibling_b2_readout_build_failure.v1"
ALLOCATION_INPUT_SCHEMA = "jass.adaptive_sibling_b2_projection_input_parent.v1"
ALLOCATION_REPORT_SCHEMA = "jass.adaptive_sibling_b2_allocation_input_report.v1"
ALLOCATION_RECEIPT_SCHEMA = "jass.adaptive_sibling_b2_allocation_receipt_parent.v1"
PROJECTION_MANIFEST_SCHEMA = "jass.adaptive_sibling_b2_projection_manifest.v1"
SELECTION_REPORT_SCHEMA = "jass.adaptive_sibling_b2_target_blind_selection.v1"
MERGE_REPORT_SCHEMA = "jass.adaptive_sibling_b2_teacher_merge.v1"
SEMANTIC_SCHEMA = "jass.adaptive_sibling_b2_semantic_action.v1"
PREFLIGHT_VERDICT = "B2_SYNTHETIC_STATISTICAL_PREFLIGHT_COMPLETE"

PARENTS = 4_000
CELL_SIZE = 500
CELL_ORDER = list(statistics.CELL_ORDER)
UINT64_MAX = (1 << 64) - 1
INT64_MAX = (1 << 63) - 1
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
SELECTION_FIELDS = [
    "parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm",
    "pieces", "legal_moves", "phase", "source_shard", "source_row_index",
    "selection_hash",
]
SEMANTIC_KEYS = {
    "captured_kings", "captured_square_bitboard", "child_fingerprint",
    "child_pieces", "from", "global_row_index", "local_row_index",
    "material_count_delta_parent", "num_captures", "parent_fingerprint",
    "parent_id", "parent_legal_moves", "parent_pieces", "promotes", "schema",
    "source_shard", "to",
}
RECEIPT_KEYS = {
    "schema", "parent_id", "ordered_rows", "S5_rows", "S50_rows",
    "S200_charge_rows", "pre_q200_choice_row_or_null", "exact_shortcut_reason",
    "sole_survivor_reason", "uncertified_shadow", "shadow_nodes5",
    "shadow_nodes50", "shadow_nodes200", "shadow_nodes_total",
    "projection_input_sha256", "decision_input_sha256", "decision_output_sha256",
    "nodes200k_validated_rows", "nodes200k_policy_reads",
    "nodes200k_policy_branches", "nodes200k_preseal_aggregation_reads",
    "nodes200k_aggregation_reads", "q200_value_reads", "q200_label_reads",
    "q200_branches",
}
PROJECTION_MANIFEST_KEYS = {
    "schema", "policy", "parents", "rows", "input_jsonl_sha256",
    "allocation_receipts_jsonl_sha256", "canonical_serialization",
    "q200_value_reads", "q200_label_reads", "q200_branches",
    "nodes200k_validated_rows", "nodes200k_policy_reads",
    "nodes200k_policy_branches", "nodes200k_preseal_aggregation_reads",
    "nodes200k_aggregation_reads", "searches", "fits", "strength_games",
    "parent_receipts",
}
ALLOCATION_REPORT_KEYS = {
    "schema", "code_sha", "input_manifest_sha256", "output", "parents", "cells",
    "teacher_rows", "parent_group_joins", "semantic_joins", "projection_rows",
    "q200_value_reads", "q200_label_reads", "q200_branches", "q200_value_decodes",
    "q200_metadata_decodes", "nodes200k_validated_rows", "nodes200k_policy_reads",
    "nodes200k_policy_branches", "searches", "fits", "games", "promotions",
    "bakes", "status",
}

FIRST_LEVELS = [
    "SAME_ROW_VALUE_EQUIVALENT", "DIFFERENT_ROW_VALUE_EQUIVALENT_TIE",
    "DIFFERENT_ROW_VALUE_INEQUIVALENT",
]
SUBCATEGORIES = [
    "EXACT_OR_MIXED_MISMATCH", "SIGNAL_FAMILY_DOWN_WIN_UNRESOLVED",
    "SIGNAL_FAMILY_DOWN_WIN_LOSS", "SIGNAL_FAMILY_DOWN_UNRESOLVED_LOSS",
    "SIGNAL_FAMILY_UP_LOSS_UNRESOLVED", "SIGNAL_FAMILY_UP_LOSS_WIN",
    "SIGNAL_FAMILY_UP_UNRESOLVED_WIN", "FINITE_NUMERIC_1_99",
    "FINITE_NUMERIC_GE100", "WITHIN_TB_ENCODED_ORDER",
    "WITHIN_MATE_ENCODED_ORDER", "SAME_SIGNAL_FAMILY_DIFFERENT_MECHANISM",
    "OTHER_INCOMPATIBLE_SCORE_MECHANISM",
]
BUILD_OUTPUT_NAMES = (
    "parent-stats-rich-v1.jsonl", "parent-stats-sufficient-v1.jsonl",
    "rich-to-sufficient-report-v1.json",
)
SIGNAL_DIRECTIONS = {
    ("WIN_SCORE_SIGNAL", "UNRESOLVED_NUMERIC"): (1, "WIN_TO_UNRESOLVED"),
    ("WIN_SCORE_SIGNAL", "LOSS_SCORE_SIGNAL"): (2, "WIN_TO_LOSS"),
    ("UNRESOLVED_NUMERIC", "LOSS_SCORE_SIGNAL"): (3, "UNRESOLVED_TO_LOSS"),
    ("LOSS_SCORE_SIGNAL", "UNRESOLVED_NUMERIC"): (4, "LOSS_TO_UNRESOLVED"),
    ("LOSS_SCORE_SIGNAL", "WIN_SCORE_SIGNAL"): (5, "LOSS_TO_WIN"),
    ("UNRESOLVED_NUMERIC", "WIN_SCORE_SIGNAL"): (6, "UNRESOLVED_TO_WIN"),
}
RICH_KEYS = {
    "schema", "parent_id", "cell", "phase", "stm", "parent_identity", "upstream",
    "siblings", "costs", "allocation", "reference", "shadow", "fully_nonexact",
    "same_row", "value_equivalent", "tie_only", "exact_mismatch", "signal_event",
    "signal_direction_code", "signal_direction", "numeric", "comparison",
}
CHOICE_KEYS = {"row_index", "action", "immediate_exact", "exact_kind",
               "exact_parent_utility", "q200"}
OBSERVATION_KEYS = {"score", "nodes", "completed_depth", "effective_depth", "aborted",
                    "stop_reason", "elapsed_us", "pv_enters_egdb",
                    "decision_score_applicable", "score_band", "score_family",
                    "score_mechanism"}


class ReadoutError(RuntimeError):
    """An authentication, observation, join, or publication violation."""


class TechnicalIOError(ReadoutError):
    """An I/O failure that must never become a scientific support receipt."""


class OutputSafetyError(ReadoutError):
    """A path or publication collision that must remain a technical failure."""


BUILD_FAILURE_STAGES = {
    "INPUT_AUTHENTICATION_FAILED": "COMMON_MANIFEST",
    "SELECTION_STRUCTURE_INVALID": "SELECTION",
    "TEACHER_OBSERVATION_TRANSPORT_INVALID": "TEACHER_GROUP",
    "SEMANTIC_JOIN_INVALID": "SEMANTIC_ACTION",
    "ALLOCATION_BINDING_INVALID": "ALLOCATION_PARENT",
    "PROJECTION_BINDING_INVALID": "PROJECTION_RECEIPT",
    "POPULATION_OR_CELL_INVALID": "POPULATION_FINAL",
}


class BuildValidationFailure(ReadoutError):
    """Closed, typed scientific-support failure; never created from message text."""

    def __init__(self, failure_class: str, *, parent_id: int | None = None,
                 global_row_index: int | None = None, horizon: str | None = None):
        if failure_class not in BUILD_FAILURE_STAGES:
            raise ValueError("unknown build failure class")
        if parent_id is not None:
            _integer(parent_id, "failure parent_id", 0, PARENTS - 1)
        if global_row_index is not None:
            _integer(global_row_index, "failure global_row_index", 0, 63_999)
        if horizon not in {None, "5k", "50k", "200k"}:
            raise ValueError("unknown failure horizon")
        super().__init__(failure_class)
        self.failure_class = failure_class
        self.stage = BUILD_FAILURE_STAGES[failure_class]
        self.parent_id = parent_id
        self.global_row_index = global_row_index
        self.horizon = horizon


def canonical_json_bytes(value: object) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                           allow_nan=False, separators=(",", ":")) + "\n").encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ReadoutError(f"value is not canonical ASCII JSON: {exc}") from exc


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReadoutError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ReadoutError(f"non-finite JSON constant: {value}")


def read_canonical_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TechnicalIOError(f"cannot read JSON {path}: {exc}") from exc
    try:
        text = raw.decode("ascii")
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReadoutError(f"cannot read canonical JSON {path}: {exc}") from exc
    if type(value) is not dict or raw != canonical_json_bytes(value):
        raise ReadoutError(f"non-canonical JSON: {path}")
    return value, raw


def _keys(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise ReadoutError(f"{label} fields mismatch")
    return value


def _exact_json_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _exact_json_equal(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(
            _exact_json_equal(a, b) for a, b in zip(left, right))
    return left == right


def _file_identity(path: Path) -> tuple[int, int]:
    """Return a stable identity for a regular, non-symlink file."""
    if path.is_symlink():
        raise OutputSafetyError(f"output path became a symlink: {path}")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise TechnicalIOError(f"cannot stat owned output {path}: {exc}") from exc
    if not path.is_file():
        raise OutputSafetyError(f"output path is not a regular file: {path}")
    return metadata.st_dev, metadata.st_ino


def _write_exclusive(path: Path, raw: bytes) -> tuple[int, int]:
    """Create one owned file without replacing an existing path."""
    identity: tuple[int, int] | None = None
    try:
        with path.open("xb") as handle:
            metadata = os.fstat(handle.fileno())
            identity = (metadata.st_dev, metadata.st_ino)
            handle.write(raw)
    except FileExistsError:
        raise
    except OSError as exc:
        if identity is not None:
            _unlink_owned(path, identity)
        raise TechnicalIOError(f"cannot create output {path}: {exc}") from exc
    try:
        if identity is None or _file_identity(path) != identity:
            raise OutputSafetyError(f"new output identity changed: {path}")
        if path.read_bytes() != raw:
            raise TechnicalIOError(f"output roundtrip mismatch: {path}")
    except BaseException as exc:
        if identity is not None:
            _unlink_owned(path, identity)
        if isinstance(exc, OSError):
            raise TechnicalIOError(f"cannot verify output {path}: {exc}") from exc
        raise
    return identity


def _publish_new_from_owned_temp(temp: Path, final: Path, raw: bytes,
                                 *, temp_identity: tuple[int, int]) -> tuple[int, int]:
    """Link an owned temporary into a new final name without replacement."""
    if _file_identity(temp) != temp_identity:
        raise OutputSafetyError(f"temporary output identity changed: {temp}")
    linked = False
    try:
        try:
            os.link(temp, final)
            linked = True
        except FileExistsError:
            raise
        except OSError as exc:
            raise TechnicalIOError(f"cannot publish output {final}: {exc}") from exc
        final_identity = _file_identity(final)
        if final_identity != temp_identity:
            raise OutputSafetyError(f"published output identity mismatch: {final}")
        if final.read_bytes() != raw:
            raise TechnicalIOError(f"published output roundtrip mismatch: {final}")
    except BaseException as exc:
        if linked:
            _unlink_owned(final, temp_identity)
        if isinstance(exc, FileExistsError):
            raise
        if isinstance(exc, OSError):
            raise TechnicalIOError(f"cannot verify published output {final}: {exc}") from exc
        raise
    return final_identity


def _unlink_owned(path: Path, identity: tuple[int, int]) -> None:
    """Remove a file only while it still has the identity created by this process."""
    try:
        if _file_identity(path) == identity:
            path.unlink()
    except FileNotFoundError:
        return
    except (TechnicalIOError, OutputSafetyError, OSError):
        return


def _integer(value: object, label: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise ReadoutError(f"{label} must be an integer in [{lo},{hi}]")
    return value


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ReadoutError(f"{label} must be boolean")
    return value


def _text_int(value: str, label: str, lo: int, hi: int) -> int:
    pattern = UINT_RE if lo >= 0 else INT_RE
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ReadoutError(f"{label} is not a canonical integer")
    return _integer(int(value), label, lo, hi)


def _text_bool(value: str, label: str) -> bool:
    return bool(_text_int(value, label, 0, 1))


def _sha(value: object, label: str) -> str:
    if type(value) is not str or not SHA_RE.fullmatch(value):
        raise ReadoutError(f"{label} is not lowercase SHA256")
    return value


def _checked_sum(values: Iterable[int], label: str, *, require_positive: bool = False) -> int:
    total = 0
    for value in values:
        _integer(value, label, 0, UINT64_MAX)
        if total > UINT64_MAX - value:
            raise ReadoutError(f"{label} uint64 overflow")
        total += value
    if require_positive and total == 0:
        raise ReadoutError(f"{label} must be positive")
    return total


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.resolve(strict=False)))).casefold()


def _parse_jsonl(path: Path, *, rows: int | None = None) -> tuple[list[dict[str, Any]], list[bytes], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TechnicalIOError(f"cannot read JSONL {path}: {exc}") from exc
    try:
        raw.decode("ascii")
    except UnicodeError as exc:
        raise ReadoutError(f"cannot read ASCII JSONL {path}: {exc}") from exc
    if not raw or not raw.endswith(b"\n") or b"\r" in raw or raw.startswith(b"\xef\xbb\xbf"):
        raise ReadoutError(f"JSONL is not canonical LF-terminated ASCII: {path}")
    line_raws = raw.splitlines(keepends=True)
    if rows is not None and len(line_raws) != rows:
        raise ReadoutError(f"JSONL row count mismatch: {path}")
    values: list[dict[str, Any]] = []
    for number, line_raw in enumerate(line_raws, 1):
        if line_raw == b"\n":
            raise ReadoutError(f"empty JSONL line {number}")
        try:
            value = json.loads(line_raw.decode("ascii"), object_pairs_hook=_pairs,
                               parse_constant=_constant)
        except json.JSONDecodeError as exc:
            raise ReadoutError(f"invalid JSONL line {number}: {exc}") from exc
        if type(value) is not dict or line_raw != canonical_json_bytes(value):
            raise ReadoutError(f"non-canonical JSONL line {number}")
        values.append(value)
    return values, line_raws, raw


def _parse_tsv(path: Path, fields: Sequence[str]) -> tuple[list[dict[str, str]], list[bytes], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TechnicalIOError(f"cannot read TSV {path}: {exc}") from exc
    try:
        text = raw.decode("ascii")
    except UnicodeError as exc:
        raise ReadoutError(f"cannot read ASCII TSV {path}: {exc}") from exc
    if not raw.endswith(b"\n") or b"\r" in raw or raw.startswith(b"\xef\xbb\xbf"):
        raise ReadoutError(f"TSV is not LF-terminated ASCII: {path}")
    lines = text.splitlines()
    if not lines or lines[0].split("\t") != list(fields):
        raise ReadoutError(f"TSV header mismatch: {path}")
    line_raws = [line.encode("ascii") + b"\n" for line in lines[1:]]
    rows = []
    for number, line in enumerate(lines[1:], 1):
        values = line.split("\t")
        if len(values) != len(fields):
            raise ReadoutError(f"TSV width mismatch at data row {number}")
        rows.append(dict(zip(fields, values)))
    return rows, line_raws, raw


def classify_score(score: int) -> tuple[str, str, str]:
    score = _integer(score, "score", -30_000, 30_000)
    magnitude = abs(score)
    if magnitude <= 20_000:
        return "EVAL_COMPATIBLE", "UNRESOLVED_NUMERIC", "EVAL_NUMERIC"
    if 29_372 <= magnitude <= 29_935:
        return ("TB_DIRECT_COMPATIBLE",
                "WIN_SCORE_SIGNAL" if score > 0 else "LOSS_SCORE_SIGNAL",
                "TB_DIRECT_POSITIVE" if score > 0 else "TB_DIRECT_NEGATIVE")
    if 29_937 <= magnitude <= 30_000:
        return ("REAL_MATE_BAND",
                "WIN_SCORE_SIGNAL" if score > 0 else "LOSS_SCORE_SIGNAL",
                "REAL_MATE_POSITIVE" if score > 0 else "REAL_MATE_NEGATIVE")
    raise ReadoutError("non-exact score has unsupported semantics")


def validate_observation(group: Mapping[str, str], horizon: str, *, exact: bool,
                         rule_terminal: bool) -> dict[str, object]:
    budget = {"5k": 5_000, "50k": 50_000, "200k": 200_000}[horizon]
    score_field = {"5k": "q5k_parent", "50k": "q50_parent", "200k": "q200_parent"}[horizon]
    score = _text_int(group[score_field], score_field, -30_000, 30_000)
    nodes = _text_int(group[f"nodes{horizon}"], f"nodes{horizon}", 0, budget)
    completed = _text_int(group[f"completed_depth{horizon}"], "completed_depth", 0, 64)
    effective = _text_int(group[f"effective_depth{horizon}"], "effective_depth", 0, 64)
    if completed > effective:
        raise ReadoutError("completed depth exceeds effective depth")
    stop = group[f"stop{horizon}"]
    if stop not in {"none", "nodes"}:
        raise ReadoutError("stop reason outside {none,nodes}")
    if stop == "nodes" and nodes != budget:
        raise ReadoutError("nodes stop without exact budget consumption")
    aborted = _text_bool(group[f"aborted{horizon}"], "aborted")
    if aborted != (stop != "none" and effective > completed):
        raise ReadoutError("aborted/depth/stop invariant mismatch")
    elapsed = _text_int(group[f"elapsed_us{horizon}"], "elapsed_us", 0, UINT64_MAX)
    pv = _text_bool(group[f"pv{horizon}_enters_egdb"], "pv_enters_egdb")
    if rule_terminal and (score, nodes, completed, effective, stop, aborted) != (
            30_000, 0, 0, 0, "none", False):
        raise ReadoutError("rule-terminal search transport invariant mismatch")
    if not exact:
        if completed == 0:
            raise ReadoutError("non-exact observation has zero completed depth")
        if stop == "none" and (completed != 64 or effective != 64):
            raise ReadoutError("completed non-exact observation did not reach depth 64")
        band, family, mechanism = classify_score(score)
    else:
        band = family = mechanism = None
    return {
        "score": score, "nodes": nodes, "completed_depth": completed,
        "effective_depth": effective, "aborted": aborted, "stop_reason": stop,
        "elapsed_us": elapsed, "pv_enters_egdb": pv,
        "decision_score_applicable": not exact, "score_band": band,
        "score_family": family, "score_mechanism": mechanism,
    }


def _action(semantic: Mapping[str, Any]) -> dict[str, object]:
    _keys(semantic, SEMANTIC_KEYS, "semantic action")
    if semantic["schema"] != SEMANTIC_SCHEMA:
        raise ReadoutError("semantic action schema mismatch")
    captured = _integer(semantic["captured_square_bitboard"], "captured bitboard", 0, PLAYABLE)
    captures = _integer(semantic["num_captures"], "num_captures", 0, 20)
    if captured.bit_count() != captures:
        raise ReadoutError("semantic action capture count mismatch")
    return {
        "from": _integer(semantic["from"], "from", 1, 50),
        "to": _integer(semantic["to"], "to", 1, 50),
        "num_captures": captures,
        "promotes": _boolean(semantic["promotes"], "promotes"),
        "captured_square_bitboard": captured,
    }


def _choice(row: Mapping[str, Any]) -> dict[str, object]:
    exact = row["exact"]
    return {
        "row_index": row["row_index"], "action": _action(row["semantic"]),
        "immediate_exact": exact,
        "exact_kind": ("RULE_TERMINAL" if row["rule_terminal"] else
                       "CHILD_TB_EXACT" if row["tb_exact"] else "NONEXACT"),
        "exact_parent_utility": row["utility"] if exact else None,
        "q200": row["observations"]["200k"],
    }


def _validate_choice(value: object, label: str) -> dict[str, Any]:
    choice = dict(_keys(value, CHOICE_KEYS, label))
    row_index = _integer(choice["row_index"], f"{label}.row_index", 0, INT64_MAX)
    action = _keys(choice["action"], {"from", "to", "num_captures", "promotes",
                                      "captured_square_bitboard"}, f"{label}.action")
    captured = _integer(action["captured_square_bitboard"], "captured bitboard", 0, PLAYABLE)
    if captured.bit_count() != _integer(action["num_captures"], "num_captures", 0, 20):
        raise ReadoutError("choice capture count mismatch")
    _integer(action["from"], "from", 1, 50)
    _integer(action["to"], "to", 1, 50)
    _boolean(action["promotes"], "promotes")
    exact = _boolean(choice["immediate_exact"], f"{label}.immediate_exact")
    kind = choice["exact_kind"]
    if kind not in {"NONEXACT", "RULE_TERMINAL", "CHILD_TB_EXACT"} \
            or exact != (kind != "NONEXACT"):
        raise ReadoutError("choice exact kind mismatch")
    utility = choice["exact_parent_utility"]
    if exact:
        _integer(utility, "exact utility", -1, 1)
        if kind == "RULE_TERMINAL" and utility != 1:
            raise ReadoutError("rule-terminal choice utility must be +1")
    elif utility is not None:
        raise ReadoutError("non-exact choice utility must be null")
    observation = _keys(choice["q200"], OBSERVATION_KEYS, f"{label}.q200")
    score = _integer(observation["score"], "q200.score", -30_000, 30_000)
    nodes = _integer(observation["nodes"], "q200.nodes", 0, 200_000)
    completed = _integer(observation["completed_depth"], "completed depth", 0, 64)
    effective = _integer(observation["effective_depth"], "effective depth", 0, 64)
    if completed > effective:
        raise ReadoutError("choice completed depth exceeds effective depth")
    aborted = _boolean(observation["aborted"], "aborted")
    stop = observation["stop_reason"]
    if stop not in {"none", "nodes"}:
        raise ReadoutError("choice stop reason mismatch")
    if stop == "nodes" and nodes != 200_000:
        raise ReadoutError("choice nodes stop without exact budget consumption")
    if aborted != (stop != "none" and effective > completed):
        raise ReadoutError("choice aborted/depth/stop invariant mismatch")
    _integer(observation["elapsed_us"], "elapsed_us", 0, UINT64_MAX)
    _boolean(observation["pv_enters_egdb"], "pv_enters_egdb")
    applicable = _boolean(observation["decision_score_applicable"], "decision applicability")
    if applicable != (not exact):
        raise ReadoutError("choice decision-score applicability mismatch")
    if exact:
        if any(observation[key] is not None for key in ("score_band", "score_family", "score_mechanism")):
            raise ReadoutError("exact choice classifies an unused score")
        if kind == "RULE_TERMINAL" and (score, nodes, completed, effective, stop, aborted) != (
                30_000, 0, 0, 0, "none", False):
            raise ReadoutError("rule-terminal choice transport invariant mismatch")
    else:
        if completed == 0 or (stop == "none" and (completed != 64 or effective != 64)):
            raise ReadoutError("non-exact choice has unsupported depth completion")
        if tuple(observation[key] for key in ("score_band", "score_family", "score_mechanism")) \
                != classify_score(score):
            raise ReadoutError("non-exact choice score classification mismatch")
    return {"row_index": row_index, "exact": exact, "utility": utility,
            "observations": {"200k": observation}}


def sufficient_from_rich(value: object) -> statistics.ParentStatsSufficientV1:
    rich = _keys(value, RICH_KEYS, "rich parent")
    if rich["schema"] != RICH_SCHEMA:
        raise ReadoutError("rich parent schema mismatch")
    parent_id = _integer(rich["parent_id"], "parent_id", 0, PARENTS - 1)
    phase = rich["phase"]
    stm = _integer(rich["stm"], "stm", 0, 1)
    if phase not in {"P0", "P1", "P2", "P3"} or rich["cell"] != f"{phase}_stm{stm}":
        raise ReadoutError("rich phase/STM/cell mismatch")
    identities = _keys(rich["parent_identity"], {"raw_fingerprint", "canonical_fingerprint"},
                       "parent_identity")
    if any(type(value) is not str or not value.isascii() or not value for value in identities.values()):
        raise ReadoutError("parent identities must be nonempty ASCII")
    upstream = _keys(rich["upstream"], {
        "selection_parent_row_sha256", "teacher_parent_block_sha256",
        "semantic_parent_block_sha256", "projection_input_sha256",
        "decision_input_sha256", "decision_output_sha256", "allocation_receipt_sha256"},
        "upstream")
    for key, digest in upstream.items():
        _sha(digest, f"upstream.{key}")
    siblings = _keys(rich["siblings"], {"count", "exact_count", "nonexact_count"}, "siblings")
    count = _integer(siblings["count"], "siblings.count", 2, 16)
    exact_count = _integer(siblings["exact_count"], "siblings.exact_count", 0, count)
    if _integer(siblings["nonexact_count"], "siblings.nonexact_count", 0, count) != count - exact_count:
        raise ReadoutError("sibling exact/non-exact partition mismatch")
    fully_nonexact = _boolean(rich["fully_nonexact"], "fully_nonexact")
    if fully_nonexact != (exact_count == 0):
        raise ReadoutError("fully_nonexact mismatch")
    costs = _keys(rich["costs"], {"full_nodes5", "full_nodes50", "full_nodes200",
                                                "full_nodes_total", "shadow_nodes5",
                                                "shadow_nodes50", "shadow_nodes200",
                                                "shadow_nodes_total"}, "costs")
    full = _checked_sum((_integer(costs[key], key, 0, UINT64_MAX)
                         for key in ("full_nodes5", "full_nodes50", "full_nodes200")),
                        "full total", require_positive=True)
    shadow = _checked_sum((_integer(costs[key], key, 0, UINT64_MAX)
                           for key in ("shadow_nodes5", "shadow_nodes50", "shadow_nodes200")),
                          "shadow total")
    if costs["full_nodes_total"] != full or type(costs["full_nodes_total"]) is not int \
            or costs["shadow_nodes_total"] != shadow or type(costs["shadow_nodes_total"]) is not int:
        raise ReadoutError("rich cost component sum mismatch")
    allocation = _keys(rich["allocation"], {"ordered_rows", "S5_rows", "S50_rows",
                                             "S200_charge_rows", "pre_q200_choice_row_or_null",
                                             "exact_shortcut_reason", "sole_survivor_reason",
                                             "uncertified_shadow"}, "allocation")
    ordered = allocation["ordered_rows"]
    if type(ordered) is not list or len(ordered) != count \
            or ordered != sorted(ordered) or len(set(ordered)) != count \
            or any(type(row) is not int or row < 0 or row > INT64_MAX for row in ordered):
        raise ReadoutError("rich ordered rows mismatch")
    for name in ("S5_rows", "S50_rows", "S200_charge_rows"):
        rows = allocation[name]
        if type(rows) is not list or rows != sorted(rows) or len(set(rows)) != len(rows) \
                or any(type(row) is not int or row not in ordered for row in rows):
            raise ReadoutError(f"rich {name} mismatch")
    if not set(allocation["S50_rows"]).issubset(allocation["S5_rows"]) \
            or not set(allocation["S200_charge_rows"]).issubset(allocation["S50_rows"]):
        raise ReadoutError("rich survivor-set nesting mismatch")
    exact_reason = allocation["exact_shortcut_reason"]
    sole_reason = allocation["sole_survivor_reason"]
    if exact_reason not in {None, "EXACT_WIN", "ALL_EXACT_DRAW", "ALL_EXACT_LOSS"} \
            or sole_reason not in {None, "SOLE_UNRESOLVED_BEFORE_Q200"}:
        raise ReadoutError("rich allocation reason enum mismatch")
    uncertified = _boolean(allocation["uncertified_shadow"], "uncertified_shadow")
    prechoice = allocation["pre_q200_choice_row_or_null"]
    if prechoice is not None and (type(prechoice) is not int or prechoice not in ordered):
        raise ReadoutError("rich pre-q200 choice mismatch")
    if exact_reason is not None and (sole_reason is not None or prechoice is None
                                     or any(allocation[name] for name in (
                                         "S5_rows", "S50_rows", "S200_charge_rows"))
                                     or uncertified):
        raise ReadoutError("rich exact shortcut shape mismatch")
    if sole_reason is not None and (exact_reason is not None or prechoice is None
                                    or allocation["S200_charge_rows"] or not uncertified):
        raise ReadoutError("rich sole-survivor shape mismatch")
    if exact_reason is None and sole_reason is None and (
            prechoice is not None or not allocation["S200_charge_rows"] or uncertified):
        raise ReadoutError("rich q200 allocation shape mismatch")
    reference = _validate_choice(rich["reference"], "reference")
    chosen = _validate_choice(rich["shadow"], "shadow")
    if reference["row_index"] not in ordered:
        raise ReadoutError("rich reference choice is not a sibling")
    if prechoice is not None and chosen["row_index"] != prechoice:
        raise ReadoutError("rich shadow differs from sealed pre-q200 choice")
    if prechoice is None and chosen["row_index"] not in allocation["S200_charge_rows"]:
        raise ReadoutError("rich shadow is not a charged q200 sibling")
    expected_utility = {"EXACT_WIN": 1, "ALL_EXACT_DRAW": 0,
                        "ALL_EXACT_LOSS": -1}.get(exact_reason)
    if exact_reason is not None and (not chosen["exact"]
                                     or chosen["utility"] != expected_utility):
        raise ReadoutError("rich exact shortcut choice/reason mismatch")
    if sole_reason is not None and chosen["exact"]:
        raise ReadoutError("rich sole survivor is exact")
    recomputed = _comparison(reference, chosen)
    for key in ("same_row", "value_equivalent", "tie_only", "exact_mismatch",
                "signal_event", "signal_direction_code", "signal_direction", "numeric",
                "comparison"):
        if not _exact_json_equal(rich[key], recomputed[key]):
            raise ReadoutError(f"rich comparison field mismatch: {key}")
    return statistics.ParentStatsSufficientV1(
        parent_id=parent_id, cell=rich["cell"], full_nodes=full, shadow_nodes=shadow,
        fully_nonexact=fully_nonexact, same_row=rich["same_row"],
        value_equivalent=rich["value_equivalent"], exact_mismatch=rich["exact_mismatch"],
        signal_event=rich["signal_event"], signal_direction_code=rich["signal_direction_code"],
        numeric_eligible=rich["numeric"]["eligible"],
        numeric_component=rich["numeric"]["component"])


def _reference_row(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    wins = [row for row in rows if row["exact"] and row["utility"] == 1]
    if wins:
        return min(wins, key=lambda row: row["row_index"])
    nonexact = [row for row in rows if not row["exact"]]
    if nonexact:
        return min(nonexact, key=lambda row: (-row["observations"]["200k"]["score"], row["row_index"]))
    draws = [row for row in rows if row["utility"] == 0]
    return min(draws or list(rows), key=lambda row: row["row_index"])


def _shadow_row(rows_by_id: Mapping[int, Mapping[str, Any]], receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    prechoice = receipt["pre_q200_choice_row_or_null"]
    if prechoice is not None:
        return rows_by_id[_integer(prechoice, "pre-q200 choice", 0, INT64_MAX)]
    charge = receipt["S200_charge_rows"]
    if not charge:
        raise ReadoutError("null pre-q200 choice with empty S200 charge")
    candidates = [rows_by_id[row_id] for row_id in charge]
    return min(candidates, key=lambda row: (-row["observations"]["200k"]["score"], row["row_index"]))


def _comparison(reference: Mapping[str, Any], shadow: Mapping[str, Any]) -> dict[str, object]:
    same_row = reference["row_index"] == shadow["row_index"]
    if reference["exact"] and shadow["exact"]:
        equivalent = reference["utility"] == shadow["utility"]
    elif not reference["exact"] and not shadow["exact"]:
        equivalent = (reference["observations"]["200k"]["score"]
                      == shadow["observations"]["200k"]["score"])
    else:
        equivalent = False
    if same_row and not equivalent:
        raise ReadoutError("same row is not value-equivalent")
    exact_mismatch = (not same_row and not equivalent
                      and (reference["exact"] or shadow["exact"]))
    ref_obs = reference["observations"]["200k"]
    shadow_obs = shadow["observations"]["200k"]
    if not reference["exact"] and not shadow["exact"]:
        code, direction = SIGNAL_DIRECTIONS.get(
            (ref_obs["score_family"], shadow_obs["score_family"]), (0, "NONE"))
    else:
        code, direction = 0, "NONE"
    signal_event = code in {1, 2, 3}
    numeric_eligible = (not reference["exact"] and not shadow["exact"]
                        and ref_obs["score_band"] == "EVAL_COMPATIBLE"
                        and shadow_obs["score_band"] == "EVAL_COMPATIBLE")
    delta = max(0, ref_obs["score"] - shadow_obs["score"]) if numeric_eligible else None
    component = delta if delta is not None else 0
    if same_row:
        first = "SAME_ROW_VALUE_EQUIVALENT"
    elif equivalent:
        first = "DIFFERENT_ROW_VALUE_EQUIVALENT_TIE"
    else:
        first = "DIFFERENT_ROW_VALUE_INEQUIVALENT"
    subcategory = None
    if first == "DIFFERENT_ROW_VALUE_INEQUIVALENT":
        if exact_mismatch:
            subcategory = "EXACT_OR_MIXED_MISMATCH"
        elif code:
            subcategory = {
                1: "SIGNAL_FAMILY_DOWN_WIN_UNRESOLVED",
                2: "SIGNAL_FAMILY_DOWN_WIN_LOSS",
                3: "SIGNAL_FAMILY_DOWN_UNRESOLVED_LOSS",
                4: "SIGNAL_FAMILY_UP_LOSS_UNRESOLVED",
                5: "SIGNAL_FAMILY_UP_LOSS_WIN",
                6: "SIGNAL_FAMILY_UP_UNRESOLVED_WIN",
            }[code]
        elif numeric_eligible and 1 <= component <= 99:
            subcategory = "FINITE_NUMERIC_1_99"
        elif numeric_eligible and component >= 100:
            subcategory = "FINITE_NUMERIC_GE100"
        elif ref_obs["score_band"] == shadow_obs["score_band"] == "TB_DIRECT_COMPATIBLE":
            subcategory = "WITHIN_TB_ENCODED_ORDER"
        elif ref_obs["score_band"] == shadow_obs["score_band"] == "REAL_MATE_BAND":
            subcategory = "WITHIN_MATE_ENCODED_ORDER"
        elif (ref_obs["score_family"] is not None
              and ref_obs["score_family"] == shadow_obs["score_family"]
              and ref_obs["score_mechanism"] != shadow_obs["score_mechanism"]):
            subcategory = "SAME_SIGNAL_FAMILY_DIFFERENT_MECHANISM"
        else:
            subcategory = "OTHER_INCOMPATIBLE_SCORE_MECHANISM"
    return {
        "same_row": same_row, "value_equivalent": equivalent,
        "tie_only": not same_row and equivalent, "exact_mismatch": exact_mismatch,
        "signal_event": signal_event, "signal_direction_code": code,
        "signal_direction": direction,
        "numeric": {"eligible": numeric_eligible, "delta": delta,
                    "component": component,
                    "moderate_1_99": component if 1 <= component <= 99 else 0,
                    "numeric_ge_100": bool(numeric_eligible and component >= 100)},
        "comparison": {"first_level": first, "subcategory": subcategory},
    }


def _build_rich_parent_impl(*, selection: Mapping[str, Any], selection_line: bytes,
                            groups: Sequence[Mapping[str, str]], group_lines: Sequence[bytes],
                            semantics: Sequence[Mapping[str, Any]], semantic_lines: Sequence[bytes],
                            allocation: Mapping[str, Any], allocation_line: bytes,
                            receipt: Mapping[str, Any], receipt_line: bytes,
                            failure_state: dict[str, object]) -> tuple[dict[str, object], statistics.ParentStatsSufficientV1, dict[str, int]]:
    def stage(failure_class: str, *, parent_id: int | None = None,
              row_index: int | None = None, horizon: str | None = None) -> None:
        failure_state.update({"failure_class": failure_class, "parent_id": parent_id,
                              "global_row_index": row_index, "horizon": horizon})

    stage("SELECTION_STRUCTURE_INVALID")
    if set(selection) != set(SELECTION_FIELDS):
        raise ReadoutError("selection parent fields mismatch")
    expected_selection_line = ("\t".join(str(selection[field]) for field in SELECTION_FIELDS)
                               + "\n").encode("ascii")
    if selection_line != expected_selection_line:
        raise ReadoutError("selection object/line mismatch")
    parent_id = _text_int(selection["parent_id"], "selection parent_id", 0, PARENTS - 1)
    stage("SELECTION_STRUCTURE_INVALID", parent_id=parent_id)
    phase = selection["phase"]
    stm = _text_int(selection["parent_stm"], "selection stm", 0, 1)
    if phase not in {"P0", "P1", "P2", "P3"}:
        raise ReadoutError("selection phase mismatch")
    cell = f"{phase}_stm{stm}"
    if len(groups) < 2 or len(groups) > 16 or len(groups) != len(semantics):
        stage("POPULATION_OR_CELL_INVALID")
        raise ReadoutError("parent sibling cardinality outside 2..16")
    if len(group_lines) != len(groups) or len(semantic_lines) != len(groups):
        stage("POPULATION_OR_CELL_INVALID")
        raise ReadoutError("parent block line cardinality mismatch")
    stage("TEACHER_OBSERVATION_TRANSPORT_INVALID", parent_id=parent_id)
    for group, line in zip(groups, group_lines):
        if line != ("\t".join(str(group[field]) for field in GROUP_FIELDS) + "\n").encode("ascii"):
            raise ReadoutError("teacher object/line mismatch")
    for semantic, line in zip(semantics, semantic_lines):
        stage("SEMANTIC_JOIN_INVALID", parent_id=parent_id)
        if line != canonical_json_bytes(dict(semantic)):
            raise ReadoutError("semantic object/line mismatch")
    stage("ALLOCATION_BINDING_INVALID", parent_id=parent_id)
    if allocation_line != canonical_json_bytes(dict(allocation)) \
            :
        raise ReadoutError("allocation object/line mismatch")
    stage("PROJECTION_BINDING_INVALID", parent_id=parent_id)
    if receipt_line != canonical_json_bytes(dict(receipt)):
        raise ReadoutError("receipt object/line mismatch")
    stage("ALLOCATION_BINDING_INVALID", parent_id=parent_id)
    _keys(allocation, {"schema", "parent_id", "phase", "stm", "rows"}, "allocation parent")
    if allocation["schema"] != ALLOCATION_INPUT_SCHEMA \
            or _integer(allocation["parent_id"], "allocation parent_id", 0, PARENTS - 1) != parent_id \
            or allocation["phase"] != phase \
            or _integer(allocation["stm"], "allocation stm", 0, 1) != stm:
        raise ReadoutError("allocation parent identity mismatch")
    _keys(receipt, RECEIPT_KEYS, "allocation receipt")
    stage("PROJECTION_BINDING_INVALID", parent_id=parent_id)
    if receipt["schema"] != ALLOCATION_RECEIPT_SCHEMA \
            or _integer(receipt["parent_id"], "receipt parent_id", 0, PARENTS - 1) != parent_id:
        raise ReadoutError("allocation receipt identity mismatch")
    if type(receipt["ordered_rows"]) is not list:
        raise ReadoutError("ordered rows must be an array")
    ordered = [_integer(x, "ordered row", 0, INT64_MAX) for x in receipt["ordered_rows"]]
    if ordered != sorted(ordered) or len(set(ordered)) != len(groups):
        raise ReadoutError("ordered rows are incomplete, duplicated, or unsorted")
    rows: list[dict[str, Any]] = []
    allocation_rows = allocation["rows"]
    stage("ALLOCATION_BINDING_INVALID", parent_id=parent_id)
    if type(allocation_rows) is not list or len(allocation_rows) != len(groups):
        raise ReadoutError("allocation rows cardinality mismatch")
    for offset, (group, semantic, alloc) in enumerate(zip(groups, semantics, allocation_rows)):
        stage("TEACHER_OBSERVATION_TRANSPORT_INVALID", parent_id=parent_id)
        row_index = _text_int(group["row_index"], "group row_index", 0, INT64_MAX)
        if row_index > 63_999:
            raise ReadoutError("teacher global row exceeds sealed maximum")
        stage("SEMANTIC_JOIN_INVALID", parent_id=parent_id, row_index=row_index)
        semantic_global = _integer(semantic["global_row_index"], "semantic global row", 0, INT64_MAX)
        semantic_parent = _integer(semantic["parent_id"], "semantic parent_id", 0, PARENTS - 1)
        semantic_parent_pieces = _integer(semantic["parent_pieces"], "semantic parent pieces", 1, 40)
        semantic_legal = _integer(semantic["parent_legal_moves"], "semantic legal moves", 2, 16)
        semantic_shard = _integer(semantic["source_shard"], "semantic source shard", 0, 15)
        _integer(semantic["local_row_index"], "semantic local row", 0, INT64_MAX)
        _integer(semantic["captured_kings"], "semantic captured kings", 0, 20)
        _integer(semantic["material_count_delta_parent"], "semantic material delta", -20, 20)
        _integer(semantic["child_pieces"], "semantic child pieces", 0, 40)
        if type(semantic["child_fingerprint"]) is not str or not semantic["child_fingerprint"].isascii() \
                or not semantic["child_fingerprint"]:
            raise ReadoutError("semantic child fingerprint mismatch")
        if row_index != ordered[offset] or semantic_global != row_index:
            raise ReadoutError("teacher/semantic/receipt row order mismatch")
        if _text_int(group["parent_id"], "group parent_id", 0, PARENTS - 1) != parent_id \
                or semantic_parent != parent_id:
            raise ReadoutError("teacher/semantic parent join mismatch")
        if (group["parent_fingerprint"] != selection["raw_fingerprint"]
                or semantic["parent_fingerprint"] != selection["raw_fingerprint"]
                or _text_int(group["parent_stm"], "group parent_stm", 0, 1) != stm
                or _text_int(group["parent_pieces"], "group parent_pieces", 1, 40)
                    != _text_int(selection["pieces"], "selection pieces", 9, 40)
                or semantic_parent_pieces != int(selection["pieces"])
                or semantic_legal != len(groups)
                or semantic_shard != parent_id % 16):
            raise ReadoutError("teacher/semantic/selection parent metadata mismatch")
        action = _action(semantic)
        if (action["from"] != _text_int(group["from"], "from", 1, 50)
                or action["to"] != _text_int(group["to"], "to", 1, 50)
                or action["num_captures"] != _text_int(group["num_captures"], "num_captures", 0, 20)
                or action["promotes"] != _text_bool(group["promotes"], "promotes")
                or semantic["captured_kings"] != _text_int(group["captured_kings"], "captured_kings", 0, 20)
                or semantic["material_count_delta_parent"]
                    != _text_int(group["material_count_delta_parent"], "material delta", -20, 20)
                or semantic["child_pieces"] != _text_int(group["child_pieces"], "child pieces", 0, 40)):
            raise ReadoutError("semantic action differs from teacher movement columns")
        stage("TEACHER_OBSERVATION_TRANSPORT_INVALID", parent_id=parent_id,
              row_index=row_index)
        rule = _text_bool(group["child_rule_terminal"], "child_rule_terminal")
        tb = _text_bool(group["child_tb_exact"], "child_tb_exact")
        if rule and tb:
            raise ReadoutError("rule-terminal and TB-exact are mutually exclusive")
        utility = _text_int(group["exact_parent_utility"], "exact utility", -1, 2)
        exact = rule or tb
        if (rule and utility != 1) or (tb and utility not in {-1, 0, 1}) \
                or (not exact and utility != 2):
            raise ReadoutError("exact flags and utility mismatch")
        expected_alloc = {
            "row_index": row_index, "child_rule_terminal": rule,
            "child_tb_exact": tb, "exact_parent_utility": utility,
            "q5k_parent": _text_int(group["q5k_parent"], "q5k", INT32_MIN, INT32_MAX),
            "q50_parent": _text_int(group["q50_parent"], "q50", INT32_MIN, INT32_MAX),
            "nodes5k": _text_int(group["nodes5k"], "nodes5k", 0, UINT64_MAX),
            "nodes50k": _text_int(group["nodes50k"], "nodes50k", 0, UINT64_MAX),
            "nodes200k": _text_int(group["nodes200k"], "nodes200k", 0, UINT64_MAX),
        }
        stage("ALLOCATION_BINDING_INVALID", parent_id=parent_id, row_index=row_index)
        if not _exact_json_equal(alloc, expected_alloc):
            raise ReadoutError("allocation row differs from authenticated teacher allowlist")
        observations = {}
        for horizon in ("5k", "50k", "200k"):
            stage("TEACHER_OBSERVATION_TRANSPORT_INVALID", parent_id=parent_id,
                  row_index=row_index, horizon=horizon)
            observations[horizon] = validate_observation(
                group, horizon, exact=exact, rule_terminal=rule)
        rows.append({"row_index": row_index, "rule_terminal": rule, "tb_exact": tb,
                     "exact": exact, "utility": utility, "semantic": semantic,
                     "observations": observations, "group": group})
    stage("PROJECTION_BINDING_INVALID", parent_id=parent_id)
    if ordered != [row["row_index"] for row in rows]:
        raise ReadoutError("ordered rows differ from teacher block")
    stage("PROJECTION_BINDING_INVALID", parent_id=parent_id)
    if sha256_bytes(allocation_line) != receipt["projection_input_sha256"]:
        raise ReadoutError("projection input per-parent hash mismatch")
    for key in ("projection_input_sha256", "decision_input_sha256", "decision_output_sha256"):
        _sha(receipt[key], key)
    decision_view = {
        "schema": allocation["schema"], "parent_id": allocation["parent_id"],
        "phase": allocation["phase"], "stm": allocation["stm"],
        "rows": [{key: value for key, value in row.items() if key != "nodes200k"}
                 for row in allocation_rows],
    }
    if sha256_bytes(canonical_json_bytes(decision_view)) != receipt["decision_input_sha256"]:
        raise ReadoutError("decision input hash mismatch")
    decision_output = {key: receipt[key] for key in (
        "parent_id", "ordered_rows", "S5_rows", "S50_rows", "S200_charge_rows",
        "pre_q200_choice_row_or_null", "exact_shortcut_reason", "sole_survivor_reason",
        "uncertified_shadow")}
    if sha256_bytes(canonical_json_bytes(decision_output)) != receipt["decision_output_sha256"]:
        raise ReadoutError("decision output hash mismatch")
    for key in ("q200_value_reads", "q200_label_reads", "q200_branches",
                "nodes200k_policy_reads", "nodes200k_policy_branches",
                "nodes200k_preseal_aggregation_reads"):
        if receipt[key] != 0 or type(receipt[key]) is not int:
            raise ReadoutError(f"nonzero projection barrier counter {key}")
    if type(receipt["nodes200k_validated_rows"]) is not int \
            or receipt["nodes200k_validated_rows"] != len(rows) \
            or type(receipt["nodes200k_aggregation_reads"]) is not int \
            or receipt["nodes200k_aggregation_reads"] != len(receipt["S200_charge_rows"]):
        raise ReadoutError("projection ingress/aggregation counter mismatch")
    rows_by_id = {row["row_index"]: row for row in rows}
    for name in ("S5_rows", "S50_rows", "S200_charge_rows"):
        if type(receipt[name]) is not list:
            raise ReadoutError(f"{name} is not an array")
        values = [_integer(x, name, 0, INT64_MAX) for x in receipt[name]]
        if values != sorted(values) or len(set(values)) != len(values) or any(x not in rows_by_id for x in values):
            raise ReadoutError(f"{name} is not a sorted row subset")
    if not set(receipt["S50_rows"]).issubset(receipt["S5_rows"]) \
            or not set(receipt["S200_charge_rows"]).issubset(receipt["S50_rows"]):
        raise ReadoutError("projection survivor set nesting mismatch")
    exact_reason = receipt["exact_shortcut_reason"]
    sole_reason = receipt["sole_survivor_reason"]
    if exact_reason not in {None, "EXACT_WIN", "ALL_EXACT_DRAW", "ALL_EXACT_LOSS"} \
            or sole_reason not in {None, "SOLE_UNRESOLVED_BEFORE_Q200"}:
        raise ReadoutError("projection reason enum mismatch")
    uncertified = _boolean(receipt["uncertified_shadow"], "uncertified_shadow")
    prechoice = receipt["pre_q200_choice_row_or_null"]
    if prechoice is not None and (type(prechoice) is not int or prechoice not in rows_by_id):
        raise ReadoutError("pre-q200 choice is not a parent row")
    if exact_reason is not None and (prechoice is None or any(receipt[name] for name in ("S5_rows", "S50_rows", "S200_charge_rows"))):
        raise ReadoutError("exact shortcut receipt shape mismatch")
    if sole_reason is not None and (prechoice is None or receipt["S200_charge_rows"] or not uncertified):
        raise ReadoutError("sole-survivor receipt shape mismatch")
    if exact_reason is None and sole_reason is None and (prechoice is not None or not receipt["S200_charge_rows"] or uncertified):
        raise ReadoutError("q200-charged receipt shape mismatch")
    nodes5_expected = 0 if exact_reason is not None else _checked_sum(
        (row["observations"]["5k"]["nodes"] for row in rows if not row["exact"]),
        "shadow nodes5")
    nodes50_expected = _checked_sum((rows_by_id[x]["observations"]["50k"]["nodes"] for x in receipt["S5_rows"]), "shadow nodes50")
    nodes200_expected = _checked_sum((rows_by_id[x]["observations"]["200k"]["nodes"] for x in receipt["S200_charge_rows"]), "shadow nodes200")
    shadow_total = _checked_sum((nodes5_expected, nodes50_expected, nodes200_expected), "shadow total")
    sealed_costs = [_integer(receipt[key], key, 0, UINT64_MAX) for key in (
        "shadow_nodes5", "shadow_nodes50", "shadow_nodes200", "shadow_nodes_total")]
    if sealed_costs != [nodes5_expected, nodes50_expected, nodes200_expected, shadow_total]:
        raise ReadoutError("shadow cost differs from sealed allocation receipt")
    full5 = _checked_sum((row["observations"]["5k"]["nodes"] for row in rows), "full nodes5")
    full50 = _checked_sum((row["observations"]["50k"]["nodes"] for row in rows), "full nodes50")
    full200 = _checked_sum((row["observations"]["200k"]["nodes"] for row in rows), "full nodes200")
    full_total = _checked_sum((full5, full50, full200), "full total", require_positive=True)
    reference = _reference_row(rows)
    shadow = _shadow_row(rows_by_id, receipt)
    comparison = _comparison(reference, shadow)
    exact_count = sum(row["exact"] for row in rows)
    rich: dict[str, object] = {
        "schema": RICH_SCHEMA, "parent_id": parent_id, "cell": cell,
        "phase": phase, "stm": stm,
        "parent_identity": {"raw_fingerprint": selection["raw_fingerprint"],
                            "canonical_fingerprint": selection["canonical_fingerprint"]},
        "upstream": {
            "selection_parent_row_sha256": sha256_bytes(selection_line),
            "teacher_parent_block_sha256": sha256_bytes(b"".join(group_lines)),
            "semantic_parent_block_sha256": sha256_bytes(b"".join(semantic_lines)),
            "projection_input_sha256": receipt["projection_input_sha256"],
            "decision_input_sha256": receipt["decision_input_sha256"],
            "decision_output_sha256": receipt["decision_output_sha256"],
            "allocation_receipt_sha256": sha256_bytes(receipt_line),
        },
        "siblings": {"count": len(rows), "exact_count": exact_count,
                     "nonexact_count": len(rows) - exact_count},
        "costs": {"full_nodes5": full5, "full_nodes50": full50,
                  "full_nodes200": full200, "full_nodes_total": full_total,
                  "shadow_nodes5": nodes5_expected, "shadow_nodes50": nodes50_expected,
                  "shadow_nodes200": nodes200_expected, "shadow_nodes_total": shadow_total},
        "allocation": {"ordered_rows": ordered, "S5_rows": receipt["S5_rows"],
                       "S50_rows": receipt["S50_rows"],
                       "S200_charge_rows": receipt["S200_charge_rows"],
                       "pre_q200_choice_row_or_null": prechoice,
                       "exact_shortcut_reason": exact_reason,
                       "sole_survivor_reason": sole_reason,
                       "uncertified_shadow": uncertified},
        "reference": _choice(reference), "shadow": _choice(shadow),
        "fully_nonexact": exact_count == 0,
        **comparison,
    }
    sufficient = statistics.ParentStatsSufficientV1(
        parent_id=parent_id, cell=cell, full_nodes=full_total,
        shadow_nodes=shadow_total, fully_nonexact=exact_count == 0,
        same_row=bool(comparison["same_row"]),
        value_equivalent=bool(comparison["value_equivalent"]),
        exact_mismatch=bool(comparison["exact_mismatch"]),
        signal_event=bool(comparison["signal_event"]),
        signal_direction_code=int(comparison["signal_direction_code"]),
        numeric_eligible=bool(comparison["numeric"]["eligible"]),
        numeric_component=int(comparison["numeric"]["component"]),
    )
    stage("POPULATION_OR_CELL_INVALID")
    if not _exact_json_equal(sufficient_from_rich(rich).to_mapping(), sufficient.to_mapping()):
        raise ReadoutError("internal rich-to-sufficient projection mismatch")
    observations = len(rows) * 3
    counts = {"total": observations, "transport_valid": observations,
              "nonexact_support_valid": (len(rows) - exact_count) * 3,
              "exact_transport_valid": exact_count * 3,
              "exact_score_band_classifications": 0,
              "exact_score_family_classifications": 0,
              "exact_score_endpoint_uses": 0}
    return rich, sufficient, counts


def build_rich_parent(*, selection: Mapping[str, Any], selection_line: bytes,
                      groups: Sequence[Mapping[str, str]], group_lines: Sequence[bytes],
                      semantics: Sequence[Mapping[str, Any]], semantic_lines: Sequence[bytes],
                      allocation: Mapping[str, Any], allocation_line: bytes,
                      receipt: Mapping[str, Any], receipt_line: bytes) -> tuple[dict[str, object], statistics.ParentStatsSufficientV1, dict[str, int]]:
    state: dict[str, object] = {}
    try:
        return _build_rich_parent_impl(
            selection=selection, selection_line=selection_line, groups=groups,
            group_lines=group_lines, semantics=semantics, semantic_lines=semantic_lines,
            allocation=allocation, allocation_line=allocation_line, receipt=receipt,
            receipt_line=receipt_line, failure_state=state)
    except BuildValidationFailure:
        raise
    except ReadoutError as exc:
        raise BuildValidationFailure(
            str(state.get("failure_class", "POPULATION_OR_CELL_INVALID")),
            parent_id=state.get("parent_id"),
            global_row_index=state.get("global_row_index"),
            horizon=state.get("horizon")) from exc


def _write_new_directory(out_dir: Path, files: Mapping[str, bytes]) -> None:
    if out_dir.exists() or out_dir.is_symlink():
        raise ReadoutError("output directory must be absent")
    parent = out_dir.parent.resolve()
    if not parent.is_dir():
        raise ReadoutError("output parent directory does not exist")
    if any(type(name) is not str or not name or Path(name).name != name for name in files) \
            or len(set(files)) != len(files):
        raise ReadoutError("output names must be distinct basenames")
    finals = [out_dir / name for name in files]
    owned: dict[Path, tuple[int, int]] = {}
    out_dir.mkdir()
    try:
        for name, raw in files.items():
            path = out_dir / name
            temp = out_dir / f"{name}.tmp"
            if path.exists() or temp.exists() or path.is_symlink() or temp.is_symlink():
                raise ReadoutError("output or temporary path already exists")
            temp_identity = _write_exclusive(temp, raw)
            owned[temp] = temp_identity
            final_identity = _publish_new_from_owned_temp(
                temp, path, raw, temp_identity=temp_identity)
            owned[path] = final_identity
            _unlink_owned(temp, temp_identity)
            owned.pop(temp, None)
        if set(out_dir.iterdir()) != set(finals):
            raise ReadoutError("unexpected file appeared in output directory")
    except BaseException:
        for path, identity in tuple(owned.items()):
            _unlink_owned(path, identity)
        try:
            out_dir.rmdir()
        except OSError:
            pass
        raise


def _guard_build_destinations(input_manifest: Path, out_dir: Path,
                              failure_receipt: Path) -> None:
    finals = [out_dir / name for name in BUILD_OUTPUT_NAMES]
    temps = [Path(str(path) + ".tmp") for path in finals]
    failure_temp = Path(str(failure_receipt) + ".tmp")
    paths = [input_manifest, out_dir, *finals, *temps, failure_receipt, failure_temp]
    if len({_path_key(path) for path in paths}) != len(paths):
        raise ReadoutError("build input/output/failure paths alias")
    if out_dir.exists() or out_dir.is_symlink() \
            or failure_receipt.exists() or failure_receipt.is_symlink() \
            or failure_temp.exists() or failure_temp.is_symlink():
        raise ReadoutError("build output/failure destinations must be absent")
    if not out_dir.parent.resolve().is_dir() \
            or not failure_receipt.parent.resolve().is_dir():
        raise ReadoutError("build output/failure parent directory is missing")


def _build_failure_receipt(*, failure: BuildValidationFailure,
                           expected_input_sha256: str,
                           actual_input_sha256: str | None,
                           input_authenticated: bool,
                           manifest_code_sha: str | None,
                           tool_binding_authenticated: bool,
                           preregistration_authenticated: bool) -> dict[str, object]:
    _sha(expected_input_sha256, "expected input manifest SHA")
    if actual_input_sha256 is not None:
        _sha(actual_input_sha256, "actual input manifest SHA")
    if input_authenticated:
        if manifest_code_sha is None or not GIT_RE.fullmatch(manifest_code_sha):
            raise ReadoutError("authenticated failure receipt lacks code SHA")
    elif any((manifest_code_sha is not None, tool_binding_authenticated,
              preregistration_authenticated, failure.parent_id is not None,
              failure.global_row_index is not None, failure.horizon is not None)):
        raise ReadoutError("unauthenticated failure receipt claims authenticated context")
    tool_path = Path(__file__).resolve()
    tool_raw = tool_path.read_bytes()
    receipt = {
        "schema": BUILD_FAILURE_SCHEMA, "status": "SUPPORT_NOT_ESTABLISHED",
        "expected_input_manifest_sha256": expected_input_sha256,
        "actual_input_manifest_sha256": actual_input_sha256,
        "input_manifest_authenticated": input_authenticated,
        "manifest_code_sha": manifest_code_sha,
        "running_tool": {"sha256": sha256_bytes(tool_raw), "size_bytes": len(tool_raw)},
        "tool_binding_authenticated": tool_binding_authenticated,
        "preregistration_authenticated": preregistration_authenticated,
        "failure": {"class": failure.failure_class, "stage": failure.stage,
                    "parent_id": failure.parent_id,
                    "global_row_index": failure.global_row_index,
                    "horizon": failure.horizon},
        "outputs": {"rich_jsonl": None, "sufficient_jsonl": None,
                    "rich_to_sufficient_report": None, "statistics": None},
        "counters": {"rich_rows_published": 0, "sufficient_rows_published": 0,
                     "statistics_invocations": 0, "bootstrap_draws": 0,
                     "searches": 0, "fits": 0, "games": 0,
                     "promotions": 0},
    }
    return receipt


def _validate_build_failure_receipt(value: object) -> dict[str, Any]:
    receipt = dict(_keys(value, {
        "schema", "status", "expected_input_manifest_sha256",
        "actual_input_manifest_sha256", "input_manifest_authenticated",
        "manifest_code_sha", "running_tool", "tool_binding_authenticated",
        "preregistration_authenticated", "failure", "outputs", "counters"},
        "build failure receipt"))
    if receipt["schema"] != BUILD_FAILURE_SCHEMA \
            or receipt["status"] != "SUPPORT_NOT_ESTABLISHED":
        raise ReadoutError("build failure receipt schema/status mismatch")
    _sha(receipt["expected_input_manifest_sha256"], "expected input manifest SHA")
    if receipt["actual_input_manifest_sha256"] is not None:
        _sha(receipt["actual_input_manifest_sha256"], "actual input manifest SHA")
    authenticated = _boolean(receipt["input_manifest_authenticated"], "input authenticated")
    tool_authenticated = _boolean(receipt["tool_binding_authenticated"], "tool authenticated")
    prereg_authenticated = _boolean(
        receipt["preregistration_authenticated"], "preregistration authenticated")
    code_sha = receipt["manifest_code_sha"]
    if code_sha is not None and (type(code_sha) is not str or not GIT_RE.fullmatch(code_sha)):
        raise ReadoutError("build failure manifest code SHA mismatch")
    tool = _keys(receipt["running_tool"], {"sha256", "size_bytes"}, "running tool")
    _sha(tool["sha256"], "running tool SHA")
    _integer(tool["size_bytes"], "running tool size", 1, INT64_MAX)
    failure = _keys(receipt["failure"], {
        "class", "stage", "parent_id", "global_row_index", "horizon"}, "failure")
    failure_class = failure["class"]
    if failure_class not in BUILD_FAILURE_STAGES \
            or failure["stage"] != BUILD_FAILURE_STAGES[failure_class]:
        raise ReadoutError("build failure class/stage mismatch")
    if failure["parent_id"] is not None:
        _integer(failure["parent_id"], "failure parent_id", 0, PARENTS - 1)
    if failure["global_row_index"] is not None:
        _integer(failure["global_row_index"], "failure row index", 0, 63_999)
    if failure["horizon"] not in {None, "5k", "50k", "200k"}:
        raise ReadoutError("build failure horizon mismatch")
    if not _exact_json_equal(receipt["outputs"], {
            "rich_jsonl": None, "sufficient_jsonl": None,
            "rich_to_sufficient_report": None, "statistics": None}):
        raise ReadoutError("build failure receipt claims outputs")
    counters = _keys(receipt["counters"], {
        "rich_rows_published", "sufficient_rows_published", "statistics_invocations",
        "bootstrap_draws", "searches", "fits", "games", "promotions"}, "failure counters")
    if any(type(counter) is not int or counter != 0 for counter in counters.values()):
        raise ReadoutError("build failure counters must be integer zero")
    if authenticated:
        if code_sha is None or not tool_authenticated or not prereg_authenticated:
            raise ReadoutError("authenticated failure receipt has incomplete provenance")
    elif any((code_sha is not None, tool_authenticated, prereg_authenticated,
              failure["parent_id"] is not None, failure["global_row_index"] is not None,
              failure["horizon"] is not None)):
        raise ReadoutError("unauthenticated failure receipt claims trusted context")
    if not authenticated and failure_class != "INPUT_AUTHENTICATION_FAILED":
        raise ReadoutError("unauthenticated receipt has a post-authentication failure class")
    return receipt


def _publish_build_failure(path: Path, receipt: Mapping[str, Any]) -> None:
    checked = _validate_build_failure_receipt(receipt)
    raw = canonical_json_bytes(checked)
    temporary = Path(str(path) + ".tmp")
    owned: dict[Path, tuple[int, int]] = {}
    try:
        temp_identity = _write_exclusive(temporary, raw)
        owned[temporary] = temp_identity
        final_identity = _publish_new_from_owned_temp(
            temporary, path, raw, temp_identity=temp_identity)
        owned[path] = final_identity
        parsed, final_raw = read_canonical_json(path)
        if not _exact_json_equal(parsed, checked) or final_raw != raw:
            raise TechnicalIOError("failure receipt final roundtrip mismatch")
        _unlink_owned(temporary, temp_identity)
        owned.pop(temporary, None)
    except BaseException:
        for owned_path, identity in tuple(owned.items()):
            _unlink_owned(owned_path, identity)
        raise


def _descriptor(path: Path, *, rows: int | None = None, row_schema: str | None = None) -> dict[str, object]:
    raw = path.read_bytes()
    result: dict[str, object] = {"local_name": path.name, "sha256": sha256_bytes(raw),
                                "size_bytes": len(raw)}
    if rows is not None:
        result["rows"] = rows
    if row_schema is not None:
        result["row_schema"] = row_schema
    return result


def _build_report(code_sha: str, input_sha: str, rich_lines: list[bytes],
                  sufficient_lines: list[bytes], rich_rows: Sequence[Mapping[str, Any]],
                  observation_counts: Mapping[str, int], teacher_rows: int) -> dict[str, object]:
    cells = {cell: 0 for cell in CELL_ORDER}
    fully = {cell: 0 for cell in CELL_ORDER}
    numeric = {cell: 0 for cell in CELL_ORDER}
    first = {key: 0 for key in FIRST_LEVELS}
    sub = {key: 0 for key in SUBCATEGORIES}
    row_hashes = []
    for parent_id, (rich, rich_line, sufficient_line) in enumerate(zip(rich_rows, rich_lines, sufficient_lines)):
        if rich["parent_id"] != parent_id:
            raise ReadoutError("rich parent IDs are not contiguous")
        cell = rich["cell"]
        cells[cell] += 1
        fully[cell] += int(rich["fully_nonexact"])
        numeric[cell] += int(rich["numeric"]["eligible"])
        first[rich["comparison"]["first_level"]] += 1
        category = rich["comparison"]["subcategory"]
        if category is not None:
            sub[category] += 1
        row_hashes.append({"parent_id": parent_id, "rich_line_sha256": sha256_bytes(rich_line),
                           "sufficient_line_sha256": sha256_bytes(sufficient_line)})
    if cells != {cell: CELL_SIZE for cell in CELL_ORDER}:
        raise ReadoutError("rich population is not 8x500")
    inequivalent = first["DIFFERENT_ROW_VALUE_INEQUIVALENT"]
    if sum(first.values()) != PARENTS or sum(sub.values()) != inequivalent:
        raise ReadoutError("ledger is not exhaustive")
    ids_raw = b"".join(canonical_json_bytes(parent_id) for parent_id in range(PARENTS))
    return {
        "schema": REPORT_SCHEMA, "code_sha": code_sha,
        "input_manifest_sha256": input_sha,
        "outputs": {
            "rich": {"local_name": "parent-stats-rich-v1.jsonl",
                     "sha256": sha256_bytes(b"".join(rich_lines)),
                     "size_bytes": len(b"".join(rich_lines)), "rows": PARENTS,
                     "row_schema": RICH_SCHEMA},
            "sufficient": {"local_name": "parent-stats-sufficient-v1.jsonl",
                           "sha256": sha256_bytes(b"".join(sufficient_lines)),
                           "size_bytes": len(b"".join(sufficient_lines)), "rows": PARENTS,
                           "row_schema": statistics.INPUT_SCHEMA}},
        "ordered_parent_ids_sha256": sha256_bytes(ids_raw), "row_hashes": row_hashes,
        "population": {"parents": PARENTS, "cells": cells, "teacher_rows": teacher_rows,
                       "fully_nonexact_global": sum(fully.values()),
                       "fully_nonexact_by_cell": fully,
                       "numeric_eligible_global": sum(numeric.values()),
                       "numeric_eligible_by_cell": numeric},
        "observation_validation": {**observation_counts, "invalid": 0},
        "ledger": {"first_level_counts": first, "subcategory_counts": sub,
                   "unclassified": 0, "first_level_sum": PARENTS,
                   "subcategory_sum": inequivalent, "value_inequivalent": inequivalent},
        "barrier": {"allocation_decisions_recomputed": 0,
                    "allocation_q200_value_reads": 0, "allocation_q200_label_reads": 0,
                    "allocation_q200_branches": 0,
                    "postseal_q200_score_decodes": teacher_rows},
        "actions": {"searches": 0, "fits": 0, "games": 0,
                    "promotions": 0, "bakes": 0},
        "support_inputs_valid": True, "status": "VALID",
    }


def build_from_components(*, code_sha: str, input_manifest_sha256: str,
                          selections: Sequence[Mapping[str, Any]], selection_lines: Sequence[bytes],
                          groups_by_parent: Sequence[Sequence[Mapping[str, str]]],
                          group_lines_by_parent: Sequence[Sequence[bytes]],
                          semantics_by_parent: Sequence[Sequence[Mapping[str, Any]]],
                          semantic_lines_by_parent: Sequence[Sequence[bytes]],
                          allocations: Sequence[Mapping[str, Any]], allocation_lines: Sequence[bytes],
                          receipts: Sequence[Mapping[str, Any]], receipt_lines: Sequence[bytes]) -> tuple[bytes, bytes, bytes]:
    _sha(input_manifest_sha256, "input manifest SHA")
    if not GIT_RE.fullmatch(code_sha):
        raise ReadoutError("code SHA mismatch")
    sequences = (selections, selection_lines, groups_by_parent, group_lines_by_parent,
                 semantics_by_parent, semantic_lines_by_parent, allocations,
                 allocation_lines, receipts, receipt_lines)
    if any(len(sequence) != PARENTS for sequence in sequences):
        raise ReadoutError("build inputs must contain exactly 4000 aligned parents")
    rich_rows: list[dict[str, object]] = []
    sufficient_rows: list[statistics.ParentStatsSufficientV1] = []
    observation_counts = {"total": 0, "transport_valid": 0,
                          "nonexact_support_valid": 0, "exact_transport_valid": 0,
                          "exact_score_band_classifications": 0,
                          "exact_score_family_classifications": 0,
                          "exact_score_endpoint_uses": 0}
    teacher_rows = 0
    for parent_id in range(PARENTS):
        rich, sufficient, counts = build_rich_parent(
            selection=selections[parent_id], selection_line=selection_lines[parent_id],
            groups=groups_by_parent[parent_id], group_lines=group_lines_by_parent[parent_id],
            semantics=semantics_by_parent[parent_id], semantic_lines=semantic_lines_by_parent[parent_id],
            allocation=allocations[parent_id], allocation_line=allocation_lines[parent_id],
            receipt=receipts[parent_id], receipt_line=receipt_lines[parent_id])
        rich_rows.append(rich)
        sufficient_rows.append(sufficient)
        teacher_rows += len(groups_by_parent[parent_id])
        for key in observation_counts:
            observation_counts[key] += counts[key]
    rich_lines = [canonical_json_bytes(row) for row in rich_rows]
    sufficient_lines = [canonical_json_bytes(row.to_mapping()) for row in sufficient_rows]
    report = _build_report(code_sha, input_manifest_sha256, rich_lines, sufficient_lines,
                           rich_rows, observation_counts, teacher_rows)
    return b"".join(rich_lines), b"".join(sufficient_lines), canonical_json_bytes(report)


def _build_success(args: argparse.Namespace, state: dict[str, object]) -> None:
    # The common authenticator is imported here so importing this module never
    # opens teacher payloads and so its q200-free preparation remains a separate
    # process boundary.
    from jobs.tools import adaptive_sibling_b2_allocation_input as common

    authenticated = common.authenticate_common_manifest(
        args.input_manifest, args.expected_input_manifest_sha256,
        expected_schema=BUILD_INPUT_SCHEMA,
        exact_root_keys=frozenset({"allocation", "code_sha", "preregistration",
                                   "projection", "schema", "selection",
                                   "teacher_merge", "tools"}),
        exact_tool_keys=frozenset({"allocation_input", "projection", "readout",
                                   "statistics", "statistical_preflight_receipt"}))
    manifest = authenticated.manifest
    if set(manifest) != {"allocation", "code_sha", "preregistration", "projection",
                        "schema", "selection", "teacher_merge", "tools"}:
        raise ReadoutError("readout input manifest root fields mismatch")
    implementation_paths = {
        "allocation_input": Path(common.__file__).resolve(),
        "projection": Path(__file__).with_name("adaptive_sibling_b2_projection.py").resolve(),
        "readout": Path(__file__).resolve(),
        "statistics": Path(statistics.__file__).resolve(),
    }
    for name, implementation in implementation_paths.items():
        if common.sha256_file(authenticated.files[f"tools.{name}"]) != common.sha256_file(implementation):
            raise BuildValidationFailure("INPUT_AUTHENTICATION_FAILED")
    state.update({"authenticated": True, "manifest_code_sha": manifest["code_sha"],
                  "tool_binding_authenticated": True,
                  "preregistration_authenticated": True,
                  "failure_class": "ALLOCATION_BINDING_INVALID"})
    # The final common-authenticator interface supplies already authenticated
    # paths.  Keep this adapter narrow and explicit rather than rediscovering
    # files from untrusted local_name values.
    base = authenticated.base_dir
    allocation = _keys(manifest["allocation"], {"input_jsonl", "report", "report_schema"},
                       "allocation")
    if allocation["report_schema"] != ALLOCATION_REPORT_SCHEMA:
        raise ReadoutError("allocation report schema declaration mismatch")
    allocation_input = common.verify_file_descriptor(
        base, allocation["input_jsonl"], "allocation.input_jsonl",
        extra_keys=frozenset({"rows", "row_schema"}))
    if allocation["input_jsonl"]["rows"] != PARENTS \
            or allocation["input_jsonl"]["row_schema"] != ALLOCATION_INPUT_SCHEMA:
        raise ReadoutError("allocation input descriptor mismatch")
    allocation_report_path = common.verify_file_descriptor(
        base, allocation["report"], "allocation.report")
    state["failure_class"] = "PROJECTION_BINDING_INVALID"
    projection = _keys(manifest["projection"], {"receipts_jsonl", "manifest", "manifest_schema"},
                       "projection")
    if projection["manifest_schema"] != PROJECTION_MANIFEST_SCHEMA:
        raise ReadoutError("projection manifest schema declaration mismatch")
    projection_receipts = common.verify_file_descriptor(
        base, projection["receipts_jsonl"], "projection.receipts_jsonl",
        extra_keys=frozenset({"rows", "row_schema"}))
    if projection["receipts_jsonl"]["rows"] != PARENTS \
            or projection["receipts_jsonl"]["row_schema"] != ALLOCATION_RECEIPT_SCHEMA:
        raise ReadoutError("projection receipts descriptor mismatch")
    projection_manifest_path = common.verify_file_descriptor(
        base, projection["manifest"], "projection.manifest")
    protected = [args.input_manifest.resolve(), *authenticated.files.values(), allocation_input,
                 allocation_report_path, projection_receipts, projection_manifest_path]
    if len({_path_key(path) for path in protected}) != len(protected):
        raise OutputSafetyError("readout input paths contain aliases")
    common.guard_new_output_dir(args.out_dir, protected, output_names=(
        "parent-stats-rich-v1.jsonl", "parent-stats-sufficient-v1.jsonl",
        "rich-to-sufficient-report-v1.json"))
    failure_paths = (args.failure_receipt, Path(str(args.failure_receipt) + ".tmp"))
    if any(_path_key(path) in {_path_key(source) for source in protected}
           for path in failure_paths):
        raise OutputSafetyError("failure receipt aliases an authenticated input")
    state["failure_class"] = "SELECTION_STRUCTURE_INVALID"
    selections, selection_lines, _ = _parse_tsv(
        authenticated.files["selection.parents_tsv"], SELECTION_FIELDS)
    state["failure_class"] = "TEACHER_OBSERVATION_TRANSPORT_INVALID"
    groups, group_lines, _ = _parse_tsv(authenticated.files["teacher.groups_tsv"], GROUP_FIELDS)
    state["failure_class"] = "SEMANTIC_JOIN_INVALID"
    semantics, semantic_lines, _ = _parse_jsonl(authenticated.files["teacher.semantic_actions"])
    state["failure_class"] = "ALLOCATION_BINDING_INVALID"
    allocations, allocation_lines, allocation_raw = _parse_jsonl(allocation_input, rows=PARENTS)
    allocation_report, _ = read_canonical_json(allocation_report_path)
    _keys(allocation_report, ALLOCATION_REPORT_KEYS, "allocation report")
    if allocation_report.get("schema") != ALLOCATION_REPORT_SCHEMA \
            or allocation_report.get("code_sha") != manifest["code_sha"] \
            or allocation_report.get("status") != "VALID":
        raise ReadoutError("allocation report is not VALID")
    expected_allocation_output = dict(allocation["input_jsonl"])
    if not _exact_json_equal(allocation_report["output"], expected_allocation_output):
        raise ReadoutError("allocation report output binding mismatch")
    teacher_rows_declared = manifest["teacher_merge"]["groups_tsv"]["rows"]
    allocation_fixed = {
        "parents": PARENTS, "cells": {cell: CELL_SIZE for cell in CELL_ORDER},
        "teacher_rows": teacher_rows_declared, "parent_group_joins": PARENTS,
        "semantic_joins": teacher_rows_declared, "projection_rows": teacher_rows_declared,
        "q200_value_reads": 0, "q200_label_reads": 0, "q200_branches": 0,
        "q200_value_decodes": 0, "q200_metadata_decodes": 0,
        "nodes200k_validated_rows": teacher_rows_declared,
        "nodes200k_policy_reads": 0, "nodes200k_policy_branches": 0,
        "searches": 0, "fits": 0, "games": 0, "promotions": 0, "bakes": 0,
    }
    for key, expected in allocation_fixed.items():
        if not _exact_json_equal(allocation_report[key], expected):
            raise ReadoutError(f"allocation report contract mismatch: {key}")
    state["failure_class"] = "PROJECTION_BINDING_INVALID"
    receipts, receipt_lines, receipts_raw = _parse_jsonl(projection_receipts, rows=PARENTS)
    projection_manifest, _ = read_canonical_json(projection_manifest_path)
    _keys(projection_manifest, PROJECTION_MANIFEST_KEYS, "projection manifest")
    if projection_manifest.get("schema") != PROJECTION_MANIFEST_SCHEMA \
            or projection_manifest.get("parents") != PARENTS \
            or projection_manifest.get("input_jsonl_sha256") != sha256_bytes(allocation_raw) \
            or projection_manifest.get("allocation_receipts_jsonl_sha256") != sha256_bytes(receipts_raw):
        raise ReadoutError("projection manifest identity mismatch")
    if not _exact_json_equal(projection_manifest["policy"],
                             {"M5": 100, "M50": 60, "minimum_survivors": 2}) \
            or projection_manifest["canonical_serialization"] != \
            "UTF-8, compact sorted-key JSON, LF per record" \
            or projection_manifest["rows"] != teacher_rows_declared \
            or projection_manifest["nodes200k_validated_rows"] != teacher_rows_declared:
        raise ReadoutError("projection manifest fixed contract mismatch")
    for name in ("q200_value_reads", "q200_label_reads", "q200_branches",
                 "nodes200k_policy_reads", "nodes200k_policy_branches",
                 "nodes200k_preseal_aggregation_reads", "searches", "fits", "strength_games"):
        if projection_manifest.get(name) != 0 or type(projection_manifest.get(name)) is not int:
            raise ReadoutError(f"projection manifest barrier mismatch: {name}")
    parent_receipts = projection_manifest.get("parent_receipts")
    if type(parent_receipts) is not list or len(parent_receipts) != PARENTS:
        raise ReadoutError("projection parent receipt catalogue mismatch")
    for parent_id, (catalogue, receipt, receipt_line) in enumerate(zip(parent_receipts, receipts, receipt_lines)):
        expected = {"parent_id": parent_id,
                    "allocation_receipt_sha256": sha256_bytes(receipt_line),
                    "projection_input_sha256": receipt.get("projection_input_sha256"),
                    "decision_input_sha256": receipt.get("decision_input_sha256"),
                    "decision_output_sha256": receipt.get("decision_output_sha256")}
        if not _exact_json_equal(catalogue, expected):
            raise ReadoutError("projection per-parent receipt hash mismatch")
    if len(groups) != len(semantics) or len(groups) != projection_manifest.get("rows"):
        raise ReadoutError("teacher/projection row cardinality mismatch")
    state["failure_class"] = "ALLOCATION_BINDING_INVALID"
    if allocation_report["teacher_rows"] != len(groups):
        raise ReadoutError("allocation/teacher observed cardinality mismatch")
    groups_by_parent = [[] for _ in range(PARENTS)]
    group_lines_by_parent = [[] for _ in range(PARENTS)]
    semantics_by_parent = [[] for _ in range(PARENTS)]
    semantic_lines_by_parent = [[] for _ in range(PARENTS)]
    state["failure_class"] = "TEACHER_OBSERVATION_TRANSPORT_INVALID"
    for group, line in zip(groups, group_lines):
        parent_id = _text_int(group["parent_id"], "group parent_id", 0, PARENTS - 1)
        groups_by_parent[parent_id].append(group)
        group_lines_by_parent[parent_id].append(line)
    state["failure_class"] = "SEMANTIC_JOIN_INVALID"
    for semantic, line in zip(semantics, semantic_lines):
        parent_id = _integer(semantic.get("parent_id"), "semantic parent_id", 0, PARENTS - 1)
        semantics_by_parent[parent_id].append(semantic)
        semantic_lines_by_parent[parent_id].append(line)
    state["failure_class"] = "POPULATION_OR_CELL_INVALID"
    rich_raw, sufficient_raw, report_raw = build_from_components(
        code_sha=manifest["code_sha"], input_manifest_sha256=authenticated.manifest_sha256,
        selections=selections, selection_lines=selection_lines,
        groups_by_parent=groups_by_parent, group_lines_by_parent=group_lines_by_parent,
        semantics_by_parent=semantics_by_parent, semantic_lines_by_parent=semantic_lines_by_parent,
        allocations=allocations, allocation_lines=allocation_lines,
        receipts=receipts, receipt_lines=receipt_lines)
    # Re-authenticate after every payload parse and before the first write.  The
    # common helper rehashes the selection/teacher/tool graph; the four readout-
    # specific descriptors are rehashed explicitly below.
    authenticated_after = common.authenticate_common_manifest(
        args.input_manifest, args.expected_input_manifest_sha256,
        expected_schema=BUILD_INPUT_SCHEMA,
        exact_root_keys=frozenset({"allocation", "code_sha", "preregistration",
                                   "projection", "schema", "selection",
                                   "teacher_merge", "tools"}),
        exact_tool_keys=frozenset({"allocation_input", "projection", "readout",
                                   "statistics", "statistical_preflight_receipt"}))
    if authenticated_after.manifest_raw != authenticated.manifest_raw \
            or authenticated_after.files != authenticated.files:
        raise ReadoutError("common inputs changed during readout build")
    stable_specific = (
        common.verify_file_descriptor(
            base, allocation["input_jsonl"], "allocation.input_jsonl",
            extra_keys=frozenset({"rows", "row_schema"})),
        common.verify_file_descriptor(base, allocation["report"], "allocation.report"),
        common.verify_file_descriptor(
            base, projection["receipts_jsonl"], "projection.receipts_jsonl",
            extra_keys=frozenset({"rows", "row_schema"})),
        common.verify_file_descriptor(base, projection["manifest"], "projection.manifest"),
    )
    if stable_specific != (allocation_input, allocation_report_path,
                           projection_receipts, projection_manifest_path):
        raise ReadoutError("readout-specific inputs changed paths during build")
    state["publication_started"] = True
    _write_new_directory(args.out_dir, {
        "parent-stats-rich-v1.jsonl": rich_raw,
        "parent-stats-sufficient-v1.jsonl": sufficient_raw,
        "rich-to-sufficient-report-v1.json": report_raw,
    })


def build_command(args: argparse.Namespace) -> int:
    from jobs.tools import adaptive_sibling_b2_allocation_input as common

    _guard_build_destinations(args.input_manifest, args.out_dir, args.failure_receipt)
    try:
        input_raw = args.input_manifest.read_bytes()
    except OSError as exc:
        raise TechnicalIOError(f"cannot read build input manifest: {exc}") from exc
    actual_sha = sha256_bytes(input_raw)
    state: dict[str, object] = {
        "authenticated": False, "manifest_code_sha": None,
        "tool_binding_authenticated": False, "preregistration_authenticated": False,
        "publication_started": False,
    }
    failure: BuildValidationFailure
    try:
        _build_success(args, state)
        return 0
    except common.CommonAuthenticationError as exc:
        if exc.reason is not common.CommonAuthReason.INPUT_AUTHENTICATION_FAILED:
            raise
        failure = BuildValidationFailure("INPUT_AUTHENTICATION_FAILED")
    except BuildValidationFailure as exc:
        failure = exc
    except (TechnicalIOError, OutputSafetyError):
        raise
    except common.TechnicalIOError as exc:
        raise TechnicalIOError(str(exc)) from exc
    except common.OutputSafetyError as exc:
        raise OutputSafetyError(str(exc)) from exc
    except ReadoutError as exc:
        if state.get("publication_started") is True:
            raise
        failure_class = state.get("failure_class")
        if failure_class not in BUILD_FAILURE_STAGES:
            raise
        failure = BuildValidationFailure(str(failure_class))
        failure.__cause__ = exc
    receipt = _build_failure_receipt(
        failure=failure, expected_input_sha256=args.expected_input_manifest_sha256,
        actual_input_sha256=actual_sha,
        input_authenticated=bool(state["authenticated"]),
        manifest_code_sha=state["manifest_code_sha"],
        tool_binding_authenticated=bool(state["tool_binding_authenticated"]),
        preregistration_authenticated=bool(state["preregistration_authenticated"]))
    _publish_build_failure(args.failure_receipt, receipt)
    return 4


def _finalize_with_analyzer(*, code_sha: str, input_manifest_sha256: str,
                            rows: Sequence[statistics.ParentStatsSufficientV1],
                            support: Mapping[str, bool], out_dir: Path,
                            analyzer: Callable[..., dict[str, object]],
                            stability_check: Callable[[], None] | None = None) -> dict[str, object]:
    if not GIT_RE.fullmatch(code_sha):
        raise ReadoutError("terminal code SHA mismatch")
    _sha(input_manifest_sha256, "terminal input manifest SHA")
    support_keys = {"authentication_valid", "selection_valid", "teacher_valid",
                    "observations_valid", "projection_invariance_valid",
                    "rich_ledger_valid", "sufficient_projection_valid",
                    "statistics_support_valid"}
    _keys(dict(support), support_keys, "terminal support")
    checked_support = {key: _boolean(support[key], key) for key in support_keys}
    all_valid = all(checked_support.values())
    if all_valid and len(rows) != PARENTS:
        raise ReadoutError("terminal statistics require exactly 4000 parents")
    if out_dir.exists() or out_dir.is_symlink() or not out_dir.parent.resolve().is_dir():
        raise ReadoutError("terminal output directory must be absent below an existing parent")
    owned: dict[Path, tuple[int, int]] = {}
    out_dir.mkdir()
    stats_raw: bytes | None = None
    progress_raw: bytes | None = None
    analysis: dict[str, object] | None = None
    try:
        def publish_new(name: str, raw: bytes) -> None:
            final = out_dir / name
            temporary = out_dir / f"{name}.tmp"
            temp_identity = _write_exclusive(temporary, raw)
            owned[temporary] = temp_identity
            final_identity = _publish_new_from_owned_temp(
                temporary, final, raw, temp_identity=temp_identity)
            owned[final] = final_identity
            _unlink_owned(temporary, temp_identity)
            owned.pop(temporary, None)

        def publish_progress(raw: bytes) -> None:
            final = out_dir / "progress.json"
            temporary = out_dir / "progress.json.tmp"
            current_identity = owned.get(final)
            if current_identity is None:
                publish_new("progress.json", raw)
                return
            if _file_identity(final) != current_identity:
                raise OutputSafetyError("owned progress output identity changed")
            temp_identity = _write_exclusive(temporary, raw)
            owned[temporary] = temp_identity
            try:
                # Replacement is limited to the final file whose identity this
                # invocation created and just revalidated.
                os.replace(temporary, final)
            except OSError as exc:
                raise TechnicalIOError(f"cannot update progress output: {exc}") from exc
            owned.pop(temporary, None)
            owned[final] = temp_identity
            if _file_identity(final) != temp_identity or final.read_bytes() != raw:
                raise TechnicalIOError("progress output roundtrip mismatch")

        if all_valid:
            if stability_check is not None:
                stability_check()
            progress_value: dict[str, int] = {
                "completed_replications": 0,
                "total_replications": statistics.BOOTSTRAP_REPLICATIONS}

            def progress(value: dict[str, int]) -> None:
                nonlocal progress_value, progress_raw
                progress_value = dict(value)
                progress_raw = canonical_json_bytes(progress_value)
                publish_progress(progress_raw)

            analysis = analyzer(rows, progress_callback=progress)
            if stability_check is not None:
                stability_check()
            stats_raw = canonical_json_bytes(analysis)
            if progress_raw is None:
                progress_raw = canonical_json_bytes(progress_value)
                publish_progress(progress_raw)
        if analysis is None or analysis.get("status") != "VALID":
            verdict = "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1"
            evaluated = False if analysis is None else analysis.get("scientific_gates_evaluated") is True
            all_gates = None
        else:
            evaluated = analysis.get("scientific_gates_evaluated") is True
            gates = analysis.get("gates")
            if not evaluated or type(gates) is not dict or type(gates.get("all_passed")) is not bool:
                verdict = "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1"
                all_gates = None
            else:
                all_gates = gates["all_passed"]
                verdict = ("B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1" if all_gates
                           else "B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1")
        outputs = {"statistics": None, "progress": None}
        if stats_raw is not None and progress_raw is not None:
            publish_new("b2-statistics-v1.json", stats_raw)
            if (out_dir / "progress.json").read_bytes() != progress_raw:
                raise ReadoutError("progress final bytes mismatch")
            outputs = {
                "statistics": {"local_name": "b2-statistics-v1.json", "sha256": sha256_bytes(stats_raw),
                               "size_bytes": len(stats_raw)},
                "progress": {"local_name": "progress.json", "sha256": sha256_bytes(progress_raw),
                             "size_bytes": len(progress_raw)},
            }
        report = {
            "schema": TERMINAL_SCHEMA, "code_sha": code_sha,
            "input_manifest_sha256": input_manifest_sha256,
            "outputs": outputs, "support": {**checked_support, "all_valid": all_valid},
            "statistics": {"status": analysis.get("status") if analysis else None,
                           "scientific_gates_evaluated": evaluated,
                           "all_gates_passed": all_gates},
            "actions": {"searches": 0, "fits": 0, "games": 0, "promotions": 0,
                        "bakes": 0, "automatic_downstream_jobs": 0},
            "verdict": verdict,
        }
        report_raw = canonical_json_bytes(report)
        publish_new("b2-terminal-report-v1.json", report_raw)
        expected_names = {"b2-terminal-report-v1.json"}
        if stats_raw is not None:
            expected_names.update({"b2-statistics-v1.json", "progress.json"})
        if {path.name for path in out_dir.iterdir()} != expected_names:
            raise ReadoutError("unexpected file appeared in terminal output directory")
        return report
    except BaseException:
        for path, identity in tuple(owned.items()):
            _unlink_owned(path, identity)
        try:
            out_dir.rmdir()
        except OSError:
            pass
        raise


def finalize_from_authenticated(*, code_sha: str, input_manifest_sha256: str,
                                rows: Sequence[statistics.ParentStatsSufficientV1],
                                support: Mapping[str, bool], out_dir: Path,
                                stability_check: Callable[[], None] | None = None) -> dict[str, object]:
    """Finalize through the fixed public R=200000 statistical implementation."""
    return _finalize_with_analyzer(
        code_sha=code_sha, input_manifest_sha256=input_manifest_sha256,
        rows=rows, support=support, out_dir=out_dir,
        analyzer=statistics.analyze_parent_stats, stability_check=stability_check)


def _finalize_from_authenticated_for_test(*, code_sha: str,
                                          input_manifest_sha256: str,
                                          rows: Sequence[statistics.ParentStatsSufficientV1],
                                          support: Mapping[str, bool], out_dir: Path,
                                          analyzer: Callable[..., dict[str, object]]) -> dict[str, object]:
    """Private synthetic-fixture hook; production CLI cannot select an analyzer."""
    return _finalize_with_analyzer(
        code_sha=code_sha, input_manifest_sha256=input_manifest_sha256,
        rows=rows, support=support, out_dir=out_dir, analyzer=analyzer)


def _read_control(path: Path) -> dict[str, Any]:
    return read_canonical_json(path)[0]


def _legacy_equivalence_valid(legacy: Mapping[str, Any]) -> bool:
    equivalence_report = legacy.get("equivalence_report")
    equivalence = equivalence_report.get("equivalence") \
        if type(equivalence_report) is dict else None
    barrier = equivalence_report.get("information_barrier") \
        if type(equivalence_report) is dict else None
    return (
        legacy.get("schema") == "jass.decision_math.b2_legacy_equivalence_publisher.v1"
        and legacy.get("verdict") == "B1_HISTORICAL_PROJECTION_EQUIVALENCE_COMPLETE"
        and type(equivalence_report) is dict
        and equivalence_report.get("schema")
            == "jass.adaptive_sibling_b2_legacy_equivalence.v1"
        and equivalence_report.get("verdict")
            == "B1_HISTORICAL_PROJECTION_EQUIVALENCE_COMPLETE"
        and type(equivalence) is dict
        and all(type(equivalence.get(key)) is int and equivalence.get(key) == 8_000 for key in (
            "parents_compared", "allocation_decision_matches", "final_b1_result_matches"))
        and type(barrier) is dict
        and barrier.get("allocation_hash_excludes_q200_values") is True
        and type(barrier.get("q200_fields_in_projection_decision")) is int
        and barrier.get("q200_fields_in_projection_decision") == 0
        and all(type(barrier.get(key)) is int and barrier.get(key) == 0 for key in (
            "q200_value_reads", "q200_label_reads", "q200_policy_reads",
            "q200_policy_branches", "nodes200k_policy_reads",
            "nodes200k_policy_branches", "nodes200k_preseal_aggregation_reads")))


def _historical_receipt_valid(receipt: Mapping[str, Any]) -> bool:
    files = receipt.get("files")
    expected_paths = {
        "artefacts/historical-parent-exclusion-manifest.json",
        "artefacts/historical-parent-canonical-union.txt",
    }
    if type(files) is not list or len(files) != 2:
        return False
    seen: set[str] = set()
    for value in files:
        if type(value) is not dict or set(value) != {
                "path", "local_name", "sha256", "size_bytes"}:
            return False
        path = value["path"]
        if type(path) is not str or path not in expected_paths or path in seen:
            return False
        seen.add(path)
        if type(value["local_name"]) is not str or not value["local_name"] \
                or Path(value["local_name"]).name != value["local_name"] \
                or type(value["sha256"]) is not str or not SHA_RE.fullmatch(value["sha256"]) \
                or type(value["size_bytes"]) is not int or value["size_bytes"] <= 0:
            return False
    return (
        seen == expected_paths
        and type(receipt.get("schema")) is int and receipt.get("schema") == 1
        and receipt.get("state") == "verified"
        and receipt.get("result_state") == "completed"
        and type(receipt.get("exit_code")) is int and receipt.get("exit_code") == 0
        and receipt.get("job_id")
            == "cpx62-1773-l3-decision-math-b2-historical-identities-v1"
        and type(receipt.get("attempt_id")) is str and bool(receipt["attempt_id"])
        and type(receipt.get("prefix")) is str and bool(receipt["prefix"])
        and type(receipt.get("code_sha")) is str and bool(GIT_RE.fullmatch(receipt["code_sha"])))


def _preflight_support_valid(receipt: Mapping[str, Any], runtime: Mapping[str, Any]) -> bool:
    observed_runtime = receipt.get("runtime")
    return (
        receipt.get("schema") == "jass.adaptive_sibling_b2_statistical_preflight.v1"
        and receipt.get("status") == "VALID"
        and receipt.get("synthetic_only") is True
        and type(receipt.get("scientific_parents")) is int
        and receipt.get("scientific_parents") == 0
        and type(receipt.get("bootstrap_replications")) is int
        and receipt.get("bootstrap_replications") == statistics.BOOTSTRAP_REPLICATIONS
        and type(receipt.get("accepted_draws")) is int
        and receipt.get("accepted_draws") == statistics.BOOTSTRAP_REPLICATIONS * PARENTS
        and receipt.get("runtime_matches_kernel_environment") is True
        and type(observed_runtime) is dict
        and all(observed_runtime.get(key) == value
                and type(observed_runtime.get(key)) is type(value)
                for key, value in runtime.items())
        and type(observed_runtime.get("pid")) is int and observed_runtime.get("pid") > 0
        and type(receipt.get("fresh_data_reads")) is int
        and receipt.get("fresh_data_reads") == 0
        and type(receipt.get("fits")) is int and receipt.get("fits") == 0
        and type(receipt.get("games")) is int and receipt.get("games") == 0
        and receipt.get("promotion") is False and receipt.get("bake") is False
        and receipt.get("gate_exercise_only") is True
        and receipt.get("scientific_verdict") is None)


def _runtime_matches_current(runtime: Mapping[str, Any]) -> bool:
    """Match the seven authenticated runtime fields; PID is invocation-specific."""
    try:
        observed = statistics.runtime_environment()
    except statistics.StatisticsContractError:
        return False
    expected_keys = {"python_executable", "python_implementation", "python_version",
                     "platform", "machine", "libc", "nproc"}
    return set(runtime) == expected_keys and all(
        _exact_json_equal(observed.get(key), runtime[key]) for key in expected_keys)


def _manifest_file_descriptors(value: object) -> list[Mapping[str, Any]]:
    """Collect declared FileV1 objects from an already authenticated manifest."""
    found: list[Mapping[str, Any]] = []
    if type(value) is dict:
        if {"local_name", "sha256", "size_bytes"}.issubset(value):
            found.append(value)
        for child in value.values():
            found.extend(_manifest_file_descriptors(child))
    elif type(value) is list:
        for child in value:
            found.extend(_manifest_file_descriptors(child))
    return found


def _terminal_identity_snapshot(input_manifest: Path, manifest: Mapping[str, Any],
                                base: Path) -> dict[str, tuple[int, int, str, int]]:
    """Bind every terminal/build manifest file to bytes and one filesystem identity."""
    rich_descriptor = _keys(
        manifest["rich_input_manifest"], {"local_name", "sha256", "size_bytes"},
        "rich input manifest descriptor")
    rich_path = base / rich_descriptor["local_name"]
    rich_manifest, rich_raw = read_canonical_json(rich_path)
    if sha256_bytes(rich_raw) != rich_descriptor["sha256"] \
            or len(rich_raw) != rich_descriptor["size_bytes"]:
        raise ReadoutError("rich input manifest descriptor changed")
    descriptors = [*_manifest_file_descriptors(manifest),
                   *_manifest_file_descriptors(rich_manifest)]
    snapshot: dict[str, tuple[int, int, str, int]] = {}
    identities: dict[tuple[int, int], str] = {}
    for descriptor in descriptors:
        local_name = descriptor.get("local_name")
        expected_sha = descriptor.get("sha256")
        expected_size = descriptor.get("size_bytes")
        if type(local_name) is not str or not local_name or Path(local_name).name != local_name \
                or type(expected_sha) is not str or not SHA_RE.fullmatch(expected_sha) \
                or type(expected_size) is not int or expected_size < 0:
            raise ReadoutError("terminal manifest FileV1 shape mismatch")
        path = base / local_name
        identity = _file_identity(path)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise TechnicalIOError(f"cannot snapshot terminal input {path}: {exc}") from exc
        if len(raw) != expected_size or sha256_bytes(raw) != expected_sha:
            raise ReadoutError(f"terminal input descriptor changed: {local_name}")
        key = _path_key(path)
        value = (*identity, expected_sha, expected_size)
        if key in snapshot and snapshot[key] != value:
            raise ReadoutError("terminal manifests disagree on a file descriptor")
        other = identities.get(identity)
        if other is not None and other != key:
            raise OutputSafetyError("terminal input files are samefile aliases")
        snapshot[key] = value
        identities[identity] = key
    input_identity = _file_identity(input_manifest)
    try:
        input_raw = input_manifest.read_bytes()
    except OSError as exc:
        raise TechnicalIOError(f"cannot snapshot terminal manifest: {exc}") from exc
    input_key = _path_key(input_manifest)
    if input_identity in identities and identities[input_identity] != input_key:
        raise OutputSafetyError("terminal manifest is a samefile alias")
    snapshot[input_key] = (*input_identity, sha256_bytes(input_raw), len(input_raw))
    return snapshot


def _descriptor_shape(value: object, *, extras: Mapping[str, object] | None = None) -> bool:
    extra = {} if extras is None else dict(extras)
    if type(value) is not dict or set(value) != {"local_name", "sha256", "size_bytes", *extra}:
        return False
    local_name = value.get("local_name")
    if type(local_name) is not str or not local_name or Path(local_name).name != local_name:
        return False
    if type(value.get("sha256")) is not str or not SHA_RE.fullmatch(value["sha256"]):
        return False
    if type(value.get("size_bytes")) is not int or value["size_bytes"] <= 0:
        return False
    return all(type(value.get(key)) is type(expected) and value.get(key) == expected
               for key, expected in extra.items())


def _teacher_controls_valid(teacher: Mapping[str, Any], publication: Mapping[str, Any],
                            native: Mapping[str, Any], *, code_sha: str,
                            report_descriptor: Mapping[str, Any],
                            selection_report_descriptor: Mapping[str, Any]) -> bool:
    outputs = teacher.get("outputs")
    counters = teacher.get("counters")
    native_wrapper = teacher.get("native_verification")
    artifacts = publication.get("artifacts")
    if type(outputs) is not dict or type(counters) is not dict \
            or type(native_wrapper) is not dict or type(artifacts) is not dict:
        return False
    if set(outputs) != {"children_jnnw", "groups_tsv", "semantic_actions"} \
            or set(native_wrapper) != {"receipt", "sha256", "size_bytes"} \
            or set(publication) != {"artifacts", "byte_roundtrip_verified", "code_sha",
                                    "input_manifest", "schema"} \
            or set(artifacts) != {"children_jnnw", "groups_tsv", "semantic_actions",
                                  "merge_report"}:
        return False
    teacher_rows = outputs.get("groups_tsv", {}).get("rows") \
        if type(outputs.get("groups_tsv")) is dict else None
    return (
        teacher.get("schema") == MERGE_REPORT_SCHEMA
        and teacher.get("code_sha") == code_sha
        and publication.get("schema") == "jass.adaptive_sibling_b2_teacher_merge_publication.v1"
        and publication.get("code_sha") == code_sha
        and publication.get("byte_roundtrip_verified") is True
        and _descriptor_shape(teacher.get("input_manifest"))
        and _descriptor_shape(outputs.get("children_jnnw"), extras={
            "records": teacher_rows, "record_size_bytes": 38})
        and _descriptor_shape(outputs.get("groups_tsv"), extras={"rows": teacher_rows})
        and _descriptor_shape(outputs.get("semantic_actions"), extras={
            "rows": teacher_rows, "row_schema": SEMANTIC_SCHEMA})
        and _descriptor_shape(report_descriptor)
        and _exact_json_equal(publication.get("input_manifest"), teacher.get("input_manifest"))
        and _exact_json_equal(artifacts.get("children_jnnw"), {
            key: outputs["children_jnnw"][key]
            for key in ("local_name", "sha256", "size_bytes")})
        and _exact_json_equal(artifacts.get("groups_tsv"), {
            key: outputs["groups_tsv"][key]
            for key in ("local_name", "sha256", "size_bytes")})
        and _exact_json_equal(artifacts.get("semantic_actions"), {
            key: outputs["semantic_actions"][key]
            for key in ("local_name", "sha256", "size_bytes")})
        and _exact_json_equal(artifacts.get("merge_report"), report_descriptor)
        and type(teacher.get("selection")) is dict
        and _exact_json_equal(teacher["selection"].get("report"), selection_report_descriptor)
        and _exact_json_equal(native_wrapper.get("receipt"), native)
        and type(native_wrapper.get("sha256")) is str
        and native_wrapper.get("sha256") == sha256_bytes(canonical_json_bytes(dict(native)))
        and type(native_wrapper.get("size_bytes")) is int
        and native_wrapper.get("size_bytes") == len(canonical_json_bytes(dict(native)))
        and native.get("schema")
            == "jass.adaptive_sibling_b2_teacher_merge_native_verification.v1"
        and native.get("verification_complete") is True
        and type(teacher_rows) is int and 8_000 <= teacher_rows <= 64_000
        and type(counters.get("parents")) is int and counters.get("parents") == PARENTS
        and type(counters.get("groups_rows")) is int and counters.get("groups_rows") == teacher_rows
        and type(counters.get("semantic_actions")) is int
        and counters.get("semantic_actions") == teacher_rows
        and all(type(counters.get(key)) is int and counters.get(key) == 0 for key in (
            "missing_actions", "extra_actions", "duplicate_semantic_actions"))
        and type(native.get("actions_verified")) is int
        and native.get("actions_verified") == teacher_rows
        and type(native.get("catalogues_verified")) is int
        and native.get("catalogues_verified") == PARENTS
        and all(type(native.get(key)) is int and native.get(key) == 0 for key in (
            "missing_actions", "extra_actions", "duplicate_semantic_actions")))


def _terminal_inputs(manifest: Mapping[str, Any], base: Path) -> tuple[dict[str, bool], list[statistics.ParentStatsSufficientV1]]:
    """Authenticate terminal inputs and derive support without evaluating gates."""
    from jobs.tools import adaptive_sibling_b2_allocation_input as common

    flags = {"authentication_valid": False, "selection_valid": False,
             "teacher_valid": False, "observations_valid": False,
             "projection_invariance_valid": False, "rich_ledger_valid": False,
             "sufficient_projection_valid": False, "statistics_support_valid": False}
    try:
        rich_input_path = common.verify_file_descriptor(
            base, manifest["rich_input_manifest"], "rich input manifest")
        rich_authenticated = common.authenticate_common_manifest(
            rich_input_path, manifest["rich_input_manifest"]["sha256"],
            expected_schema=BUILD_INPUT_SCHEMA,
            exact_root_keys=frozenset({"allocation", "code_sha", "preregistration",
                                       "projection", "schema", "selection",
                                       "teacher_merge", "tools"}),
            exact_tool_keys=frozenset({"allocation_input", "projection", "readout",
                                       "statistics", "statistical_preflight_receipt"}))
        rich_manifest = rich_authenticated.manifest
        if rich_manifest["code_sha"] != manifest["code_sha"]:
            raise ReadoutError("terminal/rich input code SHA mismatch")
        prereg = _keys(manifest["preregistration"], {"file", "schema"}, "preregistration")
        if prereg["schema"] != common.PREREGISTRATION_SCHEMA:
            raise ReadoutError("preregistration schema declaration mismatch")
        prereg_path = common.verify_file_descriptor(base, prereg["file"], "preregistration.file")
        if prereg_path.suffix.lower() != ".md":
            raise ReadoutError("preregistration is not Markdown")
        if not _exact_json_equal(prereg, rich_manifest["preregistration"]):
            raise ReadoutError("terminal/rich preregistration mismatch")
        rich_report_path = common.verify_file_descriptor(
            base, manifest["rich_to_sufficient_report"], "rich-to-sufficient report")
        rich_path = common.verify_file_descriptor(
            base, manifest["rich_jsonl"], "rich JSONL",
            extra_keys=frozenset({"rows", "row_schema"}))
        sufficient_path = common.verify_file_descriptor(
            base, manifest["sufficient_jsonl"], "sufficient JSONL",
            extra_keys=frozenset({"rows", "row_schema"}))
        if manifest["rich_jsonl"]["rows"] != PARENTS \
                or manifest["rich_jsonl"]["row_schema"] != RICH_SCHEMA \
                or manifest["sufficient_jsonl"]["rows"] != PARENTS \
                or manifest["sufficient_jsonl"]["row_schema"] != statistics.INPUT_SCHEMA:
            raise ReadoutError("terminal rich/sufficient descriptor mismatch")
        statistics_tool = common.verify_file_descriptor(
            base, manifest["statistics_tool"], "statistics tool")
        terminal_tool = common.verify_file_descriptor(base, manifest["terminal_tool"], "terminal tool")
        if common.sha256_file(statistics_tool) != common.sha256_file(Path(statistics.__file__).resolve()) \
                or common.sha256_file(terminal_tool) != common.sha256_file(Path(__file__).resolve()):
            raise ReadoutError("terminal tool implementation hash mismatch")
        if not _exact_json_equal(manifest["statistics_tool"], rich_manifest["tools"]["statistics"]) \
                or not _exact_json_equal(manifest["terminal_tool"], rich_manifest["tools"]["readout"]):
            raise ReadoutError("terminal tools differ from rich build manifest")
        preflight = _keys(manifest["preflight"], {"receipt", "verdict", "runtime"}, "preflight")
        preflight_path = common.verify_file_descriptor(base, preflight["receipt"], "preflight receipt")
        if preflight["verdict"] != PREFLIGHT_VERDICT:
            raise ReadoutError("preflight verdict mismatch")
        if not _exact_json_equal(preflight["receipt"],
                                 rich_manifest["tools"]["statistical_preflight_receipt"]):
            raise ReadoutError("terminal preflight differs from rich build manifest")
        runtime = _keys(preflight["runtime"], {"python_executable", "python_implementation",
                                               "python_version", "platform", "machine", "libc",
                                               "nproc"}, "preflight runtime")
        if runtime["python_executable"] != "/usr/bin/python3" \
                or runtime["python_implementation"] != "CPython" \
                or runtime["python_version"] != "3.14.4" \
                or type(runtime["platform"]) is not str or not runtime["platform"] \
                or runtime["machine"] != "x86_64" or runtime["libc"] != ["glibc", "2.43"] \
                or runtime["nproc"] != 16 or type(runtime["nproc"]) is not int:
            raise ReadoutError("preflight runtime mismatch")
        support_manifest = _keys(manifest["support"], {
            "historical_exclusion_receipt", "source_manifest", "selection_report",
            "teacher_merge_report", "teacher_merge_publication_receipt",
            "teacher_native_verification_receipt", "allocation_input_report",
            "projection_manifest", "legacy_equivalence_terminal_summary"}, "support")
        support_paths = {name: common.verify_file_descriptor(base, descriptor, f"support.{name}")
                         for name, descriptor in support_manifest.items()}
        bindings = {
            "selection_report": rich_manifest["selection"]["report"],
            "teacher_merge_report": rich_manifest["teacher_merge"]["report"],
            "teacher_merge_publication_receipt":
                rich_manifest["teacher_merge"]["publication_receipt"],
            "teacher_native_verification_receipt":
                rich_manifest["teacher_merge"]["native_verification_receipt"],
            "allocation_input_report": rich_manifest["allocation"]["report"],
            "projection_manifest": rich_manifest["projection"]["manifest"],
        }
        if any(not _exact_json_equal(support_manifest[name], descriptor)
               for name, descriptor in bindings.items()):
            raise ReadoutError("terminal support differs from rich build manifest")
        protected = [rich_input_path, prereg_path, rich_report_path, rich_path, sufficient_path,
                      statistics_tool, terminal_tool, preflight_path, *support_paths.values()]
        if len({_path_key(path) for path in protected}) != len(protected):
            raise ReadoutError("terminal inputs contain path aliases")
        controls = {name: _read_control(path) for name, path in support_paths.items()}
        preflight_receipt = _read_control(preflight_path)
        rich_report = _read_control(rich_report_path)
        if rich_report.get("input_manifest_sha256") != rich_authenticated.manifest_sha256:
            raise ReadoutError("rich report is not bound to terminal rich input manifest")
        flags["authentication_valid"] = True
    except (TechnicalIOError, OutputSafetyError):
        raise
    except common.TechnicalIOError as exc:
        raise TechnicalIOError(str(exc)) from exc
    except common.OutputSafetyError as exc:
        raise OutputSafetyError(str(exc)) from exc
    except (ReadoutError, common.AllocationInputError, OSError, KeyError, TypeError, ValueError) as exc:
        raise ReadoutError(f"terminal input authentication failed: {exc}") from exc

    historical = controls["historical_exclusion_receipt"]
    source = controls["source_manifest"]
    selection = controls["selection_report"]
    try:
        source_environment = source.get("producer_environment")
        source_barrier = source.get("producer_barrier")
        source_shards = source.get("shards")
        selection_exclusion = selection.get("exclusion")
        selection_cells = selection.get("selected_by_phase_stm")
        flags["selection_valid"] = (
            _historical_receipt_valid(historical)
            and source.get("schema") == "jass.adaptive_sibling_b2_source_preparation.v1"
            and type(source_environment) is dict
            and source_environment.get("transmitted_names") == []
            and source_environment.get("jass_prefixed_environment") == []
            and type(source_barrier) is dict
            and source_barrier.get("passed") is True
            and type(source_barrier.get("child_count")) is int
            and source_barrier.get("child_count") == 16
            and type(source_barrier.get("alive_barrier_count")) is int
            and source_barrier.get("alive_barrier_count") == 16
            and type(source_shards) is list and len(source_shards) == 16
            and selection.get("schema") == SELECTION_REPORT_SCHEMA
            and selection.get("code_sha") == manifest["code_sha"]
            and selection.get("source_manifest_sha256")
                == support_manifest["source_manifest"]["sha256"]
            and type(selection_exclusion) is dict
            and selection_exclusion.get("receipt_sha256")
                == support_manifest["historical_exclusion_receipt"]["sha256"]
            and selection.get("selected") == PARENTS and type(selection.get("selected")) is int
            and type(selection_cells) is dict and set(selection_cells) == set(CELL_ORDER)
            and all(type(selection_cells.get(cell)) is int
                    and selection_cells.get(cell) == CELL_SIZE for cell in CELL_ORDER)
            and selection.get("target_blind") is True
            and all(type(selection.get(key)) is int and selection.get(key) == 0 for key in (
                "forbidden_overlap", "raw_source_jnnw_inputs", "source_score_bytes_read",
                "source_wdl_bytes_read", "source_labels_read",
                "output_target_nonzero_records")))
    except (AttributeError, TypeError):
        flags["selection_valid"] = False

    teacher = controls["teacher_merge_report"]
    publication = controls["teacher_merge_publication_receipt"]
    native = controls["teacher_native_verification_receipt"]
    flags["teacher_valid"] = _teacher_controls_valid(
        teacher, publication, native, code_sha=manifest["code_sha"],
        report_descriptor=support_manifest["teacher_merge_report"],
        selection_report_descriptor=support_manifest["selection_report"])

    allocation_report = controls["allocation_input_report"]
    projection_manifest = controls["projection_manifest"]
    legacy = controls["legacy_equivalence_terminal_summary"]
    flags["projection_invariance_valid"] = (
        _legacy_equivalence_valid(legacy)
        and allocation_report.get("schema") == ALLOCATION_REPORT_SCHEMA
        and allocation_report.get("status") == "VALID"
        and all(type(allocation_report.get(key)) is int and allocation_report.get(key) == 0 for key in (
            "q200_value_reads", "q200_label_reads", "q200_branches",
            "q200_value_decodes", "q200_metadata_decodes", "nodes200k_policy_reads",
            "nodes200k_policy_branches", "searches", "fits", "games", "promotions", "bakes"))
        and projection_manifest.get("schema") == PROJECTION_MANIFEST_SCHEMA
        and type(projection_manifest.get("parents")) is int
        and projection_manifest.get("parents") == PARENTS
        and all(type(projection_manifest.get(key)) is int and projection_manifest.get(key) == 0 for key in (
            "q200_value_reads", "q200_label_reads", "q200_branches",
            "nodes200k_policy_reads", "nodes200k_policy_branches",
            "nodes200k_preseal_aggregation_reads", "searches", "fits", "strength_games")))

    try:
        rich_values, rich_lines, rich_raw = _parse_jsonl(rich_path, rows=PARENTS)
        try:
            sufficient_rows, sufficient_raw = statistics.load_parent_stats_sufficient_jsonl(
                sufficient_path)
        except statistics.StatisticsContractError:
            try:
                sufficient_path.read_bytes()
            except OSError as exc:
                raise TechnicalIOError(
                    f"cannot read sufficient JSONL during public load: {exc}") from exc
            raise
        statistics.validate_parent_population(sufficient_rows)
        sufficient_lines = sufficient_raw.splitlines(keepends=True)
        if _keys(rich_report, {"schema", "code_sha", "input_manifest_sha256", "outputs",
                               "ordered_parent_ids_sha256", "row_hashes", "population",
                               "observation_validation", "ledger", "barrier", "actions",
                               "support_inputs_valid", "status"}, "rich report")["schema"] != REPORT_SCHEMA:
            raise ReadoutError("rich report schema mismatch")
        if not _exact_json_equal(rich_report["outputs"], {
                "rich": manifest["rich_jsonl"],
                "sufficient": manifest["sufficient_jsonl"]}):
            raise ReadoutError("rich report output descriptors mismatch")
        if rich_report["code_sha"] != manifest["code_sha"]:
            raise ReadoutError("rich report code SHA mismatch")
        _sha(rich_report["input_manifest_sha256"], "rich report input manifest SHA")
        if rich_report["ordered_parent_ids_sha256"] != sha256_bytes(
                b"".join(canonical_json_bytes(index) for index in range(PARENTS))):
            raise ReadoutError("ordered parent IDs hash mismatch")
        row_hashes = rich_report["row_hashes"]
        if type(row_hashes) is not list or len(row_hashes) != PARENTS:
            raise ReadoutError("rich row hash catalogue mismatch")
        projected = []
        for parent_id, (rich, parsed, rich_line, sufficient_line, hashes) in enumerate(
                zip(rich_values, sufficient_rows, rich_lines, sufficient_lines, row_hashes)):
            row = sufficient_from_rich(rich)
            if not _exact_json_equal(row.to_mapping(), parsed.to_mapping()) \
                    or parsed.parent_id != parent_id:
                raise ReadoutError("rich-to-sufficient row mismatch")
            if not _exact_json_equal(hashes, {
                    "parent_id": parent_id,
                    "rich_line_sha256": sha256_bytes(rich_line),
                    "sufficient_line_sha256": sha256_bytes(sufficient_line)}):
                raise ReadoutError("rich row hash mismatch")
            projected.append(parsed)
        if sha256_bytes(rich_raw) != manifest["rich_jsonl"]["sha256"] \
                or sha256_bytes(sufficient_raw) != manifest["sufficient_jsonl"]["sha256"]:
            raise ReadoutError("terminal JSONL descriptor hash mismatch")
        teacher_rows_recomputed = _checked_sum(
            (_integer(value["siblings"]["count"], "siblings.count", 2, 16)
             for value in rich_values), "teacher row count")
        exact_observations = 3 * _checked_sum(
            (_integer(value["siblings"]["exact_count"], "siblings.exact_count", 0, 16)
             for value in rich_values), "exact observation rows")
        observation_counts = {
            "total": 3 * teacher_rows_recomputed,
            "transport_valid": 3 * teacher_rows_recomputed,
            "nonexact_support_valid": 3 * teacher_rows_recomputed - exact_observations,
            "exact_transport_valid": exact_observations,
            "exact_score_band_classifications": 0,
            "exact_score_family_classifications": 0,
            "exact_score_endpoint_uses": 0,
        }
        expected_report = _build_report(
            manifest["code_sha"], rich_report["input_manifest_sha256"],
            rich_lines, sufficient_lines, rich_values, observation_counts,
            teacher_rows_recomputed)
        if not _exact_json_equal(rich_report, expected_report):
            raise ReadoutError("rich-to-sufficient report is not reproducible from payloads")
        observation = rich_report["observation_validation"]
        ledger = rich_report["ledger"]
        barrier = rich_report["barrier"]
        population = rich_report["population"]
        flags["observations_valid"] = (
            observation.get("invalid") == 0
            and observation.get("total") == 3 * population.get("teacher_rows", -1)
            and observation.get("transport_valid") == observation.get("total")
            and observation.get("nonexact_support_valid", -1)
                + observation.get("exact_transport_valid", -1) == observation.get("total")
            and observation.get("exact_score_band_classifications") == 0
            and observation.get("exact_score_family_classifications") == 0
            and observation.get("exact_score_endpoint_uses") == 0)
        flags["rich_ledger_valid"] = (
            rich_report.get("status") == "VALID" and rich_report.get("support_inputs_valid") is True
            and population.get("parents") == PARENTS
            and _exact_json_equal(
                population.get("cells"), {cell: CELL_SIZE for cell in CELL_ORDER})
            and ledger.get("unclassified") == 0 and ledger.get("first_level_sum") == PARENTS
            and ledger.get("subcategory_sum") == ledger.get("value_inequivalent"))
        flags["sufficient_projection_valid"] = len(projected) == PARENTS
        flags["projection_invariance_valid"] = flags["projection_invariance_valid"] and (
            _exact_json_equal(barrier, {
                "allocation_decisions_recomputed": 0,
                "allocation_q200_value_reads": 0, "allocation_q200_label_reads": 0,
                "allocation_q200_branches": 0,
                "postseal_q200_score_decodes": population.get("teacher_rows")}))
        rows = projected
    except (TechnicalIOError, OutputSafetyError):
        raise
    except (ReadoutError, statistics.StatisticsContractError, KeyError, TypeError, ValueError):
        rows = []

    flags["statistics_support_valid"] = (
        _preflight_support_valid(preflight_receipt, runtime)
        and _runtime_matches_current(runtime))
    return flags, rows


def finalize_command(args: argparse.Namespace) -> None:
    manifest, raw = read_canonical_json(args.input_manifest)
    if sha256_bytes(raw) != args.expected_input_manifest_sha256:
        raise ReadoutError("terminal input manifest external SHA mismatch")
    expected_root = {"schema", "code_sha", "preregistration", "rich_to_sufficient_report",
                     "rich_input_manifest", "rich_jsonl", "sufficient_jsonl",
                     "statistics_tool", "terminal_tool", "preflight", "support"}
    _keys(manifest, expected_root, "terminal input manifest")
    if manifest["schema"] != TERMINAL_INPUT_SCHEMA or not GIT_RE.fullmatch(manifest["code_sha"]):
        raise ReadoutError("terminal input schema/code mismatch")
    base = args.input_manifest.resolve().parent
    support, rows = _terminal_inputs(manifest, base)
    initial_snapshot = _terminal_identity_snapshot(args.input_manifest, manifest, base)

    def stability_check() -> None:
        current_manifest, current_raw = read_canonical_json(args.input_manifest)
        if current_raw != raw or not _exact_json_equal(current_manifest, manifest):
            raise OutputSafetyError("terminal input manifest changed during finalize")
        current_support, current_rows = _terminal_inputs(current_manifest, base)
        if not _exact_json_equal(current_support, support) \
                or len(current_rows) != len(rows) \
                or any(not _exact_json_equal(left.to_mapping(), right.to_mapping())
                       for left, right in zip(current_rows, rows)):
            raise OutputSafetyError("terminal authenticated inputs changed during finalize")
        if _terminal_identity_snapshot(args.input_manifest, current_manifest, base) \
                != initial_snapshot:
            raise OutputSafetyError("terminal input identity changed during finalize")

    finalize_from_authenticated(code_sha=manifest["code_sha"],
                                input_manifest_sha256=sha256_bytes(raw), rows=rows,
                                support=support, out_dir=args.out_dir,
                                stability_check=stability_check)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    finalize = commands.add_parser("finalize")
    for command in (build, finalize):
        command.add_argument("--input-manifest", type=Path, required=True)
        command.add_argument("--expected-input-manifest-sha256", required=True)
        command.add_argument("--out-dir", type=Path, required=True)
    build.add_argument("--failure-receipt", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not SHA_RE.fullmatch(args.expected_input_manifest_sha256):
        raise ReadoutError("expected input manifest SHA must be lowercase SHA256")
    if args.command == "build":
        return build_command(args)
    finalize_command(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReadoutError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
