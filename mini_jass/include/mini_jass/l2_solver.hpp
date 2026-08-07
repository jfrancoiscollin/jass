#pragma once

#include "mini_jass/l2_game.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace mini_jass::l2 {

enum class ExactValue : std::int8_t { Loss = -1, Draw = 0, Win = 1 };

struct OracleTransition {
    std::uint8_t action{};
    std::uint32_t child_id{};
    friend constexpr bool operator==(const OracleTransition&, const OracleTransition&) = default;
};

struct OracleState {
    State state;
    TerminalStatus terminal{TerminalStatus::Ongoing};
    ExactValue value{ExactValue::Draw};
    std::optional<std::uint16_t> dtw;
    std::vector<OracleTransition> transitions;
    std::vector<std::uint8_t> optimal_actions;
    std::uint32_t canonical_state_id{};
    bool canonical_transform{};
};

struct SolverManifest {
    std::uint64_t raw_state_count{};
    std::uint64_t raw_transition_count{};
    std::uint64_t canonical_state_count{};
    std::uint64_t canonical_transition_count{};
    std::uint64_t win_count{};
    std::uint64_t draw_count{};
    std::uint64_t loss_count{};
    std::uint16_t maximum_dtw{};
    ExactValue initial_value{ExactValue::Draw};
    std::optional<std::uint16_t> initial_dtw;
    std::uint64_t action_vocabulary_hash{};
    std::uint64_t raw_graph_hash{};
    std::uint64_t canonical_graph_hash{};
    std::uint64_t solver_hash{};
    std::uint64_t manifest_hash{};
    friend constexpr bool operator==(const SolverManifest&, const SolverManifest&) = default;
};

struct ExactOracle {
    std::vector<OracleState> states;
    SolverManifest manifest;
};

[[nodiscard]] ExactOracle solve_exact_oracle();
[[nodiscard]] std::string solver_manifest_json(const SolverManifest& manifest);
[[nodiscard]] std::string_view to_string(ExactValue value) noexcept;

}  // namespace mini_jass::l2
