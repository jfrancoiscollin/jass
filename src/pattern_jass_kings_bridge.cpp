// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern_jass_kings_bridge.hpp"

#include "position.hpp"

#include "../pattern_jass_kings/src/weights.hpp"

namespace jass {

PatternJassKingsNetwork::PatternJassKingsNetwork(
    std::vector<std::int32_t> weights, std::uint32_t scale)
    : weights_(std::move(weights)), scale_(scale ? scale : 1U) {}

int PatternJassKingsNetwork::evaluate(const Position& pos) const noexcept {
    const std::uint64_t bm = static_cast<std::uint64_t>(pos.black_men());
    const std::uint64_t bk = static_cast<std::uint64_t>(pos.black_kings());
    const std::uint64_t wm = static_cast<std::uint64_t>(pos.white_men());
    const std::uint64_t wk = static_cast<std::uint64_t>(pos.white_kings());

    const std::int64_t sum_black =
        pattern_jass_kings::eval_pattern(bm, bk, wm, wk, weights_.data());

    const std::int64_t cp_black = (sum_black * 100) / static_cast<std::int64_t>(scale_);
    const std::int64_t cp_stm =
        (pos.side_to_move() == Color::Black) ? cp_black : -cp_black;
    if (cp_stm >  20000) return  20000;
    if (cp_stm < -20000) return -20000;
    return static_cast<int>(cp_stm);
}

std::unique_ptr<PatternJassKingsNetwork> load_pattern_jass_kings_network(
    const std::string& path, std::string* err) {
    auto loaded = pattern_jass_kings::load_weights(path, err);
    if (!loaded) return nullptr;
    return std::make_unique<PatternJassKingsNetwork>(
        std::move(loaded->w), loaded->scale);
}

}  // namespace jass
