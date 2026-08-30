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
    JASS_CHECK_EQ(n.evaluate(p), 98);
    JASS_CHECK_EQ(n.evaluate_from_base(p, 100), 98);
    JASS_CHECK(std::fabs(n.residual_parent(p) - 2.4) < 1e-12);
    t3_f6::Network tie(std::make_unique<ConstantNetwork>(100), constant_residual(0.5));
    JASS_CHECK_EQ(tie.evaluate(p), 100);
    t3_f6::Network negative_tie(std::make_unique<ConstantNetwork>(-100), constant_residual(0.5));
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
    JASS_CHECK_EQ(-n.evaluate(a), -first);
}

void test_f6_fast_path_matches_full_extractor_bitwise() {
    for (const std::string_view fen : {"W:W28,31,K40:B14,22,K3","B:W31,32:B1,2","W:W26,K45:B6,K10","W:W28:B22,23,14"}) {
        const Position p = parse(fen);
        const auto full = residual_features::extract(p).all_new();
        residual_features::Profile profile;
        const auto fast = residual_features::extract_f6(p, &profile).all_new();
        for (std::size_t i = 0; i < full.size(); ++i)
            JASS_CHECK_EQ(std::bit_cast<std::uint32_t>(full[i]), std::bit_cast<std::uint32_t>(fast[i]));
        JASS_CHECK_EQ(profile.movegen_calls, 2U + static_cast<std::uint64_t>(fast[12]));
    }
}

void test_exact_cache_index_and_validity() {
    const Position empty{};
    Position empty_black{}; empty_black.set_side_to_move(Color::Black);
    JASS_CHECK_EQ(t3_f6::Network::cache_index(empty), 26463U);
    JASS_CHECK_EQ(t3_f6::Network::cache_index(empty_black), 26028U);
    JASS_CHECK_EQ(t3_f6::Network::cache_index(parse("W:W28,31,K40:B14,22,K3")), 33051U);

    std::string err;
    auto rejected = t3_f6::Network::make_o1_cached(
        std::make_unique<ConstantNetwork>(73), constant_residual(1.25), 2, &err);
    JASS_CHECK(!rejected);
    JASS_CHECK(!err.empty());

    auto cached = t3_f6::Network::make_o1_cached(
        std::make_unique<ConstantNetwork>(73), constant_residual(1.25), 1, &err);
    JASS_CHECK(cached != nullptr);
    if (!cached) return;
    JASS_CHECK(cached->cache_enabled());
    JASS_CHECK(cached->thread_contract_ok(1));
    JASS_CHECK(!cached->thread_contract_ok(2));
    auto stats = cached->cache_stats();
    JASS_CHECK_EQ(stats.lookups, 0U);

    const double first = cached->residual_parent(empty);
    stats = cached->cache_stats();
    JASS_CHECK_EQ(std::bit_cast<std::uint64_t>(first), std::bit_cast<std::uint64_t>(1.25));
    JASS_CHECK_EQ(stats.lookups, 1U); JASS_CHECK_EQ(stats.hits, 0U); JASS_CHECK_EQ(stats.misses, 1U);
    JASS_CHECK_EQ(stats.replacements, 0U); JASS_CHECK_EQ(stats.extract_f6_executions, 1U);
    const double second = cached->residual_parent(empty);
    stats = cached->cache_stats();
    JASS_CHECK_EQ(std::bit_cast<std::uint64_t>(first), std::bit_cast<std::uint64_t>(second));
    JASS_CHECK_EQ(stats.hits, 1U); JASS_CHECK_EQ(stats.misses, 1U); JASS_CHECK_EQ(stats.extract_f6_executions, 1U);
    cached->clear_cache();
    JASS_CHECK_EQ(cached->cache_stats().lookups, 0U);
    (void)cached->residual_parent(empty);
    JASS_CHECK_EQ(cached->cache_stats().misses, 1U);

    t3_f6::Network control(std::make_unique<ConstantNetwork>(73), constant_residual(1.25));
    JASS_CHECK(!control.cache_enabled()); JASS_CHECK(control.thread_contract_ok(8));
    (void)control.residual_parent(empty);
    JASS_CHECK_EQ(control.cache_stats().lookups, 0U);
}

void test_exact_cache_collision_is_not_a_hit() {
    const Position a = parse("W:W10:B46");
    const Position b = parse("W:W12:B2");
    JASS_CHECK(a != b);
    JASS_CHECK_EQ(t3_f6::Network::cache_index(a), 53309U);
    JASS_CHECK_EQ(t3_f6::Network::cache_index(b), 53309U);
    auto cached = t3_f6::Network::make_o1_cached(
        std::make_unique<ConstantNetwork>(0), constant_residual(3.0), 1);
    JASS_CHECK(cached != nullptr); if (!cached) return;
    (void)cached->residual_parent(a); (void)cached->residual_parent(b);
    auto stats = cached->cache_stats();
    JASS_CHECK_EQ(stats.lookups, 2U); JASS_CHECK_EQ(stats.hits, 0U); JASS_CHECK_EQ(stats.misses, 2U);
    JASS_CHECK_EQ(stats.replacements, 1U); JASS_CHECK_EQ(stats.extract_f6_executions, 2U);
    (void)cached->residual_parent(a);
    stats = cached->cache_stats();
    JASS_CHECK_EQ(stats.hits, 0U); JASS_CHECK_EQ(stats.misses, 3U); JASS_CHECK_EQ(stats.replacements, 2U);
}

void test_cache_preserves_search_result() {
    const Position root = Position::start_position();
    t3_f6::Network off(std::make_unique<ConstantNetwork>(73), constant_residual(1.25));
    auto on = t3_f6::Network::make_o1_cached(
        std::make_unique<ConstantNetwork>(73), constant_residual(1.25), 1);
    JASS_CHECK(on != nullptr); if (!on) return;
    SearchLimits limits; limits.max_depth = 2; limits.threads = 1;
    TranspositionTable off_tt; off_tt.resize_mb(1); limits.nnue = &off;
    const SearchResult a = search(root, limits, off_tt);
    TranspositionTable on_tt; on_tt.resize_mb(1); limits.nnue = on.get();
    const SearchResult b = search(root, limits, on_tt);
    JASS_CHECK_EQ(a.best_move,b.best_move); JASS_CHECK_EQ(a.score,b.score); JASS_CHECK_EQ(a.depth,b.depth);
    JASS_CHECK_EQ(a.effective_depth,b.effective_depth); JASS_CHECK_EQ(a.completed_depth,b.completed_depth);
    JASS_CHECK_EQ(a.nodes,b.nodes); JASS_CHECK_EQ(a.cutoffs,b.cutoffs); JASS_CHECK_EQ(a.first_move_cutoffs,b.first_move_cutoffs);
    JASS_CHECK_EQ(a.pvs_researches,b.pvs_researches); JASS_CHECK_EQ(a.moves_searched,b.moves_searched);
    JASS_CHECK_EQ(a.eval_calls,b.eval_calls); JASS_CHECK_EQ(a.qnodes,b.qnodes); JASS_CHECK_EQ(a.qsearch_calls,b.qsearch_calls);
    JASS_CHECK_EQ(a.tt_probes,b.tt_probes); JASS_CHECK_EQ(a.tt_hits,b.tt_hits); JASS_CHECK_EQ(a.terminal_hits,b.terminal_hits);
    JASS_CHECK_EQ(a.reductions,b.reductions); JASS_CHECK_EQ(a.extensions,b.extensions); JASS_CHECK_EQ(a.pv,b.pv);
    JASS_CHECK_EQ(a.from_book,b.from_book);
}

void test_search_uses_exactly_one_negamax_inversion() {
    const Position root = Position::start_position();
    t3_f6::Network network(std::make_unique<ConstantNetwork>(73), constant_residual(1.25));
    MoveList legal; generate_legal_moves(root, legal); int expected = -30000;
    for (const Move& move : legal) {
        const Position child = root.after(move); MoveList replies; generate_legal_moves(child, replies);
        JASS_CHECK(std::none_of(replies.begin(), replies.end(), [](const Move& reply){return reply.is_capture();}));
        expected = std::max(expected, -network.evaluate(child));
    }
    SearchLimits limits; limits.max_depth = 1; limits.nnue = &network; DepthOneSearchTrace trace; limits.depth_one_trace = &trace;
    TranspositionTable tt; tt.resize_mb(1); const SearchResult traced = search(root, limits, tt);
    JASS_CHECK_EQ(traced.score, expected); JASS_CHECK_EQ(trace.moves.size(), legal.size());
    int traced_max = -INF_SCORE;
    for (const auto& row : trace.moves) { JASS_CHECK_EQ(row.child_return, -row.root_negated_return); traced_max = std::max(traced_max, row.root_negated_return); }
    JASS_CHECK_EQ(traced_max, traced.score);
    limits.depth_one_trace = nullptr; TranspositionTable control_tt; control_tt.resize_mb(1);
    const SearchResult control = search(root, limits, control_tt);
    JASS_CHECK_EQ(control.score,traced.score); JASS_CHECK_EQ(control.best_move,traced.best_move);
    JASS_CHECK_EQ(control.nodes,traced.nodes); JASS_CHECK_EQ(control.eval_calls,traced.eval_calls);
}

}  // namespace

void run_t3_f6_tests() {
    test_sha256(); test_exact_formula_rounding_and_clamp(); test_position_only_and_colour_perspective();
    test_f6_fast_path_matches_full_extractor_bitwise(); test_exact_cache_index_and_validity();
    test_exact_cache_collision_is_not_a_hit(); test_cache_preserves_search_result();
    test_search_uses_exactly_one_negamax_inversion();
}
