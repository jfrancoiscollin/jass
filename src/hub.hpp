// SPDX-License-Identifier: MIT
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
//   eval                           emit the static eval (white POV)
//   fen                            emit the current FEN
//   quit                           exit
//
// Move format on input/output:
//   - "from-to"  for quiet moves (e.g. "31-26")
//   - "fromxto"  for captures    (e.g. "28x17")
// Multi-jump captures are accepted as just "fromxto" (final landing only);
// the engine resolves the captured-piece path against its legal-move list.

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

private:
    Engine        engine_;
    std::istream& in_;
    std::ostream& out_;

    // Output mutex: the worker thread emits `bestmove` while the main
    // thread may still be writing other replies; serialise them line-by-
    // line so they never interleave mid-character.
    std::mutex        out_mutex_;
    std::atomic<bool> stop_flag_{false};
    std::thread       worker_;
    int               threads_{1};

    void dispatch(std::string_view line);

    void cmd_hello();
    void cmd_newgame();
    void cmd_position(std::string_view args);
    void cmd_apply   (std::string_view args);
    void cmd_go        (std::string_view args);
    void cmd_stop      ();
    void cmd_setoption (std::string_view args);
    void cmd_eval      ();
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

// Parse a move string (`from-to` / `fromxto`) and return the matching
// legal move from `pos`, if any. The first matching legal move is
// returned in the rare case where two captures share the same (from, to)
// but differ in their captured-piece path.
std::optional<Move> parse_move(const Position& pos, std::string_view text);

// Format a move as `from-to` (quiet) or `fromxto` (capture).
std::string format_move(const Move& m);

}  // namespace jass
