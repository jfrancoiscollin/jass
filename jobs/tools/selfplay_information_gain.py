#!/usr/bin/env python3
"""Quantify marginal diversity/information across independent Jass self-play corpora.

This is a screening tool, not a strength proxy. It deliberately uses only raw
state/outcome statistics so the decision to scale a multi-seed pool can be made
before any candidate-model strength result is observed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Iterable

REC = struct.Struct("<QQQQBib")
HEADER = struct.Struct("<4sI")


def parse_assignment(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    name, path = value.split("=", 1)
    if not name or not path:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    return name, path


def bitcount(value: int) -> int:
    return int(value).bit_count()


def fingerprint(row: tuple[int, int, int, int, int, int, int]) -> int:
    wm, wk, bm, bk, stm, _score, _wdl = row
    payload = struct.pack("<QQQQB", wm, wk, bm, bk, stm)
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "little")


def state_bin(row: tuple[int, int, int, int, int, int, int]) -> str:
    wm, wk, bm, bk, stm, _score, _wdl = row
    men_w = bitcount(wm)
    kings_w = bitcount(wk)
    men_b = bitcount(bm)
    kings_b = bitcount(bk)
    total = men_w + kings_w + men_b + kings_b
    material_delta = (men_w + 3 * kings_w) - (men_b + 3 * kings_b)
    if material_delta < -4:
        delta_bucket = "lt-4"
    elif material_delta > 4:
        delta_bucket = "gt4"
    else:
        delta_bucket = str(material_delta)
    return f"pc={total}|kw={kings_w}|kb={kings_b}|d={delta_bucket}|stm={stm}"


def entropy(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in counter.values() if n)


def js_divergence(a: Counter[str], b: Counter[str]) -> float:
    """Jensen-Shannon divergence in bits, bounded to [0, 1]."""
    ta = sum(a.values())
    tb = sum(b.values())
    if ta <= 0 or tb <= 0:
        return 0.0
    keys = set(a) | set(b)
    out = 0.0
    for key in keys:
        pa = a.get(key, 0) / ta
        pb = b.get(key, 0) / tb
        m = 0.5 * (pa + pb)
        if pa:
            out += 0.5 * pa * math.log2(pa / m)
        if pb:
            out += 0.5 * pb * math.log2(pb / m)
    return max(0.0, min(1.0, out))


def iter_jnnw(path: Path) -> Iterable[tuple[int, int, int, int, int, int, int]]:
    with path.open("rb") as handle:
        raw = handle.read(HEADER.size)
        if len(raw) != HEADER.size:
            raise ValueError(f"{path}: truncated header")
        magic, count = HEADER.unpack(raw)
        if magic != b"JNNW":
            raise ValueError(f"{path}: expected JNNW magic")
        expected = HEADER.size + count * REC.size
        if path.stat().st_size != expected:
            raise ValueError(f"{path}: size/count mismatch")
        for _ in range(count):
            raw_row = handle.read(REC.size)
            if len(raw_row) != REC.size:
                raise ValueError(f"{path}: truncated record")
            yield REC.unpack(raw_row)


def deterministic_sample(path: Path, limit: int) -> list[tuple[int, int, int, int, int, int, int]]:
    with path.open("rb") as handle:
        raw = handle.read(HEADER.size)
        if len(raw) != HEADER.size:
            raise ValueError(f"{path}: truncated header")
        magic, count = HEADER.unpack(raw)
        if magic != b"JNNW":
            raise ValueError(f"{path}: expected JNNW magic")
        expected = HEADER.size + count * REC.size
        if path.stat().st_size != expected:
            raise ValueError(f"{path}: size/count mismatch")
        if limit <= 0 or count <= limit:
            indices = range(count)
        else:
            indices = [(i * count) // limit for i in range(limit)]
        rows = []
        for index in indices:
            handle.seek(HEADER.size + index * REC.size)
            raw_row = handle.read(REC.size)
            if len(raw_row) != REC.size:
                raise ValueError(f"{path}: truncated record at {index}")
            rows.append(REC.unpack(raw_row))
        return rows


def describe(name: str, path: Path, limit: int) -> dict:
    rows = deterministic_sample(path, limit)
    if not rows:
        raise ValueError(f"{path}: empty corpus")
    fps = {fingerprint(row) for row in rows}
    states = Counter(state_bin(row) for row in rows)
    outcomes = Counter(str(row[-1]) for row in rows)
    return {
        "name": name,
        "path": str(path),
        "sampled_records": len(rows),
        "unique_positions": len(fps),
        "unique_fraction": len(fps) / len(rows),
        "state_entropy_bits": entropy(states),
        "state_histogram": states,
        "outcome_histogram": outcomes,
        "fingerprints": fps,
    }


def public_description(item: dict) -> dict:
    sampled = item["sampled_records"]
    outcomes = item["outcome_histogram"]
    return {
        "path": item["path"],
        "sampled_records": sampled,
        "unique_positions": item["unique_positions"],
        "unique_fraction": item["unique_fraction"],
        "state_entropy_bits": item["state_entropy_bits"],
        "state_bins": len(item["state_histogram"]),
        "wdl_share": {
            key: outcomes.get(key, 0) / sampled for key in ("-1", "0", "1")
        },
    }


def pairwise(items: list[dict]) -> list[dict]:
    out = []
    for i, left in enumerate(items):
        for right in items[i + 1 :]:
            a = left["fingerprints"]
            b = right["fingerprints"]
            union = len(a | b)
            inter = len(a & b)
            out.append({
                "a": left["name"],
                "b": right["name"],
                "exact_position_jaccard": inter / union if union else 0.0,
                "a_covered_by_b": inter / len(a) if a else 0.0,
                "b_covered_by_a": inter / len(b) if b else 0.0,
                "state_js_bits": js_divergence(left["state_histogram"], right["state_histogram"]),
                "outcome_js_bits": js_divergence(left["outcome_histogram"], right["outcome_histogram"]),
            })
    return out


def add_counters(left: Counter[str], right: Counter[str]) -> Counter[str]:
    out = Counter(left)
    out.update(right)
    return out


def greedy_order(items: list[dict], novelty_weight: float) -> list[dict]:
    remaining = {item["name"]: item for item in items}
    first = max(items, key=lambda x: (x["unique_fraction"], x["state_entropy_bits"], x["name"]))
    order = []
    pool_fps: set[int] = set()
    pool_states: Counter[str] = Counter()
    while remaining:
        if not order:
            chosen = first
            novelty = 1.0
            js = 1.0
            score = 1.0
        else:
            ranked = []
            for candidate in remaining.values():
                fps = candidate["fingerprints"]
                novelty = len(fps - pool_fps) / len(fps) if fps else 0.0
                js = js_divergence(candidate["state_histogram"], pool_states)
                score = novelty_weight * novelty + (1.0 - novelty_weight) * js
                ranked.append((score, novelty, js, candidate["name"], candidate))
            score, novelty, js, _name, chosen = max(ranked)
        pool_before = len(pool_fps)
        pool_fps |= chosen["fingerprints"]
        pool_states = add_counters(pool_states, chosen["state_histogram"])
        order.append({
            "rank": len(order) + 1,
            "name": chosen["name"],
            "marginal_exact_novelty": novelty,
            "state_js_vs_pool_bits": js,
            "information_gain_proxy": score,
            "pool_unique_before": pool_before,
            "pool_unique_after": len(pool_fps),
            "pool_unique_added": len(pool_fps) - pool_before,
        })
        remaining.pop(chosen["name"])
    return order


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="append", type=parse_assignment, required=True,
                        help="NAME=PATH; repeat for each independent corpus")
    parser.add_argument("--sample-per-corpus", type=int, default=200000)
    parser.add_argument("--novelty-weight", type=float, default=0.7)
    parser.add_argument("--min-marginal-novelty", type=float, default=0.05)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if not 0.0 <= args.novelty_weight <= 1.0:
        raise SystemExit("--novelty-weight must be in [0,1]")
    if not 0.0 <= args.min_marginal_novelty <= 1.0:
        raise SystemExit("--min-marginal-novelty must be in [0,1]")
    names = [name for name, _ in args.corpus]
    if len(set(names)) != len(names):
        raise SystemExit("duplicate corpus name")
    if len(names) < 2:
        raise SystemExit("at least two corpora are required")

    items = [describe(name, Path(path), args.sample_per_corpus) for name, path in args.corpus]
    pairs = pairwise(items)
    order = greedy_order(items, args.novelty_weight)
    tail = order[-1]
    mean_jaccard = sum(p["exact_position_jaccard"] for p in pairs) / len(pairs)
    mean_state_js = sum(p["state_js_bits"] for p in pairs) / len(pairs)
    report = {
        "schema": "jass.selfplay_information_gain.v1",
        "role": "pre_strength_screen_only",
        "sampling": {
            "sample_per_corpus": args.sample_per_corpus,
            "method": "deterministic_even_spacing",
            "position_fingerprint": "blake2b64(wm,wk,bm,bk,stm)",
        },
        "objective": {
            "proxy": "novelty_weight*marginal_exact_novelty + (1-novelty_weight)*state_js_bits",
            "novelty_weight": args.novelty_weight,
            "min_marginal_novelty": args.min_marginal_novelty,
            "warning": "proxy ranks corpus diversity; it is not Elo and must not be used as a promotion gate",
        },
        "corpora": {item["name"]: public_description(item) for item in items},
        "pairwise": pairs,
        "greedy_pool_order": order,
        "summary": {
            "corpus_count": len(items),
            "mean_pairwise_exact_position_jaccard": mean_jaccard,
            "mean_pairwise_state_js_bits": mean_state_js,
            "final_added_corpus": tail["name"],
            "final_marginal_exact_novelty": tail["marginal_exact_novelty"],
            "diversity_screen_pass": tail["marginal_exact_novelty"] >= args.min_marginal_novelty,
        },
    }
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
