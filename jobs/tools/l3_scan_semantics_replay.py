#!/usr/bin/env python3
"""Replay the 0958 sentinels through the 0959 Scan-semantics ladder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

try:
    from l3_scan_semantics_variants import VARIANT_ORDER
    from l3_search_tree_replay import DEPTHS, JassTraceEngine, ScanTraceEngine
except ModuleNotFoundError:  # pragma: no cover
    from jobs.tools.l3_scan_semantics_variants import VARIANT_ORDER
    from jobs.tools.l3_search_tree_replay import (
        DEPTHS,
        JassTraceEngine,
        ScanTraceEngine,
    )


ENGINES = (*VARIANT_ORDER, "SCAN_NATIVE")


def load_contracts(
    sentinels_path: Path, variants_path: Path
) -> tuple[list[dict[str, object]], dict[str, str]]:
    sentinels = json.loads(sentinels_path.read_text(encoding="utf-8"))
    if sentinels.get("protocol") != "l3-pure-m1-search-tree-audit-sentinels-v1":
        raise ValueError("unexpected sentinel protocol")
    rows = list(sentinels.get("sentinels", []))
    if len(rows) != 48:
        raise ValueError(f"0959 requires exactly 48 sentinels, found {len(rows)}")

    variants = json.loads(variants_path.read_text(encoding="utf-8"))
    if variants.get("protocol") != "l3-pure-m1-scan-node-semantics-ladder-v1":
        raise ValueError("unexpected variant protocol")
    if tuple(variants.get("variant_order", [])) != VARIANT_ORDER:
        raise ValueError("variant order mismatch")
    specs = {
        name: str(variants["arms"][name]["search_params"])
        for name in VARIANT_ORDER
    }
    if any(len(spec.split(",")) != 65 for spec in specs.values()):
        raise ValueError("0959 ladder is not fully resolved")
    return rows, specs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinels", type=Path, required=True)
    parser.add_argument("--variants", type=Path, required=True)
    parser.add_argument("--jass", required=True)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--scan", required=True)
    parser.add_argument("--depths", default="8,10,12")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--jass-timeout", type=float, default=900.0)
    parser.add_argument("--scan-timeout", type=float, default=900.0)
    parser.add_argument("--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    depths = tuple(int(token) for token in args.depths.split(",") if token)
    if depths != DEPTHS:
        parser.error("0959 depth ladder must be exactly 8,10,12")
    if args.shard < 0 or args.nshards <= 0 or args.shard >= args.nshards:
        parser.error("invalid shard specification")

    tool = Path(args.calibrate_tool).resolve()
    sys.path.insert(0, str(tool.parent))
    import calibrate_vs_scan as cv  # type: ignore

    sentinels, specs = load_contracts(args.sentinels, args.variants)
    engines: dict[str, Any] = {
        name: JassTraceEngine(
            cv, args.jass, args.pattern, spec, f"0959-{name}", args.jass_timeout
        )
        for name, spec in specs.items()
    }
    engines["SCAN_NATIVE"] = ScanTraceEngine(cv, args.scan, args.scan_timeout)

    rows: list[dict[str, object]] = []
    try:
        for ordinal, sentinel in enumerate(sentinels):
            if ordinal % args.nshards != args.shard:
                continue
            fen = str(sentinel["fen"])
            for depth in depths:
                for engine_name, engine in engines.items():
                    row: dict[str, object] = {
                        "sentinel_id": sentinel["sentinel_id"],
                        "stratum": sentinel["stratum"],
                        "source_index": sentinel["source_index"],
                        "advantaged_side": sentinel["advantaged_side"],
                        "family": sentinel["family"],
                        "engine": engine_name,
                        "requested_depth": depth,
                    }
                    try:
                        row["analysis"] = engine.analyse(fen, depth)
                    except Exception as exc:  # aggregate fails closed
                        row["error"] = str(exc)
                    rows.append(row)
    finally:
        for engine in engines.values():
            try:
                engine.close()
            except Exception:
                pass

    output = {
        "schema": 1,
        "protocol": "l3-pure-m1-scan-node-semantics-replay-v1",
        "diagnostic_only": True,
        "depths": list(depths),
        "engines": list(engines),
        "shard": args.shard,
        "nshards": args.nshards,
        "rows": rows,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"SCAN_NODE_SEMANTICS_REPLAY_READY shard={args.shard} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
