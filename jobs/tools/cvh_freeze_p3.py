#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Freeze a deterministic certified leader-winning P3 JNNW subset.

P3 means material-value margin exactly one (man=1, king=3), 8..19 pieces,
and the terminal/deep WDL winner is the material leader.  This guarantees the
conversion candidate is assigned to the same leader the CVH auxiliary target
models.  Duplicate positions are removed before sampling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import struct
import sys
from pathlib import Path

REC = 38


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jnnw(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError(f"{path}: invalid JNNW magic")
    count = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != count * REC:
        raise ValueError(f"{path}: size mismatch for {count} records")
    return [body[i * REC:(i + 1) * REC] for i in range(count)]


def is_certified_leader_winning_p3(record: bytes) -> bool:
    if len(record) != REC:
        raise ValueError("bad record size")
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    planes = (wm, wk, bm, bk)
    if any(value >> 50 for value in planes):
        raise ValueError("bit outside playable board")
    if any(planes[i] & planes[j] for i in range(4) for j in range(i + 1, 4)):
        raise ValueError("overlapping piece planes")
    stm = record[32]
    wdl = struct.unpack_from("<b", record, 37)[0]
    if stm not in (0, 1):
        raise ValueError(f"invalid stm {stm}")
    if wdl not in (-1, 0, 1):
        raise ValueError(f"invalid wdl {wdl}")

    nwm, nwk, nbm, nbk = (value.bit_count() for value in planes)
    pieces = nwm + nwk + nbm + nbk
    white_value = nwm + 3 * nwk
    black_value = nbm + 3 * nbk
    if abs(black_value - white_value) != 1 or not (8 <= pieces < 20) or wdl == 0:
        return False

    leader = 1 if black_value > white_value else 0  # 0=White, 1=Black
    winner = stm if wdl > 0 else 1 - stm
    return winner == leader


def freeze(source: Path, out: Path, n: int, seed: int) -> dict[str, object]:
    if n <= 0:
        raise ValueError("n must be positive")
    records = read_jnnw(source)
    eligible: list[bytes] = []
    seen: set[bytes] = set()
    for record in records:
        if not is_certified_leader_winning_p3(record):
            continue
        # Board planes + side to move define the position. Score/WDL are labels,
        # not part of the position identity.
        key = record[:33]
        if key in seen:
            continue
        seen.add(key)
        eligible.append(record)
    if len(eligible) < n:
        raise ValueError(
            f"need {n} certified leader-winning P3 records, found {len(eligible)}"
        )
    random.Random(seed).shuffle(eligible)
    selected = eligible[:n]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"JNNW" + struct.pack("<I", n) + b"".join(selected))
    return {
        "schema": 1,
        "source": str(source),
        "source_sha256": sha256(source),
        "source_records": len(records),
        "eligible_unique": len(eligible),
        "selected": n,
        "seed": seed,
        "output": str(out),
        "output_sha256": sha256(out),
        "contract": {
            "material_value": "man=1,king=3",
            "margin": 1,
            "piece_range": [8, 19],
            "decisive": True,
            "winner_is_material_leader": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--n", required=True, type=int)
    parser.add_argument("--seed", type=int, default=141421)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = freeze(args.source, args.out, args.n, args.seed)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
