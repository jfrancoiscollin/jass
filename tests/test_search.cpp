// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Functional tests for the alpha-beta search. The handcrafted scenarios
// pin down the contract that the rest of the engine relies on:
//   - the returned move is always one produced by `generate_legal_moves`
//   - a side with no legal moves is reported as mated
//   - on a position that *forces* a capture, the search returns that
//     capture (this implicitly checks the search/movegen integration)
//   - winning material is reflected in a positive score
//   - the search completes its requested depth and reports node counts

#include "test_framework.hpp"

#include "eval.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "search.hpp"
#include "selfplay_exploration.hpp"
#include "selfplay_node_budget.hpp"
#include "tt.hpp"
#include "types.hpp"
#include "zobrist.hpp"

#include <algorithm>
#include <limits>
#include <stdexcept>
#include <string_view>

using namespace jass;

namespace {

Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

bool list_contains(const MoveList& ml, const Move& m) {
    for (const auto& x : ml) if (x == m) return true;
    return false;
}

template <class Fn>
bool throws_invalid_argument(Fn&& fn) {
    try {
        fn();
    } catch (const std::invalid_argument&) {
        return true;
    }
    return false;
}

// -----------------------------------------------------------------------------
// Evaluation
// -----------------------------------------------------------------------------
// The exact PSQT values are implementation details, so the tests below check
// invariants (sign, ordering, dominance of material over positional terms)
// instead of pinning specific numbers.
void test_eval_start_is_near_zero() {
    const Position p = Position::start_position();
    // Material is identical and the PSQT is mirrored between the colours,
    // so the start-position eval is dominated by the small tempo bonus.
    const int e = evaluate(p);
    JASS_CHECK(e > -2 * MAN_VALUE / 5);  // |e| < 40
    JASS_CHECK(e <  2 * MAN_VALUE / 5);
}

void test_eval_material_dominates_positional() {
    // Removing one black man from the start position must improve white's
    // eval by clearly more than any positional swing in the PSQT.
    const Position p_full   = Position::start_position();
    const Position p_minus  = parse("W:W31-50:B1-19");  // black is missing 20

    const int e_full  = evaluate(p_full);
    const int e_minus = evaluate(p_minus);
    JASS_CHECK(e_minus - e_full > MAN_VALUE / 2);
    // And the magnitude shouldn't blow up to a king's value either.
    JASS_CHECK(e_minus - e_full < KING_VALUE);
}

void test_eval_stm_flips_sign() {
    // Identical board, only side-to-move differs: signs flip.
    const Position w = parse("W:W31-50:B1-15");
    const Position b = parse("B:W31-50:B1-15");
    JASS_CHECK(evaluate(w) > MAN_VALUE);
    JASS_CHECK(evaluate(b) < -MAN_VALUE);
}

void test_eval_king_more_valuable_than_man() {
    const Position pm = parse("W:W31:B1");
    const Position pk = parse("W:WK31:B1");
    // Replacing white's man with a king strictly improves white's eval by
    // at least KING_VALUE - MAN_VALUE minus a small PSQT slack.
    JASS_CHECK(evaluate(pk) - evaluate(pm) >= KING_VALUE - MAN_VALUE - 50);
}

void test_eval_advancement_bonus() {
    // Pushing a single white man one rank toward promotion should never
    // decrease its eval (in an otherwise identical context).
    const Position back = parse("W:W31:B1");   // row 6
    const Position fwd  = parse("W:W26:B1");   // row 5 — closer to promotion
    JASS_CHECK(evaluate(fwd) > evaluate(back));
}

void test_eval_edge_file_penalty() {
    // A white man on the edge column should score less than the same
    // material configuration with the man on a central column. We compare
    // square 26 (col 0, edge) with square 28 (col 4, central) — both on
    // the same row 5 so advancement is identical.
    const Position edge   = parse("W:W26:B1");
    const Position centre = parse("W:W28:B1");
    JASS_CHECK(evaluate(centre) > evaluate(edge));
}

void test_eval_supports_score_higher_than_isolated() {
    // Two white men supporting each other diagonally vs two isolated men
    // on the same row. Material is identical; the supported pair must
    // score strictly higher.
    const Position supported = parse("W:W37,42:B1");   // 42 is SE of 37
    const Position isolated  = parse("W:W36,40:B1");   // no diagonal link
    JASS_CHECK(evaluate(supported) > evaluate(isolated));
}

// -----------------------------------------------------------------------------
// Search
// -----------------------------------------------------------------------------
void test_search_returns_legal_move_from_start() {
    const Position p = Position::start_position();

    SearchLimits lim;
    lim.max_depth = 4;
    const SearchResult r = search(p, lim);

    JASS_CHECK_EQ(r.depth, 4);
    JASS_CHECK(r.nodes > 0);

    MoveList legal;
    generate_legal_moves(p, legal);
    JASS_CHECK(list_contains(legal, r.best_move));
}

void test_search_no_legal_moves_returns_mate() {
    // Black is to move with no pieces left at all → no legal moves.
    const Position p = parse("B:W31:B");

    SearchLimits lim;
    lim.max_depth = 3;
    const SearchResult r = search(p, lim);

    JASS_CHECK(r.score <= -(MATE_SCORE - MAX_PLY));
    JASS_CHECK(is_mate_score(r.score));
}

void test_search_finds_forced_capture() {
    // The only legal move captures black's lone piece, leaving black with
    // no pieces and therefore no legal reply: a mate-in-one for white.
    const Position p = parse("W:W28:B22");

    SearchLimits lim;
    lim.max_depth = 4;
    const SearchResult r = search(p, lim);

    JASS_CHECK_EQ(r.best_move.from, static_cast<Square>(28));
    JASS_CHECK_EQ(r.best_move.to,   static_cast<Square>(17));
    JASS_CHECK_EQ(r.best_move.num_captures, 1);
    JASS_CHECK(test(r.best_move.captured, static_cast<Square>(22)));
    JASS_CHECK(r.score >= MATE_SCORE - MAX_PLY);
    JASS_CHECK(is_mate_score(r.score));
}

void test_search_tablebase_draw_returns_a_legal_move() {
    // K vs K is a known draw, but it is not terminal. The root search must
    // return a legal move instead of the default 0-0/resignation sentinel.
    const Position p = parse("W:WK28:BK1");
    SearchLimits lim;
    lim.max_depth = 2;
    const SearchResult r = search(p, lim);

    MoveList legal;
    generate_legal_moves(p, legal);
    JASS_CHECK(list_contains(legal, r.best_move));
    JASS_CHECK(r.best_move.from != NO_SQUARE);
}

// ---------------------------------------------------------------------------
// Top-K exploration invariants (PR 384). Each of these pins a defect that
// shipped and was invisible in the published counters.
// ---------------------------------------------------------------------------

void test_topk_child_depth_is_one_ply_below_play_depth() {
    // A root search at depth d evaluates its children with d-1 plies. Ranking
    // a child with a fresh root search at d gives it one ply MORE than the
    // policy ever had; at d-2 it gets one less. Both shipped at some point.
    JASS_CHECK(jass::selfplay::topk_child_search_depth(8) == 7);
    JASS_CHECK(jass::selfplay::topk_child_search_depth(9) == 8);
    // search() iterates from depth one, so the horizon is clamped there.
    JASS_CHECK(jass::selfplay::topk_child_search_depth(1) == 1);
    JASS_CHECK(jass::selfplay::topk_child_search_depth(0) == 1);
}

void test_topk_dedupes_semantically_equal_moves() {
    // Move compares captured squares as a SET, and international draughts
    // reaches the same capture by several orders, so generate_legal_moves can
    // emit equal Moves. Without dedup one move takes several top-k slots and
    // the uniform draw is silently biased toward it.
    MoveList legal;
    Move a{}; a.from = static_cast<Square>(31); a.to = static_cast<Square>(27);
    Move b{}; b.from = static_cast<Square>(32); b.to = static_cast<Square>(28);
    legal.push(a);
    legal.push(a);   // same move reached by another path
    legal.push(b);
    const std::vector<Move> unique = jass::selfplay::unique_semantic_moves(legal);
    JASS_CHECK(unique.size() == 2);
    JASS_CHECK(unique[0] == a);
    JASS_CHECK(unique[1] == b);
}

void test_topk_child_history_includes_the_current_root() {
    // The ranking search must see the predecessors AND the position it is
    // descending from, otherwise a candidate that returns to an earlier
    // position is not scored as a repetition.
    Engine e;
    const std::vector<ZobristHash> before = e.hash_history();
    const std::vector<ZobristHash> history = jass::selfplay::topk_child_history(e);
    JASS_CHECK(history.size() == before.size() + 1);
    JASS_CHECK(history.back() == zobrist_hash(e.position()));
}

void test_topk_margin_collapses_to_the_best_move() {
    // The margin is the real filter; top-k is only a cap. With a stub ranking
    // that spreads the scores far apart, a tight margin must leave exactly one
    // eligible move — and say so, because the counter is how a job proves the
    // guard bit.
    Engine e;
    MoveList legal;
    generate_legal_moves(e.position(), legal);
    JASS_CHECK(legal.size() > 2);

    TranspositionTable tt;
    SearchLimits lim;
    lim.max_depth = 4;
    std::mt19937_64 rng(12345);

    // Stub search: score by from-square so the ordering is deterministic and
    // the gaps are far wider than the margin under test.
    int call = 0;
    auto stub = [&call](const Position&, const SearchLimits&,
                        TranspositionTable&, const std::vector<ZobristHash>&) {
        SearchResult r;
        r.score = -1000 * (call++);   // negated by the caller => descending
        return r;
    };
    const auto choice = jass::selfplay::select_topk_exploration_move_with(
        e, legal, lim, 3, /*margin=*/50, tt, rng, stub);
    JASS_CHECK(choice.ranked);
    JASS_CHECK(choice.eligible_candidates == 1);
    JASS_CHECK(choice.margin_singleton);
    JASS_CHECK(choice.child_search_depth == 3);
}

void test_topk_wide_margin_keeps_the_whole_cap() {
    Engine e;
    MoveList legal;
    generate_legal_moves(e.position(), legal);
    TranspositionTable tt;
    SearchLimits lim;
    lim.max_depth = 6;
    std::mt19937_64 rng(999);
    // All candidates score identically: nothing is separated, so the cap rules.
    auto stub = [](const Position&, const SearchLimits&,
                   TranspositionTable&, const std::vector<ZobristHash>&) {
        SearchResult r;
        r.score = 0;
        return r;
    };
    const auto choice = jass::selfplay::select_topk_exploration_move_with(
        e, legal, lim, 3, /*margin=*/50, tt, rng, stub);
    JASS_CHECK(choice.eligible_candidates == 3);
    JASS_CHECK(!choice.margin_singleton);
    JASS_CHECK(choice.child_search_depth == 5);
}

void test_split_rngs_keep_openings_independent_of_exploration() {
    // The point of the split, and the reason a paired A/B needs it: one arm
    // ranks (consuming exploration draws) and the other does not. On a shared
    // stream that desynchronises every later opening, so the two arms stop
    // being paired on the one thing held equal.
    jass::selfplay::SelfplayRngStreams a(4242, /*split=*/true);
    jass::selfplay::SelfplayRngStreams b(4242, /*split=*/true);
    for (int i = 0; i < 37; ++i) (void)b.exploration()();   // arm B explores more
    JASS_CHECK(a.opening()() == b.opening()());
    JASS_CHECK(a.role()() == b.role()());

    // Legacy mode is one shared stream — the historical sequence, bit for bit,
    // and therefore also the historical coupling.
    jass::selfplay::SelfplayRngStreams c(4242, /*split=*/false);
    jass::selfplay::SelfplayRngStreams d(4242, /*split=*/false);
    (void)d.exploration()();
    JASS_CHECK(c.opening()() != d.opening()());

    // The four split streams must not be the same sequence offset by a step.
    jass::selfplay::SelfplayRngStreams s(7, /*split=*/true);
    const auto o = s.opening()(), sa = s.sampling()(),
               x = s.exploration()(), r = s.role()();
    JASS_CHECK(o != sa && o != x && o != r && sa != x && sa != r && x != r);
}

void test_repeated_root_returns_a_legal_move() {
    // Same bug as the tablebase root, and far more common: a root already
    // present in `game_history` used to return before a move was ever
    // picked, so the HUB emitted `bestmove 0-0`. Against an opponent that
    // does not resign on repetitions this lost the game outright — it is
    // what made every Jass-vs-Scan cell of home-0997/0998/0999 collapse.
    const Position p = parse("W:WK50:BK1");
    TranspositionTable tt;
    SearchLimits lim;
    lim.max_depth = 2;
    const std::vector<ZobristHash> history{zobrist_hash(p)};
    const SearchResult r = search(p, lim, tt, history);

    MoveList legal;
    generate_legal_moves(p, legal);
    JASS_CHECK(!legal.empty());
    JASS_CHECK(list_contains(legal, r.best_move));
    JASS_CHECK(r.best_move.from != NO_SQUARE);
}

void test_fifty_move_root_returns_a_legal_move() {
    Position p = parse("W:WK50:BK1");
    p.set_halfmove_clock(FIFTY_MOVE_PLIES);
    TranspositionTable tt;
    SearchLimits lim;
    lim.max_depth = 2;
    const SearchResult r = search(p, lim, tt, {});

    MoveList legal;
    generate_legal_moves(p, legal);
    JASS_CHECK(!legal.empty());
    JASS_CHECK(list_contains(legal, r.best_move));
    JASS_CHECK(r.best_move.from != NO_SQUARE);
}

void test_qsearch_avoids_horizon_effect() {
    // White man at 33 vs black man at 22. White's two quiet moves are
    //   - 33-28 (NW): leaves white *en prise* — black 22 must capture 28
    //                 (mandatory) and lands at 33, leaving white with no
    //                 pieces and therefore mated.
    //   - 33-29 (NE): perfectly safe, no capture available for black.
    // Without quiescence the depth-1 leaf eval scores both moves equally
    // and the engine picks 33-28 because of move-ordering. Quiescence
    // plays the forced black capture out at the horizon and exposes the
    // true value of 33-28, so the engine must pick 33-29.
    const Position p = parse("W:W33:B22");
    SearchLimits lim;
    lim.max_depth = 1;
    const SearchResult r = search(p, lim);
    JASS_CHECK_EQ(r.best_move.from, static_cast<Square>(33));
    JASS_CHECK_EQ(r.best_move.to,   static_cast<Square>(29));
}

void test_search_score_reflects_material_lead() {
    // White has a king + a man, black has only a king: white is ahead by
    // roughly one man. The score from white's POV must be clearly positive
    // and not absurdly larger than a man's value at this depth.
    const Position p = parse("W:WK28,31:BK1");

    SearchLimits lim;
    lim.max_depth = 3;
    const SearchResult r = search(p, lim);

    MoveList legal;
    generate_legal_moves(p, legal);
    JASS_CHECK(list_contains(legal, r.best_move));
    JASS_CHECK(r.score > MAN_VALUE / 2);
    JASS_CHECK(r.score < KING_VALUE);
}

void test_search_with_multiple_threads() {
    // Lazy SMP must not change correctness: same depth, same legal best
    // move, same score (within a small tolerance because helper threads
    // may legitimately sharpen the score by deepening some branches via
    // the shared TT).
    const Position p = Position::start_position();

    SearchLimits a;
    a.max_depth = 4;
    a.tt_mb     = 4;
    a.threads   = 1;
    const SearchResult r1 = search(p, a);

    SearchLimits b;
    b.max_depth = 4;
    b.tt_mb     = 4;
    b.threads   = 4;
    const SearchResult r4 = search(p, b);

    JASS_CHECK_EQ(r1.depth, 4);
    JASS_CHECK_EQ(r4.depth, 4);

    MoveList legal;
    generate_legal_moves(p, legal);
    bool single_legal = false;
    bool smp_legal    = false;
    for (const auto& m : legal) {
        if (m == r1.best_move) single_legal = true;
        if (m == r4.best_move) smp_legal    = true;
    }
    JASS_CHECK(single_legal);
    JASS_CHECK(smp_legal);
}

void test_search_returns_pv_starting_with_best_move() {
    const Position p = Position::start_position();
    SearchLimits lim;
    lim.max_depth = 4;
    const SearchResult r = search(p, lim);
    JASS_CHECK(!r.pv.empty());
    JASS_CHECK(r.pv.front() == r.best_move);

    // Each pv move must be legal in the position obtained by replaying the
    // earlier ones.
    Position cur = p;
    for (const auto& m : r.pv) {
        MoveList legal;
        generate_legal_moves(cur, legal);
        bool ok = false;
        for (const auto& lm : legal) if (lm == m) { ok = true; break; }
        JASS_CHECK(ok);
        cur = cur.after(m);
    }
}

void test_search_depth_increases() {
    // Sanity: deeper iterative deepening visits strictly more nodes than a
    // shallow one (in a non-mate position) and still returns a legal move.
    const Position p = Position::start_position();

    SearchLimits lo;
    lo.max_depth = 2;
    SearchLimits hi;
    hi.max_depth = 4;

    const SearchResult r_lo = search(p, lo);
    const SearchResult r_hi = search(p, hi);

    JASS_CHECK_EQ(r_lo.depth, 2);
    JASS_CHECK_EQ(r_hi.depth, 4);
    JASS_CHECK(r_hi.nodes > r_lo.nodes);
}

void test_node_budget_policy_parsing_and_validation() {
    using namespace jass::selfplay;

    const auto choices = parse_weighted_node_budgets(
        "5000:10, 20000:25,80000:35");
    JASS_CHECK_EQ(choices.size(), 3U);
    JASS_CHECK_EQ(choices[1].nodes, 20000U);
    JASS_CHECK_EQ(choices[1].weight, 25U);

    const NodeBudgetPolicy fixed = NodeBudgetPolicy::fixed(
        80'000, SamplingGranularity::Move);
    JASS_CHECK_EQ(fixed.sample(1, 2, 3, 0), 80'000U);
    JASS_CHECK_EQ(fixed.min_nodes(), 80'000U);
    JASS_CHECK_EQ(fixed.max_nodes(), 80'000U);

    JASS_CHECK(throws_invalid_argument([] {
        (void)NodeBudgetPolicy::fixed(0, SamplingGranularity::Move);
    }));
    JASS_CHECK(throws_invalid_argument([] {
        (void)NodeBudgetPolicy::fixed(999, SamplingGranularity::Move);
    }));
    JASS_CHECK(throws_invalid_argument([] {
        (void)NodeBudgetPolicy::weighted({}, SamplingGranularity::Move);
    }));
    JASS_CHECK(throws_invalid_argument([] {
        (void)NodeBudgetPolicy::weighted(
            {{5'000, 0}, {20'000, 0}}, SamplingGranularity::Move);
    }));
    JASS_CHECK(throws_invalid_argument([] {
        (void)NodeBudgetPolicy::weighted(
            {{5'000, std::numeric_limits<std::uint64_t>::max()},
             {20'000, 1}}, SamplingGranularity::Move);
    }));
    JASS_CHECK(throws_invalid_argument([] {
        (void)parse_weighted_node_budgets("");
    }));
    JASS_CHECK(throws_invalid_argument([] {
        (void)parse_weighted_node_budgets("5000:-1");
    }));
    JASS_CHECK(throws_invalid_argument([] {
        (void)parse_weighted_node_budgets("5000:10,");
    }));
}

void test_node_budget_sampler_is_deterministic_and_isolated() {
    using namespace jass::selfplay;
    const NodeBudgetPolicy move_policy = NodeBudgetPolicy::weighted(
        {{5'000, 2}, {20'000, 5}, {80'000, 7}, {300'000, 4}},
        SamplingGranularity::Move);
    const std::uint64_t seed = 0x123456789ABCDEF0ULL;

    const auto first = move_policy.sample(seed, 17, 9, 1);
    JASS_CHECK_EQ(first, move_policy.sample(seed, 17, 9, 1));
    JASS_CHECK(first == 5'000 || first == 20'000
               || first == 80'000 || first == 300'000);

    bool ply_changed = false;
    for (std::uint32_t ply = 1; ply < 32; ++ply) {
        if (move_policy.sample(seed, 17, ply, ply & 1u)
            != move_policy.sample(seed, 17, 0, 0)) {
            ply_changed = true;
            break;
        }
    }
    JASS_CHECK(ply_changed);

    bool game_changed = false;
    for (std::uint64_t game = 18; game < 48; ++game) {
        if (move_policy.sample(seed, game, 9, 1) != first) {
            game_changed = true;
            break;
        }
    }
    JASS_CHECK(game_changed);

    const NodeBudgetPolicy game_policy = NodeBudgetPolicy::weighted(
        {{5'000, 1}, {20'000, 1}}, SamplingGranularity::Game);
    const auto per_game = game_policy.sample(seed, 99, 0, 0);
    for (std::uint32_t ply = 1; ply < 40; ++ply) {
        JASS_CHECK_EQ(game_policy.sample(seed, 99, ply, ply & 1u), per_game);
    }

    // Consuming Top-K's dedicated RNG stream cannot change the pure budget
    // hash. This pins the independence contract even as exploration evolves.
    SelfplayRngStreams streams(seed, true);
    for (int i = 0; i < 100; ++i) (void)streams.exploration()();
    JASS_CHECK_EQ(move_policy.sample(seed, 17, 9, 1), first);
}

void test_weighted_node_budget_frequencies() {
    using namespace jass::selfplay;
    const NodeBudgetPolicy policy = NodeBudgetPolicy::weighted(
        {{5'000, 1}, {20'000, 3}}, SamplingGranularity::Move);
    int low = 0;
    constexpr int samples = 20'000;
    for (int i = 0; i < samples; ++i) {
        const auto budget = policy.sample(
            1234, static_cast<std::uint64_t>(i / 100),
            static_cast<std::uint32_t>(i % 100),
            static_cast<std::uint8_t>(i & 1));
        JASS_CHECK(budget == 5'000 || budget == 20'000);
        if (budget == 5'000) ++low;
    }
    const double low_fraction = static_cast<double>(low) / samples;
    JASS_CHECK(low_fraction > 0.22);
    JASS_CHECK(low_fraction < 0.28);
}

void test_search_node_budget_stops_exactly_and_returns_legal_move() {
    const Position p = Position::start_position();
    MoveList legal;
    generate_legal_moves(p, legal);

    SearchLimits tiny;
    tiny.max_depth = MAX_PLY;
    tiny.max_nodes = 1;
    const SearchResult r_tiny = search(p, tiny);
    JASS_CHECK_EQ(r_tiny.nodes, 1U);
    JASS_CHECK(list_contains(legal, r_tiny.best_move));
    JASS_CHECK_EQ(r_tiny.completed_depth, 0);
    JASS_CHECK(r_tiny.aborted_iteration);
    JASS_CHECK(r_tiny.stop_reason == SearchStopReason::Nodes);

    SearchLimits low;
    low.max_depth = MAX_PLY;
    low.max_nodes = 1'000;
    const SearchResult r_low = search(p, low);
    JASS_CHECK_EQ(r_low.nodes, low.max_nodes);
    JASS_CHECK(list_contains(legal, r_low.best_move));
    JASS_CHECK(r_low.completed_depth == r_low.depth);
    JASS_CHECK(r_low.effective_depth > r_low.completed_depth);
    JASS_CHECK(r_low.aborted_iteration);

    SearchLimits high = low;
    high.max_nodes = 4'000;
    const SearchResult r_high = search(p, high);
    JASS_CHECK_EQ(r_high.nodes, high.max_nodes);
    JASS_CHECK(r_high.nodes > r_low.nodes);
    JASS_CHECK(list_contains(legal, r_high.best_move));
}

void test_unlimited_depth_search_keeps_historical_result() {
    const Position p = Position::start_position();
    SearchLimits historical;
    historical.max_depth = 4;
    const SearchResult before = search(p, historical);

    SearchLimits explicit_unlimited = historical;
    explicit_unlimited.max_nodes = 0;
    const SearchResult after = search(p, explicit_unlimited);
    JASS_CHECK(before.best_move == after.best_move);
    JASS_CHECK_EQ(before.score, after.score);
    JASS_CHECK_EQ(before.depth, after.depth);
    JASS_CHECK_EQ(before.nodes, after.nodes);
    JASS_CHECK_EQ(after.completed_depth, after.depth);
    JASS_CHECK_EQ(after.effective_depth, after.depth);
    JASS_CHECK(!after.aborted_iteration);
    JASS_CHECK(after.stop_reason == SearchStopReason::None);
}

void test_root_order_schedule_applies_and_fails_closed() {
    const Position p = parse("W:W31:B20");

    SearchLimits valid;
    valid.max_depth = 2;
    valid.root_order_schedule =
        "1:31-26,31-27;2:31-27,31-26";
    const SearchResult applied = search(p, valid);
    JASS_CHECK_EQ(applied.root_order_applications, 2U);
    JASS_CHECK_EQ(applied.root_order_failures, 0U);

    SearchLimits invalid;
    invalid.max_depth = 2;
    invalid.root_order_schedule =
        "1:31-26;2:31-27,31-26";
    const SearchResult rejected = search(p, invalid);
    JASS_CHECK_EQ(rejected.root_order_applications, 1U);
    JASS_CHECK_EQ(rejected.root_order_failures, 1U);

    // Regression witness from 0961: three geometrical routes used to emit
    // 2x35 capturing 8,30 three times. Move generation now exposes the same
    // nine semantic classes as Scan, and the class-order contract still
    // accepts the position.
    const Position duplicate_paths = parse("W:W40,43,K2:B8,18,29,30");
    MoveList duplicate_legal;
    generate_legal_moves(duplicate_paths, duplicate_legal);
    JASS_CHECK_EQ(duplicate_legal.size(), 9U);

    SearchLimits semantic;
    semantic.max_depth = 2;
    semantic.root_order_schedule =
        "1:2x22x8x18,2x27x8x18,2x31x8x18,2x36x8x18,"
        "2x35x8x30,2x33x8x29,2x38x8x29,2x42x8x29,2x47x8x29;"
        "2:2x33x8x29,2x35x8x30,2x22x8x18,2x27x8x18,"
        "2x31x8x18,2x36x8x18,2x38x8x29,2x42x8x29,2x47x8x29";
    const SearchResult semantic_applied = search(duplicate_paths, semantic);
    JASS_CHECK_EQ(semantic_applied.root_order_applications, 2U);
    JASS_CHECK_EQ(semantic_applied.root_order_failures, 0U);
}

// 1b search refinements (continuation history, improving, IID, multi-cut).
// `SearchLimits{}` already contains the tuned production SearchParams defaults;
// assigning `SearchParams{}` explicitly must therefore leave the search identical.
// Each opt-in flag must still return a legal best move and a sane (non-mate)
// score from the start position.
void test_explicit_default_params_match_searchlimits_default() {
    const Position p = Position::start_position();
    SearchLimits base;       base.max_depth = 7;
    const SearchResult r0 = search(p, base);

    // Explicit default params must reproduce the SearchLimits default exactly.
    SearchLimits same;       same.max_depth = 7; same.params = SearchParams{};
    const SearchResult r1 = search(p, same);
    JASS_CHECK_EQ(r0.nodes, r1.nodes);
    JASS_CHECK(r0.best_move == r1.best_move);
}

void test_1b_each_feature_searches_correctly() {
    const Position p = Position::start_position();
    MoveList legal;
    generate_legal_moves(p, legal);

    const char* specs[] = {
        "use_conthist=1",
        "use_improving=1",
        "iid_min_depth=4,iid_reduction=2",
        "multicut_min_depth=5,multicut_reduction=4,multicut_moves=6,multicut_cuts=3",
        // all together
        "use_conthist=1,use_improving=1,iid_min_depth=4,multicut_min_depth=5",
    };
    for (const char* spec : specs) {
        SearchLimits lim;
        lim.max_depth = 8;
        lim.params    = parse_search_params(spec);
        const SearchResult r = search(p, lim);
        JASS_CHECK(list_contains(legal, r.best_move));
        JASS_CHECK(!is_mate_score(r.score));   // start position isn't a mate
        JASS_CHECK(r.nodes > 0);
    }
}

}  // namespace

void run_search_tests() {
    test_eval_start_is_near_zero();
    test_eval_material_dominates_positional();
    test_eval_stm_flips_sign();
    test_eval_king_more_valuable_than_man();
    test_eval_advancement_bonus();
    test_eval_edge_file_penalty();
    test_eval_supports_score_higher_than_isolated();
    test_search_returns_legal_move_from_start();
    test_search_no_legal_moves_returns_mate();
    test_search_finds_forced_capture();
    test_search_tablebase_draw_returns_a_legal_move();
    test_topk_child_depth_is_one_ply_below_play_depth();
    test_topk_dedupes_semantically_equal_moves();
    test_topk_child_history_includes_the_current_root();
    test_topk_margin_collapses_to_the_best_move();
    test_topk_wide_margin_keeps_the_whole_cap();
    test_split_rngs_keep_openings_independent_of_exploration();
    test_repeated_root_returns_a_legal_move();
    test_fifty_move_root_returns_a_legal_move();
    test_qsearch_avoids_horizon_effect();
    test_search_score_reflects_material_lead();
    test_search_returns_pv_starting_with_best_move();
    test_search_with_multiple_threads();
    test_search_depth_increases();
    test_node_budget_policy_parsing_and_validation();
    test_node_budget_sampler_is_deterministic_and_isolated();
    test_weighted_node_budget_frequencies();
    test_search_node_budget_stops_exactly_and_returns_legal_move();
    test_unlimited_depth_search_keeps_historical_result();
    test_root_order_schedule_applies_and_fails_closed();
    test_explicit_default_params_match_searchlimits_default();
    test_1b_each_feature_searches_correctly();
}
