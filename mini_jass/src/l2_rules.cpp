#include "mini_jass/l2_rules.hpp"

#include <algorithm>
#include <array>
#include <bit>

namespace mini_jass::l2 {
namespace {

[[nodiscard]] unsigned piece_count(const Bitboard bits) noexcept {
    return std::popcount(bits);
}

[[nodiscard]] std::uint64_t side_code(
    const Bitboard men, const Bitboard kings) noexcept {
    std::array<std::uint8_t, 2> pieces{};
    std::size_t count = 0;
    for (std::uint8_t square = 0; square < kPlayableSquareCount; ++square) {
        if ((men & square_bit(square)) != 0) {
            pieces[count++] = static_cast<std::uint8_t>(square + 1);
        }
    }
    for (std::uint8_t square = 0; square < kPlayableSquareCount; ++square) {
        if ((kings & square_bit(square)) != 0) {
            pieces[count++] = static_cast<std::uint8_t>(square + 19);
        }
    }
    std::sort(pieces.begin(), pieces.begin() + static_cast<std::ptrdiff_t>(count));
    return pieces[0] + 37ULL * pieces[1];
}

}  // namespace

State initial_state() noexcept {
    State state;
    state.white_men = square_bit(10) | square_bit(17);
    state.black_men = square_bit(2) | square_bit(7);
    state.side_to_move = Side::White;
    return state;
}

StateError validate_state(const State& state) noexcept {
    const Bitboard occupied = state.white_men | state.black_men |
                              state.white_kings | state.black_kings;
    if ((occupied & ~kPlayableMask) != 0) return StateError::HighBitsSet;
    const unsigned total = piece_count(state.white_men) + piece_count(state.black_men) +
                           piece_count(state.white_kings) + piece_count(state.black_kings);
    if (piece_count(occupied) != total) return StateError::OverlappingPieces;
    if (piece_count(state.white_men | state.white_kings) > kMaxPiecesPerSide)
        return StateError::TooManyWhitePieces;
    if (piece_count(state.black_men | state.black_kings) > kMaxPiecesPerSide)
        return StateError::TooManyBlackPieces;
    if ((state.white_men & kBlackHomeMask) != 0) return StateError::UnpromotedWhiteMan;
    if ((state.black_men & kWhiteHomeMask) != 0) return StateError::UnpromotedBlackMan;
    if (state.side_to_move != Side::White && state.side_to_move != Side::Black)
        return StateError::InvalidSideToMove;
    if (state.reversible_plies > kReversiblePlyLimit)
        return StateError::InvalidReversiblePlyCount;
    return StateError::None;
}

std::string_view to_string(const StateError error) noexcept {
    switch (error) {
        case StateError::None: return "none";
        case StateError::HighBitsSet: return "high_bits_set";
        case StateError::OverlappingPieces: return "overlapping_pieces";
        case StateError::TooManyWhitePieces: return "too_many_white_pieces";
        case StateError::TooManyBlackPieces: return "too_many_black_pieces";
        case StateError::UnpromotedWhiteMan: return "unpromoted_white_man";
        case StateError::UnpromotedBlackMan: return "unpromoted_black_man";
        case StateError::InvalidSideToMove: return "invalid_side_to_move";
        case StateError::InvalidReversiblePlyCount: return "invalid_reversible_ply_count";
    }
    return "unknown";
}

Bitboard rotate180(const Bitboard bits) noexcept {
    Bitboard result{};
    for (std::uint8_t square = 0; square < kPlayableSquareCount; ++square) {
        if ((bits & square_bit(square)) != 0) {
            result |= square_bit(static_cast<std::uint8_t>(kPlayableSquareCount - 1 - square));
        }
    }
    return result;
}

State rotate180_and_swap_colours(const State& state) noexcept {
    return State{
        rotate180(state.black_men), rotate180(state.white_men),
        rotate180(state.black_kings), rotate180(state.white_kings),
        opposite(state.side_to_move), state.reversible_plies,
    };
}

std::uint64_t state_key(const State& state) noexcept {
    constexpr std::uint64_t kSideRadix = 37ULL * 37ULL;
    std::uint64_t key = side_code(state.white_men, state.white_kings);
    key += kSideRadix * side_code(state.black_men, state.black_kings);
    key += kSideRadix * kSideRadix * (state.side_to_move == Side::Black ? 1ULL : 0ULL);
    key += kSideRadix * kSideRadix * 2ULL * state.reversible_plies;
    return key;
}

}  // namespace mini_jass::l2
