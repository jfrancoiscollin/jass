// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern_jass_bridge.hpp"

#include "eval.hpp"
#include "position.hpp"

// Use the standalone pattern_jass module via relative include. The
// .cpp files are compiled directly into jass_lib (cf CMakeLists.txt).
#include "../pattern_jass/src/weights.hpp"

namespace jass {

PatternJassNetwork::PatternJassNetwork(std::vector<std::int32_t> weights,
                                       std::uint32_t scale)
    : weights_(std::move(weights)), scale_(scale ? scale : 1U) {}

int PatternJassNetwork::evaluate(const Position& pos) const noexcept {
    // Scan-style hybrid eval :
    //   eval_final = handcrafted(pos) + pattern_correction(pos)
    // The pattern weights were trained on the RESIDUAL between true
    // (NNUE-rewritten) score and handcrafted, so adding handcrafted
    // back at eval time reconstructs the model's full prediction.
    // Cf docs/SCAN_ARCHITECTURE_NOTES.md §3 : "Les patterns ne
    // remplacent pas l'éval, ils s'ajoutent à un squelette".
    const int handcrafted_cp = ::jass::evaluate(pos);

    const std::uint64_t bm = static_cast<std::uint64_t>(pos.black_men());
    const std::uint64_t wm = static_cast<std::uint64_t>(pos.white_men());
    const std::int64_t sum_black =
        pattern_jass::eval_pattern(bm, wm, weights_.data());
    const std::int64_t cp_black = (sum_black * 100) / static_cast<std::int64_t>(scale_);
    const std::int64_t pattern_cp_stm =
        (pos.side_to_move() == Color::Black) ? cp_black : -cp_black;

    const std::int64_t total = static_cast<std::int64_t>(handcrafted_cp) + pattern_cp_stm;
    if (total >  20000) return  20000;
    if (total < -20000) return -20000;
    return static_cast<int>(total);
}

std::unique_ptr<PatternJassNetwork> load_pattern_jass_network(
    const std::string& path, std::string* err) {
    auto loaded = pattern_jass::load_weights(path, err);
    if (!loaded) return nullptr;
    return std::make_unique<PatternJassNetwork>(std::move(loaded->w), loaded->scale);
}

}  // namespace jass
