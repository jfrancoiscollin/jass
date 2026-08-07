#pragma once

#include "mini_jass/l2_rules.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace mini_jass::l2 {

inline constexpr std::uint8_t kNoSquare = kPlayableSquareCount;
inline constexpr std::size_t kActionCount = 122;

struct Move {
    std::uint8_t from{kNoSquare};
    std::array<std::uint8_t, 2> landings{kNoSquare, kNoSquare};
    std::uint8_t landing_count{};
    friend constexpr bool operator==(const Move&, const Move&) = default;
};

struct MoveLess {
    [[nodiscard]] bool operator()(const Move& lhs, const Move& rhs) const noexcept;
};

[[nodiscard]] Move one_landing_move(std::uint8_t from, std::uint8_t to) noexcept;
[[nodiscard]] Move two_landing_move(
    std::uint8_t from, std::uint8_t first, std::uint8_t second) noexcept;
[[nodiscard]] bool is_quiet_step(std::uint8_t from, std::uint8_t to) noexcept;
[[nodiscard]] bool is_jump_step(std::uint8_t from, std::uint8_t to) noexcept;
[[nodiscard]] std::optional<std::uint8_t> jumped_square(
    std::uint8_t from, std::uint8_t to) noexcept;
[[nodiscard]] bool is_capture_move(const Move& move) noexcept;
[[nodiscard]] Move rotate180_move(const Move& move) noexcept;
[[nodiscard]] const std::array<Move, kActionCount>& action_vocabulary();
[[nodiscard]] std::optional<std::uint8_t> action_id(const Move& move);
[[nodiscard]] std::uint64_t action_vocabulary_hash();

}  // namespace mini_jass::l2
