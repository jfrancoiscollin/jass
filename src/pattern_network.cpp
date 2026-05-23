// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern_network.hpp"

#include <cstring>
#include <fstream>
#include <string>

namespace jass {

namespace {

// 5-state encoding per square (matches the JPAT format spec):
//   0 = empty
//   1 = white man
//   2 = white king
//   3 = black man
//   4 = black king
inline std::uint8_t encode_state(const Position& pos, std::uint8_t fmjd_sq) noexcept {
    const Square s = static_cast<Square>(fmjd_sq);
    const Piece  p = pos.piece_at(s);
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

constexpr char     JPAT_MAGIC[4]  = {'J', 'P', 'A', 'T'};
constexpr std::uint32_t JPAT_VERSION = 1;

inline std::size_t pow5(std::size_t k) noexcept {
    std::size_t r = 1;
    for (std::size_t i = 0; i < k; ++i) r *= 5;
    return r;
}

}  // namespace

PatternNetwork::PatternNetwork() = default;

PatternNetwork PatternNetwork::default_v1() {
    PatternNetwork net;
    for (const auto& p : V1_PATTERNS) {
        net.add_pattern(std::vector<std::uint8_t>(p.begin(), p.end()));
    }
    return net;
}

void PatternNetwork::add_pattern(const std::vector<std::uint8_t>& squares) {
    Pattern p;
    p.squares = squares;
    p.weights.assign(pow5(squares.size()), 0);
    patterns_.push_back(std::move(p));
}

int PatternNetwork::evaluate(const Position& pos) const noexcept {
    // White-POV sum: each pattern contributes its bucket weight.
    std::int32_t acc = bias_;
    for (const Pattern& p : patterns_) {
        std::size_t idx = 0;
        std::size_t mult = 1;
        for (std::uint8_t sq : p.squares) {
            idx += static_cast<std::size_t>(encode_state(pos, sq)) * mult;
            mult *= 5;
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
    if (!read_u32(version) || version != JPAT_VERSION) return false;
    if (!read_u32(num_patterns))                       return false;
    if (!read_i32(bias))                               return false;

    std::vector<Pattern> tmp;
    tmp.reserve(num_patterns);
    for (std::uint32_t i = 0; i < num_patterns; ++i) {
        std::uint8_t k = 0;
        f.read(reinterpret_cast<char*>(&k), 1);
        if (!f || k == 0 || k > 16) return false;
        std::vector<std::uint8_t> sqs(k);
        f.read(reinterpret_cast<char*>(sqs.data()), k);
        if (!f) return false;
        const std::size_t nbuckets = pow5(k);
        std::vector<std::int32_t> w(nbuckets);
        f.read(reinterpret_cast<char*>(w.data()),
               static_cast<std::streamsize>(nbuckets * sizeof(std::int32_t)));
        if (!f) return false;
        tmp.push_back({std::move(sqs), std::move(w)});
    }

    patterns_ = std::move(tmp);
    bias_     = bias;
    return true;
}

bool PatternNetwork::save(std::string_view path) const {
    std::ofstream f(std::string{path}, std::ios::binary);
    if (!f) return false;
    f.write(JPAT_MAGIC, 4);
    const std::uint32_t version = JPAT_VERSION;
    const std::uint32_t n       = static_cast<std::uint32_t>(patterns_.size());
    f.write(reinterpret_cast<const char*>(&version), 4);
    f.write(reinterpret_cast<const char*>(&n),       4);
    f.write(reinterpret_cast<const char*>(&bias_),   4);
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
