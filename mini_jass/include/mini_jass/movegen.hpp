#pragma once

#include "mini_jass/move.hpp"

#include <vector>

namespace mini_jass {

// Generates mandatory-capture board moves. The reversible-ply terminal rule is
// handled by game.hpp so terminal precedence can inspect board mobility first.
[[nodiscard]] std::vector<Move> generate_board_moves(const State& state);

// Independent, coordinate-based implementation used only as a correctness
// oracle for the production generator.
[[nodiscard]] std::vector<Move> generate_reference_board_moves(const State& state);

}  // namespace mini_jass
