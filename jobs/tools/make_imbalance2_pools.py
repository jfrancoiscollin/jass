#!/usr/bin/env python3
"""Create deterministic men-only pools for the L3-IMBALANCE2 lineage.

Every starting position belongs to exactly one material stratum n men versus
n+2 men, for n=1..18.  Training files are emitted one stratum per file so the
runner can allocate an exact record budget to every stratum.  Two independent
benchmark pools are emitted for the Scan-equivalence stop gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import struct
from pathlib import Path

MAGIC = b"JNNW"
REC = struct.Struct("<QQQQBiB")
STRATA = tuple((n, n + 2) for n in range(1, 19))
SAFE_SQUARES = tuple(range(6, 46))  # no uncrowned man on a promotion row


def bits(squares: list[int]) -> int:
    out = 0
    for sq in squares:
        out |= 1 << (sq - 1)
    return out


def fen_of(wm: list[int], bm: list[int], stm: int) -> str:
    side = "B" if stm else "W"
    return f"{side}:W{','.join(map(str, sorted(wm)))}:B{','.join(map(str, sorted(bm)))}"


def make_position(rng: random.Random, low: int, high: int, serial: int) -> tuple[bytes, dict[str, object]]:
    # Balance both the advantaged colour and side to move exactly over a pool.
    advantaged = "W" if serial % 2 == 0 else "B"
    stm = (serial // 2) % 2
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


def build_pool(per_stratum: int, seed: int) -> tuple[list[bytes], list[dict[str, object]]]:
    records: list[bytes] = []
    metadata: list[dict[str, object]] = []
    for low, high in STRATA:
        rng = random.Random((seed << 8) ^ (low * 0x9E3779B1))
        for serial in range(per_stratum):
            rec, meta = make_position(rng, low, high, serial)
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
    p.add_argument("--train-per-stratum", type=int, default=4096)
    p.add_argument("--bench-per-stratum", type=int, default=24)
    p.add_argument("--seed", type=int, default=271828)
    args = p.parse_args()
    if args.train_per_stratum <= 0 or args.bench_per_stratum <= 0:
        p.error("pool sizes must be positive")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "schema": 1,
        "lineage": "L3-IMBALANCE2",
        "seed": args.seed,
        "strata": [f"{a}v{b}" for a, b in STRATA],
        "training_semantics": "games_start_in_stratum; complete played trajectories are retained",
        "files": {},
    }

    for low, high in STRATA:
        records, meta = build_pool(args.train_per_stratum, args.seed + low * 1009)
        # build_pool contains all strata; select the requested one for a shard file.
        chosen = [(r, m) for r, m in zip(records, meta, strict=True) if m["stratum"] == f"{low}v{high}"]
        recs = [r for r, _ in chosen]
        metas = [dict(m, index=i) for i, (_, m) in enumerate(chosen)]
        validate(recs, metas)
        name = f"train-{low:02d}v{high:02d}.jnnw"
        sha = write_jnnw(out / name, recs)
        (out / f"{name}.json").write_text(json.dumps(metas, indent=2) + "\n", encoding="utf-8")
        manifest["files"][name] = {"records": len(recs), "sha256": sha, "stratum": f"{low}v{high}"}

    for label, seed_offset in (("a", 104729), ("b", 130363)):
        recs, metas = build_pool(args.bench_per_stratum, args.seed + seed_offset)
        validate(recs, metas)
        name = f"benchmark-{label}.jnnw"
        sha = write_jnnw(out / name, recs)
        meta_name = f"benchmark-{label}.json"
        (out / meta_name).write_text(json.dumps(metas, indent=2) + "\n", encoding="utf-8")
        manifest["files"][name] = {
            "records": len(recs), "sha256": sha,
            "metadata": meta_name, "independent_pool": label.upper(),
        }

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
