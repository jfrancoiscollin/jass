// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// A small command-line front-end for Jass, line-based and HUB-flavoured.
//
// Not a full HUB-protocol implementation — this is a deliberately minimal
// subset that lets you drive the engine from a shell or hook it up to a
// GUI for casual testing. The full set of HUB commands (level, ponder,
// time controls …) can be layered on top later without touching the
// engine core.
//
// Commands accepted (all whitespace-tolerant, one per line):
//
//   hello                          handshake; emit `id` + `ready`
//   newgame                        reset to the standard initial position
//   position startpos              set position to start
//   position fen <Hub-style FEN>   set position to a FEN string
//   apply <move>                   play one move, e.g. "31-26" or "28x17"
//   go depth <N>                   search to depth N, emit `bestmove`
//   go movetime <ms>               search up to <ms> milliseconds
//   go infinite                    search until `stop` (runs in a thread)
//   go wtime <ms> btime <ms>       tournament-style time budget. The
//      [winc <ms>] [binc <ms>]     engine derives a per-move cap from
//      [movestogo <N>]             the side-to-move's remaining time.
//   stop                           interrupt the current search
//   setoption threads <N>          set the number of search threads (>=1)
//   eval                           emit the handcrafted static eval
//   neteval                        emit the installed network eval (STM POV)
//   fen                            emit the current FEN
//   quit                           exit
//
// Move format on input/output:
//   - "from-to"  for quiet moves (e.g. "31-26")
//   - "fromxto"  for captures    (e.g. "28x17")
//   - "fromxto captures=s1,s2,..." for an exact multi-jump identity
// Endpoint-only captures remain accepted for backward compatibility.  When
// several legal captures share the same endpoints, callers that need an
// unambiguous move (referees and scientific harnesses) must provide captures=.

#pragma once

#include "engine.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "search.hpp"

#include <atomic>
#include <iosfwd>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <thread>

namespace jass {

class HubFrontEnd {
public:
    HubFrontEnd(std::istream& in, std::ostream& out);
    ~HubFrontEnd();

    HubFrontEnd(const HubFrontEnd&)            = delete;
    HubFrontEnd& operator=(const HubFrontEnd&) = delete;

    // Run the command loop until either `quit` is received or `in` reaches
    // EOF. Returns 0 (a placeholder for richer exit semantics).
    int run();

    // Override the engine-side NNUE network used at every leaf. By
    // default the constructor installs `default_nnue()`; pass `nullptr`
    // to fall back to the handcrafted eval, or any other `INetwork`
    // (e.g. a freshly loaded MLP) to swap models without recompiling.
    void set_nnue(const INetwork* n) noexcept;

    // Override the search parameters used for every `go` (LMR/pruning/etc.).
    // Lets a harness (e.g. calibrate_vs_scan via --search-params) play the
    // HUB engine with non-default search constants WITHOUT a rebuild — the
    // workflow for tuning search vs Scan. Default = compiled SearchParams{}.
    void set_search_params(const SearchParams& p) noexcept;

    // Resize the transposition table (MB). Default 16 MB is small for deep
    // search (the TT thrashes → worse move ordering + re-searched transpositions
    // → bigger tree). Lets a harness sweep TT size at fixed time without rebuild.
    void set_tt_mb(std::size_t mb);

    // Replace the engine's opening book with the contents of a JBOK
    // file at `path`. Returns false on I/O error or bad format.
    bool load_book(std::string_view path);

    // Toggle book consultation. The built-in book is small but it is
    // consulted unconditionally, so a harness that runs Scan with
    // `book=off` has no way to make the match symmetric without this.
    void use_book(bool yes) noexcept { engine_.use_book(yes); }

private:
    Engine        engine_;
    SearchParams  params_{};   // applied to every `go` (see set_search_params)
    std::istream& in_;
    std::ostream& out_;

    // Output mutex: the worker thread emits `bestmove` while the main
    // thread may still be writing other replies; serialise them line-by-
    // line so they never interleave mid-character.
    std::mutex        out_mutex_;
    std::atomic<bool> stop_flag_{false};
    std::thread       worker_;
    int               threads_{1};
    std::string       root_order_schedule_;

    void dispatch(std::string_view line);

    void cmd_hello();
    void cmd_newgame();
    void cmd_position(std::string_view args);
    void cmd_apply   (std::string_view args);
    void cmd_go        (std::string_view args);
    void cmd_stop      ();
    void cmd_setoption (std::string_view args);
    void cmd_eval      ();
    void cmd_neteval   ();
    void cmd_fen       ();

    void emit_ok();
    void emit_error(std::string_view reason);
    void emit_bestmove(const SearchResult& r);

    // Run a search synchronously and emit the result on the main thread.
    void run_search_sync(const SearchLimits& limits);
    // Spawn a worker that runs the search and emits the result; the main
    // thread continues reading commands.
    void run_search_async(SearchLimits limits);
    // Wait for any active worker to complete (joining the thread).
    void wait_for_worker();
};

// Parse a move string (`from-to` / `fromxto`) and return the matching legal
// move from `pos`, if any. Endpoint-only input retains the legacy first-match
// behaviour; appending `captures=s1,s2,...` requires that exact capture set
// and unambiguously identifies multi-captures with shared endpoints.
std::optional<Move> parse_move(const Position& pos, std::string_view text);

// Format a move as `from-to` (quiet) or `fromxto` (capture).
std::string format_move(const Move& m);

}  // namespace jass
