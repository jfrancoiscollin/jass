#!/usr/bin/env python3
"""Reproduce one 0961 conversion record with frozen parameter manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import conv_fixed_wdl
except ModuleNotFoundError:  # pragma: no cover
    from jobs.tools import conv_fixed_wdl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jass", required=True)
    parser.add_argument("--defender-jass", required=True)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--defender-pattern", required=True)
    parser.add_argument("--scan", required=True)
    parser.add_argument(
        "--native",
        action="store_true",
        help="run repaired Jass without the Scan root-order oracle",
    )
    parser.add_argument("--pool", required=True)
    parser.add_argument("--variant-manifest", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--index", type=int)
    selection.add_argument("--shard", type=int)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--max-plies", type=int, default=260)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    variants = json.loads(
        args.variant_manifest.read_text(encoding="utf-8")
    )
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    if args.index is not None:
        shard = args.index
        nshards = 300
    else:
        shard = args.shard
        nshards = args.nshards
    conv_args = [
            "--jass",
            args.jass,
            "--defender-jass",
            args.defender_jass,
            "--pattern",
            args.pattern,
            "--defender-pattern",
            args.defender_pattern,
            "--search-params",
            variants["arms"]["SCAN_VERIFY_THREAT"]["search_params"],
            "--defender-search-params",
            baseline["defender_search_params"],
            "--pool-jnnw",
            args.pool,
            "--depth",
            str(args.depth),
            "--defender-depth",
            str(args.depth),
            "--max-plies",
            str(args.max_plies),
            "--shard",
            str(shard),
            "--nshards",
            str(nshards),
            "--out",
            args.out,
        ]
    if not args.native:
        conv_args.extend(["--root-order-scan", args.scan])
    return conv_fixed_wdl.main(conv_args)


if __name__ == "__main__":
    raise SystemExit(main())
