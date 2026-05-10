// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Symbols backing the NNUE weights compiled into the binary.
//
// The byte array `NNUE_DEFAULT_BYTES` is materialised at build time by
// CMake from the `nnue.bin` file at the repo root. The format is the
// raw little-endian int32 layout consumed by `LinearNetwork::load()`
// and `LinearNetwork::load_from_bytes()`.

#pragma once

#include <cstddef>

namespace jass {

extern const unsigned char NNUE_DEFAULT_BYTES[];
extern const std::size_t   NNUE_DEFAULT_LEN;

}  // namespace jass
