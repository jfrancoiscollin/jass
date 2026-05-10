// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Tests for the HUB-flavoured CLI front-end: move parsing/formatting and
// a few full-loop sessions piped through string streams.

#include "test_framework.hpp"

#include "hub.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "types.hpp"

#include <chrono>
#include <sstream>
#include <string>
#include <string_view>

using namespace jass;

namespace {

Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

bool contains(std::string_view haystack, std::string_view needle) {
    return haystack.find(needle) != std::string_view::npos;
}

// -----------------------------------------------------------------------------
// parse_move / format_move
// -----------------------------------------------------------------------------
void test_parse_move_quiet_from_start() {
    const Position p = Position::start_position();
    const auto m = parse_move(p, "31-26");
    JASS_CHECK(m.has_value());
    JASS_CHECK_EQ(m->from, static_cast<Square>(31));
    JASS_CHECK_EQ(m->to,   static_cast<Square>(26));
    JASS_CHECK(m->is_quiet());
}

void test_parse_move_capture() {
    const Position p = parse("W:W28:B22");
    const auto m = parse_move(p, "28x17");
    JASS_CHECK(m.has_value());
    JASS_CHECK(m->is_capture());
    JASS_CHECK_EQ(m->captures[0], static_cast<Square>(22));
}

void test_parse_move_multi_jump_takes_final_square() {
    // Multi-jump on a single line: parse_move keeps only the last token as
    // the destination. The captured squares are recovered from the legal-
    // move list (W:W28:B22,23,14 has the unique 28x..x10 chain).
    const Position p = parse("W:W28:B22,23,14");
    const auto m = parse_move(p, "28x19x10");
    JASS_CHECK(m.has_value());
    JASS_CHECK_EQ(m->from, static_cast<Square>(28));
    JASS_CHECK_EQ(m->to,   static_cast<Square>(10));
    JASS_CHECK_EQ(m->num_captures, 2);
}

void test_parse_move_rejects_garbage() {
    const Position p = Position::start_position();
    JASS_CHECK(!parse_move(p, "").has_value());
    JASS_CHECK(!parse_move(p, "31").has_value());
    JASS_CHECK(!parse_move(p, "31-foo").has_value());
    // Legal syntax but illegal move from this position:
    JASS_CHECK(!parse_move(p, "1-2").has_value());
    // Square out of range:
    JASS_CHECK(!parse_move(p, "31-99").has_value());
}

void test_format_move_quiet_and_capture() {
    Move quiet;
    quiet.from = 31;
    quiet.to   = 26;
    JASS_CHECK_EQ(format_move(quiet), std::string{"31-26"});

    Move cap;
    cap.from = 28;
    cap.to   = 17;
    cap.num_captures = 1;
    cap.captures[0]  = 22;
    JASS_CHECK_EQ(format_move(cap), std::string{"28x17"});
}

// -----------------------------------------------------------------------------
// Full HUB sessions through string streams
// -----------------------------------------------------------------------------
std::string drive_session(std::string_view script) {
    std::istringstream in{std::string{script}};
    std::ostringstream out;
    HubFrontEnd hub(in, out);
    hub.run();
    return out.str();
}

void test_hub_hello_emits_id_and_ready() {
    const std::string out = drive_session("hello\n");
    JASS_CHECK(contains(out, "id"));
    JASS_CHECK(contains(out, "name=Jass"));
    JASS_CHECK(contains(out, "ready"));
}

void test_hub_position_fen_then_fen_round_trip() {
    const std::string out = drive_session(
        "position fen W:W31-50:B1-20\n"
        "fen\n");
    JASS_CHECK(contains(out, "ok"));
    JASS_CHECK(contains(out, "fen W:"));
}

void test_hub_apply_then_go_yields_bestmove() {
    const std::string out = drive_session(
        "position startpos\n"
        "apply 31-26\n"
        "go depth 2\n");
    JASS_CHECK(contains(out, "bestmove"));
}

void test_hub_unknown_command_reports_error() {
    const std::string out = drive_session("zzzbogus\n");
    JASS_CHECK(contains(out, "error"));
}

void test_hub_quit_terminates_loop() {
    // Anything after `quit` must not be processed: no `ok` emitted because
    // `position startpos` would otherwise produce one.
    const std::string out = drive_session("quit\nposition startpos\n");
    JASS_CHECK(!contains(out, "ok"));
}

// -----------------------------------------------------------------------------
// Time control & external stop
// -----------------------------------------------------------------------------
void test_hub_movetime_returns_within_budget() {
    using namespace std::chrono;
    const auto t0 = steady_clock::now();
    const std::string out = drive_session("go movetime 50\n");
    const auto elapsed = duration_cast<milliseconds>(steady_clock::now() - t0).count();
    JASS_CHECK(contains(out, "bestmove"));
    // Generous upper bound so the test stays robust under load: budget +
    // a healthy slack for the ~1024-node poll granularity.
    JASS_CHECK(elapsed < 500);
}

void test_hub_infinite_then_stop() {
    // `go infinite` spawns a worker that searches until the stop flag is
    // set. `stop` sets the flag and joins the worker; only then does it
    // return, so the `bestmove` line is guaranteed to be in the output by
    // the time `drive_session` returns.
    const std::string out = drive_session("go infinite\nstop\n");
    JASS_CHECK(contains(out, "bestmove"));
}

}  // namespace

void run_hub_tests() {
    test_parse_move_quiet_from_start();
    test_parse_move_capture();
    test_parse_move_multi_jump_takes_final_square();
    test_parse_move_rejects_garbage();
    test_format_move_quiet_and_capture();

    test_hub_hello_emits_id_and_ready();
    test_hub_position_fen_then_fen_round_trip();
    test_hub_apply_then_go_yields_bestmove();
    test_hub_unknown_command_reports_error();
    test_hub_quit_terminates_loop();

    test_hub_movetime_returns_within_budget();
    test_hub_infinite_then_stop();
}
