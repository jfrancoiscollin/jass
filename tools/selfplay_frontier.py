#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Game-aware dataset utilities for the autonomous L3-PURE self-play loop.

The tool consumes only Jass self-play records and the aligned ``JSM1`` sidecar
emitted by ``jass --gen-data-wdl --sample-meta-out``.  It has four operations:

``merge``
    Merge independent shards while namespacing game/opening identifiers.

``split``
    Put complete opening groups (including ``--pair-openings`` repetitions) in
    either train or holdout, then write train rows followed by holdout rows.

``mine``
    Build the next generation's moving conversion frontier.  Candidates are
    positions reached by the lineage itself where a material advantage was
    either lost/drawn (primary) or converted (small calibration share).  The
    only outcome used for selection is the actual terminal WDL already present
    in JNNW.  Output seed records have score and WDL zeroed, so no target can
    leak into the next game; their continuations must earn a fresh terminal WDL.

``profile``
    Publish distribution diagnostics for one merged self-play corpus: realised
    opening/game diversity, unique positions, phase/material coverage and a
    record-level conversion diagnostic.  The latter is explicitly not a gate:
    records from the same game are correlated.

This is deliberately not an oracle miner: no Scan, deep relabel, master game,
fixed gymnasium or external teacher is accepted as input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

JNNW_MAGIC = b"JNNW"
JNNW_REC = 38
META_MAGIC = b"JSM1"
META_REC = 17  # game_id:u64, opening_id:u64, seeded:u8


@dataclass(frozen=True)
class Meta:
    game_id: int
    opening_id: int
    seeded: int


@dataclass(frozen=True)
class Candidate:
    record: bytes
    meta: Meta
    kind: str
    margin: int
    pieces: int


def _read_counted(path: Path, magic: bytes, record_size: int) -> tuple[int, bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != magic:
        raise ValueError(f"{path}: expected {magic.decode('ascii')} header")
    count = struct.unpack_from("<I", raw, 4)[0]
    expected = 8 + count * record_size
    if len(raw) != expected:
        raise ValueError(f"{path}: size {len(raw)} != {expected} for {count} records")
    return count, raw[8:]


def read_pair(data_path: Path, meta_path: Path) -> tuple[list[bytes], list[Meta]]:
    n_data, data = _read_counted(data_path, JNNW_MAGIC, JNNW_REC)
    n_meta, meta = _read_counted(meta_path, META_MAGIC, META_REC)
    if n_data != n_meta:
        raise ValueError(f"data/meta count mismatch: {n_data} != {n_meta}")
    records = [data[i * JNNW_REC:(i + 1) * JNNW_REC] for i in range(n_data)]
    rows = [
        Meta(*struct.unpack_from("<QQB", meta, i * META_REC))
        for i in range(n_meta)
    ]
    return records, rows


def write_pair(data_path: Path, meta_path: Path,
               records: list[bytes], rows: list[Meta]) -> None:
    if len(records) != len(rows):
        raise ValueError("data/meta output count mismatch")
    data_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    count = len(records)
    data_path.write_bytes(JNNW_MAGIC + struct.pack("<I", count) + b"".join(records))
    meta_body = b"".join(
        struct.pack("<QQB", row.game_id, row.opening_id, row.seeded)
        for row in rows
    )
    meta_path.write_bytes(META_MAGIC + struct.pack("<I", count) + meta_body)


def _manifest(path: str | None, payload: dict) -> None:
    if path:
        Path(path).write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def do_merge(args: argparse.Namespace) -> int:
    records_out: list[bytes] = []
    meta_out: list[Meta] = []
    source_counts: Counter = Counter()
    shard_rows = []
    renamespace_nested = bool(getattr(args, "renamespace_nested", False))
    for shard_index, (data_name, meta_name) in enumerate(args.pair, start=1):
        records, rows = read_pair(Path(data_name), Path(meta_name))
        if shard_index >= (1 << 16):
            raise ValueError("too many shards for 16-bit namespace")
        prefix = shard_index << 48
        game_namespace: dict[int, int] = {}
        opening_namespace: dict[int, int] = {}
        for record, row in zip(records, rows):
            if renamespace_nested:
                game_id = game_namespace.setdefault(row.game_id, len(game_namespace))
                opening_id = opening_namespace.setdefault(row.opening_id, len(opening_namespace))
            else:
                game_id = row.game_id
                opening_id = row.opening_id
            if game_id >= (1 << 48) or opening_id >= (1 << 48):
                raise ValueError("local game/opening id exceeds 48-bit namespace")
            records_out.append(record)
            meta_out.append(Meta(prefix | game_id, prefix | opening_id, row.seeded))
            source_counts["frontier" if row.seeded else "standard"] += 1
        shard_rows.append({
            "data": data_name,
            "meta": meta_name,
            "records": len(records),
            "nested_namespace_remapped": renamespace_nested,
            "games": len(game_namespace) if renamespace_nested else None,
            "openings": len(opening_namespace) if renamespace_nested else None,
        })
    write_pair(Path(args.out_data), Path(args.out_meta), records_out, meta_out)
    _manifest(args.manifest, {
        "schema": 1,
        "operation": "merge",
        "records": len(records_out),
        "shards": shard_rows,
        "source_records": dict(sorted(source_counts.items())),
    })
    return 0


def _opening_fold(opening_id: int, seed: int, mod: int) -> int:
    payload = struct.pack("<QQ", opening_id, seed & ((1 << 64) - 1))
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "little") % mod


def do_split(args: argparse.Namespace) -> int:
    if args.holdout_mod < 2:
        raise ValueError("--holdout-mod must be >= 2")
    records, rows = read_pair(Path(args.data), Path(args.meta))
    train_records: list[bytes] = []
    train_meta: list[Meta] = []
    hold_records: list[bytes] = []
    hold_meta: list[Meta] = []
    fold_by_opening: dict[int, bool] = {}
    for record, row in zip(records, rows):
        hold = fold_by_opening.setdefault(
            row.opening_id,
            _opening_fold(row.opening_id, args.seed, args.holdout_mod) == 0,
        )
        target_records, target_meta = (
            (hold_records, hold_meta) if hold else (train_records, train_meta)
        )
        target_records.append(record)
        target_meta.append(row)
    combined_records = train_records + hold_records
    combined_meta = train_meta + hold_meta
    write_pair(Path(args.out_data), Path(args.out_meta), combined_records, combined_meta)
    hold_openings = sum(fold_by_opening.values())
    _manifest(args.manifest, {
        "schema": 1,
        "operation": "split",
        "split_unit": "opening_id",
        "holdout_mod": args.holdout_mod,
        "seed": args.seed,
        "records": len(records),
        "train_records": len(train_records),
        "holdout_records": len(hold_records),
        "train_openings": len(fold_by_opening) - hold_openings,
        "holdout_openings": hold_openings,
        "tail_is_holdout": True,
    })
    return 0


def _material(record: bytes) -> tuple[str | None, int, int]:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    white = wm.bit_count() + 3 * wk.bit_count()
    black = bm.bit_count() + 3 * bk.bit_count()
    pieces = wm.bit_count() + wk.bit_count() + bm.bit_count() + bk.bit_count()
    if white > black:
        return "W", white - black, pieces
    if black > white:
        return "B", black - white, pieces
    return None, 0, pieces


def _winner(record: bytes) -> str | None:
    stm = record[32]
    wdl = struct.unpack_from("<b", record, 37)[0]
    if wdl == 0:
        return None
    stm_side = "W" if stm == 0 else "B"
    if wdl > 0:
        return stm_side
    return "B" if stm_side == "W" else "W"


def _candidate_hash(candidate: Candidate, seed: int) -> bytes:
    return hashlib.blake2b(
        candidate.record[:33]
        + struct.pack("<QQQ", candidate.meta.game_id, candidate.meta.opening_id, seed),
        digest_size=16,
    ).digest()


def _piece_band(pieces: int) -> str:
    if pieces <= 10:
        return "deep_endgame"
    if pieces <= 16:
        return "endgame"
    return "late_midgame"


def _phase_band(pieces: int) -> str:
    if pieces >= 30:
        return "opening"
    if pieces >= 22:
        return "midgame"
    if pieces >= 15:
        return "late_midgame"
    if pieces >= 8:
        return "endgame"
    return "deep_endgame"


def _material_stratum(margin: int) -> str:
    if margin == 0:
        return "p4_equal"
    if margin == 1:
        return "p3_thin"
    if margin <= 3:
        return "p2_medium"
    return "p1_clear"


def _count_summary(values: Counter) -> dict:
    if not values:
        return {"min": 0, "max": 0, "mean": 0.0}
    counts = list(values.values())
    return {
        "min": min(counts),
        "max": max(counts),
        "mean": sum(counts) / len(counts),
    }


def do_profile(args: argparse.Namespace) -> int:
    records, rows = read_pair(Path(args.data), Path(args.meta))
    unique_positions: set[bytes] = set()
    unique_by_stratum: dict[str, set[bytes]] = defaultdict(set)
    records_by_game: Counter = Counter()
    records_by_opening: Counter = Counter()
    wdl_counts: Counter = Counter()
    winner_counts: Counter = Counter()
    phase_counts: Counter = Counter()
    stratum_counts: Counter = Counter()
    source_counts: Counter = Counter()
    conversion_total: Counter = Counter()
    conversion_wins: Counter = Counter()

    for record, row in zip(records, rows):
        position = record[:33]
        unique_positions.add(position)
        records_by_game[row.game_id] += 1
        records_by_opening[row.opening_id] += 1
        source_counts["frontier" if row.seeded else "standard"] += 1

        wdl = struct.unpack_from("<b", record, 37)[0]
        wdl_counts[{1: "win", 0: "draw", -1: "loss"}[wdl]] += 1
        winner = _winner(record)
        winner_counts[winner if winner is not None else "draw"] += 1

        advantaged, margin, pieces = _material(record)
        phase_counts[_phase_band(pieces)] += 1
        stratum = _material_stratum(margin)
        stratum_counts[stratum] += 1
        unique_by_stratum[stratum].add(position)
        if advantaged is not None:
            conversion_total[stratum] += 1
            if winner == advantaged:
                conversion_wins[stratum] += 1

    conversion = {}
    for stratum in ("p1_clear", "p2_medium", "p3_thin"):
        total = conversion_total[stratum]
        won = conversion_wins[stratum]
        conversion[stratum] = {
            "records": total,
            "converted_records": won,
            "rate": won / total if total else None,
        }

    data_path = Path(args.data)
    meta_path = Path(args.meta)
    total_records = len(records)
    _manifest(args.manifest, {
        "schema": 1,
        "operation": "profile_selfplay",
        "diagnostic_only": True,
        "input": {
            "data": str(data_path),
            "meta": str(meta_path),
            "data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
            "meta_sha256": hashlib.sha256(meta_path.read_bytes()).hexdigest(),
        },
        "records": total_records,
        "games": len(records_by_game),
        "openings": len(records_by_opening),
        "unique_positions": len(unique_positions),
        "duplicate_position_records": total_records - len(unique_positions),
        "unique_position_ratio": (
            len(unique_positions) / total_records if total_records else 0.0
        ),
        "records_per_game": _count_summary(records_by_game),
        "records_per_opening": _count_summary(records_by_opening),
        "wdl_stm": dict(sorted(wdl_counts.items())),
        "terminal_winner": dict(sorted(winner_counts.items())),
        "phase_records": dict(sorted(phase_counts.items())),
        "material_stratum_records": dict(sorted(stratum_counts.items())),
        "material_stratum_unique_positions": {
            key: len(value) for key, value in sorted(unique_by_stratum.items())
        },
        "record_level_conversion": conversion,
        "record_level_conversion_unit": "correlated_position_record_not_gate",
        "source_records": dict(sorted(source_counts.items())),
    })
    return 0


def _zero_targets(record: bytes) -> bytes:
    return record[:33] + struct.pack("<i", 0) + struct.pack("<b", 0)


def _rot50(value: int) -> int:
    result = 0
    while value:
        lsb = value & -value
        square = lsb.bit_length() - 1
        result |= 1 << (49 - square)
        value ^= lsb
    return result


def mirror_record(record: bytes) -> bytes:
    """Rotate 180 degrees, swap colours and flip side-to-move."""
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    stm = record[32]
    mirrored = struct.pack("<QQQQB", _rot50(bm), _rot50(bk), _rot50(wm), _rot50(wk), 1 - stm)
    return mirrored + struct.pack("<i", 0) + struct.pack("<b", 0)


def _round_robin(candidates: list[Candidate], limit: int, seed: int) -> list[Candidate]:
    buckets: dict[tuple[str, int, str], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        buckets[(candidate.kind, candidate.margin, _piece_band(candidate.pieces))].append(candidate)
    for values in buckets.values():
        values.sort(key=lambda row: _candidate_hash(row, seed))
    ordered_keys = sorted(buckets)
    selected: list[Candidate] = []
    offset = 0
    while len(selected) < limit:
        progressed = False
        for key in ordered_keys:
            values = buckets[key]
            if offset < len(values):
                selected.append(values[offset])
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
        offset += 1
    return selected


def do_mine(args: argparse.Namespace) -> int:
    if args.max_positions < 2:
        raise ValueError("--max-positions must be >= 2")
    if not 0.0 <= args.converted_fraction <= 1.0:
        raise ValueError("--converted-fraction must be in [0,1]")
    records, rows = read_pair(Path(args.data), Path(args.meta))
    best: dict[tuple[int, str], Candidate] = {}
    observed: Counter = Counter()
    for record, row in zip(records, rows):
        advantaged, margin, pieces = _material(record)
        if advantaged is None or not args.margin_min <= margin <= args.margin_max:
            continue
        if not args.min_pieces <= pieces <= args.max_pieces:
            continue
        kind = "converted" if _winner(record) == advantaged else "failed_conversion"
        candidate = Candidate(record, row, kind, margin, pieces)
        observed[kind] += 1
        key = (row.game_id, kind)
        previous = best.get(key)
        if previous is None or _candidate_hash(candidate, args.seed) < _candidate_hash(previous, args.seed):
            best[key] = candidate

    unique = list(best.values())
    failed = [row for row in unique if row.kind == "failed_conversion"]
    converted = [row for row in unique if row.kind == "converted"]
    # Output is colour-paired, so select at most half the requested base records.
    base_limit = args.max_positions // 2
    converted_limit = round(base_limit * args.converted_fraction)
    failed_limit = base_limit - converted_limit
    selected = _round_robin(failed, failed_limit, args.seed)
    selected += _round_robin(converted, converted_limit, args.seed ^ 0xA5A5A5A5)
    if len(selected) < base_limit:
        chosen = {(row.meta.game_id, row.kind) for row in selected}
        remainder = [row for row in failed + converted
                     if (row.meta.game_id, row.kind) not in chosen]
        selected += _round_robin(remainder, base_limit - len(selected), args.seed ^ 0x5A5A5A5A)

    output_records: list[bytes] = []
    seen_positions: set[bytes] = set()
    selected_counts: Counter = Counter()
    for candidate in selected:
        original = _zero_targets(candidate.record)
        for paired in (original, mirror_record(original)):
            key = paired[:33]
            if key in seen_positions or len(output_records) >= args.max_positions:
                continue
            seen_positions.add(key)
            output_records.append(paired)
        selected_counts[candidate.kind] += 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(JNNW_MAGIC + struct.pack("<I", len(output_records)) + b"".join(output_records))
    digest = hashlib.sha256(Path(args.data).read_bytes()).hexdigest()
    margin_counts = Counter(row.margin for row in selected)
    piece_counts = Counter(_piece_band(row.pieces) for row in selected)
    source_counts = Counter("frontier" if row.meta.seeded else "standard" for row in selected)
    _manifest(args.manifest, {
        "schema": 1,
        "operation": "mine_frontier",
        "input_sha256": digest,
        "input_records": len(records),
        "candidate_records": dict(sorted(observed.items())),
        "candidate_games": len(unique),
        "selected_base_positions": len(selected),
        "output_positions_with_colour_mirrors": len(output_records),
        "selected_kind": dict(sorted(selected_counts.items())),
        "selected_margin": {str(k): v for k, v in sorted(margin_counts.items())},
        "selected_piece_band": dict(sorted(piece_counts.items())),
        "selected_source": dict(sorted(source_counts.items())),
        "labels_used_for_selection_only": True,
        "output_score_and_wdl_zeroed": True,
        "external_teacher_inputs": 0,
    })
    return 0 if output_records else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    merge = sub.add_parser("merge", help="merge JNNW/JSM1 shards")
    merge.add_argument("--pair", nargs=2, action="append", required=True,
                       metavar=("DATA", "META"))
    merge.add_argument("--out-data", required=True)
    merge.add_argument("--out-meta", required=True)
    merge.add_argument("--manifest")
    merge.add_argument(
        "--renamespace-nested",
        action="store_true",
        help="remap existing 64-bit game/opening IDs per input while preserving equality groups",
    )
    merge.set_defaults(func=do_merge)

    split = sub.add_parser("split", help="make an opening-level holdout tail")
    split.add_argument("--data", required=True)
    split.add_argument("--meta", required=True)
    split.add_argument("--out-data", required=True)
    split.add_argument("--out-meta", required=True)
    split.add_argument("--holdout-mod", type=int, default=10)
    split.add_argument("--seed", type=int, default=1)
    split.add_argument("--manifest")
    split.set_defaults(func=do_split)

    mine = sub.add_parser("mine", help="mine a moving, self-generated conversion frontier")
    mine.add_argument("--data", required=True)
    mine.add_argument("--meta", required=True)
    mine.add_argument("--out", required=True)
    mine.add_argument("--manifest")
    mine.add_argument("--max-positions", type=int, default=4000,
                      help="total output count including colour mirrors")
    mine.add_argument("--min-pieces", type=int, default=8)
    mine.add_argument("--max-pieces", type=int, default=24)
    mine.add_argument("--margin-min", type=int, default=1)
    mine.add_argument("--margin-max", type=int, default=3)
    mine.add_argument("--converted-fraction", type=float, default=0.20,
                      help="calibration share of successfully converted positions")
    mine.add_argument("--seed", type=int, default=1)
    mine.set_defaults(func=do_mine)

    profile = sub.add_parser("profile", help="profile self-play coverage and diversity")
    profile.add_argument("--data", required=True)
    profile.add_argument("--meta", required=True)
    profile.add_argument("--manifest", required=True)
    profile.set_defaults(func=do_profile)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
