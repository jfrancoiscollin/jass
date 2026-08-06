#include "mini_jass/enumerate.hpp"
#include "mini_jass/move.hpp"
#include "mini_jass/rules.hpp"
#include "mini_jass/solver.hpp"

#include <cstdint>
#include <iostream>
#include <string_view>

namespace {

void print_help() {
    std::cout << "Mini-Jass learning laboratory\n"
              << "usage: mini_jass_cli <rules|actions|enumerate|solve>\n";
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

void print_actions() {
    std::cout << "{\n"
              << "  \"schema\": \"mini_jass.actions.v1\",\n"
              << "  \"action_count\": " << mini_jass::action_vocabulary().size() << ",\n"
              << "  \"action_hash\": " << mini_jass::action_vocabulary_hash() << "\n"
              << "}\n";
}

void print_enumeration() {
    const mini_jass::EnumerationSummary summary = mini_jass::enumerate_reachable_states();
    std::cout << "{\n"
              << "  \"schema\": \"mini_jass.graph.v1\",\n"
              << "  \"states\": " << summary.state_count << ",\n"
              << "  \"transitions\": " << summary.transition_count << ",\n"
              << "  \"loss_terminals\": " << summary.loss_terminal_count << ",\n"
              << "  \"draw_terminals\": " << summary.draw_terminal_count << ",\n"
              << "  \"graph_hash\": " << summary.graph_hash << "\n"
              << "}\n";
}

void print_solver_manifest() {
    const mini_jass::ExactOracle oracle = mini_jass::solve_exact_oracle();
    std::cout << mini_jass::solver_manifest_json(oracle.manifest);
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
    if (argc == 2 && std::string_view{argv[1]} == "actions") {
        print_actions();
        return 0;
    }
    if (argc == 2 && std::string_view{argv[1]} == "enumerate") {
        print_enumeration();
        return 0;
    }
    if (argc == 2 && std::string_view{argv[1]} == "solve") {
        print_solver_manifest();
        return 0;
    }

    std::cerr << "unknown command\n";
    print_help();
    return 2;
}
