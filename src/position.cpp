// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "position.hpp"

#include "board.hpp"

#include <cassert>
#include <cctype>
#include <sstream>

namespace jass {

// =============================================================================
// Construction helpers
// =============================================================================
Position Position::start_position() noexcept {
    Position p;
    for (int s = 1; s <= 20; ++s) {
        set(p.black_men_, static_cast<Square>(s));
    }
    for (int s = 31; s <= 50; ++s) {
        set(p.white_men_, static_cast<Square>(s));
    }
    p.stm_ = Color::White;
    return p;
}

void Position::clear() noexcept {
    white_men_   = 0;
    white_kings_ = 0;
    black_men_   = 0;
    black_kings_ = 0;
    stm_         = Color::White;
}

Piece Position::piece_at(Square s) const noexcept {
    const Bitboard m = square_bb(s);
    if (white_men_   & m) return Piece::WhiteMan;
    if (white_kings_ & m) return Piece::WhiteKing;
    if (black_men_   & m) return Piece::BlackMan;
    if (black_kings_ & m) return Piece::BlackKing;
    return Piece::None;
}

void Position::add_piece(Square s, Piece p) noexcept {
    assert(square_is_valid(s));
    assert(piece_at(s) == Piece::None);
    switch (p) {
        case Piece::WhiteMan:  set(white_men_,   s); break;
        case Piece::WhiteKing: set(white_kings_, s); break;
        case Piece::BlackMan:  set(black_men_,   s); break;
        case Piece::BlackKing: set(black_kings_, s); break;
        case Piece::None:      assert(false);        break;
    }
}

void Position::remove_piece(Square s, Piece p) noexcept {
    assert(square_is_valid(s));
    assert(piece_at(s) == p);
    // Qualified to avoid clashing with `Position::clear()` in member scope.
    switch (p) {
        case Piece::WhiteMan:  jass::clear(white_men_,   s); break;
        case Piece::WhiteKing: jass::clear(white_kings_, s); break;
        case Piece::BlackMan:  jass::clear(black_men_,   s); break;
        case Piece::BlackKing: jass::clear(black_kings_, s); break;
        case Piece::None:      assert(false);                break;
    }
}

// =============================================================================
// FEN parsing
// =============================================================================
namespace {

// Strip leading/trailing whitespace.
std::string_view trim(std::string_view s) {
    std::size_t i = 0;
    while (i < s.size() && std::isspace(static_cast<unsigned char>(s[i]))) ++i;
    std::size_t j = s.size();
    while (j > i && std::isspace(static_cast<unsigned char>(s[j - 1]))) --j;
    return s.substr(i, j - i);
}

// Parse a base-10 unsigned integer in [1, 50]. Returns 0 on error (since
// 0 is not a legal FMJD square anyway, that doubles as the failure value).
unsigned parse_square_number(std::string_view tok) {
    if (tok.empty()) return 0;
    unsigned value = 0;
    for (char c : tok) {
        if (c < '0' || c > '9') return 0;
        value = value * 10 + static_cast<unsigned>(c - '0');
        if (value > 50) return 0;
    }
    return value;
}

// Parse one entry of a colour-list: optionally "K" + a single square or
// "first-last" range. On success calls `emit(square, is_king)` for every
// square covered by the entry. Returns false on syntax error.
template <class Emit>
bool parse_entry(std::string_view entry, Emit&& emit) {
    if (entry.empty()) return false;

    bool king = false;
    if (entry.front() == 'K' || entry.front() == 'k') {
        king = true;
        entry.remove_prefix(1);
    }

    const auto dash = entry.find('-');
    if (dash == std::string_view::npos) {
        const unsigned sq = parse_square_number(entry);
        if (sq == 0) return false;
        emit(static_cast<Square>(sq), king);
        return true;
    }

    const unsigned first = parse_square_number(entry.substr(0, dash));
    const unsigned last  = parse_square_number(entry.substr(dash + 1));
    if (first == 0 || last == 0 || first > last) return false;
    for (unsigned s = first; s <= last; ++s) {
        emit(static_cast<Square>(s), king);
    }
    return true;
}

// Parse one full colour-list ("Wxx,xx,..." or "Bxx,xx,..."), invoking
// `emit(sq, piece)` for each piece. Returns false on any syntax error.
template <class Emit>
bool parse_colour_list(std::string_view list, Emit&& emit) {
    list = trim(list);
    if (list.empty()) return false;

    const char tag = list.front();
    if (tag != 'W' && tag != 'w' && tag != 'B' && tag != 'b') return false;
    list.remove_prefix(1);

    const Piece man  = (tag == 'W' || tag == 'w') ? Piece::WhiteMan
                                                  : Piece::BlackMan;
    const Piece king = (tag == 'W' || tag == 'w') ? Piece::WhiteKing
                                                  : Piece::BlackKing;

    list = trim(list);
    if (list.empty()) return true;  // colour with no pieces — legal.

    while (!list.empty()) {
        const auto comma = list.find(',');
        const auto tok   = trim(list.substr(0, comma));
        if (!tok.empty()) {
            if (!parse_entry(tok, [&](Square s, bool is_king) {
                    emit(s, is_king ? king : man);
                })) {
                return false;
            }
        }
        if (comma == std::string_view::npos) break;
        list.remove_prefix(comma + 1);
    }
    return true;
}

}  // namespace

std::optional<Position> Position::from_fen(std::string_view fen) {
    fen = trim(fen);
    if (fen.empty()) return std::nullopt;

    const auto colon1 = fen.find(':');
    if (colon1 == std::string_view::npos) return std::nullopt;
    const auto colon2 = fen.find(':', colon1 + 1);
    if (colon2 == std::string_view::npos) return std::nullopt;

    const std::string_view stm_tok    = trim(fen.substr(0, colon1));
    const std::string_view first_tok  = fen.substr(colon1 + 1, colon2 - colon1 - 1);
    const std::string_view second_tok = fen.substr(colon2 + 1);

    Color stm;
    if (stm_tok == "W" || stm_tok == "w")      stm = Color::White;
    else if (stm_tok == "B" || stm_tok == "b") stm = Color::Black;
    else return std::nullopt;

    Position pos;
    pos.stm_ = stm;

    bool failed = false;
    auto emit = [&](Square s, Piece p) {
        if (failed) return;
        if (!square_is_valid(s) || pos.piece_at(s) != Piece::None) {
            failed = true;
            return;
        }
        pos.add_piece(s, p);
    };

    if (!parse_colour_list(first_tok,  emit)) return std::nullopt;
    if (!parse_colour_list(second_tok, emit)) return std::nullopt;
    if (failed) return std::nullopt;

    // Reject a FEN that lists the same colour twice.
    const char first_tag  = trim(first_tok).empty()  ? '?' : trim(first_tok).front();
    const char second_tag = trim(second_tok).empty() ? '?' : trim(second_tok).front();
    auto normalise = [](char c) {
        return static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    };
    if (normalise(first_tag) == normalise(second_tag)) return std::nullopt;

    return pos;
}

// =============================================================================
// FEN serialisation
// =============================================================================
namespace {

// Emit "tag" + comma-separated list of squares for a (men, kings) pair.
void emit_colour_list(std::ostringstream& out,
                      char tag,
                      Bitboard men,
                      Bitboard kings) {
    out << tag;

    bool first = true;
    auto emit_one = [&](Square s, bool is_king) {
        if (!first) out << ',';
        first = false;
        if (is_king) out << 'K';
        out << static_cast<int>(s);
    };

    Bitboard m = men;
    while (m) emit_one(pop_lsb(m), /*is_king=*/false);
    Bitboard k = kings;
    while (k) emit_one(pop_lsb(k), /*is_king=*/true);
}

}  // namespace

std::string Position::to_fen() const {
    std::ostringstream out;
    out << (stm_ == Color::White ? 'W' : 'B') << ':';
    emit_colour_list(out, 'W', white_men_, white_kings_);
    out << ':';
    emit_colour_list(out, 'B', black_men_, black_kings_);
    return out.str();
}

// =============================================================================
// ASCII diagram
// =============================================================================
std::string Position::to_ascii() const {
    std::ostringstream out;
    out << "    a b c d e f g h i j\n";
    for (int r = 0; r < BOARD_SIDE; ++r) {
        out << ' ' << (10 - r) << ' ';
        if ((10 - r) < 10) out << ' ';
        for (int c = 0; c < BOARD_SIDE; ++c) {
            const bool dark = ((r + c) % 2 == 1);
            if (!dark) {
                out << " .";
                continue;
            }
            const int col_in_row = (r % 2 == 0) ? (c - 1) / 2 : c / 2;
            const Square s = static_cast<Square>(r * 5 + col_in_row + 1);
            const Piece  p = piece_at(s);
            char ch = '_';
            switch (p) {
                case Piece::None:      ch = '.'; break;
                case Piece::WhiteMan:  ch = 'w'; break;
                case Piece::WhiteKing: ch = 'W'; break;
                case Piece::BlackMan:  ch = 'b'; break;
                case Piece::BlackKing: ch = 'B'; break;
            }
            out << ' ' << ch;
        }
        out << '\n';
    }
    out << "Side to move: " << (stm_ == Color::White ? "White" : "Black") << '\n';
    return out.str();
}

}  // namespace jass
