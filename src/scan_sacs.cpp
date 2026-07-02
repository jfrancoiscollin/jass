// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// See scan_sacs.hpp. The add_sacs arithmetic below is a VERBATIM transcription of
// rhalbersma/scan src/gen.cpp::add_sacs (GPL3), operating on Scan's sparse-64
// layout ; only the jass<->Scan bitboard conversion is ours.
#include "scan_sacs.hpp"

#include "board.hpp"     // Color, is_promotion_square

#include <cstdint>

namespace jass {
namespace {

// --- Scan's sparse-64 layout constants (rhalbersma/scan) ---------------------
constexpr int I1 = 6, J1 = 7, I2 = 12, J2 = 14;
constexpr std::uint64_t SQUARES = 0x7DF3EF9F7CFBE7DFULL;   // legal sparse squares
constexpr std::uint64_t FILE1   = 0x0010008004002001ULL;   // bit::file(1)
constexpr std::uint64_t FILE8   = 0x4002001000800400ULL;   // bit::file(File_Size-2)
constexpr std::uint64_t RANK1   = 0x00000000000007C0ULL;   // bit::rank(1)
constexpr std::uint64_t RANK8   = 0x01F0000000000000ULL;   // bit::rank(Rank_Size-2)

// dense (jass square-1, 0..49) -> Scan sparse square (0..62). Scan's Square_Sparse.
constexpr int SPARSE[50] = {
     0,  1,  2,  3,  4,   6,  7,  8,  9, 10,  13, 14, 15, 16, 17,  19, 20, 21, 22, 23,
    26, 27, 28, 29, 30,  32, 33, 34, 35, 36,  39, 40, 41, 42, 43,  45, 46, 47, 48, 49,
    52, 53, 54, 55, 56,  58, 59, 60, 61, 62,
};

// inverse : Scan sparse square (0..63) -> jass square (1..50), 0 = invalid.
int g_dense_sq[64];
bool g_inited = false;
void ensure_init() {
    if (g_inited) return;
    for (int i = 0; i < 64; ++i) g_dense_sq[i] = 0;
    for (int d = 0; d < 50; ++d) g_dense_sq[SPARSE[d]] = d + 1;   // -> jass square
    g_inited = true;
}

// jass dense bitboard (bit = square-1) -> Scan sparse bitboard.
std::uint64_t to_sparse(std::uint64_t jbb) {
    std::uint64_t s = 0;
    while (jbb) {
        const int i = __builtin_ctzll(jbb);
        jbb &= jbb - 1;
        s |= std::uint64_t(1) << SPARSE[i];
    }
    return s;
}

// Emit sac moves : for each destination bit `to` in `dests`, from = to + from_off
// (Scan's add_moves_to recovers `from = to - inc`). Map both back to jass squares.
void emit(const Position& pos, std::uint64_t dests, int from_off, MoveList& out) {
    const Color us = pos.side_to_move();
    dests &= SQUARES;
    while (dests) {
        const int to_sp = __builtin_ctzll(dests);
        dests &= dests - 1;
        const int fr_sp = to_sp + from_off;
        const int fj = (fr_sp >= 0 && fr_sp < 64) ? g_dense_sq[fr_sp] : 0;
        const int tj = g_dense_sq[to_sp];
        if (fj == 0 || tj == 0) continue;                 // guard (should not happen)
        Move m;
        m.from = static_cast<Square>(fj);
        m.to   = static_cast<Square>(tj);
        m.num_captures = 0;
        m.promotes = is_promotion_square(static_cast<Square>(tj), us);
        out.push(m);
    }
}

}  // namespace

void scan_add_sacs(const Position& pos, MoveList& out) {
    ensure_init();
    const bool white = (pos.side_to_move() == Color::White);

    const std::uint64_t mp = to_sparse(white ? pos.white_men() : pos.black_men());
    const std::uint64_t op = to_sparse(white ? (pos.black_men() | pos.black_kings())
                                             : (pos.white_men() | pos.white_kings()));
    const std::uint64_t all = pos.white_men() | pos.white_kings()
                            | pos.black_men() | pos.black_kings();
    const std::uint64_t e = SQUARES & ~to_sparse(all);

    if (white) {
        std::uint64_t strong = ((FILE1 | RANK8 | (mp >> I2)) & (mp >> I1) & (e << I1))
                             | ((FILE8 | RANK8 | (mp >> J2)) & (mp >> J1) & (e << J1));
        std::uint64_t weak = ((mp << J1) & (e << J2)) | ((mp << I1) & (e << I2))
                           | ((mp >> I1) & (e >> I2)) | ((mp >> J1) & (e >> J2));
        std::uint64_t target = strong & ~weak;
        std::uint64_t pin = ((mp << J1) & (op << J2)) | ((mp << I1) & (op << I2))
                          | ((mp >> I1) & (op >> I2)) | ((mp >> J1) & (op >> J2));
        std::uint64_t danger_i = ((op << I1) & (e >> I1)) | ((op >> I1) & (e << I1));
        std::uint64_t danger_j = ((op << J1) & (e >> J1)) | ((op >> J1) & (e << J1));
        std::uint64_t wi = 0, wj = 0;
        wi |= (target >> I1) & (op << I1) & ~danger_j;
        wj |= (target >> J1) & (op << J1) & ~danger_i;
        wi |= ~(op << I1) & (op << J1) & ((e & target) >> J1);
        wj |= ~(op << J1) & (op << I1) & ((e & target) >> I1);
        wi |= ~(op << I1) & (op >> J1) & ((e & target) << J1);
        wj |= ~(op << J1) & (op >> I1) & ((e & target) << I1);
        std::uint64_t opp_weak = ((op << I1) & (e << I2)) | ((op << J1) & (e << J2));
        std::uint64_t opp_pin  = ((op >> I1) & (mp >> I2)) | ((op >> J1) & (mp >> J2));
        std::uint64_t opp_target = op & opp_weak & opp_pin;
        wi |= ((mp & ~weak) >> I1) & (opp_target << I1) & ~danger_j;
        wj |= ((mp & ~weak) >> J1) & (opp_target << J1) & ~danger_i;
        wi &= ((mp & ~pin) >> I1) & e;
        wj &= ((mp & ~pin) >> J1) & e;
        emit(pos, wi, +I1, out);   // add_moves_to(wi, -I1) : from = to + I1
        emit(pos, wj, +J1, out);
    } else {
        std::uint64_t strong = ((FILE1 | RANK1 | (mp << J2)) & (mp << J1) & (e >> J1))
                             | ((FILE8 | RANK1 | (mp << I2)) & (mp << I1) & (e >> I1));
        std::uint64_t weak = ((mp << J1) & (e << J2)) | ((mp << I1) & (e << I2))
                           | ((mp >> I1) & (e >> I2)) | ((mp >> J1) & (e >> J2));
        std::uint64_t pin = ((mp << J1) & (op << J2)) | ((mp << I1) & (op << I2))
                          | ((mp >> I1) & (op >> I2)) | ((mp >> J1) & (op >> J2));
        std::uint64_t danger_i = ((op >> I1) & (e << I1)) | ((op << I1) & (e >> I1));
        std::uint64_t danger_j = ((op >> J1) & (e << J1)) | ((op << J1) & (e >> J1));
        std::uint64_t target = strong & ~weak;
        std::uint64_t bi = 0, bj = 0;
        bi |= (target << I1) & (op >> I1) & ~danger_j;
        bj |= (target << J1) & (op >> J1) & ~danger_i;
        bi |= ~(op >> I1) & (op >> J1) & ((e & target) << J1);
        bj |= ~(op >> J1) & (op >> I1) & ((e & target) << I1);
        bi |= ~(op >> I1) & (op << J1) & ((e & target) >> J1);
        bj |= ~(op >> J1) & (op << I1) & ((e & target) >> I1);
        std::uint64_t opp_weak = ((op >> I1) & (e >> I2)) | ((op >> J1) & (e >> J2));
        std::uint64_t opp_pin  = ((op << I1) & (mp << I2)) | ((op << J1) & (mp << J2));
        std::uint64_t opp_target = op & opp_weak & opp_pin;
        bi |= ((mp & ~weak) << I1) & (opp_target >> I1) & ~danger_j;
        bj |= ((mp & ~weak) << J1) & (opp_target >> J1) & ~danger_i;
        bi &= ((mp & ~pin) << I1) & e;
        bj &= ((mp & ~pin) << J1) & e;
        emit(pos, bi, -I1, out);   // add_moves_to(bi, +I1) : from = to - I1
        emit(pos, bj, -J1, out);
    }
}

}  // namespace jass
