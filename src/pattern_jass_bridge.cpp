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
    : weights_(std::move(weights)), scale_(scale ? scale : 1U), skeleton_() {}

PatternJassNetwork::PatternJassNetwork(std::vector<std::int32_t> weights,
                                       std::uint32_t scale,
                                       std::unique_ptr<INetwork> skeleton)
    : weights_(std::move(weights)), scale_(scale ? scale : 1U),
      skeleton_(std::move(skeleton)) {}

int PatternJassNetwork::evaluate(const Position& pos) const noexcept {
    // Hybrid eval :
    //   eval_final = skeleton(pos) + pattern_correction(pos)
    // Where skeleton is either :
    //   - handcrafted (default, Option F, Scan-style §3)
    //   - NNUE (when constructed with --benchmark-pattern-jass-nnue-skel,
    //     Option I in docs/archives/PARADIGM_SHIFT_OPTIONS.md)
    const int skeleton_cp = skeleton_
        ? skeleton_->evaluate(pos)
        : ::jass::evaluate(pos);

    const std::uint64_t bm = static_cast<std::uint64_t>(pos.black_men());
    const std::uint64_t wm = static_cast<std::uint64_t>(pos.white_men());
    const std::int64_t sum_black =
        pattern_jass::eval_pattern(bm, wm, weights_.data());
    const std::int64_t cp_black = (sum_black * 100) / static_cast<std::int64_t>(scale_);
    const std::int64_t pattern_cp_stm =
        (pos.side_to_move() == Color::Black) ? cp_black : -cp_black;

    const std::int64_t total = static_cast<std::int64_t>(skeleton_cp) + pattern_cp_stm;
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

std::unique_ptr<PatternJassNetwork> load_pattern_jass_network_nnue_skel(
    const std::string& weights_path,
    const std::string& nnue_path,
    std::string* err) {
    auto loaded = pattern_jass::load_weights(weights_path, err);
    if (!loaded) return nullptr;
    auto skel = load_network(nnue_path);
    if (!skel) {
        if (err) *err = "cannot load NNUE skeleton from " + nnue_path;
        return nullptr;
    }
    return std::make_unique<PatternJassNetwork>(
        std::move(loaded->w), loaded->scale, std::move(skel));
}

}  // namespace jass
