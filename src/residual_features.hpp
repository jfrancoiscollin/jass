// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#include "position.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace jass::residual_features {

inline constexpr std::size_t CTX2_WIDTH = 15;
inline constexpr std::size_t F1_WIDTH = 12;
inline constexpr std::size_t F2_WIDTH = 14;
inline constexpr std::size_t F3_WIDTH = 12;
inline constexpr std::size_t F4_WIDTH = 16;
inline constexpr std::size_t F5_WIDTH = 12;
inline constexpr std::size_t ALL_NEW_WIDTH = F1_WIDTH + F2_WIDTH + F3_WIDTH + F4_WIDTH + F5_WIDTH;
inline constexpr std::size_t TOTAL_WIDTH = CTX2_WIDTH + ALL_NEW_WIDTH;

inline constexpr std::array<int, 16> CENTRAL_16 = {
    12, 13, 17, 18, 19, 22, 23, 24,
    27, 28, 29, 32, 33, 34, 38, 39,
};

struct FeatureVector {
    std::array<float, CTX2_WIDTH> ctx2_ref{};
    std::array<float, F1_WIDTH> capture_geometry{};
    std::array<float, F2_WIDTH> response_frontier{};
    std::array<float, F3_WIDTH> promotion_race{};
    std::array<float, F4_WIDTH> structure_graph{};
    std::array<float, F5_WIDTH> king_geometry_plus{};
    bool ctx2_available{false};

    std::array<float, ALL_NEW_WIDTH> all_new() const noexcept;
    std::array<float, TOTAL_WIDTH> packed() const noexcept;
};

FeatureVector extract(const Position& child);

// F6-only production path. It deliberately does not compute the unrelated
// CTX2 reference family. Feature values and F1..F5 order are identical to
// extract(child).all_new().
struct Profile {
    std::array<std::uint64_t, 5> family_ns{};
    std::uint64_t movegen_calls{0};
    std::uint64_t response_enumerations{0};
};
FeatureVector extract_f6(const Position& child, Profile* profile = nullptr);

const std::array<const char*, CTX2_WIDTH>& ctx2_names() noexcept;
const std::array<const char*, F1_WIDTH>& f1_names() noexcept;
const std::array<const char*, F2_WIDTH>& f2_names() noexcept;
const std::array<const char*, F3_WIDTH>& f3_names() noexcept;
const std::array<const char*, F4_WIDTH>& f4_names() noexcept;
const std::array<const char*, F5_WIDTH>& f5_names() noexcept;

}  // namespace jass::residual_features
