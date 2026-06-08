// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Full Scan-style structured evaluation for jass (PJTW v3).
//
// This is the "tout comme Scan" eval : a single linear function of
//
//     material (men + king counts)
//   + king PST   (one-hot per square, per colour)
//   + mobility   (men step + king slide, per colour)
//   + balance    (left/right men distribution, per colour)
//   + men patterns (8 vertical bands × 12 squares, ternary — pattern_jass)
//
// with EVERY feature stored in TWO weight banks (midgame / endgame) and
// interpolated by the game stage (piece count / 40), exactly like Scan
// (cf docs/SCAN_ARCHITECTURE_NOTES.md §3, docs/PATTERN_PROGRAM_NOTES.md §A).
//
// Consistency contract :
//   * `compute_extras()` is the SINGLE source of truth for the dense
//     "extras" feature vector. It is called both by the training-time
//     feature dump (`jass --dump-eval-features`) and by the playable
//     `ScanEvalNetwork::evaluate()`. There is no second implementation in
//     Python — the trainer consumes the dumped extras verbatim. Mobility
//     therefore uses fast bitboard shifts (no movegen) and is identical on
//     both sides by construction.
//   * The 8 men-pattern bucket indices are computed by pattern_jass on both
//     sides (base-3, men only) — already mirrored in pattern_jass/tools.
//
// Score convention (matches pattern_jass_bridge) : the eval is accumulated
// in BLACK POV (positive = good for Black), divided by `scale`, multiplied
// by 100 → centipawn-like units, then sign-flipped to stm-POV.

#pragma once

#include "nnue.hpp"
#include "position.hpp"

#include "../pattern_jass/src/pattern.hpp"

#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace jass::scan_eval {

// ---------------------------------------------------------------------------
// Dense "extras" feature layout (black-POV indicators / counts).
// ---------------------------------------------------------------------------
// Kept in a fixed, stable order so the trainer and the C++ eval agree. The
// men patterns (pattern_jass) are appended separately as sparse one-hots.
inline constexpr int EXTRA_BK_PST_BASE  = 0;    // [0..49]   black king on FMJD (i+1)
inline constexpr int EXTRA_WK_PST_BASE  = 50;   // [50..99]  white king on FMJD (i+1)
inline constexpr int EXTRA_BLACK_MEN    = 100;  // black men count
inline constexpr int EXTRA_WHITE_MEN    = 101;  // white men count
inline constexpr int EXTRA_BLACK_MOB    = 102;  // black mobility (men step + king slide)
inline constexpr int EXTRA_WHITE_MOB    = 103;  // white mobility
inline constexpr int EXTRA_BLACK_BAL    = 104;  // black men left − right
inline constexpr int EXTRA_WHITE_BAL    = 105;  // white men left − right
// 1st batch of structural extras (king-mob/back-rank/advancement, 106->112)
// was RE-TESTED on the clean (score-drop) baseline in 0172 and CONDEMNED:
// v4+112 = 0.889/0.389 vs the v4+106 champion 0.944/0.389 (hurts vs hc,
// neutral vs v15). Reverted to 106. To re-test, re-add here + NUM_EXTRAS.
inline constexpr int NUM_EXTRAS         = 106;

// Game-stage normaliser : 20 men/side at the FMJD start = 40 pieces.
inline constexpr int MAX_PIECES = 40;

// Fast bitboard mobility (no movegen) : number of quiet destinations for
// `c`'s men (one forward step) plus king slides (until first blocker).
// Used identically by the feature dump and by evaluate().
int mobility(const Position& pos, Color c) noexcept;

// Fill `out` with the NUM_EXTRAS dense features in black-POV. Position-only
// (independent of side to move), so a single row is dumped per position.
void compute_extras(const Position& pos,
                    std::array<float, NUM_EXTRAS>& out) noexcept;

// Game stage = min(total pieces, 40). wmg = stage/40, weg = 1 − wmg.
int game_stage(const Position& pos) noexcept;

// ---------------------------------------------------------------------------
// PJTW v3 weights : full phase-split structured eval.
// ---------------------------------------------------------------------------
// File layout (little-endian) :
//   uint32 magic   = 0x57544A50  ("PJTW")
//   uint32 version = 3
//   uint32 scale   = quantisation factor (piece-units × scale)
//   uint32 n_pat   = pattern bucket count (= pattern_jass::TOTAL_BUCKETS)
//   uint32 n_ext   = extras count (= NUM_EXTRAS)
//   int32  w[2 * (n_pat + n_ext)]  ordered [pat_mg | pat_eg | ext_mg | ext_eg]
inline constexpr std::uint32_t V3_MAGIC   = 0x57544A50U;  // "PJTW"
inline constexpr std::uint32_t V3_VERSION = 3U;
inline constexpr std::size_t   V3_HEADER  = 20;

struct ScanWeights {
    std::uint32_t scale = 1000;
    std::vector<std::int32_t> pat_mg;   // size n_pat
    std::vector<std::int32_t> pat_eg;   // size n_pat
    std::array<std::int32_t, NUM_EXTRAS> ext_mg{};
    std::array<std::int32_t, NUM_EXTRAS> ext_eg{};
};

std::optional<ScanWeights> load_scan_weights(const std::string& path,
                                             std::string* err = nullptr);

class ScanEvalNetwork : public INetwork {
public:
    explicit ScanEvalNetwork(ScanWeights w) : w_(std::move(w)) {}
    int evaluate(const Position& pos) const noexcept override;

    // Accumulator fast path : same eval as evaluate(pos) but with the 32
    // pattern base-3 indices supplied precomputed (the search maintains them
    // incrementally via ScanAccumulator), skipping extract_all. `idx` must
    // point to NUM_PATTERNS entries equal to extract_all(pos's men).
    int evaluate_with_idx(const Position& pos,
                          const std::uint32_t* idx) const noexcept;

    std::uint32_t scale() const noexcept { return w_.scale; }
    std::size_t   count() const noexcept {
        return 2 * (w_.pat_mg.size() + NUM_EXTRAS);
    }

private:
    ScanWeights w_;
};

std::unique_ptr<ScanEvalNetwork> load_scan_eval_network(
    const std::string& path, std::string* err = nullptr);

// Per-ply pattern accumulator for the search. Holds the 32 base-3 pattern
// indices; `refresh_from` rebuilds them from scratch (root / fallback) and
// `apply_move` updates them incrementally for a played move. Kings are not in
// patterns, so only the men bitboards matter. One accumulator per ply (the
// index does not depend on side-to-move; evaluate_with_idx applies the sign).
struct ScanAccumulator {
    std::array<std::uint32_t, pattern_jass::NUM_PATTERNS> idx{};

    void refresh_from(const Position& pos) noexcept {
        pattern_jass::extract_all(static_cast<std::uint64_t>(pos.black_men()),
                                  static_cast<std::uint64_t>(pos.white_men()),
                                  idx);
    }
    void apply_move(const Position& before, const Position& after) noexcept {
        pattern_jass::update_all(static_cast<std::uint64_t>(before.black_men()),
                                 static_cast<std::uint64_t>(before.white_men()),
                                 static_cast<std::uint64_t>(after.black_men()),
                                 static_cast<std::uint64_t>(after.white_men()),
                                 idx);
    }
};

}  // namespace jass::scan_eval

namespace jass {

// Unified eval loader : peeks the PJTW version and returns the right
// INetwork — v3 → ScanEvalNetwork, v1/v2 → PatternJassNetwork. Lets the
// HUB `--pattern` flag, SPSA and benches accept either format transparently.
std::unique_ptr<INetwork> load_eval_network(const std::string& path,
                                            std::string* err = nullptr);

}  // namespace jass
