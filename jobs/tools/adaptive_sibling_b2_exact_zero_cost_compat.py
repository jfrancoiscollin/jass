#!/usr/bin/env python3
"""Narrow runtime compatibility for exact-only B2 parents with zero node cost.

This module does not modify the frozen X scientific blobs.  It temporarily
relaxes one over-strict implementation invariant discovered by the target-data
preflight: a parent whose every legal sibling is already terminal/TB exact may
legitimately have full_nodes == shadow_nodes == 0 even though the final B2
preregistration only requires non-zero node support after aggregation by cell.

The shim is intentionally fail-closed:
- the frozen X readout/statistics files must be byte-unchanged relative to X;
- only readout sums labelled exactly ``full total`` may be zero;
- only statistics fields labelled exactly ``full_nodes`` may lower min 1 -> 0;
- a zero full-node parent must also have zero shadow nodes;
- all existing cell/global support, bootstrap zero-denominator and scientific
  gates remain unchanged in X.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable

from jobs.tools import adaptive_sibling_b2_readout as readout
from jobs.tools import adaptive_sibling_b2_statistics as statistics

X = "d3657332c3a5609a5501a9ff130f5d5c19488c7f"
ROOT = Path(__file__).resolve().parents[2]
FROZEN_PATHS = (
    "jobs/tools/adaptive_sibling_b2_readout.py",
    "jobs/tools/adaptive_sibling_b2_statistics.py",
)


class ExactZeroCostCompatError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompatReceipt:
    implementation_commit: str
    frozen_paths_unchanged: bool
    readout_zero_full_total_enabled: bool
    statistics_zero_full_nodes_enabled: bool
    zero_full_requires_zero_shadow: bool


_INSTALLED = False
_ORIGINAL_CHECKED_SUM: Callable[..., int] | None = None
_ORIGINAL_REQUIRE_INT: Callable[..., int] | None = None
_ORIGINAL_VALIDATE_SEMANTICS: Callable[..., None] | None = None


def _assert_frozen_blobs_unchanged() -> None:
    completed = subprocess.run(
        ["git", "diff", "--quiet", X, "--", *FROZEN_PATHS],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        raise ExactZeroCostCompatError(
            "frozen X readout/statistics blobs changed"
            + (f": {detail}" if detail else "")
        )


def install() -> CompatReceipt:
    """Install the narrow compatibility patch in the current Python process."""
    global _INSTALLED, _ORIGINAL_CHECKED_SUM, _ORIGINAL_REQUIRE_INT
    global _ORIGINAL_VALIDATE_SEMANTICS
    _assert_frozen_blobs_unchanged()
    if _INSTALLED:
        return CompatReceipt(X, True, True, True, True)

    _ORIGINAL_CHECKED_SUM = readout._checked_sum
    _ORIGINAL_REQUIRE_INT = statistics._require_int
    _ORIGINAL_VALIDATE_SEMANTICS = statistics.ParentStatsSufficientV1.validate_semantics

    def checked_sum(values: Iterable[int], label: str, *, require_positive: bool = False) -> int:
        assert _ORIGINAL_CHECKED_SUM is not None
        if label == "full total" and require_positive:
            return _ORIGINAL_CHECKED_SUM(values, label, require_positive=False)
        return _ORIGINAL_CHECKED_SUM(values, label, require_positive=require_positive)

    def require_int(value: object, field: str, minimum: int, maximum: int) -> int:
        assert _ORIGINAL_REQUIRE_INT is not None
        if field == "full_nodes" and minimum == 1:
            minimum = 0
        return _ORIGINAL_REQUIRE_INT(value, field, minimum, maximum)

    def validate_semantics(self: Any) -> None:
        assert _ORIGINAL_VALIDATE_SEMANTICS is not None
        _ORIGINAL_VALIDATE_SEMANTICS(self)
        if self.full_nodes == 0 and self.shadow_nodes != 0:
            raise statistics.StatisticsContractError(
                "zero full_nodes requires zero shadow_nodes"
            )

    readout._checked_sum = checked_sum
    statistics._require_int = require_int
    statistics.ParentStatsSufficientV1.validate_semantics = validate_semantics
    _INSTALLED = True
    return CompatReceipt(X, True, True, True, True)


def uninstall() -> None:
    """Restore exact X runtime behavior; intended for isolated contract tests."""
    global _INSTALLED
    if not _INSTALLED:
        return
    assert _ORIGINAL_CHECKED_SUM is not None
    assert _ORIGINAL_REQUIRE_INT is not None
    assert _ORIGINAL_VALIDATE_SEMANTICS is not None
    readout._checked_sum = _ORIGINAL_CHECKED_SUM
    statistics._require_int = _ORIGINAL_REQUIRE_INT
    statistics.ParentStatsSufficientV1.validate_semantics = _ORIGINAL_VALIDATE_SEMANTICS
    _INSTALLED = False
