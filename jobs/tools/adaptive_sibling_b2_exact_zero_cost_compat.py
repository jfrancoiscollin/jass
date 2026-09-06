#!/usr/bin/env python3
"""Narrow runtime compatibility for exact-only B2 parents with zero node cost.

This module does not modify the frozen X scientific blobs.  It temporarily
relaxes one over-strict implementation invariant discovered by the target-data
preflight: a parent whose every legal sibling is already terminal/TB exact may
legitimately have full_nodes == shadow_nodes == 0 even though the final B2
preregistration only requires non-zero node support after aggregation by cell.

The shim is intentionally fail-closed:
- the frozen X readout/statistics files must be byte-identical to X;
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
FROZEN_GIT_BLOBS = {
    "jobs/tools/adaptive_sibling_b2_readout.py":
        "e336b20a1c7b5ff11de50df28792b2b0f2230ef1",
    "jobs/tools/adaptive_sibling_b2_statistics.py":
        "ee3e284ff049a6f44473ddd63328199f3f9d4b9c",
}


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


def _git_blob(path: str) -> str:
    try:
        value = subprocess.check_output(
            ["git", "hash-object", "--", path], cwd=ROOT, text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ExactZeroCostCompatError(f"cannot hash frozen path {path}: {exc}") from exc
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise ExactZeroCostCompatError(f"invalid git blob identity for {path}: {value!r}")
    return value


def _assert_frozen_blobs_unchanged() -> None:
    """Authenticate frozen X bytes without requiring X commit history locally.

    GitHub Actions PR checkouts are intentionally shallow.  Comparing the
    current file Git-blob identities against blob identities read directly from
    immutable X proves byte equality while remaining valid in shallow CI and on
    the CPX worktree.
    """
    for path, expected in FROZEN_GIT_BLOBS.items():
        actual = _git_blob(path)
        if actual != expected:
            raise ExactZeroCostCompatError(
                f"frozen X blob changed for {path}: expected {expected}, got {actual}"
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
