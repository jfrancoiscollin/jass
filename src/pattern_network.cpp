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

constexpr char          JPAT_MAGIC[4]     = {'J', 'P', 'A', 'T'};
constexpr std::uint32_t JPAT_VERSION_V1   = 1;
constexpr std::uint32_t JPAT_VERSION_V2   = 2;
constexpr std::uint32_t JPAT_VERSION_V3   = 3;
constexpr std::uint32_t JPAT_VERSION_V4   = 4;

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

int PatternNetwork::evaluate(const Position& pos) const noexcept {
    // White-POV sum.
    std::int32_t acc = bias_;

    // D1 hybrid skeleton (no-op when man_value_ == king_value_ == 0,
    // i.e. pure-pattern v1 networks). Material + king count diffs are
    // the cheapest structural features and give the patterns something
    // to correct around rather than having to learn piece values from
    // raw labels (cf. docs/SCAN_ARCHITECTURE_NOTES.md §6).
    if (man_value_ != 0 || king_value_ != 0) {
        const int wm = popcount(pos.white_men());
        const int bm = popcount(pos.black_men());
        const int wk = popcount(pos.white_kings());
        const int bk = popcount(pos.black_kings());
        acc += man_value_  * (wm - bm);
        acc += king_value_ * (wk - bk);
    }

    // G3a / JPAT v4 — king PST + balance L/R. Both default to 0 so
    // v1/v2/v3 networks behave unchanged. The PST is stored in
    // white-POV; black kings get the row-mirrored entry (square 51-s
    // ↔ index 50-s) so the eval is symmetric under colour flip.
    if (balance_ != 0) {
        acc += balance_ * compute_skew(pos);
    }
    Bitboard wk = pos.white_kings();
    while (wk) {
        const std::size_t s = static_cast<std::size_t>(pop_lsb(wk));
        acc += king_pst_[s - 1];
    }
    Bitboard bk = pos.black_kings();
    while (bk) {
        const std::size_t s = static_cast<std::size_t>(pop_lsb(bk));
        acc -= king_pst_[50 - s];
    }

    const std::uint8_t base = encoding_base_;
    for (const Pattern& p : patterns_) {
        std::size_t idx = 0;
        std::size_t mult = 1;
        for (std::uint8_t sq : p.squares) {
            idx += static_cast<std::size_t>(encode_state(pos, sq, base)) * mult;
            mult *= base;
        }
        // Defensive: out-of-range index falls through to weight 0.
        if (idx < p.weights.size()) {
            acc += p.weights[idx];
        }
    }
    // STM-POV sign-flip, matching the LinearNetwork / MLPNetworkQ
    // convention. acc is in white-POV centipawns.
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
     && version != JPAT_VERSION_V4) {
        return false;
    }
    if (!read_u32(num_patterns))                       return false;
    if (!read_i32(bias))                               return false;

    std::int32_t man_value  = 0;
    std::int32_t king_value = 0;
    std::uint8_t base       = 5;  // v1/v2 imply base=5
    std::int32_t balance    = 0;
    std::array<std::int32_t, 50> king_pst{};
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

    std::vector<Pattern> tmp;
    tmp.reserve(num_patterns);
    for (std::uint32_t i = 0; i < num_patterns; ++i) {
        std::uint8_t k = 0;
        f.read(reinterpret_cast<char*>(&k), 1);
        if (!f || k == 0 || k > 16) return false;
        std::vector<std::uint8_t> sqs(k);
        f.read(reinterpret_cast<char*>(sqs.data()), k);
        if (!f) return false;
        const std::size_t nbuckets = pow_n(base, k);
        std::vector<std::int32_t> w(nbuckets);
        f.read(reinterpret_cast<char*>(w.data()),
               static_cast<std::streamsize>(nbuckets * sizeof(std::int32_t)));
        if (!f) return false;
        tmp.push_back({std::move(sqs), std::move(w)});
    }

    patterns_      = std::move(tmp);
    bias_          = bias;
    man_value_     = man_value;
    king_value_    = king_value;
    encoding_base_ = base;
    balance_       = balance;
    king_pst_      = king_pst;
    return true;
}

bool PatternNetwork::save(std::string_view path, std::uint32_t version) const {
    if (version != JPAT_VERSION_V1
     && version != JPAT_VERSION_V2
     && version != JPAT_VERSION_V3
     && version != JPAT_VERSION_V4) {
        return false;
    }
    // base=3 networks can only be saved as v3 or v4; refusing v1/v2
    // prevents silent loss of the encoding info.
    if (encoding_base_ != 5
     && version != JPAT_VERSION_V3
     && version != JPAT_VERSION_V4) {
        return false;
    }
    // v4 holds king_pst/balance; saving as v1/v2/v3 with non-zero values
    // would silently drop them. Refuse.
    const bool has_v4_payload =
        balance_ != 0 ||
        std::any_of(king_pst_.begin(), king_pst_.end(),
                    [](std::int32_t w) { return w != 0; });
    if (has_v4_payload && version != JPAT_VERSION_V4) {
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
    for (const Pattern& p : patterns_) {
        const std::uint8_t k = static_cast<std::uint8_t>(p.squares.size());
        f.write(reinterpret_cast<const char*>(&k), 1);
        f.write(reinterpret_cast<const char*>(p.squares.data()), k);
        f.write(reinterpret_cast<const char*>(p.weights.data()),
                static_cast<std::streamsize>(p.weights.size() * sizeof(std::int32_t)));
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
