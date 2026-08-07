#include "mini_jass/enumerate.hpp"
#include "mini_jass/solver.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <optional>
#include <string>
#include <vector>

namespace {

int failures = 0;

void expect(const bool condition, const char* const message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

[[nodiscard]] bool contains(
    const std::vector<std::uint8_t>& actions,
    const std::uint8_t action) {
    return std::find(actions.begin(), actions.end(), action) != actions.end();
}

[[nodiscard]] std::uint16_t incremented(const std::uint16_t value) {
    return static_cast<std::uint16_t>(value + 1);
}

}  // namespace

int main(const int argc, const char* const argv[]) {
    using namespace mini_jass;

    const ExactOracle first = solve_exact_oracle();
    const ExactOracle second = solve_exact_oracle();
    expect(first.manifest == second.manifest,
           "two exact solves produce the same manifest and hashes");
    expect(first.manifest == kSolverManifestV1,
           "exact oracle matches the frozen v1 solver manifest");
    expect(solver_manifest_json(first.manifest) == solver_manifest_json(second.manifest),
           "solver manifest JSON is byte deterministic");
    expect(first.states.size() == first.manifest.raw_state_count,
           "oracle stores every reachable raw state");
    expect(first.manifest.raw_state_count == kReachableGraphV1.state_count &&
               first.manifest.raw_transition_count == kReachableGraphV1.transition_count &&
               first.manifest.raw_graph_hash == kReachableGraphV1.graph_hash,
           "solver consumes the frozen M1 raw graph");
    expect(first.manifest.win_count + first.manifest.draw_count +
                   first.manifest.loss_count ==
               first.manifest.raw_state_count,
           "W/L/D counts partition the raw graph");
    expect(!first.states.empty() && first.states.front().state == initial_state(),
           "raw state zero is the normative initial state");

    const auto& vocabulary = action_vocabulary();
    for (std::size_t action = 0; action < vocabulary.size(); ++action) {
        const Move rotated = rotate180_move(vocabulary[action]);
        const auto rotated_id = action_id(rotated);
        expect(rotated_id.has_value(), "rotated action remains in the vocabulary");
        expect(rotate180_move(rotated) == vocabulary[action],
               "move rotation is an involution");
    }

    std::uint64_t checked_transitions = 0;
    std::uint64_t checked_symmetry_transitions = 0;
    std::uint64_t observed_wins = 0;
    std::uint64_t observed_draws = 0;
    std::uint64_t observed_losses = 0;
    std::uint16_t observed_maximum_dtw = 0;

    for (std::size_t state_id = 0; state_id < first.states.size(); ++state_id) {
        const OracleState& node = first.states[state_id];
        expect(validate_state(node.state) == StateError::None,
               "every oracle state is structurally valid");
        expect(node.canonical_state_id < first.manifest.canonical_state_count,
               "every raw state maps to a canonical state");

        const State transformed = rotate180_and_swap_colours(node.state);
        expect(node.canonical_transform ==
                   (state_key(transformed) < state_key(node.state)),
               "canonical orientation uses the smaller stable state key");
        expect(terminal_status(transformed) == node.terminal,
               "terminal status is invariant under the canonical symmetry");

        std::vector<Move> transformed_moves = legal_moves(transformed);
        std::vector<Move> expected_transformed_moves;
        for (const Move& move : legal_moves(node.state)) {
            expected_transformed_moves.push_back(rotate180_move(move));
        }
        std::sort(expected_transformed_moves.begin(), expected_transformed_moves.end(), MoveLess{});
        expect(transformed_moves == expected_transformed_moves,
               "legal move generation is equivariant under the canonical symmetry");

        switch (node.value) {
            case ExactValue::Win:
                ++observed_wins;
                break;
            case ExactValue::Draw:
                ++observed_draws;
                break;
            case ExactValue::Loss:
                ++observed_losses;
                break;
        }
        if (node.dtw.has_value()) {
            observed_maximum_dtw = std::max(observed_maximum_dtw, *node.dtw);
        }

        if (node.terminal == TerminalStatus::SideToMoveLoss) {
            expect(node.value == ExactValue::Loss && node.dtw == 0,
                   "rule-loss terminals have exact value -1 and DTW zero");
            expect(node.transitions.empty() && node.optimal_actions.empty(),
                   "rule-loss terminals are never expanded");
            continue;
        }
        if (node.terminal == TerminalStatus::Draw) {
            expect(node.value == ExactValue::Draw && !node.dtw.has_value(),
                   "reversible-limit terminals have exact value zero and null DTW");
            expect(node.transitions.empty() && node.optimal_actions.empty(),
                   "draw terminals are never expanded");
            continue;
        }

        const std::vector<Move> moves = legal_moves(node.state);
        expect(moves.size() == node.transitions.size(),
               "every legal move has exactly one stored transition");
        expect(!node.optimal_actions.empty(),
               "every non-terminal state stores at least one optimal action");

        int best_score = -2;
        std::optional<std::uint16_t> shortest_win;
        std::optional<std::uint16_t> longest_loss;
        bool has_draw_child = false;

        for (std::size_t index = 0; index < node.transitions.size(); ++index) {
            const OracleTransition transition = node.transitions[index];
            expect(transition.child_id < first.states.size(),
                   "every transition points to a stored raw state");
            expect(transition.action < vocabulary.size(),
                   "every transition action is in the frozen vocabulary");
            expect(action_id(moves[index]) == transition.action,
                   "transition order and action IDs match legal move order");

            const State applied = apply_move(node.state, moves[index]);
            const OracleState& child = first.states[transition.child_id];
            expect(applied == child.state,
                   "copy-apply reaches the stored successor exactly");

            const State transformed_applied = apply_move(
                transformed, rotate180_move(moves[index]));
            expect(transformed_applied == rotate180_and_swap_colours(applied),
                   "move application commutes with the canonical symmetry");
            ++checked_symmetry_transitions;

            const Side moving_side = node.state.side_to_move;
            const Bitboard moving_men = moving_side == Side::White
                                            ? node.state.white_men
                                            : node.state.black_men;
            const bool moving_man =
                (moving_men & square_bit(moves[index].from)) != 0;
            const std::uint8_t expected_counter =
                (moving_man || is_capture_move(moves[index]))
                    ? 0
                    : static_cast<std::uint8_t>(node.state.reversible_plies + 1);
            expect(child.state.reversible_plies == expected_counter,
                   "every transition obeys the reversible-counter rule");

            const int score = -static_cast<int>(child.value);
            best_score = std::max(best_score, score);
            expect(static_cast<int>(node.value) >= score,
                   "parent value dominates every negated child value");
            expect(contains(node.optimal_actions, transition.action) ==
                       (static_cast<int>(node.value) == score),
                   "optimal actions are exactly the value-attaining moves");

            if (child.value == ExactValue::Loss) {
                expect(child.dtw.has_value(), "loss children have a DTW");
                const std::uint16_t candidate = incremented(*child.dtw);
                shortest_win = shortest_win.has_value()
                                   ? std::min(*shortest_win, candidate)
                                   : candidate;
            } else if (child.value == ExactValue::Win) {
                expect(child.dtw.has_value(), "win children have a DTW");
                const std::uint16_t candidate = incremented(*child.dtw);
                longest_loss = longest_loss.has_value()
                                  ? std::max(*longest_loss, candidate)
                                  : candidate;
            } else {
                has_draw_child = true;
            }
            ++checked_transitions;
        }

        expect(best_score == static_cast<int>(node.value),
               "stored value satisfies the exact negamax recurrence");
        if (node.value == ExactValue::Win) {
            expect(shortest_win.has_value() && node.dtw == shortest_win,
                   "winning DTW is the shortest forced conversion");
        } else if (node.value == ExactValue::Loss) {
            expect(longest_loss.has_value() && node.dtw == longest_loss,
                   "losing DTW is the longest available resistance");
        } else {
            expect(has_draw_child && !node.dtw.has_value(),
                   "non-terminal draws preserve a draw and have null DTW");
        }
    }

    expect(checked_transitions == first.manifest.raw_transition_count,
           "all raw transitions were checked exhaustively");
    expect(checked_symmetry_transitions == first.manifest.raw_transition_count,
           "apply-move symmetry was checked on every transition");
    expect(observed_wins == first.manifest.win_count &&
               observed_draws == first.manifest.draw_count &&
               observed_losses == first.manifest.loss_count,
           "manifest W/L/D counts match stored states");
    expect(observed_maximum_dtw == first.manifest.maximum_dtw,
           "manifest maximum DTW matches stored states");

    const std::string manifest_json = solver_manifest_json(first.manifest);
    expect(argc == 2, "the frozen solver manifest path is supplied by CTest");
    if (argc == 2) {
        std::ifstream manifest_file{argv[1], std::ios::binary};
        std::string frozen_manifest{
            std::istreambuf_iterator<char>{manifest_file},
            std::istreambuf_iterator<char>{}};
        frozen_manifest.erase(
            std::remove(frozen_manifest.begin(), frozen_manifest.end(), '\r'),
            frozen_manifest.end());
        expect(manifest_file.good() || manifest_file.eof(),
               "the frozen solver manifest is readable");
        expect(manifest_json == frozen_manifest,
               "generated solver manifest matches the frozen JSON artefact after newline normalization");
    }

    std::cout << manifest_json;
    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return 1;
    }
    return 0;
}
