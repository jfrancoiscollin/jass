#include "mini_jass/movegen.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>

namespace mini_jass {
namespace {

struct Jump {
    std::uint8_t captured;
    std::uint8_t landing;
};

[[nodiscard]] std::optional<std::uint8_t> topology_square_at(
    const int row,
    const int column) noexcept {
    if (row < 0 || row >= kBoardSize || column < 0 || column >= kBoardSize) {
        return std::nullopt;
    }
    for (std::uint8_t square = 0; square < kPlayableSquareCount; ++square) {
        const Coordinate coordinate = kSquareCoordinates[square];
        if (coordinate.row == row && coordinate.column == column) {
            return square;
        }
    }
    return std::nullopt;
}

[[nodiscard]] std::array<std::optional<Jump>, 4> jump_topology(
    const std::uint8_t square) noexcept {
    std::array<std::optional<Jump>, 4> result{};
    const Coordinate origin = kSquareCoordinates[square];
    constexpr std::array<int, 4> row_delta{-2, -2, 2, 2};
    constexpr std::array<int, 4> column_delta{-2, 2, -2, 2};

    for (std::size_t index = 0; index < result.size(); ++index) {
        const auto landing = topology_square_at(
            static_cast<int>(origin.row) + row_delta[index],
            static_cast<int>(origin.column) + column_delta[index]);
        const auto captured = topology_square_at(
            static_cast<int>(origin.row) + row_delta[index] / 2,
            static_cast<int>(origin.column) + column_delta[index] / 2);
        if (landing.has_value() && captured.has_value()) {
            result[index] = Jump{*captured, *landing};
        }
    }
    return result;
}

void append_capture_sequences(
    const std::uint8_t origin,
    const std::uint8_t current,
    const Bitboard stationary_own,
    const Bitboard opponent,
    Move path,
    std::vector<Move>& moves) {
    bool extended = false;
    const Bitboard occupied = stationary_own | opponent | square_bit(current);

    for (const auto& optional_jump : jump_topology(current)) {
        if (!optional_jump.has_value()) {
            continue;
        }
        const Jump jump = *optional_jump;
        if ((opponent & square_bit(jump.captured)) == 0 ||
            (occupied & square_bit(jump.landing)) != 0) {
            continue;
        }
        if (path.landing_count >= path.landings.size()) {
            throw std::logic_error{"capture sequence exceeds L1 material bound"};
        }

        Move continuation = path;
        continuation.landings[continuation.landing_count] = jump.landing;
        ++continuation.landing_count;
        append_capture_sequences(
            origin,
            jump.landing,
            stationary_own,
            static_cast<Bitboard>(opponent & ~square_bit(jump.captured)),
            continuation,
            moves);
        extended = true;
    }

    if (!extended && path.landing_count != 0) {
        path.from = origin;
        moves.push_back(path);
    }
}

void append_quiet_moves(
    const State& state,
    const Side side,
    const std::uint8_t from,
    const bool king,
    std::vector<Move>& moves) {
    const Coordinate origin = kSquareCoordinates[from];
    const Bitboard occupied = state.white_men | state.black_men |
                              state.white_kings | state.black_kings;
    const int forward = side == Side::White ? -1 : 1;
    const std::array<int, 2> row_deltas{forward, -forward};

    for (std::size_t direction = 0; direction < row_deltas.size(); ++direction) {
        if (!king && direction == 1) {
            break;
        }
        for (const int column_delta : {-1, 1}) {
            const auto destination = topology_square_at(
                static_cast<int>(origin.row) + row_deltas[direction],
                static_cast<int>(origin.column) + column_delta);
            if (destination.has_value() &&
                (occupied & square_bit(*destination)) == 0) {
                moves.push_back(one_landing_move(from, *destination));
            }
        }
    }
}

}  // namespace

std::vector<Move> generate_board_moves(const State& state) {
    const StateError error = validate_state(state);
    if (error != StateError::None) {
        throw std::invalid_argument{std::string{to_string(error)}};
    }

    const Side side = state.side_to_move;
    const Bitboard own_men = side == Side::White ? state.white_men : state.black_men;
    const Bitboard own_kings = side == Side::White ? state.white_kings : state.black_kings;
    const Bitboard own = own_men | own_kings;
    const Bitboard opponent = side == Side::White
                                  ? static_cast<Bitboard>(state.black_men | state.black_kings)
                                  : static_cast<Bitboard>(state.white_men | state.white_kings);

    std::vector<Move> captures;
    for (std::uint8_t from = 0; from < kPlayableSquareCount; ++from) {
        if ((own & square_bit(from)) == 0) {
            continue;
        }
        Move path;
        path.from = from;
        append_capture_sequences(
            from,
            from,
            static_cast<Bitboard>(own & ~square_bit(from)),
            opponent,
            path,
            captures);
    }
    if (!captures.empty()) {
        std::sort(captures.begin(), captures.end(), MoveLess{});
        captures.erase(std::unique(captures.begin(), captures.end()), captures.end());
        return captures;
    }

    std::vector<Move> quiet;
    for (std::uint8_t from = 0; from < kPlayableSquareCount; ++from) {
        if ((own_men & square_bit(from)) != 0) {
            append_quiet_moves(state, side, from, false, quiet);
        } else if ((own_kings & square_bit(from)) != 0) {
            append_quiet_moves(state, side, from, true, quiet);
        }
    }
    std::sort(quiet.begin(), quiet.end(), MoveLess{});
    return quiet;
}

}  // namespace mini_jass
