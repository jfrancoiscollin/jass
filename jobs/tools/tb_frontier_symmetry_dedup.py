#!/usr/bin/env python3
"""Canonicalize exact TB-frontier parents under Jass's valid board symmetry.

The historical symmetry augmentation used by Jass is exactly:
  rotate the board 180 degrees + exchange White/Black.
For FMJD squares this maps square s -> 51-s; side-to-move is colour-swapped.

Input groups/children already contain exact EGDB sibling labels and exact-state
parent de-duplication.  This pass removes cross-corpus symmetry duplicates,
rewrites parent ids/row ids contiguously, and replaces parent_fingerprint by a
symmetry-canonical fingerprint so the frozen holdout split is symmetry-invariant.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys

REC_SIZE = 38
FIELDS = [
    "row_index", "parent_id", "parent_fingerprint", "parent_stm",
    "from", "to", "num_captures", "promotes", "moving_king",
    "captured_kings", "parent_utility", "child_tb_wdl_stm",
]


def rotate50(bb: int) -> int:
    if bb < 0 or bb >> 50:
        raise ValueError("bitboard outside 50 playable squares")
    out = 0
    while bb:
        bit = (bb & -bb).bit_length() - 1
        bb &= bb - 1
        out |= 1 << (49 - bit)
    return out


def parse_fingerprint(fp: str) -> tuple[int, int, int, int, int]:
    parts = fp.split(":")
    if len(parts) != 5:
        raise ValueError(f"bad parent fingerprint: {fp!r}")
    wm, wk, bm, bk = (int(x, 16) for x in parts[:4])
    stm = int(parts[4])
    if stm not in (0, 1):
        raise ValueError("bad parent STM")
    all_bb = wm | wk | bm | bk
    if all_bb >> 50:
        raise ValueError("fingerprint bitboard outside board")
    if (wm & wk) | (wm & bm) | (wm & bk) | (wk & bm) | (wk & bk) | (bm & bk):
        raise ValueError("overlapping pieces in fingerprint")
    return wm, wk, bm, bk, stm


def format_fingerprint(wm: int, wk: int, bm: int, bk: int, stm: int) -> str:
    return f"{wm:013x}:{wk:013x}:{bm:013x}:{bk:013x}:{stm}"


def symmetric_fingerprint(fp: str) -> str:
    wm, wk, bm, bk, stm = parse_fingerprint(fp)
    return format_fingerprint(
        rotate50(bm), rotate50(bk), rotate50(wm), rotate50(wk), 1 - stm
    )


def canonical_fingerprint(fp: str) -> str:
    normalized = format_fingerprint(*parse_fingerprint(fp))
    sym = symmetric_fingerprint(normalized)
    return min(normalized, sym)


def split_is_holdout(fp: str, seed: int, mod: int) -> bool:
    digest = hashlib.sha256(f"{seed}:{fp}".encode()).digest()
    return int.from_bytes(digest[:8], "little") % mod == 0


def load_children(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError("bad JNNW header")
    n = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + n * REC_SIZE:
        raise ValueError("JNNW count/size drift")
    return [raw[8+i*REC_SIZE:8+(i+1)*REC_SIZE] for i in range(n)]


def load_groups(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if reader.fieldnames != FIELDS:
            raise ValueError(f"unexpected TSV fields {reader.fieldnames!r}")
        rows = list(reader)
    if [int(r["row_index"]) for r in rows] != list(range(len(rows))):
        raise ValueError("non-contiguous row_index")
    return rows


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict:
    rows = load_groups(args.groups)
    children = load_children(args.children)
    if len(rows) != len(children):
        raise ValueError("groups/children row mismatch")

    by_parent: dict[int, list[dict[str, str]]] = {}
    parent_order: list[int] = []
    for row in rows:
        pid = int(row["parent_id"])
        if pid not in by_parent:
            by_parent[pid] = []
            parent_order.append(pid)
        by_parent[pid].append(row)

    seen: dict[str, int] = {}
    kept_parent_color: dict[str, int] = {}
    duplicate_examples: list[dict] = []
    next_pid = 0
    next_row = 0

    args.out_children.parent.mkdir(parents=True, exist_ok=True)
    args.out_groups.parent.mkdir(parents=True, exist_ok=True)
    with args.out_children.open("wb+") as child_out, args.out_groups.open("w", newline="", encoding="utf-8") as group_out:
        child_out.write(b"JNNW" + struct.pack("<I", 0))
        writer = csv.DictWriter(group_out, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for old_pid in parent_order:
            prows = by_parent[old_pid]
            fp = prows[0]["parent_fingerprint"]
            stm = int(prows[0]["parent_stm"])
            if any(r["parent_fingerprint"] != fp or int(r["parent_stm"]) != stm for r in prows):
                raise ValueError("parent id maps to inconsistent fingerprint/color")
            canon = canonical_fingerprint(fp)
            if canon in seen:
                if len(duplicate_examples) < 32:
                    duplicate_examples.append({
                        "dropped_parent_id": old_pid,
                        "kept_parent_id": seen[canon],
                        "source_fingerprint": fp,
                        "canonical_fingerprint": canon,
                    })
                continue
            seen[canon] = next_pid
            kept_parent_color[canon] = stm
            for r in prows:
                old_index = int(r["row_index"])
                out = dict(r)
                out["row_index"] = str(next_row)
                out["parent_id"] = str(next_pid)
                out["parent_fingerprint"] = canon
                writer.writerow(out)
                child_out.write(children[old_index])
                next_row += 1
            next_pid += 1
        child_out.seek(4)
        child_out.write(struct.pack("<I", next_row))

    holdout = [fp for fp in seen if split_is_holdout(fp, args.split_seed, args.holdout_mod)]
    holdout_set = set(holdout)
    hw = sum(kept_parent_color[fp] == 0 for fp in holdout)
    hb = sum(kept_parent_color[fp] == 1 for fp in holdout)
    tw = sum(kept_parent_color[fp] == 0 and fp not in holdout_set for fp in seen)
    tb = sum(kept_parent_color[fp] == 1 and fp not in holdout_set for fp in seen)
    established = (
        len(holdout) >= args.min_holdout_parents
        and hw >= args.min_holdout_per_color
        and hb >= args.min_holdout_per_color
        and tw > 0 and tb > 0
    )
    report = {
        "schema": "jass.tb_frontier.symmetry_dedup.v1",
        "symmetry": "rotate180_plus_color_swap",
        "square_map": "s_to_51_minus_s",
        "input_parents": len(parent_order),
        "unique_canonical_parents": len(seen),
        "symmetry_duplicates_removed": len(parent_order) - len(seen),
        "output_child_rows": next_row,
        "duplicate_examples": duplicate_examples,
        "split": {"seed": args.split_seed, "holdout_mod": args.holdout_mod},
        "support": {
            "established": established,
            "min_holdout_parents": args.min_holdout_parents,
            "min_holdout_per_color": args.min_holdout_per_color,
            "parents_holdout": len(holdout),
            "parents_holdout_by_color": {"white": hw, "black": hb},
            "parents_train_by_color": {"white": tw, "black": tb},
        },
        "strength_games": 0,
        "promotion_authorized": False,
    }
    write_json(args.report, report)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--children", type=Path, required=True)
    ap.add_argument("--out-groups", type=Path, required=True)
    ap.add_argument("--out-children", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--split-seed", type=int, default=2026082801)
    ap.add_argument("--holdout-mod", type=int, default=5)
    ap.add_argument("--min-holdout-parents", type=int, default=800)
    ap.add_argument("--min-holdout-per-color", type=int, default=250)
    args = ap.parse_args()
    try:
        report = run(args)
    except (OSError, ValueError) as exc:
        print(f"tb_frontier_symmetry_dedup: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
