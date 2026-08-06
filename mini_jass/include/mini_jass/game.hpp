#pragma once

#include "mini_jass/movegen.hpp"

#include <string_view>
#include <vector>

namespace mini_jass {

enum class TerminalStatus : std::uint8_t {
    Ongoing = 0,
    SideToMoveLoss,
    Draw,
};

[[nodiscard]] TerminalStatus terminal_status(const State& state);
[[nodiscard]] std::string_view to_string(TerminalStatus status) noexcept;
[[nodiscard]] std::vector<Move> legal_moves(const State& state);
[[nodiscard]] State apply_move(const State& state, const Move& move);

}  // namespace mini_jass
