// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "scan_eval.hpp"

#include "bitboard.hpp"
#include "board.hpp"
#include "pattern_jass_bridge.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>

// pattern_jass is compiled into jass_lib; reach it via relative include
// (same pattern as pattern_jass_bridge.cpp).
#include "../pattern_jass/src/pattern.hpp"
#include "../pattern_jass/src/weights.hpp"

#include <array>
#include <cstring>
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

// Set (not count) of empty squares a king can slide to (union over 4 diagonals).
Bitboard king_reach(Bitboard kings, Bitboard empty) noexcept {
    Bitboard reach = 0;
    for (const ShiftFn shift : ALL_SHIFTS) {
        Bitboard frontier = shift(kings) & empty;
        while (frontier) { reach |= frontier; frontier = shift(frontier) & empty; }
    }
    return reach;
}

// Squares attacked by `men` = squares x where an enemy man could capture a king
// on x : a man sits diagonally adjacent on one side (x+d) and the square beyond
// (x−d) is empty, for any of the 4 diagonals (FMJD men capture forward & back).
// attacked_d = shift_{−d}(men) & shift_{+d}(empty), OR'd over the 4 directions.
Bitboard man_attacks(Bitboard men, Bitboard empty) noexcept {
    return (shift_se(men) & shift_nw(empty))
         | (shift_sw(men) & shift_ne(empty))
         | (shift_ne(men) & shift_sw(empty))
         | (shift_nw(men) & shift_se(empty));
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

#ifdef JASS_ENDGAME_FEATURES
    // Endgame king-interaction (Direction B). central = how central each king sits
    // (0 edge .. 9 centre) ; prox = how close each king is to the enemy (9 adjacent
    // .. 0 far, Chebyshev on row/col). Few kings in endgames -> cheap; gated.
    auto central = [](Square s) -> float {
        const float r = static_cast<float>(row_of(s));
        const float c = static_cast<float>(col_of(s));
        return (4.5f - std::fabs(r - 4.5f)) + (4.5f - std::fabs(c - 4.5f));
    };
    auto min_dist = [](Square ks, Bitboard targets) -> int {
        const int kr = row_of(ks), kc = col_of(ks);
        int best = 9;
        for (Bitboard b = targets; b; ) {
            const Square t = pop_lsb(b);
            const int d = std::max(std::abs(row_of(t) - kr), std::abs(col_of(t) - kc));
            if (d < best) best = d;
        }
        return best;
    };
    const Bitboard whites = pos.white_men() | pos.white_kings();
    const Bitboard blacks = pos.black_men() | pos.black_kings();
    float bk_c = 0, wk_c = 0, bk_p = 0, wk_p = 0;
    for (Bitboard b = pos.black_kings(); b; ) {
        const Square s = pop_lsb(b);
        bk_c += central(s);
        if (whites) bk_p += static_cast<float>(9 - min_dist(s, whites));
    }
    for (Bitboard b = pos.white_kings(); b; ) {
        const Square s = pop_lsb(b);
        wk_c += central(s);
        if (blacks) wk_p += static_cast<float>(9 - min_dist(s, blacks));
    }
    out[EXTRA_BK_CENTRAL] = bk_c;  out[EXTRA_WK_CENTRAL] = wk_c;
    out[EXTRA_BK_PROX]    = bk_p;  out[EXTRA_WK_PROX]    = wk_p;
#endif

#ifdef JASS_KING_MOBILITY
    // Scan's king_mob (audit-faithful) : split each king's empty slide squares
    // into SAFE (not attacked by an enemy man) and DENIED (attacked → the king
    // would be capturable there). The denial count is the confinement gradient.
    const Bitboard empty_km = pos.empties();
    const Bitboard watt = man_attacks(pos.white_men(), empty_km);  // squares attacked by WHITE men
    const Bitboard batt = man_attacks(pos.black_men(), empty_km);  // squares attacked by BLACK men
    const Bitboard bkr  = king_reach(pos.black_kings(), empty_km);
    const Bitboard wkr  = king_reach(pos.white_kings(), empty_km);
    out[EXTRA_BK_SAFEMOB] = static_cast<float>(popcount(bkr & ~watt));
    out[EXTRA_WK_SAFEMOB] = static_cast<float>(popcount(wkr & ~batt));
    out[EXTRA_BK_DENIED]  = static_cast<float>(popcount(bkr & watt));
    out[EXTRA_WK_DENIED]  = static_cast<float>(popcount(wkr & batt));
#endif
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
    const std::uint32_t base_ver = version & V_VERMASK;
    const bool is_v4 = (base_ver == V4_VERSION);
    if (base_ver != V3_VERSION && !is_v4) {
        if (err) *err = "not a v3/v4 PJTW (version " + std::to_string(version) + ")";
        return std::nullopt;
    }
    // Self-describing king/men marker : a wrong binary/weights pairing fails loudly
    // instead of silently mis-evaluating. Legacy files (no SELFDESC bit) load as-is.
    if ((version & V_SELFDESC_BIT) &&
        ((((version & V_KING_BIT) != 0)) != KING_AWARE_PATTERNS)) {
        if (err) *err = std::string("king-aware mismatch: this .pjtw is ")
            + (((version & V_KING_BIT) != 0) ? "KING-AWARE" : "men-only")
            + " but this binary is " + (KING_AWARE_PATTERNS ? "KING-AWARE" : "men-only")
            + " (use the matching build / (re)train with"
            + (((version & V_KING_BIT) != 0) ? "" : "out") + " --king-patterns)";
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
    const std::size_t lin_bytes = V3_HEADER + total * sizeof(std::int32_t);
    // FM section (v4) : uint32 fm_rank, fm_hash, fm_npat, then float32 V[...].
    std::uint32_t fm_rank = 0, fm_hash = 0, fm_npat = 0;
    std::size_t expected = lin_bytes;
    if (is_v4) {
        if (raw.size() < lin_bytes + 12) {
            if (err) *err = "v4 file too short for FM header"; return std::nullopt;
        }
        fm_rank = rd_u32(raw.data() + lin_bytes + 0);
        fm_hash = rd_u32(raw.data() + lin_bytes + 4);
        fm_npat = rd_u32(raw.data() + lin_bytes + 8);
        if (fm_npat != pattern_jass::NUM_PATTERNS) {
            if (err) *err = "fm_npat " + std::to_string(fm_npat) + " != "
                          + std::to_string(pattern_jass::NUM_PATTERNS);
            return std::nullopt;
        }
        const std::size_t n_fm =
            static_cast<std::size_t>(fm_npat) * fm_hash * fm_rank;
        expected = lin_bytes + 12 + n_fm * sizeof(float);
    }
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

    if (is_v4) {
        w.fm_rank = fm_rank;
        w.fm_hash = fm_hash;
        const std::size_t n_fm =
            static_cast<std::size_t>(fm_npat) * fm_hash * fm_rank;
        w.fm_v.resize(n_fm);
        // FM floats start right after the 12-byte FM header (p is currently at
        // lin_bytes after reading all linear int32s).
        const unsigned char* fp = raw.data() + lin_bytes + 12;
        std::memcpy(w.fm_v.data(), fp, n_fm * sizeof(float));
    }
    return w;
}

int ScanEvalNetwork::evaluate(const Position& pos) const noexcept {
    // Patterns (sparse one-hots, base-3), recomputed from scratch. Occupancy is
    // men-only or men|kings (pat_black/pat_white) per the king-aware switch. The
    // accumulator path (evaluate_with_idx) shares everything below.
    std::array<std::uint32_t, pattern_jass::NUM_PATTERNS> idx{};
    pattern_jass::extract_all(pat_black(pos), pat_white(pos), idx);
    return evaluate_with_idx(pos, idx.data());
}

int ScanEvalNetwork::evaluate_with_idx(const Position& pos,
                                       const std::uint32_t* idx) const noexcept {
    constexpr auto offsets = pattern_jass::pattern_offsets();
    double pat_mg = 0.0, pat_eg = 0.0;
    for (std::size_t i = 0; i < pattern_jass::NUM_PATTERNS; ++i) {
        // Bucket hashing : reduce the full base-3 index mod PATTERN_HASH (no-op
        // when PATTERN_HASH == POW3[SIZE]). offsets[i] = i * BUCKETS_PER_PATTERN.
        const std::size_t col =
            offsets[i] + (idx[i] % pattern_jass::BUCKETS_PER_PATTERN);
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

    // Phase interpolation : sharpenable ramp (default = legacy stage/40).
    const double wmg = phase_wmg(game_stage(pos));
    const double weg = 1.0 - wmg;
    const double eval_black = wmg * (pat_mg + ext_mg) + weg * (pat_eg + ext_eg);

    // Linear eval in piece-units, plus the optional FM pairwise pattern term
    // (PJTW v4) — also in piece-units, in black-POV, using the same per-pattern
    // buckets `idx` the accumulator maintains, hashed to fm_hash slots.
    double pu_black = eval_black / static_cast<double>(w_.scale);
    if (w_.fm_rank != 0) {
        const std::uint32_t k = w_.fm_rank, H = w_.fm_hash;
        double fm = 0.0;
        // ½ Σ_f [ (Σ_p V_{p,f})² − Σ_p V_{p,f}² ], factor loop outermost.
        for (std::uint32_t f = 0; f < k; ++f) {
            double a = 0.0, bsq = 0.0;
            for (std::size_t p = 0; p < pattern_jass::NUM_PATTERNS; ++p) {
                const std::size_t slot = p * H + (idx[p] % H);
                const double v = static_cast<double>(w_.fm_v[slot * k + f]);
                a += v; bsq += v * v;
            }
            fm += a * a - bsq;
        }
        pu_black += 0.5 * fm;
    }

#ifdef JASS_DRAWISH_SCALING
    // Drawish-material draw-scaling (Scan, Normal variant) — the one non-linear
    // term Scan has that the linear net cannot learn. When the side AHEAD has too
    // little to win and the DEFENDER has a king, shrink the score toward a draw:
    // winner ≤3 pieces → ÷8 ; else equal kings & |Δmen|≤1 → ÷2. Play-time only
    // (the trained WDL weights are unchanged). Gated; -DJASS_DRAWISH_SCALING.
    {
        const int nwm = popcount(pos.white_men()), nwk = popcount(pos.white_kings());
        const int nbm = popcount(pos.black_men()), nbk = popcount(pos.black_kings());
        const bool near_equal = (nwk == nbk) && ((nwm > nbm ? nwm - nbm : nbm - nwm) <= 1);
        if (pu_black > 0.0 && nwk != 0) {            // black ahead, white (loser) has a king
            if (nbm + nbk <= 3)  pu_black *= 0.125;
            else if (near_equal) pu_black *= 0.5;
        } else if (pu_black < 0.0 && nbk != 0) {     // white ahead, black (loser) has a king
            if (nwm + nwk <= 3)  pu_black *= 0.125;
            else if (near_equal) pu_black *= 0.5;
        }
    }
#endif

    const double cp_black = pu_black * 100.0;
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

    const std::uint32_t base_ver = version & scan_eval::V_VERMASK;  // strip self-desc/king bits
    if (base_ver == scan_eval::V3_VERSION || base_ver == scan_eval::V4_VERSION) {
        return scan_eval::load_scan_eval_network(path, err);
    }
    return load_pattern_jass_network(path, err);
}

}  // namespace jass
