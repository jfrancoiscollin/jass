#include "mini_jass/l2_move.hpp"

#include <algorithm>
#include <cstdlib>
#include <stdexcept>
#include <tuple>
#include <vector>

namespace mini_jass::l2 {
namespace {
void hash_byte(std::uint64_t& hash, const std::uint8_t value) noexcept {
    hash ^= value;
    hash *= 1099511628211ULL;
}
}

bool MoveLess::operator()(const Move& lhs, const Move& rhs) const noexcept {
    return std::tie(lhs.from, lhs.landings[0], lhs.landing_count, lhs.landings[1]) <
           std::tie(rhs.from, rhs.landings[0], rhs.landing_count, rhs.landings[1]);
}

Move one_landing_move(const std::uint8_t from, const std::uint8_t to) noexcept {
    return Move{from, {to, kNoSquare}, 1};
}
Move two_landing_move(const std::uint8_t from, const std::uint8_t first,
                      const std::uint8_t second) noexcept {
    return Move{from, {first, second}, 2};
}
bool is_quiet_step(const std::uint8_t from, const std::uint8_t to) noexcept {
    if (from >= kPlayableSquareCount || to >= kPlayableSquareCount) return false;
    const Coordinate a = kSquareCoordinates[from];
    const Coordinate b = kSquareCoordinates[to];
    return std::abs(static_cast<int>(a.row) - b.row) == 1 &&
           std::abs(static_cast<int>(a.column) - b.column) == 1;
}
bool is_jump_step(const std::uint8_t from, const std::uint8_t to) noexcept {
    if (from >= kPlayableSquareCount || to >= kPlayableSquareCount) return false;
    const Coordinate a = kSquareCoordinates[from];
    const Coordinate b = kSquareCoordinates[to];
    return std::abs(static_cast<int>(a.row) - b.row) == 2 &&
           std::abs(static_cast<int>(a.column) - b.column) == 2;
}
std::optional<std::uint8_t> jumped_square(
    const std::uint8_t from, const std::uint8_t to) noexcept {
    if (!is_jump_step(from, to)) return std::nullopt;
    const Coordinate a = kSquareCoordinates[from];
    const Coordinate b = kSquareCoordinates[to];
    const Coordinate middle{static_cast<std::uint8_t>((a.row + b.row) / 2),
                            static_cast<std::uint8_t>((a.column + b.column) / 2)};
    for (std::uint8_t square = 0; square < kPlayableSquareCount; ++square) {
        if (kSquareCoordinates[square] == middle) return square;
    }
    return std::nullopt;
}
bool is_capture_move(const Move& move) noexcept {
    return move.landing_count != 0 && is_jump_step(move.from, move.landings[0]);
}
Move rotate180_move(const Move& move) noexcept {
    Move result = move;
    if (result.from < kPlayableSquareCount)
        result.from = static_cast<std::uint8_t>(kPlayableSquareCount - 1 - result.from);
    for (std::size_t i = 0; i < std::min<std::size_t>(move.landing_count, 2); ++i) {
        if (result.landings[i] < kPlayableSquareCount)
            result.landings[i] = static_cast<std::uint8_t>(kPlayableSquareCount - 1 - result.landings[i]);
    }
    return result;
}

const std::array<Move, kActionCount>& action_vocabulary() {
    static const std::array<Move, kActionCount> vocabulary = [] {
        std::vector<Move> paths;
        for (std::uint8_t from = 0; from < kPlayableSquareCount; ++from) {
            for (std::uint8_t first = 0; first < kPlayableSquareCount; ++first) {
                if (is_quiet_step(from, first) || is_jump_step(from, first))
                    paths.push_back(one_landing_move(from, first));
                const auto captured = jumped_square(from, first);
                if (!captured.has_value()) continue;
                for (std::uint8_t second = 0; second < kPlayableSquareCount; ++second) {
                    const auto captured_second = jumped_square(first, second);
                    if (captured_second.has_value() && second != from &&
                        captured_second != captured) {
                        paths.push_back(two_landing_move(from, first, second));
                    }
                }
            }
        }
        std::sort(paths.begin(), paths.end(), MoveLess{});
        paths.erase(std::unique(paths.begin(), paths.end()), paths.end());
        if (paths.size() != kActionCount)
            throw std::logic_error{"Mini-Jass L2 action vocabulary must contain 122 paths"};
        std::array<Move, kActionCount> result{};
        std::copy(paths.begin(), paths.end(), result.begin());
        return result;
    }();
    return vocabulary;
}
std::optional<std::uint8_t> action_id(const Move& move) {
    const auto& vocabulary = action_vocabulary();
    const auto found = std::lower_bound(vocabulary.begin(), vocabulary.end(), move, MoveLess{});
    if (found == vocabulary.end() || *found != move) return std::nullopt;
    return static_cast<std::uint8_t>(std::distance(vocabulary.begin(), found));
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

}  // namespace mini_jass::l2
