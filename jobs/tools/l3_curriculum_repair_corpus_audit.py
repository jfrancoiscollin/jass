#!/usr/bin/env python3
"""Fail-closed audit for the CURRICULUM error-repair corpus.

The generator is allowed to run only after the sealed error-region screen.  This
auditor proves that the resulting 500k-row corpus is entirely seeded, that each
catalogue row starts at most one paired opening, and that every generated
opening can be joined back to the immutable error-decision lineage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


JNNW_MAGIC = b"JNNW"
JNNW_RECORD_BYTES = 38
JSM2_MAGIC = b"JSM2"
JSM2 = struct.Struct("<QQBHHHbB")
SCHEMA_SEEDS = "jass.l3_curriculum_repair_seeds.v1"
SCHEMA_AUDIT = "jass.l3_curriculum_repair_corpus_audit.v1"
TARGET_RECORDS = 500_000


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _counted_file(path: Path, magic: bytes, record_bytes: int) -> int:
    size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(8)
    if len(header) != 8 or header[:4] != magic:
        raise ValueError(f"{path}: invalid {magic.decode()} header")
    count = struct.unpack_from("<I", header, 4)[0]
    expected = 8 + count * record_bytes
    if size != expected:
        raise ValueError(f"{path}: size {size} differs from exact {expected}")
    return count


def _parse_usage(path: Path) -> dict[int, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "JSSU1\topening_id\tseed_index":
        raise ValueError("seed usage sidecar is not JSSU1")
    usage: dict[int, int] = {}
    for line_number, line in enumerate(lines[1:], start=2):
        fields = line.split("\t")
        if len(fields) != 2:
            raise ValueError(f"seed usage line {line_number}: expected two fields")
        opening_id, seed_index = map(int, fields)
        if opening_id <= 0 or seed_index < 0:
            raise ValueError(f"seed usage line {line_number}: invalid seeded mapping")
        if opening_id in usage:
            raise ValueError(f"seed usage opening {opening_id} is duplicated")
        usage[opening_id] = seed_index
    if not usage:
        raise ValueError("seed usage sidecar is empty")
    return usage


def _counter(log: str, name: str) -> int:
    hits = re.findall(rf"(?:^|\s){re.escape(name)}=(-?\d+)(?=\s|$)", log, re.MULTILINE)
    if len(hits) != 1:
        raise ValueError(f"generator log must expose exactly one {name} counter")
    return int(hits[0])


def audit(
    *,
    data: Path,
    meta: Path,
    seed_usage: Path,
    seed_report: dict[str, Any],
    lineage: dict[str, Any],
    generator_log: str,
    champion_sha256: str,
    source_job: str,
    source_attempt: str,
    source_code_sha: str,
) -> dict[str, Any]:
    if seed_report.get("schema") != SCHEMA_SEEDS or lineage.get("schema") != SCHEMA_SEEDS:
        raise ValueError("repair seed schema drift")
    if seed_report.get("verdict") != "JASS_CURRICULUM_REPAIR_SEEDS_READY":
        raise ValueError("repair seed catalogue is not scientifically authorized")
    if seed_report.get("generation_authorized") is not True:
        raise ValueError("repair seed generation authorization is false")
    if seed_report.get("champion_sha256") != champion_sha256:
        raise ValueError("repair seed champion identity drift")
    if hashlib.sha256(_canonical(lineage)).hexdigest() != seed_report.get("lineage_sha256"):
        raise ValueError("repair lineage hash drift")
    lineage_rows = lineage.get("rows", [])
    if len(lineage_rows) != int(seed_report.get("seed_positions", -1)):
        raise ValueError("repair lineage row count drift")
    if [int(row.get("record_index", -1)) for row in lineage_rows] != list(range(len(lineage_rows))):
        raise ValueError("repair lineage record indices are not exact")

    records = _counted_file(data, JNNW_MAGIC, JNNW_RECORD_BYTES)
    meta_records = _counted_file(meta, JSM2_MAGIC, JSM2.size)
    if records != TARGET_RECORDS or meta_records != TARGET_RECORDS:
        raise ValueError("repair corpus is not exactly 500000 aligned rows")

    usage = _parse_usage(seed_usage)
    used_seed_indices = list(usage.values())
    if len(set(used_seed_indices)) != len(used_seed_indices):
        raise ValueError("a repair seed starts more than one opening")
    if min(used_seed_indices) < 0 or max(used_seed_indices) >= len(lineage_rows):
        raise ValueError("seed usage references outside the repair lineage")

    games_by_opening: dict[int, set[int]] = defaultdict(set)
    rows_by_opening: Counter[int] = Counter()
    with meta.open("rb") as stream:
        stream.seek(8)
        for index in range(meta_records):
            raw = stream.read(JSM2.size)
            if len(raw) != JSM2.size:
                raise ValueError(f"metadata truncated at record {index}")
            game_id, opening_id, seeded, ply, game_plies, _last_eps, result, flags = JSM2.unpack(raw)
            if seeded != 1:
                raise ValueError(f"metadata record {index} is not seeded")
            if opening_id not in usage:
                raise ValueError(f"metadata opening {opening_id} has no JSSU1 lineage")
            if ply >= game_plies or result not in (-1, 0, 1) or flags & ~0x07:
                raise ValueError(f"metadata record {index} is malformed")
            games_by_opening[opening_id].add(game_id)
            rows_by_opening[opening_id] += 1
    if any(len(games) > 2 for games in games_by_opening.values()):
        raise ValueError("an exact repair seed generated more than two trajectories")

    counters = {
        name: _counter(generator_log, name)
        for name in (
            "label_score_searches",
            "split_selfplay_rngs",
            "seeded_openings",
            "standard_openings",
            "seed_catalogue_positions",
            "seed_frac",
            "seed_without_replacement",
            "seed_unique_used",
            "seed_reuses",
            "seed_usage_rows",
        )
    }
    expected = {
        "label_score_searches": 0,
        "split_selfplay_rngs": 1,
        "standard_openings": 0,
        "seed_catalogue_positions": len(lineage_rows),
        "seed_frac": 100,
        "seed_without_replacement": 1,
        "seed_reuses": 0,
    }
    for name, value in expected.items():
        if counters[name] != value:
            raise ValueError(f"generator counter {name}={counters[name]} differs from {value}")
    if counters["seeded_openings"] != len(usage):
        raise ValueError("seeded opening counter and JSSU1 differ")
    if counters["seed_unique_used"] != len(usage):
        raise ValueError("unique seed counter and JSSU1 differ")
    if counters["seed_usage_rows"] != len(usage):
        raise ValueError("seed usage row counter and JSSU1 differ")

    wdl = Counter()
    with data.open("rb") as stream:
        stream.seek(8)
        for _ in range(records):
            row = stream.read(JNNW_RECORD_BYTES)
            value = struct.unpack_from("<b", row, 37)[0]
            if value not in (-1, 0, 1):
                raise ValueError("WDL outside {-1,0,1}")
            wdl[value] += 1

    return {
        "schema": SCHEMA_AUDIT,
        "verdict": "JASS_CURRICULUM_REPAIR_CORPUS_READY",
        "source": {
            "job_id": source_job,
            "attempt_id": source_attempt,
            "code_sha": source_code_sha,
            "champion_sha256": champion_sha256,
        },
        "records": records,
        "data_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
        "meta_sha256": hashlib.sha256(meta.read_bytes()).hexdigest(),
        "seed_usage_sha256": hashlib.sha256(seed_usage.read_bytes()).hexdigest(),
        "seed_report_sha256": hashlib.sha256(_canonical(seed_report)).hexdigest(),
        "lineage_sha256": hashlib.sha256(_canonical(lineage)).hexdigest(),
        "catalogue_positions": len(lineage_rows),
        "seed_unique_used": len(usage),
        "seed_reuses": 0,
        "corpus_openings": len(games_by_opening),
        "corpus_games": len({game for games in games_by_opening.values() for game in games}),
        "max_trajectories_per_seed": max(map(len, games_by_opening.values()), default=0),
        "max_rows_per_opening": max(rows_by_opening.values(), default=0),
        "all_rows_seeded": True,
        "wdl": {"loss": wdl[-1], "draw": wdl[0], "win": wdl[1]},
        "generator_counters": counters,
        "new_selfplay_positions": records,
        "fits": 0,
        "strength_games": 0,
        "frozen_reads": 0,
        "promotion_authorized": False,
        "automatic_promotion": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--meta", type=Path, required=True)
    parser.add_argument("--seed-usage", type=Path, required=True)
    parser.add_argument("--seed-report", type=Path, required=True)
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--generator-log", type=Path, required=True)
    parser.add_argument("--champion-sha256", required=True)
    parser.add_argument("--source-job", required=True)
    parser.add_argument("--source-attempt", required=True)
    parser.add_argument("--source-code-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit(
        data=args.data,
        meta=args.meta,
        seed_usage=args.seed_usage,
        seed_report=json.loads(args.seed_report.read_text(encoding="utf-8")),
        lineage=json.loads(args.lineage.read_text(encoding="utf-8")),
        generator_log=args.generator_log.read_text(encoding="utf-8", errors="replace"),
        champion_sha256=args.champion_sha256,
        source_job=args.source_job,
        source_attempt=args.source_attempt,
        source_code_sha=args.source_code_sha,
    )
    args.out.write_bytes(_canonical(report))
    print(json.dumps({"verdict": report["verdict"], "records": report["records"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
