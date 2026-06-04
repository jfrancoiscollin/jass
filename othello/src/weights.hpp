// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Loader for the OTHW (Othello Weights) binary format produced by
// othello/tools/train.py.
//
// File layout :
//   uint32_t magic    = 0x4F544857  ("OTHW")
//   uint32_t version  = 1
//   uint32_t count    = number of int32 weights (= TOTAL_BUCKETS = 39690)
//   uint32_t scale    = quantisation factor (e.g. 1000 → centi-piece units)
//   int32_t  w[count]

#pragma once

#include "pattern.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace othello {

constexpr std::uint32_t WEIGHTS_MAGIC   = 0x4F544857U;  // "OTHW"
constexpr std::uint32_t WEIGHTS_VERSION = 1U;
constexpr std::size_t   WEIGHTS_HEADER_SIZE = 16;

struct Weights {
    std::vector<std::int32_t> w;
    std::uint32_t scale = 1000;
};

// Load weights from disk. Returns std::nullopt and sets `err` on failure.
std::optional<Weights> load_weights(const std::string& path, std::string* err = nullptr);

}  // namespace othello
