#!/usr/bin/env python3
"""Build the preregistered C SiblingDataset v2 from the authenticated B3 adaptive corpus.

This stage is data packaging only.  It authenticates B3 source 1837, real adaptive
teacher 1841, and terminal authorization 1844.  It never fetches the 1843
full-ladder reference family.  Production move generation is exercised by the
native semantic verifier before any dataset record is published.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import adaptive_sibling_b2_select as selector  # noqa: E402
from jobs.tools import adaptive_sibling_b3_fresh_teacher_stage as fresh_teacher  # noqa: E402
from jobs.tools import adaptive_sibling_b3_fresh_transfer_readout as b3_readout  # noqa: E402
from jobs.tools import adaptive_sibling_b3_parity_stage as parity_stage  # noqa: E402

PARENT_SCHEMA = "jass.sibling_dataset_v2.parent.v1"
MANIFEST_SCHEMA = "jass.sibling_dataset_v2.manifest.v1"
VALIDATION_SCHEMA = "jass.sibling_dataset_v2.validation.v1"
SPLIT_SCHEMA = "jass.sibling_dataset_v2.splits.v1"
SEMANTIC_SCHEMA = "jass.sibling_dataset_v2.semantic_action.v1"
NATIVE_SCHEMA = "jass.sibling_dataset_v2.native_semantic_verification.v1"
VERDICT = "C_SIBLING_DATASET_V2_AUTHENTICATED_V1"
INVALID_VERDICT = "C_SIBLING_DATASET_V2_INVALID_V1"
NEXT_STAGE = "D_WDL_LISTWISE_PREREGISTRATION"
PARENTS = 4000
ROWS = 38053
CELL_TRAIN = 400
CELL_VALID = 50
CELL_TEST = 50
SPLIT_DOMAIN = "C_SIBLING_DATASET_V2_SPLIT_V1:"
PREREG_PATH = "docs/experiments/L3_SIBLING_DATASET_V2_PREREGISTRATION_V1_20260906.md"
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"

SOURCE_JOB = "cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1"
SOURCE_ATTEMPT = "20260906T141235Z-29084b25"
SOURCE_CODE = "29084b25789b1a88c19a86f73c476eedc52acbc6"
SOURCE_PREFIX = f"r2:jass-data/runs/{SOURCE_JOB}/{SOURCE_ATTEMPT}"
TEACHER_JOB = "cpx62-1841-l3-decision-math-b3-fresh-adaptive-teacher-rerun-v1"
TEACHER_ATTEMPT = "20260906T154029Z-299779c0"
TEACHER_CODE = "299779c03c89084ff65c672f23ccae24be16d2b5"
TEACHER_PREFIX = f"r2:jass-data/runs/{TEACHER_JOB}/{TEACHER_ATTEMPT}"
TERMINAL_JOB = "cpx62-1844-l3-decision-math-b3-fresh-corpus-transfer-readout-v1"
TERMINAL_ATTEMPT = "20260906T180342Z-37b46f2a"
TERMINAL_CODE = "37b46f2a228af3d327782d7d59140fbe8ed1cd1d"
TERMINAL_PREFIX = f"r2:jass-data/runs/{TERMINAL_JOB}/{TERMINAL_ATTEMPT}"
FORBIDDEN_REFERENCE_JOB = "cpx62-1843-l3-decision-math-b3-fresh-full-ladder-audit-v1"

SOURCE_MAPPINGS = [
    ("artefacts/source-selection-publication.json", "source-selection-publication.json"),
    ("artefacts/parents.jnnw", "parents.jnnw"),
    ("artefacts/parents.tsv", "parents.tsv"),
    ("artefacts/ordered-identities.txt", "ordered-identities.txt"),
]
TEACHER_MAPPINGS = [
    ("artefacts/b3-fresh-adaptive-groups.tsv", "b3-fresh-adaptive-groups.tsv"),
    ("artefacts/b3-fresh-source-identity.json", "b3-fresh-source-identity.json"),
    ("artefacts/scientific-summary.json", "teacher-scientific-summary.json"),
]
TERMINAL_MAPPINGS = [
    ("artefacts/b3-fresh-corpus-publication.json", "b3-fresh-corpus-publication.json"),
]


class CError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                           separators=(",", ":")) + "\n").encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CError(f"not canonical ASCII JSON: {exc}") from exc


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise CError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    if temp.exists() or temp.is_symlink():
        raise CError(f"refusing existing temp {temp}")
    try:
        temp.write_bytes(raw)
        if temp.read_bytes() != raw:
            raise CError(f"temporary roundtrip failed {path}")
        os.replace(temp, path)
        if path.read_bytes() != raw:
            raise CError(f"published roundtrip failed {path}")
    except BaseException:
        temp.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def descriptor(path: Path, **extra: object) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise CError(f"not a regular file: {path}")
    return {"local_name": path.name, "sha256": sha_file(path),
            "size_bytes": path.stat().st_size, **extra}


def _int(value: object, label: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise CError(f"{label} must be int in [{lo},{hi}]")
    return value


def _text_int(text: str, label: str, lo: int, hi: int) -> int:
    if not isinstance(text, str) or not text or not text.isascii():
        raise CError(f"{label} is not canonical integer text")
    if text == "0":
        value = 0
    elif text.startswith("-"):
        digits = text[1:]
        if not digits.isdigit() or digits.startswith("0"):
            raise CError(f"{label} is not canonical integer text")
        value = -int(digits)
    else:
        if not text.isdigit() or text.startswith("0"):
            raise CError(f"{label} is not canonical integer text")
        value = int(text)
    if not lo <= value <= hi:
        raise CError(f"{label} outside [{lo},{hi}]")
    return value


def _flag(row: Mapping[str, str], key: str) -> bool:
    value = row.get(key)
    if value == "0":
        return False
    if value == "1":
        return True
    raise CError(f"{key} is not 0/1")


def _bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise CError(f"{label} must be bool")
    return value


def _read_json(path: Path, *, canonical_required: bool = False) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("ascii"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CError(f"invalid JSON {path}: {exc}") from exc
    if type(value) is not dict:
        raise CError(f"JSON object required: {path}")
    if canonical_required and raw != canonical(value):
        raise CError(f"noncanonical JSON {path}")
    return value


def _read_tsv(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise CError(f"TSV must be LF terminated: {path}")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), delimiter="\t")
    except UnicodeError as exc:
        raise CError(f"TSV is not UTF-8: {path}") from exc
    if reader.fieldnames != list(fields):
        raise CError(f"TSV header mismatch: {path}")
    rows = list(reader)
    if any(set(row) != set(fields) or any(value is None for value in row.values()) for row in rows):
        raise CError(f"TSV row shape mismatch: {path}")
    return rows


def _read_jsonl(path: Path, *, schema: str) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise CError(f"JSONL must be LF canonical: {path}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        try:
            value = json.loads(line.decode("ascii"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise CError(f"JSONL parse failure line {number}: {exc}") from exc
        if type(value) is not dict or value.get("schema") != schema or line != canonical(value):
            raise CError(f"JSONL canonical/schema failure line {number}")
        rows.append(value)
    return rows


def authenticate_terminal(path: Path) -> dict[str, object]:
    publication = _read_json(path, canonical_required=True)
    expected = {
        "schema": b3_readout.PUBLICATION_SCHEMA,
        "state": "completed",
        "verdict": b3_readout.VERDICT,
        "fresh_b3_parents": PARENTS,
        "adaptive_rows": ROWS,
        "structural_identity_checks": "PASS",
        "action_set_checks": "PASS",
        "exact_result_consistency_checks": "PASS",
        "executed_search_replay_checks": "PASS",
        "reference_backfill": False,
        "adaptive_corpus_mutated": False,
        "sibling_dataset_v2_creation_authorized": True,
        "fits_authorized": False,
        "model_search_authorized": False,
        "strength_games_authorized": False,
        "promotion_authorized": False,
        "bake_authorized": False,
    }
    for key, expected_value in expected.items():
        if publication.get(key) != expected_value or type(publication.get(key)) is not type(expected_value):
            raise CError(f"terminal B3 authorization mismatch: {key}")
    # Deliberately return an allow-listed authorization view. Transfer diagnostics are not
    # exposed to any conversion function and cannot influence records or splits.
    return {key: publication[key] for key in expected}


def fetch_inputs(work: Path) -> dict[str, Path]:
    if FORBIDDEN_REFERENCE_JOB in "\n".join(remote for remote, _ in
                                              SOURCE_MAPPINGS + TEACHER_MAPPINGS + TERMINAL_MAPPINGS):
        raise CError("forbidden 1843 reference artifact entered C fetch map")
    source = work / "source"
    teacher = work / "teacher"
    terminal = work / "terminal"
    parity_stage.fetch_completed(
        SOURCE_PREFIX, job=SOURCE_JOB, attempt=SOURCE_ATTEMPT, expected_code=SOURCE_CODE,
        mappings=SOURCE_MAPPINGS, out_dir=source, report=work / "source-fetch.json")
    parity_stage.fetch_completed(
        TEACHER_PREFIX, job=TEACHER_JOB, attempt=TEACHER_ATTEMPT, expected_code=TEACHER_CODE,
        mappings=TEACHER_MAPPINGS, out_dir=teacher, report=work / "teacher-fetch.json")
    parity_stage.fetch_completed(
        TERMINAL_PREFIX, job=TERMINAL_JOB, attempt=TERMINAL_ATTEMPT, expected_code=TERMINAL_CODE,
        mappings=TERMINAL_MAPPINGS, out_dir=terminal, report=work / "terminal-fetch.json")
    return {
        "source_publication": source / "source-selection-publication.json",
        "parents_jnnw": source / "parents.jnnw",
        "parents_tsv": source / "parents.tsv",
        "ordered_identities": source / "ordered-identities.txt",
        "adaptive_groups": teacher / "b3-fresh-adaptive-groups.tsv",
        "teacher_identity": teacher / "b3-fresh-source-identity.json",
        "teacher_summary": teacher / "teacher-scientific-summary.json",
        "terminal_publication": terminal / "b3-fresh-corpus-publication.json",
    }


def validate_upstream(paths: Mapping[str, Path]) -> tuple[dict[str, Any], dict[str, Any], dict[str, object]]:
    source_publication = _read_json(paths["source_publication"], canonical_required=True)
    fresh_teacher.verify_source_publication(source_publication, paths["parents_jnnw"].parent)
    teacher_identity = _read_json(paths["teacher_identity"], canonical_required=True)
    teacher_summary = _read_json(paths["teacher_summary"], canonical_required=True)
    if teacher_summary.get("schema") != fresh_teacher.SCHEMA \
            or teacher_summary.get("state") != "completed" \
            or teacher_summary.get("verdict") != fresh_teacher.VERDICT \
            or teacher_summary.get("fresh_b3_parents") != PARENTS \
            or teacher_summary.get("reference_audit_reads") != 0 \
            or teacher_summary.get("full_ladder_backfill") is not False:
        raise CError("1841 adaptive teacher summary mismatch")
    groups_desc = teacher_summary.get("adaptive_groups")
    if not isinstance(groups_desc, Mapping) \
            or groups_desc.get("rows") != ROWS \
            or groups_desc.get("sha256") != sha_file(paths["adaptive_groups"]):
        raise CError("1841 adaptive groups descriptor mismatch")
    source = teacher_summary.get("source")
    if not isinstance(source, Mapping):
        raise CError("1841 source identity missing")
    expected_source = {"job_id": SOURCE_JOB, "attempt_id": SOURCE_ATTEMPT,
                       "code_sha": SOURCE_CODE, "prefix": SOURCE_PREFIX}
    for key, value in expected_source.items():
        if source.get(key) != value or teacher_identity.get(key) != value:
            raise CError(f"1841/1837 source identity mismatch: {key}")
    if teacher_identity.get("parents_jnnw") != source_publication["selection"]["parents_jnnw"] \
            or teacher_identity.get("ordered_identities") != source_publication["selection"]["ordered_identities"]:
        raise CError("1841 source descriptors differ from 1837 publication")
    terminal_view = authenticate_terminal(paths["terminal_publication"])
    return source_publication, teacher_summary, terminal_view


def run(argv: Sequence[str], *, timeout: int, log: Path) -> None:
    with log.open("wb") as handle:
        completed = subprocess.run(list(argv), cwd=str(ROOT), stdout=handle,
                                   stderr=subprocess.STDOUT, timeout=timeout, check=False)
    if completed.returncode != 0:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-80:])
        raise CError(f"command failed rc={completed.returncode}: {' '.join(argv)}\n{tail}")


def build_native_verifier(work: Path) -> tuple[Path, dict[str, object]]:
    build = work / "build"
    run(["/usr/bin/cmake", "-S", str(ROOT), "-B", str(build), "-G", "Unix Makefiles",
         "-DCMAKE_BUILD_TYPE=Release", "-DJASS_EGDB=OFF"], timeout=240,
        log=work / "cmake-configure.log")
    run(["/usr/bin/cmake", "--build", str(build), "--target", "jass_lib", "-j", "8"],
        timeout=900, log=work / "cmake-build.log")
    exe = work / "sibling_dataset_v2_semantic_verify"
    source = ROOT / "src/sibling_dataset_v2_semantic_verify.cpp"
    run(["/usr/bin/c++", "-std=c++20", "-O2", "-march=native",
         f"-I{ROOT / 'src'}", f"-I{ROOT / 'pattern_jass/src'}", str(source),
         "-o", str(exe), str(build / "libjass_lib.a"), "-pthread"],
        timeout=240, log=work / "native-link.log")
    exe.chmod(0o755)
    run([str(exe), "selftest"], timeout=30, log=work / "native-selftest.log")
    return exe, {"source_sha256": sha_file(source), "build_type": "Release",
                 "compiler": subprocess.check_output(["/usr/bin/c++", "--version"], text=True).splitlines()[0],
                 "production_movegen": True, "searches": 0}


def native_semantics(exe: Path, paths: Mapping[str, Path], work: Path) -> tuple[Path, dict[str, Any]]:
    semantic = work / "semantic-actions.jsonl"
    receipt = work / "native-semantic-receipt.json"
    run([str(exe), str(paths["parents_jnnw"]), str(paths["adaptive_groups"]),
         str(semantic), str(receipt)], timeout=300, log=work / "native-semantic.log")
    native = _read_json(receipt, canonical_required=True)
    expected = {"schema": NATIVE_SCHEMA, "parents_verified": PARENTS, "rows_verified": ROWS,
                "production_movegen": True, "full_ladder_reference_reads": 0,
                "searches": 0, "fits": 0, "strength_games": 0, "promotions": 0}
    for key, value in expected.items():
        if native.get(key) != value or type(native.get(key)) is not type(value):
            raise CError(f"native semantic receipt mismatch: {key}")
    if len(_read_jsonl(semantic, schema=SEMANTIC_SCHEMA)) != ROWS:
        raise CError("native semantic row count mismatch")
    return semantic, native


def _normalize_reason(value: str, allowed: set[str], label: str) -> str | None:
    if value == "NONE":
        return None
    if value not in allowed:
        raise CError(f"{label} enum mismatch")
    return value


def _observation(row: Mapping[str, str], horizon: str, observed: bool) -> dict[str, object]:
    if horizon == "5k":
        suffix, score_key, budget = "5k", "q5k_parent", 5000
    elif horizon == "50k":
        suffix, score_key, budget = "50k", "q50_parent", 50000
    elif horizon == "200k":
        suffix, score_key, budget = "200k", "q200_parent", 200000
    else:
        raise CError("unknown horizon")
    payload_keys = ("score_parent", "nodes", "completed_depth", "effective_depth",
                    "aborted_iteration", "stop_reason", "elapsed_us", "pv_enters_egdb")
    if not observed:
        return {"observed": False, **{key: None for key in payload_keys}}
    score = _text_int(row[score_key], score_key, -30000, 30000)
    nodes = _text_int(row[f"nodes{suffix}"], f"nodes{suffix}", 0, budget)
    completed = _text_int(row[f"completed_depth{suffix}"], "completed_depth", 0, 64)
    effective = _text_int(row[f"effective_depth{suffix}"], "effective_depth", 0, 64)
    if completed > effective:
        raise CError("completed depth exceeds effective depth")
    aborted = _flag(row, f"aborted{suffix}")
    stop = row[f"stop{suffix}"]
    if stop not in {"none", "nodes"} or (stop == "nodes" and nodes != budget):
        raise CError("search stop/nodes contract mismatch")
    if aborted != (stop != "none" and effective > completed):
        raise CError("aborted/depth/stop contract mismatch")
    return {
        "observed": True,
        "score_parent": score,
        "nodes": nodes,
        "completed_depth": completed,
        "effective_depth": effective,
        "aborted_iteration": aborted,
        "stop_reason": stop,
        "elapsed_us": _text_int(row[f"elapsed_us{suffix}"], "elapsed_us", 0, (1 << 63) - 1),
        "pv_enters_egdb": _flag(row, f"pv{suffix}_enters_egdb"),
    }


def assign_splits(source_rows: Sequence[Mapping[str, str]]) -> dict[int, str]:
    if len(source_rows) != PARENTS:
        raise CError("split requires exactly 4000 parents")
    by_cell: dict[str, list[tuple[bytes, str, int]]] = {cell: [] for cell in selector.CELL_ORDER}
    seen: set[str] = set()
    for row in source_rows:
        parent_id = _text_int(row["parent_id"], "parent_id", 0, PARENTS - 1)
        canonical_id = row["canonical_fingerprint"]
        if not canonical_id or not canonical_id.isascii() or canonical_id in seen:
            raise CError("canonical parent identity missing/duplicate")
        seen.add(canonical_id)
        cell = f"{row['phase']}_stm{row['parent_stm']}"
        if cell not in by_cell:
            raise CError("unknown split cell")
        digest = hashlib.sha256((SPLIT_DOMAIN + canonical_id).encode("ascii")).digest()
        by_cell[cell].append((digest, canonical_id, parent_id))
    assignment: dict[int, str] = {}
    for cell in selector.CELL_ORDER:
        ordered = sorted(by_cell[cell])
        if len(ordered) != 500:
            raise CError(f"cell {cell} is not exactly 500 parents")
        for offset, (_, _, parent_id) in enumerate(ordered):
            split = "train" if offset < CELL_TRAIN else "valid" if offset < CELL_TRAIN + CELL_VALID else "test"
            if parent_id in assignment:
                raise CError("parent assigned twice")
            assignment[parent_id] = split
    counts = {name: sum(value == name for value in assignment.values()) for name in ("train", "valid", "test")}
    if counts != {"train": 3200, "valid": 400, "test": 400} or len(assignment) != PARENTS:
        raise CError("global split counts mismatch")
    return assignment


def _semantic_key(value: Mapping[str, Any]) -> tuple[int, int, int, bool]:
    return (_int(value.get("from"), "semantic.from", 1, 50),
            _int(value.get("to"), "semantic.to", 1, 50),
            _int(value.get("captured_square_bitboard"), "semantic.captured", 0, (1 << 50) - 1),
            _bool(value.get("promotes"), "semantic.promotes"))


def build_dataset(paths: Mapping[str, Path], semantic_path: Path, artifact_dir: Path,
                  source_publication: Mapping[str, Any], teacher_summary: Mapping[str, Any],
                  terminal_view: Mapping[str, object], native_receipt: Mapping[str, Any],
                  build_receipt: Mapping[str, object]) -> tuple[dict[str, Any], dict[str, Any]]:
    source_rows = _read_tsv(paths["parents_tsv"], selector.OUTPUT_FIELDS)
    if len(source_rows) != PARENTS:
        raise CError("source TSV parent count mismatch")
    adaptive_fields = list(b3_readout.ADAPTIVE_FIELDS)
    groups = _read_tsv(paths["adaptive_groups"], adaptive_fields)
    semantics = _read_jsonl(semantic_path, schema=SEMANTIC_SCHEMA)
    if len(groups) != ROWS or len(semantics) != ROWS:
        raise CError("adaptive/semantic row count mismatch")
    assignment = assign_splits(source_rows)

    group_blocks: list[list[dict[str, str]]] = [[] for _ in range(PARENTS)]
    semantic_blocks: list[list[dict[str, Any]]] = [[] for _ in range(PARENTS)]
    for index, (group, semantic) in enumerate(zip(groups, semantics)):
        if _text_int(group["row_index"], "row_index", 0, ROWS - 1) != index:
            raise CError("adaptive row_index is not contiguous")
        parent_id = _text_int(group["parent_id"], "group.parent_id", 0, PARENTS - 1)
        if _int(semantic.get("parent_id"), "semantic.parent_id", 0, PARENTS - 1) != parent_id:
            raise CError("adaptive/semantic parent join mismatch")
        group_blocks[parent_id].append(group)
        semantic_blocks[parent_id].append(semantic)

    records: list[dict[str, Any]] = []
    total_actions = 0
    total_nodes = 0
    per_split_parents = {"train": 0, "valid": 0, "test": 0}
    per_split_actions = {"train": 0, "valid": 0, "test": 0}
    per_cell_split = {cell: {"train": 0, "valid": 0, "test": 0} for cell in selector.CELL_ORDER}
    context_identity = (
        f"adaptive_teacher:M5=100,M50=60,min=2;budgets=5000,50000,200000;"
        f"curriculum={CURRICULUM_SHA};tt_mib=16;threads=1;node_limit=exact;book=off"
    )

    for parent_id, source in enumerate(source_rows):
        if _text_int(source["parent_id"], "source.parent_id", 0, PARENTS - 1) != parent_id:
            raise CError("source parent ids are not zero-based order")
        expected_legal = _text_int(source["legal_moves"], "legal_moves", 2, 16)
        parent_groups = group_blocks[parent_id]
        parent_semantics = semantic_blocks[parent_id]
        if len(parent_groups) != expected_legal or len(parent_semantics) != expected_legal:
            raise CError("parent action cardinality differs from source legal_moves")
        if [s["local_action_index"] for s in parent_semantics] != list(range(expected_legal)):
            raise CError("native local_action_index order mismatch")
        selected_count = sum(_flag(row, "selected") for row in parent_groups)
        if selected_count != 1:
            raise CError("parent must have exactly one selected action")
        reasons_exact = {row["exact_shortcut_reason"] for row in parent_groups}
        reasons_sole = {row["sole_survivor_reason"] for row in parent_groups}
        uncertified_values = {_flag(row, "uncertified") for row in parent_groups}
        if len(reasons_exact) != 1 or len(reasons_sole) != 1 or len(uncertified_values) != 1:
            raise CError("parent allocation reason fields are not uniform")
        exact_reason = _normalize_reason(next(iter(reasons_exact)),
                                         {"EXACT_WIN", "ALL_EXACT_DRAW", "ALL_EXACT_LOSS"},
                                         "exact_shortcut_reason")
        sole_reason = _normalize_reason(next(iter(reasons_sole)),
                                        {"SOLE_UNRESOLVED_BEFORE_Q200"},
                                        "sole_survivor_reason")
        uncertified = next(iter(uncertified_values))

        actions: list[dict[str, Any]] = []
        parent_nodes = 0
        seen_actions: set[tuple[int, int, int, bool]] = set()
        for local, (group, semantic) in enumerate(zip(parent_groups, parent_semantics)):
            if semantic.get("parent_fingerprint") != source["raw_fingerprint"] \
                    or group["parent_fingerprint"] != source["raw_fingerprint"]:
                raise CError("parent raw fingerprint join mismatch")
            semantic_key = _semantic_key(semantic)
            if semantic_key in seen_actions:
                raise CError("duplicate semantic action in parent")
            seen_actions.add(semantic_key)
            promotes = _bool(semantic["promotes"], "semantic.promotes")
            if semantic_key[0] != _text_int(group["from"], "from", 1, 50) \
                    or semantic_key[1] != _text_int(group["to"], "to", 1, 50) \
                    or _int(semantic["num_captures"], "num_captures", 0, 20) != _text_int(group["num_captures"], "num_captures", 0, 20) \
                    or promotes != _flag(group, "promotes"):
                raise CError("adaptive action identity differs from native semantic verifier")
            rule_terminal = _flag(group, "child_rule_terminal")
            tb_exact = _flag(group, "child_tb_exact")
            if rule_terminal and tb_exact:
                raise CError("rule-terminal and TB-exact are mutually exclusive")
            utility_token = _text_int(group["exact_parent_utility"], "exact_parent_utility", -1, 2)
            exact_utility: int | None
            if rule_terminal:
                if utility_token != 1:
                    raise CError("rule-terminal utility must be +1")
                exact_utility = 1
            elif tb_exact:
                if utility_token not in {-1, 0, 1}:
                    raise CError("TB exact utility invalid")
                exact_utility = utility_token
            else:
                if utility_token != 2:
                    raise CError("nonexact utility sentinel must be 2")
                exact_utility = None

            searched5 = _flag(group, "searched5")
            searched50 = _flag(group, "searched50")
            searched200 = _flag(group, "searched200")
            survived5 = _flag(group, "survived5")
            survived50 = _flag(group, "survived50")
            selected = _flag(group, "selected")
            if searched200 and not searched50 or searched50 and not searched5 \
                    or survived50 and not survived5:
                raise CError("adaptive nested allocation invariant failed")
            observations = {
                "5k": _observation(group, "5k", searched5),
                "50k": _observation(group, "50k", searched50),
                "200k": _observation(group, "200k", searched200),
            }
            parent_nodes += sum(obs["nodes"] for obs in observations.values() if obs["observed"])
            action = {
                "local_action_index": local,
                "from": semantic_key[0],
                "to": semantic_key[1],
                "captured_square_bitboard": semantic_key[2],
                "num_captures": _int(semantic["num_captures"], "num_captures", 0, 20),
                "promotes": promotes,
                "moving_king": _bool(semantic["moving_king"], "moving_king"),
                "captured_kings": _int(semantic["captured_kings"], "captured_kings", 0, 20),
                "material_count_delta_parent": _int(semantic["material_count_delta_parent"], "material_delta", -20, 20),
                "child_identity": semantic["child_fingerprint"],
                "child_pieces": _int(semantic["child_pieces"], "child_pieces", 0, 40),
                "child_legal_moves": _int(semantic["child_legal_moves"], "child_legal_moves", 0, 64),
                "child_forced_capture": _bool(semantic["child_forced_capture"], "child_forced_capture"),
                "rule_terminal": rule_terminal,
                "child_tb_exact": tb_exact,
                "exact_parent_utility": exact_utility,
                "static_baseline_parent": _text_int(group["t_baseline_parent"], "t_baseline_parent", -30000, 30000),
                "observations": observations,
                "searched5": searched5,
                "searched50": searched50,
                "searched200": searched200,
                "survived5": survived5,
                "survived50": survived50,
                "selected": selected,
            }
            actions.append(action)

        cell = f"{source['phase']}_stm{source['parent_stm']}"
        split = assignment[parent_id]
        record = {
            "schema": PARENT_SCHEMA,
            "parent_id": parent_id,
            "canonical_parent_identity": source["canonical_fingerprint"],
            "raw_parent_identity": source["raw_fingerprint"],
            "board_identity": source["raw_fingerprint"],
            "rule_state_identity": "halfmove_clock=0",
            "search_context_identity": context_identity,
            "phase": source["phase"],
            "stm": _text_int(source["parent_stm"], "parent_stm", 0, 1),
            "pieces": _text_int(source["pieces"], "pieces", 9, 40),
            "legal_action_count": expected_legal,
            "cell": cell,
            "source_shard": _text_int(source["source_shard"], "source_shard", 0, 15),
            "source_row_index": _text_int(source["source_row_index"], "source_row_index", 0, 9999),
            "source_selection_hash": source["selection_hash"],
            "split": split,
            "actions": actions,
            "exact_shortcut_reason": exact_reason,
            "sole_survivor_reason": sole_reason,
            "uncertified": uncertified,
            "policy": {"M5": 100, "M50": 60, "minimum_survivors": 2},
            "budgets_nodes": [5000, 50000, 200000],
            "real_teacher_nodes": parent_nodes,
            "search_bounds": None,
            "certified_relations": None,
            "stability": None,
            "provenance_ref": "manifest:v1",
        }
        records.append(record)
        total_actions += len(actions)
        total_nodes += parent_nodes
        per_split_parents[split] += 1
        per_split_actions[split] += len(actions)
        per_cell_split[cell][split] += 1

    if total_actions != ROWS or total_nodes != (
        teacher_summary["teacher"]["cheap_nodes"] + teacher_summary["teacher"]["screen_nodes"]
        + teacher_summary["teacher"]["teacher_nodes"]
    ):
        raise CError("dataset action/node totals differ from 1841")
    expected_cell_split = {"train": 400, "valid": 50, "test": 50}
    if any(per_cell_split[cell] != expected_cell_split for cell in selector.CELL_ORDER):
        raise CError("per-cell split counts differ from preregistration")

    dataset_path = artifact_dir / "sibling-dataset-v2.jsonl"
    dataset_raw = b"".join(canonical(record) for record in records)
    write_new(dataset_path, dataset_raw)
    split_obj = {
        "schema": SPLIT_SCHEMA,
        "method": "sha256(C_SIBLING_DATASET_V2_SPLIT_V1:canonical_parent_identity)",
        "counts": per_split_parents,
        "actions": per_split_actions,
        "per_cell": per_cell_split,
        "train_parent_ids": [r["parent_id"] for r in records if r["split"] == "train"],
        "valid_parent_ids": [r["parent_id"] for r in records if r["split"] == "valid"],
        "test_parent_ids": [r["parent_id"] for r in records if r["split"] == "test"],
        "canonical_overlap_train_valid": 0,
        "canonical_overlap_train_test": 0,
        "canonical_overlap_valid_test": 0,
        "all_parents_assigned_once": True,
        "all_actions_assigned_with_parent": True,
    }
    split_path = artifact_dir / "sibling-dataset-v2-splits.json"
    write_new(split_path, canonical(split_obj))

    repo_sha = subprocess.check_output(["/usr/bin/git", "rev-parse", "HEAD"], cwd=ROOT,
                                       text=True).strip()
    prereg_raw = subprocess.check_output(["/usr/bin/git", "show", f"HEAD:{PREREG_PATH}"], cwd=ROOT)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "state": "completed",
        "verdict": VERDICT,
        "dataset": descriptor(dataset_path, parents=PARENTS, actions=ROWS,
                              serialization="canonical ASCII JSONL, one parent per line"),
        "splits": descriptor(split_path, parents=PARENTS),
        "population": {"parents": PARENTS, "actions": ROWS, "cells": 8,
                       "train": 3200, "valid": 400, "test": 400},
        "real_teacher_nodes": total_nodes,
        "source": {"job_id": SOURCE_JOB, "attempt_id": SOURCE_ATTEMPT,
                   "code_sha": SOURCE_CODE, "prefix": SOURCE_PREFIX,
                   "parents_jnnw": source_publication["selection"]["parents_jnnw"],
                   "ordered_identities": source_publication["selection"]["ordered_identities"]},
        "adaptive_teacher": {"job_id": TEACHER_JOB, "attempt_id": TEACHER_ATTEMPT,
                             "code_sha": TEACHER_CODE, "prefix": TEACHER_PREFIX,
                             "groups": teacher_summary["adaptive_groups"]},
        "b3_terminal_authorization": {"job_id": TERMINAL_JOB, "attempt_id": TERMINAL_ATTEMPT,
                                      "code_sha": TERMINAL_CODE, "prefix": TERMINAL_PREFIX,
                                      "publication_sha256": sha_file(paths["terminal_publication"]),
                                      "authorization": terminal_view},
        "converter": {"code_sha": repo_sha, "schema_version": PARENT_SCHEMA,
                      "preregistration_path": PREREG_PATH,
                      "preregistration_sha256": sha256_bytes(prereg_raw),
                      "native_verifier": build_receipt,
                      "native_receipt": dict(native_receipt)},
        "information_barrier": {"full_ladder_reference_job": FORBIDDEN_REFERENCE_JOB,
                                "full_ladder_reference_reads": 0,
                                "reference_backfill": False,
                                "terminal_transfer_metrics_used_for_training": False},
        "fits": 0, "model_searches": 0, "strength_games": 0,
        "promotions": 0, "bakes": 0,
        "next_stage": NEXT_STAGE,
    }
    validate_dataset(dataset_path, manifest, split_obj)
    validation = {
        "schema": VALIDATION_SCHEMA,
        "state": "completed",
        "verdict": VERDICT,
        "dataset_sha256": manifest["dataset"]["sha256"],
        "parents_validated": PARENTS,
        "actions_validated": ROWS,
        "canonical_parent_identities_unique": True,
        "parent_cluster_split": True,
        "symmetry_canonical_overlap": 0,
        "structural_missingness_null_not_zero": True,
        "native_production_movegen_verified": True,
        "full_ladder_reference_reads": 0,
        "fits": 0, "model_searches": 0, "strength_games": 0,
        "promotions": 0, "bakes": 0,
        "next_stage": NEXT_STAGE,
    }
    return manifest, validation


def validate_observation_object(value: object, *, expected_observed: bool) -> None:
    if type(value) is not dict or value.get("observed") is not expected_observed:
        raise CError("observation observed flag mismatch")
    payload = ("score_parent", "nodes", "completed_depth", "effective_depth",
               "aborted_iteration", "stop_reason", "elapsed_us", "pv_enters_egdb")
    if set(value) != {"observed", *payload}:
        raise CError("observation fields mismatch")
    if not expected_observed:
        if any(value[key] is not None for key in payload):
            raise CError("structural missingness must be null, never zero/payload")
        return
    for key in ("score_parent", "nodes", "completed_depth", "effective_depth", "elapsed_us"):
        if type(value[key]) is not int:
            raise CError("observed numeric payload must be int")
    if type(value["aborted_iteration"]) is not bool or type(value["pv_enters_egdb"]) is not bool:
        raise CError("observed boolean payload type mismatch")
    if value["stop_reason"] not in {"none", "nodes"}:
        raise CError("observed stop reason mismatch")


def validate_dataset(path: Path, manifest: Mapping[str, Any], splits: Mapping[str, Any]) -> None:
    records = _read_jsonl(path, schema=PARENT_SCHEMA)
    if len(records) != PARENTS:
        raise CError("reader: parent count mismatch")
    seen_parent: set[str] = set()
    action_total = 0
    split_counts = {"train": 0, "valid": 0, "test": 0}
    for expected_id, record in enumerate(records):
        if record.get("parent_id") != expected_id or type(record.get("parent_id")) is not int:
            raise CError("reader: parent order/id mismatch")
        canonical_id = record.get("canonical_parent_identity")
        if type(canonical_id) is not str or canonical_id in seen_parent:
            raise CError("reader: canonical parent identity duplicate/type mismatch")
        seen_parent.add(canonical_id)
        actions = record.get("actions")
        legal = record.get("legal_action_count")
        if type(actions) is not list or type(legal) is not int or len(actions) != legal \
                or not 2 <= legal <= 16:
            raise CError("reader: action cardinality mismatch")
        if sum(action.get("selected") is True for action in actions) != 1:
            raise CError("reader: selected action count mismatch")
        seen_action: set[tuple[int, int, int, bool]] = set()
        for local, action in enumerate(actions):
            if type(action) is not dict or action.get("local_action_index") != local:
                raise CError("reader: local action order mismatch")
            key = (action.get("from"), action.get("to"), action.get("captured_square_bitboard"),
                   action.get("promotes"))
            if key in seen_action:
                raise CError("reader: duplicate semantic action")
            seen_action.add(key)
            if action.get("searched200") and not action.get("searched50") \
                    or action.get("searched50") and not action.get("searched5") \
                    or action.get("survived50") and not action.get("survived5"):
                raise CError("reader: nested allocation invariant failed")
            observations = action.get("observations")
            if type(observations) is not dict or set(observations) != {"5k", "50k", "200k"}:
                raise CError("reader: observations shape mismatch")
            validate_observation_object(observations["5k"], expected_observed=bool(action.get("searched5")))
            validate_observation_object(observations["50k"], expected_observed=bool(action.get("searched50")))
            validate_observation_object(observations["200k"], expected_observed=bool(action.get("searched200")))
        split = record.get("split")
        if split not in split_counts:
            raise CError("reader: split enum mismatch")
        split_counts[split] += 1
        action_total += len(actions)
    if action_total != ROWS or split_counts != {"train": 3200, "valid": 400, "test": 400}:
        raise CError("reader: global action/split count mismatch")
    if manifest.get("information_barrier", {}).get("full_ladder_reference_reads") != 0 \
            or manifest.get("information_barrier", {}).get("reference_backfill") is not False:
        raise CError("reader: full-ladder information barrier violated")
    ids = {name: set(splits[f"{name}_parent_ids"]) for name in ("train", "valid", "test")}
    if ids["train"] & ids["valid"] or ids["train"] & ids["test"] or ids["valid"] & ids["test"] \
            or len(ids["train"] | ids["valid"] | ids["test"]) != PARENTS:
        raise CError("reader: parent split overlap/coverage failure")


def run_stage(args: argparse.Namespace) -> dict[str, Any]:
    if args.work_dir.exists() or args.work_dir.is_symlink():
        raise CError("work-dir must be absent")
    args.work_dir.mkdir(parents=True)
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    paths = fetch_inputs(args.work_dir)
    source_publication, teacher_summary, terminal_view = validate_upstream(paths)
    exe, build_receipt = build_native_verifier(args.work_dir)
    semantic_path, native_receipt = native_semantics(exe, paths, args.work_dir)
    manifest, validation = build_dataset(
        paths, semantic_path, args.artifact_dir, source_publication, teacher_summary,
        terminal_view, native_receipt, build_receipt)
    semantic_out = args.artifact_dir / "sibling-dataset-v2-semantic-actions.jsonl"
    shutil.copyfile(semantic_path, semantic_out)
    native_out = args.artifact_dir / "sibling-dataset-v2-native-receipt.json"
    write_new(native_out, canonical(native_receipt))
    manifest["semantic_actions"] = descriptor(
        semantic_out, rows=ROWS, schema=SEMANTIC_SCHEMA,
        purpose="production-movegen structural verification only")
    manifest["native_receipt_artifact"] = descriptor(native_out, schema=NATIVE_SCHEMA)
    manifest_path = args.artifact_dir / "sibling-dataset-v2-manifest.json"
    validation_path = args.artifact_dir / "sibling-dataset-v2-validation.json"
    summary_path = args.artifact_dir / "scientific-summary.json"
    write_new(manifest_path, canonical(manifest))
    write_new(validation_path, canonical(validation))
    write_new(summary_path, canonical({
        "schema": MANIFEST_SCHEMA, "state": "completed", "verdict": VERDICT,
        "parents": PARENTS, "actions": ROWS,
        "splits": {"train": 3200, "valid": 400, "test": 400},
        "full_ladder_reference_reads": 0, "reference_backfill": False,
        "fits": 0, "model_searches": 0, "strength_games": 0,
        "promotions": 0, "bakes": 0, "next_stage": NEXT_STAGE,
    }))
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        result = run_stage(parse_args(argv))
    except Exception as exc:
        print(f"sibling_dataset_v2_stage: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"state": result["state"], "verdict": result["verdict"],
                      "next_stage": result["next_stage"]},
                     sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
