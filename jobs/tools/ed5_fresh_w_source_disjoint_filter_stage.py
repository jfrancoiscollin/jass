#!/usr/bin/env python3
"""Mechanical ED5 W repair: make the single preregistered reserve disjoint.

ED5 preregisters one W reserve seed for a pre-target canonical collision. 1979
proved that, after the 64-bit seed repair, the reserve stream itself can still
contain positions from the already-sealed D source. This wrapper changes no
candidate, target, population, seed, quota, opening/game shape, row quota or
statistical gate. It only applies the already-required canonical-disjointness
constraint while selecting openings from the *same* reserve-seed score-free
stream: an opening is ineligible if any of its otherwise-selected 16 rows is in
the frozen forbidden identity set. Selection remains first-appearance order.

Primary-seed behavior is byte-for-byte delegated to the existing ED5 W stage;
the filter activates only when the preregistered reserve seed is being used.
All inspected JNNW target bytes are zero and no game result is decoded.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed4_fresh_w_source_stage as base
from jobs.tools import ed5_fresh_w_source_stage as stage
# Import installs the already-proven uint64 seed repair by replacing
# stage.configure_base before stage.main() is called below.
from jobs.tools import ed5_fresh_w_source_seedfix_stage as seedfix
from jobs.tools.launch_runtime_v2 import atomic_json

_ORIGINAL_SELECT_ROWS = base.select_rows
_LAST_FILTER_STATS: dict[str, int | str | bool] = {}


def _record_at(raw: bytes, index: int) -> bytes:
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError("reserve_filter_jnnw_magic")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * base.JNNW_REC:
        raise ValueError("reserve_filter_jnnw_size")
    if index < 0 or index >= count:
        raise ValueError("reserve_filter_row_index")
    off = 8 + index * base.JNNW_REC
    rec = raw[off:off + base.JNNW_REC]
    if rec[33:38] != b"\0" * 5:
        raise ValueError("reserve_filter_target_bytes_nonzero")
    return rec


def select_rows_with_forbidden(
    rows: list[dict],
    jnnw: Path,
    opening_target: int,
    forbidden: set[str],
) -> tuple[list[int], list[dict], dict]:
    """Apply only the preregistered canonical-exclusion barrier to W openings."""
    raw = jnnw.read_bytes()
    openings: dict[int, dict[int, list[dict]]] = {}
    for row in rows:
        games = openings.setdefault(row["opening_id"], {})
        games.setdefault(row["game_id"], []).append(row)
    if any(len(games) > base.GAMES_PER_OPENING for games in openings.values()):
        raise ValueError("pair_opening_more_than_two_games")

    eligible: list[tuple[int, dict[int, list[dict]]]] = []
    skipped_openings = 0
    skipped_rows = 0
    for opening_id, games in openings.items():
        if len(games) != base.GAMES_PER_OPENING:
            continue
        if not all(len(group) >= base.ROWS_PER_GAME for group in games.values()):
            continue
        collision = False
        local_collisions = 0
        for game_rows in games.values():
            for row in game_rows[:base.ROWS_PER_GAME]:
                rec = _record_at(raw, int(row["raw_row_index"]))
                if base.canonical_position(rec) in forbidden:
                    collision = True
                    local_collisions += 1
        if collision:
            skipped_openings += 1
            skipped_rows += local_collisions
            continue
        eligible.append((opening_id, games))

    if len(eligible) < opening_target:
        raise base.SupportInsufficient({
            "represented_openings": len(openings),
            "eligible_paired_openings": len(eligible),
            "required_paired_openings": opening_target,
            "rows": len(rows),
            "forbidden_identity_count": len(forbidden),
            "forbidden_openings_skipped": skipped_openings,
            "forbidden_selected_rows_seen": skipped_rows,
            "selection_repair": "reserve_first_appearance_after_preregistered_canonical_exclusion",
        })

    selected: list[int] = []
    groups: list[dict] = []
    for opening_rank, (opening_id, games) in enumerate(eligible[:opening_target]):
        for game_slot, (game_id, game_rows) in enumerate(games.items()):
            for within_game_rank, row in enumerate(game_rows[:base.ROWS_PER_GAME]):
                source_row = len(selected)
                selected.append(int(row["raw_row_index"]))
                groups.append({
                    "source_row": source_row,
                    "opening_rank": opening_rank,
                    "opening_id": opening_id,
                    "game_slot": game_slot,
                    "game_id": game_id,
                    "within_game_rank": within_game_rank,
                    **row,
                })

    expected = opening_target * base.GAMES_PER_OPENING * base.ROWS_PER_GAME
    if len(selected) != expected or len(groups) != expected:
        raise ValueError("selected_cardinality")
    support = {
        "represented_openings": len(openings),
        "eligible_paired_openings": len(eligible),
        "selected_openings": opening_target,
        "selected_games": opening_target * base.GAMES_PER_OPENING,
        "selected_positions": expected,
        "forbidden_identity_count": len(forbidden),
        "forbidden_openings_skipped": skipped_openings,
        "forbidden_selected_rows_seen": skipped_rows,
        "selection_repair": "reserve_first_appearance_after_preregistered_canonical_exclusion",
    }
    return selected, groups, support


def _frozen_forbidden_set() -> set[str]:
    result = Path(os.environ["JASS_RESULT_DIR"])
    d_root = result / "ed5-w-d-source/source"
    historical_root = result / "ed5-w-historical-ed4-w1959/source"
    required = (
        d_root / "parents.jnnw",
        d_root / "children.jnnw",
        historical_root / "positions.jnnw",
    )
    if not all(path.is_file() for path in required):
        raise ValueError("reserve_filter_authenticated_sources_missing")
    forbidden = (
        stage.canonical_set(required[0])
        | stage.canonical_set(required[1])
        | stage.canonical_set(required[2])
    )
    if not forbidden:
        raise ValueError("reserve_filter_empty_forbidden_set")
    return forbidden


def _runtime_select_rows(rows: list[dict], opening_target: int):
    global _LAST_FILTER_STATS
    if base.SEED != stage.RESERVE:
        return _ORIGINAL_SELECT_ROWS(rows, opening_target)

    job = os.environ.get("JASS_JOB_ID", "unknown")
    attempt = os.environ.get("JASS_ATTEMPT_ID", "unknown")
    safe_jnnw = Path("/var/tmp") / f"jass-ed4-w-source-{job}-{attempt}" / "safe-full.jnnw"
    if not safe_jnnw.is_file():
        raise ValueError("reserve_filter_safe_jnnw_missing")
    selected, groups, support = select_rows_with_forbidden(
        rows,
        safe_jnnw,
        opening_target,
        _frozen_forbidden_set(),
    )
    _LAST_FILTER_STATS = {
        "enabled": True,
        "seed": stage.RESERVE,
        "forbidden_identity_count": int(support["forbidden_identity_count"]),
        "forbidden_openings_skipped": int(support["forbidden_openings_skipped"]),
        "forbidden_selected_rows_seen": int(support["forbidden_selected_rows_seen"]),
        "selection_repair": str(support["selection_repair"]),
    }
    return selected, groups, support


base.select_rows = _runtime_select_rows


def _publish_repair_receipt() -> None:
    if not _LAST_FILTER_STATS:
        return
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    source_json = art / "source/source.json"
    seal_json = art / "cohort-seal.json"
    if not source_json.is_file() or not seal_json.is_file():
        raise ValueError("reserve_filter_final_outputs_missing")

    source = json.loads(source_json.read_text())
    source["reserve_disjoint_filter"] = dict(_LAST_FILTER_STATS)
    atomic_json(source_json, source)

    seal = json.loads(seal_json.read_text())
    seal["reserve_disjoint_filter"] = dict(_LAST_FILTER_STATS)
    seal["files"]["source.json"] = stage.sha(source_json)
    atomic_json(seal_json, seal)
    atomic_json(art / "scientific-summary.json", seal)
    atomic_json(art / "reserve-disjoint-filter.json", {
        "schema": "jass.ed5.w_reserve_disjoint_filter.v1",
        "classification": "TECHNICAL_SOURCE_RECOVERY",
        "target_reads": 0,
        "candidate_reads": 0,
        "control_evaluations": 0,
        "fits": 0,
        "alpha_spent": 0,
        **_LAST_FILTER_STATS,
    })


def main() -> int:
    rc = seedfix.main()
    if rc == 0:
        _publish_repair_receipt()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
