// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Optional leader-relative conversion expert layered on top of an existing
// INetwork. The base evaluator remains untouched; a sibling `<weights>.cvh`
// sidecar activates the expert. Absence of the sidecar is exactly the legacy
// loading path.
#pragma once

#include "nnue.hpp"
#include "position.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>

namespace jass::conversion_head {

inline constexpr std::uint32_t MAGIC = 0x31485643U;  // "CVH1" little-endian
inline constexpr std::uint32_t SCHEMA = 1U;
inline constexpr std::size_t NUM_FEATURES = 16;
inline constexpr std::size_t BINARY_SIZE =
    4U * sizeof(std::uint32_t) +
    9U * sizeof(float) +
    3U * NUM_FEATURES * sizeof(float);

enum Feature : std::size_t {
    TOTAL_PIECES = 0,
    LEADER_MEN,
    LEADER_KINGS,
    DEFENDER_MEN,
    DEFENDER_KINGS,
    LEADER_MOBILITY,
    DEFENDER_MOBILITY,
    MOBILITY_DIFF,
    LEADER_KING_CENTRALITY,
    DEFENDER_KING_CENTRALITY,
    LEADER_MEN_ADVANCEMENT,
    DEFENDER_MEN_ADVANCEMENT,
    LEADER_NEAR_PROMOTION,
    DEFENDER_NEAR_PROMOTION,
    LEADER_LR_IMBALANCE,
    DEFENDER_LR_IMBALANCE,
};

struct Model {
    std::uint32_t flags = 0;
    float lambda_cp = 0.0F;
    float tanh_scale = 1.0F;
    float center_logit = 0.0F;
    float piece_min = 8.0F;
    float piece_full_max = 12.0F;
    float piece_zero_max = 20.0F;
    float margin_min = 1.0F;
    float margin_max = 1.0F;
    float bias = 0.0F;
    std::array<float, NUM_FEATURES> mean{};
    std::array<float, NUM_FEATURES> inv_std{};
    std::array<float, NUM_FEATURES> weight{};
};

struct Features {
    std::array<float, NUM_FEATURES> value{};
    int leader_sign_black = 0;  // +1 black leader, -1 white leader, 0 no leader
    int material_margin = 0;    // man=1, king=3
    int total_pieces = 0;
};

float gate_for(int total_pieces, int material_margin,
               const Model& model) noexcept;
Features compute_features(const Position& pos) noexcept;
double delta_cp_black(const Position& pos, const Model& model) noexcept;

std::optional<Model> load_model(const std::string& path,
                                std::string* err = nullptr);

class Network final : public INetwork {
public:
    Network(std::unique_ptr<INetwork> base, Model model)
        : base_(std::move(base)), model_(std::move(model)) {}

    int evaluate(const Position& pos) const noexcept override;
    bool valid() const noexcept { return base_ != nullptr; }

private:
    std::unique_ptr<INetwork> base_;
    Model model_;
};

// If `<pattern_path>.cvh` does not exist, return `base` unchanged. If it exists,
// load it fail-closed and return a conversion-head wrapper.
std::unique_ptr<INetwork> maybe_wrap(std::unique_ptr<INetwork> base,
                                    const std::string& pattern_path,
                                    std::string* err = nullptr);

}  // namespace jass::conversion_head
