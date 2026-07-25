#!/usr/bin/env python3
"""Select deterministic 0958 sentinels from the corrected 0957 gauge."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from conv_fixed_wdl import read_records, record_to_fen, winning_side
except ImportError:  # pragma: no cover
    from jobs.tools.conv_fixed_wdl import read_records, record_to_fen, winning_side


VALID_RESULTS = {"win", "draw", "loss"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def result_map(document: dict[str, Any], pool_sha256: str) -> dict[int, str]:
    if document.get("pool_sha256") != pool_sha256:
        raise ValueError("conversion report pool SHA mismatch")
    if int(document.get("n_errors", -1)) != 0:
        raise ValueError("conversion report contains engine errors")
    rows = document.get("position_results")
    if not isinstance(rows, list):
        raise ValueError("conversion report lacks position_results")
    result: dict[int, str] = {}
    for row in rows:
        index = int(row["index"])
        outcome = str(row["result"])
        if outcome not in VALID_RESULTS:
            raise ValueError(f"invalid conversion outcome {outcome!r}")
        if index in result:
            raise ValueError(f"duplicate source index {index}")
        result[index] = outcome
    return result


def stable_rank(seed: int, stratum: str, side: str, family: str, index: int) -> str:
    return hashlib.sha256(
        f"{seed}:{stratum}:{side}:{family}:{index}".encode()
    ).hexdigest()


def select_stratum(
    *,
    stratum: str,
    records: list[bytes],
    exact: dict[int, str],
    native: dict[int, str],
    failures_per_side: int,
    controls_per_side: int,
    seed: int,
) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for index, record in enumerate(records):
        side = winning_side(record)
        if side not in {"W", "B"}:
            continue
        exact_outcome = exact.get(index)
        native_outcome = native.get(index)
        if native_outcome != "win":
            continue
        family = "jass_failure" if exact_outcome != "win" else "shared_win_control"
        groups.setdefault((side, family), []).append(
            {
                "sentinel_id": f"{stratum}-{side}-{family}-{index:03d}",
                "stratum": stratum,
                "source_index": index,
                "advantaged_side": side,
                "family": family,
                "jass_exact_d12_result": exact_outcome,
                "scan_native_d12_result": native_outcome,
                "fen": record_to_fen(record),
            }
        )

    selected: list[dict[str, object]] = []
    for side in ("W", "B"):
        for family, count in (
            ("jass_failure", failures_per_side),
            ("shared_win_control", controls_per_side),
        ):
            candidates = groups.get((side, family), [])
            candidates.sort(
                key=lambda row: stable_rank(
                    seed, stratum, side, family, int(row["source_index"])
                )
            )
            if len(candidates) < count:
                raise ValueError(
                    f"{stratum}/{side}/{family}: {len(candidates)} candidates, "
                    f"need {count}"
                )
            selected.extend(candidates[:count])
    selected.sort(key=lambda row: str(row["sentinel_id"]))
    return selected


def build_selection(
    *,
    strata: list[str],
    pools: list[Path],
    exact_reports: list[Path],
    native_reports: list[Path],
    failures_per_side: int,
    controls_per_side: int,
    seed: int,
) -> dict[str, object]:
    if not (
        len(strata)
        == len(pools)
        == len(exact_reports)
        == len(native_reports)
    ):
        raise ValueError("strata/input cardinalities differ")
    sentinels: list[dict[str, object]] = []
    sources: dict[str, object] = {}
    for stratum, pool, exact_path, native_path in zip(
        strata, pools, exact_reports, native_reports
    ):
        records = read_records(pool)
        pool_sha = sha256_file(pool)
        exact_raw = exact_path.read_bytes()
        native_raw = native_path.read_bytes()
        exact = result_map(json.loads(exact_raw), pool_sha)
        native = result_map(json.loads(native_raw), pool_sha)
        if set(exact) != set(range(len(records))) or set(native) != set(
            range(len(records))
        ):
            raise ValueError(f"{stratum}: incomplete source-index coverage")
        chosen = select_stratum(
            stratum=stratum,
            records=records,
            exact=exact,
            native=native,
            failures_per_side=failures_per_side,
            controls_per_side=controls_per_side,
            seed=seed,
        )
        sentinels.extend(chosen)
        sources[stratum] = {
            "pool_sha256": pool_sha,
            "records": len(records),
            "exact_report_sha256": hashlib.sha256(exact_raw).hexdigest(),
            "native_report_sha256": hashlib.sha256(native_raw).hexdigest(),
            "selected": len(chosen),
        }

    expected = len(strata) * 2 * (failures_per_side + controls_per_side)
    if len(sentinels) != expected:
        raise ValueError(f"selected {len(sentinels)} sentinels, expected {expected}")
    return {
        "schema": 1,
        "protocol": "l3-pure-m1-search-tree-audit-sentinels-v1",
        "selection_seed": seed,
        "failures_per_side_per_stratum": failures_per_side,
        "controls_per_side_per_stratum": controls_per_side,
        "sentinel_count": len(sentinels),
        "sources": sources,
        "sentinels": sentinels,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strata", nargs="+", required=True)
    parser.add_argument("--pool-jnnw", action="append", type=Path, required=True)
    parser.add_argument("--jass-exact-d12", action="append", type=Path, required=True)
    parser.add_argument("--scan-native-d12", action="append", type=Path, required=True)
    parser.add_argument("--failures-per-side", type=int, default=8)
    parser.add_argument("--controls-per-side", type=int, default=4)
    parser.add_argument("--seed", type=int, default=958_001)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = build_selection(
        strata=args.strata,
        pools=args.pool_jnnw,
        exact_reports=args.jass_exact_d12,
        native_reports=args.scan_native_d12,
        failures_per_side=args.failures_per_side,
        controls_per_side=args.controls_per_side,
        seed=args.seed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"SEARCH_TREE_SENTINELS_READY n={payload['sentinel_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
