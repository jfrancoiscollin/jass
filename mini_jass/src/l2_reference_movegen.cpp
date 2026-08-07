#include "mini_jass/l2_movegen.hpp"

#include <algorithm>
#include <array>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>

namespace mini_jass::l2 {
namespace {

enum class Cell : std::uint8_t { Empty, WhiteMan, BlackMan, WhiteKing, BlackKing };
using Board = std::array<Cell, kBoardSize * kBoardSize>;

[[nodiscard]] std::size_t cell(const int row, const int column) noexcept {
    return static_cast<std::size_t>(row * kBoardSize + column);
}
[[nodiscard]] bool inside(const int row, const int column) noexcept {
    return row >= 0 && row < kBoardSize && column >= 0 && column < kBoardSize;
}
[[nodiscard]] std::optional<std::uint8_t> square_at(const int row, const int column) noexcept {
    if (!inside(row, column) || ((row + column) & 1) != 0) return std::nullopt;
    std::uint8_t square = 0;
    for (int r = 0; r < kBoardSize; ++r) for (int c = 0; c < kBoardSize; ++c) {
        if (((r + c) & 1) != 0) continue;
        if (r == row && c == column) return square;
        ++square;
    }
    return std::nullopt;
}
[[nodiscard]] std::pair<int, int> coordinates(const std::uint8_t target) {
    std::uint8_t square = 0;
    for (int row = 0; row < kBoardSize; ++row) for (int column = 0; column < kBoardSize; ++column) {
        if (((row + column) & 1) != 0) continue;
        if (square++ == target) return {row, column};
    }
    throw std::logic_error{"invalid L2 reference square"};
}
[[nodiscard]] bool belongs_to(const Cell value, const Side side) noexcept {
    return side == Side::White
        ? value == Cell::WhiteMan || value == Cell::WhiteKing
        : value == Cell::BlackMan || value == Cell::BlackKing;
}
[[nodiscard]] bool is_king(const Cell value) noexcept {
    return value == Cell::WhiteKing || value == Cell::BlackKing;
}
[[nodiscard]] Board make_board(const State& state) {
    Board board{};
    board.fill(Cell::Empty);
    for (std::uint8_t square = 0; square < kPlayableSquareCount; ++square) {
        const auto [row, column] = coordinates(square);
        Cell value = Cell::Empty;
        if ((state.white_men & square_bit(square)) != 0) value = Cell::WhiteMan;
        else if ((state.black_men & square_bit(square)) != 0) value = Cell::BlackMan;
        else if ((state.white_kings & square_bit(square)) != 0) value = Cell::WhiteKing;
        else if ((state.black_kings & square_bit(square)) != 0) value = Cell::BlackKing;
        board[cell(row, column)] = value;
    }
    return board;
}

void append_captures(const Board& board, const Side side, const Cell moving,
                     const std::uint8_t origin, const int row, const int column,
                     Move path, std::vector<Move>& moves) {
    bool extended = false;
    for (const int dr : {-1, 1}) for (const int dc : {-1, 1}) {
        const int cr = row + dr, cc = column + dc;
        const int lr = row + 2 * dr, lc = column + 2 * dc;
        if (!inside(lr, lc)) continue;
        const Cell captured = board[cell(cr, cc)];
        if (captured == Cell::Empty || belongs_to(captured, side) ||
            board[cell(lr, lc)] != Cell::Empty) continue;
        const auto landing = square_at(lr, lc);
        if (!landing.has_value()) continue;
        if (path.landing_count >= path.landings.size())
            throw std::logic_error{"L2 reference capture exceeds material bound"};
        Board next = board;
        next[cell(row, column)] = Cell::Empty;
        next[cell(cr, cc)] = Cell::Empty;
        next[cell(lr, lc)] = moving;
        Move continuation = path;
        continuation.landings[continuation.landing_count++] = *landing;
        append_captures(next, side, moving, origin, lr, lc, continuation, moves);
        extended = true;
    }
    if (!extended && path.landing_count != 0) {
        path.from = origin;
        moves.push_back(path);
    }
}

}  // namespace

std::vector<Move> generate_reference_board_moves(const State& state) {
    const StateError error = validate_state(state);
    if (error != StateError::None) throw std::invalid_argument{std::string{to_string(error)}};
    const Side side = state.side_to_move;
    const Board board = make_board(state);
    std::vector<Move> captures;
    for (int row = 0; row < kBoardSize; ++row) for (int column = 0; column < kBoardSize; ++column) {
        const Cell piece = board[cell(row, column)];
        if (!belongs_to(piece, side)) continue;
        Move path;
        path.from = *square_at(row, column);
        append_captures(board, side, piece, path.from, row, column, path, captures);
    }
    if (!captures.empty()) {
        std::sort(captures.begin(), captures.end(), MoveLess{});
        captures.erase(std::unique(captures.begin(), captures.end()), captures.end());
        return captures;
    }

    std::vector<Move> quiet;
    const int forward = side == Side::White ? -1 : 1;
    for (int row = 0; row < kBoardSize; ++row) for (int column = 0; column < kBoardSize; ++column) {
        const Cell piece = board[cell(row, column)];
        if (!belongs_to(piece, side)) continue;
        for (const int dr : {-1, 1}) {
            if (!is_king(piece) && dr != forward) continue;
            for (const int dc : {-1, 1}) {
                const int r = row + dr, c = column + dc;
                if (!inside(r, c) || board[cell(r, c)] != Cell::Empty) continue;
                const auto to = square_at(r, c);
                if (to.has_value()) quiet.push_back(one_landing_move(*square_at(row, column), *to));
            }
        }
    }
    std::sort(quiet.begin(), quiet.end(), MoveLess{});
    return quiet;
}

}  // namespace mini_jass::l2
