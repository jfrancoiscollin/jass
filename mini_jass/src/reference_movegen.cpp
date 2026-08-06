#include "mini_jass/movegen.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>

namespace mini_jass {
namespace {

enum class Cell : std::uint8_t {
    Empty,
    WhiteMan,
    BlackMan,
    WhiteKing,
    BlackKing,
};

using Board = std::array<Cell, kBoardSize * kBoardSize>;

[[nodiscard]] std::size_t cell_index(const int row, const int column) noexcept {
    return static_cast<std::size_t>(row * kBoardSize + column);
}

[[nodiscard]] bool inside(const int row, const int column) noexcept {
    return row >= 0 && row < kBoardSize && column >= 0 && column < kBoardSize;
}

[[nodiscard]] std::optional<std::uint8_t> reference_square_at(
    const int row,
    const int column) noexcept {
    if (!inside(row, column) || ((row + column) & 1) != 0) {
        return std::nullopt;
    }

    std::uint8_t square = 0;
    for (int scan_row = 0; scan_row < kBoardSize; ++scan_row) {
        for (int scan_column = 0; scan_column < kBoardSize; ++scan_column) {
            if (((scan_row + scan_column) & 1) != 0) {
                continue;
            }
            if (scan_row == row && scan_column == column) {
                return square;
            }
            ++square;
        }
    }
    return std::nullopt;
}

[[nodiscard]] std::pair<int, int> reference_coordinates(const std::uint8_t square) {
    std::uint8_t current = 0;
    for (int row = 0; row < kBoardSize; ++row) {
        for (int column = 0; column < kBoardSize; ++column) {
            if (((row + column) & 1) != 0) {
                continue;
            }
            if (current == square) {
                return {row, column};
            }
            ++current;
        }
    }
    throw std::logic_error{"invalid reference square"};
}

[[nodiscard]] bool belongs_to(const Cell cell, const Side side) noexcept {
    if (side == Side::White) {
        return cell == Cell::WhiteMan || cell == Cell::WhiteKing;
    }
    return cell == Cell::BlackMan || cell == Cell::BlackKing;
}

[[nodiscard]] bool is_king(const Cell cell) noexcept {
    return cell == Cell::WhiteKing || cell == Cell::BlackKing;
}

[[nodiscard]] Board make_reference_board(const State& state) {
    Board board{};
    board.fill(Cell::Empty);
    for (std::uint8_t square = 0; square < kPlayableSquareCount; ++square) {
        const auto [row, column] = reference_coordinates(square);
        Cell cell = Cell::Empty;
        if ((state.white_men & square_bit(square)) != 0) {
            cell = Cell::WhiteMan;
        } else if ((state.black_men & square_bit(square)) != 0) {
            cell = Cell::BlackMan;
        } else if ((state.white_kings & square_bit(square)) != 0) {
            cell = Cell::WhiteKing;
        } else if ((state.black_kings & square_bit(square)) != 0) {
            cell = Cell::BlackKing;
        }
        board[cell_index(row, column)] = cell;
    }
    return board;
}

void append_reference_captures(
    const Board& board,
    const Side side,
    const Cell moving_piece,
    const std::uint8_t origin,
    const int row,
    const int column,
    Move path,
    std::vector<Move>& moves) {
    bool extended = false;
    for (const int row_delta : {-1, 1}) {
        for (const int column_delta : {-1, 1}) {
            const int captured_row = row + row_delta;
            const int captured_column = column + column_delta;
            const int landing_row = row + 2 * row_delta;
            const int landing_column = column + 2 * column_delta;
            if (!inside(landing_row, landing_column)) {
                continue;
            }

            const Cell captured = board[cell_index(captured_row, captured_column)];
            if (captured == Cell::Empty || belongs_to(captured, side) ||
                board[cell_index(landing_row, landing_column)] != Cell::Empty) {
                continue;
            }
            const auto landing_square = reference_square_at(landing_row, landing_column);
            if (!landing_square.has_value()) {
                continue;
            }
            if (path.landing_count >= path.landings.size()) {
                throw std::logic_error{"reference capture exceeds L1 material bound"};
            }

            Board continuation_board = board;
            continuation_board[cell_index(row, column)] = Cell::Empty;
            continuation_board[cell_index(captured_row, captured_column)] = Cell::Empty;
            continuation_board[cell_index(landing_row, landing_column)] = moving_piece;

            Move continuation = path;
            continuation.landings[continuation.landing_count] = *landing_square;
            ++continuation.landing_count;
            append_reference_captures(
                continuation_board,
                side,
                moving_piece,
                origin,
                landing_row,
                landing_column,
                continuation,
                moves);
            extended = true;
        }
    }

    if (!extended && path.landing_count != 0) {
        path.from = origin;
        moves.push_back(path);
    }
}

}  // namespace

std::vector<Move> generate_reference_board_moves(const State& state) {
    const StateError error = validate_state(state);
    if (error != StateError::None) {
        throw std::invalid_argument{std::string{to_string(error)}};
    }

    const Side side = state.side_to_move;
    const Board board = make_reference_board(state);
    std::vector<Move> captures;

    for (int row = 0; row < kBoardSize; ++row) {
        for (int column = 0; column < kBoardSize; ++column) {
            const Cell piece = board[cell_index(row, column)];
            if (!belongs_to(piece, side)) {
                continue;
            }
            const auto origin = reference_square_at(row, column);
            Move path;
            path.from = *origin;
            append_reference_captures(
                board, side, piece, *origin, row, column, path, captures);
        }
    }

    if (!captures.empty()) {
        std::sort(captures.begin(), captures.end(), MoveLess{});
        captures.erase(std::unique(captures.begin(), captures.end()), captures.end());
        return captures;
    }

    std::vector<Move> quiet;
    const int forward = side == Side::White ? -1 : 1;
    for (int row = 0; row < kBoardSize; ++row) {
        for (int column = 0; column < kBoardSize; ++column) {
            const Cell piece = board[cell_index(row, column)];
            if (!belongs_to(piece, side)) {
                continue;
            }
            const auto from = reference_square_at(row, column);
            for (const int row_delta : {-1, 1}) {
                if (!is_king(piece) && row_delta != forward) {
                    continue;
                }
                for (const int column_delta : {-1, 1}) {
                    const int destination_row = row + row_delta;
                    const int destination_column = column + column_delta;
                    if (!inside(destination_row, destination_column) ||
                        board[cell_index(destination_row, destination_column)] != Cell::Empty) {
                        continue;
                    }
                    const auto to = reference_square_at(destination_row, destination_column);
                    if (to.has_value()) {
                        quiet.push_back(one_landing_move(*from, *to));
                    }
                }
            }
        }
    }
    std::sort(quiet.begin(), quiet.end(), MoveLess{});
    return quiet;
}

}  // namespace mini_jass
