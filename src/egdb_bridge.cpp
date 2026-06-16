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

// The egdb_intl public header declares everything in `namespace egdb_interface`
// at GLOBAL scope — it must be included outside jass::egdb or the symbols would
// nest as jass::egdb::egdb_interface and fail to link.
#ifdef JASS_EGDB
#include <egdb/egdb_intl.h>
#endif

#include <atomic>
#include <cstdlib>
#include <mutex>
#include <string>

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
// Verified against the egdb_intl public header (egdb/egdb_intl.h) + example:
//   * EGDB_POSITION { EGDB_BITBOARD black, white, king } — gapped bitboards
//     (skipped bits 10/21/32/43); converted via spread50_to_egdb().
//   * Free functions egdb_open / egdb_lookup / egdb_close / egdb_get_pieces in
//     namespace egdb_interface; lookup value is from the `color`-to-move POV.
//   * Open with options "maxpieces=N", lookup cl=0 (unconditional disk/cache).

namespace {

egdb_interface::EGDB_DRIVER* g_handle = nullptr;
std::mutex                   g_mutex;

// egdb_intl emits diagnostics through a caller-supplied callback. Swallow them
// (could route to stderr) — must not throw.
void egdb_msg(char const* /*msg*/) {}

// --- Board conversion (gapped layout, cf spread50_to_egdb in the header) ---
// EGDB_POSITION: `black` = all black pieces, `white` = all white pieces, `king`
// = all kings (either colour). jass Black sits on the low squares / top rows
// and egdb's black uses the same home-row + men direction, so jass Black ↔ egdb
// black, jass White ↔ egdb white (verified against the example WIN/LOSS rows).
egdb_interface::EGDB_POSITION to_egdb_position(const Position& pos) noexcept {
    egdb_interface::EGDB_POSITION ep;
    ep.black = spread50_to_egdb(static_cast<std::uint64_t>(pos.blacks()));
    ep.white = spread50_to_egdb(static_cast<std::uint64_t>(pos.whites()));
    ep.king  = spread50_to_egdb(static_cast<std::uint64_t>(pos.white_kings()
                                                         | pos.black_kings()));
    return ep;
}

constexpr int to_egdb_color(Color c) noexcept {
    return (c == Color::White) ? egdb_interface::EGDB_WHITE
                               : egdb_interface::EGDB_BLACK;
}

// Map a driver WLD code (from the side-to-move's perspective) to an absolute
// White/Black result. Only EXACT win/loss/draw are propagated; partial/unknown
// codes (UNKNOWN / NOT_IN_CACHE / SUBDB_UNAVAILABLE / *_OR_*) degrade to
// Unknown so the normal search keeps running.
EndgameResult from_egdb_value(int value, Color stm) noexcept {
    switch (value) {
        case egdb_interface::EGDB_WIN:
            return (stm == Color::White) ? EndgameResult::WhiteWin
                                         : EndgameResult::BlackWin;
        case egdb_interface::EGDB_LOSS:
            return (stm == Color::White) ? EndgameResult::BlackWin
                                         : EndgameResult::WhiteWin;
        case egdb_interface::EGDB_DRAW:
            return EndgameResult::Draw;
        default:
            return EndgameResult::Unknown;
    }
}

}  // namespace

bool init(const std::string& db_dir, int cache_mb) noexcept {
    try {
        std::lock_guard<std::mutex> lk(g_mutex);
        if (g_handle) return true;
        // Identify the DB first so we open with the right "maxpieces=N" and
        // record the real piece cap (rather than guessing). egdb_identify is
        // side-effect-free; a failure just means "no usable DB here".
        egdb_interface::EGDB_TYPE type;
        int id_max = 0;
        if (egdb_interface::egdb_identify(db_dir.c_str(), &type, &id_max) != 0
            || id_max <= 0) {
            return false;
        }
        const std::string options = "maxpieces=" + std::to_string(id_max);
        g_handle = egdb_interface::egdb_open(options.c_str(), cache_mb,
                                             db_dir.c_str(), &egdb_msg);
        if (!g_handle) return false;
        int maxp = id_max, maxp_1side = 0;
        egdb_interface::egdb_get_pieces(g_handle, &maxp, &maxp_1side);
        g_max_pieces.store(maxp > 0 ? maxp : id_max, std::memory_order_release);
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
            egdb_interface::egdb_close(g_handle);
            g_handle = nullptr;
        }
        g_available.store(false, std::memory_order_release);
        g_max_pieces.store(0, std::memory_order_release);
    } catch (...) {
    }
}

EndgameResult probe(const Position& pos) noexcept {
    if (!g_available.load(std::memory_order_acquire)) return EndgameResult::Unknown;
    const int n = popcount(pos.occupied());
    if (n > g_max_pieces.load(std::memory_order_acquire))
        return EndgameResult::Unknown;
    // The 2-piece slice (db2) returns a spurious decisive WLD for some 1K-vs-1K
    // positions (observed e.g. WK37/BK46, WK5/BK32: egdb=WIN, but bare KvK with
    // no capture is a forced draw — confirmed against the native egdb example
    // test, which only covers >=4 pieces). KvK is trivially drawn anyway, so
    // never trust egdb below 3 pieces — defer to the in-memory tables, whose
    // 1v1 = Draw shortcut is exact.
    if (n < 3) return EndgameResult::Unknown;
    try {
        const egdb_interface::EGDB_POSITION ep = to_egdb_position(pos);
        const int color = to_egdb_color(pos.side_to_move());
        // cl=0 : unconditional lookup (load from disk if not cached). The
        // driver's egdb_lookup is documented thread-safe → no lock needed.
        const int value = egdb_interface::egdb_lookup(g_handle, &ep, color, 0);
        return from_egdb_value(value, pos.side_to_move());
    } catch (...) {
        return EndgameResult::Unknown;
    }
}

#endif  // JASS_EGDB

}  // namespace jass::egdb
