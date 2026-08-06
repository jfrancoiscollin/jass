#include "mini_jass/move.hpp"

#include <algorithm>
#include <array>
#include <cstdlib>
#include <stdexcept>
#include <tuple>
#include <vector>

namespace mini_jass {
namespace {

[[nodiscard]] int delta(const std::uint8_t lhs, const std::uint8_t rhs) noexcept {
    return static_cast<int>(lhs) - static_cast<int>(rhs);
}

void hash_byte(std::uint64_t& hash, const std::uint8_t value) noexcept {
    hash ^= value;
    hash *= 1099511628211ULL;
}

}  // namespace

bool MoveLess::operator()(const Move& lhs, const Move& rhs) const noexcept {
    return std::tie(lhs.from, lhs.landings[0], lhs.landing_count, lhs.landings[1]) <
           std::tie(rhs.from, rhs.landings[0], rhs.landing_count, rhs.landings[1]);
}

Move one_landing_move(const std::uint8_t from, const std::uint8_t to) noexcept {
    return Move{from, {to, kNoSquare}, 1};
}

Move two_landing_move(
    const std::uint8_t from,
    const std::uint8_t first,
    const std::uint8_t second) noexcept {
    return Move{from, {first, second}, 2};
}

bool is_quiet_step(const std::uint8_t from, const std::uint8_t to) noexcept {
    if (from >= kPlayableSquareCount || to >= kPlayableSquareCount) {
        return false;
    }
    const Coordinate origin = kSquareCoordinates[from];
    const Coordinate destination = kSquareCoordinates[to];
    return std::abs(delta(origin.row, destination.row)) == 1 &&
           std::abs(delta(origin.column, destination.column)) == 1;
}

bool is_jump_step(const std::uint8_t from, const std::uint8_t to) noexcept {
    if (from >= kPlayableSquareCount || to >= kPlayableSquareCount) {
        return false;
    }
    const Coordinate origin = kSquareCoordinates[from];
    const Coordinate destination = kSquareCoordinates[to];
    return std::abs(delta(origin.row, destination.row)) == 2 &&
           std::abs(delta(origin.column, destination.column)) == 2;
}

std::optional<std::uint8_t> jumped_square(
    const std::uint8_t from,
    const std::uint8_t to) noexcept {
    if (!is_jump_step(from, to)) {
        return std::nullopt;
    }

    const Coordinate origin = kSquareCoordinates[from];
    const Coordinate destination = kSquareCoordinates[to];
    const std::uint8_t middle_row =
        static_cast<std::uint8_t>((origin.row + destination.row) / 2);
    const std::uint8_t middle_column =
        static_cast<std::uint8_t>((origin.column + destination.column) / 2);

    for (std::uint8_t square = 0; square < kPlayableSquareCount; ++square) {
        if (kSquareCoordinates[square] == Coordinate{middle_row, middle_column}) {
            return square;
        }
    }
    return std::nullopt;
}

bool is_capture_move(const Move& move) noexcept {
    return move.landing_count >= 1 && is_jump_step(move.from, move.landings[0]);
}

Move rotate180_move(const Move& move) noexcept {
    Move rotated = move;
    if (move.from < kPlayableSquareCount) {
        rotated.from = static_cast<std::uint8_t>(kPlayableSquareCount - 1 - move.from);
    }
    const std::size_t landing_count = std::min<std::size_t>(
        move.landing_count, move.landings.size());
    for (std::size_t index = 0; index < landing_count; ++index) {
        if (move.landings[index] < kPlayableSquareCount) {
            rotated.landings[index] = static_cast<std::uint8_t>(
                kPlayableSquareCount - 1 - move.landings[index]);
        }
    }
    return rotated;
}

const std::array<Move, kActionCount>& action_vocabulary() {
    static const std::array<Move, kActionCount> vocabulary = [] {
        std::vector<Move> paths;
        paths.reserve(kActionCount);

        for (std::uint8_t from = 0; from < kPlayableSquareCount; ++from) {
            for (std::uint8_t first = 0; first < kPlayableSquareCount; ++first) {
                if (is_quiet_step(from, first) || is_jump_step(from, first)) {
                    paths.push_back(one_landing_move(from, first));
                }

                const auto first_capture = jumped_square(from, first);
                if (!first_capture.has_value()) {
                    continue;
                }
                for (std::uint8_t second = 0; second < kPlayableSquareCount; ++second) {
                    const auto second_capture = jumped_square(first, second);
                    if (!second_capture.has_value() || second == from ||
                        second_capture == first_capture) {
                        continue;
                    }
                    paths.push_back(two_landing_move(from, first, second));
                }
            }
        }

        std::sort(paths.begin(), paths.end(), MoveLess{});
        paths.erase(std::unique(paths.begin(), paths.end()), paths.end());
        if (paths.size() != kActionCount) {
            throw std::logic_error{"Mini-Jass action vocabulary must contain 72 paths"};
        }

        std::array<Move, kActionCount> result{};
        std::copy(paths.begin(), paths.end(), result.begin());
        return result;
    }();
    return vocabulary;
}

std::optional<std::uint8_t> action_id(const Move& move) {
    const auto& vocabulary = action_vocabulary();
    const auto iterator = std::lower_bound(
        vocabulary.begin(), vocabulary.end(), move, MoveLess{});
    if (iterator == vocabulary.end() || *iterator != move) {
        return std::nullopt;
    }
    return static_cast<std::uint8_t>(std::distance(vocabulary.begin(), iterator));
}

std::uint64_t action_vocabulary_hash() {
    std::uint64_t hash = 14695981039346656037ULL;
    for (const Move& move : action_vocabulary()) {
        hash_byte(hash, move.from);
        hash_byte(hash, move.landing_count);
        hash_byte(hash, move.landings[0]);
        hash_byte(hash, move.landings[1]);
    }
    return hash;
}

}  // namespace mini_jass
