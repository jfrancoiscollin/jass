#include "mini_jass/l2_solver.hpp"

#include <iostream>
#include <vector>

namespace {
int failures = 0;
void expect(const bool condition, const char* const message) {
    if (!condition) { std::cerr << "FAIL: " << message << '\n'; ++failures; }
}
}

int main() {
    using namespace mini_jass::l2;

    expect(kBoardSize == 6 && kPlayableSquareCount == 18,
           "L2 owns the exact 6x6 topology");
    expect(action_vocabulary().size() == kActionCount && kActionCount == 122,
           "L2 has its independent 122-path vocabulary");
    for (std::size_t index = 0; index < action_vocabulary().size(); ++index) {
        const auto id = action_id(action_vocabulary()[index]);
        expect(id.has_value() && *id == index, "L2 action IDs round-trip");
    }

    const State root = initial_state();
    expect(generate_board_moves(root) == std::vector<Move>{one_landing_move(10, 3)},
           "the selected 2v2 root has exactly one forced capture into 2v1");
    expect(generate_reference_board_moves(root) == generate_board_moves(root),
           "independent L2 move generators agree at the root");

    State multi_capture;
    multi_capture.black_men = square_bit(0);
    multi_capture.white_men = square_bit(3) | square_bit(10);
    multi_capture.side_to_move = Side::Black;
    const Move forced = two_landing_move(0, 7, 14);
    expect(generate_board_moves(multi_capture) == std::vector<Move>{forced},
           "L2 emits a complete mandatory two-capture path");
    expect(generate_reference_board_moves(multi_capture) == std::vector<Move>{forced},
           "the independent L2 generator agrees on multi-capture");

    State promotion;
    promotion.black_men = square_bit(12);
    promotion.white_kings = square_bit(0);
    promotion.side_to_move = Side::Black;
    const State promoted = apply_move(promotion, one_landing_move(12, 15));
    expect(promoted.black_men == 0 && promoted.black_kings == square_bit(15),
           "L2 promotion occurs after the complete move");

    const ExactOracle first = solve_exact_oracle();
    const ExactOracle second = solve_exact_oracle();
    expect(first.manifest == second.manifest, "L2 exact solver is byte-deterministic");
    expect(first.states.size() == first.manifest.raw_state_count,
           "L2 oracle size matches its manifest");
    expect(first.manifest.raw_state_count > 10000 && first.manifest.raw_state_count < 100000,
           "selected L2 exact scope stays scientifically useful and CI-sized");
    expect(first.manifest.action_vocabulary_hash == action_vocabulary_hash(),
           "L2 solver binds the independent action vocabulary");
    expect(first.manifest.win_count + first.manifest.draw_count + first.manifest.loss_count ==
               first.manifest.raw_state_count,
           "every L2 state has an exact W/D/L label");

    std::cout << solver_manifest_json(first.manifest);
    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return 1;
    }
    return 0;
}
