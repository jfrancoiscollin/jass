#include "mini_jass/game.hpp"

#include <algorithm>
#include <stdexcept>
#include <string>

namespace mini_jass {
namespace {

[[nodiscard]] Bitboard side_pieces(const State& state, const Side side) noexcept {
    if (side == Side::White) {
        return static_cast<Bitboard>(state.white_men | state.white_kings);
    }
    return static_cast<Bitboard>(state.black_men | state.black_kings);
}

void remove_captured_piece(State& state, const Side moving_side, const std::uint8_t square) {
    const Bitboard mask = static_cast<Bitboard>(~square_bit(square));
    if (moving_side == Side::White) {
        state.black_men &= mask;
        state.black_kings &= mask;
    } else {
        state.white_men &= mask;
        state.white_kings &= mask;
    }
}

}  // namespace

TerminalStatus terminal_status(const State& state) {
    const StateError error = validate_state(state);
    if (error != StateError::None) {
        throw std::invalid_argument{std::string{to_string(error)}};
    }
    if (side_pieces(state, state.side_to_move) == 0) {
        return TerminalStatus::SideToMoveLoss;
    }
    if (generate_board_moves(state).empty()) {
        return TerminalStatus::SideToMoveLoss;
    }
    if (state.reversible_plies >= kReversiblePlyLimit) {
        return TerminalStatus::Draw;
    }
    return TerminalStatus::Ongoing;
}

std::string_view to_string(const TerminalStatus status) noexcept {
    switch (status) {
        case TerminalStatus::Ongoing:
            return "ongoing";
        case TerminalStatus::SideToMoveLoss:
            return "side_to_move_loss";
        case TerminalStatus::Draw:
            return "draw";
    }
    return "unknown";
}

std::vector<Move> legal_moves(const State& state) {
    if (terminal_status(state) != TerminalStatus::Ongoing) {
        return {};
    }
    return generate_board_moves(state);
}

State apply_move(const State& state, const Move& move) {
    const std::vector<Move> moves = legal_moves(state);
    if (std::find(moves.begin(), moves.end(), move) == moves.end()) {
        throw std::invalid_argument{"move is not legal in the supplied state"};
    }

    State result = state;
    const Side moving_side = state.side_to_move;
    const Bitboard origin = square_bit(move.from);
    bool moving_man = false;

    if (moving_side == Side::White) {
        moving_man = (result.white_men & origin) != 0;
        result.white_men &= static_cast<Bitboard>(~origin);
        result.white_kings &= static_cast<Bitboard>(~origin);
    } else {
        moving_man = (result.black_men & origin) != 0;
        result.black_men &= static_cast<Bitboard>(~origin);
        result.black_kings &= static_cast<Bitboard>(~origin);
    }

    bool captured = false;
    std::uint8_t current = move.from;
    for (std::uint8_t index = 0; index < move.landing_count; ++index) {
        const std::uint8_t destination = move.landings[index];
        const auto jumped = jumped_square(current, destination);
        if (jumped.has_value()) {
            remove_captured_piece(result, moving_side, *jumped);
            captured = true;
        }
        current = destination;
    }

    const Bitboard destination = square_bit(current);
    const bool promotes = moving_man &&
                          ((moving_side == Side::White &&
                            (destination & kBlackHomeMask) != 0) ||
                           (moving_side == Side::Black &&
                            (destination & kWhiteHomeMask) != 0));

    if (moving_side == Side::White) {
        if (moving_man && !promotes) {
            result.white_men |= destination;
        } else {
            result.white_kings |= destination;
        }
    } else {
        if (moving_man && !promotes) {
            result.black_men |= destination;
        } else {
            result.black_kings |= destination;
        }
    }

    if (captured || moving_man) {
        result.reversible_plies = 0;
    } else {
        ++result.reversible_plies;
    }
    result.side_to_move = opposite(moving_side);

    const StateError error = validate_state(result);
    if (error != StateError::None) {
        throw std::logic_error{std::string{"legal move produced invalid state: "} +
                               std::string{to_string(error)}};
    }
    return result;
}

}  // namespace mini_jass
