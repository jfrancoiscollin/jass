#!/usr/bin/env python3
"""Aggregate authenticated D4 teacher shard reports without reading labels/outcomes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_SPLITS = {"train": 3200, "valid": 400, "test": 400}
FORBIDDEN = (
    "game_outcome_reads", "qscore_reads", "search_decision_trace_reads",
    "full_ladder_1843_reads", "d3_score_reads",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, action="append", required=True)
    ap.add_argument("--code-sha", required=True)
    ap.add_argument("--model-sha256", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if len(args.report) != 16:
        raise ValueError(f"expected 16 teacher shard reports, got {len(args.report)}")

    totals = {
        "roots": 0,
        "teacher_searches": 0,
        "node_overshoot_mismatches": 0,
        "total_nodes": 0,
        "total_eval_calls": 0,
        "eligible_cutoff_events": 0,
    }
    splits = {k: 0 for k in EXPECTED_SPLITS}
    for path in args.report:
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("schema") != "jass.d4.search_utility_teacher_export.v1":
            raise ValueError(f"teacher report schema drift: {path}")
        if row.get("declared_code_sha") != args.code_sha:
            raise ValueError(f"teacher code provenance drift: {path}")
        if row.get("model_sha256") != args.model_sha256:
            raise ValueError(f"teacher WDL provenance drift: {path}")
        if row.get("exact_nodes_per_root") != 50000 or row.get("threads") != 1 \
                or row.get("book") is not False:
            raise ValueError(f"teacher search contract drift: {path}")
        if row.get("fits") != 0 or row.get("strength_games") != 0 \
                or row.get("promotions") != 0 or row.get("bakes") != 0:
            raise ValueError(f"teacher side-effect drift: {path}")
        for key in FORBIDDEN:
            if row.get(key) != 0:
                raise ValueError(f"forbidden teacher read {key}: {path}")
        for key in totals:
            totals[key] += int(row.get(key, 0))
        for key in splits:
            splits[key] += int(row.get("root_splits", {}).get(key, 0))

    if totals["roots"] != 4000 or totals["teacher_searches"] != 4000:
        raise ValueError(f"teacher root/search cardinality drift: {totals}")
    if totals["node_overshoot_mismatches"] != 0:
        raise ValueError("exact-node teacher overshoot")
    if splits != EXPECTED_SPLITS:
        raise ValueError(f"teacher split cardinality drift: {splits}")
    if totals["eligible_cutoff_events"] <= 0:
        raise ValueError("teacher emitted zero eligible cutoff events")

    out = {
        "schema": "jass.d4.search_utility_teacher_aggregate.v1",
        "verdict": "D4_SEARCH_UTILITY_TEACHER_COMPLETE_V1",
        "code_sha": args.code_sha,
        "model_sha256": args.model_sha256,
        "shards": 16,
        **totals,
        "root_splits": splits,
        "exact_nodes_per_root": 50000,
        "threads": 1,
        "book": False,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        **{key: 0 for key in FORBIDDEN},
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
