#!/usr/bin/env python3
"""Prepare authenticated C SiblingDataset-v2 children for frozen D1 training/readout.

Input is the canonical parent-group JSONL emitted by C. Child positions are
reconstructed only from production-verified child_identity fingerprints. No
teacher score, q5/q50/q200 value, audit reference, or full-ladder datum is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any, Sequence

SCHEMA = "jass.d1.selected_action_groups.v1"
RECEIPT_SCHEMA = "jass.d1.decision_prepare.v1"
PARENT_SCHEMA = "jass.sibling_dataset_v2.parent.v1"
PARENTS = 4000
ACTIONS = 38053
SPLITS = {"train": 3200, "valid": 400, "test": 400}


class D1PrepareError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_new(path: Path, data: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise D1PrepareError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise D1PrepareError(f"refusing existing temporary {tmp}")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def parse_fingerprint(text: object) -> tuple[int, int, int, int, int]:
    if not isinstance(text, str) or not text.isascii():
        raise D1PrepareError("child_identity must be ASCII string")
    parts = text.split(":")
    if len(parts) != 5 or any(len(p) != 13 for p in parts[:4]) or parts[4] not in {"0", "1"}:
        raise D1PrepareError(f"invalid child_identity format: {text!r}")
    try:
        wm, wk, bm, bk = (int(p, 16) for p in parts[:4])
    except ValueError as exc:
        raise D1PrepareError("child_identity contains non-hex board field") from exc
    if any(v < 0 or v >= (1 << 50) for v in (wm, wk, bm, bk)):
        raise D1PrepareError("child_identity bitboard outside 50 squares")
    if (wm & wk) or (wm & bm) or (wm & bk) or (wk & bm) or (wk & bk) or (bm & bk):
        raise D1PrepareError("child_identity contains overlapping pieces")
    return wm, wk, bm, bk, int(parts[4])


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise D1PrepareError("dataset JSONL must be LF terminated")
    rows: list[dict[str, Any]] = []
    for n, line in enumerate(raw.splitlines(keepends=True), 1):
        try:
            row = json.loads(line.decode("ascii"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise D1PrepareError(f"dataset JSONL parse failure line {n}") from exc
        if type(row) is not dict or row.get("schema") != PARENT_SCHEMA or canonical(row) != line:
            raise D1PrepareError(f"dataset JSONL canonical/schema failure line {n}")
        rows.append(row)
    return rows


def build(dataset: Path, out_jnnw: Path, out_groups: Path,
          out_receipt: Path) -> dict[str, Any]:
    parents = read_jsonl(dataset)
    if len(parents) != PARENTS:
        raise D1PrepareError(f"expected {PARENTS} parents, got {len(parents)}")
    records = bytearray(b"JNNW" + struct.pack("<I", ACTIONS))
    groups: list[dict[str, Any]] = []
    split_counts = {k: 0 for k in SPLITS}
    split_actions = {k: 0 for k in SPLITS}
    cursor = 0
    for expected_parent, parent in enumerate(parents):
        if parent.get("parent_id") != expected_parent or type(parent.get("parent_id")) is not int:
            raise D1PrepareError("parent ids are not contiguous")
        split = parent.get("split")
        if split not in SPLITS:
            raise D1PrepareError("unknown parent split")
        parent_stm = parent.get("stm")
        if type(parent_stm) is not int or parent_stm not in (0, 1):
            raise D1PrepareError("parent stm invalid")
        actions = parent.get("actions")
        if not isinstance(actions, list) or not 2 <= len(actions) <= 16:
            raise D1PrepareError("parent actions invalid")
        selected = [i for i, action in enumerate(actions)
                    if isinstance(action, dict) and action.get("selected") is True]
        if len(selected) != 1:
            raise D1PrepareError("parent must have exactly one selected action")
        start = cursor
        for local, action in enumerate(actions):
            if type(action) is not dict or action.get("local_action_index") != local:
                raise D1PrepareError("action order/index invalid")
            wm, wk, bm, bk, stm = parse_fingerprint(action.get("child_identity"))
            if stm == parent_stm:
                raise D1PrepareError("child stm did not flip from parent")
            records += struct.pack("<QQQQBiB", wm, wk, bm, bk, stm, 0, 0)
            cursor += 1
        cell = parent.get("cell")
        if not isinstance(cell, str) or not cell.isascii():
            raise D1PrepareError("parent cell invalid")
        groups.append({
            "cell": cell,
            "count": len(actions),
            "parent_id": expected_parent,
            "parent_stm": parent_stm,
            "selected_local_action_index": selected[0],
            "split": split,
            "start": start,
        })
        split_counts[split] += 1
        split_actions[split] += len(actions)
    if cursor != ACTIONS:
        raise D1PrepareError(f"expected {ACTIONS} actions, got {cursor}")
    if split_counts != SPLITS:
        raise D1PrepareError(f"split parent counts drift: {split_counts}")
    payload = {
        "actions": ACTIONS,
        "groups": groups,
        "parents": PARENTS,
        "schema": SCHEMA,
        "split_actions": split_actions,
        "split_parents": split_counts,
    }
    write_new(out_jnnw, bytes(records))
    write_new(out_groups, canonical(payload))
    receipt = {
        "actions": ACTIONS,
        "child_jnnw": {"sha256": sha_file(out_jnnw), "size_bytes": out_jnnw.stat().st_size},
        "dataset_sha256": sha_file(dataset),
        "full_ladder_reference_reads": 0,
        "groups": {"sha256": sha_file(out_groups), "size_bytes": out_groups.stat().st_size},
        "parents": PARENTS,
        "qscore_reads": 0,
        "schema": RECEIPT_SCHEMA,
        "split_actions": split_actions,
        "split_parents": split_counts,
    }
    write_new(out_receipt, canonical(receipt))
    return receipt


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out-jnnw", type=Path, required=True)
    p.add_argument("--out-groups", type=Path, required=True)
    p.add_argument("--out-receipt", type=Path, required=True)
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        r = build(**vars(parse_args(argv)))
    except Exception as exc:
        print(f"d1_decision_prepare: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"parents": r["parents"], "actions": r["actions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
