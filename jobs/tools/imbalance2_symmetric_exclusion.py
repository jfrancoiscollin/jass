#!/usr/bin/env python3
"""Symmetrically remove rare engine-error positions from paired imbalance reports.

The input manifest maps arbitrary report-set names (for example G4..G8) to the
candidate-only shard reports produced by ``imbalance2_scan_gate.py run``. Every
set must contain exactly the same pool/index keys before cleaning. The union of
positions carrying an ``error`` field is removed from every set, preserving a
strictly paired comparison.

This is a recovery policy for rare, explicitly allowed engine timeouts. It is
not a licence to hide missing rows, malformed reports, or broad instability:
all such conditions fail closed, and the number/fraction of excluded positions
is capped by command-line guards.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

EXPECTED_POOLS = {"plateau-a.jnnw", "plateau-b.jnnw"}
EXPECTED_STRATA = {f"{n}v{n + 2}" for n in range(1, 19)}


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    if not cleaned:
        raise ValueError(f"empty safe name for report set {value!r}")
    return cleaned


def load_report(path: Path) -> tuple[str, list[dict[str, object]], dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("engine") != "candidate":
        raise ValueError(f"{path}: symmetric cleaning accepts candidate-only reports")
    pool = Path(str(payload.get("pool", ""))).name
    if pool not in EXPECTED_POOLS:
        raise ValueError(f"{path}: unexpected pool {pool!r}")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"{path}: rows must be a list")
    return pool, rows, payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--out-manifest", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--max-excluded-positions", type=int, default=2)
    parser.add_argument("--max-excluded-fraction", type=float, default=0.001)
    parser.add_argument("--expected-per-stratum", type=int, default=64)
    parser.add_argument(
        "--allow-error-substring",
        action="append",
        default=[],
        help="repeatable substring; every excluded error must match at least one",
    )
    args = parser.parse_args()
    if args.max_excluded_positions < 0:
        parser.error("max excluded positions must be non-negative")
    if not 0.0 <= args.max_excluded_fraction <= 1.0:
        parser.error("max excluded fraction must be between zero and one")
    if args.expected_per_stratum <= 0:
        parser.error("expected per stratum must be positive")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if manifest.get("same_search_budget") is not True:
        parser.error("symmetric cleaning requires same_search_budget=true")
    report_sets = manifest.get("report_sets")
    if not isinstance(report_sets, dict) or len(report_sets) < 2:
        parser.error("manifest requires at least two report_sets")

    loaded: dict[str, list[tuple[Path, str, list[dict[str, object]], dict[str, object]]]] = {}
    key_sets: dict[str, set[tuple[str, int]]] = {}
    strata_by_set: dict[str, dict[tuple[str, int], str]] = {}
    error_positions: set[tuple[str, int]] = set()
    error_details: list[dict[str, object]] = []

    for set_name, raw_paths in report_sets.items():
        if not isinstance(raw_paths, list) or not raw_paths:
            parser.error(f"report set {set_name!r} has no paths")
        items = []
        keys: set[tuple[str, int]] = set()
        strata: dict[tuple[str, int], str] = {}
        for raw_path in raw_paths:
            path = Path(str(raw_path))
            pool, rows, payload = load_report(path)
            for row in rows:
                if "index" not in row or "stratum" not in row:
                    raise ValueError(f"{path}: row lacks index or stratum")
                key = (pool, int(row["index"]))
                if key in keys:
                    raise ValueError(f"{path}: duplicate key {key} in set {set_name}")
                keys.add(key)
                stratum = str(row["stratum"])
                if stratum not in EXPECTED_STRATA:
                    raise ValueError(f"{path}: unexpected stratum {stratum!r}")
                strata[key] = stratum
                if "error" in row:
                    error = str(row.get("error", ""))
                    if args.allow_error_substring and not any(
                        token in error for token in args.allow_error_substring
                    ):
                        raise ValueError(
                            f"{path}: error at {key} does not match an allowed substring: {error!r}"
                        )
                    error_positions.add(key)
                    error_details.append(
                        {
                            "report_set": str(set_name),
                            "file": str(path),
                            "pool": pool,
                            "index": key[1],
                            "stratum": stratum,
                            "error": error,
                        }
                    )
            items.append((path, pool, rows, payload))
        loaded[str(set_name)] = items
        key_sets[str(set_name)] = keys
        strata_by_set[str(set_name)] = strata

    first_name = next(iter(key_sets))
    expected_keys = key_sets[first_name]
    if not expected_keys:
        parser.error("no report rows")
    for set_name, keys in key_sets.items():
        if keys != expected_keys:
            missing = sorted(expected_keys - keys)[:10]
            extra = sorted(keys - expected_keys)[:10]
            parser.error(
                f"{set_name}: report keys differ before cleaning; missing={missing} extra={extra}"
            )
        for key in expected_keys:
            if strata_by_set[set_name][key] != strata_by_set[first_name][key]:
                parser.error(f"{set_name}: stratum mismatch at {key}")

    pool_counts = Counter(pool for pool, _ in expected_keys)
    expected_pool_size = 18 * args.expected_per_stratum
    if set(pool_counts) != EXPECTED_POOLS:
        parser.error("both plateau pools A and B are required")
    if any(pool_counts[pool] != expected_pool_size for pool in EXPECTED_POOLS):
        parser.error(
            f"unexpected pre-clean pool counts {dict(pool_counts)}; expected {expected_pool_size} each"
        )
    per_pool_stratum: dict[tuple[str, str], int] = Counter(
        (pool, strata_by_set[first_name][(pool, index)]) for pool, index in expected_keys
    )
    for pool in EXPECTED_POOLS:
        for stratum in EXPECTED_STRATA:
            if per_pool_stratum[(pool, stratum)] != args.expected_per_stratum:
                parser.error(
                    f"{pool} {stratum}: expected {args.expected_per_stratum}, "
                    f"got {per_pool_stratum[(pool, stratum)]}"
                )

    excluded_count = len(error_positions)
    excluded_fraction = excluded_count / len(expected_keys)
    if excluded_count > args.max_excluded_positions:
        parser.error(
            f"{excluded_count} distinct error positions exceeds cap {args.max_excluded_positions}"
        )
    if excluded_fraction > args.max_excluded_fraction:
        parser.error(
            f"excluded fraction {excluded_fraction:.6f} exceeds cap {args.max_excluded_fraction:.6f}"
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cleaned_sets: dict[str, list[str]] = {}
    rows_dropped_by_set: dict[str, int] = defaultdict(int)
    for set_name, items in loaded.items():
        set_dir = out_dir / safe_name(set_name)
        set_dir.mkdir(parents=True, exist_ok=True)
        outputs = []
        used_names: set[str] = set()
        for ordinal, (path, pool, rows, payload) in enumerate(items):
            name = path.name
            if name in used_names:
                name = f"{ordinal:03d}-{name}"
            used_names.add(name)
            cleaned_rows = [
                row for row in rows if (pool, int(row["index"])) not in error_positions
            ]
            rows_dropped_by_set[set_name] += len(rows) - len(cleaned_rows)
            payload = dict(payload)
            payload["rows"] = cleaned_rows
            output = set_dir / name
            output.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            outputs.append(str(output))
        cleaned_sets[set_name] = outputs

    cleaned_keys = expected_keys - error_positions
    clean_pool_counts = Counter(pool for pool, _ in cleaned_keys)
    if len(cleaned_keys) != len(expected_keys) - excluded_count:
        parser.error("internal cleaned-key count mismatch")
    if any(
        rows_dropped_by_set[set_name] != excluded_count for set_name in cleaned_sets
    ):
        parser.error(
            "symmetric exclusion invariant failed: every set must drop each excluded position once"
        )

    cleaned_manifest = {
        "schema": 1,
        "same_pools": True,
        "same_search_budget": True,
        "report_sets": cleaned_sets,
        "symmetric_exclusion_report": str(Path(args.report)),
    }
    Path(args.out_manifest).write_text(
        json.dumps(cleaned_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = {
        "schema": 1,
        "policy": "union_of_allowed_error_positions_removed_from_every_report_set",
        "report_sets": sorted(cleaned_sets),
        "preclean_positions_total": len(expected_keys),
        "preclean_positions_per_pool": dict(sorted(pool_counts.items())),
        "postclean_positions_total": len(cleaned_keys),
        "postclean_positions_per_pool": dict(sorted(clean_pool_counts.items())),
        "excluded_positions": [
            {
                "pool": pool,
                "index": index,
                "stratum": strata_by_set[first_name][(pool, index)],
            }
            for pool, index in sorted(error_positions)
        ],
        "excluded_distinct_positions": excluded_count,
        "excluded_fraction": excluded_fraction,
        "rows_dropped_by_set": dict(sorted(rows_dropped_by_set.items())),
        "allowed_error_substrings": args.allow_error_substring,
        "error_details": error_details,
        "guards": {
            "max_excluded_positions": args.max_excluded_positions,
            "max_excluded_fraction": args.max_excluded_fraction,
            "expected_per_stratum": args.expected_per_stratum,
            "keys_identical_before_cleaning": True,
            "strata_identical_before_cleaning": True,
        },
    }
    Path(args.report).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"excluded_positions={excluded_count} postclean_positions={len(cleaned_keys)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
