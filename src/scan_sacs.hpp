// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Faithful port of Scan's selective sacrifice generator (rhalbersma/scan,
// src/gen.cpp::add_sacs) for the forcing/sac quiescence. jass and Scan use
// DIFFERENT bit layouts (jass: dense 1-50 with parity shifts ; Scan: sparse
// 64-bit magic layout, diagonals = fixed <<6 / <<7). Rather than re-express the
// subtle ~80-line bitboard selector in jass's geometry (error-prone), we CONVERT
// jass's bitboards into Scan's sparse layout, run add_sacs VERBATIM, and map the
// resulting sac moves back to jass squares. Validated bit-for-bit against Scan's
// own add_sacs dump (tools/scan_oracle/). Scan is GPL3 ; jass is AGPL3-compatible.
#pragma once
#include "movegen.hpp"
#include "position.hpp"

namespace jass {

// Append Scan's selective sacrifices (a handful of positionally-gated man sac
// moves, quiet) for the side to move to `out`. Men-only positional selector —
// the caller applies Scan's gate (no king, no threat) before invoking.
void scan_add_sacs(const Position& pos, MoveList& out);

}  // namespace jass
