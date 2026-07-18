// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern_network.hpp"

#include "bitboard.hpp"

#include <algorithm>
#include <cstring>
#include <fstream>
#include <string>

namespace jass {

namespace {

// Per-square state encoding. Two bases are supported:
//   base=5 (legacy JPAT v1/v2): 0=empty, 1=W-man, 2=W-king, 3=B-man, 4=B-king
//   base=3 (D2 / Scan-aligned, JPAT v3): 0=empty, 1=white(*), 2=black(*)
// Kings are amalgamated with men in base=3; their separate value is
// captured by the king_value structural skeleton (cf. JPAT v2 / v3).
inline std::uint8_t encode_state(const Position& pos, std::uint8_t fmjd_sq,
                                 std::uint8_t base) noexcept {
    const Square s = static_cast<Square>(fmjd_sq);
    const Piece  p = pos.piece_at(s);
    if (base == 3) {
        switch (p) {
            case Piece::None:      return 0;
            case Piece::WhiteMan:
            case Piece::WhiteKing: return 1;
            case Piece::BlackMan:
            case Piece::BlackKing: return 2;
        }
        return 0;
    }
    switch (p) {
        case Piece::None:      return 0;
        case Piece::WhiteMan:  return 1;
        case Piece::WhiteKing: return 2;
        case Piece::BlackMan:  return 3;
        case Piece::BlackKing: return 4;
    }
    return 0;
}

// V1 default pattern set: 8 patterns × 4 squares each. Chosen to cover
// 8 spatial regions of the board (NW / N / mid-W / centre / centre-S /
// mid-E / S / SE). Coverage 32/50 squares — not exhaustive but enough
// to test the architecture. Adjust freely once we know patterns help.
constexpr std::array<std::array<std::uint8_t, 4>, 8> V1_PATTERNS = {{
    {{ 1,  2,  6,  7}},  // NW
    {{ 3,  4,  8,  9}},  // N
    {{16, 17, 21, 22}},  // mid-W
    {{18, 19, 23, 24}},  // centre
    {{25, 26, 30, 31}},  // centre-S
    {{32, 33, 37, 38}},  // mid-S
    {{42, 43, 47, 48}},  // S
    {{44, 45, 49, 50}},  // SE
}};

// V2 default pattern set: 16 patterns × 8 squares each. Built from
// 4×4 board regions at row/col offsets ∈ {0,2,4,6}² (16 regions, each
// covering 8 playable squares). Full coverage of the 50 playable
// squares with overlap (every square is in 1-4 patterns). Total
// weight count: 16 × 5^8 = 6 250 000 int32 = 25 MB on disk.
constexpr std::array<std::array<std::uint8_t, 8>, 16> V2_PATTERNS = {{
    {{ 1,  2,  6,  7, 11, 12, 16, 17}},  // (r=0, c=0)  NW corner
    {{ 2,  3,  7,  8, 12, 13, 17, 18}},  // (r=0, c=2)
    {{ 3,  4,  8,  9, 13, 14, 18, 19}},  // (r=0, c=4)
    {{ 4,  5,  9, 10, 14, 15, 19, 20}},  // (r=0, c=6)  NE corner
    {{11, 12, 16, 17, 21, 22, 26, 27}},  // (r=2, c=0)
    {{12, 13, 17, 18, 22, 23, 27, 28}},  // (r=2, c=2)
    {{13, 14, 18, 19, 23, 24, 28, 29}},  // (r=2, c=4)  centre
    {{14, 15, 19, 20, 24, 25, 29, 30}},  // (r=2, c=6)
    {{21, 22, 26, 27, 31, 32, 36, 37}},  // (r=4, c=0)
    {{22, 23, 27, 28, 32, 33, 37, 38}},  // (r=4, c=2)
    {{23, 24, 28, 29, 33, 34, 38, 39}},  // (r=4, c=4)
    {{24, 25, 29, 30, 34, 35, 39, 40}},  // (r=4, c=6)
    {{31, 32, 36, 37, 41, 42, 46, 47}},  // (r=6, c=0)  SW corner
    {{32, 33, 37, 38, 42, 43, 47, 48}},  // (r=6, c=2)
    {{33, 34, 38, 39, 43, 44, 48, 49}},  // (r=6, c=4)
    {{34, 35, 39, 40, 44, 45, 49, 50}},  // (r=6, c=6)  SE corner
}};

// V3 Scan-inspired pattern set: 8 vertical-strip patterns × 12 squares
// each. Geometry = (6 rows × 2 col-within-row) — captures forward-push
// dynamics that 4×4 blocks (v2) miss. Approximates the verticals Scan
// extracts via Perm_0/Perm_1 + 4-column bit-shifts (cf.
// docs/archives/SCAN_ARCHITECTURE_NOTES.md §3) without reproducing the exact
// bitboard tricks (those depend on Scan's sparse layout, different
// from jass's bitboard convention).
//
// Layout : 4 strips top (rows 1-6) × 4 strips bottom (rows 5-10), each
// covering 2 adjacent col-within-row values. Strips overlap so every
// square is in 2-4 patterns. Total weights: 8 × 3^12 = ~4.25M (~17 MB
// JPAT base-3).
constexpr std::array<std::array<std::uint8_t, 12>, 8> V3_PATTERNS = {{
    // Top half (rows 1-6, i.e. row indices 0..5)
    {{ 1,  2,  6,  7, 11, 12, 16, 17, 21, 22, 26, 27}},  // cols 0-1
    {{ 2,  3,  7,  8, 12, 13, 17, 18, 22, 23, 27, 28}},  // cols 1-2
    {{ 3,  4,  8,  9, 13, 14, 18, 19, 23, 24, 28, 29}},  // cols 2-3
    {{ 4,  5,  9, 10, 14, 15, 19, 20, 24, 25, 29, 30}},  // cols 3-4
    // Bottom half (rows 5-10, row indices 4..9)
    {{21, 22, 26, 27, 31, 32, 36, 37, 41, 42, 46, 47}},
    {{22, 23, 27, 28, 32, 33, 37, 38, 42, 43, 47, 48}},
    {{23, 24, 28, 29, 33, 34, 38, 39, 43, 44, 48, 49}},
    {{24, 25, 29, 30, 34, 35, 39, 40, 44, 45, 49, 50}},
}};

// V4 long vertical strips: 8 patterns × 14 squares each (7 rows × 2
// col-within-row). Pushes pattern length toward Scan's 12-square mark
// + adds 1-2 rows of context. Total: 8 × 3^14 = ~38M weights base-3
// (~153 MB JPAT). Memory-intensive (LBFGS history needs ~1.5 GB) but
// fits in CCX33's 32 GB. The architectural test for "patterns ratent
// peut-être les motifs long-distance" hypothesis post-H1-H4 flat.
constexpr std::array<std::array<std::uint8_t, 14>, 8> V4_PATTERNS = {{
    // Top half (rows 1-7, indices 0..6)
    {{ 1,  2,  6,  7, 11, 12, 16, 17, 21, 22, 26, 27, 31, 32}},  // cols 0-1
    {{ 2,  3,  7,  8, 12, 13, 17, 18, 22, 23, 27, 28, 32, 33}},  // cols 1-2
    {{ 3,  4,  8,  9, 13, 14, 18, 19, 23, 24, 28, 29, 33, 34}},  // cols 2-3
    {{ 4,  5,  9, 10, 14, 15, 19, 20, 24, 25, 29, 30, 34, 35}},  // cols 3-4
    // Bottom half (rows 4-10, indices 3..9)
    {{16, 17, 21, 22, 26, 27, 31, 32, 36, 37, 41, 42, 46, 47}},
    {{17, 18, 22, 23, 27, 28, 32, 33, 37, 38, 42, 43, 47, 48}},
    {{18, 19, 23, 24, 28, 29, 33, 34, 38, 39, 43, 44, 48, 49}},
    {{19, 20, 24, 25, 29, 30, 34, 35, 39, 40, 44, 45, 49, 50}},
}};

constexpr char          JPAT_MAGIC[4]     = {'J', 'P', 'A', 'T'};
constexpr std::uint32_t JPAT_VERSION_V1   = 1;
constexpr std::uint32_t JPAT_VERSION_V2   = 2;
constexpr std::uint32_t JPAT_VERSION_V3   = 3;
constexpr std::uint32_t JPAT_VERSION_V4   = 4;
constexpr std::uint32_t JPAT_VERSION_V5   = 5;
constexpr std::uint32_t JPAT_VERSION_V6   = 6;
constexpr std::uint32_t JPAT_VERSION_V7   = 7;
constexpr std::uint32_t JPAT_VERSION_V8   = 8;

// H4 / JPAT v6 — diagonal neighbors per FMJD square (1..50), padded
// with 0 for fewer-than-4 neighbors (corners and edges). 0 is used as
// sentinel (never a valid FMJD square). Generated by tools/...
// (matches the python helper used in king_mobility_feature).
inline constexpr std::array<std::array<std::uint8_t, 4>, 50> KING_DIAG_NEIGHBORS = {{
    {{  6,  7,  0,  0 }},  // 1
    {{  7,  8,  0,  0 }},  // 2
    {{  8,  9,  0,  0 }},  // 3
    {{  9, 10,  0,  0 }},  // 4
    {{ 10,  0,  0,  0 }},  // 5
    {{  1, 11,  0,  0 }},  // 6
    {{  1,  2, 11, 12 }},  // 7
    {{  2,  3, 12, 13 }},  // 8
    {{  3,  4, 13, 14 }},  // 9
    {{  4,  5, 14, 15 }},  // 10
    {{  6,  7, 16, 17 }},  // 11
    {{  7,  8, 17, 18 }},  // 12
    {{  8,  9, 18, 19 }},  // 13
    {{  9, 10, 19, 20 }},  // 14
    {{ 10, 20,  0,  0 }},  // 15
    {{ 11, 21,  0,  0 }},  // 16
    {{ 11, 12, 21, 22 }},  // 17
    {{ 12, 13, 22, 23 }},  // 18
    {{ 13, 14, 23, 24 }},  // 19
    {{ 14, 15, 24, 25 }},  // 20
    {{ 16, 17, 26, 27 }},  // 21
    {{ 17, 18, 27, 28 }},  // 22
    {{ 18, 19, 28, 29 }},  // 23
    {{ 19, 20, 29, 30 }},  // 24
    {{ 20, 30,  0,  0 }},  // 25
    {{ 21, 31,  0,  0 }},  // 26
    {{ 21, 22, 31, 32 }},  // 27
    {{ 22, 23, 32, 33 }},  // 28
    {{ 23, 24, 33, 34 }},  // 29
    {{ 24, 25, 34, 35 }},  // 30
    {{ 26, 27, 36, 37 }},  // 31
    {{ 27, 28, 37, 38 }},  // 32
    {{ 28, 29, 38, 39 }},  // 33
    {{ 29, 30, 39, 40 }},  // 34
    {{ 30, 40,  0,  0 }},  // 35
    {{ 31, 41,  0,  0 }},  // 36
    {{ 31, 32, 41, 42 }},  // 37
    {{ 32, 33, 42, 43 }},  // 38
    {{ 33, 34, 43, 44 }},  // 39
    {{ 34, 35, 44, 45 }},  // 40
    {{ 36, 37, 46, 47 }},  // 41
    {{ 37, 38, 47, 48 }},  // 42
    {{ 38, 39, 48, 49 }},  // 43
    {{ 39, 40, 49, 50 }},  // 44
    {{ 40, 50,  0,  0 }},  // 45
    {{ 41,  0,  0,  0 }},  // 46
    {{ 41, 42,  0,  0 }},  // 47
    {{ 42, 43,  0,  0 }},  // 48
    {{ 43, 44,  0,  0 }},  // 49
    {{ 44, 45,  0,  0 }},  // 50
}};

// H4 / JPAT v6 — king mobility proxy : sum over white kings of the
// number of empty diag neighbors, minus same for black kings. Cheap
// (no move-gen call); doesn't distinguish safe vs attacked moves
// (Scan does). Should rank-correlate with true king mobility.
inline int compute_king_mobility(const Position& pos) noexcept {
    const Bitboard occ = pos.white_men() | pos.white_kings()
                       | pos.black_men() | pos.black_kings();
    auto count_free_diag = [&](Bitboard kings) {
        int total = 0;
        while (kings) {
            const Square s = pop_lsb(kings);
            const auto&  nbrs = KING_DIAG_NEIGHBORS[static_cast<std::size_t>(s) - 1];
            for (std::uint8_t nbr : nbrs) {
                if (nbr == 0) break;  // sentinel — no more neighbors
                const Bitboard b = std::uint64_t{1} << (nbr - 1);
                if ((occ & b) == 0) ++total;
            }
        }
        return total;
    };
    return count_free_diag(pos.white_kings()) - count_free_diag(pos.black_kings());
}

// G3b / JPAT v5 — stage interpolation constants. Stage is an integer
// in [0, STAGE_SIZE] where 0 = opening (full material) and STAGE_SIZE
// = bare endgame. The eval interpolates:
//   score = (acc_mg * (STAGE_SIZE - stage) + acc_eg * stage) / STAGE_SIZE
// When acc_mg == acc_eg the result is acc_mg regardless of stage — the
// trick used to preserve v1-v4 semantics when loading older files.
constexpr int STAGE_SIZE = 300;
// Opening material baseline = 40 (20 W men + 20 B men) ; weight kings
// as 2× men so deep endgames with mostly kings count as "more endgamey"
// than the raw piece count would suggest.
constexpr int STAGE_OPEN_PHASE = 40;

inline int compute_stage(const Position& pos) noexcept {
    const int wm = popcount(pos.white_men());
    const int bm = popcount(pos.black_men());
    const int wk = popcount(pos.white_kings());
    const int bk = popcount(pos.black_kings());
    const int phase = wm + bm + 2 * (wk + bk);
    const int s = STAGE_SIZE * (STAGE_OPEN_PHASE - phase) / STAGE_OPEN_PHASE;
    if (s < 0) return 0;
    if (s > STAGE_SIZE) return STAGE_SIZE;
    return s;
}

// Files (columns of dark squares) split into left/right halves for the
// G3a "balance" feature. FMJD square s has column index (s-1) % 5
// taking values 0..4. We call cols 0-1 "left", cols 3-4 "right",
// col 2 is the center file (neutral, contributes 0).
inline int file_side(std::uint8_t fmjd_sq) noexcept {
    const int col = (fmjd_sq - 1) % 5;
    if (col <  2) return -1;  // left
    if (col >  2) return +1;  // right
    return 0;                 // center file
}

// White-POV balance: positive when whites are skewed RIGHT relative
// to blacks. For each white piece, add file_side(s); for each black
// piece, subtract file_side(s). Sum across all pieces of both
// colours via iteration over the 4 bitboards.
inline int compute_skew(const Position& pos) noexcept {
    int s = 0;
    auto add_bb = [&](Bitboard bb, int sign) {
        while (bb) {
            const Square sq = pop_lsb(bb);
            s += sign * file_side(static_cast<std::uint8_t>(sq));
        }
    };
    add_bb(pos.white_men(),   +1);
    add_bb(pos.white_kings(), +1);
    add_bb(pos.black_men(),   -1);
    add_bb(pos.black_kings(), -1);
    return s;
}

inline std::size_t pow_n(std::size_t base, std::size_t k) noexcept {
    std::size_t r = 1;
    for (std::size_t i = 0; i < k; ++i) r *= base;
    return r;
}
inline std::size_t pow5(std::size_t k) noexcept { return pow_n(5, k); }

}  // namespace

PatternNetwork::PatternNetwork() = default;

PatternNetwork PatternNetwork::default_v1() {
    PatternNetwork net;
    for (const auto& p : V1_PATTERNS) {
        net.add_pattern(std::vector<std::uint8_t>(p.begin(), p.end()));
    }
    return net;
}

PatternNetwork PatternNetwork::default_v2() {
    PatternNetwork net;
    for (const auto& p : V2_PATTERNS) {
        net.add_pattern(std::vector<std::uint8_t>(p.begin(), p.end()));
    }
    return net;
}

PatternNetwork PatternNetwork::default_v3() {
    PatternNetwork net;
    for (const auto& p : V3_PATTERNS) {
        net.add_pattern(std::vector<std::uint8_t>(p.begin(), p.end()));
    }
    return net;
}

PatternNetwork PatternNetwork::default_v4() {
    PatternNetwork net;
    for (const auto& p : V4_PATTERNS) {
        net.add_pattern(std::vector<std::uint8_t>(p.begin(), p.end()));
    }
    return net;
}

void PatternNetwork::add_pattern(const std::vector<std::uint8_t>& squares) {
    Pattern p;
    p.squares = squares;
    p.weights.assign(pow_n(encoding_base_, squares.size()), 0);
    patterns_.push_back(std::move(p));
}

void PatternNetwork::set_encoding_base(std::uint8_t b) noexcept {
    if (b != 3 && b != 5) return;  // ignore invalid
    encoding_base_ = b;
    for (Pattern& p : patterns_) {
        p.weights.assign(pow_n(encoding_base_, p.squares.size()), 0);
    }
}

void PatternNetwork::configure_mlp(std::uint8_t hidden) noexcept {
    mlp_hidden_ = hidden;
    const std::size_t n = patterns_.size();
    const std::size_t h = static_cast<std::size_t>(hidden);
    mlp_w1_.assign(n * h, 0.0f);
    mlp_b1_.assign(h, 0.0f);
    mlp_w2_.assign(h, 0.0f);
    mlp_b2_ = 0.0f;
}

void PatternNetwork::configure_v8(std::uint8_t embed_dim,
                                  std::uint8_t hidden) noexcept {
    embed_dim_     = embed_dim;
    v8_mlp_hidden_ = hidden;
    const std::size_t ed = static_cast<std::size_t>(embed_dim);
    const std::size_t h  = static_cast<std::size_t>(hidden);
    const std::size_t n  = patterns_.size();
    embeddings_.resize(n);
    for (std::size_t pi = 0; pi < n; ++pi) {
        const std::size_t nbuckets = pow_n(encoding_base_,
                                           patterns_[pi].squares.size());
        embeddings_[pi].assign(nbuckets * ed, 0.0f);
    }
    v8_mlp_w1_.assign(n * ed * h, 0.0f);
    v8_mlp_b1_.assign(h, 0.0f);
    v8_mlp_w2_.assign(h, 0.0f);
    v8_mlp_b2_ = 0.0f;
}

int PatternNetwork::evaluate(const Position& pos) const noexcept {
    // JPAT v8 — pattern embeddings + MLP end-to-end (paradigm shift A).
    // Replaces the v1-v7 linear pattern sum with an embedding lookup +
    // MLP forward. Skeleton (bias + man*mat_diff + king*king_diff) is
    // retained as an int32 residual ; phase split / king PST / balance /
    // mobility / v7 MLP head are NOT applied in v8 (they would double-
    // count features the embedding MLP already learns).
    if (embed_dim_ > 0) {
        std::int32_t acc = bias_;
        if (man_value_ != 0 || king_value_ != 0) {
            // Skeleton mat/king diffs : trainer (tools/train_pattern_embed.py
            // + train_pattern.py) flips these to STM-relative for STM=Black
            // records before feeding the model. We mirror that here so the
            // C++ eval matches the Python model exactly. Pattern indices
            // remain board-absolute (no flip) — the model learned that
            // mixed convention during training.
            int mat_diff  = popcount(pos.white_men())   - popcount(pos.black_men());
            int king_diff = popcount(pos.white_kings()) - popcount(pos.black_kings());
            if (v8_stm_flip_ != 0 && pos.side_to_move() == Color::Black) {
                mat_diff  = -mat_diff;
                king_diff = -king_diff;
            }
            acc += man_value_ * mat_diff + king_value_ * king_diff;
        }
        const std::uint8_t  base = encoding_base_;
        const std::size_t   ed   = static_cast<std::size_t>(embed_dim_);
        const std::size_t   h    = static_cast<std::size_t>(v8_mlp_hidden_);
        const std::size_t   n    = patterns_.size();
        // Concat all per-pattern embeddings into one (n*ed) float vector.
        // Inline-sized for the typical pattern set (≤ 32 patterns × ≤ 16
        // embed_dim = 512 floats max).
        constexpr std::size_t MAX_CONCAT = 32 * 16;
        std::array<float, MAX_CONCAT> concat{};
        const std::size_t total = n * ed;
        if (total > MAX_CONCAT) return (pos.side_to_move() == Color::White) ? acc : -acc;
        for (std::size_t pi = 0; pi < n; ++pi) {
            const Pattern& p = patterns_[pi];
            std::size_t idx = 0, mult = 1;
            for (std::uint8_t sq : p.squares) {
                idx += static_cast<std::size_t>(encode_state(pos, sq, base)) * mult;
                mult *= base;
            }
            const std::vector<float>& tbl = embeddings_[pi];
            const std::size_t base_off = idx * ed;
            if (base_off + ed <= tbl.size()) {
                for (std::size_t e = 0; e < ed; ++e) {
                    concat[pi * ed + e] = tbl[base_off + e];
                }
            }
        }
        // MLP forward : hidden = ReLU(b1 + concat @ w1) ; out = b2 + hidden @ w2.
        // w1 layout : [in_dim, h] row-major, in_dim = n*ed.
        float mlp_out = v8_mlp_b2_;
        for (std::size_t hi = 0; hi < h; ++hi) {
            float acc_h = v8_mlp_b1_[hi];
            for (std::size_t ii = 0; ii < total; ++ii) {
                acc_h += concat[ii] * v8_mlp_w1_[ii * h + hi];
            }
            if (acc_h > 0.0f) mlp_out += acc_h * v8_mlp_w2_[hi];
        }
        acc += static_cast<std::int32_t>(mlp_out);
        return (pos.side_to_move() == Color::White) ? acc : -acc;
    }

    // White-POV. G3b / JPAT v5 phase split: we maintain TWO accumulators
    // (mg / eg) and interpolate by game stage at the end. For v1-v4
    // networks the EG counterparts are all zero (load() leaves them
    // at default), which makes the bool `has_phase_split` below false
    // — we then skip the EG accumulator and interpolation entirely
    // and return acc_mg, exactly matching the v1-v4 mono-phase eval.
    const bool has_phase_split =
        bias_eg_       != 0 || man_value_eg_  != 0 ||
        king_value_eg_ != 0 || balance_eg_    != 0 ||
        mobility_eg_   != 0 ||
        std::any_of(king_pst_eg_.begin(), king_pst_eg_.end(),
                    [](std::int32_t w) { return w != 0; });

    std::int32_t acc_mg = bias_;
    std::int32_t acc_eg = has_phase_split ? bias_eg_ : 0;

    // D1 hybrid skeleton (mg/eg split when enabled). Material + king
    // count diffs.
    if (man_value_ != 0 || king_value_ != 0
     || man_value_eg_ != 0 || king_value_eg_ != 0) {
        const int wm = popcount(pos.white_men());
        const int bm = popcount(pos.black_men());
        const int wk = popcount(pos.white_kings());
        const int bk = popcount(pos.black_kings());
        const int mat_diff  = wm - bm;
        const int king_diff = wk - bk;
        acc_mg += man_value_    * mat_diff + king_value_    * king_diff;
        if (has_phase_split) {
            acc_eg += man_value_eg_ * mat_diff + king_value_eg_ * king_diff;
        }
    }

    // G3a + G3b — king PST + balance L/R.
    if (balance_ != 0 || balance_eg_ != 0) {
        const int skew = compute_skew(pos);
        acc_mg += balance_ * skew;
        if (has_phase_split) acc_eg += balance_eg_ * skew;
    }

    // H4 / JPAT v6 — king mobility (free diag neighbors per king).
    // Skipped when both weights 0 (preserves legacy v1-v5 eval exactly).
    if (mobility_mg_ != 0 || mobility_eg_ != 0) {
        const int mob = compute_king_mobility(pos);
        acc_mg += mobility_mg_ * mob;
        if (has_phase_split) acc_eg += mobility_eg_ * mob;
    }
    Bitboard wk = pos.white_kings();
    while (wk) {
        const std::size_t s = static_cast<std::size_t>(pop_lsb(wk));
        acc_mg += king_pst_[s - 1];
        if (has_phase_split) acc_eg += king_pst_eg_[s - 1];
    }
    Bitboard bk = pos.black_kings();
    while (bk) {
        const std::size_t s = static_cast<std::size_t>(pop_lsb(bk));
        acc_mg -= king_pst_[50 - s];
        if (has_phase_split) acc_eg -= king_pst_eg_[50 - s];
    }

    // Patterns stay mono-phase in v5+; contribute equally to mg and eg.
    // For JPAT v7 (hybrid MLP head) we also remember each pattern's
    // bucket value individually, to feed the MLP head as input.
    const std::uint8_t base = encoding_base_;
    constexpr std::size_t MAX_PATTERNS_INLINE = 32;
    std::array<std::int32_t, MAX_PATTERNS_INLINE> pattern_values{};
    const bool       has_mlp     = (mlp_hidden_ > 0);
    const std::size_t n_patterns = patterns_.size();
    for (std::size_t pi = 0; pi < n_patterns; ++pi) {
        const Pattern& p = patterns_[pi];
        std::size_t idx = 0;
        std::size_t mult = 1;
        for (std::uint8_t sq : p.squares) {
            idx += static_cast<std::size_t>(encode_state(pos, sq, base)) * mult;
            mult *= base;
        }
        std::int32_t w = 0;
        if (idx < p.weights.size()) {
            w = p.weights[idx];
            acc_mg += w;
            if (has_phase_split) acc_eg += w;
        }
        if (has_mlp && pi < MAX_PATTERNS_INLINE) {
            pattern_values[pi] = w;
        }
    }

    // JPAT v7 — hybrid MLP head (MG-only residual). Single hidden layer
    // with ReLU. Tiny float computation (~145 ops for 8 patterns × 16
    // hidden) added on top of the linear pattern sum.
    if (has_mlp && n_patterns <= MAX_PATTERNS_INLINE) {
        const std::size_t h = static_cast<std::size_t>(mlp_hidden_);
        float mlp_out = mlp_b2_;
        for (std::size_t hi = 0; hi < h; ++hi) {
            float acc_h = mlp_b1_[hi];
            for (std::size_t pi = 0; pi < n_patterns; ++pi) {
                acc_h += static_cast<float>(pattern_values[pi])
                       * mlp_w1_[pi * h + hi];
            }
            if (acc_h > 0.0f) {
                mlp_out += acc_h * mlp_w2_[hi];
            }
        }
        acc_mg += static_cast<std::int32_t>(mlp_out);
    }

    std::int32_t acc;
    if (has_phase_split) {
        const int stage = compute_stage(pos);
        acc = (acc_mg * (STAGE_SIZE - stage) + acc_eg * stage) / STAGE_SIZE;
    } else {
        acc = acc_mg;
    }
    return (pos.side_to_move() == Color::White) ? acc : -acc;
}

bool PatternNetwork::load(std::string_view path) {
    std::ifstream f(std::string{path}, std::ios::binary);
    if (!f) return false;

    char magic[4]{};
    f.read(magic, 4);
    if (!f || std::memcmp(magic, JPAT_MAGIC, 4) != 0) return false;

    auto read_u32 = [&](std::uint32_t& v) {
        f.read(reinterpret_cast<char*>(&v), 4);
        return static_cast<bool>(f);
    };
    auto read_i32 = [&](std::int32_t& v) {
        f.read(reinterpret_cast<char*>(&v), 4);
        return static_cast<bool>(f);
    };

    std::uint32_t version{}, num_patterns{};
    std::int32_t  bias{};
    if (!read_u32(version))                            return false;
    if (version != JPAT_VERSION_V1
     && version != JPAT_VERSION_V2
     && version != JPAT_VERSION_V3
     && version != JPAT_VERSION_V4
     && version != JPAT_VERSION_V5
     && version != JPAT_VERSION_V6
     && version != JPAT_VERSION_V7
     && version != JPAT_VERSION_V8) {
        return false;
    }
    if (!read_u32(num_patterns))                       return false;
    if (!read_i32(bias))                               return false;

    std::int32_t man_value  = 0;
    std::int32_t king_value = 0;
    std::uint8_t base       = 5;  // v1/v2 imply base=5
    std::int32_t balance    = 0;
    std::array<std::int32_t, 50> king_pst{};
    std::int32_t bias_eg       = 0;
    std::int32_t man_value_eg  = 0;
    std::int32_t king_value_eg = 0;
    std::int32_t balance_eg    = 0;
    std::array<std::int32_t, 50> king_pst_eg{};
    std::int32_t mobility_mg   = 0;
    std::int32_t mobility_eg   = 0;
    if (version >= JPAT_VERSION_V2) {
        if (!read_i32(man_value))  return false;
        if (!read_i32(king_value)) return false;
    }
    if (version >= JPAT_VERSION_V3) {
        f.read(reinterpret_cast<char*>(&base), 1);
        if (!f || (base != 3 && base != 5)) return false;
    }
    if (version >= JPAT_VERSION_V4) {
        if (!read_i32(balance)) return false;
        f.read(reinterpret_cast<char*>(king_pst.data()),
               static_cast<std::streamsize>(50 * sizeof(std::int32_t)));
        if (!f) return false;
    }
    if (version >= JPAT_VERSION_V5) {
        if (!read_i32(bias_eg))       return false;
        if (!read_i32(man_value_eg))  return false;
        if (!read_i32(king_value_eg)) return false;
        if (!read_i32(balance_eg))    return false;
        f.read(reinterpret_cast<char*>(king_pst_eg.data()),
               static_cast<std::streamsize>(50 * sizeof(std::int32_t)));
        if (!f) return false;
    }
    if (version >= JPAT_VERSION_V6) {
        if (!read_i32(mobility_mg)) return false;
        if (!read_i32(mobility_eg)) return false;
    }
    // JPAT v7 — hybrid MLP head (MG-only residual). Float32 weights.
    std::uint8_t mlp_hidden = 0;
    std::vector<float> mlp_w1, mlp_b1, mlp_w2;
    float mlp_b2 = 0.0f;
    if (version >= JPAT_VERSION_V7) {
        f.read(reinterpret_cast<char*>(&mlp_hidden), 1);
        if (!f) return false;
        if (mlp_hidden > 0) {
            const std::size_t h = static_cast<std::size_t>(mlp_hidden);
            const std::size_t n = static_cast<std::size_t>(num_patterns);
            mlp_w1.resize(n * h);
            mlp_b1.resize(h);
            mlp_w2.resize(h);
            f.read(reinterpret_cast<char*>(mlp_w1.data()),
                   static_cast<std::streamsize>(n * h * sizeof(float)));
            f.read(reinterpret_cast<char*>(mlp_b1.data()),
                   static_cast<std::streamsize>(h * sizeof(float)));
            f.read(reinterpret_cast<char*>(mlp_w2.data()),
                   static_cast<std::streamsize>(h * sizeof(float)));
            f.read(reinterpret_cast<char*>(&mlp_b2), sizeof(float));
            if (!f) return false;
        }
    }
    // JPAT v8 — paradigm shift A : pattern embeddings + MLP end-to-end.
    // Read v8 MLP weights here ; per-pattern embedding tables are read
    // inside the patterns loop below (replacing the int32 weights blob).
    std::uint8_t embed_dim     = 0;
    std::uint8_t v8_mlp_hidden = 0;
    std::uint8_t v8_stm_flip   = 1;  // legacy default if absent
    std::vector<float> v8_mlp_w1, v8_mlp_b1, v8_mlp_w2;
    float v8_mlp_b2 = 0.0f;
    if (version == JPAT_VERSION_V8) {
        f.read(reinterpret_cast<char*>(&embed_dim), 1);
        if (!f || embed_dim == 0 || embed_dim > 32) return false;
        f.read(reinterpret_cast<char*>(&v8_mlp_hidden), 1);
        if (!f || v8_mlp_hidden == 0) return false;
        f.read(reinterpret_cast<char*>(&v8_stm_flip), 1);
        if (!f || v8_stm_flip > 1) return false;
        const std::size_t ed = static_cast<std::size_t>(embed_dim);
        const std::size_t h  = static_cast<std::size_t>(v8_mlp_hidden);
        const std::size_t n  = static_cast<std::size_t>(num_patterns);
        v8_mlp_w1.resize(n * ed * h);
        v8_mlp_b1.resize(h);
        v8_mlp_w2.resize(h);
        f.read(reinterpret_cast<char*>(v8_mlp_w1.data()),
               static_cast<std::streamsize>(n * ed * h * sizeof(float)));
        f.read(reinterpret_cast<char*>(v8_mlp_b1.data()),
               static_cast<std::streamsize>(h * sizeof(float)));
        f.read(reinterpret_cast<char*>(v8_mlp_w2.data()),
               static_cast<std::streamsize>(h * sizeof(float)));
        f.read(reinterpret_cast<char*>(&v8_mlp_b2), sizeof(float));
        if (!f) return false;
    }

    // For v1-v4 the EG counterparts stay at their default (zeros). The
    // evaluate() path detects "no EG populated" and skips the phase
    // interpolation entirely, returning acc_mg as in v1-v4 (legacy
    // semantics preserved without rewriting state on load). v1-v5 leave
    // mobility_mg/eg at 0 → no mobility contribution, identical eval.
    // v1-v6 leave mlp_hidden = 0 → no MLP, identical eval.

    std::vector<Pattern>             tmp;
    std::vector<std::vector<float>>  tmp_embeddings;
    tmp.reserve(num_patterns);
    if (version == JPAT_VERSION_V8) tmp_embeddings.reserve(num_patterns);
    for (std::uint32_t i = 0; i < num_patterns; ++i) {
        std::uint8_t k = 0;
        f.read(reinterpret_cast<char*>(&k), 1);
        if (!f || k == 0 || k > 16) return false;
        std::vector<std::uint8_t> sqs(k);
        f.read(reinterpret_cast<char*>(sqs.data()), k);
        if (!f) return false;
        const std::size_t nbuckets = pow_n(base, k);
        std::vector<std::int32_t> w;
        if (version == JPAT_VERSION_V8) {
            // v8 : per-pattern embedding table (no int32 weights blob).
            std::vector<float> emb(nbuckets * embed_dim);
            f.read(reinterpret_cast<char*>(emb.data()),
                   static_cast<std::streamsize>(emb.size() * sizeof(float)));
            if (!f) return false;
            tmp_embeddings.push_back(std::move(emb));
        } else {
            w.resize(nbuckets);
            f.read(reinterpret_cast<char*>(w.data()),
                   static_cast<std::streamsize>(nbuckets * sizeof(std::int32_t)));
            if (!f) return false;
        }
        tmp.push_back({std::move(sqs), std::move(w)});
    }

    patterns_       = std::move(tmp);
    bias_           = bias;
    man_value_      = man_value;
    king_value_     = king_value;
    encoding_base_  = base;
    balance_        = balance;
    king_pst_       = king_pst;
    bias_eg_        = bias_eg;
    man_value_eg_   = man_value_eg;
    king_value_eg_  = king_value_eg;
    balance_eg_     = balance_eg;
    king_pst_eg_    = king_pst_eg;
    mobility_mg_    = mobility_mg;
    mobility_eg_    = mobility_eg;
    mlp_hidden_     = mlp_hidden;
    mlp_w1_         = std::move(mlp_w1);
    mlp_b1_         = std::move(mlp_b1);
    mlp_w2_         = std::move(mlp_w2);
    mlp_b2_         = mlp_b2;
    embed_dim_      = embed_dim;
    v8_mlp_hidden_  = v8_mlp_hidden;
    v8_stm_flip_    = v8_stm_flip;
    embeddings_     = std::move(tmp_embeddings);
    v8_mlp_w1_      = std::move(v8_mlp_w1);
    v8_mlp_b1_      = std::move(v8_mlp_b1);
    v8_mlp_w2_      = std::move(v8_mlp_w2);
    v8_mlp_b2_      = v8_mlp_b2;
    return true;
}

bool PatternNetwork::save(std::string_view path, std::uint32_t version) const {
    if (version != JPAT_VERSION_V1
     && version != JPAT_VERSION_V2
     && version != JPAT_VERSION_V3
     && version != JPAT_VERSION_V4
     && version != JPAT_VERSION_V5
     && version != JPAT_VERSION_V6
     && version != JPAT_VERSION_V7
     && version != JPAT_VERSION_V8) {
        return false;
    }
    // v8 holds pattern embeddings + dedicated MLP. Refuse v<8 if
    // embed_dim_ > 0 (silent loss of embeddings would corrupt the file).
    // Conversely, v8 requires embed_dim_ > 0 to be meaningful.
    if (embed_dim_ != 0 && version != JPAT_VERSION_V8) return false;
    if (version == JPAT_VERSION_V8 && embed_dim_ == 0) return false;
    // base=3 networks can only be saved as v3+; refusing v1/v2 prevents
    // silent loss of the encoding info.
    if (encoding_base_ != 5
     && version != JPAT_VERSION_V3
     && version != JPAT_VERSION_V4
     && version != JPAT_VERSION_V5
     && version != JPAT_VERSION_V6
     && version != JPAT_VERSION_V7
     && version != JPAT_VERSION_V8) {
        return false;
    }
    // v4 holds king_pst/balance; saving as v1/v2/v3 with non-zero values
    // would silently drop them. v5+v6+v7 also OK since they're supersets.
    const bool has_v4_payload =
        balance_ != 0 ||
        std::any_of(king_pst_.begin(), king_pst_.end(),
                    [](std::int32_t w) { return w != 0; });
    if (has_v4_payload
     && version != JPAT_VERSION_V4
     && version != JPAT_VERSION_V5
     && version != JPAT_VERSION_V6
     && version != JPAT_VERSION_V7
     && version != JPAT_VERSION_V8) {
        return false;
    }
    // v5 holds the EG counterparts; saving as v<5 drops them by design
    // (the loader rehydrates EG = MG to preserve mono-phase eval). We
    // only refuse v<5 when at least one EG counterpart has been set to
    // a *non-zero* value AND differs from its MG sibling — i.e. the
    // user explicitly populated a phase split that v<5 can't represent.
    // Default-zero EG fields against a non-zero MG are treated as
    // "EG not yet populated", which is the common case before the
    // trainer runs.
    auto eg_dirty = [&](std::int32_t mg, std::int32_t eg) {
        return eg != 0 && eg != mg;
    };
    bool has_v5_payload =
        eg_dirty(bias_,       bias_eg_)       ||
        eg_dirty(man_value_,  man_value_eg_)  ||
        eg_dirty(king_value_, king_value_eg_) ||
        eg_dirty(balance_,    balance_eg_);
    for (std::size_t i = 0; !has_v5_payload && i < 50; ++i) {
        has_v5_payload = eg_dirty(king_pst_[i], king_pst_eg_[i]);
    }
    if (has_v5_payload
     && version != JPAT_VERSION_V5
     && version != JPAT_VERSION_V6
     && version != JPAT_VERSION_V7
     && version != JPAT_VERSION_V8) {
        return false;
    }
    // v6 holds king mobility (mg/eg). Refuse v<6 if non-zero.
    const bool has_v6_payload = (mobility_mg_ != 0 || mobility_eg_ != 0);
    if (has_v6_payload
     && version != JPAT_VERSION_V6
     && version != JPAT_VERSION_V7
     && version != JPAT_VERSION_V8) {
        return false;
    }
    // v7 holds MLP head. Refuse v<7 if mlp_hidden != 0.
    const bool has_v7_payload = (mlp_hidden_ != 0);
    if (has_v7_payload && version != JPAT_VERSION_V7) {
        return false;
    }
    std::ofstream f(std::string{path}, std::ios::binary);
    if (!f) return false;
    f.write(JPAT_MAGIC, 4);
    const std::uint32_t n = static_cast<std::uint32_t>(patterns_.size());
    f.write(reinterpret_cast<const char*>(&version), 4);
    f.write(reinterpret_cast<const char*>(&n),       4);
    f.write(reinterpret_cast<const char*>(&bias_),   4);
    if (version >= JPAT_VERSION_V2) {
        f.write(reinterpret_cast<const char*>(&man_value_),  4);
        f.write(reinterpret_cast<const char*>(&king_value_), 4);
    }
    if (version >= JPAT_VERSION_V3) {
        f.write(reinterpret_cast<const char*>(&encoding_base_), 1);
    }
    if (version >= JPAT_VERSION_V4) {
        f.write(reinterpret_cast<const char*>(&balance_), 4);
        f.write(reinterpret_cast<const char*>(king_pst_.data()),
                static_cast<std::streamsize>(50 * sizeof(std::int32_t)));
    }
    if (version >= JPAT_VERSION_V5) {
        f.write(reinterpret_cast<const char*>(&bias_eg_),       4);
        f.write(reinterpret_cast<const char*>(&man_value_eg_),  4);
        f.write(reinterpret_cast<const char*>(&king_value_eg_), 4);
        f.write(reinterpret_cast<const char*>(&balance_eg_),    4);
        f.write(reinterpret_cast<const char*>(king_pst_eg_.data()),
                static_cast<std::streamsize>(50 * sizeof(std::int32_t)));
    }
    if (version >= JPAT_VERSION_V6) {
        f.write(reinterpret_cast<const char*>(&mobility_mg_), 4);
        f.write(reinterpret_cast<const char*>(&mobility_eg_), 4);
    }
    if (version >= JPAT_VERSION_V7) {
        f.write(reinterpret_cast<const char*>(&mlp_hidden_), 1);
        if (mlp_hidden_ > 0) {
            const std::size_t h = static_cast<std::size_t>(mlp_hidden_);
            const std::size_t n = patterns_.size();
            f.write(reinterpret_cast<const char*>(mlp_w1_.data()),
                    static_cast<std::streamsize>(n * h * sizeof(float)));
            f.write(reinterpret_cast<const char*>(mlp_b1_.data()),
                    static_cast<std::streamsize>(h * sizeof(float)));
            f.write(reinterpret_cast<const char*>(mlp_w2_.data()),
                    static_cast<std::streamsize>(h * sizeof(float)));
            f.write(reinterpret_cast<const char*>(&mlp_b2_), sizeof(float));
        }
    }
    if (version == JPAT_VERSION_V8) {
        f.write(reinterpret_cast<const char*>(&embed_dim_),     1);
        f.write(reinterpret_cast<const char*>(&v8_mlp_hidden_), 1);
        f.write(reinterpret_cast<const char*>(&v8_stm_flip_),   1);
        const std::size_t ed   = static_cast<std::size_t>(embed_dim_);
        const std::size_t h    = static_cast<std::size_t>(v8_mlp_hidden_);
        const std::size_t npat = patterns_.size();
        f.write(reinterpret_cast<const char*>(v8_mlp_w1_.data()),
                static_cast<std::streamsize>(npat * ed * h * sizeof(float)));
        f.write(reinterpret_cast<const char*>(v8_mlp_b1_.data()),
                static_cast<std::streamsize>(h * sizeof(float)));
        f.write(reinterpret_cast<const char*>(v8_mlp_w2_.data()),
                static_cast<std::streamsize>(h * sizeof(float)));
        f.write(reinterpret_cast<const char*>(&v8_mlp_b2_), sizeof(float));
    }
    for (std::size_t pi = 0; pi < patterns_.size(); ++pi) {
        const Pattern& p = patterns_[pi];
        const std::uint8_t k = static_cast<std::uint8_t>(p.squares.size());
        f.write(reinterpret_cast<const char*>(&k), 1);
        f.write(reinterpret_cast<const char*>(p.squares.data()), k);
        if (version == JPAT_VERSION_V8) {
            const std::vector<float>& emb = embeddings_[pi];
            f.write(reinterpret_cast<const char*>(emb.data()),
                    static_cast<std::streamsize>(emb.size() * sizeof(float)));
        } else {
            f.write(reinterpret_cast<const char*>(p.weights.data()),
                    static_cast<std::streamsize>(p.weights.size() * sizeof(std::int32_t)));
        }
    }
    return f.good();
}

bool PatternNetwork::load_from_bytes(const unsigned char* data, std::size_t n) {
    if (data == nullptr || n < 4 || std::memcmp(data, JPAT_MAGIC, 4) != 0) {
        return false;
    }
    // Reuse the stream loader by writing to a temp; simpler than
    // duplicating the parser. JPAT files are tiny (~KB for v1, ~MB for
    // scaled-up sets) so the temp file write is negligible.
    const std::string tmp = std::string("/tmp/jass-jpat-") +
                            std::to_string(reinterpret_cast<std::uintptr_t>(data));
    {
        std::ofstream f(tmp, std::ios::binary);
        if (!f) return false;
        f.write(reinterpret_cast<const char*>(data),
                static_cast<std::streamsize>(n));
    }
    const bool ok = load(tmp);
    std::remove(tmp.c_str());
    return ok;
}

}  // namespace jass
