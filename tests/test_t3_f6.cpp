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
    test_search_uses_exactly_one_negamax_inversion();
}
