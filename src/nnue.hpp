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
#include <vector>

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

    // In-memory variant of `load`: read `n` bytes (must equal the
    // weights footprint) from `data`. Used by `default_nnue()` when
    // the binary-embedded default network is a raw LinearNetwork file.
    bool load_from_bytes(const unsigned char* data, std::size_t n);

private:
    // weights_[square-bit 0..49][piece-kind 0..3], where the piece
    // ordering is: 0 = white man, 1 = white king, 2 = black man,
    // 3 = black king.
    std::array<std::array<std::int32_t, 4>, NUM_SQUARES> weights_{};
};

// Float32 MLP with topology INPUT_DIM → hidden1 → hidden2 → 1, ReLU
// activations on the two hidden layers, identity on the output. Input
// features are sparse one-hot indicators in STM-POV encoding (see the
// file header in src/nnue.cpp for the exact convention). The output
// is a centipawn-scale score from the side-to-move's perspective —
// no final sign flip is needed.
//
// The two hidden dimensions are runtime parameters (resolved at
// load() / construction time), so the same class can host the legacy
// 64-32 default network as well as the wider 128-64 / 256-128 /
// 512-256 candidates explored by the Cycle-2 trainer.
//
// History: a wider archi (128/64) was tried in PR #8 and lost at depth
// 5 by score rate 0.444 vs the linear baseline on 90 games — likely
// over-parameterised for 100k records of noisy depth-8 targets. We
// reverted to 64/32 there because the v2 weights at that size won the
// championship at 0.639 vs linear. With the WDL-labeled 1M dataset
// the trade-off is being re-evaluated and the class no longer hard-
// codes the choice.
class MLPNetwork : public INetwork {
public:
    static constexpr std::size_t INPUT_DIM = 200;  // 50 squares × 4 kinds

    // Default hidden dimensions — these are what the embedded weights
    // file ships with and what a default-constructed instance allocates.
    // They are kept as constants so older callers (and a few tests)
    // that size their buffers around the v2 archi keep working.
    static constexpr std::size_t HIDDEN1 = 64;
    static constexpr std::size_t HIDDEN2 = 32;

    // Upper bound used by `evaluate()` to allocate hidden-layer scratch
    // on the stack. Any arch trained by the Cycle-2 trainer stays well
    // below this; raise it if you ever load a wider model.
    static constexpr std::size_t MAX_HIDDEN = 1024;

    // Default-construct with the legacy 64-32 dims and zero weights.
    // The network returns ~0 in that state; call `load()` to install
    // a trained model (which may have different hidden dims).
    MLPNetwork();

    // Explicit-dims constructor. Allocates zero-initialised storage
    // for the requested topology.
    MLPNetwork(std::size_t hidden1, std::size_t hidden2);

    std::size_t hidden1() const noexcept { return hidden1_; }
    std::size_t hidden2() const noexcept { return hidden2_; }

    int evaluate(const Position& pos) const noexcept override;

    // Binary format (little-endian throughout):
    //   [0..4)   magic = "JNNM"
    //   [4..8)   version (uint32, currently 2)
    //   [8..12)  input_dim  (uint32, must equal 200)
    //   [12..16) hidden1    (uint32)
    //   [16..20) hidden2    (uint32)
    //   [20..24) output_dim (uint32, must equal 1)
    //   [24..)   float32 weights in this order:
    //              w1 [hidden1 × INPUT_DIM]   (row-major, neuron-major)
    //              b1 [hidden1]
    //              w2 [hidden2 × hidden1]
    //              b2 [hidden2]
    //              w3 [hidden2]                (single output row)
    //              b3 [1]
    bool load(std::string_view path);
    bool save(std::string_view path) const;

    // In-memory variant of `load`. The byte buffer must start with the
    // JNNM magic; the hidden dims are read from the header and the
    // storage is reshaped accordingly. On failure the network state
    // is left unchanged and false is returned.
    bool load_from_bytes(const unsigned char* data, std::size_t n);

private:
    void resize_for(std::size_t h1, std::size_t h2);

    std::size_t        hidden1_{HIDDEN1};
    std::size_t        hidden2_{HIDDEN2};

    // Row-major storage. `w1_[j * INPUT_DIM + i]` is the weight from
    // input feature `i` to layer-1 neuron `j`.
    std::vector<float> w1_;   // hidden1_ × INPUT_DIM
    std::vector<float> b1_;   // hidden1_
    std::vector<float> w2_;   // hidden2_ × hidden1_
    std::vector<float> b2_;   // hidden2_
    std::vector<float> w3_;   // hidden2_ (single output row)
    float              b3_{0.0f};
};

// Quantised int8 counterpart of `MLPNetwork`. Same topology and STM-
// relative encoding, but weights are int8 and biases are int32 (at
// the accumulator scale). Two hot loops do int8 × int8 → int32 MAC,
// with three precomputed float scales bridging the layers. Forward
// pass is roughly 3× faster than `MLPNetwork` on a modern x86 CPU,
// at the cost of ~5-15 ELO of precision loss (small compared to the
// gain from quantisation-enabled deeper search).
//
// As of Cycle 4a the hidden dims are runtime parameters; the AVX2 /
// WASM SIMD dot-product helpers require their inner length to be a
// multiple of 32 (16 on WASM), so `load()` rejects any topology that
// would break them. The Cycle-2 trainer only produces multiples of
// 32 today (64-32, 128-64, 256-128, 512-256), so the constraint is
// not user-visible.
//
// On-disk format (JNNQ, version 1) is described next to the load /
// save declarations.
class MLPNetworkQ : public INetwork {
public:
    static constexpr std::size_t INPUT_DIM  = 200;
    static constexpr std::size_t HIDDEN1    = 64;
    static constexpr std::size_t HIDDEN2    = 32;
    static constexpr std::size_t MAX_HIDDEN = 1024;
    static constexpr std::size_t SIMD_TILE  = 32;

    MLPNetworkQ();
    MLPNetworkQ(std::size_t hidden1, std::size_t hidden2);

    std::size_t hidden1() const noexcept { return hidden1_; }
    std::size_t hidden2() const noexcept { return hidden2_; }

    int evaluate(const Position& pos) const noexcept override;

    // Binary format (little-endian throughout):
    //   [0..4)   magic = "JNNQ"
    //   [4..8)   version (uint32, currently 1)
    //   [8..12)  input_dim  (uint32, must equal 200)
    //   [12..16) hidden1    (uint32, multiple of SIMD_TILE)
    //   [16..20) hidden2    (uint32, multiple of SIMD_TILE)
    //   [20..24) output_dim (uint32, must equal 1)
    //   [24..28) float32 mul1     (acc1 → int8 h1 quantisation factor)
    //   [28..32) float32 mul2     (acc2 → int8 h2 quantisation factor)
    //   [32..36) float32 mul_out  (acc3 → centipawn scale)
    //   [36..)   weights:
    //              w1 [hidden1 × INPUT_DIM]   int8
    //              b1 [hidden1]               int32 (at acc1 scale)
    //              w2 [hidden2 × hidden1]     int8
    //              b2 [hidden2]               int32 (at acc2 scale)
    //              w3 [hidden2]               int8
    //              b3 [1]                     int32 (at acc3 scale)
    bool load(std::string_view path);
    bool save(std::string_view path) const;
    bool load_from_bytes(const unsigned char* data, std::size_t n);

private:
    void resize_for(std::size_t h1, std::size_t h2);

    std::size_t                hidden1_{HIDDEN1};
    std::size_t                hidden2_{HIDDEN2};
    std::vector<std::int8_t>   w1_;   // hidden1_ × INPUT_DIM
    std::vector<std::int32_t>  b1_;   // hidden1_
    std::vector<std::int8_t>   w2_;   // hidden2_ × hidden1_
    std::vector<std::int32_t>  b2_;   // hidden2_
    std::vector<std::int8_t>   w3_;   // hidden2_
    std::int32_t               b3_{0};
    float                      mul1_{1.0f};
    float                      mul2_{1.0f};
    float                      mul_out_{1.0f};
};

// Sniff `path`'s 4-byte header and return the matching concrete
// network. Files starting with "JNNM" load as `MLPNetwork`, "JNNQ"
// as `MLPNetworkQ`; anything else is tried as a raw-int32
// `LinearNetwork`. Returns nullptr on I/O error or format mismatch.
std::unique_ptr<INetwork> load_network(std::string_view path);

// In-memory variant of `load_network`: same magic-based dispatch but
// reading from a byte buffer rather than the filesystem. Used by
// `default_nnue()` to instantiate the right concrete class from the
// embedded weights regardless of whether they describe a Linear or
// an MLP network.
std::unique_ptr<INetwork> load_network_from_bytes(const unsigned char* data,
                                                  std::size_t          n);

// Returns a pointer to the lazily-initialised network loaded from the
// embedded default weights (CMake compiles `nnue.bin` from the repo
// root into the binary). Today that file ships the v2 MLP weights
// (200 → 64 → 32 → 1, STM-relative encoding, score rate 0.639 vs the
// linear baseline at depth 5), but the return type is the abstract
// `INetwork*` so the embedded model can be swapped without touching
// callers. The pointer is owned by static storage and remains valid
// for the lifetime of the process; callers that want to opt out of
// NNUE entirely should pass `nullptr` to the relevant `set_nnue(...)`.
const INetwork* default_nnue();

// Switchable façade: `evaluate_nnue(pos)` mirrors `evaluate(pos)` but
// queries the internal default-constructed `LinearNetwork`. Useful as
// an A/B comparison harness for trained weights.
int evaluate_nnue(const Position& pos);

}  // namespace jass
