// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Unit tests for Zobrist hashing and the transposition table.

#include "test_framework.hpp"

#include "movegen.hpp"
#include "position.hpp"
#include "search.hpp"
#include "tt.hpp"
#include "zobrist.hpp"

#include <set>
#include <string_view>

using namespace jass;

namespace {

Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

// -----------------------------------------------------------------------------
// Zobrist
// -----------------------------------------------------------------------------
void test_zobrist_deterministic() {
    // Same position yields the same hash across calls.
    const Position p = Position::start_position();
    const ZobristHash h1 = zobrist_hash(p);
    const ZobristHash h2 = zobrist_hash(p);
    JASS_CHECK_EQ(h1, h2);
    JASS_CHECK(h1 != 0);
}

void test_zobrist_distinguishes_side_to_move() {
    const auto a = Position::from_fen("W:W31-50:B1-20");
    const auto b = Position::from_fen("B:W31-50:B1-20");
    JASS_CHECK(a.has_value() && b.has_value());
    JASS_CHECK(zobrist_hash(*a) != zobrist_hash(*b));
}

void test_zobrist_distinguishes_men_and_kings() {
    const auto man  = Position::from_fen("W:W31:B1");
    const auto king = Position::from_fen("W:WK31:B1");
    JASS_CHECK(man.has_value() && king.has_value());
    JASS_CHECK(zobrist_hash(*man) != zobrist_hash(*king));
}

void test_zobrist_incremental_matches_fen_roundtrip() {
    // Two construction paths must yield the same hash: building the
    // start position directly vs round-tripping it through FEN.
    const Position direct  = Position::start_position();
    const auto     parsed  = Position::from_fen(direct.to_fen());
    JASS_CHECK(parsed.has_value());
    JASS_CHECK_EQ(direct.hash(), parsed->hash());

    // Same after one applied move.
    MoveList ml;
    generate_legal_moves(direct, ml);
    JASS_CHECK(!ml.empty());
    const Position after = direct.after(ml[0]);
    const auto     after_parsed = Position::from_fen(after.to_fen());
    JASS_CHECK(after_parsed.has_value());
    JASS_CHECK_EQ(after.hash(), after_parsed->hash());
}

void test_zobrist_unique_across_first_ply() {
    // The 9 legal moves from the initial position should all yield distinct
    // hashes — sanity check that the hash actually depends on piece placement.
    const Position p = Position::start_position();
    MoveList moves;
    generate_legal_moves(p, moves);
    JASS_CHECK_EQ(moves.size(), static_cast<std::size_t>(9));

    std::set<ZobristHash> seen;
    seen.insert(zobrist_hash(p));
    for (const auto& m : moves) {
        seen.insert(zobrist_hash(p.after(m)));
    }
    JASS_CHECK_EQ(seen.size(), static_cast<std::size_t>(10));  // root + 9
}

// -----------------------------------------------------------------------------
// Transposition table
// -----------------------------------------------------------------------------
void test_tt_probe_miss_on_empty() {
    TranspositionTable tt;
    tt.resize_mb(1);
    TTEntry out;
    JASS_CHECK(!tt.probe(0xDEADBEEFULL, out));
}

void test_tt_store_then_probe() {
    TranspositionTable tt;
    tt.resize_mb(1);

    Move m;
    m.from = 31;
    m.to   = 26;

    tt.store(0xCAFEBABEULL, m, /*score=*/42, /*depth=*/4, Bound::Exact);

    TTEntry out;
    JASS_CHECK(tt.probe(0xCAFEBABEULL, out));
    JASS_CHECK_EQ(out.score, 42);
    JASS_CHECK_EQ(out.depth, 4);
    JASS_CHECK(out.bound == Bound::Exact);
    JASS_CHECK(out.best_move == m);
}

void test_tt_depth_preferred_replacement() {
    TranspositionTable tt;
    tt.resize_mb(1);

    Move ma; ma.from = 31; ma.to = 26;
    Move mb; mb.from = 32; mb.to = 28;

    // Deeper entry stored first.
    tt.store(0x1234ULL, ma, 100, /*depth=*/8, Bound::Exact);
    // Shallower entry must NOT overwrite.
    tt.store(0x1234ULL, mb, 200, /*depth=*/3, Bound::Exact);

    TTEntry out;
    JASS_CHECK(tt.probe(0x1234ULL, out));
    JASS_CHECK_EQ(out.score, 100);
    JASS_CHECK_EQ(out.depth, 8);

    // Same-depth or deeper entry overwrites.
    tt.store(0x1234ULL, mb, 200, /*depth=*/8, Bound::Exact);
    JASS_CHECK(tt.probe(0x1234ULL, out));
    JASS_CHECK_EQ(out.score, 200);
}

// -----------------------------------------------------------------------------
// Search × TT integration
// -----------------------------------------------------------------------------
void test_search_with_tt_still_finds_forced_capture() {
    const Position p = parse("W:W28:B22");
    SearchLimits lim;
    lim.max_depth = 4;
    const SearchResult r = search(p, lim);

    JASS_CHECK_EQ(r.best_move.from, static_cast<Square>(28));
    JASS_CHECK_EQ(r.best_move.to,   static_cast<Square>(17));
    JASS_CHECK(is_mate_score(r.score));
}

void test_search_with_tt_consistent_across_depths() {
    // Iterative deepening must not regress: a deeper search should never
    // pick a *strictly worse* move than a shallower one in a fixed
    // position. We just check that the best-move returned is legal at
    // every step.
    const Position p = Position::start_position();
    for (int d = 1; d <= 5; ++d) {
        SearchLimits lim;
        lim.max_depth = d;
        const SearchResult r = search(p, lim);
        MoveList legal;
        generate_legal_moves(p, legal);
        bool found = false;
        for (const auto& m : legal) if (m == r.best_move) { found = true; break; }
        JASS_CHECK(found);
        JASS_CHECK_EQ(r.depth, d);
    }
}

}  // namespace

void run_tt_tests() {
    test_zobrist_deterministic();
    test_zobrist_distinguishes_side_to_move();
    test_zobrist_distinguishes_men_and_kings();
    test_zobrist_incremental_matches_fen_roundtrip();
    test_zobrist_unique_across_first_ply();

    test_tt_probe_miss_on_empty();
    test_tt_store_then_probe();
    test_tt_depth_preferred_replacement();

    test_search_with_tt_still_finds_forced_capture();
    test_search_with_tt_consistent_across_depths();
}
