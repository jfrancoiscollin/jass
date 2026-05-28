// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Pattern-based NNUE alternative inspired by Scan/Kingsrow.
//
// MOTIVATION
// ----------
// The current MLPNetworkQ (dense MLP, HalfMen 450 → 256 → 128 → 1)
// plateaus at -812 ELO vs Scan. Literature on 10×10 draughts engines
// (Scan, Kingsrow, Maximus) consistently shows that **pattern-based
// evaluation outperforms dense MLPs at the high end** — locality of
// patterns + per-bucket weights captures positional features the dense
// network's global hidden layers cannot. This file implements a
// first-principles pattern eval to test that hypothesis.
//
// DESIGN
// ------
// A `PatternNetwork` is parameterised by a fixed pattern set: an array
// of patterns, each pattern being a list of K board squares (FMJD
// numbering, 1..50). For each pattern, weight table of size 5^K (one
// int32 per board state of the pattern's K squares, where each square
// has 5 possible values: empty, W-man, W-king, B-man, B-king).
//
// `evaluate(pos)` builds, per pattern, the base-5 index of the pattern's
// squares' current states, looks up the corresponding weight, sums
// across all patterns + bias, then sign-flips for STM-POV.
//
// V1 PATTERN SET (8 patterns × 4 squares each = 8 × 625 = 5000 weights)
// is intentionally minimal — proves the pipeline end-to-end, easy to
// train and validate. Scaled-up Scan-class set (16 patterns × 8 squares
// = 16 × 390 625 = 6.25 M weights) is a v2 extension.
//
// ON-DISK FORMAT (JPAT, little-endian)
// ------------------------------------
//
// Version 1 (legacy, pure-pattern):
//   [0..4)   magic        = "JPAT"
//   [4..8)   uint32 version = 1
//   [8..12)  uint32 num_patterns
//   [12..16) int32  bias
//   For each pattern (in order):
//     uint8  num_squares (K)
//     uint8[K] squares (FMJD numbering 1..50)
//     int32[5^K] weights (row-major over the base-5 state index)
//
// Version 2 (D1 hybrid, pattern + material/king skeleton — cf.
// docs/SCAN_ARCHITECTURE_NOTES.md §6):
//   [0..4)   magic         = "JPAT"
//   [4..8)   uint32 version = 2
//   [8..12)  uint32 num_patterns
//   [12..16) int32  bias
//   [16..20) int32  man_value  (centipawns per (Wmen  - Bmen)  diff)
//   [20..24) int32  king_value (centipawns per (Wkings - Bkings) diff)
//   For each pattern: (same as v1)
//
// Version 3 (D2 base-3 encoding — Scan-aligned, drops king distinction
// in patterns so kings are handled solely by king_value skeleton):
//   [0..4)   magic         = "JPAT"
//   [4..8)   uint32 version = 3
//   [8..12)  uint32 num_patterns
//   [12..16) int32  bias
//   [16..20) int32  man_value
//   [20..24) int32  king_value
//   [24..25) uint8  encoding_base (3 or 5; applies to ALL patterns)
//   For each pattern:
//     uint8  num_squares (K)
//     uint8[K] squares
//     int32[encoding_base^K] weights
//
// Version 4 (G3a feature engineering — Scan-aligned king PST + balance,
// mono-phase; cf. docs/SCAN_METHODOLOGY_GAP.md §G3). Strict additive
// extension of v3 (header grows AFTER encoding_base, then patterns):
//   [0..4)    magic         = "JPAT"
//   [4..8)    uint32 version = 4
//   [8..12)   uint32 num_patterns
//   [12..16)  int32  bias
//   [16..20)  int32  man_value
//   [20..24)  int32  king_value         (intrinsic per-king bonus, like v2/v3)
//   [24..25)  uint8  encoding_base      (3 or 5)
//   [25..29)  int32  balance            (L/R skew; positive when whites
//                                        skewed right vs blacks skewed left)
//   [29..229) int32[50] king_pst        (per-square positional bonus for
//                                        white kings on FMJD square s = pst[s-1];
//                                        black kings use pst[50-s], i.e. the
//                                        row-mirrored entry)
//   For each pattern: (same layout as v3)
//
// `load()` accepts v1, v2, v3, v4 transparently. v1/v2 imply base=5 and
// balance/king_pst=0. Phase split (mg/eg per Scan §2) is NOT in v4 yet
// (it would be v5/G3b).
//
// Single-file, self-describing. The pattern set is part of the file
// (not hard-coded at load time), so different pattern sets can be
// loaded transparently.

#pragma once

#include "nnue.hpp"
#include "position.hpp"
#include "types.hpp"

#include <array>
#include <cstdint>
#include <string_view>
#include <vector>

namespace jass {

class PatternNetwork : public INetwork {
public:
    // Each pattern stores its K squares (FMJD numbering) and a flat
    // weight table of size 5^K.
    struct Pattern {
        std::vector<std::uint8_t>  squares;  // length K, values 1..50
        std::vector<std::int32_t>  weights;  // length 5^K
    };

    PatternNetwork();

    // V1 default pattern set: 8 patterns × 4 squares each, weights zero.
    // Useful for tests; production callers should load() trained weights.
    static PatternNetwork default_v1();

    // V2 default pattern set: 16 patterns × 8 squares each, full
    // coverage of the 50 playable squares with overlap (each square is
    // in 1-4 patterns). Scan-class scale — ~6.25M weights total
    // (25 MB JPAT on disk). The architectural test the literature
    // points at for 10×10 draughts.
    static PatternNetwork default_v2();

    int evaluate(const Position& pos) const noexcept override;

    // Add a pattern (squares). Weights are initialised to zero. The
    // weights vector is sized to 5^|squares|.
    void add_pattern(const std::vector<std::uint8_t>& squares);

    // Direct weight access for the trainer and tests.
    std::size_t num_patterns() const noexcept { return patterns_.size(); }
    const Pattern& pattern(std::size_t i) const noexcept { return patterns_[i]; }
    Pattern& pattern_mut(std::size_t i) noexcept { return patterns_[i]; }
    std::int32_t bias() const noexcept { return bias_; }
    void set_bias(std::int32_t b) noexcept { bias_ = b; }

    // D1 hybrid (JPAT v2) — structural skeleton weights. man_value is
    // added to the white-POV sum as `man_value * (Wmen - Bmen)`,
    // king_value similarly for kings. Both default to 0, which makes
    // the network behave identically to a pure-pattern v1 net.
    std::int32_t man_value()  const noexcept { return man_value_;  }
    std::int32_t king_value() const noexcept { return king_value_; }
    void set_man_value (std::int32_t v) noexcept { man_value_  = v; }
    void set_king_value(std::int32_t v) noexcept { king_value_ = v; }

    // D2 base-3 encoding — Scan-aligned. When `encoding_base() == 3`,
    // each square contributes (empty=0, white=1, black=2) to the
    // bucket index (kings indistinguishable from men in patterns;
    // handled by king_value skeleton instead). When base == 5, the
    // legacy 0..4 encoding (empty/W-man/W-king/B-man/B-king) applies.
    // The base is enforced uniform across all patterns of a network.
    std::uint8_t encoding_base() const noexcept { return encoding_base_; }
    // Set the encoding base. Resizes existing pattern weight tables to
    // base^K. Use BEFORE training; mostly a constructor helper.
    void set_encoding_base(std::uint8_t b) noexcept;

    // G3a / JPAT v4 — additional Scan-aligned features. balance is
    // applied as `balance * skew(pos)` where skew is white-pieces
    // skewed-right minus black-pieces skewed-left. king_pst[s-1] is
    // added for each white king on FMJD square s; mirrored
    // (`king_pst[50-s]`) for each black king (white-POV symmetry).
    std::int32_t balance() const noexcept { return balance_; }
    void         set_balance(std::int32_t b) noexcept { balance_ = b; }
    const std::array<std::int32_t, 50>& king_pst() const noexcept { return king_pst_; }
    std::array<std::int32_t, 50>&       king_pst_mut() noexcept   { return king_pst_; }

    // Save format: pass `version = 2` to write the hybrid header (even
    // if man/king are 0); `version = 3` writes the v3 header that
    // additionally records the encoding_base; `version = 4` adds the
    // G3a balance + king PST. Default `version = 1` matches the legacy
    // pure-pattern layout.
    bool load(std::string_view path);
    bool save(std::string_view path, std::uint32_t version = 1) const;
    bool load_from_bytes(const unsigned char* data, std::size_t n);

private:
    std::vector<Pattern>  patterns_;
    std::int32_t          bias_{0};
    std::int32_t          man_value_{0};      // JPAT v2+ only
    std::int32_t          king_value_{0};     // JPAT v2+ only
    std::uint8_t          encoding_base_{5};  // JPAT v3+ only; 5 = legacy
    // G3a / JPAT v4 only. White-POV layout: king_pst_[s-1] applies to
    // each white king on FMJD square s; for black kings we use the
    // row-mirrored entry king_pst_[50-s] (square 51-s).
    std::int32_t                       balance_{0};
    std::array<std::int32_t, 50>       king_pst_{};
};

}  // namespace jass
