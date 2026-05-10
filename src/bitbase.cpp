// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "bitbase.hpp"

#include "bitboard.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "types.hpp"

#include <array>
#include <cstdint>
#include <mutex>
#include <vector>

namespace jass {

namespace {

// Small helper: read the (up to 2) set squares from a Bitboard into a
// small fixed array. Assumes the caller knows how many bits are set.
struct SquaresOf2 { Square a; Square b; };

SquaresOf2 squares_of_2(Bitboard b) noexcept {
    Square a = pop_lsb(b);
    Square c = pop_lsb(b);
    return {a, c};
}

Square single_square(Bitboard b) noexcept {
    return pop_lsb(b);
}

// ---------------------------------------------------------------------------
// 2-king-vs-1-king bitbase (white-major orientation: 2 white kings,
// 1 black king). The mirror is handled at probe time by colour-swapping
// the position.
// ---------------------------------------------------------------------------
// Encoding: a flat 50 × 50 × 50 × 2 grid. Some entries are invalid
// (king squares overlap) and stay marked Unknown. We do not enforce
// wk1 < wk2 in the encoding; the probe sorts the two squares before
// indexing so the same physical position always lands on the same
// slot.
class TwoVsOneBitbase {
public:
    void ensure_built() {
        std::call_once(once_, [this]() { build(); });
    }

    EndgameResult probe(int wk1, int wk2, int bk, int stm) const noexcept {
        if (wk1 > wk2) { const int t = wk1; wk1 = wk2; wk2 = t; }
        return table_[index(wk1, wk2, bk, stm)];
    }

private:
    static constexpr std::size_t TABLE_SIZE = 50 * 50 * 50 * 2;

    static constexpr std::size_t index(int wk1, int wk2, int bk, int stm) noexcept {
        return ((static_cast<std::size_t>(wk1 - 1) * 50
              +  static_cast<std::size_t>(wk2 - 1)) * 50
              +  static_cast<std::size_t>(bk  - 1)) * 2
              +  static_cast<std::size_t>(stm);
    }

    std::once_flag once_;
    std::vector<EndgameResult> table_{TABLE_SIZE, EndgameResult::Unknown};

    static Position make_pos(int wk1, int wk2, int bk, int stm) {
        Position p;
        p.add_piece(static_cast<Square>(wk1), Piece::WhiteKing);
        p.add_piece(static_cast<Square>(wk2), Piece::WhiteKing);
        p.add_piece(static_cast<Square>(bk),  Piece::BlackKing);
        p.set_side_to_move(stm == 0 ? Color::White : Color::Black);
        return p;
    }

    // Look up the result of a child position. The child either still
    // has 2-vs-1 material (recursive table read) or has degenerated
    // into a known terminal: K vs K is a draw, and a side with no
    // pieces has lost.
    EndgameResult child_result(const Position& child) const noexcept {
        if (child.white_men() != 0 || child.black_men() != 0) {
            return EndgameResult::Unknown;  // shouldn't happen in this table
        }
        const int wk = popcount(child.white_kings());
        const int bk = popcount(child.black_kings());
        if (wk == 0)              return EndgameResult::BlackWin;
        if (bk == 0)              return EndgameResult::WhiteWin;
        if (wk == 1 && bk == 1)   return EndgameResult::Draw;

        if (wk == 2 && bk == 1) {
            const auto [a, b] = squares_of_2(child.white_kings());
            const Square     k = single_square(child.black_kings());
            return probe(static_cast<int>(a), static_cast<int>(b),
                         static_cast<int>(k),
                         child.side_to_move() == Color::White ? 0 : 1);
        }
        // 1 vs 2 should never appear from this table (white never gains
        // a piece, black never gains either).
        return EndgameResult::Unknown;
    }

    void build() {
        // Pass 0: terminal positions (no legal moves → loss for STM).
        for (int wk1 = 1; wk1 <= 49; ++wk1) {
            for (int wk2 = wk1 + 1; wk2 <= 50; ++wk2) {
                for (int bk = 1; bk <= 50; ++bk) {
                    if (bk == wk1 || bk == wk2) continue;
                    for (int stm = 0; stm < 2; ++stm) {
                        const Position p = make_pos(wk1, wk2, bk, stm);
                        MoveList ml;
                        generate_legal_moves(p, ml);
                        if (ml.empty()) {
                            table_[index(wk1, wk2, bk, stm)] =
                                (stm == 0) ? EndgameResult::BlackWin
                                           : EndgameResult::WhiteWin;
                        }
                    }
                }
            }
        }

        // Iterative forward analysis. A position is a WIN for STM if
        // any legal move leads to a child where the same colour wins;
        // it is a LOSS for STM if every legal move leads to a child
        // where the opposite colour wins. Otherwise it stays Unknown
        // and is treated as a draw at the end.
        bool changed = true;
        while (changed) {
            changed = false;
            for (int wk1 = 1; wk1 <= 49; ++wk1) {
                for (int wk2 = wk1 + 1; wk2 <= 50; ++wk2) {
                    for (int bk = 1; bk <= 50; ++bk) {
                        if (bk == wk1 || bk == wk2) continue;
                        for (int stm = 0; stm < 2; ++stm) {
                            const std::size_t idx = index(wk1, wk2, bk, stm);
                            if (table_[idx] != EndgameResult::Unknown) continue;

                            const EndgameResult win_for_us =
                                (stm == 0) ? EndgameResult::WhiteWin
                                           : EndgameResult::BlackWin;
                            const EndgameResult loss_for_us =
                                (stm == 0) ? EndgameResult::BlackWin
                                           : EndgameResult::WhiteWin;

                            const Position p = make_pos(wk1, wk2, bk, stm);
                            MoveList ml;
                            generate_legal_moves(p, ml);

                            bool any_win  = false;
                            bool all_loss = true;
                            for (const auto& m : ml) {
                                const EndgameResult cr = child_result(p.after(m));
                                if (cr == EndgameResult::Unknown) {
                                    all_loss = false;
                                    continue;
                                }
                                if (cr == win_for_us)  any_win  = true;
                                if (cr != loss_for_us) all_loss = false;
                            }

                            if (any_win) {
                                table_[idx] = win_for_us;
                                changed = true;
                            } else if (all_loss) {
                                table_[idx] = loss_for_us;
                                changed = true;
                            }
                        }
                    }
                }
            }
        }

        // Anything still Unknown is a Draw.
        for (auto& r : table_) {
            if (r == EndgameResult::Unknown) r = EndgameResult::Draw;
        }
    }
};

TwoVsOneBitbase& two_vs_one() {
    static TwoVsOneBitbase b;
    return b;
}

EndgameResult swap_winner(EndgameResult r) noexcept {
    if (r == EndgameResult::WhiteWin) return EndgameResult::BlackWin;
    if (r == EndgameResult::BlackWin) return EndgameResult::WhiteWin;
    return r;  // Draw / Unknown unchanged
}

}  // namespace

EndgameResult probe_kings_endgame(const Position& pos) {
    if (pos.white_men() != 0 || pos.black_men() != 0) {
        return EndgameResult::Unknown;
    }
    const int wk = popcount(pos.white_kings());
    const int bk = popcount(pos.black_kings());

    // 2 white kings vs 1 black king
    if (wk == 2 && bk == 1) {
        TwoVsOneBitbase& b = two_vs_one();
        b.ensure_built();
        const auto   [a, c] = squares_of_2(pos.white_kings());
        const Square k      = single_square(pos.black_kings());
        return b.probe(static_cast<int>(a), static_cast<int>(c),
                       static_cast<int>(k),
                       pos.side_to_move() == Color::White ? 0 : 1);
    }

    // 1 white king vs 2 black kings: equivalent to the mirror after a
    // colour swap. Probe with (former black kings as wk1, wk2; former
    // white king as bk; stm flipped) and swap the resulting winner.
    if (wk == 1 && bk == 2) {
        TwoVsOneBitbase& b = two_vs_one();
        b.ensure_built();
        const auto   [a, c] = squares_of_2(pos.black_kings());
        const Square k      = single_square(pos.white_kings());
        const int    stm    = pos.side_to_move() == Color::White ? 1 : 0;
        return swap_winner(b.probe(static_cast<int>(a), static_cast<int>(c),
                                   static_cast<int>(k), stm));
    }

    return EndgameResult::Unknown;
}

}  // namespace jass
