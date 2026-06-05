// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern_jass_bridge.hpp"

#include "position.hpp"

// Use the standalone pattern_jass module via relative include. The
// .cpp files are compiled directly into jass_lib (cf CMakeLists.txt).
#include "../pattern_jass/src/weights.hpp"

namespace jass {

PatternJassNetwork::PatternJassNetwork(std::vector<std::int32_t> weights,
                                       std::uint32_t scale)
    : weights_(std::move(weights)), scale_(scale ? scale : 1U) {}

int PatternJassNetwork::evaluate(const Position& pos) const noexcept {
    // pattern_jass uses men only (kings excluded) by design.
    // Black-POV pattern sum, then sign-flip for stm-POV.
    const std::uint64_t bm = static_cast<std::uint64_t>(pos.black_men());
    const std::uint64_t wm = static_cast<std::uint64_t>(pos.white_men());

    const std::int64_t sum_black =
        pattern_jass::eval_pattern(bm, wm, weights_.data());

    // Convert to stm-POV centipawn :
    //   sum_black is in "scale * piece" units predicting WDL.
    //   cp_black = sum_black * 100 / scale.
    const std::int64_t cp_black = (sum_black * 100) / static_cast<std::int64_t>(scale_);
    const std::int64_t cp_stm   =
        (pos.side_to_move() == Color::Black) ? cp_black : -cp_black;
    // Clamp to int range — pattern eval shouldn't be enormous but be safe.
    if (cp_stm >  20000) return  20000;
    if (cp_stm < -20000) return -20000;
    return static_cast<int>(cp_stm);
}

std::unique_ptr<PatternJassNetwork> load_pattern_jass_network(
    const std::string& path, std::string* err) {
    auto loaded = pattern_jass::load_weights(path, err);
    if (!loaded) return nullptr;
    return std::make_unique<PatternJassNetwork>(std::move(loaded->w), loaded->scale);
}

}  // namespace jass
