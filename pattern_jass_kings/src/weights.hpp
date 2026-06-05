// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// PJTW loader for pattern_jass_kings (5-state, 8 patterns × 8 squares,
// 3.125M weights). Same OTHW-style format but with TOTAL_BUCKETS
// adjusted for this variant.

#pragma once

#include "pattern.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace pattern_jass_kings {

constexpr std::uint32_t WEIGHTS_MAGIC       = 0x57544A50U;  // "PJTW"
constexpr std::uint32_t WEIGHTS_VERSION     = 1U;
constexpr std::size_t   WEIGHTS_HEADER_SIZE = 16;

struct Weights {
    std::vector<std::int32_t> w;
    std::uint32_t scale = 1000;
};

std::optional<Weights> load_weights(const std::string& path,
                                    std::string* err = nullptr);

// black-POV pattern eval. Caller sign-flips for stm.
std::int64_t eval_pattern(Bitboard bm, Bitboard bk,
                          Bitboard wm, Bitboard wk,
                          const std::int32_t* weights) noexcept;

}  // namespace pattern_jass_kings
