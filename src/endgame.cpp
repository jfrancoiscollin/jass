// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "endgame.hpp"

#include "bitbase.hpp"
#include "bitboard.hpp"

namespace jass {

EndgameResult probe_endgame(const Position& pos) noexcept {
    // Reject anything that has men on the board: only kings-only
    // positions are recognised by the current tablebase.
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
