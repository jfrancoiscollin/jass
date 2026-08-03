// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Deterministic node-budget policies for WDL self-play.  The sampler is a
// pure function of stable game coordinates: it never consumes any of the
// opening, sampling, exploration or role RNG streams.

#pragma once

#include <algorithm>
#include <charconv>
#include <cctype>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace jass::selfplay {

inline constexpr std::uint64_t NODE_BUDGET_MIN = 1'000;
inline constexpr std::uint32_t NODE_BUDGET_SAMPLER_VERSION = 1;

enum class NodeBudgetDistribution : std::uint8_t {
    Fixed,
    Weighted,
};

enum class SamplingGranularity : std::uint8_t {
    Move,
    Game,
};

struct WeightedNodeBudget {
    std::uint64_t nodes{0};
    std::uint64_t weight{0};
};

inline const char* node_budget_distribution_name(
    NodeBudgetDistribution distribution) noexcept {
    return distribution == NodeBudgetDistribution::Fixed ? "fixed" : "weighted";
}

inline const char* sampling_granularity_name(
    SamplingGranularity granularity) noexcept {
    return granularity == SamplingGranularity::Move ? "move" : "game";
}

inline std::uint64_t node_budget_mix(std::uint64_t value) noexcept {
    value = (value ^ (value >> 30)) * std::uint64_t{0xBF58476D1CE4E5B9};
    value = (value ^ (value >> 27)) * std::uint64_t{0x94D049BB133111EB};
    return value ^ (value >> 31);
}

inline std::uint64_t derive_node_budget_seed(
    std::uint64_t       global_seed,
    std::uint64_t       game_id,
    std::uint32_t       ply,
    std::uint8_t        side_to_move,
    SamplingGranularity granularity) noexcept {
    // Dedicated, versioned stream tag: changing Top-K or any other self-play
    // RNG cannot perturb this value.  Game sampling intentionally omits both
    // ply and side so every move in a game resolves to the same budget.
    constexpr std::uint64_t STREAM_TAG = std::uint64_t{0x4E4F44455F425544};
    std::uint64_t value = node_budget_mix(
        global_seed ^ STREAM_TAG ^ NODE_BUDGET_SAMPLER_VERSION);
    value = node_budget_mix(value ^ node_budget_mix(game_id));
    if (granularity == SamplingGranularity::Move) {
        const std::uint64_t move_coordinate =
            (static_cast<std::uint64_t>(ply) << 1)
            | static_cast<std::uint64_t>(side_to_move & 1u);
        value = node_budget_mix(value ^ node_budget_mix(move_coordinate));
    }
    return value;
}

class NodeBudgetPolicy {
public:
    static NodeBudgetPolicy fixed(std::uint64_t nodes,
                                  SamplingGranularity granularity) {
        validate_nodes(nodes);
        NodeBudgetPolicy policy;
        policy.distribution_ = NodeBudgetDistribution::Fixed;
        policy.granularity_ = granularity;
        policy.choices_.push_back({nodes, 1});
        policy.total_weight_ = 1;
        return policy;
    }

    static NodeBudgetPolicy weighted(std::vector<WeightedNodeBudget> choices,
                                     SamplingGranularity granularity) {
        if (choices.empty()) {
            throw std::invalid_argument(
                "weighted node-budget distribution must not be empty");
        }
        std::uint64_t total_weight = 0;
        for (const auto& choice : choices) {
            validate_nodes(choice.nodes);
            if (choice.weight == 0) {
                throw std::invalid_argument(
                    "weighted node-budget choices must have positive weights");
            }
            if (choice.weight
                > std::numeric_limits<std::uint64_t>::max() - total_weight) {
                throw std::invalid_argument(
                    "weighted node-budget total weight overflows uint64");
            }
            total_weight += choice.weight;
        }

        NodeBudgetPolicy policy;
        policy.distribution_ = NodeBudgetDistribution::Weighted;
        policy.granularity_ = granularity;
        policy.choices_ = std::move(choices);
        policy.total_weight_ = total_weight;
        return policy;
    }

    std::uint64_t sample(std::uint64_t global_seed,
                         std::uint64_t game_id,
                         std::uint32_t ply,
                         std::uint8_t side_to_move) const noexcept {
        if (distribution_ == NodeBudgetDistribution::Fixed) {
            return choices_.front().nodes;
        }
        const std::uint64_t draw = derive_node_budget_seed(
            global_seed, game_id, ply, side_to_move, granularity_)
            % total_weight_;
        std::uint64_t cumulative = 0;
        for (const auto& choice : choices_) {
            cumulative += choice.weight;
            if (draw < cumulative) return choice.nodes;
        }
        return choices_.back().nodes;  // defensive; validation makes this unreachable
    }

    NodeBudgetDistribution distribution() const noexcept {
        return distribution_;
    }
    SamplingGranularity granularity() const noexcept { return granularity_; }
    const std::vector<WeightedNodeBudget>& choices() const noexcept {
        return choices_;
    }
    std::uint64_t min_nodes() const noexcept {
        return std::min_element(
            choices_.begin(), choices_.end(),
            [](const auto& lhs, const auto& rhs) { return lhs.nodes < rhs.nodes; }
        )->nodes;
    }
    std::uint64_t max_nodes() const noexcept {
        return std::max_element(
            choices_.begin(), choices_.end(),
            [](const auto& lhs, const auto& rhs) { return lhs.nodes < rhs.nodes; }
        )->nodes;
    }

private:
    static void validate_nodes(std::uint64_t nodes) {
        if (nodes < NODE_BUDGET_MIN) {
            throw std::invalid_argument(
                "node budgets must be at least 1000 nodes");
        }
    }

    NodeBudgetDistribution          distribution_{NodeBudgetDistribution::Fixed};
    SamplingGranularity             granularity_{SamplingGranularity::Move};
    std::vector<WeightedNodeBudget> choices_;
    std::uint64_t                   total_weight_{0};
};

inline std::string_view trim_node_budget_token(std::string_view token) noexcept {
    while (!token.empty()
           && std::isspace(static_cast<unsigned char>(token.front()))) {
        token.remove_prefix(1);
    }
    while (!token.empty()
           && std::isspace(static_cast<unsigned char>(token.back()))) {
        token.remove_suffix(1);
    }
    return token;
}

inline std::uint64_t parse_node_budget_integer(std::string_view token,
                                                const char* field) {
    token = trim_node_budget_token(token);
    std::uint64_t value = 0;
    const auto parsed = std::from_chars(
        token.data(), token.data() + token.size(), value);
    if (token.empty() || parsed.ec != std::errc{}
        || parsed.ptr != token.data() + token.size()) {
        throw std::invalid_argument(
            std::string{"invalid node-budget "} + field + ": "
            + std::string{token});
    }
    return value;
}

// CLI representation: "5000:10,20000:25,80000:35".
inline std::vector<WeightedNodeBudget> parse_weighted_node_budgets(
    std::string_view spec) {
    std::vector<WeightedNodeBudget> choices;
    while (!spec.empty()) {
        const std::size_t comma = spec.find(',');
        std::string_view item = trim_node_budget_token(spec.substr(0, comma));
        if (item.empty()) {
            throw std::invalid_argument(
                "weighted node-budget distribution contains an empty choice");
        }
        const std::size_t colon = item.find(':');
        if (colon == std::string_view::npos
            || item.find(':', colon + 1) != std::string_view::npos) {
            throw std::invalid_argument(
                "weighted node-budget choices must use NODES:WEIGHT");
        }
        choices.push_back({
            parse_node_budget_integer(item.substr(0, colon), "nodes"),
            parse_node_budget_integer(item.substr(colon + 1), "weight"),
        });
        if (comma == std::string_view::npos) break;
        if (comma + 1 == spec.size()) {
            throw std::invalid_argument(
                "weighted node-budget distribution contains an empty choice");
        }
        spec.remove_prefix(comma + 1);
    }
    if (choices.empty()) {
        throw std::invalid_argument(
            "weighted node-budget distribution must not be empty");
    }
    return choices;
}

}  // namespace jass::selfplay
