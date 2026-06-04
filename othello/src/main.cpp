// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Minimal CLI for manual exploration of the Othello POC.
//
//   othello_cli                    : print start position + legal moves
//   othello_cli perft <depth>      : run perft from start position
//   othello_cli play <m1,m2,...>   : apply a sequence of moves (squares
//                                    0..63 or 'p' for pass) and print
//                                    the resulting position

#include "board.hpp"
#include "movegen.hpp"

#include <charconv>
#include <cstdint>
#include <iostream>
#include <string>
#include <string_view>

namespace {

std::uint64_t perft(othello::Board b, int depth) {
    if (depth == 0) return 1;
    othello::MoveList ml;
    othello::generate_legal_moves(b, ml);

    if (ml.empty()) {
        // No legal move : pass. Game ends if both players just passed.
        if (b.passes >= 1) return 1;  // already a pass before → terminal
        othello::Board after = b;
        othello::apply_move(after, othello::NO_SQUARE);
        return perft(after, depth - 1);
    }

    std::uint64_t total = 0;
    for (std::size_t i = 0; i < ml.size(); ++i) {
        othello::Board after = b;
        othello::apply_move(after, ml[i]);
        total += perft(after, depth - 1);
    }
    return total;
}

void print_legal_moves(const othello::Board& b) {
    othello::MoveList ml;
    othello::generate_legal_moves(b, ml);
    std::cout << "legal moves (" << ml.size() << "): ";
    for (std::size_t i = 0; i < ml.size(); ++i) {
        if (i) std::cout << ' ';
        const int sq = ml[i];
        std::cout << sq;
    }
    if (ml.empty()) std::cout << "(must pass)";
    std::cout << '\n';
}

int parse_int(std::string_view s) {
    int v = 0;
    std::from_chars(s.data(), s.data() + s.size(), v);
    return v;
}

}  // namespace

int main(int argc, char** argv) {
    using namespace othello;
    Board b = Board::start_position();

    if (argc == 1) {
        std::cout << b.to_ascii();
        print_legal_moves(b);
        std::cout << "to_string: " << b.to_string() << '\n';
        return 0;
    }

    std::string_view cmd{argv[1]};

    if (cmd == "perft" && argc >= 3) {
        const int depth = parse_int(argv[2]);
        std::cout << "perft(" << depth << ") = " << perft(b, depth) << '\n';
        return 0;
    }

    if (cmd == "play" && argc >= 3) {
        std::string_view seq{argv[2]};
        std::size_t pos = 0;
        while (pos < seq.size()) {
            std::size_t next = seq.find(',', pos);
            std::string_view tok = seq.substr(pos, next - pos);
            Square sq = NO_SQUARE;
            if (tok != "p" && tok != "P") {
                sq = static_cast<Square>(parse_int(tok));
            }
            if (!apply_move(b, sq)) {
                std::cerr << "illegal move: " << tok << '\n';
                return 1;
            }
            pos = (next == std::string_view::npos) ? seq.size() : next + 1;
        }
        std::cout << b.to_ascii();
        std::cout << "to_string: " << b.to_string() << '\n';
        print_legal_moves(b);
        return 0;
    }

    std::cerr << "usage: othello_cli [perft <d> | play <m1,m2,...>]\n";
    return 1;
}
