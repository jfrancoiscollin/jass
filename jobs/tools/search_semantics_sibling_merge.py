#!/usr/bin/env python3
"""Merge Discovery A score-free sibling shards and freeze DEEP128 row IDs."""
from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.scan_ceiling_merge import (  # noqa: E402
    OUTPUT_FIELDS, Parent, canonical_move, load_export, record_fingerprint,
    sha256, sibling_identity,
)
from jobs.tools.tb_frontier_symmetry_dedup import canonical_fingerprint  # noqa: E402

EXPECTED_PARENTS = 512
EXPECTED_DEEP = 128
EXPECTED_SHARDS = 16


def load_parents(path: Path) -> dict[int, Parent]:
    parents: dict[int, Parent] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"parent_id", "canonical_fingerprint", "raw_fingerprint",
                    "parent_stm", "pieces", "legal_moves", "phase"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("Discovery parent metadata fields drift")
        for row in reader:
            p = Parent(int(row["parent_id"]), row["canonical_fingerprint"],
                       row["raw_fingerprint"], int(row["parent_stm"]), int(row["pieces"]),
                       int(row["legal_moves"]), row["phase"])
            if p.parent_id in parents or canonical_fingerprint(p.raw) != p.canonical:
                raise ValueError("Discovery parent identity drift")
            parents[p.parent_id] = p
    if sorted(parents) != list(range(EXPECTED_PARENTS)):
        raise ValueError("Discovery parent IDs must be contiguous 0..511")
    return parents


def load_deep(path: Path, parents: dict[int, Parent]) -> set[int]:
    out: set[int] = set()
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"parent_id", "canonical_fingerprint", "phase", "deep_hash"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("DEEP128 fields drift")
        for row in reader:
            pid = int(row["parent_id"]); p = parents.get(pid)
            if p is None or p.canonical != row["canonical_fingerprint"] or p.phase != row["phase"] or pid in out:
                raise ValueError("DEEP128/parent identity drift")
            out.add(pid)
    if len(out) != EXPECTED_DEEP:
        raise ValueError("DEEP128 cardinality drift")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parents", type=Path, required=True)
    ap.add_argument("--deep", type=Path, required=True)
    ap.add_argument("--children-shard", type=Path, action="append", required=True)
    ap.add_argument("--groups-shard", type=Path, action="append", required=True)
    ap.add_argument("--report-shard", type=Path, action="append", required=True)
    ap.add_argument("--expected-shards", type=int, default=EXPECTED_SHARDS)
    ap.add_argument("--out-children", type=Path, required=True)
    ap.add_argument("--out-groups", type=Path, required=True)
    ap.add_argument("--deep-row-ids", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()
    if args.expected_shards != EXPECTED_SHARDS or any(len(x) != EXPECTED_SHARDS for x in
            (args.children_shard, args.groups_shard, args.report_shard)):
        raise ValueError("Discovery sibling shard cardinality drift")
    parents = load_parents(args.parents); deep = load_deep(args.deep, parents)
    exports = []; receipts = []
    for shard, (children, groups, report_path) in enumerate(zip(args.children_shard, args.groups_shard, args.report_shard)):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (report.get("schema") != "jass.search_semantics_sibling_export.v1"
                or report.get("protocol") != "L3_JASS_SCAN_SEARCH_SEMANTICS_ATTRIBUTION_V1_20260829"
                or report.get("benchmark_only") is not True or report.get("target_blind") is not True
                or report.get("score_free") is not True or report.get("curriculum_loaded") is not False
                or report.get("shard") != shard or report.get("nshards") != EXPECTED_SHARDS
                or report.get("input_parents") != EXPECTED_PARENTS
                or report.get("evaluations") != 0 or report.get("searches") != 0
                or report.get("scores_generated") != 0 or report.get("fits") != 0):
            raise ValueError(f"Discovery score-free sibling export report drift for shard {shard}")
        rows = load_export(groups, children)
        if report.get("emitted_siblings") != len(rows):
            raise ValueError("Discovery sibling export row count drift")
        if any(int(row.row["t0_parent"]) != 0 for row in rows):
            raise ValueError("score-free sibling export contains evaluator score")
        exports.extend(rows)
        receipts.append({"shard": shard, "rows": len(rows), "children_sha256": sha256(children),
                         "groups_sha256": sha256(groups), "report_sha256": sha256(report_path)})
    def order(item):
        raw=item.row; pid=int(raw["parent_id"]); p=parents.get(pid)
        if p is None: raise ValueError("sibling parent outside Discovery A")
        cfrom,cto,ccaptured=canonical_move(p,raw)
        return (pid,cfrom,cto,ccaptured,int(raw["promotes"]),canonical_fingerprint(raw["child_fingerprint"]))
    exports.sort(key=order)
    counts=Counter(int(x.row["parent_id"]) for x in exports)
    for pid,p in parents.items():
        if counts[pid] != p.legal_moves: raise ValueError(f"parent {pid} sibling count drift")
    for p in (args.out_children,args.out_groups,args.deep_row_ids,args.manifest): p.parent.mkdir(parents=True,exist_ok=True)
    sibling_ids=set(); deep_rows=[]
    with args.out_children.open("wb") as child_out, args.out_groups.open("w",newline="",encoding="utf-8") as group_out:
        child_out.write(b"JNNW"+struct.pack("<I",len(exports)))
        writer=csv.DictWriter(group_out,fieldnames=OUTPUT_FIELDS,delimiter="\t",lineterminator="\n"); writer.writeheader()
        for row_index,item in enumerate(exports):
            raw=item.row; pid=int(raw["parent_id"]); p=parents[pid]
            if raw["parent_fingerprint"] != p.raw or int(raw["parent_stm"]) != p.stm or int(raw["parent_pieces"]) != p.pieces:
                raise ValueError("sibling/parent metadata drift")
            if record_fingerprint(item.record) != raw["child_fingerprint"]: raise ValueError("child JNNW identity drift")
            identity,cmove,child_canonical=sibling_identity(p,raw)
            if identity in sibling_ids: raise ValueError("duplicate canonical sibling identity")
            sibling_ids.add(identity); cfrom,cto,ccaptured=cmove
            output={"row_index":row_index,"sibling_identity":identity,"parent_id":pid,
                "parent_canonical":p.canonical,"parent_fingerprint":p.raw,"parent_stm":p.stm,
                "parent_pieces":p.pieces,"parent_phase":p.phase,"parent_legal_moves":p.legal_moves,
                "from":raw["from"],"to":raw["to"],"captured_hex":raw["captured_hex"],
                "canonical_from":cfrom,"canonical_to":cto,"canonical_captured_hex":f"{ccaptured:013x}",
                "num_captures":raw["num_captures"],"promotes":raw["promotes"],"moving_king":raw["moving_king"],
                "captured_kings":raw["captured_kings"],"material_count_delta_parent":raw["material_count_delta_parent"],
                "child_fingerprint":raw["child_fingerprint"],"child_canonical":child_canonical,
                "child_pieces":raw["child_pieces"],"child_legal_moves":raw["child_legal_moves"],
                "child_forced_capture":raw["child_forced_capture"],"child_rule_terminal":raw["child_rule_terminal"],
                "child_tb_exact":raw["child_tb_exact"],"exact_parent_utility":raw["exact_parent_utility"],"t0_parent":0}
            writer.writerow(output); child_out.write(item.record)
            if pid in deep: deep_rows.append(row_index)
    args.deep_row_ids.write_text("".join(f"{x}\n" for x in deep_rows),encoding="utf-8")
    payload={"schema":"jass.search_semantics_discovery_a_sibling_merge.v1","benchmark_only":True,
        "target_blind":True,"score_free":True,"curriculum_loaded":False,
        "parents":len(parents),"siblings":len(exports),"parents_by_phase":dict(sorted(Counter(p.phase for p in parents.values()).items())),
        "deep128_parents":len(deep),"deep128_siblings":len(deep_rows),"canonical_sibling_identities_unique":len(sibling_ids)==len(exports),
        "shards":receipts,"parents_sha256":sha256(args.parents),"children_sha256":sha256(args.out_children),
        "groups_sha256":sha256(args.out_groups),"deep_row_ids_sha256":sha256(args.deep_row_ids),
        "evaluations":0,"searches":0,"scores_generated":0,"fits":0,"strength_games":0,
        "training_allowed":False,"tuning_allowed":False,"model_selection_allowed":False,"promotion_authorized":False}
    args.manifest.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"parents":512,"siblings":len(exports),"deep128_siblings":len(deep_rows)},sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
