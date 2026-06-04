// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Self-play data generation for Phase Pattern-1 training.
//
// Binary record format (18 bytes/record, little-endian) :
//   uint64_t black     (8B)
//   uint64_t white     (8B)
//   uint8_t  stm       (1B : 0 = Black, 1 = White)
//   int8_t   label     (1B : +1 Black wins, -1 White wins, 0 draw)
// Label is from the ABSOLUTE perspective (black POV), matching the
// color-based pattern index convention. Training code can sign-flip
// for stm if needed.
//
// File header (16 bytes) :
//   uint32_t magic     = 0x4F544843  ("OTHC" ascii)
//   uint32_t version   = 1
//   uint32_t count     (number of records)
//   uint32_t reserved  = 0

#pragma once

#include "board.hpp"

#include <cstdint>

namespace othello {

constexpr std::uint32_t GEN_DATA_MAGIC   = 0x4F544843U;  // "CHTO" LE = "OTHC"
constexpr std::uint32_t GEN_DATA_VERSION = 1U;
constexpr std::size_t   GEN_DATA_RECORD_SIZE = 18;
constexpr std::size_t   GEN_DATA_HEADER_SIZE = 16;

// Conceptual record (padding-free serialization is done explicitly in
// writer/reader code ; the struct itself may be padded by the ABI).
struct GenRecord {
    std::uint64_t black;
    std::uint64_t white;
    std::uint8_t  stm;
    std::int8_t   label;
};

}  // namespace othello
