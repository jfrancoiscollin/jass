#pragma once

#include <cstdint>

namespace mini_jass {

struct EnumerationSummary {
    std::uint64_t state_count{};
    std::uint64_t transition_count{};
    std::uint64_t loss_terminal_count{};
    std::uint64_t draw_terminal_count{};
    std::uint64_t graph_hash{};

    friend constexpr bool operator==(
        const EnumerationSummary&,
        const EnumerationSummary&) = default;
};

inline constexpr EnumerationSummary kReachableGraphV1{
    263829,
    645620,
    499,
    14369,
    3347327730907747976ULL,
};

[[nodiscard]] EnumerationSummary enumerate_reachable_states();

}  // namespace mini_jass
