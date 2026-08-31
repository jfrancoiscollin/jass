#!/usr/bin/env python3
"""Target-blind fresh-pool selector for preregistered T3/F6 E2.

Membership is frozen by SHA256("2026100102:" + canonical_identity).  The
separate execution-order seed is realized target-blind by a second SHA256 rank
inside each frozen cell; this changes no cell membership.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.t3_f6_r0_select import fen_fingerprint, fen_rows, load_tsv_identities

GENERATION_SEED = 2026100101
SELECTION_SEED = 2026100102
EXECUTION_SEED = 2026100104
CANDIDATES = 30000
CELL_SIZES = {"C1": 750, "C2": 400, "C3": 200}


def digest(seed: int, identity: str) -> bytes:
    return hashlib.sha256(f"{seed}:{identity}".encode("utf-8")).digest()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--exclude-fen", type=Path, action="append", default=[])
    parser.add_argument("--exclude-tsv", type=Path, action="append", default=[])
    parser.add_argument("--generator-seed", type=int, default=GENERATION_SEED)
    parser.add_argument("--selection-seed", type=int, default=SELECTION_SEED)
    parser.add_argument("--execution-seed", type=int, default=EXECUTION_SEED)
    parser.add_argument("--out-c1", type=Path, required=True)
    parser.add_argument("--out-c2", type=Path, required=True)
    parser.add_argument("--out-c3", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if (args.generator_seed, args.selection_seed, args.execution_seed) != (
            GENERATION_SEED, SELECTION_SEED, EXECUTION_SEED):
        raise ValueError("E2 preregistered seed drift")

    candidates = fen_rows(args.candidates)
    if len(candidates) != CANDIDATES:
        raise ValueError(f"E2 candidate cardinality {len(candidates)} != {CANDIDATES}")

    excluded: set[str] = set()
    sources: dict[str, int] = {}
    for path in args.exclude_fen:
        ids = {fen_fingerprint(fen)[0] for fen in fen_rows(path)}
        excluded.update(ids)
        sources[str(path)] = len(ids)
    for path in args.exclude_tsv:
        ids = load_tsv_identities(path)
        excluded.update(ids)
        sources[str(path)] = len(ids)

    unique: dict[str, str] = {}
    duplicates = excluded_occurrences = 0
    for fen in candidates:
        identity = fen_fingerprint(fen)[0]
        if identity in excluded:
            excluded_occurrences += 1
            continue
        old = unique.get(identity)
        if old is None:
            unique[identity] = fen
        else:
            duplicates += 1
            unique[identity] = min(old, fen)

    ranked = sorted(unique.items(), key=lambda item: (
        digest(SELECTION_SEED, item[0]), item[0], item[1]))
    total = sum(CELL_SIZES.values())
    if len(ranked) < total:
        raise ValueError(f"E2 fresh support {len(ranked)} < {total}")
    selected = ranked[:total]

    boundaries = {
        "C1": selected[:750],
        "C2": selected[750:1150],
        "C3": selected[1150:1350],
    }
    paths = {"C1": args.out_c1, "C2": args.out_c2, "C3": args.out_c3}
    cell_ids: dict[str, set[str]] = {}
    cell_sha: dict[str, str] = {}
    for name in ("C1", "C2", "C3"):
        # Membership stays exactly the selection-rank slice; only execution order
        # is ranked by the separately preregistered execution seed.
        ordered = sorted(boundaries[name], key=lambda item: (
            digest(EXECUTION_SEED, item[0]), item[0], item[1]))
        ids = {identity for identity, _ in ordered}
        if len(ids) != CELL_SIZES[name]:
            raise ValueError(f"E2 {name} identity cardinality drift")
        cell_ids[name] = ids
        paths[name].write_text("\n".join(fen for _, fen in ordered) + "\n",
                               encoding="utf-8")
        cell_sha[name] = sha(paths[name])

    if cell_ids["C1"] & cell_ids["C2"] or cell_ids["C1"] & cell_ids["C3"] \
            or cell_ids["C2"] & cell_ids["C3"]:
        raise ValueError("E2 inter-cell overlap")
    selected_ids = set().union(*cell_ids.values())
    if selected_ids & excluded:
        raise ValueError("E2 selected/forbidden overlap")

    payload = {
        "schema": "jass.t3_f6_e2_fresh_pool.v1",
        "verdict": "E2_FRESH_TARGET_BLIND_POOL_READY",
        "passed": True,
        "candidate_records": len(candidates),
        "candidate_sha256": sha(args.candidates),
        "generator_seed": GENERATION_SEED,
        "selection_seed": SELECTION_SEED,
        "execution_seed": EXECUTION_SEED,
        "selection_rule": "SHA256('2026100102:' + canonical_identity)",
        "execution_order_rule": "within_cell_SHA256('2026100104:' + canonical_identity)",
        "canonicalization": "exact_plus_rotate180_colour_swap",
        "selected": total,
        "cell_openings": dict(CELL_SIZES),
        "cell_sha256": cell_sha,
        "unique_after_exclusion": len(unique),
        "duplicates_removed": duplicates,
        "excluded_occurrences": excluded_occurrences,
        "excluded_unique": len(excluded),
        "excluded_sources": sources,
        "inter_cell_overlap": 0,
        "forbidden_overlap": 0,
        "score_reads": 0,
        "wdl_reads": 0,
        "deep_label_reads": 0,
        "target_blind": True,
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
