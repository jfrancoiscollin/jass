#pragma once

#include "mini_jass/l2_move.hpp"

#include <vector>

namespace mini_jass::l2 {

[[nodiscard]] std::vector<Move> generate_board_moves(const State& state);
[[nodiscard]] std::vector<Move> generate_reference_board_moves(const State& state);

}  // namespace mini_jass::l2
