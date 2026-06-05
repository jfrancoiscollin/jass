// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Loader for the PJTW (Pattern-Jass-Trained-Weights) binary format
// produced by pattern_jass/tools/train.py.
//
// File layout :
//   uint32_t magic    = 0x57544A50  ("PJTW")
//   uint32_t version  = 1
//   uint32_t count    = TOTAL_BUCKETS (472392)
//   uint32_t scale    = quantisation factor (centi-piece units)
//   int32_t  w[count]

#pragma once

#include "pattern.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace pattern_jass {

constexpr std::uint32_t WEIGHTS_MAGIC       = 0x57544A50U;  // "PJTW"
constexpr std::uint32_t WEIGHTS_VERSION     = 1U;
constexpr std::size_t   WEIGHTS_HEADER_SIZE = 16;

struct Weights {
    std::vector<std::int32_t> w;
    std::uint32_t scale = 1000;
};

// Load weights from disk. Returns std::nullopt and sets `err` on failure.
std::optional<Weights> load_weights(const std::string& path,
                                    std::string* err = nullptr);

// Linear pattern eval :
//   sum(weights[offset_p + idx_p]) over the 8 patterns.
// Returns score in black-POV (positive = black better). Caller is
// responsible for sign-flipping if the eval consumer expects stm-POV.
std::int64_t eval_pattern(Bitboard black_men, Bitboard white_men,
                          const std::int32_t* weights) noexcept;

}  // namespace pattern_jass
