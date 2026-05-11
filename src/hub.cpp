// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "hub.hpp"

#include "eval.hpp"
#include "nnue.hpp"
#include "timemgr.hpp"

#include <cctype>
#include <charconv>
#include <istream>
#include <ostream>
#include <string>

namespace jass {

namespace {

constexpr const char* ENGINE_NAME    = "Jass";
constexpr const char* ENGINE_VERSION = "0.0.1";
constexpr const char* ENGINE_AUTHOR  = "Jean-François Collin";

// Strip leading/trailing ASCII whitespace.
std::string_view trim(std::string_view s) noexcept {
    std::size_t i = 0;
    while (i < s.size() && std::isspace(static_cast<unsigned char>(s[i]))) ++i;
    std::size_t j = s.size();
    while (j > i && std::isspace(static_cast<unsigned char>(s[j - 1]))) --j;
    return s.substr(i, j - i);
}

// Split a line into the leading word (the command) and the rest.
std::pair<std::string_view, std::string_view>
split_first_word(std::string_view s) noexcept {
    s = trim(s);
    const auto sp = s.find_first_of(" \t");
    if (sp == std::string_view::npos) return {s, {}};
    return {s.substr(0, sp), trim(s.substr(sp + 1))};
}

// Parse a base-10 unsigned integer; return std::nullopt on failure.
std::optional<int> parse_int(std::string_view s) noexcept {
    s = trim(s);
    int value = 0;
    auto [ptr, ec] = std::from_chars(s.data(), s.data() + s.size(), value);
    if (ec != std::errc{} || ptr != s.data() + s.size()) return std::nullopt;
    return value;
}

}  // namespace

// ---------------------------------------------------------------------------
// Move parsing / formatting
// ---------------------------------------------------------------------------
std::optional<Move> parse_move(const Position& pos, std::string_view text) {
    text = trim(text);

    // Find the first separator; subsequent tokens (multi-jump path) are
    // discarded — we resolve the captured-piece set from the legal-move
    // list based on (from, to) only.
    const auto sep = text.find_first_of("-x");
    if (sep == std::string_view::npos) return std::nullopt;

    const auto from_tok = text.substr(0, sep);
    auto rest = text.substr(sep + 1);

    // Last numeric token is the destination square.
    std::string_view to_tok = rest;
    while (true) {
        const auto next_sep = to_tok.find_first_of("-x");
        if (next_sep == std::string_view::npos) break;
        to_tok = to_tok.substr(next_sep + 1);
    }

    const auto from_n = parse_int(from_tok);
    const auto to_n   = parse_int(to_tok);
    if (!from_n || !to_n)                                   return std::nullopt;
    if (*from_n < 1 || *from_n > 50)                        return std::nullopt;
    if (*to_n   < 1 || *to_n   > 50)                        return std::nullopt;

    MoveList ml;
    generate_legal_moves(pos, ml);
    for (const auto& m : ml) {
        if (m.from == *from_n && m.to == *to_n) return m;
    }
    return std::nullopt;
}

std::string format_move(const Move& m) {
    const char sep = m.is_capture() ? 'x' : '-';
    return std::to_string(static_cast<int>(m.from)) + sep
         + std::to_string(static_cast<int>(m.to));
}

// ---------------------------------------------------------------------------
// HubFrontEnd
// ---------------------------------------------------------------------------
HubFrontEnd::HubFrontEnd(std::istream& in, std::ostream& out)
    : in_(in), out_(out) {
    // End users get the trained NNUE eval out of the box; main.cpp can
    // override or disable it via --nnue / --no-nnue.
    engine_.set_nnue(default_nnue());
}

HubFrontEnd::~HubFrontEnd() {
    stop_flag_.store(true, std::memory_order_relaxed);
    wait_for_worker();
}

void HubFrontEnd::set_nnue(const INetwork* n) noexcept {
    engine_.set_nnue(n);
}

bool HubFrontEnd::load_book(std::string_view path) {
    return engine_.load_book(path);
}

int HubFrontEnd::run() {
    std::string line;
    while (std::getline(in_, line)) {
        const auto trimmed = trim(line);
        if (trimmed.empty()) continue;
        if (trimmed == "quit") {
            cmd_stop();  // interrupt and join any running search
            break;
        }
        dispatch(trimmed);
    }
    // EOF (or `quit`) reached: signal any background search to abandon and
    // wait for its thread to drain so we don't leak a still-running worker.
    stop_flag_.store(true, std::memory_order_relaxed);
    wait_for_worker();
    return 0;
}

void HubFrontEnd::dispatch(std::string_view line) {
    const auto [cmd, args] = split_first_word(line);

    if      (cmd == "hello")     cmd_hello();
    else if (cmd == "newgame")   cmd_newgame();
    else if (cmd == "position")  cmd_position(args);
    else if (cmd == "apply")     cmd_apply(args);
    else if (cmd == "go")        cmd_go(args);
    else if (cmd == "stop")      cmd_stop();
    else if (cmd == "setoption") cmd_setoption(args);
    else if (cmd == "eval")      cmd_eval();
    else if (cmd == "fen")       cmd_fen();
    else                         emit_error("unknown command");
}

void HubFrontEnd::emit_ok() {
    std::lock_guard lk{out_mutex_};
    out_ << "ok\n";
    out_.flush();
}

void HubFrontEnd::emit_error(std::string_view reason) {
    std::lock_guard lk{out_mutex_};
    out_ << "error " << reason << '\n';
    out_.flush();
}

void HubFrontEnd::emit_bestmove(const SearchResult& r) {
    std::lock_guard lk{out_mutex_};
    out_ << "bestmove " << format_move(r.best_move)
         << " score="   << r.score
         << " depth="   << r.depth
         << " nodes="   << r.nodes;
    // External orchestrators (e.g. the Jass-vs-Scan harness) need the
    // captured-square list to translate the move into other engines'
    // notation. `format_move` only emits the (from, to) endpoints, so
    // we surface the captured squares here. Empty when the move is
    // quiet.
    if (r.best_move.num_captures > 0) {
        out_ << " captures=";
        for (std::uint8_t i = 0; i < r.best_move.num_captures; ++i) {
            if (i) out_ << ',';
            out_ << static_cast<int>(r.best_move.captures[i]);
        }
    }
    if (r.from_book) out_ << " book=1";
    if (!r.pv.empty()) {
        out_ << " pv=";
        for (std::size_t i = 0; i < r.pv.size(); ++i) {
            if (i) out_ << ',';
            out_ << format_move(r.pv[i]);
        }
    }
    out_ << '\n';
    out_.flush();
}

void HubFrontEnd::cmd_hello() {
    std::lock_guard lk{out_mutex_};
    out_ << "id name=" << ENGINE_NAME
         << " version="           << ENGINE_VERSION
         << " author=\""          << ENGINE_AUTHOR << "\"\n"
         << "ready\n";
    out_.flush();
}

void HubFrontEnd::cmd_newgame() {
    wait_for_worker();
    engine_.new_game();
    emit_ok();
}

void HubFrontEnd::cmd_position(std::string_view args) {
    wait_for_worker();
    const auto [head, rest] = split_first_word(args);
    if (head == "startpos") {
        engine_.new_game();
        emit_ok();
        return;
    }
    if (head == "fen") {
        if (engine_.set_position_fen(std::string{rest})) emit_ok();
        else                                             emit_error("bad fen");
        return;
    }
    emit_error("position: expected `startpos` or `fen <FEN>`");
}

void HubFrontEnd::cmd_apply(std::string_view args) {
    wait_for_worker();
    auto m = parse_move(engine_.position(), args);
    if (!m) {
        emit_error("apply: not a legal move");
        return;
    }
    if (!engine_.apply_move(*m)) {
        emit_error("apply: not a legal move");
        return;
    }
    emit_ok();
}

void HubFrontEnd::cmd_go(std::string_view args) {
    wait_for_worker();

    SearchLimits lim;
    TimeBudget   tb;
    bool async      = false;
    bool depth_set  = false;

    // Generic key/value tokenizer: every option after `go` is either a
    // bare token (`infinite`) or a key followed by a value. Unknown
    // tokens are silently skipped so a future protocol extension is
    // forward-compatible.
    std::string_view rest = args;
    while (true) {
        const auto [tok, after] = split_first_word(rest);
        if (tok.empty()) break;
        rest = after;

        auto take_int = [&](int& out) -> bool {
            const auto [v, after2] = split_first_word(rest);
            rest = after2;
            const auto n = parse_int(v);
            if (!n) return false;
            out = *n;
            return true;
        };

        if (tok == "infinite") {
            async = true;
        } else if (tok == "depth") {
            int v = 0;
            if (!take_int(v) || v < 1) {
                emit_error("go depth: positive integer required");
                return;
            }
            lim.max_depth = v;
            depth_set     = true;
        } else if (tok == "movetime") {
            int v = 0;
            if (!take_int(v) || v < 1) {
                emit_error("go movetime: positive integer required");
                return;
            }
            lim.movetime_ms = v;
        } else if (tok == "wtime")     { int v = 0; take_int(v); tb.wtime_ms  = v; }
          else if (tok == "btime")     { int v = 0; take_int(v); tb.btime_ms  = v; }
          else if (tok == "winc")      { int v = 0; take_int(v); tb.winc_ms   = v; }
          else if (tok == "binc")      { int v = 0; take_int(v); tb.binc_ms   = v; }
          else if (tok == "movestogo") { int v = 0; take_int(v); tb.movestogo = v; }
        // else: unknown token, ignore (forward-compat).
    }

    // Derive a movetime from the tournament-style time budget when none
    // was given explicitly.
    if (lim.movetime_ms == 0
        && (tb.wtime_ms > 0 || tb.btime_ms > 0
         || tb.winc_ms  > 0 || tb.binc_ms  > 0)) {
        lim.movetime_ms = compute_movetime_ms(tb, engine_.position().side_to_move());
    }

    // Pick the right depth ceiling based on what was actually specified.
    if (!depth_set) {
        // `infinite` and time-bounded searches go as deep as possible.
        // Default `go` (no args) uses depth 6.
        lim.max_depth = (async || lim.movetime_ms > 0) ? MAX_PLY : 6;
    }

    stop_flag_.store(false, std::memory_order_relaxed);
    lim.stop_flag = &stop_flag_;
    lim.threads   = threads_;

    if (async) run_search_async(lim);
    else       run_search_sync(lim);
}

void HubFrontEnd::cmd_setoption(std::string_view args) {
    wait_for_worker();
    const auto [name, rest] = split_first_word(args);
    if (name == "threads") {
        const auto n = parse_int(rest);
        if (!n || *n < 1) {
            emit_error("setoption threads: must be a positive integer");
            return;
        }
        threads_ = *n;
        emit_ok();
        return;
    }
    emit_error("setoption: unknown option");
}

void HubFrontEnd::cmd_stop() {
    stop_flag_.store(true, std::memory_order_relaxed);
    wait_for_worker();
}

void HubFrontEnd::cmd_eval() {
    wait_for_worker();
    std::lock_guard lk{out_mutex_};
    out_ << "eval " << evaluate(engine_.position()) << '\n';
    out_.flush();
}

void HubFrontEnd::cmd_fen() {
    wait_for_worker();
    std::lock_guard lk{out_mutex_};
    out_ << "fen " << engine_.position().to_fen() << '\n';
    out_.flush();
}

void HubFrontEnd::run_search_sync(const SearchLimits& limits) {
    const SearchResult r = engine_.search(limits);
    emit_bestmove(r);
}

void HubFrontEnd::run_search_async(SearchLimits limits) {
    worker_ = std::thread([this, limits]() {
        const SearchResult r = engine_.search(limits);
        emit_bestmove(r);
    });
}

void HubFrontEnd::wait_for_worker() {
    if (worker_.joinable()) worker_.join();
}

}  // namespace jass
