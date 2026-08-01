#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a stochastic opening-position pool from a sequential master JNNW.

The Cycle-8 master converter writes every position of every successfully
replayed game, including the standard start position at each game boundary.
This tool recovers those boundaries, considers early positions only, asks the
Jass move generator which candidates are quiet, then keeps at most one
deterministically sampled position per game.  Uniform sampling from the output
therefore de-biases popular opening prefixes instead of reproducing their raw
frequency.

No master result or move is used as a training target.  The output contains
initial states only; continuations and WDL labels must be generated afresh by
self-play.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


MAGIC = b"JNNW"
REC = struct.Struct("<QQQQBib")
START_BBS = (
    sum(1 << (square - 1) for square in range(31, 51)),
    0,
    sum(1 << (square - 1) for square in range(1, 21)),
    0,
)
START_KEY = struct.pack("<QQQQB", *START_BBS, 0)


@dataclass(frozen=True)
class Candidate:
    game_id: int
    ply: int
    pieces: int
    position: bytes
    record: bytes


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jnnw(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise ValueError(f"{path}: not a JNNW file")
    count = struct.unpack_from("<I", raw, 4)[0]
    expected = 8 + count * REC.size
    if len(raw) != expected:
        raise ValueError(
            f"{path}: size/count mismatch ({len(raw)} != {expected})"
        )
    return [
        raw[8 + index * REC.size:8 + (index + 1) * REC.size]
        for index in range(count)
    ]


def _piece_count(record: bytes) -> int:
    return sum(value.bit_count() for value in struct.unpack_from("<QQQQ", record))


def collect_candidates(
    records: list[bytes],
    *,
    min_ply: int,
    max_ply: int,
    min_pieces: int,
    allow_kings: bool,
) -> tuple[list[Candidate], int]:
    candidates: list[Candidate] = []
    game_id = -1
    ply = 0
    for record in records:
        position = record[:33]
        if position == START_KEY:
            game_id += 1
            ply = 0
            continue
        if game_id < 0:
            continue
        ply += 1
        if not min_ply <= ply <= max_ply:
            continue
        wm, wk, bm, bk = struct.unpack_from("<QQQQ", record)
        pieces = wm.bit_count() + wk.bit_count() + bm.bit_count() + bk.bit_count()
        if pieces < min_pieces or (not allow_kings and (wk or bk)):
            continue
        # Quiet classification is delegated to Jass below. Zeroing both target
        # fields also makes it impossible for source labels to leak into the
        # opening artefact.
        neutral = position + struct.pack("<ib", 0, 0)
        candidates.append(Candidate(game_id, ply, pieces, position, neutral))
    return candidates, game_id + 1


def _write_jnnw(path: Path, candidates: list[Candidate]) -> None:
    path.write_bytes(
        MAGIC
        + struct.pack("<I", len(candidates))
        + b"".join(candidate.record for candidate in candidates)
    )


def _read_quiet_flags(path: Path, expected: int) -> list[bool]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"QIET":
        raise ValueError(f"{path}: not a QIET sidecar")
    count = struct.unpack_from("<I", raw, 4)[0]
    if count != expected or len(raw) != 8 + count:
        raise ValueError(f"{path}: quiet sidecar count mismatch")
    return [value != 0 for value in raw[8:]]


def _rank(candidate: Candidate, seed: int) -> bytes:
    return hashlib.blake2b(
        candidate.position
        + struct.pack("<QQ", candidate.game_id, seed),
        digest_size=16,
    ).digest()


def select_positions(
    candidates: list[Candidate],
    quiet_flags: list[bool],
    *,
    positions: int,
    seed: int,
) -> list[Candidate]:
    if len(candidates) != len(quiet_flags):
        raise ValueError("candidate/quiet count mismatch")
    by_game: dict[int, list[Candidate]] = defaultdict(list)
    for candidate, quiet in zip(candidates, quiet_flags):
        if quiet:
            by_game[candidate.game_id].append(candidate)

    # One early quiet position per source game. The per-game choice and final
    # order are deterministic but independent of database row order.
    one_per_game = [
        min(rows, key=lambda row: _rank(row, seed))
        for rows in by_game.values()
    ]
    one_per_game.sort(key=lambda row: _rank(row, seed ^ 0x9E3779B97F4A7C15))

    selected: list[Candidate] = []
    seen: set[bytes] = set()
    for candidate in one_per_game:
        if candidate.position in seen:
            continue
        seen.add(candidate.position)
        selected.append(candidate)
        if len(selected) >= positions:
            break
    return selected


def _piece_list(men: int, kings: int) -> str:
    rows = [str(square) for square in range(1, 51) if men & (1 << (square - 1))]
    rows.extend(
        f"K{square}"
        for square in range(1, 51)
        if kings & (1 << (square - 1))
    )
    return ",".join(rows)


def position_to_fen(position: bytes) -> str:
    wm, wk, bm, bk, stm = struct.unpack("<QQQQB", position)
    side = "W" if stm == 0 else "B"
    return f"{side}:W{_piece_list(wm, wk)}:B{_piece_list(bm, bk)}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--jass", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--positions", type=int, default=8000)
    parser.add_argument("--min-ply", type=int, default=8)
    parser.add_argument("--max-ply", type=int, default=20)
    parser.add_argument("--min-pieces", type=int, default=34)
    parser.add_argument("--allow-kings", action="store_true")
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--source-label", default="master-selfplay-openings")
    args = parser.parse_args()

    if args.positions <= 0:
        raise SystemExit("--positions must be positive")
    if args.min_ply < 1 or args.max_ply < args.min_ply:
        raise SystemExit("invalid ply interval")
    if not 2 <= args.min_pieces <= 40:
        raise SystemExit("--min-pieces must be in [2,40]")
    if not args.jass.is_file():
        raise SystemExit(f"jass binary not found: {args.jass}")

    records = _read_jnnw(args.data)
    candidates, games = collect_candidates(
        records,
        min_ply=args.min_ply,
        max_ply=args.max_ply,
        min_pieces=args.min_pieces,
        allow_kings=args.allow_kings,
    )
    if not candidates:
        raise SystemExit("no early-game candidates found")

    with tempfile.TemporaryDirectory(prefix="jass-opening-pool-") as tmp:
        tmpdir = Path(tmp)
        candidate_path = tmpdir / "candidates.jnnw"
        quiet_path = tmpdir / "candidates.quiet"
        _write_jnnw(candidate_path, candidates)
        subprocess.run(
            [str(args.jass), "--dump-quiet-flags",
             str(candidate_path), str(quiet_path)],
            check=True,
        )
        quiet = _read_quiet_flags(quiet_path, len(candidates))

    selected = select_positions(
        candidates, quiet, positions=args.positions, seed=args.seed
    )
    if len(selected) != args.positions:
        raise SystemExit(
            f"only {len(selected)} unique quiet games for "
            f"--positions={args.positions}"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# jass stochastic master opening pool\n")
        stream.write(
            f"# source={args.source_label} positions={args.positions} "
            f"plies={args.min_ply}-{args.max_ply} seed={args.seed}\n"
        )
        for index, candidate in enumerate(selected):
            stream.write(
                f"{position_to_fen(candidate.position)}"
                f"  # master-opening-{index} game={candidate.game_id}"
                f" ply={candidate.ply} pieces={candidate.pieces}\n"
            )

    quiet_count = sum(quiet)
    payload = {
        "schema": 1,
        "mode": "one-quiet-opening-per-master-game-uniform-over-unique-fen",
        "source_label": args.source_label,
        "source_data": str(args.data),
        "source_sha256": _sha256(args.data),
        "source_records": len(records),
        "source_game_boundaries": games,
        "candidate_records": len(candidates),
        "quiet_candidate_records": quiet_count,
        "selected_positions": len(selected),
        "unique_positions": len({row.position for row in selected}),
        "ply_interval": [args.min_ply, args.max_ply],
        "minimum_pieces": args.min_pieces,
        "allow_kings": args.allow_kings,
        "seed": args.seed,
        "selected_ply_histogram": dict(sorted(Counter(
            str(row.ply) for row in selected
        ).items())),
        "selected_piece_histogram": dict(sorted(Counter(
            str(row.pieces) for row in selected
        ).items())),
        "master_labels_or_moves_used_for_training": False,
        "fresh_selfplay_wdl_required": True,
        "pool_sha256": _sha256(args.out),
    }
    args.manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
