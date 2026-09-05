#!/usr/bin/env python3
"""Exhaustively compare the q200-free B2 projection with frozen historical B1.

This is a historical implementation-equivalence check.  It performs no search,
fit, game, confirmation read, or scientific gate.  The allocation policy sees
only the B2 projection object.  Historical q200 values are joined after that
decision is sealed, solely to reconstruct and compare the frozen B1 result.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

if __package__ in (None, ""):
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from jobs.tools import adaptive_sibling_b2_projection as projection
from jobs.tools import adaptive_sibling_teacher_shadow as legacy


SCHEMA = "jass.adaptive_sibling_b2_legacy_equivalence.v1"
EXPECTED_PARENTS = 8_000
EXPECTED_ROWS = 74_449
EXPECTED_GROUPS_SHA256 = "bed80165f2e1249dbc8d0416237250a9ae0c62bcf0900816f60a8fc72c78ac76"
EXPECTED_B1_REPORT_SHA256 = "f786210b41490feb32e582bd6075e38b765ef53d5330525b66792cf10e7dd9c0"
EXPECTED_B1_AGGREGATE = {
    "parents": 8_000,
    "rows": 74_449,
    "fully_nonexact_parents": 7_982,
    "mixed_exact_nonexact_parents": 2,
    "exact_win_shortcut_parents": 13,
    "full_ladder_nodes": 18_542_435_675,
    "shadow_nodes": 10_789_907_706,
    "node_ratio": 0.5819034723980511,
    "teacher_node_saving": 0.41809652760194893,
    "best_move_match_vs_full_q200": 0.96425,
    "mean_q200_regret_cp": 95.749,
    "p95_q200_regret_cp": 0.0,
    "catastrophic_regret_rate": 0.004,
    "uncertified_shadow_parents": 0,
}

SOURCE_COLUMNS = {
    "row_index", "parent_id", "parent_stm", "parent_pieces",
    "child_rule_terminal", "child_tb_exact", "exact_parent_utility",
    "q5k_parent", "q50_parent", "q200_parent",
    "nodes5k", "nodes50k", "nodes200k",
}
COMPANION_FILENAMES = {
    "projection_receipts": "projection-receipts.jsonl",
    "legacy_decisions": "legacy-decisions.tsv",
    "legacy_report": "legacy-report.json",
    "postseal_join": "postseal-q200-join.jsonl",
    "empty_diff": "equivalence-diff.json",
}


class EquivalenceError(RuntimeError):
    """A historical identity, schema, equivalence, or output failure."""


@dataclass(frozen=True, slots=True)
class HistoricalRowV1:
    row_index: int
    parent_id: int
    parent_stm: int
    parent_pieces: int
    child_rule_terminal: bool
    child_tb_exact: bool
    exact_parent_utility: int
    q5k_parent: int
    q50_parent: int
    q200_parent: int
    nodes5k: int
    nodes50k: int
    nodes200k: int

    @property
    def exact(self) -> bool:
        return self.child_rule_terminal or self.child_tb_exact


@dataclass(frozen=True, slots=True)
class ParentComparisonV1:
    parent_id: int
    decision_match: bool
    final_result_match: bool
    allocation_decision: dict[str, object]
    projection_receipt: dict[str, object]
    projection_receipt_raw: bytes
    reconstructed_legacy_result: legacy.ParentResult
    projection_input_sha256: str
    decision_input_sha256: str
    decision_output_sha256: str
    shadow_choice: int
    reference_choice: int
    regret_cp: int
    full_nodes: int
    shadow_nodes5: int
    shadow_nodes50: int
    shadow_nodes200: int
    shadow_nodes: int
    postseal_q200_selection_reads: int
    postseal_q200_reference_reads: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path_alias_key(path: Path) -> str:
    # Conservative case folding also protects a Linux Python process writing
    # through a case-insensitive mounted filesystem (for example WSL DrvFS).
    return os.path.normcase(os.path.normpath(str(path.resolve(strict=False)))).casefold()


def _strict_int(text: object, name: str, lo: int, hi: int) -> int:
    if type(text) is not str:
        raise EquivalenceError(f"{name} must be a strict decimal integer")
    if not text or not text.isascii() or not text.isdigit():
        if text.startswith("-") and text[1:].isascii() and text[1:].isdigit():
            value = -int(text[1:])
        else:
            raise EquivalenceError(f"{name} must be a strict decimal integer")
    else:
        value = int(text)
    if not lo <= value <= hi:
        raise EquivalenceError(f"{name} outside [{lo},{hi}]")
    return value


def _phase(parent_pieces: int) -> str:
    if 30 <= parent_pieces <= 40:
        return "P0"
    if 20 <= parent_pieces <= 29:
        return "P1"
    if 12 <= parent_pieces <= 19:
        return "P2"
    if 9 <= parent_pieces <= 11:
        return "P3"
    raise EquivalenceError(f"parent_pieces {parent_pieces} has no historical B1 phase")


def _open_tsv(path: Path):
    try:
        raw = path.open("rb")
        if raw.read(2) != b"\x1f\x8b":
            raw.close()
            raise EquivalenceError("historical groups input must be the authenticated gzip artifact")
        raw.seek(0)
        return gzip.open(raw, mode="rt", encoding="utf-8", newline="")
    except OSError as exc:
        raise EquivalenceError(f"cannot open historical groups: {exc}") from exc


def load_historical_groups(path: Path, expected_sha256: str) -> list[HistoricalRowV1]:
    if expected_sha256 != EXPECTED_GROUPS_SHA256:
        raise EquivalenceError("expected groups SHA is not the frozen teacher-1574 identity")
    try:
        actual_sha256 = _sha256(path.read_bytes())
    except OSError as exc:
        raise EquivalenceError(f"cannot hash historical groups: {exc}") from exc
    if actual_sha256 != expected_sha256:
        raise EquivalenceError(
            f"historical groups SHA mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    rows: list[HistoricalRowV1] = []
    seen: set[int] = set()
    with _open_tsv(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise EquivalenceError("missing historical TSV header")
        missing = sorted(SOURCE_COLUMNS.difference(reader.fieldnames))
        if missing:
            raise EquivalenceError("missing historical TSV columns: " + ", ".join(missing))
        for line_number, record in enumerate(reader, 2):
            prefix = f"line {line_number}"
            row_index = _strict_int(record["row_index"], f"{prefix} row_index", 0, projection.INT64_MAX)
            if row_index in seen:
                raise EquivalenceError(f"duplicate row_index {row_index}")
            seen.add(row_index)
            terminal = _strict_int(record["child_rule_terminal"], f"{prefix} terminal", 0, 1)
            tb_exact = _strict_int(record["child_tb_exact"], f"{prefix} tb_exact", 0, 1)
            utility = _strict_int(record["exact_parent_utility"], f"{prefix} utility", -1, 2)
            if bool(terminal or tb_exact) != (utility in (-1, 0, 1)):
                raise EquivalenceError(f"{prefix} exactness/utility mismatch")
            rows.append(HistoricalRowV1(
                row_index=row_index,
                parent_id=_strict_int(record["parent_id"], f"{prefix} parent_id", 0, projection.INT64_MAX),
                parent_stm=_strict_int(record["parent_stm"], f"{prefix} parent_stm", 0, 1),
                parent_pieces=_strict_int(record["parent_pieces"], f"{prefix} parent_pieces", 9, 40),
                child_rule_terminal=bool(terminal),
                child_tb_exact=bool(tb_exact),
                exact_parent_utility=utility,
                q5k_parent=_strict_int(record["q5k_parent"], f"{prefix} q5k", projection.INT32_MIN, projection.INT32_MAX),
                q50_parent=_strict_int(record["q50_parent"], f"{prefix} q50", projection.INT32_MIN, projection.INT32_MAX),
                q200_parent=_strict_int(record["q200_parent"], f"{prefix} q200", projection.INT32_MIN, projection.INT32_MAX),
                nodes5k=_strict_int(record["nodes5k"], f"{prefix} nodes5k", 0, projection.UINT64_MAX),
                nodes50k=_strict_int(record["nodes50k"], f"{prefix} nodes50k", 0, projection.UINT64_MAX),
                nodes200k=_strict_int(record["nodes200k"], f"{prefix} nodes200k", 0, projection.UINT64_MAX),
            ))
    if len(rows) != EXPECTED_ROWS:
        raise EquivalenceError(f"historical row count must be {EXPECTED_ROWS}, got {len(rows)}")
    if len({row.parent_id for row in rows}) != EXPECTED_PARENTS:
        raise EquivalenceError(f"historical parent count must be {EXPECTED_PARENTS}")
    return rows


def projection_parent(rows: list[HistoricalRowV1]) -> dict[str, object]:
    """Build the only object passed to the allocation projector; q200 is absent."""
    if not rows:
        raise EquivalenceError("empty parent")
    ordered = sorted(rows, key=lambda row: row.row_index)
    parent_id = ordered[0].parent_id
    stms = {row.parent_stm for row in ordered}
    pieces = {row.parent_pieces for row in ordered}
    if {row.parent_id for row in ordered} != {parent_id} or len(stms) != 1 or len(pieces) != 1:
        raise EquivalenceError(f"parent {parent_id}: inconsistent parent metadata")
    return {
        "schema": projection.INPUT_SCHEMA,
        "parent_id": parent_id,
        "phase": _phase(ordered[0].parent_pieces),
        "stm": ordered[0].parent_stm,
        "rows": [{
            "row_index": row.row_index,
            "child_rule_terminal": row.child_rule_terminal,
            "child_tb_exact": row.child_tb_exact,
            "exact_parent_utility": row.exact_parent_utility,
            "q5k_parent": row.q5k_parent,
            "q50_parent": row.q50_parent,
            "nodes5k": row.nodes5k,
            "nodes50k": row.nodes50k,
            "nodes200k": row.nodes200k,
        } for row in ordered],
    }


def _legacy_rows(rows: list[HistoricalRowV1]) -> list[legacy.Row]:
    return [legacy.Row(
        row_index=row.row_index,
        parent_id=row.parent_id,
        exact=row.exact,
        exact_utility=row.exact_parent_utility if row.exact else None,
        q5=row.q5k_parent,
        q50=row.q50_parent,
        q200=row.q200_parent,
        n5=row.nodes5k,
        n50=row.nodes50k,
        n200=row.nodes200k,
    ) for row in rows]


class _PostsealQ200:
    def __init__(self, rows: list[HistoricalRowV1]) -> None:
        self._values = {row.row_index: row.q200_parent for row in rows}
        self.selection_reads = 0
        self.reference_reads = 0

    def selection(self, row_index: int) -> int:
        self.selection_reads += 1
        return self._values[row_index]

    def reference(self, row_index: int) -> int:
        self.reference_reads += 1
        return self._values[row_index]


def _postseal_result(
    rows: list[HistoricalRowV1], receipt: dict[str, object]
) -> tuple[legacy.ParentResult, _PostsealQ200]:
    ordered = sorted(rows, key=lambda row: row.row_index)
    by_index = {row.row_index: row for row in ordered}
    q200 = _PostsealQ200(ordered)

    prechoice = receipt["pre_q200_choice_row_or_null"]
    if prechoice is None:
        charge_rows = receipt["S200_charge_rows"]
        if not charge_rows:
            raise EquivalenceError("sealed decision has neither prechoice nor q200 charge rows")
        shadow_choice = min(charge_rows, key=lambda index: (-q200.selection(index), index))
    else:
        shadow_choice = prechoice

    exact_wins = [row for row in ordered if row.exact and row.exact_parent_utility == 1]
    if exact_wins:
        reference = min(exact_wins, key=lambda row: row.row_index)
    else:
        unresolved = [row for row in ordered if not row.exact]
        if unresolved:
            reference = min(unresolved, key=lambda row: (-q200.reference(row.row_index), row.row_index))
        else:
            exact_draws = [row for row in ordered if row.exact_parent_utility == 0]
            reference = min(exact_draws or ordered, key=lambda row: row.row_index)

    reference_legacy = _legacy_rows([reference])[0]
    chosen_legacy = _legacy_rows([by_index[shadow_choice]])[0]
    s5 = set(receipt["S5_rows"])
    s50 = set(receipt["S50_rows"])
    survivors50 = tuple(row.row_index for row in sorted(
        (row for row in ordered if row.row_index in s5), key=lambda row: (-row.q5k_parent, row.row_index)
    ))
    survivors200 = tuple(row.row_index for row in sorted(
        (row for row in ordered if row.row_index in s50), key=lambda row: (-row.q50_parent, row.row_index)
    ))
    result = legacy.ParentResult(
        parent_id=ordered[0].parent_id,
        siblings=len(ordered),
        exact_siblings=sum(row.exact for row in ordered),
        survivors50=survivors50,
        survivors200=survivors200,
        shadow_choice=shadow_choice,
        reference_choice=reference.row_index,
        full_nodes=sum(row.nodes5k + row.nodes50k + row.nodes200k for row in ordered),
        shadow_nodes=receipt["shadow_nodes_total"],
        regret_cp=legacy._regret_cp(reference_legacy, chosen_legacy),
        exact_win_shortcut=receipt["exact_shortcut_reason"] == "EXACT_WIN",
        uncertified_shadow=receipt["uncertified_shadow"],
    )
    return result, q200


def compare_parent(rows: list[HistoricalRowV1]) -> ParentComparisonV1:
    """Compare one parent; useful for deterministic synthetic contract tests."""
    value = projection_parent(rows)
    if any("q200" in key.lower() for key in value["rows"][0]):
        raise EquivalenceError("q200 leaked into projection input")
    receipt, receipt_raw = projection.project_parent(projection.parse_parent(value))
    if (
        receipt["q200_value_reads"] != 0
        or receipt["q200_label_reads"] != 0
        or receipt["q200_branches"] != 0
        or receipt["nodes200k_policy_reads"] != 0
        or receipt["nodes200k_policy_branches"] != 0
        or receipt["nodes200k_preseal_aggregation_reads"] != 0
    ):
        raise EquivalenceError(f"parent {rows[0].parent_id}: nonzero pre-seal policy counter")
    baseline = legacy.simulate_parent(rows[0].parent_id, _legacy_rows(rows))
    reconstructed, q200 = _postseal_result(rows, receipt)

    exact_wins = [row for row in rows if row.exact and row.exact_parent_utility == 1]
    unresolved = [row for row in rows if not row.exact]
    if exact_wins:
        expected_exact_reason = "EXACT_WIN"
    elif not unresolved:
        expected_exact_reason = (
            "ALL_EXACT_DRAW" if any(row.exact_parent_utility == 0 for row in rows)
            else "ALL_EXACT_LOSS"
        )
    else:
        expected_exact_reason = None

    expected_decision = {
        "ordered_rows": sorted(row.row_index for row in rows),
        "S5_rows": sorted(baseline.survivors50),
        "S50_rows": sorted(baseline.survivors200),
        "S200_charge_rows": [] if baseline.uncertified_shadow else sorted(baseline.survivors200),
        "pre_q200_choice_row_or_null": (
            baseline.shadow_choice if (
                baseline.exact_win_shortcut or baseline.uncertified_shadow
                or not baseline.survivors200
            ) else None
        ),
        "exact_shortcut_reason": expected_exact_reason,
        "sole_survivor_reason": (
            "SOLE_UNRESOLVED_BEFORE_Q200" if baseline.uncertified_shadow else None
        ),
        "uncertified_shadow": baseline.uncertified_shadow,
    }
    actual_decision = {key: receipt[key] for key in expected_decision}
    decision_match = actual_decision == expected_decision
    by_index = {row.row_index: row for row in rows}
    expected_nodes5 = 0 if expected_exact_reason is not None else sum(
        row.nodes5k for row in rows if not row.exact
    )
    expected_nodes50 = sum(by_index[index].nodes50k for index in receipt["S5_rows"])
    expected_nodes200 = sum(
        by_index[index].nodes200k for index in receipt["S200_charge_rows"]
    )
    expected_total = expected_nodes5 + expected_nodes50 + expected_nodes200
    cost_match = (
        receipt["shadow_nodes5"] == expected_nodes5
        and receipt["shadow_nodes50"] == expected_nodes50
        and receipt["shadow_nodes200"] == expected_nodes200
        and receipt["shadow_nodes_total"] == expected_total == baseline.shadow_nodes
    )
    final_match = reconstructed == baseline
    if not decision_match:
        raise EquivalenceError(f"parent {rows[0].parent_id}: allocation decision mismatch")
    if not cost_match:
        raise EquivalenceError(f"parent {rows[0].parent_id}: frozen B1 cost mismatch")
    if not final_match:
        raise EquivalenceError(f"parent {rows[0].parent_id}: frozen B1 result mismatch")
    return ParentComparisonV1(
        parent_id=rows[0].parent_id,
        decision_match=True,
        final_result_match=True,
        allocation_decision=actual_decision,
        projection_receipt=receipt,
        projection_receipt_raw=receipt_raw,
        reconstructed_legacy_result=reconstructed,
        projection_input_sha256=receipt["projection_input_sha256"],
        decision_input_sha256=receipt["decision_input_sha256"],
        decision_output_sha256=receipt["decision_output_sha256"],
        shadow_choice=reconstructed.shadow_choice,
        reference_choice=reconstructed.reference_choice,
        regret_cp=reconstructed.regret_cp,
        full_nodes=reconstructed.full_nodes,
        shadow_nodes5=receipt["shadow_nodes5"],
        shadow_nodes50=receipt["shadow_nodes50"],
        shadow_nodes200=receipt["shadow_nodes200"],
        shadow_nodes=reconstructed.shadow_nodes,
        postseal_q200_selection_reads=q200.selection_reads,
        postseal_q200_reference_reads=q200.reference_reads,
    )


def _legacy_report_bytes(report: dict[str, object]) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _legacy_decisions_bytes(results: list[legacy.ParentResult]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow([
        "parent_id", "siblings", "exact_siblings", "survivors50", "survivors200",
        "shadow_choice", "reference_choice", "full_nodes", "shadow_nodes", "regret_cp",
        "exact_win_shortcut", "uncertified_shadow",
    ])
    for result in results:
        writer.writerow([
            result.parent_id, result.siblings, result.exact_siblings,
            ",".join(map(str, result.survivors50)),
            ",".join(map(str, result.survivors200)),
            result.shadow_choice, result.reference_choice, result.full_nodes,
            result.shadow_nodes, result.regret_cp, int(result.exact_win_shortcut),
            int(result.uncertified_shadow),
        ])
    return output.getvalue().encode("utf-8")


def _canonical_jsonl_values(raw: bytes, name: str) -> list[object]:
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        raise EquivalenceError(f"{name} must be non-empty LF-terminated JSONL")
    values = []
    for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
        try:
            value = json.loads(line)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EquivalenceError(f"{name} line {line_number} is invalid JSON") from exc
        if projection.canonical_json_line(value) != line:
            raise EquivalenceError(f"{name} line {line_number} is not canonical")
        values.append(value)
    return values


def _build_equivalence_bundle(
    rows: list[HistoricalRowV1], groups_sha256: str
) -> tuple[dict[str, object], dict[str, bytes]]:
    if (projection.M5, projection.M50, legacy.M5_CP, legacy.M50_CP) != (100, 60, 100, 60):
        raise EquivalenceError("B1/B2 policy constants are not the frozen 100/60 margins")
    forbidden_decision_fields = sorted(
        field for field in projection.DECISION_ROW_FIELDS if "q200" in field.lower()
    )
    if forbidden_decision_fields:
        raise EquivalenceError(
            f"q200 fields present in projection decision schema: {forbidden_decision_fields}"
        )
    grouped: dict[int, list[HistoricalRowV1]] = defaultdict(list)
    for row in rows:
        grouped[row.parent_id].append(row)
    if len(rows) != EXPECTED_ROWS or len(grouped) != EXPECTED_PARENTS:
        raise EquivalenceError("historical 8000-parent/74449-row cardinality mismatch")

    comparisons = [compare_parent(grouped[parent_id]) for parent_id in sorted(grouped)]
    legacy_rows = _legacy_rows(rows)
    b1_report, _ = legacy.build_report(legacy_rows)
    for key, expected in EXPECTED_B1_AGGREGATE.items():
        if b1_report.get(key) != expected:
            raise EquivalenceError(
                f"frozen B1 aggregate {key} mismatch: expected {expected!r}, got {b1_report.get(key)!r}"
            )
    b1_report_sha256 = _sha256(_legacy_report_bytes(b1_report))
    if b1_report_sha256 != EXPECTED_B1_REPORT_SHA256:
        raise EquivalenceError(
            f"frozen B1 report SHA mismatch: expected {EXPECTED_B1_REPORT_SHA256}, got {b1_report_sha256}"
        )

    projection_receipts = b"".join(item.projection_receipt_raw for item in comparisons)
    reconstructed_results = [item.reconstructed_legacy_result for item in comparisons]
    legacy_decisions = _legacy_decisions_bytes(reconstructed_results)
    legacy_report_raw = _legacy_report_bytes(b1_report)
    postseal_ledger = b"".join(projection.canonical_json_line({
        "schema": "jass.adaptive_sibling_b2_postseal_q200_join_parent.v1",
        "parent_id": item.parent_id,
        "shadow_choice": item.shadow_choice,
        "reference_choice": item.reference_choice,
        "regret_cp": item.regret_cp,
        "postseal_q200_selection_reads": item.postseal_q200_selection_reads,
        "postseal_q200_reference_reads": item.postseal_q200_reference_reads,
    }) for item in comparisons)
    empty_diff = projection.canonical_json_line({
        "schema": "jass.adaptive_sibling_b2_legacy_equivalence_diff.v1",
        "parents_compared": len(comparisons),
        "differences": [],
    })
    artifacts = {
        "projection_receipts": projection_receipts,
        "legacy_decisions": legacy_decisions,
        "legacy_report": legacy_report_raw,
        "postseal_join": postseal_ledger,
        "empty_diff": empty_diff,
    }

    projection_values = _canonical_jsonl_values(projection_receipts, "projection receipts")
    postseal_values = _canonical_jsonl_values(postseal_ledger, "postseal ledger")
    if len(projection_values) != len(comparisons) or len(postseal_values) != len(comparisons):
        raise EquivalenceError("published parent-artifact cardinality mismatch")
    if [value["parent_id"] for value in projection_values] != [item.parent_id for item in comparisons]:
        raise EquivalenceError("projection receipt roundtrip parent order mismatch")
    if [value["parent_id"] for value in postseal_values] != [item.parent_id for item in comparisons]:
        raise EquivalenceError("postseal ledger roundtrip parent order mismatch")
    if json.loads(legacy_report_raw) != b1_report:
        raise EquivalenceError("legacy report roundtrip mismatch")
    diff_value = _canonical_jsonl_values(empty_diff, "empty diff")
    if len(diff_value) != 1 or diff_value[0]["differences"] != []:
        raise EquivalenceError("equivalence diff is not empty")
    with io.StringIO(legacy_decisions.decode("utf-8"), newline="") as handle:
        decision_rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(decision_rows) != len(comparisons):
        raise EquivalenceError("legacy decisions roundtrip parent count mismatch")
    if [int(value["parent_id"]) for value in decision_rows] != [item.parent_id for item in comparisons]:
        raise EquivalenceError("legacy decisions roundtrip parent order mismatch")
    phase_counts: dict[str, int] = defaultdict(int)
    stm_counts: dict[str, int] = defaultdict(int)
    for parent_rows in grouped.values():
        phase_counts[_phase(parent_rows[0].parent_pieces)] += 1
        stm_counts[str(parent_rows[0].parent_stm)] += 1

    report = {
        "schema": SCHEMA,
        "verdict": "B1_HISTORICAL_PROJECTION_EQUIVALENCE_COMPLETE",
        "source": {
            "job_id": "cpx62-1574-l3-deep-sibling-teacher-v2",
            "attempt_id": "20260826T185527Z-a6da4a0b",
            "groups_sha256": groups_sha256,
            "parents": len(grouped),
            "rows": len(rows),
        },
        "frozen_b1": {
            "job_id": "cpx62-1769-l3-decision-math-adaptive-shadow-b1-v1",
            "attempt_id": "20260904T221533Z-db6e6a5c",
            "report_sha256": b1_report_sha256,
            "aggregate": {key: b1_report[key] for key in EXPECTED_B1_AGGREGATE},
        },
        "policy": {"M5": projection.M5, "M50": projection.M50, "minimum_survivors": 2},
        "equivalence": {
            "parents_compared": len(comparisons),
            "allocation_decision_matches": sum(item.decision_match for item in comparisons),
            "final_b1_result_matches": sum(item.final_result_match for item in comparisons),
            "phase_parent_counts": dict(sorted(phase_counts.items())),
            "stm_parent_counts": dict(sorted(stm_counts.items())),
        },
        "information_barrier": {
            "q200_fields_in_projection_decision": len(forbidden_decision_fields),
            "q200_policy_reads": sum(
                item.projection_receipt["q200_value_reads"]
                + item.projection_receipt["q200_label_reads"]
                for item in comparisons
            ),
            "q200_value_reads": sum(
                item.projection_receipt["q200_value_reads"] for item in comparisons
            ),
            "q200_label_reads": sum(
                item.projection_receipt["q200_label_reads"] for item in comparisons
            ),
            "q200_policy_branches": sum(
                item.projection_receipt["q200_branches"] for item in comparisons
            ),
            "nodes200k_policy_reads": sum(
                item.projection_receipt["nodes200k_policy_reads"] for item in comparisons
            ),
            "nodes200k_policy_branches": sum(
                item.projection_receipt["nodes200k_policy_branches"] for item in comparisons
            ),
            "nodes200k_preseal_aggregation_reads": sum(
                item.projection_receipt["nodes200k_preseal_aggregation_reads"]
                for item in comparisons
            ),
            "nodes200k_validated_rows": sum(
                item.projection_receipt["nodes200k_validated_rows"] for item in comparisons
            ),
            "nodes200k_aggregation_reads": sum(
                item.projection_receipt["nodes200k_aggregation_reads"] for item in comparisons
            ),
            "postseal_q200_selection_reads": sum(item.postseal_q200_selection_reads for item in comparisons),
            "postseal_q200_reference_reads": sum(item.postseal_q200_reference_reads for item in comparisons),
            "allocation_hash_excludes_q200_values": True,
            "postseal_join_hash_includes_q200_results": True,
        },
        "historical_semantic_scope": {
            "allocation_sets_choices_costs_and_b1_aggregate_compared": True,
            "phase_derived_from_historical_parent_pieces": True,
            "stm_read_from_historical_parent_stm": True,
            "complete_move_identity_compared": False,
            "captured_square_bitboard_compared": False,
            "score_provenance_or_signal_family_compared": False,
            "fresh_confirmation_claimed": False,
            "b2_gate_claimed": False,
        },
        "published_artifacts": {
            name: {
                "filename": COMPANION_FILENAMES[name],
                "sha256": _sha256(raw),
                "size_bytes": len(raw),
            }
            for name, raw in artifacts.items()
        },
        "searches": 0,
        "fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
        "real_adaptive_teacher_authorized": False,
    }
    return report, artifacts


def build_equivalence_report(rows: list[HistoricalRowV1], groups_sha256: str) -> dict[str, object]:
    report, _ = _build_equivalence_bundle(rows, groups_sha256)
    return report


def run(groups: Path, expected_groups_sha256: str, out_report: Path) -> dict[str, object]:
    companion_paths = {
        name: out_report.parent / filename for name, filename in COMPANION_FILENAMES.items()
    }
    output_paths = [out_report, *companion_paths.values()]
    temporary_paths = [path.with_name(path.name + ".tmp") for path in output_paths]
    paths = [groups, *output_paths, *temporary_paths]
    if len({_path_alias_key(path) for path in paths}) != len(paths):
        raise EquivalenceError("input, outputs, and temporary paths must be pairwise distinct")
    if any(path.exists() for path in [*output_paths, *temporary_paths]):
        raise EquivalenceError("output or temporary output already exists")
    rows = load_historical_groups(groups, expected_groups_sha256)
    report, artifacts = _build_equivalence_bundle(rows, expected_groups_sha256)
    output_raw = {out_report: projection.canonical_json_line(report)}
    output_raw.update({companion_paths[name]: raw for name, raw in artifacts.items()})
    out_report.parent.mkdir(parents=True, exist_ok=True)
    try:
        for path, raw in output_raw.items():
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_bytes(raw)
            if temporary.read_bytes() != raw:
                raise EquivalenceError(f"temporary artifact byte verification failed: {path.name}")
        for path in output_raw:
            os.replace(path.with_name(path.name + ".tmp"), path)
        for path, raw in output_raw.items():
            if path.read_bytes() != raw:
                raise EquivalenceError(f"published artifact byte verification failed: {path.name}")
        parsed_report = _canonical_jsonl_values(out_report.read_bytes(), "equivalence report")
        if parsed_report != [report]:
            raise EquivalenceError("equivalence report roundtrip mismatch")
    except Exception:
        for path in [*temporary_paths, *output_paths]:
            path.unlink(missing_ok=True)
        raise
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--expected-groups-sha256", required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run(args.groups, args.expected_groups_sha256, args.out_report)
        print(projection.canonical_json_line({
            "verdict": report["verdict"],
            "parents": report["source"]["parents"],
            "rows": report["source"]["rows"],
            "report_sha256": _sha256(args.out_report.read_bytes()),
        }).decode("ascii"), end="")
        return 0
    except Exception as exc:
        print(f"adaptive_sibling_b2_legacy_equivalence: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
