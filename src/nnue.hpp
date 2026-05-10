// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Lightweight neural-network-style evaluation (a.k.a. NNUE-lite).
//
// Two concrete networks share a common `INetwork` interface so the
// search can hold a single `const INetwork*` regardless of which model
// was loaded:
//
//   * `LinearNetwork`  — 200 weights (50 squares × 4 piece kinds). The
//     output is a plain bitboard sum; the default constructor mirrors
//     the handcrafted material+PSQT evaluation.
//   * `MLPNetwork`     — small float32 multi-layer perceptron with the
//     topology 200 → 64 → 32 → 1 and ReLU activations. The default
//     constructor leaves all weights at zero (so the network outputs ~0
//     until `load()` is called).
//
// Real NNUE-style architectures use sparse incremental updates and
// quantised int8 weights. The MLP here is a clean reference
// implementation in float32 — easy to validate against PyTorch — that
// can be quantised later without changing the search-side API.

#pragma once

#include "position.hpp"
#include "types.hpp"

#include <array>
#include <cstdint>
#include <memory>
#include <string_view>

namespace jass {

// Common interface implemented by every NNUE-lite network. The search
// only needs `evaluate(pos)`; `load()` / `save()` belong to the concrete
// classes because their on-disk formats differ.
class INetwork {
public:
    virtual ~INetwork() = default;
    virtual int evaluate(const Position& pos) const noexcept = 0;
};

class LinearNetwork : public INetwork {
public:
    // Default-construct with weights mirroring the handcrafted eval
    // (material + PSQT + king centralisation).
    LinearNetwork();

    // Evaluate `pos` from the side-to-move's point of view (matching
    // the convention of the handcrafted `evaluate`).
    int evaluate(const Position& pos) const noexcept override;

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

// Float32 MLP with topology 200 → 64 → 32 → 1, ReLU activations on the
// two hidden layers, identity on the output. Input features are sparse
// one-hot indicators of (square × piece-kind) using the same ordering
// as `LinearNetwork`. The output is a centipawn-scale score from
// white's point of view; `evaluate(pos)` flips the sign for black-to-move
// so the result matches the engine's STM convention.
class MLPNetwork : public INetwork {
public:
    static constexpr std::size_t INPUT_DIM = 200;  // 50 squares × 4 kinds
    static constexpr std::size_t HIDDEN1   = 64;
    static constexpr std::size_t HIDDEN2   = 32;

    // Default-construct with zero weights and biases. The network
    // returns ~0 in that state; call `load()` to install a trained model.
    MLPNetwork() = default;

    int evaluate(const Position& pos) const noexcept override;

    // Binary format (little-endian throughout):
    //   [0..4)   magic = "JNNM"
    //   [4..8)   version (uint32, currently 1)
    //   [8..12)  input_dim  (uint32, must equal 200)
    //   [12..16) hidden1    (uint32, must equal 64)
    //   [16..20) hidden2    (uint32, must equal 32)
    //   [20..24) output_dim (uint32, must equal 1)
    //   [24..)   float32 weights in this order:
    //              w1 [HIDDEN1 × INPUT_DIM]   (row-major, neuron-major)
    //              b1 [HIDDEN1]
    //              w2 [HIDDEN2 × HIDDEN1]
    //              b2 [HIDDEN2]
    //              w3 [HIDDEN2]                (single output row)
    //              b3 [1]
    bool load(std::string_view path);
    bool save(std::string_view path) const;

private:
    // Row-major storage. `w1_[j * INPUT_DIM + i]` is the weight from
    // input feature `i` to layer-1 neuron `j`.
    std::array<float, HIDDEN1 * INPUT_DIM> w1_{};
    std::array<float, HIDDEN1>             b1_{};
    std::array<float, HIDDEN2 * HIDDEN1>   w2_{};
    std::array<float, HIDDEN2>             b2_{};
    std::array<float, HIDDEN2>             w3_{};  // single output row
    float                                  b3_{0.0f};
};

// Sniff `path`'s 4-byte header and return the matching concrete
// network. Files starting with "JNNM" load as `MLPNetwork`; anything
// else is tried as a raw-int32 `LinearNetwork`. Returns nullptr on I/O
// error or format mismatch.
std::unique_ptr<INetwork> load_network(std::string_view path);

// Switchable façade: `evaluate_nnue(pos)` mirrors `evaluate(pos)` but
// queries the internal default-constructed `LinearNetwork`. Useful as
// an A/B comparison harness for trained weights.
int evaluate_nnue(const Position& pos);

}  // namespace jass
