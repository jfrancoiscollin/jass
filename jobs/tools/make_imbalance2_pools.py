#!/usr/bin/env python3
"""Create deterministic men-only start and benchmark pools for L3-IMBALANCE2."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import struct
from pathlib import Path

MAGIC = b"JNNW"
REC = struct.Struct("<QQQQBiB")
STRATA = tuple((n, n + 2) for n in range(1, 19))
SAFE_SQUARES = tuple(range(6, 46))


def bits(squares: list[int]) -> int:
    out = 0
    for sq in squares:
        out |= 1 << (sq - 1)
    return out


def fen_of(wm: list[int], bm: list[int], stm: int) -> str:
    side = "B" if stm else "W"
    return f"{side}:W{','.join(map(str, sorted(wm)))}:B{','.join(map(str, sorted(bm)))}"


def make_position(
    rng: random.Random,
    low: int,
    high: int,
    serial: int,
    advantaged: str | None = None,
) -> tuple[bytes, dict[str, object]]:
    advantaged = advantaged or ("W" if serial % 2 == 0 else "B")
    if advantaged not in ("W", "B"):
        raise ValueError("advantaged must be W or B")
    stm = serial % 2 if advantaged else (serial // 2) % 2
    squares = list(SAFE_SQUARES)
    rng.shuffle(squares)
    white_n = high if advantaged == "W" else low
    black_n = high if advantaged == "B" else low
    wm = squares[:white_n]
    bm = squares[white_n:white_n + black_n]
    rec = REC.pack(bits(wm), 0, bits(bm), 0, stm, 0, 0)
    meta = {
        "stratum": f"{low}v{high}",
        "low": low,
        "high": high,
        "white_men": white_n,
        "black_men": black_n,
        "advantaged_side": advantaged,
        "stm": "B" if stm else "W",
        "fen": fen_of(wm, bm, stm),
    }
    return rec, meta


def write_jnnw(path: Path, records: list[bytes]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = MAGIC + struct.pack("<I", len(records)) + b"".join(records)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def build_benchmark(per_stratum: int, seed: int) -> tuple[list[bytes], list[dict[str, object]]]:
    records: list[bytes] = []
    metadata: list[dict[str, object]] = []
    for low, high in STRATA:
        rng = random.Random((seed << 8) ^ (low * 0x9E3779B1))
        for serial in range(per_stratum):
            # Four-cycle balances advantaged colour and side to move.
            advantaged = "W" if serial % 2 == 0 else "B"
            rec, meta = make_position(rng, low, high, serial // 2, advantaged)
            meta["index"] = len(records)
            records.append(rec)
            metadata.append(meta)
    return records, metadata


def build_training_side(
    low: int, high: int, count: int, seed: int, advantaged: str
) -> tuple[list[bytes], list[dict[str, object]]]:
    rng = random.Random((seed << 8) ^ (low * 0x9E3779B1) ^ (0 if advantaged == "W" else 0xA5A5A5A5))
    records: list[bytes] = []
    metadata: list[dict[str, object]] = []
    seen: set[bytes] = set()
    serial = 0
    while len(records) < count:
        rec, meta = make_position(rng, low, high, serial, advantaged)
        serial += 1
        if rec[:33] in seen:
            continue
        seen.add(rec[:33])
        meta["index"] = len(records)
        records.append(rec)
        metadata.append(meta)
    return records, metadata


def validate(records: list[bytes], metadata: list[dict[str, object]]) -> None:
    if len(records) != len(metadata):
        raise ValueError("record/metadata length mismatch")
    for index, (rec, meta) in enumerate(zip(records, metadata, strict=True)):
        wm, wk, bm, bk, stm, score, wdl = REC.unpack(rec)
        if wk or bk or score or wdl:
            raise ValueError(f"record {index}: non-men or non-zero label")
        wc, bc = wm.bit_count(), bm.bit_count()
        if abs(wc - bc) != 2 or min(wc, bc) not in range(1, 19):
            raise ValueError(f"record {index}: bad material {wc}v{bc}")
        if wm & bm or stm not in (0, 1):
            raise ValueError(f"record {index}: overlap or bad stm")
        if meta["stratum"] != f"{min(wc, bc)}v{max(wc, bc)}":
            raise ValueError(f"record {index}: metadata mismatch")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--train-per-side", type=int, default=2048)
    p.add_argument("--bench-per-stratum", type=int, default=24)
    p.add_argument("--plateau-per-stratum", type=int, default=8)
    p.add_argument("--seed", type=int, default=271828)
    p.add_argument(
        "--plateau-seed",
        type=int,
        default=None,
        help=(
            "independent seed for plateau A/B pools; defaults to "
            "IMBALANCE2_PLATEAU_SEED or --seed"
        ),
    )
    args = p.parse_args()
    if args.train_per_side <= 0 or args.bench_per_stratum <= 0 or args.plateau_per_stratum <= 0:
        p.error("pool sizes must be positive")

    plateau_seed = args.plateau_seed
    if plateau_seed is None:
        plateau_seed = int(os.environ.get("IMBALANCE2_PLATEAU_SEED", args.seed))

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "schema": 2,
        "lineage": "L3-IMBALANCE2",
        "seed": args.seed,
        "training_seed": args.seed,
        "plateau_seed": plateau_seed,
        "plateau_per_stratum": args.plateau_per_stratum,
        "plateau_records_per_pool": len(STRATA) * args.plateau_per_stratum,
        "strata": [f"{a}v{b}" for a, b in STRATA],
        "training_semantics": "rollout seeds are split by initial advantaged colour",
        "files": {},
    }

    for low, high in STRATA:
        for advantaged in ("W", "B"):
            recs, metas = build_training_side(
                low, high, args.train_per_side, args.seed + low * 1009, advantaged
            )
            validate(recs, metas)
            name = f"train-{low:02d}v{high:02d}-up{advantaged}.jnnw"
            sha = write_jnnw(out / name, recs)
            (out / f"{name}.json").write_text(json.dumps(metas, indent=2) + "\n", encoding="utf-8")
            manifest["files"][name] = {
                "records": len(recs),
                "sha256": sha,
                "stratum": f"{low}v{high}",
                "advantaged_side": advantaged,
            }

    for label, seed_offset in (("a", 15485863), ("b", 179424673)):
        recs, metas = build_benchmark(args.plateau_per_stratum, plateau_seed + seed_offset)
        validate(recs, metas)
        name = f"plateau-{label}.jnnw"
        sha = write_jnnw(out / name, recs)
        meta_name = f"plateau-{label}.json"
        (out / meta_name).write_text(json.dumps(metas, indent=2) + "\n", encoding="utf-8")
        manifest["files"][name] = {
            "records": len(recs),
            "sha256": sha,
            "metadata": meta_name,
            "independent_plateau_pool": label.upper(),
            "plateau_seed": plateau_seed,
            "external_reference_forbidden": True,
        }

    for label, seed_offset in (("a", 104729), ("b", 130363)):
        recs, metas = build_benchmark(args.bench_per_stratum, args.seed + seed_offset)
        validate(recs, metas)
        name = f"benchmark-{label}.jnnw"
        sha = write_jnnw(out / name, recs)
        meta_name = f"benchmark-{label}.json"
        (out / meta_name).write_text(json.dumps(metas, indent=2) + "\n", encoding="utf-8")
        manifest["files"][name] = {
            "records": len(recs),
            "sha256": sha,
            "metadata": meta_name,
            "independent_pool": label.upper(),
        }

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
