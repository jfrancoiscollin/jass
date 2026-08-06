#include "mini_jass/game.hpp"

#include <cstddef>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

namespace {

int failures = 0;
std::uint64_t compared_states = 0;
std::uint64_t applied_moves = 0;

void expect(const bool condition, const char* const message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

void compare_state(const mini_jass::State& state) {
    const std::vector<mini_jass::Move> production = mini_jass::generate_board_moves(state);
    const std::vector<mini_jass::Move> reference =
        mini_jass::generate_reference_board_moves(state);
    ++compared_states;

    if (production != reference) {
        std::cerr << "FAIL: move generator mismatch for state key "
                  << mini_jass::state_key(state) << '\n';
        ++failures;
        return;
    }

    if (mini_jass::terminal_status(state) != mini_jass::TerminalStatus::Ongoing) {
        return;
    }
    for (const mini_jass::Move& move : production) {
        expect(mini_jass::action_id(move).has_value(),
               "every generated move belongs to the action vocabulary");
        const mini_jass::State child = mini_jass::apply_move(state, move);
        expect(mini_jass::validate_state(child) == mini_jass::StateError::None,
               "every legal move produces a valid state");
        ++applied_moves;
    }
}

void enumerate_structural_states(
    const std::uint8_t square,
    const std::uint8_t white_count,
    const std::uint8_t black_count,
    mini_jass::State state) {
    using namespace mini_jass;

    if (square == kPlayableSquareCount) {
        for (const Side side : {Side::White, Side::Black}) {
            state.side_to_move = side;
            compare_state(state);
        }
        return;
    }

    enumerate_structural_states(square + 1, white_count, black_count, state);

    if (white_count < kMaxPiecesPerSide) {
        if ((square_bit(square) & kBlackHomeMask) == 0) {
            State with_white_man = state;
            with_white_man.white_men |= square_bit(square);
            enumerate_structural_states(
                square + 1, white_count + 1, black_count, with_white_man);
        }
        State with_white_king = state;
        with_white_king.white_kings |= square_bit(square);
        enumerate_structural_states(
            square + 1, white_count + 1, black_count, with_white_king);
    }

    if (black_count < kMaxPiecesPerSide) {
        if ((square_bit(square) & kWhiteHomeMask) == 0) {
            State with_black_man = state;
            with_black_man.black_men |= square_bit(square);
            enumerate_structural_states(
                square + 1, white_count, black_count + 1, with_black_man);
        }
        State with_black_king = state;
        with_black_king.black_kings |= square_bit(square);
        enumerate_structural_states(
            square + 1, white_count, black_count + 1, with_black_king);
    }
}

}  // namespace

int main() {
    using namespace mini_jass;

    const auto& vocabulary = action_vocabulary();
    expect(vocabulary.size() == kActionCount, "action vocabulary contains 72 paths");
    expect(action_vocabulary_hash() == kActionVocabularyHashV1,
           "action vocabulary matches the frozen v1 hash");
    for (std::size_t index = 0; index < vocabulary.size(); ++index) {
        const auto id = action_id(vocabulary[index]);
        expect(id.has_value() && *id == index, "action IDs round-trip exactly");
    }

    State multi_capture;
    multi_capture.black_men = square_bit(0);
    multi_capture.white_men = square_bit(3) | square_bit(9);
    multi_capture.side_to_move = Side::Black;
    const Move forced_multi_capture = two_landing_move(0, 6, 12);
    expect(generate_board_moves(multi_capture) == std::vector<Move>{forced_multi_capture},
           "mandatory multi-capture is generated as one complete move");
    expect(generate_reference_board_moves(multi_capture) ==
               std::vector<Move>{forced_multi_capture},
           "reference generator agrees on mandatory multi-capture");

    const State after_multi_capture = apply_move(multi_capture, forced_multi_capture);
    expect(after_multi_capture.black_men == 0 &&
               after_multi_capture.black_kings == square_bit(12),
           "promotion happens after the complete capture sequence");
    expect(after_multi_capture.white_men == 0,
           "captured pieces are removed immediately");
    expect(terminal_status(after_multi_capture) == TerminalStatus::SideToMoveLoss,
           "capturing the last opposing piece is terminal");

    State promotion;
    promotion.black_men = square_bit(8);
    promotion.white_kings = square_bit(0);
    promotion.side_to_move = Side::Black;
    const State promoted = apply_move(promotion, one_landing_move(8, 10));
    expect(promoted.black_men == 0 && promoted.black_kings == square_bit(10),
           "a man promotes after a quiet move to the home rank");
    expect(promoted.reversible_plies == 0, "man moves reset the reversible counter");

    State reversible;
    reversible.white_kings = square_bit(6);
    reversible.black_kings = square_bit(0);
    reversible.side_to_move = Side::White;
    reversible.reversible_plies = 19;
    const State drawn = apply_move(reversible, one_landing_move(6, 8));
    expect(drawn.reversible_plies == 20, "quiet king moves increment the counter");
    expect(terminal_status(drawn) == TerminalStatus::Draw,
           "the reversible-ply limit produces a draw when mobility remains");

    State blocked;
    blocked.white_men = square_bit(3);
    blocked.black_kings = square_bit(0) | square_bit(1);
    blocked.side_to_move = Side::White;
    blocked.reversible_plies = 20;
    expect(terminal_status(blocked) == TerminalStatus::SideToMoveLoss,
           "no-move loss takes precedence over the reversible draw limit");

    enumerate_structural_states(0, 0, 0, State{});
    expect(compared_states == 104794,
           "the complete structural state domain has the frozen v1 size");
    expect(applied_moves == 258632,
           "the structural domain has the frozen v1 legal-move count");

    std::cout << "action_hash=" << action_vocabulary_hash() << '\n'
              << "compared_states=" << compared_states << '\n'
              << "applied_moves=" << applied_moves << '\n';

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return 1;
    }
    return 0;
}
