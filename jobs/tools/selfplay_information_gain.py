#!/usr/bin/env python3
"""Quantify marginal diversity/information across independent Jass self-play corpora.

This is a screening tool, not a strength proxy. It deliberately uses only raw
state/outcome statistics so the decision to scale a multi-seed pool can be made
before any candidate-model strength result is observed.

⛔ WHY THE NULL SPLIT IS MANDATORY. Marginal exact novelty is NOT a measure of
"what the seed adds": in a position space large relative to the sample, two draws
from the SAME distribution barely overlap, so novelty stays high even when the
seed adds nothing at all. Measured under a true H0 (ten i.i.d. draws of one
distribution, Zipf-shaped like a real self-play corpus, 200k sampled records
each), the tenth corpus still shows 0.34 / 0.50 / 0.59 marginal novelty for
supports of 1M / 5M / 20M distinct positions — four to twelve times any
"modest" absolute threshold. An absolute cutoff therefore passes in every world
and screens nothing.

The tool consequently REFUSES to emit a pass/fail without a null: `--null-split`
partitions one corpus into disjoint equal-size shards and reruns the identical
screen, which is exactly "same generator, different sample". The gate is then the
EXCESS over that null, never an absolute level. Without a null the report carries
`diversity_screen_pass: null` and a reason — fail-closed, so a missing control
can never read as a passing screen.

⚠️ `state_bin` is deliberately coarse (piece count, kings, material delta, side
to move). Two corpora can share an identical material histogram while covering
disjoint positional regions, so `state_js_bits` is a weak descriptor and carries
the smaller weight in the proxy. It describes; it does not select.
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


def read_count(path: Path) -> int:
    with path.open("rb") as handle:
        raw = handle.read(HEADER.size)
        if len(raw) != HEADER.size:
            raise ValueError(f"{path}: truncated header")
        magic, count = HEADER.unpack(raw)
        if magic != b"JNNW":
            raise ValueError(f"{path}: expected JNNW magic")
        if path.stat().st_size != HEADER.size + count * REC.size:
            raise ValueError(f"{path}: size/count mismatch")
        return count


def index_key(index: int) -> int:
    """Deterministic, order-free rank for a record index.

    ⚠️ Even spacing (`i * count // limit`) is a SYSTEMATIC stride, and records
    are written game by game: a fixed stride can lock onto the ply structure of
    the games and sample the same phase over and over. Hashing the index keeps
    the selection fully deterministic and reproducible while breaking any
    alignment with how the file was laid out, at the same cost.
    """
    return int.from_bytes(hashlib.blake2b(struct.pack("<Q", index), digest_size=8).digest(), "little")


def deterministic_sample(
    path: Path, limit: int, shard: int = 0, shards: int = 1
) -> list[tuple[int, int, int, int, int, int, int]]:
    """Read up to `limit` records of `path`, restricted to one disjoint shard.

    `shards > 1` partitions the corpus by a HASH of the record index. The
    partition is scattered, never contiguous: a contiguous block would be a
    different slice of the generation run — early games against late games — and
    would confound "same generator, different sample" with a drift in time. Two
    shards of one corpus must differ only by sampling.

    ⚠️ And it is hashed rather than `index % shards`, which looks equivalent and
    is not: a plain modulo ALIASES against any periodicity in the file whose
    period shares a factor with `shards`. Caught by a test whose fixture cycled
    twelve positions across two shards — the modulo handed each shard six
    positions the other never saw, manufacturing a perfectly disjoint "null".
    """
    if shards < 1 or not 0 <= shard < shards:
        raise ValueError("invalid shard/shards")
    count = read_count(path)
    member = [i for i in range(count) if index_key(i) % shards == shard]
    if shards > 1 and limit > 0 and len(member) < limit:
        raise ValueError(
            f"{path}: shard {shard}/{shards} holds {len(member)} records, short of {limit}")
    if limit > 0 and len(member) > limit:
        member.sort(key=index_key)
        member = sorted(member[:limit])
    with path.open("rb") as handle:
        rows = []
        for index in member:
            handle.seek(HEADER.size + index * REC.size)
            raw_row = handle.read(REC.size)
            if len(raw_row) != REC.size:
                raise ValueError(f"{path}: truncated record at {index}")
            rows.append(REC.unpack(raw_row))
        return rows


def describe(name: str, path: Path, limit: int, shard: int = 0, shards: int = 1) -> dict:
    rows = deterministic_sample(path, limit, shard, shards)
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
            # ⚠️ Rank 1 has no pool to be novel against. Novelty is 1.0 by
            # definition, but the JS divergence is UNDEFINED, not 1.0 — and
            # `js_divergence(x, empty)` in this very module returns 0.0. Publishing
            # a hard-coded 1.0 would put a fabricated number in a scientific
            # artefact, so the field is left null and the proxy carries novelty
            # alone.
            novelty = 1.0
            js = None
            score = novelty_weight
        else:
            ranked = []
            for candidate in remaining.values():
                fps = candidate["fingerprints"]
                novelty = len(fps - pool_fps) / len(fps) if fps else 0.0
                js = js_divergence(candidate["state_histogram"], pool_states)
                score = novelty_weight * novelty + (1.0 - novelty_weight) * js
                # ⚠️ The candidate dict is deliberately NOT in the sort key: dicts
                # are not orderable, so a full tie would raise TypeError. Names are
                # unique, hence the key always resolves before it — but only while
                # that guard holds, and a sort key must not depend on it.
                ranked.append(((score, novelty, js, candidate["name"]), candidate))
            key, chosen = max(ranked, key=lambda entry: entry[0])
            score, novelty, js, _name = key
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


def null_screen(name: str, path: Path, shards: int, limit: int, novelty_weight: float) -> dict:
    """Run the identical screen on disjoint shards of ONE corpus.

    This is the H0 control: same generator, same settings, same seed lineage —
    only the sample differs. Whatever marginal novelty comes out is what the
    metric reads when independence adds NOTHING, so it is the level the real
    pool has to beat.

    Shards are sized like the real corpora (`limit` records each), because
    marginal novelty is not scale-free: it rises as the sample shrinks against
    the position space. A null built from smaller shards would flatter the pool.
    """
    count = read_count(path)
    if limit > 0 and count < shards * limit:
        raise SystemExit(
            f"--null-split {name}: {count} records cannot yield {shards} disjoint "
            f"shards of {limit}; the null must match the real corpora in size, "
            "so pass a bigger corpus or lower --sample-per-corpus")
    items = [describe(f"{name}#{i}", path, limit, shard=i, shards=shards) for i in range(shards)]
    order = greedy_order(items, novelty_weight)
    pairs = pairwise(items)
    return {
        "source": name,
        "path": str(path),
        "shards": shards,
        "records_per_shard": items[0]["sampled_records"],
        "partition": "blake2b64(record index) modulo shards (scattered, never contiguous)",
        "final_marginal_exact_novelty": order[-1]["marginal_exact_novelty"],
        "mean_pairwise_exact_position_jaccard": sum(
            p["exact_position_jaccard"] for p in pairs) / len(pairs),
        "means_what": "marginal novelty when the seed adds nothing; the floor the pool must clear",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="append", type=parse_assignment, required=True,
                        help="NAME=PATH; repeat for each independent corpus")
    parser.add_argument("--sample-per-corpus", type=int, default=200000)
    parser.add_argument("--novelty-weight", type=float, default=0.7)
    parser.add_argument("--null-split", type=parse_assignment, default=None,
                        help="NAME=PATH of one corpus to split into disjoint shards as the H0 "
                             "control; without it the screen refuses to emit a verdict")
    parser.add_argument("--min-novelty-excess", type=float, default=0.05,
                        help="how far the pool's final marginal novelty must exceed the null")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if not 0.0 <= args.novelty_weight <= 1.0:
        raise SystemExit("--novelty-weight must be in [0,1]")
    if not 0.0 <= args.min_novelty_excess <= 1.0:
        raise SystemExit("--min-novelty-excess must be in [0,1]")
    names = [name for name, _ in args.corpus]
    if len(set(names)) != len(names):
        raise SystemExit("duplicate corpus name")
    if len(names) < 2:
        raise SystemExit("at least two corpora are required")

    items = [describe(name, Path(path), args.sample_per_corpus) for name, path in args.corpus]
    pairs = pairwise(items)
    order = greedy_order(items, args.novelty_weight)
    tail = order[-1]
    observed = tail["marginal_exact_novelty"]
    mean_jaccard = sum(p["exact_position_jaccard"] for p in pairs) / len(pairs)
    mean_state_js = sum(p["state_js_bits"] for p in pairs) / len(pairs)

    # ⛔ FAIL-CLOSED. No null, no verdict. An absolute threshold on novelty
    # passes under H0 as readily as under H1 (see module docstring), so emitting
    # `True` without a control would be a rubber stamp wearing the costume of a
    # screen.
    null = None
    excess = None
    verdict: bool | None = None
    if args.null_split is not None:
        null_name, null_path = args.null_split
        null = null_screen(null_name, Path(null_path), len(items),
                           args.sample_per_corpus, args.novelty_weight)
        excess = observed - null["final_marginal_exact_novelty"]
        verdict = excess >= args.min_novelty_excess
        reason = (f"observed {observed:.4f} vs null {null['final_marginal_exact_novelty']:.4f} "
                  f"= excess {excess:+.4f} against a required {args.min_novelty_excess:.4f}")
    else:
        reason = ("no --null-split control supplied: marginal novelty has no meaning as an "
                  "absolute level, so no pass/fail is emitted")

    report = {
        "schema": "jass.selfplay_information_gain.v2",
        "role": "pre_strength_screen_only",
        "sampling": {
            "sample_per_corpus": args.sample_per_corpus,
            "method": "deterministic_hashed_index",
            "position_fingerprint": "blake2b64(wm,wk,bm,bk,stm)",
        },
        "objective": {
            "proxy": "novelty_weight*marginal_exact_novelty + (1-novelty_weight)*state_js_bits",
            "novelty_weight": args.novelty_weight,
            "min_novelty_excess": args.min_novelty_excess,
            "warning": "proxy ranks corpus diversity; it is not Elo and must not be used as a promotion gate",
            "absolute_novelty_is_not_a_criterion": (
                "under a true H0 the tenth of ten i.i.d. corpora still scores 0.34-0.59 marginal "
                "novelty at 200k sampled records; only the excess over the null split carries signal"),
        },
        "corpora": {item["name"]: public_description(item) for item in items},
        "pairwise": pairs,
        "greedy_pool_order": order,
        "null_screen": null,
        "summary": {
            "corpus_count": len(items),
            "mean_pairwise_exact_position_jaccard": mean_jaccard,
            "mean_pairwise_state_js_bits": mean_state_js,
            "final_added_corpus": tail["name"],
            "final_marginal_exact_novelty": observed,
            "null_final_marginal_exact_novelty": (
                null["final_marginal_exact_novelty"] if null else None),
            "novelty_excess_over_null": excess,
            "diversity_screen_pass": verdict,
            "diversity_screen_reason": reason,
        },
    }
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
