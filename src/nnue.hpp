// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Lightweight neural-network-style evaluation (a.k.a. NNUE-lite).
//
// This translation unit ships the *framework* — a per-piece per-square
// weight table evaluated by simple bitboard sums — plus a binary
// loader so a future training pipeline can drop trained weights in
// without changing the rest of the engine. The default-constructed
// network reproduces the handcrafted material+PSQT evaluation so
// callers can switch to it in tests without observing behaviour
// changes; replacing the weights is what unlocks any strength gain.
//
// Real NNUE-style architectures use sparse incremental updates and
// hidden layers with clipped-ReLU activations. Both are deferred:
// they require an offline training pipeline that is out of scope here.

#pragma once

#include "position.hpp"
#include "types.hpp"

#include <array>
#include <cstdint>
#include <string_view>

namespace jass {

class LinearNetwork {
public:
    // Default-construct with weights mirroring the handcrafted eval
    // (material + PSQT + king centralisation).
    LinearNetwork();

    // Evaluate `pos` from the side-to-move's point of view (matching
    // the convention of the handcrafted `evaluate`).
    int evaluate(const Position& pos) const noexcept;

    // Replace the weights with values read from a small binary file.
    // The format is the raw little-endian int32 contents of `weights_`
    // (200 values, in the order [square 0..49][kind 0..3]). Returns
    // false on I/O error or wrong file size; the network state is left
    // unchanged in that case.
    bool load(std::string_view path);

    // Save the current weights to disk in the same format `load`
    // expects. Useful for snapshotting a hand-tuned network.
    bool save(std::string_view path) const;

private:
    // weights_[square-bit 0..49][piece-kind 0..3], where the piece
    // ordering is: 0 = white man, 1 = white king, 2 = black man,
    // 3 = black king.
    std::array<std::array<std::int32_t, 4>, NUM_SQUARES> weights_{};
};

// Switchable façade: `evaluate_nnue(pos)` mirrors `evaluate(pos)` but
// queries the internal default-constructed `LinearNetwork`. Useful as
// an A/B comparison harness for trained weights.
int evaluate_nnue(const Position& pos);

}  // namespace jass
