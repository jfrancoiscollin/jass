// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// External endgame-database bridge — see egdb_bridge.hpp.
//
// Two compile flavours selected by the JASS_EGDB build option:
//   * OFF (default) : no-op stubs, zero external dependency.
//   * ON            : real adaptation against Ed Gilbert's `egdb_intl` driver.

#include "egdb_bridge.hpp"

#include "bitboard.hpp"

#include <atomic>
#include <cstdlib>
#include <mutex>

namespace jass::egdb {

namespace {
// `available()` is read on the hot search path, so keep it a plain atomic the
// probe can check without taking the mutex. The mutex guards open/close.
std::atomic<bool> g_available{false};
std::atomic<int>  g_max_pieces{0};
std::once_flag    g_lazy_once;
}  // namespace

// ---------------------------------------------------------------------------
// Lazy bootstrap from the environment (shared by both flavours).
// ---------------------------------------------------------------------------
bool ensure_initialised() noexcept {
    if (g_available.load(std::memory_order_acquire)) return true;
    std::call_once(g_lazy_once, [] {
        const char* path = std::getenv("JASS_EGDB_PATH");
        if (!path || !*path) return;
        int cache_mb = 1024;
        if (const char* c = std::getenv("JASS_EGDB_CACHE_MB")) {
            const int v = std::atoi(c);
            if (v > 0) cache_mb = v;
        }
        init(std::string(path), cache_mb);
    });
    return g_available.load(std::memory_order_acquire);
}

bool available() noexcept { return g_available.load(std::memory_order_acquire); }
int  max_pieces() noexcept { return g_max_pieces.load(std::memory_order_acquire); }

#ifndef JASS_EGDB
// ===========================================================================
// STUB FLAVOUR (default build) — no external dependency.
// ===========================================================================
bool init(const std::string&, int) noexcept { return false; }
void shutdown() noexcept {}
EndgameResult probe(const Position&) noexcept { return EndgameResult::Unknown; }

#else
// ===========================================================================
// REAL FLAVOUR (-DJASS_EGDB) — adaptation against egdb_intl.
// ===========================================================================
// NB: this is a SKELETON. Every item flagged `VERIFY` below must be confirmed
// against the actual egdb_intl headers on the build host before a probe is
// trusted (see docs/BITBASE_INTEGRATION.md §Verification). The bit-layout
// mapping in to_egdb_position() is the highest-risk assumption: a silent
// mismatch returns confidently wrong WLD values that corrupt the search.

#include <egdb/egdb_intl.h>   // VERIFY include path on the build host.

namespace {

EGDB_DRIVER*   g_handle = nullptr;
std::mutex     g_mutex;

// egdb_intl emits diagnostics through a caller-supplied callback. Swallow them
// (or route to stderr) — must not throw.
void egdb_msg(char const* /*msg*/) noexcept {}

// --- Board conversion -----------------------------------------------------
// EGDB_POSITION carries three 50-bit bitboards: `black` = all black pieces,
// `white` = all white pieces, `king` = all kings (either colour). jass uses
// bit i == FMJD square (i+1) (cf bitboard.hpp). VERIFY egdb_intl uses the SAME
// bit→square mapping (Kingsrow standard FMJD numbering, bit = square-1). If it
// differs we must permute bits here — until confirmed, treat any agreement
// against jass's own kings-only tables (bitbase.cpp) as the cross-check.
EGDB_POSITION to_egdb_position(const Position& pos) noexcept {
    EGDB_POSITION ep;
    ep.black = static_cast<decltype(ep.black)>(pos.blacks());
    ep.white = static_cast<decltype(ep.white)>(pos.whites());
    ep.king  = static_cast<decltype(ep.king)>(pos.white_kings() | pos.black_kings());
    return ep;
}

// jass Color → egdb colour code. jass Black sits on the top rows (FMJD 1..20),
// White on the bottom (31..50); egdb_intl's EGDB_BLACK/EGDB_WHITE follow the
// same home-row convention. VERIFY the enum values + direction-of-play.
constexpr int to_egdb_color(Color c) noexcept {
    return (c == Color::White) ? EGDB_WHITE : EGDB_BLACK;
}

// Map a driver WLD code (from the side-to-move's perspective) to an absolute
// White/Black result. Only EXACT values are propagated; partial/unknown codes
// degrade to Unknown so the search keeps running.
EndgameResult from_egdb_value(int value, Color stm) noexcept {
    switch (value) {
        case EGDB_WIN:
            return (stm == Color::White) ? EndgameResult::WhiteWin
                                         : EndgameResult::BlackWin;
        case EGDB_LOSS:
            return (stm == Color::White) ? EndgameResult::BlackWin
                                         : EndgameResult::WhiteWin;
        case EGDB_DRAW:
            return EndgameResult::Draw;
        default:  // EGDB_UNKNOWN / EGDB_NOT_IN_CACHE / *_OR_* partial bounds
            return EndgameResult::Unknown;
    }
}

}  // namespace

bool init(const std::string& db_dir, int cache_mb) noexcept {
    try {
        std::lock_guard<std::mutex> lk(g_mutex);
        if (g_handle) return true;
        // VERIFY egdb_open signature + the "options" string (DB type / piece
        // cap selection) against the egdb_intl docs.
        g_handle = egdb_open(/*options=*/"", cache_mb, db_dir.c_str(), &egdb_msg);
        if (!g_handle) return false;
        // VERIFY how to query the covered piece cap (get_pieces / from options).
        int maxp = 8;  // Kingsrow intl WLD ships up to 8 (some 9) pieces.
        g_max_pieces.store(maxp, std::memory_order_release);
        g_available.store(true, std::memory_order_release);
        return true;
    } catch (...) {
        return false;
    }
}

void shutdown() noexcept {
    try {
        std::lock_guard<std::mutex> lk(g_mutex);
        if (g_handle) {
            g_handle->close(g_handle);   // VERIFY close member name.
            g_handle = nullptr;
        }
        g_available.store(false, std::memory_order_release);
        g_max_pieces.store(0, std::memory_order_release);
    } catch (...) {
    }
}

EndgameResult probe(const Position& pos) noexcept {
    if (!g_available.load(std::memory_order_acquire)) return EndgameResult::Unknown;
    if (popcount(pos.occupied()) > g_max_pieces.load(std::memory_order_acquire))
        return EndgameResult::Unknown;
    try {
        const EGDB_POSITION ep    = to_egdb_position(pos);
        const int           color = to_egdb_color(pos.side_to_move());
        // `cl` (clear/load flag): use the in-RAM/disk lookup. VERIFY arg.
        const int value = g_handle->lookup(g_handle, &ep, color, /*cl=*/0);
        return from_egdb_value(value, pos.side_to_move());
    } catch (...) {
        return EndgameResult::Unknown;
    }
}

#endif  // JASS_EGDB

}  // namespace jass::egdb
