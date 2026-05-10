// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "hub.hpp"

#include "eval.hpp"

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
    : in_(in), out_(out) {}

int HubFrontEnd::run() {
    std::string line;
    while (std::getline(in_, line)) {
        const auto trimmed = trim(line);
        if (trimmed.empty()) continue;
        if (trimmed == "quit") break;
        dispatch(trimmed);
    }
    return 0;
}

void HubFrontEnd::dispatch(std::string_view line) {
    const auto [cmd, args] = split_first_word(line);

    if      (cmd == "hello")    cmd_hello();
    else if (cmd == "newgame")  cmd_newgame();
    else if (cmd == "position") cmd_position(args);
    else if (cmd == "apply")    cmd_apply(args);
    else if (cmd == "go")       cmd_go(args);
    else if (cmd == "eval")     cmd_eval();
    else if (cmd == "fen")      cmd_fen();
    else                        emit_error("unknown command");
}

void HubFrontEnd::emit_ok() {
    out_ << "ok\n";
    out_.flush();
}

void HubFrontEnd::emit_error(std::string_view reason) {
    out_ << "error " << reason << '\n';
    out_.flush();
}

void HubFrontEnd::cmd_hello() {
    out_ << "id name=" << ENGINE_NAME
         << " version="           << ENGINE_VERSION
         << " author=\""          << ENGINE_AUTHOR << "\"\n"
         << "ready\n";
    out_.flush();
}

void HubFrontEnd::cmd_newgame() {
    engine_.new_game();
    emit_ok();
}

void HubFrontEnd::cmd_position(std::string_view args) {
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
    const auto [head, rest] = split_first_word(args);
    int depth = 6;  // default
    if (head == "depth") {
        const auto n = parse_int(rest);
        if (!n || *n < 1) {
            emit_error("go: depth must be a positive integer");
            return;
        }
        depth = *n;
    } else if (!head.empty()) {
        emit_error("go: only `depth <N>` is supported for now");
        return;
    }

    const SearchResult r = engine_.search(depth);
    out_ << "bestmove " << format_move(r.best_move)
         << " score=" << r.score
         << " depth=" << r.depth
         << " nodes=" << r.nodes
         << '\n';
    out_.flush();
}

void HubFrontEnd::cmd_eval() {
    out_ << "eval " << evaluate(engine_.position()) << '\n';
    out_.flush();
}

void HubFrontEnd::cmd_fen() {
    out_ << "fen " << engine_.position().to_fen() << '\n';
    out_.flush();
}

}  // namespace jass
