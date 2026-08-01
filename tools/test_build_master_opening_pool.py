#!/usr/bin/env python3
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_master_opening_pool import (  # noqa: E402
    Candidate,
    REC,
    START_BBS,
    collect_candidates,
    position_to_fen,
    select_positions,
)


def record(
    wm: int, wk: int, bm: int, bk: int, stm: int, score: int = 0, wdl: int = 0,
) -> bytes:
    return REC.pack(wm, wk, bm, bk, stm, score, wdl)


def main() -> int:
    start = record(*START_BBS, 0)
    game1 = record(START_BBS[0] ^ (1 << 30) ^ (1 << 29),
                   0, START_BBS[2], 0, 1, 123, 1)
    game2 = record(START_BBS[0], 0,
                   START_BBS[2] ^ (1 << 19) ^ (1 << 20), 0, 0, -44, -1)
    candidates, games = collect_candidates(
        [start, game1, start, game2],
        min_ply=1,
        max_ply=1,
        min_pieces=38,
        allow_kings=False,
    )
    assert games == 2
    assert len(candidates) == 2
    assert all(row.record[33:] == struct.pack("<ib", 0, 0) for row in candidates)

    selected = select_positions(
        candidates, [True, True], positions=2, seed=7
    )
    assert len(selected) == 2
    assert len({row.position for row in selected}) == 2
    assert select_positions(candidates, [False, True], positions=2, seed=7) == [
        candidates[1]
    ]

    fen = position_to_fen(candidates[0].position)
    assert fen.startswith("B:W")
    assert ":B1,2,3" in fen
    print("ALL build_master_opening_pool TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
