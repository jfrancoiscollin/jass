// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Option H — NNUE hybride avec squelette handcrafted.
//
//   eval_final(pos) = handcrafted(pos) + inner_nnue(pos)
//
// The inner network is trained on the RESIDUAL (label - handcrafted), so
// adding the handcrafted skeleton back at eval time reconstructs the full
// prediction. The skeleton carries material + PSQT (cheap, already correct)
// and the NNUE only has to learn the positional correction — a strictly
// easier target at identical capacity. Cf docs/archives/PARADIGM_SHIFT_OPTIONS.md §H.
//
// Both `jass::evaluate` (handcrafted) and `INetwork::evaluate` return the
// score from the side-to-move point of view, so the sum is consistent.
#pragma once

#include <memory>
#include <string_view>
#include <utility>

#include "eval.hpp"
#include "nnue.hpp"
#include "position.hpp"

namespace jass {

class HybridHandcraftedNetwork : public INetwork {
public:
    explicit HybridHandcraftedNetwork(std::unique_ptr<INetwork> inner)
        : inner_(std::move(inner)) {}

    int evaluate(const Position& pos) const noexcept override {
        const long total = static_cast<long>(::jass::evaluate(pos))
                         + static_cast<long>(inner_->evaluate(pos));
        if (total >  20000) return  20000;
        if (total < -20000) return -20000;
        return static_cast<int>(total);
    }

    bool valid() const noexcept { return inner_ != nullptr; }

private:
    std::unique_ptr<INetwork> inner_;
};

// Load an NNUE residual network from `path` and wrap it with the
// handcrafted skeleton (Option H). Returns nullptr if the inner network
// cannot be loaded.
inline std::unique_ptr<HybridHandcraftedNetwork>
load_hybrid_handcrafted_network(std::string_view path) {
    auto inner = load_network(path);
    if (!inner) return nullptr;
    return std::make_unique<HybridHandcraftedNetwork>(std::move(inner));
}

}  // namespace jass
