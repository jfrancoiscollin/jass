#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build the deterministic, data-only L3 blind-spot atlas v1.

The atlas consumes one aligned JNNW/JSM1 self-play corpus.  It deliberately
uses only facts available in those two formats: board geometry, material,
side-to-move, terminal WDL, game/opening identity and the seeded flag.

Outputs are diagnostics, never gates.  Metrics that need provenance-bearing
sidecars (capture/quiet state, mobility, model disagreement, depth instability
and terminal surprise) are explicitly listed as future extensions instead of
being guessed from the base files.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import os
import re
import struct
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


JNNW_MAGIC = b"JNNW"
JNNW_RECORD_SIZE = 38
JSM1_MAGIC = b"JSM1"
JSM1_RECORD_SIZE = 17
JNNW_RECORD = struct.Struct("<QQQQBib")
JSM1_RECORD = struct.Struct("<QQB")

ATLAS_SCHEMA = "l3_blind_spot_atlas"
ATLAS_SCHEMA_VERSION = 1
CSV_SCHEMA = "l3_blind_spot_atlas_long"
CSV_SCHEMA_VERSION = 1
TAXONOMY_SCHEMA = "l3_objective_taxonomy_v1"
PROBE_SCHEMA = "l3_fixed_position_probe_v1"
PROBE_SELECTION = "bottom_k_sha256_unique_position_v1"
PROBE_DOMAIN = b"JASS-L3-BLIND-SPOT-PROBE-V1\x00"

BOARD_MASK = (1 << 50) - 1
BLACK_HALF_MASK = (1 << 25) - 1
WHITE_HALF_MASK = BOARD_MASK ^ BLACK_HALF_MASK
WHITE_PROMOTION_MASK = (1 << 5) - 1
BLACK_PROMOTION_MASK = WHITE_PROMOTION_MASK << 45

CODE_SHA_RE = re.compile(r"[0-9a-f]{40}")


TAXONOMY_DEFINITIONS = {
    "camp_penetration": {
        "basis": (
            "white piece on rows 0..4 and/or black piece on rows 5..9; "
            "half-board occupancy only, not a positional evaluation"
        ),
        "buckets": ["none", "white_only", "black_only", "both"],
    },
    "king_configuration": {
        "basis": "presence of white and black kings",
        "buckets": [
            "no_kings",
            "white_kings_only",
            "black_kings_only",
            "both_sides_kings",
        ],
    },
    "material_leader": {
        "basis": "men=1, kings=3; colour with greater weighted material",
        "buckets": ["white", "black", "equal"],
    },
    "material_stratum": {
        "basis": "absolute weighted-material margin with men=1 and kings=3",
        "buckets": ["p4_equal", "p3_thin", "p2_medium", "p1_clear"],
        "thresholds": {
            "p4_equal": "margin=0",
            "p3_thin": "margin=1",
            "p2_medium": "margin=2..3",
            "p1_clear": "margin>=4",
        },
    },
    "nearest_promotion_distance": {
        "basis": (
            "minimum geometric row distance of any man to its promotion row; "
            "ignores legality, captures and tempo"
        ),
        "buckets": ["no_men", "distance_1", "distance_2", "distance_3_4", "distance_5_plus"],
    },
    "phase": {
        "basis": "total men plus kings on board",
        "buckets": ["opening", "midgame", "late_midgame", "endgame", "deep_endgame"],
        "thresholds": {
            "opening": "pieces>=30",
            "midgame": "22<=pieces<=29",
            "late_midgame": "15<=pieces<=21",
            "endgame": "8<=pieces<=14",
            "deep_endgame": "pieces<=7",
        },
    },
    "promotion_race": {
        "basis": (
            "comparison of each colour's nearest geometric man-to-promotion "
            "row distance; ignores legality, captures and tempo"
        ),
        "buckets": [
            "no_men",
            "white_only",
            "black_only",
            "tied",
            "white_closer",
            "black_closer",
        ],
    },
    "side_to_move": {
        "basis": "JNNW side-to-move byte",
        "buckets": ["white", "black"],
    },
    "source": {
        "basis": "JSM1 seeded byte",
        "buckets": ["standard", "frontier"],
    },
    "stm_material_status": {
        "basis": "side-to-move weighted material relative to the opponent; men=1, kings=3",
        "buckets": ["ahead", "equal", "behind"],
    },
}

EXTENSIONS_NOT_IN_V1 = [
    {
        "metric": "capture_state",
        "required_input": "aligned versioned QIET/legal-move sidecar",
        "reason": "mandatory-capture versus quiet cannot be inferred safely from JNNW/JSM1",
    },
    {
        "metric": "depth_instability",
        "required_input": "two aligned search-score sidecars with pinned depths and search config",
        "reason": "the base score has no paired depth provenance",
    },
    {
        "metric": "mobility",
        "required_input": "aligned versioned FEAT or legal-move sidecar",
        "reason": "mobility requires move generation or an explicit feature producer",
    },
    {
        "metric": "model_disagreement",
        "required_input": "two aligned static-evaluation sidecars with model hashes",
        "reason": "one unprovenanced JNNW score cannot establish disagreement",
    },
    {
        "metric": "terminal_surprise",
        "required_input": (
            "aligned score sidecar with model/search provenance and a frozen definition"
        ),
        "reason": "the base score field may come from different generation protocols",
    },
]

CSV_FIELDS = [
    "schema",
    "schema_version",
    "diagnostic_only",
    "gate_authorized",
    "dimension",
    "bucket",
    "records",
    "record_share",
    "games",
    "game_share",
    "openings",
    "opening_share",
    "wdl_stm_win_records",
    "wdl_stm_draw_records",
    "wdl_stm_loss_records",
    "wdl_stm_win_rate",
    "wdl_stm_draw_rate",
    "wdl_stm_loss_rate",
    "terminal_white_win_records",
    "terminal_draw_records",
    "terminal_black_win_records",
    "conversion_eligible_records",
    "conversion_converted_records",
    "conversion_drawn_records",
    "conversion_reversed_records",
    "conversion_rate",
]


@dataclass
class BucketStats:
    records: int = 0
    games: set[int] = field(default_factory=set)
    openings: set[int] = field(default_factory=set)
    wdl_stm: Counter[str] = field(default_factory=Counter)
    terminal_winner: Counter[str] = field(default_factory=Counter)
    conversion_eligible: int = 0
    conversion_converted: int = 0
    conversion_drawn: int = 0
    conversion_reversed: int = 0


class BottomKProbe:
    """Order-independent bottom-k sample over unique 33-byte positions."""

    def __init__(self, size: int, seed: int):
        self.size = size
        self.seed = seed
        self._rows: list[tuple[bytes, bytes]] = []
        self._positions: set[bytes] = set()
        self._seed_bytes = struct.pack("<Q", seed)

    def offer(self, position: bytes) -> None:
        if position in self._positions:
            return
        selection_hash = hashlib.sha256(
            PROBE_DOMAIN + self._seed_bytes + position
        ).digest()
        row = (selection_hash, position)
        if len(self._rows) < self.size:
            bisect.insort(self._rows, row)
            self._positions.add(position)
            return
        if row >= self._rows[-1]:
            return
        removed = self._rows.pop()
        self._positions.remove(removed[1])
        bisect.insort(self._rows, row)
        self._positions.add(position)

    def payload(self) -> dict:
        entries = []
        digest = hashlib.sha256()
        digest.update(PROBE_DOMAIN)
        digest.update(struct.pack("<IQI", 1, self.seed, len(self._rows)))
        for selection_hash, position in self._rows:
            digest.update(position)
            entries.append({
                "board_tags": _board_tags(position),
                "position_hex": position.hex(),
                "position_sha256": hashlib.sha256(position).hexdigest(),
                "selection_sha256": selection_hash.hex(),
            })
        return {
            "schema": PROBE_SCHEMA,
            "schema_version": 1,
            "selection": PROBE_SELECTION,
            "seed": self.seed,
            "requested_positions": self.size,
            "selected_positions": len(entries),
            "probe_sha256": digest.hexdigest(),
            "entries": entries,
        }


def _iter_bits(bitboard: int):
    while bitboard:
        lsb = bitboard & -bitboard
        yield lsb.bit_length() - 1
        bitboard ^= lsb


def _promotion_distance(men: int, *, white: bool) -> int | None:
    distances = [
        square // 5 if white else 9 - (square // 5)
        for square in _iter_bits(men)
    ]
    return min(distances) if distances else None


def _phase(pieces: int) -> str:
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


def _distance_bucket(distance: int | None) -> str:
    if distance is None:
        return "no_men"
    if distance == 1:
        return "distance_1"
    if distance == 2:
        return "distance_2"
    if distance <= 4:
        return "distance_3_4"
    return "distance_5_plus"


def _board_tags(position: bytes) -> dict[str, str]:
    if len(position) != 33:
        raise ValueError(f"position size {len(position)} != 33")
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", position, 0)
    stm = position[32]
    white_count = wm.bit_count() + wk.bit_count()
    black_count = bm.bit_count() + bk.bit_count()
    white_material = wm.bit_count() + 3 * wk.bit_count()
    black_material = bm.bit_count() + 3 * bk.bit_count()
    margin = abs(white_material - black_material)

    if white_material > black_material:
        leader = "white"
    elif black_material > white_material:
        leader = "black"
    else:
        leader = "equal"

    stm_material = white_material if stm == 0 else black_material
    opponent_material = black_material if stm == 0 else white_material
    if stm_material > opponent_material:
        stm_status = "ahead"
    elif stm_material < opponent_material:
        stm_status = "behind"
    else:
        stm_status = "equal"

    if wk and bk:
        kings = "both_sides_kings"
    elif wk:
        kings = "white_kings_only"
    elif bk:
        kings = "black_kings_only"
    else:
        kings = "no_kings"

    white_distance = _promotion_distance(wm, white=True)
    black_distance = _promotion_distance(bm, white=False)
    available_distances = [
        distance for distance in (white_distance, black_distance)
        if distance is not None
    ]
    nearest_distance = min(available_distances) if available_distances else None
    if white_distance is None and black_distance is None:
        race = "no_men"
    elif black_distance is None:
        race = "white_only"
    elif white_distance is None:
        race = "black_only"
    elif white_distance < black_distance:
        race = "white_closer"
    elif black_distance < white_distance:
        race = "black_closer"
    else:
        race = "tied"

    white_penetrates = bool((wm | wk) & BLACK_HALF_MASK)
    black_penetrates = bool((bm | bk) & WHITE_HALF_MASK)
    if white_penetrates and black_penetrates:
        penetration = "both"
    elif white_penetrates:
        penetration = "white_only"
    elif black_penetrates:
        penetration = "black_only"
    else:
        penetration = "none"

    return {
        "camp_penetration": penetration,
        "king_configuration": kings,
        "material_leader": leader,
        "material_stratum": _material_stratum(margin),
        "nearest_promotion_distance": _distance_bucket(nearest_distance),
        "phase": _phase(white_count + black_count),
        "promotion_race": race,
        "side_to_move": "white" if stm == 0 else "black",
        "stm_material_status": stm_status,
    }


def _validate_record(record: bytes, index: int) -> tuple[bytes, int]:
    if len(record) != JNNW_RECORD_SIZE:
        raise ValueError(f"JNNW record {index}: size {len(record)} != {JNNW_RECORD_SIZE}")
    wm, wk, bm, bk, stm, _score, wdl = JNNW_RECORD.unpack(record)
    bitboards = {
        "white_men": wm,
        "white_kings": wk,
        "black_men": bm,
        "black_kings": bk,
    }
    for name, bitboard in bitboards.items():
        if bitboard & ~BOARD_MASK:
            raise ValueError(f"JNNW record {index}: {name} has bits outside squares 1..50")
    occupancy = 0
    for name, bitboard in bitboards.items():
        if occupancy & bitboard:
            raise ValueError(f"JNNW record {index}: overlapping bitboard at {name}")
        occupancy |= bitboard
    if wm & WHITE_PROMOTION_MASK:
        raise ValueError(f"JNNW record {index}: white man on white promotion row")
    if bm & BLACK_PROMOTION_MASK:
        raise ValueError(f"JNNW record {index}: black man on black promotion row")
    if stm not in (0, 1):
        raise ValueError(f"JNNW record {index}: side-to-move {stm} outside {{0,1}}")
    if wdl not in (-1, 0, 1):
        raise ValueError(f"JNNW record {index}: WDL {wdl} outside {{-1,0,1}}")
    return record[:33], wdl


def _terminal_winner(stm: int, wdl: int) -> str:
    if wdl == 0:
        return "draw"
    stm_colour = "white" if stm == 0 else "black"
    if wdl > 0:
        return stm_colour
    return "black" if stm_colour == "white" else "white"


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 12)


def _canonical_json(value: object, *, pretty: bool) -> bytes:
    if pretty:
        text = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)
    else:
        text = json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    return (text + "\n").encode("utf-8")


def _input_header(
    handle,
    path: Path,
    expected_magic: bytes,
    record_size: int,
) -> tuple[int, bytes, tuple[int, int]]:
    header = handle.read(8)
    if len(header) != 8 or header[:4] != expected_magic:
        raise ValueError(f"{path}: expected {expected_magic.decode('ascii')} header")
    count = struct.unpack_from("<I", header, 4)[0]
    expected_size = 8 + count * record_size
    stat = os.fstat(handle.fileno())
    if stat.st_size != expected_size:
        raise ValueError(
            f"{path}: size {stat.st_size} != {expected_size} for {count} records"
        )
    return count, header, (stat.st_size, stat.st_mtime_ns)


def _ensure_unchanged(handle, path: Path, initial: tuple[int, int]) -> None:
    final_stat = os.fstat(handle.fileno())
    final = (final_stat.st_size, final_stat.st_mtime_ns)
    if final != initial:
        raise ValueError(f"{path}: input changed while atlas was reading it")


def _empty_stats() -> dict[tuple[str, str], BucketStats]:
    return {
        (dimension, bucket): BucketStats()
        for dimension, definition in TAXONOMY_DEFINITIONS.items()
        for bucket in definition["buckets"]
    }


def _validate_tags(tags: dict[str, str], index: int) -> None:
    if set(tags) != set(TAXONOMY_DEFINITIONS):
        raise RuntimeError(f"record {index}: internal taxonomy dimension mismatch")
    for dimension, bucket in tags.items():
        if bucket not in TAXONOMY_DEFINITIONS[dimension]["buckets"]:
            raise RuntimeError(
                f"record {index}: internal unknown bucket {dimension}={bucket}"
            )


def _atlas_rows(
    stats: dict[tuple[str, str], BucketStats],
    records: int,
    games: int,
    openings: int,
) -> list[dict]:
    rows = []
    for dimension, bucket in sorted(stats):
        item = stats[(dimension, bucket)]
        win = item.wdl_stm["win"]
        draw = item.wdl_stm["draw"]
        loss = item.wdl_stm["loss"]
        rows.append({
            "bucket": bucket,
            "conversion": {
                "converted_records": item.conversion_converted,
                "drawn_records": item.conversion_drawn,
                "eligible_records": item.conversion_eligible,
                "rate": _ratio(item.conversion_converted, item.conversion_eligible),
                "reversed_records": item.conversion_reversed,
            },
            "dimension": dimension,
            "game_share": _ratio(len(item.games), games),
            "games": len(item.games),
            "opening_share": _ratio(len(item.openings), openings),
            "openings": len(item.openings),
            "record_share": _ratio(item.records, records),
            "records": item.records,
            "terminal_winner_records": {
                "black": item.terminal_winner["black"],
                "draw": item.terminal_winner["draw"],
                "white": item.terminal_winner["white"],
            },
            "wdl_stm_rates": {
                "draw": _ratio(draw, item.records),
                "loss": _ratio(loss, item.records),
                "win": _ratio(win, item.records),
            },
            "wdl_stm_records": {
                "draw": draw,
                "loss": loss,
                "win": win,
            },
        })
    return rows


def _csv_bytes(rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=CSV_FIELDS,
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    for row in rows:
        wdl = row["wdl_stm_records"]
        wdl_rates = row["wdl_stm_rates"]
        winners = row["terminal_winner_records"]
        conversion = row["conversion"]
        writer.writerow({
            "schema": CSV_SCHEMA,
            "schema_version": CSV_SCHEMA_VERSION,
            "diagnostic_only": "true",
            "gate_authorized": "false",
            "dimension": row["dimension"],
            "bucket": row["bucket"],
            "records": row["records"],
            "record_share": _csv_rate(row["record_share"]),
            "games": row["games"],
            "game_share": _csv_rate(row["game_share"]),
            "openings": row["openings"],
            "opening_share": _csv_rate(row["opening_share"]),
            "wdl_stm_win_records": wdl["win"],
            "wdl_stm_draw_records": wdl["draw"],
            "wdl_stm_loss_records": wdl["loss"],
            "wdl_stm_win_rate": _csv_rate(wdl_rates["win"]),
            "wdl_stm_draw_rate": _csv_rate(wdl_rates["draw"]),
            "wdl_stm_loss_rate": _csv_rate(wdl_rates["loss"]),
            "terminal_white_win_records": winners["white"],
            "terminal_draw_records": winners["draw"],
            "terminal_black_win_records": winners["black"],
            "conversion_eligible_records": conversion["eligible_records"],
            "conversion_converted_records": conversion["converted_records"],
            "conversion_drawn_records": conversion["drawn_records"],
            "conversion_reversed_records": conversion["reversed_records"],
            "conversion_rate": _csv_rate(conversion["rate"]),
        })
    return stream.getvalue().encode("utf-8")


def _csv_rate(value: float | None) -> str:
    return "" if value is None else f"{value:.12f}"


def build_atlas(
    data_path: Path,
    meta_path: Path,
    *,
    code_sha: str,
    probe_size: int,
    probe_seed: int,
) -> tuple[dict, bytes]:
    stats = _empty_stats()
    games: dict[int, tuple[int, int]] = {}
    openings: set[int] = set()
    probe = BottomKProbe(probe_size, probe_seed)
    data_hash = hashlib.sha256()
    meta_hash = hashlib.sha256()

    with data_path.open("rb") as data_handle, meta_path.open("rb") as meta_handle:
        data_count, data_header, data_stat = _input_header(
            data_handle, data_path, JNNW_MAGIC, JNNW_RECORD_SIZE
        )
        meta_count, meta_header, meta_stat = _input_header(
            meta_handle, meta_path, JSM1_MAGIC, JSM1_RECORD_SIZE
        )
        if data_count != meta_count:
            raise ValueError(f"data/meta count mismatch: {data_count} != {meta_count}")
        if data_count == 0:
            raise ValueError("refusing to build an atlas from zero records")
        data_hash.update(data_header)
        meta_hash.update(meta_header)

        for index in range(data_count):
            record = data_handle.read(JNNW_RECORD_SIZE)
            meta_raw = meta_handle.read(JSM1_RECORD_SIZE)
            if len(record) != JNNW_RECORD_SIZE or len(meta_raw) != JSM1_RECORD_SIZE:
                raise ValueError(f"aligned pair truncated at record {index}")
            data_hash.update(record)
            meta_hash.update(meta_raw)
            position, wdl = _validate_record(record, index)
            game_id, opening_id, seeded = JSM1_RECORD.unpack(meta_raw)
            if seeded not in (0, 1):
                raise ValueError(
                    f"JSM1 record {index}: seeded {seeded} outside {{0,1}}"
                )

            stm = position[32]
            winner = _terminal_winner(stm, wdl)
            game_contract = (opening_id, seeded)
            previous = games.get(game_id)
            if previous is None:
                games[game_id] = game_contract
            elif previous != game_contract:
                raise ValueError(
                    f"game_id {game_id}: inconsistent opening/seeded metadata "
                    f"{previous!r} != {game_contract!r} at record {index}"
                )
            openings.add(opening_id)

            tags = _board_tags(position)
            tags["source"] = "frontier" if seeded else "standard"
            _validate_tags(tags, index)
            leader = tags["material_leader"]
            wdl_label = {1: "win", 0: "draw", -1: "loss"}[wdl]
            for dimension, bucket in tags.items():
                item = stats[(dimension, bucket)]
                item.records += 1
                item.games.add(game_id)
                item.openings.add(opening_id)
                item.wdl_stm[wdl_label] += 1
                item.terminal_winner[winner] += 1
                if leader != "equal":
                    item.conversion_eligible += 1
                    if winner == leader:
                        item.conversion_converted += 1
                    elif winner == "draw":
                        item.conversion_drawn += 1
                    else:
                        item.conversion_reversed += 1
            probe.offer(position)

        if data_handle.read(1) or meta_handle.read(1):
            raise ValueError("unexpected trailing bytes after aligned pair")
        _ensure_unchanged(data_handle, data_path, data_stat)
        _ensure_unchanged(meta_handle, meta_path, meta_stat)

    rows = _atlas_rows(stats, data_count, len(games), len(openings))
    csv_payload = _csv_bytes(rows)
    taxonomy_payload = {
        "definitions": TAXONOMY_DEFINITIONS,
        "schema": TAXONOMY_SCHEMA,
        "schema_version": 1,
    }
    taxonomy_sha256 = hashlib.sha256(
        _canonical_json(taxonomy_payload, pretty=False)
    ).hexdigest()
    report = {
        "atlas": rows,
        "automatic_continuation_authorized": False,
        "code_sha": code_sha,
        "decision": "diagnostic_only_no_gate",
        "diagnostic_only": True,
        "external_teacher_inputs": 0,
        "extensions_not_in_v1": EXTENSIONS_NOT_IN_V1,
        "gate_authorized": False,
        "input": {
            "data": {
                "bytes": 8 + data_count * JNNW_RECORD_SIZE,
                "magic": JNNW_MAGIC.decode("ascii"),
                "record_size": JNNW_RECORD_SIZE,
                "sha256": data_hash.hexdigest(),
            },
            "meta": {
                "bytes": 8 + data_count * JSM1_RECORD_SIZE,
                "magic": JSM1_MAGIC.decode("ascii"),
                "record_size": JSM1_RECORD_SIZE,
                "sha256": meta_hash.hexdigest(),
            },
        },
        "operation": "objective_blind_spot_atlas",
        "openings": len(openings),
        "outputs": {
            "csv_schema": CSV_SCHEMA,
            "csv_schema_version": CSV_SCHEMA_VERSION,
            "csv_sha256": hashlib.sha256(csv_payload).hexdigest(),
        },
        "probe": probe.payload(),
        "promotion_authorized": False,
        "records": data_count,
        "schema": ATLAS_SCHEMA,
        "schema_version": ATLAS_SCHEMA_VERSION,
        "score_field_policy": "ignored_without_explicit_provenance",
        "taxonomy": {
            **taxonomy_payload,
            "taxonomy_sha256": taxonomy_sha256,
        },
        "units": {
            "conversion": "correlated_position_record_material_leader_not_gate",
            "games": "unique_JSM1_game_id_per_bucket",
            "openings": "unique_JSM1_opening_id_per_bucket",
            "records": "correlated_position_record_not_gate",
            "wdl": "JNNW_side_to_move_record_not_gate",
        },
        "games": len(games),
    }
    return report, csv_payload


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _stage(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _publish_pair_no_clobber(
    json_path: Path,
    json_payload: bytes,
    csv_path: Path,
    csv_payload: bytes,
) -> None:
    if _lexists(json_path):
        raise ValueError(f"refusing to overwrite existing output: {json_path}")
    if _lexists(csv_path):
        raise ValueError(f"refusing to overwrite existing output: {csv_path}")
    staged: list[tuple[Path, Path]] = []
    published: list[tuple[Path, Path]] = []
    complete = False
    try:
        staged.append((_stage(json_path, json_payload), json_path))
        staged.append((_stage(csv_path, csv_payload), csv_path))
        for temporary, destination in staged:
            if _lexists(destination):
                raise ValueError(
                    f"refusing to overwrite output created concurrently: {destination}"
                )
            os.link(temporary, destination)
            published.append((temporary, destination))
        complete = True
    except BaseException:
        for temporary, destination in reversed(published):
            try:
                if _lexists(destination) and os.path.samefile(temporary, destination):
                    destination.unlink()
            except OSError:
                pass
        raise
    finally:
        for temporary, _destination in staged:
            temporary.unlink(missing_ok=True)
        if not complete:
            for _temporary, destination in published:
                if _lexists(destination):
                    raise RuntimeError(
                        f"failed to roll back partial atlas output: {destination}"
                    )


def _validated_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    data_path = Path(args.data)
    meta_path = Path(args.meta)
    json_path = Path(args.json_out)
    csv_path = Path(args.csv_out)
    paths = [data_path, meta_path, json_path, csv_path]
    resolved = [path.resolve(strict=False) for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("data, meta, JSON output and CSV output paths must be distinct")
    for path in (data_path, meta_path):
        if not path.is_file():
            raise ValueError(f"input is not a regular file: {path}")
    for path in (json_path, csv_path):
        if _lexists(path):
            raise ValueError(f"refusing to overwrite existing output: {path}")
    return data_path, meta_path, json_path, csv_path


def do_atlas(args: argparse.Namespace) -> dict:
    if not CODE_SHA_RE.fullmatch(args.code_sha):
        raise ValueError("--code-sha must be a full lowercase 40-hex commit SHA")
    if not 1 <= args.probe_size <= 4096:
        raise ValueError("--probe-size must be in [1, 4096]")
    if not 0 <= args.probe_seed < (1 << 64):
        raise ValueError("--probe-seed must fit an unsigned 64-bit integer")
    data_path, meta_path, json_path, csv_path = _validated_paths(args)
    report, csv_payload = build_atlas(
        data_path,
        meta_path,
        code_sha=args.code_sha,
        probe_size=args.probe_size,
        probe_seed=args.probe_seed,
    )
    json_payload = _canonical_json(report, pretty=True)
    _publish_pair_no_clobber(json_path, json_payload, csv_path, csv_payload)
    return {
        "csv_sha256": hashlib.sha256(csv_payload).hexdigest(),
        "json_sha256": hashlib.sha256(json_payload).hexdigest(),
        "probe_sha256": report["probe"]["probe_sha256"],
        "records": report["records"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic objective blind-spot atlas from aligned "
            "JNNW/JSM1 self-play records. Outputs are diagnostics, never gates."
        )
    )
    parser.add_argument("--data", required=True, help="input JNNW corpus")
    parser.add_argument("--meta", required=True, help="aligned input JSM1 sidecar")
    parser.add_argument("--json-out", required=True, help="new atlas JSON path")
    parser.add_argument("--csv-out", required=True, help="new long-form CSV path")
    parser.add_argument(
        "--code-sha",
        required=True,
        help="full lowercase 40-hex SHA of the code used for the report",
    )
    parser.add_argument(
        "--probe-size",
        type=int,
        default=256,
        help="bottom-k fixed probe size (default: 256; max: 4096)",
    )
    parser.add_argument(
        "--probe-seed",
        type=int,
        default=20260728,
        help="unsigned 64-bit deterministic probe seed (default: 20260728)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = do_atlas(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"blind_spot_atlas: ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
