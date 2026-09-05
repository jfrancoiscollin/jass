#!/usr/bin/env python3
"""Build the sealed B2 allocation input without decoding q200 observations.

The module authenticates the prospective selection and teacher-merge chain,
then emits only the closed input accepted by adaptive_sibling_b2_projection.
The full teacher TSV is hashed, but its q200 score/depth/stop/elapsed/PV tokens
remain opaque.  ``nodes200k`` is the sole typed q200-stage field and is a cost.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


if __package__ in (None, ""):
    _repo = Path(__file__).resolve().parents[2]
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))

from jobs.tools import adaptive_sibling_b2_exclusions as exclusions  # noqa: E402
from jobs.tools import adaptive_sibling_b2_projection as projection  # noqa: E402


INPUT_SCHEMA = "jass.adaptive_sibling_b2_allocation_inputs.v1"
REPORT_SCHEMA = "jass.adaptive_sibling_b2_allocation_input_report.v1"
PREREGISTRATION_SCHEMA = "jass.pr771_b2_preregistration.v1"
SELECTION_SCHEMA = "jass.adaptive_sibling_b2_target_blind_selection.v1"
MERGE_SCHEMA = "jass.adaptive_sibling_b2_teacher_merge.v1"
MERGE_PUBLICATION_SCHEMA = "jass.adaptive_sibling_b2_teacher_merge_publication.v1"
NATIVE_SCHEMA = "jass.adaptive_sibling_b2_teacher_merge_native_verification.v1"
SEMANTIC_SCHEMA = "jass.adaptive_sibling_b2_semantic_action.v1"
LEGACY_SCHEMA = "jass.adaptive_sibling_b2_legacy_equivalence.v1"
LEGACY_VERDICT = "B1_HISTORICAL_PROJECTION_EQUIVALENCE_COMPLETE"

PARENT_COUNT = 4_000
CELL_QUOTA = 500
CELL_ORDER = (
    "P0_stm0", "P0_stm1", "P1_stm0", "P1_stm1",
    "P2_stm0", "P2_stm1", "P3_stm0", "P3_stm1",
)
PHASE_BOUNDS = {"P0": (30, 40), "P1": (20, 29), "P2": (12, 19), "P3": (9, 11)}
UINT64_MAX = (1 << 64) - 1
INT64_MAX = (1 << 63) - 1
INT32_MIN, INT32_MAX = -(1 << 31), (1 << 31) - 1
PLAYABLE_MASK = (1 << 50) - 1

SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
GIT_RE = re.compile(r"[0-9a-f]{40}\Z")
UINT_RE = re.compile(rb"0|[1-9][0-9]*\Z")
SINT_RE = re.compile(rb"0|-?[1-9][0-9]*\Z")
FINGERPRINT_RE = re.compile(r"[0-9a-f]{13}(?::[0-9a-f]{13}){3}:[01]\Z")

SELECTION_FIELDS = (
    "parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm",
    "pieces", "legal_moves", "phase", "source_shard", "source_row_index",
    "selection_hash",
)

GROUP_FIELDS = (
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
)
GROUP_INDEX = MappingProxyType({name: index for index, name in enumerate(GROUP_FIELDS)})

SEMANTIC_KEYS = frozenset({
    "captured_kings", "captured_square_bitboard", "child_fingerprint",
    "child_pieces", "from", "global_row_index", "local_row_index",
    "material_count_delta_parent", "num_captures", "parent_fingerprint",
    "parent_id", "parent_legal_moves", "parent_pieces", "promotes", "schema",
    "source_shard", "to",
})

COMMON_ROOT_KEYS = frozenset({
    "code_sha", "preregistration", "schema", "selection", "teacher_merge", "tools",
})
ALLOCATION_ROOT_KEYS = COMMON_ROOT_KEYS | {"legacy_equivalence"}
ALLOCATION_TOOL_KEYS = frozenset({"allocation_input", "projection"})

SELECTION_REPORT_KEYS = frozenset({
    "schema", "code_sha", "selection_contract_sha256", "source_manifest_sha256",
    "curriculum_sha256", "exclusion", "selection_seed", "selection_hash_algorithm",
    "selection_hash_payload", "canonicalization", "representative_order",
    "final_order", "cell_order", "cell_quota", "top_up", "source_shards",
    "counters", "support_before_sampling", "selected_by_phase_stm", "selected",
    "source_raw_records", "unique_selected_canonical", "forbidden_overlap",
    "target_blind", "raw_source_jnnw_inputs", "source_score_bytes_read",
    "source_wdl_bytes_read", "source_labels_read", "output_target_nonzero_records",
    "outputs", "fits", "training", "calibration", "tuning", "model_selection",
    "strength_games", "promotion_authorized",
})

MERGE_REPORT_KEYS = frozenset({
    "adapter", "aggregate", "build", "code_sha", "counters", "identity_order",
    "identity_tuple", "input_manifest", "native_verification", "outputs",
    "scientific_scope", "schema", "selection", "shards", "teacher_runtime",
})

NATIVE_KEYS = frozenset({
    "actions_verified", "build_provenance_declared", "catalogue_actions_generated",
    "catalogues_verified", "children", "duplicate_semantic_actions", "executable",
    "extra_actions", "forbidden_reordering", "identity_order", "identity_tuple",
    "missing_actions", "nonzero_child_targets", "nonzero_parent_targets",
    "parent_after_matches", "parent_count_matches", "parents", "parents_verified",
    "schema", "semantic_actions", "semantic_rows_verified", "verification_complete",
})


class AllocationInputError(RuntimeError):
    """Authentication, schema, barrier, join, arithmetic, or publication failure."""


class CommonAuthReason(str, Enum):
    """Closed reasons that a caller may map to an authenticated support failure."""

    INPUT_AUTHENTICATION_FAILED = "INPUT_AUTHENTICATION_FAILED"


class CommonAuthenticationError(AllocationInputError):
    """A typed common-manifest authentication failure with no row context."""

    def __init__(self, reason: CommonAuthReason, detail: str):
        super().__init__(detail)
        self.reason = reason


class TechnicalIOError(AllocationInputError):
    """An I/O failure that must never become a scientific support receipt."""


class OutputSafetyError(AllocationInputError):
    """An output collision or alias that must remain a technical failure."""


@dataclass(frozen=True, slots=True)
class AuthenticatedCommonInputsV1:
    manifest: Mapping[str, Any]
    manifest_raw: bytes
    manifest_sha256: str
    base_dir: Path
    files: Mapping[str, Path]
    selection_report: Mapping[str, Any]
    teacher_merge_report: Mapping[str, Any]
    teacher_publication_receipt: Mapping[str, Any]
    native_verification_receipt: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SelectedParentV1:
    parent_id: int
    canonical_fingerprint: str
    raw_fingerprint: str
    stm: int
    pieces: int
    legal_moves: int
    phase: str
    source_shard: int
    source_row_index: int
    selection_hash: str


def canonical_json_bytes(value: object) -> bytes:
    try:
        return (json.dumps(
            value, ensure_ascii=True, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ) + "\n").encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise AllocationInputError(f"cannot serialize canonical JSON: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1 << 20):
                digest.update(chunk)
    except OSError as exc:
        raise TechnicalIOError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AllocationInputError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def read_canonical_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TechnicalIOError(f"cannot read {label}: {exc}") from exc
    try:
        text = raw.decode("ascii")
    except UnicodeError as exc:
        raise AllocationInputError(f"cannot read {label}: {exc}") from exc
    if not raw or not raw.endswith(b"\n") or b"\r" in raw or raw.endswith(b"\n\n"):
        raise AllocationInputError(f"{label} is not one canonical LF-terminated JSON object")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                AllocationInputError(f"{label} has forbidden constant {token}")
            ),
        )
    except (json.JSONDecodeError, AllocationInputError) as exc:
        raise AllocationInputError(f"invalid {label}: {exc}") from exc
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise AllocationInputError(f"{label} is not canonical JSON")
    return value, raw


def _expect_keys(value: object, keys: frozenset[str] | set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys):
        actual = sorted(value) if isinstance(value, Mapping) else type(value).__name__
        raise AllocationInputError(f"{label} fields mismatch: {actual}")
    return value


def _strict_int(value: object, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise AllocationInputError(f"{label} must be integer in [{low},{high}]")
    return value


def _strict_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise AllocationInputError(f"{label} must be boolean")
    return value


def _strict_sha(value: object, label: str) -> str:
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        raise AllocationInputError(f"{label} must be lowercase SHA256")
    return value


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.resolve(strict=False)))).casefold()


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _validate_local_name(value: object, label: str) -> str:
    if type(value) is not str or not value or value in {".", ".."}:
        raise AllocationInputError(f"{label} local_name invalid")
    if Path(value).name != value or "/" in value or "\\" in value or "\0" in value:
        raise AllocationInputError(f"{label} local_name must be a basename")
    if not value.isascii() or any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise AllocationInputError(f"{label} local_name must be printable ASCII")
    return value


def verify_file_descriptor(
    base_dir: Path,
    descriptor: object,
    label: str,
    *,
    extra_keys: frozenset[str] = frozenset(),
) -> Path:
    item = _expect_keys(descriptor, {"local_name", "sha256", "size_bytes"} | set(extra_keys), label)
    local_name = _validate_local_name(item["local_name"], label)
    expected_sha = _strict_sha(item["sha256"], f"{label}.sha256")
    expected_size = _strict_int(item["size_bytes"], f"{label}.size_bytes", 1, INT64_MAX)
    for key in ("rows", "records"):
        if key in item:
            _strict_int(item[key], f"{label}.{key}", 0, INT64_MAX)
    if "record_size_bytes" in item:
        _strict_int(item["record_size_bytes"], f"{label}.record_size_bytes", 1, INT64_MAX)
    for key in ("row_schema", "serialization"):
        if key in item and (type(item[key]) is not str or not item[key]):
            raise AllocationInputError(f"{label}.{key} must be a nonempty string")
    path = base_dir / local_name
    if path.is_symlink():
        raise OutputSafetyError(f"{label} must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise TechnicalIOError(f"cannot stat {label}: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise OutputSafetyError(f"{label} is not a regular file")
    if metadata.st_size != expected_size or sha256_file(path) != expected_sha:
        raise AllocationInputError(f"{label} size/SHA mismatch")
    return path


def _descriptor_without_local(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in descriptor.items() if key != "local_name"}


def _exact_json_equal(left: object, right: object) -> bool:
    """Compare JSON values without Python's bool/int equality coercion."""
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def _validate_common_selection(
    base: Path, manifest: Mapping[str, Any], files: dict[str, Path], code_sha: str,
) -> Mapping[str, Any]:
    selection = _expect_keys(manifest["selection"], {
        "report", "report_schema", "parents_jnnw", "parents_tsv", "ordered_identities",
        "selected", "cell_quota", "cell_order",
    }, "selection")
    if selection["report_schema"] != SELECTION_SCHEMA:
        raise AllocationInputError("selection report schema declaration mismatch")
    if type(selection["selected"]) is not int or selection["selected"] != PARENT_COUNT:
        raise AllocationInputError("selection selected must be 4000")
    if selection["cell_quota"] != CELL_QUOTA or type(selection["cell_quota"]) is not int:
        raise AllocationInputError("selection cell_quota must be 500")
    if selection["cell_order"] != list(CELL_ORDER):
        raise AllocationInputError("selection cell order mismatch")
    files["selection.report"] = verify_file_descriptor(base, selection["report"], "selection.report")
    files["selection.parents_jnnw"] = verify_file_descriptor(
        base, selection["parents_jnnw"], "selection.parents_jnnw",
        extra_keys=frozenset({"records", "record_size_bytes"}),
    )
    if selection["parents_jnnw"]["records"] != PARENT_COUNT \
            or selection["parents_jnnw"]["record_size_bytes"] != 38:
        raise AllocationInputError("selection parents_jnnw cardinality/record size mismatch")
    files["selection.parents_tsv"] = verify_file_descriptor(
        base, selection["parents_tsv"], "selection.parents_tsv",
        extra_keys=frozenset({"rows"}),
    )
    if selection["parents_tsv"]["rows"] != PARENT_COUNT:
        raise AllocationInputError("selection parents_tsv rows mismatch")
    files["selection.ordered_identities"] = verify_file_descriptor(
        base, selection["ordered_identities"], "selection.ordered_identities",
        extra_keys=frozenset({"rows", "serialization"}),
    )
    identities = selection["ordered_identities"]
    if identities["rows"] != PARENT_COUNT or identities["serialization"] != \
            "canonical_fingerprint_ascii, one per line, LF terminated":
        raise AllocationInputError("selection ordered identities contract mismatch")

    report, _ = read_canonical_json(files["selection.report"], "selection report")
    _expect_keys(report, SELECTION_REPORT_KEYS, "selection report")
    if report["schema"] != SELECTION_SCHEMA or report["code_sha"] != code_sha:
        raise AllocationInputError("selection report schema/code mismatch")
    if type(report["selected"]) is not int or report["selected"] != PARENT_COUNT \
            or type(report["cell_quota"]) is not int or report["cell_quota"] != CELL_QUOTA \
            or report["cell_order"] != list(CELL_ORDER):
        raise AllocationInputError("selection report population mismatch")
    expected_cells = {cell: CELL_QUOTA for cell in CELL_ORDER}
    if type(report["selected_by_phase_stm"]) is not dict \
            or set(report["selected_by_phase_stm"]) != set(CELL_ORDER) \
            or any(type(report["selected_by_phase_stm"][cell]) is not int
                   or report["selected_by_phase_stm"][cell] != CELL_QUOTA
                   for cell in CELL_ORDER):
        raise AllocationInputError("selection report cells mismatch")
    fixed = {
        "forbidden_overlap": 0, "target_blind": True, "raw_source_jnnw_inputs": 0,
        "source_score_bytes_read": 0, "source_wdl_bytes_read": 0,
        "source_labels_read": 0, "output_target_nonzero_records": 0,
        "fits": 0, "training": False, "calibration": False, "tuning": False,
        "model_selection": False, "strength_games": 0, "promotion_authorized": False,
        "top_up": False,
    }
    for key, expected in fixed.items():
        if type(report[key]) is not type(expected) or report[key] != expected:
            raise AllocationInputError(f"selection report {key} mismatch")
    outputs = _expect_keys(
        report["outputs"], {"parents_jnnw", "parents_tsv", "ordered_identities"},
        "selection report outputs",
    )
    expected_jnnw = _descriptor_without_local(selection["parents_jnnw"])
    expected_jnnw.pop("record_size_bytes")
    expected_tsv = _descriptor_without_local(selection["parents_tsv"])
    expected_identities = _descriptor_without_local(selection["ordered_identities"])
    if not _exact_json_equal(outputs["parents_jnnw"], expected_jnnw) \
            or not _exact_json_equal(outputs["parents_tsv"], expected_tsv) \
            or not _exact_json_equal(outputs["ordered_identities"], expected_identities):
        raise AllocationInputError("selection output descriptor intersection mismatch")
    return report


def _validate_native_receipt(
    receipt: Mapping[str, Any], rows: int, *, manifest: Mapping[str, Any],
    merge_report: Mapping[str, Any],
) -> None:
    _expect_keys(receipt, NATIVE_KEYS, "native verification receipt")
    if receipt["schema"] != NATIVE_SCHEMA or receipt["verification_complete"] is not True:
        raise AllocationInputError("native verification is not complete")
    if receipt["identity_order"] != [
        "from", "to", "captured_square_bitboard_uint64", "promotes",
    ] or receipt["identity_tuple"] != [
        "from", "to", "num_captures", "promotes", "captured_square_bitboard",
    ]:
        raise AllocationInputError("native semantic identity contract mismatch")
    expected = {
        "actions_verified": rows, "catalogue_actions_generated": rows,
        "catalogues_verified": PARENT_COUNT, "duplicate_semantic_actions": 0,
        "extra_actions": 0, "forbidden_reordering": 0, "missing_actions": 0,
        "nonzero_child_targets": 0, "nonzero_parent_targets": 0,
        "parent_after_matches": rows, "parent_count_matches": PARENT_COUNT,
        "parents_verified": PARENT_COUNT, "semantic_rows_verified": rows,
    }
    for key, value in expected.items():
        if type(receipt[key]) is not int or receipt[key] != value:
            raise AllocationInputError(f"native verification {key} mismatch")
    parents = _expect_keys(
        receipt["parents"], {"local_name", "sha256", "size_bytes", "records", "record_size_bytes"},
        "native parents descriptor",
    )
    children = _expect_keys(
        receipt["children"], {"local_name", "sha256", "size_bytes", "records", "record_size_bytes"},
        "native children descriptor",
    )
    semantic = _expect_keys(
        receipt["semantic_actions"], {"local_name", "sha256", "size_bytes", "rows", "row_schema"},
        "native semantic descriptor",
    )
    executable = _expect_keys(
        receipt["executable"], {"local_name", "sha256", "size_bytes"},
        "native executable descriptor",
    )
    for label, item in (("parents", parents), ("children", children),
                        ("semantic", semantic), ("executable", executable)):
        _validate_local_name(item["local_name"], f"native {label}")
        _strict_sha(item["sha256"], f"native {label}.sha256")
        _strict_int(item["size_bytes"], f"native {label}.size_bytes", 1, INT64_MAX)
    for label, item in (("parents", parents), ("children", children)):
        _strict_int(item["records"], f"native {label}.records", 0, INT64_MAX)
        if type(item["record_size_bytes"]) is not int or item["record_size_bytes"] != 38:
            raise AllocationInputError(f"native {label} record size mismatch")
    _strict_int(semantic["rows"], "native semantic.rows", 0, INT64_MAX)
    if semantic["row_schema"] != SEMANTIC_SCHEMA:
        raise AllocationInputError("native semantic row schema mismatch")
    selection_parent = manifest["selection"]["parents_jnnw"]
    if not _exact_json_equal(parents, selection_parent):
        raise AllocationInputError("native parent descriptor differs from selection")
    teacher = manifest["teacher_merge"]
    for native_item, final_item, label in (
        (children, teacher["children_jnnw"], "children"),
        (semantic, teacher["semantic_actions"], "semantic actions"),
    ):
        if not _exact_json_equal(_descriptor_without_local(native_item),
                                 _descriptor_without_local(final_item)):
            raise AllocationInputError(f"native {label} descriptor differs from final payload")
    build = _expect_keys(
        merge_report["build"], {"build_type", "cmake_cache", "cmake_options", "compiler_id",
                                "compiler_version", "merge_tool", "teacher_executable",
                                "verifier_executable", "verifier_source"},
        "teacher merge build",
    )
    if not _exact_json_equal(executable, build["verifier_executable"]):
        raise AllocationInputError("native executable descriptor differs from merge build")
    expected_build = {
        "build_type": build["build_type"],
        "cmake_cache_sha256": build["cmake_cache"]["sha256"],
        "code_sha": manifest["code_sha"],
        "compiler_id": build["compiler_id"],
        "compiler_version": build["compiler_version"],
        "verifier_source_sha256": build["verifier_source"]["sha256"],
    }
    if not _exact_json_equal(receipt["build_provenance_declared"], expected_build):
        raise AllocationInputError("native build provenance differs from merge report")


def _validate_common_teacher(
    base: Path, manifest: Mapping[str, Any], files: dict[str, Path], code_sha: str,
    selection_report: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    teacher = _expect_keys(manifest["teacher_merge"], {
        "input_manifest", "report", "report_schema", "publication_receipt",
        "publication_schema", "native_verification_receipt",
        "native_verification_schema", "children_jnnw", "groups_tsv",
        "semantic_actions",
    }, "teacher_merge")
    if teacher["report_schema"] != MERGE_SCHEMA \
            or teacher["publication_schema"] != MERGE_PUBLICATION_SCHEMA \
            or teacher["native_verification_schema"] != NATIVE_SCHEMA:
        raise AllocationInputError("teacher merge schema declaration mismatch")
    files["teacher.input_manifest"] = verify_file_descriptor(
        base, teacher["input_manifest"], "teacher_merge.input_manifest")
    files["teacher.report"] = verify_file_descriptor(base, teacher["report"], "teacher_merge.report")
    files["teacher.publication_receipt"] = verify_file_descriptor(
        base, teacher["publication_receipt"], "teacher_merge.publication_receipt")
    files["teacher.native_receipt"] = verify_file_descriptor(
        base, teacher["native_verification_receipt"],
        "teacher_merge.native_verification_receipt",
    )
    files["teacher.children_jnnw"] = verify_file_descriptor(
        base, teacher["children_jnnw"], "teacher_merge.children_jnnw",
        extra_keys=frozenset({"records", "record_size_bytes"}),
    )
    files["teacher.groups_tsv"] = verify_file_descriptor(
        base, teacher["groups_tsv"], "teacher_merge.groups_tsv",
        extra_keys=frozenset({"rows"}),
    )
    files["teacher.semantic_actions"] = verify_file_descriptor(
        base, teacher["semantic_actions"], "teacher_merge.semantic_actions",
        extra_keys=frozenset({"rows", "row_schema"}),
    )
    rows = _strict_int(teacher["groups_tsv"]["rows"], "teacher rows", 1, 64_000)
    if teacher["children_jnnw"]["records"] != rows \
            or teacher["children_jnnw"]["record_size_bytes"] != 38 \
            or teacher["semantic_actions"]["rows"] != rows \
            or teacher["semantic_actions"]["row_schema"] != SEMANTIC_SCHEMA:
        raise AllocationInputError("teacher payload cardinality/schema mismatch")

    report, _ = read_canonical_json(files["teacher.report"], "teacher merge report")
    _expect_keys(report, MERGE_REPORT_KEYS, "teacher merge report")
    if report["schema"] != MERGE_SCHEMA or report["code_sha"] != code_sha:
        raise AllocationInputError("teacher merge report schema/code mismatch")
    outputs = _expect_keys(
        report["outputs"], {"children_jnnw", "groups_tsv", "semantic_actions"},
        "teacher merge outputs",
    )
    if not _exact_json_equal(outputs, {
        "children_jnnw": teacher["children_jnnw"],
        "groups_tsv": teacher["groups_tsv"],
        "semantic_actions": teacher["semantic_actions"],
    }):
        raise AllocationInputError("teacher merge output descriptors mismatch")
    if not _exact_json_equal(report["input_manifest"], teacher["input_manifest"]):
        raise AllocationInputError("teacher merge input manifest descriptor mismatch")
    report_selection = _expect_keys(report["selection"], {
        "contract", "ordered_identities", "parents_jnnw", "parents_tsv", "report",
    }, "teacher merge selection")
    if not _exact_json_equal(report_selection["report"], manifest["selection"]["report"]) \
            or not _exact_json_equal(report_selection["parents_jnnw"], manifest["selection"]["parents_jnnw"]) \
            or not _exact_json_equal(report_selection["parents_tsv"], manifest["selection"]["parents_tsv"]) \
            or not _exact_json_equal(report_selection["ordered_identities"], _descriptor_without_local(
                manifest["selection"]["ordered_identities"])):
        raise AllocationInputError("teacher merge selection descriptors mismatch")
    contract = _expect_keys(report_selection["contract"], {"local_name", "sha256", "size_bytes"},
                            "teacher merge selection contract")
    _validate_local_name(contract["local_name"], "teacher merge selection contract")
    _strict_int(contract["size_bytes"], "teacher merge selection contract size", 1, INT64_MAX)
    if _strict_sha(contract["sha256"], "teacher merge selection contract SHA") \
            != selection_report["selection_contract_sha256"]:
        raise AllocationInputError("teacher merge selection contract SHA mismatch")
    counters = report["counters"]
    if type(counters) is not dict:
        raise AllocationInputError("teacher merge counters missing")
    for key, expected in {
        "children_records": rows, "groups_rows": rows, "semantic_actions": rows,
        "semantic_ledger_rows": rows, "global_rows_rebased": rows,
        "captured_bitboards_reconstructed": rows, "parent_child_transitions_verified": rows,
        "parents": PARENT_COUNT, "processed_parent_rows": PARENT_COUNT,
        "parents_with_legal_count_match": PARENT_COUNT, "full_catalogues_verified": PARENT_COUNT,
        "duplicate_semantic_actions": 0, "missing_actions": 0, "extra_actions": 0,
        "forbidden_reordering": 0, "nonzero_child_targets": 0, "shards": 16,
    }.items():
        if counters.get(key) != expected or type(counters.get(key)) is not int:
            raise AllocationInputError(f"teacher merge counter {key} mismatch")
    scope = report["scientific_scope"]
    if not _exact_json_equal(scope, {
        "calibration": False, "fits": 0, "model_selection": False,
        "promotion_authorized": False, "strength_games": 0,
        "training": False, "tuning": False,
    }):
        raise AllocationInputError("teacher merge scientific scope mismatch")

    native, native_raw = read_canonical_json(
        files["teacher.native_receipt"], "native verification receipt")
    _validate_native_receipt(native, rows, manifest=manifest, merge_report=report)
    native_binding = _expect_keys(
        report["native_verification"], {"receipt", "sha256", "size_bytes"},
        "teacher native binding",
    )
    if not _exact_json_equal(native_binding["receipt"], native) \
            or _strict_sha(native_binding["sha256"], "teacher native binding SHA") \
            != sha256_bytes(native_raw) \
            or type(native_binding["size_bytes"]) is not int \
            or native_binding["size_bytes"] != len(native_raw):
        raise AllocationInputError("native receipt binding mismatch")

    publication, _ = read_canonical_json(
        files["teacher.publication_receipt"], "teacher publication receipt")
    _expect_keys(publication, {
        "artifacts", "byte_roundtrip_verified", "code_sha", "input_manifest", "schema",
    }, "teacher publication receipt")
    if publication["schema"] != MERGE_PUBLICATION_SCHEMA \
            or publication["code_sha"] != code_sha \
            or publication["byte_roundtrip_verified"] is not True \
            or not _exact_json_equal(publication["input_manifest"], teacher["input_manifest"]):
        raise AllocationInputError("teacher publication receipt contract mismatch")
    artifacts = _expect_keys(publication["artifacts"], {
        "children_jnnw", "groups_tsv", "merge_report", "semantic_actions",
    }, "teacher publication artifacts")
    for key, descriptor_key in (
        ("children_jnnw", "children_jnnw"), ("groups_tsv", "groups_tsv"),
        ("semantic_actions", "semantic_actions"),
    ):
        expected = {name: teacher[descriptor_key][name]
                    for name in ("local_name", "sha256", "size_bytes")}
        if not _exact_json_equal(artifacts[key], expected):
            raise AllocationInputError(f"teacher publication {key} mismatch")
    expected_report = {
        "local_name": teacher["report"]["local_name"],
        "sha256": teacher["report"]["sha256"],
        "size_bytes": teacher["report"]["size_bytes"],
    }
    if not _exact_json_equal(artifacts["merge_report"], expected_report):
        raise AllocationInputError("teacher publication merge report mismatch")
    return report, publication, native


def _authenticate_common_manifest(
    manifest_path: Path,
    expected_sha256: str,
    *,
    expected_schema: str,
    exact_root_keys: frozenset[str],
    exact_tool_keys: frozenset[str],
) -> AuthenticatedCommonInputsV1:
    """Authenticate common preregistration/selection/teacher inputs.

    This public helper hashes teacher TSV/JSONL bytes through their FileV1
    descriptors, but never parses their rows.  A post-seal readout may reuse it
    without importing the q200-free row parser.
    """
    expected = _strict_sha(expected_sha256, "expected input manifest SHA256")
    if manifest_path.is_symlink():
        raise OutputSafetyError("input manifest must not be a symlink")
    try:
        manifest_metadata = manifest_path.stat()
    except OSError as exc:
        raise TechnicalIOError(f"cannot stat input manifest: {exc}") from exc
    if not stat.S_ISREG(manifest_metadata.st_mode):
        raise OutputSafetyError("input manifest must be a regular file")
    manifest, raw = read_canonical_json(manifest_path, "input manifest")
    if sha256_bytes(raw) != expected:
        raise AllocationInputError("input manifest SHA256 mismatch")
    _expect_keys(manifest, exact_root_keys, "input manifest")
    if manifest["schema"] != expected_schema:
        raise AllocationInputError("input manifest schema mismatch")
    code_sha = manifest["code_sha"]
    if type(code_sha) is not str or not GIT_RE.fullmatch(code_sha):
        raise AllocationInputError("input manifest code_sha invalid")
    base = manifest_path.resolve().parent
    files: dict[str, Path] = {}

    prereg = _expect_keys(manifest["preregistration"], {"file", "schema"}, "preregistration")
    if prereg["schema"] != PREREGISTRATION_SCHEMA:
        raise AllocationInputError("preregistration schema declaration mismatch")
    files["preregistration"] = verify_file_descriptor(base, prereg["file"], "preregistration.file")
    if files["preregistration"].suffix.lower() != ".md":
        raise AllocationInputError("preregistration file must be Markdown")

    selection_report = _validate_common_selection(base, manifest, files, code_sha)
    merge_report, publication, native = _validate_common_teacher(
        base, manifest, files, code_sha, selection_report)
    tools = _expect_keys(manifest["tools"], exact_tool_keys, "tools")
    for name in sorted(exact_tool_keys):
        files[f"tools.{name}"] = verify_file_descriptor(base, tools[name], f"tools.{name}")

    runtime_tools = {
        "allocation_input": Path(__file__).resolve(),
        "projection": Path(projection.__file__).resolve(),
    }
    for name, runtime_path in runtime_tools.items():
        if name in exact_tool_keys:
            described = files[f"tools.{name}"]
            if described.stat().st_size != runtime_path.stat().st_size \
                    or sha256_file(described) != sha256_file(runtime_path):
                raise AllocationInputError(f"tools.{name} differs from the running implementation")

    all_paths = [manifest_path.resolve(), *files.values()]
    keys = [_path_key(path) for path in all_paths]
    if len(set(keys)) != len(keys):
        raise OutputSafetyError("manifest and described inputs contain path aliases")
    for index, left in enumerate(all_paths):
        for right in all_paths[index + 1:]:
            try:
                if os.path.samefile(left, right):
                    raise OutputSafetyError(
                        "manifest and described inputs contain filesystem aliases")
            except OSError as exc:
                raise TechnicalIOError(
                    f"cannot compare authenticated input paths: {exc}") from exc
    return AuthenticatedCommonInputsV1(
        MappingProxyType(manifest), raw, expected, base, MappingProxyType(files),
        MappingProxyType(selection_report), MappingProxyType(merge_report),
        MappingProxyType(publication), MappingProxyType(native),
    )


def authenticate_common_manifest(
    manifest_path: Path,
    expected_sha256: str,
    *,
    expected_schema: str,
    exact_root_keys: frozenset[str],
    exact_tool_keys: frozenset[str],
) -> AuthenticatedCommonInputsV1:
    """Authenticate common inputs and expose only typed failure categories.

    Schema, digest, descriptor, and provenance mismatches are safe for a caller
    to map to ``INPUT_AUTHENTICATION_FAILED``.  I/O failures remain technical.
    No untrusted parent, row, or horizon context is attached at this stage.
    """
    try:
        return _authenticate_common_manifest(
            manifest_path, expected_sha256,
            expected_schema=expected_schema,
            exact_root_keys=exact_root_keys,
            exact_tool_keys=exact_tool_keys,
        )
    except TechnicalIOError:
        raise
    except OutputSafetyError:
        raise
    except CommonAuthenticationError:
        raise
    except OSError as exc:
        raise TechnicalIOError(f"common input authentication I/O failure: {exc}") from exc
    except AllocationInputError as exc:
        raise CommonAuthenticationError(
            CommonAuthReason.INPUT_AUTHENTICATION_FAILED, str(exc)) from exc


def guard_new_output_dir(
    out_dir: Path,
    protected_inputs: Sequence[Path],
    output_names: Sequence[str] = (
        "allocation-parents-v1.jsonl", "allocation-input-report-v1.json",
    ),
) -> None:
    """Require a new output directory and non-aliasing fixed output basenames."""
    if _lexists(out_dir):
        raise OutputSafetyError("output directory already exists or is a symlink")
    parent = out_dir.parent if out_dir.parent != Path("") else Path(".")
    if parent.is_symlink() or not parent.is_dir():
        raise OutputSafetyError("output parent must be an existing non-symlink directory")
    try:
        names = [_validate_local_name(name, "output") for name in output_names]
    except AllocationInputError as exc:
        raise OutputSafetyError(str(exc)) from exc
    if not names or len(set(name.casefold() for name in names)) != len(names):
        raise OutputSafetyError("output basenames must be nonempty and distinct")
    output_paths = [out_dir / name for name in names]
    output_paths.extend(out_dir / f"{name}.tmp" for name in names)
    keys = [_path_key(path) for path in [*protected_inputs, out_dir, *output_paths]]
    if len(set(keys)) != len(keys):
        raise OutputSafetyError("input/output path alias")


def _validate_legacy(common: AuthenticatedCommonInputsV1) -> tuple[Path, Path]:
    legacy = _expect_keys(common.manifest["legacy_equivalence"], {
        "report", "report_schema", "terminal_summary", "verdict",
        "parents", "rows", "differences",
    }, "legacy_equivalence")
    if legacy["report_schema"] != LEGACY_SCHEMA or legacy["verdict"] != LEGACY_VERDICT \
            or type(legacy["parents"]) is not int or legacy["parents"] != 8000 \
            or type(legacy["rows"]) is not int or legacy["rows"] != 74449 \
            or type(legacy["differences"]) is not int or legacy["differences"] != 0:
        raise AllocationInputError("legacy equivalence declaration mismatch")
    report_path = verify_file_descriptor(common.base_dir, legacy["report"], "legacy report")
    summary_path = verify_file_descriptor(
        common.base_dir, legacy["terminal_summary"], "legacy terminal summary")
    report, _ = read_canonical_json(report_path, "legacy equivalence report")
    if report.get("schema") != LEGACY_SCHEMA or report.get("verdict") != LEGACY_VERDICT:
        raise AllocationInputError("legacy equivalence report schema/verdict mismatch")
    source = report.get("source")
    equivalence = report.get("equivalence")
    diff = report.get("published_artifacts", {}).get("empty_diff")
    counters = (
        (source, "parents", 8000), (source, "rows", 74449),
        (equivalence, "parents_compared", 8000),
        (equivalence, "allocation_decision_matches", 8000),
        (equivalence, "final_b1_result_matches", 8000),
    )
    if not isinstance(source, Mapping) or not isinstance(equivalence, Mapping) \
            or any(type(obj.get(key)) is not int or obj.get(key) != expected
                   for obj, key, expected in counters) \
            or not isinstance(diff, Mapping) \
            or not SHA256_RE.fullmatch(str(diff.get("sha256", ""))):
        raise AllocationInputError("legacy equivalence report counters mismatch")
    barrier = report.get("information_barrier")
    if not isinstance(barrier, Mapping):
        raise AllocationInputError("legacy equivalence information barrier missing")
    expected_barrier = {
        "q200_fields_in_projection_decision": 0,
        "q200_policy_reads": 0,
        "q200_value_reads": 0,
        "q200_label_reads": 0,
        "q200_policy_branches": 0,
        "nodes200k_policy_reads": 0,
        "nodes200k_policy_branches": 0,
        "nodes200k_preseal_aggregation_reads": 0,
        "nodes200k_validated_rows": 74449,
        "allocation_hash_excludes_q200_values": True,
        "postseal_join_hash_includes_q200_results": True,
    }
    for key, expected_value in expected_barrier.items():
        if type(barrier.get(key)) is not type(expected_value) \
                or barrier.get(key) != expected_value:
            raise AllocationInputError(f"legacy equivalence barrier {key} mismatch")
    for key, expected_value in {
        "searches": 0, "fits": 0, "strength_games": 0,
        "promotion_authorized": False, "real_adaptive_teacher_authorized": False,
    }.items():
        if type(report.get(key)) is not type(expected_value) or report.get(key) != expected_value:
            raise AllocationInputError(f"legacy equivalence scope {key} mismatch")
    summary, _ = read_canonical_json(summary_path, "legacy terminal summary")
    if summary.get("verdict") != LEGACY_VERDICT:
        raise AllocationInputError("legacy terminal summary verdict mismatch")
    return report_path, summary_path


def _require_common_inputs_stable(
    manifest_path: Path, original: AuthenticatedCommonInputsV1,
) -> AuthenticatedCommonInputsV1:
    current = authenticate_common_manifest(
        manifest_path,
        original.manifest_sha256,
        expected_schema=INPUT_SCHEMA,
        exact_root_keys=ALLOCATION_ROOT_KEYS,
        exact_tool_keys=ALLOCATION_TOOL_KEYS,
    )
    if current.manifest_raw != original.manifest_raw or current.manifest != original.manifest \
            or set(current.files) != set(original.files):
        raise AllocationInputError("authenticated common inputs changed during preparation")
    for name, original_path in original.files.items():
        try:
            if not os.path.samefile(original_path, current.files[name]):
                raise AllocationInputError(f"authenticated input identity changed: {name}")
        except OSError as exc:
            raise AllocationInputError(f"cannot recheck authenticated input {name}: {exc}") from exc
    return current


def _load_selection_parents(common: AuthenticatedCommonInputsV1) -> list[SelectedParentV1]:
    path = common.files["selection.parents_tsv"]
    try:
        raw = path.read_bytes()
        text = raw.decode("ascii")
    except (OSError, UnicodeError) as exc:
        raise AllocationInputError(f"cannot read selection parents TSV: {exc}") from exc
    if not raw.endswith(b"\n") or b"\r" in raw or raw.endswith(b"\n\n"):
        raise AllocationInputError("selection parents TSV must use one final LF")
    lines = text[:-1].split("\n")
    if not lines or tuple(lines[0].split("\t")) != SELECTION_FIELDS:
        raise AllocationInputError("selection parents TSV header mismatch")
    if len(lines) != PARENT_COUNT + 1:
        raise AllocationInputError("selection parents TSV row count mismatch")
    parents: list[SelectedParentV1] = []
    canonical_seen: set[str] = set()
    raw_seen: set[str] = set()
    cells = {cell: 0 for cell in CELL_ORDER}
    for expected_id, line in enumerate(lines[1:]):
        values = line.split("\t")
        if len(values) != len(SELECTION_FIELDS):
            raise AllocationInputError("selection parents TSV field count mismatch")
        item = dict(zip(SELECTION_FIELDS, values))
        def uint(name: str, high: int) -> int:
            encoded = item[name].encode("ascii")
            if not UINT_RE.fullmatch(encoded):
                raise AllocationInputError(f"selection {name} is not canonical uint")
            return _strict_int(int(item[name]), f"selection {name}", 0, high)
        parent_id = uint("parent_id", PARENT_COUNT - 1)
        if parent_id != expected_id:
            raise AllocationInputError("selection parent IDs are not ordered 0..3999")
        canonical = item["canonical_fingerprint"]
        raw_fp = item["raw_fingerprint"]
        if not FINGERPRINT_RE.fullmatch(canonical) or not FINGERPRINT_RE.fullmatch(raw_fp):
            raise AllocationInputError("selection fingerprint syntax invalid")
        if exclusions.canonical_fingerprint(raw_fp) != canonical:
            raise AllocationInputError("selection canonical fingerprint mismatch")
        if canonical in canonical_seen or raw_fp in raw_seen:
            raise AllocationInputError("selection duplicate canonical/raw fingerprint")
        canonical_seen.add(canonical)
        raw_seen.add(raw_fp)
        stm = uint("parent_stm", 1)
        if stm != int(raw_fp[-1]):
            raise AllocationInputError("selection STM/fingerprint mismatch")
        pieces = uint("pieces", 40)
        legal_moves = uint("legal_moves", 16)
        phase = item["phase"]
        if phase not in PHASE_BOUNDS or not PHASE_BOUNDS[phase][0] <= pieces <= PHASE_BOUNDS[phase][1]:
            raise AllocationInputError("selection phase/pieces mismatch")
        if not 2 <= legal_moves <= 16:
            raise AllocationInputError("selection legal move count outside 2..16")
        source_shard = uint("source_shard", 15)
        source_row = uint("source_row_index", UINT64_MAX)
        selection_hash = item["selection_hash"]
        if not SHA256_RE.fullmatch(selection_hash):
            raise AllocationInputError("selection hash invalid")
        cell = f"{phase}_stm{stm}"
        cells[cell] += 1
        parents.append(SelectedParentV1(
            parent_id, canonical, raw_fp, stm, pieces, legal_moves, phase,
            source_shard, source_row, selection_hash,
        ))
    if cells != {cell: CELL_QUOTA for cell in CELL_ORDER}:
        raise AllocationInputError("selection TSV cells mismatch")
    identity_raw = "".join(parent.canonical_fingerprint + "\n" for parent in parents).encode("ascii")
    if common.files["selection.ordered_identities"].read_bytes() != identity_raw:
        raise AllocationInputError("ordered identities do not match parents TSV")
    return parents


def _strict_token(tokens: Sequence[bytes], name: str, low: int, high: int) -> int:
    token = tokens[GROUP_INDEX[name]]
    pattern = UINT_RE if low >= 0 else SINT_RE
    if not pattern.fullmatch(token):
        raise AllocationInputError(f"teacher {name} is not a canonical integer")
    return _strict_int(int(token), f"teacher {name}", low, high)


def _bool_token(tokens: Sequence[bytes], name: str) -> bool:
    token = tokens[GROUP_INDEX[name]]
    if token not in {b"0", b"1"}:
        raise AllocationInputError(f"teacher {name} must be 0/1")
    return token == b"1"


def _ascii_token(tokens: Sequence[bytes], name: str) -> str:
    try:
        return tokens[GROUP_INDEX[name]].decode("ascii")
    except UnicodeError as exc:
        raise AllocationInputError(f"teacher {name} is not ASCII") from exc


def _load_semantic_rows(common: AuthenticatedCommonInputsV1) -> list[dict[str, Any]]:
    path = common.files["teacher.semantic_actions"]
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or b"\r" in raw or raw.endswith(b"\n\n"):
        raise AllocationInputError("semantic JSONL must use one final LF")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(raw[:-1].split(b"\n")):
        try:
            text = line.decode("ascii")
            value = json.loads(
                text, object_pairs_hook=_unique_object,
                parse_constant=lambda token: (_ for _ in ()).throw(
                    AllocationInputError(f"semantic constant {token}")
                ),
            )
        except (UnicodeError, json.JSONDecodeError, AllocationInputError) as exc:
            raise AllocationInputError(f"semantic row {index} invalid: {exc}") from exc
        _expect_keys(value, SEMANTIC_KEYS, f"semantic row {index}")
        if canonical_json_bytes(value) != line + b"\n" or value["schema"] != SEMANTIC_SCHEMA:
            raise AllocationInputError(f"semantic row {index} not canonical/schema mismatch")
        if _strict_int(value["global_row_index"], "semantic global row", 0, 63_999) != index:
            raise AllocationInputError("semantic global row order mismatch")
        parent_id = _strict_int(value["parent_id"], "semantic parent_id", 0, 3999)
        _strict_int(value["source_shard"], "semantic source_shard", 0, 15)
        _strict_int(value["local_row_index"], "semantic local row", 0, 63_999)
        _strict_int(value["from"], "semantic from", 1, 50)
        _strict_int(value["to"], "semantic to", 1, 50)
        captures = _strict_int(value["num_captures"], "semantic captures", 0, 20)
        captured = _strict_int(
            value["captured_square_bitboard"], "semantic captured bitboard", 0, PLAYABLE_MASK)
        if captured.bit_count() != captures:
            raise AllocationInputError("semantic captured bitboard/count mismatch")
        if captures == 0 and captured != 0:
            raise AllocationInputError("semantic quiet action has captured bits")
        _strict_bool(value["promotes"], "semantic promotes")
        _strict_int(value["captured_kings"], "semantic captured_kings", 0, captures)
        _strict_int(value["parent_pieces"], "semantic parent_pieces", 9, 40)
        _strict_int(value["parent_legal_moves"], "semantic parent_legal_moves", 2, 16)
        _strict_int(value["child_pieces"], "semantic child_pieces", 0, 40)
        _strict_int(value["material_count_delta_parent"], "semantic material delta", -40, 40)
        for key in ("parent_fingerprint", "child_fingerprint"):
            if type(value[key]) is not str or not FINGERPRINT_RE.fullmatch(value[key]):
                raise AllocationInputError(f"semantic {key} invalid")
        if value["source_shard"] != parent_id % 16:
            raise AllocationInputError("semantic source shard/parent mismatch")
        rows.append(value)
    if len(rows) != common.manifest["teacher_merge"]["semantic_actions"]["rows"]:
        raise AllocationInputError("semantic row count mismatch")
    return rows


def _build_projection_parents(
    common: AuthenticatedCommonInputsV1, selected: Sequence[SelectedParentV1],
) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    semantic = _load_semantic_rows(common)
    path = common.files["teacher.groups_tsv"]
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or b"\r" in raw or raw.endswith(b"\n\n"):
        raise AllocationInputError("teacher groups TSV must use one final LF")
    lines = raw[:-1].split(b"\n")
    expected_header = "\t".join(GROUP_FIELDS).encode("ascii")
    if not lines or lines[0] != expected_header:
        raise AllocationInputError("teacher groups TSV 43-column header mismatch")
    group_lines = lines[1:]
    expected_rows = common.manifest["teacher_merge"]["groups_tsv"]["rows"]
    if len(group_lines) != expected_rows or len(semantic) != expected_rows:
        raise AllocationInputError("teacher groups/semantic row count mismatch")

    output: list[dict[str, Any]] = []
    parent_rows: list[dict[str, Any]] = []
    current_parent = 0
    shard_local = [0] * 16
    cells = {cell: 0 for cell in CELL_ORDER}

    def finish_parent(parent_id: int) -> None:
        nonlocal parent_rows
        selected_parent = selected[parent_id]
        if len(parent_rows) != selected_parent.legal_moves:
            raise AllocationInputError(f"parent {parent_id} action count mismatch")
        parent_object = {
            "schema": projection.INPUT_SCHEMA,
            "parent_id": parent_id,
            "phase": selected_parent.phase,
            "stm": selected_parent.stm,
            "rows": parent_rows,
        }
        # The published projector parser is the final schema/type guard.  Its
        # input contains no q200 observation field, only nodes200k.
        projection.parse_parent(parent_object)
        output.append(parent_object)
        cells[f"{selected_parent.phase}_stm{selected_parent.stm}"] += 1
        parent_rows = []

    for row_index, line in enumerate(group_lines):
        tokens = line.split(b"\t")
        if len(tokens) != len(GROUP_FIELDS):
            raise AllocationInputError(f"teacher row {row_index} does not have 43 fields")
        if _strict_token(tokens, "row_index", 0, 63_999) != row_index:
            raise AllocationInputError("teacher global row_index order mismatch")
        parent_id = _strict_token(tokens, "parent_id", 0, PARENT_COUNT - 1)
        if parent_id < current_parent or parent_id > current_parent + 1:
            raise AllocationInputError("teacher parent blocks are missing or out of order")
        if parent_id != current_parent:
            finish_parent(current_parent)
            current_parent = parent_id
        parent = selected[parent_id]
        fingerprint = _ascii_token(tokens, "parent_fingerprint")
        if fingerprint != parent.raw_fingerprint \
                or _strict_token(tokens, "parent_stm", 0, 1) != parent.stm \
                or _strict_token(tokens, "parent_pieces", 9, 40) != parent.pieces:
            raise AllocationInputError("teacher row does not join selected parent")

        sem = semantic[row_index]
        shard = parent_id % 16
        if sem["parent_id"] != parent_id or sem["parent_fingerprint"] != fingerprint \
                or sem["parent_pieces"] != parent.pieces \
                or sem["parent_legal_moves"] != parent.legal_moves \
                or sem["source_shard"] != shard \
                or sem["local_row_index"] != shard_local[shard]:
            raise AllocationInputError("teacher/semantic structural join mismatch")
        shard_local[shard] += 1
        for group_name, semantic_name, low, high in (
            ("from", "from", 1, 50), ("to", "to", 1, 50),
            ("num_captures", "num_captures", 0, 20),
            ("captured_kings", "captured_kings", 0, 20),
            ("material_count_delta_parent", "material_count_delta_parent", -40, 40),
            ("child_pieces", "child_pieces", 0, 40),
        ):
            if _strict_token(tokens, group_name, low, high) != sem[semantic_name]:
                raise AllocationInputError(f"teacher/semantic {group_name} mismatch")
        if _bool_token(tokens, "promotes") != sem["promotes"]:
            raise AllocationInputError("teacher/semantic promotes mismatch")
        _bool_token(tokens, "moving_king")
        _strict_token(tokens, "child_legal_moves", 0, 255)
        _bool_token(tokens, "child_forced_capture")

        terminal = _bool_token(tokens, "child_rule_terminal")
        tb_exact = _bool_token(tokens, "child_tb_exact")
        utility = _strict_token(tokens, "exact_parent_utility", -128, 127)
        if terminal:
            if tb_exact or utility != 1:
                raise AllocationInputError("rule-terminal row must have exact utility +1 only")
        elif tb_exact:
            if utility not in {-1, 0, 1}:
                raise AllocationInputError("TB-exact row utility must be -1/0/+1")
        elif utility != 2:
            raise AllocationInputError("nonexact row utility must use sentinel 2")
        q5 = _strict_token(tokens, "q5k_parent", INT32_MIN, INT32_MAX)
        q50 = _strict_token(tokens, "q50_parent", INT32_MIN, INT32_MAX)
        if abs(q5) > 30_000 or abs(q50) > 30_000:
            raise AllocationInputError("q5/q50 score outside engine score range")
        nodes5 = _strict_token(tokens, "nodes5k", 0, 5_000)
        nodes50 = _strict_token(tokens, "nodes50k", 0, 50_000)
        nodes200 = _strict_token(tokens, "nodes200k", 0, 200_000)
        parent_rows.append({
            "row_index": row_index,
            "child_rule_terminal": terminal,
            "child_tb_exact": tb_exact,
            "exact_parent_utility": utility,
            "q5k_parent": q5,
            "q50_parent": q50,
            "nodes5k": nodes5,
            "nodes50k": nodes50,
            "nodes200k": nodes200,
        })
    if current_parent != PARENT_COUNT - 1:
        raise AllocationInputError("teacher groups do not contain every parent")
    finish_parent(current_parent)
    if len(output) != PARENT_COUNT or cells != {cell: CELL_QUOTA for cell in CELL_ORDER}:
        raise AllocationInputError("projection parent population/cells mismatch")
    return output, len(group_lines), cells


def _publish_output(out_dir: Path, parents: Sequence[Mapping[str, Any]], report: Mapping[str, Any]) -> None:
    parent_raw = b"".join(projection.canonical_json_line(parent) for parent in parents)
    report_raw = canonical_json_bytes(report)
    expected_report = dict(report)
    output_descriptor = expected_report["output"]
    if output_descriptor["sha256"] != sha256_bytes(parent_raw) \
            or output_descriptor["size_bytes"] != len(parent_raw):
        raise AllocationInputError("internal allocation output descriptor mismatch")
    os.mkdir(out_dir)
    parent_tmp = out_dir / "allocation-parents-v1.jsonl.tmp"
    report_tmp = out_dir / "allocation-input-report-v1.json.tmp"
    parent_final = out_dir / "allocation-parents-v1.jsonl"
    report_final = out_dir / "allocation-input-report-v1.json"
    owned: list[Path] = []
    try:
        for path, raw in ((parent_tmp, parent_raw), (report_tmp, report_raw)):
            with path.open("xb") as stream:
                stream.write(raw)
            owned.append(path)
            if path.read_bytes() != raw:
                raise AllocationInputError("temporary output byte roundtrip mismatch")
        # Validate the real serialized parent objects through the projector.
        parsed, reread = projection.load_jsonl(parent_tmp)
        if reread != parent_raw or len(parsed) != PARENT_COUNT:
            raise AllocationInputError("allocation JSONL projector roundtrip mismatch")
        reread_report, reread_report_raw = read_canonical_json(report_tmp, "allocation report temporary")
        if reread_report != report or reread_report_raw != report_raw:
            raise AllocationInputError("allocation report roundtrip mismatch")
        for temporary, final in ((parent_tmp, parent_final), (report_tmp, report_final)):
            os.replace(temporary, final)
            owned.remove(temporary)
            owned.append(final)
        if parent_final.read_bytes() != parent_raw or report_final.read_bytes() != report_raw:
            raise AllocationInputError("published allocation outputs differ from rendered bytes")
    except BaseException:
        for path in owned:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            out_dir.rmdir()
        except OSError:
            pass
        raise


def prepare(input_manifest: Path, expected_manifest_sha256: str, out_dir: Path) -> dict[str, Any]:
    common = authenticate_common_manifest(
        input_manifest, expected_manifest_sha256, expected_schema=INPUT_SCHEMA,
        exact_root_keys=ALLOCATION_ROOT_KEYS, exact_tool_keys=ALLOCATION_TOOL_KEYS,
    )
    legacy_paths = _validate_legacy(common)
    protected = [input_manifest.resolve(), *common.files.values()]
    legacy = common.manifest["legacy_equivalence"]
    for descriptor in (legacy["report"], legacy["terminal_summary"]):
        protected.append(common.base_dir / descriptor["local_name"])
    guard_new_output_dir(out_dir, protected)
    selected = _load_selection_parents(common)
    parents, teacher_rows, cells = _build_projection_parents(common, selected)
    stable = _require_common_inputs_stable(input_manifest, common)
    stable_legacy_paths = _validate_legacy(stable)
    for before, after in zip(legacy_paths, stable_legacy_paths):
        try:
            if not os.path.samefile(before, after):
                raise AllocationInputError("legacy equivalence input identity changed")
        except OSError as exc:
            raise AllocationInputError(f"cannot recheck legacy equivalence input: {exc}") from exc
    parent_raw = b"".join(projection.canonical_json_line(parent) for parent in parents)
    report = {
        "schema": REPORT_SCHEMA,
        "code_sha": common.manifest["code_sha"],
        "input_manifest_sha256": common.manifest_sha256,
        "output": {
            "local_name": "allocation-parents-v1.jsonl",
            "sha256": sha256_bytes(parent_raw),
            "size_bytes": len(parent_raw),
            "rows": PARENT_COUNT,
            "row_schema": projection.INPUT_SCHEMA,
        },
        "parents": PARENT_COUNT,
        "cells": cells,
        "teacher_rows": teacher_rows,
        "parent_group_joins": PARENT_COUNT,
        "semantic_joins": teacher_rows,
        "projection_rows": teacher_rows,
        "q200_value_reads": 0,
        "q200_label_reads": 0,
        "q200_branches": 0,
        "q200_value_decodes": 0,
        "q200_metadata_decodes": 0,
        "nodes200k_validated_rows": teacher_rows,
        "nodes200k_policy_reads": 0,
        "nodes200k_policy_branches": 0,
        "searches": 0,
        "fits": 0,
        "games": 0,
        "promotions": 0,
        "bakes": 0,
        "status": "VALID",
    }
    _publish_output(out_dir, parents, report)
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--input-manifest", type=Path, required=True)
    prepare_parser.add_argument("--expected-input-manifest-sha256", required=True)
    prepare_parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = prepare(
            args.input_manifest, args.expected_input_manifest_sha256, args.out_dir)
        print(canonical_json_bytes({
            "schema": REPORT_SCHEMA, "status": report["status"],
            "parents": report["parents"], "teacher_rows": report["teacher_rows"],
            "output_sha256": report["output"]["sha256"],
        }).decode("ascii"), end="")
        return 0
    except Exception as exc:
        print(f"adaptive_sibling_b2_allocation_input: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
