// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Bridge for pattern_jass_kings (Variant C) → jass core.
// Same scheme as pattern_jass_bridge but uses the 5-state eval that
// includes kings.

#pragma once

#include "nnue.hpp"

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace jass {

class PatternJassKingsNetwork : public INetwork {
public:
    PatternJassKingsNetwork(std::vector<std::int32_t> weights,
                            std::uint32_t scale);

    int evaluate(const Position& pos) const noexcept override;

    std::uint32_t scale() const noexcept { return scale_; }
    std::size_t   count() const noexcept { return weights_.size(); }

private:
    std::vector<std::int32_t> weights_;
    std::uint32_t             scale_;
};

std::unique_ptr<PatternJassKingsNetwork> load_pattern_jass_kings_network(
    const std::string& path, std::string* err = nullptr);

}  // namespace jass
