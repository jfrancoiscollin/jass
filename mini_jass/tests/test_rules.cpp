#include "mini_jass/rules.hpp"

#include <cstdint>
#include <iostream>

namespace {

int failures = 0;

void expect(const bool condition, const char* const message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

}  // namespace

int main() {
    using namespace mini_jass;

    const State initial = initial_state();
    expect(validate_state(initial) == StateError::None, "initial state is valid");
    expect(initial.white_men == (square_bit(10) | square_bit(12)),
           "initial White placement is normative");
    expect(initial.black_men == (square_bit(0) | square_bit(2)),
           "initial Black placement is normative");
    expect(initial.side_to_move == Side::White, "White moves first");

    State invalid = initial;
    invalid.white_kings = square_bit(0);
    expect(validate_state(invalid) == StateError::OverlappingPieces,
           "overlapping pieces are rejected");

    invalid = {};
    invalid.white_kings = static_cast<Bitboard>(Bitboard{1} << 13);
    expect(validate_state(invalid) == StateError::HighBitsSet,
           "unused high bits are rejected");

    invalid = {};
    invalid.white_men = square_bit(3) | square_bit(6) | square_bit(8);
    expect(validate_state(invalid) == StateError::TooManyWhitePieces,
           "more than two White pieces are rejected");

    invalid = {};
    invalid.white_men = square_bit(1);
    expect(validate_state(invalid) == StateError::UnpromotedWhiteMan,
           "White men cannot persist on Black's home rank");

    invalid = {};
    invalid.black_men = square_bit(11);
    expect(validate_state(invalid) == StateError::UnpromotedBlackMan,
           "Black men cannot persist on White's home rank");

    invalid = {};
    invalid.side_to_move = static_cast<Side>(2);
    expect(validate_state(invalid) == StateError::InvalidSideToMove,
           "invalid side-to-move values are rejected");

    invalid = {};
    invalid.reversible_plies = 21;
    expect(validate_state(invalid) == StateError::InvalidReversiblePlyCount,
           "reversible counter values above the limit are rejected");

    for (std::uint8_t square = 0; square < kPlayableSquareCount; ++square) {
        const Bitboard bit = square_bit(square);
        expect(rotate180(rotate180(bit)) == bit, "bitboard rotation is an involution");

        const Coordinate coordinate = kSquareCoordinates[square];
        const Coordinate rotated =
            kSquareCoordinates[static_cast<std::uint8_t>(kPlayableSquareCount - 1 - square)];
        expect(rotated.row == kBoardSize - 1 - coordinate.row &&
                   rotated.column == kBoardSize - 1 - coordinate.column,
               "square permutation is a geometric 180-degree rotation");
    }

    const State rotated_initial = rotate180_and_swap_colours(initial);
    expect(rotated_initial.white_men == initial.white_men &&
               rotated_initial.black_men == initial.black_men &&
               rotated_initial.white_kings == initial.white_kings &&
               rotated_initial.black_kings == initial.black_kings,
           "initial piece placement is invariant under colour-swapping rotation");
    expect(rotated_initial.side_to_move == Side::Black,
           "colour-swapping rotation also swaps the side to move");
    expect(rotate180_and_swap_colours(rotated_initial) == initial,
           "initial state returns after applying the symmetry twice");

    State representative;
    representative.white_men = square_bit(3);
    representative.white_kings = square_bit(10);
    representative.black_men = square_bit(8);
    representative.black_kings = square_bit(0);
    representative.side_to_move = Side::Black;
    representative.reversible_plies = 7;
    expect(validate_state(representative) == StateError::None,
           "representative state is valid");
    expect(rotate180_and_swap_colours(rotate180_and_swap_colours(representative)) ==
               representative,
           "state symmetry is an involution");
    expect(validate_state(rotate180_and_swap_colours(representative)) == StateError::None,
           "state symmetry preserves validity");

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return 1;
    }

    std::cout << "all Mini-Jass rule tests passed\n";
    return 0;
}
