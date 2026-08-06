#pragma once

#include <array>
#include <cstdint>
#include <string_view>

namespace mini_jass {

using Bitboard = std::uint16_t;

inline constexpr std::uint8_t kBoardSize = 5;
inline constexpr std::uint8_t kPlayableSquareCount = 13;
inline constexpr std::uint8_t kMaxPiecesPerSide = 2;
inline constexpr std::uint8_t kReversiblePlyLimit = 20;
inline constexpr Bitboard kPlayableMask = (Bitboard{1} << kPlayableSquareCount) - 1;
inline constexpr Bitboard kBlackHomeMask =
    (Bitboard{1} << 0) | (Bitboard{1} << 1) | (Bitboard{1} << 2);
inline constexpr Bitboard kWhiteHomeMask =
    (Bitboard{1} << 10) | (Bitboard{1} << 11) | (Bitboard{1} << 12);

enum class Side : std::uint8_t {
    White = 0,
    Black = 1,
};

struct Coordinate {
    std::uint8_t row;
    std::uint8_t column;

    friend constexpr bool operator==(const Coordinate&, const Coordinate&) = default;
};

inline constexpr std::array<Coordinate, kPlayableSquareCount> kSquareCoordinates{{
    {0, 0}, {0, 2}, {0, 4},
    {1, 1}, {1, 3},
    {2, 0}, {2, 2}, {2, 4},
    {3, 1}, {3, 3},
    {4, 0}, {4, 2}, {4, 4},
}};

struct State {
    Bitboard white_men{};
    Bitboard black_men{};
    Bitboard white_kings{};
    Bitboard black_kings{};
    Side side_to_move{Side::White};
    std::uint8_t reversible_plies{};

    friend constexpr bool operator==(const State&, const State&) = default;
};

enum class StateError : std::uint8_t {
    None = 0,
    HighBitsSet,
    OverlappingPieces,
    TooManyWhitePieces,
    TooManyBlackPieces,
    UnpromotedWhiteMan,
    UnpromotedBlackMan,
    InvalidSideToMove,
    InvalidReversiblePlyCount,
};

[[nodiscard]] constexpr Bitboard square_bit(const std::uint8_t square) noexcept {
    return static_cast<Bitboard>(Bitboard{1} << square);
}

[[nodiscard]] constexpr Side opposite(const Side side) noexcept {
    return side == Side::White ? Side::Black : Side::White;
}

[[nodiscard]] State initial_state() noexcept;
[[nodiscard]] StateError validate_state(const State& state) noexcept;
[[nodiscard]] std::string_view to_string(StateError error) noexcept;
[[nodiscard]] Bitboard rotate180(Bitboard bits) noexcept;
[[nodiscard]] State rotate180_and_swap_colours(const State& state) noexcept;
[[nodiscard]] std::uint64_t state_key(const State& state) noexcept;

}  // namespace mini_jass
