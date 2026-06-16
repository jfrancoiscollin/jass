// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// External endgame-database bridge (Kingsrow `egdb_intl`).
// ---------------------------------------------------------------------------
// jass ships its own tiny retrograde kings-only tables (bitbase.cpp). They
// cover K-vs-K / 2-vs-1 / 3-vs-1 only. Scan/Kingsrow-class strength in the
// endgame leans on a FULL WLD database (men + kings, up to 7-8 pieces). Rather
// than build our own multi-GB retrograde analysis, we ADAPT an existing
// external source: Ed Gilbert's open-source `egdb_intl` driver
// (https://github.com/eygilbert/egdb_intl), which reads the Kingsrow-format
// international-draughts databases.
//
// This header is the STABLE SEAM. The implementation has two flavours:
//
//   * default (JASS_EGDB OFF) — no-op stubs. `init()` returns false,
//     `available()` is false, `probe()` returns Unknown. The engine builds
//     and runs with ZERO external dependency; the endgame path is exactly the
//     in-memory kings-only tables as before.
//
//   * JASS_EGDB ON — links `egdb_intl`, opens the DB directory once, and
//     converts a jass `Position` into the driver's board representation for a
//     WLD lookup. Built only on a host that has the library + the database
//     files (a box / Codex job — the DBs are large and licence-gated).
//
// The seam keeps the adaptation (board mapping, result mapping, side-to-move,
// lifecycle, thread-safety, noexcept wrapping) in ONE translation unit so the
// rest of the engine never sees `egdb_intl` types. See
// docs/BITBASE_INTEGRATION.md for the full plan and the open verification
// items (the bit-layout mapping is the #1 thing to confirm against the
// egdb_intl headers before trusting a single probe).

#pragma once

#include "endgame.hpp"
#include "position.hpp"

#include <cstdint>
#include <string>

namespace jass::egdb {

// Bit-layout adaptation (the #1 correctness item, RESOLVED against the
// egdb_intl header). jass packs the 50 playable squares CONTIGUOUSLY: FMJD
// square s → bit (s-1), bits 0..49. egdb_intl packs them with a 1-bit GAP after
// each group of 10 squares (skipped bits 10, 21, 32, 43): square s → bit
// (s-1) + (s-1)/10, spanning bits 0..53. `spread50_to_egdb` converts one of
// jass's contiguous 50-bit piece bitboards into egdb's gapped layout by
// shifting each 10-square group left by its group index. Pure + always
// compiled (no egdb dependency) so it is unit-tested offline against the
// egdb_intl example positions — the strongest guard on the mapping before any
// real probe. Verified: square 2 → 0x2, square 26 → 0x08000000 (cf the
// egdb_intl example table).
inline std::uint64_t spread50_to_egdb(std::uint64_t jass_bb) noexcept {
    constexpr std::uint64_t G = 0x3FFULL;  // 10-bit group mask
    return  (jass_bb & G)
         | ((jass_bb & (G << 10)) << 1)
         | ((jass_bb & (G << 20)) << 2)
         | ((jass_bb & (G << 30)) << 3)
         | ((jass_bb & (G << 40)) << 4);
}

// Open the database rooted at `db_dir` with `cache_mb` of RAM cache. Safe to
// call more than once (subsequent calls are ignored once a handle is open).
// Returns true iff a usable handle is now open. No-op stub returns false when
// the engine was built without JASS_EGDB. Never throws.
bool init(const std::string& db_dir, int cache_mb) noexcept;

// Close the handle (idempotent). Never throws.
void shutdown() noexcept;

// True once a database handle is open. Cheap (atomic load) — the search probe
// path checks this first so a non-EGDB build pays nothing.
bool available() noexcept;

// Largest total piece count covered by the open database (0 when unavailable).
// `probe()` short-circuits to Unknown above this, so the search can gate the
// call on `popcount(occupied) <= max_pieces()` to avoid a wasted lookup.
int max_pieces() noexcept;

// WLD probe. Converts `pos` to the driver board, looks up the exact
// win/loss/draw value (from the side-to-move's perspective inside the driver,
// re-expressed here as White/Black absolute), and maps it to EndgameResult.
// Returns Unknown when the engine lacks a handle, the position is outside the
// DB's piece cap, or the driver returns a non-exact value (WIN_OR_DRAW /
// DRAW_OR_LOSS / not-in-cache). noexcept — any driver error degrades to
// Unknown so the normal search simply continues.
EndgameResult probe(const Position& pos) noexcept;

// Convenience: if no handle is open yet, try a one-time lazy open from the
// `JASS_EGDB_PATH` environment variable (cache size from `JASS_EGDB_CACHE_MB`,
// default 1024). Returns available(). Lets the endgame probe self-bootstrap
// without threading an init call through Engine/HUB/main. Thread-safe
// (std::call_once); never throws.
bool ensure_initialised() noexcept;

}  // namespace jass::egdb
