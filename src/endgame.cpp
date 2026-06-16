// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "endgame.hpp"

#include "bitbase.hpp"
#include "bitboard.hpp"
#include "egdb_bridge.hpp"

namespace jass {

EndgameResult probe_endgame(const Position& pos) noexcept {
    // 0. External full WLD database (Kingsrow egdb_intl) when present. Covers
    //    men + kings up to the DB's piece cap — a strict superset of the tiny
    //    in-memory kings-only tables below. No-op (returns Unknown instantly)
    //    on a build without JASS_EGDB or when no DB path is configured, so the
    //    default build falls straight through to the kings-only logic.
    //    `available()` is a single atomic load — false in the default build,
    //    so this whole block costs one branch per node and falls through. The
    //    one-time bootstrap from JASS_EGDB_PATH happens once per top-level
    //    search (see search.cpp), NOT here, to keep the per-node gate minimal.
    if (egdb::available()) {
        if (popcount(pos.occupied()) <= egdb::max_pieces()) {
            const EndgameResult r = egdb::probe(pos);
            if (r != EndgameResult::Unknown) return r;
        }
    }

    // Reject anything that has men on the board: only kings-only
    // positions are recognised by the in-memory tablebase.
    if (pos.white_men() != 0 || pos.black_men() != 0) {
        return EndgameResult::Unknown;
    }

    const int wk = popcount(pos.white_kings());
    const int bk = popcount(pos.black_kings());

    // Mate-by-no-pieces is handled by the move generator (no legal
    // moves → the search returns -MATE_SCORE+ply on its own).
    if (wk == 0 || bk == 0) return EndgameResult::Unknown;

    // 1 king vs 1 king is the canonical theoretical draw in international
    // draughts.
    if (wk == 1 && bk == 1) return EndgameResult::Draw;

    // 2-vs-1 and 3-vs-1 endgames are resolved by the retrograde-built
    // bitbases (and their colour-mirrored counterparts).
    if ((wk == 2 && bk == 1) || (wk == 1 && bk == 2)
     || (wk == 3 && bk == 1) || (wk == 1 && bk == 3)) {
        return probe_kings_endgame(pos);
    }

    return EndgameResult::Unknown;
}

}  // namespace jass
