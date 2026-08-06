#include "mini_jass/rules.hpp"

#include <cstdint>
#include <iostream>
#include <string_view>

namespace {

void print_help() {
    std::cout << "Mini-Jass foundation\n"
              << "usage: mini_jass_cli rules\n";
}

void print_rules() {
    const mini_jass::State initial = mini_jass::initial_state();
    std::cout << "{\n"
              << "  \"schema\": \"mini_jass.rules.v1\",\n"
              << "  \"board_size\": " << static_cast<unsigned>(mini_jass::kBoardSize) << ",\n"
              << "  \"playable_squares\": "
              << static_cast<unsigned>(mini_jass::kPlayableSquareCount) << ",\n"
              << "  \"max_pieces_per_side\": "
              << static_cast<unsigned>(mini_jass::kMaxPiecesPerSide) << ",\n"
              << "  \"reversible_ply_limit\": "
              << static_cast<unsigned>(mini_jass::kReversiblePlyLimit) << ",\n"
              << "  \"initial_white_men\": " << initial.white_men << ",\n"
              << "  \"initial_black_men\": " << initial.black_men << ",\n"
              << "  \"initial_side_to_move\": \"white\"\n"
              << "}\n";
}

}  // namespace

int main(const int argc, const char* const argv[]) {
    if (argc == 1) {
        print_help();
        return 0;
    }

    if (argc == 2 && std::string_view{argv[1]} == "rules") {
        print_rules();
        return 0;
    }

    std::cerr << "unknown command\n";
    print_help();
    return 2;
}
