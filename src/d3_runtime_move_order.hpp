// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#include "board.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "scan_eval.hpp"
#include "../pattern_jass/src/pattern.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <optional>
#include <string>
#include <tuple>
#include <vector>

namespace jass::d3_runtime_order {

inline constexpr std::size_t BASE_WIDTH = 158;
inline constexpr std::size_t PHASES = 4;
inline constexpr std::size_t WIDTH = BASE_WIDTH * PHASES;

struct Runtime {
    bool active{false};
    std::array<double, WIDTH> beta{};
    scan_eval::ScanWeights base{};
};

inline int phase_index(const Position& parent) noexcept {
    const int pieces = popcount(parent.occupied());
    if (pieces >= 30 && pieces <= 40) return 0;
    if (pieces >= 20 && pieces <= 29) return 1;
    if (pieces >= 12 && pieces <= 19) return 2;
    if (pieces >= 9  && pieces <= 11) return 3;
    return -1;  // frozen support amendment: <9 is control/legacy ordering.
}

inline int canonical_square(Square sq, Color parent_stm) noexcept {
    const int value = static_cast<int>(sq);
    return parent_stm == Color::Black ? value : 51 - value;
}

inline std::tuple<int, int, std::uint64_t, bool> semantic_key(const Move& m) noexcept {
    return {static_cast<int>(m.from), static_cast<int>(m.to),
            static_cast<std::uint64_t>(m.captured), m.promotes};
}

inline bool semantic_less(const Move& a, const Move& b) noexcept {
    return semantic_key(a) < semantic_key(b);
}

inline bool read_npy632(const std::string& path,
                        std::array<double, WIDTH>& out,
                        std::string& err) {
    static_assert(std::endian::native == std::endian::little,
                  "D3 sealed npy runtime requires a little-endian host");
    std::ifstream f(path, std::ios::binary);
    if (!f) { err = "cannot open adapter " + path; return false; }
    f.seekg(0, std::ios::end);
    const auto n = f.tellg();
    f.seekg(0, std::ios::beg);
    if (n < 16) { err = "adapter npy too short"; return false; }
    std::vector<unsigned char> raw(static_cast<std::size_t>(n));
    f.read(reinterpret_cast<char*>(raw.data()), n);
    if (!f) { err = "adapter npy read failure"; return false; }
    const unsigned char magic[6] = {0x93, 'N', 'U', 'M', 'P', 'Y'};
    if (std::memcmp(raw.data(), magic, 6) != 0) {
        err = "adapter npy magic mismatch"; return false;
    }
    const unsigned major = raw[6], minor = raw[7];
    (void)minor;
    std::size_t hlen = 0, hoff = 0;
    if (major == 1) {
        if (raw.size() < 10) { err = "adapter npy v1 header truncated"; return false; }
        hlen = static_cast<std::size_t>(raw[8])
             | (static_cast<std::size_t>(raw[9]) << 8);
        hoff = 10;
    } else if (major == 2 || major == 3) {
        if (raw.size() < 12) { err = "adapter npy v2/v3 header truncated"; return false; }
        hlen = static_cast<std::size_t>(raw[8])
             | (static_cast<std::size_t>(raw[9]) << 8)
             | (static_cast<std::size_t>(raw[10]) << 16)
             | (static_cast<std::size_t>(raw[11]) << 24);
        hoff = 12;
    } else {
        err = "unsupported adapter npy version"; return false;
    }
    if (hoff + hlen > raw.size()) { err = "adapter npy header overflow"; return false; }
    const std::string header(reinterpret_cast<const char*>(raw.data() + hoff), hlen);
    const bool descr_ok = header.find("'<f8'") != std::string::npos
                       || header.find("\"<f8\"") != std::string::npos;
    if (!descr_ok || header.find("False") == std::string::npos
        || header.find("632") == std::string::npos) {
        err = "adapter npy dtype/order/shape mismatch"; return false;
    }
    const std::size_t data = hoff + hlen;
    if (raw.size() != data + WIDTH * sizeof(double)) {
        err = "adapter npy payload size mismatch"; return false;
    }
    std::memcpy(out.data(), raw.data() + data, WIDTH * sizeof(double));
    for (const double v : out) {
        if (!std::isfinite(v)) { err = "adapter contains non-finite weight"; return false; }
    }
    return true;
}

inline double tempo_wmg_exact(const Position& pos) noexcept {
    long tempo = 0;
    for (Bitboard b = pos.white_men(); b;) {
        const Square sq = pop_lsb(b);
        tempo += static_cast<long>(row_of(sq));
    }
    for (Bitboard b = pos.black_men(); b;) {
        const Square sq = pop_lsb(b);
        tempo += static_cast<long>(9 - row_of(sq));
    }
    const double w = static_cast<double>(tempo) / 300.0;
    return std::clamp(w, 0.0, 1.0);
}

inline const scan_eval::PatPair& pattern_pair(const scan_eval::ScanWeights& w,
                                               std::size_t col) noexcept {
    if (!w.remap8.empty()) return w.pat[w.remap8[col]];
    if (!w.remap.empty()) return w.pat[w.remap[col]];
    return w.pat[col];
}

// Exact offline D3 base channel: quantized PJTW linear dot in BLACK POV,
// piece-units, before runtime centipawn rounding. This mirrors
// d1_postfit_readout._predict / train.load_v3_weights_float.
inline double raw_black_piece_units(const scan_eval::ScanWeights& w,
                                    const Position& pos) noexcept {
    static constexpr auto offsets = pattern_jass::pattern_offsets();
    std::array<std::uint32_t, pattern_jass::NUM_PATTERNS> idx{};
    pattern_jass::extract_all(scan_eval::pat_black(pos), scan_eval::pat_white(pos), idx);
    std::int64_t smg = 0, seg = 0;
    for (std::size_t i = 0; i < pattern_jass::NUM_PATTERNS; ++i) {
        const std::size_t col = offsets[i]
            + (idx[i] % pattern_jass::BUCKETS_PER_PATTERN);
        const auto& p = pattern_pair(w, col);
        smg += p.mg; seg += p.eg;
    }
    std::array<float, scan_eval::NUM_EXTRAS> ex{};
    scan_eval::compute_extras(pos, ex);
    double emg = 0.0, eeg = 0.0;
    for (std::size_t i = 0; i < ex.size(); ++i) {
        const double x = static_cast<double>(ex[i]);
        emg += static_cast<double>(w.ext_mg[i]) * x;
        eeg += static_cast<double>(w.ext_eg[i]) * x;
    }
#ifdef JASS_TEMPO_STAGE
    const double wmg = tempo_wmg_exact(pos);
#else
    const double wmg = scan_eval::phase_wmg(scan_eval::game_stage(pos));
#endif
    const double weg = 1.0 - wmg;
    const double black = wmg * (static_cast<double>(smg) + emg)
                       + weg * (static_cast<double>(seg) + eeg);
    return black / static_cast<double>(w.scale);
}

inline int material_delta_parent(const Position& parent,
                                 const Position& child) noexcept {
    const Color us = parent.side_to_move();
    const Color them = opposite(us);
    const int own_before = popcount(parent.pieces_of(us));
    const int opp_before = popcount(parent.pieces_of(them));
    const int own_after = popcount(child.pieces_of(us));
    const int opp_after = popcount(child.pieces_of(them));
    return (own_after - opp_after) - (own_before - opp_before);
}

inline double residual(const Runtime& rt, const Position& parent,
                       const Move& move, const Position& child) {
    const int phase = phase_index(parent);
    if (phase < 0) return 0.0;
    const std::size_t b = static_cast<std::size_t>(phase) * BASE_WIDTH;
    const Color us = parent.side_to_move();
    const Color them = opposite(us);
    double r = 0.0;
    r += rt.beta[b + static_cast<std::size_t>(canonical_square(move.from, us) - 1)];
    r += rt.beta[b + 50 + static_cast<std::size_t>(canonical_square(move.to, us) - 1)];
    for (Bitboard caps = move.captured; caps;) {
        const Square sq = pop_lsb(caps);
        r += rt.beta[b + 100 + static_cast<std::size_t>(canonical_square(sq, us) - 1)];
    }
    const int nc = popcount(move.captured);
    const int ck = popcount(move.captured & parent.kings_of(them));
    const Bitboard from_bit = square_bb(move.from);
    const bool moving_king = (parent.kings_of(us) & from_bit) != 0;
    MoveList child_moves;
    generate_legal_moves(child, child_moves);
    const int child_pieces = popcount(child.occupied());
    const int child_legal = static_cast<int>(child_moves.size());
    const bool child_forced_capture = has_any_capture(child);
    r += rt.beta[b + 150] * (static_cast<double>(nc) / 20.0);
    r += rt.beta[b + 151] * static_cast<double>(move.promotes);
    r += rt.beta[b + 152] * static_cast<double>(moving_king);
    r += rt.beta[b + 153] * (static_cast<double>(ck) / 20.0);
    r += rt.beta[b + 154] * (static_cast<double>(material_delta_parent(parent, child)) / 20.0);
    r += rt.beta[b + 155] * (static_cast<double>(child_pieces) / 40.0);
    r += rt.beta[b + 156] * (static_cast<double>(child_legal) / 64.0);
    r += rt.beta[b + 157] * static_cast<double>(child_forced_capture);
    return r;
}

inline double score(const Runtime& rt, const Position& parent,
                    const Move& move) {
    const Position child = parent.after(move);
    const double black = raw_black_piece_units(rt.base, child);
    const double parent_value = parent.side_to_move() == Color::Black ? black : -black;
    return parent_value + residual(rt, parent, move, child);
}

inline const Runtime& runtime() {
    static const Runtime rt = [] {
        Runtime out;
        const char* ap = std::getenv("JASS_D3_RUNTIME_ADAPTER");
        const char* bp = std::getenv("JASS_D3_RUNTIME_BASE_MODEL");
        if (!ap && !bp) return out;
        if (!ap || !bp) {
            std::cerr << "D3_RUNTIME_INVALID: adapter/base env must be set together\n";
            std::abort();
        }
        std::string err;
        if (!read_npy632(ap, out.beta, err)) {
            std::cerr << "D3_RUNTIME_INVALID: " << err << '\n'; std::abort();
        }
        auto base = scan_eval::load_scan_weights(bp, &err);
        if (!base || base->fm_rank != 0 || base->scale != 1000U) {
            std::cerr << "D3_RUNTIME_INVALID: base PJTW " << err << '\n'; std::abort();
        }
        out.base = std::move(*base);
        out.active = true;
        return out;
    }();
    return rt;
}

inline bool active() { return runtime().active; }

}  // namespace jass::d3_runtime_order
