// SPDX-License-Identifier: AGPL-3.0-or-later
#include "test_framework.hpp"
#define JASS_P4_SYNTHETIC_FIXTURES 1
#include "p4_internal_root_rollout.hpp"

#include <limits>

using namespace jass;

namespace {

Move move(int from, int to) {
    Move result;
    result.from = static_cast<Square>(from);
    result.to = static_cast<Square>(to);
    return result;
}

SearchDecisionActionTrace action(const Move& m, int score, int alpha,
                                 SearchDecisionBound bound) {
    SearchDecisionActionTrace result;
    result.move = m;
    result.score = score;
    result.alpha = alpha;
    result.beta = 100;
    result.bound = bound;
    result.completed = true;
    result.nodes = 10;
    return result;
}

SearchDecisionTrace certifiable_trace() {
    SearchDecisionTrace trace;
    trace.root_actions = {move(1, 2), move(3, 4), move(5, 6)};
    SearchDecisionAttemptTrace attempt;
    attempt.depth = 2;
    attempt.attempt = 1;
    attempt.alpha = -100;
    attempt.beta = 100;
    attempt.score = 10;
    attempt.best_move = trace.root_actions[1];
    attempt.bound = SearchDecisionBound::Exact;
    attempt.completed = true;
    attempt.all_actions_searched = true;
    attempt.nodes_after = 30;
    // Respect the real root pass's increasing alpha. Two fabricated Exact
    // tags against inconsistent windows must not count as a positive fixture.
    attempt.actions = {
        action(trace.root_actions[0], 8, -100, SearchDecisionBound::Exact),
        action(trace.root_actions[1], 10, 8, SearchDecisionBound::Exact),
        action(trace.root_actions[2], 7, 10, SearchDecisionBound::Upper)};
    trace.attempts.push_back(attempt);
    return trace;
}

void test_certification() {
    auto trace = certifiable_trace();
    auto pair = p4::top2(trace);
    JASS_CHECK(pair.has_value());
    if (pair) {
        JASS_CHECK(pair->first == trace.root_actions[1]);
        JASS_CHECK(pair->second == trace.root_actions[0]);
    }
    for (int upper : {8, 9, 10}) {
        trace = certifiable_trace();
        trace.attempts[0].actions[2].score = upper;
        JASS_CHECK(!p4::top2(trace));
    }
    for (auto bound : {SearchDecisionBound::None, SearchDecisionBound::Lower}) {
        trace = certifiable_trace();
        trace.attempts[0].actions[1].bound = bound;
        JASS_CHECK(!p4::top2(trace));
    }
    trace = certifiable_trace();
    trace.root_actions[2] = trace.root_actions[0];
    JASS_CHECK(!p4::top2(trace));
    trace = certifiable_trace();
    trace.attempts[0].actions[2] = trace.attempts[0].actions[0];
    JASS_CHECK(!p4::top2(trace));
    trace = certifiable_trace();
    trace.attempts[0].actions.pop_back();
    JASS_CHECK(!p4::top2(trace));
    trace = certifiable_trace();
    trace.attempts[0].actions[0].move = move(7, 8);
    JASS_CHECK(!p4::top2(trace));
    trace = certifiable_trace();
    trace.attempts[0].actions[0].alpha = 9; // incompatible Exact tag
    JASS_CHECK(!p4::top2(trace));
    trace = certifiable_trace();
    trace.attempts[0].actions[1].alpha = -100; // inconsistent root history
    JASS_CHECK(!p4::top2(trace));
    trace = certifiable_trace();
    trace.attempts[0].cutoff = true;
    JASS_CHECK(!p4::top2(trace));
    trace = certifiable_trace();
    trace.attempts[0].all_actions_searched = false;
    JASS_CHECK(!p4::top2(trace));
    trace = certifiable_trace();
    trace.attempts[0].bound = SearchDecisionBound::Upper;
    JASS_CHECK(!p4::top2(trace));

    trace = certifiable_trace();
    auto later = trace.attempts[0];
    later.depth = 3;
    later.completed = false;
    later.bound = SearchDecisionBound::None;
    later.nodes_before = 30;
    later.nodes_after = 80;
    trace.attempts.push_back(later);
    pair = p4::top2(trace);
    JASS_CHECK(pair.has_value());
    if (pair) JASS_CHECK_EQ(pair->depth, 2);
    // Certification discards no work: the call still charges all 80 nodes.
    p4::Ledger ledger(100, {{"base", 100}});
    JASS_CHECK(ledger.finish("base", 80, p4::CallDisposition::Searched));
    JASS_CHECK_EQ(ledger.actual(), std::uint64_t{80});
    JASS_CHECK(ledger.complete());
    trace.attempts[1] = trace.attempts[0];
    trace.attempts[1].depth = 3;
    pair = p4::top2(trace);
    JASS_CHECK(pair.has_value());
    if (pair) JASS_CHECK_EQ(pair->depth, 3);
    trace.attempts.push_back(trace.attempts[1]);
    JASS_CHECK(!p4::top2(trace)); // ambiguous duplicate attempt identity
}

p4::DomainIdentity domain_identity() {
    p4::DomainIdentity result;
    result.code_commit = std::string(40, 'a');
    result.build_sha256 = std::string(64, 'b');
    result.driver_sha256 = std::string(64, 'c');
    result.database_manifest_sha256 = std::string(64, 'd');
    result.config_sha256 = std::string(64, 'e');
    result.database_type = "synthetic-wld";
    return result;
}

p4::DomainObservation domain_observation(const p4::DomainVerifier& verifier) {
    p4::DomainObservation result;
    result.identity = domain_identity();
    result.state = p4::BackendState::Ready;
    result.identified_cap = 7;
    result.handle_cap = 7;
    result.effective_cap = 7;
    result.epoch = verifier.epoch();
    return result;
}

void test_domain_receipts() {
    const auto expected = domain_identity();
    p4::DomainVerifier verifier(expected);
    auto observed = domain_observation(verifier);
    JASS_CHECK(verifier.publish(observed));
    const auto snapshot = verifier.snapshot();
    JASS_CHECK(snapshot.has_value());
    if (!snapshot) return;
    JASS_CHECK(verifier.assess(*snapshot, 8) == p4::DomainClass::Outside);
    JASS_CHECK(verifier.assess(*snapshot, 7) == p4::DomainClass::Covered);
    JASS_CHECK(verifier.assess(*snapshot, 6) == p4::DomainClass::Covered);
    JASS_CHECK(verifier.assess(*snapshot, 0) == p4::DomainClass::Invalid);
    JASS_CHECK(verifier.assess(*snapshot, 51) == p4::DomainClass::Invalid);
    auto altered = *snapshot;
    altered.effective_cap = 6;
    JASS_CHECK(verifier.assess(altered, 8) == p4::DomainClass::Invalid);

    verifier.invalidate();
    JASS_CHECK(!verifier.snapshot());
    JASS_CHECK(verifier.assess(*snapshot, 8) == p4::DomainClass::Invalid);
    observed = domain_observation(verifier);
    JASS_CHECK(verifier.publish(observed));
    JASS_CHECK(verifier.assess(*snapshot, 8) == p4::DomainClass::Invalid);
    // Even a second publication of the same descriptor cannot revive a
    // previously issued snapshot without a fresh lifecycle observation.
    JASS_CHECK(!verifier.publish(observed));
    JASS_CHECK(!verifier.snapshot());

    for (auto state : {p4::BackendState::Disabled, p4::BackendState::Missing,
                       p4::BackendState::IdentifyFailure,
                       p4::BackendState::OpenFailure, p4::BackendState::IoFailure,
                       p4::BackendState::DriverFailure}) {
        p4::DomainVerifier candidate(expected);
        auto bad = domain_observation(candidate);
        bad.state = state;
        JASS_CHECK(!candidate.publish(bad));
        JASS_CHECK(!candidate.snapshot());
    }
    const std::string p4::DomainIdentity::* fields[] = {
        &p4::DomainIdentity::code_commit, &p4::DomainIdentity::build_sha256,
        &p4::DomainIdentity::driver_sha256,
        &p4::DomainIdentity::database_manifest_sha256,
        &p4::DomainIdentity::config_sha256,
        &p4::DomainIdentity::database_type};
    for (auto field : fields) {
        p4::DomainVerifier candidate(expected);
        auto bad = domain_observation(candidate);
        bad.identity.*field += "x";
        JASS_CHECK(!candidate.publish(bad));
    }
    for (int bad_case = 0; bad_case < 8; ++bad_case) {
        p4::DomainVerifier candidate(expected);
        auto bad = domain_observation(candidate);
        if (bad_case == 0) bad.identified_cap = 0;
        if (bad_case == 1) bad.handle_cap = 0;
        if (bad_case == 2) bad.effective_cap = 6;
        if (bad_case == 3) ++bad.epoch;
        if (bad_case == 4) ++bad.identity.schema_version;
        if (bad_case == 5) bad.handle_cap = 8; // exceeds identified domain
        if (bad_case == 6) bad.handle_cap = 6; // effective cap not reconciled
        if (bad_case == 7) bad.state = p4::BackendState::Unknown;
        JASS_CHECK(!candidate.publish(bad));
    }
    p4::DomainVerifier empty_anchor({});
    JASS_CHECK(!empty_anchor.publish(domain_observation(empty_anchor)));
}

p4::ScoreContract score_contract() {
    p4::ScoreContract result;
    result.artifact_sha256 = std::string(64, 'a');
    result.implementation_commit = std::string(40, 'b');
    result.build_sha256 = std::string(64, 'c');
    result.config_sha256 = std::string(64, 'd');
    result.range_proof_sha256 = std::string(64, 'e');
    result.terminal_order_sha256 = std::string(64, 'f');
    result.static_min = -100;
    result.static_max = 100;
    result.terminal_loss_highest = -29000;
    result.terminal_win_lowest = 29000;
    result.epoch = 1;
    return result;
}

void test_score_receipts_and_arithmetic() {
    const auto expected = score_contract();
    JASS_CHECK(p4::verify_score_contract(expected, expected, 1));
    JASS_CHECK(!p4::verify_score_contract(expected, expected, 2));
    const std::string p4::ScoreContract::* fields[] = {
        &p4::ScoreContract::artifact_sha256,
        &p4::ScoreContract::implementation_commit,
        &p4::ScoreContract::build_sha256, &p4::ScoreContract::config_sha256,
        &p4::ScoreContract::range_proof_sha256,
        &p4::ScoreContract::terminal_order_sha256};
    for (auto field : fields) {
        auto observed = expected;
        observed.*field += "x";
        JASS_CHECK(!p4::verify_score_contract(expected, observed, 1));
    }
    auto bad = expected;
    bad.static_max = bad.terminal_win_lowest;
    JASS_CHECK(!p4::verify_score_contract(bad, bad, 1));
    bad = expected;
    bad.static_min = bad.terminal_loss_highest;
    JASS_CHECK(!p4::verify_score_contract(bad, bad, 1));
    bad = expected;
    bad.static_min = 101;
    JASS_CHECK(!p4::verify_score_contract(bad, bad, 1));
    bad = expected;
    bad.perspective = p4::ScorePerspective::WhiteAbsolute;
    JASS_CHECK(!p4::verify_score_contract(bad, bad, 1));
    bad = expected;
    bad.range_proof_sha256.clear();
    JASS_CHECK(!p4::verify_score_contract(bad, bad, 1));

    JASS_CHECK_EQ(p4::root_score(Color::White, Color::Black,
                                std::numeric_limits<int>::min()),
                  -static_cast<std::int64_t>(std::numeric_limits<int>::min()));
    const auto half = p4::mean2(1, 0);
    const auto zero = p4::mean2(0, 0);
    JASS_CHECK(half && zero && half->numerator > zero->numerator);
    constexpr auto hi = std::numeric_limits<std::int64_t>::max();
    constexpr auto lo = std::numeric_limits<std::int64_t>::min();
    JASS_CHECK(!p4::mean2(hi, 1));
    JASS_CHECK(!p4::mean2(lo, -1));
    const auto balanced = p4::mean2(hi, lo);
    JASS_CHECK(balanced && balanced->numerator == -1);
}

void test_ledger() {
    const auto plan = p4::treatment_plan(128);
    JASS_CHECK_EQ(plan.size(), std::size_t{65});
    p4::Ledger ledger(128, plan);
    JASS_CHECK_EQ(ledger.submitted(), std::uint64_t{128});
    JASS_CHECK(!ledger.complete());
    JASS_CHECK(ledger.finish("base", 50, p4::CallDisposition::Searched));
    for (std::size_t index = 1; index < plan.size(); ++index) {
        JASS_CHECK(ledger.finish(plan[index].id, 0, p4::CallDisposition::Unused));
    }
    JASS_CHECK(ledger.complete());
    JASS_CHECK_EQ(ledger.actual(), std::uint64_t{50});
    JASS_CHECK_EQ(ledger.slack(), std::uint64_t{78});
    JASS_CHECK(!ledger.finish("base", 1, p4::CallDisposition::Searched));
    JASS_CHECK(!ledger.complete());

    p4::Ledger overspend(128, plan);
    JASS_CHECK(!overspend.finish("base", 65, p4::CallDisposition::Searched));
    p4::Ledger zero_search(128, plan);
    JASS_CHECK(!zero_search.finish("base", 0, p4::CallDisposition::Searched));
    p4::Ledger hidden(128, plan);
    JASS_CHECK(!hidden.finish("unplanned", 1, p4::CallDisposition::Searched));
    p4::Ledger fake_skip(128, plan);
    JASS_CHECK(!fake_skip.finish("base", 1, p4::CallDisposition::Unused));
    p4::Ledger missing(128, plan);
    JASS_CHECK(missing.finish("base", 0, p4::CallDisposition::Searched));
    JASS_CHECK(!missing.complete());

    bool rejected = false;
    try {
        p4::Ledger invalid(128, {{"base", 64}, {"base", 64}});
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    JASS_CHECK(rejected);
    rejected = false;
    try {
        p4::Ledger invalid(128, {{"underallocated", 127}});
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    JASS_CHECK(rejected);
    rejected = false;
    constexpr auto max = std::numeric_limits<std::uint64_t>::max();
    try {
        p4::Ledger invalid(max, {{"first", max}, {"second", 1}});
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    JASS_CHECK(rejected);
    p4::Ledger edge(max, {{"only", max}});
    JASS_CHECK(edge.finish("only", max, p4::CallDisposition::Searched));
    JASS_CHECK(edge.complete());
    JASS_CHECK_EQ(edge.slack(), std::uint64_t{0});
}

void test_seed_binding() {
    const p4::SeedIdentity seed{"v1", "run", "case", Color::White, move(1, 2), 0, 0};
    const auto encoded = p4::encode_seed(seed);
    JASS_CHECK_EQ(p4::seed_v1(seed), p4::seed_v1(seed));
    for (int field = 0; field < 7; ++field) {
        auto changed = seed;
        if (field == 0) changed.contract += "x";
        if (field == 1) changed.run += "x";
        if (field == 2) changed.case_id += "x";
        if (field == 3) changed.color = Color::Black;
        if (field == 4) changed.root_move.to = static_cast<Square>(3);
        if (field == 5) ++changed.rollout;
        if (field == 6) ++changed.ply;
        JASS_CHECK(p4::encode_seed(changed) != encoded);
        JASS_CHECK(p4::seed_v1(changed) != p4::seed_v1(seed));
    }
    auto a = seed;
    auto b = seed;
    a.contract = "ab"; a.run = "c";
    b.contract = "a"; b.run = "bc";
    JASS_CHECK(p4::encode_seed(a) != p4::encode_seed(b));
}

}  // namespace

void run_p4_internal_root_rollout_tests() {
    test_certification();
    test_domain_receipts();
    test_score_receipts_and_arithmetic();
    test_ledger();
    test_seed_binding();
}
