#!/usr/bin/env python3
"""Exact, deterministic statistics for the PR771 adaptive-shadow B2 contract.

The public analysis entry point always uses the prospective B2 constants:
4,000 sealed parent sufficient-statistic rows, 200,000 sequential stratified
bootstrap replications, and SplitMix64 seed 2026110717.  Tests exercise the
same implementation through a private small-replication helper.  The CLI has
no option that can reduce the production replication count.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


INPUT_SCHEMA = "jass.adaptive_sibling_b2_parent_stats_sufficient.v1"
OUTPUT_SCHEMA = "jass.adaptive_sibling_b2_statistics.v1"
PREFLIGHT_SCHEMA = "jass.adaptive_sibling_b2_statistical_preflight.v1"
CELL_ORDER = (
    "P0_stm0", "P0_stm1", "P1_stm0", "P1_stm1",
    "P2_stm0", "P2_stm1", "P3_stm0", "P3_stm1",
)
CELL_SIZE = 500
PARENT_COUNT = 4000
BOOTSTRAP_REPLICATIONS = 200_000
BOOTSTRAP_SEED = 2026110717
PROGRESS_EVERY_REPLICATIONS = 1000
ALPHA_GLOBAL = 0.05
ALPHA_CELL = 0.00625
UINT64_MAX = (1 << 64) - 1
INT64_MAX = (1 << 63) - 1
MASK64 = UINT64_MAX
KERNEL_EXPECTED_CHECKSUMS = (
    500_934_807, 1_001_869_614, 1_502_804_421, 2_003_739_228,
    2_504_674_035, 3_005_608_842, 3_506_543_649, 4_007_478_456,
    4_508_413_263, 5_009_348_070,
)

PARENT_KEYS = frozenset({
    "schema", "parent_id", "cell", "full_nodes", "shadow_nodes",
    "fully_nonexact", "same_row", "value_equivalent", "exact_mismatch",
    "signal_event", "signal_direction_code", "numeric_eligible", "numeric_component",
})

SIGNAL_DIRECTIONS = {
    0: "NONE",
    1: "WIN_TO_UNRESOLVED",
    2: "WIN_TO_LOSS",
    3: "UNRESOLVED_TO_LOSS",
    4: "LOSS_TO_UNRESOLVED",
    5: "LOSS_TO_WIN",
    6: "UNRESOLVED_TO_WIN",
}
SIGNAL_DOWN_CODES = frozenset({1, 2, 3})

FAMILY_ORDER = (
    "all_parent_saving",
    "fully_nonexact_saving",
    "value_equivalence",
    "signal_event",
    "moderate_1_99",
    "total_component",
    "numeric_ge_100",
)


class StatisticsContractError(RuntimeError):
    """A structural, support, arithmetic, or deterministic contract failure."""


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_json_loads(text: str, label: str) -> object:
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StatisticsContractError(f"{label} duplicate key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str):
        raise StatisticsContractError(f"{label} forbidden constant: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise StatisticsContractError(f"{label} is invalid JSON") from exc


def _require_int(value: object, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise StatisticsContractError(
            f"{field} must be an integer in [{minimum},{maximum}]"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise StatisticsContractError(f"{field} must be boolean")
    return value


def _checked_add(left: int, right: int, maximum: int, field: str) -> int:
    result = left + right
    if result < 0 or result > maximum:
        raise StatisticsContractError(f"{field} overflow")
    return result


def _finite_ratio(numerator: int, denominator: int, field: str) -> float:
    if denominator <= 0:
        raise StatisticsContractError(f"{field} denominator is zero")
    value = numerator / denominator
    if not math.isfinite(value):
        raise StatisticsContractError(f"{field} is non-finite")
    return value


@dataclass(frozen=True, slots=True)
class ParentStatsSufficientV1:
    """One sealed projection of a rich ParentStatsV1 into sufficient statistics."""

    parent_id: int
    cell: str
    full_nodes: int
    shadow_nodes: int
    fully_nonexact: bool
    same_row: bool
    value_equivalent: bool
    exact_mismatch: bool
    signal_event: bool
    signal_direction_code: int
    numeric_eligible: bool
    numeric_component: int

    def __post_init__(self) -> None:
        _require_int(self.parent_id, "parent_id", 0, INT64_MAX)
        if not isinstance(self.cell, str) or self.cell not in CELL_ORDER:
            raise StatisticsContractError("cell is outside the fixed eight-cell order")
        _require_int(self.full_nodes, "full_nodes", 1, UINT64_MAX)
        _require_int(self.shadow_nodes, "shadow_nodes", 0, UINT64_MAX)
        _require_bool(self.fully_nonexact, "fully_nonexact")
        _require_bool(self.same_row, "same_row")
        _require_bool(self.value_equivalent, "value_equivalent")
        _require_bool(self.exact_mismatch, "exact_mismatch")
        _require_bool(self.signal_event, "signal_event")
        _require_int(self.signal_direction_code, "signal_direction_code", 0, 6)
        _require_bool(self.numeric_eligible, "numeric_eligible")
        _require_int(self.numeric_component, "numeric_component", 0, INT64_MAX)
        self.validate_semantics()

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ParentStatsSufficientV1":
        if not isinstance(value, Mapping) or frozenset(value) != PARENT_KEYS:
            raise StatisticsContractError("ParentStatsSufficientV1 fields mismatch")
        if value["schema"] != INPUT_SCHEMA:
            raise StatisticsContractError("ParentStatsSufficientV1 schema mismatch")
        cell = value["cell"]
        if not isinstance(cell, str) or cell not in CELL_ORDER:
            raise StatisticsContractError("cell is outside the fixed eight-cell order")
        row = cls(
            parent_id=_require_int(value["parent_id"], "parent_id", 0, INT64_MAX),
            cell=cell,
            full_nodes=_require_int(value["full_nodes"], "full_nodes", 1, UINT64_MAX),
            shadow_nodes=_require_int(
                value["shadow_nodes"], "shadow_nodes", 0, UINT64_MAX
            ),
            fully_nonexact=_require_bool(value["fully_nonexact"], "fully_nonexact"),
            same_row=_require_bool(value["same_row"], "same_row"),
            value_equivalent=_require_bool(
                value["value_equivalent"], "value_equivalent"
            ),
            exact_mismatch=_require_bool(value["exact_mismatch"], "exact_mismatch"),
            signal_event=_require_bool(value["signal_event"], "signal_event"),
            signal_direction_code=_require_int(
                value["signal_direction_code"], "signal_direction_code", 0, 6
            ),
            numeric_eligible=_require_bool(
                value["numeric_eligible"], "numeric_eligible"
            ),
            numeric_component=_require_int(
                value["numeric_component"], "numeric_component", 0, INT64_MAX
            ),
        )
        return row

    def validate_semantics(self) -> None:
        expected_signal_event = self.signal_direction_code in SIGNAL_DOWN_CODES
        if self.signal_event != expected_signal_event:
            raise StatisticsContractError(
                "signal_event must equal the union of the three downward directions"
            )
        if self.same_row and not self.value_equivalent:
            raise StatisticsContractError("same_row requires value_equivalent")
        if self.exact_mismatch and self.value_equivalent:
            raise StatisticsContractError("exact_mismatch cannot be value_equivalent")
        if self.signal_direction_code and self.value_equivalent:
            raise StatisticsContractError("signal direction cannot be value_equivalent")
        if self.signal_direction_code and self.exact_mismatch:
            raise StatisticsContractError("signal direction cannot be exact_mismatch")
        if self.signal_direction_code and self.numeric_eligible:
            raise StatisticsContractError(
                "signal direction cannot be numeric-eligible"
            )
        if self.exact_mismatch and self.numeric_eligible:
            raise StatisticsContractError(
                "exact_mismatch cannot be numeric-eligible"
            )
        if not self.numeric_eligible and self.numeric_component != 0:
            raise StatisticsContractError(
                "numeric_component must be zero for an ineligible parent"
            )
        if self.value_equivalent and self.numeric_component != 0:
            raise StatisticsContractError(
                "value-equivalent parents must have zero numeric_component"
            )

    @property
    def moderate_1_99(self) -> int:
        return (
            self.numeric_component
            if 1 <= self.numeric_component <= 99
            else 0
        )

    @property
    def numeric_ge_100(self) -> int:
        return int(self.numeric_eligible and self.numeric_component >= 100)

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": INPUT_SCHEMA,
            "parent_id": self.parent_id,
            "cell": self.cell,
            "full_nodes": self.full_nodes,
            "shadow_nodes": self.shadow_nodes,
            "fully_nonexact": self.fully_nonexact,
            "same_row": self.same_row,
            "value_equivalent": self.value_equivalent,
            "exact_mismatch": self.exact_mismatch,
            "signal_event": self.signal_event,
            "signal_direction_code": self.signal_direction_code,
            "numeric_eligible": self.numeric_eligible,
            "numeric_component": self.numeric_component,
        }


class SplitMix64:
    """Normative unsigned-64 SplitMix stream with unbiased bounded draws."""

    __slots__ = ("state", "generated", "rejected")

    def __init__(self, seed: int):
        self.state = _require_int(seed, "SplitMix64 seed", 0, UINT64_MAX)
        self.generated = 0
        self.rejected = 0

    def next_uint64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        value = self.state
        value = (
            (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9
        ) & MASK64
        value = (
            (value ^ (value >> 27)) * 0x94D049BB133111EB
        ) & MASK64
        result = (value ^ (value >> 31)) & MASK64
        self.generated += 1
        return result

    def randbelow(self, n: int) -> int:
        n = _require_int(n, "randbelow n", 1, UINT64_MAX)
        limit = (1 << 64) - ((1 << 64) % n)
        while True:
            value = self.next_uint64()
            if value < limit:
                return value % n
            self.rejected += 1


def inverse_edf_type1(values: Sequence[float], probability: float) -> float:
    if not values:
        raise StatisticsContractError("quantile sequence is empty")
    if not math.isfinite(probability) or not 0.0 < probability <= 1.0:
        raise StatisticsContractError("quantile probability must be in (0,1]")
    if any(not math.isfinite(value) for value in values):
        raise StatisticsContractError("quantile sequence contains non-finite value")
    ordered = sorted(values)
    index = math.ceil(probability * len(ordered)) - 1
    return ordered[index]


def _binomial_cdf_logspace(x: int, n: int, probability: float) -> float:
    if x < 0:
        return 0.0
    if x >= n:
        return 1.0
    if probability == 0.0:
        return 1.0
    if probability == 1.0:
        return 0.0
    logs = []
    for j in range(x + 1):
        logs.append(
            math.lgamma(n + 1)
            - math.lgamma(j + 1)
            - math.lgamma(n - j + 1)
            + j * math.log(probability)
            + (n - j) * math.log1p(-probability)
        )
    maximum = max(logs)
    value = math.exp(maximum) * math.fsum(
        math.exp(item - maximum) for item in logs
    )
    if not math.isfinite(value):
        raise StatisticsContractError("binomial CDF is non-finite")
    return min(1.0, max(0.0, value))


def clopper_pearson_upper(x: int, n: int, alpha: float) -> float:
    x = _require_int(x, "CP x", 0, UINT64_MAX)
    n = _require_int(n, "CP n", 1, UINT64_MAX)
    if x > n:
        raise StatisticsContractError("CP x exceeds n")
    if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise StatisticsContractError("CP alpha must be in (0,1)")
    if x == n:
        return 1.0
    low = 0.0
    high = 1.0
    for _ in range(256):
        middle = (low + high) / 2.0
        if _binomial_cdf_logspace(x, n, middle) > alpha:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def clopper_pearson_lower(x: int, n: int, alpha: float) -> float:
    x = _require_int(x, "CP x", 0, UINT64_MAX)
    n = _require_int(n, "CP n", 1, UINT64_MAX)
    if x > n:
        raise StatisticsContractError("CP x exceeds n")
    if x == 0:
        return 0.0
    return 1.0 - clopper_pearson_upper(n - x, n, alpha)


def load_parent_stats_sufficient_jsonl(
    path: Path,
) -> tuple[list[ParentStatsSufficientV1], bytes]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise StatisticsContractError(
            f"cannot read ParentStatsSufficientV1 JSONL: {exc}"
        ) from exc
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        raise StatisticsContractError(
            "ParentStatsSufficientV1 JSONL must be non-empty LF text"
        )
    rows: list[ParentStatsSufficientV1] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        value = _strict_json_loads(
            line, f"ParentStatsSufficientV1 line {line_number}"
        )
        if _canonical_json_bytes(value) != (line + "\n").encode("utf-8"):
            raise StatisticsContractError(
                f"ParentStatsSufficientV1 line {line_number} is not canonical JSON"
            )
        rows.append(ParentStatsSufficientV1.from_mapping(value))
    validate_parent_population(rows)
    return rows, raw


def write_parent_stats_sufficient_jsonl(
    path: Path, rows: Sequence[ParentStatsSufficientV1]
) -> bytes:
    validate_parent_population(rows)
    raw = b"".join(_canonical_json_bytes(row.to_mapping()) for row in rows)
    if path.exists():
        raise StatisticsContractError(
            "ParentStatsSufficientV1 output already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise StatisticsContractError(
            "ParentStatsSufficientV1 temporary output exists"
        )
    try:
        temporary.write_bytes(raw)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise
    return raw


def validate_parent_population(rows: Sequence[ParentStatsSufficientV1]) -> None:
    if len(rows) != PARENT_COUNT:
        raise StatisticsContractError(
            f"expected {PARENT_COUNT} ParentStatsSufficientV1 rows, got {len(rows)}"
        )
    identifiers = [row.parent_id for row in rows]
    if identifiers != sorted(identifiers) or len(set(identifiers)) != len(identifiers):
        raise StatisticsContractError("parent_id order must be strictly increasing")
    cells = {cell: [] for cell in CELL_ORDER}
    for row in rows:
        row.validate_semantics()
        cells[row.cell].append(row)
    for cell in CELL_ORDER:
        if len(cells[cell]) != CELL_SIZE:
            raise StatisticsContractError(
                f"cell {cell} must contain exactly {CELL_SIZE} parents"
            )
        if [row.parent_id for row in cells[cell]] != sorted(
            row.parent_id for row in cells[cell]
        ):
            raise StatisticsContractError(f"cell {cell} parent order drift")
    _prove_bootstrap_arithmetic_bounds(cells)


def _prove_bootstrap_arithmetic_bounds(
    cells: Mapping[str, Sequence[ParentStatsSufficientV1]],
) -> None:
    for cell, rows in cells.items():
        maximum_full = max(row.full_nodes for row in rows)
        maximum_shadow = max(row.shadow_nodes for row in rows)
        maximum_delta = max(row.numeric_component for row in rows)
        if maximum_full * CELL_SIZE > UINT64_MAX:
            raise StatisticsContractError(f"{cell} bootstrap full_nodes may overflow")
        if maximum_shadow * CELL_SIZE > UINT64_MAX:
            raise StatisticsContractError(f"{cell} bootstrap shadow_nodes may overflow")
        if maximum_delta * CELL_SIZE > INT64_MAX:
            raise StatisticsContractError(f"{cell} bootstrap numeric_delta may overflow")
    global_full_bound = sum(
        max(row.full_nodes for row in rows) * CELL_SIZE for rows in cells.values()
    )
    global_shadow_bound = sum(
        max(row.shadow_nodes for row in rows) * CELL_SIZE for rows in cells.values()
    )
    global_delta_bound = sum(
        max(row.numeric_component for row in rows) * CELL_SIZE
        for rows in cells.values()
    )
    if global_full_bound > UINT64_MAX:
        raise StatisticsContractError("global bootstrap full_nodes may overflow")
    if global_shadow_bound > UINT64_MAX:
        raise StatisticsContractError("global bootstrap shadow_nodes may overflow")
    if global_delta_bound > INT64_MAX:
        raise StatisticsContractError("global bootstrap numeric_delta may overflow")


def _partition(
    rows: Sequence[ParentStatsSufficientV1],
) -> dict[str, list[ParentStatsSufficientV1]]:
    return {cell: [row for row in rows if row.cell == cell] for cell in CELL_ORDER}


def _aggregate_rows(rows: Sequence[ParentStatsSufficientV1]) -> dict[str, int]:
    result = {
        "rows": 0,
        "full_nodes": 0,
        "shadow_nodes": 0,
        "fully_nonexact": 0,
        "fully_nonexact_full_nodes": 0,
        "fully_nonexact_shadow_nodes": 0,
        "same_row": 0,
        "value_equivalent": 0,
        "exact_mismatch": 0,
        "signal_event": 0,
        "signal_win_to_unresolved": 0,
        "signal_win_to_loss": 0,
        "signal_unresolved_to_loss": 0,
        "signal_loss_to_unresolved": 0,
        "signal_loss_to_win": 0,
        "signal_unresolved_to_win": 0,
        "numeric_eligible": 0,
        "numeric_delta": 0,
        "moderate_1_99": 0,
        "numeric_ge_100": 0,
        "maximum_numeric_delta": 0,
    }
    for row in rows:
        result["rows"] += 1
        result["full_nodes"] = _checked_add(
            result["full_nodes"], row.full_nodes, UINT64_MAX, "full_nodes"
        )
        result["shadow_nodes"] = _checked_add(
            result["shadow_nodes"], row.shadow_nodes, UINT64_MAX, "shadow_nodes"
        )
        result["same_row"] += int(row.same_row)
        result["value_equivalent"] += int(row.value_equivalent)
        result["exact_mismatch"] += int(row.exact_mismatch)
        result["signal_event"] += int(row.signal_event)
        if row.signal_direction_code:
            key = "signal_" + SIGNAL_DIRECTIONS[row.signal_direction_code].lower()
            result[key] += 1
        if row.fully_nonexact:
            result["fully_nonexact"] += 1
            result["fully_nonexact_full_nodes"] = _checked_add(
                result["fully_nonexact_full_nodes"],
                row.full_nodes,
                UINT64_MAX,
                "fully_nonexact_full_nodes",
            )
            result["fully_nonexact_shadow_nodes"] = _checked_add(
                result["fully_nonexact_shadow_nodes"],
                row.shadow_nodes,
                UINT64_MAX,
                "fully_nonexact_shadow_nodes",
            )
        if row.numeric_eligible:
            result["numeric_eligible"] += 1
            result["numeric_delta"] = _checked_add(
                result["numeric_delta"],
                row.numeric_component,
                INT64_MAX,
                "numeric_delta",
            )
            result["moderate_1_99"] = _checked_add(
                result["moderate_1_99"],
                row.moderate_1_99,
                INT64_MAX,
                "moderate_1_99",
            )
            result["numeric_ge_100"] += row.numeric_ge_100
            result["maximum_numeric_delta"] = max(
                result["maximum_numeric_delta"], row.numeric_component
            )
    return result


def _support_report(
    global_counts: Mapping[str, int],
    cell_counts: Mapping[str, Mapping[str, int]],
) -> dict[str, object]:
    reasons = []
    if global_counts["fully_nonexact"] < 2000:
        reasons.append("global fully_nonexact below 2000")
    if global_counts["numeric_eligible"] < 1000:
        reasons.append("global numeric_eligible below 1000")
    for cell in CELL_ORDER:
        counts = cell_counts[cell]
        if counts["full_nodes"] <= 0 or counts["shadow_nodes"] <= 0:
            reasons.append(f"{cell} node support is zero")
        if counts["fully_nonexact"] < 100:
            reasons.append(f"{cell} fully_nonexact below 100")
        if counts["numeric_eligible"] < 50:
            reasons.append(f"{cell} numeric_eligible below 50")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "required": {
            "parents": PARENT_COUNT,
            "parents_per_cell": CELL_SIZE,
            "global_fully_nonexact_min": 2000,
            "cell_fully_nonexact_min": 100,
            "global_numeric_eligible_min": 1000,
            "cell_numeric_eligible_min": 50,
        },
        "observed_global": dict(global_counts),
        "observed_cells": {cell: dict(cell_counts[cell]) for cell in CELL_ORDER},
    }


def _point_estimates(
    global_counts: Mapping[str, int],
    cell_counts: Mapping[str, Mapping[str, int]],
) -> dict[str, object]:
    def estimates(counts: Mapping[str, int]) -> dict[str, float]:
        return {
            "all_parent_saving": 1.0 - _finite_ratio(
                counts["shadow_nodes"], counts["full_nodes"], "all_parent_saving"
            ),
            "fully_nonexact_saving": 1.0 - _finite_ratio(
                counts["fully_nonexact_shadow_nodes"],
                counts["fully_nonexact_full_nodes"],
                "fully_nonexact_saving",
            ),
            "same_row_rate": _finite_ratio(
                counts["same_row"], counts["rows"], "same_row_rate"
            ),
            "value_equivalence_rate": _finite_ratio(
                counts["value_equivalent"], counts["rows"], "value_equivalence_rate"
            ),
            "signal_event_rate": _finite_ratio(
                counts["signal_event"], counts["rows"], "signal_event_rate"
            ),
            "conditional_numeric_mean": _finite_ratio(
                counts["numeric_delta"],
                counts["numeric_eligible"],
                "conditional_numeric_mean",
            ),
            "all_parent_component_mean": _finite_ratio(
                counts["numeric_delta"], counts["rows"], "all_parent_component_mean"
            ),
            "moderate_1_99_mean": _finite_ratio(
                counts["moderate_1_99"], counts["rows"], "moderate_1_99_mean"
            ),
            "total_component_mean": _finite_ratio(
                counts["numeric_delta"], counts["rows"], "total_component_mean"
            ),
            "numeric_ge_100_rate": _finite_ratio(
                counts["numeric_ge_100"], counts["rows"], "numeric_ge_100_rate"
            ),
        }

    return {
        "global": estimates(global_counts),
        "cells": {cell: estimates(cell_counts[cell]) for cell in CELL_ORDER},
    }


def _packed_cells(
    cells: Mapping[str, Sequence[ParentStatsSufficientV1]],
) -> dict[str, tuple[tuple[int, ...], ...]]:
    packed = {}
    for cell in CELL_ORDER:
        packed[cell] = tuple(
            (
                row.full_nodes,
                row.shadow_nodes,
                row.full_nodes if row.fully_nonexact else 0,
                row.shadow_nodes if row.fully_nonexact else 0,
                int(row.same_row),
                int(row.value_equivalent),
                int(row.numeric_eligible),
                row.numeric_component,
                row.moderate_1_99,
            )
            for row in cells[cell]
        )
    return packed


def _bootstrap(
    cells: Mapping[str, Sequence[ParentStatsSufficientV1]],
    *,
    replications: int,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
) -> tuple[dict[str, object], dict[str, int]]:
    replications = _require_int(replications, "replications", 1, BOOTSTRAP_REPLICATIONS)
    packed = _packed_cells(cells)
    global_series = {
        name: [] for name in (
            "all_parent_saving",
            "fully_nonexact_saving",
            "same_row_rate",
            "value_equivalence_rate",
            "conditional_numeric_mean",
            "all_parent_component_mean",
        )
    }
    cell_series = {
        family: {cell: [] for cell in CELL_ORDER}
        for family in (
            "all_parent_saving",
            "fully_nonexact_saving",
            "moderate_1_99",
            "total_component",
        )
    }
    generator = SplitMix64(BOOTSTRAP_SEED)
    try:
        for replication in range(replications):
            global_totals = [0] * 9
            for cell in CELL_ORDER:
                totals = [0] * 9
                rows = packed[cell]
                for _draw in range(CELL_SIZE):
                    values = rows[generator.randbelow(CELL_SIZE)]
                    totals[0] += values[0]
                    totals[1] += values[1]
                    totals[2] += values[2]
                    totals[3] += values[3]
                    totals[4] += values[4]
                    totals[5] += values[5]
                    totals[6] += values[6]
                    totals[7] += values[7]
                    totals[8] += values[8]
                if totals[0] == 0 or totals[2] == 0 or totals[6] == 0:
                    raise StatisticsContractError(
                        f"bootstrap zero denominator in {cell}"
                    )
                all_saving = 1.0 - totals[1] / totals[0]
                fully_saving = 1.0 - totals[3] / totals[2]
                moderate = totals[8] / CELL_SIZE
                total_component = totals[7] / CELL_SIZE
                for value in (all_saving, fully_saving, moderate, total_component):
                    if not math.isfinite(value):
                        raise StatisticsContractError(
                            f"bootstrap non-finite value in {cell}"
                        )
                cell_series["all_parent_saving"][cell].append(all_saving)
                cell_series["fully_nonexact_saving"][cell].append(fully_saving)
                cell_series["moderate_1_99"][cell].append(moderate)
                cell_series["total_component"][cell].append(total_component)
                for index in range(9):
                    global_totals[index] += totals[index]
            if global_totals[0] == 0 or global_totals[2] == 0 or global_totals[6] == 0:
                raise StatisticsContractError("bootstrap global zero denominator")
            global_values = {
                "all_parent_saving": 1.0 - global_totals[1] / global_totals[0],
                "fully_nonexact_saving": 1.0 - global_totals[3] / global_totals[2],
                "same_row_rate": global_totals[4] / PARENT_COUNT,
                "value_equivalence_rate": global_totals[5] / PARENT_COUNT,
                "conditional_numeric_mean": global_totals[7] / global_totals[6],
                "all_parent_component_mean": global_totals[7] / PARENT_COUNT,
            }
            for name, value in global_values.items():
                if not math.isfinite(value):
                    raise StatisticsContractError(
                        f"bootstrap global {name} is non-finite"
                    )
                global_series[name].append(value)
            completed = replication + 1
            if progress_callback is not None and (
                completed % PROGRESS_EVERY_REPLICATIONS == 0
                or completed == replications
            ):
                progress_callback({
                    "completed_replications": completed,
                    "total_replications": replications,
                    "accepted_draws": completed * PARENT_COUNT,
                    "generated_uint64": generator.generated,
                    "rejected_uint64": generator.rejected,
                })
    except StatisticsContractError:
        raise

    intervals = {"global": {}, "cells": {}}
    for name, values in global_series.items():
        intervals["global"][name] = {
            "lcb95": inverse_edf_type1(values, ALPHA_GLOBAL),
            "ucb95": inverse_edf_type1(values, 1.0 - ALPHA_GLOBAL),
        }
    for family, by_cell in cell_series.items():
        intervals["cells"][family] = {}
        for cell, values in by_cell.items():
            intervals["cells"][family][cell] = {
                "lcb_sim95": inverse_edf_type1(values, ALPHA_CELL),
                "ucb_sim95": inverse_edf_type1(values, 1.0 - ALPHA_CELL),
            }
    return intervals, {
        "seed": BOOTSTRAP_SEED,
        "replications": replications,
        "accepted_draws": replications * len(CELL_ORDER) * CELL_SIZE,
        "generated_uint64": generator.generated,
        "rejected_uint64": generator.rejected,
    }


def _cp_cell_intervals(
    cell_counts: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, float]]:
    return {
        cell: {
            "value_equivalence_lcb_sim95": clopper_pearson_lower(
                counts["value_equivalent"], CELL_SIZE, ALPHA_CELL
            ),
            "signal_event_ucb_sim95": clopper_pearson_upper(
                counts["signal_event"], CELL_SIZE, ALPHA_CELL
            ),
            "numeric_ge_100_ucb_sim95": clopper_pearson_upper(
                counts["numeric_ge_100"], CELL_SIZE, ALPHA_CELL
            ),
        }
        for cell, counts in cell_counts.items()
    }


def _gate_report(
    global_counts: Mapping[str, int],
    intervals: Mapping[str, object],
    cp_cells: Mapping[str, Mapping[str, float]],
) -> dict[str, object]:
    global_intervals = intervals["global"]
    cell_intervals = intervals["cells"]
    global_gates = {
        "all_parent_saving_lcb95_ge_0_30":
            global_intervals["all_parent_saving"]["lcb95"] >= 0.30,
        "fully_nonexact_saving_lcb95_ge_0_30":
            global_intervals["fully_nonexact_saving"]["lcb95"] >= 0.30,
        "same_row_lcb95_ge_0_94":
            global_intervals["same_row_rate"]["lcb95"] >= 0.94,
        "value_equivalence_lcb95_ge_0_96":
            global_intervals["value_equivalence_rate"]["lcb95"] >= 0.96,
        "conditional_numeric_mean_ucb95_le_2":
            global_intervals["conditional_numeric_mean"]["ucb95"] <= 2.0,
        "exact_mismatch_count_eq_0": global_counts["exact_mismatch"] == 0,
        "maximum_numeric_delta_le_1000":
            global_counts["maximum_numeric_delta"] <= 1000,
    }

    families = {}
    all_saving_cells = {
        cell: cell_intervals["all_parent_saving"][cell]["lcb_sim95"] >= 0.20
        for cell in CELL_ORDER
    }
    families["all_parent_saving"] = {
        "alpha_cell": ALPHA_CELL,
        "method": "bootstrap_type1_lcb",
        "cells": all_saving_cells,
        "passed": all(all_saving_cells.values()),
    }
    fully_saving_cells = {
        cell: cell_intervals["fully_nonexact_saving"][cell]["lcb_sim95"] >= 0.20
        for cell in CELL_ORDER
    }
    families["fully_nonexact_saving"] = {
        "alpha_cell": ALPHA_CELL,
        "method": "bootstrap_type1_lcb",
        "cells": fully_saving_cells,
        "passed": all(fully_saving_cells.values()),
    }
    value_cells = {
        cell: cp_cells[cell]["value_equivalence_lcb_sim95"] >= 0.90
        for cell in CELL_ORDER
    }
    families["value_equivalence"] = {
        "alpha_cell": ALPHA_CELL,
        "method": "clopper_pearson_lcb",
        "cells": value_cells,
        "passed": all(value_cells.values()),
    }
    signal_bounds = [cp_cells[cell]["signal_event_ucb_sim95"] for cell in CELL_ORDER]
    signal_cells = {
        cell: cp_cells[cell]["signal_event_ucb_sim95"] <= 0.04
        for cell in CELL_ORDER
    }
    families["signal_event"] = {
        "alpha_cell": ALPHA_CELL,
        "method": "clopper_pearson_ucb",
        "cells": signal_cells,
        "mean_ucb_le_0_020": math.fsum(signal_bounds) / len(signal_bounds) <= 0.020,
        "max_ucb_le_0_040": max(signal_bounds) <= 0.040,
    }
    families["signal_event"]["passed"] = (
        all(signal_cells.values())
        and families["signal_event"]["mean_ucb_le_0_020"]
        and families["signal_event"]["max_ucb_le_0_040"]
    )
    moderate_cells = {
        cell: cell_intervals["moderate_1_99"][cell]["ucb_sim95"] <= 4.0
        for cell in CELL_ORDER
    }
    families["moderate_1_99"] = {
        "alpha_cell": ALPHA_CELL,
        "method": "bootstrap_type1_ucb",
        "cells": moderate_cells,
        "passed": all(moderate_cells.values()),
    }
    total_cells = {
        cell: cell_intervals["total_component"][cell]["ucb_sim95"] <= 6.0
        for cell in CELL_ORDER
    }
    families["total_component"] = {
        "alpha_cell": ALPHA_CELL,
        "method": "bootstrap_type1_ucb",
        "cells": total_cells,
        "passed": all(total_cells.values()),
    }
    numeric_bounds = [
        cp_cells[cell]["numeric_ge_100_ucb_sim95"] for cell in CELL_ORDER
    ]
    numeric_cells = {
        cell: cp_cells[cell]["numeric_ge_100_ucb_sim95"] <= 0.03
        for cell in CELL_ORDER
    }
    families["numeric_ge_100"] = {
        "alpha_cell": ALPHA_CELL,
        "method": "clopper_pearson_ucb",
        "cells": numeric_cells,
        "mean_ucb_le_0_015": math.fsum(numeric_bounds) / len(numeric_bounds) <= 0.015,
        "max_ucb_le_0_030": max(numeric_bounds) <= 0.030,
    }
    families["numeric_ge_100"]["passed"] = (
        all(numeric_cells.values())
        and families["numeric_ge_100"]["mean_ucb_le_0_015"]
        and families["numeric_ge_100"]["max_ucb_le_0_030"]
    )
    if tuple(families) != FAMILY_ORDER:
        raise StatisticsContractError("seven-family order drift")
    return {
        "logic": "intersection_union",
        "no_cross_family_alpha_correction": True,
        "global_gates": global_gates,
        "cell_families": families,
        "all_passed": all(global_gates.values())
        and all(family["passed"] for family in families.values()),
    }


def _analyze_parent_stats(
    rows: Sequence[ParentStatsSufficientV1],
    *,
    replications: int,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, object]:
    validate_parent_population(rows)
    cells = _partition(rows)
    cell_counts = {cell: _aggregate_rows(cells[cell]) for cell in CELL_ORDER}
    global_counts = _aggregate_rows(rows)
    support = _support_report(global_counts, cell_counts)
    base = {
        "schema": OUTPUT_SCHEMA,
        "input_schema": INPUT_SCHEMA,
        "parent_count": PARENT_COUNT,
        "cell_order": list(CELL_ORDER),
        "cell_size": CELL_SIZE,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_replications": replications,
        "alpha_global": ALPHA_GLOBAL,
        "alpha_cell": ALPHA_CELL,
        "family_order": list(FAMILY_ORDER),
        "support": support,
    }
    if not support["valid"]:
        return {
            **base,
            "status": "INVALID_UNKNOWN",
            "scientific_gates_evaluated": False,
        }
    try:
        estimates = _point_estimates(global_counts, cell_counts)
        intervals, stream = _bootstrap(
            cells,
            replications=replications,
            progress_callback=progress_callback,
        )
        cp_cells = _cp_cell_intervals(cell_counts)
        gates = _gate_report(global_counts, intervals, cp_cells)
    except StatisticsContractError as exc:
        return {
            **base,
            "status": "INVALID_UNKNOWN",
            "scientific_gates_evaluated": False,
            "runtime_failure": str(exc),
        }
    return {
        **base,
        "status": "VALID",
        "scientific_gates_evaluated": True,
        "point_estimates": estimates,
        "bootstrap_intervals": intervals,
        "clopper_pearson_cells": cp_cells,
        "bootstrap_stream": stream,
        "gates": gates,
    }


def analyze_parent_stats(
    rows: Sequence[ParentStatsSufficientV1],
    *,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, object]:
    """Run the fixed production analysis; replication count is not configurable."""
    return _analyze_parent_stats(
        rows,
        replications=BOOTSTRAP_REPLICATIONS,
        progress_callback=progress_callback,
    )


def _analyze_parent_stats_for_test(
    rows: Sequence[ParentStatsSufficientV1],
    *,
    replications: int,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, object]:
    """Private test hook; never exposed by the production CLI."""
    return _analyze_parent_stats(
        rows,
        replications=replications,
        progress_callback=progress_callback,
    )


def build_synthetic_parent_stats() -> list[ParentStatsSufficientV1]:
    """Build the fixed 4,000-parent synthetic-only preflight population."""
    rows = []
    for cell_index, cell in enumerate(CELL_ORDER):
        for local_index in range(CELL_SIZE):
            value_equivalent = local_index % 25 != 0
            same_row = local_index % 20 != 0 and value_equivalent
            signal_direction_code = {
                25: 1,
                125: 2,
                225: 3,
                325: 5,
            }.get(local_index, 0)
            signal_event = signal_direction_code in SIGNAL_DOWN_CODES
            numeric_eligible = local_index % 2 == 0
            numeric_component = (
                0
                if not numeric_eligible or value_equivalent
                else local_index % 151
            )
            rows.append(ParentStatsSufficientV1(
                parent_id=cell_index * CELL_SIZE + local_index,
                cell=cell,
                full_nodes=1_000_000 + 1_000 * cell_index + local_index,
                shadow_nodes=500_000 + 500 * cell_index + local_index,
                fully_nonexact=local_index % 5 != 0,
                same_row=same_row,
                value_equivalent=value_equivalent,
                exact_mismatch=False,
                signal_event=signal_event,
                signal_direction_code=signal_direction_code,
                numeric_eligible=numeric_eligible,
                numeric_component=numeric_component,
            ))
    validate_parent_population(rows)
    return rows


def synthetic_expected_aggregates() -> dict[str, object]:
    cells = {}
    for cell_index, cell in enumerate(CELL_ORDER):
        cells[cell] = {
            "rows": 500,
            "full_nodes": 500_124_750 + 500_000 * cell_index,
            "shadow_nodes": 250_124_750 + 250_000 * cell_index,
            "fully_nonexact": 400,
            "fully_nonexact_full_nodes": 400_100_000 + 400_000 * cell_index,
            "fully_nonexact_shadow_nodes": 200_100_000 + 200_000 * cell_index,
            "same_row": 460,
            "value_equivalent": 480,
            "exact_mismatch": 0,
            "signal_event": 3,
            "signal_win_to_unresolved": 1,
            "signal_win_to_loss": 1,
            "signal_unresolved_to_loss": 1,
            "signal_loss_to_unresolved": 0,
            "signal_loss_to_win": 1,
            "signal_unresolved_to_win": 0,
            "numeric_eligible": 250,
            "numeric_delta": 891,
            "moderate_1_99": 344,
            "numeric_ge_100": 4,
            "maximum_numeric_delta": 150,
        }
    return {
        "schema": "jass.adaptive_sibling_b2_synthetic_truth.v1",
        "cells": cells,
        "global": {
            "rows": 4000,
            "full_nodes": 4_014_998_000,
            "shadow_nodes": 2_007_998_000,
            "fully_nonexact": 3200,
            "fully_nonexact_full_nodes": 3_212_000_000,
            "fully_nonexact_shadow_nodes": 1_606_400_000,
            "same_row": 3680,
            "value_equivalent": 3840,
            "exact_mismatch": 0,
            "signal_event": 24,
            "signal_win_to_unresolved": 8,
            "signal_win_to_loss": 8,
            "signal_unresolved_to_loss": 8,
            "signal_loss_to_unresolved": 0,
            "signal_loss_to_win": 8,
            "signal_unresolved_to_win": 0,
            "numeric_eligible": 2000,
            "numeric_delta": 7128,
            "moderate_1_99": 2752,
            "numeric_ge_100": 32,
            "maximum_numeric_delta": 150,
        },
    }


def verify_synthetic_truth(
    rows: Sequence[ParentStatsSufficientV1],
) -> dict[str, object]:
    validate_parent_population(rows)
    expected = synthetic_expected_aggregates()
    cells = _partition(rows)
    observed_cells = {cell: _aggregate_rows(cells[cell]) for cell in CELL_ORDER}
    observed_global = _aggregate_rows(rows)
    if observed_cells != expected["cells"] or observed_global != expected["global"]:
        raise StatisticsContractError("synthetic fixture aggregate truth mismatch")
    return expected


def load_kernel_receipt(path: Path) -> tuple[dict[str, object], str]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise StatisticsContractError(f"cannot read kernel receipt: {exc}") from exc
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise StatisticsContractError("kernel receipt must be LF-terminated UTF-8")
    value = _strict_json_loads(text, "kernel receipt")
    if _canonical_json_bytes(value) != raw:
        raise StatisticsContractError("kernel receipt is not canonical JSON")
    if not isinstance(value, dict):
        raise StatisticsContractError("kernel receipt is not an object")
    exact = {
        "kind": "SYNTHETIC_ARITHMETIC_ONLY",
        "scientific_parents": 0,
        "draws": 2_000_000,
        "integer_accumulations_per_draw": 10,
        "splitmix_test_vector_pass": True,
        "kernel_only_excludes_parsing_ratios_quantiles_and_final_validation": True,
    }
    for key, expected in exact.items():
        if type(value.get(key)) is not type(expected) or value.get(key) != expected:
            raise StatisticsContractError(f"kernel receipt {key} mismatch")
    for key in ("elapsed_seconds", "draws_per_second", "extrapolated_800m_draw_kernel_seconds"):
        observed = value.get(key)
        if type(observed) not in (int, float) or not math.isfinite(observed) or observed <= 0:
            raise StatisticsContractError(f"kernel receipt {key} invalid")
    checksums = value.get("synthetic_accumulator_checksums")
    if (
        not isinstance(checksums, list)
        or any(type(item) is not int for item in checksums)
        or tuple(checksums) != KERNEL_EXPECTED_CHECKSUMS
    ):
        raise StatisticsContractError("kernel receipt checksums invalid")
    if not isinstance(value.get("environment"), dict):
        raise StatisticsContractError("kernel receipt environment missing")
    return value, _sha256_bytes(raw)


def runtime_environment() -> dict[str, object]:
    if hasattr(os, "sched_getaffinity"):
        nproc = len(os.sched_getaffinity(0))
    else:
        nproc = os.cpu_count()
    if not nproc:
        raise StatisticsContractError("cannot determine visible processor count")
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "libc": list(platform.libc_ver()),
        "nproc": nproc,
        "pid": os.getpid(),
    }


def peak_rss_bytes() -> int | None:
    try:
        import resource
    except ImportError:
        return None
    observed = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if not isinstance(observed, (int, float)) or observed < 0:
        raise StatisticsContractError("invalid peak RSS observation")
    multiplier = 1 if sys.platform == "darwin" else 1024
    return int(observed * multiplier)


def validate_runtime_against_kernel(
    kernel_receipt: Mapping[str, object],
) -> dict[str, object]:
    kernel_environment = kernel_receipt.get("environment")
    if not isinstance(kernel_environment, Mapping):
        raise StatisticsContractError("kernel receipt environment missing")
    observed = runtime_environment()
    for key in (
        "python_version", "python_implementation", "python_executable",
        "platform", "machine", "libc", "nproc",
    ):
        if kernel_environment.get(key) != observed[key]:
            raise StatisticsContractError(
                f"runtime differs from authenticated kernel environment: {key}"
            )
    return observed


def run_synthetic_preflight(*, out_dir: Path, kernel_receipt_path: Path) -> dict[str, object]:
    """Run the full fixed synthetic preflight. This is intentionally expensive."""
    if out_dir.exists():
        raise StatisticsContractError("preflight output directory already exists")
    kernel_receipt, kernel_sha = load_kernel_receipt(kernel_receipt_path)
    observed_runtime = validate_runtime_against_kernel(kernel_receipt)
    out_dir.mkdir(parents=True)
    rows = build_synthetic_parent_stats()
    truth = verify_synthetic_truth(rows)
    input_path = out_dir / "synthetic-parent-stats-sufficient-v1.jsonl"
    input_raw = write_parent_stats_sufficient_jsonl(input_path, rows)
    truth_raw = _canonical_json_bytes(truth)
    (out_dir / "synthetic-parent-stats-truth-v1.json").write_bytes(truth_raw)
    started_wall = time.monotonic_ns()
    started_cpu = time.process_time_ns()
    loaded_rows, loaded_raw = load_parent_stats_sufficient_jsonl(input_path)
    if loaded_raw != input_raw or loaded_rows != rows:
        raise StatisticsContractError("synthetic sufficient-stat wire round-trip drift")
    progress_path = out_dir / "progress.json"
    progress_started = time.monotonic()

    def publish_progress(payload: dict[str, int]) -> None:
        value = {
            "schema": "jass.adaptive_sibling_b2_statistical_preflight_progress.v1",
            "phase": "bootstrap",
            "elapsed_seconds": time.monotonic() - progress_started,
            **payload,
        }
        raw = _canonical_json_bytes(value)
        temporary = progress_path.with_name(progress_path.name + ".tmp")
        temporary.write_bytes(raw)
        os.replace(temporary, progress_path)

    report = analyze_parent_stats(loaded_rows, progress_callback=publish_progress)
    report_raw = _canonical_json_bytes(report)
    (out_dir / "synthetic-statistics-v1.json").write_bytes(report_raw)
    cpu_ns = time.process_time_ns() - started_cpu
    wall_ns = time.monotonic_ns() - started_wall
    if report["status"] != "VALID":
        raise StatisticsContractError("synthetic preflight analysis is invalid")
    expected_draws = BOOTSTRAP_REPLICATIONS * PARENT_COUNT
    if report["bootstrap_stream"]["accepted_draws"] != expected_draws:
        raise StatisticsContractError("synthetic preflight accepted-draw count drift")
    receipt = {
        "schema": PREFLIGHT_SCHEMA,
        "synthetic_only": True,
        "scientific_parents": 0,
        "fresh_data_reads": 0,
        "games": 0,
        "fits": 0,
        "promotion": False,
        "bake": False,
        "bootstrap_replications": BOOTSTRAP_REPLICATIONS,
        "accepted_draws": expected_draws,
        "input_schema": INPUT_SCHEMA,
        "kernel_receipt_sha256": kernel_sha,
        "kernel_receipt": kernel_receipt,
        "input_sha256": _sha256_bytes(input_raw),
        "truth_sha256": _sha256_bytes(truth_raw),
        "statistics_sha256": _sha256_bytes(report_raw),
        "measured_scope": (
            "wire_parse_bootstrap_cp_quantiles_report_serialization_and_write"
        ),
        "full_pipeline_wall_ns": wall_ns,
        "full_pipeline_cpu_process_ns": cpu_ns,
        "max_rss_bytes": peak_rss_bytes(),
        "input_bytes": len(input_raw),
        "truth_bytes": len(truth_raw),
        "statistics_bytes": len(report_raw),
        "runtime": observed_runtime,
        "runtime_matches_kernel_environment": True,
        "status": report["status"],
        "gate_exercise_only": True,
        "scientific_verdict": None,
    }
    receipt_raw = _canonical_json_bytes(receipt)
    (out_dir / "statistical-preflight-receipt-v1.json").write_bytes(receipt_raw)
    return receipt


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-synthetic", action="store_true", required=True)
    parser.add_argument("--kernel-receipt", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = run_synthetic_preflight(
            out_dir=args.out_dir,
            kernel_receipt_path=args.kernel_receipt,
        )
        print(json.dumps({
            "schema": receipt["schema"],
            "synthetic_only": receipt["synthetic_only"],
            "bootstrap_replications": receipt["bootstrap_replications"],
            "accepted_draws": receipt["accepted_draws"],
            "status": receipt["status"],
        }, sort_keys=True))
        return 0 if receipt["status"] == "VALID" else 2
    except Exception as exc:
        print(f"adaptive_sibling_b2_statistics: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
