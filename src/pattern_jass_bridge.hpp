// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Bridge between pattern_jass (Phase Pattern-2 POC) and the jass core
// search infrastructure.
//
// Wraps a loaded `pattern_jass::Weights` as an `INetwork` so that any
// search/bench path that takes a `const INetwork*` (e.g. `--benchmark-nnue`,
// `run_tournament`) can transparently use the pattern eval instead of
// an NNUE forward pass.
//
// Score convention :
//   pattern_jass::eval_pattern returns int64 in black-POV scaled units.
//   We sign-flip to stm-POV and rescale to centipawn-like units :
//     score_cp = int(pattern_sum * 100 / weights.scale) [stm-POV]
//   With scale=1000 (PJTW default), a +1.0 WDL prediction → +100 cp.

#pragma once

#include "nnue.hpp"

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace jass {

class PatternJassNetwork : public INetwork {
public:
    // Build with handcrafted skeleton (default — Scan-style §3 hybrid).
    PatternJassNetwork(std::vector<std::int32_t> weights, std::uint32_t scale);

    // Build with an NNUE skeleton instead of handcrafted. The pattern
    // weights then learn the residual on top of the NNUE prediction
    // (Option I — pattern hybride sur NNUE, cf
    // docs/archives/PARADIGM_SHIFT_OPTIONS.md). The bridge owns `skeleton`.
    PatternJassNetwork(std::vector<std::int32_t> weights, std::uint32_t scale,
                       std::unique_ptr<INetwork> skeleton);

    int evaluate(const Position& pos) const noexcept override;

    std::uint32_t scale() const noexcept { return scale_; }
    std::size_t   count() const noexcept { return weights_.size(); }
    bool          has_nnue_skeleton() const noexcept { return skeleton_ != nullptr; }

private:
    std::vector<std::int32_t> weights_;
    std::uint32_t             scale_;
    std::unique_ptr<INetwork> skeleton_;  // nullptr → handcrafted skeleton
};

// Load weights from a PJTW file and return the wrapped network with
// handcrafted skeleton (default). Returns nullptr and sets `err` on failure.
std::unique_ptr<PatternJassNetwork> load_pattern_jass_network(
    const std::string& path, std::string* err = nullptr);

// Same but with an NNUE skeleton (loaded from `nnue_path` via
// `load_network`). Used by --benchmark-pattern-jass-nnue-skel.
std::unique_ptr<PatternJassNetwork> load_pattern_jass_network_nnue_skel(
    const std::string& weights_path,
    const std::string& nnue_path,
    std::string* err = nullptr);

}  // namespace jass
