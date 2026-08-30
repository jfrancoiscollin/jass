// SPDX-License-Identifier: AGPL-3.0-or-later
#include "test_framework.hpp"

#include "movegen.hpp"
#include "position.hpp"
#include "residual_features.hpp"
#include "search.hpp"
#include "t3_f6.hpp"
#include "tt.hpp"

#include <algorithm>
#include <cmath>
#include <bit>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <memory>
#include <string>
#include <string_view>
#include <unistd.h>

using namespace jass;

namespace {

class ConstantNetwork final : public INetwork {
public:
    explicit ConstantNetwork(int value) : value_(value) {}
    int evaluate(const Position&) const noexcept override { return value_; }
private:
    int value_;
};

Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

t3_f6::Model constant_residual(double residual) {
    t3_f6::Model m;
    m.stddev.fill(1.0);
    m.w0.assign(t3_f6::INPUT_WIDTH * t3_f6::H0, 0.0);
    m.w1.assign(t3_f6::H0 * t3_f6::H1, 0.0);
    m.w2.assign(t3_f6::H1 * t3_f6::H2, 0.0);
    m.b3 = residual;
    return m;
}

bool same_result_v4(const SearchResult& a, const SearchResult& b) {
    return a.best_move == b.best_move
        && a.score == b.score
        && a.depth == b.depth
        && a.effective_depth == b.effective_depth
        && a.completed_depth == b.completed_depth
        && a.aborted_iteration == b.aborted_iteration
        && a.stop_reason == b.stop_reason
        && a.nodes == b.nodes
        && a.cutoffs == b.cutoffs
        && a.first_move_cutoffs == b.first_move_cutoffs
        && a.pvs_researches == b.pvs_researches
        && a.moves_searched == b.moves_searched
        && a.eval_calls == b.eval_calls
        && a.scan_verify_probes == b.scan_verify_probes
        && a.scan_verify_cutoffs == b.scan_verify_cutoffs
        && a.scan_threat_reentries == b.scan_threat_reentries
        && a.qnodes == b.qnodes
        && a.qsearch_calls == b.qsearch_calls
        && a.tablebase_probes == b.tablebase_probes
        && a.tablebase_hits == b.tablebase_hits
        && a.tt_probes == b.tt_probes
        && a.tt_hits == b.tt_hits
        && a.terminal_hits == b.terminal_hits
        && a.reductions == b.reductions
        && a.extensions == b.extensions
        && a.root_order_applications == b.root_order_applications
        && a.root_order_failures == b.root_order_failures
        && a.pv == b.pv
        && a.from_book == b.from_book;
}

void test_sha256() {
    std::string path = jass_tmp_template("jass_t3_sha");
    const int fd = mkstemp(path.data());
    JASS_CHECK(fd != -1);
    if (fd == -1) return;
    close(fd);
    { std::ofstream out(path, std::ios::binary); out << "abc"; }
    std::string err;
    JASS_CHECK_EQ(t3_f6::sha256_file(path, &err),
                  std::string("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
    std::remove(path.c_str());
}

void test_exact_formula_rounding_and_clamp() {
    const Position p = parse("W:W28,31,K40:B14,22,K3");
    t3_f6::Network n(std::make_unique<ConstantNetwork>(100), constant_residual(2.4));
    JASS_CHECK_EQ(n.evaluate(p), 98);  // llround(97.6)
    JASS_CHECK_EQ(n.evaluate_from_base(p, 100), 98);
    JASS_CHECK(std::fabs(n.residual_parent(p) - 2.4) < 1e-12);

    t3_f6::Network tie(std::make_unique<ConstantNetwork>(100), constant_residual(0.5));
    JASS_CHECK_EQ(tie.evaluate(p), 100);  // llround(99.5), ties away from zero
    t3_f6::Network negative_tie(
        std::make_unique<ConstantNetwork>(-100), constant_residual(0.5));
    JASS_CHECK_EQ(negative_tie.evaluate(p), -101);
    t3_f6::Network clamp(std::make_unique<ConstantNetwork>(20000), constant_residual(-1000.0));
    JASS_CHECK_EQ(clamp.evaluate(p), 20000);
}

void test_position_only_and_colour_perspective() {
    const Position a = parse("W:W28,31,K40:B14,22,K3");
    const Position image = parse("B:W29,37,K48:B20,23,K11");
    t3_f6::Network n(std::make_unique<ConstantNetwork>(73), constant_residual(1.25));
    const auto fa = residual_features::extract(a).all_new();
    const auto fb = residual_features::extract(image).all_new();
    for (std::size_t i = 0; i < fa.size(); ++i) JASS_CHECK_EQ(fa[i], fb[i]);
    const int first = n.evaluate(a);
    (void)n.evaluate(parse("B:W31,32:B1,2"));
    JASS_CHECK_EQ(n.evaluate(a), first);
    JASS_CHECK_EQ(n.evaluate(image), first);
    JASS_CHECK_EQ(-n.evaluate(a), -first);  // exactly one negamax inversion
}

void test_f6_fast_path_matches_full_extractor_bitwise() {
    for (const std::string_view fen : {
             "W:W28,31,K40:B14,22,K3",
             "B:W31,32:B1,2",
             "W:W26,K45:B6,K10",
             "W:W28:B22,23,14"}) {
        const Position p = parse(fen);
        const auto full = residual_features::extract(p).all_new();
        residual_features::Profile profile;
        const auto fast = residual_features::extract_f6(p, &profile).all_new();
        for (std::size_t i = 0; i < full.size(); ++i) {
            JASS_CHECK_EQ(std::bit_cast<std::uint32_t>(full[i]),
                          std::bit_cast<std::uint32_t>(fast[i]));
        }
        JASS_CHECK_EQ(profile.movegen_calls,
                      2U + static_cast<std::uint64_t>(fast[12]));
    }
}

void test_exact_cache_index_validity_thread_boundary_and_lifecycle() {
    const Position empty{};
    Position empty_black{};
    empty_black.set_side_to_move(Color::Black);
    JASS_CHECK_EQ(t3_f6::Network::cache_index(empty), 26463U);
    JASS_CHECK_EQ(t3_f6::Network::cache_index(empty_black), 26028U);
    JASS_CHECK_EQ(t3_f6::Network::cache_index(
                      parse("W:W28,31,K40:B14,22,K3")),
                  33051U);

    std::string err;
    auto rejected = t3_f6::O1SearchSession::create(
        std::make_unique<ConstantNetwork>(73),
        constant_residual(1.25), 2, &err);
    JASS_CHECK(!rejected);
    JASS_CHECK(!err.empty());

    auto cached = t3_f6::O1SearchSession::create(
        std::make_unique<ConstantNetwork>(73),
        constant_residual(1.25), 1, &err);
    JASS_CHECK(cached != nullptr);
    if (!cached) return;
    auto stats = cached->cache_stats();
    JASS_CHECK_EQ(stats.lookups, 0U);

    // The default all-zero/White key must be a miss in a fresh cache despite
    // every value-initialised CacheEntry carrying the same zero key bytes.
    const double first = cached->residual_parent(empty);
    stats = cached->cache_stats();
    JASS_CHECK_EQ(std::bit_cast<std::uint64_t>(first),
                  std::bit_cast<std::uint64_t>(1.25));
    JASS_CHECK_EQ(stats.lookups, 1U);
    JASS_CHECK_EQ(stats.hits, 0U);
    JASS_CHECK_EQ(stats.misses, 1U);
    JASS_CHECK_EQ(stats.replacements, 0U);
    JASS_CHECK_EQ(stats.extract_f6_executions, 1U);

    const double second = cached->residual_parent(empty);
    stats = cached->cache_stats();
    JASS_CHECK_EQ(std::bit_cast<std::uint64_t>(first),
                  std::bit_cast<std::uint64_t>(second));
    JASS_CHECK_EQ(stats.hits, 1U);
    JASS_CHECK_EQ(stats.misses, 1U);
    JASS_CHECK_EQ(stats.extract_f6_executions, 1U);

    cached->clear_cache();
    JASS_CHECK_EQ(cached->cache_stats().lookups, 0U);
    (void)cached->residual_parent(empty);
    JASS_CHECK_EQ(cached->cache_stats().misses, 1U);

    // The actual search boundary re-checks the caller's SearchLimits instead
    // of trusting the thread count that was supplied at construction time.
    SearchLimits bad_limits;
    bad_limits.max_depth = 1;
    bad_limits.threads = 2;
    err.clear();
    const auto bad_search = cached->run_search(
        Position::start_position(), bad_limits, &err);
    JASS_CHECK(!bad_search.has_value());
    JASS_CHECK(!err.empty());

    // Destroying and reconstructing the O1 owner is the preregistered
    // root×budget lifecycle boundary: entries and counters are both empty.
    cached.reset();
    auto fresh = t3_f6::O1SearchSession::create(
        std::make_unique<ConstantNetwork>(73),
        constant_residual(1.25), 1, &err);
    JASS_CHECK(fresh != nullptr);
    if (!fresh) return;
    JASS_CHECK_EQ(fresh->cache_stats().lookups, 0U);
    (void)fresh->residual_parent(empty);
    JASS_CHECK_EQ(fresh->cache_stats().hits, 0U);
    JASS_CHECK_EQ(fresh->cache_stats().misses, 1U);

    // Cache-OFF retains the historical multithread path.
    t3_f6::Network control(
        std::make_unique<ConstantNetwork>(73), constant_residual(1.25));
    SearchLimits control_limits;
    control_limits.max_depth = 1;
    control_limits.threads = 2;
    control_limits.nnue = &control;
    const SearchResult control_result = search(
        Position::start_position(), control_limits);
    JASS_CHECK(control_result.best_move.from != 0);
    JASS_CHECK_EQ(control.cache_stats().lookups, 0U);
}

void test_exact_cache_collision_is_not_a_hit() {
    const Position a = parse("W:W10:B46");
    const Position b = parse("W:W12:B2");
    JASS_CHECK(a != b);
    JASS_CHECK_EQ(t3_f6::Network::cache_index(a), 53309U);
    JASS_CHECK_EQ(t3_f6::Network::cache_index(b), 53309U);

    auto cached = t3_f6::O1SearchSession::create(
        std::make_unique<ConstantNetwork>(0), constant_residual(3.0), 1);
    JASS_CHECK(cached != nullptr);
    if (!cached) return;
    (void)cached->residual_parent(a);
    (void)cached->residual_parent(b);
    auto stats = cached->cache_stats();
    JASS_CHECK_EQ(stats.lookups, 2U);
    JASS_CHECK_EQ(stats.hits, 0U);
    JASS_CHECK_EQ(stats.misses, 2U);
    JASS_CHECK_EQ(stats.replacements, 1U);
    JASS_CHECK_EQ(stats.extract_f6_executions, 2U);
    (void)cached->residual_parent(a);
    stats = cached->cache_stats();
    JASS_CHECK_EQ(stats.hits, 0U);
    JASS_CHECK_EQ(stats.misses, 3U);
    JASS_CHECK_EQ(stats.replacements, 2U);
}

void test_cache_preserves_complete_v4_search_result_contract() {
    const Position root = Position::start_position();
    t3_f6::Network off(
        std::make_unique<ConstantNetwork>(73), constant_residual(1.25));
    auto on = t3_f6::O1SearchSession::create(
        std::make_unique<ConstantNetwork>(73), constant_residual(1.25), 1);
    JASS_CHECK(on != nullptr);
    if (!on) return;

    SearchLimits off_limits;
    off_limits.max_depth = 2;
    off_limits.threads = 1;
    off_limits.nnue = &off;
    const SearchResult a = search(root, off_limits);

    SearchLimits on_limits;
    on_limits.max_depth = 2;
    on_limits.threads = 1;
    const auto b = on->run_search(root, on_limits);
    JASS_CHECK(b.has_value());
    if (!b) return;
    JASS_CHECK(same_result_v4(a, *b));
    JASS_CHECK(on->cache_stats().lookups > 0U);
}

void test_search_uses_exactly_one_negamax_inversion() {
    const Position root = Position::start_position();
    t3_f6::Network network(
        std::make_unique<ConstantNetwork>(73), constant_residual(1.25));
    MoveList legal;
    generate_legal_moves(root, legal);
    int expected = -30000;
    for (const Move& move : legal) {
        const Position child = root.after(move);
        MoveList replies;
        generate_legal_moves(child, replies);
        JASS_CHECK(std::none_of(replies.begin(), replies.end(),
                                [](const Move& reply) { return reply.is_capture(); }));
        expected = std::max(expected, -network.evaluate(child));
    }
    SearchLimits limits;
    limits.max_depth = 1;
    limits.nnue = &network;
    DepthOneSearchTrace trace;
    limits.depth_one_trace = &trace;
    TranspositionTable tt;
    tt.resize_mb(1);
    const SearchResult traced = search(root, limits, tt);
    JASS_CHECK_EQ(traced.score, expected);
    JASS_CHECK_EQ(trace.moves.size(), legal.size());
    int traced_max = -INF_SCORE;
    for (const auto& row : trace.moves) {
        JASS_CHECK_EQ(row.child_return, -row.root_negated_return);
        traced_max = std::max(traced_max, row.root_negated_return);
    }
    JASS_CHECK_EQ(traced_max, traced.score);

    // The null/default path must remain semantically identical.
    limits.depth_one_trace = nullptr;
    TranspositionTable control_tt;
    control_tt.resize_mb(1);
    const SearchResult control = search(root, limits, control_tt);
    JASS_CHECK_EQ(control.score, traced.score);
    JASS_CHECK_EQ(control.best_move, traced.best_move);
    JASS_CHECK_EQ(control.nodes, traced.nodes);
    JASS_CHECK_EQ(control.eval_calls, traced.eval_calls);
}

}  // namespace

void run_t3_f6_tests() {
    test_sha256();
    test_exact_formula_rounding_and_clamp();
    test_position_only_and_colour_perspective();
    test_f6_fast_path_matches_full_extractor_bitwise();
    test_exact_cache_index_validity_thread_boundary_and_lifecycle();
    test_exact_cache_collision_is_not_a_hit();
    test_cache_preserves_complete_v4_search_result_contract();
    test_search_uses_exactly_one_negamax_inversion();
}
