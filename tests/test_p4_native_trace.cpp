// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Synthetic-only native search fixture for the P4 trace selection boundary.

#include "test_framework.hpp"

#define JASS_P4_SYNTHETIC_FIXTURES 1
#include "p4_internal_root_rollout.hpp"

#include "movegen.hpp"
#include "tt.hpp"
#include "egdb_bridge.hpp"

#include <cstdint>
#include <cstdlib>
#include <cstdio>

using namespace jass;

namespace {

constexpr std::uint64_t kSyntheticRolloutNodes = 16'384;
constexpr std::uint64_t kBaseCap = kSyntheticRolloutNodes / 2;
constexpr int kFixtureDepth = 6;

struct TraceWorkTotals {
    std::uint64_t attempt_nodes{0};
    std::uint64_t attempt_evals{0};
    std::uint64_t attempt_pvs{0};
    std::uint64_t action_nodes{0};
    std::uint64_t action_evals{0};
    std::uint64_t action_pvs{0};
};

TraceWorkTotals check_trace_receipts(const SearchDecisionTrace& trace) {
    TraceWorkTotals totals;
    std::uint64_t previous_nodes = 0;
    std::uint64_t previous_evals = 0;
    std::uint64_t previous_pvs = 0;

    for (const SearchDecisionAttemptTrace& attempt : trace.attempts) {
        JASS_CHECK_EQ(attempt.nodes_before, previous_nodes);
        JASS_CHECK_EQ(attempt.eval_calls_before, previous_evals);
        JASS_CHECK_EQ(attempt.pvs_researches_before, previous_pvs);
        JASS_CHECK(attempt.nodes_after >= attempt.nodes_before);
        JASS_CHECK(attempt.eval_calls_after >= attempt.eval_calls_before);
        JASS_CHECK(attempt.pvs_researches_after
                   >= attempt.pvs_researches_before);
        JASS_CHECK(attempt.nodes_after <= kBaseCap);

        const std::uint64_t attempt_nodes =
            attempt.nodes_after - attempt.nodes_before;
        const std::uint64_t attempt_evals =
            attempt.eval_calls_after - attempt.eval_calls_before;
        const std::uint64_t attempt_pvs =
            attempt.pvs_researches_after - attempt.pvs_researches_before;
        totals.attempt_nodes += attempt_nodes;
        totals.attempt_evals += attempt_evals;
        totals.attempt_pvs += attempt_pvs;

        std::uint64_t action_nodes = 0;
        std::uint64_t action_evals = 0;
        std::uint64_t action_pvs = 0;
        for (const SearchDecisionActionTrace& action : attempt.actions) {
            action_nodes += action.nodes;
            action_evals += action.eval_calls;
            action_pvs += action.pvs_researches;
        }
        // Actions partition one attempt's work.  Do not combine this sum
        // with the attempt delta when checking the final search receipt.
        JASS_CHECK_EQ(action_nodes, attempt_nodes);
        JASS_CHECK_EQ(action_evals, attempt_evals);
        JASS_CHECK_EQ(action_pvs, attempt_pvs);
        totals.action_nodes += action_nodes;
        totals.action_evals += action_evals;
        totals.action_pvs += action_pvs;

        previous_nodes = attempt.nodes_after;
        previous_evals = attempt.eval_calls_after;
        previous_pvs = attempt.pvs_researches_after;
    }

    JASS_CHECK_EQ(totals.attempt_nodes, trace.nodes);
    JASS_CHECK_EQ(totals.attempt_evals, trace.eval_calls);
    JASS_CHECK_EQ(totals.attempt_pvs, trace.pvs_researches);
    JASS_CHECK_EQ(totals.action_nodes, trace.nodes);
    JASS_CHECK_EQ(totals.action_evals, trace.eval_calls);
    JASS_CHECK_EQ(totals.action_pvs, trace.pvs_researches);
    return totals;
}

bool contains_move(const MoveList& moves, const Move& move) {
    for (const Move& legal : moves) {
        if (legal == move) return true;
    }
    return false;
}

void test_p4_native_trace_fixture() {
    // search() lazily initializes EGDB from these environment variables.
    // Do not let this synthetic fixture read a configured database or inherit
    // a live handle initialized by an earlier test.
    const bool configured_egdb = [] {
        const char* const names[] = {
            "JASS_EGDB_PATH", "JASS_EGDB_MTC_PATH"};
        for (const char* name : names) {
            const char* value = std::getenv(name);
            if (value != nullptr && value[0] != '\0') return true;
        }
        return false;
    }();
    if (configured_egdb || egdb::available() || egdb::available_mtc()) {
        std::printf(
            "P4_NATIVE_TRACE_FIXTURE {\"status\":\"SKIPPED_EXTERNAL_EGDB\"}\n");
        return;
    }

    const Position position = Position::start_position();
    SearchLimits off_limits;
    off_limits.max_depth = kFixtureDepth;
    off_limits.max_nodes = kBaseCap;
    off_limits.node_limit_mode = NodeLimitMode::Exact;
    off_limits.threads = 1;
    off_limits.nnue = nullptr;

    TranspositionTable off_tt;
    off_tt.resize_mb(off_limits.tt_mb);
    const SearchResult off = search(position, off_limits, off_tt);

    SearchDecisionTrace trace;
    SearchLimits on_limits = off_limits;
    on_limits.search_decision_trace = &trace;
    TranspositionTable on_tt;
    on_tt.resize_mb(on_limits.tt_mb);
    const SearchResult on = search(position, on_limits, on_tt);

    const bool identity = off.best_move == on.best_move
                       && off.score == on.score
                       && off.nodes == on.nodes
                       && static_cast<std::uint8_t>(off.stop_reason)
                          == static_cast<std::uint8_t>(on.stop_reason);
    JASS_CHECK(identity);
    // Exact is a ceiling, not padding: a completed fixed-depth search may
    // finish before consuming the whole cap.
    JASS_CHECK(on.nodes > 0 && on.nodes <= kBaseCap);
    JASS_CHECK_EQ(trace.nodes, on.nodes);
    JASS_CHECK(trace.nodes <= kBaseCap);
    JASS_CHECK(static_cast<std::uint8_t>(trace.stop_reason)
               == static_cast<std::uint8_t>(on.stop_reason));

    const TraceWorkTotals totals = check_trace_receipts(trace);
    const std::optional<p4::Pair> pair = p4::top2(trace);
    MoveList legal;
    generate_legal_moves(position, legal);
    if (pair) {
        JASS_CHECK(pair->first != pair->second);
        JASS_CHECK(contains_move(legal, pair->first));
        JASS_CHECK(contains_move(legal, pair->second));
    }

    std::printf(
        "P4_NATIVE_TRACE_FIXTURE {\"status\":\"EXECUTED\","
        "\"R\":%llu,\"base_cap\":%llu,"
        "\"depth\":%d,\"identity\":%s,\"node_limit\":\"exact\","
        "\"nodes\":%llu,\"stop\":%u,\"top2\":%s,"
        "\"attempts\":%zu,\"actions\":%zu,\"trace_work_nodes\":%llu}\n",
        static_cast<unsigned long long>(kSyntheticRolloutNodes),
        static_cast<unsigned long long>(kBaseCap), kFixtureDepth,
        identity ? "true" : "false",
        static_cast<unsigned long long>(on.nodes),
        static_cast<unsigned>(on.stop_reason), pair ? "true" : "false",
        trace.attempts.size(), trace.root_actions.size(),
        static_cast<unsigned long long>(totals.attempt_nodes));
}

}  // namespace

void run_p4_native_trace_tests() {
    test_p4_native_trace_fixture();
}
