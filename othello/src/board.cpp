// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "board.hpp"

#include <charconv>
#include <sstream>

namespace othello {

int Board::black_count() const noexcept {
    return __builtin_popcountll(black);
}

int Board::white_count() const noexcept {
    return __builtin_popcountll(white);
}

std::string Board::to_ascii() const {
    std::string s;
    s.reserve(8 * 9 + 16);
    s += "  a b c d e f g h\n";
    for (int row = 0; row < 8; ++row) {
        s += static_cast<char>('1' + row);
        s += ' ';
        for (int col = 0; col < 8; ++col) {
            const Bitboard bit = Bitboard{1} << make_square(row, col);
            if      (black & bit) s += 'X';
            else if (white & bit) s += 'O';
            else                  s += '.';
            s += ' ';
        }
        s += '\n';
    }
    s += "stm=";
    s += (stm == Color::Black ? "Black" : "White");
    s += "  passes=";
    s += static_cast<char>('0' + passes);
    s += '\n';
    return s;
}

namespace {

void emit_squares(std::ostringstream& out, Bitboard bb) {
    bool first = true;
    while (bb) {
        const int sq = __builtin_ctzll(bb);
        if (!first) out << ',';
        out << sq;
        first = false;
        bb &= bb - 1;
    }
}

}  // namespace

std::string Board::to_string() const {
    std::ostringstream out;
    out << (stm == Color::Black ? 'B' : 'W') << ':';
    emit_squares(out, black);
    out << ':';
    emit_squares(out, white);
    if (passes > 0) {
        out << ":p" << static_cast<int>(passes);
    }
    return out.str();
}

std::optional<Board> Board::from_string(std::string_view s) {
    if (s.size() < 3) return std::nullopt;
    Board b;
    if      (s[0] == 'B') b.stm = Color::Black;
    else if (s[0] == 'W') b.stm = Color::White;
    else                  return std::nullopt;
    if (s[1] != ':') return std::nullopt;

    // Helper to parse a comma-separated list of integers from [pos, end)
    // into `target`, returning the index after the consumed section.
    auto parse_squares = [](std::string_view str, std::size_t pos,
                            Bitboard& target) -> std::size_t {
        target = 0;
        while (pos < str.size() && str[pos] != ':') {
            int v = 0;
            const char* first = str.data() + pos;
            const char* last  = str.data() + str.size();
            auto [next, ec] = std::from_chars(first, last, v);
            if (ec != std::errc{} || v < 0 || v >= BOARD_SIZE) {
                return std::string_view::npos;
            }
            target |= Bitboard{1} << v;
            pos = static_cast<std::size_t>(next - str.data());
            if (pos < str.size() && str[pos] == ',') ++pos;
        }
        return pos;
    };

    std::size_t pos = 2;
    pos = parse_squares(s, pos, b.black);
    if (pos == std::string_view::npos) return std::nullopt;
    if (pos >= s.size() || s[pos] != ':') return std::nullopt;
    ++pos;
    pos = parse_squares(s, pos, b.white);
    if (pos == std::string_view::npos) return std::nullopt;

    // Optional ":pN" suffix for pass counter.
    if (pos < s.size() && s[pos] == ':') {
        ++pos;
        if (pos < s.size() && s[pos] == 'p') {
            ++pos;
            int v = 0;
            const char* first = s.data() + pos;
            const char* last  = s.data() + s.size();
            auto [next, ec] = std::from_chars(first, last, v);
            if (ec != std::errc{} || v < 0 || v > 2) return std::nullopt;
            b.passes = static_cast<std::uint8_t>(v);
            pos = static_cast<std::size_t>(next - s.data());
        }
    }

    if (b.black & b.white) return std::nullopt;
    return b;
}

}  // namespace othello
