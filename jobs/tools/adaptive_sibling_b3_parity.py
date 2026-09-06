#!/usr/bin/env python3
"""Compare a real B3 adaptive-teacher run against frozen B2 projection/full observations.

The B2 cohort is already consumed; this checker is an implementation-parity
gate, not a new scientific confirmation. Wall-clock fields are intentionally
excluded. Every actually executed B3 search must reproduce the corresponding B2
full-ladder deterministic observation, while the executed horizon sets and real
node cost must equal the sealed B2 shadow receipt.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import sys
from typing import Iterable, Mapping, Sequence

VERDICT = "B3_REAL_ADAPTIVE_TEACHER_PARITY_ESTABLISHED_V1"
SCHEMA = "jass.adaptive_sibling_b3_parity.v1"

IDENTITY_FIELDS = (
    "row_index", "parent_id", "parent_fingerprint", "parent_stm", "parent_pieces",
    "from", "to", "num_captures", "promotes", "moving_king", "captured_kings",
    "material_count_delta_parent", "child_pieces", "child_legal_moves",
    "child_forced_capture", "child_rule_terminal", "child_tb_exact",
    "exact_parent_utility", "t_baseline_parent",
)
HORIZONS = {
    "5": ("q5k_parent", "nodes5k", "completed_depth5k", "effective_depth5k",
          "aborted5k", "stop5k", "pv5k_enters_egdb", "searched5"),
    "50": ("q50_parent", "nodes50k", "completed_depth50k", "effective_depth50k",
           "aborted50k", "stop50k", "pv50k_enters_egdb", "searched50"),
    "200": ("q200_parent", "nodes200k", "completed_depth200k", "effective_depth200k",
            "aborted200k", "stop200k", "pv200k_enters_egdb", "searched200"),
}
B3_EXTRA = frozenset({
    "searched5", "searched50", "searched200", "survived5", "survived50",
    "selected", "exact_shortcut_reason", "sole_survivor_reason", "uncertified",
})


class ParityError(RuntimeError):
    pass


def read_tsv(path: Path) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ParityError(f"missing TSV header: {path}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise ParityError(f"empty TSV: {path}")
    return rows, tuple(reader.fieldnames)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        raise ParityError("receipt JSONL must be non-empty LF text")
    out = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ParityError(f"bad receipt JSON line {number}") from exc
        if type(value) is not dict:
            raise ParityError(f"receipt line {number} is not object")
        out.append(value)
    return out


def as_int(row: Mapping[str, str], field: str) -> int:
    try:
        return int(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ParityError(f"invalid integer field {field}: {row.get(field)!r}") from exc


def flag(row: Mapping[str, str], field: str) -> bool:
    value = as_int(row, field)
    if value not in (0, 1):
        raise ParityError(f"flag {field} outside 0/1")
    return bool(value)


def canonical_reason(value: object) -> str:
    return "NONE" if value is None else str(value)


def expected_selected(receipt: Mapping[str, object], b2_by_index: Mapping[int, Mapping[str, str]]) -> int:
    pre = receipt.get("pre_q200_choice_row_or_null")
    if type(pre) is int:
        return pre
    charged = receipt.get("S200_charge_rows")
    if type(charged) is not list or not charged:
        raise ParityError(f"parent {receipt.get('parent_id')}: no prechoice and no q200 charge set")
    indices = []
    for value in charged:
        if type(value) is not int or value not in b2_by_index:
            raise ParityError("invalid S200 row")
        indices.append(value)
    return min(indices, key=lambda index: (-as_int(b2_by_index[index], "q200_parent"), index))


def compare(b2_groups: Path, b2_receipts: Path, b3_groups: Path) -> dict[str, object]:
    b2, b2_header = read_tsv(b2_groups)
    b3, b3_header = read_tsv(b3_groups)
    if len(b2) != len(b3):
        raise ParityError(f"row count mismatch B2={len(b2)} B3={len(b3)}")
    if not B3_EXTRA.issubset(b3_header):
        raise ParityError("B3 TSV missing adaptive fields")
    missing_identity = [field for field in IDENTITY_FIELDS if field not in b2_header or field not in b3_header]
    if missing_identity:
        raise ParityError(f"identity fields missing: {missing_identity}")

    b2_by_index: dict[int, dict[str, str]] = {}
    b3_by_index: dict[int, dict[str, str]] = {}
    by_parent: dict[int, list[int]] = defaultdict(list)
    mismatches: list[dict[str, object]] = []

    def mismatch(kind: str, **payload: object) -> None:
        if len(mismatches) < 100:
            mismatches.append({"kind": kind, **payload})

    for left, right in zip(b2, b3):
        li = as_int(left, "row_index")
        ri = as_int(right, "row_index")
        if li != ri:
            mismatch("row_order", b2=li, b3=ri)
            continue
        if li in b2_by_index:
            raise ParityError(f"duplicate row_index {li}")
        b2_by_index[li] = left
        b3_by_index[ri] = right
        parent = as_int(left, "parent_id")
        by_parent[parent].append(li)
        for field in IDENTITY_FIELDS:
            if left[field] != right[field]:
                mismatch("identity", row_index=li, field=field, b2=left[field], b3=right[field])

    receipts = read_jsonl(b2_receipts)
    if len(receipts) != 4000:
        raise ParityError(f"expected 4000 receipts, got {len(receipts)}")
    receipt_by_parent = {}
    for receipt in receipts:
        parent = receipt.get("parent_id")
        if type(parent) is not int or parent in receipt_by_parent:
            raise ParityError("invalid/duplicate receipt parent_id")
        receipt_by_parent[parent] = receipt
    if set(receipt_by_parent) != set(range(4000)):
        raise ParityError("receipt parent population must be 0..3999")
    if set(by_parent) != set(range(4000)):
        raise ParityError("group parent population must be 0..3999")

    actual_searches = {"5": 0, "50": 0, "200": 0}
    actual_nodes = {"5": 0, "50": 0, "200": 0}
    zero_cost_parents: list[int] = []

    for parent in range(4000):
        receipt = receipt_by_parent[parent]
        row_ids = sorted(by_parent[parent])
        s5 = set(receipt.get("S5_rows", []))
        s50 = set(receipt.get("S50_rows", []))
        s200 = set(receipt.get("S200_charge_rows", []))
        exact_reason = canonical_reason(receipt.get("exact_shortcut_reason"))
        sole_reason = canonical_reason(receipt.get("sole_survivor_reason"))
        expected_choice = expected_selected(receipt, b2_by_index)
        selected = []
        parent_nodes = 0

        for row_id in row_ids:
            left = b2_by_index[row_id]
            right = b3_by_index[row_id]
            exact = as_int(left, "child_rule_terminal") == 1 or as_int(left, "child_tb_exact") == 1
            expected5 = exact_reason == "NONE" and not exact
            expected50 = row_id in s5
            expected200 = row_id in s200
            expected_flags = {
                "searched5": expected5,
                "searched50": expected50,
                "searched200": expected200,
                "survived5": row_id in s5,
                "survived50": row_id in s50,
            }
            for field, expected in expected_flags.items():
                if flag(right, field) != expected:
                    mismatch("stage_set", parent_id=parent, row_index=row_id,
                             field=field, expected=expected, actual=flag(right, field))
            if right["exact_shortcut_reason"] != exact_reason:
                mismatch("exact_reason", parent_id=parent, row_index=row_id,
                         expected=exact_reason, actual=right["exact_shortcut_reason"])
            if right["sole_survivor_reason"] != sole_reason:
                mismatch("sole_reason", parent_id=parent, row_index=row_id,
                         expected=sole_reason, actual=right["sole_survivor_reason"])
            if flag(right, "uncertified") != bool(receipt.get("uncertified_shadow")):
                mismatch("uncertified", parent_id=parent, row_index=row_id)
            if flag(right, "selected"):
                selected.append(row_id)

            for horizon, fields in HORIZONS.items():
                score, nodes, completed, effective, aborted, stop, pv, searched = fields
                is_searched = flag(right, searched)
                if is_searched:
                    actual_searches[horizon] += 1
                    actual_nodes[horizon] += as_int(right, nodes)
                    parent_nodes += as_int(right, nodes)
                    for field in (score, nodes, completed, effective, aborted, stop, pv):
                        if left[field] != right[field]:
                            mismatch("search_observation", parent_id=parent, row_index=row_id,
                                     horizon=horizon, field=field,
                                     b2=left[field], b3=right[field])
                else:
                    if as_int(right, nodes) != 0:
                        mismatch("unsearched_nonzero_nodes", parent_id=parent,
                                 row_index=row_id, horizon=horizon,
                                 nodes=as_int(right, nodes))

        if selected != [expected_choice]:
            mismatch("selected", parent_id=parent, expected=expected_choice, actual=selected)
        expected_nodes = receipt.get("shadow_nodes_total")
        if type(expected_nodes) is not int or parent_nodes != expected_nodes:
            mismatch("parent_nodes", parent_id=parent, expected=expected_nodes, actual=parent_nodes)
        if expected_nodes == 0:
            zero_cost_parents.append(parent)

    success = not mismatches
    return {
        "schema": SCHEMA,
        "state": "completed" if success else "blocked",
        "verdict": VERDICT if success else "B3_REAL_ADAPTIVE_TEACHER_PARITY_BLOCKED_V1",
        "parents": 4000,
        "rows": len(b2),
        "mismatches": mismatches,
        "mismatch_count_capped": len(mismatches),
        "actual_searches": actual_searches,
        "actual_nodes": actual_nodes,
        "total_nodes": sum(actual_nodes.values()),
        "zero_cost_parent_ids": zero_cost_parents,
        "projection_policy": {"M5": 100, "M50": 60, "minimum_survivors": 2},
        "elapsed_fields_compared": False,
        "fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
        "bake_authorized": False,
        "fresh_b3_generation_authorized": success,
    }


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b2-groups", type=Path, required=True)
    parser.add_argument("--b2-receipts", type=Path, required=True)
    parser.add_argument("--b3-groups", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = compare(args.b2_groups, args.b2_receipts, args.b3_groups)
        if args.out.exists() or args.out.is_symlink():
            raise ParityError("output already exists")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(canonical(report))
        print(canonical({"verdict": report["verdict"], "parents": report["parents"],
                         "total_nodes": report["total_nodes"]}).decode("ascii"), end="")
        return 0 if report["verdict"] == VERDICT else 4
    except Exception as exc:
        print(f"adaptive_sibling_b3_parity: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
