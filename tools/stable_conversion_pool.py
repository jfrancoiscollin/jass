#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build and independently audit a *reachable, quiet and stable* +2 pool.

The old imbalance pools were synthetic placements.  A material lead in such a
position can disappear in the mandatory capture sequence on move one.  This
tool accepts either aligned, **unseeded** JNNW/JSM1 emitted by standard Jass
self-play, or the stronger replayable JSONL sidecar written by
``tools/scan_selfplay_gen.py --trajectory-out``.  Every selected position must
satisfy all of the following:

* its provenance is bound to source hashes and a game/opening id; trajectory
  input additionally starts at an allowed legal root and has every prefix
  transition accepted by Jass ``--dump-children``;
* the advantaged side has exactly two extra men, the king counts are equal and
  the men-equivalent material gap is exactly two;
* neither colour has a capture or an immediate promotion (queried by changing
  only the side to move and using Jass ``--dump-legal``).  Consequently the +2
  gap survives every legal first ply from the position.  This is deliberately
  a one-ply material-stability claim: it neither certifies a game-theoretical
  win nor guarantees that the gap survives the opponent's following reply;
* output cells are exactly balanced by material stratum, advantaged colour and
  side to move, with at most one selected position per source game (trajectory
  mode) or per ``opening_id`` (JNNW/JSM1 mode).

``build`` writes three aligned artefacts: a FEN pool, one JSON proof per FEN and
a manifest with source/output hashes and rejection counters.  ``audit`` reads
the original source again and redoes provenance, material, quiet and balance
checks; it does not trust the build proof.

Typical TOP3 replacement::

    python3 tools/stable_conversion_pool.py build \
      --jass ./build/jass --corpus g4-selfplay.jnnw.gz g4-selfplay.jsm.gz \
      --piece-pair 16:18 --piece-pair 17:19 --piece-pair 18:20 \
      --max-positions 384 --out-pool stable.fen \
      --out-proof stable.proof.jsonl --manifest stable.manifest.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import struct
import subprocess
import tempfile
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


START_FEN = "W:W31-50:B1-20"
MOVE_RE = re.compile(r"^\s*(\d+)\s*([x-])\s*(\d+)")


@dataclass(frozen=True)
class Board:
    stm: str
    wm: frozenset[int]
    wk: frozenset[int]
    bm: frozenset[int]
    bk: frozenset[int]

    def key(self) -> bytes:
        def bitboard(squares: Iterable[int]) -> int:
            value = 0
            for square in squares:
                value |= 1 << (square - 1)
            return value

        return struct.pack(
            "<QQQQB",
            bitboard(self.wm), bitboard(self.wk),
            bitboard(self.bm), bitboard(self.bk),
            0 if self.stm == "W" else 1,
        )

    def with_stm(self, stm: str) -> "Board":
        if stm not in {"W", "B"}:
            raise ValueError(f"bad side to move: {stm!r}")
        return Board(stm, self.wm, self.wk, self.bm, self.bk)

    def fen(self, stm: str | None = None) -> str:
        side = self.stm if stm is None else stm

        def piece_list(men: frozenset[int], kings: frozenset[int]) -> str:
            tokens = [str(square) for square in sorted(men)]
            tokens += [f"K{square}" for square in sorted(kings)]
            return ",".join(tokens)

        return (
            f"{side}:W{piece_list(self.wm, self.wk)}:"
            f"B{piece_list(self.bm, self.bk)}"
        )


@dataclass(frozen=True)
class Trajectory:
    source_path: str
    source_sha256: str
    row_index: int
    source_game_id: str
    trajectory_hash: str
    game_index: int | None
    shard: int | None
    outcome: str
    reason: str
    opening: str
    fens: tuple[str, ...]
    moves: tuple[str, ...]

    @property
    def source_key(self) -> str:
        return f"{self.source_sha256}:{self.source_game_id}"


@dataclass(frozen=True)
class CorpusSource:
    """Aligned JNNW/JSM1 provenance for one unseeded self-play record."""

    data_path: str
    data_sha256: str
    meta_path: str
    meta_sha256: str
    record_index: int
    game_id: int
    opening_id: int
    seeded: int

    @property
    def source_key(self) -> str:
        # Opening id is the independence unit: paired repetitions and every
        # sampled position from that opening must stay together.  Do not
        # namespace it by generation; a collision is conservatively treated as
        # the same source unit rather than allowing correlated rows through.
        return f"opening:{self.opening_id}"


@dataclass(frozen=True)
class Candidate:
    board: Board
    source: Trajectory | CorpusSource
    ply: int
    advantaged: str
    low_pieces: int
    high_pieces: int

    @property
    def position_id(self) -> str:
        return hashlib.sha256(self.board.key()).hexdigest()

    @property
    def source_key(self) -> str:
        return self.source.source_key


class JassBatch:
    """Small batch wrapper around the two eval-free Jass audit modes."""

    def __init__(self, binary: str, timeout: float = 300.0):
        self.binary = binary
        self.timeout = timeout

    def _run(self, mode: str, fens: Sequence[str]) -> list[str]:
        if not fens:
            return []
        with tempfile.TemporaryDirectory(prefix="jass-stable-pool-") as td:
            root = Path(td)
            source = root / "in.fen"
            target = root / "out.txt"
            source.write_text("".join(f"{fen}\n" for fen in fens), encoding="utf-8")
            proc = subprocess.run(
                [self.binary, mode, str(source), str(target)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"{mode} failed rc={proc.returncode}: {proc.stderr.strip()}"
                )
            lines = target.read_text(encoding="utf-8").splitlines()
        if len(lines) != len(fens):
            raise RuntimeError(
                f"{mode} returned {len(lines)} lines for {len(fens)} FENs"
            )
        return lines

    def legal(self, fens: Sequence[str]) -> list[str]:
        return self._run("--dump-legal", fens)

    def children(self, fens: Sequence[str]) -> list[list[dict]]:
        lines = self._run("--dump-children", fens)
        result: list[list[dict]] = []
        for index, line in enumerate(lines):
            row = json.loads(line)
            if not isinstance(row, list):
                raise ValueError(f"dump-children line {index} is not an array")
            result.append(row)
        return result


def _expand_token(token: str) -> tuple[bool, list[int]]:
    token = token.strip().upper()
    king = token.startswith("K")
    if king:
        token = token[1:]
    if not token:
        raise ValueError("empty piece token")
    if "-" in token:
        first_text, last_text = token.split("-", 1)
        if last_text.startswith("K"):
            last_text = last_text[1:]
        first, last = int(first_text), int(last_text)
        if first > last:
            raise ValueError(f"descending square range: {token!r}")
        squares = list(range(first, last + 1))
    else:
        squares = [int(token)]
    if any(square < 1 or square > 50 for square in squares):
        raise ValueError(f"square outside 1..50: {token!r}")
    return king, squares


def parse_fen(fen: str) -> Board:
    parts = fen.strip().split(":")
    if len(parts) != 3 or parts[0].strip().upper() not in {"W", "B"}:
        raise ValueError(f"bad Jass FEN: {fen!r}")
    stm = parts[0].strip().upper()
    parsed: dict[str, tuple[set[int], set[int]]] = {}
    for part in parts[1:]:
        part = part.strip()
        colour = part[:1].upper()
        if colour not in {"W", "B"} or colour in parsed:
            raise ValueError(f"bad colour list in FEN: {fen!r}")
        men: set[int] = set()
        kings: set[int] = set()
        for token in part[1:].split(","):
            if not token.strip():
                continue
            king, squares = _expand_token(token)
            target = kings if king else men
            for square in squares:
                if square in men or square in kings:
                    raise ValueError(f"duplicate square {square} in FEN: {fen!r}")
                target.add(square)
        parsed[colour] = men, kings
    if set(parsed) != {"W", "B"}:
        raise ValueError(f"FEN must contain W and B lists: {fen!r}")
    wm, wk = parsed["W"]
    bm, bk = parsed["B"]
    if (wm | wk) & (bm | bk):
        raise ValueError(f"white/black overlap in FEN: {fen!r}")
    return Board(stm, frozenset(wm), frozenset(wk),
                 frozenset(bm), frozenset(bk))


def trajectory_digest(opening: str, fens: Sequence[str], moves: Sequence[str]) -> str:
    payload = json.dumps(
        {"opening": opening, "fens": list(fens), "moves": list(moves)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" \
        else path.open("r", encoding="utf-8")


def load_trajectories(paths: Sequence[str], roots: set[bytes]) -> list[Trajectory]:
    trajectories: list[Trajectory] = []
    seen_games: set[str] = set()
    for name in paths:
        path = Path(name)
        source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        with _open_text(path) as handle:
            for row_index, line in enumerate(handle):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{row_index + 1}: bad JSON") from exc
                if not isinstance(raw, dict) or raw.get("schema") != 1:
                    raise ValueError(f"{path}:{row_index + 1}: expected schema=1 object")
                fens = tuple(raw.get("fens") or ())
                moves = tuple(raw.get("moves") or ())
                opening = str(raw.get("opening") or "")
                game_id = str(raw.get("source_game_id") or "")
                digest = str(raw.get("trajectory_hash") or "")
                if not game_id or len(fens) != len(moves) + 1 or not fens:
                    raise ValueError(
                        f"{path}:{row_index + 1}: missing game id or FEN/move misalignment"
                    )
                if parse_fen(opening).key() != parse_fen(fens[0]).key():
                    raise ValueError(f"{path}:{row_index + 1}: opening != first FEN")
                expected_digest = trajectory_digest(opening, fens, moves)
                if digest != expected_digest:
                    raise ValueError(f"{path}:{row_index + 1}: trajectory hash mismatch")
                if parse_fen(fens[0]).key() not in roots:
                    raise ValueError(
                        f"{path}:{row_index + 1}: trajectory does not start at an allowed root"
                    )
                source_key = f"{source_sha}:{game_id}"
                if source_key in seen_games:
                    raise ValueError(f"duplicate source game: {source_key}")
                seen_games.add(source_key)
                trajectories.append(Trajectory(
                    source_path=str(path), source_sha256=source_sha,
                    row_index=row_index, source_game_id=game_id,
                    trajectory_hash=digest,
                    game_index=(int(raw["game_index"])
                                if raw.get("game_index") is not None else None),
                    shard=(int(raw["shard"])
                           if raw.get("shard") is not None else None),
                    outcome=str(raw.get("outcome") or ""),
                    reason=str(raw.get("reason") or ""),
                    opening=opening, fens=fens, moves=moves,
                ))
    if not trajectories:
        raise ValueError("no trajectories found")
    return trajectories


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_binary(path: Path):
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")


def _board_from_record(record: bytes, *, where: str) -> Board:
    if len(record) != 38:
        raise ValueError(f"{where}: short JNNW record")
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    stm = record[32]
    if stm not in (0, 1):
        raise ValueError(f"{where}: bad STM byte {stm}")
    valid_mask = (1 << 50) - 1
    if any(value & ~valid_mask for value in (wm, wk, bm, bk)):
        raise ValueError(f"{where}: bit outside the 50-square board")
    if ((wm & wk) or (wm & bm) or (wm & bk) or (wk & bm)
            or (wk & bk) or (bm & bk)):
        raise ValueError(f"{where}: overlapping bitboards")

    def squares(value: int) -> frozenset[int]:
        return frozenset(index + 1 for index in range(50) if (value >> index) & 1)

    return Board("W" if stm == 0 else "B", squares(wm), squares(wk),
                 squares(bm), squares(bk))


def load_corpus_candidates(
    pairs: Sequence[Sequence[str]], *, men_gap: int, max_kings: int,
    piece_pairs: set[tuple[int, int]],
) -> tuple[list[Candidate], Counter, list[dict]]:
    """Stream aligned gzip/plain JNNW+JSM1 without retaining the full corpus."""
    candidates: list[Candidate] = []
    rejected: Counter = Counter()
    inputs: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for data_name, meta_name in pairs:
        data_path, meta_path = Path(data_name), Path(meta_name)
        data_sha, meta_sha = _sha256_file(data_path), _sha256_file(meta_path)
        pair_key = (data_sha, meta_sha)
        if pair_key in seen_pairs:
            raise ValueError("duplicate JNNW/JSM1 input pair")
        seen_pairs.add(pair_key)
        standard = seeded_count = 0
        with _open_binary(data_path) as data, _open_binary(meta_path) as meta:
            data_header, meta_header = data.read(8), meta.read(8)
            if len(data_header) != 8 or data_header[:4] != b"JNNW":
                raise ValueError(f"{data_path}: expected JNNW header")
            if len(meta_header) != 8 or meta_header[:4] != b"JSM1":
                raise ValueError(f"{meta_path}: expected JSM1 header")
            data_count = struct.unpack_from("<I", data_header, 4)[0]
            meta_count = struct.unpack_from("<I", meta_header, 4)[0]
            if data_count != meta_count:
                raise ValueError(
                    f"JNNW/JSM1 count mismatch: {data_count} != {meta_count}"
                )
            for index in range(data_count):
                record, metadata = data.read(38), meta.read(17)
                if len(record) != 38 or len(metadata) != 17:
                    raise ValueError(f"truncated aligned corpus at record {index}")
                game_id, opening_id, seeded = struct.unpack("<QQB", metadata)
                if seeded not in (0, 1):
                    raise ValueError(f"{meta_path}:{index}: invalid seeded byte {seeded}")
                if seeded:
                    seeded_count += 1
                else:
                    standard += 1
                board = _board_from_record(record, where=f"{data_path}:{index}")
                ok, facts, reason = _eligible(
                    board, men_gap=men_gap, max_kings=max_kings,
                    piece_pairs=piece_pairs,
                )
                if not ok:
                    rejected[reason] += 1
                    continue
                pair = tuple(sorted((facts["white_pieces"], facts["black_pieces"])))
                candidates.append(Candidate(
                    board=board,
                    source=CorpusSource(
                        data_path=str(data_path), data_sha256=data_sha,
                        meta_path=str(meta_path), meta_sha256=meta_sha,
                        record_index=index, game_id=game_id,
                        opening_id=opening_id, seeded=seeded,
                    ),
                    ply=-1,
                    advantaged=str(facts["advantaged"]),
                    low_pieces=pair[0], high_pieces=pair[1],
                ))
            if data.read(1) or meta.read(1):
                raise ValueError("JNNW/JSM1 has trailing bytes beyond declared count")
        inputs.append({
            "data": str(data_path), "data_sha256": data_sha,
            "meta": str(meta_path), "meta_sha256": meta_sha,
            "records": data_count, "standard_records": standard,
            "seeded_records": seeded_count,
        })
    seeded_total = sum(row["seeded_records"] for row in inputs)
    if seeded_total:
        raise ValueError(
            f"corpus is not standard-only: found {seeded_total} seeded records"
        )
    if not candidates:
        raise ValueError("no material candidates in JNNW/JSM1 corpus")
    return candidates, rejected, inputs


def _normalise_move(move: str) -> str:
    match = MOVE_RE.match(move)
    if not match:
        raise ValueError(f"bad logged move: {move!r}")
    return f"{int(match.group(1))}{match.group(2)}{int(match.group(3))}"


def verify_legal_trajectories(
    trajectories: Sequence[Trajectory], engine: JassBatch,
) -> int:
    parents: dict[bytes, str] = {}
    for trajectory in trajectories:
        for fen in trajectory.fens[:-1]:
            board = parse_fen(fen)
            parents.setdefault(board.key(), board.fen())
    keys = list(parents)
    dumped = engine.children([parents[key] for key in keys])
    child_map: dict[bytes, list[tuple[str, bytes]]] = {}
    for parent_key, rows in zip(keys, dumped):
        children: list[tuple[str, bytes]] = []
        for row in rows:
            if not isinstance(row, dict) or "move" not in row or "fen" not in row:
                raise ValueError("malformed row from --dump-children")
            children.append((_normalise_move(str(row["move"])),
                             parse_fen(str(row["fen"])).key()))
        child_map[parent_key] = children

    verified = 0
    for trajectory in trajectories:
        if trajectory.reason.lower().startswith("illegal move"):
            raise ValueError(f"source game ended on an illegal move: {trajectory.source_key}")
        for ply, (parent_fen, child_fen, logged_move) in enumerate(zip(
            trajectory.fens[:-1], trajectory.fens[1:], trajectory.moves
        )):
            parent_key = parse_fen(parent_fen).key()
            child_key = parse_fen(child_fen).key()
            move = _normalise_move(logged_move)
            if (move, child_key) not in child_map[parent_key]:
                raise ValueError(
                    f"illegal/desynchronised trajectory {trajectory.source_key} ply {ply}: "
                    f"{logged_move} -> {child_fen}"
                )
            verified += 1
    return verified


def material_facts(board: Board) -> dict:
    white_men, black_men = len(board.wm), len(board.bm)
    white_kings, black_kings = len(board.wk), len(board.bk)
    white_value = white_men + 3 * white_kings
    black_value = black_men + 3 * black_kings
    advantaged = "W" if white_value > black_value else (
        "B" if black_value > white_value else None
    )
    return {
        "white_men": white_men,
        "black_men": black_men,
        "white_kings": white_kings,
        "black_kings": black_kings,
        "white_value": white_value,
        "black_value": black_value,
        "men_gap": abs(white_men - black_men),
        "king_gap": abs(white_kings - black_kings),
        "value_gap": abs(white_value - black_value),
        "advantaged": advantaged,
        "white_pieces": white_men + white_kings,
        "black_pieces": black_men + black_kings,
    }


def _eligible(
    board: Board, *, men_gap: int, max_kings: int,
    piece_pairs: set[tuple[int, int]],
) -> tuple[bool, dict, str]:
    facts = material_facts(board)
    if facts["men_gap"] != men_gap:
        return False, facts, "men_gap"
    if facts["king_gap"] != 0:
        return False, facts, "king_gap"
    if facts["value_gap"] != men_gap:
        return False, facts, "value_gap"
    if facts["white_kings"] + facts["black_kings"] > max_kings:
        return False, facts, "too_many_kings"
    pair = tuple(sorted((facts["white_pieces"], facts["black_pieces"])))
    if piece_pairs and pair not in piece_pairs:
        return False, facts, "piece_pair"
    return True, facts, "eligible"


def _legal_facts(line: str) -> dict:
    stripped = line.strip()
    if stripped == "?":
        raise ValueError("Jass rejected a candidate FEN")
    tokens = stripped.split() if stripped else []
    captures = sum("*" in token for token in tokens)
    promotions = sum(token.endswith("+") for token in tokens)
    digest = hashlib.sha256(" ".join(tokens).encode("ascii")).hexdigest()
    return {
        "moves": len(tokens),
        "captures": captures,
        "promotions": promotions,
        "moves_sha256": digest,
    }


def audit_stability(
    candidates: Sequence[Candidate], engine: JassBatch,
) -> tuple[list[Candidate], dict[str, dict], Counter]:
    fens: list[str] = []
    for candidate in candidates:
        fens.extend((candidate.board.fen("W"), candidate.board.fen("B")))
    lines = engine.legal(fens)
    stable: list[Candidate] = []
    evidence: dict[str, dict] = {}
    rejected: Counter = Counter()
    for index, candidate in enumerate(candidates):
        white = _legal_facts(lines[2 * index])
        black = _legal_facts(lines[2 * index + 1])
        if white["moves"] == 0 or black["moves"] == 0:
            rejected["terminal_for_one_colour"] += 1
            continue
        if white["captures"] or black["captures"]:
            rejected["capture_available"] += 1
            continue
        if white["promotions"] or black["promotions"]:
            rejected["immediate_promotion"] += 1
            continue
        stable.append(candidate)
        evidence[candidate.position_id] = {"white": white, "black": black}
    return stable, evidence, rejected


def _rank(candidate: Candidate, seed: int) -> bytes:
    ordinal = (candidate.ply if candidate.ply >= 0
               else candidate.source.record_index)
    payload = (
        candidate.board.key()
        + candidate.source_key.encode("ascii")
        + struct.pack("<QQ", ordinal, seed & ((1 << 64) - 1))
    )
    return hashlib.blake2b(payload, digest_size=16).digest()


def _stratum(candidate: Candidate, piece_pairs: set[tuple[int, int]]) -> str:
    return f"{candidate.low_pieces}v{candidate.high_pieces}" if piece_pairs else "all"


def _cell(candidate: Candidate, piece_pairs: set[tuple[int, int]]) -> str:
    return (
        f"{_stratum(candidate, piece_pairs)}|"
        f"adv={candidate.advantaged}|stm={candidate.board.stm}"
    )


def expected_cells(piece_pairs: set[tuple[int, int]]) -> list[str]:
    strata = [f"{low}v{high}" for low, high in sorted(piece_pairs)] \
        if piece_pairs else ["all"]
    return [f"{stratum}|adv={adv}|stm={stm}"
            for stratum in strata for adv in ("W", "B") for stm in ("W", "B")]


def select_balanced(
    candidates: Sequence[Candidate], *, piece_pairs: set[tuple[int, int]],
    max_positions: int, seed: int,
) -> tuple[list[Candidate], dict[str, int], int]:
    cells = expected_cells(piece_pairs)
    if max_positions <= 0 or max_positions % len(cells):
        raise ValueError(
            f"--max-positions must be a positive multiple of {len(cells)}"
        )
    target = max_positions // len(cells)
    # Keep the best deterministic record for each source/position edge.  A
    # board may occur in several openings, so choosing its provenance greedily
    # here would be wrong: source and position are independent capacity-one
    # constraints in the exact flow solved below.
    edge_candidates: dict[tuple[str, bytes], Candidate] = {}
    position_cells: dict[bytes, str] = {}
    for candidate in candidates:
        position = candidate.board.key()
        cell = _cell(candidate, piece_pairs)
        previous_cell = position_cells.setdefault(position, cell)
        if previous_cell != cell:
            raise ValueError("one board was assigned to two balance cells")
        edge = (candidate.source_key, position)
        previous = edge_candidates.get(edge)
        if previous is None or _rank(candidate, seed) < _rank(previous, seed):
            edge_candidates[edge] = candidate

    class FlowEdge:
        __slots__ = ("to", "reverse", "capacity")

        def __init__(self, to: int, reverse: int, capacity: int):
            self.to = to
            self.reverse = reverse
            self.capacity = capacity

    def solve(per_cell: int) -> list[Candidate] | None:
        if per_cell == 0:
            return []
        source_candidates: dict[str, list[Candidate]] = defaultdict(list)
        position_candidates: dict[bytes, list[Candidate]] = defaultdict(list)
        for candidate in edge_candidates.values():
            source_candidates[candidate.source_key].append(candidate)
            position_candidates[candidate.board.key()].append(candidate)

        source_order = sorted(
            source_candidates,
            key=lambda value: (
                min(_rank(row, seed) for row in source_candidates[value]), value
            ),
        )
        position_order = sorted(
            position_candidates,
            key=lambda value: min(
                _rank(row, seed) for row in position_candidates[value]
            ),
        )
        super_source = 0
        source_node = {value: index + 1 for index, value in enumerate(source_order)}
        first_position = 1 + len(source_order)
        position_node = {
            value: first_position + index
            for index, value in enumerate(position_order)
        }
        first_cell = first_position + len(position_order)
        cell_node = {value: first_cell + index for index, value in enumerate(cells)}
        sink = first_cell + len(cells)
        graph: list[list[FlowEdge]] = [[] for _ in range(sink + 1)]

        def add_edge(origin: int, destination: int, capacity: int) -> int:
            forward_index = len(graph[origin])
            graph[origin].append(FlowEdge(destination, len(graph[destination]), capacity))
            graph[destination].append(FlowEdge(origin, forward_index, 0))
            return forward_index

        for source in source_order:
            add_edge(super_source, source_node[source], 1)
        handles: list[tuple[int, int, Candidate]] = []
        for candidate in sorted(
            edge_candidates.values(),
            key=lambda row: (_rank(row, seed), row.source_key, row.board.key()),
        ):
            origin = source_node[candidate.source_key]
            index = add_edge(origin, position_node[candidate.board.key()], 1)
            handles.append((origin, index, candidate))
        for position in position_order:
            add_edge(position_node[position], cell_node[position_cells[position]], 1)
        for cell in cells:
            add_edge(cell_node[cell], sink, per_cell)

        wanted = per_cell * len(cells)
        flow = 0
        while flow < wanted:
            level = [-1] * len(graph)
            level[super_source] = 0
            queue = deque([super_source])
            while queue:
                origin = queue.popleft()
                for edge in graph[origin]:
                    if edge.capacity and level[edge.to] < 0:
                        level[edge.to] = level[origin] + 1
                        queue.append(edge.to)
            if level[sink] < 0:
                break
            cursor = [0] * len(graph)

            def push(origin: int) -> bool:
                if origin == sink:
                    return True
                while cursor[origin] < len(graph[origin]):
                    edge = graph[origin][cursor[origin]]
                    if (edge.capacity and level[edge.to] == level[origin] + 1
                            and push(edge.to)):
                        edge.capacity -= 1
                        graph[edge.to][edge.reverse].capacity += 1
                        return True
                    cursor[origin] += 1
                return False

            while flow < wanted and push(super_source):
                flow += 1
        if flow != wanted:
            return None
        return [candidate for origin, index, candidate in handles
                if graph[origin][index].capacity == 0]

    # Feasibility is monotone in the equal per-cell quota.  Binary search the
    # largest exact b-matching so a short diagnostic pool remains balanced,
    # while the caller still marks it gate_ready=false below the requested N.
    low, high = 0, target
    chosen_rows: list[Candidate] = []
    per_cell = 0
    while low <= high:
        middle = (low + high) // 2
        solution = solve(middle)
        if solution is None:
            high = middle - 1
        else:
            per_cell = middle
            chosen_rows = solution
            low = middle + 1

    chosen: dict[str, list[Candidate]] = {cell: [] for cell in cells}
    for candidate in chosen_rows:
        chosen[_cell(candidate, piece_pairs)].append(candidate)
    for values in chosen.values():
        values.sort(key=lambda row: _rank(row, seed))
    selected: list[Candidate] = []
    for offset in range(per_cell):
        for cell in cells:
            selected.append(chosen[cell][offset])
    counts = {cell: per_cell for cell in cells}
    return selected, counts, target


def _candidate_rows(
    trajectories: Sequence[Trajectory], *, men_gap: int,
    max_kings: int, piece_pairs: set[tuple[int, int]],
) -> tuple[list[Candidate], Counter]:
    candidates: list[Candidate] = []
    rejected: Counter = Counter()
    for trajectory in trajectories:
        for ply, fen in enumerate(trajectory.fens):
            board = parse_fen(fen)
            ok, facts, reason = _eligible(
                board, men_gap=men_gap, max_kings=max_kings,
                piece_pairs=piece_pairs,
            )
            if not ok:
                rejected[reason] += 1
                continue
            pair = tuple(sorted((facts["white_pieces"], facts["black_pieces"])))
            candidates.append(Candidate(
                board=board, source=trajectory, ply=ply,
                advantaged=str(facts["advantaged"]),
                low_pieces=pair[0], high_pieces=pair[1],
            ))
    return candidates, rejected


def _proof_row(
    candidate: Candidate, legal: dict, piece_pairs: set[tuple[int, int]],
) -> dict:
    facts = material_facts(candidate.board)
    if isinstance(candidate.source, Trajectory):
        trajectory = candidate.source
        provenance = {
            "kind": "replayed_trajectory",
            "trajectory_file": trajectory.source_path,
            "trajectory_file_sha256": trajectory.source_sha256,
            "trajectory_row": trajectory.row_index,
            "source_game_id": trajectory.source_game_id,
            "source_opening_id": None,
            "source_record_index": None,
            "source_unit_kind": "game_id",
            "source_unit": candidate.source_key,
            "trajectory_hash": trajectory.trajectory_hash,
            "game_index": trajectory.game_index,
            "shard": trajectory.shard,
            "ply": candidate.ply,
            "logged_move_into_position": (
                trajectory.moves[candidate.ply - 1] if candidate.ply else None
            ),
            "root_fen": parse_fen(trajectory.fens[0]).fen(),
            "legal_prefix_plies_verified": candidate.ply,
            "reachability_evidence": "every prefix transition replayed with Jass",
            "source_outcome_not_used_for_selection": True,
        }
    else:
        source = candidate.source
        provenance = {
            "kind": "jnnw_jsm1_unseeded_selfplay",
            "data_file": source.data_path,
            "data_file_sha256": source.data_sha256,
            "meta_file": source.meta_path,
            "meta_file_sha256": source.meta_sha256,
            "source_record_index": source.record_index,
            "source_game_id": source.game_id,
            "source_opening_id": source.opening_id,
            "source_unit_kind": "opening_id",
            "source_unit": candidate.source_key,
            "seeded": source.seeded,
            "ply": None,
            "legal_prefix_plies_verified": None,
            "reachability_evidence": (
                "aligned JSM1 seeded=0 record emitted by standard Jass self-play"
            ),
            "source_outcome_not_used_for_selection": True,
        }
    return {
        "schema": 1,
        "position_id": candidate.position_id,
        "fen": candidate.board.fen(),
        "cell": _cell(candidate, piece_pairs),
        "material": facts,
        "stability": {
            "scope": "all_legal_first_plies_only",
            "certifies_theoretical_win": False,
            "quiet_white": True,
            "quiet_black": True,
            "immediate_promotion_white": False,
            "immediate_promotion_black": False,
            "white_legal": legal["white"],
            "black_legal": legal["black"],
            "gap_after_any_legal_first_ply": facts["value_gap"],
            "argument": "all legal first plies for both colours are quiet and non-promoting",
        },
        "provenance": provenance,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _parse_piece_pairs(values: Sequence[str] | None, men_gap: int) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for value in values or ():
        try:
            low, high = (int(part) for part in value.split(":", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"bad --piece-pair {value!r}; expected LOW:HIGH") from exc
        if low <= 0 or high <= low or high - low != men_gap:
            raise ValueError(
                f"--piece-pair {value!r} must have HIGH-LOW={men_gap}"
            )
        result.add((low, high))
    return result


def _roots(values: Sequence[str] | None) -> tuple[set[bytes], list[str]]:
    root_fens = list(values or [START_FEN])
    boards = [parse_fen(fen) for fen in root_fens]
    return {board.key() for board in boards}, [board.fen() for board in boards]


def build_pool(args: argparse.Namespace, engine: JassBatch | None = None) -> int:
    piece_pairs = _parse_piece_pairs(args.piece_pair, args.men_gap)
    cells = expected_cells(piece_pairs)
    min_positions = args.max_positions if args.min_positions is None else args.min_positions
    if min_positions <= 0 or min_positions % len(cells):
        raise ValueError(f"--min-positions must be a positive multiple of {len(cells)}")
    if min_positions > args.max_positions:
        raise ValueError("--min-positions cannot exceed --max-positions")
    engine = engine or JassBatch(args.jass, args.timeout)
    trajectory_names = list(args.trajectory or ())
    corpus_pairs = list(args.corpus or ())
    if bool(trajectory_names) == bool(corpus_pairs):
        raise ValueError("select exactly one source mode: --trajectory or --corpus DATA META")
    if trajectory_names:
        source_mode = "replayed_trajectory"
        root_keys, root_fens = _roots(args.root_fen)
        trajectories = load_trajectories(trajectory_names, root_keys)
        verified_plies: int | None = verify_legal_trajectories(trajectories, engine)
        raw_candidates, filter_rejected = _candidate_rows(
            trajectories, men_gap=args.men_gap, max_kings=args.max_kings,
            piece_pairs=piece_pairs,
        )
        inputs = [{
            "path": name, "sha256": _sha256_file(Path(name)),
        } for name in trajectory_names]
        source_records = sum(len(row.fens) for row in trajectories)
    else:
        source_mode = "jnnw_jsm1_unseeded_selfplay"
        root_fens = []
        trajectories = []
        verified_plies = None
        raw_candidates, filter_rejected, inputs = load_corpus_candidates(
            corpus_pairs, men_gap=args.men_gap, max_kings=args.max_kings,
            piece_pairs=piece_pairs,
        )
        source_records = sum(row["records"] for row in inputs)
    stable, legal_evidence, stability_rejected = audit_stability(raw_candidates, engine)
    selected, cell_counts, target_per_cell = select_balanced(
        stable, piece_pairs=piece_pairs, max_positions=args.max_positions,
        seed=args.seed,
    )
    proofs = [_proof_row(row, legal_evidence[row.position_id], piece_pairs)
              for row in selected]

    out_pool = Path(args.out_pool)
    out_proof = Path(args.out_proof)
    out_pool.parent.mkdir(parents=True, exist_ok=True)
    out_proof.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# stable_conversion_pool schema=1 positions={len(selected)} "
        f"men_gap={args.men_gap} max_kings={args.max_kings} "
        "reachable=true quiet_both=true immediate_promotion=false\n"
    )
    with out_pool.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(header)
        for proof in proofs:
            source = proof["provenance"]
            unit = (f"opening={source['source_opening_id']}"
                    if source["source_opening_id"] is not None
                    else f"game={source['source_game_id']}")
            location = (f"record={source['source_record_index']}"
                        if source["source_record_index"] is not None
                        else f"ply={source['ply']}")
            handle.write(
                f"{proof['fen']}  # id={proof['position_id'][:16]} "
                f"cell={proof['cell']} {unit} {location}\n"
            )
    with out_proof.open("w", encoding="utf-8", newline="\n") as handle:
        for proof in proofs:
            handle.write(json.dumps(proof, sort_keys=True, ensure_ascii=False) + "\n")

    gate_ready = len(selected) >= min_positions
    manifest = {
        "schema": 1,
        "operation": "build_stable_conversion_pool",
        "gate_ready": gate_ready,
        "invariants": {
            "source_mode": source_mode,
            "stability_scope": "all_legal_first_plies_only",
            "certifies_theoretical_win": False,
            "legal_prefix_replayed": source_mode == "replayed_trajectory",
            "standard_selfplay_jsm1_seeded_zero": (
                source_mode == "jnnw_jsm1_unseeded_selfplay"
            ),
            "allowed_roots": root_fens,
            "exact_men_gap": args.men_gap,
            "equal_king_counts": True,
            "max_total_kings": args.max_kings,
            "exact_value_gap": args.men_gap,
            "quiet_for_both_colours": True,
            "no_immediate_promotion_for_either_colour": True,
            "one_position_per_source_unit": True,
            "source_unit": "opening_id" if corpus_pairs else "game_id",
            "balanced_advantaged_colour_and_stm": True,
            "outcome_used_for_selection": False,
        },
        "configuration": {
            "piece_pairs": [list(pair) for pair in sorted(piece_pairs)],
            "max_positions": args.max_positions,
            "min_positions": min_positions,
            "seed": args.seed,
        },
        "inputs": inputs,
        "source_mode": source_mode,
        "source_records": source_records,
        "trajectory_games": len(trajectories) if trajectories else None,
        "trajectory_plies_verified": verified_plies,
        "material_candidates": len(raw_candidates),
        "stable_candidates": len(stable),
        "selected_positions": len(selected),
        "selected_source_units": len({row.source_key for row in selected}),
        "selected_source_games": (
            len({row.source_key for row in selected}) if trajectories else None
        ),
        "selected_opening_ids": (
            len({row.source_key for row in selected}) if corpus_pairs else None
        ),
        "target_per_cell": target_per_cell,
        "selected_cells": cell_counts,
        "rejected_material": dict(sorted(filter_rejected.items())),
        "rejected_stability": dict(sorted(stability_rejected.items())),
        "outputs": {
            "pool": str(out_pool),
            "pool_sha256": hashlib.sha256(out_pool.read_bytes()).hexdigest(),
            "proof": str(out_proof),
            "proof_sha256": hashlib.sha256(out_proof.read_bytes()).hexdigest(),
        },
    }
    _write_json(Path(args.manifest), manifest)
    print(json.dumps(manifest, sort_keys=True, ensure_ascii=False))
    return 0 if gate_ready else 2


def _load_pool(path: Path) -> list[str]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fen = line.split("#", 1)[0].strip()
        if fen:
            result.append(fen)
    return result


def _load_proofs(path: Path) -> list[dict]:
    result = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or row.get("schema") != 1:
            raise ValueError(f"{path}:{line_number}: bad proof schema")
        result.append(row)
    return result


def audit_pool(args: argparse.Namespace, engine: JassBatch | None = None) -> int:
    piece_pairs = _parse_piece_pairs(args.piece_pair, args.men_gap)
    pool_path, proof_path = Path(args.pool), Path(args.proof)
    fens, proofs = _load_pool(pool_path), _load_proofs(proof_path)
    if len(fens) != len(proofs) or not fens:
        raise ValueError("pool/proof count mismatch or empty pool")

    trajectory_names = list(args.trajectory or ())
    corpus_pairs = list(args.corpus or ())
    engine = engine or JassBatch(args.jass, args.timeout)
    if trajectory_names:
        source_mode = "replayed_trajectory"
        root_keys, root_fens = _roots(args.root_fen)
        trajectories = load_trajectories(trajectory_names, root_keys)
        by_source = {row.source_key: row for row in trajectories}
        corpus_by_record: dict[tuple[str, str, int], Candidate] = {}
        source_inputs = [{"path": name, "sha256": _sha256_file(Path(name))}
                         for name in trajectory_names]
    else:
        source_mode = "jnnw_jsm1_unseeded_selfplay"
        root_fens = []
        trajectories = []
        by_source = {}
        corpus_candidates, _, source_inputs = load_corpus_candidates(
            corpus_pairs, men_gap=args.men_gap, max_kings=args.max_kings,
            piece_pairs=piece_pairs,
        )
        corpus_by_record = {}
        for candidate in corpus_candidates:
            assert isinstance(candidate.source, CorpusSource)
            source = candidate.source
            key = (source.data_sha256, source.meta_sha256, source.record_index)
            if key in corpus_by_record:
                raise ValueError(f"duplicate corpus record provenance: {key}")
            corpus_by_record[key] = candidate

    selected: list[Candidate] = []
    proof_by_position: dict[str, dict] = {}
    referenced: dict[str, Trajectory] = {}
    for index, (fen, proof) in enumerate(zip(fens, proofs)):
        board = parse_fen(fen)
        position_id = hashlib.sha256(board.key()).hexdigest()
        if proof.get("position_id") != position_id or parse_fen(str(proof.get("fen"))).key() != board.key():
            raise ValueError(f"proof/FEN mismatch at pool row {index}")
        provenance = proof.get("provenance") or {}
        if source_mode == "replayed_trajectory":
            if provenance.get("kind") != source_mode:
                raise ValueError(f"proof row {index} source mode mismatch")
            source_key = (
                f"{provenance.get('trajectory_file_sha256')}:"
                f"{provenance.get('source_game_id')}"
            )
            trajectory = by_source.get(source_key)
            if trajectory is None:
                raise ValueError(f"proof row {index} references an absent source trajectory")
            ply = int(provenance.get("ply", -1))
            if not 0 <= ply < len(trajectory.fens):
                raise ValueError(f"proof row {index} has invalid source ply")
            if parse_fen(trajectory.fens[ply]).key() != board.key():
                raise ValueError(f"proof row {index} does not match its source ply")
            if provenance.get("trajectory_hash") != trajectory.trajectory_hash:
                raise ValueError(f"proof row {index} trajectory hash mismatch")
            source: Trajectory | CorpusSource = trajectory
            referenced[source_key] = trajectory
        else:
            if provenance.get("kind") != source_mode:
                raise ValueError(f"proof row {index} source mode mismatch")
            try:
                record_key = (
                    str(provenance["data_file_sha256"]),
                    str(provenance["meta_file_sha256"]),
                    int(provenance["source_record_index"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"proof row {index} has incomplete corpus provenance") from exc
            source_candidate = corpus_by_record.get(record_key)
            if source_candidate is None:
                raise ValueError(f"proof row {index} references an absent corpus record")
            if source_candidate.board.key() != board.key():
                raise ValueError(f"proof row {index} differs from source record bytes")
            assert isinstance(source_candidate.source, CorpusSource)
            source = source_candidate.source
            if (provenance.get("source_game_id") != source.game_id
                    or provenance.get("source_opening_id") != source.opening_id
                    or provenance.get("seeded") != 0):
                raise ValueError(f"proof row {index} JSM1 metadata mismatch")
            ply = -1
        ok, facts, reason = _eligible(
            board, men_gap=args.men_gap, max_kings=args.max_kings,
            piece_pairs=piece_pairs,
        )
        if not ok:
            raise ValueError(f"proof row {index} fails material invariant: {reason}")
        pair = tuple(sorted((facts["white_pieces"], facts["black_pieces"])))
        candidate = Candidate(
            board, source, ply, str(facts["advantaged"]), pair[0], pair[1]
        )
        if proof.get("cell") != _cell(candidate, piece_pairs):
            raise ValueError(f"proof row {index} cell mismatch")
        if proof.get("material") != facts:
            raise ValueError(f"proof row {index} material evidence mismatch")
        if provenance.get("source_unit") != candidate.source_key:
            raise ValueError(f"proof row {index} source-unit mismatch")
        expected_unit_kind = "game_id" if trajectories else "opening_id"
        if provenance.get("source_unit_kind") != expected_unit_kind:
            raise ValueError(f"proof row {index} source-unit kind mismatch")
        if provenance.get("source_outcome_not_used_for_selection") is not True:
            raise ValueError(f"proof row {index} outcome-selection claim missing")
        selected.append(candidate)
        proof_by_position[position_id] = proof

    if len({row.board.key() for row in selected}) != len(selected):
        raise ValueError("duplicate position in pool")
    if len({row.source_key for row in selected}) != len(selected):
        raise ValueError("more than one selected position from a source unit")

    if trajectories:
        # Recheck only the required source prefixes, independently of the
        # proof's claimed count.  Trimming cannot create a false transition.
        prefixes = []
        for source_key, trajectory in referenced.items():
            max_ply = max(row.ply for row in selected if row.source_key == source_key)
            prefixes.append(Trajectory(
                **{**trajectory.__dict__,
                   "fens": trajectory.fens[:max_ply + 1],
                   "moves": trajectory.moves[:max_ply]}
            ))
        verified_plies: int | None = verify_legal_trajectories(prefixes, engine)
    else:
        verified_plies = None
    stable, evidence, rejected = audit_stability(selected, engine)
    if len(stable) != len(selected) or rejected:
        raise ValueError(f"pool is no longer stable: {dict(rejected)}")

    cells = expected_cells(piece_pairs)
    counts = Counter(_cell(row, piece_pairs) for row in selected)
    if set(counts) != set(cells) or len(set(counts.values())) != 1:
        raise ValueError(f"pool is not exactly balanced: {dict(counts)}")
    for candidate in selected:
        proof = proof_by_position[candidate.position_id]
        claimed = proof.get("stability") or {}
        if (
            claimed.get("scope") != "all_legal_first_plies_only"
            or claimed.get("certifies_theoretical_win") is not False
            or claimed.get("gap_after_any_legal_first_ply") != args.men_gap
        ):
            raise ValueError("one-ply material-stability claim mismatch")
        if claimed.get("white_legal") != evidence[candidate.position_id]["white"]:
            raise ValueError("white legal-move proof mismatch")
        if claimed.get("black_legal") != evidence[candidate.position_id]["black"]:
            raise ValueError("black legal-move proof mismatch")

    manifest = {
        "schema": 1,
        "operation": "audit_stable_conversion_pool",
        "audit_pass": True,
        "pool": str(pool_path),
        "pool_sha256": hashlib.sha256(pool_path.read_bytes()).hexdigest(),
        "proof": str(proof_path),
        "proof_sha256": hashlib.sha256(proof_path.read_bytes()).hexdigest(),
        "positions": len(selected),
        "source_mode": source_mode,
        "source_units": len({row.source_key for row in selected}),
        "source_games": len(referenced) if trajectories else None,
        "source_opening_ids": len({row.source_key for row in selected}) if corpus_pairs else None,
        "source_inputs": source_inputs,
        "source_prefix_plies_reverified": verified_plies,
        "allowed_roots": root_fens,
        "cells": dict(sorted(counts.items())),
        "material_gap": args.men_gap,
        "stability_scope": "all_legal_first_plies_only",
        "certifies_theoretical_win": False,
        "quiet_for_both_colours": True,
        "no_immediate_promotion_for_either_colour": True,
        "legal_prefix_replayed": bool(trajectories),
        "standard_selfplay_jsm1_seeded_zero": bool(corpus_pairs),
    }
    _write_json(Path(args.manifest), manifest)
    print(json.dumps(manifest, sort_keys=True, ensure_ascii=False))
    return 0


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--jass", required=True, help="Jass binary with --dump-legal/--dump-children")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--trajectory", action="append",
                        help="replayable schema-1 trajectory JSONL(.gz); repeatable")
    source.add_argument("--corpus", nargs=2, action="append", metavar=("JNNW", "JSM1"),
                        help="aligned standard-only self-play pair; repeatable, gzip accepted")
    parser.add_argument("--root-fen", action="append",
                        help=f"allowed legal root; default is the initial position {START_FEN}")
    parser.add_argument("--men-gap", type=int, default=2)
    parser.add_argument("--max-kings", type=int, default=0,
                        help="maximum total kings; 0 reproduces the all-men TOP3 domain")
    parser.add_argument("--piece-pair", action="append",
                        help="balanced total-piece stratum LOW:HIGH; repeatable")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="seconds allowed per batch Jass audit command")
    parser.add_argument("--manifest", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build a balanced stable +2 pool")
    _common(build)
    build.add_argument("--max-positions", type=int, default=384)
    build.add_argument("--min-positions", type=int,
                       help="gate-ready floor; default requires --max-positions exactly")
    build.add_argument("--seed", type=int, default=1)
    build.add_argument("--out-pool", required=True)
    build.add_argument("--out-proof", required=True)
    build.set_defaults(func=build_pool)

    audit = sub.add_parser("audit", help="independently re-audit pool and proofs")
    _common(audit)
    audit.add_argument("--pool", required=True)
    audit.add_argument("--proof", required=True)
    audit.set_defaults(func=audit_pool)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
