#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a faithful first-pass RGSC restart archive from fresh Jass trajectories.

This tool consumes one fresh JNNW corpus plus its aligned JSM2 sidecar.  It never
uses a deep teacher, Scan, tablebase labels or future strength results.  For each
sampled state of a resolved game it maps the search score to a white-POV value
and computes the Regret-Guided Search Control trajectory target

    R(s_t) = mean_{i>=t} (V_i - z)^2

on the *emitted JNNW trajectory samples*.  One maximum-regret state is retained
per game before global ranking, mirroring RGSC's one restart candidate per game.

The first causal experiment intentionally uses an oracle regret archive rather
than training a regret network.  It publishes:

* a top-regret buffer (one state/game, then top K globally),
* a random-history buffer (one deterministic random state/game, then K games),
* three precomposed JNNW seed tables for NORMAL, ARCHIVE_RANDOM and
  ARCHIVE_REGRET generation.

The two restart arms share byte-identical normal entries.  The regret half is
sampled proportionally to R^(1/tau), using the paper default tau=0.1; the random
half samples uniformly from its buffer.  Scores and WDL bytes are zeroed in all
restart/seed outputs so no old target can leak into the new games.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

JNNW_MAGIC = b"JNNW"
JSM2_MAGIC = b"JSM2"
JNNW = struct.Struct("<QQQQBib")
JSM2 = struct.Struct("<QQBHHHbB")
PLYCAP = 0x01
ADJUDICATED = 0x02
TB_RELABELED = 0x04
DEFAULT_BUFFER_SIZE = 1600       # 100 states x 16 workers, RGSC paper default scale.
DEFAULT_TABLE_SIZE = 16000
DEFAULT_VALUE_SCALE = 200.0      # existing Jass deep-value mapping.
DEFAULT_TEMPERATURE = 0.1        # RGSC paper default.
DEFAULT_RESTART_FRACTION = 0.5   # RGSC paper default.
DEFAULT_RANDOM_SEED = 2026082401


@dataclass(frozen=True)
class Row:
    index: int
    game_id: int
    opening_id: int
    seeded: int
    ply: int
    game_plies: int
    game_result: int
    flags: int
    wm: int
    wk: int
    bm: int
    bk: int
    stm: int
    score: int
    wdl: int

    @property
    def pieces(self) -> int:
        return (self.wm | self.wk | self.bm | self.bk).bit_count()

    @property
    def fingerprint(self) -> str:
        raw = struct.pack("<QQQQB", self.wm, self.wk, self.bm, self.bk, self.stm)
        return hashlib.blake2b(raw, digest_size=16).hexdigest()

    def seed_record(self) -> bytes:
        return JNNW.pack(self.wm, self.wk, self.bm, self.bk, self.stm, 0, 0)


@dataclass(frozen=True)
class Candidate:
    row: Row
    regret: float


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"refusing to clobber {path}")
    tmp = path.with_name(f".{path.name}.tmp")
    if tmp.exists():
        tmp.unlink()
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _read_header(path: Path, magic: bytes, rec_size: int) -> int:
    size = path.stat().st_size
    with path.open("rb") as f:
        head = f.read(8)
    if len(head) != 8 or head[:4] != magic:
        raise ValueError(f"{path}: expected {magic!r} counted file")
    n = struct.unpack_from("<I", head, 4)[0]
    expected = 8 + n * rec_size
    if size != expected:
        raise ValueError(f"{path}: size/count mismatch {size} != {expected}")
    return n


def read_rows(data: Path, meta: Path) -> list[Row]:
    n = _read_header(data, JNNW_MAGIC, JNNW.size)
    nm = _read_header(meta, JSM2_MAGIC, JSM2.size)
    if n != nm:
        raise ValueError(f"data/meta count mismatch: {n} != {nm}")
    rows: list[Row] = []
    with data.open("rb") as fd, meta.open("rb") as fm:
        fd.seek(8); fm.seek(8)
        for i in range(n):
            dr = fd.read(JNNW.size); mr = fm.read(JSM2.size)
            if len(dr) != JNNW.size or len(mr) != JSM2.size:
                raise ValueError(f"truncated aligned pair at row {i}")
            wm, wk, bm, bk, stm, score, wdl = JNNW.unpack(dr)
            game_id, opening_id, seeded, ply, game_plies, _last_eps, game_result, flags = JSM2.unpack(mr)
            if stm not in (0, 1) or seeded not in (0, 1):
                raise ValueError(f"row {i}: invalid stm/seeded")
            if wdl not in (-1, 0, 1) or game_result not in (-1, 0, 1):
                raise ValueError(f"row {i}: invalid WDL/result")
            if flags & ~0x07:
                raise ValueError(f"row {i}: reserved JSM2 flag bits set")
            if ply >= game_plies:
                raise ValueError(f"row {i}: ply {ply} >= game_plies {game_plies}")
            rows.append(Row(i, game_id, opening_id, seeded, ply, game_plies,
                            game_result, flags, wm, wk, bm, bk, stm, score, wdl))
    return rows


def value_white(row: Row, value_scale: float) -> float:
    """Map Jass STM-POV search score to white-POV value in [-1,1]."""
    score_white = float(row.score if row.stm == 0 else -row.score)
    return math.tanh(score_white / (2.0 * value_scale))


def phase_name(pieces: int) -> str:
    if pieces >= 30: return "opening"
    if pieces >= 22: return "midgame"
    if pieces >= 15: return "late-mid"
    if pieces >= 8: return "endgame"
    return "deep-eg"


def deterministic_key(seed: int, *parts: object) -> bytes:
    payload = "|".join([str(seed), *(str(part) for part in parts)]).encode()
    return hashlib.blake2b(payload, digest_size=16).digest()


def game_candidates(rows: list[Row], value_scale: float, random_seed: int) -> tuple[list[Candidate], list[Row], list[Row], dict]:
    games: dict[int, list[Row]] = defaultdict(list)
    for row in rows:
        games[row.game_id].append(row)

    maxima: list[Candidate] = []
    random_states: list[Row] = []
    normal_states: list[Row] = []
    excluded = Counter()
    sampled_lengths: list[int] = []

    for game_id in sorted(games):
        g = sorted(games[game_id], key=lambda r: (r.ply, r.index))
        result = {r.game_result for r in g}
        openings = {r.opening_id for r in g}
        game_plies = {r.game_plies for r in g}
        terminal_flags = {r.flags & (PLYCAP | ADJUDICATED) for r in g}
        if len(result) != 1 or len(openings) != 1 or len(game_plies) != 1 or len(terminal_flags) != 1:
            raise ValueError(f"game {game_id}: inconsistent JSM2 game fields")
        terminal = next(iter(terminal_flags))
        if terminal & PLYCAP:
            excluded["plycap_games"] += 1
            continue
        if terminal & ADJUDICATED:
            excluded["adjudicated_games"] += 1
            continue
        # A full-TB game result is allowed, but old per-row tb relabels do not
        # change game_result and do not enter the regret formula.
        z = float(next(iter(result)))
        if not g:
            excluded["empty_games"] += 1
            continue
        initial = [r for r in g if r.ply == 0]
        if len(initial) != 1:
            excluded["missing_or_duplicate_ply0"] += 1
            continue
        normal_states.append(initial[0])
        sampled_lengths.append(len(g))

        errors = [(value_white(r, value_scale) - z) ** 2 for r in g]
        suffix = [0.0] * len(g)
        total = 0.0
        for pos in range(len(g) - 1, -1, -1):
            total += errors[pos]
            suffix[pos] = total / float(len(g) - pos)
        # One candidate per game. Earliest ply wins an exact tie.
        best_pos = max(range(len(g)), key=lambda pos: (suffix[pos], -g[pos].ply, -g[pos].index))
        maxima.append(Candidate(g[best_pos], suffix[best_pos]))
        random_row = min(g, key=lambda r: deterministic_key(random_seed, "row", game_id, r.ply, r.fingerprint))
        random_states.append(random_row)

    diagnostics = {
        "source_games": len(games),
        "eligible_games": len(maxima),
        "excluded": dict(excluded),
        "sampled_rows_per_eligible_game": {
            "min": min(sampled_lengths) if sampled_lengths else 0,
            "max": max(sampled_lengths) if sampled_lengths else 0,
            "mean": (sum(sampled_lengths) / len(sampled_lengths)) if sampled_lengths else 0.0,
        },
    }
    return maxima, random_states, normal_states, diagnostics


def dedupe_candidates(candidates: Iterable[Candidate]) -> list[Candidate]:
    by_fp: dict[str, Candidate] = {}
    for c in candidates:
        old = by_fp.get(c.row.fingerprint)
        if old is None or (c.regret, -c.row.ply, -c.row.index) > (old.regret, -old.row.ply, -old.row.index):
            by_fp[c.row.fingerprint] = c
    return list(by_fp.values())


def dedupe_rows(rows: Iterable[Row]) -> list[Row]:
    by_fp: dict[str, Row] = {}
    for row in rows:
        old = by_fp.get(row.fingerprint)
        if old is None or (row.game_id, row.ply, row.index) < (old.game_id, old.ply, old.index):
            by_fp[row.fingerprint] = row
    return list(by_fp.values())


def quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {k: None for k in ("p00", "p10", "p25", "p50", "p75", "p90", "p100")}
    x = sorted(values)
    def q(p: float) -> float:
        if len(x) == 1: return x[0]
        at = p * (len(x) - 1)
        lo = int(math.floor(at)); hi = int(math.ceil(at)); frac = at - lo
        return x[lo] * (1.0 - frac) + x[hi] * frac
    return {"p00": q(0), "p10": q(.10), "p25": q(.25), "p50": q(.50),
            "p75": q(.75), "p90": q(.90), "p100": q(1)}


def describe_rows(rows: list[Row]) -> dict:
    return {
        "rows": len(rows),
        "unique_states": len({r.fingerprint for r in rows}),
        "phase": dict(Counter(phase_name(r.pieces) for r in rows)),
        "ply_bucket": dict(Counter(f"{(r.ply // 20) * 20:03d}-{(r.ply // 20) * 20 + 19:03d}" for r in rows)),
        "pieces": {"min": min((r.pieces for r in rows), default=None),
                   "max": max((r.pieces for r in rows), default=None)},
    }


def write_jnnw(path: Path, rows: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"refusing to clobber {path}")
    with path.open("xb") as f:
        f.write(JNNW_MAGIC + struct.pack("<I", len(rows)))
        for row in rows:
            f.write(row.seed_record())


def weighted_choices(rng: random.Random, items: list[Candidate], count: int, temperature: float) -> list[Row]:
    if not items:
        raise ValueError("cannot sample an empty regret buffer")
    positive = [max(c.regret, 1e-15) for c in items]
    logs = [math.log(v) / temperature for v in positive]
    top = max(logs)
    weights = [math.exp(v - top) for v in logs]
    if not math.isfinite(sum(weights)) or sum(weights) <= 0:
        raise ValueError("invalid regret sampling weights")
    return rng.choices([c.row for c in items], weights=weights, k=count)


def build_seed_tables(normal_pool: list[Row], random_buffer: list[Row], regret_buffer: list[Candidate],
                      table_size: int, restart_fraction: float, temperature: float,
                      random_seed: int) -> tuple[list[Row], list[Row], list[Row], int]:
    if table_size <= 0:
        raise ValueError("seed table size must be positive")
    restart_n = int(round(table_size * restart_fraction))
    normal_n = table_size - restart_n
    if restart_n <= 0 or normal_n <= 0:
        raise ValueError("restart fraction must leave both normal and restart entries")
    if not normal_pool or not random_buffer or not regret_buffer:
        raise ValueError("seed-table source pools must be non-empty")
    rng_normal = random.Random(random_seed ^ 0x4E4F524D)
    shared_normal = [rng_normal.choice(normal_pool) for _ in range(normal_n)]
    rng_normal_tail = random.Random(random_seed ^ 0x4E544149)
    normal_tail = [rng_normal_tail.choice(normal_pool) for _ in range(restart_n)]
    rng_random = random.Random(random_seed ^ 0x52414E44)
    random_tail = [rng_random.choice(random_buffer) for _ in range(restart_n)]
    rng_regret = random.Random(random_seed ^ 0x52454752)
    regret_tail = weighted_choices(rng_regret, regret_buffer, restart_n, temperature)
    return shared_normal + normal_tail, shared_normal + random_tail, shared_normal + regret_tail, normal_n


def run(args: argparse.Namespace) -> dict:
    paths = [Path(v) for v in (args.regret_buffer_out, args.random_buffer_out,
                               args.normal_seed_out, args.random_seed_out,
                               args.regret_seed_out, args.report)]
    if len({p.resolve(strict=False) for p in paths}) != len(paths):
        raise ValueError("all outputs must be distinct")
    if any(p.exists() for p in paths):
        raise ValueError("outputs are no-clobber")
    if args.buffer_size <= 0:
        raise ValueError("buffer-size must be positive")
    if args.value_scale <= 0 or args.temperature <= 0:
        raise ValueError("value-scale and temperature must be positive")
    if not 0.0 < args.restart_fraction < 1.0:
        raise ValueError("restart-fraction must be in (0,1)")

    data = Path(args.data); meta = Path(args.meta)
    rows = read_rows(data, meta)
    maxima, random_states, normal_states, game_diag = game_candidates(
        rows, args.value_scale, args.random_seed)
    maxima_unique = dedupe_candidates(maxima)
    maxima_unique.sort(key=lambda c: (-c.regret, c.row.game_id, c.row.ply, c.row.fingerprint))
    random_unique = dedupe_rows(random_states)
    random_unique.sort(key=lambda r: deterministic_key(args.random_seed, "game", r.game_id, r.fingerprint))
    normal_unique = dedupe_rows(normal_states)
    normal_unique.sort(key=lambda r: deterministic_key(args.random_seed, "normal", r.game_id, r.fingerprint))
    if len(maxima_unique) < args.buffer_size:
        raise ValueError(f"only {len(maxima_unique)} unique regret candidates for buffer {args.buffer_size}")
    if len(random_unique) < args.buffer_size:
        raise ValueError(f"only {len(random_unique)} unique random candidates for buffer {args.buffer_size}")
    if len(normal_unique) < args.buffer_size:
        raise ValueError(f"only {len(normal_unique)} unique normal openings for buffer {args.buffer_size}")

    regret_buffer = maxima_unique[:args.buffer_size]
    random_buffer = random_unique[:args.buffer_size]
    # Zero old targets in every published seed/buffer file.
    write_jnnw(Path(args.regret_buffer_out), [c.row for c in regret_buffer])
    write_jnnw(Path(args.random_buffer_out), random_buffer)

    normal_table, random_table, regret_table, normal_prefix_n = build_seed_tables(
        normal_unique, random_buffer, regret_buffer, args.seed_table_size,
        args.restart_fraction, args.temperature, args.random_seed)
    write_jnnw(Path(args.normal_seed_out), normal_table)
    write_jnnw(Path(args.random_seed_out), random_table)
    write_jnnw(Path(args.regret_seed_out), regret_table)
    # The paired restart arms must share the exact same normal prefix.
    prefix_random = b"".join(r.seed_record() for r in random_table[:normal_prefix_n])
    prefix_regret = b"".join(r.seed_record() for r in regret_table[:normal_prefix_n])
    if prefix_random != prefix_regret:
        raise RuntimeError("RANDOM/REGRET normal seed prefix drift")

    overlap = len({r.fingerprint for r in random_buffer} &
                  {c.row.fingerprint for c in regret_buffer})
    report = {
        "schema": "jass.l3_rgsc_trajectory_archive.v1",
        "operation": "oracle_sampled_trajectory_regret_restart_archive",
        "source": {
            "data": str(data), "data_sha256": _sha256(data),
            "meta": str(meta), "meta_sha256": _sha256(meta),
            "records": len(rows), "meta_schema": "JSM2",
        },
        "regret": {
            "formula": "mean_future_sampled((tanh(score_white/(2*value_scale))-z_white)^2)",
            "value_scale": args.value_scale,
            "trajectory_scope": "emitted_JNNW_samples_of_each_resolved_game",
            "teacher": None,
            "deep_relabel": False,
            "one_max_candidate_per_game_before_global_ranking": True,
            "all_game_maxima_quantiles": quantiles([c.regret for c in maxima]),
            "selected_buffer_quantiles": quantiles([c.regret for c in regret_buffer]),
        },
        "source_games": game_diag,
        "buffer": {
            "size": args.buffer_size,
            "paper_scale": "100 states x 16 Jass workers",
            "regret": describe_rows([c.row for c in regret_buffer]),
            "random": describe_rows(random_buffer),
            "state_overlap": overlap,
        },
        "restart_sampling": {
            "restart_fraction": args.restart_fraction,
            "temperature": args.temperature,
            "regret_probability": "proportional_to_R^(1/tau)",
            "seed_table_size": args.seed_table_size,
            "normal_entries": normal_prefix_n,
            "restart_entries": args.seed_table_size - normal_prefix_n,
            "random_seed": args.random_seed,
            "random_and_regret_normal_prefix_byte_identical": True,
            "engine_contract": "--seed-frac 100 --random-open-plies 0 --split-selfplay-rngs; same generator seed per arm",
        },
        "outputs": {},
        "guards": {
            "old_score_bytes_in_seed_outputs": 0,
            "old_wdl_bytes_in_seed_outputs": 0,
            "scan_or_external_teacher": False,
            "future_strength_result_used": False,
            "promotion_authorized": False,
        },
    }
    for name, path in (("regret_buffer", Path(args.regret_buffer_out)),
                       ("random_buffer", Path(args.random_buffer_out)),
                       ("normal_seed_table", Path(args.normal_seed_out)),
                       ("random_seed_table", Path(args.random_seed_out)),
                       ("regret_seed_table", Path(args.regret_seed_out))):
        report["outputs"][name] = {"path": str(path), "sha256": _sha256(path)}
    _atomic_text(Path(args.report), json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", required=True)
    p.add_argument("--meta", required=True)
    p.add_argument("--regret-buffer-out", required=True)
    p.add_argument("--random-buffer-out", required=True)
    p.add_argument("--normal-seed-out", required=True)
    p.add_argument("--random-seed-out", required=True)
    p.add_argument("--regret-seed-out", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--buffer-size", type=int, default=DEFAULT_BUFFER_SIZE)
    p.add_argument("--seed-table-size", type=int, default=DEFAULT_TABLE_SIZE)
    p.add_argument("--value-scale", type=float, default=DEFAULT_VALUE_SCALE)
    p.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    p.add_argument("--restart-fraction", type=float, default=DEFAULT_RESTART_FRACTION)
    p.add_argument("--random-seed", type=int, default=DEFAULT_RANDOM_SEED)
    args = p.parse_args(argv)
    report = run(args)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
