#!/usr/bin/env python3
"""Compare the frozen Scan static eval with its PJTW port inside Jass."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Sequence

try:
    from conv_fixed_wdl import read_records, record_to_fen
except ImportError:  # pragma: no cover
    from jobs.tools.conv_fixed_wdl import read_records, record_to_fen


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_scan_output(stdout: str, expected: int) -> list[int]:
    rows: dict[int, int] = {}
    for line in stdout.splitlines():
        if not line.startswith("EVAL\t"):
            continue
        fields = line.split("\t")
        if len(fields) != 3:
            raise ValueError(f"bad Scan probe row: {line!r}")
        index, score = int(fields[1]), int(fields[2])
        if index in rows:
            raise ValueError(f"duplicate Scan probe index {index}")
        rows[index] = score
    if sorted(rows) != list(range(expected)):
        raise ValueError(
            f"Scan probe returned indices {sorted(rows)[:5]}... "
            f"for expected 0..{expected - 1}"
        )
    return [rows[index] for index in range(expected)]


def compare_scores(
    fens: Sequence[str],
    scan_scores: Sequence[int],
    jass_scores: Sequence[int],
    *,
    max_examples: int = 20,
) -> dict[str, object]:
    if not (len(fens) == len(scan_scores) == len(jass_scores)):
        raise ValueError("FEN and score lengths differ")
    deltas = [jass - scan for scan, jass in zip(scan_scores, jass_scores)]
    mismatches = [i for i, delta in enumerate(deltas) if delta != 0]
    examples = [
        {
            "index": index,
            "fen": fens[index],
            "scan": scan_scores[index],
            "jass": jass_scores[index],
            "delta_jass_minus_scan": deltas[index],
        }
        for index in mismatches[:max_examples]
    ]
    return {
        "positions": len(fens),
        "exact_matches": len(fens) - len(mismatches),
        "mismatches": len(mismatches),
        "exact_match_rate": (
            (len(fens) - len(mismatches)) / len(fens) if fens else 1.0
        ),
        "max_abs_delta": max((abs(delta) for delta in deltas), default=0),
        "mean_abs_delta": (
            sum(abs(delta) for delta in deltas) / len(deltas)
            if deltas
            else 0.0
        ),
        "mismatch_examples": examples,
    }


def run_parity(
    *,
    pools: Sequence[Path],
    limit_per_pool: int,
    scan_probe: Path,
    scan_cwd: Path,
    jass: Path,
    pjtw: Path,
    workers: int,
    max_abs_diff: int,
) -> dict[str, object]:
    fens: list[str] = []
    pool_rows: list[dict[str, object]] = []
    for pool in pools:
        records = read_records(pool)
        selected = records if limit_per_pool <= 0 else records[:limit_per_pool]
        decoded = [record_to_fen(record) for record in selected]
        start = len(fens)
        fens.extend(decoded)
        pool_rows.append(
            {
                "path": str(pool),
                "sha256": sha256_file(pool),
                "records_total": len(records),
                "records_checked": len(decoded),
                "range": [start, len(fens)],
            }
        )
    if not fens:
        raise ValueError("no positions selected")

    scan = subprocess.run(
        [str(scan_probe)],
        input="\n".join(fens) + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=scan_cwd,
        check=True,
    )
    scan_scores = parse_scan_output(scan.stdout, len(fens))

    def eval_jass(fen: str) -> int:
        proc = subprocess.run(
            [str(jass), "--eval-position", str(pjtw), fen],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return int(proc.stdout.strip().splitlines()[-1])

    with ThreadPoolExecutor(max_workers=workers) as executor:
        jass_scores = list(executor.map(eval_jass, fens))

    comparison = compare_scores(fens, scan_scores, jass_scores)
    payload: dict[str, object] = {
        "schema": 1,
        "verdict": (
            "SCAN_STATIC_PORT_EXACT"
            if int(comparison["max_abs_delta"]) <= max_abs_diff
            else "SCAN_STATIC_PORT_MISMATCH"
        ),
        "max_abs_diff_allowed": max_abs_diff,
        "pools": pool_rows,
        "scan_probe": str(scan_probe),
        "scan_cwd": str(scan_cwd),
        "jass": str(jass),
        "pjtw": {
            "path": str(pjtw),
            "sha256": sha256_file(pjtw),
        },
        "comparison": comparison,
    }
    if int(comparison["max_abs_delta"]) > max_abs_diff:
        raise RuntimeError(json.dumps(payload, sort_keys=True))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool-jnnw", action="append", type=Path, required=True)
    parser.add_argument("--limit-per-pool", type=int, default=64)
    parser.add_argument("--scan-probe", type=Path, required=True)
    parser.add_argument("--scan-cwd", type=Path, required=True)
    parser.add_argument("--jass", type=Path, required=True)
    parser.add_argument("--pjtw", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-abs-diff", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        payload = run_parity(
            pools=args.pool_jnnw,
            limit_per_pool=args.limit_per_pool,
            scan_probe=args.scan_probe,
            scan_cwd=args.scan_cwd,
            jass=args.jass,
            pjtw=args.pjtw,
            workers=args.workers,
            max_abs_diff=args.max_abs_diff,
        )
    except RuntimeError as exc:
        try:
            payload = json.loads(str(exc))
        except json.JSONDecodeError:
            raise
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(payload["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
