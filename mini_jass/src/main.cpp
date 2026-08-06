#include "mini_jass/enumerate.hpp"
#include "mini_jass/move.hpp"
#include "mini_jass/rules.hpp"
#include "mini_jass/solver.hpp"

#include <cstdint>
#include <iostream>
#include <string_view>
#include <vector>

namespace {

void print_help() {
    std::cout << "Mini-Jass learning laboratory\n"
              << "usage: mini_jass_cli <rules|actions|enumerate|solve|export-oracle>\n";
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

void print_action_list(const std::vector<std::uint8_t>& actions) {
    std::cout << '[';
    for (std::size_t index = 0; index < actions.size(); ++index) {
        if (index != 0) {
            std::cout << ',';
        }
        std::cout << static_cast<unsigned>(actions[index]);
    }
    std::cout << ']';
}

void print_oracle_jsonl() {
    const mini_jass::ExactOracle oracle = mini_jass::solve_exact_oracle();
    std::vector<std::uint32_t> canonical_parent_counts(
        oracle.manifest.canonical_state_count, 0);
    for (const mini_jass::OracleState& node : oracle.states) {
        ++canonical_parent_counts[node.canonical_state_id];
    }

    std::cout << "{\"type\":\"manifest\","
              << "\"schema\":\"mini_jass.oracle_dataset.v1\","
              << "\"solver_hash\":" << oracle.manifest.solver_hash << ','
              << "\"manifest_hash\":" << oracle.manifest.manifest_hash << ','
              << "\"state_count\":" << oracle.states.size() << ','
              << "\"canonical_state_count\":"
              << oracle.manifest.canonical_state_count << "}\n";

    for (std::size_t state_id = 0; state_id < oracle.states.size(); ++state_id) {
        const mini_jass::OracleState& node = oracle.states[state_id];
        std::vector<std::uint8_t> legal_actions;
        legal_actions.reserve(node.transitions.size());
        for (const mini_jass::OracleTransition& transition : node.transitions) {
            legal_actions.push_back(transition.action);
        }

        std::cout << "{\"type\":\"state\","
                  << "\"raw_state_id\":" << state_id << ','
                  << "\"state_key\":" << mini_jass::state_key(node.state) << ','
                  << "\"white_men\":" << node.state.white_men << ','
                  << "\"black_men\":" << node.state.black_men << ','
                  << "\"white_kings\":" << node.state.white_kings << ','
                  << "\"black_kings\":" << node.state.black_kings << ','
                  << "\"side_to_move\":"
                  << static_cast<unsigned>(node.state.side_to_move) << ','
                  << "\"reversible_plies\":"
                  << static_cast<unsigned>(node.state.reversible_plies) << ','
                  << "\"canonical_state_id\":" << node.canonical_state_id << ','
                  << "\"canonical_transform\":"
                  << (node.canonical_transform ? "true" : "false") << ','
                  << "\"canonical_parent_count\":"
                  << canonical_parent_counts[node.canonical_state_id] << ','
                  << "\"value\":" << static_cast<int>(node.value) << ','
                  << "\"dtw\":";
        if (node.dtw.has_value()) {
            std::cout << *node.dtw;
        } else {
            std::cout << "null";
        }
        std::cout << ",\"legal_actions\":";
        print_action_list(legal_actions);
        std::cout << ",\"child_ids\":[";
        for (std::size_t index = 0; index < node.transitions.size(); ++index) {
            if (index != 0) {
                std::cout << ',';
            }
            std::cout << node.transitions[index].child_id;
        }
        std::cout << "],\"optimal_actions\":";
        print_action_list(node.optimal_actions);
        std::cout << "}\n";
    }
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
    if (argc == 2 && std::string_view{argv[1]} == "export-oracle") {
        print_oracle_jsonl();
        return 0;
    }

    std::cerr << "unknown command\n";
    print_help();
    return 2;
}
