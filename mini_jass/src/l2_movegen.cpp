#include "mini_jass/l2_movegen.hpp"

#include <algorithm>
#include <array>
#include <optional>
#include <stdexcept>
#include <string>

namespace mini_jass::l2 {
namespace {

struct Jump { std::uint8_t captured; std::uint8_t landing; };

[[nodiscard]] std::optional<std::uint8_t> square_at(const int row, const int column) noexcept {
    if (row < 0 || row >= kBoardSize || column < 0 || column >= kBoardSize)
        return std::nullopt;
    for (std::uint8_t square = 0; square < kPlayableSquareCount; ++square) {
        if (kSquareCoordinates[square] == Coordinate{static_cast<std::uint8_t>(row),
                                                     static_cast<std::uint8_t>(column)})
            return square;
    }
    return std::nullopt;
}

[[nodiscard]] std::array<std::optional<Jump>, 4> jump_topology(
    const std::uint8_t square) noexcept {
    std::array<std::optional<Jump>, 4> result{};
    const Coordinate origin = kSquareCoordinates[square];
    constexpr std::array<int, 4> dr{-2, -2, 2, 2};
    constexpr std::array<int, 4> dc{-2, 2, -2, 2};
    for (std::size_t i = 0; i < result.size(); ++i) {
        const auto landing = square_at(origin.row + dr[i], origin.column + dc[i]);
        const auto captured = square_at(origin.row + dr[i] / 2, origin.column + dc[i] / 2);
        if (landing.has_value() && captured.has_value())
            result[i] = Jump{*captured, *landing};
    }
    return result;
}

void append_captures(const std::uint8_t origin, const std::uint8_t current,
                     const Bitboard stationary_own, const Bitboard opponent,
                     Move path, std::vector<Move>& moves) {
    bool extended = false;
    const Bitboard occupied = stationary_own | opponent | square_bit(current);
    for (const auto& optional_jump : jump_topology(current)) {
        if (!optional_jump.has_value()) continue;
        const Jump jump = *optional_jump;
        if ((opponent & square_bit(jump.captured)) == 0 ||
            (occupied & square_bit(jump.landing)) != 0) continue;
        if (path.landing_count >= path.landings.size())
            throw std::logic_error{"L2 capture exceeds the selected two-piece opponent bound"};
        Move continuation = path;
        continuation.landings[continuation.landing_count++] = jump.landing;
        append_captures(origin, jump.landing, stationary_own,
                        opponent & ~square_bit(jump.captured), continuation, moves);
        extended = true;
    }
    if (!extended && path.landing_count != 0) {
        path.from = origin;
        moves.push_back(path);
    }
}

void append_quiet(const State& state, const Side side, const std::uint8_t from,
                  const bool king, std::vector<Move>& moves) {
    const Coordinate origin = kSquareCoordinates[from];
    const Bitboard occupied = state.white_men | state.black_men |
                              state.white_kings | state.black_kings;
    const int forward = side == Side::White ? -1 : 1;
    const std::array<int, 2> row_deltas{forward, -forward};
    for (std::size_t direction = 0; direction < row_deltas.size(); ++direction) {
        if (!king && direction == 1) break;
        for (const int column_delta : {-1, 1}) {
            const auto destination = square_at(origin.row + row_deltas[direction],
                                               origin.column + column_delta);
            if (destination.has_value() && (occupied & square_bit(*destination)) == 0)
                moves.push_back(one_landing_move(from, *destination));
        }
    }
}

}  // namespace

std::vector<Move> generate_board_moves(const State& state) {
    const StateError error = validate_state(state);
    if (error != StateError::None) throw std::invalid_argument{std::string{to_string(error)}};
    const Side side = state.side_to_move;
    const Bitboard own_men = side == Side::White ? state.white_men : state.black_men;
    const Bitboard own_kings = side == Side::White ? state.white_kings : state.black_kings;
    const Bitboard own = own_men | own_kings;
    const Bitboard opponent = side == Side::White
        ? state.black_men | state.black_kings
        : state.white_men | state.white_kings;

    std::vector<Move> captures;
    for (std::uint8_t from = 0; from < kPlayableSquareCount; ++from) {
        if ((own & square_bit(from)) == 0) continue;
        Move path;
        path.from = from;
        append_captures(from, from, own & ~square_bit(from), opponent, path, captures);
    }
    if (!captures.empty()) {
        std::sort(captures.begin(), captures.end(), MoveLess{});
        captures.erase(std::unique(captures.begin(), captures.end()), captures.end());
        return captures;
    }

    std::vector<Move> quiet;
    for (std::uint8_t from = 0; from < kPlayableSquareCount; ++from) {
        if ((own_men & square_bit(from)) != 0) append_quiet(state, side, from, false, quiet);
        else if ((own_kings & square_bit(from)) != 0) append_quiet(state, side, from, true, quiet);
    }
    std::sort(quiet.begin(), quiet.end(), MoveLess{});
    return quiet;
}

}  // namespace mini_jass::l2
