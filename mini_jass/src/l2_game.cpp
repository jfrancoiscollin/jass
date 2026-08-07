#include "mini_jass/l2_game.hpp"

#include <algorithm>
#include <stdexcept>
#include <string>

namespace mini_jass::l2 {
namespace {
[[nodiscard]] Bitboard side_pieces(const State& state, const Side side) noexcept {
    return side == Side::White ? state.white_men | state.white_kings
                               : state.black_men | state.black_kings;
}
void remove_captured(State& state, const Side moving, const std::uint8_t square) {
    const Bitboard mask = ~square_bit(square);
    if (moving == Side::White) { state.black_men &= mask; state.black_kings &= mask; }
    else { state.white_men &= mask; state.white_kings &= mask; }
}
}

TerminalStatus terminal_status(const State& state) {
    const StateError error = validate_state(state);
    if (error != StateError::None) throw std::invalid_argument{std::string{to_string(error)}};
    if (side_pieces(state, state.side_to_move) == 0 || generate_board_moves(state).empty())
        return TerminalStatus::SideToMoveLoss;
    if (state.reversible_plies >= kReversiblePlyLimit) return TerminalStatus::Draw;
    return TerminalStatus::Ongoing;
}
std::string_view to_string(const TerminalStatus status) noexcept {
    switch (status) {
        case TerminalStatus::Ongoing: return "ongoing";
        case TerminalStatus::SideToMoveLoss: return "side_to_move_loss";
        case TerminalStatus::Draw: return "draw";
    }
    return "unknown";
}
std::vector<Move> legal_moves(const State& state) {
    return terminal_status(state) == TerminalStatus::Ongoing
        ? generate_board_moves(state) : std::vector<Move>{};
}
State apply_move(const State& state, const Move& move) {
    const std::vector<Move> moves = legal_moves(state);
    if (std::find(moves.begin(), moves.end(), move) == moves.end())
        throw std::invalid_argument{"move is not legal in the supplied L2 state"};
    State result = state;
    const Side side = state.side_to_move;
    const Bitboard origin = square_bit(move.from);
    bool moving_man = false;
    if (side == Side::White) {
        moving_man = (result.white_men & origin) != 0;
        result.white_men &= ~origin; result.white_kings &= ~origin;
    } else {
        moving_man = (result.black_men & origin) != 0;
        result.black_men &= ~origin; result.black_kings &= ~origin;
    }
    bool captured = false;
    std::uint8_t current = move.from;
    for (std::uint8_t i = 0; i < move.landing_count; ++i) {
        const std::uint8_t destination = move.landings[i];
        const auto jumped = jumped_square(current, destination);
        if (jumped.has_value()) { remove_captured(result, side, *jumped); captured = true; }
        current = destination;
    }
    const Bitboard destination = square_bit(current);
    const bool promotes = moving_man &&
        ((side == Side::White && (destination & kBlackHomeMask) != 0) ||
         (side == Side::Black && (destination & kWhiteHomeMask) != 0));
    if (side == Side::White) {
        if (moving_man && !promotes) result.white_men |= destination;
        else result.white_kings |= destination;
    } else {
        if (moving_man && !promotes) result.black_men |= destination;
        else result.black_kings |= destination;
    }
    result.reversible_plies = captured || moving_man
        ? 0 : static_cast<std::uint8_t>(result.reversible_plies + 1);
    result.side_to_move = opposite(side);
    const StateError error = validate_state(result);
    if (error != StateError::None)
        throw std::logic_error{std::string{"legal L2 move produced invalid state: "} +
                               std::string{to_string(error)}};
    return result;
}

}  // namespace mini_jass::l2
