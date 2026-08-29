#!/usr/bin/env python3
"""Merge immutable sibling-export shards and derive canonical sibling IDs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.tb_frontier_symmetry_dedup import (  # noqa: E402
    canonical_fingerprint,
    format_fingerprint,
    parse_fingerprint,
    rotate50,
)

RECORD_SIZE = 38
EXPORT_FIELDS = [
    "local_row_index", "parent_id", "parent_fingerprint", "parent_stm",
    "parent_pieces", "from", "to", "captured_hex", "num_captures",
    "promotes", "moving_king", "captured_kings",
    "material_count_delta_parent", "child_fingerprint", "child_pieces",
    "child_legal_moves", "child_forced_capture", "child_rule_terminal",
    "child_tb_exact", "exact_parent_utility", "t0_parent",
]
OUTPUT_FIELDS = [
    "row_index", "sibling_identity", "parent_id", "parent_canonical",
    "parent_fingerprint", "parent_stm", "parent_pieces", "parent_phase",
    "parent_legal_moves", "from", "to", "captured_hex", "canonical_from",
    "canonical_to", "canonical_captured_hex", "num_captures", "promotes",
    "moving_king", "captured_kings", "material_count_delta_parent",
    "child_fingerprint", "child_canonical", "child_pieces",
    "child_legal_moves", "child_forced_capture", "child_rule_terminal",
    "child_tb_exact", "exact_parent_utility", "t0_parent",
]


@dataclass(frozen=True)
class Parent:
    parent_id: int
    canonical: str
    raw: str
    stm: int
    pieces: int
    legal_moves: int
    phase: str


@dataclass
class Exported:
    row: dict[str, str]
    record: bytes


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_parents(path: Path) -> dict[int, Parent]:
    parents: dict[int, Parent] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {
            "parent_id", "canonical_fingerprint", "raw_fingerprint",
            "parent_stm", "pieces", "legal_moves", "phase",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("parent metadata fields drift")
        for row in reader:
            parent = Parent(
                int(row["parent_id"]), row["canonical_fingerprint"],
                row["raw_fingerprint"], int(row["parent_stm"]),
                int(row["pieces"]), int(row["legal_moves"]), row["phase"],
            )
            if parent.parent_id in parents:
                raise ValueError("duplicate parent_id")
            if canonical_fingerprint(parent.raw) != parent.canonical:
                raise ValueError("parent raw/canonical identity drift")
            parents[parent.parent_id] = parent
    if sorted(parents) != list(range(2000)):
        raise ValueError("benchmark parent IDs must be contiguous 0..1999")
    return parents


def load_subset(path: Path, parents: dict[int, Parent], expected: int) -> set[int]:
    out: set[int] = set()
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"parent_id", "canonical_fingerprint", "phase", "subset_hash"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("subset fields drift")
        for row in reader:
            pid = int(row["parent_id"])
            parent = parents.get(pid)
            if parent is None or parent.canonical != row["canonical_fingerprint"] or parent.phase != row["phase"]:
                raise ValueError("subset/parent identity drift")
            if pid in out:
                raise ValueError("duplicate subset parent")
            out.add(pid)
    if len(out) != expected:
        raise ValueError(f"subset cardinality {len(out)} != {expected}")
    return out


def load_child_records(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError(f"{path}: bad JNNW header")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * RECORD_SIZE:
        raise ValueError(f"{path}: JNNW count/size drift")
    return [raw[8 + i * RECORD_SIZE:8 + (i + 1) * RECORD_SIZE] for i in range(count)]


def record_fingerprint(record: bytes) -> str:
    if len(record) != RECORD_SIZE or record[32] not in (0, 1) or record[33:38] != b"\0" * 5:
        raise ValueError("invalid or labelled child JNNW record")
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    value = format_fingerprint(wm, wk, bm, bk, record[32])
    parse_fingerprint(value)
    return value


def load_export(groups: Path, children: Path) -> list[Exported]:
    records = load_child_records(children)
    with groups.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != EXPORT_FIELDS:
            raise ValueError(f"{groups}: export fields drift {reader.fieldnames!r}")
        rows = list(reader)
    if len(rows) != len(records) or [int(row["local_row_index"]) for row in rows] != list(range(len(rows))):
        raise ValueError("export group/child alignment drift")
    return [Exported(row, record) for row, record in zip(rows, records)]


def canonical_move(parent: Parent, row: dict[str, str]) -> tuple[int, int, int]:
    normalized = ":".join([
        f"{value:013x}" for value in parse_fingerprint(parent.raw)[:4]
    ]) + f":{parse_fingerprint(parent.raw)[4]}"
    frm = int(row["from"]); to = int(row["to"]); captured = int(row["captured_hex"], 16)
    if normalized == parent.canonical:
        return frm, to, captured
    return 51 - frm, 51 - to, rotate50(captured)


def sibling_identity(parent: Parent, row: dict[str, str]) -> tuple[str, tuple[int, int, int], str]:
    cfrom, cto, ccaptured = canonical_move(parent, row)
    child_canonical = canonical_fingerprint(row["child_fingerprint"])
    payload = (
        f"{parent.canonical}|{cfrom}|{cto}|{ccaptured:013x}|"
        f"{int(row['promotes'])}|{child_canonical}"
    )
    return hashlib.sha256(payload.encode()).hexdigest(), (cfrom, cto, ccaptured), child_canonical


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parents", type=Path, required=True)
    parser.add_argument("--deep", type=Path, required=True)
    parser.add_argument("--ultra", type=Path, required=True)
    parser.add_argument("--children-shard", type=Path, action="append", required=True)
    parser.add_argument("--groups-shard", type=Path, action="append", required=True)
    parser.add_argument("--report-shard", type=Path, action="append", required=True)
    parser.add_argument("--expected-shards", type=int, default=16)
    parser.add_argument("--out-children", type=Path, required=True)
    parser.add_argument("--out-groups", type=Path, required=True)
    parser.add_argument("--deep-row-ids", type=Path, required=True)
    parser.add_argument("--ultra-row-ids", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    paths = (args.children_shard, args.groups_shard, args.report_shard)
    if any(len(values) != args.expected_shards for values in paths):
        raise ValueError("export shard cardinality drift")

    parents = load_parents(args.parents)
    deep = load_subset(args.deep, parents, 512)
    ultra = load_subset(args.ultra, parents, 256)
    if not ultra < deep:
        raise ValueError("ULTRA256 is not a strict DEEP512 subset")

    exports: list[Exported] = []
    report_receipts = []
    for shard, (children, groups, report_path) in enumerate(zip(*paths)):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (report.get("schema") != "jass.scan_ceiling_sibling_export.v1"
                or report.get("shard") != shard
                or report.get("nshards") != args.expected_shards
                or report.get("input_parents") != 2000
                or report.get("searches") != 0
                or report.get("fits") != 0):
            raise ValueError(f"export report contract drift for shard {shard}")
        rows = load_export(groups, children)
        if report.get("emitted_siblings") != len(rows):
            raise ValueError("export report row count drift")
        exports.extend(rows)
        report_receipts.append({
            "shard": shard, "rows": len(rows),
            "children_sha256": sha256(children), "groups_sha256": sha256(groups),
            "report_sha256": sha256(report_path),
        })

    def order(item: Exported):
        row = item.row
        pid = int(row["parent_id"])
        if pid not in parents:
            raise ValueError("export parent_id outside frozen cohort")
        cfrom, cto, ccaptured = canonical_move(parents[pid], row)
        return (
            pid, cfrom, cto, ccaptured, int(row["promotes"]),
            canonical_fingerprint(row["child_fingerprint"]),
        )

    exports.sort(key=order)
    parent_counts = Counter(int(item.row["parent_id"]) for item in exports)
    for pid, parent in parents.items():
        if parent_counts[pid] != parent.legal_moves:
            raise ValueError(f"parent {pid} sibling count drift")

    for path in (
        args.out_children, args.out_groups, args.deep_row_ids,
        args.ultra_row_ids, args.manifest,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    with args.out_children.open("wb") as child_out, \
            args.out_groups.open("w", newline="", encoding="utf-8") as group_out:
        child_out.write(b"JNNW" + struct.pack("<I", len(exports)))
        writer = csv.DictWriter(group_out, fieldnames=OUTPUT_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        sibling_ids: set[str] = set()
        deep_rows: list[int] = []
        ultra_rows: list[int] = []
        for row_index, item in enumerate(exports):
            raw = item.row
            pid = int(raw["parent_id"])
            parent = parents[pid]
            if (raw["parent_fingerprint"] != parent.raw
                    or int(raw["parent_stm"]) != parent.stm
                    or int(raw["parent_pieces"]) != parent.pieces):
                raise ValueError("export/parent metadata drift")
            if record_fingerprint(item.record) != raw["child_fingerprint"]:
                raise ValueError("export child fingerprint/JNNW drift")
            captured = int(raw["captured_hex"], 16)
            if captured.bit_count() != int(raw["num_captures"]):
                raise ValueError("captured bitboard/count drift")
            terminal = int(raw["child_rule_terminal"])
            tb_exact = int(raw["child_tb_exact"])
            exact_utility = int(raw["exact_parent_utility"])
            if terminal not in (0, 1) or tb_exact not in (0, 1) or terminal + tb_exact > 1:
                raise ValueError("invalid exact child flags")
            if terminal and int(raw["child_legal_moves"]) != 0:
                raise ValueError("terminal child still has legal moves")
            if ((terminal or tb_exact) and exact_utility not in (-1, 0, 1)) \
                    or (not terminal and not tb_exact and exact_utility != 2):
                raise ValueError("exact child utility/sentinel drift")
            identity, cmove, child_canonical = sibling_identity(parent, raw)
            if identity in sibling_ids:
                raise ValueError("duplicate canonical sibling identity")
            sibling_ids.add(identity)
            cfrom, cto, ccaptured = cmove
            output = {
                "row_index": row_index,
                "sibling_identity": identity,
                "parent_id": pid,
                "parent_canonical": parent.canonical,
                "parent_fingerprint": parent.raw,
                "parent_stm": parent.stm,
                "parent_pieces": parent.pieces,
                "parent_phase": parent.phase,
                "parent_legal_moves": parent.legal_moves,
                "from": raw["from"], "to": raw["to"],
                "captured_hex": raw["captured_hex"],
                "canonical_from": cfrom, "canonical_to": cto,
                "canonical_captured_hex": f"{ccaptured:013x}",
                "num_captures": raw["num_captures"],
                "promotes": raw["promotes"], "moving_king": raw["moving_king"],
                "captured_kings": raw["captured_kings"],
                "material_count_delta_parent": raw["material_count_delta_parent"],
                "child_fingerprint": raw["child_fingerprint"],
                "child_canonical": child_canonical,
                "child_pieces": raw["child_pieces"],
                "child_legal_moves": raw["child_legal_moves"],
                "child_forced_capture": raw["child_forced_capture"],
                "child_rule_terminal": raw["child_rule_terminal"],
                "child_tb_exact": raw["child_tb_exact"],
                "exact_parent_utility": raw["exact_parent_utility"],
                "t0_parent": raw["t0_parent"],
            }
            writer.writerow(output)
            child_out.write(item.record)
            if pid in deep: deep_rows.append(row_index)
            if pid in ultra: ultra_rows.append(row_index)

    args.deep_row_ids.write_text("".join(f"{row}\n" for row in deep_rows), encoding="utf-8")
    args.ultra_row_ids.write_text("".join(f"{row}\n" for row in ultra_rows), encoding="utf-8")
    payload = {
        "schema": "jass.scan_ceiling_sibling_merge.v1",
        "benchmark_only": True,
        "parents": len(parents),
        "siblings": len(exports),
        "parents_by_phase": dict(sorted(Counter(p.phase for p in parents.values()).items())),
        "siblings_by_phase": dict(sorted(Counter(parents[int(x.row["parent_id"])].phase for x in exports).items())),
        "deep512_parents": len(deep), "deep512_siblings": len(deep_rows),
        "ultra256_parents": len(ultra), "ultra256_siblings": len(ultra_rows),
        "ultra_strict_subset_of_deep": ultra < deep,
        "canonical_sibling_identities_unique": len(sibling_ids) == len(exports),
        "shards": report_receipts,
        "parents_sha256": sha256(args.parents),
        "children_sha256": sha256(args.out_children),
        "groups_sha256": sha256(args.out_groups),
        "deep_row_ids_sha256": sha256(args.deep_row_ids),
        "ultra_row_ids_sha256": sha256(args.ultra_row_ids),
        "fits": 0, "calibrations": 0, "strength_games": 0,
        "training_allowed": False, "tuning_allowed": False,
        "calibration_allowed": False, "model_selection_allowed": False,
        "runtime_scale_selection_allowed": False,
        "promotion_authorized": False,
    }
    args.manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"siblings": len(exports), "deep": len(deep_rows), "ultra": len(ultra_rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
