#!/usr/bin/env python3
"""Versioned compatibility adapters for the already-frozen B2 v1 pipeline.

These adapters exist only to replay/finish the frozen B2 contract without
putting compatibility logic into jass-control. New scientific stages must use
native producer/consumer contracts and must not depend on this module.

Two v1 contradictions were discovered only after fresh B2 execution:

* source-publication v1 omitted ``top_up/regeneration/new_seed`` while the v1
  preread required those semantic false values;
* the teacher/native move catalogue preserves raw ``Move.promotes`` (a
  destination-rank flag), so a king move can carry ``moving_king=1,promotes=1``;
  the Python v1 merger redundantly rejected that combination after already
  validating the board transition.

The adapters are deliberately narrow, fail closed, restore imported module
state after invocation, and never alter teacher scores, search budgets, policy,
statistics, or scientific gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b2_teacher_merge as merge_v1  # noqa: E402
from jobs.tools import adaptive_sibling_b2_teacher_preread as preread_v1  # noqa: E402

PREREAD_COMPAT_SCHEMA = "jass.adaptive_sibling_b2_preread_v1_compat.v1"
MERGE_COMPAT_SCHEMA = "jass.adaptive_sibling_b2_merge_v1_compat.v1"


class LegacyCompatError(RuntimeError):
    pass


def _read_selection_report(path: Path) -> Mapping[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegacyCompatError(f"cannot read selection report: {exc}") from exc
    if type(value) is not dict:
        raise LegacyCompatError("selection report must be an object")
    if value.get("top_up") is not False:
        raise LegacyCompatError("selection report does not prove top_up=false")
    return value


def preread_validate_f_compat(
    receipt: Mapping[str, Any], *, selection_report: Path,
    original_validator=None, **kwargs: Any,
) -> None:
    """Validate immutable F v1 while repairing only its omitted false booleans."""
    validator = preread_v1._validate_f if original_validator is None else original_validator
    present = {key for key in ("top_up", "regeneration", "new_seed") if key in receipt}
    if present:
        # A future/native receipt shape is allowed only if the original v1
        # validator accepts the real bytes unchanged.
        validator(receipt, selection_report=selection_report, **kwargs)
        return
    _read_selection_report(selection_report)
    semantic = dict(receipt)
    semantic.update(top_up=False, regeneration=False, new_seed=False)
    validator(semantic, selection_report=selection_report, **kwargs)


def run_preread(argv: Sequence[str]) -> int:
    args = preread_v1.parse_args(argv)
    original = preread_v1._validate_f

    def compat(receipt: Mapping[str, Any], **kwargs: Any) -> None:
        preread_validate_f_compat(
            receipt,
            selection_report=args.selection_report,
            original_validator=original,
            **kwargs,
        )

    preread_v1._validate_f = compat
    try:
        return preread_v1.main(argv)
    finally:
        preread_v1._validate_f = original


def structural_action_compat(
    parent, child, group: Mapping[str, str], parent_meta: Mapping[str, Any],
    shard: int, local_index: int, global_index: int, *, original=None,
) -> dict[str, Any]:
    """Delegate to v1 while accepting the one raw king+promotion flag shape."""
    validator = merge_v1.structural_action if original is None else original
    if group.get("moving_king") == "1" and group.get("promotes") == "1":
        adjusted = dict(group)
        adjusted["promotes"] = "0"
        row = validator(
            parent, child, adjusted, parent_meta, shard, local_index, global_index,
        )
        # Restore the immutable raw teacher/native flag in the semantic ledger.
        row["promotes"] = True
        return row
    return validator(parent, child, group, parent_meta, shard, local_index, global_index)


def run_merge(argv: Sequence[str]) -> int:
    original = merge_v1.structural_action

    def compat(parent, child, group, parent_meta, shard, local_index, global_index):
        return structural_action_compat(
            parent, child, group, parent_meta, shard, local_index, global_index,
            original=original,
        )

    merge_v1.structural_action = compat
    try:
        return merge_v1.main(argv)
    finally:
        merge_v1.structural_action = original


def parse_args(argv: Sequence[str] | None = None) -> tuple[str, list[str]]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preread", "merge"))
    args, remainder = parser.parse_known_args(argv)
    return args.command, remainder


def main(argv: Sequence[str] | None = None) -> int:
    command, remainder = parse_args(argv)
    try:
        if command == "preread":
            return run_preread(remainder)
        return run_merge(remainder)
    except (LegacyCompatError, ValueError, OSError) as exc:
        print(f"adaptive_sibling_b2_legacy_contract_compat: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
