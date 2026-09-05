#!/usr/bin/env python3
"""Project the frozen B1 allocation policy without any q200 value or label.

Input is identity/exactness, q5k/q50 values and opaque node costs only.  The
decision pass receives a type with no ``nodes200k`` member.  A second pass sums
that cost for the already sealed S200 charge rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping


INPUT_SCHEMA = "jass.adaptive_sibling_b2_projection_input_parent.v1"
RECEIPT_SCHEMA = "jass.adaptive_sibling_b2_allocation_receipt_parent.v1"
MANIFEST_SCHEMA = "jass.adaptive_sibling_b2_projection_manifest.v1"
M5 = 100
M50 = 60
INT8_MIN, INT8_MAX = -(1 << 7), (1 << 7) - 1
INT32_MIN, INT32_MAX = -(1 << 31), (1 << 31) - 1
INT64_MIN, INT64_MAX = -(1 << 63), (1 << 63) - 1
UINT64_MAX = (1 << 64) - 1
PHASES = {"P0", "P1", "P2", "P3"}
EXACT_SHORTCUT_REASONS = frozenset({"EXACT_WIN", "ALL_EXACT_DRAW", "ALL_EXACT_LOSS"})
SOLE_SURVIVOR_REASONS = frozenset({"SOLE_UNRESOLVED_BEFORE_Q200"})
PARENT_FIELDS = {"schema", "parent_id", "phase", "stm", "rows"}
ROW_FIELDS = {
    "row_index", "child_rule_terminal", "child_tb_exact", "exact_parent_utility",
    "q5k_parent", "q50_parent", "nodes5k", "nodes50k", "nodes200k",
}
DECISION_ROW_FIELDS = ROW_FIELDS - {"nodes200k"}


class ProjectionError(RuntimeError):
    """A strict input, policy, arithmetic, or output contract failure."""


@dataclass(frozen=True, slots=True)
class AllocationRowV1:
    row_index: int
    child_rule_terminal: bool
    child_tb_exact: bool
    exact_parent_utility: int
    q5k_parent: int
    q50_parent: int
    nodes5k: int
    nodes50k: int
    nodes200k: int


@dataclass(frozen=True, slots=True)
class AllocationParentV1:
    parent_id: int
    phase: str
    stm: int
    rows: tuple[AllocationRowV1, ...]


@dataclass(frozen=True, slots=True)
class DecisionRowV1:
    """The policy-visible row type deliberately has no nodes200k member."""

    row_index: int
    child_rule_terminal: bool
    child_tb_exact: bool
    exact_parent_utility: int
    q5k_parent: int
    q50_parent: int
    nodes5k: int
    nodes50k: int

    @property
    def exact(self) -> bool:
        return self.child_rule_terminal or self.child_tb_exact


@dataclass(frozen=True, slots=True)
class ProjectionDecisionInputV1:
    parent_id: int
    phase: str
    stm: int
    rows: tuple[DecisionRowV1, ...]


@dataclass(frozen=True, slots=True)
class CostRows200V1:
    """Ingress-validated costs kept outside the object passed to policy."""

    costs_by_row: Mapping[int, int]
    validated_rows: int


@dataclass(frozen=True, slots=True)
class ParsedAllocationParentV1:
    decision: ProjectionDecisionInputV1
    costs200: CostRows200V1
    projection_input_sha256: str


@dataclass(frozen=True, slots=True)
class SealedDecisionV1:
    parent_id: int
    ordered_rows: tuple[int, ...]
    S5_rows: tuple[int, ...]
    S50_rows: tuple[int, ...]
    S200_charge_rows: tuple[int, ...]
    pre_q200_choice_row_or_null: int | None
    exact_shortcut_reason: str | None
    sole_survivor_reason: str | None
    uncertified_shadow: bool


def canonical_json_line(value: object) -> bytes:
    try:
        text = json.dumps(
            value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError) as exc:
        raise ProjectionError(f"value is not canonical-JSON serializable: {exc}") from exc
    return (text + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectionError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _strict_int(value: object, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise ProjectionError(f"{name} must be an integer in [{lo},{hi}]")
    return value


def _strict_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ProjectionError(f"{name} must be a JSON boolean")
    return value


def _object(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ProjectionError(f"{name} must be a JSON object")
    return value


def _reject_forbidden_q200_keys(value: object, location: str = "input") -> None:
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise ProjectionError(f"{location} contains a non-string key")
            if "q200" in key.lower() and key != "nodes200k":
                raise ProjectionError(f"{location} contains forbidden q200 key {key!r}")
        for key in value:
            _reject_forbidden_q200_keys(value[key], f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_q200_keys(item, f"{location}[{index}]")


def parse_parent(value: object) -> ParsedAllocationParentV1:
    _reject_forbidden_q200_keys(value)
    parent = _object(value, "parent")
    if set(parent) != PARENT_FIELDS:
        raise ProjectionError(f"parent fields mismatch: {sorted(parent)}")
    if parent["schema"] != INPUT_SCHEMA or type(parent["schema"]) is not str:
        raise ProjectionError("parent schema mismatch")
    parent_id = _strict_int(parent["parent_id"], "parent_id", INT64_MIN, INT64_MAX)
    phase = parent["phase"]
    if type(phase) is not str or phase not in PHASES:
        raise ProjectionError("phase must be one of P0..P3")
    stm = _strict_int(parent["stm"], "stm", 0, 1)
    raw_rows = parent["rows"]
    if type(raw_rows) is not list or len(raw_rows) < 2:
        raise ProjectionError("parent rows must be a JSON array with at least two siblings")
    rows = []
    seen = set()
    for offset, raw_row in enumerate(raw_rows):
        row = _object(raw_row, f"row[{offset}]")
        if set(row) != ROW_FIELDS:
            raise ProjectionError(f"row[{offset}] fields mismatch: {sorted(row)}")
        row_index = _strict_int(row["row_index"], "row_index", INT64_MIN, INT64_MAX)
        if row_index in seen:
            raise ProjectionError(f"duplicate row_index {row_index}")
        seen.add(row_index)
        terminal = _strict_bool(row["child_rule_terminal"], "child_rule_terminal")
        tb_exact = _strict_bool(row["child_tb_exact"], "child_tb_exact")
        utility = _strict_int(
            row["exact_parent_utility"], "exact_parent_utility", INT8_MIN, INT8_MAX
        )
        if terminal or tb_exact:
            if utility not in (-1, 0, 1):
                raise ProjectionError("exact row utility must be -1, 0, or 1")
        elif utility != 2:
            raise ProjectionError("non-exact row utility must use sentinel 2")
        rows.append(AllocationRowV1(
            row_index=row_index,
            child_rule_terminal=terminal,
            child_tb_exact=tb_exact,
            exact_parent_utility=utility,
            q5k_parent=_strict_int(row["q5k_parent"], "q5k_parent", INT32_MIN, INT32_MAX),
            q50_parent=_strict_int(row["q50_parent"], "q50_parent", INT32_MIN, INT32_MAX),
            nodes5k=_strict_int(row["nodes5k"], "nodes5k", 0, UINT64_MAX),
            nodes50k=_strict_int(row["nodes50k"], "nodes50k", 0, UINT64_MAX),
            nodes200k=_strict_int(row["nodes200k"], "nodes200k", 0, UINT64_MAX),
        ))
    rows.sort(key=lambda row: row.row_index)
    full_parent = AllocationParentV1(parent_id, phase, stm, tuple(rows))
    full_input_hash = sha256(canonical_json_line(full_input_object(full_parent)))
    separated_decision = decision_input(full_parent)
    separated_costs = CostRows200V1(
        MappingProxyType({row.row_index: row.nodes200k for row in rows}), len(rows)
    )
    return ParsedAllocationParentV1(separated_decision, separated_costs, full_input_hash)


def full_input_object(parent: AllocationParentV1) -> dict[str, object]:
    return {
        "schema": INPUT_SCHEMA,
        "parent_id": parent.parent_id,
        "phase": parent.phase,
        "stm": parent.stm,
        "rows": [asdict(row) for row in parent.rows],
    }


def decision_input(parent: AllocationParentV1) -> ProjectionDecisionInputV1:
    return ProjectionDecisionInputV1(
        parent.parent_id, parent.phase, parent.stm,
        tuple(DecisionRowV1(
            row.row_index, row.child_rule_terminal, row.child_tb_exact,
            row.exact_parent_utility, row.q5k_parent, row.q50_parent,
            row.nodes5k, row.nodes50k,
        ) for row in parent.rows),
    )


def decision_input_object(parent: ProjectionDecisionInputV1) -> dict[str, object]:
    return {
        # The canonical decision view is the full input with only nodes200k
        # omitted, including preservation of the wire schema identifier.
        "schema": INPUT_SCHEMA,
        "parent_id": parent.parent_id,
        "phase": parent.phase,
        "stm": parent.stm,
        "rows": [asdict(row) for row in parent.rows],
    }


def _top_with_margin(
    rows: tuple[DecisionRowV1, ...], field: str, margin: int,
) -> tuple[DecisionRowV1, ...]:
    ranked = sorted(rows, key=lambda row: (-getattr(row, field), row.row_index))
    if not ranked:
        return ()
    best = getattr(ranked[0], field)
    selected = {row.row_index for row in ranked if best - getattr(row, field) <= margin}
    selected.update(row.row_index for row in ranked[:min(2, len(ranked))])
    return tuple(sorted((row for row in ranked if row.row_index in selected),
                        key=lambda row: row.row_index))


def seal_decision(parent: ProjectionDecisionInputV1) -> SealedDecisionV1:
    rows = parent.rows
    ordered = tuple(row.row_index for row in rows)
    exact_wins = tuple(row for row in rows if row.exact and row.exact_parent_utility == 1)
    if exact_wins:
        choice = min(row.row_index for row in exact_wins)
        return SealedDecisionV1(parent.parent_id, ordered, (), (), (), choice,
                                "EXACT_WIN", None, False)
    unresolved = tuple(row for row in rows if not row.exact)
    if not unresolved:
        exact_draws = tuple(row for row in rows if row.exact_parent_utility == 0)
        if exact_draws:
            choice = min(row.row_index for row in exact_draws)
            reason = "ALL_EXACT_DRAW"
        else:
            choice = min(row.row_index for row in rows)
            reason = "ALL_EXACT_LOSS"
        return SealedDecisionV1(parent.parent_id, ordered, (), (), (), choice,
                                reason, None, False)
    s5 = _top_with_margin(unresolved, "q5k_parent", M5)
    s50 = _top_with_margin(s5, "q50_parent", M50)
    if len(s50) == 1:
        choice = s50[0].row_index
        charge = ()
        sole_reason = "SOLE_UNRESOLVED_BEFORE_Q200"
        uncertified = True
    else:
        choice = None
        charge = tuple(row.row_index for row in s50)
        sole_reason = None
        uncertified = False
    return SealedDecisionV1(
        parent.parent_id, ordered,
        tuple(row.row_index for row in s5),
        tuple(row.row_index for row in s50),
        charge, choice, None, sole_reason, uncertified,
    )


def decision_output_object(sealed: SealedDecisionV1) -> dict[str, object]:
    return {
        "parent_id": sealed.parent_id,
        "ordered_rows": list(sealed.ordered_rows),
        "S5_rows": list(sealed.S5_rows),
        "S50_rows": list(sealed.S50_rows),
        "S200_charge_rows": list(sealed.S200_charge_rows),
        "pre_q200_choice_row_or_null": sealed.pre_q200_choice_row_or_null,
        "exact_shortcut_reason": sealed.exact_shortcut_reason,
        "sole_survivor_reason": sealed.sole_survivor_reason,
        "uncertified_shadow": sealed.uncertified_shadow,
    }


def _checked_sum(values: Iterable[int], name: str) -> int:
    total = 0
    for value in values:
        if total > UINT64_MAX - value:
            raise ProjectionError(f"{name} uint64 overflow")
        total += value
    return total


def project_parent(parent: ParsedAllocationParentV1) -> tuple[dict[str, object], bytes]:
    decision = parent.decision
    decision_object = decision_input_object(decision)
    decision_input_hash = sha256(canonical_json_line(decision_object))
    sealed = seal_decision(decision)
    sealed_object = decision_output_object(sealed)
    decision_output_hash = sha256(canonical_json_line(sealed_object))

    rows = {row.row_index: row for row in decision.rows}
    # An exact shortcut terminates before the staged allocation starts, so it
    # incurs no q5 cost.  Otherwise every unresolved child receives q5.
    nodes5_ids = () if sealed.exact_shortcut_reason is not None else tuple(
        row.row_index for row in decision.rows if not row.exact
    )
    nodes5 = _checked_sum((rows[index].nodes5k for index in nodes5_ids), "shadow_nodes5")
    nodes50 = _checked_sum((rows[index].nodes50k for index in sealed.S5_rows), "shadow_nodes50")
    # This is the only policy-pipeline access to nodes200k.  Charge rows and all
    # decision fields are already sealed above; the pass only performs a sum.
    nodes200 = _checked_sum(
        (parent.costs200.costs_by_row[index] for index in sealed.S200_charge_rows),
        "shadow_nodes200",
    )
    total = _checked_sum((nodes5, nodes50, nodes200), "shadow_nodes_total")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        **sealed_object,
        "shadow_nodes5": nodes5,
        "shadow_nodes50": nodes50,
        "shadow_nodes200": nodes200,
        "shadow_nodes_total": total,
        "projection_input_sha256": parent.projection_input_sha256,
        "decision_input_sha256": decision_input_hash,
        "decision_output_sha256": decision_output_hash,
        "nodes200k_validated_rows": parent.costs200.validated_rows,
        "nodes200k_policy_reads": 0,
        "nodes200k_policy_branches": 0,
        "nodes200k_preseal_aggregation_reads": 0,
        "nodes200k_aggregation_reads": len(sealed.S200_charge_rows),
        "q200_value_reads": 0,
        "q200_label_reads": 0,
        "q200_branches": 0,
    }
    raw = canonical_json_line(receipt)
    return receipt, raw


def load_jsonl(path: Path) -> tuple[list[ParsedAllocationParentV1], bytes]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProjectionError(f"cannot read projection input: {exc}") from exc
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        raise ProjectionError("input JSONL must be non-empty UTF-8 with LF termination")
    parents = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line:
            raise ProjectionError(f"input JSONL has empty line {line_number}")
        try:
            value = json.loads(
                line,
                object_pairs_hook=_unique_json_object,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ProjectionError(f"non-finite JSON constant {value}")
                ),
            )
        except (json.JSONDecodeError, ProjectionError) as exc:
            raise ProjectionError(f"input JSONL line {line_number}: {exc}") from exc
        parents.append(parse_parent(value))
    parent_ids = [parent.decision.parent_id for parent in parents]
    if len(set(parent_ids)) != len(parent_ids):
        raise ProjectionError("duplicate parent_id")
    parents.sort(key=lambda parent: parent.decision.parent_id)
    return parents, raw


def project_file(input_path: Path, receipts_path: Path, manifest_path: Path) -> dict[str, object]:
    paths = [input_path, receipts_path, manifest_path,
             receipts_path.with_name(receipts_path.name + ".tmp"),
             manifest_path.with_name(manifest_path.name + ".tmp")]
    resolved = [path.resolve(strict=False) for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ProjectionError("input/output/temporary paths must be pairwise distinct")
    if receipts_path.exists() or manifest_path.exists():
        raise ProjectionError("output path already exists")
    parents, input_raw = load_jsonl(input_path)
    receipt_raws = []
    parent_hashes = []
    rows = 0
    aggregation_reads = 0
    for parent in parents:
        receipt, receipt_raw = project_parent(parent)
        receipt_raws.append(receipt_raw)
        parent_hashes.append({
            "parent_id": parent.decision.parent_id,
            "allocation_receipt_sha256": sha256(receipt_raw),
            "projection_input_sha256": receipt["projection_input_sha256"],
            "decision_input_sha256": receipt["decision_input_sha256"],
            "decision_output_sha256": receipt["decision_output_sha256"],
        })
        rows += len(parent.decision.rows)
        aggregation_reads += receipt["nodes200k_aggregation_reads"]
    receipts_raw = b"".join(receipt_raws)
    if not receipts_raw:
        raise ProjectionError("projection produced no receipts")
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "policy": {"M5": M5, "M50": M50, "minimum_survivors": 2},
        "parents": len(parents),
        "rows": rows,
        "input_jsonl_sha256": sha256(input_raw),
        "allocation_receipts_jsonl_sha256": sha256(receipts_raw),
        "canonical_serialization": "UTF-8, compact sorted-key JSON, LF per record",
        "q200_value_reads": 0,
        "q200_label_reads": 0,
        "q200_branches": 0,
        "nodes200k_validated_rows": rows,
        "nodes200k_policy_reads": 0,
        "nodes200k_policy_branches": 0,
        "nodes200k_preseal_aggregation_reads": 0,
        "nodes200k_aggregation_reads": aggregation_reads,
        "searches": 0,
        "fits": 0,
        "strength_games": 0,
        "parent_receipts": parent_hashes,
    }
    manifest_raw = canonical_json_line(manifest)
    receipts_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    receipts_tmp, manifest_tmp = paths[3], paths[4]
    if receipts_tmp.exists() or manifest_tmp.exists():
        raise ProjectionError("temporary output path already exists")
    try:
        receipts_tmp.write_bytes(receipts_raw)
        manifest_tmp.write_bytes(manifest_raw)
        os.replace(receipts_tmp, receipts_path)
        os.replace(manifest_tmp, manifest_path)
    except Exception:
        receipts_tmp.unlink(missing_ok=True)
        manifest_tmp.unlink(missing_ok=True)
        receipts_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise
    return manifest


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-receipts", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = project_file(args.input, args.out_receipts, args.out_manifest)
        print(canonical_json_line({
            "parents": manifest["parents"], "rows": manifest["rows"],
            "allocation_receipts_jsonl_sha256": manifest["allocation_receipts_jsonl_sha256"],
        }).decode("ascii"), end="")
        return 0
    except Exception as exc:
        print(f"adaptive_sibling_b2_projection: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
