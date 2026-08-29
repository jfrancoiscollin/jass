#!/usr/bin/env python3
"""Frozen target-blind selector for Search-Semantics Attribution V1 Discovery A."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.scan_ceiling_select import Candidate, PHASE_ORDER, collect_candidates, load_exclusions, sha256, write_jnnw  # noqa: E402

SOURCE_SEED_BASE = 2026091410
SELECTION_SEED = 2026091401
SUBSET_HASH_SEED = 2026091402
BOOTSTRAP_SEED = 2026091403
SELECTION_DOMAIN = "L3_SEARCH_SEMANTICS_DISCOVERY_A_V1"
DEEP_DOMAIN = "L3_SEARCH_SEMANTICS_DEEP128_V1"
PER_PHASE = 128
DEEP_PER_PHASE = 32
EXPECTED_SHARDS = 16


def frozen_hash(domain: str, seed: int, identity: str) -> str:
    return hashlib.sha256((domain + str(seed) + identity).encode("utf-8")).hexdigest()


def select(unique: dict[str, Candidate]) -> tuple[list[Candidate], set[str], dict[str, int]]:
    selected: list[Candidate] = []; deep: set[str] = set(); available: dict[str, int] = {}
    for phase in PHASE_ORDER:
        rows = [c for c in unique.values() if c.phase == phase]
        rows.sort(key=lambda c: (frozen_hash(SELECTION_DOMAIN, SELECTION_SEED, c.canonical), c.canonical))
        available[phase] = len(rows)
        if len(rows) < PER_PHASE:
            raise ValueError(f"Discovery A support insufficient in {phase}: {len(rows)} < {PER_PHASE}")
        chosen = rows[:PER_PHASE]; selected.extend(chosen)
        nested = sorted(chosen, key=lambda c: (frozen_hash(DEEP_DOMAIN, SUBSET_HASH_SEED, c.canonical), c.canonical))
        deep.update(c.canonical for c in nested[:DEEP_PER_PHASE])
    if len(selected) != 512 or len(deep) != 128: raise AssertionError("Discovery A/DEEP128 cardinality drift")
    return selected, deep, available


def write_outputs(selected: list[Candidate], deep: set[str], out_jnnw: Path, out_tsv: Path, deep_tsv: Path) -> None:
    for p in (out_jnnw, out_tsv, deep_tsv): p.parent.mkdir(parents=True, exist_ok=True)
    write_jnnw(out_jnnw, selected)
    fields = ["parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm", "pieces", "legal_moves", "phase", "source_shard", "source_row_index", "selection_hash", "deep_hash", "in_deep128"]
    subset_fields = ["parent_id", "canonical_fingerprint", "phase", "deep_hash"]
    deep_rows = []
    with out_tsv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n"); w.writeheader()
        for parent_id, c in enumerate(selected):
            row = {"parent_id": parent_id, "canonical_fingerprint": c.canonical, "raw_fingerprint": c.raw_fingerprint,
                   "parent_stm": c.stm, "pieces": c.pieces, "legal_moves": c.legal_moves, "phase": c.phase,
                   "source_shard": c.source_shard, "source_row_index": c.source_row_index,
                   "selection_hash": frozen_hash(SELECTION_DOMAIN, SELECTION_SEED, c.canonical),
                   "deep_hash": frozen_hash(DEEP_DOMAIN, SUBSET_HASH_SEED, c.canonical), "in_deep128": int(c.canonical in deep)}
            w.writerow(row)
            if c.canonical in deep: deep_rows.append(row)
    order = {p: i for i, p in enumerate(PHASE_ORDER)}
    deep_rows.sort(key=lambda r: (order[str(r["phase"])], str(r["deep_hash"]), str(r["canonical_fingerprint"])))
    with deep_tsv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=subset_fields, delimiter="\t", lineterminator="\n"); w.writeheader()
        for row in deep_rows: w.writerow({k: row[k] for k in subset_fields})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--filtered-jnnw", type=Path, action="append", required=True); ap.add_argument("--filtered-meta", type=Path, action="append", required=True)
    ap.add_argument("--exclude-fen", type=Path, action="append", default=[]); ap.add_argument("--exclude-tsv", type=Path, action="append", default=[])
    ap.add_argument("--exclusion-inventory", type=Path, required=True)
    ap.add_argument("--source-seed-base", type=int, default=SOURCE_SEED_BASE); ap.add_argument("--selection-seed", type=int, default=SELECTION_SEED)
    ap.add_argument("--subset-hash-seed", type=int, default=SUBSET_HASH_SEED); ap.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    ap.add_argument("--expected-shards", type=int, default=EXPECTED_SHARDS)
    ap.add_argument("--out-jnnw", type=Path, required=True); ap.add_argument("--out-tsv", type=Path, required=True); ap.add_argument("--deep-tsv", type=Path, required=True); ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if (args.source_seed_base, args.selection_seed, args.subset_hash_seed, args.bootstrap_seed, args.expected_shards) != (SOURCE_SEED_BASE, SELECTION_SEED, SUBSET_HASH_SEED, BOOTSTRAP_SEED, EXPECTED_SHARDS):
        raise ValueError("preregistered Discovery A random contract drift")
    if len(args.filtered_jnnw) != EXPECTED_SHARDS or len(args.filtered_meta) != EXPECTED_SHARDS: raise ValueError("Discovery A source shard cardinality drift")
    inventory = json.loads(args.exclusion_inventory.read_text(encoding="utf-8"))
    if inventory.get("schema") != "jass.search_semantics_exclusion_inventory.v1" or inventory.get("passed") is not True: raise ValueError("mandatory exclusion inventory not authenticated")
    excluded, receipts = load_exclusions(args.exclude_fen, args.exclude_tsv)
    excluded_sha = hashlib.sha256(("\n".join(sorted(excluded)) + "\n").encode()).hexdigest()
    if len(excluded) != int(inventory.get("merged_canonical_count", -1)) or excluded_sha != inventory.get("sorted_exclusion_set_sha256"):
        raise ValueError("loaded exclusion set does not match authenticated inventory")
    unique, counts = collect_candidates(args.filtered_jnnw, args.filtered_meta, excluded, SELECTION_SEED, SUBSET_HASH_SEED)
    selected, deep, available = select(unique); write_outputs(selected, deep, args.out_jnnw, args.out_tsv, args.deep_tsv)
    ids = [c.canonical for c in selected]
    payload = {"schema": "jass.search_semantics_discovery_a_selection.v1", "protocol": "L3_JASS_SCAN_SEARCH_SEMANTICS_ATTRIBUTION_V1_20260829",
        "passed": True, "benchmark_only": True, "target_blind": True, "scores_read": 0, "labels_read": 0, "fits": 0, "calibrations": 0,
        "strength_games": 0, "training_allowed": False, "tuning_allowed": False, "model_selection_allowed": False, "promotion_authorized": False,
        "source_seed_base": SOURCE_SEED_BASE, "selection_seed": SELECTION_SEED, "subset_hash_seed": SUBSET_HASH_SEED, "bootstrap_seed": BOOTSTRAP_SEED,
        "rng_contract": "numpy.random.Generator(numpy.random.PCG64(seed))", "selection_domain": SELECTION_DOMAIN, "deep_domain": DEEP_DOMAIN,
        "canonicalization": "exact_plus_rotate180_colour_swap", "exclusion_inventory_sha256": sha256(args.exclusion_inventory),
        "exclusion_sources": inventory.get("sources", []), "local_exclusion_receipts": receipts, "merged_canonical_exclusions": len(excluded), "sorted_exclusion_set_sha256": excluded_sha,
        **counts, "phase_available": available, "selected": len(selected), "selected_by_phase": dict(sorted(Counter(c.phase for c in selected).items())),
        "selected_by_side": {"white": sum(c.stm == 0 for c in selected), "black": sum(c.stm == 1 for c in selected)}, "deep128": len(deep),
        "deep128_by_phase": dict(sorted(Counter(c.phase for c in selected if c.canonical in deep).items())), "forbidden_overlap": len(set(ids) & excluded),
        "cohort_identity_sha256": hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest(), "parents_jnnw_sha256": sha256(args.out_jnnw),
        "parents_tsv_sha256": sha256(args.out_tsv), "deep128_tsv_sha256": sha256(args.deep_tsv)}
    if payload["selected_by_phase"] != {"P0": 128, "P1": 128, "P2": 128, "P3": 128}: raise AssertionError("Discovery A phase quota drift")
    if payload["deep128_by_phase"] != {"P0": 32, "P1": 32, "P2": 32, "P3": 32}: raise AssertionError("DEEP128 phase quota drift")
    if payload["forbidden_overlap"] != 0: raise AssertionError("Discovery A exclusion overlap")
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"selected": 512, "deep128": 128, "excluded": len(excluded)}, sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
