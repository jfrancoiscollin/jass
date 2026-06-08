// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "scan_eval.hpp"

#include "bitboard.hpp"
#include "board.hpp"
#include "pattern_jass_bridge.hpp"

// pattern_jass is compiled into jass_lib; reach it via relative include
// (same pattern as pattern_jass_bridge.cpp).
#include "../pattern_jass/src/pattern.hpp"
#include "../pattern_jass/src/weights.hpp"

#include <array>
#include <fstream>

namespace jass::scan_eval {

namespace {

// ---------------------------------------------------------------------------
// Per-direction single-step bitboard shifts (FMJD brick layout). These match
// the deltas documented in bitboard.hpp's reach_all_dirs() exactly.
// ---------------------------------------------------------------------------
constexpr Bitboard shift_nw(Bitboard bb) noexcept {
    const Bitboard even = bb & EVEN_ROW_MASK, odd = bb & ODD_ROW_MASK;
    return ((even >> 5) | ((odd & NOT_COL_FIRST) >> 6)) & FULL_BB;
}
constexpr Bitboard shift_ne(Bitboard bb) noexcept {
    const Bitboard even = bb & EVEN_ROW_MASK, odd = bb & ODD_ROW_MASK;
    return (((even & NOT_COL_LAST) >> 4) | (odd >> 5)) & FULL_BB;
}
constexpr Bitboard shift_sw(Bitboard bb) noexcept {
    const Bitboard even = bb & EVEN_ROW_MASK, odd = bb & ODD_ROW_MASK;
    return ((even << 5) | ((odd & NOT_COL_FIRST) << 4)) & FULL_BB;
}
constexpr Bitboard shift_se(Bitboard bb) noexcept {
    const Bitboard even = bb & EVEN_ROW_MASK, odd = bb & ODD_ROW_MASK;
    return (((even & NOT_COL_LAST) << 6) | (odd << 5)) & FULL_BB;
}

using ShiftFn = Bitboard (*)(Bitboard) noexcept;
constexpr std::array<ShiftFn, 4> ALL_SHIFTS = {
    shift_nw, shift_ne, shift_sw, shift_se};

// King slide mobility : empties reachable by sliding from `kings` through
// empty squares, summed over all 4 diagonals (counts each reachable empty
// square once per direction it is reached from).
int king_slide_mobility(Bitboard kings, Bitboard empty) noexcept {
    int count = 0;
    for (const ShiftFn shift : ALL_SHIFTS) {
        Bitboard frontier = shift(kings) & empty;
        while (frontier) {
            count += popcount(frontier);
            frontier = shift(frontier) & empty;
        }
    }
    return count;
}

float lr_balance(Bitboard men) noexcept {
    int left = 0, right = 0;
    for (Bitboard b = men; b; ) {
        const Square s = pop_lsb(b);
        (col_of(s) < 5 ? left : right) += 1;
    }
    return static_cast<float>(left - right);
}

}  // namespace

int mobility(const Position& pos, Color c) noexcept {
    const Bitboard empty = pos.empties();
    const Bitboard men   = pos.men_of(c);
    int m = 0;
    if (c == Color::White) {
        // White men move "up" (toward row 0) : NW / NE.
        m += popcount(shift_nw(men) & empty);
        m += popcount(shift_ne(men) & empty);
    } else {
        // Black men move "down" (toward row 9) : SW / SE.
        m += popcount(shift_sw(men) & empty);
        m += popcount(shift_se(men) & empty);
    }
    m += king_slide_mobility(pos.kings_of(c), empty);
    return m;
}

int game_stage(const Position& pos) noexcept {
    const int pieces = popcount(pos.occupied());
    return pieces < MAX_PIECES ? pieces : MAX_PIECES;
}

void compute_extras(const Position& pos,
                    std::array<float, NUM_EXTRAS>& out) noexcept {
    out.fill(0.0f);

    for (Bitboard b = pos.black_kings(); b; ) {
        const int bit = square_to_bit(pop_lsb(b));
        out[static_cast<std::size_t>(EXTRA_BK_PST_BASE + bit)] = 1.0f;
    }
    for (Bitboard b = pos.white_kings(); b; ) {
        const int bit = square_to_bit(pop_lsb(b));
        out[static_cast<std::size_t>(EXTRA_WK_PST_BASE + bit)] = 1.0f;
    }

    out[EXTRA_BLACK_MEN] = static_cast<float>(popcount(pos.black_men()));
    out[EXTRA_WHITE_MEN] = static_cast<float>(popcount(pos.white_men()));
    out[EXTRA_BLACK_MOB] = static_cast<float>(mobility(pos, Color::Black));
    out[EXTRA_WHITE_MOB] = static_cast<float>(mobility(pos, Color::White));
    out[EXTRA_BLACK_BAL] = lr_balance(pos.black_men());
    out[EXTRA_WHITE_BAL] = lr_balance(pos.white_men());
    // NB: the 1st batch of structural extras (king-mob/back-rank/advancement,
    // 106->112) regressed on the v5 base and AGAIN on the clean v4 base (0172:
    // 0.889/0.389 vs the v4+106 champion 0.944/0.389). REVERTED. To re-test on
    // a future base, re-add them here + NUM_EXTRAS, one feature at a time.
}

// ---------------------------------------------------------------------------
// v3 loader.
// ---------------------------------------------------------------------------
namespace {

std::uint32_t rd_u32(const unsigned char* p) noexcept {
    return  static_cast<std::uint32_t>(p[0])
         | (static_cast<std::uint32_t>(p[1]) <<  8)
         | (static_cast<std::uint32_t>(p[2]) << 16)
         | (static_cast<std::uint32_t>(p[3]) << 24);
}

}  // namespace

std::optional<ScanWeights> load_scan_weights(const std::string& path,
                                             std::string* err) {
    std::ifstream f(path, std::ios::binary);
    if (!f) { if (err) *err = "cannot open " + path; return std::nullopt; }
    f.seekg(0, std::ios::end);
    const std::streamoff size = f.tellg();
    f.seekg(0, std::ios::beg);
    if (size < static_cast<std::streamoff>(V3_HEADER)) {
        if (err) *err = "file too short"; return std::nullopt;
    }
    std::vector<unsigned char> raw(static_cast<std::size_t>(size));
    f.read(reinterpret_cast<char*>(raw.data()), size);
    if (!f) { if (err) *err = "read failure"; return std::nullopt; }

    const std::uint32_t magic   = rd_u32(raw.data() +  0);
    const std::uint32_t version = rd_u32(raw.data() +  4);
    const std::uint32_t scale   = rd_u32(raw.data() +  8);
    const std::uint32_t n_pat   = rd_u32(raw.data() + 12);
    const std::uint32_t n_ext   = rd_u32(raw.data() + 16);

    if (magic != V3_MAGIC)   { if (err) *err = "bad magic"; return std::nullopt; }
    if (version != V3_VERSION) {
        if (err) *err = "not a v3 PJTW (version " + std::to_string(version) + ")";
        return std::nullopt;
    }
    if (n_pat != pattern_jass::TOTAL_BUCKETS) {
        if (err) *err = "n_pat " + std::to_string(n_pat) + " != "
                      + std::to_string(pattern_jass::TOTAL_BUCKETS);
        return std::nullopt;
    }
    if (n_ext != static_cast<std::uint32_t>(NUM_EXTRAS)) {
        if (err) *err = "n_ext " + std::to_string(n_ext) + " != "
                      + std::to_string(NUM_EXTRAS);
        return std::nullopt;
    }
    const std::size_t total = 2 * (static_cast<std::size_t>(n_pat) + n_ext);
    const std::size_t expected = V3_HEADER + total * sizeof(std::int32_t);
    if (raw.size() != expected) {
        if (err) *err = "size " + std::to_string(raw.size())
                      + " != expected " + std::to_string(expected);
        return std::nullopt;
    }

    ScanWeights w;
    w.scale = scale ? scale : 1U;
    w.pat_mg.resize(n_pat);
    w.pat_eg.resize(n_pat);

    const unsigned char* p = raw.data() + V3_HEADER;
    auto next = [&p]() noexcept {
        const std::int32_t v = static_cast<std::int32_t>(rd_u32(p));
        p += 4;
        return v;
    };
    for (std::uint32_t i = 0; i < n_pat; ++i) w.pat_mg[i] = next();
    for (std::uint32_t i = 0; i < n_pat; ++i) w.pat_eg[i] = next();
    for (int e = 0; e < NUM_EXTRAS; ++e) w.ext_mg[static_cast<std::size_t>(e)] = next();
    for (int e = 0; e < NUM_EXTRAS; ++e) w.ext_eg[static_cast<std::size_t>(e)] = next();
    return w;
}

int ScanEvalNetwork::evaluate(const Position& pos) const noexcept {
    // Men patterns (sparse one-hots, base-3), recomputed from scratch. The
    // accumulator path (evaluate_with_idx) shares everything below.
    std::array<std::uint32_t, pattern_jass::NUM_PATTERNS> idx{};
    pattern_jass::extract_all(static_cast<std::uint64_t>(pos.black_men()),
                              static_cast<std::uint64_t>(pos.white_men()), idx);
    return evaluate_with_idx(pos, idx.data());
}

int ScanEvalNetwork::evaluate_with_idx(const Position& pos,
                                       const std::uint32_t* idx) const noexcept {
    constexpr auto offsets = pattern_jass::pattern_offsets();
    double pat_mg = 0.0, pat_eg = 0.0;
    for (std::size_t i = 0; i < pattern_jass::NUM_PATTERNS; ++i) {
        const std::size_t col = offsets[i] + idx[i];
        pat_mg += static_cast<double>(w_.pat_mg[col]);
        pat_eg += static_cast<double>(w_.pat_eg[col]);
    }

    // Dense extras (king PST, material, mobility, balance).
    std::array<float, NUM_EXTRAS> extras{};
    compute_extras(pos, extras);
    double ext_mg = 0.0, ext_eg = 0.0;
    for (std::size_t e = 0; e < NUM_EXTRAS; ++e) {
        const double x = static_cast<double>(extras[e]);
        ext_mg += static_cast<double>(w_.ext_mg[e]) * x;
        ext_eg += static_cast<double>(w_.ext_eg[e]) * x;
    }

    // Phase interpolation : wmg = stage/40, weg = 1 − wmg.
    const double wmg = static_cast<double>(game_stage(pos)) / MAX_PIECES;
    const double weg = 1.0 - wmg;
    const double eval_black = wmg * (pat_mg + ext_mg) + weg * (pat_eg + ext_eg);

    const double cp_black = eval_black * 100.0 / static_cast<double>(w_.scale);
    const double cp_stm   = (pos.side_to_move() == Color::Black) ? cp_black : -cp_black;

    if (cp_stm >  20000.0) return  20000;
    if (cp_stm < -20000.0) return -20000;
    return static_cast<int>(cp_stm);
}

std::unique_ptr<ScanEvalNetwork> load_scan_eval_network(const std::string& path,
                                                        std::string* err) {
    auto w = load_scan_weights(path, err);
    if (!w) return nullptr;
    return std::make_unique<ScanEvalNetwork>(std::move(*w));
}

}  // namespace jass::scan_eval

namespace jass {

std::unique_ptr<INetwork> load_eval_network(const std::string& path,
                                            std::string* err) {
    // Peek the version word (offset 4) to dispatch v3 vs v1/v2.
    std::ifstream f(path, std::ios::binary);
    if (!f) { if (err) *err = "cannot open " + path; return nullptr; }
    unsigned char hdr[8];
    f.read(reinterpret_cast<char*>(hdr), 8);
    if (!f) { if (err) *err = "cannot read header of " + path; return nullptr; }
    const std::uint32_t version =
          static_cast<std::uint32_t>(hdr[4])
        | (static_cast<std::uint32_t>(hdr[5]) <<  8)
        | (static_cast<std::uint32_t>(hdr[6]) << 16)
        | (static_cast<std::uint32_t>(hdr[7]) << 24);
    f.close();

    if (version == scan_eval::V3_VERSION) {
        return scan_eval::load_scan_eval_network(path, err);
    }
    return load_pattern_jass_network(path, err);
}

}  // namespace jass
